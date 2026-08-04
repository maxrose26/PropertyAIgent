"""Primary-image selection (Sprint 3C, "Allocation and Site-Plan Image
Extraction", Part 9) - deterministic ranking of which visual (if any) is
THE headline image shown for a Site or an Allocation, when several
confirmed and/or unreviewed candidates exist.

A human-confirmed image always outranks every unreviewed one, regardless
of type - Part 9: "human-confirmed must outrank AI". Within the confirmed
tier, ranking follows an explicit type-priority order (most specific/
useful type first, per object kind). Only when there is genuinely no
confirmed image at all does the highest-confidence unreviewed AI
classification stand in as primary - itself still review_status=
"needs_review", never silently treated as trustworthy just because it was
picked. A rejected image can never become primary under any
circumstances - filtered out unconditionally before ranking, since
displaying the wrong image is the single worst failure mode this sprint
is built to avoid.
"""
from __future__ import annotations

SITE_TYPE_PRIORITY = [
    "red_line_boundary",
    "site_location_plan",
    "proposed_site_layout",
    "masterplan",
    "phasing_plan",
]

ALLOCATION_TYPE_PRIORITY = [
    "allocation_map",
    "policies_map_extract",
    "development_framework",
]

_TYPE_PRIORITY = {"site": SITE_TYPE_PRIORITY, "allocation": ALLOCATION_TYPE_PRIORITY}


def _type_rank(image_type: str | None, priority_list: list[str]) -> int:
    try:
        return priority_list.index(image_type)
    except ValueError:
        return len(priority_list)  # "other confirmed" - below every named type, still above nothing


def _eligible(image) -> bool:
    if getattr(image, "review_status", None) == "rejected":
        return False
    if getattr(image, "status", "current") != "current":
        return False  # a superseded image can never be primary
    return True


def _sort_key(image, priority_list: list[str]) -> tuple:
    is_confirmed = getattr(image, "review_status", None) == "confirmed"
    confirmed_rank = 0 if is_confirmed else 1  # confirmed always sorts first
    type_rank = _type_rank(getattr(image, "image_type", None), priority_list) if is_confirmed else 0
    confidence = getattr(image, "extraction_confidence", None) or 0.0
    return (confirmed_rank, type_rank, -confidence)


def select_primary(images: list, target: str):
    """images: candidate VisualEvidence rows for ONE object (a single
    Site's images, or a single Allocation's images) - rejected/superseded
    rows are filtered out internally, not assumed pre-filtered. Returns
    the winning image, or None if nothing eligible remains."""
    if target not in _TYPE_PRIORITY:
        raise ValueError(f"Unknown primary-selection target {target!r} - expected 'site' or 'allocation'")
    eligible = [img for img in images if _eligible(img)]
    if not eligible:
        return None
    priority_list = _TYPE_PRIORITY[target]
    return min(eligible, key=lambda img: _sort_key(img, priority_list))


def compute_primary_flags(images: list, target: str) -> dict:
    """Returns {image.id: should_be_primary} for every image passed in -
    exactly one True (the winner from select_primary, if any), everything
    else False. A pipeline applies this as an update pass so is_primary
    always reflects the current ranking, even after a new confirmation
    changes the winner (Part 9: "one primary per object/purpose")."""
    winner = select_primary(images, target)
    return {getattr(img, "id"): (img is winner) for img in images}
