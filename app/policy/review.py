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

from app.db.models import LocalPlan, LocalPlanSite, PolicyChangeEvent
from app.policy.history import snapshot_allocation, snapshot_plan_status
from app.policy.progression import classify_progression

_RESOLVABLE_FIELDS_ALLOCATION = {
    "site_name", "minimum_dwellings", "indicative_capacity", "maximum_capacity",
    "category", "allocation_status", "raw_allocation_status",
}
_RESOLVABLE_FIELDS_PLAN = {"status", "raw_status", "plan_version"}


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


def approve_change(session, event: PolicyChangeEvent, note: str | None = None) -> None:
    """Applies event.proposed_data onto the LocalPlan or LocalPlanSite it
    targets, snapshotting the PRE-change state into history first, then
    marks the event confirmed. Raises if the event isn't actually pending -
    approving/rejecting twice, or approving something that was already
    auto-applied, is a programming error, not a silent no-op."""
    if event.review_status != "needs_review":
        raise ValueError(
            f"PolicyChangeEvent {event.id} is not pending review (review_status={event.review_status!r}) - "
            f"nothing to approve."
        )

    proposed = json.loads(event.proposed_data) if event.proposed_data else {}

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
    elif event.local_plan_id is not None:
        plan = session.get(LocalPlan, event.local_plan_id)
        snapshot_plan_status(session, plan, note=f"Pre-approval snapshot before applying event {event.id} ({event.event_type}).")
        for field, value in proposed.items():
            if field in _RESOLVABLE_FIELDS_PLAN:
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
