"""Stage 2.5B V7A: planning-delivery phasing semantics in buyer matching (policy v7), the self-scope guard, below-minimum wording, buyer scope, the agent-evaluation
fingerprint, the opportunity-fingerprint pins, and the wiring of ONE shared fact into the context builders, both feeds, the packet and the Slice 2 label.

Classification and the investigative flag are pinned EQUAL to accepted v6 for every B' case: only the evidence-aware reason changes.
"""
from __future__ import annotations

import inspect
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.policy.buyer_matching as bm
from app.policy.buyer_matching import (
    BUYER_MATCHING_POLICY_VERSION, INSUFFICIENT_EVIDENCE, NOT_SUITABLE, PHASING_CURRENT_EVIDENCED_PHASE, PHASING_CURRENTNESS_UNKNOWN, PHASING_DOCUMENTED,
    PHASING_HISTORICAL_ONLY, PHASING_NONE_IDENTIFIED, PLANNING_DELIVERY, STRATEGIC_LAND, AcquisitionPhasingEvidence, B2MatchingContext, MatchingFacts, assess_buyer_fit,
    subject_is_self_scope,
)
from app.policy.buyer_profiles import (
    ADOPTED_ALLOCATION, EMERGING_ALLOCATION, HOUSING_ASSOCIATION, NATIONAL_HOUSEBUILDER, NESTEN_HOMES, PERMISSION_GRANTED, STRATEGIC_LAND_BUYER,
)
from app.reporting.residential_count import CountAssessment

ROOT = Path(__file__).resolve().parents[1]
STATES = (PHASING_CURRENT_EVIDENCED_PHASE, PHASING_CURRENTNESS_UNKNOWN, PHASING_DOCUMENTED, PHASING_HISTORICAL_ONLY, PHASING_NONE_IDENTIFIED)


def facts(**overrides) -> MatchingFacts:
    base = dict(opportunity_type=PLANNING_DELIVERY, unit_count=500, development_type_raw="houses", is_specialist_development=False, affordable_percentage=30.0,
                affordable_percentage_trusted=True, affordable_unit_count=150, planning_state=PERMISSION_GRANTED, has_identified_planning_activity=True,
                has_phasing_evidence=False, matched_to_site=True)
    base.update(overrides)
    return MatchingFacts(**base)


def exact(scope_type, label, n):
    return CountAssessment(scope_type=scope_type, scope_label=label, precision="EXACT", value=n, lower=n, upper=n, resolution="agreement", confidence="high")


def ctx(state=None, **kw) -> B2MatchingContext:
    return B2MatchingContext(acquisition_phasing=AcquisitionPhasingEvidence(state) if state else None, **kw)


def investigate(profile, f, context):
    result = assess_buyer_fit(profile, f, context=context)
    return result, " ".join(result.investigate)


# --- B' wording; classification + flag equal to v6 ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("state,needle", [
    (PHASING_CURRENT_EVIDENCED_PHASE, "Phased delivery is evidenced; assess the evidenced phase scope(s) separately. Availability is unverified."),
    (PHASING_DOCUMENTED, "A phased-delivery strategy is evidenced; a buyer-relevant acquisition scope has not yet been established."),
    (PHASING_HISTORICAL_ONLY, "Historic phasing evidence exists"),
    (PHASING_CURRENTNESS_UNKNOWN, "Phase evidence exists, but its current implementation status cannot be established from the available dates; decomposition remains unverified."),
    (PHASING_NONE_IDENTIFIED, "No current phasing evidence has been identified in the qualified records; decomposition remains unverified."),
    (None, "Decomposition remains unverified."),
])
@pytest.mark.parametrize("profile,units,floor", [(NESTEN_HOMES, 500, "45-220 homes; preferred 50-200 homes"), (NATIONAL_HOUSEBUILDER, 990, "180-550 homes; preferred 200-500 homes")])
def test_oversized_wider_subject_gets_the_phasing_aware_reason_with_unchanged_classification_and_flag(profile, units, floor, state, needle):
    result, text = investigate(profile, facts(unit_count=units), ctx(state))
    assert (result.classification, result.is_investigative_exception) == (INSUFFICIENT_EVIDENCE, True)      # equal to accepted v6 at EVERY level
    assert f"Scale ({units:,} homes) is outside this buyer's discovery range ({floor})." in text and needle in text
    assert "investigate whether a relevant phase" not in text and "sub-scope" not in text                    # the speculative claim is gone
    assert "unphased" not in text.lower() and "probably" not in text.lower() and "available" not in text.lower().replace("availability is unverified", "").replace("from the available dates", "")


