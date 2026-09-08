"""Opportunity Experience V2 - the unified Dashboard "Opportunities" feed.

Product framing (see the Opportunity Experience V2 brief): the live product
review found the Dashboard presenting opportunities primarily as technical/
deterministic SIGNAL categories ("Approaching lapse date", "Low housing
supply", "Allocations without planning applications") rather than as actual
OPPORTUNITIES a land professional can open and investigate. This module is
the fix - a small, PRESENTATION-ONLY layer that reshapes already-computed,
already-tested intelligence into one unified card shape, sorted so real
opportunities (strategic land + planning/delivery) lead, with plan/council
-level context (low housing supply, emerging policy, recent policy
activity, recently adopted plans) deliberately excluded - those describe a
COUNCIL/PLAN's state, not an investigable Site/allocation, and stay
addressed by the Dashboard's existing separate "Policy Intelligence"
section rather than being mislabelled as opportunities here (Step 6's own
instruction: "Do not call low housing supply itself a land opportunity. It
is contextual evidence.").

Deliberately NOT a new intelligence engine - every classification below is
read straight from functions that already existed before this workstream:
- app.reporting.allocation_development_coverage.build_allocation_
  development_coverage / build_opportunity_signal (Gate 3A/4C - unchanged).
- app.policy.allocation_planning_coverage.classify_planning_activity_
  coverage / enrich_none_found_reason / PLANNING_ACTIVITY_COVERAGE_LABELS
  (Gate 4B/4C - unchanged).
- app.reporting.allocation_discovery.format_capacity / capacity_range_
  labels / PLAN_STATUS_META (unchanged, except capacity_range_labels is
  itself new this workstream - see that module's own docstring).
- app.reporting.dashboard's own existing, tested _approaching_lapse_cards
  / _undeveloped_phase_cards (planning/delivery signals) - reused
  verbatim, only reshaped into the same unified card dict below.

No new opportunity score. Sort order is fixed and explainable (see
build_opportunity_feed's own docstring), never a computed ranking.
"""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import LocalPlan, LocalPlanSite, Site
from app.policy.allocation_planning_coverage import (
    PLANNING_ACTIVITY_COVERAGE_LABELS,
    classify_planning_activity_coverage,
    enrich_none_found_reason,
)
from app.reporting.allocation_development_coverage import (
    INSUFFICIENT_EVIDENCE,
    INVESTIGATE,
    LOWER_PRIORITY,
    MONITOR,
    build_allocation_development_coverage,
    build_opportunity_signal,
)
from app.reporting.allocation_discovery import (
    OPPORTUNITY_DETAIL_LABELS,
    PLAN_STATUS_META,
    capacity_range_labels,
    format_capacity,
)
from app.policy.buyer_matching import (
    NOT_SUITABLE,
    STRONG_FIT,
    build_planning_delivery_matching_facts,
    build_strategic_land_matching_facts,
)

STRATEGIC_LAND = "strategic_land"
PLANNING_DELIVERY = "planning_delivery"

OPPORTUNITY_TYPE_LABELS = {
    STRATEGIC_LAND: "Strategic land",
    PLANNING_DELIVERY: "Planning / delivery",
}

# Only these two signals represent something genuinely "worth investigating"
# today (Product Objective #2) - LOWER_PRIORITY/INSUFFICIENT_EVIDENCE
# allocations are real, correctly classified, and remain fully visible on
# Allocation Discovery's own browse/filter table; they are just not
# promoted onto the Dashboard's small, curated opportunity feed. A
# deterministic filter on an already-computed classification, not a new
# scoring model.
_FEED_ELIGIBLE_SIGNALS = (INVESTIGATE, MONITOR)


