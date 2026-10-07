"""TRANSITION-ONLY: the same-universe v6/v7 parity oracle for the V7C stale-mandate re-onboarding (see verification/transition/frozen_v6_matcher.py for provenance,
independence and the REMOVAL lifecycle). Called only by scripts/reonboard_stale_mandates.py and tests; the application never imports it.

For every opportunity it feeds the frozen v6 matcher EXACTLY the facts, mandate policy and b2 context object the v7 evaluation just used, and compares ONLY the approved
parity boundary: classification and the investigative flag. Reason text is expected to differ (V7A) and is never compared.
"""
from __future__ import annotations

from app.policy.mandate_reonboarding import ParityVerdict
from verification.transition.frozen_v6_matcher import assess_buyer_fit as frozen_v6_assess_buyer_fit


def v6_parity_oracle(policy, record, context, v7_assessment) -> ParityVerdict:
    v6 = frozen_v6_assess_buyer_fit(policy, record.matching_facts, context=context)
    classification_equal = v6.classification == v7_assessment.classification
    investigative_equal = bool(v6.is_investigative_exception) == bool(v7_assessment.is_investigative_exception)
    if classification_equal and investigative_equal:
        return ParityVerdict(True, True)
    return ParityVerdict(classification_equal, investigative_equal, detail="v6 oracle differs from v7",
                         v6_classification=v6.classification, v7_classification=v7_assessment.classification,
                         v6_investigative=bool(v6.is_investigative_exception), v7_investigative=bool(v7_assessment.is_investigative_exception))