def test_level_three_stays_investigative_and_never_says_the_scheme_is_unphased():
    result, text = investigate(NESTEN_HOMES, facts(unit_count=600), ctx(PHASING_NONE_IDENTIFIED))
    assert result.is_investigative_exception is True and result.classification == INSUFFICIENT_EVIDENCE
    assert "No current phasing evidence has been identified" in text and "unphased" not in text.lower()


def test_currentness_unknown_wording_claims_nothing_beyond_unverified_status():
    result, text = investigate(NESTEN_HOMES, facts(unit_count=600), ctx(PHASING_CURRENTNESS_UNKNOWN))
    assert (result.classification, result.is_investigative_exception) == (INSUFFICIENT_EVIDENCE, True)
    tail = text.split("preferred 50-200 homes). ")[1].lower().replace("from the available dates", "")      # the approved wording itself says "available dates"
    for forbidden in ("phased delivery is evidenced", "historic", "lapsed", "expired", "available", "remaining", "another", "unphased", "assess the evidenced"):
        assert forbidden not in tail, forbidden
    _, own = investigate(NESTEN_HOMES, facts(unit_count=300, count_assessment=exact("phase", "Phase 1", 300)), ctx(PHASING_CURRENTNESS_UNKNOWN, subject_phase_scope_key="1"))
    assert "own scope is a named phase" in own and "current implementation status" not in own     # the self-scope guard still applies


def test_historical_wording_acknowledges_history_without_asserting_legal_lapse():
    _, text = investigate(NESTEN_HOMES, facts(unit_count=600), ctx(PHASING_HISTORICAL_ONLY))
    assert "assumed implementation date has passed" in text and "implementation status is unverified" in text
    assert "lapsed" not in text.lower() and "expired" not in text.lower() and "no longer valid" not in text.lower()


# --- self-scope guard ---------------------------------------------------------------------------------------------------------------

def test_the_phase_subject_itself_gets_no_sibling_aware_wording_and_is_matched_on_its_own_evidence():
    phase_facts = facts(unit_count=300, count_assessment=exact("phase", "Phase 1", 300))
    for context in (ctx(PHASING_CURRENT_EVIDENCED_PHASE, subject_phase_scope_key="1"), ctx(PHASING_CURRENT_EVIDENCED_PHASE)):   # by key, and by its own count scope
        result, text = investigate(NESTEN_HOMES, phase_facts, context)
        assert "own scope is a named phase" in text and "assess the evidenced phase" not in text and "Phased delivery is evidenced" not in text
        assert (result.classification, result.is_investigative_exception) == (INSUFFICIENT_EVIDENCE, True)


def test_a_125_home_phase_is_matched_on_its_own_scale_not_the_parent():
    phase = facts(unit_count=125, count_assessment=CountAssessment(scope_type="phase", scope_label="Phase 1", precision="EXACT", value=125, lower=125, upper=125))
    result = assess_buyer_fit(NESTEN_HOMES, phase, context=ctx(PHASING_CURRENT_EVIDENCED_PHASE, subject_phase_scope_key="1"))
    assert result.classification == "STRONG_FIT"            # 125 is inside 50-200: the phase stands on its own evidence


