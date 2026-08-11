"""Council Operations (Sprint 2, "Greater Manchester Policy Intelligence
Framework", Part 7; renamed from "Council Dashboard" in Sprint 4.3,
"Council Intelligence", Part 11) - the internal Administration view for
confirming what's been onboarded and whether monitoring is actually
working. Not a page a prospective land buyer or investor would ever need -
see app/ui/pages/5_Council_Intelligence.py and 6_Council_Intelligence_
Detail.py for that customer-facing split, built from the same underlying
data via app.reporting.council_intelligence.

Sprint 4.3 deliberately did not redesign this page - only the rename and
the navigation move (already under Administration, title updated) were in
scope; every existing operational control, table and expander below is
unchanged. See app.policy.council_dashboard for the pure data assembly
this renders.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pandas as pd
import streamlit as st
from openai import OpenAI
from sqlalchemy import select

from app.db.models import LocalPlan, MonitoredReport
from app.pipeline.freshness import FRESH, STALE, WARNING
from app.policy.council_dashboard import build_council_dashboard
from app.policy.coverage import build_coverage_inventory
from app.policy.plan_evidence_view import build_plan_evidence_view
from app.reporting.intelligence_health import build_intelligence_health_summary
from app.reporting.local_plan_summary import generate_local_plan_summary, is_summary_stale
from app.reporting.scraper_health import build_scraper_health_summary
from app.ui.common import bootstrap, credits_sidebar, get_db
from app.ui.shell import ai_summary_card, empty_state, page_header, wide_canvas

bootstrap()
session, settings = get_db()

HOME_PAGE = Path(__file__).resolve().parents[1] / "pages" / "0_Explore.py"
st.page_link(HOME_PAGE, label="← Back to Explore", icon="🔙")

credits_sidebar(session, settings)
# Live Deployment Integrity audit (Part 5) - this is an Administration-only
# page (never linked from a customer-facing surface), so widening it here
# doesn't touch any customer-facing page width - wide_canvas() is already
# page-scoped (see its own docstring in app.ui.shell).
wide_canvas()

page_header(
    "Council Operations",
    "Internal view of Policy Intelligence onboarding per council - which Local Plans have been ingested, "
    "whether monitoring is actually reaching their sources, and what's waiting for a review decision. "
    "Not part of the public site-browsing experience - see Council Intelligence under Policy for that.",
    icon="⚙️",
)

# Pilot Readiness PR-2 ("Production Freshness & Core Data Integrity", Part
# 6) - Planning Application scraper health is a DIFFERENT pipeline from the
# Policy Intelligence monitoring table below (app.policy.council_dashboard
# tracks Local Plan/policy source monitoring; this tracks the scraper that
# discovers Applications) - kept as its own section rather than merged into
# that table, since conflating the two would blur exactly the distinction
# PR-1/PR-2 both insist on ("scraper execution health and source activity
# are different concepts", and different again from Policy monitoring).
_FRESHNESS_ICON = {FRESH: "✅", WARNING: "⏰", STALE: "🔴"}


def _freshness_display(state: str, label: str) -> str:
    return f"{_FRESHNESS_ICON.get(state, '❔')} {label}"


st.markdown("### 🕷️ Planning Application Scraper Health")
scraper_rows = build_scraper_health_summary(session)
scraper_table_rows = [{
    "Council": r["council_name"],
    "Freshness": _freshness_display(r["freshness"], r["freshness_label"]),
    "Last successful run": r["last_successful_at"].strftime("%d %b %Y %H:%M") if r["last_successful_at"] else "Never",
    "Last attempt": r["last_attempted_at"].strftime("%d %b %Y %H:%M") if r["last_attempted_at"] else "Never",
    "Last attempt status": r["last_attempt_status"] or "—",
    "Applications discovered (last run)": (
        r["last_run_applications_discovered"] if r["last_run_applications_discovered"] is not None else "—"
    ),
    "Runs recorded": r["total_runs_recorded"],
} for r in scraper_rows]
st.dataframe(pd.DataFrame(scraper_table_rows), use_container_width=True, hide_index=True)
st.caption(
    "Fresh = a successful run completed within the last 48 hours. Ageing = 48-72 hours. Stale = over 72 hours. "
    "\"No run evidence\" means this council has never had a recorded scraper attempt from the production "
    "orchestrator (scripts/run_daily_councils.py) - distinct from Stale, which means a run happened but is now old."
)
st.divider()

# AI Processing Reliability & Backlog Throughput - minimum operator
# visibility for the bounded Intelligence Processing job (scripts.
# run_intelligence_processing), which previously had no UI anywhere (the
# prior audit's own finding). One row, not a per-council table -
# IntelligenceRun processes every selected council in a single bounded run.
st.markdown("### 🧠 Intelligence Processing Health")
_INTELLIGENCE_STATUS_ICON = {"success": "✅", "partial": "⚠️", "failed": "❌", "running": "⏳"}
intelligence_summary = build_intelligence_health_summary(session)
if intelligence_summary is None:
    st.caption("No Intelligence Processing run recorded yet.")
else:
    status = intelligence_summary["status"]
    started_label = (
        intelligence_summary["started_at"].strftime("%d %b %Y %H:%M")
        if intelligence_summary["started_at"] else "—"
    )
    st.markdown(
        f"**{_INTELLIGENCE_STATUS_ICON.get(status, '❔')} {status.upper()}** &nbsp;·&nbsp; "
        f"last run started {started_label} ({intelligence_summary['triggered_by']})"
    )
    intelligence_table_rows = [{
        "Extraction candidates inspected": intelligence_summary["extractions_candidates_inspected"],
        "Extraction attempted": intelligence_summary["extractions_attempted"],
        "Extraction succeeded": intelligence_summary["extractions_succeeded"],
        "Extraction no usable text": intelligence_summary["extractions_no_usable_text"],
        "Extraction failed": intelligence_summary["extractions_failed"],
        "Extraction backlog remaining": intelligence_summary["applications_backlog_remaining"],
        "Summaries attempted": intelligence_summary["summaries_attempted"],
        "Summaries succeeded": intelligence_summary["summaries_succeeded"],
        "Summaries failed": intelligence_summary["summaries_failed"],
        "Summary backlog remaining": intelligence_summary["sites_backlog_remaining"],
    }]
    st.dataframe(pd.DataFrame(intelligence_table_rows), use_container_width=True, hide_index=True)
    if intelligence_summary["detail"]:
        st.caption(intelligence_summary["detail"])
    st.caption(
        "\"No usable text\" applications do not count as an AI failure and do not re-run daily forever - "
        "see Application.extraction_last_outcome. PARTIAL means the run completed but at least one genuine "
        "extraction or summary failure occurred; FAILED means the job itself could not run at all "
        "(e.g. a missing API key with outstanding work)."
    )
st.divider()

rows = build_council_dashboard(session)
if not rows:
    empty_state(
        "No Policy Intelligence activity yet",
        "No Local Plans have been ingested and no monitoring sources are registered for any council.",
        icon="📋",
    )
    st.stop()

HEALTH_LABELS = {
    "ok": "✅ OK", "error": "❌ Error", "stale": "⏸️ Stale",
    "never_checked": "❔ Never checked", "no_sources": "— No sources registered",
}

# Sprint 3B ("AI Local Plan Evidence Extraction", Part 10) - display labels
# for app.policy.plan_evidence_view's four sections.
EVIDENCE_SECTIONS = (
    ("status", "Plan status"),
    ("requirement", "Housing requirement"),
    ("delivery", "Housing delivery"),
    ("five_year_supply", "Five-year housing land supply"),
)
EVIDENCE_FIELD_LABELS = {
    "status": "Status", "raw_status": "Raw authority status",
    "plan_period_start": "Plan period start", "plan_period_end": "Plan period end",
    "expected_adoption_date": "Expected adoption date", "adoption_date": "Adoption date",
    "next_milestone": "Next milestone", "next_milestone_date": "Next milestone date",
    "examination_status": "Examination status", "publication_date": "Publication date",
    "submission_date": "Submission date", "inspector_report_date": "Inspector's report date",
    "annual_housing_requirement": "Annual housing requirement",
    "total_housing_requirement": "Total plan housing requirement",
    "housing_need_annual": "Housing need (annual)", "housing_need_total": "Housing need (total)",
    "requirement_basis": "Requirement basis", "unmet_need": "Unmet need",
    "latest_reporting_period": "Latest reporting period",
    "homes_delivered_latest_period": "Homes delivered (latest period)",
    "delivery_requirement_for_period": "Delivery requirement (period)",
    "delivery_surplus_or_shortfall": "Surplus / shortfall",
    "housing_delivery_test_result": "Housing Delivery Test result",
    "trajectory_remaining_requirement": "Trajectory - remaining requirement",
    "five_year_supply_years": "Years of supply", "five_year_supply_base_date": "Supply base date",
    "five_year_supply_publication_date": "Supply publication date",
    "deliverable_supply_dwellings": "Deliverable supply (dwellings)",
    "five_year_requirement_dwellings": "Five-year requirement (dwellings)",
    "five_year_shortfall_or_surplus_dwellings": "Shortfall / surplus", "buffer_percentage": "Buffer %",
}


def _render_evidence_field(entry: dict) -> None:
    # Part 10: never show missing/unsupported evidence as a bare zero or
    # blank row - a field with nothing at all (no trusted value, no
    # pending proposal, AND no newer report waiting to fill it in) is
    # simply omitted from the page. newer_report_pending is included here
    # (Part 6) so a field that's still empty but has a fresh, not-yet-
    # extracted report sitting behind it doesn't just silently vanish.
    if not entry["has_value"] and entry["pending_value"] is None and not entry["newer_report_pending"]:
        return

    label = EVIDENCE_FIELD_LABELS.get(entry["field"], entry["field"])
    if entry["has_value"]:
        stale_bit = " ⏸️ *stale evidence*" if entry["is_stale"] else ""
        # Part 6: never label an older figure "current" where a newer
        # report has been discovered but not yet reviewed/extracted.
        newer_bit = " 🆕 *a newer report exists, not yet extracted*" if entry["newer_report_pending"] else ""
        source_bit = ""
        page_note = f", page {entry['source_page']}" if entry["source_page"] else ""
        if entry["source_document_url"]:
            anchor = f"#page={entry['source_page']}" if entry["source_page"] else ""
            title = entry["source_document_title"] or "source"
            source_bit = f" — [{title}]({entry['source_document_url']}{anchor}){page_note}"
        elif entry["source_document_title"]:
            source_bit = f" — {entry['source_document_title']}{page_note}"
        st.markdown(f"**{label}:** {entry['value']}{stale_bit}{newer_bit}{source_bit}")
    else:
        newer_bit = " 🆕 *a newer report exists, not yet extracted*" if entry["newer_report_pending"] else ""
        st.markdown(f"**{label}:** _not available_{newer_bit}")

    if entry["pending_value"] is not None:
        st.caption(f"🕗 Proposed change awaiting review: → **{entry['pending_value']}**")

    if entry["historic_values"]:
        with st.expander(f"Previous values ({len(entry['historic_values'])})"):
            for h in entry["historic_values"]:
                date_bit = h["extracted_at"].strftime("%d %b %Y") if h["extracted_at"] else "date unknown"
                source_bit = f" — {h['source_document_title']}" if h["source_document_title"] else ""
                st.caption(f"{h['value']} (as of {date_bit}{source_bit})")


def _render_ai_summary(plan_row: LocalPlan, council_code: str) -> None:
    """Sprint 3B.1 ("AI Local Plan Summary", Part 7) - shown at the TOP of
    each Local Plan section, above the existing detailed evidence
    expander. Never regenerates on its own (Part 6) - generate_local_plan_
    summary is only ever called from inside the Refresh button's own
    click branch below, so a plain page view/rerun never spends AI cost.

    council_code: Sprint 3E ("Joint Plan Support and Bury Allocation
    Reconciliation") - a joint plan like Places for Everyone now renders
    once per participating authority's own expander (Part 3), all showing
    the SAME plan_row - the button's key must include which council's
    expander it's rendering inside, or Streamlit raises
    StreamlitDuplicateElementKey the moment a plan appears under a second
    council. The underlying ai_summary_* fields stay genuinely shared
    (Part 3: "plan-wide metadata remains shared") - only the widget's own
    identity needs to differ per render location."""
    st.markdown("##### 🤖 AI Local Plan Summary")

    has_summary = plan_row.ai_summary_text is not None
    button_label = "🔄 Refresh" if has_summary else "Generate summary"
    if st.button(button_label, key=f"refresh_summary_{plan_row.id}_{council_code}"):
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
        st.info("No AI summary generated yet for this plan.")
        return

    if is_summary_stale(session, plan_row):
        st.warning("⚠️ The underlying evidence has changed since this summary was generated - click Refresh for an up-to-date version.")

    generated_bit = plan_row.ai_summary_generated_at.strftime("%d %b %Y %H:%M") if plan_row.ai_summary_generated_at else None
    ai_summary_card(
        plan_row.ai_summary_text,
        generated_at=generated_bit,
        model=plan_row.ai_summary_model,
        prompt_version=plan_row.ai_summary_prompt_version,
        key=f"ai-summary-card-{plan_row.id}-{council_code}",
    )

    key_risks = json.loads(plan_row.ai_summary_key_risks) if plan_row.ai_summary_key_risks else []
    key_opportunities = json.loads(plan_row.ai_summary_key_opportunities) if plan_row.ai_summary_key_opportunities else []
    evidence_gaps = json.loads(plan_row.ai_summary_evidence_gaps) if plan_row.ai_summary_evidence_gaps else []

    if key_risks:
        st.markdown("**Key risks:**\n" + "\n".join(f"- {r}" for r in key_risks))
    if key_opportunities:
        st.markdown("**Key opportunities:**\n" + "\n".join(f"- {o}" for o in key_opportunities))
    if evidence_gaps:
        st.markdown("**Evidence gaps:**\n" + "\n".join(f"- {g}" for g in evidence_gaps))


REPORT_STATUS_LABELS = {"current": "✅ Current", "superseded": "🗄️ Superseded"}
REPORT_CLASSIFICATION_LABELS = {"auto": "Auto-classified", "needs_review": "⚠️ Needs review"}


def _render_monitored_reports(council_code: str) -> None:
    reports = session.execute(
        select(MonitoredReport).where(MonitoredReport.council_code == council_code)
        .order_by(MonitoredReport.discovered_at.desc())
    ).scalars().all()
    if not reports:
        return

    rows = [{
        "Report": r.title or r.url,
        "Type": r.source_type or "(unclassified)",
        "Status": REPORT_STATUS_LABELS.get(r.status, r.status),
        "Classification": REPORT_CLASSIFICATION_LABELS.get(r.classification_status, r.classification_status),
        "Reporting period": r.reporting_period or "—",
        "Last checked": r.last_checked.strftime("%d %b %Y") if r.last_checked else "Never",
        "Extracted": "Yes" if r.last_extracted_at else "No",
    } for r in reports]

    with st.expander(f"Monitored reports ({len(reports)})"):
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        needs_review = [r for r in reports if r.classification_status == "needs_review"]
        if needs_review:
            st.warning(f"⚠️ {len(needs_review)} discovered document(s) need a human to confirm their report type.")


_YES_NO = {True: "✅ Yes", False: "—"}


def _render_document_coverage(council_code: str, council_name: str) -> None:
    """Sprint 3D ("Policy Document Coverage & Discovery", Part 7) - a
    lightweight, operational-only table of which planning-policy document
    types are expected for this council and how far each one has
    actually got through the pipeline. See app.policy.coverage for the
    pure data assembly this renders."""
    inventory = build_coverage_inventory(session, council_code)
    if not inventory:
        return

    missing = [row["label"] for row in inventory if row["missing"]]
    if missing:
        st.warning(f"⚠️ We are missing: {', '.join(missing)}.")

    rows = [{
        "Document Type": row["label"],
        "Expected": _YES_NO[row["expected"]],
        "Found": _YES_NO[row["discovered"]],
        "Current": _YES_NO[row["current"]],
        "Missing": _YES_NO[row["missing"]],
        "Superseded": _YES_NO[row["superseded"]],
        "Visual Extraction Complete": _YES_NO[row["visual_evidence_extracted"]],
        "Policy Extraction Complete": _YES_NO[row["policy_evidence_extracted"]],
        "Monitoring Active": _YES_NO[row["monitoring_active"]],
    } for row in inventory]

    with st.expander(f"Policy document coverage ({len(missing)} missing of {len(inventory)} expected)"):
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_council_detail(r: dict) -> None:
    """The full operational detail for one council row - shared by both the
    row-selection panel and the legacy per-council expander below it (Part
    6: "reuse the existing operational detail render path... do not create
    duplicate business logic"), so the two entry points can never drift
    apart into showing different things for the same council."""
    if r["review_items_pending"]:
        st.warning(f"⚠️ {r['review_items_pending']} change(s) awaiting review approval for this council.")

    # Housing-supply monitoring amendment ("Add monitored housing
    # supply and delivery reports", Part 6) - every discovered report
    # for this council, regardless of which plan (if any) it's linked
    # to, so an ambiguous/unreviewed discovery is never invisible.
    _render_monitored_reports(r["council_code"])

    # Sprint 3D ("Policy Document Coverage & Discovery", Part 7) - what
    # SHOULD exist for this council versus what's actually been found.
    _render_document_coverage(r["council_code"], r["council_name"])

    if not r["local_plans"]:
        st.caption("No Local Plan ingested yet.")
    for plan in r["local_plans"]:
        version_bit = f" ({plan['plan_version']})" if plan["plan_version"] else ""
        st.markdown(f"**{plan['plan_name']}{version_bit}** — {plan['raw_status'] or plan['status']}")
        st.caption(
            f"{plan['allocations_imported']} allocation(s) imported, {plan['sites_matched']} matched to an "
            f"existing Site" + (f", checked {plan['last_checked'].strftime('%d %b %Y')}" if plan["last_checked"] else "")
        )

        # Sprint 3B ("AI Local Plan Evidence Extraction", Part 10) - plan-
        # level housing requirement/delivery/five-year-supply evidence,
        # extending this existing Policy Intelligence view rather than
        # building a separate page for it. build_plan_evidence_view is a
        # pure function (see app.policy.plan_evidence_view) so this exact
        # assembly is testable independently of Streamlit.
        plan_row = session.get(LocalPlan, plan["plan_id"])
        if plan_row is not None:
            _render_ai_summary(plan_row, r["council_code"])

            evidence_view = build_plan_evidence_view(session, plan_row)
            sections_with_content = [
                (title, evidence_view[key]) for key, title in EVIDENCE_SECTIONS
                if any(e["has_value"] or e["pending_value"] is not None or e["newer_report_pending"] for e in evidence_view[key])
            ]
            if sections_with_content:
                with st.expander("Plan evidence (housing requirement, delivery, five-year supply)"):
                    for title, entries in sections_with_content:
                        st.markdown(f"###### {title}")
                        for entry in entries:
                            _render_evidence_field(entry)


summary_rows = [{
    "Council": r["council_name"],
    "Monitoring": "Enabled" if r["monitoring_enabled"] else "Disabled",
    "Health": HEALTH_LABELS.get(r["monitoring_health"], r["monitoring_health"]),
    "Sources": r["sources_count"],
    "Last checked": r["last_checked"].strftime("%d %b %Y %H:%M") if r["last_checked"] else "Never",
    "Local Plans": len(r["local_plans"]),
    "Allocations imported": r["total_allocations_imported"],
    "Review items pending": r["review_items_pending"],
} for r in rows]

# Live Deployment Integrity audit (Part 6) - clicking a row shows that
# council's operational detail immediately beneath the table, reusing
# _render_council_detail rather than a second copy of this rendering. The
# expanders below are left in place (Part 6: "do not remove the existing
# expanders until the replacement behaviour is proven complete") - this is
# additive, not a replacement, until that's confirmed in a follow-up.
table_event = st.dataframe(
    pd.DataFrame(summary_rows), use_container_width=True, hide_index=True,
    on_select="rerun", selection_mode="single-row", key="council-ops-table",
)
selected_rows = table_event.selection.rows if table_event and table_event.selection else []
if selected_rows:
    selected = rows[selected_rows[0]]
    st.markdown(f"#### {selected['council_name']}")
    _render_council_detail(selected)
    st.divider()

for r in rows:
    with st.expander(f"{r['council_name']} - {len(r['local_plans'])} Local Plan(s)"):
        _render_council_detail(r)
