"""Agent Evaluation Policy V1 - tests for app.policy.acquisition_evaluate.
evaluate(), the EVALUATE() orchestration entry point.

No real LLM calls anywhere in this file - the OpenAI client is replaced
with a FakeClient whose canned outputs are injected per-test, so every test
here is deterministic and free. Real (in-memory, per-test) database rows
are used to build a real BuyerFitAssessment/OpportunityIntelligencePacket,
exactly as app.policy.acquisition_evaluate.evaluate() expects to receive
them - only the model call itself is faked."""
from __future__ import annotations

import json

from sqlalchemy import select

from app.db.models import Application, Site, SchemeIntelligence
from app.policy.acquisition_evaluate import MODEL, evaluate, evaluate_with_telemetry
from app.policy.agent_evaluation_prompt import build_prompt_context
from app.policy.agent_evaluation_result import (
    ACQUISITION_TYPE_NOT_IN_MANDATE,
    FAILED,
    HIGH,
    MALFORMED_LLM_OUTPUT,
    MONITOR,
    NOT_RELEVANT,
    PURSUE,
    SUCCESS,
    UNSUPPORTED_LANGUAGE_DETECTED,
)
from app.policy.buyer_matching import (
    PERMISSION_GRANTED,
    PLANNING_DELIVERY,
    B2MatchingContext,
    MatchingFacts,
    assess_buyer_fit,
    build_planning_delivery_matching_facts_from_operative,
)
from app.policy.buyer_matching_b2_context import build_b2_context_for_planning_delivery, evaluate_buyer_fit
from app.policy.buyer_profiles import HOUSING_ASSOCIATION, NESTEN_HOMES
from app.policy.terminal_hard_exclusion import classify_terminal_exclusion
from app.reporting.opportunity_intelligence_packet import build_opportunity_intelligence_packet
from app.reporting.opportunity_universe import planning_delivery_site_opportunity_id
from app.reporting.scheme_reconciliation import build_operative_planning_facts


# --- Fixtures: a real (in-memory DB) planning_delivery opportunity ----------

class _FakeOpp:
    def __init__(self, site_id, matching_facts):
        self.opportunity_id = planning_delivery_site_opportunity_id(site_id)
        self.opportunity_type = PLANNING_DELIVERY
        self.matching_facts = matching_facts


def _make_site(session, *, unit_count=75, affordable_percentage=None, affordable_unit_count=None, development_type=None):
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
    si = SchemeIntelligence(
        application_id=app.id, total_units_final=unit_count, core_intelligence_complete=True,
        affordable_percentage_final=affordable_percentage, affordable_units_final=affordable_unit_count,
        development_type=development_type,
    )
    session.add(si)
    session.commit()
    return site


def _build_case(session, *, mandate=NESTEN_HOMES, unit_count=75, affordable_percentage=None, affordable_unit_count=None, development_type=None):
    site = _make_site(
        session, unit_count=unit_count, affordable_percentage=affordable_percentage,
        affordable_unit_count=affordable_unit_count, development_type=development_type,
    )
    apps = session.execute(select(Application).where(Application.site_id == site.id)).scalars().all()
    operative = build_operative_planning_facts(apps)
    facts = build_planning_delivery_matching_facts_from_operative(operative, apps)
    opp = _FakeOpp(site.id, facts)
    context = build_b2_context_for_planning_delivery(session, site.id)
    packet = build_opportunity_intelligence_packet(session, opp, context=context)
    assessment = evaluate_buyer_fit(session, mandate, facts, site_id=site.id)
    return opp, packet, assessment


def _build_terminal_zero_affordable_case(session):
    """Hand-built MatchingFacts (mirroring tests/test_terminal_hard_exclusion.
    py's own proven pattern) rather than the full SchemeIntelligence->
    reconciliation pipeline, which has its own separate, already-tested
    rules about what counts as a trusted affordable figure - not what this
    orchestration test is exercising."""
    site = _make_site(session, unit_count=40)
    facts = MatchingFacts(
        opportunity_type=PLANNING_DELIVERY, unit_count=40, development_type_raw="general_residential",
        is_specialist_development=False, affordable_percentage=0.0, affordable_percentage_trusted=True,
        affordable_unit_count=0, planning_state=PERMISSION_GRANTED, has_identified_planning_activity=True,
        has_phasing_evidence=False, matched_to_site=True,
    )
    opp = _FakeOpp(site.id, facts)
    context = B2MatchingContext()
    packet = build_opportunity_intelligence_packet(session, opp, context=context)
    assessment = assess_buyer_fit(HOUSING_ASSOCIATION, facts, context=context)
    return opp, packet, assessment


