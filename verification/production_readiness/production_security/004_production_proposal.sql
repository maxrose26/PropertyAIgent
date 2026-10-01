-- PROPOSAL ONLY: NOT APPROVED FOR PRODUCTION EXECUTION OR REHEARSAL.
-- External operator must verify approved project zcikcfgpblzuzpanpdqd and this file hash.
-- SQL database name/role checks are necessary, NOT sufficient target authentication.
BEGIN;
SET LOCAL search_path = public, pg_catalog;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
SELECT pg_advisory_xact_lock(718203491);
DO $preflight$
DECLARE t text;
BEGIN
 IF current_database()<>'postgres' OR current_user<>'postgres' OR session_user<>'postgres'
 OR current_setting('server_version_num')::int/10000<>17 THEN
 RAISE EXCEPTION 'Unapproved database/operator/major version'; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=current_user AND rolcreaterole AND NOT rolsuper) THEN
 RAISE EXCEPTION 'Expected non-superuser CREATEROLE executor'; END IF;
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN ('ah_evidence_owner','ah_evidence_reader','ah_evidence_importer','ah_document_registrar')) THEN
 RAISE EXCEPTION 'Existing AH role: inspect; never adopt implicitly'; END IF;
 IF EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND (left(c.relname,3)='ah_' OR left(c.relname,6)='ix_ah_'))
 OR EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND left(p.proname,3)='ah_') THEN
 RAISE EXCEPTION 'Existing/partial AH objects: verify, do not recreate'; END IF;
 FOREACH t IN ARRAY ARRAY['applications','sites','documents'] LOOP
 IF NOT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 JOIN pg_attribute a ON a.attrelid=c.oid AND a.attname='id' AND NOT a.attisdropped
 JOIN pg_constraint k ON k.conrelid=c.oid AND k.contype='p' AND k.conkey=ARRAY[a.attnum]
 WHERE n.nspname='public' AND c.relname=t AND c.relkind='r' AND pg_get_userbyid(c.relowner)='postgres'
 AND a.atttypid='integer'::regtype AND a.attnotnull AND k.convalidated) THEN
 RAISE EXCEPTION 'Incompatible parent identity: %',t; END IF;
 END LOOP;
