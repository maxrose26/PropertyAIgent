"""Exact proposed provisioning; fixed disposable PostgreSQL17 only, real logins.

Bootstrap superuser only builds/tears down the disposable fixture. Neither the
installation nor any denial assertion runs as bootstrap/superuser/SET ROLE.
"""
import json,os,secrets
from pathlib import Path
import psycopg,pytest
from psycopg import sql
PACKAGE=Path('docs/design/ingestion-provisioning-20261016')
ROLES=['ingestion_storage_owner','ingestion_storage_operator','ingestion_worker','ingestion_authority_issuer','ingestion_barrier_releaser','ingestion_worker_login','ingestion_storage_login']


def test_non_superuser_provisioning_recovery_and_real_login_denials(record_property):
 raw=os.environ.get('INGESTION_PROVISIONING_TEST_URL')
 if not raw:pytest.skip('fixed disposable PostgreSQL17 required')
 info=psycopg.conninfo.conninfo_to_dict(raw)
 assert (info.get('host'),info.get('port'),info.get('dbname'),info.get('user'))==('127.0.0.1','5432','ingestion_provisioning_test','provisioning_bootstrap')
 secrets_by_role={name:secrets.token_urlsafe(48) for name in ['provisioning_migrator',*ROLES[-2:]]}
 def connect(name):
  return psycopg.connect(**{**info,'user':name,'password':secrets_by_role[name]},autocommit=True,connect_timeout=3,prepare_threshold=None)
 def deny(c,statement):
  with pytest.raises(psycopg.Error) as e:c.execute(statement)
  assert e.value.sqlstate=='42501'
 with psycopg.connect(raw,autocommit=True,connect_timeout=3) as boot:
  assert int(boot.info.server_version)>=170000
  boot.execute('CREATE TABLE public.applications(id integer PRIMARY KEY,address text)')
  boot.execute('INSERT INTO public.applications VALUES(1504,\'PRESERVED\'),(1505,\'PRESERVED\'),(1506,\'PRESERVED\'),(1507,\'PENDING\'),(1508,\'PENDING\')')
  boot.execute(sql.SQL('CREATE ROLE provisioning_migrator LOGIN NOSUPERUSER NOCREATEDB CREATEROLE NOINHERIT NOBYPASSRLS PASSWORD {}').format(sql.Literal(secrets_by_role['provisioning_migrator'])))
  boot.execute('GRANT USAGE,CREATE ON SCHEMA public TO provisioning_migrator WITH GRANT OPTION')
  boot.execute('GRANT CONNECT ON DATABASE ingestion_provisioning_test TO provisioning_migrator WITH GRANT OPTION')
  boot.execute('CREATE ROLE provisioning_untrusted NOLOGIN')
  try:
   with connect('provisioning_migrator') as m:
    assert m.execute('SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()==(False,False,True,False)
    # CREATEROLE alone cannot execute the previously reviewed owner-transfer SQL.
    old=Path('docs/design/ingestion-readiness-20261016/migration.sql').read_text()
    with pytest.raises(psycopg.Error) as e:m.execute(old)
    assert e.value.sqlstate=='42501';m.execute('ROLLBACK')
    assert m.execute("SELECT count(*) FROM pg_roles WHERE rolname=ANY(%s)",(ROLES,)).fetchone()[0]==0
    # Deliberately adverse inherited defaults apply only to newly-created objects.
    m.execute('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO PUBLIC,provisioning_untrusted')
    m.execute('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO PUBLIC,provisioning_untrusted')
    installation=(PACKAGE/'install.sql').read_text()
    broken=installation.replace('CREATE TABLE public.ingestion_work_attempts (',"SELECT 1/0;\nCREATE TABLE public.ingestion_work_attempts (",1)
    with pytest.raises(psycopg.Error):m.execute(broken)
    m.execute('ROLLBACK')
    assert m.execute("SELECT to_regclass('public.ingestion_work_items')").fetchone()[0] is None
    assert m.execute('SELECT count(*) FROM pg_roles WHERE rolname=ANY(%s)',(ROLES,)).fetchone()[0]==0
    m.execute(installation)
    assert m.execute("SELECT pg_has_role(current_user,'ingestion_storage_owner','USAGE'),pg_has_role(current_user,'ingestion_storage_owner','SET')").fetchone()==(False,False)
    assert m.execute("SELECT has_schema_privilege('ingestion_storage_owner','public','CREATE')").fetchone()==(False,)
    # Immutable creator ADMIN-only grant is retained and explicitly reported.
    creator=m.execute("SELECT admin_option,inherit_option,set_option FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user) AND roleid='ingestion_storage_owner'::regrole").fetchall()
    assert creator and all(x==(True,False,False) for x in creator)
    assert m.execute('SELECT rolcanlogin FROM pg_roles WHERE rolname=ANY(%s) ORDER BY rolname',(ROLES[-2:],)).fetchall()==[(False,),(False,)]
    # First-install rerun refuses existing names, preserves committed control.
    with pytest.raises(psycopg.Error) as e:m.execute(installation)
    assert e.value.sqlstate=='42710';m.execute('ROLLBACK')
    # Exercise real libpq client-side SCRAM and ALTER ROLE with the exact helper;
    # intercept ONLY the GitHub CLI boundary, so no secret leaves loopback tests.
    from verification.ingestion_storage.credential_mapping import install_mapping
    from types import SimpleNamespace
    password_values=iter([secrets_by_role[name] for name in ROLES[-2:]])
    def fake_secret_cli(command,**kwargs):
     assert command[:3]==['gh','secret','set'] and command[-1]=='stage4-production-canary'
     assert b'aws-0-eu-west-2.pooler.supabase.com:5432/postgres' in kwargs['input']
     return SimpleNamespace(returncode=0)
    mapped=install_mapping(m,attested=True,runner=fake_secret_cli,password_factory=lambda:next(password_values))
    assert len(mapped)==2 and all(not row['login_enabled'] for row in mapped)
    # New login activation fails closed on inherited PUBLIC write access.
    boot.execute('GRANT UPDATE ON public.applications TO PUBLIC')
    with pytest.raises(psycopg.Error,match='AMBIENT_NON_LEDGER_ACCESS'):m.execute((PACKAGE/'activate.sql').read_text())
    m.execute('ROLLBACK');boot.execute('REVOKE UPDATE ON public.applications FROM PUBLIC')
    boot.execute("CREATE FUNCTION public.unreviewed_privileged() RETURNS void LANGUAGE sql SECURITY DEFINER AS 'SELECT NULL::void'")
    with pytest.raises(psycopg.Error,match='UNREVIEWED_SECURITY_DEFINER'):m.execute((PACKAGE/'activate.sql').read_text())
    m.execute('ROLLBACK');boot.execute('DROP FUNCTION public.unreviewed_privileged()')
    m.execute((PACKAGE/'activate.sql').read_text())
   denied=0
   with connect('ingestion_worker_login') as worker,connect('ingestion_storage_login') as operator:
    for name,c in [('ingestion_worker_login',worker),('ingestion_storage_login',operator)]:
     assert c.execute('SELECT current_user,session_user').fetchone()==(name,name)
     assert c.execute('SELECT rolsuper,rolbypassrls,rolcreaterole,rolcreatedb,rolreplication FROM pg_roles WHERE rolname=current_user').fetchone()==(False,False,False,False,False)
     assert c.execute("SELECT count(*) FROM public.ingestion_work_items").fetchone()==(1,)
     for statement in ["UPDATE public.ingestion_work_items SET outcome='{}'",'INSERT INTO public.ingestion_work_items SELECT * FROM public.ingestion_work_items LIMIT 0',"INSERT INTO public.ingestion_work_attempts(work_key) VALUES('x')",'DELETE FROM public.ingestion_work_items','TRUNCATE public.ingestion_work_attempts','ALTER TABLE public.ingestion_work_items DISABLE ROW LEVEL SECURITY',"UPDATE public.applications SET address='FORBIDDEN'",'SET ROLE ingestion_storage_owner','SET ROLE ingestion_authority_issuer','SET ROLE ingestion_barrier_releaser','SET ROLE '+('ingestion_worker' if name=='ingestion_worker_login' else 'ingestion_storage_operator'),'CREATE ROLE forbidden_role',"GRANT ingestion_storage_owner TO "+name,'CREATE TABLE public.forbidden_table(id int)']:
      deny(c,statement);denied+=1
    deny(worker,'SELECT public.ingestion_seed_storage_test()');denied+=1
    deny(operator,"SELECT public.ingestion_raise_stop('UNAUTHORISED')");denied+=1
    for _ in range(2):
     operator.execute('BEGIN');assert operator.execute('SELECT public.ingestion_seed_storage_test()').fetchone()==(3,);operator.execute('COMMIT')
    worker.execute('BEGIN');worker.execute("SELECT public.ingestion_raise_stop('STORAGE_TEST_STOP')");worker.execute('COMMIT')
   with connect('ingestion_storage_login') as operator:
    rows=operator.execute("SELECT to_jsonb(w) FROM public.ingestion_work_items w WHERE key<>repeat('0',64) ORDER BY key").fetchall()
    expected=json.loads(Path('docs/design/ingestion-readiness-20261016/three-items.json').read_text())['items']
    assert [r[0] for r in rows]==sorted(expected,key=lambda x:x['key'])
    assert operator.execute('SELECT count(*) FROM public.ingestion_work_attempts').fetchone()==(0,)
    control=operator.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
    assert control['global_stop']=={'reason':'CONSUMED_SALFORD_GLOBAL_STOP','run':'38884069913'} and control['grants']=={} and control['manual_stop']=='STORAGE_TEST_STOP'
    assert operator.execute("SELECT count(*) FROM pg_class c,LATERAL aclexplode(c.relacl) a WHERE c.oid IN ('public.ingestion_work_items'::regclass,'public.ingestion_work_attempts'::regclass) AND a.grantee IN (0,'provisioning_untrusted'::regrole)").fetchone()==(0,)
    assert operator.execute("SELECT count(*) FROM pg_proc p,LATERAL aclexplode(p.proacl) a WHERE p.oid IN ('public.ingestion_seed_storage_test()'::regprocedure,'public.ingestion_raise_stop(text)'::regprocedure) AND a.grantee IN (0,'provisioning_untrusted'::regrole)").fetchone()==(0,)
    record_property('serialized_bytes',operator.execute('SELECT sum(octet_length(to_jsonb(w)::text)) FROM public.ingestion_work_items w').fetchone()[0])
    record_property('physical_bytes',operator.execute("SELECT pg_total_relation_size('public.ingestion_work_items')+pg_total_relation_size('public.ingestion_work_attempts')").fetchone()[0])
   assert boot.execute('SELECT id,address FROM public.applications ORDER BY id').fetchall()==[(1504,'PRESERVED'),(1505,'PRESERVED'),(1506,'PRESERVED'),(1507,'PENDING'),(1508,'PENDING')]
   with connect('provisioning_migrator') as m:m.execute((PACKAGE/'revoke.sql').read_text())
   for name in ROLES[-2:]:
    with pytest.raises(psycopg.OperationalError):connect(name)
   assert boot.execute('SELECT count(*) FROM public.ingestion_work_items').fetchone()==(4,)
   record_property('server_version',boot.info.server_version);record_property('real_scram_mapping_helper',True);record_property('denials_sqlstate_42501',denied);record_property('migration_superuser',False);record_property('migration_bypassrls',False);record_property('real_restricted_logins',2);record_property('owner_creator_admin_only_retained',True);record_property('source_calls',0);record_property('production_connections',0)
  finally:
   # Test-only disposable teardown. Production rollback never drops retained data.
   boot.execute('DROP TABLE IF EXISTS public.ingestion_work_attempts,public.ingestion_work_items CASCADE')
   boot.execute('DROP FUNCTION IF EXISTS public.ingestion_seed_storage_test(),public.ingestion_raise_stop(text)')
   for name in [*ROLES,'provisioning_migrator','provisioning_untrusted']:
    if boot.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(name,)).fetchone():
     boot.execute(sql.SQL('DROP OWNED BY {} CASCADE').format(sql.Identifier(name)))
   for name in [*ROLES,'provisioning_migrator','provisioning_untrusted']:
    boot.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(name)))
   boot.execute('DROP TABLE public.applications')
