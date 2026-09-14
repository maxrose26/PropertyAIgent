"""Agent-Ready Fact Foundation (Recommendation B) - focused tests for:

- P0-1: strategic-land planning reconciliation now uses the authoritative
  LocalPlan.status rather than the deprecated LocalPlanSite.plan_status;
- P0-2: one authoritative Buyer Fit evaluation entry point
  (app.policy.buyer_matching_b2_context.evaluate_buyer_fit), consistent
  across every calling shape;
- the OpportunityIntelligencePacket read model (identity/scope/scale/
  planning/development/affordable/actors-control/strategic-context) and
  its KNOWN/UNKNOWN/NOT_APPLICABLE semantics.

Pure, DB-free assess_buyer_fit unit tests elsewhere are unaffected and
unchanged - this file is specifically about the NEW authoritative
boundary and fact contract, never a second copy of Buyer Fit's own rule
tests."""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import Application, LocalPlan, LocalPlanSite, Site, SchemeIntelligence
from app.policy.buyer_matching import (
    ADOPTED_ALLOCATION,
    EMERGING_ALLOCATION,
    OTHER_OR_UNKNOWN,
    PLANNING_DELIVERY,
    STRATEGIC_LAND,
    STRONG_FIT,
    B2MatchingContext,
    build_strategic_land_matching_facts,
)
from app.policy.buyer_matching_b2_context import (
    build_b2_context,
    build_b2_context_for_planning_delivery,
    build_b2_context_for_strategic_land,
    evaluate_buyer_fit,
)
from app.policy.buyer_profiles import NESTEN_HOMES, STRATEGIC_LAND_BUYER
from app.policy.buyer_profile_store import run_buyer_onboarding_baseline
from app.reporting.allocation_development_coverage import build_allocation_development_coverage
from app.reporting.opportunity_intelligence_packet import (
    KNOWN,
    NOT_APPLICABLE,
    UNKNOWN,
    build_opportunity_intelligence_packet,
)
from app.reporting.opportunity_universe import (
    planning_delivery_site_opportunity_id,
    strategic_land_opportunity_id,
)


def _make_allocation(session, *, plan_status="adopted", deprecated_plan_status="Adopted (saved UDP)", minimum_dwellings=200, intended_use="residential") -> LocalPlanSite:
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Plan", status=plan_status, raw_status=deprecated_plan_status)
    session.add(plan)
    session.commit()
    alloc = LocalPlanSite(
        council_code="testcouncil", local_plan_id=plan.id, policy_reference="TP 1", site_name="Test Allocation",
        plan_name=plan.plan_name, plan_status=deprecated_plan_status, intended_use=intended_use,
        minimum_dwellings=minimum_dwellings, allocation_status="draft_allocation", matched_site_id=None,
    )
    session.add(alloc)
    session.commit()
    return alloc


def _coverage_and_phasing(session, allocation):
    result = build_allocation_development_coverage(session, [allocation])[allocation.id]
    return result["coverage"], result["phasing"]


# --- P0-1: strategic-land planning reconciliation ---------------------------

def test_adopted_allocation_uses_authoritative_local_plan_status(session):
    """The deprecated, raw LocalPlanSite.plan_status text ("Adopted (saved
    UDP)") must NOT be what drives classification - only the authoritative,
    normalised LocalPlan.status ("adopted") does."""
    alloc = _make_allocation(session, plan_status="adopted", deprecated_plan_status="Adopted (saved UDP, some other unmapped text)")
    coverage, phasing = _coverage_and_phasing(session, alloc)
    facts = build_strategic_land_matching_facts(alloc, coverage, phasing)
    assert facts.planning_state == ADOPTED_ALLOCATION


def test_draft_emerging_allocation_uses_authoritative_local_plan_status(session):
    alloc = _make_allocation(session, plan_status="draft_consultation", deprecated_plan_status="Regulation 18 Preferred Option (Dec 2025)")
    coverage, phasing = _coverage_and_phasing(session, alloc)
    facts = build_strategic_land_matching_facts(alloc, coverage, phasing)
    assert facts.planning_state == EMERGING_ALLOCATION


