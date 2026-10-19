# Stage 4 stable-credential pipeline: owner readback → grant/exception → capture → durable retention → queued screening → authority invalidation

Status: specification for offline implementation and disposable validation. **Nothing here is authorised for production.** No new access, grant, exception, source call, password change, scheduling, purchase or deployment. Storage and the bounded credential qualification (run 39284253302) remain accepted; server reconciliation and operational acceptance remain outstanding. Stage 4 remains OPEN. The Salford global stop (`CONSUMED_SALFORD_GLOBAL_STOP`) and `STORAGE_TEST_STOP` are preserved; this specification does not clear or release either.

Intelligence layer: Planning Applications (Bolton RECEIVED 16 October 2026 listing) feeding the retained queue that later enriches Sites. Product principles applied: evidence over AI; every step explainable; source information never lost.

## 1. Why the accepted execution cannot be reused unchanged

The accepted capture/screening run (`REQUIRED_CAPTURE_SCREENING_SETTLED*`) is one owner-local process that creates fresh temporary passwords in memory, executes, then disables the logins. The stable credentials change the execution shape in three ways:

1. **The two restricted passwords exist only in the protected GitHub environment** (`INGESTION_WORKER_DATABASE_URL`, `INGESTION_EFFECT_DATABASE_URL`). They were never written anywhere else, cannot be read back from GitHub, and must not be rotated. Execution as the restricted logins therefore runs in a GitHub Actions job that consumes those secrets. An owner-local process cannot.
2. **The screening authority depends on the capture result** (batch membership is derived from the retained listing rows) and registering it needs the administrative identity. The two halves therefore cooperate through the ledger: the restricted job never holds the administrative credential, and the owner process never holds the restricted passwords.
3. **Standing credentials outlive the run.** Authority invalidation (ending the grant and exception) is separate from credential revocation (`STABLE_CREDENTIAL_REVOCATION`). A failed or uncertain run ends the execution authority and leaves the credential decision to the owner.

## 2. Components

**Owner controller** (new mode `STABLE_PIPELINE_AUTHORITY`, owner-local, one hidden-input session, reusing `Runner`, `Owner`, `Journal`, the session and accounting components). Administrative connections are opened per phase and closed. Phases:

* **P0 readback (read-only, before any mutation).** One connection, at most 12 driver statements, 20 s database-active, 30 s supervised-active, no retry. Observes and persists to the audit journal (no password or verifier value, no query text): identity and capability flags; both restricted logins' flags, password-presence booleans, exact `VALID UNTIL`, connection limit; exact memberships; role settings; sessions of the two logins (pid, state, backend start; **idle pooled backends are reported as such and are not classified as leaks**; an `active` or `idle in transaction` session, or an unidentifiable row, blocks); the control row (stops, hard-stop generation, every grant's expiry, exceptions); installed function inventory; absence of the capture and screening work items. Every expectation is compared with the registration; any mismatch, any failed or uncertain read, any unexpired grant or any stop change **prevents grant issuance** and ends the run with nothing mutated.
* **P1 capture authority.** Existing `Owner.register` for the single capture root item: one Bolton RECEIVED 16 October 2026 observation, `source_calls=1`, the narrowly scoped Bolton exception, under the unchanged stops. The grant lifetime is bounded separately from the registration (at most 60 minutes).
* **P2 screening authority.** After the restricted job has durably retained the capture, the owner process reads the completed root checkpoint (bounded polling, one statement per poll), derives batch plans with the accepted `batch_plans`, and registers the source-free screening authority (`source_calls=0`) with the accepted `Owner.register`.
* **P3 invalidation and readback.** `Owner.invalidate_authorities` sets `expires_at=0` on every authority and exception this run registered (it never touches credentials, memberships, role settings or secrets). Final fixed read-only readback of sessions, grants and stops. Runs on every outcome. Anything not provably invalidated is `UNCERTAIN` and blocks.

**Restricted job** (`stage4-stable-pipeline-once.yml` → `stable_pipeline.py`, protected environment `stage4-production-canary`, the two restricted secrets only, no administrative credential):

