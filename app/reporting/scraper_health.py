"""Council-by-council Planning Application scraper health (Pilot Readiness
PR-2, Part 6/7) - the one DB-touching entrypoint behind Council Operations'
new "Planning Application Scraper Health" section, mirroring
app.reporting.allocation_discovery's own "pure functions + one query-
assembly entrypoint" split (CLAUDE.md: "keep business logic out of the UI").
"""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import Council, ScrapeRun
from app.pipeline.freshness import FRESHNESS_LABELS, classify_scraper_freshness


def build_scraper_health_summary(session) -> list[dict]:
    """One row per council with any ScrapeRun history, plus every council
    with none at all (UNKNOWN, not omitted - a council this platform is
    configured to scrape but has never successfully run for is itself the
    signal, not something to hide by only listing councils with data)."""
    councils = session.execute(select(Council)).scalars().all()

    rows = []
    for council in councils:
        runs = session.execute(
            select(ScrapeRun).where(ScrapeRun.council_code == council.code).order_by(ScrapeRun.started_at.desc())
        ).scalars().all()

        last_attempt = runs[0] if runs else None
        last_success = next((r for r in runs if r.status in ("success", "partial")), None)

        freshness = classify_scraper_freshness(last_success.finished_at if last_success else None)

        rows.append({
            "council_code": council.code,
            "council_name": council.name,
            "last_attempted_at": last_attempt.started_at if last_attempt else None,
            "last_attempt_status": last_attempt.status if last_attempt else None,
            "last_successful_at": last_success.finished_at if last_success else None,
            "last_run_applications_discovered": last_success.applications_discovered if last_success else None,
            "freshness": freshness,
            "freshness_label": FRESHNESS_LABELS[freshness],
            "total_runs_recorded": len(runs),
        })

    return sorted(rows, key=lambda r: r["council_name"])
