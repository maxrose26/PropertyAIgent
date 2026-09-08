"""Gate 2A ("Applicant Intelligence") - "who is behind this planning
application or scheme, and in what commercial capacity" as a reusable,
ENTITY-level classification, layered over app.reporting.applicant_identity's
own identity resolution.

Same grounded-facts-then-narrate/classify architecture as app.reporting.
allocation_intelligence_summary (this module's direct structural precedent -
reused deliberately, not reinvented):

  trusted database facts (Application/SchemeIntelligence/Company/
  ApplicationCompany/ControlRelationship, entity-resolved by
  app.reporting.applicant_identity)
    -> ApplicantIdentityContext (this module, pure, no OpenAI)
    -> OpenAI structured generation (this module, gated by a fingerprint)
    -> deterministic grounding validation (this module, rejects ungrounded
       output - an evidence_ref the model cites that was never offered in
       context is rejected, exactly like allocation_intelligence_summary's
       own referenced_applications/referenced_entities mechanism)
    -> persisted on ApplicantIntelligence, a DEDICATED, GLOBAL table keyed
       by resolved identity (see that model's own class docstring)
    -> customer-facing UI (Opportunity Profile / Scheme Detail, read-only)

THIS IS NOT THE ACQUISITION AGENT (Gate 2A Section 3) - a bounded, single-
entity classification/enrichment capability, reusing this platform's own
already-proven "structured context -> fingerprint -> Responses API ->
grounded validation -> persist -> reuse" pattern. No autonomous reasoning,
no tool loop, no buyer-specific judgement.

CRITICAL SAFETY BOUNDARIES (Gate 2A Section 13, enforced in
validate_applicant_intelligence_output below): this module's own output
must never assert (nor may its "summary" field imply) that a site is for
sale, that an applicant owns anything solely by virtue of being the
applicant, that a promoter will sell after permission, or that an
opportunity exists solely from a role classification. Role and control
evidence stay separately reported (Gate 2A Section 14) - never flattened
into one commercial claim.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Application, ApplicantIntelligence, ApplicationCompany, Company, ControlRelationship, Site
from app.pipeline.material_change import (
    STATE_GRANTED, STATE_REFUSED, STATE_WITHDRAWN, _classify_planning_state,
)
from app.reporting.applicant_identity import (
    ApplicantIdentity, IDENTITY_COMPANY, clean_organisation_name, resolve_applicant_identity,
)
from app.reporting.opportunity_universe import build_current_opportunity_universe

MODEL = "gpt-4o-mini"  # matches every other OpenAI call already made across this codebase - no new model introduced (Gate 2A Section 17)
PROMPT_VERSION = "applicant-intelligence-v1"

# Gate 2A Section 9 - multiple roles may genuinely apply; UNKNOWN is a valid,
# desirable output when evidence cannot support any commercial-role claim
# (Section 11) - never rewarded for guessing.
ROLE_HOUSEBUILDER = "HOUSEBUILDER"
ROLE_LAND_PROMOTER = "LAND_PROMOTER"
ROLE_HOUSING_ASSOCIATION = "HOUSING_ASSOCIATION"
ROLE_LANDOWNER_PRIVATE = "LANDOWNER_PRIVATE"
ROLE_PUBLIC_SECTOR = "PUBLIC_SECTOR"
ROLE_CONSULTANT_AGENT = "CONSULTANT_AGENT"
ROLE_DEVELOPER = "DEVELOPER"
ROLE_OTHER = "OTHER"
ROLE_UNKNOWN = "UNKNOWN"
ROLE_TAXONOMY = (
    ROLE_HOUSEBUILDER, ROLE_LAND_PROMOTER, ROLE_HOUSING_ASSOCIATION, ROLE_LANDOWNER_PRIVATE,
    ROLE_PUBLIC_SECTOR, ROLE_CONSULTANT_AGENT, ROLE_DEVELOPER, ROLE_OTHER, ROLE_UNKNOWN,
)
CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW = "HIGH", "MEDIUM", "LOW"
CONFIDENCE_LEVELS = (CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW)
SPV_TRUE, SPV_FALSE, SPV_UNKNOWN = "TRUE", "FALSE", "UNKNOWN"
SPV_STATUSES = (SPV_TRUE, SPV_FALSE, SPV_UNKNOWN)

# Gate 2A Section 13 - a narrow, deliberately literal lexical safety net over
# the one free-text field this schema has (summary) - mirrors app.reporting.
# allocation_intelligence_summary's own acknowledged "mitigation, not a
# structural guarantee" precedent (see that module's own PROMPT_VERSION
# history, v7). The structured fields (roles/is_spv/parent_group) cannot
# express these claims at all by construction - this only guards the one
# field where free prose could smuggle one in.
_BANNED_SUMMARY_PHRASES = (
    "for sale", "available for", "will sell", "wants to sell", "likely to sell",
    "owns the site", "owns this site", "acquisition opportunity", "promoter opportunity",
    "likely to become available", "site is available", "land is available",
)


@dataclass
class ApplicationOccurrence:
    """One trusted fact: this identity was named (as applicant or developer)
    on this specific Application. `source_field` records exactly which
    platform field produced the name - never presented as more authoritative
    than it is (Gate 2A pre-implementation audit: SchemeIntelligence.
    applicant_company/.developer are extracted by this platform's EXISTING
    document-intelligence pipeline from planning documents, not a raw portal
    scrape; Application.applicant_name_raw IS a raw portal scrape, but is
    frequently a private individual rather than the organisation, which is
    exactly why an individual-shaped name is filtered out before it ever
    reaches this dataclass - see app.reporting.applicant_identity.
    clean_organisation_name)."""
    reference: str
    source_field: str  # "scheme_intelligence.applicant_company" | "scheme_intelligence.developer" | "application.applicant_name_raw"
    site_id: int
    site_label: str
    council_code: str
    application_category: str | None
    status: str | None
    decision: str | None
    planning_state: str  # app.pipeline.material_change._classify_planning_state's own bucket - reused, never re-derived
    is_opportunity_candidate: bool
    opportunity_kind: str | None  # "long_pending_application" | "recent_permission" | "site" | "phase" | None


@dataclass
class CompanyEvidence:
    ch_company_number: str | None
    ch_status: str | None
    ch_incorporation_date: str | None
    verified_domain: str | None
    linkedin_url: str | None


@dataclass
class ControlEvidenceEntry:
    site_label: str
    role: str  # ControlRelationship's OWN role vocabulary (OWNER/MORTGAGEE/...) - NEVER conflated with this module's commercial-role taxonomy above (Gate 2A Section 14)
    evidence_basis: str
    confidence: str | None


@dataclass
class ApplicantIdentityContext:
    """The bounded, deterministic payload the model is given - every field
    is already a short, discrete, already-verified fact or count. Never
    includes raw document text. Built by build_applicant_identity_contexts,
    never constructed directly."""
    identity_ref: str
    identity_type: str
    display_name: str
    raw_name_variants: list[str] = field(default_factory=list)
    company_evidence: CompanyEvidence | None = None
    occurrences: list[ApplicationOccurrence] = field(default_factory=list)
    control_evidence: list[ControlEvidenceEntry] = field(default_factory=list)

    # Deterministic repeated-behaviour facts (Gate 2A Section 26) - facts,
    # never a speculative label. "12 applications across Greater Manchester"
    # is a fact this dataclass carries; "therefore a land promoter" is only
    # ever the model's OWN separately-grounded role classification.
    @property
    def application_count(self) -> int:
        return len({o.reference for o in self.occurrences})

    @property
    def site_count(self) -> int:
        return len({o.site_id for o in self.occurrences})

    @property
    def authorities(self) -> list[str]:
        return sorted({o.council_code for o in self.occurrences})

    @property
    def granted_count(self) -> int:
        return len({o.reference for o in self.occurrences if o.planning_state == STATE_GRANTED})

    @property
    def refused_or_withdrawn_count(self) -> int:
        return len({o.reference for o in self.occurrences if o.planning_state in (STATE_REFUSED, STATE_WITHDRAWN)})

    @property
    def pending_count(self) -> int:
        decided = {STATE_GRANTED, STATE_REFUSED, STATE_WITHDRAWN}
        return len({o.reference for o in self.occurrences if o.planning_state not in decided})

    @property
    def opportunity_candidate_kinds(self) -> list[str]:
        return sorted({o.opportunity_kind for o in self.occurrences if o.is_opportunity_candidate and o.opportunity_kind})


# --- Batched context construction (one pass over the whole platform) -------


def _occurrence_role_sources(app_row: Application) -> list[tuple[str, str]]:
    """(source_field, raw_name) pairs for ONE Application - see
    best_organisation_name_candidates' own docstring for the trust order.
    Deliberately keeps applicant_company/developer/applicant_name_raw as up
    to 3 INDEPENDENT candidates rather than collapsing to one "best" name -
    an applicant and a developer are commonly genuinely different
    organisations and must resolve to separate identities."""
    si = app_row.scheme_intelligence
    si_applicant = si.applicant_company if si else None
    si_developer = si.developer if si else None
    raw = app_row.applicant_name_raw
    pairs: list[tuple[str, str]] = []
    if clean_organisation_name(si_applicant):
        pairs.append(("scheme_intelligence.applicant_company", clean_organisation_name(si_applicant)))
    if clean_organisation_name(si_developer):
        cleaned = clean_organisation_name(si_developer)
        if cleaned not in (p[1] for p in pairs):
            pairs.append(("scheme_intelligence.developer", cleaned))
    if clean_organisation_name(raw):
        cleaned = clean_organisation_name(raw)
        if cleaned not in (p[1] for p in pairs):
            pairs.append(("application.applicant_name_raw", cleaned))
    return pairs


def build_applicant_identity_contexts(session: Session) -> dict[str, ApplicantIdentityContext]:
    """READ ONLY - ONE batched pass over every site-linked Application
    (with its SchemeIntelligence eager-loaded) plus every ControlRelationship
    row, resolving each distinct raw name to its identity via
    app.reporting.applicant_identity (cached per raw string within this
    call, so resolve_existing_company's own O(existing Company rows) scan
    runs once per distinct string, never once per Application). Returns
    every identity found ANYWHERE on the platform, keyed by ApplicantIdentity.ref
    - bounded to a few hundred distinct organisations at current platform
    scale (Gate 2A pre-implementation audit: 434 unique SchemeIntelligence.
    applicant_company strings + 237 unique Application.applicant_name_raw
    strings), a cheap pure-DB-read pass with no AI call. Callers needing
    only a PRIORITISED subset (Gate 2A Section 24) filter this dict's own
    occurrences.is_opportunity_candidate/opportunity_kind - see
    select_priority_identity_refs below."""
    apps = session.execute(
        select(Application).where(Application.site_id.is_not(None))
        .options(selectinload(Application.scheme_intelligence))
    ).scalars().all()
    sites_by_id = {s.id: s for s in session.execute(select(Site)).scalars()}

    universe = build_current_opportunity_universe(session)
    candidate_kind_by_site: dict[int, str] = {}
    for r in universe:
        if r.opportunity_type == "strategic_land":
            continue
        parts = r.opportunity_id.split(":")
        kind = parts[1]
        if len(parts) > 2 and parts[2].isdigit():
            # A more-specific kind (recent_permission/long_pending_application)
            # is never overwritten by a less-specific one seen later - in
            # practice each site appears under at most one kind anyway
            # (Gate 1C's own precedence/dedup guarantee), this is just a
            # defensive tie-break, never load-bearing.
            candidate_kind_by_site.setdefault(int(parts[2]), kind)

    identity_cache: dict[str, ApplicantIdentity | None] = {}

    def _resolve(raw_name: str) -> ApplicantIdentity | None:
        if raw_name not in identity_cache:
            identity_cache[raw_name] = resolve_applicant_identity(session, raw_name)
        return identity_cache[raw_name]

    contexts: dict[str, ApplicantIdentityContext] = {}

    def _get_or_create(identity: ApplicantIdentity) -> ApplicantIdentityContext:
        ctx = contexts.get(identity.ref)
        if ctx is None:
            ctx = ApplicantIdentityContext(
                identity_ref=identity.ref, identity_type=identity.identity_type, display_name=identity.display_name,
            )
            contexts[identity.ref] = ctx
        if identity.raw_name not in ctx.raw_name_variants:
            ctx.raw_name_variants.append(identity.raw_name)
        return ctx

    for app_row in apps:
        site = sites_by_id.get(app_row.site_id)
        if site is None:
            continue
        planning_state = _classify_planning_state(app_row.decision, app_row.status)
        kind = candidate_kind_by_site.get(site.id)
        for source_field, raw_name in _occurrence_role_sources(app_row):
            identity = _resolve(raw_name)
            if identity is None:
                continue
            ctx = _get_or_create(identity)
            ctx.occurrences.append(ApplicationOccurrence(
                reference=app_row.reference, source_field=source_field,
                site_id=site.id, site_label=site.display_address, council_code=site.council_code,
                application_category=app_row.application_category, status=app_row.status, decision=app_row.decision,
                planning_state=planning_state, is_opportunity_candidate=kind is not None, opportunity_kind=kind,
            ))

    # Company evidence - one lookup per company-type identity (bounded: at
    # most len(contexts) companies, and Company itself has ~19 rows at
    # current platform scale).
    company_ids = {ctx.identity_ref.split(":", 1)[1] for ctx in contexts.values() if ctx.identity_type == IDENTITY_COMPANY}
    companies_by_id = {}
    if company_ids:
        companies_by_id = {
            c.id: c for c in session.execute(select(Company).where(Company.id.in_([int(i) for i in company_ids]))).scalars()
        }
    for ctx in contexts.values():
        if ctx.identity_type == IDENTITY_COMPANY:
            company = companies_by_id.get(int(ctx.identity_ref.split(":", 1)[1]))
            if company is not None:
                ctx.company_evidence = CompanyEvidence(
                    ch_company_number=company.ch_company_number, ch_status=company.ch_status,
                    ch_incorporation_date=company.ch_incorporation_date,
                    verified_domain=company.verified_domain, linkedin_url=company.linkedin_url,
                )

    # Control evidence - resolved through the SAME identity mechanism as
    # Applicant/Developer names above (Gate 2A Section 15/16), so a
    # Certificate A declaration naming the same organisation attaches to
    # the SAME identity, never a second parallel lookup.
    control_rows = session.execute(select(ControlRelationship)).scalars().all()
    for cr in control_rows:
        identity: ApplicantIdentity | None = None
        if cr.company_id is not None:
            company = companies_by_id.get(cr.company_id) or session.get(Company, cr.company_id)
            if company is not None:
                identity = ApplicantIdentity(
                    identity_type=IDENTITY_COMPANY, raw_name=cr.entity_name_raw,
                    company_id=company.id, company_display_name=company.name_raw,
                )
        else:
            identity = _resolve(cr.entity_name_raw)
        if identity is None or identity.ref not in contexts:
            # Gate 2A Section 15 - Certificate A/S106 evidence for an
            # organisation this pass never otherwise saw as an applicant/
            # developer is real, but out of THIS run's scope (no
            # Application-occurrence context exists to classify it
            # against) - never silently attached to the wrong identity.
            continue
        ctx = contexts[identity.ref]
        site_id = cr.site_id
        if site_id is None and cr.application_id is not None:
            linked_app = session.get(Application, cr.application_id)
            site_id = linked_app.site_id if linked_app else None
        site = sites_by_id.get(site_id) if site_id is not None else None
        site_label = site.display_address if site is not None else "Unknown Site"
        ctx.control_evidence.append(ControlEvidenceEntry(
            site_label=site_label, role=cr.role, evidence_basis=cr.evidence_basis, confidence=cr.confidence,
        ))

    return contexts


def select_priority_identity_refs(contexts: dict[str, ApplicantIdentityContext], *, limit: int) -> list[str]:
    """Gate 2A Section 24 - priority order: entities touching a
    long_pending_application candidate first, then recent_permission, then
    any other planning-delivery candidate, then (lowest) everything else on
    the platform. Deterministic tie-break (identity_ref) so repeated runs
    with an unchanged backlog select the same identities, never an
    arbitrary dict-iteration order."""
    def _priority(ctx: ApplicantIdentityContext) -> tuple[int, str]:
        kinds = set(ctx.opportunity_candidate_kinds)
        if "long_pending_application" in kinds:
            band = 0
        elif "recent_permission" in kinds:
            band = 1
        elif kinds:
            band = 2
        else:
            band = 3
        return (band, ctx.identity_ref)

    ordered = sorted(contexts.values(), key=_priority)
    return [ctx.identity_ref for ctx in ordered[:limit]]


# --- Fingerprint / staleness (mirrors app.reporting.allocation_intelligence_summary) --


def compute_context_fingerprint(context: ApplicantIdentityContext) -> str:
    """sha256 over only the classification-relevant portion of the context -
    same reasoning as allocation_intelligence_summary.compute_context_
    fingerprint. Deliberately excludes nothing time-based (this context
    carries no dates/timestamps of its own) - every field here is already
    narrative-material, so no exclusion list is needed the way the
    allocation module's last_checked/source_document_url were."""
    fingerprint_source = {
        "identity_type": context.identity_type,
        "raw_name_variants": sorted(context.raw_name_variants),
        "company_evidence": (
            {
                "ch_company_number": context.company_evidence.ch_company_number,
                "ch_status": context.company_evidence.ch_status,
                "ch_incorporation_date": context.company_evidence.ch_incorporation_date,
                "verified_domain": context.company_evidence.verified_domain,
                "linkedin_url": context.company_evidence.linkedin_url,
            } if context.company_evidence else None
        ),
        "occurrences": sorted([
            {
                "reference": o.reference, "source_field": o.source_field, "site_id": o.site_id,
                "application_category": o.application_category, "planning_state": o.planning_state,
            }
            for o in context.occurrences
        ], key=lambda d: (d["reference"], d["source_field"])),
        "control_evidence": sorted([
            {"site_label": c.site_label, "role": c.role, "evidence_basis": c.evidence_basis, "confidence": c.confidence}
            for c in context.control_evidence
        ], key=lambda d: (d["site_label"], d["role"], d["evidence_basis"])),
    }
    canonical = json.dumps(fingerprint_source, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_applicant_intelligence(session: Session, identity_ref: str) -> ApplicantIntelligence | None:
    identity_type, key = identity_ref.split(":", 1)
    if identity_type == IDENTITY_COMPANY:
        return session.execute(
            select(ApplicantIntelligence).where(ApplicantIntelligence.company_id == int(key))
        ).scalar_one_or_none()
    return session.execute(
        select(ApplicantIntelligence).where(ApplicantIntelligence.identity_key == key)
    ).scalar_one_or_none()


def should_regenerate(existing: ApplicantIntelligence | None, fingerprint: str, *, force: bool = False) -> bool:
    """Gate 2A Section 20 - identical trigger set to allocation_intelligence_
    summary.should_regenerate_allocation_summary: an explicit force, never
    generated before, the trusted context has genuinely changed, or the
    prompt/model version has moved on. Nothing else."""
    if force:
        return True
    if existing is None or existing.roles is None:
        return True
    if existing.context_fingerprint != fingerprint:
        return True
    if existing.prompt_version != PROMPT_VERSION:
        return True
    return False


# --- Prompt / structured schema (Gate 2A Sections 9-18) ---------------------


def _evidence_ref_for_occurrence(o: ApplicationOccurrence) -> str:
    return f"occurrence:{o.reference}"


def _company_evidence_refs(ce: CompanyEvidence) -> list[str]:
    refs = []
    if ce.ch_company_number:
        refs.append("company:ch_company_number")
    if ce.ch_status:
        refs.append("company:ch_status")
    if ce.ch_incorporation_date:
        refs.append("company:ch_incorporation_date")
    if ce.verified_domain:
        refs.append("company:verified_domain")
    if ce.linkedin_url:
        refs.append("company:linkedin_url")
    return refs


def _control_evidence_ref(i: int) -> str:
    return f"control:{i}"


def allowed_evidence_refs(context: ApplicantIdentityContext) -> set[str]:
    """The COMPLETE whitelist of evidence_ref strings the model may cite -
    anything else is a hallucinated reference and rejected outright (Gate
    2A Section 19: "the AI must not be able to cite evidence that was not
    provided in its context")."""
    refs: set[str] = {_evidence_ref_for_occurrence(o) for o in context.occurrences}
    refs.add("fact:application_count")
    refs.add("fact:site_count")
    refs.add("fact:authorities")
    refs.add("fact:granted_count")
    refs.add("fact:pending_count")
    refs.add("fact:refused_or_withdrawn_count")
    for name in context.raw_name_variants:
        refs.add(f"raw_name:{name}")
    if context.company_evidence:
        refs.update(_company_evidence_refs(context.company_evidence))
    for i in range(len(context.control_evidence)):
        refs.add(_control_evidence_ref(i))
    return refs


def _render_occurrence(o: ApplicationOccurrence) -> str:
    candidate_bit = f" [CURRENT OPPORTUNITY CANDIDATE - {o.opportunity_kind}]" if o.is_opportunity_candidate else ""
    return (
        f"- [{_evidence_ref_for_occurrence(o)}] Site \"{o.site_label}\" ({o.council_code}), named via {o.source_field}, "
        f"planning state: {o.planning_state}, category: {o.application_category or 'not categorised'}{candidate_bit}"
    )


def _render_control_entry(i: int, c: ControlEvidenceEntry) -> str:
    return (
        f"- [{_control_evidence_ref(i)}] Site \"{c.site_label}\": role {c.role} "
        f"(evidence basis: {c.evidence_basis}, confidence: {c.confidence or 'not stated'}) - this is SITE-SPECIFIC "
        f"evidence of a stated/apparent relationship to that Site ONLY; it does NOT establish current ownership, "
        f"exclusivity, or that the site is available."
    )


def build_applicant_prompt(context: ApplicantIdentityContext) -> str:
    occurrence_lines = "\n".join(_render_occurrence(o) for o in context.occurrences) or "- No linked Applications identified."
    control_lines = "\n".join(_render_control_entry(i, c) for i, c in enumerate(context.control_evidence)) or (
        "- No site-specific ownership/control evidence currently identified for this organisation."
    )
    company_lines = "- No Companies House / verified company evidence currently identified." if not context.company_evidence else "\n".join(
        f"- [{ref}] {ref.split(':', 1)[1]}: {getattr(context.company_evidence, ref.split(':', 1)[1])}"
        for ref in _company_evidence_refs(context.company_evidence)
    )
    variants_line = ", ".join(context.raw_name_variants)

    return f"""
You are producing a bounded, evidence-only ORGANISATION-LEVEL classification
for Property AIgent, a UK planning-intelligence platform. This is NOT a
commercial recommendation and NOT an acquisition assessment - it is a
reusable identity classification consumed later by separate, buyer-specific
reasoning you have no visibility into.

ORGANISATION: {context.display_name}
IDENTITY: {'A verified, Companies-House-resolved entity' if context.identity_type == 'company' else 'A NAME-BASED identity - no verified company record has been matched; treat corporate-structure claims with LOWER confidence than you would for a verified entity'}
RAW NAME VARIANT(S) SEEN ON THIS PLATFORM: {variants_line} [refs: {', '.join(f'raw_name:{n}' for n in context.raw_name_variants)}]

DETERMINISTIC FACTS (already computed - do not recompute or contradict):
- [fact:application_count] Named on {context.application_count} distinct planning application(s)
- [fact:site_count] across {context.site_count} distinct Site(s)
- [fact:authorities] in {len(context.authorities)} local authorit{'y' if len(context.authorities) == 1 else 'ies'}: {', '.join(context.authorities) or 'none'}
- [fact:granted_count] {context.granted_count} granted
- [fact:pending_count] {context.pending_count} still pending/undetermined
- [fact:refused_or_withdrawn_count] {context.refused_or_withdrawn_count} refused or withdrawn

APPLICATION/SITE OCCURRENCES (each independently evidenced - being named here means ONLY that this name appeared in this exact field on this exact Application, nothing more):
{occurrence_lines}

COMPANIES HOUSE / VERIFIED COMPANY EVIDENCE:
{company_lines}

SITE-SPECIFIC OWNERSHIP/CONTROL EVIDENCE (Gate 2A Section 14 - kept SEPARATE from your own role classification below; never flatten these into one claim):
{control_lines}

RULES - follow every one of these exactly:
1. You may assert MULTIPLE roles for this organisation (e.g. LAND_PROMOTER and DEVELOPER together) if the evidence genuinely supports more than one - never force a single label.
2. Every role you assert (other than UNKNOWN) MUST cite at least one evidence_ref from the refs shown in brackets above - a hallucinated or unlisted ref is an automatic rejection. UNKNOWN needs no evidence_refs and is the correct, expected output when nothing above supports a confident role.
3. Confidence is categorical only: HIGH, MEDIUM, or LOW - never a numeric percentage, never invented precision.
4. is_spv (Special Purpose Vehicle) is a SEPARATE corporate-structure question from role - having "Limited"/"Ltd" in a name is NEVER by itself evidence of SPV status; "Developments" in a name is NEVER by itself evidence of LAND_PROMOTER; "Homes" in a name is NEVER by itself evidence of HOUSEBUILDER. Return UNKNOWN for is_spv unless the evidence above (e.g. a very narrow application/site footprint alongside other signals) genuinely supports TRUE or FALSE.
5. parent_group is null unless the evidence above genuinely names a parent/group relationship - never invented from a name resembling a larger group.
6. NEVER assert, or let your summary imply: that this site or any site above is for sale or available; that this organisation owns any site solely because it is the applicant; that a promoter will sell after permission; that any Application/Site above is an "acquisition opportunity"; that being an applicant establishes ownership, control, or exclusivity. Ownership/control evidence above is SEPARATE, SITE-SPECIFIC evidence - never merge it with your own role classification into a single stronger claim (e.g. never write "promoter-owned site for sale").
7. summary must be plain, evidence-only prose (2-4 sentences) - state only what the facts above actually show; frame genuine gaps as investigation signals, never as a real-world absence (an application with no ownership evidence here means Property AIgent has not identified any, not that none exists).
8. unresolved_questions: 0-3 short, specific open questions the evidence above cannot yet answer (empty list if genuinely none) - never a generic instruction.
9. Every evidence_ref you cite anywhere (roles[].evidence_refs, parent_group.evidence_refs) must be an EXACT string from the bracketed refs shown above - never invent, abbreviate, or paraphrase a ref.
"""


APPLICANT_INTELLIGENCE_SCHEMA = {
    "name": "applicant_intelligence",
    "schema": {
        "type": "object",
        "properties": {
            "roles": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string", "enum": list(ROLE_TAXONOMY)},
                        "confidence": {"type": "string", "enum": list(CONFIDENCE_LEVELS)},
                        "evidence_refs": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["role", "confidence", "evidence_refs"],
                    "additionalProperties": False,
                },
            },
            "is_spv": {"type": "string", "enum": list(SPV_STATUSES)},
            "parent_group": {
                "type": ["object", "null"],
                "properties": {
                    "name": {"type": "string"},
                    "confidence": {"type": "string", "enum": list(CONFIDENCE_LEVELS)},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "confidence", "evidence_refs"],
                "additionalProperties": False,
            },
            "summary": {"type": "string"},
            "unresolved_questions": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["roles", "is_spv", "parent_group", "summary", "unresolved_questions"],
        "additionalProperties": False,
    },
}


