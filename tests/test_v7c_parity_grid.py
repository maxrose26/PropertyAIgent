"""Stage 2.5B V7C: bounded deterministic OFFLINE differential grid - the frozen v6 oracle versus the current v7 matcher.

Representative boundary values only (not a combinatorial explosion). Across the whole approved V7A domain, classification and the investigative flag must be IDENTICAL between the frozen v6
matcher and v7; reason text is allowed (and, where V7A applies, expected) to differ. The grid also asserts it actually exercises the V7A branches (otherwise equality would prove nothing).
"""
from __future__ import annotations

from itertools import product

import pytest

import verification.transition.frozen_v6_matcher as frozen
from app.policy.buyer_matching import (
    PHASING_CURRENT_EVIDENCED_PHASE, PHASING_CURRENTNESS_UNKNOWN, PHASING_DOCUMENTED, PHASING_HISTORICAL_ONLY, PHASING_NONE_IDENTIFIED, PLANNING_DELIVERY,
    STRATEGIC_LAND, AcquisitionPhasingEvidence, B2MatchingContext, MatchingFacts, assess_buyer_fit, discovery_bounds,
)
from app.policy.buyer_profiles import ADOPTED_ALLOCATION, AFFORDABLE_UNITS, BUYER_PROFILES, EMERGING_ALLOCATION, PERMISSION_GRANTED
from app.reporting.residential_count import CountAssessment

BUYERS = ("nesten_homes", "national_housebuilder", "strategic_land_buyer", "housing_association")
PHASING = (None, PHASING_CURRENT_EVIDENCED_PHASE, PHASING_CURRENTNESS_UNKNOWN, PHASING_HISTORICAL_ONLY, PHASING_NONE_IDENTIFIED, PHASING_DOCUMENTED)
SCOPES = ("wider", "phase_key", "application_anchored")           # wider/whole subject, phase self-scope (explicit key), application-anchored subject


