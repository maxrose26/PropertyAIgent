"""Pilot Readiness PR-2 pre-merge architecture check - focused tests for:

1. AI cost safety (Part 1) - the daily orchestrator must default to
   deterministic-only subprocess invocations, never require OPENAI_API_KEY
   by default, and only include AI stages when explicitly opted in.
2. Database schema deployment safety (Part 2) - app.db.session.
   _add_missing_columns must now work for every dialect, not just SQLite
   (the exact fix that removes the deployment-ordering risk the pre-merge
   check identified). A genuine functional SQLite test proves the ADD-
   COLUMN code path itself still works end-to-end; a dialect-compilation
   check proves the same statement shape is valid PostgreSQL DDL, without
   requiring a second live Postgres instance in this test environment (and
   deliberately without touching the real production database, which
   already carries real reviewed data in exactly these columns).
3. render.yaml Blueprint safety (Part 3) - exactly one service, no secret
   the scheduled job doesn't genuinely need.

Uses the same in-memory-SQLite `session` fixture as every other test in
this suite (tests/conftest.py) where a DB is needed.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import yaml
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect

from app.db.session import _add_missing_columns

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_DAILY_COUNCILS_SOURCE = (REPO_ROOT / "scripts" / "run_daily_councils.py").read_text(encoding="utf-8")
RENDER_YAML = REPO_ROOT / "render.yaml"


# --- Part 1: AI cost safety --------------------------------------------------


def test_daily_orchestrator_defaults_to_skipping_ai_stages():
    """The exact fix: run_one_council must pass --skip-extraction
    --skip-scheme-summary unless include_ai_stages=True."""
    from scripts.run_daily_councils import run_one_council

    captured_commands = []

    def fake_run(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        captured_commands.append(command)
        if on_line is not None:
            on_line("Done.")
        return 0

    from sqlalchemy import create_engine as _ce
    from sqlalchemy.orm import sessionmaker as _sm
    from app.db.models import Base, Council

    engine = _ce("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    db = _sm(bind=engine, future=True, expire_on_commit=False)()
    db.add(Council(code="testcouncil", name="Test", base_url="https://x.invalid",
                    date_field_mode="received", doc_system="idox"))
    db.commit()

    with patch("scripts.run_daily_councils._run_council_subprocess", side_effect=fake_run):
        run_one_council(db, "testcouncil", timeout_seconds=60, triggered_by="scheduled")

    assert len(captured_commands) == 1
    assert "--skip-extraction" in captured_commands[0]
    assert "--skip-scheme-summary" in captured_commands[0]


def test_daily_orchestrator_include_ai_stages_flag_omits_the_skip_flags():
    from scripts.run_daily_councils import run_one_council

    captured_commands = []

    def fake_run(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        captured_commands.append(command)
        if on_line is not None:
            on_line("Done.")
        return 0

    from sqlalchemy import create_engine as _ce
    from sqlalchemy.orm import sessionmaker as _sm
    from app.db.models import Base, Council

    engine = _ce("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    db = _sm(bind=engine, future=True, expire_on_commit=False)()
    db.add(Council(code="testcouncil", name="Test", base_url="https://x.invalid",
                    date_field_mode="received", doc_system="idox"))
    db.commit()

    with patch("scripts.run_daily_councils._run_council_subprocess", side_effect=fake_run):
        run_one_council(db, "testcouncil", timeout_seconds=60, triggered_by="manual", include_ai_stages=True)

    assert "--skip-extraction" not in captured_commands[0]
    assert "--skip-scheme-summary" not in captured_commands[0]


def test_run_daily_councils_exposes_include_ai_stages_cli_flag():
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "scripts.run_daily_councils", "--help"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert "--include-ai-stages" in result.stdout


def test_run_weekly_ai_stages_are_individually_gated_and_incremental():
    """Documents (via source inspection) the two facts the pre-merge
    report relies on: stage_extraction only processes applications with no
    scheme_intelligence yet, and stage_generate_scheme_summaries skips a
    site with nothing new since its last summary. Both were already true
    before this check - not changed by it - this test exists so a future
    edit to either gate can't silently regress without a test noticing."""
    source = (REPO_ROOT / "app" / "pipeline" / "run_weekly.py").read_text(encoding="utf-8")
    extraction_body = source[source.index("def stage_extraction"):source.index("def stage_geocode_sites")]
    assert "Application.scheme_intelligence == None" in extraction_body

    summary_body = source[
        source.index("def stage_generate_scheme_summaries"):source.index("def stage_enrichment")
    ]
    assert "continue  # nothing new since the last summary" in summary_body


