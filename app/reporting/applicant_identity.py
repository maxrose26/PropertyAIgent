"""Gate 2A ("Applicant Intelligence") - entity-level identity resolution.

Applicant Intelligence classification must be ENTITY-level, reusable across
every Application/Site an organisation appears on (Gate 2A Section 6) - this
module answers the prior question that makes that possible: "which
organisation, if any, does this raw applicant/developer name actually
refer to?", before any AI classification ever runs.

TWO IDENTITY KINDS (Gate 2A Section 7) - never conflated:
  - VERIFIED/RESOLVED ENTITY (company_id set): the raw name was matched to
    an EXISTING Company row via app.enrichment.control_entities.
    resolve_existing_company - the platform's own established, conservative
    resolver (exact normalised-name match, or fuzzy score >= 92, against
    Company rows already in the database; NEVER calls the Companies House
    API, NEVER creates a new Company row here). Reused verbatim, not
    reimplemented - this task's own explicit instruction ("do not duplicate
    this infrastructure").
  - NAME-BASED APPLICANT IDENTITY (identity_key set): no Company row could
    be confidently resolved. identity_key is app.enrichment.
    companies_house.normalise_name's own DETERMINISTIC normalisation
    (lowercase, punctuation stripped, legal suffix stripped) of the best
    available raw name - a purely mechanical transform, never a fuzzy
    semantic merge. "Peel L&P" and "Peel Land and Property" normalise to
    two DIFFERENT strings and therefore become two DIFFERENT identities
    here, even though a human would recognise them as the same
    organisation - this is the deliberate, honest boundary Gate 2A Section
    7 requires ("do not pretend name-normalisation equals verified
    legal-entity resolution"); such variants are reported, never silently
    merged.

WHICH RAW NAME FIELD (read-only production audit, Gate 2A pre-implementation
investigation): Application.applicant_name_raw (the actual PORTAL-SCRAPED
field) has only ~35% coverage platform-wide, and a large share of its
populated values are private individuals (e.g. "Ms Annie Jackson" appears
25 times) or placeholder junk ("See company name", "-", "."), not
organisation names at all - a portal application form's own "applicant"
field is very often the person submitting it, not the organisation behind
the scheme. SchemeIntelligence.applicant_company/.developer - extracted by
this platform's EXISTING document-intelligence pipeline from the planning
application's own documents (Certificate A, agent letters, etc.), not
invented by this task - has materially higher, more usable coverage (87%/
75%/91% either, platform-wide) and its values are overwhelmingly
organisation-shaped. This is a genuine, evidence-grounded finding, not an
assumption: Gate 2A's identity resolution therefore prefers
SchemeIntelligence.applicant_company, then .developer, then
Application.applicant_name_raw, in that trust order - see
best_organisation_name_candidates below. Each is labelled honestly by its
own real provenance wherever it becomes evidence (never presented as a
raw portal fact when it is in fact a document-extracted, AI-mediated one) -
see app.reporting.applicant_intelligence's own context builder.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.enrichment.companies_house import normalise_name
from app.enrichment.control_entities import resolve_existing_company

IDENTITY_COMPANY = "company"
IDENTITY_NAME = "name"

# Same "portal placeholder is not a real value" discipline already
# established in app.reporting.allocation_intelligence_summary's own
# _NON_INFORMATIVE_PORTAL_VALUES - a small, deliberately non-duplicated
# local set (that module's own constant is private and scoped to its own
# Application.decision/applicant_name_raw cleaning use, not exported for
# reuse) covering the SAME class of placeholder plus two forms confirmed in
# this task's own production audit ("See company name", "See Company
# Name" - a portal form's own literal instruction text, scraped as if it
# were the answer).
_NON_INFORMATIVE_VALUES = {
    "not available", "n/a", "na", "unknown", "not known", "not provided", "not stated", "tbc", "to be confirmed",
    "-", ".", "see company name", "see name",
}

# A private individual applicant (Gate 2A pre-implementation audit: "Ms
# Annie Jackson" x25, "Mr Darran Morrison" x16, etc. - a material share of
# real production applicant_name_raw values) is not an organisation and is
# never given a commercial-role classification - Gate 2A's own taxonomy
# (HOUSEBUILDER/LAND_PROMOTER/...) has no meaningful application to a named
# individual. This is a narrow, evidence-safe SHAPE check only (a title
# prefix) - it never asserts anything about the person, never blocks their
# name from being SHOWN as the applicant elsewhere on the platform, and is
# used only to decide "does this raw name get an Applicant Intelligence
# entity built for it at all" - deliberately not "Ltd company = SPV"-style
# overreach (Gate 2A Section 13), since a title prefix is a much stronger,
# near-certain signal than a bare legal suffix or a word appearing in a name.
_INDIVIDUAL_TITLE_PREFIX = re.compile(r"^(mr|mrs|miss|ms|mx|dr|prof)\.?\s+", re.IGNORECASE)


def clean_organisation_name(raw: str | None) -> str | None:
    """None if `raw` is blank, a known placeholder, or shaped like a named
    individual rather than an organisation - otherwise the trimmed raw
    string, unmodified (normalisation happens separately, only once an
    identity is actually being resolved - see resolve_applicant_identity)."""
    if not raw:
        return None
    cleaned = raw.strip()
    if not cleaned or cleaned.casefold() in _NON_INFORMATIVE_VALUES:
        return None
    if _INDIVIDUAL_TITLE_PREFIX.match(cleaned):
        return None
    return cleaned


# Gate 2A amendment ("Evidence-Grounded Applicant Web Research") Section 12:
# "Do NOT perform broad web research on private individuals merely because
# their name appears on a planning application." _INDIVIDUAL_TITLE_PREFIX
# above already keeps an OBVIOUSLY-titled individual ("Mr Darran Morrison")
# out of the identity index entirely - but a real production case slipped
# through that filter with no title at all ("Annabel Baker", two bare
# capitalised words) and still reached the AI with no organisational
# keyword to hint otherwise. This is a SEPARATE, WIDER, DELIBERATELY
# over-inclusive heuristic used ONLY to gate whether an already-resolved
# identity is offered to bounded web research at all (see app.reporting.
# applicant_intelligence's own eligibility check) - it does NOT remove the
# identity from the platform's index, and a false positive here (a small
# organisation whose name happens to look like a person) only costs a
# skipped web search, never a wrong or invented classification: internal-
# only evidence can still classify it (typically UNKNOWN, honestly). A
# false negative (missing a genuine individual) is caught downstream by the
# prompt's own explicit rule never to assert a role from a name alone -
# this heuristic is a cost/privacy guard, not the last line of defence.
_ORGANISATION_KEYWORDS = {
    "ltd", "limited", "plc", "llp", "llc", "inc", "corp", "corporation", "company", "co", "cic",
    "homes", "home", "developments", "development", "developers", "properties", "property", "land",
    "estates", "estate", "group", "holdings", "holding", "trust", "housing", "construction", "constructions",
    "investments", "investment", "capital", "partners", "partnership", "ventures", "assets", "management",
    "strategic", "promotions", "promoters", "promoter", "society", "association", "council", "university",
    "nhs", "church", "charity", "charitable", "foundation", "enterprises", "consultancy", "consultants",
    "architects", "planning", "surveyors", "developments", "regeneration", "residential", "living",
}


def is_likely_individual_name(name: str) -> bool:
    """True for a title-prefixed name (redundant with clean_organisation_name's
    own filter, kept here too so this function is a complete, independently-
    correct check) OR a bare 2-3 capitalised-word name with no digit and no
    recognised organisational keyword - the shape of an ordinary personal
    name ("Annabel Baker", "John A Smith"), never a claim about who the
    person actually is."""
    if _INDIVIDUAL_TITLE_PREFIX.match(name):
        return True
    if "&" in name:
        return False  # an ampersand is a business-naming convention ("L&P", "M&S"), never part of an ordinary personal name
    words = [w for w in name.strip().split() if w]
    if not (2 <= len(words) <= 3):
        return False
    if any(ch.isdigit() for ch in name):
        return False
    lowered = {w.strip(".,()").lower() for w in words}
    if lowered & _ORGANISATION_KEYWORDS:
        return False
    return all(w[:1].isupper() for w in words if w[:1].isalpha())


def best_organisation_name_candidates(
    *, si_applicant_company: str | None, si_developer: str | None, raw_applicant_name: str | None,
) -> list[str]:
    """Ordered, deduplicated candidate organisation names for ONE
    Application/Site, most-trusted-and-most-likely-organisation-shaped
    first (see this module's own docstring for why this order was chosen
    from real production coverage data, not assumed). Callers resolve each
    candidate to its OWN identity independently where they name genuinely
    different roles (applicant vs developer) - this function only cleans
    and orders, it never collapses multiple real candidates into one."""
    candidates = []
    for raw in (si_applicant_company, si_developer, raw_applicant_name):
        cleaned = clean_organisation_name(raw)
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)
    return candidates


@dataclass(frozen=True)
class ApplicantIdentity:
    """One resolved organisation-level identity - see module docstring for
    the two kinds. `raw_name` is the specific cleaned string that produced
    this identity (kept so a caller can track which raw variant led here,
    for the "report unresolved variants" requirement - see
    app.reporting.applicant_intelligence's own variant-tracking)."""
    identity_type: str  # IDENTITY_COMPANY | IDENTITY_NAME
    raw_name: str
    company_id: int | None = None
    identity_key: str | None = None
    company_display_name: str | None = None  # only set when identity_type == IDENTITY_COMPANY

    @property
    def display_name(self) -> str:
        return self.company_display_name if self.identity_type == IDENTITY_COMPANY else self.raw_name

    @property
    def ref(self) -> str:
        """Stable string key uniquely identifying this identity - used both
        as the in-memory dedup key (the same organisation named on many
        Sites must resolve to the SAME ApplicantIntelligence row) and as an
        opaque cross-reference the AI context/grounding validator can cite
        without exposing internal ids in prose."""
        if self.identity_type == IDENTITY_COMPANY:
            return f"company:{self.company_id}"
        return f"name:{self.identity_key}"


def resolve_applicant_identity(session: Session, raw_name: str) -> ApplicantIdentity | None:
    """READ ONLY. `raw_name` should already be cleaned (see
    clean_organisation_name) - returns None only if normalisation reduces
    it to nothing (e.g. a string of pure punctuation), which
    clean_organisation_name should already have excluded in practice."""
    company = resolve_existing_company(session, raw_name)
    if company is not None:
        return ApplicantIdentity(
            identity_type=IDENTITY_COMPANY, raw_name=raw_name,
            company_id=company.id, company_display_name=company.name_raw,
        )
    key = normalise_name(raw_name)
    if not key:
        return None
    return ApplicantIdentity(identity_type=IDENTITY_NAME, raw_name=raw_name, identity_key=key)
