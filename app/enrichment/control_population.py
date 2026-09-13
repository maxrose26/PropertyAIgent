"""Stage 4B.1 ("Deterministic Ownership & Control Population Runner") -
orchestrates ONLY the existing, already-approved Stage 4B building blocks
into a safe, idempotent, dry-run-by-default production population pass.

Introduces NO new extraction logic: every evidence decision is made by
app.extraction.ownership_control_evidence.detect_ownership_certificate /
extract_s106_defined_parties / extract_s106_title_numbers, exactly as
Stage 4B built and approved them. Introduces NO new persistence logic:
every write goes through app.enrichment.control_entities.create_control_
relationship_if_absent, the one shared path that module already owns.
This module's own job is ONLY document selection, evidence-to-role
routing, entity resolution wiring, per-document transaction safety, and
report accounting - the same "thin orchestration over existing
primitives" shape Stage 3B's app.policy.allocation_evidence_scan already
established for a different evidence domain.

ELIGIBLE DETERMINISTIC EVIDENCE (Stage 4B.1 Section 5/6/7, FINAL AMENDMENT
"Certificate-A Identity Safety" - the ONLY evidence classes this module
ever persists):

  CERTIFICATE_A + applicant identity independently confirmed as
  belonging to that SAME application-form Document
      -> OWNER relationship for the confirmed applicant. Certificate A
         alone only proves SOME applicant declared sole ownership - it
         says nothing about WHO. The identity used here is resolved by
         app.extraction.ownership_control_evidence.resolve_certificate_
         a_applicant_identity, which reads the SAME Document's own
         "Applicant Details" section directly (preferred) and only falls
         back to Application.applicant_name_raw (a separate portal-
         scraped field) when that raw name is ALSO conservatively
         confirmed present within the same section - never the AI-
         derived SchemeIntelligence.applicant_company, which belongs to
         a different evidence path entirely (Stage 4C's job, not this
         one's). A form/raw CONFLICT, or no confirmable identity at all,
         resolves to CERTIFICATE_A_APPLICANT_IDENTITY_UNRESOLVED and
         creates ZERO relationship - see that function's own docstring
         for the full algorithm and the real production edge case
         (individual applicants) it was built against.

         Certificate A is a SELF-declaration by the applicant that they
         are the sole owner "for planning-certificate purposes" -
         entity_category is deliberately CERTIFICATE_A_APPLICANT_OWNER_
         DECLARATION (never a bare "OWNER" evidence_category), and
         confidence is "medium", not "high" - a self-declaration is real
         evidence but is NOT the same evidential weight as a third-
         party-witnessed S106 deed. It NEVER means "currently registered
         owner" - see ControlRelationship's own semantic invariant,
         unchanged by this module.

  S106_DEFINED_OWNER / S106_DEFINED_DEVELOPER / S106_DEFINED_MORTGAGEE
      -> the exact role app.extraction.ownership_control_evidence.
         extract_s106_defined_parties already determined, confidence
         "high" (a legal deed's own defining clause). A title number
         found in the SAME document is attached ONLY to that document's
         OWNER-role relationship (title is land/property evidence,
         naturally an owner's own fact - never attached to a Developer/
         Mortgagee row, which would misrepresent whose title it is).

  CERTIFICATE_B / CERTIFICATE_C / CERTIFICATE_D + applicant identity
  independently confirmed (Gate 2C V1, "Certificate B/C/D structured
  evidence") -> an APPLICANT relationship (never OWNER - B/C/D each mean
  something other than sole ownership) for the confirmed applicant, using
  the EXACT SAME identity-confirmation algorithm as Certificate A
  (resolve_certificate_a_applicant_identity - its name is certificate-
  specific for historical reasons only; the algorithm itself reads the
  form's own "Applicant Details" section regardless of which certificate
  letter was detected). This deliberately never names a specific OTHER
  owner - no such extractor exists in this codebase (Acquisition
  Intelligence Architecture Amendment, "do not invent named owners from
  B/C/D unless the document actually provides safely extractable names")
  - only the applicant's own declared ownership-completeness position:
  evidence_category = CERTIFICATE_B_OTHER_OWNER_INTEREST_DECLARED /
  CERTIFICATE_C_PARTIAL_OWNERSHIP_IDENTIFICATION /
  CERTIFICATE_D_OWNERSHIP_NOT_FULLY_KNOWN, confidence "medium" (a self-
  declaration, same evidential weight as Certificate A).

NEVER PERSISTED, by construction:
  - CERTIFICATE_B / C / D with no confirmable applicant identity (same
    fail-closed rule as Certificate A - reported via certificate_bcd_
    identity_unresolved/certificate_bcd_reported_no_entity, never guessed).
  - A named, specific OTHER owner implied by Certificate B/C/D (no
    extractor for this exists - only the applicant's own position is ever
    recorded, never a fabricated third party).
  - CERTIFICATE_A with no Application.applicant_name_raw available (no
    safe entity name exists - reported, never invented).
  - CERTIFICATE_UNKNOWN / NO_CERTIFICATE_EVIDENCE (Stage 4B's own "fail
    closed" outcomes - carried through unchanged).
  - A title number with no accompanying party relationship in the same
    document (never invents a party just to hold a title number).
  - Any S106 document flagged by _application_ids_needing_semantic_
    review (owner/developer/mortgagee LANGUAGE present in prose but the
    strict deterministic pattern found nothing confident) - reported as
    excluded, never guessed at.

TRANSACTION SAFETY: processed strictly per-document. Each document's
evidence is written and committed as one unit; an exception anywhere
while processing one document triggers session.rollback() for that
document only (discarding any partial writes from it) before moving on -
one malformed document can never corrupt relationships already committed
for a prior document. Mirrors app.policy.allocation_evidence_scan.
scan_council_for_allocation_evidence's own established per-document
isolation exactly.

DRY-RUN vs EXECUTE share the SAME evidence-evaluation code path (Stage
4B.1 Section 12's own "re-evaluate evidence at execution time rather
than blindly trusting a frozen dry-run artefact" instruction) - dry_run
only changes whether create_control_relationship_if_absent is actually
called (and therefore whether anything is added/flushed/committed); the
certificate/S106 extraction and role-routing logic is identical either
way, so a dry-run report can never drift from what execute mode would
actually do."""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.db.models import Application, ControlRelationship, Document
from app.enrichment.control_entities import (
    _application_ids_needing_semantic_review,
    create_control_relationship_if_absent,
    resolve_existing_company,
)
from app.extraction.ownership_control_evidence import (
    CERTIFICATE_B,
    CERTIFICATE_C,
    CERTIFICATE_D,
    CERTIFICATE_UNKNOWN,
    NO_CERTIFICATE_EVIDENCE,
    detect_ownership_certificate,
    extract_s106_defined_parties,
    extract_s106_title_numbers,
    resolve_certificate_a_applicant_identity,
)

