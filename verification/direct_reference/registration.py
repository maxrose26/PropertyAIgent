"""Three frozen Idox summaries, audit only. Registration never authorises execution."""
import argparse
from dataclasses import asdict
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import resource
import subprocess
import sys
import tempfile
import time

from verification.stage26b_l1.actions_canary import ImportFence, offline_network_denial
from verification.stage26b_l1.actions_runner import supervise

AUTHORITY = 'AUTHORISE_STAGE4_THREE_SUMMARIES_ONCE_NO_PERSISTENCE'
WORKFLOW = '.github/workflows/stage4-direct-live-once.yml'
IDS = (202, 42, 78)
IDENTITIES = (
 ('bolton', '00307/26', 'https://paplanning.bolton.gov.uk/online-applications/applicationDetails.do?activeTab=summary&keyVal=TAPAO1DEGJP00'),
 ('oldham', 'FUL/355686/26', 'https://planningpa.oldham.gov.uk/online-applications/applicationDetails.do?activeTab=summary&keyVal=TA7382MCIP700'),
 ('stockport', 'DC/078942', 'https://planning.stockport.gov.uk/PlanningData-live/applicationDetails.do?keyVal=QKM8H1PJGJA00&activeTab=summary'),
)
MAX_AUDIT = 49152
WORKER_AUDIT = 16384
ACQUISITION_SECONDS = 140
MEMORY_BYTES = 512 * 1024 * 1024
UNKNOWN = 'UNKNOWN'
FIELDS = {'reference','status','decision','decision_date'}
FAILURES = {'SOURCE_UNAVAILABLE','REFERENCE_NOT_FOUND','AMBIGUOUS_SOURCE_RESULT',
 'PARTIAL_RETRIEVAL','PARSER_FAILURE','RATE_LIMITED','TIMEOUT','UNSUPPORTED_ROUTE',
 'SCOPE_ESCAPE','REDIRECT_VIOLATION','PRIVACY_FAILURE','ACCOUNTING_FAILURE','CLEANUP_FAILURE','INVALID_ARTIFACT'}

class AuditFence(ImportFence):
    prefixes = ImportFence.prefixes + ('app.pipeline.status_verification',)


def cohort():
    from .refresh import admitted_row
    rows = [admitted_row(i) for i in IDS]
    if any((r['council'],r['reference'],r['source_url']) != identity for r,identity in zip(rows,IDENTITIES)):
        raise ValueError('Frozen cohort differs')
    return rows


def admit(sha, mode, authority, env=None):
    env = os.environ if env is None else env
    if not re.fullmatch('[0-9a-f]{40}',sha): raise ValueError('Exact SHA required')
    actual = subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    dirty = subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],text=True).strip()
    if actual != sha or dirty: raise ValueError('Clean exact checkout required')
    if mode == 'offline':
        if authority != 'OFFLINE_ONLY': raise ValueError('Offline acknowledgement')
    elif mode == 'live':
        required = {'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted',
          'GITHUB_EVENT_NAME':'workflow_dispatch','DIRECT_WORKFLOW_SHA':sha,
          'GITHUB_RUN_ATTEMPT':'1','GITHUB_RUN_NUMBER':'1',
          'GITHUB_REPOSITORY':'maxrose26/PropertyAIgent'}
        if authority != AUTHORITY or any(env.get(k)!=v for k,v in required.items()):
            raise ValueError('Single-use live admission required')
        if not re.fullmatch(r'[1-9][0-9]*',env.get('GITHUB_RUN_ID','')):
            raise ValueError('Immutable run identity required')
        if not env.get('GITHUB_WORKFLOW_REF','').startswith('maxrose26/PropertyAIgent/'+WORKFLOW+'@'):
            raise ValueError('Exact registered workflow required')
    else: raise ValueError('Unknown mode')


def encode(value, limit=MAX_AUDIT):
    data=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if len(data)>limit: raise ValueError('Audit bound')
    return data


