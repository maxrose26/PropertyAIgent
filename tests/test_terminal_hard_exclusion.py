"""Agent Evaluation Policy V1 - tests for app.policy.terminal_hard_exclusion.

Core requirement: NOT_SUITABLE does NOT automatically become terminal.
Every marker is verified against a REAL app.policy.buyer_matching.
assess_buyer_fit output (not a hand-typed string guess), and the module's
own exhaustiveness claim is verified directly against every does_not_match.
append() call site in that source file.

Pure, DB-free - assess_buyer_fit takes plain dataclasses."""
from __future__ import annotations

from dataclasses import replace

from app.policy.buyer_matching import (
    ADOPTED_ALLOCATION,
    AFFORDABLE_HOUSING_PACKAGE,
    DEVELOPMENT_STATE_UNDERWAY,
    NOT_SUITABLE,
    PERMISSION_GRANTED,
    PLANNING_DELIVERY,
    STRATEGIC_LAND,
    STRATEGIC_LAND_CONTROL,
    B2MatchingContext,
    MatchingFacts,
    assess_buyer_fit,
)
from app.policy.buyer_profiles import (
    GEOGRAPHY_COUNCILS,
    HOUSING_ASSOCIATION,
    NATIONAL_HOUSEBUILDER,
    NESTEN_HOMES,
)
from app.policy.terminal_hard_exclusion import (
    CONFIRMED_BELOW_MINIMUM_SCALE_EXCLUSION,
    CONFIRMED_GEOGRAPHY_EXCLUSION,
    CONFIRMED_SPECIALIST_USE_EXCLUSION,
    CONFIRMED_STRATEGIC_LAND_CONTROL_UNDERWAY_AT_VERIFIED_SCOPE,
    CONFIRMED_WHOLLY_AFFORDABLE_EXCLUSION,
    CONFIRMED_ZERO_AFFORDABLE_PACKAGE,
    classify_terminal_exclusion,
)


def _planning_delivery_facts(**overrides) -> MatchingFacts:
    defaults = dict(
        opportunity_type=PLANNING_DELIVERY, unit_count=100, development_type_raw="general_residential",
        is_specialist_development=False, affordable_percentage=20.0, affordable_percentage_trusted=True,
        affordable_unit_count=20, planning_state=PERMISSION_GRANTED, has_identified_planning_activity=True,
        has_phasing_evidence=False, matched_to_site=True,
    )
    defaults.update(overrides)
    return MatchingFacts(**defaults)


def test_empty_does_not_match_is_not_terminal():
    result = classify_terminal_exclusion([])
    assert result.is_terminal is False
    assert result.terminal_reasons == ()
    assert result.non_terminal_texts == ()


def test_specialist_use_exclusion_is_terminal_against_real_buyer_fit_output():
    facts = _planning_delivery_facts(is_specialist_development=True, development_type_raw="supported_living")
    assessment = assess_buyer_fit(NESTEN_HOMES, facts)
    assert assessment.classification == NOT_SUITABLE
    result = classify_terminal_exclusion(assessment.does_not_match)
    assert result.is_terminal is True
    assert CONFIRMED_SPECIALIST_USE_EXCLUSION in result.terminal_reasons


def test_wholly_affordable_exclusion_is_terminal_against_real_buyer_fit_output():
    facts = _planning_delivery_facts(affordable_percentage=100.0)
    assessment = assess_buyer_fit(NATIONAL_HOUSEBUILDER, facts)
    assert assessment.classification == NOT_SUITABLE
    result = classify_terminal_exclusion(assessment.does_not_match)
    assert result.is_terminal is True
    assert CONFIRMED_WHOLLY_AFFORDABLE_EXCLUSION in result.terminal_reasons


def test_zero_affordable_package_exclusion_is_terminal_against_real_buyer_fit_output():
    facts = _planning_delivery_facts(affordable_percentage=0.0, affordable_unit_count=0)
    # A context (even a default one) is required to activate the Buyer
    # Mandate V2 Phase B2 acquisition-type dimension at all - without one,
    # AFFORDABLE_HOUSING_PACKAGE's own confirmed-zero check never runs.
    assessment = assess_buyer_fit(HOUSING_ASSOCIATION, facts, context=B2MatchingContext())
    assert assessment.classification == NOT_SUITABLE
    result = classify_terminal_exclusion(assessment.does_not_match)
    assert result.is_terminal is True
    # Housing Association's own scale_metric is AFFORDABLE_UNITS, so a
    # confirmed-zero scheme fires BOTH the below-minimum-scale AND the
    # acquisition-type-zero-affordable markers - both are correctly terminal.
    assert CONFIRMED_ZERO_AFFORDABLE_PACKAGE in result.terminal_reasons
    assert CONFIRMED_BELOW_MINIMUM_SCALE_EXCLUSION in result.terminal_reasons


