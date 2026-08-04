"""Housing-supply monitoring amendment ("Add monitored housing supply and
delivery reports", Part 7) - tests for should_extract/run_extraction_for_report
in app.policy.extract_plan_evidence: AI extraction must run only when a
report is new, its content changed, or an explicit reprocess is requested -
never on an unchanged report, and never twice for the same content. A fake
OpenAI client stands in for the API; app.extraction.plan_evidence.
extract_pdf_pages is stubbed so no real PDF file is needed (mirrors
tests/test_extract_plan_evidence_pipeline.py's own pattern)."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.db.models import LocalPlan, MonitoredReport, PolicyChangeEvent
from app.extraction.plan_evidence import CATEGORIES
from app.policy.extract_plan_evidence import run_extraction_for_report, should_extract


class _FakeUsage:
    input_tokens = 100
    output_tokens = 20


class _FakeResponse:
    def __init__(self, output_text):
        self.output_text = output_text
        self.usage = _FakeUsage()


class _FakeClient:
    def __init__(self, facts_by_category):
        self._facts_by_category = facts_by_category
        outer = self

        class _Responses:
            def create(self, model, input, text):
                category = text["format"]["name"].removeprefix("plan_evidence_")
                return _FakeResponse(json.dumps({"facts": outer._facts_by_category[category]}))

        self.responses = _Responses()


def _null_facts(category):
    return [{"field": f, "value": None, "source_page": None, "source_excerpt": None, "confidence": None} for f in CATEGORIES[category]]


def _make_plan(session, **kwargs):
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Local Plan", status="draft_consultation", raw_status="draft", **kwargs)
    session.add(plan)
    session.commit()
    return plan


def _make_report(session, plan, content_hash="hash1", **kwargs):
    report = MonitoredReport(
        council_code="testcouncil", local_plan_id=plan.id, source_type="authority_monitoring_report",
        title="Test AMR", url="https://example.invalid/amr.pdf", content_hash=content_hash, status="current", **kwargs,
    )
    session.add(report)
    session.commit()
    return report


@pytest.fixture(autouse=True)
def _stub_pdf_pages():
    with patch("app.policy.extract_plan_evidence.extract_pdf_pages", return_value=[(1, "stub source text")]):
        yield


# --- should_extract gating (Part 4) ---

def test_a_never_extracted_report_should_extract():
    report = MonitoredReport(council_code="testcouncil", source_type="authority_monitoring_report", url="https://x.invalid/a.pdf", content_hash="hash1", status="current")
    assert should_extract(report) is True


def test_a_report_whose_hash_matches_its_last_extraction_should_not_extract():
    report = MonitoredReport(
        council_code="testcouncil", source_type="authority_monitoring_report", url="https://x.invalid/a.pdf",
        content_hash="hash1", status="current", last_extracted_content_hash="hash1",
    )
    assert should_extract(report) is False


def test_a_report_whose_hash_changed_since_last_extraction_should_extract():
    report = MonitoredReport(
        council_code="testcouncil", source_type="authority_monitoring_report", url="https://x.invalid/a.pdf",
        content_hash="hash2", status="current", last_extracted_content_hash="hash1",
    )
    assert should_extract(report) is True


def test_force_always_extracts_regardless_of_hash():
    report = MonitoredReport(
        council_code="testcouncil", source_type="authority_monitoring_report", url="https://x.invalid/a.pdf",
        content_hash="hash1", status="current", last_extracted_content_hash="hash1",
    )
    assert should_extract(report, force=True) is True


# --- run_extraction_for_report: only runs when should_extract, links events, records extraction state ---

def test_new_report_runs_extraction_and_records_state(session):
    plan = _make_plan(session)
    report = _make_report(session, plan)
    facts = _null_facts("housing_delivery")
    facts[0] = {"field": "latest_reporting_period", "value": "2023/24", "source_page": 4,
                "source_excerpt": "the reporting period is 2023/24", "confidence": "high"}
    client = _FakeClient({"housing_delivery": facts, "five_year_supply": _null_facts("five_year_supply")})

    stats = run_extraction_for_report(session, client, report, pdf_path="unused.pdf", first_page=1, last_page=1)

    assert stats["skipped"] is False
    assert stats["events_created"] == 1
    session.refresh(report)
    assert report.last_extracted_content_hash == "hash1"
    assert report.last_extracted_prompt_version is not None
    assert report.last_extracted_at is not None

    events = session.execute(select(PolicyChangeEvent).where(PolicyChangeEvent.monitored_report_id == report.id)).scalars().all()
    assert len(events) == 1


def test_rerunning_against_an_unchanged_report_is_skipped_entirely(session):
    plan = _make_plan(session)
    report = _make_report(session, plan)
    client = _FakeClient({"housing_delivery": _null_facts("housing_delivery"), "five_year_supply": _null_facts("five_year_supply")})

    run_extraction_for_report(session, client, report, pdf_path="unused.pdf", first_page=1, last_page=1)
    second = run_extraction_for_report(session, client, report, pdf_path="unused.pdf", first_page=1, last_page=1)

    assert second["skipped"] is True
    assert second["events_created"] == 0


def test_force_reruns_even_when_unchanged(session):
    plan = _make_plan(session)
    report = _make_report(session, plan)
    facts = _null_facts("housing_delivery")
    facts[0] = {"field": "latest_reporting_period", "value": "2023/24", "source_page": 4,
                "source_excerpt": "the reporting period is 2023/24", "confidence": "high"}
    client = _FakeClient({"housing_delivery": facts, "five_year_supply": _null_facts("five_year_supply")})

    run_extraction_for_report(session, client, report, pdf_path="unused.pdf", first_page=1, last_page=1)
    forced = run_extraction_for_report(session, client, report, pdf_path="unused.pdf", first_page=1, last_page=1, force=True)

    assert forced["skipped"] is False


def test_dry_run_does_not_record_extraction_state(session):
    plan = _make_plan(session)
    report = _make_report(session, plan)
    client = _FakeClient({"housing_delivery": _null_facts("housing_delivery"), "five_year_supply": _null_facts("five_year_supply")})

    stats = run_extraction_for_report(session, client, report, pdf_path="unused.pdf", first_page=1, last_page=1, dry_run=True)

    assert stats["skipped"] is False
    session.refresh(report)
    assert report.last_extracted_content_hash is None  # dry run never commits extraction state
    assert should_extract(report) is True  # so a real run afterwards is still considered "new"


def test_a_report_content_change_after_extraction_makes_it_due_again(session):
    plan = _make_plan(session)
    report = _make_report(session, plan)
    client = _FakeClient({"housing_delivery": _null_facts("housing_delivery"), "five_year_supply": _null_facts("five_year_supply")})

    run_extraction_for_report(session, client, report, pdf_path="unused.pdf", first_page=1, last_page=1)
    assert should_extract(report) is False

    report.content_hash = "hash2"  # simulates a same-URL replacement's fresh edition
    session.commit()
    assert should_extract(report) is True

    third = run_extraction_for_report(session, client, report, pdf_path="unused.pdf", first_page=1, last_page=1)
    assert third["skipped"] is False
    session.refresh(report)
    assert report.last_extracted_content_hash == "hash2"
