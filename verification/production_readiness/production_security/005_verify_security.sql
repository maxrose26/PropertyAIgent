-- READ-ONLY security supplement. Full catalogue/hash comparator is ALSO required.
BEGIN READ ONLY;
SET LOCAL statement_timeout='10s';
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
SELECT 'PASS: dark-install security supplement' AS result;
COMMIT;
