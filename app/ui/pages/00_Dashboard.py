"""The Intelligence Dashboard (Sprint 4.2, revised for visual hierarchy) -
PropertyAIgent's default landing page. Answers three questions immediately:
what has changed, where are the opportunities, what needs attention.

All data assembly lives in app.reporting.dashboard (a pure module, no
Streamlit imports) - this file is rendering only, per CLAUDE.md's "keep
business logic out of the UI". Every figure shown here is real; nothing is
estimated or invented - see that module's own docstring for the "never
fabricate metrics, never rename a real signal to match a nicer-sounding
label" discipline this page relies on.

Section order (hierarchy revision): page header -> KPI strip -> AI Daily
Brief -> Live Intelligence Leaderboard -> [Opportunities | Quick Actions
side panel] -> Policy Intelligence -> Recent Activity -> Recent AI
Summaries. From Opportunities onward the page is a two-column layout (main
~72% / side ~28%) so Quick Actions stays visible alongside the detailed
sections rather than competing with them at the very top or bottom of the
page.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st

from app.reporting.dashboard import build_dashboard
from app.ui.common import bootstrap, credits_sidebar, get_db
from app.ui.shell import (
    activity_timeline,
    ai_daily_brief_placeholder,
    ai_summary_carousel,
    empty_state,
    live_leaderboard,
    metric_row,
    opportunity_card,
    page_header,
    quick_actions_panel,
    relative_time,
    section_container,
    section_header,
)

bootstrap()
session, settings = get_db()
credits_sidebar(session, settings)

page_header(
    "Dashboard",
    "What has changed, where the opportunities are, and what needs your attention today.",
    icon="🏠",
)

data = build_dashboard(session)

# --- KPI strip ---------------------------------------------------------------

kpis = data["kpis"]
metric_row([(k["label"], k["value"], k["help"]) for k in kpis[:4]])
metric_row([(k["label"], k["value"], k["help"]) for k in kpis[4:]])

st.divider()


def _mini_list(items: list[str], empty_message: str) -> None:
    """Shared rendering for every small "recent N things" list on this
    page - a consistent, always-graceful-when-empty treatment (Part 9),
    rather than each panel inventing its own."""
    if not items:
        st.caption(empty_message)
        return
    for line in items:
        st.markdown(f"- {line}")


# --- AI Daily Brief (moved near the top) -------------------------------------

ai_daily_brief_placeholder()

st.divider()

# --- Live Intelligence Leaderboard -------------------------------------------

section_header("Planning Intelligence", icon="🏗️")
live_leaderboard(data["leaderboard"], key="dashboard")

st.divider()

# --- Opportunities (main column) + Quick Actions (side column) --------------

main_col, side_col = st.columns([7, 3], gap="large")

with side_col:
    quick_actions_panel([
        {"icon": "🔍", "title": "Explore", "description": "Search, filter and browse every site.",
         "page": "pages/0_Explore.py"},
        {"icon": "📋", "title": "Local Plan Sites", "description": "Browse Local Plan allocations.",
         "page": "pages/3_Local_Plan_Sites.py"},
        {"icon": "⚙️", "title": "Administration", "description": "Council Dashboard & Site Matching.",
         "page": "pages/4_Council_Dashboard.py"},
        {"icon": "🏛️", "title": "Council Intelligence", "description": "Coming soon"},
        {"icon": "📄", "title": "Reports", "description": "Coming soon"},
    ])

with main_col:
    section_header("Opportunities", icon="🎯")
    st.caption("Deterministic signals only - a plain filter/sort over real data, never a scored or predicted ranking.")
    opportunity_cards = data["opportunity_cards"]
    if not opportunity_cards:
        st.caption("No opportunities to surface yet.")
    else:
        opp_cols = st.columns(2)
        for i, card in enumerate(opportunity_cards):
            with opp_cols[i % 2]:
                opportunity_card(card, key=card["id"])

    st.divider()

    # --- Policy Intelligence - one contained, tinted section -----------------

    policy = data["policy"]
    with section_container(
        "Policy Intelligence", "Local Plan activity, monitoring and evidence across every onboarded council.",
        icon="📋", key="policy-section",
    ):
        col1, col2 = st.columns(2)
        with col1:
            with st.container(border=True):
                st.markdown("**Local Plan updates**")
                _mini_list(
                    [
                        f"{p['plan_name']} ({p['council_code']}) · {relative_time(p['when'])}"
                        for p in policy["recent_plan_updates"]
                    ],
                    "No Local Plans updated recently.",
                )
            with st.container(border=True):
                st.markdown("**Monitored reports & policy documents**")
                _mini_list(
                    [
                        f"{d['title'][:60]} ({d['council_code']}) · {relative_time(d['when'])}"
                        for d in policy["recent_documents"]
                    ],
                    "No policy documents discovered recently.",
                )
                st.caption(
                    relative_time(policy["last_monitoring_check"]) + " — last monitoring check"
                    if policy["last_monitoring_check"] else "No monitoring has run yet."
                )
        with col2:
            with st.container(border=True):
                st.markdown("**Review items**")
                _mini_list(
                    [
                        f"{p['plan_name']} ({p['council_code']}) — {p['pending']} pending"
                        for p in policy["plans_awaiting_review"]
                    ],
                    "Nothing awaiting policy review.",
                )
            with st.container(border=True):
                st.markdown("**Evidence & AI summary updates**")
                _mini_list(
                    [
                        f"{v['label']}" + (f" — {v['source'][:40]}" if v["source"] else "") + f" · {relative_time(v['when'])}"
                        for v in policy["recent_visual_evidence"]
                    ],
                    "No new visual evidence extracted recently.",
                )
                _mini_list(
                    [
                        f"{p['plan_name']} ({p['council_code']}) AI summary refreshed · {relative_time(p['when'])}"
                        for p in policy["recent_ai_summaries"]
                    ],
                    "No AI Local Plan summaries generated yet.",
                )

    st.divider()

    # --- Recent Activity - aggregated, never a repeated identical list -------

    section_header("Recent Activity", icon="🕗")
    grouped_activity = data["activity_grouped"]
    if not grouped_activity:
        empty_state(
            "Nothing to show yet",
            "Activity will appear here once scraping, monitoring or extraction has run.",
            icon="🕗", show_home_link=False,
        )
    else:
        activity_timeline(grouped_activity, key="dashboard-activity")

    st.divider()

    # --- Recent AI Summaries carousel -----------------------------------------

    section_header("Recent AI Summaries", icon="🤖")
    st.caption("Already-generated summaries only - nothing here triggers a new AI call.")
    ai_summary_carousel(data["ai_summary_carousel"], key="dashboard")
