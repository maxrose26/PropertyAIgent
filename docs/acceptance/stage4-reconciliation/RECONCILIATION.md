# Stage 4 — bounded reliable pipeline gate reconciliation

Date: 12 October 2026. Documentation-only REVIEW candidate. Repository base: `d253773a09690f27b150adb701c95f9aa3ee210f`.

## A. Gate and decision

**MASTER STAGE:** 4 — Bounded reliable pipeline. **CURRENT GATE:** determine exact remaining acceptance scope from existing pipeline, freshness and acquisition work. **NEXT GATE:** REVIEW decision on the smallest work required for Stage 4.

**NO-GO — STAGE 4 REQUIREMENT/ARCHITECTURE DECISION REQUIRED.** Existing evidence does not establish a proportionate operational route for both material known-reference refresh and new-application discovery across all ten GM councils. This is an evidence/architecture conclusion, not a claim that those sources are incapable of covering GM, nor a finding requiring an immediate code rewrite.

Recommend one decision: approve **licensed-feed-first qualification for the ten-council GM planning baseline**, retaining selective official verification, and authorise one capped commercial qualification round against the existing minimum data/rights contract. This would select a direction to evaluate, not a supplier, purchase, trial, integration or production action. No qualification or supplier contact has been performed under this authority. Council-specific engineering remains paused. Sections S–T define the decision and its bounded output.

The original runtime acceptance gate remains necessary whichever sourcing direction is chosen. A sourcing decision alone cannot close Stage 4.

## B. Stage 3 exit and publication

Product Owner acceptance is preserved: **CLOSED_WITH_EXPLICIT_LIMITATIONS**, PR #59, head `f0f777a736aa62509c3f833e34bae650dc1a493e`; hosted run **38292398488 SUCCESS**. Its recorded tree is `4a6cf2ba9e7803c834ddba43b5a9b707b5e1bffa`; base is the repository base above. The hosted merge candidate `d749ee2e6c4ff3d415fe7afb9c3508e66a81e43b` had that same tree. PR #59 is published, draft and unmerged at inspection. It is not represented as integrated or deployed.

Retained limitations: nine original AH cases remain **BLOCKED HISTORICAL REGRESSION CASES** for insufficient retained source evidence; Focus School retains its limited disposition; six unseen cases covered six GM councils, with two substantive AH cases and four truthful UNKNOWN cases; manual source interpretation did not prove extraction; full per-case browser coverage through every consumer was not proved; current production state remains UNKNOWN; AH security/truth-store artifact `5f1c410...` remains BLOCKED/DEFERRED and not production-installed. No demonstrated Stage 3 defect was identified here and Stage 3 is not reopened. Stage 2 acceptance is likewise unchanged.

`docs/DEVELOPMENT_WORKFLOW.md` separates publication, merge, deployment and activation and contains no documentation-only merge exemption. Exact additional authority required is REVIEW permission to merge PR #59 at the accepted head, subject to a fresh integration-base/conflict/required-check check. Acceptance and successful hosted CI alone are not merge permission. This reconciliation neither changes #59 nor merges any PR.

## C. Original Stage 4 gate

Authority: supplied **PropertyAIgent Critical Review and Staged Improvement Plan**, original section “Stage 4: Prove bounded ingestion and runtime recovery.” The supplied platform-context PDF is historical context, not current operational proof. Later DA0/DA1/L0/L1 plans do not replace the master gate.

