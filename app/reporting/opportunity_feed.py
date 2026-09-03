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
    metric carry the explanation instead."""
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
    }


def build_opportunity_feed(session, limit: int = 6) -> dict:
    """The Dashboard's own small, curated opportunity feed. Returns
    {"cards": [...], "counts": {...}} - counts cover every card considered
    (not just the ones shown), so a caller can show an honest "N more" /
    "view all" line without re-querying.

    Sort order (transparent, never a score - Step 8): strategic land
    (INVESTIGATE, then MONITOR) first, since this workstream's own product
    review found strategic Local Plan opportunities specifically buried
    under a technical category label and asked for them promoted; then
    planning/delivery items in their own existing, already-sorted order
    (approaching lapse - genuinely time-bound - before undeveloped phase);
    scale (capacity/hectares, already the tie-break within each source
    query) is never used to rank ACROSS types, only within one."""
    from app.reporting.dashboard import _approaching_lapse_cards, _undeveloped_phase_cards  # local import: avoids a circular import (dashboard.py may grow a reason to import this module later)

    strategic = _strategic_land_cards(session, limit)
    lapse_raw = _approaching_lapse_cards(session, limit)
    undeveloped_raw = _undeveloped_phase_cards(session, limit)

    lapse = [_reshape_signal_card(c, opportunity_type=PLANNING_DELIVERY, extra_tags=["Approaching lapse"]) for c in lapse_raw]
    undeveloped = [_reshape_signal_card(c, opportunity_type=PLANNING_DELIVERY, extra_tags=["Undeveloped permission"]) for c in undeveloped_raw]
    delivery = [*lapse, *undeveloped]  # already sorted within each source query - lapse (time-bound) first

    investigate_cards = [c for c in strategic if c["signal"] == INVESTIGATE]
    monitor_cards = [c for c in strategic if c["signal"] == MONITOR]

    # Reserve roughly half the feed for planning/delivery opportunities
    # whenever any exist, rather than letting strategic land - which is
    # usually more numerous - crowd them out entirely by raw count. A
    # fixed, explainable reservation rule, never a cross-type score: both
    # opportunity types remain genuinely discoverable together, matching
    # this workstream's own "planning/delivery opportunities remain
    # supported" requirement.
    delivery_reserved = min(len(delivery), limit // 2) if delivery else 0
    strategic_slots = limit - delivery_reserved
    chosen_strategic = investigate_cards[:strategic_slots]
    remaining_strategic_slots = strategic_slots - len(chosen_strategic)
    if remaining_strategic_slots > 0:
        chosen_strategic += monitor_cards[:remaining_strategic_slots]
    chosen_delivery = delivery[:limit - len(chosen_strategic)]

    ordered = (chosen_strategic + chosen_delivery)[:limit]

    return {
        "cards": ordered,
        "counts": {
            "strategic_land": len(strategic),
            "approaching_lapse": len(lapse_raw),
            "undeveloped_phase": len(undeveloped_raw),
        },
    }
