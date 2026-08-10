"""Planning Application scraper freshness (Pilot Readiness PR-2, "Production
Freshness & Core Data Integrity", Part 7). Pure, DB-free functions - callers
supply the evidence (a council's most recent ScrapeRun rows), this module
only classifies it.

Deliberately reads ScrapeRun (scraper EXECUTION evidence), never
Application.last_seen_at alone, as the basis for a FRESH/STALE verdict -
Part 7's own principle: "Scraper execution health and source activity are
different concepts." A council can have a perfectly healthy daily run that
finds zero new Applications (nothing changed on the portal that day) - that
run is still evidence the scraper is working. Conversely, a council with
recent Application activity scraped days ago by a run that has since stopped
happening would look falsely "fresh" if judged by Application dates alone.
"""
from __future__ import annotations

import datetime as dt

FRESH = "fresh"
WARNING = "warning"
STALE = "stale"
UNKNOWN = "unknown"

FRESHNESS_LABELS = {
    FRESH: "Fresh",
    WARNING: "Ageing",
    STALE: "Stale",
    UNKNOWN: "No run evidence",
}

FRESH_HOURS = 48
WARNING_HOURS = 72


def classify_scraper_freshness(last_successful_run_at: dt.datetime | None, *, now: dt.datetime | None = None) -> str:
    """FRESH: a successful (status in success|partial) run completed
    within the last 48 hours. WARNING: >48h and <=72h. STALE: >72h.
    UNKNOWN: no successful run evidence exists at all for this council -
    never silently defaulted to STALE, since "we have never seen a
    successful run" and "we saw one and it's now old" are different,
    equally honest facts a pilot operator needs told apart (the same
    "missing evidence is not proof of absence" principle CLAUDE.md and the
    PR-1 audit both apply elsewhere in this platform)."""
    if last_successful_run_at is None:
        return UNKNOWN

    now = now or dt.datetime.now(dt.timezone.utc)
    if last_successful_run_at.tzinfo is None:
        last_successful_run_at = last_successful_run_at.replace(tzinfo=dt.timezone.utc)

    age = now - last_successful_run_at
    age_hours = age.total_seconds() / 3600

    if age_hours <= FRESH_HOURS:
        return FRESH
    if age_hours <= WARNING_HOURS:
        return WARNING
    return STALE
