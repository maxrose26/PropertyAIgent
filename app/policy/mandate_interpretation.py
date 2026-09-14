"""Agent Evaluation Foundation - Mandate Interpretation Policy V1 (narrow
pre-Agent foundation; Product Owner review of the Agent Evaluation Policy
V1 architecture report and its refinement).

A read-only, declarative classification of app.policy.buyer_profiles.
BuyerMandatePolicy's OWN EXISTING fields into six interpretation
categories:

    HARD_CONSTRAINT       - a KNOWN fact contradicting this genuinely
                             excludes the opportunity for this buyer.
    TARGET                - a stated band; sitting outside it is a
                             commercial signal, never a classification
                             blocker on its own.
    PREFERENCE             - a stated leaning that shapes which facts read
                             as positive, never a rejection reason.
    TOLERANCE              - a modifier that widens/relaxes how a TARGET or
                             fact is read for a specific opportunity type.
    EXCLUSION              - a boolean hard-rejection rule, active only
                             when actually configured True for this mandate.
    INVESTIGATION_CONDITION - marks a fact as worth investigating rather
                             than either a match or a rejection.

NO BuyerMandate FIELD IS ADDED, RENAMED, OR CHANGED BY THIS MODULE. This is
a pure interpretation layer over the exact fields Buyer Mandate V2 already
has - see each classifier function's own docstring for the specific
assess_buyer_fit code its classification is grounded in.

CORE PRINCIPLE (Product Owner correction, preserved here structurally): A
TARGET IS NOT AUTOMATICALLY A HARD BOUNDARY. Confirmed directly against
app.policy.buyer_matching.assess_buyer_fit's own scale-handling code: an
oversized scale value NEVER sets does_not_match or the blocking_unknown
flag for ANY current mandate - it is always read into `unknown`/
`investigate` with is_investigative_exception=True. There is currently NO
"above_maximum_scale_is_exclusion"-equivalent field on BuyerMandatePolicy
at all (confirmed by inspection) - the maximum side of target_unit_min/
target_unit_max is TARGET-with-TOLERANCE for every mandate that exists
today, full stop. This module documents that as a fact about the current
mandate structure, not a design choice a future mandate could not
override - see classify_scale's own docstring for the one known schema
limitation this implies (Q7 of the architecture report): there is no way,
today, to express a genuine hard maximum. This module does NOT add one.

ACQUISITION TYPE IS DELIBERATELY NOT CLASSIFIED HERE (Product Owner
correction, Section 8): app.policy.buyer_profiles.BuyerMandatePolicy.
acquisition_types is an ACQUISITION OBJECTIVE / INTERPRETATION SELECTOR,
not a constraint/preference dimension - it selects WHICH commercial
interpretation policy (see app.policy.acquisition_type_interpretation)
governs reasoning about a given opportunity, rather than itself
constraining or preferring anything the way the six categories above do.
resolve_acquisition_types below exposes it as a plain read, deliberately
outside the six-category classification.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.policy.buyer_profiles import (
    AFFORDABLE_UNITS,
    BuyerMandatePolicy,
    DEVELOPMENT_STATE_UNSPECIFIED,
    GEOGRAPHY_COUNCILS,
    GEOGRAPHY_UNSPECIFIED,
)

MANDATE_INTERPRETATION_POLICY_VERSION = 1

# --- The six interpretation categories --------------------------------------

HARD_CONSTRAINT = "HARD_CONSTRAINT"
TARGET = "TARGET"
PREFERENCE = "PREFERENCE"
TOLERANCE = "TOLERANCE"
EXCLUSION = "EXCLUSION"
INVESTIGATION_CONDITION = "INVESTIGATION_CONDITION"

INTERPRETATION_CATEGORIES = frozenset({
    HARD_CONSTRAINT, TARGET, PREFERENCE, TOLERANCE, EXCLUSION, INVESTIGATION_CONDITION,
})


@dataclass(frozen=True)
class MandateDimensionInterpretation:
    """One BuyerMandatePolicy dimension's own interpretation, for THIS
    specific policy instance. `active` distinguishes "this dimension is
    architecturally an EXCLUSION/HARD_CONSTRAINT" from "this dimension is
    currently configured to actually exclude/constrain for this buyer" -
    e.g. specialist_development_is_exclusion is an EXCLUSION-category
    dimension on every mandate, but `active` is only True where the
    mandate's own boolean is True."""

    dimension: str
    category: str
    active: bool
    explanation: str

    def __post_init__(self) -> None:
        if self.category not in INTERPRETATION_CATEGORIES:
            raise ValueError(f"category {self.category!r} is not one of {sorted(INTERPRETATION_CATEGORIES)}")


