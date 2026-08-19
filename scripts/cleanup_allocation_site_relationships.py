"""Stage 2E.2 ("Controlled Allocation<->Site Relationship Cleanup Runner")
CLI - the explicit, operator-invoked execution of the Stage 2E.1 Amendment's
final approved classification (KEEP=17, NEEDS_CONFIRMATION=12, REJECT=7,
TOTAL=36) against AllocationSiteRelationship.review_status.

Orchestrates ONLY app.policy.relationship_cleanup_runner - no independent
matcher or write logic here (see that module's own docstring for the full
reasoning). This file is deliberately a thin CLI wrapper, mirroring
scripts/populate_control_relationships.py's own established shape exactly.

Dry-run (the default, no flags needed) is READ ONLY - makes zero database
mutations:

    python -m scripts.cleanup_allocation_site_relationships

Production write mode requires BOTH flags together (same deliberate-
friction pattern as every other Stage 2/3/4 write-capable script in this
codebase):

    python -m scripts.cleanup_allocation_site_relationships --execute --confirm YES-CLEANUP-ALLOCATION-SITE-RELATIONSHIPS

FAIL CLOSED: any other value for --confirm (missing, misspelled, or simply
absent) with --execute given refuses to write and exits non-zero.

PREREQUISITE: the Stage 2E.1 matcher-integrity fix (merge fef5689, tag
v0.4.8u-allocation-site-relationship-integrity-fix) MUST already be
deployed to the environment this script is run against - every target's
eligibility is revalidated live against whatever matcher code is actually
running, so running this against an undeployed/pre-fix environment would
revalidate against the WRONG matcher. This script does not itself verify
deployment; verifying that is the caller's / operator's responsibility."""
from __future__ import annotations

import argparse
import sys

from app.db.models import LocalPlanSite
from app.db.session import get_session, init_db
from app.policy.relationship_cleanup_runner import (
    APPLIED,
    CONFIRM_PHRASE,
    WOULD_APPLY,
    affected_allocation_ids,
    current_status_distribution,
    proposed_status_distribution,
    run_cleanup_relationships,
    simulate_proposed_coverage,
)
from app.reporting.allocation_development_coverage import build_allocation_development_coverage

# Section 5's explicit minimum coverage display set, by allocation_id -
# H3/H4/H5/H6/AN11 are the affected allocations named in the approved
# TO_REJECT/TO_NEEDS_CONFIRMATION targets; JPA 32 (North of Mosley Common)
# is deliberately NOT one of the targets - it is shown as the regression
# anchor proving the cleanup touches nothing it shouldn't.
_MINIMUM_COVERAGE_DISPLAY_ALLOCATION_IDS = (210, 211, 212, 213, 146, 73)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Write to production. Requires --confirm with the exact phrase below as well.")
    parser.add_argument("--confirm", default=None, help=f"Must exactly equal '{CONFIRM_PHRASE}' to actually write. Ignored unless --execute is also given.")
    return parser.parse_args()


def _print_outcomes(label: str, outcomes) -> None:
    print(f"{label} ({len(outcomes)} requested):")
    for o in outcomes:
        print(
            f"  allocation={o.allocation_id} site={o.site_id} rel_id={o.relationship_id} "
            f"action={o.action} outcome={o.outcome} previous_status={o.previous_review_status!r} - {o.detail}"
        )


def _count(outcomes, outcome_name: str) -> int:
    return sum(1 for o in outcomes if o.outcome == outcome_name)


def _outcome_breakdown(outcomes) -> dict[str, int]:
    breakdown: dict[str, int] = {}
    for o in outcomes:
        breakdown[o.outcome] = breakdown.get(o.outcome, 0) + 1
    return breakdown


def _print_coverage_comparison(session, allocation_ids: list[int], report) -> None:
    allocations = [a for a in (session.get(LocalPlanSite, aid) for aid in allocation_ids) if a is not None]
    current = build_allocation_development_coverage(session, allocations)
    proposed = simulate_proposed_coverage(session, allocation_ids, report)

    print("\n=== CURRENT VS PROPOSED DEVELOPMENT COVERAGE (affected allocations + regression anchor) ===")
    for allocation in allocations:
        cur = current.get(allocation.id, {}).get("coverage")
        prop = proposed.get(allocation.id, {}).get("coverage")
        label = f"{allocation.policy_reference or '(no ref)'} {allocation.site_name}"
        print(f"\n[{allocation.id}] {label}")
        if cur is not None:
            print(
                f"  current : sites={cur.number_of_related_sites} homes_identified={cur.identified_application_capacity} "
                f"residual={cur.indicative_residual_capacity} classification={cur.development_coverage_classification} "
                f"status={cur.capacity_accounting_status}"
            )
        if prop is not None:
            print(
                f"  proposed: sites={prop.number_of_related_sites} homes_identified={prop.identified_application_capacity} "
                f"residual={prop.indicative_residual_capacity} classification={prop.development_coverage_classification} "
                f"status={prop.capacity_accounting_status}"
            )


