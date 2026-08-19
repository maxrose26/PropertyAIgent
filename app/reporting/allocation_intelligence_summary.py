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
    -> persisted on LocalPlanSite.ai_summary_* (additive columns only -
       never overwrites a source field)
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

from sqlalchemy.orm import Session

from app.db.models import LocalPlanSite
from app.reporting.allocation_development_coverage import build_allocation_development_coverage
from app.reporting.allocation_discovery import format_capacity
from app.reporting.ownership_control import get_allocation_control_intelligence

MODEL = "gpt-4o-mini"
# Bumped whenever the prompt or schema changes in a way that could change
# the generated summary - persisted on every summary (mirrors
# app.reporting.local_plan_summary.PROMPT_VERSION exactly) so a version
# bump alone never retroactively invalidates an already-generated summary
# until it is actually next regenerated.
PROMPT_VERSION = "allocation-intelligence-summary-v1"


# --- Context object (Section 4) ---------------------------------------------


@dataclass
class SiteContextEntry:
    site_id: int
    label: str
    relationship_review_status: str  # auto_applied | needs_confirmation | confirmed
    capacity_known: bool
    capacity: int | None
    application_references: list[str] = field(default_factory=list)
    representative_application_reference: str | None = None


@dataclass
class OwnershipContextEntry:
    site_label: str
    is_residual: bool
    entity_name_raw: str
    role_label: str
    application_references: list[str] = field(default_factory=list)


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

    source_document_url: str | None = None
    source_page: int | None = None
    last_checked: str | None = None


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
    for s in site_summaries:
        if s.relationship_review_status == "needs_confirmation":
            disputed_site_count += 1
        sites.append(SiteContextEntry(
            site_id=s.site_id, label=s.site.display_address,
            relationship_review_status=s.relationship_review_status,
            capacity_known=s.capacity_known, capacity=s.capacity,
            application_references=sorted({a.reference for a in s.applications}),
            representative_application_reference=(
                s.representative_application.reference if s.representative_application else None
            ),
        ))

    control_sections = get_allocation_control_intelligence(
        session, site_summaries,
        indicative_residual_capacity=coverage.indicative_residual_capacity if coverage else None,
    )
    ownership_entities: list[OwnershipContextEntry] = []
    ownership_review_pending_count = 0
    residual_ownership_known = False
    for section in control_sections:
        for group in section.groups:
            if group.needs_review:
                # Section 14 - a disputed ownership/control group is NEVER
                # named as a fact, only counted as an uncertainty signal.
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
        source_document_url=allocation.source_document_url,
        source_page=allocation.source_page,
        last_checked=plan.last_checked.isoformat() if plan and plan.last_checked else None,
    )


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
    }
    canonical = json.dumps(fingerprint_source, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def should_regenerate_allocation_summary(allocation: LocalPlanSite, fingerprint: str, *, force: bool = False) -> bool:
    """Section 7's exact regeneration triggers, mirroring app.reporting.
    local_plan_summary.should_regenerate: an explicit force, no summary has
    ever been generated, the trusted context has genuinely changed since
    the last generation, or the prompt/model version has moved on. Nothing
    else - a routine check that finds nothing new must NOT trigger this.
    This is the ONE mechanism that makes "new Application ingested ->
    relationship established -> context changes -> summary marked stale"
    (Section 6) true - deliberately NOT a persisted boolean flag flipped by
    some other part of the ingestion pipeline (Section 7: "prefer a
    fingerprint over scattering ad-hoc mark-stale writes"). A newly-ingested
    Application only ever makes an allocation's summary stale once it has
    been linked through the trusted AllocationSiteRelationship architecture
    and therefore actually changes the fingerprint above - an Application
    for an unrelated Site changes nothing here at all."""
    if force:
        return True
    if allocation.ai_summary_headline is None:
        return True
    if allocation.ai_summary_context_fingerprint != fingerprint:
        return True
    if allocation.ai_summary_prompt_version != PROMPT_VERSION:
        return True
    return False


def is_allocation_summary_stale(session: Session, allocation: LocalPlanSite) -> bool:
    """True when the allocation's LIVE context has moved since its summary
    was last generated, without generating anything or calling the AI.
    False (not stale) when there is no summary at all yet - that is a
    "missing" state for the caller to handle separately, not a staleness
    one (mirrors app.reporting.local_plan_summary.is_summary_stale)."""
    if allocation.ai_summary_headline is None:
        return False
    context = build_allocation_context(session, allocation)
    return compute_context_fingerprint(context) != allocation.ai_summary_context_fingerprint


# --- Prompt / structured schema (Sections 10-15) ----------------------------


_CAPACITY_ACCOUNTING_LABELS = {
    "ok": "confidently accounted for",
    "no_activity": "no identified planning activity",
    "capacity_unknown": "the allocation's own total capacity is not stated",
    "review_required": "accounting requires review (see uncertainties)",
}


def _render_site_line(s: SiteContextEntry) -> str:
    status_bit = {
        "auto_applied": "trusted relationship",
        "confirmed": "human-confirmed relationship",
        "needs_confirmation": "RELATIONSHIP STILL PENDING CONFIRMATION - do not present as settled",
    }.get(s.relationship_review_status, s.relationship_review_status)
    cap_bit = f"{s.capacity:,} homes identified" if s.capacity_known else "capacity not yet determined"
    apps_bit = ", ".join(s.application_references) if s.application_references else "no linked Application"
    return f"- Site \"{s.label}\" [{status_bit}]: {cap_bit}. Linked Application(s): {apps_bit}."


def _render_ownership_line(o: OwnershipContextEntry) -> str:
    scope = "the allocation's residual (unaccounted-for) capacity" if o.is_residual else f'Site "{o.site_label}"'
    apps_bit = f" (evidenced via {', '.join(o.application_references)})" if o.application_references else ""
    return f"- For {scope}: {o.entity_name_raw} - role: {o.role_label}{apps_bit}."


def build_summary_prompt(context: AllocationIntelligenceContext) -> str:
    site_lines = "\n".join(_render_site_line(s) for s in context.sites) or "- No related Sites currently identified."
    ownership_lines = "\n".join(_render_ownership_line(o) for o in context.ownership_entities) or (
        "- No confirmed ownership/control evidence currently identified for this allocation."
    )

    return f"""
You are writing a concise internal briefing on ONE UK Local Plan housing
allocation, for a housebuilder/land buyer/developer/land promoter/development
consultant, using ONLY the verified PropertyAIgent evidence given below.
Every fact below has already been extracted and validated by this platform -
restate and synthesise it, never invent a fact, figure, Application
reference, or organisation name that isn't given here.

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

OWNERSHIP/CONTROL EVIDENCE (Section 13 - each fact below is scoped to the exact Site or residual-capacity context named, NEVER the allocation as a whole - never say an entity "owns the allocation", only that ownership/control evidence for a NAMED Site or the residual capacity names that entity in that role):
{ownership_lines}
{f"- {context.ownership_review_pending_count} additional ownership/control relationship(s) exist but remain subject to review - do not name the entity or role, only note that review is pending." if context.ownership_review_pending_count else ""}
{"- No ownership/control evidence currently identified for the allocation's residual (unaccounted-for) capacity - you may state this plainly, it is commercially useful information." if not context.residual_ownership_known and context.indicative_residual_capacity else ""}

RULES - follow every one of these exactly:
1. Never invent a number, Application reference, organisation name, or role not given above.
2. Never perform arithmetic yourself - every capacity/coverage figure you might want is already given above; never derive a new one.
3. Use role labels EXACTLY as given (e.g. "S106 Owner", "S106 Developer", "S106 Mortgagee", "Planning ownership declaration", "Applicant evidence") - never upgrade, downgrade, or relabel a role (an applicant is never a developer; a mortgagee is never an owner; a planning ownership declaration is never "the current owner"; a planning agent is never a promoter; never use the word "promoter" unless a role label above literally contains it).
4. A Site relationship or ownership/control relationship marked as pending confirmation/review must be described as uncertain, never as a settled or confirmed fact - do not name any entity or role that was excluded above as "still under review".
5. Do NOT mention any other Local Plan allocation, policy reference, or nearby/adjoining site by name or code under any circumstances, even if you think one might be nearby - this platform does not currently hold trusted adjacency evidence.
6. Never describe this allocation as adopted unless the PLANNING STATUS line above literally says ADOPTED.
7. Ownership/control evidence is always scoped to the specific Site or residual-capacity context it is given for above - never generalise it to "the allocation" as a whole.
8. key_uncertainties should name the specific pending-review counts, unknown capacity, or missing ownership evidence above that limit confidence - be specific, not generic.
9. investigation_priorities must each be directly traceable to a fact given above (e.g. investigate the residual capacity, investigate a pending relationship) - never a generic planning-consultant opinion, never a legal conclusion, never marketing language.
10. referenced_application_references, referenced_entity_names, and referenced_roles must each list EVERY Application reference / organisation name / role label you used anywhere in headline, overview, key_points, key_uncertainties, or investigation_priorities - used for automatic fact-checking, so be complete and exact.

Write:
- headline: one short sentence (under 15 words) capturing the allocation's overall commercial position.
- overview: 2-3 short paragraphs, plain prose, no markdown headers, covering: what this allocation is and its planning status/scale; what planning activity has been identified and how much capacity is accounted for versus indicative residual capacity; what ownership/control evidence exists and for which Site(s); material uncertainties.
- key_points: 3-5 concise bullet-style facts (each a short sentence).
- key_uncertainties: 0-4 concise items (empty list if genuinely none).
- investigation_priorities: 0-3 concise items (empty list if genuinely none).
- referenced_application_references: every Application reference used above, exactly as given.
- referenced_entity_names: every organisation/entity name used above, exactly as given.
- referenced_roles: every role label used above, exactly as given.
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
            "referenced_application_references": {"type": "array", "items": {"type": "string"}},
            "referenced_entity_names": {"type": "array", "items": {"type": "string"}},
            "referenced_roles": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "headline", "overview", "key_points", "key_uncertainties", "investigation_priorities",
            "referenced_application_references", "referenced_entity_names", "referenced_roles",
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
    return allowed


def _allowed_application_references(context: AllocationIntelligenceContext) -> set[str]:
    allowed: set[str] = set()
    for s in context.sites:
        allowed.update(s.application_references)
    for o in context.ownership_entities:
        allowed.update(o.application_references)
    return allowed


def _allowed_entity_names(context: AllocationIntelligenceContext) -> set[str]:
    return {o.entity_name_raw for o in context.ownership_entities}


def _allowed_roles(context: AllocationIntelligenceContext) -> set[str]:
    return {o.role_label for o in context.ownership_entities}


def validate_summary_output(context: AllocationIntelligenceContext, structured_output: dict) -> tuple[bool, list[str]]:
    """Deterministic post-generation check (Section 22) - rejects an output
    whose claims cannot be traced back to the context it was given. Prefers
    the model's own structured self-report (referenced_application_
    references/referenced_entity_names/referenced_roles) over free-text
    NLP extraction for entity/reference/role grounding - Section 22's own
    closing instruction ("prefer structured generation that makes this
    validation straightforward"); numeric grounding still scans the free
    text directly, mirroring app.reporting.local_plan_summary's own proven
    approach. Returns (is_valid, problems) - a non-empty problems list means
    the output must be rejected, never persisted."""
    problems: list[str] = []

    allowed_numbers = _allowed_numbers(context)
    all_text = " ".join([
        structured_output.get("headline", ""), structured_output.get("overview", ""),
        *structured_output.get("key_points", []), *structured_output.get("key_uncertainties", []),
        *structured_output.get("investigation_priorities", []),
    ])
    found_numbers = _numbers_in(all_text)
    unsupported_numbers = sorted(n for n in found_numbers if len(n.lstrip("0")) >= 2 and n not in allowed_numbers)
    if unsupported_numbers:
        problems.append(f"unsupported numbers: {', '.join(unsupported_numbers)}")

    allowed_refs = _allowed_application_references(context)
    unsupported_refs = sorted(set(structured_output.get("referenced_application_references", [])) - allowed_refs)
    if unsupported_refs:
        problems.append(f"unsupported application references: {', '.join(unsupported_refs)}")

    allowed_entities = _allowed_entity_names(context)
    unsupported_entities = sorted(set(structured_output.get("referenced_entity_names", [])) - allowed_entities)
    if unsupported_entities:
        problems.append(f"unsupported entity names: {', '.join(unsupported_entities)}")

    allowed_roles = _allowed_roles(context)
    unsupported_roles = sorted(set(structured_output.get("referenced_roles", [])) - allowed_roles)
    if unsupported_roles:
        problems.append(f"unsupported roles: {', '.join(unsupported_roles)}")

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


def _persisted_summary_result(allocation: LocalPlanSite, *, regenerated: bool, rejected: bool, rejection_reason: list[str] | None) -> AllocationSummaryResult:
    return AllocationSummaryResult(
        regenerated=regenerated, rejected=rejected, rejection_reason=rejection_reason,
        headline=allocation.ai_summary_headline, overview=allocation.ai_summary_overview,
        key_points=json.loads(allocation.ai_summary_key_points) if allocation.ai_summary_key_points else [],
        key_uncertainties=json.loads(allocation.ai_summary_key_uncertainties) if allocation.ai_summary_key_uncertainties else [],
        investigation_priorities=json.loads(allocation.ai_summary_investigation_priorities) if allocation.ai_summary_investigation_priorities else [],
        generated_at=allocation.ai_summary_generated_at, model=allocation.ai_summary_model,
        prompt_version=allocation.ai_summary_prompt_version, status=allocation.ai_summary_status,
        generation_error=allocation.ai_summary_generation_error,
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
    ai_summary_status/ai_summary_generation_error record that the most
    recent attempt failed."""
    context = build_allocation_context(session, allocation)
    fingerprint = compute_context_fingerprint(context)

    if not should_regenerate_allocation_summary(allocation, fingerprint, force=force):
        return _persisted_summary_result(allocation, regenerated=False, rejected=False, rejection_reason=None)

    prompt = build_summary_prompt(context)
    try:
        response = client.responses.create(
            model=MODEL, input=prompt,
            text={"format": {"type": "json_schema", "name": SUMMARY_SCHEMA["name"], "schema": SUMMARY_SCHEMA["schema"], "strict": True}},
        )
        structured = json.loads(response.output_text)
    except Exception as e:
        allocation.ai_summary_status = "error"
        allocation.ai_summary_generation_error = str(e)[:2000]
        session.commit()
        return _persisted_summary_result(allocation, regenerated=False, rejected=False, rejection_reason=None)

    is_valid, problems = validate_summary_output(context, structured)
    if not is_valid:
        allocation.ai_summary_status = "error"
        allocation.ai_summary_generation_error = "; ".join(problems)[:2000]
        session.commit()
        return _persisted_summary_result(allocation, regenerated=False, rejected=True, rejection_reason=problems)

    now = dt.datetime.now(dt.timezone.utc)
    allocation.ai_summary_headline = structured["headline"]
    allocation.ai_summary_overview = structured["overview"]
    allocation.ai_summary_key_points = json.dumps(structured["key_points"])
    allocation.ai_summary_key_uncertainties = json.dumps(structured["key_uncertainties"])
    allocation.ai_summary_investigation_priorities = json.dumps(structured["investigation_priorities"])
    allocation.ai_summary_generated_at = now
    allocation.ai_summary_context_fingerprint = fingerprint
    allocation.ai_summary_model = MODEL
    allocation.ai_summary_prompt_version = PROMPT_VERSION
    allocation.ai_summary_status = "ok"
    allocation.ai_summary_generation_error = None
    session.commit()

    return AllocationSummaryResult(
        regenerated=True, rejected=False, rejection_reason=None,
        headline=structured["headline"], overview=structured["overview"],
        key_points=structured["key_points"], key_uncertainties=structured["key_uncertainties"],
        investigation_priorities=structured["investigation_priorities"],
        generated_at=now, model=MODEL, prompt_version=PROMPT_VERSION,
        status="ok", generation_error=None,
    )
