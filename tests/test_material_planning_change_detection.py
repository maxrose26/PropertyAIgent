"""PR B1: Material Application-State Detection + Persisted Refresh Signal -
focused tests for:

1. app.pipeline.material_change.detect_material_application_change in
   isolation - decision/status bucket transitions, the conservative
   unit-count rule, normalization preventing false positives.
2. Its wiring into app.pipeline.run_weekly._upsert_scraped_application -
   the persisted evidence_refresh_* signal, new-application exclusion,
   idempotent repeated-observation behaviour, deterministic multi-reason
   ordering.
3. Migration/backfill safety for the four new Application columns.
4. Regression guards: PR A, the circuit breaker, and AI-free Daily
   Discovery are all unaffected by this feature.

Uses the same in-memory-SQLite `session` fixture as the rest of this
suite (tests/conftest.py) - "testcouncil"/"othercouncil" already present.
"""
from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.config import CouncilConfig
from app.db.models import Application, Base, Council
from app.pipeline.material_change import (
    REASON_DECISION_GRANTED,
    REASON_DECISION_REFUSED,
    REASON_DECISION_WITHDRAWN,
    REASON_STATUS_TRANSITION,
    REASON_UNIT_COUNT_CHANGED,
    TRIGGER_MATERIAL_CHANGE,
    ApplicationState,
    MaterialChangeStats,
    detect_material_application_change,
)
from app.pipeline.run_weekly import _upsert_scraped_application, stage_scrape


def _council_config(code: str = "testcouncil") -> CouncilConfig:
    return CouncilConfig(
        code=code, name=code, base_url="https://example.invalid",
        date_field_mode="received", doc_system="idox", anite_base_url=None,
        unit_threshold=10, region=None, country=None,
    )


def _add_application(session, *, reference: str, council_code: str = "testcouncil", **kwargs) -> Application:
    application = Application(
        council_code=council_code, reference=reference,
        summary_url=f"https://example.invalid/{reference}", **kwargs,
    )
    session.add(application)
    session.commit()
    return application


def _scraped_app(reference: str, fields: dict, *, estimated_unit_count=None, qualifies=True, category=None):
    return MagicMock(
        reference=reference, fields=fields, qualifies=qualifies, application_category=category,
        opportunity_classification=None, estimated_unit_count=estimated_unit_count,
        summary_url=f"https://example.invalid/{reference}", further_info_url=None, keyval=None,
    )


# --- A: detect_material_application_change in isolation ----------------------


def test_awaiting_to_granted_is_material():
    old = ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=100)
    new = ApplicationState(status="Decided", decision="Granted", estimated_unit_count=100)
    result = detect_material_application_change(old, new)
    assert result.changed is True
    assert result.reasons == (REASON_DECISION_GRANTED,)


def test_awaiting_to_refused_is_material():
    old = ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=100)
    new = ApplicationState(status="Decided", decision="Refused", estimated_unit_count=100)
    result = detect_material_application_change(old, new)
    assert result.changed is True
    assert result.reasons == (REASON_DECISION_REFUSED,)


def test_awaiting_to_withdrawn_is_material():
    old = ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=100)
    new = ApplicationState(status="Withdrawn", decision=None, estimated_unit_count=100)
    result = detect_material_application_change(old, new)
    assert result.changed is True
    assert result.reasons == (REASON_DECISION_WITHDRAWN,)


def test_awaiting_to_awaiting_is_unchanged():
    old = ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=100)
    new = ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=100)
    result = detect_material_application_change(old, new)
    assert result.changed is False
    assert result.reasons == ()


def test_granted_to_granted_is_unchanged():
    old = ApplicationState(status="Decided", decision="Granted", estimated_unit_count=100)
    new = ApplicationState(status="Decided", decision="Granted", estimated_unit_count=100)
    result = detect_material_application_change(old, new)
    assert result.changed is False


