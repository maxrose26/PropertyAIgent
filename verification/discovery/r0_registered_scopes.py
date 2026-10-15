"""Closed credential-free R0 registrations. No dispatch or persistence API."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from . import r0_fixed80_qualification as q
from . import r0_bolton53_qualification as b
from . import r0_recovery_proposal as recovery
from . import r0_proposal as original
from . import finite_acceptance as finite

ROOT=Path(__file__).resolve().parents[2]
PROFILES={
 'fixed80':dict(workflow='.github/workflows/stage4-r0-fixed80-qualification-once.yml',
   authority='AUTHORISE_R0_FIXED80_EXACT_RECORD_QUALIFICATION_ONCE',manifest=q.MANIFEST,
   manifest_sha=q.MANIFEST_SHA,calls=80,requests=160,bytes=160_000_000,seconds=4400,
   output_bytes=8_000_000,record_output_bytes=65536,job_seconds=4800),
 'untouched27':dict(workflow='.github/workflows/stage4-r0-untouched27-once.yml',
   authority='AUTHORISE_R0_27_UNTOUCHED_PRIMARY_WINDOWS_ONCE',
   manifest=ROOT/'docs/design/stage4-r0-execution/page-cap-correction/untouched27-manifest.json',
   manifest_sha='f99d86a5deb251f45c0787af295836aa948d8250d9f7b180062db229c6dc0e3d',
   calls=27,requests=1040,bytes=278686720,seconds=1900,output_bytes=20_000_000,record_output_bytes=1_048_576,job_seconds=2280),
 'untouched20':dict(workflow='.github/workflows/stage4-r0-untouched20-once.yml',
   authority='AUTHORISE_R0_20_UNTOUCHED_PRIMARY_WINDOWS_ONCE',
   manifest=ROOT/'docs/design/stage4-r0-execution/initial-application-preparation/primary-unattempted20.json',
   manifest_sha='7c46a54e91201ba2cff1b392e4d606f592f79a8752827e3536135bfb3912e66c',
   calls=20,requests=760,bytes=203772160,seconds=1220,output_bytes=20_000_000,
   record_output_bytes=1_048_576,job_seconds=1620,setup_seconds=260),
 'bolton53':dict(workflow='.github/workflows/stage4-r0-bolton53-qualification-once.yml',
   authority='AUTHORISE_R0_BOLTON53_INITIAL_LITERAL_QUALIFICATION_ONCE',manifest=b.MANIFEST,
   manifest_sha=b.MANIFEST_SHA,calls=53,requests=106,bytes=106_000_000,seconds=2915,
   output_bytes=8_000_000,record_output_bytes=65536,job_seconds=3360,setup_seconds=280),
}
RSS_LIMIT=1536*1024*1024
AUDIT_RESERVE=131072  # metadata, result envelope, not-attempted identities, outer audit
WORKFLOW_HASHES={'fixed80': 'daf3e452d0a89cd74a725a28aca7c14fb6bdbd63ce3eb0d37176e588dc89f32d', 'untouched27': 'a358223c5707c22d0550c9b966ea3b67f463f856f1624b5196b86d89ebb8583e'}

WORKFLOW_HASHES['untouched20']='0a6a9a647663fa17ef0bd3ada628633f398142003819d53952e1d2db3b3aef66'
WORKFLOW_HASHES['bolton53']='e7b44f658ebdf408bf467258836b0cd5d13eb748a7237bb371c63a766f73190d'

def plan(scope):
    if scope not in PROFILES:raise ValueError('SCOPE_REJECTED')
    p=PROFILES[scope];raw=p['manifest'].read_bytes()
    if hashlib.sha256(raw).hexdigest()!=p['manifest_sha']:raise ValueError('MANIFEST_REJECTED')
    if scope=='fixed80':q.targets()
    if scope=='bolton53':b.targets()
    return dict(scope=scope,manifest_sha256=p['manifest_sha'],limits={k:p[k] for k in
        ('calls','requests','bytes','seconds','output_bytes')})


def validate_plan(value):
    if not isinstance(value,dict) or value.get('scope') not in PROFILES or value!=plan(value['scope']):
        raise ValueError('PLAN_REJECTED')
    return PROFILES[value['scope']]


def admit(scope,sha,manifest_sha,authority,env):
    q.credential_free(env)
    if scope not in PROFILES:raise ValueError('SCOPE_REJECTED')
    p=PROFILES[scope]
    expected=dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',
        GITHUB_REPOSITORY='maxrose26/PropertyAIgent',GITHUB_EVENT_NAME='workflow_dispatch',
        GITHUB_REF='refs/heads/master',GITHUB_SHA=sha,GITHUB_WORKFLOW_SHA=sha,
        GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+p['workflow']+'@refs/heads/master',
        GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1')
    if (not isinstance(sha,str) or re.fullmatch('[0-9a-f]{40}',sha) is None
        or manifest_sha!=p['manifest_sha'] or authority!=p['authority']
        or any(env.get(k)!=v for k,v in expected.items())):raise ValueError('REGISTRATION_REJECTED')
    plan(scope)
    started=env.get('JOB_STARTED_EPOCH','')
    if (re.fullmatch('[0-9]{10}',started) is None or not 0<=time.time()-int(started)<=min(p['job_seconds']-p['seconds']-120,p.get('setup_seconds',10**9))):
        raise ValueError('SETUP_BUDGET_REJECTED')
    raw=(ROOT/p['workflow']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=WORKFLOW_HASHES.get(scope):raise ValueError('WORKFLOW_CONTENT_REJECTED')


def checkout(sha):
    if (subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=sha
        or subprocess.check_output(['git','status','--porcelain'],text=True).strip()):
        raise ValueError('CHECKOUT_REJECTED')


def audit_bytes(directory):
    total=0;files=0
    for path in Path(directory).rglob('*'):
        if path.is_symlink():raise ValueError('AUDIT_SYMLINK')
        if path.is_file():total+=path.stat().st_size;files+=1
        if files>85:raise ValueError('AUDIT_FILE_COUNT')
    return total


class AuditStore:
    """Bounded checkpoints plus a reserved second copy in the final result.

    The outer supervisor independently observes aggregate files and child RSS.
    Completed checkpoint files never change; a write/hash failure stops calls.
    """
    def __init__(self,directory,profile):
        self.root=Path(directory);self.p=profile;self.records=[];self.bytes=0;self.hashes=[]
        self.directory=self.root/'checkpoints';self.directory.mkdir(exist_ok=False)
    def record(self,value):
        raw=json.dumps(value,sort_keys=True).encode()+b'\n'
        if len(self.records)>=self.p['calls'] or len(raw)>=self.p['record_output_bytes']:
            raise ValueError('CHECKPOINT_RECORD_BOUND')
        # Checkpoint + final result copy; reserve all fixed envelopes up front.
        if 2*(self.bytes+len(raw))+self.p.get('audit_reserve',AUDIT_RESERVE)>self.p['output_bytes']:
            raise ValueError('AGGREGATE_AUDIT_BOUND')
        path=self.directory/f'{len(self.records):03}.json'
        with path.open('xb') as target:
            target.write(raw);target.flush();os.fsync(target.fileno())
        digest=hashlib.sha256(raw).hexdigest()
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('CHECKPOINT_HASH')
        fd=os.open(self.directory,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
        self.records.append(value);self.bytes+=len(raw);self.hashes.append(digest)
    def finish(self,result,path):
        result.update(checkpoint_sha256=self.hashes,checkpoint_bytes=self.bytes)
        raw=json.dumps(result,sort_keys=True).encode()+b'\n'
        if len(raw)+audit_bytes(self.root)+32768>self.p['output_bytes']:
            raise ValueError('FINAL_AUDIT_BOUND')
        with Path(path).open('xb') as target:
            target.write(raw);target.flush();os.fsync(target.fileno())


def execute_worker(value,output,audit_dir):
    q.credential_free(os.environ);p=validate_plan(value)
    store=AuditStore(audit_dir,p)
    try:
        if value['scope']=='fixed80':
            result=q.qualify(reader=q.read,checkpoint=store.record)
        elif value['scope']=='bolton53':
            result=b.qualify(reader=b.read,checkpoint=store.record)
        else:
            manifest=json.loads(p['manifest'].read_bytes())
            result=recovery._execute_fixed(manifest,p['manifest_sha'],reader=finite.read,
                limits=p,checkpoint=store.record)
    except Exception:
        # Never export raw source/parser exceptions. Previously checkpointed rows
        # remain in the upload directory; uncertain accounting blocks continuation.
        result=dict(stop_reason='WORKER_EXCEPTION_NO_RETRY',accounting_complete=False,
            persistence=False,completed_through_advanced=False,results=[],
            checkpointed_observations=len(store.records))
    try:store.finish(result,output)
    except Exception:
        result=dict(stop_reason='FINAL_AUDIT_FAILURE_NO_RETRY',accounting_complete=False,
            persistence=False,prior_stop_reason=result.get('stop_reason'),checkpointed_observations=len(store.records))
        raw=json.dumps(result).encode()
        if audit_bytes(audit_dir)+len(raw)+32768<=p['output_bytes']:
            Path(output).write_bytes(raw)
        else:raise ValueError('AUDIT_FAILURE_NO_OUTPUT') from None


def supervise(value,output,*,runner=None):
    p=validate_plan(value)
    kwargs={} if runner is None else dict(runner=runner)
    return original.supervise_round(value,output,deadline=p['seconds'],
        worker_module='verification.discovery.r0_registered_scopes',**kwargs)


def verify_export(scope,directory,env):
    """Read-only pre-upload gate. Never upload an over-limit or unbound audit."""
    if scope not in PROFILES:raise ValueError('EXPORT_SCOPE')
    p=PROFILES[scope];root=Path(directory)
    if not root.is_dir() or audit_bytes(root)>p['output_bytes']:raise ValueError('EXPORT_BOUND')
    paths=[x for x in root.rglob('*') if x.is_file()]
    for path in paths:
        relative=path.relative_to(root).as_posix()
        if relative not in {'execution.json','result.json'} and re.fullmatch(r'checkpoints/[0-9]{3}\.json',relative) is None:
            raise ValueError('EXPORT_PATH')
    metadata=root/'execution.json'
    if not metadata.is_file() or metadata.stat().st_size>65536:raise ValueError('EXPORT_METADATA')
    value=json.loads(metadata.read_bytes())
    if (value.get('scope')!=scope or value.get('sha')!=env.get('GITHUB_SHA')
        or value.get('run_id')!=env.get('GITHUB_RUN_ID') or value.get('run_number')!=1
        or value.get('attempt')!=1 or value.get('manifest_sha256')!=p['manifest_sha']
        or value.get('persistence') is not False):raise ValueError('EXPORT_IDENTITY')
    return audit_bytes(root)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scope',choices=PROFILES)
    parser.add_argument('--verify-audit',action='store_true')
    parser.add_argument('--reviewed-sha');parser.add_argument('--manifest-sha');parser.add_argument('--authority')
    parser.add_argument('--worker',type=Path);parser.add_argument('--audit-dir',type=Path)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    q.credential_free(os.environ)
    if args.verify_audit:
        verify_export(args.scope,args.output,os.environ);return 0
    if args.worker:
        if (args.worker.stat().st_size>20000 or args.output.exists() or args.audit_dir is None
            or os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted'):
            raise ValueError('WORKER_CONTEXT_REJECTED')
        value=json.loads(args.worker.read_bytes());p=validate_plan(value)
        import resource
        resource.setrlimit(resource.RLIMIT_FSIZE,(p['output_bytes'],p['output_bytes']))
        execute_worker(value,args.output,args.audit_dir);return 0
    admit(args.scope,args.reviewed_sha,args.manifest_sha,args.authority,os.environ)
    checkout(args.reviewed_sha);value=plan(args.scope);p=PROFILES[args.scope]
    args.output.mkdir(exist_ok=False)
    metadata=dict(scope=args.scope,sha=args.reviewed_sha,manifest_sha256=p['manifest_sha'],
        workflow=p['workflow'],workflow_sha256=WORKFLOW_HASHES[args.scope],
        run_id=os.environ['GITHUB_RUN_ID'],run_number=1,attempt=1,
        started_at=datetime.now(timezone.utc).isoformat(),persistence=False,
        production_database_connections=0,production_reads=0,production_writes=0,
        publication_coverage='UNKNOWN',latency='UNKNOWN',
        code_hashes={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in (
            Path(__file__),Path(original.__file__),Path(recovery.__file__),Path(q.__file__),
            Path(finite.__file__),Path(b.__file__),ROOT/'verification/direct_reference/instrumented_probe.py',
            ROOT/'verification/discovery/arcus_ui_config.py',ROOT/'verification/discovery/idox_window.py',
            ROOT/'app/pipeline/discovery_contract.py')})
    record=args.output/'execution.json';record.write_text(json.dumps(metadata,sort_keys=True))
    result=supervise(value,args.output/'result.json')
    other_bytes=audit_bytes(args.output)-record.stat().st_size
    metadata.update(ended_at=datetime.now(timezone.utc).isoformat(),aggregate_audit_bytes=0)
    for _ in range(5):metadata['aggregate_audit_bytes']=other_bytes+len(json.dumps(metadata,sort_keys=True).encode())
    record.write_text(json.dumps(metadata,sort_keys=True))
    if metadata['aggregate_audit_bytes']!=audit_bytes(args.output):raise ValueError('AUDIT_ACCOUNTING')
    if audit_bytes(args.output)>p['output_bytes']:raise ValueError('AGGREGATE_AUDIT_BOUND')
    return 0 if (not result.get('stop_reason') and result.get('accounting_complete') is True
        and result.get('outer_supervisor',{}).get('cleanup')=='CLOSED') else 1

if __name__=='__main__':raise SystemExit(main())
