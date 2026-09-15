"""Agent Evaluation Policy V1 - EVALUATE() orchestration (narrow
implementation slice; Product Owner narrow-implementation authorisation).

evaluate() is the ONE entry point. It never persists anything, never
generates a production baseline, and never touches the UI - see this
module's own docstring sections below for the exact flow and the bounded
retry policy.

MODEL/PROVIDER: reuses the project's existing OpenAI Responses API pattern
verbatim (app.reporting.scheme_summary.generate_scheme_summary is the
established precedent this module copies: `OpenAI()` client construction,
`client.responses.create(model=..., input=..., text={"format": {"type":
"json_schema", ...}})`, `json.loads(response.output_text)`). No new AI
provider, no hard-coded secret - the API key is read from the environment
by the OpenAI SDK itself, exactly as every other caller in this codebase
already relies on."""
from __future__ import annotations

import json
from dataclasses import dataclass

from app.policy.acquisition_type_interpretation import ACQUISITION_TYPE_INTERPRETATION_POLICY_VERSION
from app.policy.agent_evaluation_prompt import GOVERNING_POLICY, build_prompt_context, render_prompt
from app.policy.agent_evaluation_result import (
    AGENT_EVALUATION_POLICY_VERSION,
    FAILED,
    MALFORMED_LLM_OUTPUT,
    SUCCESS,
    UNSUPPORTED_LANGUAGE_DETECTED,
    ACQUISITION_TYPE_NOT_IN_MANDATE,
    NOT_RELEVANT,
    HIGH,
    AcquisitionSubject,
    AgentEvaluationResult,
    AgentEvaluationResultKey,
    EvaluationExecutionResult,
    WHOLE_ALLOCATION,
    DEVELOPMENT_SITE,
)
from app.policy.agent_evaluation_validator import validate_and_build_result
from app.policy.buyer_matching import STRATEGIC_LAND
from app.policy.mandate_interpretation import MANDATE_INTERPRETATION_POLICY_VERSION
from app.policy.terminal_hard_exclusion import (
    TERMINAL_HARD_EXCLUSION_POLICY_VERSION,
    classify_terminal_exclusion,
)
from app.reporting.opportunity_transaction_signals import TRANSACTION_SIGNAL_POLICY_VERSION

# Bounded repair/retry policy (Section 21 of the narrow-implementation
# authorisation, "report the exact retry policy you choose"): ONE retry,
# with the specific validation errors fed back to the model as corrective
# feedback appended to the same input - never a fresh, unguided second
# attempt. If the repaired output is still invalid, evaluate() returns
# FAILED with MALFORMED_LLM_OUTPUT - it never attempts a third call.
MAX_REPAIR_ATTEMPTS = 1

MODEL = "gpt-4o-mini"

# --- Structured-output contract provenance (Acquisition Agent V1, Gate 1 --
# --- controlled release) ----------------------------------------------------
#
# Tracks OUTPUT_SCHEMA specifically - owned beside the artefact it versions,
# the same principle already applied to app.policy.agent_evaluation_prompt.
# GOVERNING_POLICY_PROMPT_VERSION for GOVERNING_POLICY. A pure provenance
# identifier: never read by evaluate(), validate_and_build_result(), or any
# other evaluation/validation logic, so declaring it does not change Agent
# Evaluation Policy V1's commercial semantics in any way, and it is
# deliberately NOT part of app.policy.agent_evaluation_persistence.
# compute_agent_evaluation_input_fingerprint's own payload - a structured-
# output schema change is a CONTROLLED EVALUATION RELEASE (Section 19 of
# that module's own design), never something that should automatically
# invalidate every persisted evaluation merely because a scheduled runner
# executes. Starts at 1 because it tracks the CURRENT, already-production-
# verified OUTPUT_SCHEMA (unchanged by this addition) - bump by 1 whenever
# OUTPUT_SCHEMA's shape changes in a future controlled release, the same
# manual, documented discipline every other *_VERSION constant in this
# codebase already follows.
AGENT_EVALUATION_OUTPUT_SCHEMA_VERSION = 1

