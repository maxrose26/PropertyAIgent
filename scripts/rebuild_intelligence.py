"""Historical B3 Intelligence Rebuild Runner - operator CLI.

Regenerates EXISTING production SchemeIntelligence rows using the current
approved B3 refresh standard (see app.extraction.historical_rebuild for the
full design). Manually/operator invoked ONLY - deliberately not wired into
the normal 07:00 cron (see render.yaml, untouched by this script).

Always run --dry-run first:

    python -m scripts.rebuild_intelligence --dry-run --limit 25

Then a small live batch:

    python -m scripts.rebuild_intelligence --limit 10

Optional scope filters (combinable):

    --council stockport
    --application-id 708
    --site-id 74

Batches above 50 candidates require an explicit, deliberate override:

    python -m scripts.rebuild_intelligence --limit 100 --allow-large-batch

There is no flag that runs the full corpus by default - --limit always has
a bounded default (25) and anything past the safety threshold requires
--allow-large-batch.
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from app.extraction.historical_rebuild import (
    DEFAULT_BATCH_LIMIT,
    MAX_BATCH_LIMIT_WITHOUT_OVERRIDE,
    REBUILD_VERSION,
    HistoricalRebuildRunSummary,
    run_historical_rebuild,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.rebuild_intelligence",
        description=(
            "One-off, resumable historical B3 intelligence rebuild runner. "
            "Regenerates existing SchemeIntelligence rows using the current "
            "approved B3 standard. Always run --dry-run first."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Select and report candidates only. Zero database writes, zero OpenAI calls.",
    )
    parser.add_argument(
        "--limit", type=int, default=DEFAULT_BATCH_LIMIT,
        help=f"Maximum candidates this invocation processes (default {DEFAULT_BATCH_LIMIT}). "
             f"Values above {MAX_BATCH_LIMIT_WITHOUT_OVERRIDE} require --allow-large-batch.",
    )
    parser.add_argument(
        "--allow-large-batch", action="store_true",
        help=f"Required to set --limit above {MAX_BATCH_LIMIT_WITHOUT_OVERRIDE}. "
             "Makes an accidentally huge batch a deliberate choice, not a default.",
    )
    parser.add_argument("--council", type=str, default=None, help="Restrict candidates to one council code (e.g. stockport).")
    parser.add_argument("--application-id", type=int, default=None, help="Restrict to one Application id.")
    parser.add_argument("--site-id", type=int, default=None, help="Restrict to applications linked to one Site id.")
    parser.add_argument(
        "--rebuild-version", type=str, default=REBUILD_VERSION,
        help=f"Rebuild version to mark successfully-rebuilt rows with (default {REBUILD_VERSION!r}).",
    )
    return parser


def _print_report(summary: HistoricalRebuildRunSummary) -> None:
    mode = "DRY RUN" if summary.dry_run else "LIVE BATCH"
    print(f"[rebuild-intelligence] mode={mode} rebuild_version={summary.rebuild_version!r}")

    print(
        f"[rebuild-intelligence] GLOBAL corpus={summary.total_historical_corpus} "
        f"currently_rebuildable={summary.currently_rebuildable} "
        f"blocked_no_usable_evidence={summary.blocked_no_usable_evidence} "
        f"already_rebuilt={summary.already_rebuilt_before} remaining_rebuildable={summary.remaining_rebuildable_before}"
    )
    print(
        f"[rebuild-intelligence] SCOPE (this invocation's filters) total={summary.scope_total_historical} "
        f"currently_rebuildable={summary.scope_currently_rebuildable} "
        f"blocked_no_usable_evidence={summary.scope_blocked_no_usable_evidence} "
        f"already_rebuilt={summary.scope_already_rebuilt_before} "
        f"remaining_rebuildable={summary.scope_remaining_rebuildable_before}"
    )
    print(f"[rebuild-intelligence] candidates_inspected={summary.candidates_inspected} selected={summary.selected}")

    if summary.dry_run:
        print(f"[rebuild-intelligence] estimated_llm_calls={summary.estimated_llm_calls}")
        for snapshot in summary.dry_run_snapshots:
            print(
                f"  - app={snapshot.application_id} ref={snapshot.reference!r} council={snapshot.council_code} "
                f"site_id={snapshot.site_id} depth={snapshot.depth} usable_docs={snapshot.usable_document_count} "
                f"prior_version={snapshot.prior_rebuild_version!r} expected_calls={snapshot.expected_llm_calls}"
            )
        print("[rebuild-intelligence] No database writes. No OpenAI calls.")
    else:
        print(
            f"[rebuild-intelligence] THIS BATCH attempted={summary.attempted} success={summary.success} "
            f"success_with_warning={summary.success_with_warning} no_usable_text={summary.no_usable_text} "
            f"ai_error={summary.ai_error} invalid_output={summary.invalid_output} error={summary.error}"
        )
        print(
            f"[rebuild-intelligence] qa_warnings: tenure_mismatch={summary.tenure_mismatch_warnings} "
            f"complex_site={summary.complex_site_warnings}"
        )
        for result in summary.results:
            if result.qa_warnings:
                print(f"  ! app={result.application_id} ref={result.reference!r} warnings={result.qa_warnings}")
        print(
            f"[rebuild-intelligence] AFTER BATCH GLOBAL rebuilt={summary.already_rebuilt_after} "
            f"remaining_rebuildable={summary.remaining_rebuildable_after}"
        )
        print(
            f"[rebuild-intelligence] AFTER BATCH SCOPE rebuilt={summary.scope_already_rebuilt_after} "
            f"remaining_rebuildable={summary.scope_remaining_rebuildable_after}"
        )

    print(f"[rebuild-intelligence] council_distribution={summary.council_distribution}")


def main(argv: list[str] | None = None) -> int:
    load_dotenv(override=True)
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    from app.db.session import get_session

    session = get_session()
    client = None
    if not args.dry_run:
        from openai import OpenAI

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("[rebuild-intelligence] OPENAI_API_KEY is not set - required for a live (non-dry-run) batch.", file=sys.stderr)
            session.close()
            return 1
        client = OpenAI(api_key=api_key)

    try:
        summary = run_historical_rebuild(
            session, client,
            dry_run=args.dry_run, limit=args.limit, allow_large_batch=args.allow_large_batch,
            council=args.council, application_id=args.application_id, site_id=args.site_id,
            rebuild_version=args.rebuild_version,
        )
    except ValueError as exc:
        print(f"[rebuild-intelligence] {exc}", file=sys.stderr)
        session.close()
        return 1

    session.close()
    _print_report(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
