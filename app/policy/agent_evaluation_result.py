"""Agent Evaluation Policy V1 - AgentEvaluationResult domain contract
(narrow implementation slice; Product Owner-approved narrow authorisation
following the Agent Evaluation Policy V1 design & production calibration
report).

This module defines the SHAPE app.policy.acquisition_evaluate.evaluate()
returns. It is still a pure domain contract - no LLM call, no database
persistence live HERE - but it is no longer aspirational: this narrow
slice's own EVALUATE() (app.policy.acquisition_evaluate) constructs real
instances of AgentEvaluationResult from real LLM output, subject to the
deterministic validator (app.policy.agent_evaluation_validator).

EVALUATION_FAILED IS NOT A RECOMMENDATION (Product Owner correction): a
technical/structural failure is represented by EvaluationExecutionResult's
own FAILED status, never by adding a fifth value to RECOMMENDATION_VALUES.
An AgentEvaluationResult, once constructed, is always a genuine commercial
recommendation - see EvaluationExecutionResult below for the wrapper that
keeps execution status and commercial recommendation structurally separate.

ONE RESULT PER (BUYER MANDATE, OPPORTUNITY, ACQUISITION TYPE) - not one
blended result per (mandate, opportunity). A mandate stating more than one
acquisition_types entry (Buyer Mandate V2 already permits this) may
genuinely warrant a DIFFERENT recommendation under each acquisition-type
reading of the same opportunity (e.g. LAND_SITE_ACQUISITION says VERIFY,
DEVELOPMENT_HOMES_ACQUISITION says PURSUE, for the identical buyer and
opportunity) - blending would silently hide exactly that divergence. See
AgentEvaluationResultKey below for the composite identity this implies.

NO CHAIN-OF-THOUGHT. reasoning_summary is a short, structured explanation
(the eventual WHY/WHAT WE DON'T KNOW/NEXT ACTION contract), never a raw
LLM transcript.
"""
from __future__ import annotations

from dataclasses import dataclass, field

PURSUE = "PURSUE"
VERIFY = "VERIFY"
MONITOR = "MONITOR"
NOT_RELEVANT = "NOT_RELEVANT"

RECOMMENDATION_VALUES = frozenset({PURSUE, VERIFY, MONITOR, NOT_RELEVANT})

HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"

CONFIDENCE_VALUES = frozenset({HIGH, MEDIUM, LOW})

AGENT_EVALUATION_POLICY_VERSION = 1

# --- Acquisition subject (Product Owner narrow-implementation approval) ----
# A typed, validated structure - never arbitrary free text, and PARCEL_TBD
# never asserts that a smaller parcel/phase has actually been established;
# it means only "a smaller acquisition subject may be commercially relevant
# but has not yet been identified" (e.g. Nesten Homes against a 990-unit
# site - the subject is a not-yet-identified parcel, not a fabricated one).
WHOLE_ALLOCATION = "WHOLE_ALLOCATION"
DEVELOPMENT_SITE = "DEVELOPMENT_SITE"
PHASE = "PHASE"
PARCEL_TBD = "PARCEL_TBD"
AFFORDABLE_PACKAGE = "AFFORDABLE_PACKAGE"
DELIVERY_PIPELINE = "DELIVERY_PIPELINE"

ACQUISITION_SUBJECT_LEVELS = frozenset({
    WHOLE_ALLOCATION, DEVELOPMENT_SITE, PHASE, PARCEL_TBD, AFFORDABLE_PACKAGE, DELIVERY_PIPELINE,
})


@dataclass(frozen=True)
class AcquisitionSubject:
    """WHAT the buyer is potentially acquiring - never conflates a strategic
    allocation, a development site, a phase, and an individual parcel
    (architecture report, Section D). `reference` names the specific
    sub-scope where one exists (e.g. a phase_code, or a linked allocation
    id) - None when the subject IS the opportunity itself (WHOLE_ALLOCATION/
    DEVELOPMENT_SITE) or not yet identified (PARCEL_TBD). `note` is a short,
    evidence-grounded qualifier, never a fabricated claim that a specific
    parcel has been found."""

    level: str
    reference: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        if self.level not in ACQUISITION_SUBJECT_LEVELS:
            raise ValueError(f"acquisition subject level {self.level!r} is not one of {sorted(ACQUISITION_SUBJECT_LEVELS)}")