def empty_row(application_id, outcome='NOT_ATTEMPTED', *, identity=None):
    if identity is None:
        n=IDS.index(application_id);council,reference,url=IDENTITIES[n]
    else:
        if identity['application_id'] != application_id:raise ValueError('Identity')
        council,reference,url=(identity[k] for k in ('council','reference','source_url'))
    return dict(application_id=application_id,council=council,reference=reference,source_url=url,
      outcome=outcome,attempted=False if outcome=='NOT_ATTEMPTED' else UNKNOWN,
      requests=0 if outcome=='NOT_ATTEMPTED' else UNKNOWN,
      redirects=0 if outcome=='NOT_ATTEMPTED' else UNKNOWN,
      retries=0 if outcome=='NOT_ATTEMPTED' else UNKNOWN,
      received_body_bytes=0 if outcome=='NOT_ATTEMPTED' else UNKNOWN,
      elapsed_seconds=0 if outcome=='NOT_ATTEMPTED' else UNKNOWN,
      identity_qualification=UNKNOWN,field_states=None,literal_facts=None,
      normalized_facts=None,semantic_qualification=UNKNOWN,
      budget_state='NOT_STARTED' if outcome=='NOT_ATTEMPTED' else UNKNOWN,
      cleanup_state='NOT_STARTED' if outcome=='NOT_ATTEMPTED' else UNKNOWN)


class MeteredSession:
    """Exact destination wrapper; counters never include headers/cookies or errors."""
    def __init__(self, row, inner):
        self.row,self.inner=row,inner
        self.requests=0;self.redirects=0;self.bytes=0
        self.closed=False;self.responses=[];self.violation=None
    def get(self,url,**kwargs):
        from .refresh import fail
        if url!=self.row['source_url'] or kwargs.get('allow_redirects') is not False or self.requests>=2:
            self.violation='SCOPE_ESCAPE';fail(self.violation,'Frozen destination only')
        self.requests+=1
        response=self.inner.get(url,**kwargs)
        self.responses.append([response,False])
        if 300<=response.status_code<400:self.redirects+=1;self.violation='REDIRECT_VIOLATION'
        if response.url!=url or response.history:self.violation='SCOPE_ESCAPE'
        original_iter=response.iter_content;original_close=response.close
        tracked=self.responses[-1]
        def chunks(chunk_size):
            for chunk in original_iter(chunk_size):
                self.bytes+=len(chunk)
                yield chunk
        def close():
            try:original_close();tracked[1]=True
            except BaseException:self.violation='CLEANUP_FAILURE';raise
        response.iter_content=chunks;response.close=close
        return response
    def close(self):
        try:self.inner.close();self.closed=True
        except BaseException:self.violation='CLEANUP_FAILURE';raise


