"""Gate 1 (Acquisition Monitoring Substrate) - tests for app.reporting.
opportunity_change: deterministic NEW / MATERIALLY_CHANGED / UNCHANGED
classification and the app.db.models.OpportunityMonitoringState sync.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from sqlalchemy import func

from app.db.models import Application, LocalPlan, LocalPlanSite, OpportunityMonitoringState, Site
from app.reporting.opportunity_change import (
    BASELINE_EXISTING,
    MATERIALLY_CHANGED,
    NEW,
    UNCHANGED,
    REASON_UNIT_COUNT_CHANGED,
    classify_opportunity_change,
    sync_opportunity_monitoring_state,
)
from app.reporting.opportunity_universe import (
    DEFAULT_STRATEGIC_LAND_PAGE_SIZE,
    OpportunityRecord,
    build_current_opportunity_universe,
    strategic_land_opportunity_id,
)
from app.policy.buyer_matching import STRATEGIC_LAND


def _dummy_record(opportunity_id: str, fingerprint_fields: dict) -> OpportunityRecord:
    return OpportunityRecord(opportunity_id=opportunity_id, opportunity_type=STRATEGIC_LAND, matching_facts=None, fingerprint_fields=fingerprint_fields)


# --- Pure classification (no DB) ------------------------------------------

def test_unseen_opportunity_is_classified_new_in_ongoing_mode():
    record = _dummy_record("strategic_land:allocation:1", {"unit_count": 100})
    result = classify_opportunity_change(record, previous_state=None, is_baseline_run=False)
    assert result.classification == NEW
    assert result.reasons == ()


def test_unseen_opportunity_is_classified_baseline_existing_in_baseline_mode():
    """Gate 1 amendment (Product Owner review): the very first time
    monitoring is established against an already-populated database, an
    untracked opportunity must be recorded as historical baseline, never
    as if it had just been discovered."""
    record = _dummy_record("strategic_land:allocation:1", {"unit_count": 100})
    result = classify_opportunity_change(record, previous_state=None, is_baseline_run=True)
    assert result.classification == BASELINE_EXISTING
    assert result.classification != NEW
    assert result.reasons == ()


def test_identical_fingerprint_is_classified_unchanged():
    fields = {"unit_count": 100, "development_type_raw": "houses"}
    record = _dummy_record("strategic_land:allocation:1", fields)
    from app.reporting.opportunity_universe import compute_opportunity_fingerprint
    import json
    previous = OpportunityMonitoringState(
        opportunity_id=record.opportunity_id, opportunity_type=STRATEGIC_LAND,
        fingerprint=compute_opportunity_fingerprint(fields), fingerprint_fields=json.dumps(fields, sort_keys=True),
    )
    result = classify_opportunity_change(record, previous_state=previous)
    assert result.classification == UNCHANGED
    assert result.reasons == ()


def test_changed_material_field_is_classified_materially_changed_with_reason():
    import json
    from app.reporting.opportunity_universe import compute_opportunity_fingerprint

    old_fields = {"unit_count": 100, "development_type_raw": "houses"}
    new_fields = {"unit_count": 150, "development_type_raw": "houses"}
    record = _dummy_record("strategic_land:allocation:1", new_fields)
    previous = OpportunityMonitoringState(
        opportunity_id=record.opportunity_id, opportunity_type=STRATEGIC_LAND,
        fingerprint=compute_opportunity_fingerprint(old_fields), fingerprint_fields=json.dumps(old_fields, sort_keys=True),
    )
    result = classify_opportunity_change(record, previous_state=previous)
    assert result.classification == MATERIALLY_CHANGED
    assert REASON_UNIT_COUNT_CHANGED in result.reasons


# --- sync_opportunity_monitoring_state (real DB) --------------------------

def _make_plan(session, *, status="proposed_submission") -> LocalPlan:
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Local Plan", status=status, raw_status=status)
    session.add(plan)
    session.commit()
    return plan


def _make_allocation(session, plan_id, **kwargs) -> LocalPlanSite:
    allocation = LocalPlanSite(
        council_code=kwargs.pop("council_code", "testcouncil"), local_plan_id=plan_id,
        policy_reference=kwargs.pop("policy_reference", "AN1"), site_name=kwargs.pop("site_name", "Test Allocation"),
        plan_name="Test Local Plan", plan_status=kwargs.pop("plan_status", "proposed_submission"),
        matched_site_id=kwargs.pop("matched_site_id", None), **kwargs,
    )
    session.add(allocation)
    session.commit()
    return allocation


def test_sync_marks_a_first_ever_run_as_baseline_existing_not_new(session):
    """Required Gate 1 amendment behaviour: on the very first call against
    an empty OpportunityMonitoringState table (the first-deployment case),
    every current opportunity must be recorded as BASELINE_EXISTING - it
    must NEVER be classified NEW, since it did not just newly appear, it
    was already sitting in the existing Property AIgent database."""
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan.id, site_name="Fresh Allocation", minimum_dwellings=120)

    counts = sync_opportunity_monitoring_state(session)
    assert counts["baseline_existing"] >= 1
    assert counts["new"] == 0
    assert counts["materially_changed"] == 0

    state = session.execute(
        select(OpportunityMonitoringState).where(OpportunityMonitoringState.opportunity_id == strategic_land_opportunity_id(allocation.id))
    ).scalars().first()
    assert state is not None
    assert state.last_change_classification == BASELINE_EXISTING
    assert state.first_seen_at is not None


def test_sync_classifies_a_genuinely_new_opportunity_as_new_once_baseline_exists(session):
    """Once the monitoring table already holds at least one row (baseline
    established), a genuinely new opportunity appearing afterward IS
    correctly classified NEW - BASELINE_EXISTING only ever applies to the
    one-time, first-ever establishment run."""
    plan = _make_plan(session)
    _make_allocation(session, plan.id, site_name="Already Baselined", minimum_dwellings=120)
    first = sync_opportunity_monitoring_state(session)
    assert first["baseline_existing"] >= 1
    assert first["new"] == 0

    later_allocation = _make_allocation(session, plan.id, site_name="Genuinely New Allocation", policy_reference="AN2", minimum_dwellings=90)
    second = sync_opportunity_monitoring_state(session)
    assert second["new"] >= 1
    assert second["baseline_existing"] == 0  # the table was no longer empty - this is ordinary ongoing monitoring

    state = session.execute(
        select(OpportunityMonitoringState).where(OpportunityMonitoringState.opportunity_id == strategic_land_opportunity_id(later_allocation.id))
    ).scalars().first()
    assert state.last_change_classification == NEW


def test_sync_is_correct_regardless_of_call_order_not_ordering_luck(session):
    """Gate 1 amendment: correctness must not depend on scripts.bootstrap_
    acquisition_monitoring and scripts.sync_opportunity_monitoring being
    invoked in a particular order - sync_opportunity_monitoring_state
    self-detects an empty table and establishes the baseline correctly
    (BASELINE_EXISTING) even if it is the very first thing ever called,
    with no buyer onboarding having happened yet at all."""
    plan = _make_plan(session)
    _make_allocation(session, plan.id, site_name="Called First", minimum_dwellings=120)

    # sync runs before anything resembling buyer onboarding exists.
    assert session.execute(select(func.count()).select_from(OpportunityMonitoringState)).scalar() == 0
    counts = sync_opportunity_monitoring_state(session)
    assert counts["baseline_existing"] >= 1
    assert counts["new"] == 0


def test_sync_detects_a_material_change_on_the_third_run(session):
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan.id, site_name="Changing Allocation", minimum_dwellings=120)

    sync_opportunity_monitoring_state(session)  # BASELINE_EXISTING (first-ever run)
    sync_opportunity_monitoring_state(session)  # UNCHANGED

    allocation.minimum_dwellings = 240
    session.commit()

    counts = sync_opportunity_monitoring_state(session)
    assert counts["materially_changed"] >= 1

    state = session.execute(
        select(OpportunityMonitoringState).where(OpportunityMonitoringState.opportunity_id == strategic_land_opportunity_id(allocation.id))
    ).scalars().first()
    assert state.last_change_classification == MATERIALLY_CHANGED
    assert REASON_UNIT_COUNT_CHANGED in (state.last_change_reasons or "").split(",")
    assert state.last_change_at is not None


def test_sync_never_deletes_a_row_for_a_vanished_opportunity(session):
    """An opportunity leaving the live candidate universe (e.g. an
    allocation getting matched to a Site and dropping out of the
    strategic-land pool) must never delete its monitoring history - it is
    simply not refreshed further, per this gate's own "an opportunity that
    vanishes is itself meaningful information, never cleaned up
    automatically" design."""
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan.id, site_name="Soon Matched", minimum_dwellings=120)
    sync_opportunity_monitoring_state(session)
    opportunity_id = strategic_land_opportunity_id(allocation.id)
    assert session.execute(select(OpportunityMonitoringState).where(OpportunityMonitoringState.opportunity_id == opportunity_id)).scalars().first() is not None

    site = Site(council_code="testcouncil", canonical_address="now-matched", display_address="Now Matched")
    session.add(site)
    session.flush()
    allocation.matched_site_id = site.id  # removes it from the strategic-land candidate query entirely
    session.commit()

    sync_opportunity_monitoring_state(session)
    state = session.execute(select(OpportunityMonitoringState).where(OpportunityMonitoringState.opportunity_id == opportunity_id)).scalars().first()
    assert state is not None  # still present, untouched - never deleted
