"""PR B3: Evidence-Driven AI Intelligence Refresh - focused tests for:

1. Freshness eligibility (app.pipeline.run_weekly.INTELLIGENCE_REFRESH_ELIGIBLE) -
   material_evidence_changed_at vs intelligence_evidence_processed_at, NOT
   evidence_refresh_required.
2. Atomic replacement (app.extraction.intelligence_refresh.
   refresh_intelligence_for_application) - success commits intelligence +
   summary + watermark together; any failure preserves all three untouched
   and leaves the candidate retryable.
3. Event-aware refresh depth routing (B1 reason -> refresh depth -> target
   evidence categories).
4. Affordable housing / tenure as first-class, evidence-grounded intelligence -
   status/security distinct from raw data, changes surfaced, nothing
   fabricated.
5. Site Summary prompt grounding (recommendation vs formal decision,
   affordable housing status wording).

Uses the same in-memory-SQLite `session` fixture as the rest of this suite
(tests/conftest.py). No real OpenAI call anywhere - the LLM client is always
a MagicMock whose .responses.create(...).output_text is a fixed JSON string.
"""
from __future__ import annotations

import datetime as dt
import json
from unittest.mock import MagicMock

import pytest
from openai import OpenAIError
from sqlalchemy import select

from app.config import CouncilConfig
from app.db.models import Application, Council, Document, SchemeIntelligence, Site
from app.extraction.intelligence_refresh import (
    AFFORDABLE_HOUSING_STATUSES,
    DEPTH_BROAD,
    DEPTH_DECISION_RESOLUTION,
    DEPTH_FOCUSED_REFUSAL,
    DEPTH_FOCUSED_WITHDRAWAL,
    DEPTH_RECOMMENDATION,
    DEPTH_UNIT_CHANGE,
    LEGALLY_SECURED_STATUS,
    MIXED_SECURITY_FALLBACK_STATUS,
    REFRESH_SCHEMA,
    _DOC_TYPES_BY_DEPTH,
    build_refresh_prompt,
    detect_affordable_housing_changes,
    extract_refusal_reason_excerpt,
    guard_conditioned_status_requires_an_actual_condition,
    guard_legally_secured_position,
    guard_legally_secured_requires_authoritative_content,
    guard_mixed_legal_security_position,
    refresh_depth_for_reasons,
    refresh_intelligence_for_application,
    select_refresh_evidence_documents,
)
from app.extraction.run_extraction import (
    OUTCOME_AI_ERROR,
    OUTCOME_ERROR,
    OUTCOME_INVALID_OUTPUT,
    OUTCOME_NO_USABLE_TEXT,
    OUTCOME_SUCCESS,
)
from app.pipeline.material_change import (
    REASON_DECISION_GRANTED,
    REASON_DECISION_OUTCOME_UNKNOWN,
    REASON_DECISION_REFUSED,
    REASON_DECISION_WITHDRAWN,
    REASON_RECOMMENDATION_MADE,
    REASON_UNIT_COUNT_CHANGED,
)
from app.pipeline.run_weekly import INTELLIGENCE_REFRESH_ELIGIBLE
from app.reporting.scheme_summary import build_summary_prompt


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


def _summary_stub(text: str = "Updated status note.", raise_error: bool = False):
    def _fn(site, applications):
        if raise_error:
            raise RuntimeError("summary generation failed")
        return text
    return _fn


# --- 1-7: Freshness eligibility ----------------------------------------------


def test_material_evidence_newer_than_watermark_is_eligible(session):
    now = dt.datetime.now(dt.timezone.utc)
    app = _add_application(
        session, reference="APP/1",
        material_evidence_changed_at=now,
        intelligence_evidence_processed_at=now - dt.timedelta(days=1),
    )
    _add_scheme_intelligence(session, app)
    candidates = session.execute(select(Application).where(INTELLIGENCE_REFRESH_ELIGIBLE)).scalars().all()
    assert app.id in {a.id for a in candidates}


def test_equal_watermark_not_eligible(session):
    now = dt.datetime.now(dt.timezone.utc)
    app = _add_application(session, reference="APP/1", material_evidence_changed_at=now, intelligence_evidence_processed_at=now)
    _add_scheme_intelligence(session, app)
    candidates = session.execute(select(Application).where(INTELLIGENCE_REFRESH_ELIGIBLE)).scalars().all()
    assert app.id not in {a.id for a in candidates}


def test_older_material_evidence_not_eligible(session):
    now = dt.datetime.now(dt.timezone.utc)
    app = _add_application(
        session, reference="APP/1",
        material_evidence_changed_at=now - dt.timedelta(days=1), intelligence_evidence_processed_at=now,
    )
    _add_scheme_intelligence(session, app)
    candidates = session.execute(select(Application).where(INTELLIGENCE_REFRESH_ELIGIBLE)).scalars().all()
    assert app.id not in {a.id for a in candidates}


def test_missing_watermark_with_material_evidence_is_eligible(session):
    app = _add_application(session, reference="APP/1", material_evidence_changed_at=dt.datetime.now(dt.timezone.utc))
    _add_scheme_intelligence(session, app)
    candidates = session.execute(select(Application).where(INTELLIGENCE_REFRESH_ELIGIBLE)).scalars().all()
    assert app.id in {a.id for a in candidates}


def test_evidence_refresh_required_alone_does_not_trigger(session):
    # evidence_refresh_required=True but material_evidence_changed_at was
    # never set (e.g. B2 hasn't run yet, or found nothing new) - not B3
    # eligible (Part 6's own explicit instruction).
    app = _add_application(session, reference="APP/1", evidence_refresh_required=True, material_evidence_changed_at=None)
    _add_scheme_intelligence(session, app)
    candidates = session.execute(select(Application).where(INTELLIGENCE_REFRESH_ELIGIBLE)).scalars().all()
    assert app.id not in {a.id for a in candidates}


def test_checked_no_new_evidence_does_not_trigger(session):
    # CHECKED_NO_NEW_EVIDENCE never sets material_evidence_changed_at (see
    # app.pipeline.evidence_refresh) - simulated here directly by its
    # absence.
    app = _add_application(session, reference="APP/1", evidence_refresh_required=False, material_evidence_changed_at=None)
    _add_scheme_intelligence(session, app)
    candidates = session.execute(select(Application).where(INTELLIGENCE_REFRESH_ELIGIBLE)).scalars().all()
    assert app.id not in {a.id for a in candidates}


def test_no_scheme_intelligence_yet_is_not_a_refresh_candidate(session):
    # A brand-new Application (no SchemeIntelligence at all) belongs to
    # stage_extraction, not stage_intelligence_refresh, even if somehow
    # material_evidence_changed_at got set.
    app = _add_application(session, reference="APP/1", material_evidence_changed_at=dt.datetime.now(dt.timezone.utc))
    candidates = session.execute(select(Application).where(INTELLIGENCE_REFRESH_ELIGIBLE)).scalars().all()
    assert app.id not in {a.id for a in candidates}


# --- 8-16: Atomic replacement -------------------------------------------------


def test_successful_refresh_replaces_intelligence(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app, affordable_percentage_final=20.0)
    _add_document(session, app, "decision_notice", "The council grants planning permission.")

    client = _client_returning(_base_refresh_response(affordable_percentage=35.0, affordable_housing_status="agreed"))
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert outcome.outcome == OUTCOME_SUCCESS
    assert app.scheme_intelligence.affordable_percentage_final == 35.0
    assert app.scheme_intelligence.affordable_housing_status == "agreed"


def test_successful_refresh_updates_site_summary(session):
    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED, site_id=site.id)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")

    client = _client_returning(_base_refresh_response())
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub("New summary text"))

    assert site.status_summary == "New summary text"
    assert site.status_summary_updated_at is not None


def test_successful_refresh_advances_watermark(session):
    now = dt.datetime.now(dt.timezone.utc)
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED, material_evidence_changed_at=now)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")

    client = _client_returning(_base_refresh_response())
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.intelligence_evidence_processed_at == now


def test_ai_error_preserves_old_intelligence(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app, affordable_percentage_final=20.0)
    _add_document(session, app, "decision_notice", "Granted.")

    client = MagicMock()
    client.responses.create.side_effect = OpenAIError("api down")
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert outcome.outcome == OUTCOME_AI_ERROR
    assert app.scheme_intelligence.affordable_percentage_final == 20.0


def test_invalid_structured_output_preserves_old_intelligence(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app, affordable_percentage_final=20.0)
    _add_document(session, app, "decision_notice", "Granted.")

    client = MagicMock()
    client.responses.create.return_value = MagicMock(output_text="{not valid json")
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert outcome.outcome == OUTCOME_INVALID_OUTPUT
    assert app.scheme_intelligence.affordable_percentage_final == 20.0


def test_invalid_affordable_status_enum_preserves_old_intelligence(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app, affordable_percentage_final=20.0)
    _add_document(session, app, "decision_notice", "Granted.")

    client = _client_returning(_base_refresh_response(affordable_housing_status="totally_made_up"))
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert outcome.outcome == OUTCOME_INVALID_OUTPUT
    assert app.scheme_intelligence.affordable_percentage_final == 20.0


def test_summary_failure_preserves_old_intelligence_and_summary(session):
    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED, site_id=site.id)
    site.status_summary = "Old summary"
    _add_scheme_intelligence(session, app, affordable_percentage_final=20.0)
    _add_document(session, app, "decision_notice", "Granted.")
    session.commit()

    client = _client_returning(_base_refresh_response(affordable_percentage=99.0))
    outcome = refresh_intelligence_for_application(
        session, client, app, generate_summary=_summary_stub(raise_error=True),
    )

    assert outcome.outcome == OUTCOME_ERROR
    assert app.scheme_intelligence.affordable_percentage_final == 20.0  # not overwritten
    assert site.status_summary == "Old summary"  # not overwritten


def test_failed_refresh_leaves_watermark_unchanged(session):
    now = dt.datetime.now(dt.timezone.utc)
    app = _add_application(
        session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED,
        material_evidence_changed_at=now, intelligence_evidence_processed_at=None,
    )
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")

    client = MagicMock()
    client.responses.create.side_effect = OpenAIError("api down")
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.intelligence_evidence_processed_at is None


def test_failed_refresh_remains_retryable(session):
    now = dt.datetime.now(dt.timezone.utc)
    app = _add_application(
        session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED, material_evidence_changed_at=now,
    )
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")

    client = MagicMock()
    client.responses.create.side_effect = OpenAIError("api down")
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    candidates = session.execute(select(Application).where(INTELLIGENCE_REFRESH_ELIGIBLE)).scalars().all()
    assert app.id in {a.id for a in candidates}


def test_same_evidence_not_processed_twice_after_success(session):
    now = dt.datetime.now(dt.timezone.utc)
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED, material_evidence_changed_at=now)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")

    client = _client_returning(_base_refresh_response())
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    candidates = session.execute(select(Application).where(INTELLIGENCE_REFRESH_ELIGIBLE)).scalars().all()
    assert app.id not in {a.id for a in candidates}


# --- 17-27: Event-specific refresh depth -------------------------------------


def test_granted_triggers_broad_depth():
    assert refresh_depth_for_reasons([REASON_DECISION_GRANTED]) == DEPTH_BROAD


def test_refused_triggers_focused_refusal_depth():
    assert refresh_depth_for_reasons([REASON_DECISION_REFUSED]) == DEPTH_FOCUSED_REFUSAL


def test_withdrawn_triggers_focused_withdrawal_depth():
    assert refresh_depth_for_reasons([REASON_DECISION_WITHDRAWN]) == DEPTH_FOCUSED_WITHDRAWAL


def test_recommendation_made_triggers_recommendation_depth():
    assert refresh_depth_for_reasons([REASON_RECOMMENDATION_MADE]) == DEPTH_RECOMMENDATION


def test_decision_outcome_unknown_triggers_decision_resolution_depth():
    assert refresh_depth_for_reasons([REASON_DECISION_OUTCOME_UNKNOWN]) == DEPTH_DECISION_RESOLUTION


def test_unit_count_changed_triggers_unit_change_depth():
    assert refresh_depth_for_reasons([REASON_UNIT_COUNT_CHANGED]) == DEPTH_UNIT_CHANGE


def test_later_s106_evidence_triggers_refresh_without_new_status_transition(session):
    # No B1 reason at all (empty evidence_refresh_reason) - a later S106
    # advancing material_evidence_changed_at with no fresh B1 transition
    # must still default to the broadest (safest) depth, per Part 9.
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=None)
    _add_scheme_intelligence(session, app, affordable_percentage_final=35.0)
    _add_document(session, app, "s106", "The executed S106 secures 35% affordable housing.")

    client = _client_returning(_base_refresh_response(
        affordable_housing_status=LEGALLY_SECURED_STATUS, affordable_provision_fully_legally_secured=True,
    ))
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert outcome.depth == DEPTH_BROAD
    assert outcome.outcome == OUTCOME_SUCCESS
    assert app.scheme_intelligence.affordable_housing_status == LEGALLY_SECURED_STATUS


