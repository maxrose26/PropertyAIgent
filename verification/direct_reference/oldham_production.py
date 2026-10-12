"""One Oldham B2 transaction. Registration is not execution authority.

No migrations, no second writer, no retry after uncertain commit. All external
activity is confined to the separately admitted worker. Test injection is only
available in the Python API, never the production CLI.
"""
import argparse
import contextlib
import datetime as dt
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import resource
import subprocess
import sys
import tempfile
import time

APP_ID=42
REFERENCE='FUL/355686/26'
URL='https://planningpa.oldham.gov.uk/online-applications/applicationDetails.do?activeTab=summary&keyVal=TA7382MCIP700'
AUTHORITY='AUTHORISE_STAGE4_OLDHAM42_B2_PERSISTENCE_ONCE'
WORKFLOW='.github/workflows/stage4-oldham-production-once.yml'
MAX_AUDIT=16384
UNKNOWN='UNKNOWN'
COUPLED=('status','decision','decision_issued_date','status_verified_at','evidence_refresh_required',
 'evidence_refresh_reason','evidence_refresh_trigger','evidence_refresh_requested_at')
EVENT_FIELDS=('id','event_type','field_name','old_value','new_value','authoritative_source')
EVENT_TYPES={'status_changed','decision_granted','decision_refused','decision_withdrawn'}
WRITE_FIELDS=set(COUPLED)


def utc():return dt.datetime.now(dt.timezone.utc).isoformat()

def encode(a):
    b=json.dumps(a,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if len(b)>MAX_AUDIT:raise ValueError('AUDIT_BOUND')
    return b


def safe_text(v):
    if v is not None and (not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9 _()/.,:;+\-]{1,256}',v)):
        raise ValueError('UNSAFE_FACT')


def validate_snapshot(s):
    if set(s)!={'facts','events'} or set(s['facts'])!=set(COUPLED):raise ValueError('SNAPSHOT_SCHEMA')
    for k,v in s['facts'].items():
        if k=='evidence_refresh_required':
            if type(v) is not bool:raise ValueError('SIGNAL_UNKNOWN')
        elif k.endswith('_at'):
            if v is not None:dt.datetime.fromisoformat(v)
        else:safe_text(v)
    if not isinstance(s['events'],list) or len(s['events'])>16:raise ValueError('EVENT_BOUND')
    for e in s['events']:
        if set(e)!=set(EVENT_FIELDS) or type(e['id']) is not int:raise ValueError('EVENT_SCHEMA')
        for k,v in e.items():
            if k!='id':safe_text(v)


def empty(sha,run):
    return dict(schema=1,repository_sha=sha,run_id=run,application_id=APP_ID,reference=REFERENCE,
      source_url=URL,source_provenance='FRESH_OFFICIAL_SUMMARY',retrieval_started_at=None,
      retrieval_completed_at=None,source=None,before=None,expected=None,after=None,
      b2_outcome=UNKNOWN,materiality=UNKNOWN,transaction=UNKNOWN,error=None,
      cleanup=UNKNOWN)


def validate(a):
    if set(a)!=set(empty(a.get('repository_sha'),a.get('run_id'))):raise ValueError('AUDIT_SCHEMA')
    if a['application_id']!=APP_ID or a['reference']!=REFERENCE or a['source_url']!=URL:raise ValueError('AUDIT_IDENTITY')
    if not re.fullmatch('[0-9a-f]{40}',a['repository_sha']) or not re.fullmatch('[1-9][0-9]*',a['run_id']):raise ValueError('AUDIT_RUN')
    if a['source_provenance']!='FRESH_OFFICIAL_SUMMARY':raise ValueError('PROVENANCE')
    for k in ('before','expected','after'):
        if a[k] is not None:validate_snapshot(a[k])
    if a['source'] is not None:
        from .registration import validate_row
        validate_row(a['source'],APP_ID)
    for k in ('retrieval_started_at','retrieval_completed_at'):
        if a[k] is not None:dt.datetime.fromisoformat(a[k])
    if a['transaction'] not in {'COMMITTED','NOT_COMMITTED',UNKNOWN}:raise ValueError('TRANSACTION')
    if a['materiality'] not in {'MATERIAL','NON_MATERIAL','UNCHANGED',UNKNOWN}:raise ValueError('MATERIALITY')
    if a['b2_outcome'] not in {UNKNOWN,'VERIFIED_MATERIAL_CHANGE','VERIFIED_NON_MATERIAL_CHANGE','VERIFIED_UNCHANGED','PARTIAL_RETRIEVAL','STALE_RESPONSE','PERSISTENCE_FAILED','PARSER_FAILURE','AMBIGUOUS_SOURCE_RESULT','SOURCE_UNAVAILABLE','TIMEOUT','RATE_LIMITED'}:raise ValueError('OUTCOME')
    if a['error'] not in {None,'ADMISSION','SOURCE_REJECTED','AUDIT_REJECTED','DB_REJECTED','READBACK_MISMATCH','COMMIT_ACK_UNKNOWN','INTERRUPTED','CLEANUP_FAILED'}:raise ValueError('ERROR')
    if a['cleanup'] not in {'CLOSED',UNKNOWN,'FAILED'}:raise ValueError('CLEANUP')
    if a['transaction']=='COMMITTED' and (a['expected'] is None or a['after']!=a['expected']):raise ValueError('UNPROVED_COMMIT')
    encode(a)


def admit(sha,authority,env=None):
    e=os.environ if env is None else env
    if authority!=AUTHORITY or not re.fullmatch('[0-9a-f]{40}',sha):raise ValueError('ADMISSION')
    required={'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','GITHUB_EVENT_NAME':'workflow_dispatch',
      'OLDHAM_WORKFLOW_SHA':sha,'GITHUB_RUN_NUMBER':'1','GITHUB_RUN_ATTEMPT':'1','GITHUB_REPOSITORY':'maxrose26/PropertyAIgent'}
    if any(e.get(k)!=v for k,v in required.items()) or not re.fullmatch('[1-9][0-9]*',e.get('GITHUB_RUN_ID','')):raise ValueError('ADMISSION')
    if e.get('GITHUB_WORKFLOW_REF')!='maxrose26/PropertyAIgent/'+WORKFLOW+'@refs/heads/master':raise ValueError('WORKFLOW_REF')
    if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=sha:raise ValueError('HEAD')
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],text=True).strip():raise ValueError('DIRTY')


