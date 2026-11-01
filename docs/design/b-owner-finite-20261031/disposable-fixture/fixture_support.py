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
 # Existing fixed PG17 service and existing SQL generators; no runtime activation.
 from tests.e2e_pg_world import settings
 from verification.ingestion_storage.operational_owner import PKG as OPKG,GENERATION3_SCREENING_V3_POLICY
 from verification.ingestion_storage import oldham_policy,screening_v3_worker_sql
 settings();assert os.environ.get('BOLTON_TEST_PG_CONTAINER'), 'PRIVATE_DISPOSABLE_SERVICE_REQUIRED'
 b=psycopg.connect(host='127.0.0.1',port=5432,dbname='postgres',user='provisioning_bootstrap',password=FIXTURE_PASSWORD,autocommit=True)
 version=b.info.server_version;assert 170000<=version<180000
 b.execute('CREATE ROLE provisioning_migrator NOLOGIN NOSUPERUSER CREATEROLE NOINHERIT')
 b.execute('GRANT USAGE,CREATE ON SCHEMA public TO provisioning_migrator WITH GRANT OPTION')
 b.execute('GRANT CONNECT ON DATABASE postgres TO provisioning_migrator WITH GRANT OPTION')
 b.execute('SET SESSION AUTHORIZATION provisioning_migrator')
 try:
  initial=Path('docs/design/ingestion-provisioning-20261016/install.sql').read_text()
  # Initial bootstrap omits the historical worker mapping entirely: never restore it.
  mapping='GRANT ingestion_worker TO ingestion_worker_login WITH ADMIN FALSE, INHERIT TRUE, SET FALSE;'
  assert initial.count(mapping)==1;b.execute(initial.replace(mapping,'-- No runtime mapping in post-cleanup fixture.'))
  b.execute(Path('docs/design/ingestion-operational-20261016/worker.sql').read_text())
  b.execute(screening_v3_worker_sql.installation_script())
  b.execute((OPKG/'successor-policy.sql').read_text());b.execute(GENERATION3_SCREENING_V3_POLICY.read_text());b.execute(oldham_policy.installation_script())
 finally:b.execute('RESET SESSION AUTHORIZATION')
 for role in ['ingestion_effect_login','ingestion_application_login','ingestion_recovery_login']:
  b.execute('CREATE ROLE '+role+' NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS NOREPLICATION CONNECTION LIMIT 1 PASSWORD NULL')
 assert {n:body_sha(b,n) for n in PRED}==PRED and {n:body_sha(b,n) for n in UNCH}==UNCH
 w={'boot':b,'server_version':version,'control':b.execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]}
 w['predecessor_defs']={n:b.execute('SELECT pg_get_functiondef(%s::regprocedure)',(SIG[n],)).fetchone()[0] for n in ALL7}
 w['owners']={n:b.execute('SELECT pg_get_userbyid(proowner) FROM pg_proc WHERE oid=%s::regprocedure',(SIG[n],)).fetchone()[0] for n in ALL7}
 b.execute("CREATE ROLE postgres LOGIN NOSUPERUSER BYPASSRLS CREATEROLE CREATEDB INHERIT PASSWORD 'disposable_actor_password'")
 b.execute('GRANT USAGE,CREATE ON SCHEMA public TO postgres WITH GRANT OPTION')
 b.execute('GRANT SELECT ON ingestion_work_items,ingestion_work_attempts TO postgres');b.execute('GRANT pg_read_all_stats TO postgres')
 b.execute('GRANT SELECT (rolname,rolpassword) ON pg_authid TO postgres')
 try:yield w
 finally:
  b.execute('DROP SCHEMA public CASCADE;CREATE SCHEMA public')
  names=[x[0] for x in b.execute("SELECT rolname FROM pg_roles WHERE rolname LIKE 'ingestion_%' OR rolname IN ('postgres','provisioning_migrator')").fetchall()]
  for name in names:b.execute(psycopg.sql.SQL('DROP OWNED BY {} CASCADE').format(psycopg.sql.Identifier(name)))
  for name in names:b.execute(psycopg.sql.SQL('DROP ROLE {}').format(psycopg.sql.Identifier(name)))
  b.close()