def observe(application_id, session_factory, *, identity=None, limits=None):
    from .refresh import retrieve, Budget
    from verification.stage26b_l1.request_boundary import BoundaryFailure
    row=cohort()[IDS.index(application_id)] if identity is None else identity
    from .refresh import admitted_row
    if row != admitted_row(application_id):raise ValueError('Unadmitted identity')
    audit=empty_row(application_id,identity=row)
    limits=limits or dict(requests=2,bytes=2_000_000,seconds=40)
    if set(limits)!={'requests','bytes','seconds'} or not 0<limits['requests']<=2 or not 0<limits['bytes']<=2_000_000 or not 0<limits['seconds']<=40:raise ValueError('Record limits')
    budget=Budget(request_limit=limits['requests'],byte_limit=limits['bytes'],seconds=limits['seconds'])
    meter=MeteredSession(row,session_factory())
    started=time.monotonic()
    bound_exhausted=False
    try:
        observation=retrieve(application_id,session_factory=lambda:meter,budget=budget)
        audit.update(outcome='LITERAL_VERIFIED',identity_qualification='EXACT_DISPLAYED_REFERENCE',
          field_states=observation.field_states,literal_facts=observation.literal_fields,
          normalized_facts=observation.fields,semantic_qualification=observation.semantic_state)
    except BoundaryFailure as error:
        audit['outcome']=error.outcome if error.outcome in FAILURES else 'PARSER_FAILURE'
        bound_exhausted=any(word in error.reason.lower() for word in ('ceiling','bound','deadline'))
        diagnostics=getattr(error,'diagnostics',None)
        if diagnostics:
            audit['field_states']={k:v['state'] for k,v in diagnostics['fields'].items()}
    except Exception:
        audit['outcome']='PARSER_FAILURE'
    finally:
        audit.update(attempted=meter.requests>0,requests=meter.requests,redirects=meter.redirects,
          retries=max(0,meter.requests-1),received_body_bytes=meter.bytes,
          elapsed_seconds=round(time.monotonic()-started,6),
          budget_state='WITHIN_LIMITS' if not budget.failed and not bound_exhausted and meter.bytes<=2_000_000 and time.monotonic()-started<40 else 'EXHAUSTED',
          cleanup_state='CLOSED' if meter.closed and all(x[1] for x in meter.responses) else 'FAILED')
    if meter.violation:audit['outcome']=meter.violation
    if meter.requests!=budget.requests or meter.bytes!=budget.bytes:
        audit['outcome']='ACCOUNTING_FAILURE'
    if audit['cleanup_state']!='CLOSED':audit['outcome']='CLEANUP_FAILURE'
    if audit['outcome']!='LITERAL_VERIFIED':
        audit.update(literal_facts=None,normalized_facts=None,semantic_qualification=UNKNOWN,identity_qualification=UNKNOWN)
    validate_row(audit,application_id,identity=row)
    return audit


def integer(value, maximum):
    if type(value) is not int or not 0<=value<=maximum:raise ValueError('Audit integer bound')


