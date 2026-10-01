-- Local native rehearsal security contract. Not production-approved.
-- Exact canonical AH tables and protections are otherwise unchanged.
REVOKE ALL ON public.ah_source_claims, public.ah_claim_events FROM PUBLIC, ah_ci_reader, ah_ci_importer, ah_ci_registrar, ah_ci_nobody, ah_ci_anon, ah_ci_authenticated, ah_ci_service_role;
REVOKE ALL ON SEQUENCE public.ah_source_claims_id_seq, public.ah_claim_events_id_seq FROM PUBLIC, ah_ci_reader, ah_ci_importer, ah_ci_registrar, ah_ci_nobody, ah_ci_anon, ah_ci_authenticated, ah_ci_service_role;
REVOKE ALL ON FUNCTION public.ah_deny_mutation() FROM PUBLIC, ah_ci_reader, ah_ci_importer, ah_ci_registrar, ah_ci_nobody, ah_ci_anon, ah_ci_authenticated, ah_ci_service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE ah_ci_owner IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC, ah_ci_reader, ah_ci_importer, ah_ci_registrar, ah_ci_nobody, ah_ci_anon, ah_ci_authenticated, ah_ci_service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE ah_ci_owner IN SCHEMA public REVOKE ALL ON SEQUENCES FROM PUBLIC, ah_ci_reader, ah_ci_importer, ah_ci_registrar, ah_ci_nobody, ah_ci_anon, ah_ci_authenticated, ah_ci_service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE ah_ci_owner REVOKE ALL ON FUNCTIONS FROM PUBLIC, ah_ci_reader, ah_ci_importer, ah_ci_registrar, ah_ci_nobody, ah_ci_anon, ah_ci_authenticated, ah_ci_service_role;
ALTER TABLE public.ah_source_claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ah_source_claims FORCE ROW LEVEL SECURITY;
ALTER TABLE public.ah_claim_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ah_claim_events FORCE ROW LEVEL SECURITY;

ALTER DEFAULT PRIVILEGES FOR ROLE ah_ci_owner  REVOKE ALL ON TABLES FROM PUBLIC, ah_ci_reader, ah_ci_importer, ah_ci_registrar, ah_ci_nobody, ah_ci_anon, ah_ci_authenticated, ah_ci_service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE ah_ci_owner  REVOKE ALL ON SEQUENCES FROM PUBLIC, ah_ci_reader, ah_ci_importer, ah_ci_registrar, ah_ci_nobody, ah_ci_anon, ah_ci_authenticated, ah_ci_service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE ah_ci_owner IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM PUBLIC, ah_ci_reader, ah_ci_importer, ah_ci_registrar, ah_ci_nobody, ah_ci_anon, ah_ci_authenticated, ah_ci_service_role;