END $preflight$;
CREATE ROLE ah_evidence_owner NOLOGIN NOSUPERUSER NOINHERIT NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE ah_evidence_reader NOLOGIN NOSUPERUSER NOINHERIT NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE ah_evidence_importer NOLOGIN NOSUPERUSER NOINHERIT NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE ah_document_registrar NOLOGIN NOSUPERUSER NOINHERIT NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
-- PostgreSQL 17 CREATEROLE membership defaults do not confer SET ROLE.
GRANT ah_evidence_owner TO postgres WITH SET TRUE;
GRANT USAGE, CREATE ON SCHEMA public TO ah_evidence_owner;
GRANT REFERENCES(id) ON public.applications, public.sites, public.documents TO ah_evidence_owner;
SET LOCAL ROLE ah_evidence_owner;
-- Dedicated-owner defaults only: never change postgres/Supabase shared defaults.
ALTER DEFAULT PRIVILEGES REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES REVOKE ALL ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM PUBLIC;
-- BEGIN IDENTICAL REHEARSED SCHEMA BODY
CREATE TABLE ah_source_claims (
	id SERIAL NOT NULL,
	schema_version INTEGER DEFAULT '1' NOT NULL,
	application_id INTEGER NOT NULL,
	site_id INTEGER,
	scheme_application_id INTEGER NOT NULL,
	scope_kind VARCHAR(20) NOT NULL,
	scope_key VARCHAR(200) NOT NULL,
	scope_label VARCHAR(300) NOT NULL,
	scope_basis TEXT NOT NULL,
	metric VARCHAR(30) NOT NULL,
	tenure_name VARCHAR(100),
	qualifier VARCHAR(20) NOT NULL,
	value NUMERIC(18, 6),
	lower_bound NUMERIC(18, 6),
	upper_bound NUMERIC(18, 6),
	unknown_reason TEXT,
	document_id INTEGER NOT NULL,
	document_url_snapshot TEXT,
	document_title_snapshot TEXT,
	document_content_hash VARCHAR(64),
	document_date DATE,
	document_date_missing_reason TEXT,
	passage_text TEXT NOT NULL,
	passage_locator TEXT NOT NULL,
	page_start INTEGER,
	page_end INTEGER,
	extracted_text_hash VARCHAR(64),
	passage_start INTEGER,
	passage_end INTEGER,
	passage_hash VARCHAR(64) NOT NULL,
	planning_stage VARCHAR(20) NOT NULL,
	stage_document_id INTEGER,
	stage_passage_text TEXT,
	stage_passage_locator TEXT,
	origin_kind VARCHAR(20) NOT NULL,
	origin_reference VARCHAR(200) NOT NULL,
	extractor_version VARCHAR(200),
	created_by VARCHAR(200) NOT NULL,
	recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
	import_key VARCHAR(200) NOT NULL,
	payload_hash VARCHAR(64) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_ah_import_key UNIQUE (import_key),
	CONSTRAINT ah_schema_v1 CHECK (schema_version = 1),
	CONSTRAINT ah_metric CHECK (metric IN ('affordable_count','tenure_count')),
	CONSTRAINT ah_tenure CHECK ((metric='tenure_count' AND tenure_name IS NOT NULL AND length(trim(tenure_name))>0) OR (metric='affordable_count' AND tenure_name IS NULL)),
	CONSTRAINT ah_scope_kind CHECK (scope_kind IN ('whole_scheme','component','phase','unclear')),
	CONSTRAINT ah_scope_key CHECK ((scope_kind='whole_scheme' AND scope_key='WHOLE_SCHEME') OR (scope_kind='unclear' AND scope_key='UNRESOLVED') OR (scope_kind IN ('component','phase') AND scope_key NOT IN ('WHOLE_SCHEME','UNRESOLVED'))),
	CONSTRAINT ah_stage CHECK (planning_stage IN ('proposed','approved','legally_secured','unresolved')),
	CONSTRAINT ah_origin CHECK (origin_kind IN ('reviewed_import','extraction')),
	CONSTRAINT ah_quantity_shape CHECK ((qualifier IN ('exact','approximate') AND value IS NOT NULL AND lower_bound IS NULL AND upper_bound IS NULL AND unknown_reason IS NULL) OR (qualifier='range' AND value IS NULL AND lower_bound IS NOT NULL AND upper_bound IS NOT NULL AND lower_bound<=upper_bound AND unknown_reason IS NULL) OR (qualifier='at_least' AND value IS NULL AND lower_bound IS NOT NULL AND upper_bound IS NULL AND unknown_reason IS NULL) OR (qualifier='up_to' AND value IS NULL AND lower_bound IS NULL AND upper_bound IS NOT NULL AND unknown_reason IS NULL) OR (qualifier='unknown' AND value IS NULL AND lower_bound IS NULL AND upper_bound IS NULL AND unknown_reason IS NOT NULL AND length(trim(unknown_reason))>0)),
	CONSTRAINT ah_value CHECK (value IS NULL OR (value >= 0 AND value < 1000000000000)),
	CONSTRAINT ah_lower_bound CHECK (lower_bound IS NULL OR (lower_bound >= 0 AND lower_bound < 1000000000000)),
	CONSTRAINT ah_upper_bound CHECK (upper_bound IS NULL OR (upper_bound >= 0 AND upper_bound < 1000000000000)),
	CONSTRAINT ah_date CHECK ((document_date IS NULL AND document_date_missing_reason IS NOT NULL AND length(trim(document_date_missing_reason))>0) OR (document_date IS NOT NULL AND document_date_missing_reason IS NULL)),
	CONSTRAINT ah_pages CHECK ((page_start IS NULL AND page_end IS NULL) OR (page_start IS NOT NULL AND page_end IS NOT NULL AND page_start>0 AND page_end>=page_start)),
	CONSTRAINT ah_offsets CHECK ((passage_start IS NULL AND passage_end IS NULL) OR (passage_start IS NOT NULL AND passage_end IS NOT NULL AND extracted_text_hash IS NOT NULL AND passage_start>=0 AND passage_end>passage_start)),
	CONSTRAINT ah_stage_source CHECK ((stage_document_id IS NULL AND stage_passage_text IS NULL AND stage_passage_locator IS NULL) OR (stage_document_id IS NOT NULL AND stage_passage_text IS NOT NULL AND stage_passage_locator IS NOT NULL AND length(trim(stage_passage_text))>0 AND length(trim(stage_passage_locator))>0)),
	FOREIGN KEY(application_id) REFERENCES applications (id) ON DELETE RESTRICT,
	FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE RESTRICT,
	FOREIGN KEY(scheme_application_id) REFERENCES applications (id) ON DELETE RESTRICT,
	FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE RESTRICT,
	FOREIGN KEY(stage_document_id) REFERENCES documents (id) ON DELETE RESTRICT,
	CONSTRAINT ah_nonempty_scope_key CHECK (length(trim(scope_key))>0),
	CONSTRAINT ah_nonempty_scope_label CHECK (length(trim(scope_label))>0),
	CONSTRAINT ah_nonempty_scope_basis CHECK (length(trim(scope_basis))>0),
	CONSTRAINT ah_nonempty_passage_text CHECK (length(trim(passage_text))>0),
	CONSTRAINT ah_nonempty_passage_locator CHECK (length(trim(passage_locator))>0),
	CONSTRAINT ah_nonempty_origin_reference CHECK (length(trim(origin_reference))>0),
	CONSTRAINT ah_nonempty_created_by CHECK (length(trim(created_by))>0),
	CONSTRAINT ah_nonempty_import_key CHECK (length(trim(import_key))>0),
	CONSTRAINT ah_hex_document_content_hash CHECK (document_content_hash IS NULL OR (length(document_content_hash)=64 AND length(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(document_content_hash,'0',''),'1',''),'2',''),'3',''),'4',''),'5',''),'6',''),'7',''),'8',''),'9',''),'a',''),'b',''),'c',''),'d',''),'e',''),'f',''))=0)),
	CONSTRAINT ah_hex_extracted_text_hash CHECK (extracted_text_hash IS NULL OR (length(extracted_text_hash)=64 AND length(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(extracted_text_hash,'0',''),'1',''),'2',''),'3',''),'4',''),'5',''),'6',''),'7',''),'8',''),'9',''),'a',''),'b',''),'c',''),'d',''),'e',''),'f',''))=0)),
	CONSTRAINT ah_hex_passage_hash CHECK (passage_hash IS NULL OR (length(passage_hash)=64 AND length(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(passage_hash,'0',''),'1',''),'2',''),'3',''),'4',''),'5',''),'6',''),'7',''),'8',''),'9',''),'a',''),'b',''),'c',''),'d',''),'e',''),'f',''))=0)),
	CONSTRAINT ah_hex_payload_hash CHECK (payload_hash IS NULL OR (length(payload_hash)=64 AND length(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(payload_hash,'0',''),'1',''),'2',''),'3',''),'4',''),'5',''),'6',''),'7',''),'8',''),'9',''),'a',''),'b',''),'c',''),'d',''),'e',''),'f',''))=0))
)