OUTPUT_SCHEMA = {
    "name": "agent_evaluation_result",
    "schema": {
        "type": "object",
        "properties": {
            "recommendation": {"type": "string", "enum": ["PURSUE", "VERIFY", "MONITOR", "NOT_RELEVANT"]},
            "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
            "confidence_basis": {"type": "array", "items": {"type": "string"}},
            "acquisition_subject": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "string",
                        "enum": ["WHOLE_ALLOCATION", "DEVELOPMENT_SITE", "PHASE", "PARCEL_TBD", "AFFORDABLE_PACKAGE", "DELIVERY_PIPELINE"],
                    },
                    "reference": {"type": ["string", "null"]},
                    "note": {"type": ["string", "null"]},
                },
                "required": ["level", "reference", "note"],
                "additionalProperties": False,
            },
            "supporting_reasons": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"label": {"type": "string"}, "evidence_reference": {"type": "string"}},
                    "required": ["label", "evidence_reference"],
                    "additionalProperties": False,
                },
            },
            "countervailing_reasons": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"label": {"type": "string"}, "evidence_reference": {"type": "string"}},
                    "required": ["label", "evidence_reference"],
                    "additionalProperties": False,
                },
            },
            "material_unknowns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "fact_or_question": {"type": "string"},
                        "material": {"type": "boolean"},
                        "resolvable": {"type": "boolean"},
                        "blocking": {"type": "boolean"},
                        "why_it_matters": {"type": "string"},
                    },
                    "required": ["fact_or_question", "material", "resolvable", "blocking", "why_it_matters"],
                    "additionalProperties": False,
                },
            },
            "reasoning_summary": {"type": "string"},
            "next_action": {
                "type": "string",
                "enum": [
                    "CONTACT_OWNER_OR_CONTROLLER", "VERIFY_OWNERSHIP", "VERIFY_CONTROL_POSITION",
                    "REVIEW_PLANNING_POSITION", "VERIFY_AFFORDABLE_PACKAGE", "IDENTIFY_PHASE_OR_PARCEL",
                    "CHECK_IMPLEMENTATION_ACTIVITY", "COMMERCIAL_DUE_DILIGENCE", "NO_ACTION",
                ],
            },
            "next_action_detail": {"type": "string"},
            "monitoring_trigger": {
                "type": ["string", "null"],
                "enum": [
                    "DECISION_CHANGED", "PLANNING_STATUS_CHANGED", "ALLOCATION_STATUS_CHANGED",
                    "IMPLEMENTATION_ACTIVITY_CHANGED", "IMPLEMENTATION_DEADLINE_CHANGED",
                    "OWNERSHIP_EVIDENCE_CHANGED", "AFFORDABLE_POSITION_CHANGED", "PHASING_EVIDENCE_CHANGED",
                    "UNIT_COUNT_CHANGED", None,
                ],
            },
            "evidence_references": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "recommendation", "confidence", "confidence_basis", "acquisition_subject", "supporting_reasons",
            "countervailing_reasons", "material_unknowns", "reasoning_summary", "next_action",
            "next_action_detail", "monitoring_trigger", "evidence_references",
        ],
        "additionalProperties": False,
    },
}


def _evaluation_policy_version() -> str:
    return (
        f"mandate_interpretation={MANDATE_INTERPRETATION_POLICY_VERSION};"
        f"acquisition_type_interpretation={ACQUISITION_TYPE_INTERPRETATION_POLICY_VERSION};"
        f"transaction_signal={TRANSACTION_SIGNAL_POLICY_VERSION};"
        f"terminal_hard_exclusion={TERMINAL_HARD_EXCLUSION_POLICY_VERSION};"
        f"agent_evaluation={AGENT_EVALUATION_POLICY_VERSION}"
    )


def _deterministic_terminal_result(
    *, key: AgentEvaluationResultKey, terminal, packet, mandate_fingerprint: str, opportunity_fingerprint: str,
) -> AgentEvaluationResult:
    """Constructs a NOT_RELEVANT result WITHOUT any LLM call, for a
    confirmed terminal hard exclusion (Section 4/21 of the narrow-
    implementation authorisation) - the cheapest, safest possible path,
    and the one case where confidence is always HIGH by construction (a
    genuine, trusted, confirmed hard boundary)."""
    subject_level = WHOLE_ALLOCATION if packet.opportunity_type == STRATEGIC_LAND else DEVELOPMENT_SITE
    return AgentEvaluationResult(
        key=key,
        recommendation=NOT_RELEVANT,
        confidence=HIGH,
        confidence_basis=tuple(terminal.terminal_texts),
        acquisition_subject=AcquisitionSubject(level=subject_level, note="Terminal hard exclusion - acquisition subject is the opportunity as evaluated."),
        material_negative_signals=(),
        reasoning_summary=(
            "A confirmed, deterministic hard exclusion applies: " + " ".join(terminal.terminal_texts)
        ),
        next_action="NO_ACTION",
        next_action_detail="No acquisition effort warranted - a trusted hard exclusion applies.",
        monitoring_trigger=None,
        evidence_references=tuple(terminal.terminal_texts),
        mandate_fingerprint=mandate_fingerprint,
        opportunity_fingerprint=opportunity_fingerprint,
        evaluation_policy_version=_evaluation_policy_version(),
    )


