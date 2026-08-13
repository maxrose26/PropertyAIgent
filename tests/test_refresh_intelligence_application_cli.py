"""Targeted operator CLI: scripts/refresh_intelligence_application.py.

Tests 1-14 exercise run() directly (session/client fully injectable, no
real DB/OpenAI config needed). Tests 15-16 exercise main() with a spied,
monkeypatched session and a monkeypatched refresh_intelligence_for_
application (so no real OPENAI_API_KEY/network call is ever required).
"""
from __future__ import annotations

import datetime as dt
import json
from unittest.mock import MagicMock

import pytest

from app.db.models import Application, Document, SchemeIntelligence, Site
from app.extraction.run_extraction import OUTCOME_AI_ERROR, OUTCOME_SUCCESS
from scripts.refresh_intelligence_application import (
    EXIT_AI_ERROR,
    EXIT_SUCCESS,
    EXIT_TARGET_ERROR,
    TargetResolutionError,
    build_arg_parser,
    main,
    resolve_target,
    run,
)


def _add_application(session, *, reference: str, council_code: str = "testcouncil", **kwargs) -> Application:
    application = Application(
        council_code=council_code, reference=reference,
        summary_url=kwargs.pop("summary_url", f"https://example.invalid/{reference}"),
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


def _client_returning(payload: dict) -> MagicMock:
    client = MagicMock()
    client.responses.create.return_value = MagicMock(output_text=json.dumps(payload))
    return client


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


def _summary_stub(text: str = "Fresh summary."):
    def _fn(site, applications):
        return text
    return _fn


# --- Item 1/2: target resolution ----------------------------------------------


def test_application_id_selects_exactly_one_app(session):
    app = _add_application(session, reference="APP/1")
    resolved = resolve_target(session, application_id=app.id, reference=None, council=None)
    assert resolved.id == app.id


def test_reference_and_council_select_exactly_one_app(session):
    app = _add_application(session, reference="APP/1", council_code="testcouncil")
    resolved = resolve_target(session, application_id=None, reference="APP/1", council="testcouncil")
    assert resolved.id == app.id


# --- Item 3: id/reference mismatch aborts before OpenAI call -----------------


def test_id_reference_mismatch_raises_before_resolution(session):
    app_a = _add_application(session, reference="APP/A", council_code="testcouncil")
    _add_application(session, reference="APP/B", council_code="testcouncil")
    with pytest.raises(TargetResolutionError, match="does not match"):
        resolve_target(session, application_id=app_a.id, reference="APP/B", council="testcouncil")


def test_id_reference_mismatch_via_run_aborts_before_openai_call(session):
    app_a = _add_application(session, reference="APP/A", council_code="testcouncil")
    _add_application(session, reference="APP/B", council_code="testcouncil")
    client = MagicMock()

    exit_code = run(session, client, application_id=app_a.id, reference="APP/B", council="testcouncil", inspect=False)

    assert exit_code == EXIT_TARGET_ERROR
    client.responses.create.assert_not_called()


# --- Item 4: nonexistent application aborts -----------------------------------


def test_nonexistent_application_id_raises(session):
    with pytest.raises(TargetResolutionError, match="No application found"):
        resolve_target(session, application_id=999999, reference=None, council=None)


def test_nonexistent_application_via_run_aborts_before_openai_call(session):
    client = MagicMock()
    exit_code = run(session, client, application_id=999999, reference=None, council=None, inspect=False)
    assert exit_code == EXIT_TARGET_ERROR
    client.responses.create.assert_not_called()


def test_neither_id_nor_reference_council_raises():
    session = MagicMock()
    with pytest.raises(TargetResolutionError, match="Provide either"):
        resolve_target(session, application_id=None, reference=None, council=None)


# --- Item 5/6: exactly one refresh call, extra_fields never passed -----------


def test_run_calls_refresh_intelligence_for_application_exactly_once(session, monkeypatch):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")

    calls = []

    def fake_refresh(session_arg, client_arg, application_arg, **kwargs):
        calls.append(kwargs)
        from app.extraction.intelligence_refresh import RefreshOutcome
        return RefreshOutcome(outcome=OUTCOME_SUCCESS)

    monkeypatch.setattr("scripts.refresh_intelligence_application.refresh_intelligence_for_application", fake_refresh)

    exit_code = run(session, MagicMock(), application_id=app.id, reference=None, council=None, inspect=False)

    assert exit_code == EXIT_SUCCESS
    assert len(calls) == 1


def test_run_never_passes_extra_fields(session, monkeypatch):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)

    captured_kwargs = {}

    def fake_refresh(session_arg, client_arg, application_arg, **kwargs):
        captured_kwargs.update(kwargs)
        from app.extraction.intelligence_refresh import RefreshOutcome
        return RefreshOutcome(outcome=OUTCOME_SUCCESS)

    monkeypatch.setattr("scripts.refresh_intelligence_application.refresh_intelligence_for_application", fake_refresh)

    run(session, MagicMock(), application_id=app.id, reference=None, council=None, inspect=False)

    assert "extra_fields" not in captured_kwargs


