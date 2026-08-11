"""Daily multi-council Planning Application scraper orchestrator (Pilot
Readiness PR-2, "Production Scheduling"). This is the production entry
point Render's Cron Job (see render.yaml) invokes once a day.

Reuses the existing per-council pipeline entry point UNCHANGED - each
council is run as its own subprocess of

    python -m app.pipeline.run_weekly --council <code>

exactly the command scripts/register_weekly_task.ps1 already registers
locally, just invoked here in a loop across every council instead of one
Windows Task Scheduler job per council. No scraping/extraction/matching
business logic is duplicated or reimplemented here - this script is
orchestration only.

Failure isolation (Part 5: "A failed council should not silently prevent
the remaining councils from updating"): each council's subprocess failing
(non-zero exit code, timeout, or an exception raised while managing it)
is caught and recorded, and the loop always continues to the next council.
A subprocess boundary is used deliberately, not an in-process function
call - Playwright/browser and OpenAI SDK state from one council's run
cannot leak into or destabilise the next council's run this way, a
stronger isolation guarantee than a shared-process try/except would give.

Observability (Part 6): before and after each council's subprocess, this
script counts that council's Application rows directly (no change to
run_weekly.py needed to get this) and writes one app.db.models.ScrapeRun
row per attempt - see app.reporting.scraper_health for how Council
Operations reads this back.

Incremental by design (Part 3/5): invoked with no extra date-range flags,
run_weekly.py's own default ("Default weekly cadence: just the current
month") already bounds each daily run to a small, upsert-idempotent
window - never a historical re-scrape. Running this daily instead of
weekly does not change that default; it just checks it more often.

AI cost safety (Pilot Readiness PR-2 pre-merge architecture check, "Daily
Pipeline / AI Cost Safety"): run_weekly.py's own stage_extraction and
stage_generate_scheme_summaries are each individually well-gated (the
former only processes an Application with no scheme_intelligence row yet;
the latter only regenerates a Site's summary when a newer Application has
been linked since the last one) - genuinely incremental once a steady
state is reached, not a blind re-run. But main() invokes BOTH
unconditionally by default, with no orchestrator-level control, and BOTH
raise immediately if OPENAI_API_KEY is unset - meaning this daily cron, if
simply pointed at the existing entry point unmodified, would (a) require
OPENAI_API_KEY to exist at all just to run scraping/document-discovery,
and (b) on its very first-ever production run, potentially attempt AI
extraction across however large an already-accumulated backlog of
never-extracted qualifying Applications happens to exist, all in one
subprocess invocation, with no operator visibility into that cost before
it happens. Neither is a redesign of the extraction architecture (both
stages' own gating is correct and untouched) - it is purely a question of
whether the DAILY SCHEDULED job should include them by default. It should
not: this script defaults to `--skip-extraction --skip-scheme-summary` on
every subprocess invocation (a flag run_weekly.py already exposes - no
change to that file was needed), so the scheduled daily job is
deterministic discovery/document-collection/site-linking ONLY, and does
not require OPENAI_API_KEY. Pass --include-ai-stages to opt a specific
invocation IN to extraction/summary generation as well (e.g. for a
manually-triggered catch-up run once an operator has reviewed how large
the current backlog is).

    python -m scripts.run_daily_councils [--council CODE ...] [--timeout-seconds N] [--include-ai-stages]

Process exit status (Render Daily Discovery runtime failure hotfix):
main() now returns a real exit code reflecting overall run health, instead
of always exiting 0 regardless of how many councils failed - a production
run that failed all 10 councils was previously still reported by Render as
"Cron job run finished successfully", since the process fell off the end
of main() with no explicit exit code at all (Python's default is 0).
Policy (Product Owner, pilot readiness): ANY council failing marks the
whole Cron Job run unhealthy - exit 0 only when every attempted council
succeeded, exit 1 otherwise (whether some or all councils failed). An
incomplete Greater Manchester refresh needs operator attention regardless
of how many councils were affected; Render's own monitoring/alerting can
only reflect that if the process exit code says so. This does not change
failure isolation - every council is still attempted regardless of
earlier failures; only the FINAL exit code changes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
import threading
from collections import deque
from pathlib import Path

from sqlalchemy import func, select

from app.config import load_councils
from app.db.models import Application, ScrapeRun
from app.db.session import get_session, init_db
from app.diagnostics.memory import log_memory

# Bounded ring buffer size for one council's streamed output - generous
# relative to a normal run's real line counts (the earlier production
# incident's own successful councils logged roughly 15-70 lines each; see
# this module's own docstring, "Streamed, bounded subprocess output") -
# while still guaranteeing the buffer itself can never grow unbounded
# regardless of how verbose a pathological run becomes.
_OUTPUT_TAIL_MAX_LINES = 200

_ERROR_LINE_PATTERN = re.compile(r"^\s*[\w.]*(?:Error|Exception)\s*:.*$", re.MULTILINE)


def _summarize_error(text: str) -> str:
    """Pulls the most informative single line out of a subprocess's
    captured stdout+stderr for the concise, actionable Render-log line
    (Render Daily Discovery runtime failure hotfix, "a failed council
    should emit a concise but actionable error line"). Prefers the LAST
    Python `SomeError: message`/`SomeException: message` line (a
    traceback's own final line is always the actual exception - matches
    even library-raised errors like playwright._impl._errors.Error:...),
    since some tools (Playwright's own CLI) print extra explanatory text
    AFTER the real exception line, which a naive "last non-blank line"
    would pick up instead. Falls back to the last non-blank line if no
    such pattern is found. Never touches os.environ - only summarizes text
    the subprocess itself already printed, so this cannot surface a secret
    that wasn't already in that output."""
    matches = _ERROR_LINE_PATTERN.findall(text)
    if matches:
        return matches[-1].strip()
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-1].strip() if lines else "(no output captured)"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TIMEOUT_SECONDS = 3600  # 1 hour per council - generous; a genuinely stuck run should not block the next council forever


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--council", action="append", dest="councils",
        help="Council code to run (repeatable). Default: every council in config/councils.yaml.",
    )
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--triggered-by", default="scheduled", choices=["scheduled", "manual"],
        help="Recorded on each ScrapeRun row - 'manual' for an operator-triggered re-run, distinct from the daily schedule.",
    )
    parser.add_argument(
        "--include-ai-stages", action="store_true",
        help=(
            "Also run run_weekly.py's AI extraction and scheme-summary stages for each council "
            "(requires OPENAI_API_KEY). Off by default - see this module's own docstring for why."
        ),
    )
    return parser.parse_args()