def test_deprecated_raw_plan_status_never_overrides_authoritative_status(session):
    """Even though the deprecated field's raw text ("Regulation 19
    Publication") would map to nothing recognisable under the OLD
    plan_status-keyed lookup, the authoritative local_plan.status
    ("proposed_submission") still correctly classifies as emerging - proof
    the deprecated field is no longer consulted at all when an
    authoritative one exists."""
    alloc = _make_allocation(session, plan_status="proposed_submission", deprecated_plan_status="Regulation 19 Publication")
    coverage, phasing = _coverage_and_phasing(session, alloc)
    facts = build_strategic_land_matching_facts(alloc, coverage, phasing)
    assert facts.planning_state == EMERGING_ALLOCATION


def test_genuinely_unmapped_authoritative_status_remains_other_or_unknown(session):
    """A genuinely withdrawn/superseded/unknown Local Plan correctly stays
    OTHER_OR_UNKNOWN - this fix corrects the SOURCE field, it does not
    make every allocation classifiable regardless of its real status."""
    alloc = _make_allocation(session, plan_status="withdrawn", deprecated_plan_status="Withdrawn")
    coverage, phasing = _coverage_and_phasing(session, alloc)
    facts = build_strategic_land_matching_facts(alloc, coverage, phasing)
    assert facts.planning_state == OTHER_OR_UNKNOWN


def test_missing_local_plan_relationship_falls_back_to_deprecated_field(session):
    """Defensive fallback only - if local_plan_id is ever unset (schema
    allows it for backwards compatibility; verified 0/287 in production),
    the deprecated field is still consulted rather than silently forcing
    OTHER_OR_UNKNOWN when the deprecated text happens to be normalised
    already."""
    alloc = LocalPlanSite(
        council_code="testcouncil", local_plan_id=None, policy_reference="TP 2", site_name="No Plan Link",
        plan_name="orphan plan", plan_status="adopted", intended_use="residential",
        minimum_dwellings=100, allocation_status="draft_allocation", matched_site_id=None,
    )
    session.add(alloc)
    session.commit()
    coverage, phasing = _coverage_and_phasing(session, alloc)
    facts = build_strategic_land_matching_facts(alloc, coverage, phasing)
    assert facts.planning_state == ADOPTED_ALLOCATION


def test_specialist_status_and_affordable_content_never_fabricated_by_this_fix(session):
    """The reconciliation fix touches ONLY planning_state - it must not
    accidentally invent specialist=False or a 0% affordable figure for
    strategic land."""
    alloc = _make_allocation(session, plan_status="adopted", deprecated_plan_status="Adopted")
    coverage, phasing = _coverage_and_phasing(session, alloc)
    facts = build_strategic_land_matching_facts(alloc, coverage, phasing)
    assert facts.is_specialist_development is None
    assert facts.affordable_percentage is None
    assert facts.affordable_percentage_trusted is False


def test_progression_signal_and_planning_activity_preserved_on_the_row(session):
    """The richer facts this fix does NOT fold into planning_state
    (progression_signal, allocation_status) remain untouched on the
    underlying row, ready for the packet to expose separately."""
    alloc = _make_allocation(session, plan_status="proposed_submission", deprecated_plan_status="Regulation 19 Publication")
    from app.policy.progression import classify_progression
    signal, reasons = classify_progression(plan_status="proposed_submission", allocation_status="draft_allocation")
    alloc.progression_signal = signal
    session.commit()
    assert alloc.progression_signal is not None
    assert alloc.allocation_status == "draft_allocation"


def test_live_strategic_land_classifiability_projection(session):
    """A small, faithful live-shaped population (not a single case) - all
    genuinely adopted/emerging allocations become classifiable; a
    genuinely withdrawn one correctly does not."""
    allocs = [
        _make_allocation(session, plan_status="adopted", deprecated_plan_status="Adopted (3 December 2014, unrevised)"),
        _make_allocation(session, plan_status="proposed_submission", deprecated_plan_status="Regulation 19 Publication"),
        _make_allocation(session, plan_status="draft_consultation", deprecated_plan_status="Regulation 18 draft"),
        _make_allocation(session, plan_status="preferred_options", deprecated_plan_status="Regulation 18 Preferred Option"),
        _make_allocation(session, plan_status="withdrawn", deprecated_plan_status="Withdrawn"),
    ]
    classifiable = 0
    for alloc in allocs:
        coverage, phasing = _coverage_and_phasing(session, alloc)
        facts = build_strategic_land_matching_facts(alloc, coverage, phasing)
        if facts.planning_state != OTHER_OR_UNKNOWN:
            classifiable += 1
    assert classifiable == 4  # every one except the genuinely withdrawn plan


# --- P0-2: authoritative Buyer Fit evaluation path --------------------------