def validate_row(row, application_id, *, identity=None):
    expected=empty_row(application_id,identity=identity)
    if not isinstance(row,dict) or set(row)!=set(expected):raise ValueError('Closed audit schema')
    for k in ('application_id','council','reference','source_url'):
        if row[k]!=expected[k]:raise ValueError('Audit identity')
    if row['outcome'] not in FAILURES|{'LITERAL_VERIFIED','NOT_ATTEMPTED','INTERRUPTED'}:
        raise ValueError('Audit outcome')
    if row['outcome'] in ('NOT_ATTEMPTED','INTERRUPTED'):
        if row!=empty_row(application_id,row['outcome'],identity=identity):raise ValueError('Unknown/unattempted accounting')
        return
    for k,cap in [('requests',2),('redirects',2),('retries',1),('received_body_bytes',2_016_384)]:integer(row[k],cap)
    if row['attempted'] is not (row['requests']>0) or row['retries']!=max(0,row['requests']-1):raise ValueError('Request accounting')
    elapsed=row['elapsed_seconds']
    if type(elapsed) not in (int,float) or not math.isfinite(elapsed) or not 0<=elapsed<=46:raise ValueError('Elapsed bound')
    if row['cleanup_state'] not in ('CLOSED','FAILED') or row['budget_state'] not in ('WITHIN_LIMITS','EXHAUSTED'):raise ValueError('Completion state')
    states=row['field_states']
    if states is not None and (set(states)!=FIELDS or any(v not in {'PRESENT_VALUE','PRESENT_BLANK','NOT_PRESENT','CONFLICTING','UNPARSEABLE'} for v in states.values())):
        raise ValueError('Field states')
    if row['outcome']!='LITERAL_VERIFIED':
        if any(row[k] is not None for k in ('literal_facts','normalized_facts')) or row['semantic_qualification']!=UNKNOWN or row['identity_qualification']!=UNKNOWN:raise ValueError('Failure facts')
        return
    if (row['cleanup_state']!='CLOSED' or row['budget_state']!='WITHIN_LIMITS' or row['redirects']!=0
        or row['requests']<1 or not 0<row['received_body_bytes']<=2_000_000 or row['identity_qualification']!='EXACT_DISPLAYED_REFERENCE'):
        raise ValueError('False literal success')
    from verification.stage26b_l1.bolton_literal import FIELD_IDS, semantic_state
    fields=row['normalized_facts'];literal=row['literal_facts']
    if not isinstance(fields,dict) or set(fields)!=set(FIELD_IDS) or not isinstance(literal,dict) or set(literal)-set(FIELD_IDS):raise ValueError('Private fields')
    if fields['Reference']!=row['reference'] or literal.get('Reference')!=row['reference']:raise ValueError('Displayed identity')
    if states is None or states['reference']!='PRESENT_VALUE' or states['status']!='PRESENT_VALUE':raise ValueError('Required evidence')
    for key,name in FIELD_IDS.items():
        state=states[name];value=fields[key];raw=literal.get(key)
        if state not in {'PRESENT_VALUE','PRESENT_BLANK','NOT_PRESENT'}:raise ValueError('Conflicting facts')
        if (key in literal)!=(state!='NOT_PRESENT') or (value is not None)!=(state=='PRESENT_VALUE'):raise ValueError('Field absence')
        if state=='PRESENT_BLANK' and raw!='':raise ValueError('Blank value')
        if state=='NOT_PRESENT' and raw is not None:raise ValueError('Missing value')
        if value is not None:
            if not isinstance(raw,str) or not isinstance(value,str):raise ValueError('Literal type')
            if key in ('Status','Decision') and (raw!=value or not re.fullmatch(r'[A-Za-z0-9 ()/.,:;-]{1,256}',raw)):raise ValueError('Unsafe literal')
            if key=='Decision Issued Date':
                from app.pipeline.lapse_tracking import parse_portal_date
                if len(raw)>64 or not re.fullmatch(r'[A-Za-z0-9 /-]{1,64}',raw) or parse_portal_date(raw).isoformat()!=value:raise ValueError('Date literal')
    semantic='UNKNOWN_UNMAPPED' if states['decision']=='NOT_PRESENT' else semantic_state(fields)
    if row['semantic_qualification']!=semantic:raise ValueError('Semantic mismatch')
    encode(row,WORKER_AUDIT)


