# PropertyAIgent — bounded operational review, 28 September 2026

Status: investigation and local documentation complete to available evidence; proposed remedy awaiting Product Owner review. No application-code change, production write, paid model call, scrape, migration, billing/configuration change, push, merge or deployment performed.

## Baseline and evidence limits

Fresh public clone: `6fd4202f2cc8cbc9cd5a664c3f0a71019933eb5a`, branch `docs/astra-reliability-handover-20260928`. GitHub connector read succeeded. Working tree was clean before this branch. No repository AGENTS.md was found; CLAUDE.md was read. The current Product Vision governs acquisition-first value, preserving the shared Site/evidence architecture. The July PDF is historical background, not a capability acceptance record.

Earlier in this session on 28 September, authenticated Render showed the web service and daily cron deployed at the same SHA; the app footer showed `6fd4202`, Production, v0.4.5. `git diff 3193d3a..6fd4202 --stat` contains only PRODUCT_ROADMAP and the two specialist addenda (809 insertions); no application fixes in that interval. Production data may have changed independently.

On resuming later that day, the browser inventory had reset to a blank tab. Reopening the intelligence job redirected to Render sign-in. Therefore subsequent job-outcome and database metadata checks are not claimed complete. No credentials were retrieved. The narrow follow-up needs authenticated Render logs and Supabase metadata access, not a database export or secrets in chat.

## Confirmed observations

| Evidence | Observation | What it establishes / does not establish |
|---|---|---|
| Render daily Runs page, service `crn-d9sv93vavr4c73f98rb0` | All 30 displayed records failed; last successful run shown as 11 August 2026, 11:39 BST. Standard plan; 05:00 UTC; `python -u -m scripts.run_daily_councils`. | Sustained top-level failure; not failure of every council or every committed stage. |
| 28 September run log | Container ended at 06:22:34 BST with “Out of memory (used over 2Gi)”. Immediately preceding entries repeatedly looked up identical Manchester parent references. | Termination reason and in-flight stage, not memory-growth root cause. |
| Same run, filtered `[mem]` | Bolton process exit 06:10:48 BST; orchestrator 84 MiB / children 0 afterward. Bury process exit 06:14:13; orchestrator 84 MiB / children 0 afterward. | Those councils reached the end of their processes; these samples argue against cross-council retained child trees in this run. Their success/partial classification still needs the run-health records. |
| Manchester memory | Scrape before: self 252 MiB, children 494 MiB, total 746 MiB. Scrape after and parent-loop entry at 06:18:51: self 256, children 666, total 921 MiB. | Growth during scrape predominantly in descendants. No in-loop breakdown before kill; cannot attribute the later growth to Chromium, Node or Python. RSS sums are not container cgroup accounting and can double-count shared pages. |
| Manchester lookup log | `137764` twice; `137841` three times; `138788` at least six attempts, five completed as not found before the final attempt/kill in the visible tail. | Directly observed duplicate work. Does not establish why the portal search failed to match these references. |
| Supabase Usage, billing period 5 September–5 October | Egress 9.065 / 5 GB (181%); restricted for egress; banner says requests return 402. Database summary 0.081 / 0.5 GB; detailed size 77.08 MB. Cached egress 0. | Network allowance exceeded; storage is not the issue. HTTP banner does not prove the direct PostgreSQL/pooler path failed. Restriction start time unknown. |
| Supabase chart | Largest visible day around 9 September, with other large bars 13–15 September; smaller bars after 18 September. | Timing pattern only; no measured attribution by job, query or client. |
| Render service inventory | Intelligence and weekly sync showed “Successful run”; historical rebuild “Successful build”. | Outcome badges only. Execution timestamps, counts and input freshness were not captured before session loss. A successful build proves no execution. |
| Live dashboard | New application entries dated 2–4 days earlier; several summaries generated about 2 hours earlier; policy monitoring “02 Sep 2026 — last monitoring check”. | Some recent ingestion and interpretation are displayed. Summary generation does not establish source verification or all-council freshness. |

## Code trace: discovery and recovery

