"""scripts/run_historical_rebuild_to_completion.py - the unattended overnight
orchestration wrapper around app.extraction.historical_rebuild.run_
historical_rebuild.

Covers: sequential bounded batching, already-rebuilt/evidence-blocked
exclusion, isolated-failure tolerance, systemic-failure stop conditions
(consecutive failures, batch failure rate, no forward progress), resume
after interruption, exit-code semantics, precheck, and no historical-marker
fabrication on failure.

Uses the same in-memory-SQLite `session` fixture as the rest of this suite
(tests/conftest.py). No real OpenAI call anywhere - every client is a
MagicMock. No production credentials required anywhere in this file.
"""
from __future__ import annotations

import datetime as dt
import json
from unittest.mock import MagicMock

from openai import OpenAIError

from app.db.models import Application, Document, SchemeIntelligence
import scripts.run_historical_rebuild_to_completion as orchestrator
from scripts.run_historical_rebuild_to_completion import (
    EXIT_STOPPED_SYSTEMIC,
    EXIT_SUCCESS,
    precheck,
    run_to_completion,
)


def _add_application(session, *, reference: str, council_code: str = "testcouncil", last_seen_at=None, **kwargs) -> Application:
    application = Application(
        council_code=council_code, reference=reference,
        summary_url=kwargs.pop("summary_url", f"https://example.invalid/{reference}"),
        last_seen_at=last_seen_at or dt.datetime.now(dt.timezone.utc),
        **kwargs,
    )
    session.add(application)
    session.commit()
    return application


def _add_scheme_intelligence(session, application: Application, **kwargs) -> SchemeIntelligence:
    intel = SchemeIntelligence(application_id=application.id, **kwargs)
    session.add(intel)
    session.commit()
    return intel


def _add_document(session, application: Application, doc_type: str, text: str = "some evidence text") -> Document:
    document = Document(
        application_id=application.id, doc_type=doc_type, document_name=f"{doc_type}.pdf",
        source_url=f"https://example.invalid/{application.reference}/{doc_type}.pdf",
        text_extracted=True, extracted_text=text, downloaded_at=dt.datetime.now(dt.timezone.utc),
    )
    session.add(document)
    session.commit()
    return document


def _base_refresh_response(**overrides) -> dict:
    payload = {
        "recommendation_direction": None,
        "formal_decision_outstanding": None,
        "refusal_reasons": None,
        "withdrawal_reason": None,
        "affordable_percentage": None,
        "affordable_units": None,
        "affordable_tenure_split": None,
        "affordable_housing_status": "unknown",
        "affordable_housing_notes": None,
        "affordable_provision_fully_legally_secured": None,
        "planning_position_summary": "The application remains under consideration.",
    }
    payload.update(overrides)
    return payload


def _always_succeeding_client() -> MagicMock:
    """No linked Site on any test application below, so exactly one
    responses.create call per candidate (the intelligence refresh call
    only - refresh_intelligence_for_application's own `if site is not
    None` branch never fires here)."""
    client = MagicMock()
    client.responses.create.return_value = MagicMock(output_text=json.dumps(_base_refresh_response()))
    return client


def _client_failing_on_marker(marker: str) -> MagicMock:
    """Raises OpenAIError for any prompt containing `marker` (embedded in
    that candidate's own document text), succeeds otherwise - lets a single
    MagicMock simulate a mix of per-candidate outcomes without needing to
    know call order in advance."""
    client = MagicMock()

    def _dispatch(model, input, text):  # noqa: A002 - matches real call signature
        if marker in input:
            raise OpenAIError("simulated failure")
        return MagicMock(output_text=json.dumps(_base_refresh_response()))

    client.responses.create.side_effect = _dispatch
    return client


# --- 1/2. Sequential, bounded batching ---------------------------------------


def test_batches_run_sequentially_with_bounded_internal_size(session, monkeypatch):
    apps = []
    for i in range(7):
        app = _add_application(
            session, reference=f"APP/{i}", last_seen_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=i),
        )
        _add_scheme_intelligence(session, app)
        _add_document(session, app, "decision_notice", "Granted, 20% affordable housing.")
        apps.append(app)

    seen_limits = []
    real_run_historical_rebuild = orchestrator.run_historical_rebuild

    def spy_run_historical_rebuild(*args, **kwargs):
        seen_limits.append(kwargs.get("limit"))
        return real_run_historical_rebuild(*args, **kwargs)

    monkeypatch.setattr(orchestrator, "run_historical_rebuild", spy_run_historical_rebuild)

    stop_reason, exit_code = run_to_completion(session, _always_succeeding_client(), batch_size=3, max_batches=10)

    assert stop_reason == "completed"
    assert exit_code == EXIT_SUCCESS
    assert seen_limits == [3, 3, 3]  # 3 sequential batches of 7 candidates, each capped at the given batch_size
    for app in apps:
        session.refresh(app.scheme_intelligence)
        assert app.scheme_intelligence.intelligence_rebuild_version == "b3_v1"


