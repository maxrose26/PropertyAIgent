"""Render Daily Discovery missing-runtime-logs + repeated 2GiB OOM
diagnosis.

Two production runs on the merged memory-instrumentation branch (63b3bb6)
both OOM'd after ~14-15 minutes with ZERO [mem]/[mem-warning] lines and
ZERO normal streamed council output visible in Render's log viewer -
despite the child subprocess (app.pipeline.run_weekly) already being
launched with -u. Root cause: the PARENT process itself
(scripts.run_daily_councils) was launched as plain `python -m
scripts.run_daily_councils` - unbuffered mode was only ever applied to the
CHILD's own command line, never to the parent's own invocation. CPython
block-buffers stdout whenever it is not attached to a real terminal (always
true for a Cron Job's captured output), so every print() the PARENT itself
made - including every re-printed child line and every [mem] line from
log_memory() being called AT THE PARENT LEVEL TOO (see
_run_council_subprocess's own "council.subprocess_started" call) - sat
unflushed in that process's own stdout buffer. A container-level OOM SIGKILL
gives Python no chance to flush on the way out, so none of it ever reached
Render.

Reconstructing the actual latest ScrapeRun rows also found a second, real
gap independent of Render's log viewer: even with the previous hotfix's
streaming design, a council's ScrapeRun.detail is only ever written ONCE,
at the very end of run_one_council - if the whole container dies mid-
council (not just that one council's own subprocess timing out), that
final write never executes, and NOTHING streamed during that council's
run is recoverable afterward. Confirmed directly: all 3 of the most
recent production runs left the in-flight council (salford, all 3 times)
with ScrapeRun.detail == None. This file tests the fix for both gaps:
(1) the parent-process buffering fix (render.yaml -u + PYTHONUNBUFFERED +
flush=True on every critical print), and (2) the DB-persisted incremental
memory checkpoint that survives even when the final end-of-run write never
happens.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import yaml
import pytest
from unittest.mock import patch

from app.db.models import Application, ScrapeRun

REPO_ROOT = Path(__file__).resolve().parents[1]
RENDER_YAML = REPO_ROOT / "render.yaml"


# --- Part 5: streaming must be timing-proven, not just source-scanned ------


def test_streaming_delivers_a_line_before_the_child_sleep_completes():
    """The exact scenario the missing-logs diagnosis needed proven: a
    child that prints, then sleeps for several seconds, then prints again
    and exits - the FIRST line must reach the parent's on_line callback
    well before the sleep finishes (proving genuine incremental streaming,
    not "read everything once the child exits"), and the second line must
    still arrive afterward."""
    from scripts.run_daily_councils import _run_council_subprocess

    received: list[str] = []
    timestamps: dict[str, float] = {}
    start = time.monotonic()

    def _on_line(line: str) -> None:
        received.append(line)
        timestamps.setdefault(line, time.monotonic() - start)

    command = [
        sys.executable, "-u", "-c",
        "import time; print('line-A', flush=True); time.sleep(3); print('line-B', flush=True)",
    ]
    return_code = _run_council_subprocess(command, cwd=REPO_ROOT, timeout_seconds=30, on_line=_on_line)

    assert return_code == 0
    assert received == ["line-A", "line-B"]
    # line-A must have arrived almost immediately - well before the 3s
    # sleep completes, not just before the process eventually exits.
    assert timestamps["line-A"] < 1.5
    assert timestamps["line-B"] >= 3.0


# --- Parts 3/4: parent-level buffering fix ----------------------------------


def test_render_yaml_daily_scrape_start_command_is_launched_unbuffered():
    """The confirmed root cause of the missing-logs symptom: the PARENT
    orchestrator process was never itself launched with -u, only the
    CHILD run_weekly.py subprocess was. Without this, everything the
    parent process prints - including every [mem] line from its own
    log_memory() calls - sits unflushed in ITS OWN stdout buffer and is
    lost entirely if the container is SIGKILLed for OOM."""
    config = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    discovery = next(s for s in config["services"] if s["name"] == "propertyaigent-daily-scrape")
    assert discovery["startCommand"] == "python -u -m scripts.run_daily_councils"


def test_render_yaml_daily_scrape_sets_pythonunbuffered_as_a_second_layer():
    """Belt-and-braces (Part 4: "Do not rely on only one fragile buffering
    assumption") - PYTHONUNBUFFERED=1 must be set independently of the -u
    flag, so a future manual dashboard edit that drops -u from
    startCommand still can't silently reintroduce parent-side buffering."""
    config = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    discovery = next(s for s in config["services"] if s["name"] == "propertyaigent-daily-scrape")
    env_vars = {e["key"]: e.get("value") for e in discovery.get("envVars", [])}
    assert env_vars.get("PYTHONUNBUFFERED") == "1"


def test_log_memory_flushes_every_print_explicitly(monkeypatch):
    """A third, independent layer (Part 4) - log_memory() itself must not
    depend on the calling process's own buffering configuration staying
    correct forever. Spies on the real print() call to assert flush=True
    is passed on every line log_memory emits, including the warning line."""
    import builtins

    import app.diagnostics.memory as memory_module

    calls = []
    real_print = builtins.print

    def _spy_print(*args, **kwargs):
        calls.append(kwargs)
        real_print(*args, **kwargs)

    monkeypatch.setattr(builtins, "print", _spy_print)
    monkeypatch.setattr(
        memory_module, "process_tree_rss_mib", lambda pid=None: (2000.0, 0.0)
    )

    memory_module.log_memory("stage_documents.after", council="salford")

    assert len(calls) == 2  # one [mem] line, one [mem-warning] line (total > default threshold)
    assert all(kwargs.get("flush") is True for kwargs in calls)


def test_run_daily_councils_critical_prints_use_flush_true():
    """Source-level guard (cheap, direct) that the orchestrator's own
    critical status lines - not just log_memory() - are flushed
    explicitly: the "starting", "OK", "FAILED", per-line child-forwarding,
    and final "Done." prints must all pass flush=True."""
    source = (REPO_ROOT / "scripts" / "run_daily_councils.py").read_text(encoding="utf-8")
    critical_snippets = [
        'print(f"\\n[run-daily-councils] {council_code}: starting',
        'print(f"[{council_code}] {line}"',
        'print(f"[run-daily-councils] {council_code}: OK',
        'print(f"[run-daily-councils] {council_code}: FAILED"',
        'print(f"  return_code={return_code}"',
        'print(f"  error={error_summary}"',
        'print(f"[run-daily-councils] {council_code}: orchestrator-level error',
    ]
    for snippet in critical_snippets:
        idx = source.index(snippet)
        # The matching print(...) call, wherever its closing paren falls,
        # must include flush=True somewhere before that close.
        call_end = source.index(")\n", idx)
        assert "flush=True" in source[idx:call_end + 1], f"missing flush=True near: {snippet!r}"


def test_orchestrator_logs_a_mem_line_before_the_council_loop_starts():
    """Part 6: [mem] orchestrator.start must exist before init_db()/the
    loop, so the very first line of a production run proves whether the
    parent process itself is genuinely emitting/flushing output."""
    source = (REPO_ROOT / "scripts" / "run_daily_councils.py").read_text(encoding="utf-8")
    main_body = source[source.index("def main() -> int:"):]
    orchestrator_start_idx = main_body.index('log_memory("orchestrator.start")')
    # The bare "init_db()" ALSO appears inside this same block's own
    # explanatory comment (referring to the function in prose) - search
    # for the actual statement on its own line, not just the substring,
    # so the comment mentioning it doesn't produce a false match.
    init_db_call_idx = main_body.index("\n    init_db()\n")
    assert orchestrator_start_idx < init_db_call_idx


# --- Part 7: persisted memory checkpoint survives a hard kill --------------


def test_mem_line_is_persisted_to_scraperun_before_subprocess_call_returns(session):
    """Proves the actual guarantee that matters: the checkpoint must be
    committed to the database WHILE the council subprocess is still
    running, not only after run_one_council finishes - since a container-
    level OOM (the observed real failure mode, confirmed directly from
    production ScrapeRun evidence: 3/3 latest runs left the in-flight
    council's own ScrapeRun.detail entirely None) kills the whole process
    before any end-of-run code ever executes. Queries the SAME session
    independently, from inside the fake subprocess itself, before
    run_one_council has had any chance to return - this is the only way
    to prove a mid-flight commit without literally killing the test
    process."""
    from scripts.run_daily_councils import run_one_council

    observed_detail = {}

    def _fake(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        on_line("[mem] council=testcouncil stage=chromium.launched self=250MiB children=300MiB total=550MiB")
        # Independent read - proves the write already landed in the DB,
        # not just held in a Python variable inside run_one_council.
        row = session.query(ScrapeRun).filter_by(council_code="testcouncil", status="running").one()
        observed_detail["mid_flight"] = row.detail
        return 0

    with patch("scripts.run_daily_councils._run_council_subprocess", side_effect=_fake):
        run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="scheduled")

    assert observed_detail["mid_flight"] == (
        "[mem] council=testcouncil stage=chromium.launched self=250MiB children=300MiB total=550MiB"
    )


def test_mem_warning_line_is_also_persisted_as_a_checkpoint(session):
    from scripts.run_daily_councils import run_one_council

    observed_detail = {}

    def _fake(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        on_line(
            "[mem-warning] council=testcouncil stage=stage_documents.after total=1800MiB "
            "exceeds 1536MiB warning threshold"
        )
        row = session.query(ScrapeRun).filter_by(council_code="testcouncil", status="running").one()
        observed_detail["mid_flight"] = row.detail
        return 0

    with patch("scripts.run_daily_councils._run_council_subprocess", side_effect=_fake):
        run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="scheduled")

    assert observed_detail["mid_flight"].startswith("[mem-warning]")


def test_non_mem_lines_do_not_trigger_a_mid_flight_checkpoint_write(session):
    """Only [mem]/[mem-warning] prefixed lines should cause an extra
    commit - ordinary scraping output (which can include portal-derived
    text) must not be persisted early via this path; it still reaches
    ScrapeRun.detail normally through the existing end-of-run write."""
    from scripts.run_daily_councils import run_one_council

    observed_detail = {}

    def _fake(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        on_line("[scrape] testcouncil 01/08/2026 -> 10/08/2026")
        row = session.query(ScrapeRun).filter_by(council_code="testcouncil", status="running").one()
        observed_detail["mid_flight"] = row.detail
        return 0

    with patch("scripts.run_daily_councils._run_council_subprocess", side_effect=_fake):
        run = run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="scheduled")

    assert observed_detail["mid_flight"] is None  # no checkpoint write for a non-[mem] line
    assert "[scrape] testcouncil" in run.detail  # still captured normally at the end


def test_persisted_checkpoint_is_bounded_to_4000_chars(session):
    from scripts.run_daily_councils import run_one_council

    observed_detail = {}
    huge_mem_line = "[mem] council=testcouncil stage=x " + ("a" * 5000)

    def _fake(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        on_line(huge_mem_line)
        row = session.query(ScrapeRun).filter_by(council_code="testcouncil", status="running").one()
        observed_detail["mid_flight"] = row.detail
        return 0

    with patch("scripts.run_daily_councils._run_council_subprocess", side_effect=_fake):
        run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="scheduled")

    assert len(observed_detail["mid_flight"]) == 4000


def test_persisted_checkpoint_contains_no_secrets(session):
    """log_memory() itself never emits secrets (see
    tests/test_render_daily_discovery_memory_instrumentation.py), but this
    asserts the persistence path adds nothing extra - the exact same line
    that was streamed is what lands in the database, no env/context
    enrichment along the way."""
    from scripts.run_daily_councils import run_one_council

    observed_detail = {}

    def _fake(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        on_line("[mem] council=testcouncil stage=bootstrap.after self=240MiB children=0MiB total=240MiB")
        row = session.query(ScrapeRun).filter_by(council_code="testcouncil", status="running").one()
        observed_detail["mid_flight"] = row.detail
        return 0

    with patch("scripts.run_daily_councils._run_council_subprocess", side_effect=_fake):
        run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="scheduled")

    detail = observed_detail["mid_flight"]
    assert "DATABASE_URL" not in detail
    assert "API_KEY" not in detail
    assert "postgres://" not in detail


def test_normal_completion_still_ends_with_the_full_bounded_tail(session):
    """The mid-flight checkpoint must not interfere with the existing,
    already-tested end-of-run behaviour on a normal (non-OOM) completion -
    the FINAL ScrapeRun.detail is still the full bounded output tail, not
    left stuck on whichever [mem] line happened to stream last."""
    from scripts.run_daily_councils import run_one_council

    def _fake(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        on_line("[mem] council=testcouncil stage=process.start self=220MiB children=0MiB total=220MiB")
        on_line("[scrape] testcouncil 01/08/2026 -> 10/08/2026")
        on_line("[scrape] 5 applications checked, 1 qualify")
        return 0

    with patch("scripts.run_daily_councils._run_council_subprocess", side_effect=_fake):
        run = run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="scheduled")

    assert run.status == "success"
    assert "[scrape] testcouncil" in run.detail
    assert "5 applications checked" in run.detail


# --- Part 9: config drift (Starter vs Standard) -----------------------------


def test_render_yaml_daily_scrape_plan_is_standard_not_starter():
    """The exact operational defect the diagnosis was asked to check for:
    render.yaml declaring "starter" (512Mi) for propertyaigent-daily-
    scrape despite production having genuinely run on Standard/2Gi for
    weeks - any future "Sync Blueprint" would silently revert the live
    service back to 512Mi, making an OOM kill MORE likely, not less."""
    config = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    discovery = next(s for s in config["services"] if s["name"] == "propertyaigent-daily-scrape")
    assert discovery["plan"] == "standard"


def test_render_yaml_intelligence_processing_plan_unchanged():
    """Part 9 explicitly: do not change Intelligence Processing unless
    separately justified - no evidence here concerns that job."""
    config = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    intelligence = next(s for s in config["services"] if s["name"] == "propertyaigent-intelligence-processing")
    assert intelligence["plan"] == "starter"


# --- Part 10: exactly one Daily Discovery cron ------------------------------


def test_exactly_one_daily_discovery_cron_service_exists():
    config = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    matches = [s for s in config["services"] if s.get("name") == "propertyaigent-daily-scrape"]
    assert len(matches) == 1


def test_daily_discovery_schedule_is_05_00_utc():
    """The intended schedule (05:00 UTC, i.e. 06:00 BST during British
    Summer Time, matching the Aug 11 06:00 local-time production event
    exactly) - confirms no accidental schedule drift and no duplicate
    cron at a different time."""
    config = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    discovery = next(s for s in config["services"] if s["name"] == "propertyaigent-daily-scrape")
    assert discovery["schedule"] == "0 5 * * *"


# --- Preserved behaviour (Part 13) ------------------------------------------


def test_run_daily_councils_still_defaults_to_ai_free_after_this_change(session):
    from scripts.run_daily_councils import run_one_council

    captured_commands = []

    def _fake(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        captured_commands.append(command)
        return 0

    with patch("scripts.run_daily_councils._run_council_subprocess", side_effect=_fake):
        run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="scheduled")

    assert "--skip-extraction" in captured_commands[0]
    assert "--skip-scheme-summary" in captured_commands[0]


def test_scraperun_applications_before_after_still_recorded(session):
    """Confirms ordinary ScrapeRun bookkeeping (unrelated to the
    checkpoint change) is unaffected."""
    from scripts.run_daily_councils import run_one_council

    session.add(Application(council_code="testcouncil", reference="APP/1"))
    session.commit()

    def _fake(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        return 0

    with patch("scripts.run_daily_councils._run_council_subprocess", side_effect=_fake):
        run = run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="scheduled")

    assert run.applications_before == 1
    assert run.applications_after == 1
