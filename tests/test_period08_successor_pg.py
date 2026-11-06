"""Period08 actual owner/PG boundaries. Synthetic evidence only; no live transport."""
import copy,hashlib,json,time,subprocess
from datetime import date,datetime,timezone
from types import SimpleNamespace
import pytest
from contextlib import contextmanager
from tests.test_attempt06_owner_path_pg import world,act,Fault
from tests.test_period07_settlement_pg import failed07
from tests.e2e_connection_support import entry,SCHEME,idox_supervised,arcus_audit,arcus_slot_supervised
from verification.ingestion_storage import period08_successor as p08,period07_settlement as p07,attempt06_recovery as a06,intake_owner as op,intake_owner_operations as extra,owner_pilot,database_evidence as de
from verification.ingestion_storage.daily_intake_runtime import Runtime,execution_binding

@pytest.fixture
def settled08(failed07,monkeypatch):
 w=failed07;c=w['boot']
 with w['actor']() as actor:p07.recover(actor,w['binding'])
 ctl=op.control(c);r=ctl['intake_periods'][p07.PERIOD]['failed_runs'][p07.RUN]
 monkeypatch.setattr(p08,'RECEIPT_SHA',a06.sha(r));monkeypatch.setattr(p08,'BINDING',execution_binding())
 monkeypatch.setattr(p08,'TREE',subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True).strip())
 b=w['binding'];b.pop('attempt06_receipt_sha256');b.update(period=p08.SUCCESSOR,accepted_stop=p08.ACCEPTED,execution_binding=p08.BINDING,period07_receipt_sha256=p08.RECEIPT_SHA)
 p=w['policy'];p.update(expected_stop=p08.ACCEPTED,execution_binding=p08.BINDING);b['period_policy_sha256']=a06.sha(p)
 release=dict(execution_binding=p08.BINDING,tree=p08.TREE,branch=p08.BRANCH,period07_receipt_sha256=p08.RECEIPT_SHA)
 monkeypatch.setenv('PROPERTYAIGENT_INTAKE_SOURCE_RELEASE',json.dumps(release))
 # Read-only inventory capability observed on the configured live owner; no write ACL.
 c.execute('GRANT pg_read_all_data TO postgres')
 c.execute('GRANT CREATE ON SCHEMA public TO ingestion_storage_owner');c.execute('SET ROLE ingestion_storage_owner')
 c.execute(de.ATTEMPT07_OWNER_SQL.split('REVOKE ALL ON FUNCTION',1)[0].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1))
 c.execute('RESET ROLE');c.execute('REVOKE CREATE ON SCHEMA public FROM ingestion_storage_owner')
 c.execute('GRANT CREATE ON SCHEMA public TO postgres WITH GRANT OPTION')
 w['members']=c.execute(op.MEMBERS).fetchall();w['history07']=copy.deepcopy(ctl['intake_periods'][p07.PERIOD])
 return w

@pytest.mark.parametrize('mode',['normal','before','lost','after_update','before_cleanup'])
def test_disposition_atomicity_and_ack_reconciliation(settled08,mode):
 w=settled08;c=w['boot'];before=op.ledger_sha(c)
 with w['actor']() as actor:assert p08.inspect(actor,w['binding'])['status']=='PRE_DISPOSITION_VERIFIED'
 class Break(Fault):
  def execute(self,q,p=None):
   if mode=='before_cleanup' and q=='RESET ROLE':raise RuntimeError('SYNTHETIC_BEFORE_CLEANUP')
   r=super().execute(q,p)
   if mode=='after_update' and q.startswith('UPDATE public.ingestion_work_items SET outcome'):raise RuntimeError('SYNTHETIC_AFTER_UPDATE')
   return r
 with w['actor']() as actor:
  if mode=='normal':p08.dispose(actor,w['binding'])
  else:
   with pytest.raises(RuntimeError):p08.dispose(Break(actor,mode),w['binding'])
 assert c.execute(op.MEMBERS).fetchall()==w['members']
 assert c.execute('SELECT period,run_id,name,body,sha256 FROM ingestion_run_evidence ORDER BY period,run_id,name').fetchall()==w['evidence_before']
 ctl=op.control(c);assert ctl['intake_periods'][a06.PERIOD]==w['history06']
 if mode in ('normal','lost'):
  with w['actor']() as actor:assert p08.inspect(actor,w['binding'])['status']=='DISPOSITION_COMMITTED_VERIFIED'
  assert ctl['intake_periods'][p07.PERIOD]['failed_runs']==w['history07']['failed_runs']
  assert op.stop_snapshot(ctl)==p08.ACCEPTED and ctl['unrelated_preserved']=={'stop':'DO_NOT_CHANGE'}
  snapshot=op.ledger_sha(c)
  with w['actor']() as actor:
   with pytest.raises(op.Denied):p08.dispose(actor,w['binding'])
  assert op.ledger_sha(c)==snapshot
 else:assert op.ledger_sha(c)==before