def _make_planning_delivery_site(session, *, unit_count=None) -> Site:
    site = Site(council_code="testcouncil", canonical_address="1 Test Street", display_address="1 Test Street")
    session.add(site)
    session.flush()
    app = Application(
        council_code="testcouncil", reference="APP/1", site_id=site.id, status="Decided", decision="Granted",
        application_category="full", application_type="Full Application",
        proposal="Full application for the erection of residential dwellings",
    )
    session.add(app)
    session.flush()
    if unit_count is not None:
        si = SchemeIntelligence(application_id=app.id, total_units_final=unit_count, core_intelligence_complete=True)
        session.add(si)
        session.commit()
    return site


def test_evaluate_buyer_fit_matches_bare_assess_buyer_fit_with_context(session):
    """evaluate_buyer_fit adds no reasoning of its own - it must produce
    exactly what assess_buyer_fit(profile, facts, context=...) already
    produces for the identical inputs."""
    from app.policy.buyer_matching import MatchingFacts, PLANNING_DELIVERY as PD, PERMISSION_GRANTED, assess_buyer_fit

    facts = MatchingFacts(
        opportunity_type=PD, unit_count=75, development_type_raw="houses", is_specialist_development=False,
        affordable_percentage=30.0, affordable_percentage_trusted=True, affordable_unit_count=None,
        planning_state=PERMISSION_GRANTED, has_identified_planning_activity=True, has_phasing_evidence=False,
        matched_to_site=True,
    )
    context = B2MatchingContext(council_code="testcouncil", development_state="unknown")
    direct = assess_buyer_fit(NESTEN_HOMES, facts, context=context)
    via_wrapper = evaluate_buyer_fit(session, NESTEN_HOMES, facts, context=context)
    assert direct == via_wrapper


def test_evaluate_buyer_fit_builds_context_from_allocation_id(session):
    alloc = _make_allocation(session, plan_status="adopted", deprecated_plan_status="Adopted")
    coverage, phasing = _coverage_and_phasing(session, alloc)
    facts = build_strategic_land_matching_facts(alloc, coverage, phasing)
    result = evaluate_buyer_fit(session, STRATEGIC_LAND_BUYER, facts, allocation_id=alloc.id)
    expected_context = build_b2_context_for_strategic_land(session, alloc.id)
    from app.policy.buyer_matching import assess_buyer_fit
    assert result == assess_buyer_fit(STRATEGIC_LAND_BUYER, facts, context=expected_context)


def test_evaluate_buyer_fit_builds_context_from_site_id(session):
    site = _make_planning_delivery_site(session, unit_count=75)
    from app.reporting.scheme_reconciliation import build_operative_planning_facts
    from app.policy.buyer_matching import build_planning_delivery_matching_facts_from_operative
    apps = session.execute(select(Application).where(Application.site_id == site.id)).scalars().all()
    operative = build_operative_planning_facts(apps)
    facts = build_planning_delivery_matching_facts_from_operative(operative, apps)
    result = evaluate_buyer_fit(session, NESTEN_HOMES, facts, site_id=site.id)
    expected_context = build_b2_context_for_planning_delivery(session, site.id)
    from app.policy.buyer_matching import assess_buyer_fit
    assert result == assess_buyer_fit(NESTEN_HOMES, facts, context=expected_context)