# --- Next Action V1 (bounded vocabulary - Product Owner narrow-implementation approval) ---
CONTACT_OWNER_OR_CONTROLLER = "CONTACT_OWNER_OR_CONTROLLER"
VERIFY_OWNERSHIP = "VERIFY_OWNERSHIP"
VERIFY_CONTROL_POSITION = "VERIFY_CONTROL_POSITION"
REVIEW_PLANNING_POSITION = "REVIEW_PLANNING_POSITION"
VERIFY_AFFORDABLE_PACKAGE = "VERIFY_AFFORDABLE_PACKAGE"
IDENTIFY_PHASE_OR_PARCEL = "IDENTIFY_PHASE_OR_PARCEL"
CHECK_IMPLEMENTATION_ACTIVITY = "CHECK_IMPLEMENTATION_ACTIVITY"
COMMERCIAL_DUE_DILIGENCE = "COMMERCIAL_DUE_DILIGENCE"
NO_ACTION = "NO_ACTION"

NEXT_ACTION_VALUES = frozenset({
    CONTACT_OWNER_OR_CONTROLLER, VERIFY_OWNERSHIP, VERIFY_CONTROL_POSITION, REVIEW_PLANNING_POSITION,
    VERIFY_AFFORDABLE_PACKAGE, IDENTIFY_PHASE_OR_PARCEL, CHECK_IMPLEMENTATION_ACTIVITY,
    COMMERCIAL_DUE_DILIGENCE, NO_ACTION,
})

# --- Monitoring Trigger V1 (bounded vocabulary, aliasing app.reporting. ---
# --- opportunity_change's own real reason codes - see that module for the
# --- authoritative mapping this module deliberately does not duplicate
# --- logic for; app.policy.agent_evaluation_validator owns the alias map.)
DECISION_CHANGED = "DECISION_CHANGED"
PLANNING_STATUS_CHANGED = "PLANNING_STATUS_CHANGED"
ALLOCATION_STATUS_CHANGED = "ALLOCATION_STATUS_CHANGED"
IMPLEMENTATION_ACTIVITY_CHANGED = "IMPLEMENTATION_ACTIVITY_CHANGED"
IMPLEMENTATION_DEADLINE_CHANGED = "IMPLEMENTATION_DEADLINE_CHANGED"
OWNERSHIP_EVIDENCE_CHANGED = "OWNERSHIP_EVIDENCE_CHANGED"
AFFORDABLE_POSITION_CHANGED = "AFFORDABLE_POSITION_CHANGED"
PHASING_EVIDENCE_CHANGED = "PHASING_EVIDENCE_CHANGED"
UNIT_COUNT_CHANGED = "UNIT_COUNT_CHANGED"

MONITORING_TRIGGER_VALUES = frozenset({
    DECISION_CHANGED, PLANNING_STATUS_CHANGED, ALLOCATION_STATUS_CHANGED, IMPLEMENTATION_ACTIVITY_CHANGED,
    IMPLEMENTATION_DEADLINE_CHANGED, OWNERSHIP_EVIDENCE_CHANGED, AFFORDABLE_POSITION_CHANGED,
    PHASING_EVIDENCE_CHANGED, UNIT_COUNT_CHANGED,
})


@dataclass(frozen=True)
class AgentEvaluationResultKey:
    """The composite identity one AgentEvaluationResult is scoped to -
    (buyer, opportunity, acquisition_type), never merely (buyer,
    opportunity). Two results sharing the same buyer_key/opportunity_id but
    different acquisition_type are two independent, equally valid results,
    never a collision."""

    buyer_key: str
    opportunity_id: str
    acquisition_type: str


@dataclass(frozen=True)
class MaterialSignal:
    """One positive or negative signal cited in a recommendation - always
    traceable to a specific source, never free-floating prose. `source_reference`
    names the packet field or app.reporting.opportunity_transaction_signals
    signal this was read from (e.g. "operative_planning_state",
    "recent_permission")."""

    label: str
    source_reference: str


