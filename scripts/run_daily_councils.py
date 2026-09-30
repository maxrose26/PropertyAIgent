"""Daily discovery supervisor (specification 019).

One owned invocation runs councils in least-recently-started order. Each council
uses the existing run_weekly pipeline in a separately supervised process group.
Count/time/memory limits contain exposure; they are not a proven OOM root-cause
fix. Supporting partial coverage preserves exit 0; process failure, missing
final health, and unattempted selected councils yield nonzero. Production is
fail-closed pending separately approved runtime/migration/trial gates.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
import threading
import queue
import time
import json
import signal
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


# Render Daily Discovery Portal Resilience & Truthful Run Health, Part 4:
# matches app.pipeline.run_weekly's own [run-health] summary line (see
# app.pipeline.acquisition_health's own docstring) - deliberately a
# narrow, anchored pattern on a fixed "status=" field, never scraping
# arbitrary human-readable log text for classification.
_RUN_HEALTH_STATUS_RE = re.compile(r"^\[run-health\] status=(success|partial|failed)\b")


def _parse_run_health_status(line: str) -> str | None:
    match = _RUN_HEALTH_STATUS_RE.match(line)
    return match.group(1) if match else None


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
            os.killpg(process.pid, 9)
        except ProcessLookupError:
            pass  # already gone between the timeout firing and us getting here - fine
    else:
        process.kill()


class MemoryContainment(RuntimeError):
    pass


def _run_council_subprocess(
    command: list[str], *, cwd: Path, timeout_seconds: int, on_line=None,
    council_code: str | None = None, owner=None, run_id=None, on_start=None,
) -> int:
    """Bounded stream and process-group supervision, including silent children.

    A bounded reader queue avoids blocking the supervisor on a child's partial
    line. An independent invocation watchdog covers stalled DB callbacks. The inherited lock
    remains held by a child after supervisor death.
    """
    from app.diagnostics.memory import cgroup_memory
    started = time.monotonic()
    watchdog = getattr(owner, 'watchdog', None)
    deadline = min(started + timeout_seconds, watchdog.deadline) if watchdog else started + timeout_seconds
    if started >= deadline:
        raise subprocess.TimeoutExpired(command, timeout_seconds)
    kwargs = {'start_new_session': True} if os.name == 'posix' else {}
    if owner is not None:
        kwargs.update(env=owner.child_environment(run_id), pass_fds=(owner.fd,))
    gate_read = gate_write = None
    launch = command
    if watchdog is not None:
        gate_read, gate_write = os.pipe()
        kwargs['pass_fds'] = (*kwargs.get('pass_fds', ()), gate_read)
        launch = [sys.executable, '-m', 'app.pipeline.discovery_watchdog', 'gate',
                  str(gate_read), str(deadline), *command]
    try:
        process = subprocess.Popen(launch, cwd=cwd, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1, **kwargs)
    except BaseException:
        if gate_write is not None: os.close(gate_write)
        raise
    finally:
        if gate_read is not None: os.close(gate_read)
    messages = queue.Queue(maxsize=100)
    stopped = threading.Event()
    parent_deadline = None
    parent_seen = False
    reader_error = []
    dropped_lines = [0]

    def reader():
        nonlocal parent_deadline, parent_seen
        try:
            while not stopped.is_set():
                line = process.stdout.readline(16384)
                if not line: break
                # Budget control must not wait behind a blocked DB/log callback.
                if not parent_seen and re.search(r'\bstage=stage_fetch_missing_parents\.before\b', line):
                    from app.pipeline.parent_lookup import positive_limit
                    parent_seen = True
                    stamp = re.search(r'\bparent_started=([0-9.]+)', line)
                    parent_start = min(time.monotonic(), float(stamp[1])) if stamp else time.monotonic()
                    from app.pipeline.discovery_watchdog import parent_deadlines
                    parent_deadline, parent_hard_stop = parent_deadlines(parent_start,
                        positive_limit('PARENT_SECONDS', 180), deadline,
                        watchdog.deadline if watchdog else deadline + 20)
                    if watchdog is not None:
                        watchdog.register(process.pid, parent_hard_stop)
                elif parent_deadline is not None and re.search(r'\bstage=stage_fetch_missing_parents\.after\b', line):
                    # A late after-message cannot turn an expired stage into success.
                    if time.monotonic() < parent_deadline:
                        parent_deadline = None
                        if watchdog is not None: watchdog.register(process.pid, deadline + 20)
                try: messages.put_nowait(line.rstrip('\n'))
                except queue.Full: dropped_lines[0] += 1
        except BaseException as exc:
            reader_error.append(exc)
            _kill_process_tree(process)
        finally:
            while not stopped.is_set():
                try:
                    messages.put(None, timeout=.1)
                    break
                except queue.Full: pass

    thread = threading.Thread(target=reader, daemon=True)
    peak, next_sample, next_report = 0, 0, 0
    reason = None
    try:
        if watchdog is not None:
            watchdog.register(process.pid, deadline + 20)
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(command, timeout_seconds)
            os.write(gate_write, b'!')
            os.close(gate_write)
            gate_write = None
        thread.start()
        if on_start: on_start(process.pid)
        eof = False
        while not eof or process.poll() is None:
            now = time.monotonic()
            if parent_deadline is not None and now >= parent_deadline:
                reason = 'parent_envelope'
                break
            if now >= deadline:
                reason = 'timeout'
                break
            if now >= next_sample:
                memory = cgroup_memory()
                next_sample = now + 2
                if memory:
                    peak = max(peak, memory[0])
                    if memory[0] / memory[1] >= .80:
                        reason = 'hard_memory'
                        break
                if now >= next_report:
                    if on_line:
                        on_line('[discovery-progress] ' + json.dumps({'memory': {
                            'current_bytes': memory[0] if memory else None,
                            'limit_bytes': memory[1] if memory else None,
                            'peak_bytes': peak or None, 'available': memory is not None}}))
                    next_report = now + 30
            try:
                line = messages.get(timeout=min(.2, max(.001, deadline-now)))
                if line is None: eof = True
                else:
                    if on_line: on_line(line)
            except queue.Empty: pass
        if reason:
            if os.name == 'posix':
                try: os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError: pass
            else: process.terminate()
            try: process.wait(timeout=5 if reason in ('hard_memory', 'parent_envelope') else 15)
            except subprocess.TimeoutExpired: pass
            _kill_process_tree(process)
            process.wait(timeout=5)
            if reason == 'hard_memory': raise MemoryContainment('cgroup hard threshold')
            if reason == 'parent_envelope': raise RuntimeError('parent stage stop envelope exhausted')
            raise subprocess.TimeoutExpired(command, timeout_seconds)
        if reader_error: raise RuntimeError('discovery control reader failed') from reader_error[0]
        if dropped_lines[0]:
            raise RuntimeError(f'discovery progress incomplete: {dropped_lines[0]} streamed lines dropped')
        return process.wait()
    finally:
        if gate_write is not None: os.close(gate_write)
        # Includes callback/DB errors and successful child exit with surviving
        # browser descendants. Group id remains child pid after leader exit.
        if os.name == 'posix':
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        elif process.poll() is None: process.kill()
        process.wait(timeout=5)
        stopped.set()
        if thread.ident is not None: thread.join(timeout=2)
        process.stdout.close()
        if watchdog is not None:
            watchdog.unregister(process.pid)


def run_one_council(
    session, council_code: str, *, timeout_seconds: int, triggered_by: str, include_ai_stages: bool = False, owner=None,
) -> ScrapeRun:
    applications_before = _application_count(session, council_code)

    run = ScrapeRun(council_code=council_code, status="running", triggered_by=triggered_by)
    progress = {'version': 1, 'scope': {'council': council_code, 'period': 'current_month'},
                'owner': dict(owner.identity) if owner else None}
    progress['limits'] = {**(getattr(owner, 'limits', {}) if owner else {}), 'effective_council_seconds': timeout_seconds}
    run.progress = json.dumps(progress)
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
    # Render Daily Discovery Portal Resilience & Truthful Run Health, Part
    # 4/5 - the council subprocess's own materiality assessment (success/
    # partial/failed), captured from its [run-health] line as it streams.
    # A plain dict (not a bare local) because _on_line is a nested closure
    # that needs to WRITE this, not just read it. None until/unless that
    # line is actually seen - see the classification logic below this
    # subprocess call for what happens if it never is.
    run_health: dict[str, str | None] = {"status": None}
    stage_starts = {}
    last_memory_commit = [float("-inf")]

    def _on_line(line: str) -> None:
        # flush=True (Render Daily Discovery missing-runtime-logs diagnosis,
        # "Do not rely on only one fragile buffering assumption") - this
        # process is now launched with -u and PYTHONUNBUFFERED=1 (see
        # render.yaml), but a live-streamed line surviving an OOM SIGKILL
        # is important enough not to depend on external configuration
        # alone staying correct.
        print(f"[{council_code}] {line}", flush=True)
        tail_lines.append(line[:16384])
        if line.startswith('[discovery-progress] '):
            progress.update(json.loads(line[len('[discovery-progress] '):]))
            progress['heartbeat_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
            run.progress = json.dumps(progress)
            session.commit()
        if line.startswith("[mem]") or line.startswith("[mem-warning]"):
            # Stage transitions are durable immediately. Routine per-item
            # memory diagnostics remain in logs; DB checkpoint at most every 30s.
            stage_match = re.search(r'\bstage=(stage_[\w]+)\.(before|after)\b', line)
            if stage_match:
                stage, boundary = stage_match.groups()
                stages = progress.setdefault('stages', {})
                entry = stages.setdefault(stage, {})
                entry[boundary + '_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
                if boundary == 'before':
                    stage_starts[stage] = time.monotonic()
                    entry['status'] = 'running'
                else:
                    entry['status'] = 'returned'  # not proof every item succeeded
                    if stage in stage_starts:
                        entry['duration_seconds'] = round(time.monotonic()-stage_starts[stage], 3)
                run.progress = json.dumps(progress)
            if stage_match or time.monotonic() - last_memory_commit[0] >= 30:
                run.detail = line[:4000]
                session.commit()
                last_memory_commit[0] = time.monotonic()
        else:
            # Render Daily Discovery Portal Resilience & Truthful Run
            # Health, Part 4 - captured the same way as [mem] lines
            # above, but classification is read at the end (not
            # committed live) since it's only meaningful once the whole
            # run has actually finished; the [mem] checkpoint above
            # already covers OOM-survival for the "what was happening"
            # question.
            status = _parse_run_health_status(line)
            if status is not None:
                run_health["status"] = status

    def _on_start(pid):
        from app.pipeline.discovery_owner import process_identity
        if progress['owner']:
            progress['owner'].update(child_pid=pid, child_start=process_identity(pid))
        run.progress = json.dumps(progress)
        session.commit()

    return_code = None
    try:
        return_code = _run_council_subprocess(
            command, cwd=PROJECT_ROOT, timeout_seconds=timeout_seconds, on_line=_on_line, council_code=council_code,
            owner=owner, run_id=run.id, on_start=_on_start,
        )
        crashed = return_code != 0
        # Council-level failure isolation lives here: a non-zero exit code
        # is recorded and reported, never re-raised - the loop in main()
        # always proceeds to the next council regardless.
    except subprocess.TimeoutExpired:
        crashed = True
        tail_lines.append(f"Timed out after {timeout_seconds}s.")
    except Exception as e:  # noqa: BLE001 - genuinely must never take the loop down
        crashed = True
        tail_lines.append(f"Orchestrator error managing subprocess: {e}")

    # A clean process exit without its final coverage assessment is unknown,
    # not success. Preserve partial coverage separately from process health.
    if crashed:
        run.status = "failed"
    else:
        run.status = run_health["status"] or "partial"

    log_memory("council.after", council=council_code)

    combined_output = "\n".join(tail_lines)
    applications_after = _application_count(session, council_code)
    discovered = applications_after - applications_before

    for entry in progress.get('stages', {}).values():
        if entry['status'] == 'running': entry['status'] = 'interrupted_or_completion_unverified'
    progress['process_failure'] = bool(crashed or run_health['status'] is None)
    progress['final_health_received'] = run_health['status'] is not None
    run.progress = json.dumps(progress)
    run.finished_at = dt.datetime.now(dt.timezone.utc)
    # run.status already set above (Part 4/5/7) - success/partial/failed,
    # not the old binary success/failed.
    run.applications_before = applications_before
    run.applications_after = applications_after
    run.applications_discovered = discovered
    run.detail = combined_output[-4000:]  # bounded twice over - a bounded LINE ring buffer, then a bounded CHAR tail
    session.commit()

    from app.pipeline.discovery_owner import release_interrupted_work
    release_interrupted_work(session, run.id)

    # Render Daily Discovery Portal Resilience & Truthful Run Health, Part
    # 4/5/7 - reported from run.status, NOT the earlier crash-only
    # `success` boolean: a clean exit (success=True in the old sense) with
    # a materially failed primary scrape (the confirmed Trafford scenario)
    # must NOT print "OK" - that was exactly the misleading behaviour this
    # work exists to fix, and printing from the old boolean here would
    # have silently reintroduced it even after the DB-side fix above.
    if run.status == "success":
        print(f"[run-daily-councils] {council_code}: OK ({discovered:+d} applications)", flush=True)
    elif run.status == "partial":
        # Still a materially useful run (primary scrape completed) - not
        # printed as FAILED, and does not affect the overall Cron exit
        # code (Part 7), but visibly distinct from a clean OK so an
        # operator scanning Render's log viewer doesn't miss it.
        print(
            f"[run-daily-councils] {council_code}: PARTIAL ({discovered:+d} applications) "
            "- some supporting acquisition failed, see ScrapeRun.detail",
            flush=True,
        )
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
    started = time.monotonic()
    from app.pipeline.discovery_owner import DiscoveryOwner, reconcile_owners
    from app.pipeline.parent_lookup import positive_limit
    from app.diagnostics.memory import cgroup_memory
    args = parse_args()
    from app.pipeline.discovery_config import discovery_switches
    switches = discovery_switches()
    if switches['disabled']:
        print('[run-daily-councils] discovery disabled', flush=True)
        return 1
    if args.timeout_seconds <= 0: raise ValueError('council timeout must be positive')
    limits = dict(parent_items=positive_limit('PARENT_ITEMS', 25),
        parent_attempts=positive_limit('PARENT_ATTEMPTS', 30),
        parent_seconds=positive_limit('PARENT_SECONDS', 180),
        invocation_seconds=positive_limit('INVOCATION_SECONDS', 9000),
        council_seconds=args.timeout_seconds, lookup_seconds=60,
        soft_memory_ratio=.70, stop_memory_ratio=.80, restart_memory_ratio=.60)
    from app.pipeline.discovery_watchdog import DiscoveryWatchdog
    from app.db.session import configure_discovery_database_bounds
    deadline = started + limits['invocation_seconds']
    with DiscoveryWatchdog(deadline) as watchdog, DiscoveryOwner() as owner:
        owner.watchdog = watchdog
        configure_discovery_database_bounds()
        owner.limits = limits
        print('[discovery-config] ' + json.dumps({'switches': switches, 'limits': limits}), flush=True)
        log_memory('orchestrator.start')
        init_db()
        session = get_session()
        try:
            reconcile_owners(session, owner)
            codes = args.councils or sorted(load_councils().keys())
            history = dict(session.execute(select(ScrapeRun.council_code,
                func.max(ScrapeRun.started_at)).group_by(ScrapeRun.council_code)).all())
            codes = sorted(set(codes), key=lambda code: ((history[code].replace(tzinfo=dt.timezone.utc).timestamp() if history.get(code) else float('-inf')), code))
            owner.identity['council_order'] = codes
            results = []
            deferred = []
            for index, code in enumerate(codes):
                memory = cgroup_memory()
                if time.monotonic() >= deadline or (memory and memory[0]/memory[1] >= .60):
                    deferred = codes[index:]
                    break
                try:
                    results.append(run_one_council(session, code,
                        timeout_seconds=min(args.timeout_seconds, max(1, int(deadline-time.monotonic()))),
                        triggered_by=args.triggered_by, include_ai_stages=args.include_ai_stages, owner=owner))
                except Exception as exc:
                    session.rollback()
                    print(f'[run-daily-councils] {code}: bookkeeping failure {type(exc).__name__}', flush=True)
            if deferred:
                print('[discovery-progress] ' + json.dumps({'deferred_councils': deferred}), flush=True)
                if results:
                    progress = json.loads(results[-1].progress or '{}')
                    progress['deferred_councils'] = deferred
                    results[-1].progress = json.dumps(progress)
                    session.commit()
            healthy = sum(r.status in ('success', 'partial') and not
                json.loads(r.progress or '{}').get('process_failure', True) for r in results)
            print(f"[run-daily-councils] {sum(r.status == 'success' for r in results)} success, {sum(r.status == 'partial' for r in results)} partial, {sum(r.status == 'failed' for r in results)} failed, {len(results)} attempted", flush=True)
            print(f'[run-daily-councils] completed={len(results)} selected={len(codes)} deferred={len(deferred)}', flush=True)
            return _exit_code(healthy=healthy, attempted=len(codes))
        finally:
            session.close()


def _exit_code(*, healthy: int, attempted: int) -> int:
    """Exit status policy (Render Daily Discovery runtime failure hotfix,
    updated by Portal Resilience & Truthful Run Health Part 7): every
    council attempted must be either "success" or "partial" for a 0 exit -
    "partial" counts as HEALTHY for Render's own Cron exit-code purposes
    (approved policy: "PARTIAL: should still count as a successful Render
    Cron execution / exit 0... Render infrastructure health and Property
    AIgent data-quality health are separate concepts" - the [run-health]-
    derived ScrapeRun.status already carries the truthful distinction;
    this exit code is only about "did the Cron Job itself need operator
    attention"). Only a genuinely FAILED council (subprocess crash/
    timeout/non-zero exit, OR a materially failed primary scrape) trips
    the overall exit code. `attempted` (not healthy + explicitly-failed)
    is still the comparison base deliberately: an orchestrator-level
    bookkeeping error that skipped a council entirely (never reaching
    run_one_council's own try/except, so never becoming a recorded
    ScrapeRun at all) is just as unhealthy a run and must not be silently
    invisible to this policy. Factored out as its own pure function (no
    DB/session access) so the policy itself is directly unit-testable
    without touching a real database - main() is the only caller."""
    if healthy == attempted:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