def test_recommendation_never_represented_as_formal_decision_without_evidence(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_RECOMMENDATION_MADE)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "officer_report", "Officers recommend approval, subject to conditions.")

    client = _client_returning(_base_refresh_response(recommendation_direction="approval", formal_decision_outstanding=True))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.recommendation_direction == "approval"
    assert app.scheme_intelligence.formal_decision_outstanding is True


def test_unknown_outcome_not_guessed(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_OUTCOME_UNKNOWN)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "officer_report", "Status shows Decided but no formal outcome is stated anywhere.")

    client = _client_returning(_base_refresh_response(recommendation_direction="unclear"))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.recommendation_direction == "unclear"


def test_missing_refusal_reason_not_fabricated(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_REFUSED)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "The application is refused.")

    client = _client_returning(_base_refresh_response(refusal_reasons=None))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.refusal_reasons is None


def test_missing_withdrawal_reason_not_fabricated(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_WITHDRAWN)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "The application has been withdrawn.")

    client = _client_returning(_base_refresh_response(withdrawal_reason=None))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.withdrawal_reason is None


# --- 28-44: Affordable housing / tenure --------------------------------------


def test_affordable_percentage_extracted_when_evidenced(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted, 40% affordable housing secured.")

    client = _client_returning(_base_refresh_response(affordable_percentage=40.0))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_percentage_final == 40.0


def test_affordable_unit_count_extracted_when_evidenced(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "40 affordable units secured.")

    client = _client_returning(_base_refresh_response(affordable_units=40))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_units_final == 40


def test_tenure_split_extracted_when_evidenced(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "s106", "70% Social Rent, 30% Shared Ownership.")

    client = _client_returning(_base_refresh_response(affordable_tenure_split="70% Social Rent, 30% Shared Ownership"))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_tenure_split_final == "70% Social Rent, 30% Shared Ownership"


def test_no_tenure_split_fabricated_when_absent(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app, affordable_tenure_split_final=None)
    _add_document(session, app, "decision_notice", "Granted, no tenure detail stated.")

    client = _client_returning(_base_refresh_response(affordable_tenure_split=None))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_tenure_split_final is None


def test_proposed_tenure_split_distinct_from_legally_secured(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_RECOMMENDATION_MADE)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "officer_report", "Applicant proposes 35% affordable, tenure not yet agreed.")

    client = _client_returning(_base_refresh_response(affordable_percentage=35.0, affordable_housing_status="proposed"))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_housing_status == "proposed"
    assert app.scheme_intelligence.affordable_housing_status != LEGALLY_SECURED_STATUS


def test_later_s106_supersedes_earlier_proposal(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app, affordable_percentage_final=40.0, affordable_housing_status="proposed")
    _add_document(session, app, "s106", "Executed S106 secures 35% affordable housing, a reduction from the original proposal.")

    client = _client_returning(_base_refresh_response(
        affordable_percentage=35.0, affordable_housing_status=LEGALLY_SECURED_STATUS,
        affordable_provision_fully_legally_secured=True,
        affordable_housing_notes="The executed S106 secures 35%, down from the applicant's original 40% proposal.",
    ))
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_percentage_final == 35.0
    assert app.scheme_intelligence.affordable_housing_status == LEGALLY_SECURED_STATUS
    assert "affordable_percentage_changed" in outcome.affordable_housing_changes
    assert "affordable_status_changed" not in outcome.affordable_housing_changes  # went straight to legally_secured, its own label fires instead
    assert "tenure_split_legally_secured" in outcome.affordable_housing_changes


def test_later_deed_of_variation_updates_s106_derived_intelligence(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=None)
    _add_scheme_intelligence(session, app, affordable_percentage_final=35.0, affordable_housing_status=LEGALLY_SECURED_STATUS)
    _add_document(session, app, "s106", "Deed of Variation revises the affordable housing provision to 30%.")

    client = _client_returning(_base_refresh_response(
        affordable_percentage=30.0, affordable_housing_status=LEGALLY_SECURED_STATUS,
        affordable_provision_fully_legally_secured=True,
    ))
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_percentage_final == 30.0
    assert app.scheme_intelligence.affordable_housing_status == LEGALLY_SECURED_STATUS
    assert "affordable_percentage_changed" in outcome.affordable_housing_changes


def test_affordable_percentage_change_surfaced():
    old = MagicMock(affordable_percentage_final=40.0, affordable_units_final=None, affordable_tenure_split_final=None, affordable_housing_status=None)
    changes = detect_affordable_housing_changes(old, {"affordable_percentage_final": 35.0})
    assert "affordable_percentage_changed" in changes


def test_affordable_unit_count_change_surfaced():
    old = MagicMock(affordable_percentage_final=None, affordable_units_final=40, affordable_tenure_split_final=None, affordable_housing_status=None)
    changes = detect_affordable_housing_changes(old, {"affordable_units_final": 35})
    assert "affordable_unit_count_changed" in changes


def test_tenure_split_change_surfaced():
    old = MagicMock(affordable_percentage_final=None, affordable_units_final=None, affordable_tenure_split_final="50/50", affordable_housing_status=None)
    changes = detect_affordable_housing_changes(old, {"affordable_tenure_split_final": "70/30"})
    assert "tenure_split_changed" in changes


def test_tenure_split_newly_agreed_surfaced_even_if_percentage_unchanged():
    old = MagicMock(affordable_percentage_final=35.0, affordable_units_final=None, affordable_tenure_split_final=None, affordable_housing_status=None)
    changes = detect_affordable_housing_changes(old, {"affordable_percentage_final": 35.0, "affordable_tenure_split_final": "70/30"})
    assert "tenure_split_newly_agreed" in changes
    assert "affordable_percentage_changed" not in changes


def test_onsite_to_offsite_change_represented_in_notes(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app, affordable_housing_notes="On-site provision of 35%.")
    _add_document(session, app, "s106", "Revised to off-site commuted sum provision.")

    client = _client_returning(_base_refresh_response(
        affordable_housing_status="conditioned",
        affordable_housing_notes="Provision changed from on-site to an off-site commuted sum.",
    ))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert "off-site" in app.scheme_intelligence.affordable_housing_notes


def test_commuted_sum_represented_where_evidenced(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "s106", "A commuted sum of £500,000 is secured in lieu of on-site affordable housing.")

    client = _client_returning(_base_refresh_response(
        affordable_housing_status=LEGALLY_SECURED_STATUS, affordable_provision_fully_legally_secured=True,
        affordable_housing_notes="A commuted sum of £500,000 is secured in lieu of on-site provision.",
    ))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert "commuted sum" in app.scheme_intelligence.affordable_housing_notes


def test_viability_review_mechanism_represented_where_evidenced(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "s106", "Subject to a viability review at implementation and post-completion.")

    client = _client_returning(_base_refresh_response(
        affordable_housing_status="subject_to_viability_review",
        affordable_housing_notes="A viability review mechanism applies at implementation and post-completion.",
    ))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_housing_status == "subject_to_viability_review"


def test_proposed_provision_not_described_as_legally_secured_in_prompt_rules():
    # Structural check that the prompt's own grounding rules explicitly
    # forbid this - the schema enum alone can't encode a cross-field
    # evidence constraint (Part 12/25).
    prompt = build_refresh_prompt(
        MagicMock(reference="APP/1", address="1 Test St", status="Awaiting decision", decision=None),
        DEPTH_BROAD, None, "evidence text",
    )
    assert "legally_secured" in prompt
    assert "never describe" in prompt.lower() or "never" in prompt.lower()


def test_executed_s106_position_represented_as_legally_secured_where_supported(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "s106", "This executed S106 Agreement legally secures 35% affordable housing.")

    client = _client_returning(_base_refresh_response(
        affordable_percentage=35.0, affordable_housing_status=LEGALLY_SECURED_STATUS,
        affordable_provision_fully_legally_secured=True,
    ))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_housing_status == LEGALLY_SECURED_STATUS


def test_refusal_focused_refresh_does_not_target_unrelated_affordable_fields():
    # Part 16/44 - a focused refusal refresh's own target category set must
    # not include planning_statement/design_access (applicant-proposal-only
    # evidence unrelated to the refusal itself).
    targets = _DOC_TYPES_BY_DEPTH[DEPTH_FOCUSED_REFUSAL]
    assert "planning_statement" not in targets
    assert "design_access" not in targets


def test_withdrawal_focused_refresh_does_not_target_s106():
    targets = _DOC_TYPES_BY_DEPTH[DEPTH_FOCUSED_WITHDRAWAL]
    assert "s106" not in targets


def test_all_affordable_housing_statuses_are_the_approved_vocabulary():
    assert AFFORDABLE_HOUSING_STATUSES == frozenset({
        "proposed", "policy_required", "officer_recommended", "committee_position",
        "agreed", "conditioned", "legally_secured", "subject_to_viability_review", "unknown",
    })


# --- Evidence selection / authority ------------------------------------------


def test_evidence_selection_orders_s106_and_decision_notice_above_planning_statement(session):
    app = _add_application(session, reference="APP/1")
    _add_document(session, app, "planning_statement", "applicant proposal text")
    _add_document(session, app, "s106", "executed legal agreement text")
    docs = select_refresh_evidence_documents([app], DEPTH_BROAD)
    doc_types_in_order = [d.doc_type for d in docs]
    assert doc_types_in_order.index("s106") < doc_types_in_order.index("planning_statement")


def test_evidence_selection_excludes_documents_without_extracted_text(session):
    app = _add_application(session, reference="APP/1")
    doc = Document(application_id=app.id, doc_type="decision_notice", document_name="d.pdf", text_extracted=False, extracted_text=None)
    session.add(doc)
    session.commit()
    docs = select_refresh_evidence_documents([app], DEPTH_BROAD)
    assert docs == []


def test_no_usable_evidence_text_returns_no_usable_text_outcome_and_preserves_intelligence(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app, affordable_percentage_final=20.0)
    # no documents at all for the target categories
    client = _client_returning(_base_refresh_response())
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert outcome.outcome == OUTCOME_NO_USABLE_TEXT
    assert app.scheme_intelligence.affordable_percentage_final == 20.0
    client.responses.create.assert_not_called()  # no LLM call, not billed


# --- 45-56: Site Summary contract --------------------------------------------


def _merged(**overrides) -> dict:
    base = {
        "total_units_final": 100, "developer": "Example Developer",
        "recommendation_direction": None, "formal_decision_outstanding": None,
        "refusal_reasons": None, "withdrawal_reason": None,
        "affordable_housing_status": None, "affordable_housing_notes": None,
        "affordable_percentage_final": None, "affordable_units_final": None, "affordable_tenure_split_final": None,
    }
    base.update(overrides)
    return base


def _site_and_apps():
    site = MagicMock(display_address="1 Test Street", council_code="testcouncil")
    app = Application(
        council_code="testcouncil", reference="APP/1", application_category="full",
        status="Awaiting decision", decision=None, proposal="",
    )
    return site, [app]


def test_recommendation_prompt_distinguishes_from_granted():
    site, apps = _site_and_apps()
    merged = _merged(recommendation_direction="approval", formal_decision_outstanding=True)
    prompt = build_summary_prompt(site, apps, merged, {"status": "on_track", "build_status": "not_started"}, [])
    assert "RECOMMENDATION DIRECTION: approval" in prompt
    assert "formal decision still outstanding" in prompt


def test_refusal_recommendation_prompt_content():
    site, apps = _site_and_apps()
    merged = _merged(recommendation_direction="refusal", formal_decision_outstanding=True)
    prompt = build_summary_prompt(site, apps, merged, {"status": "on_track", "build_status": "not_started"}, [])
    assert "RECOMMENDATION DIRECTION: refusal" in prompt


def test_refusal_reasons_included_when_evidenced():
    site, apps = _site_and_apps()
    merged = _merged(refusal_reasons="Overdevelopment and loss of amenity.")
    prompt = build_summary_prompt(site, apps, merged, {"status": "on_track", "build_status": "not_started"}, [])
    assert "Overdevelopment and loss of amenity." in prompt


def test_refusal_reasons_absent_not_invented():
    site, apps = _site_and_apps()
    merged = _merged(refusal_reasons=None)
    prompt = build_summary_prompt(site, apps, merged, {"status": "on_track", "build_status": "not_started"}, [])
    assert "REFUSAL REASONS (evidenced):" not in prompt  # the grounded fact line, not the generic instruction


