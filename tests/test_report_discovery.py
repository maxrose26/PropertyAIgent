"""Housing-supply monitoring amendment ("Add monitored housing supply and
delivery reports", Part 7) - tests for app.policy.report_discovery: index-
page discovery, deterministic classification, same-URL replacement
detection, cross-URL supersession review, and idempotency. All external
I/O (requests.get) is mocked with local HTML fixtures - no real network
access anywhere in this file, matching the pattern already established in
tests/test_monitor.py."""
from __future__ import annotations

from unittest.mock import patch

from sqlalchemy import select

from app.db.models import LocalPlan, MonitoredReport, MonitoredSource, PolicyChangeEvent
from app.policy.report_discovery import (
    check_report_for_changes,
    check_reports_for_council,
    discover_reports_for_council,
    discover_reports_for_source,
    register_discovered_reports,
)


class _FakeResponse:
    def __init__(self, html: str, url: str = "https://example.invalid/monitoring"):
        self.text = html
        self.url = url

    def raise_for_status(self):
        pass


def _make_source(session, source_type="amr_page", url="https://example.invalid/monitoring", local_plan_id=None):
    source = MonitoredSource(council_code="testcouncil", local_plan_id=local_plan_id, url=url, source_type=source_type, title="Monitoring page")
    session.add(source)
    session.commit()
    return source


def _make_plan(session):
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Local Plan", status="draft_consultation", raw_status="draft")
    session.add(plan)
    session.commit()
    return plan


_COMBINED_AMR_HTML = """
<html><body>
<a href="/docs/amr-2023-24.pdf">Authority Monitoring Report 2023/24</a>
</body></html>
"""

_SEPARATE_AMR_AND_SUPPLY_HTML = """
<html><body>
<a href="/docs/amr-2023-24.pdf">Authority Monitoring Report 2023/24</a>
<a href="/docs/5yhls-2024.pdf">Five Year Housing Land Supply Statement 2024</a>
</body></html>
"""

_AMBIGUOUS_HTML = """
<html><body>
<a href="/docs/update-notes.pdf">Housing Update Document</a>
</body></html>
"""


# --- one council using a combined AMR (Part 7) ---

def test_combined_amr_registers_a_single_report_eligible_for_both_categories(session):
    plan = _make_plan(session)
    source = _make_source(session, local_plan_id=plan.id)

    with patch("app.policy.report_discovery.requests.get", return_value=_FakeResponse(_COMBINED_AMR_HTML)):
        counts = discover_reports_for_source(session, source)

    assert counts["new_reports"] == 1
    assert counts["auto_classified"] == 1
    reports = session.execute(select(MonitoredReport).where(MonitoredReport.monitored_source_id == source.id)).scalars().all()
    assert len(reports) == 1
    assert reports[0].source_type == "authority_monitoring_report"


# --- one council using separate AMR and land-supply statement (Part 7) ---

def test_separate_amr_and_land_supply_statement_register_as_two_distinct_reports(session):
    plan = _make_plan(session)
    source = _make_source(session, local_plan_id=plan.id)

    with patch("app.policy.report_discovery.requests.get", return_value=_FakeResponse(_SEPARATE_AMR_AND_SUPPLY_HTML)):
        counts = discover_reports_for_source(session, source)

    assert counts["new_reports"] == 2
    reports = session.execute(select(MonitoredReport).where(MonitoredReport.monitored_source_id == source.id)).scalars().all()
    types = {r.source_type for r in reports}
    assert types == {"authority_monitoring_report", "housing_land_supply_statement"}


# --- discovery of a newly published report ---

def test_a_newly_added_link_is_discovered_on_a_later_check_without_touching_existing_reports(session):
    plan = _make_plan(session)
    source = _make_source(session, local_plan_id=plan.id)

    with patch("app.policy.report_discovery.requests.get", return_value=_FakeResponse(_COMBINED_AMR_HTML)):
        discover_reports_for_source(session, source)

    with patch("app.policy.report_discovery.requests.get", return_value=_FakeResponse(_SEPARATE_AMR_AND_SUPPLY_HTML)):
        counts = discover_reports_for_source(session, source)

    assert counts["new_reports"] == 1  # only the land supply statement is genuinely new
    reports = session.execute(select(MonitoredReport).where(MonitoredReport.monitored_source_id == source.id)).scalars().all()
    assert len(reports) == 2


# --- unchanged index page causes no duplicate reports (idempotent discovery) ---

