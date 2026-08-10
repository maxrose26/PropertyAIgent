"""Tests for app.db.session's DATABASE_URL-driven engine selection - the
Supabase migration's Stage 1 (see scripts/migrate_to_postgres.py for the
data-copy half, tested separately in tests/test_migrate_to_postgres.py).

Every test here only ever constructs SQLAlchemy Engine objects, never
connects one - engine creation is lazy (no network/socket activity), so a
PostgreSQL-flavoured DATABASE_URL can be exercised without a real Postgres
server anywhere nearby, and without touching the real Supabase database or
the real on-disk data/deal_finder.db.

Each test resets app.db.session's module-level engine/session-factory cache
via the autouse fixture below, so this file's monkeypatched DATABASE_URL
values never leak into (or get overwritten by) another test module's own
use of get_engine()/get_session(). The fixture also stubs out get_engine()'s
own load_dotenv() call - without that, a developer's real .env (which, once
Stage 2 configures a real Supabase connection, legitimately has its own
DATABASE_URL) would get re-read on every call and silently refill a value a
test had just deleted via monkeypatch.delenv, since load_dotenv() only ever
fills in variables that are currently unset. Tests must exercise
get_engine()'s own logic in isolation, independent of whatever happens to
be in any developer's real .env file at the time.
"""
from __future__ import annotations

import pytest

import app.db.session as db_session


@pytest.fixture(autouse=True)
def _reset_engine_cache(monkeypatch):
    monkeypatch.setattr(db_session, "_engine", None)
    monkeypatch.setattr(db_session, "_SessionLocal", None)
    monkeypatch.setattr(db_session, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    yield
    monkeypatch.setattr(db_session, "_engine", None)
    monkeypatch.setattr(db_session, "_SessionLocal", None)


# --- Requirement 1: SQLite remains the default when DATABASE_URL is unset --

def test_default_engine_is_sqlite_when_database_url_unset(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    engine = db_session.get_engine()
    assert engine.dialect.name == "sqlite"
    assert engine.driver == "pysqlite"
    assert str(db_session.DB_PATH.name) in str(engine.url)


def test_default_engine_creates_data_directory(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_session.get_engine()
    assert db_session.DATA_DIR.is_dir()


# --- Requirement 2/3: Postgres + psycopg 3 used when DATABASE_URL is set ---

def test_database_url_selects_postgres_engine_with_psycopg3(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/postgres")
    engine = db_session.get_engine()
    assert engine.dialect.name == "postgresql"
    assert engine.driver == "psycopg"


def test_database_url_legacy_postgres_scheme_also_normalised(monkeypatch):
    # Some tools (and Supabase's own older docs) still emit postgres:// -
    # must resolve to the same psycopg 3 driver as postgresql://.
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@localhost:5432/postgres")
    engine = db_session.get_engine()
    assert engine.dialect.name == "postgresql"
    assert engine.driver == "psycopg"


def test_database_url_with_explicit_driver_left_untouched(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/postgres")
    engine = db_session.get_engine()
    assert engine.dialect.name == "postgresql"
    assert engine.driver == "psycopg"


def test_database_url_never_leaks_password_into_str(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:supersecret@localhost:5432/postgres")
    engine = db_session.get_engine()
    assert "supersecret" not in engine.url.render_as_string(hide_password=True)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("postgres://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),
        ("postgresql://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),
        ("postgresql+psycopg://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),
        ("postgresql+psycopg2://u:p@h:5432/d", "postgresql+psycopg2://u:p@h:5432/d"),
        ("sqlite:///some.db", "sqlite:///some.db"),
    ],
)
def test_normalize_database_url(raw, expected):
    assert db_session._normalize_database_url(raw) == expected


# --- Requirement 4 (superseded): schema-upgrade logic now runs on every
# dialect, not just SQLite.
#
# Originally this test asserted the opposite - that _add_missing_columns
# returned immediately, untouched, for any non-SQLite engine. That guard
# was removed during the Pilot Readiness PR-2 pre-merge architecture check
# ("Database Schema Deployment Safety"): it meant a brand-new column added
# to an existing model (like LocalPlanSite.confirmed_by in this same
# sprint) would never be added to the real production PostgreSQL database
# by init_db() alone, creating a deployment-ordering risk. The underlying
# diff-and-ALTER logic was already dialect-agnostic; only the early-return
# was PostgreSQL-specific. See tests/test_pr2_premerge_ai_cost_and_migration_safety.py
# for the tests covering the corrected behaviour (dialect-compiled DDL
# validity, idempotency, and a full SQLite functional add-column proof).


def test_add_missing_columns_still_runs_for_sqlite():
    from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine

    engine = create_engine("sqlite:///:memory:", future=True)
    metadata = MetaData()
    # A table matching one of Base's own (same name, missing one column) so
    # _add_missing_columns has something real to diff against, using the
    # real Base.metadata rather than a throwaway table - Settings is the
    # smallest model in app.db.models.
    Table("settings", metadata, Column("id", Integer, primary_key=True))
    metadata.create_all(engine)

    db_session._add_missing_columns(engine)

    from sqlalchemy import inspect

    columns = {c["name"] for c in inspect(engine).get_columns("settings")}
    assert "credits_remaining" in columns  # added by the diff, matching app.db.models.Settings