def council():
    from app.config import CouncilConfig
    return CouncilConfig(code='oldham',name='Oldham',base_url='https://planningpa.oldham.gov.uk/online-applications',
      date_field_mode='received',doc_system='idox',anite_base_url=None,unit_threshold=10,region='GM',country='England')


def snapshot(session):
    from sqlalchemy import select
    from app.db.models import Application,ApplicationLifecycleEvent as E
    row=session.execute(select(*(getattr(Application,k) for k in COUPLED)).where(
      Application.id==APP_ID,Application.reference==REFERENCE,Application.council_code=='oldham').limit(1)).one()
    facts={k:(v.isoformat() if isinstance(v,dt.datetime) else v) for k,v in zip(COUPLED,row)}
    events=[dict(zip(EVENT_FIELDS,r)) for r in session.execute(select(*(getattr(E,k) for k in EVENT_FIELDS)).where(E.application_id==APP_ID).order_by(E.id).limit(17))]
    out=dict(facts=facts,events=events);validate_snapshot(out);return out


def check_consequences(before,after):
    from app.pipeline.material_change import ApplicationState,detect_material_application_change
    from app.pipeline.lifecycle_events import _REASON_TO_EVENT_TYPE
    from app.pipeline.lapse_tracking import parse_portal_date
    b=before['facts'];a=after['facts']
    changed=detect_material_application_change(ApplicationState(b['status'],b['decision'],None),ApplicationState(a['status'],a['decision'],None))
    field='decision' if a['decision']!=b['decision'] else 'status'
    expected=[(_REASON_TO_EVENT_TYPE.get(r,'status_changed'),field,b[field],a[field]) for r in changed.reasons]
    reasons=list(changed.reasons)
    if a['decision']==b['decision'] and parse_portal_date(a['decision_issued_date'])!=dt.date.min and parse_portal_date(a['decision_issued_date'])!=parse_portal_date(b['decision_issued_date']):
        expected.append(('status_changed','decision_issued_date',b['decision_issued_date'],a['decision_issued_date']));reasons.append('decision_date_corrected')
    new=after['events'][len(before['events']):]
    if [(e['event_type'],e['field_name'],e['old_value'],e['new_value']) for e in new]!=expected:raise ValueError('EVENT_CONSEQUENCE')
    if reasons:
        if not a['evidence_refresh_required'] or a['evidence_refresh_reason']!=','.join(reasons) or a['evidence_refresh_trigger']!='material_change' or a['evidence_refresh_requested_at'] is None:raise ValueError('REFRESH_CONSEQUENCE')
    elif any(a[k]!=b[k] for k in COUPLED if k.startswith('evidence_refresh')):raise ValueError('UNEXPECTED_REFRESH')


