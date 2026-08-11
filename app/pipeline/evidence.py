"""Evidence sufficiency (Evidence Completeness Foundation, PR A) - the
canonical, reusable answer to "does this application already have enough
useful planning evidence," derived from stored Document rows rather than
persisted as its own boolean (CLAUDE.md/this sprint's own principle: prefer
deterministic derivation over stored state where the underlying facts
already exist and are cheap to recompute - see the Evidence Sufficiency &
Triggered AI Freshness audit, Part 8).

Approved rule (Evidence Sufficiency & Triggered AI Freshness audit, Part 4):
sufficient when EITHER >=3 useful documents, OR >=2 of the 3 core categories
(planning_statement/decision_notice/officer_report) are each present at
least once. Deliberately NOT the originally-hypothesised "5 documents" rule -
production analysis (692 SchemeIntelligence rows against their source
document counts) showed extraction success saturating at 3-4 useful
documents (89.0% at 1-2 useful, 98.2% at 3-4, 99.1% at 5-6 and 7+ - the
marginal 5th document buys almost nothing), and found 102 real applications
with strong core-category coverage but fewer than 5 useful documents that a
flat count-only rule would wrongly classify as insufficient.

This module intentionally does NOT decide when to re-check a scheme's
evidence (that is a future PR's job - material-change detection, the 90-day
fallback, or manual refresh) - it only ever answers "is what we have right
now enough," given whatever Document rows already exist.
"""
from __future__ import annotations

from app.db.models import Application, Document
from app.extraction.pdf_text import USEFUL_DOC_TYPES

CORE_DOCUMENT_TYPES = frozenset({"planning_statement", "decision_notice", "officer_report"})

MIN_USEFUL_DOCUMENTS = 3
MIN_CORE_CATEGORIES = 2


def document_identity_key(source_url: str | None, document_name: str | None) -> tuple[str, str]:
    """The smallest reliable identity available from existing portal/
    document metadata (Evidence Sufficiency & Triggered AI Freshness audit,
    Part 1 finding: Document has no content hash, version, or unique
    constraint today) - source_url where the portal exposes one (idox/
    arcus), falling back to document_name for idox_anite (Bury), whose
    document URLs are only generated client-side at download time and are
    never persisted (see app.scrapers.documents' own module docstring).
    Prefixed by kind so a URL and a name can never collide with each other.

    Shared by _document_identity (already-stored Document rows, below) and
    by app.pipeline.run_weekly.stage_documents (a not-yet-stored discovery-
    listing row, before deciding whether to insert it) - the ONE identity
    rule used everywhere a "have we already got this exact document"
    decision is made, so a freshly (re)discovered document and an already-
    stored one are always compared the same way. This is what makes future
    targeted rediscovery (PR B) safe against creating duplicate Document
    rows without requiring a database-level uniqueness constraint (which
    would risk failing migration against any duplicates that may already
    exist in production, given no such constraint has ever been enforced)."""
    if source_url:
        return ("url", source_url)
    return ("name", document_name or "")


def _document_identity(document: Document) -> tuple[str, str]:
    return document_identity_key(document.source_url, document.document_name)


def deduped_useful_documents(application: Application) -> list[Document]:
    """This application's stored Document rows that are both a useful type
    and distinct by identity - one row per genuinely distinct piece of
    evidence, first-seen-wins on a duplicate. Guards is_evidence_sufficient
    below against a duplicate/re-discovered row ever inflating a count past
    what genuinely distinct evidence supports."""
    seen: set[tuple[str, str]] = set()
    result: list[Document] = []
    for document in application.documents:
        if document.doc_type not in USEFUL_DOC_TYPES:
            continue
        identity = _document_identity(document)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(document)
    return result


def is_evidence_sufficient(application: Application) -> bool:
    """The one canonical answer to "does this application already have
    enough useful evidence to extract from" - see this module's own
    docstring for the approved rule and its production justification. Any
    future code (PR B's material-change escalation, the 90-day fallback,
    manual refresh, or a SQL-level equivalent if one is ever needed) must
    call this function rather than re-implementing the >=3 / >=2-core
    comparison separately, so the definition can only ever drift in one
    place. Deliberately not persisted as a column - see this module's own
    docstring for why derivation is preferred here."""
    useful = deduped_useful_documents(application)
    if len(useful) >= MIN_USEFUL_DOCUMENTS:
        return True
    core_categories_present = {d.doc_type for d in useful} & CORE_DOCUMENT_TYPES
    return len(core_categories_present) >= MIN_CORE_CATEGORIES
