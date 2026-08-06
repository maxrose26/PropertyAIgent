"""Council Intelligence (Sprint 4.3, refined by the Sprint 4.3 presentation
refinement) - the customer-facing per-council planning intelligence
overview. Lists every council this platform has real Policy Intelligence
activity for as a card - Local Plan status, headline housing position,
allocation coverage, a short AI summary excerpt - with a link into that
council's own detail page.

This is deliberately NOT the same page as Council Operations (Administration
- see app/ui/pages/4_Council_Dashboard.py): no monitoring health, no
classification queues, no raw internal enum values. See
app.reporting.council_intelligence for the pure data assembly this renders
- every figure here is read from data Council Operations already tracks,
reshaped for a planning consultant / land buyer audience rather than an
administrator.

Presentation refinement history:

- wide_canvas() gives this page its own wider canvas (like the Dashboard)
  since a card grid otherwise leaves substantial unused space on the right
  at the shared shell's normal contained width; cards render inside a
  "council-grid" container whose key app.ui.shell's global stylesheet
  targets with a CSS Grid auto-fit/minmax rule (as many 320px+ cards per
  row as the available content width actually allows - see
  inject_global_styles's "Council Intelligence overview refinement" CSS
  block); "Evidence" is no longer a headline KPI tile (it's now a compact
  secondary caption alongside evidence gaps); headline values use
  shell.stat_tile/five_year_supply_tile, which wrap long text instead of
  truncating it.
- Commercial Planning Readiness refinement: the plain Adopted/Emerging
  badge is replaced by a Planning Readiness chip (shell.
  planning_readiness_chip) - a finer-grained, colour-dotted label that
  includes the adoption year and plan age where LocalPlan.adoption_date
  supports it; a deterministic Planning Health banner (shell.
  planning_health_banner, never AI-generated) sits beneath the plan line;
  and each card's "cc-<status_color>-<council_code>" container key now
  drives a six-bucket colour treatment (Adopted / Emerging / Regulation 18
  / Examination / Withdrawn / Joint-plan only) - see
  app.reporting.council_intelligence's own docstrings for exactly how each
  is derived from stored evidence.
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
    five_year_supply_tile,
    page_header,
    planning_health_banner,
    planning_readiness_chip,
    relative_time,
    stat_tile,
    status_badge,
    wide_canvas,
)

bootstrap()
session, settings = get_db()
credits_sidebar(session, settings)

wide_canvas()

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
    container_key = f"cc-{card['status_color']}-{card['council_code']}"
    with st.container(border=True, key=container_key):
        # Header: council name + Planning Readiness chip (Commercial
        # Planning Readiness refinement, Part 2) - replaces the plain
        # Adopted/Emerging badge with a finer-grained, colour-dotted label.
        col_name, col_status = st.columns([3, 2], vertical_alignment="center")
        with col_name:
            st.markdown(f"### {card['council_name']}")
        with col_status:
            if card["planning_readiness_chip"] is not None:
                planning_readiness_chip(card["planning_readiness_chip"])
            else:
                status_badge("info", "No Local Plan yet")

        # Plan line: primary Local Plan name + current stage.
        st.caption(
            f"{card['plan_name']} · {card['current_stage']}" if card["plan_name"] else card["current_stage"]
        )

        # Planning Health banner (refinement Part 4) - a short, purely
        # deterministic classification, never AI-generated.
        planning_health_banner(card["planning_health"])

        # Headline metrics - a 2x2 grid of non-truncating tiles (refinement
        # Parts 2 & 3). "Evidence" is deliberately not one of these four.
        row1_col1, row1_col2 = st.columns(2)
        with row1_col1:
            five_year_supply_tile(
                card["five_year_supply_display"],
                card["five_year_supply_state"],
                base_date=card["five_year_supply_base_date"],
            )
        with row1_col2:
            stat_tile(
                "Housing requirement",
                card["housing_requirement_display"] or "Not yet stated",
                help="Total plan-period figure where stated, otherwise the annual rate.",
            )

        row2_col1, row2_col2 = st.columns(2)
        with row2_col1:
            stat_tile("Allocations", f"{card['allocation_count']:,}")
        with row2_col2:
            metric4 = card["headline_metric_4"]
            stat_tile(metric4["label"], metric4["value"], caption=metric4["caption"])

        # Secondary information - kept visible but subordinate to the
        # headline metrics above (refinement Parts 2 & 6).
        secondary_bits = []
        if card["expected_adoption_date"]:
            secondary_bits.append(f"Expected adoption: {card['expected_adoption_date']}")
        secondary_bits.append(f"Updated {relative_time(card['last_updated'])}")
        secondary_bits.append(card["evidence_freshness"])
        st.caption(" · ".join(secondary_bits))
        if card["has_missing_evidence"]:
            status_badge("review", "Evidence gaps")

        # AI summary - a short, stored excerpt only; never regenerated here.
        if card["ai_summary_excerpt"]:
            ai_badge()
            st.write(card["ai_summary_excerpt"])
            st.caption(f"Generated {relative_time(card['ai_summary_generated_at'])}")
        else:
            st.caption("No AI summary generated yet for this council's Local Plan.")

        st.page_link(card["page"], label="Open Council →", query_params=card["params"])


with st.container(key="council-grid"):
    # A SINGLE st.columns() call for every card, not chunked into groups of
    # 3 - Streamlit renders each st.columns() call as its own independent
    # stHorizontalBlock, and CSS Grid's auto-fit only reflows children
    # WITHIN one such block. Chunking into separate 3-wide Python rows
    # created one independent grid per chunk, so at a width that only fits
    # 2 cards per line each 3-card chunk wrapped into its own "2 then 1"
    # pair rather than the whole card list flowing evenly across full
    # rows. A single call gives auto-fit every card at once to lay out.
    cols = st.columns(len(cards))
    for col, card in zip(cols, cards):
        with col:
            _render_council_card(card)