@pytest.mark.parametrize('drift',['receipt','global','manual','generation','last','release','history','used','journal','marker','permission','namespace'])
def test_disposition_refuses_changed_state(settled08,drift):
 w=settled08;c=w['boot'];ctl=op.control(c);b=copy.deepcopy(w['binding'])
 if drift=='receipt':b['period07_receipt_sha256']='0'*64
 elif drift=='release':b['execution_binding']=dict(b['execution_binding'],revision='0'*40)
 elif drift in ('global','manual','generation','last'):ctl[dict(global_='global_stop',manual='manual_stop',generation='hard_stop_generation',last='last_hard_stop').get(drift,'global_stop')]='UNRELATED'
 elif drift=='history':ctl['intake_periods'][p07.PERIOD]['failed_runs'][p07.RUN]['actual_requests']=0
 elif drift=='used':ctl['intake_periods'][p08.SUCCESSOR]={}
 elif drift=='marker':ctl['intake_run']={'id':'0'*32}
 elif drift=='namespace':
  c.execute('GRANT CREATE ON SCHEMA public TO ingestion_storage_owner');c.execute('SET ROLE ingestion_storage_owner')
  c.execute(de.ATTEMPT06_OWNER_SQL.split('REVOKE ALL ON FUNCTION',1)[0].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1))
  c.execute('RESET ROLE');c.execute('REVOKE CREATE ON SCHEMA public FROM ingestion_storage_owner')
 elif drift=='permission':c.execute('GRANT ingestion_storage_owner TO postgres WITH ADMIN FALSE,INHERIT FALSE,SET TRUE')
 elif drift=='journal':c.execute("INSERT INTO ingestion_run_evidence(period,run_id,name,body,sha256) VALUES(%s,%s,'owner/state-000',%s,%s)",(p08.SUCCESSOR+'_owner','0'*32,b'used',hashlib.sha256(b'used').hexdigest()))
 c.execute('UPDATE ingestion_work_items SET outcome=%s::json WHERE key=%s',(json.dumps(ctl),op.CONTROL))
 before=op.ledger_sha(c);members=c.execute(op.MEMBERS).fetchall()
 with w['actor']() as actor:
  with pytest.raises(Exception):p08.dispose(actor,b)
 assert op.ledger_sha(c)==before and c.execute(op.MEMBERS).fetchall()==members

