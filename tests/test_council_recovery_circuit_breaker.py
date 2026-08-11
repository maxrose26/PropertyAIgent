"""Hotfix: Recovery-First Council Processing + Portal Circuit Breaker -
focused tests for:

1. app.pipeline.portal_circuit_breaker (CouncilPortalCircuitBreaker,
   is_portal_host_failure, PORTAL_CIRCUIT_FAILURE_THRESHOLD) in isolation.
2. Its wiring into stage_documents/discover_and_store_documents_for_application
   and stage_fetch_missing_parents - circuit opens, remaining portal work is
   skipped, already-successful work is preserved, health classification
   stays truthful.
3. Recovery-first ordering within stage_documents' own eligible set.
4. Regression guards: PR A behaviour, evidence sufficiency, legacy
   protection, AI-free Daily Discovery, and Stockport 429/get_with_retry
   pacing are all unaffected by this hotfix.

Uses the same in-memory-SQLite `session` fixture as the rest of this suite
(tests/conftest.py) - "testcouncil"/"othercouncil" already present.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.config import CouncilConfig
from app.db.models import Application, Document
from app.pipeline.acquisition_health import AcquisitionHealth
from app.pipeline.portal_circuit_breaker import (
    PORTAL_CIRCUIT_FAILURE_THRESHOLD,
    CouncilPortalCircuitBreaker,
    is_portal_host_failure,
)
from app.pipeline.run_weekly import (
    DOCUMENT_DISCOVERY_ELIGIBLE,
    discover_and_store_documents_for_application,
    stage_documents,
    stage_fetch_missing_parents,
)


def _council_config(code: str = "testcouncil") -> CouncilConfig:
    return CouncilConfig(
        code=code, name=code, base_url="https://example.invalid",
        date_field_mode="received", doc_system="idox", anite_base_url=None,
        unit_threshold=10, region=None, country=None,
    )


def _fake_row(name: str, doc_type_raw: str = "", source_url: str | None = None, local_path=None):
    return MagicMock(document_name=name, doc_type_raw=doc_type_raw, source_url=source_url, local_path=local_path, referer=None)


def _add_application(session, *, reference: str, council_code: str = "testcouncil") -> Application:
    application = Application(
        council_code=council_code, reference=reference,
        summary_url=f"https://example.invalid/{reference}",
    )
    session.add(application)
    session.commit()
    return application


def _add_document(session, application: Application, doc_type: str = "application_form", *, source_url: str | None = None) -> Document:
    document = Document(
        application_id=application.id, doc_type=doc_type,
        document_name=f"{doc_type}.pdf", source_url=source_url,
        text_extracted=True, extracted_text="text", downloaded_at=dt.datetime.now(dt.timezone.utc),
    )
    session.add(document)
    session.commit()
    return document


# --- A: CouncilPortalCircuitBreaker / is_portal_host_failure in isolation ----


def test_threshold_constant_is_three():
    assert PORTAL_CIRCUIT_FAILURE_THRESHOLD == 3


def test_one_connect_timeout_does_not_open_circuit():
    breaker = CouncilPortalCircuitBreaker(council_code="trafford")
    opened = breaker.record_failure(requests.exceptions.ConnectTimeout(), stage="documents")
    assert opened is False
    assert breaker.is_open is False
    assert breaker.consecutive_host_failures == 1


def test_second_consecutive_connect_timeout_does_not_open_circuit():
    breaker = CouncilPortalCircuitBreaker(council_code="trafford")
    breaker.record_failure(requests.exceptions.ConnectTimeout(), stage="documents")
    opened = breaker.record_failure(requests.exceptions.ConnectTimeout(), stage="documents")
    assert opened is False
    assert breaker.is_open is False
    assert breaker.consecutive_host_failures == 2


def test_third_consecutive_connect_timeout_opens_circuit():
    breaker = CouncilPortalCircuitBreaker(council_code="trafford")
    breaker.record_failure(requests.exceptions.ConnectTimeout(), stage="documents")
    breaker.record_failure(requests.exceptions.ConnectTimeout(), stage="documents")
    opened = breaker.record_failure(requests.exceptions.ConnectTimeout(), stage="documents")
    assert opened is True
    assert breaker.is_open is True
    assert breaker.open_reason == "portal_unavailable"


def test_successful_request_resets_consecutive_failure_count():
    breaker = CouncilPortalCircuitBreaker(council_code="trafford")
    breaker.record_failure(requests.exceptions.ConnectTimeout(), stage="documents")
    breaker.record_failure(requests.exceptions.ConnectTimeout(), stage="documents")
    assert breaker.consecutive_host_failures == 2
    breaker.record_success()
    assert breaker.consecutive_host_failures == 0
    assert breaker.is_open is False


def test_timeout_success_timeout_timeout_does_not_prematurely_open():
    """3 consecutive, not 3 accumulated anywhere - two failures either
    side of a success must not add up to opening the circuit."""
    breaker = CouncilPortalCircuitBreaker(council_code="trafford")
    breaker.record_failure(requests.exceptions.ConnectTimeout(), stage="documents")
    breaker.record_success()
    breaker.record_failure(requests.exceptions.ConnectTimeout(), stage="documents")
    opened = breaker.record_failure(requests.exceptions.ConnectTimeout(), stage="documents")
    assert opened is False
    assert breaker.is_open is False
    assert breaker.consecutive_host_failures == 2


def test_requests_connection_error_counts_as_host_failure():
    assert is_portal_host_failure(requests.exceptions.ConnectionError()) is True


def test_playwright_timeout_error_counts_as_host_failure():
    assert is_portal_host_failure(PlaywrightTimeoutError("Timeout 30000ms exceeded")) is True


def test_http_429_does_not_open_host_unavailable_circuit():
    assert is_portal_host_failure(requests.exceptions.HTTPError("429 Client Error")) is False
    breaker = CouncilPortalCircuitBreaker(council_code="stockport")
    for _ in range(10):
        opened = breaker.record_failure(requests.exceptions.HTTPError("429 Client Error"), stage="documents")
        assert opened is False
    assert breaker.is_open is False
    assert breaker.consecutive_host_failures == 0


def test_http_404_does_not_open_circuit():
    assert is_portal_host_failure(requests.exceptions.HTTPError("404 Client Error")) is False
    breaker = CouncilPortalCircuitBreaker(council_code="testcouncil")
    breaker.record_failure(requests.exceptions.HTTPError("404 Client Error"), stage="documents")
    assert breaker.is_open is False
    assert breaker.consecutive_host_failures == 0


def test_document_specific_non_host_error_does_not_open_circuit():
    """A malformed/unparseable single document is not evidence the whole
    portal is down."""
    breaker = CouncilPortalCircuitBreaker(council_code="testcouncil")
    for _ in range(5):
        opened = breaker.record_failure(ValueError("could not parse document"), stage="documents")
        assert opened is False
    assert breaker.is_open is False
    assert breaker.consecutive_host_failures == 0


def test_fresh_breaker_instances_are_independent():
    """Item 12/13: 'next council still attempted' and 'breaker resets on
    next run' are structural guarantees of constructing a brand new
    CouncilPortalCircuitBreaker per council/run (main() does this once per
    process; scripts.run_daily_councils runs each council as its own
    subprocess - unchanged by this hotfix) - proven here by showing two
    independently-constructed instances never share state, and that a
    previously-open breaker has no bearing on a freshly-constructed one."""
    trafford = CouncilPortalCircuitBreaker(council_code="trafford")
    for _ in range(PORTAL_CIRCUIT_FAILURE_THRESHOLD):
        trafford.record_failure(requests.exceptions.ConnectTimeout(), stage="documents")
    assert trafford.is_open is True

    stockport = CouncilPortalCircuitBreaker(council_code="stockport")
    assert stockport.is_open is False
    assert stockport.consecutive_host_failures == 0

    # Simulates "the next Daily Discovery run" for Trafford itself -
    # a fresh instance, not the same object continuing.
    trafford_next_run = CouncilPortalCircuitBreaker(council_code="trafford")
    assert trafford_next_run.is_open is False


# --- B: health classification (Section 10) -----------------------------------


def test_primary_scrape_blocked_by_circuit_is_failed():
    """Mirrors main()'s own new branch exactly: if breaker.is_open before
    stage_scrape is attempted, record_primary_scrape_completed() is never
    called - only record_primary_scrape_attempt() is - and classify()
    must report FAILED, per Section 10's own definition ('primary...
    discovery could not meaningfully complete because the portal circuit
    opened')."""
    health = AcquisitionHealth()
    breaker = CouncilPortalCircuitBreaker(council_code="trafford")
    for _ in range(PORTAL_CIRCUIT_FAILURE_THRESHOLD):
        breaker.record_failure(requests.exceptions.ConnectTimeout(), stage="scrape")

    health.record_primary_scrape_attempt()
    if breaker.is_open:
        pass  # stage_scrape is skipped - record_primary_scrape_completed() never called
    else:
        health.record_primary_scrape_completed()

    assert health.classify() == "failed"