# --- Item 7: historical rebuild markers untouched -----------------------------


def test_historical_rebuild_markers_remain_untouched(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(
        session, app, intelligence_rebuild_version="b3_v1",
        intelligence_rebuilt_at=dt.datetime(2026, 8, 12, 22, 45, tzinfo=dt.timezone.utc),
    )
    _add_document(session, app, "decision_notice", "Granted.")
    client = _client_returning(_base_refresh_response())

    run(session, client, application_id=app.id, reference=None, council=None, inspect=False)

    assert app.scheme_intelligence.intelligence_rebuild_version == "b3_v1"
    assert app.scheme_intelligence.intelligence_rebuilt_at.replace(tzinfo=None) == dt.datetime(2026, 8, 12, 22, 45)


# --- Item 8/9: Site Summary default pathway / no-Site case --------------------


def test_linked_site_summary_regenerated_via_default_pathway(session, monkeypatch):
    captured = {}

    def fake_generate_scheme_summary(client, site, applications, merged, lapse, phase_breakdown, **kwargs):
        captured["called"] = True
        return "New summary text."

    monkeypatch.setattr("app.reporting.scheme_summary.generate_scheme_summary", fake_generate_scheme_summary)

    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    app = _add_application(session, reference="APP/1", site_id=site.id)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")
    client = _client_returning(_base_refresh_response())

    exit_code = run(session, client, application_id=app.id, reference=None, council=None, inspect=False)

    assert exit_code == EXIT_SUCCESS
    assert captured.get("called") is True
    assert site.status_summary == "New summary text."


def test_no_site_application_succeeds_without_summary_call(session):
    app = _add_application(session, reference="APP/1")  # no site_id
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")
    client = _client_returning(_base_refresh_response())

    exit_code = run(session, client, application_id=app.id, reference=None, council=None, inspect=False)

    assert exit_code == EXIT_SUCCESS
    assert client.responses.create.call_count == 1  # refresh call only, no summary call


# --- Item 10/11: exit codes ----------------------------------------------------


def test_ai_error_outcome_returns_non_zero(session, monkeypatch):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)

    def fake_refresh(session_arg, client_arg, application_arg, **kwargs):
        from app.extraction.intelligence_refresh import RefreshOutcome
        return RefreshOutcome(outcome=OUTCOME_AI_ERROR)

    monkeypatch.setattr("scripts.refresh_intelligence_application.refresh_intelligence_for_application", fake_refresh)

    exit_code = run(session, MagicMock(), application_id=app.id, reference=None, council=None, inspect=False)

    assert exit_code == EXIT_AI_ERROR
    assert exit_code != EXIT_SUCCESS


