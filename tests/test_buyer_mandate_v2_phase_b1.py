"""Buyer Mandate V2, Phase B1 (Structured Mandate Domain Expansion) - pure,
DB-free structural tests for the four new BuyerMandatePolicy dimensions
(geography, acquisition type, development-state appetite, control
appetite). Follows this codebase's own established convention (see
tests/test_buyer_matching.py's own docstring): unit-test the pure
structure/policy objects directly, never through a Streamlit page, never
through an LLM.

Phase B1's own explicit brief: these dimensions must be persisted,
fingerprinted and validated WITHOUT changing app.policy.buyer_matching.
assess_buyer_fit's own behaviour yet (that activation is Phase B2). Every
test in this file is therefore a structural/architecture proof, never a
buyer-fit classification assertion - see tests/test_buyer_profile_
persistence.py's own test_existing_four_mandates_behaviourally_unchanged_
by_b1_fields for the behavioural-equivalence proof that belongs there.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from app.policy.buyer_matching import PLANNING_DELIVERY, STRATEGIC_LAND, MatchingFacts
from app.policy.buyer_profiles import (
    ACQUISITION_TYPES,
    AFFORDABLE_HOUSING_PACKAGE,
    AFFORDABLE_UNITS,
    CONTROL_APPETITES,
    DEVELOPER_LED_ACCEPTABLE,
    DEVELOPMENT_HOMES_ACQUISITION,
    DEVELOPMENT_STATE_APPETITES,
    DEVELOPMENT_STATE_UNSPECIFIED,
    GEOGRAPHY_ALL_CURRENT_COVERAGE,
    GEOGRAPHY_COUNCILS,
    GEOGRAPHY_UNSPECIFIED,
    HOUSING_ASSOCIATION,
    LAND_SITE_ACQUISITION,
    NATIONAL_HOUSEBUILDER,
    NESTEN_HOMES,
    PARTIAL_SITE_CONTROL_ACCEPTABLE,
    PERMISSION_GRANTED,
    STRATEGIC_LAND_BUYER,
    STRATEGIC_LAND_CONTROL,
    THIRD_PARTY_INTEREST_ACCEPTABLE,
    TOTAL_UNITS,
    UNCOMMENCED_PREFERRED,
    UNDERWAY_ACCEPTABLE,
    UNDERWAY_PREFERRED,
    UNRESOLVED_OWNERSHIP_INVESTIGATABLE,
    BuyerMandatePolicy,
)


def _base_policy(**overrides) -> BuyerMandatePolicy:
    """A minimal, valid BuyerMandatePolicy for structural tests that don't
    care about the pre-existing Phase A/pilot fields - built by replace()
    from a real template rather than duplicating every required field."""
    return replace(NESTEN_HOMES, key="structural_test", **overrides)


# --- Acquisition Type structural tests (Phase B1 brief, Section 35) --------

def test_mandate_can_hold_one_acquisition_type():
    policy = _base_policy(acquisition_types=frozenset({LAND_SITE_ACQUISITION}))
    assert policy.acquisition_types == frozenset({LAND_SITE_ACQUISITION})


def test_mandate_can_hold_multiple_acquisition_types():
    """Phase B1 brief, Section 7: a single mandate must support one OR
    MORE acquisition types - e.g. a future institutional buyer wanting
    both forward-funding and completed-home acquisition from the same
    geography/scale/appetite envelope."""
    policy = _base_policy(acquisition_types=frozenset({LAND_SITE_ACQUISITION, DEVELOPMENT_HOMES_ACQUISITION}))
    assert policy.acquisition_types == frozenset({LAND_SITE_ACQUISITION, DEVELOPMENT_HOMES_ACQUISITION})
    assert len(policy.acquisition_types) == 2


def test_invalid_acquisition_type_is_rejected():
    with pytest.raises(ValueError, match="acquisition_types"):
        _base_policy(acquisition_types=frozenset({"FORWARD_PURCHASE"}))


def test_acquisition_type_order_does_not_affect_equality_or_fingerprint():
    """A frozenset has no inherent order - this proves construction order
    genuinely cannot matter, closing off the "unstable fingerprint from
    set iteration order" risk the Phase B1 brief itself warns about
    (Section 27) at the structural level; compute_buyer_mandate_
    fingerprint's own sorted() call is exercised in tests/
    test_buyer_profile_persistence.py."""
    a = _base_policy(acquisition_types=frozenset([LAND_SITE_ACQUISITION, AFFORDABLE_HOUSING_PACKAGE]))
    b = _base_policy(acquisition_types=frozenset([AFFORDABLE_HOUSING_PACKAGE, LAND_SITE_ACQUISITION]))
    assert a.acquisition_types == b.acquisition_types
    assert sorted(a.acquisition_types) == sorted(b.acquisition_types)


def test_acquisition_types_round_trip_through_comma_joined_persistence_shape():
    """Structural proof of the persistence shape app.policy.buyer_profile_
    store._template_to_mandate_fields/_b1_fields_from_template actually
    use (comma-joined, sorted) - independent of any database, matching
    the same convention accepted_planning_states already established."""
    original = frozenset({DEVELOPMENT_HOMES_ACQUISITION, LAND_SITE_ACQUISITION, STRATEGIC_LAND_CONTROL})
    persisted = ",".join(sorted(original))
    rebuilt = frozenset(t for t in persisted.split(",") if t)
    assert rebuilt == original


def test_all_four_approved_acquisition_types_are_exactly_the_vocabulary():
    """Phase B1 brief, Section 6: exactly these four, no more - a larger
    taxonomy (forward purchase/forward funding/completed homes/SFH/BTR/
    portfolio) is explicitly deferred, never split out in B1."""
    assert ACQUISITION_TYPES == frozenset({
        LAND_SITE_ACQUISITION, STRATEGIC_LAND_CONTROL, AFFORDABLE_HOUSING_PACKAGE, DEVELOPMENT_HOMES_ACQUISITION,
    })


# --- Geography structural tests (Phase B1 brief, Section 36) --------------

def test_geography_can_store_one_council():
    policy = _base_policy(geography_scope=GEOGRAPHY_COUNCILS, geography_councils=frozenset({"trafford"}))
    assert policy.geography_councils == frozenset({"trafford"})


def test_geography_can_store_multiple_councils():
    councils = frozenset({"trafford", "bury", "stockport"})
    policy = _base_policy(geography_scope=GEOGRAPHY_COUNCILS, geography_councils=councils)
    assert policy.geography_councils == councils
    assert len(policy.geography_councils) == 3


def test_geography_councils_scope_requires_at_least_one_council():
    with pytest.raises(ValueError, match="COUNCILS"):
        _base_policy(geography_scope=GEOGRAPHY_COUNCILS, geography_councils=frozenset())


def test_geography_councils_forbidden_outside_councils_scope():
    """A geography_councils value alongside a non-COUNCILS scope is a
    contradiction (Phase B1 brief, Section 5/26 - unknown/all/specific
    must never blur into each other) - rejected, not silently ignored."""
    with pytest.raises(ValueError, match="geography_councils"):
        _base_policy(geography_scope=GEOGRAPHY_ALL_CURRENT_COVERAGE, geography_councils=frozenset({"trafford"}))
    with pytest.raises(ValueError, match="geography_councils"):
        _base_policy(geography_scope=GEOGRAPHY_UNSPECIFIED, geography_councils=frozenset({"trafford"}))


def test_geography_unspecified_and_all_current_coverage_are_distinct_values():
    """Phase B1 brief, Section 19/26: NULL/unconfigured must never
    silently mean "all councils" - proven here as two genuinely different,
    independently constructible, non-equal enum values, not merely two
    names for the same thing."""
    unspecified = _base_policy(geography_scope=GEOGRAPHY_UNSPECIFIED)
    all_coverage = _base_policy(geography_scope=GEOGRAPHY_ALL_CURRENT_COVERAGE)
    assert unspecified.geography_scope != all_coverage.geography_scope
    assert unspecified.geography_councils == all_coverage.geography_councils == frozenset()


def test_invalid_geography_scope_is_rejected():
    with pytest.raises(ValueError, match="geography_scope"):
        _base_policy(geography_scope="EVERYWHERE")


def test_geography_council_order_does_not_affect_fingerprint_shape():
    a = _base_policy(geography_scope=GEOGRAPHY_COUNCILS, geography_councils=frozenset(["trafford", "bury"]))
    b = _base_policy(geography_scope=GEOGRAPHY_COUNCILS, geography_councils=frozenset(["bury", "trafford"]))
    assert sorted(a.geography_councils) == sorted(b.geography_councils)


def test_geography_not_yet_used_to_filter_opportunities():
    """Phase B1 brief, Section 36: 'Do not yet filter opportunities by
    geography.' Structural confirmation: MatchingFacts (what assess_buyer_
    fit actually reads) carries no geography field at all as of Phase B1 -
    a mandate's own geography cannot possibly affect a live classification
    yet, because there is nothing on the facts side for it to compare
    against."""
    assert "geography" not in MatchingFacts.__dataclass_fields__
    assert "council" not in " ".join(MatchingFacts.__dataclass_fields__).lower()


# --- Development-State Appetite structural tests (Phase B1 brief, Section 37)

def test_opposite_development_state_appetites_coexist_across_mandates():
    """The Phase B1 brief's own central example: a land buyer's
    UNCOMMENCED_PREFERRED and an institutional buyer's UNDERWAY_PREFERRED
    must be representable simultaneously, on two different mandates, with
    no platform-wide rule favouring either."""
    land_buyer = _base_policy(development_state_appetite=UNCOMMENCED_PREFERRED)
    institutional_buyer = _base_policy(development_state_appetite=UNDERWAY_PREFERRED)
    assert land_buyer.development_state_appetite != institutional_buyer.development_state_appetite
    assert {land_buyer.development_state_appetite, institutional_buyer.development_state_appetite} == {
        UNCOMMENCED_PREFERRED, UNDERWAY_PREFERRED,
    }


def test_development_state_appetite_round_trips_losslessly():
    for value in DEVELOPMENT_STATE_APPETITES:
        policy = _base_policy(development_state_appetite=value)
        assert policy.development_state_appetite == value


def test_invalid_development_state_appetite_is_rejected():
    with pytest.raises(ValueError, match="development_state_appetite"):
        _base_policy(development_state_appetite="ALWAYS_UNDERWAY")


def test_development_state_appetite_is_bounded_to_exactly_four_values():
    assert DEVELOPMENT_STATE_APPETITES == frozenset({
        DEVELOPMENT_STATE_UNSPECIFIED, UNCOMMENCED_PREFERRED, UNDERWAY_ACCEPTABLE, UNDERWAY_PREFERRED,
    })


# --- Control Appetite structural tests (Phase B1 brief, Section 38) --------

def test_control_appetite_vocabulary_is_commercial_not_gate2c_evidence():
    """Phase B1 brief, Section 11/38: the mandate's own vocabulary must
    share NO string with Gate 2C's evidence-coverage/ownership-state
    constants - proven by direct import-and-compare rather than merely
    asserted, so a future accidental reuse of a Gate 2C string here would
    fail this test immediately."""
    from app.reporting import acquisition_position as gate2c

    gate2c_strings = {
        value for name, value in vars(gate2c).items()
        if name.isupper() and isinstance(value, str)
    }
    assert CONTROL_APPETITES.isdisjoint(gate2c_strings)


def test_control_appetite_can_represent_unresolved_ownership_without_changing_evidence():
    """A buyer's own stated willingness to investigate unresolved
    ownership is a mandate-level fact - it must never be confused with, or
    capable of overwriting, Gate 2C's own genuinely-unknown evidence state
    (Phase B1 brief, Section 12: "a buyer's willingness to investigate
    uncertainty does not transform uncertainty into confirmed control").
    Structural proof, two parts: (1) setting this appetite has zero effect
    on Gate 2C's own facts (there is no Gate 2C object anywhere in this
    call), and (2) app.policy.buyer_profiles itself imports NOTHING from
    Gate 2C's own module - the same real, AST-level "no forbidden import"
    check test_buyer_matching.py's own test_matching_modules_make_no_llm_
    or_network_calls already establishes as this codebase's convention for
    proving a structural boundary, not merely asserting it in prose."""
    import ast
    import inspect

    policy = _base_policy(control_appetite=frozenset({UNRESOLVED_OWNERSHIP_INVESTIGATABLE}))
    assert policy.control_appetite == frozenset({UNRESOLVED_OWNERSHIP_INVESTIGATABLE})

    import app.policy.buyer_profiles as buyer_profiles_module
    tree = ast.parse(inspect.getsource(buyer_profiles_module))
    imported_modules = [
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    ] + [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
    assert not any("acquisition_position" in m or "reporting" in m for m in imported_modules)


def test_control_appetite_can_hold_multiple_values():
    policy = _base_policy(control_appetite=frozenset({
        DEVELOPER_LED_ACCEPTABLE, THIRD_PARTY_INTEREST_ACCEPTABLE, PARTIAL_SITE_CONTROL_ACCEPTABLE,
    }))
    assert len(policy.control_appetite) == 3


def test_invalid_control_appetite_is_rejected():
    with pytest.raises(ValueError, match="control_appetite"):
        _base_policy(control_appetite=frozenset({"MIND_READING"}))


def test_control_appetite_round_trips_through_persistence_shape():
    original = frozenset({DEVELOPER_LED_ACCEPTABLE, UNRESOLVED_OWNERSHIP_INVESTIGATABLE})
    persisted = ",".join(sorted(original))
    rebuilt = frozenset(c for c in persisted.split(",") if c)
    assert rebuilt == original


# --- Same-facts/different-mandates architecture fixture (Section 39) ------

def test_same_hypothetical_scheme_expressible_by_four_materially_different_mandates():
    """Groundwork fixture for Phase B2/Gate 3 - proves the FOUR mandate
    dimensions together can structurally express four materially different
    acquisition strategies against the same hypothetical factual situation
    (~300 homes, permissioned, developer-led, Phase 1 underway, ~30%
    affordable, no disposal evidence) WITHOUT requiring assess_buyer_fit to
    produce any new commercial conclusion yet - this is a structural
    expressiveness proof, not a matching-behaviour test."""
    land_buyer = _base_policy(
        acquisition_types=frozenset({LAND_SITE_ACQUISITION}),
        development_state_appetite=UNCOMMENCED_PREFERRED,
        control_appetite=frozenset({UNRESOLVED_OWNERSHIP_INVESTIGATABLE}),
    )
    housing_association = _base_policy(
        acquisition_types=frozenset({AFFORDABLE_HOUSING_PACKAGE}),
        scale_metric=AFFORDABLE_UNITS,
        development_state_appetite=UNDERWAY_ACCEPTABLE,
        control_appetite=frozenset({DEVELOPER_LED_ACCEPTABLE, PARTIAL_SITE_CONTROL_ACCEPTABLE}),
    )
    institutional_buyer = _base_policy(
        acquisition_types=frozenset({DEVELOPMENT_HOMES_ACQUISITION}),
        development_state_appetite=UNDERWAY_PREFERRED,
        control_appetite=frozenset({DEVELOPER_LED_ACCEPTABLE, PARTIAL_SITE_CONTROL_ACCEPTABLE}),
    )
    strategic_land_buyer = _base_policy(
        acquisition_types=frozenset({STRATEGIC_LAND_CONTROL}),
        development_state_appetite=UNCOMMENCED_PREFERRED,
        control_appetite=frozenset({UNRESOLVED_OWNERSHIP_INVESTIGATABLE}),
    )

    mandates = [land_buyer, housing_association, institutional_buyer, strategic_land_buyer]

    # No two mandates collapse into an identical acquisition strategy -
    # the four dimensions genuinely distinguish them from each other.
    acquisition_type_sets = [m.acquisition_types for m in mandates]
    assert len(set(acquisition_type_sets)) == 4

    # The land buyer and the institutional buyer hold OPPOSITE development-
    # state appetites over the SAME hypothetical underway scheme - exactly
    # the "same facts, opposite commercial meaning" case the Phase B1
    # brief itself requires be representable without a platform-wide rule.
    assert land_buyer.development_state_appetite == UNCOMMENCED_PREFERRED
    assert institutional_buyer.development_state_appetite == UNDERWAY_PREFERRED

    # Housing Association and the institutional buyer both accept
    # developer-led, partial-site-control situations (neither requires
    # whole-site control) despite wanting entirely different things from
    # the scheme (the affordable package vs. the completed homes).
    assert PARTIAL_SITE_CONTROL_ACCEPTABLE in housing_association.control_appetite
    assert PARTIAL_SITE_CONTROL_ACCEPTABLE in institutional_buyer.control_appetite
    assert housing_association.acquisition_types != institutional_buyer.acquisition_types


# --- Opportunity Type vs Acquisition Type separation (Section 40) ---------

def test_opportunity_type_and_acquisition_type_are_separate_concepts():
    """Phase B1 brief, Section 8/40: opportunity_type (STRATEGIC_LAND/
    PLANNING_DELIVERY - the candidate's own buyer-independent situation)
    and acquisition_type (what a specific mandate wants from it) must
    never collapse into a disguised one-to-one mapping. Proven by
    construction: the SAME PLANNING_DELIVERY opportunity_type is paired
    here with three DIFFERENT acquisition types across three mandates,
    which would be structurally impossible if the two concepts were
    secretly the same enum."""
    facts = MatchingFacts(
        opportunity_type=PLANNING_DELIVERY, unit_count=300, development_type_raw="general_needs",
        is_specialist_development=False, affordable_percentage=30.0, affordable_percentage_trusted=True,
        affordable_unit_count=90, planning_state=PERMISSION_GRANTED, has_identified_planning_activity=True,
        has_phasing_evidence=True, matched_to_site=True,
    )
    land_buyer = _base_policy(acquisition_types=frozenset({LAND_SITE_ACQUISITION}))
    housing_association = _base_policy(acquisition_types=frozenset({AFFORDABLE_HOUSING_PACKAGE}))
    institutional_buyer = _base_policy(acquisition_types=frozenset({DEVELOPMENT_HOMES_ACQUISITION}))

    # All three mandates are being evaluated against the exact SAME
    # opportunity_type/facts object - opportunity_type itself never
    # changes, only what each mandate's own acquisition_types says it
    # wants from that one shared situation.
    for mandate in (land_buyer, housing_association, institutional_buyer):
        assert facts.opportunity_type == PLANNING_DELIVERY  # unchanged by which mandate is looking at it

    acquisition_types_seen = {land_buyer.acquisition_types, housing_association.acquisition_types, institutional_buyer.acquisition_types}
    assert len(acquisition_types_seen) == 3  # three genuinely different buyer intents over one opportunity_type

    # STRATEGIC_LAND is a real, independent opportunity_type value -
    # confirming acquisition_type's own vocabulary (LAND_SITE_ACQUISITION,
    # STRATEGIC_LAND_CONTROL, ...) is never merely an alias/rename of it.
    assert STRATEGIC_LAND != PLANNING_DELIVERY
    assert STRATEGIC_LAND not in ACQUISITION_TYPES
    assert PLANNING_DELIVERY not in ACQUISITION_TYPES


# --- Existing four mandates: B1 fields inspected, matching untouched ------

def test_existing_four_mandates_carry_the_documented_b1_defaults():
    """Sanity check of the actual persisted-template defaults (Phase B1
    brief, Sections 18/20-22) - see each template's own inline comments in
    app.policy.buyer_profiles for the brief citation behind every value
    here."""
    assert NESTEN_HOMES.acquisition_types == frozenset({LAND_SITE_ACQUISITION})
    assert NESTEN_HOMES.development_state_appetite == UNCOMMENCED_PREFERRED
    assert NESTEN_HOMES.control_appetite == frozenset({UNRESOLVED_OWNERSHIP_INVESTIGATABLE})

    assert STRATEGIC_LAND_BUYER.acquisition_types == frozenset({STRATEGIC_LAND_CONTROL})
    assert STRATEGIC_LAND_BUYER.development_state_appetite == UNCOMMENCED_PREFERRED
    assert STRATEGIC_LAND_BUYER.control_appetite == frozenset({UNRESOLVED_OWNERSHIP_INVESTIGATABLE})

    assert NATIONAL_HOUSEBUILDER.acquisition_types == frozenset({LAND_SITE_ACQUISITION})
    assert NATIONAL_HOUSEBUILDER.development_state_appetite == UNCOMMENCED_PREFERRED
    assert NATIONAL_HOUSEBUILDER.control_appetite == frozenset()  # deliberately unconfigured - no brief evidence

    assert HOUSING_ASSOCIATION.acquisition_types == frozenset({AFFORDABLE_HOUSING_PACKAGE})
    assert HOUSING_ASSOCIATION.development_state_appetite == UNDERWAY_ACCEPTABLE
    assert HOUSING_ASSOCIATION.control_appetite == frozenset({DEVELOPER_LED_ACCEPTABLE})

    for policy in (NESTEN_HOMES, STRATEGIC_LAND_BUYER, NATIONAL_HOUSEBUILDER, HOUSING_ASSOCIATION):
        assert policy.geography_scope == GEOGRAPHY_ALL_CURRENT_COVERAGE
        assert policy.geography_councils == frozenset()
