import json

import pytest
from sqlalchemy import select

from app.db.models import AllocationVersion, LocalPlan, LocalPlanSite, LocalPlanStatusHistory, PolicyChangeEvent
from app.policy.change_detection import classify_confidence, diff_allocations
from app.policy.progression import classify_progression
from app.policy.review import approve_change, reject_change


def _make_plan(session, status="draft_consultation", raw_status="draft"):
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Local Plan", status=status, raw_status=raw_status)
    session.add(plan)
    session.commit()
    return plan


def _make_allocation(session, plan, ref="HOM 2.30", dwellings=40, allocation_status="draft_allocation"):
    row = LocalPlanSite(
        council_code="testcouncil", local_plan_id=plan.id, policy_reference=ref, site_name="Sanderling Road",
        minimum_dwellings=dwellings, plan_name=plan.plan_name, plan_status=plan.raw_status,
        allocation_status=allocation_status, raw_allocation_status=allocation_status, review_status="auto_applied",
    )
    session.add(row)
    session.commit()
    return row


def _queue_capacity_change(session, plan, row, new_dwellings):
    """Mirrors exactly what ingest_local_plan.py does for a capacity_changed
    event - creates a PolicyChangeEvent with proposed_data, never touches
    row.minimum_dwellings directly."""
    old = {"policy_reference": row.policy_reference, "minimum_dwellings": row.minimum_dwellings,
           "indicative_capacity": None, "maximum_capacity": None, "allocation_status": row.allocation_status}
    new = dict(old, minimum_dwellings=new_dwellings)
    [event] = diff_allocations([old], [new])
    assert event["event_type"] == "capacity_changed"
    assert classify_confidence(event["event_type"]) == "needs_review"

    change = PolicyChangeEvent(
        local_plan_id=plan.id, allocation_id=row.id, event_type=event["event_type"],
        old_value=event["old_value"], new_value=event["new_value"], detail=event["detail"],
        proposed_data=json.dumps({"minimum_dwellings": new_dwellings}),
        source_document_url="https://example.invalid/plan.pdf", source_page=110,
        auto_applied=False, review_status="needs_review",
    )
    session.add(change)
    row.review_status = "needs_review"
    session.commit()
    return change


def test_ambiguous_change_leaves_trusted_value_unchanged(session):
    plan = _make_plan(session)
    row = _make_allocation(session, plan, dwellings=40)

    _queue_capacity_change(session, plan, row, new_dwellings=55)

    session.refresh(row)
    assert row.minimum_dwellings == 40  # untouched - the proposal is only in the event, not applied
    assert row.review_status == "needs_review"


def test_approving_a_proposed_change_applies_it_and_writes_history(session):
    plan = _make_plan(session)
    row = _make_allocation(session, plan, dwellings=40)
    change = _queue_capacity_change(session, plan, row, new_dwellings=55)

    approve_change(session, change, note="Confirmed against the latest plan document.")

    session.refresh(row)
    assert row.minimum_dwellings == 55
    assert row.review_status == "confirmed"

    session.refresh(change)
    assert change.review_status == "confirmed"
    assert change.reviewed_note == "Confirmed against the latest plan document."
    assert change.reviewed_at is not None

    versions = session.execute(
        select(AllocationVersion).where(AllocationVersion.allocation_id == row.id)
    ).scalars().all()
    assert len(versions) == 1
    assert versions[0].minimum_dwellings == 40  # the PRE-change value, preserved


def test_rejecting_a_proposed_change_preserves_the_current_value(session):
    plan = _make_plan(session)
    row = _make_allocation(session, plan, dwellings=40)
    change = _queue_capacity_change(session, plan, row, new_dwellings=55)

    reject_change(session, change, note="Extraction error - the PDF's table cell was misread.")

    session.refresh(row)
    assert row.minimum_dwellings == 40  # unchanged
    assert row.review_status == "confirmed"  # reviewed, current value stands - no longer "pending"

    session.refresh(change)
    assert change.review_status == "rejected"
    assert change.reviewed_note == "Extraction error - the PDF's table cell was misread."

    # Rejection must never write a version snapshot - nothing changed.
    versions = session.execute(
        select(AllocationVersion).where(AllocationVersion.allocation_id == row.id)
    ).scalars().all()
    assert versions == []