def _run_dry_run(session) -> None:
    print("[cleanup-allocation-site-relationships] DRY RUN - zero database mutations will be made\n")

    total = sum(current_status_distribution(session).values())
    print(f"total relationships: {total}")
    print(f"current status distribution: {current_status_distribution(session)}")

    report = run_cleanup_relationships(session, execute=False)

    _print_outcomes("\nreject targets", report.reject_outcomes)
    _print_outcomes("\nneeds_confirmation targets", report.needs_confirmation_outcomes)

    reject_valid = _count(report.reject_outcomes, WOULD_APPLY)
    reject_blocked = len(report.reject_outcomes) - reject_valid
    review_valid = _count(report.needs_confirmation_outcomes, WOULD_APPLY)
    review_blocked = len(report.needs_confirmation_outcomes) - review_valid

    print(f"\nreject targets requested: {len(report.reject_outcomes)}")
    print(f"reject targets still valid after revalidation: {reject_valid}")
    print(f"reject targets blocked by drift/other: {reject_blocked}")
    print(f"  reject outcome breakdown: {_outcome_breakdown(report.reject_outcomes)}")
    print(f"needs_confirmation targets requested: {len(report.needs_confirmation_outcomes)}")
    print(f"needs_confirmation targets still valid after revalidation: {review_valid}")
    print(f"review targets blocked by drift/other: {review_blocked}")
    print(f"  needs_confirmation outcome breakdown: {_outcome_breakdown(report.needs_confirmation_outcomes)}")

    keep_count = total - len(report.reject_outcomes) - len(report.needs_confirmation_outcomes)
    print(f"keep count (unaffected relationships): {keep_count}")

    print(f"\ncurrent status distribution : {current_status_distribution(session)}")
    print(f"proposed status distribution: {proposed_status_distribution(session, report)}")

    affected = affected_allocation_ids(report)
    print(f"\naffected allocations (allocation_id): {affected}")

    display_ids = sorted(set(_MINIMUM_COVERAGE_DISPLAY_ALLOCATION_IDS) | set(affected))
    _print_coverage_comparison(session, display_ids, report)

    print("\n=== RESULT ===")
    print("DRY RUN COMPLETE - NO WRITES MADE")


def _run_execute(session) -> None:
    print("[cleanup-allocation-site-relationships] PRODUCTION WRITE MODE - this WILL write to the database\n")

    print(f"status distribution BEFORE: {current_status_distribution(session)}")

    report = run_cleanup_relationships(session, execute=True)

    _print_outcomes("\nreject targets", report.reject_outcomes)
    _print_outcomes("\nneeds_confirmation targets", report.needs_confirmation_outcomes)

    applied = _count(report.reject_outcomes + report.needs_confirmation_outcomes, APPLIED)
    failed = len(report.failures)
    print(f"\napplied: {applied}")
    print(f"failed (isolated, other targets unaffected): {failed}")
    if report.failures:
        print("failures:")
        for o in report.failures:
            print(f"  allocation={o.allocation_id} site={o.site_id} action={o.action} - {o.detail}")

    print(f"\nstatus distribution AFTER: {current_status_distribution(session)}")

    print("\n=== RESULT ===")
    print("PRODUCTION WRITE COMPLETE" if not report.failures else "PRODUCTION WRITE COMPLETE WITH FAILURES - see above")


def main() -> None:
    args = parse_args()

    production_mode = args.execute
    if production_mode and args.confirm != CONFIRM_PHRASE:
        print(
            f"[cleanup-allocation-site-relationships] --execute requires --confirm '{CONFIRM_PHRASE}' exactly - refusing to write.",
            file=sys.stderr,
        )
        sys.exit(2)

    init_db()
    session = get_session()

    if production_mode:
        _run_execute(session)
        return

    _run_dry_run(session)


if __name__ == "__main__":
    main()
