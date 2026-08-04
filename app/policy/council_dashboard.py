"""Builds the internal, administration-facing Council summary (Sprint 2,
"Greater Manchester Policy Intelligence Framework", Part 7) - a pure data-
assembly function, kept separate from Streamlit so this exact assembly is
testable independently of rendering (CLAUDE.md's "keep business logic out
of the UI", the same pattern app.policy.site_view already established for
the Site Profile's Policy Intelligence section).

This is NOT the public Site Profile view. It exists so someone maintaining
the platform can see, per council: what's been onboarded, whether
monitoring is actually working, and what's waiting for a decision - not
for a prospective land buyer or investor.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Council, LocalPlan, LocalPlanSite, MonitoredSource, PolicyChangeEvent

# Worst-to-best - a council's overall monitoring_health is the WORST health
# across its own sources, so a single failing source can't be hidden behind
# others that are fine (the same reasoning app.policy.monitor.check_source
# applies per-source, rolled up to council level here).
_HEALTH_SEVERITY = {"error": 0, "stale": 1, "never_checked": 2, "ok": 3}


def _rollup_monitoring_health(sources: list[MonitoredSource]) -> str:
    if not sources:
        return "no_sources"
    return min((s.monitoring_health for s in sources), key=lambda h: _HEALTH_SEVERITY.get(h, 99))


def summarise_local_plan(session: Session, plan: LocalPlan) -> dict:
    allocations = session.execute(
        select(LocalPlanSite).where(LocalPlanSite.local_plan_id == plan.id)
    ).scalars().all()
    return {
        "plan_id": plan.id,
        "plan_name": plan.plan_name,
        "plan_version": plan.plan_version,
        "status": plan.status,
        "raw_status": plan.raw_status,
        "allocations_imported": len(allocations),
        "sites_matched": sum(1 for a in allocations if a.matched_site_id is not None),
        "last_checked": plan.last_checked,
    }


def summarise_council(session: Session, council: Council) -> dict:
    plans = session.execute(select(LocalPlan).where(LocalPlan.council_code == council.code)).scalars().all()
    sources = session.execute(select(MonitoredSource).where(MonitoredSource.council_code == council.code)).scalars().all()

    plan_ids = {p.id for p in plans}
    source_ids = {s.id for s in sources}
    # A review item belongs to this council if it's attached to one of the
    # council's own plans OR one of its own monitored sources - a source-
    # level change (Part 9's source_content_changed) may have no
    # local_plan_id yet (a council-level landing page with nothing ingested
    # against it) but is still unambiguously this council's own item.
    pending_events = session.execute(
        select(PolicyChangeEvent).where(PolicyChangeEvent.review_status == "needs_review")
    ).scalars().all()
    review_items_pending = sum(
        1 for e in pending_events
        if (e.local_plan_id in plan_ids) or (e.monitored_source_id in source_ids)
    )

    last_checked_values = [s.last_checked for s in sources if s.last_checked is not None]

    return {
        "council_code": council.code,
        "council_name": council.name,
        "authority_type": council.authority_type,
        "monitoring_enabled": council.monitoring_enabled,
        "local_plans": [summarise_local_plan(session, p) for p in plans],
        "sources_count": len(sources),
        "monitoring_health": _rollup_monitoring_health(sources),
        "last_checked": max(last_checked_values) if last_checked_values else None,
        "review_items_pending": review_items_pending,
        "total_allocations_imported": sum(len(session.execute(
            select(LocalPlanSite).where(LocalPlanSite.local_plan_id == p.id)
        ).scalars().all()) for p in plans),
    }


def build_council_dashboard(session: Session) -> list[dict]:
    """One row per council that has any real Policy Intelligence activity -
    monitoring enabled, at least one LocalPlan, or at least one registered
    source. A council configured for application scraping only (most of
    the other 8 Greater Manchester boroughs, at this sprint) is correctly
    left out - there is nothing to administer for it yet."""
    councils = session.execute(select(Council)).scalars().all()
    rows = []
    for council in councils:
        has_plans = session.execute(
            select(LocalPlan).where(LocalPlan.council_code == council.code)
        ).first() is not None
        has_sources = session.execute(
            select(MonitoredSource).where(MonitoredSource.council_code == council.code)
        ).first() is not None
        if not (council.monitoring_enabled or has_plans or has_sources):
            continue
        rows.append(summarise_council(session, council))
    return rows