@pytest.fixture
def seeded(world):
 b=world['boot']
 b.execute('ALTER ROLE ingestion_worker_login NOINHERIT')
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
 from verification.ingestion_storage.oldham_reuse import expected_historical
 class Owner:
  def q(self,c,query,params=None):return c.execute(query,params).fetchall()
 historical_grant,historical_allowance=expected_historical(Owner(),b)
 historical_grant['expires_at']=0;historical_allowance['revoked']=True
 authority='INGESTION_CHAIN_OLDHAM_STAGED_CAPTURE_E9D12874CFB5'
 ctl['grants'][authority]=historical_grant;ctl.setdefault('oldham_allowances',{})[authority]=historical_allowance
 b.execute("UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),))
 b.execute('INSERT INTO ingestion_work_items SELECT (jsonb_populate_record(NULL::ingestion_work_items,%s::jsonb)).*',(json.dumps(historical_allowance['package']['registration']['rows'][0]),))
 assert {n:body_sha(b,n) for n in PRED}==PRED
 assert_closed(b)
 return world


def snapshot(b):
 """Everything the installation may touch or must leave alone."""
 fn=b.execute("""SELECT jsonb_object_agg(p.proname,jsonb_build_array(encode(sha256(convert_to(p.prosrc,'UTF8')),'hex'),pg_get_userbyid(p.proowner),p.proconfig,p.prosecdef,p.provolatile::text,
   (SELECT coalesce(jsonb_agg(jsonb_build_array(x.grantor::regrole::text,x.grantee,x.privilege_type,x.is_grantable) ORDER BY x.grantor,x.grantee,x.privilege_type),'[]'::jsonb) FROM aclexplode(p.proacl) x)))
   FROM pg_proc p WHERE p.pronamespace='public'::regnamespace AND p.proname LIKE 'ingestion\\_%'""").fetchone()[0]
 q=["SELECT jsonb_agg(to_jsonb(m) ORDER BY roleid,member,grantor) FROM pg_auth_members m",
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
 assert_closed(b)
 for name in ALL7:
  if name in CAND:assert fa[name][1:5]==fb[name][1:5]      # owner, config, security definer, volatility unchanged
  if name not in CAND:assert fa[name]==fb[name]      # Oldham helper and every other function untouched, ACLs included
 for name in ('ingestion_bolton_allowed','ingestion_worker_step'):assert fa[name][5]==fb[name][5]
 added=[e for e in fa['ingestion_register_bolton_exception'][5] if e not in fb['ingestion_register_bolton_exception'][5]]
 assert len(added)==1 and added[0][2:]==['EXECUTE',False] and len(fa['ingestion_register_bolton_exception'][5])==len(fb['ingestion_register_bolton_exception'][5])+1      # the single worker EXECUTE addition
 assert after[1:]==before[1:]      # memberships (all rows), schema ACL, ledger/stop/recovered items, role flags identical
 with actor() as c:
  assert c.execute("SELECT has_function_privilege('ingestion_worker','public.ingestion_register_bolton_exception(jsonb)','EXECUTE'),has_function_privilege('ingestion_effect_broker','public.ingestion_register_bolton_exception(jsonb)','EXECUTE'),pg_has_role(current_user,'ingestion_storage_owner','SET'),pg_has_role(current_user,'ingestion_storage_owner','USAGE'),has_schema_privilege('ingestion_storage_owner','public','CREATE')").fetchone()==(True,False,False,False,False)
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
  ('no_owner_membership','REVOKE ingestion_storage_owner FROM postgres CASCADE','INSTALL_OWNER_ADMIN_BASELINE'),
 ('owner_set_already','REVOKE ingestion_storage_owner FROM postgres CASCADE;GRANT ingestion_storage_owner TO postgres WITH ADMIN TRUE, INHERIT FALSE, SET TRUE GRANTED BY provisioning_bootstrap','INSTALL_OWNER_ADMIN_BASELINE'),
 ('admin_option_missing','REVOKE ingestion_storage_owner FROM postgres CASCADE;GRANT ingestion_storage_owner TO postgres WITH ADMIN FALSE, INHERIT FALSE, SET FALSE GRANTED BY provisioning_bootstrap','INSTALL_OWNER_ADMIN_BASELINE'),
 ('preexisting_self_grant','GRANT ingestion_storage_owner TO postgres WITH ADMIN FALSE, INHERIT FALSE, SET FALSE GRANTED BY postgres','INSTALL_OWNER_ADMIN_BASELINE'),
 ('owner_already_has_schema_create','GRANT CREATE ON SCHEMA public TO ingestion_storage_owner','INSTALL_SCHEMA_BASELINE'),
 ('no_schema_create_grant_option','REVOKE CREATE ON SCHEMA public FROM postgres CASCADE;GRANT CREATE ON SCHEMA public TO postgres','INSTALL_SCHEMA_BASELINE'),
 ('owner_role_state','ALTER ROLE ingestion_storage_owner CREATEDB','INSTALL_OWNER_ROLE_STATE')]


@pytest.mark.parametrize('name,change,code',REFUSALS,ids=[r[0] for r in REFUSALS])
def test_unexpected_baseline_is_refused_before_any_change(seeded,name,change,code):
 b=seeded['boot']
 for s in change.split(';'):b.execute(s)
 try:refuses(b,code)
 finally:
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




A='INGESTION_CHAIN_OLDHAM_STAGED_CAPTURE_E9D12874CFB5'
def assert_closed(b):
 assert b.execute("SELECT count(*) FROM pg_roles r JOIN pg_authid a ON a.rolname=r.rolname WHERE r.rolname IN ('ingestion_worker_login','ingestion_effect_login') AND NOT r.rolcanlogin AND a.rolpassword IS NULL").fetchone()[0]==2
 assert b.execute("SELECT count(*) FROM pg_auth_members WHERE member IN ('ingestion_worker_login'::regrole,'ingestion_effect_login'::regrole) AND roleid IN ('ingestion_worker'::regrole,'ingestion_effect_broker'::regrole)").fetchone()[0]==0
 assert b.execute("SELECT has_function_privilege('ingestion_worker_login','public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)','EXECUTE'),has_function_privilege('ingestion_effect_login','public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)','EXECUTE')").fetchone()==(False,False)


def test_postcleanup_role_grant_does_not_open_runtime_or_undo_revocation(seeded):
 b=seeded['boot'];before=snapshot(b);assert_closed(b)
 with actor() as c:execute(c)
 assert_closed(b)
 assert snapshot(b)[1:]==before[1:]
 ctl=b.execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
 assert ctl['grants'][A]['expires_at']==0 and ctl['oldham_allowances'][A]['revoked'] is True
 assert b.execute("SELECT has_function_privilege('ingestion_worker','public.ingestion_register_bolton_exception(jsonb)','EXECUTE'),has_function_privilege('ingestion_worker_login','public.ingestion_register_bolton_exception(jsonb)','EXECUTE')").fetchone()==(True,False)


@pytest.mark.parametrize('fault',['unrevoked','expiry_restored','string_zero','binding_rewritten','work_changed','runtime_password','runtime_inherit'])
def test_postcleanup_drift_refuses_without_reopening_access(seeded,fault):
 b=seeded['boot']
 if fault=='runtime_password':b.execute("ALTER ROLE ingestion_worker_login PASSWORD 'synthetic_only'")
 elif fault=='runtime_inherit':b.execute('ALTER ROLE ingestion_worker_login INHERIT')
 elif fault=='work_changed':b.execute("UPDATE ingestion_work_items SET attempt_count=1 WHERE key='abf1b6f7e9c8119a74e2f8f3d2bdec0a4b2da3a5eee8768a2783614755aa26cf'")
 else:
  ctl=b.execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
  if fault=='unrevoked':ctl['oldham_allowances'][A]['revoked']=False
  if fault=='expiry_restored':ctl['grants'][A]['expires_at']=1793228890.0
  if fault=='string_zero':ctl['grants'][A]['expires_at']='0'
  if fault=='binding_rewritten':ctl['oldham_allowances'][A]['grant_binding']['expires_at']=0
  b.execute("UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),))
 try:refuses(b,'INSTALL_RUNTIME_NOT_CLOSED' if fault.startswith('runtime_') else 'INSTALL_OLDHAM_CLEANUP_BINDING')
 finally:
  b.execute('ALTER ROLE ingestion_worker_login NOINHERIT PASSWORD NULL')


def test_reopened_oldham_allowance_inside_transaction_rolls_back(seeded):
 s=mutate(SQL,'RESET ROLE;\nREVOKE CREATE',"UPDATE public.ingestion_work_items SET outcome=jsonb_set(outcome::jsonb,ARRAY['oldham_allowances','"+A+"','revoked'],'false')::json WHERE key=repeat('0',64);\nRESET ROLE;\nREVOKE CREATE")
 refuses(seeded['boot'],'INSTALL_LEDGER_CHANGED',s,bodies=PRED)
 assert_closed(seeded['boot'])
