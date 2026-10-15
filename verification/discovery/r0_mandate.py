"""Finite successor observations. No historical resume or additional calls."""
import hashlib,json,os,re,time
from pathlib import Path
from . import r0_registered_scopes as shared
from . import r0_recovery_proposal as recovery
from . import r0_proposal as outer
from . import finite_acceptance as finite
ROOT=Path(__file__).resolve().parents[2]
PACK=ROOT/'docs/design/stage4-r0-execution/autonomous-recovery-20261015'
PROFILES=json.loads((PACK/'profiles.json').read_text())
PROFILES_SHA='1880db76a825f346344c575b1108dd315f26209c4ce5b20593bec2d18f073fd1'

def profile(scope):
    if hashlib.sha256((PACK/'profiles.json').read_bytes()).hexdigest()!=PROFILES_SHA or scope not in PROFILES:raise ValueError('PROFILE_REJECTED')
    return PROFILES[scope]

def manifest(scope):
    p=profile(scope);raw=(PACK/(scope+'.json')).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=p['manifest_sha']:raise ValueError('MANIFEST_REJECTED')
    return json.loads(raw)

def plan(scope):
    p=profile(scope);manifest(scope)
    return dict(scope=scope,manifest_sha256=p['manifest_sha'],limits={k:p[k] for k in ('calls','requests','bytes','seconds','output_bytes')})

def validate_plan(value):
    if not isinstance(value,dict) or value!=plan(value.get('scope')):raise ValueError('PLAN_REJECTED')
    return profile(value['scope'])


def admit(scope,sha,manifest_sha,authority,env,*,workflow_bytes=None):
    p=profile(scope);WORKFLOW=p['workflow'];TEMPLATE=PACK/(scope+'.yml.txt')
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
    plan(scope)


def execute_worker(value,output,audit_dir):
    shared.q.credential_free(os.environ);PROFILE=validate_plan(value)
    store=shared.AuditStore(audit_dir,PROFILE)
    result=recovery._execute_fixed(manifest(value['scope']),PROFILE['manifest_sha'],reader=finite.read,
        limits=PROFILE,checkpoint=store.record,containment=True)
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
    result=outer.supervise_round(plan(a.scope),a.output/'result.json',deadline=PROFILE['seconds'],worker_module='verification.discovery.r0_mandate')
    return 1 if result.get('stop_reason') else 0

if __name__=='__main__':raise SystemExit(main())
