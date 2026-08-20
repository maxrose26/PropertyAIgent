"""AI Allocation Intelligence Summary (Phase 1 Local Plan Intelligence) - a
narrative/interpretation layer over trusted PropertyAIgent intelligence for
ONE Local Plan allocation.

Same grounded-numbers-then-narrate architecture as app.reporting.
local_plan_summary and app.reporting.scheme_summary (the two established
precedents this module is deliberately modelled on): every fact fed to the
model is computed/looked up in Python first, from data this platform already
trusts - the model only ever writes the connective prose synthesising facts
it is given. It never establishes Allocation<->Site membership, never
decides whether a planning application is linked, never performs capacity
arithmetic, never assigns an ownership/developer/promoter role, never infers
adjacency between allocations, and never decides an allocation's planning
status. All of that is decided deterministically, elsewhere, before the
model ever sees a payload:

  trusted database facts
    -> AllocationIntelligenceContext (this module, pure, no OpenAI)
    -> OpenAI structured generation (this module, gated by a fingerprint)
    -> deterministic validation (this module, rejects ungrounded output)
    -> persisted on AllocationIntelligenceSummary, a DEDICATED table keyed
       by allocation_id (Pre-Merge Architecture Amendment - superseded the
       original V1 design of ai_summary_* columns directly on LocalPlanSite
       before that design ever reached production; see AllocationIntelligenceSummary's
       own class docstring for the full separation-of-source-from-
       interpretation reasoning). Never overwrites any LocalPlanSite field.
    -> customer-facing UI (app/ui/pages/3_Local_Plan_Sites.py, read-only)

TRUSTED SOURCES (Section 3 audit - see this module's own functions for how
each is used):
  - Identity/status/capacity: LocalPlanSite itself (site_name,
    policy_reference, intended_use, plan_status via LocalPlan, capacity via
    app.reporting.allocation_discovery.format_capacity - the SAME field the
    customer-facing gallery/detail page already reads, not re-derived).
  - Related Sites, linked Applications, capacity accounting: app.reporting.
    allocation_development_coverage.build_allocation_development_coverage -
    the AUTHORITATIVE AllocationSiteRelationship-derived source (already
    excludes every "rejected" relationship; a "needs_confirmation"
    relationship is still counted as related but its Site's capacity
    contribution is flagged disputed - see DevelopmentCoverageResult's own
    docstring). This module never reads LocalPlanSite.matched_site_id and
    never falls back to it - unlike app.reporting.allocation_discovery's
    has_trusted_linked_application (which must stay compatible with a
    legacy field for its own different purpose), an AI summary has no
    legacy-compatibility obligation at all, so it is built on the single,
    fully-trusted AllocationSiteRelationship source with no fallback path
    to weaken.
  - Ownership/control entities: app.reporting.ownership_control.
    get_allocation_control_intelligence - the SAME per-Site hierarchy the
    Allocation Detail page's own "Ownership & Control" section already
    renders from (Stage 4B.2/4B.3). role_label is used verbatim (Section 5)
    - never re-derived, re-worded, or reclassified - and a
    needs_review=True group is NEVER named as a fact (Section 14): only its
    existence is surfaced, as an uncertainty, never an owner/developer name.
  - Applicant (Allocation Party Evidence Amendment, aggregated across ALL
    trusted linked Applications by its own Pre-Merge Amendment "Multi-
    Application Party Intelligence"): Application.applicant_name_raw for
    EVERY trusted linked Application on a Site (not only the representative
    one - see ApplicantPartyEvidence), deduplicated by exact cleaned name -
    a raw portal scrape, cleaned only of non-informative placeholder values
    (_clean_applicant_name), never SchemeIntelligence's own
    applicant_company/developer/landowner/planning_agent fields (those are
    AI re-interpretations of this exact value with no evidence-grounding of
    their own, deliberately excluded from this evidence-grounded pathway).
    Role label is always "Applicant" - being named applicant, on one
    Application or many, is never treated as developer, promoter, or owner
    evidence.
  - Adjoining/nearby allocations: NO trusted source exists on this platform
    today (Section 15) - deliberately omitted from the context entirely, so
    the model has no adjacency data to draw on even by accident.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AllocationIntelligenceSummary, LocalPlanSite
from app.reporting.allocation_development_coverage import build_allocation_development_coverage
from app.reporting.allocation_discovery import format_capacity
from app.reporting.ownership_control import get_allocation_control_intelligence

MODEL = "gpt-4o-mini"
# Bumped whenever the prompt or schema changes in a way that could change
# the generated summary - persisted on every summary (mirrors
# app.reporting.local_plan_summary.PROMPT_VERSION exactly) so a version
# bump alone never retroactively invalidates an already-generated summary
# until it is actually next regenerated.
#
# v2 (Pre-Sample Amendment, "Trusted Planning Application Status/Decision
# Context") - build_summary_prompt materially changed: new representative-
# Application status/decision/category rendering, a bounded multi-
# Application category summary, and five new RULES distinguishing planning
# ACTIVITY from planning OUTCOME. No production summary has ever been
# generated under v1 (0 rows exist), so this bump has no practical effect
# today - it is the correct, disciplined action regardless, per this
# constant's own contract above.
#
# v3 (Final Pre-Merge Amendment, "needs_confirmation Trust Boundary") -
# _render_site_line's needs_confirmation branch materially changed (no
# longer says "capacity not yet determined"/lists any reference - a wholly
# different, more restrictive sentence). No production summary has ever
# been generated under v1 or v2 (0 rows exist), so this bump again has no
# practical effect today.
#
# v4 (Evidence-Grounded Validation Architecture Amendment) - the model is
# now explicitly told it may use ordinary connective language/synthesis
# freely (previously implied, now explicit); SUMMARY_SCHEMA's three flat
# referenced_application_references/referenced_entity_names/referenced_
# roles fields were replaced with two structured, PAIRED self-reports
# (referenced_applications: reference+claimed_status+claimed_decision;
# referenced_entities: name+role+site_scope) - see validate_summary_
# output's own docstring. No production summary has ever been generated
# under any prior version (0 rows exist), so this bump again has no
# practical effect today.
#
# v5 (Allocation Party Evidence Amendment, as corrected by its own
# Pre-Merge Amendment "Multi-Application Party Intelligence" before ever
# merging - both amendments landed on this SAME version, since the first
# shape was never merged/deployed/used to generate any production summary,
# 0 rows exist under it) - the model can now see, and is asked to
# synthesise, applicant evidence AGGREGATED ACROSS EVERY TRUSTED linked
# Application on a Site (ApplicantPartyEvidence, exact-name-deduplicated,
# never just the representative Application's own applicant - see
# AllocationIntelligenceContext.applicant_evidence and build_allocation_
# context's own comment for why: the representative Application stays the
# sole authority for capacity/status/decision, but WHICH organisations are
# involved is a separate question answered from the Site's full trusted
# Application set), sourced from Application.applicant_name_raw, never
# SchemeIntelligence's own AI-derived entity fields; a new APPLICANT
# EVIDENCE prompt section, Rule 2 widened to also guard against
# applicant->developer/promoter/owner promotion regardless of how many
# Applications name that applicant, and referenced_entities' grounding
# allow-set widened (via _allowed_party_facts, unifying ownership/control
# and applicant evidence into one (name, role, scope) -> allowed Application
# references lookup) to cover applicant claims through the SAME mechanism
# already used for ownership/control claims. SUMMARY_SCHEMA gained one new
# optional field, referenced_entities[].application_reference (validated
# against that same lookup) - needed only when the model chooses to tie a
# claim to ONE specific Application. Also generalises numeric grounding to
# mask context.allocation_reference/plan_status_label as known trusted
# strings (root cause of the "unsupported numbers: 18, 2.33" false
# rejection on Heald Green West's own "HOM 2.33" reference/"Regulation 18"
# plan-stage wording - see validate_summary_output's own comment). No
# production summary has ever been generated under any prior version (0
# rows exist - the four controlled-sample rows all carry status="error"/
# headline=None from OpenAI-auth failures predating this amendment), so
# this bump again has no practical effect on any existing row today.
# CORRECTION (recorded at v6 time, since this comment is no longer edited
# in place) - v5 WAS subsequently deployed and used for a real controlled
# production generation: allocation 51 (Beal Valley) succeeded under it
# (status="ok", prompt_version="allocation-intelligence-summary-v5"); the
# same run rejected allocations 32/66/196, which is what v6 below fixes.
#
# v6 (Final Grounding Hardening Amendment) - two representation gaps found
# from REAL v5 production rejections, neither a hallucination-protection
# weakening:
#   (1) trusted-label masking (Section 10 above) only matched a label's
#       FULL literal string; production proved a model narrating just the
#       label's parenthetical sub-phrase ("Regulation 18" alone, not the
#       whole "Draft consultation (Regulation 18)") was still flagged -
#       _trusted_label_substrings now also masks that sub-phrase, generic
#       to any "<phase> (<qualifier>)"-shaped trusted label, never a
#       one-off "18" exception - see validate_summary_output's own
#       comment.
#   (2) a self-reported claimed_decision="" was ambiguous between "no
#       claim made" and "explicitly claiming no decision is recorded" -
#       production proved the model needed the latter (East of Boothstown,
#       PA/2024/0749, decision=None) and had no way to self-report it
#       without inventing prose the validator then rejected.
#       referenced_applications gained decision_claim_mode ("none" |
#       "value" | "absent") to disambiguate - "absent" is only ever
#       accepted when the trusted decision is genuinely falsy, so a
#       decided Application (Granted/Refused/Withdrawn/...) can never be
#       described as undecided.
# Both fixes are representation-only - a genuinely invented number or a
# genuinely contradictory absence claim (e.g. "absent" against a real
# Granted/Refused/Withdrawn decision) is still rejected, proven by
# dedicated companion tests.
PROMPT_VERSION = "allocation-intelligence-summary-v6"


# --- Context object (Section 4) ---------------------------------------------


@dataclass
class RepresentativeApplicationDetail:
    """The trusted, portal-scraped planning status/decision facts for the
    ONE Application app.ui.common.pick_representative_application already
    selects for this Site (Pre-Sample Amendment, "Trusted Planning
    Application Status/Decision Context") - the SAME Application whose
    SchemeIntelligence.total_units_final already determines this Site's
    capacity contribution (SiteContextEntry.capacity above), so the status/
    decision the model sees always describes the SAME figure it is being
    given, never a different Application's status attached to a different
    Application's capacity. Every field here is a raw, portal-scraped fact
    already used elsewhere in this codebase's own customer-facing
    reporting (app.reporting.scheme_summary's own _fmt_application reads
    the identical fields) - none of it is AI-derived, and none of it is
    invented for this task. status/decision are PLANNING ACTIVITY/OUTCOME
    facts only - never a construction/delivery signal (see build_summary_
    prompt's own rules)."""
    reference: str
    status: str | None  # raw portal status, e.g. "Decided", "Under Consultation", "Awaiting decision"
    decision: str | None  # raw portal decision, e.g. "Granted", "Refuse", "Withdrawn" - null until determined
    decision_issued_date: str | None  # raw scraped date string, null until a decision exists
    application_category: str | None  # deterministic, e.g. "primary_residential" | "condition_discharge_or_details" - see app.scrapers.unit_filter.classify_application_category, reused verbatim, never re-derived
    proposal_summary: str | None  # truncated proposal text, same 150-char convention as app.reporting.scheme_summary._fmt_application
    # NOTE (Allocation Party Evidence Pre-Merge Amendment) - applicant is
    # deliberately NOT a field here. The Product Owner's own review decided
    # the representative Application stays the sole authority for capacity/
    # status/decision/category, while WHICH ORGANISATIONS are involved is
    # aggregated across every trusted linked Application on the Site (see
    # ApplicantPartyEvidence / SiteContextEntry.applicant_evidence below) -
    # a v5-only field limited to the representative Application's own
    # applicant existed briefly and was superseded here, never shipped in
    # any production summary (0 rows exist under any prior PROMPT_VERSION).


@dataclass
class SiteContextEntry:
    site_id: int
    label: str
    relationship_review_status: str  # auto_applied | needs_confirmation | confirmed
    capacity_known: bool
    capacity: int | None
    application_references: list[str] = field(default_factory=list)
    representative_application: RepresentativeApplicationDetail | None = None
    # Count of this Site's OTHER (non-representative) trusted Applications,
    # grouped by their own deterministic application_category - deliberately
    # NOT one entry per Application (Section 6: "the AI should NOT produce
    # something resembling Application A..., B..., C... x30" - see Heald
    # Green West's real ~30-Application case). Reuses the SAME bounded,
    # already-existing category vocabulary as representative_application's
    # own application_category field, never a new classification scheme.
    other_applications_by_category: dict[str, int] = field(default_factory=dict)


@dataclass
class OwnershipContextEntry:
    site_label: str
    is_residual: bool
    entity_name_raw: str
    role_label: str
    application_references: list[str] = field(default_factory=list)


@dataclass
class ApplicantPartyEvidence:
    """Allocation Party Evidence Pre-Merge Amendment ("Multi-Application
    Party Intelligence") - one entity named as applicant on one or more of
    a Site's TRUSTED linked Applications, deduplicated by exact cleaned
    name (never fuzzy-resolved - see _clean_applicant_name). Deliberately
    NOT scoped to the representative Application: the representative
    Application stays the sole authority for capacity/status/decision
    (RepresentativeApplicationDetail, unchanged by this amendment); WHICH
    organisations are involved is a separate question, answered by
    aggregating across every trusted linked Application on the Site - the
    exact split the Product Owner's review decided (Section 2).

    Role is always "Applicant", regardless of application_count - being
    named applicant on many Applications is still only Applicant evidence,
    never Developer/Owner/Promoter evidence, by construction (there is no
    field here that could carry a stronger role)."""
    site_label: str
    entity_name: str
    application_references: list[str] = field(default_factory=list)

    @property
    def application_count(self) -> int:
        return len(self.application_references)


@dataclass
class AllocationIntelligenceContext:
    """The bounded, deterministic payload the model is given - every field
    here is already a short, discrete, already-verified fact or count.
    Never includes raw document text. Built by build_allocation_context,
    never constructed directly by a caller."""

    allocation_id: int
    allocation_reference: str | None
    allocation_name: str
    council_code: str
    council_name: str
    local_plan_name: str | None
    plan_status_bucket: str  # adopted | emerging | other
    plan_status_label: str
    allocation_status: str | None
    intended_use: str | None

    allocation_capacity_value: int | None
    allocation_capacity_kind: str  # minimum | maximum | indicative | range | unknown
    allocation_capacity_display: str

    identified_application_capacity: int | None
    indicative_residual_capacity: int | None
    development_coverage_percentage: float | None
    development_coverage_classification: str
    capacity_accounting_status: str  # ok | no_activity | capacity_unknown | review_required

    number_of_related_sites: int
    number_of_linked_applications: int
    sites: list[SiteContextEntry] = field(default_factory=list)
    disputed_site_count: int = 0  # needs_confirmation relationships - never named, only counted

    ownership_entities: list[OwnershipContextEntry] = field(default_factory=list)
    ownership_review_pending_count: int = 0  # needs_review ControlRelationship groups - never named
    residual_ownership_known: bool = False

    # Allocation Party Evidence Pre-Merge Amendment - one entry per unique
    # (Site, cleaned applicant name), aggregated across every TRUSTED
    # linked Application on that Site (never just the representative one -
    # see ApplicantPartyEvidence's own docstring). Flat, top-level list,
    # mirroring ownership_entities' own shape exactly, for the same reason:
    # both are validated by the identical (name, role, scope) mechanism.
    applicant_evidence: list[ApplicantPartyEvidence] = field(default_factory=list)

    source_document_url: str | None = None
    source_page: int | None = None
    last_checked: str | None = None


# Allocation Party Evidence Amendment - Application.applicant_name_raw is a
# raw portal scrape, and portals sometimes populate it with a non-answer
# placeholder rather than leaving it NULL (confirmed in real production data
# - DC/060928 on the Heald Green West sample carries the literal string
# "Not Available"). A placeholder is not evidence of who the applicant is;
# treating it as a real name would let the model narrate "Not Available is
# named as the applicant", a factually-empty but schema-valid-looking claim.
# Generalises to the standard equivalents a scraped portal field can hold,
# not just the one literal string observed - never allocation/council-
# specific.
_NON_INFORMATIVE_APPLICANT_VALUES = {
    "not available", "n/a", "na", "unknown", "not known", "not provided", "not stated", "tbc", "to be confirmed",
}


def _clean_applicant_name(raw: str | None) -> str | None:
    """Returns the trimmed raw applicant name, or None if it is blank or a
    known non-informative portal placeholder (see _NON_INFORMATIVE_
    APPLICANT_VALUES above) - "no applicant evidence" and "a placeholder
    value" must both present to the model as the SAME thing (absence), not
    as a fabricated-looking real name."""
    if not raw:
        return None
    cleaned = raw.strip()
    if not cleaned or cleaned.casefold() in _NON_INFORMATIVE_APPLICANT_VALUES:
        return None
    return cleaned


def build_allocation_context(session: Session, allocation: LocalPlanSite) -> AllocationIntelligenceContext:
    """READ ONLY - issues the same batched queries app.reporting.
    allocation_development_coverage.build_allocation_development_coverage
    and app.reporting.ownership_control.get_allocation_control_intelligence
    already issue for exactly this one allocation (both already O(1) in
    query count for a single allocation - see their own docstrings); no new
    query pattern introduced here."""
    from app.config import load_councils
    from app.reporting.allocation_discovery import PLAN_STATUS_META

    plan = allocation.local_plan
    plan_status = plan.status if plan else (allocation.plan_status or None)
    plan_meta = PLAN_STATUS_META.get(plan_status, PLAN_STATUS_META[None])
    capacity = format_capacity(allocation)
    council_config = load_councils()
    council_name = council_config[allocation.council_code].name if allocation.council_code in council_config else allocation.council_code

    coverage_by_allocation = build_allocation_development_coverage(session, [allocation])
    entry = coverage_by_allocation.get(allocation.id, {})
    coverage = entry.get("coverage")
    site_summaries = entry.get("site_summaries", [])

    sites: list[SiteContextEntry] = []
    disputed_site_count = 0
    applicant_evidence: list[ApplicantPartyEvidence] = []
    for s in site_summaries:
        is_disputed = s.relationship_review_status == "needs_confirmation"
        if is_disputed:
            disputed_site_count += 1

        # Final Pre-Merge Amendment ("needs_confirmation Trust Boundary") -
        # a disputed AllocationSiteRelationship must never enter the
        # context in the SAME Application-shaped structure trusted
        # activity uses, even hedged by a text label - the ORIGINAL V1
        # design already committed to "never named, only counted" for
        # disputed evidence (see disputed_site_count's own comment above,
        # unchanged); representative_application/other_applications_by_
        # category/capacity/application_references are the Application-
        # shaped facts that must be withheld here, STRUCTURALLY (None/
        # empty at construction, not merely hedged in prompt text) so a
        # disputed Site can never be mistaken for trusted linked activity
        # by the model OR by anything else reading this dataclass (the
        # fingerprint included - see compute_context_fingerprint below).
        rep = s.representative_application if not is_disputed else None
        rep_detail = None
        if rep is not None:
            proposal = rep.proposal or None
            rep_detail = RepresentativeApplicationDetail(
                reference=rep.reference, status=rep.status, decision=rep.decision,
                decision_issued_date=rep.decision_issued_date, application_category=rep.application_category,
                proposal_summary=proposal[:150] if proposal else None,
            )

        if is_disputed:
            sites.append(SiteContextEntry(
                site_id=s.site_id, label=s.site.display_address,
                relationship_review_status=s.relationship_review_status,
                capacity_known=False, capacity=None,
                application_references=[], representative_application=None,
                other_applications_by_category={},
            ))
            continue

        # Section 6 - every OTHER trusted Application on this Site (never
        # the representative one, already surfaced in full above) is
        # counted, not narrated - grouped by the SAME deterministic
        # application_category classify_application_category already
        # assigned at ingestion, "uncategorized" only for the rare
        # legacy row with no value at all (nullable column).
        other_applications_by_category: dict[str, int] = {}
        for a in s.applications:
            if rep is not None and a.id == rep.id:
                continue
            category = a.application_category or "uncategorized"
            other_applications_by_category[category] = other_applications_by_category.get(category, 0) + 1

        # Allocation Party Evidence Pre-Merge Amendment ("Multi-Application
        # Party Intelligence", Section 2) - party evidence is aggregated
        # across EVERY trusted linked Application on this Site (s.applications
        # already is exactly that set - the same trusted, Site-scoped
        # Application list other_applications_by_category above already
        # iterates), INCLUDING the representative Application if it happens
        # to carry an applicant too - unlike other_applications_by_category,
        # this is never representative-excluding, because the representative
        # Application's own applicant is just as valid party evidence as any
        # other's. Exact cleaned-name deduplication only (Section 5) - no
        # fuzzy company resolution.
        applicant_refs_by_name: dict[str, list[str]] = {}
        for a in s.applications:
            name = _clean_applicant_name(a.applicant_name_raw)
            if name is None:
                continue
            applicant_refs_by_name.setdefault(name, []).append(a.reference)
        for name, refs in sorted(applicant_refs_by_name.items()):
            applicant_evidence.append(ApplicantPartyEvidence(
                site_label=s.site.display_address, entity_name=name, application_references=sorted(set(refs)),
            ))

        sites.append(SiteContextEntry(
            site_id=s.site_id, label=s.site.display_address,
            relationship_review_status=s.relationship_review_status,
            capacity_known=s.capacity_known, capacity=s.capacity,
            application_references=sorted({a.reference for a in s.applications}),
            representative_application=rep_detail,
            other_applications_by_category=other_applications_by_category,
        ))

    control_sections = get_allocation_control_intelligence(
        session, site_summaries,
        indicative_residual_capacity=coverage.indicative_residual_capacity if coverage else None,
    )
    # Final Pre-Merge Amendment ("needs_confirmation Trust Boundary",
    # Section 5) - get_allocation_control_intelligence only ever checks
    # ControlRelationship.review_status (whether the OWNERSHIP evidence
    # itself is disputed); it has no knowledge of whether the SITE it is
    # attached to only reached this allocation via a disputed
    # AllocationSiteRelationship. An "auto_applied" (accepted)
    # ControlRelationship on a Site linked only by a needs_confirmation
    # relationship must still be treated as uncertain HERE, at the
    # allocation-context boundary - never redesigning get_allocation_
    # control_intelligence itself (it is correct and unchanged for its
    # own, wider callers, e.g. the Ownership & Control UI section, which
    # has its own display requirements outside this task's scope).
    disputed_site_ids = {s.site_id for s in site_summaries if s.relationship_review_status == "needs_confirmation"}

    ownership_entities: list[OwnershipContextEntry] = []
    ownership_review_pending_count = 0
    residual_ownership_known = False
    for section in control_sections:
        site_relationship_disputed = section.site_id is not None and section.site_id in disputed_site_ids
        for group in section.groups:
            if group.needs_review or site_relationship_disputed:
                # Section 14 (unchanged) / Section 5 (this amendment) - a
                # disputed ownership/control group, OR any group attached
                # to a Site whose OWN allocation linkage is itself
                # disputed, is NEVER named as a fact - only counted as an
                # uncertainty signal.
                ownership_review_pending_count += 1
                continue
            ownership_entities.append(OwnershipContextEntry(
                site_label=section.label, is_residual=section.is_residual,
                entity_name_raw=group.entity_name_raw, role_label=group.role_label,
                application_references=list(group.application_references),
            ))
            if section.is_residual:
                residual_ownership_known = True

    return AllocationIntelligenceContext(
        allocation_id=allocation.id,
        allocation_reference=allocation.policy_reference,
        allocation_name=allocation.site_name,
        council_code=allocation.council_code,
        council_name=council_name,
        local_plan_name=plan.plan_name if plan else allocation.plan_name,
        plan_status_bucket=plan_meta["bucket"],
        plan_status_label=plan_meta["label"],
        allocation_status=allocation.allocation_status,
        intended_use=allocation.intended_use,
        allocation_capacity_value=capacity["value"],
        allocation_capacity_kind=capacity["kind"],
        allocation_capacity_display=capacity["display"],
        identified_application_capacity=coverage.identified_application_capacity if coverage else None,
        indicative_residual_capacity=coverage.indicative_residual_capacity if coverage else None,
        development_coverage_percentage=coverage.development_coverage_percentage if coverage else None,
        development_coverage_classification=coverage.development_coverage_classification if coverage else "NO_IDENTIFIED_ACTIVITY",
        capacity_accounting_status=coverage.capacity_accounting_status if coverage else "no_activity",
        number_of_related_sites=coverage.number_of_related_sites if coverage else 0,
        number_of_linked_applications=coverage.number_of_linked_applications if coverage else 0,
        sites=sites,
        disputed_site_count=disputed_site_count,
        ownership_entities=ownership_entities,
        ownership_review_pending_count=ownership_review_pending_count,
        residual_ownership_known=residual_ownership_known,
        applicant_evidence=applicant_evidence,
        source_document_url=allocation.source_document_url,
        source_page=allocation.source_page,
        last_checked=plan.last_checked.isoformat() if plan and plan.last_checked else None,
    )


def has_sufficient_context_for_summary(session: Session, allocation: LocalPlanSite) -> bool:
    """The "insufficient context" eligibility gate (originally the CLI's own
    _has_sufficient_context, promoted here - Pre-Merge Architecture
    Amendment - so the CLI runner and the automatic refresh stage in
    app.pipeline.run_weekly share exactly one definition rather than two
    independently-maintained copies). An allocation with no stated capacity
    AND no related Site at all gives the model nothing concrete to
    synthesise; every other allocation is eligible, even one with
    NO_IDENTIFIED_ACTIVITY (that absence is itself a genuine, reportable
    fact - see build_summary_prompt)."""
    context = build_allocation_context(session, allocation)
    return context.allocation_capacity_value is not None or context.number_of_related_sites > 0


def get_allocation_summary(session: Session, allocation_id: int) -> AllocationIntelligenceSummary | None:
    """The one lookup path for an allocation's current (at most one row,
    per the table's own unique constraint) persisted summary."""
    return session.execute(
        select(AllocationIntelligenceSummary).where(AllocationIntelligenceSummary.allocation_id == allocation_id)
    ).scalar_one_or_none()


# --- Fingerprint / staleness (Section 7) ------------------------------------


def compute_context_fingerprint(context: AllocationIntelligenceContext) -> str:
    """sha256 over only the narrative-relevant portion of the context -
    mirrors app.reporting.local_plan_summary.compute_evidence_fingerprint's
    own reasoning exactly. Deliberately excludes last_checked,
    source_document_url/source_page, and council_name: none of those change
    what the summary would actually SAY, so including them would force a
    regeneration (and AI cost) on every routine check even when nothing a
    reader would notice has changed. Site/ownership entries are sorted so
    row-order alone (never semantically meaningful) cannot change the
    fingerprint."""
    fingerprint_source = {
        "allocation_reference": context.allocation_reference,
        "allocation_name": context.allocation_name,
        "plan_status_bucket": context.plan_status_bucket,
        "allocation_status": context.allocation_status,
        "intended_use": context.intended_use,
        "allocation_capacity_value": context.allocation_capacity_value,
        "allocation_capacity_kind": context.allocation_capacity_kind,
        "identified_application_capacity": context.identified_application_capacity,
        "indicative_residual_capacity": context.indicative_residual_capacity,
        "development_coverage_percentage": context.development_coverage_percentage,
        "development_coverage_classification": context.development_coverage_classification,
        "capacity_accounting_status": context.capacity_accounting_status,
        "number_of_related_sites": context.number_of_related_sites,
        "number_of_linked_applications": context.number_of_linked_applications,
        "disputed_site_count": context.disputed_site_count,
        "sites": sorted([
            {
                "site_id": s.site_id, "relationship_review_status": s.relationship_review_status,
                "capacity_known": s.capacity_known, "capacity": s.capacity,
                "application_references": sorted(s.application_references),
                # Trusted planning status/decision facts (Pre-Sample
                # Amendment) - status/decision/decision_issued_date/
                # application_category are all narrative-material (a
                # pending->granted or pending->refused/withdrawn change is
                # exactly the kind of thing a customer-facing summary must
                # not go stale on - see the amendment's own Section 8).
                # Deliberately EXCLUDES the representative Application's
                # own `reference`-independent proposal_summary text and
                # application_received date here - neither changes what
                # the summary would actually SAY (same reasoning this
                # function's own docstring already applies to last_checked/
                # source_document_url above); a trivial portal wording
                # correction or a long-past submission date being re-
                # scraped identically must not force a regeneration.
                # `reference` itself IS included - a different Application
                # becoming representative is a genuinely different fact.
                "representative_application": (
                    {
                        "reference": s.representative_application.reference,
                        "status": s.representative_application.status,
                        "decision": s.representative_application.decision,
                        "decision_issued_date": s.representative_application.decision_issued_date,
                        "application_category": s.representative_application.application_category,
                    }
                    if s.representative_application else None
                ),
                "other_applications_by_category": dict(sorted(s.other_applications_by_category.items())),
            }
            for s in context.sites
        ], key=lambda d: d["site_id"]),
        "ownership_entities": sorted([
            {
                "site_label": o.site_label, "is_residual": o.is_residual,
                "entity_name_raw": o.entity_name_raw, "role_label": o.role_label,
                "application_references": sorted(o.application_references),
            }
            for o in context.ownership_entities
        ], key=lambda d: (d["site_label"], d["entity_name_raw"], d["role_label"])),
        "ownership_review_pending_count": context.ownership_review_pending_count,
        "residual_ownership_known": context.residual_ownership_known,
        # Allocation Party Evidence Pre-Merge Amendment ("Multi-Application
        # Party Intelligence") - a later-discovered/corrected applicant, or
        # a materially different set of supporting Application references
        # for one, is narrative-material (test #16: "applicant changes move
        # fingerprint") and must trigger regeneration; a portal placeholder
        # variant cleaning to the same name/reference set must not (test
        # #17), which falls out for free since _clean_applicant_name has
        # already run by the time this list is built.
        "applicant_evidence": sorted([
            {
                "site_label": e.site_label, "entity_name": e.entity_name,
                "application_references": sorted(e.application_references),
            }
            for e in context.applicant_evidence
        ], key=lambda d: (d["site_label"], d["entity_name"])),
    }
    canonical = json.dumps(fingerprint_source, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def should_regenerate_allocation_summary(
    summary: AllocationIntelligenceSummary | None, fingerprint: str, *, force: bool = False,
) -> bool:
    """Section 7's exact regeneration triggers, mirroring app.reporting.
    local_plan_summary.should_regenerate: an explicit force, no summary has
    ever been generated (summary is None, or exists but was never
    successfully written - headline is None), the trusted context has
    genuinely changed since the last generation, or the prompt/model
    version has moved on. Nothing else - a routine check that finds
    nothing new must NOT trigger this. This is the ONE mechanism that makes
    "new Application ingested -> relationship established -> context
    changes -> summary marked stale" (Section 6) true - deliberately NOT a
    persisted boolean flag flipped by some other part of the ingestion
    pipeline (Section 7: "prefer a fingerprint over scattering ad-hoc
    mark-stale writes"). A newly-ingested Application only ever makes an
    allocation's summary stale once it has been linked through the trusted
    AllocationSiteRelationship architecture and therefore actually changes
    the fingerprint above - an Application for an unrelated Site changes
    nothing here at all.

    Takes the AllocationIntelligenceSummary row directly (Pre-Merge
    Architecture Amendment - previously took the LocalPlanSite itself, back
    when the summary fields lived on it) - `summary` is None for an
    allocation that has never had a row written for it at all, distinct
    from a row that exists but never successfully generated (headline is
    None) - both are treated identically here (always regenerate), the
    distinction only matters to get_allocation_summary's caller, never to
    this decision."""
    if force:
        return True
    if summary is None or summary.headline is None:
        return True
    if summary.context_fingerprint != fingerprint:
        return True
    if summary.prompt_version != PROMPT_VERSION:
        return True
    return False


def is_allocation_summary_stale(session: Session, allocation: LocalPlanSite) -> bool:
    """True when the allocation's LIVE context has moved since its summary
    was last generated, without generating anything or calling the AI.
    False (not stale) when there is no summary at all yet - that is a
    "missing" state for the caller to handle separately, not a staleness
    one (mirrors app.reporting.local_plan_summary.is_summary_stale)."""
    summary = get_allocation_summary(session, allocation.id)
    if summary is None or summary.headline is None:
        return False
    context = build_allocation_context(session, allocation)
    return compute_context_fingerprint(context) != summary.context_fingerprint


# --- Prompt / structured schema (Sections 10-15) ----------------------------


_CAPACITY_ACCOUNTING_LABELS = {
    "ok": "confidently accounted for",
    "no_activity": "no identified planning activity",
    "capacity_unknown": "the allocation's own total capacity is not stated",
    "review_required": "accounting requires review (see uncertainties)",
}


def _render_representative_application(rep: RepresentativeApplicationDetail) -> str:
    """The trusted planning ACTIVITY/OUTCOME facts for the one Application
    that already determines this Site's capacity figure - status/decision
    are raw portal facts, never a construction/delivery signal (see
    build_summary_prompt's own RULES for how the model must use these)."""
    category_bit = f", category: {rep.application_category}" if rep.application_category else ""
    status_bit = rep.status or "status not stated"
    decision_bit = rep.decision or "no decision recorded yet"
    date_bit = f", decision dated {rep.decision_issued_date}" if rep.decision_issued_date else ""
    proposal_bit = f" Proposal: {rep.proposal_summary}" if rep.proposal_summary else ""
    return (
        f"    Representative Application {rep.reference} - status: {status_bit}, decision: {decision_bit}{date_bit}{category_bit}."
        f"{proposal_bit}"
    )


def _render_site_line(s: SiteContextEntry) -> str:
    if s.relationship_review_status == "needs_confirmation":
        # Final Pre-Merge Amendment (Section 3B/7) - a disputed Site is
        # never described with the SAME "Linked Application(s): ..."
        # wording trusted Sites get, even to say "none" - this Site MAY
        # have linked Applications, they are simply withheld pending
        # confirmation, and saying "no linked Application" would be a
        # false statement, not just an unhedged one. No capacity,
        # reference, status, or decision of any kind appears here -
        # SiteContextEntry itself never carries them for a disputed Site
        # (see build_allocation_context).
        return (
            f"- Site \"{s.label}\" [RELATIONSHIP STILL PENDING CONFIRMATION - do not present as settled]: "
            f"potential planning activity may exist, but this Site's link to the allocation is unconfirmed - "
            f"do not describe any capacity, Application, status, or decision for it."
        )

    status_bit = {
        "auto_applied": "trusted relationship",
        "confirmed": "human-confirmed relationship",
    }.get(s.relationship_review_status, s.relationship_review_status)
    cap_bit = f"{s.capacity:,} homes identified" if s.capacity_known else "capacity not yet determined"
    # Section 6 - listing every reference is fine for the common small
    # case, but for a Site with many Applications (Heald Green West's real
    # ~30) even a bare reference list starts to invite exhaustive
    # enumeration; above a small threshold, name only the count - the
    # representative Application and category breakdown lines below
    # already give the model everything it needs.
    if not s.application_references:
        apps_bit = "no linked Application"
    elif len(s.application_references) <= 5:
        apps_bit = ", ".join(s.application_references)
    else:
        apps_bit = f"{len(s.application_references)} linked Applications (see representative Application and category breakdown below)"
    lines = [f"- Site \"{s.label}\" [{status_bit}]: {cap_bit}. Linked Application(s): {apps_bit}."]
    if s.representative_application:
        lines.append(_render_representative_application(s.representative_application))
    if s.other_applications_by_category:
        # Section 6 - a bounded count, never one line per Application (the
        # real Heald Green West case has ~30 linked Applications; this is
        # the mechanism that keeps the prompt from becoming an Application
        # register regardless of how many secondary filings exist).
        counts_bit = ", ".join(f"{count} {category}" for category, count in sorted(s.other_applications_by_category.items()))
        lines.append(f"    Plus {sum(s.other_applications_by_category.values())} further Application(s) on this Site ({counts_bit}) - do not narrate these individually.")
    return "\n".join(lines)


def _ownership_scope_label(o: OwnershipContextEntry) -> str:
    """The single canonical string naming WHERE an ownership/control fact
    applies - shared verbatim between the rendered prompt line (below) and
    validate_summary_output's grounding check (Evidence-Grounded Validation
    Architecture Amendment, Section 11 "site-scope grounding") - the model
    is asked to self-report this exact string back for each entity it
    names, so a claim naming the wrong scope (or the allocation as a
    whole) simply cannot match any allowed (entity, role, scope) tuple."""
    return "the allocation's residual (unaccounted-for) capacity" if o.is_residual else f'Site "{o.site_label}"'


def _render_ownership_line(o: OwnershipContextEntry) -> str:
    scope = _ownership_scope_label(o)
    apps_bit = f" (evidenced via {', '.join(o.application_references)})" if o.application_references else ""
    return f"- For {scope}: {o.entity_name_raw} - role: {o.role_label}{apps_bit}."


# Allocation Party Evidence Pre-Merge Amendment ("Multi-Application Party
# Intelligence") - Applicant is deliberately NOT an OwnershipContextEntry:
# its evidence source (Application.applicant_name_raw, a portal scrape) is
# a different, weaker, Application-submission fact than a ControlRelationship
# row (a certificate declaration or S106-defined role), and this codebase's
# own established discipline (see ControlRelationship's "CURRENT VS
# HISTORICAL" class docstring) is to keep evidence classes honestly distinct
# rather than merge them into one shape. The applicant's SCOPE STRING is
# still deliberately identical in form to _ownership_scope_label's own Site
# case (`Site "{label}"`) - the model already knows this exact phrase from
# the OWNERSHIP/CONTROL section, so reusing it (rather than inventing a
# second scope vocabulary) costs nothing new to learn and keeps validate_
# summary_output's triple-check mechanism uniform across both evidence
# sources.
def _applicant_scope_label(e: ApplicantPartyEvidence) -> str:
    return f'Site "{e.site_label}"'


def _render_applicant_line(e: ApplicantPartyEvidence) -> str:
    refs_bit = ", ".join(e.application_references)
    if e.application_count == 1:
        provenance = f"named on Application {refs_bit}'s own form"
    else:
        provenance = f"named as applicant on {e.application_count} linked Applications: {refs_bit}"
    return f"- For {_applicant_scope_label(e)}: {e.entity_name} - role: Applicant ({provenance})."


def _allowed_party_facts(context: AllocationIntelligenceContext) -> dict[tuple[str, str, str], set[str]]:
    """(entity name, role label, scope) -> the set of Application references
    that specific claim may be tied to (Section 5/8 - a self-report may
    optionally name ONE specific supporting Application; if it does, that
    reference must genuinely belong to this entity/role/scope's own
    evidence). Unifies ownership/control entities (OwnershipContextEntry)
    and applicant evidence (ApplicantPartyEvidence) into ONE lookup so
    validate_summary_output's referenced_entities check is a single
    mechanism regardless of which evidence source a claim comes from -
    "real applicant claimed as Developer without developer evidence" is
    rejected here for free: (name, "Developer", scope) is simply never a
    key in this dict unless a SEPARATE, independently-evidenced
    ControlRelationship row grants it, entirely unaffected by how many
    Applications name that same entity as Applicant."""
    facts: dict[tuple[str, str, str], set[str]] = {}
    for o in context.ownership_entities:
        key = (o.entity_name_raw, o.role_label, _ownership_scope_label(o))
        facts.setdefault(key, set()).update(o.application_references)
    for e in context.applicant_evidence:
        key = (e.entity_name, "Applicant", _applicant_scope_label(e))
        facts.setdefault(key, set()).update(e.application_references)
    return facts


def build_summary_prompt(context: AllocationIntelligenceContext) -> str:
    site_lines = "\n".join(_render_site_line(s) for s in context.sites) or "- No related Sites currently identified."
    ownership_lines = "\n".join(_render_ownership_line(o) for o in context.ownership_entities) or (
        "- No confirmed ownership/control evidence currently identified for this allocation."
    )
    applicant_lines = "\n".join(_render_applicant_line(e) for e in context.applicant_evidence) or (
        "- No applicant evidence currently identified from any related Site's trusted linked Applications."
    )

    return f"""
You are writing a concise internal briefing on ONE UK Local Plan housing
allocation, for a housebuilder/land buyer/developer/land promoter/development
consultant, using ONLY the verified PropertyAIgent evidence given below.
Every fact below has already been extracted and validated by this platform.

Your job is genuine synthesis, not a copy-paste exercise: prioritise what
matters, connect related facts, explain what they mean commercially, and
distinguish settled fact from open uncertainty. Ordinary connective language,
your own phrasing, and reasonable interpretation of the evidence are all
expected and welcome - you are not restricted to a fixed vocabulary or
sentence shape. The one hard boundary is MATERIAL FACTUAL CLAIMS - a number,
an Application reference, an organisation name, a role, a planning status or
decision - which must always be the exact facts given below, never invented,
altered, or recomputed. You may write "DC/084620 was granted" as ordinary
prose; you may not write about an Application, capacity, or entity that
isn't listed below.

ALLOCATION: {context.allocation_name} ({context.allocation_reference or 'no policy reference stated'})
COUNCIL: {context.council_name}
LOCAL PLAN: {context.local_plan_name or 'not stated'}
PLANNING STATUS: {context.plan_status_label.upper()} (this is the ONLY trusted classification of this allocation's stage - never describe it as adopted unless this literally says ADOPTED)
INTENDED USE: {context.intended_use or 'not stated'}
ALLOCATION CAPACITY (the allocation's own TOTAL stated capacity - never linked-application units, Site capacity, or residual capacity): {context.allocation_capacity_display}

DEVELOPMENT COVERAGE (deterministic, already computed - do NOT recalculate any of these numbers yourself):
- Identified planning application capacity: {context.identified_application_capacity if context.identified_application_capacity is not None else 'not determined'}
- Indicative residual allocation capacity: {context.indicative_residual_capacity if context.indicative_residual_capacity is not None else 'not determined'} (this term is the ONLY acceptable way to describe this figure - NEVER call it "available land", "developable land", "opportunity capacity", "deliverable capacity", or "consentable capacity")
- Development coverage percentage: {f'{context.development_coverage_percentage:.0%}' if context.development_coverage_percentage is not None else 'not determined'}
- Coverage classification: {context.development_coverage_classification}
- Capacity accounting status: {_CAPACITY_ACCOUNTING_LABELS.get(context.capacity_accounting_status, context.capacity_accounting_status)}
- Related Sites: {context.number_of_related_sites}, linked Applications: {context.number_of_linked_applications}
{f"- {context.disputed_site_count} Site relationship(s) remain subject to review - do not present as confirmed." if context.disputed_site_count else ""}

RELATED SITES (each independently evidenced - a Site relates to THIS allocation, never assume it covers the whole allocation):
{site_lines}

APPLICANT EVIDENCE (who has submitted planning applications relating to a Site, aggregated across ALL of that Site's trusted linked Applications - not only the representative one; being named as applicant, on one Application or many, does NOT by itself mean this party is the developer, promoter, landowner, or "behind" the wider scheme; see Rule 2):
{applicant_lines}

OWNERSHIP/CONTROL EVIDENCE (Section 13 - each fact below is scoped to the exact Site or residual-capacity context named, NEVER the allocation as a whole - never say an entity "owns the allocation", only that ownership/control evidence for a NAMED Site or the residual capacity names that entity in that role):
{ownership_lines}
{f"- {context.ownership_review_pending_count} additional ownership/control relationship(s) exist but remain subject to review - do not name the entity or role, only note that review is pending." if context.ownership_review_pending_count else ""}
{"- No ownership/control evidence currently identified for the allocation's residual (unaccounted-for) capacity - you may state this plainly, it is commercially useful information." if not context.residual_ownership_known and context.indicative_residual_capacity else ""}

RULES - follow every one of these exactly:
1. Never invent a number, Application reference, organisation name, planning status, decision, or role not given above, and never recompute a capacity/coverage figure - every one you might want is already given above.
2. Use role labels EXACTLY as given (e.g. "S106 Owner", "S106 Developer", "S106 Mortgagee", "Planning ownership declaration", "Applicant") - never upgrade, downgrade, or relabel a role (an applicant is never a developer, promoter, or owner - you may note commercially that a company is "named as applicant", never that it "is developing" or "owns" anything unless a stronger role label is separately given for it; a mortgagee is never an owner; a planning ownership declaration is never "the current owner"; a planning agent is never a promoter; never use the word "promoter" unless a role label above literally contains it). The SAME entity may legitimately hold more than one role above (e.g. named as Applicant AND, separately, as S106 Developer) - only ever narrate the roles it is actually given, never merge them into a single stronger claim. An applicant named on many linked Applications for a Site is still only Applicant evidence, however many - frequency is a fact you may mention (e.g. "named as applicant on 4 linked applications"), never a reason to imply a stronger role.
3. A Site relationship or ownership/control relationship marked as pending confirmation/review must be described as uncertain, never as a settled or confirmed fact - do not name any entity or role that was excluded above as "still under review".
4. Do NOT mention any other Local Plan allocation, policy reference, or nearby/adjoining site by name or code under any circumstances, even if you think one might be nearby - this platform does not currently hold trusted adjacency evidence.
5. Never describe this allocation as adopted unless the PLANNING STATUS line above literally says ADOPTED.
6. Ownership/control evidence is always scoped to the specific Site or residual-capacity context it is given for above - never generalise it to "the allocation" as a whole; when you name an entity, the SCOPE you describe it in (which Site, or the residual capacity) must match exactly what is given above for that entity.
7. key_uncertainties should name the specific pending-review counts, unknown capacity, or missing ownership evidence above that limit confidence - be specific, not generic.
8. investigation_priorities must each be directly traceable to a fact given above (e.g. investigate the residual capacity, investigate a pending relationship) - never a generic planning-consultant opinion, never a legal conclusion, never marketing language.
9. PLANNING ACTIVITY is never the same thing as PLANNING OUTCOME. A Site having a linked Application (live, registered, or under consultation) demonstrates planning activity - it does NOT by itself mean planning permission exists, and it never means the development is consented, under construction, delivered, implemented, or completed. State the Application's actual status/decision (given above) rather than assuming one from the fact that an Application merely exists.
10. Only describe an Application as having planning permission/consent if its stated decision above literally says so (e.g. "Granted"). A refused or withdrawn Application remains real, relevant planning history - describe it accurately as refused/withdrawn, never as ongoing or successful.
11. Never describe an Application, or the allocation, as under construction, built, delivered, or completed - PropertyAIgent does not hold construction/delivery evidence; a granted planning permission is still only a planning permission.
12. Never infer an Application's status or decision from the identified/residual capacity figures or the development coverage percentage above - those are pure capacity arithmetic and carry no planning-outcome information on their own. If a large share of an allocation's capacity is "identified" via an Application that is still pending/under consultation, say so explicitly - do not let the size of the figure imply the application has been decided.
13. If a Site's further Applications are given only as a category count (never individually narrated), do not enumerate or speculate about them - one sentence acknowledging the volume (e.g. "a further N applications relate to this Site, mostly condition-discharge/technical filings") is enough; never produce anything resembling a list of every Application.
14. referenced_applications and referenced_entities (described below) are your own structured self-report of every material claim you made anywhere in headline/overview/key_points/key_uncertainties/investigation_priorities - used for automatic fact-checking. This is bookkeeping, not composition - it does not constrain how you write the prose above. referenced_entities covers ONLY parties from the APPLICANT EVIDENCE or OWNERSHIP/CONTROL EVIDENCE sections above (applicants, owners, developers, mortgagees, etc.) - it does NOT include the council name, the Local Plan name, or any other proper noun that appears elsewhere in this brief; those are not party claims and do not need self-reporting.
15. Where an Application's decision above is genuinely not yet recorded, you are free to say so in plain language ("no decision has yet been issued", "the application remains undetermined", "a decision is still pending", or your own equivalent phrasing) - this is a grounded, useful fact, not an invented one. Self-report it via decision_claim_mode="absent" (see below) rather than inventing a decision value. Never make such a claim for an Application whose decision above is already a real value (Granted/Refused/Withdrawn/etc.) - that Application has been decided, and the decision given above is the only thing you may say about it.

Write:
- headline: one short sentence (under 15 words) capturing the allocation's overall commercial position.
- overview: 2-3 short paragraphs, plain prose, no markdown headers, covering: what this allocation is and its planning status/scale; what planning activity has been identified, its actual status/decision, and how much capacity is accounted for versus indicative residual capacity (distinguishing identified activity from a determined planning outcome per Rules 9-12); what ownership/control evidence exists and for which Site(s); material uncertainties.
- key_points: 3-5 concise bullet-style facts (each a short sentence).
- key_uncertainties: 0-4 concise items (empty list if genuinely none).
- investigation_priorities: 0-3 concise items (empty list if genuinely none).
- referenced_applications: one entry for every Application reference you named anywhere above, each with:
  - reference: the Application reference, exactly as given.
  - claimed_status: if you stated its planning status anywhere above, the EXACT status value as given above for that Application; otherwise "".
  - claimed_decision: if you stated its decision anywhere above AS A SPECIFIC VALUE (e.g. "Granted"), the EXACT decision value as given above for that Application; otherwise "".
  - decision_claim_mode: "value" if claimed_decision above is a specific decision value you stated; "absent" if you said/implied the decision is not yet recorded (Rule 15) - leave claimed_decision "" in this case, your own wording is not checked word-for-word; "none" if you made no claim about this Application's decision at all.
- referenced_entities: one entry for every APPLICANT/OWNERSHIP/CONTROL party you named anywhere above (never the council or Local Plan name), each with:
  - name: the entity name, exactly as given.
  - role: its role label, exactly as given (e.g. "Applicant", "S106 Developer", "Planning ownership declaration").
  - site_scope: exactly the scope text given above for that entity (e.g. Site "Land At Wilmslow Road Heald Green Stockport", or "the allocation's residual (unaccounted-for) capacity") - never "the allocation" as a whole.
  - application_reference: if you named ONE SPECIFIC Application reference in connection with this party (e.g. "named as applicant on DC/078180"), that exact reference; if you only described the party generally (e.g. "named as applicant on several linked applications", with no single reference singled out), "".
"""


SUMMARY_SCHEMA = {
    "name": "allocation_intelligence_summary",
    "schema": {
        "type": "object",
        "properties": {
            "headline": {"type": "string"},
            "overview": {"type": "string"},
            "key_points": {"type": "array", "items": {"type": "string"}},
            "key_uncertainties": {"type": "array", "items": {"type": "string"}},
            "investigation_priorities": {"type": "array", "items": {"type": "string"}},
            # Evidence-Grounded Validation Architecture Amendment - replaces
            # the three flat, independently-validated string lists this
            # schema previously had (referenced_application_references/
            # referenced_entity_names/referenced_roles) with two structured,
            # PAIRED self-reports. A flat list could accidentally validate
            # an entity and a role that both independently exist in context
            # but are paired together WRONGLY (e.g. an Applicant reported
            # alongside a Developer role that belongs to a different
            # entity); pairing reference+status+decision and name+role+
            # site_scope together closes that gap - see validate_summary_
            # output's own docstring.
            "referenced_applications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "reference": {"type": "string"},
                        "claimed_status": {"type": "string"},
                        "claimed_decision": {"type": "string"},
                        # Final Grounding Hardening Amendment - distinguishes
                        # "I am not making a decision claim" (none) from "I
                        # am claiming a specific decision value" (value,
                        # claimed_decision must then be set) from "I am
                        # explicitly claiming no decision has been recorded"
                        # (absent, claimed_decision left "") - without this,
                        # claimed_decision="" was ambiguous between the
                        # first and third cases, so a genuinely grounded
                        # absence claim (e.g. "no decision recorded yet"
                        # when the trusted decision is None) had nothing to
                        # self-report and was rejected as an unsupported
                        # numeric-free prose claim by the free-text path -
                        # see validate_summary_output's own comment.
                        "decision_claim_mode": {"type": "string", "enum": ["none", "value", "absent"]},
                    },
                    "required": ["reference", "claimed_status", "claimed_decision", "decision_claim_mode"],
                    "additionalProperties": False,
                },
            },
            "referenced_entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "role": {"type": "string"},
                        "site_scope": {"type": "string"},
                        # Allocation Party Evidence Pre-Merge Amendment
                        # ("Multi-Application Party Intelligence", Section
                        # 8) - optional: the ONE specific Application
                        # reference this claim is tied to, if any ("" when
                        # the claim is a general one, e.g. "named as
                        # applicant on several linked applications"). Lets
                        # validate_summary_output catch "assigned to an
                        # Application where it does not occur" without
                        # ever scanning free-text prose for reference-
                        # shaped tokens.
                        "application_reference": {"type": "string"},
                    },
                    "required": ["name", "role", "site_scope", "application_reference"],
                    "additionalProperties": False,
                },
            },
        },
        "required": [
            "headline", "overview", "key_points", "key_uncertainties", "investigation_priorities",
            "referenced_applications", "referenced_entities",
        ],
        "additionalProperties": False,
    },
}


