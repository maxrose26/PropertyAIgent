"""Deterministic change detection for Policy Intelligence (sprint Parts 9 &
11): hashing a monitored source's content, diffing one ingest's allocations
against the previous ones, and deciding what's safe to apply automatically
versus what needs a human in the loop.

Nothing here overwrites data - every function returns a description of what
changed; the caller (ingest_local_plan.py, or a future monitoring pipeline
stage) decides what to do with that description, always via an explicit
PolicyChangeEvent row rather than a silent field overwrite.
"""
from __future__ import annotations

import hashlib

EVENT_TYPES = (
    "new_plan_version",
    "stage_change",
    "adoption",
    "withdrawal",
    "new_allocation",
    "allocation_removed",
    "allocation_retained",
    "allocation_amended",
    "capacity_changed",
)

# Only these event types are safe to auto-apply (Part 11): a brand new
# allocation appearing, or an allocation confirmed unchanged, are both
# purely additive/no-op outcomes that can't misrepresent anything that
# already existed. Every other event type changes or removes something a
# user may already be relying on, so it goes to the review queue instead -
# deliberately more conservative than it strictly needs to be, since a
# wrongly-auto-applied change here would misinform an acquisition decision.
_AUTO_APPLY_EVENT_TYPES = frozenset({"new_allocation", "allocation_retained"})

_CAPACITY_FIELDS = ("minimum_dwellings", "indicative_capacity", "maximum_capacity")


def compute_content_hash(text: str) -> str:
    """Whitespace-normalised sha256 - two fetches of a PDF/webpage that
    differ only in incidental whitespace shouldn't register as a change."""
    normalised = " ".join((text or "").split())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def classify_source_check(previous_hash: str | None, new_hash: str) -> str:
    """"first_check" (nothing to compare against yet - not a change),
    "unchanged", or "changed". Hashes are compared, never URLs alone - a
    URL staying the same says nothing about whether the document behind it
    did (Part 9: "Use hashes rather than URLs alone")."""
    if previous_hash is None:
        return "first_check"
    return "changed" if previous_hash != new_hash else "unchanged"


def diff_plan(old: dict | None, new: dict) -> list[dict]:
    """old/new: dicts with at least "plan_version" and "status" keys
    (normalised status). old=None means this plan has never been seen
    before - reported as new_plan_version, not silently treated as a
    no-op. Returns a list of change dicts: {event_type, old_value,
    new_value, detail}."""
    if old is None:
        return [{
            "event_type": "new_plan_version",
            "old_value": None,
            "new_value": new.get("plan_version"),
            "detail": "First time this Local Plan has been recorded.",
        }]

    events: list[dict] = []
    if old.get("plan_version") != new.get("plan_version"):
        events.append({
            "event_type": "new_plan_version",
            "old_value": old.get("plan_version"),
            "new_value": new.get("plan_version"),
            "detail": "Plan version changed.",
        })

    old_status, new_status = old.get("status"), new.get("status")
    if old_status != new_status:
        if new_status == "adopted":
            event_type = "adoption"
            detail = "Local Plan adopted."
        elif new_status == "withdrawn":
            event_type = "withdrawal"
            detail = "Local Plan withdrawn."
        else:
            event_type = "stage_change"
            detail = "Local Plan stage changed."
        events.append({"event_type": event_type, "old_value": old_status, "new_value": new_status, "detail": detail})

    return events


def diff_allocations(old: list[dict], new: list[dict]) -> list[dict]:
    """old/new: lists of dicts, each with at least "policy_reference" plus
    the capacity/status fields being compared. Matched by policy_reference -
    the one field a source document always states for an individual
    allocation, unlike site_name (which can be reworded between plan
    versions without the allocation itself changing). Returns one event dict
    per policy_reference, covering every allocation present in either list -
    including "allocation_retained" for ones with no change at all, so a
    caller can distinguish "checked, nothing changed" from "not checked"."""
    old_by_ref = {o["policy_reference"]: o for o in old}
    new_by_ref = {n["policy_reference"]: n for n in new}
    events: list[dict] = []

    for ref, new_row in new_by_ref.items():
        if ref not in old_by_ref:
            events.append({
                "policy_reference": ref, "event_type": "new_allocation",
                "old_value": None, "new_value": ref,
                "detail": f"New allocation {ref} in the latest version.",
            })
            continue

        old_row = old_by_ref[ref]
        capacity_changed = any(old_row.get(f) != new_row.get(f) for f in _CAPACITY_FIELDS)
        status_changed = old_row.get("allocation_status") != new_row.get("allocation_status")

        if capacity_changed:
            events.append({
                "policy_reference": ref, "event_type": "capacity_changed",
                "old_value": str({f: old_row.get(f) for f in _CAPACITY_FIELDS}),
                "new_value": str({f: new_row.get(f) for f in _CAPACITY_FIELDS}),
                "detail": f"Capacity figures for {ref} changed.",
            })
        if status_changed:
            events.append({
                "policy_reference": ref, "event_type": "allocation_amended",
                "old_value": old_row.get("allocation_status"), "new_value": new_row.get("allocation_status"),
                "detail": f"Allocation status for {ref} changed.",
            })
        if not capacity_changed and not status_changed:
            events.append({
                "policy_reference": ref, "event_type": "allocation_retained",
                "old_value": ref, "new_value": ref,
                "detail": f"{ref} unchanged from the previous version.",
            })

    for ref, old_row in old_by_ref.items():
        if ref not in new_by_ref:
            events.append({
                "policy_reference": ref, "event_type": "allocation_removed",
                "old_value": ref, "new_value": None,
                "detail": f"{ref} is no longer present in the latest version.",
            })

    return events


def classify_confidence(event_type: str) -> str:
    """"auto_applied" or "needs_review" - see _AUTO_APPLY_EVENT_TYPES."""
    return "auto_applied" if event_type in _AUTO_APPLY_EVENT_TYPES else "needs_review"
