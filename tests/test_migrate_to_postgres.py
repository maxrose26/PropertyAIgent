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
    not_null_foreign_keys_to_other_tables,
    null_out_orphaned_nullable_fks,
    nullable_foreign_keys_to_other_tables,
    prepare_rows,
    require_postgres_database_url,
    resolve_missing_defaults,
    self_referential_columns,
    sequence_reset_statement,
    split_dangling_rows,
    to_utc_aware,
)


@pytest.fixture(autouse=True)
def _isolate_from_real_env_file(monkeypatch):
    # require_postgres_database_url() calls load_dotenv() itself - without
    # stubbing it out, a real .env (which, once Stage 2 configures a real
    # Supabase connection, legitimately has its own DATABASE_URL) would get
    # re-read and silently refill a value a test had just deleted via
    # monkeypatch.delenv, since load_dotenv() only fills in variables that
    # are currently unset. These tests must be isolated from whatever
    # happens to be in any developer's real .env file.
    monkeypatch.setattr("scripts.migrate_to_postgres.load_dotenv", lambda *a, **k: None)


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
    # Explicitly given values survive untouched - resolve_missing_defaults
    # (tested separately below) may still fill in other NOT NULL columns
    # this minimal row omitted entirely, which is correct, not a leak.
    assert insert_rows[0]["id"] == 1
    assert insert_rows[0]["council_code"] == "bury"
    assert deferred == []


def test_prepare_rows_fills_missing_not_null_default_for_old_rows():
    # sites.excluded is NOT NULL with default=False - a row from before
    # that column existed (added via _add_missing_columns's ALTER TABLE,
    # which never backfills or enforces NOT NULL on SQLite) has it missing
    # entirely, exactly like the real data this was written against.
    table = Base.metadata.tables["sites"]
    rows = [{"id": 1, "council_code": "bury"}]
    insert_rows, _ = prepare_rows(table, rows, [])
    assert insert_rows[0]["excluded"] is False


def test_prepare_rows_leaves_explicit_false_alone():
    table = Base.metadata.tables["sites"]
    rows = [{"id": 1, "council_code": "bury", "excluded": False}]
    insert_rows, _ = prepare_rows(table, rows, [])
    assert insert_rows[0]["excluded"] is False


def test_prepare_rows_never_overwrites_a_genuinely_provided_value():
    table = Base.metadata.tables["councils"]
    rows = [{"code": "bury", "monitoring_enabled": True}]
    insert_rows, _ = prepare_rows(table, rows, [])
    assert insert_rows[0]["monitoring_enabled"] is True


# --- resolve_missing_defaults directly (real data confirmed this gap:    --
# councils.created_at/updated_at/monitoring_enabled and sites.excluded)   --

def test_resolve_missing_defaults_applies_scalar_default():
    table = Base.metadata.tables["councils"]
    row = {"code": "bury", "monitoring_enabled": None}
    resolved = resolve_missing_defaults(table, row)
    assert resolved["monitoring_enabled"] is False


def test_resolve_missing_defaults_applies_callable_default():
    table = Base.metadata.tables["councils"]
    row = {"code": "bury", "created_at": None}
    resolved = resolve_missing_defaults(table, row)
    assert isinstance(resolved["created_at"], dt.datetime)
    assert resolved["created_at"].tzinfo is not None


def test_resolve_missing_defaults_leaves_nullable_columns_alone():
    # councils.website is nullable with no default - a genuine NULL here
    # must stay NULL, never invented.
    table = Base.metadata.tables["councils"]
    row = {"code": "bury", "website": None}
    resolved = resolve_missing_defaults(table, row)
    assert resolved["website"] is None


def test_resolve_missing_defaults_leaves_present_values_untouched():
    table = Base.metadata.tables["councils"]
    row = {"code": "bury", "monitoring_enabled": True}
    resolved = resolve_missing_defaults(table, row)
    assert resolved["monitoring_enabled"] is True


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


# --- Dangling NOT NULL foreign keys (SQLite doesn't enforce FK           --
# constraints, confirmed against the real data: 36 `documents` rows       --
# reference a deleted `applications` row) - split_dangling_rows/          --
# not_null_foreign_keys_to_other_tables handle this without crashing the  --
# migration or fabricating a parent row.                                  --

def test_not_null_foreign_keys_to_other_tables_finds_documents_application_id():
    table = Base.metadata.tables["documents"]
    result = not_null_foreign_keys_to_other_tables(table)
    assert ("application_id", Base.metadata.tables["applications"]) in result


def test_not_null_foreign_keys_to_other_tables_excludes_self_referential():
    # monitored_reports.superseded_by_id is NOT nullable=False (it's
    # nullable), so it wouldn't qualify anyway, but the real point here is
    # nothing on this table should show up as a "NOT NULL FK to ANOTHER
    # table" pointing back at itself.
    table = Base.metadata.tables["monitored_reports"]
    result = not_null_foreign_keys_to_other_tables(table)
    assert all(target_table is not table for _, target_table in result)


def test_not_null_foreign_keys_to_other_tables_empty_for_table_without_one():
    table = Base.metadata.tables["councils"]
    assert not_null_foreign_keys_to_other_tables(table) == []


def test_nullable_foreign_keys_to_other_tables_finds_suggested_site_id():
    table = Base.metadata.tables["applications"]
    result = nullable_foreign_keys_to_other_tables(table)
    assert ("suggested_site_id", Base.metadata.tables["sites"]) in result
    # site_id is also a nullable FK to sites - both must be found, not just one.
    assert ("site_id", Base.metadata.tables["sites"]) in result