# --- Grounding validation (Gate 2A Section 19) ------------------------------


def validate_applicant_intelligence_output(context: ApplicantIdentityContext, structured: dict) -> tuple[bool, list[str]]:
    """Rejects any output citing an evidence_ref not present in
    allowed_evidence_refs(context), any role/confidence/spv_status outside
    the fixed enums (defensive - already enforced by the strict JSON
    schema, but checked again here so this function is a complete,
    independently-correct grounding gate on its own), a non-UNKNOWN role
    with zero evidence_refs, or a summary containing one of the banned
    commercial-overreach phrases (Gate 2A Section 13)."""
    problems: list[str] = []
    allowed = allowed_evidence_refs(context)

    for entry in structured.get("roles", []):
        role = entry.get("role")
        if role not in ROLE_TAXONOMY:
            problems.append(f"role outside taxonomy: {role}")
        if entry.get("confidence") not in CONFIDENCE_LEVELS:
            problems.append(f"confidence outside allowed levels: {entry.get('confidence')}")
        refs = entry.get("evidence_refs", [])
        if role != ROLE_UNKNOWN and not refs:
            problems.append(f"role {role} asserted with no evidence_refs")
        for ref in refs:
            if ref not in allowed:
                problems.append(f"unsupported evidence_ref for role {role}: {ref}")

    if structured.get("is_spv") not in SPV_STATUSES:
        problems.append(f"is_spv outside allowed values: {structured.get('is_spv')}")

    parent_group = structured.get("parent_group")
    if parent_group is not None:
        if parent_group.get("confidence") not in CONFIDENCE_LEVELS:
            problems.append(f"parent_group confidence outside allowed levels: {parent_group.get('confidence')}")
        for ref in parent_group.get("evidence_refs", []):
            if ref not in allowed:
                problems.append(f"unsupported evidence_ref for parent_group: {ref}")

    summary_lower = (structured.get("summary") or "").lower()
    for phrase in _BANNED_SUMMARY_PHRASES:
        if phrase in summary_lower:
            problems.append(f"summary contains a disallowed commercial-overreach phrase: '{phrase}'")

    return (len(problems) == 0, problems)


