"""Assemble the guarded single-transaction installation SQL from the EXISTING PR #206 generator (verification.ingestion_storage.intake_policy). Offline; no database.

    python generate_installation.py <PR206-checkout> > bolton-intake-install.sql

The three CREATE OR REPLACE statements and the one worker EXECUTE grant are taken verbatim from intake_policy.installation_script(); this file adds only the preflight, the temporary owner
capability (SET-only, narrower than the generator's ceremony), the postconditions and the cleanup verification, all inside the SAME transaction."""
import hashlib,os,re,sys,json
from pathlib import Path
repo=os.path.abspath(sys.argv[1]);sys.path.insert(0,repo);os.chdir(repo)
from verification.ingestion_storage import intake_policy as ip,screening_v3_worker_sql as v3
from verification.ingestion_storage.operational_owner import Owner

sha=lambda s:hashlib.sha256(s.encode()).hexdigest()
PRED=dict(ingestion_bolton_allowed='961c1e1c441372a6c4fb4606d0f5b973a14dbb7e1fa390740789a4d4de2fe8bf',ingestion_register_bolton_exception='b5ce45dcaa4183b2f828dfb6383a0dde838d0b5365206ba406f8854f7bc0b3cd',
          ingestion_worker_step='79324a92b380de621e595470318f725cf64dbc1ac9c332591363cb70161ca912')
CAND=dict(ingestion_bolton_allowed='09d3e0e8e87bbf158bb89cb683063a21e5e8c23076d342961d49b50ac7e60569',ingestion_register_bolton_exception='dba6b809c50b9bd937b2f509fc05c20de9d69499ca4394e9007ef3af196b481c',
          ingestion_worker_step='abb46082f6d0891e131271a2567d45d8afdeccfd4561a6692baece7c3759c5bf')
UNCH=dict(ingestion_acceptance_control='f25822db425df0c125df975d1cb46cfc710b76999744304d45d7037292d77d17',ingestion_raise_stop='5e41868876be6c533a31a8f7af25442ce308cb42681210296d516f361521e53a',
          ingestion_recover_abandoned='9e7f98210c737d6f8f7fae2d98e328261ab9faf31481f041b6f63befa6686f58',ingestion_oldham_allowed='091ec5ee578083b0b64431542ec02ff8a39263d345dee6a360dde68d3622900a')
# identity-argument text hashes OBSERVED in production (2026-10-28 reconciliation, function_identities.signature_sha256) plus language/volatility/security-definer there
ARGS=dict(ingestion_bolton_allowed='ba1a6d72fc2b3badaa07f6f30f21ca4ceb24d657fa76e2d3cd5852511a49624f',ingestion_register_bolton_exception='ae7c50f98c8176db1f8d86e47a4e03f357e564cfb0d2f9719310105cb35a8b75',
          ingestion_worker_step='89e187297ff20c60b356f8324d375a82ac988e691fd20dde56b6059875762ed7',ingestion_oldham_allowed='d7a6bbabaa4cae893f3a049ac63cc43330426c07ffeebc312515cc29cc10f8af',
          ingestion_raise_stop='b5963c90e9f0d266eef3486a4d549047ed8a808a32269541d7602a2887b370a5',ingestion_recover_abandoned='84a70cc3c7b752e69569fbb83b0825c1be76384f24ca262b94dd784b8930393e',
          ingestion_acceptance_control='e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')
ATTR=dict(ingestion_bolton_allowed=('sql','s',False),ingestion_register_bolton_exception=('plpgsql','v',True),ingestion_worker_step=('plpgsql','v',True),ingestion_oldham_allowed=('sql','s',True),
          ingestion_raise_stop=('plpgsql','v',True),ingestion_recover_abandoned=('plpgsql','v',True),ingestion_acceptance_control=('sql','v',True))
NAMES=sorted(ATTR)

