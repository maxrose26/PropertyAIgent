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


def _add_missing_columns(engine) -> None:
    """No Alembic for this solo project - just diff each model's columns
    against what's actually in the table and ADD COLUMN anything new. Only
    safe for nullable columns with no server-side default logic, which is
    all we've ever added post-launch.

    Runs for every dialect, including PostgreSQL/Supabase (Pilot Readiness
    PR-2 pre-merge architecture check, "Database Schema Deployment
    Safety") - PREVIOUSLY SQLite-only, on the documented assumption that
    "a PostgreSQL/Supabase target is always created fresh via
    Base.metadata.create_all... against an empty database, which already
    includes every column the current models define." PR-2 itself proved
    that assumption false: it was the first time this codebase added a
    column to an EXISTING, already-populated production Postgres database
    (LocalPlanSite.confirmed_by/confirmed_at/match_review_note), and doing
    so required a one-off manual script (scripts/
    add_allocation_match_review_columns.py) run as a separate, easy-to-
    forget step before the dependent code could safely deploy - exactly
    the kind of deployment-ordering risk this function generalising to
    cover Postgres now eliminates. The diffing logic below (inspector.
    get_columns, dialect-compiled column type) was already fully dialect-
    agnostic; the ONLY change is removing the early-return that used to
    skip every non-SQLite engine. Postgres DDL is transactional (unlike
    MySQL), so wrapping every ALTER TABLE in the one engine.begin() block
    below still fails loudly and rolls back atomically rather than
    partially applying a migration, on Postgres exactly as on SQLite. A
    brand-new TABLE (e.g. ScrapeRun) is unaffected by this change either
    way - create_all() above already creates those, on both dialects,
    before this function ever runs."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # brand-new table - create_all already handled it
            existing_columns = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue
                col_type = column.type.compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))
                print(f"[migration] added column {table.name}.{column.name}")


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)


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