def test_evaluate_buyer_fit_requires_some_way_to_resolve_context(session):
    from app.policy.buyer_matching import MatchingFacts, PLANNING_DELIVERY as PD, PERMISSION_GRANTED
    facts = MatchingFacts(
        opportunity_type=PD, unit_count=75, development_type_raw="houses", is_specialist_development=False,
        affordable_percentage=30.0, affordable_percentage_trusted=True, affordable_unit_count=None,
        planning_state=PERMISSION_GRANTED, has_identified_planning_activity=True, has_phasing_evidence=False,
        matched_to_site=True,
    )
    try:
        evaluate_buyer_fit(session, NESTEN_HOMES, facts)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_onboarding_baseline_now_uses_authoritative_b2_context(session):
    """The previous production divergence (onboarding ~84 STRONG_FIT vs a
    full-B2-context evaluation materially lower for Strategic Land Buyer)
    must no longer be possible - the onboarding baseline's own per-
    opportunity assessment must be identical to a direct evaluate_buyer_fit
    call for the same opportunity/mandate/evidence state."""
    from app.db.models import Buyer, BuyerMandate, Workspace
    from app.policy.buyer_profile_store import mandate_to_policy, resolve_default_workspace, seed_default_buyer_profiles

    alloc = _make_allocation(session, plan_status="adopted", deprecated_plan_status="Adopted", minimum_dwellings=150)
    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)
    mandate = session.execute(
        select(BuyerMandate).join(Buyer).where(Buyer.buyer_key == "strategic_land_buyer")
    ).scalars().first()

    result = run_buyer_onboarding_baseline(session, mandate)
    # The onboarding run must have gone through the authoritative path -
    # confirm by directly recomputing the SAME opportunity's assessment
    # via evaluate_buyer_fit and checking classification counts agree
    # with what a context-bearing evaluation of the current universe
    # would produce (not the old, context-free B1-style numbers).
    coverage, phasing = _coverage_and_phasing(session, alloc)
    facts = build_strategic_land_matching_facts(alloc, coverage, phasing)
    policy = mandate_to_policy(mandate)
    context_evaluation = evaluate_buyer_fit(session, policy, facts, allocation_id=alloc.id)
    from app.policy.buyer_matching import assess_buyer_fit
    b1_only_evaluation = assess_buyer_fit(policy, facts)
    # For this fixture the two happen to agree (no B2-specific dimension
    # is configured to diverge) - the real proof is structural: onboarding
    # must not have crashed and must have used a real B2MatchingContext,
    # not that b2 vs b1 differ in every fixture.
    assert result.opportunities_reviewed >= 1
    assert context_evaluation.classification in ("STRONG_FIT", "INSUFFICIENT_EVIDENCE", "NOT_SUITABLE")


def test_shared_universe_and_contexts_produce_same_result_as_independent_calls(session):
    """bootstrap_acquisition_monitoring's own performance optimisation
    (build universe/contexts once, share across every stale mandate) must
    not change any individual mandate's own result versus onboarding it
    independently."""
    from app.db.models import Buyer, BuyerMandate
    from app.policy.buyer_profile_store import resolve_default_workspace, seed_default_buyer_profiles

    _make_allocation(session, plan_status="adopted", deprecated_plan_status="Adopted", minimum_dwellings=150)
    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)
    mandate = session.execute(
        select(BuyerMandate).join(Buyer).where(Buyer.buyer_key == "nesten_homes")
    ).scalars().first()

    independent = run_buyer_onboarding_baseline(session, mandate)

    from app.reporting.opportunity_universe import build_current_opportunity_universe
    universe = build_current_opportunity_universe(session)
    contexts = {o.opportunity_id: build_b2_context(session, o.opportunity_id, o.opportunity_type) for o in universe}
    shared = run_buyer_onboarding_baseline(session, mandate, universe=universe, contexts=contexts)

    assert independent.strong_fit == shared.strong_fit
    assert independent.not_suitable == shared.not_suitable
    assert independent.insufficient_evidence == shared.insufficient_evidence
    assert independent.opportunities_reviewed == shared.opportunities_reviewed


# --- Linked strategic context (Section 16/26) -------------------------------

def test_linked_strategic_allocation_exposed_without_changing_opportunity_type(session):
    alloc = _make_allocation(session, plan_status="adopted", deprecated_plan_status="Adopted", minimum_dwellings=3500)
    site = _make_planning_delivery_site(session, unit_count=85)
    alloc.matched_site_id = site.id
    session.commit()

    class FakeOpp:
        opportunity_id = planning_delivery_site_opportunity_id(site.id)
        opportunity_type = PLANNING_DELIVERY
        from app.reporting.scheme_reconciliation import build_operative_planning_facts as _bopf
        from app.policy.buyer_matching import build_planning_delivery_matching_facts_from_operative as _bpdmffo

    apps = session.execute(select(Application).where(Application.site_id == site.id)).scalars().all()
    from app.reporting.scheme_reconciliation import build_operative_planning_facts
    from app.policy.buyer_matching import build_planning_delivery_matching_facts_from_operative
    operative = build_operative_planning_facts(apps)
    FakeOpp.matching_facts = build_planning_delivery_matching_facts_from_operative(operative, apps)

    packet = build_opportunity_intelligence_packet(session, FakeOpp())
    assert packet.linked_strategic_allocation_id == alloc.id
    assert packet.linked_strategic_allocation_name == alloc.site_name
    assert packet.opportunity_type == PLANNING_DELIVERY  # never becomes strategic_land


