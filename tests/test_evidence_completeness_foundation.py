"""Evidence Completeness Foundation (PR A) - focused tests for:

1. documents_last_checked_at replacing ~Application.documents.any() as the
   document-discovery eligibility signal, WITHOUT causing routine
   rediscovery merely because stored evidence is insufficient.
2. Evidence sufficiency (app.pipeline.evidence.is_evidence_sufficient) -
   >=3 useful documents OR >=2 of the 3 core categories, deduplicated by
   document identity.
3. Document identity/deduplication (app.pipeline.evidence.
   document_identity_key) making a future targeted rediscovery safe
   against creating duplicate Document rows.
4. The real old-schema-upgrade migration path (not Base.metadata.
   create_all() on the final schema - see the sibling AI-processing-
   predeployment-safety test file for why that distinction matters).
5. Legacy-row rollout safety: existing (pre-PR-A) Application rows must not
   be re-queued for document discovery en masse the first time this runs
   against production data.

Uses the same in-memory-SQLite `session` fixture as every other test in
this suite (tests/conftest.py) - "testcouncil"/"othercouncil" already
present.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.config import CouncilConfig
from app.db.models import Application, Base, Council, Document
from app.pipeline.evidence import (
    CORE_DOCUMENT_TYPES,
    MIN_CORE_CATEGORIES,
    MIN_USEFUL_DOCUMENTS,
    deduped_useful_documents,
    document_identity_key,
    is_evidence_sufficient,
)
from app.pipeline.run_weekly import DOCUMENT_DISCOVERY_ELIGIBLE, stage_documents


def _council_config(code: str, doc_system: str = "idox") -> CouncilConfig:
    return CouncilConfig(
        code=code, name=code, base_url="https://example.invalid",
        date_field_mode="received", doc_system=doc_system, anite_base_url=None,
        unit_threshold=10, region=None, country=None,
    )


def _fake_row(name: str, doc_type_raw: str = "", source_url: str | None = None, local_path=None):
    return MagicMock(document_name=name, doc_type_raw=doc_type_raw, source_url=source_url, local_path=local_path, referer=None)


def _add_application(session, *, reference: str, council_code: str = "testcouncil", summary_url: str | None = None) -> Application:
    # Unique per reference by default - a shared summary_url across
    # multiple test applications would make them indistinguishable to
    # anything that keys off it (e.g. a mock call's positional args).
    application = Application(
        council_code=council_code, reference=reference,
        summary_url=summary_url or f"https://example.invalid/{reference}",
    )
    session.add(application)
    session.commit()
    return application


def _add_document(session, application: Application, doc_type: str, *, source_url: str | None = None, document_name: str | None = None) -> Document:
    document = Document(
        application_id=application.id, doc_type=doc_type,
        document_name=document_name or f"{doc_type}.pdf", source_url=source_url,
        text_extracted=True, extracted_text="text", downloaded_at=dt.datetime.now(dt.timezone.utc),
    )
    session.add(document)
    session.commit()
    return document


# --- A: new application eligibility ------------------------------------------


def test_new_application_with_no_prior_check_is_eligible(session):
    _add_application(session, reference="APP/1")
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[]) as mock_discover:
        stage_documents(session, page=MagicMock(), council=_council_config("testcouncil"))
    mock_discover.assert_called_once()


def test_successful_listing_advances_documents_last_checked_at(session):
    application = _add_application(session, reference="APP/1")
    assert application.documents_last_checked_at is None
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[]):
        stage_documents(session, page=MagicMock(), council=_council_config("testcouncil"))
    assert application.documents_last_checked_at is not None


def test_zero_useful_documents_still_counts_as_completed_listing_check(session):
    """A listing that finds documents but none of them useful (or finds
    nothing at all) must still advance documents_last_checked_at - this is
    what stops a zero-useful-document application being re-attempted every
    single day forever."""
    application = _add_application(session, reference="APP/1")
    irrelevant_row = _fake_row("Site Location Plan.pdf")
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[irrelevant_row]):
        stage_documents(session, page=MagicMock(), council=_council_config("testcouncil"))
    assert application.documents_last_checked_at is not None
    assert session.query(Document).filter_by(application_id=application.id).count() == 0


def test_listing_failure_does_not_advance_documents_last_checked_at(session):
    application = _add_application(session, reference="APP/1")
    with patch("app.pipeline.run_weekly.discover_documents", side_effect=RuntimeError("portal unreachable")):
        stage_documents(session, page=MagicMock(), council=_council_config("testcouncil"))
    assert application.documents_last_checked_at is None


# --- B: existing application - no routine rediscovery -----------------------


def test_previously_checked_sufficient_evidence_no_routine_rediscovery(session):
    application = _add_application(session, reference="APP/1")
    for i in range(3):
        _add_document(session, application, "planning_statement", source_url=f"https://example.invalid/doc{i}.pdf")
    application.documents_last_checked_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    assert is_evidence_sufficient(application) is True

    with patch("app.pipeline.run_weekly.discover_documents") as mock_discover:
        stage_documents(session, page=MagicMock(), council=_council_config("testcouncil"))
    mock_discover.assert_not_called()


def test_previously_checked_insufficient_evidence_also_no_routine_rediscovery(session):
    """The critical product rule: insufficient evidence must NOT cause
    daily document rediscovery on its own."""
    application = _add_application(session, reference="APP/1")
    _add_document(session, application, "planning_statement", source_url="https://example.invalid/doc.pdf")
    application.documents_last_checked_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    assert is_evidence_sufficient(application) is False

    with patch("app.pipeline.run_weekly.discover_documents") as mock_discover:
        stage_documents(session, page=MagicMock(), council=_council_config("testcouncil"))
    mock_discover.assert_not_called()


def test_application_not_repeatedly_checked_merely_because_insufficient(session):
    """Run stage_documents twice in a row for an application whose first
    check yields insufficient evidence - the second run must not re-check
    it."""
    _add_application(session, reference="APP/1")
    insufficient_row = _fake_row("Planning Statement.pdf", source_url="https://example.invalid/ps.pdf")

    with patch("app.pipeline.run_weekly.discover_documents", return_value=[insufficient_row]) as mock_discover, \
         patch("app.pipeline.run_weekly.download_document", return_value=Path("/tmp/fake.pdf")), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="Planning Statement text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", return_value="planning_statement"), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        stage_documents(session, page=MagicMock(), council=_council_config("testcouncil"))
    assert mock_discover.call_count == 1

    with patch("app.pipeline.run_weekly.discover_documents") as mock_discover_2:
        stage_documents(session, page=MagicMock(), council=_council_config("testcouncil"))
    mock_discover_2.assert_not_called()


# --- C: evidence sufficiency rule --------------------------------------------


def test_zero_useful_documents_is_insufficient(session):
    application = _add_application(session, reference="APP/1")
    assert is_evidence_sufficient(application) is False


def test_one_useful_document_insufficient_unless_core_rule_satisfied(session):
    application = _add_application(session, reference="APP/1")
    _add_document(session, application, "planning_statement", source_url="https://example.invalid/1.pdf")
    assert is_evidence_sufficient(application) is False


def test_two_ordinary_useful_documents_insufficient(session):
    """2 useful documents, neither combination satisfying the 2-core-
    category rule (e.g. two non-core categories) - below both thresholds."""
    application = _add_application(session, reference="APP/1")
    _add_document(session, application, "application_form", source_url="https://example.invalid/1.pdf")
    _add_document(session, application, "s106", source_url="https://example.invalid/2.pdf")
    assert is_evidence_sufficient(application) is False


def test_three_useful_documents_sufficient(session):
    application = _add_application(session, reference="APP/1")
    _add_document(session, application, "application_form", source_url="https://example.invalid/1.pdf")
    _add_document(session, application, "design_access", source_url="https://example.invalid/2.pdf")
    _add_document(session, application, "s106", source_url="https://example.invalid/3.pdf")
    assert is_evidence_sufficient(application) is True


def test_two_qualifying_core_documents_sufficient(session):
    application = _add_application(session, reference="APP/1")
    _add_document(session, application, "planning_statement", source_url="https://example.invalid/1.pdf")
    _add_document(session, application, "decision_notice", source_url="https://example.invalid/2.pdf")
    assert len(CORE_DOCUMENT_TYPES) == 3
    assert is_evidence_sufficient(application) is True


def test_decision_notice_plus_officer_report_also_sufficient(session):
    """Explicit second combination from the amendment's own examples -
    the rule is about DISTINCT categories, not any one specific pair."""
    application = _add_application(session, reference="APP/1")
    _add_document(session, application, "decision_notice", source_url="https://example.invalid/1.pdf")
    _add_document(session, application, "officer_report", source_url="https://example.invalid/2.pdf")
    assert is_evidence_sufficient(application) is True


def test_two_documents_from_the_same_core_category_alone_insufficient(session):
    """Amendment Section 5's explicit clarification: two Planning
    Statements only does NOT satisfy the two-DISTINCT-core-category route
    - only one distinct category (planning_statement) is represented,
    regardless of how many documents carry it. Only 2 useful documents
    total, so the >=3-unique-document route doesn't apply either."""
    application = _add_application(session, reference="APP/1")
    _add_document(session, application, "planning_statement", source_url="https://example.invalid/1.pdf")
    _add_document(session, application, "planning_statement", source_url="https://example.invalid/2.pdf")
    core_categories_present = {d.doc_type for d in deduped_useful_documents(application)} & CORE_DOCUMENT_TYPES
    assert core_categories_present == {"planning_statement"}  # one distinct category, not two
    assert is_evidence_sufficient(application) is False


