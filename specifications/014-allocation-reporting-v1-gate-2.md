# Allocation Reporting V1 Gate 2 — Deterministic Context + CSV + Batched Party Evidence

## Purpose

Makes the shortlist commercially useful: a stable, deterministic report context every later output (shortlist review today, CSV today, PDF/cross-site AI synthesis in Gate 3/4) reads from, rather than each output rebuilding its own view of the shortlisted allocations.

## Report-context contract

`app/reporting/allocation_report.py` — a new, focused module (not an extension of `pdf_report.py`, whose Planning Site report domain has a materially different content contract). `build_allocation_report_context(session, allocation_ids) -> AllocationReportContext`:

- `entries: list[AllocationReportEntry]` — one per available shortlisted allocation, id-sorted (deterministic order).
- `excluded: list[ExcludedCandidate]` — ids that no longer resolve to a real allocation, each with a reason; never a crash, never silently dropped.
- `aggregates: AllocationReportAggregates` — shortlist-wide totals (see below).
- `generated_at` — when the context was built.

No ORM objects and no session-state snapshots are stored in the context — every field is a plain value or a frozen dataclass of plain values, built fresh from current trusted data on every call.

`AllocationReportEntry` covers Identity, Development Position, Planning Activity (linked Applications), Party Evidence (Applicant + ownership/control, kept as two separate lists), Trust/Review state, AI Allocation Intelligence (read-only snapshot), and Source/Evidence — matching the task's own per-allocation content contract exactly.

## Architecture decision: relation to `build_allocation_discovery`

Deliberately **not** reused. `build_allocation_discovery` has no `allocation_ids` filter — every call computes over the entire platform (287+ allocations and growing), so a report over a 5-allocation shortlist would cost the same as one over the whole platform, and its UI-card output carries fields (`why_it_matters`, visual evidence, badge kinds) this report domain doesn't need. Instead, this module composes the same **lower-level batched building blocks** `build_allocation_discovery` is itself built from:

- `app.reporting.allocation_development_coverage.build_allocation_development_coverage` — already accepts a list of allocations and returns coverage/site_summaries for all of them in one fixed, small query budget. Reused unchanged.
- Two **new batched siblings**, added by this gate:
  - `app.reporting.allocation_intelligence_summary.get_allocation_summaries(session, allocation_ids)` — one `WHERE allocation_id IN (...)` query, replacing what would otherwise be one `get_allocation_summary` call per allocation.
  - `app.reporting.ownership_control.get_allocations_control_intelligence(session, site_ids)` — one `WHERE site_id IN (...)` query across every related Site in the whole shortlist, replacing what would otherwise be one `get_site_control_intelligence` call per related Site. Neither existing single-allocation/single-Site function was modified or replaced — both remain exactly as Gate 1 left them, still used unchanged by the Allocation Detail page.

Result: a report's query cost depends on shortlist size, never platform size — **measured at a flat 9 SELECT queries for shortlists of 5, 10, 25, and 50 allocations** (see "Query behaviour" below).

## Party semantics

Two separate lists, never conflated:

- `applicant_evidence: list[ApplicantEvidenceEntry]` — Multi-Application Party Intelligence, sourced from `Application.applicant_name_raw` (a portal scrape), aggregated across **every** trusted linked Application on a Site, never only the representative one. Role is always "Applicant" — never promoted to Developer/Owner/Promoter regardless of how many Applications name the same entity. Reuses the existing `_clean_portal_value` placeholder-cleaner (imported from `allocation_intelligence_summary.py`) so this report can never disagree with the AI Allocation Intelligence layer about what counts as real applicant evidence. Exact cleaned-name dedup only — no fuzzy company-name resolution, matching the existing, deliberately-accepted V1 limitation.
- `ownership_evidence: list[OwnershipEvidenceEntry]` — a reshape of `ControlRelationshipGroup` (unchanged role/role_label vocabulary: Certificate A declarations stay "Planning ownership declaration", S106-defined roles stay labelled exactly as evidenced). `needs_confirmation` rows are retained with `needs_review=True`; `rejected` rows are excluded entirely by the underlying batched query (same filter as every existing ownership_control query).

## Linked Application structure

`LinkedApplicationEntry` per Application: reference, proposal, status, decision (placeholder-cleaned), decision date, unit count (reconciled `SchemeIntelligence.total_units_final` preferred, `estimated_unit_count` fallback flagged `unit_count_is_estimate`), application category, applicant, site label, the Site relationship's own review status, portal URL, and whether it's the Site's representative Application. Deterministic supporting evidence only — never part of an AI narrative, never surfaced with individual reference numbers in the review page's own headline text.

