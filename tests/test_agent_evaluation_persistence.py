"""Acquisition Agent V1, Gate 1 (Persistence Foundation) - tests for
app.policy.agent_evaluation_persistence.

No real LLM calls anywhere in this file (Gate 1 brief, Section 34: "Mock
the OpenAI call. DO NOT use real API calls for concurrency tests.") - real
(in-memory, per-test) database rows build real Buyer/BuyerMandate/
BuyerFitAssessment/OpportunityIntelligencePacket objects, exactly as
app.policy.acquisition_evaluate.evaluate() and app.policy.
agent_evaluation_persistence expect to receive them; only the model call
itself is faked."""
from __future__ import annotations

import json

from sqlalchemy import select

from app.db.models import (
    AcquisitionSubjectAnchor,
    AgentEvaluationClaim,
    AgentEvaluationHistory,
    Application,
    BuyerMandate,
    CurrentBuyerOpportunityState,
    Site,
    SchemeIntelligence,
)
from app.policy.agent_evaluation_persistence import (
    CLAIM_CLAIMED,
    CLAIM_COMPLETED,
    CLAIM_FAILED,
    WHOLE_SITE,
    compute_agent_evaluation_input_fingerprint,
    get_or_create_subject_anchor,
    record_evaluation_outcome,
    resolve_acquisition_subject_key,
    run_persisted_evaluation,
    try_claim_evaluation,
)
from app.policy.agent_evaluation_result import FAILED, SUCCESS, ACQUISITION_TYPE_NOT_IN_MANDATE
from app.policy.buyer_matching import PLANNING_DELIVERY, STRATEGIC_LAND, build_planning_delivery_matching_facts_from_operative
from app.policy.buyer_matching_b2_context import build_b2_context_for_planning_delivery, evaluate_buyer_fit
from app.policy.buyer_profile_store import resolve_default_workspace, seed_default_buyer_profiles
from app.reporting.opportunity_intelligence_packet import FactValue, build_opportunity_intelligence_packet
from app.reporting.opportunity_universe import (
    planning_delivery_long_pending_application_opportunity_id,
    planning_delivery_phase_opportunity_id,
    planning_delivery_recent_permission_opportunity_id,
    planning_delivery_site_opportunity_id,
    strategic_land_opportunity_id,
)
from app.reporting.scheme_reconciliation import build_operative_planning_facts


# --- Minimal fake packet for fingerprint field-sensitivity tests ------------
# (Section 1 pre-merge audit: developer_indications/ownership_coverage/
# conflicts/linked_strategic_allocation_id are easiest to vary directly
# rather than round-tripping through real S106/ownership-certificate
# documents, which test the extraction pipeline, not the fingerprint.)

class _FakeSignal:
    def __init__(self, state="UNKNOWN"):
        self.state = state
        self.detail = None


class _FakeTransactionSignals:
    def __init__(self):
        self.recent_permission = _FakeSignal()
        self.approaching_implementation_deadline = _FakeSignal()
        self.implementation_activity_evidence_identified = _FakeSignal()
        self.wider_site_implementation_activity_context = _FakeSignal()
        self.no_qualifying_progress_evidence_identified = _FakeSignal()
        self.ownership_or_control_evidence_changed = _FakeSignal()
        self.scope_verified = False


class _FakeActorsControl:
    def __init__(self, developer_indications=(), ownership_coverage="INSUFFICIENT_EVIDENCE_TO_DETERMINE_CONTROL", conflicts=(), has_ownership_evidence=False):
        self.developer_indications = developer_indications
        self.ownership_coverage = ownership_coverage
        self.conflicts = conflicts
        self.has_ownership_evidence = has_ownership_evidence


class _FakeFingerprintPacket:
    def __init__(self, **overrides):
        self.opportunity_type = PLANNING_DELIVERY
        self.total_units = FactValue.known(75)
        self.affordable_units = FactValue.unknown()
        self.affordable_percentage = FactValue.unknown()
        self.operative_planning_state = FactValue.known("permission_granted")
        self.recommendation_direction = FactValue.unknown()
        self.affordable_housing_status = FactValue.unknown()
        self.development_state = FactValue.unknown()
        self.development_state_scope_verified = False
        self.actors_control = _FakeActorsControl()
        self.linked_strategic_allocation_id = None
        self.transaction_signals = _FakeTransactionSignals()
        for k, v in overrides.items():
            setattr(self, k, v)


def _fake_assessment(**overrides):
    from app.policy.buyer_matching import BuyerFitAssessment
    defaults = dict(classification="STRONG_FIT", is_investigative_exception=False)
    defaults.update(overrides)
    return BuyerFitAssessment(**defaults)


def _fp(**packet_overrides):
    return compute_agent_evaluation_input_fingerprint(
        mandate_fingerprint="fp-mandate", acquisition_type="LAND_SITE_ACQUISITION",
        buyer_fit_assessment=_fake_assessment(), packet=_FakeFingerprintPacket(**packet_overrides),
    )


# --- Shared fixtures ---------------------------------------------------------

class _FakeOpp:
    def __init__(self, opportunity_id, opportunity_type, matching_facts):
        self.opportunity_id = opportunity_id
        self.opportunity_type = opportunity_type
        self.matching_facts = matching_facts


_reference_counter = [0]


def _make_site(session, *, unit_count=75):
    _reference_counter[0] += 1
    site = Site(council_code="testcouncil", canonical_address="1 Test Street", display_address="1 Test Street")
    session.add(site)
    session.flush()
    app = Application(
        council_code="testcouncil", reference=f"APP/{_reference_counter[0]}", site_id=site.id, status="Decided", decision="Granted",
        application_category="full", application_type="Full Application",
        proposal="Full application for the erection of residential dwellings",
    )
    session.add(app)
    session.flush()
    si = SchemeIntelligence(application_id=app.id, total_units_final=unit_count, core_intelligence_complete=True)
    session.add(si)
    session.commit()
    return site


