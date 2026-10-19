# Operational acceptance — single grouped release package (decision request; nothing here is authorised or run)

Status: PACKAGE FOR ONE GROUPED DECISION. No production execution, credential lifecycle, session termination, stop exception or ingestion is authorised by this document. Storage remains accepted. Stage 4 remains OPEN. All consumed authorities and historical results (including the consumed matrix outcome recorded by the pre-correction code) are preserved and are not reinterpreted.

## 1. Exact candidates and integration order
Code state reviewed and green on all hosted checks (offline, native, postgres-admission, restricted-provisioning with hosted PG17 rehearsals, web):

| Order | PR | Head | Content |
|---|---|---|---|
| 1 | #133 (docs) | 631386ae… | Admin-probe evidence + restricted-gap analysis with erratum |
| 2 | #138 (docs) | ad2954da… | Verified matrix and cleanup audits with hashes |
| 3 | #136 | 2854f556e9e4762fd15469136d7da18bfc382526 (tree cc062470…) | Matrix: separate identity/timeout checks, per-entry client deadline |
| 4 | #137 | 39fc5a241e3b7da6359431fad341b5c0b26df863 (tree c7d1865d…) | Operational runtime: client hard deadline on every driver wait (based on #136) |
| 5 | #139 | code state 16c26c0e0e63253dd11df1fed7673314bb214f6a (tree a5ca2bc1f50e0e0375b127190568c1e9c4660ec5); later commits on the branch are documentation only | Accounted cancellation, execution-reserve clamp, bounded admin statements, teardown session policy, hosted rehearsal faults (based on #137) |
| – | #135 | 375601af… | Consumed revoke-only cleanup: keep the head reachable (PR ref/tag); merging is optional and must not precede #138 |

Documentation PRs (#133, #138) carry the verified evidence and can be merged independently and first.

## 2. Deadline statements (precise)
- **Per wait**: every blocking driver wait of a runtime connection (statement, BEGIN, COMMIT, ROLLBACK, pool reset) is bounded at 12 s (strictly above the 10 s server statement timeout, which stays primary when reflected) and further clamped to the remaining execution reserve (`hard_stop_at`). Administrative statements are bounded at 12 s likewise. Connection establishment is bounded by `connect_timeout=3`, and as last resort by the process-level `HardDeadline`.
- **Per complete operation**: up to 2 waits (statement + its cleanup wait) + one cancel ≤ 2.0 s + close ≤ 1.0 s. The effective failure window is about 22 s (not the nominal 25 s) when two waits are consumed.
- **Aggregate**: slot ≤ 165 s; capture mode job 450 s, diagnostic total 475 s, hard stop 480 s; matrix mode active 270 s / work alarm 215 s / outer 420 s / backstop 450 s. Cancellation attempts are finite (allowance of 4 attempts at 2.0 s each per budget) and each is recorded (attempts, seconds, outcome, failures) in the budget receipt and the final accounting; once exhausted no further cancel is attempted, the connection is still closed, and the outcome is `CANCEL_SKIPPED_ALLOWANCE_EXHAUSTED`.
- **Cancel acknowledgement is not backend closure.** `cancel_safe()` opens a separate bounded cancel connection; the unbounded `cancel()` is never used. Every event records `backend_closure: NOT_ESTABLISHED`; only the session readback in teardown can prove absence.
- **Demonstration**: hosted rehearsal with a real blocked query (`blocked_query`): 1 event, `CANCEL_SENT`, deadline honoured, all connections closed, cleanup CLOSED. Wrapper rehearsal with an exhausted normal administrative allowance (`exhausted_normal_budget`): the reserved teardown allowance still disables access and removes secrets. Local tests cover cancel failure, cancel timeout through a non-forwarding proxy, no boundable cancel, no connection, exhausted allowance, reserve clamp, and admin-statement blocking.

## 3. Teardown policy (implemented, tested)
Disable first (NOLOGIN, NULL password, membership revoked) → bounded session reads (3 × 0.5 s) → terminate at most two sessions, each bound by pid + login + backend start, only when the migration identity is proven to hold usable (inherited, `USAGE`) `pg_read_all_stats` and `pg_signal_backend` → delete the temporary secrets independently once DISABLED is verified → final readbacks. Extra (>2), unidentifiable or unprivileged sessions stay `UNRESOLVED_*` and are reported (Uncertain), never closed; no privilege is ever granted. Review fix applied: a failure inside session resolution can no longer suppress secret deletion (disposition `UNRESOLVED_ERROR`).

Measured in hosted PG17 rehearsal (complete wrapper: qualification, capture, batching, teardown): privileged survivor → `TERMINATED_VERIFIED_ABSENT`, 123 admin commands / 6 connections; unprivileged survivor → `UNRESOLVED_PRIVILEGE_NOT_PROVEN`, 121 commands, 0 terminations, secrets removed; both within the existing ceilings (at most 240 commands, 13 connections). Also rehearsed: qualification failure before any grant, blocked query, uncertain commits, exhausted normal budget, matrix faults.

## 4. Qualification gate and the last live observation
The gate is **unchanged and strict**: both restricted identities must connect through the actual runtime factory with identity/flags verified **and** the reviewed server timeouts (`10s`, `3s`, `20s`) reflected, with the client deadline active. In the last live matrix the worker connected (identity right) but the requested startup options were **not reflected**. An identical setup is not assumed to behave differently: with the same setup the gate **fails safe before any grant**, tears down, and (new) records the observed timeout values (`runtime_qualification_observation`, identity and timeouts separately). The only path that could satisfy the gate is a different delivery mechanism for the timeouts, **not verified live**: role-level settings (`ALTER ROLE … SET statement_timeout / lock_timeout / idle_in_transaction_session_timeout`), which apply regardless of startup options. This needs approval (section 7). If unapproved, or if it is also not reflected, the run ends at qualification with diagnostics and nothing else happens. The client hard deadline is the independent control and does not substitute for the gate.

## 5. Risk, stop and authority binding
- **Credential risk**: acceptance of possible provider SCRAM-verifier retention is re-bound to this single run only (not extended or reused).
- **Bolton**: one grant and one exception, issued through the existing owner step only after qualification, on a fresh control readback bound into the registration, time-bound, single-use, under the unchanged global and manual stops. Salford's original stop and all consumed authorities remain intact; nothing else is released; ingestion beyond the single capture/screening is not authorised.
- No new accounts, no privilege grants, no stronger permissions.

## 6. Disclosures
- The consumed matrix-cleanup privilege check used `MEMBER` rather than `USAGE`; it never needed to terminate, so no effect. The new policy uses `USAGE` (a hosted PG17 rehearsal exposed the NOINHERIT trap; covered by a test).
- Reviewer notes accepted as residual: the 0.5 s floor on remaining reserve can slightly exceed the reserve; refused cleanup waits near the reserve rely on the 20 s idle-in-transaction timeout; disabling shares a transaction with expiring the control-table grants (a fault there leaves secrets in place, which is safe).
- SU-511198 follow-up remains unsent (no channel); no duplicate ticket.

## 7. Decision requested (grouped)
1. Merge order in section 1 (docs first; #135 head kept reachable).
2. Approve role-level ALTER ROLE timeouts as the timeout mechanism for the run (or decline; the run then ends at the gate).
3. Approve ONE run: lifecycle → qualification → (only if qualified) register Bolton grant + exception → capture_once → screening → teardown.
4. Re-bind the credential-risk acceptance to that run; approve the precise Bolton exception under the unchanged stops.
5. Release a fresh registration (earlier ones are consumed/expired and are not extended).
