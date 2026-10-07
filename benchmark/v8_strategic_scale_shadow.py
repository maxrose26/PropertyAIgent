"""Stage 2.5B final slice: PROPOSED strategic-scale benchmark cases + SHADOW evaluation (offline, deterministic; no database, network or model). NEVER imported by app/.

For each proposed strategic capacity case it shows, side by side, what the FROZEN v7 oracle says (the legacy scalar: maximum_capacity or minimum_dwellings, indicative ignored) and what the
v8 matcher says (the allocation's capacity through proper count semantics, app.reporting.strategic_capacity). The
difference is the evidence REVIEW needs to decide on a BUYER_MATCHING_POLICY_VERSION 7 -> 8 transition. Nothing here is approved: ``approved_by_product_owner`` is False and the proposed
intended outcomes are for REVIEW to accept, change or reject.

Finding the shadow run exposes (a regression a naive switch would cause): the matcher's explicit strategic large-allocation route (``large_allocation_is_self_qualifying``) exists only on its SCALAR
path; a range or minimum-only capacity above the preferred maximum would fall to the generic "outside discovery" result for the Strategic Land Buyer. A matcher change (hence a policy version
bump) would therefore be needed, not only a data-representation change.
"""
from __future__ import annotations

import dataclasses
from types import SimpleNamespace

from app.policy.buyer_matching import assess_buyer_fit, build_strategic_land_matching_facts
from app.policy.buyer_profiles import BUYER_PROFILES
from app.reporting.strategic_capacity import strategic_capacity_assessment
from verification.transition.v7_parity import differential_category

APPROVED_BY_PRODUCT_OWNER = True   # approved by Product Owner REVIEW with the 24-row table (benchmark/v8_expectation_table.APPROVAL_RECORD)


def _allocation(minimum, indicative, maximum):
    plan = SimpleNamespace(status="adopted")
    return SimpleNamespace(minimum_dwellings=minimum, indicative_capacity=indicative, maximum_capacity=maximum, intended_use="residential", local_plan=plan, plan_status="adopted",
                           matched_site_id=None)


# (case id, buyer, (minimum, indicative, maximum), what the Product Owner list called it, PROPOSED intended outcome for REVIEW)
CASES = (
    ("S1_exact_inside_preferred", "nesten_homes", (150, None, 150), "exact plan-stated capacity inside preferred", "STRONG_FIT"),
    ("S2_indicative_only_inside_preferred", "nesten_homes", (None, 160, None), "approximate/indicative capacity inside preferred", "REVIEW_TO_DECIDE (existing unbounded-estimate semantics give INSUFFICIENT)"),
    ("S3_range_inside_preferred", "nesten_homes", (80, None, 150), "range entirely inside preferred", "STRONG_FIT (range proven within preferred)"),
    ("S4_range_crossing_preferred_discovery", "nesten_homes", (150, None, 210), "range crossing preferred/discovery boundary", "POSSIBLE_FIT"),
    ("S5_range_spanning_outside_discovery", "nesten_homes", (60, None, 300), "range spanning inside and outside discovery", "INSUFFICIENT_EVIDENCE+investigative"),
    ("S6_minimum_only", "nesten_homes", (150, None, None), "minimum-only capacity", "INSUFFICIENT_EVIDENCE (a floor cannot prove fit within a ceiling)"),
    ("S7_maximum_only", "nesten_homes", (None, None, 150), "maximum-only capacity", "INSUFFICIENT_EVIDENCE (a ceiling cannot prove the floor)"),
    ("S8_malformed_conflicting", "nesten_homes", (300, None, 100), "malformed/conflicting capacity", "INSUFFICIENT_EVIDENCE (fail closed)"),
    ("S9a_self_qualifying_exact", "strategic_land_buyer", (2000, None, 2000), "Strategic Land Buyer explicit self-qualifying route (exact)", "STRONG_FIT (route preserved)"),
    ("S9b_self_qualifying_range", "strategic_land_buyer", (1500, None, 2500), "Strategic Land Buyer explicit self-qualifying route (range above maximum)", "STRONG_FIT (route must be preserved)"),
    ("S9c_self_qualifying_minimum_only", "strategic_land_buyer", (2000, None, None), "Strategic Land Buyer explicit self-qualifying route (minimum-only above maximum)", "STRONG_FIT (route must be preserved)"),
    ("S10_nesten_very_large_allocation", "nesten_homes", (2000, None, 2000), "Nesten strategic allocation far above discovery", "INSUFFICIENT_EVIDENCE+investigative"),
)


def _label(assessment) -> str:
    return assessment.classification + ("+investigative" if assessment.is_investigative_exception else "")


def evaluate_case(case) -> dict:
    case_id, buyer, (minimum, indicative, maximum), description, proposed = case
    allocation, policy = _allocation(minimum, indicative, maximum), BUYER_PROFILES[buyer]
    v8_facts = dataclasses.replace(build_strategic_land_matching_facts(allocation, None, None), has_identified_planning_activity=False)   # an allocation with a coverage result of 'no identified activity'
    capacity = strategic_capacity_assessment(allocation)
    v8 = assess_buyer_fit(policy, v8_facts)
    category, v7 = differential_category(policy, v8_facts, None, v8)
    return {"case_id": case_id, "buyer": buyer, "description": description, "stored_figures": {"minimum": minimum, "indicative": indicative, "maximum": maximum},
            "capacity_semantics": {"precision": capacity.precision, "value": capacity.value, "lower": capacity.lower, "upper": capacity.upper, "resolution": capacity.resolution},
            "legacy_unit_count": v8_facts.unit_count, "frozen_v7_result": _label(v7), "v8_result": _label(v8), "differential_category": category, "proposed_intended_outcome_for_review": proposed}


def run_shadow() -> dict:
    """Frozen v7 oracle (legacy scalar, no count semantics) vs the live v8 matcher on the SAME strategic facts."""
    rows = [evaluate_case(case) for case in CASES]
    return {"approved_by_product_owner": APPROVED_BY_PRODUCT_OWNER, "rows": rows, "differences": [r["case_id"] for r in rows if r["frozen_v7_result"] != r["v8_result"]],
            "unexpected_regressions": [r["case_id"] for r in rows if r["differential_category"] == "UNEXPECTED_REGRESSION"]}
