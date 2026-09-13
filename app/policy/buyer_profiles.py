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

Buyer Mandate V2, Phase A (Buyer/Mandate Domain Separation) - the
dataclass below is renamed from BuyerProfile to BuyerMandatePolicy. The
repository previously had two unrelated classes both literally named
BuyerProfile (this pure dataclass, and app.db.models.BuyerProfile, the
now-legacy persisted row) - a genuine naming collision the Phase A
investigation was asked to resolve where it could be done safely. This
class itself is UNCHANGED in every other respect: still a pure, DB-free,
frozen dataclass; still exactly the same fields app.policy.buyer_matching.
assess_buyer_fit has always read; still never queried, never persisted
directly. It is the PURE MATCHING POLICY object in the three-way Buyer
(identity) / BuyerMandate (persisted strategy) / BuyerMandatePolicy (pure
matching policy) naming now used consistently across this domain - see
app.policy.buyer_profile_store's own module docstring for how a
persisted BuyerMandate row becomes one of these."""
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
#   - PLANNING_ACTIVE_PROPOSAL (Gate 2B-2B.1): a live, substantive planning
#     application exists for this opportunity but has not yet been
#     decided (app.reporting.scheme_reconciliation.OperativePlanningFacts
#     resolved one or more `active_positions`, with no operative consent).
#     Distinct from OTHER_OR_UNKNOWN - "we know there is a pending
#     application" is real, positive information, not "we couldn't
#     classify this" - but membership in no pilot profile's own
#     accepted_planning_states today, so it behaves exactly like
#     OTHER_OR_UNKNOWN does for classification purposes (an honest
#     "outside this buyer's stated appetite, not disqualifying" note,
#     never a fabricated match, never a hard exclusion) until a future
#     profile explicitly opts in.
PERMISSION_GRANTED = "permission_granted"
ADOPTED_ALLOCATION = "adopted_allocation"
EMERGING_ALLOCATION = "emerging_allocation"
OTHER_OR_UNKNOWN = "other_or_unknown"
PLANNING_ACTIVE_PROPOSAL = "planning_active_proposal"

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
# assessed against 120, not 400. Generic on BuyerMandatePolicy rather than a
# Housing-Association-only branch in app.policy.buyer_matching, per the
# amendment brief's own "do NOT implement this as a one-off hard-coded
# exception if the existing structure can safely support a generic
# concept" instruction.
TOTAL_UNITS = "total_units"
AFFORDABLE_UNITS = "affordable_units"

# --- Buyer Mandate V2, Phase B1 (Structured Mandate Domain Expansion) -------
#
# Four new STRUCTURAL dimensions added to BuyerMandatePolicy below. Per the
# Phase B1 brief's own explicit instruction, none of these is read by
# app.policy.buyer_matching.assess_buyer_fit yet - that activation is
# deliberately deferred to Phase B2, so every existing test/production
# buyer-fit outcome is completely unaffected by their presence. They exist
# now so BuyerMandate can be fingerprinted, seeded, migrated and tested
# against their FINAL persisted shape before any matching logic ever reads
# them - avoiding a second, disruptive schema/fingerprint change in B2.

# --- A. Geography ------------------------------------------------------------
#
# Deliberately council_code-based (never a polygon/radius/postcode-sector/
# travel-time model) - council_code is already the platform's own native
# administrative geography (Council.code, Application.council_code,
# LocalPlan.council_code, ...), already populated on every relevant row,
# and the ten-council Greater Manchester footprint is the platform's entire
# current evidence coverage. A three-value SCOPE, not a bare set, because
# "no councils configured" and "every current council is acceptable" are
# genuinely different commercial facts that must never collapse into each
# other (Phase B1 brief, Section 5/19 - "unknown/unconfigured geography
# must not accidentally become 'all councils'"):
#   - GEOGRAPHY_UNSPECIFIED: no geography decision has been made for this
#     mandate yet. The safe default for any BRAND NEW mandate a future
#     Phase B3 creation flow produces before a user has chosen anything -
#     never silently treated as "everywhere" once geography is actually
#     wired into matching (Phase B2+).
#   - GEOGRAPHY_ALL_CURRENT_COVERAGE: an explicit statement that this buyer
#     has no geographic restriction WITHIN whatever the platform currently
#     covers - the correct, honest migration value for the four existing
#     pilot mandates (none of their own original briefs stated ANY
#     geographic restriction - see each mandate's own notes below), and
#     genuinely different from GEOGRAPHY_UNSPECIFIED: this is a stated fact
#     about the buyer's own appetite, not an unanswered question. It is
#     explicitly NOT "all councils in England and Wales" - it tracks
#     whatever the platform actually covers today, without needing to be
#     re-stated every time a new council is onboarded.
#   - GEOGRAPHY_COUNCILS: an explicit, non-empty set of council_code values
#     (geography_councils below) - the buyer wants only these.
GEOGRAPHY_UNSPECIFIED = "UNSPECIFIED"
GEOGRAPHY_ALL_CURRENT_COVERAGE = "ALL_CURRENT_COVERAGE"
GEOGRAPHY_COUNCILS = "COUNCILS"
GEOGRAPHY_SCOPES = frozenset({GEOGRAPHY_UNSPECIFIED, GEOGRAPHY_ALL_CURRENT_COVERAGE, GEOGRAPHY_COUNCILS})

# --- B. Acquisition Type ------------------------------------------------------
#
# WHAT THE BUYER IS TRYING TO ACQUIRE - deliberately NOT the same concept
# as app.policy.buyer_matching.STRATEGIC_LAND/PLANNING_DELIVERY
# (opportunity_type), which describes the CANDIDATE'S OWN SITUATION and is
# buyer-independent (see app.reporting.opportunity_universe's own module
# docstring). One development can be a PLANNING_DELIVERY opportunity to
# every buyer while three different buyers want three different things
# from it (land control / the affordable package / the completed homes) -
# collapsing the two concepts would make that impossible to express.
#
# Phase B1 brief, Section 6: the smallest useful V1 vocabulary, not the
# full long-term taxonomy (forward purchase/forward funding/completed
# homes/SFH/BTR/portfolio remain future refinements of
# DEVELOPMENT_HOMES_ACQUISITION, introduced only if a real buyer needs the
# distinction - never speculatively now).
LAND_SITE_ACQUISITION = "LAND_SITE_ACQUISITION"
STRATEGIC_LAND_CONTROL = "STRATEGIC_LAND_CONTROL"
AFFORDABLE_HOUSING_PACKAGE = "AFFORDABLE_HOUSING_PACKAGE"
DEVELOPMENT_HOMES_ACQUISITION = "DEVELOPMENT_HOMES_ACQUISITION"
ACQUISITION_TYPES = frozenset({
    LAND_SITE_ACQUISITION, STRATEGIC_LAND_CONTROL, AFFORDABLE_HOUSING_PACKAGE, DEVELOPMENT_HOMES_ACQUISITION,
})

# --- C. Development-State Appetite -------------------------------------------
#
# COMMERCIAL PREFERENCE, never a redefinition of the factual development-
# state source (app.pipeline.lapse_tracking.classify_build_status's own
# "underway"/"partially_complete"/"complete"/"unknown" vocabulary - inspected
# directly, not guessed at, before choosing this vocabulary). Note that
# vocabulary has NO positive "not started" state at all - only "underway or
# further" vs. "unknown" (no evidence either way), consistent with Unknown
# Must Remain Unknown; a future Phase B2 mapping of UNCOMMENCED_PREFERRED
# must therefore match against "no commencement evidence" (unknown), never
# against a confirmed-not-started fact that the evidence layer cannot
# actually produce.
#
# A single ordered scale (not a multi-select) - the Phase B1 brief's own
# example land-buyer-vs-institutional-buyer cases described one directional
# preference per buyer, never "accepts uncommenced AND prefers underway"
# simultaneously:
#   - DEVELOPMENT_STATE_UNSPECIFIED: no preference stated yet.
#   - UNCOMMENCED_PREFERRED: this buyer's own stated brief favours a site
#     with no development activity yet (Nesten Homes/Strategic Land
#     Buyer/National Housebuilder - see each mandate's own notes for the
#     evidence this default is grounded in).
#   - UNDERWAY_ACCEPTABLE: development progress does not disqualify, but
#     is not itself a positive signal either (Housing Association - the
#     affordable package may remain acquirable regardless of who is
#     delivering the market housing).
#   - UNDERWAY_PREFERRED: development progress is itself a positive signal
#     (an institutional/SFH/BTR-style buyer's own forward-funding/
#     completed-homes interest - not persisted for any pilot buyer in B1,
#     since no such buyer exists yet; reserved for that future case).
DEVELOPMENT_STATE_UNSPECIFIED = "UNSPECIFIED"
UNCOMMENCED_PREFERRED = "UNCOMMENCED_PREFERRED"
UNDERWAY_ACCEPTABLE = "UNDERWAY_ACCEPTABLE"
UNDERWAY_PREFERRED = "UNDERWAY_PREFERRED"
DEVELOPMENT_STATE_APPETITES = frozenset({
    DEVELOPMENT_STATE_UNSPECIFIED, UNCOMMENCED_PREFERRED, UNDERWAY_ACCEPTABLE, UNDERWAY_PREFERRED,
})

# --- D. Control / Ownership Appetite -----------------------------------------
#
# COMMERCIAL WILLINGNESS-TO-INVESTIGATE vocabulary - deliberately its own
# words, sharing NO string with Gate 2C's own evidence-coverage/ownership-
# state vocabulary (app.reporting.acquisition_position's
# COVERAGE_*/OWNERSHIP_*/CERTIFICATE_* constants). Gate 2C answers "what
# evidence do we have"; this answers "what situations is this buyer willing
# to consider" - a buyer's own appetite can never upgrade Gate 2C's
# genuinely unknown evidence into confirmed control, and Phase B2's future
# mapping between the two remains free to be designed without either
# vocabulary constraining the other. A bounded multi-select (not a single
# scale) - the Phase B1 brief's own examples are independent yes/no
# willingnesses, not points on one ordered axis:
#   - DEVELOPER_LED_ACCEPTABLE: a developer/applicant-led situation does not
#     disqualify this buyer's interest.
#   - THIRD_PARTY_INTEREST_ACCEPTABLE: evidence of a third-party ownership
#     interest (e.g. a Certificate B declaration) does not disqualify.
#   - UNRESOLVED_OWNERSHIP_INVESTIGATABLE: genuinely unknown/unresolved
#     ownership is worth investigating rather than an automatic pass.
#   - PARTIAL_SITE_CONTROL_ACCEPTABLE: this buyer's own acquisition type
#     does not require controlling the whole site (e.g. an affordable-
#     package or completed-homes acquisition).
# An empty set means no appetite has been stated - never treated as "any
# situation is acceptable" once this is wired into matching (Phase B2).
DEVELOPER_LED_ACCEPTABLE = "DEVELOPER_LED_ACCEPTABLE"
THIRD_PARTY_INTEREST_ACCEPTABLE = "THIRD_PARTY_INTEREST_ACCEPTABLE"
UNRESOLVED_OWNERSHIP_INVESTIGATABLE = "UNRESOLVED_OWNERSHIP_INVESTIGATABLE"
PARTIAL_SITE_CONTROL_ACCEPTABLE = "PARTIAL_SITE_CONTROL_ACCEPTABLE"
CONTROL_APPETITES = frozenset({
    DEVELOPER_LED_ACCEPTABLE, THIRD_PARTY_INTEREST_ACCEPTABLE, UNRESOLVED_OWNERSHIP_INVESTIGATABLE,
    PARTIAL_SITE_CONTROL_ACCEPTABLE,
})


def _require_membership(values: frozenset[str], allowed: frozenset[str], *, field_name: str) -> None:
    invalid = values - allowed
    if invalid:
        raise ValueError(f"{field_name} contains unrecognised value(s): {sorted(invalid)} (allowed: {sorted(allowed)})")


@dataclass(frozen=True)
class BuyerMandatePolicy:
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
    # --- Buyer Mandate V2, Phase B1 fields (Sections A-D above) - NOT read
    # by app.policy.buyer_matching.assess_buyer_fit yet (Phase B2). Present
    # here, fingerprinted, seeded, migrated and tested for their final
    # persisted shape ahead of that activation.
    geography_scope: str = GEOGRAPHY_UNSPECIFIED
    geography_councils: frozenset[str] = field(default_factory=frozenset)
    acquisition_types: frozenset[str] = field(default_factory=frozenset)
    development_state_appetite: str = DEVELOPMENT_STATE_UNSPECIFIED
    control_appetite: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.geography_scope not in GEOGRAPHY_SCOPES:
            raise ValueError(f"geography_scope {self.geography_scope!r} is not one of {sorted(GEOGRAPHY_SCOPES)}")
        if self.geography_scope == GEOGRAPHY_COUNCILS and not self.geography_councils:
            raise ValueError("geography_scope=COUNCILS requires at least one council code in geography_councils")
        if self.geography_scope != GEOGRAPHY_COUNCILS and self.geography_councils:
            raise ValueError("geography_councils must be empty unless geography_scope=COUNCILS")
        _require_membership(self.acquisition_types, ACQUISITION_TYPES, field_name="acquisition_types")
        if self.development_state_appetite not in DEVELOPMENT_STATE_APPETITES:
            raise ValueError(
                f"development_state_appetite {self.development_state_appetite!r} is not one of "
                f"{sorted(DEVELOPMENT_STATE_APPETITES)}"
            )
        _require_membership(self.control_appetite, CONTROL_APPETITES, field_name="control_appetite")


NESTEN_HOMES = BuyerMandatePolicy(
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
    # Phase B1 defaults - structural only, NOT yet read by assess_buyer_fit.
    # Geography: the original brief never stated any geographic restriction
    # at all - ALL_CURRENT_COVERAGE is the honest translation of "no
    # restriction stated" into the new field, never a fabricated council
    # list.
    geography_scope=GEOGRAPHY_ALL_CURRENT_COVERAGE,
    geography_councils=frozenset(),
    # Acquisition type: the brief's own primary_requirement ("Residential
    # development land") is a land/site acquisition, not a strategic-land-
    # control or affordable-package strategy.
    acquisition_types=frozenset({LAND_SITE_ACQUISITION}),
    # Development-state appetite: not stated verbatim in the original
    # brief, but the Phase B1 brief itself records "Land buyer: uncommenced
    # tends to be more relevant" as established product direction, and
    # Nesten's own brief is unambiguously a land/site buyer - extrapolated,
    # not verbatim, and documented as such.
    development_state_appetite=UNCOMMENCED_PREFERRED,
    # Control appetite: the Phase B1 brief's own explicit example for this
    # buyer ("ownership/control uncertainty may still justify investigation
    # rather than automatic rejection").
    control_appetite=frozenset({UNRESOLVED_OWNERSHIP_INVESTIGATABLE}),
)

STRATEGIC_LAND_BUYER = BuyerMandatePolicy(
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
    # Phase B1 defaults - structural only, NOT yet read by assess_buyer_fit.
    geography_scope=GEOGRAPHY_ALL_CURRENT_COVERAGE,
    geography_councils=frozenset(),
    acquisition_types=frozenset({STRATEGIC_LAND_CONTROL}),
    # Development-state appetite: this buyer's own EXISTING
    # treats_no_activity_as_positive=True flag already states, in effect,
    # exactly this ("no development activity can be positive context") -
    # the most directly-evidenced default of any of the four mandates,
    # not an extrapolation.
    development_state_appetite=UNCOMMENCED_PREFERRED,
    # Control appetite: the Phase B1 brief's own explicit example
    # ("ownership may be unknown early and should not automatically
    # exclude the opportunity") - also consistent with this buyer's own
    # existing large_allocation_is_self_qualifying appetite for accepting
    # uncertainty other buyers would treat as an open question.
    control_appetite=frozenset({UNRESOLVED_OWNERSHIP_INVESTIGATABLE}),
)

NATIONAL_HOUSEBUILDER = BuyerMandatePolicy(
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
    # Phase B1 defaults - structural only, NOT yet read by assess_buyer_fit.
    geography_scope=GEOGRAPHY_ALL_CURRENT_COVERAGE,
    geography_councils=frozenset(),
    # Acquisition type: brief's own primary_requirement ("Large residential
    # housing sites capable of meaningful delivery scale") is a land/site
    # acquisition, same as Nesten - not a completed-homes/forward-purchase
    # strategy, which this buyer's brief never mentions.
    acquisition_types=frozenset({LAND_SITE_ACQUISITION}),
    # Development-state appetite: extrapolated from the same "land buyer"
    # product direction as Nesten (Phase B1 brief) - this buyer is also
    # unambiguously a land/site buyer, not verbatim in its own brief.
    development_state_appetite=UNCOMMENCED_PREFERRED,
    # Control appetite: the Phase B1 brief's own explicit instruction for
    # this buyer is "do not invent assumptions beyond existing brief" -
    # its own brief never discussed ownership/control appetite at all,
    # unlike the other three, so this is left genuinely unconfigured
    # (empty), never guessed at.
    control_appetite=frozenset(),
)

HOUSING_ASSOCIATION = BuyerMandatePolicy(
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
    # see BuyerMandatePolicy.specialist_development_is_exclusion's own docstring.
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
    # Phase B1 defaults - structural only, NOT yet read by assess_buyer_fit.
    geography_scope=GEOGRAPHY_ALL_CURRENT_COVERAGE,
    geography_councils=frozenset(),
    # Acquisition type: brief's own primary_requirement ("Affordable
    # residential housing opportunities") is unambiguously an affordable-
    # package acquisition, not a land/site or strategic-land strategy.
    acquisition_types=frozenset({AFFORDABLE_HOUSING_PACKAGE}),
    # Development-state appetite: the Phase B1 brief's own explicit example
    # for this buyer ("HA: underway may remain acceptable") - ACCEPTABLE,
    # not PREFERRED, since no evidence states underway is actually
    # preferred, only that it does not disqualify.
    development_state_appetite=UNDERWAY_ACCEPTABLE,
    # Control appetite: the Phase B1 brief's own explicit example
    # ("developer-led control is clearly not inherently disqualifying
    # because the acquisition may concern the affordable package").
    control_appetite=frozenset({DEVELOPER_LED_ACCEPTABLE}),
)

BUYER_PROFILES: dict[str, BuyerMandatePolicy] = {
    p.key: p for p in (NESTEN_HOMES, STRATEGIC_LAND_BUYER, NATIONAL_HOUSEBUILDER, HOUSING_ASSOCIATION)
}
BUYER_PROFILE_ORDER: tuple[str, ...] = (
    NESTEN_HOMES.key, STRATEGIC_LAND_BUYER.key, NATIONAL_HOUSEBUILDER.key, HOUSING_ASSOCIATION.key,
)