script=ip.installation_script()
bodies={m[1]:sha(m[3]) for m in Owner.FUNCTION_PATTERN.finditer(script)}
assert bodies==CAND,bodies      # the existing generator yields exactly the expected candidate bodies
OPEN=v3.CEREMONY_OPEN;CLOSE=v3.CEREMONY_CLOSE
assert script.startswith(OPEN) and script.endswith(CLOSE)
replacements=script[len(OPEN):-len(CLOSE)]
assert replacements.count('CREATE OR REPLACE FUNCTION')==3 and replacements.count('GRANT EXECUTE')==1 and replacements.count('GRANT ')==1 and 'REVOKE' not in replacements

L=lambda d:"jsonb_build_object("+",".join("'%s','%s'"%(k,v) for k,v in d.items())+")"
SNAP="""(SELECT coalesce(jsonb_object_agg(p.proname,jsonb_build_object('sha',encode(sha256(convert_to(p.prosrc,'UTF8')),'hex'),'owner',pg_get_userbyid(p.proowner),'config',to_jsonb(p.proconfig),
 'secdef',p.prosecdef,'vol',p.provolatile::text,'lang',(SELECT lanname::text FROM pg_language WHERE oid=p.prolang),'ret',p.prorettype::regtype::text,
 'args',encode(sha256(convert_to(pg_get_function_identity_arguments(p.oid),'UTF8')),'hex'),'acl_present',p.proacl IS NOT NULL,
 'acl',coalesce((SELECT jsonb_agg(jsonb_build_array(CASE WHEN x.grantor=0 THEN 'PUBLIC' ELSE pg_get_userbyid(x.grantor) END,CASE WHEN x.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(x.grantee) END,x.privilege_type,x.is_grantable)
   ORDER BY x.grantor,x.grantee,x.privilege_type) FROM aclexplode(p.proacl) x),'[]'::jsonb))),'{}'::jsonb)
 FROM pg_proc p WHERE p.pronamespace='public'::regnamespace AND p.proname=ANY(%s))""" % "ARRAY[%s]"%",".join("'%s'"%n for n in NAMES)
LEDGER="""encode(sha256(convert_to(jsonb_build_object('items',(SELECT coalesce(jsonb_agg(to_jsonb(w) ORDER BY w.key),'[]'::jsonb) FROM public.ingestion_work_items w),
 'attempts',(SELECT coalesce(jsonb_agg(to_jsonb(a) ORDER BY a.work_key,a.fence),'[]'::jsonb) FROM public.ingestion_work_attempts a))::text,'UTF8')),'hex')"""
SCHEMA_ACL="""(SELECT coalesce(jsonb_agg(jsonb_build_array(CASE WHEN x.grantor=0 THEN 'PUBLIC' ELSE pg_get_userbyid(x.grantor) END,CASE WHEN x.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(x.grantee) END,x.privilege_type,x.is_grantable)
 ORDER BY x.grantor,x.grantee,x.privilege_type),'[]'::jsonb) FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) x WHERE n.oid='public'::regnamespace)"""
OWNER_ROWS="""(SELECT coalesce(jsonb_agg(to_jsonb(m) ORDER BY m.roleid,m.grantor),'[]'::jsonb) FROM pg_auth_members m WHERE m.member=me AND m.roleid=storage_owner)"""
PRE=L(PRED);CAN=L(CAND);UNC=L(UNCH)
ARGS_J=L(ARGS)
ATTR_J="jsonb_build_object("+",".join("'%s',jsonb_build_array('%s','%s',%s)"%(k,a,b,'true' if c else 'false') for k,(a,b,c) in ATTR.items())+")"
STOP="""'{"reason":"CONSUMED_SALFORD_GLOBAL_STOP","run":"38884069913"}'::jsonb"""

