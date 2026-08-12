"""PR B2: Targeted Evidence Refresh - focused tests for:

1. app.pipeline.evidence_refresh.target_doc_types_for_reasons - the B1
   reason -> target evidence category routing map, including deterministic
   union of multiple reasons.
2. Scope: only evidence_refresh_required Applications are ever selected,
   and resolve_application_family() stays bounded to already-persisted
   parent/child relationships, never "every Application on the Site".
3. Existing-vs-new evidence: already-known documents are skipped, new
   relevant documents are acquired, new IRRELEVANT documents (outside the
   target category set) never trigger a material-evidence signal, and no
   duplicate Document rows are ever created.
4. The four-value outcome taxonomy (NEW_MATERIAL_EVIDENCE /
   CHECKED_NO_NEW_EVIDENCE / PORTAL_UNAVAILABLE / ACQUISITION_INCOMPLETE)
   and the flag-clearing rule each outcome drives.
5. The B3 handoff signal (material_evidence_changed_at).
6. Per-run bounds/prioritisation (select_refresh_candidates).
7. Circuit-breaker participation and AcquisitionHealth PARTIAL semantics.

Uses the same in-memory-SQLite `session` fixture as the rest of this suite
(tests/conftest.py) - "testcouncil"/"othercouncil" already present. No live
council portals - app.pipeline.run_weekly.discover_documents/
download_document/extract_document_text are always patched.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config import CouncilConfig
from app.db.models import Application, Document, Site
from app.pipeline.acquisition_health import AcquisitionHealth
from app.pipeline.evidence_refresh import (
    CLEARING_OUTCOMES,
    EVIDENCE_REFRESH_RUN_LIMIT,
    OUTCOME_ACQUISITION_INCOMPLETE,
    OUTCOME_CHECKED_NO_NEW_EVIDENCE,
    OUTCOME_NEW_MATERIAL_EVIDENCE,
    OUTCOME_PORTAL_UNAVAILABLE,
    ROUTING,
    resolve_application_family,
    refresh_material_evidence,
    select_refresh_candidates,
    target_doc_types_for_reasons,
)
from app.pipeline.material_change import (
    REASON_DECISION_GRANTED,
    REASON_DECISION_OUTCOME_UNKNOWN,
    REASON_DECISION_REFUSED,
    REASON_DECISION_WITHDRAWN,
    REASON_RECOMMENDATION_MADE,
    REASON_UNIT_COUNT_CHANGED,
)
from app.pipeline.portal_circuit_breaker import CouncilPortalCircuitBreaker
from app.pipeline.run_weekly import stage_evidence_refresh


def _council_config(code: str = "testcouncil") -> CouncilConfig:
    return CouncilConfig(
        code=code, name=code, base_url="https://example.invalid",
        date_field_mode="received", doc_system="idox", anite_base_url=None,
        unit_threshold=10, region=None, country=None,
    )


def _add_application(session, *, reference: str, council_code: str = "testcouncil", **kwargs) -> Application:
    application = Application(
        council_code=council_code, reference=reference,
        summary_url=kwargs.pop("summary_url", f"https://example.invalid/{reference}"),
        evidence_refresh_required=kwargs.pop("evidence_refresh_required", True),
        evidence_refresh_reason=kwargs.pop("evidence_refresh_reason", REASON_DECISION_GRANTED),
        evidence_refresh_trigger=kwargs.pop("evidence_refresh_trigger", "material_change"),
        **kwargs,
    )
    session.add(application)
    session.commit()
    return application


def _fake_row(name: str, doc_type_raw: str = "", source_url: str | None = None):
    return MagicMock(document_name=name, doc_type_raw=doc_type_raw, source_url=source_url, local_path=None, referer=None)


def _add_document(session, application: Application, doc_type: str, *, source_url: str | None = None, document_name: str | None = None) -> Document:
    document = Document(
        application_id=application.id, doc_type=doc_type,
        document_name=document_name or f"{doc_type}.pdf", source_url=source_url,
        text_extracted=True, extracted_text="text", downloaded_at=dt.datetime.now(dt.timezone.utc),
    )
    session.add(document)
    session.commit()
    return document


# --- 1-7: Routing --------------------------------------------------------------


def test_recommendation_made_routes_to_officer_report():
    assert target_doc_types_for_reasons([REASON_RECOMMENDATION_MADE]) == frozenset({"officer_report"})


def test_decision_granted_includes_decision_officer_and_s106():
    assert target_doc_types_for_reasons([REASON_DECISION_GRANTED]) == frozenset(
        {"decision_notice", "officer_report", "s106"}
    )


def test_decision_refused_uses_focused_refusal_evidence():
    targets = target_doc_types_for_reasons([REASON_DECISION_REFUSED])
    assert targets == frozenset({"decision_notice", "officer_report"})
    assert "s106" not in targets  # deliberately narrower than decision_granted


def test_decision_withdrawn_remains_focused():
    assert target_doc_types_for_reasons([REASON_DECISION_WITHDRAWN]) == frozenset({"decision_notice", "officer_report"})


def test_decision_outcome_unknown_targets_decision_resolution_evidence():
    assert target_doc_types_for_reasons([REASON_DECISION_OUTCOME_UNKNOWN]) == frozenset({"decision_notice", "officer_report"})


def test_unit_count_changed_routes_to_appropriate_revised_scheme_evidence():
    assert target_doc_types_for_reasons([REASON_UNIT_COUNT_CHANGED]) == frozenset({"planning_statement", "design_access"})


def test_multiple_reasons_union_deterministically():
    targets = target_doc_types_for_reasons([REASON_DECISION_GRANTED, REASON_UNIT_COUNT_CHANGED])
    assert targets == frozenset({"decision_notice", "officer_report", "s106", "planning_statement", "design_access"})
    # Order-independence - the union must not depend on which reason came first.
    assert target_doc_types_for_reasons([REASON_UNIT_COUNT_CHANGED, REASON_DECISION_GRANTED]) == targets


def test_every_named_reason_has_a_routing_entry():
    for reason in (
        REASON_RECOMMENDATION_MADE, REASON_DECISION_OUTCOME_UNKNOWN, REASON_DECISION_GRANTED,
        REASON_DECISION_REFUSED, REASON_DECISION_WITHDRAWN, REASON_UNIT_COUNT_CHANGED,
    ):
        assert reason in ROUTING


# --- 8-12: Scope -----------------------------------------------------------


def test_only_evidence_refresh_required_applications_eligible(session):
    flagged = _add_application(session, reference="APP/FLAGGED")
    session.execute  # no-op, keeps import used
    candidates = select_refresh_candidates(session, "testcouncil")
    assert [c.id for c in candidates] == [flagged.id]


def test_unflagged_applications_excluded(session):
    _add_application(session, reference="APP/FLAGGED")
    _add_application(session, reference="APP/UNFLAGGED", evidence_refresh_required=False, evidence_refresh_reason=None, evidence_refresh_trigger=None)
    candidates = select_refresh_candidates(session, "testcouncil")
    assert [c.reference for c in candidates] == ["APP/FLAGGED"]


def test_legacy_documented_applications_are_not_mass_requeued(session):
    # A legacy application that was never touched by B1 has evidence_refresh_
    # required=False (its own model default / migration backfill) - it must
    # never appear in the candidate set just because it has documents.
    legacy = _add_application(
        session, reference="APP/LEGACY", evidence_refresh_required=False,
        evidence_refresh_reason=None, evidence_refresh_trigger=None,
    )
    _add_document(session, legacy, "planning_statement")
    candidates = select_refresh_candidates(session, "testcouncil")
    assert candidates == []


def test_bounded_family_targeting_only(session):
    trigger = _add_application(session, reference="APP/CHILD", proposal="Reserved matters pursuant to planning permission APP/PARENT/1")
    parent = _add_application(session, reference="APP/PARENT/1", evidence_refresh_required=False, evidence_refresh_reason=None, evidence_refresh_trigger=None)
    family = resolve_application_family(session, trigger)
    assert {a.id for a in family} == {trigger.id, parent.id}


def test_application_family_does_not_expand_uncontrolled(session):
    """A real production site was found with up to 30 Applications sharing
    one site_id (see this PR's own read-only production analysis) - the
    family for one trigger must stay narrow (trigger + its own explicit
    parent/child citations only), never every Application on that Site."""
    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()

    trigger = _add_application(session, reference="APP/TRIGGER", site_id=site.id)
    # A genuine child - explicitly cites the trigger as its parent.
    child = _add_application(
        session, reference="APP/CHILD", site_id=site.id,
        proposal="Reserved matters pursuant to planning permission APP/TRIGGER",
        evidence_refresh_required=False, evidence_refresh_reason=None, evidence_refresh_trigger=None,
    )
    # Several unrelated Applications that merely share the same site_id
    # (e.g. address-matched, no textual citation relationship) - must be
    # excluded from the family.
    for i in range(5):
        _add_application(
            session, reference=f"APP/UNRELATED/{i}", site_id=site.id,
            evidence_refresh_required=False, evidence_refresh_reason=None, evidence_refresh_trigger=None,
        )

    family = resolve_application_family(session, trigger)
    assert {a.id for a in family} == {trigger.id, child.id}


# --- 13-16: Existing vs new evidence -----------------------------------------


def test_already_known_relevant_document_skipped(session):
    application = _add_application(session, reference="APP/1")
    _add_document(session, application, "decision_notice", source_url="https://example.invalid/decision.pdf")
    known_row = _fake_row("Decision Notice.pdf", source_url="https://example.invalid/decision.pdf")

    with patch("app.pipeline.run_weekly.discover_documents", return_value=[known_row]), \
         patch("app.pipeline.run_weekly.standardise_document_type", return_value="decision_notice"):
        result = refresh_material_evidence(
            session, MagicMock(), MagicMock(), _council_config(), application,
            trigger="material_change", reason=REASON_DECISION_GRANTED,
        )

    assert result.outcome == OUTCOME_CHECKED_NO_NEW_EVIDENCE
    assert session.query(Document).filter_by(application_id=application.id).count() == 1  # not duplicated


def test_new_relevant_document_acquired(session):
    application = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_REFUSED)
    new_row = _fake_row("Decision Notice.pdf", source_url="https://example.invalid/decision.pdf")

    with patch("app.pipeline.run_weekly.discover_documents", return_value=[new_row]), \
         patch("app.pipeline.run_weekly.download_document", return_value=Path("/tmp/fake.pdf")), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", return_value="decision_notice"), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        result = refresh_material_evidence(
            session, MagicMock(), MagicMock(), _council_config(), application,
            trigger="material_change", reason=REASON_DECISION_REFUSED,
        )

    assert result.outcome == OUTCOME_NEW_MATERIAL_EVIDENCE
    assert result.new_document_count == 1
    assert session.query(Document).filter_by(application_id=application.id, doc_type="decision_notice").count() == 1


def test_new_irrelevant_document_does_not_cause_material_evidence_signal(session):
    # decision_refused only targets decision_notice/officer_report - a
    # newly-discovered design_access drawing must not itself be persisted
    # or counted as material for this refresh, since it's outside the
    # target category set entirely (Part 8's filter/parameter extension).
    application = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_REFUSED)
    irrelevant_row = _fake_row("Design and Access Statement.pdf", source_url="https://example.invalid/da.pdf")

    with patch("app.pipeline.run_weekly.discover_documents", return_value=[irrelevant_row]), \
         patch("app.pipeline.run_weekly.standardise_document_type", return_value="design_access"):
        result = refresh_material_evidence(
            session, MagicMock(), MagicMock(), _council_config(), application,
            trigger="material_change", reason=REASON_DECISION_REFUSED,
        )

    assert result.outcome == OUTCOME_CHECKED_NO_NEW_EVIDENCE
    assert session.query(Document).filter_by(application_id=application.id).count() == 0  # never stored


def test_no_duplicate_document_rows_across_repeated_refresh(session):
    application = _add_application(session, reference="APP/1")
    row = _fake_row("Decision Notice.pdf", source_url="https://example.invalid/decision.pdf")

    for _ in range(2):
        application.evidence_refresh_required = True
        session.commit()
        with patch("app.pipeline.run_weekly.discover_documents", return_value=[row]), \
             patch("app.pipeline.run_weekly.download_document", return_value=Path("/tmp/fake.pdf")), \
             patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
             patch("app.pipeline.run_weekly.standardise_document_type", return_value="decision_notice"), \
             patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
            refresh_material_evidence(
                session, MagicMock(), MagicMock(), _council_config(), application,
                trigger="material_change", reason=REASON_DECISION_GRANTED,
            )

    assert session.query(Document).filter_by(application_id=application.id).count() == 1


# --- 17-20: Outcomes ---------------------------------------------------------


def test_successful_check_with_new_evidence_returns_new_material_evidence(session):
    application = _add_application(session, reference="APP/1")
    row = _fake_row("Decision Notice.pdf", source_url="https://example.invalid/d.pdf")
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[row]), \
         patch("app.pipeline.run_weekly.download_document", return_value=Path("/tmp/fake.pdf")), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", return_value="decision_notice"), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        result = refresh_material_evidence(
            session, MagicMock(), MagicMock(), _council_config(), application,
            trigger="material_change", reason=REASON_DECISION_GRANTED,
        )
    assert result.outcome == OUTCOME_NEW_MATERIAL_EVIDENCE


def test_successful_check_nothing_new_returns_checked_no_new_evidence(session):
    application = _add_application(session, reference="APP/1")
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[]):
        result = refresh_material_evidence(
            session, MagicMock(), MagicMock(), _council_config(), application,
            trigger="material_change", reason=REASON_DECISION_GRANTED,
        )
    assert result.outcome == OUTCOME_CHECKED_NO_NEW_EVIDENCE


def test_portal_failure_returns_portal_unavailable(session):
    application = _add_application(session, reference="APP/1")
    with patch("app.pipeline.run_weekly.discover_documents", side_effect=RuntimeError("portal unreachable")):
        result = refresh_material_evidence(
            session, MagicMock(), MagicMock(), _council_config(), application,
            trigger="material_change", reason=REASON_DECISION_GRANTED,
        )
    assert result.outcome == OUTCOME_PORTAL_UNAVAILABLE


def test_download_failure_returns_acquisition_incomplete(session):
    application = _add_application(session, reference="APP/1")
    row = _fake_row("Decision Notice.pdf", source_url="https://example.invalid/d.pdf")
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[row]), \
         patch("app.pipeline.run_weekly.download_document", side_effect=RuntimeError("download failed")), \
         patch("app.pipeline.run_weekly.standardise_document_type", return_value="decision_notice"):
        result = refresh_material_evidence(
            session, MagicMock(), MagicMock(), _council_config(), application,
            trigger="material_change", reason=REASON_DECISION_GRANTED,
        )
    assert result.outcome == OUTCOME_ACQUISITION_INCOMPLETE


# --- 21-25: Flag lifecycle ----------------------------------------------------


def test_new_material_evidence_clears_flag(session):
    application = _add_application(session, reference="APP/1")
    row = _fake_row("Decision Notice.pdf", source_url="https://example.invalid/d.pdf")
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[row]), \
         patch("app.pipeline.run_weekly.download_document", return_value=Path("/tmp/fake.pdf")), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", return_value="decision_notice"), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        refresh_material_evidence(
            session, MagicMock(), MagicMock(), _council_config(), application,
            trigger="material_change", reason=REASON_DECISION_GRANTED,
        )
    assert application.evidence_refresh_required is False
    # B1's own audit trail is preserved, not wiped.
    assert application.evidence_refresh_reason == REASON_DECISION_GRANTED


def test_checked_no_new_evidence_clears_flag(session):
    application = _add_application(session, reference="APP/1")
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[]):
        refresh_material_evidence(
            session, MagicMock(), MagicMock(), _council_config(), application,
            trigger="material_change", reason=REASON_DECISION_GRANTED,
        )
    assert application.evidence_refresh_required is False


def test_portal_unavailable_does_not_clear_flag(session):
    application = _add_application(session, reference="APP/1")
    with patch("app.pipeline.run_weekly.discover_documents", side_effect=RuntimeError("boom")):
        refresh_material_evidence(
            session, MagicMock(), MagicMock(), _council_config(), application,
            trigger="material_change", reason=REASON_DECISION_GRANTED,
        )
    assert application.evidence_refresh_required is True
    assert application.evidence_refresh_reason == REASON_DECISION_GRANTED  # unchanged, retryable


def test_acquisition_incomplete_does_not_clear_flag(session):
    application = _add_application(session, reference="APP/1")
    row = _fake_row("Decision Notice.pdf", source_url="https://example.invalid/d.pdf")
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[row]), \
         patch("app.pipeline.run_weekly.download_document", side_effect=RuntimeError("boom")), \
         patch("app.pipeline.run_weekly.standardise_document_type", return_value="decision_notice"):
        refresh_material_evidence(
            session, MagicMock(), MagicMock(), _council_config(), application,
            trigger="material_change", reason=REASON_DECISION_GRANTED,
        )
    assert application.evidence_refresh_required is True


def test_unexpected_failure_does_not_lose_the_request(session):
    # discover_and_store_documents_for_application's own broad except
    # catches genuinely any exception raised out of discover_documents,
    # not just network-shaped ones - from evidence_refresh's own
    # perspective that is indistinguishable from a portal failure, and
    # must be equally retryable.
    application = _add_application(session, reference="APP/1")
    with patch("app.pipeline.run_weekly.discover_documents", side_effect=ValueError("unexpected parsing error")):
        result = refresh_material_evidence(
            session, MagicMock(), MagicMock(), _council_config(), application,
            trigger="material_change", reason=REASON_DECISION_GRANTED,
        )
    assert result.outcome == OUTCOME_PORTAL_UNAVAILABLE
    assert application.evidence_refresh_required is True


# --- 26-28: B3 handoff ---------------------------------------------------------


def test_new_material_evidence_creates_b3_handoff(session):
    application = _add_application(session, reference="APP/1")
    row = _fake_row("Decision Notice.pdf", source_url="https://example.invalid/d.pdf")
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[row]), \
         patch("app.pipeline.run_weekly.download_document", return_value=Path("/tmp/fake.pdf")), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", return_value="decision_notice"), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        refresh_material_evidence(
            session, MagicMock(), MagicMock(), _council_config(), application,
            trigger="material_change", reason=REASON_DECISION_GRANTED,
        )
    assert application.material_evidence_changed_at is not None


def test_no_new_evidence_does_not_create_b3_handoff(session):
    application = _add_application(session, reference="APP/1")
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[]):
        refresh_material_evidence(
            session, MagicMock(), MagicMock(), _council_config(), application,
            trigger="material_change", reason=REASON_DECISION_GRANTED,
        )
    assert application.material_evidence_changed_at is None


def test_portal_failure_does_not_create_b3_handoff(session):
    application = _add_application(session, reference="APP/1")
    with patch("app.pipeline.run_weekly.discover_documents", side_effect=RuntimeError("boom")):
        refresh_material_evidence(
            session, MagicMock(), MagicMock(), _council_config(), application,
            trigger="material_change", reason=REASON_DECISION_GRANTED,
        )
    assert application.material_evidence_changed_at is None


# --- 29-30: Ordering / bounds ------------------------------------------------


def test_newest_refresh_request_processed_first(session):
    now = dt.datetime.now(dt.timezone.utc)
    older = _add_application(session, reference="APP/OLDER", evidence_refresh_requested_at=now - dt.timedelta(days=1))
    newer = _add_application(session, reference="APP/NEWER", evidence_refresh_requested_at=now)
    candidates = select_refresh_candidates(session, "testcouncil")
    assert [c.id for c in candidates] == [newer.id, older.id]


def test_configured_run_maximum_enforced(session):
    for i in range(EVIDENCE_REFRESH_RUN_LIMIT + 5):
        _add_application(session, reference=f"APP/{i}")
    candidates = select_refresh_candidates(session, "testcouncil")
    assert len(candidates) == EVIDENCE_REFRESH_RUN_LIMIT


# --- 31-33: Circuit breaker / health -----------------------------------------


def test_participates_in_existing_circuit_breaker(session):
    application = _add_application(session, reference="APP/1")
    breaker = CouncilPortalCircuitBreaker(council_code="testcouncil")
    breaker._open = True  # simulate an already-open circuit from an earlier stage
    with patch("app.pipeline.run_weekly.discover_documents") as mock_discover:
        result = refresh_material_evidence(
            session, MagicMock(), MagicMock(), _council_config(), application,
            trigger="material_change", reason=REASON_DECISION_GRANTED, breaker=breaker,
        )
    assert result.outcome == OUTCOME_PORTAL_UNAVAILABLE
    mock_discover.assert_not_called()  # no network call attempted once open
    assert application.evidence_refresh_required is True


def test_circuit_open_skips_remaining_council_refresh_work(session):
    _add_application(session, reference="APP/1")
    _add_application(session, reference="APP/2")
    breaker = CouncilPortalCircuitBreaker(council_code="testcouncil")
    breaker._open = True
    with patch("app.pipeline.run_weekly.discover_documents") as mock_discover:
        stage_evidence_refresh(session, MagicMock(), _council_config(), breaker=breaker)
    mock_discover.assert_not_called()  # stage_evidence_refresh's own loop breaks before attempting either


def test_portal_unavailable_refresh_causes_partial_where_primary_scrape_completed():
    health = AcquisitionHealth()
    health.record_primary_scrape_attempt()
    health.record_primary_scrape_completed()
    health.record_evidence_refresh(succeeded=False)
    assert health.classify() == "partial"  # never FAILED - the primary scrape itself succeeded


def test_evidence_refresh_success_does_not_force_partial():
    health = AcquisitionHealth()
    health.record_primary_scrape_attempt()
    health.record_primary_scrape_completed()
    health.record_evidence_refresh(succeeded=True)
    assert health.classify() == "success"


# --- AI-free confirmation ----------------------------------------------------


def test_evidence_refresh_module_never_imports_openai():
    import sys

    import app.pipeline.evidence_refresh as module
    source = Path(module.__file__).read_text()
    assert "import openai" not in source.lower()
    assert "openai" not in sys.modules.get(module.__name__).__dict__
    assert not hasattr(module, "SchemeIntelligence")  # never even imports the model it must not touch


# ==============================================================================
# PR B2 pre-merge amendment: Explicit Acquisition Completion Contract +
# Trigger-Agnostic S106 Refresh
# ==============================================================================

# --- 1-6: explicit acquisition contract --------------------------------------


def test_fully_successful_acquisition_returns_explicit_completed_state(session):
    from app.pipeline.run_weekly import discover_and_store_documents_for_application

    application = _add_application(session, reference="APP/1")
    row = _fake_row("Decision Notice.pdf", source_url="https://example.invalid/d.pdf")
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[row]), \
         patch("app.pipeline.run_weekly.download_document", return_value=Path("/tmp/fake.pdf")), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", return_value="decision_notice"), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        result = discover_and_store_documents_for_application(
            session, MagicMock(), MagicMock(), _council_config(), application,
        )
    assert result.listing_succeeded is True
    assert result.acquisition_complete is True
    assert result.new_document_count == 1
    assert application.documents_last_checked_at is not None  # PR A semantics unchanged (item 4)


def test_partial_acquisition_returns_explicit_incomplete_state(session):
    from app.pipeline.run_weekly import discover_and_store_documents_for_application

    application = _add_application(session, reference="APP/1")
    row_ok = _fake_row("Decision Notice.pdf", source_url="https://example.invalid/ok.pdf")
    row_fails = _fake_row("Officer Report.pdf", source_url="https://example.invalid/broken.pdf")
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[row_ok, row_fails]), \
         patch("app.pipeline.run_weekly.download_document", side_effect=[Path("/tmp/ok.pdf"), RuntimeError("boom")]), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", side_effect=["decision_notice", "officer_report"]), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        result = discover_and_store_documents_for_application(
            session, MagicMock(), MagicMock(), _council_config(), application,
        )
    assert result.listing_succeeded is True
    assert result.acquisition_complete is False
    assert result.new_document_count == 1  # the one that DID succeed, not lost (item 8)
    assert application.documents_last_checked_at is None  # PR A semantics unchanged (item 5)


def test_b2_no_longer_infers_completion_from_documents_last_checked_at():
    """Structural proof (item 3): the indirect timestamp-movement proxy this
    amendment removes must not reappear in app.pipeline.evidence_refresh -
    the module now reads DocumentAcquisitionResult.acquisition_complete
    explicitly instead."""
    import app.pipeline.evidence_refresh as module
    source = Path(module.__file__).read_text()
    assert "before_checked_at" not in source  # the removed proxy variable itself
    assert ".documents_last_checked_at ==" not in source  # the removed comparison
    assert "acquisition_result.acquisition_complete" in source  # the explicit replacement


def test_existing_stage_documents_caller_remains_compatible(session):
    """Item 6 - stage_documents (PR A's own bulk caller) still works with
    the new DocumentAcquisitionResult return type, unmodified in spirit."""
    from app.pipeline.run_weekly import stage_documents

    _add_application(session, reference="APP/1", evidence_refresh_required=False, evidence_refresh_reason=None, evidence_refresh_trigger=None)
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[]):
        processed = stage_documents(session, page=MagicMock(), council=_council_config())
    assert processed == 1


# --- 7-12: partial acquisition + B3 handoff (recovery flow) -----------------


def test_partial_acquisition_then_successful_recovery_full_flow(session):
    """One comprehensive scenario covering items 7-12: a targeted refresh
    where one relevant document succeeds and another fails must report
    ACQUISITION_INCOMPLETE, keep evidence_refresh_required True, persist the
    successful document, and NOT create the B3 handoff yet. A later retry
    that completes cleanly must then dedup the already-persisted document,
    acquire only the missing one, and finally produce NEW_MATERIAL_EVIDENCE
    with the B3 handoff."""
    application = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    row_ok = _fake_row("Decision Notice.pdf", source_url="https://example.invalid/ok.pdf")
    row_fails = _fake_row("Officer Report.pdf", source_url="https://example.invalid/broken.pdf")

    # Pass 1: partial failure.
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[row_ok, row_fails]), \
         patch("app.pipeline.run_weekly.download_document", side_effect=[Path("/tmp/ok.pdf"), RuntimeError("boom")]), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", side_effect=["decision_notice", "officer_report"]), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        result_1 = refresh_material_evidence(
            session, MagicMock(), MagicMock(), _council_config(), application,
            trigger="material_change", reason=REASON_DECISION_GRANTED,
        )

    assert result_1.outcome == OUTCOME_ACQUISITION_INCOMPLETE  # item 7
    docs = session.query(Document).filter_by(application_id=application.id).all()
    assert len(docs) == 1 and docs[0].doc_type == "decision_notice"  # item 8 - not lost
    assert application.evidence_refresh_required is True  # item 9
    assert application.material_evidence_changed_at is None  # item 10 - no B3 handoff yet

    # Pass 2: recovery - the portal is re-listed with BOTH rows again (as a
    # real re-listing would), the previously-successful one is now a
    # duplicate by identity, and only the previously-failing one is retried.
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[row_ok, row_fails]), \
         patch("app.pipeline.run_weekly.download_document", return_value=Path("/tmp/recovered.pdf")), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", side_effect=["decision_notice", "officer_report"]), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        result_2 = refresh_material_evidence(
            session, MagicMock(), MagicMock(), _council_config(), application,
            trigger="material_change", reason=REASON_DECISION_GRANTED,
        )

    assert result_2.outcome == OUTCOME_NEW_MATERIAL_EVIDENCE  # item 12
    assert result_2.new_document_count == 1  # item 11 - only the missing one, not re-downloaded
    docs_after = session.query(Document).filter_by(application_id=application.id).all()
    assert len(docs_after) == 2  # the recovered pass never duplicated the first document
    assert application.evidence_refresh_required is False
    assert application.material_evidence_changed_at is not None  # item 12 - B3 handoff now created


# --- 13-14: portal behaviour ---------------------------------------------------


def test_portal_unavailable_remains_distinct_from_acquisition_incomplete():
    assert OUTCOME_PORTAL_UNAVAILABLE != OUTCOME_ACQUISITION_INCOMPLETE
    assert OUTCOME_PORTAL_UNAVAILABLE not in CLEARING_OUTCOMES
    assert OUTCOME_ACQUISITION_INCOMPLETE not in CLEARING_OUTCOMES


# --- 15-19: generic S106, status-agnostic ------------------------------------


def test_awaiting_decision_application_with_explicit_s106_target_is_not_gated_by_status(session):
    application = _add_application(
        session, reference="APP/1", status="Awaiting decision", decision=None,
        evidence_refresh_reason=REASON_RECOMMENDATION_MADE,  # a reason that would NOT normally route to s106
    )
    row = _fake_row("S106 Agreement.pdf", source_url="https://example.invalid/s106.pdf")
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[row]), \
         patch("app.pipeline.run_weekly.download_document", return_value=Path("/tmp/fake.pdf")), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", return_value="s106"), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        result = refresh_material_evidence(
            session, MagicMock(), MagicMock(), _council_config(), application,
            trigger="manual_s106", reason=None, target_categories=frozenset({"s106"}),
        )
    assert result.outcome == OUTCOME_NEW_MATERIAL_EVIDENCE
    assert session.query(Document).filter_by(application_id=application.id, doc_type="s106").count() == 1


def test_granted_application_with_explicit_s106_target_works_identically(session):
    application = _add_application(
        session, reference="APP/1", status="Decided", decision="Approve with Conditions",
        evidence_refresh_reason=REASON_DECISION_GRANTED,
    )
    row = _fake_row("S106 Agreement.pdf", source_url="https://example.invalid/s106.pdf")
    with patch("app.pipeline.run_weekly.discover_documents", return_value=[row]), \
         patch("app.pipeline.run_weekly.download_document", return_value=Path("/tmp/fake.pdf")), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", return_value="s106"), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=1)):
        result = refresh_material_evidence(
            session, MagicMock(), MagicMock(), _council_config(), application,
            trigger="manual_s106", reason=None, target_categories=frozenset({"s106"}),
        )
    assert result.outcome == OUTCOME_NEW_MATERIAL_EVIDENCE


def test_generic_refresh_never_inspects_application_status_or_decision():
    """Item 17 - structural proof that neither the generic refresh service
    nor the acquisition function it calls ever branch on planning status."""
    import inspect

    import app.pipeline.evidence_refresh as evidence_refresh_module
    from app.pipeline.run_weekly import discover_and_store_documents_for_application

    for source in (
        Path(evidence_refresh_module.__file__).read_text(),
        inspect.getsource(discover_and_store_documents_for_application),
    ):
        assert "application.status" not in source
        assert "application.decision" not in source
        assert "target.status" not in source
        assert "target.decision" not in source


def test_decision_granted_routing_still_includes_s106_after_amendment():
    # Item 18 - the amendment must not have narrowed B1's own routing.
    assert "s106" in target_doc_types_for_reasons([REASON_DECISION_GRANTED])


def test_recommendation_made_does_not_automatically_include_s106():
    # Item 19 - the amendment must not have broadened B1's own routing either.
    assert "s106" not in target_doc_types_for_reasons([REASON_RECOMMENDATION_MADE])
