"""The Intelligence Dashboard (Sprint 4.2, revised for visual hierarchy;
Dashboard refinement; Dashboard layout correction) - PropertyAIgent's
default landing page. Answers three questions immediately: what has
changed, where are the opportunities, what needs attention.

All data assembly lives in app.reporting.dashboard (a pure module, no
Streamlit imports) - this file is rendering only, per CLAUDE.md's "keep
business logic out of the UI". Every figure shown here is real; nothing is
estimated or invented.

Layout (Dashboard layout correction): Quick Actions live in Streamlit's own
native left sidebar (st.sidebar), above Credits - not a column inside the
page body, which is what made the earlier three-column version read as
cramped (a body-level "left rail" competing with the sidebar for the same
job). wide_canvas() widens this page's own .block-container so the KPI
strip, scheme stack and AI rail all get meaningfully more room than the
shared shell's normal contained width - every OTHER page keeps that
default untouched (see wide_canvas's own docstring in app.ui.shell).

Section order: KPI strip (full width) -> AI Daily Brief (full width) ->
two-column split: main column (~76%: Planning Intelligence scheme stack ->
Opportunities -> Policy Intelligence -> Recent Activity) and right rail
(~24%: Recent AI Summaries). Declaring main_col before right_col means
Streamlit's native narrow-width stacking naturally puts the main column
first and the AI rail second - no CSS reordering trick needed now that the
body no longer has a competing left column.
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
    ai_summary_rail,
    empty_state,
    metric_row,
    opportunity_category_section,
    page_header,
    quick_actions_panel,
    relative_time,
    scheme_stack,
    section_container,
    section_header,
    wide_canvas,
)

bootstrap()
session, settings = get_db()

wide_canvas()

with st.sidebar:
    quick_actions_panel([
        {"icon": "🔍", "title": "Explore", "description": "Search, filter and browse every site.",
         "page": "pages/0_Explore.py"},
        {"icon": "📋", "title": "Local Plan Sites", "description": "Browse Local Plan allocations.",
         "page": "pages/3_Local_Plan_Sites.py"},
        {"icon": "⚙️", "title": "Administration", "description": "Council Dashboard & Site Matching.",
         "page": "pages/4_Council_Dashboard.py"},
    ])
credits_sidebar(session, settings)

page_header(
    "Dashboard",
    "What has changed, where the opportunities are, and what needs your attention today.",
    icon="🏠",
)

data = build_dashboard(session)

# --- KPI strip (full width) --------------------------------------------------
#
# Four cards then three, not all seven in one row: measured against a
# standard laptop width (~1000px, even after wide_canvas()'s extra room),
# seven-across truncates every label ("Councils" -> "Cou...", "Applications"
# -> "Appl...", even the 1381 value itself clipping to "1..."). Four-and-
# three keeps every label and value fully legible at every width this was
# tested at, at the cost of a little more vertical space - a trade this
# task's own "ensure labels remain legible" instruction takes priority over.

kpis = data["kpis"]
metric_row([(k["label"], k["value"], k["help"]) for k in kpis[:4]])
metric_row([(k["label"], k["value"], k["help"]) for k in kpis[4:]])

st.divider()


def _mini_list(items: list[str], empty_message: str) -> None:
    """Shared rendering for every small "recent N things" list in the
    Policy Intelligence section - a consistent, always-graceful-when-empty
    treatment rather than each panel inventing its own."""
    if not items:
        st.caption(empty_message)
        return
    for line in items:
        st.markdown(f"- {line}")


# --- AI Daily Brief (full width) ---------------------------------------------

ai_daily_brief_placeholder()

st.divider()

# --- Main column: Planning Intelligence -> Opportunities ->
#     Policy Intelligence -> Recent Activity | Right rail: AI Summaries -----

main_col, right_col = st.columns([0.76, 0.24], gap="large")

with main_col:
    section_header("Planning Intelligence", icon="🏗️")
    scheme_stack(data["scheme_stack"], key="dashboard")

    st.divider()

    section_header("Opportunities", icon="🎯")
    st.caption("Deterministic signals only - a plain filter/sort over real data, never a scored or predicted ranking.")
    for category in data["opportunity_categories"]:
        opportunity_category_section(category, key="dashboard")

    st.divider()

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
            with st.expander("Evidence & AI summary updates"):
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

with right_col:
    section_header("Recent AI Summaries", icon="🤖")
    st.caption("Already-generated summaries only - nothing here triggers a new AI call.")
    ai_summary_rail(data["ai_summary_rail"], key="dashboard")
