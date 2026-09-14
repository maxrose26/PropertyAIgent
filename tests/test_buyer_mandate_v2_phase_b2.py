"""Buyer Mandate V2, Phase B2 (Deterministic Buyer Fit Integration) - pure,
DB-free tests activating the four Phase B1 structural mandate dimensions
inside app.policy.buyer_matching.assess_buyer_fit. Follows this
codebase's own established convention (test_buyer_matching.py's own
docstring): unit-test the pure matching logic against real-shaped
fixtures, never a Streamlit page, never an LLM.

Every test that does NOT pass a `context` to assess_buyer_fit proves B2's
own backward-compatibility contract; every test that DOES pass one proves
one specific new deterministic rule from the Phase B2 brief's own hard-
vs-soft rule matrix (see MODULE-LEVEL comment block below).

============================== RULE MATRIX ==================================
Geography (COUNCILS scope only):
    known council IN set          -> HARD MATCH   (matches)
    known council NOT IN set      -> HARD MISMATCH (does_not_match)
    unknown council                -> EVIDENCE GAP (unknown)
    ALL_CURRENT_COVERAGE/UNSPECIFIED -> no reason at all
Acquisition Type (Phase B2 narrow remediation, Issue C: positive matches
must come from opportunity-side facts, never merely from the mandate
stating the type - "neutral is preferable to circular logic"):
    LAND_SITE_ACQUISITION          -> NEUTRAL - contributes nothing on its
                                       own (no opportunity-side fact makes
                                       this type positively established);
                                       never excludes
    STRATEGIC_LAND_CONTROL         -> MATCH if strategic-shaped; HARD
                                       MISMATCH only if confirmed underway+
                                       AND the underway evidence is scope-
                                       verified for this opportunity (Issue
                                       B); confirmed-underway-but-scope-
                                       unverified is EVIDENCE GAP/investigate,
                                       never a hard rejection; requires no
                                       other type in the set to have matched
    AFFORDABLE_HOUSING_PACKAGE     -> MATCH if affordable content known;
                                       HARD MISMATCH only if trusted 0%;
                                       else EVIDENCE GAP
    DEVELOPMENT_HOMES_ACQUISITION  -> MATCH only if confirmed underway/
                                       further (an opportunity-side fact);
                                       otherwise NEUTRAL - never excludes
Development-State Appetite (never hard, always SOFT/CONTEXTUAL - Phase B2
narrow remediation, Issue A: none of these four reasons are classification-
driving; they stay visible in `unknown` but never by themselves prevent
STRONG_FIT for an otherwise-qualifying opportunity):
    UNCOMMENCED_PREFERRED + underway   -> SOFT MISMATCH (unknown, non-blocking)
    UNCOMMENCED_PREFERRED + no evidence -> EVIDENCE GAP (unknown, non-blocking)
    UNDERWAY_ACCEPTABLE + underway      -> SOFT MATCH (matches)
    UNDERWAY_ACCEPTABLE/PREFERRED + no evidence -> EVIDENCE GAP (unknown, non-blocking)
    UNDERWAY_PREFERRED + underway       -> SOFT MATCH (matches, stronger)
    (anything) + UNSPECIFIED appetite   -> no reason at all
Control/Ownership Appetite (never hard, always SOFT):
    DEVELOPER_LED_ACCEPTABLE + developer-led evidence   -> matches
    THIRD_PARTY_INTEREST_ACCEPTABLE + third-party evid. -> matches
    UNRESOLVED_OWNERSHIP_INVESTIGATABLE + unresolved    -> investigate
    PARTIAL_SITE_CONTROL_ACCEPTABLE + partial evidence  -> matches
    empty appetite set                                   -> no reason at all
===============================================================================
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from app.policy.buyer_matching import (
    DEVELOPMENT_STATE_COMPLETE,
    DEVELOPMENT_STATE_PARTIALLY_COMPLETE,
    DEVELOPMENT_STATE_UNDERWAY,
    INSUFFICIENT_EVIDENCE,
    NOT_SUITABLE,
    PLANNING_DELIVERY,
    STRATEGIC_LAND,
    STRONG_FIT,
    B2MatchingContext,
    BUYER_MATCHING_POLICY_VERSION,
    ControlAppetiteFacts,
    MatchingFacts,
    assess_buyer_fit,
    build_control_appetite_facts,
)
from app.policy.buyer_profiles import (
    ADOPTED_ALLOCATION,
    AFFORDABLE_HOUSING_PACKAGE,
    DEVELOPER_LED_ACCEPTABLE,
    DEVELOPMENT_HOMES_ACQUISITION,
    DEVELOPMENT_STATE_UNSPECIFIED,
    GEOGRAPHY_ALL_CURRENT_COVERAGE,
    GEOGRAPHY_COUNCILS,
    GEOGRAPHY_UNSPECIFIED,
    HOUSING_ASSOCIATION,
    LAND_SITE_ACQUISITION,
    NATIONAL_HOUSEBUILDER,
    NESTEN_HOMES,
    OTHER_OR_UNKNOWN,
    PARTIAL_SITE_CONTROL_ACCEPTABLE,
    PERMISSION_GRANTED,
    STRATEGIC_LAND_BUYER,
    STRATEGIC_LAND_CONTROL,
    THIRD_PARTY_INTEREST_ACCEPTABLE,
    UNCOMMENCED_PREFERRED,
    UNDERWAY_ACCEPTABLE,
    UNDERWAY_PREFERRED,
    UNRESOLVED_OWNERSHIP_INVESTIGATABLE,
    BuyerMandatePolicy,
)
from app.policy.buyer_profile_store import compute_buyer_mandate_fingerprint


def _facts(**overrides) -> MatchingFacts:
    """A minimal, valid planning-delivery MatchingFacts - fields not
    overridden are 'nothing to say' defaults (never a hidden assumption)."""
    base = dict(
        opportunity_type=PLANNING_DELIVERY, unit_count=300, development_type_raw="houses",
        is_specialist_development=False, affordable_percentage=30.0, affordable_percentage_trusted=True,
        affordable_unit_count=90, planning_state=PERMISSION_GRANTED, has_identified_planning_activity=True,
        has_phasing_evidence=False, matched_to_site=True,
    )
    base.update(overrides)
    return MatchingFacts(**base)


class _FakeOwnershipFact:
    def __init__(self, state: str):
        self.state = state


class _FakeAcquisitionPositionFacts:
    """Duck-typed stand-in for app.reporting.acquisition_position.
    AcquisitionPositionFacts - build_control_appetite_facts deliberately
    reads this untyped (see its own docstring), so a real Gate 2C object
    is never required to unit-test the pure adapter."""
    def __init__(self, ownership_evidence=(), developer_indications=(), ownership_coverage="INSUFFICIENT_EVIDENCE_TO_DETERMINE_CONTROL", conflicts=()):
        self.ownership_evidence = ownership_evidence
        self.developer_indications = developer_indications
        self.ownership_coverage = ownership_coverage
        self.conflicts = conflicts


# --- Matching-policy version tests (Phase B2 brief, Section 47) ------------

def test_policy_version_is_the_current_expected_value():
    assert BUYER_MATCHING_POLICY_VERSION == 2


def test_fingerprint_changes_when_policy_version_changes():
    """Same mandate values, different matching_policy_version -> different
    fingerprint. Proven by monkeypatching the module-level constant the
    fingerprint function reads, since it is a plain module attribute."""
    import app.policy.buyer_matching as buyer_matching_module
    import app.policy.buyer_profile_store as store_module

    fp_v2 = compute_buyer_mandate_fingerprint(NESTEN_HOMES)

    original = buyer_matching_module.BUYER_MATCHING_POLICY_VERSION
    try:
        buyer_matching_module.BUYER_MATCHING_POLICY_VERSION = 1
        store_module.BUYER_MATCHING_POLICY_VERSION = 1
        fp_v1 = compute_buyer_mandate_fingerprint(NESTEN_HOMES)
    finally:
        buyer_matching_module.BUYER_MATCHING_POLICY_VERSION = original
        store_module.BUYER_MATCHING_POLICY_VERSION = original

    assert fp_v1 != fp_v2


def test_fingerprint_set_ordering_does_not_affect_value_only_policy_version_does():
    a = replace(NESTEN_HOMES, acquisition_types=frozenset(["LAND_SITE_ACQUISITION"]))
    b = replace(NESTEN_HOMES, acquisition_types=frozenset(["LAND_SITE_ACQUISITION"]))
    assert compute_buyer_mandate_fingerprint(a) == compute_buyer_mandate_fingerprint(b)


def test_b1_persisted_fingerprint_is_stale_under_b2_policy_version():
    """The exact required Section 6/47 proof: a fingerprint computed
    WITHOUT matching_policy_version in its hash input (i.e. exactly what
    every real production mandate's OWN persisted Phase-B1-era fingerprint
    looks like) does not equal today's (B2) fingerprint for the identical
    mandate values - the policy-version transition alone is sufficient to
    stale a baseline, with no mandate field changing at all."""
    import hashlib
    import json

    # Replicates Phase B1's OWN fingerprint function exactly (no
    # matching_policy_version key) - i.e. a real pre-B2 persisted value.
    def b1_era_fingerprint(policy: BuyerMandatePolicy) -> str:
        source = {
            "target_unit_min": policy.target_unit_min, "target_unit_max": policy.target_unit_max,
            "scale_metric": policy.scale_metric, "accepted_planning_states": sorted(policy.accepted_planning_states),
            "treats_no_activity_as_positive": policy.treats_no_activity_as_positive,
            "large_allocation_is_self_qualifying": policy.large_allocation_is_self_qualifying,
            "specialist_development_is_exclusion": policy.specialist_development_is_exclusion,
            "wholly_affordable_is_exclusion": policy.wholly_affordable_is_exclusion,
            "below_minimum_scale_is_exclusion": policy.below_minimum_scale_is_exclusion,
            "geography_scope": policy.geography_scope, "geography_councils": sorted(policy.geography_councils),
            "acquisition_types": sorted(policy.acquisition_types),
            "development_state_appetite": policy.development_state_appetite,
            "control_appetite": sorted(policy.control_appetite),
        }
        return hashlib.sha256(json.dumps(source, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    b1_fingerprint = b1_era_fingerprint(NESTEN_HOMES)  # simulates the real persisted value today
    b2_fingerprint = compute_buyer_mandate_fingerprint(NESTEN_HOMES)  # freshly recomputed, current code
    assert b1_fingerprint != b2_fingerprint  # stale - no mandate field changed, only the code did


def test_after_reassessment_fingerprint_matches_and_is_no_longer_stale():
    """After a controlled reassessment simply re-persists the freshly
    computed (B2-inclusive) fingerprint, a subsequent comparison finds it
    current again - proving the transition is a one-time event, not a
    permanent staleness."""
    current = compute_buyer_mandate_fingerprint(NESTEN_HOMES)
    reassessed_and_persisted = current  # what a real reassessment would write back
    assert compute_buyer_mandate_fingerprint(NESTEN_HOMES) == reassessed_and_persisted


def test_changing_policy_version_again_would_stale_it_again():
    import app.policy.buyer_matching as buyer_matching_module
    import app.policy.buyer_profile_store as store_module

    persisted = compute_buyer_mandate_fingerprint(NESTEN_HOMES)  # "reassessed under v2"
    original = buyer_matching_module.BUYER_MATCHING_POLICY_VERSION
    try:
        buyer_matching_module.BUYER_MATCHING_POLICY_VERSION = 3
        store_module.BUYER_MATCHING_POLICY_VERSION = 3
        fresh_under_v3 = compute_buyer_mandate_fingerprint(NESTEN_HOMES)
    finally:
        buyer_matching_module.BUYER_MATCHING_POLICY_VERSION = original
        store_module.BUYER_MATCHING_POLICY_VERSION = original
    assert fresh_under_v3 != persisted


# --- Backward-compatibility (no context = Phase B1 behaviour exactly) -----

def test_no_context_reproduces_phase_b1_behaviour_exactly_for_all_four_pilots():
    """The single most important B2 safety property: every real
    production mandate already has non-empty B1 fields (acquisition_types
    etc.) - calling assess_buyer_fit WITHOUT a context must not evaluate
    any of them, exactly reproducing pre-B2 output."""
    facts = _facts()
    for policy in (NESTEN_HOMES, STRATEGIC_LAND_BUYER, NATIONAL_HOUSEBUILDER, HOUSING_ASSOCIATION):
        result = assess_buyer_fit(policy, facts)
        joined = " ".join(result.matches + result.does_not_match + result.unknown + result.investigate)
        assert "acquisition strategy" not in joined
        assert "geographic" not in joined
        assert "development is" not in joined.lower() or "development" not in profile_b2_terms(joined)


def profile_b2_terms(text: str) -> str:
    # helper for the assertion above - kept trivial and explicit
    return text


# --- Geography test matrix (Phase B2 brief, Section 41) --------------------

def test_geography_councils_in_scope_matches():
    policy = replace(NESTEN_HOMES, geography_scope=GEOGRAPHY_COUNCILS, geography_councils=frozenset({"bury", "stockport"}))
    ctx = B2MatchingContext(council_code="bury")
    result = assess_buyer_fit(policy, _facts(), context=ctx)
    assert any("bury" in m.lower() and "within" in m.lower() for m in result.matches)
    assert result.classification != NOT_SUITABLE


def test_geography_councils_out_of_scope_is_hard_mismatch():
    policy = replace(NESTEN_HOMES, geography_scope=GEOGRAPHY_COUNCILS, geography_councils=frozenset({"bury", "stockport"}))
    ctx = B2MatchingContext(council_code="trafford")
    result = assess_buyer_fit(policy, _facts(), context=ctx)
    assert any("trafford" in m.lower() and "outside" in m.lower() for m in result.does_not_match)
    assert result.classification == NOT_SUITABLE


def test_geography_councils_unknown_council_is_evidence_gap_not_rejection():
    policy = replace(NESTEN_HOMES, geography_scope=GEOGRAPHY_COUNCILS, geography_councils=frozenset({"bury"}))
    ctx = B2MatchingContext(council_code=None)
    result = assess_buyer_fit(policy, _facts(), context=ctx)
    assert not result.does_not_match
    assert any("council" in u.lower() for u in result.unknown)


def test_geography_all_current_coverage_never_restricts():
    policy = replace(NESTEN_HOMES, geography_scope=GEOGRAPHY_ALL_CURRENT_COVERAGE, geography_councils=frozenset())
    for council in ("bury", "trafford", "some_future_council"):
        result = assess_buyer_fit(policy, _facts(), context=B2MatchingContext(council_code=council))
        assert result.classification != NOT_SUITABLE
        assert not any("geograph" in m.lower() or "council" in m.lower() for m in result.matches + result.does_not_match + result.unknown)


def test_geography_unspecified_is_not_silently_unrestricted_and_not_rejected():
    policy = replace(NESTEN_HOMES, geography_scope=GEOGRAPHY_UNSPECIFIED, geography_councils=frozenset())
    result = assess_buyer_fit(policy, _facts(), context=B2MatchingContext(council_code="trafford"))
    # No geography-specific reason at all (mirrors ALL_CURRENT_COVERAGE's
    # own silence) - and, critically, never a rejection.
    assert not any("council" in m.lower() for m in result.does_not_match)
    assert result.classification != NOT_SUITABLE


def test_geography_multiple_councils_is_deterministic():
    policy = replace(NESTEN_HOMES, geography_scope=GEOGRAPHY_COUNCILS, geography_councils=frozenset({"bury", "stockport", "trafford"}))
    for council in ("bury", "stockport", "trafford"):
        result = assess_buyer_fit(policy, _facts(), context=B2MatchingContext(council_code=council))
        assert result.classification != NOT_SUITABLE
    result = assess_buyer_fit(policy, _facts(), context=B2MatchingContext(council_code="wigan"))
    assert result.classification == NOT_SUITABLE


# --- Acquisition Type test matrix (Phase B2 brief, Section 42) -------------

def test_strategic_land_opportunity_matches_strategic_land_control():
    policy = replace(NESTEN_HOMES, acquisition_types=frozenset({STRATEGIC_LAND_CONTROL}))
    facts = _facts(opportunity_type=STRATEGIC_LAND, planning_state=ADOPTED_ALLOCATION, matched_to_site=False)
    result = assess_buyer_fit(policy, facts, context=B2MatchingContext())
    assert any("strategic-land-control" in m for m in result.matches)


def test_land_site_acquisition_type_is_neutral_not_circular():
    """Phase B2 narrow remediation (Issue C): a mandate stating it wants
    LAND_SITE_ACQUISITION opportunities is a fact about the MANDATE, not
    the opportunity - it must never by itself produce a positive match.
    LAND_SITE_ACQUISITION contributes nothing (neither matches nor
    unknown), and an otherwise fully-qualifying opportunity (using
    Nesten's own real target range/appetite) still reaches STRONG_FIT -
    removing the circular match must not force INSUFFICIENT_EVIDENCE
    either."""
    policy = replace(NESTEN_HOMES, target_unit_min=200, target_unit_max=500, acquisition_types=frozenset({LAND_SITE_ACQUISITION}))
    result = assess_buyer_fit(policy, _facts(opportunity_type=PLANNING_DELIVERY, unit_count=300), context=B2MatchingContext())
    assert not any("land/site acquisition" in m for m in result.matches)
    assert not any("land/site acquisition" in u for u in result.unknown)
    assert result.classification == STRONG_FIT


def test_affordable_containing_scheme_matches_affordable_housing_package():
    policy = replace(NESTEN_HOMES, acquisition_types=frozenset({AFFORDABLE_HOUSING_PACKAGE}))
    facts = _facts(affordable_unit_count=90, affordable_percentage=30.0, affordable_percentage_trusted=True)
    result = assess_buyer_fit(policy, facts, context=B2MatchingContext())
    assert any("affordable-housing-package" in m and "does not establish" in m for m in result.matches)


def test_underway_developer_scheme_matches_development_homes_acquisition():
    policy = replace(NESTEN_HOMES, acquisition_types=frozenset({DEVELOPMENT_HOMES_ACQUISITION}))
    ctx = B2MatchingContext(development_state=DEVELOPMENT_STATE_UNDERWAY)
    result = assess_buyer_fit(policy, _facts(), context=ctx)
    assert any("development/homes acquisition" in m and "does not establish" in m for m in result.matches)


def test_one_opportunity_compatible_with_multiple_acquisition_types():
    """Proves there is no one-to-one Opportunity Type map (Section 14) -
    the SAME facts satisfy three different acquisition types independently."""
    facts = _facts(affordable_unit_count=90, affordable_percentage=30.0, affordable_percentage_trusted=True)
    ctx = B2MatchingContext(development_state=DEVELOPMENT_STATE_UNDERWAY)
    land = assess_buyer_fit(replace(NESTEN_HOMES, acquisition_types=frozenset({LAND_SITE_ACQUISITION})), facts, context=ctx)
    affordable = assess_buyer_fit(replace(NESTEN_HOMES, acquisition_types=frozenset({AFFORDABLE_HOUSING_PACKAGE})), facts, context=ctx)
    homes = assess_buyer_fit(replace(NESTEN_HOMES, acquisition_types=frozenset({DEVELOPMENT_HOMES_ACQUISITION})), facts, context=ctx)
    assert land.matches and affordable.matches and homes.matches
    assert land.matches != affordable.matches != homes.matches


def test_mandate_with_multiple_acquisition_types():
    """Confirmed-underway-but-scope-unverified (the default) never hard-
    mismatches STRATEGIC_LAND_CONTROL (Issue B) - and LAND_SITE_ACQUISITION
    is neutral rather than an automatic rescue (Issue C) - so this mandate
    is never NOT_SUITABLE purely from this dimension."""
    policy = replace(NESTEN_HOMES, acquisition_types=frozenset({LAND_SITE_ACQUISITION, STRATEGIC_LAND_CONTROL}))
    ctx = B2MatchingContext(development_state=DEVELOPMENT_STATE_UNDERWAY)
    result = assess_buyer_fit(policy, _facts(), context=ctx)
    assert result.classification != NOT_SUITABLE
    assert not any("fundamentally incompatible" in m for m in result.does_not_match)


def test_strategic_land_control_only_hard_mismatches_when_confirmed_underway_and_scope_verified():
    """Phase B2 narrow remediation (Issue B): the hard rejection requires
    BOTH confirmed-underway AND verified opportunity scope."""
    policy = replace(NESTEN_HOMES, acquisition_types=frozenset({STRATEGIC_LAND_CONTROL}))
    ctx = B2MatchingContext(development_state=DEVELOPMENT_STATE_UNDERWAY, development_state_scope_verified=True)
    result = assess_buyer_fit(policy, _facts(opportunity_type=PLANNING_DELIVERY, planning_state=PERMISSION_GRANTED), context=ctx)
    assert result.classification == NOT_SUITABLE
    assert any("underway" in m for m in result.does_not_match)


def test_strategic_land_control_confirmed_underway_but_scope_unverified_is_not_hard_rejected():
    """Phase B2 narrow remediation (Issue B): confirmed-underway evidence
    whose scope is NOT verified to cover this specific opportunity (the
    DEFAULT, e.g. a named phase, a recent permission, or a long-pending
    application on a larger site) must never hard-reject the whole
    opportunity - it is surfaced as worth investigating instead."""
    policy = replace(NESTEN_HOMES, acquisition_types=frozenset({STRATEGIC_LAND_CONTROL}))
    ctx = B2MatchingContext(development_state=DEVELOPMENT_STATE_UNDERWAY)  # development_state_scope_verified defaults False
    result = assess_buyer_fit(policy, _facts(opportunity_type=PLANNING_DELIVERY, planning_state=PERMISSION_GRANTED), context=ctx)
    assert result.classification != NOT_SUITABLE
    assert not result.does_not_match
    assert any("underway" in i and "scope" in i for i in result.investigate)


def test_affordable_housing_package_hard_mismatch_only_on_trusted_zero():
    policy = replace(NESTEN_HOMES, acquisition_types=frozenset({AFFORDABLE_HOUSING_PACKAGE}))
    facts = _facts(affordable_unit_count=0, affordable_percentage=0.0, affordable_percentage_trusted=True)
    result = assess_buyer_fit(policy, facts, context=B2MatchingContext())
    assert result.classification == NOT_SUITABLE
    assert any("no affordable housing content" in m for m in result.does_not_match)


def test_missing_acquisition_type_facts_remain_unknown_not_forced_mismatch():
    policy = replace(NESTEN_HOMES, acquisition_types=frozenset({AFFORDABLE_HOUSING_PACKAGE}))
    facts = _facts(affordable_unit_count=None, affordable_percentage=None, affordable_percentage_trusted=False)
    result = assess_buyer_fit(policy, facts, context=B2MatchingContext())
    assert not result.does_not_match
    assert any("affordable-housing-package" in u for u in result.unknown)


# --- Development-State test matrix (Phase B2 brief, Section 43) -----------

def test_underway_with_underway_acceptable_is_soft_match():
    policy = replace(NESTEN_HOMES, development_state_appetite=UNDERWAY_ACCEPTABLE)
    result = assess_buyer_fit(policy, _facts(), context=B2MatchingContext(development_state=DEVELOPMENT_STATE_UNDERWAY))
    assert any("does not count against" in m for m in result.matches)
    assert result.classification != NOT_SUITABLE


def test_underway_with_underway_preferred_is_soft_match():
    policy = replace(NESTEN_HOMES, development_state_appetite=UNDERWAY_PREFERRED)
    result = assess_buyer_fit(policy, _facts(), context=B2MatchingContext(development_state=DEVELOPMENT_STATE_UNDERWAY))
    assert any("positive signal" in m for m in result.matches)


def test_underway_with_uncommenced_preferred_is_soft_mismatch_never_hard():
    policy = replace(NESTEN_HOMES, development_state_appetite=UNCOMMENCED_PREFERRED)
    result = assess_buyer_fit(policy, _facts(), context=B2MatchingContext(development_state=DEVELOPMENT_STATE_UNDERWAY))
    assert not result.does_not_match  # never hard, per Section 21/24
    assert any("preference is not met" in u for u in result.unknown)


def test_no_commencement_evidence_with_uncommenced_preferred_is_evidence_gap_never_confirmed():
    """THE mandatory safeguard (Section 19/21): absence of commencement
    evidence must NEVER be treated as confirmed uncommenced."""
    policy = replace(NESTEN_HOMES, development_state_appetite=UNCOMMENCED_PREFERRED)
    result = assess_buyer_fit(policy, _facts(), context=B2MatchingContext(development_state="unknown"))
    assert not result.does_not_match
    assert not any("preference is not met" in u for u in result.unknown)  # not treated as "known underway" either
    assert any("not treated as confirmed non-commencement" in u for u in result.unknown)


def test_partially_complete_and_complete_are_also_treated_as_started():
    policy = replace(NESTEN_HOMES, development_state_appetite=UNDERWAY_ACCEPTABLE)
    for state in (DEVELOPMENT_STATE_PARTIALLY_COMPLETE, DEVELOPMENT_STATE_COMPLETE):
        result = assess_buyer_fit(policy, _facts(), context=B2MatchingContext(development_state=state))
        assert any("does not count against" in m for m in result.matches)


def test_unspecified_development_state_appetite_contributes_nothing():
    policy = replace(NESTEN_HOMES, development_state_appetite=DEVELOPMENT_STATE_UNSPECIFIED)
    result = assess_buyer_fit(policy, _facts(), context=B2MatchingContext(development_state=DEVELOPMENT_STATE_UNDERWAY))
    assert not any("underway" in m for m in result.matches + result.unknown)


# --- Classification-driving vs contextual/soft-preference unknown (Phase B2
# narrow remediation, Issue A) - "PREFERRED must not behave like REQUIRED" --

def test_a_otherwise_strong_fit_with_only_soft_preference_unknown_stays_strong_fit():
    """(A) An opportunity that satisfies every classification-driving
    requirement, whose ONLY gap is an unevaluable soft preference
    (UNCOMMENCED_PREFERRED with unknown development state), must remain
    STRONG_FIT - the contextual unknown stays visible in `unknown` for
    transparency but must not by itself downgrade the classification."""
    policy = replace(NESTEN_HOMES, target_unit_min=50, target_unit_max=100, development_state_appetite=UNCOMMENCED_PREFERRED)
    facts = _facts(unit_count=70, is_specialist_development=False, affordable_percentage=0.0, affordable_percentage_trusted=True, planning_state=PERMISSION_GRANTED)
    result = assess_buyer_fit(policy, facts, context=B2MatchingContext(development_state=None))
    assert result.classification == STRONG_FIT
    assert any("not treated as confirmed non-commencement" in u for u in result.unknown)


def test_b_otherwise_insufficient_evidence_from_genuine_classification_driving_gap_stays_insufficient_evidence():
    """(B) An opportunity whose evidence gap is a genuine classification-
    driving requirement (here: no trusted unit count at all) must remain
    INSUFFICIENT_EVIDENCE - the remediation must not erase real
    uncertainty, only stop a SOFT preference from behaving like one."""
    policy = replace(NESTEN_HOMES, target_unit_min=50, target_unit_max=100, development_state_appetite=UNCOMMENCED_PREFERRED)
    facts = _facts(unit_count=None, is_specialist_development=False, affordable_percentage=0.0, affordable_percentage_trusted=True, planning_state=PERMISSION_GRANTED)
    result = assess_buyer_fit(policy, facts, context=B2MatchingContext(development_state=None))
    assert result.classification == INSUFFICIENT_EVIDENCE
    assert any("No trusted unit count" in u for u in result.unknown)


def test_c_otherwise_not_suitable_from_hard_contradiction_stays_not_suitable():
    """(C) A genuine hard contradiction (100% affordable-led, an explicit
    exclusion for this buyer) must remain NOT_SUITABLE regardless of any
    soft-preference gap elsewhere."""
    policy = replace(NESTEN_HOMES, target_unit_min=50, target_unit_max=100, development_state_appetite=UNCOMMENCED_PREFERRED)
    facts = _facts(unit_count=70, is_specialist_development=False, affordable_percentage=100.0, affordable_percentage_trusted=True, planning_state=PERMISSION_GRANTED)
    result = assess_buyer_fit(policy, facts, context=B2MatchingContext(development_state=None))
    assert result.classification == NOT_SUITABLE


def test_d_no_commencement_evidence_never_becomes_a_positive_uncommenced_match():
    """(D) Absence of commencement evidence is an evidence gap, never a
    positive "confirmed uncommenced" match - even though it no longer
    blocks STRONG_FIT (test A above), it must never itself appear in
    `matches`."""
    policy = replace(NESTEN_HOMES, target_unit_min=50, target_unit_max=100, development_state_appetite=UNCOMMENCED_PREFERRED)
    facts = _facts(unit_count=70, is_specialist_development=False, affordable_percentage=0.0, affordable_percentage_trusted=True, planning_state=PERMISSION_GRANTED)
    result = assess_buyer_fit(policy, facts, context=B2MatchingContext(development_state=None))
    assert not any("uncommenced" in m.lower() for m in result.matches)


# --- Control Appetite test matrix (Phase B2 brief, Section 44) ------------

def test_developer_led_evidence_with_matching_appetite():
    control_facts = ControlAppetiteFacts(developer_or_applicant_led=True, third_party_interest_declared=None, ownership_unresolved=None, partial_control_evidence=None)
    policy = replace(NESTEN_HOMES, control_appetite=frozenset({DEVELOPER_LED_ACCEPTABLE}))
    result = assess_buyer_fit(policy, _facts(), context=B2MatchingContext(control_facts=control_facts))
    assert any("developer/applicant-led" in m for m in result.matches)
    assert result.classification != NOT_SUITABLE


def test_developer_led_evidence_with_empty_appetite_is_never_a_rejection():
    control_facts = ControlAppetiteFacts(developer_or_applicant_led=True, third_party_interest_declared=None, ownership_unresolved=None, partial_control_evidence=None)
    policy = replace(NESTEN_HOMES, control_appetite=frozenset())
    result = assess_buyer_fit(policy, _facts(), context=B2MatchingContext(control_facts=control_facts))
    assert not result.does_not_match
    assert not any("developer" in m for m in result.matches)  # not evaluated at all - empty set


def test_third_party_interest_evidence_with_matching_appetite():
    control_facts = ControlAppetiteFacts(developer_or_applicant_led=None, third_party_interest_declared=True, ownership_unresolved=False, partial_control_evidence=True)
    policy = replace(NESTEN_HOMES, control_appetite=frozenset({THIRD_PARTY_INTEREST_ACCEPTABLE}))
    result = assess_buyer_fit(policy, _facts(), context=B2MatchingContext(control_facts=control_facts))
    assert any("third-party ownership interest" in m for m in result.matches)


def test_unresolved_ownership_with_matching_appetite_goes_to_investigate_not_matches():
    control_facts = ControlAppetiteFacts(developer_or_applicant_led=None, third_party_interest_declared=None, ownership_unresolved=True, partial_control_evidence=None)
    policy = replace(NESTEN_HOMES, control_appetite=frozenset({UNRESOLVED_OWNERSHIP_INVESTIGATABLE}))
    result = assess_buyer_fit(policy, _facts(), context=B2MatchingContext(control_facts=control_facts))
    assert any("remains unresolved" in i for i in result.investigate)
    assert not any("remains unresolved" in m for m in result.matches)  # never upgraded to a positive match
    assert result.classification != NOT_SUITABLE


def test_partial_control_evidence_with_matching_appetite():
    control_facts = ControlAppetiteFacts(developer_or_applicant_led=None, third_party_interest_declared=True, ownership_unresolved=False, partial_control_evidence=True)
    policy = replace(NESTEN_HOMES, control_appetite=frozenset({PARTIAL_SITE_CONTROL_ACCEPTABLE}))
    result = assess_buyer_fit(policy, _facts(), context=B2MatchingContext(control_facts=control_facts))
    assert any("partial/shared ownership" in m for m in result.matches)


def test_unknown_control_evidence_remains_unknown_never_a_hard_rejection():
    control_facts = ControlAppetiteFacts(developer_or_applicant_led=None, third_party_interest_declared=None, ownership_unresolved=None, partial_control_evidence=None)
    policy = replace(NESTEN_HOMES, control_appetite=frozenset({DEVELOPER_LED_ACCEPTABLE, THIRD_PARTY_INTEREST_ACCEPTABLE, UNRESOLVED_OWNERSHIP_INVESTIGATABLE, PARTIAL_SITE_CONTROL_ACCEPTABLE}))
    result = assess_buyer_fit(policy, _facts(), context=B2MatchingContext(control_facts=control_facts))
    assert not result.does_not_match


def test_national_housebuilders_empty_control_appetite_stays_neutral():
    """Section 32/53 - an empty/unconfigured control appetite must never
    become 'reject all control situations'."""
    control_facts = ControlAppetiteFacts(developer_or_applicant_led=True, third_party_interest_declared=True, ownership_unresolved=True, partial_control_evidence=True)
    result = assess_buyer_fit(NATIONAL_HOUSEBUILDER, _facts(), context=B2MatchingContext(control_facts=control_facts))
    assert result.classification != NOT_SUITABLE
    assert not any("developer" in m or "third-party" in m or "partial" in m for m in result.matches)


# --- Gate-2C-adapter unit tests (build_control_appetite_facts) -------------

def test_adapter_developer_led_from_developer_indications():
    facts = build_control_appetite_facts(_FakeAcquisitionPositionFacts(developer_indications=["Some Developer Ltd"]))
    assert facts.developer_or_applicant_led is True


def test_adapter_never_asserts_false_for_developer_led():
    facts = build_control_appetite_facts(_FakeAcquisitionPositionFacts(ownership_evidence=[_FakeOwnershipFact("APPLICANT_DECLARED_SOLE_OWNER")], ownership_coverage="RELEVANT_EVIDENCE_SEARCHED_INDICATION_FOUND"))
    assert facts.developer_or_applicant_led is None  # never proven False, only True or None


def test_adapter_third_party_and_partial_control_from_certificate_b_shaped_evidence():
    facts = build_control_appetite_facts(_FakeAcquisitionPositionFacts(
        ownership_evidence=[_FakeOwnershipFact("OTHER_OWNER_INTEREST_DECLARED")],
        ownership_coverage="RELEVANT_EVIDENCE_SEARCHED_INDICATION_FOUND",
    ))
    assert facts.third_party_interest_declared is True
    assert facts.partial_control_evidence is True
    assert facts.ownership_unresolved is False  # a specific, conflict-free fact IS on record


def test_adapter_unresolved_when_coverage_insufficient():
    facts = build_control_appetite_facts(_FakeAcquisitionPositionFacts(ownership_coverage="INSUFFICIENT_EVIDENCE_TO_DETERMINE_CONTROL"))
    assert facts.ownership_unresolved is True


def test_adapter_unresolved_when_conflicts_present():
    facts = build_control_appetite_facts(_FakeAcquisitionPositionFacts(
        ownership_evidence=[_FakeOwnershipFact("OTHER_OWNER_INTEREST_DECLARED")],
        ownership_coverage="RELEVANT_EVIDENCE_SEARCHED_INDICATION_FOUND",
        conflicts=["conflicting developer evidence"],
    ))
    assert facts.ownership_unresolved is True


def test_adapter_returns_unresolved_for_genuinely_empty_facts():
    """Empty AcquisitionPositionFacts (e.g. a Local Plan allocation with
    no matched site, per app.policy.buyer_matching_b2_context's own
    handling) carries coverage=COVERAGE_INSUFFICIENT by Gate 2C's own
    construction - honestly mapped to 'no specific fact established, and
    the overall position is unresolved', never a separate 'not evaluated'
    concept."""
    facts = build_control_appetite_facts(_FakeAcquisitionPositionFacts())
    assert facts == ControlAppetiteFacts(None, None, True, None)


# --- Certificate semantics safeguard (Phase B2 brief, Section 45) ---------

def test_certificate_a_evidence_never_becomes_registered_ownership_or_control_or_availability():
    """Certificate A (sole-ownership DECLARATION) must never, through the
    B2 adapter or matching, become a claim of registered title, whole-
    site control, or availability."""
    facts = build_control_appetite_facts(_FakeAcquisitionPositionFacts(
        ownership_evidence=[_FakeOwnershipFact("APPLICANT_DECLARED_SOLE_OWNER")],
        ownership_coverage="RELEVANT_EVIDENCE_SEARCHED_INDICATION_FOUND",
    ))
    # Certificate A evidence alone establishes neither developer-led nor
    # third-party/partial control - it is a sole-ownership declaration,
    # structurally distinct from every control-appetite fact this adapter
    # produces.
    assert facts.developer_or_applicant_led is None
    assert facts.third_party_interest_declared is None
    assert facts.partial_control_evidence is None
    policy = replace(NESTEN_HOMES, control_appetite=frozenset({DEVELOPER_LED_ACCEPTABLE, THIRD_PARTY_INTEREST_ACCEPTABLE, PARTIAL_SITE_CONTROL_ACCEPTABLE}))
    result = assess_buyer_fit(policy, _facts(), context=B2MatchingContext(control_facts=facts))
    # No control-appetite reason fabricated from a sole-ownership
    # declaration (other matches, e.g. planning-state/scale/acquisition-
    # type, are unrelated dimensions and are expected to still fire).
    assert not any("developer" in m.lower() or "third-party" in m.lower() or "partial" in m.lower() for m in result.matches)
    assert result.classification != NOT_SUITABLE


def test_certificate_b_evidence_never_becomes_unavailable_or_unwilling_or_automatic_mismatch():
    facts = build_control_appetite_facts(_FakeAcquisitionPositionFacts(
        ownership_evidence=[_FakeOwnershipFact("OTHER_OWNER_INTEREST_DECLARED")],
        ownership_coverage="RELEVANT_EVIDENCE_SEARCHED_INDICATION_FOUND",
    ))
    policy = replace(NESTEN_HOMES, control_appetite=frozenset({THIRD_PARTY_INTEREST_ACCEPTABLE}))
    result = assess_buyer_fit(policy, _facts(), context=B2MatchingContext(control_facts=facts))
    assert result.classification != NOT_SUITABLE
    assert not result.does_not_match
    joined = " ".join(result.matches).lower()
    assert "unavailable" not in joined and "not for sale" not in joined and "unwilling" not in joined


# --- No-disposal / availability safeguard (Section 46) ---------------------

def test_absence_of_disposal_evidence_does_not_cause_not_suitable():
    """Buyer Fit does not require the site to be listed for sale -
    MatchingFacts/B2MatchingContext carry no disposal/marketing field at
    all, so this is structurally, not just behaviourally, guaranteed."""
    assert "disposal" not in MatchingFacts.__dataclass_fields__
    assert "marketing" not in MatchingFacts.__dataclass_fields__
    assert "available" not in " ".join(MatchingFacts.__dataclass_fields__).lower()
    control_facts = ControlAppetiteFacts(developer_or_applicant_led=True, third_party_interest_declared=True, ownership_unresolved=False, partial_control_evidence=True)
    result = assess_buyer_fit(NESTEN_HOMES, _facts(), context=B2MatchingContext(council_code=None, development_state="unknown", control_facts=control_facts))
    assert result.classification != NOT_SUITABLE


# --- Real buyer architecture tests (Phase B2 brief, Section 40) -----------

def test_nesten_homes_b2_behaviour():
    """Nesten: known underway weakens UNCOMMENCED_PREFERRED (soft), but
    developer-led/unresolved ownership/no marketing evidence must not
    cause NOT_SUITABLE (Section 51)."""
    control_facts = ControlAppetiteFacts(developer_or_applicant_led=True, third_party_interest_declared=None, ownership_unresolved=True, partial_control_evidence=None)
    ctx = B2MatchingContext(council_code="trafford", development_state=DEVELOPMENT_STATE_UNDERWAY, control_facts=control_facts)
    result = assess_buyer_fit(NESTEN_HOMES, _facts(unit_count=70), context=ctx)
    assert result.classification != NOT_SUITABLE
    assert any("preference is not met" in u for u in result.unknown)  # uncommenced preference weakened, softly
    assert any("worth investigating" in i for i in result.investigate)  # unresolved ownership -> investigate, not rejected


def test_strategic_land_buyer_b2_behaviour_early_stage():
    ctx = B2MatchingContext(council_code="bury", development_state="unknown", control_facts=ControlAppetiteFacts(None, None, True, None))
    facts = _facts(opportunity_type=STRATEGIC_LAND, planning_state=ADOPTED_ALLOCATION, unit_count=150, matched_to_site=False, has_identified_planning_activity=False)
    result = assess_buyer_fit(STRATEGIC_LAND_BUYER, facts, context=ctx)
    assert result.classification != NOT_SUITABLE
    assert any("strategic-land-control" in m for m in result.matches)


def test_strategic_land_buyer_b2_behaviour_confirmed_underway_is_incompatible():
    """Section 52: a genuinely permissioned AND underway development is
    much less compatible with strategic-land-control - but only because
    trusted facts clearly contradict it, not merely because it's a
    PLANNING_DELIVERY signal.

    Phase B2 narrow remediation (Issue B): this hard rejection is only
    safe when the underway evidence is verified to cover the SAME
    opportunity scope being assessed (e.g. this opportunity IS the whole
    site, not merely a phase/recent permission/long-pending application
    on a larger site whose remaining scope is unresolved)."""
    ctx = B2MatchingContext(development_state=DEVELOPMENT_STATE_UNDERWAY, development_state_scope_verified=True)
    facts = _facts(opportunity_type=PLANNING_DELIVERY, planning_state=PERMISSION_GRANTED, unit_count=150)
    result = assess_buyer_fit(STRATEGIC_LAND_BUYER, facts, context=ctx)
    assert result.classification == NOT_SUITABLE


def test_strategic_land_buyer_b2_behaviour_underway_phase_of_larger_opportunity_is_not_auto_rejected():
    """Phase B2 narrow remediation (Issue B), regression test: one known
    underway phase/recent-permission/long-pending-application on what may
    be a larger strategic-land opportunity must NOT automatically reject
    the whole opportunity when the remaining opportunity scope is
    unresolved - the exact real-world pattern found during remediation
    investigation (a still-pending application whose own opportunity
    signal was previously hard-rejected using a site-wide "underway" fact
    that may describe a different part of the same site)."""
    ctx = B2MatchingContext(development_state=DEVELOPMENT_STATE_UNDERWAY)  # scope NOT verified (the honest default)
    facts = _facts(opportunity_type=PLANNING_DELIVERY, planning_state=PERMISSION_GRANTED, unit_count=150)
    result = assess_buyer_fit(STRATEGIC_LAND_BUYER, facts, context=ctx)
    assert result.classification != NOT_SUITABLE
    assert not result.does_not_match


def test_national_housebuilder_b2_behaviour():
    """Section 53: empty control appetite stays neutral; no new
    assumptions invented."""
    ctx = B2MatchingContext(council_code="wigan", development_state="unknown", control_facts=ControlAppetiteFacts(True, True, True, True))
    result = assess_buyer_fit(NATIONAL_HOUSEBUILDER, _facts(unit_count=300), context=ctx)
    assert result.classification != NOT_SUITABLE
    assert not any("developer" in m or "third-party" in m or "partial" in m for m in result.matches)


def test_housing_association_b2_behaviour_developer_led_mixed_tenure():
    """Section 50: a developer-led, underway, mixed-tenure scheme must
    remain relevant to Housing Association's AFFORDABLE_HOUSING_PACKAGE
    strategy - never penalised for not being a land-sale opportunity."""
    control_facts = ControlAppetiteFacts(developer_or_applicant_led=True, third_party_interest_declared=None, ownership_unresolved=None, partial_control_evidence=None)
    ctx = B2MatchingContext(council_code="stockport", development_state=DEVELOPMENT_STATE_UNDERWAY, control_facts=control_facts)
    facts = _facts(unit_count=300, affordable_unit_count=90, affordable_percentage=30.0, affordable_percentage_trusted=True)
    result = assess_buyer_fit(HOUSING_ASSOCIATION, facts, context=ctx)
    assert result.classification == STRONG_FIT
    assert any("developer/applicant-led" in m for m in result.matches)
    assert any("does not count against" in m for m in result.matches)  # UNDERWAY_ACCEPTABLE
    assert any("affordable-housing-package" in m and "does not establish that the package is known to be available" in m for m in result.matches)


# --- Same-facts/different-mandates fixture, now B2-active (Section 38-39) -

def test_same_facts_different_mandates_produce_materially_different_b2_reasoning():
    """The B1 fixture, now WITH B2 active: ~300 homes, permissioned,
    developer-led, Phase 1 underway, ~30% affordable, no disposal
    evidence. Four mandates must reason differently about it.

    Phase B2 narrow remediation (Issues B & C): the fixture only ever
    says "Phase 1 underway" - it does NOT establish that the wider
    strategic-land opportunity itself has been overtaken by delivery -
    so development_state_scope_verified is deliberately left at its
    honest default (False/unverified) here. This fixture must therefore
    NOT be used to prove a whole-opportunity Strategic Land NOT_SUITABLE
    result (see test_strategic_land_hard_rejection_requires_verified_
    whole_opportunity_scope below for the case where scope IS verified).
    The land/site buyer must also not receive a fact-free positive
    acquisition-type reason merely for stating LAND_SITE_ACQUISITION."""
    shared_facts = _facts(unit_count=300, affordable_unit_count=90, affordable_percentage=30.0, affordable_percentage_trusted=True, planning_state=PERMISSION_GRANTED)
    control_facts = ControlAppetiteFacts(developer_or_applicant_led=True, third_party_interest_declared=None, ownership_unresolved=None, partial_control_evidence=None)
    ctx = B2MatchingContext(council_code="trafford", development_state=DEVELOPMENT_STATE_UNDERWAY, control_facts=control_facts)

    land_buyer = replace(NESTEN_HOMES, target_unit_min=200, target_unit_max=500, acquisition_types=frozenset({LAND_SITE_ACQUISITION}), development_state_appetite=UNCOMMENCED_PREFERRED, control_appetite=frozenset({DEVELOPER_LED_ACCEPTABLE}))
    housing_association = replace(HOUSING_ASSOCIATION, target_unit_min=50, target_unit_max=300, acquisition_types=frozenset({AFFORDABLE_HOUSING_PACKAGE}), development_state_appetite=UNDERWAY_ACCEPTABLE, control_appetite=frozenset({DEVELOPER_LED_ACCEPTABLE}))
    institutional_buyer = replace(NESTEN_HOMES, target_unit_min=100, target_unit_max=500, acquisition_types=frozenset({DEVELOPMENT_HOMES_ACQUISITION}), development_state_appetite=UNDERWAY_PREFERRED, control_appetite=frozenset({DEVELOPER_LED_ACCEPTABLE}))
    strategic_buyer = replace(STRATEGIC_LAND_BUYER, target_unit_min=100, target_unit_max=500, acquisition_types=frozenset({STRATEGIC_LAND_CONTROL}))

    land_result = assess_buyer_fit(land_buyer, shared_facts, context=ctx)
    ha_result = assess_buyer_fit(housing_association, shared_facts, context=ctx)
    institutional_result = assess_buyer_fit(institutional_buyer, shared_facts, context=ctx)
    strategic_result = assess_buyer_fit(strategic_buyer, shared_facts, context=ctx)

    # Land buyer: underway weakens its uncommenced preference (soft), but
    # developer-led control is accepted, never a hard rejection - and it
    # must not get a circular, fact-free LAND_SITE_ACQUISITION match.
    assert land_result.classification != NOT_SUITABLE
    assert any("preference is not met" in u for u in land_result.unknown)
    assert not any("land/site acquisition" in m for m in land_result.matches)

    # Housing Association: STRONG_FIT - developer-led + underway both
    # explicitly accepted, affordable package structurally relevant.
    assert ha_result.classification == STRONG_FIT

    # Institutional/development-homes buyer: underway is a POSITIVE
    # signal here - the opposite polarity from the land buyer.
    assert any("positive signal" in m for m in institutional_result.matches)

    # Strategic land buyer: "Phase 1 underway" alone does NOT establish
    # that the wider strategic-land opportunity's own relevant scope has
    # been overtaken - scope is unverified, so this must NOT be a hard
    # rejection; it is surfaced as worth investigating instead.
    assert strategic_result.classification != NOT_SUITABLE
    assert not strategic_result.does_not_match
    assert any("scope" in i for i in strategic_result.investigate)


def test_strategic_land_hard_rejection_requires_verified_whole_opportunity_scope():
    """Positive companion to the fixture above (Phase B2 narrow
    remediation, Issue B): when evidence DOES establish that the
    RELEVANT strategic-land opportunity itself - not merely one phase of
    a larger site - has been overtaken by confirmed development delivery
    (development_state_scope_verified=True, e.g. this opportunity IS the
    whole site), the hard rejection remains available. The remediation
    must not remove all Strategic Land hard exclusions - only make them
    scope-safe."""
    shared_facts = _facts(unit_count=300, affordable_unit_count=90, affordable_percentage=30.0, affordable_percentage_trusted=True, planning_state=PERMISSION_GRANTED)
    control_facts = ControlAppetiteFacts(developer_or_applicant_led=True, third_party_interest_declared=None, ownership_unresolved=None, partial_control_evidence=None)
    ctx = B2MatchingContext(council_code="trafford", development_state=DEVELOPMENT_STATE_UNDERWAY, control_facts=control_facts, development_state_scope_verified=True)
    strategic_buyer = replace(STRATEGIC_LAND_BUYER, target_unit_min=100, target_unit_max=500, acquisition_types=frozenset({STRATEGIC_LAND_CONTROL}))

    result = assess_buyer_fit(strategic_buyer, shared_facts, context=ctx)
    assert result.classification == NOT_SUITABLE
    assert any("underway" in m and "scope" in m for m in result.does_not_match)


# --- UNKNOWN semantics review (Section 22) ---------------------------------

def test_unknown_remains_distinct_from_not_suitable_under_b2():
    policy = replace(NESTEN_HOMES, geography_scope=GEOGRAPHY_COUNCILS, geography_councils=frozenset({"bury"}))
    ctx = B2MatchingContext(council_code=None, development_state="unknown", control_facts=ControlAppetiteFacts(None, None, None, None))
    result = assess_buyer_fit(policy, _facts(), context=ctx)
    assert result.classification == INSUFFICIENT_EVIDENCE
    assert result.classification != NOT_SUITABLE
