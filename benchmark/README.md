# Agent Evaluation Benchmark V1

Compares Agent Evaluation Policy V1 across explicit OpenAI model/reasoning
configurations, on a small, frozen, human-reviewed case set — to answer
"what materially improves if we move away from `gpt-4o-mini`?", never
"which model scores highest on a generic benchmark."

See `docs/PRODUCT_ROADMAP.md` and the two governing design documents for the
full rationale:
- *PropertyAIgent — Agent Evaluation Benchmark V1 Design & Repository Audit
  Report* (read-only design phase)
- *PropertyAIgent — Agent Evaluation Benchmark V1 Implementation Report*
  (this implementation gate)

## What lives here

- `benchmark_case.py` — the `BenchmarkCase` schema (two frozen layers — see
  below), the golden-invariant name registry, and `BENCHMARK_VERSION`.
- `extraction.py` — a **read-only** tool that builds a candidate
  `BenchmarkCase` from one explicit `(opportunity_id, buyer_key,
  acquisition_type)` triple. Never calls OpenAI, never writes production
  data, never auto-approves a case.
- `scoring.py` — critical-incident classification (`PASS` /
  `QUALITY_CONCERN` / `CRITICAL_INCIDENT`) and per-configuration scorecard
  aggregation. Deliberately has **no single weighted score** and **never
  disqualifies a model** — that decision belongs to the Product Owner.
- `cases/*.json` — the actual frozen fixtures. Version-controlled, human-
  readable, diffable. Every case ships with `approved_by_product_owner:
  false` until a human explicitly reviews and flips it.

## Two frozen layers, per case

- **Layer A** (`frozen_commercial_facts`) — a model-independent snapshot of
  the commercially material facts (mirrors the same "what matters"
  reasoning as `agent_evaluation_persistence.compute_agent_evaluation_
  input_fingerprint`). Survives a future Policy/Prompt V2.
- **Layer B** (`frozen_evaluation_input`) — the exact `PromptContext`/
  reference-token table Agent Evaluation Policy V1 actually consumes.
  Guarantees byte-for-byte V1 reproducibility. Superseded wholesale (never
  patched) by a future policy version's own Layer B.

`provenance.captured_from_opportunity_id` is **provenance only** — it is
never re-resolved against live data by anything that reads a case file.

## Running it

Dry-run only (no OpenAI client is ever constructed):

```bash
python -m scripts.run_agent_evaluation_benchmark --models gpt-4o-mini,gpt-5.6-luna:medium --cases all --dry-run
```

Real execution requires **two** explicit flags, refuses any case that is
not `approved_by_product_owner`, and is never invoked from `app/`, a test,
or a deploy step:

```bash
python -m scripts.run_agent_evaluation_benchmark --models ... --cases all \
    --execute --confirm YES-RUN-REAL-AGENT-EVALUATION-BENCHMARK
```

## What this is not

- Not a database — no benchmark table exists or is planned.
- Not a generic ML experimentation platform — one policy/prompt/model axis
  at a time.
- Not persisted to `AgentEvaluationHistory` / `CurrentBuyerOpportunityState`
  / `AgentEvaluationClaim` / `AcquisitionSubjectAnchor` — completely
  isolated from production Agent state.
- Not something the Scheduled Acquisition Agent Runner ever touches.
