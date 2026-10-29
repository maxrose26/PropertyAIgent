"""Narrow daily-intake extension of the EXISTING issuer/policy/worker.

Offline SQL generation only. No new role/table, stop release or installation.
The owner preauthorises an expiring period; worker credentials can register only
that period's bounded daily capture and its source-free screening children.
"""
from . import screening_v3_worker_sql as v3

SNAPSHOT = "jsonb_build_object('global_stop',ctl->'global_stop','manual_stop',ctl->'manual_stop','last_hard_stop',ctl->'last_hard_stop','hard_stop_generation',coalesce(ctl->'hard_stop_generation','0'::jsonb))"

# Branch is inserted before the historical owner-only registration branch.
REGISTRATION = r"""
 IF p->>'operation' IN ('intake_period','intake_capture','intake_screen','intake_close') THEN
  IF p IS NULL OR jsonb_typeof(p)<>'object' OR octet_length(p::text)>131072 THEN RAISE EXCEPTION 'INTAKE_ARGUMENT_BOUND'; END IF;
  SELECT outcome::jsonb INTO STRICT ctl FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE;
  t:=extract(epoch FROM clock_timestamp());
  a:=p->>'period';
  IF a IS NULL OR a !~ '^[A-Za-z0-9_-]{1,60}$' THEN RAISE EXCEPTION 'INTAKE_PERIOD_ID'; END IF;
  IF p->>'operation'='intake_period' THEN
   IF NOT pg_has_role(session_user,'ingestion_barrier_releaser','USAGE') THEN RAISE EXCEPTION 'OWNER_DISPOSITION_REQUIRED' USING ERRCODE='42501'; END IF;
   e:=p->'policy';
   IF jsonb_typeof(e) IS DISTINCT FROM 'object' OR NOT (e ?& ARRAY['expires_at','max_runs','overlap_days','councils','expected_stop','execution_binding','test_evidence','screening_config']) OR NOT (e->'execution_binding' ?& ARRAY['revision','workflow_sha256','manifest_sha256']) OR ctl->'intake_periods' ? a
    OR jsonb_typeof(e->'expires_at') IS DISTINCT FROM 'number'
    OR (e->>'expires_at')::double precision<=t OR (e->>'expires_at')::double precision>t+604800
    OR e->'max_runs' IS DISTINCT FROM '7'::jsonb OR e->'overlap_days' IS DISTINCT FROM '7'::jsonb
    OR jsonb_typeof(e->'councils') IS DISTINCT FROM 'object' OR (SELECT count(*) FROM jsonb_each(e->'councils')) NOT BETWEEN 1 AND 2
    OR (e->'councils')-ARRAY['tameside','manchester']<>'{}'::jsonb
    OR e->'expected_stop' IS DISTINCT FROM __SNAPSHOT__
    OR jsonb_typeof(e->'screening_config') IS DISTINCT FROM 'string'
    OR jsonb_typeof(e->'execution_binding'->'revision') IS DISTINCT FROM 'string'
    OR jsonb_typeof(e->'execution_binding'->'workflow_sha256') IS DISTINCT FROM 'string'
    OR jsonb_typeof(e->'execution_binding'->'manifest_sha256') IS DISTINCT FROM 'string'
    OR e->'execution_binding'->>'revision' !~ '^[a-f0-9]{40}$'
    OR e->'execution_binding'->>'workflow_sha256' !~ '^[a-f0-9]{64}$'
    OR e->'execution_binding'->>'manifest_sha256' !~ '^[a-f0-9]{64}$'
    OR jsonb_typeof(e->'test_evidence') IS DISTINCT FROM 'boolean'
    OR e->>'screening_config' !~ '^[a-f0-9]{64}$'
   THEN RAISE EXCEPTION 'INTAKE_PERIOD_POLICY'; END IF;
   FOR item IN SELECT value FROM jsonb_each(e->'councils') LOOP
    IF jsonb_typeof(item) IS DISTINCT FROM 'object' OR NOT (item ?& ARRAY['contract','qualification_sha256']) OR jsonb_typeof(item->'contract') IS DISTINCT FROM 'string' OR jsonb_typeof(item->'qualification_sha256') IS DISTINCT FROM 'string' OR item->>'contract' !~ '^[A-Za-z0-9_-]{1,100}$'
     OR item->>'qualification_sha256' !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'INTAKE_QUALIFIED_CONTRACT'; END IF;
   END LOOP;
   e:=e||jsonb_build_object('registered_at',t,'days','{}'::jsonb);
   ctl:=jsonb_set(ctl,'{intake_periods}',coalesce(ctl->'intake_periods','{}'::jsonb)||jsonb_build_object(a,e));
   UPDATE public.ingestion_work_items SET outcome=ctl::json WHERE key=repeat('0',64);
   RETURN e;
  END IF;
  IF session_user<>'ingestion_worker_login' OR NOT pg_has_role(session_user,'ingestion_worker','USAGE') THEN RAISE EXCEPTION 'INTAKE_WORKER_ONLY' USING ERRCODE='42501'; END IF;
  e:=ctl->'intake_periods'->a;
  IF e IS NULL OR p->'execution_binding' IS DISTINCT FROM e->'execution_binding'
   OR (p->>'operation'<>'intake_close' AND ((e->>'expires_at')::double precision<=t OR e->'expected_stop' IS DISTINCT FROM __SNAPSHOT__)) THEN RAISE EXCEPTION 'INTAKE_PERIOD_EXPIRED_OR_STOP_CHANGED'; END IF;
  IF p->>'operation'='intake_close' THEN
   IF jsonb_typeof(p->'authorities') IS DISTINCT FROM 'array' OR jsonb_array_length(p->'authorities')>4 THEN RAISE EXCEPTION 'INTAKE_CLOSE_BOUND'; END IF;
   FOR item IN SELECT value FROM jsonb_array_elements(p->'authorities') LOOP
    IF ctl->'grants'->(item#>>'{}')->>'intake_period' IS DISTINCT FROM a THEN RAISE EXCEPTION 'INTAKE_CLOSE_IDENTITY'; END IF;
    ctl:=jsonb_set(ctl,ARRAY['grants',item#>>'{}','expires_at'],'0'::jsonb);
   END LOOP;
   UPDATE public.ingestion_work_items SET outcome=ctl::json WHERE key=repeat('0',64);
   RETURN jsonb_build_object('authorities_invalidated',true,'stop_preserved',true);
  END IF;
  g:=p->'grant';
  IF jsonb_typeof(g) IS DISTINCT FROM 'object' OR NOT (g ?& ARRAY['login','effect_login','workers','writes','detail_source_keys','capture_only','execution_binding','expires_at','bindings','keys','contracts','source_calls','capture_key','completion_outcomes']) OR jsonb_typeof(p->'authority') IS DISTINCT FROM 'string' OR jsonb_typeof(p->'rows') IS DISTINCT FROM 'array'
   OR jsonb_array_length(p->'rows') NOT BETWEEN 1 AND 73
   OR g->'login' IS DISTINCT FROM '"ingestion_worker_login"'::jsonb
   OR g->'effect_login' IS DISTINCT FROM '"ingestion_effect_login"'::jsonb
   OR g->'workers' IS DISTINCT FROM '["required_once"]'::jsonb OR g->'writes' IS DISTINCT FROM '0'::jsonb
   OR g->'detail_source_keys' IS DISTINCT FROM '[]'::jsonb OR g->'capture_only' IS DISTINCT FROM 'false'::jsonb
   OR g->'execution_binding' IS DISTINCT FROM e->'execution_binding'
   OR jsonb_typeof(g->'expires_at') IS DISTINCT FROM 'number' OR (g->>'expires_at')::double precision<=t
   OR (g->>'expires_at')::double precision>least(t+1800,(e->>'expires_at')::double precision)
   OR jsonb_typeof(g->'bindings') IS DISTINCT FROM 'object' OR jsonb_typeof(g->'keys') IS DISTINCT FROM 'array'
   OR jsonb_typeof(p->'identity_json') IS DISTINCT FROM 'object'
   OR p->>'authority' !~ '^INGESTION_CHAIN_[A-Z0-9_]{1,80}$'
   OR ctl->'grants' ? (p->>'authority')
  THEN RAISE EXCEPTION 'INTAKE_GRANT_BOUND'; END IF;
  IF p->>'operation'='intake_capture' THEN
   IF jsonb_array_length(p->'rows')<>1 OR g->'source_calls' IS DISTINCT FROM '1'::jsonb THEN RAISE EXCEPTION 'INTAKE_CAPTURE_ONLY'; END IF;
   item:=p->'rows'->0;
   IF item->>'task' IS DISTINCT FROM 'DISCOVERY' OR item->'subject'->>'kind' IS DISTINCT FROM 'DISCOVERY_SCOPE'
    OR NOT (item->'subject' ?& ARRAY['start','end','semantics','council'])
    OR jsonb_typeof(item->'subject'->'start') IS DISTINCT FROM 'string'
    OR jsonb_typeof(item->'subject'->'end') IS DISTINCT FROM 'string'
    OR jsonb_typeof(item->'subject'->'council') IS DISTINCT FROM 'string'
    OR item->'subject'->>'end'<>((clock_timestamp() AT TIME ZONE 'Europe/London')::date-1)::text
    OR item->'subject'->>'start'<>((clock_timestamp() AT TIME ZONE 'Europe/London')::date-7)::text
    OR item->'subject'->>'semantics' IS DISTINCT FROM (CASE WHEN item->'subject'->>'council'='manchester' THEN 'VALIDATED' ELSE 'RECEIVED' END)
    OR NOT (e->'councils' ? (item->'subject'->>'council'))
    OR item->>'contract' IS DISTINCT FROM e->'councils'->(item->'subject'->>'council')->>'contract'
    OR g->>'capture_key' IS DISTINCT FROM item->>'key' OR item->'dependencies'<>'[]'::jsonb
    OR (SELECT count(*) FROM jsonb_each(coalesce(e->'days','{}'::jsonb)))>=7 AND NOT (e->'days' ? item->'subject'->>'end')
    OR e->'days'->(item->'subject'->>'end') ? (item->'subject'->>'council')
   THEN RAISE EXCEPTION 'INTAKE_ROLLING_SCOPE_OR_CONSUMED'; END IF;
   e:=jsonb_set(e,ARRAY['days',item->'subject'->>'end'],coalesce(e->'days'->(item->'subject'->>'end'),'{}'::jsonb)||jsonb_build_object(item->'subject'->>'council',item->>'key'));
   -- jsonb_set cannot create a missing intermediate path; days exists from issuance.
   ctl:=jsonb_set(ctl,ARRAY['intake_periods',a],e);
  ELSE
   SELECT * INTO STRICT root FROM public.ingestion_work_items WHERE key=g->>'capture_key' FOR SHARE;
   IF root.state<>'COMPLETE' OR root.task<>'DISCOVERY' OR root.checkpoint::jsonb->>'kind'<>'LISTING_RECEIPT_V1'
    OR NOT (e->'councils' ? root.subject->>'council')
    OR e->'days'->(root.subject->>'end')->>(root.subject->>'council') IS DISTINCT FROM root.key
    OR g->'source_calls' IS DISTINCT FROM '0'::jsonb
    OR g->'screening_configs' IS DISTINCT FROM jsonb_build_array(e->>'screening_config')
   THEN RAISE EXCEPTION 'INTAKE_SCREEN_PARENT'; END IF;
  END IF;
  IF (SELECT count(*) FROM public.ingestion_work_items)+jsonb_array_length(p->'rows')>4096 THEN RAISE EXCEPTION 'ITEM_BOUND'; END IF;
  FOR item IN SELECT value FROM jsonb_array_elements(p->'rows') LOOP
   IF NOT (item ?& ARRAY['key','subject','task','contract','revision','dependencies','priority','eligible_at','state','reason','next_action','limits','authority','attempt_count','max_attempts','fence','owner','lease_until','phase','checkpoint','outcome']) OR jsonb_typeof(item->'key') IS DISTINCT FROM 'string' OR jsonb_typeof(item->'subject') IS DISTINCT FROM 'object' OR NOT (item->'subject' ?& ARRAY['kind','council']) OR jsonb_typeof(item->'subject'->'council') IS DISTINCT FROM 'string' OR jsonb_typeof(item->'task') IS DISTINCT FROM 'string' OR jsonb_typeof(item->'contract') IS DISTINCT FROM 'string' OR jsonb_typeof(item->'revision') IS DISTINCT FROM 'string' OR item->>'key' !~ '^[a-f0-9]{64}$' OR item->>'state' IS DISTINCT FROM 'QUEUED' OR item->>'phase' IS DISTINCT FROM 'IDLE'
    OR item->'attempt_count'<>'0'::jsonb OR item->'fence'<>'0'::jsonb OR item->'max_attempts'<>'2'::jsonb
    OR item->'owner'<>'null'::jsonb OR item->'authority'<>'null'::jsonb OR item->'lease_until'<>'null'::jsonb
    OR item->'outcome'<>'null'::jsonb OR item->'eligible_at'<>'0'::jsonb
    OR (p->'identity_json'->>(item->>'key'))::jsonb IS DISTINCT FROM jsonb_build_object('subject',item->'subject','task',item->'task','contract',item->'contract','revision',item->'revision')
    OR encode(sha256(convert_to(p->'identity_json'->>(item->>'key'),'UTF8')),'hex') IS DISTINCT FROM item->>'key'
    OR g->'bindings'->(item->>'key') IS DISTINCT FROM (p->'identity_json'->>(item->>'key'))::jsonb
   THEN RAISE EXCEPTION 'INTAKE_ITEM_BINDING'; END IF;
   IF p->>'operation'='intake_screen' THEN
    IF item->>'key'=root.key THEN
     IF item IS DISTINCT FROM to_jsonb(root) THEN RAISE EXCEPTION 'INTAKE_ROOT_IMMUTABLE'; END IF;
    ELSIF item->>'task'='LISTING_METADATA' THEN
     IF item->>'contract'<>'listing-batch-v1' OR item->'subject' IS DISTINCT FROM root.subject::jsonb
      OR item->'checkpoint'->'plan'->>'capture_key'<>root.key
      OR item->'checkpoint'->'plan'->'capture_bound' IS DISTINCT FROM 'true'::jsonb
      OR item->'checkpoint'->'plan'->'screening'->>'config_sha256' IS DISTINCT FROM e->>'screening_config'
     THEN RAISE EXCEPTION 'INTAKE_BATCH_SCOPE'; END IF;
    ELSIF item->>'task'='SCREENING' THEN
     IF item->>'contract'<>'listing-screen-v3' OR item->'subject'->>'council' IS DISTINCT FROM root.subject->>'council'
      OR item->'dependencies' IS DISTINCT FROM jsonb_build_array(root.key)
      OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(root.checkpoint::jsonb->'records') r WHERE r->>'reference'=item->'subject'->>'reference')
     THEN RAISE EXCEPTION 'INTAKE_SCREEN_SCOPE'; END IF;
    ELSE RAISE EXCEPTION 'INTAKE_NO_DOWNSTREAM_TASK'; END IF;
   END IF;
   -- Limits are finite positive values bounded by the existing worker envelope.
   IF NOT (item->'limits' ?& ARRAY['aggregate_rss','audit_bytes','bytes','outer_seconds','pages','requests','rows','source_rss','worker_seconds']) OR item->'limits' IS NULL OR jsonb_typeof(item->'limits')<>'object' OR (item->'limits')-ARRAY['aggregate_rss','audit_bytes','bytes','outer_seconds','pages','requests','rows','source_rss','worker_seconds']<>'{}'::jsonb
    OR EXISTS(SELECT 1 FROM jsonb_each(item->'limits') x WHERE jsonb_typeof(x.value)<>'number' OR (x.value::text)::numeric<=0)
    OR (item->'limits'->>'rows')::int>60 OR (item->'limits'->>'pages')::int>6 OR (item->'limits'->>'requests')::int>80
    OR (item->'limits'->>'bytes')::bigint>20971520 OR (item->'limits'->>'audit_bytes')::bigint>2097152
    OR (item->'limits'->>'worker_seconds')::int>75 OR (item->'limits'->>'outer_seconds')::int>90
    OR (item->'limits'->>'source_rss')::bigint>1610612736 OR (item->'limits'->>'aggregate_rss')::bigint>2147483648
   THEN RAISE EXCEPTION 'INTAKE_ITEM_LIMITS'; END IF;
   INSERT INTO public.ingestion_work_items SELECT * FROM jsonb_populate_record(NULL::public.ingestion_work_items,item);
  END LOOP;
  -- Screening grants include the already registered root binding but never insert it.
  IF (SELECT count(*) FROM jsonb_each(g->'bindings'))<>(SELECT count(*) FROM jsonb_array_elements(p->'rows'))+(CASE WHEN p->>'operation'='intake_screen' THEN 1 ELSE 0 END)
   OR jsonb_array_length(g->'keys')<>(SELECT count(*) FROM jsonb_each(g->'bindings'))
   OR EXISTS(SELECT 1 FROM jsonb_each(g->'bindings') b WHERE NOT (g->'keys' ? b.key) OR NOT (g->'contracts' ? (b.value->>'contract')))
   OR (p->>'operation'='intake_screen' AND g->'bindings'->root.key IS DISTINCT FROM jsonb_build_object('subject',root.subject::jsonb,'task',root.task,'contract',root.contract,'revision',root.revision))
  THEN RAISE EXCEPTION 'INTAKE_CLOSED_KEY_SET'; END IF;
  g:=g||jsonb_build_object('intake_period',a);
  ctl:=jsonb_set(ctl,'{grants}',coalesce(ctl->'grants','{}'::jsonb)||jsonb_build_object(p->>'authority',g));
  UPDATE public.ingestion_work_items SET outcome=ctl::json WHERE key=repeat('0',64);
  RETURN g;
 END IF;
""".replace('__SNAPSHOT__', SNAPSHOT)

