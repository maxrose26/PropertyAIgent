# Specification 031 — Legacy planning-freshness bootstrap

Status: **PROPOSED — specification and read-only preflight only**. No implementation, evidence repair, external refresh job or operational activation is authorised by this document.

## 1. Objective and accepted baseline

Bring acquisition-relevant legacy planning evidence to an explicitly accepted verification baseline before treating steady-state discovery as coverage. This is evidence maintenance, not commercial ranking. Do not rescrape all sites merely because the database exists.

Application baseline: `a65ee9795fe58449ba826098480c75b7753d5767`, tree `eeb88a620e3ae2bfd0062482075c8407178b250e`; Render deployment `dep-db4aog7lot8c738ddfug`. B1.1 containment and B2.0/B2.1 correctness/presentation remain accepted. Specification 030 controls status authority, atomicity, stale-response rejection and failure semantics. Stage 1, AH/P0-A, v8 matching, subject/family/fingerprint algorithms remain unchanged. All four operational crons remain suspended; commercial ranking remains on HOLD.

The attached 30 July platform report is historical vision/capability context, not current database truth or authority to resume jobs. In particular, administrative filings do not prove lawful commencement, applicants do not prove ownership, and missing evidence does not prove availability.

## 2. Measured inventory and denominator contract

Read-only Supabase SQL Editor observations: 9 October 2026 at 09:51:12 and 09:52:38 UTC. Two separate read-only transactions, not one cross-query snapshot. No intervening mutation was performed by this work; compatible totals do not prove database-wide immutability. Queries used BEGIN, READ ONLY, 5-second statement timeout, 2-second lock timeout, SHOW transaction_read_only, SELECT/CTE, ROLLBACK. No DDL/DML/COMMIT, bodies, AI prose, buyer records or contact data were exported.

The structured audit is `docs/stage26b/legacy-freshness-bootstrap/inventory.json`.

| Measure | Count / denominator |
|---|---:|
| Non-excluded sites | 555 |
| Sites with linked applications | 550 / 555 |
| Sites without linked applications | 5 / 555 |
| Linked applications | 1,270 |
| Successful status verification present | 302 / 1,270 |
| Successful status verification missing | 968 / 1,270 |
| Sites with any verified application | 227 / 550 linked sites |
| Sites with every linked application verified | 162 / 550 linked sites |
| Sites with no verified linked application | 323 / 550 linked sites |
| Sites with mixed verified/missing applications | 65 / 550 linked sites |
| Verification age 0–7 days | 0 / 302 verified applications |
| Verification age 7–30 days | 302 / 302 verified applications |
| Verification age 30–90 / over 90 days / future | 0 / 302 in each category |
| Intelligence rows | 601 linked application records |
| Stored site status-narrative presence | 550 / 555 non-excluded sites |
| Allocation summary rows | 263 / 287 allocations |
| Allocation rows containing narrative | 249 / 263 summary rows |
| Narrative eligible under deployed B2.1 | 0 / 249 narratives |
| Narrative withheld under deployed B2.1 | 249 / 249 narratives |
| Summary row without narrative | 14 |
| Allocation without summary row | 24 |

Narrative eligibility is decisive without exporting prose: 1 narrative uses prompt v6, 108 use v7, 140 use v8; deployed `allocation_narrative_eligibility` requires v9. All 249 therefore require refresh independently of any context-hash comparison. All have a stored context hash; presence of a hash alone is not eligibility. Stored site status narrative presence is not proof of model origin or read-time eligibility; do not apply the allocation guard automatically to different narrative types.

Age bands are descriptive histogram bins, NOT accepted expiry thresholds. No timestamp was fabricated or bulk marked stale.

### Council coverage

| Council | Linked sites | Applications | Verified | Missing | Existing adapter |
|---|---:|---:|---:|---:|---|
| Bolton | 48 | 70 | 26 | 44 | Idox |
| Bury | 22 | 37 | 7 | 30 | Idox + Anite documents |
| Manchester | 98 | 293 | 68 | 225 | Arcus |
| Oldham | 44 | 77 | 26 | 51 | Idox |
| Rochdale | 59 | 111 | 41 | 70 | Arcus |
| Salford | 74 | 247 | 70 | 177 | Arcus |
| Stockport | 70 | 152 | 11 | 141 | Idox |
| Tameside | 25 | 44 | 18 | 26 | Idox |
| Trafford | 51 | 109 | 0 | 109 | Idox |
| Wigan | 59 | 130 | 35 | 95 | Idox |

