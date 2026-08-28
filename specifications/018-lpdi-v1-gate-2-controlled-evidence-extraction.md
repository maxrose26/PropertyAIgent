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

## Recommendations

1. **Do not yet proceed to LPDI authority-level aggregation.** Coverage remains thin (1 of 11 plans meaningfully improved this gate) and — more importantly — this gate surfaced a genuine, unresolved evidence-grounding risk (the wrong-plan-reference finding) that argues for caution before broader ancillary-document extraction is trusted at scale.
2. A future, dedicated gate should design and build a genuine same-plan-reference validator check before extraction is run more broadly against supporting/ancillary documents (Viability Assessments, SFRAs, etc.) — a real feature requiring its own product review, not a "smallest possible fix."
3. Resolve Bury's/Tameside's plan-attribution question (which of two real plans housing-delivery evidence should attach to) — a Product Owner decision, not an engineering one.
4. Consider whether the `local_plan` `MonitoredReport.source_type` bucket should be split more finely to stop conflating a real plan document with consultation-process schedules — a product/classification decision for a future gate.
5. Manchester's HTTP 403 remains unresolved (Gate 1 finding, unchanged).
