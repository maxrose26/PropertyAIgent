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
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Application, ApplicantIntelligence, ApplicationCompany, Company, ControlRelationship, Site
from app.pipeline.material_change import (
    STATE_GRANTED, STATE_REFUSED, STATE_WITHDRAWN, _classify_planning_state,
)
from app.reporting.applicant_identity import (
    ApplicantIdentity, IDENTITY_COMPANY, clean_organisation_name, is_likely_individual_name, resolve_applicant_identity,
)
from app.reporting.opportunity_universe import build_current_opportunity_universe

MODEL = "gpt-4o-mini"  # matches every other OpenAI call already made across this codebase - no new model introduced (Gate 2A Section 17)
# v2 (Gate 2A amendment, "Evidence-Grounded Applicant Web Research") - adds
# the bounded web-search tool, the `evidence` schema field, and the
# evidence-sufficiency confidence ceiling (see apply_evidence_sufficiency_
# ceiling below) - a materially different prompt/schema/validation contract
# from v1, so every v1-generated row is correctly treated as stale by
# should_regenerate's own existing prompt_version check, with NO other
# staleness mechanism needed.
PROMPT_VERSION = "applicant-intelligence-v2-web-research"

# Gate 2A amendment Section 20 - the native OpenAI Responses API hosted
# web_search tool (confirmed against the ACTUALLY INSTALLED openai SDK,
# v2.44.0 - app.reporting.applicant_intelligence's own implementation
# report documents the exact smoke test used to verify this, never assumed
# from memory). This is a server-side, MODEL-INVOKED tool: attaching it to
# a single client.responses.create(...) call lets the model decide for
# itself whether searching is needed at all (Section 5/11 - "do not
# necessarily execute all queries"), still within ONE bounded, non-
# autonomous turn - never a persistent loop, never the Agents SDK. Kept at
# "low" context size deliberately (Section 4 - "bounded research, not
# free-roaming autonomy"): enough for a handful of targeted lookups per
# identity, not an open-ended browse.
WEB_SEARCH_TOOL = {"type": "web_search", "search_context_size": "low"}

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

# Gate 2A amendment Section 7 - the evidence source-type taxonomy.
# INTERNAL_* are named here for completeness/documentation only - internal
# facts are already represented via the existing evidence_ref mechanism
# (occurrence:*/company:*/raw_name:*/fact:*/control:*, see
# allowed_evidence_refs) and are never duplicated into the `evidence` array
# below, which is reserved for EXTERNALLY-discovered (bounded web research)
# evidence only - a deliberate, narrow split, not the maximal taxonomy
# Section 7 itself warns against ("do not create excessive taxonomy").
SOURCE_INTERNAL_PLANNING_RECORD = "INTERNAL_PLANNING_RECORD"
SOURCE_INTERNAL_COMPANY_RECORD = "INTERNAL_COMPANY_RECORD"
SOURCE_INTERNAL_CONTROL_RECORD = "INTERNAL_CONTROL_RECORD"
SOURCE_OFFICIAL_COMPANY_WEBSITE = "OFFICIAL_COMPANY_WEBSITE"
SOURCE_COMPANIES_HOUSE = "COMPANIES_HOUSE"
SOURCE_GOVERNMENT_OR_LOCAL_AUTHORITY = "GOVERNMENT_OR_LOCAL_AUTHORITY"
SOURCE_PLANNING_DOCUMENT = "PLANNING_DOCUMENT"
SOURCE_CORPORATE_GROUP_WEBSITE = "CORPORATE_GROUP_WEBSITE"
SOURCE_REPUTABLE_PROPERTY_PRESS = "REPUTABLE_PROPERTY_PRESS"
SOURCE_REPUTABLE_NEWS_SOURCE = "REPUTABLE_NEWS_SOURCE"
SOURCE_OTHER_RELIABLE_PUBLIC_SOURCE = "OTHER_RELIABLE_PUBLIC_SOURCE"
# The ONLY source types the model may use in the `evidence` array - Section
# 8's own quality hierarchy, ordered most- to least-trusted; also this
# module's own tier classification below.
EXTERNAL_SOURCE_TYPES = (
    SOURCE_OFFICIAL_COMPANY_WEBSITE, SOURCE_COMPANIES_HOUSE, SOURCE_GOVERNMENT_OR_LOCAL_AUTHORITY,
    SOURCE_PLANNING_DOCUMENT, SOURCE_CORPORATE_GROUP_WEBSITE, SOURCE_REPUTABLE_PROPERTY_PRESS,
    SOURCE_REPUTABLE_NEWS_SOURCE, SOURCE_OTHER_RELIABLE_PUBLIC_SOURCE,
)

