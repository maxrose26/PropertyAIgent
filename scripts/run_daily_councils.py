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

    python -m scripts.run_daily_councils [--council CODE ...] [--timeout-seconds N]
"""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

from sqlalchemy import func, select

from app.config import load_councils
from app.db.models import Application, ScrapeRun
from app.db.session import get_session, init_db

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
    return parser.parse_args()


def _application_count(session, council_code: str) -> int:
    return session.execute(
        select(func.count(Application.id)).where(Application.council_code == council_code)
    ).scalar()


def run_one_council(session, council_code: str, *, timeout_seconds: int, triggered_by: str) -> ScrapeRun:
    applications_before = _application_count(session, council_code)

    run = ScrapeRun(council_code=council_code, status="running", triggered_by=triggered_by)
    session.add(run)
    session.commit()

    print(f"\n[run-daily-councils] {council_code}: starting (ScrapeRun id={run.id})")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.pipeline.run_weekly", "--council", council_code],
            cwd=PROJECT_ROOT, timeout=timeout_seconds,
            capture_output=True, text=True,
        )
        success = result.returncode == 0
        # Council-level failure isolation lives here: a non-zero exit code
        # is recorded and reported, never re-raised - the loop in main()
        # always proceeds to the next council regardless.
        tail = "\n".join((result.stdout + result.stderr).splitlines()[-40:])
    except subprocess.TimeoutExpired as e:
        success = False
        tail = f"Timed out after {timeout_seconds}s. Partial output:\n" + "\n".join(
            ((e.stdout or "") + (e.stderr or "")).splitlines()[-40:]
        )
    except Exception as e:  # noqa: BLE001 - genuinely must never take the loop down
        success = False
        tail = f"Orchestrator error managing subprocess: {e}"

    applications_after = _application_count(session, council_code)
    discovered = applications_after - applications_before

    run.finished_at = dt.datetime.now(dt.timezone.utc)
    run.status = "success" if success else "failed"
    run.applications_before = applications_before
    run.applications_after = applications_after
    run.applications_discovered = discovered
    run.detail = tail[-4000:]  # bounded - this is operator-facing diagnostic text, not a full log store
    session.commit()

    verb = "OK" if success else "FAILED"
    print(f"[run-daily-councils] {council_code}: {verb} ({discovered:+d} applications)")
    return run


def main() -> None:
    args = parse_args()
    init_db()
    session = get_session()

    council_codes = args.councils or sorted(load_councils().keys())
    print(f"[run-daily-councils] {len(council_codes)} council(s) to run: {', '.join(council_codes)}")

    results = []
    for council_code in council_codes:
        try:
            run = run_one_council(
                session, council_code, timeout_seconds=args.timeout_seconds, triggered_by=args.triggered_by,
            )
            results.append(run)
        except Exception as e:  # noqa: BLE001 - one council's bookkeeping failure must not stop the rest
            print(f"[run-daily-councils] {council_code}: orchestrator-level error, continuing: {e}")

    succeeded = sum(1 for r in results if r.status == "success")
    failed = sum(1 for r in results if r.status == "failed")
    print(f"\n[run-daily-councils] Done. {succeeded} succeeded, {failed} failed, {len(council_codes)} attempted.")


if __name__ == "__main__":
    main()