def test_supporting_only_outage_after_successful_primary_scrape_is_partial(session):
    """Primary scrape completes; the circuit then opens during document
    discovery - Section 10: PARTIAL, not FAILED."""
    import requests as _requests
    from app.pipeline.run_weekly import discover_and_store_documents_for_application

    health = AcquisitionHealth()
    health.record_primary_scrape_attempt()
    health.record_primary_scrape_completed()

    breaker = CouncilPortalCircuitBreaker(council_code="testcouncil")
    application = _add_application(session, reference="APP/1")

    with patch("app.pipeline.run_weekly.discover_documents", side_effect=_requests.exceptions.ConnectTimeout()):
        for _ in range(PORTAL_CIRCUIT_FAILURE_THRESHOLD):
            discover_and_store_documents_for_application(
                session, MagicMock(), _requests.Session(), _council_config(), application, health, breaker,
            )

    assert breaker.is_open is True
    assert health.classify() == "partial"


# --- C: stage_documents circuit integration -----------------------------------


def test_circuit_open_skips_remaining_applications_in_stage_documents(session):
    applications = [_add_application(session, reference=f"APP/{i}") for i in range(5)]
    assert len(applications) == 5

    with patch(
        "app.pipeline.run_weekly.discover_documents",
        side_effect=[requests.exceptions.ConnectTimeout()] * 3 + [[], []],
    ) as mock_discover:
        breaker = CouncilPortalCircuitBreaker(council_code="testcouncil")
        stage_documents(session, MagicMock(), _council_config(), breaker=breaker)

    assert breaker.is_open is True
    assert mock_discover.call_count == 3  # circuit opened on the 3rd - the 4th/5th never attempted
    for application in applications:
        assert application.documents_last_checked_at is None  # none completed - all remain eligible


