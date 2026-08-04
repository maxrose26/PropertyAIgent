"""Multi-council correctness (Sprint 2, "Greater Manchester Policy
Intelligence Framework", Part 8) - source registration, monitoring
isolation, duplicate prevention, and independent history/review-queue
state across more than one council. The `session` fixture seeds two
councils ("testcouncil" and "othercouncil") specifically so these tests
exercise real cross-council boundaries, not just single-council behaviour
repeated twice.
"""
from __future__ import annotations

import json
from unittest.mock import patch

from sqlalchemy import select

from app.db.models import (
    Council,
    LocalPlan,
    LocalPlanSite,
    LocalPlanStatusHistory,
    MonitoredSource,
    PolicyChangeEvent,
)
from app.policy.council_dashboard import build_council_dashboard, summarise_council
from app.policy.monitor import run_monitor
from app.policy.review import approve_change
from app.policy.sources import register_sources_for_council


def _config_for(council_code: str, url: str, source_type: str = "landing_page") -> dict:
    return {"councils": {council_code: {"sources": [{"url": url, "source_type": source_type}]}}}


class _FakeResponse:
    def __init__(self, text: str, url: str = "https://example.invalid/"):
        self.text = text
        self.url = url

    def raise_for_status(self):
        pass


def test_source_registration_is_council_scoped(session):
    config = {
        "councils": {
            "testcouncil": {"sources": [{"url": "https://a.invalid/plan", "source_type": "landing_page"}]},
            "othercouncil": {"sources": [{"url": "https://b.invalid/plan", "source_type": "landing_page"}]},
        }
    }
    register_sources_for_council(session, "testcouncil", config=config)
    register_sources_for_council(session, "othercouncil", config=config)

    a_sources = session.execute(select(MonitoredSource).where(MonitoredSource.council_code == "testcouncil")).scalars().all()
    b_sources = session.execute(select(MonitoredSource).where(MonitoredSource.council_code == "othercouncil")).scalars().all()
    assert [s.url for s in a_sources] == ["https://a.invalid/plan"]
    assert [s.url for s in b_sources] == ["https://b.invalid/plan"]


def test_source_registration_no_config_entry_is_not_an_error(session):
    assert register_sources_for_council(session, "othercouncil", config={"councils": {"testcouncil": {"sources": []}}}) == []


def test_source_registration_does_not_require_a_local_plan_to_exist(session):
    # Part 3: a council-level source (no plan_name) must register even
    # when the council has never had a Local Plan ingested.
    sources = register_sources_for_council(session, "testcouncil", config=_config_for("testcouncil", "https://a.invalid/plan"))
    assert len(sources) == 1
    assert sources[0].local_plan_id is None


def test_source_registration_resolves_local_plan_once_it_exists(session):
    config = {"councils": {"testcouncil": {"sources": [{
        "url": "https://a.invalid/plan.pdf", "source_type": "emerging_plan", "plan_name": "Test Plan", "plan_version": None,
    }]}}}
    sources = register_sources_for_council(session, "testcouncil", config=config)
    assert sources[0].local_plan_id is None  # plan doesn't exist yet

    plan = LocalPlan(council_code="testcouncil", plan_name="Test Plan", status="draft_consultation")
    session.add(plan)
    session.commit()

    sources_again = register_sources_for_council(session, "testcouncil", config=config)
    assert sources_again[0].local_plan_id == plan.id  # resolved on the second call
    assert sources_again[0].id == sources[0].id  # same row, not a duplicate


def test_duplicate_registration_does_not_create_duplicate_sources(session):
    config = _config_for("testcouncil", "https://a.invalid/plan")
    first = register_sources_for_council(session, "testcouncil", config=config)
    second = register_sources_for_council(session, "testcouncil", config=config)
    assert len(first) == 1
    assert len(second) == 1
    assert first[0].id == second[0].id

    all_sources = session.execute(select(MonitoredSource)).scalars().all()
    assert len(all_sources) == 1


