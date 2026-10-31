-- INACTIVE: guarded single-transaction replacement of exactly three daily-intake functions over the recognised Oldham-worker predecessor. Generated from the EXISTING PR #206 generator.
BEGIN;
SET LOCAL statement_timeout='10s';
SET LOCAL lock_timeout='3s';
SET LOCAL idle_in_transaction_session_timeout='10s';
SET LOCAL search_path=pg_catalog;
DO $preflight$
DECLARE me oid; storage_owner oid; worker_cap oid; ctl jsonb; snap jsonb; n integer; names constant text[]:=ARRAY['ingestion_acceptance_control','ingestion_bolton_allowed','ingestion_oldham_allowed','ingestion_raise_stop','ingestion_recover_abandoned','ingestion_register_bolton_exception','ingestion_worker_step'];
 pred constant jsonb:=jsonb_build_object('ingestion_bolton_allowed','961c1e1c441372a6c4fb4606d0f5b973a14dbb7e1fa390740789a4d4de2fe8bf','ingestion_register_bolton_exception','b5ce45dcaa4183b2f828dfb6383a0dde838d0b5365206ba406f8854f7bc0b3cd','ingestion_worker_step','79324a92b380de621e595470318f725cf64dbc1ac9c332591363cb70161ca912'); cand constant jsonb:=jsonb_build_object('ingestion_bolton_allowed','09d3e0e8e87bbf158bb89cb683063a21e5e8c23076d342961d49b50ac7e60569','ingestion_register_bolton_exception','dba6b809c50b9bd937b2f509fc05c20de9d69499ca4394e9007ef3af196b481c','ingestion_worker_step','abb46082f6d0891e131271a2567d45d8afdeccfd4561a6692baece7c3759c5bf'); unch constant jsonb:=jsonb_build_object('ingestion_acceptance_control','f25822db425df0c125df975d1cb46cfc710b76999744304d45d7037292d77d17','ingestion_raise_stop','5e41868876be6c533a31a8f7af25442ce308cb42681210296d516f361521e53a','ingestion_recover_abandoned','9e7f98210c737d6f8f7fae2d98e328261ab9faf31481f041b6f63befa6686f58','ingestion_oldham_allowed','091ec5ee578083b0b64431542ec02ff8a39263d345dee6a360dde68d3622900a'); argh constant jsonb:=jsonb_build_object('ingestion_bolton_allowed','ba1a6d72fc2b3badaa07f6f30f21ca4ceb24d657fa76e2d3cd5852511a49624f','ingestion_register_bolton_exception','ae7c50f98c8176db1f8d86e47a4e03f357e564cfb0d2f9719310105cb35a8b75','ingestion_worker_step','89e187297ff20c60b356f8324d375a82ac988e691fd20dde56b6059875762ed7','ingestion_oldham_allowed','d7a6bbabaa4cae893f3a049ac63cc43330426c07ffeebc312515cc29cc10f8af','ingestion_raise_stop','b5963c90e9f0d266eef3486a4d549047ed8a808a32269541d7602a2887b370a5','ingestion_recover_abandoned','84a70cc3c7b752e69569fbb83b0825c1be76384f24ca262b94dd784b8930393e','ingestion_acceptance_control','e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'); attr constant jsonb:=jsonb_build_object('ingestion_bolton_allowed',jsonb_build_array('sql','s',false),'ingestion_register_bolton_exception',jsonb_build_array('plpgsql','v',true),'ingestion_worker_step',jsonb_build_array('plpgsql','v',true),'ingestion_oldham_allowed',jsonb_build_array('sql','s',true),'ingestion_raise_stop',jsonb_build_array('plpgsql','v',true),'ingestion_recover_abandoned',jsonb_build_array('plpgsql','v',true),'ingestion_acceptance_control',jsonb_build_array('sql','v',true)); k text;
