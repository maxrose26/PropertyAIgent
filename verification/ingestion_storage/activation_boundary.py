"""Closed capture/screening gate derivation. No SQL installation or ACL changes."""
from pathlib import Path
from app.ingestion.ledger import Denied

STORAGE_GATE=Path('docs/design/ingestion-provisioning-20261016/activate.sql')
GATE_CODES=frozenset({
 'LOGIN_FLAGS_OR_PARTIAL_ACTIVATION','EXACT_RUNTIME_MEMBERSHIP',
 'FORBIDDEN_RUNTIME_MEMBERSHIP','AMBIENT_SCHEMA_CREATE',
 'AMBIENT_UNRELATED_TABLE_ACCESS','AMBIENT_UNRELATED_SEQUENCE',
 'AMBIENT_UNREVIEWED_DEFINER','WORKER_DIRECT_LEDGER_MUTATION',
 'REQUIRED_RUNTIME_FUNCTION_MISSING','RECOVERY_MUST_REMAIN_DORMANT',
 'STATISTICS_BASELINE_BOUNDARY','STATISTICS_OBJECT_OR_PRIVILEGE_CHANGED',
 'STATISTICS_FUNCTION_BOUNDARY'})


def fixed_gate_reason(exc):
    """Only an exact server primary message from P0001 at the gate boundary."""
    import psycopg
    original=getattr(exc,'orig',exc)
    if not isinstance(original,psycopg.Error) or original.sqlstate!='P0001':return None
    reason=getattr(original.diag,'message_primary',None)
    return reason if isinstance(reason,str) and reason in GATE_CODES else None


