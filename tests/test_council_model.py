"""Council entity tests (Sprint 2, Part 2)."""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import Council, LocalPlan, MonitoredSource


def test_council_carries_policy_intelligence_fields(session):
    council = Council(
        code="newcouncil", name="New Council", base_url="https://new.invalid",
        date_field_mode="received", doc_system="idox",
        gss_code="E08000099", authority_type="Metropolitan Borough Council",
        website="https://www.new.invalid", monitoring_enabled=True,
    )
    session.add(council)
    session.commit()
    stored = session.get(Council, "newcouncil")
    assert stored.gss_code == "E08000099"
    assert stored.monitoring_enabled is True
    assert stored.created_at is not None


def test_council_defaults_monitoring_disabled(session):
    council = session.get(Council, "testcouncil")
    assert council.monitoring_enabled is False


def test_council_local_plans_relationship(session):
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Plan", status="draft_consultation")
    session.add(plan)
    session.commit()

    council = session.get(Council, "testcouncil")
    assert [p.plan_name for p in council.local_plans] == ["Test Plan"]
    assert plan.council.code == "testcouncil"


def test_council_monitored_sources_relationship(session):
    source = MonitoredSource(council_code="testcouncil", url="https://example.invalid/plan", source_type="landing_page")
    session.add(source)
    session.commit()

    council = session.get(Council, "testcouncil")
    assert [s.url for s in council.monitored_sources] == ["https://example.invalid/plan"]
    assert source.council.code == "testcouncil"


def test_monitored_source_supports_no_local_plan(session):
    source = MonitoredSource(council_code="testcouncil", url="https://example.invalid/landing", source_type="landing_page")
    session.add(source)
    session.commit()
    assert source.local_plan_id is None
    assert source.monitoring_frequency_days == 7
