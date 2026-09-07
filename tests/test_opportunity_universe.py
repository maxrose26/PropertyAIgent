"""Gate 1 (Acquisition Monitoring Substrate) - tests for app.reporting.
opportunity_universe: stable logical identity and the deterministic
fingerprint fact set built on top of the platform's own existing,
unmodified opportunity-detection functions.
"""
from __future__ import annotations

import datetime as dt

from app.db.models import Application, ControlRelationship, LocalPlan, LocalPlanSite, Site
from app.reporting.opportunity_universe import (
    build_current_opportunity_universe,
    compute_opportunity_fingerprint,
    planning_delivery_phase_opportunity_id,
    planning_delivery_site_opportunity_id,
    strategic_land_opportunity_id,
)


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


def _granted_site(session, *, decision_date: dt.date) -> Site:
    site = Site(council_code="testcouncil", canonical_address=f"site-{decision_date.isoformat()}", display_address=f"Site {decision_date.isoformat()}")
    session.add(site)
    session.flush()
    session.add(Application(
        council_code="testcouncil", reference=f"APP-{site.id}", site_id=site.id,
        decision="Granted", decision_issued_date=decision_date.strftime("%a %d %b %Y"),
        first_seen_at=dt.datetime.now(dt.timezone.utc),
    ))
    session.commit()
    return site


# --- Opportunity identity -----------------------------------------------

def test_strategic_land_identity_is_stable_and_reproducible(session):
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan.id, site_name="Wharfside", minimum_dwellings=8400, maximum_capacity=15000)

    universe_1 = build_current_opportunity_universe(session)
    universe_2 = build_current_opportunity_universe(session)
    record_1 = next(r for r in universe_1 if r.opportunity_id == strategic_land_opportunity_id(allocation.id))
    record_2 = next(r for r in universe_2 if r.opportunity_id == strategic_land_opportunity_id(allocation.id))
    assert record_1.opportunity_id == record_2.opportunity_id == f"strategic_land:allocation:{allocation.id}"


def test_planning_delivery_site_identity_is_stable(session):
    today = dt.date.today()
    site = _granted_site(session, decision_date=today - dt.timedelta(days=3 * 365 - 50))

    universe = build_current_opportunity_universe(session)
    expected_id = planning_delivery_site_opportunity_id(site.id)
    assert any(r.opportunity_id == expected_id for r in universe)
    # Reproducible across a second, independent build.
    universe_again = build_current_opportunity_universe(session)
    assert any(r.opportunity_id == expected_id for r in universe_again)


def test_planning_delivery_phase_identity_helper_is_stable_and_reproducible():
    """Direct unit test of the identity contract itself (real phase
    detection via app.pipeline.phase_tracking.build_phase_breakdown is
    exercised separately by tests/test_dashboard.py's own undeveloped-
    phase tests - not re-tested here) - the SAME site_id/phase_code always
    produces the SAME identity string, and app.reporting.opportunity_
    universe's own card-id reuse (card["id"].rsplit("-", 1)[-1]) picks out
    exactly the trailing phase_code segment app.reporting.dashboard.
    _undeveloped_phase_cards already assigns as f"opp-phase-{site_id}-
    {code}"."""
    assert planning_delivery_phase_opportunity_id(42, "A") == "planning_delivery:phase:42:A"
    assert planning_delivery_phase_opportunity_id(42, "A") == planning_delivery_phase_opportunity_id(42, "A")
    assert planning_delivery_phase_opportunity_id(42, "A") != planning_delivery_phase_opportunity_id(42, "B")

    card_id = "opp-phase-42-A"
    phase_code = card_id.rsplit("-", 1)[-1]
    assert planning_delivery_phase_opportunity_id(42, phase_code) == "planning_delivery:phase:42:A"


# --- Opportunity fingerprint ----------------------------------------------

def test_material_fact_change_changes_the_fingerprint():
    fields_before = {"unit_count": 100, "development_type_raw": "houses", "planning_state": "permission_granted"}
    fields_after = {"unit_count": 150, "development_type_raw": "houses", "planning_state": "permission_granted"}
    assert compute_opportunity_fingerprint(fields_before) != compute_opportunity_fingerprint(fields_after)


def test_identical_fields_in_a_different_order_produce_the_same_fingerprint():
    fields_a = {"unit_count": 100, "development_type_raw": "houses"}
    fields_b = {"development_type_raw": "houses", "unit_count": 100}
    assert compute_opportunity_fingerprint(fields_a) == compute_opportunity_fingerprint(fields_b)


def test_strategic_land_fingerprint_excludes_noise_and_includes_material_facts(session):
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan.id, site_name="Noise Test", minimum_dwellings=200)
    universe = build_current_opportunity_universe(session)
    record = next(r for r in universe if r.opportunity_id == strategic_land_opportunity_id(allocation.id))

    # Material facts are present.
    assert "unit_count" in record.fingerprint_fields
    assert "development_type_raw" in record.fingerprint_fields
    assert "planning_state" in record.fingerprint_fields

    # Non-material noise (timestamps, source URLs) is never part of the
    # fingerprint fact set at all - a routine re-check with nothing new
    # must never register as a change purely because updated_at ticked.
    assert "updated_at" not in record.fingerprint_fields
    assert "source_document_url" not in record.fingerprint_fields
    assert "source_page" not in record.fingerprint_fields


def test_planning_delivery_fingerprint_excludes_live_day_countdown(session):
    """The single most important noise-exclusion case: a lapse card's own
    "N days left" figure changes every single day purely with the passage
    of time - the fingerprint must use the STABLE underlying deadline
    date/lapse-status, never that live countdown, or every opportunity
    would register as materially changed once a day forever."""
    today = dt.date.today()
    site = _granted_site(session, decision_date=today - dt.timedelta(days=3 * 365 - 50))
    universe = build_current_opportunity_universe(session)
    record = next(r for r in universe if r.opportunity_id == planning_delivery_site_opportunity_id(site.id))

    assert "deadline" in record.fingerprint_fields
    assert "lapse_status" in record.fingerprint_fields
    for key in record.fingerprint_fields:
        assert "days_left" not in key and "days left" not in key


def test_ownership_evidence_count_is_part_of_the_planning_delivery_fingerprint(session):
    today = dt.date.today()
    site = _granted_site(session, decision_date=today - dt.timedelta(days=3 * 365 - 50))
    universe_before = build_current_opportunity_universe(session)
    record_before = next(r for r in universe_before if r.opportunity_id == planning_delivery_site_opportunity_id(site.id))
    assert record_before.fingerprint_fields["ownership_evidence_count"] == 0

    session.add(ControlRelationship(
        site_id=site.id, entity_name_raw="Example Developer Ltd", entity_type="company", role="OWNER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER", extraction_method="deterministic_regex",
    ))
    session.commit()

    universe_after = build_current_opportunity_universe(session)
    record_after = next(r for r in universe_after if r.opportunity_id == planning_delivery_site_opportunity_id(site.id))
    assert record_after.fingerprint_fields["ownership_evidence_count"] == 1
    assert compute_opportunity_fingerprint(record_before.fingerprint_fields) != compute_opportunity_fingerprint(record_after.fingerprint_fields)