| Original requirement | Existing support | Remaining acceptance obligation |
|---|---|---|
| Close operational P0-A before recurring acquisition; preserve suspension/no-op controls | Retained suspension records; process-isolated daily council runner | Recover/pin the exact reviewed P0-A candidate and evidence; current operational state is UNKNOWN |
| Approved resource bounds hold under stress | Per-council timeout, process-group termination, document protections and bounded experimental probes | Whole-run approved time/process-tree memory/request/row/byte/DB/provider budgets and enforcement evidenced on the chosen callable path |
| Browser/process/database cleanup, including cancellation | Runner cleanup tests; B2 native transaction failure/cancellation tests | Exact relevant stalled-browser/descendant/connection cleanup coverage and evidence tied to candidate |
| Transaction-local DB timeouts survive rollback/re-entry | B2 native query-cancellation cleanup rehearsed | Pipeline timeout installation and reapplication after rollback not established by retained acceptance pack |
| Resumable partial outcomes are honest | AcquisitionHealth partial outcomes; atomic B2 writer; DA0 outcome contract | End-to-end restart/checkpoint proof without duplicates, false freshness or silent opportunity removal |
| Per-council failure cannot consume subsequent budgets | Isolated council workers; timeout/next-council tests | Approved whole-run and per-council budget evidence under 429, timeout and stalled-worker fixtures |
| Expired worker cannot write after ownership changes | Historical agent lease tests include an old worker that never returns | Returning stale owner after replacement ownership is not directly proved; prove it for any ownership-enabled path actually used, or keep that path disabled |
| Exact canary SHA, budget and abort plan | Narrow historical canaries exist | Chosen integrated candidate needs exact approved canary plan; execution needs separate authority |

Original GO: approved stress bounds, cleanup, honest resumability, stale-worker protection where applicable, and exact bounded canary plan. Original NO-GO: unbounded retries, false complete coverage, timeout protection lost after rollback, exceeded resource ceilings, or local tests described as live proof. No new scheduler/queue is required absent a demonstrated need.

The Product Owner now explicitly requires a **functioning ten-council GM pilot**. This adds an operational coverage constraint to application of the original gate; controlled samples remain mechanism evidence, not GM coverage acceptance. It does not require national infrastructure or Stage 9 orchestration.

## D. Existing pipeline inventory and identities

Statuses below describe the inspected artifact or retained evidence, never inferred current production state.

| Component / identity | Status | Stage 4 contribution / limit |
|---|---|---|
| Daily council subprocess runner, acquisition health, portal circuit breaker; runtime baseline includes `804d6a60a4000a9abe423bb09bda2d03a5aabc08` | IMPLEMENTED; operational activation historically disabled | Isolation, timeout, partial reporting and cooldown mechanisms. Whole original runtime acceptance not proved |
| Historical P0-A `ff0baa2` reference | BLOCKED evidence identity | Exact object/artifact was not recoverable in inspected local history; GitHub commit lookup returned no commit. This does not prove work never existed. Recover evidence before duplicating engineering |
| B2.0 PR #34 head `88eaf10c93bce167d53d865782fe0549a21ac928`, merge `7446c1218e2daca591a74918150863a89bb90d50` | IMPLEMENTED + ACCEPTED + MERGED; native DB REHEARSED | Atomic guarded acceptance, not a working acquisition service |
| B2.1 PR #35 head `a62470a73a76c16e95e1089a8c5258700a594f4f`, merge `a65ee9795fe58449ba826098480c75b7753d5767` | IMPLEMENTED + ACCEPTED + MERGED | Freshness/provenance qualification and phase fail-closed behaviour; no operational refresh proof |
| L0 PR #36 head `203196fc6fd2ca0f27f0619588ae1d94804ad8b9`; #37 head `6993afa56e2c38870705a9515c0285213ac665f1` | ACCEPTED + MERGED | Dependency attribution/containment; not live completeness |
| L1 PR #38 head `371acef3e2a075d8fb7a8579540f87f5dc72c985` | IMPLEMENTED BUT UNMERGED; REHEARSED ONLY | Historical 211-reference selection and bounded contracts; not production refresh |
| Request-boundary PR #39 `27966c34...` | BLOCKED / UNMERGED | Cancellation/ownership NO-GO; not a supported operational path |
| Actions prototype #40 `d1b950c569f3c73ab6595afaebdd416b8ade94b2` | UNMERGED prototype | Selected reviewed minimal closure registered through #41; do not equate with whole #40 integration |
| L1 canary registration #41 `c69a...`, merge `1e1159fa85058d71da8a9b9c555c8071a5055fc2` | MERGED; live canary FAILED | Demonstrates bounded safe failure on Oldham, not successful refresh |
| Bolton literal #44 `bdb7bef27191530fb2f3ad6950e41b6538dde114`; registration #45 `d242a587eebfd3cfad8762c7dab095f44a089992` | MERGED; live canary FAILED | Narrow exact-summary transport; not family or B2 integration proof |
| Bolton contract correction #46 `6ea1e471ab6a511f24cb5da79921c44ad1933f45` | MERGED; OFFLINE correction | Field-granular optional decision/date semantics; no successful live rerun retained |
| Owned acquisition architecture #47 `96036769d64da20c28ee3b8db6afb693f33c4e02` | MERGED DESIGN / EXPLORATORY | Two distinct acquisition loops; source research. Owned-first preference is not binding after build/buy review |
| DA0 #48 `17f1de47e9533149b12d33f50aac91451aa0d695` | MERGED OFFLINE CONTRACT | Completeness, identity, field states and failure semantics. No transport, importer or persistence |
| Idox family #51 `882dbe5f788598aa4e9f1dad4464b6291ebcff48`; safety #52 `ddcfa0a5f59c61fbc6dd925ddf94aa8667a86d4a` | UNMERGED / REHEARSED ONLY | Synthetic pagination, identity and bounds; no qualified live family transport |
| Bolton discovery #53 `02aa2311a2039806c3ec7b5fcf0c2c6f76bf68c1`, merge `d253773a09690f27b150adb701c95f9aa3ee210f` | MERGED; live reconnaissance FAILED | Safe containment, not discovery |
| Wigan #49 `ef584df315d26ee60d4a1bab0982647a44fc2a0f`; Salford #50 `687cacd4ed1ae0e3c7ee9a0ba01bfdd5081dd0a7` | UNMERGED / EXPLORATORY | Advertised structured sources, unqualified data access/coverage |
| Publication #54 `8653a2be7741cd7a391e461172fa20ab9f7b860e`; build/buy #55 `3417dd933e84ca8e190a9dc24c162817c1498789` | UNMERGED / EXPLORATORY | No implementation-ready GM baseline; commercial qualification decision remains |
| Pilot plan #56 `8bc89a4ae2cd5ce0ad7cc3d391f0d2c572c1f7a6` | DEFERRED planning | Not a replacement master roadmap or Stage 4 acceptance |
| Monitoring/fingerprints and weekly sync | IMPLEMENTED BUT historically DISABLED / separately held | Fingerprint mismatch predates B1.1; no rebaseline or activation here |
| Intelligence batches | IMPLEMENTED; historically suspended | Current code caps 20 extractions, 40 summaries, 10 refreshes, 10 allocation and 10 applicant batches. Counts are not a provider-spend ceiling |

