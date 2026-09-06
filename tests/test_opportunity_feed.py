"""Opportunity Experience V2 - tests for app.reporting.opportunity_feed, the
new unified Dashboard "Opportunities" feed. Follows this codebase's own
established convention (see tests/test_allocation_discovery.py's own
docstring): unit-test the pure/presentation-reshaping logic against a real
in-memory schema, never a Streamlit page script directly, and never a
brittle assertion against exact copy that isn't safety-relevant.
"""
from __future__ import annotations

import datetime as dt

from app.db.models import Application, LocalPlan, LocalPlanSite, Site
from app.reporting.opportunity_feed import (
    PLANNING_DELIVERY,
    STRATEGIC_LAND,
    _reshape_signal_card,
    build_opportunity_feed,
)


def _now(offset_minutes: int = 0) -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=offset_minutes)


def _make_plan(session, *, status="proposed_submission", council_code="testcouncil") -> LocalPlan:
    plan = LocalPlan(council_code=council_code, plan_name="Test Local Plan", status=status, raw_status=status)
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


def _granted_site_with_decision(session, *, decision_date: dt.date, decision: str = "Granted") -> Site:
    site = Site(
        council_code="testcouncil", canonical_address=f"site-{decision_date.isoformat()}",
        display_address=f"Site decided {decision_date.isoformat()}",
    )
    session.add(site)
    session.flush()
    session.add(Application(
        council_code="testcouncil", reference=f"APP-{site.id}", site_id=site.id,
        decision=decision, decision_issued_date=decision_date.strftime("%a %d %b %Y"), first_seen_at=_now(),
    ))
    session.commit()
    return site


# --- Strategic land cards ----------------------------------------------------

def test_strategic_land_card_shape_and_signal_for_a_real_shaped_allocation(session):
    plan = _make_plan(session)
    allocation = _make_allocation(
        session, plan.id, site_name="Wharfside", policy_reference="AN1",
        minimum_dwellings=8400, maximum_capacity=15000, site_area_hectares=145.0,
        source_excerpt="15,000 dwellings (8,400 in plan period)",
    )
    feed = build_opportunity_feed(session, limit=6)
    card = next(c for c in feed["cards"] if c["id"] == f"opp-feed-alloc-{allocation.id}")

    assert card["opportunity_type"] == STRATEGIC_LAND
    assert card["opportunity_type_label"] == "Strategic land"
    assert card["signal"] == "INVESTIGATE"
    assert card["signal_label"] == "Investigate"
    assert card["title"] == "Wharfside"
    assert card["page"] == "pages/3_Local_Plan_Sites.py"
    assert card["params"] == {"allocation_id": str(allocation.id)}
    # Plan-period/wider capacity labels only appear because this fixture's
    # own source_excerpt states the relationship explicitly (see
    # app.reporting.allocation_discovery.capacity_range_labels) - never a
    # universal inference from the bare min/max range.
    metric_labels = [label for label, _ in card["metrics"]]
    assert "Plan-period capacity" in metric_labels
    assert "Wider capacity" in metric_labels
    assert ("Site area", "145.00 ha") in card["metrics"]
    assert "No identified activity" in card["tags"]


def test_strategic_land_card_falls_back_to_generic_capacity_label_without_plan_period_evidence(session):
    plan = _make_plan(session)
    allocation = _make_allocation(
        session, plan.id, site_name="Civic Quarter", policy_reference="AN2",
        minimum_dwellings=3000, maximum_capacity=4000,  # a range, but no source_excerpt at all
    )
    feed = build_opportunity_feed(session, limit=6)
    card = next(c for c in feed["cards"] if c["id"] == f"opp-feed-alloc-{allocation.id}")
    metric_labels = [label for label, _ in card["metrics"]]
    assert "Plan-period capacity" not in metric_labels
    assert "Capacity (range)" in metric_labels


