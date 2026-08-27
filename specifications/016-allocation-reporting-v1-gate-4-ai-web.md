# Allocation Reporting V1 Gate 4 — Cross-Site AI Intelligence + Bounded Web Research

## Purpose

Answers, across a shortlist as a whole (not allocation-by-allocation): *"Looking across these shortlisted opportunities, what actually matters and what should I investigate first?"* Adds ONE new intelligence layer on top of Gate 2/3's deterministic report: bounded external web research (Layer 2) + one report-level AI synthesis call (Layer 3) that reasons across both PropertyAIgent's own trusted evidence (Layer 1) and the curated web evidence. Never a numerical score, never a replacement for the deterministic report — the Gate 3 PDF stays fully, independently available.

## Three-layer evidence architecture

- **Layer 1 — PropertyAIgent trusted evidence**: `app.reporting.allocation_report.AllocationReportContext` (Gate 2/3, completely unchanged — zero diff in this gate).
- **Layer 2 — external web evidence**: `app.reporting.allocation_web_research.AllocationWebResearchContext` (new). Bounded, curated, never persisted, never merged into Layer 1.
- **Layer 3 — AI interpretation**: `app.reporting.cross_site_intelligence.CrossSiteIntelligence` (new). Reasons across Layers 1+2; a dedicated grounding validator rejects any output whose material claims aren't traceable back to them.

External web evidence never silently overwrites a PropertyAIgent trusted fact. A conflict is surfaced in prose (prompt Rule 5), never silently resolved.

## Existing web-search capability audit (Section 30)

Confirmed BEFORE writing any new code: `app.enrichment.news_contact_lookup.find_scheme_news_contacts` already calls `client.responses.create(model=..., input=..., tools=[{"type": "web_search_preview"}])` in production, on the installed `openai` SDK (2.44.0, unpinned in `requirements.txt`) — the OpenAI Responses API's web-search tool. **No new dependency, no new environment variable, no SerpAPI/Tavily/Bing integration.** `app.reporting.allocation_web_research` follows that exact same two-call shape (free-text search call, then a separate structured-extraction call) for the same, already-proven reliability reason documented in that module's own docstring (a single call combining `web_search_preview` with strict structured output was found unreliable in production).

## Bounded search budget (Section 5/31/32)

| Limit | Value |
|---|---|
| Max search angles instructed per allocation | 3 (`MAX_SEARCHES_PER_ALLOCATION`) |
| Max shortlist-level comparative angles | 2 (`MAX_SHORTLIST_LEVEL_SEARCHES`, picks the 2 most-represented councils deterministically — never one query per council) |
| Max evidence items retained per allocation | 3 (`MAX_SOURCES_RETAINED_PER_ALLOCATION`) |
| Max evidence items retained shortlist-level | 4 (`MAX_SOURCES_RETAINED_SHORTLIST_LEVEL`) |
| Per-search-call timeout | 30s (`SEARCH_TIMEOUT_SECONDS`, via `client.with_options(timeout=...)`) |

One `responses.create` call per allocation performs the search (the model may issue several underlying web searches within that one call to satisfy a multi-angle prompt — this is how `web_search_preview` is designed to be used — but the prompt explicitly caps how many angles/searches it should attempt); one separate call extracts structured evidence from whatever was found. For a normal 5-allocation shortlist this is `5 × 2 + 1 shortlist-level × 2 = 12` OpenAI calls for research, plus exactly 1 for cross-site synthesis — never N-sites × N-searches × N-generation.

## Query construction (Section 6)

`_build_allocation_search_angles`/`_build_shortlist_search_angles` build every query string from `AllocationReportEntry`'s own already-trusted identity fields (allocation name, reference, council, Local Plan, trusted Developer/Applicant name) by plain Python string formatting — the model is never asked to invent what to search for.

## Source tier classification (Section 7)

