-- Run only AFTER separately approved secure credential mapping and audit review.
-- New logins have remained NOLOGIN throughout provisioning/mapping.
BEGIN;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='10s';
SET LOCAL search_path=pg_catalog,public;
DO $gate$
DECLARE login text; capability text; n integer; stats record;
BEGIN
 FOR login,capability IN SELECT * FROM (VALUES
 ('ingestion_worker_login','ingestion_worker'),
 ('ingestion_effect_login','ingestion_effect_broker')) AS x(l,c) LOOP
  IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=login AND NOT rolcanlogin AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolbypassrls AND NOT rolreplication AND rolconnlimit=1)
  THEN RAISE EXCEPTION 'LOGIN_FLAGS_OR_PARTIAL_ACTIVATION'; END IF;
  IF (SELECT count(*) FROM pg_auth_members WHERE member=login::regrole)<>1
  OR NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE member=login::regrole AND roleid=capability::regrole AND NOT admin_option AND inherit_option AND NOT set_option)
  THEN RAISE EXCEPTION 'LOGIN_MEMBERSHIP'; END IF;
  IF pg_has_role(login,'ingestion_storage_owner','MEMBER')
  OR pg_has_role(login,'ingestion_authority_issuer','MEMBER')
  OR pg_has_role(login,'ingestion_barrier_releaser','MEMBER')
  THEN RAISE EXCEPTION 'FORBIDDEN_MEMBERSHIP'; END IF;
  IF has_table_privilege(login,'public.ingestion_work_items','INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN')
  OR has_any_column_privilege(login,'public.ingestion_work_items','INSERT,UPDATE,REFERENCES')
  OR has_table_privilege(login,'public.ingestion_work_attempts','INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN')
  OR has_any_column_privilege(login,'public.ingestion_work_attempts','INSERT,UPDATE,REFERENCES')
  THEN RAISE EXCEPTION 'RUNTIME_DIRECT_LEDGER_MUTATION'; END IF;
  IF login='ingestion_effect_login' AND (has_table_privilege(login,'public.ingestion_work_items','SELECT') OR has_any_column_privilege(login,'public.ingestion_work_items','SELECT') OR has_table_privilege(login,'public.ingestion_work_attempts','SELECT') OR has_any_column_privilege(login,'public.ingestion_work_attempts','SELECT'))
  THEN RAISE EXCEPTION 'BROKER_DIRECT_LEDGER_READ'; END IF;
  IF EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind='S' AND n.nspname NOT IN ('pg_catalog','information_schema') AND has_sequence_privilege(login,c.oid,'USAGE,SELECT,UPDATE'))
  THEN RAISE EXCEPTION 'RUNTIME_SEQUENCE_ACCESS'; END IF;
  -- Exact latent SELECT ACLs only: schema lookup must remain DENIED. No new
  -- USAGE/SELECT grant, query-text retrieval, or statistics function invocation.
  IF to_regclass('extensions.pg_stat_statements') IS NOT NULL
     OR to_regclass('extensions.pg_stat_statements_info') IS NOT NULL THEN
   IF NOT EXISTS(SELECT 1 FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace
     WHERE e.extname='pg_stat_statements' AND e.extversion='1.11' AND n.nspname='extensions')
     OR (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
       WHERE n.nspname='extensions' AND c.relname IN ('pg_stat_statements','pg_stat_statements_info'))<>2
     OR has_schema_privilege(login,'extensions','USAGE,CREATE')
     OR pg_has_role(login,'pg_read_all_stats','MEMBER')
     OR pg_has_role(login,'pg_monitor','MEMBER')
   THEN RAISE EXCEPTION 'STATISTICS_BASELINE_BOUNDARY'; END IF;
   FOR stats IN SELECT c.*,v.expected FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
     JOIN (VALUES ('pg_stat_statements','ad1495ce5b4c54e4501e907a1f6aae8c'),
                  ('pg_stat_statements_info','1807985dc152d2828720e1272d549775')) v(name,expected)
       ON c.relname=v.name WHERE n.nspname='extensions' LOOP
    IF stats.relkind<>'v' OR stats.reloptions IS NOT NULL
      OR md5(pg_get_viewdef(stats.oid,true))<>stats.expected
      OR NOT EXISTS(SELECT 1 FROM pg_depend d JOIN pg_extension e ON e.oid=d.refobjid
        WHERE d.classid='pg_class'::regclass AND d.objid=stats.oid AND d.deptype='e' AND e.extname='pg_stat_statements')
      OR has_table_privilege(login,stats.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN,SELECT WITH GRANT OPTION')
      OR has_any_column_privilege(login,stats.oid,'INSERT,UPDATE,REFERENCES,SELECT WITH GRANT OPTION')
    THEN RAISE EXCEPTION 'STATISTICS_OBJECT_OR_PRIVILEGE_CHANGED'; END IF;
   END LOOP;
   IF (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
     WHERE n.nspname='extensions' AND p.proname IN ('pg_stat_statements','pg_stat_statements_info','pg_stat_statements_reset'))<>3
     OR EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
       WHERE n.nspname='extensions' AND p.proname IN ('pg_stat_statements','pg_stat_statements_info','pg_stat_statements_reset')
       AND (p.prosecdef OR p.probin IS DISTINCT FROM '$libdir/pg_stat_statements'
         OR p.prosrc NOT IN ('pg_stat_statements_1_11','pg_stat_statements_info','pg_stat_statements_reset_1_11')
         OR (p.proname='pg_stat_statements_reset' AND has_function_privilege(login,p.oid,'EXECUTE'))))
   THEN RAISE EXCEPTION 'STATISTICS_FUNCTION_BOUNDARY'; END IF;
  END IF;
  -- Catalog scans are bounded by statement timeout; export no object contents.
  -- No DENY ACL exists: PUBLIC grants cannot be overridden for just this login.
  IF EXISTS(SELECT 1 FROM pg_namespace n WHERE n.nspname !~ '^pg_temp_' AND has_schema_privilege(login,n.oid,'CREATE'))
  THEN RAISE EXCEPTION 'UNREVIEWED_SCHEMA_CREATE'; END IF;
  IF EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_toast' AND n.nspname !~ '^pg_temp_' AND c.relkind IN ('r','p','v','m','f')
   AND c.oid NOT IN ('public.ingestion_work_items'::regclass,'public.ingestion_work_attempts'::regclass)
   AND NOT (n.nspname='extensions' AND c.relname IN ('pg_stat_statements','pg_stat_statements_info'))
   AND (has_table_privilege(login,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_any_column_privilege(login,c.oid,'SELECT,INSERT,UPDATE,REFERENCES')))
  THEN RAISE EXCEPTION 'AMBIENT_NON_LEDGER_ACCESS'; END IF;
  IF EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
   WHERE p.prosecdef AND n.nspname NOT IN ('pg_catalog','information_schema')
   AND p.oid NOT IN ('public.ingestion_raise_stop(text)'::regprocedure,'public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)'::regprocedure)
   AND has_function_privilege(login,p.oid,'EXECUTE'))
  THEN RAISE EXCEPTION 'UNREVIEWED_SECURITY_DEFINER'; END IF;
 END LOOP;
END $gate$;
ALTER ROLE ingestion_worker_login LOGIN;
ALTER ROLE ingestion_effect_login LOGIN;
COMMIT;

