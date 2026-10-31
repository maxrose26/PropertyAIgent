"""Only NEW cleanup cases. Existing installation suite is imported for fixtures, never collected."""
from pathlib import Path
import importlib.util,sys,os,json,copy,time,hashlib,subprocess
import pytest,psycopg
ROOT=Path.cwd();P=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('retained_install_fixture',ROOT/'docs/design/bolton-intake-install-20261031/test_install_package.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
world=m.world
seeded=m.seeded
SQL=(P/'oldham-cleanup.sql').read_text()
A='INGESTION_CHAIN_OLDHAM_STAGED_CAPTURE_E9D12874CFB5'

@pytest.fixture
def baseline(seeded):
 b=seeded['boot']
 from verification.ingestion_storage.oldham_reuse import expected_historical
 class Owner:
  def q(self,c,q,p=None):return c.execute(q,p).fetchall()
 g,a=expected_historical(Owner(),b)
 b.execute('GRANT SELECT (rolname,rolpassword) ON pg_authid TO postgres')
 for role,cap in [('ingestion_worker_login','ingestion_worker'),('ingestion_effect_login','ingestion_effect_broker')]:
  b.execute('REVOKE '+cap+' FROM '+role+' CASCADE')
  b.execute('GRANT '+cap+' TO postgres WITH ADMIN TRUE, INHERIT FALSE, SET FALSE')
  b.execute('GRANT '+cap+' TO '+role+' WITH ADMIN FALSE, INHERIT TRUE, SET FALSE GRANTED BY postgres')
  b.execute('ALTER ROLE '+role+' NOLOGIN PASSWORD NULL')
 row=a['package']['registration']['rows'][0]
 b.execute('INSERT INTO public.ingestion_work_items SELECT (jsonb_populate_record(NULL::public.ingestion_work_items,%s::jsonb)).*',(json.dumps(row),))
 ctl=b.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
 ctl.setdefault('grants',{})[A]=g;ctl.setdefault('oldham_allowances',{})[A]=a
 b.execute("UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),))
 return seeded

def snap(b):
 return (m.snapshot(b),b.execute('SELECT jsonb_agg(to_jsonb(x) ORDER BY roleid,member,grantor) FROM pg_auth_members x').fetchone()[0])

def run(sql=SQL):
 with m.actor() as c:
  try:m.execute(c,sql)
  except BaseException:c.execute('ROLLBACK');raise

def test_exact_cleanup_and_preserved_stops_history_functions_schema(baseline,record_property):
 b=baseline['boot'];before=snap(b);ctl=copy.deepcopy(before[0][3]['items'][0]['outcome']) if False else b.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
 run();after=snap(b)
 expected=copy.deepcopy(ctl);expected['grants'][A]['expires_at']=0;expected['oldham_allowances'][A]['revoked']=True
 assert b.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]==expected
 assert after[0][0]==before[0][0] and after[0][2]==before[0][2] and after[0][4]==before[0][4]
 assert m.actor_flags()==(False,False,False)
 assert not b.execute("SELECT 1 FROM pg_auth_members WHERE (roleid='ingestion_worker'::regrole AND member='ingestion_worker_login'::regrole) OR (roleid='ingestion_effect_broker'::regrole AND member='ingestion_effect_login'::regrole)").fetchall()
 record_property('server_version',baseline['server_version']);record_property('installer_superuser',False)

@pytest.mark.parametrize('fault,code',[
 ('stop', 'CLEANUP_CURRENT_STOP_DRIFT'),('authority','CLEANUP_HISTORICAL_BINDING_OR_EXPIRY'),('work','CLEANUP_HISTORICAL_WORK_DRIFT'),('grantor','CLEANUP_TARGET_GRANTOR_OR_ADMIN'),('login','CLEANUP_LOGIN_STATE'),('password','CLEANUP_PASSWORD_PRESENCE'),('owner_set','CLEANUP_OWNER_BASELINE')])
def test_drift_refuses_without_change(baseline,fault,code):
 b=baseline['boot']
 q={'stop':"UPDATE ingestion_work_items SET outcome=jsonb_set(outcome::jsonb,'{hard_stop_generation}','6')::json WHERE key=repeat('0',64)",
 'authority':"UPDATE ingestion_work_items SET outcome=jsonb_set(outcome::jsonb,ARRAY['grants','"+A+"','writes'],'1')::json WHERE key=repeat('0',64)",
 'work':"UPDATE ingestion_work_items SET attempt_count=1 WHERE key='abf1b6f7e9c8119a74e2f8f3d2bdec0a4b2da3a5eee8768a2783614755aa26cf'",
 'grantor':'REVOKE ingestion_worker FROM ingestion_worker_login GRANTED BY postgres; GRANT ingestion_worker TO ingestion_worker_login WITH ADMIN FALSE, INHERIT TRUE, SET FALSE',
 'login':'ALTER ROLE ingestion_worker_login LOGIN',
 'password':"ALTER ROLE ingestion_worker_login PASSWORD 'synthetic_only'",
 'owner_set':'GRANT ingestion_storage_owner TO postgres WITH ADMIN FALSE, INHERIT FALSE, SET TRUE GRANTED BY postgres'}[fault]
 b.execute(q);before=snap(b)
 with pytest.raises(psycopg.Error,match=code):run()
 assert snap(b)==before

@pytest.mark.parametrize('point',['after_update','after_first_revoke','missing_temp_cleanup','extra_authority_change'])
def test_midtransaction_failures_rollback_every_effect(baseline,point):
 b=baseline['boot'];before=snap(b)
 if point=='after_update':s=SQL.replace('RESET ROLE;','RESET ROLE; SELECT 1/0;')
 elif point=='after_first_revoke':s=SQL.replace('REVOKE ingestion_effect_broker','SELECT 1/0; REVOKE ingestion_effect_broker')
 elif point=='missing_temp_cleanup':s=SQL.replace('REVOKE ingestion_storage_owner FROM postgres GRANTED BY postgres RESTRICT;','')
 else:s=SQL.replace('RESET ROLE;',"UPDATE public.ingestion_work_items SET outcome=jsonb_set(outcome::jsonb,'{hard_stop_generation}','6')::json WHERE key=repeat('0',64); RESET ROLE;")
 with pytest.raises(psycopg.Error):run(s)
 assert snap(b)==before

def test_second_attempt_refused_no_retry(baseline):
 run();b=baseline['boot'];before=snap(b)
 with pytest.raises(psycopg.Error):run()
 assert snap(b)==before