;

CREATE INDEX ix_ah_application_metric ON ah_source_claims (application_id, metric);

CREATE INDEX ix_ah_context ON ah_source_claims (site_id, scheme_application_id, scope_kind, scope_key, metric);

CREATE INDEX ix_ah_document ON ah_source_claims (document_id);

CREATE INDEX ix_ah_payload ON ah_source_claims (payload_hash);


CREATE TABLE ah_claim_events (
	id SERIAL NOT NULL,
	claim_id INTEGER NOT NULL,
	sequence INTEGER NOT NULL,
	previous_event_id INTEGER,
	action VARCHAR(20) NOT NULL,
	related_claim_id INTEGER,
	reversed_event_id INTEGER,
	source_checked BOOLEAN NOT NULL,
	scope_checked BOOLEAN NOT NULL,
	stage_checked BOOLEAN NOT NULL,
	actor_id VARCHAR(200) NOT NULL,
	reason TEXT NOT NULL,
	recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
	request_key VARCHAR(200) NOT NULL,
	request_hash VARCHAR(64) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_ah_sequence UNIQUE (claim_id, sequence),
	CONSTRAINT uq_ah_request UNIQUE (request_key),
	CONSTRAINT ah_sequence CHECK (sequence>0),
	CONSTRAINT ah_previous CHECK ((sequence=1 AND previous_event_id IS NULL) OR (sequence>1 AND previous_event_id IS NOT NULL)),
	CONSTRAINT ah_action CHECK (action IN ('ACCEPT','REJECT','NEEDS_REVIEW','WITHDRAW','CORRECT','SUPERSEDE','CONFLICT','REVERSE_LINK')),
	CONSTRAINT ah_relation CHECK ((action IN ('CORRECT','SUPERSEDE','CONFLICT') AND related_claim_id IS NOT NULL AND related_claim_id<>claim_id AND reversed_event_id IS NULL) OR (action='REVERSE_LINK' AND reversed_event_id IS NOT NULL AND related_claim_id IS NULL) OR (action IN ('ACCEPT','REJECT','NEEDS_REVIEW','WITHDRAW') AND related_claim_id IS NULL AND reversed_event_id IS NULL)),
	CONSTRAINT ah_check_flags CHECK ((action='ACCEPT' AND source_checked AND scope_checked) OR (action<>'ACCEPT' AND NOT source_checked AND NOT scope_checked AND NOT stage_checked)),
	CONSTRAINT ah_event_nonempty CHECK (length(trim(actor_id))>0 AND length(trim(reason))>0 AND length(trim(request_key))>0),
	CONSTRAINT ah_request_hash CHECK (length(request_hash)=64),
	FOREIGN KEY(claim_id) REFERENCES ah_source_claims (id) ON DELETE RESTRICT,
	FOREIGN KEY(previous_event_id) REFERENCES ah_claim_events (id) ON DELETE RESTRICT,
	FOREIGN KEY(related_claim_id) REFERENCES ah_source_claims (id) ON DELETE RESTRICT,
	FOREIGN KEY(reversed_event_id) REFERENCES ah_claim_events (id) ON DELETE RESTRICT
)

