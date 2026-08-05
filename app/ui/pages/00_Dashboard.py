"""The Intelligence Dashboard (Sprint 4.2) - PropertyAIgent's default
landing page. Answers three questions immediately: what has changed, where
are the opportunities, what needs attention.

All data assembly lives in app.reporting.dashboard (a pure module, no
Streamlit imports) - this file is rendering only, per CLAUDE.md's "keep
business logic out of the UI". Every figure shown here is real; nothing is
estimated or invented - see that module's own docstring for the "never
fabricate metrics, never rename a real signal to match a nicer-sounding
label" discipline this page relies on.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st

from app.reporting.dashboard import build_dashboard
from app.ui.common import bootstrap, credits_sidebar, get_db
from app.ui.shell import (
    empty_state,
    live_leaderboard,
    locked_card,
    metric_row,
    page_header,
    quick_action_card,
    relative_time,
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

# --- Part 2: KPI row -------------------------------------------------------

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


# --- Part 3: Planning Intelligence -------------------------------------------
# Sprint 4.2 amendment: the plain two-column "recently discovered
# applications" / "recently updated schemes" bullet lists are replaced by
# one reusable Live Intelligence Leaderboard - same underlying data, no new
# queries or business logic (see app.reporting.dashboard's own leaderboard
# functions), just a single tabbed component covering New Applications,
# Updated Schemes, Policy Updates, Evidence & AI and Needs Attention. A tab
# with no supporting data is simply absent, never shown empty.

section_header("Planning Intelligence", icon="🏗️")
live_leaderboard(data["leaderboard"], key="dashboard")

st.divider()

# --- Part 4: Policy Intelligence -------------------------------------------

section_header("Policy Intelligence", icon="📋")
policy = data["policy"]
col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("**Recently updated Local Plans**")
    _mini_list(
        [
            f"{p['plan_name']} ({p['council_code']}) · {relative_time(p['when'])}"
            for p in policy["recent_plan_updates"]
        ],
        "No Local Plans updated recently.",
    )
    st.markdown("**Recently discovered policy documents**")
    _mini_list(
        [
            f"{d['title'][:60]} ({d['council_code']}) · {relative_time(d['when'])}"
            for d in policy["recent_documents"]
        ],
        "No policy documents discovered recently.",
    )
with col2:
    st.markdown("**New visual evidence**")
    _mini_list(
        [
            f"{v['label']}" + (f" — {v['source'][:40]}" if v["source"] else "") + f" · {relative_time(v['when'])}"
            for v in policy["recent_visual_evidence"]
        ],
        "No new visual evidence extracted recently.",
    )
    st.markdown("**Recently refreshed AI summaries**")
    _mini_list(
        [
            f"{p['plan_name']} ({p['council_code']}) · {relative_time(p['when'])}"
            for p in policy["recent_ai_summaries"]
        ],
        "No AI Local Plan summaries generated yet.",
    )
with col3:
    st.markdown("**Plans awaiting review**")
    _mini_list(
        [
            f"{p['plan_name']} ({p['council_code']}) — {p['pending']} pending"
            for p in policy["plans_awaiting_review"]
        ],
        "Nothing awaiting policy review.",
    )
    st.markdown("**Last monitoring check**")
    st.caption(relative_time(policy["last_monitoring_check"]) if policy["last_monitoring_check"] else "No monitoring has run yet.")

st.divider()

# --- Part 5: Opportunities --------------------------------------------------

section_header("Opportunities", icon="🎯")
st.caption("Deterministic signals only - a plain filter/sort over real data, never a scored or predicted ranking.")
opportunities = data["opportunities"]
col1, col2 = st.columns(2)
with col1:
    st.markdown("**Authorities with low housing supply**")
    _mini_list(
        [f"{o['council_code']} — {o['plan_name']} ({o['years']:.1f} years)" for o in opportunities["low_supply_authorities"]],
        "No five-year housing land supply figures recorded yet.",
    )
    st.markdown("**Large allocations without an application yet**")
    _mini_list(
        [
            f"{a['policy_reference'] or a['site_name']} ({a['council_code']}) — {a['minimum_dwellings']} dwellings"
            for a in opportunities["large_unmatched_allocations"]
        ],
        "No unmatched allocations with a stated dwelling count.",
    )
    st.markdown("**Recently adopted plans**")
    _mini_list(
        [f"{p['plan_name']} ({p['council_code']}) · {relative_time(p['when'])}" for p in opportunities["recently_adopted_plans"]],
        "No adopted plans on record yet.",
    )
with col2:
    st.markdown("**Emerging Local Plans**")
    _mini_list(
        [f"{p['plan_name']} ({p['council_code']}) — {p['status'].replace('_', ' ')}" for p in opportunities["emerging_plans"]],
        "No plans currently in an emerging/pre-adoption stage.",
    )
    st.markdown("**Authorities with recent policy updates**")
    _mini_list(
        [f"{a['council_code']} · {relative_time(a['when'])}" for a in opportunities["recent_policy_activity"]],
        "No monitored source has changed recently.",
    )

st.divider()

# --- Part 6: Recent Activity -------------------------------------------------

section_header("Recent Activity", icon="🕗")
activity = data["activity"]
if not activity:
    empty_state(
        "Nothing to show yet",
        "Activity will appear here once scraping, monitoring or extraction has run.",
        icon="🕗", show_home_link=False,
    )
else:
    for event in activity:
        st.markdown(f"{event['icon']} **{event['text']}** — {relative_time(event['when'])}")

st.divider()

# --- Part 7: AI Daily Brief --------------------------------------------------

section_header("AI Daily Brief", icon="🤖")
with st.container(border=True):
    st.markdown("🤖 **AI Daily Brief**")
    st.write("Daily briefing will become available once dashboard aggregation is implemented.")
    st.caption("This will reuse the existing AI summary architecture (evidence-based, never invented) once built - see docs/PRODUCT_ROADMAP.md.")

st.divider()

# --- Part 8: Quick Actions ---------------------------------------------------

section_header("Quick Actions", icon="⚡")
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    quick_action_card("🔍", "Explore", "Search, filter and browse every site.", page="pages/0_Explore.py")
with col2:
    locked_card("🏛️", "Council Intelligence", "Coming soon")
with col3:
    quick_action_card("📋", "Local Plan Sites", "Browse Local Plan allocations.", page="pages/3_Local_Plan_Sites.py")
with col4:
    locked_card("📄", "Reports", "Coming soon")
with col5:
    quick_action_card("⚙️", "Administration", "Council Dashboard & Site Matching.", page="pages/4_Council_Dashboard.py")
