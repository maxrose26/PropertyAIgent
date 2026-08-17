"""Stage 4B - ownership/control relationship persistence + conservative
entity resolution + zero-write production dry-run reporting (Sections
7/8/10 of the Stage 4B task).

ONE PERSISTENCE PATH (mirrors app.policy.allocation_site_relationships.
create_relationship_if_absent and Stage 3B's own "do not create a second
direct-write path" precedent exactly): every ControlRelationship row this
codebase ever creates goes through create_control_relationship_if_absent
below - nothing else in this codebase constructs ControlRelationship(...)
directly.

ENTITY RESOLUTION (Stage 4B Section 7): resolve_existing_company reuses
app.enrichment.companies_house's OWN normalise_name/match_score helpers
against Company rows ALREADY IN THE DATABASE - it never calls the
Companies House API, never creates a new Company row, and returns None
(leaves the relationship's company_id unset) on anything less than a
confident match, per the task's own explicit "do not auto-resolve
ambiguous names" instruction. A high bar (exact normalised-name match, or
fuzzy score >= 92) is used deliberately - a false-positive company match
here would silently attach one real company's Companies House identity
(and therefore its officers/PSC/enrichment history) to a DIFFERENT
extracted name, which is a materially worse failure than simply leaving
company_id null and showing the raw extracted name instead."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Application, Company, ControlRelationship, Document, utcnow
from app.enrichment.companies_house import match_score, normalise_name
from app.extraction.ownership_control_evidence import (
    CERTIFICATE_UNKNOWN,
    NO_CERTIFICATE_EVIDENCE,
    detect_ownership_certificate,
    extract_s106_defined_parties,
    extract_s106_title_numbers,
)

# Fuzzy-match acceptance threshold for resolving an extracted name to an
# EXISTING Company row - deliberately high (see module docstring); a
# score below this leaves company_id unset rather than risk a wrong match.
_COMPANY_MATCH_THRESHOLD = 92.0


def resolve_existing_company(session: Session, name_raw: str) -> Company | None:
    """READ ONLY - issues a query, makes no writes, calls no external
    service. Returns an EXISTING Company row only on a confident match;
    None otherwise (including "no Company rows exist to compare against"
    - never a reason to create one here)."""
    normalised = normalise_name(name_raw)
    if not normalised:
        return None

    candidates = session.execute(select(Company)).scalars().all()
    exact = [c for c in candidates if normalise_name(c.name_raw) == normalised]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        # More than one existing Company row normalises to the same name -
        # genuinely ambiguous, never guess between them.
        return None

    best: Company | None = None
    best_score = 0.0
    for c in candidates:
        score = match_score(name_raw, c.name_raw)
        if score > best_score:
            best, best_score = c, score
    if best is not None and best_score >= _COMPANY_MATCH_THRESHOLD:
        return best
    return None


def create_control_relationship_if_absent(
    session: Session, *,
    entity_name_raw: str, role: str, evidence_basis: str, evidence_category: str, extraction_method: str,
    application_id: int | None = None, site_id: int | None = None,
    entity_type: str = "unknown", company_id: int | None = None,
    confidence: str | None = None, evidence_document_id: int | None = None,
    evidence_snippet: str | None = None, title_number: str | None = None,
    review_status: str = "auto_applied",
) -> ControlRelationship | None:
    """The ONE shared row-creation path for this table (see module
    docstring). LIVE idempotency + contradiction handling:

    - An existing row for the SAME (application_id, role) with the SAME
      entity_name_raw (case-insensitive) is a duplicate confirmation of
      the same claim - no new row, returns None (pure no-op), exactly
      like create_relationship_if_absent's own precedent.
    - An existing row for the SAME (application_id, role) with a
      DIFFERENT entity_name_raw is a genuine competing claim - NEITHER
      row is deleted or silently preferred. The new row is still created,
      and every OTHER non-rejected row sharing that (application_id,
      role) - including the new one - is set to review_status=
      "needs_confirmation", so a human reviewing this application sees
      BOTH candidates flagged rather than one silently "winning".
    - No existing row for that (application_id, role) at all - a plain
      new row at the given review_status (normally "auto_applied")."""
    existing = session.execute(
        select(ControlRelationship).where(
            ControlRelationship.application_id == application_id,
            ControlRelationship.role == role,
            ControlRelationship.review_status != "rejected",
        )
    ).scalars().all()

    normalised_new = entity_name_raw.strip().lower()
    for rel in existing:
        if rel.entity_name_raw.strip().lower() == normalised_new:
            return None  # same claim already recorded - idempotent no-op

    contradiction = len(existing) > 0
    effective_review_status = "needs_confirmation" if contradiction else review_status

    rel = ControlRelationship(
        application_id=application_id, site_id=site_id,
        entity_name_raw=entity_name_raw, entity_type=entity_type, company_id=company_id,
        role=role, evidence_basis=evidence_basis, evidence_category=evidence_category,
        extraction_method=extraction_method, confidence=confidence,
        evidence_document_id=evidence_document_id, evidence_snippet=evidence_snippet,
        title_number=title_number, review_status=effective_review_status,
    )
    session.add(rel)
    session.flush()

    if contradiction:
        for other in existing:
            other.review_status = "needs_confirmation"

    return rel


# --- Section 10: zero-write production dry-run ------------------------------


def _application_ids_needing_semantic_review(session: Session, council_code: str | None) -> set[int]:
    """S106 documents that mention 'the owner'/'the developer' in prose
    but where the strict deterministic defined-role patterns found
    nothing - real evidence may exist, but it is not in a shape this
    module's regex can safely resolve without guessing. Flagged for a
    future bounded AI pass (Section 5), never guessed at here."""
    query = select(Document, Application).join(Application, Document.application_id == Application.id).where(
        Document.doc_type == "s106", Document.text_extracted.is_(True), Document.extracted_text.is_not(None),
    )
    if council_code:
        query = query.where(Application.council_code == council_code)
    flagged: set[int] = set()
    for doc, app in session.execute(query).all():
        low = (doc.extracted_text or "").lower()
        mentions_role_language = "the owner" in low or "the developer" in low or "the mortgagee" in low
        if mentions_role_language and not extract_s106_defined_parties(doc):
            flagged.add(app.id)
    return flagged


def build_ownership_control_dry_run_report(session: Session, council_code: str | None = None) -> dict:
    """READ ONLY. Runs ONLY the deterministic extractors in app.extraction.
    ownership_control_evidence over the corpus already held - no OpenAI,
    no Companies House, no Land Registry, no writes of any kind (a plain
    Session is accepted purely to run SELECT queries; nothing is ever
    added/flushed/committed here)."""
    form_query = select(Document, Application).join(Application, Document.application_id == Application.id).where(
        Document.doc_type == "application_form", Document.text_extracted.is_(True), Document.extracted_text.is_not(None),
    )
    if council_code:
        form_query = form_query.where(Application.council_code == council_code)
    forms = session.execute(form_query).all()

    cert_counts = {"CERTIFICATE_A": 0, "CERTIFICATE_B": 0, "CERTIFICATE_C": 0, "CERTIFICATE_D": 0}
    ambiguous_count = 0
    no_evidence_count = 0
    apps_with_control_evidence: set[int] = set()
    site_ids_with_control_evidence: set[int] = set()

    for doc, app in forms:
        result = detect_ownership_certificate(doc)
        if result is None:
            continue
        if result.certificate_type == NO_CERTIFICATE_EVIDENCE:
            no_evidence_count += 1
        elif result.certificate_type == CERTIFICATE_UNKNOWN:
            ambiguous_count += 1
        else:
            cert_counts[result.certificate_type] += 1
            apps_with_control_evidence.add(app.id)
            if app.site_id:
                site_ids_with_control_evidence.add(app.site_id)

    s106_query = select(Document, Application).join(Application, Document.application_id == Application.id).where(
        Document.doc_type == "s106", Document.text_extracted.is_(True), Document.extracted_text.is_not(None),
    )
    if council_code:
        s106_query = s106_query.where(Application.council_code == council_code)
    s106_docs = session.execute(s106_query).all()

    role_counts = {"OWNER": 0, "DEVELOPER": 0, "MORTGAGEE": 0}
    title_number_count = 0
    conflicting_cases = 0

    for doc, app in s106_docs:
        parties = extract_s106_defined_parties(doc)
        titles = extract_s106_title_numbers(doc)
        title_number_count += len(titles)
        by_role: dict[str, set[str]] = {}
        for hit in parties:
            role_counts[hit.role] += 1
            by_role.setdefault(hit.role, set()).add(hit.entity_name_raw.strip().lower())
            apps_with_control_evidence.add(app.id)
            if app.site_id:
                site_ids_with_control_evidence.add(app.site_id)
        for names in by_role.values():
            if len(names) > 1:
                conflicting_cases += 1

    semantic_review_apps = _application_ids_needing_semantic_review(session, council_code)

    return {
        "application_forms_evaluated": len(forms),
        "certificate_a_count": cert_counts["CERTIFICATE_A"],
        "certificate_b_count": cert_counts["CERTIFICATE_B"],
        "certificate_c_count": cert_counts["CERTIFICATE_C"],
        "certificate_d_count": cert_counts["CERTIFICATE_D"],
        "certificate_ambiguous_count": ambiguous_count,
        "certificate_no_evidence_count": no_evidence_count,
        "s106_documents_evaluated": len(s106_docs),
        "s106_title_numbers_extracted": title_number_count,
        "s106_explicit_owner_count": role_counts["OWNER"],
        "s106_explicit_developer_count": role_counts["DEVELOPER"],
        "s106_explicit_mortgagee_count": role_counts["MORTGAGEE"],
        "applications_with_deterministic_control_evidence": len(apps_with_control_evidence),
        "sites_with_deterministic_control_evidence": len(site_ids_with_control_evidence),
        "conflicting_evidence_cases": conflicting_cases,
        "cases_requiring_semantic_review": len(semantic_review_apps),
        "generated_at": utcnow(),
    }
