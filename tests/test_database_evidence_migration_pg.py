"""Exact migration on existing non-superuser production-shaped PG17 fixture."""
import pytest
from tests.test_intake_owner_finite import installed,world,support,accepted
from verification.ingestion_storage import intake_owner as op
from verification.ingestion_storage.database_evidence import migration_sql

@pytest.fixture
def migration_world(installed):
 accepted(installed)
 yield installed
 b=installed['boot']
 b.execute('DROP FUNCTION IF EXISTS ingestion_intake_evidence_write(text,text,text,bytea)')
 b.execute('DROP FUNCTION IF EXISTS ingestion_intake_evidence_read(text,text,text)')
 b.execute('DROP FUNCTION IF EXISTS ingestion_intake_owner_state(text,text,text,bytea)')
 b.execute('DROP TABLE IF EXISTS ingestion_run_evidence')

@pytest.mark.parametrize('mode',['success','late_failure','wrong_predecessor'])
def test_exact_atomic_migration_cleanup_and_predecessor(migration_world,mode,record_property):
 w=migration_world;b=w['boot'];before=op.ledger_sha(b);members=b.execute(op.MEMBERS).fetchall()
 sql=migration_sql()
 if mode=='late_failure':sql=sql.replace('DO $post$', 'SELECT 1/0;\nDO $post$',1)
 if mode=='wrong_predecessor':sql=sql.replace('dba6b809c50b9bd937b2f509fc05c20de9d69499ca4394e9007ef3af196b481c','0'*64,1)
 with support.actor() as c:
  assert c.execute('SELECT rolsuper FROM pg_roles WHERE rolname=current_user').fetchone()==(False,)
  if mode=='success':support.execute(c,sql)
  else:
   with pytest.raises(Exception) as failure:support.execute(c,sql)
   assert getattr(failure.value,'sqlstate',None)==('22012' if mode=='late_failure' else 'P0001')
   c.execute('ROLLBACK')
 assert op.ledger_sha(b)==before and b.execute(op.MEMBERS).fetchall()==members
 assert support.actor_flags()==(False,False,False)
 assert (b.execute("SELECT to_regclass('public.ingestion_run_evidence')").fetchone()[0] is not None)==(mode=='success')
 if mode=='success':
  from verification.ingestion_storage.database_evidence import verify_inventory
  with support.actor() as c:op.inventory(c);verify_inventory(c)
  assert b.execute("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid='public.ingestion_run_evidence'::regclass").fetchone()==(True,True)
 record_property('server_version',w['server_version']);record_property('actor_superuser',False)

