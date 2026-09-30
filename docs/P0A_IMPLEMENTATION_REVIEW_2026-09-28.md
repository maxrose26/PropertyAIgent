# P0-A local implementation review

> Historical progress snapshot for `cd1d0bd`, accepted as a progress report only. Current findings and operating instructions are in [Gate A follow-up](P0A_GATE_A_FOLLOWUP_2026-09-28.md) and [P0-A operating instructions](P0A_OPERATING_INSTRUCTIONS.md). The later report records additional unclosed checks; this snapshot is not release approval.

**Status: local review candidate; production activation blocked. Offline Gate A is not fully closed.**

The approved code and independent offline checks have been completed where this environment permits. Disposable PostgreSQL verification remains unavailable, and browser-specific memory/cancellation behaviour has not been validated with real Chromium. These are explicit remaining gates, not passing results. Deduplication removes duplicate work; limits contain exposure; diagnostics investigate memory growth. This is not a demonstrated fix for the original Manchester OOM.

## 1. Exact review baseline

- Feature branch: `feature/p0a-bounded-discovery`.
- Implementation commit: `cd1d0bdd1c154c31e790a0ab5ded63c4a1908d31`.
- Preserved documentation branch: `docs/astra-reliability-handover-20260928`, commit `301a56b3cde781f37e5f5bb0ffaded6537d5ca14`.
- Application baseline: `6fd4202f2cc8cbc9cd5a664c3f0a71019933eb5a`.
- Reviewed specification: `specifications/019-p0a-bounded-discovery-reliability.md`.
- SHA-256 verified before implementation and again at packaging: `c007e2b2912ae5d8817142c32fdf35e0000f72d4fa127d5c83e32e6ef10970f8`.

The specification, wider roadmap, vision, architecture and completed acquisition-agent foundations were not revised by this implementation. This report is committed separately after the implementation commit. Nothing was pushed, merged, deployed, migrated in production, scraped live or evaluated through a paid model.

## 2. Changes and boundaries

| Files | Implemented behaviour |
|---|---|
| `app/pipeline/lookup_outcome.py`, Idox and Arcus adapters | Typed found/not-found/ambiguous/transient results; full-reference trim/casefold matching; recognised empty states only; conservative rejection of conflicting/unreadable/incomplete result states; 60-second POSIX logical deadline around existing retry layers. |
| `app/pipeline/parent_lookup.py` | Council/reference deduplication, durable reservations, cooldowns, optional bounded transient retry behind selected first attempts, successful-result reuse, repeatable child updates, stable continuation order and narrow Application projections. |
| `app/db/models.py` | Additive `ParentLookupWork`, council/reference uniqueness, due-work index and nullable `ScrapeRun.progress`. Existing migration machinery discovers and applies these additions explicitly. |
| `app/pipeline/discovery_owner.py` | Sole-service runtime admission, invocation/host/process identity, exclusive inherited file lock, positive recovery evidence, legacy-row handling and matching interrupted reservation release. No advisory-lock fallback. |
| `scripts/run_daily_councils.py` | Least-recently-started council order, bounded output, silent-child monitoring, process-group termination/cleanup, cgroup containment, global and parent-stage supervision, durable structured progress and truthful exit status. |
| `app/pipeline/page_owner.py`, `run_weekly.py` | Shared current-page handle across document recycling and evidence refresh; independent creation/close-failure handling. This defect is separate from the earlier OOM. |
| Memory diagnostics, acquisition health, scraper-health reporting and Council Dashboard | Container availability/peak reporting, parent deferrals, cleanup failures, stage-return/interruption markers, historical incomplete visibility and an operator coverage expander. Unknown final health cannot refresh the successful-run timestamp. |
| Focused tests, affected existing fixtures, offline test harness | Real subprocess lock/death/cleanup tests, synthetic continuation/outcome tests, page regression, SQLite migration, conditional local PostgreSQL test and reproducible network-blocked comparison. |

