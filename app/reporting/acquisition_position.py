"""Gate 2C V1 ("Acquisition Position Intelligence") - AcquisitionPositionFacts.

A computed, non-persisted, buyer-independent read model over already-
existing shared evidence, following the same architectural pattern as
app.reporting.scheme_reconciliation.build_operative_planning_facts:

    RAW / EXTRACTED EVIDENCE -> RECONCILIATION -> COMPUTED TRUSTED FACTS -> CONSUMERS

No new Scheme entity. No persisted universal AcquisitionOpportunity. See
docs/PRODUCT_ROADMAP.md, "Gate 2C — Acquisition Position, Transaction
Signals & Buyer Acquisition Type", for the approved architecture this
implements.

CORE QUESTION this module answers: "what do we know about the parties,
control and transaction context of this development?" It does NOT answer
"is this site available?" and does NOT answer "should this buyer acquire
it?" - see docs/DESIGN_PRINCIPLES.md, "Unknown Must Remain Unknown," for
the availability principle this module is built around. No AVAILABLE /
POTENTIALLY_AVAILABLE / NOT_AVAILABLE classification exists anywhere in
this module, by construction - there is no code path that could produce
one.

GOVERNING SEMANTIC (ControlRelationship's own invariant, unchanged, never
weakened here): every fact below means ONLY "PropertyAIgent holds evidence
that this party had this stated/apparent relationship, in this cited
evidence" - never current registered ownership, current development
control, exclusivity, whole-allocation control, land availability, or
seller intention.

BUYER-INDEPENDENT: this module never imports BuyerProfile or any buyer-
specific logic, and never produces PURSUE/VERIFY/MONITOR/NOT_RELEVANT. The
same AcquisitionPositionFacts for one site/application family is reusable,
unmodified, by every future buyer type (Section 17 of the approved
implementation prompt).

OWNERSHIP-CERTIFICATE AND S106 FACTS ARE COMPUTED LIVE, NOT READ FROM
PERSISTED ControlRelationship ROWS - deliberately. app.enrichment.
control_population.run_control_relationship_population (the batch writer)
is NOT part of the scheduled production pipeline (confirmed by the Gate 2C
architecture investigation) - reading only persisted rows would silently
conflate "no control evidence recorded" with "this document has never
been examined at all", exactly the confusion Section 12 of the approved
implementation prompt requires this module to avoid. detect_ownership_
certificate / resolve_certificate_a_applicant_identity / extract_s106_
defined_parties / extract_s106_title_numbers are all PURE, deterministic,
no-I/O, no-AI functions (confirmed by their own module's docstring) -
re-running them at read time is cheap (no network call, no LLM call, no
extra document fetch - Document.extracted_text is already loaded data)
and makes "was this genuinely examined" an honest, always-true-when-a-
document-exists answer, never a stale batch-job-freshness guess. Any
EXISTING persisted ControlRelationship row is still surfaced separately
(as `recorded_relationships`), for its own review_status/human-
confirmation value a live recomputation cannot reproduce.

THIS IS A V1 BRIDGE, APPROVED FOR GATE 2C V1, NOT NECESSARILY THE FINAL
OPERATING ARCHITECTURE (Product Owner decision, Gate 2C V1 amendment).
The intended long-term direction, not implemented here:

    DOCUMENT ARRIVES / CHANGES
            -> SHARED FACT EXTRACTION ONCE
            -> PERSIST EVIDENCED RELATIONSHIPS
            -> AcquisitionPositionFacts RECONCILES THEM
            -> Transaction Signals
            -> Buyer Agents evaluate many times

Moving to that model requires either scheduling app.enrichment.
control_population.run_control_relationship_population as a routine
production stage, or an equivalent persistence trigger - neither is
implemented or authorised by this module. Until then, live computation
is the correct, honest V1 answer to "was this genuinely examined."

NO COARSE SUMMARY FIELD (e.g. a "control_position"/"acquisition_status"/
"availability_status" enum) EXISTS ANYWHERE IN THIS MODULE - Product
Owner decision, Gate 2C V1 amendment: compressing ownership evidence,
applicant position, developer indication and control/third-party
relationships into one summary risks overstating what the evidence
establishes (a developer/applicant indication does not establish
developer CONTROL; an absence of relationships does not establish
CONTROL_UNKNOWN in a legally meaningful sense). The detailed fact lists
on AcquisitionPositionFacts ARE the trusted source of truth - a consumer
reads them directly, never a derived label.

DEVELOPMENT STATE IS DELIBERATELY NOT A FIELD HERE - see Gate 2B's own
app.pipeline.lapse_tracking.compute_lapse_status / app.pipeline.
phase_tracking.compute_phase_progress for that fact. A consumer wanting
both reads them side by side, never merged into one taxonomy (Section 16
of the approved implementation prompt, "Development state remains
separate").
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Application, ApplicantIntelligence, ControlRelationship
from app.enrichment.control_entities import resolve_existing_company
from app.extraction.ownership_control_evidence import (
    CERTIFICATE_A,
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
from app.reporting.applicant_identity import best_organisation_name_candidates, resolve_applicant_identity

# --- Ownership evidence states (Acquisition Intelligence Architecture Amendment,
# "Ownership semantics" - evidence-specific, never a stronger inference) ---
OWNERSHIP_APPLICANT_DECLARED_SOLE_OWNER = "APPLICANT_DECLARED_SOLE_OWNER"
OWNERSHIP_OTHER_OWNER_INTEREST_DECLARED = "OTHER_OWNER_INTEREST_DECLARED"
OWNERSHIP_PARTIAL_IDENTIFICATION = "PARTIAL_OWNERSHIP_IDENTIFICATION"
OWNERSHIP_NOT_FULLY_KNOWN = "OWNERSHIP_NOT_FULLY_KNOWN"
OWNERSHIP_S106_DEFINED_OWNER = "S106_DEFINED_OWNER"

_CERTIFICATE_TO_OWNERSHIP_STATE = {
    CERTIFICATE_A: OWNERSHIP_APPLICANT_DECLARED_SOLE_OWNER,
    CERTIFICATE_B: OWNERSHIP_OTHER_OWNER_INTEREST_DECLARED,
    CERTIFICATE_C: OWNERSHIP_PARTIAL_IDENTIFICATION,
    CERTIFICATE_D: OWNERSHIP_NOT_FULLY_KNOWN,
}

# --- Evidence-coverage states (Section 12 - "explicit evidence coverage") --
COVERAGE_SEARCHED_NO_INDICATION_FOUND = "RELEVANT_EVIDENCE_SEARCHED_NO_CONTROL_INDICATION_FOUND"
COVERAGE_INDICATION_FOUND = "RELEVANT_EVIDENCE_SEARCHED_INDICATION_FOUND"
COVERAGE_INSUFFICIENT = "INSUFFICIENT_EVIDENCE_TO_DETERMINE_CONTROL"


@dataclass(frozen=True)
class OwnershipEvidenceFact:
    """One ownership-related fact, evidence-specific per the Acquisition
    Intelligence Architecture Amendment - never a stronger inference than
    the cited evidence actually supports."""
    state: str  # one of the OWNERSHIP_* constants above
    entity_name: str | None
    entity_type: str  # company | individual | unknown
    company_id: int | None
    confidence: str  # medium | high - source-native, never averaged
    application_id: int | None
    site_id: int | None
    evidence_document_id: int | None
    evidence_snippet: str | None
    source: str  # "certificate_a" | "certificate_b" | "certificate_c" | "certificate_d" | "s106"
    recorded_review_status: str | None = None  # from a matching persisted ControlRelationship row, if any


@dataclass(frozen=True)
class ApplicantPositionFact:
    """The applicant position for one Application in the family."""
    application_id: int
    raw_applicant_name: str | None
    resolved_identity_ref: str | None  # ApplicantIdentity.ref, e.g. "company:42" or "name:abc"
    applicant_intelligence_primary_type: str | None
    applicant_intelligence_confidence: str | None
    is_spv: str | None  # TRUE | FALSE | UNKNOWN | None (no ApplicantIntelligence row)
    parent_group: dict | None
    unresolved_questions: tuple[str, ...]
    applicant_intelligence_available: bool


@dataclass(frozen=True)
class DeveloperIndicationFact:
    """One developer-name candidate, kept separate per source - never
    collapsed to 'the' developer by picking the most recent/complete row
    (Section K of the approved implementation prompt)."""
    application_id: int
    developer_name: str
    source: str  # "scheme_intelligence.developer" | "scheme_intelligence.applicant_company" | "s106_defined_developer" | "applicant_intelligence"


@dataclass(frozen=True)
class ControlRelationshipFact:
    """A relevant, already-persisted ControlRelationship row, surfaced
    for its own review_status/human-confirmation/company_id value."""
    role: str
    entity_name: str
    entity_type: str
    company_id: int | None
    confidence: str | None
    evidence_basis: str
    evidence_category: str
    evidence_document_id: int | None
    evidence_snippet: str | None
    application_id: int | None
    site_id: int | None
    review_status: str
    title_number: str | None


@dataclass(frozen=True)
class EvidenceCoverage:
    """Explicit, transparent coverage facts (Section 12) - never a generic
    numeric coverage score. Distinguishes 'relevant evidence searched, no
    indication found' from 'insufficient evidence/coverage to determine
    control' (Section 13's own 'absence of evidence != evidence of
    absence')."""
    ownership_certificate_documents_present: bool
    s106_documents_present: bool
    applicant_name_raw_available: bool
    scheme_intelligence_available: bool
    applicant_intelligence_available: bool
    company_enrichment_available: bool  # an ApplicationCompany/Company link exists for this family
    persisted_control_relationship_exists: bool


