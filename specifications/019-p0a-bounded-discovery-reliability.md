# P0-A — bounded discovery reliability

**Status:** proposed implementation specification, awaiting Product Owner review.
**Date:** 28 September 2026. **Baseline:** `6fd4202f2cc8cbc9cd5a664c3f0a71019933eb5a`.
**Authority:** direction approved; specification only. No implementation, migration, release, production correction/recovery, paid evaluation or billing change authorised.

Read with [operational evidence](../docs/ASTRA_OPERATIONAL_REVIEW_2026-09-28.md) and the [current roadmap](../docs/PRODUCT_ROADMAP.md). Preserve completed lifecycle, acquisition facts, mandate, evaluation, persistence, identity and taxonomy milestones.

## 1. Objective and limits of the claim

A buyer needs evidence coverage that continues to advance across every configured council, with explicit gaps and failures. The observed Manchester loop repeats unresolved parent requests; a container OOM can prevent later councils receiving attention.

Three distinct claims govern acceptance:

- Deduplication removes observed duplicate work.
- Work/time limits bound exposure and preserve opportunities to process other work.
- Instrumentation investigates memory growth. Neither of the above is a proven OOM root-cause fix.

Document-discovery page ownership is a separate defect: a locally replaced page is not returned to the caller before evidence refresh. Fix and test it independently. It occurs after the Manchester failing stage and does not explain that earlier OOM.

No new orchestrator, autonomous agent, broad ORM rewrite, AH correction, mass reprocessing, fuzzy identity resolver or unrestricted recovery belongs here. P0-A does not resolve Supabase egress.

## 2. Exact proposed module scope

| File/module | Proposed responsibility |
|---|---|
| `app/pipeline/parent_lookup.py` (new) | Typed lookup outcomes, stable reference key, bounded due-work selection, result sharing, continuation transitions and fan-out using existing upsert/qualification logic. No duplicate planning-truth model. |
| `app/pipeline/run_weekly.py` | Delegate parent stage; pass run identity/budgets; use one explicit mutable page owner across discovery and refresh; emit structured progress/final health. Preserve stage order and existing fact semantics. |
| `app/scrapers/arcus_portal.py`, `app/scrapers/idox_portal.py` | Add narrowly scoped detailed parent-lookup adapters without breaking legacy callers; distinguish observable no-result from ambiguous/unreadable/transient outcomes; enforce exact identity before any upsert. |
| `scripts/run_daily_councils.py` | Least-recently-attempted council ordering, bounded council supervision, memory sampling/stop, durable stage progress, explicit process/coverage classification. |
| `app/pipeline/acquisition_health.py` | Add deferred-work and outcome counters; retain primary failure precedence and partial-vs-failure semantics. |
| `app/diagnostics/memory.py` | Reuse process-class RSS; add best-effort cgroup current/limit sampling and throttling. Never log secrets/document bodies or raise into the pipeline. |
| `app/db/models.py`, `app/db/session.py` | One additive parent-work table and nullable structured progress on ScrapeRun, with explicit migration/verification through existing machinery. No changes to Application facts or agent tables. |
| `app/reporting/scraper_health.py`, `app/ui/pages/4_Council_Dashboard.py` | Small existing-health-view extension: stage coverage, deferred count, oldest pending age, incomplete/unknown-liveness indicator. No new dashboard or generic observability platform. |
| `tests/test_parent_lookup_continuation.py` (new) | Outcomes, identity, fairness, retries, interruption and committed fan-out. |
| `tests/test_discovery_page_lifetime.py` (new) | Offline discovery→refresh regression and cleanup. |
| Existing daily-discovery, health, memory and migration tests | Extend only contracts changed by this gate; add a focused council-supervision test module if existing fixtures cannot express them cleanly. |
| `render.yaml` | Only proposed conservative limit environment declarations and safety-mode setting, if approved. No plan, cadence, provider or unrelated job change. |

Implementation must inspect scoped AGENTS/CLAUDE guidance again. If broader changes become necessary, return to review rather than expanding this list silently.

## 3. Continuation contract before storage

### 3.1 References within a council

Each distinct `(council, reference)` is a work item shared by every citing application. Canonicalisation is limited to trimming surrounding whitespace and case folding, consistent with exact-reference comparison. Never remove separators, truncate, expand numeric citations or infer aliases.

At each run, discover citations with narrow Application projections, coalesce keys, and reconcile already-present exact parent references first. Select eligible unresolved work ordered by `COALESCE(last_started_at, first_seen_at)` ascending, then stable key. Never use unconditional NULL-first priority: continual new arrivals must not jump ahead of older eligible retries. A reservation moves that item to the current time; deferred items retain their earlier queue age. Before external lookup, durably advance `last_started_at` and reserve that attempt; commit its owner and attempt count. Completed outcome and retry due time commit promptly. The row is operational state, not a planning conclusion.

The reservation-before-request rule means a crash does not keep the same reference at the head forever. The next run sees its reservation and moves older eligible work ahead of it. An interrupted request's result remains unknown: reservation is not completion, absence or a negative finding.

