"""Finite successor observations. No historical resume or additional calls."""
import hashlib,json,os,re,time
from pathlib import Path
from . import r0_registered_scopes as shared
from . import r0_recovery_proposal as recovery
from . import r0_proposal as outer
from . import finite_acceptance as finite
ROOT=Path(__file__).resolve().parents[2]
PACK=ROOT/'docs/design/stage4-r0-execution/completion-mandate-20261015'
PROFILES=json.loads((PACK/'registered-profiles.json').read_text())
PROFILES_SHA='6756e8e55f78eeaa81e074ee6ca3d4b3dabb12f2361f479d1379add01480ffd8'

def profile(scope):
    if hashlib.sha256((PACK/'registered-profiles.json').read_bytes()).hexdigest()!=PROFILES_SHA or scope not in PROFILES:raise ValueError('PROFILE_REJECTED')
    return PROFILES[scope]

def manifest(scope):
    p=profile(scope);raw=(PACK/p['manifest']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=p['manifest_sha']:raise ValueError('MANIFEST_REJECTED')
    return json.loads(raw)

def plan(scope):
    p=profile(scope);manifest(scope)
    return dict(scope=scope,manifest_sha256=p['manifest_sha'],limits={k:p[k] for k in ('calls','requests','bytes','seconds','output_bytes')})

def validate_plan(value):
    if not isinstance(value,dict) or value!=plan(value.get('scope')):raise ValueError('PLAN_REJECTED')
    return profile(value['scope'])


def admit(scope,sha,manifest_sha,authority,env,*,workflow_bytes=None,now=None):
    p=profile(scope);WORKFLOW=p['workflow'];TEMPLATE=PACK/('registered-'+scope+'.yml.txt')
    shared.q.credential_free(env)
    expected=dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_REPOSITORY='maxrose26/PropertyAIgent',
        GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF='refs/heads/master',GITHUB_SHA=sha,GITHUB_WORKFLOW_SHA=sha,
        GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+WORKFLOW+'@refs/heads/master',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1')
    if (not isinstance(sha,str) or not re.fullmatch('[0-9a-f]{40}',sha) or manifest_sha!=p['manifest_sha'] or authority!=p['authority']
        or any(env.get(k)!=v for k,v in expected.items())):raise ValueError('EXACT9_BINDING_REJECTED')
    if not re.fullmatch('[0-9]{10}',env.get('JOB_STARTED_EPOCH','')) or not 0<=time.time()-int(env['JOB_STARTED_EPOCH'])<=260:
        raise ValueError('SETUP_BOUND')
    # Injection only for offline equivalence tests; runtime reads registered path.
    raw=(ROOT/WORKFLOW).read_bytes() if workflow_bytes is None else workflow_bytes
    if raw!=TEMPLATE.read_bytes():raise ValueError('WORKFLOW_CONTENT_REJECTED')
    if scope=='bridge9':
        from datetime import datetime,timezone
        if (now or datetime.now(timezone.utc))<datetime(2026,10,15,23,tzinfo=timezone.utc):raise ValueError('CUT_NOT_REACHED')
    plan(scope)


def read(row):
    if row['council'] not in finite.ARCUS:return finite.read(row)
    import tempfile,contextlib
    from verification.direct_reference.instrumented_probe import supervised
    from app.pipeline.discovery_screening import retain_screening
    with tempfile.TemporaryDirectory(prefix='completion-metadata-') as directory:
        path=Path(directory)/'source.json'
        with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink):
            supervised('discovery_'+row['council']+'_ui_window',path,window=(row['start'],row['end']),metadata=True)
        if not path.is_file() or path.stat().st_size>=512000:raise ValueError('METADATA_AUDIT_BOUND')
        return retain_screening(json.loads(path.read_bytes()))


def execute_worker(value,output,audit_dir):
    shared.q.credential_free(os.environ);PROFILE=validate_plan(value)
    store=shared.AuditStore(audit_dir,PROFILE)
    fixed=manifest(value['scope']);blocked=[]
    if value['scope']=='residual4':
        # Retained evidence establishes no proof-improving change for these routes.
        # Explicit authority requires BLOCKED rather than repeating a known failure.
        blocked=[dict(window=r,outcome='BLOCKED_UNRESOLVED',reason='NO_SUPPORTED_NEW_PROOF_PATH_RETAINED') for r in fixed['rows'] if r['council'] in {'bury','oldham','tameside'}]
        fixed=dict(fixed,rows=[r for r in fixed['rows'] if r['council']=='rochdale'])
    result=recovery._execute_fixed(fixed,PROFILE['manifest_sha'],reader=read,
        limits=PROFILE,checkpoint=store.record,containment=True)
    result['blocked_unresolved']=blocked
    result['not_attempted']+= [x['window'] for x in blocked]
    if blocked:result['enumeration_completeness']='INCOMPLETE'
    store.finish(result,output)


def main():
    import argparse,resource
    p=argparse.ArgumentParser();p.add_argument('--scope',choices=PROFILES);p.add_argument('--worker',type=Path);p.add_argument('--audit-dir',type=Path)
    p.add_argument('--reviewed-sha');p.add_argument('--manifest-sha');p.add_argument('--authority');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--verify-audit',action='store_true');a=p.parse_args();shared.q.credential_free(os.environ)
    if not a.worker:PROFILE=profile(a.scope)
    if a.verify_audit:
        if shared.audit_bytes(a.output)>PROFILE['output_bytes']:raise ValueError('EXPORT_BOUND')
        m=json.loads((a.output/'execution.json').read_bytes())
        if m!=dict(sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],manifest_sha256=PROFILE['manifest_sha'],persistence=False,run_number=1,attempt=1):raise ValueError('EXPORT_IDENTITY')
        for path in a.output.rglob('*'):
            if path.is_file() and path.name not in {'result.json','execution.json'} and not re.fullmatch(r'checkpoints/[0-9]{3}\.json',path.relative_to(a.output).as_posix()):raise ValueError('EXPORT_PATH')
        return
    if a.worker:
        if a.worker.stat().st_size>20000 or a.output.exists() or a.audit_dir is None:raise ValueError('WORKER_CONTEXT')
        resource.setrlimit(resource.RLIMIT_FSIZE,(20_000_000,20_000_000))
        execute_worker(json.loads(a.worker.read_bytes()),a.output,a.audit_dir);return
    admit(a.scope,a.reviewed_sha,a.manifest_sha,a.authority,os.environ);shared.checkout(a.reviewed_sha);a.output.mkdir(exist_ok=False)
    (a.output/'execution.json').write_text(json.dumps(dict(sha=a.reviewed_sha,run_id=os.environ['GITHUB_RUN_ID'],manifest_sha256=PROFILE['manifest_sha'],persistence=False,run_number=1,attempt=1)))
    result=outer.supervise_round(plan(a.scope),a.output/'result.json',deadline=PROFILE['seconds'],worker_module='verification.discovery.completion_source')
    return 1 if result.get('stop_reason') else 0

if __name__=='__main__':raise SystemExit(main())
