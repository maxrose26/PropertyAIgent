"""Internal Council administration dashboard (Sprint 2, "Greater Manchester
Policy Intelligence Framework", Part 7). For administration - confirming
what's been onboarded and whether monitoring is actually working - not a
page a prospective land buyer or investor would ever need. See
app.policy.council_dashboard for the pure data assembly this renders.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pandas as pd
import streamlit as st

from app.policy.council_dashboard import build_council_dashboard
from app.ui.common import bootstrap, credits_sidebar, get_db

st.set_page_config(page_title="Council dashboard - UK Planning Deal Finder", layout="wide")

bootstrap()
session, settings = get_db()

HOME_PAGE = Path(__file__).resolve().parents[1] / "streamlit_app.py"
st.page_link(HOME_PAGE, label="← Back to search", icon="🔙")

credits_sidebar(session, settings)

st.title("Council administration dashboard")
st.caption(
    "Internal view of Policy Intelligence onboarding per council - which Local Plans have been ingested, "
    "whether monitoring is actually reaching their sources, and what's waiting for a review decision. "
    "Not part of the public site-browsing experience."
)

rows = build_council_dashboard(session)
if not rows:
    st.info("No council has any Policy Intelligence activity yet (no Local Plans ingested, no sources registered).")
    st.stop()

HEALTH_LABELS = {
    "ok": "✅ OK", "error": "❌ Error", "stale": "⏸️ Stale",
    "never_checked": "❔ Never checked", "no_sources": "— No sources registered",
}

summary_rows = [{
    "Council": r["council_name"],
    "Monitoring": "Enabled" if r["monitoring_enabled"] else "Disabled",
    "Health": HEALTH_LABELS.get(r["monitoring_health"], r["monitoring_health"]),
    "Sources": r["sources_count"],
    "Last checked": r["last_checked"].strftime("%d %b %Y %H:%M") if r["last_checked"] else "Never",
    "Local Plans": len(r["local_plans"]),
    "Allocations imported": r["total_allocations_imported"],
    "Review items pending": r["review_items_pending"],
} for r in rows]

st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

for r in rows:
    with st.expander(f"{r['council_name']} - {len(r['local_plans'])} Local Plan(s)"):
        if r["review_items_pending"]:
            st.warning(f"⚠️ {r['review_items_pending']} change(s) awaiting review approval for this council.")
        if not r["local_plans"]:
            st.caption("No Local Plan ingested yet.")
        for plan in r["local_plans"]:
            version_bit = f" ({plan['plan_version']})" if plan["plan_version"] else ""
            st.markdown(f"**{plan['plan_name']}{version_bit}** — {plan['raw_status'] or plan['status']}")
            st.caption(
                f"{plan['allocations_imported']} allocation(s) imported, {plan['sites_matched']} matched to an "
                f"existing Site" + (f", checked {plan['last_checked'].strftime('%d %b %Y')}" if plan["last_checked"] else "")
            )
