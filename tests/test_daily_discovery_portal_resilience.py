"""Render Daily Discovery Portal Resilience & Truthful Run Health.

A successful production 10/10 run exposed two real problems:

1. Stockport: document-discovery requests hit HTTP 429 because
   get_idox_documents/download_document bypassed the existing, already-
   proven get_with_retry() helper entirely, and stage_documents had no
   inter-request pacing at all (unlike every other stage that talks to
   Idox).
2. Trafford: current-period scraping timed out (Playwright navigation)
   and parent lookups/document discovery hit connection-level timeouts
   (requests/urllib3 ConnectTimeout) - both with ZERO retry - and the
   whole council was still reported "OK (+0 applications)" because
   run_weekly.py's own per-stage try/except (correctly) swallows
   individual failures so one bad council can't take down the whole
   Daily Discovery run, but nothing downstream ever asked "how much of
   this run actually completed" - only "did the subprocess crash".

This file covers the fixes: extended retry/backoff/pacing (Parts 1-3),
and the new AcquisitionHealth-based SUCCESS/PARTIAL/FAILED classification
(Parts 4-7), using mocks/fakes throughout - no real council portal is ever
contacted.

Amended (Pre-Merge Health Classification Amendment): PARTIAL's own
threshold changed from "the whole supporting stage totally failed" to
"any single attempted core operation exhausted its retry budget and
ultimately failed" - the original threshold let 49 of 50 document-
discovery failures still classify SUCCESS, which conflicted with
"SUCCESS must not imply known completeness where core planning-data
acquisition actually failed". A transient error that recovers within its
own retry budget (429/ConnectTimeout/navigation timeout -> retry ->
success) is still NOT a failure - see the "transient recovery" tests
below, which exercise the REAL retry mechanism (real requests.Session.get
sequencing, not just AcquisitionHealth in isolation) to prove that.
"""
from __future__ import annotations

import subprocess as subprocess_module
import time
from unittest.mock import MagicMock, patch

import pytest
import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.pipeline.acquisition_health import AcquisitionHealth
from app.scrapers.idox_portal import (
    CONNECTION_ERROR_BACKOFF_SECONDS,
    GOTO_MAX_ATTEMPTS,
    MAX_RETRIES,
    _goto_with_retry,
    get_with_retry,
)


class _FakeResponse:
    def __init__(self, status_code: int = 200, headers: dict | None = None, text: str = ""):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} error")

    def close(self):
        self.closed = True


def _fake_session(*side_effects):
    session = MagicMock()
    session.get = MagicMock(side_effect=list(side_effects))
    return session


# --- REQUESTS / 429 ----------------------------------------------------


def test_429_with_numeric_retry_after_is_honoured(monkeypatch):
    sleeps = []
    monkeypatch.setattr("app.scrapers.idox_portal.time.sleep", lambda s: sleeps.append(s))
    session = _fake_session(
        _FakeResponse(status_code=429, headers={"Retry-After": "7"}),
        _FakeResponse(status_code=200, text="ok"),
    )

    response = get_with_retry(session, "https://example.invalid/x")

    assert response.text == "ok"
    assert sleeps == [7.0]


def test_429_without_retry_after_uses_backoff_base(monkeypatch):
    sleeps = []
    monkeypatch.setattr("app.scrapers.idox_portal.time.sleep", lambda s: sleeps.append(s))
    session = _fake_session(
        _FakeResponse(status_code=429),  # no Retry-After header
        _FakeResponse(status_code=200, text="ok"),
    )

    response = get_with_retry(session, "https://example.invalid/x")

    assert response.text == "ok"
    from app.scrapers.idox_portal import BACKOFF_BASE_SECONDS
    assert sleeps == [BACKOFF_BASE_SECONDS * 1]


def test_success_after_transient_429(monkeypatch):
    monkeypatch.setattr("app.scrapers.idox_portal.time.sleep", lambda s: None)
    session = _fake_session(
        _FakeResponse(status_code=429),
        _FakeResponse(status_code=429),
        _FakeResponse(status_code=200, text="recovered"),
    )

    response = get_with_retry(session, "https://example.invalid/x")

    assert response.text == "recovered"
    assert session.get.call_count == 3