def classify_scale(policy: BuyerMandatePolicy) -> tuple[MandateDimensionInterpretation, MandateDimensionInterpretation]:
    """target_unit_min/target_unit_max, split into two independent
    dimensions - grounded directly in app.policy.buyer_matching.
    assess_buyer_fit's own scale-handling branch (search that module for
    "Unit-range assessment"):

    - The MINIMUM is a TARGET by default (a known below-minimum scale reads
      into `unknown`, explicitly commented in that code as "a target range
      is not automatically a hard constraint... never missing evidence"),
      and becomes a HARD_CONSTRAINT only when profile.below_minimum_scale_
      is_exclusion is True (Housing Association is the one current mandate
      where this is active - a scheme below the affordable-unit minimum is
      does_not_match there, not merely unknown).
    - The MAXIMUM is ALWAYS TARGET-with-TOLERANCE for every mandate that
      exists today - there is no equivalent exclusion field for the
      maximum side at all. An oversized value is read into `unknown`/
      `investigate` with is_investigative_exception=True, NEVER
      does_not_match, regardless of profile. See this module's own
      docstring for the one known schema gap this implies for a
      hypothetical future mandate needing a genuine hard ceiling - not
      addressed by this module."""
    metric_label = "affordable homes" if policy.scale_metric == AFFORDABLE_UNITS else "total homes"

    minimum = MandateDimensionInterpretation(
        dimension="target_unit_min",
        category=HARD_CONSTRAINT if policy.below_minimum_scale_is_exclusion else TARGET,
        active=policy.below_minimum_scale_is_exclusion,
        explanation=(
            f"A scheme below {policy.target_unit_min} {metric_label} is a genuine hard exclusion for this buyer."
            if policy.below_minimum_scale_is_exclusion else
            f"A scheme below {policy.target_unit_min} {metric_label} is a soft/contextual signal for this buyer, "
            f"never a disqualifying fact on its own."
        ),
    )
    maximum = MandateDimensionInterpretation(
        dimension="target_unit_max",
        category=TARGET,
        active=False,
        explanation=(
            f"A scheme above {policy.target_unit_max} {metric_label} is a soft/contextual signal, worth "
            f"investigating (e.g. for a suitable phase/parcel), never a disqualifying fact on its own - no current "
            f"mandate has a hard maximum, and this module does not add one."
        ),
    )
    return minimum, maximum


def classify_accepted_planning_states(policy: BuyerMandatePolicy) -> MandateDimensionInterpretation:
    """PREFERENCE - the BuyerMandatePolicy class docstring states this
    explicitly: absence from accepted_planning_states is "NEVER treated as
    a hard exclusion" by any current mandate."""
    return MandateDimensionInterpretation(
        dimension="accepted_planning_states", category=PREFERENCE, active=bool(policy.accepted_planning_states),
        explanation="A planning state outside this set is a soft signal (unknown/context), never a disqualifying fact on its own.",
    )


def classify_specialist_development_exclusion(policy: BuyerMandatePolicy) -> MandateDimensionInterpretation:
    """EXCLUSION - a literal boolean hard-rejection rule in assess_buyer_fit
    (a confirmed specialist development triggers does_not_match whenever
    True)."""
    return MandateDimensionInterpretation(
        dimension="specialist_development_is_exclusion", category=EXCLUSION,
        active=policy.specialist_development_is_exclusion,
        explanation="A confirmed specialist development is a hard exclusion for this buyer." if policy.specialist_development_is_exclusion
        else "Specialist development status is not configured as an exclusion for this buyer.",
    )


def classify_wholly_affordable_exclusion(policy: BuyerMandatePolicy) -> MandateDimensionInterpretation:
    """EXCLUSION - same pattern as specialist_development_is_exclusion."""
    return MandateDimensionInterpretation(
        dimension="wholly_affordable_is_exclusion", category=EXCLUSION,
        active=policy.wholly_affordable_is_exclusion,
        explanation="A confirmed wholly-affordable scheme is a hard exclusion for this buyer." if policy.wholly_affordable_is_exclusion
        else "Wholly-affordable status is not configured as an exclusion for this buyer.",
    )


def classify_treats_no_activity_as_positive(policy: BuyerMandatePolicy) -> MandateDimensionInterpretation:
    """PREFERENCE, directional only - only ever appends to `matches`/
    `unknown` in assess_buyer_fit, never to `does_not_match`."""
    return MandateDimensionInterpretation(
        dimension="treats_no_activity_as_positive", category=PREFERENCE, active=policy.treats_no_activity_as_positive,
        explanation="No identified planning activity on a strategic land allocation reads as a positive signal for this buyer." if policy.treats_no_activity_as_positive
        else "This buyer has not stated a preference for early-stage, activity-free allocations.",
    )


def classify_large_allocation_self_qualifying(policy: BuyerMandatePolicy) -> MandateDimensionInterpretation:
    """TOLERANCE - modifies how an oversized STRATEGIC_LAND opportunity's
    own scale TARGET (see classify_scale) is read, without itself being a
    target or an exclusion."""
    return MandateDimensionInterpretation(
        dimension="large_allocation_is_self_qualifying", category=TOLERANCE, active=policy.large_allocation_is_self_qualifying,
        explanation="An oversized strategic land allocation is read as a meaningful position in its own right for this buyer, independent of a confirmed smaller parcel." if policy.large_allocation_is_self_qualifying
        else "An oversized strategic land allocation is read the same as any other oversized opportunity for this buyer (see target_unit_max).",
    )