def test_affordable_status_included_only_when_material():
    site, apps = _site_and_apps()
    merged = _merged()  # nothing set
    prompt = build_summary_prompt(site, apps, merged, {"status": "on_track", "build_status": "not_started"}, [])
    assert "AFFORDABLE HOUSING STATUS:" not in prompt  # the grounded fact line, not the generic instruction


def test_affordable_percentage_included_correctly_when_material():
    site, apps = _site_and_apps()
    merged = _merged(affordable_housing_status="agreed", affordable_percentage_final=35.0, affordable_units_final=35, affordable_tenure_split_final="70/30")
    prompt = build_summary_prompt(site, apps, merged, {"status": "on_track", "build_status": "not_started"}, [])
    assert "AFFORDABLE HOUSING STATUS: agreed" in prompt
    assert "35.0%" in prompt or "35%" in prompt


def test_proposed_tenure_not_described_as_secured_in_prompt_instructions():
    site, apps = _site_and_apps()
    merged = _merged(affordable_housing_status="proposed")
    prompt = build_summary_prompt(site, apps, merged, {"status": "on_track", "build_status": "not_started"}, [])
    assert "NEVER" in prompt
    assert "legally_secured" in prompt


def test_legally_secured_position_represented_correctly():
    site, apps = _site_and_apps()
    merged = _merged(affordable_housing_status=LEGALLY_SECURED_STATUS, affordable_percentage_final=35.0)
    prompt = build_summary_prompt(site, apps, merged, {"status": "on_track", "build_status": "not_started"}, [])
    assert "AFFORDABLE HOUSING STATUS: legally_secured" in prompt


def test_summary_target_length_instruction_is_two_to_five_sentences():
    site, apps = _site_and_apps()
    merged = _merged()
    prompt = build_summary_prompt(site, apps, merged, {"status": "on_track", "build_status": "not_started"}, [])
    assert "2-5 sentences" in prompt


def test_withdrawal_reason_included_when_evidenced():
    site, apps = _site_and_apps()
    merged = _merged(withdrawal_reason="Applicant withdrew following objections.")
    prompt = build_summary_prompt(site, apps, merged, {"status": "on_track", "build_status": "not_started"}, [])
    assert "Applicant withdrew following objections." in prompt


def test_affordable_housing_notes_included_when_present():
    site, apps = _site_and_apps()
    merged = _merged(affordable_housing_status="agreed", affordable_housing_notes="Changed from 40% to 35% following negotiation.")
    prompt = build_summary_prompt(site, apps, merged, {"status": "on_track", "build_status": "not_started"}, [])
    assert "Changed from 40% to 35%" in prompt


def test_merged_scheme_fields_includes_b3_fields():
    from app.ui.common import MERGED_SCHEME_FIELDS
    for field in (
        "recommendation_direction", "formal_decision_outstanding", "refusal_reasons",
        "withdrawal_reason", "affordable_housing_status", "affordable_housing_notes", "latest_material_event",
    ):
        assert field in MERGED_SCHEME_FIELDS


# --- stage_intelligence_refresh wiring + regression --------------------------


def test_stage_intelligence_refresh_processes_newest_material_evidence_first(session):
    from app.pipeline.run_weekly import stage_intelligence_refresh

    now = dt.datetime.now(dt.timezone.utc)
    older = _add_application(session, reference="APP/OLDER", evidence_refresh_reason=REASON_DECISION_GRANTED, material_evidence_changed_at=now - dt.timedelta(days=1))
    newer = _add_application(session, reference="APP/NEWER", evidence_refresh_reason=REASON_DECISION_GRANTED, material_evidence_changed_at=now)
    _add_scheme_intelligence(session, older)
    _add_scheme_intelligence(session, newer)
    _add_document(session, older, "decision_notice", "Granted.")
    _add_document(session, newer, "decision_notice", "Granted.")

    processed_order = []

    def fake_refresh(session_, client_, application, generate_summary=None):
        processed_order.append(application.reference)
        from app.extraction.intelligence_refresh import RefreshOutcome
        return RefreshOutcome(outcome=OUTCOME_SUCCESS)

    import app.pipeline.run_weekly as run_weekly_module
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.extraction.intelligence_refresh.refresh_intelligence_for_application", fake_refresh)
        council = CouncilConfig(
            code="testcouncil", name="testcouncil", base_url="https://example.invalid",
            date_field_mode="received", doc_system="idox", anite_base_url=None,
            unit_threshold=10, region=None, country=None,
        )
        stage_intelligence_refresh(session, MagicMock(), council)

    assert processed_order == ["APP/NEWER", "APP/OLDER"]


def test_stage_intelligence_refresh_respects_limit(session):
    from app.pipeline.run_weekly import stage_intelligence_refresh

    now = dt.datetime.now(dt.timezone.utc)
    for i in range(3):
        app = _add_application(session, reference=f"APP/{i}", evidence_refresh_reason=REASON_DECISION_GRANTED, material_evidence_changed_at=now)
        _add_scheme_intelligence(session, app)
        _add_document(session, app, "decision_notice", "Granted.")

    call_count = 0

    def fake_refresh(session_, client_, application, generate_summary=None):
        nonlocal call_count
        call_count += 1
        from app.extraction.intelligence_refresh import RefreshOutcome
        return RefreshOutcome(outcome=OUTCOME_SUCCESS)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.extraction.intelligence_refresh.refresh_intelligence_for_application", fake_refresh)
        council = CouncilConfig(
            code="testcouncil", name="testcouncil", base_url="https://example.invalid",
            date_field_mode="received", doc_system="idox", anite_base_url=None,
            unit_threshold=10, region=None, country=None,
        )
        result = stage_intelligence_refresh(session, MagicMock(), council, limit=2)

    assert call_count == 2
    assert result.attempted == 2
    assert result.succeeded == 2


def test_daily_discovery_stages_never_import_intelligence_refresh_at_module_level():
    """Structural proof B3 stays inside Intelligence Processing, never Daily
    Discovery (Part 29) - app.extraction.intelligence_refresh is only ever
    imported LAZILY inside stage_intelligence_refresh itself, never at
    run_weekly.py's own top level (which would make it load-bearing for
    every Daily Discovery invocation too)."""
    import inspect

    import app.pipeline.run_weekly as run_weekly_module
    source = inspect.getsource(run_weekly_module)
    top_level_imports = "\n".join(
        line for line in source.split("\n")
        if line.startswith("from app.extraction.intelligence_refresh") or line.startswith("import app.extraction.intelligence_refresh")
    )
    assert top_level_imports == ""


def test_process_intelligence_backlog_records_refresh_counters(session, monkeypatch):
    from scripts.run_intelligence_processing import process_intelligence_backlog

    now = dt.datetime.now(dt.timezone.utc)
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED, material_evidence_changed_at=now)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")

    council = CouncilConfig(
        code="testcouncil", name="testcouncil", base_url="https://example.invalid",
        date_field_mode="received", doc_system="idox", anite_base_url=None,
        unit_threshold=10, region=None, country=None,
    )
    fake_client = _client_returning(_base_refresh_response())

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    run = process_intelligence_backlog(
        session, {"testcouncil": council}, ["testcouncil"],
        max_extractions=0, max_summaries=0, max_intelligence_refresh=5,
        client_factory=lambda api_key: fake_client,
    )

    assert run.refresh_attempted == 1
    assert run.refresh_succeeded == 1
    assert run.status == "success"


# ==============================================================================
# PR B3 FINAL pre-merge amendment: Schema Reconciliation +
# Affordable Housing Change Narrative
# ==============================================================================

# --- Schema reconciliation ----------------------------------------------------

_B3_APPLICATION_FIELDS = frozenset({"intelligence_evidence_processed_at"})
_B3_SCHEME_INTELLIGENCE_FIELDS = frozenset({
    "latest_material_event", "recommendation_direction", "formal_decision_outstanding",
    "refusal_reasons", "withdrawal_reason", "affordable_housing_status", "affordable_housing_notes",
})
_B3_INTELLIGENCE_RUN_FIELDS = frozenset({
    "refresh_candidates_inspected", "refresh_attempted", "refresh_succeeded", "refresh_failed",
})


def test_b3_application_column_count_is_1():
    assert len(_B3_APPLICATION_FIELDS) == 1
    for name in _B3_APPLICATION_FIELDS:
        assert hasattr(Application, name)


def test_b3_scheme_intelligence_column_count_is_7():
    assert len(_B3_SCHEME_INTELLIGENCE_FIELDS) == 7
    for name in _B3_SCHEME_INTELLIGENCE_FIELDS:
        assert hasattr(SchemeIntelligence, name)


def test_b3_intelligence_run_column_count_is_4():
    from app.db.models import IntelligenceRun
    assert len(_B3_INTELLIGENCE_RUN_FIELDS) == 4
    for name in _B3_INTELLIGENCE_RUN_FIELDS:
        assert hasattr(IntelligenceRun, name)


def test_b3_total_persisted_column_count_is_12():
    total = len(_B3_APPLICATION_FIELDS) + len(_B3_SCHEME_INTELLIGENCE_FIELDS) + len(_B3_INTELLIGENCE_RUN_FIELDS)
    assert total == 12  # 1 + 7 + 4 - the previous report's "8" was a plain arithmetic/reporting error


def test_b3_columns_are_nullable_or_safely_integer_defaulted():
    """Every B3 Application/SchemeIntelligence column must be nullable
    (String/Text/DateTime/Boolean, no server-side default needed); every B3
    IntelligenceRun column is an Integer with a Python-side default=0 - the
    same established, already-migration-safe pattern as every other counter
    on that model (e.g. extractions_attempted)."""
    from sqlalchemy import inspect as sa_inspect

    from app.db.models import IntelligenceRun

    for model, fields in (
        (Application, _B3_APPLICATION_FIELDS),
        (SchemeIntelligence, _B3_SCHEME_INTELLIGENCE_FIELDS),
    ):
        mapper = sa_inspect(model)
        for name in fields:
            column = mapper.columns[name]
            assert column.nullable is True, f"{model.__name__}.{name} must be nullable"

    mapper = sa_inspect(IntelligenceRun)
    for name in _B3_INTELLIGENCE_RUN_FIELDS:
        column = mapper.columns[name]
        assert column.nullable is False
        assert column.default is not None and column.default.arg == 0


def test_b3_schema_covered_by_generic_add_missing_columns_no_new_backfill():
    """Structural proof migration stays additive/safe (Part 3/14 of the
    amendment) - no new backfill function was introduced for any B3 column;
    app.db.session._add_missing_columns' existing generic ADD COLUMN
    mechanism is sufficient (same treatment as B1/B2's own reason/trigger/
    requested_at/evidence_refresh_last_outcome fields, which also needed no
    backfill)."""
    import inspect as py_inspect

    import app.db.session as db_session_module
    source = py_inspect.getsource(db_session_module)
    for name in _B3_APPLICATION_FIELDS | _B3_SCHEME_INTELLIGENCE_FIELDS | _B3_INTELLIGENCE_RUN_FIELDS:
        assert f"_backfill_{name}" not in source


# --- Affordable housing change narrative --------------------------------------


def test_35_percent_proposed_to_20_percent_legally_secured_preserves_movement(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app, affordable_percentage_final=35.0, affordable_housing_status="proposed")
    _add_document(session, app, "s106", "Executed S106 secures 20% affordable housing.")

    client = _client_returning(_base_refresh_response(
        affordable_percentage=20.0, affordable_housing_status=LEGALLY_SECURED_STATUS,
        affordable_provision_fully_legally_secured=True,
        affordable_housing_notes="Affordable housing reduced from 35% to 20%, now legally secured through the executed S106.",
    ))
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_percentage_final == 20.0
    assert app.scheme_intelligence.affordable_housing_status == LEGALLY_SECURED_STATUS
    assert "35%" in app.scheme_intelligence.affordable_housing_notes and "20%" in app.scheme_intelligence.affordable_housing_notes
    assert "affordable_percentage_changed" in outcome.affordable_housing_changes


def test_35_percent_proposed_to_35_percent_legally_secured_identifies_security_progression(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app, affordable_percentage_final=35.0, affordable_housing_status="proposed")
    _add_document(session, app, "s106", "Executed S106 secures the previously proposed 35% affordable housing.")

    client = _client_returning(_base_refresh_response(
        affordable_percentage=35.0, affordable_housing_status=LEGALLY_SECURED_STATUS,
        affordable_provision_fully_legally_secured=True,
        affordable_housing_notes="The previously proposed 35% affordable provision is now legally secured through the executed S106.",
    ))
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_percentage_final == 35.0  # unchanged number
    assert app.scheme_intelligence.affordable_housing_status == LEGALLY_SECURED_STATUS
    assert "secured" in app.scheme_intelligence.affordable_housing_notes.lower()
    assert "tenure_split_legally_secured" in outcome.affordable_housing_changes
    assert "affordable_percentage_changed" not in outcome.affordable_housing_changes  # number itself didn't move