def test_actual_period08_owner_sequence_and_bounded_successor(settled08,tmp_path,monkeypatch,record_property):
 w=settled08;c=w['boot'];b=w['binding'];p=w['policy']
 saved=copy.deepcopy(op.control(c)['intake_periods'][p07.PERIOD])
 act(w,p08.dispose)
 with w['actor']() as actor:assert p08.inspect(actor,b)['stop']==p08.ACCEPTED
 from verification.ingestion_storage.owner_pilot_continuation import migrate_owner_namespace
 with w['actor']() as actor:migrate_owner_namespace(actor,attempt08=True,binding08=b,stable_verifiers=b['credential_verifier_sha256'])
 with w['actor']() as actor:p08.namespace(actor,migrated=True)
 state=dict(version='FINITE_INTAKE_PERIOD_V1',state='ARMED_NO_RETRY',binding=b,policy=p)
 with w['actor']() as actor:extra.issue_period(actor,b,p,state,lambda _:None)
 assert c.execute(op.MEMBERS).fetchall()==w['members']
 passwords={r:__import__('sqlalchemy').engine.make_url(w['urls'][r]).password for r in op.ROLES}
 states=[]
 with w['actor']() as actor:
  prepared=op.prepare_activation(actor,b,stable_credentials=passwords)
  op.activate(actor,b,lambda v:states.append(copy.deepcopy(v)),prepared=prepared)
 # Only transport/resource adapters are synthetic. Owner/SQL guards are unchanged.
 for role,var in [('ingestion_worker_login','INGESTION_WORKER_DATABASE_URL'),('ingestion_effect_login','INGESTION_EFFECT_DATABASE_URL')]:monkeypatch.setenv(var,w['urls'][role])
 monkeypatch.delenv('DATABASE_URL',raising=False)
 args=SimpleNamespace(period=p08.SUCCESSOR,output=str(tmp_path/'run'),hostaddr=b['hostaddr'],disposable_sources=None,disposable_archive=None)
 runtime=Runtime(args);runtime.route_name=b['route']  # same SQL connection, fixture loopback transport
 monkeypatch.setattr('verification.ingestion_storage.daily_intake_runtime.require_source_context',lambda *a,**kw:None)
 def source(row):
  runtime.run.begin_source();start,end=date.fromisoformat(row['start']),date.fromisoformat(row['end'])
  records=[entry('SYNTHETIC/26',SCHEME)]
  folder=tmp_path/row['council'];folder.mkdir()
  if row['council']=='tameside':
   from tests.test_tameside_b_connection import connected_source
   prep=folder/'prepare';prep.mkdir();audit,physical_calls=connected_source(prep,monkeypatch,row)
   assert len(physical_calls)==5
  else:audit=arcus_audit('manchester',records,start,end,budget='BROWSER_SOURCE_V2')
  if row['council']=='tameside':
   audit,outer=idox_supervised(folder,audit);r=audit['resource']
   metrics=dict(requests=r['requests_attempted'],source_bytes=r['received_bytes'],source_seconds=r['elapsed_seconds'])
  else:
   audit,outer,_=arcus_slot_supervised(folder,audit,runtime.contract(row).scope())
   metrics=dict(requests=audit['requests'],source_bytes=audit['decoded_bytes']+audit['encoded_bytes']+audit['outbound_payload_bytes'],source_seconds=audit['supervisor_seconds'])
  runtime.run.source(dict(metrics,supervised_seconds=outer['elapsed_seconds']))
  return audit,dict(outer,observed_at=datetime.now(timezone.utc).isoformat())
 runtime.collect=source
 result=runtime.execute()
 assert result['status']=='RETAINED_AND_SCREENED',json.dumps(result,sort_keys=True)
 assert result['authority_closure']=='INVALIDATED' and result['cleanup']=='CLOSED'
 ctl=op.control(c);assert ctl['intake_run']['state']=='VERIFIED' and ctl['intake_run']['id']!=p07.RUN
 assert ctl['intake_periods'][p07.PERIOD]['failed_runs']==saved['failed_runs'] and op.stop_snapshot(ctl)==p08.ACCEPTED
 assert len(ctl['intake_periods'][p08.SUCCESSOR]['days']['2026-11-02'])==2
 assert c.execute("SELECT count(*) FROM ingestion_run_evidence WHERE period=%s AND sha256=encode(sha256(body),'hex')",(p08.SUCCESSOR,)).fetchone()==(4,)
 with w['actor']() as actor:verified=op.finalisation(actor,b,{'run_id':ctl['intake_run']['id'],'publication':ctl['intake_run']['publication']})
 assert verified['status']=='INDEPENDENT_DATABASE_VERIFIED_SUCCESS' and len(verified['captures'])==2
 assert all(x['screening_complete']==x['record_count'] for x in verified['captures'])
 with w['actor']() as actor:closed=op.close(actor,states[-1],lambda _:None)
 assert closed['runtime_access']=='DISABLED' and closed['sessions']=='ABSENT'
 assert c.execute(op.MEMBERS).fetchall()==w['members']
 record_property('postgres_version',w['server_version']);record_property('actor_superuser',False)
 record_property('sequence','recover/readback/dispose/readback/issue/activate/runtime/close')