def _seed_mandate(session, buyer_key="nesten_homes") -> BuyerMandate:
    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)
    return session.execute(
        select(BuyerMandate).join(BuyerMandate.buyer).where(BuyerMandate.buyer.has(buyer_key=buyer_key))
    ).scalars().first()


def _build_case(session, *, opportunity_id_fn=planning_delivery_site_opportunity_id, unit_count=75):
    site = _make_site(session, unit_count=unit_count)
    apps = session.execute(select(Application).where(Application.site_id == site.id)).scalars().all()
    operative = build_operative_planning_facts(apps)
    facts = build_planning_delivery_matching_facts_from_operative(operative, apps)
    opp = _FakeOpp(opportunity_id_fn(site.id), PLANNING_DELIVERY, facts)
    mandate_row = _seed_mandate(session)
    from app.policy.buyer_profile_store import mandate_to_policy
    mandate = mandate_to_policy(mandate_row)
    context = build_b2_context_for_planning_delivery(session, site.id)
    packet = build_opportunity_intelligence_packet(session, opp, context=context)
    assessment = evaluate_buyer_fit(session, mandate, facts, site_id=site.id)
    return site, opp, mandate_row, mandate, packet, assessment


class _FakeResponse:
    def __init__(self, output_text):
        self.output_text = output_text
        self.status = "completed"
        self.incomplete_details = None


class _FakeResponses:
    def __init__(self, outputs):
        self._outputs = list(outputs)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        item = self._outputs.pop(0)
        if isinstance(item, Exception):
            raise item
        return _FakeResponse(item)


class _FakeClient:
    def __init__(self, outputs):
        self.responses = _FakeResponses(outputs)


def _valid_raw(recommendation="PURSUE", ref_token="packet.total_units"):
    return {
        "recommendation": recommendation,
        "confidence": "HIGH",
        "confidence_basis": [ref_token],
        "acquisition_subject": {"level": "DEVELOPMENT_SITE", "reference": None, "note": None},
        "supporting_reasons": [{"label": "A clean positive signal.", "evidence_reference": ref_token}],
        "countervailing_reasons": [],
        "material_unknowns": [],
        "reasoning_summary": "A concise, evidence-grounded commercial rationale.",
        "next_action": "VERIFY_OWNERSHIP",
        "next_action_detail": "Investigate ownership.",
        "monitoring_trigger": None,
        "evidence_references": [ref_token],
    }


# --- Section 31: subject identity --------------------------------------------

def test_site_recent_permission_and_long_pending_share_one_whole_site_subject():
    for fn in (
        planning_delivery_site_opportunity_id, planning_delivery_recent_permission_opportunity_id,
        planning_delivery_long_pending_application_opportunity_id,
    ):
        assert resolve_acquisition_subject_key(fn(61), PLANNING_DELIVERY) == (PLANNING_DELIVERY, 61, WHOLE_SITE)


def test_phase_3b_and_phase_4_on_same_site_are_different_subjects():
    a = resolve_acquisition_subject_key(planning_delivery_phase_opportunity_id(67, "3B"), PLANNING_DELIVERY)
    b = resolve_acquisition_subject_key(planning_delivery_phase_opportunity_id(67, "4"), PLANNING_DELIVERY)
    assert a != b
    assert a == (PLANNING_DELIVERY, 67, "3B")
    assert b == (PLANNING_DELIVERY, 67, "4")


def test_whole_site_and_a_named_phase_on_same_site_are_different_subjects():
    whole = resolve_acquisition_subject_key(planning_delivery_site_opportunity_id(67), PLANNING_DELIVERY)
    phase = resolve_acquisition_subject_key(planning_delivery_phase_opportunity_id(67, "3B"), PLANNING_DELIVERY)
    assert whole != phase


def test_strategic_land_allocation_resolves_to_whole_allocation_scope():
    key = resolve_acquisition_subject_key(strategic_land_opportunity_id(1), STRATEGIC_LAND)
    assert key == (STRATEGIC_LAND, 1, "WHOLE_ALLOCATION")


def test_get_or_create_subject_anchor_is_idempotent(session):
    a1 = get_or_create_subject_anchor(session, subject_type=PLANNING_DELIVERY, anchor_id=61, scope_key=WHOLE_SITE)
    a2 = get_or_create_subject_anchor(session, subject_type=PLANNING_DELIVERY, anchor_id=61, scope_key=WHOLE_SITE)
    assert a1.id == a2.id
    count = session.execute(select(AcquisitionSubjectAnchor)).scalars().all()
    assert len(count) == 1


def test_lineage_preserved_across_a_long_pending_to_recent_permission_transition(session):
    """The Product Owner's own worked example: the SAME site's opportunity_id
    changes kind as it moves through its lifecycle, but the persistent
    subject anchor (and therefore any lineage referencing it) must be the
    SAME row both times."""
    key1 = resolve_acquisition_subject_key(planning_delivery_long_pending_application_opportunity_id(61), PLANNING_DELIVERY)
    key2 = resolve_acquisition_subject_key(planning_delivery_recent_permission_opportunity_id(61), PLANNING_DELIVERY)
    anchor1 = get_or_create_subject_anchor(session, subject_type=key1[0], anchor_id=key1[1], scope_key=key1[2])
    anchor2 = get_or_create_subject_anchor(session, subject_type=key2[0], anchor_id=key2[1], scope_key=key2[2])
    assert anchor1.id == anchor2.id


