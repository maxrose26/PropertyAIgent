"""AI Processing Reliability & Backlog Throughput - pre-deployment safety
hotfix - focused tests for the two issues found in merge review before
production migration/deployment:

A. Application.extraction_attempt_count is left SQL NULL (not the ORM's
   own default=0) for every pre-existing production row the moment the
   additive ALTER TABLE ADD COLUMN mechanism (app.db.session.
   _add_missing_columns) first adds it - confirmed directly: a bare
   `application.extraction_attempt_count += 1` on such a row raises
   TypeError. Fixed two ways (defence in depth): the increment itself is
   now null-safe (app.pipeline.run_weekly.stage_extraction), AND the
   migration mechanism now explicitly backfills any lingering NULL to 0
   (app.db.session._backfill_extraction_attempt_count).

B. process_intelligence_backlog commits IntelligenceRun(status="running")
   before doing any real work; an uncaught catastrophic exception anywhere
   after that point (but before the run's own normal finalisation) used to
   leave the row stuck at status="running" forever - neither a truthful
   SUCCESS/PARTIAL nor a FAILED. Fixed with a run-level guard that
   best-effort persists a terminal FAILED state and re-raises the original
   exception unchanged.

Every other test in this suite builds its schema via Base.metadata.
create_all() on the FINAL model shape (see tests/conftest.py) - which is
exactly why issue A was invisible to the original test suite: that never
exercises "ALTER TABLE onto a table that already has data". The migration
tests below deliberately do NOT use that fixture for the same reason.
"""
from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import pytest
from openai import OpenAIError
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

from app.config import CouncilConfig
from app.db.models import Application, Base, Document, IntelligenceRun
from app.db.session import _backfill_extraction_attempt_count, migrate_schema
from app.pipeline import run_weekly as run_weekly_module
from app.pipeline.run_weekly import stage_extraction


def _council_config(code: str) -> CouncilConfig:
    return CouncilConfig(
        code=code, name=code, base_url="https://example.invalid",
        date_field_mode="received", doc_system="idox", anite_base_url=None,
        unit_threshold=10, region=None, country=None,
    )


COUNCILS = {"testcouncil": _council_config("testcouncil")}


def _app_with_document(session, *, reference: str, council_code: str = "testcouncil") -> Application:
    application = Application(council_code=council_code, reference=reference)
    session.add(application)
    session.commit()
    session.add(Document(
        application_id=application.id, doc_type="planning_statement",
        text_extracted=True, extracted_text="Some planning statement text.",
    ))
    session.commit()
    return application


def _build_old_applications_table(engine) -> MetaData:
    """Minimal pre-hotfix `applications` table (same convention as this
    project's sibling test, test_add_missing_columns_adds_a_genuinely_
    missing_column_on_sqlite in test_pr2_premerge_ai_cost_and_migration_
    safety.py) - just enough columns to insert and identify a real
    existing row, deliberately WITHOUT extraction_last_outcome/
    extraction_last_attempted_at/extraction_attempt_count."""
    old_metadata = MetaData()
    Table(
        "applications", old_metadata,
        Column("id", Integer, primary_key=True),
        Column("council_code", String(20)),
        Column("reference", String(100)),
    )
    old_metadata.create_all(engine)
    return old_metadata


# --- A: real old-schema -> migration -> existing row repaired --------------


def test_migration_backfills_extraction_attempt_count_on_real_old_schema_upgrade():
    """Reproduces the REAL production upgrade path end to end: 1) old
    schema without the column, 2) an existing row, 3) the real
    migrate_schema(), 4) the column exists, 5) the existing row reads 0
    not NULL, 6) loaded through the ORM, 7) the real increment path is
    exercised, 8) it becomes 1 without TypeError."""
    engine = create_engine("sqlite:///:memory:", future=True)
    old_metadata = _build_old_applications_table(engine)

    with engine.begin() as conn:
        conn.execute(
            Table("applications", old_metadata).insert(),
            [{"id": 1, "council_code": "testcouncil", "reference": "APP/OLD/1"}],
        )

    created_tables, added_columns = migrate_schema(engine)
    assert ("applications", "extraction_attempt_count") in added_columns

    # 4/5: column exists, existing row is 0, not NULL.
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT extraction_attempt_count FROM applications WHERE reference = 'APP/OLD/1'"
        )).fetchone()
    assert row.extraction_attempt_count == 0

    # 6/7/8: load through the ORM, exercise the REAL increment path used by
    # stage_extraction, confirm no TypeError and the value becomes 1.
    session_local = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    session = session_local()
    application = session.execute(select(Application).where(Application.reference == "APP/OLD/1")).scalar_one()
    assert application.extraction_attempt_count == 0
    application.extraction_attempt_count = (application.extraction_attempt_count or 0) + 1
    session.commit()
    assert application.extraction_attempt_count == 1
    session.close()