def _reference_tokens_for(*, opp, packet, assessment, mandate, acquisition_type):
    """Mirrors evaluate()'s own internal build_prompt_context() call so a
    test can construct a fake LLM response citing REAL reference tokens
    without needing evaluate() to expose its internal PromptContext."""
    terminal = classify_terminal_exclusion(assessment.does_not_match)
    context = build_prompt_context(
        buyer_key=mandate.key, mandate=mandate, acquisition_type=acquisition_type,
        opportunity_id=opp.opportunity_id, opportunity_type=opp.opportunity_type,
        buyer_fit_assessment=assessment, non_terminal_does_not_match=terminal.non_terminal_texts,
        packet=packet, transaction_signals=packet.transaction_signals,
    )
    return context.reference_tokens


def _valid_raw(*, recommendation, ref_token, monitoring_trigger=None, extra_countervailing_ref=None):
    countervailing = []
    if extra_countervailing_ref:
        countervailing = [{"label": "A confirmed negative fact.", "evidence_reference": extra_countervailing_ref}]
    return {
        "recommendation": recommendation,
        "confidence": "HIGH",
        "confidence_basis": [ref_token],
        "acquisition_subject": {"level": "DEVELOPMENT_SITE", "reference": None, "note": None},
        "supporting_reasons": [{"label": "A clean positive signal.", "evidence_reference": ref_token}],
        "countervailing_reasons": countervailing,
        "material_unknowns": [],
        "reasoning_summary": "A concise, evidence-grounded commercial rationale.",
        "next_action": "VERIFY_OWNERSHIP",
        "next_action_detail": "Investigate ownership.",
        "monitoring_trigger": monitoring_trigger,
        "evidence_references": [ref_token] + ([extra_countervailing_ref] if extra_countervailing_ref else []),
    }


# --- Fake OpenAI client -----------------------------------------------------

class _FakeUsageDetails:
    def __init__(self, reasoning_tokens):
        self.reasoning_tokens = reasoning_tokens


class _FakeUsage:
    def __init__(self, input_tokens, output_tokens, total_tokens, reasoning_tokens=None):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens = total_tokens
        self.output_tokens_details = _FakeUsageDetails(reasoning_tokens)


class _FakeResponse:
    def __init__(self, output_text, usage=None):
        self.output_text = output_text
        self.status = "completed"
        self.incomplete_details = None
        self.usage = usage


class _FakeResponses:
    def __init__(self, outputs, usage=None):
        self._outputs = list(outputs)
        self.calls = 0
        self.calls_kwargs = []
        self._usage = usage

    def create(self, **kwargs):
        self.calls += 1
        self.calls_kwargs.append(kwargs)
        item = self._outputs.pop(0)
        if isinstance(item, Exception):
            raise item
        return _FakeResponse(item, usage=self._usage)


class _FakeClient:
    def __init__(self, outputs, usage=None):
        self.responses = _FakeResponses(outputs, usage=usage)


# --- Tests -------------------------------------------------------------------

def test_acquisition_type_not_in_mandate_fails_before_any_llm_call():
    """No DB/packet/client needed at all - this is the very first guard in
    evaluate() (Section 21 flow, step 1)."""
    client = _FakeClient([])  # would raise IndexError if ever called
    result = evaluate(
        session=None, mandate=NESTEN_HOMES, mandate_key="nesten_homes", mandate_fingerprint="fp",
        acquisition_type="AFFORDABLE_HOUSING_PACKAGE", opportunity=_FakeOpp(1, None),
        opportunity_fingerprint="fp", packet=None, buyer_fit_assessment=None, client=client,
    )
    assert result.status == FAILED
    assert result.failure_reason == ACQUISITION_TYPE_NOT_IN_MANDATE
    assert result.evaluation is None
    assert client.responses.calls == 0


