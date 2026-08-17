"""GM Allocation <-> Site many-to-many relationship foundation (Stage 2D).

Builds and (behind an explicit confirmation gate) writes
app.db.models.AllocationSiteRelationship rows - see that class's own
docstring for the full architectural rationale (why a new table, why it's
compatible with the existing matched_site_id, why relationship_type is
currently always "unknown_scope"). This module never writes anything
implicitly; every write path here is dry-run by default and requires an
explicit call to run_controlled_relationship_write().

TWO SOURCES of relationships, combined into one dry-run report:

1. LEGACY BACKFILL - every existing LocalPlanSite.matched_site_id (9 in
   production today) becomes exactly one AllocationSiteRelationship row,
   UNCHANGED in meaning ("do not reinterpret them" - Stage 2D Section 6).
   matched_site_id itself is never touched by this path.

2. STAGE 2C DOCUMENT EVIDENCE - reuses app.policy.allocation_document_evidence's
   OWN dry-run output (never re-derives or re-searches documents itself).
   Only three recommended_outcome values are eligible for automatic
   relationship creation, per the Product Owner's explicit instruction
   that fuzzy matching alone is no longer authoritative evidence:

     DOCUMENT_CONFIRMED_SITE            - one relationship, the confirmed Site
     FUZZY_SUPPORTED_BY_DOCUMENT        - one relationship, the document-agreed Site
     MULTIPLE_DOCUMENT_SUPPORTED_SITES  - one relationship PER strongly-evidenced
                                           Site (never forced to a single winner)

   Every other outcome is explicitly EXCLUDED from automatic relationship
   creation and reported as such, never silently dropped:
     - WEAK_REFERENCE/NAME_AND_POLICY_CONTEXT-only hits (folded into
       DOCUMENT_REVIEW_REQUIRED or NO_DOCUMENT_EVIDENCE by Stage 2C's own
       classification) - insufficient evidence.
     - DOCUMENT_CONTRADICTS_FUZZY - a Stage 2A fuzzy candidate document
       evidence actively disagrees with; never persisted.
     - DOCUMENT_CONFIRMED_APPLICATION_ONLY - real evidence, but for an
       Application with no linked Site at all (Dairyground Farm is the
       one production example) - creating a Site relationship here would
       require either fabricating a Site or misusing this table to point
       at a nonexistent one; instead this is reported as a separate
       APPLICATION-ONLY EVIDENCE GAP, a follow-up item for
       Application<->Site linking, never smuggled into the Site
       relationship set (Stage 2D Section 12).
     - Fuzzy-only candidates (HIGH_CONFIDENCE_CANDIDATE/REVIEW_CANDIDATE
       with NO_DOCUMENT_EVIDENCE) - score >= 80 alone is no longer
       sufficient (this is the explicit Product Owner reversal this stage
       implements) - these remain review suggestions only, never
       auto-linked. Includes the three examples the Product Owner named
       directly: John Street/Hazel Grove, Land west of Skerton Road,
       Ashton Road/Woodhouses - all three have NO_DOCUMENT_EVIDENCE and
       are therefore excluded here exactly like every other unsupported
       fuzzy candidate, not special-cased.

matched_site_id CONVENIENCE-POINTER BEHAVIOUR (Stage 2D Section 5): when a
SINGLE new relationship is created for an allocation whose matched_site_id
is currently NULL, the write path also sets matched_site_id/match_confidence
as a convenience mirror - purely so existing code that only ever reads
matched_site_id still benefits from Stage 2D's findings. This NEVER
happens for a MULTIPLE_DOCUMENT_SUPPORTED_SITES allocation (setting one
scalar "primary" Site there would be exactly the "pick a winner" bias
Stage 2D exists to eliminate - Section 8's explicit instruction), and
NEVER overwrites an already-set matched_site_id (fail-closed, mirroring
Stage 2B's own drift-check discipline).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AllocationSiteRelationship, LocalPlanSite
from app.policy.allocation_document_evidence import (
    DOCUMENT_CONFIRMED_APPLICATION_ONLY,
    DOCUMENT_CONFIRMED_SITE,
    DOCUMENT_CONTRADICTS_FUZZY,
    FUZZY_SUPPORTED_BY_DOCUMENT,
    MULTIPLE_DOCUMENT_SUPPORTED_SITES,
    AllocationEvidenceResult,
    evaluate_allocation_document_evidence,
)
from app.policy.allocation_site_dry_run_matching import (
    AMBIGUOUS,
    HIGH_CONFIDENCE_CANDIDATE,
    REVIEW_CANDIDATE,
    run_dry_run_matching,
)

# --- evidence_basis vocabulary -----------------------------------------

EVIDENCE_BASIS_LEGACY_BACKFILL = "legacy_matched_site_id_backfill"
EVIDENCE_BASIS_DOCUMENT_CONFIRMED_SITE = "document_confirmed_site"
EVIDENCE_BASIS_FUZZY_SUPPORTED_BY_DOCUMENT = "fuzzy_supported_by_document"
EVIDENCE_BASIS_MULTIPLE_DOCUMENT_SUPPORTED_SITES = "multiple_document_supported_sites"

# The ONLY Stage 2C outcomes eligible for automatic relationship creation.
AUTO_ELIGIBLE_OUTCOMES = {DOCUMENT_CONFIRMED_SITE, FUZZY_SUPPORTED_BY_DOCUMENT, MULTIPLE_DOCUMENT_SUPPORTED_SITES}

_OUTCOME_TO_EVIDENCE_BASIS = {
    DOCUMENT_CONFIRMED_SITE: EVIDENCE_BASIS_DOCUMENT_CONFIRMED_SITE,
    FUZZY_SUPPORTED_BY_DOCUMENT: EVIDENCE_BASIS_FUZZY_SUPPORTED_BY_DOCUMENT,
    MULTIPLE_DOCUMENT_SUPPORTED_SITES: EVIDENCE_BASIS_MULTIPLE_DOCUMENT_SUPPORTED_SITES,
}


@dataclass
class PlannedRelationship:
    allocation_id: int
    site_id: int
    evidence_basis: str
    relationship_type: str = "unknown_scope"
    confidence: float | None = None
    evidence_category: str | None = None
    evidence_document_id: int | None = None
    evidence_application_id: int | None = None
    evidence_snippet: str | None = None
    review_status: str = "auto_applied"


@dataclass
class RelationshipDryRunReport:
    legacy_backfill: list[PlannedRelationship] = field(default_factory=list)
    new_document_relationships: list[PlannedRelationship] = field(default_factory=list)
    already_present: list[tuple[int, int]] = field(default_factory=list)  # (allocation_id, site_id) pairs
    fuzzy_only_excluded: list[int] = field(default_factory=list)  # allocation_ids
    contradicted_excluded: list[int] = field(default_factory=list)
    application_only_evidence: list[dict] = field(default_factory=list)  # {allocation_id, application_id, ...}
    review_required_excluded: list[int] = field(default_factory=list)


def plan_legacy_backfill(session: Session) -> list[PlannedRelationship]:
    """One PlannedRelationship per existing matched_site_id - UNCHANGED in
    meaning (Stage 2D Section 6: "do not reinterpret them"). READ ONLY."""
    allocations = session.execute(
        select(LocalPlanSite).where(LocalPlanSite.matched_site_id.is_not(None))
    ).scalars().all()
    return [
        PlannedRelationship(
            allocation_id=a.id, site_id=a.matched_site_id,
            evidence_basis=EVIDENCE_BASIS_LEGACY_BACKFILL,
            confidence=a.match_confidence,
            review_status=a.review_status,
        )
        for a in allocations
    ]


def _best_hit_for_site(hits: list, site_id: int):
    """Among an evidence result's strong hits naming this site_id, picks
    the one with the highest document-type weight (Stage 2C's own
    tie-breaking rule - see that module's docstring) as the relationship's
    provenance - never a blend of several hits, one clear source per row."""
    candidates = [h for h in hits if h.site_id == site_id]
    return max(candidates, key=lambda h: h.weight)


def plan_document_evidence_relationships(
    evidence_results: list[AllocationEvidenceResult],
) -> tuple[list[PlannedRelationship], dict]:
    """Turns Stage 2C's own dry-run output into planned relationships,
    strictly limited to AUTO_ELIGIBLE_OUTCOMES. READ ONLY - never touches
    the database. Returns (planned, excluded_report) where excluded_report
    has keys: fuzzy_only, contradicted, application_only, review_required."""
    planned: list[PlannedRelationship] = []
    excluded = {"fuzzy_only": [], "contradicted": [], "application_only": [], "review_required": []}

    for result in evidence_results:
        if result.recommended_outcome in AUTO_ELIGIBLE_OUTCOMES:
            strong_hits = [
                h for h in result.positive_hits
                if h.category in ("EXPLICIT_REFERENCE", "STRONG_CONTEXTUAL_REFERENCE") and h.site_id is not None
            ]
            site_ids = sorted({h.site_id for h in strong_hits})
            for site_id in site_ids:
                best = _best_hit_for_site(strong_hits, site_id)
                planned.append(PlannedRelationship(
                    allocation_id=result.allocation_id, site_id=site_id,
                    evidence_basis=_OUTCOME_TO_EVIDENCE_BASIS[result.recommended_outcome],
                    # Stage 2C's DocumentEvidenceHit carries no 0-100 score
                    # (its evidence CATEGORY - EXPLICIT_REFERENCE etc. - IS
                    # its confidence signal) - left null rather than
                    # inventing a number Stage 2C never computed.
                    confidence=None,
                    evidence_category=best.category,
                    evidence_document_id=best.document_id,
                    evidence_application_id=best.application_id,
                    evidence_snippet=best.snippet,
                ))
        elif result.recommended_outcome == DOCUMENT_CONTRADICTS_FUZZY:
            excluded["contradicted"].append(result.allocation_id)
        elif result.recommended_outcome == DOCUMENT_CONFIRMED_APPLICATION_ONLY:
            unlinked = [h for h in result.positive_hits if h.site_id is None]
            evidence = unlinked[0] if unlinked else None
            excluded["application_only"].append({
                "allocation_id": result.allocation_id,
                "council": result.council,
                "policy_reference": result.policy_reference,
                "allocation_name": result.allocation_name,
                "application_id": evidence.application_id if evidence else None,
                "application_reference": evidence.application_reference if evidence else None,
                "evidence_snippet": evidence.snippet if evidence else None,
            })
        elif result.stage2a_classification in (HIGH_CONFIDENCE_CANDIDATE, REVIEW_CANDIDATE, AMBIGUOUS) and not result.positive_hits:
            excluded["fuzzy_only"].append(result.allocation_id)
        else:
            excluded["review_required"].append(result.allocation_id)

    return planned, excluded


def fetch_accepted_relationships(session: Session) -> list[AllocationSiteRelationship]:
    """Every currently-ACCEPTED allocation<->Site relationship - the
    authoritative set, for the review UI's "ACCEPTED RELATED SITES"
    section (Stage 2D Section 13). Read-only. Ordered by allocation_id so
    a caller can group consecutive rows per allocation without a second
    pass."""
    return list(
        session.execute(select(AllocationSiteRelationship).order_by(AllocationSiteRelationship.allocation_id))
        .scalars().all()
    )


def run_relationship_dry_run(session: Session) -> RelationshipDryRunReport:
    """Combines legacy backfill + Stage 2C document evidence into one
    report, checked against the CURRENT AllocationSiteRelationship table
    for idempotency. READ ONLY throughout - zero mutations."""
    legacy_planned = plan_legacy_backfill(session)

    stage2a = run_dry_run_matching(session)
    stage2a_by_id = {r.allocation_id: r for r in stage2a["results"]}
    all_allocations = session.execute(select(LocalPlanSite).where(LocalPlanSite.matched_site_id.is_(None))).scalars().all()
    from app.policy.allocation_document_evidence import evaluate_allocation_document_evidence
    evidence_results = [
        evaluate_allocation_document_evidence(session, a, stage2a_by_id.get(a.id))
        for a in all_allocations
    ]
    document_planned, excluded = plan_document_evidence_relationships(evidence_results)

    existing_pairs = {
        (r.allocation_id, r.site_id)
        for r in session.execute(select(AllocationSiteRelationship)).scalars().all()
    }

    report = RelationshipDryRunReport()
    for planned in legacy_planned + document_planned:
        pair = (planned.allocation_id, planned.site_id)
        if pair in existing_pairs:
            report.already_present.append(pair)
        elif planned.evidence_basis == EVIDENCE_BASIS_LEGACY_BACKFILL:
            report.legacy_backfill.append(planned)
        else:
            report.new_document_relationships.append(planned)

    report.fuzzy_only_excluded = excluded["fuzzy_only"]
    report.contradicted_excluded = excluded["contradicted"]
    report.application_only_evidence = excluded["application_only"]
    report.review_required_excluded = excluded["review_required"]
    return report


def create_relationship_if_absent(
    session: Session, *, allocation_id: int, site_id: int, evidence_basis: str,
    relationship_type: str = "unknown_scope", confidence: float | None = None,
    evidence_category: str | None = None, evidence_document_id: int | None = None,
    evidence_application_id: int | None = None, evidence_snippet: str | None = None,
    review_status: str = "auto_applied",
) -> AllocationSiteRelationship | None:
    """Stage 3B amendment ("reuse the existing Stage 2D relationship
    persistence architecture... do not create a second direct-write
    path") - the ONE place a new AllocationSiteRelationship row is ever
    constructed from evidence, shared by run_controlled_relationship_
    write's own batch loops below (Stage 2D's historical/periodic path)
    and app.policy.allocation_evidence_scan's per-document forward
    auto-create path (Stage 3B) - one persistence implementation to keep
    idempotent and correct, never two independently-maintained ones.

    LIVE re-check immediately before insert, not just a reliance on an
    earlier-computed dry-run snapshot - fail-closed against a duplicate
    a DIFFERENT document/call already created earlier in the SAME batch
    (Stage 3B's forward scan calls this once per document, so two
    documents in one run naming the same new Site would otherwise both
    attempt the same pair). Returns None (a pure no-op, never an error)
    if the (allocation_id, site_id) pair already exists - never
    duplicates, never overwrites, never touches any field of an existing
    row (so stronger/human-confirmed provenance already on file is
    always preserved untouched, per Stage 3B's own amendment Section 3)."""
    existing = session.execute(
        select(AllocationSiteRelationship).where(
            AllocationSiteRelationship.allocation_id == allocation_id,
            AllocationSiteRelationship.site_id == site_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return None
    rel = AllocationSiteRelationship(
        allocation_id=allocation_id, site_id=site_id, evidence_basis=evidence_basis,
        relationship_type=relationship_type, confidence=confidence, evidence_category=evidence_category,
        evidence_document_id=evidence_document_id, evidence_application_id=evidence_application_id,
        evidence_snippet=evidence_snippet, review_status=review_status,
    )
    session.add(rel)
    session.flush()  # populate rel.id immediately - callers (e.g. Stage 3B's own report/logging) rely on it
    return rel


def run_controlled_relationship_write(session: Session) -> dict:
    """PRODUCTION WRITE MODE. Only called with explicit CLI confirmation.

    Writes AllocationSiteRelationship rows for the dry-run's legacy_backfill
    + new_document_relationships sets ONLY - the excluded sets are never
    written under any circumstances. Idempotent: re-checks the unique
    (allocation_id, site_id) pair live immediately before each insert,
    skipping (not erroring) if it already exists - safe to run any number
    of times, matching this codebase's own established backfill-script
    convention (see scripts/migrate_joint_plan_support.py).

    Also sets LocalPlanSite.matched_site_id/match_confidence as a
    convenience pointer, but ONLY when: the allocation currently has
    matched_site_id IS NULL (fail-closed - never overwrites), AND exactly
    one NEW relationship is being created for that allocation in this run
    (never for a multi-Site allocation - see module docstring)."""
    report = run_relationship_dry_run(session)

    created_legacy = 0
    created_document = 0
    matched_site_id_set = []

    for planned in report.legacy_backfill:
        created = create_relationship_if_absent(
            session, allocation_id=planned.allocation_id, site_id=planned.site_id,
            evidence_basis=planned.evidence_basis, relationship_type=planned.relationship_type,
            confidence=planned.confidence, review_status=planned.review_status,
        )
        if created is not None:
            created_legacy += 1

    # Group new document relationships per allocation to detect the
    # "exactly one new relationship" convenience-pointer condition.
    by_allocation: dict[int, list[PlannedRelationship]] = {}
    for planned in report.new_document_relationships:
        by_allocation.setdefault(planned.allocation_id, []).append(planned)

    for allocation_id, planned_list in by_allocation.items():
        for planned in planned_list:
            created = create_relationship_if_absent(
                session, allocation_id=planned.allocation_id, site_id=planned.site_id,
                evidence_basis=planned.evidence_basis, relationship_type=planned.relationship_type,
                confidence=planned.confidence, evidence_category=planned.evidence_category,
                evidence_document_id=planned.evidence_document_id,
                evidence_application_id=planned.evidence_application_id,
                evidence_snippet=planned.evidence_snippet,
            )
            if created is not None:
                created_document += 1

        if len(planned_list) == 1:
            allocation = session.get(LocalPlanSite, allocation_id)
            if allocation is not None and allocation.matched_site_id is None:
                allocation.matched_site_id = planned_list[0].site_id
                allocation.match_confidence = planned_list[0].confidence
                matched_site_id_set.append(allocation_id)

    session.commit()

    return {
        "created_legacy_backfill": created_legacy,
        "created_document_relationships": created_document,
        "already_present_skipped": len(report.already_present),
        "matched_site_id_convenience_pointer_set": matched_site_id_set,
    }
