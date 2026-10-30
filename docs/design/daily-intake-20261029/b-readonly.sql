-- REVIEW PROPOSAL ONLY. NOT AUTHORISED FOR EXECUTION.
-- Candidate c47b829ab766d2bdc7dfb329b9384c403ecb6a7d.
-- Use existing psql (not a lifecycle command), one connection, no retry.
-- Required before later approval: exact existing login/route/IPv4/CA,
-- verify-full client TLS, hidden password prompt, psql -X and ON_ERROR_STOP=1.
-- Proposed client bounds: outer deadline 60s; connect_timeout=5; output 64KiB.
-- This SQL sets server/row bounds only. The later approved client invocation
-- must enforce the outer deadline and aggregate output ceiling separately.
-- Do not place a password/connection URL in arguments, logs or this file.
-- 16 statements: BEGIN + four SET LOCAL + ten SELECT + ROLLBACK.
-- Server READ ONLY does not turn an administrative login into a restricted login.
-- A permission error stops the inspection: NO GRANT, SET ROLE or fallback.
-- No application data, password/verifier, query text, function bodies or raw
-- checkpoints/control JSON is exported. Local output must stay owner-private.

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '3s';
SET LOCAL lock_timeout = '1s';
SET LOCAL idle_in_transaction_session_timeout = '10s';
SET LOCAL search_path = pg_catalog;

-- Q1: identity and own transport. Client verify-full must be recorded separately.
SELECT current_user, session_user, current_database(),
       current_setting('transaction_read_only') AS read_only,
       current_setting('transaction_isolation') AS isolation,
       current_setting('server_version_num') AS server_version_num,
       statement_timestamp() AS observed_at,
       (SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()) AS backend_tls,
       has_table_privilege(current_user,to_regclass('public.ingestion_work_items'),'SELECT') AS can_read_items,
       has_table_privilege(current_user,to_regclass('public.ingestion_work_attempts'),'SELECT') AS can_read_attempts;

-- Q2: only the two B logins. No pg_authid/password read.
SELECT rolname,rolcanlogin,rolvaliduntil,rolconnlimit,rolsuper,
       rolcreaterole,rolcreatedb,rolbypassrls,rolreplication,rolinherit
FROM pg_roles WHERE rolname IN ('ingestion_worker_login','ingestion_effect_login')
ORDER BY rolname LIMIT 3;

-- Q3: only recognised timeout settings, including database-specific overrides.
-- Unrecognised values are marked, not echoed; >30 rows is incomplete.
SELECT r.rolname,s.setdatabase AS database_oid,split_part(v,'=',1) AS setting,
       CASE WHEN split_part(v,'=',2) ~ '^[0-9]{1,9}(ms|s|min|h|d)?$'
            THEN split_part(v,'=',2) ELSE 'UNRECOGNISED_NOT_EXPORTED' END AS value
FROM pg_db_role_setting s JOIN pg_roles r ON r.oid=s.setrole
CROSS JOIN LATERAL unnest(s.setconfig) v
WHERE r.rolname IN ('ingestion_worker_login','ingestion_effect_login')
AND split_part(v,'=',1) IN ('statement_timeout','lock_timeout','idle_in_transaction_session_timeout')
ORDER BY 1,2,3 LIMIT 31;

-- Q4: membership paths can confer privilege indirectly; retain direct edges
-- and test inherited privileged capabilities independently in Q5.
SELECT m.rolname AS member,r.rolname AS role,a.admin_option
FROM pg_auth_members a JOIN pg_roles m ON m.oid=a.member
JOIN pg_roles r ON r.oid=a.roleid
WHERE m.rolname IN ('ingestion_worker_login','ingestion_effect_login')
ORDER BY 1,2 LIMIT 33;