def test_429_retry_budget_exhaustion_raises(monkeypatch):
    monkeypatch.setattr("app.scrapers.idox_portal.time.sleep", lambda s: None)
    session = _fake_session(*[_FakeResponse(status_code=429) for _ in range(MAX_RETRIES)])

    with pytest.raises(requests.exceptions.HTTPError, match="429"):
        get_with_retry(session, "https://example.invalid/x")

    assert session.get.call_count == MAX_RETRIES


def test_document_discovery_uses_retry_behaviour(monkeypatch):
    """Part 1: get_idox_documents must go through get_with_retry, not a
    bare session.get() - this is the confirmed Stockport root cause."""
    monkeypatch.setattr("app.scrapers.idox_portal.time.sleep", lambda s: None)
    from app.scrapers.documents import get_idox_documents

    session = _fake_session(
        _FakeResponse(status_code=429),
        _FakeResponse(status_code=200, text="<html><body><table></table></body></html>"),
    )

    rows = get_idox_documents(session, "https://example.invalid/applicationDetails.do?activeTab=summary&keyVal=X")

    assert rows == []  # empty table, but no exception - the 429 was transparently retried
    assert session.get.call_count == 2


def test_streamed_document_download_remains_streamed_and_bounded(monkeypatch, tmp_path):
    """Part 1: confirms download_document's own streaming/chunking/200MB-
    ceiling behaviour is unaffected by routing through get_with_retry -
    complements tests/test_salford_document_memory_diagnosis.py's own
    deeper streaming tests with a 429-then-success path specifically."""
    monkeypatch.setattr("app.extraction.pdf_text.DATA_DIR", tmp_path)
    monkeypatch.setattr("app.scrapers.idox_portal.time.sleep", lambda s: None)
    from app.extraction.pdf_text import download_document

    class _StreamedFakeResponse(_FakeResponse):
        def iter_content(self, chunk_size):
            yield b"chunk-data"

    session = _fake_session(
        _FakeResponse(status_code=429),
        _StreamedFakeResponse(status_code=200),
    )

    dest = download_document("testcouncil", "APP/1", "doc.pdf", "https://example.invalid/doc.pdf", session=session)

    assert dest is not None
    assert dest.read_bytes() == b"chunk-data"
    # stream=True was passed on BOTH attempts (the retried 429 and the
    # eventual success) - confirms the streaming contract survives retry.
    for call in session.get.call_args_list:
        assert call.kwargs.get("stream") is True


# --- CONNECTION FAILURES -------------------------------------------------


def test_connect_timeout_then_success(monkeypatch):
    sleeps = []
    monkeypatch.setattr("app.scrapers.idox_portal.time.sleep", lambda s: sleeps.append(s))
    session = _fake_session(
        requests.exceptions.ConnectTimeout("connect timeout"),
        _FakeResponse(status_code=200, text="ok"),
    )

    response = get_with_retry(session, "https://example.invalid/x")

    assert response.text == "ok"
    assert sleeps == [CONNECTION_ERROR_BACKOFF_SECONDS * 1]


def test_connection_error_then_success(monkeypatch):
    monkeypatch.setattr("app.scrapers.idox_portal.time.sleep", lambda s: None)
    session = _fake_session(
        requests.exceptions.ConnectionError("Max retries exceeded... Connection timed out"),
        _FakeResponse(status_code=200, text="ok"),
    )

    response = get_with_retry(session, "https://example.invalid/x")

    assert response.text == "ok"


def test_connection_error_exhaustion_raises_and_is_bounded(monkeypatch):
    monkeypatch.setattr("app.scrapers.idox_portal.time.sleep", lambda s: None)
    session = _fake_session(*[requests.exceptions.ConnectTimeout("timeout") for _ in range(MAX_RETRIES)])

    with pytest.raises(requests.exceptions.ConnectTimeout):
        get_with_retry(session, "https://example.invalid/x")

    assert session.get.call_count == MAX_RETRIES  # bounded - not one more, not fewer


def test_permanent_http_error_is_not_retried():
    """Part 2: 'do not retry obviously permanent HTTP failures
    indiscriminately' - a 404 must fail immediately, not consume the
    retry budget."""
    session = _fake_session(_FakeResponse(status_code=404))

    with pytest.raises(requests.exceptions.HTTPError):
        get_with_retry(session, "https://example.invalid/x")

    assert session.get.call_count == 1


