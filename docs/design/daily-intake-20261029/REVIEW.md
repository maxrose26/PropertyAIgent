# Daily intake — INACTIVE release candidate

Stage 4 OPEN. This proposal does not authorise production access, SQL installation,
period issuance, merge, deployment, a Render job, or recurring activation.

## Narrow Render adaptation — implementation review pending

Owner approved implementation/disposable validation only. The new explicit
`render-intake-v1` mode is Manchester-only and requires a frozen `render_profile`
in the owner-issued period. It binds service crn-d9sv93vavr4c73f98rb0, exact code
revision, pinned Playwright headless-shell executable SHA256/cache path, and
explicit byte/time limits. No production profile is issued or approved here.
Owner-local and historical Trafford modes retain their existing checks.

Required profile keys: mode, service_id, revision, browser_path, browser_sha256,
aggregate_bytes, source_rss_bytes, controller_rss_bytes, reserve_bytes,
source_seconds. Runtime reads the effective finite cgroup-v2 memory.max and
refuses mismatch. Swap settings are read/reported, never inferred from the plan
name; changing them refuses. The source environment contains only the existing
private-worker marker, reviewed profile, browser path and fixed harmless basics.
No database/GitHub/model credentials enter the source.

The existing source supervisor opts into Linux child-subreaper ownership only
for this profile and only with no pre-existing children. Kernel adoption catches
orphans that create another session, including unsampled descendants. Closure
repeatedly kills/reaps remaining adopted children and refuses uncertainty.
This does not promise cleanup if the controller itself receives SIGKILL: whole
job teardown must be verified in actual Render acceptance; no closure is inferred.

Memory proposal ONLY: up to the historical 1536MiB sampled source RSS threshold,
256MiB sampled controller RSS threshold and at least256MiB aggregate headroom,
with source+controller+reserve <= the actual aggregate byte limit (at most2048MiB).
A marketed2GB plan is not proof of2147483648 bytes. If it exposes2000000000 bytes,
source allowance must be lower; no automatic plan increase. Runtime also refuses
aggregate memory.current above aggregate-reserve and new max/OOM events. These
are samples with enumeration/scheduling latency, not hard source/controller
caps or guaranteed peaks. Shared pages and kernel/file accounting make summed
RSS different from memory.current. Real browser startup and workload headroom
remain unmeasured. 75s is the maximum source-work proposal including startup;
cleanup may take up to the existing seconds+10 refusal bound, within the90s
Arcus supervision reservation and whole-run150s source-supervision allowance.

Interruption handling reuses the existing control row: first capture registration
atomically writes ONE bounded intake_run OPEN marker with run UUID, period, day
and deterministic final-publication path. Other invocations/new periods cannot
bypass OPEN, including after expiry. Capture, archive and screening checkpoints
remain in their existing storage. Read-only backlog exposes the marker even when
no capture exists. No automatic clearing/recovery/replay operation is added.
Existing owner reconciliation must establish the disposition; an unresolved
marker stays blocked until a separately reviewed correction is authorised.

Both normal and repeated success require the exact expected batches and screens,
using the existing completed_screening validator. Capture completion alone is
insufficient. Finalisation invalidates grants, publishes/readbacks the result,
then records VERIFIED plus the publication hash/path/commit through the existing
trusted registration function and committed readback. A crash before that commit
leaves OPEN; a lost acknowledgement after commit is recoverable by independent
readback of VERIFIED and exact screening state, without source/publication replay.
A retained/source-complete result file published before finalisation is explicitly
not the terminal receipt: database finalisation plus archive and platform evidence
are required. A crash before archive can lose raw observations but preserves
incomplete intent; it never advances coverage.

Acceptance remains INACTIVE. After separate production prerequisites and reviewed
profile issuance: use the existing suspended cron's exact successful build for
ONE separately authorised one-off job, plan-crn-005 only if verified compatible:

    timeout --signal=INT --kill-after=5s 960s python -u -m scripts.run_daily_councils --period REVIEW_APPROVED_PERIOD --hostaddr REVIEWED_IPV4 --output /tmp/propertyaigent-intake-UNIQUE_RUN

Obtain runtime sampled source/controller/aggregate observations, readable kernel
peak/events/swap fields, durable run/checkpoint/archive readbacks, and independent
Render terminal status/logs. One-off metric streams and survival of /tmp are not
assumed. Missing terminal evidence means incomplete/reconciliation. Disposable
whole-job kill acceptance must verify descendant teardown before live collection.
Production access/recovery, exact installation/function inventory, credentials,
TLS route/IP, real source qualification, machine policy and owner period remain
separate requirements. No merge/deploy/settings/job/activation authority follows.

