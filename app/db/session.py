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

    SQLite-only: this exists purely to evolve an existing on-disk SQLite
    file across app versions, one column at a time, with no real migration
    tool in place. A PostgreSQL/Supabase target is always created fresh via
    Base.metadata.create_all (see init_db, just above where this is called)
    against an empty database, which already includes every column the
    current models define - there is nothing to diff there. Once the
    Postgres schema needs to evolve after its initial creation, it should
    get a real migration tool (e.g. Alembic) rather than this ad hoc
    ALTER TABLE approach, which is why this returns immediately for any
    non-SQLite dialect rather than attempting the equivalent there."""
    if engine.dialect.name != "sqlite":
        return

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
