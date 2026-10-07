"""TRANSITION-ONLY, IMMUTABLE: the frozen accepted-v6 buyer matcher, used ONLY as the independent oracle for the V7C same-universe v6/v7 parity check.

This is NOT application policy, NOT a fallback matcher and NOT a public API. Normal application code uses the v7 matcher (app.policy.buyer_matching) exclusively and must never
import this module (the application never imports `verification`; a test enforces it). Only the transition parity tooling (scripts/reonboard_stale_mandates.py via
verification.transition.v6_parity) and tests may call it.

DO NOT MODIFY. Future feature work must not edit this file or its pins. LIFECYCLE: it may remain through the production dry runs, the v7 transition and the immediate rollback window;
once v7 activation is accepted and the rollback window closes it is REMOVED in a dedicated cleanup (together with verification/transition/v6_parity.py and its tests).

PROVENANCE (immutable; recorded in PROVENANCE below and re-verified by tests/test_v7c_frozen_v6_oracle.py):
  source commit   3cce0815fd6d243993edf5ca511094ae3a795285 (master immediately before the first V7A commit d0a62da)
  source file     app/policy/buyer_matching.py
  source blob     2bb36a12d1b828d2b2bee3d9d58621cdb7057d50   (git blob id of the whole file at that commit)
  source function assess_buyer_fit, lines 821-1394 of that blob
  function sha256 0003d20e05a1ac279c56059c6f726f7473ad1951a2e464e25ae84660347fbd83
  extraction      `git show <commit>:<file>` -> ast.get_source_segment of the module-level function, copied VERBATIM (no edit of any character); extracted once by the audit generator
                  (verification/transition/audit_extract_frozen_v6.py). Reproduce: sha256 of the segment equals FUNCTION_SHA256 below.

INDEPENDENCE: classification-affecting logic is the verbatim v6 function body. The module-level names the function references were compared with v7: all are byte-identical
definitions except B2MatchingContext (v7 only ADDED optional fields the v6 body never reads). Those identical definitions are imported from app.policy.buyer_matching rather than copied;
DEPENDENCY_PINS records the sha256 of each v6 definition and the test recomputes the CURRENT definition and fails if any drifts, so the oracle can never silently delegate to changed logic.
The imported-name modules (buyer_profiles, commercial_evidence) and the modules reached indirectly through the helpers it calls (residential_count, scheme_reconciliation,
allocation_development_coverage) are pinned by whole-file sha256 (LF-normalised); indirectly reached buyer_matching definitions (ControlAppetiteFacts, AFFORDABLE_STATE_UNKNOWN,
DEFAULT_DISCOVERY_TOLERANCE_PERCENT) are pinned by definition hash.
"""
from __future__ import annotations

from app.policy.buyer_matching import (
    AFFORDABLE_STATE_WHOLLY,
    B2MatchingContext,
    BuyerFitAssessment,
    DEVELOPMENT_STATE_UNKNOWN,
    INSUFFICIENT_EVIDENCE,
    MatchingFacts,
    NOT_SUITABLE,
    POSSIBLE_FIT,
    STRATEGIC_LAND,
    STRONG_FIT,
    _DEVELOPMENT_STARTED_STATES,
    _planning_state_label,
    discovery_bounds,
)
from app.policy.buyer_profiles import (
    ADOPTED_ALLOCATION,
    AFFORDABLE_HOUSING_PACKAGE,
    AFFORDABLE_UNITS,
    BuyerMandatePolicy,
    DEVELOPER_LED_ACCEPTABLE,
    DEVELOPMENT_HOMES_ACQUISITION,
    DEVELOPMENT_STATE_UNSPECIFIED,
    EMERGING_ALLOCATION,
    GEOGRAPHY_COUNCILS,
    OTHER_OR_UNKNOWN,
    PARTIAL_SITE_CONTROL_ACCEPTABLE,
    PERMISSION_GRANTED,
    STRATEGIC_LAND_CONTROL,
    THIRD_PARTY_INTEREST_ACCEPTABLE,
    UNCOMMENCED_PREFERRED,
    UNDERWAY_ACCEPTABLE,
    UNDERWAY_PREFERRED,
    UNRESOLVED_OWNERSHIP_INVESTIGATABLE,
    WHOLLY_AFFORDABLE_THRESHOLD,
)
from app.reporting.commercial_evidence import known_unit_count

