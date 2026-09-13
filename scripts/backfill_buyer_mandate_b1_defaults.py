"""Buyer Mandate V2, Phase B1 (Structured Mandate Domain Expansion) -
one-time backfill of the five new BuyerMandate structural fields
(geography, acquisition types, development-state appetite, control
appetite) onto every pre-existing, known-template mandate whose
geography_scope is still NULL (i.e. every mandate created before Phase B1
added these columns - in practice, production's own four Phase A mandates).

Orchestrates ONLY app.policy.buyer_profile_store.backfill_buyer_mandate_b1_
defaults, which itself calls the same seed_default_buyer_profiles() every
other reseed already goes through - see that function's own docstring for
the idempotent, non-destructive "only fill in what's genuinely missing"
contract, and for the one-time fingerprint-baseline-migration it performs
for an already-onboarded mandate (recomputing matching_fingerprint under
the new, complete field set WITHOUT re-running the opportunity-universe
scan - Phase B1 does not change assess_buyer_fit's own output, so a
re-scan would be wasted production work).

Dry-run (the default, no flags needed) makes ZERO database mutations -
reports exactly what WOULD be backfilled for each known-template mandate:

    python -m scripts.backfill_buyer_mandate_b1_defaults

Production write mode requires BOTH flags together (same deliberate-
friction pattern as every other population/migration script in this
codebase):

    python -m scripts.backfill_buyer_mandate_b1_defaults --execute --confirm YES-BACKFILL-BUYER-MANDATE-B1

FAIL CLOSED: production write mode additionally verifies the new B1
columns actually exist on buyer_mandates before doing anything -
`scripts.migrate_schema` must have already been run.

Never touches the legacy BuyerProfile table, never touches a mandate not
seeded from a known code template (a genuinely custom future mandate is
Phase B3's own concern, not this one-time backfill's)."""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import inspect

from app.db.session import get_engine, get_session
from app.policy.buyer_profile_store import backfill_buyer_mandate_b1_defaults

CONFIRM_PHRASE = "YES-BACKFILL-BUYER-MANDATE-B1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Write to production. Requires --confirm with the exact phrase below as well.")
    parser.add_argument("--confirm", default=None, help=f"Must exactly equal '{CONFIRM_PHRASE}' to actually write. Ignored unless --execute is also given.")
    return parser.parse_args()


def _print_report(report: dict) -> None:
    print(f"workspace_id: {report['workspace_id']}")
    for key, info in report["mandates"].items():
        print(f"  {key}:")
        print(f"    needs_backfill: {info['needs_backfill']}")
        print(f"    matching_fingerprint_before: {info['matching_fingerprint_before']}")
        if "proposed_fields" in info:
            print(f"    proposed_fields: {info['proposed_fields']}")
        if "applied_fields" in info:
            print(f"    applied_fields: {info['applied_fields']}")
        if "matching_fingerprint_after" in info:
            print(f"    matching_fingerprint_after: {info['matching_fingerprint_after']}")


def main() -> None:
    args = parse_args()
    execute = bool(args.execute and args.confirm == CONFIRM_PHRASE)

    if args.execute and not execute:
        print(f"[backfill-buyer-mandate-b1] --execute given without the exact --confirm phrase ({CONFIRM_PHRASE!r}) - refusing to write.")
        sys.exit(1)

    if execute:
        engine = get_engine()
        columns = {c["name"] for c in inspect(engine).get_columns("buyer_mandates")}
        missing = {"geography_scope", "geography_councils", "acquisition_types", "development_state_appetite", "control_appetite"} - columns
        if missing:
            print(f"[backfill-buyer-mandate-b1] Missing column(s) {sorted(missing)} on buyer_mandates - run `python -m scripts.migrate_schema` first.")
            sys.exit(1)

    session = get_session()
    try:
        report = backfill_buyer_mandate_b1_defaults(session, dry_run=not execute)
    finally:
        session.close()

    print(f"[backfill-buyer-mandate-b1] {'DRY RUN - zero database mutations were made' if not execute else 'PRODUCTION WRITE MODE - database was updated'}")
    print()
    _print_report(report)
    print()
    print("[backfill-buyer-mandate-b1] RESULT: " + ("DRY RUN COMPLETE - NO WRITES MADE" if not execute else "BACKFILL COMPLETE"))


if __name__ == "__main__":
    main()
