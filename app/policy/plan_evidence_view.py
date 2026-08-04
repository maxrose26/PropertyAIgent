"""Builds the Sprint 3B ("AI Local Plan Evidence Extraction") plan-level
evidence view - Part 10's four sections (Plan status / Housing requirement
/ Housing delivery / Five-year supply), each field paired with the source
evidence that backed it and any change still awaiting review. A pure
data-assembly function, kept separate from Streamlit - the same "keep
business logic out of the UI" pattern already established by
app.policy.site_view and app.policy.council_dashboard.

Never represents an unsupported/missing value as zero (Part 10) - a field
with nothing to show carries value=None/has_value=False throughout; it is
the UI layer's job to render that as an explicit "not available", never a
bare "0".
"""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import LocalPlan, PolicyChangeEvent

# Part 10's four sections, using LocalPlan's own attribute names throughout
# (see app.policy.extract_plan_evidence.EXTRACTION_FIELD_TO_MODEL_FIELD for
# the two places the extraction schema's field names differ from these).
STATUS_FIELDS = [
    "status", "raw_status", "plan_period_start", "plan_period_end",
    "expected_adoption_date", "adoption_date", "next_milestone", "next_milestone_date",
    "examination_status", "publication_date", "submission_date", "inspector_report_date",
]
REQUIREMENT_FIELDS = [
    "annual_housing_requirement", "total_housing_requirement",
    "housing_need_annual", "housing_need_total", "requirement_basis", "unmet_need",
]
DELIVERY_FIELDS = [
    "latest_reporting_period", "homes_delivered_latest_period", "delivery_requirement_for_period",
    "delivery_surplus_or_shortfall", "housing_delivery_test_result", "trajectory_remaining_requirement",
]
FIVE_YEAR_SUPPLY_FIELDS = [
    "five_year_supply_years", "five_year_supply_base_date", "five_year_supply_publication_date",
    "deliverable_supply_dwellings", "five_year_requirement_dwellings",
    "five_year_shortfall_or_surplus_dwellings", "buffer_percentage",
]

# How long a confirmed fact's evidence is treated as current before the UI
# flags it "stale" - a plan-level fact genuinely doesn't change often, but a
# year-old five-year-supply position is exactly the kind of thing Part 10
# asks to be visibly distinguished from a freshly-extracted one.
STALE_AFTER_DAYS = 365


def get_field_evidence(session: Session, local_plan_id: int, field_name: str) -> PolicyChangeEvent | None:
    """The most recently confirmed (or auto-applied) PolicyChangeEvent that
    set field_name on this plan - the evidence behind whatever value is
    currently sitting on the trusted LocalPlan row. Confirmed/auto_applied
    events are never deleted, so this always stays consistent with
    whatever app.policy.review.approve_change or the auto-apply pipeline
    actually wrote, without a separate "current evidence" table that could
    drift out of sync with it."""
    events = session.execute(
        select(PolicyChangeEvent).where(
            PolicyChangeEvent.local_plan_id == local_plan_id,
            PolicyChangeEvent.event_type == "plan_evidence_proposed",
            PolicyChangeEvent.review_status.in_(("confirmed", "auto_applied")),
        ).order_by(PolicyChangeEvent.detected_at.desc())
    ).scalars().all()
    for event in events:
        if event.proposed_data and field_name in json.loads(event.proposed_data):
            return event
    return None


def get_pending_proposals(session: Session, local_plan_id: int) -> dict[str, PolicyChangeEvent]:
    """field_name -> the earliest still-pending PolicyChangeEvent proposing
    a new value for it, so the UI can show "a change is proposed, awaiting
    review" even though the trusted value hasn't moved yet."""
    events = session.execute(
        select(PolicyChangeEvent).where(
            PolicyChangeEvent.local_plan_id == local_plan_id,
            PolicyChangeEvent.event_type == "plan_evidence_proposed",
            PolicyChangeEvent.review_status == "needs_review",
        ).order_by(PolicyChangeEvent.detected_at.asc())
    ).scalars().all()
    result: dict[str, PolicyChangeEvent] = {}
    for event in events:
        if not event.proposed_data:
            continue
        for field_name in json.loads(event.proposed_data):
            result.setdefault(field_name, event)
    return result


def _is_stale(extracted_at: dt.datetime | None) -> bool:
    if extracted_at is None:
        return False
    # SQLite round-trips a stored tz-aware datetime as naive on read back
    # (the same fact app.policy.monitor's own _naive_utcnow works around) -
    # comparing naive-to-naive UTC wall-clock time throughout is correct
    # here, not a workaround for a bug.
    now_naive = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    return (now_naive - extracted_at.replace(tzinfo=None)).days > STALE_AFTER_DAYS


def _build_field_entry(plan: LocalPlan, field_name: str, evidence: PolicyChangeEvent | None, pending: PolicyChangeEvent | None) -> dict:
    value = getattr(plan, field_name)
    pending_value = json.loads(pending.proposed_data)[field_name] if pending else None
    return {
        "field": field_name,
        "value": value,
        "has_value": value is not None,
        "source_document_title": evidence.source_document_title if evidence else None,
        "source_document_url": evidence.source_document_url if evidence else None,
        "source_page": evidence.source_page if evidence else None,
        "source_excerpt": evidence.source_excerpt if evidence else None,
        "is_stale": _is_stale(evidence.extracted_at) if evidence else False,
        "pending_value": pending_value,
        "pending_event_id": pending.id if pending else None,
    }


def build_plan_evidence_view(session: Session, plan: LocalPlan) -> dict:
    """Returns {"plan_id", "plan_name", "status": [...], "requirement": [...],
    "delivery": [...], "five_year_supply": [...]} - each list holds one
    field-entry dict per field in that section (see _build_field_entry),
    in Part 10's own stated field order."""
    pending_by_field = get_pending_proposals(session, plan.id)
    sections = {}
    for section_key, fields in (
        ("status", STATUS_FIELDS), ("requirement", REQUIREMENT_FIELDS),
        ("delivery", DELIVERY_FIELDS), ("five_year_supply", FIVE_YEAR_SUPPLY_FIELDS),
    ):
        sections[section_key] = [
            _build_field_entry(
                plan, field_name,
                get_field_evidence(session, plan.id, field_name) if getattr(plan, field_name) is not None else None,
                pending_by_field.get(field_name),
            )
            for field_name in fields
        ]
    return {"plan_id": plan.id, "plan_name": plan.plan_name, **sections}
