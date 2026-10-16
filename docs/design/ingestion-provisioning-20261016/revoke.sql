-- Non-destructive pause; retained data, objects and consumed authorities survive.
BEGIN;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='10s';
ALTER ROLE ingestion_worker_login NOLOGIN PASSWORD NULL;
ALTER ROLE ingestion_storage_login NOLOGIN PASSWORD NULL;
REVOKE ingestion_worker FROM ingestion_worker_login;
REVOKE ingestion_storage_operator FROM ingestion_storage_login;
COMMIT;
-- Existing authenticated backends must also be closed by the owned controller.
-- If any remain, owner must inspect pg_stat_activity for these EXACT two users
-- and request finite termination of their recorded PIDs. NOLOGIN alone does not
-- disconnect an already-authenticated client. Do not drop roles/tables or rows.