def test_response_closed_on_permanent_http_error():
    fake_response = _FakeResponse(status_code=404)
    session = _fake_session(fake_response)

    with pytest.raises(requests.exceptions.HTTPError):
        get_with_retry(session, "https://example.invalid/x")

    assert fake_response.closed is True


# --- PLAYWRIGHT NAVIGATION -------------------------------------------------


def test_goto_navigation_timeout_then_success(monkeypatch):
    monkeypatch.setattr("app.scrapers.idox_portal.time.sleep", lambda s: None)
    page = MagicMock()
    page.goto = MagicMock(side_effect=[PlaywrightTimeoutError("Timeout 30000ms exceeded"), None])

    _goto_with_retry(page, "https://example.invalid/search")

    assert page.goto.call_count == 2


def test_goto_navigation_timeout_exhaustion_raises(monkeypatch):
    monkeypatch.setattr("app.scrapers.idox_portal.time.sleep", lambda s: None)
    page = MagicMock()
    page.goto = MagicMock(side_effect=PlaywrightTimeoutError("Timeout 30000ms exceeded"))

    with pytest.raises(PlaywrightTimeoutError):
        _goto_with_retry(page, "https://example.invalid/search")

    assert page.goto.call_count == GOTO_MAX_ATTEMPTS


def test_goto_no_uncontrolled_retry_loop(monkeypatch):
    """Confirms the retry is genuinely bounded, not just 'eventually
    raises' - exactly GOTO_MAX_ATTEMPTS calls, never more."""
    monkeypatch.setattr("app.scrapers.idox_portal.time.sleep", lambda s: None)
    page = MagicMock()
    page.goto = MagicMock(side_effect=PlaywrightTimeoutError("timeout"))

    with pytest.raises(PlaywrightTimeoutError):
        _goto_with_retry(page, "https://example.invalid/search")

    assert page.goto.call_count == GOTO_MAX_ATTEMPTS
    assert GOTO_MAX_ATTEMPTS <= 3  # "2-3 attempts maximum" per the approved design


def test_goto_does_not_retry_non_timeout_errors():
    """Only a navigation TIMEOUT is retried - an unrelated Playwright
    error (e.g. a closed page/context) must propagate immediately."""
    page = MagicMock()
    page.goto = MagicMock(side_effect=RuntimeError("page has been closed"))

    with pytest.raises(RuntimeError):
        _goto_with_retry(page, "https://example.invalid/search")

    assert page.goto.call_count == 1


# --- HEALTH CLASSIFICATION (AcquisitionHealth) ------------------------------


def test_healthy_primary_scrape_and_acquisition_is_success():
    health = AcquisitionHealth()
    health.record_primary_scrape_attempt()
    health.record_primary_scrape_completed()
    health.record_document_discovery(succeeded=True)
    health.record_document_discovery(succeeded=True)
    health.record_parent_lookup(succeeded=True)

    assert health.classify() == "success"


def test_material_supporting_stage_total_failure_is_partial():
    """Primary scrape completed, but document discovery totally failed
    (attempted at least once, zero successes) - the approved conservative
    "clearly material" rule."""
    health = AcquisitionHealth()
    health.record_primary_scrape_attempt()
    health.record_primary_scrape_completed()
    health.record_document_discovery(succeeded=False)
    health.record_document_discovery(succeeded=False)

    assert health.classify() == "partial"


def test_material_parent_lookup_total_failure_is_partial():
    health = AcquisitionHealth()
    health.record_primary_scrape_attempt()
    health.record_primary_scrape_completed()
    health.record_parent_lookup(succeeded=False)

    assert health.classify() == "partial"


def test_primary_scrape_failure_is_failed_even_though_process_could_exit_cleanly():
    """The exact confirmed Trafford scenario: current-period scrape
    attempted but never completed (an exception was raised and caught
    elsewhere in run_weekly.py's own per-month try/except - the subprocess
    itself still exits 0). AcquisitionHealth must classify this "failed"
    regardless of what happens downstream."""
    health = AcquisitionHealth()
    health.record_primary_scrape_attempt()
    # record_primary_scrape_completed() deliberately never called - this
    # is exactly what happens when stage_scrape raises.

    assert health.classify() == "failed"


