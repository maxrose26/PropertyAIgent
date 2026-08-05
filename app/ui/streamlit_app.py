"""PropertyAIgent - application entrypoint / router.

    streamlit run app/ui/streamlit_app.py

Sprint 4.1 ("Application Shell, Branding & Design System"): this file is
now a thin router only - global page config, branding and shared styling
live here (once, per docs/UI_DESIGN_SYSTEM.md), and every actual page's
content lives in its own file under pages/, registered below via
st.navigation. This inherits Streamlit's own multipage routing model: the
entrypoint runs on every request, then dispatches to whichever page was
selected via pg.run(). No business logic lives in this file.

Navigation groups follow docs/NAVIGATION_ARCHITECTURE.md: Dashboard is the
default landing page (Sprint 4.2, "Intelligence Dashboard"), Explore is the
second destination; Policy groups Local Plan Sites; Administration groups
Council Dashboard and Site Matching. Site Profile is declared with
visibility="hidden" - reached by clicking a site on Explore's map/table,
not as a persistent top-level tab (matching docs/WIREFRAMES.md Part 5's
"reached via Explore/search, not a standalone nav item").

Deliberately NOT implemented (see the Sprint 4.2 completion report): a
customer-facing Council Intelligence page and a Reports page - both remain
locked "Coming soon" Quick Action cards on the Dashboard, per that sprint's
explicit scope restriction to "only build the Dashboard."
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from app.ui.shell import PRODUCT_NAME, inject_global_styles, render_footer

st.set_page_config(page_title=PRODUCT_NAME, page_icon="🏠", layout="wide")
inject_global_styles()
st.logo("🏠", size="medium")

dashboard_page = st.Page("pages/00_Dashboard.py", title="Dashboard", icon="🏠", default=True)
explore_page = st.Page("pages/0_Explore.py", title="Explore", icon="🔍")
site_profile_page = st.Page("pages/1_Scheme_Detail.py", title="Site Profile", icon="📍", visibility="hidden")
council_dashboard_page = st.Page("pages/4_Council_Dashboard.py", title="Council Dashboard", icon="⚙️")
local_plan_page = st.Page("pages/3_Local_Plan_Sites.py", title="Local Plan Sites", icon="📋")
review_links_page = st.Page("pages/2_Review_Site_Links.py", title="Site Matching", icon="🔗")

pg = st.navigation(
    {
        "": [dashboard_page, explore_page, site_profile_page],
        "Policy": [local_plan_page],
        "Administration": [council_dashboard_page, review_links_page],
    },
    position="top",
)
pg.run()
render_footer()
