"""AI Processing Reliability & Backlog Throughput - focused tests for:

1. Deterministic extraction outcome classification (SUCCESS/NO_USABLE_TEXT/
   AI_ERROR/INVALID_OUTPUT/ERROR) instead of the previous conflated
   dict-or-None/bare-except behaviour.
2. NO_USABLE_TEXT applications stop consuming the daily extraction quota
   forever, without being permanently blacklisted (reactivatable).
3. Genuine AI/API failures remain retryable after a bounded cooldown, and
   never starve the rest of the backlog.
4. The bounded candidate-scan mechanism (Part 5) - "up to N genuine
   attempts, inspecting at most a bounded multiple of N candidates".
5. Deterministic extraction/summary ordering (Part 6).
6. Truthful IntelligenceRun SUCCESS/PARTIAL/FAILED status (Part 7) and its
   new counters (Part 8).
7. Failure isolation (Part 9) and unchanged cost controls (Part 10).

Uses the same in-memory-SQLite `session` fixture as every other test in
this suite (tests/conftest.py).
"""
from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import pytest
from openai import OpenAIError

from app.config import CouncilConfig
from app.db.models import Application, Document, IntelligenceRun, SchemeIntelligence, Site
from app.extraction.run_extraction import (
    OUTCOME_AI_ERROR,
    OUTCOME_ERROR,
    OUTCOME_INVALID_OUTPUT,
    OUTCOME_NO_USABLE_TEXT,
    OUTCOME_SUCCESS,
    has_usable_document_text,
)
from app.pipeline import run_weekly as run_weekly_module
from app.pipeline.run_weekly import (
    EXTRACTION_CANDIDATE_SCAN_MULTIPLIER,
    EXTRACTION_RETRY_COOLDOWN_HOURS,
    count_pending_extraction,
    stage_extraction,
    stage_generate_scheme_summaries,
)


def _council_config(code: str) -> CouncilConfig:
    return CouncilConfig(
        code=code, name=code, base_url="https://example.invalid",
        date_field_mode="received", doc_system="idox", anite_base_url=None,
        unit_threshold=10, region=None, country=None,
    )


def _app_with_document(session, *, reference: str, council_code: str = "testcouncil", first_seen_at=None) -> Application:
    application = Application(council_code=council_code, reference=reference)
    if first_seen_at is not None:
        application.first_seen_at = first_seen_at
    session.add(application)
    session.commit()
    session.add(Document(
        application_id=application.id, doc_type="planning_statement",
        text_extracted=True, extracted_text="Some planning statement text.",
    ))
    session.commit()
    return application


def _app_without_document(session, *, reference: str, council_code: str = "testcouncil") -> Application:
    application = Application(council_code=council_code, reference=reference)
    session.add(application)
    session.commit()
    return application


COUNCILS = {"testcouncil": _council_config("testcouncil")}


# --- 1/2/3/4/5: outcome classification ---------------------------------------


def test_has_usable_document_text_true_when_text_extracted(session):
    app = _app_with_document(session, reference="APP/1")
    assert has_usable_document_text(app) is True


def test_has_usable_document_text_false_with_no_documents(session):
    app = _app_without_document(session, reference="APP/1")
    assert has_usable_document_text(app) is False


def test_extraction_success_classification(session):
    app = _app_with_document(session, reference="APP/1")
    with patch.object(run_weekly_module, "run_extraction_for_application", return_value={"total_units_final": 12}):
        result = stage_extraction(session, object(), COUNCILS["testcouncil"])
    assert result.succeeded == 1
    assert result.attempted == 1
    assert result.no_usable_text == 0
    assert result.failed == 0
    si = session.query(SchemeIntelligence).filter_by(application_id=app.id).one()
    assert si.total_units_final == 12
    assert app.extraction_last_outcome is None  # cleared on success


