"""Buyer Profiles V1 (Phase 1 pilot) - three fixed, Product-Owner-approved
acquisition strategies, expressed as typed, structured configuration.

Deliberately NOT a database model. This mirrors existing repository
convention for small, fixed vocabularies (e.g. app.reporting.
allocation_discovery.PLAN_STATUS_META, app.ui.housing_type's
_DEV_TYPE_* sets) rather than introducing a schema/migration for exactly
three pilot profiles that the Product Owner defined by hand, not by any
user-facing "create a buyer" workflow. If a future gate needs
user-editable, growing buyer profiles, that is a genuine schema decision
for that gate to make explicitly - not implied by this one.

Every field here is either a literal fact the Product Owner stated
verbatim in the brief, or a narrow, explained interpretation of it -
never an invented threshold. See each profile's own `notes` for anything
that required interpretation, and app/policy/buyer_matching.py's own
module docstring for the shared decision rules built on top of these.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# --- Planning-state vocabulary (shared, not per-profile) --------------------
#
# Deliberately narrower than the full plan_status/allocation_status
# vocabulary elsewhere in the codebase - buyer matching only needs to know
# which of these three coarse positions an opportunity is in, derived from
# already-trusted fields (never re-classified from scratch here):
#   - PERMISSION_GRANTED: a real, granted planning decision exists
#     (planning/delivery opportunities are only ever sourced from these -
#     see app.reporting.dashboard's approaching-lapse/undeveloped-phase
#     builders, both already gated on a granted decision).
#   - ADOPTED_ALLOCATION / EMERGING_ALLOCATION: from
#     app.reporting.allocation_discovery.PLAN_STATUS_META's own
#     "adopted"/"emerging" bucket - never re-derived from raw status text.
#   - OTHER_OR_UNKNOWN: anything else (a plan status bucketed "other", or
#     a case this module cannot classify with confidence) - always reads
#     as missing evidence, never as a silent exclusion.
PERMISSION_GRANTED = "permission_granted"
ADOPTED_ALLOCATION = "adopted_allocation"
EMERGING_ALLOCATION = "emerging_allocation"
OTHER_OR_UNKNOWN = "other_or_unknown"

# --- Specialist/non-general-needs development types -------------------------
#
# Read directly from SchemeIntelligence.development_type's own existing
# controlled vocabulary (app/extraction/prompts.py's development_type enum,
# already reused by app.ui.housing_type's _DEV_TYPE_OTHER/_DEV_TYPE_MIXED
# sets) - not a new classification. The investigation's own Focus School
# finding is the reason "mixed_retirement_and_market_housing"/
# "mixed_specialist_and_market_housing" are included here even though
# app.ui.housing_type's own UI-facing bucketing lumps them into a generic
# "Mixed" label: that bucketing is a presentation simplification for a map
# legend, not a signal that the specialist component is incidental. A
# scheme the platform's own extraction schema named "retirement AND
# market" (naming the specialist use as one of exactly two components) is
# not honestly described as this buyer's stated "general-needs housing"
# primary product, independent of the unrecorded unit-level split - see
# this module's own test suite for the real Focus School figures this
# reasoning is grounded in (72 of 82 units were the retirement component).
# Never inferred from a numeric threshold - MEMBERSHIP of this fixed,
# evidence-grounded set is the only rule, exactly per the brief's own "do
# not invent an affordable-percentage-style threshold" instruction applied
# here to development type instead.
SPECIALIST_DEVELOPMENT_TYPES = frozenset({
    "retirement_living",
    "care_home",
    "student_accommodation",
    "supported_living",
    "mixed_retirement_and_market_housing",
    "mixed_specialist_and_market_housing",
})

# The exact, literal boundary the brief itself specifies ("100%
# affordable-led development") - not a threshold invented by this module.
WHOLLY_AFFORDABLE_THRESHOLD = 100.0

# --- Scale metric (Housing Association amendment) ---------------------------
#
# Which unit figure a profile's target_unit_min/max range is measured
# against. The three original pilot profiles all assess scale against the
# TOTAL scheme unit count (unchanged - this constant makes that explicit
# rather than assumed). The Housing Association profile is the first to
# need AFFORDABLE_UNITS instead: its brief is explicit that "for the
# Housing Association profile, scale must be assessed using AFFORDABLE
# residential units" - a 400-home scheme with 120 affordable homes is
# assessed against 120, not 400. Generic on BuyerProfile rather than a
# Housing-Association-only branch in app.policy.buyer_matching, per the
# amendment brief's own "do NOT implement this as a one-off hard-coded
# exception if the existing structure can safely support a generic
# concept" instruction.
TOTAL_UNITS = "total_units"
AFFORDABLE_UNITS = "affordable_units"


@dataclass(frozen=True)
class BuyerProfile:
    key: str
    display_name: str
    buyer_type: str
    primary_requirement: str
    target_unit_min: int
    target_unit_max: int
    # Which of target_unit_min/max's own unit figures this profile's scale
    # is measured against - TOTAL_UNITS for every original pilot profile,
    # AFFORDABLE_UNITS for Housing Association. See the constants' own
    # docstring above.
    scale_metric: str
    # Planning states this buyer has explicitly stated an appetite for -
    # membership produces a positive "matches" reason. Absence from this
    # set is NEVER treated as a hard exclusion (none of the three pilot
    # profiles' own brief lists a planning-state mismatch as a disqualifying
    # ground - only development type and 100%-affordable are) - it reads as
    # an "unknown relevance" note instead, per the brief's own "do not
    # invent additional planning-risk requirements" instruction.
    accepted_planning_states: frozenset[str]
    # Strategic Land Buyer-specific framing (Product Owner brief, Profile
    # 2): "little/no identified planning activity can be positive context
    # rather than a disqualifier." False for every other profile - this
    # is the one place a buyer's own risk appetite changes how an
    # otherwise-neutral fact is framed, not what the fact itself is.
    treats_no_activity_as_positive: bool
    # Strategic Land Buyer-specific framing (Product Owner brief, Profile
    # 2): "a large allocation may still represent a strategic opportunity
    # where... the allocation itself represents a meaningful strategic-land
    # position" - i.e. for this buyer only, an allocation's own scale can
    # itself be a positive match even without confirmed parcel/phasing
    # evidence, distinct from Nesten/National Housebuilder, for whom an
    # oversized allocation without phasing evidence stays an open question,
    # never a match.
    large_allocation_is_self_qualifying: bool
    # Housing Association amendment - whether a trusted specialist/non-
    # general-needs RESIDENTIAL development type (SPECIALIST_DEVELOPMENT_
    # TYPES - retirement/care/student/supported) is a hard exclusion for
    # this buyer. True for every housebuilder pilot profile (unchanged).
    # False for Housing Association, whose own brief explicitly forbids
    # copying the housebuilders' exclusion list onto it ("I have not
    # specified that requirement... do not invent a hard exclusion") - for
    # such a profile the fact is preserved as contextual/unknown instead
    # (app.policy.buyer_matching.assess_buyer_fit). This flag does NOT
    # govern a genuinely non-residential (e.g. employment) allocation - that
    # stays a universal exclusion for every profile regardless of this flag,
    # since it is a different, unambiguous fact ("not residential at all"),
    # not an unstated specialist-product preference.
    specialist_development_is_exclusion: bool
    # Housing Association amendment - whether a trusted wholly (100%)
    # affordable-led scheme is a hard exclusion. True for every housebuilder
    # pilot profile (unchanged - "not open-market residential development").
    # False for Housing Association, whose own brief states this is "the
    # opposite of the three existing pilot profiles... potentially highly
    # relevant" - deliberately reversed polarity, never merely "not an
    # exclusion" (a trusted 100%-affordable figure becomes a positive
    # "matches" reason for this buyer, since it is directly on-strategy).
    wholly_affordable_is_exclusion: bool
    # Housing Association amendment - whether falling BELOW this profile's
    # own minimum scale figure is a hard exclusion. False for every
    # housebuilder pilot profile (unchanged - a scheme below a housebuilder's
    # minimum stays an open "not treated as a disqualifying fact on its own"
    # question, never excluded). True for Housing Association, whose own
    # brief explicitly requires this ("NOT SUITABLE: fewer than 50 affordable
    # homes") - a genuine behavioural difference from the housebuilders, not
    # an oversight; see this profile's own notes.
    below_minimum_scale_is_exclusion: bool
    notes: str


NESTEN_HOMES = BuyerProfile(
    key="nesten_homes",
    display_name="Nesten Homes",
    buyer_type="Regional housebuilder",
    primary_requirement="Residential development land",
    target_unit_min=50,
    target_unit_max=100,
    scale_metric=TOTAL_UNITS,
    accepted_planning_states=frozenset({PERMISSION_GRANTED, ADOPTED_ALLOCATION, EMERGING_ALLOCATION}),
    treats_no_activity_as_positive=False,
    large_allocation_is_self_qualifying=False,
    specialist_development_is_exclusion=True,
    wholly_affordable_is_exclusion=True,
    below_minimum_scale_is_exclusion=False,
    notes=(
        "Brief: \"residential sites with planning permission; OR sites allocated for residential "
        "development\" - read as accepting both adopted and emerging allocation status, since the brief "
        "does not restrict Nesten to adopted-only allocations. No affordable-percentage threshold below "
        "100% is implemented (brief: \"do NOT invent an affordable-percentage threshold below 100%\")."
    ),
)

STRATEGIC_LAND_BUYER = BuyerProfile(
    key="strategic_land_buyer",
    display_name="Strategic Land Buyer",
    buyer_type="Strategic land buyer / promoter",
    primary_requirement="Large residential strategic-land opportunities",
    target_unit_min=100,
    target_unit_max=300,
    scale_metric=TOTAL_UNITS,
    accepted_planning_states=frozenset({ADOPTED_ALLOCATION, EMERGING_ALLOCATION}),
    treats_no_activity_as_positive=True,
    large_allocation_is_self_qualifying=True,
    specialist_development_is_exclusion=True,
    wholly_affordable_is_exclusion=True,
    below_minimum_scale_is_exclusion=False,
    notes=(
        "Brief: \"Planning permission is NOT required\" - PERMISSION_GRANTED is deliberately not in this "
        "buyer's accepted_planning_states (their own stated appetite doesn't mention it), but per this "
        "module's own rule, that absence produces an 'unknown relevance' note for a permission-granted "
        "opportunity, never a hard exclusion - the brief never asked for permission-granted sites to be "
        "excluded, only that they aren't this buyer's stated focus."
    ),
)

NATIONAL_HOUSEBUILDER = BuyerProfile(
    key="national_housebuilder",
    display_name="National Housebuilder",
    buyer_type="Large national housebuilder",
    primary_requirement="Large residential housing sites capable of meaningful delivery scale",
    target_unit_min=200,
    target_unit_max=500,
    scale_metric=TOTAL_UNITS,
    accepted_planning_states=frozenset({PERMISSION_GRANTED, ADOPTED_ALLOCATION, EMERGING_ALLOCATION}),
    treats_no_activity_as_positive=False,
    large_allocation_is_self_qualifying=False,
    specialist_development_is_exclusion=True,
    wholly_affordable_is_exclusion=True,
    below_minimum_scale_is_exclusion=False,
    notes=(
        "Brief: \"Sites larger than 500 homes may be relevant where there is evidence of credible phasing "
        "or parcel delivery... classify this honestly as requiring investigation rather than automatically "
        "rejecting\" - implemented identically to Nesten's own oversized-allocation handling (investigate, "
        "never invented as a match) since the brief does not give National Housebuilder the same "
        "large-allocation-is-self-qualifying appetite it explicitly gives Strategic Land Buyer."
    ),
)

HOUSING_ASSOCIATION = BuyerProfile(
    key="housing_association",
    display_name="Housing Association",
    buyer_type="Housing association / registered provider",
    primary_requirement="Affordable residential housing opportunities",
    target_unit_min=50,
    target_unit_max=300,
    # The one profile whose scale is assessed against AFFORDABLE units, not
    # total scheme units - a 400-home scheme with 120 affordable homes is
    # assessed against 120 (see the AFFORDABLE_UNITS constant's own
    # docstring, and app.policy.buyer_matching.MatchingFacts.
    # affordable_unit_count for where that figure comes from).
    scale_metric=AFFORDABLE_UNITS,
    # Brief: "Do not assume the buyer requires: planning permission; adopted
    # allocation; emerging allocation... Where planning status exists,
    # expose it as context" - the widest accepted set of any pilot profile
    # (matching National Housebuilder's), so a classifiable planning
    # position always reads as consistent context rather than "outside
    # this buyer's stated appetite" for a buyer who was never given a
    # stated planning-stage preference at all.
    accepted_planning_states=frozenset({PERMISSION_GRANTED, ADOPTED_ALLOCATION, EMERGING_ALLOCATION}),
    treats_no_activity_as_positive=False,
    large_allocation_is_self_qualifying=False,
    # Brief, Section 8: "Do NOT assume the Housing Association wants or does
    # not want retirement/care/student/supported housing... I have not
    # specified that requirement... do not invent a hard exclusion." A
    # trusted specialist residential development type is preserved as an
    # explicit "unknown/unspecified appetite" note instead - see this
    # profile's own acceptance case (Focus School) in tests/
    # test_buyer_matching.py for the resulting INSUFFICIENT_EVIDENCE (never
    # STRONG_FIT, never NOT_SUITABLE) outcome this produces. Note this flag
    # does NOT reach a genuinely non-residential (employment) allocation -
    # see BuyerProfile.specialist_development_is_exclusion's own docstring.
    specialist_development_is_exclusion=False,
    # Brief, Section 7: "the opposite of the three existing pilot profiles
    # ... 100% affordable is NOT an exclusion. It is potentially highly
    # relevant" - reversed polarity (a positive "matches" reason), not
    # merely a lifted exclusion.
    wholly_affordable_is_exclusion=False,
    # Brief, Section 6: "NOT SUITABLE: ...fewer than 50 affordable homes."
    # Unlike every housebuilder profile (for whom an undersized scheme stays
    # an open question, never excluded), this buyer's own stated floor is a
    # genuine hard requirement - a deliberate, brief-specified behavioural
    # difference, not an oversight.
    below_minimum_scale_is_exclusion=True,
    notes=(
        "Brief: scale is assessed using AFFORDABLE units (50-300), not total scheme units - a 400-home "
        "scheme with 120 affordable homes is potentially relevant, never rejected for exceeding 300 total "
        "units. 100% affordable is explicitly NOT an exclusion for this buyer (the opposite of the other "
        "three profiles). No specialist/retirement development-type exclusion is implemented - the brief "
        "explicitly states this buyer's specialist-product appetite has not been defined, so a specialist "
        "residential development type (e.g. Focus School's mixed_retirement_and_market_housing) is "
        "preserved as an unresolved/unknown fact, never a fabricated hard exclusion. No planning-stage "
        "preference is implemented beyond exposing whatever planning position exists as context (brief: "
        "\"do not assume the buyer requires planning permission/adopted/emerging allocation\"). Allocation- "
        "level (Local Plan) opportunities have no scheme-specific affordable-unit evidence at all (brief: "
        "\"do NOT estimate affordable units by applying Local Plan/NPPF affordable-housing policy "
        "percentages to allocation capacity\") - Housing Association fit for a Local Plan allocation is "
        "therefore INSUFFICIENT_EVIDENCE by design, not a gap in this implementation."
    ),
)

BUYER_PROFILES: dict[str, BuyerProfile] = {
    p.key: p for p in (NESTEN_HOMES, STRATEGIC_LAND_BUYER, NATIONAL_HOUSEBUILDER, HOUSING_ASSOCIATION)
}
BUYER_PROFILE_ORDER: tuple[str, ...] = (
    NESTEN_HOMES.key, STRATEGIC_LAND_BUYER.key, NATIONAL_HOUSEBUILDER.key, HOUSING_ASSOCIATION.key,
)