`render.yaml` declares daily scrape (standard, 05:00 UTC), intelligence (starter, 07:00 UTC), weekly opportunity sync (Monday 06:00 UTC), and historical rebuild (annual January 1, 03:00 UTC). Annual scheduling is not equivalent to manual disablement. Later retained records say all four were suspended; earlier records differ. Neither YAML nor those historical records establishes today's Render settings. Existing DB backlogs/batches suffice as a starting design; no need for a new queue has been demonstrated.

## E. Known-reference refresh and freshness

B2.1 truthfully presents evidence age, uncertainty and provenance. It cannot make old evidence current. The missing operational chain is **bounded retrieval of exact material references → qualified field observations → B2 atomic acceptance → honest success/failure records → retry/recovery and coverage accounting**.

Retained full census (`census-full-result/REPORT.txt`, `inventory.json`, `qualified-capture.json`) observed 9 October 2026 17:46:54: 1,270 applications, 302 with a verification timestamp, 968 without. At that capture, none were within seven days, 300 were 8–30 days and two older than 30 days. Those bands are descriptive, not an approved cadence. No present-day state is inferred.

Failsworth, application 42/site 28/reference FUL/355686/26: retained pending record verified 18 September, with retained refusal evidence dated 25 September. This is a historical freshness contradiction; root cause and present state are UNKNOWN. No repair occurred. Southlink FUL/355201/25 also had an old pending verification; no unsupported current decision is asserted.

L0 retained 649/1,270 applications with edges (234 direct, 415 context), eleven application-attribution gaps and 226 strategic dependencies without an application. L1 selected **211 direct status references**, with 23 other-fact dependencies deferred from the 234 direct set. The basis reconciliation preserved application identities across two snapshots; added allocation review items did not mean new planning applications. There were 100 missing timestamps in the 211 cohort. C1=1, C2=134, C3=0, C4=67, C5=9 (deferred). These are prioritisation evidence, not completed refreshes.

