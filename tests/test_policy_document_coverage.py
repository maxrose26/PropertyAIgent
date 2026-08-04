"""Sprint 3D ("Policy Document Coverage & Discovery") - tests for
app.policy.document_types, app.policy.expected_documents,
app.policy.coverage, app.policy.document_discovery, and the
policy_document_type classification now also applied by
app.policy.report_discovery/app.policy.sources.

All external I/O (requests.get, the shared PDF downloader) is mocked -
no real network access anywhere in this file, matching the pattern
already established in tests/test_report_discovery.py.
"""
from __future__ import annotations

from unittest.mock import patch

from sqlalchemy import select

from app.db.models import LocalPlan, MonitoredReport, MonitoredSource, PolicyChangeEvent, VisualEvidence
from app.policy.coverage import build_coverage_inventory, missing_document_types
from app.policy.document_discovery import (
    MAP_LIKE_DOCUMENT_TYPES,
    discover_policy_pages,
    discover_policy_pages_for_council,
    download_policy_document,
    queue_ambiguous_policy_document,
    queue_visual_evidence_candidates,
    register_candidate_policy_sources,
)
from app.policy.document_types import POLICY_DOCUMENT_TYPES, classify_policy_document_type
from app.policy.expected_documents import expected_document_types
from app.policy.report_discovery import check_report_for_changes, register_discovered_reports


class _FakeResponse:
    def __init__(self, html: str, url: str = "https://example.invalid/planning-policy"):
        self.text = html
        self.url = url

    def raise_for_status(self):
        pass


def _make_source(session, council_code="testcouncil", source_type="policy_document_library", url="https://example.invalid/planning-policy"):
    source = MonitoredSource(council_code=council_code, url=url, source_type=source_type, title="Planning Policy")
    session.add(source)
    session.commit()
    return source


def _make_local_plan(session, council_code="testcouncil"):
    plan = LocalPlan(council_code=council_code, plan_name="Test Local Plan", status="draft_consultation", raw_status="draft")
    session.add(plan)
    session.commit()
    return plan


def _make_report(session, council_code="testcouncil", policy_document_type="policies_map", status="current", local_path=None, url="https://example.invalid/map.pdf"):
    report = MonitoredReport(
        council_code=council_code, source_type="policies_map", classification_status="auto",
        policy_document_type=policy_document_type, title="A policy document", url=url, status=status,
        local_path=local_path,
    )
    session.add(report)
    session.commit()
    return report


# --- Document classification (Part 2) --------------------------------------

def test_every_classified_type_is_in_the_declared_vocabulary():
    samples = [
        ("Stockport Policies Map", "https://stockport.gov.uk/policies-map.pdf"),
        ("Interactive Policies Map", "https://maps.stockport.gov.uk/interactive"),
        ("Authority Monitoring Report 2023/24", "https://example.gov.uk/amr.pdf"),
        ("Completely unrelated document", "https://example.gov.uk/unrelated.pdf"),
    ]
    for title, url in samples:
        doc_type, _ = classify_policy_document_type(title, url)
        assert doc_type in POLICY_DOCUMENT_TYPES


def test_stockport_policies_map_detection():
    doc_type, rule = classify_policy_document_type("Stockport Policies Map", "https://stockport.gov.uk/policies-map.pdf")
    assert doc_type == "policies_map"
    assert rule == "policies_map_keywords"


def test_interactive_map_detection_by_title():
    doc_type, _ = classify_policy_document_type("Interactive Policies Map", "https://maps.stockport.gov.uk/viewer")
    assert doc_type == "interactive_map"


def test_interactive_map_detection_by_gis_service_url():
    doc_type, _ = classify_policy_document_type("Policies Map", "https://services.arcgis.com/xyz/FeatureServer/0")
    assert doc_type == "interactive_map"


def test_masterplan_outranks_spd_when_both_keywords_present():
    # A masterplan document is a MORE specific type than the generic SPD
    # bucket it would otherwise also match - Part 2's classification must
    # not collapse the more specific signal into the generic one.
    doc_type, _ = classify_policy_document_type("Northern Gateway Masterplan SPD", "https://example.gov.uk/masterplan-spd.pdf")
    assert doc_type == "masterplan"


def test_unclassifiable_document_returns_unknown_not_none():
    doc_type, rule = classify_policy_document_type("Random unrelated notice", "https://example.gov.uk/notice.pdf")
    assert doc_type == "unknown"
    assert rule is None