CERTIFICATE_A_EVIDENCE_CATEGORY = "CERTIFICATE_A_APPLICANT_OWNER_DECLARATION"

# Gate 2C V1 ("Certificate B/C/D structured evidence") - evidence_basis/
# evidence_category for the applicant's own declared ownership-
# completeness position, per Certificate letter. Deliberately named after
# what the applicant DECLARED (never a stronger claim - see the Acquisition
# Intelligence Architecture Amendment, "Ownership semantics"):
#   B - applicant declares they are NOT the sole owner (other owner
#       interest exists), no specific other owner named.
#   C - some but not all owners known/agricultural tenants may exist -
#       incomplete identification, per the certificate's own wording.
#   D - the applicant could not identify all the other owners - ownership
#       not fully known.
CERTIFICATE_BCD_EVIDENCE_BASIS = {
    CERTIFICATE_B: "certificate_b_declaration",
    CERTIFICATE_C: "certificate_c_declaration",
    CERTIFICATE_D: "certificate_d_declaration",
}
CERTIFICATE_BCD_EVIDENCE_CATEGORY = {
    CERTIFICATE_B: "CERTIFICATE_B_OTHER_OWNER_INTEREST_DECLARED",
    CERTIFICATE_C: "CERTIFICATE_C_PARTIAL_OWNERSHIP_IDENTIFICATION",
    CERTIFICATE_D: "CERTIFICATE_D_OWNERSHIP_NOT_FULLY_KNOWN",
}