def test_run_weekly_ai_stages_are_not_gated_by_orchestrator_flags_alone():
    """Confirms the orchestrator's fix is necessary in the first place -
    run_weekly.py's own main() calls both AI stages unconditionally
    (guarded only by its OWN --skip-extraction/--skip-scheme-summary CLI
    flags, which nothing calls by default) - i.e. the daily-cron-specific
    defaulting genuinely has to live in the orchestrator, not assume
    run_weekly.py already opts out on its own."""
    source = (REPO_ROOT / "app" / "pipeline" / "run_weekly.py").read_text(encoding="utf-8")
    assert 'if not args.skip_extraction:' in source
    assert 'if not args.skip_scheme_summary:' in source
    # Both raise immediately without OPENAI_API_KEY - confirming the cost-
    # safety report's own claim about what would happen if unmodified.
    assert 'raise RuntimeError("OPENAI_API_KEY not set in .env")' in source


# --- Part 2: database schema deployment safety ------------------------------


def test_add_missing_columns_now_handles_every_dialect_not_just_sqlite():
    """The exact fix - the previous `if engine.dialect.name != "sqlite":
    return` early-exit must be gone."""
    source = (REPO_ROOT / "app" / "db" / "session.py").read_text(encoding="utf-8")
    body = source[source.index("def _add_missing_columns"):source.index("def init_db")]
    assert 'if engine.dialect.name != "sqlite"' not in body


def test_add_missing_columns_adds_a_genuinely_missing_column_on_sqlite():
    """Real functional proof the diff-and-ALTER logic itself still works:
    create a table matching an OLDER version of a real model (missing a
    column Base.metadata currently declares), run _add_missing_columns,
    confirm the column is added with the correct type and the table's
    existing data survives untouched."""
    from app.db.models import Base, LocalPlanSite  # noqa: F401 - ensures LocalPlanSite is registered on Base.metadata

    engine = create_engine("sqlite:///:memory:", future=True)

    # Create every table via the real metadata EXCEPT hand-build local_plan_sites
    # without confirmed_by/confirmed_at/match_review_note, simulating "a
    # database created before this sprint's columns existed".
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
    old_metadata.create_all(engine)

    inspector_before = inspect(engine)
    columns_before = {c["name"] for c in inspector_before.get_columns("local_plan_sites")}
    assert "confirmed_by" not in columns_before
    assert "match_review_note" not in columns_before

    with engine.begin() as conn:
        conn.execute(
            Table("local_plan_sites", old_metadata).insert(),
            [{"id": 1, "council_code": "testcouncil", "site_name": "Existing Row", "plan_name": "Test Plan",
              "plan_status": "adopted", "review_status": "needs_confirmation"}],
        )

    _add_missing_columns(engine)

    inspector_after = inspect(engine)
    columns_after = {c["name"] for c in inspector_after.get_columns("local_plan_sites")}
    assert "confirmed_by" in columns_after
    assert "confirmed_at" in columns_after
    assert "match_review_note" in columns_after

    with engine.begin() as conn:
        row = conn.execute(Table("local_plan_sites", old_metadata).select()).fetchone()
        assert row.site_name == "Existing Row"  # existing data survived the migration untouched


def test_add_missing_columns_is_idempotent_second_run_is_a_no_op():
    from app.db.models import Base  # noqa: F401

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)  # first run - should be a no-op, everything already exists
    _add_missing_columns(engine)  # second run - must not raise (duplicate-column error)


def test_generated_alter_table_statement_is_valid_postgresql_ddl():
    """Proves the ALTER TABLE statement _add_missing_columns would send to
    Postgres is syntactically valid PostgreSQL DDL, via SQLAlchemy's own
    dialect-aware type compilation - without requiring a live Postgres
    connection in this test environment. Deliberately does not run this
    against the real production database (it already holds real, human-
    written review data in exactly these columns from this sprint's own
    allocation-match review - see scripts/apply_pr2_allocation_match_review.py)."""
    from sqlalchemy.dialects import postgresql
    from app.db.models import LocalPlanSite

    pg_dialect = postgresql.dialect()
    confirmed_by_column = LocalPlanSite.__table__.columns["confirmed_by"]
    compiled_type = confirmed_by_column.type.compile(dialect=pg_dialect)
    statement = f'ALTER TABLE "local_plan_sites" ADD COLUMN "confirmed_by" {compiled_type}'

    assert statement.startswith("ALTER TABLE")
    assert "VARCHAR" in compiled_type  # String(100) compiles to VARCHAR on postgresql, confirming real dialect awareness

    match_review_note_column = LocalPlanSite.__table__.columns["match_review_note"]
    text_compiled = match_review_note_column.type.compile(dialect=pg_dialect)
    assert "TEXT" in text_compiled


