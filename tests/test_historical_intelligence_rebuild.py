"""PROPERTY AIGENT — Historical B3 Intelligence Rebuild Runner tests.

Covers: candidate selection, dry-run (zero writes/zero AI calls), success/
resume semantics, QA warnings (tenure mismatch, complex site), B3 safety
reconfirmation (mixed legal security, refusal reliability, prospective Site
Summary, recommendation/decision distinction), historical-watermark safety
(never fabricates intelligence_evidence_processed_at), and batch/safety
limits.

Uses the same in-memory-SQLite `session` fixture as the rest of this suite
(tests/conftest.py). No real OpenAI call anywhere - the LLM client is
always a MagicMock whose .responses.create(...).output_text is a fixed
JSON string.
"""
from __future__ import annotations

import datetime as dt
import json
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.db.models import Application, Document, SchemeIntelligence, Site
from app.extraction.historical_rebuild import (
    COMPLEX_SITE_APPLICATION_THRESHOLD,
    DEFAULT_BATCH_LIMIT,
    MAX_BATCH_LIMIT_WITHOUT_OVERRIDE,
    QA_SITE_SUMMARY_COMPLEX_SITE,
    QA_TENURE_NARRATIVE_MISMATCH,
    REBUILD_VERSION,
    build_candidate_evidence_snapshot,
    detect_tenure_narrative_mismatch,
    is_complex_site,
    run_historical_rebuild,
    select_historical_rebuild_candidates,
)
from app.extraction.intelligence_refresh import LEGALLY_SECURED_STATUS, broad_refresh_evidence_categories
from app.extraction.run_extraction import (
    OUTCOME_AI_ERROR,
    OUTCOME_NO_USABLE_TEXT,
    OUTCOME_SUCCESS,
)
from app.pipeline.evidence_refresh import resolve_application_family
from app.pipeline.run_weekly import INTELLIGENCE_REFRESH_ELIGIBLE


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


def _summary_client(text: str = "Rebuilt status note.") -> MagicMock:
    """A client whose .responses.create is called twice per successful,
    site-linked candidate (intelligence refresh, then Site Summary) - both
    calls return valid JSON for their own schema, so this single mock
    covers a full end-to-end run_historical_rebuild pass without needing
    the generate_summary injection seam (this module always uses the
    default generate_summary, matching real production usage)."""
    client = MagicMock()

    def _dispatch(model, input, text: dict):  # noqa: A002 - matches real call signature
        schema_name = text["format"]["name"]
        if schema_name == "planning_intelligence_refresh":
            return MagicMock(output_text=json.dumps(_base_refresh_response()))
        return MagicMock(output_text=json.dumps({"summary": "Rebuilt status note."}))

    client.responses.create.side_effect = _dispatch
    return client


# --- Candidate selection (37: items 1-10) --------------------------------------


