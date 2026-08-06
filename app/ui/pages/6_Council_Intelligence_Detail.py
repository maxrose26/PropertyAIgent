"""Council Intelligence detail (Sprint 4.3) - one council's full customer-
facing planning intelligence: overview KPIs, every applicable Local Plan's
existing AI summary (prominently, never regenerated on page load), housing
position with evidence confidence, every Local Plan the council has, an
allocation summary, policy document coverage, a visual-evidence summary,
known evidence gaps, and a policy activity timeline.

Reached via a "council" query param (mirrors app/ui/pages/1_Scheme_Detail.py's
own site_id pattern) rather than being a standalone nav item - visited by
clicking "Open Council ->" on app/ui/pages/5_Council_Intelligence.py.

Section order (Sprint 4.3 resumption brief, Part 5): Council overview -> AI
planning-policy summary -> Housing position -> Local Plans -> Allocations ->
Policy documents -> Visual evidence -> Evidence gaps -> Policy timeline.
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
    evidence_badge,
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

# --- 1. Council overview -----------------------------------------------

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

# --- 2. AI planning-policy summary - prominent, never auto-regenerated --
#
# Part 6: "If multiple Local Plans apply to one council, present them
# clearly and avoid blending facts incorrectly" - every one of the
# council's own Local Plans (detail["plans"], not just the primary one)
# gets its own clearly-labelled summary block below, each reading only
# that plan's own persisted ai_summary_* columns - never merged.

section_header("AI Local Plan Summary", icon="🤖")

if not detail["plans"]:
    st.caption("No Local Plan onboarded yet - nothing to summarise.")
else:
    for plan_row in detail["plans"]:
        if len(detail["plans"]) > 1:
            st.markdown(f"##### {plan_row.plan_name}")

        has_summary = plan_row.ai_summary_text is not None
        button_label = "🔄 Refresh" if has_summary else "Generate summary"
        if st.button(button_label, key=f"ci-refresh-summary-{plan_row.id}"):
            openai_key = os.getenv("OPENAI_API_KEY")
            if not openai_key:
                st.error("OPENAI_API_KEY not set in .env.")
            else:
                with st.spinner("Generating summary from verified evidence..."):
                    result = generate_local_plan_summary(session, OpenAI(api_key=openai_key), plan_row, force=True)
                if result["rejected"]:
                    st.error(
                        f"The generated summary referenced figures not supported by this plan's evidence "
                        f"({', '.join(result['rejection_reason'])}) and was rejected - the previous summary, if any, "
                        f"has been kept."
                    )
                st.rerun()

        if not has_summary:
            st.info("No AI summary generated yet for this Local Plan.")
            continue

        if is_summary_stale(session, plan_row):
            st.warning("⚠️ The underlying evidence has changed since this summary was generated - click Refresh for an up-to-date version.")

        evidence_badge("Evidence-based summary", help="Generated only from evidence already verified elsewhere on this platform.")
        generated_bit = plan_row.ai_summary_generated_at.strftime("%d %b %Y %H:%M") if plan_row.ai_summary_generated_at else None
        ai_summary_card(
            plan_row.ai_summary_text, generated_at=generated_bit, model=plan_row.ai_summary_model,
            prompt_version=plan_row.ai_summary_prompt_version, key=f"ci-ai-summary-{plan_row.id}",
        )
        key_risks = json.loads(plan_row.ai_summary_key_risks) if plan_row.ai_summary_key_risks else []
        key_opportunities = json.loads(plan_row.ai_summary_key_opportunities) if plan_row.ai_summary_key_opportunities else []
        ai_evidence_gaps = json.loads(plan_row.ai_summary_evidence_gaps) if plan_row.ai_summary_evidence_gaps else []
        if key_risks:
            st.markdown("**Key risks:**\n" + "\n".join(f"- {r}" for r in key_risks))
        if key_opportunities:
            st.markdown("**Key opportunities:**\n" + "\n".join(f"- {o}" for o in key_opportunities))
        if ai_evidence_gaps:
            st.markdown("**Evidence gaps:**\n" + "\n".join(f"- {g}" for g in ai_evidence_gaps))

        if len(detail["plans"]) > 1 and plan_row is not detail["plans"][-1]:
            st.markdown("---")

st.divider()

# --- 3. Housing position - every figure with its evidence confidence ----

section_header("Housing Position", icon="🏘️")
if detail["evidence_view"] is None:
    st.caption("No Local Plan onboarded yet - no housing position to show.")
else:
    if plan:
        ownership_bit = "this council's own Local Plan" if detail["primary_plan_is_own"] else "the joint plan this council participates in - it has no separate Local Plan of its own onboarded yet"
        st.caption(f"Shown for {plan.plan_name} - {ownership_bit}.")
    by_field = {
        entry["field"]: entry
        for section in ("requirement", "delivery", "five_year_supply")
        for entry in detail["evidence_view"][section]
    }

    def _source_label(entry: dict) -> str | None:
        if entry["source_page"]:
            return f"p.{entry['source_page']}"
        return entry["source_document_title"]

    def _render_housing_row(fields: list[tuple[str, str]]) -> None:
        cols = st.columns(len(fields))
        for col, (field, label) in zip(cols, fields):
            entry = by_field.get(field)
            with col:
                if entry is None:
                    housing_stat_card(label, None)
                else:
                    housing_stat_card(
                        label, entry["value"],
                        trust=entry["trust"] if entry["has_value"] else None,
                        source_label=_source_label(entry) if entry["has_value"] else None,
                    )

    _render_housing_row([
        ("annual_housing_requirement", "Housing requirement"),
        ("housing_need_annual", "Housing need"),
        ("five_year_supply_years", "Five-year supply (years)"),
        ("deliverable_supply_dwellings", "Deliverable supply"),
    ])
    _render_housing_row([
        ("five_year_requirement_dwellings", "Five-year requirement"),
        ("homes_delivered_latest_period", "Delivery (latest period)"),
        ("five_year_shortfall_or_surplus_dwellings", "Shortfall / surplus"),
        ("buffer_percentage", "NPPF buffer"),
    ])
    base_date_entry = by_field.get("five_year_supply_base_date")
    if base_date_entry and base_date_entry["has_value"]:
        st.caption(f"Five-year supply base date: {base_date_entry['value']}")

st.divider()

# --- 4. Local Plans (Part 8: single-authority, emerging, adopted, joint) -

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
                f"{p['allocations_imported']} allocation(s) in {detail['council_name']}, {p['sites_matched']} matched to a Site"
                + (f" · checked {relative_time(p['last_checked'])}" if p["last_checked"] else "")
            )

st.divider()

# --- 5. Allocations - links out to Local Plan Sites, no duplication -----

section_header("Allocations", icon="🗺️")
allocations = detail["allocations"]
metric_row([
    ("Allocations", allocations["total"], None),
    ("Matched to a Site", allocations["matched"], "Allocations with a planning application already submitted."),
    ("Without an application", allocations["without_application"], None),
    ("With confirmed images", allocations["with_images"], None),
])
metric_row([
    ("Images awaiting review", allocations["images_needing_review"], "AI-suggested allocation images not yet confirmed by a reviewer."),
    ("Allocations awaiting review", allocations["needing_review"], None),
])
st.page_link(
    "pages/3_Local_Plan_Sites.py", label="View Local Plan Sites →",
    query_params={"council": detail["council_code"]},
)
st.caption(
    "Opens Local Plan Sites pre-filtered to this council - the sidebar's council filter can still be "
    "widened or cleared from there."
)

st.divider()

# --- 6. Policy documents - reuses app.policy.coverage unchanged ---------

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

# --- 7. Visual evidence - concise summary, not a duplicate gallery ------

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

# --- 8. Evidence gaps - reuses the coverage engine + evidence view ------

section_header("Evidence Gaps", icon="⚠️")
if not detail["evidence_gaps"]:
    st.caption("No known evidence gaps for this council right now.")
else:
    with st.container(border=True):
        for gap in detail["evidence_gaps"]:
            st.markdown(f"- {gap}")

st.divider()

# --- 9. Policy timeline --------------------------------------------------

section_header("Policy Timeline", icon="🕗")
timeline(detail["timeline"], key="council-intel", empty_message="No recorded activity for this council yet.")
