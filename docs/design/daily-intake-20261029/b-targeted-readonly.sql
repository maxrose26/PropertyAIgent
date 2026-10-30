-- Fixed supplement: no lifecycle functions are invoked. INACTIVE pending approval.
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='3s';
SET LOCAL lock_timeout='1s';
SET LOCAL idle_in_transaction_session_timeout='10s';
SET LOCAL search_path=pg_catalog;
SELECT 'context' AS section,current_user,session_user,current_database(),
 current_setting('transaction_read_only') AS read_only,
 current_setting('transaction_isolation') AS isolation,transaction_timestamp() AS observed_at,
 pg_has_role(current_user,'pg_read_all_stats','USAGE') AS full_stats_visibility,
 row_security_active('public.ingestion_work_items'::regclass) AS items_rls_active,
 row_security_active('public.ingestion_work_attempts'::regclass) AS attempts_rls_active;
WITH keys(key) AS (VALUES
 ('3f0dba235de9b9efcd52ef3b281ba8c967491f57824404c695ed2b32fae4c045'),
 ('e92a8e220bbbbcefb2425d6f97a60920bc447bc1fe097d600ea28e3e9d87588e'))
SELECT 'items' AS section,k.key,w.key IS NOT NULL AS found,w.state,w.phase,w.fence,w.owner,w.authority,
 w.lease_until AS lease_epoch,w.lease_until<=extract(epoch FROM transaction_timestamp()) AS lease_expired,
 w.attempt_count,w.checkpoint IS NOT NULL AS checkpoint_present,
 a.work_key IS NOT NULL AS matching_attempt_found,a.owner AS attempt_owner,a.authority AS attempt_authority,
 a.phase AS attempt_phase,a.started_at,a.finished_at,a.checkpoint IS NOT NULL AS attempt_checkpoint_present,
 a.owner=w.owner AND a.authority=w.authority AS attempt_identity_matches
FROM keys k LEFT JOIN public.ingestion_work_items w USING(key)
LEFT JOIN public.ingestion_work_attempts a ON a.work_key=w.key AND a.fence=w.fence ORDER BY k.key;
WITH sessions AS MATERIALIZED (
 SELECT pid,usename,state,backend_start,xact_start,backend_type
 FROM pg_stat_activity WHERE usename IN
 ('ingestion_worker_login','ingestion_effect_login','ingestion_application_login','ingestion_recovery_login')),
 bounded AS (SELECT * FROM sessions ORDER BY pid LIMIT 32)
SELECT 'sessions' AS section,(SELECT count(*) FROM sessions) AS total_count,
 count(*) AS reported_count,(SELECT count(*) FROM sessions)<=32 AS complete,
 coalesce(jsonb_agg(to_jsonb(bounded) ORDER BY pid),'[]'::jsonb) AS records FROM bounded;
WITH wanted(name) AS (VALUES ('ingestion_recovery_login'),('ingestion_recovery_operator'),('postgres')),
 target AS (SELECT to_regprocedure('public.ingestion_recover_abandoned(text,integer,boolean)')::oid AS oid)
SELECT 'recovery_access' AS section,w.name,r.oid IS NOT NULL AS role_found,r.rolcanlogin,r.rolvaliduntil,
 r.rolsuper,r.rolbypassrls,r.rolinherit,
 pg_has_role(r.oid,to_regrole('ingestion_recovery_operator'),'MEMBER') AS recovery_member,
 pg_has_role(r.oid,to_regrole('ingestion_recovery_operator'),'USAGE') AS recovery_inherited,
 pg_has_role(r.oid,to_regrole('ingestion_recovery_operator'),'SET') AS recovery_set_available,
 target.oid IS NOT NULL AS function_found,has_function_privilege(r.oid,target.oid,'EXECUTE') AS executable
