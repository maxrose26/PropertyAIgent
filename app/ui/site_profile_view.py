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
from app.reporting.ownership_control import EMPTY_STATE_APPLICATION, EMPTY_STATE_SITE, SOURCE_NOTE, get_site_control_detail
from app.reporting.residential_mix import format_affordable_tile
from app.reporting.site_profile import build_site_profile
from app.ui.common import (
    aggregate_scheme_fields,
    pick_representative_application,
    render_companies_and_contacts,
)
from app.ui.shell import (
    ai_badge,
    ai_status_summary_view,
    arrow_safe_count,
    control_relationship_group_card,
    control_relationship_view_card,
    evidence_gap_panel,
    opportunity_position_card,
    section_header,
    site_profile_header,
    stat_tile,
    status_badge,
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
            "Units": arrow_safe_count(p.get("unit_count"), "—" if p["kind"] == "phase" else ""),
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


def affordable_headline_tile(headline: dict) -> None:
    """The Affordable Homes headline tile (Sprint 4.4 Amendment, Part 4) -
    value first, evidence state secondary (Part 16). value/caption come
    from format_affordable_tile, the one shared implementation of "which
    line is primary" per state - also used by app.reporting.site_profile.
    build_headline_metrics, so the Overview headline tile and every use of
    this same tile inside the Residential Mix Intelligence tab can never
    disagree with each other."""
    value, caption = format_affordable_tile(headline)
    stat_tile("Affordable homes", value, caption=caption)


def residential_mix_overview_excerpt(mix: dict) -> None:
    """Part 3 - the Overview tab's concise excerpt: a short commentary
    excerpt where one exists, and a prompt to open the full tab. Never the
    full bedroom/tenure breakdown - that lives only in the dedicated tab.
    The Affordable Homes headline tile itself is rendered separately,
    already one of the four Site Profile headline metrics."""
    excerpt = mix["ai_commentary"]["text"] or mix["structured_summary"]
    if excerpt:
        label = "Residential Mix Commentary" if mix["ai_commentary"]["has_commentary"] else "Structured summary"
        st.caption(f"**{label}:** {excerpt}")
    st.caption("See the Residential Mix Intelligence tab for the full bedroom mix, tenure and evidence detail →")


def _current_version_banner(current_version: dict) -> None:
    if not current_version.get("application_id"):
        st.info("No qualifying application is linked to this site yet.")
        return
    st.caption(f"Current preferred version: **{current_version['reference']}** — {current_version['why_preferred']}")
    if current_version["version_conflict"]:
        status_badge("conflicting", "Alternative versions record a different total — see Evidence and Reconciliation below")


def _residential_mix_overview_section(mix: dict) -> None:
    section_header("Residential Mix Overview", icon="🏘️")
    _current_version_banner(mix["current_version"])
    totals = mix["overview_totals"]
    cols = st.columns(3)
    with cols[0]:
        stat_tile("Total homes", f"{totals['total_homes']:,}" if totals["total_homes"] is not None else "Not yet verified")
    with cols[1]:
        affordable_headline_tile(mix["affordable_headline"])
    with cols[2]:
        density = mix["density"]
        stat_tile("Density", f"{density['density_dph']:g} dwellings/ha" if density["available"] else "Not yet verified")


def _bedroom_mix_section(bedroom_mix: dict) -> None:
    """Part 8 - honestly absent in Phase 1 (see app.reporting.
    residential_mix.build_bedroom_mix's own docstring for why: no
    structured bedroom-mix extraction exists on this platform today).
    Never a table of invented zero-value categories."""
    section_header("Bedroom Mix", icon="🛏️")
    if not bedroom_mix["available"]:
        st.info("No structured bedroom mix has been extracted for this platform yet.")


def _housing_type_section(housing_type: dict) -> None:
    section_header("Housing Type", icon="🏠")
    if not housing_type["available"]:
        st.info("No housing-type evidence has been extracted for this scheme yet.")
        return
    if housing_type["typology_description"]:
        st.write(housing_type["typology_description"])
    if housing_type["specialist_type"]:
        st.caption(f"Specialist housing type: {housing_type['specialist_type']}")
    if housing_type["development_type"]:
        st.caption(f"Development type: {housing_type['development_type']}")
    st.caption("Recorded as descriptive evidence, not a quantified house/flat/bungalow count.")


def _affordable_housing_section(mix: dict) -> None:
    section_header("Affordable Housing", icon="🏡")
    scheme = mix["scheme"]
    headline = mix["affordable_headline"]
    affordable_headline_tile(headline)
    if headline["percentage_is_calculated"]:
        st.caption(
            "Percentage calculated from affordable homes ÷ total homes for this scheme version - "
            "not independently stated in evidence."
        )
    if scheme:
        detail_bits = []
        if scheme.affordable_classification_confidence:
            detail_bits.append(f"confidence: {scheme.affordable_classification_confidence}")
        if scheme.affordable_data_status:
            detail_bits.append(f"status: {scheme.affordable_data_status}")
        if detail_bits:
            st.caption(" · ".join(detail_bits))
        if scheme.affordable_classification_evidence:
            with st.expander("Source evidence"):
                st.write(scheme.affordable_classification_evidence)
        if scheme.affordable_status_note:
            status_badge("review")
            st.caption(scheme.affordable_status_note)


def _affordable_tenure_section(tenure: dict) -> None:
    section_header("Affordable Tenure", icon="🔑")
    if tenure["has_categories"]:
        for category in tenure["categories"]:
            st.markdown(f"- {category}")
    elif tenure["affordable_known_tenure_unknown"]:
        st.info("Affordable tenure not identified")
    else:
        st.caption("Not applicable - no affordable homes identified for this scheme.")


def _residential_mix_commentary_section(mix: dict) -> None:
    """Part 13/14/15 - reuses the existing stored Residential Mix
    Commentary where one exists (none does today, see app.reporting.
    residential_mix.build_ai_commentary_view); otherwise the deterministic
    "Structured summary" (Part 15), visibly distinct from an AI commentary
    (a different badge colour and an explicit different label, never
    "AI Commentary")."""
    section_header("Residential Mix Commentary", icon="📝")
    commentary = mix["ai_commentary"]
    if commentary["has_commentary"]:
        ai_badge()
        st.write(commentary["text"])
        if commentary["is_stale"]:
            status_badge("stale", "Stale — evidence has changed since this was generated")
        return
    if mix["structured_summary"]:
        status_badge("info", "Structured summary")
        st.write(mix["structured_summary"])
    else:
        st.caption("Residential Mix Commentary not yet generated")


def _evidence_and_reconciliation_section(mix: dict) -> None:
    section_header("Evidence and Reconciliation", icon="🔍")
    current_version = mix["current_version"]
    scheme = mix["scheme"]
    if scheme:
        st.caption(
            f"Source application: {current_version['reference']} · "
            f"reconciliation status: {scheme.unit_reconciliation_status or 'OK'}"
        )
    if current_version["alternatives"]:
        st.markdown("**Alternative / superseded application versions on this site**")
        for alt in current_version["alternatives"]:
            bits = [alt["reference"]]
            if alt["total_units_final"] is not None:
                bits.append(f"{alt['total_units_final']:,} total homes")
            if alt["affordable_units_final"] is not None:
                bits.append(f"{alt['affordable_units_final']:,} affordable")
            st.caption(" · ".join(bits) + " — not combined with the current version's figures above.")


def _render_residential_mix(mix: dict) -> None:
    """The dedicated Residential Mix Intelligence tab (Sprint 4.4
    Amendment, Part 2/6) - suggested section order, each one degrading
    honestly when its evidence doesn't exist rather than a dead panel."""
    _residential_mix_overview_section(mix)
    st.divider()
    _bedroom_mix_section(mix["bedroom_mix"])
    st.divider()
    _housing_type_section(mix["housing_type"])
    st.divider()
    _affordable_housing_section(mix)
    st.divider()
    _affordable_tenure_section(mix["tenure"])
    st.divider()
    _residential_mix_commentary_section(mix)
    st.divider()
    _evidence_and_reconciliation_section(mix)
    st.divider()
    evidence_gap_panel(mix["evidence_gaps"])


def _render_ownership_control(session, site: Site, apps: list[Application]) -> None:
    """The Ownership & Control tab (Stage 4B.2) - a Site-level aggregate
    (Part 5, grouped for display only) followed by a per-Application
    breakdown (Part 4, full fidelity, each Application's own evidence
    only) - both read via ONE query (get_site_control_detail), never one
    query per linked Application. The Part 8 source note is shown once at
    the end, covering both sections, never repeated per entity."""
    section_header("Ownership & Control", icon="🗝️")
    groups, by_application = get_site_control_detail(session, site.id)

    if not groups:
        st.info(EMPTY_STATE_SITE)
    else:
        for group in groups:
            control_relationship_group_card(group)

    st.divider()
    st.markdown("**By Application**")
    ordered_apps = sorted(
        apps, key=lambda a: (not by_application.get(a.id), a.reference or ""),
    )
    for app in ordered_apps:
        views = by_application.get(app.id, [])
        with st.expander(app.reference or f"Application {app.id}", expanded=False):
            if not views:
                st.caption(EMPTY_STATE_APPLICATION)
                continue
            for view in views:
                control_relationship_view_card(view)

    st.divider()
    st.caption(SOURCE_NOTE)


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

    tab_overview, tab_planning, tab_policy, tab_ownership, tab_mix, tab_visual, tab_timeline, tab_ai = st.tabs(
        [
            "Overview", "Planning Position", "Policy Position", "Ownership & Control", "Residential Mix Intelligence",
            "Visual Evidence", "Timeline", "AI Summary",
        ]
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
        residential_mix_overview_excerpt(view["residential_mix"])

        st.divider()
        render_companies_and_contacts(session, settings, site, apps, merged, rep_app)

        st.divider()
        evidence_gap_panel(view["evidence_gaps"])
        st.caption("See the Planning Position, Policy Position and Visual Evidence tabs above for full detail.")

    with tab_planning:
        _render_planning_position(site, apps, view)

    with tab_policy:
        _render_policy_position(view)

    with tab_ownership:
        _render_ownership_control(session, site, apps)

    with tab_mix:
        _render_residential_mix(view["residential_mix"])

    with tab_visual:
        visual_evidence_gallery(view["visual_evidence"])

    with tab_timeline:
        timeline(view["timeline"], key="site-profile", empty_message="No dated events recorded yet for this site.")

    with tab_ai:
        ai_status_summary_view(view["ai_summary"])
