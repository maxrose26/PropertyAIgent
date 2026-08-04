"""Internal Council administration dashboard (Sprint 2, "Greater Manchester
Policy Intelligence Framework", Part 7). For administration - confirming
what's been onboarded and whether monitoring is actually working - not a
page a prospective land buyer or investor would ever need. See
app.policy.council_dashboard for the pure data assembly this renders.
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
from app.policy.council_dashboard import build_council_dashboard
from app.policy.plan_evidence_view import build_plan_evidence_view
from app.reporting.local_plan_summary import generate_local_plan_summary, is_summary_stale
from app.ui.common import bootstrap, credits_sidebar, get_db

st.set_page_config(page_title="Council dashboard - UK Planning Deal Finder", layout="wide")

bootstrap()
session, settings = get_db()

HOME_PAGE = Path(__file__).resolve().parents[1] / "streamlit_app.py"
st.page_link(HOME_PAGE, label="← Back to search", icon="🔙")

credits_sidebar(session, settings)

st.title("Council administration dashboard")
st.caption(
    "Internal view of Policy Intelligence onboarding per council - which Local Plans have been ingested, "
    "whether monitoring is actually reaching their sources, and what's waiting for a review decision. "
    "Not part of the public site-browsing experience."
)

rows = build_council_dashboard(session)
if not rows:
    st.info("No council has any Policy Intelligence activity yet (no Local Plans ingested, no sources registered).")
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


def _render_ai_summary(plan_row: LocalPlan) -> None:
    """Sprint 3B.1 ("AI Local Plan Summary", Part 7) - shown at the TOP of
    each Local Plan section, above the existing detailed evidence
    expander. Never regenerates on its own (Part 6) - generate_local_plan_
    summary is only ever called from inside the Refresh button's own
    click branch below, so a plain page view/rerun never spends AI cost."""
    st.markdown("##### 🤖 AI Local Plan Summary")

    has_summary = plan_row.ai_summary_text is not None
    button_label = "🔄 Refresh" if has_summary else "Generate summary"
    if st.button(button_label, key=f"refresh_summary_{plan_row.id}"):
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

    st.caption("AI-generated from verified PropertyAIgent evidence")
    st.write(plan_row.ai_summary_text)

    key_risks = json.loads(plan_row.ai_summary_key_risks) if plan_row.ai_summary_key_risks else []
    key_opportunities = json.loads(plan_row.ai_summary_key_opportunities) if plan_row.ai_summary_key_opportunities else []
    evidence_gaps = json.loads(plan_row.ai_summary_evidence_gaps) if plan_row.ai_summary_evidence_gaps else []

    if key_risks:
        st.markdown("**Key risks:**\n" + "\n".join(f"- {r}" for r in key_risks))
    if key_opportunities:
        st.markdown("**Key opportunities:**\n" + "\n".join(f"- {o}" for o in key_opportunities))
    if evidence_gaps:
        st.markdown("**Evidence gaps:**\n" + "\n".join(f"- {g}" for g in evidence_gaps))

    generated_bit = plan_row.ai_summary_generated_at.strftime("%d %b %Y %H:%M") if plan_row.ai_summary_generated_at else "unknown"
    st.caption(f"Generated {generated_bit} · model {plan_row.ai_summary_model or '?'} · prompt version {plan_row.ai_summary_prompt_version or '?'}")


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

st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

for r in rows:
    with st.expander(f"{r['council_name']} - {len(r['local_plans'])} Local Plan(s)"):
        if r["review_items_pending"]:
            st.warning(f"⚠️ {r['review_items_pending']} change(s) awaiting review approval for this council.")

        # Housing-supply monitoring amendment ("Add monitored housing
        # supply and delivery reports", Part 6) - every discovered report
        # for this council, regardless of which plan (if any) it's linked
        # to, so an ambiguous/unreviewed discovery is never invisible.
        _render_monitored_reports(r["council_code"])

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
                _render_ai_summary(plan_row)

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
