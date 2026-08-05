"""Sprint 3G ("Places for Everyone Allocation Onboarding") - creates
LocalPlanSite rows for every Places for Everyone allocation NOT already
represented (Bury's JPA 7/8/9 already exist since Sprint 2 and are never
recreated here), from config/pfe_allocation_onboarding.yaml's page-sourced
findings (Part 1/2).

Reuses the exact same "protect trusted state" architecture every other
ingestion path in this codebase already uses:
  - app.policy.status.derive_allocation_status_from_plan_status /
    app.policy.progression.classify_progression, the same functions
    ingest_local_plan.py and scripts.migrate_policy_intelligence already
    call for a brand-new allocation.
  - app.policy.history.snapshot_allocation for the very first
    AllocationVersion row, the same pattern every other ingestion path uses.
  - AllocationRelationship (Sprint 3E) for the Northern Gateway
    duplicate-across-plans case (Part 3) - never a second LocalPlanSite row
    for the same physical site, exactly Sprint 3E's own established pattern
    for Seedfield/Walshaw/Elton Reservoir, just applied here.

Idempotent: a LocalPlanSite is found-or-created by (local_plan_id,
policy_reference) - rerunning never creates a duplicate row, and never
overwrites a row that already exists (Part 8: "do not create duplicate
LocalPlanSite rows" - matches exactly, since Bury's own JPA 7/8/9 already
exist and must never be touched by this module at all).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AllocationRelationship, AllocationVersion, LocalPlan, LocalPlanSite
from app.policy.progression import classify_progression
from app.policy.status import derive_allocation_status_from_plan_status

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PFE_ONBOARDING_YAML = PROJECT_ROOT / "config" / "pfe_allocation_onboarding.yaml"

SOURCE_DOCUMENT_URL = (
    "https://www.greatermanchester-ca.gov.uk/media/9578/"
    "places-for-everyone-joint-development-plan-document.pdf"
)


def load_onboarding_config(path: Path = PFE_ONBOARDING_YAML) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _resolve_plan(session: Session, config: dict) -> LocalPlan | None:
    return session.execute(
        select(LocalPlan).where(
            LocalPlan.plan_name == config["plan_name"], LocalPlan.plan_version == config["plan_version"],
        )
    ).scalar_one_or_none()


def _existing_allocation(session: Session, local_plan_id: int, policy_reference: str) -> LocalPlanSite | None:
    return session.execute(
        select(LocalPlanSite).where(
            LocalPlanSite.local_plan_id == local_plan_id, LocalPlanSite.policy_reference == policy_reference,
        )
    ).scalar_one_or_none()


def _create_allocation(session: Session, plan: LocalPlan, entry: dict, dry_run: bool) -> LocalPlanSite | None:
    """entry: one dict from either single_authority_allocations or
    cross_boundary_allocations - both share the same required keys."""
    derived_status, derived_note = derive_allocation_status_from_plan_status(plan.raw_status)
    review_status = entry.get("review_status", "auto_applied")

    row = LocalPlanSite(
        council_code=entry["council_code"], local_plan_id=plan.id,
        policy_reference=entry["policy_reference"], site_name=entry["site_name"],
        minimum_dwellings=entry.get("minimum_dwellings"),
        intended_use=entry.get("intended_use", "residential"),
        category=entry.get("category"),
        allocation_status=derived_status, raw_allocation_status=derived_note,
        plan_name=plan.plan_name, plan_status=plan.raw_status or plan.status,
        source_document_url=SOURCE_DOCUMENT_URL, source_page=entry.get("source_page"),
        review_status=review_status,
    )
    signal, reasons = classify_progression(plan.status, row.allocation_status, present_in_latest_version=True)
    row.progression_signal = signal
    row.progression_reasons = json.dumps(reasons)
    row.progression_computed_at = dt.datetime.now(dt.timezone.utc)

    if dry_run:
        return None

    session.add(row)
    session.flush()  # assigns row.id, needed for AllocationVersion below
    session.add(AllocationVersion(
        allocation_id=row.id, local_plan_id=plan.id,
        policy_reference=row.policy_reference, site_name=row.site_name,
        minimum_dwellings=row.minimum_dwellings, category=row.category,
        allocation_status=row.allocation_status, raw_allocation_status=row.raw_allocation_status,
        change_reason="new_allocation",
    ))
    return row


def _find_bury_local_plan_site(session: Session, site_name: str) -> LocalPlanSite | None:
    """Looks up an existing allocation under Bury's OWN separate Local Plan
    (never Places for Everyone) by site_name - used only for the Northern
    Gateway duplicate-across-plans relationship (Part 3), the exact
    Sprint 3E pattern."""
    return session.execute(
        select(LocalPlanSite).where(
            LocalPlanSite.council_code == "bury", LocalPlanSite.plan_name == "Bury Local Plan",
            LocalPlanSite.site_name == site_name,
        )
    ).scalars().first()


def _has_relationship(session: Session, from_id: int, to_id: int | None, relationship_type: str) -> bool:
    query = select(AllocationRelationship).where(
        AllocationRelationship.from_allocation_id == from_id, AllocationRelationship.relationship_type == relationship_type,
    )
    if to_id is not None:
        query = query.where(AllocationRelationship.to_allocation_id == to_id)
    return session.execute(query).first() is not None


def onboard_pfe_allocations(session: Session, config: dict | None = None, dry_run: bool = False) -> dict:
    """Idempotent. Returns counts: {"created", "already_existed",
    "by_council": {code: count}, "relationships_created",
    "plan_not_found"}."""
    config = config if config is not None else load_onboarding_config()
    plan = _resolve_plan(session, config)
    if plan is None:
        return {"created": 0, "already_existed": 0, "by_council": {}, "relationships_created": 0, "plan_not_found": True}

    created = 0
    already_existed = 0
    by_council: dict[str, int] = {}
    relationships_created = 0
    created_rows: dict[str, LocalPlanSite] = {}  # policy_reference -> row, for the sibling-linking pass below

    all_entries = list(config.get("single_authority_allocations", [])) + list(config.get("cross_boundary_allocations", []))

    for entry in all_entries:
        existing = _existing_allocation(session, plan.id, entry["policy_reference"])
        if existing is not None:
            already_existed += 1
            continue
        row = _create_allocation(session, plan, entry, dry_run)
        created += 1
        by_council[entry["council_code"]] = by_council.get(entry["council_code"], 0) + 1
        if row is not None:
            created_rows[entry["policy_reference"]] = row

    if not dry_run:
        session.commit()

    # Cross-boundary relationship linking (Part 3) - only meaningful once
    # the rows above actually exist (skipped entirely on --dry-run, which
    # writes nothing to link against).
    if not dry_run:
        for entry in config.get("cross_boundary_allocations", []):
            link_target_name = entry.get("link_to_bury_local_plan_site")
            row = created_rows.get(entry["policy_reference"]) or _existing_allocation(session, plan.id, entry["policy_reference"])
            if row is None:
                continue

            if link_target_name:
                bury_row = _find_bury_local_plan_site(session, link_target_name)
                if bury_row is not None and not _has_relationship(session, row.id, bury_row.id, "same_physical_site"):
                    session.add(AllocationRelationship(
                        from_allocation_id=row.id, to_allocation_id=bury_row.id, relationship_type="same_physical_site",
                        confidence=0.9, note=entry.get("confidence_note", "").strip(),
                        source_document_url=SOURCE_DOCUMENT_URL, source_page=entry.get("source_page"),
                        review_status="needs_review",
                    ))
                    relationships_created += 1

            sibling_ref = entry.get("sibling_reference")
            if sibling_ref:
                sibling_row = created_rows.get(sibling_ref) or _existing_allocation(session, plan.id, sibling_ref)
                if sibling_row is not None and not _has_relationship(session, row.id, sibling_row.id, "implemented_through_joint_plan"):
                    session.add(AllocationRelationship(
                        from_allocation_id=row.id, to_allocation_id=sibling_row.id, relationship_type="implemented_through_joint_plan",
                        confidence=0.9, note="Both sub-allocations of the same Atom Valley MDZ-designated strategic site.",
                        source_document_url=SOURCE_DOCUMENT_URL, source_page=entry.get("source_page"),
                        review_status="needs_review",
                    ))
                    relationships_created += 1
        session.commit()

    return {
        "created": created, "already_existed": already_existed, "by_council": by_council,
        "relationships_created": relationships_created, "plan_not_found": False,
    }
