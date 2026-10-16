-- REVIEW CANDIDATE ONLY. Existing application owner (or exact grant options)
-- applies after accepted storage. Never run as a runtime or migration fallback.
-- No password, login activation, table ownership change or RLS bypass.
BEGIN;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='10s';
CREATE ROLE ingestion_application_writer NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
GRANT USAGE ON SCHEMA public TO ingestion_application_writer;
GRANT SELECT ON public.applications TO ingestion_application_writer;
GRANT INSERT (council_code,reference,unit_confirmation_status,first_seen_at,last_seen_at,
 extraction_attempt_count,documents_legacy_unverified,evidence_refresh_required)
 ON public.applications TO ingestion_application_writer;
GRANT UPDATE (status,decision,decision_issued_date,status_verified_at,planning_field_verification,last_seen_at,
 evidence_refresh_required,evidence_refresh_reason,evidence_refresh_trigger,evidence_refresh_requested_at)
 ON public.applications TO ingestion_application_writer;
GRANT SELECT (id) ON public.application_lifecycle_events TO ingestion_application_writer;
GRANT INSERT ON public.application_lifecycle_events TO ingestion_application_writer;
DO $sequences$
DECLARE seq text;
BEGIN
 FOREACH seq IN ARRAY ARRAY[pg_get_serial_sequence('public.applications','id'),pg_get_serial_sequence('public.application_lifecycle_events','id')] LOOP
  IF seq IS NULL THEN RAISE EXCEPTION 'REVIEWED_SEQUENCE_REQUIRED'; END IF;
  EXECUTE format('GRANT USAGE ON SEQUENCE %s TO ingestion_application_writer',seq);
 END LOOP;
END $sequences$;
COMMIT;