Council site counts sum to 550. Missing timestamps, especially Trafford's complete gap, are coverage deficiencies; they do not establish wrong status or a broken parser.

Applying the existing material-change normaliser to exact projected raw fields gives: 496 not-yet-decided, 472 grant-looking, 71 refused, 37 withdrawn, 190 outcome-unknown, 4 recommendation-made. These are **administrative application-state buckets**, not counts of operative residential permissions. Discharges, screening, lawful-use and technical filings remain in the denominator. Raw-status distribution remains retained in the audit; operative role/scope must be resolved before prioritising or asserting permission.

### Buyer-facing dependencies and inventory limitation

The accepted 8 October retained B1.1 replay contains 442 universe entries and 439 considered subjects per buyer; 429 families per buyer. Housing Association has 429 non-terminal families; the other three buyers have 415. Count-provenance supplies a lower bound of 176 supporting applications and 182 application-to-subject edges. Fresh 9 October metadata agrees with all 1,270 retained application identity/site/reference/status/decision/date fields compared.

This is **not** a fresh complete buyer-facing dependency census. Count sources are not always planning-status sources; clock-dependent selection and other context can change. The first offline implementation gate must construct the complete dependency manifest through the actual deployed functions and establish exact operative/status/related-application edges. Do not substitute count-producing references, assume 439 is today's live count, or invent a financial/high-value ranking. Current buyer-dashboard smoke observations may supplement, not replace, that manifest.

## 3. Deterministic risk cohorts and selection

Use ordered, auditable cohorts, not a weighted freshness or acquisition score:

1. **Known factual contradiction:** Failsworth is the first prospective correction case. Other contradictions enter only with dated authoritative evidence; unknown history remains unknown.
2. **Decision-sensitive buyer-facing subjects:** operative pending, committee/unissued resolution and supported appeal states, with missing verification before verified records within the same status/risk tier.
3. **Other decision-sensitive substantive applications:** potential upcoming evidence changes, unresolved source conflicts, relevant RM/variation progression. Exclude technical filings from pretending to be whole-scheme permission.
4. **Settled buyer-facing facts with missing/qualified provenance:** verify important permission/date facts where acquisition investigation depends on them; search related applications only where a progression gap is demonstrated.
5. **Other settled historical/administrative records:** defer where no current consumer or material unresolved question justifies requests. Preserve their unavailable/as-of presentation.

Tie-break within equivalent cohorts: oldest successful verification; missing timestamp as its own tier; council/ref/id for deterministic ordering. Do not compare NULL as a fictional date. Buyer fit/relevance indicates that a fact has a consumer, not commercial quality. Use the existing matching result; no new mandate or ranking.

Age alone cannot move an old settled refusal above a live decision-sensitive opportunity. Deadline priority requires a verified permission-specific condition/date; approval plus three years is not enough. Document context risk, exact consumer and reason codes per selected reference. Dedupe council/reference across buyers, but never combine different scopes or applications into one verified fact.

## 4. Five mechanisms and council capability certainty

| Mechanism | Benefit | Coverage/limitation | Bootstrap use |
|---|---|---|---|
| Exact-reference polling | Directly tests an accepted fact | Existing Idox/Arcus lookup; retries/multiple requests; original reference alone misses later related filings | Baseline catch-up fallback for selected references |
| Recent-decision/change feeds | Potentially cheap candidate changes | No live machine-readable complete change feed established for any council here; received/validated searches are NOT changed-since feeds | Capability canary before reliance; never substitutes baseline verification |
| Document delta | Detects new decision/S106/amended evidence | Metadata delta is not status/legal change; Bury may download inline; Arcus status detail may list Files | Only justified material categories; separate request/byte budgets |
| Related applications | Captures RM/S73/appeal/phase evolution | Existing reference search, not exhaustive identity proof; duplicates/ambiguous relations | Targeted relationship-gap cohort; review attribution before acceptance |
| Time-triggered reverification | Backstop where signals unavailable | Requires evidenced status/risk policy; no universal cadence | Approved manifest/age-based review, later schedule separately gated |