Fairness example with capacity two: eligible A,B,C,D. Run 1 reserves A then dies. Once its owner is proven terminal, run 2 selects B,C; run 3 selects D then A if due. A's repeated failure cannot monopolise the front. New items arriving during a run join the next snapshot. Newly arriving work must not continually pre-empt old eligible work: use a fixed discovery cutoff per run and age ordering; sustained arrival above measured service capacity is an explicit overload, not a fairness guarantee.

Successful results fan out deterministically to all current citing applications, without another portal request. New citing children in later runs use the exact parent already in Application. Commit the parent upsert/outcome first, then apply child updates in bounded transactions; on interruption, the next run repeats only idempotent DB reconciliation for remaining children. Parent existence alone must not incorrectly imply fan-out completed. Reuse current eligibility rules: already determined children are not overwritten merely to force convergence.

### 3.2 Councils

Use existing ScrapeRun history to order selected councils by their latest **attempt start**, oldest/null first, tie-breaking council code. Commit the running row before spawning, so a council that kills the container moves to the back on the next invocation. This replaces fixed alphabetical ordering; it requires no separate council cursor.

Example: Bolton/Bury finish, Manchester kills the process. Oldham and later untouched councils precede Manchester next time. A missing start record after a DB error is not silently treated as an attempt: refuse that child and report bookkeeping failure. Configured but unattempted councils appear in the invocation's planned/remaining list.

One invocation attempts each selected council at most once; a supervisor-terminated child is failed and the parent proceeds if safe. There is no same-run whole-council retry. A configurable global trial deadline stops new starts, terminates any active child within the recorded grace, and records remaining councils as deferred; section 6 defines the provisional value. Next invocation uses the same history-based fairness. CLI council subsets preserve their explicit scope and do not imply platform-wide completion.

**Guarantees are conditional:** with a finite eligible backlog, available services and recurrent runnable slots, every eligible item/council advances. Permanent service outages, repeated container termination before DB access or demand above capacity cannot have a finite completion guarantee. Surface oldest pending age and missed coverage instead of concealing that limitation.

### 3.3 Exclusive ownership and automatic recovery

