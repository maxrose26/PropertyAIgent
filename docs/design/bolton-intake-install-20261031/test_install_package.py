"""Guarded Bolton daily-intake function installation, exercised ONLY in a disposable server.

Actor: NON-superuser `postgres` with the OBSERVED production baseline (BYPASSRLS, CREATEROLE, CREATEDB, pg_read_all_stats, SELECT but no UPDATE on the ledger tables, an ADMIN-only distinct-grantor membership
on ingestion_storage_owner, schema-public CREATE grant option, NO owner SET). The installed predecessor is the recognised Oldham-worker state (bodies verified against the production-observed hashes).
Synthetic setup (grantors, fixture ledger rows, passwords) is test bootstrap only and is NOT a production fact. No production host is contacted."""
import copy,json,os,subprocess,sys,time,hashlib,ast,difflib,re,shutil
from pathlib import Path
import psycopg
import pytest

PKG=Path(__file__).resolve().parent
FIXTURE_REPO=os.environ.get('RECOVERY_TEST_REPO',str(Path.cwd()))      # exact published PR206 base; no PR205 imports
REPO206=Path(os.environ.get('PR206_CHECKOUT',FIXTURE_REPO))
TRUST=Path(os.environ.get('TRUST_CHECKOUT',FIXTURE_REPO))
PYTHON=os.environ.get('GENERATOR_PYTHON',sys.executable)
sys.path.insert(0,FIXTURE_REPO)
from tests.e2e_pg_world import disposable_world
FIXTURE_PASSWORD='disposable_fixture_only';PGENV=dict(os.environ,PGPASSWORD=FIXTURE_PASSWORD)
PGBIN=os.environ.get('PG_BIN',str(Path(shutil.which('psql') or '/usr/bin/psql').parent))
FIXTURE_CONTAINER=os.environ.get('BOLTON_TEST_PG_CONTAINER')
def pg_tool(name):
 return ['docker','exec','-i','-e','PGPASSWORD',FIXTURE_CONTAINER,name] if FIXTURE_CONTAINER else [str(Path(PGBIN)/name)]
SQL=(PKG/'bolton-intake-install.sql').read_text()
PRED=dict(ingestion_bolton_allowed='961c1e1c441372a6c4fb4606d0f5b973a14dbb7e1fa390740789a4d4de2fe8bf',ingestion_register_bolton_exception='b5ce45dcaa4183b2f828dfb6383a0dde838d0b5365206ba406f8854f7bc0b3cd',ingestion_worker_step='79324a92b380de621e595470318f725cf64dbc1ac9c332591363cb70161ca912')
CAND=dict(ingestion_bolton_allowed='09d3e0e8e87bbf158bb89cb683063a21e5e8c23076d342961d49b50ac7e60569',ingestion_register_bolton_exception='dba6b809c50b9bd937b2f509fc05c20de9d69499ca4394e9007ef3af196b481c',ingestion_worker_step='abb46082f6d0891e131271a2567d45d8afdeccfd4561a6692baece7c3759c5bf')
UNCH=dict(ingestion_acceptance_control='f25822db425df0c125df975d1cb46cfc710b76999744304d45d7037292d77d17',ingestion_raise_stop='5e41868876be6c533a31a8f7af25442ce308cb42681210296d516f361521e53a',
          ingestion_recover_abandoned='9e7f98210c737d6f8f7fae2d98e328261ab9faf31481f041b6f63befa6686f58',ingestion_oldham_allowed='091ec5ee578083b0b64431542ec02ff8a39263d345dee6a360dde68d3622900a')
ALL7=sorted({**PRED,**UNCH})
KEYS=['3f0dba235de9b9efcd52ef3b281ba8c967491f57824404c695ed2b32fae4c045','e92a8e220bbbbcefb2425d6f97a60920bc447bc1fe097d600ea28e3e9d87588e']
AUTH=['AUTHORISE_INGESTION_BOLTON_CAPTURE_ACCEPTANCE_ONCE_20261022_CAPTURE','AUTHORISE_INGESTION_STABLE_PIPELINE_AUTHORITY_ONCE_20261020_CAPTURE']
SIG={'ingestion_oldham_allowed':'public.ingestion_oldham_allowed(jsonb,text,text,jsonb)','ingestion_raise_stop':'public.ingestion_raise_stop(text)','ingestion_recover_abandoned':'public.ingestion_recover_abandoned(text,integer,boolean)','ingestion_acceptance_control':'public.ingestion_acceptance_control()',
     'ingestion_bolton_allowed':'public.ingestion_bolton_allowed(jsonb,text,jsonb)','ingestion_register_bolton_exception':'public.ingestion_register_bolton_exception(jsonb)',
     'ingestion_worker_step':'public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)'}


def mutate(sql,old,new,count=1):
 assert sql.count(old)==count,(old[:70],sql.count(old))
 return sql.replace(old,new)


def body_sha(b,name):
 return b.execute("SELECT encode(sha256(convert_to(prosrc,'UTF8')),'hex') FROM pg_proc WHERE proname=%s AND pronamespace='public'::regnamespace",(name,)).fetchone()[0]


