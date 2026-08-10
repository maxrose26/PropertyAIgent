"""Suggested site links awaiting review - moved to its own page so it
doesn't push the main deal-finding table down the page every time a batch of
new applications comes in with a pile of ambiguous fuzzy matches.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st
from sqlalchemy import select

from app.db.models import Application
from app.pipeline.site_linking import confirm_suggested_link, extract_postcode_district, reject_suggested_link
from app.ui.common import (
    aggregate_scheme_fields,
    bootstrap,
    credits_sidebar,
    get_db,
    pick_representative_application,
)
from app.ui.shell import empty_state, page_header, wide_canvas

bootstrap()
session, settings = get_db()

# Post-Sprint-4.5b hotfix: this data-review page was never given the
# page-scoped wide_canvas() override, so its side-by-side comparison rows
# were confined to the shared shell's 1200px default on wide viewports.
wide_canvas()

HOME_PAGE = Path(__file__).resolve().parents[1] / "pages" / "0_Explore.py"
st.page_link(HOME_PAGE, label="← Back to Explore", icon="🔙")

credits_sidebar(session, settings)

suggested = session.execute(
    select(Application).where(Application.site_link_method == "suggested_fuzzy", Application.site_id.is_(None))
).scalars().all()

page_header(
    f"Site Matching — {len(suggested)} awaiting review",
    "These couldn't be auto-linked with full confidence - compare the two portal pages below, then "
    "confirm if they're the same site or reject to keep them separate.",
    icon="🔗",
)

if not suggested:
    empty_state("Nothing to review right now", "Every suggested site link has already been resolved.", icon="✅")
    st.stop()

for app in suggested:
    candidate = app.suggested_site
    candidate_apps = list(candidate.applications) if candidate else []
    candidate_rep = pick_representative_application(candidate_apps) if candidate_apps else None

    district = extract_postcode_district(app.address)
    confidence_pct = f"{app.site_link_confidence:.0%}" if app.site_link_confidence else "n/a"
    st.markdown(
        f"**Suggested reason:** same postcode district ({district or 'n/a'}) "
        f"and {confidence_pct} address text similarity to the site below."
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**New application: {app.reference}**")
        st.markdown(app.address or "(no address)")
        if app.summary_url:
            st.markdown(f"[Open on planning portal]({app.summary_url})")
        merged = aggregate_scheme_fields([app])
        st.caption(f"Total units: {merged['total_units_final'] or 'not yet extracted'} | "
                   f"Development type: {merged['development_type'] or 'unknown'}")
    with col2:
        st.markdown(f"**Existing site: {', '.join(a.reference for a in candidate_apps) or 'unknown'}**")
        st.markdown(candidate.display_address if candidate else "(unknown)")
        if candidate_rep and candidate_rep.summary_url:
            st.markdown(f"[Open on planning portal]({candidate_rep.summary_url})")
        merged = aggregate_scheme_fields(candidate_apps)
        st.caption(f"Total units: {merged['total_units_final'] or 'not yet extracted'} | "
                   f"Development type: {merged['development_type'] or 'unknown'}")

    btn_col1, btn_col2, _ = st.columns([1, 1, 3])
    with btn_col1:
        if st.button("Confirm same site", key=f"confirm_{app.id}"):
            confirm_suggested_link(session, app)
            session.commit()
            st.rerun()
    with btn_col2:
        if st.button("Reject - different site", key=f"reject_{app.id}"):
            reject_suggested_link(session, app)
            session.commit()
            st.rerun()
    st.divider()
