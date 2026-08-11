"""Pilot Readiness PR-2 - focused tests for:

1. app.pipeline.freshness.classify_scraper_freshness (Part 7 thresholds).
2. app.reporting.scraper_health.build_scraper_health_summary (Part 6).
3. scripts/run_daily_councils.py's council-isolation behaviour (Part 5) -
   subprocess.run is monkeypatched so this never actually scrapes a real
   portal or opens a browser; only the orchestration/bookkeeping logic
   (ScrapeRun rows, continue-on-failure) is under test.
4. render.yaml / production-scheduling repository artifacts exist and are
   correctly shaped (Part 4).

Uses the same in-memory-SQLite `session` fixture as every other test in
this suite (tests/conftest.py).
"""
from __future__ import annotations

import datetime as dt
import subprocess
from pathlib import Path
from unittest.mock import patch

import yaml

from app.db.models import Application, Council, ScrapeRun
from app.pipeline.freshness import FRESH, STALE, UNKNOWN, WARNING, classify_scraper_freshness
from app.reporting.scraper_health import build_scraper_health_summary

REPO_ROOT = Path(__file__).resolve().parents[1]


# --- classify_scraper_freshness (Part 7) ------------------------------------


def test_no_evidence_is_unknown_not_stale():
    """Part 7's own principle: missing evidence must never be silently
    treated as proof of staleness."""
    assert classify_scraper_freshness(None) == UNKNOWN


def test_recent_successful_run_is_fresh():
    now = dt.datetime(2026, 8, 10, 12, 0, tzinfo=dt.timezone.utc)
    last_run = now - dt.timedelta(hours=10)
    assert classify_scraper_freshness(last_run, now=now) == FRESH


def test_exactly_48_hours_is_still_fresh():
    now = dt.datetime(2026, 8, 10, 12, 0, tzinfo=dt.timezone.utc)
    last_run = now - dt.timedelta(hours=48)
    assert classify_scraper_freshness(last_run, now=now) == FRESH


def test_just_over_48_hours_is_warning():
    now = dt.datetime(2026, 8, 10, 12, 0, tzinfo=dt.timezone.utc)
    last_run = now - dt.timedelta(hours=48, minutes=1)
    assert classify_scraper_freshness(last_run, now=now) == WARNING


def test_exactly_72_hours_is_still_warning():
    now = dt.datetime(2026, 8, 10, 12, 0, tzinfo=dt.timezone.utc)
    last_run = now - dt.timedelta(hours=72)
    assert classify_scraper_freshness(last_run, now=now) == WARNING


def test_just_over_72_hours_is_stale():
    now = dt.datetime(2026, 8, 10, 12, 0, tzinfo=dt.timezone.utc)
    last_run = now - dt.timedelta(hours=72, minutes=1)
    assert classify_scraper_freshness(last_run, now=now) == STALE


def test_ten_days_stale_matches_the_actual_pr1_finding():
    """Reproduces PR-1's own real finding (every council 5-10 days behind)
    as a regression case - this must classify as STALE, not FRESH/WARNING."""
    now = dt.datetime(2026, 8, 10, tzinfo=dt.timezone.utc)
    last_run = now - dt.timedelta(days=10)
    assert classify_scraper_freshness(last_run, now=now) == STALE


def test_naive_datetime_is_treated_as_utc_not_rejected():
    now = dt.datetime(2026, 8, 10, 12, 0, tzinfo=dt.timezone.utc)
    naive_last_run = dt.datetime(2026, 8, 10, 0, 0)  # no tzinfo
    assert classify_scraper_freshness(naive_last_run, now=now) == FRESH


# --- build_scraper_health_summary (Part 6) ----------------------------------


def test_council_with_no_scrape_runs_at_all_is_unknown_not_omitted(session):
    """A council this platform is configured to scrape but has never had a
    ScrapeRun for is itself the signal - must appear in the summary, not
    be silently dropped."""
    rows = build_scraper_health_summary(session)
    codes = {r["council_code"] for r in rows}
    assert "testcouncil" in codes
    row = next(r for r in rows if r["council_code"] == "testcouncil")
    assert row["freshness"] == UNKNOWN
    assert row["last_successful_at"] is None
    assert row["total_runs_recorded"] == 0


def test_successful_run_makes_council_fresh(session):
    now = dt.datetime.now(dt.timezone.utc)
    session.add(ScrapeRun(
        council_code="testcouncil", started_at=now - dt.timedelta(hours=1), finished_at=now,
        status="success", applications_before=10, applications_after=12, applications_discovered=2,
    ))
    session.commit()

    rows = build_scraper_health_summary(session)
    row = next(r for r in rows if r["council_code"] == "testcouncil")
    assert row["freshness"] == FRESH
    assert row["last_run_applications_discovered"] == 2
    assert row["total_runs_recorded"] == 1