def test_migration_is_idempotent_second_run_does_not_corrupt_backfilled_value():
    engine = create_engine("sqlite:///:memory:", future=True)
    old_metadata = _build_old_applications_table(engine)
    with engine.begin() as conn:
        conn.execute(
            Table("applications", old_metadata).insert(),
            [{"id": 1, "council_code": "testcouncil", "reference": "APP/OLD/1"}],
        )

    first_created, first_added = migrate_schema(engine)
    assert ("applications", "extraction_attempt_count") in first_added

    second_created, second_added = migrate_schema(engine)
    assert second_added == []  # nothing missing the second time - true no-op

    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT extraction_attempt_count FROM applications WHERE reference = 'APP/OLD/1'"
        )).fetchone()
    assert row.extraction_attempt_count == 0  # still 0, not re-mangled by the second run


def test_backfill_repairs_an_explicit_null_value_directly():
    """Narrower unit test of _backfill_extraction_attempt_count itself,
    independent of the full migrate_schema() flow above - directly proves
    an explicit NULL is repaired to 0. Reuses the same old-schema-then-
    ALTER-TABLE construction as the end-to-end test above (NOT Base.
    metadata.create_all(), whose ORM-declared NOT NULL constraint on this
    column - correctly enforced for a brand-new table - would reject an
    explicit NULL insert outright and never reproduce the real bug at all;
    it only exists on rows added via the raw ALTER TABLE ADD COLUMN path,
    exactly as production will see it)."""
    engine = create_engine("sqlite:///:memory:", future=True)
    old_metadata = _build_old_applications_table(engine)
    with engine.begin() as conn:
        conn.execute(
            Table("applications", old_metadata).insert(),
            [{"id": 1, "council_code": "testcouncil", "reference": "APP/NULL/1"}],
        )

    from app.db.session import _add_missing_columns
    _add_missing_columns(engine)  # adds the column, leaves the existing row NULL - not the backfill yet

    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT extraction_attempt_count FROM applications WHERE reference = 'APP/NULL/1'"
        )).fetchone()
    assert row.extraction_attempt_count is None  # confirms the bug is real before the fix runs

    repaired = _backfill_extraction_attempt_count(engine)
    assert repaired == 1

    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT extraction_attempt_count FROM applications WHERE reference = 'APP/NULL/1'"
        )).fetchone()
    assert row.extraction_attempt_count == 0

    # Idempotent - a second call with nothing left NULL touches zero rows.
    assert _backfill_extraction_attempt_count(engine) == 0


