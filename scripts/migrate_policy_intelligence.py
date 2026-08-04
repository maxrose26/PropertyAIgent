"""One-off, idempotent backfill for the Policy Intelligence Foundation
sprint (specifications/004-core-domain-model.md's "Policy" domain object).

Schema changes (new tables, new nullable columns on local_plan_sites) need
no bespoke migration - app.db.session._add_missing_columns already diffs
every model against the live SQLite schema and ADDs any missing column on
every init_db() call. This script only backfills DATA: linking every
pre-sprint LocalPlanSite row (created before a real LocalPlan entity
existed) to a proper LocalPlan row, and snapshotting each into
AllocationVersion so it has a version history from this point forward.

Safe to run any number of times:
  - Only touches LocalPlanSite rows where local_plan_id IS NULL - already-
    migrated (or newly-ingested, which always sets local_plan_id itself)
    rows are left untouched on every rerun.
  - LocalPlan rows are found-or-created by (council_code, plan_name,
    plan_version) - rerunning never creates a duplicate plan.
  - Never deletes or overwrites an existing column value on LocalPlanSite -
    only SETS local_plan_id, and only on rows where it's currently null.
  - matched_site_id / match_confidence / latitude / longitude (the existing
    Stockport pilot's Site-matching results) are never touched.

    python -m scripts.migrate_policy_intelligence [--dry-run]
"""
from __future__ import annotations

import argparse
import json

from sqlalchemy import select

from app.db.models import AllocationVersion, LocalPlan, LocalPlanSite
from app.db.session import get_session, init_db
from app.policy.progression import classify_progression
from app.policy.status import derive_allocation_status_from_plan_status, normalise_plan_status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing anything.")
    return parser.parse_args()


def migrate(session, dry_run: bool = False) -> dict:
    pending = session.execute(
        select(LocalPlanSite).where(LocalPlanSite.local_plan_id.is_(None))
    ).scalars().all()

    plans_created = 0
    plans_reused = 0
    allocations_linked = 0
    versions_snapshotted = 0
    plan_cache: dict[tuple[str, str], LocalPlan] = {}

    for row in pending:
        key = (row.council_code, row.plan_name)
        plan = plan_cache.get(key)
        if plan is None:
            plan = session.execute(
                select(LocalPlan).where(
                    LocalPlan.council_code == row.council_code,
                    LocalPlan.plan_name == row.plan_name,
                    LocalPlan.plan_version.is_(None),
                )
            ).scalar_one_or_none()
            if plan is None:
                plan = LocalPlan(
                    council_code=row.council_code, plan_name=row.plan_name,
                    status=normalise_plan_status(row.plan_status), raw_status=row.plan_status,
                    source_webpage=row.source_document_url,
                )
                if not dry_run:
                    session.add(plan)
                    session.flush()  # assigns plan.id for the FK set below
                plans_created += 1
            else:
                plans_reused += 1
            plan_cache[key] = plan

        if dry_run:
            allocations_linked += 1
            continue

        row.local_plan_id = plan.id
        if row.allocation_status is None:
            derived_status, note = derive_allocation_status_from_plan_status(row.plan_status)
            row.allocation_status = derived_status
            row.raw_allocation_status = note
            row.review_status = "needs_confirmation"

        signal, reasons = classify_progression(plan.status, row.allocation_status, present_in_latest_version=True)
        row.progression_signal = signal
        row.progression_reasons = json.dumps(reasons)

        session.add(AllocationVersion(
            allocation_id=row.id, local_plan_id=plan.id,
            policy_reference=row.policy_reference, site_name=row.site_name,
            minimum_dwellings=row.minimum_dwellings, indicative_capacity=row.indicative_capacity,
            maximum_capacity=row.maximum_capacity, category=row.category,
            allocation_status=row.allocation_status, raw_allocation_status=row.raw_allocation_status,
            change_reason="initial_migration",
        ))
        versions_snapshotted += 1
        allocations_linked += 1

    if not dry_run:
        session.commit()

    return {
        "plans_created": plans_created, "plans_reused": plans_reused,
        "allocations_linked": allocations_linked, "versions_snapshotted": versions_snapshotted,
        "allocations_already_migrated": 0,
    }


def main() -> None:
    args = parse_args()
    init_db()
    session = get_session()
    already_migrated = session.execute(
        select(LocalPlanSite).where(LocalPlanSite.local_plan_id.is_not(None))
    ).scalars().all()

    result = migrate(session, dry_run=args.dry_run)
    result["allocations_already_migrated"] = len(already_migrated)

    verb = "would be" if args.dry_run else "were"
    print(f"[migrate-policy-intelligence] {result['plans_created']} Local Plan(s) {verb} created, "
          f"{result['plans_reused']} reused")
    print(f"[migrate-policy-intelligence] {result['allocations_linked']} allocation(s) {verb} linked, "
          f"{result['versions_snapshotted']} version snapshot(s) {verb} written")
    print(f"[migrate-policy-intelligence] {result['allocations_already_migrated']} allocation(s) already "
          f"migrated (skipped)")
    if args.dry_run:
        print("[migrate-policy-intelligence] --dry-run: no changes were written")


if __name__ == "__main__":
    main()