def test_genuine_zero_application_scrape_is_not_failed():
    """A healthy scrape that happens to find nothing new today is
    SUCCESS, not FAILED - the explicit distinction the approved design
    insists on preserving. Completion, not discovery count, is what
    matters."""
    health = AcquisitionHealth()
    health.record_primary_scrape_attempt()
    health.record_primary_scrape_completed()
    # No document/parent activity at all this run - still success.

    assert health.classify() == "success"


def test_non_material_stage_activity_never_recorded_does_not_downgrade():
    """Geocoding/build-status/enrichment are never wired to
    AcquisitionHealth at all (Part 6) - confirmed by construction: there
    is no record_* method for them, so their failures structurally cannot
    affect classify()."""
    health = AcquisitionHealth()
    health.record_primary_scrape_attempt()
    health.record_primary_scrape_completed()

    assert not hasattr(health, "record_geocode")
    assert not hasattr(health, "record_build_status")
    assert not hasattr(health, "record_enrichment")
    assert health.classify() == "success"


def test_one_document_discovery_failure_out_of_fifty_is_partial():
    """Pre-merge health classification amendment - ANY unresolved core
    acquisition failure is enough for PARTIAL, not just total failure of
    the whole stage. This is the exact case the amendment exists to fix:
    49 of 50 succeeding (1 failure) previously still classified SUCCESS,
    which conflicted with "SUCCESS must not imply known completeness
    where core planning-data acquisition actually failed"."""
    health = AcquisitionHealth()
    health.record_primary_scrape_attempt()
    health.record_primary_scrape_completed()
    for _ in range(49):
        health.record_document_discovery(succeeded=True)
    health.record_document_discovery(succeeded=False)

    assert health.classify() == "partial"


def test_one_parent_lookup_failure_out_of_many_is_partial():
    health = AcquisitionHealth()
    health.record_primary_scrape_attempt()
    health.record_primary_scrape_completed()
    for _ in range(20):
        health.record_parent_lookup(succeeded=True)
    health.record_parent_lookup(succeeded=False)

    assert health.classify() == "partial"


def test_multiple_transient_errors_that_all_recover_is_success():
    """A run where document discovery/parent lookup/navigation all hit
    transient errors at SOME point, but every one of them succeeded
    within its own retry budget - no unresolved failures were ever
    recorded (record_*(succeeded=False) is only ever called in
    run_weekly.py's own except blocks, which only run AFTER retries are
    exhausted - see app.scrapers.idox_portal.get_with_retry/
    _goto_with_retry), so classify() sees zero failures despite the
    underlying transient noise."""
    health = AcquisitionHealth()
    health.record_primary_scrape_attempt()
    health.record_primary_scrape_completed()
    # Every one of these represents an operation that internally hit
    # (and recovered from) a 429/ConnectTimeout/navigation timeout -
    # only the FINAL outcome is ever recorded here.
    for _ in range(10):
        health.record_document_discovery(succeeded=True)
    for _ in range(5):
        health.record_parent_lookup(succeeded=True)

    assert health.classify() == "success"


def test_zero_unresolved_core_failures_is_success():
    health = AcquisitionHealth()
    health.record_primary_scrape_attempt()
    health.record_primary_scrape_completed()
    health.record_document_discovery(succeeded=True)
    health.record_parent_lookup(succeeded=True)

    assert health.classify() == "success"


# --- END-TO-END transient-recovery integration tests ------------------
# These exercise the REAL retry mechanism (actual requests.Session.get
# sequencing through the real stage_documents/get_idox_documents/
# get_with_retry call chain), not just AcquisitionHealth in isolation -
# direct proof that a recovered transient failure never reaches
# record_document_discovery(succeeded=False) in the first place.


def _sequenced_session_get(monkeypatch, items):
    """Makes every requests.Session().get(...) call (regardless of which
    Session instance) return/raise the next item in `items`, in order."""
    it = iter(items)

    def _get(self, *args, **kwargs):
        item = next(it)
        if isinstance(item, BaseException):
            raise item
        return item

    monkeypatch.setattr(requests.Session, "get", _get)