def test_monitoring_only_checks_its_own_councils_sources(session):
    register_sources_for_council(session, "testcouncil", config=_config_for("testcouncil", "https://a.invalid/plan"))
    register_sources_for_council(session, "othercouncil", config=_config_for("othercouncil", "https://b.invalid/plan"))

    with patch("app.policy.monitor.requests.get", return_value=_FakeResponse("content")):
        counts_a = run_monitor(session, "testcouncil")
        counts_b = run_monitor(session, "othercouncil")

    assert counts_a["checked"] == 1
    assert counts_b["checked"] == 1  # not 2 - othercouncil's source wasn't picked up by testcouncil's run


def test_monitoring_changes_stay_isolated_to_the_correct_council(session):
    register_sources_for_council(session, "testcouncil", config=_config_for("testcouncil", "https://a.invalid/plan"))
    register_sources_for_council(session, "othercouncil", config=_config_for("othercouncil", "https://b.invalid/plan"))

    with patch("app.policy.monitor.requests.get", return_value=_FakeResponse("v1")):
        run_monitor(session, "testcouncil")
        run_monitor(session, "othercouncil")
    with patch("app.policy.monitor.requests.get", return_value=_FakeResponse("v2")):
        # force=True: this second check happens moments after the first in
        # test time, which a real due-date-aware run would normally skip
        # (see tests/test_monitor.py::test_run_monitor_skips_sources_not_yet_due) -
        # this test's own intent is isolation between councils, not cadence.
        run_monitor(session, "testcouncil", force=True)  # only testcouncil's source changes

    events = session.execute(select(PolicyChangeEvent)).scalars().all()
    assert len(events) == 1
    changed_source = session.get(MonitoredSource, events[0].monitored_source_id)
    assert changed_source.council_code == "testcouncil"


def test_monitoring_is_idempotent_per_council(session):
    register_sources_for_council(session, "testcouncil", config=_config_for("testcouncil", "https://a.invalid/plan"))
    with patch("app.policy.monitor.requests.get", return_value=_FakeResponse("same content")):
        run_monitor(session, "testcouncil")
        first_events = len(session.execute(select(PolicyChangeEvent)).scalars().all())
        run_monitor(session, "testcouncil")
        second_events = len(session.execute(select(PolicyChangeEvent)).scalars().all())
    assert first_events == second_events == 0


def _seed_plan_and_allocation(session, council_code, plan_name, ref):
    plan = LocalPlan(council_code=council_code, plan_name=plan_name, status="draft_consultation", raw_status="draft")
    session.add(plan)
    session.commit()
    row = LocalPlanSite(
        council_code=council_code, local_plan_id=plan.id, policy_reference=ref, site_name="Test Site",
        minimum_dwellings=40, plan_name=plan_name, plan_status="draft", allocation_status="draft_allocation",
    )
    session.add(row)
    session.commit()
    return plan, row


def test_local_plan_histories_are_independent_per_council(session):
    plan_a, _ = _seed_plan_and_allocation(session, "testcouncil", "Plan A", "REF-A")
    plan_b, _ = _seed_plan_and_allocation(session, "othercouncil", "Plan B", "REF-B")

    session.add(LocalPlanStatusHistory(local_plan_id=plan_a.id, status="draft_consultation", note="A's own history"))
    session.add(LocalPlanStatusHistory(local_plan_id=plan_b.id, status="draft_consultation", note="B's own history"))
    session.commit()

    a_history = session.execute(select(LocalPlanStatusHistory).where(LocalPlanStatusHistory.local_plan_id == plan_a.id)).scalars().all()
    b_history = session.execute(select(LocalPlanStatusHistory).where(LocalPlanStatusHistory.local_plan_id == plan_b.id)).scalars().all()
    assert [h.note for h in a_history] == ["A's own history"]
    assert [h.note for h in b_history] == ["B's own history"]


