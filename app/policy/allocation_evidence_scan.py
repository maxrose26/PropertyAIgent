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

FINAL PRE-MERGE AMENDMENT ("Automatic Strong-Evidence Linking"): strong
deterministic evidence (EXPLICIT_REFERENCE / STRONG_CONTEXTUAL_REFERENCE,
naming a Site the linked Application already has - see Section 2's own
"Application must already have a Site" requirement, satisfied structurally
since a hit only ever carries a site_id when application.site_id is
already set) now AUTO-CREATES the AllocationSiteRelationship row, via
app.policy.allocation_site_relationships.create_relationship_if_absent -
the SAME shared, idempotent row-creation helper run_controlled_
relationship_write's own batch loops use. This is deliberately NOT a
second direct-write path: it is the one persistence implementation Stage
2D already owns, called from one more place. evidence_basis is always
EVIDENCE_BASIS_DOCUMENT_CONFIRMED_SITE here, never "fuzzy_supported_by_
document" - this module never cross-checks against a Stage 2A fuzzy
candidate (it evaluates one document against a council's allocations in
isolation), so it never claims agreement with a fuzzy match it hasn't
actually looked at; that stronger claim remains the batch dry-run's own,
which DOES have Stage 2A context.

Weak/contextual evidence, Application-only evidence, and negative/
contradictory evidence are UNCHANGED by this amendment - still never
auto-linked, still only ever reported (see Sections 4/7 below) or, for
contradictions, used to flag an EXISTING relationship for review (never
to create a new one).