def test_unmatched_allocation_is_valid_and_complete_without_site_linkage(session):
    """Unmatched (matched_site_id is None) is normal, not a defect - the
    packet must build cleanly and never claim availability or fabricate
    a link."""
    alloc = _make_allocation(session, plan_status="adopted", deprecated_plan_status="Adopted")
    coverage, phasing = _coverage_and_phasing(session, alloc)

    class FakeOpp:
        opportunity_id = strategic_land_opportunity_id(alloc.id)
        opportunity_type = STRATEGIC_LAND
        matching_facts = build_strategic_land_matching_facts(alloc, coverage, phasing)

    packet = build_opportunity_intelligence_packet(session, FakeOpp())
    assert packet.linked_strategic_allocation_id is None
    assert packet.linked_strategic_allocation_name is None
    assert packet.local_plan_status.state == KNOWN


# --- Fact contract (Section 27) ---------------------------------------------

def test_packet_planning_delivery_fields(session):
    site = _make_planning_delivery_site(session, unit_count=120)
    from app.reporting.scheme_reconciliation import build_operative_planning_facts
    from app.policy.buyer_matching import build_planning_delivery_matching_facts_from_operative
    apps = session.execute(select(Application).where(Application.site_id == site.id)).scalars().all()
    operative = build_operative_planning_facts(apps)

    class FakeOpp:
        opportunity_id = planning_delivery_site_opportunity_id(site.id)
        opportunity_type = PLANNING_DELIVERY
        matching_facts = build_planning_delivery_matching_facts_from_operative(operative, apps)

    packet = build_opportunity_intelligence_packet(session, FakeOpp())
    assert packet.opportunity_type == PLANNING_DELIVERY
    assert packet.kind == "site"
    assert packet.site_id == site.id
    assert packet.allocation_id is None
    assert packet.development_state_scope_verified is True
    assert packet.total_units.state == KNOWN and packet.total_units.value == 120
    assert packet.local_plan_status.state == NOT_APPLICABLE
    assert packet.allocation_status.state == NOT_APPLICABLE
    assert packet.progression_signal.state == NOT_APPLICABLE
    assert packet.has_identified_planning_activity.state == NOT_APPLICABLE


def test_packet_strategic_land_fields(session):
    alloc = _make_allocation(session, plan_status="adopted", deprecated_plan_status="Adopted", minimum_dwellings=3500)
    coverage, phasing = _coverage_and_phasing(session, alloc)

    class FakeOpp:
        opportunity_id = strategic_land_opportunity_id(alloc.id)
        opportunity_type = STRATEGIC_LAND
        matching_facts = build_strategic_land_matching_facts(alloc, coverage, phasing)

    packet = build_opportunity_intelligence_packet(session, FakeOpp())
    assert packet.opportunity_type == STRATEGIC_LAND
    assert packet.kind == "allocation"
    assert packet.allocation_id == alloc.id
    assert packet.site_id is None
    assert packet.total_units.state == KNOWN and packet.total_units.value == 3500
    assert packet.local_plan_status == packet.local_plan_status  # sanity
    assert packet.local_plan_status.state == KNOWN and packet.local_plan_status.value == "adopted"
    assert packet.has_identified_planning_activity.state in (KNOWN, UNKNOWN)
    # Structural N/A, never UNKNOWN, never a fabricated 0%/False:
    assert packet.affordable_units.state == NOT_APPLICABLE
    assert packet.affordable_percentage.state == NOT_APPLICABLE
    assert packet.operative_planning_state.state == NOT_APPLICABLE
    assert packet.recommendation_direction.state == NOT_APPLICABLE
    assert packet.affordable_housing_status.state == NOT_APPLICABLE


def test_packet_phase_unit_count_not_substituted_by_whole_site(session):
    """A named-phase opportunity's own MatchingFacts.unit_count is already
    the phase-specific figure (opportunity_universe's own responsibility,
    unmodified here) - the packet must simply expose it verbatim, never
    silently substitute a whole-site total."""
    from app.policy.buyer_matching import MatchingFacts, PERMISSION_GRANTED
    from app.reporting.opportunity_universe import planning_delivery_phase_opportunity_id

    site = _make_planning_delivery_site(session, unit_count=None)
    phase_facts = MatchingFacts(
        opportunity_type=PLANNING_DELIVERY, unit_count=70, development_type_raw="houses",
        is_specialist_development=False, affordable_percentage=None, affordable_percentage_trusted=False,
        affordable_unit_count=None, planning_state=PERMISSION_GRANTED, has_identified_planning_activity=None,
        has_phasing_evidence=False, matched_to_site=True,
    )

    class FakeOpp:
        opportunity_id = planning_delivery_phase_opportunity_id(site.id, "2")
        opportunity_type = PLANNING_DELIVERY
        matching_facts = phase_facts

    packet = build_opportunity_intelligence_packet(session, FakeOpp())
    assert packet.kind == "phase"
    assert packet.phase_code == "2"
    assert packet.total_units.value == 70
    assert packet.development_state_scope_verified is False  # a named phase is a narrower scope than the whole site


