"""Forward Allocation-Reference Evidence Scan (Stage 3B).

PRODUCT OBJECTIVE: keep AllocationSiteRelationship evidence current as new
planning documents arrive, without a human having to remember to re-run
Stage 2C/2D's historical batch CLI. This is a KEEP-EVIDENCE-CURRENT
mechanism, not a second matcher, not ownership intelligence, not an AI
agent.

REUSE, NOT A NEW MATCHER: every regex/proximity/classification rule comes
from app.policy.allocation_document_evidence.find_allocation_evidence_for_
document (the Stage 3A "forward direction" primitive, itself built
entirely from Stage 2C's own reused private helpers). This module adds
ONLY orchestration - which documents to look at, how to batch allocations/
relationships, and what to do with a hit - never a second evidence
vocabulary or a second regex.

WHY THIS DOES NOT NEED TO WRITE AllocationSiteRelationship ROWS ITSELF:
app.policy.allocation_site_relationships.run_relationship_dry_run/
run_controlled_relationship_write already RE-SCAN every unmatched
allocation's document evidence FRESH, from the live extracted_text, every
single time they run - they do not read a cache this module would need to
populate. So the moment a new document's text is scanned into the
database, the EXISTING historical/batch mechanism already sees it on its
next invocation, with zero help needed from this module. This module's
job is therefore narrower and different: (1) give an operator/report
visibility into what NEW evidence has appeared without needing to run the
full batch CLI just to find out, and (2) catch the one case the existing
batch mechanism structurally CANNOT see - new evidence that CONTRADICTS
an allocation that ALREADY HAS an accepted relationship (Stage 2D's dry-
run functions only ever evaluate allocations with matched_site_id IS NULL
for document evidence; once a relationship exists, nothing re-checks it
against new incoming documents). See flag_contradicted_relationships
below for how that gap is closed.

WRITES THIS MODULE DOES MAKE (both narrow, both reversible, neither
"creates a relationship"):
  1. Document.allocation_evidence_scanned_at - bookkeeping only, so the
     same document is never rescanned (Section 3/10 idempotency).
  2. AllocationSiteRelationship.review_status flipped from its current
     value to "needs_confirmation" ONLY when new evidence explicitly
     contradicts that specific accepted relationship (Section 8: "raise a
     review event, do not create silent relationship reversals") - never
     deletes the row, never touches evidence_basis/site_id/confidence/
     evidence_snippet, so the original accepted evidence remains fully
     intact for a human to weigh against the new contradicting text. This
     reuses AllocationSiteRelationship.review_status's own EXISTING
     bounded vocabulary (auto_applied | needs_confirmation | confirmed |
     rejected) - the exact field Stage 2D's own model docstring already
     reserved for "whatever future review UI eventually acts on a
     specific relationship row". No new schema for this case.
     Precedent for an unguarded automatic "flag for review" write:
     app.pipeline.material_change already sets Application.evidence_
     refresh_required = True with zero human confirmation - only
     ACCEPTING new evidence is confirm-phrase-gated in this codebase,
     never flagging existing state for re-review.

WHAT THIS MODULE NEVER DOES:
  - create a new AllocationSiteRelationship row (exclusively app.policy.
    allocation_site_relationships.run_controlled_relationship_write's
    job, via its own --execute --confirm-gated CLI);
  - delete or silently reverse an accepted relationship;
  - call OpenAI or any external service;
  - rescan a document that already has allocation_evidence_scanned_at set;
  - rescan every historical document on a normal run (see select_
    unscanned_documents - strictly WHERE allocation_evidence_scanned_at
    IS NULL, an ever-shrinking set as normal operation proceeds. Stage 2C's
    own CLI, scripts/dry_run_gm_allocation_site_relationships.py, remains
    the unmodified historical/manual full-corpus mechanism.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AllocationSiteRelationship, Application, Document, LocalPlanSite, utcnow
from app.policy.allocation_document_evidence import (
    EXPLICIT_REFERENCE,
    STRONG_CONTEXTUAL_REFERENCE,
    find_allocation_evidence_for_document,
)

# Bounded per-run limit (Section 11: "do not make routine ingestion
# significantly slower") - same established pattern as app.pipeline.
# evidence_refresh.EVIDENCE_REFRESH_RUN_LIMIT. A normal run only ever has
# a handful of newly-extracted documents per council per day (Daily
# Discovery's own typical volume), so this bound is a safety ceiling, not
# an expected steady-state limit.
ALLOCATION_EVIDENCE_SCAN_RUN_LIMIT = 200

# Strong evidence categories (Stage 2C's own vocabulary) eligible to be
# reported as a new relationship candidate - mirrors app.policy.
# allocation_site_relationships.plan_document_evidence_relationships'
# own strong_hits filter exactly (EXPLICIT_REFERENCE / STRONG_CONTEXTUAL_
# REFERENCE), so this module's "new candidate" count always agrees with
# what the existing controlled-write CLI would actually create.
_STRONG_CATEGORIES = (EXPLICIT_REFERENCE, STRONG_CONTEXTUAL_REFERENCE)


@dataclass
class NewCandidateHit:
    allocation_id: int
    allocation_reference: str | None
    allocation_name: str
    site_id: int
    document_id: int
    application_id: int
    application_reference: str
    category: str
    snippet: str


@dataclass
class WeakEvidenceHit:
    allocation_id: int
    allocation_reference: str | None
    allocation_name: str
    document_id: int
    application_id: int
    application_reference: str
    category: str
    snippet: str


@dataclass
class ApplicationOnlyHit:
    allocation_id: int
    allocation_reference: str | None
    allocation_name: str
    document_id: int
    application_id: int
    application_reference: str
    category: str
    snippet: str


@dataclass
class ContradictionFlag:
    allocation_id: int
    site_id: int
    relationship_id: int
    document_id: int
    application_id: int
    application_reference: str
    snippet: str
    previous_review_status: str


@dataclass
class AllocationEvidenceScanReport:
    documents_scanned: int = 0
    documents_failed: int = 0
    new_strong_candidates: list[NewCandidateHit] = field(default_factory=list)
    weak_evidence: list[WeakEvidenceHit] = field(default_factory=list)
    application_only_evidence: list[ApplicationOnlyHit] = field(default_factory=list)
    contradictions_flagged: list[ContradictionFlag] = field(default_factory=list)


def select_unscanned_documents(session: Session, council_code: str, *, limit: int = ALLOCATION_EVIDENCE_SCAN_RUN_LIMIT) -> list[tuple[Document, Application]]:
    """Batched, single query (Section 11: avoid N+1) - every Document with
    usable extracted text, belonging to an Application with a known
    council, not yet allocation-scanned. Bounded per Section 11's own
    "do not slow down routine ingestion" instruction - a normal run
    processes the oldest unscanned documents first (id order), leaving
    any excess for the next run rather than blocking on a large one-off
    backlog."""
    rows = session.execute(
        select(Document, Application)
        .join(Application, Document.application_id == Application.id)
        .where(
            Application.council_code == council_code,
            Document.text_extracted.is_(True),
            Document.extracted_text.is_not(None),
            Document.allocation_evidence_scanned_at.is_(None),
        )
        .order_by(Document.id)
        .limit(limit)
    ).all()
    return [(doc, app) for doc, app in rows]


def _existing_relationships_by_allocation(
    session: Session, allocation_ids: list[int],
) -> dict[int, list[AllocationSiteRelationship]]:
    if not allocation_ids:
        return {}
    rows = session.execute(
        select(AllocationSiteRelationship).where(AllocationSiteRelationship.allocation_id.in_(allocation_ids))
    ).scalars().all()
    result: dict[int, list[AllocationSiteRelationship]] = {aid: [] for aid in allocation_ids}
    for rel in rows:
        result.setdefault(rel.allocation_id, []).append(rel)
    return result


def _snippet_for_site(hits, site_id: int | None) -> str:
    for h in hits:
        if h.site_id == site_id:
            return h.snippet
    return hits[0].snippet if hits else ""


def _process_one_document(
    document: Document, application: Application, allocations: list[LocalPlanSite],
    relationships_by_allocation: dict[int, list[AllocationSiteRelationship]],
    report: AllocationEvidenceScanReport,
) -> None:
    """Pure per-document classification against already-loaded allocations/
    relationships - no query of its own, so this can be called for every
    document in a batch without adding N+1 queries. Raises on a genuine
    processing error - the caller is responsible for isolating that
    failure (Section 12)."""
    results = find_allocation_evidence_for_document(document, application, allocations)

    allocations_by_id = {a.id: a for a in allocations}

    for allocation_id, (positive_hits, contradictory_hits) in results.items():
        allocation = allocations_by_id[allocation_id]
        existing = relationships_by_allocation.get(allocation_id, [])
        existing_site_ids = {rel.site_id for rel in existing}

        # --- Section 8: contradiction against an ALREADY-ACCEPTED relationship ---
        # This is the one case the existing Stage 2D dry-run/write mechanism
        # structurally cannot see on its own (see module docstring) - a
        # CONTRADICTORY_REFERENCE hit naming a Site this allocation already
        # has an accepted relationship with.
        for hit in contradictory_hits:
            if hit.site_id is None or hit.site_id not in existing_site_ids:
                continue
            for rel in existing:
                if rel.site_id != hit.site_id:
                    continue
                if rel.review_status == "needs_confirmation":
                    continue  # already flagged - idempotent, no duplicate flag/log
                previous_status = rel.review_status
                rel.review_status = "needs_confirmation"
                report.contradictions_flagged.append(ContradictionFlag(
                    allocation_id=allocation_id, site_id=hit.site_id, relationship_id=rel.id,
                    document_id=document.id, application_id=application.id,
                    application_reference=application.reference, snippet=hit.snippet,
                    previous_review_status=previous_status,
                ))

        strong_hits = [h for h in positive_hits if h.category in _STRONG_CATEGORIES]
        strong_linked = [h for h in strong_hits if h.site_id is not None]
        strong_unlinked = [h for h in strong_hits if h.site_id is None]
        weak_hits = [h for h in positive_hits if h.category not in _STRONG_CATEGORIES]

        # --- Section 6: strong evidence for a Site NOT already accepted ---
        # Reported only - never persisted here (see module docstring).
        new_strong_site_ids = {h.site_id for h in strong_linked} - existing_site_ids
        for site_id in new_strong_site_ids:
            best = _best_strong_hit(strong_linked, site_id)
            report.new_strong_candidates.append(NewCandidateHit(
                allocation_id=allocation_id, allocation_reference=allocation.policy_reference,
                allocation_name=allocation.site_name, site_id=site_id, document_id=document.id,
                application_id=application.id, application_reference=application.reference,
                category=best.category, snippet=best.snippet,
            ))

        # --- Section 6/7: application-only strong evidence (no linked Site) ---
        for hit in strong_unlinked:
            report.application_only_evidence.append(ApplicationOnlyHit(
                allocation_id=allocation_id, allocation_reference=allocation.policy_reference,
                allocation_name=allocation.site_name, document_id=document.id,
                application_id=application.id, application_reference=application.reference,
                category=hit.category, snippet=hit.snippet,
            ))

        # --- Section 7: weak/contextual evidence - human review only, never auto-write ---
        for hit in weak_hits:
            report.weak_evidence.append(WeakEvidenceHit(
                allocation_id=allocation_id, allocation_reference=allocation.policy_reference,
                allocation_name=allocation.site_name, document_id=document.id,
                application_id=application.id, application_reference=application.reference,
                category=hit.category, snippet=hit.snippet,
            ))


def _best_strong_hit(hits, site_id: int):
    candidates = [h for h in hits if h.site_id == site_id]
    return max(candidates, key=lambda h: h.category == EXPLICIT_REFERENCE)


def scan_council_for_allocation_evidence(
    session: Session, council_code: str, *, limit: int = ALLOCATION_EVIDENCE_SCAN_RUN_LIMIT,
) -> AllocationEvidenceScanReport:
    """The core Stage 3B entrypoint for one council - bounded query budget
    regardless of document count:
      1. Unscanned documents (+ their Application), batched, bounded, one query.
      2. This council's LocalPlanSite allocations, batched, one query.
      3. Existing AllocationSiteRelationship rows for those allocations,
         batched, one query.
    Then iterates documents in memory - no further queries per document.

    FAILURE ISOLATION (Section 12): one document's processing error is
    caught, logged into the report, and never aborts the batch or leaves
    that document falsely marked scanned (so it remains eligible for
    retry next run) - and never corrupts any already-committed row from
    an earlier document in the same batch, since each document's own
    writes (scanned_at + any relationship flips found for IT) are
    committed immediately after that document succeeds, before moving to
    the next.

    IDEMPOTENT: rerunning immediately afterwards finds zero unscanned
    documents (this call marks every successfully-processed one) and
    zero new contradiction flags (a relationship already flagged stays
    flagged, never double-flagged - see _process_one_document)."""
    documents = select_unscanned_documents(session, council_code, limit=limit)
    allocations = list(session.execute(
        select(LocalPlanSite).where(LocalPlanSite.council_code == council_code)
    ).scalars())
    relationships_by_allocation = _existing_relationships_by_allocation(session, [a.id for a in allocations])

    report = AllocationEvidenceScanReport()

    for document, application in documents:
        try:
            _process_one_document(document, application, allocations, relationships_by_allocation, report)
        except Exception as exc:  # noqa: BLE001 - deliberate: one bad document must never abort the batch
            report.documents_failed += 1
            print(f"[allocation-evidence-scan] council={council_code} document_id={document.id} "
                  f"application_id={application.id} FAILED: {exc!r}")
            continue

        document.allocation_evidence_scanned_at = utcnow()
        report.documents_scanned += 1
        session.commit()

    return report
