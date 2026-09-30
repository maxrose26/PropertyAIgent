# P0-A Gate A follow-up — blocked, not passed

**Offline Gate A remains open. No release approval is requested or implied.** The previous package was accepted as a progress report only. Independent local corrections and trace analysis are complete; missing runtime capabilities and the implementation issue below prevent completion of the gate.

## Exact state

- Branch: `feature/p0a-bounded-discovery`.
- Exact code/test commit exercised: `57451caa519676472767fa2270fbe2864a4d201f`.
- Previous package: `705590b26d79239df9a808946bd3bfb487f29928`.
- Baseline comparison: `301a56b3cde781f37e5f5bb0ffaded6537d5ca14` (documentation-only changes atop application baseline `6fd4202...`).
- Approved specification SHA-256 remains `c007e2b2912ae5d8817142c32fdf35e0000f72d4fa127d5c83e32e6ef10970f8`.
- Documentation branch is preserved. This follow-up documentation is a subsequent local commit; working tree was clean after packaging. No push, merge, production DB access/migration, live scrape, paid call, deployment, billing or production configuration change occurred.

## Actual runtime and test outcomes

| Check | Actual outcome |
|---|---|
| Disposable PostgreSQL | Not executed; one explicit skip. No postgres/initdb/pg_ctl or container engine exists here. Prior package installation failed on user/group switching; that installation method was not retried. No alternate authorised development executor is exposed. |
| Real Chromium | Four explicit skips. One installer invocation returned an empty/invalid ZIP (`End of central directory record signature not found`, final download failure). Its internal retry did not obtain a binary. No repeated install invocation or cloud-browser substitution was used. |
| Prepared real-browser coverage | Local navigation deadline, cleanup/subsequent work, actual document→refresh page recycling, supervisor failure with browser descendants and supervisor death with a surviving browser child. These tests are prepared, **not validated as passing**. |
| Final affected-suite run | **331 passed, 6 failed, 5 skipped, 1 deselected**, 32.00 seconds. Not a passing suite. |
| Matched baseline run | **281 passed, 5 failed, 1 deselected**, 24.41 seconds. Same offline harness and affected baseline suite list. |
| Additional final failure | `test_actual_supervisor_death_surviving_child_holds_lock`: supervisor could not establish its own PID identity, so admission correctly stopped and no ready child appeared. This is a new unresolved execution failure, not a baseline-equivalent pass. |
| Process visibility | An earlier aggregate also raised `psutil.NoSuchProcess` for its own live PID during the existing local HTTP/RSS test. One isolated check passed; the final aggregate passed that test. The contradictory process visibility is retained as a runtime limitation, not erased by the recheck. |
| Source hygiene | Compilation and `git diff --check` pass. |

The five baseline failures remain in `test_pr2_final_amendment_migration_and_intelligence_processing.py`: selection of outstanding applications, unchanged-summary exclusion, extraction limit, failure isolation and workload bound. Four encounter the existing API-key requirement despite fake factories; one encounters the missing SOCKS dependency during SDK construction. No paid call was made. Complete test IDs and counts are in `docs/reports/p0a-gate-a-test-results.json`.

An earlier focused run passed 51 tests with five integration skips, before the stronger missing-PID admission check. It does **not** supersede the final six-failure aggregate. Earlier plain-subprocess tests are not proof of browser-descendant cleanup. No claim is made that real browser processes/locks were demonstrated orphan-free here.

**Exact capability needed:** an authorised non-production Linux development runtime able to run PostgreSQL as a non-root user and the matching Playwright Chromium binary, with loopback networking, child-process signals/groups, file locking and reliable `/proc` PID/start/descendant visibility. The existing runtime cannot provide the outstanding evidence. Current operating instructions and runnable checks are in `P0A_OPERATING_INSTRUCTIONS.md`.

## Narrow SQL changes supported by the trace

The original synthetic reproduction was re-run with SQLAlchemy cursor and transaction events on 48 parent references, 192 citations and three invocations. No portal/model call or configured application database was used.

| Category | Before | After | Explanation |
|---|---:|---:|---|
| Work-discovery SELECTs | 147 | 6 | Replace one lookup per reference per invocation with one council work-state map per invocation; retain the three citation projections. |
| Reservation/result refresh SELECTs | 96 | 0 | Remove redundant refreshes after conditional writes; production sessions already retain state after commit. |
| Result-sharing SELECTs | 383 | 59 | Read a parent's proposal/qualification once per fan-out; avoid reloading each child solely to update its known ID. Keep bounded child selection and conditional eligibility. |
| Other SELECTs | 63 | 63 | Council reference/work/due snapshots, existing-parent upsert checks and counters remain. |
| INSERT/UPDATE statements | 384 | 384 | 48 work inserts, 48 parent evidence inserts, 48 reservations, 48 outcome writes and 192 child updates retained. |
| SAVEPOINT/RELEASE statements | 96 | 96 | Unique work insertion remains safe around a competing insert. |
| Total cursor statements | **1,169** | **608** | **561 fewer reads**, with unchanged synthetic outcomes and continuation order. |
| Commit boundaries (separate from cursor count) | **294** | **294** | 48 reservation + 48 result + 192 child commits, plus six stage state commits. |

The narrow changes preserve conditional owner transitions and independently committed child progress. Already-loaded child objects are synchronised without another SELECT/UPDATE. A regression found during this work exposed stale in-session child values; that was corrected, and result-sharing/crash-recovery checks passed afterwards. No broad ORM refactor was performed.

