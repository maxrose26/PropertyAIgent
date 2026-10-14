"""Frozen Arcus invocation; existing B2 batch, one-off only, no deployment."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import re
import sys
import subprocess
import time

from . import batch
from .batch_supervisor import isolated
from .oldham_production import production_engine

WORKFLOW='.github/workflows/stage4-arcus-production-once.yml'
AUTHORITY='AUTHORISE_STAGE4_ARCUS_NINE_COUNCIL_COMPLETION_ONCE'
PHASES=('validation','catchup_a','catchup_b','catchup_c','catchup_d','catchup_e','catchup_f')
ENV_KEYS=('GITHUB_ACTIONS','RUNNER_ENVIRONMENT','GITHUB_EVENT_NAME','GITHUB_RUN_NUMBER',
          'GITHUB_RUN_ATTEMPT','GITHUB_RUN_ID','GITHUB_REPOSITORY','GITHUB_WORKFLOW_REF',
          'GITHUB_REF','ARCUS_WORKFLOW_SHA','PLAYWRIGHT_BROWSERS_PATH')


def admit(sha, *, workflow=WORKFLOW):
    if workflow not in {WORKFLOW,'.github/workflows/stage4-salford15-production-once.yml'}:
        raise ValueError('WORKFLOW_SCOPE')
    required=dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',
        GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',
        GITHUB_REPOSITORY='maxrose26/PropertyAIgent',GITHUB_REF='refs/heads/master',
        ARCUS_WORKFLOW_SHA=sha,
        GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+workflow+'@refs/heads/master')
    if not re.fullmatch('[0-9a-f]{40}',sha) or any(os.environ.get(k)!=v for k,v in required.items()):
        raise ValueError('ADMISSION')
    if not re.fullmatch('[1-9][0-9]*',os.environ.get('GITHUB_RUN_ID','')):raise ValueError('RUN_ID')
    if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=sha:raise ValueError('HEAD')
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],text=True).strip():raise ValueError('DIRTY')


def migrate_column():
    """One additive nullable column only. No application facts or generic migration."""
    from sqlalchemy import text
    engine=production_engine(secret_name='BATCH_DATABASE_URL',application_name='stage4_arcus_field_scope')
    try:
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL lock_timeout = '5s'"))
            row=conn.execute(text("SELECT data_type,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' AND table_name='applications' AND column_name='planning_field_verification' LIMIT 1")).one_or_none()
            if row is None:
                conn.execute(text('ALTER TABLE public.applications ADD COLUMN planning_field_verification TEXT NULL'))
            elif tuple(row)!=('text','YES',None):raise ValueError('COLUMN_CONTRACT')
        with engine.connect() as conn:
            row=conn.execute(text("SELECT data_type,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' AND table_name='applications' AND column_name='planning_field_verification' LIMIT 1")).one()
            if tuple(row)!=('text','YES',None):raise ValueError('COLUMN_READBACK')
        return {'column':'planning_field_verification','type':'text','nullable':True,'backfill':False,'readback':'MATCH'}
    finally:engine.dispose()


def worker(row,allowance,output):
    from .batch_transaction import run_transaction
    from .arcus_transport import retrieve
    engine=None
    a=batch.blank(row)
    a.update(b2_outcome='UNKNOWN',transaction='UNKNOWN',error='DB_REJECTED',cleanup='UNKNOWN',disposition='UNCERTAIN')
    with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
        try:
            engine=production_engine(secret_name='BATCH_DATABASE_URL',application_name='stage4_arcus_b2_once',idle_transaction_ms=60000)
            a=run_transaction(engine,row,lambda:retrieve(row['application_id']),allowance,
                              provenance='FRESH_OFFICIAL_SUMMARY',family='ARCUS')
        except Exception:pass  # no inference about commit on missing/failed audit
        finally:
            try:
                if engine is not None:
                    if engine.pool.checkedout():raise ValueError('CONNECTION_LEAK')
                    engine.dispose()
                if a['cleanup']!='FAILED':a['cleanup']='CLOSED'
            except Exception:a.update(cleanup='FAILED',error='CLEANUP_FAILED',disposition='SAFETY_STOP')
    batch.validate_record(a,row)
    with output.open('xb') as f:f.write(batch.encode(a,batch.MAX_RECORD))


def execute(sha,phase,output,validation):
    from .arcus_batch import CONTEXTS
    spec=CONTEXTS[phase]
    rows=batch.manifest(spec)
    if output.exists():raise ValueError('OUTPUT_EXISTS')
    if phase!='validation':
        if validation is None:raise ValueError('VALIDATION_REQUIRED')
        proof=json.loads(validation.read_bytes())
        batch.validate(proof,spec=CONTEXTS['validation'])
        if proof['repository_sha']!=sha or proof['invocation']!=os.environ['GITHUB_RUN_ID']+'-validation':raise ValueError('VALIDATION_IDENTITY')
        if any(r['transaction']!='COMMITTED' or r['disposition']!='COMPLETED' for r in proof['records']):raise ValueError('FAMILY_NOT_OPERATIONAL')
    environment={k:os.environ[k] for k in ENV_KEYS if k in os.environ}
    environment['BATCH_DATABASE_URL']=os.environ.pop('BATCH_DATABASE_URL','')
    if not environment['BATCH_DATABASE_URL']:raise ValueError('CREDENTIAL_MISSING')
    indices={r['identity']['application_id']:i for i,r in enumerate(rows)}
    def record(row,limits):
        def command(r,l,path):
            return [sys.executable,'-m','verification.direct_reference.arcus_production',
                    '--sha',sha,'--authority',AUTHORITY,'--phase',phase,'--output',str(path),
                    '--worker-index',str(indices[r['application_id']]),'--limits',json.dumps(l)]
        return isolated(row,limits,command,environment)
    try:
        audit=batch.run(sha,os.environ['GITHUB_RUN_ID']+'-'+phase,record,spec=spec)
        with output.open('xb') as f:f.write(batch.encode(audit))
        return 0 if audit['assessment']=='ACCOUNTED' else 1
    finally:environment.pop('BATCH_DATABASE_URL',None)


def main():
    p=argparse.ArgumentParser();p.add_argument('--sha',required=True);p.add_argument('--authority',required=True)
    p.add_argument('--phase',choices=PHASES);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--validation',type=Path);p.add_argument('--migrate',action='store_true')
    p.add_argument('--worker-index',type=int);p.add_argument('--limits')
    a=p.parse_args()
    try:
        if a.authority!=AUTHORITY:raise ValueError('AUTHORITY')
        admit(a.sha)
        if a.migrate:
            if a.phase or a.worker_index is not None or a.limits or a.output.exists():raise ValueError('MIGRATION_SCOPE')
            with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
                result=migrate_column()
            a.output.write_text(json.dumps(result))
            return 0
        if a.phase is None:raise ValueError('PHASE')
        if a.worker_index is not None:
            from .arcus_batch import CONTEXTS
            rows=batch.manifest(CONTEXTS[a.phase])
            if not 0<=a.worker_index<len(rows) or a.limits is None:raise ValueError('WORKER')
            limits=json.loads(a.limits)
            if limits != dict(requests=80,bytes=20*1024*1024,seconds=45,worker_seconds=75):raise ValueError('WORKER_LIMITS')
            worker(rows[a.worker_index]['identity'],limits,a.output)
            return 0
        if a.limits:raise ValueError('LIMITS')
        return execute(a.sha,a.phase,a.output,a.validation)
    except Exception:
        print('Arcus admission/execution stopped; inspect bounded audit. Do not retry uncertain persistence.',file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
