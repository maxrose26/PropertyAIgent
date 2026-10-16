-- OFFLINE/DISPOSABLE REVIEW CANDIDATE. No production installation authority.
-- Apply after accepted base migration. Installer needs temporary owner SET/CREATE,
-- using the reviewed explicit self-grant/revoke sequence, never runtime membership.
BEGIN;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='10s';
GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE;
GRANT CREATE ON SCHEMA public TO ingestion_storage_owner;
CREATE ROLE ingestion_effect_broker NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE ROLE ingestion_recovery_operator NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE FUNCTION public.ingestion_worker_step(p_op text,p_key text,p_fence integer,p_owner text,p_authority text,p_binding jsonb,p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $fn$
DECLARE w public.ingestion_work_items%ROWTYPE; ctl jsonb; g jsonb; t double precision; dep text; answer jsonb; n bigint; child jsonb; rec jsonb; old_child jsonb;
BEGIN
 IF p_op IN ('fence_effect','resolve_effect','enqueue_child') THEN
  IF NOT pg_has_role(session_user,'ingestion_effect_broker','USAGE') THEN RAISE EXCEPTION 'BROKER_REQUIRED' USING ERRCODE='42501'; END IF;
 ELSE
  IF session_user<>'ingestion_worker_login' OR NOT pg_has_role(session_user,'ingestion_worker','USAGE') THEN RAISE EXCEPTION 'WORKER_LOGIN_REQUIRED' USING ERRCODE='42501'; END IF;
 END IF;
 IF p_fence IS NULL OR jsonb_typeof(p_binding) IS DISTINCT FROM 'object' OR jsonb_typeof(p_payload) IS DISTINCT FROM 'object' OR p_op IS NULL OR p_op NOT IN ('claim','checkpoint','complete','begin_source','begin_write','fence_effect','resolve_effect','block','enqueue_child') OR p_key IS NULL OR p_key !~ '^[a-f0-9]{64}$' OR p_key=repeat('0',64)
 OR p_owner IS NULL OR p_owner !~ '^[A-Za-z0-9_-]{1,100}$' OR p_authority IS NULL OR length(p_authority)>100
 OR p_binding IS NULL OR p_payload IS NULL OR octet_length(p_binding::text)>8192 OR octet_length(p_payload::text)>131072
 THEN RAISE EXCEPTION 'BOUNDED_ARGUMENTS' USING ERRCODE='22023'; END IF;
 SELECT outcome::jsonb INTO STRICT ctl FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE;
 SELECT * INTO STRICT w FROM public.ingestion_work_items WHERE key=p_key FOR UPDATE;
 t:=extract(epoch FROM clock_timestamp());
 IF ctl->'global_stop' IS DISTINCT FROM 'null'::jsonb THEN RAISE EXCEPTION 'GLOBAL_STOP' USING ERRCODE='42501'; END IF;
 IF EXISTS(SELECT 1 FROM public.ingestion_work_items WHERE phase='WRITE_INTENT' AND (key<>p_key OR p_op NOT IN ('fence_effect','resolve_effect','enqueue_child'))) THEN RAISE EXCEPTION 'UNRESOLVED_WRITE_BARRIER' USING ERRCODE='42501'; END IF;
 IF (ctl->'council_deferred_until'->>(w.subject->>'council'))::double precision>t THEN RAISE EXCEPTION 'COUNCIL_DEFERRED' USING ERRCODE='42501'; END IF;
 g:=ctl->'grants'->p_authority;
 IF g IS NULL OR (g->'keys' ? p_key) IS DISTINCT FROM true OR (g->'contracts' ? w.contract) IS DISTINCT FROM true
 OR jsonb_typeof(g->'expires_at') IS DISTINCT FROM 'number' OR coalesce((g->>'expires_at')::double precision,0)<=t OR (g->>'expires_at')::double precision>t+86400
 OR (CASE WHEN p_op IN ('fence_effect','resolve_effect','enqueue_child') THEN g->>'effect_login' ELSE g->>'login' END) IS DISTINCT FROM session_user OR (g->'workers' ? p_owner) IS DISTINCT FROM true
 OR g->'bindings'->p_key IS DISTINCT FROM p_binding
 OR p_binding IS DISTINCT FROM jsonb_build_object('task',w.task,'contract',w.contract,'revision',w.revision,'subject',w.subject::jsonb)
 THEN RAISE EXCEPTION 'EXACT_AUTHORITY_BINDING_REQUIRED' USING ERRCODE='42501'; END IF;
 IF w.state IN ('SAFETY_BLOCKED','UNSUPPORTED_CONTRACT','PERSISTENCE_UNCERTAIN') THEN RAISE EXCEPTION 'BLOCKED_TASK' USING ERRCODE='42501'; END IF;
 IF p_op='claim' THEN
  IF p_fence<>0 OR p_payload<>jsonb_build_object('lease_seconds',(p_payload->>'lease_seconds')::integer)
  OR coalesce((p_payload->>'lease_seconds')::integer,0) NOT BETWEEN 1 AND 480
  OR w.state NOT IN ('QUEUED','DEFERRED') OR w.eligible_at>t OR w.attempt_count>=w.max_attempts THEN RAISE EXCEPTION 'NOT_ELIGIBLE' USING ERRCODE='42501'; END IF;
  FOR dep IN SELECT json_array_elements_text(w.dependencies) LOOP
   IF (SELECT state FROM public.ingestion_work_items WHERE key=dep) IS DISTINCT FROM 'COMPLETE' THEN RAISE EXCEPTION 'DEPENDENCY_UNFINISHED' USING ERRCODE='42501'; END IF;
  END LOOP;
  IF (SELECT count(*) FROM public.ingestion_work_attempts)>=12288 THEN RAISE EXCEPTION 'ATTEMPT_STORAGE_BOUND'; END IF;
  UPDATE public.ingestion_work_items SET state='CLAIMED',owner=p_owner,authority=p_authority,fence=fence+1,lease_until=t+(p_payload->>'lease_seconds')::integer,attempt_count=attempt_count+1,phase='CLAIMED',reason=NULL,next_action='EXECUTE_APPROVED_STAGE' WHERE key=p_key RETURNING * INTO w;
  INSERT INTO public.ingestion_work_attempts(work_key,fence,owner,authority,started_at,phase,checkpoint) VALUES(p_key,w.fence,p_owner,p_authority,t,'CLAIMED',w.checkpoint);
 ELSE
  IF w.state<>'CLAIMED' OR w.fence IS DISTINCT FROM p_fence OR w.owner IS DISTINCT FROM p_owner OR w.authority IS DISTINCT FROM p_authority OR w.lease_until IS NULL OR w.lease_until<=t THEN RAISE EXCEPTION 'STALE_WORKER' USING ERRCODE='42501'; END IF;
  IF p_op NOT IN ('fence_effect','resolve_effect','enqueue_child') AND w.phase NOT IN ('CLAIMED','CHECKPOINTED') THEN RAISE EXCEPTION 'EFFECT_RESOLUTION_REQUIRES_TRUSTED_WRITER' USING ERRCODE='42501'; END IF;
  IF p_op='enqueue_child' THEN
   IF w.phase<>'CHECKPOINTED' OR w.checkpoint::jsonb->>'kind' IS DISTINCT FROM 'LISTING_RECEIPT_V1' THEN RAISE EXCEPTION 'QUALIFIED_LISTING_CHECKPOINT_REQUIRED'; END IF;
   child:=p_payload->'child';
   IF child->>'task' IS DISTINCT FROM 'SCREENING' OR child->>'contract' IS DISTINCT FROM 'listing-screen-v1'
   OR child->'subject'->>'kind' IS DISTINCT FROM 'APPLICATION' OR child->'subject'->>'council' IS DISTINCT FROM w.subject->>'council'
   OR child->'dependencies' IS DISTINCT FROM jsonb_build_array(p_key) OR child->>'key' !~ '^[a-f0-9]{64}$'
   OR (child->>'priority')::integer IS DISTINCT FROM w.priority OR child->'limits' IS DISTINCT FROM w.limits::jsonb
   OR (child->>'max_attempts')::integer IS DISTINCT FROM 2 THEN RAISE EXCEPTION 'CHILD_SCOPE'; END IF;
   SELECT x INTO STRICT rec FROM jsonb_array_elements(w.checkpoint::jsonb->'records') x WHERE x->>'reference'=child->'subject'->>'reference';
   IF (p_payload->>'record_json')::jsonb IS DISTINCT FROM rec
   OR encode(sha256(convert_to(p_payload->>'record_json','UTF8')),'hex') IS DISTINCT FROM child->>'revision'
   OR (p_payload->>'identity_json')::jsonb IS DISTINCT FROM jsonb_build_object('subject',child->'subject','task','SCREENING','contract','listing-screen-v1','revision',child->>'revision')
   OR encode(sha256(convert_to(p_payload->>'identity_json','UTF8')),'hex') IS DISTINCT FROM child->>'key' THEN RAISE EXCEPTION 'CHILD_HASH_BINDING'; END IF;
   SELECT to_jsonb(x) INTO old_child FROM public.ingestion_work_items x WHERE subject::jsonb=child->'subject' AND task='SCREENING' AND contract='listing-screen-v1' AND revision=child->>'revision';
   IF old_child IS NOT NULL THEN RETURN old_child; END IF;
   IF (SELECT count(*) FROM public.ingestion_work_items)>=4096 THEN RAISE EXCEPTION 'ITEM_BOUND'; END IF;
   INSERT INTO public.ingestion_work_items(key,subject,task,contract,revision,dependencies,priority,eligible_at,state,reason,next_action,limits,authority,attempt_count,max_attempts,fence,owner,lease_until,phase,checkpoint,outcome)
   VALUES(child->>'key',(child->'subject')::json,'SCREENING','listing-screen-v1',child->>'revision',json_build_array(p_key),w.priority,0,'QUEUED',NULL,'CLAIM_WHEN_AUTHORISED',w.limits,NULL,0,2,0,NULL,NULL,'IDLE',NULL,NULL) RETURNING * INTO w;
  ELSIF p_op IN ('begin_source','begin_write') THEN
   IF nullif(w.checkpoint::jsonb,'null'::jsonb) IS NOT NULL THEN RAISE EXCEPTION 'CHECKPOINT_RESUME_NO_EFFECT_REPLAY'; END IF;
   IF p_payload<>jsonb_build_object('cost',(p_payload->>'cost')::integer) OR coalesce((p_payload->>'cost')::integer,0) NOT BETWEEN 1 AND 2 OR (p_op='begin_source' AND ((p_payload->>'cost')::integer<>1 OR w.task NOT IN ('DISCOVERY','LISTING_METADATA') OR w.subject->>'kind'<>'DISCOVERY_SCOPE')) OR (p_op='begin_write' AND w.task<>'FACTUAL_REFRESH') THEN RAISE EXCEPTION 'TASK_EFFECT'; END IF;
   dep:=CASE WHEN p_op='begin_source' THEN 'source_calls' ELSE 'writes' END;
   IF coalesce((g->>dep)::integer,0)<(p_payload->>'cost')::integer THEN RAISE EXCEPTION 'EFFECT_ALLOWANCE_EXHAUSTED' USING ERRCODE='42501'; END IF;
   g:=jsonb_set(g,ARRAY[dep],to_jsonb((g->>dep)::integer-(p_payload->>'cost')::integer));
   ctl:=jsonb_set(ctl,ARRAY['grants',p_authority],g);
   UPDATE public.ingestion_work_items SET outcome=ctl::json WHERE key=repeat('0',64);
   UPDATE public.ingestion_work_items SET phase=CASE WHEN p_op='begin_source' THEN 'SOURCE_INTENT' ELSE 'WRITE_INTENT' END WHERE key=p_key RETURNING * INTO w;
   UPDATE public.ingestion_work_attempts SET phase=w.phase WHERE work_key=p_key AND fence=p_fence;
  ELSIF p_op IN ('fence_effect','resolve_effect','enqueue_child') THEN
   IF w.phase NOT IN ('SOURCE_INTENT','WRITE_INTENT') THEN RAISE EXCEPTION 'DURABLE_INTENT_REQUIRED'; END IF;
   -- fence_effect is held open by the trusted broker transaction across the
   -- existing shared writer; workers cannot resolve an intent or clear a stop.
   IF p_op='resolve_effect' THEN
    IF jsonb_typeof(p_payload)<>'object' OR p_payload->>'cleanup' IS DISTINCT FROM 'CLOSED'
    OR p_payload->'accounting_complete' IS DISTINCT FROM 'true'::jsonb THEN RAISE EXCEPTION 'EFFECT_CLOSURE_REQUIRED'; END IF;
    UPDATE public.ingestion_work_items SET checkpoint=p_payload::json,phase='CHECKPOINTED' WHERE key=p_key RETURNING * INTO w;
    UPDATE public.ingestion_work_attempts SET checkpoint=p_payload::json,phase='CHECKPOINTED' WHERE work_key=p_key AND fence=p_fence;
   ELSIF p_payload<>'{}'::jsonb THEN RAISE EXCEPTION 'FENCE_PAYLOAD'; END IF;
  ELSIF p_op='block' THEN
   IF p_payload->>'state' NOT IN ('UNSUPPORTED_CONTRACT','SAFETY_BLOCKED') OR coalesce(length(p_payload->>'reason'),0) NOT BETWEEN 1 AND 200 THEN RAISE EXCEPTION 'BLOCK_STATE'; END IF;
   UPDATE public.ingestion_work_items SET state=p_payload->>'state',reason=p_payload->>'reason',outcome=(p_payload->'outcome')::json,owner=NULL,lease_until=NULL,phase='FINISHED',next_action='REVIEW' WHERE key=p_key RETURNING * INTO w;
   UPDATE public.ingestion_work_attempts SET finished_at=t,phase='FINISHED',outcome=w.outcome WHERE work_key=p_key AND fence=p_fence;
  ELSIF p_op='checkpoint' THEN
   IF w.checkpoint::jsonb->>'outcome' IN ('SUPPORTED_FACTS_VERIFIED','INITIAL_FACTS_VERIFIED') OR p_payload->>'outcome' IN ('SUPPORTED_FACTS_VERIFIED','INITIAL_FACTS_VERIFIED') THEN RAISE EXCEPTION 'BROKER_FACT_RECEIPT_REQUIRED' USING ERRCODE='42501'; END IF;
   IF octet_length(p_payload::text)>least(131072,(w.limits->>'audit_bytes')::integer) OR jsonb_typeof(p_payload)<>'object' THEN RAISE EXCEPTION 'CHECKPOINT_BOUND'; END IF;
   -- SQL records a worker receipt, never promotes its contents to factual truth.
   UPDATE public.ingestion_work_items SET checkpoint=p_payload::json,phase='CHECKPOINTED' WHERE key=p_key RETURNING * INTO w;
   UPDATE public.ingestion_work_attempts SET checkpoint=p_payload::json,phase='CHECKPOINTED' WHERE work_key=p_key AND fence=p_fence;
  ELSE
   IF w.phase<>'CHECKPOINTED' OR nullif(w.checkpoint::jsonb,'null'::jsonb) IS NULL OR jsonb_typeof(p_payload)<>'object'
   OR (g->'completion_outcomes'->w.task ? (p_payload->>'outcome')) IS DISTINCT FROM true
   OR (p_payload->>'outcome' IN ('SUPPORTED_FACTS_VERIFIED','INITIAL_FACTS_VERIFIED') AND w.checkpoint::jsonb->>'outcome' IS DISTINCT FROM p_payload->>'outcome')
   OR p_payload ?| ARRAY['global_stop','grants','authority','verified_facts'] THEN RAISE EXCEPTION 'TASK_COMPLETION_CONTRACT' USING ERRCODE='42501'; END IF;
   -- Worker task completion is not coverage advancement or factual acceptance.
   UPDATE public.ingestion_work_items SET state='COMPLETE',outcome=p_payload::json,owner=NULL,lease_until=NULL,phase='FINISHED',next_action='NONE' WHERE key=p_key RETURNING * INTO w;
   UPDATE public.ingestion_work_attempts SET outcome=p_payload::json,phase='FINISHED',finished_at=t WHERE work_key=p_key AND fence=p_fence;
  END IF;
 END IF;
 SELECT coalesce(sum(octet_length(to_jsonb(x)::text)),0) INTO n FROM public.ingestion_work_items x;
 SELECT n+coalesce(sum(octet_length(to_jsonb(x)::text)),0) INTO n FROM public.ingestion_work_attempts x;
 IF n>33554432 THEN RAISE EXCEPTION 'LEDGER_STORAGE_BOUND'; END IF;
 answer:=to_jsonb(w);RETURN answer;
END $fn$;
ALTER FUNCTION public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb) OWNER TO ingestion_storage_owner;
REVOKE ALL ON FUNCTION public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb) FROM PUBLIC;
DO $acl$ DECLARE r record; BEGIN
 FOR r IN SELECT DISTINCT p.rolname FROM pg_proc f CROSS JOIN LATERAL aclexplode(f.proacl) a JOIN pg_roles p ON p.oid=a.grantee WHERE f.oid='public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)'::regprocedure AND p.rolname<>'ingestion_storage_owner' LOOP
 EXECUTE format('REVOKE ALL ON FUNCTION public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb) FROM %I',r.rolname); END LOOP;END $acl$;
