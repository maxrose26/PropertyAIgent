-- FINAL NON-DESTRUCTIVE REVOCATION. Existing owned backends must be closed and
-- exact-role pg_stat_activity readback reconciled; NOLOGIN alone cannot do that.
BEGIN;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='10s';
ALTER ROLE ingestion_worker_login NOLOGIN PASSWORD NULL;
ALTER ROLE ingestion_storage_login NOLOGIN PASSWORD NULL;
ALTER ROLE ingestion_effect_login NOLOGIN PASSWORD NULL;
ALTER ROLE ingestion_recovery_login NOLOGIN PASSWORD NULL;
ALTER ROLE ingestion_application_login NOLOGIN PASSWORD NULL;
REVOKE ingestion_worker FROM ingestion_worker_login;
REVOKE ingestion_storage_operator FROM ingestion_storage_login;
REVOKE ingestion_effect_broker FROM ingestion_effect_login;
REVOKE ingestion_recovery_operator FROM ingestion_recovery_login;
REVOKE ingestion_application_writer FROM ingestion_application_login;
COMMIT;
-- Remove only the exact test protected mappings after acknowledged revocation.
-- Preserve all ledger rows, attempts, application/lifecycle rows and evidence.
-- Uncertain SQL/secret commits require reconciliation, never replay or deletion.
