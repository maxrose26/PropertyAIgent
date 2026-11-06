"""Actual fixed owner operations and runtime against disposable PG; no council transport."""
import copy,json,subprocess,hashlib,os
from pathlib import Path
from contextlib import contextmanager
from datetime import date,datetime,timezone
from types import SimpleNamespace
import pytest
from tests.test_attempt06_owner_path_pg import world,act,Fault
from tests.test_period07_settlement_pg import failed07
from tests.test_period08_successor_pg import settled08
from tests.test_period08_settlement_pg import failed08,backlog
from tests.test_period09_successor_pg import ready09
from tests.test_period09_settlement_pg import failed09
from tests.e2e_connection_support import arcus_audit,arcus_slot_supervised,entry,SCHEME
from verification.ingestion_storage import period09_settlement as s,period08_settlement as prior,period10_successor as p10,intake_owner as op,intake_owner_operations as extra,attempt06_recovery as a06,owner_pilot as pilot
from verification.ingestion_storage.daily_intake_runtime import Runtime,execution_binding,main

@pytest.fixture
def ready10(failed09,monkeypatch):
 w=failed09;c=w['boot'];act(w,s.recover)
 r=s.history(c,op.control(c));monkeypatch.setattr(p10,'RECEIPT_SHA',a06.sha(r));monkeypatch.setattr(p10,'BINDING',execution_binding());monkeypatch.setattr(p10,'TREE',subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True).strip())
 b=w['binding'];b.pop('period08_receipt_sha256');b.update(period=p10.SUCCESSOR,period09_receipt_sha256=p10.RECEIPT_SHA,accepted_stop=p10.ACCEPTED,execution_binding=p10.BINDING)
 p=w['policy'];p.update(councils=p10.councils(),expected_stop=p10.ACCEPTED,execution_binding=p10.BINDING);b['period_policy_sha256']=a06.sha(p)
 monkeypatch.setenv('PROPERTYAIGENT_INTAKE_SOURCE_RELEASE',json.dumps(dict(execution_binding=p10.BINDING,tree=p10.TREE,branch=p10.BRANCH)))
 w['protected_backlog']=backlog(w);w['histories']=copy.deepcopy(op.control(c)['intake_periods'])
 w['members']=c.execute(op.MEMBERS).fetchall()
 return w

@pytest.mark.parametrize('mode',['normal','before','lost','after_update','before_cleanup'])
def test_disposition_atomic_and_uncertain_ack(ready10,mode):
 w=ready10;c=w['boot'];before=op.ledger_sha(c)
 class Break(Fault):
  def execute(self,q,p=None):
   if mode=='before_cleanup' and q=='RESET ROLE':raise RuntimeError('BEFORE_CLEANUP')
   r=super().execute(q,p)
   if mode=='after_update' and q.startswith('UPDATE public.ingestion_work_items SET outcome'):raise RuntimeError('AFTER_UPDATE')
   return r
 with w['actor']() as actor:
  if mode=='normal':p10.dispose(actor,w['binding'])
  else:
   with pytest.raises(RuntimeError):p10.dispose(Break(actor,mode),w['binding'])
 assert c.execute(op.MEMBERS).fetchall()==w['members'];assert backlog(w)==w['protected_backlog']
 if mode in ('normal','lost'):
  with w['actor']() as actor:assert p10.inspect(actor,w['binding'])['status']=='DISPOSITION_COMMITTED_VERIFIED'
  assert op.stop_snapshot(op.control(c))==p10.ACCEPTED
  with w['actor']() as actor:
   with pytest.raises(op.Denied):p10.dispose(actor,w['binding'])
 else:assert op.ledger_sha(c)==before

@pytest.mark.parametrize('drift',['receipt','global','manual','generation','last','used','tameside','release'])
def test_changed_state_refuses(ready10,drift):
 w=ready10;c=w['boot'];b=copy.deepcopy(w['binding']);ctl=op.control(c)
 if drift=='receipt':b['period09_receipt_sha256']='0'*64
 elif drift=='release':b['execution_binding']=dict(b['execution_binding'],revision='0'*40)
 elif drift=='used':ctl['intake_periods'][p10.SUCCESSOR]={}
 elif drift=='tameside':c.execute("UPDATE ingestion_work_items SET checkpoint='{}' WHERE key=%s",(prior.TAMESIDE,))
 else:ctl[dict(global_='global_stop',manual='manual_stop',generation='hard_stop_generation',last='last_hard_stop').get(drift,'global_stop')]='UNRELATED'
 c.execute('UPDATE ingestion_work_items SET outcome=%s::json WHERE key=%s',(json.dumps(ctl),op.CONTROL));before=op.ledger_sha(c)
 with w['actor']() as actor:
  with pytest.raises(Exception):p10.dispose(actor,b)
 assert before==op.ledger_sha(c) and c.execute(op.MEMBERS).fetchall()==w['members']

