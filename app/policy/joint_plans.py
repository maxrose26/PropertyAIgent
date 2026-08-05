"""Joint/multi-authority LocalPlan <-> Council linking (Sprint 3E, "Joint
Plan Support and Bury Allocation Reconciliation", Part 1-3).

LocalPlan.council_code is a single, non-nullable foreign key - correct for
almost every plan in this platform (Stockport's own plan, Bury's own plan),
but wrong for a genuinely joint plan like Places for Everyone, adopted by
nine Greater Manchester authorities as one plan. This module is the
config-driven (config/joint_plans.yaml) logic for populating and reading
the additive LocalPlanCouncil join table introduced to represent that,
without removing council_code (kept as a backwards-compatible lead/legacy
field - see LocalPlanCouncil's own docstring) and without ever creating a
second LocalPlan row for the same real-world plan.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import LocalPlan, LocalPlanCouncil

PROJECT_ROOT = Path(__file__).resolve().parents[2]
JOINT_PLANS_YAML = PROJECT_ROOT / "config" / "joint_plans.yaml"


def load_joint_plans_config(path: Path = JOINT_PLANS_YAML) -> list[dict]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("joint_plans", [])


def find_joint_plan_entry(plan: LocalPlan, config: list[dict] | None = None) -> dict | None:
    """Matches a LocalPlan against config/joint_plans.yaml on the same
    (council_code, plan_name, plan_version) triple LocalPlan itself is
    uniquely constrained on - a plan with no matching entry is simply not a
    joint plan, not an error."""
    config = config if config is not None else load_joint_plans_config()
    for entry in config:
        if (
            entry.get("council_code") == plan.council_code
            and entry.get("plan_name") == plan.plan_name
            and entry.get("plan_version") == plan.plan_version
        ):
            return entry
    return None


def ensure_council_links_for_plan(
    session: Session, plan: LocalPlan, config: list[dict] | None = None, dry_run: bool = False,
) -> dict:
    """Idempotent: find-or-create LocalPlanCouncil rows for one LocalPlan.

    A joint-plan config entry links every confirmed participating
    authority. A plan with no config entry gets exactly one row (its
    existing council_code, role="legacy_owner") - this is what makes a
    single-authority plan safe by construction: nothing about an ordinary
    plan changes shape, it just gets one join row mirroring what
    council_code already said.

    Never removes or reassigns an existing LocalPlanCouncil row - reruns
    only ever ADD rows that don't already exist (matched on council_code,
    the same column the DB's own (local_plan_id, council_code) uniqueness
    constraint is keyed on) - calling this twice in a row for the same plan
    creates zero additional rows the second time."""
    entry = find_joint_plan_entry(plan, config)

    existing = {
        link.council_code
        for link in session.execute(
            select(LocalPlanCouncil).where(LocalPlanCouncil.local_plan_id == plan.id)
        ).scalars().all()
    }

    created = 0
    if entry:
        lead = entry.get("lead_authority")
        for council_code in entry.get("participating_authorities", []):
            if council_code in existing:
                continue
            created += 1
            if not dry_run:
                session.add(LocalPlanCouncil(
                    local_plan_id=plan.id, council_code=council_code,
                    role="lead_authority" if council_code == lead else "participating_authority",
                    is_lead_authority=(council_code == lead),
                    source_note=entry.get("source_note"),
                ))
    else:
        if plan.council_code not in existing:
            created += 1
            if not dry_run:
                session.add(LocalPlanCouncil(
                    local_plan_id=plan.id, council_code=plan.council_code,
                    role="legacy_owner", is_lead_authority=True,
                    source_note="Backfilled from LocalPlan.council_code - no config/joint_plans.yaml "
                                 "entry found, treated as a single-authority plan.",
                ))

    return {"created": created, "already_linked": len(existing)}


def council_codes_for_plan(session: Session, plan: LocalPlan) -> list[str]:
    """Every council this plan is linked to via LocalPlanCouncil, falling
    back to [plan.council_code] for a plan that hasn't been backfilled yet
    (predates this sprint's migration) - callers never need to special-case
    "no join rows yet" themselves."""
    codes = [
        link.council_code
        for link in session.execute(
            select(LocalPlanCouncil).where(LocalPlanCouncil.local_plan_id == plan.id)
        ).scalars().all()
    ]
    return codes if codes else [plan.council_code]


def plans_for_council(session: Session, council_code: str) -> list[LocalPlan]:
    """Every LocalPlan a council should see - linked via LocalPlanCouncil OR
    (for a plan that hasn't been backfilled) via the legacy council_code
    column directly, deduplicated by plan id. This is what lets Places for
    Everyone appear under every one of its participating authorities once
    they're onboarded for Policy Intelligence, without ever creating a
    second LocalPlan row for it (Part 3) - app.policy.council_dashboard is
    the primary caller."""
    via_join = session.execute(
        select(LocalPlan)
        .join(LocalPlanCouncil, LocalPlanCouncil.local_plan_id == LocalPlan.id)
        .where(LocalPlanCouncil.council_code == council_code)
    ).scalars().all()
    via_legacy = session.execute(
        select(LocalPlan).where(LocalPlan.council_code == council_code)
    ).scalars().all()

    by_id: dict[int, LocalPlan] = {}
    for plan in (*via_join, *via_legacy):
        by_id[plan.id] = plan
    return list(by_id.values())
