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

Housing Association amendment (fourth pilot profile): every per-buyer
behavioural difference introduced by this amendment is expressed as an
explicit, generic BuyerProfile field - never a Housing-Association-only
branch keyed on profile.key - see app.policy.buyer_profiles.BuyerProfile's
own field docstrings (scale_metric, specialist_development_is_exclusion,
wholly_affordable_is_exclusion, below_minimum_scale_is_exclusion) and the
matching blocks below for exactly how each one changes assess_buyer_fit's
behaviour. Every housebuilder pilot profile's own flag values reproduce
the original (pre-amendment) behaviour and reason-string text exactly.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.policy.buyer_profiles import (
    ADOPTED_ALLOCATION,
    AFFORDABLE_UNITS,
    EMERGING_ALLOCATION,
    OTHER_OR_UNKNOWN,
    PERMISSION_GRANTED,
    PLANNING_ACTIVE_PROPOSAL,
    SPECIALIST_DEVELOPMENT_TYPES,
    WHOLLY_AFFORDABLE_THRESHOLD,
    BuyerProfile,
)
from app.reporting.allocation_development_coverage import NO_IDENTIFIED_ACTIVITY
from app.reporting.scheme_reconciliation import FACT_RESOLVED

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
    unit_count: int | None  # the single most representative TOTAL scale figure available (see extractors)
    development_type_raw: str | None
    is_specialist_development: bool | None  # None = genuinely unknown, never inferred as False
    affordable_percentage: float | None
    affordable_percentage_trusted: bool
    # Housing Association amendment - the number of AFFORDABLE homes,
    # distinct from unit_count (total). None = genuinely not safely
    # knowable, never 0 by assumption. See build_planning_delivery_
    # matching_facts's own docstring for exactly where this comes from
    # (SchemeIntelligence.affordable_units_final - already app.extraction.
    # reconcile's own fully reconciled figure, derived from total x
    # percentage using that module's own existing convention where the
    # classifier didn't state an explicit count, and reset to None there
    # whenever that derivation would be unsafe - no second derivation is
    # implemented here). Always None for STRATEGIC_LAND (Local Plan
    # allocations carry no scheme-specific affordable-unit evidence at all -
    # never estimated from a Local Plan/NPPF affordable-housing policy
    # percentage applied to allocation capacity).
    affordable_unit_count: int | None
    planning_state: str  # one of app.policy.buyer_profiles' five planning-state constants
    has_identified_planning_activity: bool | None  # None = not applicable/not determined
    has_phasing_evidence: bool
    matched_to_site: bool  # allocations only - whether AllocationSiteRelationship/matched_site_id exists at all
    # Gate 2B-2B.1 - whether OperativePlanningFacts resolved one or more
    # live `active_positions` for this opportunity, independent of
    # `planning_state` above. This is what lets a consented permission and
    # a separately-live active proposal (e.g. Hazelhurst Farm's 400-unit
    # consent plus its own 176-unit active phase) coexist in Buyer Fit
    # reasoning without either fact silently disappearing - see assess_
    # buyer_fit's own use of these two fields. Always False/0 for
    # STRATEGIC_LAND and for the legacy (pre-2B-2B.1) representative-
    # application builder below, neither of which has any concept of
    # "active positions" to report.
    has_active_proposal: bool = False
    active_proposal_count: int = 0


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
        # Housing Association amendment (brief Section 10): no scheme-
        # specific affordable-unit evidence exists for a Local Plan
        # allocation - deliberately never estimated by applying a Local
        # Plan/NPPF affordable-housing policy percentage to allocation
        # capacity. Genuinely unknown, correctly producing INSUFFICIENT_
        # EVIDENCE for the Housing Association profile rather than a
        # fabricated figure.
        affordable_unit_count=None,
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
            affordable_unit_count=None,
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

    # Housing Association amendment (brief Sections 4-5) - the safest
    # existing source for "number of affordable homes" is SchemeIntelligence.
    # affordable_units_final itself: app.extraction.reconcile.reconcile_
    # application_intelligence already computes this as the platform's own
    # fully reconciled figure - preferring an explicit classifier-stated
    # affordable-unit count, and ONLY where no such count was stated,
    # deterministically deriving one from total_units_final x
    # affordable_percentage_final (that module's own existing round()
    # convention - never a new rounding rule invented here), and that same
    # reconciliation resets this field to None in every case it judges the
    # derivation unsafe (an unconfirmed split, an external-consultation
    # record, a self-contradictory classifier result). Reading this field
    # directly - rather than re-deriving from total x percentage a second
    # time in this module - reuses that existing, already-tested provenance
    # verbatim instead of duplicating it (CLAUDE.md: "reuse existing
    # architecture"). A None value here already means "not safely knowable"
    # per that module's own rules - never assumed to be 0 by this function.
    affordable_unit_count = scheme_intelligence.affordable_units_final

    return MatchingFacts(
        opportunity_type=PLANNING_DELIVERY,
        unit_count=scheme_intelligence.total_units_final,
        development_type_raw=dev_type,
        is_specialist_development=is_specialist,
        affordable_percentage=affordable_pct if affordable_trusted else None,
        affordable_percentage_trusted=affordable_trusted,
        affordable_unit_count=affordable_unit_count,
        planning_state=PERMISSION_GRANTED,
        has_identified_planning_activity=True,
        has_phasing_evidence=False,
        matched_to_site=True,
    )