def test_existing_scheme_intelligence_row_is_eligible(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Some evidence.")
    candidates = select_historical_rebuild_candidates(session)
    assert app.id in {a.id for a in candidates}


def test_application_without_scheme_intelligence_excluded(session):
    app = _add_application(session, reference="APP/1")
    _add_document(session, app, "decision_notice", "Some evidence.")
    candidates = select_historical_rebuild_candidates(session)
    assert app.id not in {a.id for a in candidates}


def test_already_rebuilt_current_version_excluded(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app, intelligence_rebuild_version=REBUILD_VERSION)
    _add_document(session, app, "decision_notice", "Some evidence.")
    candidates = select_historical_rebuild_candidates(session, rebuild_version=REBUILD_VERSION)
    assert app.id not in {a.id for a in candidates}


def test_older_rebuild_version_eligible_for_newer_version(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app, intelligence_rebuild_version="b3_v0")
    _add_document(session, app, "decision_notice", "Some evidence.")
    candidates = select_historical_rebuild_candidates(session, rebuild_version="b3_v1")
    assert app.id in {a.id for a in candidates}


def test_null_rebuild_version_still_eligible(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app, intelligence_rebuild_version=None)
    _add_document(session, app, "decision_notice", "Some evidence.")
    candidates = select_historical_rebuild_candidates(session, rebuild_version=REBUILD_VERSION)
    assert app.id in {a.id for a in candidates}


def test_council_filter_works(session):
    app_a = _add_application(session, reference="APP/A", council_code="stockport")
    app_b = _add_application(session, reference="APP/B", council_code="trafford")
    _add_scheme_intelligence(session, app_a)
    _add_scheme_intelligence(session, app_b)
    _add_document(session, app_a, "decision_notice", "Evidence.")
    _add_document(session, app_b, "decision_notice", "Evidence.")
    candidates = select_historical_rebuild_candidates(session, council="stockport")
    ids = {a.id for a in candidates}
    assert app_a.id in ids
    assert app_b.id not in ids


def test_application_id_filter_works(session):
    app_a = _add_application(session, reference="APP/A")
    app_b = _add_application(session, reference="APP/B")
    _add_scheme_intelligence(session, app_a)
    _add_scheme_intelligence(session, app_b)
    _add_document(session, app_a, "decision_notice", "Evidence.")
    _add_document(session, app_b, "decision_notice", "Evidence.")
    candidates = select_historical_rebuild_candidates(session, application_id=app_a.id)
    ids = {a.id for a in candidates}
    assert ids == {app_a.id}


def test_site_id_filter_works(session):
    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    app_a = _add_application(session, reference="APP/A", site_id=site.id)
    app_b = _add_application(session, reference="APP/B")
    _add_scheme_intelligence(session, app_a)
    _add_scheme_intelligence(session, app_b)
    _add_document(session, app_a, "decision_notice", "Evidence.")
    _add_document(session, app_b, "decision_notice", "Evidence.")
    candidates = select_historical_rebuild_candidates(session, site_id=site.id)
    ids = {a.id for a in candidates}
    assert ids == {app_a.id}


def test_limit_enforced(session):
    for i in range(5):
        app = _add_application(session, reference=f"APP/{i}")
        _add_scheme_intelligence(session, app)
        _add_document(session, app, "decision_notice", "Evidence.")
    candidates = select_historical_rebuild_candidates(session, limit=2)
    assert len(candidates) == 2


def test_deterministic_ordering_by_last_seen_then_id(session):
    now = dt.datetime.now(dt.timezone.utc)
    older = _add_application(session, reference="APP/OLDER", last_seen_at=now - dt.timedelta(days=5))
    newer = _add_application(session, reference="APP/NEWER", last_seen_at=now)
    _add_scheme_intelligence(session, older)
    _add_scheme_intelligence(session, newer)
    _add_document(session, older, "decision_notice", "Evidence.")
    _add_document(session, newer, "decision_notice", "Evidence.")
    candidates = select_historical_rebuild_candidates(session)
    assert [a.id for a in candidates] == [newer.id, older.id]


# --- Candidate evidence-eligibility (this amendment, items 1-9) ----------------


def test_row_with_usable_b3_evidence_is_eligible(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")
    candidates = select_historical_rebuild_candidates(session)
    assert app.id in {a.id for a in candidates}


def test_row_with_no_usable_evidence_is_excluded(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)  # no documents at all
    candidates = select_historical_rebuild_candidates(session)
    assert app.id not in {a.id for a in candidates}


def test_null_extracted_text_does_not_qualify(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    doc = Document(
        application_id=app.id, doc_type="decision_notice", document_name="d.pdf",
        source_url="https://example.invalid/d.pdf", text_extracted=True, extracted_text=None,
    )
    session.add(doc)
    session.commit()
    candidates = select_historical_rebuild_candidates(session)
    assert app.id not in {a.id for a in candidates}


def test_empty_extracted_text_does_not_qualify(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    doc = Document(
        application_id=app.id, doc_type="decision_notice", document_name="d.pdf",
        source_url="https://example.invalid/d.pdf", text_extracted=True, extracted_text="",
    )
    session.add(doc)
    session.commit()
    candidates = select_historical_rebuild_candidates(session)
    assert app.id not in {a.id for a in candidates}


def test_irrelevant_category_does_not_qualify(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "other", "Some unrelated document text.")
    candidates = select_historical_rebuild_candidates(session)
    assert app.id not in {a.id for a in candidates}


def test_evidence_category_set_matches_b3_broad_depth():
    from app.extraction.intelligence_refresh import DEPTH_BROAD, _DOC_TYPES_BY_DEPTH

    assert broad_refresh_evidence_categories() == _DOC_TYPES_BY_DEPTH[DEPTH_BROAD]


def test_excluded_no_evidence_row_does_not_consume_batch_limit(session):
    app_no_evidence = _add_application(session, reference="APP/NO_EVIDENCE", last_seen_at=dt.datetime.now(dt.timezone.utc))
    app_with_evidence = _add_application(
        session, reference="APP/WITH_EVIDENCE", last_seen_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1),
    )
    _add_scheme_intelligence(session, app_no_evidence)
    _add_scheme_intelligence(session, app_with_evidence)
    _add_document(session, app_with_evidence, "decision_notice", "Granted.")

    candidates = select_historical_rebuild_candidates(session, limit=1)

    assert [a.id for a in candidates] == [app_with_evidence.id]


def test_no_evidence_row_receives_no_openai_call(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    client = MagicMock()

    run_historical_rebuild(session, client, dry_run=False)

    client.responses.create.assert_not_called()


def test_no_evidence_row_is_not_falsely_marked_rebuilt(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    client = MagicMock()

    run_historical_rebuild(session, client, dry_run=False)

    assert app.scheme_intelligence.intelligence_rebuild_version is None


def test_row_automatically_becomes_eligible_after_evidence_added(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)

    candidates_before = select_historical_rebuild_candidates(session)
    assert app.id not in {a.id for a in candidates_before}

    _add_document(session, app, "decision_notice", "Granted.")

    candidates_after = select_historical_rebuild_candidates(session)
    assert app.id in {a.id for a in candidates_after}


# --- Family-evidence eligibility (final family-evidence amendment) -------------
# The bounded family this module resolves (resolve_application_family) must be
# EXACTLY the same one refresh_intelligence_for_application itself resolves -
# reused directly, not reimplemented. These tests prove eligibility is neither
# narrower (Cases A/B/C/F) nor broader (Case D) than that real B3 family scope.


def test_case_a_direct_evidence_qualifies(session):
    app = _add_application(session, reference="APP/A")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted directly.")

    candidates = select_historical_rebuild_candidates(session)

    assert app.id in {a.id for a in candidates}


def test_case_b_parent_evidence_qualifies(session):
    parent = _add_application(session, reference="APP/PARENT/1")
    child = _add_application(
        session, reference="APP/CHILD",
        proposal="Reserved matters pursuant to planning permission APP/PARENT/1",
    )
    _add_scheme_intelligence(session, child)  # only the child has an existing intelligence row
    _add_document(session, parent, "decision_notice", "Parent's own decision notice.")

    candidates = select_historical_rebuild_candidates(session)

    assert child.id in {a.id for a in candidates}


def test_case_c_child_evidence_qualifies(session):
    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()

    trigger = _add_application(session, reference="APP/TRIGGER", site_id=site.id)
    _add_scheme_intelligence(session, trigger)
    child = _add_application(
        session, reference="APP/CHILD", site_id=site.id,
        proposal="Reserved matters pursuant to planning permission APP/TRIGGER",
    )
    _add_document(session, child, "decision_notice", "Child's own decision notice.")

    candidates = select_historical_rebuild_candidates(session)

    assert trigger.id in {a.id for a in candidates}


def test_case_d_unrelated_same_site_sibling_does_not_qualify(session):
    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()

    app = _add_application(session, reference="APP/A", site_id=site.id)
    _add_scheme_intelligence(session, app)
    # Same site, usable evidence, but does NOT cite `app` as its parent -
    # resolve_application_family must not include it (confirmed structurally
    # by test_application_family_does_not_expand_uncontrolled in B2's own
    # suite - this reconfirms the historical rebuild never broadens that).
    unrelated = _add_application(session, reference="APP/UNRELATED", site_id=site.id)
    _add_document(session, unrelated, "decision_notice", "Unrelated scheme's own decision.")

    candidates = select_historical_rebuild_candidates(session)

    assert app.id not in {a.id for a in candidates}


def test_case_e_family_document_with_null_text_does_not_qualify(session):
    parent = _add_application(session, reference="APP/PARENT/1")
    child = _add_application(
        session, reference="APP/CHILD",
        proposal="Reserved matters pursuant to planning permission APP/PARENT/1",
    )
    _add_scheme_intelligence(session, child)
    doc = Document(
        application_id=parent.id, doc_type="decision_notice", document_name="d.pdf",
        source_url="https://example.invalid/d.pdf", text_extracted=True, extracted_text=None,
    )
    session.add(doc)
    session.commit()

    candidates = select_historical_rebuild_candidates(session)

    assert child.id not in {a.id for a in candidates}


def test_case_e_family_document_with_empty_text_does_not_qualify(session):
    parent = _add_application(session, reference="APP/PARENT/1")
    child = _add_application(
        session, reference="APP/CHILD",
        proposal="Reserved matters pursuant to planning permission APP/PARENT/1",
    )
    _add_scheme_intelligence(session, child)
    doc = Document(
        application_id=parent.id, doc_type="decision_notice", document_name="d.pdf",
        source_url="https://example.invalid/d.pdf", text_extracted=True, extracted_text="",
    )
    session.add(doc)
    session.commit()

    candidates = select_historical_rebuild_candidates(session)

    assert child.id not in {a.id for a in candidates}


def test_family_document_with_irrelevant_category_does_not_qualify(session):
    parent = _add_application(session, reference="APP/PARENT/1")
    child = _add_application(
        session, reference="APP/CHILD",
        proposal="Reserved matters pursuant to planning permission APP/PARENT/1",
    )
    _add_scheme_intelligence(session, child)
    _add_document(session, parent, "other", "Not a B3-relevant category.")

    candidates = select_historical_rebuild_candidates(session)

    assert child.id not in {a.id for a in candidates}


def test_case_f_family_evidence_arriving_later_makes_row_eligible(session):
    parent = _add_application(session, reference="APP/PARENT/1")
    child = _add_application(
        session, reference="APP/CHILD",
        proposal="Reserved matters pursuant to planning permission APP/PARENT/1",
    )
    _add_scheme_intelligence(session, child)

    candidates_before = select_historical_rebuild_candidates(session)
    assert child.id not in {a.id for a in candidates_before}

    _add_document(session, parent, "decision_notice", "Parent's decision notice, added later.")

    candidates_after = select_historical_rebuild_candidates(session)
    assert child.id in {a.id for a in candidates_after}


def test_family_resolution_matches_b2s_own_resolve_application_family(session):
    """Reconfirms this module never reimplements family resolution: for a
    genuine parent/child pair, resolve_application_family's own result
    (imported directly, unchanged) is exactly what governs eligibility."""
    parent = _add_application(session, reference="APP/PARENT/1")
    child = _add_application(
        session, reference="APP/CHILD",
        proposal="Reserved matters pursuant to planning permission APP/PARENT/1",
    )
    family = resolve_application_family(session, child)
    assert {a.id for a in family} == {parent.id, child.id}


def test_blocked_family_row_does_not_consume_batch_limit(session):
    now = dt.datetime.now(dt.timezone.utc)
    blocked = _add_application(session, reference="APP/BLOCKED", last_seen_at=now)
    _add_scheme_intelligence(session, blocked)  # no family evidence anywhere
    rebuildable = _add_application(session, reference="APP/REBUILDABLE", last_seen_at=now - dt.timedelta(days=1))
    _add_scheme_intelligence(session, rebuildable)
    _add_document(session, rebuildable, "decision_notice", "Granted.")

    candidates = select_historical_rebuild_candidates(session, limit=1)

    assert [a.id for a in candidates] == [rebuildable.id]


def test_limit_returns_up_to_n_genuinely_rebuildable_rows(session):
    now = dt.datetime.now(dt.timezone.utc)
    for i in range(3):
        app = _add_application(session, reference=f"APP/BLOCKED/{i}", last_seen_at=now - dt.timedelta(days=i))
        _add_scheme_intelligence(session, app)  # no evidence anywhere
    rebuildable_ids = []
    for i in range(2):
        app = _add_application(session, reference=f"APP/OK/{i}", last_seen_at=now - dt.timedelta(days=10 + i))
        _add_scheme_intelligence(session, app)
        _add_document(session, app, "decision_notice", "Granted.")
        rebuildable_ids.append(app.id)

    candidates = select_historical_rebuild_candidates(session, limit=2)

    assert {a.id for a in candidates} == set(rebuildable_ids)


def test_old_rebuild_version_with_only_family_evidence_is_eligible_for_new_version(session):
    parent = _add_application(session, reference="APP/PARENT/1")
    child = _add_application(
        session, reference="APP/CHILD",
        proposal="Reserved matters pursuant to planning permission APP/PARENT/1",
    )
    _add_scheme_intelligence(session, child, intelligence_rebuild_version="b3_v0")
    _add_document(session, parent, "decision_notice", "Granted.")

    candidates = select_historical_rebuild_candidates(session, rebuild_version="b3_v1")

    assert child.id in {a.id for a in candidates}


def test_global_currently_rebuildable_is_family_aware(session):
    parent = _add_application(session, reference="APP/PARENT/1")
    child = _add_application(
        session, reference="APP/CHILD",
        proposal="Reserved matters pursuant to planning permission APP/PARENT/1",
    )
    _add_scheme_intelligence(session, child)
    _add_document(session, parent, "decision_notice", "Granted.")

    summary = run_historical_rebuild(session, None, dry_run=True)

    assert summary.currently_rebuildable == 1
    assert summary.blocked_no_usable_evidence == 0


def test_global_blocked_count_is_family_aware(session):
    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    app = _add_application(session, reference="APP/A", site_id=site.id)
    _add_scheme_intelligence(session, app)
    unrelated = _add_application(session, reference="APP/UNRELATED", site_id=site.id)
    _add_document(session, unrelated, "decision_notice", "Unrelated - not a family member.")

    summary = run_historical_rebuild(session, None, dry_run=True)

    assert summary.currently_rebuildable == 0
    assert summary.blocked_no_usable_evidence == 1


def test_scoped_progress_is_family_aware(session):
    parent = _add_application(session, reference="APP/PARENT/1", council_code="stockport")
    child = _add_application(
        session, reference="APP/CHILD", council_code="stockport",
        proposal="Reserved matters pursuant to planning permission APP/PARENT/1",
    )
    _add_scheme_intelligence(session, child)
    _add_document(session, parent, "decision_notice", "Granted.")

    summary = run_historical_rebuild(session, None, dry_run=True, council="stockport")

    assert summary.scope_currently_rebuildable == 1
    assert summary.scope_blocked_no_usable_evidence == 0


def test_site_filter_scope_does_not_narrow_family_evidence_source(session):
    """--site-id restricts which Applications become CANDIDATES, not where
    their family evidence may come from - a parent outside the filtered
    site must still count."""
    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()

    parent = _add_application(session, reference="APP/PARENT/1")  # no site_id at all
    child = _add_application(
        session, reference="APP/CHILD", site_id=site.id,
        proposal="Reserved matters pursuant to planning permission APP/PARENT/1",
    )
    _add_scheme_intelligence(session, child)
    _add_document(session, parent, "decision_notice", "Granted.")

    candidates = select_historical_rebuild_candidates(session, site_id=site.id)

    assert child.id in {a.id for a in candidates}


# --- Dry run (38: items 11-16) --------------------------------------------------


def test_dry_run_performs_zero_db_writes(session):
    app = _add_application(session, reference="APP/1", evidence_refresh_reason=None)
    _add_scheme_intelligence(session, app, affordable_percentage_final=20.0)
    _add_document(session, app, "decision_notice", "Some evidence.")
    client = _client_returning(_base_refresh_response())

    run_historical_rebuild(session, client, dry_run=True)

    assert client.responses.create.call_count == 0
    assert app.scheme_intelligence.affordable_percentage_final == 20.0
    assert app.scheme_intelligence.intelligence_rebuild_version is None


def test_dry_run_performs_zero_openai_calls(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Some evidence.")
    client = MagicMock()

    run_historical_rebuild(session, client, dry_run=True)

    client.responses.create.assert_not_called()


def test_dry_run_can_omit_client_entirely(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Evidence.")
    summary = run_historical_rebuild(session, None, dry_run=True)
    assert summary.selected == 1


def test_dry_run_reports_selected_candidates(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Evidence.")
    summary = run_historical_rebuild(session, None, dry_run=True)
    assert summary.candidates_inspected == 1
    assert summary.selected == 1
    assert summary.dry_run_snapshots[0].application_id == app.id


def test_dry_run_reports_evidence_counts(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Evidence one.")
    _add_document(session, app, "officer_report", "Evidence two.")
    summary = run_historical_rebuild(session, None, dry_run=True)
    snapshot = summary.dry_run_snapshots[0]
    assert snapshot.usable_document_count == 2
    assert snapshot.has_usable_evidence is True


def test_dry_run_excludes_no_usable_evidence_rows_and_reports_blocked(session):
    app_blocked = _add_application(session, reference="APP/BLOCKED")
    app_ok = _add_application(session, reference="APP/OK")
    _add_scheme_intelligence(session, app_blocked)  # no documents at all
    _add_scheme_intelligence(session, app_ok)
    _add_document(session, app_ok, "decision_notice", "Evidence.")

    summary = run_historical_rebuild(session, None, dry_run=True)

    selected_ids = {s.application_id for s in summary.dry_run_snapshots}
    assert app_ok.id in selected_ids
    assert app_blocked.id not in selected_ids
    assert summary.currently_rebuildable == 1
    assert summary.blocked_no_usable_evidence == 1


def test_dry_run_estimates_llm_call_count(session):
    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    app_with_site = _add_application(session, reference="APP/A", site_id=site.id)
    app_without_site = _add_application(session, reference="APP/B")
    _add_scheme_intelligence(session, app_with_site)
    _add_scheme_intelligence(session, app_without_site)
    _add_document(session, app_with_site, "decision_notice", "Evidence.")
    _add_document(session, app_without_site, "decision_notice", "Evidence.")

    summary = run_historical_rebuild(session, None, dry_run=True)

    # 2 calls (refresh + summary) for the site-linked app, 1 call for the
    # unlinked app - matches refresh_intelligence_for_application's own
    # `if site is not None` branch.
    assert summary.estimated_llm_calls == 3


def test_dry_run_respects_filters_and_limit(session):
    for i in range(5):
        app = _add_application(session, reference=f"APP/{i}", council_code="stockport" if i < 2 else "trafford")
        _add_scheme_intelligence(session, app)
        _add_document(session, app, "decision_notice", "Evidence.")
    summary = run_historical_rebuild(session, None, dry_run=True, council="stockport", limit=1)
    assert summary.selected == 1
    assert summary.dry_run_snapshots[0].council_code == "stockport"


# --- Success / resume (39: items 17-24) -----------------------------------------


def test_successful_rebuild_marks_rebuild_version(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")
    client = _client_returning(_base_refresh_response())

    run_historical_rebuild(session, client, dry_run=False, rebuild_version="b3_v1")

    assert app.scheme_intelligence.intelligence_rebuild_version == "b3_v1"


def test_successful_rebuild_records_rebuilt_timestamp(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")
    client = _client_returning(_base_refresh_response())

    before = dt.datetime.now(dt.timezone.utc)
    run_historical_rebuild(session, client, dry_run=False)
    after = dt.datetime.now(dt.timezone.utc)

    rebuilt_at = app.scheme_intelligence.intelligence_rebuilt_at
    assert rebuilt_at is not None
    assert before <= rebuilt_at <= after


def test_current_version_success_skipped_on_rerun(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")
    client = _client_returning(_base_refresh_response())

    run_historical_rebuild(session, client, dry_run=False, rebuild_version="b3_v1")
    assert client.responses.create.call_count >= 1
    first_call_count = client.responses.create.call_count

    # Second run at the SAME version must not touch this application again.
    run_historical_rebuild(session, client, dry_run=False, rebuild_version="b3_v1")
    assert client.responses.create.call_count == first_call_count


def test_failure_does_not_mark_rebuilt(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app, affordable_percentage_final=20.0)
    _add_document(session, app, "decision_notice", "Granted.")
    from openai import OpenAIError

    client = MagicMock()
    client.responses.create.side_effect = OpenAIError("api down")

    summary = run_historical_rebuild(session, client, dry_run=False)

    assert summary.ai_error == 1
    assert app.scheme_intelligence.intelligence_rebuild_version is None
    assert app.scheme_intelligence.affordable_percentage_final == 20.0


def test_failure_retried_on_next_run(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")
    candidates = select_historical_rebuild_candidates(session)
    assert app.id in {a.id for a in candidates}

    from openai import OpenAIError
    client = MagicMock()
    client.responses.create.side_effect = OpenAIError("api down")
    run_historical_rebuild(session, client, dry_run=False)

    candidates_after = select_historical_rebuild_candidates(session)
    assert app.id in {a.id for a in candidates_after}


def test_one_candidate_failure_does_not_affect_previous_success(session):
    app_ok = _add_application(session, reference="APP/OK", last_seen_at=dt.datetime.now(dt.timezone.utc))
    app_fail = _add_application(session, reference="APP/FAIL", last_seen_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1))
    _add_scheme_intelligence(session, app_ok, affordable_percentage_final=10.0)
    _add_scheme_intelligence(session, app_fail, affordable_percentage_final=20.0)
    _add_document(session, app_ok, "decision_notice", "Granted.")
    _add_document(session, app_fail, "decision_notice", "Granted.")

    from openai import OpenAIError

    call_count = {"n": 0}

    def _dispatch(model, input, text):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return MagicMock(output_text=json.dumps(_base_refresh_response(affordable_percentage=99.0)))
        raise OpenAIError("api down")

    client = MagicMock()
    client.responses.create.side_effect = _dispatch

    summary = run_historical_rebuild(session, client, dry_run=False)

    assert summary.success == 1
    assert summary.ai_error == 1
    assert app_ok.scheme_intelligence.affordable_percentage_final == 99.0
    assert app_ok.scheme_intelligence.intelligence_rebuild_version == REBUILD_VERSION
    assert app_fail.scheme_intelligence.affordable_percentage_final == 20.0  # untouched
    assert app_fail.scheme_intelligence.intelligence_rebuild_version is None


def test_atomic_b3_replacement_preserved_on_summary_failure(session, monkeypatch):
    def failing_generate_scheme_summary(client, site, applications, merged, lapse, phase_breakdown):
        raise RuntimeError("summary generation failed")

    monkeypatch.setattr("app.reporting.scheme_summary.generate_scheme_summary", failing_generate_scheme_summary)

    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    app = _add_application(session, reference="APP/1", site_id=site.id)
    site.status_summary = "Old summary"
    _add_scheme_intelligence(session, app, affordable_percentage_final=20.0)
    _add_document(session, app, "decision_notice", "Granted.")
    session.commit()

    client = _client_returning(_base_refresh_response(affordable_percentage=99.0))
    summary = run_historical_rebuild(session, client, dry_run=False)

    assert summary.error == 1
    assert app.scheme_intelligence.affordable_percentage_final == 20.0
    assert site.status_summary == "Old summary"
    assert app.scheme_intelligence.intelligence_rebuild_version is None


def test_no_duplicate_openai_work_for_successful_rows(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")
    client = _client_returning(_base_refresh_response())

    run_historical_rebuild(session, client, dry_run=False)
    calls_after_first = client.responses.create.call_count

    # Rerun with a fresh mock to prove NO candidates remain, not merely
    # that the same mock wasn't called again.
    fresh_client = MagicMock()
    summary = run_historical_rebuild(session, fresh_client, dry_run=False)
    assert summary.selected == 0
    fresh_client.responses.create.assert_not_called()
    assert calls_after_first >= 1


# --- QA (40: items 25-30) -------------------------------------------------------


def test_tenure_narrative_mismatch_detected():
    assert detect_tenure_narrative_mismatch(
        "Shared Ownership, Rent to Buy",
        "16 for social rent and 57 for shared ownership.",
    ) is True


def test_clean_tenure_position_no_mismatch():
    assert detect_tenure_narrative_mismatch(
        "16 social rent, 57 shared ownership",
        "16 for social rent and 57 for shared ownership.",
    ) is False


def test_tenure_mismatch_missing_inputs_no_warning():
    assert detect_tenure_narrative_mismatch(None, "16 for social rent.") is False
    assert detect_tenure_narrative_mismatch("Shared Ownership", None) is False


def test_complex_site_flagged():
    site = MagicMock(applications=[MagicMock() for _ in range(COMPLEX_SITE_APPLICATION_THRESHOLD)])
    assert is_complex_site(site) is True


def test_ordinary_small_site_not_flagged():
    site = MagicMock(applications=[MagicMock() for _ in range(3)])
    assert is_complex_site(site) is False


def test_qa_warning_end_to_end_flags_tenure_mismatch(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app, affordable_tenure_split_final="Shared Ownership, Rent to Buy")
    _add_document(session, app, "viability_affordable_housing", "16 social rent, 57 shared ownership.")
    client = _client_returning(_base_refresh_response(
        # Structured field intentionally left unchanged (None -> falls
        # back to existing stale value), while notes mention social rent -
        # exactly the live-validation defect shape.
        affordable_tenure_split=None,
        affordable_housing_notes="16 for social rent and 57 for shared ownership are proposed.",
    ))

    summary = run_historical_rebuild(session, client, dry_run=False)

    assert summary.success_with_warning == 1
    assert summary.tenure_mismatch_warnings == 1
    result = summary.results[0]
    assert QA_TENURE_NARRATIVE_MISMATCH in result.qa_warnings
    assert result.rebuilt is True  # non-blocking (item 30)


def test_qa_does_not_mutate_application_status_or_decision(session):
    app = _add_application(session, reference="APP/1", status="Decided", decision="Refuse")
    _add_scheme_intelligence(session, app, affordable_tenure_split_final="Shared Ownership, Rent to Buy")
    _add_document(session, app, "viability_affordable_housing", "16 social rent proposed.")
    client = _client_returning(_base_refresh_response(
        affordable_housing_notes="16 for social rent are proposed.",
    ))

    run_historical_rebuild(session, client, dry_run=False)

    assert app.status == "Decided"
    assert app.decision == "Refuse"


def test_complex_site_warning_end_to_end(session):
    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    target = _add_application(session, reference="APP/TARGET", site_id=site.id, last_seen_at=dt.datetime.now(dt.timezone.utc))
    for i in range(COMPLEX_SITE_APPLICATION_THRESHOLD - 1):
        _add_application(session, reference=f"APP/SIBLING{i}", site_id=site.id)
    _add_scheme_intelligence(session, target)
    _add_document(session, target, "decision_notice", "Granted.")
    client = _summary_client()

    summary = run_historical_rebuild(session, client, dry_run=False, application_id=target.id)

    assert summary.complex_site_warnings == 1
    assert QA_SITE_SUMMARY_COMPLEX_SITE in summary.results[0].qa_warnings
    assert summary.results[0].rebuilt is True


def test_ordinary_site_no_complex_warning(session):
    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    app = _add_application(session, reference="APP/1", site_id=site.id)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")
    client = _summary_client()

    summary = run_historical_rebuild(session, client, dry_run=False)

    assert summary.complex_site_warnings == 0
    assert summary.success == 1


# --- B3 safety reconfirmation (41: items 31-36) ---------------------------------


def test_mixed_s106_position_not_overclaimed_during_rebuild(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app, affordable_percentage_final=10.2, affordable_units_final=15)
    _add_document(session, app, "s106", "Completed S106 secures the base 10% requirement.")
    _add_document(session, app, "viability_affordable_housing", "An additional 40% non-s106 affordable homes are proposed.")
    client = _client_returning(_base_refresh_response(
        affordable_percentage=50.0, affordable_units=73,
        affordable_housing_status=LEGALLY_SECURED_STATUS, affordable_provision_fully_legally_secured=False,
        affordable_housing_notes="The S106 secures the base 10%; a further 40% non-S106 provision brings the total to 50%.",
    ))

    run_historical_rebuild(session, client, dry_run=False)

    assert app.scheme_intelligence.affordable_housing_status != LEGALLY_SECURED_STATUS


def test_fully_secured_position_still_legally_secured_during_rebuild(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app, affordable_housing_status="proposed")
    _add_document(session, app, "s106", "This executed S106 Agreement legally secures the entire affordable housing provision.")
    client = _client_returning(_base_refresh_response(
        affordable_percentage=50.0, affordable_housing_status=LEGALLY_SECURED_STATUS,
        affordable_provision_fully_legally_secured=True,
    ))

    run_historical_rebuild(session, client, dry_run=False)

    assert app.scheme_intelligence.affordable_housing_status == LEGALLY_SECURED_STATUS


def test_refusal_reason_extracted_during_rebuild(session):
    app = _add_application(session, reference="APP/1", decision="Refuse")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "REFUSED for the following\nreason:\n1. Green Belt harm.")
    client = _client_returning(_base_refresh_response(refusal_reasons="Green Belt harm."))

    run_historical_rebuild(session, client, dry_run=False)

    assert app.scheme_intelligence.refusal_reasons == "Green Belt harm."


def test_no_refusal_reason_fabricated_during_rebuild(session):
    app = _add_application(session, reference="APP/1", decision="Refuse")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "The application is refused, no further detail here.")
    client = _client_returning(_base_refresh_response(refusal_reasons=None))

    run_historical_rebuild(session, client, dry_run=False)

    assert app.scheme_intelligence.refusal_reasons is None


def test_site_summary_prospective_state_still_works_during_rebuild(session, monkeypatch):
    captured = {}

    def fake_generate_scheme_summary(client, site, applications, merged, lapse, phase_breakdown):
        captured["merged"] = dict(merged)
        return "New summary reflecting the rebuild."

    monkeypatch.setattr("app.reporting.scheme_summary.generate_scheme_summary", fake_generate_scheme_summary)

    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    app = _add_application(session, reference="APP/1", site_id=site.id)
    _add_scheme_intelligence(session, app, affordable_housing_notes="Old notes.")
    _add_document(session, app, "decision_notice", "Granted, 40% affordable housing secured.")
    client = _client_returning(_base_refresh_response(
        affordable_percentage=40.0, affordable_housing_status="agreed",
        affordable_housing_notes="40% affordable housing is now agreed.",
    ))

    run_historical_rebuild(session, client, dry_run=False)

    assert captured["merged"]["affordable_housing_notes"] == "40% affordable housing is now agreed."


def test_recommendation_vs_formal_decision_distinction_intact_during_rebuild(session):
    app = _add_application(session, reference="APP/1", status="Awaiting decision", decision=None)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "officer_report", "RECOMMENDATION: MINDED TO GRANT.")
    client = _client_returning(_base_refresh_response(
        recommendation_direction="approval", formal_decision_outstanding=True,
    ))

    run_historical_rebuild(session, client, dry_run=False)

    assert app.scheme_intelligence.recommendation_direction == "approval"
    assert app.scheme_intelligence.formal_decision_outstanding is True


# --- Historical watermark safety (42: items 37-40) ------------------------------


def test_rebuild_does_not_fabricate_intelligence_evidence_processed_at(session):
    app = _add_application(session, reference="APP/1", material_evidence_changed_at=None)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")
    client = _client_returning(_base_refresh_response())

    run_historical_rebuild(session, client, dry_run=False)

    assert app.intelligence_evidence_processed_at is None  # copied from material_evidence_changed_at, still None


def test_rebuild_completion_tracked_separately_from_watermark(session):
    app = _add_application(session, reference="APP/1", material_evidence_changed_at=None)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")
    client = _client_returning(_base_refresh_response())

    run_historical_rebuild(session, client, dry_run=False, rebuild_version="b3_v1")

    assert app.scheme_intelligence.intelligence_rebuild_version == "b3_v1"
    assert app.intelligence_evidence_processed_at is None


def test_future_material_evidence_change_still_triggers_normal_b3_after_rebuild(session):
    now = dt.datetime.now(dt.timezone.utc)
    app = _add_application(session, reference="APP/1", material_evidence_changed_at=None)
    _add_scheme_intelligence(session, app, intelligence_rebuild_version=REBUILD_VERSION, intelligence_rebuilt_at=now)

    # Simulate a genuine later B2 evidence-refresh advancing the watermark.
    app.material_evidence_changed_at = now
    session.commit()

    candidates = session.execute(select(Application).where(INTELLIGENCE_REFRESH_ELIGIBLE)).scalars().all()
    assert app.id in {a.id for a in candidates}


def test_normal_b3_eligibility_query_unaffected_by_rebuild_marker(session):
    now = dt.datetime.now(dt.timezone.utc)
    app = _add_application(
        session, reference="APP/1",
        material_evidence_changed_at=now, intelligence_evidence_processed_at=now,
    )
    _add_scheme_intelligence(session, app, intelligence_rebuild_version=None)
    candidates = session.execute(select(Application).where(INTELLIGENCE_REFRESH_ELIGIBLE)).scalars().all()
    assert app.id not in {a.id for a in candidates}  # watermark equal -> not eligible, regardless of rebuild marker


# --- Limit / safety (43: items 41-44) -------------------------------------------


def test_default_batch_size_is_bounded():
    assert DEFAULT_BATCH_LIMIT == 25


def test_large_batch_rejected_without_override(session):
    with pytest.raises(ValueError):
        run_historical_rebuild(session, None, dry_run=True, limit=MAX_BATCH_LIMIT_WITHOUT_OVERRIDE + 1)


def test_large_batch_override_works(session):
    for i in range(3):
        app = _add_application(session, reference=f"APP/{i}")
        _add_scheme_intelligence(session, app)
        _add_document(session, app, "decision_notice", "Granted.")
    summary = run_historical_rebuild(
        session, None, dry_run=True, limit=MAX_BATCH_LIMIT_WITHOUT_OVERRIDE + 1, allow_large_batch=True,
    )
    assert summary.selected == 3  # bounded by actual candidates, not the raised limit


def test_no_unbounded_default_run(session):
    for i in range(3):
        app = _add_application(session, reference=f"APP/{i}")
        _add_scheme_intelligence(session, app)
    # Calling with no explicit limit uses DEFAULT_BATCH_LIMIT, never unbounded.
    summary = run_historical_rebuild(session, None, dry_run=True)
    assert summary.candidates_inspected <= DEFAULT_BATCH_LIMIT


# --- Migration safety (Section 36) ----------------------------------------------


def test_rebuild_marker_columns_are_nullable():
    from sqlalchemy import inspect as sa_inspect

    mapper = sa_inspect(SchemeIntelligence)
    for name in ("intelligence_rebuild_version", "intelligence_rebuilt_at"):
        column = mapper.columns[name]
        assert column.nullable is True, f"SchemeIntelligence.{name} must be nullable"


def test_rebuild_marker_covered_by_generic_add_missing_columns_no_new_backfill():
    """Same additive-only, no-backfill-needed pattern as every prior B1/B2/
    B3 nullable column addition - app.db.session._add_missing_columns'
    existing generic ADD COLUMN mechanism is sufficient; old rows are
    correctly left NULL (never fabricated as already-rebuilt) by a bare
    ALTER TABLE ADD COLUMN with no DEFAULT clause."""
    import inspect as py_inspect

    import app.db.session as db_session_module

    source = py_inspect.getsource(db_session_module)
    for name in ("intelligence_rebuild_version", "intelligence_rebuilt_at"):
        assert f"_backfill_{name}" not in source


# ==============================================================================
# FINAL PRE-MERGE AMENDMENT: rebuild-marker atomicity + explicit progress
# ==============================================================================

# --- Issue A: rebuild-marker transaction atomicity ------------------------------


def test_atomic_rebuild_commits_intelligence_summary_and_marker_together(session, monkeypatch):
    def fake_generate_scheme_summary(client, site, applications, merged, lapse, phase_breakdown):
        return "Rebuilt summary."

    monkeypatch.setattr("app.reporting.scheme_summary.generate_scheme_summary", fake_generate_scheme_summary)

    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    app = _add_application(session, reference="APP/1", site_id=site.id)
    _add_scheme_intelligence(session, app, affordable_percentage_final=20.0)
    _add_document(session, app, "decision_notice", "Granted, 40% affordable housing secured.")
    client = _client_returning(_base_refresh_response(affordable_percentage=40.0, affordable_housing_status="agreed"))

    run_historical_rebuild(session, client, dry_run=False)

    assert app.scheme_intelligence.affordable_percentage_final == 40.0
    assert site.status_summary == "Rebuilt summary."
    assert app.scheme_intelligence.intelligence_rebuild_version == REBUILD_VERSION
    assert app.scheme_intelligence.intelligence_rebuilt_at is not None


def test_site_summary_failure_leaves_marker_null_alongside_old_intelligence(session, monkeypatch):
    def failing_generate_scheme_summary(client, site, applications, merged, lapse, phase_breakdown):
        raise RuntimeError("summary generation failed")

    monkeypatch.setattr("app.reporting.scheme_summary.generate_scheme_summary", failing_generate_scheme_summary)

    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    app = _add_application(session, reference="APP/1", site_id=site.id)
    site.status_summary = "Old summary"
    _add_scheme_intelligence(session, app, affordable_percentage_final=20.0)
    _add_document(session, app, "decision_notice", "Granted.")
    session.commit()

    client = _client_returning(_base_refresh_response(affordable_percentage=99.0))
    summary = run_historical_rebuild(session, client, dry_run=False)

    assert summary.error == 1
    assert app.scheme_intelligence.affordable_percentage_final == 20.0
    assert site.status_summary == "Old summary"
    assert app.scheme_intelligence.intelligence_rebuild_version is None
    assert app.scheme_intelligence.intelligence_rebuilt_at is None


def test_invalid_ai_output_does_not_mark_rebuilt(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app, affordable_percentage_final=20.0)
    _add_document(session, app, "decision_notice", "Granted.")
    client = MagicMock()
    client.responses.create.return_value = MagicMock(output_text="{not valid json")

    summary = run_historical_rebuild(session, client, dry_run=False)

    assert summary.invalid_output == 1
    assert app.scheme_intelligence.affordable_percentage_final == 20.0
    assert app.scheme_intelligence.intelligence_rebuild_version is None


def test_ai_error_does_not_mark_rebuilt(session):
    from openai import OpenAIError

    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app, affordable_percentage_final=20.0)
    _add_document(session, app, "decision_notice", "Granted.")
    client = MagicMock()
    client.responses.create.side_effect = OpenAIError("api down")

    summary = run_historical_rebuild(session, client, dry_run=False)

    assert summary.ai_error == 1
    assert app.scheme_intelligence.intelligence_rebuild_version is None


def test_db_commit_failure_does_not_leave_false_rebuild_marker(session, monkeypatch):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app, affordable_percentage_final=20.0)
    _add_document(session, app, "decision_notice", "Granted.")
    client = _client_returning(_base_refresh_response(affordable_percentage=99.0))

    real_commit = session.commit
    call_count = {"n": 0}

    def flaky_commit():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise Exception("simulated DB failure")
        real_commit()

    monkeypatch.setattr(session, "commit", flaky_commit)

    summary = run_historical_rebuild(session, client, dry_run=False)

    assert summary.error == 1
    assert summary.results[0].rebuilt is False
    # session.rollback() (called by our own defensive handler) reverts the
    # in-memory ORM state back to what was actually persisted - never a
    # false "rebuilt" marker despite the setattr calls having run in memory
    # before the failed commit.
    assert app.scheme_intelligence.intelligence_rebuild_version is None
    assert app.scheme_intelligence.affordable_percentage_final == 20.0


def test_one_candidate_db_failure_does_not_block_next_candidate(session, monkeypatch):
    app_fail = _add_application(session, reference="APP/FAIL", last_seen_at=dt.datetime.now(dt.timezone.utc))
    app_ok = _add_application(session, reference="APP/OK", last_seen_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1))
    _add_scheme_intelligence(session, app_fail)
    _add_scheme_intelligence(session, app_ok)
    _add_document(session, app_fail, "decision_notice", "Granted.")
    _add_document(session, app_ok, "decision_notice", "Granted.")
    client = _client_returning(_base_refresh_response())

    real_commit = session.commit
    call_count = {"n": 0}

    def flaky_commit():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise Exception("simulated DB failure")
        real_commit()

    monkeypatch.setattr(session, "commit", flaky_commit)

    summary = run_historical_rebuild(session, client, dry_run=False)

    assert summary.error == 1
    assert summary.success == 1
    assert app_fail.scheme_intelligence.intelligence_rebuild_version is None
    assert app_ok.scheme_intelligence.intelligence_rebuild_version == REBUILD_VERSION


# --- Issue A: normal B3 unaffected ----------------------------------------------


def test_normal_b3_refresh_never_sets_historical_rebuild_markers(session):
    from app.pipeline.material_change import REASON_DECISION_GRANTED

    app = _add_application(session, reference="APP/1", evidence_refresh_reason=REASON_DECISION_GRANTED)
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")
    client = _client_returning(_base_refresh_response())

    from app.extraction.intelligence_refresh import refresh_intelligence_for_application

    outcome = refresh_intelligence_for_application(
        session, client, app, generate_summary=lambda site, applications: "Summary text.",
    )

    assert outcome.outcome == OUTCOME_SUCCESS
    assert app.scheme_intelligence.intelligence_rebuild_version is None
    assert app.scheme_intelligence.intelligence_rebuilt_at is None


# --- Issue B: explicit rebuild progress ------------------------------------------


def test_progress_reports_global_corpus_and_already_rebuilt(session):
    app1 = _add_application(session, reference="APP/1")
    app2 = _add_application(session, reference="APP/2")
    _add_scheme_intelligence(session, app1, intelligence_rebuild_version=REBUILD_VERSION)
    _add_scheme_intelligence(session, app2)
    _add_document(session, app2, "decision_notice", "Granted.")

    summary = run_historical_rebuild(session, None, dry_run=True)

    assert summary.total_historical_corpus == 2
    assert summary.already_rebuilt_before == 1
    assert summary.remaining_rebuildable_before == 1


def test_already_rebuilt_row_excluded_from_batch_but_counted_in_progress(session):
    app1 = _add_application(session, reference="APP/1")
    app2 = _add_application(session, reference="APP/2")
    _add_scheme_intelligence(session, app1, intelligence_rebuild_version=REBUILD_VERSION)
    _add_scheme_intelligence(session, app2)
    _add_document(session, app2, "decision_notice", "Granted.")

    summary = run_historical_rebuild(session, None, dry_run=True)

    assert summary.selected == 1  # only app2 - app1 already rebuilt
    assert summary.already_rebuilt_before == 1  # app1 still counted in progress


def test_older_rebuild_version_counted_as_remaining_for_new_version(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app, intelligence_rebuild_version="b3_v0")
    _add_document(session, app, "decision_notice", "Granted.")

    summary = run_historical_rebuild(session, None, dry_run=True, rebuild_version="b3_v1")

    assert summary.already_rebuilt_before == 0
    assert summary.remaining_rebuildable_before == 1


def test_filter_scoped_progress_differs_from_global(session):
    app_a = _add_application(session, reference="APP/A", council_code="stockport")
    app_b = _add_application(session, reference="APP/B", council_code="trafford")
    _add_scheme_intelligence(session, app_a)
    _add_scheme_intelligence(session, app_b, intelligence_rebuild_version=REBUILD_VERSION)

    summary = run_historical_rebuild(session, None, dry_run=True, council="stockport")

    assert summary.total_historical_corpus == 2  # global - both applications
    assert summary.already_rebuilt_before == 1  # global - app_b
    assert summary.scope_total_historical == 1  # scoped to stockport only - app_a
    assert summary.scope_already_rebuilt_before == 0  # app_a not rebuilt


def test_dry_run_progress_before_equals_after(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")

    summary = run_historical_rebuild(session, None, dry_run=True)

    assert summary.already_rebuilt_after == summary.already_rebuilt_before
    assert summary.remaining_rebuildable_after == summary.remaining_rebuildable_before
    assert summary.scope_already_rebuilt_after == summary.scope_already_rebuilt_before
    assert summary.scope_remaining_rebuildable_after == summary.scope_remaining_rebuildable_before


def test_live_batch_progress_before_and_after_reflect_new_rebuilds(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    _add_document(session, app, "decision_notice", "Granted.")
    client = _client_returning(_base_refresh_response())

    summary = run_historical_rebuild(session, client, dry_run=False)

    assert summary.already_rebuilt_before == 0
    assert summary.already_rebuilt_after == 1
    assert summary.remaining_rebuildable_before == 1
    assert summary.remaining_rebuildable_after == 0


def test_progress_distinguishes_blocked_from_rebuildable(session):
    app_blocked = _add_application(session, reference="APP/BLOCKED")
    app_rebuildable = _add_application(session, reference="APP/REBUILDABLE")
    app_rebuilt = _add_application(session, reference="APP/REBUILT")
    _add_scheme_intelligence(session, app_blocked)  # no documents
    _add_scheme_intelligence(session, app_rebuildable)
    _add_scheme_intelligence(session, app_rebuilt, intelligence_rebuild_version=REBUILD_VERSION)
    _add_document(session, app_rebuildable, "decision_notice", "Granted.")
    _add_document(session, app_rebuilt, "decision_notice", "Granted.")

    summary = run_historical_rebuild(session, None, dry_run=True)

    assert summary.total_historical_corpus == 3
    assert summary.currently_rebuildable == 2  # app_rebuildable + app_rebuilt
    assert summary.blocked_no_usable_evidence == 1  # app_blocked
    assert summary.already_rebuilt_before == 1  # app_rebuilt
    assert summary.remaining_rebuildable_before == 1  # app_rebuildable only


def test_no_extra_openai_calls_from_progress_queries(session):
    app = _add_application(session, reference="APP/1")
    _add_scheme_intelligence(session, app)
    client = MagicMock()

    run_historical_rebuild(session, client, dry_run=True)

    client.responses.create.assert_not_called()