def test_terminal_hard_exclusion_short_circuits_without_any_llm_call(session):
    """A confirmed-zero-affordable Housing Association case must resolve
    deterministically - zero calls to the fake client proves the terminal
    path never reaches the model."""
    opp, packet, assessment = _build_terminal_zero_affordable_case(session)
    client = _FakeClient([])
    result = evaluate(
        session=session, mandate=HOUSING_ASSOCIATION, mandate_key="housing_association", mandate_fingerprint="fp",
        acquisition_type="AFFORDABLE_HOUSING_PACKAGE", opportunity=opp, opportunity_fingerprint="fp",
        packet=packet, buyer_fit_assessment=assessment, client=client,
    )
    assert result.status == SUCCESS
    assert result.evaluation.recommendation == NOT_RELEVANT
    assert result.evaluation.confidence == HIGH
    assert result.retry_count == 0
    assert client.responses.calls == 0


def test_valid_first_response_succeeds_with_zero_retries(session):
    opp, packet, assessment = _build_case(session, unit_count=75)
    tokens = _reference_tokens_for(opp=opp, packet=packet, assessment=assessment, mandate=NESTEN_HOMES, acquisition_type="LAND_SITE_ACQUISITION")
    ref = next(iter(tokens))
    raw = _valid_raw(recommendation=PURSUE, ref_token=ref)
    client = _FakeClient([json.dumps(raw)])

    result = evaluate(
        session=session, mandate=NESTEN_HOMES, mandate_key="nesten_homes", mandate_fingerprint="fp",
        acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp, opportunity_fingerprint="fp",
        packet=packet, buyer_fit_assessment=assessment, client=client,
    )
    assert result.status == SUCCESS
    assert result.evaluation.recommendation == PURSUE
    assert result.retry_count == 0
    assert client.responses.calls == 1


def test_invalid_then_valid_response_succeeds_with_one_retry(session):
    """Bounded repair/retry policy: an invalid first attempt (unknown
    reference token cited) is repaired by a second, valid attempt -
    MAX_REPAIR_ATTEMPTS=1 permits exactly this."""
    opp, packet, assessment = _build_case(session, unit_count=75)
    tokens = _reference_tokens_for(opp=opp, packet=packet, assessment=assessment, mandate=NESTEN_HOMES, acquisition_type="LAND_SITE_ACQUISITION")
    ref = next(iter(tokens))

    invalid_raw = _valid_raw(recommendation=PURSUE, ref_token="not_a_real_reference_token")
    valid_raw = _valid_raw(recommendation=PURSUE, ref_token=ref)
    client = _FakeClient([json.dumps(invalid_raw), json.dumps(valid_raw)])

    result = evaluate(
        session=session, mandate=NESTEN_HOMES, mandate_key="nesten_homes", mandate_fingerprint="fp",
        acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp, opportunity_fingerprint="fp",
        packet=packet, buyer_fit_assessment=assessment, client=client,
    )
    assert result.status == SUCCESS
    assert result.retry_count == 1
    assert client.responses.calls == 2


def test_still_invalid_after_bounded_retry_fails_with_diagnostic(session):
    opp, packet, assessment = _build_case(session, unit_count=75)
    invalid_raw = _valid_raw(recommendation=PURSUE, ref_token="not_a_real_reference_token")
    client = _FakeClient([json.dumps(invalid_raw), json.dumps(invalid_raw)])

    result = evaluate(
        session=session, mandate=NESTEN_HOMES, mandate_key="nesten_homes", mandate_fingerprint="fp",
        acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp, opportunity_fingerprint="fp",
        packet=packet, buyer_fit_assessment=assessment, client=client,
    )
    assert result.status == FAILED
    assert result.failure_reason == MALFORMED_LLM_OUTPUT
    assert result.retry_count == 1
    assert client.responses.calls == 2
    assert result.evaluation is None
    assert result.diagnostic_detail is not None and "not_a_real_reference_token" in result.diagnostic_detail


def test_json_parse_exception_retries_then_fails_with_exception_diagnostic(session):
    """A malformed-JSON / SDK exception on both attempts must produce
    FAILED/MALFORMED_LLM_OUTPUT with the real exception preserved in
    diagnostic_detail - never an uncaught crash, and never silently
    discarding the cause (the real gap fixed after a live-calibration
    batch run produced an undiagnosable FAILED result)."""
    opp, packet, assessment = _build_case(session, unit_count=75)
    client = _FakeClient(["{not valid json", "{also not valid json"])

    result = evaluate(
        session=session, mandate=NESTEN_HOMES, mandate_key="nesten_homes", mandate_fingerprint="fp",
        acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp, opportunity_fingerprint="fp",
        packet=packet, buyer_fit_assessment=assessment, client=client,
    )
    assert result.status == FAILED
    assert result.failure_reason == MALFORMED_LLM_OUTPUT
    assert result.retry_count == 1
    assert client.responses.calls == 2
    assert result.diagnostic_detail is not None
    assert "JSONDecodeError" in result.diagnostic_detail