# Gate 2A amendment Section 6/22 - the SEMANTIC evidence-sufficiency tiers
# (deterministic, never a second LLM "judge" call - "the narrowest robust
# approach"). STRONG: a direct, independently verifiable, official/
# governmental source - can support HIGH. MEDIUM: a reputable but indirect
# source (press/news/other reliable public source), OR an internal
# Companies House fact this platform already holds (a verified legal-entity
# record - real, but proves incorporation/status, not commercial ROLE) -
# can support MEDIUM, or HIGH only when STRONG evidence is also present.
# WEAK: everything else this platform holds internally about planning
# ACTIVITY (an occurrence/raw name/aggregate fact/site-specific control
# relationship) - real, but Section 6's own example is exact: being named
# on N applications, or a bare raw name, does not by itself prove a
# commercial role - WEAK evidence alone can never exceed LOW.
_STRONG_SOURCE_TYPES = {
    SOURCE_OFFICIAL_COMPANY_WEBSITE, SOURCE_CORPORATE_GROUP_WEBSITE, SOURCE_COMPANIES_HOUSE,
    SOURCE_GOVERNMENT_OR_LOCAL_AUTHORITY, SOURCE_PLANNING_DOCUMENT,
}
_MEDIUM_SOURCE_TYPES = {SOURCE_REPUTABLE_PROPERTY_PRESS, SOURCE_REPUTABLE_NEWS_SOURCE, SOURCE_OTHER_RELIABLE_PUBLIC_SOURCE}
_CONFIDENCE_RANK = {CONFIDENCE_LOW: 0, CONFIDENCE_MEDIUM: 1, CONFIDENCE_HIGH: 2}

# Syntactic-only check (Gate 2A amendment Section 29: "invalid URL/source
# reference rejected") - this platform has no live URL-fetch/liveness
# check anywhere, and adding one here would be a new, flaky, out-of-scope
# network dependency inside validation; a malformed/empty URL is still
# rejected outright.
_URL_PATTERN = re.compile(r"^https?://[^\s]+\.[^\s]+$", re.IGNORECASE)

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


def is_planning_opportunity_linked(context: ApplicantIdentityContext) -> bool:
    """Gate 2A amendment Section 1/14 - the SCOPE gate: eligible only when
    at least one of this identity's occurrences sits on a Site the current
    Opportunity Universe actually flags as a planning-delivery candidate
    (long_pending_application/recent_permission/site[approaching_lapse]/
    phase[undeveloped_permission]) - never merely "an Application exists
    somewhere in the platform's history". A strategic_land allocation
    (LocalPlanSite) never produces an occurrence at all (build_applicant_
    identity_contexts only ever scans Application rows), so this already
    correctly excludes every strategic-land-only opportunity by
    construction; a strategic-land Site that ALSO carries a genuine linked
    Application is unaffected and remains eligible through that
    Application relationship (see test_strategic_land_regression)."""
    return any(o.is_opportunity_candidate for o in context.occurrences)


def is_person_shaped_identity(context: ApplicantIdentityContext) -> bool:
    """Gate 2A amendment Section 12 - True only when EVERY raw name variant
    seen for this identity looks like a named individual (app.reporting.
    applicant_identity.is_likely_individual_name) - conservative toward
    treating an identity as a real organisation: a single organisation-
    shaped variant among several is enough to disqualify this check, so a
    genuine company is never silently skipped merely because one raw
    portal field happened to record a person's name for it too."""
    names = context.raw_name_variants or [context.display_name]
    return all(is_likely_individual_name(n) for n in names)


