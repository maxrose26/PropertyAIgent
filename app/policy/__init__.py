"""Policy Intelligence domain logic - status normalisation, deterministic
progression classification, and change detection. Kept independent of both
the database session and the UI (CLAUDE.md's "keep business logic out of
the UI") so every rule here is testable in isolation - see tests/test_status.py,
tests/test_progression.py, tests/test_change_detection.py.

Nothing in this package calls an LLM. Every classification is a deterministic
function of already-known facts - see specifications/004-core-domain-model.md
and the Policy Intelligence Foundation sprint brief (Part 7: "Do NOT use AI.
Do NOT predict outcomes.").
"""
