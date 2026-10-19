# Operational acceptance — final candidate and numerical production proposal (decision request; nothing here is authorised or run)

Status: ONE FINAL CANDIDATE, ONE PRODUCTION PROPOSAL. No production execution, credential lifecycle, role change, session termination, stop exception or ingestion is authorised by this document. Storage remains accepted. Stage 4 remains OPEN. All consumed authorities and historical results are preserved and are not reinterpreted by later code. This revision supersedes the earlier package text on this branch.

## 0. Correction of a historical statement
Earlier text said the consumed matrix showed the worker's identity to be right and only the timeouts not reflected. **The consumed matrix does not support that.** Its retained outcome for entry 2 is a single merged result (`IDENTITY_UNEXPECTED`, produced by pre-correction code that checked identity, flags and timeouts in one comparison). It did not separately retain proof that the identity and flag checks passed. What is established: the session connected and ran the identity statement. What is **not** established: which of identity, flags or timeouts differed. "Requested options were not reflected" is the most probable explanation and the reason this package adds a role-level mechanism, but it is an inference and is carried here as uncertain. The corrected code now reports identity/flags and timeouts separately (`runtime_qualification_observation`), so the next run will resolve the question whichever way it falls.

## 1. Final candidate and integration order
| Order | PR | Head | Content |
|---|---|---|---|
| 1 | #133 (docs) | 631386ae… | Admin-probe evidence, restricted-gap analysis with erratum |
| 2 | #138 (docs) | ad2954da… | Verified matrix and cleanup audits |
| 3 | #136 | 2854f556e9e4762fd15469136d7da18bfc382526 | Matrix: separate identity/timeout checks, per-entry client deadline |
| 4 | #137 | 39fc5a241e3b7da6359431fad341b5c0b26df863 | Operational client hard deadline (based on #136) |
| 5 | #139 | **code state 50c9f7063a61aac341cee47e57455b0537fea987** (tree 52b9f4a2e0c095e2c1e38aa6aaa40f319667e52d); later commits on the branch are documentation only | Accounted/aggregate cancellation, reserve clamp, bounded admin statements, teardown policy with protected first session read, role-level timeout settings with exact restoration, hosted rehearsals |
| – | #135 | 375601af… | Consumed revoke-only cleanup: keep head reachable; optional to merge, never before #138 |

Final code state is green on all hosted checks (offline, native, postgres-admission, restricted-provisioning with PG17 rehearsals of the complete wrapper, web). Two independent focused reviews of the final fixes are complete; every substantive finding was fixed (secret deletion independent of session resolution; late watchdog; session residuals and restoration residuals recorded on every teardown path; resumed slots keep their cancel counts; sub-0.5 s waits refused rather than stretched; arithmetic corrected).

## 2. Role-level timeout settings (exact configuration and restoration)
Scope: **only** `ingestion_worker_login` and `ingestion_effect_login`. No other role, no database-wide setting, no new privilege.
1. **Capture** (1 command, same admin connection as credential mapping, before any password exists or LOGIN is possible): `rolconfig` of both roles and the count of database-specific settings. Refusal **before any change**: a database-specific setting present (`ROLE_DATABASE_SPECIFIC_SETTINGS_PRESENT`), a prior value of a reviewed parameter outside `[0-9]{1,9}(ms|s|min|h|d)?` (`ROLE_SETTING_PRIOR_VALUE_UNSUPPORTED`), or either role missing. Audit records reviewed-parameter values and the **names** (never values) of unrelated settings.
2. **Apply** in one transaction (BEGIN, 6 × `ALTER ROLE <role> SET <param> TO <literal>`, COMMIT): `statement_timeout='10s'`, `lock_timeout='3s'`, `idle_in_transaction_session_timeout='20s'`, each role. One parameter per statement; unrelated settings are untouched (tested with a prior `work_mem` and a prior `statement_timeout='7s'`). Read back and compare, else `ROLE_SETTINGS_NOT_VERIFIED`.
3. **Effective settings** are verified by the unchanged qualification gate through the **actual runtime factory**: each restricted login must report `('10s','3s','20s')` and its exact identity/flags. Rehearsed with startup options deliberately ignored (as a pooler may): the gate passes only because of the role-level settings.
4. **Restoration at teardown**, after access is verified disabled and the temporary secrets are deleted, on its own connection: per reviewed parameter `SET` to the captured prior value or `RESET` if there was none, one transaction, read back must equal the capture, else `RESTORATION_UNCERTAIN`.
5. **Failure handling (all rehearsed on hosted PG17)**:
   - success: restored exactly, prior unrelated and prior reviewed values preserved;
   - partial installation (failure after 3 of 6 statements): one transaction, nothing applied, no automatic compensation, state `APPLYING` and the actual role configuration reported in diagnostics;
   - failed qualification (worker timeout not reflected): stops before any grant, teardown disables, restores, secrets removed;
   - uncertain restoration: access disabled and secrets deleted regardless; the unrestored settings are a reported residual (`ROLE_SETTINGS_UNRESTORED`), the run result is not CLOSED, the captured prior values are in the audit for exact manual reversal.