def test_opaque_opportunity_id_is_not_the_sole_durable_identity(session):
    """Two structurally different opportunity_id strings for the same real
    site (long_pending vs recent_permission) must map to ONE subject
    anchor - proving the anchor, not the opaque string, is what persistence
    treats as durable."""
    site_opp_id = planning_delivery_site_opportunity_id(61)
    long_pending_opp_id = planning_delivery_long_pending_application_opportunity_id(61)
    assert site_opp_id != long_pending_opp_id
    key_a = resolve_acquisition_subject_key(site_opp_id, PLANNING_DELIVERY)
    key_b = resolve_acquisition_subject_key(long_pending_opp_id, PLANNING_DELIVERY)
    anchor_a = get_or_create_subject_anchor(session, subject_type=key_a[0], anchor_id=key_a[1], scope_key=key_a[2])
    anchor_b = get_or_create_subject_anchor(session, subject_type=key_b[0], anchor_id=key_b[1], scope_key=key_b[2])
    assert anchor_a.id == anchor_b.id


# --- Section 32: fingerprint --------------------------------------------------

def test_identical_commercial_inputs_produce_identical_fingerprint(session):
    _, _, _, _, packet, assessment = _build_case(session)
    fp1 = compute_agent_evaluation_input_fingerprint(
        mandate_fingerprint="fp-mandate", acquisition_type="LAND_SITE_ACQUISITION",
        buyer_fit_assessment=assessment, packet=packet,
    )
    fp2 = compute_agent_evaluation_input_fingerprint(
        mandate_fingerprint="fp-mandate", acquisition_type="LAND_SITE_ACQUISITION",
        buyer_fit_assessment=assessment, packet=packet,
    )
    assert fp1 == fp2


def test_unit_count_change_alters_fingerprint(session):
    _, _, _, _, packet_a, assessment_a = _build_case(session, unit_count=75)
    _, _, _, _, packet_b, assessment_b = _build_case(session, unit_count=200)
    fp_a = compute_agent_evaluation_input_fingerprint(mandate_fingerprint="fp", acquisition_type="LAND_SITE_ACQUISITION", buyer_fit_assessment=assessment_a, packet=packet_a)
    fp_b = compute_agent_evaluation_input_fingerprint(mandate_fingerprint="fp", acquisition_type="LAND_SITE_ACQUISITION", buyer_fit_assessment=assessment_b, packet=packet_b)
    assert fp_a != fp_b


def test_buyer_mandate_fingerprint_change_alters_fingerprint(session):
    _, _, _, _, packet, assessment = _build_case(session)
    fp_a = compute_agent_evaluation_input_fingerprint(mandate_fingerprint="fp-v1", acquisition_type="LAND_SITE_ACQUISITION", buyer_fit_assessment=assessment, packet=packet)
    fp_b = compute_agent_evaluation_input_fingerprint(mandate_fingerprint="fp-v2", acquisition_type="LAND_SITE_ACQUISITION", buyer_fit_assessment=assessment, packet=packet)
    assert fp_a != fp_b


def test_buyer_fit_classification_change_alters_fingerprint(session):
    from dataclasses import replace
    _, _, _, _, packet, assessment = _build_case(session)
    changed = replace(assessment, matches=list(assessment.matches) + ["A brand new match reason."])
    fp_a = compute_agent_evaluation_input_fingerprint(mandate_fingerprint="fp", acquisition_type="LAND_SITE_ACQUISITION", buyer_fit_assessment=assessment, packet=packet)
    fp_b = compute_agent_evaluation_input_fingerprint(mandate_fingerprint="fp", acquisition_type="LAND_SITE_ACQUISITION", buyer_fit_assessment=changed, packet=packet)
    assert fp_a != fp_b


def test_acquisition_type_change_alters_fingerprint(session):
    _, _, _, _, packet, assessment = _build_case(session)
    fp_a = compute_agent_evaluation_input_fingerprint(mandate_fingerprint="fp", acquisition_type="LAND_SITE_ACQUISITION", buyer_fit_assessment=assessment, packet=packet)
    fp_b = compute_agent_evaluation_input_fingerprint(mandate_fingerprint="fp", acquisition_type="STRATEGIC_LAND_CONTROL", buyer_fit_assessment=assessment, packet=packet)
    assert fp_a != fp_b


def test_display_name_change_does_not_alter_fingerprint(session):
    """Section 18: presentation-only fields must never be part of the
    fingerprint payload at all - proven here by confirming the packet's
    own site/council identity fields are never read by the fingerprint
    function (site display name lives on the Site row, never passed into
    compute_agent_evaluation_input_fingerprint at all)."""
    site, opp, _, _, packet, assessment = _build_case(session)
    fp_before = compute_agent_evaluation_input_fingerprint(mandate_fingerprint="fp", acquisition_type="LAND_SITE_ACQUISITION", buyer_fit_assessment=assessment, packet=packet)
    site.display_address = "A Completely Renamed Display Address"
    session.commit()
    fp_after = compute_agent_evaluation_input_fingerprint(mandate_fingerprint="fp", acquisition_type="LAND_SITE_ACQUISITION", buyer_fit_assessment=assessment, packet=packet)
    assert fp_before == fp_after


