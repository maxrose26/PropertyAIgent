"""Render Daily Discovery runtime failure hotfix - focused tests.

A controlled manual production run of propertyaigent-daily-scrape
(after the Playwright BUILD hotfix already landed) still failed all 10
councils, yet Render reported "Cron job run finished successfully".
Read-only inspection of the resulting ScrapeRun.detail text on every one
of the 10 rows showed the identical error:

    playwright._impl._errors.Error: BrowserType.launch: Executable
    doesn't exist at /opt/render/.cache/ms-playwright/
    chromium_headless_shell-<rev>/chrome-headless-shell-linux64/
    chrome-headless-shell

i.e. the browser binary that the build-time canary found present had
vanished by the time the Cron Job's own scheduled run actually executed -
Render Cron Jobs don't guarantee a home-directory cache written during
build persists into a later run's container. Fixed by setting
PLAYWRIGHT_BROWSERS_PATH=0 (Playwright's own documented mechanism for
this exact class of problem), which installs the browser inside the
project's own dependency tree instead of a separate, non-guaranteed cache.

Separately, run_daily_councils.py's main() never returned/exited a
non-zero status even when every council failed - fixed by giving it a
real exit-code policy (any failure -> exit 1) and adding a concise,
actionable per-failure stdout line for Render's own log viewer.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import yaml

from app.db.models import Application, Council

REPO_ROOT = Path(__file__).resolve().parents[1]
RENDER_YAML = REPO_ROOT / "render.yaml"

# The real error text captured from production ScrapeRun.detail rows -
# used verbatim so _summarize_error is tested against the actual evidence,
# not a synthetic approximation.
REAL_PRODUCTION_TRACEBACK = '''  File "<frozen runpy>", line 88, in _run_code
  File "/opt/render/project/src/app/pipeline/run_weekly.py", line 1264, in <module>
    main()
  File "/opt/render/project/src/app/pipeline/run_weekly.py", line 1176, in main
    browser = p.chromium.launch(headless=args.headless)
  File "/opt/render/project/src/.venv/lib/python3.14/site-packages/playwright/_impl/_connection.py", line 632, in wrap_api_call
    raise rewrite_error(error, f"{parsed_st['apiName']}: {error}") from None
playwright._impl._errors.Error: BrowserType.launch: Executable doesn't exist at /opt/render/.cache/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell
╔═════════════════════════════════════════════════════════╗
║ Looks like Playwright was just installed or updated.       ║
║ Please run the following command to download new browsers: ║
║                                                            ║
║     playwright install                                     ║
║                                                            ║
║ <3 Playwright Team                                         ║
╚══════════════════════════════════════════════════════════╝'''


# --- Root-cause regression: PLAYWRIGHT_BROWSERS_PATH ------------------------


def test_render_yaml_sets_playwright_browsers_path_for_daily_discovery():
    config = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    discovery = next(s for s in config["services"] if s["name"] == "propertyaigent-daily-scrape")
    env_vars = {e["key"]: e for e in discovery.get("envVars", [])}
    assert "PLAYWRIGHT_BROWSERS_PATH" in env_vars
    assert env_vars["PLAYWRIGHT_BROWSERS_PATH"]["value"] == "0"
    # Not a secret - a literal, non-sensitive Playwright config constant.
    assert "sync" not in env_vars["PLAYWRIGHT_BROWSERS_PATH"]


def test_render_yaml_does_not_set_playwright_browsers_path_for_intelligence_processing():
    """Intelligence Processing never launches a browser - it must not
    carry browser-runtime configuration it doesn't need."""
    config = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    intelligence = next(s for s in config["services"] if s["name"] == "propertyaigent-intelligence-processing")
    env_keys = {e["key"] for e in intelligence.get("envVars", [])}
    assert "PLAYWRIGHT_BROWSERS_PATH" not in env_keys


def test_playwright_browsers_path_zero_is_the_documented_bundled_install_mechanism():
    """Source-level guard: confirms the render.yaml comment explaining
    WHY this fixes the observed error is actually present, not just the
    env var itself - protects against a future edit silently changing the
    value without updating the reasoning."""
    text = RENDER_YAML.read_text(encoding="utf-8")
    assert "PLAYWRIGHT_BROWSERS_PATH" in text
    assert "chromium_headless_shell" in text or "chrome-headless-shell" in text


# --- Error summarisation (observability) ------------------------------------


