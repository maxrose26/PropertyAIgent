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
from pathlib import Path
from unittest.mock import MagicMock, patch

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


def test_run_council_subprocess_posix_kills_whole_process_group_on_timeout():
    """The exact fix: on POSIX, a timeout must kill the CHILD'S PROCESS
    GROUP (every Playwright-driver/Chromium descendant), not just the one
    tracked PID - proven here via mocks, since this Windows dev machine
    cannot exercise a real POSIX process group."""
    from scripts.run_daily_councils import _run_council_subprocess

    fake_process = MagicMock()
    fake_process.pid = 4242
    fake_process.communicate.side_effect = [
        subprocess.TimeoutExpired(cmd=["x"], timeout=1),
        ("partial stdout", "partial stderr"),
    ]

    with patch("scripts.run_daily_councils.os.name", "posix"), \
         patch("scripts.run_daily_councils.subprocess.Popen", return_value=fake_process) as mock_popen, \
         patch("scripts.run_daily_councils.os.getpgid", return_value=9999, create=True) as mock_getpgid, \
         patch("scripts.run_daily_councils.os.killpg", create=True) as mock_killpg:
        try:
            _run_council_subprocess(["python", "-m", "x"], cwd=REPO_ROOT, timeout_seconds=1)
            assert False, "expected TimeoutExpired to propagate"
        except subprocess.TimeoutExpired as e:
            assert e.stdout == "partial stdout"
            assert e.stderr == "partial stderr"

    # start_new_session=True is what makes the child its own process-group
    # leader in the first place - the fix does nothing without this.
    assert mock_popen.call_args.kwargs.get("start_new_session") is True
    mock_getpgid.assert_called_once_with(4242)
    # 9 == SIGKILL's POSIX-standard value - see the source's own comment on
    # why this is a portable literal rather than signal.SIGKILL.
    mock_killpg.assert_called_once_with(9999, 9)


def test_run_council_subprocess_posix_success_path_returns_completed_process():
    from scripts.run_daily_councils import _run_council_subprocess

    fake_process = MagicMock()
    fake_process.pid = 4242
    fake_process.returncode = 0
    fake_process.communicate.return_value = ("all good", "")

    with patch("scripts.run_daily_councils.os.name", "posix"), \
         patch("scripts.run_daily_councils.subprocess.Popen", return_value=fake_process):
        result = _run_council_subprocess(["python", "-m", "x"], cwd=REPO_ROOT, timeout_seconds=60)

    assert result.returncode == 0
    assert result.stdout == "all good"


def test_run_council_subprocess_non_posix_falls_back_to_plain_subprocess_run():
    """Windows (this repo's own local dev environment) has no equivalent
    process-group model - must not attempt os.killpg there, just delegate
    to the pre-existing subprocess.run() behaviour unchanged."""
    from scripts.run_daily_councils import _run_council_subprocess

    with patch("scripts.run_daily_councils.os.name", "nt"), \
         patch(
             "scripts.run_daily_councils.subprocess.run",
             return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
         ) as mock_run:
        result = _run_council_subprocess(["python", "-m", "x"], cwd=REPO_ROOT, timeout_seconds=60)

    assert result.returncode == 0
    mock_run.assert_called_once()


def test_run_council_subprocess_never_calls_killpg_on_non_posix():
    from scripts.run_daily_councils import _run_council_subprocess

    with patch("scripts.run_daily_councils.os.name", "nt"), \
         patch("scripts.run_daily_councils.subprocess.run",
               return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")), \
         patch("scripts.run_daily_councils.os.killpg", create=True) as mock_killpg:
        _run_council_subprocess(["python", "-m", "x"], cwd=REPO_ROOT, timeout_seconds=60)

    mock_killpg.assert_not_called()


# --- run_one_council still wired through the new helper, behaviour intact --


def test_run_one_council_still_uses_run_council_subprocess(session):
    """Confirms the wiring - run_one_council calls the new process-group-
    aware helper, not raw subprocess.run directly, without changing its
    own success/failure/ScrapeRun contract."""
    from scripts.run_daily_councils import run_one_council

    with patch(
        "scripts.run_daily_councils._run_council_subprocess",
        return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="Done.", stderr=""),
    ) as mock_helper:
        run = run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="manual")

    assert run.status == "success"
    mock_helper.assert_called_once()


def test_run_one_council_records_timeout_from_the_new_helper_without_raising(session):
    from scripts.run_daily_councils import run_one_council

    with patch(
        "scripts.run_daily_councils._run_council_subprocess",
        side_effect=subprocess.TimeoutExpired(cmd=["x"], timeout=60, output="partial", stderr="stuck"),
    ):
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

    with patch(
        "scripts.run_daily_councils._run_council_subprocess",
        side_effect=subprocess.TimeoutExpired(cmd=["x"], timeout=60, output="", stderr=""),
    ):
        run1 = run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="manual")
    with patch(
        "scripts.run_daily_councils._run_council_subprocess",
        return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="Done.", stderr=""),
    ):
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
