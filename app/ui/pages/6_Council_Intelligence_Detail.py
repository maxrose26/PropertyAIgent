"""Council Intelligence detail (Sprint 4.3) - one council's full customer-
facing planning intelligence: overview KPIs, the existing AI Local Plan
Summary (prominently, never regenerated on page load), housing position
with evidence confidence, policy document coverage, allocation and visual
evidence summaries, an activity timeline, and known evidence gaps.

Reached via a "council" query param (mirrors app/ui/pages/1_Scheme_Detail.py's
own site_id pattern) rather than being a standalone nav item - visited by
clicking "Open Council ->" on app/ui/pages/5_Council_Intelligence.py.

Section order: Overview -> Local Plans -> AI Summary -> Housing Position ->
Policy Documents -> Allocations -> Visual Evidence -> Timeline -> Evidence
Gaps. See this sprint's completion report for why AI Summary is placed
immediately after Overview (Part 5's "prominently display", read together
with Part 3's suggested structure and the Part 4-11 detailed breakdown,
which itself orders AI Summary right after Overview).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st
from openai import OpenAI

from app.reporting.council_intelligence import PLAN_STAGE_LABELS, build_council_detail, build_council_overview
from app.reporting.local_plan_summary import generate_local_plan_summary, is_summary_stale
from app.ui.common import bootstrap, credits_sidebar, get_db
from app.ui.shell import (
    ai_summary_card,
    empty_state,
    housing_stat_card,
    metric_row,
    page_header,
    relative_time,
    section_header,
    status_badge,
    timeline,
)

bootstrap()
session, settings = get_db()
credits_sidebar(session, settings)

OVERVIEW_PAGE = Path(__file__).resolve().parents[1] / "pages" / "5_Council_Intelligence.py"
st.page_link(OVERVIEW_PAGE, label="← Back to Council Intelligence", icon="🔙")

council_code = st.query_params.get("council")
if not council_code:
    empty_state(
        "No council selected",
        "Open a council from Council Intelligence, or use quick search to jump straight to one.",
        icon="🏛️", cta_label="Browse Council Intelligence", cta_page=str(OVERVIEW_PAGE),
    )
    st.stop()

detail = build_council_detail(session, council_code)
if detail is None:
    empty_state(
        "Council not found",
        "That council code isn't recognised. Browse every council in Council Intelligence.",
        icon="⚠️", cta_label="Browse Council Intelligence", cta_page=str(OVERVIEW_PAGE),
    )
    st.stop()

plan = detail["primary_plan"]

# Sidebar council switcher (docs/NAVIGATION_ARCHITECTURE.md's "Council
# Intelligence: Council switcher (jump between councils without returning
# to a list)") - reuses the same overview data the list page itself shows.
with st.sidebar:
    st.markdown("**Switch council**")
    from app.reporting.council_intelligence import build_council_overview
    other_cards = build_council_overview(session)
    options = {c["council_name"]: c["council_code"] for c in other_cards}
    names = list(options.keys())
    current_name = detail["council_name"]
    if current_name in names:
        selected_name = st.selectbox("Council", names, index=names.index(current_name), label_visibility="collapsed")
        if options[selected_name] != council_code:
            st.query_params["council"] = options[selected_name]
            st.rerun()

page_header(
    detail["council_name"],
    plan.plan_name if plan else "No Local Plan onboarded yet",
    icon="🏛️",
)

# --- Overview (Part 4) --------------------------------------------------

documents_current = sum(1 for row in detail["coverage"] if row["current"])
documents_expected = len(detail["coverage"])

_next_milestone_value = None
if plan and plan.next_milestone:
    _next_milestone_value = f"{plan.next_milestone} ({plan.next_milestone_date})" if plan.next_milestone_date else plan.next_milestone

overview_items = [
    ("Current stage", PLAN_STAGE_LABELS.get(plan.status, "Not yet stated") if plan else "No Local Plan yet", None),
    ("Next milestone", _next_milestone_value, None),
    ("Expected adoption", plan.expected_adoption_date if plan else None, None),
    (
        "Housing requirement",
        (plan.total_housing_requirement or plan.annual_housing_requirement) if plan else None,
        "The plan's own stated housing number (total or annual).",
    ),
    ("Housing need", (plan.housing_need_total or plan.housing_need_annual) if plan else None, "From a housing need study - not the same as the adopted requirement."),
]
overview_items_2 = [
    ("Five-year supply", f"{plan.five_year_supply_years:g} yrs" if plan and plan.five_year_supply_years is not None else None, None),
    (
        "Delivery",
        f"{plan.homes_delivered_latest_period:,} homes ({plan.latest_reporting_period})"
        if plan and plan.homes_delivered_latest_period is not None and plan.latest_reporting_period else None,
        None,
    ),
    ("Allocations", detail["allocations"]["total"] or None, None),
    ("Policy documents", f"{documents_current} of {documents_expected}" if documents_expected else None, "Document types currently on file, of those expected for this council."),
    ("Evidence freshness", detail["evidence_freshness"], "How recently this council's sources were checked."),
]
metric_row(overview_items)
metric_row(overview_items_2)

st.divider()

# --- Local Plans (Part 3's structure) ------------------------------------

section_header("Local Plans", icon="📋")
if not detail["plan_summaries"]:
    st.caption("No Local Plan has been onboarded for this council yet.")
else:
    for p in detail["plan_summaries"]:
        with st.container(border=True):
            col_name, col_status = st.columns([3, 2], vertical_alignment="center")
            with col_name:
                version_bit = f" ({p['plan_version']})" if p["plan_version"] else ""
                st.markdown(f"**{p['plan_name']}{version_bit}**")
            with col_status:
                status_badge("confirmed" if p["status"] == "adopted" else "pending", PLAN_STAGE_LABELS.get(p["status"], "Not yet stated"))
            st.caption(
                f"{p['allocations_imported']} allocation(s), {p['sites_matched']} matched to a Site"
                + (f" · checked {relative_time(p['last_checked'])}" if p["last_checked"] else "")
            )

st.divider()

# --- AI Summary (Part 5) - prominent, never auto-regenerated ------------

section_header("AI Local Plan Summary", icon="🤖")
if plan is None:
    st.caption("No Local Plan onboarded yet - nothing to summarise.")
else:
    has_summary = plan.ai_summary_text is not None
    button_label = "🔄 Refresh" if has_summary else "Generate summary"
    if st.button(button_label, key=f"ci-refresh-summary-{plan.id}"):
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            st.error("OPENAI_API_KEY not set in .env.")
        else:
            with st.spinner("Generating summary from verified evidence..."):
                result = generate_local_plan_summary(session, OpenAI(api_key=openai_key), plan, force=True)
            if result["rejected"]:
                st.error(
                    f"The generated summary referenced figures not supported by this plan's evidence "
                    f"({', '.join(result['rejection_reason'])}) and was rejected - the previous summary, if any, "
                    f"has been kept."
                )
            st.rerun()

    if not has_summary:
        st.info("No AI summary generated yet for this council's Local Plan.")
    else:
        if is_summary_stale(session, plan):
            st.warning("⚠️ The underlying evidence has changed since this summary was generated - click Refresh for an up-to-date version.")
        generated_bit = plan.ai_summary_generated_at.strftime("%d %b %Y %H:%M") if plan.ai_summary_generated_at else None
        ai_summary_card(
            plan.ai_summary_text, generated_at=generated_bit, model=plan.ai_summary_model,
            prompt_version=plan.ai_summary_prompt_version, key=f"ci-ai-summary-{plan.id}",
        )
        key_risks = json.loads(plan.ai_summary_key_risks) if plan.ai_summary_key_risks else []
        key_opportunities = json.loads(plan.ai_summary_key_opportunities) if plan.ai_summary_key_opportunities else []
        if key_risks:
            st.markdown("**Key risks:**\n" + "\n".join(f"- {r}" for r in key_risks))
        if key_opportunities:
            st.markdown("**Key opportunities:**\n" + "\n".join(f"- {o}" for o in key_opportunities))

st.divider()

# --- Housing Position (Part 6) - every figure with its evidence confidence

section_header("Housing Position", icon="🏘️")
if detail["evidence_view"] is None:
    st.caption("No Local Plan onboarded yet - no housing position to show.")
else:
    by_field = {
        entry["field"]: entry
        for section in ("requirement", "delivery", "five_year_supply")
        for entry in detail["evidence_view"][section]
    }

    def _source_label(entry: dict) -> str | None:
        if entry["source_page"]:
            return f"p.{entry['source_page']}"
        return entry["source_document_title"]

    housing_fields = [
        ("annual_housing_requirement", "Housing requirement"),
        ("housing_need_annual", "Housing need"),
        ("five_year_supply_years", "Five-year supply (years)"),
        ("deliverable_supply_dwellings", "Deliverable supply"),
    ]
    housing_fields_2 = [
        ("homes_delivered_latest_period", "Delivery (latest period)"),
        ("five_year_shortfall_or_surplus_dwellings", "Shortfall / surplus"),
        ("buffer_percentage", "NPPF buffer"),
    ]
    cols = st.columns(4)
    for col, (field, label) in zip(cols, housing_fields):
        entry = by_field.get(field)
        with col:
            if entry is None:
                housing_stat_card(label, None)
            else:
                housing_stat_card(label, entry["value"], trust=entry["trust"] if entry["has_value"] else None, source_label=_source_label(entry) if entry["has_value"] else None)
    cols2 = st.columns(4)
    for col, (field, label) in zip(cols2, housing_fields_2):
        entry = by_field.get(field)
        with col:
            if entry is None:
                housing_stat_card(label, None)
            else:
                housing_stat_card(label, entry["value"], trust=entry["trust"] if entry["has_value"] else None, source_label=_source_label(entry) if entry["has_value"] else None)

st.divider()

# --- Policy Documents (Part 7) - reuses app.policy.coverage unchanged ----

section_header("Policy Documents", icon="📄")
if not detail["coverage"]:
    st.caption("No expected-document checklist configured for this council.")
else:
    doc_cols = st.columns(2)
    for i, row in enumerate(detail["coverage"]):
        with doc_cols[i % 2]:
            with st.container(border=True):
                st.markdown(f"**{row['label']}**")
                if row["missing"]:
                    status_badge("error", "Missing")
                elif row["current"]:
                    status_badge("confirmed", "Current")
                elif row["superseded"]:
                    status_badge("pending", "Superseded")
                else:
                    status_badge("info", "Discovered")
                st.caption(f"{row['current_count']} current, {row['superseded_count']} superseded on file.")
                if row["latest_document_title"]:
                    st.caption(f"Last updated: {row['latest_document_updated'] or 'date not stated'}")
                if row["latest_document_url"]:
                    st.link_button("Open document", row["latest_document_url"])

st.divider()

# --- Allocations (Part 8) - links out to Local Plan Sites, no duplication

section_header("Allocations", icon="🗺️")
allocations = detail["allocations"]
metric_row([
    ("Allocations", allocations["total"], None),
    ("Matched to a Site", allocations["matched"], "Allocations with a planning application already submitted."),
    ("With confirmed images", allocations["with_images"], None),
    ("Requiring review", allocations["needing_review"], None),
])
st.page_link("pages/3_Local_Plan_Sites.py", label="View Allocations →")

st.divider()

# --- Visual Evidence (Part 9) - concise summary, not a duplicate gallery -

section_header("Visual Evidence", icon="🖼️")
ve = detail["visual_evidence"]
metric_row([
    ("Images", ve["total"], None),
    ("Confirmed", ve["confirmed"], None),
    ("Needs review", ve["needs_review"], None),
    ("Latest extracted", relative_time(ve["latest_extracted"]) if ve["latest_extracted"] else "—", None),
])
if ve["recent_allocation_maps"]:
    st.markdown("**Recent allocation maps**")
    for item in ve["recent_allocation_maps"]:
        col_label, col_badge, col_time = st.columns([5, 2, 2], vertical_alignment="center")
        with col_label:
            ref_bit = f" ({item['reference']})" if item["reference"] else ""
            st.markdown(f"🖼️ {item['label']}{ref_bit}")
        with col_badge:
            status_badge("confirmed" if item["review_status"] == "confirmed" else "review")
        with col_time:
            st.caption(relative_time(item["when"]))

st.divider()

# --- Timeline (Part 10) ---------------------------------------------------

section_header("Timeline", icon="🕗")
timeline(detail["timeline"], key="council-intel", empty_message="No recorded activity for this council yet.")

st.divider()

# --- Evidence Gaps (Part 11) - reuses the coverage engine + evidence view

section_header("Evidence Gaps", icon="⚠️")
if not detail["evidence_gaps"]:
    st.caption("No known evidence gaps for this council right now.")
else:
    with st.container(border=True):
        for gap in detail["evidence_gaps"]:
            st.markdown(f"- {gap}")