@pytest.mark.parametrize('incomplete',[False,True])
def test_actual_owner_entry_runtime_backlog_and_closure(ready10,tmp_path,monkeypatch,incomplete):
 w=ready10;c=w['boot'];b=w['binding'];p=w['policy']
 # Execute actual owner CLI for disposition/readback; only configured connection and
 # immutable fixture identity binding replace production integrations.
 from scripts import owner_period10
 class DB:
  @contextmanager
  def connection(self):
   with w['actor']() as actor:yield actor
 monkeypatch.setattr(pilot,'Database',DB);monkeypatch.setattr(p10,'binding_from_saved_state',lambda db:b)
 for name in ('PERIOD','PREDECESSOR','OWNER_PERIOD','OWNER_RUN'):monkeypatch.setattr(pilot,name,getattr(pilot,name))
 monkeypatch.setenv('PROPERTYAIGENT_OWNER_PILOT_AUTHORITY',p10.SUCCESSOR)
 assert owner_period10.main(['--action','inspect'])==0
 assert owner_period10.main(['--action','dispose'])==0
 assert owner_period10.main(['--action','inspect'])==0
 from verification.ingestion_storage.owner_pilot_continuation import migrate_owner_namespace
 with w['actor']() as actor:migrate_owner_namespace(actor,attempt10=True,binding10=b,stable_verifiers=b['credential_verifier_sha256'])
 with w['actor']() as actor:p10.namespace(actor,migrated=True)
 with w['actor']() as actor:extra.issue_period(actor,b,p,dict(version='FINITE_INTAKE_PERIOD_V1',state='ARMED_NO_RETRY',binding=b,policy=p),lambda _:None)
 passwords={r:__import__('sqlalchemy').engine.make_url(w['urls'][r]).password for r in op.ROLES};states=[]
 with w['actor']() as actor:
  prepared=op.prepare_activation(actor,b,stable_credentials=passwords);op.activate(actor,b,lambda v:states.append(copy.deepcopy(v)),prepared=prepared)
 for role,var in [('ingestion_worker_login','INGESTION_WORKER_DATABASE_URL'),('ingestion_effect_login','INGESTION_EFFECT_DATABASE_URL')]:monkeypatch.setenv(var,w['urls'][role])
 monkeypatch.delenv('DATABASE_URL',raising=False)
 argv=['--period',p10.SUCCESSOR,'--output',str(tmp_path/'successor10'),'--hostaddr',b['hostaddr']]
 args=SimpleNamespace(period=p10.SUCCESSOR,output=str(tmp_path/'successor10'),hostaddr=b['hostaddr'],disposable_sources=None,disposable_archive=None,backlog=False,after=None,page_size=3)
 runtime=Runtime(args);runtime.route_name=b['route'];called=[]
 monkeypatch.setattr('verification.ingestion_storage.daily_intake_runtime.require_source_context',lambda *a,**kw:None)
 def source(row):
  assert row==dict(council='manchester',semantics='VALIDATED',start='2026-10-27',end='2026-11-02');called.append(row)
  runtime.run.begin_source();folder=tmp_path/'source10';folder.mkdir()
  audit=arcus_audit('manchester',[entry('M10/26',SCHEME)],date(2026,10,27),date(2026,11,2),budget='BROWSER_SOURCE_V2')
  if incomplete:audit.update(failure='PAGE_CAP',safety_failure=True)
  audit,outer,_=arcus_slot_supervised(folder,audit,runtime.contract(row).scope())
  if not incomplete and os.environ.get('P10_LOOPBACK_CAPTURE'):
   observed=json.loads(Path(os.environ['P10_LOOPBACK_CAPTURE']).read_text())
   audit,outer=observed['audit'],observed['outer']
   assert len(audit['listing_records'])==60 and audit['requests']==2
  runtime.run.source(dict(requests=audit['requests'],source_bytes=audit['decoded_bytes']+audit['encoded_bytes']+audit['outbound_payload_bytes'],source_seconds=audit['supervisor_seconds'],supervised_seconds=outer['elapsed_seconds']))
  runtime.archive(__import__('verification.ingestion_storage.database_evidence',fromlist=['canonical']).canonical(audit))
  return audit,dict(outer,observed_at=datetime.now(timezone.utc).isoformat())
 expected_records=60 if not incomplete and os.environ.get('P10_LOOPBACK_CAPTURE') else 1
 runtime.collect=source
 assert main(argv,prepared_runtime=runtime)==(1 if incomplete else 0)
 assert len(called)==1 and backlog(w)==w['protected_backlog']
 ctl=op.control(c);assert ctl['intake_periods'][s.PERIOD]['failed_runs']==w['histories'][s.PERIOD]['failed_runs']
 assert set(ctl['intake_periods'][p10.SUCCESSOR]['days']['2026-11-02'])=={'manchester'}
 run=ctl['intake_run']
 if not incomplete:
  assert run['state']=='VERIFIED'
  with w['actor']() as actor:verified=op.finalisation(actor,b,dict(run_id=run['id'],publication=run['publication']))
  assert len(verified['captures'])==1 and verified['captures'][0]['council']=='manchester' and verified['captures'][0]['screening_complete']==expected_records
  from app.ingestion.daily_intake import backlog_page
  from app.ingestion.sql_ledger import SQLLedger
  from app.ingestion.listing_screening import ScreeningRule,RULE_V3
  ledger=SQLLedger(w['app'],owner='test',authority='',bindings={});records=[];cursor=None
  for _ in range(10):
   page=backlog_page(ledger,['tameside','manchester'],[extra.COUNCILS[k]['contract'] for k in ('tameside','manchester')],ScreeningRule(RULE_V3,unit_threshold=10,link_related=False),after=cursor)
   records+=page['records']
   if not page['more']:break
   cursor=page['next_cursor']
  assert len([r for r in records if r['capture_key']==prior.TAMESIDE])==24
  new=[r for r in records if r['archive']['period']==p10.SUCCESSOR]
  assert len(new)==expected_records and all(x['council']=='manchester' and x['archive']['run_id']==run['id'] for x in new)
  # Actual admission path must refuse a second run without transport.
  duplicate=Runtime(SimpleNamespace(**{**vars(args),'output':str(tmp_path/'duplicate')}));duplicate.route_name=b['route'];duplicate.collect=lambda row:pytest.fail('RECOLLECTION')
  before_duplicate=op.ledger_sha(c)
  repeated=duplicate.execute()
  assert repeated['status']=='STOP_RECONCILE_NO_RETRY' and repeated['reason']=='P10_ALREADY_CONSUMED'
  assert op.ledger_sha(c)==before_duplicate
 else:assert run['state']!='VERIFIED'
 with w['actor']() as actor:closed=op.close(actor,states[-1],lambda _:None)
 assert closed['runtime_access']=='DISABLED' and closed['sessions']=='ABSENT'
 assert c.execute(op.MEMBERS).fetchall()==w['members'] and s.protected_sha(c)==w['protected']