# --- Orchestration -----------------------------------------------------------


@dataclass
class ApplicantIntelligenceResult:
    regenerated: bool
    rejected: bool
    rejection_reason: list[str] | None
    roles: list[dict] | None
    is_spv: str | None
    parent_group: dict | None
    summary: str | None
    unresolved_questions: list[str] | None
    model: str | None
    prompt_version: str | None
    status: str | None
    generation_error: str | None


def _persisted_result(row: ApplicantIntelligence | None, *, regenerated: bool, rejected: bool, rejection_reason) -> ApplicantIntelligenceResult:
    return ApplicantIntelligenceResult(
        regenerated=regenerated, rejected=rejected, rejection_reason=rejection_reason,
        roles=json.loads(row.roles) if row and row.roles else None,
        is_spv=row.is_spv if row else None,
        parent_group=json.loads(row.parent_group) if row and row.parent_group else None,
        summary=row.summary if row else None,
        unresolved_questions=json.loads(row.unresolved_questions) if row and row.unresolved_questions else None,
        model=row.model if row else None, prompt_version=row.prompt_version if row else None,
        status=row.status if row else None, generation_error=row.generation_error if row else None,
    )


def generate_applicant_intelligence(
    session: Session, client, context: ApplicantIdentityContext, *, force: bool = False,
) -> ApplicantIntelligenceResult:
    """The one orchestration entry point (mirrors generate_allocation_
    intelligence_summary exactly). A rejected (ungrounded) output, or a raw
    client exception, NEVER overwrites the last successful classification -
    only status/generation_error record that the most recent attempt
    failed (Gate 2A Section 19: "if validation fails, retain last known
    good intelligence")."""
    fingerprint = compute_context_fingerprint(context)
    identity_type, key = context.identity_ref.split(":", 1)
    row = get_applicant_intelligence(session, context.identity_ref)

    if not should_regenerate(row, fingerprint, force=force):
        return _persisted_result(row, regenerated=False, rejected=False, rejection_reason=None)

    if row is None:
        row = ApplicantIntelligence(
            identity_type=identity_type,
            company_id=int(key) if identity_type == IDENTITY_COMPANY else None,
            identity_key=key if identity_type != IDENTITY_COMPANY else None,
            display_name=context.display_name,
        )
        session.add(row)
    else:
        row.display_name = context.display_name

    prompt = build_applicant_prompt(context)
    try:
        response = client.responses.create(
            model=MODEL, input=prompt,
            text={"format": {
                "type": "json_schema", "name": APPLICANT_INTELLIGENCE_SCHEMA["name"],
                "schema": APPLICANT_INTELLIGENCE_SCHEMA["schema"], "strict": True,
            }},
        )
        structured = json.loads(response.output_text)
    except Exception as e:
        row.status = "error"
        row.generation_error = str(e)[:2000]
        session.commit()
        return _persisted_result(row, regenerated=False, rejected=False, rejection_reason=None)

    is_valid, problems = validate_applicant_intelligence_output(context, structured)
    if not is_valid:
        row.status = "error"
        row.generation_error = "; ".join(problems)[:2000]
        session.commit()
        return _persisted_result(row, regenerated=False, rejected=True, rejection_reason=problems)

    now = dt.datetime.now(dt.timezone.utc)
    row.roles = json.dumps(structured["roles"])
    row.is_spv = structured["is_spv"]
    row.parent_group = json.dumps(structured["parent_group"]) if structured["parent_group"] else None
    row.summary = structured["summary"]
    row.unresolved_questions = json.dumps(structured["unresolved_questions"])
    row.generated_at = now
    row.context_fingerprint = fingerprint
    row.model = MODEL
    row.prompt_version = PROMPT_VERSION
    row.status = "ok"
    row.generation_error = None
    session.commit()

    return ApplicantIntelligenceResult(
        regenerated=True, rejected=False, rejection_reason=None,
        roles=structured["roles"], is_spv=structured["is_spv"], parent_group=structured["parent_group"],
        summary=structured["summary"], unresolved_questions=structured["unresolved_questions"],
        model=MODEL, prompt_version=PROMPT_VERSION, status="ok", generation_error=None,
    )


