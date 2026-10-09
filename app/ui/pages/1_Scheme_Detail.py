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

from sqlalchemy import select
from app.db.models import Application, Site
from app.reporting.profile_destination import limited_profile, origin_evidence, resolve_subject_explanation
from app.ui.buyer_selector import buyer_selector
from app.ui.common import bootstrap, credits_sidebar, get_db, load_site_applications
from app.ui.map_selection import parse_site_id_param
from app.ui.shell import empty_state
from app.ui.site_profile_view import render_site_profile

from app.ui.access import page_scope
from app.security.access import require_operator, is_operator
from app.ui import protected_download

with page_scope():
    bootstrap()
    with get_db() as (session, settings):

        # A path relative to the entrypoint's own directory ("streamlit_app.py")
        # silently failed to resolve when called from a page inside pages/ - Streamlit
        # resolved it relative to this script's directory instead, matching nothing,
        # and fell back to a self-link. An absolute path resolves reliably.
        HOME_PAGE = Path(__file__).resolve().parents[1] / "pages" / "0_Explore.py"
        st.page_link(HOME_PAGE, label="← Back to Explore", icon="🔙")

        if st.query_params.get("origin") == "opportunities":
            st.page_link(Path(__file__).resolve().parents[1] / "pages" / "00_Dashboard.py", label="← Back to opportunities")
        selected_buyer = buyer_selector(key="site-profile", session=session)

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

        subject_key = st.query_params.get("subject_key")
        if st.query_params.get("origin") == "opportunities" or subject_key:
            subject = resolve_subject_explanation(
                session, site_id=site_id, buyer_key=selected_buyer,
                subject_key=subject_key, origin_buyer_key=st.query_params.get("buyer_key"),
            )
            if subject is None:
                st.info("Subject-specific mandate explanation unavailable")
            else:
                from app.reporting.mandate_explanation import present_mandate_explanation, mandate_fit_label
                from app.ui.shell import render_mandate_explanation, render_planning_freshness
                st.subheader("Originating acquisition subject")
                source = subject.source or {}
                fit = source["buyer_fit"]
                st.write(mandate_fit_label(fit.classification, fit.is_investigative_exception))
                st.caption("Active buyer: " + selected_buyer)
                st.caption("Subject: " + subject.subject_key)
                count = source.get("count_assessment")
                if count is not None:
                    st.write(count.label())
                render_planning_freshness(source.get("planning_freshness", ()))
                render_mandate_explanation(present_mandate_explanation(fit, source), compact=False)
            st.caption("The evidence profile below covers the wider site; its evidence is not automatically attributable to the originating subject.")

        reference = st.query_params.get("application_reference")
        phase_code = st.query_params.get("phase_code")
        if reference or phase_code:
            source_apps = session.execute(select(Application).where(
                Application.site_id == site_id, Application.reference == reference,
            )).scalars().all() if reference else []
            origin = origin_evidence(site_id, source_apps, reference, phase_code)
            st.info(origin["limitation"])
            if origin["requested_phase"]:
                st.caption("Requested opportunity scope: " + origin["requested_phase"])
                from app.pipeline.phase_tracking import build_acquisition_scope_breakdown, acquisition_scope_key
                selected_scope = next((p for p in build_acquisition_scope_breakdown(list(site.applications))
                                       if acquisition_scope_key(p) == phase_code), None)
                if selected_scope and selected_scope.get("count_assessment"):
                    scoped_count = selected_scope["count_assessment"]
                    st.write(f"{selected_scope['label']}: {scoped_count.label()}")
                    st.caption(scoped_count.note() or "Planning evidence subject; package availability unverified.")
            if origin["reference"]:
                st.write("Originating planning reference: " + origin["reference"])
            if origin["source_url"]:
                from urllib.parse import urlsplit
                if urlsplit(origin["source_url"]).scheme in ("https", "http"):
                    st.link_button("View originating planning source", origin["source_url"])

        apps = load_site_applications(session, site_id)
        if not apps:
            limited = limited_profile(site, list(site.applications))
            st.subheader(limited["address"])
            st.caption(f"Site {limited['site_id']} · {site.council_code}")
            st.info(limited["limitation"])
            if limited["reference"]:
                st.write(f"Linked operative planning reference: {limited['reference']}")
            if limited["source_url"]:
                from urllib.parse import urlsplit
                if urlsplit(limited["source_url"]).scheme in ("https", "http"):
                    st.link_button("View planning source", limited["source_url"])
            if limited["lapse"].get("deadline"):
                st.caption(f"Assumed review date: {limited['lapse']['deadline']}. {limited['lapse']['deadline_note']}")
            st.stop()
        render_site_profile(session, settings, site, apps)
