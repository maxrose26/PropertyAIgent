"""Buyer Profiles V1 - deterministic buyer-fit classification (Phase 1
pilot). Sits strictly downstream of existing opportunity detection: reads
already-computed, already-trusted facts (app.reporting.allocation_
development_coverage, app.reporting.allocation_discovery, SchemeIntelligence)
and classifies them against a app.policy.buyer_profiles.BuyerMandatePolicy - it
never re-derives a fact those modules already own, never calls an LLM, and
never produces a numeric score.

Architecture (see the Buyer Profiles V1 investigation report for the full
audit this implements):

    Verified planning/Local Plan intelligence
        -> existing deterministic opportunity detection (unchanged)
        -> MatchingFacts (this module - a thin, safe reader)
        -> BuyerMandatePolicy (app.policy.buyer_profiles - fixed pilot config)
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
explicit, generic BuyerMandatePolicy field - never a Housing-Association-only
branch keyed on profile.key - see app.policy.buyer_profiles.BuyerMandatePolicy's
own field docstrings (scale_metric, specialist_development_is_exclusion,
wholly_affordable_is_exclusion, below_minimum_scale_is_exclusion) and the
matching blocks below for exactly how each one changes assess_buyer_fit's
behaviour. Every housebuilder pilot profile's own flag values reproduce
the original (pre-amendment) behaviour and reason-string text exactly.

Buyer Mandate V2, Phase B2 (Deterministic Buyer Fit Integration) activates
the four Phase B1 structural mandate dimensions (geography, acquisition
type, development-state appetite, control/ownership appetite) here, via
an OPTIONAL, backward-compatible `context: B2MatchingContext` parameter
on assess_buyer_fit - every pre-B2 call site (every existing test, the
live opportunity feed, the onboarding baseline) continues to work
completely unchanged by simply never passing one, in which case every B2
dimension contributes nothing (exactly Phase B1's own proven inertness).
See BUYER_MATCHING_POLICY_VERSION's own docstring for why this activation
required a matching-semantics version, and B2MatchingContext's own
docstring for the pure/DB-free boundary this module still enforces -
Gate 2C's own DB-touching AcquisitionPositionFacts computation happens
entirely OUTSIDE this module, in app.policy.buyer_matching_b2_context,
which this module deliberately does not import (the dependency runs the
other way: that module imports build_control_appetite_facts from here).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.policy.buyer_profiles import (
    ACQUISITION_TYPES,
    ADOPTED_ALLOCATION,
    AFFORDABLE_HOUSING_PACKAGE,
    AFFORDABLE_UNITS,
    CONTROL_APPETITES,
    DEVELOPER_LED_ACCEPTABLE,
    DEVELOPMENT_HOMES_ACQUISITION,
    DEVELOPMENT_STATE_UNSPECIFIED,
    EMERGING_ALLOCATION,
    GEOGRAPHY_ALL_CURRENT_COVERAGE,
    GEOGRAPHY_COUNCILS,
    GEOGRAPHY_UNSPECIFIED,
    LAND_SITE_ACQUISITION,
    OTHER_OR_UNKNOWN,
    PARTIAL_SITE_CONTROL_ACCEPTABLE,
    PERMISSION_GRANTED,
    PLANNING_ACTIVE_PROPOSAL,
    SPECIALIST_DEVELOPMENT_TYPES,
    STRATEGIC_LAND_CONTROL,
    THIRD_PARTY_INTEREST_ACCEPTABLE,
    UNCOMMENCED_PREFERRED,
    UNDERWAY_ACCEPTABLE,
    UNDERWAY_PREFERRED,
    UNRESOLVED_OWNERSHIP_INVESTIGATABLE,
    WHOLLY_AFFORDABLE_THRESHOLD,
    BuyerMandatePolicy,
)
from app.reporting.allocation_development_coverage import NO_IDENTIFIED_ACTIVITY
from app.reporting.scheme_reconciliation import FACT_RESOLVED

STRATEGIC_LAND = "strategic_land"
PLANNING_DELIVERY = "planning_delivery"

STRONG_FIT = "STRONG_FIT"
NOT_SUITABLE = "NOT_SUITABLE"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

# --- Buyer Mandate V2, Phase B2: matching-policy version ---------------------
#
# Phase B1 recorded this as a mandatory B2 entry condition: B1's own
# fingerprint already includes every B1 field's VALUE, but B2 changes how
# those same, unchanged values are INTERPRETED - a fingerprint over values
# alone cannot detect that. app.policy.buyer_profile_store.compute_buyer_
# mandate_fingerprint includes this constant in its own hash input, so
# introducing/bumping it invalidates every existing baseline exactly once,
# deterministically, without requiring any mandate's own persisted field to
# change. Bump this only when assess_buyer_fit's OWN INTERPRETATION of an
# already-existing field changes commercial meaning - never for a purely
# cosmetic/refactoring change that provably produces identical output.
#
# Version 3 (B2 narrow semantic cleanup, post Buyer Fit Classification
# Audit): four classification-driving rules were reclassified as
# contextual/investigative - a known-but-non-preferred planning state, a
# known scale outside a soft target range, strategic land's structurally
# unavailable affordable-percentage/specialist-status facts, and strategic
# land's ownership/site-linkage gap. No mandate field's own value changed;
# only assess_buyer_fit's interpretation of already-existing values did -
# exactly the case this version constant exists to invalidate a baseline
# for.
BUYER_MATCHING_POLICY_VERSION = 3

# --- Buyer Mandate V2, Phase B2: build_status vocabulary (reused verbatim) --
#
# The exact strings app.pipeline.lapse_tracking.classify_build_status
# already returns - never redefined here (Phase B2 brief, Section 20: "do
# not redefine the source vocabulary inside Buyer Matching"). "unknown"
# covers BOTH "genuinely no evidence at all" and "this module's caller
# chose not to compute it" - assess_buyer_fit cannot and does not
# distinguish those two cases, since both mean the same thing to a
# deterministic consumer: no positive fact is available.
DEVELOPMENT_STATE_UNDERWAY = "underway"
DEVELOPMENT_STATE_PARTIALLY_COMPLETE = "partially_complete"
DEVELOPMENT_STATE_COMPLETE = "complete"
DEVELOPMENT_STATE_UNKNOWN = "unknown"
_DEVELOPMENT_STARTED_STATES = frozenset({DEVELOPMENT_STATE_UNDERWAY, DEVELOPMENT_STATE_PARTIALLY_COMPLETE, DEVELOPMENT_STATE_COMPLETE})


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


def build_planning_delivery_matching_facts(scheme_intelligence, *, planning_state: str = OTHER_OR_UNKNOWN) -> MatchingFacts:
    """scheme_intelligence: a SchemeIntelligence ORM row for the
    representative application behind a planning/delivery opportunity
    card (already selected by app.ui.common.pick_representative_application
    elsewhere in the platform - this function does not pick one itself).
    May be None (no SchemeIntelligence extracted yet for this application) -
    every fact then reads as genuinely unknown, never guessed.

    Gate 2B-2B.1 pre-merge remediation - `planning_state` is now an
    explicit, caller-supplied argument, never a hardcoded PERMISSION_
    GRANTED. This function's OTHER fields (unit_count/affordable_unit_
    count/development_type_raw/is_specialist_development) are still read
    from this ONE representative application's own SchemeIntelligence
    verbatim - unchanged from before this remediation, because app.
    reporting.opportunity_universe's fingerprint_fields dict reads exactly
    those four fields from this function's output, and this gate is
    forbidden from changing opportunity fingerprints. `planning_state`
    itself is confirmed NOT one of those fingerprinted fields (see
    opportunity_universe.py's own fingerprint_fields construction), so it
    is free to be corrected without any fingerprint impact - callers
    (app.reporting.opportunity_universe) now compute it from
    app.reporting.scheme_reconciliation.build_operative_planning_facts via
    resolve_operative_planning_state below, the same trusted resolution
    app.policy.buyer_matching.build_planning_delivery_matching_facts_from_
    operative already uses for the live Buyer Fit path - never a second,
    independently-derived planning-state rule. Defaults to the existing,
    honest OTHER_OR_UNKNOWN (never PERMISSION_GRANTED) for any caller that
    doesn't supply real evidence, so this function can no longer assert a
    grant it hasn't actually checked."""
    if scheme_intelligence is None:
        return MatchingFacts(
            opportunity_type=PLANNING_DELIVERY, unit_count=None, development_type_raw=None,
            is_specialist_development=None, affordable_percentage=None, affordable_percentage_trusted=False,
            affordable_unit_count=None,
            planning_state=planning_state, has_identified_planning_activity=True,
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
        planning_state=planning_state,
        has_identified_planning_activity=True,
        has_phasing_evidence=False,
        matched_to_site=True,
    )


def resolve_operative_planning_state(operative_facts) -> str:
    """Gate 2B-2B.1 pre-merge remediation - the single deterministic
    planning_state rule, extracted so both build_planning_delivery_
    matching_facts_from_operative (the live Buyer Fit path) and app.
    reporting.opportunity_universe's fingerprint-compatible construction
    (build_planning_delivery_matching_facts above) resolve planning_state
    identically, from the SAME app.reporting.scheme_reconciliation.
    OperativePlanningFacts - never two independently-written rules that
    could silently drift apart.

    A. an operative consent exists -> PERMISSION_GRANTED (the primary
       planning-position basis whenever one exists - a coexisting active
       proposal never cancels it; see has_active_proposal/
       active_proposal_count on MatchingFacts instead).
    B/C. no consent, but one or more active substantive proposals exist
       -> PLANNING_ACTIVE_PROPOSAL (never "granted"; multiplicity is
       carried separately, never collapsed by "latest wins").
    D/E. refused/withdrawn-only, or genuinely NOT_DETERMINED -> the
       existing generic OTHER_OR_UNKNOWN (never a fabricated third state)."""
    consented = operative_facts.consented_position
    active_positions = operative_facts.active_positions
    if consented.planning_status.state == FACT_RESOLVED and consented.planning_status.value == "Permission granted":
        return PERMISSION_GRANTED
    if len(active_positions) >= 1:
        return PLANNING_ACTIVE_PROPOSAL
    return OTHER_OR_UNKNOWN


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

    NOT used by app.reporting.opportunity_universe's fingerprint-field
    construction (unit_count/affordable_unit_count/development_type_raw/
    is_specialist_development still come from build_planning_delivery_
    matching_facts above, reading one representative application's own
    SchemeIntelligence verbatim, unchanged - Gate 2B-2B.1 is forbidden
    from changing opportunity fingerprints, and those four fields feed it
    today). planning_state itself is NOT one of those fingerprinted
    fields, so opportunity_universe.py now ALSO resolves it correctly, via
    the shared resolve_operative_planning_state helper below - the same
    resolution this function uses - passed into build_planning_delivery_
    matching_facts's own `planning_state` argument at that call site. See
    this gate's pre-merge remediation report Section C/D for the full
    fingerprint-safety reasoning."""
    consented = operative_facts.consented_position
    active_positions = operative_facts.active_positions
    ah = operative_facts.affordable_housing

    planning_state = resolve_operative_planning_state(operative_facts)

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
class ControlAppetiteFacts:
    """Buyer Mandate V2, Phase B2 - the small, PURE, commercial-facts
    adapter output between Gate 2C's AcquisitionPositionFacts and
    assess_buyer_fit. Built once per opportunity by build_control_
    appetite_facts below (a pure function - the DB-touching call to Gate
    2C's own build_acquisition_position_facts happens in app.policy.
    buyer_matching_b2_context, never here and never inside assess_buyer_
    fit itself).

    Every field is `bool | None` - True means a trusted fact POSITIVELY
    establishes the situation; None means it cannot be established either
    way (Unknown Must Remain Unknown - this module never asserts False
    for the absence of positive evidence, since Gate 2C's own evidence
    model has no mechanism to positively rule these situations OUT, only
    to fail to find them)."""
    developer_or_applicant_led: bool | None
    third_party_interest_declared: bool | None
    # True only when Gate 2C's own evidence_coverage genuinely could not
    # pin down a control position (COVERAGE_INSUFFICIENT/SEARCHED_NO_
    # INDICATION_FOUND) or its own facts conflict (conflicts non-empty).
    # False when a specific, conflict-free ownership state IS on record
    # (e.g. Certificate A sole-ownership) - a real, evidenced fact, not a
    # guess. None only when this adapter was never given anything to
    # evaluate at all (an empty AcquisitionPositionFacts).
    ownership_unresolved: bool | None
    # Same underlying evidence as third_party_interest_declared (a
    # Certificate B/C/D-shaped "other owner interest" or "not fully
    # known" ownership state) - kept as its own field because
    # PARTIAL_SITE_CONTROL_ACCEPTABLE and THIRD_PARTY_INTEREST_ACCEPTABLE
    # are two different commercial framings of that one fact (Phase B2
    # brief, Section 31: "use only where the factual evidence genuinely
    # supports a partial/control situation").
    partial_control_evidence: bool | None


def build_control_appetite_facts(acquisition_facts) -> ControlAppetiteFacts:
    """The pure Gate-2C-evidence -> commercial-control-facts adapter
    (Phase B2 brief, Section 26's own "small deterministic interpretation
    /adapter" layer). Takes an already-built app.reporting.
    acquisition_position.AcquisitionPositionFacts (never a session, never
    an Application/Site row) and returns the small, commercial-vocabulary
    ControlAppetiteFacts assess_buyer_fit actually reads - this is the
    ONLY place in this codebase that reads Gate 2C's own OWNERSHIP_*/
    COVERAGE_* constant values for a buyer-matching purpose, and it never
    re-exports or strengthens their meaning (Section 27: a Certificate A
    fact remains "applicant declared sole ownership", never "current
    registered title"/"whole-site control"/"availability" - this adapter
    only ever asks "does at least one ownership_evidence entry indicate
    this shape", never anything stronger).

    Untyped `acquisition_facts` parameter deliberately - avoids importing
    app.reporting.acquisition_position's OWNERSHIP_*/COVERAGE_* constants
    into this module's own top-level import list for a mere type hint,
    since those string values are read directly below anyway; the actual
    object handed in is always an AcquisitionPositionFacts instance."""
    ownership_evidence = acquisition_facts.ownership_evidence
    developer_indications = acquisition_facts.developer_indications
    coverage = acquisition_facts.ownership_coverage
    conflicts = acquisition_facts.conflicts

    # No special-cased "nothing at all" branch: an allocation with no
    # matched site (empty applications list, per app.policy.
    # buyer_matching_b2_context's own strategic-land handling) produces
    # exactly ownership_evidence=(), developer_indications=(), coverage=
    # COVERAGE_INSUFFICIENT via Gate 2C's own build_acquisition_position_
    # facts - which the general logic below already maps to the honest
    # (None, None, True, None) result: no specific fact established
    # (None), but the overall position genuinely IS unresolved (True) -
    # exactly Gate 2C's own COVERAGE_INSUFFICIENT meaning, never a
    # separate "not evaluated" concept this adapter would have to invent.
    developer_or_applicant_led = True if developer_indications else None

    other_owner_states = {"OTHER_OWNER_INTEREST_DECLARED", "PARTIAL_OWNERSHIP_IDENTIFICATION", "OWNERSHIP_NOT_FULLY_KNOWN"}
    has_other_owner_evidence = any(fact.state in other_owner_states for fact in ownership_evidence)
    third_party_interest_declared = True if has_other_owner_evidence else None
    partial_control_evidence = True if has_other_owner_evidence else None

    if coverage in ("INSUFFICIENT_EVIDENCE_TO_DETERMINE_CONTROL", "RELEVANT_EVIDENCE_SEARCHED_NO_CONTROL_INDICATION_FOUND") or conflicts:
        ownership_unresolved = True
    elif ownership_evidence:
        # coverage == RELEVANT_EVIDENCE_SEARCHED_INDICATION_FOUND with at
        # least one real ownership fact on record and no conflicts - a
        # genuinely resolved (though not necessarily sole/whole-site)
        # position, per Certificate A/B/C/D's own evidence-specific
        # meaning (Section 27 - "resolved" here means "we have a specific
        # evidenced declaration", never "we have proven current title").
        ownership_unresolved = False
    else:
        ownership_unresolved = None

    return ControlAppetiteFacts(
        developer_or_applicant_led=developer_or_applicant_led,
        third_party_interest_declared=third_party_interest_declared,
        ownership_unresolved=ownership_unresolved,
        partial_control_evidence=partial_control_evidence,
    )


@dataclass(frozen=True)
class B2MatchingContext:
    """Buyer Mandate V2, Phase B2 - the single OPTIONAL bundle of trusted
    facts assess_buyer_fit needs to evaluate the four Phase B1 mandate
    dimensions, kept deliberately separate from MatchingFacts itself
    (which app.reporting.opportunity_universe.build_current_opportunity_
    universe builds and fingerprints - Phase B2 brief, Section 54:
    "do NOT modify build_current_opportunity_universe"). A caller that
    does not build one (every pre-B2 call site, and any future caller
    that judges Gate 2C's own live-computation cost not yet worth paying
    for a given code path - see app.policy.buyer_matching_b2_context's
    own module docstring for the measured cost) gets the exact Phase B1
    behaviour: every B2 dimension contributes nothing.

    Every field is independently optional - a caller can supply
    council_code/development_state cheaply (both already computed
    elsewhere for other purposes, e.g. compute_lapse_status's own
    fingerprint use) while leaving control_facts None if Gate 2C's own
    per-opportunity computation cost is not justified for that call.

    Phase B2 narrow remediation (Issue B): development_state_scope_
    verified records whether `development_state` is known to cover the
    SAME opportunity scope as the specific opportunity being assessed -
    e.g. a site-level or genuinely whole-site/unphased opportunity, vs a
    single named phase, a recent permission, or a long-pending
    application, where an "underway" fact may only describe a DIFFERENT
    part of the same site. Defaults to False (unverified/unknown scope)
    so a caller that never computes this - deliberately including every
    caller from before this field existed - gets the safe, conservative
    behaviour: a hard rejection dependent on development_state is never
    triggered on unverified scope."""
    council_code: str | None = None
    development_state: str | None = None  # one of the DEVELOPMENT_STATE_* constants above, or None (not computed)
    control_facts: ControlAppetiteFacts | None = None
    development_state_scope_verified: bool = False


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


def assess_buyer_fit(profile: BuyerMandatePolicy, facts: MatchingFacts, context: B2MatchingContext | None = None) -> BuyerFitAssessment:
    """The one deterministic decision function every buyer-fit result goes
    through - no LLM, no numeric score. Hard exclusions (development type,
    100% affordable) are checked first and dominate the classification if
    triggered, exactly matching the brief's own "Exclude where trusted
    evidence establishes..." lists, which name only these two grounds -
    planning-state mismatch is deliberately never a hard exclusion (see
    BuyerMandatePolicy.accepted_planning_states' own docstring).

    Buyer Mandate V2, Phase B2: `context` is OPTIONAL and defaults to
    None, which behaves EXACTLY as Phase B1 proved this function already
    does - every B1 mandate dimension (geography, acquisition type,
    development-state appetite, control appetite) contributes nothing.
    Passing a B2MatchingContext activates the four new evaluation blocks
    below, each independently gated on the RELEVANT mandate field
    actually being configured (GEOGRAPHY_UNSPECIFIED/DEVELOPMENT_STATE_
    UNSPECIFIED/an empty acquisition_types or control_appetite set all
    contribute zero reasons - a buyer that hasn't stated an appetite for
    a dimension is never penalised or credited for it). See each block's
    own comment for its HARD CONSTRAINT / SOFT PREFERENCE / EVIDENCE GAP
    classification (Phase B2 brief, Section 37's own required rule
    matrix) - only two paths in this whole function can ever append to
    does_not_match because of a B2 dimension: an explicit COUNCILS
    mismatch, and a STRATEGIC_LAND_CONTROL mandate against confirmed-
    underway-or-further development at a VERIFIED opportunity scope
    (Phase B2 narrow remediation, Issue B - unverified scope is routed to
    `investigate`/`unknown` instead, never a hard rejection). Every other
    B2 rule is deliberately soft (matches/unknown/investigate only), per
    the brief's own repeated "use NOT_SUITABLE conservatively"
    instruction.

    Phase B2 narrow remediation (Issue A): not every `unknown` reason
    drives classification - see `blocking_unknown` below and the module-
    level classification-driving-vs-contextual distinction it encodes."""
    matches: list[str] = []
    does_not_match: list[str] = []
    unknown: list[str] = []
    investigate: list[str] = []
    is_investigative_exception = False
    # Phase B2 narrow remediation (Issue A), extended by the B2 narrow
    # semantic cleanup (post Buyer Fit Classification Audit): not every
    # reason in `unknown` should block STRONG_FIT. A CLASSIFICATION-DRIVING
    # unknown (a genuinely missing fact needed to confirm an actual mandate
    # REQUIREMENT - e.g. is the unit count known at all, is the planning
    # position classifiable at all) means the opportunity cannot yet be
    # confirmed a strong fit, and must still produce INSUFFICIENT_EVIDENCE.
    # A CONTEXTUAL unknown - either (a) a soft preference never a
    # requirement (the four B2.3 development-state-appetite reasons), (b) a
    # KNOWN fact that simply falls outside a soft target/preference (a
    # known-but-non-preferred planning state; a known scale outside a
    # target range), or (c) a fact this platform's own domain semantics
    # already establish can never be safely resolved for a given
    # opportunity type (strategic land's affordable-percentage and
    # specialist-development status; see their own inline comments below) -
    # must remain visible in the `unknown` bucket for transparency but must
    # NOT by itself downgrade an otherwise-STRONG_FIT opportunity.
    # `blocking_unknown` is set at every remaining genuine-evidence-gap
    # `unknown.append` call, and deliberately NOT set at any of the sites
    # listed above - each site's own inline comment explains which category
    # it falls into and why.
    blocking_unknown = False
    # Buyer Mandate V2, Phase B2: whether the CALLER chose to activate B2
    # at all - deliberately independent of whether the mandate itself has
    # any B1 fields configured (all four real production mandates already
    # have non-empty acquisition_types/development_state_appetite/
    # control_appetite from Phase B1). Without an explicit context, every
    # B2 block below is skipped entirely, reproducing Phase B1's own
    # proven-inert behaviour bit-for-bit - this is what makes every
    # pre-B2 call site (every existing test, the live feed, the
    # onboarding baseline) continue to work completely unchanged.
    b2_active = context is not None
    context = context or B2MatchingContext()

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
            blocking_unknown = True
    elif facts.is_specialist_development is None:
        if facts.opportunity_type == STRATEGIC_LAND:
            # B2 semantic cleanup (Buyer Fit Classification Audit, Section
            # 7.C2): decision recorded here, not merely in commit history.
            # build_strategic_land_matching_facts's own docstring already
            # explains why this can never resolve to False by design:
            # intended_use only distinguishes residential/mixed_use/
            # employment/gypsy_traveller at Local-Plan level, with no
            # retirement/student/care granularity - a "residential"
            # allocation could still deliver a specialist product once an
            # actual scheme comes forward. Mapping non-employment to a
            # confirmed False would risk exactly the false-negative this
            # platform must never invent (Unknown Must Remain Unknown), so
            # NO mapping change is made here - the fact stays honestly
            # unresolved. But a fact this platform's own domain semantics
            # say can never be safely resolved from Local Plan evidence
            # alone must not classification-block Buyer Fit for this
            # opportunity type - that is a genuine structural-null
            # question, not a temporary evidence gap.
            unknown.append("Specialist-development status cannot be established from a strategic land allocation's own intended-use classification alone - not treated as a disqualifying fact for this opportunity type.")
        else:
            unknown.append("Development type has not been established with enough confidence to confirm this is general-needs housing.")
            blocking_unknown = True

    # --- Hard exclusion 2: wholly (100%) affordable-led ---------------------
    #
    # Housing Association amendment: deliberately reversed polarity for a
    # buyer whose own primary requirement IS affordable housing - see
    # BuyerMandatePolicy.wholly_affordable_is_exclusion's own docstring.
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
        if facts.opportunity_type == STRATEGIC_LAND:
            # B2 semantic cleanup (Buyer Fit Classification Audit, Section
            # 7.C1): scheme-specific affordable_percentage is
            # STRUCTURALLY unavailable for a Local Plan allocation (see
            # MatchingFacts' own field docstring - "Always None for
            # STRATEGIC_LAND", never estimated from an NPPF/Local Plan
            # affordable-housing policy percentage) - never a temporary
            # data gap future extraction could close, so it must not
            # classification-block Buyer Fit for this opportunity type.
            # Still surfaced for transparency; never assumed 0% or 100%.
            unknown.append("Scheme-specific affordable housing proportion is not established for a strategic land allocation - not assumed to be 0%, and not treated as a disqualifying fact for this opportunity type.")
        else:
            unknown.append("Affordable housing proportion has not been confirmed - not assumed to be 0%.")
            blocking_unknown = True
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
        # Genuinely unclassifiable - a real evidence gap (planning position
        # itself could not be established), not a known-but-non-preferred
        # fact - remains classification-driving.
        unknown.append("Planning position could not be classified with confidence against this buyer's stated appetite.")
        blocking_unknown = True
    else:
        # B2 semantic cleanup (Buyer Fit Classification Audit, Section 5):
        # the planning STATE IS KNOWN here - this is a soft/contextual
        # mismatch against this buyer's stated appetite, never a missing
        # fact, and must not by itself block STRONG_FIT (the same
        # known-but-non-preferred distinction Issue A already established
        # for development-state appetite). Text unchanged - it already
        # said "not treated as a disqualifying fact"; only the
        # classification consequence was wrong.
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
            blocking_unknown = True

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
        blocking_unknown = True
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
            # B2 semantic cleanup (Buyer Fit Classification Audit, Section
            # 6): scale_value IS KNOWN here - a target range is not
            # automatically a hard constraint (the audit's own core
            # principle), so a known below-target scale is a soft/
            # contextual mismatch, never missing evidence. Text unchanged.
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
            # B2 semantic cleanup (Buyer Fit Classification Audit, Section
            # 6): the WHOLE-OPPORTUNITY scale_value is known and known to
            # exceed target - lack of phasing evidence is a genuine open
            # question for future acquisition-position investigation ("is
            # there a suitable phase within this larger scheme?"), never a
            # reason to call the already-known scale fact "insufficient
            # evidence" for basic Buyer Fit. Text unchanged.
            unknown.append(f"Overall scale (~{scale_value:,} {unit_noun}) materially exceeds this buyer's target range ({profile.target_unit_min}-{profile.target_unit_max} {unit_noun}); no phasing/parcel evidence exists to establish whether a suitable smaller phase could become available.")
        investigate.append("Establish whether a suitable development parcel/phase could become available within this buyer's target range.")
        is_investigative_exception = True

    # --- Ownership/control - allocation-specific, structural gap -----------
    #
    # B2 semantic cleanup (Buyer Fit Classification Audit, Section 8):
    # whether a strategic allocation is linked to a matched Site/ownership
    # position is primarily an Acquisition Position / investigation
    # question, not a fundamental Buyer Fit compatibility question - moved
    # from a classification-blocking `unknown` reason to `investigate`,
    # exactly the same treatment the existing B2.4 control-appetite
    # UNRESOLVED_OWNERSHIP_INVESTIGATABLE rule already gives unresolved
    # ownership evidence elsewhere in this function. Never fabricates
    # ownership, control, availability or seller intention; never a match;
    # never a hard mismatch.
    if facts.opportunity_type == STRATEGIC_LAND and not facts.matched_to_site:
        investigate.append("Ownership/control has not been established for this allocation - a genuine investigation question, not a Buyer Fit blocker.")

    # ==========================================================================
    # Buyer Mandate V2, Phase B2 - the four newly-activated mandate dimensions.
    # ==========================================================================

    # --- B2.1 Geography — HARD CONSTRAINT (COUNCILS mismatch only) ----------
    #
    # GEOGRAPHY_UNSPECIFIED: no reason at all - a buyer that has never
    # stated a geographic appetite is neither rejected nor credited for it
    # (Phase B2 brief, Section 11: "do not reject the opportunity merely
    # because geography preference is not configured").
    # GEOGRAPHY_ALL_CURRENT_COVERAGE: no reason either - this is the
    # common, unrestricted case and adding a reason for it every time
    # would be pure noise; the absence of a geography reason for an
    # ALL_CURRENT_COVERAGE mandate IS the correct, silent "no restriction"
    # outcome (never a frozen historical council list - Section 6 of the
    # Phase B1 closure record, restated here: this reads live from
    # context.council_code, never a snapshot).
    # GEOGRAPHY_COUNCILS: the ONE new hard constraint this phase
    # introduces - a KNOWN council outside the mandate's own explicit set
    # is a known trusted fact directly contradicting an explicit mandate
    # boundary (exactly Section 4's own NOT_SUITABLE bar). An UNKNOWN
    # council (context.council_code is None) is an evidence gap, never a
    # rejection.
    if b2_active and profile.geography_scope == GEOGRAPHY_COUNCILS:
        if context.council_code is None:
            unknown.append("This opportunity's council is not available to assess against this buyer's stated geographic boundary.")
            blocking_unknown = True
        elif context.council_code in profile.geography_councils:
            matches.append(f"This opportunity's council ({context.council_code}) is within this buyer's stated geographic boundary.")
        else:
            does_not_match.append(f"This opportunity's council ({context.council_code}) is outside this buyer's explicit geographic boundary ({', '.join(sorted(profile.geography_councils))}).")

    # --- B2.2 Acquisition Type — mostly SOFT, one narrow HARD constraint ----
    #
    # Deliberately NOT a 1:1 map from facts.opportunity_type (Phase B2
    # brief, Section 14) - each acquisition type below reasons from the
    # actual facts available (planning position, affordable evidence,
    # development progress), and a multi-type mandate is compatible if
    # ANY of its stated types finds a match. STRATEGIC_LAND_CONTROL is the
    # only type capable of a hard rejection (confirmed underway-or-further
    # development AT THE SAME OPPORTUNITY SCOPE - see the scope-safety
    # note below), and AFFORDABLE_HOUSING_PACKAGE only when trusted
    # evidence explicitly shows a genuinely ZERO-affordable scheme.
    #
    # Phase B2 narrow remediation (Issue C): a mandate stating "I want
    # LAND_SITE_ACQUISITION" is a fact about the MANDATE, not about the
    # OPPORTUNITY - it does not by itself establish that any given
    # opportunity positively represents a whole/material development-site
    # acquisition context. LAND_SITE_ACQUISITION therefore contributes
    # NOTHING here (neither matches nor unknown) unless/until a genuine
    # opportunity-side fact is available to reason from; it remains one of
    # this mandate's acceptable types for the "ANY type matches" OR
    # semantics below without ever being a circular, fact-free positive
    # match on its own. Neutral is preferable to a circular reason.
    if b2_active and profile.acquisition_types:
        acquisition_type_matched = False
        acquisition_type_hard_mismatches: list[str] = []
        acquisition_type_unknowns: list[str] = []

        if STRATEGIC_LAND_CONTROL in profile.acquisition_types:
            is_strategic_situation = facts.opportunity_type == STRATEGIC_LAND or facts.planning_state in (ADOPTED_ALLOCATION, EMERGING_ALLOCATION)
            confirmed_underway_or_further = context.development_state in _DEVELOPMENT_STARTED_STATES
            # Phase B2 narrow remediation (Issue B): a hard rejection here
            # is only safe when the underway-or-further evidence is known
            # to apply to the SAME opportunity scope as the opportunity
            # being assessed (see B2MatchingContext.development_state_
            # scope_verified's own docstring) - a confirmed-underway
            # PHASE, recent permission, or long-pending application does
            # not itself prove the wider strategic-land opportunity has
            # been overtaken. Where the underway evidence exists but scope
            # is not verified, this is surfaced as worth investigating
            # rather than a confirmed hard contradiction - never
            # does_not_match on unverified scope.
            if confirmed_underway_or_further and context.development_state_scope_verified:
                acquisition_type_hard_mismatches.append(
                    "Trusted evidence shows development is already underway or further at this opportunity's own "
                    "scope, which is fundamentally incompatible with this buyer's strategic-land-control "
                    "acquisition strategy."
                )
            elif confirmed_underway_or_further:
                investigate.append(
                    "Trusted evidence shows development is underway or further, but this is not confirmed to "
                    "cover this opportunity's full relevant scope - review whether the wider strategic-land "
                    "opportunity has genuinely been overtaken by delivery, or only a part of it."
                )
                acquisition_type_unknowns.append("This opportunity's planning position does not clearly establish whether it remains an early-stage strategic-land-control opportunity, pending review of the underway evidence's own scope.")
            elif is_strategic_situation:
                matches.append("This opportunity's own planning position is consistent with this buyer's strategic-land-control acquisition strategy.")
                acquisition_type_matched = True
            else:
                # A PLANNING_DELIVERY signal that is NOT confirmed
                # underway could still represent an earlier-stage control
                # opportunity (Section 15) - never automatically excluded
                # merely for not being an allocation.
                acquisition_type_unknowns.append("This opportunity's planning position does not clearly establish whether it remains an early-stage strategic-land-control opportunity.")

        if AFFORDABLE_HOUSING_PACKAGE in profile.acquisition_types:
            if facts.affordable_percentage_trusted and facts.affordable_percentage == 0.0:
                acquisition_type_hard_mismatches.append("Trusted evidence shows this scheme has no affordable housing content at all, incompatible with this buyer's affordable-housing-package acquisition strategy.")
            elif (facts.affordable_unit_count or 0) > 0 or (facts.affordable_percentage_trusted and facts.affordable_percentage and facts.affordable_percentage > 0):
                matches.append("Trusted evidence shows this scheme includes an affordable housing component, structurally relevant to this buyer's affordable-housing-package acquisition strategy - this does not establish that the package is known to be available for acquisition.")
                acquisition_type_matched = True
            else:
                acquisition_type_unknowns.append("Affordable housing content has not been established with enough confidence to assess against this buyer's affordable-housing-package acquisition strategy.")

        if DEVELOPMENT_HOMES_ACQUISITION in profile.acquisition_types:
            # Never excluded from this dimension; confirmed underway-or-
            # further development is a positive structural signal here
            # (the opposite polarity from STRATEGIC_LAND_CONTROL above),
            # never a claim that a forward-purchase/funding or completed-
            # homes opportunity actually exists.
            #
            # Phase B2 narrow remediation (Issue C): removed the previous
            # unconditional "else" match - an opportunity that is NOT
            # confirmed underway/further has no opportunity-side fact yet
            # establishing it as a development/homes acquisition context,
            # so this dimension contributes nothing (neutral) rather than
            # matching merely because the mandate states this type.
            if context.development_state in _DEVELOPMENT_STARTED_STATES:
                matches.append("Trusted evidence shows development is underway or further, structurally compatible with this buyer's development/homes acquisition strategy - this does not establish that a forward purchase, forward funding or completed-homes opportunity actually exists.")
                acquisition_type_matched = True

        # Multi-select OR semantics: only reject if NOTHING in the set
        # matched AND at least one type was actively, hard-contradicted -
        # a mandate combining STRATEGIC_LAND_CONTROL with any other type
        # is never hard-excluded by this dimension merely because the
        # strategic-land leg alone would have been (the other type still
        # applies to the same shared facts).
        if not acquisition_type_matched and acquisition_type_hard_mismatches:
            does_not_match.extend(acquisition_type_hard_mismatches)
        elif not acquisition_type_matched:
            unknown.extend(acquisition_type_unknowns)
            if acquisition_type_unknowns:
                # Acquisition type is a stated mandate REQUIREMENT (the
                # buyer selected specific types it will acquire), not a
                # soft preference - unlike development-state appetite
                # below, a genuine evidence gap here is classification-
                # driving.
                blocking_unknown = True

    # --- B2.3 Development-State Appetite — SOFT PREFERENCE, never hard -----
    #
    # Phase B2 brief, Section 24: "Current B1 model says PREFERRED, not
    # REQUIRED" - none of these three configured values may ever append
    # to does_not_match. UNSPECIFIED contributes nothing (Section: a
    # buyer with no stated preference is neither credited nor penalised).
    if b2_active and profile.development_state_appetite != DEVELOPMENT_STATE_UNSPECIFIED:
        state = context.development_state
        confirmed_started = state in _DEVELOPMENT_STARTED_STATES
        if profile.development_state_appetite == UNCOMMENCED_PREFERRED:
            if confirmed_started:
                # SOFT mismatch - never does_not_match (Section 21/24).
                unknown.append("This buyer prefers uncommenced sites; trusted evidence shows development is already underway or further - this preference is not met, but it is not treated as a disqualifying fact on its own.")
            elif state is None or state == DEVELOPMENT_STATE_UNKNOWN:
                # EVIDENCE GAP - absence of commencement evidence is NEVER
                # treated as confirmed uncommenced (Section 19/21, the
                # mandatory evidence safeguard).
                unknown.append("No commencement evidence has been identified for this opportunity - this is not treated as confirmed non-commencement against this buyer's stated preference.")
            # else: a positively-evidenced non-commencement fact would be
            # a match here, but the current factual vocabulary has no
            # such state to read (see this module's own DEVELOPMENT_
            # STATE_* constants) - never fabricated.
        elif profile.development_state_appetite == UNDERWAY_ACCEPTABLE:
            if confirmed_started:
                matches.append("Trusted evidence shows development is underway or further - this does not count against this buyer's stated appetite.")
            elif state is None or state == DEVELOPMENT_STATE_UNKNOWN:
                unknown.append("Development progress has not been established for this opportunity.")
        elif profile.development_state_appetite == UNDERWAY_PREFERRED:
            if confirmed_started:
                matches.append("Trusted evidence shows development is underway or further, a positive signal for this buyer's stated preference.")
            elif state is None or state == DEVELOPMENT_STATE_UNKNOWN:
                unknown.append("Development progress has not been established for this opportunity - this buyer's stated preference for development progress cannot be confirmed as met.")

    # --- B2.4 Control / Ownership Appetite — SOFT, never hard ---------------
    #
    # Phase B2 brief, Section 25/32: these are commercial appetites, never
    # Gate 2C evidence states, and an empty/unconfigured set (National
    # Housebuilder today) must never become a rejection. None of these
    # four values may ever append to does_not_match - absence from the
    # set is not an exclusion (Section 28), and satisfying one never
    # resolves the underlying evidence (Section 29).
    control_facts = context.control_facts
    if b2_active and profile.control_appetite and control_facts is not None:
        if DEVELOPER_LED_ACCEPTABLE in profile.control_appetite and control_facts.developer_or_applicant_led is True:
            matches.append("Trusted evidence shows a developer/applicant-led situation, which this buyer's mandate accepts.")
        if THIRD_PARTY_INTEREST_ACCEPTABLE in profile.control_appetite and control_facts.third_party_interest_declared is True:
            matches.append("Trusted evidence shows a declared third-party ownership interest, which this buyer's mandate accepts.")
        if UNRESOLVED_OWNERSHIP_INVESTIGATABLE in profile.control_appetite and control_facts.ownership_unresolved is True:
            # investigate, not matches - the mandate accepts investigating
            # this, but the evidence itself remains genuinely unresolved
            # (Section 29 - never transformed into positive control
            # evidence).
            investigate.append("Ownership/control evidence for this opportunity remains unresolved; this buyer's mandate treats unresolved ownership as worth investigating rather than a disqualifying fact.")
        if PARTIAL_SITE_CONTROL_ACCEPTABLE in profile.control_appetite and control_facts.partial_control_evidence is True:
            matches.append("Trusted evidence indicates a partial/shared ownership position, which this buyer's mandate does not require to be whole-site control.")

    # Phase B2 narrow remediation (Issue A): classification is driven by
    # `blocking_unknown`, not by the mere presence of ANY reason in
    # `unknown` - a soft/contextual unknown (currently only the four
    # development-state-appetite reasons above) stays visible in the
    # `unknown` bucket for transparency but never by itself prevents
    # STRONG_FIT for an opportunity that satisfies every classification-
    # driving requirement.
    if does_not_match:
        classification = NOT_SUITABLE
    elif blocking_unknown:
        classification = INSUFFICIENT_EVIDENCE
    else:
        classification = STRONG_FIT

    return BuyerFitAssessment(
        classification=classification, is_investigative_exception=is_investigative_exception,
        matches=matches, does_not_match=does_not_match, unknown=unknown, investigate=investigate,
    )