def _strategic_land_cards(session, limit: int) -> list[dict]:
    """Bounded, presentation-only reshaping of the same Stage 3A/Gate 4B/4C
    engines the Allocation Discovery detail page already uses - deliberately
    NOT app.reporting.allocation_discovery.build_allocation_discovery
    (which builds a card for all ~287 allocations every call); this scopes
    build_allocation_development_coverage to a small, already-bounded
    candidate set instead, so the Dashboard's own query cost stays
    proportional to `limit`, not the whole platform."""
    candidates = session.execute(
        select(LocalPlanSite)
        .where(LocalPlanSite.matched_site_id.is_(None), LocalPlanSite.minimum_dwellings.is_not(None))
        .order_by(LocalPlanSite.minimum_dwellings.desc(), LocalPlanSite.id.desc())
        .limit(max(limit * 3, 12))  # overfetch: some candidates will be filtered out by _FEED_ELIGIBLE_SIGNALS below
    ).scalars().all()
    if not candidates:
        return []

    coverage_by_id = build_allocation_development_coverage(session, candidates)

    plan_ids = {a.local_plan_id for a in candidates if a.local_plan_id}
    plans_by_id = {p.id: p for p in session.execute(select(LocalPlan).where(LocalPlan.id.in_(plan_ids))).scalars()} if plan_ids else {}

    council_codes = {a.council_code for a in candidates}
    sites_by_council: dict[str, list[Site]] = {
        cc: list(session.execute(select(Site).where(Site.council_code == cc)).scalars()) for cc in council_codes
    }

    cards: list[dict] = []
    for a in candidates:
        if len(cards) >= limit:
            break
        result = coverage_by_id.get(a.id)
        if result is None:
            continue
        plan = plans_by_id.get(a.local_plan_id)
        plan_meta = PLAN_STATUS_META.get(plan.status if plan else None, PLAN_STATUS_META[None])
        opportunity = build_opportunity_signal(
            plan_status_bucket=plan_meta["bucket"], coverage=result["coverage"], phasing=result["phasing"],
        )
        if opportunity["signal"] not in _FEED_ELIGIBLE_SIGNALS:
            continue
        opportunity = enrich_none_found_reason(a.site_name, sites_by_council.get(a.council_code, []), opportunity)

        activity_coverage = classify_planning_activity_coverage(result["coverage"])
        capacity = format_capacity(a)
        range_labels = capacity_range_labels(capacity, a.source_excerpt)

        # Site area always shown - "Not yet verified" rather than omitted
        # when absent, never a bare 0 ha (matches the Opportunity Profile's
        # own hero metrics - one consistent rule, not two).
        metrics = [("Site area", f"{a.site_area_hectares:,.2f} ha" if a.site_area_hectares is not None else "Not yet verified")]
        if range_labels and a.minimum_dwellings is not None and a.maximum_capacity is not None:
            metrics.append((range_labels[0], f"{a.minimum_dwellings:,} homes"))
            metrics.append((range_labels[1], f"{a.maximum_capacity:,} homes"))
        else:
            # "Capacity (range)" disambiguates a bare min/max range from a
            # single figure - the same rule the Opportunity Profile detail
            # page uses (never a different label for the same fact shown
            # in two places).
            capacity_label = "Capacity (range)" if capacity["kind"] == "range" else "Capacity"
            metrics.append((capacity_label, capacity["display"]))

        tags = [OPPORTUNITY_TYPE_LABELS[STRATEGIC_LAND], plan_meta["label"], PLANNING_ACTIVITY_COVERAGE_LABELS[activity_coverage.classification]]

        cards.append({
            "id": f"opp-feed-alloc-{a.id}",
            "opportunity_type": STRATEGIC_LAND,
            "opportunity_type_label": OPPORTUNITY_TYPE_LABELS[STRATEGIC_LAND],
            "title": a.site_name,
            "subtitle": f"{a.council_code} · {a.policy_reference}" if a.policy_reference else a.council_code,
            "signal": opportunity["signal"],
            "signal_label": OPPORTUNITY_DETAIL_LABELS.get(opportunity["signal"], opportunity["signal"]),
            "headline_reason": opportunity["reasons"][0] if opportunity["reasons"] else None,
            "metrics": metrics,
            "tags": tags,
            "page": "pages/3_Local_Plan_Sites.py",
            "params": {"allocation_id": str(a.id)},
            "when": a.updated_at,
            # Buyer Profiles V1 - computed here, once, from the exact same
            # allocation/coverage/phasing objects already in scope in this
            # loop (no re-query) - None in generic mode until a buyer-fit
            # pass (build_opportunity_feed, buyer_key set) reads it.
            "matching_facts": build_strategic_land_matching_facts(a, result["coverage"], result["phasing"]),
        })
    return cards