There is no general queue, general stage continuation, AH correction, agent redesign, egress remediation, primary Stockport retry change or historical recovery.

## 3. Ownership and continuation review

Production admission requires the existing daily cron service ID, `RENDER_SERVICE_TYPE=cron`, a nonempty instance ID and explicit activation. These identifiers and the sole entrypoint must still be verified on the target runtime before activation. The implementation does not assert that they were freshly verified during this offline cycle.

The supervisor takes an exclusive host file lock and passes its descriptor to each council child. Closing the supervisor descriptor does not unlock the child's inherited descriptor. A real test kills a supervisor while its child survives, proves a competing owner is rejected, then kills the child and proves ownership becomes available. Other real subprocess tests cover inherited admission, deadlines, hard-memory termination and cleanup after a callback failure.

Each council row records invocation, service/instance, host boot and PID-start identities before work; child PID identity is added at spawn. Parent reservations reference the exact council row and validate its invocation/council ownership. Reservation/result writes are conditional. A new same-service different-instance execution can reconcile an old owned row only under the reviewed scheduler successor contract. Same-instance recovery requires process-identity absence; access errors do not count as absence. Foreign owned execution is unresolved, not reclaimed by age. Historical unowned running rows remain visible and do not block new discovery.

Reservations commit before requests. Recovered reservations keep their queue position and attempt history but receive no invented lookup result. Recovery also covers the small failure window between terminal run recording and reservation release. Found parent evidence commits with its result; fan-out can resume after interruption without another request. Children commit individually, so an interrupted fan-out can continue idempotently.

Due order is `COALESCE(last_started_at, first_seen_at)`, then the full normalised reference. Not-found and ambiguous outcomes cool down seven days; transient outcomes at least 24 hours, extended by Retry-After when necessary. A changed citation fingerprint/adapter version allows a bounded earlier attempt. This does not bypass time/count/memory limits. Retry-After HTTP-date handling is restricted to the typed parent path; existing primary retry behaviour is preserved.

## 4. Configuration and health semantics

| Setting | Local implementation default / meaning |
|---|---|
| `PROPERTYAIGENT_DISCOVERY_ACTIVATED` | Production remains blocked unless exactly `1`; this review does not authorise setting it. |
| `PROPERTYAIGENT_DISCOVERY_DISABLED` | `1` stops new supervisor/child admission with nonzero exit. It is not a guarantee that an already-running process stops. |
| `PROPERTYAIGENT_DISCOVERY_PARENT_ITEMS` | 25 distinct selected references per parent stage. |
| `PROPERTYAIGENT_DISCOVERY_PARENT_ATTEMPTS` | 30 logical attempts, including optional retries; maximum two per selected reference. |
| `PROPERTYAIGENT_DISCOVERY_PARENT_SECONDS` | 180 seconds for starting parent work. Supervisor stops a stuck parent stage after this budget plus 60 seconds, allowing at most five seconds termination grace: default 245-second envelope. |
| `--timeout-seconds` | Existing 3,600-second council trial ceiling retained; not a measured healthy production target. Up to 15 seconds termination grace. |
| `PROPERTYAIGENT_DISCOVERY_INVOCATION_SECONDS` | 9,000 seconds (150 minutes), a configurable trial hypothesis; remaining scope is deferred and overall exit is nonzero. |
| Memory | Sample container usage every two seconds; report every 30 seconds. Stop parent starts at 70%; terminate active council at 80%, five-second grace then process-group kill; start subsequent councils only below 60%. Missing cgroup data is explicitly unavailable, never replaced by summed RSS. |

Routine memory DB checkpoints are throttled; stage transitions and parent reservations/results remain durable. Existing status vocabulary is preserved. Parent budget exhaustion is partial coverage, normally exit zero when primary work completed. A child crash, hard stop or failed primary scrape yields failed/nonzero. Missing final health yields partial coverage plus process failure/nonzero. A stage returning is recorded as `returned`, not proof all its items succeeded. Unstarted selected councils produce nonzero and a reasoned scope record/log; if none started there is no fabricated completed council row.

