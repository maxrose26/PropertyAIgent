"""Housing sites allocated in a council's Local Plan - a leading-indicator
layer distinct from everything else in this app, since these are sites
identified BEFORE any planning application exists for them at all. See
app.extraction.local_plan and app.db.models.LocalPlanSite.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pandas as pd
import pydeck as pdk
import streamlit as st
from sqlalchemy import select

from app.db.models import LocalPlanSite
from app.extraction.local_plan import assess_delivery_scope
from app.ui.common import aggregate_scheme_fields, bootstrap, credits_sidebar, get_db, load_site_applications

st.set_page_config(page_title="Local Plan sites - UK Planning Deal Finder", layout="wide")

bootstrap()
session, settings = get_db()

HOME_PAGE = Path(__file__).resolve().parents[1] / "streamlit_app.py"
st.page_link(HOME_PAGE, label="← Back to search", icon="🔙")

credits_sidebar(session, settings)

st.title("Local Plan allocated sites")
st.caption(
    "Sites a council has identified for housing in its Local Plan, whether or not a planning application "
    "has been submitted yet. Sourced from whatever document the council publishes - there's no portal "
    "for this the way there is for applications, so coverage is council-by-council as each is added. "
    "A site in a DRAFT/emerging plan can still be added, resized, or dropped before adoption - status is "
    "shown against every row, never presented as final."
)

sites = session.execute(select(LocalPlanSite)).scalars().all()
if not sites:
    st.info("No Local Plan data ingested yet. Run ingest_local_plan.py for a council to add one.")
    st.stop()

with st.sidebar:
    st.header("Filters")
    councils = st.multiselect(
        "Council", sorted({s.council_code for s in sites}),
        default=sorted({s.council_code for s in sites}),
    )
    show_only_unmatched = st.checkbox(
        "Only sites with no application yet", value=False,
        help="The clearest pre-application opportunity signal - a site the council has already earmarked "
             "for housing, where nobody has submitted anything yet.",
    )

filtered = [s for s in sites if s.council_code in councils]
if show_only_unmatched:
    filtered = [s for s in filtered if not s.matched_site_id]

matched_count = sum(1 for s in filtered if s.matched_site_id)
st.subheader(f"{len(filtered)} sites ({matched_count} already have an application, {len(filtered) - matched_count} don't)")

geo_points = []
rows = []
for s in filtered:
    delivery_note = None
    if s.matched_site_id:
        matched_apps = load_site_applications(session, s.matched_site_id)
        merged = aggregate_scheme_fields(matched_apps)
        scope = assess_delivery_scope(s.minimum_dwellings, merged.get("total_units_final"))
        delivery_note = scope["note"] if scope["status"] != "unknown" else None

    plan_page_url = (
        f"{s.source_document_url}#page={s.source_page}" if s.source_document_url and s.source_page else None
    )

    rows.append({
        "Council": s.council_code,
        "Policy ref": s.policy_reference,
        "Site name": s.site_name,
        "Min. dwellings": s.minimum_dwellings,
        "Category": s.category,
        "Plan": f"{s.plan_name} ({s.plan_status})",
        "Application status": "Has application" if s.matched_site_id else "No application yet",
        "Match confidence": f"{s.match_confidence:.0f}%" if s.match_confidence else None,
        "Delivery vs. allocation": delivery_note,
        "Plan page": plan_page_url,
    })

    if s.latitude and s.longitude:
        geo_points.append({
            "latitude": s.latitude,
            "longitude": s.longitude,
            "Site name": s.site_name,
            "Policy ref": s.policy_reference,
            "Min. dwellings": s.minimum_dwellings or 0,
            "status": "Has application" if s.matched_site_id else "No application yet",
            # Gold for the genuinely new signal (no application yet), a
            # duller grey for ones already visible as a normal scheme
            # marker elsewhere - the point of this map is to make the FIRST
            # group easy to spot, not to duplicate the main map.
            "fill_color": [0, 0, 0, 0] if s.matched_site_id else [255, 191, 0, 220],
            "line_color": [120, 120, 120, 160] if s.matched_site_id else [153, 101, 0, 255],
        })

df = pd.DataFrame(rows)
st.dataframe(
    df, use_container_width=True, hide_index=True,
    column_config={"Plan page": st.column_config.LinkColumn(display_text="Open in plan →")},
)

st.caption(
    "Cross-referencing is approximate (a short site-plan name fuzzy-matched against a full scraped "
    "address) - a low match confidence is worth checking by eye before relying on it."
)

if geo_points:
    st.subheader("Map")
    st.caption(
        "🟡 Gold = allocated, no application yet (the pre-application opportunity). "
        "Grey outline only = already has an application (shown as a normal marker on the home page map too). "
        "Not every site is geocoded - coverage is best-effort, not complete."
    )
    geo_df = pd.DataFrame(geo_points)
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=geo_df,
        get_position=["longitude", "latitude"],
        get_radius=200,
        get_fill_color="fill_color",
        get_line_color="line_color",
        line_width_min_pixels=3,
        stroked=True,
        pickable=True,
    )
    view_state = pdk.ViewState(
        latitude=geo_df["latitude"].mean(), longitude=geo_df["longitude"].mean(), zoom=10,
    )
    st.pydeck_chart(pdk.Deck(
        layers=[layer], initial_view_state=view_state, map_provider="carto", map_style="road",
        tooltip={"text": "{Policy ref} {Site name}\n{Min. dwellings} dwellings\n{status}"},
    ))
else:
    st.info("No geocoded sites to show on a map yet.")
