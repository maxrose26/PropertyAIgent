"""Tests for the pure, non-network-dependent parts of
scripts/migrate_to_postgres.py: self-referential foreign key detection,
per-value UTC normalisation, primary-key-preserving row splitting, the
sequence-reset SQL shape, and the DATABASE_URL guard.

Actually copying rows into a live PostgreSQL/Supabase database is
deliberately NOT exercised here - this task must not connect to or modify
the real Supabase database. See README.md's "Database configuration"
section for how to validate a real run against your own (non-production)
Postgres/Supabase instance, including --dry-run, which is the one code path
in the script that never opens a connection to the target at all.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, func, select

from app.db.models import Base
from scripts.migrate_to_postgres import (
    copy_table,
    get_source_engine,
    prepare_rows,
    require_postgres_database_url,
    self_referential_columns,
    sequence_reset_statement,
    to_utc_aware,
)


# --- Self-referential column detection (module docstring's two-pass fix) ---

def test_self_referential_column_found_on_monitored_reports():
    table = Base.metadata.tables["monitored_reports"]
    assert self_referential_columns(table) == ["superseded_by_id"]


def test_self_referential_column_found_on_visual_evidence():
    table = Base.metadata.tables["visual_evidence"]
    assert self_referential_columns(table) == ["superseded_by_id"]


def test_self_referential_columns_empty_for_table_without_one():
    table = Base.metadata.tables["sites"]
    assert self_referential_columns(table) == []


# --- UTC normalisation (SQLite round-trips DateTime(timezone=True) naive) --

def test_to_utc_aware_attaches_utc_to_naive_datetime():
    naive = dt.datetime(2026, 1, 1, 12, 0, 0)
    result = to_utc_aware(naive)
    assert result.tzinfo == dt.timezone.utc
    assert result.replace(tzinfo=None) == naive


def test_to_utc_aware_leaves_aware_datetime_unchanged():
    aware = dt.datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt.timezone.utc)
    assert to_utc_aware(aware) is aware


@pytest.mark.parametrize("value", ["hello", None, 42, 3.14, True])
def test_to_utc_aware_leaves_non_datetime_values_unchanged(value):
    assert to_utc_aware(value) == value


# --- Row splitting: self-ref columns nulled + deferred, PKs preserved -----

def test_prepare_rows_nulls_self_referential_column_and_defers_it():
    table = Base.metadata.tables["monitored_reports"]
    rows = [
        {"id": 1, "superseded_by_id": 2, "council_code": "bury"},
        {"id": 2, "superseded_by_id": None, "council_code": "bury"},
    ]
    insert_rows, deferred = prepare_rows(table, rows, ["superseded_by_id"])

    assert insert_rows[0]["superseded_by_id"] is None
    assert insert_rows[1]["superseded_by_id"] is None
    # Original row values must otherwise survive untouched.
    assert insert_rows[0]["id"] == 1
    assert insert_rows[0]["council_code"] == "bury"
    assert deferred == [{"superseded_by_id": 2, "id": 1}]


def test_prepare_rows_no_deferred_updates_when_nothing_self_referential():
    table = Base.metadata.tables["sites"]
    rows = [{"id": 1, "council_code": "bury"}]
    insert_rows, deferred = prepare_rows(table, rows, [])
    assert insert_rows == rows
    assert deferred == []


def test_prepare_rows_utc_normalises_naive_datetime_columns():
    table = Base.metadata.tables["sites"]
    naive = dt.datetime(2026, 1, 1)
    insert_rows, _ = prepare_rows(table, [{"id": 1, "first_seen_at": naive}], [])
    assert insert_rows[0]["first_seen_at"].tzinfo == dt.timezone.utc
    assert insert_rows[0]["first_seen_at"].replace(tzinfo=None) == naive


# --- Sequence reset (only for single-column integer primary keys) ---------

def test_sequence_reset_statement_for_integer_primary_key():
    table = Base.metadata.tables["sites"]
    sql = sequence_reset_statement(table)
    assert sql is not None
    assert "setval" in sql
    assert "sites" in sql
    assert '"id"' in sql


def test_sequence_reset_statement_none_for_string_primary_key():
    # councils.code is a String primary key, never auto-incrementing.
    table = Base.metadata.tables["councils"]
    assert sequence_reset_statement(table) is None


# --- DATABASE_URL guard: fail fast rather than migrate SQLite -> SQLite ---

def test_require_postgres_database_url_fails_fast_when_unset(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit):
        require_postgres_database_url()


def test_require_postgres_database_url_fails_fast_for_non_postgres_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///something.db")
    with pytest.raises(SystemExit):
        require_postgres_database_url()


def test_require_postgres_database_url_normalises_bare_postgres_scheme(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@localhost:5432/postgres")
    url = require_postgres_database_url()
    assert url.startswith("postgresql+psycopg://")


def test_require_postgres_database_url_accepts_postgresql_scheme(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/postgres")
    url = require_postgres_database_url()
    assert url.startswith("postgresql+psycopg://")


# --- Source engine: strictly read-only, and requires the file to exist ----

def test_get_source_engine_uses_readonly_sqlite_uri(monkeypatch, tmp_path):
    fake_db = tmp_path / "deal_finder.db"
    fake_db.write_bytes(b"")  # a valid empty file is enough to satisfy the existence check
    monkeypatch.setattr("scripts.migrate_to_postgres.DB_PATH", fake_db)

    engine = get_source_engine()

    assert "mode=ro" in str(engine.url)


def test_get_source_engine_fails_fast_when_no_sqlite_db_exists(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.migrate_to_postgres.DB_PATH", tmp_path / "does_not_exist.db")
    with pytest.raises(SystemExit):
        get_source_engine()


# --- End-to-end exercise of copy_table's real row-copying/dedup/self-ref --
#
# Uses a second SQLite database as a stand-in "target" rather than real
# Postgres (this task must not connect to the real Supabase database) -
# sequence_reset_statement's SQL is Postgres-only (pg_get_serial_sequence
# doesn't exist in SQLite), so it's monkeypatched to a no-op for this test
# only; everything else in copy_table runs for real, including
# sqlalchemy.dialects.postgresql.insert(...).on_conflict_do_nothing(),
# which SQLAlchemy compiles correctly against SQLite's own native ON
# CONFLICT support too - confirmed empirically before writing this test.

@pytest.fixture()
def _no_sequence_reset(monkeypatch):
    monkeypatch.setattr("scripts.migrate_to_postgres.sequence_reset_statement", lambda table: None)


def test_copy_table_preserves_pks_and_backfills_self_reference(tmp_path, _no_sequence_reset):
    source_engine = create_engine(f"sqlite:///{tmp_path / 'source.db'}", future=True)
    target_engine = create_engine(f"sqlite:///{tmp_path / 'target.db'}", future=True)
    Base.metadata.create_all(source_engine)
    Base.metadata.create_all(target_engine)

    councils = Base.metadata.tables["councils"]
    reports = Base.metadata.tables["monitored_reports"]
    with source_engine.begin() as conn:
        conn.execute(councils.insert(), [
            {"code": "bury", "name": "Bury", "base_url": "https://x.invalid",
             "date_field_mode": "received", "doc_system": "idox"},
        ])
        conn.execute(reports.insert(), [
            {"id": 1, "council_code": "bury", "url": "https://x.invalid/1", "superseded_by_id": 2},
            {"id": 2, "council_code": "bury", "url": "https://x.invalid/2", "superseded_by_id": None},
        ])

    with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
        for table in (councils, reports):
            copy_table(source_conn, target_conn, table, batch_size=500, dry_run=False)

    with target_engine.connect() as tc:
        rows = {r.id: r.superseded_by_id for r in tc.execute(select(reports))}
    assert rows == {1: 2, 2: None}  # self-referential value correctly backfilled, PKs preserved


def test_copy_table_rerun_is_safe_and_does_not_duplicate(tmp_path, _no_sequence_reset):
    source_engine = create_engine(f"sqlite:///{tmp_path / 'source.db'}", future=True)
    target_engine = create_engine(f"sqlite:///{tmp_path / 'target.db'}", future=True)
    Base.metadata.create_all(source_engine)
    Base.metadata.create_all(target_engine)

    councils = Base.metadata.tables["councils"]
    with source_engine.begin() as conn:
        conn.execute(councils.insert(), [
            {"code": "bury", "name": "Bury", "base_url": "https://x.invalid",
             "date_field_mode": "received", "doc_system": "idox"},
        ])

    for _ in range(2):  # simulate a rerun after an interrupted/partial migration
        with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
            copy_table(source_conn, target_conn, councils, batch_size=500, dry_run=False)

    with target_engine.connect() as tc:
        count = tc.execute(select(func.count()).select_from(councils)).scalar()
    assert count == 1  # still just one row, not two - the rerun was safe


def test_copy_table_dry_run_never_touches_target(tmp_path, _no_sequence_reset):
    source_engine = create_engine(f"sqlite:///{tmp_path / 'source.db'}", future=True)
    Base.metadata.create_all(source_engine)
    councils = Base.metadata.tables["councils"]
    with source_engine.begin() as conn:
        conn.execute(councils.insert(), [
            {"code": "bury", "name": "Bury", "base_url": "https://x.invalid",
             "date_field_mode": "received", "doc_system": "idox"},
        ])

    with source_engine.connect() as source_conn:
        count = copy_table(source_conn, None, councils, batch_size=500, dry_run=True)
    assert count == 1  # reports what it would have copied without a target connection