def test_pg17_database_pilot_existing_period_activation_and_independent_close(migration_world,monkeypatch,record_property):
 import copy,json,time
 from verification.ingestion_storage import owner_pilot as p,intake_owner_operations as extra
 w=migration_world;boot=w['boot']
 with support.actor() as c:support.execute(c,migration_sql())
 boot.execute('GRANT ingestion_barrier_releaser TO postgres WITH ADMIN TRUE,INHERIT FALSE,SET FALSE GRANTED BY provisioning_bootstrap')
 e={'revision':'1'*40,'workflow_sha256':'2'*64,'manifest_sha256':'3'*64}
 release={'execution_binding':e,'deployment':'dep-'+'a'*20};monkeypatch.setenv('PROPERTYAIGENT_INTAKE_SOURCE_RELEASE',json.dumps(release))
 profile=p.source_profile({'execution_binding':e,'browser_canary':'LAUNCHED_AND_CLOSED','browser_path':'/fixture/browser','browser_sha256':'a'*64},e['revision'])
 b,policy=p.fixed_binding(release,profile,'192.0.2.1','a'*64);before=boot.execute(op.MEMBERS).fetchall();prior=op.settings(boot)
 from contextlib import contextmanager
 class DB:
  key='b'*64
  @contextmanager
  def connection(self):
   with support.actor() as conn:yield conn
 durable=p.Journal(DB());owner_state={'period':p.PERIOD,'status':'PERIOD_INTENT','intents':{'PERIOD':'INTENT_NO_RETRY'}};durable.save(owner_state)
 journal={'version':'FINITE_INTAKE_PERIOD_V1','state':'ARMED_NO_RETRY','binding':b,'policy':policy};saved=[]
 with support.actor() as c:
  def period_saved(value):
   saved.append(copy.deepcopy(value));owner_state['period_journal']=copy.deepcopy(value)
   if value.get('state')=='COMMIT_ACKNOWLEDGED':durable.save(owner_state,connection=c)
  receipt=extra.issue_period(c,b,policy,journal,period_saved)
 assert receipt['temporary_issuer']=='REMOVED' and boot.execute(op.MEMBERS).fetchall()==before
 states=[]
 with support.actor() as c:
  prepared=op.prepare_activation(c,b);owner_state['access']=copy.deepcopy(prepared);durable.save(owner_state,connection=c)
  def activated(value):
   states.append(copy.deepcopy(value));owner_state['access']=copy.deepcopy(value)
   if value.get('state')=='ACTIVATION_ACKNOWLEDGED':durable.save(owner_state,connection=c)
  op.activate(c,b,activated,prepared=prepared)
 assert states[-1]['state']=='ACTIVATION_ACKNOWLEDGED'
 with support.actor() as c:
  def closure_saved(value):
   states.append(copy.deepcopy(value));owner_state['access']=copy.deepcopy(value);durable.save(owner_state,connection=c)
  closed=op.close(c,states[-1],closure_saved)
 assert closed['runtime_access']=='DISABLED' and closed['temporary_owner']=='REMOVED' and closed['sessions']=='ABSENT'
 assert boot.execute(op.MEMBERS).fetchall()==before and op.settings(boot)==prior
 assert op.control(boot)['intake_periods'][p.PERIOD]['access_deadline']==b['valid_until']
 assert op.stop_snapshot(op.control(boot))==op.ACCEPTED_STOP
 assert durable.load()['access']['state']=='DATABASE_CLOSURE_ACKNOWLEDGED'
 record_property('actor_superuser',False);record_property('postgres_version',w['server_version'])

def test_pg17_owner_state_append_compare_and_swap_and_runtime_denial(migration_world):
 import hashlib
 from verification.ingestion_storage import owner_pilot as p
 w=migration_world;boot=w['boot']
 with support.actor() as c:
  support.execute(c,migration_sql())
  q='SELECT * FROM ingestion_intake_owner_state(%s,%s,%s,%s)'
  assert c.execute(q,(p.OWNER_PERIOD,p.OWNER_RUN,'',None)).fetchall()==[]
  one=c.execute(q,(p.OWNER_PERIOD,p.OWNER_RUN,'',b'ENCRYPTED_FIXTURE_ONLY')).fetchone()
  assert one[0]==0 and bytes(one[1])==b'ENCRYPTED_FIXTURE_ONLY' and one[2]==hashlib.sha256(bytes(one[1])).hexdigest()
  assert c.execute(q,(p.OWNER_PERIOD,p.OWNER_RUN,'',b'ENCRYPTED_FIXTURE_ONLY')).fetchone()==one
  with pytest.raises(Exception,match='CONCURRENT'):c.execute(q,(p.OWNER_PERIOD,p.OWNER_RUN,'',b'CONFLICT'))
  two=c.execute(q,(p.OWNER_PERIOD,p.OWNER_RUN,one[2],b'ENCRYPTED_SECOND')).fetchone();assert two[0]==1
  assert c.execute(q,(p.OWNER_PERIOD,p.OWNER_RUN,'',None)).fetchone()==two
  with pytest.raises(Exception,match='EXACT_PILOT'):c.execute(q,('other',p.OWNER_RUN,'',None))
  with pytest.raises(Exception,match='VAULT_BOUND'):c.execute(q,(p.OWNER_PERIOD,p.OWNER_RUN,two[2],b'x'*32769))
 for role in op.ROLES:
  assert boot.execute("SELECT has_function_privilege(%s,'ingestion_intake_owner_state(text,text,text,bytea)','EXECUTE')",(op.ROLES[role],)).fetchone()==(False,)
 assert boot.execute('SELECT count(*) FROM ingestion_run_evidence').fetchone()==(2,)
