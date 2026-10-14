"""Frozen single-record wrapper around shared PR84 admission; no new writer."""
import argparse
import json
import os
from pathlib import Path
import re
from sqlalchemy import select,text
from sqlalchemy.orm import Session
from app.db.models import Application
from .committee_exact import targets,checked_engine,_validate_cohort,_run_cohort,MANIFEST_SHA

WORKFLOW='.github/workflows/stage4-manchester-145583-admission-once.yml'
AUTHORITY='AUTHORISE_MANCHESTER_145583_FO_2026_ADMISSION_ONCE'


def cohort():
    row=targets()[1]
    if (row['council'],row['reference'])!=('manchester','145583/FO/2026'):
        raise ValueError('frozen Manchester identity')
    return (row,)


def admitted(sha,authority,env):
    return (bool(re.fullmatch('[0-9a-f]{40}',sha)) and authority==AUTHORITY
        and env.get('COMMITTEE_WORKFLOW_SHA')==sha and env.get('GITHUB_REF')=='refs/heads/master'
        and env.get('GITHUB_RUN_NUMBER')=='1' and env.get('GITHUB_RUN_ATTEMPT')=='1'
        and env.get('GITHUB_ACTIONS')=='true' and env.get('RUNNER_ENVIRONMENT')=='github-hosted'
        and env.get('GITHUB_WORKFLOW_REF')=='maxrose26/PropertyAIgent/'+WORKFLOW+'@refs/heads/master')


def absence(engine):
    with Session(engine) as session:
        if engine.dialect.name=='postgresql':
            session.execute(text('SET TRANSACTION READ ONLY'))
            session.execute(text("SET LOCAL statement_timeout = '10s'"))
        rows=session.execute(select(Application.id,Application.council_code,Application.reference)
            .where(Application.council_code=='manchester',Application.reference=='145583/FO/2026').limit(2)).mappings().all()
        return [dict(row) for row in rows]


def execute(engine,run_id,results=None,source_retrieve=None):
    duplicate=absence(engine)
    if duplicate:raise RuntimeError('ALREADY_EXISTS_AT_EXECUTION; stop without admission')
    kwargs={} if source_retrieve is None else dict(source_retrieve=source_retrieve)
    outcome=_run_cohort(engine,run_id,cohort(),results=results,**kwargs)
    if outcome[0]['admission']['outcome']=='ALREADY_KNOWN':
        raise RuntimeError('ALREADY_EXISTS_AT_EXECUTION; identity race stopped without factual write')
    outcome[0]['pre_admission_absence_check']='NO_MATCH_EXACT_COUNCIL_REFERENCE_LIMIT_2'
    return outcome


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--sha',required=True);parser.add_argument('--authority',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--transport-only',action='store_true')
    args=parser.parse_args()
    if not admitted(args.sha,args.authority,os.environ):raise ValueError('execution not admitted')
    engine=None
    audit=dict(sha=args.sha,manifest_sha=MANIFEST_SHA,run_id=os.environ['GITHUB_RUN_ID'],
        results=[],model_calls=0,execution='UNKNOWN',site_relationship='UNKNOWN',application_role='UNKNOWN')
    try:
        if args.transport_only:
            if any('DATABASE' in k or k.startswith('SUPABASE_') for k in os.environ):
                raise ValueError('transport credential forbidden')
            _validate_cohort(cohort(),results=audit['results'])
        else:
            engine=checked_engine(os.environ['COMMITTEE_DATABASE_URL'])
            execute(engine,audit['run_id'],results=audit['results'])
        audit['execution']='COMPLETED'
    except BaseException:
        audit['execution']='STOP_NO_RETRY';raise
    finally:
        if engine is not None:engine.dispose()
        raw=json.dumps(audit,sort_keys=True,default=str)
        if len(raw.encode())>65536:raise ValueError('audit size')
        Path(args.output).write_text(raw+'\n')

if __name__=='__main__':main()
