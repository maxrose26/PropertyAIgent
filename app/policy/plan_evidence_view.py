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

from app.db.models import LocalPlan, MonitoredReport, PolicyChangeEvent
from app.extraction.plan_evidence import CATEGORIES
from app.policy.document_selection import DOCUMENT_TYPE_TO_CATEGORIES
from app.policy.extract_plan_evidence import EXTRACTION_FIELD_TO_MODEL_FIELD, should_extract

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

# field_name (LocalPlan attribute) -> the set of app.extraction.plan_evidence
# categories that can speak to it - the reverse of CATEGORIES, translated
# through EXTRACTION_FIELD_TO_MODEL_FIELD so this deals only in real
# LocalPlan column names, same convention as app.policy.review.
_FIELD_TO_EXTRACTION_CATEGORIES: dict[str, set[str]] = {}
for _category_name, _category_fields in CATEGORIES.items():
    for _extraction_field in _category_fields:
        _model_field_name = EXTRACTION_FIELD_TO_MODEL_FIELD.get(_extraction_field, _extraction_field)
        _FIELD_TO_EXTRACTION_CATEGORIES.setdefault(_model_field_name, set()).add(_category_name)


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


def get_historic_values(session: Session, local_plan_id: int, field_name: str, exclude_event_id: int | None = None) -> list[dict]:
    """Every CONFIRMED/auto-applied value this field has ever had, most
    recent first, excluding the one currently trusted (exclude_event_id) -
    Part 6: "previous historic figures where available". Nothing is ever
    deleted (Part 1/Part 5's "preserve all historic reports"/"never delete
    or overwrite a previous year's evidence"), so this is always the
    complete history, not a best-effort log."""
    events = session.execute(
        select(PolicyChangeEvent).where(
            PolicyChangeEvent.local_plan_id == local_plan_id,
            PolicyChangeEvent.event_type == "plan_evidence_proposed",
            PolicyChangeEvent.review_status.in_(("confirmed", "auto_applied")),
        ).order_by(PolicyChangeEvent.detected_at.desc())
    ).scalars().all()
    history = []
    for event in events:
        if event.id == exclude_event_id or not event.proposed_data:
            continue
        data = json.loads(event.proposed_data)
        if field_name in data:
            history.append({
                "value": data[field_name], "extracted_at": event.extracted_at,
                "source_document_title": event.source_document_title, "event_id": event.id,
            })
    return history


def _has_newer_unreviewed_report(session: Session, plan: LocalPlan, field_name: str) -> bool:
    """Part 6: "Do not label an older figure as current where a newer
    report has been discovered but not yet reviewed." Scoped, pragmatic
    interpretation: True when a "current"-status MonitoredReport exists
    that's eligible (by source_type routing) to speak to this field's
    category and hasn't had extraction run against it yet (see
    app.policy.extract_plan_evidence.should_extract) - i.e. a report that
    could change this field's trusted value but genuinely hasn't been
    looked at. Does not attempt to compare THIS specific field's evidence
    date against the new report's date - the coarser "any not-yet-
    extracted eligible report exists" signal is what Part 6 actually asks
    the UI to distinguish, without requiring per-field publication-date
    bookkeeping this scale of check doesn't need."""
    categories = _FIELD_TO_EXTRACTION_CATEGORIES.get(field_name)
    if not categories:
        return False
    eligible_types = [t for t, cats in DOCUMENT_TYPE_TO_CATEGORIES.items() if cats & categories]
    if not eligible_types:
        return False
    reports = session.execute(
        select(MonitoredReport).where(
            MonitoredReport.local_plan_id == plan.id,
            MonitoredReport.status == "current",
            MonitoredReport.source_type.in_(eligible_types),
        )
    ).scalars().all()
    return any(should_extract(report) for report in reports)


def _is_stale(extracted_at: dt.datetime | None) -> bool:
    if extracted_at is None:
        return False
    # SQLite round-trips a stored tz-aware datetime as naive on read back
    # (the same fact app.policy.monitor's own _naive_utcnow works around) -
    # comparing naive-to-naive UTC wall-clock time throughout is correct
    # here, not a workaround for a bug.
    now_naive = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    return (now_naive - extracted_at.replace(tzinfo=None)).days > STALE_AFTER_DAYS


def _build_field_entry(session: Session, plan: LocalPlan, field_name: str, evidence: PolicyChangeEvent | None, pending: PolicyChangeEvent | None) -> dict:
    value = getattr(plan, field_name)
    pending_value = json.loads(pending.proposed_data)[field_name] if pending else None
    newer_pending = _has_newer_unreviewed_report(session, plan, field_name)
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
        # Part 6: never label an older figure "current" where a newer
        # report has been discovered but not yet reviewed/extracted.
        "newer_report_pending": newer_pending,
        "historic_values": get_historic_values(session, plan.id, field_name, exclude_event_id=evidence.id if evidence else None),
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
                session, plan, field_name,
                get_field_evidence(session, plan.id, field_name) if getattr(plan, field_name) is not None else None,
                pending_by_field.get(field_name),
            )
            for field_name in fields
        ]
    return {"plan_id": plan.id, "plan_name": plan.plan_name, **sections}
