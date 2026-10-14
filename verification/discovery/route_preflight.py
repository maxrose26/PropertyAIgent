"""Connection-free preflight entry. Template is NOT registered or authorised."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from .route_validation import route_audit

WORKFLOW='.github/workflows/stage4-route-preflight-once.yml'
AUTHORITY='AUTHORISE_CONNECTION_FREE_ROUTE_PREFLIGHT_ONCE'


def admitted(sha,authority,env):
    return (bool(re.fullmatch('[0-9a-f]{40}',sha)) and authority==AUTHORITY
        and env.get('GITHUB_SHA')==sha and env.get('PREFLIGHT_WORKFLOW_SHA')==sha
        and env.get('GITHUB_REF')=='refs/heads/master'
        and env.get('GITHUB_ACTIONS')=='true' and env.get('RUNNER_ENVIRONMENT')=='github-hosted'
        and env.get('GITHUB_RUN_NUMBER')=='1' and env.get('GITHUB_RUN_ATTEMPT')=='1'
        and env.get('GITHUB_EVENT_NAME')=='workflow_dispatch'
        and env.get('GITHUB_REPOSITORY')=='maxrose26/PropertyAIgent'
        and env.get('GITHUB_WORKFLOW_REF')=='maxrose26/PropertyAIgent/'+WORKFLOW+'@refs/heads/master')


def evaluate(raw):
    return dict(route_validation=route_audit(raw),engine_construction=False,database_connections=0,
        production_reads=0,production_writes=0,source_requests=0,admission_calls=0,
        authentication='NOT_TESTED',connectivity='NOT_TESTED')


def main():
    p=argparse.ArgumentParser();p.add_argument('--sha',required=True);p.add_argument('--authority',required=True)
    p.add_argument('--output',required=True);a=p.parse_args()
    if not admitted(a.sha,a.authority,os.environ):raise RuntimeError('PREFLIGHT_NOT_ADMITTED') from None
    if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=a.sha:
        raise RuntimeError('PREFLIGHT_NOT_ADMITTED') from None
    if Path(a.output).exists():raise RuntimeError('EXISTING_AUDIT') from None
    result=evaluate(os.environ.pop('PREFLIGHT_DATABASE_URL',''))
    result.update(sha=a.sha,run_id=os.environ.get('GITHUB_RUN_ID'),execution='CONNECTION_FREE_VALIDATION_COMPLETED')
    Path(a.output).write_text(json.dumps(result,sort_keys=True)+'\n')

if __name__=='__main__':main()