# Closed runtime access and completed cleanup are separate from capability ACLs.
CLEANED_INPUT=json.dumps(json.loads((Path(__file__).resolve().parent/'historical-bindings.json').read_text()),separators=(',',':'))
ALL_MEMBERS="(SELECT coalesce(jsonb_agg(to_jsonb(am) ORDER BY roleid,member,grantor),'[]'::jsonb) FROM pg_auth_members am)"
RUNTIME_SNAPSHOT="""(SELECT jsonb_agg(jsonb_build_array(rr.rolname,rr.rolcanlogin,aa.rolpassword IS NULL,rr.rolsuper,rr.rolcreaterole,rr.rolcreatedb,rr.rolbypassrls,rr.rolreplication,rr.rolinherit,rr.rolconnlimit,rr.rolvaliduntil,rr.rolconfig) ORDER BY rr.rolname)
 FROM pg_roles rr JOIN pg_authid aa ON aa.rolname=rr.rolname WHERE rr.rolname IN ('ingestion_worker_login','ingestion_effect_login'))"""
RUNTIME_CLOSED="""IF (SELECT count(*) FROM pg_roles rr JOIN pg_authid aa ON aa.rolname=rr.rolname WHERE rr.rolname IN ('ingestion_worker_login','ingestion_effect_login') AND NOT rr.rolcanlogin AND aa.rolpassword IS NULL AND NOT rr.rolsuper AND NOT rr.rolcreaterole AND NOT rr.rolcreatedb AND NOT rr.rolbypassrls AND NOT rr.rolreplication AND NOT rr.rolinherit)<>2
 OR EXISTS(SELECT 1 FROM pg_auth_members WHERE (member='ingestion_worker_login'::regrole AND roleid='ingestion_worker'::regrole) OR (member='ingestion_effect_login'::regrole AND roleid='ingestion_effect_broker'::regrole))
 OR EXISTS(SELECT 1 FROM pg_roles rr WHERE rr.rolname IN ('ingestion_worker_login','ingestion_effect_login') AND (pg_has_role(rr.oid,'ingestion_worker','MEMBER') OR pg_has_role(rr.oid,'ingestion_effect_broker','MEMBER')))
 THEN RAISE EXCEPTION 'INSTALL_RUNTIME_NOT_CLOSED'; END IF;"""
CLEANUP_BINDING="""historical_package_hash:=encode(sha256(convert_to((historical_record->'allowance'->'package')::text,'UTF8')),'hex');
 historical_record:=replace(historical_record::text,'PACKAGE_HASH_COMPUTED_IN_POSTGRES',historical_package_hash)::jsonb;
 historical_grant:=jsonb_set(historical_record->'grant','{expires_at}','0'::jsonb);
 historical_allowance:=jsonb_set(historical_record->'allowance','{revoked}','true'::jsonb);
 IF ctl->'grants'->'INGESTION_CHAIN_OLDHAM_STAGED_CAPTURE_E9D12874CFB5' IS DISTINCT FROM historical_grant
 OR ctl->'oldham_allowances'->'INGESTION_CHAIN_OLDHAM_STAGED_CAPTURE_E9D12874CFB5' IS DISTINCT FROM historical_allowance
 OR (SELECT coalesce(jsonb_agg(to_jsonb(hw) ORDER BY hw.key),'[]'::jsonb) FROM public.ingestion_work_items hw WHERE hw.key IN (SELECT jsonb_array_elements_text(historical_grant->'keys'))) IS DISTINCT FROM historical_record->'allowance'->'package'->'registration'->'rows'
 THEN RAISE EXCEPTION 'INSTALL_OLDHAM_CLEANUP_BINDING'; END IF;"""

