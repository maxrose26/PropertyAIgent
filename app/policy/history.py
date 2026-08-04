"""Shared "snapshot before you overwrite" helpers (Part 10 of the original
sprint: never lose history). Used by ingest_local_plan.py, scripts.
migrate_policy_intelligence, and app.policy.review - one implementation, so
every code path that's allowed to change a trusted LocalPlan/LocalPlanSite
value writes the same shape of history record, not three slightly
different ones."""
from __future__ import annotations

from app.db.models import AllocationVersion, LocalPlan, LocalPlanSite, LocalPlanStatusHistory


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