Historical failed Oldham and Bolton canaries do not establish reliable refresh. Stage 3 manual access to five Idox summaries on 12 October proves those pages were individually readable in that context; it proves neither unattended operation nor all references in a council. Rochdale's committee evidence likewise does not certify its application transport.

## F. Discovery reconciliation

| Route | Classification | What is actually established |
|---|---|---|
| Existing Idox date-window/portal discovery | PARTIAL / UNPROVED | Implemented adapters and historical ingestion; no accepted ten-council current completeness or bounded integrated success |
| Idox family and offline safety | REHEARSED ONLY; operationally BLOCKED | Synthetic forms/pagination/zero-result/failure safety; no live family conformance |
| Arcus routes (Manchester, Rochdale, Salford) | PARTIAL / UNPROVED | Existing adapters and historical data; shared platform does not establish per-council coverage or reliable status lookup |
| Wigan structured MapServer | EXPLORATORY EVIDENCE ONLY | Annual services advertised; retained research access failed. Schema, paging, cadence, completeness, rights and 19-reference matching unproved |
| Salford reduced CSV | EXPLORATORY EVIDENCE ONLY | Official historical-since-2014 description and stronger reduced-data reuse basis; payload/header/count/currentness and 32-reference matching unproved. Restricted UPRN material excluded |
| Publication-first | EXPLORATORY EVIDENCE ONLY | Zero qualified complete primary feeds. Trafford archived PDF and Oldham weekly-email policy are qualification leads, not operational discovery |
| Bolton fixed-window reconnaissance | BLOCKED | Live form rejected before results; no acquired candidate set or factual writes |
| DA0 contracts | PROVED OFFLINE CONTRACT capability only | Eight source-eligibility gates remained UNKNOWN; no live transport or discovery |
| Licensed baseline | EXPLORATORY EVIDENCE ONLY | Existing supplier shortlist/questions; zero qualified supplier, zero matched 211-reference evaluation; no purchase or integration |

The publication assessment did not prove those sources can never work. It did establish insufficient evidence to adopt publication-first as the primary GM route. Likewise a failed research request is not “no applications found.” No route is automatically resumed because it was researched most recently.

## G. Factual acceptance

B2.0 is the strongest completed part: compare-and-set guards relevant status, decision/date and timestamp fields; successful facts, verification watermark and related lifecycle/refresh effects commit coherently. Older or concurrent evidence is guarded. Failed reads/transactions roll back; lost acknowledgement remains uncertain instead of fabricated success. Native disposable PostgreSQL evidence includes coherent success, atomic failure, concurrent connections, older terminal evidence, correction retry, retrieval cleanup, commit rejection and query cancellation.

This supports acceptance correctness at that boundary. It does not certify every scraper's transport, full discovery writes, every downstream consumer, or a complete operational run. Failed-attempt persistence was not added: request-local attempt loss may leave UNKNOWN observability. Any chosen acquisition path must demonstrate the B2 boundary and preserve accepted facts on partial input. Failed access must not imply unchanged truth, successful verification, deletion, or disappearance of an opportunity.

## H. Failure, recovery and historical production evidence

| Evidence | Meaning / limit |
|---|---|
| Oldham canary **38121984420 FAILED**, head `1e1159fa85058d71da8a9b9c555c8071a5055fc2`, 11 October | First request stopped on unapproved form field; 1 request/63,108 bytes/~1.73 s, total ~1.98 s. Southlink not attempted; neither reference verified; no persistence. Safe partial failure, not refresh |
| Oldham metadata diagnostic **38125085437 FAILED**, head `f876b50a925cb8485750aef7a3815872ade6e7c2` | Separate failed diagnostic; no success inferred |
| Bolton literal **38181977284 FAILED**, head `bfc158838a5c1e7869b946aa1a1cd30d5ba53053` | Failed live acceptance; later optional-field correction is offline only. Mocked COMPLETE audit is not live evidence |
| Bolton reconnaissance **38261103485 FAILED**, head `d253773a09690f27b150adb701c95f9aa3ee210f`, 12 October | FORM_REJECTED / UNKNOWN_CONTROL; HTTP 200, 1 request, 44,576 bytes, ~1.68 s, cleanup/accounting complete, within bounds. No POST/results/persistence |
| Historical 429s, Stockport long runtime, Trafford timeouts, Manchester OOM, Render resource pressure, Supabase egress pressure | Relevant stress classes for the chosen route, not today's measured failure rates or current quotas |
| B2 historical deployment records in specs 030/031 | Historical deployment evidence only, not present production verification |
| Later retained four-cron suspension | Preserved operational hold; current scheduler state UNKNOWN |