def test_raw_coverage_timestamp_is_not_part_of_the_fingerprint(session):
    """signals.coverage_checked_at is a raw timestamp explicitly excluded
    (Section 18) - proven structurally: it never appears anywhere in the
    canonical payload, so two packets differing only in that timestamp
    produce the same fingerprint. We assert this by inspecting the
    function's own source rather than constructing two packets that only
    differ by a timestamp (the packet builder ties coverage_checked_at to
    real transaction-signal computation, not a freely injectable field)."""
    import inspect

    from app.policy import agent_evaluation_persistence

    func = agent_evaluation_persistence.compute_agent_evaluation_input_fingerprint
    body_only = inspect.getsource(func).split('"""', 2)[-1]  # strip the docstring, keep only executable code
    assert "coverage_checked_at" not in body_only
    assert ".detail" not in body_only  # only .state is ever read from a transaction signal


# --- Pre-merge fingerprint-completeness audit regressions -------------------
# (Section 1: three real gaps found - developer_indications/conflicts raw
# content, ownership_coverage, linked_strategic_allocation_id - each is
# shown to the LLM as its own reference token but was not previously
# reflected in the fingerprint even when the COMPUTED ownership_control_
# posture stayed unchanged.)

def test_new_developer_identification_changes_fingerprint_even_when_posture_unchanged():
    """Going from no developer named to one developer named does not, on
    its own, flip has_ownership_evidence/conflicts/posture (posture only
    reads conflicts+has_ownership_evidence+scope_verified) - yet the model
    is shown the raw developer_indications list and can legitimately
    reason differently. Must not be a false-negative gap."""
    before = _fp(actors_control=_FakeActorsControl())
    after = _fp(actors_control=_FakeActorsControl(developer_indications=("Bellway Homes Limited",)))
    assert before != after


def test_ownership_coverage_change_alters_fingerprint_even_when_posture_unchanged():
    """"Never searched" (INSUFFICIENT_EVIDENCE_TO_DETERMINE_CONTROL) vs
    "searched thoroughly, found nothing" (RELEVANT_EVIDENCE_SEARCHED_NO_
    CONTROL_INDICATION_FOUND) both leave has_ownership_evidence False and
    ownership_control_posture at INCOMPLETE_NON_BLOCKING - a genuinely
    different evidentiary state ("coverage-aware negative signal
    semantics") that must not be invisible to the fingerprint."""
    before = _fp(actors_control=_FakeActorsControl(ownership_coverage="INSUFFICIENT_EVIDENCE_TO_DETERMINE_CONTROL"))
    after = _fp(actors_control=_FakeActorsControl(ownership_coverage="RELEVANT_EVIDENCE_SEARCHED_NO_CONTROL_INDICATION_FOUND"))
    assert before != after


def test_conflict_content_change_alters_fingerprint_beyond_mere_existence():
    """Both packets have a non-empty conflicts tuple (posture stays
    EVIDENCED_CONFLICT_POTENTIALLY_BLOCKING in both) but the SPECIFIC
    conflict differs - the model is shown the raw text and this must not
    be invisible to the fingerprint."""
    before = _fp(actors_control=_FakeActorsControl(conflicts=("Conflicting developer evidence: A vs B.",)))
    after = _fp(actors_control=_FakeActorsControl(conflicts=("Conflicting developer evidence: A vs B.", "Conflicting ownership declaration: X vs Y.")))
    assert before != after


def test_linked_strategic_allocation_id_change_alters_fingerprint():
    before = _fp(linked_strategic_allocation_id=None)
    after = _fp(linked_strategic_allocation_id=42)
    assert before != after


def test_fingerprint_version_constant_was_bumped_for_this_payload_shape_change():
    from app.policy.agent_evaluation_persistence import AGENT_EVALUATION_INPUT_FINGERPRINT_VERSION
    assert AGENT_EVALUATION_INPUT_FINGERPRINT_VERSION == 2


# --- Section 33: persistence --------------------------------------------------

def test_successful_evaluation_creates_history_and_current_state(session):
    site, opp, mandate_row, mandate, packet, assessment = _build_case(session)
    client = _FakeClient([json.dumps(_valid_raw(recommendation="PURSUE"))])
    outcome = run_persisted_evaluation(
        session, mandate=mandate, mandate_key=mandate_row.buyer.buyer_key, buyer_mandate_id=mandate_row.id,
        mandate_fingerprint="fp-mandate", acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp,
        opportunity_fingerprint="fp-opp", packet=packet, buyer_fit_assessment=assessment, client=client,
    )
    assert outcome.status == "evaluated"
    assert outcome.history.execution_status == SUCCESS
    assert outcome.history.recommendation == "PURSUE"
    assert outcome.current_state.current_history_id == outcome.history.id
    assert outcome.current_state.last_attempt_status == "success"
    assert outcome.current_state.is_current_candidate is True


def test_second_successful_evaluation_creates_new_history_but_updates_current_pointer(session):
    site, opp, mandate_row, mandate, packet, assessment = _build_case(session)
    client = _FakeClient([json.dumps(_valid_raw(recommendation="PURSUE"))])
    first = run_persisted_evaluation(
        session, mandate=mandate, mandate_key=mandate_row.buyer.buyer_key, buyer_mandate_id=mandate_row.id,
        mandate_fingerprint="fp-mandate-v1", acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp,
        opportunity_fingerprint="fp-opp", packet=packet, buyer_fit_assessment=assessment, client=client,
    )
    raw2 = _valid_raw(recommendation="VERIFY")
    raw2["material_unknowns"] = [{
        "fact_or_question": "What is the ownership/control position?", "material": True,
        "resolvable": True, "blocking": True, "why_it_matters": "Determines the acquisition route.",
    }]
    client2 = _FakeClient([json.dumps(raw2)])
    second = run_persisted_evaluation(
        session, mandate=mandate, mandate_key=mandate_row.buyer.buyer_key, buyer_mandate_id=mandate_row.id,
        mandate_fingerprint="fp-mandate-v2", acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp,
        opportunity_fingerprint="fp-opp", packet=packet, buyer_fit_assessment=assessment, client=client2,
    )
    assert first.history.id != second.history.id
    assert second.current_state.id == first.current_state.id
    assert second.current_state.current_history_id == second.history.id
    all_history = session.execute(select(AgentEvaluationHistory)).scalars().all()
    assert len(all_history) == 2  # append-only - the first row still exists


