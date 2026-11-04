"""Private bounded pilot evidence in the existing database. No provider/token lookup."""
import hashlib,json,re
from app.ingestion.ledger import Denied
BACKEND='POSTGRES_PILOT_V1'
SOURCE_LIMIT=512*1024
RUN_LIMIT=2*1024*1024
NAMES=('capture-1/source.json','capture-2/source.json','final/result-before-publication.json','final/events-before-publication.json')
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def path(period,run,name):return f'docs/design/ingestion-operational-execution-daily-intake/{period}/{run}/{name}'
def validate_descriptor(v,*,sha=None,size=None):
 if not isinstance(v,dict) or v.get('backend')!=BACKEND or set(v)!={'backend','period','run_id','name','path','sha256','bytes','readback_verified'}:raise Denied('DATABASE_EVIDENCE_DESCRIPTOR')
 if not re.fullmatch(r'[A-Za-z0-9_-]{1,60}',v['period']) or not re.fullmatch('[a-f0-9]{32}',v['run_id']) or v['name'] not in NAMES or v['path']!=path(v['period'],v['run_id'],v['name']) or not re.fullmatch('[a-f0-9]{64}',v['sha256']) or type(v['bytes']) is not int or not 0<v['bytes']<=RUN_LIMIT or v['readback_verified'] is not True:raise Denied('DATABASE_EVIDENCE_DESCRIPTOR')
 if sha is not None and v['sha256']!=sha or size is not None and v['bytes']!=size:raise Denied('DATABASE_EVIDENCE_CONTENT_BINDING')
 if v['name'].startswith('capture-') and v['bytes']>SOURCE_LIMIT:raise Denied('SOURCE_AUDIT_BOUND')
 return v

def store(raw,period,run,name,write,read):
 """Exactly one write, then a separately completed independent read; no retry."""
 if type(raw) is not bytes or name not in NAMES or not 0<len(raw)<= (SOURCE_LIMIT if name.startswith('capture-') else RUN_LIMIT):raise Denied('DATABASE_EVIDENCE_BOUND')
 sha=hashlib.sha256(raw).hexdigest()
 ack=write(period,run,name,raw)
 expected=dict(backend=BACKEND,period=period,run_id=run,name=name,path=path(period,run,name),sha256=sha,bytes=len(raw),readback_verified=True)
 if ack!=dict(expected,readback_verified=False):raise Denied('DATABASE_EVIDENCE_WRITE_ACK_RECONCILE')
 got=read(period,run,name)
 if type(got) is not bytes or got!=raw or hashlib.sha256(got).hexdigest()!=sha:raise Denied('DATABASE_EVIDENCE_READBACK')
 return validate_descriptor(expected,sha=sha,size=len(raw))

