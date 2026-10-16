-- Run only AFTER separately approved secure credential mapping and audit review.
-- New logins have remained NOLOGIN throughout provisioning/mapping.
BEGIN;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='10s';
DO $gate$
DECLARE login text; capability text; n integer;
BEGIN
 FOR login,capability IN SELECT * FROM (VALUES
 ('ingestion_worker_login','ingestion_worker'),
 ('ingestion_storage_login','ingestion_storage_operator')) AS x(l,c) LOOP
  IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=login AND NOT rolcanlogin AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolbypassrls AND NOT rolreplication AND rolconnlimit=1)
  THEN RAISE EXCEPTION 'LOGIN_FLAGS_OR_PARTIAL_ACTIVATION'; END IF;
  IF (SELECT count(*) FROM pg_auth_members WHERE member=login::regrole)<>1
  OR NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE member=login::regrole AND roleid=capability::regrole AND NOT admin_option AND inherit_option AND NOT set_option)
  THEN RAISE EXCEPTION 'LOGIN_MEMBERSHIP'; END IF;
  IF pg_has_role(login,'ingestion_storage_owner','MEMBER')
  OR pg_has_role(login,'ingestion_authority_issuer','MEMBER')
  OR pg_has_role(login,'ingestion_barrier_releaser','MEMBER')
  THEN RAISE EXCEPTION 'FORBIDDEN_MEMBERSHIP'; END IF;
  -- Catalog scans are bounded by statement timeout; export no object contents.
  -- No DENY ACL exists: PUBLIC grants cannot be overridden for just this login.
  IF EXISTS(SELECT 1 FROM pg_namespace n WHERE n.nspname !~ '^pg_temp_' AND has_schema_privilege(login,n.oid,'CREATE'))
  THEN RAISE EXCEPTION 'UNREVIEWED_SCHEMA_CREATE'; END IF;
  IF EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_toast' AND n.nspname !~ '^pg_temp_' AND c.relkind IN ('r','p','v','m','f')
   AND c.oid NOT IN ('public.ingestion_work_items'::regclass,'public.ingestion_work_attempts'::regclass)
   AND (has_table_privilege(login,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_any_column_privilege(login,c.oid,'SELECT,INSERT,UPDATE,REFERENCES')))
  THEN RAISE EXCEPTION 'AMBIENT_NON_LEDGER_ACCESS'; END IF;
  IF EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
   WHERE p.prosecdef AND n.nspname NOT IN ('pg_catalog','information_schema')
   AND p.oid NOT IN ('public.ingestion_seed_storage_test()'::regprocedure,'public.ingestion_raise_stop(text)'::regprocedure)
   AND has_function_privilege(login,p.oid,'EXECUTE'))
  THEN RAISE EXCEPTION 'UNREVIEWED_SECURITY_DEFINER'; END IF;
 END LOOP;
END $gate$;
ALTER ROLE ingestion_worker_login LOGIN;
ALTER ROLE ingestion_storage_login LOGIN;
COMMIT;
