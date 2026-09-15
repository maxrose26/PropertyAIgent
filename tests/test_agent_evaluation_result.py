"""Agent Evaluation Foundation - tests for app.policy.agent_evaluation_
result: the pure AgentEvaluationResult domain contract.

No LLM, no recommendation generation, no persistence - this file tests
only the CONTRACT'S OWN shape/validation, never a live evaluation (none
exists yet).

Core requirement under test: one result key can exist per (buyer mandate,
opportunity, acquisition_type) - a multi-acquisition-type mandate must be
representable WITHOUT blending two acquisition-type readings of the same
opportunity into one result."""
from __future__ import annotations

import pytest

from app.policy.agent_evaluation_result import (
    HIGH,
    LOW,
    MEDIUM,
    MONITOR,
    NOT_RELEVANT,
    PLANNING_STATUS_CHANGED,
    PURSUE,
    INVESTIGATE,
    WHOLE_ALLOCATION,
    AcquisitionSubject,
    AgentEvaluationResult,
    AgentEvaluationResultKey,
    MaterialSignal,
    MaterialUnknown,
)


def _make_result(**overrides) -> AgentEvaluationResult:
    defaults = dict(
        key=AgentEvaluationResultKey(buyer_key="nesten_homes", opportunity_id="strategic_land:allocation:1", acquisition_type="LAND_SITE_ACQUISITION"),
        recommendation=PURSUE,
        confidence=MEDIUM,
        confidence_basis=("Ownership unresolved but non-load-bearing for a control-stage strategy",),
        acquisition_subject=AcquisitionSubject(level=WHOLE_ALLOCATION, note="The allocation itself"),
        mandate_fingerprint="fp-mandate-1",
        opportunity_fingerprint="fp-opportunity-1",
        evaluation_policy_version="mandate_interpretation=1;acquisition_type_interpretation=1",
    )
    defaults.update(overrides)
    return AgentEvaluationResult(**defaults)


def test_valid_result_constructs_cleanly():
    result = _make_result()
    assert result.recommendation == PURSUE
    assert result.confidence == MEDIUM


def test_invalid_recommendation_rejected():
    with pytest.raises(ValueError):
        _make_result(recommendation="MAYBE")


def test_invalid_confidence_rejected():
    with pytest.raises(ValueError):
        _make_result(confidence="SUPER_HIGH")


def test_monitor_requires_a_monitoring_trigger():
    with pytest.raises(ValueError):
        _make_result(recommendation=MONITOR, monitoring_trigger=None)


def test_monitor_with_a_trigger_is_valid():
    result = _make_result(recommendation=MONITOR, monitoring_trigger=PLANNING_STATUS_CHANGED)
    assert result.monitoring_trigger == PLANNING_STATUS_CHANGED


def test_invalid_monitoring_trigger_rejected():
    with pytest.raises(ValueError):
        _make_result(recommendation=MONITOR, monitoring_trigger="Re-evaluate if planning_status_changed fires.")


def test_pursue_does_not_require_a_monitoring_trigger():
    result = _make_result(recommendation=PURSUE, monitoring_trigger=None)
    assert result.monitoring_trigger is None


def test_material_signals_and_unknowns_are_structured_not_free_text():
    result = _make_result(
        material_positive_signals=(MaterialSignal(label="Early-stage allocation", source_reference="progression_signal"),),
        material_negative_signals=(),
        material_unknowns=(MaterialUnknown(fact_or_question="Ownership/control not established", blocking=False, resolvable=True),),
    )
    assert result.material_positive_signals[0].source_reference == "progression_signal"
    assert result.material_unknowns[0].blocking is False
    assert result.material_unknowns[0].fact_or_question == "Ownership/control not established"


# --- One result key per (mandate, opportunity, acquisition_type) -----------

def test_one_result_key_per_mandate_opportunity_acquisition_type():
    key_a = AgentEvaluationResultKey(buyer_key="nesten_homes", opportunity_id="planning_delivery:site:526", acquisition_type="LAND_SITE_ACQUISITION")
    key_b = AgentEvaluationResultKey(buyer_key="nesten_homes", opportunity_id="planning_delivery:site:526", acquisition_type="DEVELOPMENT_HOMES_ACQUISITION")
    assert key_a != key_b
    # Hashable, so usable directly as a dict key without any extra wrapper.
    hash(key_a)
    hash(key_b)


def test_multi_acquisition_type_mandate_representable_without_blending():
    """The same buyer/opportunity can legitimately receive DIFFERENT
    recommendations under two different acquisition-type readings - both
    must coexist as independent, addressable results."""
    result_land = _make_result(
        key=AgentEvaluationResultKey(buyer_key="mixed_mandate_buyer", opportunity_id="planning_delivery:site:526", acquisition_type="LAND_SITE_ACQUISITION"),
        recommendation=INVESTIGATE, confidence=LOW,
        confidence_basis=("Land-acquisition read is ambiguous pending phasing evidence",),
        monitoring_trigger=None,
    )
    result_homes = _make_result(
        key=AgentEvaluationResultKey(buyer_key="mixed_mandate_buyer", opportunity_id="planning_delivery:site:526", acquisition_type="DEVELOPMENT_HOMES_ACQUISITION"),
        recommendation=PURSUE, confidence=HIGH,
        confidence_basis=("Construction underway is a strong positive signal for this acquisition type",),
    )
    results_by_key = {result_land.key: result_land, result_homes.key: result_homes}
    assert len(results_by_key) == 2
    assert results_by_key[result_land.key].recommendation == INVESTIGATE
    assert results_by_key[result_homes.key].recommendation == PURSUE


def test_not_relevant_result_shape():
    result = _make_result(
        key=AgentEvaluationResultKey(buyer_key="housing_association", opportunity_id="planning_delivery:recent_permission:460", acquisition_type="AFFORDABLE_HOUSING_PACKAGE"),
        recommendation=NOT_RELEVANT, confidence=HIGH,
        confidence_basis=("Confirmed zero affordable units - a genuine hard exclusion",),
        monitoring_trigger=None,
    )
    assert result.recommendation == NOT_RELEVANT