Council-by-council matrix: direct reference and reference-based related search exist in code for all ten councils; Idox received-date discovery for Bolton/Bury/Oldham/Tameside/Trafford/Wigan, validated-date discovery for Stockport, and Arcus validated-date discovery for Manchester/Rochdale/Salford. Idox/direct document register except Bury/Anite; Arcus Files for the three Arcus councils. Stockport configured spacing is 2.5 seconds; other default spacing 0.4 seconds. Configured sleeps are not measured current council tolerance.

For every council, current feed endpoint/completeness, legal reuse, pagination coverage, exact request/byte cost and safe live throughput are **UNVERIFIED**. No council register refresh was executed by this preflight. Public council guidance was inspected only for capability context: Oldham publishes received lists and decisions; Manchester's current register includes appeal information and warns that displayed register information is not formal notification. Old Idox weekly-list guidance does not prove current Arcus feed support. Stockport/Rochdale source opens were unavailable; search snippets are not validated endpoints.

Primary references (capability context, not application facts):
- https://www.oldham.gov.uk/homepage/1252/statement_of_community_involvement_2021 — sections 8.15 and 8.53; accessed 9 October 2026.
- https://www.manchester.gov.uk/planning-and-regeneration/planning/planning-permission/see-or-comment-on-planning-applications — appeals/register disclaimer/reuse notice; accessed 9 October 2026.

Code evidence: `config/councils.yaml`, `app/scrapers/idox_portal.py`, `arcus_portal.py`, `documents.py`, `app/pipeline/status_verification.py`, `evidence_refresh.py`, `run_weekly.py`. Do not invoke write-capable refresh/bootstrap helpers during this specification gate.

## 5. Minimal hybrid architecture

Reuse existing verifier, normaliser/upsert, lifecycle/material-change machinery, scheme reconciliation, exact-source presentation and allocation context fingerprints. Do not introduce another freshness engine, queue platform, matcher or generic evidence framework.

Flow: frozen local inventory/dependency manifest → approved per-council batch → cheap supported signal where reliable → exact-reference authoritative verification → outcome classification → atomic accepted factual change → dependency-scoped deterministic recomputation/withholding → optional separately approved extraction/generation manifest.

For existing records never successfully verified, a recent-decisions feed cannot certify unchanged status. Direct-reference verification remains necessary for selected baseline facts. Feed windows must overlap the last accepted watermark and deduplicate; no watermark advance across incomplete coverage. Portal dates often identify new filings, not alterations to old cases. Keep status verification, document completeness and related-application completeness separate.

Do not launch `run_weekly` merely to reuse a helper: its fanout, downloads, persistence and legacy commencement assumptions exceed a bounded bootstrap. A later implementation must expose a dedicated Stage 1 action with exact approved manifest and budgets; creating/activating that command is not authorised now.

## 6. Material change and authority

Retain Specification 030's fact-specific authority: issued notice for legal decision/date/conditions; council register for administrative state and reference identity; committee report/minutes for an unissued resolution; retained snapshots for dated historical proof. AI prose and lifecycle history cannot outrank new authoritative source evidence. Conflict stays qualified; no commercially convenient selection.

| Event | Materiality / dependency effect |
|---|---|
| Pending → issued grant/refusal/withdrawal | Material accepted planning-fact change; status/date/permission consumers recompute |
| Committee resolution → issued decision | Material formal-status change; do not pre-promote resolution to permission |
| Supported appeal outcome | Material only with exact appeal/reference/decision evidence; not merely the presence of an appeal filing |
| Decision/date correction | Material when authoritative fact changes; preserve provenance and independent source date |
| Operative reference/RM/phase progression | Potential material subject-context change; reconcile exact scope, never blindly replace newest |
| Residential quantum change | Qualified metric/source/scope change only; B1.1 remains controlling; conflict/UNKNOWN if ineligible |
| AH change | Candidate material evidence only; preserve P0-A/AH boundaries and B3 truth gate; proposed is not secured |
| Deadline/commencement | Candidate only with permission-specific conditions/evidence; filing or missing evidence is not lawful commencement/lapse |
| Successful unchanged verification | Timestamp only: no material/lifecycle event, fit/order/key/fingerprint change or automatic AI |
| Cosmetic metadata/unrelated document | No factual change unless contents/source identity justify it; metadata replacement alone not substantive |

