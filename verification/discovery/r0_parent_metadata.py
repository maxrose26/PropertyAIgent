"""Unregistered fixed-two source-only execution proposal. No dispatch or writer."""
import argparse,hashlib,json,math,os,re,sys,time,tempfile
from pathlib import Path
import requests
from . import bolton_parent_metadata as metadata
from . import r0_proposal as outer,r0_registered_scopes as shared

ROOT=Path(__file__).resolve().parents[2]
PACK=ROOT/'docs/design/stage4-r0-execution/exact9-registration-parent-controls'
MANIFEST=PACK/'two-parent-manifest.json'
MANIFEST_SHA='9997f55e9af0e646ccf376137f79534fbc73e75e0c0984dffc222ee811f711fa'
WORKFLOW='.github/workflows/stage4-bolton-two-parent-metadata-once.yml'
TEMPLATE=PACK/'stage4-bolton-two-parent-metadata-once.yml.txt'
AUTHORITY='AUTHORISE_BOLTON_TWO_PARENT_METADATA_ONCE'
# Active supervisor150s + bounded kill/wait/process closure <=8s + export2s.
# Per-parent source45s + child startup5s + cleanup8s fits60s reservation.
PROFILE=dict(calls=2,requests=12,bytes=6_000_000,source_seconds=90,seconds=150,
    execution_seconds=160,output_bytes=131072,record_output_bytes=16384,
    audit_reserve=32768,setup_seconds=120,job_seconds=360)


def plan(index=None):
    raw=MANIFEST.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=MANIFEST_SHA:raise ValueError('MANIFEST_REJECTED')
    if tuple(json.loads(raw)['references'])!=metadata.REFERENCES:raise ValueError('FIXED_PARENTS_REJECTED')
    if index is not None and (type(index) is not int or not 0<=index<2):raise ValueError('RECORD_INDEX')
    return dict(scope='two_parents' if index is None else 'parent_record',index=index,
        manifest_sha256=MANIFEST_SHA,persistence=False)


def validate_plan(value):
    if not isinstance(value,dict) or value!=plan(value.get('index')):raise ValueError('PLAN_REJECTED')
    if value['index'] is None:return PROFILE
    return dict(calls=1,requests=6,bytes=3_000_000,seconds=50,output_bytes=65536)


def admit(sha,digest,authority,env,*,workflow_bytes=None):
    shared.q.credential_free(env)
    expected=dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',
        GITHUB_REPOSITORY='maxrose26/PropertyAIgent',GITHUB_EVENT_NAME='workflow_dispatch',
        GITHUB_REF='refs/heads/master',GITHUB_SHA=sha,GITHUB_WORKFLOW_SHA=sha,
        GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+WORKFLOW+'@refs/heads/master',
        GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1')
    if not isinstance(sha,str) or not re.fullmatch('[0-9a-f]{40}',sha) or digest!=MANIFEST_SHA or authority!=AUTHORITY or any(env.get(k)!=v for k,v in expected.items()):raise ValueError('BINDING_REJECTED')
    stamp=env.get('JOB_STARTED_EPOCH','')
    if not re.fullmatch('[0-9]{10}',stamp) or not 0<=time.time()-int(stamp)<=120:raise ValueError('SETUP_BOUND')
    raw=(ROOT/WORKFLOW).read_bytes() if workflow_bytes is None else workflow_bytes
    if raw!=TEMPLATE.read_bytes():raise ValueError('WORKFLOW_CONTENT_REJECTED')
    plan()


def source_worker(index,*,session_factory=requests.Session):
    """One owned, closed HTTP session; called only in isolated record process."""
    shared.q.credential_free(os.environ);plan(index);session=session_factory()
    result=None;closed=False
    try:
        session.trust_env=False
        session.mount('https://',requests.adapters.HTTPAdapter(max_retries=0))
        def dispatch(method,url,**kwargs):
            kwargs.pop('deadline',None);kwargs['timeout']=(3,8)
            return session.request(method,url,**kwargs)
        result=metadata.metadata(metadata.REFERENCES[index],dispatch)
    finally:
        try:session.close();closed=True
        except Exception:closed=False
    if result is None:raise ValueError('SOURCE_WORKER_REJECTED')
    result['session_cleanup']='CLOSED' if closed else 'UNKNOWN'
    # Limit output BEFORE checkpoint duplication; withhold, never truncate facts.
    if len(json.dumps(result).encode())>12288:
        result['fields']={};result['failure']='METADATA_OUTPUT_BOUND'
    return result


def read(index):
    """Reuse same owned-process supervisor for each fresh credential-free child."""
    with tempfile.TemporaryDirectory(prefix='bolton-parent-record-') as td:
        path=Path(td)/'record.json'
        value=outer.supervise_round(plan(index),path,deadline=50,
            worker_module='verification.discovery.r0_parent_metadata')
        if not path.is_file() or path.stat().st_size>PROFILE['record_output_bytes']:raise ValueError('RECORD_AUDIT_BOUND')
        if json.loads(path.read_bytes())!=value:raise ValueError('RECORD_AUDIT_MISMATCH')
        return value


