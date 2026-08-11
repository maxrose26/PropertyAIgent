from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "deal_finder.db"

_engine = None
_SessionLocal: sessionmaker | None = None


def _normalize_database_url(url: str) -> str:
    """Supabase's own dashboard hands out a plain postgresql://... (or the
    legacy postgres://... scheme some tools still emit) connection string,
    whose default SQLAlchemy driver is psycopg2 - not a dependency of this
    project (psycopg 3 is, per the Supabase migration's dependency choice).
    Rewrite either scheme to explicitly request the psycopg 3 driver so a
    connection string copied verbatim out of Supabase's dashboard just
    works, without asking anyone to hand-edit it. A URL that already names
    a driver (postgresql+psycopg://, postgresql+psycopg2://, ...) is left
    exactly as given."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def get_engine():
    global _engine
    if _engine is None:
        # Unlike this project's other entrypoints (app.ui.common.bootstrap,
        # app.pipeline.run_weekly.main, ...), this deliberately does NOT
        # pass override=True: a DATABASE_URL already present in the real
        # environment (a deployment platform's own env var, or a value a
        # test has monkeypatched) must always win over whatever a stray
        # local .env file happens to contain - not the other way round.
        load_dotenv()
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            _engine = create_engine(_normalize_database_url(database_url), future=True)
        else:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            _engine = create_engine(f"sqlite:///{DB_PATH}", future=True)
    return _engine


class SchemaVerificationError(RuntimeError):
    """Raised by init_db() on a non-SQLite engine when Base.metadata
    declares a table or column that does not yet exist in the connected
    database. Fixing this requires running the explicit migration command
    (python -m scripts.migrate_schema) - init_db() itself deliberately
    never mutates a non-SQLite schema to fix it automatically. See this
    module's own docstring-level comments on init_db()/migrate_schema()
    for the full reasoning (Pilot Readiness PR-2 final pre-merge
    amendment, "Database Migrations Must Not Be A Page-Load Side
    Effect")."""


def _diff_missing_columns(engine) -> tuple[list[str], list[tuple[str, str]]]:
    """Read-only diff of Base.metadata against the connected database.
    Returns (missing_table_names, [(table_name, column_name), ...]) -
    shared by both migrate_schema() (which then ADD COLUMNs/CREATE
    TABLEs what this finds) and verify_schema() (which only ever reports
    it). Never opens a transaction or mutates anything itself."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    missing_tables: list[str] = []
    missing_columns: list[tuple[str, str]] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            missing_tables.append(table.name)
            continue
        existing_columns = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name not in existing_columns:
                missing_columns.append((table.name, column.name))
    return missing_tables, missing_columns


def verify_schema(engine) -> tuple[list[str], list[tuple[str, str]]]:
    """Read-only check: does the connected database already have every
    table and column Base.metadata currently declares? Returns
    (missing_table_names, [(table_name, column_name), ...]), both empty
    when the schema is fully current. Never mutates anything - this is
    the "verify/use expected schema" half of the startup/migration split
    (see init_db() and scripts/migrate_schema.py)."""
    return _diff_missing_columns(engine)


def _add_missing_columns(engine) -> list[tuple[str, str]]:
    """The actual ADD COLUMN mutation - diff Base.metadata against what's
    actually in the table (via _diff_missing_columns) and ALTER TABLE
    whatever's missing. Only safe for nullable columns with no server-side
    default logic, which is all this project has ever added post-launch.
    Dialect-agnostic (Pilot Readiness PR-2 pre-merge architecture check,
    "Database Schema Deployment Safety") - shared by migrate_schema() (the
    explicit, operator-invoked production command) and init_db()'s SQLite
    branch (still automatic there - see init_db()'s own docstring for why
    that split exists). Transactional (engine.begin()): a failure partway
    through rolls back atomically on both SQLite and PostgreSQL, rather
    than partially applying - "fail loudly rather than partially
    corrupt". Returns the list of (table_name, column_name) added."""
    _missing_tables, missing_columns = _diff_missing_columns(engine)
    if not missing_columns:
        return []
    with engine.begin() as conn:
        for table_name, column_name in missing_columns:
            column = Base.metadata.tables[table_name].columns[column_name]
            col_type = column.type.compile(dialect=engine.dialect)
            conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {col_type}'))
            print(f"[migration] added column {table_name}.{column_name}")
    return missing_columns


def _backfill_extraction_attempt_count(engine) -> int:
    """AI Processing Reliability & Backlog Throughput pre-deployment safety
    hotfix - applications.extraction_attempt_count is declared NOT NULL
    with a Python-side ORM default=0, but _add_missing_columns' own bare
    ALTER TABLE ADD COLUMN (deliberately no NOT NULL/DEFAULT clause - see
    that function's own docstring) leaves every EXISTING row with SQL NULL,
    not 0, the instant this column is first added to a table that already
    has data - confirmed directly: a fresh production row would raise
    TypeError the first time app.pipeline.run_weekly.stage_extraction tried
    `application.extraction_attempt_count += 1` on it. That call site is
    now null-safe independently of this backfill (see stage_extraction's
    own `(application.extraction_attempt_count or 0) + 1`) - but a real 0
    is still the correct, honest value for a row that has genuinely never
    had an extraction attempt recorded, so this repairs it explicitly
    rather than leaving it permanently NULL in the data itself.

    Idempotent and safe to call on every migrate_schema() invocation, not
    just the one that adds the column: only rows where the column IS NULL
    are touched, so a database that's already fully repaired matches zero
    rows and is a no-op. Scoped to this one column only - not a general
    "backfill every nullable-with-Python-default column" mechanism, since
    no other such column in this project is ever incremented in place the
    way this one is (the actual root cause of the original bug); introducing
    a generic mechanism for a problem no other column actually has would be
    unnecessary schema/migration complexity. Uses the same raw-SQL,
    dialect-agnostic style as _add_missing_columns - no new migration
    framework."""
    with engine.begin() as conn:
        result = conn.execute(
            text('UPDATE "applications" SET "extraction_attempt_count" = 0 WHERE "extraction_attempt_count" IS NULL')
        )
        return result.rowcount if result.rowcount is not None else 0


def _backfill_documents_last_checked_at(engine) -> int:
    """Evidence Completeness Foundation (PR A), pre-merge amendment
    "Partial Initial Document Acquisition Recovery" - repairs the one
    remaining legacy-rollout gap the amendment's corrected eligibility
    logic creates.

    stage_documents' eligibility is now simply `documents_last_checked_at
    IS NULL` (see app.pipeline.run_weekly.DOCUMENT_DISCOVERY_ELIGIBLE's own
    comment for why the earlier design's extra `~Application.documents.
    any()` legacy-compatibility clause had to be removed: it would also
    have permanently blocked ROUTINE recovery of a genuinely-incomplete
    NEW acquisition the moment even one of its documents succeeded and was
    persisted - defeating this very amendment's purpose). Without some
    other legacy-rollout safeguard, every pre-existing production
    Application that already has Document rows (708 of 756 qualifying
    applications, per the PR A audit) would become eligible for document
    discovery again the first time this runs against production - exactly
    the uncontrolled full-corpus re-scrape PR A was built to avoid.

    Deliberately NOT "now" (explicitly forbidden - a legacy row was not
    just checked, and "now" would additionally imply completeness this
    migration cannot actually verify). Instead, backfills to the MAX
    downloaded_at across that application's own existing Document rows -
    a real, honest, already-true fact ("the last time document activity
    genuinely happened for this application"), not an invented value.
    This is a correct - not merely convenient - value for every row it
    touches: under the PRE-amendment system, `~Application.documents.
    any()` alone already permanently excluded any application the moment
    it had one document, complete or not, so no legacy row's document set
    is any less "final" than this backfill implies - there is no partial-
    acquisition state to recover for legacy rows specifically, only for
    NEW acquisitions made under this amended code going forward.

    Applications with ZERO documents are correctly left untouched (NULL) -
    they remain eligible for their first-ever discovery attempt, exactly
    as before this field existed.

    Idempotent: only rows where the column IS NULL are touched, so a
    database that's already fully repaired matches zero rows and is a
    no-op. Uses the same raw-SQL, dialect-agnostic style as the rest of
    this module - no new migration framework."""
    with engine.begin() as conn:
        result = conn.execute(text("""
            UPDATE "applications"
            SET "documents_last_checked_at" = (
                SELECT MAX("downloaded_at") FROM "documents" WHERE "documents"."application_id" = "applications"."id"
            )
            WHERE "documents_last_checked_at" IS NULL
              AND EXISTS (SELECT 1 FROM "documents" WHERE "documents"."application_id" = "applications"."id")
        """))
        return result.rowcount if result.rowcount is not None else 0


def migrate_schema(engine) -> tuple[list[str], list[tuple[str, str]]]:
    """The EXPLICIT, operator-invoked production migration step (Pilot
    Readiness PR-2 final pre-merge amendment, "Implement The Smallest
    Explicit Migration Mechanism") - creates any table Base.metadata
    declares that doesn't exist yet (Base.metadata.create_all, which is
    itself already idempotent - a no-op for tables that already exist),
    then ADD COLUMNs anything create_all() couldn't retroactively add to
    an EXISTING table via _add_missing_columns(). Returns
    (created_table_names, [(table_name, column_name), ...] added) for the
    caller to log/report.

    Not called automatically by init_db() on a non-SQLite engine - see
    that function's own docstring for why. Invoke explicitly via
        python -m scripts.migrate_schema
    before deploying/restarting application code that depends on new
    schema, per docs/PLATFORM_ARCHITECTURE.md's documented deployment
    order. Idempotent (safe to run any number of times, including against
    an already-fully-current database - a logged no-op)."""
    missing_tables, _missing_columns = _diff_missing_columns(engine)

    Base.metadata.create_all(engine)  # only ever creates tables that don't already exist
    for table_name in missing_tables:
        print(f"[migrate-schema] created table {table_name}")

    added_columns = _add_missing_columns(engine)  # already logs each one as it goes

    backfilled = _backfill_extraction_attempt_count(engine)
    if backfilled:
        print(f"[migrate-schema] backfilled {backfilled} existing applications.extraction_attempt_count "
              f"row(s) from NULL to 0")

    docs_backfilled = _backfill_documents_last_checked_at(engine)
    if docs_backfilled:
        print(f"[migrate-schema] backfilled {docs_backfilled} existing applications.documents_last_checked_at "
              f"row(s) from NULL to their latest document's downloaded_at")

    return missing_tables, added_columns


def init_db() -> None:
    """Ensures the engine exists and the schema is ready to use - called
    on every ordinary application/pipeline startup (app.ui.common.
    bootstrap on the first Streamlit page load per server process,
    app.pipeline.run_weekly.main, scripts.run_daily_councils.main, every
    operator script). Deliberately does NOT mutate a production schema
    (Pilot Readiness PR-2 final pre-merge amendment, "Database Migrations
    Must Not Be A Page-Load Side Effect" - Product Owner review: "Normal
    customer page loads should NOT perform schema evolution").

    SQLite (local dev / tests / CI - the default with no DATABASE_URL
    set): auto-creates any missing table/column exactly as before this
    amendment - zero production risk (there is no real "customer" on a
    developer's own throwaway local database), and keeps local/test setup
    exactly as low-friction as it has always been. All of this project's
    tests build their own engine via Base.metadata.create_all() directly
    (see tests/conftest.py) rather than through init_db() at all, so this
    branch's behaviour is untouched by anything this amendment changes.

    PostgreSQL/Supabase (production - DATABASE_URL set): read-only
    verify_schema() only, never a mutation. Raises SchemaVerificationError
    - loudly, before any query that would otherwise hit a missing
    table/column - if the schema is not already fully current, naming
    exactly what's missing and pointing at the fix (python -m
    scripts.migrate_schema). This is "application startup -> verify/use
    expected schema" from the desired principle; the actual schema
    evolution now only ever happens via migrate_schema(), invoked
    explicitly as its own deployment step - see that function's own
    docstring and docs/PLATFORM_ARCHITECTURE.md for the full deployment
    order."""
    engine = get_engine()
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(engine)
        _add_missing_columns(engine)
        _backfill_extraction_attempt_count(engine)
        _backfill_documents_last_checked_at(engine)
        return

    missing_tables, missing_columns = verify_schema(engine)
    if missing_tables or missing_columns:
        parts = []
        if missing_tables:
            parts.append(f"missing table(s): {', '.join(sorted(missing_tables))}")
        if missing_columns:
            cols = ", ".join(f"{t}.{c}" for t, c in missing_columns)
            parts.append(f"missing column(s): {cols}")
        raise SchemaVerificationError(
            "Database schema is out of date - " + "; ".join(parts) + ". "
            "Run `python -m scripts.migrate_schema` before starting this process. "
            "init_db() no longer mutates a non-SQLite schema automatically - "
            "see app.db.session.init_db's own docstring."
        )


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _SessionLocal()


def get_settings(session: Session):
    from app.db.models import Settings

    settings = session.get(Settings, 1)
    if settings is None:
        settings = Settings(id=1, credits_remaining=0)
        session.add(settings)
        session.commit()
    return settings
