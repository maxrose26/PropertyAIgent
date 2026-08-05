"""Council Intelligence (Sprint 4.3) - the customer-facing per-council
planning intelligence overview. Lists every council this platform has real
Policy Intelligence activity for as a card - Local Plan status, housing
position, allocation coverage, evidence freshness, a short AI summary
excerpt - with a link into that council's own detail page.

This is deliberately NOT the same page as Council Operations (Administration
- see app/ui/pages/4_Council_Dashboard.py): no monitoring health, no
classification queues, no raw internal enum values. See
app.reporting.council_intelligence for the pure data assembly this renders
- every figure here is read from data Council Operations already tracks,
reshaped for a planning consultant / land buyer audience rather than an
administrator.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st

from app.reporting.council_intelligence import build_council_overview
from app.ui.common import bootstrap, credits_sidebar, get_db
from app.ui.shell import (
    ai_badge,
    empty_state,
    page_header,
    relative_time,
    status_badge,
)

bootstrap()
session, settings = get_db()
credits_sidebar(session, settings)

page_header(
    "Council Intelligence",
    "Local Plan status, housing position and evidence freshness for every council this platform tracks.",
    icon="🏛️",
)

cards = build_council_overview(session)

if not cards:
    empty_state(
        "No councils onboarded yet",
        "Council Intelligence will appear here once a Local Plan or monitoring source has been onboarded "
        "for at least one council.",
        icon="🏛️",
        show_home_link=False,
    )
    st.stop()


def _render_council_card(card: dict) -> None:
    with st.container(border=True):
        col_name, col_status = st.columns([3, 2], vertical_alignment="center")
        with col_name:
            st.markdown(f"### {card['council_name']}")
        with col_status:
            if card["adopted_or_emerging"] == "Adopted":
                status_badge("confirmed", "Adopted")
            elif card["adopted_or_emerging"] == "Emerging":
                status_badge("pending", "Emerging")
            else:
                status_badge("info", "No Local Plan yet")

        st.caption(
            f"{card['plan_name']} · {card['current_stage']}" if card["plan_name"] else card["current_stage"]
        )

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(
                "Five-year supply",
                f"{card['five_year_supply_years']:g} yrs" if card["five_year_supply_years"] is not None else "—",
            )
        with col2:
            requirement = card["housing_requirement"]
            basis = " (total)" if card["housing_requirement_basis"] == "total" else " (annual)" if card["housing_requirement_basis"] == "annual" else ""
            st.metric("Housing requirement", f"{requirement:,}{basis}" if requirement is not None else "—")
        with col3:
            st.metric("Allocations", card["allocation_count"] if card["allocation_count"] else "—")
        with col4:
            st.metric("Evidence", card["evidence_freshness"])

        if card["next_milestone"]:
            st.caption(f"Next milestone: **{card['next_milestone']}**" + (f" ({card['next_milestone_date']})" if card["next_milestone_date"] else ""))

        if card["ai_summary_excerpt"]:
            ai_badge()
            st.write(card["ai_summary_excerpt"])
            st.caption(f"Generated {relative_time(card['ai_summary_generated_at'])}")
        else:
            st.caption("No AI summary generated yet for this council's Local Plan.")

        st.caption(f"Latest policy update: {relative_time(card['last_updated'])}")
        st.page_link(card["page"], label="Open Council →", query_params=card["params"])


cols = st.columns(2)
for i, card in enumerate(cards):
    with cols[i % 2]:
        _render_council_card(card)