This section supersedes the former unconditional Manchester-context refusal below
only for the explicit validated profile; all unconfigured live invocations refuse.
First implementation candidate3f6e9895f9a6514abbf9803458b32dd953874758:
79 focused tests passed on hosted PostgreSQL17.11/native Linux, job123806710989
(run40976790552). Includes original58 plus8 real SIGKILL boundaries, exact
screen/batch redelivery checks and12 Render/profile/native supervision tests.
Local namespace-mismatched native cases are skipped explicitly, not counted as
passes. Final follow-up adds controller-in-flight kill, aged/expired marker checks,
source credential/controller-memory refusal and tighter cgroup path accounting.
Final identities/results are in the consolidated handoff; no live Render claim.

## Current connected path

Approved continuation base: PR #206 head
1aa8d7e534b6ddf443fe05a194ae47e36032b3ba, tree
3fb5ffe08b9f4edb42de1c03e100f55f83428e6b. The final candidate's commit/tree,
hosted checks and measured usage are recorded in the PR handoff. Historical
partial-delivery text below is superseded by this section, not erased.

In disposable acceptance, the daily command connects the existing expiring registration function,
restricted worker/effect principals, qualified supervised listing readers,
Coordinator retained capture, archive readback, frozen v3 screening, paginated
backlog and authority invalidation/readback. No argument means no effects; the
manual legacy command remains separate. There is no Application credential,
admission, document downloading, enrichment, opportunity processing or AI consumer.

First supported intake allowance: Tameside RECEIVED (Idox) and Manchester VALIDATED
(Arcus), at most two scopes. This does not establish nine-council capacity or
complete GM coverage. The period may allow either or both; no arbitrary council.
Existing metadata/reader qualification is still required for live use. The two-council
Render route is BLOCKED by the execution-context requirement described below;
this candidate refuses it before registration or source work.

### Existing issuer and stops

`intake_policy.installation_script()` is offline generation of replacements for
three EXISTING functions: ingestion_register_bolton_exception,
ingestion_bolton_allowed and ingestion_worker_step. The original policy-v6
registration branch remains text-identical. One EXECUTE privilege is added for
the existing ingestion_worker role on the existing registration function; its
historical owner branch still requires ingestion_barrier_releaser. No new role,
table, queue, index or unrestricted SQL interface is introduced.

Owner.register_intake_period performs inventory verification and a narrowly
scoped owner-only period authorisation, revoking its temporary capability and
reading it back. Runtime holds ONLY existing restricted worker/effect URLs.
The owner never passes its connector or administrative credential to runtime.

The trusted SQL boundary requires:
- no active global/manual stop and no unresolved SOURCE_INTENT/WRITE_INTENT or
  PERSISTENCE_UNCERTAIN work at period issuance; no stop is cleared or excepted;
- a unique period name, code/workflow/file-manifest binding, frozen screening
  configuration, qualified contract identities, a route and reviewed IPv4;
- expiry <=7 days, max_runs an integer 1..7, London-completed-day derivation
  (end=yesterday, start=end-6), and one source capture per allowed council/day;
- at most73 bound keys per scope, no factual/admission tasks, source_calls=1 for
  capture and0 for screening, writes=0, finite work limits and <=30-minute grants;
- exact immutable capture dependencies and runtime identities. Existing named
  historical allowances keep their historical definitions and consumption state.

Runtime verifies the coherent installed function hashes, owner/search_path and
security-definer flags. A source-free metered control reader polls during owned
collection every2s; its bounded database wait runs outside the source supervisor
loop. A stop/access/inventory change cancels the owned source; no retry/fallback.
It also checks before archive publication. A STOP file in the output directory
is an attended stop; it prevents new work while preserving protected closure.
Ctrl+C is also terminal. Unknown/broken/uncertain closure is not a contained error.

### Failure settlement and overlap

Recognised contained failures are currently only fully accounted, positively
closed Idox HTTP429/503, with exact council/window identity. The original audit
is durably archived and a trusted effect-broker operation settles the existing
item/attempt as DEFERRED with a one-hour council pause. The source allowance
remains consumed and is invalidated; DEFERRED does not permit replay. Unrelated
councils may continue. Unknown source errors, shared access/persistence failure,
uncertain acknowledgement or required publication failure stop the run.
No partial-observation screening is enabled or generalised.

Complete-capture screening retains the accepted observation-bound revision:
observation_revision(assessment_identity(record,rule)[3],digest(capture)). New
observations retain their own parent/provenance; same-root delivery does not
refetch. Historical keys/default worker modes remain valid. Duplicate completed
daily invocation reads existing evidence and does not issue work, recollect or
publish another remote result. Interrupted attempted work remains reconcile-only.

