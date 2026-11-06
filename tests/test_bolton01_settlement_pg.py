"""Actual failed Bolton runtime and owner settlement against disposable PG17."""
import copy,json,time,hashlib
from contextlib import contextmanager
import pytest
from tests.test_intake_scope_pg import succeeded10,ready10,ready09,failed09,failed08,settled08,failed07,world,Fault
from tests.test_period08_settlement_pg import backlog
from verification.ingestion_storage import bolton01_settlement as s,period08_settlement as prior,intake_owner as op,attempt06_recovery as a06

@pytest.fixture
def failed_bolton(succeeded10,tmp_path,monkeypatch):
 from tests import test_intake_scope_pg as source
 w=succeeded10;c=w['boot'];original=source.idox_audit
 monkeypatch.delenv('BOLTON_WORKER_AUDIT',raising=False)
 monkeypatch.setattr(source,'idox_audit',lambda council,entries,start,end:original(council,entries[:7],start,end,single_page_no_pager=True))
 source.test_actual_bolton_entry_capture_screen_backlog_close(w,tmp_path,monkeypatch,True,authenticate=True)
 ctl=op.control(c);key=ctl['intake_periods'][s.PERIOD]['days']['2026-11-05']['bolton']
 for name,value in dict(RUN=ctl['intake_run']['id'],KEY=key,BINDING=w['binding']['execution_binding'],MARKER_SHA=a06.sha(ctl['intake_run']),AUTHORITY=c.execute('SELECT authority FROM ingestion_work_items WHERE key=%s',(key,)).fetchone()[0]).items():monkeypatch.setattr(s,name,value)
 monkeypatch.setattr(s,'EVIDENCE',dict(c.execute('SELECT name,sha256 FROM ingestion_run_evidence WHERE period=%s AND run_id=%s',(s.PERIOD,s.RUN)).fetchall()))
 c.execute('UPDATE ingestion_work_items SET lease_until=%s WHERE key=%s',(time.time()-60,key))
 # Two retained historical assessment sets; never silently choose one.
 root=s.HISTORICAL_BOLTON
 c.execute("INSERT INTO ingestion_work_items SELECT (jsonb_populate_record(NULL::ingestion_work_items,to_jsonb(w)||%s::jsonb)).* FROM ingestion_work_items w WHERE key=%s",(json.dumps(dict(key=root,contract='bolton-received-idox-coordinator-v1')),prior.TAMESIDE))
 rows=c.execute("SELECT key FROM ingestion_work_items WHERE task='SCREENING' AND dependencies::jsonb=jsonb_build_array(%s::text)",(prior.TAMESIDE,)).fetchall();assert len(rows)==24
 for group in range(2):
  for (old,) in rows:
   patch=dict(key=hashlib.sha256((str(group)+old).encode()).hexdigest(),dependencies=[root])
   c.execute("INSERT INTO ingestion_work_items SELECT (jsonb_populate_record(NULL::ingestion_work_items,to_jsonb(w)||%s::jsonb)).* FROM ingestion_work_items w WHERE key=%s",(json.dumps(patch),old))
 assert c.execute("SELECT count(*) FROM ingestion_work_items WHERE dependencies::jsonb=jsonb_build_array(%s::text)",(root,)).fetchone()==(48,)
 w['history_before']=copy.deepcopy(ctl['intake_periods']);w['protected']=s.protected_sha(c);w['all_other']=s.all_other_work_sha(c);w['members']=c.execute(op.MEMBERS).fetchall();w['protected_backlog']=backlog(w)
 w['evidence_before']=c.execute('SELECT period,run_id,name,body,sha256 FROM ingestion_run_evidence ORDER BY period,run_id,name').fetchall()
 assert op.stop_snapshot(ctl)==s.STOP14
 return w

