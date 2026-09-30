# P0-A final preflight — Gate A OPEN

No release is authorised. This supersedes the correction report as current evidence; prior reports are retained as historical snapshots.

## Exact state and reproducibility

- Branch: `feature/p0a-bounded-discovery`.
- Starting HEAD verified clean: `2be728e804424091dc4e0a01f94c8344b54d25d0`.
- New exact tested candidate: `e1b53eb4b942eb7b27fa14b49a60731eb2179293`; clean tree at test start.
- Subsequent reporting commit adds only this review and results JSON; code, tests and runner remain identical to the candidate.
- Runner Git blob: `a82af5ab4f49675a92cba4ad10f9f6fae11f5969`.
- Runner SHA-256: `7b916e9824857ca679ae2ae6525eccd9581338263e6a424e1b9abbc4f7617065`.
- Dependency snapshot SHA-256: `551b45953598a503c8190a9f924cd6930e04f127ba496770a9a64c8ab05f43d9`; Python 3.12.14.
- Specification 019 unchanged: `c007e2b2912ae5d8817142c32fdf35e0000f72d4fa127d5c83e32e6ef10970f8`.
- Documentation branch remains preserved. No push, merge, production migration, deployment, live scrape, paid call, new infrastructure or production configuration change.

## Concrete corrections

The watchdog is a **separate process**, not a thread. It has no DB dependency. Its command channel is now acknowledged with a bounded wait. A small child launcher waits on a pipe before executing discovery; the supervisor releases it only after registration acknowledgement and a deadline check. The launcher independently checks its absolute deadline before exec. Supervisor loss before release produces EOF, so the unregistered child exits without application work and releases inherited descriptors. This closes the creation/registration work-admission gap without a new ownership mechanism.

Expired deadlines now win over queued extensions, removals and completion messages. Emergency cleanup kills the supervisor first, preventing subsequent starts, then registered process groups. Logging is attempted only after signals, using nonblocking output. Unexpected control-protocol failure also enters cleanup. Process-group cleanup now uses the established group ID (child PID under `start_new_session`), so an already-exited leader does not prevent killing its descendants. The affected existing unit assertion was updated to this contract; the draft's resulting assertion failure was corrected, not labelled baseline-equivalent.

A bounded reader tracks parent-stage control independently of persistence/log callbacks, using the child's monotonic start timestamp. Duplicate start markers cannot restart the clock. A late after-marker cannot turn expiry into completion. Slow callback consumers no longer block this reader: excess queued log lines are counted, and their loss explicitly fails the run rather than claiming complete health. This is a disclosed fail-closed backpressure trade-off, not silent log loss or successful coverage.

## Time bounds and limitations

For a 60-second parent start budget, hard envelope is **60 + 60 + 10 = 130 seconds**, not 125. Operating instructions and an explicit regression assertion now agree. Earlier council and invocation deadlines cap it. Budgets are fixed absolute deadlines; retries and callbacks do not restart them. Returning from the parent stage restores only the pre-existing council deadline, not a fresh council budget. The approved specification is untouched; the envelope refinement remains a disclosed deviation.

Normal supervision sends SIGTERM, waits at most 15 seconds for council timeout or five seconds for parent/memory termination, then SIGKILL and bounded leader wait. Council watchdog allowance is 20 seconds, parent allowance ten, capped by the invocation deadline. Invocation deadline itself has no extra grace. The watchdog remains independent of blocked persistence and logging. Hard interruption produces process failure/unverified persisted status, never NOT_FOUND, completed work or successful coverage. Committed evidence is retained for positive-termination recovery.

Cooperative lookup cancellation remains distinct from emergency group termination. Native browser waits/retry sleeps share remaining budget; immediate protocol operations and requests body reads rely on the wider emergency envelope if stuck. No SIGALRM is used.

Limits remain: OS scheduling is not instantaneous; uninterruptible kernel tasks cannot be guaranteed to die promptly; descendants escaping their process group are not covered by group signals. Unexpected watchdog death while the supervisor is already blocked is a remaining single-watchdog limitation; acknowledgements prevent further admission when its loss is observed, not continuous redundancy. These are disclosed enforcement limits. No untested universal no-orphan guarantee is made.

## Actual matched evidence

| Run | Passed | Failed | Skipped | Deselected | Duration |
|---|---:|---:|---:|---:|---:|
| Candidate e1b53eb | 343 | 6 | 6 | 1 | 51.76 s |
| Baseline 301a56b | 281 | 5 | 0 | 1 | 24.47 s |

Same interpreter/dependencies/offline guard. The baseline is `301a56b3cde781f37e5f5bb0ffaded6537d5ca14`. Both explicitly deselect the same legacy renderer-RSS test; it is not passed. Five failures match existing intelligence-processing missing-key/SDK dependency paths, but remain failures. This is not a fully passing suite.

The extra candidate failure remains `test_actual_supervisor_death_surviving_child_holds_lock`: the spawned supervisor cannot observe its process-start identity, fails strict admission and never reaches child readiness. It is not baseline-equivalent. Admission was not weakened. Its assertion now specifically requires “still active”, preventing an unrelated identity error from being mistaken for lock contention.

