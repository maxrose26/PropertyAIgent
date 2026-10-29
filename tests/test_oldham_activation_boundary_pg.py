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
    if recovery=='absent':
        grants=b.execute("SELECT grantor::regrole::text FROM pg_database d CROSS JOIN LATERAL aclexplode(d.datacl) a WHERE d.datname=current_database() AND a.grantee='ingestion_recovery_login'::regrole").fetchall()
        for (grantor,) in grants:
            statement='REVOKE ALL ON DATABASE ingestion_provisioning_test FROM ingestion_recovery_login'
            if grantor==b.info.user:b.execute(statement)
            else:
                assert grantor=='provisioning_migrator'
                with world['connect'](grantor) as issuer:issuer.execute(statement)
        b.execute('DROP OWNED BY ingestion_recovery_login');b.execute('DROP ROLE ingestion_recovery_login')
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
        if recovery=='absent':b.execute('CREATE ROLE ingestion_recovery_login NOLOGIN')
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
    changed=original.replace("$function$pg_stat_statements_info$function$", "$function$pg_stat_statements_1_11$function$")
    assert changed!=original
    try:
        b.execute(changed)
        with pytest.raises(Exception,match='STATISTICS_OBJECT_OR_PRIVILEGE_CHANGED'):gate(b)
    finally:b.execute(original)


def test_nologin_does_not_hide_existing_recovery_session(world):
    b=world['boot'];b.execute('ALTER ROLE ingestion_recovery_login LOGIN')
    connection=world['connect']('ingestion_recovery_login')
    try:
        b.execute('ALTER ROLE ingestion_recovery_login NOLOGIN')
        with pytest.raises(Exception,match='RECOVERY_MUST_REMAIN_DORMANT'):gate(b)
    finally:connection.close()
    gate(b)


# --- search_path determinism of the reviewed view-definition comparison --------------------------------------------------------------------------------------------------------------
# Real pg_stat_statements 1.11 views in a schema named `extensions` and the ACTUAL derived gate (not a reduced example). It shows that the rendered definition, hence its MD5, depends on the session
# search_path; that the corrected gate compares the same reviewed hashes regardless; and that genuine changes still refuse. It does not reproduce, or prove anything about, the historical production failure.
REVIEWED={'pg_stat_statements':'ad1495ce5b4c54e4501e907a1f6aae8c','pg_stat_statements_info':'1807985dc152d2828720e1272d549775'}
PATHS=['pg_catalog','extensions, public','"$user", public, extensions','public']


def rendered(b,path):
    b.execute('SET search_path='+path)
    try:return {n:b.execute("SELECT md5(pg_get_viewdef(('extensions.'||%s)::regclass,true))",(n,)).fetchone()[0] for n in REVIEWED}
    finally:b.execute('RESET search_path')


def gate_under(b,path,text=None):
    b.execute('BEGIN READ ONLY');b.execute('SET LOCAL search_path='+path)
    try:
        for q in split_sql(text or activation_gate(True)):
            if q.lstrip().startswith('DO '):b.execute(q)
        return b.execute("SELECT current_setting('search_path')").fetchone()[0]
    finally:b.execute('ROLLBACK')


def test_rendering_differs_by_search_path_and_the_reviewed_hashes_correspond_to_pg_catalog(world):
    b=world['boot']
    pinned=rendered(b,'pg_catalog');assert pinned==REVIEWED      # the reviewed constants are the pg_catalog rendering
    shown=rendered(b,'extensions, public')
    assert shown!=pinned and all(shown[n]!=pinned[n] for n in REVIEWED)      # the same views hash differently when the provider schema is on the path (demonstrated, not assumed)
    assert rendered(b,'public')==pinned


@pytest.mark.parametrize('path',PATHS)
def test_corrected_gate_is_deterministic_across_session_search_paths_and_restores_the_caller_path(world,path):
    b=world['boot']
    inside=gate_under(b,path)      # raises on any refusal
    assert inside.replace(' ','').replace('"','')==path.replace(' ','').replace('"','')      # the caller's search_path is restored after the provider block


def test_the_regression_is_sensitive_the_unpinned_gate_refuses_when_the_provider_schema_is_on_the_path(world):
    b=world['boot']
    unpinned=activation_gate(True).replace("PERFORM set_config('search_path','pg_catalog',true);",'').replace("PERFORM set_config('search_path',stats_path,true);",'')
    gate_under(b,'pg_catalog',unpinned);gate_under(b,'public',unpinned)
    for path in ('extensions, public','"$user", public, extensions'):
        with pytest.raises(Exception,match='STATISTICS_OBJECT_OR_PRIVILEGE_CHANGED'):gate_under(b,path,unpinned)