def test_null_safe_application_logic_independent_of_migration_backfill():
    """Even if a NULL somehow still reaches application code (the backfill
    never ran, or a future write path re-introduces one), stage_extraction
    itself must not crash - proves this in isolation from Requirement B's
    migration backfill entirely.

    Cannot use the ordinary `session` fixture's schema for this: Base.
    metadata.create_all() DOES declare a genuine SQL-level NOT NULL
    constraint on this column (correct for a brand-new table), so writing
    - or even autoflushing - an explicit NULL through it raises
    IntegrityError before this test could ever reach the code path it's
    trying to exercise. A NULL is only ever reachable in practice via the
    ALTER-TABLE-added column, which - deliberately, see _add_missing_
    columns' own docstring - has no such constraint. So this builds that
    same shape directly: the old minimal applications table (ALTER-TABLE'd
    to add the 3 new columns, WITHOUT running the backfill), every other
    table via the real Base.metadata (documents, councils, sites, ...)."""
    engine = create_engine("sqlite:///:memory:", future=True)
    _build_old_applications_table(engine)
    other_tables = [t for name, t in Base.metadata.tables.items() if name != "applications"]
    Base.metadata.create_all(engine, tables=other_tables)

    from app.db.session import _add_missing_columns
    _add_missing_columns(engine)  # adds the 3 columns, no backfill - the row stays genuinely NULL

    # Insert via raw SQL, not the ORM - Application(...) + session.add() would
    # apply the ORM's own Python-side default=0 on INSERT, silently avoiding
    # the exact NULL this test needs to reproduce.
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO applications (council_code, reference) VALUES ('testcouncil', 'APP/1')"
        ))

    session_local = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    session = session_local()
    application = session.execute(select(Application).where(Application.reference == "APP/1")).scalar_one()
    assert application.extraction_attempt_count is None  # confirmed genuinely NULL, not just in-memory

    session.add(Document(
        application_id=application.id, doc_type="planning_statement",
        text_extracted=True, extracted_text="Some planning statement text.",
    ))
    session.commit()

    with patch.object(run_weekly_module, "run_extraction_for_application", return_value={"total_units_final": 1}):
        result = stage_extraction(session, object(), COUNCILS["testcouncil"])

    assert result.succeeded == 1  # no TypeError
    assert application.extraction_attempt_count == 1
    session.close()


# --- B: orphaned "running" state -> truthful terminal FAILED ---------------


def test_successful_run_still_ends_success(session):
    _app_with_document(session, reference="APP/1")
    from scripts.run_intelligence_processing import process_intelligence_backlog

    with patch.object(run_weekly_module, "run_extraction_for_application", return_value={"total_units_final": 1}):
        run = process_intelligence_backlog(
            session, COUNCILS, ["testcouncil"], max_extractions=10, max_summaries=0,
            client_factory=lambda api_key: object(),
        )
    assert run.status == "success"


def test_isolated_item_failure_still_ends_partial(session):
    _app_with_document(session, reference="APP/FAIL")
    from scripts.run_intelligence_processing import process_intelligence_backlog

    with patch.object(run_weekly_module, "run_extraction_for_application", side_effect=OpenAIError("boom")):
        run = process_intelligence_backlog(
            session, COUNCILS, ["testcouncil"], max_extractions=10, max_summaries=0,
            client_factory=lambda api_key: object(),
        )
    assert run.status == "partial"  # not failed - the job itself still completed