SETTLEMENT = r"""
  IF p_op='settle_failure' THEN
   IF w.phase NOT IN ('SOURCE_INTENT','CLAIMED','CHECKPOINTED') OR w.task<>'DISCOVERY'
    OR w.subject->>'kind'<>'DISCOVERY_SCOPE' OR g->>'intake_period' IS NULL
    OR p_payload->>'reason' NOT IN ('RATE_LIMIT','SOURCE_UNAVAILABLE','UNSUPPORTED_CONTRACT','NO_SUPPORTED_FACTS')
    OR p_payload->'resolved_receipt'->>'cleanup'<>'CLOSED'
    OR p_payload->'resolved_receipt'->'accounting_complete' IS DISTINCT FROM 'true'::jsonb
    OR p_payload->'resolved_receipt'->>'failure' IS DISTINCT FROM p_payload->>'reason'
    OR p_payload->'resolved_receipt'->'durable_archive'->'readback_verified' IS DISTINCT FROM 'true'::jsonb
    OR p_payload->'resolved_receipt'->>'source_sha256' IS DISTINCT FROM p_payload->'resolved_receipt'->'durable_archive'->>'sha256'
    OR p_payload->'outcome'->>'outcome' IS DISTINCT FROM p_payload->>'reason'
    OR (CASE WHEN p_payload->>'reason' IN ('RATE_LIMIT','SOURCE_UNAVAILABLE') THEN
      p_payload->>'state'<>'DEFERRED' OR p_payload->'delay'<>'3600'::jsonb OR p_payload->'council_defer_seconds'<>'3600'::jsonb
     ELSE p_payload->>'state'<>'UNSUPPORTED_CONTRACT' OR p_payload->'delay'<>'0'::jsonb OR p_payload->'council_defer_seconds'<>'0'::jsonb END)
   THEN RAISE EXCEPTION 'INTAKE_FAILURE_SETTLEMENT'; END IF;
   UPDATE public.ingestion_work_items SET state=p_payload->>'state',reason=p_payload->>'reason',outcome=(p_payload->'outcome')::json,
    checkpoint=(p_payload->'resolved_receipt')::json,eligible_at=t+(p_payload->>'delay')::integer,
    owner=NULL,lease_until=NULL,phase='FINISHED',next_action='FRESH_RUN_OR_REVIEW_NO_SOURCE_REPLAY' WHERE key=p_key RETURNING * INTO w;
   UPDATE public.ingestion_work_attempts SET checkpoint=w.checkpoint,outcome=w.outcome,phase='FINISHED',finished_at=t WHERE work_key=p_key AND fence=p_fence;
   IF (p_payload->>'council_defer_seconds')::int>0 THEN
    ctl:=jsonb_set(ctl,'{council_deferred_until}',coalesce(ctl->'council_deferred_until','{}'::jsonb)||jsonb_build_object(w.subject->>'council',t+3600));
    UPDATE public.ingestion_work_items SET outcome=ctl::json WHERE key=repeat('0',64);
   END IF;
  ELSIF p_op IN ('batch_row','batch_reseal') THEN
"""


