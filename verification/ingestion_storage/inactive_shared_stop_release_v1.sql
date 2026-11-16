-- S4-04/S4-05 INACTIVE, review-bound ONE-SHOT OWNER TRANSACTION.
-- Not in installation_script(), not a SQL function, not approved for use.
-- Mandatory manifest is deliberately WITHHELD. A future independent review
-- and explicit owner operational decision must pin a NEW exact artifact.
-- Never substitute the disposable release function or test-labelled approvals.
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '10s';
LOCK TABLE public.ingestion_work_items IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.ingestion_work_attempts IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.ingestion_run_evidence IN SHARE MODE;
DO $owner_release$
DECLARE
  ctl jsonb; oldstop jsonb; receipt jsonb; w public.ingestion_work_items%ROWTYPE;
  audit public.ingestion_work_items%ROWTYPE; wr pg_catalog.pg_proc%ROWTYPE;
  rd pg_catalog.pg_proc%ROWTYPE; rel pg_catalog.pg_class%ROWTYPE;
  -- THIS EXACT SOURCE IS INERT. Do not install or execute against production.
  review_manifest jsonb := '{"release_status":"WITHHELD","review_sha256":null,"effects":[]}'::jsonb;
  expected_prior jsonb := '{
    "d9d8d667eef5fb012c74cdd28f5c55c6b577f749e7dc69d9179a6c032853d252":"37307a3af9253d7b1e44501c0cbd3b3ff75b3a9aed4345bae76606bb3eb4b442",
    "3f0dba235de9b9efcd52ef3b281ba8c967491f57824404c695ed2b32fae4c045":"117eda0e1a2185f0d158c9c27e677d265c308714cf5967a2286a5aca3e35ae1e",
    "e92a8e220bbbbcefb2425d6f97a60920bc447bc1fe097d600ea28e3e9d87588e":"aa36a1c191073dd87d3ab1eaad326b150189fe451d0334744f886032399171eb",
    "a22bac9985d0141d82a4adceaba2354eb3808280413bf7c3aad44d34de8515ad":"6d30c20b8e7fa0e3ea20f60af9115922ae78299208d16055b74e0b9fe2f10c76",
    "ef5afe887f3e5162212fc33f2cf4429d5cbb19cf11bede34e2d1156b09741bc5":"0863af12b15f9272a5450fff1309b4ff4bc6479ac8060f88541ae412c72e26f8",
    "21330c060171f6f95286a8f31131bda00fa3c081a21ebfc0f418b10706e510e4":"a39ce8681bb35059de626ef0bf9a8196af4e8bfded50d5af6d0b67c826c81fd7",
    "dc8ae276a9c3f697b9905adf0ec8835398009769b69e788e4fd70e13216ee6fc":"dff707aa0a40de896369aafa23ef2f243c84b0ebf249544109d7aecc91f67a09"
  }'::jsonb;
  e jsonb; k text; ah text; wh text; n integer := 0; t double precision;