;

CREATE INDEX ix_ah_related ON ah_claim_events (related_claim_id);

CREATE INDEX ix_ah_reversed ON ah_claim_events (reversed_event_id);

CREATE FUNCTION ah_deny_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'AH history is append-only'; END; $$;

CREATE TRIGGER ah_source_claims_deny_mutation BEFORE UPDATE OR DELETE OR TRUNCATE ON ah_source_claims FOR EACH STATEMENT EXECUTE FUNCTION ah_deny_mutation();

CREATE TRIGGER ah_claim_events_deny_mutation BEFORE UPDATE OR DELETE OR TRUNCATE ON ah_claim_events FOR EACH STATEMENT EXECUTE FUNCTION ah_deny_mutation();

ALTER TABLE public.ah_source_claims ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.ah_source_claims FORCE ROW LEVEL SECURITY;

REVOKE ALL ON public.ah_source_claims FROM PUBLIC;

REVOKE ALL ON SEQUENCE public.ah_source_claims_id_seq FROM PUBLIC;

ALTER TABLE public.ah_claim_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.ah_claim_events FORCE ROW LEVEL SECURITY;

REVOKE ALL ON public.ah_claim_events FROM PUBLIC;

REVOKE ALL ON SEQUENCE public.ah_claim_events_id_seq FROM PUBLIC;

