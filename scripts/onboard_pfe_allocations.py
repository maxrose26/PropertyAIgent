"""Sprint 3G ("Places for Everyone Allocation Onboarding") - creates
LocalPlanSite rows for every remaining Places for Everyone allocation from
config/pfe_allocation_onboarding.yaml. Never touches Bury's existing
JPA 7/8/9 rows or recreates the LocalPlan itself. Safe to run any number of
times.

    python -m scripts.onboard_pfe_allocations [--dry-run]
"""
from __future__ import annotations

import argparse

from app.db.session import get_session, init_db
from app.policy.pfe_allocation_onboarding import onboard_pfe_allocations


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report what would be created without writing anything.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    init_db()
    session = get_session()

    result = onboard_pfe_allocations(session, dry_run=args.dry_run)

    if result["plan_not_found"]:
        print("[onboard-pfe-allocations] Places for Everyone LocalPlan not found - nothing to do.")
        return

    verb = "would be" if args.dry_run else "were"
    print(f"[onboard-pfe-allocations] {result['created']} LocalPlanSite row(s) {verb} created, "
          f"{result['already_existed']} already existed (skipped)")
    print(f"[onboard-pfe-allocations] {result['relationships_created']} AllocationRelationship row(s) {verb} created")
    print("[onboard-pfe-allocations] by council:")
    for code, count in sorted(result["by_council"].items()):
        print(f"    {code}: {count}")
    if args.dry_run:
        print("[onboard-pfe-allocations] --dry-run: no changes were written")


if __name__ == "__main__":
    main()
