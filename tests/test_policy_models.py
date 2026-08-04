import datetime as dt

from sqlalchemy import select

from app.db.models import (
    AllocationVersion,
    LocalPlan,
    LocalPlanSite,
    LocalPlanStatusHistory,
    MonitoredSource,
    PolicyChangeEvent,
)


def test_create_local_plan(session):
    plan = LocalPlan(
        council_code="testcouncil", plan_name="Test Local Plan", plan_version="Regulation 18",
        status="issues_and_options", raw_status="Issues and Options consultation",
        plan_period="2024-2042", annual_housing_requirement=500, total_housing_requirement=9000,
        housing_land_supply="5.2 years",
    )
    session.add(plan)
    session.commit()

    stored = session.execute(select(LocalPlan).where(LocalPlan.plan_name == "Test Local Plan")).scalar_one()
    assert stored.status == "issues_and_options"
    assert stored.raw_status == "Issues and Options consultation"
    assert stored.plan_period == "2024-2042"
    assert stored.annual_housing_requirement == 500


def test_create_allocation_linked_to_plan(session):
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Local Plan", status="draft_consultation", raw_status="draft")
    session.add(plan)
    session.commit()

    allocation = LocalPlanSite(
        council_code="testcouncil", local_plan_id=plan.id,
        policy_reference="HOM 2.30", site_name="Sanderling Road", minimum_dwellings=40,
        plan_name="Test Local Plan", plan_status="draft",
        allocation_status="draft_allocation", raw_allocation_status="Draft allocation",
    )
    session.add(allocation)
    session.commit()

    stored = session.execute(select(LocalPlanSite).where(LocalPlanSite.policy_reference == "HOM 2.30")).scalar_one()
    assert stored.local_plan_id == plan.id
    assert stored.local_plan.plan_name == "Test Local Plan"
    # Legacy fields must remain populated - existing code (the Local Plan
    # browse page) reads these directly, not through local_plan.
    assert stored.plan_name == "Test Local Plan"
    assert stored.plan_status == "draft"


def test_allocation_status_never_defaults_to_adopted(session):
    allocation = LocalPlanSite(
        council_code="testcouncil", policy_reference="HOM 2.31", site_name="Draft Site",
        plan_name="Test Local Plan", plan_status="draft",
    )
    session.add(allocation)
    session.commit()
    assert allocation.allocation_status is None  # not yet classified, never a silent "adopted"


def test_adopted_allocation_status(session):
    allocation = LocalPlanSite(
        council_code="testcouncil", policy_reference="HOM 2.32", site_name="Adopted Site",
        plan_name="Test Local Plan", plan_status="adopted",
        allocation_status="adopted_allocation", raw_allocation_status="Adopted allocation",
    )
    session.add(allocation)
    session.commit()
    assert allocation.allocation_status == "adopted_allocation"


def test_removed_allocation_status_is_preserved_not_deleted(session):
    allocation = LocalPlanSite(
        council_code="testcouncil", policy_reference="HOM 2.33", site_name="Dropped Site",
        plan_name="Test Local Plan", plan_status="draft", allocation_status="removed",
    )
    session.add(allocation)
    session.commit()
    allocation_id = allocation.id

    # "Removed" is a status, not a deletion - the row must still exist.
    still_there = session.get(LocalPlanSite, allocation_id)
    assert still_there is not None
    assert still_there.allocation_status == "removed"


def test_allocation_version_history_is_append_only(session):
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Local Plan", status="draft_consultation")
    session.add(plan)
    session.commit()
    allocation = LocalPlanSite(
        council_code="testcouncil", local_plan_id=plan.id, policy_reference="HOM 2.34",
        site_name="Versioned Site", minimum_dwellings=40, plan_name="Test Local Plan", plan_status="draft",
    )
    session.add(allocation)
    session.commit()

    session.add(AllocationVersion(
        allocation_id=allocation.id, local_plan_id=plan.id, policy_reference="HOM 2.34",
        site_name="Versioned Site", minimum_dwellings=40, change_reason="initial_migration",
    ))
    session.add(AllocationVersion(
        allocation_id=allocation.id, local_plan_id=plan.id, policy_reference="HOM 2.34",
        site_name="Versioned Site", minimum_dwellings=55, change_reason="capacity_changed",
    ))
    session.commit()

    versions = session.execute(
        select(AllocationVersion).where(AllocationVersion.allocation_id == allocation.id)
    ).scalars().all()
    assert len(versions) == 2
    assert {v.minimum_dwellings for v in versions} == {40, 55}


def test_plan_status_history_records_stage_transition(session):
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Local Plan", status="issues_and_options")
    session.add(plan)
    session.commit()

    session.add(LocalPlanStatusHistory(local_plan_id=plan.id, status="issues_and_options", note="initial"))
    plan.status = "draft_consultation"
    session.add(LocalPlanStatusHistory(local_plan_id=plan.id, status="draft_consultation", note="moved to draft consultation"))
    session.commit()

    history = session.execute(
        select(LocalPlanStatusHistory).where(LocalPlanStatusHistory.local_plan_id == plan.id)
    ).scalars().all()
    assert [h.status for h in history] == ["issues_and_options", "draft_consultation"]


def test_monitored_source_defaults_to_never_checked(session):
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Local Plan", status="draft_consultation")
    session.add(plan)
    session.commit()

    source = MonitoredSource(
        council_code="testcouncil", local_plan_id=plan.id,
        url="https://example.invalid/local-plan.pdf", source_type="pdf", title="Local Plan PDF",
    )
    session.add(source)
    session.commit()
    assert source.monitoring_health == "never_checked"
    assert source.content_hash is None


def test_policy_change_event_is_never_overwritten(session):
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Local Plan", status="draft_consultation")
    session.add(plan)
    session.commit()

    session.add(PolicyChangeEvent(
        local_plan_id=plan.id, event_type="new_plan_version", new_value="Regulation 18",
        auto_applied=True, review_status="auto_applied",
    ))
    session.add(PolicyChangeEvent(
        local_plan_id=plan.id, event_type="stage_change", old_value="issues_and_options",
        new_value="draft_consultation", auto_applied=False, review_status="needs_review",
    ))
    session.commit()

    events = session.execute(
        select(PolicyChangeEvent).where(PolicyChangeEvent.local_plan_id == plan.id)
    ).scalars().all()
    assert len(events) == 2
    assert {e.event_type for e in events} == {"new_plan_version", "stage_change"}