def capture_screening_gate(text):
    """Mechanically reuse the reviewed latent-statistics guard, not name-only ACLs."""
    original=STORAGE_GATE.read_text()
    first="  IF to_regclass('extensions.pg_stat_statements') IS NOT NULL"
    last='  -- Catalog scans are bounded by statement timeout; export no object contents.'
    if original.count(first)!=1 or original.count(last)!=1:raise Denied('ACTIVATION_BOUNDARY_DERIVATION')
    stats=original[original.index(first):original.index(last)]
    # Resolve only catalogue identities: the inspector and runtime deliberately
    # have no USAGE on this provider schema. Name resolution via to_regclass
    # itself checks USAGE, before any reviewed metadata predicate can run.
    old_presence="  IF to_regclass('extensions.pg_stat_statements') IS NOT NULL\n     OR to_regclass('extensions.pg_stat_statements_info') IS NOT NULL THEN"
    if stats.count(old_presence)!=1:raise Denied('ACTIVATION_BOUNDARY_DERIVATION')
    stats=stats.replace(old_presence,"  IF EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='extensions' AND c.relname IN ('pg_stat_statements','pg_stat_statements_info')) THEN")
    # In addition to reviewed view hashes, all three C functions must be members
    # of the SAME extension, owned by its owner, with exact reviewed symbols.
    marker="   THEN RAISE EXCEPTION 'STATISTICS_FUNCTION_BOUNDARY'; END IF;"
    extra="""   IF EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
      JOIN pg_extension e ON e.extname='pg_stat_statements'
      WHERE n.nspname='extensions' AND p.proname IN ('pg_stat_statements','pg_stat_statements_info','pg_stat_statements_reset')
      AND (p.proowner<>e.extowner OR p.proconfig IS NOT NULL OR p.prokind<>'f'
        OR (SELECT lanname FROM pg_language WHERE oid=p.prolang)<>'c'
        OR NOT EXISTS(SELECT 1 FROM (VALUES
          ('pg_stat_statements','pg_stat_statements_1_11','16',2249,true),
          ('pg_stat_statements_info','pg_stat_statements_info','',2249,false),
          ('pg_stat_statements_reset','pg_stat_statements_reset_1_11','26 26 20 16',1184,false))
          x(name,symbol,args,result,setof) WHERE p.proname=x.name AND p.prosrc=x.symbol
            AND p.proargtypes::text=x.args AND p.prorettype=x.result::oid AND p.proretset=x.setof)
        OR NOT EXISTS(SELECT 1 FROM pg_depend d
        WHERE d.classid='pg_proc'::regclass AND d.objid=p.oid AND d.refclassid='pg_extension'::regclass AND d.refobjid=e.oid AND d.deptype='e')))
      OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_extension e ON e.extname='pg_stat_statements'
        WHERE n.nspname='extensions' AND c.relname IN ('pg_stat_statements','pg_stat_statements_info') AND c.relowner<>e.extowner)
   THEN RAISE EXCEPTION 'STATISTICS_OBJECT_OR_PRIVILEGE_CHANGED'; END IF;
"""
    if stats.count(marker)!=1:raise Denied('ACTIVATION_BOUNDARY_DERIVATION')
    stats=stats.replace(marker,marker+'\n'+extra)
    # pg_get_viewdef (hence the reviewed MD5) renders extension-schema function names unqualified when that schema is on the session search_path. Pin pg_catalog for
    # this provider block ONLY, restoring the caller's value afterwards: every other reference in the gate is schema-qualified or a role name, so nothing else changes.
    stats="  stats_path:=current_setting('search_path');\n  PERFORM set_config('search_path','pg_catalog',true);\n"+stats+"  PERFORM set_config('search_path',stats_path,true);\n"
    declaration='allowed_update text[];'
    insertion="  IF EXISTS(SELECT 1 FROM pg_namespace n WHERE"
    table="   AND NOT (login='ingestion_application_login' AND c.oid IN ('public.applications'::regclass,'public.application_lifecycle_events'::regclass)))"
    recovery=" IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='ingestion_recovery_login' AND NOT rolcanlogin) THEN RAISE EXCEPTION 'RECOVERY_MUST_REMAIN_DORMANT'; END IF;"
    if any(text.count(x)!=1 for x in (declaration,insertion,table,recovery)):raise Denied('ACTIVATION_BOUNDARY_DERIVATION')
    text=text.replace(declaration,declaration+' stats record; stats_path text;').replace(insertion,stats+insertion)
    text=text.replace(table,table[:-1]+"\n   AND NOT (n.nspname='extensions' AND c.relname IN ('pg_stat_statements','pg_stat_statements_info')))")
    # Missing is safe only for this non-recovery operation. Existing recovery
    # identities must have no authentication, administrative flags or extra roles.
    text=text.replace(recovery,""" IF EXISTS(SELECT 1 FROM pg_stat_activity recovery_session
   WHERE recovery_session.usename='ingestion_recovery_login' OR
     (recovery_session.usesysid IS NOT NULL AND NOT EXISTS(SELECT 1 FROM pg_roles r WHERE r.oid=recovery_session.usesysid)))
 THEN RAISE EXCEPTION 'RECOVERY_MUST_REMAIN_DORMANT'; END IF;
 IF EXISTS(SELECT 1 FROM pg_roles r WHERE r.rolname='ingestion_recovery_login' AND
   (r.rolcanlogin OR r.rolsuper OR r.rolcreaterole OR r.rolcreatedb OR r.rolbypassrls OR r.rolreplication
    OR r.rolconnlimit<>1
    OR EXISTS(SELECT 1 FROM pg_auth_members m WHERE m.member=r.oid AND
      (m.roleid IS DISTINCT FROM to_regrole('ingestion_recovery_operator') OR m.admin_option OR NOT m.inherit_option OR m.set_option))
    OR pg_has_role(r.oid,'ingestion_storage_owner','MEMBER')
    OR pg_has_role(r.oid,'ingestion_authority_issuer','MEMBER')
    OR pg_has_role(r.oid,'ingestion_barrier_releaser','MEMBER')
    OR pg_has_role(r.oid,'pg_read_all_stats','MEMBER') OR pg_has_role(r.oid,'pg_monitor','MEMBER')
    OR EXISTS(SELECT 1 FROM pg_namespace n WHERE n.nspname !~ '^pg_temp_' AND has_schema_privilege(r.oid,n.oid,'CREATE'))
    OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_toast' AND n.nspname !~ '^pg_temp_'
      AND c.relkind IN ('r','p','v','m','f') AND
      (has_table_privilege(r.oid,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_any_column_privilege(r.oid,c.oid,'INSERT,UPDATE,REFERENCES')
       OR ((has_table_privilege(r.oid,c.oid,'SELECT') OR has_any_column_privilege(r.oid,c.oid,'SELECT')) AND NOT (n.nspname='extensions' AND c.relname IN ('pg_stat_statements','pg_stat_statements_info')))))
    OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind='S'
      AND n.nspname NOT IN ('pg_catalog','information_schema') AND CASE WHEN c.relkind='S' THEN has_sequence_privilege(r.oid,c.oid,'USAGE,SELECT,UPDATE') ELSE false END)
    OR EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
      WHERE p.prosecdef AND n.nspname NOT IN ('pg_catalog','information_schema') AND has_function_privilege(r.oid,p.oid,'EXECUTE')
      AND p.oid IS DISTINCT FROM to_regprocedure('public.ingestion_recover_abandoned(text,integer,boolean)'))
    OR EXISTS(SELECT 1 FROM pg_namespace n WHERE n.nspname='extensions' AND has_schema_privilege(r.oid,n.oid,'USAGE'))))
 THEN RAISE EXCEPTION 'RECOVERY_MUST_REMAIN_DORMANT'; END IF;""")
    return text


def reviewed_control_attributes():
    """Volatility defaults to VOLATILE when the authoritative SQL omits it."""
    source=Path('docs/design/ingestion-operational-20261016/worker.sql').read_text()
    statement=source.split('CREATE FUNCTION public.ingestion_acceptance_control()',1)[1].split('$diagnostic$;',1)[0]
    header=statement.split('AS $diagnostic$',1)[0]
    if 'LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog' not in header:raise Denied('CONTROL_REVIEWED_DEFINITION_CHANGED')
    volatility='s' if ' STABLE ' in header else 'i' if ' IMMUTABLE ' in header else 'v'
    return dict(language='sql',volatility=volatility,security_definer=True)