Runner timeout/next-council tests support containment. Memory warning logging is not a memory kill ceiling. Checkpoint/health observations are not necessarily restart cursors. An exit code of zero for an honestly reported partial run can mean infrastructure health; it must not be mislabelled as complete acquisition. No semantic defect is inferred solely from that exit code.

Remaining original acceptance holes include whole-run stress/resource measurements, rollback timeout reinstallation, resumable recovery, and returning-stale-owner protection if the chosen path uses leases. These are unproved acceptance items, not authority to rewrite working code. Recover exact P0-A artifacts first.

## I. Bounded execution

| Dimension | Existing evidence | Required proportionate acceptance |
|---|---|---|
| Requests, retries, pagination | Narrow probes strictly cap requests; circuit breaker; Idox/browser retry limits | Caps across redirects, retries and all pages for both loops; explicit incomplete outcome on exhaustion; respect cooldown without consuming other councils' allocation |
| Runtime | Daily worker default 3,600 seconds per council; group kill/watchdog mechanisms; narrow probes much smaller | Approved whole-run ceiling as well as council/attempt ceilings. Ten one-hour limits are not an accepted whole-run budget |
| Memory | Process isolation and memory logs; historical OOM | Measured/enforced process-tree envelope suitable for approved hosting capacity; logs alone insufficient |
| Rows and bytes | Document protections and experimental response/result caps | Whole batch/window row and byte limits; bounded DB reads/writes and pagination; no truncation described as complete |
| Concurrency | Sequential narrow probes; isolated council execution | Explicit worker/connection ceiling; cleanup under cancellation and failure |
| DB transactions | Atomic B2; native rollback/cancellation rehearsals | Appropriate transaction-local statement/lock timeout and reapplication on new transaction; connection release and stale ownership protection |
| Model/API spend | Intelligence count caps | Planning reliability slice can exclude model execution. If later included, explicit provider-call/spend ceilings; no model work required now |
| Checkpoints | Health/checkpoint observability | Proven resume cursor/idempotency where work is resumable, not a progress log called recovery |

Bolton discovery's accepted narrow probe budget: at most two HTTP requests, one results page/20 candidates, 500 KB per response/1 MB total, 3 s connect/8 s read, 30 s worker/2 minute job, zero retries/redirects, concurrency one and 32 KB audit. Its safe failure validates that experiment, not the original whole-pipeline gate. Idox safety's proposed 18 requests/6 MB/100 seconds/3 minute job were synthetic/offline, not measured production limits. L1's 664 logical operations and 17.6–105.5 minute estimate are illustrative, not actual requests or accepted capacity.

## J. Ten-council capability matrix

K = known-reference refresh; D = discovery. “Operational UNKNOWN” means no present production verification was attempted. No row is certified by family membership. Counts are historical L1 subset sizes only.