Manchester's existing qualified exact-zero UI result can be retained through an
explicit intake opt-in, without creating screening children. Historical default
empty-window refusal is preserved. Tameside zero-result markup has NOT acquired
new qualification: unrecognised empty/error pages still stop rather than becoming
complete coverage. The intake-only Arcus projection omits the duplicate assessment_capture label
array from checkpoint records only AFTER validating the complete original. All
projected fields, capture hash and provenance remain; the full label array stays
in the source_sha256-bound, readback-verified archive. Historical adapter defaults
are unchanged. This keeps the tested 60-row receipt inside the existing128KiB
checkpoint cap without truncating rows, increasing the cap or adding a table.
Longer real metadata can still exceed the cap: retain the source archive and stop,
never claim complete capture or refetch automatically.

Raw partial evidence can remain archived, never a full-window
pass. Current intake does not wait for historical catch-up and never advances a
complete-coverage watermark across incomplete windows.

### Backlog and later consumers

`--backlog --page-size N [--after CURSOR]` uses the existing restricted SELECT
access, primary-key cursor, <=3 roots/page and <=60 records/root. It needs no list
of historical keys. Captures, including qualified zero, failures, provenance and
screening state are visible across runs. Overflow/duplicate assessments refuse,
not silently truncate a conclusion. `more`/next_cursor expose additional pages.
New insertions behind a cursor are seen on the next scan; a page is not a frozen
whole-database snapshot. Existing 4096-item/32MiB ledger ceilings still apply.
No schema/index/access change is required for this bounded slice.

Expired collection authority does not block read-only backlog inspection. The
read command explicitly begins READ ONLY, rolls back and closes. It never issues
an authority or makes a source/publication call. Completion of SCREENING is not
completion of downstream processing: cross-run records report downstream state
NOT_TRACKED_BY_INTAKE, with admission/extraction completion unknown, not invented.

Retained records supply exact council/reference, source URL/key, literal field
states, source/capture/config hashes, observed time and archive provenance. They
remain usable by existing nomination. Fresh detail evidence/qualification is
still required before admission/B2. execute_retained_v3 currently expects the
unbound assessment revision: later adaptation must validate the shared wrapped
revision and its capture dependency consistently in the stored screen, nominee
and batch binding. Do not merely remove its revision checks. No admission or
extraction consumer is implemented here.

The accepted refresh specification below stays deferred and uses the same shared
identity/dependency resolution. It must separately implement verified unchanged
assessment reuse; repeated deterministic intake screening is not an AI consumer.
Retained-only refresh must not create an Application. Decided-record monitoring
and same-URL document revisions remain deferred; ten checks is acceptance only.

## One run envelope (proposed for REVIEW, not production allowance)

Across both councils and ALL stages, including issuer/control/catalogue reads:
90 source requests;23,971,520 mixed-accounting source bytes;120 worker seconds;
150 source-supervision seconds;2080 driver statements;96 database connection
attempts INCLUDING at most8 auxiliary cancel requests;8MiB returned values;
80 GitHub calls;2MiB combined exported evidence;960s active wall ceiling.
No allowance resets between councils or deliveries. The existing restricted
DatabaseBudget lowers each phase's cap and carries cumulative cancellation use.
The existing GitHub publisher refuses uncertain mutations and never force-updates.

Before source work, a whole supported scope must fit the remaining aggregate.
Protected closure reserves are32 statements,4 normal connections,20 GitHub calls,
768KiB export and180s wall; remaining auxiliary cancel connections stay inside
96, not on top. Work cannot borrow these reserves. Source monitors keep the
existing Idox envelope and opt into the existing BROWSER_SOURCE_V2 envelope for
Arcus (75s/1.5GiB source tree). The acceptance container ceiling is2GiB; actual
Render peak/controller/browser and platform termination remain to be measured.
The outer GNU timeout sends INT at960s and KILL5s later if necessary;965s is the
outer kill ceiling, not extra processing time. Closure uncertainty is a stop,
never a continuation or automatic retry. Source/driver/GitHub accounting units
remain separate, not falsely equated to wire traffic.

## Reproducible disposable validation

Existing hosted workflow job daily-intake-pg uses its fixed loopback PostgreSQL17
service and existing pinned test requirements:

    python -m pytest tests/test_daily_intake.py tests/test_daily_intake_limits.py tests/test_daily_intake_pg.py tests/test_daily_intake_runtime.py -q