def _operative_source_scheme_intelligence(operative_facts, applications_by_id: dict):
    """The SchemeIntelligence row behind whichever operative unit figure
    build_planning_delivery_matching_facts_from_operative used (the
    consented position's source application, else - only when exactly one
    active proposal exists - that proposal's own source) - never a second,
    independently-selected representative application, and never inferred
    from OperativePlanningFacts.unit_mix's own free text (Gate 2B-2B.1
    brief Section 10: "do not infer numerical house/apartment dominance
    from free text"). Returns None when no such source can be identified
    (e.g. genuinely NOT_DETERMINED, or multiple simultaneous active
    proposals with no single one to attribute development type to)."""
    consented = operative_facts.consented_position
    source = None
    if consented.approved_units.state == FACT_RESOLVED and consented.approved_units.source is not None:
        source = consented.approved_units.source
    elif len(operative_facts.active_positions) == 1:
        proposed = operative_facts.active_positions[0].proposed_units
        if proposed.state == FACT_RESOLVED and proposed.source is not None:
            source = proposed.source
    if source is None:
        return None
    app = applications_by_id.get(source.application_id)
    return app.scheme_intelligence if app else None


def build_planning_delivery_matching_facts_from_operative(operative_facts, applications: list) -> MatchingFacts:
    """Gate 2B-2B.1 - the trusted-facts-aware counterpart to
    build_planning_delivery_matching_facts above, consuming
    app.reporting.scheme_reconciliation.OperativePlanningFacts (already
    computed once by the caller over the Site's full application list)
    instead of independently selecting one representative Application via
    app.ui.common.pick_representative_application. `applications` is that
    same Site's full application list, used only to look up the
    SchemeIntelligence row behind whichever operative fact this function
    reads (see _operative_source_scheme_intelligence) - never to pick a
    representative application itself.

    Used by app.reporting.opportunity_feed's live Buyer Fit rendering -
    the exact consumer Astra's "Strong Fit because permission granted"
    report traced to (Former Pendlebury Miners Club: an outline
    application still 'Under Consultation', with no decision at all).
    Deliberately NOT used by app.reporting.opportunity_universe's
    fingerprint-field construction, which keeps calling the legacy
    build_planning_delivery_matching_facts above completely unchanged -
    Gate 2B-2B.1 is explicitly forbidden from changing opportunity
    fingerprints, and unit_count/affordable_unit_count/development_type_raw/
    is_specialist_development all feed that fingerprint today. See this
    gate's own implementation report Section C for the full reasoning."""
    consented = operative_facts.consented_position
    active_positions = operative_facts.active_positions
    ah = operative_facts.affordable_housing

    # --- planning_state: cases A-E from the Gate 2B-2B.1 brief ----------
    # A. an operative consent exists -> PERMISSION_GRANTED (consent is
    #    always the primary planning-position basis when it exists, per
    #    Section 9 - a coexisting active proposal never cancels it, see
    #    has_active_proposal/active_proposal_count below instead).
    # B/C. no consent, but one or more active substantive proposals exist
    #    -> PLANNING_ACTIVE_PROPOSAL (never "granted"; multiplicity is
    #    carried separately, never collapsed by "latest wins").
    # D/E. refused/withdrawn-only, or genuinely NOT_DETERMINED -> neither
    #    is a classifiable planning stage this buyer vocabulary already
    #    has a positive name for; reuses the existing generic
    #    OTHER_OR_UNKNOWN constant rather than inventing two more (Section
    #    7: "if compatibility requires an existing generic/unknown state,
    #    use it").
    if consented.planning_status.state == FACT_RESOLVED and consented.planning_status.value == "Permission granted":
        planning_state = PERMISSION_GRANTED
    elif len(active_positions) >= 1:
        planning_state = PLANNING_ACTIVE_PROPOSAL
    else:
        planning_state = OTHER_OR_UNKNOWN

    # --- units: consented preferred, else (only when exactly one active
    # proposal exists) that proposal's own figure - the same A/B/C/D rule
    # app.reporting.scheme_reconciliation.resolve_operative_filter_facts
    # already implements for Explore, reused conceptually rather than
    # re-derived from scratch. Multiple simultaneous active proposals with
    # no consent leave unit_count None/not-determined - never summed,
    # never "latest wins".
    unit_count = None
    if consented.approved_units.state == FACT_RESOLVED:
        unit_count = consented.approved_units.value
    elif len(active_positions) == 1 and active_positions[0].proposed_units.state == FACT_RESOLVED:
        unit_count = active_positions[0].proposed_units.value

    # --- development type / specialist flag - read from the SAME
    # application the unit figure above came from; never inferred from
    # unit_mix's own joined free-text string (Section 10). -------------
    applications_by_id = {a.id: a for a in applications}
    source_si = _operative_source_scheme_intelligence(operative_facts, applications_by_id)
    dev_type = source_si.development_type if source_si else None
    is_specialist = (dev_type in SPECIALIST_DEVELOPMENT_TYPES) if dev_type else None

    # --- affordable housing: consented AH preferred, else (exactly one
    # active proposal) that proposal's own AH - ah.historical (withdrawn/
    # refused positions) is never read here, so a withdrawn scheme's AH
    # figure structurally cannot influence Buyer Fit (Section 8: "withdrawn/
    # refused AH must NOT influence current Buyer Fit").
    affordable_pct = None
    affordable_units = None
    if ah.whole_site is not None:
        affordable_pct, affordable_units = ah.whole_site.percentage, ah.whole_site.units
    elif len(active_positions) == 1 and ah.active_whole_site is not None:
        affordable_pct, affordable_units = ah.active_whole_site.percentage, ah.active_whole_site.units
    # A trusted, explicitly-evidenced 0% is preserved as 0 (never
    # discarded) - affordable_trusted is about WHETHER a position was
    # resolved at all (ah.whole_site/ah.active_whole_site is None whenever
    # nothing genuinely evidenced was found - see affordable_housing_
    # scope.py's own _has_no_independent_affordable_position), never about
    # the resolved value happening to be zero.
    affordable_trusted = affordable_pct is not None

    return MatchingFacts(
        opportunity_type=PLANNING_DELIVERY,
        unit_count=unit_count,
        development_type_raw=dev_type,
        is_specialist_development=is_specialist,
        affordable_percentage=affordable_pct if affordable_trusted else None,
        affordable_percentage_trusted=affordable_trusted,
        affordable_unit_count=affordable_units,
        planning_state=planning_state,
        has_identified_planning_activity=True,
        has_phasing_evidence=False,
        matched_to_site=True,
        has_active_proposal=len(active_positions) >= 1,
        active_proposal_count=len(active_positions),
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
        PLANNING_ACTIVE_PROPOSAL: "an active planning application, not yet decided",
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
    #
    # Housing Association amendment: profile.specialist_development_is_
    # exclusion is True for every housebuilder pilot profile (unchanged
    # behaviour/wording), but False for Housing Association, whose own
    # brief forbids inventing this exclusion for a buyer whose specialist-
    # product appetite was never stated. `facts.opportunity_type ==
    # STRATEGIC_LAND` is ORed in regardless of that flag because this flag
    # only ever means "employment allocation" for strategic land (see
    # build_strategic_land_matching_facts) - genuinely non-residential, a
    # universal exclusion for every buyer in this pilot, not an unstated
    # specialist-housing preference question.
    if facts.is_specialist_development is True:
        if profile.specialist_development_is_exclusion or facts.opportunity_type == STRATEGIC_LAND:
            does_not_match.append(
                f"Trusted evidence identifies this as a specialist development "
                f"({facts.development_type_raw or 'non-residential use'}), not the general-needs residential "
                f"development this buyer requires."
            )
        else:
            unknown.append(
                f"Trusted evidence identifies this as a specialist development "
                f"({facts.development_type_raw or 'a specialist residential product'}); this buyer's own "
                f"appetite for specialist/retirement housing has not been specified, so this is not treated "
                f"as confirmed positive or negative evidence."
            )
    elif facts.is_specialist_development is None:
        unknown.append("Development type has not been established with enough confidence to confirm this is general-needs housing.")

    # --- Hard exclusion 2: wholly (100%) affordable-led ---------------------
    #
    # Housing Association amendment: deliberately reversed polarity for a
    # buyer whose own primary requirement IS affordable housing - see
    # BuyerProfile.wholly_affordable_is_exclusion's own docstring.
    if facts.affordable_percentage is not None and facts.affordable_percentage >= WHOLLY_AFFORDABLE_THRESHOLD:
        if profile.wholly_affordable_is_exclusion:
            does_not_match.append(
                f"Trusted evidence shows this is a wholly ({facts.affordable_percentage:.0f}%) affordable-led "
                f"scheme, not open-market residential development."
            )
        else:
            matches.append(
                f"Trusted evidence shows this is a wholly ({facts.affordable_percentage:.0f}%) affordable-led "
                f"scheme, directly relevant to this buyer's affordable-housing focus."
            )
    elif not facts.affordable_percentage_trusted:
        unknown.append("Affordable housing proportion has not been confirmed - not assumed to be 0%.")
    # A trusted, non-100% figure (the normal policy-compliant case) is
    # deliberately NOT added as a "matches"/"does_not_match" reason for any
    # profile - per the brief, the mere presence of policy-compliant
    # affordable housing inside an otherwise open-market scheme must never
    # itself read as a point in favour or against; the affordable UNIT
    # COUNT (below) is where a Housing Association's own interest in that
    # component is actually assessed.

    # --- Planning appetite - never a hard exclusion (see module docstring) -
    if facts.planning_state in profile.accepted_planning_states:
        matches.append(f"Planning position ({_planning_state_label(facts.planning_state)}) matches this buyer's stated planning appetite.")
    elif facts.planning_state == OTHER_OR_UNKNOWN:
        unknown.append("Planning position could not be classified with confidence against this buyer's stated appetite.")
    else:
        unknown.append(f"This opportunity is {_planning_state_label(facts.planning_state)}, which is outside this buyer's stated planning appetite but not treated as a disqualifying fact.")

    # --- Consent + active proposal coexistence (Gate 2B-2B.1, Section 9) -
    #
    # A live active proposal alongside an operative consent (e.g.
    # Hazelhurst Farm's 400-unit whole-site consent plus its own separate
    # 176-unit active phase) is never allowed to disappear merely because
    # `planning_state` above already resolved to PERMISSION_GRANTED - it is
    # surfaced as its own investigate-worthy note instead, never fabricated
    # into a second "current application" and never treated as cancelling
    # the consent.
    if facts.planning_state == PERMISSION_GRANTED and facts.has_active_proposal:
        proposal_noun = "a further active planning application is" if facts.active_proposal_count == 1 else f"{facts.active_proposal_count} further active planning applications are"
        investigate.append(
            f"An operative planning permission exists for this opportunity, and {proposal_noun} also live and "
            f"not yet decided - review whether this represents an additional phase or a proposed variation."
        )

    # --- Strategic Land Buyer's own risk-appetite framing -------------------
    if profile.treats_no_activity_as_positive and facts.opportunity_type == STRATEGIC_LAND:
        if facts.has_identified_planning_activity is False:
            matches.append("No planning activity has yet been identified against this allocation - an early-stage position consistent with this buyer's strategic land appetite.")
        elif facts.has_identified_planning_activity is None:
            unknown.append("Planning activity position could not be established for this allocation.")

    # --- Unit-range assessment -----------------------------------------------
    #
    # Housing Association amendment: profile.scale_metric picks which of
    # MatchingFacts' two unit figures this buyer's target_unit_min/max is
    # actually measured against. For every housebuilder pilot profile
    # (scale_metric=TOTAL_UNITS) this reproduces the original behaviour and
    # message text exactly (unit_noun/no_count_message below both resolve
    # to the pre-amendment literal strings). Housing Association
    # (scale_metric=AFFORDABLE_UNITS) is assessed against facts.
    # affordable_unit_count instead - a 400-home scheme with 120 affordable
    # homes is judged on 120, never rejected for the total exceeding 300.
    if profile.scale_metric == AFFORDABLE_UNITS:
        scale_value = facts.affordable_unit_count
        unit_noun = "affordable homes"
        no_count_message = "No trusted affordable-unit count is available to assess against this buyer's target range."
    else:
        scale_value = facts.unit_count
        unit_noun = "homes"
        no_count_message = "No trusted unit count is available to assess against this buyer's target range."

    if scale_value is None:
        unknown.append(no_count_message)
    elif profile.target_unit_min <= scale_value <= profile.target_unit_max:
        matches.append(f"Approximately {scale_value:,} {unit_noun} sits within this buyer's target range ({profile.target_unit_min}-{profile.target_unit_max} {unit_noun}).")
    elif scale_value < profile.target_unit_min:
        # Housing Association amendment: below_minimum_scale_is_exclusion is
        # False for every housebuilder profile (unchanged "unknown" branch,
        # never a disqualifier on its own) but True for Housing Association,
        # whose own brief states a scheme with fewer than 50 affordable
        # homes is NOT SUITABLE, not merely under-evidenced.
        if profile.below_minimum_scale_is_exclusion:
            does_not_match.append(
                f"Trusted evidence shows only {scale_value:,} {unit_noun}, below this buyer's minimum "
                f"requirement of {profile.target_unit_min} {unit_noun}."
            )
        else:
            unknown.append(f"Approximately {scale_value:,} {unit_noun} is below this buyer's target range ({profile.target_unit_min}-{profile.target_unit_max} {unit_noun}) - not treated as a disqualifying fact on its own.")
    else:  # oversized
        if profile.large_allocation_is_self_qualifying and facts.opportunity_type == STRATEGIC_LAND:
            matches.append(
                f"This allocation's own scale (~{scale_value:,} {unit_noun}) represents a meaningful "
                f"strategic-land position in its own right, independent of whether a specific parcel size "
                f"is confirmed."
            )
        elif facts.has_phasing_evidence:
            investigate.append("Evidence of phased delivery exists for this opportunity - review whether a phase within this buyer's target range could be available.")
        else:
            unknown.append(f"Overall scale (~{scale_value:,} {unit_noun}) materially exceeds this buyer's target range ({profile.target_unit_min}-{profile.target_unit_max} {unit_noun}); no phasing/parcel evidence exists to establish whether a suitable smaller phase could become available.")
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