def count_pending_applicant_intelligence(session: Session) -> int:
    """How many identities currently need a (re)generation - the same
    should_regenerate trigger process_applicant_intelligence_backlog itself
    uses. NOT a cheap SQL predicate (mirrors app.pipeline.run_weekly.
    count_pending_allocation_summary_refresh's own "no cheap SQL predicate
    exists" reasoning exactly - this must build the full identity index to
    answer it) - callers should only pay this cost once an operator has
    explicitly opted in (see scripts.run_intelligence_processing's own
    enable_applicant_intelligence gate), never on every routine run before
    opt-in."""
    contexts = build_applicant_identity_contexts(session)
    pending = 0
    for context in contexts.values():
        fingerprint = compute_context_fingerprint(context)
        existing = get_applicant_intelligence(session, context.identity_ref)
        if should_regenerate(existing, fingerprint):
            pending += 1
    return pending


def process_applicant_intelligence_backlog(
    session: Session, client_factory, *, limit: int, force: bool = False,
) -> dict:
    """Gate 2A Section 23/24 - the bounded processing entry point a new
    intelligence-processing stage calls. Builds the full deterministic
    identity index (cheap, no AI), selects up to `limit` identities by
    priority (candidate-linked first), and calls the AI ONLY for identities
    whose fingerprint indicates a real, stale/missing classification -
    mirrors app.pipeline.run_weekly's own per-item failure isolation: one
    identity's OpenAI/validation failure never stops the rest of the
    batch."""
    contexts = build_applicant_identity_contexts(session)
    candidate_refs = select_priority_identity_refs(contexts, limit=limit * 3)  # overfetch: some will already be fresh
    client = None
    attempted = succeeded = rejected = failed = skipped_fresh = 0
    for ref in candidate_refs:
        if attempted >= limit:
            break
        context = contexts[ref]
        fingerprint = compute_context_fingerprint(context)
        existing = get_applicant_intelligence(session, ref)
        if not should_regenerate(existing, fingerprint, force=force):
            skipped_fresh += 1
            continue
        if client is None:
            client = client_factory()
        attempted += 1
        try:
            result = generate_applicant_intelligence(session, client, context, force=force)
        except Exception:
            failed += 1
            continue
        if result.rejected:
            rejected += 1
        elif result.regenerated:
            succeeded += 1
    return {
        "identities_considered": len(contexts), "attempted": attempted,
        "succeeded": succeeded, "rejected": rejected, "failed": failed, "skipped_fresh": skipped_fresh,
    }