def test_no_usable_text_classification_never_calls_run_extraction(session):
    _app_without_document(session, reference="APP/1")
    with patch.object(run_weekly_module, "run_extraction_for_application") as mock_extract:
        result = stage_extraction(session, object(), COUNCILS["testcouncil"])
    mock_extract.assert_not_called()  # free classification, no LLM call, not billed
    assert result.no_usable_text == 1
    assert result.attempted == 0
    assert result.candidates_inspected == 1


def test_no_usable_text_classification_when_extraction_finds_nothing_extractable(session):
    """has_usable_document_text() can be True (a Document row exists with
    text_extracted=True) while run_extraction_for_application still
    returns None internally (e.g. every document's cleaned text ends up
    empty) - this must still classify as NO_USABLE_TEXT, not SUCCESS/
    failure, and must not count against the genuine-attempt budget."""
    _app_with_document(session, reference="APP/1")
    with patch.object(run_weekly_module, "run_extraction_for_application", return_value=None):
        result = stage_extraction(session, object(), COUNCILS["testcouncil"])
    assert result.no_usable_text == 1
    assert result.attempted == 0
    assert result.succeeded == 0
    assert result.failed == 0


def test_ai_api_failure_classification(session):
    app = _app_with_document(session, reference="APP/1")
    with patch.object(run_weekly_module, "run_extraction_for_application", side_effect=OpenAIError("rate limited")):
        result = stage_extraction(session, object(), COUNCILS["testcouncil"])
    assert result.failed == 1
    assert result.attempted == 1
    assert app.extraction_last_outcome == OUTCOME_AI_ERROR


def test_malformed_output_classification(session):
    app = _app_with_document(session, reference="APP/1")

    def _raise_json_error(client, application):
        import json
        json.loads("{not valid json")

    with patch.object(run_weekly_module, "run_extraction_for_application", side_effect=_raise_json_error):
        result = stage_extraction(session, object(), COUNCILS["testcouncil"])
    assert result.failed == 1
    assert app.extraction_last_outcome == OUTCOME_INVALID_OUTPUT


def test_unexpected_error_classification(session):
    app = _app_with_document(session, reference="APP/1")
    with patch.object(run_weekly_module, "run_extraction_for_application", side_effect=AttributeError("bug")):
        result = stage_extraction(session, object(), COUNCILS["testcouncil"])
    assert result.failed == 1
    assert app.extraction_last_outcome == OUTCOME_ERROR


# --- 6/7: no-usable-text does not loop forever, but is reactivatable --------


def test_no_usable_text_item_excluded_from_backlog_next_run(session):
    _app_without_document(session, reference="APP/1")
    with patch.object(run_weekly_module, "run_extraction_for_application"):
        stage_extraction(session, object(), COUNCILS["testcouncil"])

    assert count_pending_extraction(session, "testcouncil") == 0
    with patch.object(run_weekly_module, "run_extraction_for_application") as mock_extract:
        result = stage_extraction(session, object(), COUNCILS["testcouncil"])
    assert result.candidates_inspected == 0
    mock_extract.assert_not_called()


def test_no_usable_text_item_is_not_a_permanent_blacklist(session):
    """Nothing in this task implements automatic reactivation (that's the
    next task, evidence fingerprinting) - but the state must not be a dead
    end. Clearing extraction_last_outcome (standing in for "a document
    actually changed" / "a manual refresh" / "the next architecture
    reactivates it") must immediately re-open eligibility."""
    app = _app_without_document(session, reference="APP/1")
    with patch.object(run_weekly_module, "run_extraction_for_application"):
        stage_extraction(session, object(), COUNCILS["testcouncil"])
    assert count_pending_extraction(session, "testcouncil") == 0

    app.extraction_last_outcome = None
    session.commit()
    assert count_pending_extraction(session, "testcouncil") == 1


# --- 8/9: retry/cooldown for genuine failures --------------------------------