@pytest.mark.parametrize("state,expect_self", [(PHASING_CURRENT_EVIDENCED_PHASE, True), (PHASING_NONE_IDENTIFIED, False), (PHASING_HISTORICAL_ONLY, False)])
def test_application_anchored_subjects_are_neutral_only_when_current_phase_evidence_exists(state, expect_self):
    """recent-permission / long-pending subjects cannot be shown not to be that phase when CURRENT evidence exists -> neutral self-scope wording."""
    context = ctx(state, subject_application_anchored=True)
    assert subject_is_self_scope(facts(), context) is expect_self
    _, text = investigate(NESTEN_HOMES, facts(unit_count=600), context)
    assert ("own scope is a named phase" in text) is expect_self


def test_the_unphased_bucket_and_whole_site_subjects_get_the_sibling_aware_wording():
    whole = facts(unit_count=500, count_assessment=exact("whole_site", "Whole site", 500))
    assert subject_is_self_scope(whole, ctx(PHASING_CURRENT_EVIDENCED_PHASE, subject_phase_scope_key=None)) is False
    _, text = investigate(NESTEN_HOMES, whole, ctx(PHASING_CURRENT_EVIDENCED_PHASE))
    assert "assess the evidenced phase scope(s) separately" in text


# --- below-minimum wording (separately authorised; classification/flag preserved) -----------------------------------------------------------

def test_below_minimum_is_neutral_and_never_suggests_phasing_or_aggregation_and_keeps_v6_classification_and_flag():
    result, text = investigate(NATIONAL_HOUSEBUILDER, facts(unit_count=23), ctx(PHASING_CURRENT_EVIDENCED_PHASE))
    assert "Scale (23 homes) is below this buyer's discovery range (180-550 homes; preferred 200-500 homes)." in text
    for forbidden in ("phase", "sub-scope", "combin", "aggregat", "decomposition", "another"):
        assert forbidden not in text.lower(), forbidden
    assert (result.classification, result.is_investigative_exception) == (INSUFFICIENT_EVIDENCE, True)      # unchanged from v6


def test_above_maximum_still_receives_the_phasing_aware_wording_alongside_below_minimum_neutrality():
    _, above = investigate(NATIONAL_HOUSEBUILDER, facts(unit_count=990), ctx(PHASING_CURRENT_EVIDENCED_PHASE))
    _, below = investigate(NATIONAL_HOUSEBUILDER, facts(unit_count=23), ctx(PHASING_CURRENT_EVIDENCED_PHASE))
    assert "Phased delivery is evidenced" in above and "Phased delivery" not in below


def test_the_below_minimum_wording_also_applies_to_strategic_subjects_without_changing_their_flag():
    strategic = facts(opportunity_type=STRATEGIC_LAND, unit_count=60, planning_state=ADOPTED_ALLOCATION, development_type_raw=None, is_specialist_development=None,
                      affordable_percentage=None, affordable_percentage_trusted=False, affordable_unit_count=None)
    result, text = investigate(STRATEGIC_LAND_BUYER, strategic, None)
    assert "is below this buyer's discovery range" in text and "sub-scope" not in text
    assert (result.classification, result.is_investigative_exception) == (INSUFFICIENT_EVIDENCE, True)


def test_uncertain_range_wholly_outside_discovery_uses_the_direction_aware_wording():
    def range_facts(lower, upper):
        return facts(unit_count=None, count_assessment=CountAssessment(scope_type="whole_site", scope_label="Whole site", precision="RANGE", lower=lower, upper=upper,
                                                                       resolution="material_conflict"))
    above_result, above = investigate(NESTEN_HOMES, range_facts(300, 400), ctx(PHASING_CURRENT_EVIDENCED_PHASE))
    below_result, below = investigate(NESTEN_HOMES, range_facts(20, 30), ctx(PHASING_CURRENT_EVIDENCED_PHASE))
    assert "is outside this buyer's discovery range" in above and "Phased delivery is evidenced" in above
    assert "is below this buyer's discovery range" in below and "phas" not in below.lower().replace("supported scale", "")
    assert above_result.is_investigative_exception and below_result.is_investigative_exception        # the uncertain branch's flag is untouched