def scales(profile):
    lo, hi = profile.target_unit_min, profile.target_unit_max
    dmin, dmax = discovery_bounds(lo, hi)
    if profile.below_minimum_scale_is_exclusion:
        dmin = lo
    return sorted({1, max(1, dmin - 1), dmin, lo - 1 if lo > 1 else lo, lo, (lo + hi) // 2, hi, hi + 1, dmax, dmax + 1, hi * 2, hi * 5, 15000})


def facts(profile, scale, **overrides):
    base = dict(opportunity_type=PLANNING_DELIVERY, unit_count=scale, development_type_raw="houses", is_specialist_development=False, affordable_percentage=30.0,
                affordable_percentage_trusted=True, affordable_unit_count=scale if profile.scale_metric == AFFORDABLE_UNITS else max(1, scale // 3),
                planning_state=PERMISSION_GRANTED, has_identified_planning_activity=True, has_phasing_evidence=False, matched_to_site=True)
    if profile.scale_metric == AFFORDABLE_UNITS:
        base["unit_count"] = scale * 3
    base.update(overrides)
    return MatchingFacts(**base)


def context(state, scope, **kw):
    return B2MatchingContext(acquisition_phasing=AcquisitionPhasingEvidence(state) if state else None,
                             subject_phase_scope_key="1" if scope == "phase_key" else None, subject_application_anchored=scope == "application_anchored", **kw)


def exact(scope_type, n):
    return CountAssessment(scope_type=scope_type, scope_label="x", precision="EXACT", value=n, lower=n, upper=n, resolution="agreement", confidence="high")


class Stats:
    total = 0
    text_differs = 0
    by_branch: dict = {}


def compare(profile, fact, ctx, branch):
    v6 = frozen.assess_buyer_fit(profile, fact, context=ctx)
    v7 = assess_buyer_fit(profile, fact, context=ctx)
    assert v6.classification == v7.classification, (profile.key, branch, fact, ctx)
    assert bool(v6.is_investigative_exception) == bool(v7.is_investigative_exception), (profile.key, branch, fact, ctx)
    Stats.total += 1
    Stats.by_branch[branch] = Stats.by_branch.get(branch, 0) + 1
    differs = (v6.matches, v6.unknown, v6.investigate, v6.does_not_match) != (v7.matches, v7.unknown, v7.investigate, v7.does_not_match)
    Stats.text_differs += differs
    return v6, v7, differs


@pytest.fixture(autouse=True, scope="module")
def reset_stats():
    Stats.total, Stats.text_differs, Stats.by_branch = 0, 0, {}


@pytest.mark.parametrize("buyer", BUYERS)
def test_planning_delivery_scalar_scales_across_phasing_scope_and_hard_exclusions(buyer):
    profile = BUYER_PROFILES[buyer]
    oversize_text_differences = below_text_differences = 0
    for scale, state, scope, exclusion in product(scales(profile), PHASING, SCOPES, ("none", "specialist", "wholly_affordable")):
        overrides = {}
        if exclusion == "specialist":
            overrides = dict(is_specialist_development=True, development_type_raw="retirement_living")
        elif exclusion == "wholly_affordable":
            overrides = dict(affordable_percentage=100.0, affordable_percentage_trusted=True)
        fact = facts(profile, scale, **overrides)
        v6, v7, differs = compare(profile, fact, context(state, scope), f"planning_scalar:{exclusion}")
        lo, hi = profile.target_unit_min, profile.target_unit_max
        dmin, dmax = discovery_bounds(lo, hi)
        if exclusion == "none" and profile.scale_metric != AFFORDABLE_UNITS:
            if scale > dmax and scope == "wider" and state:
                assert differs                                   # the V7A B' reason change really fires here (otherwise this grid proves nothing)
                oversize_text_differences += 1
            if scale < min(dmin, lo):
                below_text_differences += differs
    if BUYER_PROFILES[buyer].scale_metric != AFFORDABLE_UNITS:
        assert oversize_text_differences > 0 and below_text_differences > 0
    else:
        # Housing Association: affordable-unit scale keeps its v6 wording above the maximum; only the below-minimum neutral wording can differ (and it is a hard minimum there)
        assert oversize_text_differences == 0


@pytest.mark.parametrize("buyer", BUYERS)
def test_uncertain_counts_exact_approximate_and_ranges_in_every_phasing_and_scope(buyer):
    profile = BUYER_PROFILES[buyer]
    lo, hi = profile.target_unit_min, profile.target_unit_max
    dmin, dmax = discovery_bounds(lo, hi)
    if profile.below_minimum_scale_is_exclusion:
        dmin = lo
    assessments = [
        exact("whole_site", hi * 3), exact("phase", hi * 3), exact("whole_site", (lo + hi) // 2),
        CountAssessment(scope_type="whole_site", scope_label="x", precision="APPROXIMATE", value=hi * 2, lower=hi * 2 - 1, upper=hi * 2 + 1, resolution="immaterial_variance", confidence="medium"),
        CountAssessment(scope_type="whole_site", scope_label="x", precision="RANGE", lower=dmax + 5, upper=dmax + 50, resolution="material_conflict", confidence="low"),     # wholly above
        CountAssessment(scope_type="whole_site", scope_label="x", precision="RANGE", lower=1, upper=max(1, dmin - 1), resolution="material_conflict", confidence="low"),       # wholly below
        CountAssessment(scope_type="whole_site", scope_label="x", precision="RANGE", lower=lo, upper=hi, resolution="material_conflict", confidence="low"),                   # within preferred
        CountAssessment(scope_type="whole_site", scope_label="x", precision="RANGE", lower=max(1, dmin - 5), upper=dmax + 5, resolution="material_conflict", confidence="low"),  # crossing
        CountAssessment(scope_type="whole_site", scope_label="x", precision="UNKNOWN"),
    ]
    for assessment, state, scope in product(assessments, PHASING, SCOPES):
        fact = facts(profile, assessment.value or hi, count_assessment=assessment)
        compare(profile, fact, context(state, scope), "uncertain_or_assessed")


@pytest.mark.parametrize("buyer", BUYERS)
def test_strategic_allocations_including_the_explicit_large_allocation_route(buyer):
    profile = BUYER_PROFILES[buyer]
    for scale, phasing_flag, matched, planning_state, state in product(scales(profile), (False, True), (False, True), (EMERGING_ALLOCATION, ADOPTED_ALLOCATION), (None, PHASING_CURRENT_EVIDENCED_PHASE)):
        fact = facts(profile, scale, opportunity_type=STRATEGIC_LAND, planning_state=planning_state, development_type_raw=None, is_specialist_development=None,
                     affordable_percentage=None, affordable_percentage_trusted=False, affordable_unit_count=None, has_phasing_evidence=phasing_flag, matched_to_site=matched,
                     has_identified_planning_activity=False)
        v6, v7, differs = compare(profile, fact, context(state, "wider"), "strategic")
        if scale > discovery_bounds(profile.target_unit_min, profile.target_unit_max)[1]:
            assert not differs                                      # strategic above-maximum wording is untouched by V7A (v6 text exactly)


@pytest.mark.parametrize("buyer", BUYERS)
def test_b2_context_dimensions_development_state_scope_geography_and_none_context(buyer):
    profile = BUYER_PROFILES[buyer]
    lo, hi = profile.target_unit_min, profile.target_unit_max
    for scale, development_state, verified, council, no_context in product((lo, hi * 3), ("unknown", "underway", "complete"), (False, True), (None, "testcouncil", "elsewhere"), (False, True)):
        fact = facts(profile, scale)
        ctx = None if no_context else B2MatchingContext(council_code=council, development_state=development_state, development_state_scope_verified=verified)
        compare(profile, fact, ctx, "b2_context")


def test_the_grid_exercised_a_meaningful_domain_and_reason_text_did_differ_where_v7a_applies():
    # Runs after the parametrised tests above (module order). Equality alone would be vacuous if the V7A branches were never hit.
    assert Stats.total >= 3000
    assert Stats.text_differs > 0
    assert Stats.by_branch.get("planning_scalar:none", 0) > 500 and Stats.by_branch.get("planning_scalar:specialist", 0) > 100
    assert Stats.by_branch.get("planning_scalar:wholly_affordable", 0) > 100 and Stats.by_branch.get("uncertain_or_assessed", 0) > 500
    assert Stats.by_branch.get("strategic", 0) > 200 and Stats.by_branch.get("b2_context", 0) > 100