@dataclass(frozen=True)
class AcquisitionPositionFacts:
    site_id: int | None
    application_ids: tuple[int, ...]
    ownership_evidence: tuple[OwnershipEvidenceFact, ...]
    applicant_positions: tuple[ApplicantPositionFact, ...]
    developer_indications: tuple[DeveloperIndicationFact, ...]
    control_relationships: tuple[ControlRelationshipFact, ...]
    # Deliberately NO coarse summary field here (e.g. "control_position") -
    # Product Owner decision, Gate 2C V1 amendment: compressing ownership
    # evidence, applicant position, developer indication and control/
    # third-party relationships into one summary risks overstating what
    # the evidence establishes (a developer/applicant indication does not
    # establish developer CONTROL; an absence of relationships does not
    # establish that control is genuinely unknown in a legally meaningful
    # sense). The detailed fact lists above ARE the trusted source of
    # truth - a consumer reads them directly, never a derived label.
    ownership_coverage: str  # one of the COVERAGE_* constants
    conflicts: tuple[str, ...]
    evidence_coverage: EvidenceCoverage


def _company_entity_type_for(session: Session, name: str, known_entity_type: str | None) -> tuple[str, int | None]:
    """Mirrors app.enrichment.control_population._persist_or_preview's own
    (fixed) logic exactly - READ ONLY here (never writes/creates a Company
    row). known_entity_type='company' is retained even when no existing
    Company row matches (Gate 2C V1 entity-type fix); 'individual' is
    never looked up against Companies House at all."""
    if known_entity_type == "individual":
        return "individual", None
    company = resolve_existing_company(session, name)
    if company is not None:
        return "company", company.id
    if known_entity_type == "company":
        return "company", None
    return "unknown", None