@pytest.fixture(scope='module')
def world():
 from verification.ingestion_storage.operational_owner import PKG as OPKG,GENERATION3_SCREENING_V3_POLICY
 from verification.ingestion_storage import oldham_policy
 for w in disposable_world():
  if os.environ.get('BOLTON_REQUIRE_PG17')=='1':assert 170000<=w['server_version']<180000, 'EXACT_POSTGRES_17_REQUIRED'
  original=w['boot']
  with w['connect']('provisioning_migrator') as c:      # recognised Oldham-worker predecessor, built from the repository's reviewed generators
   c.execute((OPKG/'successor-policy.sql').read_text());c.execute(GENERATION3_SCREENING_V3_POLICY.read_text());c.execute(oldham_policy.installation_script())
  dump=subprocess.run(pg_tool('pg_dump')+['-h','127.0.0.1','-U','provisioning_bootstrap','-d','ingestion_provisioning_test'],capture_output=True,check=True,env=PGENV).stdout
  subprocess.run(pg_tool('psql')+['-X','-v','ON_ERROR_STOP=1','-h','127.0.0.1','-U','provisioning_bootstrap','-d','postgres'],input=dump,capture_output=True,check=True,env=PGENV)
  b=psycopg.connect(host='127.0.0.1',port=5432,dbname='postgres',user='provisioning_bootstrap',password=FIXTURE_PASSWORD,autocommit=True)
  w['boot']=b
  assert {n:body_sha(b,n) for n in PRED}==PRED and {n:body_sha(b,n) for n in UNCH}==UNCH      # the fixture really is the recognised predecessor state
  w['predecessor_defs']={n:b.execute('SELECT pg_get_functiondef(%s::regprocedure)',(SIG[n],)).fetchone()[0] for n in ALL7}      # all seven, so every test starts from the same recognised state
  w['owners']={n:b.execute('SELECT pg_get_userbyid(proowner) FROM pg_proc WHERE oid=%s::regprocedure',(SIG[n],)).fetchone()[0] for n in ALL7}
  b.execute("CREATE ROLE postgres LOGIN NOSUPERUSER BYPASSRLS CREATEROLE CREATEDB INHERIT PASSWORD 'disposable_actor_password'")
  b.execute('GRANT USAGE ON SCHEMA public TO postgres WITH GRANT OPTION');b.execute('GRANT CREATE ON SCHEMA public TO postgres WITH GRANT OPTION')      # observed schema grant options
  b.execute('GRANT SELECT ON ingestion_work_items,ingestion_work_attempts TO postgres');b.execute('GRANT pg_read_all_stats,pg_signal_backend TO postgres')
  try:yield w
  finally:
   b.execute('DROP OWNED BY postgres CASCADE');b.execute('DROP ROLE postgres')
   b.execute('DROP SCHEMA public CASCADE;CREATE SCHEMA public')
   for (name,) in b.execute("SELECT rolname FROM pg_roles WHERE rolname LIKE 'ingestion_%' OR rolname='provisioning_migrator'").fetchall():
    b.execute(psycopg.sql.SQL('DROP OWNED BY {} CASCADE').format(psycopg.sql.Identifier(name)))
   b.close();w['boot']=original


@pytest.fixture
def seeded(world):
 b=world['boot']
 for n,d in world['predecessor_defs'].items():
  b.execute(d);b.execute('ALTER FUNCTION '+SIG[n]+' OWNER TO '+world['owners'][n])      # restore every definition, owner and configuration (superuser)
  b.execute('ALTER FUNCTION '+SIG[n]+' '+('SECURITY DEFINER' if n!='ingestion_bolton_allowed' else 'SECURITY INVOKER'))
 for n in PRED:b.execute('REVOKE EXECUTE ON FUNCTION '+SIG[n]+' FROM PUBLIC')
 b.execute('REVOKE EXECUTE ON FUNCTION public.ingestion_register_bolton_exception(jsonb) FROM ingestion_worker,ingestion_effect_broker')
 b.execute('REVOKE EXECUTE ON FUNCTION public.ingestion_bolton_allowed(jsonb,text,jsonb) FROM ingestion_worker,ingestion_effect_broker')
 b.execute('REVOKE ingestion_storage_owner FROM postgres CASCADE');b.execute('REVOKE CREATE ON SCHEMA public FROM ingestion_storage_owner')
 b.execute('GRANT ingestion_storage_owner TO postgres WITH ADMIN TRUE, INHERIT FALSE, SET FALSE GRANTED BY provisioning_bootstrap')      # OBSERVED: admin-only, distinct grantor
 b.execute('DELETE FROM ingestion_work_attempts');b.execute("DELETE FROM ingestion_work_items WHERE key<>repeat('0',64)")
 ctl=copy.deepcopy(world['control']);ctl.update(global_stop={'run':'38884069913','reason':'CONSUMED_SALFORD_GLOBAL_STOP'},manual_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP',last_hard_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP',hard_stop_generation=5)
 b.execute("UPDATE ingestion_work_items SET outcome=%s WHERE key=repeat('0',64)",(json.dumps(ctl),))
 for key,authority in zip(KEYS,AUTH):      # the committed recovery's end state, seeded directly (synthetic)
  patch=dict(key=key,task='DISCOVERY',state='SAFETY_BLOCKED',phase='RECOVERED',fence=2,owner=None,authority=authority,lease_until=None,attempt_count=1,checkpoint=None,reason='ABANDONED_SOURCE_INTENT',next_action='RECONCILE',
             outcome=json.dumps(dict(outcome='ABANDONED_SOURCE_INTENT',source_or_write_replay_authorised=False)))
  b.execute("INSERT INTO ingestion_work_items SELECT (jsonb_populate_record(NULL::ingestion_work_items,to_jsonb(t)||%s::jsonb)).* FROM ingestion_work_items t WHERE key=repeat('0',64)",(json.dumps(patch),))
  b.execute("INSERT INTO ingestion_work_attempts(work_key,fence,owner,started_at,finished_at,authority,phase,outcome) VALUES(%s,1,'required_once',%s,%s,%s,'RECOVERED',%s)",(key,time.time()-200,time.time()-100,authority,json.dumps(dict(outcome='ABANDONED_SOURCE_INTENT',source_or_write_replay_authorised=False))))
 assert {n:body_sha(b,n) for n in PRED}==PRED
 return world


