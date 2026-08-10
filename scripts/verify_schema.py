"""Lightweight, deterministic production schema verification command
(Pilot Readiness PR-2 final pre-merge amendment, "Schema Version /
Verification").

Read-only - never mutates anything. Checks that the connected database
already has every table and column app.db.models.Base.metadata currently
declares (at minimum, for this amendment: scrape_runs, confirmed_by,
confirmed_at, match_review_note - but checks the FULL current schema, not
just those four, since the same underlying diff app.db.session.
migrate_schema() uses is reused here rather than hardcoding a one-off
checklist that would silently go stale as the schema grows).

    python -m scripts.verify_schema

Exits 0 and prints "schema is current" if nothing is missing. Exits 1 and
prints exactly which table(s)/column(s) are missing otherwise - intended
as deployment-step 3 (see scripts/migrate_schema.py's own docstring for
the full deployment order) and as a manual operator sanity check. Never
prints connection credentials - only table/column names, which are not
sensitive.
"""
from __future__ import annotations

import sys

from app.db.session import get_engine, verify_schema


def main() -> int:
    engine = get_engine()
    print(f"[verify-schema] target dialect: {engine.dialect.name}")

    missing_tables, missing_columns = verify_schema(engine)

    if not missing_tables and not missing_columns:
        print("[verify-schema] schema is current - every table and column Base.metadata declares is present.")
        return 0

    if missing_tables:
        print(f"[verify-schema] MISSING TABLE(S): {', '.join(sorted(missing_tables))}")
    if missing_columns:
        for table_name, column_name in missing_columns:
            print(f"[verify-schema] MISSING COLUMN: {table_name}.{column_name}")
    print("[verify-schema] Run `python -m scripts.migrate_schema` to fix this.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
