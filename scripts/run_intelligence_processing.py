"""Bounded automated Intelligence Processing job (Pilot Readiness PR-2 final
pre-merge amendment, "Continuous Intelligence Processing"). This is the
production entry point Render's second Cron Job (see render.yaml) invokes
once a day, separately from Daily Discovery (scripts.run_daily_councils),
to turn newly-scraped data into actual AI-derived intelligence without
requiring an operator to remember to run a manual catch-up command.

Reuses run_weekly.py's own AI stages UNCHANGED - no second extraction
pipeline exists. This script only adds a bounded workload wrapper around
app.pipeline.run_weekly.stage_extraction and .stage_generate_scheme_
summaries, each called with an explicit `limit=` (a parameter this
amendment added to both functions for exactly this purpose - see their
own docstrings). Selection criteria (what counts as "outstanding work")
is entirely theirs, untouched: an Application with no SchemeIntelligence
row yet, or a Site whose linked-application history has grown since its
last AI summary. Nothing here re-implements or duplicates that logic.

Bounded AI workload (Part 6 of the amendment): configurable via
    PROPERTYAIGENT_MAX_EXTRACTIONS_PER_RUN  (default 20)
    PROPERTYAIGENT_MAX_SUMMARIES_PER_RUN    (default 20)
or the equivalent --max-extractions/--max-summaries CLI flags (CLI wins
over env var). Each cap applies ACROSS all councils processed in one
invocation, not per council - a run never processes more than the
configured maximum of either kind of work, regardless of how large the
backlog is. At the conservative defaults, one run can make at most
20 x 3 = 60 extraction LLM calls plus 20 x 1 = 20 summary LLM calls = 80
LLM calls total (see stage_extraction/run_extraction_for_application's own
"3 LLM stages" and stage_generate_scheme_summaries' "1 LLM call per
site" - this comment is the report's own source-of-truth figure, verified
against the actual code, not a separate estimate).

Backlog-aware, cost-safe by construction (Part 8): if there is genuinely
no outstanding extraction or summary work across the selected councils,
this script never creates an OpenAI client and never reads OPENAI_API_KEY
at all - the very first thing it does is a READ-ONLY count of outstanding
work (app.pipeline.run_weekly.count_pending_extraction/
count_pending_summaries) before deciding whether an API key is even
needed this run.

Observability (Part 9): writes one app.db.models.IntelligenceRun row per
invocation - attempted/succeeded/failed counts for each of extraction and
summaries, backlog remaining after this run, and a run timestamp. Mirrors
ScrapeRun's existing append-only pattern rather than introducing a new one.

Failure isolation: an individual application's extraction failing or an
individual site's summary generation failing is caught INSIDE stage_
extraction/stage_generate_scheme_summaries themselves (pre-existing
behaviour, untouched) - one failure never stops the rest of the run.

    python -m scripts.run_intelligence_processing [--council CODE ...]
        [--max-extractions N] [--max-summaries N] [--triggered-by manual]

Does NOT require EPC_API_KEY - this job never calls stage_check_build_status
or anything else that touches EPC data.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
from typing import Callable

from openai import OpenAI

from app.config import CouncilConfig, load_councils
from app.db.models import IntelligenceRun
from app.db.session import get_session, init_db
from app.pipeline.run_weekly import (
    count_pending_extraction,
    count_pending_summaries,
    stage_extraction,
    stage_generate_scheme_summaries,
)

DEFAULT_MAX_EXTRACTIONS_PER_RUN = 20
DEFAULT_MAX_SUMMARIES_PER_RUN = 20


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    return int(raw)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--council", action="append", dest="councils",
        help="Council code to consider (repeatable). Default: every council in config/councils.yaml.",
    )
    parser.add_argument(
        "--max-extractions", type=int, default=None,
        help=f"Max Applications to extract this run, across all councils combined. "
             f"Default: ${{PROPERTYAIGENT_MAX_EXTRACTIONS_PER_RUN}} or {DEFAULT_MAX_EXTRACTIONS_PER_RUN}.",
    )
    parser.add_argument(
        "--max-summaries", type=int, default=None,
        help=f"Max Site summaries to generate this run, across all councils combined. "
             f"Default: ${{PROPERTYAIGENT_MAX_SUMMARIES_PER_RUN}} or {DEFAULT_MAX_SUMMARIES_PER_RUN}.",
    )
    parser.add_argument(
        "--triggered-by", default="scheduled", choices=["scheduled", "manual"],
        help="Recorded on the IntelligenceRun row - 'manual' for an operator-triggered catch-up run.",
    )
    return parser.parse_args()


def process_intelligence_backlog(
    session,
    councils: dict[str, CouncilConfig],
    council_codes: list[str],
    *,
    max_extractions: int,
    max_summaries: int,
    triggered_by: str = "scheduled",
    client_factory: Callable[[str], object] = lambda api_key: OpenAI(api_key=api_key),
) -> IntelligenceRun:
    """The actual bounded-workload logic, factored out of main() so it can
    be exercised in tests against an in-memory SQLite session (never the
    real database - see tests/conftest.py) without needing a real OpenAI
    client. main() is a thin CLI wrapper around this function; nothing
    about the selection/limiting/observability logic lives in main()
    itself. client_factory exists purely so tests can inject a fake
    client instead of a real openai.OpenAI(...) - production always uses
    the default."""
    run = IntelligenceRun(status="running", triggered_by=triggered_by)
    session.add(run)
    session.commit()

    # Read-only backlog sizing BEFORE deciding whether an OpenAI client is
    # needed at all this run - see this module's own docstring ("Backlog-
    # aware, cost-safe by construction").
    extraction_backlog = {code: count_pending_extraction(session, code) for code in council_codes}
    summary_backlog = {code: count_pending_summaries(session, code) for code in council_codes}
    total_extraction_backlog = sum(extraction_backlog.values())
    total_summary_backlog = sum(summary_backlog.values())
    print(f"[intelligence-processing] backlog: {total_extraction_backlog} application(s) awaiting extraction, "
          f"{total_summary_backlog} site(s) awaiting a summary")

    extractions_planned = min(max_extractions, total_extraction_backlog)
    summaries_planned = min(max_summaries, total_summary_backlog)

    extractions_attempted = extractions_succeeded = extractions_failed = 0
    summaries_attempted = summaries_succeeded = summaries_failed = 0

    if extractions_planned == 0 and summaries_planned == 0:
        print("[intelligence-processing] no outstanding work within this run's limits - nothing to do, "
              "OPENAI_API_KEY was never read.")
        detail = "No outstanding work this run."
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            run.status = "failed"
            run.finished_at = dt.datetime.now(dt.timezone.utc)
            run.detail = "OPENAI_API_KEY not set in .env - outstanding work exists but could not be processed."
            session.commit()
            raise RuntimeError("OPENAI_API_KEY not set in .env")
        client = client_factory(api_key)

        remaining_extractions = extractions_planned
        remaining_summaries = summaries_planned

        for code in council_codes:
            council = councils[code]

            if remaining_extractions > 0 and extraction_backlog[code] > 0:
                planned_this_council = min(remaining_extractions, extraction_backlog[code])
                succeeded = stage_extraction(session, client, council, limit=remaining_extractions)
                extractions_attempted += planned_this_council
                extractions_succeeded += succeeded
                extractions_failed += max(planned_this_council - succeeded, 0)
                remaining_extractions -= planned_this_council

            if remaining_summaries > 0 and summary_backlog[code] > 0:
                planned_this_council = min(remaining_summaries, summary_backlog[code])
                generated = stage_generate_scheme_summaries(session, client, council, limit=remaining_summaries)
                summaries_attempted += planned_this_council
                summaries_succeeded += generated
                summaries_failed += max(planned_this_council - generated, 0)
                remaining_summaries -= planned_this_council

        detail = (
            f"Extractions: {extractions_succeeded}/{extractions_attempted} succeeded. "
            f"Summaries: {summaries_succeeded}/{summaries_attempted} succeeded."
        )

    # Re-count backlog AFTER the run - what's genuinely still outstanding,
    # for the next run (or an operator) to see.
    applications_backlog_remaining = sum(count_pending_extraction(session, code) for code in council_codes)
    sites_backlog_remaining = sum(count_pending_summaries(session, code) for code in council_codes)

    run.status = "success"
    run.finished_at = dt.datetime.now(dt.timezone.utc)
    run.extractions_attempted = extractions_attempted
    run.extractions_succeeded = extractions_succeeded
    run.extractions_failed = extractions_failed
    run.summaries_attempted = summaries_attempted
    run.summaries_succeeded = summaries_succeeded
    run.summaries_failed = summaries_failed
    run.applications_backlog_remaining = applications_backlog_remaining
    run.sites_backlog_remaining = sites_backlog_remaining
    run.detail = detail
    session.commit()

    print(f"\n[intelligence-processing] Done. {detail}")
    print(f"[intelligence-processing] Backlog remaining: {applications_backlog_remaining} application(s), "
          f"{sites_backlog_remaining} site(s).")
    return run


def main() -> None:
    args = parse_args()
    init_db()
    session = get_session()

    max_extractions = args.max_extractions if args.max_extractions is not None else _int_env(
        "PROPERTYAIGENT_MAX_EXTRACTIONS_PER_RUN", DEFAULT_MAX_EXTRACTIONS_PER_RUN
    )
    max_summaries = args.max_summaries if args.max_summaries is not None else _int_env(
        "PROPERTYAIGENT_MAX_SUMMARIES_PER_RUN", DEFAULT_MAX_SUMMARIES_PER_RUN
    )

    councils = load_councils()
    council_codes = args.councils or sorted(councils.keys())
    print(f"[intelligence-processing] {len(council_codes)} council(s) in scope: {', '.join(council_codes)}")
    print(f"[intelligence-processing] limits this run: max_extractions={max_extractions}, max_summaries={max_summaries}")

    process_intelligence_backlog(
        session, councils, council_codes,
        max_extractions=max_extractions, max_summaries=max_summaries, triggered_by=args.triggered_by,
    )


if __name__ == "__main__":
    main()
