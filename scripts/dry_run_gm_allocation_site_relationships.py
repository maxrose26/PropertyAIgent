"""GM Allocation <-> Site relationship dry-run / controlled write (Stage 2D, CLI).

Dry-run (the default, no flags needed) is READ ONLY - makes zero database
mutations. See app.policy.allocation_site_relationships for the full
design rationale (why a new AllocationSiteRelationship table, evidence
eligibility rules, matched_site_id convenience-pointer behaviour).

    python -m scripts.dry_run_gm_allocation_site_relationships

Production write mode requires BOTH flags together - --execute alone does
nothing but print an error (same deliberate-friction pattern as every
other Stage 2 CLI script in this codebase). Writes ONLY the legacy
matched_site_id backfill and the new deterministic document-evidence
relationships (DOCUMENT_CONFIRMED_SITE / FUZZY_SUPPORTED_BY_DOCUMENT /
MULTIPLE_DOCUMENT_SUPPORTED_SITES) - fuzzy-only, contradicted, and
application-only-evidence allocations are never written:

    python -m scripts.dry_run_gm_allocation_site_relationships --execute --confirm YES-CREATE-GM-ALLOCATION-SITE-RELATIONSHIPS
"""
from __future__ import annotations

import argparse
import sys

from app.db.session import get_session, init_db
from app.policy.allocation_site_relationships import run_controlled_relationship_write, run_relationship_dry_run

CONFIRM_PHRASE = "YES-CREATE-GM-ALLOCATION-SITE-RELATIONSHIPS"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Write relationships to production. Requires --confirm with the exact phrase below as well.")
    parser.add_argument("--confirm", default=None, help=f"Must exactly equal '{CONFIRM_PHRASE}' to actually write. Ignored unless --execute is also given.")
    return parser.parse_args()


def _print_report(report) -> None:
    print("=== LEGACY matched_site_id BACKFILL ===")
    print(f"to backfill: {len(report.legacy_backfill)}")
    for p in report.legacy_backfill:
        print(f"  allocation {p.allocation_id} -> site {p.site_id} (confidence={p.confidence})")

    print("\n=== NEW DOCUMENT-EVIDENCE RELATIONSHIPS ===")
    print(f"to create: {len(report.new_document_relationships)}")
    by_allocation: dict[int, list] = {}
    for p in report.new_document_relationships:
        by_allocation.setdefault(p.allocation_id, []).append(p)
    first_relationship = [a for a, ps in by_allocation.items() if len(ps) == 1]
    multi_relationship = [a for a, ps in by_allocation.items() if len(ps) > 1]
    print(f"allocations gaining their first accepted relationship: {len(first_relationship)}")
    print(f"allocations gaining MULTIPLE relationships: {len(multi_relationship)}")
    for allocation_id, planned_list in by_allocation.items():
        print(f"  allocation {allocation_id}: {len(planned_list)} relationship(s)")
        for p in planned_list:
            print(f"      -> site {p.site_id} ({p.evidence_basis}, category={p.evidence_category})")

    print("\n=== ALREADY PRESENT (skipped, idempotent) ===")
    print(f"{len(report.already_present)} pair(s) already exist")

    print("\n=== EXCLUDED ===")
    print(f"fuzzy-only (no document evidence): {len(report.fuzzy_only_excluded)} -> {report.fuzzy_only_excluded}")
    print(f"document-contradicted: {len(report.contradicted_excluded)} -> {report.contradicted_excluded}")
    print(f"review-required (weak/contextual evidence only): {len(report.review_required_excluded)}")
    print(f"application-only evidence (no Site relationship created): {len(report.application_only_evidence)}")
    for a in report.application_only_evidence:
        print(f"  allocation {a['allocation_id']} ({a['council']}/{a['policy_reference']!r}) {a['allocation_name']!r} "
              f"-> application {a['application_reference']}")


def main() -> None:
    args = parse_args()

    production_mode = args.execute
    if production_mode and args.confirm != CONFIRM_PHRASE:
        print(f"[gm-allocation-site-relationships] --execute requires --confirm '{CONFIRM_PHRASE}' exactly - refusing to write.", file=sys.stderr)
        sys.exit(2)

    init_db()
    session = get_session()

    if production_mode:
        print("[gm-allocation-site-relationships] PRODUCTION WRITE MODE - this WILL write to the database\n")
        result = run_controlled_relationship_write(session)
        print("=== WRITE RESULT ===")
        print(f"legacy backfill created: {result['created_legacy_backfill']}")
        print(f"new document relationships created: {result['created_document_relationships']}")
        print(f"already present (skipped): {result['already_present_skipped']}")
        print(f"matched_site_id convenience pointer set for: {result['matched_site_id_convenience_pointer_set']}")
        print("\n=== RESULT ===")
        print("PRODUCTION WRITE COMPLETE")
        return

    print("[gm-allocation-site-relationships] DRY RUN - zero database mutations will be made\n")
    report = run_relationship_dry_run(session)
    _print_report(report)

    print("\n=== RESULT ===")
    print("DRY RUN COMPLETE - NO WRITES MADE")


if __name__ == "__main__":
    main()
