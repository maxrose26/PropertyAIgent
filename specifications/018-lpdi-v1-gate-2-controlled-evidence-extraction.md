# LPDI V1 Gate 2 — Controlled Evidence Extraction Pass

## Purpose

Not LPDI intelligence itself — a controlled, isolated exercise of the **existing, unmodified** plan-evidence extraction pipeline against Gate 1's discovered document cohort, to answer: what structured housing-delivery evidence can it actually, safely produce today, and what does that reveal about extraction *quality*, not just discovery coverage?

## Starting architecture (audited, unmodified)

`MonitoredSource → MonitoredReport → document_selection.DOCUMENT_TYPE_TO_CATEGORIES (routing) → [manual download — see finding below] → extraction.plan_evidence.extract_pdf_pages (pdfplumber, page-addressable) → extraction.plan_evidence.extract_plan_evidence (one OpenAI structured-output call per category) → evidence_validation.validate_facts (deterministic, no LLM) → extract_plan_evidence.run_extraction (writes PolicyChangeEvent, auto-applies only a genuinely-null field at "high" confidence, else queues for review) → LocalPlan / history.snapshot_field`.

**Key finding (Section 5A/9): there is no automated MonitoredReport→download step.** `app.policy.extract_plan_evidence`'s own module docstring states this explicitly: *"nothing here downloads a council's PDF on your behalf; `--pdf` is always a file you already have locally."* The real CLI (`python -m app.policy.extract_plan_evidence --pdf <local file>`) requires a human operator to have already fetched the document. This gate's own controlled-validation script therefore did exactly what an operator would do — fetched each candidate document's already-known URL with a plain `requests.get` (the same library and headers `report_discovery.py` already uses) and passed the resulting local file to the unmodified `run_extraction`. This is not a new download pipeline; it is the documented, expected manual step, scripted for a controlled batch rather than one CLI invocation at a time.