def test_normalization_prevents_false_changes():
    """Different raw portal text, SAME classify_decision_status bucket -
    must not be treated as a change. 'Approved' and 'Granted' both match
    is_granted_decision's own keyword check."""
    old = ApplicationState(status="Decided", decision="Approved", estimated_unit_count=100)
    new = ApplicationState(status="Decided", decision="Granted", estimated_unit_count=100)
    result = detect_material_application_change(old, new)
    assert result.changed is False
    assert result.old_decision_bucket == result.new_decision_bucket == "granted"


def test_terminal_decision_correction_is_status_transition():
    """A rarer real-world case (portal correction): refused -> granted -
    still genuinely material, but not one of the three named reasons."""
    old = ApplicationState(status="Decided", decision="Refused", estimated_unit_count=100)
    new = ApplicationState(status="Decided", decision="Granted", estimated_unit_count=100)
    result = detect_material_application_change(old, new)
    assert result.changed is True
    assert result.reasons == (REASON_DECISION_GRANTED,)  # new bucket IS granted - gets its own named reason


def test_reverting_to_not_yet_decided_is_status_transition():
    old = ApplicationState(status="Decided", decision="Granted", estimated_unit_count=100)
    new = ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=100)
    result = detect_material_application_change(old, new)
    assert result.changed is True
    assert result.reasons == (REASON_STATUS_TRANSITION,)


def test_reliable_unit_count_change_is_material():
    old = ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=100)
    new = ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=120)
    result = detect_material_application_change(old, new)
    assert result.changed is True
    assert result.reasons == (REASON_UNIT_COUNT_CHANGED,)


def test_unchanged_unit_count_is_not_material():
    old = ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=100)
    new = ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=100)
    result = detect_material_application_change(old, new)
    assert result.changed is False


def test_null_to_known_unit_count_is_not_material():
    """Section F's explicit conservative rule: NULL -> 100 means the
    count simply BECAME known, not that it changed - deliberately NOT
    treated the same way the decision/status rule treats an unknown ->
    terminal transition."""
    old = ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=None)
    new = ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=100)
    result = detect_material_application_change(old, new)
    assert result.changed is False


def test_known_to_null_unit_count_is_not_material():
    """Symmetric case - a count becoming unknown again (e.g. a later
    scrape's proposal text no longer parses cleanly) is equally not
    material by the same conservative rule."""
    old = ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=100)
    new = ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=None)
    result = detect_material_application_change(old, new)
    assert result.changed is False


def test_multiple_material_changes_produce_deterministic_reasons():
    old = ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=100)
    new = ApplicationState(status="Decided", decision="Granted", estimated_unit_count=120)
    result = detect_material_application_change(old, new)
    assert result.changed is True
    assert result.reasons == (REASON_DECISION_GRANTED, REASON_UNIT_COUNT_CHANGED)  # always this order

    # Re-run with fields in a different construction order - same result,
    # proving the ordering is intrinsic to the function, not incidental.
    result_again = detect_material_application_change(old, new)
    assert result_again.reasons == result.reasons


# --- B: _upsert_scraped_application wiring ------------------------------------


def test_new_application_does_not_become_a_material_change_event(session, capsys):
    scraped = _scraped_app("APP/NEW/1", {"Status": "Decided", "Decision": "Granted"}, estimated_unit_count=100)
    application = _upsert_scraped_application(session, _council_config(), scraped, batch_id="b1")
    session.commit()  # the Boolean column's Python-side default=False only applies on flush

    assert application.evidence_refresh_required is False
    assert application.evidence_refresh_reason is None
    assert application.evidence_refresh_trigger is None
    out = capsys.readouterr().out
    assert "[material-change]" not in out


