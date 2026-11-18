BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '10s';
DO $owner_install_preflight$
DECLARE n integer; baseline_ok boolean;
BEGIN
 IF current_database() IS DISTINCT FROM 'postgres'
    OR session_user IS DISTINCT FROM 'postgres'
    OR current_user IS DISTINCT FROM 'postgres'
    OR (SELECT rolsuper OR NOT rolcreaterole OR NOT rolcreatedb OR NOT rolbypassrls
        FROM pg_catalog.pg_roles WHERE rolname=current_user)
 THEN RAISE EXCEPTION 'OWNER_WRITER_IDENTITY' USING ERRCODE='42501'; END IF;
 SELECT count(*),coalesce(bool_and(grantor<>'postgres'::regrole
       AND admin_option AND NOT inherit_option AND NOT set_option),false)
   INTO n,baseline_ok FROM pg_catalog.pg_auth_members
   WHERE member='postgres'::regrole AND roleid='ingestion_storage_owner'::regrole;
 IF n<>1 OR NOT baseline_ok
    OR pg_catalog.pg_has_role(current_user,'ingestion_storage_owner','USAGE')
    OR pg_catalog.pg_has_role(current_user,'ingestion_storage_owner','SET')
 THEN RAISE EXCEPTION 'OWNER_WRITER_ADMIN_ONLY_BASELINE' USING ERRCODE='42501'; END IF;
END $owner_install_preflight$;
DO $owner_schema_preflight$
BEGIN
 IF NOT pg_catalog.has_schema_privilege(current_user,'public','USAGE WITH GRANT OPTION')
    OR NOT pg_catalog.has_schema_privilege(current_user,'public','CREATE WITH GRANT OPTION')
 THEN RAISE EXCEPTION 'OWNER_WRITER_SCHEMA_CAPABILITY' USING ERRCODE='42501'; END IF;
END $owner_schema_preflight$;
GRANT ingestion_storage_owner TO postgres
 WITH ADMIN FALSE, INHERIT TRUE, SET TRUE GRANTED BY postgres;

DO $capacity_upgrade_guard$
DECLARE ctl jsonb;
BEGIN
 IF has_schema_privilege('ingestion_storage_owner','public','CREATE') THEN RAISE EXCEPTION 'CAPACITY_SCHEMA_BASELINE'; END IF;
 IF NOT pg_try_advisory_xact_lock(1886547824,20261103) THEN RAISE EXCEPTION 'OWNER_STATE_BUSY'; END IF;
 LOCK TABLE public.ingestion_work_items,public.ingestion_run_evidence IN SHARE ROW EXCLUSIVE MODE;
 SELECT outcome::jsonb INTO STRICT ctl FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE;
 IF (ctl->>'hard_stop_generation')::integer IS DISTINCT FROM 15
 OR ctl->'global_stop' IS DISTINCT FROM '{"reason":"DAILY_INTAKE_SHARED_FAILURE"}'::jsonb
 OR ctl->>'manual_stop' IS DISTINCT FROM 'ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP'
 OR ctl ? 'intake_run' THEN RAISE EXCEPTION 'CAPACITY_STOP15'; END IF;
 IF EXISTS(SELECT 1 FROM public.ingestion_work_items WHERE state IN ('CLAIMED','PERSISTENCE_UNCERTAIN') OR phase IN ('SOURCE_INTENT','WRITE_INTENT')) THEN RAISE EXCEPTION 'CAPACITY_ACTIVE_WORK'; END IF;
 IF EXISTS(SELECT 1 FROM pg_stat_activity WHERE usename IN ('ingestion_worker_login','ingestion_effect_login','ingestion_recovery_login','ingestion_application_login')) THEN RAISE EXCEPTION 'CAPACITY_ACTIVE_SESSION'; END IF;
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN ('ingestion_worker_login','ingestion_effect_login') AND rolcanlogin) THEN RAISE EXCEPTION 'CAPACITY_LOGIN'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.ingestion_run_evidence WHERE period='S4_FINITE_677f555670666bcf21f45860_owner' AND run_id='416cdc40d6837dbb772e2bcce514bf39' AND name='owner/state-018' AND sha256='0e6d08aa0b6e04c669998a828924e30322bab4ac73a0cf157a9d63b5fac955af' AND encode(sha256(body),'hex')=sha256)
 OR (SELECT name FROM public.ingestion_run_evidence WHERE period='S4_FINITE_677f555670666bcf21f45860_owner' AND run_id='416cdc40d6837dbb772e2bcce514bf39' ORDER BY name DESC LIMIT 1) IS DISTINCT FROM 'owner/state-019'
 OR (SELECT sha256 FROM public.ingestion_run_evidence WHERE period='S4_FINITE_677f555670666bcf21f45860_owner' AND run_id='416cdc40d6837dbb772e2bcce514bf39' AND name='owner/state-019' AND encode(sha256(body),'hex')=sha256) IS DISTINCT FROM 'UPGRADE_INTENT_SHA256'
 THEN RAISE EXCEPTION 'CAPACITY_CHECKPOINT_DRIFT'; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_proc WHERE oid='public.ingestion_intake_owner_state(text,text,text,bytea)'::regprocedure AND proowner='ingestion_storage_owner'::regrole AND prosecdef AND proconfig=ARRAY['search_path=pg_catalog'] AND encode(sha256(convert_to(prosrc,'UTF8')),'hex')='58cb6c34ca11c3aac50de1a0a51cdcf5a3ea5cdf8f3607075a25811f856f3dbd') THEN RAISE EXCEPTION 'CAPACITY_FUNCTION_DRIFT'; END IF;
