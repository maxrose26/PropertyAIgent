-- REVIEW PACKAGE ONLY. Explicit administrator transaction; never app startup.
-- First install only. Existing objects/roles must cause failure and reconciliation.
BEGIN;
SET LOCAL search_path=pg_catalog,public;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='10s';
CREATE ROLE ingestion_storage_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE ROLE ingestion_storage_operator NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE ROLE ingestion_worker NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE ROLE ingestion_authority_issuer NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE ROLE ingestion_barrier_releaser NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
GRANT USAGE ON SCHEMA public TO ingestion_storage_owner, ingestion_storage_operator, ingestion_worker;

CREATE TABLE public.ingestion_work_items (
	key VARCHAR(64) NOT NULL, 
	subject JSON NOT NULL, 
	task VARCHAR(32) NOT NULL, 
	contract VARCHAR(100) NOT NULL, 
	revision VARCHAR(100) NOT NULL, 
	dependencies JSON NOT NULL, 
	priority INTEGER NOT NULL, 
	eligible_at FLOAT NOT NULL, 
	state VARCHAR(32) NOT NULL, 
	reason VARCHAR(200), 
	next_action VARCHAR(100) NOT NULL, 
	limits JSON NOT NULL, 
	authority VARCHAR(100), 
	attempt_count INTEGER NOT NULL, 
	max_attempts INTEGER NOT NULL, 
	fence INTEGER NOT NULL, 
	owner VARCHAR(100), 
	lease_until FLOAT, 
	phase VARCHAR(32) NOT NULL, 
	checkpoint JSON, 
	outcome JSON, 
	PRIMARY KEY (key), 
	CHECK (attempt_count >= 0 AND max_attempts BETWEEN 1 AND 3), 
	CHECK (priority BETWEEN 0 AND 100)
)

;
ALTER TABLE public.ingestion_work_items OWNER TO ingestion_storage_owner;
REVOKE ALL ON public.ingestion_work_items FROM PUBLIC;
DO $acl$ DECLARE r record; BEGIN
 FOR r IN SELECT DISTINCT p.rolname FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a JOIN pg_roles p ON p.oid=a.grantee WHERE c.oid='public.ingestion_work_items'::regclass AND p.rolname<>'ingestion_storage_owner' LOOP
 EXECUTE format('REVOKE ALL ON TABLE public.ingestion_work_items FROM %I',r.rolname); END LOOP; END $acl$;
ALTER TABLE public.ingestion_work_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ingestion_work_items FORCE ROW LEVEL SECURITY;
CREATE POLICY storage_owner ON public.ingestion_work_items TO ingestion_storage_owner USING (true) WITH CHECK (true);
CREATE POLICY storage_read ON public.ingestion_work_items FOR SELECT TO ingestion_worker, ingestion_storage_operator USING (true);
GRANT SELECT ON public.ingestion_work_items TO ingestion_worker, ingestion_storage_operator;

CREATE TABLE public.ingestion_work_attempts (
	work_key VARCHAR(64) NOT NULL, 
	fence INTEGER NOT NULL, 
	owner VARCHAR(100) NOT NULL, 
	started_at FLOAT NOT NULL, 
	finished_at FLOAT, 
	authority VARCHAR(100) NOT NULL, 
	phase VARCHAR(32) NOT NULL, 
	outcome JSON, 
	checkpoint JSON, 
	PRIMARY KEY (work_key, fence), 
	FOREIGN KEY(work_key) REFERENCES public.ingestion_work_items (key)
)

;
ALTER TABLE public.ingestion_work_attempts OWNER TO ingestion_storage_owner;
REVOKE ALL ON public.ingestion_work_attempts FROM PUBLIC;
DO $acl$ DECLARE r record; BEGIN
 FOR r IN SELECT DISTINCT p.rolname FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a JOIN pg_roles p ON p.oid=a.grantee WHERE c.oid='public.ingestion_work_attempts'::regclass AND p.rolname<>'ingestion_storage_owner' LOOP
 EXECUTE format('REVOKE ALL ON TABLE public.ingestion_work_attempts FROM %I',r.rolname); END LOOP; END $acl$;