def _ownership_facts_for_application(session: Session, app: Application) -> list[OwnershipEvidenceFact]:
    facts: list[OwnershipEvidenceFact] = []
    forms = [d for d in app.documents if d.doc_type == "application_form" and d.extracted_text]
    for doc in forms:
        result = detect_ownership_certificate(doc)
        if result is None or result.certificate_type in (NO_CERTIFICATE_EVIDENCE, CERTIFICATE_UNKNOWN):
            continue
        identity = resolve_certificate_a_applicant_identity(doc, app)
        if identity.method == "unresolved":
            continue
        entity_type, company_id = _company_entity_type_for(session, identity.resolved_name, identity.entity_type)
        facts.append(OwnershipEvidenceFact(
            state=_CERTIFICATE_TO_OWNERSHIP_STATE[result.certificate_type],
            entity_name=identity.resolved_name, entity_type=entity_type, company_id=company_id,
            confidence="medium", application_id=app.id, site_id=app.site_id,
            evidence_document_id=doc.id,
            evidence_snippet=f"{result.snippet or ''} | applicant identity: {identity.snippet or ''}",
            source=result.certificate_type.lower(),
        ))

    s106_docs = [d for d in app.documents if d.doc_type == "s106" and d.extracted_text]
    for doc in s106_docs:
        titles = extract_s106_title_numbers(doc)
        owner_title = titles[0].title_number if titles else None
        for hit in extract_s106_defined_parties(doc):
            if hit.role != "OWNER":
                continue
            entity_type, company_id = _company_entity_type_for(session, hit.entity_name_raw, None)
            facts.append(OwnershipEvidenceFact(
                state=OWNERSHIP_S106_DEFINED_OWNER, entity_name=hit.entity_name_raw,
                entity_type=entity_type, company_id=company_id, confidence="high",
                application_id=app.id, site_id=app.site_id, evidence_document_id=doc.id,
                evidence_snippet=hit.snippet + (f" | title: {owner_title}" if owner_title else ""),
                source="s106",
            ))
    return facts


