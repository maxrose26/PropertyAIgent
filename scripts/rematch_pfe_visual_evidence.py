"""Sprint 3G ("Places for Everyone Allocation Onboarding", Part 4/5) - re-runs
deterministic matching for a Local Plan's already-extracted VisualEvidence
rows against its current (possibly since-grown) set of allocations. No
rendering, no Vision call, no source PDF read at all - see
app.visuals.pipeline.rematch_local_plan_evidence.

    python -m scripts.rematch_pfe_visual_evidence --local-plan-id 2 [--dry-run]
"""
from __future__ import annotations

import argparse

from app.db.models import LocalPlan
from app.db.session import get_session, init_db
from app.visuals.pipeline import rematch_local_plan_evidence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-plan-id", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing anything.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    init_db()
    session = get_session()

    plan = session.get(LocalPlan, args.local_plan_id)
    if plan is None:
        raise ValueError(f"No LocalPlan {args.local_plan_id} found")

    stats = rematch_local_plan_evidence(session, args.local_plan_id, dry_run=args.dry_run)

    verb = "would be" if args.dry_run else "were"
    print(f"[rematch-pfe-visual-evidence] plan: {plan.plan_name!r}")
    print(f"[rematch-pfe-visual-evidence] {stats.candidates_considered} unlinked current row(s) considered")
    print(f"[rematch-pfe-visual-evidence] {stats.newly_linked} {verb} newly linked to an allocation")
    print(f"[rematch-pfe-visual-evidence] {stats.secondary_page_suggestions} secondary-page review suggestion(s) {verb} recorded")
    print(f"[rematch-pfe-visual-evidence] {stats.skipped_confirmed} skipped (already confirmed) | "
          f"{stats.skipped_rejected} skipped (rejected) | {stats.unmatched} remain unmatched")
    if args.dry_run:
        print("[rematch-pfe-visual-evidence] --dry-run: no changes were written")


if __name__ == "__main__":
    main()
