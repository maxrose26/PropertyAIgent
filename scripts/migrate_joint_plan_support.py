"""One-off, idempotent backfill for Sprint 3E ("Joint Plan Support and Bury
Allocation Reconciliation", Part 2). Populates the new LocalPlanCouncil join
table for every existing LocalPlan row - see app.policy.joint_plans for the
actual linking logic this script drives, and app.db.models.LocalPlanCouncil
for why the table exists at all.

Safe to run any number of times:
  - LocalPlanCouncil rows are found-or-created per (local_plan_id,
    council_code) - a rerun creates zero new rows for a plan already fully
    linked (enforced by app.policy.joint_plans.ensure_council_links_for_plan
    AND the table's own DB-level uniqueness constraint as a second line of
    defence).
  - Never touches LocalPlan.council_code, never touches LocalPlanSite (no
    allocation is read, moved, deleted, or reassigned by this script at
    all - allocation-level reconciliation is a separate, explicitly
    reviewable process, see scripts/propose_bury_allocation_reconciliation.py).
  - A plan with no config/joint_plans.yaml entry (the ordinary,
    overwhelming majority case) gets exactly one join row, matching its
    existing council_code - single-authority plans are unaffected in
    substance, only in having an explicit join row instead of an implicit
    one.

    python -m scripts.migrate_joint_plan_support [--dry-run]
"""
from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db.models import LocalPlan
from app.db.session import get_session, init_db
from app.policy.joint_plans import ensure_council_links_for_plan, load_joint_plans_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing anything.")
    return parser.parse_args()


def migrate(session, dry_run: bool = False) -> dict:
    config = load_joint_plans_config()
    plans = session.execute(select(LocalPlan)).scalars().all()

    plans_processed = 0
    links_created = 0
    links_already_present = 0

    for plan in plans:
        result = ensure_council_links_for_plan(session, plan, config=config, dry_run=dry_run)
        plans_processed += 1
        links_created += result["created"]
        links_already_present += result["already_linked"]

    if not dry_run:
        session.commit()

    return {
        "plans_processed": plans_processed,
        "links_created": links_created,
        "links_already_present": links_already_present,
    }


def main() -> None:
    args = parse_args()
    init_db()
    session = get_session()

    result = migrate(session, dry_run=args.dry_run)

    verb = "would be" if args.dry_run else "were"
    print(f"[migrate-joint-plan-support] {result['plans_processed']} LocalPlan(s) processed")
    print(f"[migrate-joint-plan-support] {result['links_created']} LocalPlanCouncil link(s) {verb} created, "
          f"{result['links_already_present']} already present (skipped)")
    if args.dry_run:
        print("[migrate-joint-plan-support] --dry-run: no changes were written")


if __name__ == "__main__":
    main()