## 5. Offline validation evidence

Machine-readable results: `docs/reports/p0a-offline-test-results.json` and `docs/reports/p0a-synthetic-reproduction.json`.

- Final focused suite: **40 passed, 1 skipped** (3.88 seconds). The skip is disposable PostgreSQL.
- Affected-suite run: **319 passed, 5 failed, 1 skipped, 1 deselected** (27.55 seconds).
- Same affected baseline suites: **281 passed, 5 failed, 1 deselected** (24.88 seconds).
- The final focused run adds two regression tests after the aggregate run; totals overlap and must not be added together.
- Exactly the same five failing test IDs occur on baseline and feature. Four fail because their intelligence-processing fixtures do not provide `OPENAI_API_KEY` despite fake client factories; one encounters a missing SOCKS dependency during SDK construction. No paid call was made. These unrelated tests were not changed to hide the failures.
- Existing Chromium renderer-RSS comparison explicitly deselected: local browser binary unavailable. The independent document→refresh test executes the actual pipeline stage functions with a deterministic offline page double, reproduces the old closed-page failure and passes with the shared page owner. It is not a real Chromium memory test.
- Actual subprocess tests pass for inherited locking, killed supervisor/surviving child, lock availability after cleanup, callback failure cleanup, time supervision and injected hard-memory containment.
- Source compilation and `git diff --check` pass.

The committed `tests/p0a_offline_guard.py` blocks external HTTP, stubs the legacy independent TLS HEAD probe and isolates document folders. Initial exploratory runs identified existing fixtures that otherwise make certificate probes or globally mock filesystem metadata. The final feature/baseline comparison uses the same isolation harness. Localhost-only synthetic HTTP streaming is permitted; external portals and model calls are blocked.

The synthetic fixed cohort contained 48 references cited by 192 applications. Three invocations attempted 20, 20 and 8 distinct references, leaving 28, 8 and 0 due references; 144 duplicate requests were suppressed. All citing children received the committed result. The measured run took 1.217 seconds, with 1,175,918 bytes of peak Python allocations, 1,169 SQL statements and 25,843 bytes of serialized work-state payload. These are synthetic Python/database measurements, not container memory, actual network transfer, production throughput or egress attribution. Individual durable commits contribute to the query count; normal operating usage still needs measurement.

## 6. Migration and compatibility

SQLite migration testing starts from a schema missing the new table and progress column. The existing explicit `migrate_schema()` creates/adds only those missing objects on that otherwise-current fixture; a second invocation is a no-op. Unique constraints and the due index exist; existing Application/agent columns are unchanged. Legacy progress is nullable. Old code can ignore the additions; no destructive downgrade is required.

A PostgreSQL test is included but has **not executed**. It accepts only an explicitly supplied `P0A_TEST_POSTGRES_URL` pointing to a loopback, empty database named `p0a_test_*`; it never consumes the application's `DATABASE_URL`. The environment has no PostgreSQL server, and package installation failed on OS user/group switching permissions. No permission bypass was attempted. PostgreSQL migration/uniqueness/transaction behaviour must pass on a disposable local server before release approval.

Existing non-SQLite application startup verifies schema rather than migrating it. Deploying consumers before the additive migration can therefore fail startup; migration approval and ordering remain mandatory.

## 7. Stockport and separate operational work

The specification's retained timings remain historical evidence, not a new production check. Stockport's primary month scrape collects results before its stage commit; interruption repeats uncommitted work. Its HTTP loop permits four attempts, with default 429 waits of 5, 10, 15 and 20 seconds, including a wait after the final failed attempt. The primary scrape can continue to another record after that exhaustion. The host-outage circuit intentionally does not treat HTTP 429 as a host failure, and the primary collection loop has no new P0-A durable cursor. This supports the earlier observed approximately 53-second exhausted-record pattern; it does not explain every Stockport failure. Parent deduplication cannot repair that primary-stage behaviour. No equivalent Stockport trial should be scheduled until its retry/circuit remedy and useful-progress expectations are separately reviewed.

