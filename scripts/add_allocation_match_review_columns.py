"""SUPERSEDED by app.db.session._add_missing_columns (Pilot Readiness PR-2
pre-merge architecture check, "Database Schema Deployment Safety") -
kept only as an explicit, documented, still-safe manual entry point, not
because it does anything init_db() doesn't already do on its own now.

Originally written to add the three new LocalPlanSite columns
(confirmed_by, confirmed_at, match_review_note) used by
app.policy.site_match_review, back when app.db.session._add_missing_
columns explicitly declined to touch any non-SQLite (Postgres/Supabase
production) target. That early-return has since been removed - the
underlying "diff what's actually there, ADD COLUMN what's missing" logic
was already fully dialect-agnostic, so init_db() alone now provisions
BOTH the scrape_runs table (via create_all, already worked) AND these
three columns (via the now-generalised _add_missing_columns) on Postgres,
automatically, on every process that calls init_db() - which is already
every Streamlit page load (app.ui.common.bootstrap) and every
app.pipeline.run_weekly invocation. No separate manual step is required
before deploying code that depends on these columns.

This script is retained only so an operator who wants to explicitly
provision the schema ahead of a deploy (rather than relying on it
happening automatically on next boot) still has a documented, safe way to
do so. Safe to run any number of times - idempotent by construction,
since it is now nothing more than a call to init_db() itself.

    python -m scripts.add_allocation_match_review_columns
"""
from __future__ import annotations

from app.db.session import init_db


def main() -> None:
    init_db()
    print("[add-allocation-match-review-columns] init_db() completed - schema is now current on both SQLite and "
          "PostgreSQL (see this script's own docstring: this is now a thin wrapper, not separate logic).")


if __name__ == "__main__":
    main()
