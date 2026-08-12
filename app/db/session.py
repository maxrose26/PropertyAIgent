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


def _backfill_documents_legacy_unverified(engine) -> int:
    """Evidence Completeness Foundation (PR A), SECOND pre-merge amendment
    "Legacy Document-State Truthfulness" - the sole rollout-safety
    mechanism for pre-existing Application rows, replacing an earlier
    version of this function that backfilled documents_last_checked_at
    itself to MAX(Document.downloaded_at). That was rejected in Product
    Owner review: a Document row only ever proves "one document was
    downloaded once", never "a complete intended acquisition pass
    finished" (documents_last_checked_at's own approved definition, see
    that field's comment on Application) - some legacy applications may
    have had other intended documents that failed or were never even
    discovered, with no reliable record either way. Stamping ANY value
    into documents_last_checked_at for those rows would misrepresent
    unknown completeness as a genuine completed check - recreating the
    old "has any document = complete" bug via migration instead of code.

    So this backfill NEVER touches documents_last_checked_at at all - it
    stays NULL for every legacy row, truthfully. Instead it sets the
    narrowly-scoped documents_legacy_unverified marker (see that field's
    own comment on Application) to True for every pre-existing Application
    that already has >=1 Document row, and to False for every pre-existing
    Application with zero Document rows - both explicitly, so no row is
    left in an ambiguous NULL state for this column either.
    DOCUMENT_DISCOVERY_ELIGIBLE (app.pipeline.run_weekly) excludes any row
    where this marker is True, which is what actually prevents the ~708
    pre-existing documented applications from being bulk re-queued for
    document discovery the first time this runs against production - NOT
    any inferred value in documents_last_checked_at itself. A zero-document
    legacy row is marked False (not legacy-unverified) and so remains
    eligible for its first-ever discovery attempt, exactly as before PR A
    existed.

    This marker is only ever cleared later by a genuine, successful,
    explicitly-targeted discover_and_store_documents_for_application call
    (see that function's own comment) - never re-set to True afterwards,
    and never touched again by this backfill (idempotent: only rows where
    the column IS NULL are affected, so a database that's already been
    marked matches zero rows on a second run - including any row a
    targeted recheck has since moved to False, since False is not NULL).
    Uses the same raw-SQL, dialect-agnostic style as the rest of this
    module - no new migration framework, and no new workflow-state
    machine: a single boolean, scoped to exactly this one rollout-safety
    question."""
    with engine.begin() as conn:
        result = conn.execute(text("""
            UPDATE "applications"
            SET "documents_legacy_unverified" = EXISTS (
                SELECT 1 FROM "documents" WHERE "documents"."application_id" = "applications"."id"
            )
            WHERE "documents_legacy_unverified" IS NULL
        """))
        return result.rowcount if result.rowcount is not None else 0


def _backfill_evidence_refresh_required(engine) -> int:
    """PR B1 ("Material Application-State Detection + Persisted Refresh
    Signal") - same NOT-NULL-with-Python-default gap _backfill_
    extraction_attempt_count already exists to repair (_add_missing_
    columns' own bare ALTER TABLE ADD COLUMN leaves every EXISTING row
    with SQL NULL, not the model's Python-side default=False, the moment
    this column is first added to a table that already has data).

    Deliberately sets False, never True - a legacy row (there are
    approximately 1,387 pre-existing Application rows in production)
    genuinely has no material-change signal to report: this migration
    only ever ADDS the column, it never runs
    detect_material_application_change against anything, so there is no
    "old vs new" comparison for any legacy row to have produced a
    change from in the first place. Explicitly does NOT touch
    evidence_refresh_reason/evidence_refresh_trigger/
    evidence_refresh_requested_at at all - those stay NULL for every
    legacy row, truthfully (no reason to fabricate for a signal that was
    never set), matching the same "additive, never invents a value"
    principle _backfill_documents_legacy_unverified already established
    for documents_last_checked_at.

    Idempotent: only rows where the column IS NULL are touched, so a
    database that's already fully repaired matches zero rows and is a
    no-op - identical convention to every other backfill in this
    module."""
    with engine.begin() as conn:
        result = conn.execute(
            text('UPDATE "applications" SET "evidence_refresh_required" = FALSE WHERE "evidence_refresh_required" IS NULL')
        )
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

    legacy_marked = _backfill_documents_legacy_unverified(engine)
    if legacy_marked:
        print(f"[migrate-schema] marked {legacy_marked} existing applications.documents_legacy_unverified "
              f"row(s) True (has documents) or False (no documents) - documents_last_checked_at itself "
              f"is never inferred and remains NULL for every legacy row")

    refresh_backfilled = _backfill_evidence_refresh_required(engine)
    if refresh_backfilled:
        print(f"[migrate-schema] backfilled {refresh_backfilled} existing applications.evidence_refresh_required "
              f"row(s) from NULL to False - no historical row is marked as having a material change")

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
        _backfill_documents_legacy_unverified(engine)
        _backfill_evidence_refresh_required(engine)
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