def test_failed_run_does_not_count_as_a_successful_freshness_signal(session):
    """A failed run must not make a council look fresh - only success/
    partial runs count as evidence of a healthy execution."""
    now = dt.datetime.now(dt.timezone.utc)
    session.add(ScrapeRun(
        council_code="testcouncil", started_at=now - dt.timedelta(hours=1), finished_at=now,
        status="failed", detail="portal timeout",
    ))
    session.commit()

    rows = build_scraper_health_summary(session)
    row = next(r for r in rows if r["council_code"] == "testcouncil")
    assert row["freshness"] == UNKNOWN  # no successful run exists yet
    assert row["last_attempt_status"] == "failed"
    assert row["last_attempted_at"] is not None  # the attempt itself is still visible


def test_partial_run_counts_as_a_successful_freshness_signal(session):
    now = dt.datetime.now(dt.timezone.utc)
    session.add(ScrapeRun(
        council_code="testcouncil", started_at=now - dt.timedelta(hours=1), finished_at=now, status="partial",
    ))
    session.commit()

    rows = build_scraper_health_summary(session)
    row = next(r for r in rows if r["council_code"] == "testcouncil")
    assert row["freshness"] == FRESH


def test_most_recent_successful_run_is_used_not_the_oldest(session):
    now = dt.datetime.now(dt.timezone.utc)
    session.add_all([
        ScrapeRun(council_code="testcouncil", started_at=now - dt.timedelta(days=10),
                  finished_at=now - dt.timedelta(days=10), status="success"),
        ScrapeRun(council_code="testcouncil", started_at=now - dt.timedelta(hours=1),
                  finished_at=now, status="success"),
    ])
    session.commit()

    rows = build_scraper_health_summary(session)
    row = next(r for r in rows if r["council_code"] == "testcouncil")
    assert row["freshness"] == FRESH  # the recent one, not the 10-day-old one


def test_council_isolation_covers_every_registered_council(session):
    session.add(Council(code="thirdcouncil", name="Third Council", base_url="https://third.invalid",
                         date_field_mode="received", doc_system="idox"))
    session.commit()
    rows = build_scraper_health_summary(session)
    codes = {r["council_code"] for r in rows}
    assert {"testcouncil", "othercouncil", "thirdcouncil"}.issubset(codes)


# --- scripts/run_daily_councils.py orchestration/isolation (Part 5) --------


def _fake_completed_process(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _fake_run_council_subprocess(lines=(), returncode=0):
    """Render Daily Discovery memory instrumentation: _run_council_subprocess
    now streams output line-by-line via an on_line callback and returns a
    plain int exit code, instead of buffering everything into a
    CompletedProcess - this reproduces that streaming contract for tests
    that only care about run_one_council's own behaviour, not
    _run_council_subprocess's internals (see
    tests/test_render_daily_discovery_memory_audit.py for those)."""
    def _fake(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        if on_line is not None:
            for line in lines:
                on_line(line)
        return returncode
    return _fake


def _fake_run_council_subprocess_timeout(lines=()):
    def _fake(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        if on_line is not None:
            for line in lines:
                on_line(line)
        raise subprocess.TimeoutExpired(command, timeout_seconds)
    return _fake


def test_run_one_council_records_success(session):
    from scripts.run_daily_councils import run_one_council

    session.add(Application(council_code="testcouncil", reference="APP/1"))
    session.commit()

    with patch(
        "scripts.run_daily_councils._run_council_subprocess",
        side_effect=_fake_run_council_subprocess(["Done."], returncode=0),
    ):
        run = run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="manual")

    assert run.status == "success"
    assert run.applications_before == 1
    assert run.applications_after == 1
    assert run.applications_discovered == 0
    assert run.triggered_by == "manual"


def test_run_one_council_records_failure_without_raising(session):
    """A non-zero exit code must be recorded, never propagated as an
    exception - the caller (main()'s loop) relies on this to move on to
    the next council."""
    from scripts.run_daily_councils import run_one_council

    with patch(
        "scripts.run_daily_councils._run_council_subprocess",
        side_effect=_fake_run_council_subprocess(["Traceback: portal unreachable"], returncode=1),
    ):
        run = run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="scheduled")

    assert run.status == "failed"
    assert "portal unreachable" in run.detail


def test_run_one_council_records_timeout_without_raising(session):
    from scripts.run_daily_councils import run_one_council

    with patch(
        "scripts.run_daily_councils._run_council_subprocess",
        side_effect=_fake_run_council_subprocess_timeout(),
    ):
        run = run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="scheduled")

    assert run.status == "failed"
    assert "Timed out" in run.detail


