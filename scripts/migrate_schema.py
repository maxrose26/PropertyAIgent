"""Explicit production schema migration command (Pilot Readiness PR-2 final
pre-merge amendment, "Database Migrations Must Not Be A Page-Load Side
Effect" / "Implement The Smallest Explicit Migration Mechanism").

Applies every schema change Base.metadata (app.db.models) currently
declares that the connected database doesn't have yet: creates missing
tables (e.g. scrape_runs, intelligence_runs) and ADD COLUMNs missing
columns on existing tables (e.g. LocalPlanSite.confirmed_by/confirmed_at/
match_review_note). See app.db.session.migrate_schema for the underlying
mechanism (create_all + the dialect-agnostic diff-and-ALTER logic that was
already in place before this amendment - no new migration framework was
introduced, per explicit instruction not to unless genuinely necessary).

    python -m scripts.migrate_schema

Idempotent - safe to run any number of times, including against a database
that's already fully current (logged as a no-op). Fails loudly (lets the
underlying exception propagate with a non-zero exit code) rather than
partially applying a migration; on PostgreSQL the ADD COLUMN statements run
inside one transaction (engine.begin()), so a failure partway through
rolls back atomically.

Production deployment order (see docs/PLATFORM_ARCHITECTURE.md for the
full explanation):
    1. Deploy/make this command available (ship the new code, don't start
       it yet - or run this command as a one-off pre-deploy step).
    2. Execute this migration: python -m scripts.migrate_schema
    3. Verify: python -m scripts.verify_schema (must print "schema is
       current" / exit 0 before continuing).
    4. Start/restart the application (Streamlit web service).
    5. Start/allow the cron jobs (Daily Discovery, Intelligence
       Processing) to run.

Ordinary application startup (Streamlit's bootstrap(), run_weekly.py,
run_daily_councils.py, run_intelligence_processing.py) never calls this -
it only ever calls app.db.session.init_db(), which on a non-SQLite
(production) target performs a read-only schema check and raises loudly if
this command hasn't been run yet. This command contains no credentials -
it uses the same DATABASE_URL every other entry point already reads from
the environment.
"""
from __future__ import annotations

from app.db.session import get_engine, migrate_schema


def main() -> None:
    engine = get_engine()
    print(f"[migrate-schema] target dialect: {engine.dialect.name}")

    created_tables, added_columns = migrate_schema(engine)

    if not created_tables and not added_columns:
        print("[migrate-schema] schema already fully current - no changes made.")
        return

    print(
        f"[migrate-schema] done. {len(created_tables)} table(s) created, "
        f"{len(added_columns)} column(s) added."
    )


if __name__ == "__main__":
    main()
