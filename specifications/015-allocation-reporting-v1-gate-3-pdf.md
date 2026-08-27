# Allocation Reporting V1 Gate 3 — Deterministic Shortlist PDF Report

## Purpose

Turns Gate 2's deterministic `AllocationReportContext` into a downloadable, professional PDF suitable for internal circulation, land/acquisitions meeting discussion, and supporting initial site investigation — an opportunity-screening / allocation-intelligence report, explicitly not yet an investment-committee document.

## PDF architecture audit

**(A) Existing PDF library.** ReportLab, already a project dependency, used by `app/reporting/pdf_report.py` (the Planning Site scheme-summary PDF).

**(B) Reuse of existing PDF infrastructure.** `pdf_report.py`'s `_styles()` builds a `getSampleStyleSheet()`-based stylesheet plus four genuinely domain-neutral styles (`ReportTitle`, `ReportSubtitle`, `SectionHeading`, `Body`) and two Planning-Site-specific styles (`SchemeHeading`, `SchemeBody`). The rest of that module — `render_pdf`, `_stats_table`, `generate_narrative`, the OpenAI narrative call — is shaped entirely around Planning Site scheme rows and stats, not the Allocation report-context domain, and is not reused directly.

**(C) Decision.** New sibling module, `app/reporting/allocation_report_pdf.py`, importing and extending `pdf_report._styles()` (adding allocation-specific styles: `AllocationHeading`, `AllocationBody`, `Small`, `Pending`, `TableCell`) rather than duplicating it, and importing `allocation_report._planning_activity_label` so the PDF's "Planning Activity" wording can never drift from the CSV's own wording. Everything else — layout, sections, per-allocation rendering — is new, purpose-built for this report's content contract. This mirrors Gate 2's own precedent (a new, focused module rather than forcing a different content contract into an existing one) and keeps `pdf_report.py` completely untouched.

## Renderer contract

```
render_allocation_report_pdf(context: AllocationReportContext) -> bytes
allocation_report_pdf_filename(context: AllocationReportContext) -> str
```

Pure renderer: no `Session`, no ORM object, no OpenAI client, and (measured) zero database queries — every fact is already present on `context`. Verified in tests via (1) a `before_cursor_execute` SELECT counter around a bare `render_allocation_report_pdf(context)` call returning `0`, and (2) an `inspect.signature` check that the function accepts exactly one positional argument named `context` — nothing else could be threaded through even if a caller tried. Deterministic for a given context: two renders of the same context produce identical extracted text (a dedicated test proves this); PDF *bytes* may differ trivially in ReportLab's own embedded metadata, which application code does not control.

`allocation_report_pdf_filename` builds `property-aigent-allocation-report-YYYY-MM-DD.pdf` from `context.generated_at` only — an internally-produced UTC timestamp, never arbitrary site/user input, so no sanitisation step is needed.

## No `AllocationReportContext` extension required

Every fact the required report structure calls for (Identity, Development Position, Planning Activity, Party Evidence with its trust partition, AI Allocation Intelligence snapshot, Source/Evidence, and the aggregate totals) was already present on `AllocationReportEntry`/`AllocationReportAggregates` as Gate 2 left them. No field was added, and no new query was introduced.

