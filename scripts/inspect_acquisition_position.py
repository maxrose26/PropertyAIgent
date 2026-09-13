"""Gate 2C V1 ("Acquisition Position Intelligence") - read-only diagnostic
consumer for app.reporting.acquisition_position.build_acquisition_position_facts.

The narrowest useful existing-surface integration (Section 20 of the
approved implementation prompt): AcquisitionPositionFacts is not
commercially complete if it exists only as an internal Python object
nobody can inspect. This is a plain, read-only CLI report - the same
pattern as scripts/populate_control_relationships.py's own dry-run
printer - not a new UI, not a redesign of the opportunity page.

Usage:
    python -m scripts.inspect_acquisition_position --site-id 248
    python -m scripts.inspect_acquisition_position --reference "117693/OUT/25" --council manchester

Makes zero database writes."""
from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db.models import Application, Site
from app.db.session import get_session, init_db
from app.reporting.acquisition_position import build_acquisition_position_facts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-id", type=int, default=None, help="Inspect the full application family for this Site.")
    parser.add_argument("--reference", default=None, help="Inspect a single Application by reference (with --council).")
    parser.add_argument("--council", default=None, help="Council code, required with --reference.")
    return parser.parse_args()


def _print_facts(facts) -> None:
    print(f"site_id: {facts.site_id}")
    print(f"application_ids: {facts.application_ids}")
    print(f"ownership_coverage: {facts.ownership_coverage}")
    print()
    print("evidence_coverage:")
    for k, v in vars(facts.evidence_coverage).items():
        print(f"  {k}: {v}")
    print()
    print(f"ownership_evidence ({len(facts.ownership_evidence)}):")
    for f in facts.ownership_evidence:
        print(f"  - state={f.state} entity={f.entity_name!r} entity_type={f.entity_type} company_id={f.company_id} "
              f"confidence={f.confidence} application_id={f.application_id} source={f.source} "
              f"evidence_document_id={f.evidence_document_id}")
    print()
    print(f"developer_indications ({len(facts.developer_indications)}):")
    for d in facts.developer_indications:
        print(f"  - application_id={d.application_id} developer_name={d.developer_name!r} source={d.source}")
    print()
    print(f"applicant_positions ({len(facts.applicant_positions)}):")
    for p in facts.applicant_positions:
        print(f"  - application_id={p.application_id} raw_applicant_name={p.raw_applicant_name!r} "
              f"identity_ref={p.resolved_identity_ref} primary_type={p.applicant_intelligence_primary_type} "
              f"primary_type_confidence={p.applicant_intelligence_confidence} is_spv={p.is_spv} "
              f"applicant_intelligence_available={p.applicant_intelligence_available}")
    print()
    print(f"control_relationships (persisted, {len(facts.control_relationships)}):")
    for r in facts.control_relationships:
        print(f"  - role={r.role} entity={r.entity_name!r} entity_type={r.entity_type} company_id={r.company_id} "
              f"evidence_basis={r.evidence_basis} evidence_category={r.evidence_category} "
              f"review_status={r.review_status} confidence={r.confidence}")
    print()
    print(f"conflicts ({len(facts.conflicts)}):")
    for c in facts.conflicts:
        print(f"  - {c}")


def main() -> None:
    args = parse_args()
    init_db()
    session = get_session()

    if args.site_id is not None:
        site = session.get(Site, args.site_id)
        if site is None:
            print(f"No Site with id={args.site_id}")
            return
        applications = list(site.applications)
        print(f"Site {site.id}: {site.canonical_address}")
        print(f"Application family: {[a.reference for a in applications]}")
    elif args.reference and args.council:
        app = session.execute(
            select(Application).where(Application.council_code == args.council, Application.reference == args.reference)
        ).scalar_one_or_none()
        if app is None:
            print(f"No Application {args.reference!r} in council {args.council!r}")
            return
        applications = [app]
        if app.site_id is not None:
            site = session.get(Site, app.site_id)
            applications = list(site.applications) if site else [app]
            print(f"Site {app.site_id}: expanded to full application family {[a.reference for a in applications]}")
        else:
            print(f"Application {app.reference} has no site_id - inspecting on its own (narrower scope, per Section 11).")
    else:
        print("Provide either --site-id or --reference with --council. See module docstring for usage.")
        return

    print()
    facts = build_acquisition_position_facts(session, applications)
    _print_facts(facts)


if __name__ == "__main__":
    main()
