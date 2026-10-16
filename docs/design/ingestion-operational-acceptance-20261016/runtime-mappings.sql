-- PROPOSED ONLY. Apply after exact no-conflict/ambient-permission preflight.
-- Existing protected secure credential method remains BLOCKED pending answer.
-- These roles stay NOLOGIN, with no owner/admin or authority-release membership.
BEGIN;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='10s';
CREATE ROLE ingestion_effect_login NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS NOREPLICATION CONNECTION LIMIT 1;
CREATE ROLE ingestion_recovery_login NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS NOREPLICATION CONNECTION LIMIT 1;
CREATE ROLE ingestion_application_login NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS NOREPLICATION CONNECTION LIMIT 1;
GRANT ingestion_effect_broker TO ingestion_effect_login WITH ADMIN FALSE, INHERIT TRUE, SET FALSE;
GRANT ingestion_recovery_operator TO ingestion_recovery_login WITH ADMIN FALSE, INHERIT TRUE, SET FALSE;
GRANT ingestion_application_writer TO ingestion_application_login WITH ADMIN FALSE, INHERIT TRUE, SET FALSE;
-- CONNECT must be granted on the existing approved database only if not already
-- effectively available. No CREATE/owner grant is part of runtime mapping.
DO $database$ BEGIN
 IF current_database() NOT IN ('postgres','ingestion_provisioning_test') THEN RAISE EXCEPTION 'EXACT_DATABASE_REQUIRED'; END IF;
 EXECUTE format('GRANT CONNECT ON DATABASE %I TO ingestion_effect_login,ingestion_recovery_login,ingestion_application_login',current_database());
END $database$;
COMMIT;