# --- Deterministic factual-grounding validation (Section 22) ---------------

# Matches only whole numbers with 2+ digits (ignoring thousands separators) -
# mirrors app.reporting.local_plan_summary's own _NUMBER_PATTERN reasoning
# exactly: single-digit numbers are excused (routine phrasing like "one
# Site" would otherwise fail every summary on harmless boilerplate that
# isn't really a claimed figure).
_NUMBER_PATTERN = re.compile(r"\d[\d,]*(?:\.\d+)?")

# Every role label in the platform's fixed vocabulary that itself
# contains a digit (see app.reporting.ownership_control._ROLE_LABEL_BY_
# EVIDENCE_CATEGORY) - masked before number extraction REGARDLESS of
# whether THIS allocation has any accepted ownership evidence at all,
# since the prompt's own RULES text teaches the model these exact
# strings verbatim (rule 2's own example list). "no S106 Developer
# evidence has been identified" is legitimate, fully grounded prose even
# when context.ownership_entities is empty - the digits in "S106" are not
# an independent numeric claim either way.
_DIGIT_BEARING_ROLE_LABELS = {"S106 Owner", "S106 Developer", "S106 Mortgagee"}


def _numbers_in(text: str) -> set[str]:
    return {m.replace(",", "") for m in _NUMBER_PATTERN.findall(text)}