6. **Not proven**: that the managed pooler/Postgres applies role-level settings to these logins. Supabase's own guidance uses role-level timeouts, but nothing in this repository has observed it. If they are not reflected the run stops at the gate before any grant; nothing else follows.
7. Mechanism risk accepted for this finite test: temporary configuration of two roles that are `NOLOGIN` at rest; restored at teardown.

## 3. Deadlines: reconciled arithmetic and worst-case trace
Constants (tested in `tests/test_ingestion_deadline_arithmetic.py`): per wait 12 s (runtime and administrative; above the 10 s server timeout); cancel ≤ 2.0 s; close ≤ 1.0 s; reserve clamp: no runtime wait may run past `hard_stop_at` = job limit; waits shorter than 0.5 s are refused.

| Level | Statement |
|---|---|
| Per wait | ≤ 12 s, and never beyond the slot budget or `hard_stop_at` |
| Complete runtime operation (unclamped) | 2 waits × 12 + cancel 2 + close 1 = 27 s; always inside the clamp, so it can pass `hard_stop_at` only by cancel + close = **3 s** |
| Aggregate runtime | slot ≤ 165 s; statements ≤ 1 040, connections ≤ 40, 300 s runtime total (existing, unchanged) |
| Cancellation, whole run | runtime cancels ≤ **8** across all slots (carried through receipts, pause/resume and same-key re-entry; never reset per batch); administrative cancels ≤ **3**; at most 11 cancel connections, each ≤ 2 s; exhaustion still closes the client and is recorded |

Worst-case trace, capture mode (job 450 s, failure window 25 s, diagnostic total 475 s, process backstop 480 s):
| t (s) | Event | Cumulative overrun/window |
|---|---|---|
| ≤ 450.0 | runtime wait clamped to the job limit | – |
| ≤ 453.0 | cancel (≤ 2.0) + close (≤ 1.0); the second (cleanup) wait is refused by the reserve; reporting begins | 3.0 |
| ≤ 468.0 | one blocked administrative statement during teardown: 12 + 2 + 1 | 18.0 |
| ≤ 471.0 | session reads: (3 wait + 3 post) × 0.5 | 21.0 |
| ≤ 474.0 | restoration: new connection + 9 commands, allowance 3.0 | **24.0 ≤ 25** |
| 475 / 480 | diagnostic total / process backstop | margin 1 s / 6 s |

The figure assumes a healthy GitHub and database apart from the single blocked statement. **A second blocked administrative statement, or slow GitHub calls (each bounded at 5 s), does not fit the window**: remaining teardown steps are then denied by the diagnostic window and reported, and the process backstop at 480 s still ends the run. Whether the secrets were deleted is always reported separately from access disablement.