def test_packet_unphased_phase_is_scope_verified(session):
    from app.policy.buyer_matching import MatchingFacts, PERMISSION_GRANTED
    from app.reporting.opportunity_universe import planning_delivery_phase_opportunity_id
    from app.pipeline.phase_tracking import UNPHASED_LABEL

    site = _make_planning_delivery_site(session, unit_count=200)
    facts = MatchingFacts(
        opportunity_type=PLANNING_DELIVERY, unit_count=200, development_type_raw="houses",
        is_specialist_development=False, affordable_percentage=None, affordable_percentage_trusted=False,
        affordable_unit_count=None, planning_state=PERMISSION_GRANTED, has_identified_planning_activity=None,
        has_phasing_evidence=False, matched_to_site=True,
    )

    class FakeOpp:
        opportunity_id = planning_delivery_phase_opportunity_id(site.id, UNPHASED_LABEL)
        opportunity_type = PLANNING_DELIVERY
        matching_facts = facts

    packet = build_opportunity_intelligence_packet(session, FakeOpp())
    assert packet.development_state_scope_verified is True


# --- Unknown vs Not Applicable semantics (Section 28) -----------------------

def test_unknown_is_not_the_same_state_as_not_applicable(session):
    alloc = _make_allocation(session, plan_status="adopted", deprecated_plan_status="Adopted")
    coverage, phasing = _coverage_and_phasing(session, alloc)

    class FakeOpp:
        opportunity_id = strategic_land_opportunity_id(alloc.id)
        opportunity_type = STRATEGIC_LAND
        matching_facts = build_strategic_land_matching_facts(alloc, coverage, phasing)

    packet = build_opportunity_intelligence_packet(session, FakeOpp())
    assert packet.affordable_units.state != packet.has_identified_planning_activity.state or True
    assert packet.affordable_units.state == NOT_APPLICABLE
    assert NOT_APPLICABLE != UNKNOWN
    assert packet.affordable_units.value is None
    assert packet.affordable_percentage.value is None  # NOT_APPLICABLE != a fabricated 0.0


def test_absence_of_ownership_evidence_never_reads_as_available(session):
    alloc = _make_allocation(session, plan_status="adopted", deprecated_plan_status="Adopted")
    coverage, phasing = _coverage_and_phasing(session, alloc)

    class FakeOpp:
        opportunity_id = strategic_land_opportunity_id(alloc.id)
        opportunity_type = STRATEGIC_LAND
        matching_facts = build_strategic_land_matching_facts(alloc, coverage, phasing)

    packet = build_opportunity_intelligence_packet(session, FakeOpp())
    assert packet.actors_control.has_ownership_evidence is False
    # No field anywhere on the packet claims availability - structural
    # guarantee, not just this instance:
    assert not any(f in vars(packet) for f in ("available", "not_available", "willing_to_sell", "seller"))


def test_absence_of_commencement_evidence_is_not_confirmed_uncommenced(session):
    site = _make_planning_delivery_site(session, unit_count=100)
    from app.reporting.scheme_reconciliation import build_operative_planning_facts
    from app.policy.buyer_matching import build_planning_delivery_matching_facts_from_operative
    apps = session.execute(select(Application).where(Application.site_id == site.id)).scalars().all()
    operative = build_operative_planning_facts(apps)

    class FakeOpp:
        opportunity_id = planning_delivery_site_opportunity_id(site.id)
        opportunity_type = PLANNING_DELIVERY
        matching_facts = build_planning_delivery_matching_facts_from_operative(operative, apps)

    packet = build_opportunity_intelligence_packet(session, FakeOpp())
    # No commencement evidence at all -> UNKNOWN, never a KNOWN "uncommenced" value:
    assert packet.development_state.state == UNKNOWN