@dataclass
class PopulationReport:
    application_forms_evaluated: int = 0
    certificate_a_count: int = 0
    certificate_b_count: int = 0
    certificate_c_count: int = 0
    certificate_d_count: int = 0
    certificate_ambiguous_count: int = 0
    certificate_no_evidence_count: int = 0
    certificate_a_identity_confirmed_from_form: int = 0
    certificate_a_identity_confirmed_via_raw_fallback: int = 0
    certificate_a_identity_unresolved: int = 0
    certificate_a_relationships_eligible: int = 0
    # Gate 2C V1 - Certificate B/C/D now reuse the same identity-
    # confirmation algorithm as Certificate A (see CERTIFICATE_BCD_
    # EVIDENCE_BASIS/CATEGORY above); certificate_bcd_reported_no_entity
    # now means "identity unresolved", not "always report-only".
    certificate_bcd_identity_unresolved: int = 0
    certificate_bcd_relationships_eligible: int = 0
    certificate_bcd_reported_no_entity: int = 0

    s106_documents_evaluated: int = 0
    s106_title_numbers_found: int = 0
    s106_title_numbers_without_party: int = 0
    s106_owner_hits: int = 0
    s106_developer_hits: int = 0
    s106_mortgagee_hits: int = 0

    relationships_would_create: int = 0
    relationships_created: int = 0
    relationships_already_present: int = 0
    conflicting_evidence_cases: int = 0

    company_resolved_count: int = 0
    unresolved_entity_count: int = 0

    semantic_review_excluded_count: int = 0

    documents_failed: int = 0
    errors: list[str] = field(default_factory=list)

    applications_with_deterministic_evidence: int = 0
    sites_with_deterministic_evidence: int = 0

    _apps_seen: set[int] = field(default_factory=set, repr=False)
    _sites_seen: set[int] = field(default_factory=set, repr=False)


def _control_relationships_table_exists(session: Session) -> bool:
    """Section 12's own fail-closed schema check, reused for the dry-run's
    OWN idempotency preview (Section 9/10 below): if the table simply
    doesn't exist yet, every 'would create' candidate is trivially not-
    yet-present - there is nothing to query, and that is itself the
    correct, honest answer, not an error."""
    bind = session.get_bind()
    return inspect(bind).has_table(ControlRelationship.__tablename__)


def _existing_rows_for(session: Session, application_id: int, role: str, table_exists: bool) -> list[ControlRelationship]:
    if not table_exists:
        return []
    return session.execute(
        select(ControlRelationship).where(
            ControlRelationship.application_id == application_id,
            ControlRelationship.role == role,
            ControlRelationship.review_status != "rejected",
        )
    ).scalars().all()


def _persist_or_preview(
    session: Session, report: PopulationReport, *, dry_run: bool, table_exists: bool,
    application_id: int, site_id: int | None, entity_name_raw: str, role: str,
    evidence_basis: str, evidence_category: str, confidence: str,
    evidence_document_id: int, evidence_snippet: str, title_number: str | None = None,
    known_entity_type: str | None = None,
) -> None:
    if known_entity_type == "individual":
        # Companies House resolution is meaningless for a named person -
        # never attempted, never counted as company_resolved/unresolved.
        entity_type, company_id = "individual", None
    elif known_entity_type == "company":
        # Gate 2C V1 fix ("narrow entity-type resolution improvement") -
        # the form's own "Company Name" field ALREADY told us this is a
        # company (resolve_certificate_a_applicant_identity's own
        # deterministic parse, entity_type="company") - that classification
        # must never be discarded just because no EXISTING Company row
        # happens to match it. Still attempt resolve_existing_company for
        # company_id (conservative - only an exact/high-confidence match
        # against an already-enriched row, never creates one), but
        # entity_type="company" is retained either way - this is exactly
        # the "establish entity_type=company without establishing
        # company_id" distinction the investigation called out as safe.
        # Real production case this fixes: "Ropley Properties Limited" /
        # "Triple Jersey Limited" (Certificate A, same_form_company_name)
        # previously landed as entity_type=unknown purely because neither
        # had an existing, Companies-House-enriched Company row to match.
        company = resolve_existing_company(session, entity_name_raw)
        if company is not None:
            report.company_resolved_count += 1
            entity_type, company_id = "company", company.id
        else:
            entity_type, company_id = "company", None
    else:
        company = resolve_existing_company(session, entity_name_raw)
        if company is not None:
            report.company_resolved_count += 1
            entity_type, company_id = "company", company.id
        else:
            report.unresolved_entity_count += 1
            entity_type, company_id = "unknown", None

    if dry_run:
        existing = _existing_rows_for(session, application_id, role, table_exists)
        normalised = entity_name_raw.strip().lower()
        if any(r.entity_name_raw.strip().lower() == normalised for r in existing):
            report.relationships_already_present += 1
        else:
            if existing:
                report.conflicting_evidence_cases += 1
            report.relationships_would_create += 1
        return

    created = create_control_relationship_if_absent(
        session, application_id=application_id, site_id=site_id,
        entity_name_raw=entity_name_raw, entity_type=entity_type, company_id=company_id,
        role=role, evidence_basis=evidence_basis, evidence_category=evidence_category,
        extraction_method="deterministic_regex", confidence=confidence,
        evidence_document_id=evidence_document_id, evidence_snippet=evidence_snippet,
        title_number=title_number,
    )
    if created is None:
        report.relationships_already_present += 1
    else:
        report.relationships_created += 1


