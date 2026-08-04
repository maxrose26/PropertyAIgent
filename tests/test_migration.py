from sqlalchemy import select

from app.db.models import AllocationVersion, LocalPlan, LocalPlanSite
from scripts.migrate_policy_intelligence import migrate


def _seed_legacy_allocation(session, ref="HOM 2.30", plan_name="Legacy Local Plan", plan_status="draft"):
    """Shape of a LocalPlanSite row exactly as the pre-sprint pilot created
    it - no local_plan_id, no allocation_status, only the flat plan_name/
    plan_status strings."""
    allocation = LocalPlanSite(
        council_code="testcouncil", policy_reference=ref, site_name="Legacy Site",
        minimum_dwellings=40, plan_name=plan_name, plan_status=plan_status,
    )
    session.add(allocation)
    session.commit()
    return allocation


def test_migration_links_legacy_allocation_to_a_new_local_plan(session):
    allocation = _seed_legacy_allocation(session)
    assert allocation.local_plan_id is None

    result = migrate(session)

    session.refresh(allocation)
    assert allocation.local_plan_id is not None
    assert result["plans_created"] == 1
    assert result["allocations_linked"] == 1

    plan = session.get(LocalPlan, allocation.local_plan_id)
    assert plan.plan_name == "Legacy Local Plan"
    assert plan.raw_status == "draft"


def test_migration_derives_allocation_status_and_flags_for_confirmation(session):
    allocation = _seed_legacy_allocation(session)
    migrate(session)
    session.refresh(allocation)

    assert allocation.allocation_status is not None
    assert allocation.allocation_status != "adopted_allocation"  # never guessed, see test_status.py
    assert allocation.review_status == "needs_confirmation"


def test_migration_writes_an_initial_version_snapshot(session):
    allocation = _seed_legacy_allocation(session)
    migrate(session)

    versions = session.execute(
        select(AllocationVersion).where(AllocationVersion.allocation_id == allocation.id)
    ).scalars().all()
    assert len(versions) == 1
    assert versions[0].change_reason == "initial_migration"


def test_migration_does_not_duplicate_plans_across_allocations_in_the_same_plan(session):
    _seed_legacy_allocation(session, ref="HOM 2.30")
    _seed_legacy_allocation(session, ref="HOM 2.31")

    result = migrate(session)

    assert result["plans_created"] == 1  # both allocations share one plan
    assert result["allocations_linked"] == 2
    plans = session.execute(select(LocalPlan)).scalars().all()
    assert len(plans) == 1


def test_migration_is_idempotent(session):
    _seed_legacy_allocation(session)

    first = migrate(session)
    second = migrate(session)

    assert first["allocations_linked"] == 1
    assert second["allocations_linked"] == 0  # nothing left to migrate
    assert second["plans_created"] == 0

    plans = session.execute(select(LocalPlan)).scalars().all()
    assert len(plans) == 1  # no duplicate plan created on rerun

    versions = session.execute(select(AllocationVersion)).scalars().all()
    assert len(versions) == 1  # no duplicate snapshot written on rerun


def test_migration_preserves_existing_site_match(session):
    allocation = _seed_legacy_allocation(session)
    allocation.matched_site_id = None  # pilot's own "no application yet" case
    allocation.match_confidence = None
    allocation.latitude = 53.4
    allocation.longitude = -2.2
    session.commit()

    migrate(session)
    session.refresh(allocation)

    # Migration must never touch Site-matching fields - it only links to a
    # LocalPlan and derives allocation-level status.
    assert allocation.matched_site_id is None
    assert allocation.latitude == 53.4
    assert allocation.longitude == -2.2


def test_migration_dry_run_writes_nothing(session):
    _seed_legacy_allocation(session)
    result = migrate(session, dry_run=True)

    assert result["allocations_linked"] == 1  # reported...
    plans = session.execute(select(LocalPlan)).scalars().all()
    assert len(plans) == 0  # ...but nothing actually written