def _stockport_setup(session):
    from app.config import CouncilConfig
    from app.db.models import Application, Council

    session.add(Council(code="stockport", name="Stockport", base_url="https://example.invalid",
                         date_field_mode="validated", doc_system="idox"))
    session.add(Application(
        council_code="stockport", reference="APP/1",
        summary_url="https://example.invalid/applicationDetails.do?activeTab=summary&keyVal=X",
    ))
    session.commit()
    return CouncilConfig(
        code="stockport", name="stockport", base_url="https://example.invalid",
        date_field_mode="validated", doc_system="idox", anite_base_url=None,
        unit_threshold=10, region=None, country=None,
    )


def test_429_then_success_via_real_stage_documents_records_success(session, monkeypatch, tmp_path):
    """Item 3: 429 -> retry -> success, exercised through the real
    stage_documents/get_idox_documents/get_with_retry chain, must record
    a SUCCESS, not a failure - and classify() as "success" overall."""
    from app.pipeline.acquisition_health import AcquisitionHealth
    from app.pipeline.run_weekly import stage_documents

    monkeypatch.setattr("app.extraction.pdf_text.DATA_DIR", tmp_path)
    monkeypatch.setattr("app.scrapers.idox_portal.time.sleep", lambda s: None)
    monkeypatch.setattr("app.pipeline.run_weekly.time.sleep", lambda s: None)  # skip the new pacing delay in-test
    _sequenced_session_get(monkeypatch, [
        _FakeResponse(status_code=429),
        _FakeResponse(status_code=200, text="<html><body><table></table></body></html>"),
    ])

    council = _stockport_setup(session)
    health = AcquisitionHealth()
    health.record_primary_scrape_attempt()
    health.record_primary_scrape_completed()

    stage_documents(session, page=MagicMock(), council=council, health=health)

    assert health.documents_applications_failed == 0
    assert health.documents_applications_succeeded == 1
    assert health.classify() == "success"


def test_connect_timeout_then_success_via_real_stage_documents_records_success(session, monkeypatch, tmp_path):
    """Item 4: ConnectTimeout -> retry -> success, exercised end-to-end -
    the confirmed Trafford failure MODE, but recovered this time."""
    from app.pipeline.acquisition_health import AcquisitionHealth
    from app.pipeline.run_weekly import stage_documents

    monkeypatch.setattr("app.extraction.pdf_text.DATA_DIR", tmp_path)
    monkeypatch.setattr("app.scrapers.idox_portal.time.sleep", lambda s: None)
    monkeypatch.setattr("app.pipeline.run_weekly.time.sleep", lambda s: None)
    _sequenced_session_get(monkeypatch, [
        requests.exceptions.ConnectTimeout("connect timeout"),
        _FakeResponse(status_code=200, text="<html><body><table></table></body></html>"),
    ])

    council = _stockport_setup(session)
    health = AcquisitionHealth()
    health.record_primary_scrape_attempt()
    health.record_primary_scrape_completed()

    stage_documents(session, page=MagicMock(), council=council, health=health)

    assert health.documents_applications_failed == 0
    assert health.documents_applications_succeeded == 1
    assert health.classify() == "success"


def test_navigation_timeout_then_success_records_successful_parent_lookup(session, monkeypatch):
    """Item 5: a parent-lookup call that internally retried a Playwright
    navigation timeout and recovered (already proven at the _goto_with_
    retry level - see test_goto_navigation_timeout_then_success) is, from
    stage_fetch_missing_parents' own point of view, indistinguishable
    from one that succeeded immediately: it returns without raising, so
    record_parent_lookup(succeeded=True) fires. Confirms that call-site
    contract directly."""
    from app.config import CouncilConfig
    from app.db.models import Application, Council
    from app.pipeline.acquisition_health import AcquisitionHealth
    from app.pipeline.run_weekly import stage_fetch_missing_parents

    session.add(Council(code="trafford", name="Trafford", base_url="https://example.invalid",
                         date_field_mode="received", doc_system="idox"))
    session.add(Application(
        council_code="trafford", reference="RES/1",
        proposal="Reserved matters application pursuant to outline planning permission OUT/999",
    ))
    session.commit()
    council = CouncilConfig(
        code="trafford", name="trafford", base_url="https://example.invalid",
        date_field_mode="received", doc_system="idox", anite_base_url=None,
        unit_threshold=10, region=None, country=None,
    )

    from app.scrapers.idox_portal import ScrapedApplication

    fake_result = ScrapedApplication(
        reference="OUT/999", fields={"Proposal": "Outline permission for 5 dwellings"},
        summary_url="https://example.invalid/applicationDetails.do?activeTab=summary&keyVal=Y",
        further_info_url="https://example.invalid/applicationDetails.do?activeTab=details&keyVal=Y",
        keyval="Y", estimated_unit_count=None, application_category="reserved_matters",
        opportunity_classification="Confirmed", qualifies=True,
    )

    # Stands in for a call that internally hit-and-recovered-from a
    # Playwright navigation timeout via _goto_with_retry - what matters
    # here is only that it returns normally (does not raise).
    with patch("app.pipeline.run_weekly.fetch_application_by_reference_idox", return_value=fake_result):
        health = AcquisitionHealth()
        health.record_primary_scrape_attempt()
        health.record_primary_scrape_completed()
        stage_fetch_missing_parents(session, page=MagicMock(), council=council, health=health)

    assert health.parents_failed == 0
    assert health.parents_succeeded == 1
    assert health.classify() == "success"