def test_failed_ai_item_remains_retryable_after_cooldown(session):
    app = _app_with_document(session, reference="APP/1")
    with patch.object(run_weekly_module, "run_extraction_for_application", side_effect=OpenAIError("boom")):
        stage_extraction(session, object(), COUNCILS["testcouncil"])
    assert app.extraction_last_outcome == OUTCOME_AI_ERROR

    # Still within cooldown - not yet retryable.
    assert count_pending_extraction(session, "testcouncil") == 0

    # Simulate the cooldown having elapsed.
    app.extraction_last_attempted_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
        hours=EXTRACTION_RETRY_COOLDOWN_HOURS + 1
    )
    session.commit()
    assert count_pending_extraction(session, "testcouncil") == 1


def test_failed_ai_item_not_retried_within_cooldown_window(session):
    app = _app_with_document(session, reference="APP/1")
    with patch.object(run_weekly_module, "run_extraction_for_application", side_effect=OpenAIError("boom")):
        result1 = stage_extraction(session, object(), COUNCILS["testcouncil"])
    assert result1.failed == 1

    with patch.object(run_weekly_module, "run_extraction_for_application") as mock_extract:
        result2 = stage_extraction(session, object(), COUNCILS["testcouncil"])
    mock_extract.assert_not_called()  # still inside cooldown
    assert result2.candidates_inspected == 0


# --- 10: bounded candidate scan ----------------------------------------------


def test_candidate_scan_remains_bounded(session):
    """20 applications, every one permanently no-usable-text. A limit of 3
    must not scan all 20 - only up to limit * EXTRACTION_CANDIDATE_SCAN_MULTIPLIER."""
    for i in range(20):
        _app_without_document(session, reference=f"APP/{i}")

    result = stage_extraction(session, object(), COUNCILS["testcouncil"], limit=3)
    assert result.no_usable_text <= 3 * EXTRACTION_CANDIDATE_SCAN_MULTIPLIER
    assert result.candidates_inspected <= 3 * EXTRACTION_CANDIDATE_SCAN_MULTIPLIER
    assert result.candidates_inspected < 20  # bounded - never a full scan
    assert result.attempted == 0  # none of them were genuinely processable


def test_candidate_scan_stops_once_target_genuine_attempts_reached(session):
    for i in range(10):
        _app_with_document(session, reference=f"APP/{i}")

    with patch.object(run_weekly_module, "run_extraction_for_application", return_value={"total_units_final": 1}):
        result = stage_extraction(session, object(), COUNCILS["testcouncil"], limit=3)
    assert result.attempted == 3
    assert result.succeeded == 3
    assert result.candidates_inspected == 3  # every candidate here was genuinely processable


# --- 11/12: deterministic ordering -------------------------------------------


def test_extraction_ordering_is_newest_first(session):
    old = _app_with_document(session, reference="APP/OLD", first_seen_at=dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc))
    new = _app_with_document(session, reference="APP/NEW", first_seen_at=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc))

    seen_order = []

    def _record(client, application):
        seen_order.append(application.reference)
        return {"total_units_final": 1}

    with patch.object(run_weekly_module, "run_extraction_for_application", side_effect=_record):
        stage_extraction(session, object(), COUNCILS["testcouncil"])

    assert seen_order == ["APP/NEW", "APP/OLD"]


def test_extraction_ordering_tie_break_by_id_descending(session):
    same_time = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    first = _app_with_document(session, reference="APP/A", first_seen_at=same_time)
    second = _app_with_document(session, reference="APP/B", first_seen_at=same_time)
    assert second.id > first.id

    seen_order = []

    def _record(client, application):
        seen_order.append(application.reference)
        return {"total_units_final": 1}

    with patch.object(run_weekly_module, "run_extraction_for_application", side_effect=_record):
        stage_extraction(session, object(), COUNCILS["testcouncil"])

    assert seen_order == ["APP/B", "APP/A"]  # higher id (more recently inserted) first