def test_tenure_unknown_to_60_40_agreed_identifies_newly_agreed(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_RECOMMENDATION_MADE)
    _add_scheme_intelligence(session, app, affordable_tenure_split_final=None, affordable_housing_status="proposed")
    _add_document(session, app, "officer_report", "Officers report the tenure split is now agreed at 60% Social Rent / 40% Shared Ownership.")

    client = _client_returning(_base_refresh_response(
        affordable_tenure_split="60% Social Rent / 40% Shared Ownership", affordable_housing_status="agreed",
        affordable_housing_notes="The tenure split is now agreed at 60/40, previously unknown.",
    ))
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_tenure_split_final == "60% Social Rent / 40% Shared Ownership"
    assert "tenure_split_newly_agreed" in outcome.affordable_housing_changes


def test_70_30_proposed_to_60_40_legally_secured_retains_material_change(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app, affordable_tenure_split_final="70/30", affordable_housing_status="proposed")
    _add_document(session, app, "s106", "Executed S106 secures a 60/40 affordable housing tenure split, differing from the applicant's earlier 70/30 proposal.")

    client = _client_returning(_base_refresh_response(
        affordable_tenure_split="60/40", affordable_housing_status=LEGALLY_SECURED_STATUS,
        affordable_housing_notes="The final secured tenure mix differs from the earlier 70/30 proposal and is now 60/40.",
    ))
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_tenure_split_final == "60/40"
    assert "70/30" in app.scheme_intelligence.affordable_housing_notes
    assert "tenure_split_changed" in outcome.affordable_housing_changes


def test_20_secured_to_15_via_deed_of_variation_retains_narrative(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=None)
    _add_scheme_intelligence(session, app, affordable_percentage_final=20.0, affordable_housing_status=LEGALLY_SECURED_STATUS)
    _add_document(session, app, "s106", "A later Deed of Variation reduces the secured affordable provision from 20% to 15%.")

    client = _client_returning(_base_refresh_response(
        affordable_percentage=15.0, affordable_housing_status=LEGALLY_SECURED_STATUS,
        affordable_housing_notes="A later Deed of Variation reduces the secured affordable provision from 20% to 15%.",
    ))
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_percentage_final == 15.0
    assert "affordable_percentage_changed" in outcome.affordable_housing_changes
    assert "20%" in app.scheme_intelligence.affordable_housing_notes and "15%" in app.scheme_intelligence.affordable_housing_notes


def test_lower_authority_later_document_does_not_overwrite_secured_position(session):
    # Part 10's own example: executed S106 already secured 20%; a LATER,
    # lower-authority document (this pass's own evidence has no s106/
    # decision_notice at all) claims 35% - must NOT overwrite the secured
    # position, regardless of what the (mocked, deliberately "wrong") LLM
    # response says.
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=None)
    _add_scheme_intelligence(
        session, app, affordable_percentage_final=20.0, affordable_housing_status=LEGALLY_SECURED_STATUS,
        affordable_tenure_split_final="60/40", affordable_housing_notes="Secured at 20% via executed S106.",
    )
    _add_document(session, app, "planning_statement", "A later marketing planning statement claims 35% affordable housing.")

    client = _client_returning(_base_refresh_response(
        affordable_percentage=35.0, affordable_housing_status="proposed",
        affordable_housing_notes="Now proposing 35%, up from the previous 20%.",
    ))
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_percentage_final == 20.0  # guarded - unchanged
    assert app.scheme_intelligence.affordable_housing_status == LEGALLY_SECURED_STATUS
    assert app.scheme_intelligence.affordable_tenure_split_final == "60/40"
    assert app.scheme_intelligence.affordable_housing_notes == "Secured at 20% via executed S106."  # untouched
    assert "affordable_percentage_changed" not in outcome.affordable_housing_changes


def test_legally_authoritative_document_can_revise_secured_position(session):
    # Sanity counterpart - the guard must NOT block a genuine s106/decision_
    # notice-backed revision (e.g. a real Deed of Variation), only a
    # lower-authority one.
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=None)
    _add_scheme_intelligence(session, app, affordable_percentage_final=20.0, affordable_housing_status=LEGALLY_SECURED_STATUS)
    _add_document(session, app, "s106", "Deed of Variation revises the secured provision to 15%.")

    client = _client_returning(_base_refresh_response(
        affordable_percentage=15.0, affordable_housing_status=LEGALLY_SECURED_STATUS,
        affordable_provision_fully_legally_secured=True,
    ))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_percentage_final == 15.0  # guard did not block a legitimate revision
    assert app.scheme_intelligence.affordable_housing_status == LEGALLY_SECURED_STATUS


def test_unchanged_affordable_position_does_not_fabricate_change_narrative():
    old = MagicMock(affordable_percentage_final=35.0, affordable_units_final=40, affordable_tenure_split_final="70/30", affordable_housing_status="agreed")
    new_fields = {
        "affordable_percentage_final": 35.0, "affordable_units_final": 40,
        "affordable_tenure_split_final": "70/30", "affordable_housing_status": "agreed",
    }
    assert detect_affordable_housing_changes(old, new_fields) == []


def test_missing_prior_affordable_data_does_not_invent_comparison(session):
    from app.extraction.intelligence_refresh import _fmt_existing_position

    assert _fmt_existing_position(None) == "(no prior AI intelligence exists for this application yet)"

    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    # No SchemeIntelligence row exists at all - a first-ever B3 pass.
    _add_document(session, app, "decision_notice", "Granted, 35% affordable housing secured.")

    client = _client_returning(_base_refresh_response(affordable_percentage=35.0, affordable_housing_status=LEGALLY_SECURED_STATUS))
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert outcome.outcome == OUTCOME_SUCCESS
    assert app.scheme_intelligence.affordable_percentage_final == 35.0
    assert outcome.affordable_housing_changes == []  # nothing to compare against - no fabricated "change"


def test_notes_replaced_not_appended_across_successive_refreshes(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED, material_evidence_changed_at=dt.datetime.now(dt.timezone.utc))
    _add_scheme_intelligence(session, app, affordable_percentage_final=35.0, affordable_housing_status="proposed")
    _add_document(session, app, "s106", "Executed S106 secures 25% affordable housing.")

    client_1 = _client_returning(_base_refresh_response(
        affordable_percentage=25.0, affordable_housing_status=LEGALLY_SECURED_STATUS,
        affordable_housing_notes="Reduced from 35% to 25%, now legally secured.",
    ))
    refresh_intelligence_for_application(session, client_1, app, generate_summary=_summary_stub())
    first_notes = app.scheme_intelligence.affordable_housing_notes

    # Second pass - a Deed of Variation further revises the position. The
    # new notes must REPLACE the first, not have the first note appended.
    app.material_evidence_changed_at = dt.datetime.now(dt.timezone.utc)
    _add_document(session, app, "s106", "Deed of Variation reduces to 20%.")
    client_2 = _client_returning(_base_refresh_response(
        affordable_percentage=20.0, affordable_housing_status=LEGALLY_SECURED_STATUS,
        affordable_housing_notes="A later Deed of Variation reduces the secured provision from 25% to 20%.",
    ))
    refresh_intelligence_for_application(session, client_2, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_housing_notes != first_notes
    assert first_notes not in app.scheme_intelligence.affordable_housing_notes  # not concatenated/appended
    assert "20%" in app.scheme_intelligence.affordable_housing_notes


def test_site_summary_surfaces_material_affordable_change():
    site, apps = _site_and_apps()
    merged = _merged(
        affordable_housing_status=LEGALLY_SECURED_STATUS, affordable_percentage_final=20.0,
        affordable_housing_notes="Reduced from the earlier 35% proposal to 20%, now legally secured.",
    )
    prompt = build_summary_prompt(site, apps, merged, {"status": "on_track", "build_status": "not_started"}, [])
    assert "Reduced from the earlier 35% proposal to 20%" in prompt


def test_site_summary_does_not_surface_comparison_when_no_notes_present():
    site, apps = _site_and_apps()
    merged = _merged(affordable_housing_status="agreed", affordable_percentage_final=35.0)  # no notes set
    prompt = build_summary_prompt(site, apps, merged, {"status": "on_track", "build_status": "not_started"}, [])
    assert "AFFORDABLE HOUSING NOTES" not in prompt


# --- Atomic replacement regression reconfirmation ----------------------------


def test_failed_summary_preserves_old_affordable_notes(session):
    site = Site(council_code="testcouncil", canonical_address="2 test street", display_address="2 Test Street")
    session.add(site)
    session.commit()
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED, site_id=site.id)
    _add_scheme_intelligence(session, app, affordable_percentage_final=20.0, affordable_housing_notes="Secured at 20%.")
    _add_document(session, app, "s106", "Deed of Variation reduces to 15%.")

    client = _client_returning(_base_refresh_response(
        affordable_percentage=15.0, affordable_housing_notes="Reduced from 20% to 15%.",
    ))
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub(raise_error=True))

    assert outcome.outcome == OUTCOME_ERROR
    assert app.scheme_intelligence.affordable_percentage_final == 20.0
    assert app.scheme_intelligence.affordable_housing_notes == "Secured at 20%."


def test_successful_replacement_commits_notes_status_summary_and_watermark_together(session):
    site = Site(council_code="testcouncil", canonical_address="3 test street", display_address="3 Test Street")
    session.add(site)
    session.commit()
    now = dt.datetime.now(dt.timezone.utc)
    app = _add_application(
        session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED,
        site_id=site.id, material_evidence_changed_at=now,
    )
    _add_scheme_intelligence(session, app, affordable_percentage_final=35.0, affordable_housing_status="proposed")
    _add_document(session, app, "s106", "Executed S106 secures 20% affordable housing.")

    client = _client_returning(_base_refresh_response(
        affordable_percentage=20.0, affordable_housing_status=LEGALLY_SECURED_STATUS,
        affordable_provision_fully_legally_secured=True,
        affordable_housing_notes="Reduced from 35% to 20%, now secured.",
    ))
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub("Fresh summary"))

    assert outcome.outcome == OUTCOME_SUCCESS
    assert app.scheme_intelligence.affordable_percentage_final == 20.0
    assert app.scheme_intelligence.affordable_housing_status == LEGALLY_SECURED_STATUS
    assert app.scheme_intelligence.affordable_housing_notes == "Reduced from 35% to 20%, now secured."
    assert site.status_summary == "Fresh summary"
    assert app.intelligence_evidence_processed_at == now


# ==============================================================================
# B3 LIVE VALIDATION AMENDMENT: Site Summary prospective state + formal
# decision semantics + broad affordable evidence
#
# The first controlled live sample (Oldham FUL/354904/25) exposed three
# narrow defects, fixed here:
#   A. Site Summary was generated from STALE pre-refresh intelligence.
#   B. formal_decision_outstanding conflated "no formal decision issued"
#      with "S106 not executed / conditions outstanding".
#   C. DEPTH_BROAD omitted viability_affordable_housing evidence.
# Plus an affordable-unit-reconciliation prompt strengthening.
# ==============================================================================

# --- Defect A: prospective Site Summary state --------------------------------


def test_default_summary_receives_prospective_new_intelligence_values(session, monkeypatch):
    captured = {}

    def fake_generate_scheme_summary(client, site, applications, merged, lapse, phase_breakdown):
        captured["merged"] = dict(merged)
        return "New summary reflecting the fresh affordable housing position."

    monkeypatch.setattr("app.reporting.scheme_summary.generate_scheme_summary", fake_generate_scheme_summary)

    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED, site_id=site.id)
    _add_scheme_intelligence(session, app, affordable_housing_notes="Old notes, no affordable detail.")
    _add_document(session, app, "decision_notice", "Granted, 40% affordable housing secured.")

    client = _client_returning(_base_refresh_response(
        affordable_percentage=40.0, affordable_housing_status="agreed",
        affordable_housing_notes="40% affordable housing is now agreed.",
    ))
    outcome = refresh_intelligence_for_application(session, client, app)  # generate_summary=None -> default path

    assert outcome.outcome == OUTCOME_SUCCESS
    assert captured["merged"]["affordable_housing_notes"] == "40% affordable housing is now agreed."
    assert captured["merged"]["affordable_housing_status"] == "agreed"