def test_unsupported_language_failure_reason_distinct_from_malformed(session):
    """A response that is syntactically valid JSON/schema but uses
    forbidden seller-intent language must fail as UNSUPPORTED_LANGUAGE_
    DETECTED, not the generic MALFORMED_LLM_OUTPUT bucket - the caller can
    branch on WHY the evaluation failed."""
    opp, packet, assessment = _build_case(session, unit_count=75)
    tokens = _reference_tokens_for(opp=opp, packet=packet, assessment=assessment, mandate=NESTEN_HOMES, acquisition_type="LAND_SITE_ACQUISITION")
    ref = next(iter(tokens))
    raw = _valid_raw(recommendation=PURSUE, ref_token=ref)
    raw["reasoning_summary"] = "The site is available and the owner wants to sell."
    client = _FakeClient([json.dumps(raw), json.dumps(raw)])

    result = evaluate(
        session=session, mandate=NESTEN_HOMES, mandate_key="nesten_homes", mandate_fingerprint="fp",
        acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp, opportunity_fingerprint="fp",
        packet=packet, buyer_fit_assessment=assessment, client=client,
    )
    assert result.status == FAILED
    assert result.failure_reason == UNSUPPORTED_LANGUAGE_DETECTED
    assert result.retry_count == 1


def test_not_relevant_citing_only_buyer_fit_unknown_is_repaired_or_fails(session):
    """Regression test for the live-calibration finding: a model that
    grounds NOT_RELEVANT solely in a buyer_fit.unknown[i] token (Buyer
    Fit's own could-not-establish bucket, not a confirmed fact) must never
    reach SUCCESS with that as the only countervailing basis - either the
    bounded retry repairs it into something citing a real confirmed fact,
    or it fails outright. It must never silently pass."""
    opp, packet, assessment = _build_case(session, unit_count=75)
    tokens = _reference_tokens_for(opp=opp, packet=packet, assessment=assessment, mandate=NESTEN_HOMES, acquisition_type="LAND_SITE_ACQUISITION")
    unknown_refs = [t for t in tokens if t.startswith("buyer_fit.unknown[")]
    assert unknown_refs, "fixture must produce at least one buyer_fit.unknown[] token for this test to be meaningful"
    unknown_ref = unknown_refs[0]

    bad_raw = {
        "recommendation": NOT_RELEVANT,
        "confidence": "HIGH",
        "confidence_basis": [unknown_ref],
        "acquisition_subject": {"level": "DEVELOPMENT_SITE", "reference": None, "note": None},
        "supporting_reasons": [],
        "countervailing_reasons": [{"label": "Framed as if confirmed.", "evidence_reference": unknown_ref}],
        "material_unknowns": [],
        "reasoning_summary": "Not relevant based on an unresolved fact only.",
        "next_action": "NO_ACTION",
        "next_action_detail": "",
        "monitoring_trigger": None,
        "evidence_references": [unknown_ref],
    }
    client = _FakeClient([json.dumps(bad_raw), json.dumps(bad_raw)])

    result = evaluate(
        session=session, mandate=NESTEN_HOMES, mandate_key="nesten_homes", mandate_fingerprint="fp",
        acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp, opportunity_fingerprint="fp",
        packet=packet, buyer_fit_assessment=assessment, client=client,
    )
    assert result.status == FAILED
    assert result.failure_reason == MALFORMED_LLM_OUTPUT
    assert "CONFIRMED MANDATE-INCOMPATIBILITY fact" in result.diagnostic_detail


def test_monitor_with_valid_trigger_and_confirmed_countervailing_succeeds(session):
    opp, packet, assessment = _build_case(session, unit_count=75)
    tokens = _reference_tokens_for(opp=opp, packet=packet, assessment=assessment, mandate=NESTEN_HOMES, acquisition_type="LAND_SITE_ACQUISITION")
    positive_ref = next(t for t in tokens if t.startswith("packet.") or t.startswith("signals."))
    negative_ref = positive_ref
    raw = _valid_raw(recommendation=MONITOR, ref_token=positive_ref, monitoring_trigger="OWNERSHIP_EVIDENCE_CHANGED", extra_countervailing_ref=negative_ref)
    client = _FakeClient([json.dumps(raw)])

    result = evaluate(
        session=session, mandate=NESTEN_HOMES, mandate_key="nesten_homes", mandate_fingerprint="fp",
        acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp, opportunity_fingerprint="fp",
        packet=packet, buyer_fit_assessment=assessment, client=client,
    )
    assert result.status == SUCCESS
    assert result.evaluation.recommendation == MONITOR
    assert result.evaluation.monitoring_trigger == "OWNERSHIP_EVIDENCE_CHANGED"