def test_history_rows_are_never_mutated_after_insert(session):
    site, opp, mandate_row, mandate, packet, assessment = _build_case(session)
    client = _FakeClient([json.dumps(_valid_raw(recommendation="PURSUE"))])
    outcome = run_persisted_evaluation(
        session, mandate=mandate, mandate_key=mandate_row.buyer.buyer_key, buyer_mandate_id=mandate_row.id,
        mandate_fingerprint="fp-mandate", acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp,
        opportunity_fingerprint="fp-opp", packet=packet, buyer_fit_assessment=assessment, client=client,
    )
    original_recommendation = outcome.history.recommendation
    reloaded = session.get(AgentEvaluationHistory, outcome.history.id)
    assert reloaded.recommendation == original_recommendation


def test_not_relevant_persists_correctly(session):
    site, opp, mandate_row, mandate, packet, assessment = _build_case(session)
    client = _FakeClient([json.dumps({
        **_valid_raw(recommendation="NOT_RELEVANT"),
        "supporting_reasons": [],
        "countervailing_reasons": [{"label": "A confirmed disqualifying fact.", "evidence_reference": "packet.total_units"}],
    })])
    outcome = run_persisted_evaluation(
        session, mandate=mandate, mandate_key=mandate_row.buyer.buyer_key, buyer_mandate_id=mandate_row.id,
        mandate_fingerprint="fp-mandate", acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp,
        opportunity_fingerprint="fp-opp", packet=packet, buyer_fit_assessment=assessment, client=client,
    )
    assert outcome.history.recommendation == "NOT_RELEVANT"
    assert outcome.current_state.current_history_id == outcome.history.id
    assert outcome.current_state.is_current_candidate is True


def test_failed_evaluation_is_persisted(session):
    site, opp, mandate_row, mandate, packet, assessment = _build_case(session)
    client = _FakeClient(["{not valid json", "{still not valid json"])
    outcome = run_persisted_evaluation(
        session, mandate=mandate, mandate_key=mandate_row.buyer.buyer_key, buyer_mandate_id=mandate_row.id,
        mandate_fingerprint="fp-mandate", acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp,
        opportunity_fingerprint="fp-opp", packet=packet, buyer_fit_assessment=assessment, client=client,
    )
    assert outcome.status == "evaluated"
    assert outcome.history.execution_status == FAILED
    assert outcome.history.recommendation is None


def test_failed_evaluation_does_not_replace_previous_successful_current_evaluation(session):
    site, opp, mandate_row, mandate, packet, assessment = _build_case(session)
    good_client = _FakeClient([json.dumps(_valid_raw(recommendation="PURSUE"))])
    first = run_persisted_evaluation(
        session, mandate=mandate, mandate_key=mandate_row.buyer.buyer_key, buyer_mandate_id=mandate_row.id,
        mandate_fingerprint="fp-mandate-v1", acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp,
        opportunity_fingerprint="fp-opp", packet=packet, buyer_fit_assessment=assessment, client=good_client,
    )
    bad_client = _FakeClient(["{invalid", "{invalid"])
    second = run_persisted_evaluation(
        session, mandate=mandate, mandate_key=mandate_row.buyer.buyer_key, buyer_mandate_id=mandate_row.id,
        mandate_fingerprint="fp-mandate-v2", acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp,
        opportunity_fingerprint="fp-opp", packet=packet, buyer_fit_assessment=assessment, client=bad_client,
    )
    assert second.history.execution_status == FAILED
    # The current-state row's operative recommendation must still be the
    # FIRST (successful) evaluation, never overwritten by the failure.
    assert second.current_state.current_history_id == first.history.id
    assert second.current_state.last_attempt_status == "failed"


def test_no_prior_success_plus_failure_is_represented_honestly(session):
    site, opp, mandate_row, mandate, packet, assessment = _build_case(session)
    client = _FakeClient(["{invalid", "{invalid"])
    outcome = run_persisted_evaluation(
        session, mandate=mandate, mandate_key=mandate_row.buyer.buyer_key, buyer_mandate_id=mandate_row.id,
        mandate_fingerprint="fp-mandate", acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp,
        opportunity_fingerprint="fp-opp", packet=packet, buyer_fit_assessment=assessment, client=client,
    )
    assert outcome.current_state.current_history_id is None
    assert outcome.current_state.last_attempt_status == "failed"