def test_summary_ordering_is_most_recently_changed_first(session):
    site_old = Site(council_code="testcouncil", canonical_address="1 Old St", display_address="1 Old St")
    site_new = Site(council_code="testcouncil", canonical_address="2 New St", display_address="2 New St")
    session.add_all([site_old, site_new])
    session.commit()

    old_time = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
    new_time = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    session.add(Application(council_code="testcouncil", reference="A1", site_id=site_old.id, last_seen_at=old_time))
    session.add(Application(council_code="testcouncil", reference="A2", site_id=site_new.id, last_seen_at=new_time))
    session.commit()

    seen_order = []

    def _record(client, site, apps, merged, lapse, phase_breakdown):
        seen_order.append(site.id)
        return "summary text"

    with patch.object(run_weekly_module, "generate_scheme_summary", side_effect=_record):
        stage_generate_scheme_summaries(session, object(), COUNCILS["testcouncil"])

    assert seen_order == [site_new.id, site_old.id]


# --- 13/14/15/16: truthful IntelligenceRun status + counters ----------------


def test_intelligence_run_success_status_with_zero_failures(session):
    _app_with_document(session, reference="APP/1")
    from scripts.run_intelligence_processing import process_intelligence_backlog

    with patch.object(run_weekly_module, "run_extraction_for_application", return_value={"total_units_final": 1}):
        run = process_intelligence_backlog(
            session, COUNCILS, ["testcouncil"], max_extractions=10, max_summaries=0,
            client_factory=lambda api_key: object(),
        )
    assert run.status == "success"


def test_intelligence_run_partial_status_on_extraction_failure(session):
    _app_with_document(session, reference="APP/FAIL")
    from scripts.run_intelligence_processing import process_intelligence_backlog

    with patch.object(run_weekly_module, "run_extraction_for_application", side_effect=OpenAIError("boom")):
        run = process_intelligence_backlog(
            session, COUNCILS, ["testcouncil"], max_extractions=10, max_summaries=0,
            client_factory=lambda api_key: object(),
        )
    assert run.status == "partial"
    assert run.extractions_failed == 1


def test_intelligence_run_partial_status_on_summary_failure(session):
    site = Site(council_code="testcouncil", canonical_address="1 St", display_address="1 St")
    session.add(site)
    session.commit()
    session.add(Application(council_code="testcouncil", reference="A1", site_id=site.id))
    session.commit()

    from scripts.run_intelligence_processing import process_intelligence_backlog

    with patch.object(run_weekly_module, "generate_scheme_summary", side_effect=RuntimeError("boom")):
        run = process_intelligence_backlog(
            session, COUNCILS, ["testcouncil"], max_extractions=0, max_summaries=10,
            client_factory=lambda api_key: object(),
        )
    assert run.status == "partial"
    assert run.summaries_failed == 1