PROVENANCE = {
    "source_commit": "3cce0815fd6d243993edf5ca511094ae3a795285",
    "source_file": "app/policy/buyer_matching.py",
    "source_blob": "2bb36a12d1b828d2b2bee3d9d58621cdb7057d50",
    "source_function": "assess_buyer_fit",
    "source_lines": (821, 1394),
    "function_sha256": "0003d20e05a1ac279c56059c6f726f7473ad1951a2e464e25ae84660347fbd83",
    "policy_version_at_source": 6,
    "extraction": "git show <commit>:<file>; ast.get_source_segment of the module-level function; verbatim copy",
}
FUNCTION_SHA256 = PROVENANCE["function_sha256"]

# sha256 of each v6 module-level definition the function references (B2MatchingContext excluded: v7 only added optional fields the v6 body never reads).
DEPENDENCY_PINS = {    "AFFORDABLE_STATE_UNKNOWN": "005c04b8d491d59f89ec1f0976c7f5d95b21e39ad67ba8a17914fd696266bb7c",
    "AFFORDABLE_STATE_WHOLLY": "6e3ceaaa16d7b7504b44f4c50b6fa1702b0ee02e715d3a22fdc17567ac9fa879",
    "BuyerFitAssessment": "99048b668eed62f7f2b8e656fee5238526740dcdb1aa255fe113a7d24169dea3",
    "ControlAppetiteFacts": "61e7e697521838604ce93dd2b395a2e1a7cd2637ad79a6bf42a5b1363cce2744",
    "DEFAULT_DISCOVERY_TOLERANCE_PERCENT": "391c22485818115aba852802a664117bd5e74d6e178b2e401c3e3ad433ad174f",
    "DEVELOPMENT_STATE_UNKNOWN": "92ddb49b7b0c9f9a43b3f7463d95058ae68a6ca60c2fd16f2698adbecc07291c",
    "INSUFFICIENT_EVIDENCE": "9a141f6b50fd56d0a0dc49cb7d2306f96c994bfeb2f74be38d42ffd0c6f53e75",
    "MatchingFacts": "1a7a51339af42eae8ba7847f7104a6a36ca6146fe73b29819dbca1ba760f2be6",
    "NOT_SUITABLE": "76a19432165cbd19cb3b4016ad525283878afd046fe8342684854dd2c9aabaaa",
    "POSSIBLE_FIT": "eb7003d7c6727fe8bcf9d94cfe75c845aad52a14211818e0c524a6f0f8e70143",
    "STRATEGIC_LAND": "579219a6c7373dffdfd41ea0fb25607e427fc2d673363b968c4258be67baa0a7",
    "STRONG_FIT": "b3af91accb4bf4649da4691a1b46ff0a8dda85ed3f84be2602bd862e75408b10",
    "_DEVELOPMENT_STARTED_STATES": "cae2794be517391bc2d2c6e33633d692e8bd9c5095512504ca46be648f4016e3",
    "_planning_state_label": "ddfba1083f13fcf543f26a506a8506bf39adcace7be231c87e11341ee8074269",
    "discovery_bounds": "fba20a4bd22f7b555ae28694908dd61a2d09f21e62b793671fe2da1d8dc95610",
}

