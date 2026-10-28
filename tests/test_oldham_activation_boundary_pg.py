"""Actual derived gate, PG17 extension and inherited ACLs; disposable only."""
import pytest
from psycopg import sql
from tests.e2e_pg_world import disposable_world
from verification.ingestion_storage.oldham_lifecycle import activation_gate
from verification.ingestion_storage.storage_controller import split_sql

@pytest.fixture
def world():
    gen=disposable_world();w=next(gen);b=w['boot']
    try:
        for role in ('ingestion_worker_login','ingestion_effect_login'):b.execute('ALTER ROLE '+role+' NOLOGIN')
        b.execute('CREATE SCHEMA extensions');b.execute('REVOKE ALL ON SCHEMA extensions FROM PUBLIC')
        b.execute("CREATE EXTENSION pg_stat_statements WITH SCHEMA extensions VERSION '1.11'")
        yield w
    finally:
        b.execute('DROP EXTENSION IF EXISTS pg_stat_statements CASCADE');b.execute('DROP SCHEMA IF EXISTS extensions CASCADE')
        try:next(gen)
        except StopIteration:pass


def gate(b):
    b.execute('BEGIN READ ONLY')
    try:
        for q in split_sql(activation_gate(True)):
            if q.lstrip().startswith('DO '):b.execute(q)
    finally:b.execute('ROLLBACK')


@pytest.mark.parametrize('recovery',['absent','dormant','enabled','super','extra_role','direct_write','column_read'])
def test_recovery_and_both_latent_views(world,recovery):
    b=world['boot']
    if recovery=='absent':b.execute('DROP OWNED BY ingestion_recovery_login');b.execute('DROP ROLE ingestion_recovery_login')
    elif recovery=='enabled':b.execute('ALTER ROLE ingestion_recovery_login LOGIN')
    elif recovery=='super':b.execute('ALTER ROLE ingestion_recovery_login SUPERUSER')
    elif recovery=='extra_role':b.execute('GRANT pg_read_all_stats TO ingestion_recovery_login')
    elif recovery=='column_read':b.execute('GRANT SELECT(reference) ON public.applications TO ingestion_recovery_login')
    elif recovery=='direct_write':b.execute('GRANT UPDATE ON public.applications TO ingestion_recovery_login')
    try:
        if recovery in ('absent','dormant'):gate(b)
        else:
            with pytest.raises(Exception,match='RECOVERY_MUST_REMAIN_DORMANT'):gate(b)
        for r in ('ingestion_worker_login','ingestion_effect_login'):
            assert b.execute("SELECT has_table_privilege(%s,'extensions.pg_stat_statements','SELECT'),has_table_privilege(%s,'extensions.pg_stat_statements_info','SELECT'),has_schema_privilege(%s,'extensions','USAGE')",(r,r,r)).fetchone()==(True,True,False)
    finally:
        if recovery=='super':b.execute('ALTER ROLE ingestion_recovery_login NOSUPERUSER')
        if recovery=='extra_role':b.execute('REVOKE pg_read_all_stats FROM ingestion_recovery_login')
        if recovery=='column_read':b.execute('REVOKE SELECT(reference) ON public.applications FROM ingestion_recovery_login')
        if recovery=='direct_write':b.execute('REVOKE UPDATE ON public.applications FROM ingestion_recovery_login')


@pytest.mark.parametrize('change,undo,code',[
 ('GRANT USAGE ON SCHEMA extensions TO ingestion_worker','REVOKE USAGE ON SCHEMA extensions FROM ingestion_worker','STATISTICS_BASELINE_BOUNDARY'),
 ('GRANT pg_monitor TO ingestion_worker','REVOKE pg_monitor FROM ingestion_worker','STATISTICS_BASELINE_BOUNDARY'),
 ('GRANT UPDATE ON extensions.pg_stat_statements_info TO ingestion_effect_broker','REVOKE UPDATE ON extensions.pg_stat_statements_info FROM ingestion_effect_broker','STATISTICS_OBJECT_OR_PRIVILEGE_CHANGED'),
 ('ALTER VIEW extensions.pg_stat_statements SET (security_invoker=true)','ALTER VIEW extensions.pg_stat_statements RESET (security_invoker)','STATISTICS_OBJECT_OR_PRIVILEGE_CHANGED'),
 ('GRANT EXECUTE ON FUNCTION extensions.pg_stat_statements_reset(oid,oid,bigint,boolean) TO ingestion_worker','REVOKE EXECUTE ON FUNCTION extensions.pg_stat_statements_reset(oid,oid,bigint,boolean) FROM ingestion_worker','STATISTICS_FUNCTION_BOUNDARY'),
 ('CREATE VIEW extensions.lookalike AS SELECT 1; GRANT SELECT ON extensions.lookalike TO ingestion_effect_broker','DROP VIEW extensions.lookalike','AMBIENT_UNRELATED_TABLE_ACCESS'),
 ('CREATE TABLE public.unrelated(x int); GRANT SELECT ON public.unrelated TO ingestion_worker','DROP TABLE public.unrelated','AMBIENT_UNRELATED_TABLE_ACCESS'),
 ('ALTER EXTENSION pg_stat_statements DROP VIEW extensions.pg_stat_statements_info','ALTER EXTENSION pg_stat_statements ADD VIEW extensions.pg_stat_statements_info','STATISTICS_OBJECT_OR_PRIVILEGE_CHANGED'),
 ('ALTER VIEW extensions.pg_stat_statements_info RENAME TO original_info; CREATE VIEW extensions.pg_stat_statements_info AS SELECT 1 AS sentinel','DROP VIEW extensions.pg_stat_statements_info; ALTER VIEW extensions.original_info RENAME TO pg_stat_statements_info','STATISTICS_OBJECT_OR_PRIVILEGE_CHANGED'),
])
def test_changed_provider_or_inherited_access_refuses(world,change,undo,code):
    b=world['boot']
    try:
        for q in split_sql(change+';'):b.execute(q)
        with pytest.raises(Exception,match=code):gate(b)
    finally:
        for q in split_sql(undo+';'):b.execute(q)


def test_latent_acl_is_not_usable_information_access(world):
    b=world['boot'];gate(b)
    for role in ('ingestion_worker_login','ingestion_effect_login'):
        b.execute(sql.SQL('ALTER ROLE {} LOGIN').format(sql.Identifier(role)))
        # World supplies temporary fixture-only passwords; never provider creds.
        with world['connect'](role) as c:
            for name in ('pg_stat_statements','pg_stat_statements_info'):
                with pytest.raises(Exception) as e:c.execute('SELECT 1 FROM extensions.'+name+' LIMIT 0')
                assert e.value.sqlstate=='42501'
        b.execute(sql.SQL('ALTER ROLE {} NOLOGIN').format(sql.Identifier(role)))


def test_changed_extension_c_symbol_refuses(world):
    b=world['boot']
    original=b.execute("SELECT pg_get_functiondef('extensions.pg_stat_statements_info()'::regprocedure)").fetchone()[0]
    changed=original.replace("'pg_stat_statements_info'", "'pg_stat_statements_1_11'")
    assert changed!=original
    try:
        b.execute(changed)
        with pytest.raises(Exception,match='STATISTICS_OBJECT_OR_PRIVILEGE_CHANGED'):gate(b)
    finally:b.execute(original)