PREFLIGHT="""DO $preflight$
DECLARE me oid; storage_owner oid; worker_cap oid; ctl jsonb; snap jsonb; n integer; names constant text[]:=ARRAY[%(names)s];
 pred constant jsonb:=%(pred)s; cand constant jsonb:=%(cand)s; unch constant jsonb:=%(unch)s; argh constant jsonb:=%(args)s; attr constant jsonb:=%(attr)s; k text; historical_record jsonb:=$cleanup$%(cleaned_input)s$cleanup$::jsonb; historical_package_hash text; historical_grant jsonb; historical_allowance jsonb;
BEGIN
 IF current_user<>'postgres' OR session_user<>'postgres' OR current_database()<>'postgres' OR current_setting('transaction_read_only')<>'off' THEN RAISE EXCEPTION 'INSTALL_IDENTITY_OR_MODE'; END IF;
 me:=to_regrole('postgres');storage_owner:=to_regrole('ingestion_storage_owner');worker_cap:=to_regrole('ingestion_worker');
 IF storage_owner IS NULL OR worker_cap IS NULL THEN RAISE EXCEPTION 'INSTALL_ROLES_MISSING'; END IF;
 IF pg_has_role(me,'pg_read_all_stats','USAGE') IS DISTINCT FROM true OR row_security_active('public.ingestion_work_items'::regclass) OR row_security_active('public.ingestion_work_attempts'::regclass)
 OR EXISTS(SELECT 1 FROM pg_stat_activity WHERE usename IN ('ingestion_worker_login','ingestion_effect_login','ingestion_application_login','ingestion_recovery_login'))
 THEN RAISE EXCEPTION 'INSTALL_SESSION_VISIBILITY_OR_ACTIVITY'; END IF;
 -- Exact recognised predecessor: one function per name, reviewed owner/search_path/security/volatility/language/arguments, no PUBLIC ACL.
 snap:=%(snap)s;
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
 -- The three replaced functions: capability-role EXECUTE state (runtime remains closed) (no worker EXECUTE on the exception registrar; worker/effect on the worker step; nothing on the allowance policy).
 IF has_function_privilege('ingestion_worker',to_regprocedure('public.ingestion_register_bolton_exception(jsonb)'),'EXECUTE') IS DISTINCT FROM false
 OR has_function_privilege('ingestion_effect_broker',to_regprocedure('public.ingestion_register_bolton_exception(jsonb)'),'EXECUTE') IS DISTINCT FROM false
 OR has_function_privilege('ingestion_worker',to_regprocedure('public.ingestion_bolton_allowed(jsonb,text,jsonb)'),'EXECUTE') IS DISTINCT FROM false
 OR has_function_privilege('ingestion_effect_broker',to_regprocedure('public.ingestion_bolton_allowed(jsonb,text,jsonb)'),'EXECUTE') IS DISTINCT FROM false
 OR has_function_privilege('ingestion_worker',to_regprocedure('public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)'),'EXECUTE') IS DISTINCT FROM true
 OR has_function_privilege('ingestion_effect_broker',to_regprocedure('public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)'),'EXECUTE') IS DISTINCT FROM true
 OR has_function_privilege(worker_cap,to_regprocedure('public.ingestion_register_bolton_exception(jsonb)'),'EXECUTE') IS DISTINCT FROM false
 THEN RAISE EXCEPTION 'INSTALL_PRIOR_FUNCTION_PRIVILEGE'; END IF;
 %(runtime_closed)s
 -- Stop, recovered items and ledger as left by the committed recovery (generation 5; NOT the historical generation-3 binding).
 SELECT outcome::jsonb INTO STRICT ctl FROM public.ingestion_work_items WHERE key=repeat('0',64);
 IF ctl->'global_stop' IS DISTINCT FROM %(stop)s OR ctl->>'manual_stop' IS DISTINCT FROM 'ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP' OR ctl->>'last_hard_stop' IS DISTINCT FROM 'ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP'
 OR ctl->'hard_stop_generation' IS DISTINCT FROM '5'::jsonb THEN RAISE EXCEPTION 'INSTALL_STOP_BINDING'; END IF;
 IF (SELECT count(*) FROM public.ingestion_work_items WHERE key IN ('3f0dba235de9b9efcd52ef3b281ba8c967491f57824404c695ed2b32fae4c045','e92a8e220bbbbcefb2425d6f97a60920bc447bc1fe097d600ea28e3e9d87588e')
    AND state='SAFETY_BLOCKED' AND phase='RECOVERED' AND fence=2 AND owner IS NULL AND lease_until IS NULL AND reason='ABANDONED_SOURCE_INTENT' AND next_action='RECONCILE')<>2
 THEN RAISE EXCEPTION 'INSTALL_RECOVERED_ITEMS'; END IF;
 %(cleanup_binding)s
 -- Owner-role baseline: exactly the ADMIN-only distinct-grantor membership; no SET/USAGE; no schema CREATE for the owner; the identity must hold the schema CREATE grant option.
 IF pg_has_role(me,storage_owner,'SET') IS DISTINCT FROM false OR pg_has_role(me,storage_owner,'USAGE') IS DISTINCT FROM false
 OR (SELECT count(*) FROM pg_auth_members WHERE roleid=storage_owner AND member=me)<>1
 OR NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE roleid=storage_owner AND member=me AND admin_option AND NOT inherit_option AND NOT set_option AND grantor<>me)
 THEN RAISE EXCEPTION 'INSTALL_OWNER_ADMIN_BASELINE'; END IF;
 IF has_schema_privilege(storage_owner,'public','CREATE') IS DISTINCT FROM false OR has_schema_privilege(me,'public','CREATE WITH GRANT OPTION') IS DISTINCT FROM true
 THEN RAISE EXCEPTION 'INSTALL_SCHEMA_BASELINE'; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE oid=storage_owner AND NOT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolinherit AND NOT rolbypassrls)
 THEN RAISE EXCEPTION 'INSTALL_OWNER_ROLE_STATE'; END IF;
 PERFORM set_config('intake_install.memberships',%(all_members)s::text,true);
 PERFORM set_config('intake_install.runtime',%(runtime_snapshot)s::text,true);
 PERFORM set_config('intake_install.functions',snap::text,true);
 PERFORM set_config('intake_install.owner_rows',%(owner_rows)s::text,true);
 PERFORM set_config('intake_install.schema_acl',%(schema_acl)s::text,true);
 PERFORM set_config('intake_install.ledger',%(ledger)s,true);
 PERFORM set_config('intake_install.control',ctl::text,true);
END $preflight$;
""" % dict(names=",".join("'%s'"%n for n in NAMES),pred=PRE,cand=CAN,unch=UNC,args=ARGS_J,attr=ATTR_J,snap=SNAP,stop=STOP,owner_rows=OWNER_ROWS,schema_acl=SCHEMA_ACL,ledger=LEDGER,runtime_closed=RUNTIME_CLOSED,cleanup_binding=CLEANUP_BINDING,cleaned_input=CLEANED_INPUT,all_members=ALL_MEMBERS,runtime_snapshot=RUNTIME_SNAPSHOT)