# --- 3. Already-rebuilt rows skipped ------------------------------------------


def test_already_rebuilt_rows_are_skipped(session):
    already_done = _add_application(session, reference="APP/DONE")
    _add_scheme_intelligence(session, already_done, intelligence_rebuild_version="b3_v1", intelligence_rebuilt_at=dt.datetime.now(dt.timezone.utc))
    _add_document(session, already_done, "decision_notice", "Granted.")

    pending = _add_application(session, reference="APP/PENDING")
    _add_scheme_intelligence(session, pending)
    _add_document(session, pending, "decision_notice", "Granted.")

    client = _always_succeeding_client()
    stop_reason, exit_code = run_to_completion(session, client, batch_size=25, max_batches=5)

    assert stop_reason == "completed"
    assert exit_code == EXIT_SUCCESS
    assert client.responses.create.call_count == 1  # only the pending one


# --- 4. Evidence-blocked rows excluded, never consume a batch slot -----------


def test_evidence_blocked_rows_are_excluded_and_dont_block_others(session):
    blocked = _add_application(session, reference="APP/BLOCKED")
    _add_scheme_intelligence(session, blocked)  # no Document at all -> no usable evidence

    usable = _add_application(session, reference="APP/USABLE")
    _add_scheme_intelligence(session, usable)
    _add_document(session, usable, "decision_notice", "Granted.")

    client = _always_succeeding_client()
    stop_reason, exit_code = run_to_completion(session, client, batch_size=25, max_batches=5)

    assert stop_reason == "completed"
    assert exit_code == EXIT_SUCCESS
    assert client.responses.create.call_count == 1
    assert blocked.scheme_intelligence.intelligence_rebuild_version is None


def test_wholly_evidence_blocked_backlog_completes_with_zero_calls(session):
    blocked = _add_application(session, reference="APP/BLOCKED")
    _add_scheme_intelligence(session, blocked)

    client = _always_succeeding_client()
    stop_reason, exit_code = run_to_completion(session, client, batch_size=25, max_batches=5)

    assert stop_reason == "completed"
    assert exit_code == EXIT_SUCCESS
    client.responses.create.assert_not_called()


# --- 5. Isolated failure does not kill the job --------------------------------


def test_isolated_failure_does_not_prevent_other_candidates_from_completing(session):
    """A persistently-failing candidate can never itself let the GLOBAL run
    reach "completed" (it always remains eligible for retry - Part 15D:
    "failed rows remain eligible") - but its one failure must never block
    or kill any OTHER candidate's own successful rebuild, in the batch it
    was isolated within or any later one."""
    good_apps = []
    for i in range(6):
        app = _add_application(
            session, reference=f"APP/OK-{i}", last_seen_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=i + 1),
        )
        _add_scheme_intelligence(session, app)
        _add_document(session, app, "decision_notice", "Granted, ordinary evidence.")
        good_apps.append(app)
    failing = _add_application(session, reference="APP/FAIL", last_seen_at=dt.datetime.now(dt.timezone.utc))
    _add_scheme_intelligence(session, failing)
    _add_document(session, failing, "decision_notice", "FAIL_TRIGGER unique marker.")

    client = _client_failing_on_marker("FAIL_TRIGGER")
    stop_reason, exit_code = run_to_completion(session, client, batch_size=25, max_batches=10)

    for app in good_apps:
        session.refresh(app.scheme_intelligence)
        assert app.scheme_intelligence.intelligence_rebuild_version == "b3_v1"
    assert failing.scheme_intelligence.intelligence_rebuild_version is None  # never fabricated on failure
    assert stop_reason in ("consecutive_systemic_failures", "max_batches_exceeded")


# --- 6. Repeated/systemic AI failure stops the job ----------------------------


def test_three_consecutive_failures_stop_the_job(session):
    ok = _add_application(session, reference="APP/OK", last_seen_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1))
    _add_scheme_intelligence(session, ok)
    _add_document(session, ok, "decision_notice", "Granted, ordinary evidence.")

    for i in range(3):
        app = _add_application(
            session, reference=f"APP/FAIL-{i}", last_seen_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=i + 2),
        )
        _add_scheme_intelligence(session, app)
        _add_document(session, app, "decision_notice", "FAIL_TRIGGER unique marker.")

    client = _client_failing_on_marker("FAIL_TRIGGER")
    stop_reason, exit_code = run_to_completion(session, client, batch_size=25, max_batches=5)

    assert stop_reason == "consecutive_systemic_failures"
    assert exit_code == EXIT_STOPPED_SYSTEMIC


# --- 7. No-forward-progress condition stops the job ---------------------------


