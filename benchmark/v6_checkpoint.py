"""Stage 2.5B V7A pre-implementation checkpoint: what does CURRENT (v6) buyer matching say about the 14 frozen benchmark cases?

READ-ONLY and deterministic: no database, no network, no model call, no production read, and the frozen fixtures are never modified. The frozen cases are
v4 snapshots; their raw MatchingFacts were not captured, so each case's facts are RECONSTRUCTED from the captured Layer A / provenance values (unit count,
planning state, development state, affordable figures, allocation status, planning activity). Fields the snapshot did not capture (development type, council,
control facts) are left unknown, exactly as the frozen reasons say. The reconstruction is validated per case: the NON-scale reasons produced by v6 must equal the
frozen non-scale reasons; where they do not, the case is flagged ``fidelity != "exact"`` and its v6 result must be read as indicative only.

This establishes the immediate pre-v7 result. It does NOT approve or reject any historical expectation, and a v4 -> v6 change recorded here is caused by v5/v6
(scale-aware uncertain discovery; the 10% discovery envelope), never by the v7 phasing delta.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.policy.buyer_matching import (
    AFFORDABLE_UNITS, B2MatchingContext, ControlAppetiteFacts, DEVELOPMENT_STATE_UNKNOWN, MatchingFacts, assess_buyer_fit, discovery_bounds,
)
from app.policy.buyer_profiles import (
    ADOPTED_ALLOCATION, BUYER_PROFILES, EMERGING_ALLOCATION, OTHER_OR_UNKNOWN, PERMISSION_GRANTED, PLANNING_ACTIVE_PROPOSAL,
)

CASES_DIR = Path(__file__).parent / "cases"
_PLANNING_STATES = {
    "permission_granted": PERMISSION_GRANTED, "planning_active_proposal": PLANNING_ACTIVE_PROPOSAL,
    "adopted_allocation": ADOPTED_ALLOCATION, "draft_allocation": EMERGING_ALLOCATION, "proposed_submission_allocation": EMERGING_ALLOCATION,
}
_SCALE_WORDS = ("homes", "target range", "discovery range", "scale", "range (")


def _value(pair):
    return pair[1] if isinstance(pair, (list, tuple)) and len(pair) == 2 and pair[0] == "KNOWN" else None


def _reconstruct(case: dict):
    facts_layer = case["frozen_commercial_facts"]
    of = facts_layer["opportunity_facts"]
    strategic = facts_layer["opportunity_type"] == "strategic_land"
    state_key = of.get("allocation_status", [None, None])[1] if strategic else of.get("operative_planning_state", [None, None])[1]
    planning_state = _PLANNING_STATES.get(state_key, OTHER_OR_UNKNOWN)
    pct = _value(of.get("affordable_percentage"))
    matched_to_site = not any("Ownership/control has not been established for this allocation" in t for t in facts_layer["buyer_fit_investigate"])
    # The snapshot has no raw development type: infer only what the FROZEN reasons establish. If the frozen reasons do not say the development type
    # is unestablished, it was known and not specialist at capture time.
    dev_type_known = (not strategic) and not any("Development type has not been established" in t for t in facts_layer["buyer_fit_unknown"])
    facts = MatchingFacts(
        opportunity_type=facts_layer["opportunity_type"], unit_count=_value(of.get("total_units")),
        development_type_raw="general needs" if dev_type_known else None,
        is_specialist_development=False if dev_type_known else None, affordable_percentage=pct, affordable_percentage_trusted=pct is not None,
        affordable_unit_count=_value(of.get("affordable_units")), planning_state=planning_state,
        has_identified_planning_activity=(_value(of.get("has_identified_planning_activity")) if strategic else True),
        has_phasing_evidence=False, matched_to_site=matched_to_site if strategic else True)
    development_state = _value(of.get("development_state")) or DEVELOPMENT_STATE_UNKNOWN
    # Control facts: only what the frozen reasons positively state.
    frozen_text = " ".join((*facts_layer["buyer_fit_matches"], *facts_layer["buyer_fit_investigate"], *facts_layer["buyer_fit_unknown"]))
    control = ControlAppetiteFacts(
        developer_or_applicant_led=True if "developer/applicant-led situation" in frozen_text else None, third_party_interest_declared=None,
        ownership_unresolved=True if "Ownership/control evidence for this opportunity remains unresolved" in frozen_text else None,
        partial_control_evidence=None)
    context = B2MatchingContext(council_code=None, development_state=development_state, control_facts=control,
                                development_state_scope_verified=bool(of.get("development_state_scope_verified")))
    return facts, context


def _scale_outcome(profile, scale_value, strategic):
    if scale_value is None:
        return "scale_unknown"
    lo, hi = profile.target_unit_min, profile.target_unit_max
    dmin, dmax = discovery_bounds(lo, hi)
    if profile.below_minimum_scale_is_exclusion:
        dmin = lo
    if lo <= scale_value <= hi:
        return "within_preferred"
    if scale_value < lo and profile.below_minimum_scale_is_exclusion:
        return "below_hard_minimum"
    if dmin <= scale_value <= dmax:
        return "within_discovery_only"
    if scale_value > hi and profile.large_allocation_is_self_qualifying and strategic:
        return "above_max_strategic_self_qualifying_route"
    return "above_discovery_max" if scale_value > dmax else "below_discovery_min"


def _is_scale_reason(text: str) -> bool:
    lowered = text.lower()
    return any(w in lowered for w in _SCALE_WORDS)


def checkpoint_case(case: dict) -> dict:
    layer_a, layer_b, provenance = case["frozen_commercial_facts"], case["frozen_evaluation_input"], case["provenance"]
    profile = BUYER_PROFILES[layer_b["buyer_key"]]
    facts, context = _reconstruct(case)
    result = assess_buyer_fit(profile, facts, context=context)
    v6_classification, v6_investigative, basis = result.classification, result.is_investigative_exception, "reconstructed_assess_buyer_fit"
    terminal_not_captured = layer_a["buyer_fit_classification"] == "NOT_SUITABLE" and result.classification != "NOT_SUITABLE"
    if terminal_not_captured:
        # Layer A/B do not record which does_not_match text was terminal (see the case's own reviewer_notes). A terminal hard exclusion is scale-independent
        # and untouched by v5/v6, so the current result is carried from the frozen exclusion - an inference, flagged as such.
        v6_classification, v6_investigative, basis = "NOT_SUITABLE", False, "inferred_from_frozen_terminal_exclusion"
    strategic = facts.opportunity_type == "strategic_land"
    metric_value = facts.affordable_unit_count if profile.scale_metric == AFFORDABLE_UNITS else facts.unit_count
    outcome = _scale_outcome(profile, metric_value, strategic)

    def non_scale(buckets):
        return sorted(t for bucket in buckets for t in bucket if not _is_scale_reason(t))
    frozen_non_scale = non_scale((layer_a["buyer_fit_matches"], layer_a["buyer_fit_unknown"], layer_a["buyer_fit_investigate"]))
    v6_non_scale = non_scale((result.matches, result.unknown, result.investigate))
    phasing_relevant = (not strategic) and profile.scale_metric != AFFORDABLE_UNITS and outcome == "above_discovery_max"
    below_min_relevant = (not strategic) and profile.scale_metric != AFFORDABLE_UNITS and outcome == "below_discovery_min"
    return {
        "case_id": case["case_id"], "buyer": layer_b["buyer_key"], "opportunity": provenance["captured_from_opportunity_id"],
        "frozen_policy_version": provenance.get("buyer_matching_policy_version"),
        "frozen_classification": layer_a["buyer_fit_classification"], "frozen_investigative": layer_a["buyer_fit_is_investigative_exception"],
        "v6_classification": v6_classification, "v6_investigative": v6_investigative, "v6_basis": basis,
        "scale_value": metric_value, "scale_outcome_v6": outcome,
        "principal_v6_scale_reasons": [t for t in (*result.matches, *result.unknown, *result.investigate) if _is_scale_reason(t)][:2],
        # frozen_only empty = v6 reproduces every frozen non-scale reason (the reconstruction lost nothing); v6_only reasons are genuine v4 -> v6 additions.
        "reconstruction": "complete" if not (set(frozen_non_scale) - set(v6_non_scale)) and not terminal_not_captured else "incomplete",
        "non_scale_reasons_only_in_frozen_v4": sorted(set(frozen_non_scale) - set(v6_non_scale)),
        "non_scale_reasons_only_in_v6": sorted(set(v6_non_scale) - set(frozen_non_scale)),
        "v7_phasing_delta_relevant": phasing_relevant, "v7_below_minimum_wording_relevant": below_min_relevant,
        "changed_v4_to_v6": (layer_a["buyer_fit_classification"], layer_a["buyer_fit_is_investigative_exception"]) != (v6_classification, v6_investigative),
    }


def build_checkpoint() -> list[dict]:
    rows = []
    for path in sorted(CASES_DIR.glob("*.json")):
        rows.append(checkpoint_case(json.loads(path.read_text(encoding="utf-8"))))
    return rows


if __name__ == "__main__":  # pragma: no cover
    print(json.dumps(build_checkpoint(), indent=2, sort_keys=True))