Trace: `docs/reports/p0a-gate-a-sql-trace.json`. Reproducer: `scripts/diagnose_parent_lookup_sql.py`. These are statement counts on synthetic SQLite, not bytes crossing Supabase, production performance, or production egress savings. Remaining per-child commits are intentionally retained; fewer writes would need separate durability evidence.

## Specification conformance and material deviations

1. **Switch replacement corrected and disclosed.** The first implementation replaced the reviewed MODE input with ACTIVATED/DISABLED and ignored MODE. This was an undocumented deviation. MODE is now accepted again. ACTIVATED is an additional production release guard; DISABLED remains a compatible disable alias. Either disable input wins over activation; all values are validated first, including empty/malformed values. Production remains inactive by default. `P0A_OPERATING_INSTRUCTIONS.md` is the current operational contract; the hash-locked specification is not silently edited.
2. **Effective configuration visibility corrected.** Limits are now validated before database bootstrap, emitted once and stored in run progress. Existing CLI council timeout is retained; the specification's proposed council environment naming was not added. No 12-minute limit or fixed 20-attempts/day promise was introduced.
3. **PID evidence tightened.** The owner now refuses admission when its own start identity is unavailable instead of recording a null identity. This deliberately exposes the current runtime's limitation; the guard is not relaxed to obtain a green test.
4. **Cancellation mechanism remains unproven with Playwright.** The logical deadline currently uses POSIX SIGALRM/BaseException interruption; the specification described cooperative cancellation. Synthetic synchronous deadline tests are not evidence that this safely unwinds Playwright's greenlet/driver state. The real Chromium cancellation→cleanup→next-work test must execute; until then this remains a material unverified deviation.
5. **Hard supervision during DB stalls is an open implementation issue.** Bootstrap and synchronous progress callbacks can block the same thread that polls time/memory. The invocation clock also starts after bootstrap/reconciliation. Therefore the code does not yet prove the specification's hard whole-invocation bound during a database stall. This is a code-inspection finding, not a measured production incident. It needs bounded DB operations and supervision independent of blocked persistence, with an offline blocking-callback test, before claiming full conformance. No broader queue/stage-continuation design or provider change is proposed.
6. **Some live-contract fields remain release checks.** Service/type/instance identifiers, sole discovery entrypoint, actual deployed revision and scheduler admission evidence have not been freshly verified in this offline cycle. No foreign-owner advisory-lock fallback was introduced.

The additive table, identity rules, result sharing, retry caps, fairness, page correction, partial/failure distinction and safe rollback remain in the agreed scope. The completed agent foundations and wider roadmap were not changed. Full Gate A acceptance is explicitly withheld for items 3–5 and the outstanding PostgreSQL checks.

## Stockport: separate proposed remedy, not implemented

The retained source evidence shows four primary HTTP attempts and default 429 sleeps of 5/10/15/20 seconds, including a sleep after final exhaustion; subsequent records can continue. A 429 is deliberately excluded from the existing host-outage circuit. The month scraper buffers results before the commit, so repeated interruption can lose uncommitted progress. Parent lookup changes cannot resolve that primary behaviour.

Propose a **narrow primary rate-limit stop**: on exhausted HTTP 429, retain a typed rate-limit outcome and Retry-After, stop further primary detail requests for that council invocation, remove the pointless final backoff sleep when no retry remains, and report primary coverage incomplete/nonzero. Keep host-outage and rate-limit reasons separate. Use the next scheduled invocation for a bounded retry; no extra scheduler or general stage cursor. This first remedy limits waste; it does not itself guarantee forward progress through a buffered month under persistent rate limits. Partial-primary persistence would require its own narrow design/approval if representative trials demonstrate replay starvation.

Acceptance before any equivalent Stockport trial: synthetic repeated-429 responses produce no next-record requests after exhaustion; numeric and HTTP-date Retry-After are honoured; no unbounded waits; the final failed attempt does not sleep solely to make no further request; primary incomplete is never reported successful; committed pre-existing evidence is retained; a subsequent healthy synthetic run completes correctly. A later separately approved limited live trial must show primary completion and later stages reached, or provide an evidenced outage/gap decision. Repeating the same timeout with no useful commits fails acceptance.

**A Manchester/Salford-only release candidate is not platform-wide discovery readiness.** Stockport remains excluded. Passing limited smoke cannot close the all-council seven-cycle reliability/freshness acceptance.

## Rollout, smoke and rollback — still proposals

Migration-first: close offline checks and code gaps; approve the exact tested commit; verify/suspend conflicting discovery paths; apply and verify only the approved additive migration before consumers; confirm deployed SHA and runtime/ownership identifiers while inactive; approve explicit council scope and trial limits before activation. Do not activate the unchanged all-council default command for a limited release.

Proposed scope remains Manchester, then Salford after prior termination, current-month only, no AI/historical recovery. Parent trial caps: five distinct references, six attempts, 60-second start budget/125-second stop envelope; council ceiling 3600 seconds remains a trial hypothesis, not a healthy target. Read bounded eligible metadata before the run so the intended parent and document→refresh paths can actually be exercised. Agree these values and stop criteria before any live run. No Stockport trial is included.

Rollback: suspend the scheduler, verify active process groups terminal, then revert while retaining the safety entrypoint where possible. Keep discovery suspended if reverting to code that ignores switches. Retain additive schema, continuation state, committed evidence and health history; no destructive downgrade, mass clearing or replay. Reconcile only from positive owner termination evidence. Resume only after renewed bounded-smoke approval.

Supabase egress attribution, actual application connection-path verification and AH remediation remain separate. None was claimed resolved by the synthetic SQL reduction.