TABLE_SQL=r'''
CREATE TABLE public.ingestion_run_evidence (
 period text NOT NULL CHECK (period ~ '^[A-Za-z0-9_-]{1,60}$'),
 run_id text NOT NULL CHECK (run_id ~ '^[a-f0-9]{32}$'),
 name text NOT NULL CHECK (name IN ('capture-1/source.json','capture-2/source.json','final/result-before-publication.json','final/events-before-publication.json') OR name ~ '^owner/state-[0-9]{3}$'),
 body bytea NOT NULL CHECK (octet_length(body)>0 AND octet_length(body)<=2097152),
 sha256 text NOT NULL CHECK (sha256 ~ '^[a-f0-9]{64}$' AND sha256=encode(sha256(body),'hex')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(period,run_id,name),
 CHECK (name NOT LIKE 'capture-%' OR octet_length(body)<=524288)
);
ALTER TABLE public.ingestion_run_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ingestion_run_evidence FORCE ROW LEVEL SECURITY;
CREATE POLICY ingestion_evidence_owner ON public.ingestion_run_evidence TO ingestion_storage_owner USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE public.ingestion_run_evidence FROM PUBLIC;
'''
WRITE_SQL=r'''
CREATE FUNCTION public.ingestion_intake_evidence_write(p_period text,p_run text,p_name text,p_body bytea)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $evidence_write$
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
 SELECT * INTO prior FROM public.ingestion_run_evidence WHERE period=p_period AND run_id=p_run AND name=p_name;
 IF FOUND THEN
  IF prior.body IS DISTINCT FROM p_body THEN RAISE EXCEPTION 'EVIDENCE_CONFLICT_NO_OVERWRITE'; END IF;
  RETURN jsonb_build_object('backend','POSTGRES_PILOT_V1','period',p_period,'run_id',p_run,'name',p_name,
   'path','docs/design/ingestion-operational-execution-daily-intake/'||p_period||'/'||p_run||'/'||p_name,
   'sha256',prior.sha256,'bytes',octet_length(prior.body),'readback_verified',false);
 END IF;
 IF run->>'state'<>'OPEN' OR t>(policy->>'expires_at')::double precision+185 THEN RAISE EXCEPTION 'EVIDENCE_RUN_CLOSED'; END IF;
 IF p_name LIKE 'capture-%' AND (t>(policy->>'expires_at')::double precision OR NOT EXISTS (
 SELECT 1 FROM jsonb_each(ctl->'grants') g JOIN public.ingestion_work_items w ON w.key=g.value->>'capture_key'
 WHERE g.value->>'intake_period'=p_period AND g.value->>'intake_run'=p_run AND w.phase='SOURCE_INTENT'
 AND g.value->'execution_binding'=policy->'execution_binding' AND (g.value->>'expires_at')::double precision>t
 AND (convert_from(p_body,'UTF8')::jsonb)->'requested_interval'=jsonb_build_array(w.subject::jsonb->>'start',w.subject::jsonb->>'end')
 AND ((w.subject::jsonb->>'council'='tameside' AND w.subject::jsonb->>'semantics'='RECEIVED' AND (convert_from(p_body,'UTF8')::jsonb)->>'council'='tameside' AND (convert_from(p_body,'UTF8')::jsonb)->>'date_semantics'='RECEIVED')
 OR (w.subject::jsonb->>'council'='manchester' AND w.subject::jsonb->>'semantics'='VALIDATED' AND (convert_from(p_body,'UTF8')::jsonb)->>'case'='discovery_manchester_ui_window'))
 )) THEN RAISE EXCEPTION 'EVIDENCE_SOURCE_AUTHORITY'; END IF;
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
END $evidence_write$;
REVOKE ALL ON FUNCTION public.ingestion_intake_evidence_write(text,text,text,bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.ingestion_intake_evidence_write(text,text,text,bytea) TO ingestion_worker;
'''
READ_SQL=r'''
CREATE FUNCTION public.ingestion_intake_evidence_read(p_period text,p_run text,p_name text)
RETURNS bytea LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $evidence_read$
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
END $evidence_read$;
REVOKE ALL ON FUNCTION public.ingestion_intake_evidence_read(text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.ingestion_intake_evidence_read(text,text,text) TO ingestion_worker,postgres;
'''

OWNER_SQL=r'''
CREATE FUNCTION public.ingestion_intake_owner_state(p_period text,p_run text,p_previous text,p_body bytea)
RETURNS TABLE(ordinal integer,body bytea,sha256 text) LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $owner_state$
DECLARE prior public.ingestion_run_evidence%ROWTYPE; n integer; h text;
BEGIN
 IF session_user<>'postgres' THEN RAISE EXCEPTION 'OWNER_STATE_OWNER_ONLY' USING ERRCODE='42501'; END IF;
 IF p_period NOT IN ('b-dbpilot-20261027-1102-01_owner','b-dbpilot-20261027-1102-02_owner','b-dbpilot-20261027-1102-03_owner','b-dbpilot-20261027-1102-04_owner','b-dbpilot-20261027-1102-05_owner') OR p_run<>substr(encode(sha256(convert_to(p_period,'UTF8')),'hex'),1,32) THEN RAISE EXCEPTION 'OWNER_STATE_EXACT_PILOT'; END IF;
 -- Owner journal transactions must never wait for the period/controller lock:
 -- they preserve intent before that transaction starts, or ack after COMMIT.
 IF NOT pg_try_advisory_xact_lock(1886547824,20261103) THEN RAISE EXCEPTION 'OWNER_STATE_BUSY'; END IF;
 SELECT * INTO prior FROM public.ingestion_run_evidence d WHERE d.period=p_period AND d.run_id=p_run AND d.name LIKE 'owner/state-%' ORDER BY d.name DESC LIMIT 1;
 IF p_body IS NULL THEN
  IF prior.name IS NOT NULL THEN RETURN QUERY SELECT substring(prior.name from 13)::integer,prior.body,prior.sha256; END IF;
  RETURN;
 END IF;
 IF octet_length(p_body) NOT BETWEEN 1 AND 32768 THEN RAISE EXCEPTION 'OWNER_STATE_VAULT_BOUND'; END IF;
 h:=encode(sha256(p_body),'hex');
 IF prior.name IS NOT NULL AND prior.body=p_body THEN
  RETURN QUERY SELECT substring(prior.name from 13)::integer,prior.body,prior.sha256;RETURN;
 END IF;
 IF coalesce(prior.sha256,'') IS DISTINCT FROM p_previous THEN RAISE EXCEPTION 'OWNER_STATE_CONCURRENT_OR_UNCERTAIN'; END IF;
 n:=CASE WHEN prior.name IS NULL THEN 0 ELSE substring(prior.name from 13)::integer+1 END;
 IF n>=64 THEN RAISE EXCEPTION 'OWNER_STATE_HISTORY_BOUND'; END IF;
 INSERT INTO public.ingestion_run_evidence(period,run_id,name,body,sha256) VALUES(p_period,p_run,'owner/state-'||lpad(n::text,3,'0'),p_body,h);
 RETURN QUERY SELECT n,p_body,h;
END $owner_state$;
REVOKE ALL ON FUNCTION public.ingestion_intake_owner_state(text,text,text,bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.ingestion_intake_owner_state(text,text,text,bytea) TO postgres;
'''

