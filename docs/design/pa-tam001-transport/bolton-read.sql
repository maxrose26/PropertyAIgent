BEGIN READ ONLY;
SET LOCAL statement_timeout = '10s';
SET LOCAL lock_timeout = '3s';

-- Q1: identity, actual safeguards and controller bindings; no raw payload.
SELECT session_user, current_user, current_database(),
 current_setting('transaction_read_only') AS read_only,
 current_setting('statement_timeout') AS statement_timeout,
 current_setting('lock_timeout') AS lock_timeout,
 outcome::jsonb->'global_stop' AS global_stop,
 outcome::jsonb->'manual_stop' AS manual_stop,
 outcome::jsonb->'last_hard_stop' AS last_hard_stop,
 outcome::jsonb->'hard_stop_generation' AS generation,
 outcome::jsonb->'intake_run'->>'period' AS period,
 outcome::jsonb->'intake_run'->>'id' AS run_id,
 outcome::jsonb->'intake_run'->>'state' AS run_state,
 encode(sha256(convert_to(outcome::jsonb::text,'UTF8')),'hex') AS controller_sha
FROM public.ingestion_work_items WHERE key=repeat('0',64);

-- Q2: exact unfinished identity/attempt evidence; total detects >8 overflow.
WITH candidates AS (
 SELECT w.*, count(*) OVER () AS total
 FROM public.ingestion_work_items w
 WHERE w.state='CLAIMED'
    OR w.phase IN ('SOURCE_INTENT','WRITE_INTENT')
    OR w.state='PERSISTENCE_UNCERTAIN'
 ORDER BY w.key LIMIT 8
)
SELECT w.total,w.key,w.authority,w.revision,w.state,w.phase,w.fence,
 w.attempt_count,w.task,w.contract,w.subject::jsonb,
 w.checkpoint IS NULL AS no_checkpoint,
 w.lease_until < extract(epoch FROM clock_timestamp()) AS lease_expired,
 (SELECT count(*) FROM public.ingestion_work_attempts a
   WHERE a.work_key=w.key) AS attempts,
 (SELECT count(*) FROM public.ingestion_work_attempts a
   WHERE a.work_key=w.key AND a.fence=1 AND a.phase='SOURCE_INTENT'
   AND a.finished_at IS NULL AND a.checkpoint IS NULL
   AND a.authority=w.authority) AS expected_pending_attempts,
 encode(sha256(convert_to(jsonb_build_object(
  'work',to_jsonb(w)-'total',
  'attempts',coalesce((SELECT jsonb_agg(to_jsonb(a) ORDER BY a.fence)
    FROM public.ingestion_work_attempts a WHERE a.work_key=w.key),
    '[]'::jsonb))::text,'UTF8')),'hex') AS work_attempt_sha
FROM candidates w ORDER BY w.key;

-- Q3: metadata only, no query text; absence does not prove process closure.
SELECT count(*) OVER () AS total,pid,usename,application_name,
 backend_start,xact_start,state
FROM pg_stat_activity
WHERE pid<>pg_backend_pid() AND
 (usename LIKE 'ingestion_%' OR application_name='propertyaigent_owner_pilot')
ORDER BY pid LIMIT 8;
ROLLBACK;
