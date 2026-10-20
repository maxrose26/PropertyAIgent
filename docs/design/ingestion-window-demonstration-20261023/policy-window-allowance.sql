-- POLICY V5 (generation-3 window demonstration). Derived MECHANICALLY from policy v4 (docs/design/ingestion-capture-acceptance-20261022/policy-capture-allowance.sql); tests/test_ingestion_window_demonstration_owner.py regenerates it and requires byte equality.
-- v4 admitted two named allowances in the exact generation-2 stop state; the capture they permitted stopped fail-safe (generation 3) and is consumed. v5 admits, in the exact generation-3 stop state ONLY (manual stop and last hard stop
-- both IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE, stop-state digest ff2876015380e16d3ce794b289d207e15e0e39f62fb44cf104c1608edcb39f7b) and for ONE exact scope (Bolton RECEIVED 2026-09-28 to 2026-10-04), exactly TWO MORE named allowances:
--   AUTHORISE_INGESTION_BOLTON_WINDOW_DEMONSTRATION_ONCE_20261023_CAPTURE   (the capture grant: source_calls=1, writes=0)
--   AUTHORISE_INGESTION_BOLTON_WINDOW_DEMONSTRATION_ONCE_20261023_SCREEN    (the screening grant: source_calls=0, writes=0)
-- and exempts only those two names from the cap of three exception keys, only at generation 3. The generation is never reset, no historical grant or exception is touched, the v3/v4 branches are unchanged
-- (and unreachable now), and a name that already exists can never be registered again. Preparation only; no production release.
BEGIN;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='10s';
GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE;
GRANT CREATE ON SCHEMA public TO ingestion_storage_owner;
SET LOCAL ROLE ingestion_storage_owner;
CREATE OR REPLACE FUNCTION public.ingestion_bolton_allowed(ctl jsonb, authority text, subject jsonb) RETURNS boolean
LANGUAGE sql STABLE SET search_path=pg_catalog AS $policy$
 SELECT coalesce(ctl->'global_stop'='{"reason":"CONSUMED_SALFORD_GLOBAL_STOP","run":"38884069913"}'::jsonb
 AND ((coalesce((ctl->>'hard_stop_generation')::integer,0)=coalesce((ctl->'bolton_exceptions'->authority->>'hard_stop_generation')::integer,0)
   AND (ctl->>'manual_stop' IS NULL OR ctl->>'manual_stop'='STORAGE_TEST_STOP'))
  OR (authority IN ('AUTHORISE_INGESTION_BOLTON_FORM_PROBE_ONCE_20261021_PROBE','AUTHORISE_INGESTION_BOLTON_CAPTURE_ACCEPTANCE_ONCE_20261022_CAPTURE','AUTHORISE_INGESTION_BOLTON_CAPTURE_ACCEPTANCE_ONCE_20261022_SCREEN')
   AND (ctl->>'hard_stop_generation')::integer=2 AND (ctl->'bolton_exceptions'->authority->>'hard_stop_generation')::integer=2
   AND ctl->>'manual_stop'='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE' AND ctl->>'last_hard_stop'='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE')
  OR (authority IN ('AUTHORISE_INGESTION_BOLTON_WINDOW_DEMONSTRATION_ONCE_20261023_CAPTURE','AUTHORISE_INGESTION_BOLTON_WINDOW_DEMONSTRATION_ONCE_20261023_SCREEN')
   AND (ctl->>'hard_stop_generation')::integer=3 AND (ctl->'bolton_exceptions'->authority->>'hard_stop_generation')::integer=3
   AND ctl->>'manual_stop'='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE' AND ctl->>'last_hard_stop'='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE'))
 AND subject->>'council'='bolton'
 AND ctl->'bolton_exceptions'->authority->>'transport'='REQUESTS_IDOX'
 AND (ctl->'bolton_exceptions'->authority->>'expires_at')::double precision>extract(epoch FROM statement_timestamp())
 AND ctl->'bolton_exceptions'->authority->'grant_binding'=((ctl->'grants'->authority)-ARRAY['source_calls','writes']),false)