def test_two_documents_same_core_category_plus_a_third_useful_document_is_sufficient(session):
    """The amendment's own worked example: two Planning Statements alone
    are insufficient, but MAY still satisfy the >=3-unique-useful-document
    route if a third, genuinely distinct useful document exists - the two
    routes are independent, and this one doesn't require category
    diversity at all."""
    application = _add_application(session, reference="APP/1")
    _add_document(session, application, "planning_statement", source_url="https://example.invalid/1.pdf")
    _add_document(session, application, "planning_statement", source_url="https://example.invalid/2.pdf")
    _add_document(session, application, "application_form", source_url="https://example.invalid/3.pdf")
    assert is_evidence_sufficient(application) is True


def test_irrelevant_documents_do_not_contribute(session):
    application = _add_application(session, reference="APP/1")
    _add_document(session, application, "other", source_url="https://example.invalid/1.pdf")
    _add_document(session, application, "other", source_url="https://example.invalid/2.pdf")
    _add_document(session, application, "other", source_url="https://example.invalid/3.pdf")
    assert is_evidence_sufficient(application) is False


def test_duplicate_evidence_does_not_falsely_satisfy_threshold(session):
    """Three Document rows, but only two distinct pieces of evidence (same
    source_url twice) - deduplication must prevent this reaching the
    3-document threshold."""
    application = _add_application(session, reference="APP/1")
    _add_document(session, application, "application_form", source_url="https://example.invalid/same.pdf")
    _add_document(session, application, "application_form", source_url="https://example.invalid/same.pdf")
    _add_document(session, application, "design_access", source_url="https://example.invalid/2.pdf")
    assert len(deduped_useful_documents(application)) == 2  # not 3
    assert is_evidence_sufficient(application) is False


