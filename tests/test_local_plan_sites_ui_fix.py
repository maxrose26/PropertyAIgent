"""Sprint 3E ("Joint Plan Support and Bury Allocation Reconciliation") Part
4/9 - regression tests for the policy_reference=None UI defect fix. The
real bug lived in app/ui/pages/3_Local_Plan_Sites.py's dict-building line
(`{row["policy_reference"]: row ...}`), which cannot be imported directly
(Streamlit executes it as a script) - these tests instead exercise the same
lookup pattern the fixed page now uses (keyed by build_site_policy_
intelligence's "allocation_id" field) directly against real LocalPlanSite
rows, proving the fix's actual mechanism: allocation.id as the key, never
policy_reference."""
from __future__ import annotations

from app.db.models import LocalPlan, LocalPlanSite
from app.policy.site_view import build_site_policy_intelligence


def _make_allocation(session, plan, *, site_name, policy_reference, allocation_status):
    row = LocalPlanSite(
        council_code="testcouncil", local_plan_id=plan.id,
        policy_reference=policy_reference, site_name=site_name, minimum_dwellings=100,
        plan_name=plan.plan_name, plan_status=plan.status,
        allocation_status=allocation_status, raw_allocation_status=allocation_status,
    )
    session.add(row)
    session.commit()
    return row


def _build_policy_rows_by_id(allocations):
    """Mirrors exactly what 3_Local_Plan_Sites.py now does."""
    return {row["allocation_id"]: row for row in build_site_policy_intelligence(allocations)}


def test_multiple_none_policy_references_do_not_collapse(session):
    plan = LocalPlan(council_code="testcouncil", plan_name="Bury Local Plan", status="proposed_submission")
    session.add(plan)
    session.commit()

    rows = [
        _make_allocation(session, plan, site_name="Seedfield", policy_reference=None, allocation_status="status_a"),
        _make_allocation(session, plan, site_name="Walshaw", policy_reference=None, allocation_status="status_b"),
        _make_allocation(session, plan, site_name="Elton Reservoir", policy_reference=None, allocation_status="status_c"),
        _make_allocation(session, plan, site_name="Castle Road (Unsworth)", policy_reference=None, allocation_status="status_d"),
        _make_allocation(session, plan, site_name="Simister", policy_reference=None, allocation_status="status_e"),
    ]

    policy_rows = _build_policy_rows_by_id(rows)

    # One dict entry per allocation - not one shared "None" entry.
    assert len(policy_rows) == 5

    for row in rows:
        looked_up = policy_rows[row.id]
        assert looked_up["allocation_name"] == row.site_name
        assert looked_up["allocation_status"] == row.allocation_status  # never another row's status


def test_duplicate_policy_references_do_not_collapse(session):
    # Two different plans legitimately reusing the same code (or a data
    # error producing one) must still be two independent rows in the UI.
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Plan", status="adopted")
    session.add(plan)
    session.commit()

    row_a = _make_allocation(session, plan, site_name="Site A", policy_reference="DUP-1", allocation_status="adopted_allocation")
    row_b = _make_allocation(session, plan, site_name="Site B", policy_reference="DUP-1", allocation_status="draft_allocation")

    policy_rows = _build_policy_rows_by_id([row_a, row_b])

    assert len(policy_rows) == 2
    assert policy_rows[row_a.id]["allocation_name"] == "Site A"
    assert policy_rows[row_a.id]["allocation_status"] == "adopted_allocation"
    assert policy_rows[row_b.id]["allocation_name"] == "Site B"
    assert policy_rows[row_b.id]["allocation_status"] == "draft_allocation"


def test_mixed_none_and_real_references_all_resolve_independently(session):
    plan = LocalPlan(council_code="testcouncil", plan_name="Mixed Plan", status="adopted")
    session.add(plan)
    session.commit()

    coded = _make_allocation(session, plan, site_name="Northern Gateway", policy_reference="JPA1.1", allocation_status="adopted_allocation")
    uncoded_1 = _make_allocation(session, plan, site_name="Seedfield", policy_reference=None, allocation_status="submitted_allocation")
    uncoded_2 = _make_allocation(session, plan, site_name="Walshaw", policy_reference=None, allocation_status="unknown")

    policy_rows = _build_policy_rows_by_id([coded, uncoded_1, uncoded_2])
    assert len(policy_rows) == 3
    assert policy_rows[coded.id]["allocation_status"] == "adopted_allocation"
    assert policy_rows[uncoded_1.id]["allocation_status"] == "submitted_allocation"
    assert policy_rows[uncoded_2.id]["allocation_status"] == "unknown"
    # policy_reference is still carried through as DISPLAY data, just no
    # longer used as the lookup key.
    assert policy_rows[uncoded_1.id]["policy_reference"] is None
    assert policy_rows[coded.id]["policy_reference"] == "JPA1.1"
