"""One frozen transport diagnostic. No admission or database call."""
import argparse
import json
import os
from pathlib import Path
import re
from .committee_exact import targets, retrieve, MANIFEST_SHA
from .rejection_audit import observation_audit

WORKFLOW='.github/workflows/stage4-salford-1506-diagnostic-once.yml'
AUTHORITY='AUTHORISE_SALFORD_PA_2025_1506_TRANSPORT_DIAGNOSTIC_ONCE'


def admitted(sha, authority, env):
    return (bool(re.fullmatch('[0-9a-f]{40}',sha)) and authority==AUTHORITY
        and env.get('DIAGNOSTIC_WORKFLOW_SHA')==sha and env.get('GITHUB_REF')=='refs/heads/master'
        and env.get('GITHUB_RUN_NUMBER')=='1' and env.get('GITHUB_RUN_ATTEMPT')=='1'
        and env.get('GITHUB_ACTIONS')=='true' and env.get('RUNNER_ENVIRONMENT')=='github-hosted'
        and env.get('GITHUB_WORKFLOW_REF')=='maxrose26/PropertyAIgent/'+WORKFLOW+'@refs/heads/master'
        and not any('DATABASE' in key or key.startswith(('SUPABASE_','PGPASSWORD','PGUSER','PGHOST')) for key in env))


def diagnose(source_retrieve=retrieve):
    row=targets()[0]
    if (row['council'],row['reference'])!=('salford','PA/2025/1506'):
        raise ValueError('frozen diagnostic identity')
    resource=source_retrieve(row,None)
    return dict(council=row['council'],reference=row['reference'],source=resource['audit'],
        transport_failure=resource.get('failure'),observation_evidence=observation_audit(row,resource),
        database_connections=0,database_reads=0,database_writes=0,admission_attempts=0)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--sha',required=True);parser.add_argument('--authority',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if not admitted(args.sha,args.authority,os.environ):raise ValueError('diagnostic not admitted')
    output=dict(sha=args.sha,manifest_sha=MANIFEST_SHA,run_id=os.environ['GITHUB_RUN_ID'],
        execution='UNKNOWN',model_calls=0,results=[])
    try:
        result=diagnose();output['results'].append(result)
        source=result['source']
        if (source.get('cleanup_state')!='CLOSED' or source.get('budget_state')!='WITHIN_LIMITS'
                or result['transport_failure']):
            raise RuntimeError('diagnostic source boundary failed; no retry')
        output['execution']='DIAGNOSTIC_COMPLETED_NO_ADMISSION'
    except BaseException:
        output['execution']='DIAGNOSTIC_STOP_NO_RETRY'
        raise
    finally:
        raw=json.dumps(output,sort_keys=True)
        if len(raw.encode())>65536:raise ValueError('diagnostic audit size')
        Path(args.output).write_text(raw+'\n')

if __name__=='__main__':main()