def definition_sql():return TABLE_SQL+WRITE_SQL+READ_SQL+OWNER_SQL

FINISH_GUARD_SQL=r'''
   IF e->>'evidence_backend'='POSTGRES_PILOT_V1' THEN
    IF p->'publication'->>'backend' IS DISTINCT FROM 'POSTGRES_PILOT_V1'
     OR p->'publication'->>'period' IS DISTINCT FROM a OR p->'publication'->>'run_id' IS DISTINCT FROM p->>'run_id'
     OR p->'publication'->>'name' IS DISTINCT FROM 'final/result-before-publication.json'
     OR NOT EXISTS(SELECT 1 FROM public.ingestion_run_evidence d WHERE d.period=a AND d.run_id=p->>'run_id'
       AND d.name='final/result-before-publication.json' AND d.sha256=p->'publication'->>'sha256'
       AND d.sha256=encode(sha256(d.body),'hex') AND octet_length(d.body)=(p->'publication'->>'bytes')::integer
       AND (convert_from(d.body,'UTF8')::jsonb)->>'period'=a
       AND (convert_from(d.body,'UTF8')::jsonb)->>'run_id'=p->>'run_id'
       AND (convert_from(d.body,'UTF8')::jsonb)->>'status'=p->>'status'
       AND (convert_from(d.body,'UTF8')::jsonb)->'execution_binding'=e->'execution_binding'
       AND (convert_from(d.body,'UTF8')::jsonb)->>'cleanup'='CLOSED'
       AND (convert_from(d.body,'UTF8')::jsonb)->>'authority_closure'='INVALIDATED'
       AND (convert_from(d.body,'UTF8')::jsonb)->>'github_publication'='NOT_REQUESTED')
     OR NOT EXISTS(SELECT 1 FROM public.ingestion_run_evidence d WHERE d.period=a AND d.run_id=p->>'run_id'
       AND d.name='final/events-before-publication.json' AND d.sha256=encode(sha256(d.body),'hex')
       AND jsonb_typeof(convert_from(d.body,'UTF8')::jsonb)='array')
     OR EXISTS(SELECT 1 FROM jsonb_each(e->'days'->(ctl->'intake_run'->>'day')) x
       JOIN public.ingestion_work_items w ON w.key=x.value#>>'{}'
       WHERE w.state IN ('COMPLETE','DEFERRED') AND NOT EXISTS(
        SELECT 1 FROM public.ingestion_run_evidence d WHERE d.period=a AND d.run_id=p->>'run_id'
         AND d.name IN ('capture-1/source.json','capture-2/source.json')
         AND d.sha256=w.checkpoint::jsonb->>'source_sha256'
         AND d.sha256=encode(sha256(d.body),'hex')
         AND (((convert_from(d.body,'UTF8')::jsonb)->>'council'=w.subject::jsonb->>'council' AND w.subject::jsonb->>'council'='tameside') OR (w.subject::jsonb->>'council'='manchester' AND (convert_from(d.body,'UTF8')::jsonb)->>'case'='discovery_manchester_ui_window'))
         AND (convert_from(d.body,'UTF8')::jsonb)->'requested_interval'=jsonb_build_array(w.subject::jsonb->>'start',w.subject::jsonb->>'end')
         AND (w.subject::jsonb->>'council'<>'manchester' OR w.state<>'COMPLETE' OR (convert_from(d.body,'UTF8')::jsonb)->'applied_interval'=jsonb_build_array(w.subject::jsonb->>'start',w.subject::jsonb->>'end'))
         AND w.checkpoint::jsonb->'durable_archive'->>'backend'='POSTGRES_PILOT_V1'
         AND w.checkpoint::jsonb->'durable_archive'->>'period'=a
         AND w.checkpoint::jsonb->'durable_archive'->>'run_id'=p->>'run_id'
         AND w.checkpoint::jsonb->'durable_archive'->>'name'=d.name
         AND (w.checkpoint::jsonb->'durable_archive'->>'bytes')::integer=octet_length(d.body)
       ))
    THEN RAISE EXCEPTION 'INTAKE_DATABASE_EVIDENCE_NOT_VERIFIED'; END IF;
   ELSIF p->'publication' ? 'backend' THEN RAISE EXCEPTION 'INTAKE_EVIDENCE_BACKEND_NOT_AUTHORISED';
   END IF;
'''