REVOKE ALL ON FUNCTION public.ah_deny_mutation() FROM PUBLIC;
-- END IDENTICAL REHEARSED SCHEMA BODY
REVOKE ALL ON TABLE public.ah_source_claims, public.ah_claim_events FROM anon, authenticated, service_role, authenticator, ah_evidence_reader, ah_evidence_importer, ah_document_registrar;
REVOKE ALL ON SEQUENCE public.ah_source_claims_id_seq, public.ah_claim_events_id_seq FROM anon, authenticated, service_role, authenticator, ah_evidence_reader, ah_evidence_importer, ah_document_registrar;
REVOKE ALL ON FUNCTION public.ah_deny_mutation() FROM anon, authenticated, service_role, authenticator, ah_evidence_reader, ah_evidence_importer, ah_document_registrar;
RESET ROLE;
REVOKE REFERENCES(id) ON public.applications, public.sites, public.documents FROM ah_evidence_owner;
REVOKE CREATE, USAGE ON SCHEMA public FROM ah_evidence_owner;
-- Remove automatic creator memberships as well as temporary SET membership.
REVOKE ah_evidence_owner, ah_evidence_reader, ah_evidence_importer, ah_document_registrar FROM postgres;
DO $security_verify$
DECLARE owner_oid oid; role_count int;
BEGIN
 SELECT oid INTO STRICT owner_oid FROM pg_roles WHERE rolname='ah_evidence_owner';
 SELECT count(*) INTO role_count FROM pg_roles WHERE rolname IN ('ah_evidence_owner','ah_evidence_reader','ah_evidence_importer','ah_document_registrar');
 IF role_count<>4 OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN ('ah_evidence_owner','ah_evidence_reader','ah_evidence_importer','ah_document_registrar')
 AND (rolcanlogin OR rolsuper OR rolinherit OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)) THEN
 RAISE EXCEPTION 'AH role attributes differ'; END IF;
 IF EXISTS(SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid JOIN pg_roles u ON u.oid=m.member
 WHERE r.rolname IN ('ah_evidence_owner','ah_evidence_reader','ah_evidence_importer','ah_document_registrar')
 OR u.rolname IN ('ah_evidence_owner','ah_evidence_reader','ah_evidence_importer','ah_document_registrar')) THEN
 RAISE EXCEPTION 'AH membership unexpectedly present'; END IF;
 IF (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
 AND c.relname IN ('ah_source_claims','ah_claim_events') AND c.relkind='r' AND c.relowner=owner_oid AND c.relrowsecurity AND c.relforcerowsecurity)<>2 THEN
 RAISE EXCEPTION 'AH table ownership/RLS differs'; END IF;
 IF EXISTS(SELECT 1 FROM pg_policy WHERE polrelid IN ('public.ah_source_claims'::regclass,'public.ah_claim_events'::regclass)) THEN
 RAISE EXCEPTION 'Unexpected AH RLS policy'; END IF;
 IF (SELECT count(*) FROM pg_class WHERE oid IN ('public.ah_source_claims_id_seq'::regclass,'public.ah_claim_events_id_seq'::regclass) AND relkind='S' AND relowner=owner_oid)<>2 THEN
 RAISE EXCEPTION 'Sequence ownership differs'; END IF;
 IF EXISTS(SELECT 1 FROM pg_class c CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault(CASE WHEN c.relkind='S' THEN 's'::"char" ELSE 'r'::"char" END,c.relowner))) a
 WHERE c.oid IN ('public.ah_source_claims'::regclass,'public.ah_claim_events'::regclass,'public.ah_source_claims_id_seq'::regclass,'public.ah_claim_events_id_seq'::regclass)
 AND (a.grantee<>owner_oid OR a.grantor<>owner_oid)) THEN RAISE EXCEPTION 'Unexpected table/sequence ACL'; END IF;
 IF EXISTS(SELECT 1 FROM pg_attribute a CROSS JOIN LATERAL aclexplode(a.attacl) g
 WHERE a.attrelid IN ('public.ah_source_claims'::regclass,'public.ah_claim_events'::regclass)
 AND (g.grantee<>owner_oid OR g.grantor<>owner_oid)) THEN
 RAISE EXCEPTION 'Unexpected AH column ACL'; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_proc WHERE oid='public.ah_deny_mutation()'::regprocedure AND proowner=owner_oid AND NOT prosecdef) THEN
 RAISE EXCEPTION 'Trigger function owner/security differs'; END IF;
 IF EXISTS(SELECT 1 FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
 WHERE p.oid='public.ah_deny_mutation()'::regprocedure AND (a.grantee<>owner_oid OR a.grantor<>owner_oid)) THEN
 RAISE EXCEPTION 'Unexpected function ACL'; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_default_acl d WHERE d.defaclrole=owner_oid AND d.defaclnamespace=0 AND d.defaclobjtype='f')
 OR EXISTS(SELECT 1 FROM pg_default_acl d CROSS JOIN LATERAL aclexplode(d.defaclacl) a WHERE d.defaclrole=owner_oid AND a.grantee<>owner_oid) THEN
 RAISE EXCEPTION 'Unsafe dedicated-owner defaults'; END IF;
 IF EXISTS(SELECT 1 FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) a WHERE n.nspname='public' AND a.grantee=owner_oid)
 OR EXISTS(SELECT 1 FROM pg_attribute a CROSS JOIN LATERAL aclexplode(a.attacl) g WHERE a.attrelid IN ('public.applications'::regclass,'public.sites'::regclass,'public.documents'::regclass) AND g.grantee=owner_oid) THEN
 RAISE EXCEPTION 'Temporary privileges remain'; END IF;
 IF (SELECT count(*) FROM pg_trigger WHERE tgrelid IN ('public.ah_source_claims'::regclass,'public.ah_claim_events'::regclass) AND NOT tgisinternal)<>2 THEN
 RAISE EXCEPTION 'Unexpected AH user trigger'; END IF;
 IF (SELECT count(*) FROM pg_trigger WHERE tgrelid IN ('public.ah_source_claims'::regclass,'public.ah_claim_events'::regclass) AND NOT tgisinternal AND tgfoid='public.ah_deny_mutation()'::regprocedure AND tgenabled='O' AND tgtype=58)<>2 THEN
 RAISE EXCEPTION 'Append-only triggers differ'; END IF;
END $security_verify$;
SELECT 'AH dark-install security assertions passed; full catalogue verification still required' AS result;
COMMIT;