def test_already_successful_work_survives_circuit_opening_later(session):
    """Item 16: an application processed successfully BEFORE the circuit
    opens keeps its persisted Document row and stamped timestamp -
    opening the circuit only affects applications not yet attempted."""
    ok_application = _add_application(session, reference="APP/OK")
    broken_applications = [_add_application(session, reference=f"APP/BROKEN/{i}") for i in range(4)]
    row = _fake_row("Application Form.pdf", source_url="https://example.invalid/form.pdf")

    call_plan = [[row]] + [requests.exceptions.ConnectTimeout()] * 4  # first succeeds, next 3 trip the circuit, 5th never reached
    with patch("app.pipeline.run_weekly.discover_documents", side_effect=call_plan), \
         patch("app.pipeline.run_weekly.download_document", return_value=Path("/tmp/form.pdf")), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", return_value="application_form"), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        breaker = CouncilPortalCircuitBreaker(council_code="testcouncil")
        stage_documents(session, MagicMock(), _council_config(), breaker=breaker)

    assert breaker.is_open is True
    assert ok_application.documents_last_checked_at is not None  # preserved
    assert session.query(Document).filter_by(application_id=ok_application.id).count() == 1  # preserved
    for broken in broken_applications:
        assert broken.documents_last_checked_at is None


def test_recovery_work_is_prioritised_before_new_work(session):
    """Item 18: applications that already have a Document (recovery -
    PR A's own partial-acquisition-recovery state) are attempted before
    brand-new, zero-document applications, within stage_documents' own
    single query - an early portal-health probe from real prior
    engagement, not a full stage reorder."""
    new_applications = [_add_application(session, reference=f"APP/NEW/{i}") for i in range(2)]
    recovery_applications = [_add_application(session, reference=f"APP/RECOVERY/{i}") for i in range(2)]
    for app in recovery_applications:
        _add_document(session, app)  # has a document, documents_last_checked_at still NULL - a real recovery case

    called_urls: list[str] = []

    def _record_and_return(page, requests_session, council, summary_url, dest_dir):
        called_urls.append(summary_url)
        return []

    with patch("app.pipeline.run_weekly.discover_documents", side_effect=_record_and_return):
        stage_documents(session, MagicMock(), _council_config())

    recovery_urls = {a.summary_url for a in recovery_applications}
    new_urls = {a.summary_url for a in new_applications}
    assert set(called_urls) == recovery_urls | new_urls
    last_recovery_index = max(called_urls.index(u) for u in recovery_urls)
    first_new_index = min(called_urls.index(u) for u in new_urls)
    assert last_recovery_index < first_new_index  # every recovery URL called before every new one


# --- D: stage_fetch_missing_parents circuit integration -----------------------


