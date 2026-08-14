"""Complete GM Local Plan Baseline - production ingestion runner (CLI).

Reads the frozen manifests in config/gm_local_plan_baseline/ and creates/
updates LocalPlan + LocalPlanSite rows. Never touches
gm_local_plan_relationship_review.json or gm_local_plan_ah_sidecar.json -
both are explicitly deferred/review-only, see
app.policy.gm_baseline_ingestion's module docstring.

Dry-run (the default - makes ZERO database mutations):

    python -m scripts.ingest_gm_local_plan_baseline
    python -m scripts.ingest_gm_local_plan_baseline --dry-run

Production write mode requires BOTH flags together - --execute alone does
nothing but print an error. This is deliberate friction (Requirement 3:
"must be explicit and difficult to trigger accidentally"), not a bug:

    python -m scripts.ingest_gm_local_plan_baseline --execute --confirm YES-INGEST-GM-BASELINE-TO-PRODUCTION

If baseline/manifest validation fails, or any update target is unresolved,
nothing is written at all (fail closed) regardless of --execute.
"""
from __future__ import annotations

import argparse
import sys

from app.db.session import get_session, init_db
from app.policy.gm_baseline_ingestion import ingest_gm_baseline

CONFIRM_PHRASE = "YES-INGEST-GM-BASELINE-TO-PRODUCTION"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report what would happen. Zero database mutations. This is also the default with no flags.")
    parser.add_argument("--execute", action="store_true", help="Write to production. Requires --confirm with the exact phrase below as well.")
    parser.add_argument("--confirm", default=None, help=f"Must exactly equal '{CONFIRM_PHRASE}' to actually write. Ignored unless --execute is also given.")
    return parser.parse_args()


def _print_report(result: dict) -> None:
    b = result["baseline"]
    print("=== BASELINE ===")
    print(f"existing LocalPlanSite count: {b['actual']} (expected {b['expected']}, matches={b['matches']})")

    print("\n=== CREATE ===")
    print(f"total: {result['create']['total']}")
    for council, count in sorted(result["create"]["by_council"].items()):
        print(f"  {council}: {count}")

    u = result["update"]
    print("\n=== UPDATE ===")
    print(f"total: {u['total']}")
    print(f"  PfE status corrections: {u['pfe_status_corrections']}")
    print(f"  Medipark correction present: {u['medipark_correction']}")
    print(f"  Heywood/Pilsworth correction present: {u['heywood_pilsworth_correction']}")

    s = result["skipped_review_only"]
    print("\n=== SKIPPED / REVIEW ONLY (never processed by this runner) ===")
    print(f"  relationships: {s['relationships']}")
    print(f"  AH sidecar: {s['ah_sidecar']}")
    print(f"  manual review (non-blocking, informational): {s['manual_review']}")
    print(f"  excluded: {s['excluded']}")

    v = result["validation"]
    print("\n=== VALIDATION ===")
    print(f"baseline matches: {v['baseline_matches']}")
    print(f"invalid rows: {len(v['invalid_rows'])}")
    for problem in v["invalid_rows"]:
        print(f"  - {problem}")
    print(f"unresolved update targets: {len(v['unresolved_update_targets'])}")
    for target in v["unresolved_update_targets"]:
        print(f"  - {target}")
    print(f"expected final count: {v['expected_final_count']}")

    if not result["dry_run"]:
        print("\n=== WRITE RESULT ===")
        print(f"created: {result['created']}  already_existed: {result['already_existed']}")
        print(f"updated: {result['updated']}  already_applied: {result['already_applied']}")

    print("\n=== RESULT ===")
    print("READY" if result["ready"] else "NOT READY")


def main() -> None:
    args = parse_args()

    production_mode = args.execute
    if production_mode and args.confirm != CONFIRM_PHRASE:
        print(f"[gm-baseline] --execute requires --confirm '{CONFIRM_PHRASE}' exactly - refusing to write.", file=sys.stderr)
        sys.exit(2)

    dry_run = not production_mode

    init_db()
    session = get_session()

    if dry_run:
        print("[gm-baseline] DRY RUN - zero database mutations will be made\n")
    else:
        print("[gm-baseline] PRODUCTION MODE - this WILL write to the database\n")

    try:
        result = ingest_gm_baseline(session, dry_run=dry_run)
    except RuntimeError as exc:
        print(f"[gm-baseline] ABORTED before any write: {exc}", file=sys.stderr)
        sys.exit(1)

    _print_report(result)

    if not result["ready"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