# --- Agent Evaluation Benchmark V1, Implementation Gate: additive seam ------
# --- safety tests (Modification #1/#2 - "prove through tests") -------------

def test_ordinary_evaluate_always_requests_the_production_model(session):
    """evaluate() (the production entry point) must request MODEL - never a
    caller-suppliable value - regardless of anything a benchmark call
    elsewhere in the process might have done first."""
    opp, packet, assessment = _build_case(session, unit_count=75)
    tokens = _reference_tokens_for(opp=opp, packet=packet, assessment=assessment, mandate=NESTEN_HOMES, acquisition_type="LAND_SITE_ACQUISITION")
    ref = next(iter(tokens))
    raw = _valid_raw(recommendation=PURSUE, ref_token=ref)
    client = _FakeClient([json.dumps(raw)])

    result = evaluate(
        session=session, mandate=NESTEN_HOMES, mandate_key="nesten_homes", mandate_fingerprint="fp",
        acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp, opportunity_fingerprint="fp",
        packet=packet, buyer_fit_assessment=assessment, client=client,
    )
    assert result.status == SUCCESS
    assert client.responses.calls_kwargs[0]["model"] == MODEL
    assert "reasoning" not in client.responses.calls_kwargs[0]


def test_benchmark_evaluate_with_telemetry_uses_explicitly_requested_model(session):
    """evaluate_with_telemetry() must request exactly the model/reasoning
    configuration the caller supplied - never silently substitute MODEL."""
    opp, packet, assessment = _build_case(session, unit_count=75)
    tokens = _reference_tokens_for(opp=opp, packet=packet, assessment=assessment, mandate=NESTEN_HOMES, acquisition_type="LAND_SITE_ACQUISITION")
    ref = next(iter(tokens))
    raw = _valid_raw(recommendation=PURSUE, ref_token=ref)
    client = _FakeClient([json.dumps(raw)], usage=_FakeUsage(1000, 200, 1200, reasoning_tokens=50))

    result, telemetry = evaluate_with_telemetry(
        session=session, mandate=NESTEN_HOMES, mandate_key="nesten_homes", mandate_fingerprint="fp",
        acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp, opportunity_fingerprint="fp",
        packet=packet, buyer_fit_assessment=assessment, client=client,
        model="gpt-5.6-terra", reasoning_effort="medium",
    )
    assert result.status == SUCCESS
    assert client.responses.calls_kwargs[0]["model"] == "gpt-5.6-terra"
    assert client.responses.calls_kwargs[0]["reasoning"] == {"effort": "medium"}
    assert telemetry.model == "gpt-5.6-terra"
    assert telemetry.reasoning_effort == "medium"
    assert telemetry.input_tokens == 1000
    assert telemetry.output_tokens == 200
    assert telemetry.total_tokens == 1200
    assert telemetry.reasoning_tokens == 50
    assert telemetry.api_call_count == 1
    assert telemetry.retry_count == 0
    assert telemetry.wall_clock_seconds >= 0.0


def test_benchmark_model_choice_cannot_mutate_production_module_state(session):
    """A benchmark call requesting a non-production model must never alter
    what a SUBSEQUENT plain evaluate() call does for a different caller -
    proves there is no module-global mutation (no monkeypatching MODEL)
    anywhere in this seam."""
    opp, packet, assessment = _build_case(session, unit_count=75)
    tokens = _reference_tokens_for(opp=opp, packet=packet, assessment=assessment, mandate=NESTEN_HOMES, acquisition_type="LAND_SITE_ACQUISITION")
    ref = next(iter(tokens))
    raw = _valid_raw(recommendation=PURSUE, ref_token=ref)

    benchmark_client = _FakeClient([json.dumps(raw)])
    evaluate_with_telemetry(
        session=session, mandate=NESTEN_HOMES, mandate_key="nesten_homes", mandate_fingerprint="fp",
        acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp, opportunity_fingerprint="fp",
        packet=packet, buyer_fit_assessment=assessment, client=benchmark_client,
        model="gpt-6-astra", reasoning_effort="high",
    )
    assert benchmark_client.responses.calls_kwargs[0]["model"] == "gpt-6-astra"
    assert MODEL == "gpt-4o-mini", "MODEL constant must remain the production default, unmutated"

    production_client = _FakeClient([json.dumps(raw)])
    evaluate(
        session=session, mandate=NESTEN_HOMES, mandate_key="nesten_homes", mandate_fingerprint="fp",
        acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp, opportunity_fingerprint="fp",
        packet=packet, buyer_fit_assessment=assessment, client=production_client,
    )
    assert production_client.responses.calls_kwargs[0]["model"] == MODEL