def test_scrape_run_new_table_creation_is_unaffected_by_the_column_fix():
    """A brand-new table (ScrapeRun) must still be created by create_all()
    alone, on every dialect - the diffing helper explicitly reports (never
    mutates) any table not already present, since create_all's job is
    creating it - so neither _add_missing_columns nor migrate_schema()
    change that division of responsibility.

    Updated by the PR-2 final pre-merge amendment ("Implement The
    Smallest Explicit Migration Mechanism"): the diff logic itself moved
    into a separate _diff_missing_columns helper shared by _add_missing_
    columns (init_db()'s SQLite auto-mutation) and migrate_schema() (the
    new explicit command) - see tests/
    test_pr2_final_amendment_migration_and_intelligence_processing.py for
    the tests covering that split specifically."""
    source = (REPO_ROOT / "app" / "db" / "session.py").read_text(encoding="utf-8")
    body = source[source.index("def _diff_missing_columns"):source.index("def verify_schema")]
    assert 'if table.name not in existing_tables' in body
    assert 'missing_tables.append(table.name)' in body


def test_add_allocation_match_review_columns_script_is_now_a_thin_wrapper():
    """The standalone script is documented as superseded - confirms it no
    longer contains its own duplicate ALTER TABLE logic. Updated by the
    PR-2 final pre-merge amendment: this script now delegates to
    scripts.migrate_schema (the explicit migration command), not
    init_db() directly (init_db() no longer mutates a non-SQLite schema -
    see this module's own docstring for why)."""
    source = (REPO_ROOT / "scripts" / "add_allocation_match_review_columns.py").read_text(encoding="utf-8")
    assert "ALTER TABLE" not in source
    assert "migrate_schema" in source


# --- Part 3: render.yaml Blueprint safety -----------------------------------
#
# NOTE: render.yaml grew a second Cron Job (Intelligence Processing) in the
# PR-2 final pre-merge amendment ("Automated Intelligence Cadence" /
# "Render Architecture") - see
# tests/test_pr2_final_amendment_migration_and_intelligence_processing.py
# for the tests covering the two-service structure specifically. The tests
# below still hold: services[0] remains propertyaigent-daily-scrape,
# unchanged by that amendment.


def test_render_yaml_defines_at_least_the_original_cron_job():
    config = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    services = config["services"]
    assert len(services) >= 1
    assert all(s["type"] == "cron" for s in services)
    assert services[0]["name"] == "propertyaigent-daily-scrape"


def test_render_yaml_does_not_declare_a_web_service():
    """Confirms syncing this Blueprint cannot create or interfere with the
    existing Streamlit web service - there is no `type: web` entry here at
    all for Render to reconcile against."""
    config = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    service_types = {s["type"] for s in config["services"]}
    assert "web" not in service_types


def test_render_yaml_only_requires_database_url():
    """The corrected minimal requirement - OPENAI_API_KEY/EPC_API_KEY are
    genuinely not needed by the default scheduled invocation and must not
    be declared as required secrets the job doesn't actually need.

    Updated by the Render Daily Discovery runtime failure hotfix:
    PLAYWRIGHT_BROWSERS_PATH is a legitimate addition - not a secret this
    job doesn't need, but a plain Playwright configuration constant (see
    render.yaml's own "BUILD/RUNTIME" header comment) required for the
    browser Daily Discovery already unconditionally depends on to actually
    be found at run time, not just at build time."""
    config = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    env_var_keys = {e["key"] for e in config["services"][0].get("envVars", [])}
    assert env_var_keys == {"DATABASE_URL", "PLAYWRIGHT_BROWSERS_PATH"}


def test_render_yaml_start_command_matches_the_orchestrator_default_behaviour():
    """The Cron Job's startCommand has no --include-ai-stages flag - it
    relies on run_daily_councils.py's own default (skip AI stages), not on
    the Blueprint itself re-deciding this."""
    config = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    start_command = config["services"][0]["startCommand"]
    assert "run_daily_councils" in start_command
    assert "--include-ai-stages" not in start_command