The runtime test installs only into disposable PG, verifies the actual owner
period method, and invokes the real authorised command as a subprocess:

    timeout --signal=INT --kill-after=5s 960s python -m scripts.run_daily_councils --period TEST_PERIOD --output FRESH_TEST_OUTPUT --disposable-sources FIXTURE_AUDIT_DIRECTORY --disposable-archive TEST_ARCHIVE_DIRECTORY

The harness creates those prerequisites; this command does not bootstrap an
arbitrary database or self-authorise a period. The two disposable switches are
refused outside the exact loopback test database/test-evidence period. Source
fixtures exercise existing parsers/qualification and run in credential-free owned
processes; they are NOT live council/browser/Render acceptance. Daily rows and
grants go through the actual SQL issuer, not fixture INSERTs. Application-table
snapshots, connection closure, consumption, failure settlement and cross-run
pagination are checked. Hosted logs/artifacts preserve failed candidates and
corrections; the final PR report identifies which candidate each result tested.

## INACTIVE actual-Render acceptance proposal — BLOCKED

Read-only service metadata checked29October2026: existing daily service
crn-d9sv93vavr4c73f98rb0 remains suspended, autoDeploy off, startCommand /bin/true.
No settings were changed. Use a ONE-OFF JOB based on its reviewed successful
build, not cron Trigger Run and not recurring activation. Current Render docs:
https://render.com/docs/one-off-jobs and
https://api-docs.render.com/reference/post-job . One-off jobs snapshot the base
service's latest successful build/environment; verify that build's exact commit
BEFORE creating a job. No new service or workflow system is required.

### Concrete source execution-context decision (not a credential problem)

The profiled Arcus reader's existing finite_acceptance.read requires
four-council-owner-local. instrumented_probe.supervised then calls
four_council_release.owner_source_context, which requires an exact source child
cgroup under propertyaigent-operational-once.scope, kernel1.5GiB/2GiB caps,
swap0, group OOM and an exact source-only environment. OperationalMemory creates
that layout only within the delegated owner systemd scope. This intake controller
uses the existing owned-process supervisor but does NOT establish that layout;
its private environment also differs. The historical render-disposable mode
allows only Trafford, not Manchester, and is not a supported profile substitute.
The browser package path also needs explicit propagation through the existing
credential-free environment allowlist. Fixture child success cannot prove any
of these live browser requirements.

require_source_context therefore refuses a non-disposable Manchester period
BEFORE any issuer, source or archive effect, even if Idox would run first.
Read-only backlog remains available. No runner impersonation or containment
relaxation is implemented. A2GiB Render plan alone is insufficient.

Exact proposed policy decision: accept, for an explicitly bound Render intake
service/build only, the Render container's aggregate2GiB ceiling plus the existing
owned source-tree1.5GiB RSS/75s monitor instead of the owner-host delegated source
cgroup. Then authorise the narrow existing-reader/profile/environment adaptation
and its negative controls. This is a proposed exception, NOT an accepted rule.
Risk: sampled RSS is not a kernel source-only ceiling; transient growth/aggregate
OOM can kill the controller and make closure uncertain. Required evidence and
stops still apply. Alternative: preserve the exact kernel rule; then the proposed
Render acceptance remains NO-GO until that existing containment can actually be
provided. No new diagnostic controller or access framework is proposed.

Prerequisites needing separate production authority/evidence:
1. REVIEW accepts final code/checks, exact policy/worker fingerprints and this
   initial two-council envelope. Integrate/build the exact candidate through the
   established workflow while leaving the cron suspended/no-op.
2. Existing production provider/recovery/access gate is satisfied. The PR205
   search_path correction is not silently imported and fixtures do not resolve
   that gate. Historical originals/failed operations are never rerun.
3. Approved installation of the three existing function replacements and the one
   EXECUTE privilege; separately qualified restricted worker/effect credentials,
   reviewed CA/IPv4/route and authentic source-qualification hashes. No application
   or administrative database credential is present in the intake environment.
4. Existing named machine launch policy permits launch:run_daily_councils. The
   reviewed build provides pinned Python/PG/browser dependencies, GNU timeout,
   gh and the existing secure GitHub evidence-publication input. Remove inherited
   legacy administrative/Application/AI credentials from THIS intake environment
   only under explicit settings authority; runtime refuses them, never uses them.
5. Owner authorises ONE period: max_runs=1, <=1-hour expiry, Tameside+Manchester,
   rolling seven-day London windows, exact execution/config/source bindings and
   reviewed route/IP. This is not prepared/issued by this document. Start with at
   least960s of authority remaining. No additional daily owner permit is required
   within a later explicitly accepted recurring period (at most7days/7dated runs).

