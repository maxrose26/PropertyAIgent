"""Agent Evaluation Benchmark V1 - version-controlled fixtures + harness.

NEVER imported by app/ at runtime. This package exists purely to let an
operator (never a scheduled job, never a test, never a deploy step) compare
Agent Evaluation Policy V1 across explicit OpenAI model/reasoning
configurations, using a small, frozen, Product-Owner-reviewed case set.

See benchmark/README.md for the full design rationale.
"""
