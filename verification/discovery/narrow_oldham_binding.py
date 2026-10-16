"""Unregistered proposed primary53 execution binding; no live authority yet."""
import hashlib,os,re,time
from pathlib import Path
from . import narrow_oldham as shared
WORKFLOW='.github/workflows/stage4-oldham-two-capture-once.yml'
AUTHORITY='AUTHORISE_OLDHAM_TWO_COUPLED_CAPTURE_ONCE'
TEMPLATE=shared.PACK/'registered-oldham2.yml.txt'


def admit(sha,manifest,authority,env,*,workflow_bytes=None):
    expected=dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_REPOSITORY='maxrose26/PropertyAIgent',
        GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF='refs/heads/master',GITHUB_SHA=sha,GITHUB_WORKFLOW_SHA=sha,
        GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+WORKFLOW+'@refs/heads/master',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1')
    if (not isinstance(sha,str) or not re.fullmatch('[0-9a-f]{40}',sha) or manifest!=shared.COHORT_SHA or authority!=AUTHORITY
        or any(env.get(k)!=v for k,v in expected.items())):raise ValueError('ADMISSION_BINDING_REJECTED')
    if not re.fullmatch('[0-9]{10}',env.get('JOB_STARTED_EPOCH','')) or not 0<=time.time()-int(env['JOB_STARTED_EPOCH'])<=280:
        raise ValueError('SETUP_BOUND')
    raw=(shared.ROOT/WORKFLOW).read_bytes() if workflow_bytes is None else workflow_bytes
    if raw!=TEMPLATE.read_bytes():raise ValueError('WORKFLOW_CONTENT_REJECTED')
    list(shared.rows())


def successful(value):
    result=value.get('result')
    return (value.get('stop_reason') is None and value.get('accounting_complete') is True
        and value.get('cleanup')=='CLOSED' and value.get('live_owned_survivors')==0
        and value.get('transaction')=='PER_RECORD_DISPOSITIONS' and isinstance(result,dict)
        and result.get('stop') is None and len(result.get('results',[]))==2
        and all(not r.get('stop') and r.get('transaction') in {'IDENTITY_COMMIT_READBACK_CONFIRMED','COMMIT_READBACK_CONFIRMED','NOT_STARTED'} for r in result['results']))


def main():
    import argparse
    from .r0_registered_scopes import checkout
    from .narrow_oldham_supervisor import supervise
    p=argparse.ArgumentParser();p.add_argument('--reviewed-sha');p.add_argument('--manifest-sha')
    p.add_argument('--authority');p.add_argument('--output',type=Path,required=True);p.add_argument('--verify-audit',action='store_true');a=p.parse_args()
    if a.verify_audit:
        from .narrow_oldham_supervisor import files
        if files(a.output)>shared.LIMITS['output_bytes'] or any(x.is_symlink() for x in a.output.rglob('*')):raise ValueError('AUDIT_BOUND')
        import json
        for path in a.output.rglob('*'):
            rel=path.relative_to(a.output).as_posix()
            if path.is_file() and rel not in {'execution.json','supervisor.json','worker-result.json'} and not re.fullmatch(r'(phase-[0-9]{3}|checkpoints/[0-9]{3})\.json',rel):raise ValueError('AUDIT_PATH')
        meta=json.loads((a.output/'execution.json').read_bytes())
        if meta!=dict(sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],cohort_sha256=shared.COHORT_SHA,run_number=1,attempt=1):raise ValueError('EXECUTION_IDENTITY')
        v=json.loads((a.output/'supervisor.json').read_bytes())
        if v.get('cohort_sha256')!=shared.COHORT_SHA or v.get('primary_sha256')!=shared.PRIMARY_SHA:raise ValueError('AUDIT_IDENTITY')
        return
    admit(a.reviewed_sha,a.manifest_sha,a.authority,os.environ);checkout(a.reviewed_sha)
    # Secret is used in place after all pure execution guards; never returned.
    result=supervise(a.output,credential=os.environ['BOLTON_ADMISSION_DATABASE_URL'],execution=dict(sha=a.reviewed_sha,run_id=os.environ['GITHUB_RUN_ID'],cohort_sha256=shared.COHORT_SHA,run_number=1,attempt=1))
    return 0 if successful(result) else 1

if __name__=='__main__':raise SystemExit(main())
