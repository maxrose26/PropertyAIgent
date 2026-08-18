"""Stage 2E.1 ("Allocation<->Site Relationship Matcher Integrity Fix") -
controlled cleanup PLAN preparation (Section 15/16). This module ONLY
computes what a future, separately-approved, explicitly write-gated
script would do to AllocationSiteRelationship.review_status - it makes NO
database writes itself anywhere. Every candidate is identified
SEMANTICALLY by (allocation_id, site_id), never by a hardcoded
relationship row id (Section 15/24: "do not blindly target database
IDs"), and must be revalidated live via revalidate_before_write
immediately before any future write - a plan computed once is never
assumed to still be accurate later (Section 16: "immediate revalidation
+ idempotent write behaviour").

REJECT vs NEEDS_CONFIRMATION (Section 13's own explicit warning: "this
task must not confuse 'previously confirmed' with 'independently
evidence-verified'"): a relationship the corrected matcher no longer
finds auto-eligible for is ONLY ever a reject_candidate when the caller
independently supplies it as a confirmed false positive (e.g. Stage 2E's
own human-verified King Street/Rectory Lane findings, passed in via
confirmed_false_positive_pairs) - every OTHER relationship that merely
lost auto-eligibility is a needs_confirmation_candidate instead, never
silently rejected on the matcher's word alone.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AllocationSiteRelationship, LocalPlanSite
from app.policy.allocation_document_evidence import (
    EXPLICIT_REFERENCE,
    STRONG_CONTEXTUAL_REFERENCE,
    find_document_evidence_for_allocation,
)

_AUTO_ELIGIBLE_CATEGORIES = (EXPLICIT_REFERENCE, STRONG_CONTEXTUAL_REFERENCE)
_CATEGORY_STRENGTH = {"WEAK_REFERENCE": 0, "NAME_AND_POLICY_CONTEXT": 1, STRONG_CONTEXTUAL_REFERENCE: 2, EXPLICIT_REFERENCE: 3}


def _best_category_for_site(hits, site_id: int) -> str | None:
    site_hits = [h for h in hits if h.site_id == site_id]
    if not site_hits:
        return None
    return max(site_hits, key=lambda h: _CATEGORY_STRENGTH.get(h.category, 0)).category


@dataclass(frozen=True)
class CleanupTarget:
    allocation_id: int
    site_id: int
    relationship_id: int
    previous_evidence_category: str | None
    new_evidence_category: str | None
    reason: str


@dataclass(frozen=True)
class CleanupPlan:
    reject_candidates: list[CleanupTarget] = field(default_factory=list)
    needs_confirmation_candidates: list[CleanupTarget] = field(default_factory=list)
    unchanged: list[CleanupTarget] = field(default_factory=list)


def build_cleanup_plan(
    session: Session, *, confirmed_false_positive_pairs: set[tuple[int, int]] | None = None,
) -> CleanupPlan:
    """READ ONLY - re-evaluates every currently-accepted
    (review_status != "rejected") AllocationSiteRelationship against the
    CORRECTED matcher and classifies each into reject / needs_confirmation
    / unchanged. Never mutates anything."""
    confirmed_false_positive_pairs = confirmed_false_positive_pairs or set()
    relationships = list(session.execute(
        select(AllocationSiteRelationship).where(AllocationSiteRelationship.review_status != "rejected")
    ).scalars().all())

    by_allocation: dict[int, list[AllocationSiteRelationship]] = {}
    for rel in relationships:
        by_allocation.setdefault(rel.allocation_id, []).append(rel)

    plan = CleanupPlan()
    evidence_cache: dict[int, tuple[list, list]] = {}

    for allocation_id, rels in by_allocation.items():
        allocation = session.get(LocalPlanSite, allocation_id)
        if allocation.id not in evidence_cache:
            evidence_cache[allocation.id] = find_document_evidence_for_allocation(session, allocation)
        positive_hits, _ = evidence_cache[allocation.id]

        for rel in rels:
            new_category = _best_category_for_site(positive_hits, rel.site_id)
            still_eligible = new_category in _AUTO_ELIGIBLE_CATEGORIES
            pair = (allocation_id, rel.site_id)

            if still_eligible:
                plan.unchanged.append(CleanupTarget(
                    allocation_id=allocation_id, site_id=rel.site_id, relationship_id=rel.id,
                    previous_evidence_category=rel.evidence_category, new_evidence_category=new_category,
                    reason="Still auto-eligible under the corrected matcher.",
                ))
                continue

            target = CleanupTarget(
                allocation_id=allocation_id, site_id=rel.site_id, relationship_id=rel.id,
                previous_evidence_category=rel.evidence_category, new_evidence_category=new_category,
                reason=(
                    "No longer auto-eligible under the corrected matcher "
                    f"(best remaining category: {new_category})."
                ),
            )
            if pair in confirmed_false_positive_pairs:
                plan.reject_candidates.append(target)
            else:
                plan.needs_confirmation_candidates.append(target)

    return plan


@dataclass(frozen=True)
class RevalidationResult:
    allocation_id: int
    site_id: int
    relationship_exists: bool
    current_review_status: str | None
    still_matches_plan: bool
    reason: str


def revalidate_before_write(
    session: Session, allocation_id: int, site_id: int, *, expected_action: str,
) -> RevalidationResult:
    """Section 15/16 - "identify cleanup targets semantically by
    allocation_id + site_id, and revalidate the relationship immediately
    before any future write". Re-fetches the CURRENT relationship row live
    (never trusts a snapshot computed earlier by build_cleanup_plan) and
    re-runs the corrected matcher fresh against CURRENT documents, so a
    plan is never blindly replayed against data that has since changed -
    a relationship a human already acted on (confirmed/rejected), or new
    document evidence that has since appeared, both correctly abort the
    proposed write rather than silently overriding it. NEVER writes
    anything itself - `expected_action` is "reject" or
    "needs_confirmation", the write this check would gate, not an action
    this function performs."""
    if expected_action not in ("reject", "needs_confirmation"):
        raise ValueError(f"expected_action must be 'reject' or 'needs_confirmation', got {expected_action!r}")

    rel = session.execute(
        select(AllocationSiteRelationship).where(
            AllocationSiteRelationship.allocation_id == allocation_id,
            AllocationSiteRelationship.site_id == site_id,
        )
    ).scalar_one_or_none()
    if rel is None:
        return RevalidationResult(
            allocation_id=allocation_id, site_id=site_id, relationship_exists=False,
            current_review_status=None, still_matches_plan=False,
            reason="Relationship no longer exists - nothing to write.",
        )
    if rel.review_status in ("rejected", "confirmed"):
        return RevalidationResult(
            allocation_id=allocation_id, site_id=site_id, relationship_exists=True,
            current_review_status=rel.review_status, still_matches_plan=False,
            reason=(
                f"Relationship already has review_status={rel.review_status!r} - a human has since acted on "
                f"it; the plan's proposed {expected_action!r} must never overwrite that decision."
            ),
        )

    allocation = session.get(LocalPlanSite, allocation_id)
    positive_hits, _ = find_document_evidence_for_allocation(session, allocation)
    new_category = _best_category_for_site(positive_hits, site_id)
    still_eligible = new_category in _AUTO_ELIGIBLE_CATEGORIES

    if expected_action == "reject" and still_eligible:
        return RevalidationResult(
            allocation_id=allocation_id, site_id=site_id, relationship_exists=True,
            current_review_status=rel.review_status, still_matches_plan=False,
            reason=f"New document evidence now makes this relationship auto-eligible ({new_category}) - no longer a reject candidate.",
        )
    if expected_action == "needs_confirmation" and not still_eligible:
        return RevalidationResult(
            allocation_id=allocation_id, site_id=site_id, relationship_exists=True,
            current_review_status=rel.review_status, still_matches_plan=True,
            reason="Still not auto-eligible under the corrected matcher - needs_confirmation still applies.",
        )
    if expected_action == "needs_confirmation" and still_eligible:
        return RevalidationResult(
            allocation_id=allocation_id, site_id=site_id, relationship_exists=True,
            current_review_status=rel.review_status, still_matches_plan=False,
            reason=f"New document evidence now makes this relationship auto-eligible ({new_category}) - no longer a needs_confirmation candidate.",
        )

    return RevalidationResult(
        allocation_id=allocation_id, site_id=site_id, relationship_exists=True,
        current_review_status=rel.review_status, still_matches_plan=True,
        reason=f"Revalidated: matches the plan's proposed {expected_action!r}.",
    )
