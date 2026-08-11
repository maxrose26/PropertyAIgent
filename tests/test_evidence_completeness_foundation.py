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
    for one specific Application WITHOUT relying on ~Application.
    documents.any() to somehow re-select it - which it structurally
    cannot, once DOCUMENT_DISCOVERY_ELIGIBLE has excluded it for having a
    document at all)."""
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


def test_legacy_row_with_existing_documents_is_not_requeued_for_discovery(session):
    """The central rollout-safety property (Section 9): a legacy
    Application that already has stored Document rows (from before PR A
    existed) but a NULL documents_last_checked_at (since the field is new)
    must NOT be treated as eligible for document discovery - reproducing
    today's ~Application.documents.any() behaviour for existing data, not
    an uncontrolled full-corpus re-scrape."""
    application = _add_application(session, reference="APP/LEGACY/1")
    _add_document(session, application, "planning_statement", source_url="https://example.invalid/1.pdf")
    assert application.documents_last_checked_at is None  # never backfilled

    with patch("app.pipeline.run_weekly.discover_documents") as mock_discover:
        stage_documents(session, page=MagicMock(), council=_council_config("testcouncil"))
    mock_discover.assert_not_called()


def test_legacy_row_with_zero_documents_remains_eligible(session):
    """A legacy application that genuinely has zero stored documents
    (documents_last_checked_at also NULL) is exactly today's eligibility
    set - it should remain eligible, unchanged."""
    _add_application(session, reference="APP/LEGACY/2")
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[]) as mock_discover:
        stage_documents(session, page=MagicMock(), council=_council_config("testcouncil"))
    mock_discover.assert_called_once()


def test_first_run_after_migration_does_not_document_scrape_whole_corpus(session):
    """Simulates the production rollout moment: a mix of legacy
    applications (some with documents, some without) all having
    documents_last_checked_at NULL. Only the genuinely-undocumented ones
    must be selected."""
    already_documented = []
    for i in range(5):
        app = _add_application(session, reference=f"APP/DOCUMENTED/{i}")
        _add_document(session, app, "application_form", source_url=f"https://example.invalid/{i}.pdf")
        already_documented.append(app)
    never_documented = [_add_application(session, reference=f"APP/NEW/{i}") for i in range(3)]

    with patch("app.pipeline.run_weekly.discover_documents", return_value=[]) as mock_discover:
        stage_documents(session, page=MagicMock(), council=_council_config("testcouncil"))

    assert mock_discover.call_count == 3  # only the 3 never-documented ones
    called_refs = {c.args[3] for c in mock_discover.call_args_list}  # summary_url positional arg
    for app in never_documented:
        assert app.summary_url in called_refs
    for app in already_documented:
        assert app.summary_url not in called_refs


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