# sha256 (LF-normalised) of the supporting modules whose names the function imports indirectly, as at the source commit.
SUPPORTING_MODULE_SHA256 = {    "app/policy/buyer_profiles.py": "c85ff74791a21a042a50a5599b59c9f1c46bbdd4ab490b599c1eddaf46f6a03c",
    "app/reporting/allocation_development_coverage.py": "442c71bf20922cbf4b5b3a80c9314fd89ae939e62bdba0fcc97757651d059112",
    "app/reporting/commercial_evidence.py": "4f9f343e345ef2399516860a1d493888817be06ce2f4b8e13d77ce060e58725b",
    "app/reporting/residential_count.py": "ce2a778b1f13038180c27642c4955ccd39c61ff869474853290f4d480aa7c073",
    "app/reporting/scheme_reconciliation.py": "9eaafa1d502acc12be56a19a4b0d701c9ada132f778a842df547905eb5af62d1",
}


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
    wholly_by_percentage = facts.affordable_percentage is not None and facts.affordable_percentage >= WHOLLY_AFFORDABLE_THRESHOLD
    wholly_by_counts = facts.whole_site_affordable_state == AFFORDABLE_STATE_WHOLLY
    if wholly_by_percentage or wholly_by_counts:
        # The percentage wording is kept where a trusted percentage exists; same-scope exact counts state the
        # proposition without inventing a percentage.
        descriptor = (f"wholly ({facts.affordable_percentage:.0f}%)" if wholly_by_percentage
                      else "wholly (every residential unit is affordable)")
        if profile.wholly_affordable_is_exclusion:
            does_not_match.append(
                f"Trusted evidence shows this is a {descriptor} affordable-led "
                f"scheme, not open-market residential development."
            )
        elif profile.scale_metric == AFFORDABLE_UNITS:
            # Only a buyer whose OWN scale is measured in affordable homes (Housing Association) reads
            # wholly-affordable evidence as on-strategy.
            matches.append(
                f"Trusted evidence shows this is a {descriptor} affordable-led "
                f"scheme, directly relevant to this buyer's affordable-housing focus."
            )
        else:
            # No stated exclusion AND no stated affordable-housing focus (e.g. Nesten, whose real brief is
            # silent on affordable composition): visible context only - never a match, never an exclusion.
            unknown.append(
                f"Trusted evidence shows this is a {descriptor} affordable-led "
                f"scheme; this buyer has not stated an exclusion for it, so it is context to investigate, "
                f"not a fit signal."
            )
            investigate.append("Confirm the affordable composition and whether the scheme suits this buyer's requirement.")
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
            # Stage 2.5A (v6, N1-B): a missing/unqualified percentage is a visible
            # evidence gap, not proof of a problem. It no longer blocks fit on its
            # own: the wholly-affordable exclusion above still needs positive
            # evidence, and mandates that need affordable QUANTUM (affordable-unit
            # scale, AFFORDABLE_HOUSING_PACKAGE) keep those requirements below.
            unknown.append("Affordable housing proportion has not been confirmed - not assumed to be 0%.")
            investigate.append("Confirm the affordable housing proportion and whether the scheme is affordable-led.")
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
        scale_value = known_unit_count(facts.unit_count)
        unit_noun = "homes"
        no_count_message = "No trusted unit count is available to assess against this buyer's target range."

    assessment = facts.count_assessment if profile.scale_metric != AFFORDABLE_UNITS else None
    uncertain_scale = assessment is not None and assessment.precision in ("APPROXIMATE", "RANGE")
    if assessment is not None:
        # A rounded/stale scalar cannot override the shared evidence assessment.
        scale_value = assessment.exact_value
    # Stage 2.5A: preferred range vs discovery envelope. Tolerance only widens
    # SOFT preferences: an explicit hard minimum (below_minimum_scale_is_
    # exclusion) stays at the buyer's stated minimum.
    preferred_text = f"{profile.target_unit_min}-{profile.target_unit_max} {unit_noun}"
    discovery_min, discovery_max = discovery_bounds(profile.target_unit_min, profile.target_unit_max)
    if profile.below_minimum_scale_is_exclusion:
        discovery_min = profile.target_unit_min
    discovery_text = f"{discovery_min}-{discovery_max} {unit_noun}"
    outside_discovery_text = (
        f"is outside this buyer's discovery range ({discovery_text}; preferred {preferred_text}) - investigate "
        f"whether a relevant phase or acquisition sub-scope exists; this subject is not itself a preferred or "
        f"possible scale fit."
    )
    scale_possible = scale_outside_discovery = False
    if scale_value is None and uncertain_scale:
        preferred_fit = assessment.within_hard_bounds(minimum=profile.target_unit_min, maximum=profile.target_unit_max)
        discovery_fit = assessment.within_hard_bounds(minimum=discovery_min, maximum=discovery_max)
        # Existing minimum exclusion remains hard, at the stated minimum.
        hard_minimum_fit = (assessment.within_hard_bounds(minimum=profile.target_unit_min)
                            if profile.below_minimum_scale_is_exclusion else True)
        if hard_minimum_fit is False:
            does_not_match.append("Supported scale is below this buyer's hard minimum.")
        elif preferred_fit is True:
            unknown.append(f"{assessment.label()}: uncertain discovery scale; exact mandate compliance unverified. " + assessment.note())
        elif discovery_fit is True:
            scale_possible = True
            matches.append(
                f"{assessment.label()} - not fully within this buyer's preferred range ({preferred_text}), but wholly "
                f"within its discovery range ({discovery_text}). " + assessment.note()
            )
        elif discovery_fit is False:
            scale_outside_discovery = True
            investigate.append(f"The supported scale ({assessment.label()}) " + outside_discovery_text)
        else:
            blocking_unknown = True
            unknown.append(
                f"{assessment.label()}: the supported evidence does not establish whether scale is within this "
                f"buyer's discovery range ({discovery_text}). " + assessment.note()
            )
        if hard_minimum_fit is None:
            blocking_unknown = True
        investigate.append("Verify current subject scale before treating this lead as numerically qualified.")
        is_investigative_exception = True
    elif scale_value is None:
        unknown.append(no_count_message)
        blocking_unknown = True
    elif profile.target_unit_min <= scale_value <= profile.target_unit_max:
        matches.append(f"Approximately {scale_value:,} {unit_noun} sits within this buyer's target range ({profile.target_unit_min}-{profile.target_unit_max} {unit_noun}).")
    elif scale_value < profile.target_unit_min and profile.below_minimum_scale_is_exclusion:
        # Housing Association amendment: an explicit hard minimum (e.g. "fewer
        # than 50 affordable homes is NOT SUITABLE") - never moved to the
        # discovery floor.
        does_not_match.append(
            f"Trusted evidence shows only {scale_value:,} {unit_noun}, below this buyer's minimum "
            f"requirement of {profile.target_unit_min} {unit_noun}."
        )
    elif discovery_min <= scale_value <= discovery_max:
        scale_possible = True
        side = "below" if scale_value < profile.target_unit_min else "above"
        matches.append(
            f"{scale_value:,} {unit_noun} is slightly {side} this buyer's preferred range ({preferred_text}), "
            f"but within its discovery range ({discovery_text})."
        )
    elif (scale_value > profile.target_unit_max and profile.large_allocation_is_self_qualifying
          and facts.opportunity_type == STRATEGIC_LAND):
        # An explicit mandate rule (unchanged): a large strategic allocation
        # qualifies in its own right for this buyer, independent of parcel size.
        matches.append(
            f"This allocation's own scale (~{scale_value:,} {unit_noun}) represents a meaningful "
            f"strategic-land position in its own right, independent of whether a specific parcel size "
            f"is confirmed."
        )
        investigate.append("Establish whether a suitable development parcel/phase could become available within this buyer's target range.")
        is_investigative_exception = True
    else:
        # Stage 2.5A: a KNOWN count outside the soft discovery envelope. The
        # count itself is not in doubt; whether the wider scheme contains a
        # relevant acquisition sub-scope is (Stage 2.5B decomposition), so the
        # subject stays visible as an investigative exception, never
        # NOT_SUITABLE and never STRONG/POSSIBLE.
        scale_outside_discovery = True
        investigate.append(f"{scale_value:,} {unit_noun} " + outside_discovery_text)
        if scale_value > profile.target_unit_max and facts.has_phasing_evidence:
            investigate.append("Evidence of phased delivery exists for this opportunity - review whether a phase within this buyer's target range could be available.")
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
    # Stage 2.5A precedence: hard exclusion > blocking uncertainty > known
    # subject outside the soft discovery envelope (investigate for sub-scope)
    # > within discovery but outside preferred (POSSIBLE_FIT) > STRONG_FIT.
    if does_not_match:
        classification = NOT_SUITABLE
    elif blocking_unknown or scale_outside_discovery:
        classification = INSUFFICIENT_EVIDENCE
    elif scale_possible:
        classification = POSSIBLE_FIT
    else:
        classification = STRONG_FIT

    return BuyerFitAssessment(
        classification=classification, is_investigative_exception=is_investigative_exception,
        matches=matches, does_not_match=does_not_match, unknown=unknown, investigate=investigate,
    )