@dataclass(frozen=True)
class MaterialUnknown:
    """One fact the evaluation identified as unresolved.

    `material` marks whether this unknown is actually relevant to THIS
    buyer's acquisition type at all (an immaterial unknown should not be
    listed here in the first place, but the field keeps this an explicit,
    checkable judgement rather than an implicit one).
    `resolvable` marks whether a plausible bounded capability could
    establish it.
    `blocking` marks whether this unknown, if resolved unfavourably, could
    plausibly change the recommendation - VERIFY requires at least one
    unknown with BOTH blocking=True and resolvable=True (app.policy.
    agent_evaluation_validator enforces this); PURSUE may legitimately
    carry a non-blocking (blocking=False) unknown alongside it - a
    unresolved-but-non-blocking fact is a parallel investigation, not a
    gate (architecture report, Section G/Investigation Policy)."""

    fact_or_question: str
    blocking: bool
    resolvable: bool
    material: bool = True
    why_it_matters: str = ""


@dataclass(frozen=True)
class AgentEvaluationResult:
    """The complete result of evaluating one (buyer mandate, opportunity,
    acquisition_type) combination. Every field here is either produced by
    an evaluation or (for the fingerprint fields) copied verbatim from
    already-existing trusted state - nothing here computes a NEW
    fingerprint of its own.

    NOT PERSISTED by anything in this task - see this module's own
    docstring."""

    key: AgentEvaluationResultKey

    recommendation: str  # one of RECOMMENDATION_VALUES
    confidence: str  # one of CONFIDENCE_VALUES
    # The specific load-bearing fact(s)/signal(s) the confidence judgement
    # rests on - confidence must never be asserted without this (Agent
    # Evaluation Policy V1 architecture report, Section H: confidence by
    # evidentiary MATERIALITY, never a raw unknown-count).
    confidence_basis: tuple[str, ...]

    # What is actually being evaluated - typed, validated (Section D of the
    # architecture report / Section 7 of the narrow-implementation
    # authorisation) - never arbitrary free text.
    acquisition_subject: AcquisitionSubject

    # "supporting_reasons"/"countervailing_reasons" in the Product Owner's
    # own vocabulary - kept as the pre-existing field names (identical
    # concept, already-approved MaterialSignal shape) rather than a purely
    # cosmetic rename of an already-shipped contract.
    material_positive_signals: tuple[MaterialSignal, ...] = field(default_factory=tuple)
    material_negative_signals: tuple[MaterialSignal, ...] = field(default_factory=tuple)
    material_unknowns: tuple[MaterialUnknown, ...] = field(default_factory=tuple)

    reasoning_summary: str = ""
    # One of NEXT_ACTION_VALUES - never arbitrary free text from the LLM;
    # next_action_detail carries the short human-readable qualifier
    # (architecture report, Section I: "a short human-readable explanation
    # alongside the structured action").
    next_action: str = NO_ACTION
    next_action_detail: str = ""
    # One of MONITORING_TRIGGER_VALUES, or None. REQUIRED when
    # recommendation == MONITOR (every MONITOR needs a named trigger -
    # Product Owner's own explicit rule); optional otherwise - never
    # invented merely to populate the field for PURSUE/VERIFY/NOT_RELEVANT.
    monitoring_trigger: str | None = None

    evidence_references: tuple[str, ...] = field(default_factory=tuple)

    # Copied verbatim from already-existing trusted state at evaluation
    # time - never independently recomputed by this contract, and never a
    # new fingerprinting scheme (mirrors app.db.models.BuyerMandate.
    # matching_fingerprint / app.db.models.OpportunityMonitoringState.
    # fingerprint exactly).
    mandate_fingerprint: str = ""
    opportunity_fingerprint: str = ""

    # Composite descriptor identifying which policy versions produced this
    # result - e.g. "mandate_interpretation=1;acquisition_type_interpretation=1".
    # Deliberately a plain string, not yet a structured evaluation-policy
    # version of its own (Agent Evaluation Policy V1 does not exist yet).
    evaluation_policy_version: str = ""

    def __post_init__(self) -> None:
        if self.recommendation not in RECOMMENDATION_VALUES:
            raise ValueError(f"recommendation {self.recommendation!r} is not one of {sorted(RECOMMENDATION_VALUES)}")
        if self.confidence not in CONFIDENCE_VALUES:
            raise ValueError(f"confidence {self.confidence!r} is not one of {sorted(CONFIDENCE_VALUES)}")
        if self.recommendation == MONITOR and not self.monitoring_trigger:
            raise ValueError("monitoring_trigger is required whenever recommendation == MONITOR")
        if self.monitoring_trigger is not None and self.monitoring_trigger not in MONITORING_TRIGGER_VALUES:
            raise ValueError(f"monitoring_trigger {self.monitoring_trigger!r} is not one of {sorted(MONITORING_TRIGGER_VALUES)}")
        if self.next_action not in NEXT_ACTION_VALUES:
            raise ValueError(f"next_action {self.next_action!r} is not one of {sorted(NEXT_ACTION_VALUES)}")
        if not isinstance(self.acquisition_subject, AcquisitionSubject):
            raise ValueError("acquisition_subject must be an AcquisitionSubject instance, never a bare string")