def test_telemetry_zero_calls_for_terminal_hard_exclusion(session):
    """A deterministic terminal-exclusion path makes zero OpenAI calls -
    evaluate_with_telemetry() must report that honestly (api_call_count=0,
    every token field None), never fabricate a call that never happened."""
    opp, packet, assessment = _build_terminal_zero_affordable_case(session)
    client = _FakeClient([])
    result, telemetry = evaluate_with_telemetry(
        session=session, mandate=HOUSING_ASSOCIATION, mandate_key="housing_association", mandate_fingerprint="fp",
        acquisition_type="AFFORDABLE_HOUSING_PACKAGE", opportunity=opp, opportunity_fingerprint="fp",
        packet=packet, buyer_fit_assessment=assessment, client=client, model="gpt-5.6-luna",
    )
    assert result.status == SUCCESS
    assert result.evaluation.recommendation == NOT_RELEVANT
    assert telemetry.api_call_count == 0
    assert telemetry.input_tokens is None and telemetry.output_tokens is None and telemetry.total_tokens is None
    assert client.responses.calls == 0


def test_telemetry_counts_repair_retry_as_two_api_calls(session):
    opp, packet, assessment = _build_case(session, unit_count=75)
    tokens = _reference_tokens_for(opp=opp, packet=packet, assessment=assessment, mandate=NESTEN_HOMES, acquisition_type="LAND_SITE_ACQUISITION")
    ref = next(iter(tokens))
    invalid_raw = _valid_raw(recommendation=PURSUE, ref_token="not_a_real_reference_token")
    valid_raw = _valid_raw(recommendation=PURSUE, ref_token=ref)
    client = _FakeClient(
        [json.dumps(invalid_raw), json.dumps(valid_raw)],
        usage=_FakeUsage(500, 100, 600),
    )

    result, telemetry = evaluate_with_telemetry(
        session=session, mandate=NESTEN_HOMES, mandate_key="nesten_homes", mandate_fingerprint="fp",
        acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp, opportunity_fingerprint="fp",
        packet=packet, buyer_fit_assessment=assessment, client=client, model="gpt-5.6-luna",
    )
    assert result.status == SUCCESS
    assert result.retry_count == 1
    assert telemetry.api_call_count == 2
    assert telemetry.retry_count == 1
    # usage accumulated across BOTH calls (500+500 input, 100+100 output) -
    # the repaired attempt's own tokens are real cost, never discarded.
    assert telemetry.input_tokens == 1000
    assert telemetry.output_tokens == 200
    assert telemetry.total_tokens == 1200


def test_gpt_4o_mini_style_model_omits_reasoning_kwarg_by_default(session):
    """evaluate_with_telemetry() called with reasoning_effort=None (the
    correct configuration for a model generation that predates configurable
    reasoning, e.g. gpt-4o-mini) must never send a `reasoning` kwarg at
    all - some models reject an unrecognised parameter outright."""
    opp, packet, assessment = _build_case(session, unit_count=75)
    tokens = _reference_tokens_for(opp=opp, packet=packet, assessment=assessment, mandate=NESTEN_HOMES, acquisition_type="LAND_SITE_ACQUISITION")
    ref = next(iter(tokens))
    raw = _valid_raw(recommendation=PURSUE, ref_token=ref)
    client = _FakeClient([json.dumps(raw)])

    evaluate_with_telemetry(
        session=session, mandate=NESTEN_HOMES, mandate_key="nesten_homes", mandate_fingerprint="fp",
        acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp, opportunity_fingerprint="fp",
        packet=packet, buyer_fit_assessment=assessment, client=client, model="gpt-4o-mini", reasoning_effort=None,
    )
    assert "reasoning" not in client.responses.calls_kwargs[0]
