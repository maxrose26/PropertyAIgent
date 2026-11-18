-- PA-D002: synthetic PostgreSQL 17 fixture; DO NOT APPLY TO PRODUCTION.
-- Existing installed function bodies independently inspected SELECT-only 2026-11-09.
-- read SHA256(prosrc) 8552e361065807eb428c15d95cbb7a5a81011f6c0ee08d8db5bd8cb572f94a8a
-- installed baseline write SHA256(prosrc) 8ffd8fdda0692a49a776137ea6342c1378d1f513cd418b8f983a92f0fe910290
-- OFFLINE STOP-CAS candidate write SHA256(prosrc) 4ce46b98cbf986596f907b7236509b87ade6788bce7e4c9f40ebbd8167381f77
-- These operations execute ONLY in disposable_world() with fixed loopback host/DB.
CREATE TABLE public.ingestion_run_evidence (
 period text NOT NULL, run_id text NOT NULL, name text NOT NULL,
 body bytea NOT NULL, sha256 text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY (period,run_id,name)
);
ALTER TABLE public.ingestion_run_evidence OWNER TO ingestion_storage_owner;
REVOKE ALL ON public.ingestion_run_evidence FROM PUBLIC;
CREATE OR REPLACE FUNCTION public.ingestion_intake_evidence_read(p_period text, p_run text, p_name text)
 RETURNS bytea
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog'
AS $function$
DECLARE result public.ingestion_run_evidence%ROWTYPE;ctl jsonb;
BEGIN
 IF NOT (session_user='postgres' OR session_user='ingestion_worker_login' AND pg_has_role(session_user,'ingestion_worker','USAGE')) THEN RAISE EXCEPTION 'EVIDENCE_READER_ONLY' USING ERRCODE='42501'; END IF;
 IF p_period IS NULL OR p_period !~ '^[A-Za-z0-9_-]{1,60}$' OR p_run IS NULL OR p_run !~ '^[a-f0-9]{32}$'
 OR p_name IS NULL OR p_name NOT IN ('capture-1/source.json','capture-2/source.json','final/result-before-publication.json','final/events-before-publication.json') THEN RAISE EXCEPTION 'EVIDENCE_READ_BOUND'; END IF;
 IF session_user='ingestion_worker_login' THEN
  SELECT outcome::jsonb INTO STRICT ctl FROM public.ingestion_work_items WHERE key=repeat('0',64);
  IF ctl->'intake_run'->>'id' IS DISTINCT FROM p_run OR ctl->'intake_run'->>'period' IS DISTINCT FROM p_period OR ctl->'intake_periods'->p_period->>'evidence_backend' IS DISTINCT FROM 'POSTGRES_PILOT_V1' THEN RAISE EXCEPTION 'EVIDENCE_READ_RUN_BINDING'; END IF;
 END IF;
 SELECT * INTO STRICT result FROM public.ingestion_run_evidence WHERE period=p_period AND run_id=p_run AND name=p_name;
 IF encode(sha256(result.body),'hex') IS DISTINCT FROM result.sha256 OR octet_length(result.body)>2097152 THEN RAISE EXCEPTION 'EVIDENCE_STORED_HASH'; END IF;
 RETURN result.body;