# --- Execution wrapper: technical failure is never a commercial recommendation ---

SUCCESS = "SUCCESS"
FAILED = "FAILED"

EXECUTION_STATUS_VALUES = frozenset({SUCCESS, FAILED})

# Bounded failure reason codes (Section 19 of the narrow-implementation
# authorisation) - never free text, so a caller can branch on these
# deterministically.
UNSUPPORTED_POLICY_VERSION = "UNSUPPORTED_POLICY_VERSION"
ACQUISITION_TYPE_NOT_IN_MANDATE = "ACQUISITION_TYPE_NOT_IN_MANDATE"
CORRUPT_OR_MISSING_ACQUISITION_SUBJECT = "CORRUPT_OR_MISSING_ACQUISITION_SUBJECT"
INVALID_PACKET_CONTRACT = "INVALID_PACKET_CONTRACT"
CONTRADICTORY_LOAD_BEARING_FACTS = "CONTRADICTORY_LOAD_BEARING_FACTS"
INVALID_EVIDENCE_REFERENCES = "INVALID_EVIDENCE_REFERENCES"
MALFORMED_LLM_OUTPUT = "MALFORMED_LLM_OUTPUT"
UNSUPPORTED_LANGUAGE_DETECTED = "UNSUPPORTED_LANGUAGE_DETECTED"

FAILURE_REASON_VALUES = frozenset({
    UNSUPPORTED_POLICY_VERSION, ACQUISITION_TYPE_NOT_IN_MANDATE, CORRUPT_OR_MISSING_ACQUISITION_SUBJECT,
    INVALID_PACKET_CONTRACT, CONTRADICTORY_LOAD_BEARING_FACTS, INVALID_EVIDENCE_REFERENCES,
    MALFORMED_LLM_OUTPUT, UNSUPPORTED_LANGUAGE_DETECTED,
})


@dataclass(frozen=True)
class EvaluationExecutionResult:
    """The actual return type of app.policy.acquisition_evaluate.evaluate().

    Keeps EXECUTION STATUS (did the evaluation run successfully) structurally
    separate from COMMERCIAL RECOMMENDATION (what the Agent concluded) - a
    technical/structural failure is represented by status=FAILED with
    evaluation=None, NEVER by a fifth value on RECOMMENDATION_VALUES and
    NEVER by silently returning VERIFY. `retry_count` records how many
    bounded repair attempts were used (app.policy.acquisition_evaluate's own
    documented retry policy) - 0 means the first LLM response was already
    valid."""

    status: str  # one of EXECUTION_STATUS_VALUES
    evaluation: AgentEvaluationResult | None = None
    failure_reason: str | None = None
    retry_count: int = 0
    # Free-text diagnostic only (e.g. the underlying exception type/message
    # for MALFORMED_LLM_OUTPUT) - never persisted, never shown to a buyer,
    # never branched on; exists purely so a FAILED result is diagnosable
    # after the fact instead of silently discarding the real cause.
    diagnostic_detail: str | None = None

    def __post_init__(self) -> None:
        if self.status not in EXECUTION_STATUS_VALUES:
            raise ValueError(f"status {self.status!r} is not one of {sorted(EXECUTION_STATUS_VALUES)}")
        if self.status == SUCCESS and self.evaluation is None:
            raise ValueError("evaluation is required when status == SUCCESS")
        if self.status == FAILED and self.evaluation is not None:
            raise ValueError("evaluation must be None when status == FAILED")
        if self.status == FAILED and self.failure_reason not in FAILURE_REASON_VALUES:
            raise ValueError(f"failure_reason {self.failure_reason!r} is not one of {sorted(FAILURE_REASON_VALUES)}")