def test_review_queues_are_independent_per_council(session):
    plan_a, row_a = _seed_plan_and_allocation(session, "testcouncil", "Plan A", "REF-A")
    plan_b, row_b = _seed_plan_and_allocation(session, "othercouncil", "Plan B", "REF-B")

    event_a = PolicyChangeEvent(
        local_plan_id=plan_a.id, allocation_id=row_a.id, event_type="capacity_changed",
        proposed_data=json.dumps({"minimum_dwellings": 55}), auto_applied=False, review_status="needs_review",
    )
    event_b = PolicyChangeEvent(
        local_plan_id=plan_b.id, allocation_id=row_b.id, event_type="capacity_changed",
        proposed_data=json.dumps({"minimum_dwellings": 99}), auto_applied=False, review_status="needs_review",
    )
    session.add_all([event_a, event_b])
    session.commit()

    # Approving council A's change must never touch council B's allocation.
    approve_change(session, event_a)
    session.refresh(row_a)
    session.refresh(row_b)
    assert row_a.minimum_dwellings == 55
    assert row_b.minimum_dwellings == 40  # untouched
    assert event_b.review_status == "needs_review"  # still pending, unaffected


def test_dashboard_reports_councils_independently(session):
    _seed_plan_and_allocation(session, "testcouncil", "Plan A", "REF-A")
    _seed_plan_and_allocation(session, "othercouncil", "Plan B", "REF-B")

    rows = build_council_dashboard(session)
    codes = {r["council_code"] for r in rows}
    assert {"testcouncil", "othercouncil"}.issubset(codes)

    row_a = next(r for r in rows if r["council_code"] == "testcouncil")
    row_b = next(r for r in rows if r["council_code"] == "othercouncil")
    assert row_a["total_allocations_imported"] == 1
    assert row_b["total_allocations_imported"] == 1
    assert row_a["local_plans"][0]["plan_name"] == "Plan A"
    assert row_b["local_plans"][0]["plan_name"] == "Plan B"


def test_summarise_council_excludes_unrelated_councils_review_items(session):
    plan_a, row_a = _seed_plan_and_allocation(session, "testcouncil", "Plan A", "REF-A")
    plan_b, row_b = _seed_plan_and_allocation(session, "othercouncil", "Plan B", "REF-B")

    session.add(PolicyChangeEvent(
        local_plan_id=plan_b.id, allocation_id=row_b.id, event_type="capacity_changed",
        review_status="needs_review", auto_applied=False,
    ))
    session.commit()

    council_a = session.get(Council, "testcouncil")
    summary_a = summarise_council(session, council_a)
    assert summary_a["review_items_pending"] == 0  # B's pending item must not leak into A's count


def test_onboarding_a_new_council_does_not_disturb_an_existing_ones_data(session):
    # Simulates the shape of onboarding Bury as a second council after
    # Stockport: seed "testcouncil" first (standing in for an
    # already-onboarded council), confirm its data is unaffected once a
    # second council's plan/allocation/sources are added afterward.
    plan_a, row_a = _seed_plan_and_allocation(session, "testcouncil", "Existing Plan", "REF-EXISTING")
    register_sources_for_council(session, "testcouncil", config=_config_for("testcouncil", "https://a.invalid/plan"))

    before_allocation_count = len(session.execute(select(LocalPlanSite)).scalars().all())
    before_source_count = len(session.execute(select(MonitoredSource)).scalars().all())

    # Onboard the new council.
    plan_b, row_b = _seed_plan_and_allocation(session, "othercouncil", "New Council Plan", "REF-NEW")
    register_sources_for_council(session, "othercouncil", config=_config_for("othercouncil", "https://b.invalid/plan"))

    session.refresh(row_a)
    assert row_a.minimum_dwellings == 40  # existing council's allocation untouched
    assert row_a.policy_reference == "REF-EXISTING"

    after_allocation_count = len(session.execute(select(LocalPlanSite)).scalars().all())
    after_source_count = len(session.execute(select(MonitoredSource)).scalars().all())
    assert after_allocation_count == before_allocation_count + 1
    assert after_source_count == before_source_count + 1
