"""Stage 2.5B V8-B: PROPOSED residual-opportunity benchmark cases (offline, deterministic; no database, network or model). NEVER imported by app/.

Cases 15-24 of the proposed v8 benchmark (strategic cases 1-14 are benchmark/v8_strategic_scale_shadow.py). Approved by Product Owner REVIEW (``APPROVED_BY_PRODUCT_OWNER``). Expectations are NOT adjusted to match the implementation: a disagreement is a failing test, reported, never silently re-pinned.

Each row: route, evidence facts, v7 result (always "no residual concept" - v7 had no residual subject), proposed v8 level / subject / count / fit ceiling, representative expectation,
rationale and the prohibited inferences the case checks. "Qualified" evidence here is SYNTHETIC test evidence: production supplies none (R1 is dormant by evidence).
"""
from __future__ import annotations

from types import SimpleNamespace

from app.reporting.residual_opportunity import (
    LEVEL_R1, LEVEL_R2, LEVEL_R3, NO_EVIDENCE, ResidualEvidence, allocation_residual_context, production_residual_evidence, qualify_residual,
)
from app.reporting.residential_count import CountAssessment

APPROVED_BY_PRODUCT_OWNER = True   # approved by Product Owner REVIEW with the 24-row table (benchmark/v8_expectation_table.APPROVAL_RECORD)
SITE = 61
PARENT_ID = f"site:{SITE}:whole_site:Whole site"
CONTAINMENT = "RM_DIRECT_PARENT_CITATION: pursuant to outline permission OUT/1"
NON_OVERLAP = "S106 schedule 2 plan: phases 1 and 2 are distinct, non-overlapping parcels"
CHILD_SET = "Outline decision notice condition 5: the permission is delivered in phases 1 and 2 only"


def count(subject_id, value, *, scope_type, basis="consented", metric="total_residential", precision="EXACT", ref="OUT/1", lower=None, upper=None):
    return CountAssessment(scope_type=scope_type, scope_label=subject_id.split(":", 3)[3], subject_id=subject_id, metric=metric, precision=precision, value=value, lower=lower,
                           upper=upper, resolution="resolved", confidence="high", sources=(SimpleNamespace(application_reference=ref),), basis=basis)


def parent(value=500, **kw):
    return count(PARENT_ID, value, scope_type="whole_site", **kw)


def child(label, value, **kw):
    kw.setdefault("ref", f"RM/{label}")
    return count(f"site:{SITE}:phase:{label}", value, scope_type="phase", **kw)


def containment_for(par, kids, text=CONTAINMENT):
    return tuple((k.subject_id, par.subject_id, text) for k in kids)


def pairs_for(kids, text=NON_OVERLAP):
    return tuple((a.subject_id, b.subject_id, text) for i, a in enumerate(kids) for b in kids[i + 1:])


def qualified_evidence(par, kids) -> ResidualEvidence:
    return ResidualEvidence(containment=containment_for(par, kids), non_overlap=pairs_for(kids), child_set=((par.subject_id, tuple(k.subject_id for k in kids), CHILD_SET),))


