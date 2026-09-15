"""Agent Evaluation Benchmark V1 - READ-ONLY fixture extraction tool
(Implementation Gate, Section 17).

extract_candidate_case() builds a CANDIDATE BenchmarkCase for one explicitly
supplied (opportunity_id, buyer_key, acquisition_type) triple, using the
exact same read-only assembly app.policy.acquisition_evaluate.evaluate()
itself would use - up to, but never including, the OpenAI call.

MUST NOT (Section 17, verbatim requirements):
  - call OpenAI - this module never imports `openai` and never constructs a
    client;
  - alter production data - every function here only ever reads;
  - iterate the candidate universe as a discovery mechanism - the caller
    always supplies one explicit opportunity_id; build_current_opportunity_
    universe() is used only as a READ-ONLY LOOKUP for that one already-known
    ID (see _locate_opportunity_record's own docstring for why, and its
    honestly-disclosed cost), never to auto-discover cases;
  - automatically approve a case - extract_candidate_case() always returns
    approved_by_product_owner=False; only a human, editing the saved JSON
    fixture directly, ever sets that field True;
  - silently overwrite an existing approved fixture - see benchmark.
    benchmark_case.save_case's own overwrite guard, used by this module's
    own CLI wrapper (scripts/extract_benchmark_case.py).

Extraction is PREPARATION, not approval (Section 17's own closing line).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from app.db.models import Buyer, BuyerMandate
from app.policy.acquisition_type_interpretation import ACQUISITION_TYPE_INTERPRETATION_POLICY_VERSION
from app.policy.agent_evaluation_persistence import resolve_acquisition_subject_key
from app.policy.agent_evaluation_prompt import build_prompt_context, compute_ownership_control_posture, GOVERNING_POLICY_PROMPT_VERSION
from app.policy.agent_evaluation_result import AGENT_EVALUATION_POLICY_VERSION
from app.policy.buyer_matching import BUYER_MATCHING_POLICY_VERSION, STRATEGIC_LAND
from app.policy.buyer_matching_b2_context import build_b2_context, evaluate_buyer_fit
from app.policy.mandate_interpretation import MANDATE_INTERPRETATION_POLICY_VERSION
from app.policy.terminal_hard_exclusion import TERMINAL_HARD_EXCLUSION_POLICY_VERSION, classify_terminal_exclusion
from app.reporting.opportunity_intelligence_packet import build_opportunity_intelligence_packet
from app.reporting.opportunity_transaction_signals import TRANSACTION_SIGNAL_POLICY_VERSION
from app.reporting.opportunity_universe import build_current_opportunity_universe

from benchmark.benchmark_case import BenchmarkCase, CaseProvenance, FrozenCommercialFacts, FrozenRenderedInput

try:
    from app.policy.acquisition_evaluate import AGENT_EVALUATION_OUTPUT_SCHEMA_VERSION
except ImportError:  # pragma: no cover - defensive only, module always exports this
    AGENT_EVALUATION_OUTPUT_SCHEMA_VERSION = 1


def _locate_opportunity_record(session, opportunity_id: str):
    """Read-only lookup of ONE already-known opportunity_id.

    HONEST DESIGN NOTE (not hidden): no per-ID direct resolver function
    exists elsewhere in this codebase today (confirmed by inspection of
    app.reporting.opportunity_universe) - matching_facts for a single
    opportunity are only ever produced as a side effect of building the
    complete universe. This function therefore calls
    build_current_opportunity_universe(session) ONCE and filters to the one
    requested ID - the same pattern the Gate 1 production smoke test already
    used and documented as safe/read-only. This is NOT the "iterate the
    candidate universe" cost-safety violation Section 23 forbids (that rule
    targets the RUNNER auto-discovering many cases to EXECUTE against a paid
    API) - this is a one-shot, read-only, zero-cost lookup, invoked once per
    extraction of one named case, exactly as this tool's own contract
    requires. A future optimisation could add a direct single-ID resolver;
    not needed for V1."""
    universe = build_current_opportunity_universe(session)
    for record in universe:
        if record.opportunity_id == opportunity_id:
            return record
    raise ValueError(f"opportunity_id {opportunity_id!r} is not present in the CURRENT candidate universe")


def _resolve_mandate(session, buyer_key: str) -> BuyerMandate:
    mandate = session.execute(
        select(BuyerMandate).join(Buyer).where(Buyer.buyer_key == buyer_key)
    ).scalar_one_or_none()
    if mandate is None:
        raise ValueError(f"no BuyerMandate found for buyer_key={buyer_key!r}")
    return mandate


def _fact_pair(fv) -> tuple[str, object | None]:
    return (fv.state, fv.value if fv.state == "KNOWN" else None)


def extract_candidate_case(
    session, *, opportunity_id: str, buyer_key: str, acquisition_type: str,
    case_id: str, case_name: str, commercial_scenario: str, benchmark_version_introduced: int,
    proposed_expected_recommendation: tuple[str, ...], proposed_commercial_rationale: str,
    required_invariants: tuple[str, ...] = (), forbidden_claims: tuple[str, ...] = (),
    required_material_unknowns: tuple[str, ...] = (),
    expected_acquisition_subject_level: tuple[str, ...] | None = None,
    expected_next_action: tuple[str, ...] | None = None,
    monitoring_trigger_constraints: tuple[str, ...] | None = None,
    repeat_for_consistency: bool = False, reviewer_notes: str = "",
) -> BenchmarkCase:
    """Builds ONE candidate BenchmarkCase, read-only, zero OpenAI calls.

    The `proposed_*` parameters are the EXTRACTOR's (this session's) own
    proposed labels - they are NEVER treated as approved; the returned
    case always has approved_by_product_owner=False (Section 9: "Before any
    real model output is seen: the Product Owner must approve..."). A human
    reviewing the saved JSON either edits these fields or accepts them, then
    flips approved_by_product_owner to true by hand."""
    record = _locate_opportunity_record(session, opportunity_id)
    mandate = _resolve_mandate(session, buyer_key)

    context = build_b2_context(session, record.opportunity_id, record.opportunity_type)
    packet = build_opportunity_intelligence_packet(session, record, context=context)
    assessment = evaluate_buyer_fit(session, mandate, record.matching_facts, context=context)
    terminal = classify_terminal_exclusion(assessment.does_not_match)

    is_zero_llm = terminal.is_terminal

    prompt_context = build_prompt_context(
        buyer_key=buyer_key, mandate=mandate, acquisition_type=acquisition_type,
        opportunity_id=record.opportunity_id, opportunity_type=record.opportunity_type,
        buyer_fit_assessment=assessment, non_terminal_does_not_match=terminal.non_terminal_texts,
        packet=packet, transaction_signals=packet.transaction_signals,
    )

    layer_b = FrozenRenderedInput(
        buyer_key=buyer_key, acquisition_type=acquisition_type, opportunity_type=record.opportunity_type,
        mandate_interpretation_lines=prompt_context.mandate_interpretation_lines,
        buyer_fit_classification=prompt_context.buyer_fit_classification,
        buyer_fit_is_investigative_exception=prompt_context.buyer_fit_is_investigative_exception,
        reference_tokens=dict(prompt_context.reference_tokens),
        governing_policy_prompt_version=GOVERNING_POLICY_PROMPT_VERSION,
        agent_evaluation_output_schema_version=AGENT_EVALUATION_OUTPUT_SCHEMA_VERSION,
    )

    opportunity_facts: dict = {
        "total_units": _fact_pair(packet.total_units),
        "development_state_scope_verified": packet.development_state_scope_verified,
        "actors_control_developer_indications": sorted(packet.actors_control.developer_indications),
        "actors_control_ownership_coverage": packet.actors_control.ownership_coverage,
        "actors_control_conflicts": sorted(packet.actors_control.conflicts),
    }
    if packet.opportunity_type != STRATEGIC_LAND:
        opportunity_facts["development_state"] = _fact_pair(packet.development_state)
        opportunity_facts["affordable_units"] = _fact_pair(packet.affordable_units)
        opportunity_facts["affordable_percentage"] = _fact_pair(packet.affordable_percentage)
        opportunity_facts["operative_planning_state"] = _fact_pair(packet.operative_planning_state)
        opportunity_facts["recommendation_direction"] = _fact_pair(packet.recommendation_direction)
        opportunity_facts["affordable_housing_status"] = _fact_pair(packet.affordable_housing_status)
    else:
        opportunity_facts["local_plan_status"] = _fact_pair(packet.local_plan_status)
        opportunity_facts["allocation_status"] = _fact_pair(packet.allocation_status)
        opportunity_facts["progression_signal"] = _fact_pair(packet.progression_signal)
        opportunity_facts["has_identified_planning_activity"] = _fact_pair(packet.has_identified_planning_activity)

    s = packet.transaction_signals
    transaction_signal_states = {
        "recent_permission": s.recent_permission.state,
        "approaching_implementation_deadline": s.approaching_implementation_deadline.state,
        "implementation_activity_evidence_identified": s.implementation_activity_evidence_identified.state,
        "wider_site_implementation_activity_context": s.wider_site_implementation_activity_context.state,
        "no_qualifying_progress_evidence_identified": s.no_qualifying_progress_evidence_identified.state,
        "ownership_or_control_evidence_changed": s.ownership_or_control_evidence_changed.state,
        "scope_verified": s.scope_verified,
    }

    layer_a = FrozenCommercialFacts(
        acquisition_type=acquisition_type, opportunity_type=record.opportunity_type,
        buyer_fit_classification=assessment.classification,
        buyer_fit_is_investigative_exception=assessment.is_investigative_exception,
        buyer_fit_matches=tuple(assessment.matches), buyer_fit_unknown=tuple(assessment.unknown),
        buyer_fit_investigate=tuple(assessment.investigate),
        buyer_fit_non_terminal_does_not_match=tuple(terminal.non_terminal_texts),
        ownership_control_posture=compute_ownership_control_posture(packet),
        opportunity_facts=opportunity_facts, transaction_signal_states=transaction_signal_states,
        linked_strategic_allocation_id=packet.linked_strategic_allocation_id,
    )

    subject_type, anchor_id, scope_key = resolve_acquisition_subject_key(record.opportunity_id, record.opportunity_type)

    provenance = CaseProvenance(
        captured_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        captured_from_opportunity_id=record.opportunity_id,
        buyer_key=buyer_key, mandate_key=getattr(mandate, "mandate_key", "default"),
        acquisition_subject_scope_key=scope_key,
        buyer_matching_policy_version=BUYER_MATCHING_POLICY_VERSION,
        mandate_interpretation_policy_version=MANDATE_INTERPRETATION_POLICY_VERSION,
        acquisition_type_interpretation_policy_version=ACQUISITION_TYPE_INTERPRETATION_POLICY_VERSION,
        transaction_signal_policy_version=TRANSACTION_SIGNAL_POLICY_VERSION,
        terminal_hard_exclusion_policy_version=TERMINAL_HARD_EXCLUSION_POLICY_VERSION,
        agent_evaluation_policy_version=AGENT_EVALUATION_POLICY_VERSION,
    )

    return BenchmarkCase(
        case_id=case_id, case_name=case_name, commercial_scenario=commercial_scenario,
        benchmark_version_introduced=benchmark_version_introduced,
        provenance=provenance, frozen_commercial_facts=layer_a, frozen_evaluation_input=layer_b,
        expected_recommendation=proposed_expected_recommendation, commercial_rationale=proposed_commercial_rationale,
        required_invariants=required_invariants, forbidden_claims=forbidden_claims,
        required_material_unknowns=required_material_unknowns,
        expected_acquisition_subject_level=expected_acquisition_subject_level,
        expected_next_action=expected_next_action, monitoring_trigger_constraints=monitoring_trigger_constraints,
        repeat_for_consistency=(repeat_for_consistency and not is_zero_llm),
        is_zero_llm_case=is_zero_llm, reviewer_notes=reviewer_notes,
        approved_by_product_owner=False,
    )


def render_case_prompt_preview(case: BenchmarkCase) -> str:
    """Convenience for human review: reconstructs the exact prompt text
    Layer B would render, without needing a live PromptContext object -
    useful when a reviewer wants to read exactly what the model would see
    for a candidate case. Never used by the runner itself."""
    lines = [f"ACQUISITION TYPE: {case.frozen_evaluation_input.acquisition_type}", ""]
    lines.append("BUYER MANDATE INTERPRETATION:")
    lines.extend(case.frozen_evaluation_input.mandate_interpretation_lines)
    lines.append("")
    lines.append("EVIDENCE (reference tokens):")
    for token, value in case.frozen_evaluation_input.reference_tokens.items():
        lines.append(f"  {token}: {value}")
    return "\n".join(lines)