- `scripts/run_daily_councils.py`: councils run sequentially in sorted order, each in a fresh Python subprocess/process group. One-hour per-council timer kills the process group on timeout. Output is streamed with a 200-line deque and 4,000-character stored tail. This is already bounded; rebuilding log streaming is not the next fix.
- `run_one_council` commits a `ScrapeRun(status=running)` before starting; memory checkpoints overwrite its detail during execution. A container kill can leave the row running, with no finished timestamp. Final classification distinguishes success/partial/failed, but missing run-health on clean exit falls back to success. Partial is considered healthy for cron exit status. Preserve the meaningful distinction while exposing interrupted/deferred coverage honestly.
- `app/pipeline/run_weekly.py:stage_fetch_missing_parents`: loads all council Application objects into a list plus a reference/id map. There is no attempted-reference set, item budget, per-reference cooldown or inside-loop memory sample. A not-found result records lookup success and resets the circuit breaker, then is forgotten. The next citing child retries it. Successfully fetched parents enter the reference map and are committed, providing some deduplication for successful lookups.
- `app/scrapers/arcus_portal.py:fetch_application_by_reference`: navigates the same page for each quick search and exact-matches the requested reference against result references. A shortened citation may not equal a full portal reference, but this remains a hypothesis until a bounded authoritative example is inspected. Do not silently loosen identity matching.
- One browser/context/page is created per council and reused across early stages. No parent-loop page recycling exists. Existing document-stage recycling was introduced for a different, historically diagnosed Salford workload; that evidence cannot prove Manchester's current root cause.
- `stage_documents` closes its incoming page and assigns a new page locally, returning only a processed count. `main` subsequently passes the original page to `stage_evidence_refresh`. If at least one recycle succeeds and refresh has eligible work, this is a concrete closed-page path requiring a focused reproduction. It occurs later than the observed Manchester kill and is not its explanation.
- ORM session uses `expire_on_commit=False` and spans the council. Lists retain loaded Application objects for their stage; document relationships can load text. This is a plausible working-set/transfer contributor, not proof of an ORM leak (identity-map behaviour alone is insufficient).
- Document discovery selects all eligible pending applications, processes per application, commits progress and preserves incomplete acquisition eligibility. It is not a globally capped queue merely because extraction later has limits. Document/text processing already has dedicated instrumentation and extraction-worker isolation in the existing implementation/tests; do not discard those foundations.
- `stage_scrape` commits before parent lookup; parent discoveries/qualification changes commit individually. Useful Manchester scrape data may therefore survive its later kill. Amount and actual row freshness need metadata verification. Later councils can be starved by a container kill despite subprocess error isolation.
- Current recovery relies on eligibility flags, upserts and subsequent scheduled attempts, not a durable parent-lookup continuation cursor. A cap without fair continuation could repeat the same early missing references forever; that must be prevented in design.

## Egress: supported hypotheses, not measured causes

| Candidate contributor | Repository evidence | Required attribution |
|---|---|---|
| Streamlit reruns | `app/ui/common.py:get_db` creates a session each rerun; bootstrap alone is resource-cached. Dashboard calls `build_dashboard` and `build_opportunity_feed`; Explore loads all non-excluded Sites. | Query count/rows/bytes for representative page loads and filter changes on an isolated fixture, correlated with production request frequency. Do not cache trust-sensitive facts without invalidation. |
| Wide relationship/document reads | `Document.extracted_text` is ordinary Text; acquisition-position computation iterates linked documents for live ownership/S106 extraction. | Identify hot queries and transferred text volume; choose projections/deferred fields only where semantics permit. |
| Full-universe recomputation | Lifecycle reassessment explicitly calls full-universe sync because its API has no site-scoping parameter; weekly sync also consumes shared candidates. | Actual execution counts, query fingerprints and byte estimates. Do not assume a new incremental framework is necessary. |
| Repeated shared evidence work | Packet builder accepts a reusable context; current architecture intends one shared computation. | Trace actual callers before asserting duplication per buyer; count actual recomputations. |
| Scheduled processing | Discovery loads council corpus; processing counts pending work and loads summary candidates; current summary default is 40 although old introductory comments say 20. | Read IntelligenceRun outcomes/backlog and job logs; do not estimate costs from stale comments. |

