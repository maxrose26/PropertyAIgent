"""Pilot Readiness PR-2 FINAL pre-merge amendment - focused tests for:

1. Database migrations must not be a page-load side effect: init_db()
   never mutates a non-SQLite (production) schema; the explicit
   migrate_schema()/verify_schema() functions (and their CLI wrappers,
   scripts.migrate_schema / scripts.verify_schema) do the actual work,
   invoked only by an operator.
2. Bounded, backlog-aware Intelligence Processing
   (scripts.run_intelligence_processing): only outstanding work is
   selected, workload is capped by PROPERTYAIGENT_MAX_EXTRACTIONS_PER_RUN/
   _MAX_SUMMARIES_PER_RUN, one failure never corrupts the rest of a run,
   and OPENAI_API_KEY is only ever read when there is genuinely
   outstanding work to do.
3. render.yaml now declares two independent Cron Jobs (Daily Discovery,
   Intelligence Processing), each with only the secrets it genuinely needs,
   still without touching the existing web service.

Uses the same in-memory-SQLite `session` fixture as every other test in
this suite (tests/conftest.py) - two councils, "testcouncil" and
"othercouncil", already present.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect

import app.db.session as db_session
from app.db.models import Application, Base, Council, IntelligenceRun, Site
from app.pipeline import run_weekly as run_weekly_module

REPO_ROOT = Path(__file__).resolve().parents[1]
RENDER_YAML = REPO_ROOT / "render.yaml"


# --- Part 1: database migrations must not be a page-load side effect -------


def test_init_db_never_mutates_a_non_sqlite_schema(monkeypatch):
    """The core fix: on a non-SQLite engine, init_db() must call
    verify_schema() (read-only) and MUST NOT call create_all() or
    _add_missing_columns() - even when the schema is already current."""
    class _FakeDialect:
        name = "postgresql"

    class _FakeEngine:
        dialect = _FakeDialect()

    fake_engine = _FakeEngine()
    monkeypatch.setattr(db_session, "get_engine", lambda: fake_engine)
    monkeypatch.setattr(db_session, "verify_schema", lambda engine: ([], []))

    def _boom(*_a, **_k):
        raise AssertionError("init_db() must not mutate a non-SQLite schema")

    monkeypatch.setattr(db_session.Base.metadata, "create_all", _boom)
    monkeypatch.setattr(db_session, "_add_missing_columns", _boom)

    db_session.init_db()  # must not raise - schema reported current, nothing mutated


def test_init_db_raises_loudly_on_a_non_sqlite_engine_with_missing_schema(monkeypatch):
    """The fail-loud half - a production engine missing a table/column
    must raise SchemaVerificationError naming exactly what's missing,
    still without attempting any mutation."""
    class _FakeDialect:
        name = "postgresql"

    class _FakeEngine:
        dialect = _FakeDialect()

    fake_engine = _FakeEngine()
    monkeypatch.setattr(db_session, "get_engine", lambda: fake_engine)
    monkeypatch.setattr(
        db_session, "verify_schema",
        lambda engine: (["intelligence_runs"], [("local_plan_sites", "confirmed_by")]),
    )

    def _boom(*_a, **_k):
        raise AssertionError("init_db() must not mutate a non-SQLite schema, even when it's out of date")

    monkeypatch.setattr(db_session.Base.metadata, "create_all", _boom)
    monkeypatch.setattr(db_session, "_add_missing_columns", _boom)

    with pytest.raises(db_session.SchemaVerificationError) as excinfo:
        db_session.init_db()

    message = str(excinfo.value)
    assert "intelligence_runs" in message
    assert "local_plan_sites.confirmed_by" in message
    assert "scripts.migrate_schema" in message


def test_init_db_still_auto_migrates_sqlite():
    """Local dev / tests / CI (SQLite) keep the old, low-friction
    behaviour - unaffected by this amendment."""
    engine = create_engine("sqlite:///:memory:", future=True)
    with patch.object(db_session, "get_engine", return_value=engine):
        db_session.init_db()
    inspector = inspect(engine)
    assert "intelligence_runs" in set(inspector.get_table_names())
    assert "local_plan_sites" in set(inspector.get_table_names())


def test_verify_schema_reports_missing_table_and_column():
    engine = create_engine("sqlite:///:memory:", future=True)
    old_metadata = MetaData()
    Table("councils", old_metadata, Column("code", String(50), primary_key=True))
    old_metadata.create_all(engine)

    missing_tables, missing_columns = db_session.verify_schema(engine)
    assert "scrape_runs" in missing_tables
    assert "intelligence_runs" in missing_tables
    assert ("councils", "name") in missing_columns


def test_verify_schema_reports_nothing_missing_once_current():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    missing_tables, missing_columns = db_session.verify_schema(engine)
    assert missing_tables == []
    assert missing_columns == []


def test_migrate_schema_creates_all_pr2_schema_from_an_old_database():
    """The explicit command creates the PR-2 table (intelligence_runs is
    this amendment's own new table - a good stand-in for "a table added
    after the database was first created") and adds PR-2's columns to an
    existing table, in one call."""
    engine = create_engine("sqlite:///:memory:", future=True)
    old_metadata = MetaData()
    Table(
        "local_plan_sites", old_metadata,
        Column("id", Integer, primary_key=True),
        Column("council_code", String(50)),
        Column("site_name", String(300)),
        Column("plan_name", String(300)),
        Column("plan_status", String(50)),
        Column("review_status", String(30)),
    )
    Table("councils", old_metadata, Column("code", String(50), primary_key=True))
    old_metadata.create_all(engine)

    created_tables, added_columns = db_session.migrate_schema(engine)

    assert "intelligence_runs" in created_tables
    assert "scrape_runs" in created_tables
    assert ("local_plan_sites", "confirmed_by") in added_columns
    assert ("local_plan_sites", "confirmed_at") in added_columns
    assert ("local_plan_sites", "match_review_note") in added_columns

    missing_tables, missing_columns = db_session.verify_schema(engine)
    assert missing_tables == []
    assert missing_columns == []


def test_migrate_schema_second_run_is_a_no_op():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    first_tables, first_columns = db_session.migrate_schema(engine)
    assert first_tables == []
    assert first_columns == []
    second_tables, second_columns = db_session.migrate_schema(engine)
    assert second_tables == []
    assert second_columns == []


def test_migrate_schema_cli_and_verify_schema_cli_against_isolated_sqlite_db(tmp_path):
    """A genuine subprocess smoke test of both CLI commands, isolated to a
    throwaway SQLite file via DATABASE_URL - never the real dev database
    (data/deal_finder.db) and never production."""
    import os
    import subprocess
    import sys

    db_path = tmp_path / "isolated_migration_test.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}

    # Before migrating: verify-schema must report missing tables and exit 1.
    result = subprocess.run(
        [sys.executable, "-m", "scripts.verify_schema"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30, env=env,
    )
    assert result.returncode == 1
    assert "MISSING TABLE" in result.stdout

    # Migrate.
    result = subprocess.run(
        [sys.executable, "-m", "scripts.migrate_schema"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30, env=env,
    )
    assert result.returncode == 0
    assert "created table" in result.stdout

    # After migrating: verify-schema must report current and exit 0.
    result = subprocess.run(
        [sys.executable, "-m", "scripts.verify_schema"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30, env=env,
    )
    assert result.returncode == 0
    assert "schema is current" in result.stdout

    # Re-running migrate-schema is a logged no-op.
    result = subprocess.run(
        [sys.executable, "-m", "scripts.migrate_schema"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30, env=env,
    )
    assert result.returncode == 0
    assert "already fully current" in result.stdout


def test_add_allocation_match_review_columns_delegates_to_migrate_schema():
    from scripts.add_allocation_match_review_columns import main as legacy_main
    from scripts.migrate_schema import main as migrate_main
    assert legacy_main is not migrate_main  # thin wrapper function, not literally aliased
    import inspect as _inspect
    source = _inspect.getsource(legacy_main)
    assert "migrate_schema_main()" in source


# --- Part 2: bounded, backlog-aware Intelligence Processing -----------------


def _make_application(session, council_code: str, reference: str, *, extracted: bool = False, with_usable_text: bool = True):
    """with_usable_text=True (the default) attaches a Document with
    text_extracted=True - AI Processing Reliability & Backlog Throughput's
    has_usable_document_text() gate means stage_extraction now skips
    (classifies OUTCOME_NO_USABLE_TEXT) any Application with no such
    Document BEFORE ever calling run_extraction_for_application, so tests
    exercising a genuine extraction attempt need one present. Pass
    with_usable_text=False to instead test the no-usable-text path."""
    from app.db.models import Document, SchemeIntelligence

    application = Application(council_code=council_code, reference=reference)
    session.add(application)
    session.commit()
    if with_usable_text and not extracted:
        session.add(Document(
            application_id=application.id, doc_type="planning_statement",
            text_extracted=True, extracted_text="Planning statement text for " + reference,
        ))
        session.commit()
    if extracted:
        session.add(SchemeIntelligence(application_id=application.id, total_units_final=10))
        session.commit()
    return application


def test_process_intelligence_backlog_selects_only_outstanding_applications(session):
    _make_application(session, "testcouncil", "APP/1", extracted=False)
    _make_application(session, "testcouncil", "APP/2", extracted=True)  # already extracted - must be skipped

    from scripts.run_intelligence_processing import process_intelligence_backlog

    with patch.object(run_weekly_module, "run_extraction_for_application", return_value={"total_units_final": 5}):
        run = process_intelligence_backlog(
            session, {"testcouncil": _council_config("testcouncil")}, ["testcouncil"],
            max_extractions=10, max_summaries=10,
            client_factory=lambda api_key: object(),
        )

    assert run.extractions_attempted == 1
    assert run.extractions_succeeded == 1
    assert run.applications_backlog_remaining == 0


def test_process_intelligence_backlog_excludes_unchanged_sites_from_summaries(session, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    import datetime as dt

    site = Site(council_code="testcouncil", canonical_address="1 Test St", display_address="1 Test St")
    session.add(site)
    session.commit()
    app1 = Application(council_code="testcouncil", reference="APP/1", site_id=site.id)
    session.add(app1)
    session.commit()
    site.status_summary = "Already summarised"
    site.status_summary_updated_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)  # newer than app1.last_seen_at
    session.commit()

    from scripts.run_intelligence_processing import process_intelligence_backlog

    with patch.object(run_weekly_module, "generate_scheme_summary") as mock_summary:
        run = process_intelligence_backlog(
            session, {"testcouncil": _council_config("testcouncil")}, ["testcouncil"],
            max_extractions=10, max_summaries=10,
        )
    mock_summary.assert_not_called()
    assert run.summaries_attempted == 0


def test_process_intelligence_backlog_enforces_extraction_limit_across_councils(session):
    for i in range(5):
        _make_application(session, "testcouncil", f"APP/{i}", extracted=False)
    for i in range(5):
        _make_application(session, "othercouncil", f"OTHER/{i}", extracted=False)

    from scripts.run_intelligence_processing import process_intelligence_backlog

    with patch.object(run_weekly_module, "run_extraction_for_application", return_value={"total_units_final": 5}):
        run = process_intelligence_backlog(
            session,
            {"testcouncil": _council_config("testcouncil"), "othercouncil": _council_config("othercouncil")},
            ["testcouncil", "othercouncil"],
            max_extractions=3, max_summaries=0,
            client_factory=lambda api_key: object(),
        )

    assert run.extractions_attempted == 3
    assert run.extractions_succeeded == 3
    assert run.applications_backlog_remaining == 7  # 10 total - 3 processed


def test_process_intelligence_backlog_one_failure_does_not_corrupt_remaining_work(session):
    _make_application(session, "testcouncil", "APP/FAILS", extracted=False)
    _make_application(session, "testcouncil", "APP/OK", extracted=False)

    from scripts.run_intelligence_processing import process_intelligence_backlog

    def _fake_extraction(client, application):
        if application.reference == "APP/FAILS":
            raise RuntimeError("simulated extraction failure")
        return {"total_units_final": 5}

    with patch.object(run_weekly_module, "run_extraction_for_application", side_effect=_fake_extraction):
        run = process_intelligence_backlog(
            session, {"testcouncil": _council_config("testcouncil")}, ["testcouncil"],
            max_extractions=10, max_summaries=0,
            client_factory=lambda api_key: object(),
        )

    assert run.extractions_attempted == 2
    assert run.extractions_succeeded == 1
    assert run.extractions_failed == 1
    # One item failing still never CORRUPTS the rest of the run (APP/OK
    # still succeeded, counters are accurate) - but AI Processing
    # Reliability & Backlog Throughput's truthful-status policy means the
    # run itself is now reported "partial", not a misleading "success"
    # (mirrors AcquisitionHealth's own "any known unresolved failure
    # counts" rule - see scripts.run_intelligence_processing._classify_run_status).
    assert run.status == "partial"


def test_process_intelligence_backlog_workload_is_bounded_not_unlimited(session):
    for i in range(50):
        _make_application(session, "testcouncil", f"APP/{i}", extracted=False)

    from scripts.run_intelligence_processing import process_intelligence_backlog

    call_count = {"n": 0}

    def _counting_extraction(client, application):
        call_count["n"] += 1
        return {"total_units_final": 5}

    with patch.object(run_weekly_module, "run_extraction_for_application", side_effect=_counting_extraction):
        run = process_intelligence_backlog(
            session, {"testcouncil": _council_config("testcouncil")}, ["testcouncil"],
            max_extractions=5, max_summaries=0,
            client_factory=lambda api_key: object(),
        )

    assert call_count["n"] == 5  # not 50 - the backlog is real but the run is bounded
    assert run.applications_backlog_remaining == 45


def test_process_intelligence_backlog_no_work_never_requires_openai_api_key(session, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from scripts.run_intelligence_processing import process_intelligence_backlog

    def _boom(api_key):
        raise AssertionError("must not create an OpenAI client when there is no outstanding work")

    run = process_intelligence_backlog(
        session, {"testcouncil": _council_config("testcouncil")}, ["testcouncil"],
        max_extractions=10, max_summaries=10,
        client_factory=_boom,
    )
    assert run.status == "success"
    assert run.extractions_attempted == 0


def test_process_intelligence_backlog_raises_loudly_when_work_exists_but_no_api_key(session, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _make_application(session, "testcouncil", "APP/1", extracted=False)

    from scripts.run_intelligence_processing import process_intelligence_backlog

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        process_intelligence_backlog(
            session, {"testcouncil": _council_config("testcouncil")}, ["testcouncil"],
            max_extractions=10, max_summaries=10,
        )

    run = session.query(IntelligenceRun).one()
    assert run.status == "failed"


def test_run_intelligence_processing_cli_exposes_bounding_flags():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "scripts.run_intelligence_processing", "--help"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert "--max-extractions" in result.stdout
    assert "--max-summaries" in result.stdout


def test_run_daily_councils_never_imports_openai():
    """Daily Discovery must remain deterministic-only, unaffected by this
    amendment - it should have no reason to import the OpenAI SDK at all."""
    source = (REPO_ROOT / "scripts" / "run_daily_councils.py").read_text(encoding="utf-8")
    assert "import openai" not in source.lower()
    assert "from openai" not in source.lower()


def _council_config(code: str):
    from app.config import CouncilConfig

    return CouncilConfig(
        code=code, name=code, base_url="https://example.invalid",
        date_field_mode="received", doc_system="idox", anite_base_url=None,
        unit_threshold=10, region=None, country=None,
    )


# --- Part 3: render.yaml two-Cron-Job architecture --------------------------


def test_render_yaml_declares_exactly_three_cron_jobs_no_web_service():
    """Updated by the Historical B3 Rebuild Unattended Overnight Runner task
    - adds a third, deliberately temporary, deliberately separate Cron Job
    (propertyaigent-historical-rebuild-overnight) for the one-off historical
    backlog. Still exactly cron jobs, still no web service declared here."""
    config = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    services = config["services"]
    assert len(services) == 3
    assert all(s["type"] == "cron" for s in services)
    names = {s["name"] for s in services}
    assert names == {
        "propertyaigent-daily-scrape", "propertyaigent-intelligence-processing",
        "propertyaigent-historical-rebuild-overnight",
    }


def test_render_yaml_historical_rebuild_overnight_requires_database_and_openai():
    config = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    overnight = next(s for s in config["services"] if s["name"] == "propertyaigent-historical-rebuild-overnight")
    env_var_keys = {e["key"] for e in overnight.get("envVars", [])}
    assert env_var_keys == {"DATABASE_URL", "OPENAI_API_KEY", "PYTHONUNBUFFERED"}


def test_render_yaml_historical_rebuild_overnight_calls_the_completion_runner():
    config = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    overnight = next(s for s in config["services"] if s["name"] == "propertyaigent-historical-rebuild-overnight")
    assert "scripts.run_historical_rebuild_to_completion" in overnight["startCommand"]
    # A valid cron expression is required by Render's config format, but
    # this job's real trigger is a manual "Trigger Run" - confirmed here by
    # asserting the schedule fires at most once a year (day-of-month AND
    # month both pinned to fixed values), not on any recurring cadence that
    # could fire unattended before an operator has deliberately chosen to.
    schedule_fields = overnight["schedule"].split()
    assert len(schedule_fields) == 5
    day_of_month, month = schedule_fields[2], schedule_fields[3]
    assert day_of_month != "*" and month != "*"


def test_render_yaml_daily_discovery_still_does_not_require_openai_key():
    """Updated by the Render Daily Discovery runtime failure hotfix:
    PLAYWRIGHT_BROWSERS_PATH is a legitimate addition (a non-secret
    Playwright config constant - see render.yaml's own "BUILD/RUNTIME"
    header) - OPENAI_API_KEY is still correctly absent.

    Updated again by the Render Daily Discovery missing-runtime-logs
    diagnosis: PYTHONUNBUFFERED is the same kind of legitimate, non-secret
    addition (belt-and-braces alongside startCommand's own -u flag)."""
    config = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    discovery = next(s for s in config["services"] if s["name"] == "propertyaigent-daily-scrape")
    env_var_keys = {e["key"] for e in discovery.get("envVars", [])}
    assert env_var_keys == {"DATABASE_URL", "PLAYWRIGHT_BROWSERS_PATH", "PYTHONUNBUFFERED"}


def test_render_yaml_intelligence_processing_requires_database_and_openai():
    config = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    intelligence = next(s for s in config["services"] if s["name"] == "propertyaigent-intelligence-processing")
    env_var_keys = {e["key"] for e in intelligence.get("envVars", [])}
    assert env_var_keys == {"DATABASE_URL", "OPENAI_API_KEY"}


def test_render_yaml_intelligence_processing_does_not_require_epc_key():
    config = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    intelligence = next(s for s in config["services"] if s["name"] == "propertyaigent-intelligence-processing")
    env_var_keys = {e["key"] for e in intelligence.get("envVars", [])}
    assert "EPC_API_KEY" not in env_var_keys


def test_render_yaml_intelligence_processing_start_command_matches_the_new_script():
    config = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    intelligence = next(s for s in config["services"] if s["name"] == "propertyaigent-intelligence-processing")
    assert "run_intelligence_processing" in intelligence["startCommand"]


def test_render_yaml_no_service_commits_an_actual_secret_value():
    """Every genuinely SECRET env var must be sync: false (operator-set in
    the Render dashboard) - none may carry a literal `value:` in this
    file. PLAYWRIGHT_BROWSERS_PATH=0 (Render Daily Discovery runtime
    failure hotfix) and PYTHONUNBUFFERED=1 (Render Daily Discovery
    missing-runtime-logs diagnosis) are the deliberate, documented
    exceptions - plain configuration constants, not secrets."""
    config = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    KNOWN_NON_SECRET_LITERALS = {"PLAYWRIGHT_BROWSERS_PATH": "0", "PYTHONUNBUFFERED": "1"}
    for service in config["services"]:
        for env_var in service.get("envVars", []):
            if env_var["key"] in KNOWN_NON_SECRET_LITERALS:
                assert env_var["value"] == KNOWN_NON_SECRET_LITERALS[env_var["key"]]
                continue
            assert env_var.get("sync") is False
            assert "value" not in env_var
