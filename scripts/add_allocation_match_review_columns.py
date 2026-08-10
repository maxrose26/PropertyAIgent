"""One-off schema migration for Pilot Readiness PR-2 ("Existing Allocation
<-> Site Matches") - adds the three new LocalPlanSite columns
(confirmed_by, confirmed_at, match_review_note) used by
app.policy.site_match_review.

app.db.session._add_missing_columns already does this automatically for
SQLite (the local-dev database) on every init_db() call - this script
exists only because that mechanism explicitly declines to touch a
non-SQLite (Postgres/Supabase production-equivalent) target, per its own
docstring: "Once the Postgres schema needs to evolve after its initial
creation, it should get a real migration tool (e.g. Alembic)". Adding
Alembic is out of scope for this sprint; this script is the same "diff
against what's actually there, ADD COLUMN what's missing" discipline,
made explicit and Postgres-safe (IF NOT EXISTS) rather than automatic.

Safe to run any number of times - IF NOT EXISTS makes every statement a
no-op once the columns already exist, on both dialects.

    python -m scripts.add_allocation_match_review_columns
"""
from __future__ import annotations

from sqlalchemy import text

from app.db.session import get_engine, init_db

_COLUMNS = [
    ("confirmed_by", "VARCHAR(100)"),
    ("confirmed_at", "TIMESTAMPTZ"),
    ("match_review_note", "TEXT"),
]


def main() -> None:
    init_db()  # handles SQLite automatically; a harmless no-op for Postgres here
    engine = get_engine()
    if engine.dialect.name != "postgresql":
        print(f"[add-allocation-match-review-columns] dialect={engine.dialect.name!r} already handled by init_db().")
        return

    with engine.begin() as conn:
        for name, sql_type in _COLUMNS:
            conn.execute(text(f'ALTER TABLE local_plan_sites ADD COLUMN IF NOT EXISTS "{name}" {sql_type}'))
            print(f"[add-allocation-match-review-columns] ensured local_plan_sites.{name} ({sql_type})")


if __name__ == "__main__":
    main()