def test_candidate_representation_can_change_while_subject_lineage_remains(session):
    """The site transitions from long_pending_application to recent_
    permission - the CURRENT candidate representation string changes, but
    both evaluations must land on the SAME subject anchor / same current-
    state row."""
    site = _make_site(session, unit_count=75)
    apps = session.execute(select(Application).where(Application.site_id == site.id)).scalars().all()
    operative = build_operative_planning_facts(apps)
    facts = build_planning_delivery_matching_facts_from_operative(operative, apps)
    mandate_row = _seed_mandate(session)
    from app.policy.buyer_profile_store import mandate_to_policy
    mandate = mandate_to_policy(mandate_row)
    context = build_b2_context_for_planning_delivery(session, site.id)

    opp1 = _FakeOpp(planning_delivery_long_pending_application_opportunity_id(site.id), PLANNING_DELIVERY, facts)
    packet1 = build_opportunity_intelligence_packet(session, opp1, context=context)
    assessment1 = evaluate_buyer_fit(session, mandate, facts, site_id=site.id)
    client1 = _FakeClient([json.dumps(_valid_raw(recommendation="MONITOR", ref_token="packet.total_units"))])
    # MONITOR requires a monitoring_trigger.
    raw1 = _valid_raw(recommendation="MONITOR")
    raw1["monitoring_trigger"] = "PLANNING_STATUS_CHANGED"
    client1 = _FakeClient([json.dumps(raw1)])
    first = run_persisted_evaluation(
        session, mandate=mandate, mandate_key=mandate_row.buyer.buyer_key, buyer_mandate_id=mandate_row.id,
        mandate_fingerprint="fp-mandate", acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp1,
        opportunity_fingerprint="fp-opp1", packet=packet1, buyer_fit_assessment=assessment1, client=client1,
    )

    opp2 = _FakeOpp(planning_delivery_recent_permission_opportunity_id(site.id), PLANNING_DELIVERY, facts)
    packet2 = build_opportunity_intelligence_packet(session, opp2, context=context)
    assessment2 = evaluate_buyer_fit(session, mandate, facts, site_id=site.id)
    client2 = _FakeClient([json.dumps(_valid_raw(recommendation="PURSUE"))])
    second = run_persisted_evaluation(
        session, mandate=mandate, mandate_key=mandate_row.buyer.buyer_key, buyer_mandate_id=mandate_row.id,
        mandate_fingerprint="fp-mandate-2", acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp2,
        opportunity_fingerprint="fp-opp2", packet=packet2, buyer_fit_assessment=assessment2, client=client2,
    )

    assert first.current_state.id == second.current_state.id
    assert first.history.subject_anchor_id == second.history.subject_anchor_id
    assert second.current_state.current_opportunity_id == opp2.opportunity_id
    assert second.current_state.current_opportunity_kind == "recent_permission"
    assert first.history.opportunity_kind == "long_pending_application"


# --- Section 34: concurrency (mocked OpenAI only) ---------------------------

def test_first_worker_claims_and_second_cannot_claim_same_fingerprint(session):
    outcome1 = try_claim_evaluation(
        session, buyer_mandate_id=1, subject_anchor_id=1, acquisition_type="LAND_SITE_ACQUISITION",
        evaluation_input_fingerprint="fp-shared",
    )
    outcome2 = try_claim_evaluation(
        session, buyer_mandate_id=1, subject_anchor_id=1, acquisition_type="LAND_SITE_ACQUISITION",
        evaluation_input_fingerprint="fp-shared",
    )
    assert outcome1.status == "claimed"
    assert outcome2.status == "already_in_progress"


def test_second_worker_does_not_proceed_to_evaluation_when_claim_refused(session):
    """The pre-LLM guarantee itself: a refused claim means the caller's own
    orchestration (run_persisted_evaluation) never even constructs a
    client call - proven by a FakeClient that would raise IndexError if
    its create() were ever invoked."""
    site, opp, mandate_row, mandate, packet, assessment = _build_case(session)
    fingerprint = compute_agent_evaluation_input_fingerprint(
        mandate_fingerprint="fp-mandate", acquisition_type="LAND_SITE_ACQUISITION",
        buyer_fit_assessment=assessment, packet=packet,
    )
    subject_type, anchor_id, scope_key = resolve_acquisition_subject_key(opp.opportunity_id, opp.opportunity_type)
    anchor = get_or_create_subject_anchor(session, subject_type=subject_type, anchor_id=anchor_id, scope_key=scope_key)
    # Pre-claim it, simulating a concurrent worker already in progress.
    try_claim_evaluation(
        session, buyer_mandate_id=mandate_row.id, subject_anchor_id=anchor.id,
        acquisition_type="LAND_SITE_ACQUISITION", evaluation_input_fingerprint=fingerprint,
    )
    never_call_client = _FakeClient([])  # would raise IndexError if .create() is ever called
    outcome = run_persisted_evaluation(
        session, mandate=mandate, mandate_key=mandate_row.buyer.buyer_key, buyer_mandate_id=mandate_row.id,
        mandate_fingerprint="fp-mandate", acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp,
        opportunity_fingerprint="fp-opp", packet=packet, buyer_fit_assessment=assessment, client=never_call_client,
    )
    assert outcome.status == "skipped_in_progress"
    assert never_call_client.responses.calls == 0


def test_completed_claim_reports_already_evaluated_and_does_not_call_client(session):
    site, opp, mandate_row, mandate, packet, assessment = _build_case(session)
    client = _FakeClient([json.dumps(_valid_raw(recommendation="PURSUE"))])
    first = run_persisted_evaluation(
        session, mandate=mandate, mandate_key=mandate_row.buyer.buyer_key, buyer_mandate_id=mandate_row.id,
        mandate_fingerprint="fp-mandate", acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp,
        opportunity_fingerprint="fp-opp", packet=packet, buyer_fit_assessment=assessment, client=client,
    )
    never_call_client = _FakeClient([])
    second = run_persisted_evaluation(
        session, mandate=mandate, mandate_key=mandate_row.buyer.buyer_key, buyer_mandate_id=mandate_row.id,
        mandate_fingerprint="fp-mandate", acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp,
        opportunity_fingerprint="fp-opp", packet=packet, buyer_fit_assessment=assessment, client=never_call_client,
    )
    assert second.status == "skipped_already_evaluated"
    assert second.history.id == first.history.id
    assert never_call_client.responses.calls == 0