def test_strategic_land_card_shows_not_yet_verified_for_missing_hectares(session):
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan.id, site_name="No Hectares Yet", minimum_dwellings=2000)
    feed = build_opportunity_feed(session, limit=6)
    card = next(c for c in feed["cards"] if c["id"] == f"opp-feed-alloc-{allocation.id}")
    assert ("Site area", "Not yet verified") in card["metrics"]


def test_matched_allocation_is_excluded_from_the_strategic_land_feed(session):
    plan = _make_plan(session)
    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.flush()
    _make_allocation(session, plan.id, site_name="Already Matched", minimum_dwellings=5000, matched_site_id=site.id)
    feed = build_opportunity_feed(session, limit=6)
    titles = [c["title"] for c in feed["cards"]]
    assert "Already Matched" not in titles


# --- The three real evidence shapes this workstream must keep distinguishable
# (Trafford Waters / Pomona / Stretford Mall) -------------------------------

def test_no_candidate_site_still_produces_a_real_investigate_card(session):
    # No Site in the platform even text-resembles this allocation's name -
    # the genuine "nothing found" shape (distinct from the false-match and
    # process-gap shapes covered below). headline_reason is deliberately
    # the FIRST reason (the capacity/allocation-type sentence), not the
    # match-related one - see build_opportunity_signal's own reason
    # ordering, unchanged here.
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan.id, site_name="Wharfside", minimum_dwellings=15000)
    feed = build_opportunity_feed(session, limit=6)
    card = next(c for c in feed["cards"] if c["id"] == f"opp-feed-alloc-{allocation.id}")
    assert card["signal"] == "INVESTIGATE"
    assert "15,000 homes" in card["headline_reason"]


def test_false_match_and_process_gap_are_distinguished_not_shown_as_confirmed(session):
    # Real Trafford false-positive shape: "Trafford Waters" (Urmston) and
    # "Pomona" (Old Trafford) both fuzzy-match the same Site at 100.0,
    # sharing only the generic word "Waters" - see app.policy.
    # allocation_planning_coverage's own module docstring for the full
    # real-world case this is built from.
    plan = _make_plan(session)
    manchester_waters = Site(
        council_code="testcouncil", canonical_address="manchester waters pomona strand old trafford",
        display_address="Manchester Waters Pomona Strand Old Trafford",
    )
    session.add(manchester_waters)
    session.commit()

    trafford_waters = _make_allocation(session, plan.id, site_name="Trafford Waters", policy_reference="AN3", minimum_dwellings=3000)
    pomona = _make_allocation(session, plan.id, site_name="Pomona", policy_reference="AN4", minimum_dwellings=3200)

    from app.policy.allocation_planning_coverage import classify_site_match_confidence
    from app.extraction.local_plan import match_to_existing_site

    # Sanity check on the underlying real fixtures before asserting on the
    # feed's own reshaping of them (never trust an assertion built on an
    # accidentally-wrong fixture).
    site_a, score_a = match_to_existing_site("Trafford Waters", [manchester_waters])
    site_b, score_b = match_to_existing_site("Pomona", [manchester_waters])
    assert classify_site_match_confidence("Trafford Waters", site_a, score_a).confidence == "LOW"
    assert classify_site_match_confidence("Pomona", site_b, score_b).confidence == "HIGH"

    feed = build_opportunity_feed(session, limit=6)
    waters_card = next(c for c in feed["cards"] if c["id"] == f"opp-feed-alloc-{trafford_waters.id}")
    pomona_card = next(c for c in feed["cards"] if c["id"] == f"opp-feed-alloc-{pomona.id}")

    # Neither card's own signal is ever upgraded by a false/plausible match
    # - both remain INVESTIGATE (an evidence-gap signal), never anything
    # resembling "activity confirmed".
    assert waters_card["signal"] == "INVESTIGATE"
    assert pomona_card["signal"] == "INVESTIGATE"


# --- Uncertain / insufficient-evidence allocations must never look like a
# recommendation (Stretford Mall shape) --------------------------------------