def test_no_forward_progress_stops_the_job(session, monkeypatch):
    """Isolates the no-forward-progress decision itself from the underlying
    candidate/outcome distribution: a batch that genuinely attempted
    several candidates (>= NO_PROGRESS_MIN_ATTEMPTED) but rebuilt none of
    them must stop the job, regardless of which OUTCOME_* category absorbed
    each candidate."""
    from app.extraction.historical_rebuild import HistoricalRebuildRunSummary

    def fake_run_historical_rebuild(*args, **kwargs):
        return HistoricalRebuildRunSummary(
            dry_run=False, rebuild_version="b3_v1",
            selected=5, attempted=5, success=0, success_with_warning=0,
            no_usable_text=5, ai_error=0, invalid_output=0, error=0,
            already_rebuilt_before=10, already_rebuilt_after=10,
            remaining_rebuildable_before=5, remaining_rebuildable_after=5,
            blocked_no_usable_evidence=0,
        )

    monkeypatch.setattr(orchestrator, "run_historical_rebuild", fake_run_historical_rebuild)

    stop_reason, exit_code = run_to_completion(session, MagicMock(), batch_size=25, max_batches=5)

    assert stop_reason == "no_forward_progress"
    assert exit_code == EXIT_STOPPED_SYSTEMIC


def test_systemic_exception_during_batch_stops_the_job(session, monkeypatch):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated DB connectivity failure")

    monkeypatch.setattr(orchestrator, "run_historical_rebuild", _raise)

    stop_reason, exit_code = run_to_completion(session, _always_succeeding_client(), batch_size=25, max_batches=5)

    assert stop_reason == "systemic_exception"
    assert exit_code == EXIT_STOPPED_SYSTEMIC


# --- 8. Resume after interruption ----------------------------------------------


def test_restart_resumes_remaining_backlog_without_reprocessing(session):
    apps = []
    for i in range(5):
        app = _add_application(
            session, reference=f"APP/{i}", last_seen_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=i),
        )
        _add_scheme_intelligence(session, app)
        _add_document(session, app, "decision_notice", "Granted, ordinary evidence.")
        apps.append(app)

    client = _always_succeeding_client()

    # Simulate an interruption: only 1 batch of 2 is allowed to run.
    stop_reason, exit_code = run_to_completion(session, client, batch_size=2, max_batches=1)
    assert stop_reason == "max_batches_exceeded"
    assert exit_code == EXIT_STOPPED_SYSTEMIC
    assert client.responses.create.call_count == 2

    # Restart on the SAME database state - must resume, not reprocess.
    stop_reason, exit_code = run_to_completion(session, client, batch_size=2, max_batches=10)
    assert stop_reason == "completed"
    assert exit_code == EXIT_SUCCESS
    assert client.responses.create.call_count == 5  # 2 from the first run + 3 more, never 5+2=7
    for app in apps:
        session.refresh(app.scheme_intelligence)
        assert app.scheme_intelligence.intelligence_rebuild_version == "b3_v1"


def test_completed_job_run_again_does_zero_further_work(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")

    client = _always_succeeding_client()
    run_to_completion(session, client, batch_size=25, max_batches=5)
    assert client.responses.create.call_count == 1

    stop_reason, exit_code = run_to_completion(session, client, batch_size=25, max_batches=5)
    assert stop_reason == "completed"
    assert exit_code == EXIT_SUCCESS
    assert client.responses.create.call_count == 1  # unchanged - nothing left to do


# --- 9/10. Exit-code semantics (also exercised by tests above) ---------------


def test_successful_completion_exits_zero(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")

    stop_reason, exit_code = run_to_completion(session, _always_succeeding_client(), batch_size=25, max_batches=5)
    assert exit_code == 0
    assert stop_reason == "completed"


def test_max_batches_exceeded_exits_non_zero(session):
    apps = []
    for i in range(5):
        app = _add_application(
            session, reference=f"APP/{i}", last_seen_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=i),
        )
        _add_scheme_intelligence(session, app)
        _add_document(session, app, "decision_notice", "Granted, ordinary evidence.")
        apps.append(app)

    stop_reason, exit_code = run_to_completion(session, _always_succeeding_client(), batch_size=1, max_batches=2)
    assert stop_reason == "max_batches_exceeded"
    assert exit_code != 0


# --- Precheck -------------------------------------------------------------------


def test_precheck_fails_without_database_url(session, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    reason = precheck(session)
    assert reason is not None
    assert "DATABASE_URL" in reason


def test_precheck_fails_without_openai_key(session, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    reason = precheck(session)
    assert reason is not None
    assert "OPENAI_API_KEY" in reason


def test_precheck_fails_on_missing_schema_columns(session, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    monkeypatch.setattr("app.db.session.verify_schema", lambda engine: (["some_table"], []))
    reason = precheck(session)
    assert reason is not None
    assert "Schema is not current" in reason


def test_precheck_passes_with_current_in_memory_schema(session, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    reason = precheck(session)
    assert reason is None


def test_precheck_never_prints_secret_values(session, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:super-secret-marker@host/db")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-super-secret-marker-value")
    precheck(session)
    output = capsys.readouterr().out
    assert "super-secret-marker" not in output