# --- D: failure recovery / identity / dedup ----------------------------------


def test_failed_listing_request_remains_eligible_for_recovery(session):
    application = _add_application(session, reference="APP/1")
    with patch("app.pipeline.run_weekly.discover_documents", side_effect=RuntimeError("boom")):
        stage_documents(session, page=MagicMock(), council=_council_config("testcouncil"))

    session.refresh(application)
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[]) as mock_discover:
        stage_documents(session, page=MagicMock(), council=_council_config("testcouncil"))
    mock_discover.assert_called_once()  # still eligible after the failure


def test_rediscovering_existing_document_does_not_duplicate_it(session):
    """Simulates a future targeted rediscovery (PR B) of an application
    that already has documents - a document already stored must not be
    inserted again when the same listing row appears again. Uses
    discover_and_store_documents_for_application directly (Section 13's
    requirement: a future caller must be able to invoke document discovery
    for one specific Application at will, independent of stage_documents'
    own bulk DOCUMENT_DISCOVERY_ELIGIBLE query, which by this point in the
    test would correctly no longer select this application at all, since
    it already completed successfully)."""
    import requests
    from app.pipeline.run_weekly import discover_and_store_documents_for_application

    application = _add_application(session, reference="APP/1")
    existing_row = _fake_row("Planning Statement.pdf", source_url="https://example.invalid/ps.pdf")
    new_row = _fake_row("Decision Notice.pdf", source_url="https://example.invalid/decision.pdf")
    requests_session = requests.Session()

    with patch("app.pipeline.run_weekly.discover_documents", return_value=[existing_row]), \
         patch("app.pipeline.run_weekly.download_document", return_value=Path("/tmp/fake.pdf")), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", return_value="planning_statement"), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        succeeded = discover_and_store_documents_for_application(
            session, MagicMock(), requests_session, _council_config("testcouncil"), application,
        )
    assert succeeded is True
    assert session.query(Document).filter_by(application_id=application.id).count() == 1

    # A future targeted rediscovery calls this function directly for the
    # ONE application it cares about - it never goes through stage_
    # documents' bulk DOCUMENT_DISCOVERY_ELIGIBLE query at all, which is
    # exactly why this remains safe even though that query would still
    # correctly exclude this (already-documented) application.
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[existing_row, new_row]), \
         patch("app.pipeline.run_weekly.download_document", return_value=Path("/tmp/fake2.pdf")), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", side_effect=["planning_statement", "decision_notice"]), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        succeeded_2 = discover_and_store_documents_for_application(
            session, MagicMock(), requests_session, _council_config("testcouncil"), application,
        )
    assert succeeded_2 is True

    docs = session.query(Document).filter_by(application_id=application.id).all()
    assert len(docs) == 2  # the existing one was NOT duplicated
    doc_types = {d.doc_type for d in docs}
    assert doc_types == {"planning_statement", "decision_notice"}  # the new one WAS added