* **H0 admission.** Single use by run number, pinned reviewed SHA, authority string, clean environment; actual-memory enforcement established before Python starts (§5).
* **H1 bounded connection qualification (before any ledger work).** The reviewed `stable_qualification.Qualification` runs unchanged (≤3 per login, ≤6 total, 20 s then 60 s spacing, continue only after exact `AUTHENTICATION_REJECTED` and verified client closure). It performs read-only introspection only, so no effect can be replayed. Pipeline work starts only after both logins qualified. **This is the only place the reconnect sequence applies**; after H1 there is no connection retry anywhere: a later connection failure is a stop, never a replay of an uncertain effect.
* **H2 capture and durable retention.** The accepted `capture_once` through `ControllerLedger`/`DatabaseBudget` with the accepted ceilings. The source worker runs in the accepted credential-free supervised subprocess. The raw source is retained durably (evidence branch, fast-forward only, read back at the committed revision) **before** the ledger checkpoint is marked durable; screening is impossible without `durable_archive` (accepted `process_batch` rule).
* **H3 wait for the screening authority.** Bounded polling of the control row as the worker (read only) for the exact owner-registered screening authority, with bindings recomputed locally from the retained capture. Timeout is a stop, not a retry.
* **H4 source-free queued screening.** The accepted `process_batch` per plan; `source_reader` is a function that raises.
* **Result.** Cumulative accounting with a basis for every figure (`MEASURED`, `NOT_STARTED`, `LOWER_BOUND_ONLY_SOME_RECEIPT_UNKNOWN`), per-slot receipts, the sealed execution chain, client-closure evidence kept separate from server observations. The job never changes credentials and never revokes anything.

## 3. Reused unchanged
Accepted storage state and stops; `ControllerLedger`, `DatabaseBudget` (client hard deadline on every driver call), `capture_once`, `batch_plans`, `process_batch`, `item`/`digest`; the capture and screening ceilings; `Owner.register`; the stable qualification module; the evidence publisher's path allow-list and fast-forward-only rule; the session policy; the journal and accounting schema.

## 4. Numerical budgets (confirmed by disposable measurement before any registration; none is widened afterwards)
| Boundary | Bound |
|---|---|
| P0 readback | 1 connection, ≤ 12 statements, ≤ 20 s database-active, ≤ 30 s supervised-active, no retry |
| Owner administration overall | measured in the rehearsal and bound in the registration (connections and commands), with a failure-diagnostic reserve |
| Owner session | hidden input 120 s; one fixed overall owner window sized from the measured phase waits; registration ≤ 110 minutes |
| Grant / exception lifetime | ≤ 60 minutes; invalidated at P3 and by its own expiry |
| Source | one observation; ≤ 10 transport requests, ≤ 3,000,000 received-body bytes, ≤ 6 pages, ≤ 60 rows; screening 0 source requests |
| Restricted runtime (capture + screening) | ≤ 1,040 driver statements, ≤ 40 connections, ≤ 300 s aggregate, plus the qualification allowance (≤ 6 connection attempts, ≤ 330 s) |
| Job | timeout sized from the above, hard `timeout` kill below it |
| Evidence | combined output closure reserve as accepted; sealed chain published |

## 5. Hosted actual-memory enforcement
An address-space limit (`ulimit -v`) is **not** an actual-memory (RSS) ceiling and is never described as one. The hosted job places itself in a cgroup-v2 group with `memory.max` and `memory.swap.max=0` before starting Python (privileged setup step only; the secrets are not exposed to it), so the kernel OOM-kills on actual memory. CI proves the mechanism with a real allocation that is killed at the limit. If the cgroup cannot be established on the runner the job stops before any database connection (`ACTUAL_MEMORY_ENFORCEMENT_UNAVAILABLE`). The source subprocess keeps its accepted `RLIMIT_AS`/CPU/file limits; the supervisor's RSS polling is retained as defence in depth only.

## 6. Retention capability residual (to be accepted explicitly)
Durable retention before screening requires a write to the evidence branch from the restricted job. The job's `GITHUB_TOKEN` therefore needs `contents: write` for this single-use, hash-pinned workflow. It is confined by code (branch constant, `docs/design/ingestion-operational-execution-*` path allow-list, fast-forward only, ≤ 8 files, ≤ 2 MiB) and by static workflow tests, but the token is not branch-scoped by GitHub. No other write permission is requested; the token is not passed to the source subprocess.

## 7. Failure and recovery (execution authority vs standing credentials)
| Event | Execution authority | Standing credentials |
|---|---|---|
| P0 mismatch or uncertainty | none issued | untouched |
| Failure around P1 commit | state read back; any uncertain registration is invalidated | untouched |
| Qualification (H1) stops | owner P3 invalidates the capture authority | untouched; the owner decides on `STABLE_CREDENTIAL_REVOCATION` |
| Source worker fails or is uncertain | **no replay**; capture authority invalidated; run `UNCERTAIN` | untouched |
| Capture retained but screening incomplete | screening authority invalidated at P3; retained capture preserved; **resume is a separate decision** (the accepted resume reconstructs from the ledger with zero source calls) | untouched |
| Owner session lost | the grant lifetime bound (≤ 60 min) and the registration expiry end the authority; reconciliation by readback | untouched |
| Suspected credential compromise or uncertain closure | invalidate | revoke via the existing, separately registered `STABLE_CREDENTIAL_REVOCATION` |

## 8. Not authorised by this specification
Any production registration, dispatch, grant, exception, source call, application write, unit-fact work, stop release, password rotation, scheduling, deployment, purchase, or Stage advancement.
