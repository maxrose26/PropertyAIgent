"""Human review of an allocation's own Site match (Pilot Readiness PR-2,
"Existing Allocation <-> Site Matches"). Distinct from app.policy.review
(which resolves PolicyChangeEvent proposals about a LocalPlan/LocalPlanSite's
POLICY-CONTENT fields) - this module resolves the separate question of
whether LocalPlanSite.matched_site_id itself is correct, mirroring
app.visuals.review.confirm_image/reject_image's already-established
confirm/reject shape rather than inventing a new one.

Confirming or rejecting a match is a deliberate, individually-justified
human decision (never bulk, never automatic on confidence alone - see this
module's own callers) - both functions require a real reviewer note."""
from __future__ import annotations

import datetime as dt

from app.db.models import LocalPlanSite


def confirm_site_match(session, allocation: LocalPlanSite, confirmed_by: str, note: str) -> None:
    """Marks allocation.matched_site_id as a human-confirmed relationship.
    Requires a non-empty note (the supporting evidence - shared distinctive
    name, matching address/location, corroborating application detail -
    per the Part 11 review principle: "generic place-name similarity alone
    is insufficient"). Leaves matched_site_id/match_confidence exactly as
    they were - this action only changes review_status and adds
    provenance, never the relationship itself."""
    if allocation.matched_site_id is None:
        raise ValueError(f"Allocation {allocation.id} has no matched_site_id - nothing to confirm.")
    if not note or not note.strip():
        raise ValueError("confirm_site_match requires a non-empty note explaining the supporting evidence.")
    allocation.review_status = "confirmed"
    allocation.confirmed_by = confirmed_by
    allocation.confirmed_at = dt.datetime.now(dt.timezone.utc)
    allocation.match_review_note = note.strip()
    session.commit()


def reject_site_match(session, allocation: LocalPlanSite, confirmed_by: str, reason: str) -> None:
    """Records that a proposed Site match was reviewed and found NOT to
    genuinely relate to this allocation. Unlike VisualEvidence's
    reject_image (which keeps a rejected image's site_id/application_id,
    since the underlying relationship it's evidence FOR is still real - a
    rejected image just isn't good evidence), rejecting an allocation-Site
    match means the relationship itself is false: this allocation is NOT
    that Site. matched_site_id and match_confidence are therefore cleared
    (returning the allocation to a genuinely unmatched state), and
    match_review_note records which candidate Site was rejected and why,
    so the decision stays auditable even though the pointer itself is
    gone. review_status stays "rejected" (not reset to null/auto_applied)
    so a future matching pass can see this allocation already had its
    obvious candidate looked at and declined, distinct from one nobody has
    reviewed yet."""
    if allocation.matched_site_id is None:
        raise ValueError(f"Allocation {allocation.id} has no matched_site_id - nothing to reject.")
    if not reason or not reason.strip():
        raise ValueError("reject_site_match requires a non-empty reason.")
    rejected_site_id = allocation.matched_site_id
    allocation.matched_site_id = None
    allocation.match_confidence = None
    allocation.review_status = "rejected"
    allocation.confirmed_by = confirmed_by
    allocation.confirmed_at = dt.datetime.now(dt.timezone.utc)
    allocation.match_review_note = f"Rejected candidate Site {rejected_site_id}: {reason.strip()}"
    session.commit()