def test_document_identity_key_prefers_source_url_falls_back_to_name():
    assert document_identity_key("https://x/1.pdf", "Doc.pdf") == ("url", "https://x/1.pdf")
    assert document_identity_key(None, "Doc.pdf") == ("name", "Doc.pdf")
    assert document_identity_key("", "Doc.pdf") == ("name", "Doc.pdf")


# --- D2: Partial Initial Document Acquisition Recovery (pre-merge amendment) -


def test_listing_success_all_intended_downloads_succeed_advances_timestamp(session):
    import requests
    from app.pipeline.run_weekly import discover_and_store_documents_for_application

    application = _add_application(session, reference="APP/1")
    row_a = _fake_row("Planning Statement.pdf", source_url="https://example.invalid/a.pdf")
    row_b = _fake_row("Decision Notice.pdf", source_url="https://example.invalid/b.pdf")

    with patch("app.pipeline.run_weekly.discover_documents", return_value=[row_a, row_b]), \
         patch("app.pipeline.run_weekly.download_document", side_effect=[Path("/tmp/a.pdf"), Path("/tmp/b.pdf")]), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", side_effect=["planning_statement", "decision_notice"]), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        discover_and_store_documents_for_application(
            session, MagicMock(), requests.Session(), _council_config("testcouncil"), application,
        )

    assert application.documents_last_checked_at is not None
    assert session.query(Document).filter_by(application_id=application.id).count() == 2


def test_listing_success_already_known_documents_only_advances_timestamp(session):
    """A recovery-style call where the listing returns only documents
    already persisted (nothing new, nothing missing) - a fully complete
    acquisition, even though every row is a duplicate skip rather than a
    fresh download."""
    import requests
    from app.pipeline.run_weekly import discover_and_store_documents_for_application

    application = _add_application(session, reference="APP/1")
    row = _fake_row("Planning Statement.pdf", source_url="https://example.invalid/ps.pdf")
    requests_session = requests.Session()

    with patch("app.pipeline.run_weekly.discover_documents", return_value=[row]), \
         patch("app.pipeline.run_weekly.download_document", return_value=Path("/tmp/a.pdf")), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", return_value="planning_statement"), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        discover_and_store_documents_for_application(
            session, MagicMock(), requests_session, _council_config("testcouncil"), application,
        )
    first_stamp = application.documents_last_checked_at
    assert first_stamp is not None

    # Force a second pass (a future PR B would trigger this on demand) -
    # the listing returns the SAME already-known row only.
    application.documents_last_checked_at = None
    session.commit()
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[row]), \
         patch("app.pipeline.run_weekly.download_document") as mock_download:
        discover_and_store_documents_for_application(
            session, MagicMock(), requests_session, _council_config("testcouncil"), application,
        )
    mock_download.assert_not_called()  # already known - never re-downloaded
    assert application.documents_last_checked_at is not None  # still a completed pass
    assert session.query(Document).filter_by(application_id=application.id).count() == 1  # not duplicated


def test_one_intended_download_failure_leaves_timestamp_null(session):
    """The amendment's central case: listing succeeds, one of two intended
    documents fails to download - the acquisition pass is incomplete, so
    documents_last_checked_at must NOT be stamped."""
    import requests
    from app.pipeline.run_weekly import discover_and_store_documents_for_application

    application = _add_application(session, reference="APP/1")
    row_ok = _fake_row("Planning Statement.pdf", source_url="https://example.invalid/ok.pdf")
    row_fails = _fake_row("Decision Notice.pdf", source_url="https://example.invalid/broken.pdf")

    with patch("app.pipeline.run_weekly.discover_documents", return_value=[row_ok, row_fails]), \
         patch("app.pipeline.run_weekly.download_document", side_effect=[Path("/tmp/ok.pdf"), RuntimeError("connection reset")]), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", side_effect=["planning_statement", "decision_notice"]), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        succeeded = discover_and_store_documents_for_application(
            session, MagicMock(), requests.Session(), _council_config("testcouncil"), application,
        )

    assert succeeded is True  # the LISTING itself succeeded (distinct claim - see item 6)
    assert application.documents_last_checked_at is None  # but the pass did not complete
    docs = session.query(Document).filter_by(application_id=application.id).all()
    assert len(docs) == 1  # only the successful one was persisted
    assert docs[0].doc_type == "planning_statement"