-- Q5: capability USAGE/MEMBER, including indirect membership.
-- SET-role semantics require version-specific interpretation; no SET ROLE occurs.
SELECT l.rolname AS login,r.rolname AS capability,
pg_has_role(l.oid,r.oid,'USAGE') AS inherited,
pg_has_role(l.oid,r.oid,'MEMBER') AS member
FROM pg_roles l CROSS JOIN pg_roles r
WHERE l.rolname IN ('ingestion_worker_login','ingestion_effect_login')
AND r.rolname IN ('ingestion_worker','ingestion_effect_broker',
'ingestion_storage_owner','ingestion_authority_issuer','ingestion_barrier_releaser',
'ingestion_recovery_operator','ingestion_storage_operator') ORDER BY 1,2 LIMIT 15;

-- Q6: entire daily-intake fingerprint set, not only the three replacements.
-- Missing/overloaded functions are visible. Hashes below are prosrc UTF-8 SHA256.
WITH expected(name,sha) AS (VALUES
('ingestion_acceptance_control','f25822db425df0c125df975d1cb46cfc710b76999744304d45d7037292d77d17'),
('ingestion_bolton_allowed','09d3e0e8e87bbf158bb89cb683063a21e5e8c23076d342961d49b50ac7e60569'),
('ingestion_register_bolton_exception','dba6b809c50b9bd937b2f509fc05c20de9d69499ca4394e9007ef3af196b481c'),
('ingestion_raise_stop','5e41868876be6c533a31a8f7af25442ce308cb42681210296d516f361521e53a'),
('ingestion_worker_step','abb46082f6d0891e131271a2567d45d8afdeccfd4561a6692baece7c3759c5bf'),
('ingestion_recover_abandoned','9e7f98210c737d6f8f7fae2d98e328261ab9faf31481f041b6f63befa6686f58'))
SELECT e.name,p.oid,encode(sha256(convert_to(p.prosrc,'UTF8')),'hex') AS observed_sha256,
encode(sha256(convert_to(p.prosrc,'UTF8')),'hex')=e.sha AS body_matches,
pg_get_userbyid(p.proowner)='ingestion_storage_owner' AS owner_matches,
p.proconfig=ARRAY['search_path=pg_catalog']::text[] AS search_path_matches,
p.prosecdef=(e.name<>'ingestion_bolton_allowed') AS definer_matches,
count(p.oid) OVER (PARTITION BY e.name) AS overload_count
FROM expected e LEFT JOIN pg_proc p ON p.proname=e.name
AND p.pronamespace=(SELECT oid FROM pg_namespace WHERE nspname='public')
ORDER BY e.name,p.oid LIMIT 25;

-- Q7: exact runtime EXECUTE rights for the same six functions.
SELECT r.rolname,p.proname,p.oid,has_function_privilege(r.oid,p.oid,'EXECUTE') AS executable
FROM pg_roles r CROSS JOIN pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE r.rolname IN ('ingestion_worker_login','ingestion_effect_login')
AND n.nspname='public' AND p.proname IN ('ingestion_acceptance_control',
'ingestion_bolton_allowed','ingestion_register_bolton_exception',
'ingestion_raise_stop','ingestion_worker_step','ingestion_recover_abandoned')
ORDER BY 1,2,3 LIMIT 49;