def _reshape_signal_card(card: dict, *, opportunity_type: str, extra_tags: list[str]) -> dict:
    """Reshapes an existing app.reporting.dashboard planning/delivery card
    (already real, already tested - see _approaching_lapse_cards/
    _undeveloped_phase_cards) into the same unified shape _strategic_land_
    cards produces above, without inventing a signal these functions never
    computed (Step 3/24: "Do not pretend these are identical... Do not
    force allocation-specific fields onto planning-application
    opportunities") - "signal" stays None; the card's own real reason/
    metric carry the explanation instead. "matching_facts" starts None -
    _attach_planning_delivery_matching_facts (below) fills it in, in a
    single batched pass over every reshaped card, only when buyer matching
    is actually requested."""
    return {
        "id": card["id"],
        "opportunity_type": opportunity_type,
        "opportunity_type_label": OPPORTUNITY_TYPE_LABELS[opportunity_type],
        "title": card["title"],
        "subtitle": card["subtitle"],
        "signal": None,
        "signal_label": None,
        "headline_reason": card["reason"],
        "metrics": [("Status", card["metric"])],
        "tags": [OPPORTUNITY_TYPE_LABELS[opportunity_type], *extra_tags],
        "page": card["page"],
        "params": card["params"],
        "when": card["when"],
        "matching_facts": None,
    }


