"""Stage 3B historical scan-state cutover (CLI).

Marks every Document that already existed BEFORE deployment as "already
allocation-evidence scanned" (allocation_evidence_scanned_at = cutoff),
so a normal Daily Discovery run's incremental app.policy.
allocation_evidence_scan never has to rescan the entire historic corpus
(already covered by Stage 2C's own historical batch mechanism) just to
initialise scan state. See app.policy.allocation_evidence_scan's own
"Historical scan-state cutover" section for the full design rationale.

Dry-run (the default, no flags needed) is READ ONLY - makes zero database
mutations:

    python -m scripts.backfill_allocation_evidence_scan_state

Production write mode requires BOTH flags together (same deliberate-
friction pattern as every other Stage 2/3 script in this codebase):

    python -m scripts.backfill_allocation_evidence_scan_state --execute --confirm YES-BACKFILL-ALLOCATION-EVIDENCE-SCAN-STATE

INTENDED TIMING: run this ONCE, during deployment, between
`scripts.migrate_schema` and allowing the Daily Discovery cron job to
resume - the same established deployment order this codebase already
documents (docs/PLATFORM_ARCHITECTURE.md). Idempotent - safe to run more
than once regardless.
"""
from __future__ import annotations

import argparse
import sys

from app.db.session import get_session, init_db
from app.policy.allocation_evidence_scan import apply_historical_scan_state_backfill, backfill_historical_scan_state

CONFIRM_PHRASE = "YES-BACKFILL-ALLOCATION-EVIDENCE-SCAN-STATE"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Write scan-state backfill to production. Requires --confirm with the exact phrase below as well.")
    parser.add_argument("--confirm", default=None, help=f"Must exactly equal '{CONFIRM_PHRASE}' to actually write. Ignored unless --execute is also given.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    production_mode = args.execute
    if production_mode and args.confirm != CONFIRM_PHRASE:
        print(f"[allocation-evidence-scan-backfill] --execute requires --confirm '{CONFIRM_PHRASE}' exactly - refusing to write.", file=sys.stderr)
        sys.exit(2)

    init_db()
    session = get_session()

    if production_mode:
        print("[allocation-evidence-scan-backfill] PRODUCTION WRITE MODE - this WILL write to the database\n")
        result = apply_historical_scan_state_backfill(session)
        print("=== WRITE RESULT ===")
        print(f"cutoff: {result['cutoff'].isoformat()}")
        print(f"documents marked scanned: {result['marked_count']}")
        print("\n=== RESULT ===")
        print("PRODUCTION WRITE COMPLETE")
        return

    print("[allocation-evidence-scan-backfill] DRY RUN - zero database mutations will be made\n")
    plan = backfill_historical_scan_state(session)
    print(f"cutoff: {plan['cutoff'].isoformat()}")
    print(f"documents eligible to be marked scanned: {plan['count']}")

    print("\n=== RESULT ===")
    print("DRY RUN COMPLETE - NO WRITES MADE")


if __name__ == "__main__":
    main()