def test_intelligence_run_failed_status_reserved_for_top_level_failure(session, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _app_with_document(session, reference="APP/1")

    from scripts.run_intelligence_processing import process_intelligence_backlog

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        process_intelligence_backlog(session, COUNCILS, ["testcouncil"], max_extractions=10, max_summaries=10)

    run = session.query(IntelligenceRun).one()
    assert run.status == "failed"


def test_intelligence_run_no_usable_text_never_counts_as_failure(session):
    """A run made entirely of no-usable-text items must still be reported
    SUCCESS, per this task's own explicit policy."""
    _app_without_document(session, reference="APP/1")
    from scripts.run_intelligence_processing import process_intelligence_backlog

    with patch.object(run_weekly_module, "run_extraction_for_application") as mock_extract:
        run = process_intelligence_backlog(
            session, COUNCILS, ["testcouncil"], max_extractions=10, max_summaries=0,
            client_factory=lambda api_key: object(),
        )
    mock_extract.assert_not_called()
    assert run.status == "success"
    assert run.extractions_no_usable_text == 1
    assert run.extractions_failed == 0


def test_intelligence_run_counters_are_accurate(session):
    _app_with_document(session, reference="APP/OK")
    _app_with_document(session, reference="APP/FAIL")
    _app_without_document(session, reference="APP/NOTEXT")

    def _fake_extraction(client, application):
        if application.reference == "APP/FAIL":
            raise OpenAIError("boom")
        return {"total_units_final": 1}

    from scripts.run_intelligence_processing import process_intelligence_backlog

    with patch.object(run_weekly_module, "run_extraction_for_application", side_effect=_fake_extraction):
        run = process_intelligence_backlog(
            session, COUNCILS, ["testcouncil"], max_extractions=10, max_summaries=0,
            client_factory=lambda api_key: object(),
        )
    assert run.extractions_candidates_inspected == 3
    assert run.extractions_attempted == 2  # APP/OK + APP/FAIL - not APP/NOTEXT
    assert run.extractions_succeeded == 1
    assert run.extractions_no_usable_text == 1
    assert run.extractions_failed == 1
    assert run.status == "partial"


# --- 17/18: failure isolation ------------------------------------------------


def test_one_extraction_failure_does_not_stop_later_extractions(session):
    apps = [_app_with_document(session, reference=f"APP/{i}") for i in range(3)]

    def _fake_extraction(client, application):
        if application.reference == "APP/1":
            raise OpenAIError("boom")
        return {"total_units_final": 1}

    with patch.object(run_weekly_module, "run_extraction_for_application", side_effect=_fake_extraction):
        result = stage_extraction(session, object(), COUNCILS["testcouncil"])
    assert result.succeeded == 2
    assert result.failed == 1


def test_one_summary_failure_does_not_stop_later_summaries(session):
    sites = []
    for i in range(3):
        site = Site(council_code="testcouncil", canonical_address=f"{i} St", display_address=f"{i} St")
        session.add(site)
        session.commit()
        session.add(Application(council_code="testcouncil", reference=f"A{i}", site_id=site.id))
        session.commit()
        sites.append(site)

    def _fake_summary(client, site, apps, merged, lapse, phase_breakdown):
        if site.id == sites[1].id:
            raise RuntimeError("boom")
        return "summary text"

    with patch.object(run_weekly_module, "generate_scheme_summary", side_effect=_fake_summary):
        generated = stage_generate_scheme_summaries(session, object(), COUNCILS["testcouncil"])
    assert generated == 2


# --- 19/20/21: cost controls + Daily Discovery AI-free -----------------------


def test_zero_backlog_after_no_usable_text_exclusion_means_zero_openai_calls(session):
    """Once an application has been classified NO_USABLE_TEXT (its one
    unavoidable first attempt, which itself never calls OpenAI - see
    test_no_usable_text_classification_never_calls_run_extraction_at_all),
    a LATER run with nothing else outstanding must make zero OpenAI calls -
    the new eligibility rule must not keep re-admitting a classified item
    into what counts as backlog."""
    _app_without_document(session, reference="APP/1")
    with patch.object(run_weekly_module, "run_extraction_for_application"):
        stage_extraction(session, object(), COUNCILS["testcouncil"])
    assert count_pending_extraction(session, "testcouncil") == 0

    from scripts.run_intelligence_processing import process_intelligence_backlog

    def _boom(api_key):
        raise AssertionError("must not create an OpenAI client when there is no genuinely processable work left")

    run = process_intelligence_backlog(
        session, COUNCILS, ["testcouncil"], max_extractions=10, max_summaries=10, client_factory=_boom,
    )
    assert run.status == "success"
    assert run.extractions_attempted == 0


def test_run_daily_councils_still_never_imports_openai():
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "scripts" / "run_daily_councils.py").read_text(encoding="utf-8")
    assert "import openai" not in source.lower()
    assert "from openai" not in source.lower()


# --- 24: live-app propagation path not regressed -----------------------------


def test_successful_extraction_is_immediately_queryable_same_session(session):
    """Direct DB write -> direct DB read, no intermediate materialisation
    step - confirms this task didn't introduce one."""
    app = _app_with_document(session, reference="APP/1")
    with patch.object(run_weekly_module, "run_extraction_for_application", return_value={"total_units_final": 7}):
        stage_extraction(session, object(), COUNCILS["testcouncil"])

    si = session.query(SchemeIntelligence).filter_by(application_id=app.id).one_or_none()
    assert si is not None
    assert si.total_units_final == 7