def test_scrape_skipped_entirely_does_not_trigger_failed():
    """--skip-scrape (a manual/operator invocation, never Daily
    Discovery's own default) must not be misclassified as a failed
    primary scrape - record_primary_scrape_attempt() is simply never
    called in that case."""
    health = AcquisitionHealth()
    health.record_document_discovery(succeeded=True)

    assert health.classify() == "success"


def test_run_health_summary_line_format():
    health = AcquisitionHealth()
    health.record_primary_scrape_attempt()
    health.record_primary_scrape_completed()
    health.record_document_discovery(succeeded=False)

    line = health.summary_line()

    assert line.startswith("[run-health] status=partial")
    assert "primary_scrape_attempted=1" in line
    assert "primary_scrape_completed=1" in line
    assert "documents_applications_attempted=1" in line
    assert "documents_applications_failed=1" in line


# --- ORCHESTRATOR: parsing + priority over crash detection -----------------


def test_run_daily_councils_parses_run_health_status_into_scraperun(session):
    """End-to-end: a real [run-health] line, streamed through the same
    _on_line mechanism the orchestrator already uses for [mem] lines, is
    parsed and used as ScrapeRun.status - not the old crash-only binary."""
    from scripts.run_daily_councils import run_one_council

    def _fake_subprocess(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        on_line("[run-health] status=partial primary_scrape_attempted=1 primary_scrape_completed=1 "
                 "documents_applications_attempted=3 documents_applications_succeeded=0 documents_applications_failed=3")
        return 0

    with patch("scripts.run_daily_councils._run_council_subprocess", side_effect=_fake_subprocess):
        run = run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="scheduled")

    assert run.status == "partial"


def test_crashed_subprocess_is_failed_regardless_of_run_health_line(session):
    """Crash detection (non-zero exit) takes priority over anything the
    subprocess printed - a crash can happen at any point, including
    mid-print, so its own exit signal is the more reliable one."""
    from scripts.run_daily_councils import run_one_council

    def _fake_subprocess(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        on_line("[run-health] status=success primary_scrape_attempted=1 primary_scrape_completed=1")
        return 1  # crashed AFTER printing a (now stale) success line

    with patch("scripts.run_daily_councils._run_council_subprocess", side_effect=_fake_subprocess):
        run = run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="scheduled")

    assert run.status == "failed"