Only after resolving the source-context decision AND those permissions, the
proposed one-off API operation is:
POST /v1/services/crn-d9sv93vavr4c73f98rb0/jobs with fields
planId=plan-crn-005 (2GB cron-job plan) and startCommand:

    timeout --signal=INT --kill-after=5s 960s python -u -m scripts.run_daily_councils --period REVIEW_APPROVED_PERIOD --hostaddr REVIEWED_IPV4 --output /tmp/propertyaigent-intake-UNIQUE_RUN

REVIEW_APPROVED_PERIOD, REVIEWED_IPV4 and UNIQUE_RUN are release-time bindings,
not active values. This exact command currently refuses the live two-council
period with ARCUS_INTAKE_EXECUTION_CONTEXT_UNSUPPORTED; it is not an executable
release promise until the narrowly scoped decision/adaptation above is resolved.
Restricted URLs and GitHub input stay in the existing secure
route, never arguments/chat. The base cron remains suspended. Do not create the
job now, do not Trigger Run, and never retry an attempted/uncertain job.

Acceptance: source/adaptor provenance and truthful incomplete status; durable
archive/path readback before capture completion; screening/backlog visibility;
zero Application/document/AI/opportunity writes; measured whole-run usage inside
all ceilings; owned-source and database-client closure; committed authority
invalidation; required publication verified; Render job terminal status and peak
memory/log evidence inspected independently. MATCH of fixture paths is not live
acceptance. Any shared/uncertain failure or overflow is STOP_RECONCILE_NO_RETRY.
Retain original JSON/events and immutable archive hashes. No cleanup, grants,
stop clearing, admission or processing follows acceptance automatically.

---

## Historical checkpoints and accepted refresh specification

The following records preserve earlier partial delivery and its accepted refresh
specification. Their intake blocker/status statements are historical; use the
current section and final PR handoff above for the release candidate.

# Minimal daily intake — INACTIVE, corrections required

## Continuation checkpoint — 29 October 2026

Implementation parent 9f17436425fe28851e43a9e2f2f22da86c2b37c0,
tree 436c65136e03340ed9752c26a7c60a6c15bbe64a: all 13 hosted check
runs retrieved as completed/success. Earlier running-check snapshots below are
historical. They do not describe this continuation candidate's validation.

This continuation adds an explicit capture-bound COMPLETE-v3 screening mode.
It reuses observation_revision(assessment_identity(record,rule)[3],digest(capture))
without enabling partial observations or changing historical keys/default modes.
Plans, prepared grants/items, SQL batch creation, Python screening and backlog
readback must agree. An offline derived worker extension validates the revision
and receipt parent/digest; its disposable PostgreSQL tests must pass before this
correction is represented as validated. The former overlap failure remains in
parent history and is replaced by a no-reset, two-capture regression, not erased.

No rolling authority issuer has been found: Owner.register still invokes the
fixed Bolton exception. There is no supported daily production launch. No owner
credential, broad grant or source-only permit is substituted. No new framework is
authorised. Generic contained-failure settlement and cross-run backlog discovery
remain incomplete: the existing projection needs explicit bound run keys and
does not discover earlier roots. These are delivery blockers, not successful
features. The unchanged inactive command/Render proposal below remains held.

## Accepted known-reference refresh direction — implementation DEFERRED

Accepted against repository maxrose26/PropertyAIgent, PR #206 implementation
parent 9f17436425fe28851e43a9e2f2f22da86c2b37c0 and tree
436c65136e03340ed9752c26a7c60a6c15bbe64a, based on master
210d09c5bf314c16baf0680df71d4ae8b30b71f4. This is a bounded specification,
not refresh implementation or an active release. Intake corrections take priority.

- Initial subjects: pending retained references and pending admitted Applications.
  A retained reference MUST NOT require an Application to become refreshable.
  Reuse exact-reference Idox/Arcus readers, ledger items/attempts/checkpoints,
  archive publication and the existing qualified B2 writer for admitted records.
  Initial validation scopes: Tameside Idox and Manchester Arcus; listing support
  is not proof of exact-reference field qualification for either or other councils.
- Identity: exact council/reference, verified returned source identity/URL and
  prior accepted observation digest. Each check binds observed time, parser/field
  contract, evidence/archive digests and supported field states. Reuse the intake
  overlap resolution; no competing task/dependency identity. Semantic assessment
  identity remains record/configuration-bound; capture-bound tasks use the shared
  observation revision wrapper. Assessment reuse requires verified equal inputs,
  configuration and eligibility, not dependency reassignment or historical rekeys.
