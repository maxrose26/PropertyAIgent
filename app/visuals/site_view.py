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
