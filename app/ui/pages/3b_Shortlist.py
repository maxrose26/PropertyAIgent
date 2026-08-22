"""Shortlist review (Site Selection & Reporting V1 Gate 1) - shows the
allocations added to the session-only shortlist (app.ui.shortlist) together,
so a user can review them as a group before Gate 3/4 add CSV/PDF export.

Deliberately NOT an analytics dashboard: no new scoring, ranking, or charts -
just the same evidence already shown elsewhere, reused (never re-derived)
for a set of allocations instead of one at a time.

Data reuse (Section 9 of the approved design): reuses
app.reporting.allocation_discovery.build_allocation_discovery's already-
batched card list, filtered down to the shortlisted ids, rather than a new
query path built solely for this page. The one per-allocation read is
app.reporting.allocation_intelligence_summary.get_allocation_summary
(read-only, never generates) - acceptable at the 5-10 item scale this V1
targets; a batched sibling is Gate 3 scope, not this one, per the approved
design's explicit batching plan for the eventual report-context builder.

Party/ownership evidence (known Applicant/Developer signal) is deliberately
NOT shown on this page - surfacing it correctly requires
app.reporting.ownership_control.get_allocation_control_intelligence, which
today queries per related Site, only ever called per-allocation - looping it
here would be exactly the kind of new architecture Gate 1 was told not to
introduce (a batched entrypoint is explicitly Gate 3 scope). Omitted per the
task's own instruction: "If showing this evidence would require new party
logic, omit it from Gate 1 rather than expanding scope."
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st

from app.reporting.allocation_discovery import build_allocation_discovery
from app.reporting.allocation_intelligence_summary import get_allocation_summary
from app.ui.common import bootstrap, credits_sidebar, get_db
from app.ui.shell import empty_state, page_header, section_header, stat_tile, status_badge_row, wide_canvas
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
if st.button("Clear shortlist", key="shortlist-clear-all"):
    st.session_state[SHORTLIST_SESSION_KEY] = clear_shortlist(st.session_state[SHORTLIST_SESSION_KEY])
    st.rerun()

# Reuses the same batched view Allocation Discovery itself already builds
# (fixed query budget regardless of allocation count) rather than a new
# query path built solely for this page - then filters down to just the
# shortlisted ids.
all_view = build_allocation_discovery(session)
cards_by_id = {c["id"]: c for c in all_view["cards"]}

st.divider()

for candidate in candidates:
    card = cards_by_id.get(candidate.candidate_id)

    if card is None:
        # Stale/missing candidate (Section 10) - never crash, never
        # silently drop it from the shortlist on our own initiative; show
        # it as unavailable and let the user remove it explicitly.
        with st.container(border=True, key=f"shortlist-missing-{candidate.candidate_id}"):
            st.markdown(f"**{candidate.display_name}**")
            st.caption("This allocation is no longer available - it may have been removed or reclassified.")
            if st.button("Remove from shortlist", key=f"shortlist-remove-missing-{candidate.candidate_id}"):
                st.session_state[SHORTLIST_SESSION_KEY] = remove_candidate(
                    st.session_state[SHORTLIST_SESSION_KEY], "allocation", candidate.candidate_id,
                )
                st.rerun()
        continue

    with st.container(border=True, key=f"shortlist-card-{card['id']}"):
        header_cols = st.columns([5, 1])
        with header_cols[0]:
            st.markdown(f"##### {card['site_name']}")
            context_bits = [b for b in (card["council_name"], card["plan_name"], card.get("policy_reference")) if b]
            st.caption(" · ".join(str(b) for b in context_bits))
        with header_cols[1]:
            if st.button("Remove", key=f"shortlist-remove-{card['id']}", use_container_width=True):
                st.session_state[SHORTLIST_SESSION_KEY] = remove_candidate(
                    st.session_state[SHORTLIST_SESSION_KEY], "allocation", card["id"],
                )
                st.rerun()

        status_badge_row([
            (card["plan_status_chip_kind"], card["plan_status_label"]),
            (card["review_status_badge_kind"], card["review_status_label"]),
        ])

        info_cols = st.columns(4)
        with info_cols[0]:
            stat_tile("Intended use", card["intended_use_label"])
        with info_cols[1]:
            stat_tile("Capacity", card["capacity"]["display"])
        with info_cols[2]:
            coverage = card.get("development_coverage")
            stat_tile(
                "Development coverage",
                f"{coverage.development_coverage_percentage:.0%}" if coverage and coverage.development_coverage_percentage is not None else "Not determined",
            )
        with info_cols[3]:
            stat_tile(
                "Indicative residual",
                f"~{coverage.indicative_residual_capacity:,}" if coverage and coverage.indicative_residual_capacity else "Not determined",
            )

        # Evidence-bounded wording (Section 14) - identical phrasing to the
        # gallery card/detail page, never a warning/error styling solely
        # because no application is linked.
        st.caption(card["matched_summary"], help=card["matched_summary_help"])

        ai_summary_row = get_allocation_summary(session, card["id"])
        if ai_summary_row is not None and ai_summary_row.headline:
            st.markdown(f"**AI Allocation Intelligence:** {ai_summary_row.headline}")
        else:
            st.caption("AI allocation summary not yet generated.")

        st.page_link(
            "pages/3_Local_Plan_Sites.py", label="Open full allocation detail →",
            query_params={"allocation_id": str(card["id"])},
        )
