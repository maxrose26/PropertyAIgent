"""Historical B3 Intelligence Rebuild - Unattended Overnight Runner.

Runs the existing, approved historical rebuild logic (app.extraction.
historical_rebuild.run_historical_rebuild - the SAME function scripts.
rebuild_intelligence's operator CLI calls) in repeated bounded batches
until the remaining rebuildable backlog reaches zero or a safe stop
condition fires, so ONE Render Cron Job invocation can work through the
whole remaining historical corpus without an operator staying connected
to trigger every individual batch by hand.

This module implements NO second AI rebuild engine, NO second candidate-
selection query, and NO second atomic-commit mechanism - every batch is
exactly one unmodified call to run_historical_rebuild(). This module's own
job is strictly: precheck -> loop batches -> log progress -> evaluate stop
conditions -> report a final summary -> exit code.

    python -m scripts.run_historical_rebuild_to_completion

Intended execution environment: a Render Cron Job (manually triggered via
"Trigger Run" in the Render dashboard - see render.yaml's own
propertyaigent-historical-rebuild-overnight entry), using Render's own
DATABASE_URL/OPENAI_API_KEY. Never a developer machine, never a Claude
session, never an interactive Shell session that could disconnect mid-run
(the previous dry-run Shell session disconnected during a relatively heavy
candidate scan - a Render Cron Job's own execution is entirely independent
of any client connection once triggered).

STOP CONDITIONS (conservative, based on run_historical_rebuild's own
OUTCOME_* taxonomy - see run_to_completion's own docstring for the exact
thresholds): an isolated candidate failure never stops the job (run_
historical_rebuild's own per-candidate isolation already guarantees that);
repeated/systemic failure (consecutive ai_error/invalid_output/error
outcomes, a high-failure-rate batch, an entire batch that attempted work
but rebuilt nothing, or an exception escaping run_historical_rebuild
itself - e.g. a DB connectivity failure) stops the job with a non-zero
exit code so it never silently burns through OpenAI calls against a
systemically broken backlog.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

from app.extraction.historical_rebuild import (
    DEFAULT_BATCH_LIMIT,
    REBUILD_VERSION,
    HistoricalRebuildRunSummary,
    run_historical_rebuild,
)
from app.extraction.run_extraction import OUTCOME_AI_ERROR, OUTCOME_ERROR, OUTCOME_INVALID_OUTPUT

EXIT_SUCCESS = 0
EXIT_PRECHECK_FAILED = 1
EXIT_STOPPED_SYSTEMIC = 2

# Reuses the existing historical runner's own conservative default batch
# size (app.extraction.historical_rebuild.DEFAULT_BATCH_LIMIT = 25) rather
# than inventing a second "the right batch size" number.
DEFAULT_INTERNAL_BATCH_SIZE = DEFAULT_BATCH_LIMIT

# Hard safety cap on total batches this single invocation will run - at 25
# candidates/batch this is up to 1,500 candidates, comfortably above the
# current ~625-application backlog while still bounding worst-case runtime
# if something behaves unexpectedly (e.g. remaining_rebuildable_after never
# reaching 0 due to a logic edge case this task's own tests didn't catch).
DEFAULT_MAX_BATCHES = 60

# "3 consecutive infrastructure/API failures: STOP" (task spec Part 6) -
# counts ai_error/invalid_output/error outcomes across CANDIDATES (not
# batches), consecutively, resetting on any success or no_usable_text
# (neither of which is evidence anything is systemically wrong).
CONSECUTIVE_SYSTEMIC_FAILURE_STOP = 3

# "batch failure rate >20%: STOP" (task spec Part 6). Only applied once a
# batch has attempted a minimum number of candidates, so a small tail batch
# (e.g. 1 of 1 candidates failing) doesn't trip a rate-based stop that only
# makes sense at meaningful volume.
BATCH_FAILURE_RATE_STOP = 0.20
BATCH_FAILURE_RATE_MIN_ATTEMPTED = 5

# "no forward progress between consecutive batches" (task spec Part 6).
# Deliberately requires at least 2 attempted candidates, not just 1 - a
# single, isolated, persistently-failing candidate can never be marked
# rebuilt and therefore can never let remaining_rebuildable reach zero on
# its own (Part 15D: "failed rows remain eligible"); once it is the ONLY
# thing left, every future batch attempting just that one candidate would
# otherwise look like "zero forward progress" every single time, even
# though this is exactly the "one isolated application failure: log and
# continue" case the task spec says must NOT stop the job. The consecutive-
# systemic-failure counter above already gives that specific candidate up
# to CONSECUTIVE_SYSTEMIC_FAILURE_STOP tries before stopping - this
# threshold exists for the DIFFERENT, stronger signal of a batch with
# multiple simultaneous non-progressing candidates.
NO_PROGRESS_MIN_ATTEMPTED = 2

_SYSTEMIC_OUTCOMES = (OUTCOME_AI_ERROR, OUTCOME_INVALID_OUTPUT, OUTCOME_ERROR)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def precheck(session) -> str | None:
    """Read-only, zero-OpenAI-call precheck (task spec Part 12/13). Returns
    None when safe to proceed, otherwise a human-readable reason to abort
    BEFORE any OpenAI call or batch is attempted. Never prints a secret
    value - only whether required environment variables are present."""
    if not os.environ.get("DATABASE_URL"):
        return "DATABASE_URL is not set."
    if not os.environ.get("OPENAI_API_KEY"):
        return "OPENAI_API_KEY is not set."

    from app.db.session import verify_schema

    missing_tables, missing_columns = verify_schema(session.get_bind())
    if missing_tables or missing_columns:
        return f"Schema is not current - missing_tables={missing_tables} missing_columns={missing_columns}."
    return None


def _log_batch(batch_number: int, started_at: dt.datetime, finished_at: dt.datetime, summary: HistoricalRebuildRunSummary) -> None:
    print(
        f"[historical-rebuild-overnight] batch={batch_number} "
        f"start={started_at.isoformat()} end={finished_at.isoformat()} "
        f"selected={summary.selected} attempted={summary.attempted} "
        f"success={summary.success} success_with_warning={summary.success_with_warning} "
        f"no_usable_text={summary.no_usable_text} ai_error={summary.ai_error} "
        f"invalid_output={summary.invalid_output} error={summary.error} "
        f"already_rebuilt_after={summary.already_rebuilt_after} "
        f"remaining_rebuildable_after={summary.remaining_rebuildable_after} "
        f"qa_tenure_mismatch={summary.tenure_mismatch_warnings} qa_complex_site={summary.complex_site_warnings}",
        flush=True,
    )
    for result in summary.results:
        if result.qa_warnings:
            print(
                f"[historical-rebuild-overnight]   review app={result.application_id} "
                f"ref={result.reference!r} warnings={result.qa_warnings}",
                flush=True,
            )
        if result.outcome in _SYSTEMIC_OUTCOMES:
            print(
                f"[historical-rebuild-overnight]   failed app={result.application_id} "
                f"ref={result.reference!r} outcome={result.outcome}",
                flush=True,
            )


class _Totals:
    """Running totals across every batch this invocation ran - accumulated
    purely for the final summary report (task spec Part 8), never used to
    decide anything about rebuild-marker state itself."""

    def __init__(self) -> None:
        self.attempted = 0
        self.success = 0
        self.success_with_warning = 0
        self.no_usable_text = 0
        self.ai_error = 0
        self.invalid_output = 0
        self.error = 0
        self.tenure_mismatch_warnings = 0
        self.complex_site_warnings = 0
        self.batches = 0

    def add(self, summary: HistoricalRebuildRunSummary) -> None:
        self.batches += 1
        self.attempted += summary.attempted
        self.success += summary.success
        self.success_with_warning += summary.success_with_warning
        self.no_usable_text += summary.no_usable_text
        self.ai_error += summary.ai_error
        self.invalid_output += summary.invalid_output
        self.error += summary.error
        self.tenure_mismatch_warnings += summary.tenure_mismatch_warnings
        self.complex_site_warnings += summary.complex_site_warnings


def _log_final(
    stop_reason: str, started_at: dt.datetime, totals: _Totals,
    final_rebuilt: int | None, final_remaining: int | None, final_blocked: int | None,
) -> None:
    elapsed = (_utcnow() - started_at).total_seconds()
    print(
        f"[historical-rebuild-overnight] FINAL stop_reason={stop_reason} batches={totals.batches} "
        f"attempted={totals.attempted} success={totals.success} success_with_warning={totals.success_with_warning} "
        f"no_usable_text={totals.no_usable_text} ai_error={totals.ai_error} invalid_output={totals.invalid_output} "
        f"error={totals.error} qa_tenure_mismatch={totals.tenure_mismatch_warnings} "
        f"qa_complex_site={totals.complex_site_warnings} final_rebuilt={final_rebuilt} "
        f"final_remaining_rebuildable={final_remaining} final_blocked_no_usable_evidence={final_blocked} "
        f"elapsed_seconds={elapsed:.1f}",
        flush=True,
    )


def run_to_completion(
    session, client: OpenAI, *,
    batch_size: int = DEFAULT_INTERNAL_BATCH_SIZE, max_batches: int = DEFAULT_MAX_BATCHES,
) -> tuple[str, int]:
    """The testable core - loops bounded run_historical_rebuild() batches
    until completion or a stop condition. Returns (stop_reason, exit_code).

    Stop reasons: "completed" (exit 0, backlog genuinely empty);
    "consecutive_systemic_failures", "batch_failure_rate",
    "no_forward_progress", "systemic_exception", "max_batches_exceeded"
    (all exit EXIT_STOPPED_SYSTEMIC - a deliberately conservative signal
    that something is wrong and an operator should look before any more
    OpenAI spend happens)."""
    started_at = _utcnow()
    totals = _Totals()
    consecutive_systemic_failures = 0

    for batch_number in range(1, max_batches + 1):
        batch_started = _utcnow()
        try:
            summary = run_historical_rebuild(
                session, client, dry_run=False, limit=batch_size, rebuild_version=REBUILD_VERSION,
            )
        except Exception as exc:
            session.rollback()
            print(
                f"[historical-rebuild-overnight] batch={batch_number} SYSTEMIC EXCEPTION: "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr, flush=True,
            )
            _log_final("systemic_exception", started_at, totals, None, None, None)
            return "systemic_exception", EXIT_STOPPED_SYSTEMIC
        batch_finished = _utcnow()

        _log_batch(batch_number, batch_started, batch_finished, summary)
        totals.add(summary)

        for result in summary.results:
            if result.outcome in _SYSTEMIC_OUTCOMES:
                consecutive_systemic_failures += 1
                if consecutive_systemic_failures >= CONSECUTIVE_SYSTEMIC_FAILURE_STOP:
                    _log_final(
                        "consecutive_systemic_failures", started_at, totals,
                        summary.already_rebuilt_after, summary.remaining_rebuildable_after,
                        summary.blocked_no_usable_evidence,
                    )
                    return "consecutive_systemic_failures", EXIT_STOPPED_SYSTEMIC
            else:
                consecutive_systemic_failures = 0

        if summary.selected == 0:
            # Nothing left matching this rebuild version's eligibility -
            # the genuinely-empty-backlog completion signal.
            _log_final(
                "completed", started_at, totals,
                summary.already_rebuilt_after, summary.remaining_rebuildable_after,
                summary.blocked_no_usable_evidence,
            )
            return "completed", EXIT_SUCCESS

        if summary.attempted >= BATCH_FAILURE_RATE_MIN_ATTEMPTED:
            failure_count = summary.ai_error + summary.invalid_output + summary.error
            if failure_count / summary.attempted > BATCH_FAILURE_RATE_STOP:
                _log_final(
                    "batch_failure_rate", started_at, totals,
                    summary.already_rebuilt_after, summary.remaining_rebuildable_after,
                    summary.blocked_no_usable_evidence,
                )
                return "batch_failure_rate", EXIT_STOPPED_SYSTEMIC

        if summary.attempted >= NO_PROGRESS_MIN_ATTEMPTED and summary.already_rebuilt_after == summary.already_rebuilt_before:
            # A batch that genuinely attempted candidates but rebuilt none
            # of them - no forward progress, regardless of which outcome
            # category absorbed each candidate.
            _log_final(
                "no_forward_progress", started_at, totals,
                summary.already_rebuilt_after, summary.remaining_rebuildable_after,
                summary.blocked_no_usable_evidence,
            )
            return "no_forward_progress", EXIT_STOPPED_SYSTEMIC

        if summary.remaining_rebuildable_after == 0:
            _log_final(
                "completed", started_at, totals,
                summary.already_rebuilt_after, summary.remaining_rebuildable_after,
                summary.blocked_no_usable_evidence,
            )
            return "completed", EXIT_SUCCESS

    _log_final("max_batches_exceeded", started_at, totals, None, None, None)
    return "max_batches_exceeded", EXIT_STOPPED_SYSTEMIC


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.run_historical_rebuild_to_completion",
        description=(
            "Unattended historical B3 rebuild runner - repeats bounded "
            "run_historical_rebuild() batches to completion or a safe stop "
            "condition. Intended for a Render Cron Job, not interactive use."
        ),
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_INTERNAL_BATCH_SIZE,
        help=f"Candidates per internal batch (default {DEFAULT_INTERNAL_BATCH_SIZE}, "
             "the same default run_historical_rebuild itself uses).",
    )
    parser.add_argument(
        "--max-batches", type=int, default=DEFAULT_MAX_BATCHES,
        help=f"Hard safety cap on total batches this invocation will run (default {DEFAULT_MAX_BATCHES}).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv(override=True)
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    from app.db.session import get_session

    session = get_session()
    try:
        reason = precheck(session)
        if reason:
            print(f"[historical-rebuild-overnight] PRECHECK FAILED: {reason}", file=sys.stderr, flush=True)
            return EXIT_PRECHECK_FAILED

        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        stop_reason, exit_code = run_to_completion(
            session, client, batch_size=args.batch_size, max_batches=args.max_batches,
        )
        print(f"[historical-rebuild-overnight] STOP REASON: {stop_reason}", flush=True)
        return exit_code
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