# --- buyer scope ---------------------------------------------------------------------------------------------------------------------

def test_housing_association_affordable_unit_semantics_are_preserved_and_ignore_site_phasing():
    ha_facts = facts(unit_count=900, affordable_unit_count=400)
    with_phasing, text_with = investigate(HOUSING_ASSOCIATION, ha_facts, ctx(PHASING_CURRENT_EVIDENCED_PHASE))
    without, text_without = investigate(HOUSING_ASSOCIATION, ha_facts, None)
    assert text_with == text_without and "Phased delivery is evidenced" not in text_with           # total-site phasing never implies an affordable package
    assert (with_phasing.classification, with_phasing.is_investigative_exception) == (without.classification, without.is_investigative_exception)
    assert "400 affordable homes" in text_with


def test_strategic_allocations_keep_v6_wording_and_the_strategic_phasing_note_and_routes():
    allocation = facts(opportunity_type=STRATEGIC_LAND, unit_count=600, planning_state=EMERGING_ALLOCATION, development_type_raw=None, is_specialist_development=None,
                       affordable_percentage=None, affordable_percentage_trusted=False, affordable_unit_count=None, has_phasing_evidence=True, matched_to_site=False)
    nhb, nhb_text = investigate(NATIONAL_HOUSEBUILDER, allocation, ctx(PHASING_CURRENT_EVIDENCED_PHASE))                          # a planning fact must not leak into strategic subjects
    assert "investigate whether a relevant phase or acquisition sub-scope exists" in nhb_text and "Evidence of phased delivery exists for this opportunity" in nhb_text
    assert "Phased delivery is evidenced; assess" not in nhb_text
    slb, slb_text = investigate(STRATEGIC_LAND_BUYER, replace(allocation, unit_count=1400), None)
    assert slb.classification != INSUFFICIENT_EVIDENCE and "meaningful strategic-land position" in " ".join(slb.matches) and slb.is_investigative_exception


def test_a_planning_delivery_subject_for_the_strategic_land_buyer_uses_the_planning_wording_not_the_strategic_route():
    result, text = investigate(STRATEGIC_LAND_BUYER, facts(unit_count=990), ctx(PHASING_CURRENT_EVIDENCED_PHASE))
    assert result.classification == INSUFFICIENT_EVIDENCE and "Phased delivery is evidenced" in text and "meaningful strategic-land" not in " ".join(result.matches)


# --- hard-excluded child -----------------------------------------------------------------------------------------------------------------

def test_a_not_suitable_child_still_evidences_phasing_without_promoting_the_parent_or_implying_another_phase():
    from app.reporting.opportunity_families import FamilySubject, group_into_families, ID_SYSTEM_FEED, SLOT_LIFECYCLE, SLOT_PHASE
    retirement = facts(unit_count=80, is_specialist_development=True, development_type_raw="retirement_living", count_assessment=exact("phase", "Phase 1", 80))
    child = assess_buyer_fit(NESTEN_HOMES, retirement, context=ctx(PHASING_CURRENT_EVIDENCED_PHASE, subject_phase_scope_key="1"))
    parent = assess_buyer_fit(NESTEN_HOMES, facts(unit_count=600), ctx(PHASING_CURRENT_EVIDENCED_PHASE))
    assert child.classification == NOT_SUITABLE
    assert (parent.classification, parent.is_investigative_exception) == (INSUFFICIENT_EVIDENCE, True)                  # NOT promoted
    assert "Phased delivery is evidenced" in " ".join(parent.investigate)
    assert "another" not in " ".join(parent.investigate).lower() and "remaining" not in " ".join(parent.investigate).lower()

    def subject(key, slot, assessed):
        return FamilySubject(domain=PLANNING_DELIVERY, anchor_id=1, subject_key=key, slot=slot, fit=assessed.classification,
                             investigative=assessed.is_investigative_exception, id_system=ID_SYSTEM_FEED)
    family = group_into_families([subject("opp-phase-1-1", SLOT_PHASE, child), subject("opp-lapse-1", SLOT_LIFECYCLE, parent)])[0]
    assert family.representative.subject_key == "opp-lapse-1" and family.fit == INSUFFICIENT_EVIDENCE and not family.is_terminally_excluded


