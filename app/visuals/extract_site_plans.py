"""Runnable command wiring the app.visuals package into real
VisualEvidence rows (Sprint 3C, "Allocation and Site-Plan Image
Extraction", Part 15):

    python -m app.visuals.extract_site_plans --council bury
    python -m app.visuals.extract_site_plans --site-id 9
    python -m app.visuals.extract_site_plans --application-id 11
    python -m app.visuals.extract_site_plans --document-id 37
    python -m app.visuals.extract_site_plans --local-plan-id 3 --pdf data/local_plans/stockport/LocalPlan.pdf
    python -m app.visuals.extract_site_plans --allocation-id 42 --pdf data/local_plans/stockport/LocalPlan.pdf
    python -m app.visuals.extract_site_plans --report-id 17 --pdf data/local_plans/bury/AMR-2024.pdf

Exactly one scope flag is required. --local-plan-id, --allocation-id and
--report-id additionally require --pdf, mirroring
app.policy.extract_plan_evidence's own "you already have this PDF
locally" shape - this codebase has no automated Local-Plan-document fetch
to call instead.

--dry-run runs real page detection, rendering and AI classification but
writes nothing to the database (app.policy.extract_plan_evidence's own
--dry-run has the same "extract and validate, don't persist" meaning -
kept consistent rather than reinvented). --force reprocesses pages whose
source content and prompt version are unchanged (never a REJECTED image,
which a human's decision always protects - see app.visuals.pipeline).
"""
from __future__ import annotations

import argparse

from dotenv import load_dotenv
from openai import OpenAI

from app.db.models import Application, Document, LocalPlan, LocalPlanSite, MonitoredReport, Site
from app.visuals.pipeline import (
    DEFAULT_MAX_AI_CLASSIFICATIONS_PER_RUN,
    DEFAULT_MAX_PAGES_PER_DOCUMENT,
    PipelineLimits,
    PipelineStats,
    process_document,
    process_local_plan_pdf,
    process_report,
    run_for_application,
    run_for_council,
    run_for_site,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--council", default=None, help="Process every Application for this council code")
    scope.add_argument("--site-id", type=int, default=None, help="Process every Application linked to this Site")
    scope.add_argument("--application-id", type=int, default=None, help="Process every candidate Document for this Application")
    scope.add_argument("--document-id", type=int, default=None, help="Process exactly this one Document, bypassing the candidate-document gate")
    scope.add_argument("--local-plan-id", type=int, default=None, help="Process a Local Plan's own PDF (requires --pdf)")
    scope.add_argument("--allocation-id", type=int, default=None, help="Process a single Allocation's plan PDF, matching only to it (requires --pdf)")
    scope.add_argument("--report-id", type=int, default=None, help="Process a MonitoredReport's PDF (requires --pdf)")

    parser.add_argument("--pdf", default=None, help="Local PDF path - required with --local-plan-id, --allocation-id, or --report-id")
    parser.add_argument("--dry-run", action="store_true", help="Render and classify but write nothing to the database")
    parser.add_argument("--force", action="store_true", help="Reprocess pages even if unchanged since the last run (never overrides a human rejection)")
    parser.add_argument("--max-pages-per-document", type=int, default=DEFAULT_MAX_PAGES_PER_DOCUMENT)
    parser.add_argument("--max-ai-classifications", type=int, default=DEFAULT_MAX_AI_CLASSIFICATIONS_PER_RUN)

    args = parser.parse_args()
    if (args.local_plan_id is not None or args.allocation_id is not None or args.report_id is not None) and not args.pdf:
        parser.error("--pdf is required with --local-plan-id, --allocation-id, or --report-id")
    return args


def _print_stats(stats: PipelineStats, mode: str) -> None:
    print(f"  [{mode}]")
    print(f"  documents scanned: {stats.documents_scanned} (skipped, not a candidate: {stats.documents_skipped_not_candidate})")
    print(f"  pages considered: {stats.pages_considered} | rendered: {stats.pages_rendered} | duplicates skipped: {stats.duplicates_skipped}")
    print(f"  AI classifications run: {stats.ai_classifications_run} | useful visuals found: {stats.useful_visuals_found}")
    print(f"  visuals linked to an object: {stats.visuals_linked} | queued for review: {stats.visuals_queued_for_review}")
    print(f"  estimated AI cost: ${stats.estimated_ai_cost_usd:.4f}")
    if stats.limit_reached:
        print("  NOTE: a configured limit was reached - not every candidate page in scope was processed this run")
    for error in stats.errors:
        print(f"  ERROR: {error}")


def main() -> None:
    args = parse_args()
    load_dotenv(override=True)
    from app.db.session import get_session, init_db  # local import: keeps this module importable/testable without touching the real DB

    init_db()
    session = get_session()
    client = OpenAI()

    limits = PipelineLimits(max_pages_per_document=args.max_pages_per_document, max_ai_classifications=args.max_ai_classifications)
    stats = PipelineStats()
    mode = "DRY RUN - nothing written" if args.dry_run else "applied"

    if args.council is not None:
        run_for_council(session, client, args.council, limits, stats, force=args.force, dry_run=args.dry_run)
    elif args.site_id is not None:
        site = session.get(Site, args.site_id)
        if site is None:
            raise ValueError(f"No Site {args.site_id} found")
        run_for_site(session, client, site, limits, stats, force=args.force, dry_run=args.dry_run)
    elif args.application_id is not None:
        application = session.get(Application, args.application_id)
        if application is None:
            raise ValueError(f"No Application {args.application_id} found")
        run_for_application(session, client, application, limits, stats, force=args.force, dry_run=args.dry_run)
    elif args.document_id is not None:
        document = session.get(Document, args.document_id)
        if document is None:
            raise ValueError(f"No Document {args.document_id} found")
        process_document(session, client, document, limits, stats, force=args.force, dry_run=args.dry_run)
    elif args.local_plan_id is not None:
        local_plan = session.get(LocalPlan, args.local_plan_id)
        if local_plan is None:
            raise ValueError(f"No LocalPlan {args.local_plan_id} found")
        process_local_plan_pdf(session, client, local_plan, args.pdf, limits, stats, force=args.force, dry_run=args.dry_run)
    elif args.allocation_id is not None:
        allocation = session.get(LocalPlanSite, args.allocation_id)
        if allocation is None:
            raise ValueError(f"No LocalPlanSite (Allocation) {args.allocation_id} found")
        if allocation.local_plan_id is None:
            raise ValueError(f"Allocation {args.allocation_id} has no local_plan_id - cannot resolve which plan/council it belongs to")
        local_plan = session.get(LocalPlan, allocation.local_plan_id)
        process_local_plan_pdf(
            session, client, local_plan, args.pdf, limits, stats, force=args.force, dry_run=args.dry_run, allocation_scope=allocation,
        )
    else:  # args.report_id is not None
        report = session.get(MonitoredReport, args.report_id)
        if report is None:
            raise ValueError(f"No MonitoredReport {args.report_id} found")
        process_report(session, client, report, args.pdf, limits, stats, force=args.force, dry_run=args.dry_run)

    print("[extract-site-plans]")
    _print_stats(stats, mode)


if __name__ == "__main__":
    main()