def _developer_indications_for_application(app: Application) -> list[DeveloperIndicationFact]:
    facts: list[DeveloperIndicationFact] = []
    si = app.scheme_intelligence
    if si is not None:
        if si.developer:
            facts.append(DeveloperIndicationFact(app.id, si.developer, "scheme_intelligence.developer"))
        if si.applicant_company:
            facts.append(DeveloperIndicationFact(app.id, si.applicant_company, "scheme_intelligence.applicant_company"))
    for doc in app.documents:
        if doc.doc_type != "s106" or not doc.extracted_text:
            continue
        for hit in extract_s106_defined_parties(doc):
            if hit.role == "DEVELOPER":
                facts.append(DeveloperIndicationFact(app.id, hit.entity_name_raw, "s106_defined_developer"))
    return facts


def _third_party_control_facts_for_application(app: Application) -> list[OwnershipEvidenceFact]:
    """S106 MORTGAGEE hits - genuine third-party control evidence, never an
    ownership fact and never a developer indication."""
    facts: list[OwnershipEvidenceFact] = []
    for doc in app.documents:
        if doc.doc_type != "s106" or not doc.extracted_text:
            continue
        for hit in extract_s106_defined_parties(doc):
            if hit.role != "MORTGAGEE":
                continue
            facts.append(OwnershipEvidenceFact(
                state="S106_DEFINED_MORTGAGEE", entity_name=hit.entity_name_raw, entity_type="unknown",
                company_id=None, confidence="high", application_id=app.id, site_id=app.site_id,
                evidence_document_id=doc.id, evidence_snippet=hit.snippet, source="s106",
            ))
    return facts


def _applicant_position_for_application(session: Session, app: Application) -> ApplicantPositionFact:
    si = app.scheme_intelligence
    candidates = best_organisation_name_candidates(
        si_applicant_company=si.applicant_company if si else None,
        si_developer=si.developer if si else None,
        raw_applicant_name=app.applicant_name_raw,
    )
    identity_ref = None
    ai_row: ApplicantIntelligence | None = None
    if candidates:
        identity = resolve_applicant_identity(session, candidates[0])
        if identity is not None:
            identity_ref = identity.ref
            if identity.company_id is not None:
                ai_row = session.execute(
                    select(ApplicantIntelligence).where(ApplicantIntelligence.company_id == identity.company_id)
                ).scalar_one_or_none()
            elif identity.identity_key is not None:
                ai_row = session.execute(
                    select(ApplicantIntelligence).where(ApplicantIntelligence.identity_key == identity.identity_key)
                ).scalar_one_or_none()

    parent_group = None
    unresolved_questions: tuple[str, ...] = ()
    if ai_row is not None and ai_row.parent_group:
        try:
            parent_group = json.loads(ai_row.parent_group)
        except (ValueError, TypeError):
            parent_group = None
    if ai_row is not None and ai_row.unresolved_questions:
        try:
            unresolved_questions = tuple(json.loads(ai_row.unresolved_questions))
        except (ValueError, TypeError):
            unresolved_questions = ()

    return ApplicantPositionFact(
        application_id=app.id, raw_applicant_name=app.applicant_name_raw, resolved_identity_ref=identity_ref,
        applicant_intelligence_primary_type=ai_row.primary_type if ai_row else None,
        applicant_intelligence_confidence=ai_row.primary_type_confidence if ai_row else None,
        is_spv=ai_row.is_spv if ai_row else None,
        parent_group=parent_group, unresolved_questions=unresolved_questions,
        applicant_intelligence_available=ai_row is not None,
    )