ALTER TABLE public.ingestion_work_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ingestion_work_attempts FORCE ROW LEVEL SECURITY;
CREATE POLICY storage_owner ON public.ingestion_work_attempts TO ingestion_storage_owner USING (true) WITH CHECK (true);
CREATE POLICY storage_read ON public.ingestion_work_attempts FOR SELECT TO ingestion_worker, ingestion_storage_operator USING (true);
GRANT SELECT ON public.ingestion_work_attempts TO ingestion_worker, ingestion_storage_operator;
INSERT INTO public.ingestion_work_items SELECT * FROM json_populate_record(NULL::public.ingestion_work_items,'{"attempt_count":0,"authority":null,"checkpoint":null,"contract":"v1","dependencies":[],"eligible_at":0,"fence":0,"key":"0000000000000000000000000000000000000000000000000000000000000000","lease_until":null,"limits":{},"max_attempts":1,"next_action":"OPERATOR_REVIEW","outcome":{"global_stop":{"reason":"CONSUMED_SALFORD_GLOBAL_STOP","run":"38884069913"},"grants":{}},"owner":null,"phase":"IDLE","priority":0,"reason":null,"revision":"v1","state":"CONTROL","subject":{"kind":"CONTROL"},"task":"CONTROL"}'::json);
CREATE FUNCTION public.ingestion_seed_storage_test() RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $fn$
DECLARE n integer; expected jsonb; actual jsonb;
BEGIN
 PERFORM 1 FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE;
 IF (SELECT outcome::jsonb->'grants' FROM public.ingestion_work_items WHERE key=repeat('0',64)) <> '{}'::jsonb
 OR (SELECT outcome::jsonb->'global_stop'->>'reason' FROM public.ingestion_work_items WHERE key=repeat('0',64)) IS DISTINCT FROM 'CONSUMED_SALFORD_GLOBAL_STOP'
 OR EXISTS(SELECT 1 FROM public.ingestion_work_attempts) THEN RAISE EXCEPTION 'STORAGE_PRECONDITION'; END IF;
 expected := '{"attempt_count":0,"authority":null,"checkpoint":{"evidence_commit":"e2db0277b99c3b8ff57b5fb808b6c83aa4643e7c","live_allowance":{"source_calls":0,"writes":0},"retained_evidence":{"checkpoint_sha256":"a2345cf136fc92abf13bb55772f5c14a7a299b7f2b9cb0b89fe6037ccdb8a10e","durable_reference":{"bytes":4298,"commit":"e2db0277b99c3b8ff57b5fb808b6c83aa4643e7c","path":"docs/design/stage4-r0-execution/metadata-rollout-result-20261016/scopes/00/artifact/checkpoints/000.json","sha256":"a2345cf136fc92abf13bb55772f5c14a7a299b7f2b9cb0b89fe6037ccdb8a10e"},"run":"38884069913"}},"contract":"storage-acceptance-blocked-v1","dependencies":[],"eligible_at":0,"fence":0,"key":"c1f526eed20e392382001cad4d28eb5bc16e5d1c0f92adb282fe7b1cc775f3f3","lease_until":null,"limits":{"aggregate_rss":1610612736,"audit_bytes":2097152,"bytes":20971520,"outer_seconds":60,"pages":6,"requests":80,"rows":60,"source_rss":1073741824,"worker_seconds":45},"max_attempts":1,"next_action":"REVIEW_ONLY","outcome":null,"owner":null,"phase":"IDLE","priority":0,"reason":"CONSUMED_SALFORD_GLOBAL_STOP","revision":"20261016","state":"SAFETY_BLOCKED","subject":{"council":"salford","end":"2026-10-14","kind":"DISCOVERY_SCOPE","semantics":"VALIDATED","start":"2026-10-08"},"task":"LISTING_METADATA"}'::jsonb;
 INSERT INTO public.ingestion_work_items SELECT * FROM json_populate_record(NULL::public.ingestion_work_items,expected::json) ON CONFLICT (key) DO NOTHING;
 SELECT to_jsonb(w) INTO actual FROM public.ingestion_work_items w WHERE key=expected->>'key';
 IF actual IS DISTINCT FROM expected THEN RAISE EXCEPTION 'CONFLICTING_STORAGE_ITEM'; END IF;
 expected := '{"attempt_count":0,"authority":null,"checkpoint":{"evidence_commit":"e2db0277b99c3b8ff57b5fb808b6c83aa4643e7c","live_allowance":{"source_calls":0,"writes":0},"retained_evidence":{"checkpoint_sha256":"d2d7349ea85710aadb804c8a547934d4d034f0a9984a9f19c1a58586117f6da1","durable_reference":{"bytes":298338,"commit":"e2db0277b99c3b8ff57b5fb808b6c83aa4643e7c","path":"docs/design/stage4-r0-execution/manchester-screening-result-20261016/remaining-coverage-ledger.json","sha256":"188f70940318c4114bdbfd1bd0615699fb2e4ebabc72f4203e0bebeb52640f30"},"record_id":"a0rSl00000tnpbVIAQ"}},"contract":"storage-acceptance-blocked-v1","dependencies":[],"eligible_at":0,"fence":0,"key":"0eff5d22b28ee79039d151382ac0321e26350b9ccb10c58f46b82050dab82bf9","lease_until":null,"limits":{"aggregate_rss":1610612736,"audit_bytes":2097152,"bytes":20971520,"outer_seconds":60,"pages":6,"requests":80,"rows":60,"source_rss":1073741824,"worker_seconds":45},"max_attempts":1,"next_action":"REVIEW_ONLY","outcome":null,"owner":null,"phase":"IDLE","priority":0,"reason":"ROCHDALE_SOURCE_QUALIFICATION_NOT_EXECUTED","revision":"20261016","state":"UNSUPPORTED_CONTRACT","subject":{"council":"rochdale","kind":"APPLICATION","reference":"PL/2026/0882"},"task":"LISTING_METADATA"}'::jsonb;
 INSERT INTO public.ingestion_work_items SELECT * FROM json_populate_record(NULL::public.ingestion_work_items,expected::json) ON CONFLICT (key) DO NOTHING;
 SELECT to_jsonb(w) INTO actual FROM public.ingestion_work_items w WHERE key=expected->>'key';
 IF actual IS DISTINCT FROM expected THEN RAISE EXCEPTION 'CONFLICTING_STORAGE_ITEM'; END IF;
 expected := '{"attempt_count":0,"authority":null,"checkpoint":{"evidence_commit":"e2db0277b99c3b8ff57b5fb808b6c83aa4643e7c","live_allowance":{"source_calls":0,"writes":0},"retained_evidence":{"application_id_context":1507,"durable_reference":{"bytes":1805,"commit":"e2db0277b99c3b8ff57b5fb808b6c83aa4643e7c","path":"docs/design/stage4-r0-execution/narrow-continuation-20261016/recovery-screening-plan-20261016/artifacts/oldham/checkpoints/000.json","sha256":"bf909d799d7f97fd5250ab26a78f65309a1d869e4a9faf231b16a77e404763d0"},"outcome":"COMMITTED_PENDING_IDENTITY; FACTS_WITHHELD","run":"38871588708"}},"contract":"storage-acceptance-blocked-v1","dependencies":[],"eligible_at":0,"fence":0,"key":"16c9c4d1fb67d844ddb29b092217c3b5a7c42eb8ba63e296611ce2f617779f6d","lease_until":null,"limits":{"aggregate_rss":1610612736,"audit_bytes":2097152,"bytes":20971520,"outer_seconds":60,"pages":6,"requests":80,"rows":60,"source_rss":1073741824,"worker_seconds":45},"max_attempts":1,"next_action":"REVIEW_ONLY","outcome":null,"owner":null,"phase":"IDLE","priority":0,"reason":"COUPLED_FACTS_WITHHELD_NO_SUPPORTED_DECISION","revision":"20261016","state":"UNSUPPORTED_CONTRACT","subject":{"council":"oldham","kind":"APPLICATION","reference":"NMA/356901/26"},"task":"FACTUAL_REFRESH"}'::jsonb;
 INSERT INTO public.ingestion_work_items SELECT * FROM json_populate_record(NULL::public.ingestion_work_items,expected::json) ON CONFLICT (key) DO NOTHING;
 SELECT to_jsonb(w) INTO actual FROM public.ingestion_work_items w WHERE key=expected->>'key';
 IF actual IS DISTINCT FROM expected THEN RAISE EXCEPTION 'CONFLICTING_STORAGE_ITEM'; END IF;
 IF EXISTS(SELECT 1 FROM public.ingestion_work_items WHERE key NOT IN (repeat('0',64),'c1f526eed20e392382001cad4d28eb5bc16e5d1c0f92adb282fe7b1cc775f3f3','0eff5d22b28ee79039d151382ac0321e26350b9ccb10c58f46b82050dab82bf9','16c9c4d1fb67d844ddb29b092217c3b5a7c42eb8ba63e296611ce2f617779f6d')) THEN RAISE EXCEPTION 'UNEXPECTED_STORAGE_ITEM'; END IF;
 SELECT sum(octet_length(to_jsonb(w)::text)) INTO n FROM public.ingestion_work_items w;
 IF n>32768 OR pg_total_relation_size('public.ingestion_work_items')+pg_total_relation_size('public.ingestion_work_attempts')>1048576 THEN RAISE EXCEPTION 'STORAGE_CAP'; END IF;
 RETURN 3;
