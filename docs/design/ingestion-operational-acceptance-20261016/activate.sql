-- NEW OPERATIONAL REVIEW CANDIDATE, not the accepted base-storage activation.
-- Exact mappings/CA/credentials, installed SQL hashes, finite authority and
-- independently accepted global-stop decision must precede this activation.
BEGIN;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='10s';
DO $gate$
DECLARE login text; capability text; a record; allowed_insert text[]; allowed_update text[];
BEGIN
 allowed_insert:=ARRAY['council_code','reference','unit_confirmation_status','first_seen_at','last_seen_at','extraction_attempt_count','documents_legacy_unverified','evidence_refresh_required'];
 allowed_update:=ARRAY['status','decision','decision_issued_date','status_verified_at','planning_field_verification','last_seen_at','evidence_refresh_required','evidence_refresh_reason','evidence_refresh_trigger','evidence_refresh_requested_at'];
 FOR login,capability IN SELECT * FROM (VALUES
  ('ingestion_worker_login','ingestion_worker'),
  ('ingestion_effect_login','ingestion_effect_broker'),
  ('ingestion_application_login','ingestion_application_writer')) AS x(l,c) LOOP
  IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=login AND NOT rolcanlogin AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolbypassrls AND NOT rolreplication AND rolconnlimit=1)
  THEN RAISE EXCEPTION 'LOGIN_FLAGS_OR_PARTIAL_ACTIVATION'; END IF;
  IF (SELECT count(*) FROM pg_auth_members WHERE member=login::regrole)<>1
  OR NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE member=login::regrole AND roleid=capability::regrole AND NOT admin_option AND inherit_option AND NOT set_option)
  THEN RAISE EXCEPTION 'EXACT_RUNTIME_MEMBERSHIP'; END IF;
  IF pg_has_role(login,'ingestion_storage_owner','MEMBER') OR pg_has_role(login,'ingestion_authority_issuer','MEMBER') OR pg_has_role(login,'ingestion_barrier_releaser','MEMBER') OR pg_has_role(login,'ingestion_recovery_operator','MEMBER')
  THEN RAISE EXCEPTION 'FORBIDDEN_RUNTIME_MEMBERSHIP'; END IF;
  IF EXISTS(SELECT 1 FROM pg_namespace n WHERE n.nspname !~ '^pg_temp_' AND has_schema_privilege(login,n.oid,'CREATE')) THEN RAISE EXCEPTION 'AMBIENT_SCHEMA_CREATE'; END IF;
  IF EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_toast' AND n.nspname !~ '^pg_temp_' AND c.relkind IN ('r','p','v','m','f')
   AND (has_table_privilege(login,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_any_column_privilege(login,c.oid,'SELECT,INSERT,UPDATE,REFERENCES'))
   AND NOT (login='ingestion_worker_login' AND c.oid IN ('public.ingestion_work_items'::regclass,'public.ingestion_work_attempts'::regclass))
   AND NOT (login='ingestion_application_login' AND c.oid IN ('public.applications'::regclass,'public.application_lifecycle_events'::regclass)))
  THEN RAISE EXCEPTION 'AMBIENT_UNRELATED_TABLE_ACCESS'; END IF;
  IF EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind='S' AND n.nspname NOT IN ('pg_catalog','information_schema') AND CASE WHEN c.relkind='S' THEN has_sequence_privilege(login,c.oid,'USAGE,SELECT,UPDATE') ELSE false END AND NOT (login='ingestion_application_login' AND c.oid IN (pg_get_serial_sequence('public.applications','id')::regclass,pg_get_serial_sequence('public.application_lifecycle_events','id')::regclass))) THEN RAISE EXCEPTION 'AMBIENT_UNRELATED_SEQUENCE'; END IF;
  IF EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
   WHERE p.prosecdef AND n.nspname NOT IN ('pg_catalog','information_schema') AND has_function_privilege(login,p.oid,'EXECUTE')
   AND NOT (login='ingestion_worker_login' AND p.oid IN ('public.ingestion_raise_stop(text)'::regprocedure,'public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)'::regprocedure))
   AND NOT (login='ingestion_effect_login' AND p.oid='public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)'::regprocedure))
  THEN RAISE EXCEPTION 'AMBIENT_UNREVIEWED_DEFINER'; END IF;
 END LOOP;
 IF has_table_privilege('ingestion_worker_login','public.ingestion_work_items','INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_any_column_privilege('ingestion_worker_login','public.ingestion_work_items','INSERT,UPDATE,REFERENCES') OR has_table_privilege('ingestion_worker_login','public.ingestion_work_attempts','INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_any_column_privilege('ingestion_worker_login','public.ingestion_work_attempts','INSERT,UPDATE,REFERENCES') THEN RAISE EXCEPTION 'WORKER_DIRECT_LEDGER_MUTATION'; END IF;
 IF NOT has_function_privilege('ingestion_worker_login','public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)','EXECUTE') OR NOT has_function_privilege('ingestion_worker_login','public.ingestion_raise_stop(text)','EXECUTE') OR NOT has_function_privilege('ingestion_effect_login','public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)','EXECUTE') THEN RAISE EXCEPTION 'REQUIRED_RUNTIME_FUNCTION_MISSING'; END IF;
 FOR a IN SELECT attname FROM pg_attribute WHERE attrelid='public.application_lifecycle_events'::regclass AND attnum>0 AND NOT attisdropped AND attname<>'id' LOOP
  IF has_column_privilege('ingestion_application_login','public.application_lifecycle_events',a.attname,'SELECT') THEN RAISE EXCEPTION 'LIFECYCLE_READ_EXPANSION'; END IF;
 END LOOP;
 FOR a IN SELECT attname FROM pg_attribute WHERE attrelid='public.applications'::regclass AND attnum>0 AND NOT attisdropped LOOP
  IF (has_column_privilege('ingestion_application_login','public.applications',a.attname,'INSERT') AND NOT a.attname=ANY(allowed_insert))
  OR (has_column_privilege('ingestion_application_login','public.applications',a.attname,'UPDATE') AND NOT a.attname=ANY(allowed_update)) THEN RAISE EXCEPTION 'APPLICATION_COLUMN_EXPANSION'; END IF;
 END LOOP;
 IF has_any_column_privilege('ingestion_application_login','public.applications','REFERENCES') OR has_any_column_privilege('ingestion_application_login','public.application_lifecycle_events','UPDATE,REFERENCES') THEN RAISE EXCEPTION 'AMBIENT_APPLICATION_COLUMN_MUTATION'; END IF;
 IF has_sequence_privilege('ingestion_application_login',pg_get_serial_sequence('public.applications','id'),'SELECT,UPDATE') OR has_sequence_privilege('ingestion_application_login',pg_get_serial_sequence('public.application_lifecycle_events','id'),'SELECT,UPDATE') THEN RAISE EXCEPTION 'SEQUENCE_MUTATION_EXPANSION'; END IF;
 IF has_table_privilege('ingestion_application_login','public.applications','DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_table_privilege('ingestion_application_login','public.application_lifecycle_events','UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') THEN RAISE EXCEPTION 'APPLICATION_MUTATION_EXPANSION'; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='ingestion_recovery_login' AND NOT rolcanlogin) THEN RAISE EXCEPTION 'RECOVERY_MUST_REMAIN_DORMANT'; END IF;
END $gate$;
ALTER ROLE ingestion_worker_login LOGIN;
ALTER ROLE ingestion_effect_login LOGIN;
ALTER ROLE ingestion_application_login LOGIN;
COMMIT;
