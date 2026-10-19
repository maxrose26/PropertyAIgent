# Settled operational run 2026-10-19 — complete audit (stopped in ADMIN_PREFLIGHT; the experiment did not start)

Run: master `2afee9cc7581e19f8cad7951eed6dc9b428af73b` (tree `3446ec4f750818028769fa110570d6c3ff9d9c48`), registration sha256 `fa3a94c8b27b32e0ab07119530caf001632768f7c88a3e0ff87fc385434b4634`, namespace `operational-capture-queue-settled-once-20261019` (now consumed). Files are the owner's local audit byte for byte (hashes in HASHES.sha256). Chain verified: 35 events, head `e0ccfb6ef0391da74efb0321ca1a8a465bd448ce9b5b0b81726b57bf4e3aaf30`.

## Result
`STOP_RECONCILE_NO_RETRY`, operation phase `ADMIN_PREFLIGHT`, failure `ValueError` (message deliberately not exported). Reported cleanup `UNCERTAIN` and access `UNRECONCILED` because no teardown ran (nothing had been created); the read-only diagnostics and later checks show nothing was left behind.

**This was not an authentication failure.** No role-level setting was applied, no password or secret was created, the 30-second settling period never started, and neither restricted login was ever contacted. The delayed-first-connection hypothesis is therefore untested.

## Cause (attributed from the audit and the repository; the exception message itself was not exported)
Preflight in reuse mode verifies the installed function bodies against `worker.sql` (`verify_installed`, event `installed_function_inventory`, immediately before the failure). Comparing the inventories of the two runs:
- Run 1 (stopped at qualification) and run 2 differ in exactly two functions: `ingestion_bolton_allowed` and `ingestion_register_bolton_exception`.
- In run 1 both matched `worker.sql`; in run 2 both match the bodies of `successor-policy.sql` and no longer match `worker.sql`.
- The other four functions are identical in both runs and match `worker.sql`.
Run 1's `install()` applied the reviewed successor policy (`CREATE OR REPLACE FUNCTION`, committed); teardown does not and cannot undo it. The reuse-mode preflight accepts only the pre-policy state, so the first run's own (reviewed) policy application makes every later reuse run fail its preflight with `INSTALLED_FUNCTION_CONTENT_CHANGED`. The defect is in the preflight's idempotence, not in the database, the policy or the credentials.

## Reconciliation
| Obligation | Evidence |
|---|---|
| Authority, grant, source | none issued; control `unexpired_grants: 0`; source `NOT_STARTED`, 0 requests, 0 bytes; no capture; application writes 0 |
| Settling and first contact | `settling_started` absent; `first_connection_intervals` empty; zero `runtime_connection_*` events |
| Credentials and roles | both logins `NOLOGIN`, NULL password, no memberships, no sessions (diagnostics, 2nd admin connection); role configuration untouched (`NOT_REQUESTED`) |
| Secrets | environment secrets re-read after the run: `["DATABASE_URL"]` only |
| Administration | 19 commands / 2 connections (ceilings 240 / 13); both closed; no deadline events |
| Process | closure `CLOSED`: 0 children, 0 new sockets, 0 owned survivors, no OOM events, peak 74.0 MB; scope `propertyaigent-operational-once.scope` is `not-found`/`inactive`; active 1.67 s; hidden input 11.9 s; GitHub CLI invocations 2 |
| Evidence branch | head unchanged `7368d77b4908d1676023904ed0af6f0345ce0053` |
| Consumed records | predecessor audit and registration unmodified; this namespace and registration are consumed; no retry |
