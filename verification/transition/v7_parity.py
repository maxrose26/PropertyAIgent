"""TRANSITION-ONLY: the same-universe v7/v8 differential gate (see verification/transition/frozen_v7_matcher.py for provenance, independence and the REMOVAL lifecycle). Called only by
scripts/reonboard_stale_mandates.py, benchmark/shadow tooling and tests; the application never imports it.

For every opportunity it feeds the frozen v7 matcher the SAME facts the v8 evaluation used, except that STRATEGIC facts are given ``count_assessment=None`` (v7 never carried capacity
semantics for strategic allocations: it read only the legacy scalar ``unit_count``). The classification + investigative flag are then compared and every difference is placed in exactly one
category. Reason text is never compared.

Categories:
  EQUAL                          identical classification and investigative flag.
  EXPECTED_STRATEGIC_DELTA       strategic subject, plan-stated capacity kind other than EXACT (the approved v8 STRATEGIC_CAPACITY_SEMANTICS change), and NOT the preserved
                                 large-allocation route (a Strategic Land Buyer whose plan-stated LOWER bound is above the discovery maximum must show NO delta).
  UNEXPECTED_REGRESSION          anything else: any planning-delivery difference, any EXACT strategic difference, any preserved-route difference.
Residual-subject additions are not matcher deltas: they appear only as new subjects in the family differential (V8-B) and are classified there.
"""
from __future__ import annotations

import dataclasses

from app.policy.buyer_matching import STRATEGIC_LAND, discovery_bounds
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
    if facts.opportunity_type == STRATEGIC_LAND and facts.count_assessment is not None and facts.count_assessment.precision != "EXACT" and not _preserved_large_allocation_route(policy, facts):
        return EXPECTED_STRATEGIC_DELTA, v7
    return UNEXPECTED_REGRESSION, v7


def v7_parity_oracle(policy, record, context, v8_assessment) -> ParityVerdict:
    """Re-onboarding oracle: acceptable when equal or an EXPECTED strategic delta; anything else is a parity failure."""
    category, v7 = differential_category(policy, record.matching_facts, context, v8_assessment)
    if category != UNEXPECTED_REGRESSION:
        return ParityVerdict(True, True, detail=category)
    return ParityVerdict(v7.classification == v8_assessment.classification, bool(v7.is_investigative_exception) == bool(v8_assessment.is_investigative_exception),
                         detail="v7 oracle differs from v8 outside the approved strategic deltas", v6_classification=v7.classification, v7_classification=v8_assessment.classification,
                         v6_investigative=bool(v7.is_investigative_exception), v7_investigative=bool(v8_assessment.is_investigative_exception))
