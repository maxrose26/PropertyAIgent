"""Stage 2.5B final slice: the USER-FACING opportunity-signal wording, with residual / coverage arithmetic neutralised.

Product Owner ruling: never present an acquisition inference by subtracting planning/application counts from an allocation capacity (overlapping scopes, amendments, phased permissions,
non-comparable counts, unknown boundaries, delivery already occurring, no proof the difference is available land). The Stage 3A coverage figures remain an INTERNAL diagnostic: they still
select the signal (INVESTIGATE / MONITOR / LOWER_PRIORITY) through the unchanged ``build_opportunity_signal``; this wrapper only rewrites what the user is shown.

Implemented as a wrapper (not an edit of allocation_development_coverage) because that module is whole-file pinned by the frozen v6 parity oracle (verification/transition), which must not drift.
"""
from __future__ import annotations

import re

from app.reporting.allocation_development_coverage import build_opportunity_signal

PLANNING_ACTIVITY_IDENTIFIED_REASON = "Planning activity has been identified within this allocation."
_CAPACITY_REASON = re.compile(r"^((?:Adopted|Emerging) residential allocation) with capacity of approximately ([\d,]+) homes\.$")
_COVERAGE_ARITHMETIC = (
    re.compile(r"of capacity is represented by identified planning activity"),
    re.compile(r"of allocation capacity are not currently accounted for"),
    re.compile(r"Capacity appears fully accounted for by identified planning activity"),
)


def build_neutral_opportunity_signal(*, plan_status_bucket, coverage, phasing) -> dict:
    """Same signal as build_opportunity_signal; reasons rewritten: the capacity statement is qualified as plan-stated and unverified, and every coverage-percentage / residual / 'fully
    accounted for' statement is replaced by the single neutral planning-activity statement (once). All other reasons (phasing, ownership caveat, status) are unchanged."""
    raw = build_opportunity_signal(plan_status_bucket=plan_status_bucket, coverage=coverage, phasing=phasing)
    reasons: list[str] = []
    for reason in raw["reasons"]:
        match = _CAPACITY_REASON.match(reason)
        if match:
            reasons.append(f"{match.group(1)} with plan-stated capacity of approximately {match.group(2)} homes (unverified).")
        elif any(pattern.search(reason) for pattern in _COVERAGE_ARITHMETIC):
            if PLANNING_ACTIVITY_IDENTIFIED_REASON not in reasons:
                reasons.append(PLANNING_ACTIVITY_IDENTIFIED_REASON)
        else:
            reasons.append(reason)
    return {**raw, "reasons": reasons}