- Retained-only adaptation: qualified detail observation -> durable ledger/archive
  checkpoint -> append-only history -> conditional latest-accepted projection.
  Existing observation_history is pure and its delivery-order change label is
  not a chronological acceptance rule. Persist old/new observations; guard prior
  accepted digest and time so old/duplicate/conflicting delivery cannot overwrite
  newer facts. Demonstrate existing storage supports bounded due queries and
  atomic acceptance during implementation; no schema/service assumed here.
- Supported facts: qualified status, decision and decision date; compare proposal,
  address, application type and published dates only where retrieval supports them.
  Field-level evidence scope is explicit. Missing/blank/failed evidence preserves
  accepted facts; it is not deletion, withdrawal or unchanged verification. Store
  last-attempted independently from last-successful and per-field verification.
  For Applications use B2's guarded fact/event/watermark transaction; do not route
  retained metadata through a broad legacy Application upsert or auto-admission.
- Outcomes: unchanged supported evidence advances supported freshness only;
  changed qualified evidence is retained and conditionally accepted; missing,
  failed, ambiguous or unsupported results retain failure evidence and successful
  watermark; identity/factual conflicts are withheld; stale observations remain
  historical. Uncertain writes or required publication failure stop/reconcile,
  never authorise replay. Repeated delivery uses its existing checkpoint.
- Selection: bounded due query over both populations, deduplicated by exact
  identity. Oldest due first with stable ties, reserved progress for each
  population, rotating councils and bounded priority allocation. Retry-not-before
  is separate from original overdue age. Report due/selected/completed/failed,
  oldest overdue age and unsupported scope. Borrow unused selection allocation
  ONLY within approved aggregate limits; never borrow closure reserves/authority.
- Provisional cadence: priority pending retained 7 days, other retained 14;
  assess/reuse existing pending Application tiers 7/14/30/60. Decided-record
  monitoring is an explicit DEFERRED requirement, not complete lifecycle coverage.
  Ten total checks/two councils is an acceptance cap, not production capacity.
  Demand=sum(population_in_tier/interval_days)+retries. Illustrative populations
  140/280/300/600 at 7/14/30/60 require 60/day before retries, approximately 72/day
  with a provisional 20% allowance. Actual populations and per-check source,
  DB/publication, time/memory costs remain unknown and must be measured later.
- Routing: unchanged observations produce no screening/AI work. Changes to actual
  screening inputs/configuration queue only affected screening. Qualified factual
  changes use existing lifecycle/document-assessment signals; later acquired
  material evidence may make extraction/intelligence eligible. No automatic
  admission and no connected retained-only extraction consumer is claimed.
  Known-reference refresh does not discover separate related applications,
  appeals or submissions. Same-URL document revision detection is unsupported.
- Meaningful acceptance: disposable PostgreSQL tests for unchanged/changed,
  missing/failed/ambiguous/conflicting/out-of-order evidence; exact returned
  identity; duplicate/overlap delivery; preserved history/facts and atomic rollback;
  fair bounded due selection/retry; only affected downstream work. Assert no
  automatic admission, downloads, AI or unrelated Application writes. Later
  authorised execution must prove live field qualification, usage/aggregate
  limits, closure/readback and attainable cadence. Existing access/recovery gate
  applies. No scheduling/deployment/activation authority follows this acceptance.

Compatibility: the capture-bound correction above supplies an observation-specific
task identity while preserving semantic assessment inputs/configuration. Refresh
must adopt that final shared contract and separately implement verified unchanged
assessment reuse; intake's cheap deterministic per-capture screen is not an AI
consumer or evidence that such refresh reuse is already implemented.

Stage 4 OPEN. This is partial authorised implementation, not an executable
production release. No production connection, collection, grant, stop release,
Render change, merge, deployment or activation is authorised here.

## Identity and scope

Base: master 210d09c5bf314c16baf0680df71d4ae8b30b71f4,
tree e71939ef6c07d45fb8f234c665e116f8af4e2f28. Draft PR #206, branch
stage4/minimal-daily-intake-20261029. Final commit/tree are recorded in the PR
handoff (a document cannot contain its own commit identity).

No commits from PR #205 are included. In particular its search_path consistency
correction is NOT silently imported. The accepted correction and unresolved full
provider/recovery/access gate remain separate release dependencies; do not import
standing-access changes merely to obtain that correction.

## Implemented, deliberately without a live bootstrap

- app/ingestion/daily_intake.py connects an injected, externally authorised
  supervised collector to the existing ChainCaller, Coordinator.retained_capture,
  verified archive publication, restricted SQLLedger/ControllerLedger, v3
  screening registration, batch_plans/process_batch and bounded backlog reads.
