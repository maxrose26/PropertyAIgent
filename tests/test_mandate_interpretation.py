"""Agent Evaluation Foundation - tests for app.policy.mandate_interpretation:
the Mandate Interpretation Policy V1 declarative classification of
BuyerMandatePolicy's own existing fields.

Core Product Owner correction under direct test: A TARGET IS NOT
AUTOMATICALLY A HARD BOUNDARY - specifically, 109 units against Nesten
Homes' 50-100 target must classify as TARGET (soft), never HARD_CONSTRAINT,
on both the minimum and maximum side. No BuyerMandatePolicy field is
touched by these tests - only its existing, unmodified fields are read.

Pure, DB-free - BuyerMandatePolicy is a plain dataclass."""
from __future__ import annotations

from dataclasses import replace

from app.policy.buyer_profiles import (
    HOUSING_ASSOCIATION,
    NATIONAL_HOUSEBUILDER,
    NESTEN_HOMES,
    STRATEGIC_LAND_BUYER,
)
from app.policy.mandate_interpretation import (
    EXCLUSION,
    HARD_CONSTRAINT,
    INVESTIGATION_CONDITION,
    PREFERENCE,
    TARGET,
    TOLERANCE,
    classify_mandate,
    classify_scale,
    resolve_acquisition_types,
)

ALL_PILOT_MANDATES = (NESTEN_HOMES, STRATEGIC_LAND_BUYER, NATIONAL_HOUSEBUILDER, HOUSING_ASSOCIATION)


# --- The core correction: target is soft on both sides for every current mandate ---

def test_scale_maximum_is_always_target_never_hard_constraint():
    for policy in ALL_PILOT_MANDATES:
        _minimum, maximum = classify_scale(policy)
        assert maximum.category == TARGET
        assert maximum.active is False


def test_nesten_109_units_is_not_a_hard_boundary_on_either_side():
    """The specific case the Product Owner corrected: 109 units vs
    Nesten's 50-100 target must not become a hard constraint."""
    minimum, maximum = classify_scale(NESTEN_HOMES)
    assert maximum.category == TARGET
    assert maximum.category != HARD_CONSTRAINT
    assert minimum.category == TARGET  # Nesten does not set below_minimum_scale_is_exclusion
    assert minimum.active is False


def test_housing_association_minimum_is_the_one_active_hard_constraint():
    """Housing Association is the one current mandate with below_minimum_
    scale_is_exclusion=True - its minimum genuinely is a HARD_CONSTRAINT,
    while its own maximum remains TARGET like every other mandate."""
    minimum, maximum = classify_scale(HOUSING_ASSOCIATION)
    assert minimum.category == HARD_CONSTRAINT
    assert minimum.active is True
    assert maximum.category == TARGET
    assert maximum.active is False


# --- Geography hard boundary remains intact ---------------------------------

def test_geography_hard_constraint_inactive_when_unspecified_or_all_coverage():
    for policy in ALL_PILOT_MANDATES:
        interpretation = classify_mandate(policy)
        assert interpretation.geography.category == HARD_CONSTRAINT
        # None of the four pilot mandates currently scope to specific councils.
        assert interpretation.geography.active is False


def test_geography_hard_constraint_becomes_active_for_a_councils_scoped_mandate():
    from app.policy.buyer_profiles import GEOGRAPHY_COUNCILS
    scoped = replace(NESTEN_HOMES, geography_scope=GEOGRAPHY_COUNCILS, geography_councils=frozenset({"manchester"}))
    interpretation = classify_mandate(scoped)
    assert interpretation.geography.category == HARD_CONSTRAINT
    assert interpretation.geography.active is True


# --- Specialist/wholly-affordable exclusions remain intact ------------------

def test_specialist_and_wholly_affordable_exclusions_are_active_for_every_current_housebuilder_mandate():
    for policy in (NESTEN_HOMES, STRATEGIC_LAND_BUYER, NATIONAL_HOUSEBUILDER, HOUSING_ASSOCIATION):
        interpretation = classify_mandate(policy)
        assert interpretation.specialist_development_exclusion.category == EXCLUSION
        assert interpretation.specialist_development_exclusion.active == policy.specialist_development_is_exclusion
        assert interpretation.wholly_affordable_exclusion.category == EXCLUSION
        assert interpretation.wholly_affordable_exclusion.active == policy.wholly_affordable_is_exclusion


# --- control_appetite is an INVESTIGATION_CONDITION, not an exclusion ------

def test_control_appetite_is_investigation_condition_not_exclusion():
    for policy in ALL_PILOT_MANDATES:
        interpretation = classify_mandate(policy)
        assert interpretation.control_appetite.category == INVESTIGATION_CONDITION


# --- accepted_planning_states and development_state_appetite are PREFERENCE, never exclusions ---

def test_accepted_planning_states_and_development_state_appetite_are_preferences():
    for policy in ALL_PILOT_MANDATES:
        interpretation = classify_mandate(policy)
        assert interpretation.accepted_planning_states.category == PREFERENCE
        assert interpretation.development_state_appetite.category == PREFERENCE


# --- large_allocation_is_self_qualifying is a TOLERANCE modifier ------------

def test_large_allocation_self_qualifying_is_tolerance():
    for policy in ALL_PILOT_MANDATES:
        interpretation = classify_mandate(policy)
        assert interpretation.large_allocation_self_qualifying.category == TOLERANCE


# --- acquisition_types is deliberately NOT one of the six categories -------

def test_acquisition_types_is_not_part_of_the_six_category_classification():
    interpretation = classify_mandate(NESTEN_HOMES)
    six_category_fields = {
        interpretation.scale_minimum.dimension, interpretation.scale_maximum.dimension,
        interpretation.accepted_planning_states.dimension, interpretation.specialist_development_exclusion.dimension,
        interpretation.wholly_affordable_exclusion.dimension, interpretation.treats_no_activity_as_positive.dimension,
        interpretation.large_allocation_self_qualifying.dimension, interpretation.geography.dimension,
        interpretation.development_state_appetite.dimension, interpretation.control_appetite.dimension,
    }
    assert "acquisition_types" not in six_category_fields
    # It is still readable, just via its own dedicated accessor.
    assert resolve_acquisition_types(NESTEN_HOMES) == NESTEN_HOMES.acquisition_types


def test_classify_mandate_policy_version_is_stamped():
    interpretation = classify_mandate(NESTEN_HOMES)
    assert interpretation.policy_version == 1