def snapshot(b):
 """Everything the installation may touch or must leave alone."""
 fn=b.execute("""SELECT jsonb_object_agg(p.proname,jsonb_build_array(encode(sha256(convert_to(p.prosrc,'UTF8')),'hex'),pg_get_userbyid(p.proowner),p.proconfig,p.prosecdef,p.provolatile::text,
   (SELECT coalesce(jsonb_agg(jsonb_build_array(x.grantor::regrole::text,x.grantee,x.privilege_type,x.is_grantable) ORDER BY x.grantor,x.grantee,x.privilege_type),'[]'::jsonb) FROM aclexplode(p.proacl) x)))
   FROM pg_proc p WHERE p.pronamespace='public'::regnamespace AND p.proname LIKE 'ingestion\\_%'""").fetchone()[0]
 q=["SELECT jsonb_agg(to_jsonb(m) ORDER BY roleid,grantor) FROM pg_auth_members m WHERE member='postgres'::regrole",
    "SELECT coalesce(jsonb_agg(jsonb_build_array(x.grantor::regrole::text,x.grantee,x.privilege_type,x.is_grantable) ORDER BY x.grantor,x.grantee,x.privilege_type),'[]'::jsonb) FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) x WHERE n.oid='public'::regnamespace",
    "SELECT jsonb_build_object('items',(SELECT coalesce(jsonb_agg(to_jsonb(w) ORDER BY w.key),'[]') FROM ingestion_work_items w),'attempts',(SELECT coalesce(jsonb_agg(to_jsonb(a) ORDER BY a.work_key,a.fence),'[]') FROM ingestion_work_attempts a))",
    "SELECT jsonb_agg(jsonb_build_array(rolname,rolsuper,rolcreaterole,rolcreatedb,rolbypassrls,rolinherit,rolcanlogin) ORDER BY rolname) FROM pg_roles WHERE rolname IN ('postgres','ingestion_storage_owner','ingestion_worker','ingestion_worker_login','ingestion_effect_login')"]
 return (fn,)+tuple(b.execute(x).fetchone()[0] for x in q)


def actor():return psycopg.connect(host='127.0.0.1',port=5432,dbname='postgres',user='postgres',password='disposable_actor_password',autocommit=True,prepare_threshold=None)


def execute(c,sql=SQL):
 c.execute(sql)
 while c.pgconn.get_result() is not None:pass


def actor_flags():
 with actor() as c:return c.execute("SELECT pg_has_role(current_user,'ingestion_storage_owner','SET'),pg_has_role(current_user,'ingestion_storage_owner','USAGE'),has_schema_privilege('ingestion_storage_owner','public','CREATE')").fetchone()


def refuses(b,code,sql=SQL,bodies=None):
 before=snapshot(b)
 flags=lambda:actor_flags()
 flags_before=flags()
 with actor() as c:
  with pytest.raises(psycopg.Error,match=code):execute(c,sql)
  c.execute('ROLLBACK')
 assert snapshot(b)==before and flags()==flags_before      # the actor's effective owner SET and the owner's schema CREATE are exactly as before the attempt      # definitions, ACLs, every membership, schema ACL, ledger/stop and role flags exactly as before
 if bodies is not None:assert {n:body_sha(b,n) for n in bodies}==bodies      # definitions as they were before the attempt (the full snapshot comparison above already covers every function)


def run_py_in_206(code):
 return subprocess.run([PYTHON,'-I','-B','-c',code],cwd=REPO206,capture_output=True,text=True,check=True,env={'PATH':'/usr/bin:/bin','HOME':str(Path.home())}).stdout


# --- the package is the existing generator's output plus guards -------------------------------------------------------------------------------------------------------------------------------
def test_sql_is_reproduced_exactly_by_the_builder_from_the_pr206_generator():
 out=subprocess.run([PYTHON,'-I','-B',str(PKG/'generate_installation.py'),str(REPO206)],capture_output=True,text=True,check=True,env={'PATH':'/usr/bin:/bin','HOME':str(Path.home())}).stdout
 assert out==SQL


def test_generator_statements_are_embedded_verbatim_and_the_ceremony_is_only_narrowed():
 script=run_py_in_206("import sys;sys.path.insert(0,'.');from verification.ingestion_storage import intake_policy as ip;sys.stdout.write(ip.installation_script())")
 open_=script[:script.index('SET LOCAL ROLE ingestion_storage_owner;\n')+len('SET LOCAL ROLE ingestion_storage_owner;\n')];close=script[script.index('RESET ROLE;\n'):]
 middle=script[len(open_):-len(close)]
 assert middle.rstrip('\n') in SQL      # the three CREATE OR REPLACE statements and the one worker EXECUTE grant: byte-identical
 assert 'GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE;' in open_ and 'GRANT ingestion_storage_owner TO postgres WITH ADMIN FALSE, INHERIT FALSE, SET TRUE GRANTED BY postgres;' in SQL
 assert re.search(r'WITH ADMIN FALSE, INHERIT FALSE, SET TRUE',SQL) and 'INHERIT TRUE, SET TRUE' not in SQL      # INHERIT is dropped from the ceremony
 assert SQL.count('GRANT CREATE ON SCHEMA public TO ingestion_storage_owner;')==1 and SQL.count('REVOKE CREATE ON SCHEMA public FROM ingestion_storage_owner;')==1
 assert SQL.count('REVOKE ingestion_storage_owner FROM postgres GRANTED BY postgres;')==1


def test_embedded_function_bodies_are_exactly_the_expected_candidates():
 bodies={m[1]:hashlib.sha256(m[3].encode()).hexdigest() for m in re.finditer(r'CREATE OR REPLACE FUNCTION public\.(\w+)\(.*?\).*?AS \$(\w*)\$(.*?)\$\2\$;',SQL,re.S)}
 assert bodies==CAND


# --- the owner ceremony: what is actually required ----------------------------------------------------------------------------------------------------------------------------------------------
def test_baseline_actor_cannot_replace_a_function_or_set_the_owner_role(seeded):
 with actor() as c:
  assert c.execute("SELECT rolsuper,rolbypassrls,rolcreaterole FROM pg_roles WHERE rolname=current_user").fetchone()==(False,True,True)
  assert c.execute("SELECT pg_has_role(current_user,'ingestion_storage_owner','SET'),pg_has_role(current_user,'ingestion_storage_owner','USAGE')").fetchone()==(False,False)
  with pytest.raises(psycopg.Error):c.execute("CREATE OR REPLACE FUNCTION public.ingestion_bolton_allowed(ctl jsonb, authority text, subject jsonb) RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog AS 'SELECT false'")
 assert body_sha(seeded['boot'],'ingestion_bolton_allowed')==PRED['ingestion_bolton_allowed']


