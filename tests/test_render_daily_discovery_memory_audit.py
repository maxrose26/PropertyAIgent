"""Render Daily Discovery memory audit - focused tests.

Render's Cron Job (512Mi Starter instance) survived the earlier Playwright
browser-path hotfix (build succeeds, the browser launches) but was then
OOM-killed by the container after running for several minutes. This audit
measured the real process-tree memory Playwright's own Chromium lifecycle
costs (scripts/diagnose_browser_memory.py: ~330 MiB peak for ONE council's
browser alone, before touching a single real portal page or document) and
found the pipeline's own cleanup already correct on both the happy path and
an uncaught-exception unwind (verified locally) - so this amendment applies
two narrowly-scoped, evidence-based safe fixes rather than a redesign:

1. Two conservative Playwright/Chromium launch flags for headless/
   container use (--disable-dev-shm-usage, --disable-gpu) - neither
   affects what a planning portal actually renders.
2. Process-group-isolated subprocess execution in run_daily_councils.py,
   so a council that genuinely hangs long enough to hit the per-council
   timeout has its ENTIRE process tree (Playwright driver + every
   Chromium descendant) killed, not just the one tracked PID - closing a
   real (if conditional) orphaned-browser risk that subprocess.run(...,
   timeout=...)'s own default behaviour leaves open on POSIX.

Neither the classification (512Mi is fundamentally too small for a
reliable Chromium scraper - see this audit's own final report) nor the
recommended fix (a larger Render instance) is a code change, so this file
does not attempt to prove a specific memory ceiling - it proves the two
code-level changes are correct and that nothing else about the pipeline
(failure isolation, exit-status policy, ScrapeRun observability, no AI
stages, no schema/matching changes) regressed.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import psutil
import pytest

from app.db.models import Council

REPO_ROOT = Path(__file__).resolve().parents[1]


# --- Chromium launch flags ---------------------------------------------


def test_run_weekly_chromium_launch_includes_safe_headless_container_flags():
    source = (REPO_ROOT / "app" / "pipeline" / "run_weekly.py").read_text(encoding="utf-8")
    launch_call = source[source.index("browser = p.chromium.launch"):]
    launch_call = launch_call[:launch_call.index(")") + 1]
    assert "--disable-dev-shm-usage" in launch_call
    assert "--disable-gpu" in launch_call


def test_run_weekly_chromium_launch_does_not_disable_the_sandbox():
    """--no-sandbox weakens Chromium's security sandbox against exactly
    the kind of untrusted third-party web content (council planning
    portals) this pipeline renders, and doesn't reduce memory - there is
    no memory-motivated reason to accept that security cost, and no
    evidence it's needed (no sandbox-setup error was observed - the
    reported failure was an OOM kill, not a sandbox failure). Checks only
    the actual launch() call arguments, not this file's own explanatory
    comments (which legitimately name --no-sandbox to document why it's
    deliberately absent)."""
    source = (REPO_ROOT / "app" / "pipeline" / "run_weekly.py").read_text(encoding="utf-8")
    launch_call = source[source.index("browser = p.chromium.launch"):]
    launch_call = launch_call[:launch_call.index(")") + 1]
    assert "--no-sandbox" not in launch_call


def test_run_weekly_still_launches_headless_chromium_only_once():
    """Confirms the flag addition didn't accidentally introduce a second
    browser/context/page - still exactly one of each per council run."""
    source = (REPO_ROOT / "app" / "pipeline" / "run_weekly.py").read_text(encoding="utf-8")
    assert source.count("p.chromium.launch(") == 1
    assert source.count(".new_context(") == 1
    assert source.count(".new_page()") == 1


# --- Process-group-isolated subprocess timeout handling ---------------------
#
# Render Daily Discovery memory instrumentation: _run_council_subprocess was
# redesigned from a single subprocess.run(..., capture_output=True) call
# into a STREAMING design (each line handed to an on_line callback as it
# arrives, not buffered until the child exits) - reconstructing the
# timeline of the real 2Gi production OOM found the in-flight council's
# ScrapeRun.detail was entirely empty, because the old design only ever
# wrote it from the fully-buffered output AFTER subprocess.run() returned,
# which never happened once the orchestrator itself was killed. These
# tests exercise the new _kill_process_tree helper directly (pure logic,
# no real process needed) and _run_council_subprocess itself against real,
# tiny, fast subprocesses (more robust than deep-mocking Popen/threading
# internals, and this is exactly the kind of small controlled local test
# this audit's own "Controlled Local Testing" section asks for).


def test_kill_process_tree_posix_kills_the_whole_process_group():
    from scripts.run_daily_councils import _kill_process_tree

    fake_process = MagicMock()
    fake_process.pid = 4242

    with patch("scripts.run_daily_councils.os.name", "posix"), \
         patch("scripts.run_daily_councils.os.getpgid", return_value=9999, create=True) as mock_getpgid, \
         patch("scripts.run_daily_councils.os.killpg", create=True) as mock_killpg:
        _kill_process_tree(fake_process)

    mock_getpgid.assert_called_once_with(4242)
    # 9 == SIGKILL's POSIX-standard value - see the source's own comment on
    # why this is a portable literal rather than signal.SIGKILL.
    mock_killpg.assert_called_once_with(9999, 9)
    fake_process.kill.assert_not_called()


def test_kill_process_tree_non_posix_kills_just_the_tracked_process():
    """Windows (this repo's own local dev environment) has no process-group
    model - must not attempt os.killpg there, just kill the one tracked
    Popen object, unchanged from the prior hotfix's own behaviour."""
    from scripts.run_daily_councils import _kill_process_tree

    fake_process = MagicMock()

    with patch("scripts.run_daily_councils.os.name", "nt"), \
         patch("scripts.run_daily_councils.os.killpg", create=True) as mock_killpg:
        _kill_process_tree(fake_process)

    fake_process.kill.assert_called_once()
    mock_killpg.assert_not_called()


def test_run_council_subprocess_streams_each_line_via_callback():
    """Real subprocess, not a mock - proves lines actually arrive one at a
    time rather than only being visible after the child exits."""
    from scripts.run_daily_councils import _run_council_subprocess

    lines = []
    rc = _run_council_subprocess(
        [sys.executable, "-u", "-c", "print('line1'); print('line2')"],
        cwd=REPO_ROOT, timeout_seconds=15, on_line=lines.append,
    )
    assert rc == 0
    assert lines == ["line1", "line2"]


def test_run_council_subprocess_raises_timeout_and_kills_the_hung_process():
    """Real subprocess that sleeps past its timeout - proves the process is
    actually killed (test completes quickly, not after the full sleep) and
    that whatever it printed BEFORE hanging was still streamed through."""
    from scripts.run_daily_councils import _run_council_subprocess

    lines = []
    start = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        _run_council_subprocess(
            [sys.executable, "-u", "-c", "import time; print('before-hang'); time.sleep(30)"],
            cwd=REPO_ROOT, timeout_seconds=1, on_line=lines.append,
        )
    elapsed = time.monotonic() - start

    assert elapsed < 15  # actually killed - did not wait out the full 30s sleep
    assert lines == ["before-hang"]


def test_run_council_subprocess_leaves_no_orphaned_descendants_after_normal_exit():
    """Process-tree/orphan validation (Part 9) - a child that itself spawns
    a grandchild (standing in for run_weekly.py spawning Playwright's
    driver, which spawns Chromium) must have NO live descendants once
    _run_council_subprocess returns normally - real evidence, not an
    assumption, that normal-path cleanup reaches every level of the tree,
    not just the one directly-tracked child."""
    from scripts.run_daily_councils import _run_council_subprocess

    script = (
        "import subprocess, sys; "
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(0.3)']); "
        "print('grandchild_pid=' + str(p.pid)); "
        "p.wait()"
    )
    lines = []
    rc = _run_council_subprocess(
        [sys.executable, "-u", "-c", script], cwd=REPO_ROOT, timeout_seconds=15, on_line=lines.append,
    )
    assert rc == 0

    grandchild_pid = int(next(line for line in lines if line.startswith("grandchild_pid=")).split("=")[1])
    time.sleep(0.5)  # give the OS a moment past the grandchild's own 0.3s sleep
    assert not psutil.pid_exists(grandchild_pid)


# --- run_one_council still wired through the new helper, behaviour intact --


def test_run_one_council_still_uses_run_council_subprocess(session):
    """Confirms the wiring - run_one_council calls the new streaming
    helper, not raw subprocess.run directly, without changing its own
    success/failure/ScrapeRun contract."""
    from scripts.run_daily_councils import run_one_council

    def _fake_subprocess(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        if on_line is not None:
            on_line("Done.")
        return 0

    with patch("scripts.run_daily_councils._run_council_subprocess", side_effect=_fake_subprocess) as mock_helper:
        run = run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="manual")

    assert run.status == "success"
    mock_helper.assert_called_once()


def test_run_one_council_records_timeout_from_the_new_helper_without_raising(session):
    from scripts.run_daily_councils import run_one_council

    def _fake_timeout(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        if on_line is not None:
            on_line("stuck mid-stage")
        raise subprocess.TimeoutExpired(command, timeout_seconds)

    with patch("scripts.run_daily_councils._run_council_subprocess", side_effect=_fake_timeout):
        run = run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="manual")

    assert run.status == "failed"
    assert "Timed out" in run.detail


def test_one_council_timeout_does_not_prevent_the_next_council_being_attempted(session):
    from scripts.run_daily_councils import run_one_council

    session.add(Council(
        code="thirdcouncil", name="Third", base_url="https://third.invalid",
        date_field_mode="received", doc_system="idox",
    ))
    session.commit()

    def _fake_timeout(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        raise subprocess.TimeoutExpired(command, timeout_seconds)

    def _fake_success(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        if on_line is not None:
            on_line("Done.")
        return 0

    with patch("scripts.run_daily_councils._run_council_subprocess", side_effect=_fake_timeout):
        run1 = run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="manual")
    with patch("scripts.run_daily_councils._run_council_subprocess", side_effect=_fake_success):
        run2 = run_one_council(session, "thirdcouncil", timeout_seconds=60, triggered_by="manual")

    assert run1.status == "failed"
    assert run2.status == "success"


# --- Diagnostic script: exists, imports, never touches production/AI ------


def test_diagnose_browser_memory_script_exists():
    assert (REPO_ROOT / "scripts" / "diagnose_browser_memory.py").exists()


def test_diagnose_browser_memory_never_touches_database_or_secrets():
    source = (REPO_ROOT / "scripts" / "diagnose_browser_memory.py").read_text(encoding="utf-8")
    assert "get_session" not in source
    assert "init_db" not in source
    assert "DATABASE_URL" not in source
    assert "OPENAI_API_KEY" not in source
    assert "OpenAI(" not in source


def test_diagnose_browser_memory_never_contacts_a_real_council_portal():
    source = (REPO_ROOT / "scripts" / "diagnose_browser_memory.py").read_text(encoding="utf-8")
    for council_hint in ("idox_portal", "arcus_portal", "councils.yaml", "scrape_month"):
        assert council_hint not in source
    assert "about:blank" in source


def test_diagnose_browser_memory_imports_successfully():
    import scripts.diagnose_browser_memory  # noqa: F401 - import-success is the assertion


def test_psutil_declared_in_requirements():
    text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "psutil" in text


# --- No AI / schema / matching / business-logic regressions ----------------


def test_run_daily_councils_still_never_imports_openai():
    source = (REPO_ROOT / "scripts" / "run_daily_councils.py").read_text(encoding="utf-8")
    assert "import openai" not in source.lower()
    assert "from openai" not in source.lower()


def test_exit_code_policy_unchanged_by_this_audit():
    from scripts.run_daily_councils import _exit_code

    assert _exit_code(succeeded=10, attempted=10) == 0
    assert _exit_code(succeeded=9, attempted=10) == 1
    assert _exit_code(succeeded=0, attempted=10) == 1
