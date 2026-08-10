"""One-off, idempotent correction for Pilot Readiness PR-2 ("PfE Authority
Integrity"). Removes the erroneous LocalPlanCouncil row that recorded
Stockport as a Places for Everyone participating authority - Stockport
withdrew from the plan's predecessor (the Greater Manchester Spatial
Framework) in December 2020 and is not one of the nine authorities named on
data/local_plans/bury/places_for_everyone.pdf's own title page (Bolton,
Bury, Manchester, Oldham, Rochdale, Salford, Tameside, Trafford, Wigan).

scripts/migrate_joint_plan_support.py is deliberately additive-only (see its
own docstring: "Never removes or reassigns an existing LocalPlanCouncil
row"), so re-running it after config/joint_plans.yaml's correction adds the
missing Manchester row but cannot remove this pre-existing incorrect one -
this script is the explicit, auditable counterpart for that removal.

Safe to run any number of times: finds the specific
(plan_name="Places for Everyone...", council_code="stockport") row and
deletes it if present; a rerun after it's already gone is a no-op.

Only ever deletes a LocalPlanCouncil row (the join table). LocalPlanSite is
never read, moved, deleted, or reassigned by this script - a pre-flight
check confirms zero of Stockport's own LocalPlanSite rows are attributed to
the Places for Everyone plan_name before doing anything, and aborts without
writing if that assumption doesn't hold (Stockport's 37 allocations are
already independently confirmed to belong to "Stockport Local Plan", not
PfE - this check exists as a second line of defence, not because that's
expected to fail).

    python -m scripts.fix_pfe_stockport_membership [--dry-run]
"""
from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db.models import LocalPlan, LocalPlanCouncil, LocalPlanSite
from app.db.session import get_session, init_db

PFE_PLAN_NAME = "Places for Everyone Joint Development Plan (Bury allocations)"
ERRONEOUS_COUNCIL = "stockport"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing anything.")
    return parser.parse_args()


def fix(session, dry_run: bool = False) -> dict:
    plan = session.execute(select(LocalPlan).where(LocalPlan.plan_name == PFE_PLAN_NAME)).scalars().first()
    if plan is None:
        return {"plan_found": False, "row_removed": False, "stockport_pfe_allocations": 0}

    # Pre-flight safety check - this script must never run if it would leave
    # Stockport allocations pointing at a plan Stockport no longer has a
    # council link to.
    stockport_pfe_allocations = session.execute(
        select(LocalPlanSite).where(
            LocalPlanSite.council_code == ERRONEOUS_COUNCIL, LocalPlanSite.local_plan_id == plan.id,
        )
    ).scalars().all()
    if stockport_pfe_allocations:
        raise RuntimeError(
            f"ABORTED: {len(stockport_pfe_allocations)} Stockport LocalPlanSite row(s) are attributed to the PfE "
            f"plan (local_plan_id={plan.id}) - removing the LocalPlanCouncil link would leave these allocations "
            f"inconsistent. Investigate before rerunning; no changes were written."
        )

    existing = session.execute(
        select(LocalPlanCouncil).where(
            LocalPlanCouncil.local_plan_id == plan.id, LocalPlanCouncil.council_code == ERRONEOUS_COUNCIL,
        )
    ).scalars().first()

    if existing is None:
        return {"plan_found": True, "row_removed": False, "stockport_pfe_allocations": 0}

    if not dry_run:
        session.delete(existing)
        session.commit()

    return {"plan_found": True, "row_removed": True, "stockport_pfe_allocations": 0}


def main() -> None:
    args = parse_args()
    init_db()
    session = get_session()

    result = fix(session, dry_run=args.dry_run)

    if not result["plan_found"]:
        print(f"[fix-pfe-stockport-membership] No LocalPlan found named {PFE_PLAN_NAME!r} - nothing to do.")
        return

    if result["row_removed"]:
        verb = "would be removed" if args.dry_run else "removed"
        print(f"[fix-pfe-stockport-membership] Stockport's erroneous PfE participating-authority link {verb}.")
    else:
        print("[fix-pfe-stockport-membership] No erroneous Stockport PfE link found - already correct, no changes.")
    if args.dry_run:
        print("[fix-pfe-stockport-membership] --dry-run: no changes were written")


if __name__ == "__main__":
    main()
