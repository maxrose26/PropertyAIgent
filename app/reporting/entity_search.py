"""Entity Search (Sprint 4.5b, "Entity Search + Allocation Card
Refinement") - a reusable search layer above the platform's two separate
domain models, never a combined one (see specifications/005-entity-search-
allocation-refinement.md's Product Principle, and 004-core-domain-model.md:
"Applications are not Sites", Policy/Allocation "relates to Sites the same
way Applications do... but represents intent rather than a live regulatory
process"). The UX may present unified search results; the database and
this module never merge Application and LocalPlanSite into one entity or
one query.

Two independent search functions - one over LocalPlanSite (reusing
app.reporting.allocation_discovery's already-batched view model), one over
Application (a single bounded, LIMIT'd query) - each returns SearchResult
rows tagged with their own entity_type, so a caller can never mistake one
for the other. Deterministic ranking only (exact reference > exact title >
prefix > substring > id tie-break) - no AI, no OPENAI_API_KEY dependency,
no opportunity/relevance scoring anywhere in this module.

Presentation-agnostic - no Streamlit import (CLAUDE.md: "keep business
logic out of the UI"). app/ui/pages/0_Explore.py is the only caller.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.db.models import Application, LocalPlanSite

EntityType = Literal["allocation", "planning_site"]

# A bounded default - Part 13: "allocate sensible result limits", never an
# unbounded scan into Python. Applies per entity_type, not to the combined
# "All" total, so neither type can starve the other's results.
DEFAULT_RESULT_LIMIT = 25


@dataclass(frozen=True)
class SearchResult:
    """One search hit, always tagged with which domain object it came
    from. Never carries full Site/Allocation detail (Part 13: "avoid
    loading full Site/Allocation detail during search; lazy-load detail
    only after user selection") - just enough to render a result row and
    navigate onward via destination_page/destination_params."""
    entity_type: EntityType
    entity_id: int
    title: str
    subtitle: str
    council: str | None
    reference: str | None
    status: str | None
    capacity_or_units: str | None
    matched_entity_id: int | None
    matched_entity_label: str | None
    destination_page: str
    destination_params: dict
    # Deterministic ranking only (Part 11) - never an AI/opportunity score.
    # 0=exact reference, 1=exact title, 2=prefix, 3=substring.
    match_rank: int
    tie_break_id: int


@dataclass(frozen=True)
class EntitySearchResults:
    """Grouped, never-merged results (Part 8) - a caller renders
    .allocations and .planning_sites as separate sections, never one
    flattened list that could blur which entity type a row belongs to."""
    query: str
    scope: str
    allocations: list[SearchResult]
    planning_sites: list[SearchResult]

    @property
    def is_empty(self) -> bool:
        return not self.allocations and not self.planning_sites


# --- Deterministic ranking (Part 11) -----------------------------------------


def _match_rank(query_lower: str, *, reference: str | None, title: str | None, other_texts: list[str | None]) -> int | None:
    """None means "no match at all" (excluded from results). reference and
    title are checked for exact/prefix match; other_texts (council, plan
    name, intended use, category, matched address, applicant) are only
    ever substring matches - matching a council name exactly should never
    outrank an exact allocation-name or reference match."""
    if not query_lower:
        return None
    ref = (reference or "").strip().lower()
    ttl = (title or "").strip().lower()
    if ref and ref == query_lower:
        return 0
    if ttl and ttl == query_lower:
        return 1
    if (ref and ref.startswith(query_lower)) or (ttl and ttl.startswith(query_lower)):
        return 2
    haystacks = [ref, ttl] + [(t or "").strip().lower() for t in other_texts]
    if any(h and query_lower in h for h in haystacks):
        return 3
    return None


def _sort_results(results: list[SearchResult]) -> list[SearchResult]:
    return sorted(results, key=lambda r: (r.match_rank, r.tie_break_id))


# --- Allocation search (Part 6) ----------------------------------------------


def search_allocation_entities(
    session, query: str, *, filters: dict | None = None, limit: int = DEFAULT_RESULT_LIMIT,
) -> list[SearchResult]:
    """Searches LocalPlanSite directly - never infers allocations from the
    Application dataset (Part 5: "Allocations must search LocalPlanSite /
    Allocation Discovery data directly. Do not search the 1,381-application
    dataset and then try to infer which results are allocations."). Reuses
    app.reporting.allocation_discovery.build_allocation_discovery for the
    underlying data - the same batched, bounded query set Allocation
    Discovery's own gallery already uses (see that function's own
    docstring for the exact query budget) - no parallel loader invented
    here. Fields matched: allocation name, policy reference, council,
    Local Plan, intended use, category, matched Site/address (Part 6),
    case-insensitive, no AI (Part 6: "Do not use OpenAI. Do not require
    OPENAI_API_KEY.")."""
    from app.reporting.allocation_discovery import apply_filters, build_allocation_discovery, sort_cards

    view = build_allocation_discovery(session, council_codes=(filters or {}).get("councils"))
    cards = view["cards"]
    if filters:
        cards = apply_filters(cards, filters)

    q = (query or "").strip().lower()
    results: list[SearchResult] = []

    if not q:
        # Browsing with no search text yet - every (filtered) allocation,
        # in the same deterministic default order Allocation Discovery's
        # own gallery uses, never an arbitrary/unranked dump.
        for card in sort_cards(cards, "default")[:limit]:
            results.append(_allocation_result(card, rank=0))
        return results

    for card in cards:
        rank = _match_rank(
            q, reference=card["policy_reference"], title=card["site_name"],
            other_texts=[
                card["council_name"], card["plan_name"], card["intended_use_label"],
                card["category"], card["matched_site_address"],
            ],
        )
        if rank is None:
            continue
        results.append(_allocation_result(card, rank=rank))

    return _sort_results(results)[:limit]


def _allocation_result(card: dict, *, rank: int) -> SearchResult:
    matched_label = "Linked planning Site" if card["matched"] else None
    subtitle_bits = [b for b in (card["policy_reference"], card["council_name"], card["plan_status_label"]) if b]
    return SearchResult(
        entity_type="allocation",
        entity_id=card["id"],
        title=card["site_name"],
        subtitle=" · ".join(subtitle_bits),
        council=card["council_name"],
        reference=card["policy_reference"],
        status=card["plan_status_label"],
        capacity_or_units=card["capacity"]["display"],
        matched_entity_id=card["matched_site_id"],
        matched_entity_label=matched_label,
        destination_page="pages/3_Local_Plan_Sites.py",
        destination_params={"allocation_id": str(card["id"])},
        match_rank=rank,
        tie_break_id=card["id"],
    )


# --- Planning Site (Application) search (Part 7) -----------------------------


def search_planning_site_entities(
    session, query: str, *, allowed_site_ids: set[int] | None = None, limit: int = DEFAULT_RESULT_LIMIT,
) -> list[SearchResult]:
    """Deterministic search over Application - reference, address, council,
    applicant (Part 7's field list) - never OpenAI/an LLM (Part 6's "Do not
    use OpenAI" applies equally here; Part 10: "No AI call should be
    required for... Application reference search... Site/address search").

    Bounded to ONE query (Part 13): a single ILIKE-filtered, LIMIT'd SELECT
    - never a full-table scan into Python, never one query per result. A
    blank query returns nothing (there is no "browse every Application"
    default view here - Explore's own existing table already serves that;
    this is the deterministic entity SEARCH path only).

    allowed_site_ids optionally reuses whatever the caller's own existing
    filters (Council, housing type, etc. - Part 12: "retain existing
    Explore filters") already narrowed the visible Site set to, rather
    than this function inventing a second, parallel filter pipeline."""
    q = (query or "").strip()
    if not q:
        return []
    like = f"%{q}%"

    stmt = (
        select(Application)
        .where(or_(
            Application.reference.ilike(like),
            Application.alternative_reference.ilike(like),
            Application.address.ilike(like),
            Application.applicant_name_raw.ilike(like),
            Application.council_code.ilike(like),
        ))
        # Batched eager-load (Part 13: "avoid N+1 queries") - _units_display
        # below reads app.scheme_intelligence for every result; without
        # this it would be one extra lazy-load SELECT per Application row.
        .options(selectinload(Application.scheme_intelligence))
    )
    # Over-fetch a small, still-bounded multiple of `limit` before ranking/
    # deduping/site-filtering in Python, so a query that matches many low-
    # relevance rows (e.g. a common council code) doesn't silently starve
    # out a handful of exact-reference matches sorted later in id order.
    stmt = stmt.limit(limit * 4)
    apps = list(session.execute(stmt).scalars())

    if allowed_site_ids is not None:
        apps = [a for a in apps if a.site_id in allowed_site_ids]

    if not apps:
        return []

    # One batched reverse-lookup (Part 8's cross-link indicator) - never
    # one query per Application result.
    site_ids = sorted({a.site_id for a in apps if a.site_id is not None})
    allocation_by_site_id = _load_allocation_links(session, site_ids)

    q_lower = q.lower()
    results: list[SearchResult] = []
    for app in apps:
        rank = _match_rank(
            q_lower, reference=app.reference, title=app.address,
            other_texts=[app.alternative_reference, app.applicant_name_raw, app.council_code],
        )
        if rank is None:
            continue
        allocation = allocation_by_site_id.get(app.site_id) if app.site_id else None
        matched_label = None
        if allocation is not None:
            matched_label = f"Linked to allocation {allocation['reference_or_name']}"
        results.append(SearchResult(
            entity_type="planning_site",
            entity_id=app.id,
            title=app.address or app.reference,
            subtitle=" · ".join(b for b in (app.reference, app.council_code, app.status) if b),
            council=app.council_code,
            reference=app.reference,
            status=app.status,
            capacity_or_units=_units_display(app),
            matched_entity_id=allocation["id"] if allocation else app.site_id,
            matched_entity_label=matched_label,
            destination_page="pages/1_Scheme_Detail.py",
            destination_params={"site_id": str(app.site_id)} if app.site_id else {},
            match_rank=rank,
            tie_break_id=app.id,
        ))

    return _sort_results(results)[:limit]


def _units_display(app: Application) -> str | None:
    si = getattr(app, "scheme_intelligence", None)
    units = si.total_units_final if si is not None and si.total_units_final else app.estimated_unit_count
    return f"{units:,} units" if units else None


def _load_allocation_links(session, site_ids: list[int]) -> dict[int, dict]:
    """One batched query: which of these matched_site_ids already have a
    LocalPlanSite pointing at them (Part 8's "Planning Site <-> allocation
    already linked" indicator). Never one query per Application."""
    if not site_ids:
        return {}
    rows = session.execute(
        select(LocalPlanSite.matched_site_id, LocalPlanSite.id, LocalPlanSite.policy_reference, LocalPlanSite.site_name)
        .where(LocalPlanSite.matched_site_id.in_(site_ids))
    ).all()
    result: dict[int, dict] = {}
    for matched_site_id, allocation_id, policy_reference, site_name in rows:
        # A Site could in principle match more than one allocation row;
        # the first one found is shown - a search result's cross-link is a
        # pointer for navigation, not an exhaustive relationship list (that
        # full detail already lives on the Allocation Detail page itself).
        result.setdefault(matched_site_id, {
            "id": allocation_id, "reference_or_name": policy_reference or site_name,
        })
    return result


# --- Combined "All" scope (Part 5/8) -----------------------------------------

SEARCH_SCOPES = ("all", "planning_sites", "allocations")


def search_entities(
    session, query: str, *, scope: str = "all", allocation_filters: dict | None = None,
    allowed_site_ids: set[int] | None = None, limit: int = DEFAULT_RESULT_LIMIT,
) -> EntitySearchResults:
    """The one entrypoint app/ui/pages/0_Explore.py calls. scope narrows
    which of the two independent searches actually run - "planning_sites"
    never touches LocalPlanSite, "allocations" never touches Application,
    so neither search path pays for the other's query cost when scoped
    away entirely."""
    if scope not in SEARCH_SCOPES:
        raise ValueError(f"Unknown search scope: {scope!r} (expected one of {SEARCH_SCOPES})")

    allocations: list[SearchResult] = []
    planning_sites: list[SearchResult] = []

    if scope in ("all", "allocations"):
        allocations = search_allocation_entities(session, query, filters=allocation_filters, limit=limit)
    if scope in ("all", "planning_sites"):
        planning_sites = search_planning_site_entities(session, query, allowed_site_ids=allowed_site_ids, limit=limit)

    return EntitySearchResults(query=query, scope=scope, allocations=allocations, planning_sites=planning_sites)
