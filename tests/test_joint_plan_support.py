"""Sprint 3E ("Joint Plan Support and Bury Allocation Reconciliation") Part
9 tests for the LocalPlanCouncil join model, its migration, and the
council-facing queries it feeds."""
from __future__ import annotations

from unittest.mock import patch

from sqlalchemy import select

from app.db.models import Council, LocalPlan, LocalPlanCouncil, LocalPlanSite, MonitoredSource
from app.policy.council_dashboard import build_council_dashboard, summarise_council
from app.policy.joint_plans import (
    council_codes_for_plan,
    ensure_council_links_for_plan,
    find_joint_plan_entry,
    plans_for_council,
)
from app.policy.monitor import run_monitor
from app.policy.sources import register_sources_for_council
from scripts.migrate_joint_plan_support import migrate


def _add_council(session, code: str, name: str | None = None) -> Council:
    council = Council(
        code=code, name=name or code.title(), base_url=f"https://{code}.invalid",
        date_field_mode="received", doc_system="idox",
    )
    session.add(council)
    session.commit()
    return council


JOINT_CONFIG = [{
    "council_code": "testcouncil",
    "plan_name": "Joint Plan",
    "plan_version": "2022-2039",
    "lead_authority": "testcouncil",
    "participating_authorities": ["testcouncil", "othercouncil", "thirdcouncil"],
    "source_note": "Test fixture joint plan.",
}]


def test_one_plan_links_to_multiple_councils(session):
    _add_council(session, "thirdcouncil")
    plan = LocalPlan(council_code="testcouncil", plan_name="Joint Plan", plan_version="2022-2039", status="adopted")
    session.add(plan)
    session.commit()

    result = ensure_council_links_for_plan(session, plan, config=JOINT_CONFIG)
    session.commit()

    assert result["created"] == 3
    links = session.execute(select(LocalPlanCouncil).where(LocalPlanCouncil.local_plan_id == plan.id)).scalars().all()
    assert {l.council_code for l in links} == {"testcouncil", "othercouncil", "thirdcouncil"}
    lead = next(l for l in links if l.council_code == "testcouncil")
    assert lead.is_lead_authority is True
    assert lead.role == "lead_authority"
    participant = next(l for l in links if l.council_code == "othercouncil")
    assert participant.role == "participating_authority"
    assert participant.is_lead_authority is False


def test_one_council_links_to_multiple_plans(session):
    plan_a = LocalPlan(council_code="testcouncil", plan_name="Plan A", status="adopted")
    plan_b = LocalPlan(council_code="testcouncil", plan_name="Plan B", status="draft_consultation")
    session.add_all([plan_a, plan_b])
    session.commit()

    ensure_council_links_for_plan(session, plan_a, config=[])
    ensure_council_links_for_plan(session, plan_b, config=[])
    session.commit()

    plans = plans_for_council(session, "testcouncil")
    assert {p.plan_name for p in plans} == {"Plan A", "Plan B"}


def test_migration_idempotency_creates_no_duplicate_rows_on_rerun(session):
    _add_council(session, "thirdcouncil")
    plan = LocalPlan(council_code="testcouncil", plan_name="Joint Plan", plan_version="2022-2039", status="adopted")
    session.add(plan)
    session.commit()

    with patch("scripts.migrate_joint_plan_support.load_joint_plans_config", return_value=JOINT_CONFIG):
        first = migrate(session)
        second = migrate(session)

    assert first["links_created"] == 3
    assert second["links_created"] == 0
    assert second["links_already_present"] == 3

    all_links = session.execute(select(LocalPlanCouncil).where(LocalPlanCouncil.local_plan_id == plan.id)).scalars().all()
    assert len(all_links) == 3  # not 6


def test_no_duplicate_local_plan_council_rows_for_same_pair(session):
    plan = LocalPlan(council_code="testcouncil", plan_name="Plan A", status="adopted")
    session.add(plan)
    session.commit()

    ensure_council_links_for_plan(session, plan, config=[])
    ensure_council_links_for_plan(session, plan, config=[])  # rerun, no config entry -> legacy_owner path
    session.commit()

    links = session.execute(select(LocalPlanCouncil).where(LocalPlanCouncil.local_plan_id == plan.id)).scalars().all()
    assert len(links) == 1
    assert links[0].role == "legacy_owner"
    assert links[0].is_lead_authority is True


def test_single_authority_plan_gets_exactly_one_join_row(session):
    plan = LocalPlan(council_code="testcouncil", plan_name="Stockport-style Plan", status="draft_consultation")
    session.add(plan)
    session.commit()

    result = ensure_council_links_for_plan(session, plan, config=[])  # no joint_plans.yaml entry
    session.commit()

    assert result["created"] == 1
    links = session.execute(select(LocalPlanCouncil).where(LocalPlanCouncil.local_plan_id == plan.id)).scalars().all()
    assert len(links) == 1
    assert links[0].council_code == "testcouncil"


def test_plan_predating_migration_still_resolves_via_legacy_council_code(session):
    # No LocalPlanCouncil rows exist at all for this plan - plans_for_council
    # must still find it via the legacy column, never treat it as invisible.
    plan = LocalPlan(council_code="testcouncil", plan_name="Unmigrated Plan", status="adopted")
    session.add(plan)
    session.commit()

    assert plan in plans_for_council(session, "testcouncil")
    assert council_codes_for_plan(session, plan) == ["testcouncil"]


