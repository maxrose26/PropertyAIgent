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
 b.execute('ALTER ROLE ingestion_storage_owner NOINHERIT')
 from verification.ingestion_storage.oldham_reuse import expected_historical
 class Owner:
  def q(self,c,q,p=None):return c.execute(q,p).fetchall()
 g,a=expected_historical(Owner(),b)
 b.execute('GRANT SELECT (rolname,rolpassword) ON pg_authid TO postgres')
 for role,cap in [('ingestion_worker_login','ingestion_worker'),('ingestion_effect_login','ingestion_effect_broker')]:
  for (grantor,) in b.execute('SELECT grantor::regrole::text FROM pg_auth_members WHERE roleid=%s::regrole AND member=%s::regrole',(cap,role)).fetchall():
   b.execute(psycopg.sql.SQL('REVOKE {} FROM {} GRANTED BY {} CASCADE').format(*map(psycopg.sql.Identifier,(cap,role,grantor))))
  b.execute('GRANT '+cap+' TO postgres WITH ADMIN TRUE, INHERIT FALSE, SET FALSE')
  b.execute('GRANT '+cap+' TO '+role+' WITH ADMIN FALSE, INHERIT TRUE, SET FALSE GRANTED BY postgres')
  b.execute('ALTER ROLE '+role+' NOLOGIN PASSWORD NULL')
 row=a['package']['registration']['rows'][0]
 b.execute('INSERT INTO public.ingestion_work_items SELECT (jsonb_populate_record(NULL::public.ingestion_work_items,%s::jsonb)).*',(json.dumps(row),))
 ctl=b.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
 ctl.setdefault('grants',{})['SYNTHETIC_UNRELATED']={'expires_at':0,'retained':True};ctl['grants'][A]=g;ctl.setdefault('oldham_allowances',{})[A]=a
 b.execute("UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),))
 return seeded

def snap(b):
 return (m.snapshot(b),b.execute('SELECT jsonb_agg(to_jsonb(x) ORDER BY roleid,member,grantor) FROM pg_auth_members x').fetchone()[0])

def run(sql=SQL):
 with m.actor() as c:
  try:m.execute(c,sql)
  except BaseException:c.execute('ROLLBACK');raise

def test_exact_cleanup_and_preserved_stops_history_functions_schema(baseline,record_property):
 b=baseline['boot'];before=snap(b);ctl=b.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
 run();after=snap(b)
 expected=copy.deepcopy(ctl);expected['grants'][A]['expires_at']=0;expected['oldham_allowances'][A]['revoked']=True
 assert b.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]==expected
 assert after[0][0]==before[0][0] and after[0][2]==before[0][2] and after[0][4]==before[0][4]
 assert m.actor_flags()==(False,False,False)
 assert not b.execute("SELECT 1 FROM pg_auth_members WHERE (roleid='ingestion_worker'::regrole AND member='ingestion_worker_login'::regrole) OR (roleid='ingestion_effect_broker'::regrole AND member='ingestion_effect_login'::regrole)").fetchall()
 record_property('server_version',baseline['server_version']);record_property('installer_superuser',False)

@pytest.mark.parametrize('fault,code',[
 ('stop', 'CLEANUP_CURRENT_STOP_DRIFT'),('authority','CLEANUP_HISTORICAL_BINDING_OR_EXPIRY'),('work','CLEANUP_HISTORICAL_WORK_DRIFT'),('grantor','CLEANUP_TARGET_GRANTOR_OR_ADMIN'),('login','CLEANUP_LOGIN_STATE'),('password','CLEANUP_PASSWORD_PRESENCE'),('owner_set','CLEANUP_OWNER_BASELINE'),('owner_flags','CLEANUP_ROLE_FLAGS')])
