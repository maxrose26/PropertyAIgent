"""Buyer Mandate V2, Phase A (Buyer/Mandate Domain Separation) - one-time,
idempotent backfill from the legacy app.db.models.BuyerProfile table into
an equivalent Buyer + BuyerMandate pair per row.

Orchestrates ONLY app.policy.buyer_profile_store.migrate_buyer_profiles_to_
mandates - see that function's own docstring for exactly what is migrated,
matched, and left untouched.

Dry-run (the default, no flags needed) makes ZERO database mutations -
every row is read, every prospective Buyer/BuyerMandate is built and
checked (including the fingerprint cross-check), then rolled back:

    python -m scripts.migrate_buyer_profiles_to_mandates

Production write mode requires BOTH flags together (same deliberate-
friction pattern as every other Stage/Gate population script in this
codebase):

    python -m scripts.migrate_buyer_profiles_to_mandates --execute --confirm YES-MIGRATE-BUYER-MANDATES

FAIL CLOSED: production write mode additionally verifies the buyers/
buyer_mandates tables actually exist before doing anything -
`scripts.migrate_schema` must have already been run. This script never
runs a schema migration itself.

Never deletes, modifies, or writes to the legacy BuyerProfile table -
this is a pure additive backfill; see app.db.models.BuyerProfile's own
docstring for its retirement/rollback posture."""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import inspect

from app.db.session import get_engine, get_session
from app.policy.buyer_profile_store import migrate_buyer_profiles_to_mandates

CONFIRM_PHRASE = "YES-MIGRATE-BUYER-MANDATES"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Write to production. Requires --confirm with the exact phrase below as well.")
    parser.add_argument("--confirm", default=None, help=f"Must exactly equal '{CONFIRM_PHRASE}' to actually write. Ignored unless --execute is also given.")
    return parser.parse_args()


def _print_report(report: dict) -> None:
    print(f"legacy_rows_found: {report['legacy_rows_found']}")
    print(f"buyers_created: {report['buyers_created']}")
    print(f"buyers_already_present: {report['buyers_already_present']}")
    print(f"mandates_created: {report['mandates_created']}")
    print(f"mandates_already_present: {report['mandates_already_present']}")
    print(f"fingerprint_mismatches: {report['fingerprint_mismatches']}")


def main() -> None:
    args = parse_args()
    execute = bool(args.execute and args.confirm == CONFIRM_PHRASE)

    if args.execute and not execute:
        print(f"[migrate-buyer-profiles-to-mandates] --execute given without the exact --confirm phrase ({CONFIRM_PHRASE!r}) - refusing to write.")
        sys.exit(1)

    if execute:
        engine = get_engine()
        existing_tables = set(inspect(engine).get_table_names())
        missing = {"buyers", "buyer_mandates"} - existing_tables
        if missing:
            print(f"[migrate-buyer-profiles-to-mandates] Missing table(s) {sorted(missing)} - run `python -m scripts.migrate_schema` first.")
            sys.exit(1)

    session = get_session()
    try:
        report = migrate_buyer_profiles_to_mandates(session, dry_run=not execute)
    finally:
        session.close()

    print(f"[migrate-buyer-profiles-to-mandates] {'DRY RUN - zero database mutations were made' if not execute else 'PRODUCTION WRITE MODE - database was updated'}")
    print()
    _print_report(report)
    print()

    if report["fingerprint_mismatches"]:
        print(
            "[migrate-buyer-profiles-to-mandates] STOP: fingerprint mismatch(es) detected for "
            f"{report['fingerprint_mismatches']} - the migrated BuyerMandate's recomputed fingerprint did not "
            "match the legacy BuyerProfile row's own matching_fingerprint. Do not run --execute until this is "
            "investigated; this should be structurally impossible if the field-by-field copy is correct."
        )
        sys.exit(1)

    print("[migrate-buyer-profiles-to-mandates] RESULT: " + ("DRY RUN COMPLETE - NO WRITES MADE" if not execute else "MIGRATION COMPLETE"))


if __name__ == "__main__":
    main()