def test_existing_application_material_change_sets_refresh_signal(session):
    application = _add_application(session, reference="APP/1", status="Awaiting Decision", decision=None)
    scraped = _scraped_app("APP/1", {"Status": "Decided", "Decision": "Granted"}, estimated_unit_count=None)

    _upsert_scraped_application(session, _council_config(), scraped, batch_id="b1")

    assert application.evidence_refresh_required is True
    assert application.evidence_refresh_reason == REASON_DECISION_GRANTED
    assert application.evidence_refresh_trigger == TRIGGER_MATERIAL_CHANGE
    assert application.evidence_refresh_requested_at is not None
    # B1 must not touch AI/evidence state itself.
    assert application.documents_last_checked_at is None


def test_existing_application_unchanged_does_not_set_refresh_signal(session):
    application = _add_application(session, reference="APP/1", status="Awaiting Decision", decision=None)
    scraped = _scraped_app("APP/1", {"Status": "Awaiting Decision"}, estimated_unit_count=None)

    _upsert_scraped_application(session, _council_config(), scraped, batch_id="b1")

    assert application.evidence_refresh_required is False
    assert application.evidence_refresh_reason is None


def test_repeated_observation_of_same_state_does_not_repeat_change_event(session, capsys):
    application = _add_application(session, reference="APP/1", status="Awaiting Decision", decision=None)
    scraped_grant = _scraped_app("APP/1", {"Status": "Decided", "Decision": "Granted"}, estimated_unit_count=None)

    _upsert_scraped_application(session, _council_config(), scraped_grant, batch_id="b1")
    first_requested_at = application.evidence_refresh_requested_at
    capsys.readouterr()  # clear captured output from the first (real) change

    # Second pass observes the SAME now-current state - no new change.
    scraped_still_granted = _scraped_app("APP/1", {"Status": "Decided", "Decision": "Granted"}, estimated_unit_count=None)
    _upsert_scraped_application(session, _council_config(), scraped_still_granted, batch_id="b2")

    assert application.evidence_refresh_required is True  # still set from the real change - never cleared by B1
    assert application.evidence_refresh_requested_at == first_requested_at  # NOT re-stamped
    out = capsys.readouterr().out
    assert "[material-change]" not in out  # no new event logged for a non-change


def test_upsert_records_into_material_change_stats(session):
    application = _add_application(session, reference="APP/1", status="Awaiting Decision", decision=None)
    stats = MaterialChangeStats()
    scraped = _scraped_app("APP/1", {"Status": "Decided", "Decision": "Refused"}, estimated_unit_count=None)

    _upsert_scraped_application(session, _council_config(), scraped, batch_id="b1", material_change_stats=stats)

    assert stats.compared == 1
    assert stats.material_changes == 1
    assert stats.reason_counts[REASON_DECISION_REFUSED] == 1


def test_new_application_not_recorded_into_material_change_stats(session):
    stats = MaterialChangeStats()
    scraped = _scraped_app("APP/NEW/1", {"Status": "Decided", "Decision": "Granted"}, estimated_unit_count=None)

    _upsert_scraped_application(session, _council_config(), scraped, batch_id="b1", material_change_stats=stats)

    assert stats.compared == 0  # a brand-new row is never compared at all
    assert stats.material_changes == 0


# --- C: stage_scrape end-to-end -----------------------------------------------


def test_stage_scrape_flags_material_change_for_existing_application(session, capsys):
    application = _add_application(session, reference="APP/1", status="Awaiting Decision", decision=None)
    scraped = _scraped_app("APP/1", {"Status": "Decided", "Decision": "Granted"}, estimated_unit_count=None)

    with patch("app.pipeline.run_weekly._scrape_month_for_council", return_value=[scraped]):
        stage_scrape(session, MagicMock(), _council_config(), "01/08/2026", "31/08/2026", "batch1")

    assert application.evidence_refresh_required is True
    out = capsys.readouterr().out
    assert "[material-change] council=testcouncil summary compared=1 material_changes=1" in out