## 4. Teardown (implemented, tested)
Disable first; `disabled` is decided from the role/password/membership readbacks alone. The first session read is now protected: a failure leaves the session disposition `UNVERIFIED` (reported, never CLOSED) and never prevents secret deletion or role-setting restoration (unit test and complete-wrapper regression `first_session_query_fails`). Surviving sessions: bounded reads, at most two precisely identified terminations (pid + login + backend start) only with proven inherited `pg_read_all_stats` and `pg_signal_backend`; extra or unidentifiable sessions stay unresolved; no privilege is ever granted. Secrets are deleted only after DISABLED is verified.

## 5. Numerical production proposal (single run)
Hosted PG17 measurements of the complete wrapper (qualification → capture → screening → teardown), including every added command and connection:
| Case | Admin commands | Admin connections |
|---|---|---|
| Complete success (role settings applied and restored) | 136 | 7 |
| Success with a privileged surviving session terminated | 142 | 7 |
| Unprivileged surviving session left unresolved | 140 | 7 |
| First session read fails | 135 | 7 |
| Failed qualification, restored | 106 | 6 |
| Uncertain restoration | 104 | 6 |
| Partial installation | 69 | 4 |
Role settings add exactly **+10 commands (same connection)** at mapping and **+9 commands, +1 connection** at teardown (asserted in tests). Ceilings, unchanged: administrative connections ≤ 13, commands ≤ 240 (normal 200 / teardown 232); runtime statements ≤ 1 040, connections ≤ 40, 300 s; cancellations ≤ 11; capture: one source request (10-request, 3 MB, 60-row, 6-page limits); screening: 0 source requests.

Sequence and stops (each failure stops the run, tears down, and reports; no retry, no second run):
1. Preflight (read-only, exact storage and stop state, fresh control readback bound into the registration).
2. Install/reuse accepted components (no new accounts or privileges).
3. Capture role settings; apply the three settings; mapping (fresh passwords, protected secrets); activation.
4. Qualification through the actual runtime factory: both identities, flags and `('10s','3s','20s')` reflected. **Failure here ends the run before any grant.**
5. Registration of **one** Bolton capture authority and **one** exception: scope `bolton`, received 2026-10-16, transport `REQUESTS_IDOX`, one source call, bound to stop checkpoint `a2345cf136fc92abf13bb55772f5c14a7a299b7f2b9cb0b89fe6037ccdb8a10e` and the freshly read hard-stop generation, expiring with the registration, single-use, under the unchanged global (consumed Salford) and manual stops. The consumed Salford stop and all consumed authorities remain intact; nothing else is released.
6. Capture (1 request), then batched screening (0 requests), within the ceilings above.
7. Teardown: invalidate the grants, disable both logins, session policy, delete the temporary secrets, restore role settings, closure checks.

## 6. Credentials and residual risk
The acceptance of possible provider SCRAM-verifier retention is re-bound to this single run only. Temporary secret values are described as "disabled for new login", never as destroyed. No credential is entered into chat, arguments, files or environment: the session prompt runs only in the owner's own visible WSL terminal.

## 7. Disclosures
- The consumed matrix-cleanup privilege check used `MEMBER`, not `USAGE`; it never needed to terminate a session.
- A partial or uncertain role-settings installation is not compensated automatically (the existing rule for uncertain administrative effects); the roles remain `NOLOGIN` and the audit carries the captured prior values.
- Administrative cancel accounting is shared by the resumed copies of the owner within one process; it does not survive a process restart (a restart is reconciliation-required in any case).
- SU-511198 follow-up remains unsent (no channel); no duplicate ticket.

## 8. Decision requested (one grouped decision)
1. Merge order in section 1 (docs first; #135 head kept reachable).
2. Approve the role-level configuration and restoration in section 2, including the unproven managed-pooler reflection (stop at the gate if not reflected).
3. Approve the single run in section 5 with its numerical ceilings.
4. Re-bind the credential-risk acceptance to this run; approve the Bolton exception exactly as in section 5, step 5.
5. Release a fresh registration (earlier ones are consumed or expired and are not extended).