| Council / L1 subset | K capability | D capability | Source/transport and retained live evidence | Blockers; failure/recovery and rate/access concerns | Current operational status |
|---|---|---|---|---|---|
| Bolton / 16 | PARTIAL / UNPROVED | BLOCKED in bounded reconnaissance | Idox; narrow literal live canary failed; manual AH summary readable; reconnaissance returned form | Optional-field contract corrected offline; unexpected controls; no integrated B2 success or family qualification; probe cleanup proved | Operational UNKNOWN; no accepted reliable route |
| Bury / 5 | PARTIAL / UNPROVED | PARTIAL / UNPROVED | Idox adapter; manual AH summary readable | No bounded unattended refresh/discovery acceptance or council-specific recovery/rate proof | Operational UNKNOWN |
| Manchester / 38 | PARTIAL / UNPROVED | PARTIAL / UNPROVED | Arcus adapter; historical ingestion | Historical OOM; dynamic navigation/extraction and resource envelope unqualified for accepted route | Operational UNKNOWN |
| Oldham / 20 | BLOCKED bounded canary; manual access partial | PARTIAL / UNPROVED | Idox; exact-reference canary failed; manual AH summary readable; weekly-email policy lead | Unapproved form field; browser investigation NO-GO; stale Failsworth evidence; source availability context-dependent; canary safe failure only | Operational UNKNOWN |
| Rochdale / 20 | PARTIAL / UNPROVED | PARTIAL / UNPROVED | Arcus; retained AH committee evidence, application shell inaccessible in that review | Committee subset cannot certify application refresh/discovery; no bounded recovery/completeness proof | Operational UNKNOWN |
| Salford / 32 | PARTIAL / UNPROVED | PARTIAL / UNPROVED; CSV EXPLORATORY | Arcus; official reduced CSV advertised, payload not qualified | CSV schema/count/cadence/matching unknown; retained access timeout; no integrated path | Operational UNKNOWN |
| Stockport / 35 | PARTIAL / UNPROVED | PARTIAL / UNPROVED | Idox; historical ingestion; synthetic safety fixture | Historical 429/long runtime; offline fixture not live recovery/throughput; cooldown/resource acceptance missing | Operational UNKNOWN |
| Tameside / 7 | PARTIAL / UNPROVED | PARTIAL / UNPROVED | Idox adapter; manual AH summary readable | No accepted bounded unattended route, completeness or rate/recovery evidence | Operational UNKNOWN |
| Trafford / 19 | PARTIAL / UNPROVED | PARTIAL / UNPROVED; publication EXPLORATORY | Idox; archived council-branded PDF lead | Historical timeouts; third-party PDF provenance/period completeness/rights unqualified; no operational baseline | Operational UNKNOWN |
| Wigan / 19 | PARTIAL / UNPROVED | PARTIAL / UNPROVED; structured EXPLORATORY | Idox; manual AH summary readable; MapServer advertised | Research access failure, paging/schema/cadence/rights unknown; synthetic safety fixture not live proof | Operational UNKNOWN |

Idox: seven councils/121 references; Arcus: three/90. These add to 211, but do not measure current operational coverage. Historical full-census verified/missing counts respectively were Bolton 26/44, Bury 7/30, Manchester 68/225, Oldham 26/51, Rochdale 41/70, Salford 70/177, Stockport 11/141, Tameside 18/26, Trafford 0/109, Wigan 35/95. A timestamp's existence is not verification of present truth or a council capability score.

## K. Required GM denominator and credible coverage

Use two separate denominators at an explicit as-of date:

1. **Refresh:** all known material application references whose current facts can affect in-scope pilot opportunities or their material dependencies, including unresolved attribution where relevant. State due/not-due/deferred/unsupported and successful/partial/failed/unknown coverage separately.
2. **Discovery:** material new applications across all ten councils within an agreed window, with explicit inclusion rules, corrections/late arrivals and completeness evidence. Count candidates before and after qualification; never call an interrupted/truncated/blocked window empty or complete.

The numerical denominators remain unresolved. The 211 cohort omits other facts, context dependencies, unresolved links and subsequent arrivals; 1,270 is a historical database population, not an independently complete GM universe. No percentage of actual current GM operational coverage can honestly be calculated from these alone. Discovery needs a trustworthy source/window completeness basis, not a percentage fabricated from the current database.

Credible coverage means a documented primary route for **each of ten councils** for both loops, with approved timeliness/materiality rules, measurable due-work outcomes, bounded failures and a demonstrably small explicitly owned residual. It need not mean perfect real-world knowledge, instantaneous data, all national applications or every document. Exact cadence, eligibility/window definition and acceptable residual must be agreed before operational acceptance; they are inputs to qualification, not a reason to build a national platform.

## L. Manual fallback

Manual work is permissible only for a small, measured residual with an owner, volume cap, review cadence, escalation/expiry rule, evidence qualification and the same safe acceptance boundary. It must be visible as manual coverage, not claimed as automation. No retained evidence establishes that the present residual is small.

Illustration only: at an assumed 2–5 minutes per reference, checking 211 references once costs roughly **7.0–17.6 operator hours**, before discovery, retries, source interpretation and review. This is not a measured productivity estimate. It rules out treating “manually check the historical manifest each cycle” as a demonstrated low-burden fallback. Six AH manual reviews do not establish routine planning verification costs. No manual verification/discovery was undertaken here.