BEGIN
  IF current_database() IS DISTINCT FROM 'postgres'
     OR session_user IS DISTINCT FROM 'postgres'
     OR current_user IS DISTINCT FROM 'postgres'
  THEN RAISE EXCEPTION 'OWNER_RELEASE_EXECUTION_IDENTITY' USING ERRCODE='42501'; END IF;
  -- A GitHub comment or preservation ACCEPT is not executable approval.
  -- Source remains WITHHELD until a separately reviewed, pinned new artifact.
  IF review_manifest->>'release_status' IS DISTINCT FROM 'ACCEPTED_FOR_OPERATIONAL_RELEASE'
     OR coalesce(review_manifest->>'review_sha256','') !~ '^[a-f0-9]{64}$'
     OR jsonb_typeof(review_manifest->'effects') IS DISTINCT FROM 'array'
     OR jsonb_array_length(review_manifest->'effects') <> 7
     OR coalesce(review_manifest->>'expected_controller_sha256','') !~ '^[a-f0-9]{64}$'
     OR review_manifest ? 'test_only'
  THEN RAISE EXCEPTION 'OWNER_RELEASE_REVIEW_WITHHELD' USING ERRCODE='42501'; END IF;

  SELECT outcome::jsonb INTO STRICT ctl FROM public.ingestion_work_items
    WHERE key=repeat('0',64) FOR UPDATE;
  oldstop:=jsonb_build_object('global_stop',ctl->'global_stop',
    'manual_stop',ctl->'manual_stop','last_hard_stop',ctl->'last_hard_stop',
    'hard_stop_generation',coalesce(ctl->'hard_stop_generation','0'::jsonb));
  IF ctl->'global_stop' IS DISTINCT FROM '{"reason":"DAILY_INTAKE_SHARED_FAILURE"}'::jsonb
     OR ctl->>'manual_stop' IS DISTINCT FROM 'ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP'
     OR ctl->>'last_hard_stop' IS DISTINCT FROM 'ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP'
     OR ctl->'hard_stop_generation' IS DISTINCT FROM '15'::jsonb
     OR ctl ? 'intake_run' OR ctl ? 'owner_shared_stop_release'
  THEN RAISE EXCEPTION 'OWNER_RELEASE_STOP_CAS'; END IF;
  receipt:=ctl->'intake_periods'->'b-bolton-20261103-1105-01'
             ->'failed_runs'->'ee7cf0d9bc714f56951527b940937054';
  IF receipt->>'version' IS DISTINCT FROM 'BOLTON01_FAILED_RECOVERY_V1'
     OR receipt->>'status' IS DISTINCT FROM 'FAILED_RECONCILED'
     OR receipt->>'coverage' IS DISTINCT FROM 'UNKNOWN'
     OR receipt->>'recovered_key' IS DISTINCT FROM
         'd9d8d667eef5fb012c74cdd28f5c55c6b577f749e7dc69d9179a6c032853d252'
     OR receipt->'recovered_fence' IS DISTINCT FROM '2'::jsonb
     OR receipt->'source_or_write_replay_authorised' IS DISTINCT FROM 'false'::jsonb
     OR receipt->'stop_after' IS DISTINCT FROM oldstop
     OR receipt->'original_marker'->>'state' IS DISTINCT FROM 'OPEN'
     OR receipt->'original_marker'->>'id' IS DISTINCT FROM 'ee7cf0d9bc714f56951527b940937054'
     OR receipt->'original_marker'->>'period' IS DISTINCT FROM 'b-bolton-20261103-1105-01'
  THEN RAISE EXCEPTION 'OWNER_RELEASE_BOLTON_RECEIPT'; END IF;

  SELECT * INTO STRICT audit FROM public.ingestion_work_items
    WHERE key='c1f526eed20e392382001cad4d28eb5bc16e5d1c0f92adb282fe7b1cc775f3f3';
  IF to_jsonb(audit) IS DISTINCT FROM
      '{"attempt_count":0,"authority":null,"checkpoint":{"evidence_commit":"e2db0277b99c3b8ff57b5fb808b6c83aa4643e7c","live_allowance":{"source_calls":0,"writes":0},"retained_evidence":{"checkpoint_sha256":"a2345cf136fc92abf13bb55772f5c14a7a299b7f2b9cb0b89fe6037ccdb8a10e","durable_reference":{"bytes":4298,"commit":"e2db0277b99c3b8ff57b5fb808b6c83aa4643e7c","path":"docs/design/stage4-r0-execution/metadata-rollout-result-20261016/scopes/00/artifact/checkpoints/000.json","sha256":"a2345cf136fc92abf13bb55772f5c14a7a299b7f2b9cb0b89fe6037ccdb8a10e"},"run":"38884069913"}},"contract":"storage-acceptance-blocked-v1","dependencies":[],"eligible_at":0,"fence":0,"key":"c1f526eed20e392382001cad4d28eb5bc16e5d1c0f92adb282fe7b1cc775f3f3","lease_until":null,"limits":{"aggregate_rss":1610612736,"audit_bytes":2097152,"bytes":20971520,"outer_seconds":60,"pages":6,"requests":80,"rows":60,"source_rss":1073741824,"worker_seconds":45},"max_attempts":1,"next_action":"REVIEW_ONLY","outcome":null,"owner":null,"phase":"IDLE","priority":0,"reason":"CONSUMED_SALFORD_GLOBAL_STOP","revision":"20261016","state":"SAFETY_BLOCKED","subject":{"council":"salford","end":"2026-10-14","kind":"DISCOVERY_SCOPE","semantics":"VALIDATED","start":"2026-10-08"},"task":"LISTING_METADATA"}'::jsonb
     OR EXISTS (SELECT 1 FROM public.ingestion_work_attempts a WHERE a.work_key=audit.key)
  THEN RAISE EXCEPTION 'OWNER_RELEASE_SALFORD_DRIFT'; END IF;

  SELECT * INTO STRICT wr FROM pg_catalog.pg_proc WHERE
    oid='public.ingestion_intake_evidence_write(text,text,text,bytea)'::pg_catalog.regprocedure;
  SELECT * INTO STRICT rd FROM pg_catalog.pg_proc WHERE
    oid='public.ingestion_intake_evidence_read(text,text,text)'::pg_catalog.regprocedure;
  SELECT * INTO STRICT rel FROM pg_catalog.pg_class WHERE
    oid='public.ingestion_run_evidence'::pg_catalog.regclass;
  IF encode(pg_catalog.sha256(pg_catalog.convert_to(wr.prosrc,'UTF8')),'hex')
       IS DISTINCT FROM '4ce46b98cbf986596f907b7236509b87ade6788bce7e4c9f40ebbd8167381f77'
     OR encode(pg_catalog.sha256(pg_catalog.convert_to(rd.prosrc,'UTF8')),'hex')
       IS DISTINCT FROM '8552e361065807eb428c15d95cbb7a5a81011f6c0ee08d8db5bd8cb572f94a8a'
     OR pg_catalog.pg_get_userbyid(wr.proowner) IS DISTINCT FROM 'ingestion_storage_owner'
     OR pg_catalog.pg_get_userbyid(rd.proowner) IS DISTINCT FROM 'ingestion_storage_owner'
     OR NOT wr.prosecdef OR NOT rd.prosecdef
     OR wr.proconfig::text IS DISTINCT FROM '{search_path=pg_catalog}'
     OR rd.proconfig::text IS DISTINCT FROM '{search_path=pg_catalog}'
     OR wr.proacl::text IS DISTINCT FROM '{ingestion_storage_owner=X/ingestion_storage_owner,ingestion_worker=X/ingestion_storage_owner}'
     OR rd.proacl::text IS DISTINCT FROM '{ingestion_storage_owner=X/ingestion_storage_owner,ingestion_worker=X/ingestion_storage_owner,postgres=X/ingestion_storage_owner}'
     OR rel.relacl::text IS DISTINCT FROM '{ingestion_storage_owner=arwdDxtm/ingestion_storage_owner}'
     OR NOT rel.relrowsecurity OR NOT rel.relforcerowsecurity
     OR (SELECT count(*) FROM pg_catalog.pg_policy p
         WHERE p.polrelid=rel.oid) <> 1
     OR NOT EXISTS (SELECT 1 FROM pg_catalog.pg_policy p
         WHERE p.polrelid=rel.oid
           AND p.polname='ingestion_evidence_owner'
           AND p.polpermissive AND p.polcmd='*'
           AND pg_catalog.cardinality(p.polroles)=1
           AND pg_catalog.pg_get_userbyid(p.polroles[1])='ingestion_storage_owner'
           AND pg_catalog.pg_get_expr(p.polqual,p.polrelid)='true'
           AND pg_catalog.pg_get_expr(p.polwithcheck,p.polrelid)='true')
     OR EXISTS (SELECT 1 FROM public.ingestion_run_evidence
        WHERE encode(pg_catalog.sha256(body),'hex') IS DISTINCT FROM sha256)
  THEN RAISE EXCEPTION 'OWNER_RELEASE_WRITER_OR_EVIDENCE_DRIFT'; END IF;

  FOR e IN SELECT value FROM jsonb_array_elements(review_manifest->'effects') LOOP
    k:=e->>'key';
    IF NOT (expected_prior ? k) OR e->>'prior_sha256' IS DISTINCT FROM expected_prior->>k
       OR e->>'release_containment' IS DISTINCT FROM 'ACCEPT'
       OR e->>'coverage' IS DISTINCT FROM 'UNKNOWN'
       OR e->'source_or_write_replay_authorised' IS DISTINCT FROM 'false'::jsonb
       OR coalesce(e->>'review_ref','') NOT LIKE 'https://github.com/maxrose26/PropertyAIgent/%'
       OR coalesce(e->>'work_sha256','') !~ '^[a-f0-9]{64}$'
       OR coalesce(e->>'attempts_sha256','') !~ '^[a-f0-9]{64}$'
       OR e->>'source_decision_scope' IS DISTINCT FROM 'EXPLICIT_OPERATIONAL_RELEASE_NOT_PRESERVATION_ONLY'
       OR e ? 'test_only'
       OR (k IN ('21330c060171f6f95286a8f31131bda00fa3c081a21ebfc0f418b10706e510e4',
                    'dc8ae276a9c3f697b9905adf0ec8835398009769b69e788e4fd70e13216ee6fc')
            AND (e->>'effect_state' IS DISTINCT FROM 'UNKNOWN'
                 OR e->>'risk_acceptance' IS DISTINCT FROM 'OWNER_AND_DISTINCT_REVIEW_EXPLICIT_UNKNOWN'
                 OR e->>'risk_boundary' IS DISTINCT FROM 'NO_REPLAY_ONE_GENERATION_NO_COVERAGE'
                 OR coalesce(e->>'owner_decision_ref','')
                       NOT LIKE 'https://github.com/maxrose26/PropertyAIgent/issues/214#issuecomment-%'))
    THEN RAISE EXCEPTION 'OWNER_RELEASE_EFFECT_REVIEW_MISSING'; END IF;
    SELECT * INTO STRICT w FROM public.ingestion_work_items WHERE key=k FOR UPDATE;
    SELECT encode(pg_catalog.sha256(pg_catalog.convert_to(
      coalesce(jsonb_agg(to_jsonb(a) ORDER BY a.fence)::text,'[]'),'UTF8')),'hex')
      INTO ah FROM public.ingestion_work_attempts a WHERE a.work_key=k;
    wh:=encode(pg_catalog.sha256(pg_catalog.convert_to(to_jsonb(w)::text,'UTF8')),'hex');
    IF wh IS DISTINCT FROM e->>'work_sha256'
       OR ah IS DISTINCT FROM e->>'attempts_sha256'
       OR w.owner IS NOT NULL OR w.lease_until IS NOT NULL
       OR w.outcome::jsonb->'source_or_write_replay_authorised' IS DISTINCT FROM 'false'::jsonb
       OR (w.key = 'd9d8d667eef5fb012c74cdd28f5c55c6b577f749e7dc69d9179a6c032853d252'
           AND (w.state IS DISTINCT FROM 'SAFETY_BLOCKED'
                OR w.phase IS DISTINCT FROM 'RECOVERED'
                OR w.next_action IS DISTINCT FROM 'RECONCILE'))
       OR (w.key <> 'd9d8d667eef5fb012c74cdd28f5c55c6b577f749e7dc69d9179a6c032853d252'
           AND (w.state IS DISTINCT FROM 'DEFERRED'
                OR w.phase IS DISTINCT FROM 'FINISHED'
                OR w.next_action IS DISTINCT FROM 'PRESERVE_HISTORY_NO_REPLAY'
                OR w.checkpoint::jsonb->>'review_sha256' IS DISTINCT FROM review_manifest->>'review_sha256'
                OR coalesce(w.checkpoint::jsonb->>'reviewer_evidence','') IN ('','NOT_SUPPLIED')
                OR w.checkpoint::jsonb->'test_only' IS NOT NULL
                OR w.outcome::jsonb->>'coverage' IS DISTINCT FROM 'UNKNOWN'
                OR w.outcome::jsonb->>'outcome' IS DISTINCT FROM 'REVIEW_ACCEPTED_PRESERVE_NO_REPLAY'))
    THEN RAISE EXCEPTION 'OWNER_RELEASE_EFFECT_OR_NO_REPLAY_DRIFT'; END IF;
    n:=n+1;
  END LOOP;
  IF n<>7 OR (SELECT count(DISTINCT value->>'key')
               FROM jsonb_array_elements(review_manifest->'effects'))<>7
  THEN RAISE EXCEPTION 'OWNER_RELEASE_EFFECT_SET'; END IF;
  t:=extract(epoch FROM clock_timestamp());
  IF EXISTS (SELECT 1 FROM public.ingestion_work_items x WHERE
       (x.state IN ('CLAIMED','PERSISTENCE_UNCERTAIN') OR
        x.phase IN ('SOURCE_INTENT','WRITE_INTENT') OR
        x.reason='ABANDONED_SOURCE_INTENT' OR x.next_action='RECONCILE' OR
        (x.state='SAFETY_BLOCKED' AND x.key<>audit.key))
       AND x.key<>repeat('0',64)
       AND x.key<>audit.key  -- exact whole-row audit already verified above
       AND NOT (x.key='d9d8d667eef5fb012c74cdd28f5c55c6b577f749e7dc69d9179a6c032853d252'
         AND x.state='SAFETY_BLOCKED' AND x.phase='RECOVERED'
         AND x.next_action='RECONCILE'))
     OR EXISTS (SELECT 1 FROM public.ingestion_work_attempts a
         WHERE a.phase IN ('SOURCE_INTENT','WRITE_INTENT') OR a.finished_at IS NULL)
     OR EXISTS (SELECT 1 FROM jsonb_each(coalesce(ctl->'grants','{}'::jsonb)) g
         WHERE jsonb_typeof(g.value->'expires_at') IS DISTINCT FROM 'number'
           OR (g.value->>'expires_at')::double precision>t)
     OR EXISTS (SELECT 1 FROM jsonb_each(coalesce(ctl->'intake_periods','{}'::jsonb)) p
         WHERE jsonb_typeof(p.value->'expires_at') IS DISTINCT FROM 'number'
           OR (p.value->>'expires_at')::double precision>t)
     OR EXISTS (SELECT 1 FROM pg_catalog.pg_stat_activity a
         WHERE a.datname=current_database()
           AND a.usename IN ('ingestion_worker_login','ingestion_effect_login')
           AND a.pid<>pg_backend_pid())
  THEN RAISE EXCEPTION 'OWNER_RELEASE_OUTSTANDING_EFFECT_OR_AUTHORITY'; END IF;
  -- The owner's pinned manifest must bind the ENTIRE generation-15 controller
  -- read under the locks, not just the selected known STOP fields. A changed
  -- policy, budget, grant history or unrelated controller field refuses.
  IF encode(pg_catalog.sha256(pg_catalog.convert_to(ctl::text,'UTF8')),'hex')
       IS DISTINCT FROM review_manifest->>'expected_controller_sha256'
  THEN RAISE EXCEPTION 'OWNER_RELEASE_CONTROLLER_DRIFT'; END IF;

  -- Sole permitted write: clear these TWO stops, advance this exact generation
  -- once, retain last_hard_stop/failed runs/UNKNOWN evidence and no-replay keys.
  ctl:=ctl||jsonb_build_object('global_stop',null,'manual_stop',null,
      'hard_stop_generation',16,'owner_shared_stop_release',
       jsonb_build_object('version','OWNER_REVIEWED_ONE_SHOT_V1',
        'review_sha256',review_manifest->>'review_sha256',
        'source_generation',15,'no_work_issued',true));
  UPDATE public.ingestion_work_items SET outcome=ctl::json WHERE key=repeat('0',64);
END $owner_release$;
COMMIT;
-- On unknown COMMIT acknowledgement: separate read-only gen16 + receipt readback,
-- NEVER retry, never restore gen14/15. On later failure raise a NEW stop and
-- reconcile physical effects independently; do not delete preserved evidence.
-- This file does not enable LIVE_PRIVATE_EVIDENCE_RELEASE, issue a period, run
-- a council request, create roles/grants/tables/functions, or unsuspend cron.