Supabase access/freshness checks and egress attribution remain separate and outstanding. This offline implementation cycle did not exercise the application's real PostgreSQL/pooler connection, inspect new production usage or change billing. SQL Editor access alone is insufficient evidence of that application connection path. No upgrade is recommended by this report.

## 8. Remaining gates and bounded smoke proposal

Before any activation:

1. Execute disposable PostgreSQL migration/constraint/owner-transition checks and validate real local Chromium deadline/page cleanup behaviour. This is the smallest remaining offline evidence work; it needs an appropriate local runtime, not production data.
2. Verify target service/type/instance identifiers, sole active discovery route and scheduler guarantee. Specifically exclude overlapping historical rebuild, standalone weekly scripts, manual alternatives and legacy deployed code. If that assumption fails, stop and bring the ownership decision back; do not substitute advisory locks silently.
3. Review the exact tested release commit, additive migration and migration-first order. Confirm all activation/safety settings before any scheduled run.
4. Agree representative trial limits and exact smoke scope. Do not infer production budgets from the synthetic reproduction or adopt a 12-minute limit.

**Proposed smoke, not executed or authorised:** after those gates, select Manchester only for the first controlled sole-entrypoint invocation, then Salford for the independent document→refresh path after the first invocation is terminal. Use the existing 3,600-second council trial ceiling, current-month scope, no AI stages or historical arguments, and initially lower parent caps to five unique references, six attempts and 60 seconds start budget (125-second parent stop envelope). Record the existing eligible cohort before execution; do not force flags, rewrite evidence or broaden recovery. Review candidate/stage counts first; a council with no eligible document→refresh work cannot validate that path. Stockport is excluded.

Observe the actual strict outcomes, selected IDs and older eligible ordering, partial/deferred scope, child cleanup, memory peak and committed progress. A second separately agreed bounded invocation verifies durable continuation and idempotent sharing. A primary scrape failing to complete, repeated replay without useful commits, ownership contradiction, unexpected incomplete row, cgroup threshold stop or missed downstream input blocks acceptance; a successful deployment alone proves none of these.

After passing smoke, seven scheduled daily cycles establish sustained health under the specification's criteria: representative stage completion, justified memory/duration bounds, measured first-attempt capacity, fixed-cohort progress with cooldown/outage/arrival accounting, and a small metadata trace into downstream processing. This observation window does not block independent AH design or benchmark preparation. Any AI execution remains subject to its separate approval.

## 9. Safe rollback

1. For a post-release incident, suspend the cron at the scheduler and verify that the active invocation and its process groups are terminal. Turning off activation/setting disabled can prevent new-version starts but is not sufficient for old code or an already-running process.
2. Keep discovery suspended before reverting code. Older discovery ignores the new safety switches and must not be automatically restarted with an uncontrolled workload.
3. Retain the additive table/column, committed applications/documents and structured health records. Do not delete continuation state, clear pending references wholesale or reverse committed evidence. Old readers ignore added fields.
4. Preserve incomplete owner records for evidence-based reconciliation when compatible code is reintroduced. Do not mark them interrupted solely from elapsed time.
5. Re-enable only an explicitly approved bounded discovery version after the runtime, schema, trial and ownership gates are satisfied.

## 10. Review decision

Review the local implementation and remaining evidence gaps; this is **not a request to deploy**. PostgreSQL and real-browser verification remain incomplete, so full offline acceptance and production release approval are withheld. The five baseline test failures should be tracked separately without expanding P0-A into intelligence-processing repair. No new product feature or wider roadmap decision is required.