def test_classification_is_apostrophe_insensitive():
    doc_type, _ = classify_policy_document_type("Authority's Monitoring Report", "https://example.gov.uk/amr.pdf")
    assert doc_type == "authority_monitoring_report"


# --- Expected-document configuration (Part 1) -------------------------------

def test_expected_document_types_returns_default_for_unconfigured_council():
    types = expected_document_types("nowhereville", config={"default": ["local_plan", "policies_map"]})
    assert types == ["local_plan", "policies_map"]


def test_expected_document_types_adds_council_specific_entries():
    config = {"default": ["local_plan"], "councils": {"stockport": {"additional": ["interactive_map"]}}}
    assert expected_document_types("stockport", config=config) == ["local_plan", "interactive_map"]


def test_expected_document_types_excludes_when_configured():
    config = {"default": ["local_plan", "policies_map"], "councils": {"testcouncil": {"exclude": ["policies_map"]}}}
    assert expected_document_types("testcouncil", config=config) == ["local_plan"]


def test_expected_document_types_drops_unrecognised_slugs_silently():
    config = {"default": ["local_plan", "not_a_real_type"]}
    assert expected_document_types("anycouncil", config=config) == ["local_plan"]


def test_expected_document_types_deduplicates():
    config = {"default": ["local_plan", "local_plan"], "councils": {"x": {"additional": ["local_plan"]}}}
    assert expected_document_types("x", config=config) == ["local_plan"]


# --- Coverage engine (Part 3) ------------------------------------------------

def test_missing_documents_when_nothing_registered(session):
    with patch("app.policy.coverage.expected_document_types", return_value=["local_plan", "policies_map"]):
        inventory = build_coverage_inventory(session, "testcouncil")
        assert {row["policy_document_type"]: row["missing"] for row in inventory} == {"local_plan": True, "policies_map": True}
        assert missing_document_types(session, "testcouncil") == ["local_plan", "policies_map"]


def test_coverage_calculation_for_a_discovered_current_report(session):
    _make_report(session, policy_document_type="policies_map", status="current", local_path="/data/map.pdf")
    with patch("app.policy.coverage.expected_document_types", return_value=["policies_map"]):
        row = build_coverage_inventory(session, "testcouncil")[0]
    assert row["discovered"] is True
    assert row["current"] is True
    assert row["missing"] is False
    assert row["downloaded"] is True
    assert row["superseded"] is False


def test_coverage_superseded_documents_tracked_separately_from_current(session):
    _make_report(session, policy_document_type="policies_map", status="superseded", url="https://example.invalid/old.pdf")
    with patch("app.policy.coverage.expected_document_types", return_value=["policies_map"]):
        row = build_coverage_inventory(session, "testcouncil")[0]
    # Discovered (something of this type has genuinely been found), but
    # NOT current - the only copy found so far is an old, superseded one.
    assert row["discovered"] is True
    assert row["superseded"] is True
    assert row["current"] is False


def test_coverage_local_plan_ingested_via_localplan_row_without_a_report(session):
    _make_local_plan(session)
    with patch("app.policy.coverage.expected_document_types", return_value=["local_plan"]):
        row = build_coverage_inventory(session, "testcouncil")[0]
    assert row["ingested"] is True
    # A LocalPlan row existing doesn't, by itself, mean a MonitoredReport
    # was ever discovered for it (this project's real Local Plan PDFs are
    # frequently registered directly, not scraped from an index page).
    assert row["discovered"] is False


def test_coverage_visual_evidence_extracted_flag(session):
    report = _make_report(session, policy_document_type="policies_map", status="current")
    session.add(VisualEvidence(monitored_report_id=report.id, source_page=1, image_type="policies_map", status="current"))
    session.commit()
    with patch("app.policy.coverage.expected_document_types", return_value=["policies_map"]):
        row = build_coverage_inventory(session, "testcouncil")[0]
    assert row["visual_evidence_extracted"] is True
    assert row["ingested"] is True  # rolled up from visual_evidence_extracted


def test_coverage_policy_evidence_extracted_flag(session):
    import datetime as dt
    report = _make_report(session, policy_document_type="authority_monitoring_report", status="current")
    report.last_extracted_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    with patch("app.policy.coverage.expected_document_types", return_value=["authority_monitoring_report"]):
        row = build_coverage_inventory(session, "testcouncil")[0]
    assert row["policy_evidence_extracted"] is True


