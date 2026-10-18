# Restricted-account connection gap — comparison and proposal

Status: ANALYSIS AND PROPOSAL ONLY. Nothing here releases a registration, changes a credential, role or stop, or runs anything live. Storage remains accepted. Operational acceptance and Stage 4 remain OPEN. Historical uncertainty is preserved.

## What is established (with the evidence that establishes it)
1. **Administrative qualification (successor 2, `evidence/successor-2-qualified/`).** The role `postgres.<ref>` completes preparation and one connection through the approved pooler (host `aws-0-eu-west-2.pooler.supabase.com:5432`, verify-full, pinned IPv4) **with the reviewed startup options**, runs one `SELECT current_user`, identity matches, closure verified. Scope is the administrative role only.
2. **Restricted custom roles have authenticated through this same pooler route before.** In the accepted storage run (`storage-acceptance-identity-successor-20261017`, events: `connection_closed` for `ingestion_storage_login` ×2 and `ingestion_worker_login` ×2, `storage_connections: 4`, `storage_commands: 40`), both restricted logins connected as `<role>.zcikcfgpblzuzpanpdqd` with password, TLS verify-full and the pinned address. That run created those roles fresh (`role_names_unused: true`) and connected **without any startup `options`**.
3. **The 18 Oct operational attempt failed on the first restricted connection** (`operational-route-diagnostic-once-20261018`, event 69–70): role `ingestion_worker_login`, phase `DRIVER_CONNECT`, `OperationalError`, **SQLSTATE absent**; the slot's recorded connection-active time was ≈0.57 s, and the whole run took ≈5.4 s including teardown. By inference from those durations (not proof), the failure was not a client preparation defect (preparation stages are now separately proven), not an immediate local refusal and not a 3 s connect timeout. Its class is undetermined: with no SQLSTATE the driver did not receive a server `ErrorResponse` it could code.
4. **Credential generation, encoding and mapping are the same in both paths.** `secrets.token_urlsafe(48)` (alphabet `A–Z a–z 0–9 _ -`, so URL quoting is a no-op), SCRAM-SHA-256 verifier from `pgconn.encrypt_password`, `ALTER ROLE … PASSWORD … VALID UNTIL …` in a short transaction, then `LOGIN` after mapping. Role names and routing username are built identically (`<role>.zcikcfgpblzuzpanpdqd`); a disposable test already pins the storage-path and operational-path connect arguments as identical except the differences listed below.
5. **Role flags and lifecycle are the same pattern.** Both logins: `NOLOGIN … CONNECTION LIMIT 1 PASSWORD NULL` at rest; activation gate then `ALTER ROLE … LOGIN`; teardown `ALTER ROLE … NOLOGIN PASSWORD NULL` and capability revoke (readback `(role, false, true)` = NOLOGIN, NULL password, no membership, no sessions).

## Differences between the demonstrated-working restricted path (10-17) and the failed one (10-18)
| # | Difference | Status |
|---|---|---|
| D1 | **Startup `options`** (`-c statement_timeout=10000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=20000`) were present on the operational restricted connection and absent on the accepted storage connections. | Candidate. Not a defect: the **administrative** role connects through the same pooler **with** these options, so the pooler does not reject the options as such. Whether it treats them differently for a custom role is untested. |
| D2 | **Role reuse and credential rotation.** On 10-17 the role names were new; on 10-18 `ingestion_worker_login` pre-existed (NOLOGIN, NULL password) and its password was rotated and the role set to `LOGIN` ≈ seconds before the first connection. | Candidate. A pooler-side per-(tenant, user) credential or negative-lookup cache would affect only the reused role. Provider-dependent. |
| D3 | **`ingestion_effect_login`** (never demonstrated through the pooler; not part of the storage run) is the second operational role. | Never attempted: the run stopped at the worker failure. A separate, untested role. |
| D4 | Client driver class (`Cursor` subclass, SQLAlchemy `creator`) vs plain `psycopg.connect`. | Client-side only; cannot change what is sent in the startup packet apart from D1. Disposable tests already pin the arguments. |

Not differences (checked, same in both): SQL role name, routing username, password generation/encoding/length, SCRAM verifier method, `VALID UNTIL`, `CONNECTION LIMIT 1`, NOLOGIN→LOGIN ordering relative to connection, TLS mode/CA, pinned address, `prepare_threshold=None`, `autocommit=True`, `connect_timeout=3`.

## Established defects
**None established in repository code.** The comparison finds no encoding, role-name, ordering or flag defect. The preparation-stage defects already corrected in PR #131 do not explain this failure (the failure occurred after a completed connect handshake attempt of ≈0.57 s). The previous diagnostic mode (`CONNECTION_DIAGNOSTIC_ONLY`) ran the full credential lifecycle but has never answered *why* the first restricted connection failed.

