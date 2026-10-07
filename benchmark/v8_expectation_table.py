"""Stage 2.5B V8: the COMPLETE proposed v8 benchmark expectation table (strategic cases + residual cases), assembled for REVIEW. Offline and deterministic; NEVER imported by app/.

``approved_by_product_owner`` is False for every row: nothing here is approved. Each row carries the route, the evidence facts, the frozen-v7 result where applicable, the proposed v8
classification / investigative flag, the residual level, the representative expectation, the rationale and the prohibited inferences the case checks. Expectations are never adjusted to
match the implementation: ``disagreements`` lists any row where the live evaluation differs from its proposed expectation (it must be empty, else the case is reported to REVIEW).
"""
from __future__ import annotations

from benchmark.v8_residual_cases import run_residual_benchmark
from benchmark.v8_strategic_scale_shadow import CASES as STRATEGIC_CASES, run_shadow

APPROVED_BY_PRODUCT_OWNER = False

# PROPOSED v8 outcome per strategic case (for REVIEW to accept, change or reject): (classification+investigative label, representative expectation, rationale)
STRATEGIC_EXPECTATIONS = {
    "S1_exact_inside_preferred": ("STRONG_FIT", "the strategic allocation family subject", "an exact plan-stated capacity inside the preferred range is unchanged from v7"),
    "S2_indicative_only_inside_preferred": ("INSUFFICIENT_EVIDENCE+investigative", "as S1", "an indicative-only figure is APPROXIMATE, never exact; v8 adds the investigative flag (REVIEW to decide)"),
    "S3_range_inside_preferred": ("STRONG_FIT+investigative", "as S1", "a bounded range is a range, not its maximum; classification unchanged, investigative flag added (Part 33)"),
    "S4_range_crossing_preferred_discovery": ("POSSIBLE_FIT+investigative", "as S1", "a range crossing the preferred/discovery boundary is Possible; flag added (Part 33)"),
    "S5_range_spanning_outside_discovery": ("INSUFFICIENT_EVIDENCE+investigative", "as S1", "a range spanning inside and outside discovery cannot prove a fit"),
    "S6_minimum_only": ("INSUFFICIENT_EVIDENCE+investigative", "as S1", "an open floor is not an exact count and cannot prove fit within a ceiling"),
    "S7_maximum_only": ("INSUFFICIENT_EVIDENCE+investigative", "as S1", "an open ceiling cannot prove the floor"),
    "S8_malformed_conflicting": ("INSUFFICIENT_EVIDENCE", "as S1", "malformed or conflicting capacity fails closed"),
    "S9a_self_qualifying_exact": ("STRONG_FIT+investigative", "as S1", "the Strategic Land Buyer large-allocation route is preserved"),
    "S9b_self_qualifying_range": ("STRONG_FIT+investigative", "as S1", "preserved only because the plan-stated LOWER bound is itself above the discovery maximum"),
    "S9c_self_qualifying_minimum_only": ("STRONG_FIT+investigative", "as S1", "preserved only because the open floor is itself above the discovery maximum; no count is faked"),
    "S10_nesten_very_large_allocation": ("INSUFFICIENT_EVIDENCE+investigative", "as S1", "far above the discovery range: outside discovery, investigative"),
}
STRATEGIC_PROHIBITED = ["an open floor or ceiling treated as an exact count", "a range reduced to its maximum", "a faked count to preserve the large-allocation route"]


def build_v8_expectation_table() -> dict:
    shadow = {r["case_id"]: r for r in run_shadow()["rows"]}
    rows, disagreements = [], []
    for number, case in enumerate(STRATEGIC_CASES, start=1):
        case_id = case[0]
        row = shadow[case_id]
        proposed, representative, rationale = STRATEGIC_EXPECTATIONS[case_id]
        if row["v8_result"] != proposed:
            disagreements.append(case_id)
        rows.append({"case_no": number, "case_id": case_id, "route": "STRATEGIC_ALLOCATION", "buyer": row["buyer"], "evidence_facts": row["stored_figures"],
                     "capacity_semantics": row["capacity_semantics"], "v7_result": row["frozen_v7_result"], "proposed_v8_result": proposed, "actual_v8_result": row["v8_result"],
                     "differential_category": row["differential_category"], "residual_level": None, "representative_expectation": representative, "rationale": rationale,
                     "prohibited_inferences": STRATEGIC_PROHIBITED, "approved_by_product_owner": False})
    residual = run_residual_benchmark()
    offset = len(rows)
    for number, row in enumerate(residual["rows"], start=offset + 1):
        if row["case_id"] in residual["disagreements"]:
            disagreements.append(row["case_id"])
        fit = row["fit_ceiling"] or "no residual subject: no fit of its own"
        rows.append({"case_no": number, "case_id": row["case_id"], "route": row["route"] or "no residual route (R2 context / R3 nothing)", "buyer": "nesten_homes",
                     "evidence_facts": row["description"], "predicates": row["predicates"], "v7_result": row["v7_result"], "proposed_v8_result": fit,
                     "actual_v8_result": row["actual_level"], "differential_category": None, "residual_level": row["proposed_level"],
                     "proposed_residual_count": row["proposed_residual"], "representative_expectation": row["representative"], "rationale": row["rationale"],
                     "prohibited_inferences": row["prohibited_inferences"], "approved_by_product_owner": False})
    allocation = residual["allocation_case"]
    rows.append({"case_no": len(rows) + 1, "case_id": allocation["case_id"], "route": allocation["route"], "buyer": "nesten_homes",
                 "evidence_facts": "allocation 1,000 + linked permission 600, no comparable-scope / completeness / non-overlap proof", "v7_result": "no residual concept",
                 "proposed_v8_result": "existing strategic fit unchanged; R2 context only", "actual_v8_result": allocation["actual_level"], "differential_category": None,
                 "residual_level": allocation["proposed_level"], "proposed_residual_count": None, "representative_expectation": "the strategic allocation subject (no residual subject exists)",
                 "rationale": "the allocation-minus-planning subtraction is only a trigger", "prohibited_inferences": allocation["prohibited_inferences"], "approved_by_product_owner": False})
    return {"approved_by_product_owner": APPROVED_BY_PRODUCT_OWNER, "rows": rows, "disagreements": disagreements,
            "unexpected_regressions": run_shadow()["unexpected_regressions"]}


def to_markdown(table: dict) -> str:
    lines = ["| # | case | route | v7 | proposed v8 | residual | representative | prohibited |", "|---|---|---|---|---|---|---|---|"]
    for r in table["rows"]:
        residual = r.get("residual_level") or "-"
        count = r.get("proposed_residual_count")
        lines.append(f"| {r['case_no']} | {r['case_id']} | {r['route']} | {r['v7_result']} | {r['proposed_v8_result']} | {residual}{'' if count is None else f' ({count})'} | "
                     f"{r['representative_expectation']} | {'; '.join(r['prohibited_inferences'])} |")
    return "\n".join(lines)