# --- Discovery: policy pages (Part 4) ---------------------------------------

_POLICY_LANDING_HTML = """
<html><body>
<a href="/planning-policy">Planning Policy</a>
<a href="/planning-policy/local-plan">Local Plan</a>
<a href="https://maps.example.invalid/interactive">Interactive Policies Map</a>
<a href="/contact-us">Contact us</a>
<a href="#top">Back to top</a>
</body></html>
"""


def test_discover_policy_pages_matches_keyword_links_only():
    candidates = discover_policy_pages(_POLICY_LANDING_HTML, "https://example.invalid/planning")
    urls = {c["url"] for c in candidates}
    assert "https://example.invalid/planning-policy" in urls
    assert "https://example.invalid/planning-policy/local-plan" in urls
    assert "https://maps.example.invalid/interactive" in urls
    assert not any("contact-us" in u for u in urls)


def test_register_candidate_policy_sources_is_idempotent(session):
    candidates = [{"url": "https://example.invalid/planning-policy", "link_text": "Planning Policy", "matched_keyword": "planning policy"}]
    first = register_candidate_policy_sources(session, "testcouncil", candidates)
    assert len(first) == 1
    second = register_candidate_policy_sources(session, "testcouncil", candidates)
    assert second == []  # duplicate discovery - nothing new registered


def test_register_candidate_policy_sources_classifies_on_registration(session):
    candidates = [{"url": "https://example.invalid/policies-map.pdf", "link_text": "Policies Map", "matched_keyword": "policies map"}]
    registered = register_candidate_policy_sources(session, "testcouncil", candidates)
    assert registered[0].policy_document_type == "policies_map"


@patch("app.policy.document_discovery.requests.get")
def test_discover_policy_pages_for_council_registers_new_sources(mock_get, session):
    mock_get.return_value = _FakeResponse(_POLICY_LANDING_HTML)
    result = discover_policy_pages_for_council(session, "testcouncil", "https://example.invalid/planning")
    assert result["fetch_failed"] is False
    assert result["new_sources_registered"] == 3


@patch("app.policy.document_discovery.requests.get")
def test_discover_policy_pages_for_council_handles_fetch_failure(mock_get, session):
    import requests

    mock_get.side_effect = requests.RequestException("boom")
    result = discover_policy_pages_for_council(session, "testcouncil", "https://example.invalid/planning")
    assert result["fetch_failed"] is True
    assert result["new_sources_registered"] == 0


# --- Ambiguous candidate queueing (Part 5) ----------------------------------

def test_queue_ambiguous_policy_document_requires_at_least_two_candidates(session):
    import pytest

    with pytest.raises(ValueError):
        queue_ambiguous_policy_document(session, "testcouncil", "policies_map", [{"url": "https://a.invalid", "title": "A"}])


def test_queue_ambiguous_policy_document_creates_a_review_event(session):
    event = queue_ambiguous_policy_document(session, "testcouncil", "policies_map", [
        {"url": "https://a.invalid/map1.pdf", "title": "Policies Map (2023)"},
        {"url": "https://b.invalid/map2.pdf", "title": "Policies Map (2024 draft)"},
    ])
    assert event.review_status == "needs_review"
    assert event.event_type == "policy_document_candidates_ambiguous"
    assert "a.invalid/map1.pdf" in event.detail
    assert "b.invalid/map2.pdf" in event.detail


# --- Download tracking (Part 3/5) -------------------------------------------

@patch("app.policy.document_discovery.download_document")
def test_download_policy_document_sets_local_path_on_success(mock_download, session):
    from pathlib import Path

    mock_download.return_value = Path("data/documents/testcouncil/policy-1/abc_map.pdf")
    report = _make_report(session, local_path=None)
    ok = download_policy_document(session, report)
    assert ok is True
    assert report.local_path == str(Path("data/documents/testcouncil/policy-1/abc_map.pdf"))


@patch("app.policy.document_discovery.download_document")
def test_download_policy_document_leaves_local_path_null_on_failure(mock_download, session):
    mock_download.return_value = None
    report = _make_report(session, local_path=None)
    ok = download_policy_document(session, report)
    assert ok is False
    assert report.local_path is None


# --- Visual Evidence queue (Part 6) ------------------------------------------