def test_a_current_phase_makes_the_family_strong_through_the_phase_without_promoting_the_parent():
    from app.reporting.opportunity_families import FamilySubject, group_into_families, ID_SYSTEM_FEED, SLOT_LIFECYCLE, SLOT_PHASE
    phase_facts = facts(unit_count=125, count_assessment=CountAssessment(scope_type="phase", scope_label="Phase 1", precision="EXACT", value=125, lower=125, upper=125))
    child = assess_buyer_fit(NESTEN_HOMES, phase_facts, context=ctx(PHASING_CURRENT_EVIDENCED_PHASE, subject_phase_scope_key="1"))
    parent = assess_buyer_fit(NESTEN_HOMES, facts(unit_count=500), ctx(PHASING_CURRENT_EVIDENCED_PHASE))
    assert child.classification == "STRONG_FIT" and parent.classification == INSUFFICIENT_EVIDENCE
    subjects = [FamilySubject(domain=PLANNING_DELIVERY, anchor_id=1, subject_key=k, slot=s, fit=a.classification, investigative=a.is_investigative_exception, id_system=ID_SYSTEM_FEED)
                for k, s, a in (("opp-phase-1-1", SLOT_PHASE, child), ("opp-lapse-1", SLOT_LIFECYCLE, parent))]
    family = group_into_families(subjects)[0]
    assert family.fit == "STRONG_FIT" and family.representative.subject_key == "opp-phase-1-1"


# --- versions and fingerprints ------------------------------------------------------------------------------------------------------------

def test_policy_is_v7_and_the_mandate_fingerprint_moves_with_it(monkeypatch):
    from app.policy import buyer_profile_store
    assert BUYER_MATCHING_POLICY_VERSION == 7
    v7 = buyer_profile_store.compute_buyer_mandate_fingerprint(NESTEN_HOMES)
    monkeypatch.setattr(buyer_profile_store, "BUYER_MATCHING_POLICY_VERSION", 6)
    assert buyer_profile_store.compute_buyer_mandate_fingerprint(NESTEN_HOMES) != v7


class _Packet:
    def __init__(self, **overrides):
        from tests.test_agent_evaluation_persistence import _FakeFingerprintPacket
        self.__dict__.update(_FakeFingerprintPacket().__dict__)
        self.__dict__.update(overrides)


def _agent_fp(**overrides):
    from app.policy.agent_evaluation_persistence import compute_agent_evaluation_input_fingerprint
    assessment = SimpleNamespace(classification=INSUFFICIENT_EVIDENCE, is_investigative_exception=True, matches=[], unknown=[], investigate=["same text"], does_not_match=[])
    return compute_agent_evaluation_input_fingerprint(mandate_fingerprint="m", acquisition_type="LAND_SITE_ACQUISITION", buyer_fit_assessment=assessment, packet=_Packet(**overrides))


def test_the_agent_fingerprint_payload_is_v3_and_the_phasing_state_changes_it_even_if_reason_text_is_identical():
    from app.policy.agent_evaluation_persistence import AGENT_EVALUATION_INPUT_FINGERPRINT_VERSION
    assert AGENT_EVALUATION_INPUT_FINGERPRINT_VERSION == 3
    fingerprints = {state: _agent_fp(acquisition_phasing_state=state) for state in (*STATES, None)}
    assert len(set(fingerprints.values())) == len(fingerprints)                       # every state (and absence) is distinguishable; wording drift cannot hide it
    assert _agent_fp(acquisition_phasing_state=PHASING_NONE_IDENTIFIED) != _agent_fp(acquisition_phasing_state=PHASING_NONE_IDENTIFIED, acquisition_phasing_self_scope=True)
    assert _agent_fp(acquisition_phasing_state=PHASING_NONE_IDENTIFIED) == _agent_fp(acquisition_phasing_state=PHASING_NONE_IDENTIFIED)


