"""Fixed period09 settlement over actual predecessor and failed runtime paths."""
import copy,json,time
from types import SimpleNamespace
import pytest
from tests.test_attempt06_owner_path_pg import world,act,Fault
from tests.test_period07_settlement_pg import failed07
from tests.test_period08_successor_pg import settled08
from tests.test_period08_settlement_pg import failed08,backlog
from tests.test_period09_successor_pg import ready09
from verification.ingestion_storage import period09_settlement as s,period08_settlement as prior,period09_successor as p09,intake_owner as op,intake_owner_operations as extra,attempt06_recovery as a06
from verification.ingestion_storage.daily_intake_runtime import Runtime

@pytest.fixture
def failed09(ready09,tmp_path,monkeypatch):
 w=ready09;c=w['boot'];b=w['binding'];act(w,p09.dispose)
 from verification.ingestion_storage.owner_pilot_continuation import migrate_owner_namespace
 with w['actor']() as actor:migrate_owner_namespace(actor,attempt09=True,binding09=b,stable_verifiers=b['credential_verifier_sha256'])
 with w['actor']() as actor:extra.issue_period(actor,b,w['policy'],dict(version='FINITE_INTAKE_PERIOD_V1',state='ARMED_NO_RETRY',binding=b,policy=w['policy']),lambda _:None)
 passwords={r:__import__('sqlalchemy').engine.make_url(w['urls'][r]).password for r in op.ROLES};states=[]
 with w['actor']() as actor:
  prepared=op.prepare_activation(actor,b,stable_credentials=passwords);op.activate(actor,b,lambda v:states.append(copy.deepcopy(v)),prepared=prepared)
 for role,var in [('ingestion_worker_login','INGESTION_WORKER_DATABASE_URL'),('ingestion_effect_login','INGESTION_EFFECT_DATABASE_URL')]:monkeypatch.setenv(var,w['urls'][role])
 monkeypatch.delenv('DATABASE_URL',raising=False)
 runtime=Runtime(SimpleNamespace(period=p09.SUCCESSOR,output=str(tmp_path/'failed09'),hostaddr=b['hostaddr'],disposable_sources=None,disposable_archive=None));runtime.route_name=b['route']
 def source(row):
  assert row=={k:v for k,v in s.SCOPE.items() if k!='kind'}
  runtime.run.begin_source()
  raise op.Denied('SOURCE_OR_CLEANUP_UNCERTAIN_NO_REPLAY')
 runtime.collect=source
 runtime.emit('runtime_authentication',dict(fixture=True))
 result=runtime.execute();assert result['reason']=='SOURCE_OR_CLEANUP_UNCERTAIN_NO_REPLAY' and result['usage']['requests'] is None
 with w['actor']() as actor:op.close(actor,states[-1],lambda _:None)
 ctl=op.control(c);key=ctl['intake_periods'][s.PERIOD]['days']['2026-11-02']['manchester']
 for name,value in [('RUN',ctl['intake_run']['id']),('KEY',key),('BINDING',b['execution_binding']),('MARKER_SHA',a06.sha(ctl['intake_run']))]:monkeypatch.setattr(s,name,value)
 monkeypatch.setattr(s,'AUTHORITY',c.execute('SELECT authority FROM ingestion_work_items WHERE key=%s',(key,)).fetchone()[0])
 c.execute('UPDATE ingestion_work_items SET lease_until=%s WHERE key=%s',(time.time()-60,key))
 monkeypatch.setattr(s,'EVIDENCE',dict(c.execute('SELECT name,sha256 FROM ingestion_run_evidence WHERE period=%s AND run_id=%s',(s.PERIOD,s.RUN)).fetchall()))
 w['history_before']=copy.deepcopy(ctl['intake_periods']);w['protected']=s.protected_sha(c);w['all_other']=s.all_other_work_sha(c);w['members']=c.execute(op.MEMBERS).fetchall()
 w['evidence_before']=c.execute('SELECT period,run_id,name,body,sha256 FROM ingestion_run_evidence ORDER BY period,run_id,name').fetchall()
 assert op.stop_snapshot(ctl)==s.STOP12
 return w

@pytest.mark.parametrize('mode',['normal','before','lost','after_recover','before_cleanup'])
def test_settlement_preserves_completed_tameside(failed09,mode):
 w=failed09;c=w['boot'];before=op.ledger_sha(c);retained=backlog(w)
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
 assert s.protected_sha(c)==w['protected'] and s.all_other_work_sha(c)==w['all_other'];s.tameside(c);assert backlog(w)==retained
 assert c.execute(op.MEMBERS).fetchall()==w['members']
 assert c.execute('SELECT period,run_id,name,body,sha256 FROM ingestion_run_evidence ORDER BY period,run_id,name').fetchall()==w['evidence_before']
 ctl=op.control(c)
 for period in w['history_before']:
  if period!=s.PERIOD:assert ctl['intake_periods'][period]==w['history_before'][period]
 if mode in ('normal','lost'):
  with w['actor']() as actor:assert s.inspect(actor,w['binding'])['status']=='COMMITTED_STATE_VERIFIED_READ_ONLY'
  assert op.stop_snapshot(ctl)==s.STOP13 and 'intake_run' not in ctl
  snapshot=op.ledger_sha(c)
  with w['actor']() as actor:
   with pytest.raises(op.Denied):s.recover(actor,w['binding'])
  assert op.ledger_sha(c)==snapshot
  if mode=='normal':
   c.execute("INSERT INTO ingestion_work_items SELECT (jsonb_populate_record(NULL::ingestion_work_items,to_jsonb(w)||%s::jsonb)).* FROM ingestion_work_items w WHERE key=%s",(json.dumps(dict(key='f'*64,task='DISCOVERY',checkpoint=None)),op.CONTROL))
   assert s.history(c,op.control(c))['actual_requests'] is None
 else:assert op.ledger_sha(c)==before

@pytest.mark.parametrize('drift',['marker','stop','fence','checkpoint','lease','tameside','screen','screen_content','batch','evidence','prior'])
def test_changed_state_refuses_atomically(failed09,drift):
 w=failed09;c=w['boot'];ctl=op.control(c)
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

def test_actual_owner_entrypoint_and_readback(failed09,monkeypatch):
 from contextlib import contextmanager
 from scripts import owner_period09_settlement as cli
 w=failed09
 class DB:
  @contextmanager
  def connection(self):
   with w['actor']() as c:yield c
 monkeypatch.setattr(cli.pilot,'Database',DB);monkeypatch.setattr(s,'binding',lambda db:w['binding'])
 monkeypatch.delenv('PROPERTYAIGENT_OWNER_SETTLEMENT_AUTHORITY',raising=False)
 before=op.ledger_sha(w['boot']);assert cli.main(['--action','settle'])==2
 assert op.ledger_sha(w['boot'])==before
 assert cli.main(['--action','inspect'])==0
 monkeypatch.setenv('PROPERTYAIGENT_OWNER_SETTLEMENT_AUTHORITY',s.PERIOD)
 assert cli.main(['--action','settle'])==0
 assert cli.main(['--action','inspect'])==0
 assert backlog(w)==w['protected_backlog']
 assert w['boot'].execute(op.MEMBERS).fetchall()==w['members']