No query/client byte attribution was available. Egress spikes do not establish which development sessions, UI traffic, audits or scheduled jobs caused them. Do not prescribe a paid plan as the sole correction. Restoration (quota reset or separately approved plan choice) and workload efficiency are different decisions.

## Affordable housing and benchmark findings

Both handover risks are present in this exact source:

1. `affordable_housing_scope._has_no_independent_affordable_position`: any status except null/unknown counts as real evidence independently of its notes, so even an absence-of-information note cannot neutralise an incorrectly extracted status. Adding phrases alone cannot establish affirmative zero or authority.
2. `opportunity_intelligence_packet._scheme_intelligence_field`: picks the first populated sibling-application field. AH status uses this path while counts derive from matching facts; scope/authority consistency is not enforced by that selection. Reuse an operative scoped AH position for all components rather than special-case the ten sites.

These are code risks, not newly verified source corrections for the historical cohort. Full original audit was not attached in this turn; the repository addendum and user-supplied cohort were used. No historical numeric value was promoted into a production correction.

Benchmark: 14 JSON cases, 5 marked approved and 9 not approved. Infrastructure, scoring and execution safeguards exist. Preserve approvals, but review material frozen-input defects before execution. Non-AH strategic-land cases can be prepared independently; mixed ownership-conflict cases carrying AH status need input review even when their intended behavioural assertion concerns control. Keep separate evidence-validity and reasoning-quality outcomes. No benchmark execution or live model/pricing selection was attempted, since approval is required and those checks belong immediately before execution.

## Missing evidence and smallest follow-up

Once authenticated dashboard access is restored, use one bounded metadata pass (no document text export):

- Latest ScrapeRun per council plus latest success/partial and incomplete running rows within a fixed recent window; status, start/end, counts, last checkpoint only.
- Per council: max first_seen/status_verified/documents_last_checked and counts missing/overdue, reported separately. A max timestamp alone must not imply complete coverage.
- Latest IntelligenceRun rows: attempt/success/failure, remaining backlog and timestamps; latest weekly sync and historical rebuild actual execution logs/SHA.
- Correlate a few newly seen application IDs with extraction and source-check timestamps, plus opportunity-state updates. Do not regenerate anything.
- Supabase available egress category/day breakdown and top query aggregates if accessible; no resets of statistics, new extensions or instrumentation changes in production.
- Verify required read paths without obtaining secret values. Supabase SQL Editor access, if restored, is not itself proof that the application pooler path works.

This investigation did not execute SQL because no established database connection was available and the dashboard session reset. It did not run local pipelines that contact councils or paid APIs.

## Proposed smallest implementation gate — P0-A bounded discovery reliability

**Problem/commercial consequence:** repeated parent searches and unbounded stage work can prevent later councils and downstream stages receiving fresh evidence. Buyer recommendations may then be grounded in uneven coverage while recent summaries create an appearance of freshness.

**Proposed remedy, awaiting approval:**

1. Coalesce exact council/reference lookups once per invocation and fan out successful resolution to all citing applications. Preserve not-found, transient failure and unresolved identity as separate outcomes; never create a false parent or permanent negative from one search.
2. Add bounded parent-work/time limits, explicit deferred-work counts and fair continuation across runs using the smallest auditable mechanism agreed in the implementation design. Merely truncating the same ordered list is unacceptable. Avoid an entire new queue framework.
3. Add throttled parent-loop process-class RSS, lookup counts, page counts and ORM identity-map measurements using existing diagnostics; include container accounting where available. This allows a controlled reproduction to distinguish browser, driver and Python growth. Do not pre-emptively mandate browser restarts or bigger instances.
4. Correct page ownership so later evidence refresh receives a live page. Preserve context/session behaviour and close resources deterministically; test the exact discovery→refresh transition.
5. Surface deferred/partial/interrupted outcomes through existing health records. Do not silently label budget exhaustion as success or overwrite committed evidence. A minimal schema addition, if truly needed for fair continuation, must be explicitly included in the reviewed specification before coding.

**Scope exclusions:** no AH data repair, broad ORM refactor, new orchestrator/agent, full backfill, paid calls, automatic model selection, infrastructure upgrade or release. Supabase egress attribution/restoration remains parallel P0 work, not solved by P0-A.