def test_failed_claim_refuses_a_second_attempt_by_default(session):
    site, opp, mandate_row, mandate, packet, assessment = _build_case(session)
    client = _FakeClient(["{invalid", "{invalid"])
    first = run_persisted_evaluation(
        session, mandate=mandate, mandate_key=mandate_row.buyer.buyer_key, buyer_mandate_id=mandate_row.id,
        mandate_fingerprint="fp-mandate", acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp,
        opportunity_fingerprint="fp-opp", packet=packet, buyer_fit_assessment=assessment, client=client,
    )
    assert first.history.execution_status == FAILED
    never_call_client = _FakeClient([])
    second = run_persisted_evaluation(
        session, mandate=mandate, mandate_key=mandate_row.buyer.buyer_key, buyer_mandate_id=mandate_row.id,
        mandate_fingerprint="fp-mandate", acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp,
        opportunity_fingerprint="fp-opp", packet=packet, buyer_fit_assessment=assessment, client=never_call_client,
    )
    assert second.status == "skipped_previously_failed"
    assert never_call_client.responses.calls == 0


def test_expired_claim_can_be_recovered(session):
    import datetime as dt

    outcome = try_claim_evaluation(
        session, buyer_mandate_id=1, subject_anchor_id=1, acquisition_type="LAND_SITE_ACQUISITION",
        evaluation_input_fingerprint="fp-stale",
    )
    claim = outcome.claim
    claim.claimed_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=999)
    session.commit()

    recovered = try_claim_evaluation(
        session, buyer_mandate_id=1, subject_anchor_id=1, acquisition_type="LAND_SITE_ACQUISITION",
        evaluation_input_fingerprint="fp-stale",
    )
    assert recovered.status == "claimed"


def test_recovered_expired_claim_completes_exactly_once_end_to_end(session):
    """The full worked sequence from Section 2: worker holding DEF crashes
    (claim stays "claimed" forever, never completed) -> expiry makes it
    recoverable -> the recovering worker completes it -> exactly ONE
    AgentEvaluationHistory row and ONE claim row exist in a terminal
    state, never two."""
    site, opp, mandate_row, mandate, packet, assessment = _build_case(session)
    fingerprint = compute_agent_evaluation_input_fingerprint(
        mandate_fingerprint="fp-mandate", acquisition_type="LAND_SITE_ACQUISITION",
        buyer_fit_assessment=assessment, packet=packet,
    )
    subject_type, anchor_id, scope_key = resolve_acquisition_subject_key(opp.opportunity_id, opp.opportunity_type)
    anchor = get_or_create_subject_anchor(session, subject_type=subject_type, anchor_id=anchor_id, scope_key=scope_key)

    # Simulate the crashed worker: claim it, then never complete it.
    crashed = try_claim_evaluation(
        session, buyer_mandate_id=mandate_row.id, subject_anchor_id=anchor.id,
        acquisition_type="LAND_SITE_ACQUISITION", evaluation_input_fingerprint=fingerprint,
    )
    assert crashed.status == "claimed"
    import datetime as dt
    crashed.claim.claimed_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=999)
    session.commit()

    # The recovering worker uses the normal orchestration entry point.
    client = _FakeClient([json.dumps(_valid_raw(recommendation="PURSUE"))])
    recovered_outcome = run_persisted_evaluation(
        session, mandate=mandate, mandate_key=mandate_row.buyer.buyer_key, buyer_mandate_id=mandate_row.id,
        mandate_fingerprint="fp-mandate", acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp,
        opportunity_fingerprint="fp-opp", packet=packet, buyer_fit_assessment=assessment, client=client,
    )
    assert recovered_outcome.status == "evaluated"

    all_claims = session.execute(
        select(AgentEvaluationClaim).where(AgentEvaluationClaim.evaluation_input_fingerprint == fingerprint)
    ).scalars().all()
    all_history = session.execute(
        select(AgentEvaluationHistory).where(AgentEvaluationHistory.evaluation_input_fingerprint == fingerprint)
    ).scalars().all()
    assert len(all_claims) == 1
    assert all_claims[0].status == CLAIM_COMPLETED
    assert len(all_history) == 1


def test_completed_claim_can_be_force_reclaimed_for_a_controlled_release(session):
    """Section 2 pre-merge defect fix: since prompt_version/model_id/
    AGENT_EVALUATION_POLICY_VERSION are deliberately excluded from the
    fingerprint (Section 19's own controlled-release design), a
    "completed" claim for an otherwise-unchanged fingerprint must not
    block a deliberate, explicit future re-evaluation forever - force=True
    is the escape hatch, never automatic."""
    first = try_claim_evaluation(
        session, buyer_mandate_id=1, subject_anchor_id=1, acquisition_type="LAND_SITE_ACQUISITION",
        evaluation_input_fingerprint="fp-release",
    )
    first.claim.status = CLAIM_COMPLETED
    first.claim.history_id = None
    session.commit()

    default_attempt = try_claim_evaluation(
        session, buyer_mandate_id=1, subject_anchor_id=1, acquisition_type="LAND_SITE_ACQUISITION",
        evaluation_input_fingerprint="fp-release",
    )
    assert default_attempt.status == "already_completed"

    forced_attempt = try_claim_evaluation(
        session, buyer_mandate_id=1, subject_anchor_id=1, acquisition_type="LAND_SITE_ACQUISITION",
        evaluation_input_fingerprint="fp-release", force=True,
    )
    assert forced_attempt.status == "claimed"


