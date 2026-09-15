"""Agent Evaluation Benchmark V1 - case schema, invariant registry, and
BENCHMARK_VERSION.

Version-controlled, human-reviewable JSON fixtures only - no database
table, no ORM model (Implementation Gate, Section 16/24: "no benchmark
persistence"; "no database benchmark tables"). A BenchmarkCase carries TWO
related frozen layers (Modification #2):

  LAYER A (FrozenCommercialFacts) - a canonical, MODEL-INDEPENDENT snapshot
    of the commercially material facts used to construct the evaluation.
    Derived from the same "what is commercially material" thinking as
    app.policy.agent_evaluation_persistence.compute_agent_evaluation_input_
    fingerprint (Gate 1) - deliberately NOT a serialisation of
    OpportunityIntelligencePacket (see the Design Audit's own Section G).
    Supports FUTURE policy/prompt benchmarking: a Policy V2 harness can
    re-render its own prompt from this layer without a new extraction pass
    against production data.

  LAYER B (FrozenRenderedInput) - the EXACT app.policy.agent_evaluation_
    prompt.PromptContext / reference-token representation Agent Evaluation
    Policy V1 actually consumes. Guarantees byte-for-byte V1
    reproducibility. Superseded WHOLESALE (never patched) by a future
    Policy/Prompt V2's own Layer B - Layer A is what survives version
    changes, Layer B does not.

CaseProvenance's `captured_from_opportunity_id` is PROVENANCE ONLY
(Implementation Gate, Section 5) - benchmark execution must NEVER re-resolve
it against live data; it exists solely so a human can trace a case back to
where it came from.

Changing ANY of: frozen evidence, expected recommendation/acceptable set,
a required invariant, a forbidden claim, or the commercial rationale of an
APPROVED case requires a BENCHMARK_VERSION bump (Implementation Gate,
Section 25) - see this module's own CHANGELOG below. A case is never
silently mutated after model outputs exist for it.

CHANGELOG:
  BENCHMARK_VERSION 1 - initial schema + invariant registry (this gate).
    No case has been run against a real model yet, so no case has ever
    needed post-hoc correction.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

BENCHMARK_VERSION = 1

CASES_DIR = Path(__file__).parent / "cases"

# --- Golden invariant registry (Design Audit, Section I) --------------------
#
# Named references ONLY - the rule text itself lives in exactly one place
# (app.policy.agent_evaluation_validator's own code/docstrings for the
# machine-enforced ones; a case's own commercial_rationale/reviewer_notes
# for the human-reviewed ones) so a case file never restates rule text that
# could silently drift from the real rule (Section 19 of the Implementation
# Gate: "reuse deterministic validators wherever possible... do not
# duplicate validator logic unnecessarily").
#
# MACHINE_ENFORCED: every model in the benchmark inherits these for free via
# app.policy.acquisition_evaluate's own bounded repair/retry loop - a case
# should reference one of these only to record WHICH rule it is specifically
# designed to stress (e.g. for the repair-rate/first-pass-validity
# telemetry), never because passing it is itself evidence of model quality.
MACHINE_ENFORCED_INVARIANTS = frozenset({
    "verify_requires_material_resolvable_blocking_unknown",
    "monitor_not_investigate_now_in_disguise",
    "evidence_references_must_exist_in_context",
    "parcel_tbd_never_carries_specific_reference",
    "identify_phase_or_parcel_requires_parcel_tbd_or_phase_subject",
    "not_relevant_requires_confirmed_mandate_incompatibility",
    "monitor_not_relevant_inconsistent_with_own_signals",
    "absence_of_ownership_evidence_never_a_confirmed_negative",
    "unsupported_seller_intent_language_forbidden",
})

# HUMAN_REVIEWED: no JSON-shape check can catch these - a case referencing
# one of these is asking the Section 12/20 human reviewer to specifically
# look for this failure mode in the model's own prose.
HUMAN_REVIEWED_INVARIANTS = frozenset({
    "no_developer_to_ownership_control_inference",
    "monitor_trigger_is_genuinely_future_not_investigate_later",
    "phase_control_never_promoted_to_whole_allocation_control",
    "not_applicable_facts_never_treated_as_unknowns",
})

ALL_INVARIANTS = MACHINE_ENFORCED_INVARIANTS | HUMAN_REVIEWED_INVARIANTS


@dataclass(frozen=True)
class FrozenCommercialFacts:
    """LAYER A - see module docstring."""

    acquisition_type: str
    opportunity_type: str  # STRATEGIC_LAND | PLANNING_DELIVERY
    buyer_fit_classification: str
    buyer_fit_is_investigative_exception: bool
    buyer_fit_matches: tuple[str, ...]
    buyer_fit_unknown: tuple[str, ...]
    buyer_fit_investigate: tuple[str, ...]
    buyer_fit_non_terminal_does_not_match: tuple[str, ...]
    ownership_control_posture: str
    opportunity_facts: dict  # same shape as compute_agent_evaluation_input_fingerprint's "opportunity_facts", real values not a hash
    transaction_signal_states: dict  # .state only per signal, never .detail (mirrors the fingerprint's own exclusion)
    linked_strategic_allocation_id: int | None = None


@dataclass(frozen=True)
class FrozenRenderedInput:
    """LAYER B - see module docstring."""

    buyer_key: str
    acquisition_type: str
    opportunity_type: str
    mandate_interpretation_lines: tuple[str, ...]
    buyer_fit_classification: str
    buyer_fit_is_investigative_exception: bool
    reference_tokens: dict  # token -> human-readable fact text, verbatim from PromptContext.reference_tokens
    governing_policy_prompt_version: int
    agent_evaluation_output_schema_version: int


@dataclass(frozen=True)
class CaseProvenance:
    captured_at: str  # ISO-8601 UTC
    captured_from_opportunity_id: str  # PROVENANCE ONLY - never re-resolved at benchmark run time (Section 5)
    buyer_key: str
    mandate_key: str
    acquisition_subject_scope_key: str | None
    buyer_matching_policy_version: int
    mandate_interpretation_policy_version: int
    acquisition_type_interpretation_policy_version: int
    transaction_signal_policy_version: int
    terminal_hard_exclusion_policy_version: int
    agent_evaluation_policy_version: int


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    case_name: str
    commercial_scenario: str
    benchmark_version_introduced: int

    provenance: CaseProvenance
    frozen_commercial_facts: FrozenCommercialFacts
    frozen_evaluation_input: FrozenRenderedInput

    expected_recommendation: tuple[str, ...]  # acceptable set; a single-element tuple means "exact"
    commercial_rationale: str

    required_invariants: tuple[str, ...] = ()
    forbidden_claims: tuple[str, ...] = ()
    required_material_unknowns: tuple[str, ...] = ()
    expected_acquisition_subject_level: tuple[str, ...] | None = None
    expected_next_action: tuple[str, ...] | None = None
    monitoring_trigger_constraints: tuple[str, ...] | None = None
    repeat_for_consistency: bool = False  # Section S/22 - only judgement-sensitive cases repeat
    is_zero_llm_case: bool = False  # deterministic hard-exclusion cases - never repeated, never counted in call estimates

    reviewer_notes: str = ""
    # False until a human Product Owner review (Section 9/20) explicitly
    # approves expected_recommendation/commercial_rationale/invariants
    # BEFORE any real model output is seen. The runner (Section X) refuses
    # to execute real API calls against a case where this is False.
    approved_by_product_owner: bool = False

    def __post_init__(self) -> None:
        unknown = set(self.required_invariants) - ALL_INVARIANTS
        if unknown:
            raise ValueError(f"case {self.case_id!r} references unknown invariant(s): {sorted(unknown)}")
        if not self.expected_recommendation:
            raise ValueError(f"case {self.case_id!r} must name at least one acceptable recommendation")
        if self.is_zero_llm_case and self.repeat_for_consistency:
            raise ValueError(f"case {self.case_id!r}: a zero-LLM deterministic case must never be a consistency-repeat case")


def case_to_dict(case: BenchmarkCase) -> dict:
    return asdict(case)


def case_from_dict(data: dict) -> BenchmarkCase:
    provenance = CaseProvenance(**data["provenance"])
    layer_a = FrozenCommercialFacts(
        **{**data["frozen_commercial_facts"], **{
            k: tuple(v) for k, v in data["frozen_commercial_facts"].items()
            if k in ("buyer_fit_matches", "buyer_fit_unknown", "buyer_fit_investigate", "buyer_fit_non_terminal_does_not_match")
        }}
    )
    layer_b = FrozenRenderedInput(
        **{**data["frozen_evaluation_input"], **{
            "mandate_interpretation_lines": tuple(data["frozen_evaluation_input"]["mandate_interpretation_lines"]),
        }}
    )
    kwargs = {**data}
    kwargs["provenance"] = provenance
    kwargs["frozen_commercial_facts"] = layer_a
    kwargs["frozen_evaluation_input"] = layer_b
    kwargs["expected_recommendation"] = tuple(data["expected_recommendation"])
    kwargs["required_invariants"] = tuple(data.get("required_invariants", ()))
    kwargs["forbidden_claims"] = tuple(data.get("forbidden_claims", ()))
    kwargs["required_material_unknowns"] = tuple(data.get("required_material_unknowns", ()))
    if data.get("expected_acquisition_subject_level") is not None:
        kwargs["expected_acquisition_subject_level"] = tuple(data["expected_acquisition_subject_level"])
    if data.get("expected_next_action") is not None:
        kwargs["expected_next_action"] = tuple(data["expected_next_action"])
    if data.get("monitoring_trigger_constraints") is not None:
        kwargs["monitoring_trigger_constraints"] = tuple(data["monitoring_trigger_constraints"])
    return BenchmarkCase(**kwargs)


def save_case(case: BenchmarkCase, path: Path, *, overwrite: bool = False) -> None:
    """Refuses to silently clobber an already-APPROVED case file
    (Implementation Gate, Section 17: "must not silently overwrite an
    existing approved fixture") unless overwrite=True is passed explicitly."""
    if path.exists() and not overwrite:
        existing = case_from_dict(json.loads(path.read_text(encoding="utf-8")))
        if existing.approved_by_product_owner:
            raise FileExistsError(
                f"{path} already holds an APPROVED case ({existing.case_id!r}) - "
                "pass overwrite=True explicitly to replace it (this should be rare and deliberate)"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(case_to_dict(case), indent=2, sort_keys=False, default=str), encoding="utf-8")


def load_case(path: Path) -> BenchmarkCase:
    return case_from_dict(json.loads(path.read_text(encoding="utf-8")))


def load_all_cases(cases_dir: Path = CASES_DIR) -> list[BenchmarkCase]:
    return [load_case(p) for p in sorted(cases_dir.glob("*.json"))]