def test_drift_refuses_without_change(baseline,fault,code):
 b=baseline['boot']
 q={'stop':"UPDATE ingestion_work_items SET outcome=jsonb_set(outcome::jsonb,'{hard_stop_generation}','6')::json WHERE key=repeat('0',64)",
 'authority':"UPDATE ingestion_work_items SET outcome=jsonb_set(outcome::jsonb,ARRAY['grants','"+A+"','writes'],'1')::json WHERE key=repeat('0',64)",
 'work':"UPDATE ingestion_work_items SET attempt_count=1 WHERE key='abf1b6f7e9c8119a74e2f8f3d2bdec0a4b2da3a5eee8768a2783614755aa26cf'",
 'grantor':'REVOKE ingestion_worker FROM ingestion_worker_login GRANTED BY postgres; GRANT ingestion_worker TO ingestion_worker_login WITH ADMIN FALSE, INHERIT TRUE, SET FALSE',
 'login':'ALTER ROLE ingestion_worker_login LOGIN',
 'password':"ALTER ROLE ingestion_worker_login PASSWORD 'synthetic_only'",
 'owner_flags':'ALTER ROLE ingestion_storage_owner INHERIT',
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
 code={'after_update':'division by zero','after_first_revoke':'division by zero','missing_temp_cleanup':'CLEANUP_MEMBERSHIP_POST','extra_authority_change':'CLEANUP_LEDGER_POST'}[point]
 with pytest.raises(psycopg.Error,match=code):run(s)
 assert snap(b)==before

def test_second_attempt_refused_no_retry(baseline):
 run();b=baseline['boot'];before=snap(b)
 with pytest.raises(psycopg.Error):run()
 assert snap(b)==before


@pytest.mark.parametrize('mode',['ack','no_ack','error','overflow','deadline'])
def test_cleanup_client_marker_bounds_secret_removal(tmp_path,monkeypatch,mode):
 spec=importlib.util.spec_from_file_location('cleanup_client',P/'oldham-cleanup-client.py');client=importlib.util.module_from_spec(spec);spec.loader.exec_module(client)
 ca=tmp_path/'ca';ca.write_text('synthetic');out=tmp_path/'evidence'
 answers=iter(['18.135.253.94',str(ca),'postgres',str(out)])
 monkeypatch.setattr('builtins.input',lambda _:next(answers));monkeypatch.setattr(client.getpass,'getpass',lambda _:'SYNTHETIC_PASSWORD_SENTINEL');monkeypatch.setattr(client.shutil,'which',lambda _:'/usr/bin/psql')
 seen={}
 def capture(cmd,env,**kw):
  seen.update(env);assert env['PGSSLMODE']=='verify-full' and kw['ceiling']==64512
  assert 'SYNTHETIC_PASSWORD_SENTINEL' not in repr(cmd)+repr(env)
  assert Path(env['PGPASSFILE']).stat().st_mode&0o777==0o600
  data=b'COMMIT\ndisposition\nOLDHAM_CLEANUP_COMMIT_ACKNOWLEDGED\n' if mode=='ack' else b'fixture\n'
  return data,dict(exit_code=1 if mode=='error' else 0,reason=mode.upper() if mode in ('overflow','deadline') else None,client_closed=True,output_bytes=len(data),remote_closure='LOCAL_FIXTURE_ONLY')
 monkeypatch.setattr(client,'capture',capture)
 code=client.main();status=json.loads((out/'status.json').read_text())
 assert code==(0 if mode=='ack' else 2)
 assert status['transaction_outcome']==('COMMIT_ACKNOWLEDGED' if mode=='ack' else 'UNKNOWN_RECONCILE_NO_RETRY')
 assert status['classification']==('CLEANUP_REQUIRES_REVIEW' if mode=='ack' else 'INCOMPLETE')
 assert not Path(seen['PGPASSFILE']).exists()
 assert sum(x.stat().st_size for x in out.iterdir())<=65536
 assert 'SYNTHETIC_PASSWORD_SENTINEL' not in ''.join(x.read_text() for x in out.iterdir())


def test_builder_runner_and_unchanged_capture_bindings():
 import ast
 assert subprocess.check_output([sys.executable,'-B',str(P/'build_cleanup.py')],text=True)==SQL
 block=(P/'RUN-INACTIVE.sh').read_text().split("<<'PY'\n",1)[1].split('\nPY\n',1)[0]
 result=subprocess.run([sys.executable,'-I','-S','-',str(ROOT),str(P)],input=block,text=True,capture_output=True,check=True)
 assert 'NO_DATABASE_CONNECTION_YET' in result.stdout
 source=ROOT/'docs/design/daily-intake-20261029/b-readonly-client.py'
 pick=lambda f:next(x for x in ast.parse(f.read_text()).body if isinstance(x,ast.FunctionDef) and x.name=='capture')
 assert ast.dump(pick(source))==ast.dump(pick(P/'oldham-cleanup-client.py'))
