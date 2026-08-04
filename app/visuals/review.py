"""Lightweight review workflow for VisualEvidence rows (Sprint 3C,
"Allocation and Site-Plan Image Extraction", Part 10) - confirm, reject,
change type, relink, mark primary. Deliberately NOT a large standalone
media-management system: five small, explicit actions, each committing
its own change immediately, mirroring app.policy.review's
approve_change/reject_change shape.

Every AI classification starts review_status="needs_review"
(app.visuals.pipeline never writes "confirmed" itself, regardless of the
model's own reported confidence - see that module's docstring) - these
functions are the only code paths allowed to move a row out of that
state. A rejected image stays rejected on every future pipeline rerun
unless the source content or classification prompt version actually
changes (Part 10) - that check lives in app.visuals.pipeline, which
consults review_status before ever re-classifying a page whose
VisualEvidence row already exists; this module only records the decision
itself.
"""
from __future__ import annotations

from app.db.models import VisualEvidence, utcnow

# Sentinel distinguishing "argument not passed, leave this link untouched"
# from "argument explicitly passed as None, clear this link" - relink_image
# needs both.
_UNSET = object()


def confirm_image(session, image: VisualEvidence, confirmed_by: str, image_type: str | None = None) -> None:
    """Marks image as human-confirmed. image_type, if given, lets a
    reviewer correct the AI's classification in the same action (Part 10:
    "change type") rather than requiring two separate calls."""
    if image_type is not None:
        image.image_type = image_type
    image.review_status = "confirmed"
    image.confirmed_by = confirmed_by
    image.confirmed_at = utcnow()
    image.rejection_reason = None
    session.commit()


def reject_image(session, image: VisualEvidence, reason: str, confirmed_by: str) -> None:
    """Rejects image. The row itself is never deleted - just marked - so a
    future rerun's idempotency check (app.visuals.pipeline) can see this
    decision and skip re-proposing the same page."""
    if not reason or not reason.strip():
        raise ValueError("reject_image requires a non-empty reason")
    image.review_status = "rejected"
    image.rejection_reason = reason.strip()
    image.confirmed_by = confirmed_by
    image.confirmed_at = utcnow()
    session.commit()


def relink_image(
    session, image: VisualEvidence, *, site_id=_UNSET, application_id=_UNSET,
    local_plan_id=_UNSET, allocation_id=_UNSET,
) -> None:
    """Changes which object(s) this image is evidence for - a reviewer
    correcting a wrong or ambiguous automatic match. Only the keyword
    arguments actually PASSED are changed (including explicitly passing
    None to clear a link); anything left at the default is untouched, so
    correcting one link doesn't require restating every other one."""
    if site_id is not _UNSET:
        image.site_id = site_id
    if application_id is not _UNSET:
        image.application_id = application_id
    if local_plan_id is not _UNSET:
        image.local_plan_id = local_plan_id
    if allocation_id is not _UNSET:
        image.allocation_id = allocation_id
    session.commit()


def mark_primary(session, image: VisualEvidence, siblings: list[VisualEvidence]) -> None:
    """Sets image as the primary visual, clearing is_primary on every
    other row in siblings (the rest of the same object's current, non-
    rejected images - caller loads these). A direct manual override:
    app.visuals.primary_selection's automatic ranking will run again on a
    future pipeline pass and may recompute a different winner if the
    underlying set of confirmed images changes - this action does not
    pin the choice permanently, only sets it as of right now (a documented
    V1 simplicity trade-off, not a gap expected to matter often in
    practice, since a manually-marked CONFIRMED image already ranks at or
    near the top of the automatic ordering)."""
    image.is_primary = True
    for sibling in siblings:
        if sibling.id != image.id:
            sibling.is_primary = False
    session.commit()