- An explicit generic intake_only caller mode never constructs an Application
  engine, refuses CHAIN/ADMISSION registrations and cannot prepare admission.
  Historical callers and Oldham's existing mode retain their defaults.
- The existing database claim checks stop/authority BEFORE invoking the injected
  collector. This is a retention claim, not a source permit. Source authority and
  its durable intent/accounting must still come from a supported release.
- Capture is validated, archived/read back, checkpointed, completed and read back
  before screening preparation. The supervised source's observed_at is retained;
  it is not inferred from historical filter dates or the later retention time.
- Completed redelivery of the SAME scope/root is read-only and never recollects.
  Changed record content/configuration yields a distinguishable assessment.
- Screening preparation failure retains readable unscreened records and supports
  later unattempted preparation without another collection. Attempted screening
  failure preserves capture and requires existing reconciliation; it is NOT an
  automatic resume with fresh budget/authority.
- Backlog includes council/reference, source ID/URL, literal field states,
  observation time, capture/archive hashes, screening outcome/state, task phase,
  attempt/reason/next_action and derived processing state. It explicitly reports
  no Application admission, no extraction completion and no coverage advance.
  Reads are limited to 73 explicitly bound items (one capture, 60 screens,
  12 batches), 60 records and 2MiB projection. No unbounded queue scan or schema.
- current_windows selects a London-completed-day overlap (default seven days,
  maximum 28), exact council date semantics, no Trafford and at most three slots.
  It does not block current intake on historical catch-up, advance watermarks,
  reconstruct historical public availability or refresh older decisions.
- scripts/run_daily_councils.py now refuses live execution with the fixed reason
  DAILY_INTAKE_AUTHORITY_BOOTSTRAP_NOT_SUPPORTED (exit 2, no source/DB calls).
  Its old behaviour is available only through the separate manual
  python -m scripts.run_daily_councils_legacy command, with the SAME existing
  launch:run_daily_councils permission. This is not authority to run that command.
  No --include-ai-stages flag can activate a legacy fallback in the new main.

The extraction consumer is NOT implemented. Existing Application-based processing
fields (extraction_last_outcome/attempted_at, intelligence evidence timestamps,
SchemeIntelligence absence) remain untouched. Completed screening items form a
retained backlog, not executable extraction tasks. Existing nomination accepts
representative eligible records; detail targets, fresh factual verification,
independent admission/B2 and consumer handoff are still required before existing
AI processing. Unknown/truncated facts and related/low-signal records stay held.

## Concrete material dependencies — stop rule applied

1. Existing production Owner.register issues the fixed Bolton exception via
   ingestion_register_bolton_exception. Chain registration can PREPARE other
   scopes, but the PG harness inserts rows/grants as a disposable owner stand-in.
   There is no supported unattended Render issuer for a rolling scope/period.
   The source-only external permit cannot authorise SQL writes. No new issuer,
   owner/admin credential path, grant or access framework is added.
2. Overlapping COMPLETE captures with unchanged record/configuration reuse the
   same screening task identity but require different capture dependencies.
   The actual v3 worker refuses CONFLICTING_DUPLICATE. A focused PG test retains
   both captures and demonstrates this collision without resetting old rows.
   Same-root redelivery is safe; cross-capture unchanged delivery is NOT solved.
   Smallest remedy is a reviewed compatibility decision for observation-bound
   assessment identity or verified reuse of the existing assessment, including
   SQL checks. Do not alter historical keys or merely change a Python hash.
3. Coordinator.idox_source raises the shared stop on source failure, and an
   abandoned SOURCE_INTENT is reconciliation-required. Existing partial
   observation screening is explicitly Bolton-only. A generic contained-error
   label cannot grant continuation or turn partial source audits into complete
   capture receipts. Council-local continuation and safe partial capture need
   an exact existing worker-policy/contract adaptation before they can be wired.
   None is manufactured in this partial delivery; no sequence silently continues.

These are specific compatibility/authority gaps, not a request for another
historical diagnosis or a replacement architecture. Oldham successor and
standing-access expansion stay deferred. A production grant alone would not fix
(2) or (3). The default Render command remains held.

## Bounds and accounting

Each intake caller shares the existing finite DB envelope across all stages,
reads and same-root redelivery: 1040 driver statements, 40 connections, 4MiB
returned data, 300 seconds including a 30-second closure reserve. Before each
stage leave 16 statements/two connections for closure; refuse when the minimum
next operation cannot fit. Existing DatabaseBudget enforces each lowered stage
limit, hard driver waits, connection cleanup and cumulative cancellation allowance
(8 requests). Source supervision/publication is external and not counted as DB
traffic. These are per-scope engineering ceilings, NOT a nine-council run budget.