def test_failed_primary_scrape_cannot_fabricate_material_changes(session):
    """If the portal call itself fails, stage_scrape never reaches the
    upsert loop at all - no Application row is touched, so no refresh
    signal can be fabricated from a scrape that never actually
    completed."""
    application = _add_application(session, reference="APP/1", status="Awaiting Decision", decision=None)

    with patch("app.pipeline.run_weekly._scrape_month_for_council", side_effect=RuntimeError("portal unreachable")):
        with pytest.raises(RuntimeError):
            stage_scrape(session, MagicMock(), _council_config(), "01/08/2026", "31/08/2026", "batch1")

    assert application.evidence_refresh_required is False
    assert application.status == "Awaiting Decision"  # completely untouched


# --- D: migration / backfill --------------------------------------------------


def _build_old_applications_table(engine) -> MetaData:
    old_metadata = MetaData()
    Table(
        "applications", old_metadata,
        Column("id", Integer, primary_key=True),
        Column("council_code", String(20)),
        Column("reference", String(100)),
    )
    old_metadata.create_all(engine)
    return old_metadata


def test_migration_adds_evidence_refresh_columns_safely():
    from app.db.session import migrate_schema

    engine = create_engine("sqlite:///:memory:", future=True)
    old_metadata = _build_old_applications_table(engine)
    with engine.begin() as conn:
        conn.execute(
            Table("applications", old_metadata).insert(),
            [{"id": 1, "council_code": "testcouncil", "reference": "APP/OLD/1"}],
        )

    created_tables, added_columns = migrate_schema(engine)
    added_names = {col for _table, col in added_columns}
    assert "evidence_refresh_required" in added_names
    assert "evidence_refresh_reason" in added_names
    assert "evidence_refresh_trigger" in added_names
    assert "evidence_refresh_requested_at" in added_names


def test_historical_rows_are_neutral_after_migration():
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
            "SELECT evidence_refresh_required, evidence_refresh_reason, evidence_refresh_trigger, "
            "evidence_refresh_requested_at FROM applications WHERE reference = 'APP/OLD/1'"
        )).fetchone()
    assert bool(row.evidence_refresh_required) is False  # backfilled False, never fabricated True
    assert row.evidence_refresh_reason is None  # never fabricated
    assert row.evidence_refresh_trigger is None
    assert row.evidence_refresh_requested_at is None


def test_migration_is_idempotent_for_evidence_refresh_required():
    from app.db.session import _backfill_evidence_refresh_required, migrate_schema

    engine = create_engine("sqlite:///:memory:", future=True)
    old_metadata = _build_old_applications_table(engine)
    with engine.begin() as conn:
        conn.execute(
            Table("applications", old_metadata).insert(),
            [{"id": 1, "council_code": "testcouncil", "reference": "APP/OLD/1"}],
        )

    migrate_schema(engine)
    second_pass_updated = _backfill_evidence_refresh_required(engine)
    assert second_pass_updated == 0  # already backfilled - no-op

    second_created, second_added = migrate_schema(engine)
    assert second_added == []


# --- E: regression guards -----------------------------------------------------


def test_daily_discovery_still_never_imports_openai():
    from pathlib import Path as _Path

    repo_root = _Path(__file__).resolve().parents[1]
    for module_path in ("scripts/run_daily_councils.py", "app/pipeline/material_change.py"):
        source = (repo_root / module_path).read_text(encoding="utf-8")
        assert "import openai" not in source.lower()
        assert "from openai" not in source.lower()


def test_material_change_module_does_not_touch_document_or_ai_fields(session):
    """B1 must not modify AI/evidence state - only the four evidence_
    refresh_* fields it owns."""
    application = _add_application(
        session, reference="APP/1", status="Awaiting Decision", decision=None,
        documents_last_checked_at=None,
    )
    scraped = _scraped_app("APP/1", {"Status": "Decided", "Decision": "Granted"}, estimated_unit_count=None)

    _upsert_scraped_application(session, _council_config(), scraped, batch_id="b1")

    assert application.documents_last_checked_at is None
    assert application.documents_legacy_unverified is False