def test_success_outcome_returns_zero(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")
    client = _client_returning(_base_refresh_response())

    exit_code = run(session, client, application_id=app.id, reference=None, council=None, inspect=False)

    assert exit_code == EXIT_SUCCESS


# --- Item 12: no secret printed ------------------------------------------------


def test_no_secret_printed_by_run(session, capsys):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")
    client = _client_returning(_base_refresh_response())

    run(session, client, application_id=app.id, reference=None, council=None, inspect=False)

    output = capsys.readouterr().out
    assert "OPENAI_API_KEY" not in output
    assert "DATABASE_URL" not in output


# --- Item 13: no batch selection possible --------------------------------------


def test_cli_does_not_support_multiple_ids_or_batches():
    parser = build_arg_parser()
    app_id_action = next(a for a in parser._actions if a.dest == "application_id")
    assert app_id_action.type is int
    assert app_id_action.nargs is None  # single value only, never a list
    with pytest.raises(SystemExit):
        parser.parse_args(["--application-id", "1,2,3"])  # not a valid int -> argparse rejects it


def test_resolve_target_always_returns_a_single_application_never_a_list(session):
    app = _add_application(session, reference="APP/1")
    resolved = resolve_target(session, application_id=app.id, reference=None, council=None)
    assert isinstance(resolved, Application)


# --- Item 14: no B1/B2 fields fabricated ---------------------------------------


def test_no_b1_b2_fields_fabricated(session):
    app = _add_application(
        session, reference="APP/1", evidence_refresh_required=False,
        evidence_refresh_reason=None, material_evidence_changed_at=None,
    )
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")
    client = _client_returning(_base_refresh_response())

    run(session, client, application_id=app.id, reference=None, council=None, inspect=False)

    assert app.evidence_refresh_required is False
    assert app.evidence_refresh_reason is None
    assert app.material_evidence_changed_at is None


# --- Item 15/16: session lifecycle via main() ----------------------------------


class _SpySession:
    def __init__(self, real_session):
        self._real = real_session
        self.closed = False
        self.rolled_back = False

    def __getattr__(self, name):
        return getattr(self._real, name)

    def close(self):
        self.closed = True
        self._real.close()

    def rollback(self):
        self.rolled_back = True
        self._real.rollback()


def test_session_closes_on_success(session, monkeypatch):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)

    spy = _SpySession(session)
    monkeypatch.setattr("app.db.session.get_session", lambda: spy)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")

    def fake_refresh(session_arg, client_arg, application_arg, **kwargs):
        from app.extraction.intelligence_refresh import RefreshOutcome
        return RefreshOutcome(outcome=OUTCOME_SUCCESS)

    monkeypatch.setattr("scripts.refresh_intelligence_application.refresh_intelligence_for_application", fake_refresh)

    exit_code = main(["--application-id", str(app.id)])

    assert exit_code == EXIT_SUCCESS
    assert spy.closed is True


def test_session_rolls_back_and_closes_on_unhandled_exception(session, monkeypatch):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)

    spy = _SpySession(session)
    monkeypatch.setattr("app.db.session.get_session", lambda: spy)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")

    def raising_refresh(session_arg, client_arg, application_arg, **kwargs):
        raise RuntimeError("simulated unexpected failure")

    monkeypatch.setattr("scripts.refresh_intelligence_application.refresh_intelligence_for_application", raising_refresh)

    with pytest.raises(RuntimeError, match="simulated unexpected failure"):
        main(["--application-id", str(app.id)])

    assert spy.rolled_back is True
    assert spy.closed is True


def test_main_never_prints_the_fake_test_secret(session, monkeypatch, capsys):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)

    spy = _SpySession(session)
    monkeypatch.setattr("app.db.session.get_session", lambda: spy)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-super-secret-marker-value")

    def fake_refresh(session_arg, client_arg, application_arg, **kwargs):
        from app.extraction.intelligence_refresh import RefreshOutcome
        return RefreshOutcome(outcome=OUTCOME_SUCCESS)

    monkeypatch.setattr("scripts.refresh_intelligence_application.refresh_intelligence_for_application", fake_refresh)

    main(["--application-id", str(app.id)])

    output = capsys.readouterr().out
    assert "sk-test-super-secret-marker-value" not in output


# --- --inspect mode: zero OpenAI calls, zero writes ----------------------------


def test_inspect_mode_makes_zero_openai_calls_and_zero_writes(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app, affordable_percentage_final=20.0)
    _add_document(session, app, "decision_notice", "Granted.")
    client = MagicMock()

    exit_code = run(session, client, application_id=app.id, reference=None, council=None, inspect=True)

    assert exit_code == EXIT_SUCCESS
    client.responses.create.assert_not_called()
    assert app.scheme_intelligence.affordable_percentage_final == 20.0
