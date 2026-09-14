"""Agent Evaluation Foundation - tests for app.policy.
acquisition_type_interpretation: the Acquisition-Type Interpretation Policy
V1 bounded commercial principles.

Core Product Owner correction under direct test: this is NOT a rigid
signal -> positive/negative polarity table. Every principle must describe
CIRCUMSTANCES (strengthens_when/weakens_when/neutral_when), never assert a
single universal polarity for a signal - RECENT_PERMISSION and
DEVELOPMENT_UNDERWAY are the two signals the Product Owner named explicitly
as needing this discipline.

Pure, DB-free - this module is plain config."""
from __future__ import annotations

from app.policy.acquisition_type_interpretation import (
    ACQUISITION_TYPE_INTERPRETATION_POLICY_VERSION,
    ACQUISITION_TYPE_PRINCIPLES,
    get_principle_for_signal,
    get_principles,
)
from app.policy.buyer_profiles import (
    ACQUISITION_TYPES,
    AFFORDABLE_HOUSING_PACKAGE,
    DEVELOPMENT_HOMES_ACQUISITION,
    LAND_SITE_ACQUISITION,
    STRATEGIC_LAND_CONTROL,
)


def test_all_four_existing_acquisition_types_are_covered():
    for acquisition_type in ACQUISITION_TYPES:
        assert len(get_principles(acquisition_type)) > 0, f"no principles documented for {acquisition_type!r}"


def test_no_rigid_universal_polarity_encoded_for_recent_permission():
    """RECENT_PERMISSION must never be reduced to a single positive/
    negative verdict - every acquisition type's own principle must express
    circumstances, not a verdict."""
    for acquisition_type in ACQUISITION_TYPES:
        principle = get_principle_for_signal(acquisition_type, "recent_permission")
        if principle is None:
            continue
        # A verdict-shaped principle would leave strengthens_when/weakens_when
        # essentially unconditional ("always"/"" or absent) - every principle
        # documented here must instead name a real, specific circumstance.
        assert principle.strengthens_when.strip()
        assert principle.weakens_when.strip()
        assert principle.neutral_when.strip()
        assert "low transaction propensity" not in principle.why_it_matters.lower()
        assert "always negative" not in principle.weakens_when.lower()
        assert "always positive" not in principle.strengthens_when.lower()


def test_no_rigid_universal_polarity_encoded_for_development_underway():
    for acquisition_type in ACQUISITION_TYPES:
        principle = get_principle_for_signal(acquisition_type, "development_underway")
        if principle is None:
            continue
        assert principle.strengthens_when.strip()
        assert principle.weakens_when.strip()
        assert principle.neutral_when.strip()


def test_land_site_acquisition_recent_permission_is_genuinely_ambiguous():
    """The specific Product Owner example: for LAND_SITE_ACQUISITION,
    recent permission must not collapse to a single negative reading -
    both a strengthening and a weakening circumstance must be documented."""
    principle = get_principle_for_signal(LAND_SITE_ACQUISITION, "recent_permission")
    assert principle is not None
    assert principle.strengthens_when.strip()
    assert principle.weakens_when.strip()


def test_development_underway_polarity_differs_by_acquisition_type():
    """The same signal must be read through genuinely different, acquisition-
    type-specific commercial lenses - not copy-pasted principles."""
    land = get_principle_for_signal(LAND_SITE_ACQUISITION, "development_underway")
    homes = get_principle_for_signal(DEVELOPMENT_HOMES_ACQUISITION, "development_underway")
    assert land is not None and homes is not None
    assert land.why_it_matters != homes.why_it_matters
    assert land.strengthens_when != homes.strengthens_when


def test_get_principles_returns_empty_tuple_never_raises_for_unknown_type():
    assert get_principles("SOME_FUTURE_TYPE_NOT_YET_DEFINED") == ()
    assert get_principle_for_signal("SOME_FUTURE_TYPE_NOT_YET_DEFINED", "recent_permission") is None


def test_policy_version_is_stamped():
    assert ACQUISITION_TYPE_INTERPRETATION_POLICY_VERSION == 1


def test_no_forbidden_seller_intent_language_anywhere_in_the_principles():
    forbidden = ("willing to sell", "seller intent", "likely to sell", "available for purchase", "transaction propensity score")
    for principles in ACQUISITION_TYPE_PRINCIPLES.values():
        for principle in principles:
            for field_value in (principle.why_it_matters, principle.strengthens_when, principle.weakens_when, principle.neutral_when, principle.distinguishing_evidence):
                lowered = field_value.lower()
                for phrase in forbidden:
                    assert phrase not in lowered, f"forbidden phrase {phrase!r} found in {field_value!r}"


def test_strategic_land_control_and_affordable_housing_package_are_also_covered():
    assert len(get_principles(STRATEGIC_LAND_CONTROL)) > 0
    assert len(get_principles(AFFORDABLE_HOUSING_PACKAGE)) > 0