GRANT EXECUTE ON FUNCTION public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb) TO ingestion_worker,ingestion_effect_broker;
CREATE FUNCTION public.ingestion_recover_abandoned(p_key text,p_fence integer,p_closed boolean) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $recover$
DECLARE w public.ingestion_work_items%ROWTYPE; ctl jsonb; t double precision; uncertain boolean;
BEGIN
 IF NOT pg_has_role(session_user,'ingestion_recovery_operator','USAGE') THEN RAISE EXCEPTION 'RECOVERY_OPERATOR_REQUIRED' USING ERRCODE='42501'; END IF;
 SELECT outcome::jsonb INTO STRICT ctl FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE;
 SELECT * INTO STRICT w FROM public.ingestion_work_items WHERE key=p_key FOR UPDATE;
 t:=extract(epoch FROM clock_timestamp());
 IF p_key=repeat('0',64) OR w.state<>'CLAIMED' OR w.fence IS DISTINCT FROM p_fence OR w.lease_until IS NULL OR w.lease_until>t THEN RAISE EXCEPTION 'RECOVERY_BOUNDARY'; END IF;
 uncertain:=w.phase='WRITE_INTENT';
 IF uncertain OR w.phase='SOURCE_INTENT' OR p_closed IS DISTINCT FROM true THEN
  IF ctl->'global_stop'='null'::jsonb THEN ctl:=jsonb_set(ctl,'{global_stop}',jsonb_build_object('reason','ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP','work_key',p_key)); END IF;
  UPDATE public.ingestion_work_items SET outcome=ctl::json WHERE key=repeat('0',64);
 END IF;
 UPDATE public.ingestion_work_items SET state=CASE WHEN uncertain THEN 'PERSISTENCE_UNCERTAIN' WHEN w.phase='SOURCE_INTENT' OR p_closed IS DISTINCT FROM true THEN 'SAFETY_BLOCKED' ELSE 'DEFERRED' END,
 reason='ABANDONED_'||w.phase,outcome=jsonb_build_object('outcome','ABANDONED_'||w.phase,'source_or_write_replay_authorised',false)::json,
 owner=NULL,lease_until=NULL,fence=fence+1,phase='RECOVERED',next_action=CASE WHEN uncertain OR w.phase='SOURCE_INTENT' OR p_closed IS DISTINCT FROM true THEN 'RECONCILE' ELSE 'CLAIM_OFFLINE_CHECKPOINT_ONLY' END
 WHERE key=p_key RETURNING * INTO w;
 UPDATE public.ingestion_work_attempts SET finished_at=t,phase='RECOVERED',outcome=w.outcome WHERE work_key=p_key AND fence=p_fence;
 RETURN to_jsonb(w);
