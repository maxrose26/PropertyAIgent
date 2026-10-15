"""Unregistered proposed primary53 execution binding; no live authority yet."""
import hashlib,os,re,time
from pathlib import Path
from . import bolton53_admission as shared
WORKFLOW='.github/workflows/stage4-r0-bolton53-admission-once.yml'
AUTHORITY='AUTHORISE_R0_BOLTON53_PRIMARY_ADMISSION_ONCE'
TEMPLATE=shared.PACK/'stage4-r0-bolton53-admission-once.yml.txt'


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
        and result.get('stop') is None and len(result.get('results',[]))==53
        and all(not r.get('stop') and r.get('transaction') in {'IDENTITY_COMMIT_READBACK_CONFIRMED','COMMIT_READBACK_CONFIRMED'} for r in result['results']))


def main():
    import argparse
    from .r0_registered_scopes import checkout
    from .bolton53_admission_supervisor import supervise
    p=argparse.ArgumentParser();p.add_argument('--reviewed-sha',required=True);p.add_argument('--manifest-sha',required=True)
    p.add_argument('--authority',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    admit(a.reviewed_sha,a.manifest_sha,a.authority,os.environ);checkout(a.reviewed_sha)
    # Secret is used in place after all pure execution guards; never returned.
    result=supervise(a.output,credential=os.environ['BOLTON_ADMISSION_DATABASE_URL'])
    return 0 if successful(result) else 1

if __name__=='__main__':raise SystemExit(main())
