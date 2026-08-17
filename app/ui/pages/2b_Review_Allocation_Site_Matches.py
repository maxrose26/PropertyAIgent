"""Allocation <-> Site match review (Stage 2B, amended).

Deliberately a SEPARATE page from 2_Review_Site_Links.py rather than a
section bolted onto it - that page reviews a completely different
relationship (Application<->Site fuzzy-suggested links, via
app.pipeline.site_linking's suggested_fuzzy mechanism and
confirm_suggested_link/reject_suggested_link). Mixing the two would put two
different underlying questions, two different data models, and two
different confirm/reject functions behind buttons that look identical -
exactly the kind of confusion this task was warned against.

Two independent sections, BOTH computed live on every page load, never
queried from persisted "suggestion" rows - a REVIEW_CANDIDATE is never
written to the database until a human explicitly confirms it (Stage 2B
amendment's SEMANTIC INVARIANT: matched_site_id populated means
PropertyAIgent has ACCEPTED the relationship, never "a candidate a human
might approve later"):

1. Pending review - app.policy.allocation_site_dry_run_matching.
   fetch_pending_review_allocations() re-derives this list from the
   matching harness itself on every load, never from
   LocalPlanSite.review_status (that field carries broader, unrelated
   Local Plan content-review meaning - querying on it was the original
   design's conflation bug). Confirm/Reject here call
   confirm_review_candidate()/reject_review_candidate(), which re-
   validate the candidate against CURRENT Site data immediately before
   writing anything and fail closed if it has changed - this page never
   duplicates that write/revalidation logic itself, only renders the
   result.

2. Ambiguous allocations - fetch_ambiguous_allocations(), same live-
   computation pattern. Read-only: multiple candidate Sites are shown
   side by side with NO action buttons at all (not even a blanket
   reject) - the current schema has nowhere to record a choice among
   them without misusing the single matched_site_id.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st

from app.policy.allocation_site_dry_run_matching import (
    confirm_review_candidate,
    fetch_ambiguous_allocations,
    fetch_pending_review_allocations,
    reject_review_candidate,
)
from app.ui.common import bootstrap, credits_sidebar, get_db
from app.ui.shell import empty_state, page_header, section_header, wide_canvas

bootstrap()
session, settings = get_db()
wide_canvas()

HOME_PAGE = Path(__file__).resolve().parents[1] / "pages" / "3_Local_Plan_Sites.py"
st.page_link(HOME_PAGE, label="← Back to Local Plan Sites", icon="🔙")

credits_sidebar(session, settings)

page_header(
    "Allocation Match Review",
    "A confirmed relationship here means PropertyAIgent has ACCEPTED that this Site relates to this "
    "allocation - never that the Site accounts for the allocation's whole capacity. A large allocation "
    "may relate to more than one Site or phase. Nothing shown below is persisted until you act.",
    icon="🔗",
)

pending = fetch_pending_review_allocations(session)
ambiguous = fetch_ambiguous_allocations(session)

section_header(f"Pending review — {len(pending)}", icon="📋")

if not pending:
    empty_state("Nothing pending review", "No allocation currently has an unresolved review candidate.", icon="✅")
else:
    for result in pending:
        candidate = result.near_miss_candidates[0]

        st.markdown(
            f"**{result.council} / {result.policy_reference or '(no reference)'} — {result.allocation_name}**"
        )
        st.caption(
            f"Allocation capacity: {result.allocation_capacity if result.allocation_capacity is not None else 'not stated'} | "
            f"Current status: {result.current_review_status}"
        )

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Allocation**")
            st.write(result.allocation_name)
            st.caption(f"Capacity: {result.allocation_capacity if result.allocation_capacity is not None else 'not stated'}")
        with col2:
            st.markdown("**Candidate Site**")
            st.write(candidate.site_name)
            st.caption(
                f"Total units: {candidate.total_units if candidate.total_units is not None else 'not yet extracted'} | "
                f"Applications: {candidate.application_count}"
            )
        st.caption(f"Match score: {candidate.score:.1f}")

        note_key = f"alloc-match-note-{result.allocation_id}"
        note = st.text_input(
            "Supporting evidence / reason (required for either action)", key=note_key,
            placeholder="e.g. shared distinctive name, matching address, corroborating application detail",
        )

        btn_col1, btn_col2, _ = st.columns([1, 1, 3])
        with btn_col1:
            if st.button("Confirm relationship", key=f"confirm_{result.allocation_id}", disabled=not note.strip()):
                outcome = confirm_review_candidate(
                    session, allocation_id=result.allocation_id, expected_site_id=candidate.site_id,
                    confirmed_by="streamlit_review", note=note,
                )
                if outcome["success"]:
                    st.rerun()
                else:
                    st.error(outcome["reason"])
        with btn_col2:
            if st.button("Reject", key=f"reject_{result.allocation_id}", disabled=not note.strip()):
                outcome = reject_review_candidate(
                    session, allocation_id=result.allocation_id, expected_site_id=candidate.site_id,
                    confirmed_by="streamlit_review", reason=note,
                )
                if outcome["success"]:
                    st.rerun()
                else:
                    st.error(outcome["reason"])
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