BEGIN
 IF current_user<>'postgres' OR session_user<>'postgres' OR current_database()<>'postgres' OR current_setting('transaction_read_only')<>'off' THEN RAISE EXCEPTION 'INSTALL_IDENTITY_OR_MODE'; END IF;
 me:=to_regrole('postgres');storage_owner:=to_regrole('ingestion_storage_owner');worker_cap:=to_regrole('ingestion_worker');
 IF storage_owner IS NULL OR worker_cap IS NULL THEN RAISE EXCEPTION 'INSTALL_ROLES_MISSING'; END IF;
 IF pg_has_role(me,'pg_read_all_stats','USAGE') IS DISTINCT FROM true OR row_security_active('public.ingestion_work_items'::regclass) OR row_security_active('public.ingestion_work_attempts'::regclass)
 OR EXISTS(SELECT 1 FROM pg_stat_activity WHERE usename IN ('ingestion_worker_login','ingestion_effect_login','ingestion_application_login','ingestion_recovery_login'))
 THEN RAISE EXCEPTION 'INSTALL_SESSION_VISIBILITY_OR_ACTIVITY'; END IF;
 -- Exact recognised predecessor: one function per name, reviewed owner/search_path/security/volatility/language/arguments, no PUBLIC ACL.
 snap:=(SELECT coalesce(jsonb_object_agg(p.proname,jsonb_build_object('sha',encode(sha256(convert_to(p.prosrc,'UTF8')),'hex'),'owner',pg_get_userbyid(p.proowner),'config',to_jsonb(p.proconfig),
 'secdef',p.prosecdef,'vol',p.provolatile::text,'lang',(SELECT lanname::text FROM pg_language WHERE oid=p.prolang),'ret',p.prorettype::regtype::text,
 'args',encode(sha256(convert_to(pg_get_function_identity_arguments(p.oid),'UTF8')),'hex'),'acl_present',p.proacl IS NOT NULL,
 'acl',coalesce((SELECT jsonb_agg(jsonb_build_array(CASE WHEN x.grantor=0 THEN 'PUBLIC' ELSE pg_get_userbyid(x.grantor) END,CASE WHEN x.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(x.grantee) END,x.privilege_type,x.is_grantable)
   ORDER BY x.grantor,x.grantee,x.privilege_type) FROM aclexplode(p.proacl) x),'[]'::jsonb))),'{}'::jsonb)
 FROM pg_proc p WHERE p.pronamespace='public'::regnamespace AND p.proname=ANY(ARRAY['ingestion_acceptance_control','ingestion_bolton_allowed','ingestion_oldham_allowed','ingestion_raise_stop','ingestion_recover_abandoned','ingestion_register_bolton_exception','ingestion_worker_step']));
 IF (SELECT count(*) FROM pg_proc WHERE pronamespace='public'::regnamespace AND proname=ANY(names))<>7 OR (SELECT count(*) FROM jsonb_object_keys(snap))<>7 THEN RAISE EXCEPTION 'INSTALL_FUNCTION_INVENTORY'; END IF;
 FOREACH k IN ARRAY names LOOP
  IF snap->k->>'owner' IS DISTINCT FROM 'ingestion_storage_owner' OR snap->k->'config' IS DISTINCT FROM '["search_path=pg_catalog"]'::jsonb
  OR jsonb_build_array(snap->k->'lang',snap->k->'vol',snap->k->'secdef') IS DISTINCT FROM (SELECT jsonb_build_array(to_jsonb(v->>0),to_jsonb(v->>1),v->2) FROM (SELECT attr->k v) q)
  OR snap->k->>'args' IS DISTINCT FROM argh->>k OR (snap->k->'acl_present') IS DISTINCT FROM 'true'::jsonb
  OR EXISTS(SELECT 1 FROM jsonb_array_elements(snap->k->'acl') e WHERE e->>0='PUBLIC' OR e->>1='PUBLIC')
  THEN RAISE EXCEPTION 'INSTALL_PREDECESSOR_ATTRIBUTES'; END IF;
  IF pred ? k THEN IF snap->k->>'sha' IS DISTINCT FROM pred->>k THEN RAISE EXCEPTION 'INSTALL_PREDECESSOR_BODY'; END IF;
  ELSE IF snap->k->>'sha' IS DISTINCT FROM unch->>k THEN RAISE EXCEPTION 'INSTALL_UNCHANGED_FUNCTION_CHANGED'; END IF; END IF;
 END LOOP;
 -- The three replaced functions: current EXECUTE state exactly as observed (no worker EXECUTE on the exception registrar; worker/effect on the worker step; nothing on the allowance policy).
 IF has_function_privilege('ingestion_worker_login',to_regprocedure('public.ingestion_register_bolton_exception(jsonb)'),'EXECUTE') IS DISTINCT FROM false
 OR has_function_privilege('ingestion_effect_login',to_regprocedure('public.ingestion_register_bolton_exception(jsonb)'),'EXECUTE') IS DISTINCT FROM false
 OR has_function_privilege('ingestion_worker_login',to_regprocedure('public.ingestion_bolton_allowed(jsonb,text,jsonb)'),'EXECUTE') IS DISTINCT FROM false
 OR has_function_privilege('ingestion_effect_login',to_regprocedure('public.ingestion_bolton_allowed(jsonb,text,jsonb)'),'EXECUTE') IS DISTINCT FROM false
 OR has_function_privilege('ingestion_worker_login',to_regprocedure('public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)'),'EXECUTE') IS DISTINCT FROM true
 OR has_function_privilege('ingestion_effect_login',to_regprocedure('public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)'),'EXECUTE') IS DISTINCT FROM true
 OR has_function_privilege(worker_cap,to_regprocedure('public.ingestion_register_bolton_exception(jsonb)'),'EXECUTE') IS DISTINCT FROM false
 THEN RAISE EXCEPTION 'INSTALL_PRIOR_FUNCTION_PRIVILEGE'; END IF;
 -- Stop, recovered items and ledger as left by the committed recovery (generation 5; NOT the historical generation-3 binding).
 SELECT outcome::jsonb INTO STRICT ctl FROM public.ingestion_work_items WHERE key=repeat('0',64);
 IF ctl->'global_stop' IS DISTINCT FROM '{"reason":"CONSUMED_SALFORD_GLOBAL_STOP","run":"38884069913"}'::jsonb OR ctl->>'manual_stop' IS DISTINCT FROM 'ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP' OR ctl->>'last_hard_stop' IS DISTINCT FROM 'ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP'
 OR ctl->'hard_stop_generation' IS DISTINCT FROM '5'::jsonb THEN RAISE EXCEPTION 'INSTALL_STOP_BINDING'; END IF;
 IF (SELECT count(*) FROM public.ingestion_work_items WHERE key IN ('3f0dba235de9b9efcd52ef3b281ba8c967491f57824404c695ed2b32fae4c045','e92a8e220bbbbcefb2425d6f97a60920bc447bc1fe097d600ea28e3e9d87588e')
    AND state='SAFETY_BLOCKED' AND phase='RECOVERED' AND fence=2 AND owner IS NULL AND lease_until IS NULL AND reason='ABANDONED_SOURCE_INTENT' AND next_action='RECONCILE')<>2
 THEN RAISE EXCEPTION 'INSTALL_RECOVERED_ITEMS'; END IF;
 -- Owner-role baseline: exactly the ADMIN-only distinct-grantor membership; no SET/USAGE; no schema CREATE for the owner; the identity must hold the schema CREATE grant option.
 IF pg_has_role(me,storage_owner,'SET') IS DISTINCT FROM false OR pg_has_role(me,storage_owner,'USAGE') IS DISTINCT FROM false
 OR (SELECT count(*) FROM pg_auth_members WHERE roleid=storage_owner AND member=me)<>1
 OR NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE roleid=storage_owner AND member=me AND admin_option AND NOT inherit_option AND NOT set_option AND grantor<>me)
 THEN RAISE EXCEPTION 'INSTALL_OWNER_ADMIN_BASELINE'; END IF;
 IF has_schema_privilege(storage_owner,'public','CREATE') IS DISTINCT FROM false OR has_schema_privilege(me,'public','CREATE WITH GRANT OPTION') IS DISTINCT FROM true
 THEN RAISE EXCEPTION 'INSTALL_SCHEMA_BASELINE'; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE oid=storage_owner AND NOT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolinherit AND NOT rolbypassrls)
 THEN RAISE EXCEPTION 'INSTALL_OWNER_ROLE_STATE'; END IF;
 PERFORM set_config('intake_install.functions',snap::text,true);
 PERFORM set_config('intake_install.owner_rows',(SELECT coalesce(jsonb_agg(to_jsonb(m) ORDER BY m.roleid,m.grantor),'[]'::jsonb) FROM pg_auth_members m WHERE m.member=me AND m.roleid=storage_owner)::text,true);
 PERFORM set_config('intake_install.schema_acl',(SELECT coalesce(jsonb_agg(jsonb_build_array(CASE WHEN x.grantor=0 THEN 'PUBLIC' ELSE pg_get_userbyid(x.grantor) END,CASE WHEN x.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(x.grantee) END,x.privilege_type,x.is_grantable)
 ORDER BY x.grantor,x.grantee,x.privilege_type),'[]'::jsonb) FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) x WHERE n.oid='public'::regnamespace)::text,true);
 PERFORM set_config('intake_install.ledger',encode(sha256(convert_to(jsonb_build_object('items',(SELECT coalesce(jsonb_agg(to_jsonb(w) ORDER BY w.key),'[]'::jsonb) FROM public.ingestion_work_items w),
 'attempts',(SELECT coalesce(jsonb_agg(to_jsonb(a) ORDER BY a.work_key,a.fence),'[]'::jsonb) FROM public.ingestion_work_attempts a))::text,'UTF8')),'hex'),true);
 PERFORM set_config('intake_install.control',ctl::text,true);
END $preflight$;
-- Temporary capabilities (both removed again before COMMIT): a SET-only self-granted owner row and the owner's schema CREATE (required for CREATE OR REPLACE FUNCTION in schema public).
GRANT ingestion_storage_owner TO postgres WITH ADMIN FALSE, INHERIT FALSE, SET TRUE GRANTED BY postgres;
GRANT CREATE ON SCHEMA public TO ingestion_storage_owner;
DO $capability$
DECLARE me oid:=to_regrole('postgres'); storage_owner oid:=to_regrole('ingestion_storage_owner');
BEGIN
 IF pg_has_role(me,storage_owner,'SET') IS DISTINCT FROM true OR pg_has_role(me,storage_owner,'USAGE') IS DISTINCT FROM false
 OR (SELECT count(*) FROM pg_auth_members WHERE roleid=storage_owner AND member=me)<>2
 OR NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE roleid=storage_owner AND member=me AND grantor=me AND NOT admin_option AND NOT inherit_option AND set_option)
 OR has_schema_privilege(storage_owner,'public','CREATE') IS DISTINCT FROM true
 THEN RAISE EXCEPTION 'INSTALL_TEMP_CAPABILITY'; END IF;