$policy$;
CREATE OR REPLACE FUNCTION public.ingestion_register_bolton_exception(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $register$
DECLARE ctl jsonb; g jsonb; item jsonb; a text; e jsonb; t double precision; sc jsonb; root public.ingestion_work_items%ROWTYPE;
BEGIN
 IF NOT pg_has_role(session_user,'ingestion_barrier_releaser','USAGE') THEN RAISE EXCEPTION 'OWNER_DISPOSITION_REQUIRED' USING ERRCODE='42501'; END IF;
 IF p IS NULL OR octet_length(p::text)>131072 OR jsonb_typeof(p)<>'object' OR NOT (p ?& ARRAY['authority','transport','grant_binding','stop_checkpoint_sha256','revision','workflow_sha256','manifest_sha256']) THEN RAISE EXCEPTION 'EXCEPTION_BOUND'; END IF;
 SELECT outcome::jsonb INTO STRICT ctl FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE;
 a:=p->>'authority';g:=ctl->'grants'->a;t:=extract(epoch FROM clock_timestamp());
 sc:=CASE WHEN a IN ('AUTHORISE_INGESTION_BOLTON_WINDOW_DEMONSTRATION_ONCE_20261023_CAPTURE','AUTHORISE_INGESTION_BOLTON_WINDOW_DEMONSTRATION_ONCE_20261023_SCREEN') THEN '{"kind":"DISCOVERY_SCOPE","council":"bolton","start":"2026-09-28","end":"2026-10-04","semantics":"RECEIVED"}'::jsonb ELSE '{"kind":"DISCOVERY_SCOPE","council":"bolton","start":"2026-10-16","end":"2026-10-16","semantics":"RECEIVED"}'::jsonb END;      -- the exact scope this allowance may concern
 IF jsonb_typeof(p->'authority') IS DISTINCT FROM 'string' OR length(a) NOT BETWEEN 1 AND 100
 OR jsonb_typeof(g) IS DISTINCT FROM 'object' OR jsonb_typeof(g->'bindings') IS DISTINCT FROM 'object'
 OR jsonb_typeof(g->'expires_at') IS DISTINCT FROM 'number'
 OR jsonb_typeof(p->'transport') IS DISTINCT FROM 'string'
 OR jsonb_typeof(p->'stop_checkpoint_sha256') IS DISTINCT FROM 'string'
 OR jsonb_typeof(p->'revision') IS DISTINCT FROM 'string'
 OR jsonb_typeof(p->'workflow_sha256') IS DISTINCT FROM 'string'
 OR jsonb_typeof(p->'manifest_sha256') IS DISTINCT FROM 'string'
 OR jsonb_typeof(g->'keys') IS DISTINCT FROM 'array' OR jsonb_array_length(g->'keys') NOT BETWEEN 1 AND 74
 THEN RAISE EXCEPTION 'EXCEPTION_TYPES'; END IF;
 IF ctl->'global_stop' IS DISTINCT FROM '{"reason":"CONSUMED_SALFORD_GLOBAL_STOP","run":"38884069913"}'::jsonb
 OR NOT ((NOT (coalesce((ctl->>'hard_stop_generation')::integer,0)<>coalesce((p->>'hard_stop_generation')::integer,0)
 OR coalesce((p->>'hard_stop_generation')::integer,0) NOT IN (0,1)
 OR (coalesce((p->>'hard_stop_generation')::integer,0)=1 AND ctl->>'last_hard_stop' IS DISTINCT FROM 'OPERATIONAL_FIRST_CONNECTION_FAILURE_CLEANUP_20261018')
 OR (ctl->>'manual_stop' IS NOT NULL AND ctl->>'manual_stop'<>'STORAGE_TEST_STOP')
 OR p->>'stop_checkpoint_sha256'<>'a2345cf136fc92abf13bb55772f5c14a7a299b7f2b9cb0b89fe6037ccdb8a10e'))
  OR coalesce(a IN ('AUTHORISE_INGESTION_BOLTON_FORM_PROBE_ONCE_20261021_PROBE','AUTHORISE_INGESTION_BOLTON_CAPTURE_ACCEPTANCE_ONCE_20261022_CAPTURE','AUTHORISE_INGESTION_BOLTON_CAPTURE_ACCEPTANCE_ONCE_20261022_SCREEN') AND (ctl->>'hard_stop_generation')::integer=2 AND (p->>'hard_stop_generation')::integer=2
   AND ctl->>'manual_stop'='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE' AND ctl->>'last_hard_stop'='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE'
   AND p->>'stop_checkpoint_sha256'='675b69adfe844e2e443bcdaaf26b5d745f03b01a6651b025ad2a002445f06b21',false)
  OR coalesce(a IN ('AUTHORISE_INGESTION_BOLTON_WINDOW_DEMONSTRATION_ONCE_20261023_CAPTURE','AUTHORISE_INGESTION_BOLTON_WINDOW_DEMONSTRATION_ONCE_20261023_SCREEN') AND (ctl->>'hard_stop_generation')::integer=3 AND (p->>'hard_stop_generation')::integer=3
   AND ctl->>'manual_stop'='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE' AND ctl->>'last_hard_stop'='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE'
   AND p->>'stop_checkpoint_sha256'='ff2876015380e16d3ce794b289d207e15e0e39f62fb44cf104c1608edcb39f7b',false))      -- NULL (an absent stop field) is FALSE here, never a widening
 OR p->>'transport'<>'REQUESTS_IDOX' OR g IS NULL OR p->'grant_binding' IS DISTINCT FROM g-ARRAY['source_calls','writes']
 OR (g->>'expires_at')::double precision<=t OR (g->>'expires_at')::double precision>t+86400
 OR ctl->'bolton_exceptions' ? a OR ((SELECT count(*) FROM jsonb_object_keys(coalesce(ctl->'bolton_exceptions','{}'::jsonb)))>=3 AND NOT coalesce((a IN ('AUTHORISE_INGESTION_BOLTON_CAPTURE_ACCEPTANCE_ONCE_20261022_CAPTURE','AUTHORISE_INGESTION_BOLTON_CAPTURE_ACCEPTANCE_ONCE_20261022_SCREEN') AND (ctl->>'hard_stop_generation')::integer=2) OR (a IN ('AUTHORISE_INGESTION_BOLTON_WINDOW_DEMONSTRATION_ONCE_20261023_CAPTURE','AUTHORISE_INGESTION_BOLTON_WINDOW_DEMONSTRATION_ONCE_20261023_SCREEN') AND (ctl->>'hard_stop_generation')::integer=3),false))
 OR p->>'revision' !~ '^[a-f0-9]{40}$' OR p->>'workflow_sha256' !~ '^[a-f0-9]{64}$' OR p->>'manifest_sha256' !~ '^[a-f0-9]{64}$'
 THEN RAISE EXCEPTION 'EXACT_SCOPED_DISPOSITION'; END IF;
 SELECT * INTO STRICT root FROM public.ingestion_work_items WHERE key=g->>'capture_key';
 IF root.task<>'DISCOVERY' OR root.subject::jsonb IS DISTINCT FROM sc
 OR g->'execution_binding' IS DISTINCT FROM jsonb_build_object('revision',p->>'revision','workflow_sha256',p->>'workflow_sha256','manifest_sha256',p->>'manifest_sha256') THEN RAISE EXCEPTION 'EXECUTION_AND_CAPTURE_BINDING'; END IF;
 FOR item IN SELECT value FROM jsonb_each(g->'bindings') LOOP
  IF item->'subject'->>'council' IS DISTINCT FROM 'bolton' OR (item->>'task' IN ('DISCOVERY','LISTING_METADATA','SCREENING','FACTUAL_REFRESH')) IS DISTINCT FROM true THEN RAISE EXCEPTION 'BOLTON_ONLY'; END IF;
  IF item->'subject'->>'kind'='DISCOVERY_SCOPE' AND item->'subject' IS DISTINCT FROM sc THEN RAISE EXCEPTION 'EXACT_BOLTON_DAY'; END IF;
 END LOOP;
 e:=p||jsonb_build_object('expires_at',g->'expires_at');
 ctl:=jsonb_set(ctl,'{bolton_exceptions}',coalesce(ctl->'bolton_exceptions','{}'::jsonb)||jsonb_build_object(a,e));
 UPDATE public.ingestion_work_items SET outcome=ctl::json WHERE key=repeat('0',64);
 RETURN e;
END $register$;
RESET ROLE;
REVOKE CREATE ON SCHEMA public FROM ingestion_storage_owner;
REVOKE ingestion_storage_owner FROM CURRENT_USER GRANTED BY CURRENT_USER;
COMMIT;