END $recover$;
ALTER FUNCTION public.ingestion_recover_abandoned(text,integer,boolean) OWNER TO ingestion_storage_owner;
REVOKE ALL ON FUNCTION public.ingestion_recover_abandoned(text,integer,boolean) FROM PUBLIC;
DO $acl$ DECLARE r record; BEGIN
 FOR r IN SELECT DISTINCT p.rolname FROM pg_proc f CROSS JOIN LATERAL aclexplode(f.proacl) a JOIN pg_roles p ON p.oid=a.grantee WHERE f.oid='public.ingestion_recover_abandoned(text,integer,boolean)'::regprocedure AND p.rolname<>'ingestion_storage_owner' LOOP
 EXECUTE format('REVOKE ALL ON FUNCTION public.ingestion_recover_abandoned(text,integer,boolean) FROM %I',r.rolname); END LOOP;END $acl$;
GRANT EXECUTE ON FUNCTION public.ingestion_recover_abandoned(text,integer,boolean) TO ingestion_recovery_operator;
REVOKE CREATE ON SCHEMA public FROM ingestion_storage_owner;
REVOKE ingestion_storage_owner FROM CURRENT_USER GRANTED BY CURRENT_USER;
DO $check$ BEGIN
 IF pg_has_role(current_user,'ingestion_storage_owner','USAGE') OR pg_has_role(current_user,'ingestion_storage_owner','SET') OR has_schema_privilege('ingestion_storage_owner','public','CREATE') THEN RAISE EXCEPTION 'TEMPORARY_OWNER_CAPABILITY_REMAINS'; END IF;
END $check$;
COMMIT;