def _application_count(session, council_code: str) -> int:
    return session.execute(
        select(func.count(Application.id)).where(Application.council_code == council_code)
    ).scalar()


def _kill_process_tree(process: subprocess.Popen) -> None:
    """Kills the WHOLE process group a child was started in (POSIX), not
    just the one tracked PID - see _run_council_subprocess's own docstring
    for why this matters (an orphaned Playwright-driver-plus-Chromium tree
    otherwise). Windows has no process-group equivalent; falls back to
    killing just the tracked PID there (production/Render is POSIX; this
    repo's own local dev happens to run on Windows)."""
    if os.name == "posix":
        try:
            # 9 == SIGKILL's POSIX-standard value, used as a portable literal
            # rather than signal.SIGKILL - the `signal` module's Windows
            # build has no SIGKILL attribute at all, which would break even
            # importing this module cleanly under test on this repo's own
            # Windows dev environment (this branch never actually runs on
            # Windows in production - os.name is always "posix" there).
            os.killpg(os.getpgid(process.pid), 9)
        except ProcessLookupError:
            pass  # already gone between the timeout firing and us getting here - fine
    else:
        process.kill()


def _run_council_subprocess(
    command: list[str], *, cwd: Path, timeout_seconds: int, on_line=None, council_code: str | None = None,
) -> int:
    """Runs one council's subprocess with STREAMED, bounded output instead
    of subprocess.run(..., capture_output=True)'s "buffer everything, only
    look at it once the child exits" model (Render Daily Discovery memory
    instrumentation & architecture diagnosis).

    Two production failures (Starter/512Mi, then Standard/2Gi) both ended
    in a container-level OOM kill of the WHOLE process tree, including the
    orchestrator itself. Reconstructing the timeline afterwards from
    ScrapeRun rows found the council that was actually running at the
    moment of death had NO detail recorded at all (status stuck at
    "running", detail=None) - because the old design only ever wrote
    ScrapeRun.detail from the fully-buffered captured output AFTER
    subprocess.run() returned, which never happened once the orchestrator
    itself was killed. Whatever that council had already printed was
    sitting entirely inside a Python string buffer nobody had looked at
    yet - genuinely lost, not just hard to find.

    Fixed by streaming: each line the child prints is read and handed to
    `on_line` (the caller's own responsibility - run_one_council both
    re-prints it to THIS process's own stdout, which Render's log capture
    receives continuously and independently of whether this process is
    later OOM-killed, AND appends it to a small bounded ring buffer for
    ScrapeRun.detail) as it arrives, not buffered until the end. This also
    directly answers Part 5's "does capture_output pose a real memory
    risk": yes, unbounded buffering of a real (not blank-page) council's
    full output is a genuine, if secondary, contributor - streaming with a
    bounded ring buffer caps it regardless of how verbose a run becomes.

    Kills the child's WHOLE PROCESS GROUP on timeout (POSIX), not just the
    one tracked PID - unchanged reasoning from the prior hotfix, just
    factored into _kill_process_tree so the streaming redesign didn't need
    to duplicate it. Returns the child's own exit code; raises
    subprocess.TimeoutExpired (no output/stderr payload - the caller
    already received every line via on_line as it streamed) on timeout."""
    stdout_kwargs = {"start_new_session": True} if os.name == "posix" else {}
    process = subprocess.Popen(
        command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, **stdout_kwargs,
    )
    # "Immediately after council subprocess starts" (Render Daily Discovery
    # memory instrumentation orchestrator boundary) - measures the CHILD's
    # own OS-level footprint by pid from the parent's side, distinct from
    # run_weekly.py's own self-measurement of the SAME process from inside.
    log_memory("council.subprocess_started", council=council_code, pid=process.pid)

    timed_out = threading.Event()

    def _on_timeout() -> None:
        timed_out.set()
        _kill_process_tree(process)

    timer = threading.Timer(timeout_seconds, _on_timeout)
    timer.start()
    try:
        assert process.stdout is not None
        for line in process.stdout:
            if on_line is not None:
                on_line(line.rstrip("\n"))
        process.wait()
    finally:
        timer.cancel()

    if timed_out.is_set():
        raise subprocess.TimeoutExpired(command, timeout_seconds)
    return process.returncode