def test_default_summary_receives_prospective_planning_outcome_fields(session, monkeypatch):
    captured = {}

    def fake_generate_scheme_summary(client, site, applications, merged, lapse, phase_breakdown):
        captured["merged"] = dict(merged)
        return "New summary."

    monkeypatch.setattr("app.reporting.scheme_summary.generate_scheme_summary", fake_generate_scheme_summary)

    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_REFUSED, site_id=site.id)
    _add_scheme_intelligence(session, app, recommendation_direction=None)
    _add_document(session, app, "decision_notice", "The application is refused due to overdevelopment.")

    client = _client_returning(_base_refresh_response(
        recommendation_direction="refusal", formal_decision_outstanding=False,
        refusal_reasons="Overdevelopment.",
    ))
    refresh_intelligence_for_application(session, client, app)

    assert captured["merged"]["recommendation_direction"] == "refusal"
    assert captured["merged"]["formal_decision_outstanding"] is False
    assert captured["merged"]["refusal_reasons"] == "Overdevelopment."


def test_real_orm_scheme_intelligence_not_mutated_before_summary_call(session, monkeypatch):
    observed = {}

    def fake_generate_scheme_summary(client, site, applications, merged, lapse, phase_breakdown):
        observed["live_pct_during_call"] = applications[0].scheme_intelligence.affordable_percentage_final
        return "New summary."

    monkeypatch.setattr("app.reporting.scheme_summary.generate_scheme_summary", fake_generate_scheme_summary)

    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED, site_id=site.id)
    _add_scheme_intelligence(session, app, affordable_percentage_final=20.0)
    _add_document(session, app, "decision_notice", "Granted, 40% affordable housing secured.")

    client = _client_returning(_base_refresh_response(affordable_percentage=40.0, affordable_housing_status="agreed"))
    refresh_intelligence_for_application(session, client, app)

    assert observed["live_pct_during_call"] == 20.0  # still old at the moment the summary call happens
    assert app.scheme_intelligence.affordable_percentage_final == 40.0  # mutated only after both steps succeed


def test_default_summary_failure_preserves_old_intelligence_and_site_summary(session, monkeypatch):
    def failing_generate_scheme_summary(client, site, applications, merged, lapse, phase_breakdown):
        raise RuntimeError("summary generation failed")

    monkeypatch.setattr("app.reporting.scheme_summary.generate_scheme_summary", failing_generate_scheme_summary)

    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED, site_id=site.id)
    site.status_summary = "Old summary"
    _add_scheme_intelligence(session, app, affordable_percentage_final=20.0)
    _add_document(session, app, "decision_notice", "Granted, 40% affordable housing secured.")
    session.commit()

    client = _client_returning(_base_refresh_response(affordable_percentage=99.0))
    outcome = refresh_intelligence_for_application(session, client, app)

    assert outcome.outcome == OUTCOME_ERROR
    assert app.scheme_intelligence.affordable_percentage_final == 20.0
    assert site.status_summary == "Old summary"


def test_default_successful_path_commits_intelligence_summary_watermark_together(session, monkeypatch):
    def fake_generate_scheme_summary(client, site, applications, merged, lapse, phase_breakdown):
        return "Fresh summary mentioning 40% affordable housing."

    monkeypatch.setattr("app.reporting.scheme_summary.generate_scheme_summary", fake_generate_scheme_summary)

    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    now = dt.datetime.now(dt.timezone.utc)
    app = _add_application(
        session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED,
        site_id=site.id, material_evidence_changed_at=now,
    )
    _add_scheme_intelligence(session, app, affordable_percentage_final=20.0)
    _add_document(session, app, "decision_notice", "Granted, 40% affordable housing secured.")

    client = _client_returning(_base_refresh_response(affordable_percentage=40.0, affordable_housing_status="agreed"))
    outcome = refresh_intelligence_for_application(session, client, app)

    assert outcome.outcome == OUTCOME_SUCCESS
    assert app.scheme_intelligence.affordable_percentage_final == 40.0
    assert site.status_summary == "Fresh summary mentioning 40% affordable housing."
    assert app.intelligence_evidence_processed_at == now


def test_aggregate_scheme_fields_default_prospective_overrides_backward_compatible(session):
    from app.ui.common import aggregate_scheme_fields

    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app, affordable_percentage_final=20.0)

    merged_positional = aggregate_scheme_fields([app])
    merged_explicit_none = aggregate_scheme_fields([app], prospective_overrides=None)
    assert merged_positional == merged_explicit_none
    assert merged_positional["affordable_percentage_final"] == 20.0


def test_aggregate_scheme_fields_prospective_override_applies_only_to_target_application(session):
    from app.ui.common import aggregate_scheme_fields

    app1 = _add_application(session, reference="APP/1", application_received="Mon 01 Jan 2025")
    app2 = _add_application(session, reference="APP/2", application_received="Mon 01 Jan 2024")
    _add_scheme_intelligence(session, app1, affordable_percentage_final=20.0, core_intelligence_complete=True)
    _add_scheme_intelligence(session, app2, affordable_percentage_final=99.0, core_intelligence_complete=True)

    merged = aggregate_scheme_fields([app1, app2], prospective_overrides={app1.id: {"affordable_percentage_final": 40.0}})

    assert merged["affordable_percentage_final"] == 40.0  # app1's prospective value, not its real 20.0
    assert app2.scheme_intelligence.affordable_percentage_final == 99.0  # sibling's live value untouched


def test_aggregate_scheme_fields_prospective_override_works_with_no_existing_intelligence(session):
    from app.ui.common import aggregate_scheme_fields

    app = _add_application(session, reference="APP/1")  # no SchemeIntelligence row at all yet
    merged = aggregate_scheme_fields([app], prospective_overrides={app.id: {"affordable_housing_status": "agreed"}})
    assert merged["affordable_housing_status"] == "agreed"


# --- Defect B: formal_decision_outstanding semantics --------------------------


def test_prompt_defines_formal_decision_outstanding_separately_from_s106_and_conditions():
    prompt = build_refresh_prompt(
        MagicMock(reference="APP/1", address="1 Test St", status="Awaiting decision", decision=None),
        DEPTH_BROAD, None, "evidence text",
    )
    assert "S106 has been" in prompt
    assert "conditions remain outstanding" in prompt
    assert "ready to" in prompt and "implement" in prompt


def test_prompt_instructs_decision_notice_sets_outstanding_false_despite_awaiting_status():
    prompt = build_refresh_prompt(
        MagicMock(reference="APP/1", address="1 Test St", status="Awaiting decision", decision="Granted, subject to legal agreement"),
        DEPTH_BROAD, None, "NOTICE OF APPROVAL OF PLANNING PERMISSION",
    )
    assert "formal_decision_outstanding=false" in prompt
    assert "Awaiting decision" in prompt
    assert "Granted, subject to legal agreement" in prompt
    assert "S106 execution is not evidenced" in prompt


def test_prompt_instructs_recommendation_alone_leaves_decision_outstanding_true():
    prompt = build_refresh_prompt(
        MagicMock(reference="APP/1", address="1 Test St", status="Awaiting decision", decision=None),
        DEPTH_RECOMMENDATION, None, "Officers recommend approval subject to conditions.",
    )
    assert "recommendation is never itself a formal decision" in prompt


def test_formal_decision_false_with_decision_notice_does_not_imply_legal_security(session):
    app = _add_application(
        session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED,
        status="Awaiting decision", decision="Granted, subject to legal agreement",
    )
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "NOTICE OF APPROVAL OF PLANNING PERMISSION. Conditions attached.")

    client = _client_returning(_base_refresh_response(formal_decision_outstanding=False, affordable_housing_status="proposed"))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.formal_decision_outstanding is False
    assert app.scheme_intelligence.affordable_housing_status == "proposed"
    assert app.scheme_intelligence.affordable_housing_status != LEGALLY_SECURED_STATUS


def test_decision_outcome_unknown_with_no_formal_evidence_not_guessed(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_OUTCOME_UNKNOWN, status="Decided")
    _add_scheme_intelligence(session, app, formal_decision_outstanding=None)
    _add_document(session, app, "officer_report", "Status shows Decided but no formal outcome document is available.")

    client = _client_returning(_base_refresh_response(formal_decision_outstanding=None))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.formal_decision_outstanding is None  # left as recorded, not guessed


def test_formal_refusal_notice_sets_decision_not_outstanding(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_REFUSED, decision="Refused")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "NOTICE OF REFUSAL OF PLANNING PERMISSION.")

    client = _client_returning(_base_refresh_response(formal_decision_outstanding=False, refusal_reasons="Overdevelopment."))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.formal_decision_outstanding is False


def test_s106_absence_does_not_by_itself_set_decision_outstanding(session):
    # Decision Notice present but no s106 document at all this pass - the
    # formal decision itself is still evidenced, so formal_decision_
    # outstanding must be allowed False purely on the Decision Notice's own
    # presence, independent of S106 evidence availability.
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "NOTICE OF APPROVAL OF PLANNING PERMISSION.")

    client = _client_returning(_base_refresh_response(formal_decision_outstanding=False))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.formal_decision_outstanding is False


# --- Defect C: broad refresh includes dedicated affordable evidence ----------


def test_depth_broad_includes_viability_affordable_housing():
    assert "viability_affordable_housing" in _DOC_TYPES_BY_DEPTH[DEPTH_BROAD]


def test_viability_affordable_housing_document_selected_at_broad_depth(session):
    app = _add_application(session, reference="APP/1")
    _add_document(session, app, "viability_affordable_housing", "Affordable Housing Statement: 40% affordable, tenure split 60/40.")
    docs = select_refresh_evidence_documents([app], DEPTH_BROAD)
    assert any(d.doc_type == "viability_affordable_housing" for d in docs)


def test_focused_refusal_depth_does_not_include_viability_affordable_housing():
    assert "viability_affordable_housing" not in _DOC_TYPES_BY_DEPTH[DEPTH_FOCUSED_REFUSAL]


def test_focused_withdrawal_depth_does_not_include_viability_affordable_housing():
    assert "viability_affordable_housing" not in _DOC_TYPES_BY_DEPTH[DEPTH_FOCUSED_WITHDRAWAL]


def test_other_depths_do_not_include_viability_affordable_housing():
    for depth in (DEPTH_RECOMMENDATION, DEPTH_DECISION_RESOLUTION, DEPTH_UNIT_CHANGE):
        assert "viability_affordable_housing" not in _DOC_TYPES_BY_DEPTH[depth]


def test_broad_refresh_with_viability_document_still_respects_context_cap(session):
    from app.extraction.intelligence_refresh import MAX_REFRESH_CONTEXT_CHARS
    from app.extraction.pdf_text import build_combined_priority_text

    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted. " * 20000)
    _add_document(session, app, "viability_affordable_housing", "Affordable statement. " * 20000)

    docs = select_refresh_evidence_documents([app], DEPTH_BROAD)
    doc_tuples = [(d.doc_type, d.document_name or "", d.extracted_text or "") for d in docs]
    evidence_text = build_combined_priority_text(doc_tuples, max_total_chars=MAX_REFRESH_CONTEXT_CHARS)
    # build_combined_priority_text appends a fixed "[COMBINED TEXT TRUNCATED]"
    # marker AFTER slicing to the remaining budget (pre-existing, shared
    # extraction-pipeline behaviour - see app.extraction.pdf_text - not
    # reopened by this amendment), so the true bound is the cap plus that
    # marker's own length, not an exact cap.
    assert len(evidence_text) <= MAX_REFRESH_CONTEXT_CHARS + len("\n[COMBINED TEXT TRUNCATED]")
    assert "[COMBINED TEXT TRUNCATED]" in evidence_text  # confirms the cap was actually hit, not skipped


def test_viability_affordable_housing_alone_cannot_downgrade_legally_secured_position(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=None)
    _add_scheme_intelligence(
        session, app, affordable_percentage_final=20.0, affordable_housing_status=LEGALLY_SECURED_STATUS,
        affordable_housing_notes="Secured at 20% via executed S106.",
    )
    _add_document(session, app, "viability_affordable_housing", "Updated Affordable Housing Statement now proposes 35%.")

    client = _client_returning(_base_refresh_response(
        affordable_percentage=35.0, affordable_housing_status="proposed",
        affordable_housing_notes="Now proposing 35%.",
    ))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_percentage_final == 20.0  # guarded, unchanged
    assert app.scheme_intelligence.affordable_housing_status == LEGALLY_SECURED_STATUS


# --- Affordable unit reconciliation -------------------------------------------