@pytest.mark.parametrize('mode',['normal','before','lost','after_registrar'])
def test_namespace_and_registrar_atomicity(ready10,mode):
 from verification.ingestion_storage.owner_pilot_continuation import migrate_owner_namespace
 w=ready10;c=w['boot'];act(w,p10.dispose)
 before=op.ledger_sha(c);members=c.execute(op.MEMBERS).fetchall()
 query="SELECT proname,prosrc,proacl::text,proowner,prosecdef,proconfig FROM pg_proc WHERE oid=ANY(ARRAY['public.ingestion_intake_owner_state(text,text,text,bytea)'::regprocedure,'public.ingestion_register_bolton_exception(jsonb)'::regprocedure]) ORDER BY proname"
 definitions=c.execute(query).fetchall();evidence=c.execute('SELECT * FROM ingestion_run_evidence ORDER BY period,run_id,name').fetchall()
 schema=c.execute("SELECT nspacl::text FROM pg_namespace WHERE nspname='public'").fetchone()
 class Break(Fault):
  def execute(self,q,p=None):
   r=super().execute(q,p)
   if mode=='after_registrar' and q.startswith('CREATE OR REPLACE FUNCTION public.ingestion_register_bolton_exception'):raise RuntimeError('AFTER_REGISTRAR')
   return r
 with w['actor']() as actor:
  if mode=='normal':migrate_owner_namespace(actor,attempt10=True,binding10=w['binding'],stable_verifiers=w['binding']['credential_verifier_sha256'])
  else:
   with pytest.raises(RuntimeError):migrate_owner_namespace(Break(actor,mode),attempt10=True,binding10=w['binding'],stable_verifiers=w['binding']['credential_verifier_sha256'])
 assert op.ledger_sha(c)==before and c.execute(op.MEMBERS).fetchall()==members
 assert c.execute('SELECT * FROM ingestion_run_evidence ORDER BY period,run_id,name').fetchall()==evidence
 assert c.execute("SELECT nspacl::text FROM pg_namespace WHERE nspname='public'").fetchone()==schema
 if mode in ('normal','lost'):
  with w['actor']() as actor:p10.namespace(actor,migrated=True)
  for old,new in zip(definitions,c.execute(query).fetchall()):assert old[0]==new[0] and old[2:]==new[2:]
 else:assert c.execute(query).fetchall()==definitions