def run_one_council(
    session, council_code: str, *, timeout_seconds: int, triggered_by: str, include_ai_stages: bool = False,
) -> ScrapeRun:
    applications_before = _application_count(session, council_code)

    run = ScrapeRun(council_code=council_code, status="running", triggered_by=triggered_by)
    session.add(run)
    session.commit()

    print(f"\n[run-daily-councils] {council_code}: starting (ScrapeRun id={run.id})", flush=True)
    log_memory("council.before", council=council_code)

    # -u (unbuffered stdout/stderr) is required for the streaming design
    # below to actually stream in real time - without it, CPython
    # block-buffers stdout whenever it isn't connected to a real terminal
    # (i.e. always, when piped from a subprocess), so a child's print()
    # calls could sit unflushed in ITS OWN internal buffer for a long time
    # rather than reaching this parent process line-by-line as issued -
    # confirmed locally: a child that printed then slept produced NO
    # output on the parent's side until the buffer was force-flushed by
    # the child exiting. Without -u, the whole point of streaming (Render's
    # live log capture seeing progress in real time, and surviving even if
    # THIS process is later OOM-killed) would be silently defeated.
    command = [sys.executable, "-u", "-m", "app.pipeline.run_weekly", "--council", council_code]
    if not include_ai_stages:
        # See this module's own docstring ("AI cost safety") - the daily
        # schedule is deterministic discovery/documents only by default;
        # run_weekly.py already exposes these two flags, nothing new added
        # to that file.
        command += ["--skip-extraction", "--skip-scheme-summary"]

    # Bounded ring buffer, not the full captured output (Render Daily
    # Discovery memory instrumentation - see _run_council_subprocess's own
    # docstring). Each line is ALSO re-printed to this process's own
    # stdout as it streams in, prefixed with the council code, so Render's
    # own log capture receives it live and independently of whether this
    # orchestrator process later dies before ever reaching the code below
    # that would otherwise be the only thing writing it anywhere.
    tail_lines: deque[str] = deque(maxlen=_OUTPUT_TAIL_MAX_LINES)

    def _on_line(line: str) -> None:
        # flush=True (Render Daily Discovery missing-runtime-logs diagnosis,
        # "Do not rely on only one fragile buffering assumption") - this
        # process is now launched with -u and PYTHONUNBUFFERED=1 (see
        # render.yaml), but a live-streamed line surviving an OOM SIGKILL
        # is important enough not to depend on external configuration
        # alone staying correct.
        print(f"[{council_code}] {line}", flush=True)
        tail_lines.append(line)
        if line.startswith("[mem]") or line.startswith("[mem-warning]"):
            # Persisted memory checkpoint (Render Daily Discovery missing-
            # runtime-logs diagnosis, Part 7): Render's live log stream has
            # now proven unreliable enough - by definition a container OOM
            # kill gives Python no chance to flush anything on the way out
            # - that a checkpoint must also survive independently of logs
            # entirely. The end-of-run write below (run.detail =
            # combined_output[-4000:]) is not enough on its own either: it
            # only executes once _run_council_subprocess RETURNS, and a
            # container-level OOM (the observed failure mode - distinct
            # from one council's own subprocess merely timing out) kills
            # the ORCHESTRATOR itself mid-council, so that write never
            # happens. Confirmed directly, not hypothetically: reconstructing
            # the 3 most recent production OOM runs found the in-flight
            # council's own ScrapeRun.detail entirely None every time -
            # exactly this gap, with nothing recoverable after the fact.
            # Fixed by committing the LATEST [mem]/[mem-warning] line as it
            # arrives, reusing the existing column rather than adding a new
            # one (no schema change needed) - overwritten by the final
            # combined_output tail below on any normal completion or
            # recorded failure; this only matters for the OOM case, where
            # that final write never lands. Bounded and cheap: one short
            # line, one commit, only at the small number of explicit stage
            # boundaries a council run passes through (roughly 15-20 over
            # several minutes) - not per application, per document, or per
            # raw subprocess output line.
            run.detail = line[:4000]
            session.commit()

    return_code = None
    try:
        return_code = _run_council_subprocess(
            command, cwd=PROJECT_ROOT, timeout_seconds=timeout_seconds, on_line=_on_line, council_code=council_code,
        )
        success = return_code == 0
        # Council-level failure isolation lives here: a non-zero exit code
        # is recorded and reported, never re-raised - the loop in main()
        # always proceeds to the next council regardless.
    except subprocess.TimeoutExpired:
        success = False
        tail_lines.append(f"Timed out after {timeout_seconds}s.")
    except Exception as e:  # noqa: BLE001 - genuinely must never take the loop down
        success = False
        tail_lines.append(f"Orchestrator error managing subprocess: {e}")

    log_memory("council.after", council=council_code)

    combined_output = "\n".join(tail_lines)
    applications_after = _application_count(session, council_code)
    discovered = applications_after - applications_before

    run.finished_at = dt.datetime.now(dt.timezone.utc)
    run.status = "success" if success else "failed"
    run.applications_before = applications_before
    run.applications_after = applications_after
    run.applications_discovered = discovered
    run.detail = combined_output[-4000:]  # bounded twice over - a bounded LINE ring buffer, then a bounded CHAR tail
    session.commit()

    if success:
        print(f"[run-daily-councils] {council_code}: OK ({discovered:+d} applications)", flush=True)
    else:
        # Concise, actionable line for Render's own log viewer (Render
        # Daily Discovery runtime failure hotfix) - previously only the
        # DB-stored ScrapeRun.detail carried enough information to diagnose
        # a failure; an operator watching Render's live logs saw only
        # "FAILED (+0 applications)" with no indication why. Never prints
        # os.environ or any secret - only summarizes text the subprocess
        # itself already printed to stdout/stderr.
        error_summary = _summarize_error(combined_output)
        print(f"[run-daily-councils] {council_code}: FAILED", flush=True)
        print(f"  return_code={return_code}", flush=True)
        print(f"  error={error_summary}", flush=True)
    return run