PREDECESSOR_REGISTER_SHA='dba6b809c50b9bd937b2f509fc05c20de9d69499ca4394e9007ef3af196b481c'
def function_contracts():
    contracts=[]
    for name,source,tag,grantees in (
        ('ingestion_intake_evidence_write',WRITE_SQL,'evidence_write',['ingestion_storage_owner','ingestion_worker']),
        ('ingestion_intake_evidence_read',READ_SQL,'evidence_read',['ingestion_storage_owner','ingestion_worker','postgres']),
        ('ingestion_intake_owner_state',OWNER_SQL,'owner_state',['ingestion_storage_owner','postgres'])):
        body=source.split('$'+tag+'$',2)[1]
        contracts.append(dict(name=name,sha256=hashlib.sha256(body.encode()).hexdigest(),grantees=sorted(grantees)))
    return contracts

def verify_inventory(c):
    from .intake_owner import require
    for contract in function_contracts():
        rows=c.execute("""SELECT encode(sha256(convert_to(p.prosrc,'UTF8')),'hex'),p.proowner::regrole::text,p.prosecdef,p.proconfig,
         (SELECT array_agg(a.grantee::regrole::text ORDER BY a.grantee::regrole::text) FROM aclexplode(p.proacl) a),
         (SELECT bool_or(a.is_grantable OR a.privilege_type<>'EXECUTE' OR a.grantor<>'ingestion_storage_owner'::regrole) FROM aclexplode(p.proacl) a)
         FROM pg_proc p WHERE p.pronamespace='public'::regnamespace AND p.proname=%s""",(contract['name'],)).fetchall()
        require(rows==[(contract['sha256'],'ingestion_storage_owner',True,['search_path=pg_catalog'],contract['grantees'],False)],'DATABASE_EVIDENCE_FUNCTION_OR_ACL_BINDING')
    row=c.execute("""SELECT c.relowner::regrole::text,c.relrowsecurity,c.relforcerowsecurity,
     (SELECT count(*) FROM aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a WHERE a.grantee<>c.relowner)
     FROM pg_class c WHERE c.oid='public.ingestion_run_evidence'::regclass""").fetchone()
    require(row==('ingestion_storage_owner',True,True,0),'DATABASE_EVIDENCE_TABLE_PRIVILEGES')

