"""Shortlist review + CSV/PDF export (Site Selection & Reporting V1 Gates 2-3)
- shows the allocations added to the session-only shortlist (app.ui.shortlist)
together, so a user can review them as a group and export a deterministic
opportunity dataset.

Deliberately NOT a full report or an analytics dashboard: no new scoring,
ranking, or charts - concise party-evidence signal only (Applicant/Developer/
a count of other ownership evidence), with full per-allocation detail
remaining one click away on Allocation Detail, exactly as Gate 1 already
established.

Data reuse (Gate 2/3): consumes app.reporting.allocation_report.
build_allocation_report_context - the SAME deterministic report context both
the CSV export and the Gate 3 PDF report (app.reporting.allocation_report_pdf.
render_allocation_report_pdf) read from - rather than a separate query path
per surface (see that module's own docstring). Replaces Gate 1's
build_allocation_discovery + per-card get_allocation_summary reuse now that
the batched, purpose-built report-context builder exists; party/ownership
evidence (omitted in Gate 1 because the underlying batching didn't exist yet)
is now shown, backed by app.reporting.ownership_control.
get_allocations_control_intelligence's batched entrypoint - a single query
across every shortlisted allocation's related Sites, never one query per
allocation. The PDF renderer itself performs zero additional queries -
context is built exactly once above and drives review, CSV, and PDF alike.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st

from app.reporting.allocation_discovery import ALLOCATION_REVIEW_STATUS_META, PLAN_STATUS_META
from app.reporting.allocation_report import build_allocation_report_context, to_csv_bytes
from app.reporting.allocation_report_pdf import allocation_report_pdf_filename, render_allocation_report_pdf
from app.ui.common import bootstrap, credits_sidebar, get_db
from app.ui.shell import empty_state, page_header, stat_tile, status_badge_row, wide_canvas
from app.ui.shortlist import SHORTLIST_SESSION_KEY, clear_shortlist, remove_candidate, shortlist_items

bootstrap()
session, settings = get_db()

credits_sidebar(session, settings)
wide_canvas()

LOCAL_PLAN_PAGE = Path(__file__).resolve().parent / "3_Local_Plan_Sites.py"
st.page_link(LOCAL_PLAN_PAGE, label="← Back to Allocation Discovery", icon="🔙")

page_header(
    "Shortlist",
    "Allocations you've added to your shortlist this session, together in one place.",
    icon="⭐",
)

st.session_state.setdefault(SHORTLIST_SESSION_KEY, {})
candidates = shortlist_items(st.session_state[SHORTLIST_SESSION_KEY], "allocation")
# Deterministic display order (allocation_selector.py precedent: never rely
# on dict-insertion order as if it were meaningful) - alphabetical by the
# display_name captured at add-time, id as the final tie-breaker.
candidates = sorted(candidates, key=lambda c: (c.display_name.lower(), c.candidate_id))

if not candidates:
    empty_state(
        "No allocations shortlisted yet",
        "Add opportunities from Allocation Discovery - open Local Plan Sites, filter to a population you're "
        "interested in, and use \"Add to shortlist\" on any allocation card or its detail page.",
        icon="⭐", cta_label="Browse Allocation Discovery", cta_page="pages/3_Local_Plan_Sites.py",
    )
    st.stop()

st.caption(f"{len(candidates)} allocation{'s' if len(candidates) != 1 else ''} shortlisted.")

# Site Selection & Reporting V1 Gate 2 - ONE deterministic report context,
# built fresh from current trusted data, powers both this review surface
# and the CSV export below - never a separate query path per consumer (see
# app.reporting.allocation_report's own module docstring).
context = build_allocation_report_context(session, [c.candidate_id for c in candidates])
entries_by_id = {entry.allocation_id: entry for entry in context.entries}

action_col1, action_col2, action_col3 = st.columns(3)
with action_col1:
    if st.button("Clear shortlist", key="shortlist-clear-all"):
        st.session_state[SHORTLIST_SESSION_KEY] = clear_shortlist(st.session_state[SHORTLIST_SESSION_KEY])
        st.rerun()
with action_col2:
    # Gate 2 CSV UX (Section 23) - a clear, deterministic export action; the
    # user downloads exactly the currently shortlisted allocation set, no
    # more, no less (context.entries is built from these exact candidate
    # ids).
    st.download_button(
        f"Download shortlist CSV ({len(context.entries)} allocation{'s' if len(context.entries) != 1 else ''})",
        data=to_csv_bytes(context), file_name="allocation_shortlist.csv", mime="text/csv",
        key="shortlist-download-csv", use_container_width=True,
    )
with action_col3:
    # Gate 3 PDF report - rendered from the SAME `context` object already
    # built above for this page and the CSV export, never a second query
    # path (app.reporting.allocation_report_pdf's own module docstring: a
    # pure renderer, zero database queries). Deliberately un-cached, same
    # as the CSV button above - render_allocation_report_pdf performs no
    # I/O of its own (pure in-memory ReportLab layout over already-fetched
    # data), so it costs nothing extra beyond what building `context`
    # already cost; adding a caching layer here would be complexity this
    # gate has no measured need for.
    st.download_button(
        "Download shortlist PDF report",
        data=render_allocation_report_pdf(context), file_name=allocation_report_pdf_filename(context),
        mime="application/pdf", key="shortlist-download-pdf", use_container_width=True,
    )

st.divider()

for candidate in candidates:
    entry = entries_by_id.get(candidate.candidate_id)

    if entry is None:
        # Stale/missing candidate (Gate 1 Section 10, unchanged) - never
        # crash, never silently drop it from the shortlist on our own
        # initiative; show it as unavailable and let the user remove it
        # explicitly. Driven by context.excluded now rather than a missing
        # build_allocation_discovery card, same user-facing behaviour.
        with st.container(border=True, key=f"shortlist-missing-{candidate.candidate_id}"):
            st.markdown(f"**{candidate.display_name}**")
            st.caption("This allocation is no longer available - it may have been removed or reclassified.")
            if st.button("Remove from shortlist", key=f"shortlist-remove-missing-{candidate.candidate_id}"):
                st.session_state[SHORTLIST_SESSION_KEY] = remove_candidate(
                    st.session_state[SHORTLIST_SESSION_KEY], "allocation", candidate.candidate_id,
                )
                st.rerun()
        continue

    with st.container(border=True, key=f"shortlist-card-{entry.allocation_id}"):
        header_cols = st.columns([5, 1])
        with header_cols[0]:
            st.markdown(f"##### {entry.allocation_name}")
            context_bits = [b for b in (entry.council_name, entry.local_plan_name, entry.allocation_reference) if b]
            st.caption(" · ".join(str(b) for b in context_bits))
        with header_cols[1]:
            if st.button("Remove", key=f"shortlist-remove-{entry.allocation_id}", use_container_width=True):
                st.session_state[SHORTLIST_SESSION_KEY] = remove_candidate(
                    st.session_state[SHORTLIST_SESSION_KEY], "allocation", entry.allocation_id,
                )
                st.rerun()

        status_badge_row([
            (PLAN_STATUS_META.get(entry.plan_status, PLAN_STATUS_META[None])["chip_kind"], entry.plan_status_label),
            (ALLOCATION_REVIEW_STATUS_META.get(entry.review_status, ALLOCATION_REVIEW_STATUS_META[None])["badge_kind"], entry.review_status_label),
        ])

        info_cols = st.columns(4)
        with info_cols[0]:
            stat_tile("Intended use", entry.intended_use_label)
        with info_cols[1]:
            stat_tile("Capacity", entry.capacity_display)
        with info_cols[2]:
            stat_tile(
                "Development coverage",
                f"{entry.development_coverage_percentage:.0%}" if entry.development_coverage_percentage is not None else "Not determined",
            )
        with info_cols[3]:
            stat_tile(
                "Indicative residual",
                f"~{entry.indicative_residual_capacity:,}" if entry.indicative_residual_capacity else "Not determined",
            )

        # Evidence-bounded wording (Gate 1 Section 14, unchanged) - no
        # warning/error styling solely because no application is linked;
        # no linked Application is a valid intelligence state.
        if entry.linked_application_count:
            st.caption(f"{entry.linked_application_count} linked planning application(s) identified.")
        else:
            st.caption("No linked planning application has been identified.")

        # Gate 2 - concise party-evidence signal only (Section 18: "keep
        # the page concise... full detail remains in Allocation Detail").
        # Applicant and Developer are always shown as separate, never
        # conflated - Applicant-only evidence is never promoted to
        # Developer (Section 10).
        applicant_names = sorted({e.entity_name for e in entry.applicant_evidence})
        if applicant_names:
            st.caption(f"**Applicant:** {', '.join(applicant_names)}")

        # Pre-merge semantic hardening (Gate 2 amendment) - trusted and
        # needs_review Developer evidence are never shown on the same line.
        # A needs_review "Developer" claim must not read as settled fact
        # merely because it shares the bolded "Developer:" caption with a
        # trusted one (Section 6/7) - it gets its own, plainly-worded,
        # unbolded line instead.
        trusted_developer_names = sorted(
            {e.entity_name_raw for e in entry.trusted_ownership_evidence if e.role == "DEVELOPER"}
        )
        if trusted_developer_names:
            st.caption(f"**Developer:** {', '.join(trusted_developer_names)}")

        pending_developer_names = sorted(
            {e.entity_name_raw for e in entry.review_pending_ownership_evidence if e.role == "DEVELOPER"}
        )
        if pending_developer_names:
            st.caption(f"Developer evidence pending confirmation: {', '.join(pending_developer_names)}")

        other_ownership_count = sum(1 for e in entry.ownership_evidence if e.role != "DEVELOPER")
        if other_ownership_count:
            st.caption(
                f"{other_ownership_count} other ownership/control evidence item(s) identified - "
                "see Allocation Detail for full evidence."
            )

        if entry.ai_intelligence.available:
            st.markdown(f"**AI Allocation Intelligence:** {entry.ai_intelligence.headline}")
        else:
            st.caption("AI allocation summary not yet generated.")

        st.page_link(
            "pages/3_Local_Plan_Sites.py", label="Open full allocation detail →",
            query_params={"allocation_id": str(entry.allocation_id)},
        )