The demonstrated daily selector is max three slots. It does not establish that
three arbitrary profiles, or nine councils, fit a package. An existing V2 source
package supports at most one Arcus plus two Idox under 100 requests, 26,971,520
mixed-accounting bytes, 225 source worker seconds/270 supervision seconds,
2MiB export and 320 GitHub calls (80 publication). Do not multiply these into new
production authority or reset them between slots. Final release needs a shared
aggregate reservation covering source, archive, DB and closure BEFORE collection.
That production aggregate is not implemented while the bootstrap is blocked.

## Validation and limitations

Local focused unit/legacy/security regression uses the pinned existing test
requirements, no production access. Initial local collection failed because the
scratch venv lacked Playwright; installing the existing lock resolved it (no repo
requirements change). Initial CI 40919759973 failed YAML parsing because an
unquoted disposable sqlite URL ended in a colon. Fixed quoting; failure preserved.
Hosted run40919971866/job123610226069 at 5c35c473c8fcc64800cfb4175438f8a095ca963e
passed 14 tests, including connected Idox/Arcus PG17 capture/screening/projection.
Subsequent candidate 7960d2f passed 22 focused tests. Broader CI correctly caught
an application import of verification-only date constants and a missing explicit
v3-consumer inventory entry (jobs123613130928/123613165982). Reuse application
council configuration and add only the authorised inactive intake projection to
that inventory; preserve both architectural checks.
That result precedes later cumulative-limit and negative-control additions and
must not be represented as final-head validation. Final results are in the PR.

Connected tests use actual source-reader/parser fixtures and real supervisor
processes with synthetic source data, an isolated archive publisher, real PG17,
installed worker SQL, ControllerLedger and restricted runtime principals. Only
owner registration INSERTs/fixture control setup are stand-ins. They prove no
Application-schema table changed and no Application URL is present. Synthetic
fixtures do not qualify current council markup, Render containment or live access.

## Inactive actual-Render acceptance proposal — NOT executable yet

Reuse service crn-d9sv93vavr4c73f98rb0 (propertyaigent-daily-scrape) in the confirmed
Render workspace. It remains suspended, auto-deploy off, start command /bin/true.
The proposed eventual service command is python -u -m scripts.run_daily_councils.
At this candidate it exits BLOCKED; it is NOT a supported collection invocation.
No alternate module, ad hoc Python or legacy command is an acceptance workaround.

After (1)-(3), exact candidate/CI acceptance and separately authorised deployment:
one UNSCHEDULED package, one reviewed Idox/Tameside scope and one reviewed
Arcus/Manchester scope, both screening metadata. Dates/qualification hashes and
code/tree/dependency/archive bindings must be frozen at release, not copied from
synthetic November fixtures. No recurring schedule or historical replay.

Proposed source ceiling: 90 requests (10 Idox +80 Arcus), 23,971,520 mixed-accounting
bytes (3,000,000 +20MiB), 120 worker seconds (45+75), 150 source supervision seconds,
60 rows/six pages each, 1.5GiB source/2GiB aggregate/256MiB controller. Proposed
package ceiling 960 elapsed seconds, 2MiB export, 320 GitHub calls/80 publication;
DB maximum two per-scope envelopes above (2080 commands/80 connections/8MiB data,
600 seconds) must fit the ONE 960-second package including source/publication and
closure, never add another 600-second entitlement. All figures are proposed
reservations, not measured live usage or approved allowances. A supported Render
containment/deadline route and aggregate enforcement must be demonstrated first.

Access: existing approved machine launch policy, restricted worker/effect inputs
through an inspected secure Render route, finite scope-bound issuer and full gate;
no Application/admin credential. Do not print or request secrets in chat.
Archive and ledger readbacks precede success. Retain original results, hashes,
source/DB/API usage and closure evidence. Shared uncertainty, mismatch, capacity,
publication or cleanup failure stops; no automatic replacement/retry. A later
recurring proposal should bind an owner-approved expiry (suggest seven calendar
days), council allowlist and seven-day rolling source-date filter, capacity and
run count. Derive dates mechanically within that period; no daily owner permit.
This is an authority proposal only, not an implemented recurring mechanism.

## Next decision

Corrections required / production blocked. Review the partial code and decide
whether to authorise the narrow existing worker/registration compatibility changes
in (1)-(3), without a new access framework, before further Render wiring. No
merge, deployment, production acceptance or activation is authorised by this PR.