def select_priority_identity_refs(
    contexts: dict[str, ApplicantIdentityContext], *, limit: int, only_opportunity_linked: bool = True,
) -> list[str]:
    """Gate 2A Section 24, NARROWED by the Gate 2A amendment's own Section 1/
    14 scope decision - `only_opportunity_linked` (default True, matching
    the amendment's explicit product decision) restricts selection to
    identities is_planning_opportunity_linked accepts; pass False only for
    diagnostic/reporting purposes (see estimate_bootstrap_scope below),
    never for real processing. Priority order among eligible identities:
    long_pending_application first, then recent_permission, then any other
    planning-delivery candidate. Deterministic tie-break (identity_ref) so
    repeated runs with an unchanged backlog select the same identities,
    never an arbitrary dict-iteration order."""
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

    pool = contexts.values()
    if only_opportunity_linked:
        pool = [ctx for ctx in pool if is_planning_opportunity_linked(ctx)]
    ordered = sorted(pool, key=_priority)
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

SITE-SPECIFIC OWNERSHIP/CONTROL EVIDENCE (kept SEPARATE from your own role classification below; never flatten these into one claim):
{control_lines}

EVERYTHING ABOVE IS INTERNAL PROPERTY AIGENT EVIDENCE. It proves planning
ACTIVITY (this name was submitted on these applications) and, where a
Company row exists, verified legal-entity facts (incorporation/status) -
it does NOT by itself prove a COMMERCIAL ROLE. A bare name, or a count of
applications, is a fact about activity, never proof of what kind of
organisation this is.

