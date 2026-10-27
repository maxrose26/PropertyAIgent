BEGIN;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='10s';
GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE;
GRANT CREATE ON SCHEMA public TO ingestion_storage_owner;
SET LOCAL ROLE ingestion_storage_owner;

CREATE FUNCTION public.ingestion_oldham_allowed(ctl jsonb, authority text, work_key text, subject jsonb) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $oldham$
 SELECT coalesce(
 ctl->'global_stop'='{"reason":"CONSUMED_SALFORD_GLOBAL_STOP","run":"38884069913"}'::jsonb
 AND ctl->>'manual_stop'='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE'
 AND ctl->>'last_hard_stop'='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE'
 AND ctl->'hard_stop_generation'='3'::jsonb
 AND subject->>'council'='oldham'
 AND ctl->'oldham_allowances'->authority->'package'->>'authority'=authority
 AND ctl->'oldham_allowances'->authority->'package'->'scope'->>'council'='oldham'
 AND ctl->'oldham_allowances'->authority->'package'->'scope'->>'semantics'='RECEIVED'
 AND ctl->'oldham_allowances'->authority->'package'->'stop'=jsonb_build_object('global_stop',ctl->'global_stop','manual_stop',ctl->'manual_stop','last_hard_stop',ctl->'last_hard_stop','hard_stop_generation',ctl->'hard_stop_generation')
 AND ctl->'oldham_allowances'->authority->'source_cap'=ctl->'oldham_allowances'->authority->'package'->'registration'->'grant'->'source_calls'
 AND ctl->'oldham_allowances'->authority->'write_cap'=ctl->'oldham_allowances'->authority->'package'->'registration'->'grant'->'writes'
 AND ctl->'oldham_allowances'->authority->'expires_at'=ctl->'oldham_allowances'->authority->'package'->'registration'->'grant'->'expires_at'
 AND ctl->'oldham_allowances'->authority->>'package_sha256'=ctl->'grants'->authority->>'oldham_package_sha256'
 AND ctl->'oldham_allowances'->authority->>'package_sha256'=encode(sha256(convert_to((ctl->'oldham_allowances'->authority->'package')::text,'UTF8')),'hex')
 AND ctl->'oldham_allowances'->authority->>'revoked'='false'
 AND (ctl->'oldham_allowances'->authority->>'expires_at')::double precision>extract(epoch FROM clock_timestamp())
 AND ctl->'oldham_allowances'->authority->'grant_binding'=(ctl->'grants'->authority)-ARRAY['source_calls','writes']
 AND ((ctl->'grants'->authority)-ARRAY['source_calls','writes','oldham_package_sha256'])=((ctl->'oldham_allowances'->authority->'package'->'registration'->'grant')-ARRAY['source_calls','writes'])
 AND ctl->'oldham_allowances'->authority->'grant_binding'->'keys' ? work_key
 AND (ctl->'grants'->authority->>'source_calls')::integer BETWEEN 0 AND (ctl->'oldham_allowances'->authority->>'source_cap')::integer
 AND (ctl->'grants'->authority->>'writes')::integer BETWEEN 0 AND (ctl->'oldham_allowances'->authority->>'write_cap')::integer
 AND ctl->'oldham_allowances'->authority->'grant_binding'->'bindings'->work_key->'subject'=subject,false)