## M. Stage 9 boundary

Stage 4 needs a safe **callable** pipeline with bounded work, truthful outcomes, guarded acceptance and recovery. Sophisticated recurring agents, autonomous prioritisation, monitoring activation and recurring scheduling are Stage 9. Their absence does not keep Stage 4 artificially open. If an existing lease-enabled worker is selected for Stage 4, its stale-owner safety is relevant; otherwise retain it disabled and exclude it explicitly rather than claiming its safety test passed. No scheduler, monitoring or cron was activated or rebaselined.

## N. Anti-drift and source-route comparison

| Workstream | Disposition | Would it be built now solely for Stage 4? |
|---|---|---|
| B2 acceptance and truthful B2.1 semantics | CONTINUE NOW as retained contract | Reuse; no blanket retest or rewrite |
| Exact P0-A artifact recovery and identity pinning | CONTINUE NOW as evidence prerequisite | Recover retained evidence before deciding what runtime work is missing; not a new engineering programme |
| L0/L1 census and DA0 outcome/identity contracts | PRESERVE AS EVIDENCE | Reuse useful selection/contracts; do not adopt their historical denominator or entire roadmap |
| DA0's owned-first assumption / automatic DA1 progression | DEFER | No; sourcing direction is unresolved and later build/buy evidence challenges the assumption |
| More Idox form fixes/family investigation or Arcus work | DEFER | No justified ten-council value/cost path yet; common platform is not support |
| Wigan MapServer / Salford CSV / publication lead investigation | PRESERVE AS EVIDENCE; further investigation DEFER | Useful leads, but neither all-GM nor implementation-ready; do not automatically reopen |
| Failed bounded canaries and offline safety fixtures | PRESERVE AS EVIDENCE | Reuse failure/boundary lessons; no repeat live probes under this authority |
| Existing build/buy shortlist and minimum contract | CONTINUE NOW only as REVIEW decision input | One capped qualification round recommended; not another market survey and not performed now |
| Monitoring/fingerprints/recurring orchestration | DEFER to Stage 9 | No activation needed to establish callable reliability |
| Pilot/DA/GM-R parallel programmes, national platform, AH truth-store | DEFER | Not prerequisites for this bounded Stage 4 decision |

Comparison: owned Idox could address seven councils in principle but family operation remains unproved and excludes the three Arcus councils; Arcus work addresses the complementary three with its own unproved runtime constraints. Structured Wigan/Salford and publication leads cover subsets with unresolved access/completeness. Broad manual operation has unmeasured recurring labour and is not a proportionate baseline. A licensed GM baseline potentially covers both loops across ten councils with less bespoke engineering, but coverage, latency, rights and cost are unqualified. Hence **qualify that direction**, not claim it is already the solution or select a supplier.

## O. Exact remaining blockers

1. No qualified proportionate ten-council source model proving both refresh and discovery. REVIEW/PO sourcing direction is required before more council engineering.
2. Operational denominator, materiality/window/cadence and allowable residual are not yet accepted; 211/1,270 must not substitute for them.
3. No chosen end-to-end acquired-evidence → exact identity/field qualification → B2 acceptance → recovery/coverage proof.
4. Exact current P0-A artifact/evidence is unavailable in inspected material; whole-run resource, cleanup, transaction-timeout/recovery and applicable stale-owner acceptance are not established. Recover before proposing missing implementation.
5. Current production installation, cron state and GM operational performance are UNKNOWN. This reconciliation does not require or authorise inspecting them; future operational acceptance needs separately authorised exact-candidate evidence and canary controls.

These blockers do not reopen Stage 2/3 and do not justify a new autonomous platform.

## P. Completed work and evidence that must not be repeated

Reuse accepted B2.0/B2.1 implementation, L0 containment, historical census/basis comparison, the L1 manifest as a historical sample, DA0 contracts, bounded-probe failure evidence and the existing source/build-buy assessments. Do not redo council research or count later passing AH tests as pipeline proof.

**OFFLINE/LOCAL:** this reconciliation used source/document/code inspection and arithmetic/identity consistency checks only. No application test suite or pipeline was run. Existing retained results: L1 268 tests; Idox safety 146 (57 DA0 + 89 safety); final Bolton reconnaissance 151 (57 DA0 + 94 reconnaissance). These protect their specified artifacts, not the operational GM pipeline.