def test_queue_visual_evidence_candidates_only_includes_downloaded_map_types(session):
    with_path = _make_report(session, policy_document_type="policies_map", local_path="/data/a.pdf", url="https://x.invalid/a.pdf")
    no_path = _make_report(session, policy_document_type="policies_map", local_path=None, url="https://x.invalid/b.pdf")
    not_map_type = _make_report(session, policy_document_type="authority_monitoring_report", local_path="/data/c.pdf", url="https://x.invalid/c.pdf")

    queue = queue_visual_evidence_candidates(session, "testcouncil")
    queue_ids = {r.id for r in queue}
    assert with_path.id in queue_ids
    assert no_path.id not in queue_ids
    assert not_map_type.id not in queue_ids


def test_queue_visual_evidence_candidates_excludes_already_extracted(session):
    report = _make_report(session, policy_document_type="allocation_map", local_path="/data/a.pdf")
    session.add(VisualEvidence(monitored_report_id=report.id, source_page=1, image_type="allocation_map", status="current"))
    session.commit()
    queue = queue_visual_evidence_candidates(session, "testcouncil")
    assert report.id not in {r.id for r in queue}


def test_map_like_document_types_are_all_real_policy_document_types():
    assert MAP_LIKE_DOCUMENT_TYPES.issubset(set(POLICY_DOCUMENT_TYPES))


# --- Same-URL update vs different-URL-same-document (report_discovery.py) --

def test_same_url_content_change_carries_policy_document_type_to_new_row(session):
    source = _make_source(session, url="https://example.invalid/monitoring")
    links = [{"url": "https://example.invalid/docs/policies-map.pdf", "link_text": "Policies Map"}]
    register_discovered_reports(session, source, links)
    report = session.execute(select(MonitoredReport)).scalars().one()
    assert report.policy_document_type == "policies_map"

    # First-ever check just establishes the baseline content_hash - only
    # a SECOND check against genuinely different content reports "changed".
    with patch("app.policy.report_discovery.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse("original content", url=report.url)
        assert check_report_for_changes(session, report) == "first_check"

    with patch("app.policy.report_discovery.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse("different content, same url", url=report.url)
        outcome = check_report_for_changes(session, report)
    assert outcome == "changed"

    current = session.execute(
        select(MonitoredReport).where(MonitoredReport.status == "current")
    ).scalars().one()
    assert current.policy_document_type == "policies_map"  # carried over, not lost
    assert current.id != report.id


def test_different_url_same_document_type_is_queued_not_auto_merged(session):
    # Part 5/report_discovery's existing Part 2.6 behaviour: two DIFFERENT
    # URLs classified as the same report type never get silently merged -
    # discovering a second one queues a supersession-review event instead.
    source = _make_source(session)
    register_discovered_reports(session, source, [{"url": "https://example.invalid/docs/amr-2023.pdf", "link_text": "Authority Monitoring Report 2023"}])
    counts = register_discovered_reports(session, source, [{"url": "https://example.invalid/docs/amr-2024.pdf", "link_text": "Authority Monitoring Report 2024"}])
    assert counts["new_reports"] == 1

    events = session.execute(
        select(PolicyChangeEvent).where(PolicyChangeEvent.event_type == "report_supersession_needs_review")
    ).scalars().all()
    assert len(events) == 1
    # Both reports remain "current" until a human resolves it - never
    # auto-merged.
    current_reports = session.execute(select(MonitoredReport).where(MonitoredReport.status == "current")).scalars().all()
    assert len(current_reports) == 2


# --- Idempotent reruns ---------------------------------------------------

@patch("app.policy.document_discovery.requests.get")
def test_discover_policy_pages_for_council_is_idempotent(mock_get, session):
    mock_get.return_value = _FakeResponse(_POLICY_LANDING_HTML)
    first = discover_policy_pages_for_council(session, "testcouncil", "https://example.invalid/planning")
    second = discover_policy_pages_for_council(session, "testcouncil", "https://example.invalid/planning")
    assert first["new_sources_registered"] == 3
    assert second["new_sources_registered"] == 0


def test_coverage_inventory_is_idempotent_across_repeated_calls(session):
    _make_report(session, policy_document_type="policies_map", status="current")
    with patch("app.policy.coverage.expected_document_types", return_value=["policies_map"]):
        first = build_coverage_inventory(session, "testcouncil")
        second = build_coverage_inventory(session, "testcouncil")
    assert first == second