END $capability$;
SET LOCAL ROLE ingestion_storage_owner;
CREATE OR REPLACE FUNCTION public.ingestion_bolton_allowed(ctl jsonb, authority text, subject jsonb) RETURNS boolean
LANGUAGE sql STABLE SET search_path=pg_catalog AS $policy$
 SELECT coalesce(ctl->'grants'->authority->>'intake_period' IS NOT NULL
 AND ctl->'intake_periods'->(ctl->'grants'->authority->>'intake_period')->'expected_stop'=jsonb_build_object('global_stop',ctl->'global_stop','manual_stop',ctl->'manual_stop','last_hard_stop',ctl->'last_hard_stop','hard_stop_generation',coalesce(ctl->'hard_stop_generation','0'::jsonb))
 AND (ctl->'intake_periods'->(ctl->'grants'->authority->>'intake_period')->>'expires_at')::double precision>extract(epoch FROM statement_timestamp())
 AND ctl->'intake_periods'->(ctl->'grants'->authority->>'intake_period')->'councils' ? (subject->>'council')
 AND (ctl->'grants'->authority->>'expires_at')::double precision>extract(epoch FROM statement_timestamp()),false) OR coalesce(ctl->'global_stop'='{"reason":"CONSUMED_SALFORD_GLOBAL_STOP","run":"38884069913"}'::jsonb
 AND ((coalesce((ctl->>'hard_stop_generation')::integer,0)=coalesce((ctl->'bolton_exceptions'->authority->>'hard_stop_generation')::integer,0)
   AND (ctl->>'manual_stop' IS NULL OR ctl->>'manual_stop'='STORAGE_TEST_STOP'))
  OR (authority IN ('AUTHORISE_INGESTION_BOLTON_FORM_PROBE_ONCE_20261021_PROBE','AUTHORISE_INGESTION_BOLTON_CAPTURE_ACCEPTANCE_ONCE_20261022_CAPTURE','AUTHORISE_INGESTION_BOLTON_CAPTURE_ACCEPTANCE_ONCE_20261022_SCREEN')
   AND (ctl->>'hard_stop_generation')::integer=2 AND (ctl->'bolton_exceptions'->authority->>'hard_stop_generation')::integer=2
   AND ctl->>'manual_stop'='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE' AND ctl->>'last_hard_stop'='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE')
  OR (authority IN ('AUTHORISE_INGESTION_BOLTON_WINDOW_DEMONSTRATION_ONCE_20261023_CAPTURE','AUTHORISE_INGESTION_BOLTON_WINDOW_DEMONSTRATION_ONCE_20261023_SCREEN')
   AND (ctl->>'hard_stop_generation')::integer=3 AND (ctl->'bolton_exceptions'->authority->>'hard_stop_generation')::integer=3
   AND ctl->>'manual_stop'='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE' AND ctl->>'last_hard_stop'='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE')
  OR (authority = 'AUTHORISE_INGESTION_BOLTON_SCREENING_V3_RETAINED_WINDOW_ONCE_20261030_SCREEN'
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

 IF p->>'operation' IN ('intake_period','intake_capture','intake_screen','intake_close','intake_finish') THEN
  IF p IS NULL OR jsonb_typeof(p)<>'object' OR octet_length(p::text)>131072 THEN RAISE EXCEPTION 'INTAKE_ARGUMENT_BOUND'; END IF;
  SELECT outcome::jsonb INTO STRICT ctl FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE;
  t:=extract(epoch FROM clock_timestamp());
  a:=p->>'period';
  IF a IS NULL OR a !~ '^[A-Za-z0-9_-]{1,60}$' THEN RAISE EXCEPTION 'INTAKE_PERIOD_ID'; END IF;
  IF p->>'operation'='intake_period' THEN
   IF NOT pg_has_role(session_user,'ingestion_barrier_releaser','USAGE') THEN RAISE EXCEPTION 'OWNER_DISPOSITION_REQUIRED' USING ERRCODE='42501'; END IF;
   e:=p->'policy';
   IF jsonb_typeof(e) IS DISTINCT FROM 'object' OR NOT (e ?& ARRAY['expires_at','max_runs','overlap_days','councils','expected_stop','execution_binding','test_evidence','screening_config','hostaddr','route']) OR NOT (e->'execution_binding' ?& ARRAY['revision','workflow_sha256','manifest_sha256']) OR ctl->'intake_periods' ? a
    OR jsonb_typeof(e->'expires_at') IS DISTINCT FROM 'number'
    OR (e->>'expires_at')::double precision<=t OR (e->>'expires_at')::double precision>t+604800
    OR jsonb_typeof(e->'max_runs') IS DISTINCT FROM 'number' OR (e->>'max_runs')::numeric NOT BETWEEN 1 AND 7 OR (e->>'max_runs')::numeric<>trunc((e->>'max_runs')::numeric) OR e->'overlap_days' IS DISTINCT FROM '7'::jsonb
    OR jsonb_typeof(e->'councils') IS DISTINCT FROM 'object' OR (SELECT count(*) FROM jsonb_each(e->'councils')) NOT BETWEEN 1 AND 2
    OR (e->'councils')-ARRAY['tameside','manchester']<>'{}'::jsonb
    OR e->'expected_stop' IS DISTINCT FROM jsonb_build_object('global_stop',ctl->'global_stop','manual_stop',ctl->'manual_stop','last_hard_stop',ctl->'last_hard_stop','hard_stop_generation',coalesce(ctl->'hard_stop_generation','0'::jsonb))
    OR ctl->'global_stop' IS DISTINCT FROM 'null'::jsonb OR ctl->>'manual_stop' IS NOT NULL
    OR (ctl ? 'intake_run' AND ctl->'intake_run'->>'state' IS DISTINCT FROM 'VERIFIED')
    OR EXISTS(SELECT 1 FROM public.ingestion_work_items x WHERE x.phase IN ('SOURCE_INTENT','WRITE_INTENT') OR x.state='PERSISTENCE_UNCERTAIN')
    OR jsonb_typeof(e->'screening_config') IS DISTINCT FROM 'string'
    OR jsonb_typeof(e->'execution_binding'->'revision') IS DISTINCT FROM 'string'
    OR jsonb_typeof(e->'execution_binding'->'workflow_sha256') IS DISTINCT FROM 'string'
    OR jsonb_typeof(e->'execution_binding'->'manifest_sha256') IS DISTINCT FROM 'string'
    OR e->'execution_binding'->>'revision' !~ '^[a-f0-9]{40}$'
    OR e->'execution_binding'->>'workflow_sha256' !~ '^[a-f0-9]{64}$'
    OR e->'execution_binding'->>'manifest_sha256' !~ '^[a-f0-9]{64}$'
    OR jsonb_typeof(e->'test_evidence') IS DISTINCT FROM 'boolean'
    OR (CASE WHEN e->'test_evidence'='true'::jsonb THEN e->>'route' IS DISTINCT FROM 'DISPOSABLE' ELSE coalesce(e->>'route','') NOT IN ('POOLER','DIRECT') END)
    OR (CASE WHEN e->'test_evidence'='true'::jsonb THEN e->'hostaddr' IS DISTINCT FROM 'null'::jsonb ELSE jsonb_typeof(e->'hostaddr') IS DISTINCT FROM 'string' OR family((e->>'hostaddr')::inet)<>4 OR masklen((e->>'hostaddr')::inet)<>32 END)
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
   OR (p->>'operation'<>'intake_close' AND ((e->>'expires_at')::double precision<=t OR e->'expected_stop' IS DISTINCT FROM jsonb_build_object('global_stop',ctl->'global_stop','manual_stop',ctl->'manual_stop','last_hard_stop',ctl->'last_hard_stop','hard_stop_generation',coalesce(ctl->'hard_stop_generation','0'::jsonb)))) THEN RAISE EXCEPTION 'INTAKE_PERIOD_EXPIRED_OR_STOP_CHANGED'; END IF;
  IF p->>'operation'='intake_close' THEN
   IF jsonb_typeof(p->'authorities') IS DISTINCT FROM 'array' OR jsonb_array_length(p->'authorities')>4 THEN RAISE EXCEPTION 'INTAKE_CLOSE_BOUND'; END IF;
   FOR item IN SELECT value FROM jsonb_array_elements(p->'authorities') LOOP
    IF ctl->'grants'->(item#>>'{}')->>'intake_period' IS DISTINCT FROM a THEN RAISE EXCEPTION 'INTAKE_CLOSE_IDENTITY'; END IF;
    ctl:=jsonb_set(ctl,ARRAY['grants',item#>>'{}','expires_at'],'0'::jsonb);
   END LOOP;
   UPDATE public.ingestion_work_items SET outcome=ctl::json WHERE key=repeat('0',64);
   RETURN jsonb_build_object('authorities_invalidated',true,'stop_preserved',true);
  END IF;
  -- Single bounded unresolved-run marker in the EXISTING control record. No
  -- expiry-based unlock, automatic retry, or worker reconciliation operation.
  IF p->>'operation'='intake_finish' THEN
   IF ctl->'intake_run'->>'state' IS DISTINCT FROM 'OPEN'
    OR ctl->'intake_run'->>'id' IS DISTINCT FROM p->>'run_id'
    OR ctl->'intake_run'->>'period' IS DISTINCT FROM a
    OR coalesce(p->>'status','') NOT IN ('RETAINED_AND_SCREENED','INCOMPLETE')
    OR p->'publication'->>'readback_verified' IS DISTINCT FROM 'true'
    OR coalesce(p->'publication'->>'commit','') !~ '^[a-f0-9]{40}$'
    OR coalesce(p->'publication'->>'sha256','') !~ '^[a-f0-9]{64}$'
    OR p->'publication'->>'path' IS DISTINCT FROM ctl->'intake_run'->>'publication_path'
    OR EXISTS(SELECT 1 FROM jsonb_each(ctl->'grants') x WHERE x.value->>'intake_run'=p->>'run_id' AND x.value->'expires_at' IS DISTINCT FROM '0'::jsonb)
    OR (SELECT count(*) FROM jsonb_each(e->'days'->(ctl->'intake_run'->>'day')))<>(SELECT count(*) FROM jsonb_each(e->'councils'))
    OR EXISTS(SELECT 1 FROM jsonb_each(e->'days'->(ctl->'intake_run'->>'day')) x
      LEFT JOIN public.ingestion_work_items w ON w.key=x.value#>>'{}'
      WHERE w.state IS NULL OR w.state NOT IN ('COMPLETE','DEFERRED')
       OR (w.state='DEFERRED' AND p->>'status'<>'INCOMPLETE')
       OR (w.state='COMPLETE' AND (
        (SELECT count(*) FROM public.ingestion_work_items s WHERE s.task='SCREENING' AND s.dependencies::jsonb=jsonb_build_array(w.key) AND s.state='COMPLETE')<>jsonb_array_length(w.checkpoint::jsonb->'records')
        OR (SELECT count(*) FROM public.ingestion_work_items b WHERE b.task='LISTING_METADATA' AND b.checkpoint::jsonb->'plan'->>'capture_key'=w.key AND b.state='COMPLETE')<>(jsonb_array_length(w.checkpoint::jsonb->'records')+4)/5)))
   THEN RAISE EXCEPTION 'INTAKE_FINALISATION_UNVERIFIED'; END IF;
   g:=ctl->'intake_run'||jsonb_build_object('state','VERIFIED','status',p->>'status','publication',p->'publication','verified_at',t);
   ctl:=jsonb_set(ctl,'{intake_run}',g);
   UPDATE public.ingestion_work_items SET outcome=ctl::json WHERE key=repeat('0',64);
   RETURN g;
  END IF;
  IF ctl ? 'intake_run' AND ctl->'intake_run'->>'state' IS DISTINCT FROM 'VERIFIED'
   AND (ctl->'intake_run'->>'id' IS DISTINCT FROM p->>'run_id' OR ctl->'intake_run'->>'period' IS DISTINCT FROM a)
   THEN RAISE EXCEPTION 'INTAKE_UNFINISHED_RUN_RECONCILE'; END IF;
  IF p->>'operation'='intake_capture' AND ctl->'grants' ? (p->>'authority') THEN
   SELECT * INTO STRICT root FROM public.ingestion_work_items WHERE key=p->'grant'->>'capture_key';
   IF ctl->'grants'->(p->>'authority')->>'intake_period' IS DISTINCT FROM a
    OR root.subject::jsonb IS DISTINCT FROM p->'rows'->0->'subject'
    OR e->'days'->(root.subject->>'end')->>(root.subject->>'council') IS DISTINCT FROM root.key
    OR root.state NOT IN ('COMPLETE','DEFERRED','UNSUPPORTED_CONTRACT')
   THEN RAISE EXCEPTION 'INTAKE_CONSUMED_RECONCILE_NO_REPLAY'; END IF;
   IF ctl->'intake_run'->>'state' IS DISTINCT FROM 'VERIFIED' OR ctl->'intake_run'->>'period' IS DISTINCT FROM a OR ctl->'intake_run'->>'day' IS DISTINCT FROM root.subject->>'end' THEN RAISE EXCEPTION 'INTAKE_UNFINISHED_RUN_RECONCILE'; END IF;
   RETURN jsonb_build_object('already_consumed',true,'capture_key',root.key,'state',root.state);
  END IF;
  IF EXISTS(SELECT 1 FROM public.ingestion_work_items x WHERE x.phase IN ('SOURCE_INTENT','WRITE_INTENT') OR x.state='PERSISTENCE_UNCERTAIN') THEN RAISE EXCEPTION 'INTAKE_UNRESOLVED_EFFECT_BARRIER'; END IF;
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
    OR (SELECT count(*) FROM jsonb_each(coalesce(e->'days','{}'::jsonb))) >= (e->>'max_runs')::int AND NOT (e->'days' ? (item->'subject'->>'end'))
    OR e->'days'->(item->'subject'->>'end') ? (item->'subject'->>'council')
   THEN RAISE EXCEPTION 'INTAKE_ROLLING_SCOPE_OR_CONSUMED'; END IF;
   e:=jsonb_set(e,ARRAY['days',item->'subject'->>'end'],coalesce(e->'days'->(item->'subject'->>'end'),'{}'::jsonb)||jsonb_build_object(item->'subject'->>'council',item->>'key'));
   -- jsonb_set cannot create a missing intermediate path; days exists from issuance.
   ctl:=jsonb_set(ctl,ARRAY['intake_periods',a],e);
  ELSE
   SELECT * INTO STRICT root FROM public.ingestion_work_items WHERE key=g->>'capture_key' FOR SHARE;
   IF root.state<>'COMPLETE' OR root.task<>'DISCOVERY' OR root.checkpoint::jsonb->>'kind'<>'LISTING_RECEIPT_V1'
    OR NOT (e->'councils' ? (root.subject->>'council'))
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
  IF coalesce(p->>'run_id','') !~ '^[a-f0-9]{32}$'
   OR p->>'publication_path' IS DISTINCT FROM ('docs/design/ingestion-operational-execution-daily-intake/'||a||'/'||(p->>'run_id')||'/final/result-before-publication.json')
   THEN RAISE EXCEPTION 'INTAKE_RUN_IDENTITY'; END IF;
  IF NOT (ctl ? 'intake_run') OR ctl->'intake_run'->>'state'='VERIFIED' THEN
   IF p->>'operation'<>'intake_capture' THEN RAISE EXCEPTION 'INTAKE_RUN_CAPTURE_FIRST'; END IF;
   ctl:=jsonb_set(ctl,'{intake_run}',jsonb_build_object('id',p->>'run_id','period',a,
     'day',p->'rows'->0->'subject'->>'end','state','OPEN','started_at',t,
     'publication_path',p->>'publication_path'));
  ELSIF ctl->'intake_run'->>'publication_path' IS DISTINCT FROM p->>'publication_path' THEN RAISE EXCEPTION 'INTAKE_RUN_IDENTITY';
  END IF;
  g:=g||jsonb_build_object('intake_period',a,'intake_run',p->>'run_id');
  ctl:=jsonb_set(ctl,'{grants}',coalesce(ctl->'grants','{}'::jsonb)||jsonb_build_object(p->>'authority',g));
  UPDATE public.ingestion_work_items SET outcome=ctl::json WHERE key=repeat('0',64);
  RETURN g;
 END IF;

 IF NOT pg_has_role(session_user,'ingestion_barrier_releaser','USAGE') THEN RAISE EXCEPTION 'OWNER_DISPOSITION_REQUIRED' USING ERRCODE='42501'; END IF;
 IF p IS NULL OR octet_length(p::text)>131072 OR jsonb_typeof(p)<>'object' OR NOT (p ?& ARRAY['authority','transport','grant_binding','stop_checkpoint_sha256','revision','workflow_sha256','manifest_sha256']) THEN RAISE EXCEPTION 'EXCEPTION_BOUND'; END IF;
 SELECT outcome::jsonb INTO STRICT ctl FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE;
 a:=p->>'authority';g:=ctl->'grants'->a;t:=extract(epoch FROM clock_timestamp());
 sc:=CASE WHEN a IN ('AUTHORISE_INGESTION_BOLTON_WINDOW_DEMONSTRATION_ONCE_20261023_CAPTURE','AUTHORISE_INGESTION_BOLTON_WINDOW_DEMONSTRATION_ONCE_20261023_SCREEN','AUTHORISE_INGESTION_BOLTON_SCREENING_V3_RETAINED_WINDOW_ONCE_20261030_SCREEN') THEN '{"kind":"DISCOVERY_SCOPE","council":"bolton","start":"2026-09-28","end":"2026-10-04","semantics":"RECEIVED"}'::jsonb ELSE '{"kind":"DISCOVERY_SCOPE","council":"bolton","start":"2026-10-16","end":"2026-10-16","semantics":"RECEIVED"}'::jsonb END;      -- the exact scope this allowance may concern
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
   AND p->>'stop_checkpoint_sha256'='ff2876015380e16d3ce794b289d207e15e0e39f62fb44cf104c1608edcb39f7b',false)
  OR coalesce(a = 'AUTHORISE_INGESTION_BOLTON_SCREENING_V3_RETAINED_WINDOW_ONCE_20261030_SCREEN' AND (ctl->>'hard_stop_generation')::integer=3 AND (p->>'hard_stop_generation')::integer=3
   AND ctl->>'manual_stop'='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE' AND ctl->>'last_hard_stop'='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE'
   AND p->>'stop_checkpoint_sha256'='ff2876015380e16d3ce794b289d207e15e0e39f62fb44cf104c1608edcb39f7b',false))      -- NULL (an absent stop field) is FALSE here, never a widening
 OR p->>'transport'<>'REQUESTS_IDOX' OR g IS NULL OR p->'grant_binding' IS DISTINCT FROM g-ARRAY['source_calls','writes']
 OR (g->>'expires_at')::double precision<=t OR (g->>'expires_at')::double precision>t+86400
 OR ctl->'bolton_exceptions' ? a OR ((SELECT count(*) FROM jsonb_object_keys(coalesce(ctl->'bolton_exceptions','{}'::jsonb)))>=3 AND NOT coalesce((a IN ('AUTHORISE_INGESTION_BOLTON_CAPTURE_ACCEPTANCE_ONCE_20261022_CAPTURE','AUTHORISE_INGESTION_BOLTON_CAPTURE_ACCEPTANCE_ONCE_20261022_SCREEN') AND (ctl->>'hard_stop_generation')::integer=2) OR (a IN ('AUTHORISE_INGESTION_BOLTON_WINDOW_DEMONSTRATION_ONCE_20261023_CAPTURE','AUTHORISE_INGESTION_BOLTON_WINDOW_DEMONSTRATION_ONCE_20261023_SCREEN') AND (ctl->>'hard_stop_generation')::integer=3) OR (a = 'AUTHORISE_INGESTION_BOLTON_SCREENING_V3_RETAINED_WINDOW_ONCE_20261030_SCREEN' AND (ctl->>'hard_stop_generation')::integer=3),false))
 OR p->>'revision' !~ '^[a-f0-9]{40}$' OR p->>'workflow_sha256' !~ '^[a-f0-9]{64}$' OR p->>'manifest_sha256' !~ '^[a-f0-9]{64}$'
 THEN RAISE EXCEPTION 'EXACT_SCOPED_DISPOSITION'; END IF;
 SELECT * INTO STRICT root FROM public.ingestion_work_items WHERE key=g->>'capture_key';
 IF root.task<>'DISCOVERY' OR root.subject::jsonb IS DISTINCT FROM sc
 OR g->'execution_binding' IS DISTINCT FROM jsonb_build_object('revision',p->>'revision','workflow_sha256',p->>'workflow_sha256','manifest_sha256',p->>'manifest_sha256') THEN RAISE EXCEPTION 'EXECUTION_AND_CAPTURE_BINDING'; END IF;
 IF a = 'AUTHORISE_INGESTION_BOLTON_SCREENING_V3_RETAINED_WINDOW_ONCE_20261030_SCREEN' AND (g->>'capture_key' IS DISTINCT FROM 'd1ff23c04af746a5219e7c109255db0310d2a006c732bcac4f66f126b0240545' OR root.state<>'COMPLETE' OR root.checkpoint::jsonb->>'kind' IS DISTINCT FROM 'LISTING_RECEIPT_V1'
  OR (g->>'source_calls')::integer IS DISTINCT FROM 0 OR (g->>'writes')::integer IS DISTINCT FROM 0
  OR jsonb_typeof(g->'screening_configs') IS DISTINCT FROM 'array' OR jsonb_array_length(g->'screening_configs')<>1 OR g->'screening_configs' IS DISTINCT FROM '["58e2a1a1dae30a21b8fa150a27d223793d4601e8d400a686c4f8e17d999e1b7e"]'::jsonb
  OR (SELECT count(*) FROM jsonb_each(g->'bindings'))<>59
  OR jsonb_array_length(g->'keys')<>59 OR g->'contracts' IS DISTINCT FROM '["bolton-received-idox-coordinator-v1","listing-batch-v1","listing-screen-v1","listing-screen-v3"]'::jsonb
  OR (SELECT count(*) FROM jsonb_each(g->'bindings') x WHERE x.value->>'task'='DISCOVERY')<>1
  OR (SELECT count(*) FROM jsonb_each(g->'bindings') x WHERE x.value->>'task'='LISTING_METADATA' AND x.value->>'contract'='listing-batch-v1')<>10
  OR (SELECT count(*) FROM jsonb_each(g->'bindings') x WHERE x.value->>'task'='SCREENING' AND x.value->>'contract'='listing-screen-v1')<>24
  OR (SELECT count(*) FROM jsonb_each(g->'bindings') x WHERE x.value->>'task'='SCREENING' AND x.value->>'contract'='listing-screen-v3')<>24) THEN RAISE EXCEPTION 'EXACT_SCREENING_V3_ALLOWANCE'; END IF;
 FOR item IN SELECT value FROM jsonb_each(g->'bindings') LOOP
  IF item->'subject'->>'council' IS DISTINCT FROM 'bolton' OR (item->>'task' IN ('DISCOVERY','LISTING_METADATA','SCREENING','FACTUAL_REFRESH')) IS DISTINCT FROM true THEN RAISE EXCEPTION 'BOLTON_ONLY'; END IF;
  IF item->'subject'->>'kind'='DISCOVERY_SCOPE' AND item->'subject' IS DISTINCT FROM sc THEN RAISE EXCEPTION 'EXACT_BOLTON_DAY'; END IF;
 END LOOP;
 e:=p||jsonb_build_object('expires_at',g->'expires_at');
 ctl:=jsonb_set(ctl,'{bolton_exceptions}',coalesce(ctl->'bolton_exceptions','{}'::jsonb)||jsonb_build_object(a,e));
 UPDATE public.ingestion_work_items SET outcome=ctl::json WHERE key=repeat('0',64);
 RETURN e;
END $register$;
GRANT EXECUTE ON FUNCTION public.ingestion_register_bolton_exception(jsonb) TO ingestion_worker;
CREATE OR REPLACE FUNCTION public.ingestion_worker_step(p_op text,p_key text,p_fence integer,p_owner text,p_authority text,p_binding jsonb,p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $fn$
DECLARE w public.ingestion_work_items%ROWTYPE; ctl jsonb; g jsonb; t double precision; dep text; answer jsonb; n bigint; child jsonb; rec jsonb; old_child jsonb; capture public.ingestion_work_items%ROWTYPE; plan jsonb; idx integer;
BEGIN
 IF p_op IN ('fence_effect','resolve_effect','enqueue_child','batch_row','batch_reseal','settle_failure') THEN
  IF NOT pg_has_role(session_user,'ingestion_effect_broker','USAGE') THEN RAISE EXCEPTION 'BROKER_REQUIRED' USING ERRCODE='42501'; END IF;
 ELSE
  IF session_user<>'ingestion_worker_login' OR NOT pg_has_role(session_user,'ingestion_worker','USAGE') THEN RAISE EXCEPTION 'WORKER_LOGIN_REQUIRED' USING ERRCODE='42501'; END IF;
 END IF;
 IF p_fence IS NULL OR jsonb_typeof(p_binding) IS DISTINCT FROM 'object' OR jsonb_typeof(p_payload) IS DISTINCT FROM 'object' OR p_op IS NULL OR p_op NOT IN ('claim','checkpoint','complete','begin_source','begin_write','fence_effect','resolve_effect','block','enqueue_child','batch_row','batch_reseal','settle_failure') OR p_key IS NULL OR p_key !~ '^[a-f0-9]{64}$' OR p_key=repeat('0',64)
 OR p_owner IS NULL OR p_owner !~ '^[A-Za-z0-9_-]{1,100}$' OR p_authority IS NULL OR length(p_authority)>100
 OR p_binding IS NULL OR p_payload IS NULL OR octet_length(p_binding::text)>8192 OR octet_length(p_payload::text)>131072
 THEN RAISE EXCEPTION 'BOUNDED_ARGUMENTS' USING ERRCODE='22023'; END IF;
 SELECT outcome::jsonb INTO STRICT ctl FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE;
 SELECT * INTO STRICT w FROM public.ingestion_work_items WHERE key=p_key FOR UPDATE;
 t:=extract(epoch FROM clock_timestamp());
 IF ctl->'global_stop' IS DISTINCT FROM 'null'::jsonb THEN
  IF NOT public.ingestion_bolton_allowed(ctl,p_authority,w.subject::jsonb) THEN RAISE EXCEPTION 'GLOBAL_STOP' USING ERRCODE='42501'; END IF;
 END IF;
 IF EXISTS(SELECT 1 FROM public.ingestion_work_items WHERE state='PERSISTENCE_UNCERTAIN') THEN RAISE EXCEPTION 'PERSISTENCE_UNCERTAIN_GLOBAL'; END IF;
 IF EXISTS(SELECT 1 FROM public.ingestion_work_items WHERE phase='WRITE_INTENT' AND (key<>p_key OR p_op NOT IN ('fence_effect','resolve_effect','enqueue_child','batch_row','batch_reseal','settle_failure'))) THEN RAISE EXCEPTION 'UNRESOLVED_WRITE_BARRIER' USING ERRCODE='42501'; END IF;
 IF (ctl->'council_deferred_until'->>(w.subject->>'council'))::double precision>t THEN RAISE EXCEPTION 'COUNCIL_DEFERRED' USING ERRCODE='42501'; END IF;
 g:=ctl->'grants'->p_authority;
 IF g IS NULL OR (g->'keys' ? p_key) IS DISTINCT FROM true OR (g->'contracts' ? w.contract) IS DISTINCT FROM true
 OR jsonb_typeof(g->'expires_at') IS DISTINCT FROM 'number' OR coalesce((g->>'expires_at')::double precision,0)<=t OR (g->>'expires_at')::double precision>t+86400
 OR (CASE WHEN p_op IN ('fence_effect','resolve_effect','enqueue_child','batch_row','batch_reseal','settle_failure') THEN g->>'effect_login' ELSE g->>'login' END) IS DISTINCT FROM session_user OR (g->'workers' ? p_owner) IS DISTINCT FROM true
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
  IF p_op NOT IN ('fence_effect','resolve_effect','enqueue_child','batch_row','batch_reseal','settle_failure') AND w.phase NOT IN ('CLAIMED','CHECKPOINTED') THEN RAISE EXCEPTION 'EFFECT_RESOLUTION_REQUIRES_TRUSTED_WRITER' USING ERRCODE='42501'; END IF;

  IF p_op='settle_failure' THEN
   IF w.phase NOT IN ('SOURCE_INTENT','CLAIMED','CHECKPOINTED') OR w.task<>'DISCOVERY'
    OR w.subject->>'kind'<>'DISCOVERY_SCOPE' OR g->>'intake_period' IS NULL
    OR coalesce(p_payload->>'reason','') NOT IN ('RATE_LIMIT','SOURCE_UNAVAILABLE')
    OR p_payload->'resolved_receipt'->>'cleanup' IS DISTINCT FROM 'CLOSED'
    OR p_payload->'resolved_receipt'->'accounting_complete' IS DISTINCT FROM 'true'::jsonb
    OR p_payload->'resolved_receipt'->>'failure' IS DISTINCT FROM p_payload->>'reason'
    OR p_payload->'resolved_receipt'->'durable_archive'->'readback_verified' IS DISTINCT FROM 'true'::jsonb
    OR jsonb_typeof(p_payload->'resolved_receipt'->'source_sha256') IS DISTINCT FROM 'string'
    OR p_payload->'resolved_receipt'->>'source_sha256' !~ '^[a-f0-9]{64}$'
    OR p_payload->'resolved_receipt'->>'source_sha256' IS DISTINCT FROM p_payload->'resolved_receipt'->'durable_archive'->>'sha256'
    OR p_payload->'outcome'->>'outcome' IS DISTINCT FROM p_payload->>'reason'
    OR p_payload->'resolved_receipt'->'source_audit'->'failure_diagnostic'->'transport'->'http_status'
       IS DISTINCT FROM (CASE WHEN p_payload->>'reason'='RATE_LIMIT' THEN '429'::jsonb ELSE '503'::jsonb END)
    OR p_payload->>'state' IS DISTINCT FROM 'DEFERRED'
    OR p_payload->'delay' IS DISTINCT FROM '3600'::jsonb
    OR p_payload->'council_defer_seconds' IS DISTINCT FROM '3600'::jsonb
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
   IF capture.state<>'COMPLETE' OR capture.task<>'DISCOVERY' OR capture.checkpoint::jsonb->>'kind'<>'LISTING_RECEIPT_V1'
   OR capture.subject::jsonb IS DISTINCT FROM w.subject::jsonb OR (w.dependencies::jsonb ? capture.key) IS DISTINCT FROM true
   OR (p_payload->>'capture_json')::jsonb IS DISTINCT FROM capture.checkpoint::jsonb
   OR encode(sha256(convert_to(p_payload->>'capture_json','UTF8')),'hex') IS DISTINCT FROM plan->>'capture_sha256'
   OR (plan->>'last')::integer>jsonb_array_length(capture.checkpoint::jsonb->'records') THEN RAISE EXCEPTION 'CAPTURE_BINDING'; END IF;
   IF plan ? 'capture_bound' AND (plan->'capture_bound' IS DISTINCT FROM 'true'::jsonb OR NOT (plan ? 'screening')) THEN RAISE EXCEPTION 'CAPTURE_BOUND_PLAN'; END IF;
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
   OR (((plan ? 'screening') IS DISTINCT FROM true AND child->>'contract'='listing-screen-v1') OR ((plan ? 'screening') IS TRUE AND jsonb_typeof(plan->'screening')='object' AND (plan->'screening')-ARRAY['contract','config_sha256']='{}'::jsonb AND plan->'screening'->>'contract'='listing-screen-v3' AND plan->'screening'->>'config_sha256' ~ '^[a-f0-9]{64}$' AND jsonb_typeof(g->'screening_configs')='array' AND g->'screening_configs' ? (plan->'screening'->>'config_sha256') AND child->>'contract'='listing-screen-v3' AND capture.checkpoint::jsonb->>'kind'='LISTING_RECEIPT_V1')) IS DISTINCT FROM true OR jsonb_typeof(p_payload->'record_json') IS DISTINCT FROM 'string'
   OR jsonb_typeof(p_payload->'identity_json') IS DISTINCT FROM 'string' THEN RAISE EXCEPTION 'BATCH_ROW_TYPES'; END IF;
   IF child->'subject' IS DISTINCT FROM jsonb_build_object('kind','APPLICATION','council',capture.subject->>'council','reference',rec->>'reference')
   OR child->'dependencies' IS DISTINCT FROM jsonb_build_array(capture.key) OR child->>'task'<>'SCREENING' OR child->>'contract' IS DISTINCT FROM (CASE WHEN (plan ? 'screening') IS TRUE THEN 'listing-screen-v3' ELSE 'listing-screen-v1' END)
   OR (child->>'max_attempts')::integer<>2 OR child->'limits' IS DISTINCT FROM w.limits::jsonb OR (child->>'priority')::integer<>w.priority
   OR (p_payload->>'record_json')::jsonb IS DISTINCT FROM rec OR (CASE WHEN (plan ? 'screening') IS TRUE THEN (CASE WHEN plan->'capture_bound'='true'::jsonb THEN encode(sha256(convert_to('{"assessment_revision":"'||encode(sha256(convert_to('{"config_sha256":"'||(plan->'screening'->>'config_sha256')||'","record_sha256":"'||encode(sha256(convert_to(p_payload->>'record_json','UTF8')),'hex')||'"}','UTF8')),'hex')||'","observation_sha256":"'||(plan->>'capture_sha256')||'"}','UTF8')),'hex') ELSE encode(sha256(convert_to('{"config_sha256":"'||(plan->'screening'->>'config_sha256')||'","record_sha256":"'||encode(sha256(convert_to(p_payload->>'record_json','UTF8')),'hex')||'"}','UTF8')),'hex') END) ELSE encode(sha256(convert_to(p_payload->>'record_json','UTF8')),'hex') END) IS DISTINCT FROM child->>'revision'
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
  ELSIF p_op IN ('fence_effect','resolve_effect','enqueue_child','batch_row','batch_reseal','settle_failure') THEN
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
   IF (g->>'capture_only')::boolean IS TRUE AND w.task='DISCOVERY' AND (w.checkpoint::jsonb IS DISTINCT FROM p_payload OR w.checkpoint::jsonb->>'kind' IS DISTINCT FROM 'LISTING_RECEIPT_V1') THEN RAISE EXCEPTION 'BROKER_CAPTURE_REQUIRED'; END IF;
   IF w.contract='listing-batch-v1' THEN RAISE EXCEPTION 'BROKER_PROGRESS_REQUIRED'; END IF;
   IF w.checkpoint::jsonb->>'kind'='DETAIL_RECEIPT_V1' OR p_payload->>'kind'='DETAIL_RECEIPT_V1' OR w.checkpoint::jsonb->>'outcome' IN ('SUPPORTED_FACTS_VERIFIED','INITIAL_FACTS_VERIFIED') OR p_payload->>'outcome' IN ('SUPPORTED_FACTS_VERIFIED','INITIAL_FACTS_VERIFIED') THEN RAISE EXCEPTION 'BROKER_FACT_RECEIPT_REQUIRED' USING ERRCODE='42501'; END IF;
   IF octet_length(p_payload::text)>least(131072,(w.limits->>'audit_bytes')::integer) OR jsonb_typeof(p_payload)<>'object' THEN RAISE EXCEPTION 'CHECKPOINT_BOUND'; END IF;
   IF w.contract='listing-screen-v3' AND p_payload ? 'capture_bound' THEN
    IF p_payload->'capture_bound' IS DISTINCT FROM 'true'::jsonb
    OR jsonb_array_length(w.dependencies::jsonb)<>1
    OR p_payload->>'capture_key' IS DISTINCT FROM w.dependencies->>0
    OR coalesce(p_payload->>'capture_checkpoint_sha256','') !~ '^[a-f0-9]{64}$'
    OR NOT EXISTS(SELECT 1 FROM public.ingestion_work_items x WHERE x.key=w.dependencies->>0
      AND x.state='COMPLETE' AND x.task='DISCOVERY' AND x.checkpoint::jsonb->>'kind'='LISTING_RECEIPT_V1')
    THEN RAISE EXCEPTION 'CAPTURE_BOUND_RECEIPT'; END IF;
   END IF;
   IF w.contract='listing-screen-v3' AND (coalesce(p_payload->>'rule_version','')<>'manchester-listing-screen-assessment-v3' OR coalesce(p_payload->>'routing_authority','')<>'count_assessment' OR jsonb_typeof(p_payload->'count_assessment') IS DISTINCT FROM 'object' OR coalesce((p_payload->'count_assessment'->>'admission') NOT IN ('ADMIT_FOR_ASSESSMENT','ADMIT_SCHEME','RETAIN_BELOW_THRESHOLD','RETAIN_NOT_RESIDENTIAL_SUPPLY','RETAIN_RELATED_TO_PARENT','RETAIN_UNUSABLE_PROPOSAL','RETAIN_WATCHLIST','ROUTE_COUNT_UNCONFIRMED'),true) OR coalesce(p_payload->>'assessment_revision','')<>w.revision OR coalesce(p_payload->>'record_sha256','') !~ '^[a-f0-9]{64}$' OR coalesce(p_payload->>'config_sha256','') !~ '^[a-f0-9]{64}$' OR (CASE WHEN p_payload->'capture_bound'='true'::jsonb THEN encode(sha256(convert_to('{"assessment_revision":"'||encode(sha256(convert_to('{"config_sha256":"'||(p_payload->>'config_sha256')||'","record_sha256":"'||(p_payload->>'record_sha256')||'"}','UTF8')),'hex')||'","observation_sha256":"'||(p_payload->>'capture_checkpoint_sha256')||'"}','UTF8')),'hex') ELSE encode(sha256(convert_to('{"config_sha256":"'||(p_payload->>'config_sha256')||'","record_sha256":"'||(p_payload->>'record_sha256')||'"}','UTF8')),'hex') END) IS DISTINCT FROM w.revision OR coalesce(NOT (g->'screening_configs' ? (p_payload->>'config_sha256')),true)) THEN RAISE EXCEPTION 'SCREENING_V3_RECEIPT'; END IF;
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
REVOKE ingestion_storage_owner FROM postgres GRANTED BY postgres;
DO $post$
DECLARE me oid:=to_regrole('postgres'); storage_owner oid:=to_regrole('ingestion_storage_owner'); worker_cap oid:=to_regrole('ingestion_worker'); snap jsonb; prior jsonb:=current_setting('intake_install.functions')::jsonb;
 cand constant jsonb:=jsonb_build_object('ingestion_bolton_allowed','09d3e0e8e87bbf158bb89cb683063a21e5e8c23076d342961d49b50ac7e60569','ingestion_register_bolton_exception','dba6b809c50b9bd937b2f509fc05c20de9d69499ca4394e9007ef3af196b481c','ingestion_worker_step','abb46082f6d0891e131271a2567d45d8afdeccfd4561a6692baece7c3759c5bf'); unch constant jsonb:=jsonb_build_object('ingestion_acceptance_control','f25822db425df0c125df975d1cb46cfc710b76999744304d45d7037292d77d17','ingestion_raise_stop','5e41868876be6c533a31a8f7af25442ce308cb42681210296d516f361521e53a','ingestion_recover_abandoned','9e7f98210c737d6f8f7fae2d98e328261ab9faf31481f041b6f63befa6686f58','ingestion_oldham_allowed','091ec5ee578083b0b64431542ec02ff8a39263d345dee6a360dde68d3622900a'); k text; names constant text[]:=ARRAY['ingestion_acceptance_control','ingestion_bolton_allowed','ingestion_oldham_allowed','ingestion_raise_stop','ingestion_recover_abandoned','ingestion_register_bolton_exception','ingestion_worker_step']; ctl jsonb; expected_acl jsonb;
BEGIN
 -- Cleanup first: nothing temporary may remain.
 IF current_user<>'postgres' OR pg_has_role(me,storage_owner,'SET') IS DISTINCT FROM false OR pg_has_role(me,storage_owner,'USAGE') IS DISTINCT FROM false
 OR (SELECT coalesce(jsonb_agg(to_jsonb(m) ORDER BY m.roleid,m.grantor),'[]'::jsonb) FROM pg_auth_members m WHERE m.member=me AND m.roleid=storage_owner) IS DISTINCT FROM current_setting('intake_install.owner_rows')::jsonb
 OR (SELECT coalesce(jsonb_agg(jsonb_build_array(CASE WHEN x.grantor=0 THEN 'PUBLIC' ELSE pg_get_userbyid(x.grantor) END,CASE WHEN x.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(x.grantee) END,x.privilege_type,x.is_grantable)
 ORDER BY x.grantor,x.grantee,x.privilege_type),'[]'::jsonb) FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) x WHERE n.oid='public'::regnamespace) IS DISTINCT FROM current_setting('intake_install.schema_acl')::jsonb OR has_schema_privilege(storage_owner,'public','CREATE') IS DISTINCT FROM false
 THEN RAISE EXCEPTION 'INSTALL_CLEANUP'; END IF;
 -- Function postconditions: exactly the three candidates, every attribute and every other ACL unchanged, one added worker EXECUTE.
 snap:=(SELECT coalesce(jsonb_object_agg(p.proname,jsonb_build_object('sha',encode(sha256(convert_to(p.prosrc,'UTF8')),'hex'),'owner',pg_get_userbyid(p.proowner),'config',to_jsonb(p.proconfig),
 'secdef',p.prosecdef,'vol',p.provolatile::text,'lang',(SELECT lanname::text FROM pg_language WHERE oid=p.prolang),'ret',p.prorettype::regtype::text,
 'args',encode(sha256(convert_to(pg_get_function_identity_arguments(p.oid),'UTF8')),'hex'),'acl_present',p.proacl IS NOT NULL,
 'acl',coalesce((SELECT jsonb_agg(jsonb_build_array(CASE WHEN x.grantor=0 THEN 'PUBLIC' ELSE pg_get_userbyid(x.grantor) END,CASE WHEN x.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(x.grantee) END,x.privilege_type,x.is_grantable)
   ORDER BY x.grantor,x.grantee,x.privilege_type) FROM aclexplode(p.proacl) x),'[]'::jsonb))),'{}'::jsonb)
 FROM pg_proc p WHERE p.pronamespace='public'::regnamespace AND p.proname=ANY(ARRAY['ingestion_acceptance_control','ingestion_bolton_allowed','ingestion_oldham_allowed','ingestion_raise_stop','ingestion_recover_abandoned','ingestion_register_bolton_exception','ingestion_worker_step']));
 IF (SELECT count(*) FROM pg_proc WHERE pronamespace='public'::regnamespace AND proname=ANY(names))<>7 THEN RAISE EXCEPTION 'INSTALL_POST_INVENTORY'; END IF;
 FOREACH k IN ARRAY names LOOP
  IF cand ? k THEN IF snap->k->>'sha' IS DISTINCT FROM cand->>k THEN RAISE EXCEPTION 'INSTALL_POST_BODY'; END IF;
  ELSE IF snap->k IS DISTINCT FROM prior->k OR snap->k->>'sha' IS DISTINCT FROM unch->>k THEN RAISE EXCEPTION 'INSTALL_POST_UNCHANGED'; END IF; END IF;
  IF (snap->k)-'sha'-'acl' IS DISTINCT FROM (prior->k)-'sha'-'acl' THEN RAISE EXCEPTION 'INSTALL_POST_ATTRIBUTES'; END IF;
  IF k<>'ingestion_register_bolton_exception' AND snap->k->'acl' IS DISTINCT FROM prior->k->'acl' THEN RAISE EXCEPTION 'INSTALL_POST_ACL'; END IF;
 END LOOP;
 expected_acl:=(SELECT jsonb_agg(e ORDER BY e->>0,e->>1,e->>2) FROM (SELECT e FROM jsonb_array_elements(prior->'ingestion_register_bolton_exception'->'acl') e
   UNION ALL SELECT jsonb_build_array('ingestion_storage_owner','ingestion_worker','EXECUTE',false)) q);
 IF (SELECT jsonb_agg(e ORDER BY e->>0,e->>1,e->>2) FROM jsonb_array_elements(snap->'ingestion_register_bolton_exception'->'acl') e) IS DISTINCT FROM expected_acl THEN RAISE EXCEPTION 'INSTALL_POST_REGISTER_ACL'; END IF;
 IF has_function_privilege('ingestion_worker_login',to_regprocedure('public.ingestion_register_bolton_exception(jsonb)'),'EXECUTE') IS DISTINCT FROM true
 OR has_function_privilege('ingestion_effect_login',to_regprocedure('public.ingestion_register_bolton_exception(jsonb)'),'EXECUTE') IS DISTINCT FROM false
 OR has_function_privilege('ingestion_worker_login',to_regprocedure('public.ingestion_bolton_allowed(jsonb,text,jsonb)'),'EXECUTE') IS DISTINCT FROM false
 OR has_function_privilege('ingestion_effect_login',to_regprocedure('public.ingestion_bolton_allowed(jsonb,text,jsonb)'),'EXECUTE') IS DISTINCT FROM false
 OR has_function_privilege('ingestion_worker_login',to_regprocedure('public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)'),'EXECUTE') IS DISTINCT FROM true
 OR has_function_privilege('ingestion_effect_login',to_regprocedure('public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)'),'EXECUTE') IS DISTINCT FROM true
 THEN RAISE EXCEPTION 'INSTALL_POST_FUNCTION_PRIVILEGE'; END IF;
 -- Ledger, stop, recovered items, authorities and periods byte-identical.
 SELECT outcome::jsonb INTO STRICT ctl FROM public.ingestion_work_items WHERE key=repeat('0',64);
 IF ctl IS DISTINCT FROM current_setting('intake_install.control')::jsonb OR encode(sha256(convert_to(jsonb_build_object('items',(SELECT coalesce(jsonb_agg(to_jsonb(w) ORDER BY w.key),'[]'::jsonb) FROM public.ingestion_work_items w),
 'attempts',(SELECT coalesce(jsonb_agg(to_jsonb(a) ORDER BY a.work_key,a.fence),'[]'::jsonb) FROM public.ingestion_work_attempts a))::text,'UTF8')),'hex') IS DISTINCT FROM current_setting('intake_install.ledger') THEN RAISE EXCEPTION 'INSTALL_LEDGER_CHANGED'; END IF;
 RAISE NOTICE 'BOLTON_INTAKE_INSTALL_POSTCONDITIONS_VERIFIED_NOT_YET_COMMITTED';
END $post$;
SELECT 'install_functions' AS section,p.proname,encode(sha256(convert_to(p.prosrc,'UTF8')),'hex') AS body_sha256,pg_get_userbyid(p.proowner) AS owner,p.prosecdef AS security_definer,p.proconfig AS config
FROM pg_proc p WHERE p.pronamespace='public'::regnamespace AND p.proname IN ('ingestion_bolton_allowed','ingestion_register_bolton_exception','ingestion_worker_step') ORDER BY p.proname;
SELECT 'install_stop' AS section,outcome::jsonb->'hard_stop_generation' AS generation,outcome::jsonb->>'manual_stop' AS manual_stop,outcome::jsonb->'global_stop' AS global_stop FROM public.ingestion_work_items WHERE key=repeat('0',64);
COMMIT;
SELECT 'BOLTON_INTAKE_INSTALL_COMMIT_ACKNOWLEDGED' AS disposition;