**PostgreSQL:** one skip; no actual integration execution. Prepared assertions cover additive migration twice, uniqueness/FKs, conditional ownership, transaction rollback, committed reservation survival, unknown interrupted recovery and rejection of a recovered prior owner's completion write, plus statement timeout/subsequent work. SQLite results do not substitute for PostgreSQL.

**Chromium:** five skips; no actual integration execution. Prepared tests require application PageOwner recycling after cancellation and subsequent navigation, document-discovery→refresh lifetime, callback-failure cleanup, supervisor-death lock lifetime and watchdog cleanup during blocked persistence. Relevant descendant identities, including zombies, must disappear and successor admission must succeed before test completion.

| Measured local process check | Elapsed | Assertion basis |
|---|---:|---|
| Blocked bootstrap | 2.402 s | 2 s hard limit + 0 grace + 3 s startup/scheduling margin |
| Blocked reconciliation | 2.354 s | Same |
| Blocked on-start persistence | 2.331 s | Same; child-held lock release checked |
| Blocked streamed persistence | 2.335 s | Same; child-held lock release checked |
| Blocked final status | 2.341 s | Same; child cleanup already complete |
| Unregistered launcher sees supervisor pipe loss | 0.032 s | Exits within 3 s, no work marker, lock released |
| Expired group cannot extend its deadline | 0.349 s | Deliberately pause watchdog past 0.2 s group limit; extension refused, no subsequent work |
| Child ignores SIGTERM | 5.217 s | 0.1 s synthetic parent stop + 10 s cleanup + 1 s scheduling margin; lock released before teardown |
| Full stderr pipe | 0.565 s | 0.5 s hard stop, completion/pipe EOF within 3 s; no logger drain required for termination |

Times include interpreter startup where launched externally. Test scheduling margins are not extra production work budgets. JUnit properties are retained in `docs/reports/p0a-final-preflight-results.json`. These are real local subprocess checks, not PostgreSQL/Chromium evidence.

Cleanup distinction: the explicit surviving-child test deliberately performs test-side SIGKILL only after asserting blocked successor admission; that establishes lock lifetime, not automatic application cleanup. Separate callback/watchdog cases test application-driven cleanup. Browser fixture teardown runs after assertions and cannot turn failed cleanup into a pass. Emergency fixture cleanup after a failed assertion remains cleanup of a failed test.

`git diff --check` and runner shell syntax checks passed. No blocked installation was retried.

## Isolated external handoff — blocked on runtime availability

Only the current execution runtime is connected; no authorised alternate executor is available. Read-only capability checks found no PostgreSQL server tools, Docker/Podman or usable Chromium here. Process visibility remains unsuitable. Therefore external verification has **not** been executed; stop after packaging.

**Exact user action:** download `p0a-final-preflight.bundle` and give it to an operator of an existing authorised non-production Linux runtime, or connect that runtime to this workflow. It must provide non-root Python 3.12.14, the recorded dependency snapshot, matching Playwright Chromium/shared libraries, PostgreSQL, loopback-only networking, process groups/flock and reliable `/proc` plus zombie reaping. No new paid infrastructure is requested.

On that runtime, read `verification/P0A_GATE_A_HANDOFF.md`, checkout `e1b53eb4b942eb7b27fa14b49a60731eb2179293`, set `P0A_EXPECTED_COMMIT` to that SHA and run `bash verification/p0a_gate_a.sh`. Return its logs, JUnit XML and manifest files. A local Git bundle supplies candidate and baseline history without any push. Dependency provisioning must happen separately before network-isolated execution; do not repeat installations here.

The runner rejects inherited production/model/PG/owner inputs and repository/ancestor `.env` files before Python imports or database initialisation. It clears Python/pytest override inputs, verifies clean exact commit and dependency snapshot, records the runner blob and manifests, creates a fresh loopback-only disposable PostgreSQL cluster, and stops it on exit. Tests also refuse a nonempty or non-loopback target. No production URL or secret is needed.

## Remaining release checks

Gate A remains open for real PostgreSQL/Chromium and reliable-runtime ownership evidence, plus any resulting candidate-specific defect. A direct PostgreSQL pass does not establish transaction-pooler compatibility. Render service/instance identifiers, sole discovery entrypoint, scheduler successor guarantees and actual DB-path timeout behaviour remain separately verified release preconditions.

Any release still requires exact candidate/migration approval, migration-first rollout and agreed Manchester/Salford-only trial limits/smoke. Both remain limited candidates, not release-ready and not all-council readiness. Stockport retry/circuit work remains a separate proposal. Seven-cycle sustained observation remains separate from smoke and unrelated AH design/benchmark preparation.

Rollback remains suspend discovery, positively verify process termination, then revert only to an approved bounded state or keep discovery suspended. Old code may ignore the new switches. Preserve additive schema, evidence and run-health records; no destructive downgrade, age-only recovery or bulk replay. No SQL optimisation, AH correction, egress claim or wider roadmap change was added. These corrections do not establish the Manchester OOM cause.