def test_recovery_run_skips_persisted_and_downloads_missing_document(session):
    """After a partial failure, a subsequent call (the "recovery run") for
    the SAME application must not re-download the document that already
    succeeded, and must retry the one that previously failed."""
    import requests
    from app.pipeline.run_weekly import discover_and_store_documents_for_application

    application = _add_application(session, reference="APP/1")
    row_ok = _fake_row("Planning Statement.pdf", source_url="https://example.invalid/ok.pdf")
    row_fails = _fake_row("Decision Notice.pdf", source_url="https://example.invalid/broken.pdf")
    requests_session = requests.Session()

    with patch("app.pipeline.run_weekly.discover_documents", return_value=[row_ok, row_fails]), \
         patch("app.pipeline.run_weekly.download_document", side_effect=[Path("/tmp/ok.pdf"), RuntimeError("boom")]), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", side_effect=["planning_statement", "decision_notice"]), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        discover_and_store_documents_for_application(
            session, MagicMock(), requests_session, _council_config("testcouncil"), application,
        )
    assert application.documents_last_checked_at is None
    assert session.query(Document).filter_by(application_id=application.id).count() == 1

    # Recovery run: the routine DOCUMENT_DISCOVERY_ELIGIBLE query would
    # now correctly re-select this application (documents_last_checked_at
    # IS NULL - no ~Application.documents.any() clause blocking it, per
    # this amendment's own fix) - simulated here via a direct call.
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[row_ok, row_fails]), \
         patch("app.pipeline.run_weekly.download_document") as mock_download, \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", side_effect=["planning_statement", "decision_notice"]), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        mock_download.return_value = Path("/tmp/broken-recovered.pdf")
        discover_and_store_documents_for_application(
            session, MagicMock(), requests_session, _council_config("testcouncil"), application,
        )

    mock_download.assert_called_once()  # only the missing document, not the already-successful one
    called_url = mock_download.call_args.args[3] if len(mock_download.call_args.args) > 3 else mock_download.call_args.kwargs.get("source_url")
    docs = session.query(Document).filter_by(application_id=application.id).all()
    assert len(docs) == 2
    assert {d.doc_type for d in docs} == {"planning_statement", "decision_notice"}


def test_successful_recovery_stamps_timestamp(session):
    import requests
    from app.pipeline.run_weekly import discover_and_store_documents_for_application

    application = _add_application(session, reference="APP/1")
    row_ok = _fake_row("Planning Statement.pdf", source_url="https://example.invalid/ok.pdf")
    row_fails = _fake_row("Decision Notice.pdf", source_url="https://example.invalid/broken.pdf")
    requests_session = requests.Session()

    with patch("app.pipeline.run_weekly.discover_documents", return_value=[row_ok, row_fails]), \
         patch("app.pipeline.run_weekly.download_document", side_effect=[Path("/tmp/ok.pdf"), RuntimeError("boom")]), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", side_effect=["planning_statement", "decision_notice"]), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        discover_and_store_documents_for_application(
            session, MagicMock(), requests_session, _council_config("testcouncil"), application,
        )
    assert application.documents_last_checked_at is None

    with patch("app.pipeline.run_weekly.discover_documents", return_value=[row_ok, row_fails]), \
         patch("app.pipeline.run_weekly.download_document", return_value=Path("/tmp/recovered.pdf")), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", side_effect=["planning_statement", "decision_notice"]), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        discover_and_store_documents_for_application(
            session, MagicMock(), requests_session, _council_config("testcouncil"), application,
        )

    assert application.documents_last_checked_at is not None  # now complete - stamped


def test_repeated_recovery_does_not_duplicate_documents(session):
    """Three calls in sequence: partial failure, successful recovery,
    then a THIRD call (e.g. a future manual refresh) with the same
    listing - none of the already-persisted documents must ever
    duplicate."""
    import requests
    from app.pipeline.run_weekly import discover_and_store_documents_for_application

    application = _add_application(session, reference="APP/1")
    row_ok = _fake_row("Planning Statement.pdf", source_url="https://example.invalid/ok.pdf")
    row_fails = _fake_row("Decision Notice.pdf", source_url="https://example.invalid/broken.pdf")
    requests_session = requests.Session()

    with patch("app.pipeline.run_weekly.discover_documents", return_value=[row_ok, row_fails]), \
         patch("app.pipeline.run_weekly.download_document", side_effect=[Path("/tmp/ok.pdf"), RuntimeError("boom")]), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", side_effect=["planning_statement", "decision_notice"]), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        discover_and_store_documents_for_application(
            session, MagicMock(), requests_session, _council_config("testcouncil"), application,
        )

    with patch("app.pipeline.run_weekly.discover_documents", return_value=[row_ok, row_fails]), \
         patch("app.pipeline.run_weekly.download_document", return_value=Path("/tmp/recovered.pdf")), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", side_effect=["planning_statement", "decision_notice"]), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        discover_and_store_documents_for_application(
            session, MagicMock(), requests_session, _council_config("testcouncil"), application,
        )
    assert session.query(Document).filter_by(application_id=application.id).count() == 2

    application.documents_last_checked_at = None  # simulate a future manual refresh re-opening it
    session.commit()
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[row_ok, row_fails]), \
         patch("app.pipeline.run_weekly.download_document") as mock_download:
        discover_and_store_documents_for_application(
            session, MagicMock(), requests_session, _council_config("testcouncil"), application,
        )
    mock_download.assert_not_called()  # both already known - nothing to download
    assert session.query(Document).filter_by(application_id=application.id).count() == 2  # still 2, not 4


