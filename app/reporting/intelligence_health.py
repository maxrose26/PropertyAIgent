"""Intelligence Processing run health (AI Processing Reliability & Backlog
Throughput) - the minimum operator visibility needed to know whether the
bounded daily AI extraction/summary job is actually healthy, mirroring
app.reporting.scraper_health's own "one query-assembly entrypoint" split
(CLAUDE.md: "keep business logic out of the UI"). The prior audit
(PR-2 AI Intelligence Freshness & Continuous Processing Audit) found
IntelligenceRun referenced nowhere outside app/db/models.py - no UI
surfaced it at all. IntelligenceRun (unlike ScrapeRun) is not council-
scoped - one run processes work across every selected council in a single
bounded pass - so this returns a single latest-run summary, not a
per-council table.
"""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import IntelligenceRun


def build_intelligence_health_summary(session) -> dict | None:
    """The most recent IntelligenceRun, or None if the job has never run
    yet - "no run evidence" is itself the operationally relevant signal
    (same principle as scraper_health's per-council UNKNOWN state), not
    something to hide behind a default."""
    run = session.execute(
        select(IntelligenceRun).order_by(IntelligenceRun.started_at.desc())
    ).scalars().first()
    if run is None:
        return None

    return {
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "triggered_by": run.triggered_by,
        "extractions_candidates_inspected": run.extractions_candidates_inspected,
        "extractions_attempted": run.extractions_attempted,
        "extractions_succeeded": run.extractions_succeeded,
        "extractions_no_usable_text": run.extractions_no_usable_text,
        "extractions_failed": run.extractions_failed,
        "summaries_attempted": run.summaries_attempted,
        "summaries_succeeded": run.summaries_succeeded,
        "summaries_failed": run.summaries_failed,
        "applications_backlog_remaining": run.applications_backlog_remaining,
        "sites_backlog_remaining": run.sites_backlog_remaining,
        "detail": run.detail,
    }
