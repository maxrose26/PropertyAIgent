"""Exact latent statistics ACLs, real restricted logins, disposable PG17 only.

Never selects the query column or invokes a statistics reset successfully.
Production catalogues are not used as proof of effective login behaviour.
"""
import os,secrets
from pathlib import Path
import psycopg,pytest
from psycopg import sql


def test_exact_statistics_baseline_real_logins(record_property):
 raw=os.environ.get('INGESTION_PROVISIONING_TEST_URL')
 if not raw:pytest.skip('fixed disposable PostgreSQL17 required')
 info=psycopg.conninfo.conninfo_to_dict(raw)
 assert (info.get('host'),info.get('port'),info.get('dbname'),info.get('user'))==('127.0.0.1','5432','ingestion_provisioning_test','provisioning_bootstrap')
 package=Path('docs/design/ingestion-provisioning-20261016')
 roles=['ingestion_storage_owner','ingestion_storage_operator','ingestion_worker','ingestion_authority_issuer','ingestion_barrier_releaser','ingestion_worker_login','ingestion_storage_login']
 passwords={r:secrets.token_urlsafe(48) for r in ['statistics_migrator',*roles[-2:]]}
 def connect(role):return psycopg.connect(**{**info,'user':role,'password':passwords[role]},autocommit=True,connect_timeout=3)
 with psycopg.connect(raw,autocommit=True) as boot:
  assert 170000<=boot.info.server_version<180000
  boot.execute('CREATE SCHEMA extensions')
  boot.execute('REVOKE ALL ON SCHEMA extensions FROM PUBLIC')
  boot.execute('CREATE EXTENSION pg_stat_statements WITH SCHEMA extensions VERSION \'1.11\'')
  boot.execute(sql.SQL('CREATE ROLE statistics_migrator LOGIN NOSUPERUSER CREATEROLE NOINHERIT NOBYPASSRLS PASSWORD {}').format(sql.Literal(passwords['statistics_migrator'])))
  boot.execute('GRANT USAGE,CREATE ON SCHEMA public TO statistics_migrator WITH GRANT OPTION')
  boot.execute('GRANT CONNECT ON DATABASE ingestion_provisioning_test TO statistics_migrator WITH GRANT OPTION')
  # Production postgres owns this schema; fixture migration access is separate
  # from the two runtime logins, which never receive schema USAGE.
  boot.execute('GRANT USAGE ON SCHEMA extensions TO statistics_migrator')
  try:
   with connect('statistics_migrator') as m:
    m.execute((package/'install.sql').read_text())
    for role in roles[-2:]:
     m.execute(sql.SQL('ALTER ROLE {} PASSWORD {}').format(sql.Identifier(role),sql.Literal(passwords[role])))
    def rejected(mutate,undo,reason):
     boot.execute(mutate)
     try:
      with pytest.raises(psycopg.Error,match=reason):m.execute((package/'activate.sql').read_text())
      m.execute('ROLLBACK')
      assert m.execute('SELECT bool_or(rolcanlogin) FROM pg_roles WHERE rolname=ANY(%s)',(roles[-2:],)).fetchone()==(False,)
     finally:boot.execute(undo)
    rejected('GRANT USAGE ON SCHEMA extensions TO PUBLIC','REVOKE USAGE ON SCHEMA extensions FROM PUBLIC','STATISTICS_BASELINE_BOUNDARY')
    rejected('GRANT pg_read_all_stats TO ingestion_worker_login','REVOKE pg_read_all_stats FROM ingestion_worker_login','LOGIN_MEMBERSHIP')
    rejected('GRANT UPDATE ON extensions.pg_stat_statements TO PUBLIC','REVOKE UPDATE ON extensions.pg_stat_statements FROM PUBLIC','STATISTICS_OBJECT_OR_PRIVILEGE_CHANGED')
    rejected('ALTER VIEW extensions.pg_stat_statements SET (security_invoker=true)','ALTER VIEW extensions.pg_stat_statements RESET (security_invoker)','STATISTICS_OBJECT_OR_PRIVILEGE_CHANGED')
    rejected('GRANT EXECUTE ON FUNCTION extensions.pg_stat_statements_reset(oid,oid,bigint,boolean) TO PUBLIC','REVOKE EXECUTE ON FUNCTION extensions.pg_stat_statements_reset(oid,oid,bigint,boolean) FROM PUBLIC','STATISTICS_FUNCTION_BOUNDARY')
    boot.execute('CREATE VIEW extensions.unexpected_statistics AS SELECT 1 AS sentinel')
    rejected('GRANT SELECT ON extensions.unexpected_statistics TO PUBLIC','DROP VIEW extensions.unexpected_statistics','AMBIENT_NON_LEDGER_ACCESS')
    m.execute((package/'activate.sql').read_text())
   denials=0
   for role in roles[-2:]:
    with connect(role) as c:
     assert c.execute('SELECT current_user,session_user').fetchone()==(role,role)
     assert c.execute("SELECT has_schema_privilege(current_user,'extensions','USAGE'),has_table_privilege(current_user,(SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='extensions' AND c.relname='pg_stat_statements'),'SELECT'),pg_has_role(current_user,'pg_read_all_stats','MEMBER'),has_function_privilege(current_user,(SELECT p.oid FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='extensions' AND p.proname='pg_stat_statements_reset'),'EXECUTE')").fetchone()==(False,True,False,False)
     # Real SQL parse/access checks, not SET ROLE or catalogue-only assertions.
     for statement in ['SELECT 1 FROM extensions.pg_stat_statements LIMIT 0','SELECT 1 FROM extensions.pg_stat_statements_info LIMIT 0','SELECT extensions.pg_stat_statements(false)','SELECT extensions.pg_stat_statements_reset(0::oid,0::oid,0::bigint,false)']:
      with pytest.raises(psycopg.Error) as e:c.execute(statement)
      assert e.value.sqlstate=='42501' and 'schema extensions' in str(e.value)
      denials+=1
   record_property('real_restricted_logins',2);record_property('effective_schema_denials_42501',denials)
   record_property('stored_query_text_retrieved',False);record_property('reset_executed',False)
   record_property('extension_version','1.11');record_property('production_connections',0)
  finally:
   boot.execute('DROP TABLE IF EXISTS public.ingestion_work_attempts,public.ingestion_work_items CASCADE')
   boot.execute('DROP FUNCTION IF EXISTS public.ingestion_seed_storage_test(),public.ingestion_raise_stop(text)')
   boot.execute('DROP EXTENSION pg_stat_statements')
   boot.execute('DROP SCHEMA extensions')
   for role in [*roles,'statistics_migrator']:
    if boot.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone():
     boot.execute(sql.SQL('DROP OWNED BY {} CASCADE').format(sql.Identifier(role)))
   for role in [*roles,'statistics_migrator']:
    boot.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(role)))