## Remaining provider-dependent uncertainty
- Why the pooler/database ended the 10-18 worker connection (no SQLSTATE exposed to the client).
- Whether the pooler caches credential-lookup results per (tenant, user) and for how long (D2), including the NULL-password/NOLOGIN state at rest.
- Whether startup `options` are handled differently for custom roles than for the project's `postgres` role (D1).
- Effect login behaviour through the pooler (D3).
A sanitised follow-up for SU-511198 is prepared in `provider-followup-SU-511198-DRAFT.md`. The support form reachable with existing access only creates *new* requests (not permitted); updating an existing ticket is an email-thread reply with no tool available here. It was not sent.

## Is the next meaningful test a restricted-account connection?
**Yes.** Nothing in the repository, retained evidence or disposable tests can distinguish D1 from D2 from a provider-side cause, and administrative success cannot be taken as evidence about restricted authentication. The single test below separates them directly. Qualification precedes any execution grant by construction: the proposed mode contains no authority registration and issues no grant or exception.

## Smallest concrete proposal: `RESTRICTED_CONNECTION_MATRIX_ONLY` (not implemented, not released)
**Reuses** the accepted lifecycle unchanged: owner preflight and installed-state reuse, `map_and_activate` (fresh passwords, `VALID UNTIL`, protected-secret mapping, activation gate, `LOGIN`), the existing restricted-connection qualification step and the existing `teardown`/failure invalidation. **Removes** everything after qualification: no `AUTHORITY_REGISTRATION`, no source reader, no exception, no queue/ledger mutation, no capture, no application writer, no council request.

**Change set (small):** (1) `DatabaseBudget.engine` takes `startup_options` as an explicit parameter (`REVIEWED` = today's value, `NONE`), recorded in each runtime connection event; production default unchanged. (2) A mode that executes an ordered matrix and returns after it. (3) Registration binds the matrix, caps and mode; the existing exact-key, exact-authority, single-use and namespace rules apply.

**Ordered matrix (each entry: one connection, one fixed statement `SELECT session_user`, then close):**
1. `ingestion_worker_login`, options `NONE`
2. `ingestion_worker_login`, options `REVIEWED`
3. `ingestion_effect_login`, options `NONE`
4. `ingestion_effect_login`, options `REVIEWED`
Entries 2 and 4 run even after a failure in 1 or 3 (bounded), at least 5 s later, so propagation timing is observable; there is no entry beyond these four.

**Finite accounting (hard caps; exhaustion stops the run):** runtime connection attempts ≤ 4; runtime driver statements ≤ 4 (+ the existing 8 cleanup reserve); returned bytes ≤ 1 KiB; administrative connections ≤ 5 and commands ≤ 64 (the 10-18 lifecycle used 5 and 52); credential generations = 2; secret mappings = 2 (both deleted); role changes = the existing set only; hidden input ≤ 120 s; active window ≤ 120 s; outer ceiling ≤ 300 s with a 330 s systemd backstop; memory 256 MiB controller / 1.5 GiB aggregate, no swap; evidence ≤ 64 KiB.

**Reading the result (decision table; classifications are allow-listed, never message text):**
| worker NONE | worker REVIEWED | Reading |
|---|---|---|
| success | fail | startup options are the difference (D1) |
| fail | success | timing/propagation or cache (D2), options not the cause |
| fail | fail | not options; propagation/cache, role/pooler configuration or provider-side — evidence for the ticket |
| success | success | the 10-18 failure did not recur; transient or cache-expiry (D2) — undecided, recorded |
The same table applies to the effect login (D3). No entry is a qualification for execution by itself; qualification for a later grant requires both roles to succeed with the options the pipeline will use, and is bound by hash into that later registration.

**Safe failure classification:** per entry record role, variant, ordinal, phase, exception kind, SQLSTATE (if any), allow-listed reason code, `failed_native_connection_finished`; unknown stays `UNKNOWN`. A failed entry never changes the other entries' variants and never triggers a retry.

**Teardown (complete, evidence-gated):** `ALTER ROLE … NOLOGIN PASSWORD NULL` for both logins, capability revoke, no sessions/memberships readback, deletion and absence readback of both temporary secrets, process/socket/kernel-group closure — all existing code. Any uncertain step stops with `UNCERTAIN_RECONCILE` and no replay.

**Authorisation this needs (not given):** a new Product Owner decision. It performs credential generation and mapping again, so the existing exact risk acceptance (possible provider SCRAM verifier retention) must be accepted again for the new registration, together with the matrix, caps and a fresh single-use namespace. This proposal does not propose another administrative probe.
