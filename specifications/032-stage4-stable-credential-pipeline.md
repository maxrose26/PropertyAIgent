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
* **P3 invalidation and readback.** `Owner.invalidate_authorities` is **revocation-only** and independent of every stop-state (a failed execution may legitimately have advanced the generation and replaced the manual stop through the accepted fail-safe). Under the control-row lock it identifies only the authorities this run registered, verifies their exact execution bindings and the corresponding exception bindings, and sets only their grant and exception expiry to zero by exact-path updates; stops, generation, unrelated grants and all other fields are left exactly as they are (verified from the UPDATE's own row before COMMIT). A committed revocation is confirmed by a readback before it is claimed; an uncertain commit is never retried and is reported for reconciliation with one read-only observation. It never touches credentials, memberships, role settings or secrets. Then the final fixed read-only readback. Runs on every outcome. Anything not provably invalidated is `UNCERTAIN` and blocks.

**Restricted job** (`stage4-stable-pipeline-once.yml` → `stable_pipeline.py`, protected environment `stage4-production-canary`, the two restricted secrets only, no administrative credential):

* **H0 admission.** Single use by run number, pinned reviewed SHA, authority string, clean environment; actual-memory enforcement established before Python starts (§5).
* **H1 bounded connection qualification (before any ledger work).** The reviewed `stable_qualification.Qualification` runs unchanged (≤3 per login, ≤6 total, 20 s then 60 s spacing, continue only after exact `AUTHENTICATION_REJECTED` and verified client closure). It performs read-only introspection only, so no effect can be replayed. Pipeline work starts only after both logins qualified. **This is the only place the reconnect sequence applies**; after H1 there is no connection retry anywhere: a later connection failure is a stop, never a replay of an uncertain effect.
* **H2 capture and durable retention.** The accepted `capture_once` through `ControllerLedger`/`DatabaseBudget` with the accepted ceilings. The source worker runs in the accepted credential-free supervised subprocess. The raw source is retained durably (evidence branch, fast-forward only, read back at the committed revision) **before** the ledger checkpoint is marked durable; screening is impossible without `durable_archive` (accepted `process_batch` rule).
* **H3 wait for the screening authority.** Bounded, presence-based polling of the evidence branch (no database connection) for the owner's marker, with bindings recomputed locally from the retained capture; the authority itself is the database grant, enforced when the screening slot runs. Timeout is a stop, not a retry.
* **H4 source-free queued screening.** The accepted `process_batch` per plan; `source_reader` is a function that raises.
* **Result.** Cumulative accounting with a basis for every figure (`MEASURED`, `NOT_STARTED`, `LOWER_BOUND_ONLY_SOME_RECEIPT_UNKNOWN`), per-slot receipts, the sealed execution chain, client-closure evidence kept separate from server observations. The job never changes credentials and never revokes anything.

## 3. Reused unchanged
Accepted storage state and stops; `ControllerLedger`, `DatabaseBudget` (client hard deadline on every driver call), `capture_once`, `batch_plans`, `process_batch`, `item`/`digest`; the capture and screening ceilings; `Owner.register`; the stable qualification module; the evidence publisher's path allow-list and fast-forward-only rule; the session policy; the journal and accounting schema.

## 4. Numerical budgets (confirmed by disposable measurement before any registration; none is widened afterwards)
| Boundary | Bound |
|---|---|
| P0 readback | 1 connection, ≤ 12 statements, ≤ 20 s database-active, ≤ 30 s supervised-active, no retry |
| Owner administration overall | measured, not estimated: 52 commands / 5 connections on the normal path, 73 / 7 through the end-of-run invalidation and final readback, at most 71 on the worst failure path; allowances 56 / 80 / 96 commands and 8 / 9 connections (a placeholder of 48 / 60 / 72 was exhausted by the normal path in the first rehearsal) |
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

## 9. Corrective addendum after run 39388007668 (final publication within the enforced envelope; safe source diagnostics)

Status: specification for an offline corrective candidate. It authorises no live request, replacement execution, merge or registration.

### 9.1 What the first hosted run established (artifact 12248515861, sha256 `934a7982…c0ee22`)
* The restricted job connected, qualified both logins, verified its checkout binding, made exactly one Bolton request (`requests_attempted = 1`, `retries = 0`, `redirects = 0`, 183 bytes received, 0.385 s) and stopped with `BoundaryFailure:SOURCE_CONTRACT_REJECTED` at stage `FORM_REQUEST` (the first form `GET`). No capture was retained and no screening ran.
* The failure **cause is undetermined**. The retained record names no HTTP status, media type or specific rejection: `idox_window.run` collapses every `BoundaryFailure`/`Failure` into one code, and the diagnostic body is empty because the first retrieval did not return. Nothing in the record establishes an address block, and it must never be described as one.
* The restricted job's final-result publication ended `UNCERTAIN_Denied`. The cause is reproduced offline: `closure()` removes the memory scope and sets `memory_closure`; every later GitHub call runs `check()`, which raises `Denied('RESOURCE_ENVELOPE_CLOSED_NO_MORE_OPERATIONS')`. The rehearsal ran with no memory scope, so the path was never exercised, and the same ordering would deny the final publication on a successful run. The owner, which waits for `completed/final-result.json` or the retained marker, therefore received no early signal and waited out its bounded timeout.

### 9.2 Final publication inside an enforced budget, then final closure
The closed-envelope guard is **not** relaxed. The ordering changes instead:
1. **Pre-publication closure** (local only): connections, owned processes and sockets are closed and checked exactly as before, but the memory scope is **not** removed. The result is labelled `closure_stage = PUBLISHED_BEFORE_MEMORY_SCOPE_CLOSURE`; its `cleanup` is `PENDING_MEMORY_SCOPE_CLOSURE` when every other component is closed (never `CLOSED`).
2. **Publication under an enforced reserve**, with the memory scope still enforcing: a dedicated budget of at most 14 GitHub requests (the two-file publication is 10 requests, with at most 4 for head reads), 90 seconds and the publisher's existing 2 MiB bound. It is additional to nothing: it is a ceiling on the final publication, counted inside the hosted bound of 140. Every call still passes `check()` (memory snapshot included).
3. **Final closure**: the memory scope is closed and the complete closure is computed. **No GitHub call is made after memory closure.** The sealed local record (`final-result.json`, `events.jsonl`, the workflow artifact) carries the complete closure and `cleanup = CLOSED` or `UNCERTAIN`.
4. **Publication failure** is recorded with a fixed non-secret reason (`publication_reason`, the controller's own code or `UNKNOWN`); the artifact remains authoritative and the owner's bounded wait remains the fallback.
The published result never claims `CLOSED` for the memory scope. The owner accepts a published `PENDING_MEMORY_SCOPE_CLOSURE` as a completed hosted run only together with `closure_stage = PUBLISHED_BEFORE_MEMORY_SCOPE_CLOSURE` and a non-stop status. The published and the sealed records can legitimately differ: if the final closure then fails, the sealed local record and the workflow artifact report `UNCERTAIN` and a non-zero exit, and the owner (which only sees the published record) cannot observe that. The workflow artifact is the authority for the complete closure, and the run is reconciled against it. The owner (unchanged) observes `completed/final-result.json` at the next 30-second poll and ends the ceremony through its existing failure handling.

### 9.3 Safe source diagnostics
`failure_diagnostic` keeps its version-1 keys and values unchanged and gains an **optional** `transport` object, recorded from the first response the boundary receives:
* `http_status`: integer 100–599 or `null` when no response was received;
* `media_type`: one of a fixed allow-list (`text/html`, `application/xhtml+xml`, `text/plain`, `application/json`, `application/xml`, `text/xml`) or `OTHER`, or `null`;
* `redirect`: `NONE`, `SAME_ORIGIN` or `OTHER_ORIGIN` (the `Location` value is never exported), or `null`;
* `rejection_outcome` and `rejection_reason`: the boundary's own fixed literals when they are in a closed allow-list, otherwise `OTHER`.
Never exported: credentials, cookies, request or response headers other than the allow-listed media type, URLs, bodies, exception text. Existing audit classifications (`failure`, `code`, `stage`, `body_*`) are preserved.

### 9.4 Required validation
Unit tests for the two-stage closure, the reserve, the guard (calls after memory closure still denied), and the transport object (including exclusion of sensitive values). A complete success rehearsal and a complete source-failure rehearsal over the real controller guard and publication path with a stateful memory scope, in which the owner observes the failure on its next poll, ends both authorities and confirms the readback; and a hosted proof on a real cgroup-v2 scope that the publication occurs while the scope is enforcing and that closure follows it.

## 10. Control observation (offline preparation; no execution is authorised by this section)

Purpose: establish, before any further production decision, the actual state of the control record after the consumed run - stop generation, manual stop, `last_hard_stop`, the digest of the stop state, and the identity and expiry state of every grant and Bolton exception - as a **diagnostic observation**, never as acceptance of capture, screening or any authority.

**Concrete limitation.** The only installed read-only function (`ingestion_acceptance_control()`) returns the global stop, manual stop, stop generation and the count of unexpired grants. It does not return `last_hard_stop`, the digest, or any grant or exception identity or expiry. The administrative identity has no table privilege, so the full record can be read only through the transaction-local owner capability that the accepted preflight and the accepted invalidation readback already use: `GRANT ingestion_storage_owner TO CURRENT_USER` inside a transaction that is rolled back, with the absence of the capability read back. **The observation therefore has no committed mutation but is not strictly read-only**: the GRANT would write the role catalog if it were committed, and it is the one operation beyond reads that requires explicit approval (listed in the package). It is the only way the record can be read without installing a database function, which is a policy installation and is not authorised.

**Contract.** One mode, `CONTROL_OBSERVATION`: one connection; six statements (identity, `BEGIN`, the capability, one `SELECT` with the server clock, `ROLLBACK`, the capability readback), limit 12; at most 20 database-active seconds and 30 supervised-active seconds after the 120-second hidden input; registration expiry at most 30 minutes; no GitHub request (the GitHub bound is zero), no source request, no grant or exception, no application write, no commit. The audit receives a bounded projection (stop fields, names, expiry numbers and states, counts and two digests); bindings and key lists are never exported. The failure path reports and closes: no invalidation, no teardown, no diagnostics query, no retry. Fresh names: mode `CONTROL_OBSERVATION`, authority `AUTHORISE_INGESTION_CONTROL_OBSERVATION_ONCE_20261021`, state directory `operational-control-observation-once-20261021`.

**Bounds, stated precisely.** The 20 database-active-second ceiling is structural, not merely checked afterwards: no new statement starts after the 8-second administrative point, each statement has its own 4-second deadline, and connect (3 s) + the last statement (4 s) + one cancel (2 s) + close (1 s) is 18 s. The 30 supervised-active-second ceiling is the session's hard deadline. "One connection" means one session connection: if a statement hangs, the statement deadline's bounded cancel is a separate network request, not a second session. A failure after the transaction-local capability was granted cannot read its absence back (no second connection is permitted): the transaction is aborted by the disconnect, the result says so, and the owner should confirm that the route (a pooler, if any) rolls back an open transaction on client disconnect. The 1 MiB returned-bytes cap applies to the whole row; a larger row fails safe and the observation is lost.