def run_control_relationship_population(
    session: Session, *, council_code: str | None = None, dry_run: bool = True,
) -> PopulationReport:
    """The one orchestration entry point. dry_run=True (default) makes
    ZERO database mutations - every write-shaped branch below is guarded
    by _persist_or_preview's own dry_run check, never by a separate code
    path. dry_run=False actually calls create_control_relationship_if_
    absent and commits per document (see module docstring, TRANSACTION
    SAFETY)."""
    report = PopulationReport()
    table_exists = _control_relationships_table_exists(session)

    form_query = select(Document, Application).join(Application, Document.application_id == Application.id).where(
        Document.doc_type == "application_form", Document.text_extracted.is_(True), Document.extracted_text.is_not(None),
    )
    if council_code:
        form_query = form_query.where(Application.council_code == council_code)

    for doc, app in session.execute(form_query).all():
        report.application_forms_evaluated += 1
        try:
            result = detect_ownership_certificate(doc)
            if result is None:
                continue
            if result.certificate_type == NO_CERTIFICATE_EVIDENCE:
                report.certificate_no_evidence_count += 1
            elif result.certificate_type == CERTIFICATE_UNKNOWN:
                report.certificate_ambiguous_count += 1
            elif result.certificate_type == "CERTIFICATE_A":
                report.certificate_a_count += 1
                identity = resolve_certificate_a_applicant_identity(doc, app)
                if identity.method == "unresolved":
                    report.certificate_a_identity_unresolved += 1
                else:
                    report.certificate_a_relationships_eligible += 1
                    if identity.method == "applicant_name_raw_confirmed_in_form":
                        report.certificate_a_identity_confirmed_via_raw_fallback += 1
                    else:  # same_form_company_name | same_form_individual_name
                        report.certificate_a_identity_confirmed_from_form += 1
                    _persist_or_preview(
                        session, report, dry_run=dry_run, table_exists=table_exists,
                        application_id=app.id, site_id=app.site_id, entity_name_raw=identity.resolved_name,
                        role="OWNER", evidence_basis="certificate_a_declaration",
                        evidence_category=CERTIFICATE_A_EVIDENCE_CATEGORY, confidence="medium",
                        evidence_document_id=doc.id,
                        evidence_snippet=f"{result.snippet or ''} | applicant identity: {identity.snippet or ''}",
                        known_entity_type=identity.entity_type if identity.entity_type in ("individual", "company") else None,
                    )
                    report._apps_seen.add(app.id)
                    if app.site_id:
                        report._sites_seen.add(app.site_id)
            elif result.certificate_type in CERTIFICATE_BCD_EVIDENCE_CATEGORY:
                # Gate 2C V1 ("Certificate B/C/D structured evidence") -
                # extends the Certificate A pattern to B/C/D. Certificate
                # B/C/D never name a SPECIFIC other owner safely (Section 6
                # of the approved amendment: "do not invent named owners
                # from B/C/D unless the document actually provides safely
                # extractable names" - no such extractor exists), so this
                # never creates an OWNER-role row. What IS safe and
                # genuinely new evidence: the APPLICANT's own declared
                # ownership-completeness position, resolved by the EXACT
                # SAME identity-confirmation algorithm Certificate A
                # already trusts (resolve_certificate_a_applicant_identity
                # parses the form's own "Applicant Details" section - its
                # name is certificate-specific for historical reasons, but
                # the algorithm itself has no dependency on which
                # certificate letter was detected). Persisted as role=
                # "APPLICANT" (an existing, bounded ControlRelationship
                # role that has never been written before this task) -
                # never "OWNER", since B/C/D each mean something other
                # than sole ownership.
                if result.certificate_type == CERTIFICATE_B:
                    report.certificate_b_count += 1
                elif result.certificate_type == CERTIFICATE_C:
                    report.certificate_c_count += 1
                elif result.certificate_type == CERTIFICATE_D:
                    report.certificate_d_count += 1

                identity = resolve_certificate_a_applicant_identity(doc, app)
                if identity.method == "unresolved":
                    report.certificate_bcd_identity_unresolved += 1
                    report.certificate_bcd_reported_no_entity += 1
                else:
                    report.certificate_bcd_relationships_eligible += 1
                    _persist_or_preview(
                        session, report, dry_run=dry_run, table_exists=table_exists,
                        application_id=app.id, site_id=app.site_id, entity_name_raw=identity.resolved_name,
                        role="APPLICANT", evidence_basis=CERTIFICATE_BCD_EVIDENCE_BASIS[result.certificate_type],
                        evidence_category=CERTIFICATE_BCD_EVIDENCE_CATEGORY[result.certificate_type], confidence="medium",
                        evidence_document_id=doc.id,
                        evidence_snippet=f"{result.snippet or ''} | applicant identity: {identity.snippet or ''}",
                        known_entity_type=identity.entity_type if identity.entity_type in ("individual", "company") else None,
                    )
                    report._apps_seen.add(app.id)
                    if app.site_id:
                        report._sites_seen.add(app.site_id)

            if not dry_run:
                session.commit()
        except Exception as e:
            if not dry_run:
                session.rollback()
            report.documents_failed += 1
            report.errors.append(f"application_form document {doc.id}: {e!r}")

    s106_query = select(Document, Application).join(Application, Document.application_id == Application.id).where(
        Document.doc_type == "s106", Document.text_extracted.is_(True), Document.extracted_text.is_not(None),
    )
    if council_code:
        s106_query = s106_query.where(Application.council_code == council_code)

    for doc, app in session.execute(s106_query).all():
        report.s106_documents_evaluated += 1
        try:
            parties = extract_s106_defined_parties(doc)
            titles = extract_s106_title_numbers(doc)
            report.s106_title_numbers_found += len(titles)
            owner_title_number = titles[0].title_number if titles else None
            roles_found_in_doc: set[str] = set()

            for hit in parties:
                roles_found_in_doc.add(hit.role)
                if hit.role == "OWNER":
                    report.s106_owner_hits += 1
                elif hit.role == "DEVELOPER":
                    report.s106_developer_hits += 1
                elif hit.role == "MORTGAGEE":
                    report.s106_mortgagee_hits += 1

                _persist_or_preview(
                    session, report, dry_run=dry_run, table_exists=table_exists,
                    application_id=app.id, site_id=app.site_id, entity_name_raw=hit.entity_name_raw,
                    role=hit.role, evidence_basis="s106_defined_role", evidence_category=hit.evidence_category,
                    confidence="high", evidence_document_id=doc.id, evidence_snippet=hit.snippet,
                    title_number=owner_title_number if hit.role == "OWNER" else None,
                )
                report._apps_seen.add(app.id)
                if app.site_id:
                    report._sites_seen.add(app.site_id)

            if titles and "OWNER" not in roles_found_in_doc:
                report.s106_title_numbers_without_party += 1

            if not dry_run:
                session.commit()
        except Exception as e:
            if not dry_run:
                session.rollback()
            report.documents_failed += 1
            report.errors.append(f"s106 document {doc.id}: {e!r}")

    report.applications_with_deterministic_evidence = len(report._apps_seen)
    report.sites_with_deterministic_evidence = len(report._sites_seen)
    report.semantic_review_excluded_count = len(_application_ids_needing_semantic_review(session, council_code))

    return report
