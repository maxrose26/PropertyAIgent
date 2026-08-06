"""Copies data from the existing local SQLite database (data/deal_finder.db)
into a Supabase/PostgreSQL database - the data half of the Supabase
migration's Stage 1 (see app.db.session for the engine-selection half; this
script is what actually moves rows once DATABASE_URL points at Postgres).

Non-destructive by construction, not just by convention:
  - The SQLite source is opened in SQLite's own read-only URI mode
    (?mode=ro) - even a bug in this script cannot write back to it. This
    script never calls .commit() against the source engine at all.
  - Every insert into Postgres uses ON CONFLICT (<primary key>) DO NOTHING,
    so rerunning this script after a partial or interrupted run only
    inserts whatever wasn't already copied - never a duplicate, never a
    constraint-violation crash.
  - Each table is copied and committed independently (not one giant
    transaction for the whole database), so a run interrupted partway
    through leaves already-copied tables safely committed - rerunning
    picks up from wherever it stopped, table by table.
  - Primary keys are copied verbatim, never regenerated, so foreign keys
    copied afterwards still point at the right row. Each integer-primary-
    key table's Postgres sequence is reset to MAX(id) once its copy
    finishes, so the live app's own future inserts against Postgres won't
    collide with a migrated id.

Two self-referential foreign key columns exist in this schema today
(MonitoredReport.superseded_by_id, VisualEvidence.superseded_by_id) - a row
can reference another row in the SAME table that (in primary-key order)
hasn't been copied yet. Handled generically for any such column, not just
these two: every row in a table is first inserted with its self-referential
column(s) nulled out, then a second pass UPDATEs just that column back to
its real value now that every row in the table exists.

SQLite does not enforce foreign key constraints unless PRAGMA foreign_keys
is explicitly turned on per-connection, which this project's code never
has - so the source database can (and, confirmed against the real data,
does) contain rows whose foreign key points at a parent that no longer
exists. A nullable such column (e.g. Application.suggested_site_id) is
simply nulled out during migration, same principle as the self-referential
case. A NOT NULL such column (e.g. Document.application_id) has no
recoverable value to fall back to - that row is excluded from the migrated
database rather than crashing the whole run or fabricating a parent, and
every excluded row is printed (table, column, row id) so nothing is ever
silently dropped - see split_dangling_rows.

Usage:
    DATABASE_URL=postgresql://... python -m scripts.migrate_to_postgres
    DATABASE_URL=postgresql://... python -m scripts.migrate_to_postgres --dry-run

Never run this against a DATABASE_URL you don't recognise, and never commit
a real DATABASE_URL anywhere - see .env.example.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
from sqlalchemy import Table, create_engine, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, Engine

from app.db.models import Base
from app.db.session import DB_PATH, _normalize_database_url

BATCH_SIZE = 500


def require_postgres_database_url() -> str:
    """Reads DATABASE_URL from the environment (loading .env first, same as
    every other entrypoint in this project) and fails fast with a clear
    message rather than silently doing nothing, or migrating SQLite into
    itself, which the app's own default (unset DATABASE_URL) engine
    selection would otherwise make easy to do by accident."""
    load_dotenv()
    raw_url = os.getenv("DATABASE_URL")
    if not raw_url:
        raise SystemExit(
            "DATABASE_URL is not set. This script migrates INTO Postgres/Supabase - "
            "set DATABASE_URL to your Supabase connection string first (see .env.example)."
        )
    url = _normalize_database_url(raw_url)
    if not url.startswith("postgresql"):
        raise SystemExit(
            f"DATABASE_URL does not look like a PostgreSQL connection string ({url!r} after "
            "normalisation) - refusing to run, since this script only migrates SQLite -> PostgreSQL."
        )
    return url


def get_source_engine() -> Engine:
    """The existing SQLite database, opened strictly read-only at the
    SQLite level (?mode=ro) - this migration must never delete or overwrite
    the existing SQLite database, enforced here technically rather than
    just by convention: any accidental write attempt raises an
    OperationalError instead of silently succeeding."""
    if not DB_PATH.exists():
        raise SystemExit(f"No SQLite database found at {DB_PATH} - nothing to migrate.")
    return create_engine(f"sqlite:///file:{DB_PATH}?mode=ro&uri=true", future=True)


def get_target_engine(database_url: str) -> Engine:
    return create_engine(database_url, future=True)


def self_referential_columns(table: Table) -> list[str]:
    """Column names on `table` whose ForeignKey target is `table` itself -
    these must be nulled on first insert and backfilled in a second pass
    (see module docstring)."""
    names = []
    for column in table.columns:
        for fk in column.foreign_keys:
            if fk.column.table is table:
                names.append(column.name)
    return names


def to_utc_aware(value):
    """SQLite round-trips a DateTime(timezone=True) column as a naive
    datetime even though every such column in this schema has only ever
    been written as UTC wall-clock time (see the many "SQLite round-trips
    ... as naive" comments across app/pipeline and app/policy, e.g.
    app.policy.monitor._naive_utcnow) - reattach UTC explicitly before
    writing into Postgres's real timestamptz column, so the value isn't
    silently reinterpreted using Postgres's own session TimeZone setting
    instead of the UTC it has always actually meant. A value that's already
    tz-aware (or isn't a datetime at all) is returned unchanged."""
    if isinstance(value, dt.datetime) and value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value


def resolve_missing_defaults(table: Table, row: dict) -> dict:
    """Some columns that the current model declares NOT NULL still hold a
    NULL value in the SQLite source, for rows created before that column
    existed: app.db.session._add_missing_columns's ALTER TABLE ADD COLUMN
    never enforces NOT NULL or backfills existing rows (confirmed against
    the real data - e.g. councils.created_at/updated_at/monitoring_enabled
    and sites.excluded), since SQLite itself doesn't require it, but
    Postgres enforces the constraint for real on the freshly created
    table. Only for a column that (a) the model declares NOT NULL and (b)
    has a Python-side `default` declared, apply that same default here -
    exactly what the ORM would have done for a brand new row left unset.
    A column with no declared default is left alone; this never invents a
    value for one, it only applies a default the model itself already
    specifies."""
    resolved = dict(row)
    for column in table.columns:
        if column.nullable or column.default is None:
            continue
        if resolved.get(column.name) is not None:
            continue
        default = column.default
        # A callable default's .arg is SQLAlchemy's own internally-wrapped
        # invoker, which always expects an ExecutionContext argument (even
        # when, as here, the underlying user function like models.utcnow
        # takes none itself and just ignores it) - None stands in for the
        # real context, which nothing in this schema's defaults ever uses.
        resolved[column.name] = default.arg(None) if default.is_callable else default.arg
    return resolved


def prepare_rows(
    table: Table, rows: list[dict], self_ref_columns: list[str]
) -> tuple[list[dict], list[dict]]:
    """Splits each source row into (insert_row, deferred_update). insert_row
    has every self-referential column nulled, every naive datetime made
    UTC-aware (see to_utc_aware), and any missing-but-defaultable NOT NULL
    value filled in (see resolve_missing_defaults); deferred_update carries
    the real self-referential values, keyed by the table's own primary-key
    columns, to be applied in a second pass once every row in the table
    exists."""
    pk_columns = [c.name for c in table.primary_key.columns]
    insert_rows = []
    deferred_updates = []
    for row in rows:
        insert_row = {k: to_utc_aware(v) for k, v in row.items()}
        insert_row = resolve_missing_defaults(table, insert_row)
        deferred = {}
        for col in self_ref_columns:
            if insert_row.get(col) is not None:
                deferred[col] = insert_row[col]
                insert_row[col] = None
        insert_rows.append(insert_row)
        if deferred:
            deferred.update({pk: row[pk] for pk in pk_columns})
            deferred_updates.append(deferred)
    return insert_rows, deferred_updates


def sequence_reset_statement(table: Table) -> str | None:
    """Postgres only - after copying explicit primary-key values across,
    the table's own auto-increment sequence still starts at 1 and would
    collide with a migrated row the first time the live app inserts a new
    one there. Only applies to a single-column integer primary key (every
    table in this schema except `councils`, whose primary key is its own
    string code and was never auto-incrementing to begin with)."""
    pk_columns = list(table.primary_key.columns)
    if len(pk_columns) != 1:
        return None
    pk = pk_columns[0]
    if pk.type.python_type is not int:
        return None
    return (
        f"SELECT setval(pg_get_serial_sequence('{table.name}', '{pk.name}'), "
        f'COALESCE((SELECT MAX("{pk.name}") FROM "{table.name}"), 1))'
    )


def not_null_foreign_keys_to_other_tables(table: Table) -> list[tuple[str, Table]]:
    """(column_name, target_table) for every NOT NULL foreign key column on
    `table` that points at a DIFFERENT table - self-referential ones are
    handled separately (see self_referential_columns/prepare_rows), since
    those are recoverable (null-then-backfill), unlike a NOT NULL column
    whose required parent genuinely doesn't exist at all."""
    result = []
    for column in table.columns:
        if column.nullable:
            continue
        for fk in column.foreign_keys:
            if fk.column.table is not table:
                result.append((column.name, fk.column.table))
    return result


def nullable_foreign_keys_to_other_tables(table: Table) -> list[tuple[str, Table]]:
    """(column_name, target_table) for every NULLABLE foreign key column on
    `table` that points at a DIFFERENT table - the counterpart to
    not_null_foreign_keys_to_other_tables. Confirmed against the real data:
    2 Application.suggested_site_id values reference a Site that no longer
    exists. Unlike the NOT NULL case, a row here doesn't need to be
    excluded - it's simply nulled out (see null_out_orphaned_nullable_fks),
    the same outcome the app itself would show today querying this via a
    LEFT JOIN against a deleted row."""
    result = []
    for column in table.columns:
        if not column.nullable:
            continue
        for fk in column.foreign_keys:
            if fk.column.table is not table:
                result.append((column.name, fk.column.table))
    return result


def null_out_orphaned_nullable_fks(
    source_conn: Connection, table: Table, rows: list[dict]
) -> tuple[list[dict], dict[str, int]]:
    """Nulls out any nullable_foreign_keys_to_other_tables value that
    doesn't correspond to a row that actually exists (checked against the
    read-only SQLite source, same reasoning as split_dangling_rows - SQLite
    never enforced this constraint, so such a value can exist without ever
    having raised an error). Mutates and returns `rows` in place (each row
    dict is this call's own copy, made in copy_table, so nothing shared
    with the source is touched) along with a {column_name: count} report of
    what was nulled, never done silently."""
    fk_columns = nullable_foreign_keys_to_other_tables(table)
    if not fk_columns:
        return rows, {}

    valid_ids: dict[str, set] = {}
    for _, target_table in fk_columns:
        if target_table.name not in valid_ids:
            pk_col = list(target_table.primary_key.columns)[0]
            valid_ids[target_table.name] = {r[0] for r in source_conn.execute(select(pk_col))}

    nulled_counts: dict[str, int] = {}
    for row in rows:
        for col_name, target_table in fk_columns:
            value = row.get(col_name)
            if value is not None and value not in valid_ids[target_table.name]:
                row[col_name] = None
                nulled_counts[col_name] = nulled_counts.get(col_name, 0) + 1
    return rows, nulled_counts


def split_dangling_rows(
    source_conn: Connection, table: Table, rows: list[dict]
) -> tuple[list[dict], dict[str, list]]:
    """Splits `rows` into (keepable, dangling_by_column). SQLite does not
    enforce foreign key constraints unless PRAGMA foreign_keys=ON is set
    per-connection (this project's own code has never done so), so a row
    can reference a parent that was since deleted without SQLite ever
    objecting - confirmed against the real data (e.g. 36 `documents` rows
    reference an `applications` row that no longer exists). Postgres
    enforces the constraint for real, so a NOT NULL foreign key pointing at
    a genuinely missing parent can't be migrated as-is - there is no
    parent to null it to (unlike a nullable FK, see
    null_out_orphaned_nullable_fks), and fabricating one would misrepresent
    the data. The only sound choice is
    to leave such a row out of the migrated database - but always report
    exactly what and how many, never silently drop it. Checked against the
    read-only SQLite source (not the Postgres target): a table's parent is
    always already fully copied by the time a child table is reached (see
    Base.metadata.sorted_tables' topological order), so the source's own
    parent-table contents are equally authoritative and available in both
    --dry-run and a real run."""
    fk_columns = not_null_foreign_keys_to_other_tables(table)
    if not fk_columns:
        return rows, {}

    valid_ids: dict[str, set] = {}
    for _, target_table in fk_columns:
        if target_table.name not in valid_ids:
            pk_col = list(target_table.primary_key.columns)[0]
            valid_ids[target_table.name] = {r[0] for r in source_conn.execute(select(pk_col))}

    keepable = []
    dangling_by_column: dict[str, list] = {}
    for row in rows:
        dangling_col = next(
            (col for col, target_table in fk_columns if row[col] not in valid_ids[target_table.name]),
            None,
        )
        if dangling_col is None:
            keepable.append(row)
        else:
            dangling_by_column.setdefault(dangling_col, []).append(row)
    return keepable, dangling_by_column


def copy_table(
    source_conn: Connection,
    target_conn: Connection | None,
    table: Table,
    *,
    batch_size: int,
    dry_run: bool,
) -> int:
    self_ref_columns = self_referential_columns(table)
    source_rows = [dict(r._mapping) for r in source_conn.execute(select(table))]
    if not source_rows:
        return 0

    source_rows, nulled_counts = null_out_orphaned_nullable_fks(source_conn, table, source_rows)
    for column_name, count in nulled_counts.items():
        print(
            f"[fix] {table.name}: {count} row(s) had {column_name} nulled out - it referenced "
            "a row that no longer exists in the source database"
        )

    source_rows, dangling_by_column = split_dangling_rows(source_conn, table, source_rows)
    for column_name, dangling_rows in dangling_by_column.items():
        pk_columns = [c.name for c in table.primary_key.columns]
        ids = [tuple(row[pk] for pk in pk_columns) for row in dangling_rows]
        print(
            f"[skip] {table.name}: {len(dangling_rows)} row(s) excluded - {column_name} "
            f"references a row that no longer exists in the source database, ids={ids}"
        )

    insert_rows, deferred_updates = prepare_rows(table, source_rows, self_ref_columns)

    if dry_run:
        print(f"[dry-run] {table.name}: would copy {len(insert_rows)} row(s)")
        return len(insert_rows)

    if not insert_rows:
        return 0

    assert target_conn is not None
    pk_columns = [c.name for c in table.primary_key.columns]
    # cursor.rowcount is unreliable for a multi-row VALUES(...) INSERT ...
    # ON CONFLICT DO NOTHING under psycopg (confirmed empirically: always
    # -1, even when rows genuinely were inserted) - count the table before
    # and after instead, which is accurate regardless of driver rowcount
    # support and cheap at this scale (one extra COUNT per table).
    before_count = target_conn.execute(select(func.count()).select_from(table)).scalar()
    for i in range(0, len(insert_rows), batch_size):
        batch = insert_rows[i : i + batch_size]
        stmt = pg_insert(table).values(batch).on_conflict_do_nothing(index_elements=pk_columns)
        target_conn.execute(stmt)
    after_count = target_conn.execute(select(func.count()).select_from(table)).scalar()
    newly_inserted = after_count - before_count

    for update in deferred_updates:
        pk_filter = {pk: update.pop(pk) for pk in pk_columns}
        if not update:
            continue
        stmt = table.update()
        for pk_name, pk_value in pk_filter.items():
            stmt = stmt.where(table.c[pk_name] == pk_value)
        target_conn.execute(stmt.values(**update))

    reset_sql = sequence_reset_statement(table)
    if reset_sql:
        target_conn.execute(text(reset_sql))

    target_conn.commit()  # commit per table, not one transaction for the whole database - see module docstring

    print(f"[migrate] {table.name}: {len(insert_rows)} row(s) in source, {newly_inserted} newly inserted")
    return len(insert_rows)


def run_migration(*, dry_run: bool = False, batch_size: int = BATCH_SIZE) -> None:
    database_url = require_postgres_database_url()
    source_engine = get_source_engine()
    target_engine = get_target_engine(database_url)

    print(f"Source (read-only): {DB_PATH}")
    print(f"Target: {target_engine.url.render_as_string(hide_password=True)}")

    if not dry_run:
        Base.metadata.create_all(target_engine)  # idempotent - only creates tables that don't exist yet

    total = 0
    try:
        with source_engine.connect() as source_conn:
            if dry_run:
                for table in Base.metadata.sorted_tables:
                    total += copy_table(source_conn, None, table, batch_size=batch_size, dry_run=True)
            else:
                with target_engine.connect() as target_conn:
                    for table in Base.metadata.sorted_tables:
                        total += copy_table(
                            source_conn, target_conn, table, batch_size=batch_size, dry_run=False
                        )
    finally:
        source_engine.dispose()
        target_engine.dispose()

    verb = "Would copy" if dry_run else "Copied"
    print(f"\n{verb} {total} row(s) total across {len(Base.metadata.sorted_tables)} table(s).")
    print(f"Source SQLite database at {DB_PATH} was not modified.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report how many rows would be copied per table without connecting to or writing into Postgres.",
    )
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help=f"Rows per INSERT batch (default {BATCH_SIZE}).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_migration(dry_run=args.dry_run, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