def migration_sql():
    """One guarded additive migration, exact installed predecessor, no login/data effects."""
    from .intake_policy import policy_sql
    from .operational_owner import Owner
    text=policy_sql();start=text.index('CREATE OR REPLACE FUNCTION public.ingestion_register_bolton_exception(');end=text.index('$register$;',start)+len('$register$;');register=text[start:end]
    expected=hashlib.sha256(Owner.daily_intake_inventory()['ingestion_register_bolton_exception'].encode()).hexdigest()
    contracts=function_contracts()
    return r'''
BEGIN;
SET LOCAL statement_timeout='10s';SET LOCAL lock_timeout='3s';SET LOCAL idle_in_transaction_session_timeout='20s';
DO $pre$ BEGIN
 IF current_user<>'postgres' OR session_user<>'postgres' OR current_setting('server_version_num')::int<170000
 OR pg_has_role(current_user,'ingestion_storage_owner','SET') OR pg_has_role(current_user,'ingestion_storage_owner','USAGE')
 OR has_schema_privilege('ingestion_storage_owner','public','CREATE')
 OR (SELECT count(*) FROM pg_auth_members WHERE roleid='ingestion_storage_owner'::regrole AND member=current_user::regrole AND grantor<>'postgres'::regrole AND admin_option AND NOT inherit_option AND NOT set_option)<>1
 OR (SELECT count(*) FROM pg_auth_members WHERE roleid='ingestion_storage_owner'::regrole AND member=current_user::regrole)<>1
 OR NOT has_schema_privilege(current_user,'public','CREATE WITH GRANT OPTION')
 OR to_regclass('public.ingestion_run_evidence') IS NOT NULL
 OR EXISTS(SELECT 1 FROM pg_proc WHERE pronamespace='public'::regnamespace AND proname IN ('ingestion_intake_evidence_write','ingestion_intake_evidence_read','ingestion_intake_owner_state'))
 OR (SELECT encode(sha256(convert_to(prosrc,'UTF8')),'hex') FROM pg_proc WHERE oid='public.ingestion_register_bolton_exception(jsonb)'::regprocedure) IS DISTINCT FROM '__PRE__'
 OR EXISTS(SELECT 1 FROM pg_roles r JOIN pg_authid a ON r.rolname=a.rolname WHERE r.rolname IN ('ingestion_worker_login','ingestion_effect_login') AND (r.rolcanlogin OR a.rolpassword IS NOT NULL))
 OR EXISTS(SELECT 1 FROM pg_auth_members WHERE member=ANY(ARRAY['ingestion_worker_login'::regrole,'ingestion_effect_login'::regrole]))
 OR EXISTS(SELECT 1 FROM pg_stat_activity WHERE usename IN ('ingestion_worker_login','ingestion_effect_login'))
 THEN RAISE EXCEPTION 'DATABASE_EVIDENCE_MIGRATION_PRECONDITION'; END IF;
END $pre$;
CREATE TEMP TABLE evidence_before ON COMMIT DROP AS SELECT
 (SELECT jsonb_agg(to_jsonb(m) ORDER BY roleid,member,grantor) FROM pg_auth_members m) AS memberships,
 (SELECT nspacl::text FROM pg_namespace WHERE nspname='public') AS schema_acl,
 (SELECT proacl::text FROM pg_proc WHERE oid='public.ingestion_register_bolton_exception(jsonb)'::regprocedure) AS registrar_acl,
 (SELECT jsonb_build_object('items',(SELECT jsonb_agg(to_jsonb(w) ORDER BY key) FROM public.ingestion_work_items w),
  'attempts',(SELECT jsonb_agg(to_jsonb(a) ORDER BY work_key,fence) FROM public.ingestion_work_attempts a))) AS ledger;
DO $stops$ DECLARE ctl jsonb; BEGIN
 SELECT outcome::jsonb INTO STRICT ctl FROM public.ingestion_work_items WHERE key=repeat('0',64);
 IF ctl->'global_stop' IS DISTINCT FROM 'null'::jsonb OR ctl->>'manual_stop' IS NOT NULL
 OR ctl->>'hard_stop_generation'<>'5' OR ctl->>'last_hard_stop'<>'ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP'
 OR EXISTS(SELECT 1 FROM public.ingestion_work_items WHERE phase IN ('SOURCE_INTENT','WRITE_INTENT') OR state='PERSISTENCE_UNCERTAIN')
 OR (ctl ? 'intake_run' AND ctl->'intake_run'->>'state' IS DISTINCT FROM 'VERIFIED')
 THEN RAISE EXCEPTION 'DATABASE_EVIDENCE_UNRESOLVED_STATE'; END IF;
END $stops$;
GRANT ingestion_storage_owner TO postgres WITH ADMIN FALSE, INHERIT FALSE, SET TRUE GRANTED BY postgres;
GRANT CREATE ON SCHEMA public TO ingestion_storage_owner;
SET LOCAL ROLE ingestion_storage_owner;
LOCK TABLE public.ingestion_work_items,public.ingestion_work_attempts IN SHARE ROW EXCLUSIVE MODE;
RESET ROLE;
UPDATE pg_temp.evidence_before SET ledger=(SELECT jsonb_build_object('items',(SELECT jsonb_agg(to_jsonb(w) ORDER BY key) FROM public.ingestion_work_items w),
  'attempts',(SELECT jsonb_agg(to_jsonb(a) ORDER BY work_key,fence) FROM public.ingestion_work_attempts a)));
SET LOCAL ROLE ingestion_storage_owner;
''' .replace('__PRE__',PREDECESSOR_REGISTER_SHA)+definition_sql()+register+r'''
RESET ROLE;
REVOKE CREATE ON SCHEMA public FROM ingestion_storage_owner;
REVOKE ingestion_storage_owner FROM postgres GRANTED BY postgres RESTRICT;
DO $post$ DECLARE b record; required jsonb; BEGIN
 SELECT * INTO STRICT b FROM evidence_before;
 IF pg_has_role(current_user,'ingestion_storage_owner','SET') OR pg_has_role(current_user,'ingestion_storage_owner','USAGE')
 OR has_schema_privilege('ingestion_storage_owner','public','CREATE')
 OR b.memberships IS DISTINCT FROM (SELECT jsonb_agg(to_jsonb(m) ORDER BY roleid,member,grantor) FROM pg_auth_members m)
 OR b.schema_acl IS DISTINCT FROM (SELECT nspacl::text FROM pg_namespace WHERE nspname='public')
 OR b.registrar_acl IS DISTINCT FROM (SELECT proacl::text FROM pg_proc WHERE oid='public.ingestion_register_bolton_exception(jsonb)'::regprocedure)
 OR b.ledger IS DISTINCT FROM (SELECT jsonb_build_object('items',(SELECT jsonb_agg(to_jsonb(w) ORDER BY key) FROM public.ingestion_work_items w),
 'attempts',(SELECT jsonb_agg(to_jsonb(a) ORDER BY work_key,fence) FROM public.ingestion_work_attempts a)))
 OR (SELECT encode(sha256(convert_to(prosrc,'UTF8')),'hex') FROM pg_proc WHERE oid='public.ingestion_register_bolton_exception(jsonb)'::regprocedure) IS DISTINCT FROM '__AFTER__'
 OR EXISTS(SELECT 1 FROM pg_class c CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a WHERE c.oid='public.ingestion_run_evidence'::regclass AND a.grantee<>c.relowner)
 THEN RAISE EXCEPTION 'DATABASE_EVIDENCE_EXACT_CLEANUP_OR_PRESERVATION'; END IF;
 FOR required IN SELECT value FROM jsonb_array_elements('__CONTRACTS__'::jsonb) LOOP
  IF (SELECT count(*) FROM pg_proc p WHERE p.pronamespace='public'::regnamespace AND p.proname=required->>'name')<>1
   OR NOT EXISTS(SELECT 1 FROM pg_proc p WHERE p.pronamespace='public'::regnamespace AND p.proname=required->>'name'
    AND p.proowner='ingestion_storage_owner'::regrole AND p.prosecdef AND p.proconfig=ARRAY['search_path=pg_catalog']
    AND encode(sha256(convert_to(p.prosrc,'UTF8')),'hex')=required->>'sha256'
    AND (SELECT jsonb_agg(a.grantee::regrole::text ORDER BY a.grantee::regrole::text) FROM aclexplode(p.proacl) a)=required->'grantees'
    AND NOT EXISTS(SELECT 1 FROM aclexplode(p.proacl) a WHERE a.is_grantable OR a.privilege_type<>'EXECUTE' OR a.grantor<>'ingestion_storage_owner'::regrole))
  THEN RAISE EXCEPTION 'DATABASE_EVIDENCE_FUNCTION_OR_ACL_BINDING'; END IF;
 END LOOP;
END $post$;
COMMIT;
SELECT 'DATABASE_EVIDENCE_MIGRATION_COMMIT_ACKNOWLEDGED' AS status;
''' .replace('__AFTER__',expected).replace('__CONTRACTS__',json.dumps(contracts))