def test_prompt_instructs_unit_breakdown_reconciliation_or_explicit_partial_flag():
    prompt = build_refresh_prompt(
        MagicMock(reference="APP/1", address="1 Test St", status="Awaiting decision", decision=None),
        DEPTH_BROAD, None, "evidence text",
    )
    assert "AFFORDABLE UNIT RECONCILIATION" in prompt
    assert "does not account for" in prompt


def test_reconciled_unit_breakdown_accepted_unchanged(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app, affordable_units_final=60)
    _add_document(session, app, "decision_notice", "60 affordable homes: 30 social rent, 30 shared ownership.")

    client = _client_returning(_base_refresh_response(
        affordable_units=60,
        affordable_housing_notes="60 affordable homes are secured: 30 social rent and 30 shared ownership.",
    ))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_units_final == 60
    assert "30 social rent" in app.scheme_intelligence.affordable_housing_notes


def test_partial_unit_breakdown_explicitly_flagged_as_partial(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app, affordable_units_final=60)
    _add_document(session, app, "viability_affordable_housing", "21 social/affordable rent, 21 shared ownership; remainder not specified.")

    client = _client_returning(_base_refresh_response(
        affordable_units=60,
        affordable_housing_notes=(
            "60 affordable homes are proposed. The evidence identifies 21 "
            "social/affordable-rent houses and 21 shared-ownership houses; "
            "the available evidence in this refresh does not clearly "
            "allocate the remaining 18 affordable homes by tenure."
        ),
    ))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_units_final == 60
    assert "does not clearly allocate" in app.scheme_intelligence.affordable_housing_notes
    assert "18" in app.scheme_intelligence.affordable_housing_notes


def test_missing_unit_breakdown_does_not_fabricate_tenure_detail(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app, affordable_units_final=60, affordable_tenure_split_final=None)
    _add_document(session, app, "decision_notice", "60 affordable homes secured, tenure mix not specified.")

    client = _client_returning(_base_refresh_response(affordable_units=60, affordable_tenure_split=None))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_tenure_split_final is None


def test_structured_units_total_not_derived_from_partial_narrative(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app, affordable_units_final=60)
    _add_document(session, app, "viability_affordable_housing", "21 social rent, 21 shared ownership identified.")

    # LLM doesn't return a new affordable_units figure (None) - the
    # structured total must stay authoritative at 60, never silently
    # recomputed as 21+21=42 from the partial narrative breakdown.
    client = _client_returning(_base_refresh_response(
        affordable_units=None,
        affordable_housing_notes="21 social rent and 21 shared ownership identified; remaining units not allocated by tenure.",
    ))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_units_final == 60


def test_site_summary_prompt_relays_partial_breakdown_notes_verbatim():
    site, apps = _site_and_apps()
    merged = _merged(
        affordable_housing_status="agreed", affordable_units_final=60,
        affordable_housing_notes=(
            "60 affordable homes are proposed. The evidence identifies 21 "
            "social/affordable-rent houses and 21 shared-ownership houses; "
            "the available evidence in this refresh does not clearly "
            "allocate the remaining 18 affordable homes by tenure."
        ),
    )
    prompt = build_summary_prompt(site, apps, merged, {"status": "on_track", "build_status": "not_started"}, [])
    assert "does not clearly allocate the remaining 18" in prompt


# ==============================================================================
# B3 PRE-HISTORICAL-REBUILD AMENDMENT: legal-security scope + refusal-reason
# reliability
#
# Phase 3 live validation (Trafford 114786/FUL/24, Stockport DC/060928)
# found two blocking defects, fixed here:
#   A. S106 LEGAL-SECURITY SCOPE - a genuine executed S106 anywhere in the
#      evidence incorrectly promoted the ENTIRE current affordable total to
#      legally_secured, even where the evidence itself distinguished a
#      legally-secured base from an additional non-S106 component.
#   B. REFUSAL-REASON RELIABILITY - an explicit, well-inside-context refusal
#      reason in a Decision Notice was missed because it was buried behind
#      a much larger lower-authority Planning Statement in the combined
#      evidence text.
# ==============================================================================

# --- Defect A: mixed legal security scope -------------------------------------


def test_mixed_s106_and_non_s106_position_not_labelled_legally_secured(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app, affordable_percentage_final=10.2, affordable_units_final=15, affordable_housing_status="proposed")
    _add_document(session, app, "s106", "Completed S106 secures the base 10% affordable housing requirement.")
    _add_document(session, app, "viability_affordable_housing", (
        "The applicant proposes to deliver an additional 40% non-s106 affordable homes, "
        "resulting in 50% affordable housing overall, equating to 73 properties including "
        "16 social rent and 57 shared ownership."
    ))

    client = _client_returning(_base_refresh_response(
        affordable_percentage=50.0, affordable_units=73, affordable_tenure_split="16 social rent, 57 shared ownership",
        affordable_housing_status=LEGALLY_SECURED_STATUS, affordable_provision_fully_legally_secured=False,
        affordable_housing_notes=(
            "The executed S106 secures the base 10% affordable housing requirement. The "
            "Affordable Housing Statement identifies a further 40% as non-S106 affordable "
            "housing, bringing the overall proposal to 50% / 73 homes."
        ),
    ))
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert outcome.outcome == OUTCOME_SUCCESS
    assert app.scheme_intelligence.affordable_housing_status != LEGALLY_SECURED_STATUS
    assert app.scheme_intelligence.affordable_housing_status == MIXED_SECURITY_FALLBACK_STATUS


def test_mixed_position_retains_total_current_provision_numbers(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app, affordable_percentage_final=10.2, affordable_units_final=15)
    _add_document(session, app, "s106", "Completed S106 secures the base 10% affordable housing requirement.")
    _add_document(session, app, "viability_affordable_housing", "An additional 40% non-s106 affordable homes are proposed, bringing the total to 50%, equating to 73 properties.")

    client = _client_returning(_base_refresh_response(
        affordable_percentage=50.0, affordable_units=73,
        affordable_housing_status=LEGALLY_SECURED_STATUS, affordable_provision_fully_legally_secured=False,
        affordable_housing_notes="The S106 secures the base 10%; a further 40% non-S106 provision brings the total to 50% / 73 homes.",
    ))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    # Part 4/9 of the amendment - the TOTAL current position may still
    # legitimately be 50%/73 units; only the security LABEL is corrected.
    assert app.scheme_intelligence.affordable_percentage_final == 50.0
    assert app.scheme_intelligence.affordable_units_final == 73
    assert app.scheme_intelligence.affordable_housing_status == MIXED_SECURITY_FALLBACK_STATUS


def test_mixed_position_notes_distinguish_secured_base_from_additional(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app, affordable_percentage_final=10.2, affordable_units_final=15)
    _add_document(session, app, "s106", "Completed S106 secures the base 10% requirement.")
    _add_document(session, app, "viability_affordable_housing", "Additional 40% non-s106 affordable homes proposed.")

    client = _client_returning(_base_refresh_response(
        affordable_percentage=50.0, affordable_units=73,
        affordable_housing_status=LEGALLY_SECURED_STATUS, affordable_provision_fully_legally_secured=False,
        affordable_housing_notes=(
            "The executed S106 secures the base 10% affordable housing requirement. The "
            "Affordable Housing Statement identifies a further 40% as non-S106 affordable housing."
        ),
    ))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    notes = app.scheme_intelligence.affordable_housing_notes
    assert "10%" in notes and "40%" in notes
    assert "non-S106" in notes


def test_guard_blocks_legally_secured_when_model_flag_not_true():
    new_fields_raw = {"affordable_housing_status": LEGALLY_SECURED_STATUS, "affordable_provision_fully_legally_secured": None}
    guarded = guard_mixed_legal_security_position(new_fields_raw, "some evidence text with no mixed signal")
    assert guarded["affordable_housing_status"] == MIXED_SECURITY_FALLBACK_STATUS


def test_guard_blocks_legally_secured_when_evidence_text_signals_mixed_position():
    # Even if the model itself claims full security, the deterministic
    # evidence-text scan still blocks it - "do not rely solely on prompt
    # obedience" (Part 8 of the amendment).
    new_fields_raw = {"affordable_housing_status": LEGALLY_SECURED_STATUS, "affordable_provision_fully_legally_secured": True}
    guarded = guard_mixed_legal_security_position(new_fields_raw, "an additional 40% non-s106 affordable homes are proposed")
    assert guarded["affordable_housing_status"] == MIXED_SECURITY_FALLBACK_STATUS


def test_fully_secured_position_remains_legally_secured(session):
    # Part 9 of the amendment - do not overcorrect: a genuinely fully-
    # secured position must still be allowed to be legally_secured.
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app, affordable_percentage_final=35.0, affordable_housing_status="proposed")
    _add_document(session, app, "s106", "This executed S106 Agreement legally secures the entire 50% affordable housing provision, comprising 73 homes.")

    client = _client_returning(_base_refresh_response(
        affordable_percentage=50.0, affordable_units=73,
        affordable_housing_status=LEGALLY_SECURED_STATUS, affordable_provision_fully_legally_secured=True,
        affordable_housing_notes="The executed S106 secures the entire 50% affordable housing provision.",
    ))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_housing_status == LEGALLY_SECURED_STATUS
    assert app.scheme_intelligence.affordable_percentage_final == 50.0


def test_existing_downgrade_guard_still_works_after_mixed_security_amendment(session):
    # Reconfirms guard_legally_secured_position's own downgrade protection
    # (Part 10, prior amendment) survives this one unmodified.
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=None)
    _add_scheme_intelligence(
        session, app, affordable_percentage_final=20.0, affordable_housing_status=LEGALLY_SECURED_STATUS,
        affordable_housing_notes="Secured at 20% via executed S106.",
    )
    _add_document(session, app, "planning_statement", "A later marketing planning statement claims 35% affordable housing.")

    client = _client_returning(_base_refresh_response(
        affordable_percentage=35.0, affordable_housing_status="proposed",
        affordable_housing_notes="Now proposing 35%.",
    ))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_percentage_final == 20.0
    assert app.scheme_intelligence.affordable_housing_status == LEGALLY_SECURED_STATUS


def test_downgrade_guard_output_feeds_correctly_into_mixed_security_guard():
    # Structural proof the two guards compose correctly - guard_legally_
    # secured_position's own forced reassertion must not be immediately
    # undone by guard_mixed_legal_security_position running afterward.
    existing = MagicMock(
        affordable_housing_status=LEGALLY_SECURED_STATUS, affordable_percentage_final=20.0,
        affordable_units_final=30, affordable_tenure_split_final="60/40", affordable_housing_notes="Secured at 20%.",
    )
    new_fields_raw = {"affordable_housing_status": "proposed", "affordable_percentage": 35.0}
    guarded_once = guard_legally_secured_position(existing, new_fields_raw, documents=[])
    guarded_twice = guard_mixed_legal_security_position(guarded_once, "no mixed-security signal text")
    assert guarded_twice["affordable_housing_status"] == LEGALLY_SECURED_STATUS


def test_mixed_security_fallback_status_is_valid_vocabulary_member():
    assert MIXED_SECURITY_FALLBACK_STATUS in AFFORDABLE_HOUSING_STATUSES


def test_guard_handles_missing_fully_secured_key_safely():
    guarded = guard_mixed_legal_security_position({"affordable_housing_status": LEGALLY_SECURED_STATUS}, "no signal here")
    assert guarded["affordable_housing_status"] == MIXED_SECURITY_FALLBACK_STATUS


# --- Live batch hotfix: authoritative positive-evidence legal-security guard --
# (Wigan A/20/88859/RMMAJ, application 721 - real production live-batch
# finding: guard_legally_secured_position only protects a DOWNGRADE of an
# already-secured position; guard_mixed_legal_security_position only catches
# the narrower "partial S106 + non-S106 top-up" pattern via the model's own
# self-report plus a phrase scan. Neither checked whether a FIRST-TIME
# legally_secured claim is grounded in any authoritative document's own
# content at all - guard_legally_secured_requires_authoritative_content below
# closes that gap.)


def _doc(doc_type: str, text: str):
    return MagicMock(doc_type=doc_type, extracted_text=text)


def test_decision_notice_with_no_affordable_content_cannot_establish_legally_secured():
    documents = [_doc("decision_notice", "Approval of Reserved Matters. Conditions: 1. Development in accordance with drawing SK474.")]
    new_fields_raw = {"affordable_housing_status": LEGALLY_SECURED_STATUS, "affordable_provision_fully_legally_secured": True}
    guarded = guard_legally_secured_requires_authoritative_content(None, new_fields_raw, documents)
    assert guarded["affordable_housing_status"] == MIXED_SECURITY_FALLBACK_STATUS