def classify_geography(policy: BuyerMandatePolicy) -> MandateDimensionInterpretation:
    """HARD_CONSTRAINT only when geography_scope == GEOGRAPHY_COUNCILS -
    assess_buyer_fit's own code comment states this literally: "HARD
    CONSTRAINT (COUNCILS mismatch only)". GEOGRAPHY_UNSPECIFIED/
    GEOGRAPHY_ALL_CURRENT_COVERAGE contribute no reason at all - no
    constraint of any kind."""
    active = policy.geography_scope == GEOGRAPHY_COUNCILS
    return MandateDimensionInterpretation(
        dimension="geography_scope", category=HARD_CONSTRAINT, active=active,
        explanation=(
            f"A council outside {sorted(policy.geography_councils)} is a hard exclusion for this buyer." if active
            else "This buyer has not stated a geographic boundary that excludes anything."
        ),
    )


def classify_development_state_appetite(policy: BuyerMandatePolicy) -> MandateDimensionInterpretation:
    """PREFERENCE - the vocabulary itself (UNSPECIFIED/UNCOMMENCED_
    PREFERRED/UNDERWAY_ACCEPTABLE/UNDERWAY_PREFERRED) has no exclusionary
    value at all (confirmed by inspection of app.policy.buyer_profiles -
    there is no "UNDERWAY_EXCLUDED" or equivalent)."""
    return MandateDimensionInterpretation(
        dimension="development_state_appetite", category=PREFERENCE,
        active=policy.development_state_appetite != DEVELOPMENT_STATE_UNSPECIFIED,
        explanation=f"This buyer's stated development-state appetite is {policy.development_state_appetite!r} - a leaning, never an exclusion.",
    )


def classify_control_appetite(policy: BuyerMandatePolicy) -> MandateDimensionInterpretation:
    """INVESTIGATION_CONDITION - this is already almost exactly the
    concept: the field's own governing comment in app.policy.buyer_profiles
    calls it a "COMMERCIAL WILLINGNESS-TO-INVESTIGATE vocabulary", entirely
    distinct from Gate 2C's own evidence-coverage vocabulary."""
    return MandateDimensionInterpretation(
        dimension="control_appetite", category=INVESTIGATION_CONDITION, active=bool(policy.control_appetite),
        explanation=f"This buyer is willing to investigate: {sorted(policy.control_appetite) or '(none stated)'} rather than treating unresolved ownership/control as a rejection reason.",
    )


@dataclass(frozen=True)
class MandateInterpretation:
    """The complete Mandate Interpretation Policy V1 reading of one
    BuyerMandatePolicy - every dimension EXCEPT acquisition_types (see this
    module's own docstring for why that one is deliberately excluded and
    read via resolve_acquisition_types instead)."""

    policy_version: int
    scale_minimum: MandateDimensionInterpretation
    scale_maximum: MandateDimensionInterpretation
    accepted_planning_states: MandateDimensionInterpretation
    specialist_development_exclusion: MandateDimensionInterpretation
    wholly_affordable_exclusion: MandateDimensionInterpretation
    treats_no_activity_as_positive: MandateDimensionInterpretation
    large_allocation_self_qualifying: MandateDimensionInterpretation
    geography: MandateDimensionInterpretation
    development_state_appetite: MandateDimensionInterpretation
    control_appetite: MandateDimensionInterpretation


def classify_mandate(policy: BuyerMandatePolicy) -> MandateInterpretation:
    """The one entry point a future Agent Evaluation Policy should call -
    every dimension's interpretation, for this specific mandate, in one
    place. Pure function of the policy; no I/O, no database access."""
    scale_minimum, scale_maximum = classify_scale(policy)
    return MandateInterpretation(
        policy_version=MANDATE_INTERPRETATION_POLICY_VERSION,
        scale_minimum=scale_minimum,
        scale_maximum=scale_maximum,
        accepted_planning_states=classify_accepted_planning_states(policy),
        specialist_development_exclusion=classify_specialist_development_exclusion(policy),
        wholly_affordable_exclusion=classify_wholly_affordable_exclusion(policy),
        treats_no_activity_as_positive=classify_treats_no_activity_as_positive(policy),
        large_allocation_self_qualifying=classify_large_allocation_self_qualifying(policy),
        geography=classify_geography(policy),
        development_state_appetite=classify_development_state_appetite(policy),
        control_appetite=classify_control_appetite(policy),
    )


def resolve_acquisition_types(policy: BuyerMandatePolicy) -> frozenset[str]:
    """Deliberately NOT part of MandateInterpretation's six categories
    (Product Owner correction, Section 8) - a plain read of the mandate's
    own stated acquisition objectives, for a caller to hand to app.policy.
    acquisition_type_interpretation's own per-type commercial principles."""
    return policy.acquisition_types