def test_set_without_schema_create_is_insufficient_for_create_or_replace(seeded):
 b=seeded['boot'];before=snapshot(b)
 with actor() as c:
  c.execute('BEGIN');c.execute('GRANT ingestion_storage_owner TO postgres WITH ADMIN FALSE, INHERIT FALSE, SET TRUE GRANTED BY postgres');c.execute('SET LOCAL ROLE ingestion_storage_owner')
  with pytest.raises(psycopg.Error,match='permission denied for schema public') as e:c.execute("CREATE OR REPLACE FUNCTION public.ingestion_bolton_allowed(ctl jsonb, authority text, subject jsonb) RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog AS 'SELECT false'")
  c.execute('ROLLBACK')
 assert snapshot(b)==before


def test_set_and_schema_create_suffice_and_inherit_is_not_needed(seeded):
 b=seeded['boot']
 with actor() as c:
  c.execute('BEGIN');c.execute('GRANT ingestion_storage_owner TO postgres WITH ADMIN FALSE, INHERIT FALSE, SET TRUE GRANTED BY postgres');c.execute('GRANT CREATE ON SCHEMA public TO ingestion_storage_owner');c.execute('SET LOCAL ROLE ingestion_storage_owner')
  c.execute("CREATE OR REPLACE FUNCTION public.ingestion_bolton_allowed(ctl jsonb, authority text, subject jsonb) RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog AS 'SELECT false'")      # works with SET only (INHERIT FALSE)
  c.execute('ROLLBACK')
 assert body_sha(b,'ingestion_bolton_allowed')==PRED['ingestion_bolton_allowed']


def test_inherit_alone_does_not_allow_setting_the_owner_role(seeded):
 with actor() as c:
  c.execute('BEGIN');c.execute('GRANT ingestion_storage_owner TO postgres WITH ADMIN FALSE, INHERIT TRUE, SET FALSE GRANTED BY postgres')
  with pytest.raises(psycopg.Error,match='permission denied to set role'):c.execute('SET LOCAL ROLE ingestion_storage_owner')
  c.execute('ROLLBACK')