## Capacity handling

Reuses `format_capacity` (the platform's existing, single, unchanged capacity-selection rule) directly — never reimplemented. A range's `capacity_value` is its own already-accepted upper bound (e.g. "8,400–15,000 homes" → `15000`), the same convention already used elsewhere on this platform (Allocation Discovery's own KPI totals); the full range string is preserved separately as `capacity_display`. `capacity_value` is `None` only for genuinely unknown capacity. Aggregates never silently collapse a range or manufacture a number from an unknown value — see aggregates below.

## Aggregate statistics

`AllocationReportAggregates` sums only entries with a **known** value, and separately counts how many were excluded from that sum (`capacity_known_total` + `capacity_unknown_count`, and the equivalent pair for identified/residual capacity) — never a total presented as complete when some inputs were unknown or review-required. Plus: allocation count, adopted/emerging/other plan-status counts, and allocations with vs. without linked activity.

## CSV contract

`to_csv_rows`/`to_csv_bytes` — deliberately separate from the fact model (`AllocationReportEntry` itself knows nothing about CSV formatting, so a future PDF renderer or AI-prompt builder reads the exact same context untouched). Columns: Authority, Local Plan, Allocation Reference, Allocation Name, Plan Status, Intended Use, Allocation Capacity, Planning Activity, Identified Application Capacity, Indicative Residual Capacity, Development Coverage %, Linked Application Count, Known Applicant(s), Known Developer(s), Ownership / Control Evidence, AI Intelligence Headline, AI Summary Available. Multi-value fields use `"; "` as a delimiter with the role bracketed per entity (e.g. `Entity A [Applicant]; Entity B [Applicant]`) — role distinctions are never collapsed, and Applicant values never appear in the Developer column or vice versa. UTF-8 with a BOM (`utf-8-sig`) so Excel opens non-ASCII characters correctly. Zero OpenAI calls.

## Query behaviour (measured)

| Shortlist size | SELECT queries |
|---|---|
| 5 | 9 |
| 10 | 9 |
| 25 | 9 |
| 50 | 9 |

Flat regardless of size — confirms no N+1 pattern in the party-evidence or AI-summary paths. The fixed 9 queries: `LocalPlanSite`+`LocalPlan` (1), `build_allocation_development_coverage`'s own batch (AllocationSiteRelationship+Site, Applications ×2, Documents — 4), `get_allocation_summaries` (1), `get_allocations_control_intelligence` (1), plus `ControlRelationship`'s own `selectinload` for Application/Document (2, folded into the same query plan). Not independently re-measured against production for this gate (no production allocations currently carry rich enough ownership/party fixtures to exercise every code path meaningfully) — MEASURED against the same in-memory SQLite test database this whole test suite already uses, which reflects the real query plan SQLAlchemy issues regardless of backend.

## Tests

53 new tests: `tests/test_allocation_report.py` (35 — identity, capacity exact/range/unknown, development coverage, no-linked-Application, linked Application detail, multi-Application applicant evidence, Applicant-vs-Developer role discipline, Certificate A wording, needs_confirmation/rejected trust boundaries, missing allocation, missing/errored/available AI summary, duplicate ids, empty shortlist, aggregates, 10 CSV tests including Unicode/zero-OpenAI/deterministic-order, and 2 bounded-query-count tests proving flat scaling from 5→25→50 allocations).

## Shortlist page enrichment

`app/ui/pages/3b_Shortlist.py` now consumes `AllocationReportContext` directly (replacing Gate 1's `build_allocation_discovery` + per-card `get_allocation_summary` reuse) and shows concise party-evidence signal (Applicant names, Developer names, and a count of other ownership/control evidence) — never the full evidence detail, which remains on Allocation Detail. A "Download shortlist CSV" button is added alongside the existing "Clear shortlist" action.

## Gate 3/4 deferred scope

PDF rendering, the one-time grounded cross-site AI Executive Summary, natural-language Opportunity Discovery, Housing Delivery filtering, Planning Potential, Opportunity Potential, NPPF reasoning, Buyer Profiles, opportunity scoring, database-backed shortlist persistence — none touched, none proposed. `AllocationReportContext`'s API (`build_allocation_report_context(session, allocation_ids)` → context → `to_csv_bytes(context)`) is designed so Gate 3's `render_pdf(context)` and Gate 4's `generate_cross_site_summary(context)` can consume it unchanged.