def test_trafford_style_silent_scrape_failure_is_not_reported_ok(session, capsys):
    """The exact scenario this whole implementation exists to fix: a
    subprocess that exits 0 (its own per-month try/except swallowed the
    Playwright timeout) must now be classified/printed as FAILED, not
    OK - both in ScrapeRun.status AND in the human-readable line."""
    from scripts.run_daily_councils import run_one_council

    def _fake_subprocess(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        on_line("[scrape] FAILED for 01/08/2026 -> 11/08/2026: Page.goto: Timeout 30000ms exceeded")
        on_line("[scrape] continuing to next month...")
        on_line("[run-health] status=failed primary_scrape_attempted=1 primary_scrape_completed=0")
        return 0  # the subprocess itself did NOT crash

    with patch("scripts.run_daily_councils._run_council_subprocess", side_effect=_fake_subprocess):
        run = run_one_council(session, "trafford", timeout_seconds=60, triggered_by="scheduled")

    assert run.status == "failed"
    out = capsys.readouterr().out
    assert "trafford: FAILED" in out
    assert "trafford: OK" not in out


def test_no_run_health_line_falls_back_to_success(session):
    """Backward-compatible default - a clean exit with no [run-health]
    line at all (e.g. an unexpected/older code path) still resolves to
    "success", the previous default behaviour, rather than inventing a
    new failure mode with no evidence."""
    from scripts.run_daily_councils import run_one_council

    def _fake_subprocess(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        on_line("Done.")
        return 0

    with patch("scripts.run_daily_councils._run_council_subprocess", side_effect=_fake_subprocess):
        run = run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="scheduled")

    assert run.status == "success"


def test_partial_status_prints_distinctly_not_ok_or_failed(session, capsys):
    from scripts.run_daily_councils import run_one_council

    def _fake_subprocess(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        on_line("[run-health] status=partial primary_scrape_attempted=1 primary_scrape_completed=1")
        return 0

    with patch("scripts.run_daily_councils._run_council_subprocess", side_effect=_fake_subprocess):
        run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="scheduled")

    out = capsys.readouterr().out
    assert "testcouncil: PARTIAL" in out
    assert "testcouncil: OK" not in out
    assert "testcouncil: FAILED" not in out


# --- Part 7: exit-code / orchestrator summary -------------------------------


def test_main_summary_distinguishes_success_partial_failed(monkeypatch, session, capsys):
    """Real main(), with run_one_council itself faked (no subprocess
    spawned) - proves the ACTUAL counting/print logic in main(), not a
    reimplementation of it."""
    import sys as sys_module

    import scripts.run_daily_councils as rdc

    class _FakeRun:
        def __init__(self, status):
            self.status = status

    fake_runs = {"councila": _FakeRun("success"), "councilb": _FakeRun("partial"), "councilc": _FakeRun("failed")}

    def _fake_run_one_council(sess, council_code, **kwargs):
        return fake_runs[council_code]

    monkeypatch.setattr(rdc, "init_db", lambda: None)
    monkeypatch.setattr(rdc, "get_session", lambda: session)
    monkeypatch.setattr(rdc, "run_one_council", _fake_run_one_council)
    monkeypatch.setattr(
        sys_module, "argv",
        ["run_daily_councils.py", "--council", "councila", "--council", "councilb", "--council", "councilc"],
    )

    exit_code = rdc.main()

    out = capsys.readouterr().out
    assert "1 success, 1 partial, 1 failed, 3 attempted" in out
    assert exit_code == 1  # one genuinely failed council makes the overall run unhealthy


def test_main_all_success_and_partial_exits_zero(monkeypatch, session, capsys):
    import sys as sys_module

    import scripts.run_daily_councils as rdc

    class _FakeRun:
        def __init__(self, status):
            self.status = status

    fake_runs = {"councila": _FakeRun("success"), "councilb": _FakeRun("partial")}

    def _fake_run_one_council(sess, council_code, **kwargs):
        return fake_runs[council_code]

    monkeypatch.setattr(rdc, "init_db", lambda: None)
    monkeypatch.setattr(rdc, "get_session", lambda: session)
    monkeypatch.setattr(rdc, "run_one_council", _fake_run_one_council)
    monkeypatch.setattr(
        sys_module, "argv", ["run_daily_councils.py", "--council", "councila", "--council", "councilb"],
    )

    exit_code = rdc.main()

    assert exit_code == 0  # PARTIAL still permits overall Render Cron exit 0 (Part 7)


# --- Regression guard: stage_documents pacing -------------------------------


def test_stage_documents_source_paces_with_council_request_delay(tmp_path):
    """Source-level regression guard - stage_documents must sleep
    council.request_delay_seconds once per application, matching every
    other stage that talks to Idox (scrape_month, stage_fetch_related_
    applications, fetch_application_by_reference)."""
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "app" / "pipeline" / "run_weekly.py").read_text(encoding="utf-8")
    stage_start = source.index("def stage_documents(")
    stage_end = source.index("\ndef ", stage_start + 1)
    stage_body = source[stage_start:stage_end]
    assert "time.sleep(council.request_delay_seconds)" in stage_body
