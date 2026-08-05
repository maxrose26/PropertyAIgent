"""Runs Sprint 3E's Bury duplicate-name reconciliation proposals for real
(see app.policy.allocation_reconciliation and config/bury_allocation_
reconciliation.yaml for the investigated findings this applies). Creates
PolicyChangeEvent + AllocationRelationship rows with review_status=
"needs_review" - never touches a LocalPlanSite's trusted fields directly.
Safe to run any number of times.

    python -m scripts.propose_bury_allocation_reconciliation [--dry-run]
"""
from __future__ import annotations

import argparse

from app.db.session import get_session, init_db
from app.policy.allocation_reconciliation import propose_reconciliations


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report what would be proposed without writing anything.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    init_db()
    session = get_session()

    result = propose_reconciliations(session, dry_run=args.dry_run)

    verb = "would be" if args.dry_run else "were"
    print(f"[bury-allocation-reconciliation] {result['proposals_created']} PolicyChangeEvent proposal(s) {verb} created")
    print(f"[bury-allocation-reconciliation] {result['relationships_created']} AllocationRelationship(s) {verb} created")
    print(f"[bury-allocation-reconciliation] {result['skipped_already_proposed']} allocation(s) skipped (already proposed/resolved)")
    if result["allocations_not_found"]:
        print(f"[bury-allocation-reconciliation] NOT FOUND (config entry did not match any LocalPlanSite row): "
              f"{', '.join(result['allocations_not_found'])}")
    if args.dry_run:
        print("[bury-allocation-reconciliation] --dry-run: no changes were written")


if __name__ == "__main__":
    main()