def test_officer_report_alone_cannot_establish_legally_secured():
    # officer_report is not a legally-authoritative document type at all -
    # the guard must reject regardless of its (irrelevant, since it's not
    # even checked) content.
    documents = [_doc("officer_report", "The proposed development will deliver 163 affordable homes, 63% of the total.")]
    new_fields_raw = {"affordable_housing_status": LEGALLY_SECURED_STATUS, "affordable_provision_fully_legally_secured": True}
    guarded = guard_legally_secured_requires_authoritative_content(None, new_fields_raw, documents)
    assert guarded["affordable_housing_status"] == MIXED_SECURITY_FALLBACK_STATUS


def test_planning_statement_alone_cannot_establish_legally_secured():
    documents = [_doc("planning_statement", "The applicant proposes 63% affordable housing across 163 homes.")]
    new_fields_raw = {"affordable_housing_status": LEGALLY_SECURED_STATUS, "affordable_provision_fully_legally_secured": True}
    guarded = guard_legally_secured_requires_authoritative_content(None, new_fields_raw, documents)
    assert guarded["affordable_housing_status"] == MIXED_SECURITY_FALLBACK_STATUS


def test_executed_s106_with_affordable_content_still_allowed_legally_secured():
    documents = [_doc("s106", "This executed S106 Agreement legally secures 35% affordable housing.")]
    new_fields_raw = {"affordable_housing_status": LEGALLY_SECURED_STATUS, "affordable_provision_fully_legally_secured": True}
    guarded = guard_legally_secured_requires_authoritative_content(None, new_fields_raw, documents)
    assert guarded["affordable_housing_status"] == LEGALLY_SECURED_STATUS


def test_decision_notice_explicitly_securing_provision_still_allowed_legally_secured():
    # A Decision Notice CAN by itself justify legally_secured when its own
    # text genuinely discusses the affordable housing obligation - the fix
    # is about CONTENT, not banning decision_notice as a qualifying type.
    documents = [_doc("decision_notice", "Notice of Approval. Condition 12 requires the affordable housing scheme (40% affordable) to be implemented in full prior to occupation.")]
    new_fields_raw = {"affordable_housing_status": LEGALLY_SECURED_STATUS, "affordable_provision_fully_legally_secured": True}
    guarded = guard_legally_secured_requires_authoritative_content(None, new_fields_raw, documents)
    assert guarded["affordable_housing_status"] == LEGALLY_SECURED_STATUS


def test_positive_evidence_guard_does_not_reopen_mixed_security_composition():
    # If guard_mixed_legal_security_position already downgraded the status,
    # this guard must be a pure no-op (it only ever inspects a status that
    # is STILL legally_secured) - proves the two guards compose correctly.
    documents = [_doc("decision_notice", "Approval of Reserved Matters. No affordable housing wording present.")]
    already_downgraded = {"affordable_housing_status": MIXED_SECURITY_FALLBACK_STATUS, "affordable_provision_fully_legally_secured": False}
    guarded = guard_legally_secured_requires_authoritative_content(None, already_downgraded, documents)
    assert guarded is already_downgraded  # unchanged object - true no-op


def test_positive_evidence_guard_does_not_undo_existing_downgrade_protection():
    # guard_legally_secured_position may legitimately force affordable_
    # housing_status back to legally_secured on a reassertion pass whose OWN
    # evidence contains no authoritative document at all (Part 10's own
    # downgrade-protection design) - this guard must never re-gate and undo
    # that reassertion. Uses the two guards in the SAME order refresh_
    # intelligence_for_application itself calls them.
    existing = MagicMock(
        affordable_housing_status=LEGALLY_SECURED_STATUS, affordable_percentage_final=20.0,
        affordable_units_final=30, affordable_tenure_split_final="60/40", affordable_housing_notes="Secured at 20%.",
    )
    documents = [_doc("planning_statement", "A later marketing statement claims 35% affordable housing.")]
    new_fields_raw = {"affordable_housing_status": "proposed", "affordable_percentage": 35.0}

    guarded = guard_legally_secured_position(existing, new_fields_raw, documents)
    guarded = guard_mixed_legal_security_position(guarded, "a later marketing statement claims 35% affordable housing")
    guarded = guard_legally_secured_requires_authoritative_content(existing, guarded, documents)

    assert guarded["affordable_housing_status"] == LEGALLY_SECURED_STATUS
    assert guarded["affordable_percentage"] == 20.0


def test_wigan_production_regression_decision_notice_no_affordable_content(session):
    # Real production live-batch finding (Wigan A/20/88859/RMMAJ, application
    # 721): decision_notice contained ZERO affordable-housing wording
    # anywhere in its text; the entire 63%/161-vs-163-unit/tenure narrative
    # came exclusively from officer_report and planning_statement - neither
    # a legally-authoritative document type. Test-locks the fix.
    app = _add_application(session, reference="A/20/88859/RMMAJ", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", (
        "Form P4 Approval of Reserved Matters. Conditions: 1. The development hereby approved "
        "shall be carried out in accordance with the details indicated on plan reference SK474."
    ))
    _add_document(session, app, "officer_report", (
        "The proposed development will deliver 163 affordable homes. This accounts for 63% of "
        "the total dwellings. These will be split between 72 shared ownership dwellings and 91 "
        "affordable rent dwellings, exceeding the Council's target of 25%."
    ))
    _add_document(session, app, "planning_statement", "The scheme proposes 257 dwellings including a substantial affordable housing component.")

    client = _client_returning(_base_refresh_response(
        affordable_percentage=63.0, affordable_units=161, affordable_tenure_split="72 shared ownership, 91 affordable rent",
        affordable_housing_status=LEGALLY_SECURED_STATUS, affordable_provision_fully_legally_secured=True,
        affordable_housing_notes="Affordable housing is legally secured; project delivers 163 affordable homes, exceeding the Council's target of 25%.",
    ))
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert outcome.outcome == OUTCOME_SUCCESS
    # The unsupported security classification is corrected...
    assert app.scheme_intelligence.affordable_housing_status == MIXED_SECURITY_FALLBACK_STATUS
    assert app.scheme_intelligence.affordable_housing_status != LEGALLY_SECURED_STATUS
    # ...while the underlying, evidence-grounded percentage/units/tenure
    # remain exactly where supported (only the security LABEL is corrected).
    assert app.scheme_intelligence.affordable_percentage_final == 63.0
    assert app.scheme_intelligence.affordable_units_final == 161
    assert app.scheme_intelligence.affordable_tenure_split_final == "72 shared ownership, 91 affordable rent"


# --- Live batch hotfix: "conditioned" requires an actual AH condition --------
# (Stockport DC/091326, application 825 - real production live-batch
# finding: the sole usable document was a decision_notice that is itself an
# internal council email discharging a CONTAMINATION/remediation condition,
# entirely unrelated to affordable housing. The model produced status=
# "conditioned" with 0%/0 units, while its own notes correctly said "no
# affordable housing units proposed" - an internal self-contradiction.)


def test_stockport_production_regression_conditioned_status_denied_by_own_notes(session):
    app = _add_application(session, reference="DC/091326", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", (
        "I have reviewed the LKC Updated Risk Assessment and Remediation Strategy. "
        "As such, Condition 27 of 086371 can be discharged."
    ))

    client = _client_returning(_base_refresh_response(
        affordable_percentage=0.0, affordable_units=0, affordable_housing_status="conditioned",
        affordable_housing_notes="Condition 27 can now be discharged based on the LKC Updated Risk Assessment and Remediation Strategy, but there are no affordable housing units proposed.",
    ))
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert outcome.outcome == OUTCOME_SUCCESS
    assert app.scheme_intelligence.affordable_housing_status == "unknown"
    assert app.scheme_intelligence.affordable_housing_status != "conditioned"


def test_guard_rejects_conditioned_status_when_notes_deny_any_affordable_housing():
    new_fields_raw = {
        "affordable_housing_status": "conditioned",
        "affordable_housing_notes": "There are no affordable housing units proposed for this scheme.",
    }
    guarded = guard_conditioned_status_requires_an_actual_condition(new_fields_raw)
    assert guarded["affordable_housing_status"] == "unknown"


def test_guard_leaves_genuine_conditioned_status_with_zero_delivered_units_untouched():
    # Part 15, item 10: a genuine affordable-housing CONDITION with zero
    # units DELIVERED so far (obligation exists, nothing built yet) is a
    # legitimate "conditioned" case and must not be silently erased merely
    # because the notes happen to describe zero current delivery.
    new_fields_raw = {
        "affordable_housing_status": "conditioned",
        "affordable_housing_notes": "Condition 14 requires an affordable housing scheme to be agreed prior to first occupation; no units have been delivered yet as construction has not started.",
    }
    guarded = guard_conditioned_status_requires_an_actual_condition(new_fields_raw)
    assert guarded["affordable_housing_status"] == "conditioned"


def test_guard_leaves_non_conditioned_statuses_untouched():
    new_fields_raw = {"affordable_housing_status": "proposed", "affordable_housing_notes": "No affordable housing units proposed."}
    guarded = guard_conditioned_status_requires_an_actual_condition(new_fields_raw)
    assert guarded["affordable_housing_status"] == "proposed"


# --- Live batch hotfix: conflicting source unit totals ------------------------
# (Wigan A/20/88859/RMMAJ - the officer_report itself states "161 dwellings
# will be delivered as affordable housing" in one passage and a tenure
# breakdown (72 shared ownership + 91 affordable rent) summing to 163
# elsewhere. Smallest reliable mechanism per the task: a prompt instruction,
# not a new arithmetic/reconciliation subsystem - see build_refresh_prompt's
# own "CONFLICTING SOURCE TOTALS" rule.)


def test_prompt_instructs_explicit_conflicting_totals_qualification():
    prompt = build_refresh_prompt(
        MagicMock(reference="APP/1", address="1 Test St", status="Decided", decision="Granted"),
        DEPTH_BROAD, None, "evidence text",
    )
    assert "CONFLICTING SOURCE TOTALS" in prompt
    assert "161" in prompt and "163" in prompt  # the real Wigan figures, as a concrete worked example


def test_prompt_defines_conditioned_status_requires_an_affordable_condition():
    prompt = build_refresh_prompt(
        MagicMock(reference="APP/1", address="1 Test St", status="Decided", decision="Granted"),
        DEPTH_BROAD, None, "evidence text",
    )
    assert '"conditioned" MEANS SPECIFICALLY' in prompt
    assert "Discharge of Conditions" in prompt


# --- Live batch hotfix: corrected intelligence flows into Site Summary -------


def test_corrected_legally_secured_status_flows_into_same_pass_site_summary(session, monkeypatch):
    captured = {}

    def fake_generate_scheme_summary(client, site, applications, merged, lapse, phase_breakdown):
        captured["merged"] = dict(merged)
        return "Fresh summary."

    monkeypatch.setattr("app.reporting.scheme_summary.generate_scheme_summary", fake_generate_scheme_summary)

    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    app = _add_application(session, reference="A/20/88859/RMMAJ", evidence_refresh_reason=REASON_DECISION_GRANTED, site_id=site.id)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Approval of Reserved Matters. Conditions: 1. Development in accordance with drawing SK474.")
    _add_document(session, app, "officer_report", "The proposed development will deliver 163 affordable homes, 63% of the total.")

    client = _client_returning(_base_refresh_response(
        affordable_percentage=63.0, affordable_housing_status=LEGALLY_SECURED_STATUS,
        affordable_provision_fully_legally_secured=True,
        affordable_housing_notes="Affordable housing is legally secured.",
    ))
    outcome = refresh_intelligence_for_application(session, client, app)  # default generate_summary path

    assert outcome.outcome == OUTCOME_SUCCESS
    # No separate Site Summary patch (Part 11 of the task) - the SAME
    # already-guarded new_fields dict is what generate_summary receives.
    assert captured["merged"]["affordable_housing_status"] == MIXED_SECURITY_FALLBACK_STATUS
    assert captured["merged"]["affordable_housing_status"] != LEGALLY_SECURED_STATUS
    assert app.scheme_intelligence.affordable_housing_status == MIXED_SECURITY_FALLBACK_STATUS


# --- Defect A: affordable tenure consistency -----------------------------------


def test_tenure_refreshed_coherently_when_new_evidence_clarifies_mix(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app, affordable_tenure_split_final="Shared Ownership, Rent to Buy")
    _add_document(session, app, "viability_affordable_housing", "16 social rent, 57 shared ownership.")

    client = _client_returning(_base_refresh_response(
        affordable_tenure_split="16 social rent, 57 shared ownership",
        affordable_housing_notes="The tenure mix comprises 16 social rent and 57 shared ownership homes.",
    ))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_tenure_split_final == "16 social rent, 57 shared ownership"
    assert "social rent" in app.scheme_intelligence.affordable_housing_notes


