"""SUPERSEDED by python -m scripts.migrate_schema (Pilot Readiness PR-2
final pre-merge amendment, "Implement The Smallest Explicit Migration
Mechanism") - kept only as a documented, still-safe alias, not because it
does anything scripts.migrate_schema doesn't already do on its own now.

Originally written to add the three new LocalPlanSite columns
(confirmed_by, confirmed_at, match_review_note) used by
app.policy.site_match_review. Briefly (during PR-2's pre-merge check) this
became a thin wrapper around app.db.session.init_db(), when init_db() was
still responsible for schema mutation on every dialect. That is no longer
true: init_db() now only ever mutates schema automatically on SQLite -
on PostgreSQL/Supabase (production) it performs a read-only verification
and raises loudly if the schema isn't current (Product Owner review:
"Normal customer page loads should NOT perform schema evolution" -
see app.db.session.init_db's own docstring). The actual mutation now
lives in app.db.session.migrate_schema, invoked explicitly via
python -m scripts.migrate_schema, which is the current, preferred command.

This script is retained only so anyone who still remembers its old name
keeps a safe, documented path - it is nothing more than a call to
scripts.migrate_schema.main() itself. Safe to run any number of times.

    python -m scripts.add_allocation_match_review_columns
"""
from __future__ import annotations

from scripts.migrate_schema import main as migrate_schema_main


def main() -> None:
    migrate_schema_main()


if __name__ == "__main__":
    main()