**Verified scheduler contract, 28 September:** [Render Cron Jobs](https://render.com/docs/cronjobs#single-run-guarantee) documents one active run per cron service; scheduled starts wait for the active run to finish, and manual triggers cancel the active run first. This guarantee is service-scoped, not database-wide. [Default environment variables](https://render.com/docs/environment-variables) document `RENDER_SERVICE_ID`, `RENDER_SERVICE_TYPE` and `RENDER_INSTANCE_ID`; the latter identifies an instance, not a documented cron execution ID. Do not invent a run-ID variable or use undocumented variables. The earlier authenticated dashboard confirmed daily discovery service `crn-d9sv93vavr4c73f98rb0`. After renewed sign-in, the dashboard again confirmed that service, command `python -u -m scripts.run_daily_councils`, 05:00 UTC schedule and deployed `6fd4202`. Runtime variable presence has not been inspected. The historical-rebuild service is a separate executable route: its Runs page shows a January 1, 03:00 UTC schedule and one past manual run, August 13 (2h49m52s), with no current active run shown. Therefore exclusivity is valid for daily discovery only; the production child admission guard must reject a future historical/standalone invocation of this path unless separately reviewed. No schedule was changed.

**Recommended minimal contract:** use that single cron service as the sole production discovery entrypoint, combined with a nonblocking host process lock for accidental duplicate launches within its instance. No distributed queue or additional table. Admission and association are explicit:

1. Before database mutations or council launch, validate runtime service type `cron`, exact approved service ID, and nonempty instance ID; acquire the host lock. Reject a production launch through another service, shell or standalone child route. Environment identifiers are deployment checks, not credentials or a security boundary. Release inspection must establish that no historical rebuild, duplicate cron or other active command can run this discovery path; service-wide uniqueness alone cannot establish that.
2. Create an invocation UUID, record service/instance identity, boot identity, supervisor PID/start identity and contract version. The UUID correlates records; generating it does not acquire ownership. Hold the lock throughout supervision. Pass its descriptor to council children so a surviving child retains it if only the supervisor dies; a new same-instance supervisor cannot then overlap it. Children cannot launch in production without the inherited owner contract. Verify inherited-lock/process-tree cleanup offline. Browser descendants must be terminated with their council process group before releasing ownership.
3. Before each spawn, commit its existing ScrapeRun with that invocation identity, council and planned scope in `progress`. Pass the exact ScrapeRun ID to the child; every ParentLookupWork reservation references it. Subsequent updates require matching invocation/run ownership and the expected previous work state. No separate invocation row is required: no council row means no reserved parent work exists. A duplicate host process exits nonzero without stealing work.
4. On normal completion, finish the council record after child exit and cleanup. Release the supervisor lock only after all children are reaped. On supervisor-only death, a retained child lock blocks a duplicate until that child exits; the platform remains responsible for ending a stuck cron execution. Do not use a heartbeat timeout to reclaim it.

**Next scheduled execution after container failure:** after admission, inspect only incomplete rows with this ownership-contract version. A prior different instance under the *same approved cron service* cannot still be an active cron run when this execution has been admitted, under Render's documented guarantee. Persist this evidence as `same_service_successor_admitted`, old/new instance IDs and invocation IDs, and the observation time. Mark its incomplete runs failed with `interrupted_confirmed`; do not invent the old exit time or OOM reason. `finished_at` is the reconciliation time, explicitly labelled in progress, not a measured death time. Release only its matching IN_FLIGHT reservations as outcome unknown and eligible for bounded retry, preserving their last-start queue position, attempts and committed results. This is normal application recovery under a future approved implementation, not recurring manual SQL intervention.

If Render reuses an instance, the inherited lock plus matching host/boot and positive absence of the recorded supervisor/child PID-start identities must establish local termination; a new UUID or age is insufficient. If neither this evidence nor the same-service successor contract applies, block only the genuinely competing owned execution pending exact platform terminal evidence. Identity or ownership contradictions are exceptional blockers, not routine age-based cleanup.

**Legacy records:** null/older progress without ownership metadata remains visible as historical incomplete, with termination unverified. It cannot own the new ParentLookupWork rows and does not itself block discovery. At rollout, separately verify live execution routes once; do not infer live activity from every old `running` row or bulk relabel them. A known active foreign discovery process is a real blocker regardless of its record age. Do not claim automatic recovery for a foreign-service owner from this service's successor guarantee.

**Boundary and smallest fallback for decision:** the recommended mechanism is sufficient only for the verified sole-service deployment. If release inspection cannot enforce it, stop before coding an alternative: the smallest candidate is a single PostgreSQL session advisory lock shared by all discovery entrypoints, on a dedicated session-capable connection, held until children terminate. It adds no table, but transaction-pooler compatibility, connection loss, orphan children and DB-write fencing must be resolved and tested; acquiring a replacement DB lock alone does not prove an old browser process died. A general leased queue is not proposed. Do not silently implement this fallback or add new credentials. Prefer enforcing the existing single-service boundary if feasible.

## 4. Lookup outcomes and retry policy

| Outcome | Required evidence | Current run | Later runs |
|---|---|---|---|
| `FOUND` | Exactly one authoritative detail record whose full normalised reference matches the requested key | Upsert once; share across all eligible citing children; complete idempotent fan-out | DB reuse, no repeated portal search solely for this citation; existing lifecycle verification retains refresh responsibility |
| `NOT_FOUND` | Search completed, supported result/no-results state positively recognised, no matching or plausible unresolved candidate; no timeout/truncation/error | One logical lookup; no same-run retry | Due after 7 days; new source/adapter evidence may justify earlier bounded retry; never a permanent negative or confirmed absence of a scheme |
| `AMBIGUOUS_IDENTITY` | Multiple possible candidates, shortened citation versus full references, conflicting exact identity/detail, or unresolved candidate identity | No parent selection or linking; save bounded candidate identifiers/reason, no bodies | Due after 7 days, or materially changed citation/adapter evidence; unresolved/manual-review visibility |
| `TRANSIENT_FAILURE` | Network/timeout/rate-limit, unexpected/unreadable result state, incomplete result traversal, adapter error | No negative conclusion; one optional retry as defined below | Due next daily run (at least 24h for persistent technical failure); bounded Retry-After respected; never permanent suppression |
| `IN_FLIGHT` / `DEFERRED` | Reservation without terminal result / not attempted due to cap or circuit | Operational state only; excluded from found/not-found counts | Reconcile owner liveness, then eligible under age order; no invented lookup result |

Retry accounting is explicit: maximum **two logical attempts per reference per invocation**, including the optional retry. Existing adapter HTTP/navigation retries must be inventoried and contained within the logical deadline; do not multiply unbounded retry layers. Retry only transient failure, after a minimum 5-second delay and only when circuit remains closed, memory below soft threshold and enough request/time budget remains. Retry goes behind first attempts already selected, never a tight loop at the queue head. Retry-After exceeding the remaining budget defers it; never evade portal limits. An adapter change/citation change or explicitly approved targeted retry may bypass cooldown, but not count/time/memory caps.

NOT_FOUND and AMBIGUOUS are successful technical responses with unresolved evidence, not proven technical failures. Unknown/unreadable portal content must not map to NOT_FOUND. Dedup cache stores typed outcomes, with a retry allowance for transient failure; it must not use a bare false value that suppresses retries indefinitely.

**Identity gap found during specification:** current Idox fallback selects the alphabetically first result key when several keys exist; it does not itself demonstrate exact identity. The detailed parent adapter must reject ambiguity and verify fetched detail reference before upsert. Arcus's strict equality is retained. Preserve existing caller APIs with wrappers where required, but P0-A parent lookups must use the typed strict path. Tests must include shortened Manchester-style numeric citations; no automatic alias resolution is authorised.

## 5. Storage decision and compatibility

Existing Application rows represent positive planning evidence, not unresolved search attempts. ScrapeRun.detail is truncated and overwritten by checkpoints; ephemeral Render storage and an in-memory cursor cannot survive interruption. Reconstructing retries/fairness from unstructured tails is unreliable. Therefore propose:

1. **`ParentLookupWork`**, unique `(council_code, reference_key)`: raw reference (bounded), first_seen_at, last_started_at, last_completed_at, last_outcome, next_eligible_at, total logical attempts, owner_scrape_run_id (nullable FK), resolved_application_id (nullable FK), bounded reason code/metadata (including adapter version and a citation-input fingerprint for justified cooldown invalidation), and work-contract version. Index on council/due/order fields. No source document bodies, credentials or inferred planning facts. Multiple citations remain derived from Applications; no duplicate child-link table.
2. **`ScrapeRun.progress`**, nullable versioned JSON: versioned service/instance/invocation and process owner identity; recovery evidence and observation time; planned council scope/order; stage attempted/completed/deferred/failed counters; budget/reason; last heartbeat; peak cgroup/RSS values; terminal evidence when known. Existing `status`, `detail`, counts and timestamps remain compatible; structured progress must not be overwritten by log-tail updates. Commit transitions and throttle routine updates to at most once per 30 seconds, except attempt reservations/outcomes needed for recovery.

Lazy population for the selected council only; no production bulk backfill. Migrations are additive and explicit via existing schema migration path, not app startup. Older code ignores new state; it must not be allowed to run discovery unbounded during rollback. Legacy rows have null progress and render as “coverage detail unavailable”. Do not change or migrate existing agent persistence/fingerprints or AH records.

Concurrency-safe unique insert and conditional owner transition remain required even under single-run operation. Admission and recovery follow section 3.3. Historical unowned rows do not block new work. No time-only lease, additional ownership table or general queue is introduced.

## 6. Proposed starting budgets and memory controls

These are conservative trial values for approval, not established capacity findings. All effective limits are printed once and stored with run progress. Invalid, zero/negative or unlimited values fail closed in scheduled mode.

| Limit | Initial proposal |
|---|---|
| Unique parent references selected/council/run | 25 |
| Total logical parent attempts including retries | 30 |
| Parent-stage start-work budget | 180 seconds; no new lookup/retry after deadline |
| Logical lookup deadline | 60 seconds, shared across its adapter steps/retries; cooperative cancellation; supervisor remains ultimate bound |
| Parent-stage maximum stop envelope | 245 seconds (180 + one 60-second in-flight lookup + 5-second cleanup) |
| Council wall limit | Production value not selected. Retain existing configurable 3,600-second ceiling as the initial trial ceiling, plus at most 15 seconds termination grace; not a measured healthy target. No 12-minute default. |
| Whole invocation | Configurable 150-minute trial hypothesis; hard supervisor deadline includes active-child termination, with at most 15 seconds grace. Record interrupted and unattempted scope; nonzero. Not yet demonstrated to fit all councils. |
| Supervisory sampling | Every 2 seconds; emit/store summary every 30 seconds and threshold/exit transitions |
| Container soft threshold | 70% of measured cgroup limit (about 1,434 MiB at 2 GiB): stop launching further parent requests; return explicit partial/deferred state |
| Container stop threshold | 80% (about 1,638 MiB at 2 GiB): supervisor terminates active council, grace at most 5 seconds then kills its process group; council failed; continue only after memory returns below 60% |

Sample the container where available and child process classes separately. Summed RSS is diagnostic and may double-count pages: never label it cgroup usage. If cgroup measurements are unavailable, retain wall/item caps and report memory validation unavailable; do not pass production memory acceptance using substituted RSS. A 2-second monitor can miss a sudden spike: these controls reduce exposure, not guarantee OOM prevention. Diagnose any kill or threshold trip; do not automatically restart/raise resources.

### 6.1 Duration evidence and limit selection

Read-only sampling now covers the 24 September all-council execution, a 23 September Stockport failure tail, and the previously captured 28 September execution. These represent different observed outcomes, **not a statistical capacity baseline**. From 28 September (BST):

| Council/stage | Observed interval | Interpretation |
|---|---|---|
| Bury child | 06:10:50–06:14:13, approximately 3m23s | Reached process exit; does not establish success classification or a percentile |
| Manchester child before OOM | 06:14:15–06:22:34, approximately 8m19s | Incomplete; cannot estimate its full healthy duration |
| Manchester bootstrap plus primary scrape | Child start to scrape-after 06:18:51, approximately 4m36s | Combined interval; do not label all of it scrape time |
| Manchester parent stage | 06:18:51–06:22:34, approximately 3m43s before kill | Censored duration, with observed duplicates; later stages were not reached |
| Bolton | Process exit 06:10:48; precise child-start not retained | Cannot derive a reliable council duration from cron start |
| Individual Bury supporting stages, 28 September | No retained paired timestamps | Unknown, not zero |

Additional authenticated evidence from [24 September logs](https://dashboard.render.com/cron/crn-d9sv93vavr4c73f98rb0/logs?r=2026-09-24%4005%3A00%3A04%7E2026-09-24%4006%3A39%3A11): council subprocess-start to council-after durations were Bolton **5m41s**, Bury **2m35s**, Manchester **8m57s**, Oldham **2m49s**, Rochdale **2m25s**, Salford **3m48s**, Stockport **60m00s**, Tameside **2m04s**, Trafford **3m41s**, Wigan **3m50s**. Final log reports eight successes, zero partial, Stockport/Trafford failed, ten attempted. Thus a failed cron did not mean later councils received no work on that date. Most councils added zero applications; this is not a high-arrival workload benchmark.

Stockport started 06:28:28; its last memory stage marker is primary scrape entry at 06:28:49, with no scrape-after marker before 07:28:28 supervision ended. This matches the existing 3,600-second timeout, not a measured successful hour-long workload. The [23 September Stockport tail](https://dashboard.render.com/cron/crn-d9sv93vavr4c73f98rb0/logs?r=2026-09-23%4004%3A59%3A56%7E2026-09-23%4006%3A38%3A24) shows detail records 93–142 of 147 repeatedly returning HTTP 429 after four attempts, approximately 53 seconds per exhausted record. This is evidenced rate-limit retry consumption on that date; do not infer that every Stockport failure has the same cause or increase its allowance to permit more of that work.

Wigan's 24 September paired stage markers give site linking **1s**, status verification **0s** (zero eligible), related discovery **10s** (zero searches), confirmation **1s** (zero pending), documents **7s** (zero pending), refresh **0s** (zero candidates), allocation scan **1s**, geocoding **49s** (33 candidates), build-status **8s** (zero candidates). These quantify baseline overhead but do not establish document-heavy stage capacity. No full stage timing distribution or per-council workload maximum is available yet.

**Budget consequence:** retaining the one-hour ceiling is an outer safety bound, not a sufficient Stockport solution or permission to repeat its rate-limited run. Stockport's primary scrape has a demonstrated repeat-before-commit risk; require a focused read-only review of its primary-detail retry/circuit behaviour before authorising another equivalent trial. Any code remedy comes back separately for scope approval. Parent deduplication cannot resolve this pre-parent failure. This does not justify adding general stage-continuation infrastructure.

Before selecting production council limits, inspect a bounded sample: latest three available runs per council plus up to two known completed slower runs where retained. Use paired stage markers, workload counts, child start/exit, outcome and deployed SHA; report missing/censored observations rather than treating OOM/timeout intervals as completions. If logs no longer exist, obtain these measurements only during separately approved bounded trials. No production run is authorised by this specification.

Start trials with the existing one-hour ceiling, bounded parents and memory containment; this preserves the existing outer bound without introducing an unsupported shorter failure point. It is not permission to consume an hour routinely. Configure effective child deadline as the lesser of council allowance and remaining invocation allowance; label which deadline stopped it. A start with insufficient measured end-to-end allowance should instead defer the council, unless it is an explicitly approved measurement trial. Unknown councils require that trial decision, not an invented estimate.

For a council with completed representative samples, propose a limit from the observed maximum normal end-to-end duration plus `max(5 minutes, 25%)` headroom, rounded up to minutes. This is a review heuristic, not a statistical guarantee from three samples. Validate workload representativeness and memory independently. The sum of representative council durations plus startup/cleanup margin must fit the invocation budget; otherwise the 150-minute hypothesis fails daily-coverage acceptance. Do not silently accept permanent multi-day council coverage.

Adjustment triggers: any repeated timeout at the same stage, failure to reach later stages on two consecutive non-outage trials, or zero committed progress between attempts requires diagnosis before another unchanged trial. Increase a limit only when measured useful progress and safe memory headroom justify it; lower it only after completed workloads demonstrate margin. If a replay-only stage exceeds the available envelope, review its narrow bottleneck or limit before release. Council rotation alone does not cure intra-council starvation. No new generic stage cursor is authorised.

### 6.2 What interruption preserves, and what repeats

Static trace of the scheduled path in `run_weekly.py`, its delegated stages and daily runner:

| Stage that supervision can interrupt | Durable progress and next-run behaviour |
|---|---|
| Bootstrap/browser creation | No acquisition progress; repeated. Cleanup must terminate owned process tree. |
| Primary current-month scrape | Collects portal results before the stage commit. Interruption before commit loses that month's uncommitted acquisition and repeats the search; after commit facts survive, but the next daily run still searches the current month. No page cursor. A timeout here can prevent all later stages indefinitely. |
| Parent lookup (P0-A) | Reservation/outcome and parent commits plus idempotent child fan-out persist. Next run fairly selects eligible work and reuses found parents; an interrupted request remains unknown. |
| Site linking and opportunity snapshot | Linking commits at stage end; an interrupted transaction repeats. Snapshot is computed and repeated, no durable computation cursor. |
| Status verification, when enabled | Existing per-item result commits and due selection preserve completed checks. In-flight work repeats; a recorded failure/cooldown must not be counted as fresh evidence. |
| Related-application discovery | Existing child upserts commit individually, but `related_search_checked_at` commits **before** all detail fetches finish (both portal branches). A kill can leave remaining details delayed until existing cooldown expires. This is a concrete limitation, not complete resume. Do not add a new cursor here; flag interrupted stage, and require bounded trial evidence that it completes. Repeated interruption requires a separately reviewed narrow remedy. |
| Unit confirmation | Per-application commits and qualification fields remove completed candidates; in-flight item repeats. Persistent failed items may recur. |
| Document discovery | Per-application acquisition commits; completed eligibility markers let later runs move on, partial applications remain recovery candidates. Work inside an unfinished application may repeat; recovery-first ordering can repeatedly revisit failures. No promise of eventual progress solely from a commit. |
| Evidence refresh | Existing per-item commit/refresh-required and cooldown semantics preserve completed work. Interrupted item may repeat; only qualifying completed outcomes clear its flag. |
| Allocation evidence scan | Per-document scan-state commits skip completed documents; current uncommitted item repeats. |
| Geocoding / build-status checks | Per-site commits; successful coordinates / existing check cooldown remove or defer completed candidates. Unresolved geocodes can recur. |
| Conditional lifecycle reassessment | Monitoring sync commits at completion; interruption repeats computation if triggered again. Its trigger is in-memory lifecycle stats, so next discovery is **not guaranteed** to replay it after prior evidence commits. Independent weekly sync is the existing fallback; record propagation gap and verify its next outcome. |
| Final health / browser and session cleanup | Lost final report is not success; committed evidence remains. Reconcile with process evidence and section 8. |

AI extraction and summaries are skipped by the daily command; optional enrichment is not enabled. No paid-stage continuation is added. Trial acceptance must show later stages are reached and their eligible work advances or completes, not merely that council starts rotate. Existing cooldown gaps remain explicit; a demonstrated blocking defect returns for a focused decision rather than expanding P0-A silently.

Proposed environment settings use `PROPERTYAIGENT_DISCOVERY_*` names for parent items/attempts/seconds, council seconds and total seconds; one `PROPERTYAIGENT_DISCOVERY_MODE=bounded|disabled` safety switch. Defaults remain bounded if unset; memory ratios are validated constants for V1. Existing independent intelligence/weekly-sync schedules and resource plans remain unchanged.

## 7. Page-lifetime change — independent acceptance

Use a small explicit page owner passed through browser stages; the owner tracks the active page and existing BrowserContext. Document recycling replaces `owner.page`; evidence refresh obtains that current page. No local shadowed page variable returned only as a count. All navigation uses the owner at the point of use. Preserve existing per-application recycling rather than silently dropping a previously deployed mitigation. On creation failure retain a still-live original page; on closure failure clean up and report the resource error honestly. Final cleanup closes owned pages/context/browser exactly once where possible.

First reproduce the old path offline: fake context creates page A; document stage creates B/closes A; caller passes A to refresh and records closed-page failure. Then require the corrected path to refresh through B. Also test zero pending documents, multiple recycles, creation failure, exception cleanup, and refresh with no eligible work. A bounded local-browser check may navigate local synthetic pages only, network blocked; no council contact, database or paid API. This regression is independent of parent deduplication and Manchester memory attribution.

## 8. Run-health and exit semantics

Keep ScrapeRun statuses `running`, `success`, `partial`, `failed`. Represent interruption/defer reasons and liveness in structured progress, not an incompatible new status vocabulary.

| Situation | ScrapeRun / coverage | Exit treatment |
|---|---|---|
| Primary complete, all due supporting work attempted, no technical failure | success; unresolved NOT_FOUND/AMBIGUOUS counts shown separately from coverage | Child normal; overall 0 if every selected council qualifies |
| Primary complete; parent cap/soft-memory cutoff or supporting work deliberately deferred | partial + reason and exact due/deferred counts | Normal child exit; partial remains eligible for overall 0, preserving established convention |
| Primary complete; supporting transient failure/circuit open | partial; retries/failures/deferred explicit | Same convention as existing partial |
| Future-due cooldown work | Not due now; not counted as budget-deferred or fabricated attempt; unresolved age/count visible | Does not alone force failure/partial |
| Primary attempted and incomplete | failed regardless of useful supporting commits | Overall nonzero even if child exits 0 |
| Child crash, timeout or supervisor hard-memory termination | failed; completed stage evidence retained, remainder unknown/deferred as known | Overall nonzero; proceed to next council if resources/DB safe |
| Clean child exit without valid final health | partial, `health_report_missing`, coverage unverified; never default success | Overall nonzero because completion contract is unverified, a deliberate tightening of legacy fallback |
| Whole-container kill | running row may remain; liveness unknown until positive termination evidence | Render records failure; later reconciliation marks failed with `interrupted_confirmed` only with evidence |
| Historical legacy running row | Remains historical incomplete, termination unverified; no automatic relabelling | Does not block admission by itself |
| Prior owner from same service, successor admission proven under §3.3 | Reconcile failed/interrupted with recorded evidence; preserve unknown request outcome | New invocation proceeds automatically within budgets |
| Genuinely competing owner, termination unverified | Keep incomplete; report specific identity conflict | Block competing launch, nonzero; never reclaim by age |
| Global budget stops before all councils start | Existing rows retained; planned/unattempted list records deferral; do not fabricate started rows | Overall nonzero: incomplete invocation coverage |
| Safety mode disabled | No scrape; explicit disabled message | Nonzero so operator does not mistake disabled discovery for a healthy scheduled run |

Final invocation summary separates process completion from coverage: e.g. “10 accounted for; 8 success, 2 partial; 17 due parent items deferred”. Recent AI summary timestamps never replace source checked timestamps. Do not reset status verification freshness for skipped work. Existing view must surface older incomplete attempts alongside latest run, not conceal them with a new success row.

## 9. Offline regression and reproduction plan

No production or external network access in tests. In-memory SQLite for domain logic; an isolated disposable local Postgres test is required before releasing its migration/unique-owner path, using synthetic data only.

- Shared missing key in 100 children yields one logical lookup, not 100. Two allowed attempts only for transient retry, all budgets counted.
- Successful shared result applied to every eligible child; crash between parent commit and child fan-out resumes idempotently with zero extra lookup/duplicate rows.
- Exact case/whitespace equality; cross-council same reference distinct; separator differences/shortened numeric reference never auto-linked; Idox multiple keys remain ambiguous.
- Recognised empty result versus timeout, malformed layout, partial pagination and conflicting detail identity; none of the latter becomes NOT_FOUND.
- Retry success, exhausted failure, Retry-After, open circuit, cooldown expiry and justified early retry; no permanent negative caching.
- Deterministic offline fixture with 100 due references, negligible mocked durations and 25 available first-attempt slots: all are reached within four completed runs (not a production throughput promise); repeat with one injected reservation/crash and prove the remaining oldest items progress and the interrupted item returns after its owner is terminal. Test continuing arrivals and enforce oldest eligible ordering.
- Ten councils, one recurring fatal child: no fixed alphabetical starvation; all councils start within ten invocations even when one invocation ends after one start. Supervisor-known failure must continue within the same invocation where possible.
- Same-service different-instance successor admission recovers owned reservations automatically; same-instance recovery requires inherited-lock and PID-start evidence. Legacy incomplete rows do not block. Foreign active owner, duplicate host launch and missing runtime identity fail admission. Age/PID reuse alone never proves death. Test supervisor death with surviving child, whole-container successor and conditional owner races.
- Every row in the run-health table above, including final-health loss, partial+exit-0 convention, global unattempted scope and disabled mode.
- Page-lifetime regression from section 7, independently runnable.
- Synthetic supervisor child grows memory or exceeds deadline; verify threshold stop/process-tree cleanup without exhausting the test host. Inject samplers for deterministic boundaries; optional small bounded local subprocess reproduction.
- Schema migration idempotence, null legacy progress, older-reader tolerance, unchanged Application and agent fields; no destructive downgrade.

## 10. Measurable release and observation gates

### Gate A — offline implementation review (future approval)

All targeted tests above pass; compare against baseline for affected existing suites; no new failures accepted. Capture synthetic query count and work-table transfer volume, duplicate suppression, fairness trace and memory-owner breakdown. Document any untested adapter state. No broad full-corpus test or speculative performance refactor.

### Gate B — separately authorised release smoke

First verify effective deployed SHA/config/schema and safety switch. Run only explicitly selected representative councils/cohort under the reviewed limits; no full historical recovery or paid AI. Include Manchester parent workload and one document→refresh path. Confirm strict results, continuation persistence and health visibility. Any primary scrape that cannot complete within its budget fails smoke for that council; adjust only with evidence/review.

Acceptance: zero unexpected OOM/crash; peak cgroup memory below 80% limit; normal completion target at/below 70%; parent stage ≤245 seconds; council and invocation within their recorded trial limits plus grace; later eligible stages reached with committed progress; no lost committed evidence; exactly-once logical success sharing; every selected council/stage has an honest outcome; repeat continuation advances older due work. A controlled memory stop validates containment but does not count as healthy council completion.

### Gate C — seven consecutive scheduled daily cycles, including weekly sync

This observation window establishes sustained health after smoke; it does not block independent AH design or benchmark preparation.

- Zero container OOMs and zero unexplained incomplete running records; no supervisor threshold kills in a healthy acceptance window.
- Every configured council attempted each daily cycle; primary completion on each cycle, or explicitly evidenced external portal outage with retained gap and a recovery decision. An unresolved outage means degraded coverage, not unconditional gate closure.
- Normal cgroup peaks at/below 70%, no run above 80%; stage/council/invocation duration within approved limits. Report maximum and distribution, not only averages.
- Per council/cycle record distinct eligible references actually requested, reservations with request outcome unknown, logical attempts/retries, duplicate requests suppressed (excluding justified retries), found-result reuse, deferred counts by item/time/memory/circuit/owner reason, lookup duration distribution, and achieved distinct-reference throughput. Reservation alone is not proof the portal request occurred.
- Freeze an acceptance cohort with initial eligibility/due times. Track its distinct attempted IDs and remaining IDs through each cycle, separating cooldown, transient retries, outages and later arrivals. Report new arrivals separately; cohort attempt coverage is not successful evidence resolution.
- Prove fairness from the eligible snapshot, queue keys, chosen IDs and reason-coded exclusions: no older eligible unreserved item may be bypassed by a younger first selection. Deferred work retains its priority; attempt reservations rotate priority; retries obey section 4. Use bounded counters/digests plus retained cohort IDs in existing progress/logs, not a new event table. Offline fixtures prove ordering under interruption and continuing arrivals; observation reconciles actual selections. Pending age is an alert only, not the proof.
- Publish projected cohort completion from measured **cohort first-attempt** capacity after retries and other eligible work consume budget, with observed range and assumptions. `ceil(remaining/C)` is a conditional estimate only; C=0 yields no finite projection. Include cooldown dates and outage days explicitly and revise the estimate each cycle. Remove any minimum 20/day promise. Acceptance requires observed cohort progress on service-available cycles with capacity, explained exceptions, no unexplained eligible bypass, and a measured completion projection for Product Owner review. If that projection is commercially too slow, review capacity/budgets rather than declaring success from falling age or relaxing bounds automatically.
- Metadata trace a small cohort of newly committed inputs to the next eligible intelligence job and candidate/sync stage. Report queued/capped work honestly; do not force paid processing. New evidence needing AI is not considered propagated until actual subsequent processing is verified.
- Read-only daily egress baseline and job/UI activity correlation recorded separately. No P0-A claim of reduced bytes without measurement; no requirement to reach 5 GB by assumption.

Failed criteria reopen a bounded diagnosis, not automatic larger instances or bulk reruns.

## 11. Rollout and safe rollback

Rollout only after explicit approval of tested code and release state. Additive migration precedes consumers. Do not enable P0-A if concurrent/legacy discovery could still run. Verify single-owner scheduling and identify pre-existing incomplete runs before bounded execution.

**Rollback must fail closed:** prior to reverting any discovery code, disable/pause its schedule under separate operational approval, wait for or confirm termination of the active invocation, and verify no pending automatic/manual run can start old code. The new `disabled` switch is defence in depth but cannot protect an old revision that ignores it; do not rely on it as the only rollback control.

Preferred code rollback is a forward revert retaining the bounded supervisor/safety entrypoint while reverting the faulty narrow component. If that safety component is itself suspect, keep discovery suspended until a reviewed bounded version is ready. Other independent services remain unchanged unless their own evidence requires action.

Retain ParentLookupWork and nullable progress column, all committed Application evidence and run history; no destructive schema downgrade, no clearing cooldown/reservations en masse. Reconcile active reservations using positive owner termination evidence. Old readers ignore additive fields; no old writer is permitted to resume unrestricted discovery. Resume only after safe-mode/config verification and bounded smoke approval. This is an operational procedure requiring later permission, not a schedule change authorised now.

## 12. Supabase read-only work remains open

Read-only follow-up on 28 September after user sign-in: Render access restored. Intelligence execution finished at 08:06:05 BST with 1/1 evidence refresh and 23/23 summaries reported successful; weekly sync finished at 07:02:00 BST with 396 opportunities considered and unchanged. Both deployed commits display `6fd4202`. These job outcomes support working database access for those runtimes at those times, not proof of the web service’s current connection path, fresh council evidence, or egress attribution. Supabase still displays sign-in. Prior egress observation has not been refreshed. See the operational report follow-up for exact log URLs.

When secure authenticated access is available, complete the small read-only pass in the operational report. From the application's existing runtime/connection configuration, without printing the URL/key or running pipeline startup, execute a transaction explicitly read-only with a short timeout: `SELECT 1`, database/server timestamp, and a bounded aggregate of run metadata. Roll back/end it. Pair with a normal existing app read and logs; SQL Editor alone is not proof of its pooler path. No credentials copied to chat or local files; no connectivity workaround that changes restrictions. If runtime access is unavailable on the current plan, retain that limitation rather than upgrade automatically.

Use daily/category egress charts and available query-stat aggregates, read-only and without enabling/resetting extensions. Attribute only what data supports; query rows/time alone are not network bytes. Separate direct pooler/database, API/storage and client/job traffic where available. Record restriction timing if evidenced. Restoration is a separate choice: waiting for quota reset trades downtime against cost; an approved upgrade could restore a restricted required service but would neither diagnose nor fix inefficient reads. No billing recommendation until actual connection impact and purpose are explained.

## 13. Decisions and remaining uncertainties

The additive ParentLookupWork and structured run-progress approach is approved **in principle**; no need to reopen that decision. The accepted scope, independent page fix, outcome semantics, memory diagnosis/containment and safe rollback are retained.

**Ownership recommendation:** use the existing Render single-service contract plus inherited host lock and versioned owner metadata. No new mechanism needs approval if the release preconditions can be verified. If another required production entrypoint must coexist, request a decision on the narrow advisory-lock fallback before coding it. Current runtime identity availability and discovery-entrypoint inventory still need authenticated verification; these are evidence gaps, not reasons to demand manual cleanup of legacy rows.

**Budget decision outstanding:** no production council limit is supportable from the retained sample. Recommend the existing 3,600-second ceiling solely for separately approved measurement trials, with bounded parent work, memory containment and provisional 150-minute overall supervision. Final per-council/overall limits and commercially acceptable cohort drain time come back with duration, stage-progress and throughput measurements. The user need not guess those values now. Render access is restored and the bounded historical sample is included above. Remaining evidence is workload-representative completed stage timings and runtime ownership identifiers; no further login request is currently needed. Stockport needs the focused primary-scrape retry/circuit investigation identified in section 6.1 before any equivalent measurement run; no blanket hour-long retry is recommended.

Unknowns remain the OOM-growing process, durations/backlogs beyond the small observed sample, and the effect of interruption on actual pending related details/downstream reassessment. No egress or AH conclusion changes in this refinement. Seven-cycle sustained observation remains separate from release smoke and does not block unrelated AH design or benchmark preparation.

This document is a review proposal. Approval of its direction does not authorise schema migration, production recovery, paid benchmarks or release.