def install_guards(engine):
    """Deny DDL/text/bulk writes. Actual B2 call stack and bound row ID required."""
    from sqlalchemy import event
    from sqlalchemy.sql.dml import Insert,Update
    from sqlalchemy.sql.selectable import Select
    def guard(conn,clause,multi,params,options):
        if isinstance(clause,Select):return
        if not isinstance(clause,(Insert,Update)):raise ValueError('SQL_DENIED')
        if not any(f.function=='verify_application_status' and f.filename.endswith('/app/pipeline/status_verification.py') for f in inspect.stack()):raise ValueError('B2_ONLY')
        if len(multi)>1:raise ValueError('BULK_DENIED')
        bound=dict(clause.compile().params);bound.update(params or (multi[0] if multi else {}))
        if isinstance(clause,Update):
            if clause.table.name!='applications':raise ValueError('TABLE_DENIED')
            assignments={getattr(k,'key',str(k)) for k in (clause._values or {})} or (set(params or (multi[0] if multi else {}))-{'applications_id'})
            if not assignments<=WRITE_FIELDS:raise ValueError('COLUMN_DENIED')
            # B2 CAS binds id_1; ORM flush binds applications_id. Neither is caller input.
            if bound.get('id_1',bound.get('applications_id'))!=APP_ID:raise ValueError('ROW_DENIED')
        else:
            if clause.table.name!='application_lifecycle_events' or bound.get('application_id')!=APP_ID or bound.get('authoritative_source')!='status_verification':raise ValueError('EVENT_DENIED')
    event.listen(engine,'before_execute',guard)
    return guard


def session_type():
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    from app.db.models import Application,ApplicationLifecycleEvent as E
    class BoundedSession(Session):pass
    @event.listens_for(BoundedSession,'do_orm_execute')
    def scope(state):
        if not state.is_select:return
        stmt=state.statement
        tables={getattr(t,'name',None) for t in stmt.get_final_froms()}
        if tables=={'applications'}:state.statement=stmt.where(Application.id==APP_ID).limit(2)
        elif tables=={'application_lifecycle_events'}:state.statement=stmt.where(E.application_id==APP_ID).limit(17)
        else:raise ValueError('READ_SCOPE')
    @event.listens_for(BoundedSession,'before_flush')
    def flush(s,*args):
        from sqlalchemy import inspect as sa_inspect
        if s.deleted:raise ValueError('DELETE_DENIED')
        for obj in s.new:
            if not isinstance(obj,E) or obj.application_id!=APP_ID or obj.authoritative_source!='status_verification':raise ValueError('INSERT_DENIED')
        for obj in s.dirty:
            if not isinstance(obj,Application) or obj.id!=APP_ID:raise ValueError('UPDATE_DENIED')
            if {a.key for a in sa_inspect(obj).attrs if a.history.has_changes()}-WRITE_FIELDS:raise ValueError('COLUMN_DENIED')
    return BoundedSession