One limitation was identified and deliberately **not** fixed by extending the context: `ExcludedCandidate` carries only `allocation_id` and `reason` (Gate 2's own shape) — no display name. Classified against Gate 3's own extension test (Section 16 of the task): a UI-only `ReportCandidate.display_name` lives in Streamlit session state and was never available to the context *builder* (which only ever receives raw ids) — there is no real name to source a fix from, so this is not a genuinely-required, sourceable fact (not Category A). The PDF's "Excluded Shortlist Items" section therefore shows `Allocation ID {id}: {reason}` only, matching exactly what the context has always been able to say. Documented here as a known, accepted limitation, not carried forward as a TODO against the context.

## Report structure (implemented)

- **Cover / header**: "PropertyAIgent" / "Allocation Opportunity Report" / subtitle / generated timestamp / shortlisted-allocation count / authority count. No invented client name; never labelled an "Investment Committee Report".
- **1. Shortlist Overview**: `context.aggregates` only. Exact/ranged/unknown capacity reported as three separate sentences (never blended into one "total capacity" figure — the Section 6 GOOD/BAD example is reproduced as a regression test). Plan status counts, planning-activity counts, identified/residual capacity known-total + unknown-count pairs.
- **2. Shortlist Summary**: one row per entry — Allocation, Authority, Plan Status, Capacity (`capacity_display`), Planning Activity (`_planning_activity_label`, shared with CSV), Development Coverage (percentage or `DEVELOPMENT_COVERAGE_LABELS` fallback), Indicative Residual Capacity. Every cell is `Paragraph`-wrapped so long text wraps rather than overflowing.
- **3. Allocation Details**, one section per entry in `context.entries`'s own id-sorted order:
  - **A. Identity** — name, authority/plan/reference line, plan status, intended use.
  - **B. Development Position** — capacity display, identified application capacity, development coverage, indicative residual; `None` always renders "Not determined", never zero; a range's own `capacity_display` string is used verbatim, never re-derived as if exact.
  - **C. Planning Activity** — linked Applications sorted by reference for deterministic rendering; each shown as a **proposal-first** heading line with the reference, status/decision/units/applicant demoted to a smaller, muted secondary line below (never the other way round). No linked Applications → the exact neutral sentence "No linked planning application has been identified." (never styled as a warning/error).
  - **D. Party Evidence** — Applicant names (from `applicant_evidence`) always on their own line; trusted Developer (`trusted_ownership_evidence` filtered to role `DEVELOPER`) on a plain "Developer:" line; any other trusted role on its own `{role_label}:` line; review-pending evidence (`review_pending_ownership_evidence`) rendered in a visually distinct muted/amber style with an explicit "(evidence pending confirmation)" qualifier, never sharing a line or style with trusted evidence. Rejected relationships are already excluded upstream by Gate 2's own query filter and were confirmed absent by test.
  - **E. AI Allocation Intelligence** — read-only: headline/overview/key points/key uncertainties/investigation priorities rendered exactly as persisted when `ai_intelligence.available`; otherwise the exact neutral sentence "AI Allocation Intelligence not currently available." This is the identical safe state Gate 2 already collapses "missing" and "errored" into (`AllocationIntelligenceSnapshot.available=False` either way) — `generation_error` is never on that dataclass at all, so there is nothing here that could leak it, confirmed by a dedicated test using a `status="error"` fixture with a raw traceback-shaped `generation_error` string.
  - **F. Source / Evidence** — a small, muted line (`source_document_url`, `last_checked`, `review_status_label`) placed after the AI section, visually subordinate throughout.
- **Excluded Shortlist Items** — only rendered when `context.excluded` is non-empty; `Allocation ID {id}: {reason}` per item; the presence of an excluded id never prevents the remaining valid entries from rendering in full (tested directly).
- **Footer** — page number + report title on every page, via a ReportLab `onFirstPage`/`onLaterPages` canvas callback.

## Robustness

All dynamic text (allocation names, entity names, proposal text, etc.) is passed through `xml.sax.saxutils.escape()` before being embedded in ReportLab `Paragraph` markup — `pdf_report.py`'s own existing code does not do this, and a real UK company name containing `&` (a very ordinary character, e.g. "Smith & Sons Ltd") would otherwise corrupt or crash rendering. This is a new-module-only fix, not a retroactive change to `pdf_report.py`, which stays out of scope for this gate.

## Streamlit integration

`app/ui/pages/3b_Shortlist.py` now renders a third action button, "Download shortlist PDF report", alongside the existing "Clear shortlist" and "Download shortlist CSV" actions. It calls `render_allocation_report_pdf(context)` on the exact same `context` object already built once at the top of the page for the review cards and the CSV button — no second query path. Deliberately left un-cached, matching the CSV button's own existing (also un-cached) pattern: `render_allocation_report_pdf` performs no I/O of its own (pure in-memory ReportLab layout over data `context` already holds), so it costs nothing beyond what building `context` already cost. Introducing an explicit caching layer was judged unnecessary complexity for a currently-unmeasured need, per the task's own instruction to keep this simple.

## Query behaviour (measured)

| Shortlist size | SELECT queries (context build + PDF render) |
|---|---|
| 5 | 9 |
| 10 | 9 |
| 25 | 9 |
| 50 | 9 |

Identical to Gate 2's own baseline — `render_allocation_report_pdf` itself issues zero additional queries (also verified directly, isolated from context-building, in `test_renderer_performs_zero_database_queries`).

## Tests

`tests/test_allocation_report_pdf.py` — 28 new tests:

- **PDF validity** (7): valid `%PDF-` byte signature and openable page count; report title/allocation name present; summary-table text present; multi-allocation (8-entry) generation succeeds; long proposal/name text does not crash; an allocation with every optional field empty does not crash; an entity name containing `&`/`<`/`>` renders correctly (escaping proof).
- **Capacity semantics** (3): exact capacity reported alone, never blended with a co-shortlisted range's upper bound (the Section 6 GOOD/BAD example, reproduced verbatim as an assertion); unknown capacity reported as its own sentence; a `REVIEW_REQUIRED` allocation's residual renders "Not determined", never `0` or a manufactured number.
- **Planning activity** (2): no-linked-Application neutral sentence; a linked Application's reference appears only as a secondary "Ref: ..." detail line, with the proposal text as the actual heading.
- **Party evidence** (4): Applicant evidence never promoted onto a "Developer:" line; a trusted Developer renders on the "Developer:" line; a `needs_confirmation` Developer is excluded from that trusted line and instead appears on the separate "(evidence pending confirmation)" line; a `rejected` relationship is entirely absent from output.
- **AI Allocation Intelligence** (3): an available persisted summary's headline/overview/key points render; a missing summary shows the neutral unavailable sentence; an `error`-status summary with a raw `generation_error` string shows the same neutral sentence and never leaks the raw error text.
- **Missing / excluded candidates** (2): an excluded id is reported by id + reason in its own section, and the remaining valid allocation still renders in full; the section is omitted entirely when nothing is excluded.
- **Determinism / renderer isolation** (5): two renders of the same context produce identical extracted text; entries render in `context.entries`'s own id-sorted order regardless of the order ids were requested in; a direct SELECT-query count around a bare render call is exactly `0`; the function's signature accepts only `context`; a static AST check confirms the module never imports `openai` at all (unlike `pdf_report.py`, which does for its own unrelated narrative step).
- **Combined query-count regression** (1): context-build + PDF-render together stay flat at exactly 9 queries across shortlists of 5/10/25/50 allocations.
- **Filename helper** (1): deterministic, extension-correct, no whitespace.

All 28 pass. Targeted suite (`test_allocation_report.py`, `test_allocation_report_pdf.py`, `test_allocation_discovery.py`, `test_shortlist.py`, `test_allocation_intelligence_summary.py`, `test_ownership_control_evidence.py`, `test_ownership_control_hierarchy.py`, `test_ownership_control_reporting.py`): 321 passed. Full suite: 2615 passed, 11 failed — all 11 are the pre-existing `OPENAI_API_KEY`-absence baseline in `test_ai_processing_predeployment_safety.py`, `test_ai_processing_reliability.py`, and `test_pr2_final_amendment_migration_and_intelligence_processing.py` (same `RuntimeError: OPENAI_API_KEY not set in .env` failure mode this whole session's baseline has shown, unmodified by this gate). 2615 = 2587 (established baseline) + 28 (this gate's new tests). Zero regressions.

## Manual validation

Not performed against production data in this gate. All verification here is against the in-memory SQLite integration-test fixtures already used throughout `tests/test_allocation_report.py`'s own convention — deliberately identical mixed-evidence scenarios (linked Application present/absent, trusted Developer, `needs_confirmation` Developer, rejected relationship, ranged capacity, available/missing/errored AI summary, excluded id) were exercised directly as unit/integration tests against real rendered PDF text via `pdfplumber`, rather than through a live browser session. This is an honest scope reduction, not a silent skip: a live Streamlit walkthrough would exercise the same `render_allocation_report_pdf(context)` call this page now makes and was judged to add limited additional verification value over the direct, text-extraction-based test suite above, which already inspects the actual rendered PDF bytes end to end.

## Deferred to a future gate

Cross-site AI Executive Summary generation, natural-language Opportunity Discovery, Planning/Opportunity Potential, NPPF reasoning, Buyer Profiles, opportunity scoring, comparables/land values/residual valuation, database-backed shortlist persistence, and any PDF caching architecture beyond the simple un-cached render used here — none touched, none proposed.