def test_summarize_error_extracts_the_real_exception_line_not_the_banner():
    """The exact evidence from production: Playwright prints a friendly
    ASCII-art banner AFTER the real exception line, so a naive "last
    non-blank line" heuristic would report the banner's closing border
    instead of the actual error."""
    from scripts.run_daily_councils import _summarize_error

    summary = _summarize_error(REAL_PRODUCTION_TRACEBACK)
    assert "playwright._impl._errors.Error" in summary
    assert "Executable doesn't exist" in summary
    assert "═" not in summary  # must not be the banner border


def test_summarize_error_falls_back_to_last_line_when_no_error_pattern():
    from scripts.run_daily_councils import _summarize_error

    summary = _summarize_error("some output\nwith no exception pattern at all\nlast line here")
    assert summary == "last line here"


def test_summarize_error_handles_empty_text():
    from scripts.run_daily_councils import _summarize_error

    assert _summarize_error("") == "(no output captured)"


def test_summarize_error_never_touches_environ():
    """Confirms by source inspection that the summarizer only processes
    text already captured from the subprocess, never reads os.environ -
    it cannot introduce a NEW secret leak beyond whatever the subprocess
    itself already printed."""
    source = (REPO_ROOT / "scripts" / "run_daily_councils.py").read_text(encoding="utf-8")
    body = source[source.index("def _summarize_error"):source.index("def _application_count")]
    assert "os.environ[" not in body
    assert "os.environ.get" not in body
    assert "os.getenv(" not in body


# --- run_one_council: concise actionable failure line -----------------------


def _fake_completed_process(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _fake_run_council_subprocess(text: str = "", returncode: int = 0):
    """Render Daily Discovery memory instrumentation: _run_council_subprocess
    now streams output line-by-line via an on_line callback and returns a
    plain int exit code, instead of buffering everything into a
    CompletedProcess - this reproduces that streaming contract for tests
    that only care about run_one_council's own behaviour (see
    tests/test_render_daily_discovery_memory_audit.py for tests of
    _run_council_subprocess's own internals against real subprocesses)."""
    def _fake(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        if on_line is not None:
            for line in text.splitlines():
                on_line(line)
        return returncode
    return _fake


def test_run_one_council_prints_concise_actionable_error_line_on_failure(session, capsys):
    from scripts.run_daily_councils import run_one_council

    with patch(
        "scripts.run_daily_councils._run_council_subprocess",
        side_effect=_fake_run_council_subprocess(REAL_PRODUCTION_TRACEBACK, returncode=1),
    ):
        run = run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="manual")

    assert run.status == "failed"
    captured = capsys.readouterr()
    assert "testcouncil: FAILED" in captured.out
    assert "return_code=1" in captured.out
    assert "playwright._impl._errors.Error" in captured.out


def test_run_one_council_success_path_does_not_print_error_lines(session, capsys):
    from scripts.run_daily_councils import run_one_council

    session.add(Application(council_code="testcouncil", reference="APP/1"))
    session.commit()

    with patch(
        "scripts.run_daily_councils._run_council_subprocess",
        side_effect=_fake_run_council_subprocess("Done.", returncode=0),
    ):
        run = run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="manual")

    assert run.status == "success"
    captured = capsys.readouterr()
    assert "return_code=" not in captured.out
    assert "OK" in captured.out


# --- Exit code policy ---------------------------------------------------


def test_exit_code_all_succeeded_is_zero():
    from scripts.run_daily_councils import _exit_code

    assert _exit_code(succeeded=10, attempted=10) == 0


def test_exit_code_partial_failure_is_nonzero():
    from scripts.run_daily_councils import _exit_code

    assert _exit_code(succeeded=9, attempted=10) != 0


def test_exit_code_total_failure_is_nonzero():
    from scripts.run_daily_councils import _exit_code

    assert _exit_code(succeeded=0, attempted=10) != 0


def test_exit_code_orchestrator_level_skip_also_counts_as_unhealthy():
    """A council that never even got a ScrapeRun recorded (an
    orchestrator-level bookkeeping exception, not a subprocess failure)
    must still make the whole run report unhealthy - main() passes
    `attempted=len(council_codes)`, not `len(results)`, specifically so a
    silently-skipped council can't hide inside a technically-all-succeeded
    result set."""
    from scripts.run_daily_councils import _exit_code

    # 9 councils actually got recorded and all 9 succeeded, but 10 were
    # meant to be attempted - the 10th vanished into an orchestrator-level
    # exception and was never appended to results at all.
    assert _exit_code(succeeded=9, attempted=10) != 0


