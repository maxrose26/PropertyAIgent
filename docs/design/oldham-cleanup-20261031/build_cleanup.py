"""Offline assembly of one narrow revocation transaction; never connects."""
from pathlib import Path
import json,sys,ast
p=Path(__file__).resolve().parent
bindings=json.loads((p/'historical-bindings.json').read_text())
expected=json.dumps(bindings,separators=(',',':'))
functions="""(SELECT coalesce(jsonb_agg(to_jsonb(f) ORDER BY f.oid),'[]'::jsonb) FROM pg_proc f WHERE pronamespace='public'::regnamespace)"""
members="(SELECT coalesce(jsonb_agg(to_jsonb(m) ORDER BY roleid,member,grantor),'[]'::jsonb) FROM pg_auth_members m)"
ledger="""jsonb_build_object('items',(SELECT jsonb_agg(to_jsonb(w) ORDER BY key) FROM public.ingestion_work_items w),'attempts',(SELECT coalesce(jsonb_agg(to_jsonb(attempt_row) ORDER BY work_key,fence),'[]'::jsonb) FROM public.ingestion_work_attempts attempt_row))"""
base="""BEGIN;
SET LOCAL search_path=pg_catalog;
SET LOCAL statement_timeout='10s';
SET LOCAL lock_timeout='3s';
SET LOCAL idle_in_transaction_session_timeout='10s';
DO $pre$
DECLARE owner_id oid:='ingestion_storage_owner'::regrole; me oid:='postgres'::regrole; r record;
BEGIN
 IF current_user<>'postgres' OR session_user<>'postgres' OR current_database()<>'postgres' THEN RAISE EXCEPTION 'CLEANUP_IDENTITY'; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE oid=me AND NOT rolsuper AND rolcreaterole AND rolcreatedb AND rolbypassrls) OR NOT EXISTS(SELECT 1 FROM pg_roles WHERE oid=owner_id AND NOT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolinherit AND NOT rolbypassrls) THEN RAISE EXCEPTION 'CLEANUP_ROLE_FLAGS'; END IF;
 IF pg_has_role(me,owner_id,'SET') OR pg_has_role(me,owner_id,'USAGE') OR
 (SELECT count(*) FROM pg_auth_members WHERE roleid=owner_id AND member=me)<>1 OR
 NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE roleid=owner_id AND member=me AND admin_option AND NOT inherit_option AND NOT set_option AND grantor<>me) THEN RAISE EXCEPTION 'CLEANUP_OWNER_BASELINE'; END IF;
 IF NOT pg_has_role(me,'pg_read_all_stats','USAGE') OR EXISTS(SELECT 1 FROM pg_stat_activity WHERE usename IN ('ingestion_worker_login','ingestion_effect_login','ingestion_application_login','ingestion_recovery_login')) THEN RAISE EXCEPTION 'CLEANUP_SESSIONS_OR_VISIBILITY'; END IF;
 IF (SELECT count(*) FROM pg_roles WHERE rolname IN ('ingestion_worker_login','ingestion_effect_login') AND NOT rolcanlogin AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolbypassrls AND NOT rolreplication)<>2 THEN RAISE EXCEPTION 'CLEANUP_LOGIN_STATE'; END IF;
 IF (SELECT count(*) FROM pg_authid WHERE rolname IN ('ingestion_worker_login','ingestion_effect_login') AND rolpassword IS NULL)<>2 THEN RAISE EXCEPTION 'CLEANUP_PASSWORD_PRESENCE'; END IF;
 FOR r IN SELECT * FROM (VALUES ('ingestion_worker_login','ingestion_worker'),('ingestion_effect_login','ingestion_effect_broker')) x(member_name,role_name) LOOP
  IF (SELECT count(*) FROM pg_auth_members WHERE member=r.member_name::regrole AND roleid=r.role_name::regrole)<>1 OR
   NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.member_name::regrole AND roleid=r.role_name::regrole AND grantor=me AND NOT admin_option AND inherit_option AND NOT set_option) OR
   NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE member=me AND roleid=r.role_name::regrole AND admin_option) THEN RAISE EXCEPTION 'CLEANUP_TARGET_GRANTOR_OR_ADMIN'; END IF;
 END LOOP;
 PERFORM set_config('oldham_cleanup.members',__MEMBERS__::text,true);
 PERFORM set_config('oldham_cleanup.functions',__FUNCTIONS__::text,true);
 PERFORM set_config('oldham_cleanup.schema',(SELECT to_jsonb(n)::text FROM pg_namespace n WHERE oid='public'::regnamespace),true);
END $pre$;
GRANT ingestion_storage_owner TO postgres WITH ADMIN FALSE, INHERIT FALSE, SET TRUE GRANTED BY postgres;
SET LOCAL ROLE ingestion_storage_owner;
LOCK TABLE public.ingestion_work_items,public.ingestion_work_attempts IN SHARE ROW EXCLUSIVE MODE;
DO $clean$
DECLARE ctl jsonb; expected jsonb:=$binding$__EXPECTED__$binding$::jsonb; ph text; g jsonb; a jsonb; wanted jsonb; n integer;
 authority constant text:='INGESTION_CHAIN_OLDHAM_STAGED_CAPTURE_E9D12874CFB5';
BEGIN
 IF current_user<>'ingestion_storage_owner' OR NOT pg_has_role(session_user,current_user,'SET') OR pg_has_role(session_user,current_user,'USAGE') THEN RAISE EXCEPTION 'CLEANUP_TEMP_PRIVILEGE'; END IF;
 SELECT outcome::jsonb INTO STRICT ctl FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE;
 -- The current stop is bound to the acknowledged Bolton recovery; historical package.stop remains generation 3.
 IF ctl->'global_stop' IS DISTINCT FROM '{"reason":"CONSUMED_SALFORD_GLOBAL_STOP","run":"38884069913"}'::jsonb OR ctl->>'manual_stop' IS DISTINCT FROM 'ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP' OR ctl->>'last_hard_stop' IS DISTINCT FROM 'ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP' OR ctl->'hard_stop_generation' IS DISTINCT FROM '5'::jsonb THEN RAISE EXCEPTION 'CLEANUP_CURRENT_STOP_DRIFT'; END IF;
 IF expected->'allowance'->'package'->'stop'->'hard_stop_generation' IS DISTINCT FROM '3'::jsonb THEN RAISE EXCEPTION 'CLEANUP_HISTORICAL_STOP'; END IF;
 ph:=encode(sha256(convert_to((expected->'allowance'->'package')::text,'UTF8')),'hex');
 expected:=replace(expected::text,'PACKAGE_HASH_COMPUTED_IN_POSTGRES',ph)::jsonb;g:=expected->'grant';a:=expected->'allowance';
 IF ctl->'grants'->authority IS DISTINCT FROM g OR ctl->'oldham_allowances'->authority IS DISTINCT FROM a OR (g->>'expires_at')::double precision>=extract(epoch FROM clock_timestamp()) THEN RAISE EXCEPTION 'CLEANUP_HISTORICAL_BINDING_OR_EXPIRY'; END IF;
 IF (SELECT coalesce(jsonb_agg(to_jsonb(w) ORDER BY key),'[]'::jsonb) FROM public.ingestion_work_items w WHERE key IN (SELECT jsonb_array_elements_text(g->'keys'))) IS DISTINCT FROM expected->'allowance'->'package'->'registration'->'rows' THEN RAISE EXCEPTION 'CLEANUP_HISTORICAL_WORK_DRIFT'; END IF;
 IF (SELECT count(*) FROM public.ingestion_work_items WHERE key IN ('3f0dba235de9b9efcd52ef3b281ba8c967491f57824404c695ed2b32fae4c045','e92a8e220bbbbcefb2425d6f97a60920bc447bc1fe097d600ea28e3e9d87588e') AND state='SAFETY_BLOCKED' AND phase='RECOVERED' AND fence=2 AND owner IS NULL AND lease_until IS NULL)<>2 THEN RAISE EXCEPTION 'CLEANUP_RECOVERY_DRIFT'; END IF;
 PERFORM set_config('oldham_cleanup.ledger',__LEDGER__::text,true);
 wanted:=jsonb_set(jsonb_set(ctl,ARRAY['grants',authority,'expires_at'],'0'::jsonb),ARRAY['oldham_allowances',authority,'revoked'],'true'::jsonb);
 PERFORM set_config('oldham_cleanup.expected_control',wanted::text,true);
 UPDATE public.ingestion_work_items SET outcome=wanted::json WHERE key=repeat('0',64);
 GET DIAGNOSTICS n=ROW_COUNT;IF n<>1 THEN RAISE EXCEPTION 'CLEANUP_CONTROL_COUNT'; END IF;
END $clean$;
RESET ROLE;
REVOKE ingestion_worker FROM ingestion_worker_login GRANTED BY postgres RESTRICT;
REVOKE ingestion_effect_broker FROM ingestion_effect_login GRANTED BY postgres RESTRICT;
REVOKE ingestion_storage_owner FROM postgres GRANTED BY postgres RESTRICT;
DO $post$
DECLARE before_members jsonb:=current_setting('oldham_cleanup.members')::jsonb; after_members jsonb; wanted_members jsonb;
 before_ledger jsonb:=current_setting('oldham_cleanup.ledger')::jsonb; expected_ledger jsonb; actual jsonb;
BEGIN
 SELECT coalesce(jsonb_agg(e ORDER BY (e->>'roleid')::oid,(e->>'member')::oid,(e->>'grantor')::oid),'[]'::jsonb) INTO wanted_members FROM jsonb_array_elements(before_members) e
 WHERE NOT (e->>'grantor'='postgres'::regrole::oid::text AND ((e->>'member'='ingestion_worker_login'::regrole::oid::text AND e->>'roleid'='ingestion_worker'::regrole::oid::text) OR (e->>'member'='ingestion_effect_login'::regrole::oid::text AND e->>'roleid'='ingestion_effect_broker'::regrole::oid::text)));
 after_members:=__MEMBERS__;
 IF current_user<>'postgres' OR after_members IS DISTINCT FROM wanted_members OR pg_has_role('postgres','ingestion_storage_owner','SET') OR pg_has_role('postgres','ingestion_storage_owner','USAGE') THEN RAISE EXCEPTION 'CLEANUP_MEMBERSHIP_POST'; END IF;
 IF __FUNCTIONS__ IS DISTINCT FROM current_setting('oldham_cleanup.functions')::jsonb OR (SELECT to_jsonb(n) FROM pg_namespace n WHERE oid='public'::regnamespace) IS DISTINCT FROM current_setting('oldham_cleanup.schema')::jsonb THEN RAISE EXCEPTION 'CLEANUP_UNRELATED_PRIVILEGES'; END IF;
 expected_ledger:=jsonb_set(before_ledger,'{items}',(SELECT jsonb_agg(CASE WHEN e->>'key'=repeat('0',64) THEN jsonb_set(e,'{outcome}',current_setting('oldham_cleanup.expected_control')::jsonb) ELSE e END ORDER BY e->>'key') FROM jsonb_array_elements(before_ledger->'items') e));
 actual:=__LEDGER__;
 IF actual IS DISTINCT FROM expected_ledger THEN RAISE EXCEPTION 'CLEANUP_LEDGER_POST'; END IF;
 IF EXISTS(SELECT 1 FROM pg_stat_activity WHERE usename IN ('ingestion_worker_login','ingestion_effect_login','ingestion_application_login','ingestion_recovery_login')) THEN RAISE EXCEPTION 'CLEANUP_SESSIONS_POST'; END IF;
 RAISE NOTICE 'OLDHAM_CLEANUP_POSTCONDITIONS_VERIFIED_NOT_YET_COMMITTED';
END $post$;
SELECT 'oldham_cleanup' AS section,'INGESTION_CHAIN_OLDHAM_STAGED_CAPTURE_E9D12874CFB5' AS authority,'EXACT_AUTHORITY_REVOKED_TWO_MEMBERSHIPS_REMOVED_STOP_PRESERVED' AS disposition;
COMMIT;
SELECT 'OLDHAM_CLEANUP_COMMIT_ACKNOWLEDGED' AS disposition;
"""
for a,b in [('__MEMBERS__',members),('__FUNCTIONS__',functions),('__LEDGER__',ledger),('__EXPECTED__',expected)]:base=base.replace(a,b)
sys.stdout.write(base)