def test_circuit_open_skips_remaining_parent_lookups(session):
    parent_apps = [
        _add_application(session, reference=f"RM/{i}")
        for i in range(5)
    ]
    for i, app in enumerate(parent_apps):
        app.proposal = f"Reserved matters application submitted pursuant to planning permission OUT/12/{i} granted previously."
    session.commit()

    with patch(
        "app.pipeline.run_weekly.fetch_application_by_reference_idox",
        side_effect=[requests.exceptions.ConnectTimeout()] * 3 + [MagicMock(reference=None)] * 2,
    ) as mock_fetch:
        breaker = CouncilPortalCircuitBreaker(council_code="testcouncil")
        stage_fetch_missing_parents(session, MagicMock(), _council_config(), breaker=breaker)

    assert breaker.is_open is True
    assert mock_fetch.call_count == 3


# --- E: regression guards -----------------------------------------------------


def test_pr_a_partial_document_recovery_remains_intact(session):
    """Existing PR A behaviour (a failed intended download leaves
    documents_last_checked_at NULL, a later recovery stamps it) still
    works with a breaker parameter present but never tripped."""
    application = _add_application(session, reference="APP/1")
    row_ok = _fake_row("Planning Statement.pdf", source_url="https://example.invalid/ok.pdf")
    row_fails = _fake_row("Decision Notice.pdf", source_url="https://example.invalid/broken.pdf")
    breaker = CouncilPortalCircuitBreaker(council_code="testcouncil")

    with patch("app.pipeline.run_weekly.discover_documents", return_value=[row_ok, row_fails]), \
         patch("app.pipeline.run_weekly.download_document", side_effect=[Path("/tmp/ok.pdf"), ValueError("malformed")]), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", side_effect=["planning_statement", "decision_notice"]), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        discover_and_store_documents_for_application(
            session, MagicMock(), requests.Session(), _council_config(), application, None, breaker,
        )

    assert application.documents_last_checked_at is None  # partial recovery semantics unchanged
    assert breaker.is_open is False  # a ValueError is not a host failure - circuit untouched


def test_legacy_documented_applications_remain_protected(session):
    application = _add_application(session, reference="APP/LEGACY")
    _add_document(session, application)
    application.documents_legacy_unverified = True
    session.commit()

    with patch("app.pipeline.run_weekly.discover_documents") as mock_discover:
        stage_documents(session, MagicMock(), _council_config())
    mock_discover.assert_not_called()


def test_daily_discovery_still_never_imports_openai():
    """scripts/run_daily_councils.py (the Daily Discovery Cron entrypoint)
    is untouched by this hotfix - still never imports openai directly
    (run_weekly.py's own optional AI stages are a separate, --skip-by-
    default concern - see the sibling PR A test file's own version of
    this guard). The new circuit-breaker module is a pure, dependency-
    free helper - it should never need openai either."""
    repo_root = Path(__file__).resolve().parents[1]
    daily_source = (repo_root / "scripts" / "run_daily_councils.py").read_text(encoding="utf-8")
    assert "import openai" not in daily_source.lower()
    assert "from openai" not in daily_source.lower()

    breaker_source = (repo_root / "app" / "pipeline" / "portal_circuit_breaker.py").read_text(encoding="utf-8")
    assert "openai" not in breaker_source.lower()


def test_stockport_429_pacing_constants_unchanged():
    """This hotfix touches app.pipeline.run_weekly/portal_circuit_breaker
    only - app.scrapers.idox_portal's own get_with_retry/backoff/pacing
    constants (Stockport 429 handling) are untouched."""
    from app.scrapers.idox_portal import BACKOFF_BASE_SECONDS, MAX_RETRIES, REQUEST_DELAY_SECONDS
    assert MAX_RETRIES == 4
    assert REQUEST_DELAY_SECONDS == 0.4
    assert BACKOFF_BASE_SECONDS == 5.0


def test_document_discovery_eligible_query_unaffected_by_breaker_wiring(session):
    """Regression guard: DOCUMENT_DISCOVERY_ELIGIBLE itself (documents_
    last_checked_at IS NULL AND documents_legacy_unverified IS NOT TRUE)
    is untouched by this hotfix - only stage_documents' own ORDER BY on
    top of it changed."""
    from sqlalchemy import select
    new_app = _add_application(session, reference="APP/NEW")
    legacy_app = _add_application(session, reference="APP/LEGACY")
    legacy_app.documents_legacy_unverified = True
    session.commit()

    eligible = {
        a.reference for a in session.execute(
            select(Application).where(DOCUMENT_DISCOVERY_ELIGIBLE)
        ).scalars().all()
    }
    assert "APP/NEW" in eligible
    assert "APP/LEGACY" not in eligible
