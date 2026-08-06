"""Site Profile page (Sprint 4.4, "Flagship Site Profile") - navigated to by
clicking a map dot or the "Open scheme details" button on the home page
(app/ui/streamlit_app.py), which set st.query_params["site_id"] before
calling st.switch_page. Reads that query param directly so the page is also
bookmarkable/shareable on its own.

Explore's table renders the OLD, unchanged flat scheme-detail view inline
instead of navigating here (see render_scheme_detail in app.ui.common) - per
this sprint's explicit scope restriction ("do not redesign Explore"), that
inline call site is untouched. This dedicated page is where the new
tabbed, card-based flagship experience (app.ui.site_profile_view) lives.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Streamlit can execute this page as the process's very first script (e.g. a
# bookmarked/deep-linked URL straight to a scheme), so it can't rely on
# app.ui.common's own sys.path setup having already run - importing that
# module is itself an `app.*` import that needs the project root on the path
# first.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st

from app.db.models import Site
from app.ui.common import bootstrap, credits_sidebar, get_db, load_site_applications
from app.ui.map_selection import parse_site_id_param
from app.ui.shell import empty_state
from app.ui.site_profile_view import render_site_profile

bootstrap()
session, settings = get_db()

# A path relative to the entrypoint's own directory ("streamlit_app.py")
# silently failed to resolve when called from a page inside pages/ - Streamlit
# resolved it relative to this script's directory instead, matching nothing,
# and fell back to a self-link. An absolute path resolves reliably.
HOME_PAGE = Path(__file__).resolve().parents[1] / "pages" / "0_Explore.py"
st.page_link(HOME_PAGE, label="← Back to Explore", icon="🔙")

raw_site_id = st.query_params.get("site_id")
site_id = parse_site_id_param(raw_site_id)
if raw_site_id and site_id is None:
    empty_state(
        "That link looks broken",
        "The site id in this URL isn't valid. Search for the site you're looking for, or browse every "
        "site in Explore.",
        icon="⚠️",
    )
    st.stop()
if site_id is None:
    empty_state(
        "No site selected",
        "Open a Site Profile by clicking a site on the Explore map or table, or use quick search to jump "
        "straight to one.",
        icon="🔍",
    )
    st.stop()

site = session.get(Site, site_id)
if site is None:
    empty_state(
        "This site no longer exists",
        "It may have been merged into another site or removed. Browse Explore to find what you're looking for.",
        icon="🚫",
    )
    st.stop()

credits_sidebar(session, settings)

apps = load_site_applications(session, site_id)
if not apps:
    empty_state(
        "Nothing substantive to show yet",
        "This site's only linked applications are things like a screening/scoping opinion or consultation "
        "notice — no substantive scheme behind them yet. Go back and pick another site.",
        icon="👀",
    )
    st.stop()
render_site_profile(session, settings, site, apps)