def test_unchanged_index_page_creates_no_duplicate_reports(session):
    plan = _make_plan(session)
    source = _make_source(session, local_plan_id=plan.id)

    with patch("app.policy.report_discovery.requests.get", return_value=_FakeResponse(_COMBINED_AMR_HTML)):
        first = discover_reports_for_source(session, source)
        second = discover_reports_for_source(session, source)

    assert first["new_reports"] == 1
    assert second["new_reports"] == 0
    reports = session.execute(select(MonitoredReport).where(MonitoredReport.monitored_source_id == source.id)).scalars().all()
    assert len(reports) == 1


# --- ambiguous report classification enters review ---

def test_ambiguous_link_is_registered_but_flagged_needs_review(session):
    plan = _make_plan(session)
    source = _make_source(session, local_plan_id=plan.id)

    with patch("app.policy.report_discovery.requests.get", return_value=_FakeResponse(_AMBIGUOUS_HTML)):
        counts = discover_reports_for_source(session, source)

    assert counts["new_reports"] == 1
    assert counts["needs_review"] == 1
    [report] = session.execute(select(MonitoredReport).where(MonitoredReport.monitored_source_id == source.id)).scalars().all()
    assert report.source_type is None
    assert report.classification_status == "needs_review"

    events = session.execute(select(PolicyChangeEvent).where(PolicyChangeEvent.monitored_report_id == report.id)).scalars().all()
    assert len(events) == 1
    assert events[0].event_type == "report_classification_needs_review"
    assert events[0].review_status == "needs_review"
    assert events[0].auto_applied is False


def test_regression_possessive_authoritys_monitoring_report_still_classifies(session):
    # Real pilot finding (live Stockport document): the actual official
    # title is "Authority's Monitoring Report" - the possessive form - not
    # "Authority Monitoring Report". Both must classify the same way.
    plan = _make_plan(session)
    source = _make_source(session, local_plan_id=plan.id)
    html = '<html><body><a href="/docs/amr-2026.pdf">Authority’s Monitoring Report March 2026</a></body></html>'

    with patch("app.policy.report_discovery.requests.get", return_value=_FakeResponse(html)):
        counts = discover_reports_for_source(session, source)

    assert counts["auto_classified"] == 1
    [report] = session.execute(select(MonitoredReport).where(MonitoredReport.monitored_source_id == source.id)).scalars().all()
    assert report.source_type == "authority_monitoring_report"


def test_confidently_classified_report_is_auto_applied_with_a_discovered_event(session):
    plan = _make_plan(session)
    source = _make_source(session, local_plan_id=plan.id)

    with patch("app.policy.report_discovery.requests.get", return_value=_FakeResponse(_COMBINED_AMR_HTML)):
        discover_reports_for_source(session, source)

    [report] = session.execute(select(MonitoredReport).where(MonitoredReport.monitored_source_id == source.id)).scalars().all()
    events = session.execute(select(PolicyChangeEvent).where(PolicyChangeEvent.monitored_report_id == report.id)).scalars().all()
    discovered = [e for e in events if e.event_type == "report_discovered"]
    assert len(discovered) == 1
    assert discovered[0].auto_applied is True
    assert discovered[0].review_status == "auto_applied"


# --- detection of a replacement PDF at the same URL (same-URL supersession) ---

def test_same_url_content_change_supersedes_the_old_report_and_creates_a_new_one(session):
    plan = _make_plan(session)
    source = _make_source(session, local_plan_id=plan.id)
    report = MonitoredReport(
        council_code="testcouncil", local_plan_id=plan.id, monitored_source_id=source.id,
        source_type="authority_monitoring_report", classification_status="auto",
        title="AMR", url="https://example.invalid/docs/amr.pdf", status="current",
    )
    session.add(report)
    session.commit()

    with patch("app.policy.report_discovery.requests.get", return_value=_FakeResponse("original content", url=report.url)):
        outcome = check_report_for_changes(session, report)
    assert outcome == "first_check"

    with patch("app.policy.report_discovery.requests.get", return_value=_FakeResponse("replaced content", url=report.url)):
        outcome = check_report_for_changes(session, report)

    assert outcome == "changed"
    session.refresh(report)
    assert report.status == "superseded"
    assert report.supersession_method == "auto"
    assert report.superseded_by_id is not None

    new_report = session.get(MonitoredReport, report.superseded_by_id)
    assert new_report.status == "current"
    assert new_report.url == report.url  # same URL, new row
    assert new_report.content_hash != report.content_hash  # old row's hash is frozen at its own edition

    # Older reports retained, never deleted (Part 1/Part 5).
    all_reports = session.execute(select(MonitoredReport).where(MonitoredReport.monitored_source_id == source.id)).scalars().all()
    assert len(all_reports) == 2

    events = session.execute(select(PolicyChangeEvent).where(PolicyChangeEvent.event_type == "report_superseded")).scalars().all()
    assert len(events) == 1
    assert events[0].auto_applied is True
    assert events[0].monitored_report_id == new_report.id