@pytest.mark.parametrize('path',PATHS)
@pytest.mark.parametrize('change,undo,code',[
 ('ALTER VIEW extensions.pg_stat_statements SET (security_invoker=true)','ALTER VIEW extensions.pg_stat_statements RESET (security_invoker)','STATISTICS_OBJECT_OR_PRIVILEGE_CHANGED'),
 ('ALTER VIEW extensions.pg_stat_statements_info RENAME TO original_info; CREATE VIEW extensions.pg_stat_statements_info AS SELECT 1 AS sentinel','DROP VIEW extensions.pg_stat_statements_info; ALTER VIEW extensions.original_info RENAME TO pg_stat_statements_info','STATISTICS_OBJECT_OR_PRIVILEGE_CHANGED'),
 ('GRANT UPDATE ON extensions.pg_stat_statements_info TO ingestion_effect_broker','REVOKE UPDATE ON extensions.pg_stat_statements_info FROM ingestion_effect_broker','STATISTICS_OBJECT_OR_PRIVILEGE_CHANGED'),
 ('GRANT USAGE ON SCHEMA extensions TO ingestion_worker','REVOKE USAGE ON SCHEMA extensions FROM ingestion_worker','STATISTICS_BASELINE_BOUNDARY'),
 ('GRANT EXECUTE ON FUNCTION extensions.pg_stat_statements_reset(oid,oid,bigint,boolean) TO ingestion_worker','REVOKE EXECUTE ON FUNCTION extensions.pg_stat_statements_reset(oid,oid,bigint,boolean) FROM ingestion_worker','STATISTICS_FUNCTION_BOUNDARY')])
def test_real_changes_still_refuse_under_every_search_path(world,path,change,undo,code):
    b=world['boot']
    try:
        for q in split_sql(change+';'):b.execute(q)
        with pytest.raises(Exception,match=code):gate_under(b,path)
    finally:
        for q in split_sql(undo+';'):b.execute(q)


def test_a_changed_view_body_hashes_differently_under_the_pin_and_refuses(world):
    b=world['boot']
    original=b.execute("SELECT pg_get_viewdef('extensions.pg_stat_statements_info'::regclass,true)").fetchone()[0]
    try:
        b.execute('CREATE OR REPLACE VIEW extensions.pg_stat_statements_info AS SELECT dealloc,stats_reset FROM extensions.pg_stat_statements_info() WHERE false')
        assert rendered(b,'pg_catalog')['pg_stat_statements_info']!=REVIEWED['pg_stat_statements_info']
        for path in ('pg_catalog','extensions, public'):
            with pytest.raises(Exception,match='STATISTICS_OBJECT_OR_PRIVILEGE_CHANGED'):gate_under(b,path)
    finally:b.execute('CREATE OR REPLACE VIEW extensions.pg_stat_statements_info AS '+original.rstrip(';'))


# REDUCED example (no provider extension required, so it also runs on a plain disposable server): the exact pin/restore statements extracted from the derived gate, around a view over a function in a
# non-default schema. This proves the mechanism only; the real-extension tests above exercise the actual gate path.
@pytest.fixture
def bare_world():
    gen=disposable_world();w=next(gen);b=w['boot']
    try:
        b.execute('CREATE SCHEMA vdx');b.execute("CREATE FUNCTION vdx.f(showtext boolean) RETURNS TABLE(a int,b text) LANGUAGE sql AS $$ SELECT 1,'x' $$")
        b.execute('CREATE VIEW vdx.v AS SELECT a,b FROM vdx.f(true) AS f(a,b)')
        yield w
    finally:
        b.execute('DROP SCHEMA IF EXISTS vdx CASCADE')
        try:next(gen)
        except StopIteration:pass


def mini_gate(expected):
    text=activation_gate(True)
    pin=text[text.index("stats_path:=current_setting('search_path');"):text.index("PERFORM set_config('search_path','pg_catalog',true);")+len("PERFORM set_config('search_path','pg_catalog',true);")]
    restore="PERFORM set_config('search_path',stats_path,true);"
    assert text.count(pin)==1 and text.count(restore)==1
    return "DO $t$ DECLARE stats_path text; h text; BEGIN "+pin+" h:=md5(pg_get_viewdef('vdx.v'::regclass,true)); "+restore+" IF h<>'"+expected+"' THEN RAISE EXCEPTION 'REDUCED_VIEW_CHANGED'; END IF; END $t$"


def test_reduced_pin_pattern_is_deterministic_and_still_detects_a_changed_definition(bare_world):
    b=bare_world['boot']
    b.execute('SET search_path=pg_catalog');expected=b.execute("SELECT md5(pg_get_viewdef('vdx.v'::regclass,true))").fetchone()[0];b.execute('RESET search_path')
    b.execute('SET search_path=public, vdx');shown=b.execute("SELECT md5(pg_get_viewdef('vdx.v'::regclass,true))").fetchone()[0];b.execute('RESET search_path')
    assert shown!=expected      # the rendering really depends on the session search_path
    for path in PATHS+['vdx']:
        b.execute('BEGIN READ ONLY');b.execute('SET LOCAL search_path='+path)
        try:
            b.execute(mini_gate(expected))
            assert b.execute("SELECT current_setting('search_path')").fetchone()[0].replace(' ','').replace('"','')==path.replace(' ','').replace('"','')
        finally:b.execute('ROLLBACK')
    b.execute('CREATE OR REPLACE VIEW vdx.v AS SELECT a,b FROM vdx.f(false) AS f(a,b)')      # a genuine change to the definition
    for path in PATHS:
        b.execute('BEGIN READ ONLY');b.execute('SET LOCAL search_path='+path)
        try:
            with pytest.raises(Exception,match='REDUCED_VIEW_CHANGED'):b.execute(mini_gate(expected))
        finally:b.execute('ROLLBACK')