YOU HAVE ACCESS TO A WEB SEARCH TOOL. Use it when the internal evidence
above is insufficient, ambiguous, or purely name-derived to support a
confident role - which will be the common case for a name-based identity
with no Companies House record. Do NOT search if the internal evidence
already gives you everything you need (e.g. you have nothing useful to
add beyond restating activity, and UNKNOWN is the honest answer either
way). Search efficiently and stop once you have enough - a small number
of targeted queries (e.g. "<organisation> official website", "<organisation>
land promoter", "<organisation> housebuilder", "<organisation> planning")
is normally sufficient; you do not need to run every possible query.

SOURCE QUALITY - prefer, in this order, and cite every external fact you
rely on in the `evidence` array below with the matching source_type:
1. OFFICIAL_COMPANY_WEBSITE - the organisation's own official website.
2. COMPANIES_HOUSE - a Companies House / equivalent government company record.
3. GOVERNMENT_OR_LOCAL_AUTHORITY - an official government or local/planning authority source.
4. PLANNING_DOCUMENT - an official planning application document.
5. CORPORATE_GROUP_WEBSITE - an official parent/group company website.
6. REPUTABLE_PROPERTY_PRESS - a reputable property/planning industry publication.
7. REPUTABLE_NEWS_SOURCE - a reputable general news source.
8. OTHER_RELIABLE_PUBLIC_SOURCE - another source you can confidently attribute and inspect.
AVOID relying on search-result snippets you cannot attribute to a real,
inspectable page, SEO/company directories, scraped aggregators, social
media, forums, or unverified user-generated content - if that is genuinely
all you can find, treat the evidence as insufficient rather than citing it.

ROLE-SPECIFIC EVIDENCE - what counts as real support (never a name alone):
- HOUSEBUILDER: an official/reputable source explicitly describing the organisation building and selling homes (a portfolio, an explicit description).
- LAND_PROMOTER: an official/reputable source explicitly describing land promotion or strategic land activity (acquiring/controlling land, pursuing planning, then disposing or partnering).
- HOUSING_ASSOCIATION: an official description, or a regulator/government source, identifying it as a registered provider/housing association.
- PUBLIC_SECTOR: a source establishing the entity is a public authority or public body.
- CONSULTANT_AGENT: an official professional-services website, or planning documentation, showing an agent/consultant relationship (not the applicant themselves).
- DEVELOPER: a source establishing actual development activity or an explicit developer role - broader/weaker than HOUSEBUILDER, do not use HOUSEBUILDER unless residential housebuilding specifically is shown.
- LANDOWNER_PRIVATE: treat with special care - never infer ownership merely from applicant status; this is a role about the organisation's own described business (e.g. a private estate/landowning company), never a substitute for the separate, site-specific ControlRelationship evidence above.
- OTHER / UNKNOWN: use whenever the evidence above does not meet the bar for one of the defined roles - never force a classification.

RULES - follow every one of these exactly:
1. You may assert MULTIPLE roles for this organisation (e.g. LAND_PROMOTER and DEVELOPER together) if the evidence genuinely supports more than one - never force a single label.
2. Every role you assert (other than UNKNOWN) MUST cite at least one evidence_ref from the refs shown in brackets above, and/or an "evidence:<index>" ref into the `evidence` array you return - a hallucinated or unlisted ref is an automatic rejection. UNKNOWN needs no evidence_refs and is the correct, expected output when nothing above supports a confident role.
3. Confidence is categorical only: HIGH, MEDIUM, or LOW - never a numeric percentage, never invented precision. HIGH requires direct, official/reliable evidence (internal facts about planning ACTIVITY alone, e.g. a bare name or an application count, can never alone support HIGH or MEDIUM - only LOW). MEDIUM requires either one reliable indirect source or multiple converging weaker ones. Do not use HIGH merely because you feel certain - use it only when the evidence cited genuinely is that strong.
4. is_spv (Special Purpose Vehicle) is a SEPARATE corporate-structure question from role - having "Limited"/"Ltd" in a name is NEVER by itself evidence of SPV status; "Developments" in a name is NEVER by itself evidence of LAND_PROMOTER; "Homes" in a name is NEVER by itself evidence of HOUSEBUILDER; "Land"/"Properties" in a name is NEVER by itself evidence of LAND_PROMOTER or LANDOWNER_PRIVATE. Return UNKNOWN for is_spv unless the evidence above or your research genuinely supports TRUE or FALSE.
5. parent_group is null unless the evidence above or your research genuinely names a parent/group relationship - never invented from a name resembling a larger group.
6. NEVER assert, or let your summary imply: that this site or any site above is for sale or available; that this organisation owns any site solely because it is the applicant; that a promoter will sell after permission; that an SPV means a site is being flipped; that Certificate A evidence means current disposal intent; that any Application/Site above is an "acquisition opportunity"; that being an applicant establishes ownership, control, or exclusivity. Ownership/control evidence above is SEPARATE, SITE-SPECIFIC evidence - never merge it with your own role classification into a single stronger claim (e.g. never write "promoter-owned site for sale"). Gate 2A intelligence should generally avoid site-specific commercial conclusions entirely.
7. summary must be plain, evidence-only prose (2-4 sentences) - state only what the facts above and your research actually show; frame genuine gaps as investigation signals, never as a real-world absence (an application with no ownership evidence here means Property AIgent has not identified any, not that none exists).
8. unresolved_questions: 0-3 short, specific open questions the evidence above cannot yet answer (empty list if genuinely none) - never a generic instruction.
9. Every evidence_ref you cite anywhere (roles[].evidence_refs, parent_group.evidence_refs) must be an EXACT string from the bracketed refs shown above, or a valid "evidence:<index>" into your own `evidence` array - never invent, abbreviate, or paraphrase a ref.
10. evidence: one entry per EXTERNAL fact you found via web search and relied on (empty array if you did not search, or found nothing usable) - each with source_type (from the list above), title, url (the real page you found), publisher (the site/organisation name), and a concise claim (one sentence - never a copied passage). Leave accessed_date as an empty string - Property AIgent records the real access date itself. Never fabricate a URL or title - if you are not confident a source is real and inspectable, do not include it.
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
            # Gate 2A amendment ("Evidence-Grounded Applicant Web Research")
            # Section 7/17 - EXTERNAL evidence only (internal facts are
            # already covered by the existing evidence_ref mechanism - see
            # EXTERNAL_SOURCE_TYPES' own docstring). [] is the correct,
            # expected value whenever web research was not needed or found
            # nothing usable (Section 5) - never inert placeholder entries.
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_type": {"type": "string", "enum": list(EXTERNAL_SOURCE_TYPES)},
                        "title": {"type": "string"},
                        "url": {"type": "string"},
                        "publisher": {"type": "string"},
                        "claim": {"type": "string"},
                        "accessed_date": {"type": "string"},
                    },
                    "required": ["source_type", "title", "url", "publisher", "claim", "accessed_date"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["roles", "is_spv", "parent_group", "summary", "unresolved_questions", "evidence"],
        "additionalProperties": False,
    },
}


# --- Grounding validation (Gate 2A Section 19) ------------------------------


