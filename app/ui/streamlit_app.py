"""Lead browser.

    streamlit run app/ui/streamlit_app.py

Single-user viewer over the deal_finder.db built by app.pipeline.run_weekly.
Schemes are shown at site level (see app.pipeline.site_linking) - multiple
planning applications for the same physical site are consolidated into one
row, with an application-history expander for the underlying references.
This is the home page: search/filter + map. Click a site (map dot, or the
"Open scheme" button in the table) to jump to its own detail page.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import pydeck as pdk
import streamlit as st
from openai import OpenAI
from sqlalchemy import func, select

from app.db.models import Application, Site
from app.pipeline.lapse_tracking import (
    DECISION_STATUS_LABELS,
    LAPSE_STATUS_COLORS,
    classify_decision_status,
    parse_portal_date,
)
from app.search.query_parser import SearchFilters, compute_aggregate_answer, parse_query
from app.ui.common import (
    BUILD_STATUS_LABELS,
    LAPSE_STATUS_LABELS,
    aggregate_scheme_fields,
    bootstrap,
    compute_lapse_status,
    credits_sidebar,
    get_db,
    load_site_applications,
    load_watchlist_applications,
    pick_representative_application,
    render_scheme_detail,
)
from app.reporting.pdf_report import compute_aggregate_stats, generate_narrative, render_pdf
from app.ui.housing_type import HOUSING_TYPE_COLORS, HOUSING_TYPE_LABELS, classify_housing_type, housing_type_note

st.set_page_config(page_title="UK Planning Deal Finder", layout="wide")

council_regions = {code: cfg.region for code, cfg in bootstrap().items()}
session, settings = get_db()

st.title("UK Planning Deal Finder")

credits_sidebar(session, settings)

# --- Suggested site links awaiting review -----------------------------
# Full review UI lives on its own page (pages/2_Review_Site_Links.py) - a
# batch of new applications can produce dozens of these, which used to push
# the actual deal-finding table off the top of the page every time.

suggested_count = session.execute(
    select(func.count(Application.id)).where(
        Application.site_link_method == "suggested_fuzzy", Application.site_id.is_(None)
    )
).scalar()

if suggested_count:
    REVIEW_PAGE = Path(__file__).resolve().parent / "pages" / "2_Review_Site_Links.py"
    st.page_link(REVIEW_PAGE, label=f"{suggested_count} suggested site links awaiting review →", icon="🔗")

# --- Watchlist: screening/scoping opinions ----------------------------------
# Not qualifying schemes in their own right (no real applicant/documents
# behind them yet), so kept out of the main results below - but a genuine
# early signal that a real scheme is likely coming for that site, worth
# knowing about rather than discarding entirely.

watchlist_apps = load_watchlist_applications(session)
if watchlist_apps:
    with st.expander(f"👀 {len(watchlist_apps)} screening/scoping opinions to watch", expanded=False):
        st.caption(
            "These are requests to determine whether an Environmental Impact Assessment is needed - not "
            "substantive applications yet, so no unit/affordable/developer data is extracted for them. Often "
            "precedes the real application by months."
        )
        watchlist_rows = [{
            "Council": a.council_code,
            "Reference": a.reference,
            "Address": a.address,
            "Proposal": (a.proposal or "")[:200],
            "Est. units": a.estimated_unit_count,
            "Received": a.application_received,
            "Portal URL": a.summary_url,
        } for a in sorted(watchlist_apps, key=lambda a: parse_portal_date(a.application_received), reverse=True)]
        st.dataframe(
            pd.DataFrame(watchlist_rows), use_container_width=True, hide_index=True,
            column_config={"Portal URL": st.column_config.LinkColumn()},
        )

# --- Main site-level table --------------------------------------------------

sites = session.execute(select(Site)).scalars().all()
if not sites:
    st.info("No schemes yet. Run: python -m app.pipeline.run_weekly --council bury")
    st.stop()

site_applications: dict[int, list[Application]] = {}
rows = []
for site in sites:
    apps = load_site_applications(session, site.id)
    if not apps:
        continue
    site_applications[site.id] = apps

    rep_app = pick_representative_application(apps)
    merged = aggregate_scheme_fields(apps)
    # site.applications (the raw relationship), not the display-filtered
    # `apps` from load_site_applications - that filter drops administrative
    # applications (condition discharge, variation of condition) as noise
    # for the "Application history" list, but those are exactly the
    # evidence classify_build_status's portal-filing signal depends on to
    # detect "underway". Confirmed a real case: a site with 30 linked
    # applications (10+ real condition-discharge filings spanning years)
    # showed "Permission may have lapsed" here because compute_lapse_status
    # never saw any of that evidence - only the 3 applications that survived
    # the qualifying-scheme filter.
    lapse = compute_lapse_status(site.applications, site)
    housing_type = classify_housing_type(merged["development_type"], merged["housing_typology"])
    housing_note = housing_type_note(merged["development_type"], merged["housing_typology"])
    decision_status = classify_decision_status(rep_app.decision if rep_app else None, rep_app.status if rep_app else None)

    rows.append({
        "site_id": site.id,
        "Council": site.council_code,
        "Region": council_regions.get(site.council_code),
        "Address": site.display_address,
        "Applications": len(apps),
        "References": ", ".join(sorted(a.reference for a in apps)),
        "Total Units": merged["total_units_final"],
        # Kept as a separate flag rather than folding into "Total Units"
        # itself (e.g. "~200 (est.)") - the min/max unit filters below
        # compare "Total Units" numerically, so it needs to stay a plain
        # number. True whenever the figure came from the portal search
        # listing's own regex estimate (see aggregate_scheme_fields) rather
        # than AI-verified against the actual application documents.
        "Units Estimated": merged.get("total_units_is_estimated", False),
        "Affordable Units": merged["affordable_units_final"],
        "Private Units": merged["private_units_final"],
        "Affordable %": merged["affordable_percentage_final"],
        "Tenure Split": merged["affordable_tenure_split_final"],
        "Development Type": merged["development_type"],
        "Housing Type": HOUSING_TYPE_LABELS[housing_type],
        "housing_type": housing_type,
        # None most of the time - only set when classify_housing_type
        # reclassified a lopsided (>=80% one type) mix away from "Mixed",
        # so the real split doesn't just disappear.
        "Housing Type Note": housing_note,
        "Developer": merged["developer"],
        "Applicant Company": merged["applicant_company"],
        "Landowner": merged["landowner"],
        "Planning Agent": merged["planning_agent"],
        "Housing Association": merged["housing_association"],
        "Registered Provider": merged["registered_provider"],
        "Latest Status": rep_app.status if rep_app else None,
        "Decision Status": DECISION_STATUS_LABELS[decision_status],
        "decision_status": decision_status,
        "Decision Date": lapse["granted_app"].decision_issued_date if lapse["granted_app"] else None,
        "Build Status": BUILD_STATUS_LABELS[lapse["build_status"]],
        "build_status": lapse["build_status"],
        "Lapse Risk": LAPSE_STATUS_LABELS[lapse["status"]],
        "lapse_status": lapse["status"],
        "Data Quality": merged["data_quality_status"] or "Not yet extracted",
        "Needs Review": not merged["core_intelligence_complete"],
        "Portal URL": rep_app.summary_url if rep_app else None,
        "latitude": site.latitude,
        "longitude": site.longitude,
    })
df = pd.DataFrame(rows)

# --- Natural language search -------------------------------------------

st.subheader("Search")
# A plain st.text_input reruns (and re-parses via a slow OpenAI call) on
# every keystroke - confirmed this could show a confusing "0 sites" flash
# from a previous, incomplete query while the user was still mid-typing and
# the real parse for the finished sentence hadn't landed yet. A form only
# submits on Enter/button click, so parsing only happens once per finished query.
with st.form("nl_search_form"):
    nl_query = st.text_input(
        "Describe what you're looking for",
        placeholder='e.g. "projects with 50+ affordable units in Greater Manchester which haven\'t been completed"',
    )
    nl_submitted = st.form_submit_button("Search")

nl_filters: SearchFilters | None = None
if nl_query:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        st.warning("OPENAI_API_KEY not set - can't parse natural language search.")
    elif nl_submitted or st.session_state.get("_last_nl_query") == nl_query:
        if nl_submitted:
            client = OpenAI(api_key=api_key)
            st.session_state["_last_nl_filters"] = parse_query(client, nl_query)
            st.session_state["_last_nl_query"] = nl_query
        nl_filters = st.session_state.get("_last_nl_filters")
        if nl_filters:
            st.caption(f"Interpreted as: {nl_filters.interpretation_notes}")

with st.sidebar:
    st.header("Filters")
    councils = st.multiselect("Council", sorted(df["Council"].unique()), default=list(df["Council"].unique()))
    housing_types = st.multiselect(
        "Housing type", list(HOUSING_TYPE_LABELS.values()), default=list(HOUSING_TYPE_LABELS.values()),
    )
    min_units = st.number_input("Min total units", min_value=0, value=0)
    min_affordable = st.number_input("Min affordable units", min_value=0, value=0)
    exclude_completed = st.checkbox("Hide completed sites", value=False)
    hide_needs_review = st.checkbox("Hide schemes needing manual review", value=False)
    not_commenced_only = st.checkbox(
        "Show only schemes not yet commenced", value=False,
        help="Full permission granted, but no construction activity detected - the developer has the "
             "right to build but isn't yet, whether or not the 3-year deadline is close. Excludes "
             "schemes still awaiting a decision (not an acquisition opportunity yet) and ones already "
             "confirmed underway.",
    )

filtered = df[df["Council"].isin(councils) & df["Housing Type"].isin(housing_types)]
filtered = filtered[filtered["Total Units"].fillna(0) >= min_units]
filtered = filtered[filtered["Affordable Units"].fillna(0) >= min_affordable]
if exclude_completed:
    filtered = filtered[filtered["build_status"] != "complete"]
if hide_needs_review:
    filtered = filtered[~filtered["Needs Review"]]
if not_commenced_only:
    # Granted (excludes not_granted) but not confirmed underway - "unknown"
    # is included too (still granted, decision date just couldn't be
    # parsed), only "underway" and "not_granted" are excluded.
    filtered = filtered[~filtered["lapse_status"].isin(["not_granted", "underway"])]

if nl_filters:
    # `if nl_filters.X:` treats a legitimate 0 as "not set" and silently
    # skips the filter - confirmed a real case: "no affordable units" parsed
    # correctly to max_affordable_units=0, but a truthy check would have
    # dropped that constraint entirely and shown every 50+ unit scheme
    # regardless of affordable count, the opposite of what was asked.
    if nl_filters.region:
        filtered = filtered[filtered["Region"] == nl_filters.region]
    if nl_filters.council_codes:
        filtered = filtered[filtered["Council"].isin(nl_filters.council_codes)]
    if nl_filters.min_total_units is not None:
        filtered = filtered[filtered["Total Units"].fillna(0) >= nl_filters.min_total_units]
    if nl_filters.max_total_units is not None:
        filtered = filtered[filtered["Total Units"].fillna(0) <= nl_filters.max_total_units]
    if nl_filters.min_affordable_units is not None:
        filtered = filtered[filtered["Affordable Units"].fillna(0) >= nl_filters.min_affordable_units]
    if nl_filters.max_affordable_units is not None:
        filtered = filtered[filtered["Affordable Units"].fillna(0) <= nl_filters.max_affordable_units]
    if nl_filters.development_types:
        filtered = filtered[filtered["Development Type"].isin(nl_filters.development_types)]
    if nl_filters.exclude_completed:
        filtered = filtered[filtered["build_status"] != "complete"]
    if nl_filters.statuses:
        # Confirmed a real case: "planning approved" parsed correctly into
        # structured filters (statuses=["granted"]), but this branch didn't
        # exist at all - the field was captured and then silently discarded,
        # so a query for approved-only schemes returned everything.
        filtered = filtered[filtered["decision_status"].isin(nl_filters.statuses)]
    if nl_filters.needs_review is not None:
        filtered = filtered[filtered["Needs Review"] == nl_filters.needs_review]

if nl_filters and nl_filters.query_type == "aggregate" and nl_filters.aggregate_group_by:
    # Ranking is computed in pandas against the real (already region/council-
    # scoped) data above - never asked of the LLM directly, which can't
    # reliably count/sum across rows and would risk a confidently wrong
    # answer instead of a grounded one.
    answer = compute_aggregate_answer(filtered, nl_filters)
    if answer is None:
        st.warning("No data available to answer that - try a less specific scope or a different field.")
    else:
        st.success(answer.headline)
        st.dataframe(answer.ranked, use_container_width=True, hide_index=True)
        # An answer on its own is a dead end - narrow the map/table below
        # (which already support click-through to full scheme detail,
        # map plotting, and CSV export) down to exactly the schemes behind
        # this ranking, instead of leaving them showing every site.
        filtered = filtered[filtered[answer.group_by_column].isin(answer.ranked[answer.group_by_column])]
        st.caption(f"Showing the {len(filtered)} scheme(s) behind this ranking below.")
    st.divider()

st.subheader(f"{len(filtered)} sites")


def build_report_rows(site_ids: list[int]) -> list[dict]:
    """Shared by the "download everything currently filtered" button below
    and the manual row-selection report further down - same row shape
    either way, just a different set of site_ids."""
    rows_out = []
    for site_id in site_ids:
        site = session.get(Site, site_id)
        apps = site_applications[site_id]
        rep_app = pick_representative_application(apps)
        merged = aggregate_scheme_fields(apps)
        lapse = compute_lapse_status(site.applications, site)  # see main loop above for why not the filtered `apps`
        decision_status = classify_decision_status(rep_app.decision if rep_app else None, rep_app.status if rep_app else None)
        rows_out.append({
            "Council": site.council_code,
            "Region": council_regions.get(site.council_code),
            "Address": site.display_address,
            "References": ", ".join(sorted(a.reference for a in apps)),
            "Total Units": merged["total_units_final"],
            "Units Estimated": merged.get("total_units_is_estimated", False),
            "Affordable Units": merged["affordable_units_final"],
            "Private Units": merged["private_units_final"],
            "Affordable %": merged["affordable_percentage_final"],
            "Tenure Split": merged["affordable_tenure_split_final"],
            "Development Type": merged["development_type"],
            "Housing Type": HOUSING_TYPE_LABELS[classify_housing_type(merged["development_type"], merged["housing_typology"])],
            "Housing Type Note": housing_type_note(merged["development_type"], merged["housing_typology"]),
            "Developer": merged["developer"],
            "Applicant Company": merged["applicant_company"],
            "Landowner": merged["landowner"],
            "Planning Agent": merged["planning_agent"],
            "Housing Association": merged["housing_association"],
            "Registered Provider": merged["registered_provider"],
            "RP Status": merged["registered_provider_status"],
            "Latest Status": rep_app.status if rep_app else None,
            "Decision": rep_app.decision if rep_app else None,
            "Decision Status": DECISION_STATUS_LABELS[decision_status],
            "decision_status": decision_status,
            "Decision Date": lapse["granted_app"].decision_issued_date if lapse["granted_app"] else None,
            "Build Status": BUILD_STATUS_LABELS[lapse["build_status"]],
            "build_status": lapse["build_status"],
            "Lapse Risk": LAPSE_STATUS_LABELS[lapse["status"]],
            "lapse_status": lapse["status"],
            "Commencement Deadline": lapse["deadline"].strftime("%d %b %Y") if lapse["deadline"] else None,
            "Data Quality": merged["data_quality_status"],
            "Portal URL": rep_app.summary_url if rep_app else None,
            # Per-application breakdown for the PDF report only (dropped
            # before CSV export - a list-of-dicts cell doesn't serialise
            # cleanly to a flat row). Each site can have several linked
            # applications (see app.pipeline.site_linking) and the site-level
            # fields above are already merged/reconciled across all of
            # them - this lets the PDF also show what each individual
            # application actually proposed.
            "Applications Detail": [{
                "Reference": a.reference,
                "Received": a.application_received,
                "Decision": a.decision or a.status,
                "Proposal": (a.proposal or "")[:220],
            } for a in sorted(apps, key=lambda a: parse_portal_date(a.application_received), reverse=True)],
        })
    return rows_out


if len(filtered) > 0:
    all_filtered_rows = build_report_rows(list(filtered["site_id"]))
    # decision_status/lapse_status are the raw internal keys PDF generation
    # groups on (see app.reporting.pdf_report) - redundant for a human
    # reading the CSV once "Decision Status"/"Lapse Risk" are already columns.
    # Applications Detail is a list-of-dicts per row (per-application
    # breakdown, PDF-only) that doesn't serialise cleanly to a flat CSV cell.
    all_filtered_report_df = pd.DataFrame(all_filtered_rows).drop(
        columns=["decision_status", "lapse_status", "build_status", "Applications Detail"]
    )

    col_csv, col_pdf = st.columns(2)
    with col_csv:
        st.download_button(
            f"Export as CSV ({len(filtered)} sites)",
            data=all_filtered_report_df.to_csv(index=False).encode("utf-8"),
            file_name="scheme_report.csv",
            mime="text/csv",
            key="download_all_filtered_report",
        )
    with col_pdf:
        # Two-step (generate, then download) rather than eagerly building
        # the PDF on every rerun like the CSV above - this one makes a real
        # OpenAI call, which shouldn't fire on every filter tweak/page
        # interaction, only when the user actually wants the report.
        if st.button(f"Generate PDF summary report ({len(filtered)} sites)", key="generate_pdf_report"):
            openai_key = os.getenv("OPENAI_API_KEY")
            if not openai_key:
                st.error("OPENAI_API_KEY not set - can't generate the AI-written summary.")
            else:
                with st.spinner("Analysing schemes and writing the report..."):
                    stats = compute_aggregate_stats(filtered)
                    narrative = generate_narrative(OpenAI(api_key=openai_key), stats, search_description=nl_query or None)
                    st.session_state["_pdf_report_bytes"] = render_pdf(all_filtered_rows, stats, narrative, search_description=nl_query or None)
                st.rerun()

    if st.session_state.get("_pdf_report_bytes"):
        st.download_button(
            "Download PDF summary report",
            data=st.session_state["_pdf_report_bytes"],
            file_name="scheme_summary_report.pdf",
            mime="application/pdf",
            key="download_pdf_report",
        )


def open_scheme(site_id: int) -> None:
    """Navigate to the scheme detail page for site_id. Streamlit pages are
    plain reruns, not real browser navigation, but st.switch_page gives the
    same effect the user wants - a distinct page, not just a scroll target
    on this one. query_params must be passed to switch_page itself, not set
    beforehand - switch_page clears non-embed query params by default."""
    st.switch_page("pages/1_Scheme_Detail.py", query_params={"site_id": str(site_id)})


map_points = filtered.dropna(subset=["latitude", "longitude"])
if not map_points.empty:
    # True satellite/aerial imagery needs a Mapbox or Google token - pydeck's
    # own "satellite" style keyword silently resolves to nothing (404s) on
    # the free CARTO provider Streamlit uses by default, and a custom raster
    # style dict is only accepted when map_provider="mapbox" too, so without
    # a token there's no free imagery basemap option here. Offer CARTO's
    # free styles as a manual choice; add Satellite only if a Mapbox key
    # ever gets added.
    has_mapbox_key = bool(os.getenv("MapboxAccessToken") or os.getenv("MAPBOX_API_KEY"))
    style_options = {"Road": "road", "Light": "light", "Dark": "dark"}
    if has_mapbox_key:
        style_options["Satellite"] = "satellite"
    map_style_label = st.radio("Map style", list(style_options.keys()), horizontal=True, key="map_style_choice")
    chosen_style = style_options[map_style_label]

    # Fill = planning status, outline ring = housing type - two independent
    # pydeck-native channels on the same marker, rather than picking one
    # dimension to show at a time. See LAPSE_STATUS_COLORS/HOUSING_TYPE_COLORS
    # for the palettes and the caption below the map for the legend.
    map_points = map_points.assign(
        fill_color=map_points["lapse_status"].map(LAPSE_STATUS_COLORS),
        line_color=map_points["housing_type"].map(HOUSING_TYPE_COLORS),
        # pydeck's tooltip template does plain {ColumnName} substitution with
        # no conditional logic, so a null note would otherwise print the
        # literal text "None" on every scheme without one - collapse to an
        # empty string instead, only a real note adds a visible line.
        housing_note_line=map_points["Housing Type Note"].map(lambda n: f"\n⚠️ {n}" if n else ""),
    )

    layer = pdk.Layer(
        "ScatterplotLayer",
        id="sites",
        data=map_points,
        get_position=["longitude", "latitude"],
        get_radius=180,
        get_fill_color="fill_color",
        get_line_color="line_color",
        line_width_min_pixels=3,
        stroked=True,
        pickable=True,
        auto_highlight=True,
        highlight_color=[255, 255, 0, 255],
    )
    view_state = pdk.ViewState(
        latitude=map_points["latitude"].mean(),
        longitude=map_points["longitude"].mean(),
        zoom=9,
    )
    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_provider="mapbox" if chosen_style == "satellite" else "carto",
        map_style=chosen_style,
        tooltip={
            # Address/reference are redundant with the click-through, and not
            # useful for a quick scan while hovering - lead with the figures
            # that actually help decide whether to click in.
            "text": "{Total Units} units ({Housing Type})\n"
                    "Affordable: {Affordable Units} ({Affordable %}%)\n"
                    "Status: {Latest Status} | Lapse risk: {Lapse Risk}"
                    "{housing_note_line}\n"
                    "Click to open scheme details"
        },
    )
    map_event = st.pydeck_chart(deck, on_select="rerun", selection_mode="single-object", key="site_map")

    st.caption(
        "**Pin fill = planning status:** "
        + " · ".join(
            f"<span style='color:rgb({r},{g},{b})'>●</span> {LAPSE_STATUS_LABELS[status]}"
            for status, (r, g, b, _a) in LAPSE_STATUS_COLORS.items()
        ),
        unsafe_allow_html=True,
    )
    st.caption(
        "**Ring outline = housing type:** "
        + " · ".join(
            f"<span style='color:rgb({r},{g},{b})'>◯</span> {HOUSING_TYPE_LABELS[key]}"
            for key, (r, g, b, _a) in HOUSING_TYPE_COLORS.items()
        ),
        unsafe_allow_html=True,
    )

    selected_objects = []
    if map_event is not None:
        objects_by_layer = map_event["selection"]["objects"]
        if objects_by_layer:
            selected_objects = objects_by_layer.get("sites", [])
    if selected_objects:
        open_scheme(selected_objects[0].get("site_id"))

table_display = filtered.drop(
    columns=["site_id", "latitude", "longitude", "lapse_status", "housing_type", "decision_status", "build_status"]
).reset_index(drop=True)
table_event = st.dataframe(
    table_display,
    use_container_width=True,
    column_config={"Portal URL": st.column_config.LinkColumn()},
    on_select="rerun",
    selection_mode="multi-row",
    key="sites_table",
)

selected_site_ids: list[int] = []
if table_event is not None:
    selected_rows = table_event["selection"]["rows"]
    # table_display was reset_index'd to line up 1:1 with filtered's row
    # order, so selected positions map straight back to site_id.
    selected_site_ids = [int(sid) for sid in filtered.iloc[selected_rows]["site_id"]]

if len(selected_site_ids) == 1:
    st.divider()
    selected_site = session.get(Site, selected_site_ids[0])
    render_scheme_detail(session, settings, selected_site, site_applications[selected_site_ids[0]])

if selected_site_ids:
    st.divider()
    report_df = pd.DataFrame(build_report_rows(selected_site_ids)).drop(
        columns=["decision_status", "lapse_status", "build_status", "Applications Detail"]
    )
    st.download_button(
        f"Export as CSV ({len(selected_site_ids)} selected scheme{'s' if len(selected_site_ids) != 1 else ''})",
        data=report_df.to_csv(index=False).encode("utf-8"),
        file_name="scheme_report.csv",
        mime="text/csv",
        key="download_selected_report",
    )

st.divider()
st.caption("Or get a shareable link to a specific scheme:")

options = {f"{r['References']} - {r['Address']}": r["site_id"] for _, r in filtered.iterrows()}
if options:
    col1, col2 = st.columns([4, 1])
    with col1:
        selected_label = st.selectbox("Select a site", list(options.keys()), label_visibility="collapsed")
    with col2:
        if st.button("Open scheme details →", use_container_width=True):
            open_scheme(options[selected_label])