FROM wanted w LEFT JOIN pg_roles r ON r.rolname=w.name CROSS JOIN target ORDER BY w.name;
WITH wanted(name) AS (VALUES ('ingestion_oldham_allowed'),('ingestion_recover_abandoned')),
 defs AS (SELECT p.*,pg_get_userbyid(p.proowner) AS owner FROM pg_proc p
 JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public')
SELECT 'functions' AS section,w.name,count(d.oid) AS overload_count,
 coalesce(jsonb_agg(jsonb_build_object('oid',d.oid,'arguments',pg_get_function_identity_arguments(d.oid),
 'sha256',encode(sha256(convert_to(d.prosrc,'UTF8')),'hex'),'owner',d.owner,
 'config',d.proconfig,'definer',d.prosecdef,'volatility',d.provolatile,
 'language',(SELECT lanname FROM pg_language WHERE oid=d.prolang),
 'worker_execute',has_function_privilege(to_regrole('ingestion_worker_login'),d.oid,'EXECUTE'),
 'effect_execute',has_function_privilege(to_regrole('ingestion_effect_login'),d.oid,'EXECUTE'),
 'public_execute',EXISTS(SELECT 1 FROM aclexplode(coalesce(d.proacl,acldefault('f',d.proowner))) a
 WHERE a.grantee=0 AND a.privilege_type='EXECUTE')) ORDER BY d.oid)
 FILTER(WHERE d.oid IS NOT NULL),'[]'::jsonb) AS definitions
FROM wanted w LEFT JOIN defs d ON d.proname=w.name GROUP BY w.name ORDER BY w.name;
WITH ctl AS (SELECT outcome::jsonb AS c FROM public.ingestion_work_items WHERE key=repeat('0',64)),
 snap AS (SELECT c,jsonb_build_object('global_stop',c->'global_stop','manual_stop',c->'manual_stop',
 'last_hard_stop',c->'last_hard_stop','hard_stop_generation',coalesce(c->'hard_stop_generation','0'::jsonb)) AS s FROM ctl)
SELECT 'stops' AS section,jsonb_typeof(c) AS control_type,
 c ? 'global_stop' AS global_field_present,c ? 'manual_stop' AS manual_field_present,
 c ? 'last_hard_stop' AS last_hard_stop_present,c ? 'hard_stop_generation' AS generation_present,
 (c->'global_stop' IS DISTINCT FROM 'null'::jsonb) AS intake_global_block,
 (c->>'manual_stop' IS NOT NULL) AS intake_manual_block,
 octet_length(s::text)<=4096 AS binding_complete,
 CASE WHEN octet_length(s::text)<=4096 THEN s ELSE NULL END AS exact_intake_stop_binding,
 encode(sha256(convert_to(s::text,'UTF8')),'hex') AS stop_binding_pg_jsonb_sha256,
 jsonb_typeof(c->'grants') AS grants_type,jsonb_typeof(c->'oldham_allowances') AS allowances_type
FROM snap;
WITH ctl AS (SELECT outcome::jsonb AS c FROM public.ingestion_work_items WHERE key=repeat('0',64)),
 names AS (SELECT key FROM ctl,jsonb_object_keys(CASE WHEN jsonb_typeof(c->'oldham_allowances')='object' THEN c->'oldham_allowances' ELSE '{}'::jsonb END) key
 UNION SELECT key FROM ctl,jsonb_object_keys(CASE WHEN jsonb_typeof(c->'grants')='object' THEN c->'grants' ELSE '{}'::jsonb END) key WHERE left(key,23)='INGESTION_CHAIN_OLDHAM_'),
 bounded AS (SELECT key FROM names ORDER BY key LIMIT 32),
 records AS (SELECT CASE WHEN length(key)<=100 THEN key ELSE NULL END AS authority,
 length(key)<=100 AS name_complete,c->'oldham_allowances' ? key AS allowance_present,
 c->'grants' ? key AS grant_present,c->'oldham_allowances'->key->'revoked' AS revoked,
 CASE WHEN (c->'oldham_allowances'->key->>'expires_at') ~ '^[0-9]{1,12}([.][0-9]{1,9})?$'
 THEN (c->'oldham_allowances'->key->>'expires_at')::numeric ELSE NULL END AS allowance_expiry,
 CASE WHEN (c->'grants'->key->>'expires_at') ~ '^[0-9]{1,12}([.][0-9]{1,9})?$'
 THEN (c->'grants'->key->>'expires_at')::numeric ELSE NULL END AS grant_expiry,
 (c->'oldham_allowances'->key->'grant_binding')=((c->'grants'->key)-ARRAY['source_calls','writes']) AS binding_matches
 FROM bounded CROSS JOIN ctl)
SELECT 'oldham_authorities' AS section,(SELECT count(*) FROM names) AS total_count,count(*) AS reported_count,
 (SELECT count(*) FROM names)<=32 AS complete,extract(epoch FROM transaction_timestamp()) AS observed_epoch,
 coalesce(jsonb_agg(to_jsonb(records) ORDER BY authority),'[]'::jsonb) AS records FROM records;
SELECT 'end' AS section,'READBACK_ONLY_NO_RECOVERY_OR_INSTALLATION' AS disposition;
ROLLBACK;
