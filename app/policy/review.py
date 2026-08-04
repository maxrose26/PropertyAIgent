"""Deterministic approval/rejection for queued PolicyChangeEvent rows
(Sprint 1 CTO-review amendment, "Protect trusted state from ambiguous
changes").

Ingestion (ingest_local_plan.py) and monitoring (app.policy.monitor) never
write an ambiguous change straight onto a LocalPlan/LocalPlanSite's trusted
fields - they only ever create a PolicyChangeEvent with review_status=
"needs_review" and a proposed_data payload describing what WOULD change.
approve_change and reject_change below are the only two functions in this
codebase allowed to resolve that: apply it (with history preserved first),
or leave the current value exactly as it was and record that the proposal
was rejected. No full review-queue UI is built in this amendment - these
are the deterministic building blocks a future UI (or a script, or a test)
calls directly.
"""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import select

from app.db.models import LocalPlan, LocalPlanSite, MonitoredReport, PolicyChangeEvent
from app.policy.history import snapshot_allocation, snapshot_field, snapshot_plan_status
from app.policy.progression import classify_progression

_RESOLVABLE_FIELDS_ALLOCATION = {
    "site_name", "minimum_dwellings", "indicative_capacity", "maximum_capacity",
    "category", "allocation_status", "raw_allocation_status",
}
# Sprint 1's original three - kept snapshotted via snapshot_plan_status
# (LocalPlanStatusHistory), unchanged, below.
_RESOLVABLE_FIELDS_PLAN_LEGACY = {"status", "raw_status", "plan_version"}
# Sprint 3B ("AI Local Plan Evidence Extraction") - every LocalPlan column an
# extracted evidence fact can propose a value for. Named after the actual
# LocalPlan attribute, NOT the app.extraction.plan_evidence field name where
# the two differ (raw_plan_status -> raw_status, total_plan_housing_
# requirement -> total_housing_requirement) - app.policy.extract_plan_evidence
# is responsible for that translation before proposed_data is ever written,
# so this module only ever deals in real LocalPlan attribute names.
_RESOLVABLE_FIELDS_PLAN_EVIDENCE = {
    "plan_name", "planning_system", "plan_period_start", "plan_period_end",
    "publication_date", "submission_date", "examination_status", "inspector_report_date",
    "adoption_date", "expected_adoption_date", "next_milestone", "next_milestone_date",
    "status_notes",
    "annual_housing_requirement", "total_housing_requirement", "housing_need_annual",
    "housing_need_total", "requirement_basis", "unmet_need", "neighbouring_authority_contribution",
    "requirement_notes",
    "latest_reporting_period", "homes_delivered_latest_period", "cumulative_homes_delivered",
    "delivery_requirement_for_period", "delivery_surplus_or_shortfall", "housing_delivery_test_result",
    "trajectory_remaining_requirement", "delivery_notes",
    "five_year_supply_years", "five_year_supply_base_date", "five_year_supply_publication_date",
    "deliverable_supply_dwellings", "five_year_requirement_dwellings",
    "five_year_shortfall_or_surplus_dwellings", "buffer_percentage", "calculation_method",
    "supply_position_notes",
}
_RESOLVABLE_FIELDS_PLAN = _RESOLVABLE_FIELDS_PLAN_LEGACY | _RESOLVABLE_FIELDS_PLAN_EVIDENCE
# Housing-supply monitoring amendment ("Add monitored housing supply and
# delivery reports") - resolves report_classification_needs_review
# (proposed_data supplies a reviewer-confirmed source_type, typically via
# approve_change's override_data param below, since an AMBIGUOUS
# classification has no machine-proposed value to just replay) and
# report_supersession_needs_review (proposed_data is
# {"status": "superseded", "superseded_by_id": <new report id>}) events.
_RESOLVABLE_FIELDS_REPORT = {"source_type", "classification_status", "matched_classification_rule", "status", "superseded_by_id"}


def _recompute_allocation_review_status(session, row: LocalPlanSite) -> None:
    """A single allocation can have more than one PolicyChangeEvent queued
    at once (e.g. a capacity change AND a status change from the same
    ingest run) - resolving one shouldn't mark the row "confirmed" while
    another still genuinely needs a decision."""
    still_pending = session.execute(
        select(PolicyChangeEvent).where(
            PolicyChangeEvent.allocation_id == row.id, PolicyChangeEvent.review_status == "needs_review",
        )
    ).first() is not None
    row.review_status = "needs_review" if still_pending else "confirmed"