def main() -> int:
    args = parse_args()
    # "[mem] orchestrator.start" (Render Daily Discovery missing-runtime-
    # logs diagnosis, Part 6) - deliberately BEFORE init_db()/the council
    # loop, so this line exists even if something in bootstrap itself
    # consumes substantial memory before the first council subprocess is
    # ever spawned. Proves, on the next production run, whether the parent
    # process itself is genuinely emitting/flushing output from the very
    # first line - if this is still missing from Render's log viewer next
    # time, the buffering fix below did not work and the investigation
    # must continue from here, not from some later stage.
    log_memory("orchestrator.start")
    init_db()
    session = get_session()

    council_codes = args.councils or sorted(load_councils().keys())
    print(f"[run-daily-councils] {len(council_codes)} council(s) to run: {', '.join(council_codes)}", flush=True)

    results = []
    for council_code in council_codes:
        try:
            run = run_one_council(
                session, council_code, timeout_seconds=args.timeout_seconds, triggered_by=args.triggered_by,
                include_ai_stages=args.include_ai_stages,
            )
            results.append(run)
        except Exception as e:  # noqa: BLE001 - one council's bookkeeping failure must not stop the rest
            print(f"[run-daily-councils] {council_code}: orchestrator-level error, continuing: {e}", flush=True)

    succeeded = sum(1 for r in results if r.status == "success")
    failed = sum(1 for r in results if r.status == "failed")
    print(
        f"\n[run-daily-councils] Done. {succeeded} succeeded, {failed} failed, {len(council_codes)} attempted.",
        flush=True,
    )

    return _exit_code(succeeded=succeeded, attempted=len(council_codes))


def _exit_code(*, succeeded: int, attempted: int) -> int:
    """Exit status policy (Render Daily Discovery runtime failure hotfix -
    see this module's own docstring, "Process exit status"): every council
    attempted successfully is the only condition that exits 0 - a partial
    or total failure both exit 1. `attempted` (not `succeeded + failed`) is
    the comparison base deliberately: an orchestrator-level bookkeeping
    error that skipped a council entirely (never reaching run_one_council's
    own try/except, so never becoming a recorded "failed" ScrapeRun either)
    is just as unhealthy a run and must not be silently invisible to this
    policy. Factored out as its own pure function (no DB/session access)
    so the policy itself is directly unit-testable without touching a real
    database - main() is the only caller."""
    if succeeded == attempted:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
