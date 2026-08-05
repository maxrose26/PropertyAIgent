"""Builds the Policy Intelligence view of a Site - a plain-dict shape the UI
renders and tests can assert against without touching Streamlit (Part 12,
Part 15 "Site Policy display"). Kept separate from app.ui.common so the
data assembly is testable independently of rendering, per CLAUDE.md's
"keep business logic out of the UI"."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.models import LocalPlanSite


def build_site_policy_intelligence(allocations: list["LocalPlanSite"]) -> list[dict]:
    """allocations: LocalPlanSite rows already filtered to one Site (i.e.
    matched_site_id == site.id). One dict per allocation, carrying every
    field Part 12 asks for plus full source traceability (Part 13) - never
    just a summary detached from where it came from."""
    rows = []
    for allocation in allocations:
        plan = allocation.local_plan
        reasons = json.loads(allocation.progression_reasons) if allocation.progression_reasons else []
        rows.append({
            # Sprint 3E ("Joint Plan Support and Bury Allocation
            # Reconciliation", Part 4) - the caller-side stable key a UI
            # must use to look this row back up. policy_reference (below)
            # is legitimately nullable and non-unique (see LocalPlanSite's
            # own docstring) - keying a lookup off it collapsed every
            # ref=None allocation into whichever was built last, the exact
            # defect this field exists to let callers avoid.
            "allocation_id": allocation.id,
            "plan_name": plan.plan_name if plan else allocation.plan_name,
            "plan_status": plan.status if plan else None,
            "plan_raw_status": plan.raw_status if plan else allocation.plan_status,
            "allocation_reference": allocation.policy_reference,
            "allocation_name": allocation.site_name,
            "allocation_status": allocation.allocation_status,
            "allocation_raw_status": allocation.raw_allocation_status,
            "progression_signal": allocation.progression_signal,
            "progression_reasons": reasons,
            "minimum_dwellings": allocation.minimum_dwellings,
            "indicative_capacity": allocation.indicative_capacity,
            "maximum_capacity": allocation.maximum_capacity,
            "category": allocation.category,
            "source_page": allocation.source_page,
            "source_document_url": allocation.source_document_url,
            "policy_reference": allocation.policy_reference,
            "match_confidence": allocation.match_confidence,
            "last_checked": plan.last_checked if plan else None,
        })
    return rows