END $function$;
CREATE OR REPLACE FUNCTION public.ingestion_intake_evidence_write(p_period text, p_run text, p_name text, p_body bytea)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog'
AS $function$
DECLARE ctl jsonb; policy jsonb; run jsonb; prior public.ingestion_run_evidence%ROWTYPE; n bigint; h text; t double precision;
BEGIN
 IF session_user<>'ingestion_worker_login' OR NOT pg_has_role(session_user,'ingestion_worker','USAGE') THEN RAISE EXCEPTION 'EVIDENCE_WORKER_ONLY' USING ERRCODE='42501'; END IF;
 IF p_period IS NULL OR p_period !~ '^[A-Za-z0-9_-]{1,60}$' OR p_run IS NULL OR p_run !~ '^[a-f0-9]{32}$'
 OR p_name IS NULL OR p_name NOT IN ('capture-1/source.json','capture-2/source.json','final/result-before-publication.json','final/events-before-publication.json')
 OR p_body IS NULL OR octet_length(p_body) NOT BETWEEN 1 AND 2097152 OR (p_name LIKE 'capture-%' AND octet_length(p_body)>524288) THEN RAISE EXCEPTION 'EVIDENCE_ARGUMENT_BOUND'; END IF;
 -- Same existing controller lock serialises writes and aggregate quota checks.
 SELECT outcome::jsonb INTO STRICT ctl FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE;
 policy:=ctl->'intake_periods'->p_period;run:=ctl->'intake_run';t:=extract(epoch FROM clock_timestamp());
 IF policy->>'evidence_backend' IS DISTINCT FROM 'POSTGRES_PILOT_V1' OR policy->'max_runs' IS DISTINCT FROM '1'::jsonb
 OR run->>'period' IS DISTINCT FROM p_period OR run->>'id' IS DISTINCT FROM p_run OR run->>'state' NOT IN ('OPEN','VERIFIED') THEN RAISE EXCEPTION 'EVIDENCE_RUN_BINDING'; END IF;
 -- PA-D002 OFFLINE candidate: controller row FOR UPDATE serialises an
 -- owner stop and a SOURCE write. A separate policy_read is not atomic.
 -- Final diagnostics after source close remain intentionally permitted.
 IF p_name LIKE 'capture-%' AND (
  ctl->'global_stop' IS DISTINCT FROM 'null'::jsonb
  OR ctl->'manual_stop' IS DISTINCT FROM 'null'::jsonb
  OR policy->'expected_stop' IS DISTINCT FROM jsonb_build_object(
   'global_stop',ctl->'global_stop','manual_stop',ctl->'manual_stop',
   'last_hard_stop',ctl->'last_hard_stop',
   'hard_stop_generation',coalesce(ctl->'hard_stop_generation','0'::jsonb))
 ) THEN RAISE EXCEPTION 'EVIDENCE_STOP_CHANGED'; END IF;
 -- Validate live SOURCE_INTENT authority even for byte-identical stored evidence.
 -- After grant/period closure, recover only by the separately bounded SQL reader.
 IF p_name LIKE 'capture-%' AND (run->>'state' IS DISTINCT FROM 'OPEN' OR t>(policy->>'expires_at')::double precision OR NOT EXISTS (
 SELECT 1 FROM jsonb_each(ctl->'grants') g JOIN public.ingestion_work_items w ON w.key=g.value->>'capture_key'
 WHERE g.value->>'intake_period'=p_period AND g.value->>'intake_run'=p_run AND w.phase='SOURCE_INTENT'
 AND g.value->'execution_binding'=policy->'execution_binding' AND (g.value->>'expires_at')::double precision>t
 AND (convert_from(p_body,'UTF8')::jsonb)->'requested_interval'=jsonb_build_array(w.subject::jsonb->>'start',w.subject::jsonb->>'end')
 AND ((w.subject::jsonb->>'council'='tameside' AND w.subject::jsonb->>'semantics'='RECEIVED' AND (convert_from(p_body,'UTF8')::jsonb)->>'council'='tameside' AND (convert_from(p_body,'UTF8')::jsonb)->>'date_semantics'='RECEIVED')
 OR (p_period='b-bolton-20261103-1105-01' AND policy->'fixed_window'='{"end": "2026-11-05", "start": "2026-11-03"}'::jsonb AND w.subject::jsonb->>'council'='bolton' AND w.subject::jsonb->>'semantics'='RECEIVED' AND (convert_from(p_body,'UTF8')::jsonb)->>'council'='bolton' AND (convert_from(p_body,'UTF8')::jsonb)->>'date_semantics'='RECEIVED')
 OR (w.subject::jsonb->>'council'='manchester' AND w.subject::jsonb->>'semantics'='VALIDATED' AND (convert_from(p_body,'UTF8')::jsonb)->>'case'='discovery_manchester_ui_window'))
 )) THEN RAISE EXCEPTION 'EVIDENCE_SOURCE_AUTHORITY'; END IF;
 SELECT * INTO prior FROM public.ingestion_run_evidence WHERE period=p_period AND run_id=p_run AND name=p_name;
 IF FOUND THEN
  IF prior.body IS DISTINCT FROM p_body THEN RAISE EXCEPTION 'EVIDENCE_CONFLICT_NO_OVERWRITE'; END IF;
  RETURN jsonb_build_object('backend','POSTGRES_PILOT_V1','period',p_period,'run_id',p_run,'name',p_name,
   'path','docs/design/ingestion-operational-execution-daily-intake/'||p_period||'/'||p_run||'/'||p_name,
   'sha256',prior.sha256,'bytes',octet_length(prior.body),'readback_verified',false);
 END IF;
 IF run->>'state'<>'OPEN' OR t>(policy->>'expires_at')::double precision+185 THEN RAISE EXCEPTION 'EVIDENCE_RUN_CLOSED'; END IF;
 IF p_name LIKE 'final/%' AND EXISTS(SELECT 1 FROM jsonb_each(ctl->'grants') g WHERE g.value->>'intake_run'=p_run AND g.value->'expires_at' IS DISTINCT FROM '0'::jsonb) THEN RAISE EXCEPTION 'EVIDENCE_FINITE_AUTHORITIES_NOT_CLOSED'; END IF;
 -- Reject malformed/non-object exports without converting an arbitrary exception to success.
 IF jsonb_typeof(convert_from(p_body,'UTF8')::jsonb) IS DISTINCT FROM (CASE WHEN p_name='final/events-before-publication.json' THEN 'array' ELSE 'object' END) THEN RAISE EXCEPTION 'EVIDENCE_EXPORT_OBJECT'; END IF;
 h:=encode(sha256(p_body),'hex');
 SELECT * INTO prior FROM public.ingestion_run_evidence WHERE period=p_period AND run_id=p_run AND name=p_name;
 IF FOUND THEN
  IF prior.body IS DISTINCT FROM p_body OR prior.sha256 IS DISTINCT FROM h THEN RAISE EXCEPTION 'EVIDENCE_CONFLICT_NO_OVERWRITE'; END IF;
 ELSE
  SELECT coalesce(sum(octet_length(body)),0) INTO n FROM public.ingestion_run_evidence WHERE period=p_period AND run_id=p_run;
  IF n+octet_length(p_body)>2097152 THEN RAISE EXCEPTION 'EVIDENCE_RUN_EXPORT_BOUND'; END IF;
  INSERT INTO public.ingestion_run_evidence(period,run_id,name,body,sha256) VALUES(p_period,p_run,p_name,p_body,h);
 END IF;
 RETURN jsonb_build_object('backend','POSTGRES_PILOT_V1','period',p_period,'run_id',p_run,'name',p_name,
  'path','docs/design/ingestion-operational-execution-daily-intake/'||p_period||'/'||p_run||'/'||p_name,
  'sha256',h,'bytes',octet_length(p_body),'readback_verified',false);
END $function$;
ALTER FUNCTION public.ingestion_intake_evidence_read(text,text,text) OWNER TO ingestion_storage_owner;
ALTER FUNCTION public.ingestion_intake_evidence_write(text,text,text,bytea) OWNER TO ingestion_storage_owner;
REVOKE ALL ON FUNCTION public.ingestion_intake_evidence_read(text,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.ingestion_intake_evidence_write(text,text,text,bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.ingestion_intake_evidence_read(text,text,text) TO ingestion_worker;
GRANT EXECUTE ON FUNCTION public.ingestion_intake_evidence_write(text,text,text,bytea) TO ingestion_worker;