@pytest.mark.parametrize('mode',['normal','before','lost','after_replace'])
def test_namespace_atomicity_and_history(settled08,mode,monkeypatch):
 from verification.ingestion_storage.owner_pilot_continuation import migrate_owner_namespace
 w=settled08;c=w['boot'];act(w,p08.dispose)
 c.execute('GRANT CREATE ON SCHEMA public TO ingestion_storage_owner');c.execute('SET ROLE ingestion_storage_owner')
 c.execute(de.ATTEMPT07_OWNER_SQL.split('REVOKE ALL ON FUNCTION',1)[0].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1))
 c.execute('RESET ROLE');c.execute('REVOKE CREATE ON SCHEMA public FROM ingestion_storage_owner')
 c.execute('GRANT CREATE ON SCHEMA public TO postgres WITH GRANT OPTION')
 monkeypatch.setattr(owner_pilot,'PERIOD',p08.SUCCESSOR);monkeypatch.setattr(owner_pilot,'PREDECESSOR',p07.PERIOD)
 class DB:
  key='b'*64;address='192.0.2.1'
  @contextmanager
  def connection(self):
   with w['actor']() as actor:yield actor
 db=DB();j=owner_pilot.Journal(db,p07.PERIOD)
 passwords={r:__import__('sqlalchemy').engine.make_url(w['urls'][r]).password for r in op.ROLES}
 old=dict(period=p07.PERIOD,status='CLOSED',job={'id':p07.JOB},job_terminal={'status':'failed'},binding=dict(execution_binding=p07.BINDING),
  closure_verification=dict(status='VERIFIED',runtime_memberships=0,sessions=0,temporary_owner_absent=True,stable_verifiers='MATCH',suspended=True,configuration_equal=True,environment_equal=True,authorities_closed=True),
  final_service=dict(suspended=True,configuration_equal=True,environment_equal=True),
  stable_credentials=dict(version='STABLE_RESTRICTED_V1',passwords=passwords,verifier_sha256=w['binding']['credential_verifier_sha256']))
 j.save(old)
 c.execute("UPDATE ingestion_run_evidence SET name='owner/state-056' WHERE period=%s",(p07.PERIOD+'_owner',))
 j.load();monkeypatch.setattr(p07,'JOURNAL_SHA',j.previous)
 assert p08.binding_from_saved_state(db)['period07_receipt_sha256']==p08.RECEIPT_SHA
 before=op.ledger_sha(c);members=c.execute(op.MEMBERS).fetchall()
 schema=c.execute("SELECT nspacl::text FROM pg_namespace WHERE nspname='public'").fetchone()
 query="SELECT prosrc,proacl::text,proowner,prosecdef,proconfig FROM pg_proc WHERE oid='ingestion_intake_owner_state(text,text,text,bytea)'::regprocedure"
 definition=c.execute(query).fetchone()
 evidence=c.execute('SELECT period,run_id,name,body,sha256 FROM ingestion_run_evidence ORDER BY period,run_id,name').fetchall()
 class Break(Fault):
  def execute(self,q,p=None):
   r=super().execute(q,p)
   if mode=='after_replace' and 'CREATE OR REPLACE FUNCTION' in q:raise RuntimeError('SYNTHETIC_AFTER_REPLACE')
   return r
 with w['actor']() as actor:
  if mode=='normal':migrate_owner_namespace(actor,attempt08=True,binding08=w['binding'],stable_verifiers=w['binding']['credential_verifier_sha256'])
  else:
   with pytest.raises(RuntimeError):migrate_owner_namespace(Break(actor,mode),attempt08=True,binding08=w['binding'],stable_verifiers=w['binding']['credential_verifier_sha256'])
 assert c.execute(op.MEMBERS).fetchall()==members and op.ledger_sha(c)==before
 assert c.execute("SELECT nspacl::text FROM pg_namespace WHERE nspname='public'").fetchone()==schema
 assert c.execute('SELECT period,run_id,name,body,sha256 FROM ingestion_run_evidence ORDER BY period,run_id,name').fetchall()==evidence
 assert j.load()==old
 observed=c.execute(query).fetchone()
 assert observed[1:]==definition[1:]
 if mode in ('normal','lost'):
  assert observed[0]==de.ATTEMPT08_OWNER_SQL.split('$owner_state$',2)[1]
  # Readback, not another migration, resolves a lost acknowledgement.
  with w['actor']() as actor:assert p08.inspect(actor,w['binding'])['status']=='DISPOSITION_COMMITTED_VERIFIED'
  nextj=owner_pilot.Journal(db,p08.SUCCESSOR);assert nextj.load() is None
  nextj.save(dict(period=p08.SUCCESSOR,status='PREPARING'))
  assert nextj.load()['status']=='PREPARING' and j.load()==old
 else:assert observed==definition