END $fn$;
ALTER FUNCTION public.ingestion_seed_storage_test() OWNER TO ingestion_storage_owner;
REVOKE ALL ON FUNCTION public.ingestion_seed_storage_test() FROM PUBLIC;
DO $acl$ DECLARE r record; BEGIN
 FOR r IN SELECT DISTINCT p.rolname FROM pg_proc f CROSS JOIN LATERAL aclexplode(f.proacl) a JOIN pg_roles p ON p.oid=a.grantee WHERE f.oid='public.ingestion_seed_storage_test()'::regprocedure AND p.rolname<>'ingestion_storage_owner' LOOP
 EXECUTE format('REVOKE ALL ON FUNCTION public.ingestion_seed_storage_test() FROM %I',r.rolname); END LOOP; END $acl$;
GRANT EXECUTE ON FUNCTION public.ingestion_seed_storage_test() TO ingestion_storage_operator;
CREATE FUNCTION public.ingestion_raise_stop(reason text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $fn$
BEGIN
 IF reason IS NULL OR octet_length(reason)>512 OR length(reason)=0 THEN RAISE EXCEPTION 'STOP_REASON_BOUND'; END IF;
 UPDATE public.ingestion_work_items SET outcome=(outcome::jsonb || jsonb_build_object('manual_stop',reason,'global_stop',coalesce(nullif(outcome::jsonb->'global_stop','null'::jsonb),jsonb_build_object('reason',reason))))::json
 WHERE key=repeat('0',64);
 IF NOT FOUND THEN RAISE EXCEPTION 'CONTROL_MISSING'; END IF;
END $fn$;
ALTER FUNCTION public.ingestion_raise_stop(text) OWNER TO ingestion_storage_owner;
REVOKE ALL ON FUNCTION public.ingestion_raise_stop(text) FROM PUBLIC;
DO $acl$ DECLARE r record; BEGIN
 FOR r IN SELECT DISTINCT p.rolname FROM pg_proc f CROSS JOIN LATERAL aclexplode(f.proacl) a JOIN pg_roles p ON p.oid=a.grantee WHERE f.oid='public.ingestion_raise_stop(text)'::regprocedure AND p.rolname<>'ingestion_storage_owner' LOOP
 EXECUTE format('REVOKE ALL ON FUNCTION public.ingestion_raise_stop(text) FROM %I',r.rolname); END LOOP; END $acl$;
GRANT EXECUTE ON FUNCTION public.ingestion_raise_stop(text) TO ingestion_worker, ingestion_storage_operator;
-- No memberships, LOGIN/passwords, runtime write grants, issuer or release functions.
COMMIT;