def test_unchanged_report_content_is_not_superseded(session):
    plan = _make_plan(session)
    source = _make_source(session, local_plan_id=plan.id)
    report = MonitoredReport(
        council_code="testcouncil", local_plan_id=plan.id, monitored_source_id=source.id,
        source_type="authority_monitoring_report", classification_status="auto",
        title="AMR", url="https://example.invalid/docs/amr.pdf", status="current",
    )
    session.add(report)
    session.commit()

    with patch("app.policy.report_discovery.requests.get", return_value=_FakeResponse("same content", url=report.url)):
        check_report_for_changes(session, report)
        outcome = check_report_for_changes(session, report)

    assert outcome == "unchanged"
    session.refresh(report)
    assert report.status == "current"
    all_reports = session.execute(select(MonitoredReport).where(MonitoredReport.monitored_source_id == source.id)).scalars().all()
    assert len(all_reports) == 1


# --- cross-URL supersession is always queued for review, never auto-applied ---

def test_a_same_type_report_at_a_different_url_queues_a_supersession_review_not_an_auto_apply(session):
    plan = _make_plan(session)
    source = _make_source(session, local_plan_id=plan.id)
    older = MonitoredReport(
        council_code="testcouncil", local_plan_id=plan.id, monitored_source_id=source.id,
        source_type="authority_monitoring_report", classification_status="auto",
        title="AMR 2022/23", url="https://example.invalid/docs/amr-2022-23.pdf", status="current",
    )
    session.add(older)
    session.commit()

    with patch("app.policy.report_discovery.requests.get", return_value=_FakeResponse(_COMBINED_AMR_HTML)):
        discover_reports_for_source(session, source)

    session.refresh(older)
    assert older.status == "current"  # NOT auto-superseded - still needs a human to confirm

    events = session.execute(
        select(PolicyChangeEvent).where(PolicyChangeEvent.event_type == "report_supersession_needs_review")
    ).scalars().all()
    assert len(events) == 1
    assert events[0].monitored_report_id == older.id
    assert events[0].auto_applied is False
    assert events[0].review_status == "needs_review"


# --- source due-date filtering at the council level ---

def test_discover_reports_for_council_skips_sources_not_yet_due(session):
    plan = _make_plan(session)
    source = _make_source(session, local_plan_id=plan.id)

    with patch("app.policy.report_discovery.requests.get", return_value=_FakeResponse(_COMBINED_AMR_HTML)):
        first = discover_reports_for_council(session, "testcouncil")
        second = discover_reports_for_council(session, "testcouncil")  # not forced - should skip, not due yet

    assert first["sources_checked"] == 1
    assert second["sources_checked"] == 0
    assert second["sources_skipped_not_due"] == 1


def test_discover_reports_for_council_force_bypasses_due_date(session):
    plan = _make_plan(session)
    source = _make_source(session, local_plan_id=plan.id)

    with patch("app.policy.report_discovery.requests.get", return_value=_FakeResponse(_COMBINED_AMR_HTML)):
        discover_reports_for_council(session, "testcouncil")
        forced = discover_reports_for_council(session, "testcouncil", force=True)

    assert forced["sources_checked"] == 1


def test_check_reports_for_council_skips_reports_not_yet_due(session):
    plan = _make_plan(session)
    source = _make_source(session, local_plan_id=plan.id)
    report = MonitoredReport(
        council_code="testcouncil", local_plan_id=plan.id, monitored_source_id=source.id,
        source_type="authority_monitoring_report", classification_status="auto",
        title="AMR", url="https://example.invalid/docs/amr.pdf", status="current",
    )
    session.add(report)
    session.commit()

    with patch("app.policy.report_discovery.requests.get", return_value=_FakeResponse("content", url=report.url)):
        first = check_reports_for_council(session, "testcouncil")
        second = check_reports_for_council(session, "testcouncil")

    assert first["reports_checked"] == 1
    assert second["reports_checked"] == 0
    assert second["reports_skipped_not_due"] == 1