def worker_text():
    text=v3.capture_bound_text()
    # Trusted effect operations: login, grant and phase checks must all agree.
    text=text.replace("'batch_row','batch_reseal')", "'batch_row','batch_reseal','settle_failure')")
    text=text.replace("'batch_row','batch_reseal') OR p_key", "'batch_row','batch_reseal','settle_failure') OR p_key")
    anchor="  IF p_op IN ('batch_row','batch_reseal','settle_failure') THEN\n   plan:="
    if text.count(anchor)!=1:raise ValueError('INTAKE_SETTLEMENT_ANCHOR')
    text=text.replace(anchor,SETTLEMENT+"   plan:=")
    return text


def policy_sql():
    text=v3.original_text()
    start=text.index('CREATE FUNCTION public.ingestion_register_bolton_exception(')
    end=text.index('$register$;',start)+len('$register$;')
    register=text[start:end].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1)
    register=register.replace("BEGIN\n IF NOT pg_has_role", "BEGIN\n"+REGISTRATION+"\n IF NOT pg_has_role",1)
    start=text.index('CREATE FUNCTION public.ingestion_bolton_allowed(')
    end=text.index('$policy$;',start)+len('$policy$;')
    allowed=text[start:end].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1)
    rolling="""coalesce(ctl->'grants'->authority->>'intake_period' IS NOT NULL
 AND ctl->'intake_periods'->(ctl->'grants'->authority->>'intake_period')->'expected_stop'=__SNAPSHOT__
 AND (ctl->'intake_periods'->(ctl->'grants'->authority->>'intake_period')->>'expires_at')::double precision>extract(epoch FROM statement_timestamp())
 AND ctl->'intake_periods'->(ctl->'grants'->authority->>'intake_period')->'councils' ? (subject->>'council')
 AND (ctl->'grants'->authority->>'expires_at')::double precision>extract(epoch FROM statement_timestamp()),false) OR """.replace('__SNAPSHOT__',SNAPSHOT)
    allowed=allowed.replace(' SELECT coalesce(', ' SELECT '+rolling+'coalesce(',1)
    return allowed+'\n'+register+'\nGRANT EXECUTE ON FUNCTION public.ingestion_register_bolton_exception(jsonb) TO ingestion_worker;\n'


def installation_script():
    return v3.CEREMONY_OPEN+policy_sql()+v3.original_function(worker_text())+'\n'+v3.CEREMONY_CLOSE