def test_review_required_allocation_is_excluded_from_the_investigate_feed(session):
    # An allocation whose capacity accounting genuinely can't be resolved
    # (REVIEW_REQUIRED -> INSUFFICIENT_EVIDENCE) must never be promoted onto
    # the small, curated "worth investigating" feed - _FEED_ELIGIBLE_SIGNALS
    # only ever allows INVESTIGATE/MONITOR through.
    plan = _make_plan(session)
    site = Site(council_code="testcouncil", canonical_address="stretford mall", display_address="Stretford Mall")
    session.add(site)
    session.flush()
    allocation = _make_allocation(
        session, plan.id, site_name="Stretford Mall", minimum_dwellings=750, matched_site_id=site.id,
    )
    from app.db.models import AllocationSiteRelationship
    session.add(AllocationSiteRelationship(
        allocation_id=allocation.id, site_id=site.id, evidence_basis="document_confirmed_site",
        review_status="needs_confirmation",
    ))
    session.commit()

    feed = build_opportunity_feed(session, limit=6)
    titles = [c["title"] for c in feed["cards"]]
    assert "Stretford Mall" not in titles


# --- Planning/delivery reshaping (Step 24) -----------------------------------

def test_reshape_signal_card_never_invents_a_signal_for_planning_delivery():
    raw_card = {
        "id": "opp-lapse-1", "title": "Some Site", "subtitle": "testcouncil",
        "reason": "Commencement deadline 01 Jan 2027 - no build activity detected since the grant",
        "metric": "50 days left", "when": _now(), "page": "pages/1_Scheme_Detail.py", "params": {"site_id": "1"},
    }
    card = _reshape_signal_card(raw_card, opportunity_type=PLANNING_DELIVERY, extra_tags=["Approaching lapse"])
    assert card["opportunity_type"] == PLANNING_DELIVERY
    assert card["signal"] is None
    assert card["signal_label"] is None
    assert card["headline_reason"] == raw_card["reason"]
    assert card["metrics"] == [("Status", "50 days left")]
    assert "Planning / delivery" in card["tags"] and "Approaching lapse" in card["tags"]
    assert card["page"] == "pages/1_Scheme_Detail.py"
    assert card["params"] == {"site_id": "1"}


def test_approaching_lapse_site_appears_in_the_feed_as_a_planning_delivery_card(session):
    today = dt.date.today()
    site = _granted_site_with_decision(session, decision_date=today - dt.timedelta(days=3 * 365 - 100))
    feed = build_opportunity_feed(session, limit=6)
    delivery_cards = [c for c in feed["cards"] if c["opportunity_type"] == PLANNING_DELIVERY]
    assert any(c["title"] == site.display_address for c in delivery_cards)
    assert all(c["signal"] is None for c in delivery_cards)


# --- Feed composition / counts honesty ---------------------------------------

def test_counts_reflect_every_card_considered_not_just_the_ones_shown(session):
    plan = _make_plan(session)
    for i in range(8):
        _make_allocation(session, plan.id, site_name=f"Allocation {i}", policy_reference=f"REF-{i}", minimum_dwellings=1000 + i)
    feed = build_opportunity_feed(session, limit=4)
    assert feed["counts"]["strategic_land"] >= 4
    assert len(feed["cards"]) <= 4


def test_planning_delivery_gets_representation_when_both_types_exist(session):
    plan = _make_plan(session)
    for i in range(8):
        _make_allocation(session, plan.id, site_name=f"Allocation {i}", policy_reference=f"REF-{i}", minimum_dwellings=5000 - i)
    today = dt.date.today()
    lapse_site = _granted_site_with_decision(session, decision_date=today - dt.timedelta(days=3 * 365 - 50))

    feed = build_opportunity_feed(session, limit=6)
    types_shown = {c["opportunity_type"] for c in feed["cards"]}
    # Even though strategic land alone could fill every slot by count, the
    # feed reserves representation for planning/delivery opportunities too
    # (Step 24: "planning/delivery opportunities remain supported") - a
    # fixed, explainable reservation rule, never a cross-type score.
    assert PLANNING_DELIVERY in types_shown
    assert any(c["title"] == lapse_site.display_address for c in feed["cards"])
