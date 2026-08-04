from unittest.mock import patch

from sqlalchemy import select

from app.db.models import LocalPlan, MonitoredSource, PolicyChangeEvent
from app.policy.monitor import check_source, run_monitor


class _FakeResponse:
    def __init__(self, text: str, url: str = "https://example.invalid/plan.pdf"):
        self.text = text
        self.url = url

    def raise_for_status(self):
        pass


class _FakeTimeout(Exception):
    pass


def _make_plan_and_source(session, url="https://example.invalid/plan.pdf"):
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Local Plan", status="draft_consultation")
    session.add(plan)
    session.commit()
    source = MonitoredSource(
        council_code="testcouncil", local_plan_id=plan.id, url=url, source_type="pdf", title="Test source",
    )
    session.add(source)
    session.commit()
    return plan, source


def test_first_check_establishes_baseline_without_creating_an_event(session):
    plan, source = _make_plan_and_source(session)
    with patch("app.policy.monitor.requests.get", return_value=_FakeResponse("Site HOM 2.30 - 40 dwellings")):
        outcome = check_source(session, source)

    assert outcome == "first_check"
    assert source.content_hash is not None
    assert source.monitoring_health == "ok"
    events = session.execute(select(PolicyChangeEvent)).scalars().all()
    assert events == []


def test_unchanged_source_creates_no_duplicate_event(session):
    plan, source = _make_plan_and_source(session)
    content = "Site HOM 2.30 - 40 dwellings"
    with patch("app.policy.monitor.requests.get", return_value=_FakeResponse(content)):
        check_source(session, source)   # first_check
        check_source(session, source)   # unchanged
        outcome = check_source(session, source)  # unchanged again

    assert outcome == "unchanged"
    events = session.execute(select(PolicyChangeEvent)).scalars().all()
    assert events == []


def test_changed_source_is_detected_and_queued(session):
    plan, source = _make_plan_and_source(session)
    with patch("app.policy.monitor.requests.get", return_value=_FakeResponse("Site HOM 2.30 - 40 dwellings")):
        check_source(session, source)  # establishes baseline

    with patch("app.policy.monitor.requests.get", return_value=_FakeResponse("Site HOM 2.30 - 55 dwellings")):
        outcome = check_source(session, source)

    assert outcome == "changed"
    assert source.last_changed is not None
    events = session.execute(select(PolicyChangeEvent)).scalars().all()
    assert len(events) == 1
    assert events[0].event_type == "source_content_changed"
    assert events[0].review_status == "needs_review"
    assert events[0].auto_applied is False


def test_rechecking_before_resolution_does_not_queue_a_duplicate_event(session):
    plan, source = _make_plan_and_source(session)
    with patch("app.policy.monitor.requests.get", return_value=_FakeResponse("A")):
        check_source(session, source)
    with patch("app.policy.monitor.requests.get", return_value=_FakeResponse("B")):
        check_source(session, source)  # changed, queues one event
    with patch("app.policy.monitor.requests.get", return_value=_FakeResponse("B")):
        check_source(session, source)  # same content as last check - unchanged now, no new event

    events = session.execute(select(PolicyChangeEvent)).scalars().all()
    assert len(events) == 1


def test_failed_source_becomes_stale_or_unhealthy(session):
    import requests

    plan, source = _make_plan_and_source(session)
    with patch("app.policy.monitor.requests.get", side_effect=requests.Timeout("timed out")):
        outcome = check_source(session, source)

    assert outcome == "failed"
    assert source.monitoring_health in ("error", "stale")
    assert source.last_checked is not None
    assert source.last_successful_check is None  # never succeeded, so this must stay unset


def test_run_monitor_is_idempotent(session):
    plan, source = _make_plan_and_source(session)
    content = "Site HOM 2.30 - 40 dwellings"

    with patch("app.policy.monitor.requests.get", return_value=_FakeResponse(content)):
        first = run_monitor(session, "testcouncil")
        second = run_monitor(session, "testcouncil")

    assert first["checked"] == 1
    assert second["checked"] == 1
    assert second["changed"] == 0
    assert second["queued"] == 0

    events = session.execute(select(PolicyChangeEvent)).scalars().all()
    assert events == []  # first_check then unchanged - never anything to queue


def test_run_monitor_only_checks_active_sources(session):
    plan, source = _make_plan_and_source(session)
    source.is_active = False
    session.commit()

    with patch("app.policy.monitor.requests.get", return_value=_FakeResponse("content")):
        counts = run_monitor(session, "testcouncil")

    assert counts["checked"] == 0