def _allowed_numbers(context: AllocationIntelligenceContext) -> set[str]:
    allowed: set[str] = set()

    def _add(value) -> None:
        if value is None:
            return
        allowed.update(_numbers_in(str(value)))
        if isinstance(value, float) and value == int(value):
            allowed.add(str(int(value)))
        if isinstance(value, float):
            allowed.add(f"{value:.0%}".rstrip("%"))

    _add(context.allocation_capacity_value)
    _add(context.identified_application_capacity)
    _add(context.indicative_residual_capacity)
    _add(context.development_coverage_percentage)
    _add(context.number_of_related_sites)
    _add(context.number_of_linked_applications)
    _add(context.disputed_site_count)
    _add(context.ownership_review_pending_count)
    for s in context.sites:
        _add(s.capacity)
        if s.representative_application:
            # Evidence-Grounded Validation Architecture Amendment - a
            # decision date (e.g. "Thu 11 Jan 2024") is a genuine, trusted
            # fact the model may legitimately narrate ("granted on 11 Jan
            # 2024") - its digits must be allowed, not just its reference/
            # status/decision. Confirmed root-caused: "2024" was observed
            # rejected during controlled sample review precisely because
            # this line did not exist.
            _add(s.representative_application.decision_issued_date)
        for count in s.other_applications_by_category.values():
            _add(count)
        if s.other_applications_by_category:
            _add(sum(s.other_applications_by_category.values()))
    # Allocation Party Evidence Pre-Merge Amendment - "named as applicant on
    # 4 linked applications" is legitimate narration of a genuine, trusted
    # count (ApplicantPartyEvidence.application_count); its digit must be
    # allowed, exactly like any other Site's other_applications_by_category
    # count above.
    for e in context.applicant_evidence:
        _add(e.application_count)
    return allowed