def test_opportunity_evidence_fingerprints_do_not_depend_on_the_derived_phasing_fact(session, monkeypatch):
    """Option D: objective evidence fingerprints are unchanged by the phasing fact (and by v7). Build the whole universe with the derivation forced to each state."""
    import app.reporting.acquisition_phasing as ap
    from app.reporting.opportunity_universe import build_current_opportunity_universe
    from tests.test_buyer_family_feed import LAPSE_AGE, World
    world = World(session, monkeypatch)
    world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE)
    world.site(rm_age=300, rm_phase="Phase 1")
    world.allocation(capacity=8400)
    baseline = {r.opportunity_id: r.fingerprint_fields for r in build_current_opportunity_universe(session)}
    for state in STATES:
        monkeypatch.setattr(ap, "derive_acquisition_phasing_evidence", lambda applications, site, s=state: AcquisitionPhasingEvidence(s))
        again = {r.opportunity_id: r.fingerprint_fields for r in build_current_opportunity_universe(session)}
        assert again == baseline
    assert baseline and all("phasing" not in key for fields in baseline.values() for key in fields if key != "has_phasing_evidence")
    assert not any("has_phasing_evidence" in fields for oid, fields in baseline.items() if oid.startswith("planning_delivery"))


def test_strategic_has_phasing_evidence_is_still_strategic_only_and_unchanged():
    source = inspect.getsource(bm.build_strategic_land_matching_facts)
    assert 'has_phasing = bool(phasing and phasing.get("evidence"))' in source
    assert "acquisition_phasing" not in source


# --- wiring: ONE shared fact reaches every consumer ------------------------------------------------------------------------------------------

def test_context_builders_derive_the_fact_and_the_self_scope_inputs(session, monkeypatch):
    from app.policy.buyer_matching_b2_context import build_b2_context, build_b2_context_for_planning_delivery
    from tests.test_buyer_family_feed import LAPSE_AGE, World
    world = World(session, monkeypatch)
    site = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, rm_phase="Phase 2")
    base = build_b2_context_for_planning_delivery(session, site.id)
    assert base.acquisition_phasing.state == PHASING_CURRENT_EVIDENCED_PHASE and base.subject_phase_scope_key is None and base.subject_application_anchored is False
    by_id = {
        f"planning_delivery:phase:{site.id}:2": ("2", False), f"planning_delivery:phase:{site.id}:Whole site / unphased": (None, False),
        f"planning_delivery:site:{site.id}": (None, False), f"planning_delivery:recent_permission:{site.id}": (None, True),
        f"planning_delivery:long_pending_application:{site.id}": (None, True),
    }
    for opportunity_id, (key, anchored) in by_id.items():
        context = build_b2_context(session, opportunity_id, PLANNING_DELIVERY)
        assert (context.subject_phase_scope_key, context.subject_application_anchored) == (key, anchored), opportunity_id
        assert context.acquisition_phasing.state == PHASING_CURRENT_EVIDENCED_PHASE