def worker(application_id, mode, output):
    if application_id not in IDS:raise ValueError('Frozen cohort only')
    resource.setrlimit(resource.RLIMIT_AS,(MEMORY_BYTES,MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU,(30,30))
    fence=AuditFence();sys.meta_path.insert(0,fence)
    try:
        if mode=='offline':
            from .fixtures import Session,summary
            row=cohort()[IDS.index(application_id)]
            body=summary(row['reference'],status='Deposited',omit=('Decision','Decision Issued Date')) if application_id==202 else summary(row['reference'],status='Decided',decision='Granted',date='Wed 27 Dec 2023')
            with offline_network_denial():result=observe(application_id,lambda:Session(body))
        else:
            from .refresh import requests_session
            result=observe(application_id,requests_session)
        with output.open('xb') as target:target.write(encode(result,WORKER_AUDIT))
        return 0 if result['outcome']=='LITERAL_VERIFIED' else 1
    finally:sys.meta_path.remove(fence)


def aggregate(sha,mode,results,run_id=None):
    stopped=False
    for application_id,row in zip(IDS,results):
        validate_row(row,application_id)
        if stopped and row['outcome']!='NOT_ATTEMPTED':raise ValueError('Continued after stop')
        if row['outcome']!='LITERAL_VERIFIED':stopped=True
    if len(results)!=3:raise ValueError('Three records required')
    totals={k:(UNKNOWN if any(r[k]==UNKNOWN for r in results) else sum(r[k] for r in results))
      for k in ('requests','redirects','retries','received_body_bytes')}
    if totals['requests']!=UNKNOWN and totals['requests']>6:raise ValueError('Total requests')
    complete=all(r['outcome']=='LITERAL_VERIFIED' for r in results)
    if complete and totals['received_body_bytes']>6_000_000:raise ValueError('Total bytes')
    return dict(version='stage4-direct-three-once-v1',repository_sha=sha,mode=mode,run_id=run_id,
      persistence=False,assessment='COMPLETE' if complete else 'STOPPED_REVIEW_REQUIRED',
      accounting_complete=all(r['requests']!=UNKNOWN for r in results),totals=totals,results=results)


def execute(sha,mode,authority,output,job_start_epoch=None):
    admit(sha,mode,authority)
    if output.exists():raise ValueError('Refusing existing audit')
    started=time.monotonic();deadline=ACQUISITION_SECONDS
    if mode=='live':
        if job_start_epoch is None:raise ValueError('Outer budget required')
        age=time.time()-job_start_epoch
        # Keep 20s for cleanup/upload; never start a worker without its full allowance.
        if not 0<=age<115:raise ValueError('Setup left insufficient job budget')
        deadline=min(deadline,180-age-20)
    results=[empty_row(i) for i in IDS]
    for index,application_id in enumerate(IDS):
        remaining=deadline-(time.monotonic()-started)
        if remaining<45:
            # No worker was launched; known zero attempts for this and later cases.
            break
        with tempfile.TemporaryDirectory(prefix='direct-audit-') as directory:
            audit=Path(directory)/'worker.json'
            env=dict(PATH='/usr/bin:/bin',HOME=directory,TMPDIR=directory,LANG='C.UTF-8',
              PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
            if mode=='live':
                for key in ('GITHUB_ACTIONS','RUNNER_ENVIRONMENT','GITHUB_EVENT_NAME','DIRECT_WORKFLOW_SHA','GITHUB_RUN_ATTEMPT','GITHUB_RUN_NUMBER','GITHUB_REPOSITORY','GITHUB_RUN_ID','GITHUB_WORKFLOW_REF'):
                    env[key]=os.environ[key]
            command=[sys.executable,'-m','verification.direct_reference.registration','--sha',sha,'--mode',mode,
              '--authority',authority,'--output',str(audit),'--worker-id',str(application_id)]
            try:
                status,expired=supervise(command,env=env,deadline=45)
                if expired or status not in (0,1) or not audit.is_file() or audit.stat().st_size>WORKER_AUDIT:
                    raise ValueError('No complete worker audit')
                result=json.loads(audit.read_bytes());validate_row(result,application_id)
                if (status==0)!=(result['outcome']=='LITERAL_VERIFIED'):raise ValueError('Worker result mismatch')
                results[index]=result
            except Exception:
                results[index]=empty_row(application_id,'INTERRUPTED')
            if results[index]['outcome']!='LITERAL_VERIFIED':break
    artifact=aggregate(sha,mode,results,os.environ.get('GITHUB_RUN_ID') if mode=='live' else None)
    with output.open('xb') as target:target.write(encode(artifact))
    return 0 if artifact['assessment']=='COMPLETE' else 1


def main():
    p=argparse.ArgumentParser();p.add_argument('--sha',required=True);p.add_argument('--mode',choices=['offline','live'],default='offline')
    p.add_argument('--authority',default='OFFLINE_ONLY');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--job-start-epoch',type=float);p.add_argument('--worker-id',type=int,choices=IDS)
    a=p.parse_args()
    try:
        if a.worker_id is not None:
            admit(a.sha,a.mode,a.authority);return worker(a.worker_id,a.mode,a.output)
        return execute(a.sha,a.mode,a.authority,a.output,a.job_start_epoch)
    except Exception:
        print('Registration admission or audit failed; no complete evidence',file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
