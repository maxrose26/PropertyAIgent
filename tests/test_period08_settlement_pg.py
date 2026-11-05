"""Actual runtime creates Tameside's 24 results before synthetic Manchester failure.
Only source transport and immutable production identity constants are fixtures.
"""
import copy,json,time,hashlib
from datetime import date,datetime,timezone
from types import SimpleNamespace
import pytest
from tests.test_attempt06_owner_path_pg import world,act,Fault
from tests.test_period07_settlement_pg import failed07
from tests.test_period08_successor_pg import settled08
from tests.e2e_connection_support import idox_supervised,arcus_audit,arcus_slot_supervised
from verification.ingestion_storage import period08_settlement as s,period08_successor as p08,intake_owner as op,intake_owner_operations as extra,attempt06_recovery as a06
from verification.ingestion_storage.daily_intake_runtime import Runtime

@pytest.fixture
def failed08(settled08,tmp_path,monkeypatch):
 w=settled08;c=w['boot'];b=w['binding'];act(w,p08.dispose)
 from verification.ingestion_storage.owner_pilot_continuation import migrate_owner_namespace
 with w['actor']() as actor:migrate_owner_namespace(actor,attempt08=True,binding08=b,stable_verifiers=b['credential_verifier_sha256'])
 with w['actor']() as actor:extra.issue_period(actor,b,w['policy'],dict(version='FINITE_INTAKE_PERIOD_V1',state='ARMED_NO_RETRY',binding=b,policy=w['policy']),lambda _:None)
 passwords={r:__import__('sqlalchemy').engine.make_url(w['urls'][r]).password for r in op.ROLES};states=[]
 with w['actor']() as actor:
  prepared=op.prepare_activation(actor,b,stable_credentials=passwords);op.activate(actor,b,lambda v:states.append(copy.deepcopy(v)),prepared=prepared)
 for role,var in [('ingestion_worker_login','INGESTION_WORKER_DATABASE_URL'),('ingestion_effect_login','INGESTION_EFFECT_DATABASE_URL')]:monkeypatch.setenv(var,w['urls'][role])
 monkeypatch.delenv('DATABASE_URL',raising=False)
 runtime=Runtime(SimpleNamespace(period=p08.SUCCESSOR,output=str(tmp_path/'run'),hostaddr=b['hostaddr'],disposable_sources=None,disposable_archive=None));runtime.route_name=b['route']
 monkeypatch.setattr('verification.ingestion_storage.daily_intake_runtime.require_source_context',lambda *a,**kw:None)
 def source(row):
  runtime.run.begin_source();start,end=date.fromisoformat(row['start']),date.fromisoformat(row['end']);folder=tmp_path/row['council'];folder.mkdir()
  if row['council']=='tameside':
   from tests.test_tameside_pagination_calibration import FORM,SEARCH,ECHO,body,Response
   from verification.discovery.pagination_calibration import run_counted_window,COUNTED_MODE
   from verification.discovery.four_council_proof import manifest_scope
   from verification.discovery.source_profiles import profile,bind_audit
   from verification.discovery.idox_window import WindowConfig
   bodies=[FORM,SEARCH,*[body(n,count=5 if n<5 else 4,nxt=n<5,previous=n>1,total=24) for n in range(1,6)],ECHO]
   bodies=iter(v.replace(b'24/10/2026',b'27/10/2026').replace(b'30/10/2026',b'02/11/2026') for v in bodies)
   with manifest_scope(row,profile(row,'SCREENING_METADATA',idox_pagination=COUNTED_MODE)):
    audit=run_counted_window(lambda *a,**k:Response(next(bodies)),WindowConfig('tameside','RECEIVED',start,end,0,60))
   audit=bind_audit(profile(row,'SCREENING_METADATA',idox_pagination=COUNTED_MODE),audit)
   assert audit['failure'] is None and len(audit['records'])==24
   audit,outer=idox_supervised(folder,audit);r=audit['resource'];metrics=dict(requests=r['requests_attempted'],source_bytes=r['received_bytes'],source_seconds=r['elapsed_seconds'])
  else:
   audit=arcus_audit('manchester',[],start,end,budget='BROWSER_SOURCE_V2');audit.update(requests=1,responses=0,failure='BROWSER_Error',safety_failure=True,safety_events=['BROWSER_Error'])
   audit,outer,_=arcus_slot_supervised(folder,audit,runtime.contract(row).scope());metrics=dict(requests=1,source_bytes=audit['decoded_bytes']+audit['encoded_bytes']+audit['outbound_payload_bytes'],source_seconds=audit['supervisor_seconds'])
  runtime.run.source(dict(metrics,supervised_seconds=outer['elapsed_seconds']));return audit,dict(outer,observed_at=datetime.now(timezone.utc).isoformat())
 runtime.collect=source;result=runtime.execute()
 assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['reason']=='SOURCE_SAFETY',result
 with w['actor']() as actor:op.close(actor,states[-1],lambda _:None)
 ctl=op.control(c);period=ctl['intake_periods'][s.PERIOD];keys=period['days']['2026-11-02']
 for name,value in [('RUN',ctl['intake_run']['id']),('KEY',keys['manchester']),('TAMESIDE',keys['tameside']),('BINDING',b['execution_binding']),('MARKER_SHA',a06.sha(ctl['intake_run']))]:monkeypatch.setattr(s,name,value)
 monkeypatch.setattr(s,'AUTHORITY',c.execute('SELECT authority FROM ingestion_work_items WHERE key=%s',(s.KEY,)).fetchone()[0])
 c.execute('UPDATE ingestion_work_items SET lease_until=%s WHERE key=%s',(time.time()-60,s.KEY))
 monkeypatch.setattr(s,'EVIDENCE',dict(c.execute('SELECT name,sha256 FROM ingestion_run_evidence WHERE period=%s AND run_id=%s',(s.PERIOD,s.RUN)).fetchall()))
 w['history_before']=copy.deepcopy(ctl['intake_periods']);w['protected']=s.protected_sha(c);w['members']=c.execute(op.MEMBERS).fetchall()
 w['evidence_before']=c.execute('SELECT period,run_id,name,body,sha256 FROM ingestion_run_evidence ORDER BY period,run_id,name').fetchall()
 s.tameside(c);assert op.stop_snapshot(ctl)==s.STOP10
 return w