`resolve_plan(session, council_code, plan_id=None)` (unmodified) is the existing, sole attribution mechanism used: it looks up `LocalPlan` by `council_code` directly (never via `MonitoredReport.local_plan_id`, which — a second finding — turned out to be `None` on every single one of the 43 Gate 1-discovered reports, since they were mostly discovered via pre-existing council-level sources with no `plan_name`, not via Gate 1's own new `plan_name`-carrying sources). `resolve_plan` returns the single matching plan when exactly one exists, and **raises** when a council has more than one — the existing, correct, "STOP and ask" behaviour this gate relies on entirely for attribution safety.

## Extraction cohort — SAFE_TO_EXTRACT / STILL_NEEDS_REVIEW / EXCLUDED

Classification built entirely from existing, unmodified functions (`resolve_plan`, `document_selection.DOCUMENT_TYPE_TO_CATEGORIES`) — never a new attribution heuristic:

| Group | Count | Reasoning |
|---|---|---|
| **SAFE_TO_EXTRACT** | **6** | All Salford (`classification_status="auto"`, `source_type="local_plan"` — extraction-eligible for `plan_identity`/`housing_requirement` — and `resolve_plan("salford")` unambiguously resolves, since Salford has exactly one `LocalPlan` row) |
| **EXCLUDED** | **7** | All Bury (`classification_status="auto"`, same extraction-eligible type, but `resolve_plan("bury")` **raises** — Bury genuinely has 2 real `LocalPlan` rows in production, "Bury Local Plan" and the Places for Everyone joint plan — attribution is honestly ambiguous, not guessed) |
| **STILL_NEEDS_REVIEW** | **30** | Unchanged from Gate 1 — never touched, never blindly processed |

**Total: 43** (6 + 7 + 30), matching Gate 1's own measured cohort exactly.

No `needs_review` report was reclassified. No title-based or content-based attribution shortcut was invented for Bury/Tameside — `resolve_plan`'s own refusal is the entire disambiguation mechanism used, exactly as the real CLI already relies on it.

## Document retrieval and text extraction — the 6 SAFE_TO_EXTRACT documents

All 6 downloaded successfully (real `requests.get`, real council URLs already discovered by Gate 1, HTTP 200, `Content-Type: application/pdf`), all readable, all text-extractable by `pdfplumber` with no OCR required:

| # | Document | Size | Pages | Readable |
|---|---|---|---|---|
| 12 | 01. Publication SLP:CSA (the actual Local Plan) | 8.9 MB | 98 | Yes |
| 14 | 03. Schedule of responses (plan order) | 1.3 MB | 314 | Yes |
| 15 | 04. Schedule of responses (respondent order) | 1.1 MB | 254 | Yes |
| 26 | 14a. Viability Assessment — main report | 3.0 MB | 141 | Yes |
| 27 | 14b. Viability Assessment — appendices 1–5 | 8.2 MB | 285 | Yes |
| 28 | 14c. Viability Assessment — appendices 6–8 | 14.2 MB | 835 | Yes |

**Extraction-scope decision (cost-proportionate, reasoned, documented — never a code change):**
- **#12 (98 pages, the actual Local Plan document)** — extracted **in full**. Cost was trivial (see below), and this is genuinely the document most likely to state the plan's own housing requirement.
- **#26 (141 pages, Viability Assessment main report)** — extracted **bounded to pages 1–30** (front matter/introduction, where a viability study conventionally restates its plan's target as a modelling input, if anywhere).
- **#14, #15 (254–314 pages, consultation-response schedules)** — **not extracted**. These are who-commented-on-what logs, not policy/evidence text — substantively irrelevant despite being technically `classification_status="auto"` under the coarse generic `local_plan` type. **A real, demonstrated limitation of that type's coarseness**, documented below, not fixed (would require a new, narrower classification rule — out of this gate's scope).
- **#27, #28 (285–835 pages, viability appendices)** — **not extracted**. Technical site-by-site appendices; disproportionate page count for near-zero expected plan-level-fact yield.

This mirrors the existing CLI's own `--pages` convention (an operator-set bound, not a full-document default) and this codebase's own cost-consciousness precedent (Gate 4's bounded web-research budget) — applied here to extraction *scope*, never to extractor *code*.

## Field extraction results — the genuine, real output

**Document #12 (full, 98 pages):** 2 categories run (`housing_requirement`, `plan_identity`), 16 facts extracted, 0 rejected, 16 events created — **12 auto-applied**, 4 correctly queued for review (a title/version/status/planning-system field where the extraction disagreed with an already-partially-set value). Real, grounded, verified result: **`annual_housing_requirement = 1,658`**, **`total_housing_requirement = 34,818`**, both with real page-18 excerpts ("*phased at an average of 1,658 dwellings per annum across the plan period*"; "*an overall housing requirement of at least 34,818 net additional dwellings for Salford over the period 2022 to 2043*") — this is genuine, new, structured LPDI-relevant evidence, extracted correctly, through the completely unmodified pipeline.

**Document #26 (bounded, pages 1–30):** 2 categories run, 10 facts extracted, **2 rejected** (validator correctly caught them — see failure taxonomy), 8 events created — 1 auto-applied, 7 queued for review.

## A genuine, demonstrated grounding-gap finding — the single most important result of this gate

The one fact auto-applied from document #26 (`adoption_date = "18 January 2023"`) was independently, directly verified against the real downloaded PDF and found to be **wrong for the plan it was attributed to**. The document's own text (pages 3, 7, 12, 26) explicitly states: *"This work follows on from Part One of the Local Plan – the Salford Local Plan: Development Management Policies and Designations (SLP:DMP), which was adopted on 18 January 2023."* **SLP:DMP is a different, sibling planning document — not the Salford Local Plan: Core Strategy and Allocations (SLP:CSA) this extraction run was attributing facts to**, which is explicitly still at Publication/Regulation-19 stage, not adopted.

`validate_fact` correctly confirmed the excerpt genuinely contains "18 January 2023" (its whole anti-hallucination purpose) — but it has **no mechanism to verify the claim is about the same plan** the whole document is being processed against. `resolve_plan` correctly identified which `LocalPlan` row the *document* belongs to; nothing in the pipeline checks whether a specific *sentence* inside a supporting/ancillary document (a Viability Assessment referencing its own plan's predecessor) is genuinely about that same plan. This is a real, concrete, previously-undocumented gap in the evidence-grounding architecture — reproduced as a permanent regression test (`test_a_correctly_excerpted_fact_about_a_different_named_plan_can_still_auto_apply`), **not fixed here**: a genuine fix would require a real same-plan-reference check (recognising when a document explicitly names a different plan and declining to attribute nearby facts to the plan being extracted for) — a real, non-trivial validator enhancement, not a "smallest possible fix" within this gate's narrow scope (Section 21).

**This finding was left in place in the isolated local validation database only — never applied to production, never corrected retroactively (the finding itself is the point).**

## Provenance behaviour

Confirmed unchanged and complete: every `PolicyChangeEvent` this run created carries `source_document_url`, `source_document_title`, `source_page`, `source_excerpt`, `extraction_method="ai_structured_extraction"`, `extraction_prompt_version`, `monitored_report_id`, `confidence` — verified directly against the real run's own output and locked by a dedicated test.

## Temporal/version behaviour

Confirmed unchanged and correct: `classify_evidence_confidence` auto-applies **only** when the field was genuinely null beforehand **and** confidence was reported "high" — any subsequent extraction against an already-populated field (real example: `raw_status`, which has a non-null `"unknown"` default and therefore can *never* auto-apply, even on a genuine first extraction) is always queued for review, never silently overwritten. Verified directly and locked by a dedicated test (`test_a_second_extraction_for_an_already_populated_field_never_auto_applies`).

## Conflict handling

Not exercised at the multi-report level in this narrow run (only one report per field succeeded per plan) — the existing `resolve_report_conflict`/`DOCUMENT_TYPE_PRECEDENCE` machinery (Gate 1, unchanged) remains the mechanism for that scenario, untouched here.

## Idempotency

Confirmed directly: re-running extraction against the same content produces zero new events (`unchanged_skipped` for an already-matching auto-applied field; the existing `_find_pending_proposal` de-duplication for an already-pending review fact) — locked by a dedicated test.

## Failure taxonomy (measured, this gate's own run)

| Category | Count | Detail |
|---|---|---|
| A. Download failure | 0 | All 6 SAFE_TO_EXTRACT documents downloaded successfully |
| B. Access blocked | 2 | Manchester's 2 discovery-stage sources (Gate 1 finding, unchanged — HTTP 403) |
| C. Non-PDF/unsupported format | 0 | Not observed in this cohort |
| D. Unreadable/scanned document | 0 | All 6 downloaded PDFs were text-extractable, no OCR needed |
| E. Text extraction failure | 0 | Not observed |
| F. Report misclassification | 30 (needs_review, correctly deferred) + a distinct coarseness finding (below) | |
| G. Plan attribution unresolved | 7 | Bury — genuine 2-plan ambiguity, correctly excluded |
| H. Evidence not present | 4 of 8 `housing_requirement` fields on document #12 (housing_need_annual/total, unmet_need, neighbouring_authority_contribution) correctly returned null | Honest absence, never fabricated |
| I. Extractor failed despite evidence present | 0 | Not observed |
| J. Validator rejected | 2 | Document #26 — 2 facts rejected by `evidence_validation.validate_facts` (working correctly) |
| K. Conflicting evidence | 0 (not exercised at multi-report level this run) | |
| L. Other | **1 — the grounding-gap finding above** | A correctly-excerpted fact about a verifiably different, sibling plan document, auto-applied |

**A distinct, additional finding under F**: the generic `local_plan` `MonitoredReport.source_type` bucket conflates the actual plan document with ancillary, substantively-irrelevant consultation-process documents (schedules of responses) discovered from the same crawl — real, demonstrated, not fixed here (would need a narrower classification rule, itself requiring product review, not invented unilaterally).

## Extractor code changes

**None.** No app-code was changed anywhere in `app.policy.extract_plan_evidence`, `app.extraction.plan_evidence`, `app.policy.evidence_validation`, `app.policy.document_selection`, or any model. Every finding above (the download-step gap, the plan-attribution-via-`resolve_plan`-only discipline, the ancillary-document grounding gap, the coarse `local_plan` classification bucket) is documented as a real limitation for future product decision, never patched unilaterally.

## Production BEFORE coverage (read-only, confirmed)

| LocalPlan | annual_req | total_req | HDT | 5YHLS years | supply base date | deliverable supply | buffer % |
|---|---|---|---|---|---|---|---|
| Bury Local Plan | 452 | 9,486 | — | — | — | — | — |
| Bury / PfE (shared) | — | — | — | — | — | — | — |
| Stockport Local Plan | — | 31,790 | — | 1.77 | 1 Apr 2024 | 3,847 | 20 |
| Salford SLP:CSA | — | — | — | — | — | — | — |
| Trafford Local Plan | — | — | — | — | — | — | — |
| Manchester (draft) | — | — | — | — | — | — | — |
| Oldham (saved UDP) | — | — | — | — | — | — | — |
| Tameside ×2 | — | — | — | — | — | — | — |
| Wigan (initial draft) | — | — | — | — | — | — | — |
| Bolton's Allocations Plan | — | — | — | — | — | — | — |

## Controlled AFTER coverage (isolated local database only — never applied to production)

| LocalPlan | annual_req | total_req | plan_period | publication_date | adoption_date | Supporting reports | Review-required events |
|---|---|---|---|---|---|---|---|
| **Salford SLP:CSA** | **1,658** (new) | **34,818** (new) | **2022–2043** (new) | **July 2026** (new) | 18 Jan 2023 (⚠ likely wrong-plan — see finding above) | 2 (documents #12, #26) | 11 (4 from #12 + 7 from #26) |
| All other 10 plans | unchanged | unchanged | unchanged | unchanged | unchanged | 0 (not extracted this gate) | 0 |

## Authority-by-authority four-stage funnel (real numbers only)

| Council | Sources configured | Reports discovered | Documents retrieved/text-extracted | Reports producing valid (auto-applied) evidence | LocalPlan fields populated |
|---|---|---|---|---|---|
| Bolton | 3 | 1 | 0 | 0 | 0 |
| Bury | 4 | 7 | 0 (excluded — attribution ambiguous) | 0 | 0 |
| Manchester | 2 | 0 (network blocked) | 0 | 0 | 0 |
| Oldham | 1 | 0 | 0 | 0 | 0 |
| Rochdale | 1 | 0 | 0 | 0 | 0 |
| **Salford** | **3** | **33** | **6 retrieved/extracted, 2 sent to AI extraction** | **2** | **13** (12 correct + 1 wrong-plan finding) |
| Stockport | 2 | 0 (already known) | — | — | unchanged (pre-existing 7 fields) |
| Tameside | 1 | 0 | 0 | 0 | 0 |
| Trafford | 3 | 2 (needs_review) | 0 | 0 | 0 |
| Wigan | 1 | 0 | 0 | 0 | 0 |

## Evidence-coverage-quality classification (explicitly NOT a Planning Potential/performance judgement)

Defined here transparently, describing evidence **completeness only**:
- **GOOD COVERAGE**: authority-level requirement, delivery, and 5YHLS/HDT figures all present and current.
- **PARTIAL COVERAGE**: some genuine structured figures present, meaningful gaps remain (e.g. requirement known, delivery/HDT/5YHLS unknown).
- **MINIMAL COVERAGE**: one or two isolated figures only, most gaps remain.
- **NO USABLE COVERAGE**: nothing structured populated.

| Council | Classification |
|---|---|
| Stockport | PARTIAL — requirement/need totals + a real, current 5YHLS position; HDT/completions still missing |
| Bury | PARTIAL — annual/total requirement known (pre-existing); everything else missing |
| **Salford** | **PARTIAL** (upgraded this gate) — requirement now known (new); HDT/5YHLS/completions still missing, and one field (`adoption_date`) carries a documented, unresolved grounding risk |
| Manchester, Oldham, Rochdale, Tameside, Trafford, Wigan, Bolton | NO USABLE COVERAGE |

## OpenAI usage (this gate's own live, controlled run — separate from the automated test suite, which uses mocks only)

2 real extraction runs (documents #12, #26), 4 category passes total, `input_tokens=89,178`, `output_tokens=1,790`, estimated cost **$0.0145** (gpt-4o-mini, the platform's own existing model for this pipeline — no new model introduced). All structured outputs validated against the real JSON schema successfully (no malformed-response failures). No `web_search_preview`, no authority scoring/synthesis call of any kind.

## Remaining evidence gaps

By authority: Bolton (1 irrelevant report only), Manchester (blocked), Oldham/Rochdale/Tameside/Wigan (0 discovered reports this run), Bury (attribution ambiguous), Trafford (2 needs_review only). By evidence type: **HDT remains 0/11 populated platform-wide** — no council's SAFE_TO_EXTRACT cohort this gate contained an `authority_monitoring_report`/`housing_land_supply_statement`-typed document at all (Salford's 6 were all generically `local_plan`-typed) — five-year-supply and completions/trajectory fields remain equally unaddressed by this gate's own narrow cohort.

## Recommendations (Gate 2's own, superseded in part — see Gate 2A below)

1. ~~Do not yet proceed to LPDI authority-level aggregation~~ — still true, but for a narrower reason: Gate 2A closed the specific grounding-gap risk named here; see Gate 2A's own recommendations for what remains.
2. ~~A future, dedicated gate should design and build a genuine same-plan-reference validator check~~ — **done, this gate (2A)**; see below.
3. Resolve Bury's/Tameside's plan-attribution question — **substantially addressed for Bury this gate (2A)** via report-level attribution rather than a schema change; Tameside remains open.
4. Consider whether the `local_plan` `MonitoredReport.source_type` bucket should be split more finely — still open, unchanged.
5. Manchester's HTTP 403 remains unresolved — still open, unchanged.

---

# Gate 2A — Multi-Plan Attribution & Same-Plan Evidence Validation Hardening

## Purpose

Gate 2 found and documented, but deliberately did not fix, two related attribution problems: (1) a fact whose excerpt genuinely supports a claimed value can still be about a verifiably different, sibling plan document (the Salford SLP:CSA/SLP:DMP finding), and (2) a genuinely multi-plan authority (Bury: its own Local Plan *and* Places for Everyone) had every one of its reports excluded outright rather than resolved. Gate 2A closes both with the smallest reusable, generic (never per-authority-hardcoded) hardening the existing architecture supports — **no schema change, no new database table.**

## Root cause 1 — Salford sibling-plan contamination

`validate_fact`'s excerpt-must-contain-the-claimed-value check (Gate 1/2, unchanged) answers *"does this excerpt support this number?"*, never *"is this excerpt about the plan being extracted for?"*. Nothing in the pipeline compared a fact's supporting text against the identity of any *other* known plan.

## Root cause 2 — Bury's blanket exclusion

`resolve_plan(session, council_code, plan_id=None)` (Gate 1/2, still unchanged — it remains the correct human-operator-facing CLI tool for its own use case) filters `LocalPlan.council_code == council_code` directly. Two real findings from auditing this properly this gate:

1. **`plans_for_council(session, council_code)` already exists** (`app.policy.joint_plans`, built in the prior "Joint Plan Support" sprint) and correctly resolves Places for Everyone as a candidate for **every one of its 9 real participating authorities** via the `LocalPlanCouncil` join table — not just Bury (PfE's `LocalPlan.council_code` legacy/lead value). `resolve_plan` was never updated to use it. Rebuilding the Gate 2A isolated validation database with the real `LocalPlanCouncil` backfill applied (the same `ensure_council_links_for_plan` logic `scripts/migrate_joint_plan_support.py` already runs in production) confirms this directly: Salford, Trafford, Manchester, Oldham, Wigan, Bolton, and Rochdale are **all** genuinely multi-plan authorities via PfE membership — Gate 2's own Salford SAFE_TO_EXTRACT cohort was only "unambiguous" because `resolve_plan`'s raw-column check happened not to notice PfE for Salford, not because Salford was genuinely single-plan. This is corrected, not just documented: Gate 2A's own attribution results for Salford (below) prove the new mechanism still resolves the 6 Salford reports correctly even once Salford is properly recognised as multi-plan.
2. **The 7 Bury reports were never actually discovered via the plan-linked `monitoring_page` source** (which does correctly carry `local_plan_id`) — they were all discovered via the plan-unlinked `landing_page` source, so `MonitoredReport.local_plan_id` was `None` on all 7, and `resolve_plan`'s blanket 2-plans-exist refusal excluded every one of them regardless of what each document actually was.

## Report-level attribution — `app.policy.plan_attribution.attribute_report`

New, small, generic module (`app/policy/plan_attribution.py`) — never a per-authority rule. For each report:

1. `plans_for_council` gives the true candidate set (correctly including joint plans).
2. Exactly one candidate → `PLAN_MATCH` (trivial — single-plan authorities are completely unaffected).
3. **Tier 1**: `MonitoredReport.local_plan_id` (inherited from an explicitly plan-linked discovering source, e.g. `plan_name` set in `config/policy_sources.yaml`) → `PLAN_MATCH`, the strongest signal.
4. **Tier 2**: the report's own title contains a configured identity alias (`config/plan_aliases.yaml`, falling back to the plan's own `plan_name` for any plan with no config entry) for exactly one candidate → `PLAN_MATCH`. More than one candidate named → `AMBIGUOUS`.
5. **Tier 2b**: the discovering source *page's own title* (not the individual document's) carries an alias for exactly one candidate → `PLAN_MATCH`. Needed because a Viability Assessment or a schedule of responses rarely restates which plan it belongs to in its own title, even though the landing page that discovered it is itself scoped to one specific plan's consultation.
6. **Tier 3**: no signal ties it to one plan, but its `source_type` is one that conventionally carries authority-level, not plan-specific, evidence (`AUTHORITY_WIDE_CAPABLE_SOURCE_TYPES` — AMR/housing-delivery/five-year-supply/trajectory types) → `AUTHORITY_WIDE`, `plan=None`.
7. Otherwise → `AMBIGUOUS`, review-required, never guessed.

`resolve_plan` itself is untouched — `attribute_report` is the new, additional, automated-cohort-classification path; the CLI's own human-operator contract is unchanged.

## Fact-level sibling-plan validation — `evidence_validation.detect_sibling_plan_reference`

New, small, optional (fully backward-compatible — every existing caller of `validate_fact`/`validate_facts` is unaffected) check, reusing the *existing* rejection mechanism (`is_valid=False`, `rejection_reason` set) rather than inventing a new outcome type. Given the target plan's known sibling alias groups (`plan_identity.sibling_alias_groups`), a fact is rejected if a sibling's name appears in its excerpt.

**A real, live re-run of the exact original finding demonstrated the excerpt-only version of this check is insufficient**: a fresh, real OpenAI extraction call against the same Viability Assessment returned the *same* short excerpt as Gate 2 originally saw — `"adopted on 18 January 2023"` — with no sibling name in it at all, even though the full sentence in the source (`"...the Salford Local Plan: Development Management Policies and Designations (SLP:DMP), which was adopted on 18 January 2023."`) plainly names the sibling plan. The model's own returned `source_page` for this fact (15) also does not match any of the real pages (3, 7, 8, 12, 26) that actually contain this text — a second, separate, previously-undocumented extractor citation-accuracy limitation.

**Smallest possible fix actually implemented** (Section 21 discipline — reproduced live, fixture/test added, minimal validator-only change, no new OpenAI capability, no prompt change): `detect_sibling_plan_reference` now also accepts `source_text` (the full text of the pages the extraction pass actually read, already available in `run_extraction` — nothing new is fetched or sent to OpenAI) and searches the **single sentence** containing the fact's excerpt for a sibling alias, not just the excerpt string itself.

**Why bounded to one sentence, not the whole page/document**: a second real, live extraction (the Bury Local Plan regression, below) demonstrated a document can legitimately mention a sibling plan (Places for Everyone) in a *different, nearby* sentence while correctly stating its *own* plan's genuine figure — Bury's own housing requirement (452/9,486 dwellings) sits in the same paragraph, one sentence away from an explicit "Places for Everyone" reference explaining where the underlying policy figure originates. A page- or paragraph-wide check would have wrongly blocked this genuine, correctly-attributed evidence. The sentence boundary is the narrowest window that catches the real Salford case while preserving the real Bury case — verified directly against both, not assumed.

**Re-verified directly with a fresh, live OpenAI call** (not reused from the first run, to rule out having gotten lucky): the same excerpt (`"adopted on 18 January 2023"`) came back again, and this time `validate_fact` correctly rejected it — `rejection_reason: "supporting evidence explicitly references a different Local Plan ('Salford Local Plan: Development Management Policies and Designations')"`.

## Alias/config strategy — `config/plan_aliases.yaml`

New config file, same pattern as the existing `config/joint_plans.yaml`: entries matched by exact `(council_code, plan_name, plan_version)` triple (falling back to `(council_code, plan_name)` alone when `plan_version` drifts — a known, real, already-documented risk in this codebase per spec 017's own note on Salford's `plan_version` string not always matching the live value one-for-one; without this fallback, a version mismatch would make `sibling_alias_groups` mistake a plan's own identity entry for a sibling of itself and wrongly block its own genuine evidence). Four entries: `bury_local_plan`, `bury_pfe`, `salford_slp_csa`, and **`salford_slp_dmp`** — an **identity-only** entry (`plan_name: null`) that exists solely so SLP:DMP's own name/aliases can be recognised as "a different, real plan" for contamination-detection purposes, without ingesting it as a new `LocalPlan` row (no schema/data-model change). Every plan not listed here still works correctly — `aliases_for_plan` falls back to the plan's own `plan_name`, `sibling_alias_groups` returns no groups, degrading to "nothing to conflict with." No keyword hack, no per-authority `if council == "bury"` logic anywhere in application code — every distinguishing string lives in this one config file.

## Bury/Places for Everyone analysis — all 7 Gate 2-excluded reports individually reassessed

| # | Title | Attribution result | Extraction scope decision |
|---|---|---|---|
| 2 | Publication Local Plan | **BURY_LOCAL_PLAN** (title alias) | SAFE_TO_EXTRACT — the actual plan document (189 pages, extracted in full) |
| 3 | Publication Local Plan Policies Map | **BURY_LOCAL_PLAN** (title alias) | SAFE_TO_EXTRACT — 1 page, extracted (near-zero cost) |
| 4 | Publication Local Plan representation guidance note | **BURY_LOCAL_PLAN** (title alias) | IRRELEVANT — pure procedural document (how to make a representation), not a source of plan evidence by genre |
| 5 | Publication Local Plan Statement of the representations procedure | **BURY_LOCAL_PLAN** (title alias) | IRRELEVANT — same, pure procedure document |
| 6 | Publication Local Plan representation form (word version) | **BURY_LOCAL_PLAN** (title alias) | IRRELEVANT — non-PDF format (`.docx`); existing pipeline is PDF-only (`pdfplumber`) — Category C, genuine format limitation, and a blank form template regardless |
| 7 | Publication Local Plan representation form (pdf) | **BURY_LOCAL_PLAN** (title alias) | IRRELEVANT — blank/fillable representation form template, inherently no plan-evidence content |
| 8 | Local Plan Consultation Statement (June 2026) | **BURY_LOCAL_PLAN** (discovering source page title alias — the document's own title carries no plan name) | SAFE_TO_EXTRACT — 25 pages, extracted in full |

**Result: 7/7 attributed (all `BURY_LOCAL_PLAN`, zero `PLACES_FOR_EVERYONE`, zero `AUTHORITY_WIDE`, zero `AMBIGUOUS`, zero `IRRELEVANT`-for-attribution-purposes)** — none of the 7 real titles mention Places for Everyone/PfE at all, so no false PfE attribution was ever at risk; the mechanism resolved all 7 on real, explicit signals, never a guess. Of those 7, **3 were sent to extraction** (#2, #3, #8) and **4 were excluded from extraction** on documented content/format grounds (not attribution grounds) — comfortably clearing Section 18's own stated bar ("if only 3/7 can be safely attributed, that is acceptable").

## Controlled Bury extraction (isolated Gate 2A database, zero production writes)

| Report | Categories | Facts extracted | Rejected | Auto-applied | Needs review |
|---|---|---|---|---|---|
| #2 (full plan, 189p) | housing_requirement, plan_identity | 13 | 2 | 8 | 4 |
| #3 (Policies Map, 1p) | housing_requirement, plan_identity | 1 | 0 | 0 | 1 |
| #8 (Consultation Statement, 25p) | housing_requirement, plan_identity | 11 | 7 | 0 | 6 |

Real, grounded result: `annual_housing_requirement = 452`, `total_housing_requirement = 9,486` (both auto-applied, page-28 excerpts — "*a requirement of 452 dwellings per year will apply...*"; "*this results in a total housing requirement of 9,486 dwellings from 2022 – 2043*"), plus `plan_period_start/end = 2022/2043`, `publication_date`, `expected_adoption_date`, `next_milestone`/`next_milestone_date` auto-applied from #2. **These figures are explicitly sourced from Places for Everyone's own Policy JP-H1 ("the scale of housing growth...has been set through the Joint Places for Everyone Development Plan") — Bury's own Local Plan text says so directly, in a *different* sentence one paragraph away from the figures themselves.** The sentence-bounded sibling check correctly did **not** treat this as contamination (verified directly, not assumed — see the dedicated regression test) because the figures are genuinely, legitimately Bury Local Plan's own stated requirement, merely derived from the joint plan's policy — not a case of the wrong document's fact being misattributed.

## Controlled Salford re-run (sibling hardening active)

| Report | Facts extracted | Rejected | Auto-applied | Needs review |
|---|---|---|---|---|
| #12 (full plan, 98p) | 13 | 2 | 8 | 5 |
| #26 (Viability Assessment, bounded 1–30p) | 8 | 3 | 1 | 6 |

**`adoption_date` is no longer among the auto-applied facts.** Directly re-verified with an isolated, fresh OpenAI call (`app.extraction.plan_evidence.extract_plan_evidence` against the real PDF, real API, outside of `run_extraction`): the model still returns `adoption_date = "18 January 2023"` with the same short excerpt; `validate_facts` (with the target plan's sibling groups and `source_text` supplied) now correctly rejects it with `rejection_reason: "supporting evidence explicitly references a different Local Plan ('Salford Local Plan: Development Management Policies and Designations')"`. Genuine SLP:CSA evidence remains fully intact: `annual_housing_requirement = 1,658`, `total_housing_requirement = 34,818`, `plan_period_end = 2043`, `requirement_basis`, `publication_date`, `expected_adoption_date`, `next_milestone`/`next_milestone_date`, `status_notes` all still auto-applied exactly as Gate 2 found them (real run-to-run wording/page-citation variance is expected LLM non-determinism, not a regression — the same real figures and real excerpts recur every run).

## Authority-wide evidence — architectural finding (not exercised, still worth recording)

`AUTHORITY_WIDE_CAPABLE_SOURCE_TYPES` (AMR/housing-delivery/five-year-supply/trajectory `source_type`s) exists and is tested (unit level: an AMR-typed report with no plan-specific title signal correctly returns `AUTHORITY_WIDE`, `plan=None`, never forced onto either candidate plan). **No report in this gate's real 43-report cohort actually reached this branch** — none of Bury's 7 reports, nor Salford's 6, are AMR/housing-delivery-typed. The deeper architectural question the task poses — *can this platform actually WRITE structured authority-level evidence once one is found?* — was audited: `PolicyChangeEvent.local_plan_id` is nullable (already usable for a plan-independent event), but every structured evidence FIELD (`annual_housing_requirement`, `homes_delivered_latest_period`, etc.) lives only on `LocalPlan`, never on `Council`. **There is currently no authority-level (Council-scoped) structured evidence storage** — a real, confirmed gap, matching the task's own anticipated finding. Not a blocker for this gate (nothing needed to be written this way), but a genuine limitation for the next gate that discovers a real AMR: it will hit this exact wall. **Not fixed here — no schema change was made or proposed; recorded per Section 20 for the next gate that needs it.**

## Schema/dependency changes

**None.** `git diff --stat` against Gate 2's own HEAD (`88322f6`) confirms: 2 new small modules (`app/policy/plan_identity.py`, `app/policy/plan_attribution.py`), 1 new config file (`config/plan_aliases.yaml`), targeted edits to `app/policy/evidence_validation.py` (2 new optional, backward-compatible parameters + 1 new function) and `app/policy/extract_plan_evidence.py` (4 lines wiring `sibling_alias_groups`/`source_text` through), 2 new test files. Zero migrations. Zero new tables. Zero new columns. Zero new dependencies (`pyyaml` was already a dependency — `config/joint_plans.yaml` already used it).

## Remaining limitations (Gate 2A)

- **The sentence-bounded sibling check is not a complete solution** — it depends on the model's excerpt/value and the source text lining up within one sentence; a contamination spread across two sentences (e.g. "...SLP:DMP..." in one sentence, "...adopted 18 January 2023" in the next) would still slip through. No case requiring a wider check was found in this gate's real cohort, but this is a real, honestly-stated limit, not a claim of completeness.
- **Extractor page-citation accuracy is unreliable** — the model's own `source_page` for the contaminated fact (15) never matched any real occurrence (3, 7, 8, 12, 26) of the text it claims to cite. Not investigated further this gate (out of scope — a prompt/extraction-behaviour question, not an attribution/validation one); worth a dedicated look in a future gate since it also affects how much a human reviewer can trust `source_page` when confirming a `needs_review` fact by hand.
- **Tameside's own 2-plan ambiguity is untouched** — no Tameside report existed in this gate's cohort to test against; the mechanism should generalise (it is not Bury-specific) but this was not demonstrated live.
- **The authority-wide evidence storage gap is real but unexercised** — see above.

## Revised evidence coverage (Gate 2 + Gate 2A combined)

| Council | Gate 2 coverage | Gate 2A change | Coverage after 2A |
|---|---|---|---|
| Bury | PARTIAL (pre-existing 452/9,486 only) | +`plan_period_start/end`, `publication_date`, `expected_adoption_date`, `next_milestone`/date (5 new fields, all real, isolated DB only) | PARTIAL (broader) |
| Salford | PARTIAL (13 fields, 1 flagged wrong) | `adoption_date` misattribution now blocked (correctly null instead of wrong); all other genuine fields unchanged | PARTIAL (same breadth, **correct** now instead of 1 field wrong) |
| All other 9 authorities | unchanged | unchanged (no report from any of them reached extraction this gate either) | unchanged |

## Success criteria — verified against Section 29's own 12 items

1. ✅ Salford sibling-plan contamination can no longer auto-apply (verified directly, twice, with live OpenAI calls).
2. ✅ Correct Salford evidence remains usable (annual/total housing requirement, plan period, publication date, etc. all still auto-apply).
3. ✅ Multi-plan authorities are no longer handled by blanket exclusion (Bury: 7/7 attributed, not 0/7).
4. ✅ Bury's 7 reports individually classified by evidence scope (table above).
5. ✅ Deterministically attributable Bury reports safely reached the existing extraction pipeline (3 real, isolated-DB extractions).
6. ✅ PfE evidence is not written to Bury Local Plan merely because Bury participates in PfE (all 7 correctly resolved to Bury Local Plan on real title signals, zero PfE misattribution risk existed in this real cohort — and the mechanism itself keeps them structurally distinct, tested at the unit level with a synthetic PfE-titled report).
7. ✅ Bury Local Plan evidence is not written to PfE merely because both belong to the same authority (same mechanism, same test coverage).
8. ✅ Authority-wide evidence is identified rather than forced into a plan (mechanism exists, tested; no live case existed in this cohort to exercise it further).
9. ✅ Ambiguous reports remain review-required (`AMBIGUOUS` status never silently resolved; unit-tested with a two-candidate-named-in-title case).
10. ✅ Zero production writes (isolated Gate 2A SQLite database only, throughout).
11. ✅ No new scoring/intelligence introduced (attribution and validation only).
12. ✅ Tests prove the solution is reusable beyond Bury (single-plan-authority test, generic multi-plan-with-no-signal test, PfE-side attribution test, authority-wide test — none reference Bury by name in their logic, only in fixture data).

## Recommendations (Gate 2A)

1. Do not yet proceed to LPDI authority-level aggregation — coverage is still thin (2 of 11 plans meaningfully improved across Gates 2+2A) and the authority-wide evidence storage gap remains real and unaddressed.
2. Build the authority-level (Council-scoped) structured evidence storage this gate found missing, before any future gate needs to write a genuine AMR-derived authority-wide fact.
3. Consider widening the sibling-plan sentence check if a future real case demonstrates a two-sentence-spanning contamination (do not widen pre-emptively based on assumption, per Section 21's own discipline).
4. Investigate the extractor's own page-citation accuracy — a real, separate, previously-undocumented limitation surfaced as a side effect of this gate's work.
5. Extend the same Tameside-vs-its-2-plans question Bury's own resolution here modelled, once a real Tameside report exists in a future cohort to test against.
6. Manchester's HTTP 403 remains unresolved (Gate 1 finding, unchanged).