def run_transaction(engine,sha,run_id,source_factory):
    """Only production caller passes requests_session; no frozen evidence import."""
    from sqlalchemy import event,select
    from app.db.models import Application
    from .refresh import Observation,refresh
    from .registration import observe
    from verification.stage26b_l1.request_boundary import BoundaryFailure
    S=session_type();audit=empty(sha,run_id);guard=install_guards(engine)
    try:
        with S(engine,expire_on_commit=False) as s:
            app=s.execute(select(Application).where(Application.id==APP_ID,Application.reference==REFERENCE,Application.council_code=='oldham').limit(1)).scalar_one()
            audit['before']=snapshot(s)
            def loader():
                audit['retrieval_started_at']=utc()
                row=observe(APP_ID,source_factory)
                audit['retrieval_completed_at']=utc();audit['source']=row
                validate(audit)  # privacy/accounting BEFORE B2 can reserve its watermark
                if row['outcome']!='LITERAL_VERIFIED':raise BoundaryFailure('PARTIAL_RETRIEVAL','Source rejected')
                eligible=all(v in {'PRESENT_VALUE','PRESENT_BLANK'} for v in row['field_states'].values()) and row['semantic_qualification']!='UNKNOWN_UNMAPPED'
                return Observation(APP_ID,REFERENCE,URL,row['normalized_facts'],row['field_states'],row['semantic_qualification'],None,row['literal_facts'],b2_eligible=eligible)
            def before_commit(session):
                session.flush()
                audit['expected']=snapshot(session)
                before=audit['before'];expected=audit['expected']
                if expected['events'][:len(before['events'])]!=before['events']:raise ValueError('EVENT_MUTATION')
                new=expected['events'][len(before['events']):]
                if len(new)>2 or any(e['event_type'] not in EVENT_TYPES or e['authoritative_source']!='status_verification' for e in new):raise ValueError('UNEXPECTED_EVENT')
                if expected['facts']['status_verified_at'] is None:raise ValueError('WATERMARK')
                check_consequences(before,expected)
                validate(audit) # any failure raises inside B2 and rolls back
            event.listen(s,'before_commit',before_commit)
            result=refresh(s,app,council(),retrieve_evidence=loader)
            audit['b2_outcome']=result['outcome']
        try:
            with S(engine) as reader:audit['after']=snapshot(reader)
            if audit['expected'] is not None and audit['after']==audit['expected']:
                audit['transaction']='COMMITTED'
            elif audit['after']==audit['before']:audit['transaction']='NOT_COMMITTED'
            else:audit['error']='READBACK_MISMATCH'
        except Exception:audit['error']='COMMIT_ACK_UNKNOWN'
        if audit['transaction']=='COMMITTED':
            b=audit['before'];a=audit['after']
            audit['materiality']='MATERIAL' if a['events']!=b['events'] else ('UNCHANGED' if all(a['facts'][k]==b['facts'][k] for k in ('status','decision','decision_issued_date')) else 'NON_MATERIAL')
        if result['accepted'] and audit['transaction']!='COMMITTED':audit['error']='READBACK_MISMATCH'
        if not result['accepted'] and audit['transaction']=='NOT_COMMITTED':audit['error']='SOURCE_REJECTED' if audit['expected'] is None else 'DB_REJECTED'
    except Exception:
        audit['error']='DB_REJECTED'
        # A caught exception is not evidence that a commit did not occur.
    finally:
        event.remove(engine,'before_execute',guard)
    validate(audit);return audit


