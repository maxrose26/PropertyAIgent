"""Canonical NESTEN_HOMES mandate, reconciled with the real Nesten Land Requirements
(Product Owner-supplied, authoritative): 50-200 single-family homes, and no stated
affordable-housing exclusion. Pure, DB-free tests of the deterministic v6 matching.

Scope notes: this is mandate DATA only - BUYER_MATCHING_POLICY_VERSION is unchanged. Generic
50-100 mechanics tests elsewhere use an explicit synthetic mandate, not canonical Nesten.
"""
from __future__ import annotations

import pytest

from app.policy.buyer_matching import (
    BUYER_MATCHING_POLICY_VERSION, INSUFFICIENT_EVIDENCE, NOT_SUITABLE, PLANNING_DELIVERY, POSSIBLE_FIT, STRONG_FIT,
    MatchingFacts, assess_buyer_fit, discovery_bounds,
)
from app.policy.buyer_profiles import (
    HOUSING_ASSOCIATION, NATIONAL_HOUSEBUILDER, NESTEN_HOMES, PERMISSION_GRANTED, STRATEGIC_LAND_BUYER,
)


def _facts(**overrides) -> MatchingFacts:
    base = dict(
        opportunity_type=PLANNING_DELIVERY, unit_count=120, development_type_raw="houses",
        is_specialist_development=False, affordable_percentage=30.0, affordable_percentage_trusted=True,
        affordable_unit_count=36, planning_state=PERMISSION_GRANTED, has_identified_planning_activity=True,
        has_phasing_evidence=False, matched_to_site=True,
    )
    base.update(overrides)
    return MatchingFacts(**base)


def test_policy_version_is_unchanged_by_the_mandate_correction():
    assert BUYER_MATCHING_POLICY_VERSION == 6


def test_canonical_nesten_preferred_scale_is_50_to_200():
    assert (NESTEN_HOMES.target_unit_min, NESTEN_HOMES.target_unit_max) == (50, 200)


def test_canonical_nesten_discovery_envelope_is_45_to_220():
    assert discovery_bounds(NESTEN_HOMES.target_unit_min, NESTEN_HOMES.target_unit_max) == (45, 220)


@pytest.mark.parametrize("units", [50, 100, 101, 150, 200])
def test_exact_counts_in_the_preferred_range_are_strong_fit(units):
    fit = assess_buyer_fit(NESTEN_HOMES, _facts(unit_count=units))
    assert fit.classification == STRONG_FIT


@pytest.mark.parametrize("units", [45, 49, 201, 210, 220])
def test_exact_counts_in_the_discovery_band_are_possible_fit(units):
    fit = assess_buyer_fit(NESTEN_HOMES, _facts(unit_count=units))
    assert fit.classification == POSSIBLE_FIT
    assert any("discovery range (45-220 homes)" in m for m in fit.matches)


@pytest.mark.parametrize("units", [44, 221, 675])
def test_exact_counts_outside_discovery_are_investigative_not_strong_or_possible(units):
    fit = assess_buyer_fit(NESTEN_HOMES, _facts(unit_count=units))
    assert fit.classification == INSUFFICIENT_EVIDENCE
    assert fit.is_investigative_exception is True
    assert any("outside this buyer's discovery range (45-220 homes; preferred 50-200 homes)" in i for i in fit.investigate)


def test_wholly_affordable_evidence_alone_no_longer_hard_excludes_nesten():
    assert NESTEN_HOMES.wholly_affordable_is_exclusion is False
    fit = assess_buyer_fit(NESTEN_HOMES, _facts(unit_count=120, affordable_percentage=100.0))
    assert fit.classification != NOT_SUITABLE
    assert not fit.does_not_match
    # Visible context only: neither a fit signal (that polarity is Housing Association's) nor an exclusion.
    assert not any("affordable" in m.lower() for m in fit.matches)
    assert any("100%" in u and "not a fit signal" in u for u in fit.unknown)
    assert any("affordable composition" in i for i in fit.investigate)


def test_clearly_specialist_only_subject_remains_incompatible_for_nesten():
    fit = assess_buyer_fit(NESTEN_HOMES, _facts(is_specialist_development=True, development_type_raw="retirement_living"))
    assert fit.classification == NOT_SUITABLE
    assert any("specialist" in r for r in fit.does_not_match)


def test_unknown_affordable_percentage_is_still_visible_and_never_zero():
    fit = assess_buyer_fit(NESTEN_HOMES, _facts(affordable_percentage=None, affordable_percentage_trusted=False))
    assert any("not assumed to be 0%" in u for u in fit.unknown)


def test_other_buyers_are_unchanged():
    assert (STRATEGIC_LAND_BUYER.target_unit_min, STRATEGIC_LAND_BUYER.target_unit_max) == (100, 300)
    assert (NATIONAL_HOUSEBUILDER.target_unit_min, NATIONAL_HOUSEBUILDER.target_unit_max) == (200, 500)
    for profile in (STRATEGIC_LAND_BUYER, NATIONAL_HOUSEBUILDER):
        assert profile.wholly_affordable_is_exclusion is True
        assert profile.specialist_development_is_exclusion is True
    assert HOUSING_ASSOCIATION.wholly_affordable_is_exclusion is False
    national = assess_buyer_fit(NATIONAL_HOUSEBUILDER, _facts(unit_count=300, affordable_percentage=100.0))
    assert national.classification == NOT_SUITABLE
    assert any("100%" in r for r in national.does_not_match)


def test_housing_association_still_reads_wholly_affordable_as_on_strategy():
    fit = assess_buyer_fit(HOUSING_ASSOCIATION, _facts(affordable_percentage=100.0, affordable_unit_count=120))
    assert any("100%" in m and "affordable-housing focus" in m for m in fit.matches)
    assert not any("100%" in u and "not a fit signal" in u for u in fit.unknown)


def test_real_brief_context_is_recorded_in_the_mandate_notes_without_new_rules():
    notes = NESTEN_HOMES.notes
    for expected in ("50-200 single-family homes", "joint venture", "promotable", "hectares", "South East",
                     "North West", "CONTEXT for investigation"):
        assert expected in notes
    # Context only: no region, site-size or JV matching rule exists.
    assert NESTEN_HOMES.geography_scope == "ALL_CURRENT_COVERAGE" and not NESTEN_HOMES.geography_councils