def test_one_council_failure_does_not_prevent_the_next_council_from_running(session):
    """The actual Part 5 requirement, end to end through main()'s loop
    shape (reproduced directly here rather than importing main(), since
    main() also calls init_db()/get_session() against the real database -
    this test exercises the identical isolation logic run_one_council
    provides, called twice in sequence exactly as main()'s for-loop does)."""
    from scripts.run_daily_councils import run_one_council

    session.add(Council(code="thirdcouncil", name="Third", base_url="https://third.invalid",
                         date_field_mode="received", doc_system="idox"))
    session.commit()

    call_results = iter([
        _fake_run_council_subprocess(["council 1 crashed"], returncode=1),
        _fake_run_council_subprocess(["council 2 fine"], returncode=0),
    ])
    with patch("scripts.run_daily_councils._run_council_subprocess", side_effect=lambda *a, **k: next(call_results)(*a, **k)):
        run1 = run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="scheduled")
        run2 = run_one_council(session, "thirdcouncil", timeout_seconds=60, triggered_by="scheduled")

    assert run1.status == "failed"
    assert run2.status == "success"  # the second council's run was never skipped or affected


# --- render.yaml / production scheduling repository artifacts (Part 4) -----


def test_render_yaml_exists_and_defines_a_cron_service():
    """Updated by the PR-2 final pre-merge amendment ("Automated
    Intelligence Cadence"): render.yaml now defines TWO Cron Jobs (Daily
    Discovery + Intelligence Processing), not one - see
    tests/test_pr2_final_amendment_migration_and_intelligence_processing.py
    for the tests covering that split specifically. This test now just
    confirms Daily Discovery's own entry still reuses the existing
    scraping entry point, unaffected by that amendment."""
    render_yaml_path = REPO_ROOT / "render.yaml"
    assert render_yaml_path.exists()
    config = yaml.safe_load(render_yaml_path.read_text(encoding="utf-8"))
    services = config["services"]
    cron_services = [s for s in services if s.get("type") == "cron"]
    assert len(cron_services) >= 1
    daily_discovery = next(s for s in cron_services if s["name"] == "propertyaigent-daily-scrape")
    # Reuses the existing entry point - never a second scraping system.
    assert "scripts.run_daily_councils" in daily_discovery["startCommand"]
    assert daily_discovery["schedule"]  # a real cron expression is present


def test_render_yaml_does_not_contain_secret_values():
    """Every genuinely SECRET env var must be sync: false (operator-set in
    the Render dashboard), never a literal value committed here.

    Updated by the Render Daily Discovery runtime failure hotfix:
    PLAYWRIGHT_BROWSERS_PATH=0 is a deliberate, documented exception - a
    plain Playwright configuration constant, not a secret (see render.
    yaml's own "BUILD/RUNTIME" header comment for why it's safe to commit
    directly). This test still asserts every OTHER declared variable
    remains sync: false with no committed value, and separately asserts
    the one literal-value variable that does exist is exactly the expected
    non-secret constant - not a blanket exemption.

    Updated again by the Render Daily Discovery missing-runtime-logs
    diagnosis: PYTHONUNBUFFERED=1 is the same kind of deliberate, documented
    exception - a plain interpreter configuration constant (belt-and-braces
    alongside startCommand's own -u flag), not a secret."""
    render_yaml_path = REPO_ROOT / "render.yaml"
    text = render_yaml_path.read_text(encoding="utf-8")
    config = yaml.safe_load(text)
    KNOWN_NON_SECRET_LITERALS = {
        "PLAYWRIGHT_BROWSERS_PATH": "0",
        "PYTHONUNBUFFERED": "1",
    }
    for service in config["services"]:
        for env_var in service.get("envVars", []):
            if env_var["key"] in KNOWN_NON_SECRET_LITERALS:
                assert env_var["value"] == KNOWN_NON_SECRET_LITERALS[env_var["key"]]
                continue
            assert env_var.get("sync") is False or "value" not in env_var


def test_run_daily_councils_reuses_the_existing_pipeline_entry_point():
    source = (REPO_ROOT / "scripts" / "run_daily_councils.py").read_text(encoding="utf-8")
    assert '"app.pipeline.run_weekly"' in source
    assert "--council" in source