def _rows():
    p500, c300 = parent(500), child("1", 300)
    c200, c150 = child("1", 200), child("2", 150)
    c300b, c250 = child("1", 300), child("2", 250)
    yield dict(case_id="R15_qualified_500_300", description="outline 500 exact + qualified RM 300 exact; containment, completeness, non-overlap (single child), metric, no conflict all PASS",
               parent=p500, children=[c300], evidence=qualified_evidence(p500, [c300]), level=LEVEL_R1, residual=200, route="RESIDUAL_OPPORTUNITY", fit_ceiling="POSSIBLE_FIT",
               representative="a genuine STRONG phase/plot/permission outranks it; a POSSIBLE residual may represent an otherwise investigative family",
               rationale="the canonical qualified case", prohibits=["availability", "ownership", "parcel geometry", "STRONG_FIT"])
    yield dict(case_id="R16_500_300_no_completeness", description="500 exact + 300 exact, containment evidenced, child-set completeness NOT evidenced",
               parent=p500, children=[c300], evidence=ResidualEvidence(containment=containment_for(p500, [c300])), level=LEVEL_R2, residual=None, route=None, fit_ceiling=None,
               representative="no residual subject: the existing real family subjects determine fit",
               rationale="a plausible residual proposition without safe arithmetic is investigation context only", prohibits=["a 200-home subject", "a trusted 200 count", "its own fit"])
    yield dict(case_id="R17_500_overlap_unknown_300_250", description="500 + children 300 and 250 with non-overlap unknown (sum 550 > parent)",
               parent=p500, children=[c300b, c250], evidence=ResidualEvidence(containment=containment_for(p500, [c300b, c250])), level=LEVEL_R2, residual=None, route=None, fit_ceiling=None,
               representative="no residual subject", rationale="overlap is not excluded, so no arithmetic is attempted; a negative residual is never produced", prohibits=["-50", "any residual count"])
    yield dict(case_id="R17b_500_proven_distinct_300_250", description="500 + children 300 and 250 proven distinct and complete (sum 550 > parent): a conflict",
               parent=p500, children=[c300b, c250], evidence=qualified_evidence(p500, [c300b, c250]), level=LEVEL_R3, residual=None, route=None, fit_ceiling=None,
               representative="no residual subject", rationale="children exceed the parent: a material conflict, never a negative residual", prohibits=["-50", "any residual count"])
    yield dict(case_id="R18_500_proven_complete_200_150", description="500 + proven complete, proven distinct children 200 and 150",
               parent=p500, children=[c200, c150], evidence=qualified_evidence(p500, [c200, c150]), level=LEVEL_R1, residual=150, route="RESIDUAL_OPPORTUNITY", fit_ceiling="POSSIBLE_FIT",
               representative="as R15", rationale="multi-child arithmetic requires explicit non-overlap AND completeness", prohibits=["availability", "STRONG_FIT"])
    yield dict(case_id="R19_amendment_no_double_subtraction", description="parent 500 + an amendment restating 500 for the same whole-site scope",
               parent=p500, children=[parent(500, ref="OUT/1A")], evidence=NO_EVIDENCE, level=LEVEL_R3, residual=None, route=None, fit_ceiling=None, representative="no residual subject",
               rationale="a whole-site scope cannot be a contained child; nothing is subtracted twice", prohibits=["0", "500 consumed twice"])
    yield dict(case_id="R19b_duplicate_child_counted_once", description="500 + the same child supplied twice (equal) with qualified evidence",
               parent=p500, children=[c300, c300], evidence=qualified_evidence(p500, [c300]), level=LEVEL_R1, residual=200, route="RESIDUAL_OPPORTUNITY", fit_ceiling="POSSIBLE_FIT",
               representative="as R15", rationale="one child subject is one subject", prohibits=["-100"])
    yield dict(case_id="R20_incompatible_metrics", description="parent 500 total residential + child 300 of a different metric",
               parent=p500, children=[child("1", 300, metric="affordable_units")], evidence=NO_EVIDENCE, level=LEVEL_R3, residual=None, route=None, fit_ceiling=None, representative="no residual subject",
               rationale="metrics are never converted", prohibits=["any residual count"])
    yield dict(case_id="R21_approximate_child", description="parent 500 exact + child ~300 approximate, containment evidenced",
               parent=p500, children=[child("1", 300, precision="APPROXIMATE")], evidence=ResidualEvidence(containment=containment_for(p500, [child("1", 300)])), level=LEVEL_R2, residual=None,
               route=None, fit_ceiling=None, representative="no residual subject", rationale="an exact residual is never invented from an estimate", prohibits=["200", "~200"])
    yield dict(case_id="R22_zero_residual", description="parent 500 + qualified child 500",
               parent=p500, children=[child("1", 500)], evidence=qualified_evidence(p500, [child("1", 500)]), level=LEVEL_R3, residual=None, route=None, fit_ceiling=None,
               representative="no residual subject", rationale="fully accounted for: a zero residual is not an opportunity", prohibits=["a 0-home subject"])
    yield dict(case_id="R23_production_default_evidence", description="500 + 300 with PRODUCTION evidence only (G2 containment; no completeness or non-overlap producer exists)",
               parent=p500, children=[c300], evidence=production_residual_evidence(containment_for(p500, [c300])), level=LEVEL_R2, residual=None, route=None, fit_ceiling=None,
               representative="no residual subject", rationale="R1 is dormant in production by evidence", prohibits=["R1", "a 200 count"])


CASES = tuple(_rows())


def evaluate_case(case) -> dict:
    q = qualify_residual(case["parent"], case["children"], case["evidence"])
    return {"case_id": case["case_id"], "description": case["description"], "v7_result": "no residual concept", "proposed_level": case["level"], "actual_level": q.level,
            "proposed_residual": case["residual"], "actual_residual": q.residual_value, "route": case["route"], "fit_ceiling": case["fit_ceiling"], "has_subject": q.is_subject,
            "representative": case["representative"], "rationale": case["rationale"], "prohibited_inferences": case["prohibits"], "reason": q.reason,
            "predicates": {p.name: p.state for p in q.predicates}}


def allocation_case() -> dict:
    """R24: allocation 1,000 with linked permission 600 and no comparable-scope proof: R2 context on the strategic allocation; NO trusted 400."""
    coverage = SimpleNamespace(capacity_accounting_status="ok", indicative_residual_capacity=400, number_of_sites_with_planning_activity=1,
                               development_coverage_classification="PARTIAL_COVERAGE")
    context = allocation_residual_context(coverage)
    return {"case_id": "R24_allocation_1000_permission_600", "route": "STRATEGIC_ALLOCATION", "proposed_level": LEVEL_R2, "actual_level": context.level if context else LEVEL_R3,
            "text": context.text if context else None, "trusted_count": None, "prohibited_inferences": ["Residual opportunity: 400 homes", "400 homes available", "400-home Possible Fit"]}


def run_residual_benchmark() -> dict:
    rows = [evaluate_case(c) for c in CASES]
    return {"approved_by_product_owner": APPROVED_BY_PRODUCT_OWNER, "rows": rows, "allocation_case": allocation_case(),
            "disagreements": [r["case_id"] for r in rows if r["proposed_level"] != r["actual_level"] or r["proposed_residual"] != r["actual_residual"]]}