@pytest.mark.parametrize('mode',['normal','before','lost','after_recover','before_cleanup'])
def test_settlement_preserves_completed_tameside(failed_bolton,mode):
 w=failed_bolton;c=w['boot'];before=op.ledger_sha(c);retained=backlog(w)
 with w['actor']() as actor:assert s.inspect(actor,w['binding'])['status']=='READY_FOR_REVIEW_NOT_AUTHORISED'
 class Break(Fault):
  def execute(self,q,p=None):
   if mode=='before_cleanup' and q=='RESET ROLE' and getattr(self,'recovered',False):raise RuntimeError('BEFORE_CLEANUP')
   r=super().execute(q,p)
   if q.startswith('SELECT public.ingestion_recover_abandoned'):self.recovered=True
   if mode=='after_recover' and q.startswith('SELECT public.ingestion_recover_abandoned'):raise RuntimeError('AFTER_RECOVER')
   return r
 with w['actor']() as actor:
  if mode=='normal':s.recover(actor,w['binding'])
  else:
   with pytest.raises(RuntimeError):s.recover(Break(actor,mode),w['binding'])
 assert s.protected_sha(c)==w['protected'] and s.all_other_work_sha(c)==w['all_other'];s.tameside(c);assert backlog(w)==retained
 assert c.execute(op.MEMBERS).fetchall()==w['members']
 assert c.execute('SELECT period,run_id,name,body,sha256 FROM ingestion_run_evidence ORDER BY period,run_id,name').fetchall()==w['evidence_before']
 ctl=op.control(c)
 for period in w['history_before']:
  if period!=s.PERIOD:assert ctl['intake_periods'][period]==w['history_before'][period]
 if mode in ('normal','lost'):
  with w['actor']() as actor:assert s.inspect(actor,w['binding'])['status']=='COMMITTED_STATE_VERIFIED_READ_ONLY'
  assert op.stop_snapshot(ctl)==s.STOP15 and 'intake_run' not in ctl
  receipt=s.history(c,ctl);assert receipt['coverage']=='UNKNOWN' and receipt['actual_requests']==receipt['requests_accounted']==4 and receipt['request_count_status']=='COMPLETE'
  snapshot=op.ledger_sha(c)
  with w['actor']() as actor:
   with pytest.raises(op.Denied):s.recover(actor,w['binding'])
  assert op.ledger_sha(c)==snapshot
  if mode=='normal':
   c.execute("INSERT INTO ingestion_work_items SELECT (jsonb_populate_record(NULL::ingestion_work_items,to_jsonb(w)||%s::jsonb)).* FROM ingestion_work_items w WHERE key=%s",(json.dumps(dict(key='f'*64,task='DISCOVERY',checkpoint=None)),op.CONTROL))
   assert s.history(c,op.control(c))['actual_requests']==4
 else:assert op.ledger_sha(c)==before

@pytest.mark.parametrize('drift',['marker','stop','fence','checkpoint','lease','tameside','screen','screen_content','batch','evidence','prior'])
def test_changed_state_refuses_atomically(failed_bolton,drift):
 w=failed_bolton;c=w['boot'];ctl=op.control(c)
 if drift=='marker':ctl['intake_run']['id']='0'*32
 elif drift=='stop':ctl['manual_stop']='UNRELATED'
 elif drift=='prior':ctl['intake_periods'][prior.PERIOD]['failed_runs'][prior.RUN]['actual_requests']=999
 elif drift in ('fence','checkpoint','lease'):
  field,value={'fence':('fence',2),'checkpoint':('checkpoint','{}'),'lease':('lease_until',time.time()+60)}[drift]
  from psycopg import sql
  c.execute(sql.SQL('UPDATE ingestion_work_items SET {}=%s WHERE key=%s').format(sql.Identifier(field)),(value,s.KEY))
 elif drift=='tameside':c.execute("UPDATE ingestion_work_items SET state='CLAIMED' WHERE key=%s",(prior.TAMESIDE,))
 elif drift=='screen_content':c.execute("UPDATE ingestion_work_items SET checkpoint=(checkpoint::jsonb||'{\"changed\":true}'::jsonb)::json WHERE key=(SELECT key FROM ingestion_work_items WHERE task='SCREENING' AND dependencies::jsonb=jsonb_build_array(%s::text) LIMIT 1)",(prior.TAMESIDE,))
 elif drift in ('screen','batch'):c.execute("UPDATE ingestion_work_items SET state='CLAIMED' WHERE key=(SELECT key FROM ingestion_work_items WHERE task=%s AND state='COMPLETE' LIMIT 1)",('SCREENING' if drift=='screen' else 'LISTING_METADATA',))
 elif drift=='evidence':c.execute("UPDATE ingestion_run_evidence SET body='bad'::bytea,sha256=encode(sha256('bad'::bytea),'hex') WHERE period=%s AND name='final/result-before-publication.json'",(s.PERIOD,))
 c.execute('UPDATE ingestion_work_items SET outcome=%s::json WHERE key=%s',(json.dumps(ctl),op.CONTROL));before=op.ledger_sha(c)
 with w['actor']() as actor:
  with pytest.raises(op.Denied):s.recover(actor,w['binding'])
 assert op.ledger_sha(c)==before and c.execute(op.MEMBERS).fetchall()==w['members']

@pytest.mark.parametrize('lost',[False,True])
def test_actual_owner_entrypoint_and_readback(failed_bolton,monkeypatch,lost):
 from contextlib import contextmanager
 from scripts import owner_bolton01_settlement as cli
 w=failed_bolton
 class DB:
  @contextmanager
  def connection(self):
   with w['actor']() as c:yield Fault(c,'lost') if lost else c
 monkeypatch.setattr(cli.pilot,'Database',DB);monkeypatch.setattr(s,'binding',lambda db:w['binding'])
 monkeypatch.delenv('PROPERTYAIGENT_OWNER_SETTLEMENT_AUTHORITY',raising=False)
 before=op.ledger_sha(w['boot']);assert cli.main(['--action','settle'])==2
 assert op.ledger_sha(w['boot'])==before
 assert cli.main(['--action','inspect'])==0
 monkeypatch.setenv('PROPERTYAIGENT_OWNER_SETTLEMENT_AUTHORITY',s.PERIOD)
 assert cli.main(['--action','settle'])==(2 if lost else 0)
 assert cli.main(['--action','inspect'])==0
 assert backlog(w)==w['protected_backlog']
 assert w['boot'].execute(op.MEMBERS).fetchall()==w['members']
