"""Independent decision-date B2 acceptance; disposable SQLite only."""
import datetime as dt
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from tests.test_planning_status_verification import _add_application, _council_config
from app.pipeline.status_verification import verify_application_status, current_verified_planning_field


def evidence():
    return SimpleNamespace(reference="R", summary_url="https://example.invalid/detail/R",
        verification_scope="FIELD_LEVEL_DATE_ONLY", body_sha256="a" * 64,
        fields={"Reference": "R", "Decision Issued Date": "2026-08-20"},
        field_evidence={"reference": {"state": "PRESENT_VALUE", "value": "R"},
            "status": {"state": "NOT_PRESENT", "value": None},
            "decision": {"state": "NOT_PRESENT", "value": None},
            "decision_date": {"state": "PRESENT_VALUE", "value": "20/08/2026"}})


@pytest.mark.parametrize("old_date", ["2026-08-20", "2026-08-19", None])
def test_date_only_atomic_provenance_and_preserved_status(session, old_date):
    app = _add_application(session, reference="R", status="Awaiting decision",
        decision=None, decision_issued_date=old_date,
        status_verified_at=dt.datetime(2026, 1, 1), last_seen_at=dt.datetime(2026, 1, 2))
    outcome = verify_application_status(session, None, _council_config(), app,
        evidence_loader=lambda prior: evidence())
    assert outcome.outcome == "field_level_verified"
    session.refresh(app)
    assert (app.status, app.decision) == ("Awaiting decision", None)
    assert app.status_verified_at == dt.datetime(2026, 1, 1)
    assert app.last_seen_at == dt.datetime(2026, 1, 2)
    assert app.decision_issued_date == "2026-08-20"
    meta = json.loads(app.planning_field_verification)
    assert meta["status"]["verified_at"] is None
    assert meta["decision_date"]["literal"] == "20/08/2026"
    assert current_verified_planning_field(app, "decision_date")
    assert bool(outcome.material_change_reasons) == (old_date != "2026-08-20")
    app.decision_issued_date = "2026-08-21"
    assert current_verified_planning_field(app, "decision_date") is None
    session.rollback()


@pytest.mark.parametrize("state,value", [("NOT_PRESENT", None), ("PRESENT_BLANK", ""),
    ("CONFLICTING", None), ("UNPARSEABLE", None), ("UNKNOWN", None)])
def test_unsupported_date_never_clears_fact(session, state, value):
    app = _add_application(session, reference="R", decision_issued_date="2026-08-19")
    result = evidence()
    result.field_evidence["decision_date"] = {"state": state, "value": value}
    outcome = verify_application_status(session, None, _council_config(), app,
        evidence_loader=lambda prior: result)
    assert outcome.outcome == "fetch_failed"
    session.refresh(app)
    assert app.decision_issued_date == "2026-08-19"
    assert app.planning_field_verification is None


def test_wrong_reference_and_future_field_stamp(session):
    app = _add_application(session, reference="R")
    result = evidence()
    result.field_evidence["reference"]["value"] = "OTHER"
    assert verify_application_status(session, None, _council_config(), app,
        evidence_loader=lambda prior: result).outcome == "fetch_failed"
    app.planning_field_verification = json.dumps({"decision_date": {
        "verified_at": "2999-01-01T00:00:00+00:00"}})
    session.commit()
    assert verify_application_status(session, None, _council_config(), app,
        evidence_loader=lambda prior: evidence()).outcome == "stale_response"


def test_date_and_metadata_rollback_together(session):
    app = _add_application(session, reference="R", decision_issued_date="2026-08-19")
    with patch.object(session, "commit", side_effect=RuntimeError("injected")):
        result = verify_application_status(session, None, _council_config(), app,
            evidence_loader=lambda prior: evidence())
    assert result.outcome == "persistence_failed"
    session.refresh(app)
    assert app.decision_issued_date == "2026-08-19"
    assert app.planning_field_verification is None
    assert not app.evidence_refresh_required


def test_metadata_changed_after_snapshot_is_stale(session):
    from sqlalchemy import update
    from app.db.models import Application
    app = _add_application(session, reference="R", decision_issued_date="2026-08-19")
    def loader(prior):
        session.execute(update(Application).where(Application.id == app.id).values(
            planning_field_verification='{}', last_seen_at=prior[4]))
        return evidence()
    result = verify_application_status(session, None, _council_config(), app,
        evidence_loader=loader)
    assert result.outcome == "stale_response"
    session.refresh(app)
    assert app.decision_issued_date == "2026-08-19"
    assert app.planning_field_verification is None


@pytest.mark.parametrize('changes', [
    {'verified_at': 'not-a-time'}, {'verified_at': '2026-01-01T00:00:00'},
    {'verified_at': '2999-01-01T00:00:00+00:00'}, {'scope': 'COUPLED'},
    {'body_sha256': 'bad'}, {'source_url': 'https://user:secret@example.invalid/detail'},
    {'source_url': 'http://example.invalid/detail'}, {'literal': '2026-08-19'},
    {'extra': 'unexpected'}])
def test_field_provenance_accessor_rejects_malformed_claims(changes):
    item = dict(state='PRESENT_VALUE', literal='20/08/2026', normalized='2026-08-20',
        source_url='https://example.invalid/detail/R', body_sha256='a'*64,
        verified_at='2026-01-01T00:00:00+00:00', scope='FIELD_LEVEL_DATE_ONLY')
    metadata={'status':dict(item,state='NOT_PRESENT',literal=None,normalized=None,verified_at=None),
              'decision':dict(item,state='NOT_PRESENT',literal=None,normalized=None,verified_at=None),
              'decision_date':item}
    app = SimpleNamespace(decision_issued_date='2026-08-20',
        planning_field_verification=json.dumps(metadata))
    assert current_verified_planning_field(app,'decision_date') is not None
    item.update(changes)
    app.planning_field_verification=json.dumps(metadata)
    assert current_verified_planning_field(app, 'decision_date') is None


@pytest.mark.parametrize('raw',['{"decision_date":{},"decision_date":{}}','{}','x'*8193])
def test_accessor_rejects_unbounded_duplicate_or_missing_schema(raw):
    app=SimpleNamespace(decision_issued_date='2026-08-20',planning_field_verification=raw)
    assert current_verified_planning_field(app,'decision_date') is None
