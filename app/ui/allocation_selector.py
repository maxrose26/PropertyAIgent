"""Pure helper functions for the Local Plan Sites "Allocation detail"
selector (feature/allocation-image-discovery-ui) - deterministic ordering,
image-availability labelling, filtering, and the coverage message. Kept
out of the page script itself so they're unit-testable without a
Streamlit runtime, mirroring app.ui.site_headline's role for the map
tooltip (Sprint 3A, "Map Navigation and Site UX").

Root cause this module fixes: app/ui/pages/3_Local_Plan_Sites.py's
Allocation detail selectbox previously defaulted (Streamlit's own
index=0 default) to the first LocalPlanSite row an unordered SQL SELECT
happened to return - reliably an allocation with no image, silently
burying the one allocation that actually had a confirmed map 37 rows
down an unordered list. Nothing here touches the VisualEvidence data
model or the extraction pipeline - it only orders/labels/filters
whatever app.visuals.site_view.build_allocation_image_status already
returns.
"""
from __future__ import annotations

IMAGE_STATUS_LABELS = {
    "confirmed": "Map available",
    "needs_review": "Awaiting review",
    "none": "No confirmed map",
}

FILTER_ALL = "All allocations"
FILTER_CHOICES = (
    FILTER_ALL,
    "Allocations with confirmed maps",
    "Allocations awaiting visual review",
    "Allocations with no visual evidence",
)

_FILTER_TO_STATUS = {
    "Allocations with confirmed maps": "confirmed",
    "Allocations awaiting visual review": "needs_review",
    "Allocations with no visual evidence": "none",
}


def sort_allocations(allocations: list, council_names: dict) -> list:
    """Deterministic order: council name (falling back to its code when
    unknown), policy reference (present before absent, then
    alphabetically), site name, then id as the final, always-unique
    tie-breaker - so the same list renders in the same order on every
    rerun, unlike an unordered SQL SELECT (the actual root cause of the
    "opens on an arbitrary no-image allocation" bug)."""

    def key(allocation):
        council_label = council_names.get(allocation.council_code) or allocation.council_code or ""
        has_reference = allocation.policy_reference is not None
        return (
            council_label.lower(),
            not has_reference,
            (allocation.policy_reference or "").lower(),
            (allocation.site_name or "").lower(),
            allocation.id,
        )

    return sorted(allocations, key=key)


def format_allocation_option(allocation, image_status: str) -> str:
    """e.g. "Northern Gateway — JPA1.1 — Map available"."""
    reference = allocation.policy_reference or "(no ref)"
    status_label = IMAGE_STATUS_LABELS.get(image_status, IMAGE_STATUS_LABELS["none"])
    return f"{allocation.site_name} — {reference} — {status_label}"


def filter_allocations_by_image_status(allocations: list, image_status_by_id: dict, filter_choice: str) -> list:
    """filter_choice: one of FILTER_CHOICES. FILTER_ALL is a no-op -
    everything else narrows to allocations whose
    image_status_by_id.get(id, "none") matches the chosen status."""
    target_status = _FILTER_TO_STATUS.get(filter_choice)
    if target_status is None:
        return list(allocations)
    return [a for a in allocations if image_status_by_id.get(a.id, "none") == target_status]


def coverage_message(allocations: list, image_status_by_id: dict) -> str:
    """"1 of 47 allocations currently has a confirmed map image." -
    computed dynamically against whatever list is passed in; the caller
    decides whether that's every allocation or an already
    council-filtered subset."""
    total = len(allocations)
    confirmed = sum(1 for a in allocations if image_status_by_id.get(a.id, "none") == "confirmed")
    noun = "allocation" if total == 1 else "allocations"
    verb = "has" if confirmed == 1 else "have"
    return f"{confirmed} of {total} {noun} currently {verb} a confirmed map image."