def verified(index,value):
    o=value.get('outer_supervisor',{});r=value.get('resource',{})
    counters=(r.get('requests_attempted'),r.get('received_bytes'))
    elapsed=r.get('elapsed_seconds')
    if (value.get('reference')!=metadata.REFERENCES[index] or value.get('council')!='bolton'
        or value.get('persistence') is not False or value.get('admission_authorised') is not False
        or value.get('failure') is not None or value.get('identity')!='EXACT_DISPLAYED_REFERENCE'
        or value.get('cleanup')!='BOUNDARY_CLOSED' or value.get('session_cleanup')!='CLOSED'
        or r.get('budget_exhaustion') is not False
        or any(type(x) is not int for x in counters)
        or not 0<=counters[0]<=6 or not 0<=counters[1]<=3_000_000
        or type(elapsed) not in (int,float) or not math.isfinite(elapsed) or not 0<=elapsed<=45
        or o.get('cleanup')!='CLOSED' or type(o.get('live_owned_survivors')) is not int or o['live_owned_survivors']!=0
        or o.get('expired') is not False or type(o.get('exit_code')) is not int or o.get('exit_code')!=0 or o.get('limit_hit') is not None
        or value.get('accounting_complete') is False):return False
    return True


def execute(output,audit_dir,*,reader=read,clock=time.monotonic,store_factory=shared.AuditStore):
    shared.q.credential_free(os.environ);plan();store=store_factory(audit_dir,PROFILE)
    started=clock();results=[];stop=None;used_requests=used_bytes=0;source_seconds=0;attempted=0
    for index,reference in enumerate(metadata.REFERENCES):
        if (clock()-started+60+10>PROFILE['seconds'] or used_requests+6>12 or used_bytes+3_000_000>6_000_000
                or source_seconds+45>90):stop='AGGREGATE_BUDGET_NO_NEXT_CALL';break
        attempted+=1
        try:value=reader(index)
        except Exception:stop='WORKER_OR_ACCOUNTING_UNCERTAIN_NO_NEXT_CALL';break
        if not isinstance(value,dict) or len(json.dumps(value).encode())>=PROFILE['record_output_bytes']:
            stop='INVALID_WORKER_AUDIT_NO_NEXT_CALL';break
        results.append(value)
        try:store.record(value)
        except Exception:stop='CHECKPOINT_UNCERTAIN_NO_NEXT_CALL';break
        if not verified(index,value):stop='SOURCE_IDENTITY_RESOURCE_OR_CLEANUP_REJECTED';break
        r=value['resource'];used_requests+=r['requests_attempted'];used_bytes+=r['received_bytes'];source_seconds+=r['elapsed_seconds']
    result=dict(results=results,attempted=attempted,not_attempted=list(metadata.REFERENCES[attempted:]),
        stop_reason=stop,accounting_complete=stop is None,
        requests=used_requests if stop is None else None,received_bytes=used_bytes if stop is None else None,
        known_verified_requests=used_requests,known_verified_received_bytes=used_bytes,
        source_seconds=source_seconds if stop is None else None,known_verified_source_seconds=source_seconds,
        elapsed_seconds=clock()-started,persistence=False,admission_authorised=False)
    store.finish(result,output);return result


def execute_worker(value,output,audit_dir):
    validate_plan(value);shared.q.credential_free(os.environ)
    index=value['index']
    if index is None:return execute(output,audit_dir)
    result=source_worker(index)
    raw=json.dumps(result,sort_keys=True).encode()
    if len(raw)>16384:raise ValueError('WORKER_OUTPUT_BOUND')
    with Path(output).open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())


def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',type=Path);p.add_argument('--audit-dir',type=Path)
    p.add_argument('--reviewed-sha');p.add_argument('--manifest-sha');p.add_argument('--authority');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--verify-audit',action='store_true');a=p.parse_args();shared.q.credential_free(os.environ)
    if a.verify_audit:
        if shared.audit_bytes(a.output)>131072:raise ValueError('EXPORT_BOUND')
        m=json.loads((a.output/'execution.json').read_bytes())
        if m!=dict(sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],manifest_sha256=MANIFEST_SHA,persistence=False,run_number=1,attempt=1):raise ValueError('EXPORT_IDENTITY')
        for f in a.output.rglob('*'):
            if f.is_file() and f.name not in {'result.json','execution.json'} and not re.fullmatch(r'checkpoints/[0-9]{3}\.json',f.relative_to(a.output).as_posix()):raise ValueError('EXPORT_PATH')
        return
    if a.worker:
        if a.worker.stat().st_size>20000 or a.output.exists() or a.audit_dir is None:raise ValueError('WORKER_CONTEXT')
        import resource
        resource.setrlimit(resource.RLIMIT_FSIZE,(131072,131072))
        execute_worker(json.loads(a.worker.read_bytes()),a.output,a.audit_dir)
        return 0
    admit(a.reviewed_sha,a.manifest_sha,a.authority,os.environ);shared.checkout(a.reviewed_sha);a.output.mkdir(exist_ok=False)
    (a.output/'execution.json').write_text(json.dumps(dict(sha=a.reviewed_sha,run_id=os.environ['GITHUB_RUN_ID'],manifest_sha256=MANIFEST_SHA,persistence=False,run_number=1,attempt=1)))
    result=outer.supervise_round(plan(),a.output/'result.json',deadline=150,worker_module='verification.discovery.r0_parent_metadata')
    return 1 if result.get('stop_reason') else 0

if __name__=='__main__':raise SystemExit(main())