@pytest.mark.parametrize('mode',['before','lost'])
def test_registration_ack_reconciled_without_repetition(ready10,mode):
 from verification.ingestion_storage.owner_pilot_continuation import migrate_owner_namespace
 w=ready10;c=w['boot'];act(w,p10.dispose);b=w['binding'];p=w['policy']
 with w['actor']() as actor:migrate_owner_namespace(actor,attempt10=True,binding10=b,stable_verifiers=b['credential_verifier_sha256'])
 before=op.ledger_sha(c)
 with w['actor']() as actor:
  with pytest.raises(Exception):extra.issue_period(Fault(actor,mode),b,p,dict(version='FINITE_INTAKE_PERIOD_V1',state='ARMED_NO_RETRY',binding=b,policy=p),lambda _:None)
 with w['actor']() as fresh:
  fresh.execute('BEGIN READ ONLY')
  ctl=op.control(fresh);fresh.execute('ROLLBACK')
 if mode=='lost':assert {k:ctl['intake_periods'][p10.SUCCESSOR][k] for k in p}==p
 else:assert p10.SUCCESSOR not in ctl['intake_periods'] and op.ledger_sha(c)==before
 assert c.execute(op.MEMBERS).fetchall()==w['members'] and backlog(w)==w['protected_backlog']

@pytest.mark.parametrize('change',['both','tameside','other_period','generation','receipt','binding'])
def test_sql_registration_scope_not_just_python_guard(ready10,change):
 from verification.ingestion_storage.owner_pilot_continuation import migrate_owner_namespace
 w=ready10;c=w['boot'];act(w,p10.dispose);b=w['binding'];policy=copy.deepcopy(w['policy']);period=p10.SUCCESSOR
 with w['actor']() as actor:migrate_owner_namespace(actor,attempt10=True,binding10=b,stable_verifiers=b['credential_verifier_sha256'])
 before=op.ledger_sha(c);members=c.execute(op.MEMBERS).fetchall()
 if change=='both':policy['councils']=copy.deepcopy(extra.COUNCILS)
 if change=='tameside':policy['councils']={'tameside':extra.COUNCILS['tameside']}
 if change=='other_period':period='b-dbpilot-20261027-1102-11'
 if change=='binding':policy['execution_binding']['revision']='0'*40
 c.execute('BEGIN')
 try:
  if change in ('generation','receipt'):
   ctl=op.control(c)
   if change=='generation':ctl['hard_stop_generation']=12;policy['expected_stop']['hard_stop_generation']=12
   else:ctl['intake_periods'][s.PERIOD]['failure_disposition']['receipt_sha256']='0'*64
   c.execute('UPDATE ingestion_work_items SET outcome=%s::json WHERE key=%s',(json.dumps(ctl),op.CONTROL))
  with pytest.raises(__import__('psycopg').errors.RaiseException):
   c.execute('SELECT ingestion_register_bolton_exception(%s::jsonb)',(json.dumps(dict(operation='intake_period',period=period,policy=policy)),))
 finally:c.execute('ROLLBACK')
 assert op.ledger_sha(c)==before and c.execute(op.MEMBERS).fetchall()==members
