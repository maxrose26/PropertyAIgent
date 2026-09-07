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


@dataclass(frozen=True)
class BuyerProfile:
    key: str
    display_name: str
    buyer_type: str
    primary_requirement: str
    target_unit_min: int
    target_unit_max: int
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
    notes: str


NESTEN_HOMES = BuyerProfile(
    key="nesten_homes",
    display_name="Nesten Homes",
    buyer_type="Regional housebuilder",
    primary_requirement="Residential development land",
    target_unit_min=50,
    target_unit_max=100,
    accepted_planning_states=frozenset({PERMISSION_GRANTED, ADOPTED_ALLOCATION, EMERGING_ALLOCATION}),
    treats_no_activity_as_positive=False,
    large_allocation_is_self_qualifying=False,
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
    accepted_planning_states=frozenset({ADOPTED_ALLOCATION, EMERGING_ALLOCATION}),
    treats_no_activity_as_positive=True,
    large_allocation_is_self_qualifying=True,
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
    accepted_planning_states=frozenset({PERMISSION_GRANTED, ADOPTED_ALLOCATION, EMERGING_ALLOCATION}),
    treats_no_activity_as_positive=False,
    large_allocation_is_self_qualifying=False,
    notes=(
        "Brief: \"Sites larger than 500 homes may be relevant where there is evidence of credible phasing "
        "or parcel delivery... classify this honestly as requiring investigation rather than automatically "
        "rejecting\" - implemented identically to Nesten's own oversized-allocation handling (investigate, "
        "never invented as a match) since the brief does not give National Housebuilder the same "
        "large-allocation-is-self-qualifying appetite it explicitly gives Strategic Land Buyer."
    ),
)

BUYER_PROFILES: dict[str, BuyerProfile] = {
    p.key: p for p in (NESTEN_HOMES, STRATEGIC_LAND_BUYER, NATIONAL_HOUSEBUILDER)
}
BUYER_PROFILE_ORDER: tuple[str, ...] = (NESTEN_HOMES.key, STRATEGIC_LAND_BUYER.key, NATIONAL_HOUSEBUILDER.key)
