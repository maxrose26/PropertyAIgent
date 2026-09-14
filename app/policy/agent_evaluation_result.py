"""Agent Evaluation Foundation - AgentEvaluationResult domain contract
(narrow pre-Agent foundation; Product Owner review of the Agent Evaluation
Policy V1 architecture report and its refinement).

A PURE DOMAIN RESULT CONTRACT ONLY. No LLM call, no recommendation
generation, and no database persistence are implemented here or anywhere
in this task - this module defines the SHAPE a future Agent Evaluation
Policy's own evaluation function would return, so that shape can be
designed, reviewed, and tested before any evaluation logic exists.

Nothing in PropertyAIgent constructs an AgentEvaluationResult today except
this module's own tests.

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
    """One fact the evaluation identified as unresolved. `blocking` marks
    whether this unknown, if resolved unfavourably, could plausibly change
    the recommendation; `resolvable` marks whether a plausible bounded
    capability could establish it. Both are judgements the (not-yet-built)
    evaluation logic makes, recorded here so they are inspectable rather
    than implicit in prose."""

    fact: str
    blocking: bool
    resolvable: bool


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

    # What is actually being evaluated - the whole allocation, a linked
    # phase/parcel, the affordable package, or the scheme as a delivery
    # vehicle (architecture report, Section C's "acquisition-subject
    # resolution" step).
    acquisition_subject: str

    material_positive_signals: tuple[MaterialSignal, ...] = field(default_factory=tuple)
    material_negative_signals: tuple[MaterialSignal, ...] = field(default_factory=tuple)
    material_unknowns: tuple[MaterialUnknown, ...] = field(default_factory=tuple)

    reasoning_summary: str = ""
    next_action: str = ""
    # REQUIRED when recommendation == MONITOR (every MONITOR needs a named
    # trigger - Product Owner's own explicit rule); optional otherwise (a
    # PURSUE/VERIFY may still usefully carry one).
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