def evaluate(
    session, *, mandate, mandate_key: str, mandate_fingerprint: str,
    acquisition_type: str, opportunity, opportunity_fingerprint: str,
    packet, buyer_fit_assessment, client=None,
) -> EvaluationExecutionResult:
    """The narrow-slice EVALUATE(buyer_mandate, acquisition_type,
    opportunity_packet). `client` is an optional pre-constructed OpenAI
    client (dependency-injected for testing without a live API call) -
    defaults to a fresh `OpenAI()` instance, exactly like every other
    caller in this codebase.

    FLOW (Section 21 of the narrow-implementation authorisation):
      1. validate acquisition_type is in the mandate  -> FAILED if not.
      2. deterministic Terminal Hard Exclusion Policy check -> if terminal,
         return a deterministic NOT_RELEVANT result, NO LLM call.
      3. otherwise build the bounded prompt context and call the LLM once.
      4. deterministic post-validation; on failure, ONE bounded repair
         retry with the specific errors fed back; still-invalid -> FAILED.
    """
    key = AgentEvaluationResultKey(buyer_key=mandate_key, opportunity_id=opportunity.opportunity_id, acquisition_type=acquisition_type)

    if acquisition_type not in mandate.acquisition_types:
        return EvaluationExecutionResult(status=FAILED, failure_reason=ACQUISITION_TYPE_NOT_IN_MANDATE)

    terminal = classify_terminal_exclusion(buyer_fit_assessment.does_not_match)
    if terminal.is_terminal:
        result = _deterministic_terminal_result(
            key=key, terminal=terminal, packet=packet,
            mandate_fingerprint=mandate_fingerprint, opportunity_fingerprint=opportunity_fingerprint,
        )
        return EvaluationExecutionResult(status=SUCCESS, evaluation=result, retry_count=0)

    context = build_prompt_context(
        buyer_key=mandate_key, mandate=mandate, acquisition_type=acquisition_type,
        opportunity_id=opportunity.opportunity_id, opportunity_type=opportunity.opportunity_type,
        buyer_fit_assessment=buyer_fit_assessment, non_terminal_does_not_match=terminal.non_terminal_texts,
        packet=packet, transaction_signals=packet.transaction_signals,
    )
    prompt = render_prompt(context)

    if client is None:
        from openai import OpenAI
        client = OpenAI()

    retry_count = 0
    input_text = prompt
    while True:
        try:
            response = client.responses.create(
                model=MODEL, instructions=GOVERNING_POLICY, input=input_text,
                text={"format": {"type": "json_schema", "name": OUTPUT_SCHEMA["name"], "schema": OUTPUT_SCHEMA["schema"], "strict": True}},
            )
            raw = json.loads(response.output_text)
        except Exception as exc:  # noqa: BLE001 - any SDK/parse failure is a bounded MALFORMED_LLM_OUTPUT failure, never an uncaught crash
            # Deliberately broad: covers json.JSONDecodeError (malformed JSON)
            # as well as any OpenAI SDK exception (timeout, API error,
            # refusal). The exact type/message is preserved on the returned
            # EvaluationExecutionResult so a FAILED result is diagnosable
            # after the fact - a bare `except Exception` that discarded this
            # detail previously made a real batch-run failure undiagnosable.
            diagnostic = f"{type(exc).__name__}: {exc}"
            if retry_count >= MAX_REPAIR_ATTEMPTS:
                return EvaluationExecutionResult(
                    status=FAILED, failure_reason=MALFORMED_LLM_OUTPUT, retry_count=retry_count,
                    diagnostic_detail=diagnostic,
                )
            retry_count += 1
            input_text = prompt + f"\n\nYour previous response could not be parsed ({exc}). Return ONLY valid JSON matching the required schema."
            continue

        outcome = validate_and_build_result(
            raw, context=context, key=key, mandate_fingerprint=mandate_fingerprint,
            opportunity_fingerprint=opportunity_fingerprint, evaluation_policy_version=_evaluation_policy_version(),
        )
        if outcome.ok:
            return EvaluationExecutionResult(status=SUCCESS, evaluation=outcome.result, retry_count=retry_count)

        if retry_count >= MAX_REPAIR_ATTEMPTS:
            failure_reason = (
                UNSUPPORTED_LANGUAGE_DETECTED
                if any("unsupported language" in e for e in outcome.errors)
                else MALFORMED_LLM_OUTPUT
            )
            return EvaluationExecutionResult(
                status=FAILED, failure_reason=failure_reason, retry_count=retry_count,
                diagnostic_detail="; ".join(outcome.errors),
            )

        retry_count += 1
        input_text = (
            prompt
            + "\n\nYour previous response was INVALID for these specific reasons - correct them and return a new, "
              "fully valid response (cite ONLY reference tokens from the table above; every rule in the governing "
              "policy still applies):\n- " + "\n- ".join(outcome.errors)
        )
