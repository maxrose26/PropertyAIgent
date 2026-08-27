"""Stage 4B.2 ("Ownership & Control Intelligence - Customer-Facing UI") - the
read-only reporting/query layer over ControlRelationship (Stage 4B), reused
by every Application/Site/Allocation UI surface rather than each page
independently querying and wording this evidence (CLAUDE.md: "keep business
logic out of the UI"). A pure module - no Streamlit import, mirroring
app.reporting.site_profile/allocation_discovery's own discipline.

CRITICAL SEMANTIC RULE (Stage 4B.2 Section 2, restated) - a ControlRelationship
row is evidence that a party had a stated/apparent relationship to an
Application/Site in cited evidence. It is NEVER proof of current registered
ownership, Land Registry proprietorship, whole-allocation control, or sole/
freehold/beneficial ownership. Every customer-facing label this module
produces is deliberately hedged (see _ROLE_LABEL_BY_EVIDENCE_CATEGORY/
_SOURCE_LABEL_BY_EVIDENCE_BASIS below - "Planning ownership declaration",
never "Current Owner") and SOURCE_NOTE's exact wording must always accompany
anything built from this module's output.

SCOPING (Sections 4/5/6 - the entire point of this module):
  - get_application_control_intelligence returns ONLY one Application's own
    rows.
  - get_site_control_intelligence returns ONLY rows scoped to one Site (via
    ControlRelationship.site_id, which Stage 4B's writers set from
    Application.site_id at write time - never propagated between Sites).
  - get_allocation_control_intelligence takes the SAME per-Site
    SiteActivitySummary list app.reporting.allocation_development_coverage
    already builds for an allocation (Stage 3A) and queries EACH related
    Site independently, one section per Site, NEVER merged into one
    allocation-wide owner. A "Residual allocation capacity" section is added
    only when the allocation's own DevelopmentCoverageResult already
    evidences uncovered capacity (indicative_residual_capacity > 0) - it is
    never given any relationship, only the empty-state wording - which is
    the exact mechanism that stops a developer confirmed for one phase of a
    multi-phase allocation (e.g. Taylor Wimpey's 244-unit Southern Parcel of
    the 1,100-unit North of Mosley Common allocation, JPA 32) from ever
    being read as controlling the allocation's residual capacity. Nothing
    in this module is specific to that or any other named allocation - the
    same generic Site-scoped query produces the correct result for any
    multi-Site allocation.

REJECTED EVIDENCE (Section 10): every query below excludes
review_status == "rejected" - rejected evidence never appears in these
customer-facing summaries. needs_confirmation evidence IS included but is
individually flagged (ControlRelationshipView.needs_review /
ControlRelationshipGroup.needs_review) so the UI can mark it "Evidence
requires review" rather than presenting it as accepted fact.

DISPLAY-LAYER GROUPING (Section 5/16) - get_site_control_intelligence groups
rows by (entity name, role, customer-facing role label) purely for display,
never touching the database - see ControlRelationshipGroup. Two rows are
only ever grouped together when they would show an IDENTICAL customer-facing
label (grouping by role label, not just role, means a Certificate A
declaration and an S106-defined role for the same nominal role are never
silently merged under one label - the "Certificate A vs S106" distinction
Section 8 requires stays visible even under grouping). Underlying rows
remain fully available on the group's own `items` list, never discarded.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import ControlRelationship

# Bounded evidence snippet (Section 4/12/17 item 17) - a customer-facing
# excerpt, never the full extracted document text, regardless of how long
# the underlying evidence_snippet already stored on the row is.
EVIDENCE_SNIPPET_MAX_CHARS = 320

# Customer-facing role wording (Section 2/11, exact examples given) - keyed
# on evidence_category, the POINT-IN-TIME-HONEST field (see
# ControlRelationship's own class docstring, "CURRENT VS HISTORICAL") -
# never on the bare `role` column alone, so a Certificate A self-declaration
# and an S106 legal-deed statement of the same nominal role never collapse
# onto the same wording.
_ROLE_LABEL_BY_EVIDENCE_CATEGORY: dict[str, str] = {
    "CERTIFICATE_A_APPLICANT_OWNER_DECLARATION": "Planning ownership declaration",
    "S106_DEFINED_OWNER": "S106 Owner",
    "S106_DEFINED_DEVELOPER": "S106 Developer",
    "S106_DEFINED_MORTGAGEE": "S106 Mortgagee",
}

# Fallback wording by the bare `role` column, only ever reached for a role/
# evidence_category combination this task's own deterministic writers never
# produce (e.g. a future extractor's OTHER/UNKNOWN row) - still hedged,
# never a bare technical enum value shown to a customer.
_ROLE_LABEL_BY_ROLE_FALLBACK: dict[str, str] = {
    "OWNER": "Ownership evidence",
    "APPLICANT": "Applicant evidence",
    "DEVELOPER": "Developer evidence",
    "PROMOTER": "Promoter evidence",
    "AGENT": "Agent evidence",
    "OPTION_HOLDER": "Option holder evidence",
    "JV_PARTY": "Joint venture party evidence",
    "S106_PARTY": "S106 party evidence",
    "MORTGAGEE": "Mortgagee evidence",
    "ARCHITECT": "Architect evidence",
    "REGISTERED_PROVIDER": "Registered provider evidence",
    "OTHER": "Ownership/control evidence",
    "UNKNOWN": "Ownership/control evidence",
}

# Customer-facing evidence-source wording (Section 4/11, exact examples
# given), keyed on evidence_basis - the coarse mechanism field.
_SOURCE_LABEL_BY_EVIDENCE_BASIS: dict[str, str] = {
    "certificate_a_declaration": "Planning Application Form — Certificate A",
    "s106_defined_role": "S106 Agreement",
    "s106_title_number": "S106 Agreement",
}
_DEFAULT_SOURCE_LABEL = "Planning document"

# Section 8 - exact required wording, reproduced verbatim. Never repeated
# per-entity (visually subordinate, shown once beneath a section).
SOURCE_NOTE = (
    "Source note: Ownership and control information is extracted from planning documents held by "
    "PropertyAIgent, including planning application ownership certificates and Section 106 agreements. "
    "It may not reflect current registered ownership."
)

# Section 9 - exact required empty-state wording, reproduced verbatim.
EMPTY_STATE_APPLICATION = (
    "No ownership/control evidence has yet been identified from the planning documents held by PropertyAIgent."
)
EMPTY_STATE_SITE = (
    "No ownership/control evidence has yet been identified for this Site from linked planning Applications."
)
EMPTY_STATE_ALLOCATION_RESIDUAL = "No ownership/control evidence currently identified."

# Stage 4B.3 ("Local Plan Ownership & Control Hierarchy UI Refinement"),
# Section 11 - a Site-card-specific empty state within the ALLOCATION
# detail page's Ownership & Control hierarchy. Deliberately a separate
# constant from EMPTY_STATE_SITE (Stage 4B.2's Site Profile "Ownership &
# Control" tab wording, "...has yet been identified...") - the two
# surfaces are allowed to phrase the same absence-of-evidence fact
# slightly differently without one silently drifting to match the other.
EMPTY_STATE_ALLOCATION_SITE = (
    "No ownership/control evidence currently identified for this Site from linked planning Applications."
)

# Stage 4B.3, Section 7 - a light, restrained cue, never a commercial
# opportunity claim. Shown only alongside the residual allocation section,
# never implying the land is available, uncontrolled, or that ownership is
# "unknown" - only that further ownership investigation is warranted.
OWNERSHIP_INTELLIGENCE_GAP_CUE = "Ownership intelligence gap — investigate"


def _role_label(row: ControlRelationship) -> str:
    return _ROLE_LABEL_BY_EVIDENCE_CATEGORY.get(row.evidence_category) or _ROLE_LABEL_BY_ROLE_FALLBACK.get(
        row.role, "Ownership/control evidence",
    )


def _source_label(row: ControlRelationship) -> str:
    return _SOURCE_LABEL_BY_EVIDENCE_BASIS.get(row.evidence_basis, _DEFAULT_SOURCE_LABEL)


def _bounded_snippet(text: str | None) -> str | None:
    if not text:
        return None
    text = text.strip()
    if not text:
        return None
    if len(text) <= EVIDENCE_SNIPPET_MAX_CHARS:
        return text
    return text[:EVIDENCE_SNIPPET_MAX_CHARS].rstrip() + "…"


@dataclass(frozen=True)
class ControlRelationshipView:
    """One ControlRelationship row, reshaped for customer-facing display -
    every raw technical field (entity_name_raw, evidence_category,
    relationship_type-equivalent, database ids) stays available for
    internal use, but role_label/evidence_source_label are the ONLY wording
    a customer-facing surface should ever render for what this row means
    (Section 11)."""

    id: int
    entity_name_raw: str
    role: str
    role_label: str
    evidence_source_label: str
    confidence: str | None
    title_number: str | None
    evidence_date: dt.datetime | None
    review_status: str
    needs_review: bool
    company_id: int | None
    application_id: int | None
    application_reference: str | None
    evidence_snippet: str | None
    document_id: int | None
    document_source_url: str | None
    document_name: str | None


@dataclass(frozen=True)
class ControlRelationshipGroup:
    """Display-layer-only grouping of one or more ControlRelationshipViews
    that would show an identical entity/role/role_label (Section 5/16) -
    NEVER a database merge. `items` always holds every underlying row so a
    user can still inspect the individual evidence records."""

    entity_name_raw: str
    role: str
    role_label: str
    company_id: int | None
    needs_review: bool
    supporting_evidence_count: int
    application_references: list[str] = field(default_factory=list)
    items: list[ControlRelationshipView] = field(default_factory=list)


@dataclass(frozen=True)
class RelatedApplicationSummary:
    """Stage 4B.3 - one Application already known to relate to a Site
    within an allocation's Ownership & Control hierarchy (Section 4).
    Reshapes fields Stage 3A's own SiteActivitySummary/Application already
    carry - never a new query, never a new capacity calculation."""

    reference: str
    status: str | None
    decision: str | None
    is_representative: bool


@dataclass(frozen=True)
class SiteControlSection:
    """One Site's (or the allocation's residual land's) ownership/control
    summary within an allocation's Ownership & Control view (Section 6/7) -
    `groups` is always empty for a residual section; a residual section
    never carries any relationship evidence, by construction.

    Stage 4B.3 ("Hierarchy UI Refinement") additive fields - applications/
    representative_application_reference/capacity_known/capacity are
    reshaped directly from the SAME SiteActivitySummary the caller already
    passed in (Stage 3A's own already-computed, safe per-Site figures -
    see summarise_site_activity's own docstring for why capacity is never
    a blind sum across every Application). residual_capacity and
    show_ownership_intelligence_gap_cue are populated ONLY on the residual
    section; both are None/False for every Site section."""

    label: str
    site_id: int | None
    is_residual: bool
    groups: list[ControlRelationshipGroup] = field(default_factory=list)
    applications: list[RelatedApplicationSummary] = field(default_factory=list)
    representative_application_reference: str | None = None
    capacity_known: bool = False
    capacity: int | None = None
    residual_capacity: int | None = None
    show_ownership_intelligence_gap_cue: bool = False


def _to_view(row: ControlRelationship) -> ControlRelationshipView:
    app = row.application
    doc = row.evidence_document
    return ControlRelationshipView(
        id=row.id,
        entity_name_raw=row.entity_name_raw,
        role=row.role,
        role_label=_role_label(row),
        evidence_source_label=_source_label(row),
        confidence=row.confidence,
        title_number=row.title_number,
        evidence_date=row.evidence_date,
        review_status=row.review_status,
        needs_review=row.review_status == "needs_confirmation",
        company_id=row.company_id,
        application_id=row.application_id,
        application_reference=app.reference if app else None,
        evidence_snippet=_bounded_snippet(row.evidence_snippet),
        document_id=row.evidence_document_id,
        document_source_url=doc.source_url if doc else None,
        document_name=doc.document_name if doc else None,
    )


def _fetch_views(session: Session, *, application_id: int | None = None, site_id: int | None = None) -> list[ControlRelationshipView]:
    """Shared query - excludes rejected evidence (Section 10), batches the
    Application/Document lookups every row needs for its customer-facing
    reference/source-link fields (never one query per row)."""
    stmt = select(ControlRelationship).where(ControlRelationship.review_status != "rejected")
    if application_id is not None:
        stmt = stmt.where(ControlRelationship.application_id == application_id)
    if site_id is not None:
        stmt = stmt.where(ControlRelationship.site_id == site_id)
    stmt = stmt.options(
        selectinload(ControlRelationship.application), selectinload(ControlRelationship.evidence_document),
    ).order_by(ControlRelationship.role, ControlRelationship.id)
    rows = session.execute(stmt).scalars().all()
    return [_to_view(r) for r in rows]


def get_application_control_intelligence(session: Session, application_id: int) -> list[ControlRelationshipView]:
    """Section 4 - ONLY the given Application's own ControlRelationship
    rows, ungrouped (an Application-level view has no cross-document
    duplication concern the way a multi-application Site does)."""
    return _fetch_views(session, application_id=application_id)


def _group_key(view: ControlRelationshipView) -> tuple[str, str, str]:
    return (view.entity_name_raw.strip().casefold(), view.role, view.role_label)


def _group_views(views: list[ControlRelationshipView]) -> list[ControlRelationshipGroup]:
    groups: dict[tuple[str, str, str], list[ControlRelationshipView]] = {}
    order: list[tuple[str, str, str]] = []
    for view in views:
        key = _group_key(view)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(view)

    result: list[ControlRelationshipGroup] = []
    for key in order:
        items = groups[key]
        first = items[0]
        refs: list[str] = []
        for item in items:
            if item.application_reference and item.application_reference not in refs:
                refs.append(item.application_reference)
        result.append(ControlRelationshipGroup(
            entity_name_raw=first.entity_name_raw, role=first.role, role_label=first.role_label,
            company_id=first.company_id, needs_review=any(item.needs_review for item in items),
            supporting_evidence_count=len(items), application_references=refs, items=items,
        ))
    return result


def get_site_control_intelligence(session: Session, site_id: int) -> list[ControlRelationshipGroup]:
    """Section 5 - ONLY ControlRelationship rows scoped to this Site (via
    the denormalised site_id column, set once from Application.site_id at
    write time - see the model's own class docstring), grouped for display
    per Section 5/16. Never aggregates from any other Site."""
    return _group_views(_fetch_views(session, site_id=site_id))


def get_site_control_detail(
    session: Session, site_id: int,
) -> tuple[list[ControlRelationshipGroup], dict[int, list[ControlRelationshipView]]]:
    """Section 15 - "UI pages should not each independently reproduce
    complicated ControlRelationship query logic": one query for the Site,
    returning BOTH the grouped Site-level aggregate (Section 5) and a
    per-Application breakdown (Section 4, keyed by application_id) from the
    same fetch - so a page needing both (the Site Profile Ownership &
    Control tab) never issues one query per linked Application."""
    views = _fetch_views(session, site_id=site_id)
    by_application: dict[int, list[ControlRelationshipView]] = {}
    for view in views:
        if view.application_id is not None:
            by_application.setdefault(view.application_id, []).append(view)
    return _group_views(views), by_application


def _application_summaries(summary) -> list[RelatedApplicationSummary]:
    rep = summary.representative_application
    return [
        RelatedApplicationSummary(
            reference=app.reference, status=app.status, decision=app.decision,
            is_representative=bool(rep and app.id == rep.id),
        )
        for app in summary.applications
    ]


def get_allocations_control_intelligence(session: Session, site_ids: list[int]) -> dict[int, list[ControlRelationshipGroup]]:
    """Site Selection & Reporting V1 Gate 2 - batched sibling of
    get_site_control_intelligence: ONE query across every given site_id
    (WHERE site_id IN (...)), never one per Site, so a shortlist spanning
    many allocations' many related Sites can be evidenced without an N+1
    query pattern. Does not replace or modify get_site_control_intelligence
    or get_allocation_control_intelligence below (both still used,
    unchanged, by the Allocation Detail page) - purely an additive,
    batch-scale entrypoint for report-context building. Sites with no
    evidence rows simply have no key in the returned dict - callers should
    use `.get(site_id, [])`."""
    if not site_ids:
        return {}
    stmt = select(ControlRelationship).where(
        ControlRelationship.review_status != "rejected",
        ControlRelationship.site_id.in_(site_ids),
    ).options(
        selectinload(ControlRelationship.application), selectinload(ControlRelationship.evidence_document),
    ).order_by(ControlRelationship.site_id, ControlRelationship.role, ControlRelationship.id)
    rows = session.execute(stmt).scalars().all()
    views_by_site: dict[int, list[ControlRelationshipView]] = {}
    for row in rows:
        views_by_site.setdefault(row.site_id, []).append(_to_view(row))
    return {site_id: _group_views(views) for site_id, views in views_by_site.items()}


def get_allocation_control_intelligence(
    session: Session, site_summaries: list, *, indicative_residual_capacity: int | None,
) -> list[SiteControlSection]:
    """Section 6/7 - one SiteControlSection per related Site (each queried
    independently via get_site_control_intelligence, so evidence never
    crosses Sites), plus a trailing "Residual allocation capacity" section
    ONLY when the allocation's own Stage 3A DevelopmentCoverageResult has
    already evidenced uncovered capacity - that section never carries any
    relationship evidence (there is no Site to query for it), so it always
    renders the empty-state wording, by construction rather than by any
    per-allocation special case. `site_summaries` is the same
    app.reporting.allocation_development_coverage.SiteActivitySummary list
    Stage 3A's own coverage computation already builds for this allocation -
    passed in, not recomputed, so this module never has to know how
    AllocationSiteRelationship rows are resolved to Sites.

    Stage 4B.3 - each Site section is additionally populated with that
    Site's own already-computed planning-activity context (applications,
    representative Application, capacity) purely reshaped from
    SiteActivitySummary - no new query, no new capacity arithmetic (see
    RelatedApplicationSummary/_application_summaries above). The residual
    section carries the SAME indicative_residual_capacity figure the
    caller already passed in, plus show_ownership_intelligence_gap_cue=True
    - trivially always true whenever a residual section exists at all,
    since a residual section never has any Site to carry evidence for, by
    construction; this is a restrained investigation cue, never a
    commercial-opportunity claim (Section 7)."""
    sections = [
        SiteControlSection(
            label=summary.site.display_address, site_id=summary.site_id, is_residual=False,
            groups=get_site_control_intelligence(session, summary.site_id),
            applications=_application_summaries(summary),
            representative_application_reference=(
                summary.representative_application.reference if summary.representative_application else None
            ),
            capacity_known=summary.capacity_known, capacity=summary.capacity,
        )
        for summary in site_summaries
    ]
    if indicative_residual_capacity:
        sections.append(SiteControlSection(
            label="Residual allocation capacity", site_id=None, is_residual=True, groups=[],
            residual_capacity=indicative_residual_capacity, show_ownership_intelligence_gap_cue=True,
        ))
    return sections
