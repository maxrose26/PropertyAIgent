# Allocation Shortlist V1 - Gate 1: Shortlist Foundation + Selection UX

## Purpose

First implementation slice of Site Selection, Shortlist & Allocation Reporting V1 (approved design, `docs/PLATFORM_ARCHITECTURE.md` §2 "Opportunity Intelligence"). Lets a user filter Allocation Discovery, add allocations to a session-only shortlist, keep browsing without losing it, and review the shortlisted allocations together. Reporting (CSV/PDF/AI Executive Summary) is explicitly out of scope - see "Deferred" below.

## Approved scope for this gate

Shortlist foundation, Allocation Discovery selection UX, shortlist review surface. Nothing else - no CSV, no PDF, no report-context builder, no cross-site AI synthesis, no OpenAI calls, no database-backed persistence, no Planning Discovery migration, no natural-language search, no housing-delivery filtering, no Planning/Opportunity Potential, no NPPF reasoning, no Buyer Profiles.

## Session-state architecture

Shortlist state lives only in `st.session_state["_shortlist"]` (`SHORTLIST_SESSION_KEY`, `app/ui/shortlist.py`) - a plain `dict[(candidate_type, candidate_id), ReportCandidate]`. No database table, no migration. It survives filter changes, pagination, and navigation between pages within one Streamlit session (Streamlit's own `session_state` guarantee) - it does not survive a browser/session termination, a different device, or a different authenticated session, by design (a later capability, not this gate).

## ReportCandidate contract

```python
@dataclass(frozen=True)
class ReportCandidate:
    candidate_type: str   # "allocation" for this gate; "planning_site" reserved for later
    candidate_id: int
    display_name: str
```

Identity only - never a snapshot of planning data. Current trusted data is always reloaded from the database (via `build_allocation_discovery`) when the shortlist review page renders; `display_name` exists only so the shortlist can show something before that reload, and is never treated as authoritative.

Duplicate prevention is structural: the dict key is `(candidate_type, candidate_id)`, so adding the same candidate twice overwrites rather than duplicates, and the same numeric id under two different `candidate_type`s can never collide.

API (`app/ui/shortlist.py` - pure, no Streamlit runtime dependency, mirrors `app/ui/allocation_selector.py`'s existing pattern): `add_candidate`, `remove_candidate`, `clear_shortlist`, `is_shortlisted`, `shortlist_items`, `shortlist_count`. Every function takes a state dict and returns a new one - never mutates in place.

## UI interaction

**Allocation Discovery gallery** (`app/ui/pages/3_Local_Plan_Sites.py`) - `app.ui.shell.allocation_card` gained an `in_shortlist: bool` parameter and now returns whether its shortlist button was clicked this render; the page script (not the presentation-only `shell.py` module) owns the actual add/remove decision and session-state mutation, preserving `allocation_card`'s existing pure-render contract.

**Allocation detail view** (`_render_detail` in the same file) - an identical toggle button, added directly (the detail view isn't built from `allocation_card`), using the same `app.ui.shortlist` helpers.

**Discoverability** - a "N allocations shortlisted →" `st.page_link`, shown on both Local Plan Sites and Explore only when the count is non-zero, matching the existing "N suggested site links awaiting review →" / "N Local Plan allocated sites with no application yet →" badge pattern already on Explore. Explore's own existing multi-row Planning Discovery selection is untouched.

## Shortlist review page

`app/ui/pages/3b_Shortlist.py`, registered `visibility="hidden"` in `app/ui/streamlit_app.py`'s navigation (same pattern as Site Profile / Council Intelligence Detail - reached via the badge link, not a persistent top-level tab). Reuses `build_allocation_discovery(session)`'s already-batched card list, filtered to the shortlisted ids - no new query architecture built solely for this page. Shows, per shortlisted allocation: name, authority, Local Plan, plan status, review status, intended use, capacity, development coverage %, indicative residual capacity, the existing evidence-bounded matched/linked-application caption, and the AI Allocation Intelligence headline where one is already persisted (`get_allocation_summary`, read-only, never regenerates).

**Deliberately omitted**: known Applicant/Developer party signal. Surfacing it correctly needs `get_allocation_control_intelligence`, which today queries per related Site and is only ever called per-allocation - looping it across a shortlist here would be exactly the new batched-query architecture the approved design scoped into a later gate. Omitted per the gate's own instruction to omit rather than expand scope.

Party-evidence and no-linked-Application wording, where shown at all, follows the existing discipline unchanged (Applicant ≠ Developer ≠ Owner ≠ Promoter; "no linked planning application" rendered as a neutral fact via the existing `matched_summary`/`matched_summary_help` text, never as an error).

**Stale/missing candidate**: if a shortlisted allocation id isn't found in the current `build_allocation_discovery` cards, the review page shows it as unavailable with a "Remove from shortlist" action - never a crash, never a silent auto-removal.

**Empty state**: the existing `empty_state` component, pointed back at Allocation Discovery.

## Tests

`tests/test_shortlist.py` - 20 tests covering the full pure `app/ui/shortlist.py` API: add, duplicate add (no duplicate), remove (including no-op on a missing key), clear, `is_shortlisted`, `shortlist_items` (unfiltered and filtered), `shortlist_count`, mixed candidate types coexisting without collision, same numeric id under different `candidate_type`s not colliding, display-name retention, and `ReportCandidate` being a frozen, value-equal dataclass. No mutation-in-place is verified explicitly (add/remove both leave their input dict untouched).

Page-level behaviour (shortlist surviving a rerun/pagination/navigation; the review page showing only shortlisted allocations; a stale candidate rendering gracefully) is not covered by an automated UI test - this codebase has no `streamlit.testing.v1.AppTest` (or equivalent) harness for page scripts, and building one is out of this gate's scope. That behaviour follows from Streamlit's own documented `session_state` persistence guarantee plus the page code's `dict.get()`-based lookup, verified by code review rather than a new test harness.

## Deferred (Gate 2+)

CSV export, PDF export, `app/reporting/allocation_report.py` (report-context builder), the batched ownership/control entrypoint, the cross-site AI Executive Summary, database-backed/persistent shortlists, collaborative shortlists, migrating Explore's existing selection onto this abstraction, comparison views, natural-language Opportunity Discovery, Planning Potential, Opportunity Potential, Buyer Profiles, NPPF reasoning, any housing-delivery filtering.