def approve_change(session, event: PolicyChangeEvent, note: str | None = None, override_data: dict | None = None) -> None:
    """Applies event.proposed_data (or override_data, if given) onto the
    LocalPlan/LocalPlanSite/MonitoredReport it targets, snapshotting the
    PRE-change state into history first where that applies, then marks the
    event confirmed. Raises if the event isn't actually pending -
    approving/rejecting twice, or approving something that was already
    auto-applied, is a programming error, not a silent no-op.

    override_data exists for report_classification_needs_review events
    (housing-supply monitoring amendment): an AMBIGUOUS classification has
    no machine-proposed source_type to just replay - the reviewer supplies
    the real value themselves, e.g.
    approve_change(session, event, override_data={"source_type": "housing_delivery_report", "classification_status": "auto"}).
    Ignored for every other event type, which always applies proposed_data
    exactly as detected."""
    if event.review_status != "needs_review":
        raise ValueError(
            f"PolicyChangeEvent {event.id} is not pending review (review_status={event.review_status!r}) - "
            f"nothing to approve."
        )

    proposed = override_data if override_data is not None else (json.loads(event.proposed_data) if event.proposed_data else {})

    if event.allocation_id is not None:
        row = session.get(LocalPlanSite, event.allocation_id)
        snapshot_allocation(session, row, change_reason=event.event_type)
        for field, value in proposed.items():
            if field in _RESOLVABLE_FIELDS_ALLOCATION:
                setattr(row, field, value)
        # row.review_status is set below by _recompute_allocation_review_status,
        # after event.review_status is updated - not here, since another
        # event for the same allocation might still be pending.
        plan_status = row.local_plan.status if row.local_plan else None
        signal, reasons = classify_progression(plan_status, row.allocation_status, present_in_latest_version=True)
        row.progression_signal = signal
        row.progression_reasons = json.dumps(reasons)
        row.progression_computed_at = dt.datetime.now(dt.timezone.utc)
    elif event.monitored_report_id is not None:
        # Checked BEFORE local_plan_id below: a report_supersession_needs_
        # review event's proposed_data uses field names ("status") that
        # ALSO happen to be resolvable LocalPlan fields - report events
        # always carry a monitored_report_id, so branching on that first
        # (rather than local_plan_id, which such an event may incidentally
        # also carry for dashboard visibility) is what keeps these two
        # targets from ever being confused.
        report = session.get(MonitoredReport, event.monitored_report_id)
        for field, value in proposed.items():
            if field in _RESOLVABLE_FIELDS_REPORT:
                setattr(report, field, value)
    elif event.local_plan_id is not None:
        plan = session.get(LocalPlan, event.local_plan_id)
        snapshot_plan_status(session, plan, note=f"Pre-approval snapshot before applying event {event.id} ({event.event_type}).")
        for field, value in proposed.items():
            if field not in _RESOLVABLE_FIELDS_PLAN:
                continue
            if field in _RESOLVABLE_FIELDS_PLAN_EVIDENCE:
                # snapshot_plan_status above only ever captures status/
                # raw_status/plan_version - every other resolvable field
                # needs its own pre-change value recorded here, or approving
                # this event would lose it with no audit trail at all.
                snapshot_field(session, plan, field_name=field, old_value=getattr(plan, field), new_value=value, change_reason=event.event_type)
            setattr(plan, field, value)
        # A plan's own status/version changing does NOT cascade onto its
        # allocations' individual allocation_status - each allocation's
        # adopted/removed/etc. state stays exactly what it already was.
        # This is deliberate, not an oversight: see Sec.5 of the sprint's
        # adopted-status safeguard requirement, and
        # tests/test_progression.py's negative "adopted plan does not
        # adopt an unconfirmed allocation" cases.

    event.review_status = "confirmed"
    event.reviewed_at = dt.datetime.now(dt.timezone.utc)
    event.reviewed_note = note
    if event.allocation_id is not None:
        _recompute_allocation_review_status(session, session.get(LocalPlanSite, event.allocation_id))
    session.commit()


def reject_change(session, event: PolicyChangeEvent, note: str | None = None) -> None:
    """Records that a proposed change was reviewed and declined. Touches
    NOTHING on the target LocalPlan/LocalPlanSite's actual data fields -
    the current value was judged correct (or the proposal a
    mis-extraction/false positive) - the only state that changes is the
    event's own review outcome, plus the allocation's denormalised
    "has a pending review" flag if this was its last one."""
    if event.review_status != "needs_review":
        raise ValueError(
            f"PolicyChangeEvent {event.id} is not pending review (review_status={event.review_status!r}) - "
            f"nothing to reject."
        )
    event.review_status = "rejected"
    event.reviewed_at = dt.datetime.now(dt.timezone.utc)
    event.reviewed_note = note
    if event.allocation_id is not None:
        _recompute_allocation_review_status(session, session.get(LocalPlanSite, event.allocation_id))
    session.commit()