def _evidence_ref_pool(context: ApplicantIdentityContext, structured_evidence: list[dict]) -> set[str]:
    """The complete whitelist for THIS specific response: every internal
    context ref PLUS one "evidence:<i>" ref per entry the model itself
    returned in its own `evidence` array (Section 17's own external-
    evidence mechanism) - computed per-response, since the external
    entries don't exist until the model returns them."""
    return allowed_evidence_refs(context) | {f"evidence:{i}" for i in range(len(structured_evidence))}


def validate_applicant_intelligence_output(context: ApplicantIdentityContext, structured: dict) -> tuple[bool, list[str]]:
    """Rejects any output citing an evidence_ref not present in this
    response's own ref pool (internal context refs + this response's own
    `evidence` array indices), any role/confidence/spv_status/source_type
    outside the fixed enums (defensive - already enforced by the strict
    JSON schema, but checked again here so this function is a complete,
    independently-correct grounding gate on its own), a non-UNKNOWN role
    with zero evidence_refs, a malformed/missing evidence URL, or a summary
    containing one of the banned commercial-overreach phrases (Gate 2A
    Section 13/23).

    This function checks ONLY that cited evidence EXISTS and is well-
    formed - "evidence exists" is necessary but not sufficient (Gate 2A
    amendment Section 6). Whether the cited evidence actually SUPPORTS the
    confidence level claimed is a separate, deterministic question answered
    by apply_evidence_sufficiency_ceiling below, applied by the
    orchestrator AFTER this validation passes."""
    problems: list[str] = []
    evidence_list = structured.get("evidence", [])
    allowed = _evidence_ref_pool(context, evidence_list)

    for i, item in enumerate(evidence_list):
        if item.get("source_type") not in EXTERNAL_SOURCE_TYPES:
            problems.append(f"evidence[{i}] has an unrecognised source_type: {item.get('source_type')!r}")
        url = item.get("url") or ""
        if not _URL_PATTERN.match(url):
            problems.append(f"evidence[{i}] has a missing or malformed URL: {url!r}")

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


# --- Semantic evidence sufficiency (Gate 2A amendment Section 6/22) --------


def _evidence_ref_tier(ref: str, structured_evidence: list[dict]) -> str:
    """STRONG | MEDIUM | WEAK for one evidence_ref string - see the module-
    level _STRONG_SOURCE_TYPES/_MEDIUM_SOURCE_TYPES docstring for the exact
    reasoning behind each tier."""
    if ref.startswith("evidence:"):
        try:
            idx = int(ref.split(":", 1)[1])
        except ValueError:
            return "WEAK"
        if 0 <= idx < len(structured_evidence):
            source_type = structured_evidence[idx].get("source_type")
            if source_type in _STRONG_SOURCE_TYPES:
                return "STRONG"
            if source_type in _MEDIUM_SOURCE_TYPES:
                return "MEDIUM"
        return "WEAK"
    if ref.startswith("company:"):
        # A Companies House-derived fact this platform already holds - a
        # real, verified legal-entity record (MEDIUM), but proves
        # incorporation/status, never commercial ROLE on its own (Gate 2A
        # amendment Section 6's own reasoning for why internal evidence is
        # "often insufficient to establish commercial role reliably").
        return "MEDIUM"
    # occurrence:* / raw_name:* / fact:* / control:* - planning ACTIVITY or
    # site-specific control evidence, never commercial-role proof alone
    # (the exact "raw_name:Bloor Homes... does not prove LAND_PROMOTER"
    # example the amendment brief itself gives).
    return "WEAK"


