"""Normalised Local Plan and Allocation status vocabularies, plus best-effort
mapping from a council's own wording to them.

Every mapping function here is deliberately conservative: if a raw status
string doesn't clearly match a known stage, the result is "unknown" - never
a guess, and never "adopted" unless the raw text actually says so. A wrong
guess here is worse than an honest "unknown", because a status flows
straight into app.policy.progression's classifier and, from there, onto a
Site's own page - the exact case Part 6 of the sprint brief calls out
directly: "Never display a draft allocation as adopted."
"""
from __future__ import annotations

# Ordered earliest -> latest in a legacy (2004 Act) Local Plan's lifecycle.
# "unknown" is a valid, storable value - not just an error sentinel - for a
# status this codebase hasn't seen worded that way yet.
PLAN_STATUSES = (
    "preparation",
    "early_consultation",
    "issues_and_options",
    "draft_consultation",
    "preferred_options",
    "proposed_submission",
    "submitted",
    "examination",
    "main_modifications",
    "inspector_report",
    "adopted",
    "paused",
    "withdrawn",
    "superseded",
    "unknown",
)

ALLOCATION_STATUSES = (
    "call_for_sites",
    "under_consideration",
    "reasonable_alternative",
    "preferred_option",
    "draft_allocation",
    "proposed_submission_allocation",
    "submitted_allocation",
    "modification_proposed",
    "adopted_allocation",
    "removed",
    "rejected",
    "safeguarded",
    "superseded",
    "unknown",
)

# Ordered most-specific-first: a raw phrase like "Proposed Submission (Reg
# 19)" must match "proposed submission" (a distinct, EARLIER stage) before
# the more generic "submission"/"submitted" keyword lower down would
# otherwise catch it. Order is load-bearing here, not cosmetic.
_PLAN_STATUS_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("withdrawn", "withdrawn"),
    ("superseded", "superseded"),
    ("suspend", "paused"),
    ("paused", "paused"),
    ("on hold", "paused"),
    ("adopted", "adopted"),
    ("adoption", "adopted"),
    ("inspector", "inspector_report"),
    ("main modification", "main_modifications"),
    ("examination", "examination"),
    ("proposed submission", "proposed_submission"),
    ("regulation 19", "proposed_submission"),
    ("reg 19", "proposed_submission"),
    ("submitted", "submitted"),
    ("submission", "submitted"),
    ("preferred option", "preferred_options"),
    ("draft", "draft_consultation"),
    ("regulation 18", "issues_and_options"),
    ("reg 18", "issues_and_options"),
    ("issues and options", "issues_and_options"),
    ("early consultation", "early_consultation"),
    ("early engagement", "early_consultation"),
    ("scoping", "preparation"),
    ("preparation", "preparation"),
)

_ALLOCATION_STATUS_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("removed", "removed"),
    ("reject", "rejected"),
    ("superseded", "superseded"),
    ("safeguard", "safeguarded"),
    ("adopted", "adopted_allocation"),
    ("modification", "modification_proposed"),
    ("proposed submission", "proposed_submission_allocation"),
    ("submitted", "submitted_allocation"),
    ("submission", "submitted_allocation"),
    ("draft", "draft_allocation"),
    ("preferred option", "preferred_option"),
    ("reasonable alternative", "reasonable_alternative"),
    ("under consideration", "under_consideration"),
    ("call for sites", "call_for_sites"),
)


def normalise_plan_status(raw: str | None) -> str:
    """Best-effort mapping from a council's own status wording to
    PLAN_STATUSES. Returns "unknown" rather than guessing when nothing
    matches - see module docstring."""
    if not raw or not raw.strip():
        return "unknown"
    lowered = raw.strip().lower()
    for keyword, normalised in _PLAN_STATUS_KEYWORDS:
        if keyword in lowered:
            return normalised
    return "unknown"


def normalise_allocation_status(raw: str | None) -> str:
    """Best-effort mapping from a council's own allocation-status wording to
    ALLOCATION_STATUSES. Same conservative "unknown, not a guess" rule as
    normalise_plan_status."""
    if not raw or not raw.strip():
        return "unknown"
    lowered = raw.strip().lower()
    for keyword, normalised in _ALLOCATION_STATUS_KEYWORDS:
        if keyword in lowered:
            return normalised
    return "unknown"


def derive_allocation_status_from_plan_status(plan_status_raw: str | None) -> tuple[str, str]:
    """Best-effort default for allocations that predate this sprint and have
    no allocation-level status of their own (only ever had the OLD
    plan-level plan_status field to go on). Deliberately maps to the
    EARLIEST plausible allocation status for a given plan status, never to
    "adopted_allocation" - an allocation's own status can lag behind its
    plan's (a plan can be adopted while a specific late-added allocation is
    still going through its own confirmation), so assuming they moved
    together would risk exactly the "draft shown as adopted" mistake this
    module exists to prevent from the OTHER direction (adopted plan,
    unconfirmed allocation). Callers should treat the result as
    review_status="needs_confirmation", never "auto_applied" - see
    scripts/migrate_policy_intelligence.py.
    """
    plan_status = normalise_plan_status(plan_status_raw)
    if plan_status == "adopted":
        # Deliberately NOT "adopted_allocation" - see docstring above.
        return "submitted_allocation", f"derived from legacy plan_status={plan_status_raw!r} (plan adopted, allocation status not independently confirmed)"
    if plan_status in ("examination", "main_modifications", "inspector_report", "submitted", "proposed_submission"):
        return "proposed_submission_allocation", f"derived from legacy plan_status={plan_status_raw!r}"
    return "draft_allocation", f"derived from legacy plan_status={plan_status_raw!r}"
