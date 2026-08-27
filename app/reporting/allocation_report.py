"""Site Selection & Reporting V1 Gate 2 - the deterministic allocation
report-context builder: SHORTLIST IDS -> AllocationReportContext -> shortlist
review / CSV / (future PDF / future one-time cross-site AI synthesis).

ONE context builder, ONE query path, reused by every consumer (Gate 2's
shortlist review page and CSV export today; Gate 3/4's PDF and cross-site AI
summary later) - never a separate query-building path per output, mirroring
the same principle app.reporting.pdf_report's AggregateStats already proves
out for Planning Discovery (one object powering both its stats table and its
narrative prompt).

Deliberately a NEW, focused module rather than an extension of
app.reporting.pdf_report: the Allocation and Planning Site report domains
have materially different content contracts (allocation identity/capacity/
coverage/party evidence vs. scheme/decision/lapse-risk), and forcing one
module to own both would make pdf_report.py a monolithic report engine for
two genuinely different domains. Generic ReportLab styling helpers (when
Gate 3 adds PDF rendering here) remain candidates to import FROM
pdf_report.py where truly generic - nothing here duplicates that module's
existing PDF/stats logic today, since this gate ships no PDF.

ARCHITECTURE DECISION (relation to build_allocation_discovery): this module
deliberately does NOT call build_allocation_discovery and filter by id.
build_allocation_discovery has no allocation_ids parameter - it always
computes over the ENTIRE platform's allocations (287+ and growing), which
would make every report build's cost scale with platform size rather than
shortlist size, and its output is a UI-card shape carrying many fields
(why_it_matters, visual evidence, badge kinds) this report domain doesn't
need and would have to strip back out. Instead, this module composes the
same LOWER-LEVEL batched building blocks build_allocation_discovery itself
is built from - app.reporting.allocation_development_coverage.
build_allocation_development_coverage (already accepts a list of
allocations and returns coverage/site_summaries for all of them in one
fixed, small query budget) plus two NEW batched siblings added by this gate
(get_allocation_summaries, get_allocations_control_intelligence) - each
scoped to exactly the requested allocation_ids, so a report's query cost
depends on shortlist size, never platform size. See
specifications/014-allocation-reporting-v1-gate-2.md for the full
reasoning.

NEVER stores ORM objects or stale session-state snapshots in the final
AllocationReportContext - every field is a plain value (str/int/float/bool/
list/dataclass-of-plain-values), and the whole context is built fresh,
against current trusted data, on every call.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import load_councils
from app.db.models import LocalPlanSite
from app.reporting.allocation_development_coverage import build_allocation_development_coverage
from app.reporting.allocation_discovery import (
    ALLOCATION_REVIEW_STATUS_META,
    INTENDED_USE_LABELS,
    PLAN_STATUS_META,
    format_capacity,
)
from app.reporting.allocation_intelligence_summary import _clean_portal_value, get_allocation_summaries
from app.reporting.ownership_control import get_allocations_control_intelligence

# --- Report-entry value objects (Section 6/7) --------------------------------


@dataclass(frozen=True)
class LinkedApplicationEntry:
    """One Application already known to relate to a shortlisted allocation's
    Site - deterministic supporting evidence (Section 7), never part of an
    AI narrative. Every field is reshaped from already-batched data (the
    same Application rows app.reporting.allocation_development_coverage's
    own site_summaries already carry) - no new per-Application query."""

    reference: str
    proposal: str | None
    status: str | None
    decision: str | None
    decision_date: str | None
    unit_count: int | None
    unit_count_is_estimate: bool
    application_category: str | None
    applicant: str | None
    site_label: str
    site_relationship_review_status: str
    portal_url: str | None
    is_representative: bool


@dataclass(frozen=True)
class ApplicantEvidenceEntry:
    """One entity named as applicant on one or more of a Site's TRUSTED
    linked Applications - Multi-Application Party Intelligence (Section 11):
    aggregated across every trusted linked Application on the Site, never
    only the representative one. Role is always "Applicant" - being named
    on many Applications is still only Applicant evidence, never promoted
    to Developer/Owner/Promoter (Section 10). Exact cleaned-name dedup only
    (Section 11) - no fuzzy company-name resolution."""

    site_label: str
    entity_name: str
    application_references: list[str] = field(default_factory=list)

    @property
    def application_count(self) -> int:
        return len(self.application_references)


@dataclass(frozen=True)
class OwnershipEvidenceEntry:
    """Reshape of one app.reporting.ownership_control.ControlRelationshipGroup
    scoped to one related Site, for report/CSV consumption - entity_name_raw/
    role/role_label/needs_review/application_references map 1:1 to the
    group's own fields (Section 10: exact role labels preserved, never
    upgraded - a Certificate A declaration stays "Planning ownership
    declaration", an S106 Developer stays labelled Developer only because
    it is independently evidenced). site_label names which related Site
    this evidence belongs to - never merged across Sites, the same
    discipline app.reporting.ownership_control.SiteControlSection already
    enforces."""

    site_label: str
    entity_name_raw: str
    role: str
    role_label: str
    needs_review: bool
    application_references: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AllocationIntelligenceSnapshot:
    """Read-only reshape of the existing persisted AllocationIntelligenceSummary
    row - NEVER a generation call (Section 13). available=False for a
    missing OR error-only summary, in both cases without exposing the raw
    generation_error to this customer-facing context."""

    available: bool
    headline: str | None = None
    overview: str | None = None
    key_points: list[str] = field(default_factory=list)
    key_uncertainties: list[str] = field(default_factory=list)
    investigation_priorities: list[str] = field(default_factory=list)
    generated_at: dt.datetime | None = None


@dataclass(frozen=True)
class AllocationReportEntry:
    """One shortlisted allocation's full deterministic report entry - the
    one shape shortlist review, CSV, and (Gate 3/4) PDF/AI-prompt all read
    from. No ORM objects, no session-state snapshots - built fresh from
    current trusted data at report-build time."""

    # IDENTITY
    allocation_id: int
    allocation_name: str
    allocation_reference: str | None
    council_code: str
    council_name: str
    local_plan_name: str | None
    plan_status: str | None
    plan_status_label: str
    plan_status_bucket: str | None
    intended_use: str | None
    intended_use_label: str

    # DEVELOPMENT POSITION
    capacity_value: int | None
    capacity_kind: str
    capacity_display: str
    identified_application_capacity: int | None
    indicative_residual_capacity: int | None
    development_coverage_percentage: float | None
    development_coverage_classification: str
    capacity_accounting_status: str  # ok | no_activity | capacity_unknown | review_required

    # PLANNING ACTIVITY (Section 8 - no-linked-Application is a valid state,
    # never an error: linked_application_count == 0 and linked_applications
    # == [] together are simply what "no identified activity" looks like)
    linked_application_count: int
    linked_applications: list[LinkedApplicationEntry] = field(default_factory=list)

    # PARTY EVIDENCE (Section 10/11 - kept as two separate lists so a
    # consumer can never conflate portal-scrape Applicant evidence with
    # evidence-backed Owner/Developer/Promoter/etc. ControlRelationship
    # evidence; see the two dataclasses' own docstrings)
    applicant_evidence: list[ApplicantEvidenceEntry] = field(default_factory=list)
    ownership_evidence: list[OwnershipEvidenceEntry] = field(default_factory=list)

    # TRUST / REVIEW STATE
    review_status: str | None = None
    review_status_label: str | None = None
    disputed_site_count: int = 0  # AllocationSiteRelationship rows needs_confirmation - never named, only counted

    # AI ALLOCATION INTELLIGENCE
    ai_intelligence: AllocationIntelligenceSnapshot = field(default_factory=lambda: AllocationIntelligenceSnapshot(available=False))

    # SOURCE / EVIDENCE
    source_document_url: str | None = None
    last_checked: dt.datetime | None = None

    # Pre-merge semantic hardening (Gate 2 amendment) - structural trust
    # partitioning of ownership_evidence, so a consumer (this gate's own
    # Shortlist page and CSV, and future Gate 3/4 PDF/AI code) never has to
    # remember to check needs_review itself before treating an entry as
    # settled fact. trusted_ownership_evidence is safe to present as plain
    # evidence with its existing role label; review_pending_ownership_
    # evidence must always be shown with an explicit uncertainty marker (or
    # omitted from a "Known X" style signal entirely) - never silently
    # merged into the same display as trusted evidence (Section 6/9).
    @property
    def trusted_ownership_evidence(self) -> list[OwnershipEvidenceEntry]:
        return [e for e in self.ownership_evidence if not e.needs_review]

    @property
    def review_pending_ownership_evidence(self) -> list[OwnershipEvidenceEntry]:
        return [e for e in self.ownership_evidence if e.needs_review]


@dataclass(frozen=True)
class ExcludedCandidate:
    """A shortlisted id that could not be included in the report (Section
    21A/G) - the allocation no longer exists, or the id was invalid. Never
    silently dropped without a reason."""

    allocation_id: int
    reason: str


@dataclass(frozen=True)
class AllocationReportAggregates:
    """Low-risk deterministic shortlist-wide totals (Section 19). Every
    *_total is a sum over entries with a KNOWN value only - a paired
    *_unknown_count/_count field names how many entries were excluded from
    that sum, rather than pretending a total is complete when it isn't
    (Section 19/20's explicit "expose known_total + unknown_count rather
    than manufacturing a precise total from uncertain values").

    Pre-merge semantic hardening (Gate 2 amendment) - allocation CAPACITY is
    deliberately NOT one blended "known total": format_capacity's own
    capacity_kind ("minimum" | "maximum" | "indicative" | "range" |
    "unknown") distinguishes a genuinely single stated figure from a range
    that only has an upper BOUND, never an exact value. Blending the two
    into one total (as an earlier version of this dataclass did) let a
    range's upper bound silently masquerade as an exact figure the moment
    it was summed - exactly the risk a future PDF/AI consumer must be
    structurally unable to reproduce. exact_capacity_total therefore sums
    ONLY entries whose capacity_kind is "minimum"/"maximum"/"indicative" (a
    single genuinely-stated figure, whichever field it came from);
    ranged_capacity_count/unknown_capacity_count are separate counts, never
    folded into that total - see each individual entry's own capacity_kind/
    capacity_value/capacity_display (never fabricated here) for the actual
    range bounds. There is deliberately no field that could be read as "the
    total capacity including ranges" - if a future consumer wants that, it
    must compute and explicitly label it as an upper-bound total itself,
    never inherit that framing silently from this dataclass.

    identified_application_capacity and indicative_residual_capacity carry
    NO equivalent range concept - app.reporting.allocation_development_
    coverage.compute_development_coverage only ever returns a single
    genuine integer for these (summed from real per-Site Application unit
    counts, or arithmetic on the allocation's own single capacity_value) or
    None when accounting is review_required/capacity_unknown (see that
    function's own docstring/tests) - never a range. Their existing known_
    total/unknown_count pairs are therefore already safe as originally
    designed: None (including every REVIEW_REQUIRED case) is correctly
    excluded from the sum and counted separately, never fabricated as
    zero or as a confident number - see tests/test_allocation_report.py's
    dedicated aggregate-level proof of this."""

    allocation_count: int
    exact_capacity_total: int
    exact_capacity_count: int
    ranged_capacity_count: int
    unknown_capacity_count: int
    identified_application_capacity_known_total: int
    identified_application_capacity_unknown_count: int
    indicative_residual_capacity_known_total: int
    indicative_residual_capacity_unknown_count: int
    adopted_count: int
    emerging_count: int
    other_plan_status_count: int
    allocations_with_linked_activity: int
    allocations_with_no_identified_activity: int


@dataclass(frozen=True)
class AllocationReportContext:
    entries: list[AllocationReportEntry]
    excluded: list[ExcludedCandidate]
    aggregates: AllocationReportAggregates
    generated_at: dt.datetime


# --- Context builder (Sections 4/5/9/13/14/15) -------------------------------


def _plan_status_meta(plan_status: str | None) -> dict:
    return PLAN_STATUS_META.get(plan_status, PLAN_STATUS_META[None])


def _review_status_meta(review_status: str | None) -> dict:
    return ALLOCATION_REVIEW_STATUS_META.get(review_status, ALLOCATION_REVIEW_STATUS_META[None])


def _applicant_evidence_for_site(site_label: str, applications: list) -> list[ApplicantEvidenceEntry]:
    """Multi-Application Party Intelligence (Section 11) - aggregated across
    EVERY trusted linked Application on this Site (never only the
    representative one), exact cleaned-name dedup only. Mirrors
    app.reporting.allocation_intelligence_summary's own established
    applicant-aggregation logic byte-for-byte (reusing its shared
    _clean_portal_value placeholder-cleaner directly) so this report can
    never disagree with the AI Allocation Intelligence layer about what
    counts as real applicant evidence."""
    refs_by_name: dict[str, list[str]] = {}
    for application in applications:
        name = _clean_portal_value(application.applicant_name_raw)
        if name is None:
            continue
        refs_by_name.setdefault(name, []).append(application.reference)
    return [
        ApplicantEvidenceEntry(site_label=site_label, entity_name=name, application_references=sorted(set(refs)))
        for name, refs in sorted(refs_by_name.items())
    ]


def _linked_applications_for_site(site_summary) -> list[LinkedApplicationEntry]:
    rep = site_summary.representative_application
    entries = []
    for application in site_summary.applications:
        unit_count = None
        unit_count_is_estimate = False
        scheme_intelligence = getattr(application, "scheme_intelligence", None)
        if scheme_intelligence is not None and scheme_intelligence.total_units_final is not None:
            unit_count = scheme_intelligence.total_units_final
        elif application.estimated_unit_count is not None:
            unit_count = application.estimated_unit_count
            unit_count_is_estimate = True
        entries.append(LinkedApplicationEntry(
            reference=application.reference,
            proposal=application.proposal,
            status=application.status,
            decision=_clean_portal_value(application.decision),
            decision_date=application.decision_issued_date,
            unit_count=unit_count,
            unit_count_is_estimate=unit_count_is_estimate,
            application_category=application.application_category,
            applicant=_clean_portal_value(application.applicant_name_raw),
            site_label=site_summary.site.display_address,
            site_relationship_review_status=site_summary.relationship_review_status,
            portal_url=application.summary_url,
            is_representative=bool(rep and application.id == rep.id),
        ))
    return entries


def build_allocation_report_context(session: Session, allocation_ids: list[int]) -> AllocationReportContext:
    """SHORTLIST IDS -> AllocationReportContext. The one context builder
    every Gate 2+ consumer reads from (Section 3/24) - never a separate
    query-building path per output.

    Fixed, bounded query budget regardless of shortlist size (Section 22):
      1. LocalPlanSite (+ selectinload LocalPlan) for the requested ids only
         - never the whole platform (see this module's own docstring for
           why build_allocation_discovery is deliberately not reused here).
      2. build_allocation_development_coverage's own batch (3-4 queries
         total: AllocationSiteRelationship+Site, Applications, Documents) -
         reused unchanged, never reimplemented (Section 14).
      3. get_allocation_summaries - one batched AllocationIntelligenceSummary
         read (Section 13) - never one query per allocation, never a
         generation call.
      4. get_allocations_control_intelligence - one batched ControlRelationship
         read across every related Site in the whole shortlist (Section 9) -
         never one query per allocation or per Site.

    Duplicate/invalid ids never crash (Section 21G): the input is
    deduplicated up front, and any id with no matching LocalPlanSite row
    lands in `excluded` with a reason, while every other id's entry is
    still built normally (Section 21A: "one broken allocation must not
    prevent export of the others")."""
    unique_ids = sorted(set(allocation_ids))
    generated_at = dt.datetime.now(dt.timezone.utc)

    if not unique_ids:
        return AllocationReportContext(
            entries=[], excluded=[], aggregates=_empty_aggregates(), generated_at=generated_at,
        )

    allocations = list(session.execute(
        select(LocalPlanSite)
        .where(LocalPlanSite.id.in_(unique_ids))
        .options(selectinload(LocalPlanSite.local_plan))
    ).scalars())
    allocations_by_id = {a.id: a for a in allocations}

    excluded = [
        ExcludedCandidate(allocation_id=aid, reason="This allocation is no longer available.")
        for aid in unique_ids if aid not in allocations_by_id
    ]

    coverage_by_allocation = build_allocation_development_coverage(session, allocations)

    summaries_by_allocation = get_allocation_summaries(session, list(allocations_by_id.keys()))

    all_site_ids = sorted({
        summary.site_id
        for result in coverage_by_allocation.values()
        for summary in result["site_summaries"]
    })
    control_groups_by_site = get_allocations_control_intelligence(session, all_site_ids)

    council_config = load_councils()

    entries: list[AllocationReportEntry] = []
    for allocation in allocations:
        plan = allocation.local_plan
        plan_status = plan.status if plan else allocation.plan_status
        plan_meta = _plan_status_meta(plan_status)
        review_meta = _review_status_meta(allocation.review_status)
        capacity = format_capacity(allocation)

        coverage_result = coverage_by_allocation.get(allocation.id, {})
        coverage = coverage_result.get("coverage")
        site_summaries = coverage_result.get("site_summaries", [])

        linked_applications: list[LinkedApplicationEntry] = []
        applicant_evidence: list[ApplicantEvidenceEntry] = []
        ownership_evidence: list[OwnershipEvidenceEntry] = []
        disputed_site_count = 0
        for site_summary in site_summaries:
            if site_summary.relationship_review_status == "needs_confirmation":
                disputed_site_count += 1
            linked_applications.extend(_linked_applications_for_site(site_summary))
            applicant_evidence.extend(_applicant_evidence_for_site(
                site_summary.site.display_address, site_summary.applications,
            ))
            for group in control_groups_by_site.get(site_summary.site_id, []):
                ownership_evidence.append(OwnershipEvidenceEntry(
                    site_label=site_summary.site.display_address,
                    entity_name_raw=group.entity_name_raw, role=group.role, role_label=group.role_label,
                    needs_review=group.needs_review, application_references=group.application_references,
                ))

        linked_application_count = sum(len(s.applications) for s in site_summaries)

        summary_row = summaries_by_allocation.get(allocation.id)
        if summary_row is not None and summary_row.headline:
            ai_intelligence = AllocationIntelligenceSnapshot(
                available=True,
                headline=summary_row.headline,
                overview=summary_row.overview,
                key_points=_json_list(summary_row.key_points),
                key_uncertainties=_json_list(summary_row.key_uncertainties),
                investigation_priorities=_json_list(summary_row.investigation_priorities),
                generated_at=summary_row.generated_at,
            )
        else:
            # Missing OR error-only summary (Section 13/21B/21C) - identical
            # safe "not available" state either way; generation_error is
            # never exposed to this customer-facing context.
            ai_intelligence = AllocationIntelligenceSnapshot(available=False)

        entries.append(AllocationReportEntry(
            allocation_id=allocation.id,
            allocation_name=allocation.site_name,
            allocation_reference=allocation.policy_reference,
            council_code=allocation.council_code,
            council_name=council_config[allocation.council_code].name if allocation.council_code in council_config else allocation.council_code,
            local_plan_name=plan.plan_name if plan else allocation.plan_name,
            plan_status=plan_status,
            plan_status_label=plan_meta["label"],
            plan_status_bucket=plan_meta["bucket"],
            intended_use=allocation.intended_use,
            intended_use_label=INTENDED_USE_LABELS.get(allocation.intended_use, allocation.intended_use or "Not stated"),
            capacity_value=capacity["value"],
            capacity_kind=capacity["kind"],
            capacity_display=capacity["display"],
            identified_application_capacity=coverage.identified_application_capacity if coverage else None,
            indicative_residual_capacity=coverage.indicative_residual_capacity if coverage else None,
            development_coverage_percentage=coverage.development_coverage_percentage if coverage else None,
            development_coverage_classification=coverage.development_coverage_classification if coverage else "NO_IDENTIFIED_ACTIVITY",
            capacity_accounting_status=coverage.capacity_accounting_status if coverage else "no_activity",
            linked_application_count=linked_application_count,
            linked_applications=linked_applications,
            applicant_evidence=applicant_evidence,
            ownership_evidence=ownership_evidence,
            review_status=allocation.review_status,
            review_status_label=review_meta["label"],
            disputed_site_count=disputed_site_count,
            ai_intelligence=ai_intelligence,
            source_document_url=allocation.source_document_url,
            last_checked=plan.last_checked if plan else None,
        ))

    # Deterministic order (id) - never dependent on dict/query iteration order.
    entries.sort(key=lambda e: e.allocation_id)
    aggregates = _build_aggregates(entries)
    return AllocationReportContext(entries=entries, excluded=excluded, aggregates=aggregates, generated_at=generated_at)


def _json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    import json

    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return value if isinstance(value, list) else []


def _empty_aggregates() -> AllocationReportAggregates:
    return AllocationReportAggregates(
        allocation_count=0, exact_capacity_total=0, exact_capacity_count=0,
        ranged_capacity_count=0, unknown_capacity_count=0,
        identified_application_capacity_known_total=0, identified_application_capacity_unknown_count=0,
        indicative_residual_capacity_known_total=0, indicative_residual_capacity_unknown_count=0,
        adopted_count=0, emerging_count=0, other_plan_status_count=0,
        allocations_with_linked_activity=0, allocations_with_no_identified_activity=0,
    )


# capacity_kind values that represent one genuinely-stated single figure
# (never a range's upper bound) - format_capacity's own vocabulary, see
# app.reporting.allocation_discovery.format_capacity. Deliberately excludes
# "range" (two differing bounds - see EXACT vs RANGE distinction above) and
# "unknown" (no figure stated at all).
_EXACT_CAPACITY_KINDS = {"minimum", "maximum", "indicative"}


def _build_aggregates(entries: list[AllocationReportEntry]) -> AllocationReportAggregates:
    def _known_total_and_unknown(values: list[int | None]) -> tuple[int, int]:
        known = [v for v in values if v is not None]
        return sum(known), len(values) - len(known)

    identified_total, identified_unknown = _known_total_and_unknown([e.identified_application_capacity for e in entries])
    residual_total, residual_unknown = _known_total_and_unknown([e.indicative_residual_capacity for e in entries])

    exact_entries = [e for e in entries if e.capacity_kind in _EXACT_CAPACITY_KINDS]
    exact_capacity_total = sum(e.capacity_value for e in exact_entries if e.capacity_value is not None)

    return AllocationReportAggregates(
        allocation_count=len(entries),
        exact_capacity_total=exact_capacity_total,
        exact_capacity_count=len(exact_entries),
        ranged_capacity_count=sum(1 for e in entries if e.capacity_kind == "range"),
        unknown_capacity_count=sum(1 for e in entries if e.capacity_kind == "unknown"),
        identified_application_capacity_known_total=identified_total,
        identified_application_capacity_unknown_count=identified_unknown,
        indicative_residual_capacity_known_total=residual_total,
        indicative_residual_capacity_unknown_count=residual_unknown,
        adopted_count=sum(1 for e in entries if e.plan_status_bucket == "adopted"),
        emerging_count=sum(1 for e in entries if e.plan_status_bucket == "emerging"),
        other_plan_status_count=sum(1 for e in entries if e.plan_status_bucket not in ("adopted", "emerging")),
        allocations_with_linked_activity=sum(1 for e in entries if e.linked_application_count > 0),
        allocations_with_no_identified_activity=sum(1 for e in entries if e.linked_application_count == 0),
    )


# --- CSV serialization (Sections 16/17/24) -----------------------------------
# Deliberately separate from the fact model above (Section 24: "keep domain
# facts separate from serialization") - to_csv_rows/to_csv_bytes are the
# ONLY functions that know about CSV formatting; future render_pdf/
# generate_cross_site_summary functions (Gate 3/4) would read the same
# AllocationReportContext without touching this section at all.

_MULTI_VALUE_DELIMITER = "; "


def _format_applicant_evidence(entries: list[ApplicantEvidenceEntry]) -> str:
    # Section 17 - role never collapsed/omitted, even though every entry
    # here is already known to be "Applicant" (ApplicantEvidenceEntry's own
    # role-only-ever-Applicant guarantee) - the label is still shown
    # explicitly so this column's format matches the ownership/control
    # column's below, rather than silently relying on the reader already
    # knowing this column means Applicant.
    return _MULTI_VALUE_DELIMITER.join(f"{e.entity_name} [Applicant]" for e in entries)


def _format_ownership_evidence(entries: list[OwnershipEvidenceEntry], *, role: str | None = None) -> str:
    """needs_review entries are always suffixed "(needs confirmation)" -
    never silently indistinguishable from trusted evidence in this general
    evidence column. "Known Developer(s)" (see to_csv_rows below) does NOT
    call this on the unfiltered list - it is deliberately restricted to
    entry.trusted_ownership_evidence first, so a column whose own name
    ("Known") implies confidence never contains review-pending evidence at
    all, qualified or not (Section 8: "exclude it from trusted columns")."""
    filtered = [e for e in entries if role is None or e.role == role]
    return _MULTI_VALUE_DELIMITER.join(
        f"{e.entity_name_raw} [{e.role_label}]" + (" (needs confirmation)" if e.needs_review else "")
        for e in filtered
    )


CSV_COLUMNS = [
    "Authority", "Local Plan", "Allocation Reference", "Allocation Name", "Plan Status", "Intended Use",
    "Allocation Capacity", "Planning Activity", "Identified Application Capacity", "Indicative Residual Capacity",
    "Development Coverage %", "Linked Application Count", "Known Applicant(s)", "Known Developer(s)",
    "Ownership / Control Evidence", "AI Intelligence Headline", "AI Summary Available",
]

# The same neutral, evidence-bounded wording used everywhere else on this
# platform for "no identified planning activity" (Section 8) - never an
# error/warning phrase, reused here rather than a CSV-specific rewording.
_NO_ACTIVITY_LABEL = "No identified activity"
_ACTIVITY_IDENTIFIED_LABEL = "Activity identified"
_REVIEW_REQUIRED_LABEL = "Review required"


def _planning_activity_label(entry: AllocationReportEntry) -> str:
    if entry.capacity_accounting_status == "review_required":
        return _REVIEW_REQUIRED_LABEL
    if entry.linked_application_count == 0:
        return _NO_ACTIVITY_LABEL
    return _ACTIVITY_IDENTIFIED_LABEL


def to_csv_rows(context: AllocationReportContext) -> list[dict]:
    """Deterministic list-of-dicts, one per shortlisted allocation entry, in
    the context's own (id-sorted) order - never the platform-wide filtered
    set, only what's in `context.entries` (Section 16: "shortlisted
    allocations only"). Makes zero OpenAI calls - purely a reshape of
    already-built AllocationReportEntry values."""
    rows = []
    for entry in context.entries:
        rows.append({
            "Authority": entry.council_name,
            "Local Plan": entry.local_plan_name or "",
            "Allocation Reference": entry.allocation_reference or "",
            "Allocation Name": entry.allocation_name,
            "Plan Status": entry.plan_status_label,
            "Intended Use": entry.intended_use_label,
            "Allocation Capacity": entry.capacity_display,
            "Planning Activity": _planning_activity_label(entry),
            "Identified Application Capacity": (
                entry.identified_application_capacity if entry.identified_application_capacity is not None else ""
            ),
            "Indicative Residual Capacity": (
                entry.indicative_residual_capacity if entry.indicative_residual_capacity is not None else ""
            ),
            "Development Coverage %": (
                f"{entry.development_coverage_percentage:.0%}" if entry.development_coverage_percentage is not None else ""
            ),
            "Linked Application Count": entry.linked_application_count,
            "Known Applicant(s)": _format_applicant_evidence(entry.applicant_evidence),
            # Deliberately trusted_ownership_evidence only (Section 8) - a
            # needs_review "Developer" claim never appears in this column,
            # however it were worded; it remains visible in the general
            # Ownership / Control Evidence column below, explicitly
            # qualified "(needs confirmation)".
            "Known Developer(s)": _format_ownership_evidence(entry.trusted_ownership_evidence, role="DEVELOPER"),
            "Ownership / Control Evidence": _format_ownership_evidence(entry.ownership_evidence),
            "AI Intelligence Headline": entry.ai_intelligence.headline or "",
            "AI Summary Available": "Yes" if entry.ai_intelligence.available else "No",
        })
    return rows


def to_csv_bytes(context: AllocationReportContext) -> bytes:
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for row in to_csv_rows(context):
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8-sig")  # BOM so Excel opens UTF-8 (e.g. "é", "—") correctly
