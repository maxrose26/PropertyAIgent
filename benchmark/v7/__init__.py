"""Stage 2.5B Gate A: the authoritative DETERMINISTIC v7 acquisition-policy benchmark (policy acceptance set).

NEW and separate from the v4 fixtures (benchmark/cases, agent-evaluation policy 1, kept byte-for-byte) and from the recorded v6 checkpoint
(benchmark/checkpoints/v6_checkpoint.json, kept byte-for-byte). It is not a rewritten v4 snapshot: it states, for the commercially important
acquisition situations, what the Product Owner intends under matcher policy 7, FACTS FIRST and EXPECTATION SECOND, in benchmark/v7/cases.py. benchmark/v7/runner.py then
runs the real matcher, the real family grouping and the real family presentation label and compares.

OFFLINE: no database, no network, no model call. NEVER imported by app/.
"""
from __future__ import annotations

V7_BENCHMARK_VERSION = "v7-1"