def test_catastrophic_run_level_exception_persists_failed(session, monkeypatch):
    """A run-level failure (something breaking client_factory/the loop
    itself, not an isolated per-item failure already handled inside
    stage_extraction) must terminalise the run as FAILED, not leave it at
    "running" forever."""
    _app_with_document(session, reference="APP/1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from scripts.run_intelligence_processing import process_intelligence_backlog

    def _boom(api_key):
        raise RuntimeError("simulated catastrophic client setup failure")

    with pytest.raises(RuntimeError, match="simulated catastrophic client setup failure"):
        process_intelligence_backlog(
            session, COUNCILS, ["testcouncil"], max_extractions=10, max_summaries=0, client_factory=_boom,
        )

    run = session.query(IntelligenceRun).one()
    assert run.status == "failed"  # never "running" forever, never "success"


def test_catastrophic_run_level_exception_sets_finished_at(session, monkeypatch):
    _app_with_document(session, reference="APP/1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from scripts.run_intelligence_processing import process_intelligence_backlog

    def _boom(api_key):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        process_intelligence_backlog(
            session, COUNCILS, ["testcouncil"], max_extractions=10, max_summaries=0, client_factory=_boom,
        )

    run = session.query(IntelligenceRun).one()
    assert run.finished_at is not None


def test_catastrophic_exception_is_re_raised_unchanged(session, monkeypatch):
    """The ORIGINAL exception (type and message) must propagate - never
    swallowed, never replaced by a generic one - so Render's own non-zero
    exit code still reflects the real cause."""
    _app_with_document(session, reference="APP/1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from scripts.run_intelligence_processing import process_intelligence_backlog

    class _CustomError(RuntimeError):
        pass

    def _boom(api_key):
        raise _CustomError("very specific original cause")

    with pytest.raises(_CustomError, match="very specific original cause"):
        process_intelligence_backlog(
            session, COUNCILS, ["testcouncil"], max_extractions=10, max_summaries=0, client_factory=_boom,
        )


def test_mid_loop_catastrophic_failure_also_persists_failed_not_partial(session, monkeypatch):
    """A failure INSIDE the council loop that is NOT one of stage_
    extraction's own classified outcomes (i.e. genuinely escapes it) must
    still terminalise as FAILED, not be silently absorbed into PARTIAL.
    Patched on scripts.run_intelligence_processing itself (where the name
    is actually called from, via `from app.pipeline.run_weekly import
    stage_extraction`) - patching app.pipeline.run_weekly's own copy of
    the name would not affect the already-bound reference in the caller's
    namespace."""
    import scripts.run_intelligence_processing as rip_module

    _app_with_document(session, reference="APP/1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from scripts.run_intelligence_processing import process_intelligence_backlog

    with patch.object(
        rip_module, "stage_extraction", side_effect=RuntimeError("simulated unexpected bug in stage_extraction itself")
    ):
        with pytest.raises(RuntimeError, match="simulated unexpected bug"):
            process_intelligence_backlog(
                session, COUNCILS, ["testcouncil"], max_extractions=10, max_summaries=0,
                client_factory=lambda api_key: object(),
            )

    run = session.query(IntelligenceRun).one()
    assert run.status == "failed"


def test_failure_state_persistence_does_not_swallow_original_exception_when_db_write_fails(session, monkeypatch):
    """Case C: even if the best-effort FAILED-state commit itself fails
    (database unavailable), the ORIGINAL catastrophic exception must still
    propagate - never masked by the secondary persistence failure."""
    _app_with_document(session, reference="APP/1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from scripts.run_intelligence_processing import process_intelligence_backlog

    original_commit = session.commit
    call_count = {"n": 0}

    def _commit_fails_on_second_call():
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise RuntimeError("simulated database unavailable during failure-state persistence")
        return original_commit()

    def _boom(api_key):
        raise ValueError("the real original catastrophic cause")

    with patch.object(session, "commit", side_effect=_commit_fails_on_second_call):
        with pytest.raises(ValueError, match="the real original catastrophic cause"):
            process_intelligence_backlog(
                session, COUNCILS, ["testcouncil"], max_extractions=10, max_summaries=0, client_factory=_boom,
            )


def test_missing_api_key_case_still_produces_failed_with_its_own_specific_message(session, monkeypatch):
    """Case A boundary - the pre-existing missing-API-key handling (not
    this hotfix's new run-level guard) must remain exactly as before: its
    own specific status/detail/finished_at, not overwritten by the new
    generic run-level guard's message."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _app_with_document(session, reference="APP/1")
    from scripts.run_intelligence_processing import process_intelligence_backlog

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        process_intelligence_backlog(session, COUNCILS, ["testcouncil"], max_extractions=10, max_summaries=10)

    run = session.query(IntelligenceRun).one()
    assert run.status == "failed"
    assert "OPENAI_API_KEY not set in .env" in run.detail  # the specific message, not the generic one
    assert "Run-level failure" not in run.detail


def test_db_unavailable_before_run_creation_is_still_a_process_level_failure(session):
    """Case A: if the very first session.add(run)/session.commit() itself
    fails, this hotfix's new run-level guard is never even entered (it
    only wraps code that runs AFTER that initial commit succeeds) - the
    exception propagates exactly as it always did, completely unhandled
    by anything this hotfix added. Asserted via the exception itself
    rather than re-querying the same (now internally inconsistent, since
    its one real commit attempt was mocked to fail) session object."""
    from scripts.run_intelligence_processing import process_intelligence_backlog

    with patch.object(session, "commit", side_effect=RuntimeError("database unavailable")):
        with pytest.raises(RuntimeError, match="database unavailable"):
            process_intelligence_backlog(
                session, COUNCILS, ["testcouncil"], max_extractions=10, max_summaries=10,
                client_factory=lambda api_key: object(),
            )
