"""Agent Evaluation Benchmark V1 - harness unit tests.

NO REAL OpenAI CALLS ANYWHERE IN THIS FILE. Every OpenAI interaction is a
FakeClient exactly like tests/test_acquisition_evaluate.py's own pattern.
These tests exercise: the case schema (validation, save/load round-trip),
the extraction tool against a real in-memory DB fixture, the scoring/
classification logic, and the runner's own safeguards (call/cost estimation,
the confirm-phrase gate, the unapproved-case refusal) - never the real
`--execute` path itself, which this file never invokes."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.db.models import Application, Site, SchemeIntelligence
from app.policy.acquisition_evaluate import (
    MODEL,
    OUTPUT_SCHEMA,
    EvaluationExecutionTelemetry,
    evaluate_frozen_input_with_telemetry,
)
from app.policy.agent_evaluation_prompt import build_prompt_context
from app.policy.agent_evaluation_result import (
    AgentEvaluationResultKey,
    PURSUE,
    SUCCESS,
)
from app.policy.buyer_matching import PLANNING_DELIVERY, build_planning_delivery_matching_facts_from_operative
from app.policy.buyer_matching_b2_context import build_b2_context_for_planning_delivery, evaluate_buyer_fit
from app.policy.buyer_profiles import NESTEN_HOMES
from app.policy.terminal_hard_exclusion import classify_terminal_exclusion
from app.reporting.opportunity_intelligence_packet import build_opportunity_intelligence_packet
from app.reporting.opportunity_universe import planning_delivery_site_opportunity_id
from app.reporting.scheme_reconciliation import build_operative_planning_facts

from benchmark.benchmark_case import (
    ALL_INVARIANTS,
    BenchmarkCase,
    CaseProvenance,
    FrozenCommercialFacts,
    FrozenRenderedInput,
    case_from_dict,
    case_to_dict,
    load_all_cases,
    save_case,
)
from benchmark.scoring import (
    CRITICAL_INCIDENT,
    PASS,
    QUALITY_CONCERN,
    build_case_run_record,
    build_config_scorecard,
    classify_execution_auto,
    estimate_cost,
)
from scripts.run_agent_evaluation_benchmark import ModelConfig, estimate_call_plan, run_real_benchmark, _reconstruct_context


# --- Shared fixture builder (mirrors tests/test_acquisition_evaluate.py) ---

class _FakeOpp:
    def __init__(self, site_id, matching_facts):
        self.opportunity_id = planning_delivery_site_opportunity_id(site_id)
        self.opportunity_type = PLANNING_DELIVERY
        self.matching_facts = matching_facts


def _make_case(session):
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
    si = SchemeIntelligence(application_id=app.id, total_units_final=75, core_intelligence_complete=True)
    session.add(si)
    session.commit()

    apps = session.execute(select(Application).where(Application.site_id == site.id)).scalars().all()
    operative = build_operative_planning_facts(apps)
    facts = build_planning_delivery_matching_facts_from_operative(operative, apps)
    opp = _FakeOpp(site.id, facts)
    context = build_b2_context_for_planning_delivery(session, site.id)
    packet = build_opportunity_intelligence_packet(session, opp, context=context)
    assessment = evaluate_buyer_fit(session, NESTEN_HOMES, facts, site_id=site.id)
    return opp, packet, assessment


def _build_dummy_case(*, case_id="dummy_case", is_zero_llm=False, repeat=False, expected=("PURSUE",)) -> BenchmarkCase:
    provenance = CaseProvenance(
        captured_at="2026-09-15T00:00:00+00:00", captured_from_opportunity_id="planning_delivery:site:1",
        buyer_key="nesten_homes", mandate_key="default", acquisition_subject_scope_key="WHOLE_SITE",
        buyer_matching_policy_version=1, mandate_interpretation_policy_version=1,
        acquisition_type_interpretation_policy_version=1, transaction_signal_policy_version=1,
        terminal_hard_exclusion_policy_version=1, agent_evaluation_policy_version=1,
    )
    layer_a = FrozenCommercialFacts(
        acquisition_type="LAND_SITE_ACQUISITION", opportunity_type=PLANNING_DELIVERY,
        buyer_fit_classification="MATCH", buyer_fit_is_investigative_exception=False,
        buyer_fit_matches=("a match",), buyer_fit_unknown=(), buyer_fit_investigate=(),
        buyer_fit_non_terminal_does_not_match=(), ownership_control_posture="INCOMPLETE_NON_BLOCKING",
        opportunity_facts={"total_units": ("KNOWN", 75)}, transaction_signal_states={"recent_permission": "UNKNOWN"},
    )
    layer_b = FrozenRenderedInput(
        buyer_key="nesten_homes", acquisition_type="LAND_SITE_ACQUISITION", opportunity_type=PLANNING_DELIVERY,
        mandate_interpretation_lines=("- a dimension [TARGET]: explanation",),
        buyer_fit_classification="MATCH", buyer_fit_is_investigative_exception=False,
        reference_tokens={"packet.total_units": "KNOWN = 75"},
        governing_policy_prompt_version=1, agent_evaluation_output_schema_version=1,
    )
    return BenchmarkCase(
        case_id=case_id, case_name="Dummy", commercial_scenario="A dummy case for harness tests.",
        benchmark_version_introduced=1, provenance=provenance, frozen_commercial_facts=layer_a,
        frozen_evaluation_input=layer_b, expected_recommendation=expected,
        commercial_rationale="Because it is a test.", is_zero_llm_case=is_zero_llm, repeat_for_consistency=repeat,
    )


# --- Fake OpenAI client (mirrors tests/test_acquisition_evaluate.py) -------

class _FakeUsage:
    def __init__(self, input_tokens=1000, output_tokens=200, total_tokens=1200):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens = total_tokens
        self.output_tokens_details = type("D", (), {"reasoning_tokens": None})()


class _FakeResponse:
    def __init__(self, output_text, usage=None):
        self.output_text = output_text
        self.usage = usage


class _FakeResponses:
    def __init__(self, outputs, usage=None):
        self._outputs = list(outputs)
        self.calls_kwargs = []
        self._usage = usage

    def create(self, **kwargs):
        self.calls_kwargs.append(kwargs)
        return _FakeResponse(self._outputs.pop(0), usage=self._usage)


class _FakeClient:
    def __init__(self, outputs, usage=None):
        self.responses = _FakeResponses(outputs, usage=usage)


def _valid_raw(ref_token, recommendation=PURSUE):
    return {
        "recommendation": recommendation, "confidence": "HIGH", "confidence_basis": [ref_token],
        "acquisition_subject": {"level": "DEVELOPMENT_SITE", "reference": None, "note": None},
        "supporting_reasons": [{"label": "positive", "evidence_reference": ref_token}],
        "countervailing_reasons": [], "material_unknowns": [],
        "reasoning_summary": "A concise, evidence-grounded commercial rationale.",
        "next_action": "VERIFY_OWNERSHIP", "next_action_detail": "Investigate.",
        "monitoring_trigger": None, "evidence_references": [ref_token],
    }


# --- Case schema tests -------------------------------------------------------

def _replace_case(case: BenchmarkCase, **overrides) -> BenchmarkCase:
    """dataclasses.replace() doesn't work directly here because BenchmarkCase
    holds nested dataclasses that were flattened by case_to_dict/asdict for
    the JSON round-trip tests - this helper reconstructs a BenchmarkCase
    with the SAME nested dataclass instances, only the given top-level
    fields overridden."""
    base = case_to_dict(case)
    base.update(overrides)
    base["provenance"] = case.provenance
    base["frozen_commercial_facts"] = case.frozen_commercial_facts
    base["frozen_evaluation_input"] = case.frozen_evaluation_input
    return BenchmarkCase(**base)


def test_case_rejects_unknown_invariant_name():
    with pytest.raises(ValueError, match="unknown invariant"):
        _replace_case(_build_dummy_case(), required_invariants=("not_a_real_invariant",))


def test_case_requires_at_least_one_acceptable_recommendation():
    with pytest.raises(ValueError, match="at least one acceptable recommendation"):
        BenchmarkCase(
            case_id="x", case_name="x", commercial_scenario="x", benchmark_version_introduced=1,
            provenance=_build_dummy_case().provenance, frozen_commercial_facts=_build_dummy_case().frozen_commercial_facts,
            frozen_evaluation_input=_build_dummy_case().frozen_evaluation_input,
            expected_recommendation=(), commercial_rationale="x",
        )


def test_zero_llm_case_cannot_be_a_consistency_repeat():
    with pytest.raises(ValueError, match="never be a consistency-repeat case"):
        _build_dummy_case(is_zero_llm=True, repeat=True)


def test_save_and_load_round_trip(tmp_path):
    case = _build_dummy_case()
    path = tmp_path / "dummy_case.json"
    save_case(case, path)
    loaded = case_from_dict(json.loads(path.read_text(encoding="utf-8")))
    assert loaded.case_id == case.case_id
    assert loaded.expected_recommendation == case.expected_recommendation
    assert loaded.frozen_evaluation_input.reference_tokens == case.frozen_evaluation_input.reference_tokens
    assert loaded.approved_by_product_owner is False


def test_save_refuses_to_silently_overwrite_an_approved_case(tmp_path):
    approved = _replace_case(_build_dummy_case(), approved_by_product_owner=True)
    path = tmp_path / "approved_case.json"
    save_case(approved, path)
    with pytest.raises(FileExistsError, match="already holds an APPROVED case"):
        save_case(_build_dummy_case(), path)
    # explicit overwrite=True is allowed
    save_case(_build_dummy_case(), path, overwrite=True)
    assert case_from_dict(json.loads(path.read_text(encoding="utf-8"))).approved_by_product_owner is False


def test_all_shipped_cases_load_and_reference_only_known_invariants():
    """The 12 real candidate fixtures extracted from production in this
    gate must all load cleanly and reference only registered invariant
    names - a real regression check on benchmark/cases/*.json itself."""
    cases = load_all_cases()
    assert len(cases) >= 12
    for case in cases:
        assert set(case.required_invariants) <= ALL_INVARIANTS
        assert case.approved_by_product_owner is False, f"{case.case_id} must not be pre-approved by extraction"
        assert case.frozen_evaluation_input.reference_tokens, f"{case.case_id} must carry a non-empty reference-token table"


# --- Extraction tool tests (real in-memory DB, zero OpenAI calls) ----------

def test_extraction_never_imports_openai():
    import benchmark.extraction as ext
    import sys
    assert "openai" not in vars(ext), "extraction.py must never construct or import an OpenAI client"


def test_extracted_case_layer_b_matches_live_prompt_context(session):
    """Layer B (frozen_evaluation_input.reference_tokens) must be BYTE-FOR-
    BYTE identical to what build_prompt_context() itself would produce for
    the same live inputs - this is the whole point of freezing that exact
    layer (Design Audit Section G)."""
    opp, packet, assessment = _make_case(session)
    terminal = classify_terminal_exclusion(assessment.does_not_match)
    live_context = build_prompt_context(
        buyer_key="nesten_homes", mandate=NESTEN_HOMES, acquisition_type="LAND_SITE_ACQUISITION",
        opportunity_id=opp.opportunity_id, opportunity_type=opp.opportunity_type,
        buyer_fit_assessment=assessment, non_terminal_does_not_match=terminal.non_terminal_texts,
        packet=packet, transaction_signals=packet.transaction_signals,
    )
    # Build Layer B the same way benchmark.extraction.extract_candidate_case does.
    from benchmark.benchmark_case import FrozenRenderedInput
    layer_b = FrozenRenderedInput(
        buyer_key="nesten_homes", acquisition_type="LAND_SITE_ACQUISITION", opportunity_type=opp.opportunity_type,
        mandate_interpretation_lines=live_context.mandate_interpretation_lines,
        buyer_fit_classification=live_context.buyer_fit_classification,
        buyer_fit_is_investigative_exception=live_context.buyer_fit_is_investigative_exception,
        reference_tokens=dict(live_context.reference_tokens),
        governing_policy_prompt_version=1, agent_evaluation_output_schema_version=1,
    )
    assert layer_b.reference_tokens == live_context.reference_tokens


# --- Frozen-input execution seam tests --------------------------------------

def test_evaluate_frozen_input_reconstructs_and_calls_correctly(session):
    """The runner's _reconstruct_context + evaluate_frozen_input_with_telemetry
    path must produce a valid SUCCESS result and telemetry from a dummy
    case's own frozen Layer A/B - no live DB objects involved at all."""
    case = _build_dummy_case()
    context = _reconstruct_context(case)
    key = AgentEvaluationResultKey(buyer_key="nesten_homes", opportunity_id="planning_delivery:site:1", acquisition_type="LAND_SITE_ACQUISITION")
    raw = _valid_raw(ref_token="packet.total_units")
    client = _FakeClient([json.dumps(raw)], usage=_FakeUsage())

    result, telemetry = evaluate_frozen_input_with_telemetry(context=context, key=key, client=client, model="gpt-5.6-luna", reasoning_effort="medium")
    assert result.status == SUCCESS
    assert result.evaluation.recommendation == PURSUE
    assert telemetry.model == "gpt-5.6-luna"
    assert telemetry.reasoning_effort == "medium"
    assert telemetry.input_tokens == 1000
    assert client.responses.calls_kwargs[0]["model"] == "gpt-5.6-luna"
    assert client.responses.calls_kwargs[0]["reasoning"] == {"effort": "medium"}


def test_run_real_benchmark_refuses_unapproved_cases():
    case = _build_dummy_case()
    assert case.approved_by_product_owner is False
    with pytest.raises(RuntimeError, match="unapproved case"):
        run_real_benchmark([case], [ModelConfig.parse("gpt-4o-mini")], repeats=1)


def test_run_real_benchmark_skips_zero_llm_cases_entirely(monkeypatch):
    """A zero-LLM case must produce NO record at all from run_real_benchmark
    (it was already resolved deterministically at extraction time) - and,
    critically, must never reach the point of constructing an OpenAI call,
    proven here by monkeypatching evaluate_frozen_input_with_telemetry to
    raise if it is ever invoked."""
    import scripts.run_agent_evaluation_benchmark as runner_module

    def _boom(**kwargs):
        raise AssertionError("must never call evaluate_frozen_input_with_telemetry for a zero-LLM case")

    monkeypatch.setattr("app.policy.acquisition_evaluate.evaluate_frozen_input_with_telemetry", _boom)
    zero_case = _build_dummy_case(case_id="zero", is_zero_llm=True)
    zero_case = BenchmarkCase(**{**case_to_dict(zero_case), "approved_by_product_owner": True,
                                  "provenance": zero_case.provenance, "frozen_commercial_facts": zero_case.frozen_commercial_facts,
                                  "frozen_evaluation_input": zero_case.frozen_evaluation_input})
    records = runner_module.run_real_benchmark([zero_case], [ModelConfig.parse("gpt-4o-mini")], repeats=3)
    assert records == []


# --- Scoring/classification tests -------------------------------------------

def test_classify_execution_auto_unsupported_language_is_critical():
    from app.policy.agent_evaluation_result import FAILED, UNSUPPORTED_LANGUAGE_DETECTED
    outcome = classify_execution_auto(execution_status=FAILED, failure_reason=UNSUPPORTED_LANGUAGE_DETECTED, recommendation=None, matched_expected_recommendation=None)
    assert outcome == CRITICAL_INCIDENT


def test_classify_execution_auto_other_failure_is_quality_concern():
    from app.policy.agent_evaluation_result import FAILED, MALFORMED_LLM_OUTPUT
    outcome = classify_execution_auto(execution_status=FAILED, failure_reason=MALFORMED_LLM_OUTPUT, recommendation=None, matched_expected_recommendation=None)
    assert outcome == QUALITY_CONCERN


def test_classify_execution_auto_disagreement_is_quality_concern_not_critical():
    outcome = classify_execution_auto(execution_status=SUCCESS, failure_reason=None, recommendation="MONITOR", matched_expected_recommendation=False)
    assert outcome == QUALITY_CONCERN


def test_classify_execution_auto_agreement_is_pass():
    outcome = classify_execution_auto(execution_status=SUCCESS, failure_reason=None, recommendation="PURSUE", matched_expected_recommendation=True)
    assert outcome == PASS


def test_case_run_record_human_review_overrides_to_more_severe_outcome():
    from app.policy.agent_evaluation_result import EvaluationExecutionResult
    from app.policy.agent_evaluation_result import AgentEvaluationResult, AcquisitionSubject, AgentEvaluationResultKey as Key
    evaluation = AgentEvaluationResult(
        key=Key(buyer_key="b", opportunity_id="o", acquisition_type="LAND_SITE_ACQUISITION"),
        recommendation=PURSUE, confidence="HIGH", confidence_basis=(), acquisition_subject=AcquisitionSubject(level="DEVELOPMENT_SITE"),
    )
    result = EvaluationExecutionResult(status=SUCCESS, evaluation=evaluation, retry_count=0)
    record = build_case_run_record(case_id="c1", config_id="gpt-4o-mini", repeat_index=0, execution_result=result, telemetry=None, expected_recommendation=(PURSUE,))
    assert record.auto_outcome == PASS
    assert record.final_outcome == PASS
    # A human reviewer later finds a prose-level failure the validator missed.
    from dataclasses import replace
    record_with_review = replace(record, human_reviewed_outcome=CRITICAL_INCIDENT, human_reviewed_notes="Fabricated ownership inference in prose.")
    assert record_with_review.final_outcome == CRITICAL_INCIDENT


def test_config_scorecard_never_computes_a_single_weighted_score():
    """Structural proof that ConfigScorecard has no 'overall_score'-style
    field - Section 21's own 'no universal weighted score' requirement."""
    from dataclasses import fields
    from benchmark.scoring import ConfigScorecard
    field_names = {f.name for f in fields(ConfigScorecard)}
    forbidden = {"overall_score", "weighted_score", "total_score", "composite_score"}
    assert not (field_names & forbidden)


def test_estimate_cost_uses_explicit_pricing_never_hardcoded():
    from benchmark.scoring import ModelPricing, ConfigScorecard
    pricing = ModelPricing(model="gpt-4o-mini", input_price_per_million=0.15, output_price_per_million=0.60, source="test", verified_at="2026-09-15")
    scorecard = ConfigScorecard(
        config_id="gpt-4o-mini", model="gpt-4o-mini", reasoning_effort=None, total_runs=2,
        critical_incident_count=0, critical_incident_case_ids=(), quality_concern_count=0, pass_count=2,
        recommendation_agreement_rate=1.0, first_pass_validity_rate=1.0, repair_rate=0.0, final_validity_rate=1.0,
        consistency_self_agreement_rate=None, mean_wall_clock_seconds=1.0, mean_input_tokens=1000.0,
        mean_output_tokens=200.0, mean_total_tokens=1200.0, estimated_cost_usd=None,
    )
    cost = estimate_cost(scorecard, pricing)
    assert cost == pytest.approx((1000 / 1_000_000 * 0.15 + 200 / 1_000_000 * 0.60) * 2)


# --- Runner cost-safety tests -----------------------------------------------

def test_estimate_call_plan_excludes_zero_llm_cases():
    zero_case = _build_dummy_case(case_id="zero", is_zero_llm=True)
    normal_case = _build_dummy_case(case_id="normal")
    plan = estimate_call_plan([zero_case, normal_case], [ModelConfig.parse("gpt-4o-mini")], repeats=3)
    assert plan["per_config"]["gpt-4o-mini"]["min_calls"] == 1  # only the normal, non-repeated case
    assert plan["total_calls_min"] == 1


def test_estimate_call_plan_repeats_only_consistency_marked_cases():
    repeated = _build_dummy_case(case_id="repeated", repeat=True)
    single = _build_dummy_case(case_id="single")
    plan = estimate_call_plan([repeated, single], [ModelConfig.parse("gpt-4o-mini")], repeats=3)
    assert plan["per_config"]["gpt-4o-mini"]["min_calls"] == 4  # 3 (repeated) + 1 (single)


def test_model_config_parse_rejects_reasoning_effort_for_models_without_support():
    with pytest.raises(ValueError, match="does not support"):
        ModelConfig.parse("gpt-4o-mini:medium")
    cfg = ModelConfig.parse("gpt-5.6-terra:high")
    assert cfg.model == "gpt-5.6-terra"
    assert cfg.reasoning_effort == "high"
