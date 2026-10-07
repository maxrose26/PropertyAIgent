"""Request-local provenance follows existing matcher decisions, not prose parsing."""
from dataclasses import asdict, replace

import pytest

from app.policy.buyer_matching import (
    B2MatchingContext, BuyerFitAssessment, BUYER_MATCHING_POLICY_VERSION,
    INSUFFICIENT_EVIDENCE, NOT_SUITABLE, POSSIBLE_FIT, STRONG_FIT,
    MatchingFacts, PLANNING_DELIVERY, assess_buyer_fit,
)
from app.policy.buyer_profiles import (
    AFFORDABLE_HOUSING_PACKAGE, DEVELOPMENT_STATE_UNSPECIFIED,
    HOUSING_ASSOCIATION, NESTEN_HOMES, UNCOMMENCED_PREFERRED,
)
from app.reporting.residential_count import CountAssessment


def facts(**changes):
    values = dict(opportunity_type=PLANNING_DELIVERY, unit_count=100,
                  development_type_raw="houses", is_specialist_development=False,
                  affordable_percentage=30.0, affordable_percentage_trusted=True,
                  affordable_unit_count=70, planning_state="permission_granted",
                  has_identified_planning_activity=True, has_phasing_evidence=False,
                  matched_to_site=True)
    values.update(changes)
    return MatchingFacts(**values)


def causes(result):
    return [entry for entry in result.explanation_trace
            if entry.role == "classification_affecting" and entry.contributed]


def test_historical_constructors_do_not_claim_coverage_or_change_serialization():
    result = BuyerFitAssessment(POSSIBLE_FIT, False, matches=["Retained reason"])
    assert getattr(result, "explanation_trace", None) is None
    assert getattr(result, "explanation_coverage", None) is None
    assert set(asdict(result)) == {"classification", "is_investigative_exception", "matches",
                                  "does_not_match", "unknown", "investigate"}


@pytest.mark.parametrize("units,classification,rule", [
    (100, STRONG_FIT, None), (205, POSSIBLE_FIT, "scale.discovery"),
    (300, INSUFFICIENT_EVIDENCE, "scale.outside"),
    (None, INSUFFICIENT_EVIDENCE, "scale.unknown"),
])
def test_scale_provenance_at_existing_precedence(units, classification, rule):
    result = assess_buyer_fit(NESTEN_HOMES, facts(unit_count=units))
    assert result.classification == classification
    assert result.explanation_coverage == "complete"
    assert [entry.rule_id for entry in causes(result)] == ([rule] if rule else [])
    originals = result.matches + result.does_not_match + result.unknown + result.investigate
    assert all(entry.reason in originals for entry in result.explanation_trace)
    assert [entry.reason for entry in result.explanation_trace if entry.role == "positive"] == result.matches
    assert all(type(values) is list for values in
               (result.matches, result.does_not_match, result.unknown, result.investigate))


def test_possible_cause_contains_preferred_and_discovery_bounds():
    result = assess_buyer_fit(NESTEN_HOMES, facts(unit_count=205))
    assert causes(result)[0].reason in result.matches
    assert "50-200" in causes(result)[0].reason
    assert "45-220" in causes(result)[0].reason


def test_contextual_unknown_is_not_a_cause_for_strong_or_possible():
    profile = replace(NESTEN_HOMES, acquisition_types=frozenset(),
                      development_state_appetite=UNCOMMENCED_PREFERRED)
    for units, expected in ((100, STRONG_FIT), (205, POSSIBLE_FIT)):
        result = assess_buyer_fit(profile, facts(unit_count=units), B2MatchingContext())
        assert result.classification == expected
        entry = next(entry for entry in result.explanation_trace
                     if entry.rule_id == "development.no_commencement")
        assert entry.role == "contextual"
        assert not entry.contributed
        assert all(cause.rule_id.startswith("scale.") for cause in causes(result))


def test_hard_exclusion_overrides_possible_and_blocking_unknown_trace():
    result = assess_buyer_fit(NESTEN_HOMES, facts(unit_count=205,
                             is_specialist_development=True, planning_state="other_or_unknown"))
    assert result.classification == NOT_SUITABLE
    assert [entry.rule_id for entry in causes(result)] == ["specialist.exclusion"]
    assert not next(entry for entry in result.explanation_trace
                    if entry.rule_id == "scale.discovery" and entry.role == "classification_affecting").contributed


def test_approximate_boundary_is_recorded_as_possible_not_exact():
    profile = replace(NESTEN_HOMES, target_unit_max=100)
    count = CountAssessment("site", "current scheme", precision="APPROXIMATE",
                            value=100, lower=100, upper=102, resolution="immaterial_variance")
    result = assess_buyer_fit(profile, facts(count_assessment=count))
    assert result.classification == POSSIBLE_FIT
    assert causes(result)[0].rule_id == "scale.uncertain_discovery"
    assert "~100" in causes(result)[0].reason
    assert "100" in causes(result)[0].reason and "110" in causes(result)[0].reason


def test_affordable_hard_minimum_keeps_own_metric_and_policy():
    result = assess_buyer_fit(HOUSING_ASSOCIATION, facts(affordable_unit_count=40))
    assert result.classification == NOT_SUITABLE
    assert causes(result)[0].rule_id == "scale.hard_minimum"
    assert "affordable homes" in causes(result)[0].reason
    assert BUYER_MATCHING_POLICY_VERSION == 8


def test_acquisition_unknown_provenance_respects_existing_or_gate():
    profile = replace(NESTEN_HOMES, acquisition_types=frozenset({AFFORDABLE_HOUSING_PACKAGE}),
                      development_state_appetite=DEVELOPMENT_STATE_UNSPECIFIED)
    result = assess_buyer_fit(profile, facts(affordable_unit_count=None,
                             affordable_percentage=None, affordable_percentage_trusted=False),
                             B2MatchingContext())
    assert result.classification == INSUFFICIENT_EVIDENCE
    assert [entry.rule_id for entry in causes(result)] == ["acquisition.blocking"]
    assert causes(result)[0].reason in result.unknown


def test_trace_is_request_local_and_excluded_from_asdict():
    first = assess_buyer_fit(NESTEN_HOMES, facts(unit_count=205))
    second = assess_buyer_fit(NESTEN_HOMES, facts(unit_count=100))
    assert first.explanation_trace is not second.explanation_trace
    assert len(asdict(first)) == 6
    assert not causes(second)