def _allowed_application_references(context: AllocationIntelligenceContext) -> set[str]:
    allowed: set[str] = set()
    for s in context.sites:
        allowed.update(s.application_references)
    for o in context.ownership_entities:
        allowed.update(o.application_references)
    return allowed


def _allowed_entity_names(context: AllocationIntelligenceContext) -> set[str]:
    # Allocation Party Evidence Amendment - unioned with applicant names too
    # (a different evidence source than ownership_entities) so an applicant
    # company name's own digits (e.g. a name containing a house/unit number)
    # are masked before numeric-grounding, exactly like an ownership
    # entity's name already is.
    return {o.entity_name_raw for o in context.ownership_entities} | {e.entity_name for e in context.applicant_evidence}


def _representative_applications_by_reference(context: AllocationIntelligenceContext) -> dict[str, RepresentativeApplicationDetail]:
    """Only a Site's OWN representative Application carries a status/
    decision fact in context at all (RepresentativeApplicationDetail) - a
    reference appearing only in application_references/other_applications_
    by_category (a secondary, non-representative filing) has no per-
    reference status/decision available to ground a claim against, so a
    claimed_status/claimed_decision for one of those must be rejected, not
    silently accepted because the bare reference happens to be trusted."""
    return {s.representative_application.reference: s.representative_application for s in context.sites if s.representative_application}