-- Q8: table/column privilege enquiries, no table contents.
SELECT r.rolname,c.relname,
c.relrowsecurity,c.relforcerowsecurity,row_security_active(c.oid) AS observer_rls_active,
has_table_privilege(r.oid,c.oid,'SELECT') AS table_select,
has_any_column_privilege(r.oid,c.oid,'SELECT') AS any_column_select,
has_table_privilege(r.oid,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') AS any_table_write,
has_any_column_privilege(r.oid,c.oid,'INSERT,UPDATE,REFERENCES') AS any_column_write
FROM pg_roles r CROSS JOIN pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE r.rolname IN ('ingestion_worker_login','ingestion_effect_login')
AND n.nspname='public' AND c.relname IN ('ingestion_work_items','ingestion_work_attempts')
ORDER BY 1,2 LIMIT 5;

-- Q9: control projection only. Existing SELECT privilege is required.
-- Zero rows, wrong JSON types, or NULL required observations are UNKNOWN.
-- No stored function is invoked; missing access aborts instead of adding grants.
WITH c AS (SELECT outcome::jsonb AS j FROM public.ingestion_work_items
WHERE key=repeat('0',64))
SELECT jsonb_typeof(j) AS control_type,
j->'global_stop' IS NOT NULL AND j->'global_stop'<>'null'::jsonb AS global_stop_present,
j->'manual_stop' IS NOT NULL AND j->'manual_stop'<>'null'::jsonb AS manual_stop_present,
j->'last_hard_stop' IS NOT NULL AND j->'last_hard_stop'<>'null'::jsonb AS last_hard_stop_present,
jsonb_typeof(j->'grants') AS grants_type,
jsonb_typeof(j->'intake_periods') AS periods_type,
CASE WHEN j#>>'{intake_run,state}' IN ('OPEN','VERIFIED') THEN j#>>'{intake_run,state}'
     WHEN j->'intake_run' IS NULL OR j->'intake_run'='null'::jsonb THEN 'ABSENT'
     ELSE 'UNKNOWN_NOT_EXPORTED' END AS intake_run_state,
encode(sha256(convert_to(coalesce((j->'intake_run')::text,'ABSENT'),'UTF8')),'hex') AS intake_run_sha256,
encode(sha256(convert_to(jsonb_build_object('global_stop',j->'global_stop',
'manual_stop',j->'manual_stop','last_hard_stop',j->'last_hard_stop',
'hard_stop_generation',j->'hard_stop_generation')::text,'UTF8')),'hex') AS stop_projection_sha256,
(SELECT count(*) FROM jsonb_each(CASE WHEN jsonb_typeof(j->'grants')='object'
THEN j->'grants' ELSE '{}'::jsonb END)) AS grant_count,
(SELECT count(*) FROM jsonb_each(CASE WHEN jsonb_typeof(j->'grants')='object'
THEN j->'grants' ELSE '{}'::jsonb END) g
WHERE CASE WHEN jsonb_typeof(g.value->'expires_at')='number'
THEN (g.value->>'expires_at')::numeric > extract(epoch FROM statement_timestamp())
ELSE true END) AS unexpired_or_unreadable_grants
FROM c LIMIT 2;

-- Q10: bounded operational-state projection across unfinished work; no subject,
-- proposal, address, source body or checkpoint content. Global unfinished work
-- matters to the shared barrier; this is not unrelated application-table data.
-- 201 rows means INCOMPLETE: do not infer absence or auto-page/retry.
SELECT key,
CASE WHEN state IN ('QUEUED','RUNNING','CLAIMED','COMPLETE','CONTROL','SAFETY_BLOCKED',
'PERSISTENCE_UNCERTAIN','UNSUPPORTED_CONTRACT','FAILED','DEFERRED')
THEN state ELSE 'OTHER_NOT_EXPORTED' END AS state,
CASE WHEN phase IN ('IDLE','CLAIMED','SOURCE_INTENT','WRITE_INTENT','FINISHED','RECOVERED')
THEN phase ELSE 'OTHER_NOT_EXPORTED' END AS phase,
phase='SOURCE_INTENT' AS unresolved_source_intent,
phase='WRITE_INTENT' AS unresolved_write_intent,
attempt_count,checkpoint IS NOT NULL AS checkpoint_present,
encode(sha256(convert_to(coalesce(checkpoint::text,'ABSENT'),'UTF8')),'hex') AS checkpoint_sha256,
lease_until IS NOT NULL AS lease_recorded
FROM public.ingestion_work_items
WHERE key<>repeat('0',64) AND (state<>'COMPLETE' OR phase IN ('SOURCE_INTENT','WRITE_INTENT'))
ORDER BY key LIMIT 201;

ROLLBACK;

-- LIMITATIONS: no password presence, no other-session visibility assertion,
-- no restricted-login authentication proof, no readback of remote archive,
-- no complete checkpoints if 201-row sentinel reached. Stop digest is a SQL
-- observation, NOT the application's canonical binding digest.
-- RLS-active observations cannot establish global absence without a separately
-- verified applicable SELECT policy. This proposal never bypasses RLS.
-- Missing tables/privileges abort this transaction. Never repair in this script.