def evidence_supported_confidence_ceiling(evidence_refs: list[str], structured_evidence: list[dict]) -> str:
    """The HIGHEST confidence this specific set of evidence_refs can
    actually support, independent of what the model itself claimed."""
    if not evidence_refs:
        return CONFIDENCE_LOW
    tiers = [_evidence_ref_tier(ref, structured_evidence) for ref in evidence_refs]
    if "STRONG" in tiers:
        return CONFIDENCE_HIGH
    if tiers.count("MEDIUM") >= 1 or tiers.count("WEAK") >= 2:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def apply_evidence_sufficiency_ceiling(structured: dict) -> tuple[dict, list[str]]:
    """Gate 2A amendment Section 6/22's own semantic-sufficiency layer,
    applied AFTER validate_applicant_intelligence_output passes (never
    instead of it - ref-existence and semantic-sufficiency are two
    independent checks). Deterministically DOWNGRADES (never upgrades,
    never rejects) each non-UNKNOWN role's confidence to the ceiling its
    OWN cited evidence can support - "evidence exists" is already proven
    by validation; this proves "evidence exists AT THIS STRENGTH". Returns
    the (possibly adjusted) structured dict plus a list of human-readable
    adjustment notes for observability/tests - the notes are NEVER
    persisted as intelligence fact, only used for reporting/audit."""
    adjustments: list[str] = []
    evidence_list = structured.get("evidence", [])
    new_roles = []
    for entry in structured.get("roles", []):
        role = dict(entry)
        if role["role"] != ROLE_UNKNOWN:
            ceiling = evidence_supported_confidence_ceiling(role.get("evidence_refs", []), evidence_list)
            if _CONFIDENCE_RANK[role["confidence"]] > _CONFIDENCE_RANK[ceiling]:
                adjustments.append(
                    f"{role['role']}: downgraded {role['confidence']} -> {ceiling} "
                    f"(cited evidence does not support the higher confidence claimed)"
                )
                role["confidence"] = ceiling
        new_roles.append(role)
    adjusted = dict(structured)
    adjusted["roles"] = new_roles
    return adjusted, adjustments


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
    evidence: list[dict] | None
    web_research_performed: bool
    confidence_adjustments: list[str] | None
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
        evidence=json.loads(row.evidence) if row and row.evidence else None,
        web_research_performed=bool(row.web_research_performed) if row else False,
        confidence_adjustments=None,
        model=row.model if row else None, prompt_version=row.prompt_version if row else None,
        status=row.status if row else None, generation_error=row.generation_error if row else None,
    )


# Gate 2A amendment Section 12 - the fixed, honest summary text for a
# person-shaped identity's deterministic not_researched result. Never
# generated by the model, never varying - a private individual applicant
# gets exactly this, every time, at zero AI cost.
_NOT_RESEARCHED_SUMMARY = (
    "This applicant identity appears to be a named individual rather than an organisation. "
    "Property AIgent does not perform commercial-role classification or web research on private "
    "individuals named on planning applications."
)


