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

from app.config import load_councils
from app.db.models import LocalPlanSite
from app.extraction.local_plan import assess_delivery_scope
from app.policy.site_view import build_site_policy_intelligence
from app.ui.allocation_selector import (
    FILTER_CHOICES,
    coverage_message,
    filter_allocations_by_image_status,
    format_allocation_option,
    sort_allocations,
)
from app.ui.common import (
    PROGRESSION_SIGNAL_LABELS,
    aggregate_scheme_fields,
    bootstrap,
    credits_sidebar,
    get_db,
    load_site_applications,
    render_visual_evidence,
)
from app.ui.shell import empty_state, page_header
from app.visuals.site_view import build_allocation_image_status, build_allocation_visual_evidence

bootstrap()
session, settings = get_db()

HOME_PAGE = Path(__file__).resolve().parents[1] / "pages" / "0_Explore.py"
st.page_link(HOME_PAGE, label="← Back to Explore", icon="🔙")

credits_sidebar(session, settings)

page_header(
    "Local Plan Sites",
    "Sites a council has identified for housing in its Local Plan, whether or not a planning application "
    "has been submitted yet. Sourced from whatever document the council publishes - there's no portal "
    "for this the way there is for applications, so coverage is council-by-council as each is added. "
    "A site in a DRAFT/emerging plan can still be added, resized, or dropped before adoption - status is "
    "shown against every row, never presented as final.",
    icon="📋",
)

sites = session.execute(select(LocalPlanSite)).scalars().all()
if not sites:
    empty_state(
        "No Local Plan data yet",
        "Run ingest_local_plan.py for a council to add its Local Plan allocations.",
        icon="📋",
    )
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
# Sprint 3E ("Joint Plan Support and Bury Allocation Reconciliation", Part
# 4) - keyed by allocation ID, never policy_reference. policy_reference is
# legitimately nullable AND non-unique (several allocations can share
# policy_reference=None, or - in principle - the same code across two
# different plans) - a dict keyed by it collapses every colliding
# allocation down to whichever was built last, silently showing that one
# row's status/progression signal for every other allocation that shared
# the key. allocation.id is the one thing guaranteed unique per row.
policy_rows = {row["allocation_id"]: row for row in build_site_policy_intelligence(filtered)}
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
    policy_row = policy_rows[s.id]

    rows.append({
        "Council": s.council_code,
        "Policy ref": s.policy_reference,
        "Site name": s.site_name,
        "Min. dwellings": s.minimum_dwellings,
        "Category": s.category,
        "Plan": f"{s.plan_name} ({s.plan_status})",
        # Allocation status is distinct from the Local Plan's own status
        # (Part 6 of the Policy Intelligence Foundation sprint) - never
        # collapse the two, and never show a draft allocation as adopted.
        "Allocation status": policy_row["allocation_raw_status"] or policy_row["allocation_status"] or "not yet classified",
        "Progression signal": PROGRESSION_SIGNAL_LABELS.get(policy_row["progression_signal"], PROGRESSION_SIGNAL_LABELS[None]),
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

st.subheader("Allocation detail")

# Deterministic order (council, reference, name, id) - an unordered SQL
# SELECT previously left the selectbox below defaulting to whichever
# allocation happened to come back first, almost always one with no image,
# silently burying the ones that actually have a confirmed map.
council_names = {code: cfg.name for code, cfg in load_councils().items()}
ordered_allocations = sort_allocations(filtered, council_names)

# One batched query for every allocation currently in view, never one
# query per allocation (Part 3 of the fix).
image_status = build_allocation_image_status(session, [s.id for s in ordered_allocations])

st.caption(coverage_message(ordered_allocations, image_status))

image_filter = st.selectbox("Filter by image availability", FILTER_CHOICES, index=0)
selector_options = filter_allocations_by_image_status(ordered_allocations, image_status, image_filter)

selected = st.selectbox(
    "Choose an allocation to view its map/visual evidence",
    selector_options,
    index=None,
    placeholder="Select an allocation",
    format_func=lambda s: format_allocation_option(s, image_status.get(s.id, "none")),
)
if selected is not None:
    st.markdown(f"**{selected.policy_reference or '(no ref)'} — {selected.site_name}**")
    render_visual_evidence(
        build_allocation_visual_evidence(session, selected.id),
        missing_message="No confirmed allocation map image has been extracted yet.",
        expander_label="Other visual evidence",
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
