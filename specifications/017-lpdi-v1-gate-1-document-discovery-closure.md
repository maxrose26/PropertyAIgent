# LPDI V1 Gate 1 — Greater Manchester Document Discovery Closure

## Purpose

Not Local Plan Delivery Intelligence itself — a data-foundation gate that materially closes the missing authoritative housing-delivery evidence coverage LPDI (and Housing Supply Pressure Intelligence, and Opportunity Discovery's "low housing delivery" filter) will eventually need, by using PropertyAIgent's **existing** document discovery / monitoring / extraction architecture more widely, not by building a new one.

## Architecture audited

`app/db/models.py` (`LocalPlan`, `MonitoredSource`, `MonitoredReport`, `LocalPlanCouncil`), `app/policy/document_types.py`, `app/policy/report_discovery.py`, `app/policy/document_selection.py`, `app/policy/sources.py`, `app/policy/evidence_validation.py`, `app/policy/plan_evidence_view.py`, `app/policy/review.py`, `app/extraction/plan_evidence.py`, `app/policy/extract_plan_evidence.py`, `config/policy_sources.yaml`, `scripts/register_policy_sources.py`, and the relevant existing test suite (`test_report_discovery.py`, `test_document_selection.py`, `test_extract_plan_evidence_pipeline.py`, `test_plan_evidence_extraction.py`, `test_plan_evidence_view.py`, `test_policy_document_coverage.py`, `test_policy_models.py`, `test_evidence_validation.py`, `test_salford_trafford_reg19_sources.py`).

## Root cause of sparse coverage — CONFIRMED, precisely, against current code and production data

**The prior audit's diagnosis was confirmed exactly**, and pinpointed to one specific mechanism: `app.policy.report_discovery.discover_reports_for_council` only ever checks `MonitoredSource` rows already registered for a council (`WHERE council_code = ... AND is_active = True`). Production has **exactly 7 `MonitoredSource` rows total**, across only 2 of 10 councils (Bury: 3, none of the discovery-capable index-page types; Stockport: 4, including the `amr_page`/`housing_land_supply_page` rows that are exactly why Stockport succeeded). **The other 8 councils had zero `MonitoredSource` rows of any type** — discovery had nothing to iterate over, not because it is incapable, but because it was never told where to look. The extraction pipeline (`app/extraction/plan_evidence.py`, `app.policy.extract_plan_evidence`), the deterministic classification rules (`report_discovery.classify_report_type`), the routing table (`document_selection.DOCUMENT_TYPE_TO_CATEGORIES`), the conflict/precedence rules (`resolve_fact_conflict`/`resolve_report_conflict`, `DOCUMENT_TYPE_PRECEDENCE`) are all complete, tested, and — for Stockport — demonstrably already working in production. **This is a document-discovery/configuration gap, not a missing-capability gap.**

## Source strategy — config-only, zero code change

`app.policy.sources.register_sources_for_council` (unmodified) is fully idempotent, config-driven from `config/policy_sources.yaml`, and auto-resolves `local_plan_id` by exact `(plan_name, plan_version)` match against an already-ingested `LocalPlan` row. This gate's entire implementation is therefore **config data only** — **12 new `MonitoredSource` entries added across 9 councils** (6 newly covered: Bolton, Manchester, Oldham, Rochdale, Tameside, Wigan; 3 extended: Bury, Salford, Trafford), on top of **9 pre-existing** entries (Stockport 2, Bury 3, Salford 2, Trafford 2), for **21 total**. Every new entry was located and verified by direct, live browser navigation against the council's own real website (never a search-engine summary, never AI-generated):

<!-- Documentation-only correction (LPDI V1 Gate 2) - this section originally
     miscounted/transposed the pre-existing vs. new split ("9 new across 8
     councils"; "12 pre-existing + 9 new" further below). The implementation
     (config/policy_sources.yaml), the tests, and every other number in this
     specification were always correct - only this prose summary was wrong.
     Corrected here to: 9 pre-existing + 12 new = 21 total, across 9 councils
     touched by this gate (6 newly covered + 3 extended). -->

| Council | New source(s) | Verified content |
|---|---|---|
| Bolton | `monitoring_page` (index) + 2 directly-registered PDFs | 5YHLS statement genuinely current (1 Apr 2026, 3.61 years' supply); AMR confirmed **stale** (2018/19, Bolton's own site's "latest") |
| Manchester | `amr_page` + `housing_land_supply_page` | AMR page current (2025 AMRs + 2012–2024 archive); 5YHLS page confirmed **stale** (2019 edition, the only one linked) |
| Oldham | `monitoring_page` | Monitoring reports, SHLAA, Brownfield Register, HDT Action Plan, Infrastructure Funding Statement together |
| Rochdale | `amr_page` (no `plan_name` — see below) | AMR updated May 2025, covers 1 Apr 2022–31 Mar 2023 |
| Tameside | `amr_page` (no `plan_name` — see below) | "Authority's Monitoring Report" (possessive form) |
| Wigan | `monitoring_page` | AMR, Brownfield Register, LDS, SCI together |
| Bury (extend) | `monitoring_page` | Housing land evidence + Monitoring reports sections |
| Salford (extend) | `monitoring_page` | Housing / Monitoring / Town-and-neighbourhood-centres sections |
| Trafford (extend) | `monitoring_page` | SHLAA, HDT, AMR, Brownfield Register, 5YHLS position together, all on one page |

No new `MonitoredSource.source_type` vocabulary was introduced — every value used (`monitoring_page`, `amr_page`, `housing_land_supply_page`, `authority_monitoring_report`, `housing_land_supply_statement`) was already documented in that model's own docstring, confirmed by a dedicated test (`test_config_file_introduces_no_new_source_type_vocabulary`).

## Authority-specific adapters/config

None beyond plain data in `config/policy_sources.yaml` — no per-council branching was added to any Python module. This matches CLAUDE.md's "do not hardcode council-specific behaviour" and the task's own Section 9 instruction exactly.

## Two councils deliberately registered without a `plan_name` — a genuine, evidence-based STOP, not an oversight

- **Rochdale**: has **no independent `LocalPlan` row of its own** in this database (confirmed by direct query) — only a `LocalPlanCouncil` `participating_authority` link to the *shared* "Places for Everyone Joint Development Plan" row (id 2). That shared row's own scalar housing-delivery fields (`housing_delivery_test_result`, `five_year_supply_years`, etc.) are single-valued per row; **8 councils share it**. Attaching Rochdale's own, genuinely distinct AMR figures to that shared row would silently conflate them with Bolton's/Oldham's/etc. Registering the source as council-level (`local_plan_id` left `null`, the same documented, valid "steady state" `app.policy.sources`'s own docstring already describes) is the correct, honest action. Giving Rochdale its own independent `LocalPlan` row is a separately-roadmapped item (`PRODUCT_ROADMAP.md` §2, "Independent Local Plan monitoring for the remaining 8 GM authorities") — deliberately not expanded into here.
- **Tameside**: has **two** existing `LocalPlan` rows (emerging "Homes, Spaces, Places" preferred option; adopted saved "Unitary Development Plan"), and its one real monitoring page does not itself state which plan its AMR belongs to. Guessing would risk silently misattributing evidence. Registered council-level, flagged for a Product Owner decision on which plan (most likely the emerging plan, since the saved UDP is a legacy document — but this is a judgement call this gate deliberately does not make).

This is exactly the class of situation Section 12 of the task anticipated: *"If the architecture does not currently define how conflicting or newer authority evidence should supersede older evidence, identify this as a blocker and STOP before inventing a rule."* Here the issue is prior to conflict/supersession — it's *attribution* — and the same discipline applies.

## A third, related, pre-existing finding: config `plan_version` drift

Cross-checking every new entry's `plan_name`/`plan_version` against the *live* database (not assumed from prior config) surfaced that the **pre-existing** Salford and Trafford `emerging_plan` entries in `config/policy_sources.yaml` (added by an earlier task) use `plan_version` strings ("Publication July 2026", "Publication Version (July 2026)") that **no longer match** the current database's actual `LocalPlan.plan_version` ("Regulation 19 Publication" for both, confirmed by direct query). Their `MonitoredSource.local_plan_id` is presumably already set correctly in the database from an earlier registration (possibly when the plan's stated version genuinely was different, or set through a different path) — but if either entry were ever re-registered fresh today, auto-linking would silently fail. This is a **pre-existing** issue, not introduced by this gate; it was not "fixed" here (editing another task's historical config entries is out of this gate's scope), but is recorded as a known limitation. This gate's own new entries were verified against the *current* database value specifically to avoid repeating it.

## Provenance behaviour

Every `MonitoredReport` row (index-page-discovered or config-direct) retains `council_code`, `local_plan_id` (where resolvable), `monitored_source_id`, `source_type`, `classification_status`, `matched_classification_rule`, `title`, `url`, `status`. A `PolicyChangeEvent` is written for every discovery (`report_discovered` or `report_classification_needs_review`), carrying `source_document_url`/`detected_at`/`review_status` — unchanged, existing architecture.

## Temporal / version behaviour

Unchanged, existing, and already correct: `document_selection.DOCUMENT_TYPE_PRECEDENCE` + `resolve_report_conflict` rank candidates by document type, then reporting/base-date year, then publication date; a same-URL content swap is auto-superseded (`check_report_for_changes`); a different-URL "possible newer edition" is queued for human confirmation (`report_discovery.register_discovered_reports`'s own supersession-review logic), never auto-applied. No new temporal rule was invented — none was needed.

## Conflict handling

Unchanged, existing: `resolve_fact_conflict`/`resolve_report_conflict` return `(None, True)` — "queue for review" — whenever no unambiguous precedence winner exists, rather than guessing. Verified still correct by the full, unmodified existing test suite for these modules.

## Idempotency behaviour

Verified directly (`test_registration_is_idempotent_across_repeated_runs`, `test_new_councils_register_without_a_local_plan_existing_yet`, `test_registering_new_councils_does_not_disturb_previously_existing_ones`): repeated registration produces identical `MonitoredSource` id sets, no duplicate URLs, and registering new councils never disturbs any previously-existing council's rows.

## Failure-isolation behaviour — measured live

A real, controlled discovery run (Section "Baseline vs validated coverage" below) confirmed the existing architecture already isolates failures correctly: Manchester's two sources both returned HTTP 403 (confirmed independently via a direct `requests.get` with the exact same `User-Agent` header `report_discovery.py` already uses) while every other council's discovery proceeded and completed normally in the same run. No council's failure affected any other council's result.

## Search-provider discipline

No live web-search/AI capability was used to *locate* these pages — every URL was found via a search engine acting purely as an index (Bing), then **independently verified by direct navigation to the council's own real domain**, reading the real page content, and confirming real, working document links before being written into config. No AI-generated fact was retained as evidence — only real, directly-observed URLs and page content.

## Tests added

`tests/test_lpdi_gate1_document_discovery_closure.py` (16 tests): config shape for every new/extended council; the two deliberately-plan_name-less councils; idempotent registration against an isolated test database (never production); auto-linking to a real `LocalPlan` row once one exists; the two councils staying unlinked even when unrelated plans exist; real link-text classification for every genuinely-found live pattern (including two genuine "correctly deferred to review" cases — see below); existing extraction-category routing already covers the new source types; provenance retention; no new source-type vocabulary introduced.

`tests/test_salford_trafford_reg19_sources.py` (pre-existing) — 4 assertions updated (not weakened) to reflect the new, larger, correct source counts for bury/salford/trafford now that this gate has added one monitoring source to each; the underlying claims being tested (correct types, correct plan-name linkage, non-disturbance of other councils) are unchanged and still hold.

## Two genuine, demonstrated classifier limitations (documented, not "fixed")

Live verification surfaced two real cases where `classify_report_type` (unmodified) correctly defers to `needs_review` rather than mis-guessing, per its own Part 2.8 design:
1. **Hyphenated URL slugs**: Bolton's real AMR URL uses `authority-monitoring-report-2018-19` (hyphens); the keyword rule matches on spaces (`"authority monitoring report"`), so the substring check fails even though a human would obviously recognise it.
2. **Plural forms**: Manchester's real link text is "The 2025 AMRs are available to download." — the bounded-word rule ` amr ` requires the exact singular token, so the plural "AMRs" doesn't match.

Both are genuine, narrow, well-understood gaps — but per Section 10's own "discovery closure before extraction/classification expansion" discipline, **no fix was made**. Each affected document was still usably registered (the Bolton PDF directly, with its type stated explicitly in config, bypassing the crawler-only classifier entirely; Manchester's AMR page itself, registered as an `amr_page` index, will simply surface this specific link to a human reviewer on next crawl). Recommended as a small, low-risk future fix (normalise hyphens to spaces and singularise "AMRs"→"AMR" before matching, mirroring the classifier's own existing apostrophe-stripping precedent) — not implemented here.

## Baseline vs. validated coverage (controlled, local-only validation)

**Registration** (config parse + idempotent DB write, isolated local SQLite, 0.17s): 21 `MonitoredSource` rows across all 10 councils (9 pre-existing + 12 new). 13 auto-linked to a real `LocalPlan` row; Rochdale (0) and Tameside (0) correctly stayed unlinked as designed; Salford (1 of 3) and Trafford (1 of 3) only auto-linked their *new* Gate-1 entry, not their pre-existing `emerging_plan` entry — direct, live confirmation of the `plan_version`-drift finding above.

**Discovery** (real network requests against real council websites, 95.29s total, 21 sources checked):

| Council | Sources checked | New reports found | Auto-classified | Needs review | Failed |
|---|---|---|---|---|---|
| Bolton | 3 | 1 | 0 | 1 | 0 |
| Bury | 4 | 7 | 7 | 0 | 0 |
| Manchester | 2 | 0 | 0 | 0 | **2** |
| Oldham | 1 | 0 | 0 | 0 | 0 |
| Rochdale | 1 | 0 | 0 | 0 | 0 |
| Salford | 3 | 33 | 6 | 27 | 0 |
| Stockport | 2 | 0 | 0 | 0 | 0 |
| Tameside | 1 | 0 | 0 | 0 | 0 |
| Trafford | 3 | 2 | 0 | 2 | 0 |
| Wigan | 1 | 0 | 0 | 0 | 0 |
| **TOTAL** | **21** | **43** | **13** | **30** | **2** |

Discovered documents genuinely span real, useful evidence (Salford's Housing Needs Assessment, viability assessment, SFRA, Green Belt Assessment; Bury's Publication Local Plan supporting documents) — the large `needs_review` count is the classifier working *correctly, conservatively* on genuinely mixed evidence-base pages, not a defect.

## Manchester — confirmed HTTP 403, requires manual/source-specific follow-up

Independently reproduced with a direct `requests.get` using the exact same `User-Agent` header `report_discovery.py`/`app.policy.monitor` already send (the same header that already works for Stockport's own previously-documented 403 case). Manchester's bot-protection rejects it regardless. **Not fixed in this gate** — attempting to defeat a council website's bot-protection is outside this gate's narrow, config-only scope and risks becoming a detection-evasion exercise rather than legitimate, config-level source registration. Flagged for Product Owner decision: either a small, standard-headers addition (Accept-Language/Referer — a legitimate completeness improvement, not evasion) in a future gate, or manual/operator-side document collection for Manchester specifically.

## Remaining missing evidence

- **By authority**: Manchester (network-blocked, needs follow-up); Rochdale, Tameside (correctly unlinked pending Product Owner plan-attribution decisions); Oldham, Wigan, Stockport (0 new documents found in this run — either their real monitoring pages' documents are already fully known/registered, or the real documents sit one navigation level deeper than this gate's existing single-hop crawl reaches; genuinely unclear from this run alone, flagged as **UNKNOWN — REQUIRES SOURCE AUDIT**, not claimed as success).
- **By evidence type**: Housing Delivery Test result remains **0/11 populated** platform-wide even after this gate — no council's real monitoring page surfaced a distinct, separately-linked HDT document in this run (several mention HDT narratively on the index page itself, e.g. Bolton, Trafford, Oldham, but a specific HDT Action Plan PDF link was not confirmed reachable in one hop for any of them). Completions/trajectory figures remain similarly unconfirmed pending either a deeper crawl or the newly-registered sources' own discovered documents actually being downloaded and extracted (a later step, not this gate's own scope — see Section 10's "discovery closure before extraction expansion").

## Councils requiring manual/source-specific follow-up

Manchester (bot-protection), Rochdale (needs its own independent `LocalPlan` row before structured fields can attach), Tameside (needs a Product Owner plan-attribution decision), and — pending confirmation of whether a deeper crawl reaches them — Oldham/Wigan/Stockport's own monitoring-report sub-pages.

## Recommendation for the subsequent LPDI intelligence gate

Do not proceed to authority-level LPDI aggregation/interpretation yet. First: (1) resolve Rochdale's/Tameside's plan-attribution questions (Product Owner decision, not a new audit); (2) run `python -m scripts.extract_plan_evidence` (existing, unmodified CLI) against the 43 newly-discovered reports to see how many of the 13 auto-classified ones (and any reviewer-approved `needs_review` ones) actually populate real `LocalPlan` housing-delivery fields — this gate deliberately stopped at discovery, per Section 10's own instruction, and did not run extraction against production; (3) investigate whether Oldham/Wigan/Stockport's monitoring pages have a real, reachable "Monitoring reports" sub-page this gate's single-hop crawl didn't reach; (4) decide Manchester's follow-up path.