def test_different_fingerprint_can_be_evaluated_independently(session):
    outcome1 = try_claim_evaluation(
        session, buyer_mandate_id=1, subject_anchor_id=1, acquisition_type="LAND_SITE_ACQUISITION",
        evaluation_input_fingerprint="fp-a",
    )
    outcome2 = try_claim_evaluation(
        session, buyer_mandate_id=1, subject_anchor_id=1, acquisition_type="LAND_SITE_ACQUISITION",
        evaluation_input_fingerprint="fp-b",
    )
    assert outcome1.status == "claimed"
    assert outcome2.status == "claimed"


def test_different_buyer_mandate_can_independently_evaluate_same_subject(session):
    outcome1 = try_claim_evaluation(
        session, buyer_mandate_id=1, subject_anchor_id=1, acquisition_type="LAND_SITE_ACQUISITION",
        evaluation_input_fingerprint="fp-shared",
    )
    outcome2 = try_claim_evaluation(
        session, buyer_mandate_id=2, subject_anchor_id=1, acquisition_type="LAND_SITE_ACQUISITION",
        evaluation_input_fingerprint="fp-shared",
    )
    assert outcome1.status == "claimed"
    assert outcome2.status == "claimed"


# --- Section 35: provenance ---------------------------------------------------

def test_persisted_history_includes_full_provenance(session):
    site, opp, mandate_row, mandate, packet, assessment = _build_case(session)
    client = _FakeClient([json.dumps(_valid_raw(recommendation="PURSUE"))])
    outcome = run_persisted_evaluation(
        session, mandate=mandate, mandate_key=mandate_row.buyer.buyer_key, buyer_mandate_id=mandate_row.id,
        mandate_fingerprint="fp-mandate-xyz", acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp,
        opportunity_fingerprint="fp-opp", packet=packet, buyer_fit_assessment=assessment, client=client,
    )
    h = outcome.history
    assert h.evaluation_policy_version  # non-empty composite string
    assert h.model_provider == "openai"
    assert h.model_id == "gpt-4o-mini"
    assert h.buyer_mandate_fingerprint == "fp-mandate-xyz"
    assert h.evaluation_input_fingerprint
    assert h.retry_count == 0


def test_persisted_prompt_version_is_read_from_the_prompt_module_not_hardcoded(session):
    """Section 3 pre-merge review: GOVERNING_POLICY_PROMPT_VERSION now
    lives in app.policy.agent_evaluation_prompt, the module that owns
    GOVERNING_POLICY itself - persistence only ever reads it. Proven here
    by asserting equality against that module's own constant (not a
    literal), so a future prompt-version bump is picked up automatically
    with no change required in this module."""
    from app.policy.agent_evaluation_prompt import GOVERNING_POLICY_PROMPT_VERSION

    site, opp, mandate_row, mandate, packet, assessment = _build_case(session)
    client = _FakeClient([json.dumps(_valid_raw(recommendation="PURSUE"))])
    outcome = run_persisted_evaluation(
        session, mandate=mandate, mandate_key=mandate_row.buyer.buyer_key, buyer_mandate_id=mandate_row.id,
        mandate_fingerprint="fp-mandate", acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp,
        opportunity_fingerprint="fp-opp", packet=packet, buyer_fit_assessment=assessment, client=client,
    )
    assert outcome.history.prompt_version == GOVERNING_POLICY_PROMPT_VERSION


def test_persisted_structured_output_schema_version_is_read_from_the_owning_module(session):
    """Gate 1 controlled release, Section 1: AGENT_EVALUATION_OUTPUT_
    SCHEMA_VERSION lives in app.policy.acquisition_evaluate, the module
    that owns OUTPUT_SCHEMA itself - persistence only ever reads it.
    Proven here against that module's own constant, not a literal."""
    from app.policy.acquisition_evaluate import AGENT_EVALUATION_OUTPUT_SCHEMA_VERSION

    site, opp, mandate_row, mandate, packet, assessment = _build_case(session)
    client = _FakeClient([json.dumps(_valid_raw(recommendation="PURSUE"))])
    outcome = run_persisted_evaluation(
        session, mandate=mandate, mandate_key=mandate_row.buyer.buyer_key, buyer_mandate_id=mandate_row.id,
        mandate_fingerprint="fp-mandate", acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp,
        opportunity_fingerprint="fp-opp", packet=packet, buyer_fit_assessment=assessment, client=client,
    )
    assert outcome.history.structured_output_schema_version == AGENT_EVALUATION_OUTPUT_SCHEMA_VERSION


def test_structured_output_schema_version_is_persisted_on_every_history_row():
    """The value must be a real, always-populated column - never optional
    provenance that could silently end up NULL."""
    from app.db.models import AgentEvaluationHistory

    column = AgentEvaluationHistory.__table__.columns["structured_output_schema_version"]
    assert column.nullable is False


def test_structured_output_schema_version_is_independent_of_the_evaluation_input_fingerprint():
    """Section 1, IMPORTANT: changing AGENT_EVALUATION_OUTPUT_SCHEMA_
    VERSION must never move agent_evaluation_input_fingerprint_v2 - a
    structured-output schema change is a controlled evaluation release,
    never automatic market-input invalidation. Proven both structurally
    (the fingerprint function's own source never references the schema-
    version constant or module at all) and behaviourally (the fingerprint
    function does not even accept a schema-version parameter, so no
    caller could pass one in even by mistake)."""
    import inspect

    from app.policy import agent_evaluation_persistence

    func = agent_evaluation_persistence.compute_agent_evaluation_input_fingerprint
    source = inspect.getsource(func)
    assert "AGENT_EVALUATION_OUTPUT_SCHEMA_VERSION" not in source
    assert "OUTPUT_SCHEMA" not in source
    assert "acquisition_evaluate" not in source  # never imports from the module owning OUTPUT_SCHEMA at all
    assert "structured_output_schema_version" not in inspect.signature(func).parameters