def _attach_planning_delivery_matching_facts(session, cards: list[dict]) -> None:
    """Buyer Profiles V1 - batched, additive enrichment of already-built
    planning/delivery cards with a MatchingFacts reader over
    SchemeIntelligence, mutating each card's own "matching_facts" key in
    place. Never touches app.reporting.dashboard's own card-building
    functions - this reads the same site_id every one of their cards
    already carries in "params", via one batched query for every card in
    the list, not one query per card. The representative application per
    Site is chosen by the SAME app.ui.common.pick_representative_application
    every other part of the platform already uses - never a second,
    parallel "which application matters" rule invented here."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.db.models import Application
    from app.ui.common import pick_representative_application

    site_ids = {int(c["params"]["site_id"]) for c in cards if c.get("params", {}).get("site_id")}
    if not site_ids:
        return

    apps = session.execute(
        select(Application)
        .where(Application.site_id.in_(site_ids))
        .options(selectinload(Application.scheme_intelligence))
    ).scalars().all()
    apps_by_site: dict[int, list] = {}
    for app in apps:
        apps_by_site.setdefault(app.site_id, []).append(app)

    facts_by_site_id = {}
    for site_id, site_apps in apps_by_site.items():
        rep = pick_representative_application(site_apps)
        si = rep.scheme_intelligence if rep else None
        facts_by_site_id[site_id] = build_planning_delivery_matching_facts(si)

    for card in cards:
        site_id_raw = card.get("params", {}).get("site_id")
        if site_id_raw is not None:
            card["matching_facts"] = facts_by_site_id.get(int(site_id_raw))


def _generic_selection(strategic: list[dict], delivery: list[dict], limit: int) -> list[dict]:
    """The original Opportunity Experience V2 ordering (Step 8), extracted
    unchanged so buyer mode can reuse the exact same rule rather than a
    parallel copy of it - see build_opportunity_feed's own docstring for
    the full rationale, preserved verbatim here."""
    investigate_cards = [c for c in strategic if c["signal"] == INVESTIGATE]
    monitor_cards = [c for c in strategic if c["signal"] == MONITOR]

    delivery_reserved = min(len(delivery), limit // 2) if delivery else 0
    strategic_slots = limit - delivery_reserved
    chosen_strategic = investigate_cards[:strategic_slots]
    remaining_strategic_slots = strategic_slots - len(chosen_strategic)
    if remaining_strategic_slots > 0:
        chosen_strategic += monitor_cards[:remaining_strategic_slots]
    chosen_delivery = delivery[:limit - len(chosen_strategic)]

    return (chosen_strategic + chosen_delivery)[:limit]


def _buyer_selection(session, strategic: list[dict], delivery: list[dict], limit: int, buyer_key: str) -> tuple[list[dict], dict]:
    """Buyer Profiles V1 (Phase 1 pilot) - selects and orders the STRONGEST
    candidates for one buyer from the FULL candidate pool passed in (built
    at a materially larger pool_limit than generic mode - see
    build_opportunity_feed), not merely a re-filter of the generic top-N.
    This is the one place this module departs from "reuse the generic
    selection verbatim" - the brief's own "Critical Feed Requirement" is
    explicit that filtering only the existing small generic feed would not
    constitute meaningful personalisation.

    Ordering (deterministic, documented, never a score):
      1. STRONG_FIT
      2. INSUFFICIENT_EVIDENCE marked as an investigative exception
      3. INSUFFICIENT_EVIDENCE, not an investigative exception
    NOT_SUITABLE opportunities are excluded from the personalised feed
    entirely (the count is still reported - see the returned counts dict -
    so nothing is silently dropped from view; a buyer-fit assessment is
    always still computable and reviewable via the Opportunity Profile's
    own "Fit for <buyer>" section for any opportunity, generic-mode
    included). Within each bucket, the pool's own existing order (strategic
    land already capacity-ranked; planning/delivery already lapse/date-
    ranked) is preserved - buyer-fit never re-ranks by scale itself."""
    from app.policy.buyer_matching import assess_buyer_fit
    from app.policy.buyer_profile_store import get_buyer_profile_dataclass

    profile = get_buyer_profile_dataclass(session, buyer_key)
    if profile is None:
        # buyer_key no longer resolves to an active persisted or template
        # profile (e.g. archived between selection and this render) -
        # degrade gracefully rather than crash; the UI's own buyer_selector
        # only ever offers currently-active keys, so this is a defensive
        # fallback, not an expected path.
        return [], {"excluded_not_suitable": 0}
    _attach_planning_delivery_matching_facts(session, delivery)

    strong, exception, insufficient = [], [], []
    excluded_not_suitable = 0
    for card in (*strategic, *delivery):
        facts = card.get("matching_facts")
        if facts is None:
            continue
        assessment = assess_buyer_fit(profile, facts)
        card["buyer_fit"] = assessment
        if assessment.classification == NOT_SUITABLE:
            excluded_not_suitable += 1
            continue
        if assessment.classification == STRONG_FIT:
            strong.append(card)
        elif assessment.is_investigative_exception:
            exception.append(card)
        else:
            insufficient.append(card)

    ordered = (strong + exception + insufficient)[:limit]
    return ordered, {"excluded_not_suitable": excluded_not_suitable}


def build_opportunity_feed(session, limit: int = 6, buyer_key: str | None = None) -> dict:
    """The Dashboard's own opportunity feed. Returns {"cards": [...],
    "counts": {...}, "buyer_key": buyer_key} - counts cover every candidate
    considered (not just the ones shown), so a caller can show an honest
    "N more" / "view all" line without re-querying.

    Generic mode (buyer_key=None, the default - unchanged from Opportunity
    Experience V2): candidate pool size equals `limit` itself, and
    selection/ordering is exactly _generic_selection above - byte-for-byte
    the same behaviour this function always had.

    Buyer mode (buyer_key set - Buyer Profiles V1): the candidate pool is
    deliberately widened to a fixed, bounded ceiling (never unbounded/a
    full-platform search - "preserve bounded performance" per the brief)
    so buyer-fit selection has a genuinely larger universe to choose the
    strongest opportunities from, not just the generic top-6 re-filtered -
    see _buyer_selection's own docstring for the selection/ordering rule.

    Sort order within generic mode (transparent, never a score - Step 8):
    strategic land (INVESTIGATE, then MONITOR) first, since this
    workstream's own product review found strategic Local Plan
    opportunities specifically buried under a technical category label
    and asked for them promoted; then planning/delivery items in their own
    existing, already-sorted order (approaching lapse - genuinely
    time-bound - before undeveloped phase); scale (capacity/hectares,
    already the tie-break within each source query) is never used to rank
    ACROSS types, only within one."""
    from app.reporting.dashboard import (  # local import: avoids a circular import (dashboard.py may grow a reason to import this module later)
        _approaching_lapse_cards,
        _recent_permission_cards,
        _undeveloped_phase_cards,
    )

    # Buyer mode needs a materially larger pool to select FROM (the
    # brief's own "Critical Feed Requirement") - a fixed, documented
    # ceiling, not the display limit itself and not unbounded. This
    # bounded-feed pool is a deliberately DIFFERENT, narrower concern from
    # app.reporting.opportunity_universe's own ALWAYS-complete canonical
    # read model (Gate 1) - the Dashboard's own UI feed stays intentionally
    # bounded exactly as before Gate 1C, now just with a fourth type also
    # drawing from the same bounded pool.
    pool_limit = limit if buyer_key is None else max(limit * 8, 40)

    strategic = _strategic_land_cards(session, pool_limit)
    lapse_raw = _approaching_lapse_cards(session, pool_limit)
    undeveloped_raw = _undeveloped_phase_cards(session, pool_limit)
    # Gate 1C - recent_permission never duplicates a site the two
    # established signals above already cover (same precedence rule as
    # app.reporting.opportunity_universe's own canonical read model).
    already_covered_site_ids = frozenset(
        int(c["params"]["site_id"]) for c in (*lapse_raw, *undeveloped_raw)
    )
    recent_permission_raw = _recent_permission_cards(session, pool_limit, exclude_site_ids=already_covered_site_ids)

    lapse = [_reshape_signal_card(c, opportunity_type=PLANNING_DELIVERY, extra_tags=["Approaching lapse"]) for c in lapse_raw]
    undeveloped = [_reshape_signal_card(c, opportunity_type=PLANNING_DELIVERY, extra_tags=["Undeveloped permission"]) for c in undeveloped_raw]
    recent_permission = [
        _reshape_signal_card(c, opportunity_type=PLANNING_DELIVERY, extra_tags=["Recent permission"])
        for c in recent_permission_raw
    ]
    # Already sorted within each source query - lapse (time-bound) and
    # undeveloped permission (an already-detected phase) are the more
    # established, higher-confidence signals and are listed first;
    # recent_permission - the newest, broadest-window signal, deliberately
    # last - only fills a reserved delivery slot once those two have been
    # exhausted (Gate 1C Section 18: "do NOT allow RECENT_PERMISSION
    # candidates to overwhelm the existing strategic/planning mix merely
    # because there are more of them"). Buyer mode's own selection (below)
    # still finds a genuine recent_permission STRONG_FIT regardless of
    # this ordering, since it buckets by classification, not list position.
    delivery = [*lapse, *undeveloped, *recent_permission]

    counts = {
        "strategic_land": len(strategic),
        "approaching_lapse": len(lapse_raw),
        "undeveloped_phase": len(undeveloped_raw),
        "recent_permission": len(recent_permission_raw),
    }

    if buyer_key is None:
        ordered = _generic_selection(strategic, delivery, limit)
    else:
        ordered, buyer_counts = _buyer_selection(session, strategic, delivery, limit, buyer_key)
        counts.update(buyer_counts)

    return {"cards": ordered, "counts": counts, "buyer_key": buyer_key}