Deterministic, Python-side, domain-pattern classification (`_classify_source_tier`) — **never** the model's own self-assessment. `.gov.uk`/`.gov.wales`/`planningportal.co.uk`/`planninginspectorate.gov.uk` + the report's own council website/base-URL domains (passed in by the caller, e.g. the Streamlit page, from `app.config.load_councils()`) → `official_primary`. A curated allow-list of recognised UK property/planning press (Place North West, Insider Media, EGi, Construction Enquirer, etc.) → `strong_secondary`. Everything else → `contextual`. **Known, accepted V1 limitation**: this allow-list is not exhaustive — an un-listed genuine local paper falls through to `contextual` rather than `strong_secondary`, the deliberately conservative direction to be wrong in.

## WebEvidenceItem / AllocationWebResearchContext (Section 8/9)

`WebEvidenceItem`: `evidence_id` (stable "W1", "W2", ... report-wide sequence), `allocation_id` (`None` for shortlist-level), `allocation_name`, `title`, `publisher`, `url`, `published_date`, `retrieved_at`, `evidence_type`, `summary`, `source_tier`, `confidence`, `query`, `relevance_reason`. Never a raw search-result blob — always the curated, extracted, minimum-viability-gated (real URL + non-empty title/publisher) shape.

`AllocationWebResearchContext`: `evidence_by_allocation`, `shortlist_level_evidence`, `searches_attempted`, `searches_succeeded`, `research_timestamp`, `failures`. Deduplicated by URL, report-wide, first-occurrence-wins (deterministic). **Never persisted** — a plain, report-run-only dataclass tree, exactly like `AllocationReportContext` itself never was (Section 36).

## Freshness (Section 10)

`published_date` is retained exactly as discovered (or `None` — never fabricated). `retrieved_at` is always stamped. An undated item is passed to the model explicitly flagged "treat with caution for current-status claims" (`_render_web_evidence`).

## No-result / failure semantics (Section 11/35)

A search returning no useful findings is a valid, non-fatal outcome — nothing is added, nothing is logged as a failure. An API/tool exception (search or extraction) is caught, recorded in `.failures`, and research continues for every other allocation — `build_allocation_web_research_context` **never raises**. Confirmed by dedicated tests including a total-failure scenario (every search fails) still returning a valid, empty-but-well-formed context.

## Cross-site synthesis (Section 16/28)

`app.reporting.cross_site_intelligence.generate_cross_site_intelligence(client, report_context, web_context) -> CrossSiteIntelligenceResult`. **Exactly ONE** `responses.create` call per report, never per allocation. `CrossSiteIntelligence`: `executive_summary`, `priority_opportunities`, `cross_site_observations`, `recent_external_developments`, `key_uncertainties`, `investigation_priorities` — every field a plain string/list of strings; **no numeric field anywhere in `CROSS_SITE_SCHEMA`** (asserted directly by test `test_schema_has_no_numeric_field`), so a numerical opportunity/probability score is structurally impossible to express, not merely discouraged.

Zero per-allocation generation calls — Allocation Intelligence (Gate "Phase 1") is read-only, unchanged, never regenerated (confirmed by `test_no_per_allocation_generation_calls_regardless_of_shortlist_size` at 7 allocations).

## Citation contract (Section 19)

Every material claim from web evidence is followed by `[Wn]`. `validate_cross_site_output` rejects any `[Wn]` that does not resolve to a real, retained `WebEvidenceItem` for this exact report (`test_invented_citation_id_is_rejected`).

## Grounding validator (Section 21/22) — `validate_cross_site_output`

A **dedicated** validator for `CrossSiteIntelligence`'s own input shape — never overloads or weakens `allocation_intelligence_summary.validate_summary_output` (its own, still-in-production, single-allocation caller is untouched — zero diff in this gate). Five checks, in order:

1. **Citation grounding** — every `[Wn]` must exist in `web_context.evidence_by_id()`.
2. **Forbidden score/probability shapes** — `NN/100`, `NN% probability/chance/likelihood`, "probability of consent", "opportunity score", "planning potential score" are rejected structurally, regardless of whether `NN` happens to be a real number — the SHAPE itself is prohibited (Section 16/17), not merely an unrounded value.
3. **Numeric grounding** — every remaining number must trace to a Layer 1 trusted fact (aggregates + entry fields) or a number genuinely present in a *retained* web evidence item's own title/summary/relevance_reason/date. Citation ids are masked first so their own digits are never treated as claims. A bare `"0"` is checked too (not just 2+-digit numbers) — Section 12/22K's "unknown capacity must never become zero" (an `unknown`-kind entry's `capacity_value` is `None`, so nothing adds "0" to the allowed set *for that entry*; a genuinely-known zero elsewhere, e.g. `identified_application_capacity=0`, is still correctly allowed). **Known, honestly-documented limitation**: this is global, numeric-only grounding — it cannot distinguish "0% development coverage" (legitimate) from a fabricated "0 homes capacity" claim when both render as the bare token `"0"` in the same report; the test suite proves the *general* "unknown capacity is not converted into a fabricated figure" principle with a clearly-ungrounded non-zero number rather than relying on the ambiguous zero case, and documents why.
4. **Unsupported Developer promotion** — a bare `"Developer: X"` claim for a name not independently trusted as Developer for ANY shortlisted allocation is rejected (matches the task's own BAD example verbatim). A web-sourced association ("X publicly states it is progressing the site [W2]") is a structurally different, allowed sentence shape — never matched by this pattern.
5. **Wrong-allocation evidence attribution** — a bounded heuristic (never general NLP fact-checking, per Section 21's own instruction): for each individual claim string naming exactly one shortlisted allocation by its trusted name, any `[Wn]` it cites must be shortlist-level or bound to that same allocation.

## Party role / capacity / planning-activity semantics (Section 13/17)

- Applicant-only evidence can never be silently narrated as `"Developer: X"` (check 4 above), even across the whole shortlist.
- A trusted Developer for one allocation is accepted; the same name is never assumed Developer for a *different* allocation with no independent evidence.
- A ranged allocation's own `capacity_display` string (both bounds) is a legitimate number source; a genuinely fabricated blended total is rejected by numeric grounding.
- `"No linked planning application has been identified"` is rendered into the prompt with the identical neutral wording Gate 3's own PDF uses (`_render_allocation_line`) — never phrased as an error/warning at the deterministic-input layer. Full end-to-end neutrality of the *model's own prose* is a prompt-level guardrail (Rule 16-equivalent), the same class of "mitigation, not structural guarantee" limitation `allocation_intelligence_summary`'s own V7 amendment already documents for an analogous rule.

## Housing-delivery / NPPF boundary (Section 14/15)

No HDT/5YHLS/NPPF scoring logic exists anywhere in this gate. If such information happens to surface via web research, it is retained only as ordinary, citation-bounded contextual evidence — the forbidden-score-shape check (validator step 2) and the numeric-grounding check (step 3) together catch the overwhelming majority of any attempt to turn it into a fabricated score or ranking; the prompt (Rule 6) explicitly forbids it as well.

## PDF integration (Section 25/26) — `app.reporting.allocation_report_pdf`

`render_allocation_report_pdf(context, *, executive_intelligence=None, web_evidence=None)` — both new parameters are **optional, keyword-only, default `None`**, so every existing Gate 3 call site (`render_allocation_report_pdf(context)`) is byte-for-byte unaffected (proven by the full, unmodified Gate 3 test suite still passing, plus an updated signature test asserting exactly this shape). When `executive_intelligence` is given: an "Executive Intelligence" section (Executive Summary → Priority Opportunities → Recent External Developments → Key Cross-Site Observations → Key Uncertainties → Investigation Priorities, plus the Section 27 evidence note) is inserted right after the cover, before the deterministic Section 1; an "External Web Sources" section (labelled `EXTERNAL WEB RESEARCH`, one entry per citable source — id, publisher, title, date, clickable URL, retrieved date, source tier, confidence) is appended after Excluded Shortlist Items. Every deterministic section in between is **completely unchanged** and still reads only from `context` — `executive_intelligence`/`web_evidence` are never touched by any of the Gate 3 section functions. `allocation_report_pdf_filename(context, *, ai_enhanced=False)` — default unchanged, `ai_enhanced=True` appends `-ai-intelligence` to distinguish the two files.

## Evidence note / disclaimer (Section 27)

One concise line, shown only above the Executive Intelligence section: *"External web research supplements PropertyAIgent's structured planning evidence. Public web information may change and should be verified against primary sources before acquisition or planning decisions are made."* No heavyweight legal boilerplate.

## Streamlit integration (Section 24)

`app/ui/pages/3b_Shortlist.py` gains a fourth action, inside an expander: **"Generate AI Intelligence Report"**. Never triggered on page load/rerun — requires an explicit click. On click: builds `council_domains` from `app.config.load_councils()` for the shortlisted councils, runs `build_allocation_web_research_context` then `generate_cross_site_intelligence` against the SAME `context` object already built once at the top of the page (no second query path), stores the result in one session-state key (`_shortlist_ai_intelligence`, keyed by the current shortlist's allocation-id tuple — deliberately simple, no complex caching architecture, matches the task's own "keep it simple" instruction). A stale result (shortlist changed since generation) is detected and the user is prompted to regenerate, never silently shown against the wrong shortlist. On success: an "AI Intelligence PDF report" download button appears (built from the cached `executive_intelligence`/`web_evidence`, no OpenAI call on that click — pure rendering). On `status == "rejected"` or `"error"`: a neutral warning is shown; **no raw rejection reason or exception string ever reaches the UI**; the deterministic Gate 3 PDF button remains fully, independently available regardless.

## Failure behaviour (Section 35)

| Failure | Outcome |
|---|---|
| Web search API failure (one allocation) | Recorded in `.failures`; research continues for every other allocation/shortlist-level batch |
| Web extraction failure | Recorded in `.failures`; that batch simply contributes no evidence |
| Cross-site synthesis API/network failure | `CrossSiteIntelligenceResult(status="error", intelligence=None)` — never raises |
| Grounding validation rejection | `CrossSiteIntelligenceResult(status="rejected", intelligence=None)` — the AI section is never published; the last-known-good deterministic report is never overwritten by an error |
| Any of the above | The Gate 3 deterministic PDF download button is completely unaffected in every case |

## Persistence decision (Section 36)

**No new database table.** Web research is time-sensitive and shortlists are already session-only (Gate 1) — a report can simply be regenerated. Both `AllocationWebResearchContext` and `CrossSiteIntelligence` are plain, report-run-only dataclasses; `generate_cross_site_intelligence` takes no `Session` at all. No schema change, no migration.

## Query/call-count measurement (Section 28/31–33)

Database queries: `build_allocation_web_research_context`/`generate_cross_site_intelligence` issue **zero** SQL queries themselves (both operate purely on already-built `AllocationReportContext`/`AllocationWebResearchContext` objects) — the only DB cost is Gate 2's own unchanged, flat 9-query `build_allocation_report_context` call.

OpenAI calls for a normal 5-allocation shortlist: `5 × 2` (search + extract per allocation) `+ 1 × 2` (shortlist-level search + extract) `+ 1` (cross-site synthesis) `= 13`. Measured directly in the controlled manual validation below: **12 research calls + 1 synthesis call = 13**, confirming the design figure exactly.

## Tests

- `tests/test_allocation_web_research.py` (15 tests) — query construction determinism, source-tier classification, bounded search/call counts (both the empty-findings case and the full-findings case), allocation association, `MAX_SOURCES_RETAINED_PER_ALLOCATION` enforcement, URL deduplication across allocations, stable sequential evidence ids, dropped-invalid-item handling, dated/undated retention, no-result semantics, search-failure isolation (one allocation's failure never blocks another), extraction-failure handling, total-failure non-raising.
- `tests/test_cross_site_intelligence.py` (21 tests) — exactly-one-synthesis-call, zero-per-allocation-calls, deterministic prompt content, citation acceptance/rejection, wrong-allocation attribution rejection/acceptance, Applicant→Developer-promotion rejection, trusted-Developer acceptance, web-public-association-wording acceptance, range-capacity-fabrication rejection, unknown-capacity-fabrication rejection, genuinely-known-zero acceptance, no-linked-Application neutral rendering, three forbidden-score-shape rejections (bare score, probability-of-consent, housing-delivery score), schema-has-no-numeric-field, generation success/API-failure/rejection orchestration (all non-raising).
- `tests/test_allocation_report_pdf_gate4.py` (11 tests) — deterministic-PDF-unaffected-without-AI, filename behaviour (unchanged default, distinguished `ai_enhanced=True`), Executive Intelligence section content/ordering/citations, External Web Sources section content/ordering, no-web-evidence neutral text (both empty-context and `None` caller states), ampersand/URL-query-string robustness.
- `tests/test_allocation_report_pdf.py` — one existing signature test updated (not weakened) to reflect the deliberate, documented optional-parameter extension; all other 27 Gate 3 tests pass completely unmodified.

All 47 new/updated tests pass. Full targeted suite (Gate 2/3/4 modules + shortlist + ownership/control): see final report. Full suite: see final report, compared name-for-name against the established `OPENAI_API_KEY`-absence baseline.

## Controlled manual validation (Section 37/38)

Performed against real production data (read-only DB access, no writes), a genuinely mixed 5-allocation shortlist (`[1, 3, 136, 196, 68]` — the same set already validated for Gate 3: linked Application present, no linked Application, trusted party evidence, ranged capacity, missing AI Allocation Intelligence), with a real `OPENAI_API_KEY` and real bounded web research (no broad batch research; a single, small, explicitly-scoped run).

| Metric | Result |
|---|---|
| Shortlist size | 5 |
| Searches attempted | 6 (5 per-allocation + 1 shortlist-level) |
| Searches succeeded | 6 (0 failures) |
| Evidence items retained | 17 (13 per-allocation + 4 shortlist-level) |
| OpenAI research calls | 12 (6 search + 6 extraction) |
| OpenAI synthesis calls | 1 |
| **Total OpenAI calls** | **13** |
| Cross-site synthesis result | `status="ok"` — passed grounding validation on the first real attempt |
| Model | `gpt-4o-mini` (matches every other OpenAI call already made across this codebase) |
| Elapsed — context build | 1.2s |
| Elapsed — web research | 110.0s (dominated by real external search latency, not application code) |
| Elapsed — synthesis | 4.9s |
| **Total elapsed** | **116.1s** |
| Token usage / cost | Not captured in this run's instrumentation (an honest gap, not a fabricated figure — `response.usage` was available on the API responses but not read out by the validation script) |

Qualitative review of the real output: source tiers classified correctly (three genuine `.gov.uk` council pages → `official_primary`; press/blog sources → `contextual`, matching the deliberately conservative allow-list); citations `[W9]`/`[W10]` resolved correctly to their real sources; the executive summary and priority opportunities genuinely compared allocations against each other rather than repeating each in turn; no numerical score, probability, or housing-delivery figure appeared anywhere; the "Wharfside" allocation's real web evidence (a Manchester United stadium redevelopment announcement) was correctly retained as directly relevant context — Wharfside is the real Trafford regeneration site adjacent to Old Trafford, a genuine, valuable real-world signal Gate 2/3's deterministic data alone could never have surfaced. The generated PDF opened correctly, with the Executive Intelligence section appearing before the deterministic sections and External Web Sources appearing after them, exactly as designed.

## Known limitations

- Source-tier allow-list is not exhaustive (documented above).
- Numeric-only grounding cannot distinguish two different, coincidentally-equal legitimate numbers from a genuinely fabricated one bearing the same digits (documented above, same class as the existing single-allocation validator's own known limitations).
- No-linked-Application/party-role neutrality in the model's own free prose is a prompt-level guardrail, reinforced but not perfectly guaranteed by the validator's pattern-based checks (same "mitigation, not structural guarantee" class as `allocation_intelligence_summary`'s own documented V7 amendment).
- Wrong-allocation citation attribution is caught only for a claim naming exactly one shortlisted allocation by name — a claim naming zero or several allocations is not checked by that heuristic (deliberately, to avoid an unreliable broader check).
- Token usage/cost was not captured in the one controlled validation run performed for this gate.

## Deferred (Gate 5+/other workstreams)

Planning Potential, NPPF policy scoring, probability-of-consent, Local Plan Delivery Intelligence, HDT/5YHLS ingestion, Buyer Profiles, opportunity/investment scoring, comparables, land values, residual valuation, database-persisted AI shortlist reports, automated report emailing, background report jobs — none touched, none proposed.