END $capacity_upgrade_guard$;
GRANT CREATE ON SCHEMA public TO ingestion_storage_owner;
SET LOCAL ROLE ingestion_storage_owner;

CREATE OR REPLACE FUNCTION public.ingestion_intake_owner_state(p_period text,p_run text,p_previous text,p_body bytea)
RETURNS TABLE(ordinal integer,body bytea,sha256 text) LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $owner_state$
DECLARE prior public.ingestion_run_evidence%ROWTYPE; n integer; h text;
BEGIN
 IF session_user<>'postgres' THEN RAISE EXCEPTION 'OWNER_STATE_OWNER_ONLY' USING ERRCODE='42501'; END IF;
 IF p_period NOT IN ('S4_FINITE_677f555670666bcf21f45860_owner','b-dbpilot-20261027-1102-01_owner','b-dbpilot-20261027-1102-02_owner','b-dbpilot-20261027-1102-03_owner','b-dbpilot-20261027-1102-04_owner','b-dbpilot-20261027-1102-05_owner','b-dbpilot-20261027-1102-06_owner','b-dbpilot-20261027-1102-07_owner','b-dbpilot-20261027-1102-08_owner','b-dbpilot-20261027-1102-09_owner','b-dbpilot-20261027-1102-10_owner','b-bolton-20261103-1105-01_owner','b-qualification-20261104-01_owner','b-qualification-20261104-02_owner') OR p_run<>substr(encode(sha256(convert_to(p_period,'UTF8')),'hex'),1,32) THEN RAISE EXCEPTION 'OWNER_STATE_EXACT_PILOT'; END IF;
 -- Owner journal transactions must never wait for the period/controller lock:
 -- they preserve intent before that transaction starts, or ack after COMMIT.
 IF NOT pg_try_advisory_xact_lock(1886547824,20261103) THEN RAISE EXCEPTION 'OWNER_STATE_BUSY'; END IF;
 SELECT * INTO prior FROM public.ingestion_run_evidence d WHERE d.period=p_period AND d.run_id=p_run AND d.name LIKE 'owner/state-%' ORDER BY d.name DESC LIMIT 1;
 IF p_body IS NULL THEN
  IF prior.name IS NOT NULL THEN RETURN QUERY SELECT substring(prior.name from 13)::integer,prior.body,prior.sha256; END IF;
  RETURN;
 END IF;
 IF octet_length(p_body) NOT BETWEEN 1 AND (CASE WHEN p_period='S4_FINITE_677f555670666bcf21f45860_owner' THEN 51200 ELSE (CASE WHEN p_period='b-qualification-20261104-02_owner' THEN 36864 ELSE 32768 END) END) THEN RAISE EXCEPTION 'OWNER_STATE_VAULT_BOUND'; END IF;
 h:=encode(sha256(p_body),'hex');
 IF prior.name IS NOT NULL AND prior.body=p_body THEN
  RETURN QUERY SELECT substring(prior.name from 13)::integer,prior.body,prior.sha256;RETURN;
 END IF;
 IF coalesce(prior.sha256,'') IS DISTINCT FROM p_previous THEN RAISE EXCEPTION 'OWNER_STATE_CONCURRENT_OR_UNCERTAIN'; END IF;
 n:=CASE WHEN prior.name IS NULL THEN 0 ELSE substring(prior.name from 13)::integer+1 END;
 IF n>=64 THEN RAISE EXCEPTION 'OWNER_STATE_HISTORY_BOUND'; END IF;
 INSERT INTO public.ingestion_run_evidence(period,run_id,name,body,sha256) VALUES(p_period,p_run,'owner/state-'||lpad(n::text,3,'0'),p_body,h);
 RETURN QUERY SELECT n,p_body,h;
END $owner_state$;
REVOKE ALL ON FUNCTION public.ingestion_intake_owner_state(text,text,text,bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.ingestion_intake_owner_state(text,text,text,bytea) TO postgres;

RESET ROLE; REVOKE CREATE ON SCHEMA public FROM ingestion_storage_owner;
DO $capacity_schema_restore$ BEGIN IF has_schema_privilege('ingestion_storage_owner','public','CREATE') THEN RAISE EXCEPTION 'CAPACITY_SCHEMA_REMAINS'; END IF; END $capacity_schema_restore$;

REVOKE ingestion_storage_owner FROM postgres GRANTED BY postgres RESTRICT;
DO $owner_install_restored$
DECLARE n integer; baseline_ok boolean;
BEGIN
 SELECT count(*),coalesce(bool_and(grantor<>'postgres'::regrole
       AND admin_option AND NOT inherit_option AND NOT set_option),false)
   INTO n,baseline_ok FROM pg_catalog.pg_auth_members
   WHERE member='postgres'::regrole AND roleid='ingestion_storage_owner'::regrole;
 IF n<>1 OR NOT baseline_ok
    OR current_user IS DISTINCT FROM 'postgres'
    OR session_user IS DISTINCT FROM 'postgres'
    OR pg_catalog.pg_has_role(current_user,'ingestion_storage_owner','USAGE')
    OR pg_catalog.pg_has_role(current_user,'ingestion_storage_owner','SET')
 THEN RAISE EXCEPTION 'OWNER_WRITER_CAPABILITY_REMAINS' USING ERRCODE='42501'; END IF;
END $owner_install_restored$;
COMMIT;