def production_engine():
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    from app.db.session import _normalize_database_url
    raw=os.environ.pop('OLDHAM_DATABASE_URL','')
    if not raw:raise ValueError('CREDENTIAL_MISSING')
    u=make_url(_normalize_database_url(raw))
    if u.drivername!='postgresql+psycopg' or not u.host or not u.password or u.database!='postgres' or u.query:raise ValueError('DB_ROUTE')
    # Only the existing Supabase app route; no SQLite/local/alternate service fallback.
    if not (re.fullmatch(r'db\.[a-z0-9]{20}\.supabase\.co',u.host) or re.fullmatch(r'aws-[0-9]+-[a-z0-9-]+\.pooler\.supabase\.com',u.host)):raise ValueError('DB_ROUTE')
    return create_engine(u,pool_size=1,max_overflow=0,pool_pre_ping=False,hide_parameters=True,
      connect_args={'connect_timeout':5,'sslmode':'require','options':'-c statement_timeout=10000 -c lock_timeout=8000 -c idle_in_transaction_session_timeout=40000', 'application_name':'stage4_oldham42_once'})


def worker(sha,run_id,path):
    resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU,(30,30))
    a=empty(sha,run_id);engine=None
    with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
        try:
            engine=production_engine()
            from .refresh import requests_session
            a=run_transaction(engine,sha,run_id,requests_session)
        except Exception:a['error']='ADMISSION'
        finally:
            try:
                if engine is not None:
                    if engine.pool.checkedout():raise ValueError('CONNECTION_LEAK')
                    engine.dispose()
                a['cleanup']='CLOSED'
            except Exception:a['cleanup']='FAILED';a['error']='CLEANUP_FAILED'
    validate(a);Path(path).write_bytes(encode(a))
    return 0 if a['transaction']=='COMMITTED' and a['error'] is None and a['cleanup']=='CLOSED' else 1


def main():
    p=argparse.ArgumentParser();p.add_argument('--sha',required=True);p.add_argument('--authority',required=True)
    p.add_argument('--output',required=True);p.add_argument('--worker',action='store_true');p.add_argument('--job-start',type=float,required=True)
    args=p.parse_args()
    try:
        admit(args.sha,args.authority)
        if args.worker:return worker(args.sha,os.environ['GITHUB_RUN_ID'],args.output)
        from verification.stage26b_l1.actions_runner import supervise
        if Path(args.output).exists():raise ValueError('OUTPUT_EXISTS')
        deadline=min(45,180-(time.time()-args.job_start)-20)
        if deadline<=0:raise ValueError('JOB_DEADLINE')
        with tempfile.TemporaryDirectory() as home:
            env={k:v for k,v in os.environ.items() if k.startswith('GITHUB_') and k in {'GITHUB_ACTIONS','GITHUB_EVENT_NAME','GITHUB_RUN_NUMBER','GITHUB_RUN_ATTEMPT','GITHUB_REPOSITORY','GITHUB_RUN_ID','GITHUB_WORKFLOW_REF'}}
            env.update(PATH='/usr/bin:/bin',HOME=home,PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',RUNNER_ENVIRONMENT='github-hosted',OLDHAM_WORKFLOW_SHA=args.sha,OLDHAM_DATABASE_URL=os.environ.pop('OLDHAM_DATABASE_URL',''))
            out=Path(home)/'audit.json'
            cmd=[sys.executable,'-m','verification.direct_reference.oldham_production','--worker','--sha',args.sha,'--authority',args.authority,'--output',str(out),'--job-start',str(args.job_start)]
            status,timeout=supervise(cmd,env=env,deadline=deadline)
            if timeout or not out.exists() or out.stat().st_size>MAX_AUDIT:
                a=empty(args.sha,os.environ['GITHUB_RUN_ID']);a['error']='INTERRUPTED'
            else:
                try:a=json.loads(out.read_bytes());validate(a)
                except Exception:a=empty(args.sha,os.environ['GITHUB_RUN_ID']);a['error']='AUDIT_REJECTED'
            Path(args.output).write_bytes(encode(a))
        return 0 if status==0 and not timeout else 1
    except Exception:
        print('Oldham canary admission failed; no diagnostic details exported',file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