The current material detector does not cover every future category (e.g. proposal changes are deliberately excluded; NULL-to-known quantity has particular existing semantics). This specification identifies target fact dependencies; it does not silently extend the detector or authorise B3–B5 semantics. Route unsupported categories to a qualified evidence-review manifest rather than stamping a false complete outcome.

## 7. Dependency/invalidation and selective reprocessing

A dependency edge names application/ref, subject/scope, source/version/hash, accepted factual fields and consumer contract version. Start with a derived run manifest; no new database persistence presumed.

- Planning display: uses newly accepted exact application fields immediately after later atomic correction; failed checks retain old fact and as-of qualification.
- Deterministic counts/subjects/families/fit/Spec028: recompute request-locally using existing algorithms. Explain only actual matcher causes. Freshness is context, not a causal fit reason.
- Scheme intelligence: identify affected extraction facts; do not erase unaffected AH/mix facts or mark every record current from one status check.
- Allocation narratives: existing B2.1 prompt/context guard withholds incompatible prose; no deletion/regeneration. Status-only updated verification must not change dependency hashes.
- Future Scheme/Buyer summaries: define fact/assessment-specific dependencies; no new summary framework implemented here.
- Fingerprints: existing fact algorithms may change values after real evidence change; never change algorithms or rebaseline stored monitoring in bootstrap.
- Saved/monitoring continuity: proposed changes produce a separate transition manifest, never implicit remap. Historical monitoring mismatch remains separate; monitoring must stay suspended.

Selective sequence: verify authoritative change → one guarded transaction for status/decision/date/verification and required lifecycle/change signal → identify impacted consumers → deterministic reconciliation → emit extraction/generation candidates ONLY if new required factual content is unavailable structurally → separate model authorisation → later validated summary generation. Status changes alone do not require AI. All currently withheld allocation narratives are not an automatically approved regeneration queue.

## 8. Failsworth and Southlink rehearsal contract

Failsworth: application 42/site 28/FUL/355686/26, accepted pending, decision/date NULL, verified 18 September 2026 05:20:51 UTC. Dated audit evidence establishes refusal issued 25 September 2026. **Failsworth’s post-refusal successful-verification gap is verified; the exact historical invocation, selection, retrieval or parsing cause is unresolved.** Do not encode parser failure or use expired log recovery as a dependency.

Prospective dry-run: select known-contradiction cohort → mocked qualified authoritative refusal/date → existing B2.0 `verified_changed` → one coherent transaction in disposable test data → one lifecycle event and refresh-required signal → manifest of exact application-42 consumers → hypothetical presentation Refused / decision 25 September / separately recorded verification instant. Existing production facts remain untouched; retained refusal is NOT a new live source check. Buyer classification/fingerprint consequences require actual recomputation, not guesses such as all Strong fits disappearing.

Southlink: application 29/site 25/FUL/355201/25, pending control, last verification 10 September 2026. Mocked unchanged authoritative pending returns `verified_unchanged`; future implementation may advance freshness without lifecycle/material change or model call. No production update performed. This is a no-change rehearsal, not proof its council record is still pending today.

Executed existing offline tests: `tests/test_stage26b_b20.py::test_retained_fact_prospective_verification` — **2 passed**, no failures/errors/skips/deselections. This proves the existing isolated status transaction cases; it does not prove a not-yet-built bootstrap orchestrator, full dependency manifest or live councils.

## 9. Volumes, budgets and costs

Measured envelope: 1,270 application references, 968 missing status timestamps; do not interpret 968 as an approved request count. Exact selected substantive/consumer-dependent volume awaits complete dependency manifest acceptance. Five unlinked sites cannot be checked by inventing a reference. Retained count-supporting lower bound: 176 applications, not exhaustive status coverage. One council/ref must be fetched once for all buyers.