_PARENTHETICAL_PATTERN = re.compile(r"\(([^()]+)\)")


def _trusted_label_substrings(label: str | None) -> set[str]:
    """Final Grounding Hardening Amendment - a trusted structured label
    (context.allocation_reference, context.plan_status_label) may itself
    be a compound phrase whose parenthetical qualifier is a distinct,
    independently-narratable trusted string (e.g. "Draft consultation
    (Regulation 18)" - a model may legitimately write just "Regulation 18"
    stage without repeating "Draft consultation"). Returns the whole label
    AND, for each parenthetical group found, both the bracketed content on
    its own ("Regulation 18") and the label with that exact parenthetical
    removed - so partial narration of either half of a "<phase>
    (<qualifier>)"-shaped label is masked, without masking any digit that
    is not part of a real trusted label. Generic over the shape, not tied
    to "Regulation 18"/"HOM 2.33" or any other specific value - the SAME
    rule applies to any future label carrying a parenthetical qualifier."""
    if not label:
        return set()
    substrings = {label}
    for match in _PARENTHETICAL_PATTERN.finditer(label):
        substrings.add(match.group(1).strip())
    return {s for s in substrings if s}


def _mask_known_strings(text: str, known_strings: set[str]) -> str:
    """Removes every occurrence of an already-grounded string (a trusted
    Application reference or organisation name) from `text` before number
    extraction. Evidence-Grounded Validation Architecture Amendment - root
    cause of the "084620"/"2024"/"0749" false rejections observed during
    controlled sample review: the bare number-extraction regex below has
    no concept of "these digits are part of a token I already validated
    as ONE grounded identifier" - "DC/084620" contains the digit-run
    "084620", which is not itself an independent capacity/count claim.
    Masking the whole known string out first (longest-first, so a
    reference that happens to be a substring of a longer one is never
    partially masked) means its internal digits are never independently
    extracted and checked - while an INVENTED reference (not in
    known_strings) is left untouched and its digits are still correctly
    flagged as unsupported, so this fixes the false positive without
    weakening protection against a genuinely fabricated reference."""
    for s in sorted((k for k in known_strings if k), key=len, reverse=True):
        text = text.replace(s, " ")
    return text


