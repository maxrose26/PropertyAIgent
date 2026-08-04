"""Deterministic Progression Signal classifier (sprint Part 7).

No AI. No prediction. This module only ever restates, in one of seven fixed
labels, what the already-known Local Plan stage and Allocation status
already say - the same "grounded facts, not invented ones" discipline
applied everywhere else in this platform, just with no narration step at
all here. Every classification carries its own list of reasons; there is no
code path that returns a signal without also returning why.

The one hard rule that shapes every branch below: never claim an allocation
WILL be adopted. "advanced" means further along a real, published process -
not a prediction of the outcome.
"""
from __future__ import annotations

import datetime as dt

SIGNALS = ("early_stage", "progressing", "advanced", "adopted", "stalled", "removed", "unknown")

_EARLY_PLAN_STAGES = {"preparation", "early_consultation", "issues_and_options", "draft_consultation", "preferred_options"}
_EARLY_ALLOCATION_STATUSES = {"call_for_sites", "under_consideration", "reasonable_alternative", "preferred_option"}

_PROGRESSING_PLAN_STAGES = {"proposed_submission", "submitted"}
_PROGRESSING_ALLOCATION_STATUSES = {"draft_allocation", "proposed_submission_allocation"}

_ADVANCED_PLAN_STAGES = {"examination", "main_modifications", "inspector_report"}
_ADVANCED_ALLOCATION_STATUSES = {"submitted_allocation", "modification_proposed"}


def classify_progression(
    plan_status: str | None,
    allocation_status: str | None,
    *,
    expected_adoption_date: dt.date | None = None,
    today: dt.date | None = None,
    present_in_latest_version: bool = True,
) -> tuple[str, list[str]]:
    """Returns (signal, reasons). plan_status/allocation_status are expected
    to already be normalised (see app.policy.status) - this function doesn't
    do any keyword matching of its own, only reasons about the fixed
    vocabularies in app.policy.status.PLAN_STATUSES / ALLOCATION_STATUSES.

    present_in_latest_version=False is the one input that doesn't come from
    either status field directly - it's set by the caller when a
    site-allocation diff (app.policy.change_detection.diff_allocations) has
    found this allocation missing from the latest ingested version of its
    plan. That takes priority over everything else: a status field can be
    stale, but "no longer listed at all" is the clearest signal available."""
    today = today or dt.date.today()
    plan_status = plan_status or "unknown"
    allocation_status = allocation_status or "unknown"

    if not present_in_latest_version:
        return "removed", ["Not present in the latest published version of the Local Plan."]

    if allocation_status in ("removed", "rejected"):
        return "removed", [f"Allocation status is '{allocation_status}'."]

    if allocation_status == "superseded" or plan_status == "superseded":
        return "removed", ["Superseded by a later Local Plan or allocation."]

    if plan_status == "withdrawn":
        return "stalled", ["The Local Plan has been withdrawn."]

    if plan_status == "paused":
        return "stalled", ["The Local Plan has been paused."]

    if expected_adoption_date and expected_adoption_date < today and plan_status != "adopted":
        return "stalled", [
            f"Expected adoption date ({expected_adoption_date.isoformat()}) has passed without the "
            f"Local Plan being adopted."
        ]

    if plan_status == "adopted" and allocation_status == "adopted_allocation":
        return "adopted", ["The Local Plan is adopted and this allocation is confirmed adopted within it."]

    if plan_status == "adopted" and allocation_status != "adopted_allocation":
        return "unknown", [
            "The Local Plan is adopted but this allocation's own status has not been independently "
            "confirmed as adopted - not the same as the allocation itself being adopted."
        ]

    reasons: list[str] = []
    if plan_status in _ADVANCED_PLAN_STAGES:
        reasons.append(f"Local Plan stage is '{plan_status}'.")
    if allocation_status in _ADVANCED_ALLOCATION_STATUSES:
        reasons.append(f"Allocation status is '{allocation_status}'.")
    if reasons:
        return "advanced", reasons

    if plan_status in _PROGRESSING_PLAN_STAGES:
        reasons.append(f"Local Plan stage is '{plan_status}'.")
    if allocation_status in _PROGRESSING_ALLOCATION_STATUSES:
        reasons.append(f"Allocation status is '{allocation_status}'.")
    if reasons:
        return "progressing", reasons

    if plan_status in _EARLY_PLAN_STAGES:
        reasons.append(f"Local Plan stage is '{plan_status}'.")
    if allocation_status in _EARLY_ALLOCATION_STATUSES:
        reasons.append(f"Allocation status is '{allocation_status}'.")
    if reasons:
        return "early_stage", reasons

    return "unknown", [
        f"Local Plan stage ('{plan_status}') and allocation status ('{allocation_status}') don't map to a "
        f"known progression stage - insufficient data to classify."
    ]