Proposed first execution gate: two-case Oldham canary (Failsworth/Southlink), no more than 2 references; later cross-adapter capability canary max 2 references per council (20 total). These are proposed safety ceilings, not current execution authority or steady-state cadence. Before execution agree per-council pages/requests/bytes/time ceilings and account for assets, redirects, retries, Files listings and downloads. Suggested starting ceiling per reference: 20 requests, 10 MB, 120 seconds; serial within council, at most 2 councils concurrently; 3 retry attempts including initial; cap in-run retry wait at 30 seconds and defer longer Retry-After without ignoring council instruction. Initial canary total max 40 requests/20 MB/4 minutes, with no document-body download and model budget zero. Exhaustion is incomplete, never success. Validate these ceilings against instrumented adapters before live authority; if an adapter cannot enforce all dimensions, it is NO-GO for that step.

Illustrative healthy costs, NOT measured performance: if status lookup needs 2–8 requests, two cases need 4–16; 20 cases need 40–160; selected N references need 2N–8N before bounded retries. Browser assets/document listings may exceed this assumption. At 2–15 seconds per reference, two cases take 4–30 seconds and 20 take 40–300 seconds before backoff; configured minimum pacing adds approximately 0.4R seconds for default Idox requests and 2.5R for Stockport where sequentially applicable. These are sizing scenarios, not completion promises or permission to process all 1,270.

Deterministic bootstrap AI calls: **0; model charge £0**. Hosting, browser traffic and Supabase egress are not free merely because AI is absent. Observed Supabase dashboard warns that its grace period is over; exact remaining quota/billing headroom was not inspected. Confirm capacity before later canary, without changing plan or claiming a billable capacity estimate.

Optional later interpretation: D approved changed documents × bounded input/output tokens × then-current approved model pricing; e.g. 10–30 documents × 5k–20k input / 0.5k–2k output = 50k–600k input, 5k–60k output. No demonstrated D or model choice exists yet, so no credible sterling quote or approved model batch exists. Freshness-only updates and unchanged checks contribute zero D. Set explicit maximum calls/tokens/currency before any later approval. No wholesale reprocessing.

## 10. Safety, recovery and persistence

Manifest includes run/id/code SHA/policy/action/scope, council/ref/application/subject dependencies, prior accepted-state digest, planned mechanism, outcome, source date/URL/hash, attempt and verification times, budgets/actual requests/bytes/wall time, completeness, changed fields, affected consumers and cleanup. Failed-attempt evidence belongs to the exact reference; a run starting does not prove that reference was checked. Reuse operational records where adequate; do not add attempted fields or migration automatically.

Reuse B2.0 READ COMMITTED guarded atomic acceptance; stale/out-of-order responses rejected; duplicate retry/lost acknowledgement idempotent. No stronger isolation, distributed locks or infrastructure implied. Failed/unavailable/ambiguous/not-found/incomplete retains accepted fact and successful timestamp. Circuit trips on explicit 429/block/timeout pattern or budget, pauses council work, records unresolved backlog; no evasion. No repeated website bypass attempts.

Persistent evidence writes would require separately authorised dedicated command/operator scope and production run manifest. Supervised administrative read-only audit authority is not future write/runtime authority. Keep credentials/secrets/private mandates/prose/bodies out of Git and artifacts. Redact network diagnostics and bound retained excerpts. Review copyright/terms before storing documents; current preflight retained metadata/counts only.

Partial runs resume by exact reference/outcome and accepted-state/version guard. Successful unchanged verification is a completed unit; failures remain retryable with limits. No global watermark hides skipped/failed pages. Prefer forward evidence correction with append-only provenance, not deleting historical events. Application-code rollback does not undo later factual writes; any later repair needs separately approved exact before/after evidence and concurrency checks. No schema change is established by this specification.

## 11. Acceptance and release gates

