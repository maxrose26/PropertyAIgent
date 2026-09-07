"""Buyer Profiles V1 - deterministic buyer-fit classification (Phase 1
pilot). Sits strictly downstream of existing opportunity detection: reads
already-computed, already-trusted facts (app.reporting.allocation_
development_coverage, app.reporting.allocation_discovery, SchemeIntelligence)
and classifies them against a app.policy.buyer_profiles.BuyerProfile - it
never re-derives a fact those modules already own, never calls an LLM, and
never produces a numeric score.

Architecture (see the Buyer Profiles V1 investigation report for the full
audit this implements):

    Verified planning/Local Plan intelligence
        -> existing deterministic opportunity detection (unchanged)
        -> MatchingFacts (this module - a thin, safe reader)
        -> BuyerProfile (app.policy.buyer_profiles - fixed pilot config)
        -> assess_buyer_fit (this module - deterministic classification)
        -> BuyerFitAssessment (consumed by opportunity_feed.py / the UI)

Classification is one of STRONG_FIT / NOT_SUITABLE / INSUFFICIENT_EVIDENCE,
plus an orthogonal is_investigative_exception flag - the brief is explicit
that INSUFFICIENT_EVIDENCE and "worth investigating despite being outside
the normal range" answer different questions and must not be forced into
one mutually-exclusive enum value.

Every reason string is generated from one of the rules below, grounded in
a real field this module read - never freeform text, never AI-generated.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.policy.buyer_profiles import (
    ADOPTED_ALLOCATION,
    EMERGING_ALLOCATION,
    OTHER_OR_UNKNOWN,
    PERMISSION_GRANTED,
    SPECIALIST_DEVELOPMENT_TYPES,
    WHOLLY_AFFORDABLE_THRESHOLD,
    BuyerProfile,
)
from app.reporting.allocation_development_coverage import NO_IDENTIFIED_ACTIVITY

STRATEGIC_LAND = "strategic_land"
PLANNING_DELIVERY = "planning_delivery"

STRONG_FIT = "STRONG_FIT"
NOT_SUITABLE = "NOT_SUITABLE"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class MatchingFacts:
    """The minimum safe attribute set for buyer matching, for ONE
    opportunity - the buyer-matching equivalent of app.reporting.
    allocation_discovery.build_matching_attributes, extended to also cover
    Application/SchemeIntelligence-backed (planning/delivery) opportunities,
    which that function does not reach. Every field is read verbatim from
    an already-trusted source; nothing here is computed or inferred beyond
    a plain lookup - see the two build_*_matching_facts functions below for
    exactly which field each one comes from."""
    opportunity_type: str  # STRATEGIC_LAND | PLANNING_DELIVERY
    unit_count: int | None  # the single most representative scale figure available (see extractors)
    development_type_raw: str | None
    is_specialist_development: bool | None  # None = genuinely unknown, never inferred as False
    affordable_percentage: float | None
    affordable_percentage_trusted: bool
    planning_state: str  # one of app.policy.buyer_profiles' four planning-state constants
    has_identified_planning_activity: bool | None  # None = not applicable/not determined
    has_phasing_evidence: bool
    matched_to_site: bool  # allocations only - whether AllocationSiteRelationship/matched_site_id exists at all


def build_strategic_land_matching_facts(allocation, coverage, phasing) -> MatchingFacts:
    """allocation: a LocalPlanSite ORM row. coverage: a DevelopmentCoverageResult
    (app.reporting.allocation_development_coverage - already computed,
    never re-derived here). phasing: the same dict app.reporting.
    opportunity_feed/allocation_discovery already builds
    ({"classification": ..., "evidence": [...]})."""
    from app.reporting.allocation_discovery import PLAN_STATUS_META

    # Scale: prefer the stated maximum (the ceiling a buyer would actually
    # need to fit within), falling back to the minimum when no maximum is
    # stated - never averaged, never invented when both are absent.
    unit_count = allocation.maximum_capacity or allocation.minimum_dwellings

    # intended_use only ever distinguishes residential/mixed_use/employment/
    # gypsy_traveller_accommodation (app.reporting.allocation_discovery.
    # INTENDED_USE_LABELS) - it carries no retirement/student/care
    # granularity at all, unlike SchemeIntelligence.development_type below.
    # A non-residential-primary use is a genuine, trusted "not general-needs
    # housing" signal; residential/mixed_use/unknown all honestly say
    # nothing about specialist housing risk, so is_specialist stays None
    # (unknown) rather than being guessed at False.
    is_specialist = True if allocation.intended_use == "employment" else None

    plan_meta = PLAN_STATUS_META.get(allocation.plan_status, PLAN_STATUS_META.get(None))
    bucket = plan_meta["bucket"] if plan_meta else None
    if bucket == "adopted":
        planning_state = ADOPTED_ALLOCATION
    elif bucket == "emerging":
        planning_state = EMERGING_ALLOCATION
    else:
        planning_state = OTHER_OR_UNKNOWN

    has_activity = None
    if coverage is not None:
        has_activity = coverage.development_coverage_classification != NO_IDENTIFIED_ACTIVITY

    has_phasing = bool(phasing and phasing.get("evidence"))

    return MatchingFacts(
        opportunity_type=STRATEGIC_LAND,
        unit_count=unit_count,
        development_type_raw=allocation.intended_use,
        is_specialist_development=is_specialist,
        # Allocation-level affordable-housing percentage is not tracked
        # anywhere on LocalPlanSite today (confirmed: no such column) -
        # always genuinely unknown for strategic-land opportunities, never
        # assumed 0%.
        affordable_percentage=None,
        affordable_percentage_trusted=False,
        planning_state=planning_state,
        has_identified_planning_activity=has_activity,
        has_phasing_evidence=has_phasing,
        matched_to_site=allocation.matched_site_id is not None,
    )


def build_planning_delivery_matching_facts(scheme_intelligence) -> MatchingFacts:
    """scheme_intelligence: a SchemeIntelligence ORM row for the
    representative application behind a planning/delivery opportunity
    card (already selected by app.ui.common.pick_representative_application
    elsewhere in the platform - this function does not pick one itself).
    May be None (no SchemeIntelligence extracted yet for this application) -
    every fact then reads as genuinely unknown, never guessed."""
    if scheme_intelligence is None:
        return MatchingFacts(
            opportunity_type=PLANNING_DELIVERY, unit_count=None, development_type_raw=None,
            is_specialist_development=None, affordable_percentage=None, affordable_percentage_trusted=False,
            # Every planning/delivery opportunity card in this platform is
            # already sourced from a granted decision (see app.reporting.
            # dashboard's _approaching_lapse_cards/_undeveloped_phase_cards,
            # both gated on is_granted_decision before a card is ever built) -
            # this is a fact already established upstream, not re-derived here.
            planning_state=PERMISSION_GRANTED, has_identified_planning_activity=True,
            has_phasing_evidence=False, matched_to_site=True,
        )

    dev_type = scheme_intelligence.development_type
    is_specialist = (dev_type in SPECIALIST_DEVELOPMENT_TYPES) if dev_type else None

    affordable_pct = scheme_intelligence.affordable_percentage_final
    # affordable_missing (SchemeIntelligence's own explicit trust flag) is
    # the authoritative signal for whether the percentage is safe to use -
    # never inferred from the percentage being present/absent alone, since
    # a genuinely-0%-affordable scheme and a not-yet-established one would
    # otherwise be indistinguishable.
    affordable_trusted = affordable_pct is not None and not bool(getattr(scheme_intelligence, "affordable_missing", False))

    return MatchingFacts(
        opportunity_type=PLANNING_DELIVERY,
        unit_count=scheme_intelligence.total_units_final,
        development_type_raw=dev_type,
        is_specialist_development=is_specialist,
        affordable_percentage=affordable_pct if affordable_trusted else None,
        affordable_percentage_trusted=affordable_trusted,
        planning_state=PERMISSION_GRANTED,
        has_identified_planning_activity=True,
        has_phasing_evidence=False,
        matched_to_site=True,
    )


@dataclass(frozen=True)
class BuyerFitAssessment:
    classification: str  # STRONG_FIT | NOT_SUITABLE | INSUFFICIENT_EVIDENCE
    is_investigative_exception: bool
    matches: list[str] = field(default_factory=list)
    does_not_match: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    investigate: list[str] = field(default_factory=list)


def _planning_state_label(state: str) -> str:
    return {
        PERMISSION_GRANTED: "planning permission granted",
        ADOPTED_ALLOCATION: "an adopted residential allocation",
        EMERGING_ALLOCATION: "an emerging residential allocation",
        OTHER_OR_UNKNOWN: "an unclassified planning position",
    }.get(state, state)


def assess_buyer_fit(profile: BuyerProfile, facts: MatchingFacts) -> BuyerFitAssessment:
    """The one deterministic decision function every buyer-fit result goes
    through - no LLM, no numeric score. Hard exclusions (development type,
    100% affordable) are checked first and dominate the classification if
    triggered, exactly matching the brief's own "Exclude where trusted
    evidence establishes..." lists, which name only these two grounds -
    planning-state mismatch is deliberately never a hard exclusion (see
    BuyerProfile.accepted_planning_states' own docstring)."""
    matches: list[str] = []
    does_not_match: list[str] = []
    unknown: list[str] = []
    investigate: list[str] = []
    is_investigative_exception = False

    # --- Hard exclusion 1: specialist/non-general-needs development type ---
    if facts.is_specialist_development is True:
        does_not_match.append(
            f"Trusted evidence identifies this as a specialist development "
            f"({facts.development_type_raw or 'non-residential use'}), not the general-needs residential "
            f"development this buyer requires."
        )
    elif facts.is_specialist_development is None:
        unknown.append("Development type has not been established with enough confidence to confirm this is general-needs housing.")

    # --- Hard exclusion 2: wholly (100%) affordable-led ---------------------
    if facts.affordable_percentage is not None and facts.affordable_percentage >= WHOLLY_AFFORDABLE_THRESHOLD:
        does_not_match.append(
            f"Trusted evidence shows this is a wholly ({facts.affordable_percentage:.0f}%) affordable-led "
            f"scheme, not open-market residential development."
        )
    elif not facts.affordable_percentage_trusted:
        unknown.append("Affordable housing proportion has not been confirmed - not assumed to be 0%.")
    # A trusted, non-100% figure (the normal policy-compliant case) is
    # deliberately NOT added as a "matches" reason - per the brief, the
    # mere presence of policy-compliant affordable housing inside an
    # otherwise open-market scheme must never itself read as a point in
    # favour or against; it is simply not a disqualifier.

    # --- Planning appetite - never a hard exclusion (see module docstring) -
    if facts.planning_state in profile.accepted_planning_states:
        matches.append(f"Planning position ({_planning_state_label(facts.planning_state)}) matches this buyer's stated planning appetite.")
    elif facts.planning_state == OTHER_OR_UNKNOWN:
        unknown.append("Planning position could not be classified with confidence against this buyer's stated appetite.")
    else:
        unknown.append(f"This opportunity is {_planning_state_label(facts.planning_state)}, which is outside this buyer's stated planning appetite but not treated as a disqualifying fact.")

    # --- Strategic Land Buyer's own risk-appetite framing -------------------
    if profile.treats_no_activity_as_positive and facts.opportunity_type == STRATEGIC_LAND:
        if facts.has_identified_planning_activity is False:
            matches.append("No planning activity has yet been identified against this allocation - an early-stage position consistent with this buyer's strategic land appetite.")
        elif facts.has_identified_planning_activity is None:
            unknown.append("Planning activity position could not be established for this allocation.")

    # --- Unit-range assessment -----------------------------------------------
    if facts.unit_count is None:
        unknown.append("No trusted unit count is available to assess against this buyer's target range.")
    elif profile.target_unit_min <= facts.unit_count <= profile.target_unit_max:
        matches.append(f"Approximately {facts.unit_count:,} homes sits within this buyer's target range ({profile.target_unit_min}-{profile.target_unit_max} homes).")
    elif facts.unit_count < profile.target_unit_min:
        unknown.append(f"Approximately {facts.unit_count:,} homes is below this buyer's target range ({profile.target_unit_min}-{profile.target_unit_max} homes) - not treated as a disqualifying fact on its own.")
    else:  # oversized
        if profile.large_allocation_is_self_qualifying and facts.opportunity_type == STRATEGIC_LAND:
            matches.append(
                f"This allocation's own scale (~{facts.unit_count:,} homes) represents a meaningful "
                f"strategic-land position in its own right, independent of whether a specific parcel size "
                f"is confirmed."
            )
        elif facts.has_phasing_evidence:
            investigate.append("Evidence of phased delivery exists for this opportunity - review whether a phase within this buyer's target range could be available.")
        else:
            unknown.append(f"Overall scale (~{facts.unit_count:,} homes) materially exceeds this buyer's target range ({profile.target_unit_min}-{profile.target_unit_max} homes); no phasing/parcel evidence exists to establish whether a suitable smaller phase could become available.")
        investigate.append("Establish whether a suitable development parcel/phase could become available within this buyer's target range.")
        is_investigative_exception = True

    # --- Ownership/control - allocation-specific, structural gap -----------
    if facts.opportunity_type == STRATEGIC_LAND and not facts.matched_to_site:
        unknown.append("Ownership/control has not been established for this allocation.")

    if does_not_match:
        classification = NOT_SUITABLE
    elif unknown:
        classification = INSUFFICIENT_EVIDENCE
    else:
        classification = STRONG_FIT

    return BuyerFitAssessment(
        classification=classification, is_investigative_exception=is_investigative_exception,
        matches=matches, does_not_match=does_not_match, unknown=unknown, investigate=investigate,
    )
