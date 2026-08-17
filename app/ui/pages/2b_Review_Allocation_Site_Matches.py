"""Allocation <-> Site match review (Stage 2B).

Deliberately a SEPARATE page from 2_Review_Site_Links.py rather than a
section bolted onto it - that page reviews a completely different
relationship (Application<->Site fuzzy-suggested links, via
app.pipeline.site_linking's suggested_fuzzy mechanism and
confirm_suggested_link/reject_suggested_link). Mixing the two would put two
different underlying questions, two different data models, and two
different confirm/reject functions behind buttons that look identical -
exactly the kind of confusion this task was warned against. This page
follows that page's own established layout/interaction pattern closely
(side-by-side comparison, Confirm/Reject buttons, session.commit(),
st.rerun()) rather than inventing a new one.

Two independent sections:

1. Pending review candidates - every LocalPlanSite with an UNCONFIRMED
   Site-match suggestion already written by
   scripts.dry_run_gm_allocation_site_matching --execute (matched_site_id
   set, review_status="needs_confirmation" - see app.policy.
   allocation_site_dry_run_matching.fetch_pending_review_allocations for
   why this exact filter is safe against the review_status field's other,
   unrelated CONTENT-review use). Confirm/Reject here call the EXISTING
   app.policy.site_match_review.confirm_site_match/reject_site_match
   directly - this page never duplicates their write logic.

2. Ambiguous allocations - computed LIVE on every page load via
   app.policy.allocation_site_dry_run_matching.fetch_ambiguous_allocations
   (Stage 2B Section 4: no many-to-many table yet, so nothing is persisted
   for these - the dry-run harness itself is the "generated review
   dataset"). Read-only: multiple candidate Sites are shown side by side
   with no action buttons, since the current schema has nowhere to record
   a choice among them without misusing the single matched_site_id.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st

from app.policy.allocation_site_dry_run_matching import fetch_ambiguous_allocations, fetch_pending_review_allocations
from app.policy.site_match_review import confirm_site_match, reject_site_match
from app.ui.common import aggregate_scheme_fields, bootstrap, credits_sidebar, get_db, load_site_applications
from app.ui.shell import empty_state, page_header, section_header, wide_canvas

bootstrap()
session, settings = get_db()
wide_canvas()

HOME_PAGE = Path(__file__).resolve().parents[1] / "pages" / "3_Local_Plan_Sites.py"
st.page_link(HOME_PAGE, label="← Back to Local Plan Sites", icon="🔙")

credits_sidebar(session, settings)

page_header(
    "Allocation Match Review",
    "A confirmed relationship here means \"this Site is evidenced as relating to this allocation\" - "
    "never that the Site accounts for the allocation's whole capacity. A large allocation may relate "
    "to more than one Site or phase.",
    icon="🔗",
)

pending = fetch_pending_review_allocations(session)
ambiguous = fetch_ambiguous_allocations(session)

section_header(f"Pending review — {len(pending)}", icon="📋")

if not pending:
    empty_state("Nothing pending review", "Every suggested allocation-Site match has already been resolved.", icon="✅")
else:
    for allocation in pending:
        site = allocation.matched_site
        site_apps = load_site_applications(session, site.id) if site else []
        merged = aggregate_scheme_fields(site_apps) if site_apps else {}

        st.markdown(
            f"**{allocation.council_code} / {allocation.policy_reference or '(no reference)'} — "
            f"{allocation.site_name}**"
        )
        st.caption(
            f"Allocation capacity: {allocation.minimum_dwellings if allocation.minimum_dwellings is not None else 'not stated'} | "
            f"Current status: {allocation.review_status}"
        )

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Allocation**")
            st.write(allocation.site_name)
            st.caption(f"Capacity: {allocation.minimum_dwellings if allocation.minimum_dwellings is not None else 'not stated'}")
        with col2:
            st.markdown("**Candidate Site**")
            st.write(site.display_address if site else "(site no longer exists)")
            st.caption(
                f"Total units: {merged.get('total_units_final') if merged.get('total_units_final') is not None else 'not yet extracted'} | "
                f"Applications: {len(site_apps)}"
            )
        st.caption(f"Match score: {allocation.match_confidence:.1f}" if allocation.match_confidence is not None else "Match score: n/a")

        note_key = f"alloc-match-note-{allocation.id}"
        note = st.text_input(
            "Supporting evidence / reason (required for either action)", key=note_key,
            placeholder="e.g. shared distinctive name, matching address, corroborating application detail",
        )

        btn_col1, btn_col2, _ = st.columns([1, 1, 3])
        with btn_col1:
            if st.button("Confirm relationship", key=f"confirm_{allocation.id}", disabled=not note.strip()):
                confirm_site_match(session, allocation, confirmed_by="streamlit_review", note=note)
                st.rerun()
        with btn_col2:
            if st.button("Reject", key=f"reject_{allocation.id}", disabled=not note.strip()):
                reject_site_match(session, allocation, confirmed_by="streamlit_review", reason=note)
                st.rerun()
        st.divider()

section_header(f"Ambiguous — multiple plausible Sites — {len(ambiguous)}", icon="⚠️")
st.caption(
    "Multiple planning Sites may relate to this allocation. Nothing is persisted for these yet - "
    "the current data model can only record one Site per allocation, so recording a choice here "
    "would misrepresent a genuinely uncertain case as resolved."
)

if not ambiguous:
    empty_state("No ambiguous allocations right now", "Nothing currently has more than one equally plausible Site.", icon="✅")
else:
    for result in ambiguous:
        st.markdown(f"**{result.council} / {result.policy_reference or '(no reference)'} — {result.allocation_name}**")
        st.caption(
            f"Allocation capacity: {result.allocation_capacity if result.allocation_capacity is not None else 'not stated'} | "
            f"Current status: {result.current_review_status}"
        )
        for candidate in result.candidates:
            st.write(
                f"- Site {candidate.site_id}: {candidate.site_name} "
                f"(score={candidate.score:.1f}, total_units={candidate.total_units}, "
                f"applications={candidate.application_count})"
            )
        st.divider()