def test_places_for_everyone_style_plan_appears_under_every_participant_without_duplicate_plan_rows(session):
    _add_council(session, "thirdcouncil")
    plan = LocalPlan(
        council_code="testcouncil", plan_name="Joint Plan", plan_version="2022-2039",
        status="adopted", raw_status="Adopted",
    )
    session.add(plan)
    session.commit()
    ensure_council_links_for_plan(session, plan, config=JOINT_CONFIG)
    session.commit()

    for council_code in ("testcouncil", "othercouncil", "thirdcouncil"):
        plans = plans_for_council(session, council_code)
        assert len(plans) == 1
        assert plans[0].id == plan.id  # same underlying row every time, never a copy

    # Exactly one LocalPlan row in the whole database for this plan.
    all_plans = session.execute(select(LocalPlan).where(LocalPlan.plan_name == "Joint Plan")).scalars().all()
    assert len(all_plans) == 1


def test_council_specific_allocation_counts_for_a_joint_plan(session):
    _add_council(session, "thirdcouncil")
    plan = LocalPlan(
        council_code="testcouncil", plan_name="Joint Plan", plan_version="2022-2039",
        status="adopted", raw_status="Adopted",
    )
    session.add(plan)
    session.commit()
    ensure_council_links_for_plan(session, plan, config=JOINT_CONFIG)

    # All three allocations physically sit in testcouncil (mirrors Bury's
    # JPA7/8/9 all having council_code="bury" even though the PLAN is
    # jointly Bury/othercouncil/thirdcouncil's).
    for ref in ("JPA1", "JPA2", "JPA3"):
        session.add(LocalPlanSite(
            council_code="testcouncil", local_plan_id=plan.id, policy_reference=ref, site_name=f"Site {ref}",
            plan_name="Joint Plan", plan_status="adopted",
        ))
    session.commit()

    council_a = session.get(Council, "testcouncil")
    council_b = session.get(Council, "othercouncil")
    summary_a = summarise_council(session, council_a)
    summary_b = summarise_council(session, council_b)

    plan_summary_a = next(p for p in summary_a["local_plans"] if p["plan_id"] == plan.id)
    plan_summary_b = next(p for p in summary_b["local_plans"] if p["plan_id"] == plan.id)

    assert plan_summary_a["allocations_imported"] == 3  # testcouncil's own allocations
    assert plan_summary_b["allocations_imported"] == 0  # othercouncil sees the SAME plan, but claims none of testcouncil's allocations
    assert summary_a["total_allocations_imported"] == 3
    assert summary_b["total_allocations_imported"] == 0


def test_council_dashboard_shows_joint_plan_for_every_linked_council(session):
    _add_council(session, "thirdcouncil")
    plan = LocalPlan(
        council_code="testcouncil", plan_name="Joint Plan", plan_version="2022-2039",
        status="adopted", raw_status="Adopted",
    )
    session.add(plan)
    session.commit()
    ensure_council_links_for_plan(session, plan, config=JOINT_CONFIG)
    session.commit()

    rows = build_council_dashboard(session)
    codes_with_the_plan = {
        r["council_code"] for r in rows if any(p["plan_id"] == plan.id for p in r["local_plans"])
    }
    assert codes_with_the_plan == {"testcouncil", "othercouncil", "thirdcouncil"}


def test_no_duplicate_monitoring_from_joint_plan_linking(session):
    # A joint plan's real MonitoredSource stays registered under exactly
    # ONE council (its lead/legacy owner) - linking additional councils via
    # LocalPlanCouncil must never register or re-check that source again
    # under the other participating councils, since app.policy.monitor
    # filters strictly on MonitoredSource.council_code, never via the plan
    # relationship.
    _add_council(session, "thirdcouncil")
    plan = LocalPlan(council_code="testcouncil", plan_name="Joint Plan", plan_version="2022-2039", status="adopted")
    session.add(plan)
    session.commit()
    ensure_council_links_for_plan(session, plan, config=JOINT_CONFIG)
    session.commit()

    register_sources_for_council(
        session, "testcouncil",
        config={"councils": {"testcouncil": {"sources": [{
            "url": "https://joint-plan.invalid/doc.pdf", "source_type": "adopted_plan",
            "plan_name": "Joint Plan", "plan_version": "2022-2039",
        }]}}},
    )

    sources_all = session.execute(select(MonitoredSource)).scalars().all()
    assert len(sources_all) == 1  # not registered again for othercouncil/thirdcouncil

    class _FakeResponse:
        text = "content"
        url = "https://joint-plan.invalid/doc.pdf"

        def raise_for_status(self):
            pass

    with patch("app.policy.monitor.requests.get", return_value=_FakeResponse()):
        counts_other = run_monitor(session, "othercouncil")
        counts_third = run_monitor(session, "thirdcouncil")

    assert counts_other["checked"] == 0  # othercouncil owns no sources of its own
    assert counts_third["checked"] == 0


def test_find_joint_plan_entry_returns_none_for_ordinary_plan(session):
    plan = LocalPlan(council_code="testcouncil", plan_name="Ordinary Plan", status="adopted")
    assert find_joint_plan_entry(plan, config=JOINT_CONFIG) is None
