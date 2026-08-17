"""Stage 4B.1 - deterministic ownership/control production population (CLI).

Orchestrates ONLY the existing, already-approved Stage 4B building blocks
(app.extraction.ownership_control_evidence's deterministic extractors,
app.enrichment.control_entities.create_control_relationship_if_absent) via
app.enrichment.control_population.run_control_relationship_population - see
that module's own docstring for exactly which evidence classes are ever
persisted and why. Introduces no new extraction/persistence logic here.

Dry-run (the default, no flags needed) is READ ONLY - makes zero database
mutations, and works whether or not the control_relationships table exists
yet (identical evidence-evaluation code path either way):

    python -m scripts.populate_control_relationships
    python -m scripts.populate_control_relationships --council wigan

Production write mode requires BOTH flags together (same deliberate-
friction pattern as every other Stage 2/3/4 script in this codebase):

    python -m scripts.populate_control_relationships --execute --confirm YES-POPULATE-CONTROL-RELATIONSHIPS

FAIL CLOSED: production write mode additionally verifies the
control_relationships table actually exists before doing anything -
`scripts.migrate_schema` must have already been run. This script never
runs a migration itself.

INTENDED TIMING: run this AFTER `scripts.migrate_schema` +
`scripts.verify_schema` have confirmed the schema is current, as a
distinct, explicitly-triggered step - never automatically from
run_weekly.py/run_daily_councils.py (this is a one-off/periodically-
rerun population pass over the existing corpus, not a per-document hot-
path stage; see app.enrichment.control_population's own module docstring
for why re-running it is always safe/idempotent regardless)."""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import inspect

from app.db.models import ControlRelationship
from app.db.session import get_engine, get_session, init_db
from app.enrichment.control_population import run_control_relationship_population

CONFIRM_PHRASE = "YES-POPULATE-CONTROL-RELATIONSHIPS"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--council", default=None, help="Restrict to one council code (e.g. wigan). Default: every council.")
    parser.add_argument("--execute", action="store_true", help="Write to production. Requires --confirm with the exact phrase below as well.")
    parser.add_argument("--confirm", default=None, help=f"Must exactly equal '{CONFIRM_PHRASE}' to actually write. Ignored unless --execute is also given.")
    return parser.parse_args()


def _print_report(report) -> None:
    print(f"application_forms_evaluated: {report.application_forms_evaluated}")
    print(f"  certificate_a_count: {report.certificate_a_count}")
    print(f"  certificate_b_count: {report.certificate_b_count}")
    print(f"  certificate_c_count: {report.certificate_c_count}")
    print(f"  certificate_d_count: {report.certificate_d_count}")
    print(f"  certificate_ambiguous_count: {report.certificate_ambiguous_count}")
    print(f"  certificate_no_evidence_count: {report.certificate_no_evidence_count}")
    print(f"  certificate_a_no_entity_available: {report.certificate_a_no_entity_available}")
    print(f"  certificate_bcd_reported_no_entity (never persisted): {report.certificate_bcd_reported_no_entity}")
    print(f"s106_documents_evaluated: {report.s106_documents_evaluated}")
    print(f"  s106_title_numbers_found: {report.s106_title_numbers_found}")
    print(f"  s106_title_numbers_without_party: {report.s106_title_numbers_without_party}")
    print(f"  s106_owner_hits: {report.s106_owner_hits}")
    print(f"  s106_developer_hits: {report.s106_developer_hits}")
    print(f"  s106_mortgagee_hits: {report.s106_mortgagee_hits}")
    print(f"relationships_would_create: {report.relationships_would_create}")
    print(f"relationships_created: {report.relationships_created}")
    print(f"relationships_already_present: {report.relationships_already_present}")
    print(f"conflicting_evidence_cases: {report.conflicting_evidence_cases}")
    print(f"company_resolved_count: {report.company_resolved_count}")
    print(f"unresolved_entity_count: {report.unresolved_entity_count}")
    print(f"semantic_review_excluded_count: {report.semantic_review_excluded_count}")
    print(f"applications_with_deterministic_evidence: {report.applications_with_deterministic_evidence}")
    print(f"sites_with_deterministic_evidence: {report.sites_with_deterministic_evidence}")
    print(f"documents_failed: {report.documents_failed}")
    if report.errors:
        print("errors:")
        for err in report.errors:
            print(f"  - {err}")


def main() -> None:
    args = parse_args()

    production_mode = args.execute
    if production_mode and args.confirm != CONFIRM_PHRASE:
        print(f"[populate-control-relationships] --execute requires --confirm '{CONFIRM_PHRASE}' exactly - refusing to write.", file=sys.stderr)
        sys.exit(2)

    init_db()
    session = get_session()

    if production_mode:
        engine = get_engine()
        if not inspect(engine).has_table(ControlRelationship.__tablename__):
            print(
                "[populate-control-relationships] control_relationships table does not exist yet - "
                "run `python -m scripts.migrate_schema` first. Refusing to write.",
                file=sys.stderr,
            )
            sys.exit(2)

        print("[populate-control-relationships] PRODUCTION WRITE MODE - this WILL write to the database\n")
        report = run_control_relationship_population(session, council_code=args.council, dry_run=False)
        print("=== WRITE RESULT ===")
        _print_report(report)
        print("\n=== RESULT ===")
        print("PRODUCTION WRITE COMPLETE")
        return

    print("[populate-control-relationships] DRY RUN - zero database mutations will be made\n")
    report = run_control_relationship_population(session, council_code=args.council, dry_run=True)
    print("=== DRY RUN RESULT ===")
    _print_report(report)
    print("\n=== RESULT ===")
    print("DRY RUN COMPLETE - NO WRITES MADE")


if __name__ == "__main__":
    main()