$oldham$;
REVOKE ALL ON FUNCTION public.ingestion_oldham_allowed(jsonb,text,text,jsonb) FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.ingestion_worker_step(p_op text,p_key text,p_fence integer,p_owner text,p_authority text,p_binding jsonb,p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $fn$
DECLARE w public.ingestion_work_items%ROWTYPE; ctl jsonb; g jsonb; t double precision; dep text; answer jsonb; n bigint; child jsonb; rec jsonb; old_child jsonb; capture public.ingestion_work_items%ROWTYPE; plan jsonb; idx integer;
BEGIN
 IF p_op IN ('fence_effect','resolve_effect','enqueue_child','batch_row','batch_reseal') THEN
  IF NOT pg_has_role(session_user,'ingestion_effect_broker','USAGE') THEN RAISE EXCEPTION 'BROKER_REQUIRED' USING ERRCODE='42501'; END IF;
 ELSE
  IF session_user<>'ingestion_worker_login' OR NOT pg_has_role(session_user,'ingestion_worker','USAGE') THEN RAISE EXCEPTION 'WORKER_LOGIN_REQUIRED' USING ERRCODE='42501'; END IF;
 END IF;
 IF p_fence IS NULL OR jsonb_typeof(p_binding) IS DISTINCT FROM 'object' OR jsonb_typeof(p_payload) IS DISTINCT FROM 'object' OR p_op IS NULL OR p_op NOT IN ('claim','checkpoint','complete','begin_source','begin_write','fence_effect','resolve_effect','block','enqueue_child','batch_row','batch_reseal') OR p_key IS NULL OR p_key !~ '^[a-f0-9]{64}$' OR p_key=repeat('0',64)
 OR p_owner IS NULL OR p_owner !~ '^[A-Za-z0-9_-]{1,100}$' OR p_authority IS NULL OR length(p_authority)>100
 OR p_binding IS NULL OR p_payload IS NULL OR octet_length(p_binding::text)>8192 OR octet_length(p_payload::text)>131072
 THEN RAISE EXCEPTION 'BOUNDED_ARGUMENTS' USING ERRCODE='22023'; END IF;
 SELECT outcome::jsonb INTO STRICT ctl FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE;
 SELECT * INTO STRICT w FROM public.ingestion_work_items WHERE key=p_key FOR UPDATE;
 t:=extract(epoch FROM clock_timestamp());
 IF (left(p_authority,23)='INGESTION_CHAIN_OLDHAM_') AND NOT public.ingestion_oldham_allowed(ctl,p_authority,w.key,w.subject::jsonb) THEN RAISE EXCEPTION 'OLDHAM_ALLOWANCE_INVALID' USING ERRCODE='42501'; END IF;
 IF ctl->'global_stop' IS DISTINCT FROM 'null'::jsonb THEN
  IF NOT (public.ingestion_bolton_allowed(ctl,p_authority,w.subject::jsonb) OR public.ingestion_oldham_allowed(ctl,p_authority,w.key,w.subject::jsonb)) THEN RAISE EXCEPTION 'GLOBAL_STOP' USING ERRCODE='42501'; END IF;
 END IF;
 IF EXISTS(SELECT 1 FROM public.ingestion_work_items WHERE state='PERSISTENCE_UNCERTAIN') THEN RAISE EXCEPTION 'PERSISTENCE_UNCERTAIN_GLOBAL'; END IF;
 IF EXISTS(SELECT 1 FROM public.ingestion_work_items WHERE phase='WRITE_INTENT' AND (key<>p_key OR p_op NOT IN ('fence_effect','resolve_effect','enqueue_child','batch_row','batch_reseal'))) THEN RAISE EXCEPTION 'UNRESOLVED_WRITE_BARRIER' USING ERRCODE='42501'; END IF;
 IF (ctl->'council_deferred_until'->>(w.subject->>'council'))::double precision>t THEN RAISE EXCEPTION 'COUNCIL_DEFERRED' USING ERRCODE='42501'; END IF;
 g:=ctl->'grants'->p_authority;
 IF g IS NULL OR (g->'keys' ? p_key) IS DISTINCT FROM true OR (g->'contracts' ? w.contract) IS DISTINCT FROM true
 OR jsonb_typeof(g->'expires_at') IS DISTINCT FROM 'number' OR coalesce((g->>'expires_at')::double precision,0)<=t OR (g->>'expires_at')::double precision>t+86400
 OR (CASE WHEN p_op IN ('fence_effect','resolve_effect','enqueue_child','batch_row','batch_reseal') THEN g->>'effect_login' ELSE g->>'login' END) IS DISTINCT FROM session_user OR (g->'workers' ? p_owner) IS DISTINCT FROM true
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
  IF p_op NOT IN ('fence_effect','resolve_effect','enqueue_child','batch_row','batch_reseal') AND w.phase NOT IN ('CLAIMED','CHECKPOINTED') THEN RAISE EXCEPTION 'EFFECT_RESOLUTION_REQUIRES_TRUSTED_WRITER' USING ERRCODE='42501'; END IF;
  IF p_op IN ('batch_row','batch_reseal') THEN
   plan:=w.checkpoint::jsonb->'plan';
   IF jsonb_typeof(plan) IS DISTINCT FROM 'object' OR jsonb_typeof(plan->'first') IS DISTINCT FROM 'number'
   OR jsonb_typeof(plan->'last') IS DISTINCT FROM 'number' OR jsonb_typeof(plan->'capture_key') IS DISTINCT FROM 'string'
   OR jsonb_typeof(plan->'capture_sha256') IS DISTINCT FROM 'string'
   OR jsonb_typeof(p_payload->'plan_json') IS DISTINCT FROM 'string' OR jsonb_typeof(p_payload->'capture_json') IS DISTINCT FROM 'string'
   OR (w.checkpoint::jsonb->>'kind' IN ('BATCH_PLAN_V1','BATCH_PROGRESS_V1')) IS DISTINCT FROM true
   OR (w.checkpoint::jsonb->>'kind'='BATCH_PROGRESS_V1' AND (jsonb_typeof(w.checkpoint::jsonb->'next') IS DISTINCT FROM 'number' OR jsonb_typeof(w.checkpoint::jsonb->'children') IS DISTINCT FROM 'array'))
   THEN RAISE EXCEPTION 'BATCH_TYPES'; END IF;
   IF w.task<>'LISTING_METADATA' OR w.contract<>'listing-batch-v1' OR w.checkpoint::jsonb->>'kind' NOT IN ('BATCH_PLAN_V1','BATCH_PROGRESS_V1')
   OR (p_payload->>'plan_json')::jsonb IS DISTINCT FROM plan OR encode(sha256(convert_to(p_payload->>'plan_json','UTF8')),'hex') IS DISTINCT FROM w.revision
   OR (plan->>'first')::integer<0 OR (plan->>'last')::integer-(plan->>'first')::integer NOT BETWEEN 1 AND 5 OR (plan->>'last')::integer>60
   THEN RAISE EXCEPTION 'EXACT_BATCH_PLAN'; END IF;
   SELECT * INTO STRICT capture FROM public.ingestion_work_items WHERE key=plan->>'capture_key' FOR SHARE;
   IF capture.state<>'COMPLETE' OR capture.task<>'DISCOVERY' OR (coalesce(capture.checkpoint::jsonb->>'kind'='LISTING_RECEIPT_V1' OR (capture.checkpoint::jsonb->>'kind'='LISTING_OBSERVATION_V1' AND capture.subject::jsonb->>'council'='bolton' AND capture.subject::jsonb->>'semantics'='RECEIVED' AND g->'observation_councils'='["bolton"]'::jsonb),false)) IS DISTINCT FROM true
   OR capture.subject::jsonb IS DISTINCT FROM w.subject::jsonb OR (w.dependencies::jsonb ? capture.key) IS DISTINCT FROM true
   OR (p_payload->>'capture_json')::jsonb IS DISTINCT FROM capture.checkpoint::jsonb
   OR encode(sha256(convert_to(p_payload->>'capture_json','UTF8')),'hex') IS DISTINCT FROM plan->>'capture_sha256'
   OR (plan->>'last')::integer>jsonb_array_length(capture.checkpoint::jsonb->'records') THEN RAISE EXCEPTION 'CAPTURE_BINDING'; END IF;
   IF capture.checkpoint::jsonb->>'kind'='LISTING_OBSERVATION_V1' AND plan->>'source_kind' IS DISTINCT FROM 'LISTING_OBSERVATION_V1' THEN RAISE EXCEPTION 'OBSERVATION_PLAN_BINDING'; END IF;
   idx:=coalesce((w.checkpoint::jsonb->>'next')::integer,(plan->>'first')::integer);
   IF idx NOT BETWEEN (plan->>'first')::integer AND (plan->>'last')::integer THEN RAISE EXCEPTION 'BATCH_PROGRESS_RANGE'; END IF;
   IF p_op='batch_reseal' THEN
    IF idx<>(plan->>'last')::integer OR w.checkpoint::jsonb->>'kind'<>'BATCH_PROGRESS_V1' THEN RAISE EXCEPTION 'BATCH_NOT_MATERIALISED'; END IF;
    UPDATE public.ingestion_work_items SET phase='CHECKPOINTED' WHERE key=p_key RETURNING * INTO w;
    RETURN to_jsonb(w);
   END IF;
   IF idx>=(plan->>'last')::integer THEN RAISE EXCEPTION 'BATCH_FULL'; END IF;
   rec:=capture.checkpoint::jsonb->'records'->idx;child:=p_payload->'child';
   IF jsonb_typeof(child) IS DISTINCT FROM 'object' OR jsonb_typeof(child->'max_attempts') IS DISTINCT FROM 'number'
   OR jsonb_typeof(child->'priority') IS DISTINCT FROM 'number' OR child->>'task' IS DISTINCT FROM 'SCREENING'
   OR (((plan ? 'screening') IS DISTINCT FROM true AND child->>'contract'='listing-screen-v1') OR ((plan ? 'screening') IS TRUE AND jsonb_typeof(plan->'screening')='object' AND (plan->'screening')-ARRAY['contract','config_sha256']='{}'::jsonb AND plan->'screening'->>'contract'='listing-screen-v3' AND plan->'screening'->>'config_sha256' ~ '^[a-f0-9]{64}$' AND jsonb_typeof(g->'screening_configs')='array' AND g->'screening_configs' ? (plan->'screening'->>'config_sha256') AND child->>'contract'='listing-screen-v3' AND (coalesce(capture.checkpoint::jsonb->>'kind'='LISTING_RECEIPT_V1' OR (capture.checkpoint::jsonb->>'kind'='LISTING_OBSERVATION_V1' AND capture.subject::jsonb->>'council'='bolton' AND capture.subject::jsonb->>'semantics'='RECEIVED' AND g->'observation_councils'='["bolton"]'::jsonb),false)))) IS DISTINCT FROM true OR jsonb_typeof(p_payload->'record_json') IS DISTINCT FROM 'string'
   OR jsonb_typeof(p_payload->'identity_json') IS DISTINCT FROM 'string' THEN RAISE EXCEPTION 'BATCH_ROW_TYPES'; END IF;
   IF child->'subject' IS DISTINCT FROM jsonb_build_object('kind','APPLICATION','council',capture.subject->>'council','reference',rec->>'reference')
   OR child->'dependencies' IS DISTINCT FROM jsonb_build_array(capture.key) OR child->>'task'<>'SCREENING' OR child->>'contract' IS DISTINCT FROM (CASE WHEN (plan ? 'screening') IS TRUE THEN 'listing-screen-v3' ELSE 'listing-screen-v1' END)
   OR (child->>'max_attempts')::integer<>2 OR child->'limits' IS DISTINCT FROM w.limits::jsonb OR (child->>'priority')::integer<>w.priority
   OR (p_payload->>'record_json')::jsonb IS DISTINCT FROM rec OR (CASE WHEN capture.checkpoint::jsonb->>'kind'='LISTING_OBSERVATION_V1' THEN encode(sha256(convert_to('{"assessment_revision":"'||(CASE WHEN (plan ? 'screening') IS TRUE THEN encode(sha256(convert_to('{"config_sha256":"'||(plan->'screening'->>'config_sha256')||'","record_sha256":"'||encode(sha256(convert_to(p_payload->>'record_json','UTF8')),'hex')||'"}','UTF8')),'hex') ELSE encode(sha256(convert_to(p_payload->>'record_json','UTF8')),'hex') END)||'","observation_sha256":"'||(plan->>'capture_sha256')||'"}','UTF8')),'hex') ELSE (CASE WHEN (plan ? 'screening') IS TRUE THEN encode(sha256(convert_to('{"config_sha256":"'||(plan->'screening'->>'config_sha256')||'","record_sha256":"'||encode(sha256(convert_to(p_payload->>'record_json','UTF8')),'hex')||'"}','UTF8')),'hex') ELSE encode(sha256(convert_to(p_payload->>'record_json','UTF8')),'hex') END) END) IS DISTINCT FROM child->>'revision'
   OR (p_payload->>'identity_json')::jsonb IS DISTINCT FROM child-ARRAY['key','dependencies','priority','max_attempts','limits']
   OR encode(sha256(convert_to(p_payload->>'identity_json','UTF8')),'hex') IS DISTINCT FROM child->>'key' THEN RAISE EXCEPTION 'BATCH_ROW_IDENTITY'; END IF;
   SELECT to_jsonb(x) INTO old_child FROM public.ingestion_work_items x WHERE key=child->>'key';
   IF old_child IS NULL THEN
    IF (SELECT count(*) FROM public.ingestion_work_items)>=4096 THEN RAISE EXCEPTION 'ITEM_BOUND'; END IF;
    INSERT INTO public.ingestion_work_items(key,subject,task,contract,revision,dependencies,priority,eligible_at,state,next_action,limits,attempt_count,max_attempts,fence,phase)
    VALUES(child->>'key',(child->'subject')::json,'SCREENING',child->>'contract',child->>'revision',json_build_array(capture.key),w.priority,0,'QUEUED','CLAIM_WHEN_AUTHORISED',w.limits,0,2,0,'IDLE');
   ELSIF old_child->'subject' IS DISTINCT FROM child->'subject' OR old_child->>'revision' IS DISTINCT FROM child->>'revision' OR old_child->'dependencies' IS DISTINCT FROM child->'dependencies' OR old_child->'limits' IS DISTINCT FROM child->'limits' THEN RAISE EXCEPTION 'CONFLICTING_DUPLICATE'; END IF;
   answer:=jsonb_build_object('kind','BATCH_PROGRESS_V1','plan',plan,'next',idx+1,'children',coalesce(w.checkpoint::jsonb->'children','[]'::jsonb)||jsonb_build_array(child->>'key'));
   UPDATE public.ingestion_work_items SET checkpoint=answer::json,phase='CHECKPOINTED' WHERE key=p_key RETURNING * INTO w;
   UPDATE public.ingestion_work_attempts SET checkpoint=answer::json,phase='CHECKPOINTED' WHERE work_key=p_key AND fence=p_fence;
  ELSIF p_op='enqueue_child' THEN
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
   IF nullif(w.checkpoint::jsonb,'null'::jsonb) IS NOT NULL AND NOT (p_op='begin_write' AND w.checkpoint::jsonb->>'kind'='DETAIL_RECEIPT_V1' AND (g->'detail_source_keys' ? p_key) IS TRUE) THEN RAISE EXCEPTION 'CHECKPOINT_RESUME_NO_EFFECT_REPLAY'; END IF;
   IF p_payload<>jsonb_build_object('cost',(p_payload->>'cost')::integer) OR coalesce((p_payload->>'cost')::integer,0) NOT BETWEEN 1 AND 2 OR (p_op='begin_source' AND ((p_payload->>'cost')::integer<>1 OR NOT ((w.task IN ('DISCOVERY','LISTING_METADATA') AND w.subject->>'kind'='DISCOVERY_SCOPE') OR (w.task='FACTUAL_REFRESH' AND w.subject->>'kind'='APPLICATION' AND (g->'detail_source_keys' ? p_key) IS TRUE)))) OR (p_op='begin_write' AND w.task<>'FACTUAL_REFRESH') THEN RAISE EXCEPTION 'TASK_EFFECT'; END IF;
   IF p_op='begin_write' AND (g->'detail_source_keys' ? p_key) IS TRUE AND w.checkpoint::jsonb->>'kind' IS DISTINCT FROM 'DETAIL_RECEIPT_V1' THEN RAISE EXCEPTION 'QUALIFIED_DETAIL_RECEIPT_REQUIRED'; END IF;
   dep:=CASE WHEN p_op='begin_source' THEN 'source_calls' ELSE 'writes' END;
   IF coalesce((g->>dep)::integer,0)<(p_payload->>'cost')::integer THEN RAISE EXCEPTION 'EFFECT_ALLOWANCE_EXHAUSTED' USING ERRCODE='42501'; END IF;
   g:=jsonb_set(g,ARRAY[dep],to_jsonb((g->>dep)::integer-(p_payload->>'cost')::integer));
   ctl:=jsonb_set(ctl,ARRAY['grants',p_authority],g);
   UPDATE public.ingestion_work_items SET outcome=ctl::json WHERE key=repeat('0',64);
   UPDATE public.ingestion_work_items SET phase=CASE WHEN p_op='begin_source' THEN 'SOURCE_INTENT' ELSE 'WRITE_INTENT' END WHERE key=p_key RETURNING * INTO w;
   UPDATE public.ingestion_work_attempts SET phase=w.phase WHERE work_key=p_key AND fence=p_fence;
  ELSIF p_op IN ('fence_effect','resolve_effect','enqueue_child','batch_row','batch_reseal') THEN
   IF w.phase NOT IN ('SOURCE_INTENT','WRITE_INTENT') THEN RAISE EXCEPTION 'DURABLE_INTENT_REQUIRED'; END IF;
   -- fence_effect is held open by the trusted broker transaction across the
   -- existing shared writer; workers cannot resolve an intent or clear a stop.
   IF p_op='resolve_effect' THEN
    IF (p_payload->>'kind'='LISTING_OBSERVATION_V1' AND (w.task<>'DISCOVERY' OR (coalesce(p_payload->>'kind'='LISTING_RECEIPT_V1' OR (p_payload->>'kind'='LISTING_OBSERVATION_V1' AND w.subject::jsonb->>'council'='bolton' AND w.subject::jsonb->>'semantics'='RECEIVED' AND g->'observation_councils'='["bolton"]'::jsonb),false)) IS DISTINCT FROM true)) OR (w.task='DISCOVERY' AND (g->>'capture_only')::boolean IS TRUE AND (coalesce(p_payload->>'kind'='LISTING_RECEIPT_V1' OR (p_payload->>'kind'='LISTING_OBSERVATION_V1' AND w.subject::jsonb->>'council'='bolton' AND w.subject::jsonb->>'semantics'='RECEIVED' AND g->'observation_councils'='["bolton"]'::jsonb),false)) IS DISTINCT FROM true) THEN RAISE EXCEPTION 'BROKER_CAPTURE_REQUIRED'; END IF;
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
   IF p_payload->>'kind'='LISTING_OBSERVATION_V1' AND (w.task<>'DISCOVERY' OR w.checkpoint::jsonb IS DISTINCT FROM p_payload OR (coalesce(p_payload->>'kind'='LISTING_RECEIPT_V1' OR (p_payload->>'kind'='LISTING_OBSERVATION_V1' AND w.subject::jsonb->>'council'='bolton' AND w.subject::jsonb->>'semantics'='RECEIVED' AND g->'observation_councils'='["bolton"]'::jsonb),false)) IS DISTINCT FROM true) THEN RAISE EXCEPTION 'BROKER_CAPTURE_REQUIRED'; END IF;
   IF (g->>'capture_only')::boolean IS TRUE AND w.task='DISCOVERY' AND (w.checkpoint::jsonb IS DISTINCT FROM p_payload OR (coalesce(w.checkpoint::jsonb->>'kind'='LISTING_RECEIPT_V1' OR (w.checkpoint::jsonb->>'kind'='LISTING_OBSERVATION_V1' AND w.subject::jsonb->>'council'='bolton' AND w.subject::jsonb->>'semantics'='RECEIVED' AND g->'observation_councils'='["bolton"]'::jsonb),false)) IS DISTINCT FROM true) THEN RAISE EXCEPTION 'BROKER_CAPTURE_REQUIRED'; END IF;
   IF w.contract='listing-batch-v1' THEN RAISE EXCEPTION 'BROKER_PROGRESS_REQUIRED'; END IF;
   IF w.checkpoint::jsonb->>'kind'='DETAIL_RECEIPT_V1' OR p_payload->>'kind'='DETAIL_RECEIPT_V1' OR w.checkpoint::jsonb->>'outcome' IN ('SUPPORTED_FACTS_VERIFIED','INITIAL_FACTS_VERIFIED') OR p_payload->>'outcome' IN ('SUPPORTED_FACTS_VERIFIED','INITIAL_FACTS_VERIFIED') THEN RAISE EXCEPTION 'BROKER_FACT_RECEIPT_REQUIRED' USING ERRCODE='42501'; END IF;
   IF octet_length(p_payload::text)>least(131072,(w.limits->>'audit_bytes')::integer) OR jsonb_typeof(p_payload)<>'object' THEN RAISE EXCEPTION 'CHECKPOINT_BOUND'; END IF;
   IF w.task='SCREENING' THEN
    SELECT * INTO STRICT capture FROM public.ingestion_work_items WHERE key=w.dependencies::jsonb->>0 FOR SHARE;
    IF capture.checkpoint::jsonb->>'kind'='LISTING_OBSERVATION_V1' THEN
     IF (coalesce(capture.checkpoint::jsonb->>'kind'='LISTING_RECEIPT_V1' OR (capture.checkpoint::jsonb->>'kind'='LISTING_OBSERVATION_V1' AND capture.subject::jsonb->>'council'='bolton' AND capture.subject::jsonb->>'semantics'='RECEIVED' AND g->'observation_councils'='["bolton"]'::jsonb),false)) IS DISTINCT FROM true OR capture.state<>'COMPLETE'
      OR p_payload->>'source_kind' IS DISTINCT FROM 'LISTING_OBSERVATION_V1' OR p_payload->>'window_claim' IS DISTINCT FROM 'NONE'
      OR p_payload->>'observed_at' IS DISTINCT FROM capture.checkpoint::jsonb->>'observed_at'
      OR p_payload->>'source_sha256' IS DISTINCT FROM capture.checkpoint::jsonb->>'source_sha256'
      OR coalesce(p_payload->>'observation_digest','') !~ '^[a-f0-9]{64}$'
      OR (w.contract='listing-screen-v1' AND encode(sha256(convert_to('{"assessment_revision":"'||(p_payload->>'record_sha256')||'","observation_sha256":"'||(p_payload->>'observation_digest')||'"}','UTF8')),'hex') IS DISTINCT FROM w.revision)
     THEN RAISE EXCEPTION 'OBSERVATION_SCREEN_BINDING'; END IF;
    ELSIF p_payload ?| ARRAY['source_kind','observation_digest','window_claim','observed_at'] THEN RAISE EXCEPTION 'OBSERVATION_SOURCE_KIND'; END IF;
   END IF;
   IF w.contract='listing-screen-v3' AND (coalesce(p_payload->>'rule_version','')<>'manchester-listing-screen-assessment-v3' OR coalesce(p_payload->>'routing_authority','')<>'count_assessment' OR jsonb_typeof(p_payload->'count_assessment') IS DISTINCT FROM 'object' OR coalesce((p_payload->'count_assessment'->>'admission') NOT IN ('ADMIT_FOR_ASSESSMENT','ADMIT_SCHEME','RETAIN_BELOW_THRESHOLD','RETAIN_NOT_RESIDENTIAL_SUPPLY','RETAIN_RELATED_TO_PARENT','RETAIN_UNUSABLE_PROPOSAL','RETAIN_WATCHLIST','ROUTE_COUNT_UNCONFIRMED'),true) OR coalesce(p_payload->>'assessment_revision','')<>w.revision OR coalesce(p_payload->>'record_sha256','') !~ '^[a-f0-9]{64}$' OR coalesce(p_payload->>'config_sha256','') !~ '^[a-f0-9]{64}$' OR (CASE WHEN p_payload->>'source_kind'='LISTING_OBSERVATION_V1' THEN encode(sha256(convert_to('{"assessment_revision":"'||encode(sha256(convert_to('{"config_sha256":"'||(p_payload->>'config_sha256')||'","record_sha256":"'||(p_payload->>'record_sha256')||'"}','UTF8')),'hex')||'","observation_sha256":"'||(p_payload->>'observation_digest')||'"}','UTF8')),'hex') ELSE encode(sha256(convert_to('{"config_sha256":"'||(p_payload->>'config_sha256')||'","record_sha256":"'||(p_payload->>'record_sha256')||'"}','UTF8')),'hex') END) IS DISTINCT FROM w.revision OR coalesce(NOT (g->'screening_configs' ? (p_payload->>'config_sha256')),true)) THEN RAISE EXCEPTION 'SCREENING_V3_RECEIPT'; END IF;
   -- SQL records a worker receipt, never promotes its contents to factual truth.
   UPDATE public.ingestion_work_items SET checkpoint=p_payload::json,phase='CHECKPOINTED' WHERE key=p_key RETURNING * INTO w;
   UPDATE public.ingestion_work_attempts SET checkpoint=p_payload::json,phase='CHECKPOINTED' WHERE work_key=p_key AND fence=p_fence;
  ELSE
   IF w.phase<>'CHECKPOINTED' OR nullif(w.checkpoint::jsonb,'null'::jsonb) IS NULL OR jsonb_typeof(p_payload)<>'object'
   OR (g->'completion_outcomes'->w.task ? (p_payload->>'outcome')) IS DISTINCT FROM true
   OR (p_payload->>'outcome' IN ('SUPPORTED_FACTS_VERIFIED','INITIAL_FACTS_VERIFIED') AND w.checkpoint::jsonb->>'outcome' IS DISTINCT FROM p_payload->>'outcome')
   OR p_payload ?| ARRAY['global_stop','grants','authority','verified_facts'] THEN RAISE EXCEPTION 'TASK_COMPLETION_CONTRACT' USING ERRCODE='42501'; END IF;
   IF w.contract='listing-screen-v3' AND (p_payload->>'outcome' IS DISTINCT FROM w.checkpoint::jsonb->'count_assessment'->>'admission' OR coalesce(NOT (g->'screening_configs' ? (w.checkpoint::jsonb->>'config_sha256')),true)) THEN RAISE EXCEPTION 'SCREENING_V3_OUTCOME'; END IF;
   IF w.contract='listing-batch-v1' THEN
    IF w.checkpoint::jsonb->>'kind'<>'BATCH_PROGRESS_V1' OR (w.checkpoint::jsonb->>'next')::integer<>(w.checkpoint::jsonb->'plan'->>'last')::integer
    OR jsonb_array_length(w.checkpoint::jsonb->'children')<>(w.checkpoint::jsonb->'plan'->>'last')::integer-(w.checkpoint::jsonb->'plan'->>'first')::integer
    OR EXISTS(SELECT 1 FROM jsonb_array_elements_text(w.checkpoint::jsonb->'children') k WHERE NOT EXISTS(SELECT 1 FROM public.ingestion_work_items x WHERE x.key=k AND x.state='COMPLETE' AND x.task='SCREENING')) THEN RAISE EXCEPTION 'BATCH_INCOMPLETE'; END IF;
   END IF;
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
RESET ROLE;
REVOKE CREATE ON SCHEMA public FROM ingestion_storage_owner;
REVOKE ingestion_storage_owner FROM CURRENT_USER GRANTED BY CURRENT_USER;
COMMIT;