WHY THIS MODULE STILL DOES NOT NEED THE FULL BATCH MECHANISM FOR
EVERYTHING: app.policy.allocation_site_relationships.run_relationship_
dry_run/run_controlled_relationship_write still independently RE-SCAN
every unmatched allocation's document evidence FRESH on every invocation
- for an operator who wants the full picture (including FUZZY_SUPPORTED_
BY_DOCUMENT's stronger Stage-2A-cross-checked claim, and MULTIPLE_
DOCUMENT_SUPPORTED_SITES's multi-Site handling), that CLI remains the
authoritative, unmodified mechanism. This module's own auto-create only
ever covers the narrower "no fuzzy cross-check needed" DOCUMENT_
CONFIRMED_SITE case - a real, meaningful subset, not the whole of Stage
2C's evidence vocabulary - kept forward and incremental rather than
requiring the full periodic batch just to catch it.

The one case the existing batch mechanism structurally CANNOT see even
with this amendment: new evidence that CONTRADICTS an allocation that
ALREADY HAS an accepted relationship (Stage 2D's dry-run functions only
ever evaluate allocations with matched_site_id IS NULL for document
evidence; once a relationship exists, nothing re-checks it against new
incoming documents). See the contradiction-handling block in
_process_one_document for how that gap is closed.

WRITES THIS MODULE DOES MAKE:
  1. Document.allocation_evidence_scanned_at - bookkeeping only, so the
     same document is never rescanned (Section 3/10 idempotency).
  2. NEW AllocationSiteRelationship rows for strong DOCUMENT_CONFIRMED_
     SITE-class evidence naming a Site not already related to that
     allocation - via the shared create_relationship_if_absent helper,
     idempotent, never a duplicate pair, never a second write path.
  3. AllocationSiteRelationship.review_status flipped from its current
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

WHAT THIS MODULE NEVER DOES:
  - create an AllocationSiteRelationship from WEAK_REFERENCE, NAME_AND_
    POLICY_CONTEXT, DOCUMENT_REVIEW_REQUIRED, NO_DOCUMENT_EVIDENCE,
    fuzzy-only, Application-only, or negative/contradictory evidence;
  - manufacture a Site for Application-only evidence;
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

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import AllocationSiteRelationship, Application, Document, LocalPlanSite, utcnow
from app.policy.allocation_document_evidence import (
    EXPLICIT_REFERENCE,
    STRONG_CONTEXTUAL_REFERENCE,
    find_allocation_evidence_for_document,
)
from app.policy.allocation_site_relationships import (
    EVIDENCE_BASIS_DOCUMENT_CONFIRMED_SITE,
    create_relationship_if_absent,
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
    relationship_id: int | None = None  # set once create_relationship_if_absent succeeds; None only on a same-run race (see module docstring)


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
    session: Session, document: Document, application: Application, allocations: list[LocalPlanSite],
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

        # --- Section 1/2/3 (amendment): strong evidence for a Site NOT
        # already accepted AUTO-CREATES the relationship, via the shared
        # Stage 2D helper - see module docstring for exactly which
        # evidence class this covers and why (DOCUMENT_CONFIRMED_SITE
        # only, never a fuzzy/multi-site claim this module has no basis
        # to make). create_relationship_if_absent does its own LIVE
        # idempotency check, so a second document in this SAME batch
        # naming the same new (allocation_id, site_id) pair is still safe
        # (returns None, not a duplicate/error).
        new_strong_site_ids = {h.site_id for h in strong_linked} - existing_site_ids
        for site_id in new_strong_site_ids:
            best = _best_strong_hit(strong_linked, site_id)
            created = create_relationship_if_absent(
                session, allocation_id=allocation_id, site_id=site_id,
                evidence_basis=EVIDENCE_BASIS_DOCUMENT_CONFIRMED_SITE,
                evidence_category=best.category, evidence_document_id=document.id,
                evidence_application_id=application.id, evidence_snippet=best.snippet,
            )
            # This allocation now has a real relationship for this Site -
            # keep the in-memory snapshot honest for the REST of this
            # SAME batch (a later document for the same allocation must
            # not attempt the same pair again).
            if created is not None:
                relationships_by_allocation.setdefault(allocation_id, []).append(created)
                existing_site_ids.add(site_id)
            report.new_strong_candidates.append(NewCandidateHit(
                allocation_id=allocation_id, allocation_reference=allocation.policy_reference,
                allocation_name=allocation.site_name, site_id=site_id, document_id=document.id,
                application_id=application.id, application_reference=application.reference,
                category=best.category, snippet=best.snippet,
                relationship_id=created.id if created is not None else None,
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
    retry next run). Any relationship this document was in the middle of
    creating when it failed is explicitly rolled back (session.rollback())
    before moving on - a partially-applied write from a failed document
    must never leak into the next document's processing or be silently
    committed alongside it. Each SUCCESSFUL document's own writes
    (scanned_at + any relationship creates/flips found for IT) are
    committed immediately after that document succeeds, before moving to
    the next - so an earlier document's already-committed work is never
    at risk from a later document's failure either.

    IDEMPOTENT: rerunning immediately afterwards finds zero unscanned
    documents (this call marks every successfully-processed one), zero
    new relationship creates (create_relationship_if_absent is itself
    idempotent), and zero new contradiction flags (a relationship already
    flagged stays flagged, never double-flagged - see
    _process_one_document)."""
    documents = select_unscanned_documents(session, council_code, limit=limit)
    allocations = list(session.execute(
        select(LocalPlanSite).where(LocalPlanSite.council_code == council_code)
    ).scalars())
    relationships_by_allocation = _existing_relationships_by_allocation(session, [a.id for a in allocations])

    report = AllocationEvidenceScanReport()

    for document, application in documents:
        try:
            _process_one_document(session, document, application, allocations, relationships_by_allocation, report)
        except Exception as exc:  # noqa: BLE001 - deliberate: one bad document must never abort the batch
            session.rollback()  # discard any partial write this document was in the middle of
            report.documents_failed += 1
            print(f"[allocation-evidence-scan] council={council_code} document_id={document.id} "
                  f"application_id={application.id} FAILED: {exc!r}")
            continue

        document.allocation_evidence_scanned_at = utcnow()
        report.documents_scanned += 1
        session.commit()

    return report


# --- Historical scan-state cutover (Stage 3B final amendment, Section 7) ----
#
# The 3,137 documents already processed by Stage 2C's historical evidence
# scan would otherwise ALL appear "unscanned" the moment Document.
# allocation_evidence_scanned_at is added - triggering a slow, wasteful,
# multi-day incremental rescan of the entire historic corpus purely to
# initialise scan state, which Section 11 of the original Stage 3B task
# already explicitly ruled out ("if scanning every historical document on
# every run would be required, that architecture is NOT approved").
#
# DESIGN: mark every Document that already existed before a single
# rollout CUTOFF timestamp as "scanned" (at that cutoff), without
# re-evaluating its text at all - it was already covered by Stage 2C's
# own historical pass (scripts/dry_run_gm_allocation_site_relationships.py
# / app.policy.allocation_site_relationships), which is untouched and
# remains the historical/manual mechanism (Section 15 of the original
# task: "do NOT rebuild another historical scanner").
#
# SCOPE (deliberately broad, not narrowly re-derived per-council): every
# Document with usable extracted text, not yet scanned, whose
# downloaded_at predates the cutoff - OR whose downloaded_at is NULL at
# all (a legacy row with no download timestamp cannot be PROVEN to
# postdate the cutover; treating "unknown" as "before cutover" is the
# safe direction, since the alternative would leave it eligible for
# routine incremental rescanning forever, silently reintroducing the
# exact full-corpus cost this backfill exists to avoid). A council with
# zero LocalPlanSite allocations produces zero evidence hits regardless
# of scan state (Stage 2C's own search is allocation-driven) - marking
# its documents scanned too is harmless, not an over-reach requiring a
# separate per-council eligibility reconstruction this codebase has no
# reliable way to prove after the fact.
#
# WHY A SINGLE CUTOFF PARAMETER, NOT A HARD-CODED DATE: this script is
# meant to run ONCE, during deployment, between "migrate_schema" and
# "allow cron jobs to run" (the same established deployment order this
# codebase already documents - see docs/PLATFORM_ARCHITECTURE.md). The
# real safety mechanism is OPERATIONAL (no new document can be extracted
# while cron jobs are paused), not the cutoff value itself - the cutoff
# defaults to "now" at invocation time purely so the WHERE clause has a
# concrete, auditable boundary, not because precise timing matters if the
# operational order above is followed.


def backfill_historical_scan_state(session: Session, *, cutoff: dt.datetime | None = None) -> dict:
    """READ ONLY dry-run - computes exactly what the write-mode backfill
    below would mark, without mutating anything. `cutoff` defaults to
    "now" (see module-level design note above). IDEMPOTENT to call
    repeatedly - always recomputes against live state, never assumes a
    previous run's result."""
    cutoff = cutoff or utcnow()
    candidates = session.execute(
        select(Document).where(
            Document.text_extracted.is_(True),
            Document.extracted_text.is_not(None),
            Document.allocation_evidence_scanned_at.is_(None),
            or_(Document.downloaded_at.is_(None), Document.downloaded_at < cutoff),
        )
    ).scalars().all()
    return {"cutoff": cutoff, "eligible_document_ids": [d.id for d in candidates], "count": len(candidates)}


def apply_historical_scan_state_backfill(session: Session, *, cutoff: dt.datetime | None = None) -> dict:
    """PRODUCTION WRITE MODE. Only called with explicit CLI confirmation
    (scripts/backfill_allocation_evidence_scan_state.py's own --execute/
    --confirm gate, matching every other Stage 2/3 script's established
    convention). Recomputes the dry-run FRESH immediately before writing
    (fail-closed against concurrent state, same discipline as Stage 2D's
    own run_controlled_relationship_write) and re-checks each individual
    row live right before marking it - skipping (never erroring) any
    document a concurrent process already scanned, so this is safe to run
    any number of times."""
    plan = backfill_historical_scan_state(session, cutoff=cutoff)
    cutoff_value = plan["cutoff"]
    marked = 0
    for doc_id in plan["eligible_document_ids"]:
        doc = session.get(Document, doc_id)
        if doc is None or doc.allocation_evidence_scanned_at is not None:
            continue
        doc.allocation_evidence_scanned_at = cutoff_value
        marked += 1
    session.commit()
    return {"cutoff": cutoff_value, "marked_count": marked}