**HOSTED CI (historical):** B2.0 disposable PostgreSQL 17 run **37892007681 SUCCESS**; related AH web run **37892007677 SUCCESS**, which is not acquisition proof. L1 **38041805449 SUCCESS**. Stage 3 **38292398488 SUCCESS** supports the accepted AH scope only. Live failed acquisition runs are separately listed in H. No new hosted result is asserted in this document; publication/check status belongs to the exact-candidate handoff.

**HISTORICAL PRODUCTION EVIDENCE:** supplied/captured reports, deployment references and census dates are explicitly historical. Experimental live hosted requests are not production installation. **CURRENT PRODUCTION STATE UNKNOWN.** No production access occurred.

Primary retained evidence locations: `docs/stage26b/B2.0-OFFLINE-CORRECTNESS.md`; specifications 030/031; `verification/b20_native/test_postgres.py`; `verification/stage26b_l1/BOLTON_LITERAL_CONTRACT.md`; `docs/design/owned-planning-acquisition/ARCHITECTURE.md`; `docs/design/da0-acquisition-contract/CONTRACT.md`; `docs/design/bolton-discovery-recon/REPORT.md`; unmerged PRs #49–#55 at the exact identities above. External retained census/L0/L1/canary artifacts were inspected in the supplied workspace; their labels and dates are recorded above. Private database exports are deliberately not republished. Reproducibility of those external artifacts remains subject to their original approved retention, not this public-facing summary.

## Q. Independent review

Two independent agent reviews were completed for this reconciliation: original runtime-gate audit and product/sourcing critique. They agreed that completed semantics do not prove refresh/discovery, failure containment does not prove source coverage, and P0-A identity/evidence must be recovered before duplicating runtime work. Product review supports the decision in S, explicitly distinguishing qualification from supplier selection and preserving UNKNOWN coverage rather than claiming zero underlying coverage. These are independent analytical reviews, not REVIEW merge authority, security certification or production acceptance.

## R–T. Verdict, one next decision and acceptance criteria

**NO-GO — STAGE 4 REQUIREMENT/ARCHITECTURE DECISION REQUIRED.** No immediate implementation slice is justified on the retained evidence. The instruction's architecture-decision exception applies.

**ONE next decision:** approve licensed-feed-first qualification for the ten-council GM planning baseline, retaining selective official verification; authorise one capped commercial qualification round using the existing shortlist and minimum data/rights questions. No new market survey, council-specific source branch, purchase, trial, integration, data import or production action is included. REVIEW must approve the contact/time/spend cap before that round; no authority is presumed here.

Acceptance for that decision/qualification output:

- Use the existing shortlist; agree a finite supplier/contact count and calendar deadline, with no paid spend or data transfer absent separate permission.
- Obtain attributable answers for all ten councils, separately addressing material known-reference changes and new discovery, identifiers/scope, historical limits, coverage/completeness and exclusions.
- Record latency/corrections, outages/backfill/recovery, rate/access limits and evidence/provenance fields; label unavailable answers UNKNOWN.
- Resolve product display, storage, reuse/derived-data and retention/exit rights against the existing minimum contract; no assumption that a public marketing claim grants them.
- Record pilot price/limits and exit terms; compare whole-pilot engineering and ongoing manual burden with the retained owned-source evidence, not national-scale aspirations.
- Return one qualified route or explicit rejection/no qualified route, with evidence and residual gaps. REVIEW then authorises the smallest integration slice. No commercial response is itself Stage 4 closure.

Subsequent Stage 4 closure still requires accepted GM coverage definitions, a bounded callable acquisition-to-B2 path, exact runtime/recovery evidence, and separately approved operational verification. This is a statement of the original gate, not a second implementation workstream.

## U. Actions deliberately not taken

No new council/source requests, manual verification, supplier contact, production queries/writes, pipeline execution, scraper changes, source refresh/discovery, migrations/imports, AH changes, model/API calls, ranking/intelligence work, monitoring activation, cron changes, deployment, merge or Stage 5+ work. Only this consolidated documentation candidate is published. Stage 3 stays accepted; implementation remains paused pending REVIEW's precise decision.
