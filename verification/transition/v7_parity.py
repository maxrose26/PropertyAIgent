"""TRANSITION-ONLY: the same-universe v7/v8 differential gate (see verification/transition/frozen_v7_matcher.py for provenance, independence and the REMOVAL lifecycle). Called only by
scripts/reonboard_stale_mandates.py, benchmark/shadow tooling and tests; the application never imports it.

For every opportunity it feeds the frozen v7 matcher the SAME facts the v8 evaluation used, except that STRATEGIC facts are given ``count_assessment=None`` (v7 never carried capacity
semantics for strategic allocations: it read only the legacy scalar ``unit_count``). The classification + investigative flag are then compared and every difference is placed in exactly one
category. Reason text is never compared.

Categories:
  EQUAL                          identical classification and investigative flag.
  EXPECTED_STRATEGIC_DELTA       strategic subject, non-EXACT plan-stated capacity, NOT the preserved large-allocation route (a Strategic Land Buyer whose plan-stated LOWER bound is
                                 above the discovery maximum must show NO delta), AND one of exactly four approved transitions (see _approved_strategic_transition: (a) added investigative flag, (b) STRONG/POSSIBLE -> INSUFFICIENT_EVIDENCE, (c) unknown capacity
                                 drops v7's scalar-derived flag, (d) bounded-range STRONG -> POSSIBLE + flag). No upgrade and no new NOT_SUITABLE.
  UNEXPECTED_REGRESSION          anything else: any planning-delivery difference, any EXACT strategic difference, any preserved-route difference.
Residual-subject additions are not matcher deltas: they appear only as new subjects in the family differential (V8-B) and are classified there.
"""
from __future__ import annotations

import dataclasses

from app.policy.buyer_matching import INSUFFICIENT_EVIDENCE, POSSIBLE_FIT, STRATEGIC_LAND, STRONG_FIT, discovery_bounds
from app.policy.mandate_reonboarding import ParityVerdict
from verification.transition.frozen_v7_matcher import assess_buyer_fit as frozen_v7_assess_buyer_fit

EQUAL = "EQUAL"
EXPECTED_STRATEGIC_DELTA = "EXPECTED_STRATEGIC_DELTA"
UNEXPECTED_REGRESSION = "UNEXPECTED_REGRESSION"


def v7_oracle_facts(facts):
    """The facts exactly as v7 saw them: strategic facts without count semantics (legacy scalar only); every other facts object unchanged."""
    if facts.opportunity_type == STRATEGIC_LAND and facts.count_assessment is not None:
        return dataclasses.replace(facts, count_assessment=None)
    return facts


def _preserved_large_allocation_route(policy, facts) -> bool:
    assessment = facts.count_assessment
    if facts.opportunity_type != STRATEGIC_LAND or assessment is None or not policy.large_allocation_is_self_qualifying:
        return False
    _, discovery_max = discovery_bounds(policy.target_unit_min, policy.target_unit_max)
    return assessment.precision == "RANGE" and assessment.lower is not None and discovery_max is not None and assessment.lower > discovery_max


def differential_category(policy, facts, context, v8_assessment) -> tuple[str, object]:
    """(category, v7 assessment) for one subject. Same facts, mandate policy and context for both matchers."""
    v7 = frozen_v7_assess_buyer_fit(policy, v7_oracle_facts(facts), context=context)
    if v7.classification == v8_assessment.classification and bool(v7.is_investigative_exception) == bool(v8_assessment.is_investigative_exception):
        return EQUAL, v7
    if (facts.opportunity_type == STRATEGIC_LAND and facts.count_assessment is not None and facts.count_assessment.precision != "EXACT"
            and not _preserved_large_allocation_route(policy, facts) and _approved_strategic_transition(v7, v8_assessment, facts.count_assessment)):
        return EXPECTED_STRATEGIC_DELTA, v7
    return UNEXPECTED_REGRESSION, v7


def _approved_strategic_transition(v7, v8, assessment) -> bool:
    """ONLY the approved v7 -> v8 strategic capacity-semantics changes, each tied to the plan-stated capacity KIND (``assessment``, never EXACT here):
      (a) unchanged classification where v8 ADDS the investigative flag (existing uncertain-count semantics now apply to a range / open bound / estimate);
      (b) a v7 STRONG_FIT or POSSIBLE_FIT that v8 reports as INSUFFICIENT_EVIDENCE (a floor, ceiling, estimate or malformed figure no longer proves a scale fit), either flag;
      (c) a MALFORMED / unknown capacity (precision UNKNOWN) staying INSUFFICIENT_EVIDENCE where v8 drops the investigative flag v7 derived from an unusable scalar (fail closed);
      (d) a bounded RANGE (both bounds stated) taking v7 STRONG_FIT to v8 POSSIBLE_FIT with the investigative flag added (the range is not wholly inside the preferred range).
    Everything else - any upgrade, any NOT_SUITABLE that v7 did not already have, any other downgrade, any removed investigative flag on a usable capacity - is NOT approved."""
    c7, c8 = v7.classification, v8.classification
    f7, f8 = bool(v7.is_investigative_exception), bool(v8.is_investigative_exception)
    if c7 == c8:
        if f8 and not f7:
            return True                                                                                            # (a)
        return c8 == INSUFFICIENT_EVIDENCE and f7 and not f8 and assessment.precision == "UNKNOWN"                # (c)
    if c8 == INSUFFICIENT_EVIDENCE and c7 in (STRONG_FIT, POSSIBLE_FIT):
        return True                                                                                                # (b)
    return (c7 == STRONG_FIT and c8 == POSSIBLE_FIT and f8 and assessment.precision == "RANGE"
            and assessment.lower is not None and assessment.upper is not None)                                    # (d)


def v7_parity_oracle(policy, record, context, v8_assessment) -> ParityVerdict:
    """Re-onboarding oracle: acceptable when equal or an EXPECTED strategic delta; anything else is a parity failure."""
    category, v7 = differential_category(policy, record.matching_facts, context, v8_assessment)
    if category != UNEXPECTED_REGRESSION:
        return ParityVerdict(True, True, detail=category)
    return ParityVerdict(v7.classification == v8_assessment.classification, bool(v7.is_investigative_exception) == bool(v8_assessment.is_investigative_exception),
                         detail="v7 oracle differs from v8 outside the approved strategic deltas", v6_classification=v7.classification, v7_classification=v8_assessment.classification,
                         v6_investigative=bool(v7.is_investigative_exception), v7_investigative=bool(v8_assessment.is_investigative_exception))


# V8-B hardening: the frozen oracle imports MatchingFacts / B2MatchingContext LIVE (they only ever ADD optional fields the v7 body never reads). Pin the exact accepted v8 definitions so a later
# classification-affecting change to either fails a test instead of silently flowing into the "oracle". Re-pinning is a deliberate, reviewed act.
LIVE_DEPENDENCY_PINS = {
    "MatchingFacts": "1a7a51339af42eae8ba7847f7104a6a36ca6146fe73b29819dbca1ba760f2be6",
    "B2MatchingContext": "3c635ad6023432519acd18d453b8d9a388f0bba97afe65b1c63234b14603b5d4",
}