def test_cannot_approve_or_reject_an_already_resolved_event(session):
    plan = _make_plan(session)
    row = _make_allocation(session, plan, dwellings=40)
    change = _queue_capacity_change(session, plan, row, new_dwellings=55)

    approve_change(session, change)
    with pytest.raises(ValueError):
        approve_change(session, change)
    with pytest.raises(ValueError):
        reject_change(session, change)


def test_row_stays_needs_review_while_another_event_is_still_pending(session):
    plan = _make_plan(session)
    row = _make_allocation(session, plan, dwellings=40, allocation_status="draft_allocation")
    change_1 = _queue_capacity_change(session, plan, row, new_dwellings=55)

    change_2 = PolicyChangeEvent(
        local_plan_id=plan.id, allocation_id=row.id, event_type="allocation_amended",
        old_value="draft_allocation", new_value="submitted_allocation",
        proposed_data=json.dumps({"allocation_status": "submitted_allocation"}),
        auto_applied=False, review_status="needs_review",
    )
    session.add(change_2)
    session.commit()

    approve_change(session, change_1)
    session.refresh(row)
    assert row.review_status == "needs_review"  # change_2 is still pending

    approve_change(session, change_2)
    session.refresh(row)
    assert row.review_status == "confirmed"  # now both are resolved
    assert row.allocation_status == "submitted_allocation"


def test_approving_a_plan_level_event_writes_status_history_and_applies_it(session):
    plan = _make_plan(session, status="issues_and_options", raw_status="Issues and Options")
    event = PolicyChangeEvent(
        local_plan_id=plan.id, event_type="stage_change", old_value="issues_and_options",
        new_value="draft_consultation", detail="Plan stage changed.",
        proposed_data=json.dumps({"status": "draft_consultation", "raw_status": "Draft consultation"}),
        auto_applied=False, review_status="needs_review",
    )
    session.add(event)
    session.commit()

    approve_change(session, event)

    session.refresh(plan)
    assert plan.status == "draft_consultation"
    assert plan.raw_status == "Draft consultation"

    history = session.execute(
        select(LocalPlanStatusHistory).where(LocalPlanStatusHistory.local_plan_id == plan.id)
    ).scalars().all()
    assert len(history) == 1
    assert history[0].status == "issues_and_options"  # the PRE-change status, preserved


def test_approving_plan_adoption_does_not_cascade_to_allocations(session):
    # Sec.5 safeguard: an adopted LocalPlan must not automatically make an
    # allocation with no independently confirmed status "adopted".
    plan = _make_plan(session, status="examination", raw_status="Examination")
    unconfirmed = _make_allocation(session, plan, ref="HOM 2.30", allocation_status="submitted_allocation")
    removed = _make_allocation(session, plan, ref="HOM 2.31", allocation_status="removed")

    event = PolicyChangeEvent(
        local_plan_id=plan.id, event_type="adoption", old_value="examination", new_value="adopted",
        proposed_data=json.dumps({"status": "adopted", "raw_status": "Adopted"}),
        auto_applied=False, review_status="needs_review",
    )
    session.add(event)
    session.commit()

    approve_change(session, event)

    session.refresh(plan)
    session.refresh(unconfirmed)
    session.refresh(removed)
    assert plan.status == "adopted"
    assert unconfirmed.allocation_status == "submitted_allocation"  # untouched by the plan-level approval
    assert removed.allocation_status == "removed"  # still removed, not resurrected as adopted

    signal_unconfirmed, _ = classify_progression(plan.status, unconfirmed.allocation_status)
    signal_removed, _ = classify_progression(plan.status, removed.allocation_status)
    assert signal_unconfirmed != "adopted"
    assert signal_removed == "removed"