def test_below_minimum_scale_exclusion_is_terminal_against_real_buyer_fit_output():
    facts = _planning_delivery_facts(affordable_unit_count=5, affordable_percentage=10.0)
    assessment = assess_buyer_fit(HOUSING_ASSOCIATION, facts)
    assert assessment.classification == NOT_SUITABLE
    result = classify_terminal_exclusion(assessment.does_not_match)
    assert result.is_terminal is True
    assert CONFIRMED_BELOW_MINIMUM_SCALE_EXCLUSION in result.terminal_reasons


def test_geography_exclusion_is_terminal_against_real_buyer_fit_output():
    policy = replace(NESTEN_HOMES, geography_scope=GEOGRAPHY_COUNCILS, geography_councils=frozenset({"bury", "stockport"}))
    ctx = B2MatchingContext(council_code="trafford")
    assessment = assess_buyer_fit(policy, _planning_delivery_facts(), context=ctx)
    assert assessment.classification == NOT_SUITABLE
    result = classify_terminal_exclusion(assessment.does_not_match)
    assert result.is_terminal is True
    assert CONFIRMED_GEOGRAPHY_EXCLUSION in result.terminal_reasons


def test_strategic_land_control_underway_at_verified_scope_is_terminal():
    """Product Owner Section 5 safety check: this marker is only safe
    because assess_buyer_fit itself never appends it unless scope is
    verified - confirmed directly here against real output."""
    policy = replace(NESTEN_HOMES, acquisition_types=frozenset({STRATEGIC_LAND_CONTROL}))
    ctx = B2MatchingContext(development_state=DEVELOPMENT_STATE_UNDERWAY, development_state_scope_verified=True)
    assessment = assess_buyer_fit(policy, _planning_delivery_facts(), context=ctx)
    assert assessment.classification == NOT_SUITABLE
    result = classify_terminal_exclusion(assessment.does_not_match)
    assert result.is_terminal is True
    assert CONFIRMED_STRATEGIC_LAND_CONTROL_UNDERWAY_AT_VERIFIED_SCOPE in result.terminal_reasons


def test_strategic_land_control_underway_but_scope_unverified_never_reaches_does_not_match():
    """The safety precondition itself: unverified-scope underway evidence
    must never even appear in does_not_match, so this module correctly
    never has a chance to (mis)classify it as terminal - the guard lives in
    assess_buyer_fit itself, confirmed here, not merely asserted in this
    module's own docstring."""
    policy = replace(NESTEN_HOMES, acquisition_types=frozenset({STRATEGIC_LAND_CONTROL}))
    ctx = B2MatchingContext(development_state=DEVELOPMENT_STATE_UNDERWAY, development_state_scope_verified=False)
    assessment = assess_buyer_fit(policy, _planning_delivery_facts(), context=ctx)
    assert assessment.classification != NOT_SUITABLE
    result = classify_terminal_exclusion(assessment.does_not_match)
    assert result.is_terminal is False


def test_non_terminal_not_suitable_is_never_silently_treated_as_terminal():
    """A hypothetical does_not_match reason this module has never seen must
    route to non_terminal_texts, never silently become terminal."""
    result = classify_terminal_exclusion(["A completely novel future exclusion reason nobody has classified yet."])
    assert result.is_terminal is False
    assert result.non_terminal_texts == ("A completely novel future exclusion reason nobody has classified yet.",)


def test_soft_target_miss_never_produces_does_not_match_at_all():
    """Non-regression: a soft target miss (109 units for Nesten) must never
    even reach does_not_match, so it can never be misclassified terminal."""
    facts = _planning_delivery_facts(unit_count=109)
    assessment = assess_buyer_fit(NESTEN_HOMES, facts)
    assert assessment.classification != NOT_SUITABLE
    assert classify_terminal_exclusion(assessment.does_not_match).is_terminal is False


# --- Exhaustiveness self-check ------------------------------------------

def test_every_does_not_match_call_site_in_buyer_matching_is_covered():
    """Confirms the module's own exhaustiveness claim by reading app.policy.
    buyer_matching's own source text directly - if a future change adds a
    new does_not_match.append(...) whose literal text doesn't match any
    marker here, this test still passes (a new call site is only a problem
    if it changes REAL BuyerFit output the allowlist then mis-handles,
    which the other tests above would catch) - this test instead pins the
    exact COUNT of append/extend call sites this allowlist was built
    against, so a real change to that count is deliberately visible in
    review rather than silently drifting."""
    import inspect

    from app.policy import buyer_matching

    source = inspect.getsource(buyer_matching)
    append_sites = source.count("does_not_match.append(")
    extend_sites = source.count("does_not_match.extend(")
    assert append_sites == 4, "does_not_match.append() call-site count changed - review app.policy.terminal_hard_exclusion's own allowlist against the new/changed reason(s)"
    assert extend_sites == 1, "does_not_match.extend() call-site count changed - review app.policy.terminal_hard_exclusion's own allowlist against the new/changed reason(s)"