def validate_summary_output(context: AllocationIntelligenceContext, structured_output: dict) -> tuple[bool, list[str]]:
    """Deterministic post-generation check - rejects an output whose
    MATERIAL FACTUAL CLAIMS cannot be traced back to the context it was
    given. This validates claims, not prose tokens: ordinary connective
    language and the model's own phrasing are never checked against an
    allow-list at all (see the numeric-masking step below and the fact
    that referenced_applications/referenced_entities are the model's own
    structured self-report of what it claimed, not a free-text scan of
    the narrative fields for reference/entity/role-shaped substrings).

    Prefers the model's own structured self-report (referenced_
    applications/referenced_entities, each a PAIRED claim - reference+
    status+decision, name+role+site_scope - not three independent flat
    lists) over free-text NLP extraction for reference/entity/role/scope
    grounding; numeric grounding still scans the free text directly
    (mirroring app.reporting.local_plan_summary's own proven approach),
    but with known reference/entity strings masked out first so their
    internal digits are never treated as independent numeric claims.
    Returns (is_valid, problems) - a non-empty problems list means the
    output must be rejected, never persisted."""
    problems: list[str] = []

    allowed_refs = _allowed_application_references(context)
    allowed_entity_names = _allowed_entity_names(context)
    # Role labels ("S106 Owner", "S106 Developer", "S106 Mortgagee") also
    # contain digits ("106") that must not be independently extracted as
    # numeric claims - the exact same class of false positive as an
    # Application reference's own digits, found and fixed together with
    # that bug during this amendment's own test development.
    allowed_role_labels = {o.role_label for o in context.ownership_entities}
    # Allocation Party Evidence Amendment (Section 10), HARDENED by the
    # Final Grounding Hardening Amendment - context.allocation_reference
    # (e.g. "HOM 2.33") and context.plan_status_label (e.g. "Draft
    # consultation (Regulation 18)") are rendered VERBATIM in the prompt's
    # own ALLOCATION/PLANNING STATUS lines, so the model is all but
    # guaranteed to echo them - masking only the FULL literal label string
    # fixed the common case, but real production output (Heald Green West,
    # allocation 32) proved a model narrating just "Regulation 18" - the
    # trusted SUB-PHRASE inside the label, not the whole "Draft consultation
    # (Regulation 18)" string - never matches that whole-string mask, so
    # its "18" was still independently flagged. _trusted_label_substrings
    # below masks BOTH the whole label AND any parenthetical sub-phrase it
    # contains (generic - PLAN_STATUS_META's own "<phase> (Regulation N)"
    # shape is not the only label this could ever apply to), rather than
    # allow-listing the digit "18" itself - the fix generalises to ANY
    # trusted label carrying a parenthetical qualifier, never a one-off
    # numeric exception.
    trusted_labels: set[str] = set()
    for label in (context.allocation_reference, context.plan_status_label):
        trusted_labels.update(_trusted_label_substrings(label))
    known_strings = allowed_refs | allowed_entity_names | allowed_role_labels | _DIGIT_BEARING_ROLE_LABELS | trusted_labels

    allowed_numbers = _allowed_numbers(context)
    all_text = " ".join([
        structured_output.get("headline", ""), structured_output.get("overview", ""),
        *structured_output.get("key_points", []), *structured_output.get("key_uncertainties", []),
        *structured_output.get("investigation_priorities", []),
    ])
    masked_text = _mask_known_strings(all_text, known_strings)
    found_numbers = _numbers_in(masked_text)
    unsupported_numbers = sorted(n for n in found_numbers if len(n.lstrip("0")) >= 2 and n not in allowed_numbers)
    if unsupported_numbers:
        problems.append(f"unsupported numbers: {', '.join(unsupported_numbers)}")

    representative_by_reference = _representative_applications_by_reference(context)
    for item in structured_output.get("referenced_applications", []):
        ref = item.get("reference", "")
        if ref not in allowed_refs:
            problems.append(f"unsupported application reference: {ref}")
            continue
        rep = representative_by_reference.get(ref)
        claimed_status = item.get("claimed_status") or ""
        claimed_decision = item.get("claimed_decision") or ""
        decision_claim_mode = item.get("decision_claim_mode") or ""
        if not decision_claim_mode:
            # Backward-compatible default, EXACTLY matching this
            # function's own pre-v6 behaviour bit-for-bit: a legacy/
            # unset self-report (decision_claim_mode absent - every
            # v4/v5-era test and any real v4/v5 generation) is "value"
            # whenever claimed_decision is non-empty (checked as a
            # positive claim, as it always was) and "none" otherwise (no
            # claim, as it always was) - never silently downgraded to
            # "no check at all" just because a caller predates this field.
            decision_claim_mode = "value" if claimed_decision else "none"
        if claimed_status and (rep is None or claimed_status != (rep.status or "")):
            problems.append(f"unsupported status claim for {ref}: {claimed_status}")
        # Final Grounding Hardening Amendment - claimed_decision is only
        # checked as a POSITIVE value claim when decision_claim_mode is
        # "value" (mirrors the pre-existing behaviour exactly for that
        # mode). "absent" is a DIFFERENT, independently-grounded claim -
        # checked against the trusted decision's own truthiness, never
        # against a fixed phrase list (Rule 15: ground the material
        # MEANING, not a sentence) - genuinely rejected whenever the
        # trusted decision is actually a real value (Granted/Refused/
        # Withdrawn/etc.), so "no decision yet" can never be claimed
        # against an Application that really has been decided. "none"
        # makes no claim at all, exactly as before this amendment.
        if decision_claim_mode == "value":
            if claimed_decision and (rep is None or claimed_decision != (rep.decision or "")):
                problems.append(f"unsupported decision claim for {ref}: {claimed_decision}")
        elif decision_claim_mode == "absent":
            if rep is None or rep.decision:
                problems.append(
                    f"unsupported absence-of-decision claim for {ref}: trusted decision is "
                    f"{rep.decision if rep and rep.decision else 'not recorded'}"
                )

    # Allocation Party Evidence Pre-Merge Amendment ("Multi-Application
    # Party Intelligence") - unifies ownership/control tuples and applicant
    # tuples (a DIFFERENT evidence source, Application.applicant_name_raw,
    # never ControlRelationship) into ONE (name, role, scope) -> allowed
    # Application references lookup. This is what makes "real applicant
    # claimed as Developer without developer evidence" a rejection for
    # free: the dict only ever has a (name, "Applicant", scope) key for
    # that entity unless a SEPARATE, independent ControlRelationship-
    # sourced tuple also grants it a stronger role - never inferred, never
    # merged.
    allowed_party_facts = _allowed_party_facts(context)
    # Defensive backstop, not merely prompt wording (Section 11's own
    # "do not solve this merely with prompt wording" principle, applied
    # here too): a real production generation attempt (observed directly
    # during this amendment's own investigation) self-reported the COUNCIL
    # NAME and LOCAL PLAN NAME as "entities" - both are true, already-
    # given facts, just mis-bucketed into the wrong self-report field, not
    # a hallucination. Skip (never reject) an entry whose name exactly
    # matches one of those - the prompt's own RULE 14 now also tells the
    # model not to self-report them at all, but this is the structural
    # safety net if it does anyway.
    non_ownership_known_names = {n for n in (context.council_name, context.local_plan_name) if n}
    for item in structured_output.get("referenced_entities", []):
        name, role, site_scope = item.get("name", ""), item.get("role", ""), item.get("site_scope", "")
        if name in non_ownership_known_names:
            continue
        key = (name, role, site_scope)
        if key not in allowed_party_facts:
            problems.append(f"unsupported entity/role/scope claim: {name} / {role} / {site_scope}")
            continue
        # Multi-Application Party Intelligence, Section 8 - an OPTIONAL
        # single-Application claim ("named as applicant on DC/078180") must
        # genuinely belong to this entity/role/scope's own evidence; a
        # general claim (application_reference == "") makes no such
        # commitment and needs no further check.
        application_reference = item.get("application_reference") or ""
        if application_reference and application_reference not in allowed_party_facts[key]:
            problems.append(
                f"unsupported application reference for entity claim: {name} / {role} / {application_reference}"
            )

    return len(problems) == 0, problems