def generate_applicant_intelligence(
    session: Session, client, context: ApplicantIdentityContext, *, force: bool = False,
) -> ApplicantIntelligenceResult:
    """The one orchestration entry point (mirrors generate_allocation_
    intelligence_summary exactly). A rejected (ungrounded) output, or a raw
    client exception, NEVER overwrites the last successful classification -
    only status/generation_error record that the most recent attempt
    failed (Gate 2A Section 19: "if validation fails, retain last known
    good intelligence").

    PERSON-SHAPED IDENTITY FAST PATH (Gate 2A amendment Section 12): an
    identity whose every raw name variant looks like a named individual
    never reaches the model at all - `client` is never called, zero AI
    cost - and is instead persisted directly as a fixed, honest
    not_researched result. Still subject to the SAME should_regenerate
    staleness gate, so an unchanged person-shaped identity is not
    needlessly re-written on every run either."""
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

    if is_person_shaped_identity(context):
        not_researched_roles = [{"role": ROLE_UNKNOWN, "confidence": CONFIDENCE_LOW, "evidence_refs": []}]
        row.roles = json.dumps(not_researched_roles)
        row.is_spv = SPV_UNKNOWN
        row.parent_group = None
        row.summary = _NOT_RESEARCHED_SUMMARY
        row.unresolved_questions = json.dumps([])
        row.evidence = json.dumps([])
        row.web_research_performed = False
        row.generated_at = dt.datetime.now(dt.timezone.utc)
        row.context_fingerprint = fingerprint
        row.model = None
        row.prompt_version = PROMPT_VERSION
        row.status = "not_researched"
        row.generation_error = None
        session.commit()
        return ApplicantIntelligenceResult(
            regenerated=True, rejected=False, rejection_reason=None,
            roles=not_researched_roles, is_spv=SPV_UNKNOWN, parent_group=None,
            summary=_NOT_RESEARCHED_SUMMARY, unresolved_questions=[], evidence=[], web_research_performed=False,
            confidence_adjustments=None, model=None, prompt_version=PROMPT_VERSION, status="not_researched", generation_error=None,
        )

    prompt = build_applicant_prompt(context)
    try:
        response = client.responses.create(
            model=MODEL, input=prompt, tools=[WEB_SEARCH_TOOL],
            text={"format": {
                "type": "json_schema", "name": APPLICANT_INTELLIGENCE_SCHEMA["name"],
                "schema": APPLICANT_INTELLIGENCE_SCHEMA["schema"], "strict": True,
            }},
        )
        structured = json.loads(response.output_text)
        # Observability only (Section 19) - True only when the model's own
        # response actually invoked the tool, never merely because it was
        # offered (Section 5: search is skipped when internal evidence is
        # already sufficient).
        web_research_performed = any(getattr(item, "type", None) == "web_search_call" for item in response.output)
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

    # Semantic evidence-sufficiency layer (Section 6/22) - "evidence
    # exists" was just proven by validation above; this proves "evidence
    # exists AT THIS STRENGTH", deterministically downgrading (never
    # rejecting) an overclaimed confidence.
    structured, confidence_adjustments = apply_evidence_sufficiency_ceiling(structured)

    # accessed_date is recorded server-side, not trusted from the model
    # (Section 7: "when researched" must be accurate, not a guess) - every
    # evidence entry gets the real date this generation actually ran.
    today_str = dt.date.today().isoformat()
    for item in structured["evidence"]:
        item["accessed_date"] = today_str

    now = dt.datetime.now(dt.timezone.utc)
    row.roles = json.dumps(structured["roles"])
    row.is_spv = structured["is_spv"]
    row.parent_group = json.dumps(structured["parent_group"]) if structured["parent_group"] else None
    row.summary = structured["summary"]
    row.unresolved_questions = json.dumps(structured["unresolved_questions"])
    row.evidence = json.dumps(structured["evidence"])
    row.web_research_performed = web_research_performed
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
        evidence=structured["evidence"], web_research_performed=web_research_performed,
        confidence_adjustments=confidence_adjustments,
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
    opt-in.

    Scoped to is_planning_opportunity_linked identities only (Gate 2A
    amendment Section 1/14's own product decision) - matches
    select_priority_identity_refs' own default scope exactly, so this
    count and what actually gets processed never disagree."""
    contexts = build_applicant_identity_contexts(session)
    pending = 0
    for context in contexts.values():
        if not is_planning_opportunity_linked(context):
            continue
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


def estimate_bootstrap_scope(session: Session, *, intelligence_session: Session | None = None) -> dict:
    """Gate 2A amendment Section 31 - READ ONLY, no AI call. Exact current
    bootstrap scope, deduplicated at the ENTITY level (never "182
    opportunities = 182 calls" - Section 14's own explicit warning): the
    real cost driver is the number of DISTINCT eligible organisation
    identities, which is materially smaller than the opportunity count
    since one organisation commonly appears across several candidates
    (e.g. a housebuilder active on 5 current Sites is still one call, once
    classified, reused everywhere).

    `intelligence_session` defaults to `session` - pass a SEPARATE session
    only when `session` (e.g. the real production database, for this
    read-only planning-data query) does not yet have the applicant_
    intelligences table at all (this amendment's own explicit production
    state: no migration has been run there - see this module's own
    implementation report). In that case every identity is correctly
    counted as "requiring generation", exactly matching reality."""
    intelligence_session = intelligence_session if intelligence_session is not None else session
    universe = build_current_opportunity_universe(session)
    planning_delivery_records = [r for r in universe if r.opportunity_type != "strategic_land"]

    contexts = build_applicant_identity_contexts(session)
    linked = [c for c in contexts.values() if is_planning_opportunity_linked(c)]
    person_shaped_refs = {c.identity_ref for c in linked if is_person_shaped_identity(c)}
    org_shaped = [c for c in linked if c.identity_ref not in person_shaped_refs]

    already_classified_refs = {
        c.identity_ref for c in org_shaped
        if not should_regenerate(get_applicant_intelligence(intelligence_session, c.identity_ref), compute_context_fingerprint(c))
    }
    requiring_generation = [c for c in org_shaped if c.identity_ref not in already_classified_refs]

    return {
        "planning_application_opportunities": len(planning_delivery_records),
        "distinct_eligible_organisation_identities": len(org_shaped),
        "already_classified": len(already_classified_refs),
        "requiring_generation_or_refresh": len(requiring_generation),
        "private_person_identities_excluded": len(person_shaped_refs),
        "estimated_openai_calls": len(requiring_generation),
    }
