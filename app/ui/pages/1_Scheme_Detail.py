"""Scheme detail page - navigated to by clicking a map dot or the "Open
scheme details" button on the home page (app/ui/streamlit_app.py), which set
st.query_params["site_id"] before calling st.switch_page. Reads that query
param directly so the page is also bookmarkable/shareable on its own.

The table on the home page renders the same scheme detail inline instead of
navigating here (see render_scheme_detail in app.ui.common) - this page
exists for the map-click and "Open scheme details" flows specifically.
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
from app.ui.common import bootstrap, credits_sidebar, get_db, load_site_applications, render_scheme_detail

st.set_page_config(page_title="Scheme detail - UK Planning Deal Finder", layout="wide")

bootstrap()
session, settings = get_db()

# A path relative to the entrypoint's own directory ("streamlit_app.py")
# silently failed to resolve when called from a page inside pages/ - Streamlit
# resolved it relative to this script's directory instead, matching nothing,
# and fell back to a self-link. An absolute path resolves reliably.
HOME_PAGE = Path(__file__).resolve().parents[1] / "streamlit_app.py"
st.page_link(HOME_PAGE, label="← Back to search", icon="🔙")

raw_site_id = st.query_params.get("site_id")
if not raw_site_id:
    st.info("No scheme selected - go back and click a site on the map or table.")
    st.stop()

try:
    site_id = int(raw_site_id)
except ValueError:
    st.error("Invalid site id in URL.")
    st.stop()

site = session.get(Site, site_id)
if site is None:
    st.error("That scheme no longer exists.")
    st.stop()

credits_sidebar(session, settings)

apps = load_site_applications(session, site_id)
if not apps:
    st.error("That scheme's applications are no longer shown here (e.g. a screening/scoping opinion or "
             "consultation notice with no substantive scheme behind it) - go back and pick another site.")
    st.stop()
render_scheme_detail(session, settings, site, apps)