# --- Generation orchestration (Section 8) -----------------------------------


@dataclass
class AllocationSummaryResult:
    regenerated: bool
    rejected: bool
    rejection_reason: list[str] | None
    headline: str | None
    overview: str | None
    key_points: list[str]
    key_uncertainties: list[str]
    investigation_priorities: list[str]
    generated_at: dt.datetime | None
    model: str | None
    prompt_version: str | None
    status: str | None
    generation_error: str | None


def _persisted_summary_result(summary: AllocationIntelligenceSummary, *, regenerated: bool, rejected: bool, rejection_reason: list[str] | None) -> AllocationSummaryResult:
    return AllocationSummaryResult(
        regenerated=regenerated, rejected=rejected, rejection_reason=rejection_reason,
        headline=summary.headline, overview=summary.overview,
        key_points=json.loads(summary.key_points) if summary.key_points else [],
        key_uncertainties=json.loads(summary.key_uncertainties) if summary.key_uncertainties else [],
        investigation_priorities=json.loads(summary.investigation_priorities) if summary.investigation_priorities else [],
        generated_at=summary.generated_at, model=summary.model,
        prompt_version=summary.prompt_version, status=summary.status,
        generation_error=summary.generation_error,
    )


def generate_allocation_intelligence_summary(
    session: Session, client, allocation: LocalPlanSite, *, force: bool = False,
) -> AllocationSummaryResult:
    """The one orchestration entry point (Section 8). Only calls the AI
    model when should_regenerate_allocation_summary says a real trigger
    applies - an allocation re-viewed or re-checked with no new evidence
    costs nothing. A rejected (ungrounded) output, or a raw client
    exception, NEVER overwrites the last successful summary (Section 22:
    "if validation fails, do not replace the last valid summary") - only
    status/generation_error record that the most recent attempt failed.

    Gets-or-creates the ONE AllocationIntelligenceSummary row for this
    allocation (Pre-Merge Architecture Amendment - previously wrote
    directly onto the LocalPlanSite row) - a brand-new row is added but
    left entirely without headline/overview/... until a generation
    actually succeeds, so "row exists but headline is None" and "row does
    not exist yet" both correctly mean "no summary has ever been
    generated" (see should_regenerate_allocation_summary)."""
    context = build_allocation_context(session, allocation)
    fingerprint = compute_context_fingerprint(context)

    summary = get_allocation_summary(session, allocation.id)
    if not should_regenerate_allocation_summary(summary, fingerprint, force=force):
        return _persisted_summary_result(summary, regenerated=False, rejected=False, rejection_reason=None)

    if summary is None:
        summary = AllocationIntelligenceSummary(allocation_id=allocation.id)
        session.add(summary)

    prompt = build_summary_prompt(context)
    try:
        response = client.responses.create(
            model=MODEL, input=prompt,
            text={"format": {"type": "json_schema", "name": SUMMARY_SCHEMA["name"], "schema": SUMMARY_SCHEMA["schema"], "strict": True}},
        )
        structured = json.loads(response.output_text)
    except Exception as e:
        summary.status = "error"
        summary.generation_error = str(e)[:2000]
        session.commit()
        return _persisted_summary_result(summary, regenerated=False, rejected=False, rejection_reason=None)

    is_valid, problems = validate_summary_output(context, structured)
    if not is_valid:
        summary.status = "error"
        summary.generation_error = "; ".join(problems)[:2000]
        session.commit()
        return _persisted_summary_result(summary, regenerated=False, rejected=True, rejection_reason=problems)

    now = dt.datetime.now(dt.timezone.utc)
    summary.headline = structured["headline"]
    summary.overview = structured["overview"]
    summary.key_points = json.dumps(structured["key_points"])
    summary.key_uncertainties = json.dumps(structured["key_uncertainties"])
    summary.investigation_priorities = json.dumps(structured["investigation_priorities"])
    summary.generated_at = now
    summary.context_fingerprint = fingerprint
    summary.model = MODEL
    summary.prompt_version = PROMPT_VERSION
    summary.status = "ok"
    summary.generation_error = None
    session.commit()

    return AllocationSummaryResult(
        regenerated=True, rejected=False, rejection_reason=None,
        headline=structured["headline"], overview=structured["overview"],
        key_points=structured["key_points"], key_uncertainties=structured["key_uncertainties"],
        investigation_priorities=structured["investigation_priorities"],
        generated_at=now, model=MODEL, prompt_version=PROMPT_VERSION,
        status="ok", generation_error=None,
    )
