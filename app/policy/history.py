"""Shared "snapshot before you overwrite" helpers (Part 10 of the original
sprint: never lose history). Used by ingest_local_plan.py, scripts.
migrate_policy_intelligence, and app.policy.review - one implementation, so
every code path that's allowed to change a trusted LocalPlan/LocalPlanSite
value writes the same shape of history record, not three slightly
different ones."""
from __future__ import annotations

from app.db.models import AllocationVersion, LocalPlan, LocalPlanFieldHistory, LocalPlanSite, LocalPlanStatusHistory


def snapshot_field(session, plan: LocalPlan, field_name: str, old_value, new_value, change_reason: str | None = None) -> None:
    """Generic per-field pre-change snapshot for the Sprint 3B evidence
    fields (see LocalPlanFieldHistory's own docstring for why this is
    separate from snapshot_plan_status below, which stays exactly as
    Sprint 1 built it). old_value/new_value are whatever the field's own
    Python type is (int, float, str, None) - stored as text since this
    table exists purely as a human-readable audit trail, not something
    re-typed back into a live field."""
    session.add(LocalPlanFieldHistory(
        local_plan_id=plan.id, field_name=field_name,
        old_value=None if old_value is None else str(old_value),
        new_value=None if new_value is None else str(new_value),
        change_reason=change_reason,
    ))


def snapshot_allocation(session, row: LocalPlanSite, change_reason: str) -> None:
    session.add(AllocationVersion(
        allocation_id=row.id, local_plan_id=row.local_plan_id,
        policy_reference=row.policy_reference, site_name=row.site_name,
        minimum_dwellings=row.minimum_dwellings, indicative_capacity=row.indicative_capacity,
        maximum_capacity=row.maximum_capacity, category=row.category,
        allocation_status=row.allocation_status, raw_allocation_status=row.raw_allocation_status,
        change_reason=change_reason,
    ))


def snapshot_plan_status(session, plan: LocalPlan, note: str | None = None) -> None:
    session.add(LocalPlanStatusHistory(
        local_plan_id=plan.id, status=plan.status, raw_status=plan.raw_status,
        plan_version=plan.plan_version, note=note,
    ))