TEMP="""-- Temporary capabilities (both removed again before COMMIT): a SET-only self-granted owner row and the owner's schema CREATE (required for CREATE OR REPLACE FUNCTION in schema public).
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
"""

CLEAN="""RESET ROLE;
REVOKE CREATE ON SCHEMA public FROM ingestion_storage_owner;
REVOKE ingestion_storage_owner FROM postgres GRANTED BY postgres;
DO $post$
DECLARE me oid:=to_regrole('postgres'); storage_owner oid:=to_regrole('ingestion_storage_owner'); worker_cap oid:=to_regrole('ingestion_worker'); snap jsonb; prior jsonb:=current_setting('intake_install.functions')::jsonb;
 cand constant jsonb:=%(cand)s; unch constant jsonb:=%(unch)s; k text; names constant text[]:=ARRAY[%(names)s]; ctl jsonb; expected_acl jsonb;
BEGIN
 -- Cleanup first: nothing temporary may remain.
 IF current_user<>'postgres' OR pg_has_role(me,storage_owner,'SET') IS DISTINCT FROM false OR pg_has_role(me,storage_owner,'USAGE') IS DISTINCT FROM false
 OR %(owner_rows)s IS DISTINCT FROM current_setting('intake_install.owner_rows')::jsonb
 OR %(schema_acl)s IS DISTINCT FROM current_setting('intake_install.schema_acl')::jsonb OR has_schema_privilege(storage_owner,'public','CREATE') IS DISTINCT FROM false
 THEN RAISE EXCEPTION 'INSTALL_CLEANUP'; END IF;
 -- Function postconditions: exactly the three candidates, every attribute and every other ACL unchanged, one added worker EXECUTE.
 snap:=%(snap)s;
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
 IF has_function_privilege('ingestion_worker',to_regprocedure('public.ingestion_register_bolton_exception(jsonb)'),'EXECUTE') IS DISTINCT FROM true
 OR has_function_privilege('ingestion_effect_broker',to_regprocedure('public.ingestion_register_bolton_exception(jsonb)'),'EXECUTE') IS DISTINCT FROM false
 OR has_function_privilege('ingestion_worker',to_regprocedure('public.ingestion_bolton_allowed(jsonb,text,jsonb)'),'EXECUTE') IS DISTINCT FROM false
 OR has_function_privilege('ingestion_effect_broker',to_regprocedure('public.ingestion_bolton_allowed(jsonb,text,jsonb)'),'EXECUTE') IS DISTINCT FROM false
 OR has_function_privilege('ingestion_worker',to_regprocedure('public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)'),'EXECUTE') IS DISTINCT FROM true
 OR has_function_privilege('ingestion_effect_broker',to_regprocedure('public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)'),'EXECUTE') IS DISTINCT FROM true
 THEN RAISE EXCEPTION 'INSTALL_POST_FUNCTION_PRIVILEGE'; END IF;
 %(runtime_closed)s
 IF %(all_members)s IS DISTINCT FROM current_setting('intake_install.memberships')::jsonb OR %(runtime_snapshot)s IS DISTINCT FROM current_setting('intake_install.runtime')::jsonb THEN RAISE EXCEPTION 'INSTALL_RUNTIME_OR_MEMBERSHIP_CHANGED'; END IF;
 -- Ledger, stop, recovered items, authorities and periods byte-identical.
 SELECT outcome::jsonb INTO STRICT ctl FROM public.ingestion_work_items WHERE key=repeat('0',64);
 IF ctl IS DISTINCT FROM current_setting('intake_install.control')::jsonb OR %(ledger)s IS DISTINCT FROM current_setting('intake_install.ledger') THEN RAISE EXCEPTION 'INSTALL_LEDGER_CHANGED'; END IF;
 RAISE NOTICE 'BOLTON_INTAKE_INSTALL_POSTCONDITIONS_VERIFIED_NOT_YET_COMMITTED';
END $post$;
SELECT 'install_functions' AS section,p.proname,encode(sha256(convert_to(p.prosrc,'UTF8')),'hex') AS body_sha256,pg_get_userbyid(p.proowner) AS owner,p.prosecdef AS security_definer,p.proconfig AS config
FROM pg_proc p WHERE p.pronamespace='public'::regnamespace AND p.proname IN ('ingestion_bolton_allowed','ingestion_register_bolton_exception','ingestion_worker_step') ORDER BY p.proname;
SELECT 'install_stop' AS section,outcome::jsonb->'hard_stop_generation' AS generation,outcome::jsonb->>'manual_stop' AS manual_stop,outcome::jsonb->'global_stop' AS global_stop FROM public.ingestion_work_items WHERE key=repeat('0',64);
COMMIT;
SELECT 'BOLTON_INTAKE_INSTALL_COMMIT_ACKNOWLEDGED' AS disposition;
""" % dict(cand=CAN,unch=UNC,names=",".join("'%s'"%n for n in NAMES),snap=SNAP,owner_rows=OWNER_ROWS,schema_acl=SCHEMA_ACL,ledger=LEDGER,runtime_closed=RUNTIME_CLOSED,all_members=ALL_MEMBERS,runtime_snapshot=RUNTIME_SNAPSHOT)

HEAD="""-- INACTIVE: guarded single-transaction replacement of exactly three daily-intake functions over the recognised Oldham-worker predecessor. Generated from the EXISTING PR #206 generator.
BEGIN;
SET LOCAL statement_timeout='10s';
SET LOCAL lock_timeout='3s';
SET LOCAL idle_in_transaction_session_timeout='10s';
SET LOCAL search_path=pg_catalog;
"""
sql=HEAD+PREFLIGHT+TEMP+replacements.rstrip('\n')+'\n'+CLEAN
sys.stdout.write(sql)
