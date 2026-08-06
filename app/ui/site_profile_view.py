"""The flagship Site Profile rendering (Sprint 4.4, "Flagship Site Profile") -
a tabbed, card-based experience reached ONLY from the dedicated Scheme Detail
page (app/ui/pages/1_Scheme_Detail.py). Deliberately separate from
app.ui.common.render_scheme_detail, which stays completely unchanged and keeps
serving Explore's inline row-expansion (see that function's own docstring) -
per this sprint's explicit "do not redesign Explore" scope restriction.

Data assembly lives in app.reporting.site_profile (a pure module); this file
is presentation only, reusing app.ui.shell's design-system components and
app.ui.common's existing pure helpers (aggregate_scheme_fields,
pick_representative_application, render_companies_and_contacts) rather than
re-implementing any of them.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.db.models import Application, Site
from app.pipeline.lapse_tracking import (
    classify_decision_status,
    compute_lapse_status,
    parse_portal_date,
)
from app.pipeline.phase_tracking import PHASE_STATUS_LABELS, build_phase_breakdown, summarize_phase_units
from app.reporting.site_profile import build_site_profile
from app.ui.common import (
    aggregate_scheme_fields,
    pick_representative_application,
    render_companies_and_contacts,
)
from app.ui.shell import (
    ai_status_summary_view,
    evidence_gap_panel,
    opportunity_position_card,
    section_header,
    site_profile_header,
    stat_tile,
    timeline,
    visual_evidence_gallery,
    wide_canvas,
)

_DECISION_GROUP_ORDER = ["granted", "not_yet_decided", "refused", "withdrawn"]
_DECISION_GROUP_LABELS = {
    "granted": "Approved",
    "not_yet_decided": "Submitted / pending",
    "refused": "Refused",
    "withdrawn": "Withdrawn",
}


def _applications_dataframe(apps: list[Application]) -> pd.DataFrame:
    rows = [{
        "Reference": a.reference, "Type": a.application_type, "Status": a.status,
        "Decision": a.decision, "Received": a.application_received,
        "Portal URL": a.summary_url,
    } for a in sorted(apps, key=lambda a: parse_portal_date(a.application_received), reverse=True)]
    return pd.DataFrame(rows)


def _render_planning_position(site: Site, apps: list[Application], view: dict) -> None:
    """Part 7 - applications grouped by decision status (never one flat
    list), phase/plot breakdown, and commencement/build status - clearly
    distinguishing submitted/pending, approved, refused, withdrawn,
    commenced and lapsed/approaching-lapse, never inferring a lapse date
    where the required decision date is missing (compute_lapse_status_public
    already returns deadline=None in that case, and this view only ever
    renders what it's given)."""
    header = view["header"]
    lapse_label = header["lapse_status_label"]
    if lapse_label:
        st.markdown(f"**Commencement status:** {lapse_label}")
    elif header["decision_status_label"]:
        st.markdown(f"**Decision status:** {header['decision_status_label']}")

    phase_breakdown = build_phase_breakdown(site.applications)
    if phase_breakdown:
        section_header("Phase & plot breakdown", icon="🏗️")
        unit_summary = summarize_phase_units(phase_breakdown)
        for bucket_key, label in (("underway", "Under construction"), ("approved_not_started", "Approved, not yet started"), ("not_yet_approved", "Awaiting decision")):
            bucket = unit_summary[bucket_key]
            if bucket["phase_count"]:
                unit_bit = f"{bucket['units']:,} units" if bucket["units"] else "unit count not confirmed"
                st.caption(f"**{label}:** {bucket['phase_count']} phase(s), {unit_bit}")
        phase_rows = [{
            "Phase / plot": p["label"],
            "Units": p.get("unit_count") or ("—" if p["kind"] == "phase" else ""),
            "Status": PHASE_STATUS_LABELS[p["status"]],
            "Applications": len(p["applications"]),
        } for p in phase_breakdown]
        st.dataframe(pd.DataFrame(phase_rows), use_container_width=True, hide_index=True)

    section_header("Applications", icon="📋")
    groups: dict[str, list[Application]] = {}
    for a in apps:
        groups.setdefault(classify_decision_status(a.decision, a.status), []).append(a)
    for key in _DECISION_GROUP_ORDER:
        group_apps = groups.get(key)
        if not group_apps:
            continue
        with st.expander(f"{_DECISION_GROUP_LABELS[key]} ({len(group_apps)})", expanded=key == "granted"):
            st.dataframe(
                _applications_dataframe(group_apps), use_container_width=True, hide_index=True,
                column_config={"Portal URL": st.column_config.LinkColumn()},
            )


def _render_policy_position(view: dict) -> None:
    """Part 8 - full allocation detail plus the council's own five-year
    housing supply context where verified, using the same responsible,
    hedged wording established in Council Intelligence (a low supply
    figure is highlighted as policy pressure, never as proof this site
    will get permission)."""
    policy = view["policy_position"]
    if policy["council_supply"]:
        supply = policy["council_supply"]
        state = "warning" if supply["years"] < 5.0 else "ok"
        stat_tile(
            "Council five-year housing supply", f"{supply['years']:g} years ({supply['plan_name']})",
            caption="Below five years — may indicate policy pressure, not a prediction of this site's outcome." if state == "warning" else None,
        )
    if policy["no_allocation_message"]:
        st.info(policy["no_allocation_message"])
        return
    for row in policy["allocations"]:
        capacity_bits = [
            f"{row[k]:,} {label}" for k, label in (
                ("minimum_dwellings", "min"), ("indicative_capacity", "indicative"), ("maximum_capacity", "max"),
            ) if row[k]
        ]
        capacity_text = " / ".join(capacity_bits) if capacity_bits else "dwelling count not stated"
        with st.container(border=True):
            st.markdown(f"**{row['allocation_reference'] or '(no ref)'} — {row['allocation_name']}**")
            st.caption(f"{row['plan_name']} ({row['plan_raw_status'] or row['plan_status'] or 'status unknown'})")
            st.write(f"{capacity_text} · {row['category'] or 'no category given'}")
            if row["progression_signal"]:
                st.caption(f"Progression: {row['progression_signal']}")
            if row["source_document_url"] and row["source_page"]:
                st.caption(f"[Open plan page {row['source_page']}]({row['source_document_url']}#page={row['source_page']})")


def render_site_profile(session, settings, site: Site, apps: list[Application]) -> None:
    """The flagship Site Profile entry point (Sprint 4.4) - called only
    from app/ui/pages/1_Scheme_Detail.py."""
    wide_canvas()

    rep_app = pick_representative_application(apps)
    merged = aggregate_scheme_fields(apps)
    lapse = compute_lapse_status(site.applications, site)
    decision_status = classify_decision_status(rep_app.decision, rep_app.status) if rep_app else None
    phase_breakdown = build_phase_breakdown(site.applications)

    view = build_site_profile(
        session, site, apps, merged=merged, rep_app=rep_app, lapse=lapse,
        phase_breakdown=phase_breakdown, decision_status=decision_status,
    )

    # "Back to Explore" is already rendered once, above the site-resolution
    # logic, in app/ui/pages/1_Scheme_Detail.py (covers every state -
    # loading, error, and this success path alike) - not repeated here.
    col_council, col_alloc = st.columns(2)
    with col_council:
        st.page_link(
            "pages/6_Council_Intelligence_Detail.py", label="Open Council Intelligence →",
            query_params={"council": site.council_code},
        )
    with col_alloc:
        st.page_link(
            "pages/3_Local_Plan_Sites.py", label="View Local Plan Sites →",
            query_params={"council": site.council_code},
        )

    site_profile_header(view["header"])

    if site.excluded:
        st.error(
            f"🚫 Excluded from results — {site.excluded_reason or 'marked not a genuine residential scheme'} "
            f"({site.excluded_at.strftime('%d %b %Y') if site.excluded_at else 'date unknown'})"
        )

    tab_overview, tab_planning, tab_policy, tab_visual, tab_timeline, tab_ai = st.tabs(
        ["Overview", "Planning Position", "Policy Position", "Visual Evidence", "Timeline", "AI Summary"]
    )

    with tab_overview:
        row1, row2 = st.columns(2), st.columns(2)
        for col, metric in zip(row1, view["headline_metrics"][:2]):
            with col:
                stat_tile(metric["label"], metric["value"], caption=metric["caption"])
        for col, metric in zip(row2, view["headline_metrics"][2:]):
            with col:
                stat_tile(metric["label"], metric["value"], caption=metric["caption"])

        opportunity_position_card(view["opportunity_position"])

        st.divider()
        render_companies_and_contacts(session, settings, site, apps, merged, rep_app)

        st.divider()
        evidence_gap_panel(view["evidence_gaps"])
        st.caption("See the Planning Position, Policy Position and Visual Evidence tabs above for full detail.")

    with tab_planning:
        _render_planning_position(site, apps, view)

    with tab_policy:
        _render_policy_position(view)

    with tab_visual:
        visual_evidence_gallery(view["visual_evidence"])

    with tab_timeline:
        timeline(view["timeline"], key="site-profile", empty_message="No dated events recorded yet for this site.")

    with tab_ai:
        ai_status_summary_view(view["ai_summary"])
