"""Single first production batch admission. Registration is not execution authority.

No synthetic/disposable loader or resume CLI. The sole production transport is
requests_session; B2 persistence and audit rules are the reviewed batch adapter.
"""
import argparse
import contextlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from dataclasses import dataclass

from . import batch
from .batch_supervisor import isolated,resource_limits

WORKFLOW='.github/workflows/stage4-batch-production-once.yml'
AUTHORITY='AUTHORISE_STAGE4_REPRESENTATIVE20_B2_BATCH_ONCE'
ENV_KEYS=('GITHUB_ACTIONS','RUNNER_ENVIRONMENT','GITHUB_EVENT_NAME','GITHUB_RUN_NUMBER',
          'GITHUB_RUN_ATTEMPT','GITHUB_RUN_ID','GITHUB_REPOSITORY','GITHUB_WORKFLOW_REF',
          'GITHUB_REF','BATCH_WORKFLOW_SHA')

@dataclass(frozen=True)
class Admission:
    manifest: batch.ManifestSpec
    workflow: str
    authority: str
    module: str
    application_name: str

REPRESENTATIVE=Admission(batch.REPRESENTATIVE,WORKFLOW,AUTHORITY,
    'verification.direct_reference.batch_production','stage4_representative20_once')

def admit(sha,digest,authority,env=None,*,context=None):
    c=REPRESENTATIVE if context is None else context
    e=os.environ if env is None else env
    if not re.fullmatch('[0-9a-f]{40}',sha) or digest!=c.manifest.digest or authority!=c.authority:raise ValueError('ADMISSION')
    required=dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_EVENT_NAME='workflow_dispatch',
        GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',GITHUB_REPOSITORY='maxrose26/PropertyAIgent',
        GITHUB_REF='refs/heads/master',BATCH_WORKFLOW_SHA=sha,
        GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+c.workflow+'@refs/heads/master')
    if any(e.get(k)!=v for k,v in required.items()) or not re.fullmatch('[1-9][0-9]*',e.get('GITHUB_RUN_ID','')):raise ValueError('WORKFLOW_ADMISSION')
    if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=sha:raise ValueError('HEAD')
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],text=True).strip():raise ValueError('DIRTY')
    rows=batch.manifest(c.manifest)
    return rows

def limits(value):
    caps=dict(requests=2,bytes=2_000_000,seconds=40,worker_seconds=45)
    if set(value)!=set(caps):raise ValueError('LIMIT_SCHEMA')
    for k,cap in caps.items():
        if type(value[k]) not in ((int,) if k in {'requests','bytes'} else (int,float)) or not math.isfinite(value[k]) or not 0<value[k]<=cap:raise ValueError('LIMIT_BOUND')
    return value

def validate(a,sha,run_id,*,context=None):
    batch.validate(a,spec=None if context is None else context.manifest)
    if a['repository_sha']!=sha or a['invocation']!=run_id or a['parent_audit_sha256'] is not None or a['carried_ids']:raise ValueError('FIRST_INVOCATION')
    for r in a['records']:
        if r['source'] is not None and r['source_provenance']!='FRESH_OFFICIAL_SUMMARY':raise ValueError('FRESH_SOURCE_REQUIRED')

def worker(row,allowance,output,*,context=None):
    c=REPRESENTATIVE if context is None else context
    resource_limits()
    a=batch.blank(row)
    a.update(b2_outcome='UNKNOWN',transaction='UNKNOWN',error='DB_REJECTED',cleanup='UNKNOWN',disposition='UNCERTAIN')
    engine=None
    # Prevent dependency diagnostics/DSNs, HTTP errors and B2 logs from entering
    # hosted output. Only the validated, minimal audit is exported.
    with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
        try:
            from .oldham_production import production_engine
            from .batch_transaction import run_transaction
            from .refresh import requests_session
            engine=production_engine(secret_name='BATCH_DATABASE_URL',application_name=c.application_name)
            a=run_transaction(engine,row,requests_session,allowance,provenance='FRESH_OFFICIAL_SUMMARY')
        except Exception:
            # Never infer no commit from an exception, even after a failed ack.
            pass
        finally:
            try:
                if engine is not None:
                    if engine.pool.checkedout():raise ValueError('CONNECTION_LEAK')
                    engine.dispose()
                if a['cleanup']!='FAILED':a['cleanup']='CLOSED'
            except Exception:a.update(cleanup='FAILED',error='CLEANUP_FAILED',disposition='SAFETY_STOP')
    batch.validate_record(a,row)
    if a['source'] is not None and a['source_provenance']!='FRESH_OFFICIAL_SUMMARY':raise ValueError('FRESH_SOURCE_REQUIRED')
    with output.open('xb') as f:f.write(batch.encode(a,batch.MAX_RECORD))
    return 0  # a valid rejection/safety audit is data, not a lost worker artifact

def execute(sha,digest,authority,output,job_start,*,clock=time.time,context=None):
    c=REPRESENTATIVE if context is None else context
    rows=admit(sha,digest,authority) if context is None else admit(sha,digest,authority,context=c)
    if output.exists():raise ValueError('OUTPUT_EXISTS')
    age=clock()-job_start
    # Full300s batch allowance plus20s cleanup must fit10min outer job.
    if not math.isfinite(age) or not 0<=age<280:raise ValueError('OUTER_DEADLINE')
    environment={k:os.environ[k] for k in ENV_KEYS}
    environment['BATCH_DATABASE_URL']=os.environ.pop('BATCH_DATABASE_URL','')
    if not environment['BATCH_DATABASE_URL']:raise ValueError('CREDENTIAL_MISSING')
    indices={r['identity']['application_id']:n for n,r in enumerate(rows)}
    def record(row,allowance):
        limits(allowance)
        def command(r,l,out):
            return [sys.executable,'-m',c.module,
                '--sha',sha,'--manifest-sha256',digest,'--authority',authority,'--job-start',str(job_start),
                '--output',str(out),'--worker-index',str(indices[r['application_id']]),
                '--limits',json.dumps(l,separators=(',',':'))]
        return isolated(row,allowance,command,environment)
    try:
        # No prior/resume arguments: first execution only, reviewed reusable core.
        audit=batch.run(sha,os.environ['GITHUB_RUN_ID'],record,spec=None if context is None else c.manifest)
        validate(audit,sha,os.environ['GITHUB_RUN_ID'],context=context)
        with output.open('xb') as f:f.write(batch.encode(audit))
        return 0 if audit['assessment']=='ACCOUNTED' else 1
    finally:environment.pop('BATCH_DATABASE_URL',None)

def main(context=None):
    p=argparse.ArgumentParser();p.add_argument('--sha',required=True)
    p.add_argument('--manifest-sha256',required=True);p.add_argument('--authority',required=True)
    p.add_argument('--job-start',type=float,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--worker-index',type=int,choices=range(20));p.add_argument('--limits')
    a=p.parse_args()
    try:
        rows=admit(a.sha,a.manifest_sha256,a.authority,context=context)
        if a.worker_index is not None:
            if a.limits is None or a.worker_index>=len(rows) or not 0<=time.time()-a.job_start<580:raise ValueError('WORKER_ADMISSION')
            return worker(rows[a.worker_index]['identity'],limits(json.loads(a.limits)),a.output,context=context)
        if a.limits is not None:raise ValueError('NO_CALLER_LIMITS')
        return execute(a.sha,a.manifest_sha256,a.authority,a.output,a.job_start,context=context)
    except Exception:
        print('Batch admission/audit failed; no diagnostic details exported',file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