def build_acquisition_position_facts(session: Session, applications: list[Application]) -> AcquisitionPositionFacts:
    """The one entry point. `applications` should be the relevant
    application family for one Site (or a single application's own list,
    for a strategic-land/no-Site-yet case) - callers decide scope; this
    function never re-derives site linkage itself (Section 11 of the
    approved implementation prompt: 'where evidence cannot safely be
    attributed to the wider site, retain narrower application scope' -
    this function trusts whatever list it is given, exactly as
    build_operative_planning_facts already does for planning facts).

    Never imports BuyerProfile or any buyer-specific module - the returned
    facts are reusable, unmodified, by every future buyer type."""
    if not applications:
        return AcquisitionPositionFacts(
            site_id=None, application_ids=(), ownership_evidence=(), applicant_positions=(),
            developer_indications=(), control_relationships=(),
            ownership_coverage=COVERAGE_INSUFFICIENT, conflicts=(),
            evidence_coverage=EvidenceCoverage(False, False, False, False, False, False, False),
        )

    site_ids = {a.site_id for a in applications if a.site_id is not None}
    site_id = next(iter(site_ids)) if len(site_ids) == 1 else None
    app_ids = tuple(a.id for a in applications)

    ownership_evidence: list[OwnershipEvidenceFact] = []
    developer_indications: list[DeveloperIndicationFact] = []
    applicant_positions: list[ApplicantPositionFact] = []
    for app in applications:
        ownership_evidence.extend(_ownership_facts_for_application(session, app))
        ownership_evidence.extend(_third_party_control_facts_for_application(app))
        developer_indications.extend(_developer_indications_for_application(app))
        applicant_positions.append(_applicant_position_for_application(session, app))

    scope_filters = [ControlRelationship.application_id.in_(app_ids)]
    if site_id is not None:
        scope_filters.append(ControlRelationship.site_id == site_id)
    recorded = session.execute(
        select(ControlRelationship).where(or_(*scope_filters))
    ).scalars().all()
    control_relationships = tuple(
        ControlRelationshipFact(
            role=r.role, entity_name=r.entity_name_raw, entity_type=r.entity_type, company_id=r.company_id,
            confidence=r.confidence, evidence_basis=r.evidence_basis, evidence_category=r.evidence_category,
            evidence_document_id=r.evidence_document_id, evidence_snippet=r.evidence_snippet,
            application_id=r.application_id, site_id=r.site_id, review_status=r.review_status,
            title_number=r.title_number,
        )
        for r in recorded
    )

    # Conflicts (Section P / F): distinct developer names, distinct
    # ownership-declaring entities, or a persisted ControlRelationship at
    # needs_confirmation - surfaced explicitly, never silently resolved.
    conflicts: list[str] = []
    developer_names = {d.developer_name.strip().lower() for d in developer_indications if d.developer_name}
    if len(developer_names) > 1:
        conflicts.append(
            "Conflicting developer/applicant-company evidence across sources: "
            + ", ".join(sorted({d.developer_name for d in developer_indications if d.developer_name}))
        )
    owner_declared_names = {
        f.entity_name.strip().lower() for f in ownership_evidence
        if f.entity_name and f.state in (OWNERSHIP_APPLICANT_DECLARED_SOLE_OWNER, OWNERSHIP_S106_DEFINED_OWNER)
    }
    if len(owner_declared_names) > 1:
        conflicts.append(
            "Conflicting ownership-declaration evidence across sources: "
            + ", ".join(sorted({f.entity_name for f in ownership_evidence if f.entity_name and f.state in (OWNERSHIP_APPLICANT_DECLARED_SOLE_OWNER, OWNERSHIP_S106_DEFINED_OWNER)}))
        )
    for r in control_relationships:
        if r.review_status == "needs_confirmation":
            conflicts.append(f"Unresolved competing evidence recorded for role={r.role}, entity={r.entity_name!r} (needs_confirmation).")

    # Evidence coverage (Section 12/13).
    ownership_docs_present = any(d.doc_type == "application_form" and d.extracted_text for a in applications for d in a.documents)
    s106_docs_present = any(d.doc_type == "s106" and d.extracted_text for a in applications for d in a.documents)
    scheme_intelligence_available = any(a.scheme_intelligence is not None for a in applications)
    applicant_name_raw_available = any(a.applicant_name_raw for a in applications)
    applicant_intelligence_available = any(p.applicant_intelligence_available for p in applicant_positions)
    company_enrichment_available = any(f.company_id is not None for f in ownership_evidence) or any(
        r.company_id is not None for r in control_relationships
    )
    evidence_coverage = EvidenceCoverage(
        ownership_certificate_documents_present=ownership_docs_present,
        s106_documents_present=s106_docs_present,
        applicant_name_raw_available=applicant_name_raw_available,
        scheme_intelligence_available=scheme_intelligence_available,
        applicant_intelligence_available=applicant_intelligence_available,
        company_enrichment_available=company_enrichment_available,
        persisted_control_relationship_exists=len(control_relationships) > 0,
    )
    if not ownership_docs_present and not s106_docs_present:
        ownership_coverage = COVERAGE_INSUFFICIENT
    elif ownership_evidence:
        ownership_coverage = COVERAGE_INDICATION_FOUND
    else:
        ownership_coverage = COVERAGE_SEARCHED_NO_INDICATION_FOUND

    return AcquisitionPositionFacts(
        site_id=site_id, application_ids=app_ids,
        ownership_evidence=tuple(ownership_evidence), applicant_positions=tuple(applicant_positions),
        developer_indications=tuple(developer_indications), control_relationships=control_relationships,
        ownership_coverage=ownership_coverage,
        conflicts=tuple(conflicts), evidence_coverage=evidence_coverage,
    )