**Alternatives:** a larger instance offers immediate headroom but neither bounds work nor establishes the cause; skipping parent lookup permanently loses evidence needed for AH and site linkage; browser recycling alone guesses at the cause and risks page-lifetime regressions. Deduplication plus bounded work and measurements addresses observed waste while preserving investigation coverage.

**Validation proposal:** offline fixtures for repeated missing references, multiple children sharing a successful parent, transient failure versus not-found, cap exhaustion/fair continuation, interruption/partial commits, and live-page handoff. Any browser reproduction uses local synthetic pages with network disabled. After separately approved release, a bounded representative run then at least seven scheduled daily cycles, including a weekly-sync cycle: all configured councils accounted for, no unexplained interruption, explicit partial/deferred coverage, bounded backlog progress and downstream arrival. Agree memory headroom and time/egress budgets from measured baseline; do not equate summed RSS with the cgroup limit. Production validation itself is not authorised here.

**Rollback:** prior code release and disabled new optional behaviour, retaining committed evidence and diagnostics; any additive continuation state must tolerate older code without destructive rollback. No bulk undo of planning facts. Before release, explicitly document how reverting budgets avoids reintroducing an uncontrolled run.

**Product Owner decision:** agree P0-A's solution scope before implementation specifications/code. Retain P1 truth-layer work and P2 case preparation in parallel. Separately choose service restoration once the required connection-path impact is measured; no billing change is requested on an assumption.

## Local verification and changed files

`git diff --check` passed. Static AST inspection confirms document discovery closes its local page and returns only `processed`; benchmark JSON inspection confirms 14 cases, 5 approved. Markdown fence/link checks completed. No runtime test suite was executed for documentation-only changes; no prior test totals are represented as a fresh pass.

Changed: PRODUCT_ROADMAP.md (current P0–P4 order, acceptance and next task); both roadmap addenda (dependencies); PLATFORM_ARCHITECTURE.md and PRODUCT_VISION.md (narrow status/taxonomy drift only); this review (evidence and decision gate). No source/config/schema files changed. Repository-backed documentation is local on the isolated branch, unpushed and undeployed.


## Follow-up: authenticated Render execution checks, 28 September 2026

After the user restored Render sign-in, read-only inspection verified actual outcomes beyond service badges:

- Intelligence: deployed commit `6fd4202`; scheduled 07:00 UTC. Latest execution ended **08:06:05 BST**, with **1/1 evidence-driven refresh**, **23/23 summaries**, no extraction candidates and reported remaining extraction/summary backlog zero. Application `21565/25` was the refresh candidate, reason `decision_granted`. Thirty displayed runs were marked successful. [Latest execution logs](https://dashboard.render.com/cron/crn-d9sv93vavr4c73f98rag/logs?r=2026-09-28%4006%3A59%3A44%7E2026-09-28%4007%3A07%3A05).
- Weekly opportunity sync: deployed commit `6fd4202`; scheduled Monday 06:00 UTC. Latest execution ended **07:02:00 BST**, reporting **396 considered, 0 new, 0 materially changed, 396 unchanged**. [Latest execution logs](https://dashboard.render.com/cron/crn-dag1lbv40ujc73de74mg/logs?r=2026-09-28%4005%3A59%3A51%7E2026-09-28%4006%3A03%3A00).

These are process/log outcomes, not an independent audit of committed rows or source freshness. The code uses the shared database session path; successful execution supports database access working for those jobs at those times. It does not prove that the web runtime currently reaches the same endpoint or that quota restrictions have no effect. Weekly sync ran before today's intelligence job, so it cannot establish propagation of that later job's updates. No job was triggered by this investigation.

Supabase still displays sign-in. Current usage breakdown, bounded council/stage metadata and a direct read-only check through the web application's actual connection path remain outstanding. Historical-rebuild execution has not been verified.

P0-A direction is agreed, with [the implementation specification](../specifications/019-p0a-bounded-discovery-reliability.md) awaiting review. It separates deduplication, exposure bounds, memory diagnosis and the page-lifetime defect; none is claimed as a proven Manchester OOM root-cause fix.
