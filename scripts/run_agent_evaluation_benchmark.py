"""Agent Evaluation Benchmark V1 - operator-only runner (Implementation
Gate, Section 23/Section 24 cost safeguards).

    python -m scripts.run_agent_evaluation_benchmark --models gpt-4o-mini --cases all --dry-run
    python -m scripts.run_agent_evaluation_benchmark --models gpt-4o-mini,gpt-5.6-luna:medium --cases all --dry-run

Dry-run (no real OpenAI calls, no client constructed at all) is the
default whenever --execute is absent - mirrors the existing repo convention
(see scripts.dry_run_gm_allocation_site_matching) of requiring TWO explicit,
independent flags before any real external call is possible:

    python -m scripts.run_agent_evaluation_benchmark --models ... --cases all \\
        --execute --confirm YES-RUN-REAL-AGENT-EVALUATION-BENCHMARK

NEVER invoked from app/ startup, a test, or a deploy step - this module is
only ever run directly by an operator. It never imports
build_current_opportunity_universe and never accepts a flag that would let
it iterate the live candidate universe - its only data source is
benchmark/cases/*.json (Section 23: "No code path may iterate
build_current_opportunity_universe() from the benchmark runner").

Refuses to make a real call against any case whose
approved_by_product_owner is not True (Section 9/17) - a candidate case
extracted but not yet reviewed can be dry-run (to see its shape/cost) but
never actually executed.

This gate (Agent Evaluation Benchmark V1 Implementation Gate) explicitly
ends WITHOUT ever passing --execute for real (Section 29) - the real-
execution code path exists and is unit-tested with a fake client
(tests/test_agent_evaluation_benchmark_harness.py), but has not been, and
must not be, invoked against the real OpenAI API in this gate.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from app.policy.agent_evaluation_prompt import PromptContext
from app.policy.agent_evaluation_result import AgentEvaluationResultKey

from benchmark.benchmark_case import BenchmarkCase, load_all_cases
from benchmark.scoring import ConfigScorecard, ModelPricing, build_case_run_record, build_config_scorecard, estimate_cost

CONFIRM_PHRASE = "YES-RUN-REAL-AGENT-EVALUATION-BENCHMARK"

# Dated, explicit pricing assumptions (Section 15/16: "currency cost remains
# benchmark/report-layer only... never inside app.policy... domain logic").
# Source: https://developers.openai.com/api/docs/pricing, verified 2026-09-15
# during the Benchmark V1 Design & Repository Audit. RE-VERIFY before any
# real execution more than a few weeks after that date - OpenAI pricing is
# not itself version-pinned by this codebase.
KNOWN_MODEL_PRICING = {
    "gpt-4o-mini": ModelPricing("gpt-4o-mini", 0.15, 0.60, "https://developers.openai.com/api/docs/pricing", "2026-09-15"),
    "gpt-5.6-luna": ModelPricing("gpt-5.6-luna", 0.20, 1.20, "https://developers.openai.com/api/docs/pricing", "2026-09-15"),
    "gpt-5.6-terra": ModelPricing("gpt-5.6-terra", 2.00, 12.00, "https://developers.openai.com/api/docs/pricing", "2026-09-15"),
    "gpt-5.6-sol": ModelPricing("gpt-5.6-sol", 4.00, 20.00, "https://developers.openai.com/api/docs/pricing", "2026-09-15"),
}

# Models known (as of the same verification date) to have NO configurable
# reasoning_effort - passing one is a caller error, not something this
# runner silently drops.
MODELS_WITHOUT_REASONING_EFFORT = frozenset({"gpt-4o-mini"})


@dataclass(frozen=True)
class ModelConfig:
    config_id: str
    model: str
    reasoning_effort: str | None

    @staticmethod
    def parse(spec: str) -> "ModelConfig":
        """"gpt-4o-mini" or "gpt-5.6-terra:medium" -> ModelConfig."""
        if ":" in spec:
            model, effort = spec.split(":", 1)
        else:
            model, effort = spec, None
        if effort is not None and model in MODELS_WITHOUT_REASONING_EFFORT:
            raise ValueError(f"{model!r} does not support a reasoning-effort override (got {effort!r}) - omit it")
        config_id = spec
        return ModelConfig(config_id=config_id, model=model, reasoning_effort=effort)


def _select_cases(all_cases: list[BenchmarkCase], spec: str) -> list[BenchmarkCase]:
    if spec == "all":
        return all_cases
    wanted = set(spec.split(","))
    selected = [c for c in all_cases if c.case_id in wanted]
    missing = wanted - {c.case_id for c in selected}
    if missing:
        raise ValueError(f"unknown case_id(s): {sorted(missing)}")
    return selected


def estimate_call_plan(cases: list[BenchmarkCase], configs: list[ModelConfig], repeats: int) -> dict:
    """Pure, zero-I/O estimate - Section 24: 'estimated maximum API calls;
    estimated cost before execution' must be knowable WITHOUT constructing
    an OpenAI client at all."""
    plan = {"per_config": {}, "total_calls_min": 0, "total_calls_max_with_repairs": 0}
    for cfg in configs:
        base_calls = 0
        for case in cases:
            if case.is_zero_llm_case:
                continue  # deterministic hard-exclusion - genuinely zero calls, never repeated
            n = repeats if case.repeat_for_consistency else 1
            base_calls += n
        plan["per_config"][cfg.config_id] = {"min_calls": base_calls, "max_calls_with_one_repair_each": base_calls * 2}
        plan["total_calls_min"] += base_calls
        plan["total_calls_max_with_repairs"] += base_calls * 2
    return plan


def estimate_cost_plan(cases: list[BenchmarkCase], configs: list[ModelConfig], repeats: int, *, assumed_input_tokens: int = 4000, assumed_output_tokens: int = 400) -> dict:
    """A ROUGH pre-execution estimate using assumed token counts (no real
    call has happened yet, so no real usage exists) - clearly labelled as
    such. Only KNOWN_MODEL_PRICING entries are estimated; an unknown model
    is reported, never silently skipped or assumed free."""
    plan = estimate_call_plan(cases, configs, repeats)
    costs = {}
    for cfg in configs:
        pricing = KNOWN_MODEL_PRICING.get(cfg.model)
        calls = plan["per_config"][cfg.config_id]["max_calls_with_one_repair_each"]
        if pricing is None:
            costs[cfg.config_id] = {"estimated_cost_usd": None, "note": f"no known pricing for {cfg.model!r} - update KNOWN_MODEL_PRICING"}
            continue
        per_call = assumed_input_tokens / 1_000_000 * pricing.input_price_per_million + assumed_output_tokens / 1_000_000 * pricing.output_price_per_million
        costs[cfg.config_id] = {"estimated_cost_usd": round(per_call * calls, 4), "assumption": f"{assumed_input_tokens} input / {assumed_output_tokens} output tokens per call (rough, pre-execution)"}
    return costs


def _reconstruct_context(case: BenchmarkCase) -> PromptContext:
    """Rebuilds the EXACT PromptContext Agent Evaluation Policy V1 would
    have built at capture time, from the case's own frozen Layer A/B -
    never from live data, never re-resolving captured_from_opportunity_id
    against the database."""
    b = case.frozen_evaluation_input
    a = case.frozen_commercial_facts
    return PromptContext(
        buyer_key=b.buyer_key, acquisition_type=b.acquisition_type, opportunity_type=b.opportunity_type,
        opportunity_id=case.provenance.captured_from_opportunity_id,  # identity label only, never re-resolved
        mandate_interpretation_lines=b.mandate_interpretation_lines,
        buyer_fit_classification=b.buyer_fit_classification,
        buyer_fit_is_investigative_exception=b.buyer_fit_is_investigative_exception,
        buyer_fit_matches=a.buyer_fit_matches, buyer_fit_does_not_match=a.buyer_fit_non_terminal_does_not_match,
        buyer_fit_unknown=a.buyer_fit_unknown, buyer_fit_investigate=a.buyer_fit_investigate,
        reference_tokens=b.reference_tokens,
    )


def run_real_benchmark(cases: list[BenchmarkCase], configs: list[ModelConfig], repeats: int) -> list:
    """The REAL execution path - never invoked in the Implementation Gate
    session (Section 29). Exercised only by tests/test_agent_evaluation_
    benchmark_harness.py with a fake OpenAI client. Refuses any case that
    is not approved_by_product_owner. Needs NO database session at all -
    every input is already frozen in the case fixture."""
    from app.policy.acquisition_evaluate import evaluate_frozen_input_with_telemetry

    unapproved = [c.case_id for c in cases if not c.approved_by_product_owner]
    if unapproved:
        raise RuntimeError(f"refusing to execute: unapproved case(s) {unapproved} - Product Owner must approve before any real model output is seen (Section 9)")

    records = []
    for cfg in configs:
        for case in cases:
            if case.is_zero_llm_case:
                continue  # deterministic hard exclusion - already resolved at extraction time, no LLM call to make
            context = _reconstruct_context(case)
            key = AgentEvaluationResultKey(
                buyer_key=case.frozen_evaluation_input.buyer_key,
                opportunity_id=case.provenance.captured_from_opportunity_id,
                acquisition_type=case.frozen_evaluation_input.acquisition_type,
            )
            n = repeats if case.repeat_for_consistency else 1
            for repeat_index in range(n):
                result, telemetry = evaluate_frozen_input_with_telemetry(
                    context=context, key=key, model=cfg.model, reasoning_effort=cfg.reasoning_effort,
                )
                records.append(build_case_run_record(
                    case_id=case.case_id, config_id=cfg.config_id, repeat_index=repeat_index,
                    execution_result=result, telemetry=telemetry, expected_recommendation=case.expected_recommendation,
                ))
    return records


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", required=True, help="comma-separated model specs, e.g. gpt-4o-mini,gpt-5.6-terra:medium")
    parser.add_argument("--cases", required=True, help="'all' or a comma-separated list of case_id values")
    parser.add_argument("--repeats", type=int, default=3, help="repeats for cases marked repeat_for_consistency (default 3)")
    parser.add_argument("--dry-run", action="store_true", default=True, help="(default) print the call/cost estimate only, make zero OpenAI calls")
    parser.add_argument("--execute", action="store_true", help="required (with --confirm) to make REAL OpenAI calls")
    parser.add_argument("--confirm", default="", help=f"must equal {CONFIRM_PHRASE!r} together with --execute")
    args = parser.parse_args(argv)

    configs = [ModelConfig.parse(s) for s in args.models.split(",")]
    all_cases = load_all_cases()
    cases = _select_cases(all_cases, args.cases)

    call_plan = estimate_call_plan(cases, configs, args.repeats)
    cost_plan = estimate_cost_plan(cases, configs, args.repeats)

    print(f"Cases selected: {len(cases)} ({sum(1 for c in cases if c.is_zero_llm_case)} zero-LLM)")
    print(f"Configurations: {[c.config_id for c in configs]}")
    print(f"Estimated API calls: {call_plan['total_calls_min']} (min) - {call_plan['total_calls_max_with_repairs']} (max, assuming every call needs its one bounded repair)")
    for cfg_id, cost in cost_plan.items():
        print(f"  {cfg_id}: {cost}")

    if not args.execute:
        print("\nDRY RUN ONLY - no OpenAI client constructed, zero real calls made. Pass --execute --confirm ... to run for real.")
        return 0

    if args.confirm != CONFIRM_PHRASE:
        print(f"\nREFUSED: --execute requires --confirm {CONFIRM_PHRASE!r} exactly.", file=sys.stderr)
        return 1

    records = run_real_benchmark(cases, configs, args.repeats)
    for cfg in configs:
        cfg_records = [r for r in records if r.config_id == cfg.config_id]
        scorecard = build_config_scorecard(config_id=cfg.config_id, model=cfg.model, reasoning_effort=cfg.reasoning_effort, records=cfg_records)
        print(scorecard)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
