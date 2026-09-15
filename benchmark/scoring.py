"""Agent Evaluation Benchmark V1 - critical-incident classification and the
scorecard data shapes (Implementation Gate, Modification #4 / Section 21).

NO UNIVERSAL WEIGHTED SCORE (Section 21, verbatim). This module never
computes a single number and never disqualifies a model configuration on
its own authority (Section 10: "FINAL MODEL DISQUALIFICATION IS A PRODUCT
OWNER DECISION. The benchmark must expose the evidence, not silently make
that commercial decision."). Its job is strictly to (a) classify each
individual output as PASS / QUALITY_CONCERN / CRITICAL_INCIDENT using only
what is MACHINE-OBSERVABLE (the validator's own failure_reason), (b) accept
a human reviewer's OWN classification for the prose-level failure modes no
JSON-shape check can see, and (c) aggregate per-configuration counts across
the dimensions the Design Audit's Section 10/21 both name - never blended
into one opaque figure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean

from app.policy.agent_evaluation_result import (
    FAILED,
    MALFORMED_LLM_OUTPUT,
    SUCCESS,
    UNSUPPORTED_LANGUAGE_DETECTED,
)

PASS = "PASS"
QUALITY_CONCERN = "QUALITY_CONCERN"
CRITICAL_INCIDENT = "CRITICAL_INCIDENT"

OUTCOME_VALUES = frozenset({PASS, QUALITY_CONCERN, CRITICAL_INCIDENT})

_SEVERITY_ORDER = {PASS: 0, QUALITY_CONCERN: 1, CRITICAL_INCIDENT: 2}

# Machine-observable critical incidents (Section 10's list, the subset a
# validator failure_reason can actually prove) - everything else in that
# list (fabricated ownership/control, material unsafe scope promotion,
# phase-to-whole-allocation promotion) is prose-level and can ONLY be set by
# a human reviewer via CaseRunRecord.human_reviewed_outcome.
MACHINE_DETECTABLE_CRITICAL_FAILURE_REASONS = frozenset({UNSUPPORTED_LANGUAGE_DETECTED})


@dataclass(frozen=True)
class CaseRunRecord:
    """One (case, model configuration, repeat) execution's full record -
    the atomic unit the Section Y report and Section 21 scorecard are both
    built from. Never itself computes a single quality number."""

    case_id: str
    config_id: str
    repeat_index: int  # 0 for a non-repeated case

    execution_status: str  # SUCCESS | FAILED, from EvaluationExecutionResult
    failure_reason: str | None
    first_pass_valid: bool  # retry_count == 0 on a SUCCESS/terminal FAILED-for-other-reasons result
    repair_required: bool  # retry_count > 0
    final_valid: bool  # execution_status == SUCCESS

    recommendation: str | None  # None when execution_status == FAILED
    acquisition_subject_level: str | None
    next_action: str | None
    matched_expected_recommendation: bool | None  # None when execution_status == FAILED

    # Auto-classification from machine-observable facts only.
    auto_outcome: str
    # Set by a human reviewer after reading the FULL output prose (Section
    # 11/20) - None until reviewed. When set, the case's FINAL outcome is
    # the more severe of auto_outcome and human_reviewed_outcome, never a
    # silent override in either direction.
    human_reviewed_outcome: str | None = None
    human_reviewed_notes: str = ""

    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None
    api_call_count: int = 0
    wall_clock_seconds: float = 0.0

    @property
    def final_outcome(self) -> str:
        if self.human_reviewed_outcome is None:
            return self.auto_outcome
        return max(self.auto_outcome, self.human_reviewed_outcome, key=lambda o: _SEVERITY_ORDER[o])


def classify_execution_auto(
    *, execution_status: str, failure_reason: str | None, recommendation: str | None,
    matched_expected_recommendation: bool | None,
) -> str:
    """The ONLY automatic classification this module performs - strictly
    from machine-observable facts. Never infers a critical incident from
    prose content (that is exactly what MACHINE_DETECTABLE_CRITICAL_FAILURE_
    REASONS existing as a narrow, named set is for - the validator already
    did the prose-level check for unsupported seller-intent/availability
    language; this function only reads its verdict)."""
    if execution_status == FAILED:
        if failure_reason in MACHINE_DETECTABLE_CRITICAL_FAILURE_REASONS:
            return CRITICAL_INCIDENT
        return QUALITY_CONCERN
    # SUCCESS: a recommendation outside the case's own acceptable set is a
    # disagreement worth surfacing in the Section Y appendix, but is NEVER
    # itself a critical incident (it may be the case's label that is wrong,
    # not the model - Section 12's own "does the disagreement reveal the
    # case's own label was wrong" review question exists for exactly this).
    if matched_expected_recommendation is False:
        return QUALITY_CONCERN
    return PASS


def build_case_run_record(
    *, case_id: str, config_id: str, repeat_index: int, execution_result, telemetry, expected_recommendation: tuple[str, ...],
) -> CaseRunRecord:
    """Builds one CaseRunRecord from a real (EvaluationExecutionResult,
    EvaluationExecutionTelemetry) pair - the runner's own per-call assembly
    step. Never called with a fabricated/hand-built result in production
    use; test doubles are fine (see tests/test_agent_evaluation_benchmark_
    harness.py) since this function only reads attributes, never calls
    anything itself."""
    recommendation = execution_result.evaluation.recommendation if execution_result.evaluation else None
    matched = (recommendation in expected_recommendation) if recommendation is not None else None
    auto_outcome = classify_execution_auto(
        execution_status=execution_result.status, failure_reason=execution_result.failure_reason,
        recommendation=recommendation, matched_expected_recommendation=matched,
    )
    return CaseRunRecord(
        case_id=case_id, config_id=config_id, repeat_index=repeat_index,
        execution_status=execution_result.status, failure_reason=execution_result.failure_reason,
        first_pass_valid=(execution_result.retry_count == 0), repair_required=(execution_result.retry_count > 0),
        final_valid=(execution_result.status == SUCCESS),
        recommendation=recommendation,
        acquisition_subject_level=(execution_result.evaluation.acquisition_subject.level if execution_result.evaluation else None),
        next_action=(execution_result.evaluation.next_action if execution_result.evaluation else None),
        matched_expected_recommendation=matched, auto_outcome=auto_outcome,
        input_tokens=telemetry.input_tokens if telemetry else None,
        output_tokens=telemetry.output_tokens if telemetry else None,
        reasoning_tokens=telemetry.reasoning_tokens if telemetry else None,
        total_tokens=telemetry.total_tokens if telemetry else None,
        api_call_count=telemetry.api_call_count if telemetry else 1,
        wall_clock_seconds=telemetry.wall_clock_seconds if telemetry else 0.0,
    )


@dataclass(frozen=True)
class ConfigScorecard:
    """Per-model-configuration aggregate across ALL its CaseRunRecords -
    separate dimensions (Section 21), never blended into one figure. The
    four qualitative dimensions (commercial_recommendation_quality,
    acquisition_subject_reasoning_quality, next_action_quality,
    monitoring_logic_quality) are deliberately left as Optional[float] and
    populated ONLY from human review scores (Section 12) - this module
    never invents a number for them from structural data alone."""

    config_id: str
    model: str
    reasoning_effort: str | None

    total_runs: int
    critical_incident_count: int
    critical_incident_case_ids: tuple[str, ...]
    quality_concern_count: int
    pass_count: int

    recommendation_agreement_rate: float | None  # fraction of non-FAILED runs matching their case's acceptable set
    first_pass_validity_rate: float
    repair_rate: float
    final_validity_rate: float

    consistency_self_agreement_rate: float | None  # among repeated cases only, None if none were repeated

    mean_wall_clock_seconds: float
    mean_input_tokens: float | None
    mean_output_tokens: float | None
    mean_total_tokens: float | None
    estimated_cost_usd: float | None  # benchmark/report-layer only - see estimate_cost()

    # Human-review-only dimensions (Section 12/21) - None until scored.
    commercial_recommendation_quality: float | None = None
    evidence_discipline_quality: float | None = None
    acquisition_subject_reasoning_quality: float | None = None
    material_unknown_recognition_quality: float | None = None
    next_action_quality: float | None = None
    monitoring_logic_quality: float | None = None


def build_config_scorecard(*, config_id: str, model: str, reasoning_effort: str | None, records: list[CaseRunRecord]) -> ConfigScorecard:
    """Pure aggregation over already-produced CaseRunRecords - never
    executes anything, never calls OpenAI, never disqualifies. `records`
    should be exactly the records for ONE configuration (the caller's
    responsibility to filter)."""
    total = len(records)
    critical = [r for r in records if r.final_outcome == CRITICAL_INCIDENT]
    concern = [r for r in records if r.final_outcome == QUALITY_CONCERN]
    passed = [r for r in records if r.final_outcome == PASS]

    matched = [r.matched_expected_recommendation for r in records if r.matched_expected_recommendation is not None]
    agreement_rate = (sum(1 for m in matched if m) / len(matched)) if matched else None

    first_pass_rate = (sum(1 for r in records if r.first_pass_valid) / total) if total else 0.0
    repair_rate = (sum(1 for r in records if r.repair_required) / total) if total else 0.0
    final_valid_rate = (sum(1 for r in records if r.final_valid) / total) if total else 0.0

    by_case: dict[str, list[CaseRunRecord]] = {}
    for r in records:
        by_case.setdefault(r.case_id, []).append(r)
    repeated_cases = {cid: rs for cid, rs in by_case.items() if len(rs) > 1}
    if repeated_cases:
        agreements = []
        for rs in repeated_cases.values():
            recs = [r.recommendation for r in rs if r.recommendation is not None]
            if recs:
                agreements.append(recs.count(max(set(recs), key=recs.count)) / len(recs))
        consistency = mean(agreements) if agreements else None
    else:
        consistency = None

    wall_clocks = [r.wall_clock_seconds for r in records]
    input_tok = [r.input_tokens for r in records if r.input_tokens is not None]
    output_tok = [r.output_tokens for r in records if r.output_tokens is not None]
    total_tok = [r.total_tokens for r in records if r.total_tokens is not None]

    return ConfigScorecard(
        config_id=config_id, model=model, reasoning_effort=reasoning_effort,
        total_runs=total, critical_incident_count=len(critical),
        critical_incident_case_ids=tuple(sorted({r.case_id for r in critical})),
        quality_concern_count=len(concern), pass_count=len(passed),
        recommendation_agreement_rate=agreement_rate,
        first_pass_validity_rate=first_pass_rate, repair_rate=repair_rate, final_validity_rate=final_valid_rate,
        consistency_self_agreement_rate=consistency,
        mean_wall_clock_seconds=mean(wall_clocks) if wall_clocks else 0.0,
        mean_input_tokens=mean(input_tok) if input_tok else None,
        mean_output_tokens=mean(output_tok) if output_tok else None,
        mean_total_tokens=mean(total_tok) if total_tok else None,
        estimated_cost_usd=None,  # filled in by estimate_cost() once a pricing table is supplied
    )


# --- Cost estimation (benchmark/report-layer ONLY - Section 15/16) ---------
#
# Deliberately NEVER inside app.policy.acquisition_evaluate or any other
# commercial-domain module. Pricing is an explicit, dated, externally-
# sourced assumption the caller must supply - this module never hardcodes a
# "current" price it could silently go stale.
@dataclass(frozen=True)
class ModelPricing:
    model: str
    input_price_per_million: float
    output_price_per_million: float
    source: str
    verified_at: str  # ISO-8601 date the price was confirmed against OpenAI's own docs


def estimate_cost(scorecard: ConfigScorecard, pricing: ModelPricing) -> float | None:
    if scorecard.mean_input_tokens is None or scorecard.mean_output_tokens is None:
        return None
    per_call = (
        scorecard.mean_input_tokens / 1_000_000 * pricing.input_price_per_million
        + scorecard.mean_output_tokens / 1_000_000 * pricing.output_price_per_million
    )
    return per_call * scorecard.total_runs