def backlog(w):
 from app.ingestion.daily_intake import backlog_page
 from app.ingestion.sql_ledger import SQLLedger
 from app.ingestion.listing_screening import ScreeningRule,RULE_V3
 from sqlalchemy import text
 ledger=SQLLedger(w['app'],owner='test',authority='',bindings={});records=[];cursor=None
 with w['app'].connect() as connection:
  connection.execute(text('BEGIN READ ONLY'))
  try:
   for _ in range(10):
    page=backlog_page(ledger,['tameside'],['tameside-screening-metadata-five-v1'],ScreeningRule(RULE_V3,unit_threshold=10,link_related=False),after=cursor,connection=connection)
    records.extend(r for r in page['records'] if r['capture_key']==s.TAMESIDE)
    if not page['more']:break
    cursor=page['next_cursor']
   else:raise AssertionError('BACKLOG_BOUND')
  finally:connection.rollback()
 assert len(records)==24 and all(r['screening_state']=='COMPLETE' and r['screening_matches_current_rule'] for r in records)
 return records

@pytest.mark.parametrize('mode',['normal','before','lost','after_recover','before_cleanup'])
def test_settlement_preserves_completed_tameside(failed08,mode):
 w=failed08;c=w['boot'];before=op.ledger_sha(c);retained=backlog(w)
 with w['actor']() as actor:assert s.inspect(actor,w['binding'])['status']=='READY_FOR_REVIEW_NOT_AUTHORISED'
 class Break(Fault):
  def execute(self,q,p=None):
   if mode=='before_cleanup' and q=='RESET ROLE':raise RuntimeError('BEFORE_CLEANUP')
   r=super().execute(q,p)
   if mode=='after_recover' and q.startswith('SELECT public.ingestion_recover_abandoned'):raise RuntimeError('AFTER_RECOVER')
   return r
 with w['actor']() as actor:
  if mode=='normal':s.recover(actor,w['binding'])
  else:
   with pytest.raises(RuntimeError):s.recover(Break(actor,mode),w['binding'])
 assert s.protected_sha(c)==w['protected'];s.tameside(c);assert backlog(w)==retained
 assert c.execute(op.MEMBERS).fetchall()==w['members']
 assert c.execute('SELECT period,run_id,name,body,sha256 FROM ingestion_run_evidence ORDER BY period,run_id,name').fetchall()==w['evidence_before']
 ctl=op.control(c)
 for period in w['history_before']:
  if period!=s.PERIOD:assert ctl['intake_periods'][period]==w['history_before'][period]
 if mode in ('normal','lost'):
  with w['actor']() as actor:assert s.inspect(actor,w['binding'])['status']=='COMMITTED_STATE_VERIFIED_READ_ONLY'
  assert op.stop_snapshot(ctl)==s.STOP11 and 'intake_run' not in ctl
  snapshot=op.ledger_sha(c)
  with w['actor']() as actor:
   with pytest.raises(op.Denied):s.recover(actor,w['binding'])
  assert op.ledger_sha(c)==snapshot
 else:assert op.ledger_sha(c)==before

@pytest.mark.parametrize('drift',['marker','stop','fence','checkpoint','lease','tameside','screen','batch','evidence','prior'])
def test_changed_state_refuses_atomically(failed08,drift):
 w=failed08;c=w['boot'];ctl=op.control(c)
 if drift=='marker':ctl['intake_run']['id']='0'*32
 elif drift=='stop':ctl['manual_stop']='UNRELATED'
 elif drift=='prior':ctl['intake_periods'][p08.p07.PERIOD]['failed_runs'][p08.p07.RUN]['actual_requests']=999
 elif drift in ('fence','checkpoint','lease'):
  field,value={'fence':('fence',2),'checkpoint':('checkpoint','{}'),'lease':('lease_until',time.time()+60)}[drift]
  from psycopg import sql
  c.execute(sql.SQL('UPDATE ingestion_work_items SET {}=%s WHERE key=%s').format(sql.Identifier(field)),(value,s.KEY))
 elif drift=='tameside':c.execute("UPDATE ingestion_work_items SET state='CLAIMED' WHERE key=%s",(s.TAMESIDE,))
 elif drift in ('screen','batch'):c.execute("UPDATE ingestion_work_items SET state='CLAIMED' WHERE key=(SELECT key FROM ingestion_work_items WHERE task=%s AND state='COMPLETE' LIMIT 1)",('SCREENING' if drift=='screen' else 'LISTING_METADATA',))
 elif drift=='evidence':c.execute("UPDATE ingestion_run_evidence SET body='bad'::bytea WHERE period=%s AND name='capture-2/source.json'",(s.PERIOD,))
 c.execute('UPDATE ingestion_work_items SET outcome=%s::json WHERE key=%s',(json.dumps(ctl),op.CONTROL));before=op.ledger_sha(c)
 with w['actor']() as actor:
  with pytest.raises(Exception):s.recover(actor,w['binding'])
 assert op.ledger_sha(c)==before and c.execute(op.MEMBERS).fetchall()==w['members']