AC01: inventory denominators and age bins reproducible; unlinked/excluded/technical cases explicit.
AC02: exact current subject/status-supporting dependency manifest via actual application functions, not count-source substitution; per-buyer isolation; high relevance without ranking.
AC03: deterministic cohort reasons/tie-breaks; no global score or arbitrary freshness expiry.
AC04: exact-reference source/host/response identity verified; committee distinct from issued decision; conflict retained.
AC05: Failsworth qualified refusal/date dry-run; historical cause unresolved; no unauthorised production repair.
AC06: Southlink unchanged control; no material/fit/family/key/fingerprint/AI consequence solely from timestamp.
AC07: failure/timeout/rate-limit/not-found/malformed/conflicting/incomplete preserves accepted fact and freshness.
AC08: existing atomicity/concurrency/lost-ack/idempotency contract passes offline/native tests without schema/config change.
AC09: request/page/byte/time/retry/family expansion/document/model ceilings instrumented and fail closed; no Bury inline-download surprise.
AC10: received/validated list is not a changed-since feed; incomplete pagination never certifies no changes.
AC11: related discovery exact attribution/scope/duplicate handling; no identity decomposition or inferred commencement.
AC12: material fact produces precise consumer invalidation; unchanged/cosmetic/unrelated source produces none.
AC13: allocation guard consistently withholds; existing model/version mismatch is not an automatic regeneration instruction.
AC14: B1.1/v8/AH/Spec028/Stage1/subject/family/fingerprint algorithms remain unchanged; evidence-driven value differences enumerated.
AC15: zero model calls for deterministic status; separate approved extraction budget for genuinely necessary document interpretation.
AC16: audit/recovery/circuit-breaker/cleanup tested; no skipped reference stamped checked or successful.
AC17: complete risk cohorts have accepted outcomes or explicitly signed unresolved exceptions; no false claim of all-database freshness.
AC18: no cron/monitoring/bootstrap activation follows from specification, code merge or deployment; exact canary authority separate.

### Smallest implementation sequence

L0 — Offline inventory/dependency manifest and qualified fixtures, source-capability budget instrumentation design. No external calls or production writes; no model calls/schema. Resolve current dependency census limitation first.

L1 — Offline bounded exact-reference orchestrator using accepted B2.0, failure/atomicity/concurrency/resource budgets; mock Idox/Arcus/Anite side effects. No full scraping framework or model path.

L2 — Separately approved read-only capability canary; confirm safe traffic/headroom, returned-reference fidelity, feed/document/related limits. No evidence persistence or scheduler activation.

L3 — Separately approved production factual catch-up canary (first two Oldham references), exact write action/manifest; reviewed downstream difference/continuity. Then bounded cohort batches only after canary acceptance. Model processing remains disabled unless separately approved.

L4 — Separate evidence-backed selective extraction/summary regeneration proposal, only for demonstrated remaining dependencies. B3–B5 truth corrections and ownership/control programme remain distinct.

L5 — Separately accepted steady-state discovery strategy and activation, after baseline coverage and operational safety accepted. No brute-force default weekly scrape.

Bootstrap completion: signed manifest/cohort coverage; every selected status-supporting reference verified or explicit unresolved exception; known contradiction resolved or visibly held; dependent narrative current/withheld honestly; request/budget/continuity outcomes accepted; no unexplained semantics/security failure. Exceptions count as exceptions, not success. REVIEW must accept exact cohort scope and unresolved risk before completion.

Steady-state transition: per-council mechanisms/coverage and risk-specific cadence evidenced by canary/outcome data, explicit retry/failure backlog, stable baseline and targeted reprocessing; monitoring mismatch diagnosed separately before monitoring activation. Do not substitute successful deployment for freshness coverage.

## 12. Exclusions, later product requirements and decisions

No production writes/repair, schema/migration, live council refresh job, bootstrap execution, cron/monitoring/intelligence activation, models/summaries, deployment, ranking, B3–B5 implementation or ownership programme is authorised.

Stand Golf remains separately recorded: one planning scheme may contain multiple commercially distinct acquisition opportunities; wider 103 homes and 60 retirement apartments, potential 43 remainder **not independently validated**. Later component-subject work must reconcile/reuse Stage 2.5B, not implement subtraction-driven decomposition here.

Requested REVIEW decisions: accept Specification 031; authorise L0 offline dependency/fixture work only first; approve or amend proposed canary ceilings as provisional safety bounds, not frequency; retain explicit hold on live capability/execution/repair/model/regeneration/operations. Complete current dependency manifest and capacity/budget checks before asking for exact L2/L3 execution authority. Existing monitoring diagnosis stays independent.