# --- E: legacy / migration ----------------------------------------------------


def _build_old_applications_table(engine) -> MetaData:
    """Minimal pre-PR-A `applications` table - same convention as the AI
    Processing Reliability pre-deployment-safety test file's sibling
    helper - deliberately WITHOUT documents_last_checked_at."""
    old_metadata = MetaData()
    Table(
        "applications", old_metadata,
        Column("id", Integer, primary_key=True),
        Column("council_code", String(20)),
        Column("reference", String(100)),
    )
    old_metadata.create_all(engine)
    return old_metadata


def test_real_old_schema_upgrade_adds_documents_last_checked_at_safely():
    from app.db.session import migrate_schema

    engine = create_engine("sqlite:///:memory:", future=True)
    old_metadata = _build_old_applications_table(engine)
    with engine.begin() as conn:
        conn.execute(
            Table("applications", old_metadata).insert(),
            [{"id": 1, "council_code": "testcouncil", "reference": "APP/OLD/1"}],
        )

    created_tables, added_columns = migrate_schema(engine)
    assert ("applications", "documents_last_checked_at") in added_columns


def test_existing_rows_are_not_falsely_stamped_with_current_time():
    """The migration must leave documents_last_checked_at NULL for
    existing rows - never backfilled to "now", which would falsely claim
    those applications were just checked."""
    from app.db.session import migrate_schema

    engine = create_engine("sqlite:///:memory:", future=True)
    old_metadata = _build_old_applications_table(engine)
    with engine.begin() as conn:
        conn.execute(
            Table("applications", old_metadata).insert(),
            [{"id": 1, "council_code": "testcouncil", "reference": "APP/OLD/1"}],
        )

    migrate_schema(engine)

    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT documents_last_checked_at FROM applications WHERE reference = 'APP/OLD/1'"
        )).fetchone()
    assert row.documents_last_checked_at is None


def test_migration_is_idempotent_for_documents_last_checked_at():
    from app.db.session import migrate_schema

    engine = create_engine("sqlite:///:memory:", future=True)
    _build_old_applications_table(engine)

    first_created, first_added = migrate_schema(engine)
    assert ("applications", "documents_last_checked_at") in first_added

    second_created, second_added = migrate_schema(engine)
    assert second_added == []


def _migrate_legacy_fixture(applications_with_documents: list[str], applications_without: list[str]):
    """Shared real-migration fixture builder for this section: an old-
    schema `applications` table (no documents_last_checked_at/
    documents_legacy_unverified columns at all) with some references
    carrying Document rows and some not, then the real migrate_schema()
    applied on top - exactly the production rollout moment. Returns a
    bound Session ready to query/exercise stage_documents against."""
    from app.db.session import migrate_schema

    engine = create_engine("sqlite:///:memory:", future=True)
    old_metadata = _build_old_applications_table(engine)
    Base.metadata.create_all(engine, tables=[Council.__table__, Document.__table__])
    downloaded_at = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    Session = sessionmaker(bind=engine, future=True)
    with Session() as _setup_session:
        _setup_session.add(Council(code='testcouncil', name='Test', base_url='https://example.invalid', date_field_mode='received', doc_system='idox'))
        _setup_session.commit()

    all_refs = applications_with_documents + applications_without
    with engine.begin() as conn:
        conn.execute(
            Table("applications", old_metadata).insert(),
            [{"id": i + 1, "council_code": "testcouncil", "reference": ref} for i, ref in enumerate(all_refs)],
        )
        if applications_with_documents:
            conn.execute(
                Document.__table__.insert(),
                [
                    {"application_id": i + 1, "doc_type": "application_form", "downloaded_at": downloaded_at}
                    for i in range(len(applications_with_documents))
                ],
            )

    migrate_schema(engine)

    Session = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    migrated_session = Session()
    for application in migrated_session.query(Application).order_by(Application.id).all():
        application.summary_url = f"https://example.invalid/{application.reference}"
    migrated_session.commit()
    return migrated_session


def test_legacy_row_with_existing_documents_is_not_requeued_for_discovery():
    """Section 11, item 1+2 (Legacy Document-State Truthfulness amendment).
    Exercised against the REAL migration path, not the in-memory `session`
    fixture.

    documents_last_checked_at must stay truthfully NULL for a legacy
    documented row - a Document row only ever proves "something downloaded
    once", never "a complete intended acquisition pass finished" (an
    earlier version of this migration inferred MAX(downloaded_at) into
    this field - rejected in review for exactly that reason). Rollout
    safety instead comes from documents_legacy_unverified, which
    DOCUMENT_DISCOVERY_ELIGIBLE (app.pipeline.run_weekly) excludes on -
    proven here end-to-end through the real migrate_schema() function,
    not by asserting on the query in isolation."""
    migrated_session = _migrate_legacy_fixture(["APP/LEGACY/1"], [])
    with migrated_session:
        application = migrated_session.get(Application, 1)
        assert application.documents_last_checked_at is None  # truthfully NULL, never inferred
        assert application.documents_legacy_unverified is True  # the actual rollout-safety signal

        with patch("app.pipeline.run_weekly.discover_documents") as mock_discover:
            stage_documents(migrated_session, page=MagicMock(), council=_council_config("testcouncil"))
        mock_discover.assert_not_called()