def test_null_out_orphaned_nullable_fks_nulls_missing_reference():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    sites = Base.metadata.tables["sites"]
    councils = Base.metadata.tables["councils"]

    with engine.begin() as conn:
        conn.execute(councils.insert(), [{
            "code": "bury", "name": "Bury", "base_url": "https://x.invalid",
            "date_field_mode": "received", "doc_system": "idox",
        }])
        conn.execute(sites.insert(), [{
            "id": 1, "council_code": "bury",
            "canonical_address": "1 x street", "display_address": "1 X Street",
        }])

    applications = Base.metadata.tables["applications"]
    rows = [
        {"id": 10, "council_code": "bury", "reference": "A1", "suggested_site_id": 1},   # real site - kept
        {"id": 11, "council_code": "bury", "reference": "A2", "suggested_site_id": 999},  # deleted site - nulled
    ]
    with engine.connect() as conn:
        result, nulled_counts = null_out_orphaned_nullable_fks(conn, applications, rows)

    assert result[0]["suggested_site_id"] == 1
    assert result[1]["suggested_site_id"] is None
    assert nulled_counts == {"suggested_site_id": 1}


def test_null_out_orphaned_nullable_fks_leaves_genuine_null_alone():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    applications = Base.metadata.tables["applications"]
    rows = [{"id": 10, "council_code": "bury", "reference": "A1", "suggested_site_id": None}]
    with engine.connect() as conn:
        result, nulled_counts = null_out_orphaned_nullable_fks(conn, applications, rows)
    assert result[0]["suggested_site_id"] is None
    assert nulled_counts == {}


def test_copy_table_nulls_orphaned_nullable_fk_instead_of_crashing(tmp_path, _no_sequence_reset):
    source_engine = create_engine(f"sqlite:///{tmp_path / 'source.db'}", future=True)
    target_engine = create_engine(f"sqlite:///{tmp_path / 'target.db'}", future=True)
    Base.metadata.create_all(source_engine)
    Base.metadata.create_all(target_engine)

    councils = Base.metadata.tables["councils"]
    sites = Base.metadata.tables["sites"]
    applications = Base.metadata.tables["applications"]
    with source_engine.begin() as conn:
        conn.execute(councils.insert(), [{
            "code": "bury", "name": "Bury", "base_url": "https://x.invalid",
            "date_field_mode": "received", "doc_system": "idox",
        }])
        conn.execute(sites.insert(), [{
            "id": 1, "council_code": "bury",
            "canonical_address": "1 x street", "display_address": "1 X Street",
        }])
        conn.execute(applications.insert(), [
            {"id": 10, "council_code": "bury", "reference": "A1", "suggested_site_id": 999},
        ])

    with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
        for table in (councils, sites, applications):
            copy_table(source_conn, target_conn, table, batch_size=500, dry_run=False)

    with target_engine.connect() as tc:
        row = tc.execute(select(applications)).first()
    assert row.id == 10  # row was kept, not excluded
    assert row.suggested_site_id is None  # dangling reference nulled, not left violating the FK


def test_split_dangling_rows_excludes_row_with_missing_required_parent():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    applications = Base.metadata.tables["applications"]
    documents = Base.metadata.tables["documents"]
    councils = Base.metadata.tables["councils"]

    with engine.begin() as conn:
        conn.execute(councils.insert(), [{
            "code": "bury", "name": "Bury", "base_url": "https://x.invalid",
            "date_field_mode": "received", "doc_system": "idox",
        }])
        conn.execute(applications.insert(), [{"id": 1, "council_code": "bury", "reference": "A1"}])

    rows = [
        {"id": 100, "application_id": 1, "doc_type": "plan", "extracted": False},
        {"id": 101, "application_id": 999, "doc_type": "plan", "extracted": False},  # 999 doesn't exist
    ]
    with engine.connect() as conn:
        keepable, dangling = split_dangling_rows(conn, documents, rows)

    assert [r["id"] for r in keepable] == [100]
    assert [r["id"] for r in dangling["application_id"]] == [101]


def test_split_dangling_rows_no_fk_columns_returns_everything_unchanged():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    councils = Base.metadata.tables["councils"]
    rows = [{"code": "bury", "name": "Bury"}]
    with engine.connect() as conn:
        keepable, dangling = split_dangling_rows(conn, councils, rows)
    assert keepable == rows
    assert dangling == {}


def test_copy_table_skips_dangling_row_and_keeps_the_valid_one(tmp_path, _no_sequence_reset):
    source_engine = create_engine(f"sqlite:///{tmp_path / 'source.db'}", future=True)
    target_engine = create_engine(f"sqlite:///{tmp_path / 'target.db'}", future=True)
    Base.metadata.create_all(source_engine)
    Base.metadata.create_all(target_engine)

    councils = Base.metadata.tables["councils"]
    applications = Base.metadata.tables["applications"]
    documents = Base.metadata.tables["documents"]
    with source_engine.begin() as conn:
        conn.execute(councils.insert(), [{
            "code": "bury", "name": "Bury", "base_url": "https://x.invalid",
            "date_field_mode": "received", "doc_system": "idox",
        }])
        conn.execute(applications.insert(), [{"id": 1, "council_code": "bury", "reference": "A1"}])
        conn.execute(documents.insert(), [
            {"id": 100, "application_id": 1, "doc_type": "plan", "extracted": False},
            {"id": 101, "application_id": 999, "doc_type": "plan", "extracted": False},
        ])

    with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
        for table in (councils, applications, documents):
            copy_table(source_conn, target_conn, table, batch_size=500, dry_run=False)

    with target_engine.connect() as tc:
        ids = [r.id for r in tc.execute(select(documents))]
    assert ids == [100]  # the dangling row (101) was excluded, not crashed on


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