def test_tenure_and_notes_do_not_contradict_after_successful_pass(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "viability_affordable_housing", "16 social rent, 57 shared ownership.")

    client = _client_returning(_base_refresh_response(
        affordable_tenure_split="16 social rent, 57 shared ownership",
        affordable_housing_notes="16 social rent and 57 shared ownership homes are proposed.",
    ))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    tenure = app.scheme_intelligence.affordable_tenure_split_final
    notes = app.scheme_intelligence.affordable_housing_notes
    assert "social rent" in tenure and "social rent" in notes
    assert "shared ownership" in tenure and "shared ownership" in notes


def test_conflicting_tenure_evidence_states_uncertainty_not_fabricated_reconciliation(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app, affordable_tenure_split_final="Shared Ownership, Rent to Buy")
    _add_document(session, app, "officer_report", "Tenure split reported inconsistently across documents.")

    client = _client_returning(_base_refresh_response(
        affordable_tenure_split=None,
        affordable_housing_notes="Tenure evidence this pass is conflicting; the previously recorded split is retained pending clarification.",
    ))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.affordable_tenure_split_final == "Shared Ownership, Rent to Buy"
    assert "conflicting" in app.scheme_intelligence.affordable_housing_notes.lower()


def test_default_summary_receives_reconciled_tenure_position(session, monkeypatch):
    captured = {}

    def fake_generate_scheme_summary(client, site, applications, merged, lapse, phase_breakdown):
        captured["merged"] = dict(merged)
        return "Summary reflecting reconciled tenure."

    monkeypatch.setattr("app.reporting.scheme_summary.generate_scheme_summary", fake_generate_scheme_summary)

    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED, site_id=site.id)
    _add_scheme_intelligence(session, app, affordable_tenure_split_final="Shared Ownership, Rent to Buy")
    _add_document(session, app, "viability_affordable_housing", "16 social rent, 57 shared ownership.")

    client = _client_returning(_base_refresh_response(
        affordable_tenure_split="16 social rent, 57 shared ownership",
        affordable_housing_notes="16 social rent and 57 shared ownership homes are proposed.",
    ))
    refresh_intelligence_for_application(session, client, app)

    assert captured["merged"]["affordable_tenure_split_final"] == "16 social rent, 57 shared ownership"


# --- Defect B: refusal-reason reliability --------------------------------------


def test_formal_refusal_reasons_populated_when_evidenced(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_REFUSED, decision="Refuse")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", (
        "PLANNING PERMISSION HAS BEEN REFUSED for the following\nreason:\n"
        "1. Harm to the Green Belt and failure to provide 50% affordable housing."
    ))

    client = _client_returning(_base_refresh_response(
        refusal_reasons="Harm to the Green Belt and failure to provide 50% affordable housing.",
    ))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.refusal_reasons == "Harm to the Green Belt and failure to provide 50% affordable housing."


def test_extract_refusal_reason_excerpt_finds_stockport_style_wording(session):
    app = _add_application(session, reference="APP/1")
    doc = _add_document(session, app, "decision_notice", (
        "STOCKPORT METROPOLITAN BOROUGH COUNCIL\nDECISION NOTICE\n...header text...\n"
        "the Council hereby give notice that PLANNING PERMISSION HAS BEEN REFUSED "
        "for the carrying out of the development described above, for the following\n"
        "reason:\n1. Very special circumstances do not exist..."
    ))
    excerpt = extract_refusal_reason_excerpt([doc])
    assert excerpt is not None
    assert "Very special circumstances" in excerpt


def test_extract_refusal_reason_excerpt_ignores_officer_report(session):
    app = _add_application(session, reference="APP/1")
    officer_doc = _add_document(
        session, app, "officer_report", "Officers discuss the reasons for refusal at length in this report.",
    )
    excerpt = extract_refusal_reason_excerpt([officer_doc])
    assert excerpt is None  # only decision_notice documents are scanned


def test_multiple_refusal_reasons_represented_concisely(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_REFUSED)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "REFUSED for the following\nreasons:\n1. Green Belt harm.\n2. Heritage asset harm.\n3. Highways safety.")

    client = _client_returning(_base_refresh_response(
        refusal_reasons="Green Belt harm, heritage asset harm (Griffin Farmhouse), and highways safety concerns.",
    ))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    reasons = app.scheme_intelligence.refusal_reasons
    assert "Green Belt" in reasons and "highways" in reasons.lower()


def test_no_refusal_reason_fabricated_when_decision_notice_lacks_explicit_wording(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_REFUSED)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "The application is refused. No further detail provided in this excerpt.")

    client = _client_returning(_base_refresh_response(refusal_reasons=None))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert app.scheme_intelligence.refusal_reasons is None


def test_objection_text_alone_does_not_trigger_refusal_reason_extraction(session):
    app = _add_application(session, reference="APP/1")
    doc = _add_document(session, app, "decision_notice", "Numerous objections were received citing loss of light and parking concerns.")
    excerpt = extract_refusal_reason_excerpt([doc])
    assert excerpt is None


def test_refresh_prompt_includes_highlighted_refusal_excerpt_when_present(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "planning_statement", "Applicant proposal text. " * 3000)
    _add_document(session, app, "decision_notice", "REFUSED for the following\nreason:\n1. Green Belt harm and heritage impact.")

    client = _client_returning(_base_refresh_response(refusal_reasons="Green Belt harm and heritage impact."))
    refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    sent_prompt = client.responses.create.call_args.kwargs["input"]
    assert "HIGHLIGHTED EXCERPT FROM THE FORMAL DECISION NOTICE" in sent_prompt
    assert "Green Belt harm and heritage impact" in sent_prompt


def test_refusal_excerpt_works_in_broad_depth(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "REFUSED for the following\nreason:\n1. Green Belt harm.")

    client = _client_returning(_base_refresh_response(refusal_reasons="Green Belt harm."))
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert outcome.depth == DEPTH_BROAD
    sent_prompt = client.responses.create.call_args.kwargs["input"]
    assert "HIGHLIGHTED EXCERPT FROM THE FORMAL DECISION NOTICE" in sent_prompt


def test_refusal_excerpt_works_in_focused_refusal_depth(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_REFUSED)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "REFUSED for the following\nreason:\n1. Green Belt harm.")

    client = _client_returning(_base_refresh_response(refusal_reasons="Green Belt harm."))
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert outcome.depth == DEPTH_FOCUSED_REFUSAL
    sent_prompt = client.responses.create.call_args.kwargs["input"]
    assert "HIGHLIGHTED EXCERPT FROM THE FORMAL DECISION NOTICE" in sent_prompt


def test_default_summary_receives_prospective_refusal_reasons(session, monkeypatch):
    captured = {}

    def fake_generate_scheme_summary(client, site, applications, merged, lapse, phase_breakdown):
        captured["merged"] = dict(merged)
        return "Summary mentioning the refusal reason."

    monkeypatch.setattr("app.reporting.scheme_summary.generate_scheme_summary", fake_generate_scheme_summary)

    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    app = _add_application(
        session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_REFUSED, site_id=site.id, decision="Refuse",
    )
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "REFUSED for the following\nreason:\n1. Green Belt harm and heritage impact.")

    client = _client_returning(_base_refresh_response(refusal_reasons="Green Belt harm and heritage impact."))
    refresh_intelligence_for_application(session, client, app)

    assert captured["merged"]["refusal_reasons"] == "Green Belt harm and heritage impact."


# --- Atomicity reconfirmation ---------------------------------------------------


def test_refusal_summary_failure_preserves_old_refusal_reasons_and_summary(session, monkeypatch):
    def failing_generate_scheme_summary(client, site, applications, merged, lapse, phase_breakdown):
        raise RuntimeError("summary generation failed")

    monkeypatch.setattr("app.reporting.scheme_summary.generate_scheme_summary", failing_generate_scheme_summary)

    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    app = _add_application(
        session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_REFUSED, site_id=site.id, decision="Refuse",
    )
    site.status_summary = "Old summary"
    _add_scheme_intelligence(session, app, refusal_reasons="Old reason preserved.")
    _add_document(session, app, "decision_notice", "REFUSED for the following\nreason:\n1. New reason text.")
    session.commit()

    client = _client_returning(_base_refresh_response(refusal_reasons="New reason text."))
    outcome = refresh_intelligence_for_application(session, client, app)

    assert outcome.outcome == OUTCOME_ERROR
    assert app.scheme_intelligence.refusal_reasons == "Old reason preserved."
    assert site.status_summary == "Old summary"


def test_successful_refresh_commits_mixed_security_and_refusal_fields_together(session):
    site = Site(council_code="testcouncil", canonical_address="4 test street", display_address="4 Test Street")
    session.add(site)
    session.commit()
    now = dt.datetime.now(dt.timezone.utc)
    app = _add_application(
        session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED,
        site_id=site.id, material_evidence_changed_at=now,
    )
    _add_scheme_intelligence(
        session, app, affordable_percentage_final=10.2, affordable_units_final=15,
        affordable_tenure_split_final="Shared Ownership, Rent to Buy",
    )
    _add_document(session, app, "s106", "Completed S106 secures the base 10% requirement.")
    _add_document(session, app, "viability_affordable_housing", (
        "Additional 40% non-s106 affordable homes proposed, 16 social rent and 57 shared "
        "ownership, totalling 73 homes / 50%."
    ))

    client = _client_returning(_base_refresh_response(
        affordable_percentage=50.0, affordable_units=73, affordable_tenure_split="16 social rent, 57 shared ownership",
        affordable_housing_status=LEGALLY_SECURED_STATUS, affordable_provision_fully_legally_secured=False,
        affordable_housing_notes=(
            "The executed S106 secures the base 10% affordable housing requirement. An "
            "additional 40% is delivered as non-S106 affordable housing."
        ),
    ))
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub("Fresh summary"))

    assert outcome.outcome == OUTCOME_SUCCESS
    assert app.scheme_intelligence.affordable_percentage_final == 50.0
    assert app.scheme_intelligence.affordable_units_final == 73
    assert app.scheme_intelligence.affordable_tenure_split_final == "16 social rent, 57 shared ownership"
    assert app.scheme_intelligence.affordable_housing_status == MIXED_SECURITY_FALLBACK_STATUS
    assert site.status_summary == "Fresh summary"
    assert app.intelligence_evidence_processed_at == now


# ==============================================================================
# FINAL PRE-MERGE AMENDMENT (historical rebuild): extra_fields same-transaction
# seam
#
# A small, generic, opt-in mechanism letting a caller (e.g. app.extraction.
# historical_rebuild) persist its OWN completion marker in the exact same
# commit as the SchemeIntelligence/Site Summary/watermark replacement -
# never used by normal B3 processing itself (always omitted, defaults to
# None).
# ==============================================================================


def test_extra_fields_applied_on_successful_refresh(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")

    client = _client_returning(_base_refresh_response())
    outcome = refresh_intelligence_for_application(
        session, client, app, generate_summary=_summary_stub(),
        extra_fields={"intelligence_rebuild_version": "b3_v1"},
    )

    assert outcome.outcome == OUTCOME_SUCCESS
    assert app.scheme_intelligence.intelligence_rebuild_version == "b3_v1"


def test_extra_fields_not_applied_on_ai_error(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")

    client = MagicMock()
    client.responses.create.side_effect = OpenAIError("api down")
    outcome = refresh_intelligence_for_application(
        session, client, app, generate_summary=_summary_stub(),
        extra_fields={"intelligence_rebuild_version": "b3_v1"},
    )

    assert outcome.outcome == OUTCOME_AI_ERROR
    assert app.scheme_intelligence.intelligence_rebuild_version is None


def test_extra_fields_not_applied_on_summary_failure(session):
    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED, site_id=site.id)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")

    client = _client_returning(_base_refresh_response())
    outcome = refresh_intelligence_for_application(
        session, client, app, generate_summary=_summary_stub(raise_error=True),
        extra_fields={"intelligence_rebuild_version": "b3_v1"},
    )

    assert outcome.outcome == OUTCOME_ERROR
    assert app.scheme_intelligence.intelligence_rebuild_version is None


def test_extra_fields_defaults_to_none_and_is_a_no_op(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")

    client = _client_returning(_base_refresh_response())
    outcome = refresh_intelligence_for_application(session, client, app, generate_summary=_summary_stub())

    assert outcome.outcome == OUTCOME_SUCCESS
    assert app.scheme_intelligence.intelligence_rebuild_version is None
    assert app.scheme_intelligence.intelligence_rebuilt_at is None