def test_legacy_row_with_zero_documents_remains_eligible(session):
    """Section 11, item 3: a legacy application that genuinely has zero
    stored documents (documents_last_checked_at AND documents_legacy_
    unverified both falsy) is exactly today's eligibility set - it should
    remain eligible for its first-ever discovery attempt, unchanged."""
    application = _add_application(session, reference="APP/LEGACY/2")
    assert application.documents_legacy_unverified is False
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[]) as mock_discover:
        stage_documents(session, page=MagicMock(), council=_council_config("testcouncil"))
    mock_discover.assert_called_once()


def test_legacy_row_with_zero_documents_retains_initial_discovery_path_through_real_migration():
    """Section 11, item 3, exercised through the real migration path
    alongside a documented sibling - the zero-document legacy row must be
    explicitly marked documents_legacy_unverified=False (not left NULL),
    and must be the one row still selected."""
    migrated_session = _migrate_legacy_fixture(["APP/LEGACY/DOCUMENTED"], ["APP/LEGACY/ZERO"])
    with migrated_session:
        zero_doc_app = migrated_session.query(Application).filter_by(reference="APP/LEGACY/ZERO").one()
        assert zero_doc_app.documents_legacy_unverified is False
        assert zero_doc_app.documents_last_checked_at is None

        with patch("app.pipeline.run_weekly.discover_documents", return_value=[]) as mock_discover:
            stage_documents(migrated_session, page=MagicMock(), council=_council_config("testcouncil"))
        mock_discover.assert_called_once()
        assert mock_discover.call_args.args[3] == zero_doc_app.summary_url


def test_first_run_after_migration_does_not_document_scrape_whole_corpus():
    """Section 11, items 2+11: simulates the production rollout moment
    through the REAL migration path - a mix of legacy applications (some
    with documents, some without), migrated from the old schema in one
    pass. Only the genuinely never-documented ones must be selected on
    the first Daily Discovery run afterwards - no portal-stampede
    condition for the ~708-application-sized documented set."""
    documented_refs = [f"APP/DOCUMENTED/{i}" for i in range(5)]
    new_refs = [f"APP/NEW/{i}" for i in range(3)]
    migrated_session = _migrate_legacy_fixture(documented_refs, new_refs)
    with migrated_session:
        applications = migrated_session.query(Application).order_by(Application.id).all()
        already_documented = [a for a in applications if a.reference in documented_refs]
        never_documented = [a for a in applications if a.reference in new_refs]
        assert all(a.documents_legacy_unverified is True for a in already_documented)
        assert all(a.documents_legacy_unverified is False for a in never_documented)

        with patch("app.pipeline.run_weekly.discover_documents", return_value=[]) as mock_discover:
            stage_documents(migrated_session, page=MagicMock(), council=_council_config("testcouncil"))

        assert mock_discover.call_count == 3  # only the 3 never-documented ones
        called_refs = {c.args[3] for c in mock_discover.call_args_list}  # summary_url positional arg
        for app in never_documented:
            assert app.summary_url in called_refs
        for app in already_documented:
            assert app.summary_url not in called_refs


