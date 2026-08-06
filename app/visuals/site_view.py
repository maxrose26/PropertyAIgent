"""Read-only view-model builders for the Visual Evidence UI sections
(Sprint 3C, "Allocation and Site-Plan Image Extraction", Part 11 Site
Profile + Part 12 Allocation view) - keep query/selection logic out of the
UI pages themselves, mirroring app.policy.site_view's role for the Policy
Intelligence section (CLAUDE.md: "keep business logic out of the UI").

Neither function here does any ranking of its own - "primary" is simply
whichever row app.visuals.pipeline's automatic ranking (or a reviewer's
manual override, app.visuals.review.mark_primary) most recently set
is_primary=True for. A rejected image is never returned by either
function - Part 10/Part 9's "a wrong image is worse than no image" applies
to display, not just to ranking.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select

from app.db.models import VisualEvidence


def _current_non_rejected(session, **filters) -> list[VisualEvidence]:
    query = select(VisualEvidence).where(VisualEvidence.status == "current", VisualEvidence.review_status != "rejected")
    for column, value in filters.items():
        query = query.where(getattr(VisualEvidence, column) == value)
    return list(session.execute(query).scalars())


def _split_primary(images: list[VisualEvidence]) -> dict:
    primary = next((img for img in images if img.is_primary), None)
    others = [img for img in images if img is not primary]
    # Confirmed images first, then by descending AI confidence - matches
    # app.visuals.primary_selection's own ranking bias so the thumbnail
    # strip reads in the same order a human would expect after seeing
    # which one won primary.
    others.sort(key=lambda img: (img.review_status != "confirmed", -(img.extraction_confidence or 0.0)))
    return {"primary": primary, "others": others}


def build_site_visual_evidence(session, site_id: int) -> dict:
    """Returns {"primary": VisualEvidence | None, "others": [...]} for one
    Site's images."""
    return _split_primary(_current_non_rejected(session, site_id=site_id))


def build_allocation_visual_evidence(session, allocation_id: int) -> dict:
    """Returns {"primary": VisualEvidence | None, "others": [...]} for one
    Allocation (LocalPlanSite)'s images."""
    return _split_primary(_current_non_rejected(session, allocation_id=allocation_id))


def build_allocation_image_status(session, allocation_ids: list[int]) -> dict[int, str]:
    """One batched query (feature/allocation-image-discovery-ui) returning
    {allocation_id: "confirmed" | "needs_review" | "none"} for every id in
    allocation_ids - never one query per allocation, so a page listing
    dozens of allocations can label each one's image availability without
    an N+1 lookup.

    "confirmed" outranks "needs_review" when an allocation happens to have
    more than one current, non-rejected image in different review states -
    the same "confirmed is the trustworthy signal" precedence
    app.visuals.primary_selection already applies to ranking. An
    allocation with no current, non-rejected image at all gets "none"."""
    if not allocation_ids:
        return {}
    rows = session.execute(
        select(VisualEvidence.allocation_id, VisualEvidence.review_status).where(
            VisualEvidence.allocation_id.in_(allocation_ids),
            VisualEvidence.status == "current",
            VisualEvidence.review_status != "rejected",
        )
    ).all()
    best: dict[int, str] = {}
    for allocation_id, review_status in rows:
        if review_status == "confirmed":
            best[allocation_id] = "confirmed"
        elif best.get(allocation_id) != "confirmed":
            best[allocation_id] = "needs_review"
    return {aid: best.get(aid, "none") for aid in allocation_ids}


def build_allocation_visual_summaries(session, allocation_ids: list[int]) -> dict[int, dict]:
    """Allocation Discovery (Sprint 4.5) - the gallery-card equivalent of
    build_allocation_image_status, but returning the actual best evidence to
    render (primary/others), not just a status string, for every id in
    allocation_ids in ONE batched query - never one query per card. An
    allocation with no current, non-rejected image gets {"status": "none",
    "primary": None, "others": []}, same absent-is-honest convention as the
    rest of this module."""
    result = {aid: {"status": "none", "primary": None, "others": []} for aid in allocation_ids}
    if not allocation_ids:
        return result

    rows = session.execute(
        select(VisualEvidence).where(
            VisualEvidence.allocation_id.in_(allocation_ids),
            VisualEvidence.status == "current",
            VisualEvidence.review_status != "rejected",
        )
    ).scalars()
    grouped: dict[int, list[VisualEvidence]] = defaultdict(list)
    for row in rows:
        grouped[row.allocation_id].append(row)

    for allocation_id, images in grouped.items():
        split = _split_primary(images)
        has_confirmed = (split["primary"] is not None) or any(img.review_status == "confirmed" for img in split["others"])
        status = "confirmed" if has_confirmed else "needs_review"
        result[allocation_id] = {"status": status, "primary": split["primary"], "others": split["others"]}
    return result


def build_plan_wide_policies_map(session, local_plan_ids: list[int]) -> dict[int, VisualEvidence]:
    """The Stockport-style fallback (Allocation Discovery, Part 11): some
    councils publish allocation boundaries only through one authority-wide
    Policies Map, never a per-allocation image - a VisualEvidence row with
    local_plan_id set, allocation_id null, image_type="policies_map_extract"
    (see app.visuals.matching.match_report_visual: a page that can't be tied
    to one specific allocation still gets local_plan_id, never a guessed
    allocation_id). ONE batched query for every plan id in local_plan_ids -
    never one query per card. Deliberately scoped to image_type=
    "policies_map_extract" only, not any plan-wide image - showing an
    unrelated plan-wide "unknown"-type page as if it were the Policies Map
    would misrepresent what the image actually is (Part 11: "must not be
    presented as though it were an allocation-specific boundary image")."""
    if not local_plan_ids:
        return {}
    rows = session.execute(
        select(VisualEvidence).where(
            VisualEvidence.local_plan_id.in_(local_plan_ids),
            VisualEvidence.allocation_id.is_(None),
            VisualEvidence.image_type == "policies_map_extract",
            VisualEvidence.status == "current",
            VisualEvidence.review_status != "rejected",
        )
    ).scalars()
    grouped: dict[int, list[VisualEvidence]] = defaultdict(list)
    for row in rows:
        grouped[row.local_plan_id].append(row)

    best: dict[int, VisualEvidence] = {}
    for local_plan_id, images in grouped.items():
        images.sort(key=lambda img: (img.review_status != "confirmed", -(img.extraction_confidence or 0.0)))
        best[local_plan_id] = images[0]
    return best