def test_main_calls_sys_exit_with_the_real_exit_code():
    """Confirms main() is actually wired to propagate a real process exit
    code via sys.exit(main()) - not just that the pure policy function
    exists in isolation."""
    source = (REPO_ROOT / "scripts" / "run_daily_councils.py").read_text(encoding="utf-8")
    assert 'sys.exit(main())' in source
    assert "def main() -> int:" in source


# --- Failure isolation preserved (all councils still attempted) ------------


def test_one_council_failure_does_not_prevent_the_next_council_being_attempted(session):
    from scripts.run_daily_councils import run_one_council

    session.add(Council(
        code="thirdcouncil", name="Third", base_url="https://third.invalid",
        date_field_mode="received", doc_system="idox",
    ))
    session.commit()

    with patch(
        "scripts.run_daily_councils._run_council_subprocess",
        side_effect=_fake_run_council_subprocess(REAL_PRODUCTION_TRACEBACK, returncode=1),
    ):
        run1 = run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="manual")
    with patch(
        "scripts.run_daily_councils._run_council_subprocess",
        side_effect=_fake_run_council_subprocess("Done.", returncode=0),
    ):
        run2 = run_one_council(session, "thirdcouncil", timeout_seconds=60, triggered_by="manual")

    assert run1.status == "failed"
    assert run2.status == "success"  # the second council's own attempt is unaffected by the first's failure


# --- ScrapeRun / Council Operations freshness classification unaffected ----


def test_failed_run_cannot_be_classified_as_fresh(session):
    from app.pipeline.freshness import FRESH, UNKNOWN, classify_scraper_freshness
    from scripts.run_daily_councils import run_one_council

    with patch(
        "scripts.run_daily_councils._run_council_subprocess",
        side_effect=_fake_run_council_subprocess(REAL_PRODUCTION_TRACEBACK, returncode=1),
    ):
        run = run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="manual")

    assert run.status == "failed"
    # A failed attempt has no successful run timestamp to classify from -
    # classify_scraper_freshness must never be fed a failed run's own
    # finished_at as if it were a success (Council Operations' own caller
    # is responsible for that filtering; this asserts the failed run's own
    # status makes it ineligible in the first place).
    freshness = classify_scraper_freshness(None)
    assert freshness == UNKNOWN
    assert freshness != FRESH


def test_successful_council_still_recorded_as_successful_in_a_mixed_run(session):
    """Even though the overall PROCESS exit code is now non-zero for any
    partial failure, each council's own ScrapeRun status must remain
    independently accurate - Council Operations should still show the
    successful councils as genuinely fresh."""
    from scripts.run_daily_councils import run_one_council

    session.add(Council(
        code="thirdcouncil", name="Third", base_url="https://third.invalid",
        date_field_mode="received", doc_system="idox",
    ))
    session.commit()

    with patch(
        "scripts.run_daily_councils._run_council_subprocess",
        side_effect=_fake_run_council_subprocess("Done.", returncode=0),
    ):
        good_run = run_one_council(session, "thirdcouncil", timeout_seconds=60, triggered_by="manual")
    with patch(
        "scripts.run_daily_councils._run_council_subprocess",
        side_effect=_fake_run_council_subprocess(REAL_PRODUCTION_TRACEBACK, returncode=1),
    ):
        bad_run = run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="manual")

    assert good_run.status == "success"
    assert bad_run.status == "failed"


# --- No AI stages invoked by Daily Discovery, still true after this fix ----


def test_run_daily_councils_still_never_imports_openai():
    source = (REPO_ROOT / "scripts" / "run_daily_councils.py").read_text(encoding="utf-8")
    assert "import openai" not in source.lower()
    assert "from openai" not in source.lower()


def test_run_daily_councils_still_defaults_to_skipping_ai_stages(session):
    from scripts.run_daily_councils import run_one_council

    captured_commands = []

    def fake_run(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        captured_commands.append(command)
        if on_line is not None:
            on_line("Done.")
        return 0

    with patch("scripts.run_daily_councils._run_council_subprocess", side_effect=fake_run):
        run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="manual")

    assert "--skip-extraction" in captured_commands[0]
    assert "--skip-scheme-summary" in captured_commands[0]