# --- exact recognised predecessor -> candidate -----------------------------------------------------------------------------------------------------------------------------------------------------
def test_exact_transition_installs_the_three_candidates_and_nothing_else(seeded):
 b=seeded['boot'];before=snapshot(b)
 with actor() as c:execute(c)
 after=snapshot(b)
 assert {n:body_sha(b,n) for n in CAND}==CAND and {n:body_sha(b,n) for n in UNCH}==UNCH
 fb,fa=before[0],after[0]
 for name in ALL7:
  if name in CAND:assert fa[name][1:5]==fb[name][1:5]      # owner, config, security definer, volatility unchanged
  if name not in CAND:assert fa[name]==fb[name]      # Oldham helper and every other function untouched, ACLs included
 for name in ('ingestion_bolton_allowed','ingestion_worker_step'):assert fa[name][5]==fb[name][5]
 added=[e for e in fa['ingestion_register_bolton_exception'][5] if e not in fb['ingestion_register_bolton_exception'][5]]
 assert len(added)==1 and added[0][2:]==['EXECUTE',False] and len(fa['ingestion_register_bolton_exception'][5])==len(fb['ingestion_register_bolton_exception'][5])+1      # the single worker EXECUTE addition
 assert after[1:]==before[1:]      # memberships (all rows), schema ACL, ledger/stop/recovered items, role flags identical
 with actor() as c:
  assert c.execute("SELECT has_function_privilege('ingestion_worker_login','public.ingestion_register_bolton_exception(jsonb)','EXECUTE'),has_function_privilege('ingestion_effect_login','public.ingestion_register_bolton_exception(jsonb)','EXECUTE'),pg_has_role(current_user,'ingestion_storage_owner','SET'),pg_has_role(current_user,'ingestion_storage_owner','USAGE'),has_schema_privilege('ingestion_storage_owner','public','CREATE')").fetchone()==(True,False,False,False,False)
 assert b.execute('SELECT state,phase,fence FROM ingestion_work_items WHERE key=ANY(%s) ORDER BY key',(KEYS,)).fetchall()==[('SAFETY_BLOCKED','RECOVERED',2)]*2
 assert b.execute("SELECT outcome::jsonb->'hard_stop_generation' FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()==(5,)


def test_candidate_worker_no_longer_calls_the_oldham_helper_but_the_helper_remains(seeded):
 b=seeded['boot']
 assert 'ingestion_oldham_allowed' in b.execute("SELECT prosrc FROM pg_proc WHERE proname='ingestion_worker_step'").fetchone()[0]
 with actor() as c:execute(c)
 assert 'ingestion_oldham_allowed' not in b.execute("SELECT prosrc FROM pg_proc WHERE proname='ingestion_worker_step'").fetchone()[0]
 assert body_sha(b,'ingestion_oldham_allowed')==UNCH['ingestion_oldham_allowed']      # helper present and unchanged


def test_a_second_run_is_refused_as_the_predecessor_is_gone(seeded):
 b=seeded['boot']
 with actor() as c:execute(c)
 refuses(b,'INSTALL_PREDECESSOR_BODY',bodies=CAND)


# --- preflight refusals: nothing changes -------------------------------------------------------------------------------------------------------------------------------------------------------------
def alter(b,sql,undo=None):
 b.execute(sql)
 return undo


REFUSALS=[
 ('body_changed_policy',"CREATE OR REPLACE FUNCTION public.ingestion_bolton_allowed(ctl jsonb, authority text, subject jsonb) RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog AS 'SELECT false'",'INSTALL_PREDECESSOR_BODY'),
 ('overload_added',"CREATE FUNCTION public.ingestion_worker_step(x integer) RETURNS integer LANGUAGE sql AS 'SELECT 1'",'INSTALL_FUNCTION_INVENTORY'),
 ('owner_changed','ALTER FUNCTION public.ingestion_register_bolton_exception(jsonb) OWNER TO provisioning_bootstrap','INSTALL_PREDECESSOR_ATTRIBUTES'),
 ('search_path_changed','ALTER FUNCTION public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb) SET search_path=public','INSTALL_PREDECESSOR_ATTRIBUTES'),
 ('security_changed','ALTER FUNCTION public.ingestion_register_bolton_exception(jsonb) SECURITY INVOKER','INSTALL_PREDECESSOR_ATTRIBUTES'),
 ('volatility_changed','ALTER FUNCTION public.ingestion_bolton_allowed(jsonb,text,jsonb) IMMUTABLE','INSTALL_PREDECESSOR_ATTRIBUTES'),
 ('worker_already_executes_registrar','GRANT EXECUTE ON FUNCTION public.ingestion_register_bolton_exception(jsonb) TO ingestion_worker','INSTALL_PRIOR_FUNCTION_PRIVILEGE'),
 ('public_executes_registrar','GRANT EXECUTE ON FUNCTION public.ingestion_register_bolton_exception(jsonb) TO PUBLIC','INSTALL_PREDECESSOR_ATTRIBUTES'),
 ('effect_executes_policy','GRANT EXECUTE ON FUNCTION public.ingestion_bolton_allowed(jsonb,text,jsonb) TO ingestion_effect_broker','INSTALL_PRIOR_FUNCTION_PRIVILEGE'),
 ('oldham_helper_changed',"CREATE OR REPLACE FUNCTION public.ingestion_oldham_allowed(ctl jsonb, authority text, work_key text, subject jsonb) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS 'SELECT false'",'INSTALL_UNCHANGED_FUNCTION_CHANGED'),
 ('other_function_changed','ALTER FUNCTION public.ingestion_raise_stop(text) SET search_path=public','INSTALL_PREDECESSOR_ATTRIBUTES'),
 ('stop_generation_old',"UPDATE ingestion_work_items SET outcome=(outcome::jsonb||'{\"hard_stop_generation\":3}'::jsonb)::json WHERE key=repeat('0',64)",'INSTALL_STOP_BINDING'),
 ('manual_stop_old',"UPDATE ingestion_work_items SET outcome=(outcome::jsonb||'{\"manual_stop\":\"IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE\"}'::jsonb)::json WHERE key=repeat('0',64)",'INSTALL_STOP_BINDING'),
 ('item_not_recovered',"UPDATE ingestion_work_items SET state='CLAIMED' WHERE key='"+KEYS[0]+"'",'INSTALL_RECOVERED_ITEMS'),
 ('session_present',None,'INSTALL_SESSION_VISIBILITY_OR_ACTIVITY'),
 ('no_owner_membership','REVOKE ingestion_storage_owner FROM postgres CASCADE','INSTALL_OWNER_ADMIN_BASELINE'),
 ('owner_set_already','REVOKE ingestion_storage_owner FROM postgres CASCADE;GRANT ingestion_storage_owner TO postgres WITH ADMIN TRUE, INHERIT FALSE, SET TRUE GRANTED BY provisioning_bootstrap','INSTALL_OWNER_ADMIN_BASELINE'),
 ('admin_option_missing','REVOKE ingestion_storage_owner FROM postgres CASCADE;GRANT ingestion_storage_owner TO postgres WITH ADMIN FALSE, INHERIT FALSE, SET FALSE GRANTED BY provisioning_bootstrap','INSTALL_OWNER_ADMIN_BASELINE'),
 ('preexisting_self_grant','GRANT ingestion_storage_owner TO postgres WITH ADMIN FALSE, INHERIT FALSE, SET FALSE GRANTED BY postgres','INSTALL_OWNER_ADMIN_BASELINE'),
 ('owner_already_has_schema_create','GRANT CREATE ON SCHEMA public TO ingestion_storage_owner','INSTALL_SCHEMA_BASELINE'),
 ('no_schema_create_grant_option','REVOKE CREATE ON SCHEMA public FROM postgres CASCADE;GRANT CREATE ON SCHEMA public TO postgres','INSTALL_SCHEMA_BASELINE'),
 ('owner_role_state','ALTER ROLE ingestion_storage_owner CREATEDB','INSTALL_OWNER_ROLE_STATE')]


@pytest.mark.parametrize('name,change,code',REFUSALS,ids=[r[0] for r in REFUSALS])
def test_unexpected_baseline_is_refused_before_any_change(seeded,name,change,code):
 b=seeded['boot'];holder=None
 if name=='session_present':holder=seeded['connect']('ingestion_worker_login')
 else:
  for s in change.split(';'):b.execute(s)
 try:refuses(b,code)
 finally:
  if holder is not None:holder.close()
  if name=='overload_added':b.execute('DROP FUNCTION public.ingestion_worker_step(integer)')
  if name=='owner_role_state':b.execute('ALTER ROLE ingestion_storage_owner NOCREATEDB')
  if name=='preexisting_self_grant':b.execute('REVOKE ingestion_storage_owner FROM postgres GRANTED BY postgres')
  if name=='owner_changed':b.execute('ALTER FUNCTION public.ingestion_register_bolton_exception(jsonb) OWNER TO ingestion_storage_owner')
  if name=='public_executes_registrar':b.execute('REVOKE EXECUTE ON FUNCTION public.ingestion_register_bolton_exception(jsonb) FROM PUBLIC')
  if name=='no_schema_create_grant_option':b.execute('REVOKE CREATE ON SCHEMA public FROM postgres;GRANT CREATE ON SCHEMA public TO postgres WITH GRANT OPTION')


# --- failure at every stage: complete atomic rollback ------------------------------------------------------------------------------------------------------------------------------------------
BOLTON='CREATE OR REPLACE FUNCTION public.ingestion_bolton_allowed(ctl jsonb, authority text, subject jsonb) RETURNS boolean'
REGISTER='CREATE OR REPLACE FUNCTION public.ingestion_register_bolton_exception(p jsonb) RETURNS jsonb'
WORKER_HEADER='CREATE OR REPLACE FUNCTION public.ingestion_worker_step(p_op text,p_key text,p_fence integer,p_owner text,p_authority text,p_binding jsonb,p_payload jsonb)'
STAGES=[
 # role switching and capability
 ('role_switch_target_missing',lambda s:mutate(s,'SET LOCAL ROLE ingestion_storage_owner;','SET LOCAL ROLE fixture_missing_owner_role;'),'does not exist'),
 ('temp_grant_forbidden_grantor',lambda s:mutate(s,'SET TRUE GRANTED BY postgres;','SET TRUE GRANTED BY provisioning_bootstrap;'),'GRANTED BY|permission denied|must be|ADMIN'),
 ('temp_capability_inexact',lambda s:mutate(s,'WITH ADMIN FALSE, INHERIT FALSE, SET TRUE GRANTED BY postgres;','WITH ADMIN FALSE, INHERIT TRUE, SET TRUE GRANTED BY postgres;'),'INSTALL_TEMP_CAPABILITY'),
 ('schema_create_not_granted',lambda s:mutate(s,'GRANT CREATE ON SCHEMA public TO ingestion_storage_owner;\n','-- test fault: schema CREATE omitted\n'),'INSTALL_TEMP_CAPABILITY'),
 # each replacement fails on its own
 ('replacement_1_fails',lambda s:mutate(s,BOLTON,BOLTON.replace('RETURNS boolean','RETURNS integer')),'cannot change return type'),
 ('replacement_2_fails',lambda s:mutate(s,REGISTER,REGISTER.replace('RETURNS jsonb','RETURNS integer')),'cannot change return type'),
 ('replacement_3_fails',lambda s:mutate(s,WORKER_HEADER+'\nRETURNS jsonb',WORKER_HEADER+'\nRETURNS integer') if (WORKER_HEADER+'\nRETURNS jsonb') in s else mutate(s,WORKER_HEADER+' RETURNS jsonb',WORKER_HEADER+' RETURNS integer'),'cannot change return type'),
 # failure after each completed step
 ('after_replacement_1',lambda s:mutate(s,'$policy$;\n','$policy$;\nSELECT 1/0;\n'),'division by zero'),
 ('after_replacement_2',lambda s:mutate(s,'$register$;\n','$register$;\nSELECT 1/0;\n'),'division by zero'),
 ('after_worker_execute_grant',lambda s:mutate(s,'TO ingestion_worker;\n','TO ingestion_worker;\nSELECT 1/0;\n'),'division by zero'),
 ('after_replacement_3',lambda s:mutate(s,'$fn$;\n','$fn$;\nSELECT 1/0;\n'),'division by zero'),
 # cleanup and postconditions
 ('reset_role_omitted',lambda s:mutate(s,'RESET ROLE;\nREVOKE CREATE','-- test fault: reset omitted\nREVOKE CREATE'),'permission denied|INSTALL_CLEANUP'),
 ('schema_create_cleanup_omitted',lambda s:mutate(s,'REVOKE CREATE ON SCHEMA public FROM ingestion_storage_owner;\n','-- test fault\n'),'INSTALL_CLEANUP'),
 ('owner_membership_cleanup_omitted',lambda s:mutate(s,'REVOKE ingestion_storage_owner FROM postgres GRANTED BY postgres;\n','-- test fault\n'),'INSTALL_CLEANUP'),
 ('extra_grant_to_effect_broker',lambda s:mutate(s,'RESET ROLE;\nREVOKE CREATE','GRANT EXECUTE ON FUNCTION public.ingestion_register_bolton_exception(jsonb) TO ingestion_effect_broker;\nRESET ROLE;\nREVOKE CREATE'),'INSTALL_POST_REGISTER_ACL|INSTALL_POST_FUNCTION_PRIVILEGE'),
 ('worker_execute_grant_omitted',lambda s:mutate(s,'GRANT EXECUTE ON FUNCTION public.ingestion_register_bolton_exception(jsonb) TO ingestion_worker;\n','-- test fault\n'),'INSTALL_POST_REGISTER_ACL|INSTALL_POST_FUNCTION_PRIVILEGE'),
 ('oldham_helper_dropped_by_fault',lambda s:mutate(s,'RESET ROLE;\nREVOKE CREATE','DROP FUNCTION public.ingestion_oldham_allowed(jsonb,text,text,jsonb) CASCADE;\nRESET ROLE;\nREVOKE CREATE'),'INSTALL_POST_INVENTORY'),
 ('ledger_changed_by_fault',lambda s:mutate(s,'RESET ROLE;\nREVOKE CREATE',"UPDATE public.ingestion_work_items SET attempt_count=attempt_count+1 WHERE key='"+KEYS[0]+"';\nRESET ROLE;\nREVOKE CREATE"),'INSTALL_LEDGER_CHANGED|permission denied'),
 ('wrong_candidate_body',lambda s:mutate(s,"AS $policy$\n SELECT coalesce(ctl->'grants'->authority->>'intake_period'","AS $policy$\n SELECT false AND coalesce(ctl->'grants'->authority->>'intake_period'"),'INSTALL_POST_BODY')]


@pytest.mark.parametrize('name,mutator,code',STAGES,ids=[s[0] for s in STAGES])
def test_failure_at_each_stage_rolls_back_definitions_acls_memberships_and_ledger(seeded,name,mutator,code):
 b=seeded['boot']
 refuses(b,code,mutator(SQL),bodies=PRED)


def test_a_lock_held_on_the_ledger_stops_the_preflight_before_any_change(seeded):
 b=seeded['boot'];before=snapshot(b)
 blocker=psycopg.connect(host='127.0.0.1',port=5432,dbname='postgres',user='provisioning_bootstrap',password=FIXTURE_PASSWORD,autocommit=False)
 try:
  blocker.execute('LOCK TABLE public.ingestion_work_items IN ACCESS EXCLUSIVE MODE')      # a second session holds the ledger: the preflight read must time out (3 s) before any change
  with actor() as c:
   with pytest.raises(psycopg.Error,match='lock timeout|lock_not_available|canceling statement'):execute(c)
   c.execute('ROLLBACK')
 finally:
  blocker.rollback();blocker.close()
 assert snapshot(b)==before and {n:body_sha(b,n) for n in PRED}==PRED


# --- client and runner ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def test_client_and_runner_bind_the_installation_sql_hash():
 sql_sha=hashlib.sha256((PKG/'bolton-intake-install.sql').read_bytes()).hexdigest();client=(PKG/'bolton-intake-install-client.py').read_text();run=(PKG/'RUN-INACTIVE.sh').read_text()
 assert "SQL_SHA = '%s'"%sql_sha in client and sql_sha in run and hashlib.sha256(client.encode()).hexdigest() in run


@pytest.mark.parametrize('mode',['ack','no_ack','error','overflow','deadline'])
def test_client_commit_evidence_and_secret_handling(tmp_path,monkeypatch,mode):
 import importlib.util
 spec=importlib.util.spec_from_file_location('install_client',PKG/'bolton-intake-install-client.py')
 m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 assert hashlib.sha256((PKG/'bolton-intake-install.sql').read_bytes()).hexdigest()==m.SQL_SHA
 ca=tmp_path/'ca.crt';ca.write_text('fixture');out=tmp_path/'evidence'
 answers=iter(['18.135.253.94',str(ca),'postgres',str(out)])
 monkeypatch.setattr('builtins.input',lambda _:next(answers))
 sentinel='LOCAL_PASSWORD_SENTINEL'
 monkeypatch.setattr(m.getpass,'getpass',lambda _:sentinel);monkeypatch.setattr(m.shutil,'which',lambda _:'/usr/bin/psql')
 observed={}
 def capture(cmd,env,**kw):
  observed.update(env)
  assert sentinel not in repr(cmd) and sentinel not in repr(env)
  assert env['PGSSLMODE']=='verify-full' and env['PGGSSENCMODE']=='disable' and env['PGCONNECT_TIMEOUT']=='5' and kw['ceiling']==64512
  assert 'default_transaction_read_only=off' in env['PGOPTIONS'] and Path(env['PGPASSFILE']).stat().st_mode&0o777==0o600 and sentinel in Path(env['PGPASSFILE']).read_text()
  data=b'COMMIT\ndisposition\nBOLTON_INTAKE_INSTALL_COMMIT_ACKNOWLEDGED\n' if mode=='ack' else b'fixture output\n'
  return data,dict(exit_code=1 if mode=='error' else 0,reason=mode.upper() if mode in ('overflow','deadline') else None,client_closed=True,output_bytes=len(data),remote_closure='NORMAL_PSQL_EXIT')
 monkeypatch.setattr(m,'capture',capture)
 code=m.main();status=json.loads((out/'status.json').read_text())
 assert status['transaction_outcome']==('COMMIT_ACKNOWLEDGED' if mode=='ack' else 'UNKNOWN_RECONCILE_NO_RETRY') and code==(0 if mode=='ack' else 2)
 assert not Path(observed['PGPASSFILE']).exists() and sentinel not in (out/'psql-output.txt').read_text()+(out/'status.json').read_text() and sum(x.stat().st_size for x in out.iterdir())<=65536


def test_capture_function_unchanged_from_the_reviewed_read_only_client():
 pick=lambda a:next(x for x in a.body if isinstance(x,ast.FunctionDef) and x.name=='capture')
 original=ast.parse((TRUST/'docs/design/daily-intake-20261029/b-readonly-client.py').read_text());current=ast.parse((PKG/'bolton-intake-install-client.py').read_text())
 assert ast.dump(pick(original))==ast.dump(pick(current))


def test_installer_actor_and_exact_server_version_are_recorded(seeded,record_property):
 assert Path(FIXTURE_REPO).resolve()==REPO206.resolve()
 assert 'pr205' not in str(Path(FIXTURE_REPO).resolve()).lower()
 with actor() as c:
  flags=c.execute("SELECT rolsuper,rolcreaterole,rolcreatedb,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
 assert flags==(False,True,True,True)
 record_property('server_version',seeded['server_version'])
 record_property('installer_superuser',False)
 record_property('fixture_repository_commit',subprocess.check_output(['git','-C',FIXTURE_REPO,'rev-parse','HEAD'],text=True).strip())


# Compatibility observations only. Stop changes and authorities below are synthetic
# fixture setup AFTER installing at the required generation-5 baseline. No source
# method, application writer, production login activation or live authority runs.
def fixture_login(world,role):
 from sqlalchemy.engine import make_url
 u=make_url(world['urls'][role])
 return psycopg.connect(host='127.0.0.1',port=5432,dbname='postgres',user=u.username,password=u.password,autocommit=True)


def synthetic_oldham_claim(world,mode):
 from verification.ingestion_storage.oldham_authority import STOP_STATE
 b=world['boot'];key=KEYS[0];a='INGESTION_CHAIN_OLDHAM_FIXTURE';owner='compatibility_fixture'
 subject=dict(kind='APPLICATION',council='oldham',reference='SYNTHETIC_ONLY')
 binding=dict(task='SCREENING',contract='listing-screen-v3',revision='synthetic-only',subject=subject)
 expiry=time.time()+3600
 grant=dict(keys=[key],contracts=['listing-screen-v3'],expires_at=expiry,login='ingestion_worker_login',effect_login='ingestion_effect_login',workers=[owner],bindings={key:binding},source_calls=0,writes=0)
 package=dict(authority=a,scope=dict(council='oldham',semantics='RECEIVED'),stop=copy.deepcopy(STOP_STATE),registration=dict(grant=copy.deepcopy(grant)))
 h=b.execute("SELECT encode(sha256(convert_to(%s::jsonb::text,'UTF8')),'hex')",(json.dumps(package),)).fetchone()[0]
 grant['oldham_package_sha256']=h
 allowance=dict(package=package,package_sha256=h,source_cap=0,write_cap=0,expires_at=expiry,revoked=(mode=='generation3_revoked'),grant_binding={k:v for k,v in grant.items() if k not in ('source_calls','writes')})
 ctl=b.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
 ctl.update(copy.deepcopy(STOP_STATE))
 if mode=='generation5':ctl.update(manual_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP',last_hard_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP',hard_stop_generation=5)
 if mode=='clear_global':ctl.update(global_stop=None,manual_stop=None,last_hard_stop=None,hard_stop_generation=0)
 ctl['grants']={a:grant};ctl['oldham_allowances']={a:allowance}
 b.execute("UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),))
 b.execute("UPDATE public.ingestion_work_items SET subject=%s::json,task='SCREENING',contract='listing-screen-v3',revision='synthetic-only',state='QUEUED',phase='IDLE',dependencies='[]',eligible_at=0,attempt_count=0,max_attempts=2,owner=NULL,lease_until=NULL,checkpoint=NULL,authority=NULL WHERE key=%s",(json.dumps(subject),key))
 return key,a,owner,binding


@pytest.mark.parametrize('mode,old_allowed,new_allowed',[
 ('generation3_valid',True,False),('generation3_revoked',False,False),
 ('generation5',False,False),('clear_global',False,True)])
def test_oldham_compatibility_real_worker_allowance_and_unconditional_guard(seeded,mode,old_allowed,new_allowed,record_property):
 b=seeded['boot']
 with actor() as c:execute(c)
 key,a,owner,binding=synthetic_oldham_claim(seeded,mode)
 allowed=b.execute("SELECT public.ingestion_oldham_allowed(outcome::jsonb,%s,%s,%s::jsonb) FROM public.ingestion_work_items WHERE key=repeat('0',64)",(a,key,json.dumps(binding['subject']))).fetchone()[0]
 assert allowed==(mode=='generation3_valid')
 observed={}
 for version,wanted in [('predecessor',old_allowed),('candidate',new_allowed)]:
  if version=='predecessor':b.execute(seeded['predecessor_defs']['ingestion_worker_step'])
  else:
   from verification.ingestion_storage import intake_policy,screening_v3_worker_sql
   b.execute(screening_v3_worker_sql.original_function(intake_policy.worker_text()))
  before=snapshot(b)
  with fixture_login(seeded,'ingestion_worker_login') as c:
   c.execute('BEGIN')
   try:
    query="SELECT public.ingestion_worker_step('claim',%s,0,%s,%s,%s::jsonb,%s::jsonb)"
    params=(key,owner,a,json.dumps(binding),json.dumps({'lease_seconds':30}))
    if wanted:
     result=c.execute(query,params).fetchone()[0];assert result['state']=='CLAIMED';observed[version]='CLAIMED_THEN_ROLLED_BACK'
    else:
     code='OLDHAM_ALLOWANCE_INVALID' if version=='predecessor' else 'GLOBAL_STOP'
     with pytest.raises(psycopg.Error,match=code):c.execute(query,params)
     observed[version]=code
   finally:c.execute('ROLLBACK')
  assert snapshot(b)==before
 record_property('synthetic_scenario',mode);record_property('behaviour',json.dumps(observed,sort_keys=True))


@pytest.mark.parametrize('remaining',[-100,3600],ids=['expired','unexpired'])
def test_oldham_compatibility_retained_authority_is_preserved_not_retired(seeded,remaining):
 b=seeded['boot'];a='INGESTION_CHAIN_OLDHAM_RETAINED_FIXTURE';expiry=time.time()+remaining
 ctl=b.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
 ctl.setdefault('grants',{})[a]=dict(expires_at=expiry,source_calls=0,writes=0,keys=[])
 ctl.setdefault('oldham_allowances',{})[a]=dict(expires_at=expiry,revoked=False,package={'synthetic_only':True})
 b.execute("UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),))
 before=snapshot(b)
 with actor() as c:execute(c)
 assert snapshot(b)[1:]==before[1:]
 actual=b.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
 assert actual['grants'][a]==ctl['grants'][a] and actual['oldham_allowances'][a]==ctl['oldham_allowances'][a]
 assert actual['hard_stop_generation']==5 and body_sha(b,'ingestion_oldham_allowed')==UNCH['ingestion_oldham_allowed']


@pytest.mark.parametrize('phase,state',[('SOURCE_INTENT','SAFETY_BLOCKED'),('WRITE_INTENT','PERSISTENCE_UNCERTAIN'),('CHECKPOINTED','SAFETY_BLOCKED')])
def test_oldham_compatibility_recovery_function_does_not_require_worker_allowance(seeded,phase,state):
 b=seeded['boot']
 with actor() as c:execute(c)
 key,a,owner,binding=synthetic_oldham_claim(seeded,'generation5')
 b.execute("UPDATE public.ingestion_work_items SET state='CLAIMED',phase=%s,fence=7,owner=%s,authority=%s,lease_until=%s WHERE key=%s",(phase,owner,a,time.time()-100,key))
 b.execute("INSERT INTO public.ingestion_work_attempts(work_key,fence,owner,started_at,authority,phase) VALUES(%s,7,%s,%s,%s,%s)",(key,owner,time.time()-200,a,phase))
 # Synthetic recovery capability for this test only. No recovery-login activation.
 b.execute('GRANT ingestion_recovery_operator TO postgres WITH ADMIN FALSE, INHERIT TRUE, SET FALSE')
 try:
  before=snapshot(b)
  with actor() as c:
   c.execute('BEGIN')
   try:
    result=c.execute('SELECT public.ingestion_recover_abandoned(%s,7,false)',(key,)).fetchone()[0]
    assert result['state']==state and result['phase']=='RECOVERED' and result['fence']==8
    assert result['outcome']['source_or_write_replay_authorised'] is False
    assert c.execute("SELECT outcome::jsonb->'hard_stop_generation' FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]==6
   finally:c.execute('ROLLBACK')
  assert snapshot(b)==before and body_sha(b,'ingestion_recover_abandoned')==UNCH['ingestion_recover_abandoned']
 finally:b.execute('REVOKE ingestion_recovery_operator FROM postgres')


def test_oldham_compatibility_existing_inventory_gate_refuses_candidate(seeded):
 from types import SimpleNamespace
 from app.ingestion.ledger import Denied
 from verification.ingestion_storage.oldham_lifecycle import verify_inventory
 b=seeded['boot'];o=SimpleNamespace(q=lambda c,s,p=None:c.execute(s,p).fetchall())
 verify_inventory(o,b,capture_screening_only=True)
 with actor() as c:execute(c)
 with pytest.raises(Denied,match='OLDHAM_POLICY_INVENTORY'):verify_inventory(o,b,capture_screening_only=True)
