"""Sprint 3E ("Joint Plan Support and Bury Allocation Reconciliation", Part
5-6) - turns config/bury_allocation_reconciliation.yaml's investigated,
page-sourced findings into reviewable proposals. Never mutates a
LocalPlanSite row directly: every entry here only ever creates a
PolicyChangeEvent (review_status="needs_review", resolved the normal way
via app.policy.review.approve_change/reject_change) and an
AllocationRelationship (also "needs_review") - the same "protect trusted
state from ambiguous changes" discipline every other ingestion/monitoring
path in this codebase already follows.

    python -m scripts.propose_bury_allocation_reconciliation [--dry-run]
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AllocationRelationship, LocalPlanSite, PolicyChangeEvent

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RECONCILIATION_YAML = PROJECT_ROOT / "config" / "bury_allocation_reconciliation.yaml"

EVENT_TYPE = "duplicate_name_reconciliation_proposed"


def load_reconciliation_config(path: Path = RECONCILIATION_YAML) -> list[dict]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("reconciliations", [])


def _find_allocation(
    session: Session, council_code: str, plan_name: str, site_name: str, policy_reference: str | None,
) -> LocalPlanSite | None:
    conditions = [
        LocalPlanSite.council_code == council_code,
        LocalPlanSite.plan_name == plan_name,
        LocalPlanSite.site_name == site_name,
    ]
    conditions.append(
        LocalPlanSite.policy_reference.is_(None) if policy_reference is None
        else LocalPlanSite.policy_reference == policy_reference
    )
    return session.execute(select(LocalPlanSite).where(*conditions)).scalar_one_or_none()


def _has_pending_or_resolved_proposal(session: Session, allocation_id: int) -> bool:
    return session.execute(
        select(PolicyChangeEvent).where(
            PolicyChangeEvent.allocation_id == allocation_id,
            PolicyChangeEvent.event_type == EVENT_TYPE,
            PolicyChangeEvent.review_status.in_(["needs_review", "confirmed"]),
        )
    ).first() is not None


def _has_existing_relationship(session: Session, from_allocation_id: int, relationship_type: str) -> bool:
    return session.execute(
        select(AllocationRelationship).where(
            AllocationRelationship.from_allocation_id == from_allocation_id,
            AllocationRelationship.relationship_type == relationship_type,
        )
    ).first() is not None


def propose_reconciliations(session: Session, config: list[dict] | None = None, dry_run: bool = False) -> dict:
    """Idempotent: an allocation that already has a pending OR resolved
    duplicate_name_reconciliation_proposed event is skipped entirely on a
    rerun (never a second, competing proposal for the same row); a
    relationship of the same type from the same allocation is likewise
    never duplicated. Allocations named in the config that no longer exist,
    or were never matched in the first place, are reported in
    allocations_not_found rather than raising - config entries are
    investigation findings, not a hard schema this must match exactly
    forever."""
    config = config if config is not None else load_reconciliation_config()

    proposals_created = 0
    relationships_created = 0
    skipped_already_proposed = 0
    not_found: list[str] = []

    for entry in config:
        from_allocation = _find_allocation(
            session, entry["council_code"], entry["plan_name"], entry["site_name"], entry.get("policy_reference"),
        )
        if from_allocation is None:
            not_found.append(f"{entry['council_code']}/{entry['plan_name']}/{entry['site_name']}")
            continue

        if _has_pending_or_resolved_proposal(session, from_allocation.id):
            skipped_already_proposed += 1
            continue

        to_allocation = None
        if entry.get("to_site_name"):
            to_allocation = _find_allocation(
                session, entry["council_code"], entry["to_plan_name"], entry["to_site_name"],
                entry.get("to_policy_reference"),
            )

        note = (entry.get("note") or "").strip()
        source_excerpt = (entry.get("source_excerpt") or "").strip() or None

        if not dry_run:
            session.add(PolicyChangeEvent(
                local_plan_id=from_allocation.local_plan_id, allocation_id=from_allocation.id,
                event_type=EVENT_TYPE, old_value=None, new_value=entry["classification"],
                detail=note,
                proposed_data=json.dumps({
                    "duplicate_classification": entry["classification"],
                    "duplicate_classification_note": note,
                }),
                source_document_url=entry.get("source_document_url"), source_page=entry.get("source_page"),
                source_excerpt=source_excerpt,
                extraction_method="manual_primary_source_review",
                confidence=entry.get("confidence"),
                auto_applied=False, review_status="needs_review",
            ))
        proposals_created += 1

        if not _has_existing_relationship(session, from_allocation.id, entry["relationship_type"]):
            if not dry_run:
                session.add(AllocationRelationship(
                    from_allocation_id=from_allocation.id,
                    to_allocation_id=to_allocation.id if to_allocation else None,
                    relationship_type=entry["relationship_type"],
                    confidence=entry.get("confidence"),
                    note=note,
                    source_document_url=entry.get("source_document_url"), source_page=entry.get("source_page"),
                    source_excerpt=source_excerpt,
                    review_status="needs_review",
                ))
            relationships_created += 1

    if not dry_run:
        session.commit()

    return {
        "proposals_created": proposals_created,
        "relationships_created": relationships_created,
        "skipped_already_proposed": skipped_already_proposed,
        "allocations_not_found": not_found,
    }