def test_the_feed_and_the_presentation_consume_the_same_fact_including_the_lapsed_case(session, monkeypatch):
    import app.reporting.buyer_family_feed as bff
    import app.reporting.family_presentation as fp
    from tests.test_buyer_family_feed import LAPSE_AGE, World
    from tests.test_family_dashboard import treat_portal_estimates_as_exact
    treat_portal_estimates_as_exact(monkeypatch)
    world = World(session, monkeypatch)
    current = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="I", phase="S", units_out=500)
    lapsed = world.site(outline_age=365 * 3 + 300, rm_age=365 * 3 + 200, rm_phase="Phase 2", parent="I", phase="S", units_out=500)
    view = fp.build_buyer_family_dashboard_view(session, "nesten_homes", 10)
    result = bff.build_buyer_opportunity_families(session, "nesten_homes", 10)
    states = {f.family_key[1]: {m.source["acquisition_phasing"].state for m in f.members} for f in result["families"]}
    assert states[current.id] == {PHASING_CURRENT_EVIDENCED_PHASE} and states[lapsed.id] == {PHASING_HISTORICAL_ONLY}     # identical for every member of a family
    labelled = {f.title: f.phasing_context for f in view.families}
    assert labelled[f"Site {current.id}"] == fp.PHASING_CONTEXT and labelled[f"Site {lapsed.id}"] is None             # H: the label follows the SAME predicate as the matcher


def test_the_legacy_buyer_feed_passes_the_same_guard_inputs(monkeypatch):
    from app.policy import buyer_matching_b2_context, buyer_profile_store
    from app.reporting import opportunity_feed
    captured = []
    cards = [{"id": "opp-phase-1-2", "title": "p", "opportunity_type": PLANNING_DELIVERY, "matching_facts": object(), "params": {"site_id": 1}, "phase_code": "2"},
             {"id": "opp-recent-permission-3", "title": "r", "opportunity_type": PLANNING_DELIVERY, "matching_facts": object(), "params": {"site_id": 3}}]
    monkeypatch.setattr(buyer_profile_store, "get_buyer_profile_dataclass", lambda session, key: NESTEN_HOMES)
    monkeypatch.setattr(opportunity_feed, "_attach_planning_delivery_matching_facts", lambda session, delivery: None)
    monkeypatch.setattr(buyer_matching_b2_context, "evaluate_buyer_fit", lambda session, profile, facts, **kw: captured.append(kw) or SimpleNamespace(
        classification=INSUFFICIENT_EVIDENCE, is_investigative_exception=True))
    opportunity_feed._buyer_selection(None, [], cards, 6, "nesten_homes")
    assert [(k["subject_phase_scope_key"], k["subject_application_anchored"]) for k in captured] == [("2", False), (None, True)]


def test_the_packet_carries_the_state_and_the_guard_for_planning_delivery_only(session, monkeypatch):
    from app.reporting.opportunity_intelligence_packet import build_opportunity_intelligence_packet
    from app.reporting.opportunity_universe import build_current_opportunity_universe
    from tests.test_buyer_family_feed import LAPSE_AGE, World
    world = World(session, monkeypatch)
    site = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, rm_phase="Phase 2")
    world.allocation(capacity=8400)
    records = {r.opportunity_id: r for r in build_current_opportunity_universe(session)}
    phase = build_opportunity_intelligence_packet(session, records[f"planning_delivery:phase:{site.id}:2"])
    parent = build_opportunity_intelligence_packet(session, records[f"planning_delivery:site:{site.id}"])
    allocation = build_opportunity_intelligence_packet(session, next(r for oid, r in records.items() if oid.startswith("strategic_land")))
    assert (phase.acquisition_phasing_state, phase.acquisition_phasing_self_scope) == (PHASING_CURRENT_EVIDENCED_PHASE, True)
    assert (parent.acquisition_phasing_state, parent.acquisition_phasing_self_scope) == (PHASING_CURRENT_EVIDENCED_PHASE, False)
    assert (allocation.acquisition_phasing_state, allocation.acquisition_phasing_self_scope) == (None, False)


def test_the_matcher_stays_pure():
    import ast
    tree = ast.parse(inspect.getsource(bm))
    function = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "assess_buyer_fit")
    names = {n.id for n in ast.walk(function) if isinstance(n, ast.Name)}
    assert not names & {"session", "Session", "select", "sessionmaker"}               # assess_buyer_fit reasons only from the supplied facts/context
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m and ("acquisition_phasing" in m or "sqlalchemy" in m or "opportunity_universe" in m or "opportunity_families" in m) for m in imported)