def test_backfill_marks_legacy_flag_not_timestamp_and_is_idempotent():
    """Dedicated test of _backfill_documents_legacy_unverified itself
    (Section 11, item 10): documents_last_checked_at must NEVER be
    touched by this backfill (stays NULL for every legacy row, documented
    or not) - only documents_legacy_unverified is set, True for a row
    with >=1 Document, False for a row with zero, and re-running it must
    change nothing (idempotent, matching the existing
    _backfill_extraction_attempt_count convention this function
    follows)."""
    from app.db.session import _backfill_documents_legacy_unverified, migrate_schema

    engine = create_engine("sqlite:///:memory:", future=True)
    old_metadata = _build_old_applications_table(engine)
    Base.metadata.create_all(engine, tables=[Council.__table__, Document.__table__])
    older = dt.datetime(2023, 6, 1, tzinfo=dt.timezone.utc)
    newest = dt.datetime(2024, 3, 15, tzinfo=dt.timezone.utc)
    Session = sessionmaker(bind=engine, future=True)
    with Session() as _setup_session:
        _setup_session.add(Council(code='testcouncil', name='Test', base_url='https://example.invalid', date_field_mode='received', doc_system='idox'))
        _setup_session.commit()
    with engine.begin() as conn:
        conn.execute(
            Table("applications", old_metadata).insert(),
            [
                {"id": 1, "council_code": "testcouncil", "reference": "APP/MULTI/1"},  # 2 documents
                {"id": 2, "council_code": "testcouncil", "reference": "APP/ZERO/1"},  # 0 documents
            ],
        )
        conn.execute(
            Document.__table__.insert(),
            [
                {"application_id": 1, "doc_type": "planning_statement", "downloaded_at": older},
                {"application_id": 1, "doc_type": "decision_notice", "downloaded_at": newest},
            ],
        )

    migrate_schema(engine)  # adds both columns AND runs the backfill once

    with engine.connect() as conn:
        multi_row = conn.execute(text(
            "SELECT documents_last_checked_at, documents_legacy_unverified FROM applications WHERE reference = 'APP/MULTI/1'"
        )).fetchone()
        zero_row = conn.execute(text(
            "SELECT documents_last_checked_at, documents_legacy_unverified FROM applications WHERE reference = 'APP/ZERO/1'"
        )).fetchone()

    assert multi_row.documents_last_checked_at is None  # never inferred from downloaded_at
    assert bool(multi_row.documents_legacy_unverified) is True
    assert zero_row.documents_last_checked_at is None
    assert bool(zero_row.documents_legacy_unverified) is False  # explicitly False, not left NULL

    second_pass_updated = _backfill_documents_legacy_unverified(engine)
    assert second_pass_updated == 0  # idempotent - nothing left to backfill

    with engine.connect() as conn:
        multi_row_again = conn.execute(text(
            "SELECT documents_legacy_unverified FROM applications WHERE reference = 'APP/MULTI/1'"
        )).fetchone()
    assert bool(multi_row_again.documents_legacy_unverified) is True  # unchanged


def test_legacy_application_transitions_via_explicit_targeted_rediscovery(session):
    """Section 11, items 8+9 - the required future transition path: legacy
    existing documents / completeness unknown -> a targeted call to
    discover_and_store_documents_for_application (standing in here for a
    future PR B material-change trigger, 90-day fallback, or manual
    refresh, none of which are implemented by this amendment - only made
    possible by it) -> a successful full pass -> documents_last_checked_at
    gets a genuine timestamp AND documents_legacy_unverified is cleared,
    moving the row permanently into normal, non-legacy state."""
    from app.pipeline.run_weekly import discover_and_store_documents_for_application
    import requests

    application = _add_application(session, reference="APP/LEGACY/TRANSITION")
    _add_document(session, application, "planning_statement", source_url="https://example.invalid/existing.pdf")
    application.documents_legacy_unverified = True  # simulates a post-migration legacy-marked row
    session.commit()
    assert application.documents_last_checked_at is None

    new_row = _fake_row("Decision Notice.pdf", source_url="https://example.invalid/decision.pdf")
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[new_row]), \
         patch("app.pipeline.run_weekly.download_document", return_value=Path("/tmp/decision.pdf")), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", return_value="decision_notice"), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        discover_and_store_documents_for_application(
            session, MagicMock(), requests.Session(), _council_config("testcouncil"), application,
        )

    assert application.documents_last_checked_at is not None  # genuine timestamp, item 9
    assert application.documents_legacy_unverified is False  # marker cleared, item 8
    # DOCUMENT_DISCOVERY_ELIGIBLE now excludes it purely via the timestamp,
    # exactly like any other normal (non-legacy) application.
    with patch("app.pipeline.run_weekly.discover_documents") as mock_discover:
        stage_documents(session, page=MagicMock(), council=_council_config("testcouncil"))
    mock_discover.assert_not_called()


# --- F: regression / scope guards --------------------------------------------


def test_daily_discovery_still_never_imports_openai():
    from pathlib import Path as _Path

    repo_root = _Path(__file__).resolve().parents[1]
    source = (repo_root / "scripts" / "run_daily_councils.py").read_text(encoding="utf-8")
    assert "import openai" not in source.lower()
    assert "from openai" not in source.lower()


def test_evidence_module_does_not_import_openai():
    source = Path(__file__).resolve().parents[1].joinpath("app", "pipeline", "evidence.py").read_text(encoding="utf-8")
    assert "openai" not in source.lower()


def test_min_useful_documents_and_core_categories_match_approved_rule():
    """Source-level regression guard against silently drifting from the
    approved Product Owner rule (>=3 useful OR >=2 of 3 core categories)."""
    assert MIN_USEFUL_DOCUMENTS == 3
    assert MIN_CORE_CATEGORIES == 2
    assert CORE_DOCUMENT_TYPES == frozenset({"planning_statement", "decision_notice", "officer_report"})
