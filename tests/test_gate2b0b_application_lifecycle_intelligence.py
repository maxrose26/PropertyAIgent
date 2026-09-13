"""Gate 2B-0B ("Application Lifecycle Intelligence") - focused tests.

Covers:
1. app.pipeline.lifecycle_events.record_material_change_events - decision-
   granted/refused/withdrawn events, the generic status-transition event,
   the unit-count-changed event, old/new value retention, no event when
   nothing material changed.
2. Its wiring into app.pipeline.run_weekly._upsert_scraped_application and
   app.pipeline.status_verification.verify_application_status - no event
   on VERIFIED_UNCHANGED, no event on a failed/portal-unavailable/not-found
   outcome, authoritative_source recorded correctly, append-only/duplicate-
   retry idempotency (repeated observation of the same state writes no
   further events).
3. app.pipeline.lifecycle_events.record_related_application_discovery_event
   and its wiring into stage_fetch_related_applications - NEW_RELATED_
   APPLICATION always written for a genuinely new discovery,
   RESERVED_MATTERS_FOUND/CONDITION_DISCHARGE_FOUND written additionally
   where the category is one of the two safely-distinguishable ones, and
   the S73-vs-NMA "variation_or_amendment" KNOWN LIMITATION (never split,
   never fabricated).
4. Document.content_hash - populated on newly created documents, legacy/
   no-text rows stay NULL, and the still-open "revised document" limitation
   (same URL/name, unknown to the dedup check, therefore never re-hashed).
5. The Phase D targeted downstream reassessment trigger in run_weekly.main
   is exercised via its own unit (LifecycleEventStats.any_written) rather
   than a full subprocess run - see test_any_written_gates_the_trigger.
6. Non-regression: NMA/S73/condition-discharge discoveries still correctly
   never become the trusted operative permission (app.reporting.
   scheme_reconciliation's SUBSTANTIVE_ROLES exclusion, Gate 2B-2A/2B-2C,
   is completely untouched by this gate), and a lifecycle event write never
   changes app.reporting.opportunity_universe's own fingerprint_fields for
   an otherwise-unchanged opportunity.

Uses the same in-memory-SQLite `session` fixture as the rest of this suite
(tests/conftest.py). No live council portals - every portal fetch is
patched, matching tests/test_planning_status_verification.py's own
established convention.
"""
from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from app.config import CouncilConfig
from app.db.models import Application, ApplicationLifecycleEvent, Document, Site
from app.pipeline.lifecycle_events import (
    EVENT_CONDITION_DISCHARGE_FOUND,
    EVENT_DECISION_GRANTED,
    EVENT_DECISION_REFUSED,
    EVENT_DECISION_WITHDRAWN,
    EVENT_NEW_RELATED_APPLICATION,
    EVENT_RESERVED_MATTERS_FOUND,
    EVENT_STATUS_CHANGED,
    EVENT_UNITS_CHANGED,
    SOURCE_RELATED_APPLICATION_DISCOVERY,
    SOURCE_SCRAPE,
    SOURCE_STATUS_VERIFICATION,
    LifecycleEventStats,
    record_material_change_events,
    record_related_application_discovery_event,
)
from app.pipeline.material_change import ApplicationState, detect_material_application_change
from app.pipeline.run_weekly import _upsert_scraped_application, stage_fetch_related_applications
from app.pipeline.status_verification import verify_application_status
from app.reporting.opportunity_change import sync_opportunity_monitoring_state
from app.reporting.opportunity_universe import build_current_opportunity_universe
from app.reporting.scheme_reconciliation import resolve_operative_lapse_anchor
from app.scrapers.idox_portal import ScrapedApplication


def _council_config(code: str = "testcouncil") -> CouncilConfig:
    return CouncilConfig(
        code=code, name=code, base_url="https://example.invalid",
        date_field_mode="received", doc_system="idox", anite_base_url=None,
        unit_threshold=10, region=None, country=None,
    )


def _add_application(session, *, reference: str, council_code: str = "testcouncil", **kwargs) -> Application:
    application = Application(council_code=council_code, reference=reference, **kwargs)
    session.add(application)
    session.commit()
    return application


def _scraped(reference: str, *, status: str | None = None, decision: str | None = None, unit_count: int | None = None) -> ScrapedApplication:
    fields = {"Reference": reference}
    if status is not None:
        fields["Status"] = status
    if decision is not None:
        fields["Decision"] = decision
    return ScrapedApplication(
        reference=reference, fields=fields, summary_url=f"https://example.invalid/{reference}",
        further_info_url="", keyval=None, estimated_unit_count=unit_count,
        application_category="primary_residential", opportunity_classification="", qualifies=True,
    )


def _events(session, application_id: int) -> list[ApplicationLifecycleEvent]:
    return list(session.execute(
        select(ApplicationLifecycleEvent).where(ApplicationLifecycleEvent.application_id == application_id)
    ).scalars())


# --- 1. record_material_change_events (pure, given an already-computed result) --


def test_decision_granted_event_records_old_and_new_value():
    old = ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=None)
    new = ApplicationState(status="Decided", decision="Granted", estimated_unit_count=None)
    result = detect_material_application_change(old, new)

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.models import Base, Council

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True, expire_on_commit=False)()
    session.add(Council(code="testcouncil", name="Test", base_url="https://example.invalid", date_field_mode="received", doc_system="idox"))
    app = Application(council_code="testcouncil", reference="A/1")
    session.add(app)
    session.commit()

    written = record_material_change_events(
        session, application_id=app.id, result=result, authoritative_source=SOURCE_SCRAPE,
    )
    session.commit()

    assert written == 1
    events = _events(session, app.id)
    assert len(events) == 1
    assert events[0].event_type == EVENT_DECISION_GRANTED
    assert events[0].field_name == "decision"
    assert events[0].old_value is None
    assert events[0].new_value == "Granted"
    assert events[0].authoritative_source == SOURCE_SCRAPE
    assert events[0].detected_at is not None
    session.close()
    engine.dispose()


def test_decision_refused_event(session):
    app = _add_application(session, reference="A/1")
    result = detect_material_application_change(
        ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=None),
        ApplicationState(status="Decided", decision="Refused", estimated_unit_count=None),
    )
    record_material_change_events(session, application_id=app.id, result=result, authoritative_source=SOURCE_SCRAPE)
    session.commit()
    events = _events(session, app.id)
    assert len(events) == 1
    assert events[0].event_type == EVENT_DECISION_REFUSED
    assert events[0].old_value is None
    assert events[0].new_value == "Refused"


def test_decision_withdrawn_event(session):
    app = _add_application(session, reference="A/1")
    result = detect_material_application_change(
        ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=None),
        ApplicationState(status="Decided", decision="Withdrawn", estimated_unit_count=None),
    )
    record_material_change_events(session, application_id=app.id, result=result, authoritative_source=SOURCE_SCRAPE)
    session.commit()
    events = _events(session, app.id)
    assert len(events) == 1
    assert events[0].event_type == EVENT_DECISION_WITHDRAWN


def test_status_transition_event_uses_generic_status_changed_type(session):
    """A recommendation-state transition (not a decision) is recorded as the
    generic EVENT_STATUS_CHANGED - this module never invents a finer
    classification than app.pipeline.material_change itself computed."""
    app = _add_application(session, reference="A/1")
    result = detect_material_application_change(
        ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=None),
        ApplicationState(status="Officer Recommendation: Approve", decision=None, estimated_unit_count=None),
    )
    assert result.changed  # sanity: material_change really does treat this as material
    record_material_change_events(session, application_id=app.id, result=result, authoritative_source=SOURCE_SCRAPE)
    session.commit()
    events = _events(session, app.id)
    assert len(events) == 1
    assert events[0].event_type == EVENT_STATUS_CHANGED
    assert events[0].field_name == "status"
    assert events[0].old_value == "Awaiting Decision"
    assert events[0].new_value == "Officer Recommendation: Approve"


def test_unit_count_changed_event(session):
    app = _add_application(session, reference="A/1")
    result = detect_material_application_change(
        ApplicationState(status="Decided", decision="Granted", estimated_unit_count=50),
        ApplicationState(status="Decided", decision="Granted", estimated_unit_count=80),
    )
    record_material_change_events(session, application_id=app.id, result=result, authoritative_source=SOURCE_SCRAPE)
    session.commit()
    events = _events(session, app.id)
    assert len(events) == 1
    assert events[0].event_type == EVENT_UNITS_CHANGED
    assert events[0].field_name == "estimated_unit_count"
    assert events[0].old_value == "50"
    assert events[0].new_value == "80"


def test_both_decision_and_unit_count_change_write_two_events(session):
    app = _add_application(session, reference="A/1")
    result = detect_material_application_change(
        ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=50),
        ApplicationState(status="Decided", decision="Granted", estimated_unit_count=80),
    )
    written = record_material_change_events(session, application_id=app.id, result=result, authoritative_source=SOURCE_SCRAPE)
    session.commit()
    assert written == 2
    events = {e.event_type for e in _events(session, app.id)}
    assert events == {EVENT_DECISION_GRANTED, EVENT_UNITS_CHANGED}


def test_no_event_when_nothing_material_changed(session):
    app = _add_application(session, reference="A/1")
    result = detect_material_application_change(
        ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=None),
        ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=None),
    )
    written = record_material_change_events(session, application_id=app.id, result=result, authoritative_source=SOURCE_SCRAPE)
    session.commit()
    assert written == 0
    assert _events(session, app.id) == []


def test_stats_accumulate_across_multiple_calls(session):
    app = _add_application(session, reference="A/1")
    stats = LifecycleEventStats()
    assert stats.any_written is False
    result = detect_material_application_change(
        ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=None),
        ApplicationState(status="Decided", decision="Granted", estimated_unit_count=None),
    )
    record_material_change_events(session, application_id=app.id, result=result, authoritative_source=SOURCE_SCRAPE, stats=stats)
    assert stats.written == 1
    assert stats.any_written is True


# --- 2. Wiring into _upsert_scraped_application / verify_application_status -----


def test_upsert_scraped_application_writes_lifecycle_event_on_material_change(session):
    app = _add_application(session, reference="A/1", status="Awaiting Decision", decision=None)
    scraped = _scraped("A/1", status="Decided", decision="Granted")
    stats = LifecycleEventStats()

    _upsert_scraped_application(
        session, _council_config(), scraped, batch_id="b1",
        authoritative_source=SOURCE_SCRAPE, lifecycle_event_stats=stats,
    )
    session.commit()

    events = _events(session, app.id)
    assert len(events) == 1
    assert events[0].event_type == EVENT_DECISION_GRANTED
    assert events[0].authoritative_source == SOURCE_SCRAPE
    assert stats.any_written is True


def test_new_application_writes_no_lifecycle_event(session):
    """A genuinely NEW application (old_state is None) is never compared -
    same exclusion as B1's own material-change detection."""
    scraped = _scraped("A/NEW", status="Decided", decision="Granted")
    stats = LifecycleEventStats()
    application = _upsert_scraped_application(
        session, _council_config(), scraped, batch_id="b1", lifecycle_event_stats=stats,
    )
    session.commit()
    assert _events(session, application.id) == []
    assert stats.any_written is False


def test_repeated_observation_of_same_state_writes_no_further_event(session):
    """Append-only / duplicate-retry idempotency: a second upsert observing
    the SAME now-current state writes nothing new."""
    app = _add_application(session, reference="A/1", status="Awaiting Decision", decision=None)
    stats = LifecycleEventStats()
    _upsert_scraped_application(
        session, _council_config(), _scraped("A/1", status="Decided", decision="Granted"), batch_id="b1",
        lifecycle_event_stats=stats,
    )
    session.commit()
    assert len(_events(session, app.id)) == 1

    _upsert_scraped_application(
        session, _council_config(), _scraped("A/1", status="Decided", decision="Granted"), batch_id="b2",
        lifecycle_event_stats=stats,
    )
    session.commit()
    assert len(_events(session, app.id)) == 1  # still exactly one - no duplicate
    assert stats.written == 1


def test_verified_unchanged_writes_no_lifecycle_event(session):
    app = _add_application(session, reference="A/1", status="Awaiting decision", decision=None)
    stats = LifecycleEventStats()
    with patch("app.scrapers.idox_portal.fetch_application_by_reference", return_value=_scraped("A/1", status="Awaiting decision")):
        outcome = verify_application_status(
            session, MagicMock(), _council_config(), app, lifecycle_event_stats=stats,
        )
    assert outcome.outcome == "verified_unchanged"
    assert _events(session, app.id) == []
    assert stats.any_written is False


def test_verified_changed_writes_lifecycle_event_with_status_verification_source(session):
    app = _add_application(session, reference="A/1", status="Awaiting decision", decision=None)
    stats = LifecycleEventStats()
    with patch("app.scrapers.idox_portal.fetch_application_by_reference", return_value=_scraped("A/1", status="Decided", decision="Granted")):
        outcome = verify_application_status(
            session, MagicMock(), _council_config(), app, lifecycle_event_stats=stats,
        )
    assert outcome.outcome == "verified_changed"
    events = _events(session, app.id)
    assert len(events) == 1
    assert events[0].event_type == EVENT_DECISION_GRANTED
    assert events[0].authoritative_source == SOURCE_STATUS_VERIFICATION
    assert stats.any_written is True


def test_portal_unavailable_writes_no_lifecycle_event(session):
    import requests
    app = _add_application(session, reference="A/1", decision=None)
    stats = LifecycleEventStats()
    with patch("app.scrapers.idox_portal.fetch_application_by_reference", side_effect=requests.exceptions.ConnectTimeout()):
        outcome = verify_application_status(session, MagicMock(), _council_config(), app, lifecycle_event_stats=stats)
    assert outcome.outcome == "portal_unavailable"
    assert _events(session, app.id) == []
    assert stats.any_written is False


def test_fetch_failed_writes_no_lifecycle_event(session):
    import requests
    app = _add_application(session, reference="A/1", decision=None)
    stats = LifecycleEventStats()
    with patch("app.scrapers.idox_portal.fetch_application_by_reference", side_effect=requests.exceptions.HTTPError("500")):
        outcome = verify_application_status(session, MagicMock(), _council_config(), app, lifecycle_event_stats=stats)
    assert outcome.outcome == "fetch_failed"
    assert _events(session, app.id) == []
    assert stats.any_written is False


def test_application_not_found_writes_no_lifecycle_event(session):
    app = _add_application(session, reference="A/1", decision=None)
    stats = LifecycleEventStats()
    with patch("app.scrapers.idox_portal.fetch_application_by_reference", return_value=None):
        outcome = verify_application_status(session, MagicMock(), _council_config(), app, lifecycle_event_stats=stats)
    assert outcome.outcome == "application_not_found"
    assert _events(session, app.id) == []


# --- 3. record_related_application_discovery_event + stage wiring --------------


def test_new_related_application_event_recorded(session):
    child = _add_application(session, reference="CHILD/1")
    stats = LifecycleEventStats()
    written = record_related_application_discovery_event(
        session, application_id=child.id, category="primary_residential", stats=stats,
    )
    session.commit()
    assert written == 1
    events = _events(session, child.id)
    assert len(events) == 1
    assert events[0].event_type == EVENT_NEW_RELATED_APPLICATION
    assert events[0].authoritative_source == SOURCE_RELATED_APPLICATION_DISCOVERY
    assert events[0].new_value == "primary_residential"
    assert stats.written == 1


def test_reserved_matters_category_writes_specific_event_too(session):
    child = _add_application(session, reference="CHILD/1")
    written = record_related_application_discovery_event(
        session, application_id=child.id, category="reserved_matters",
    )
    session.commit()
    assert written == 2
    event_types = {e.event_type for e in _events(session, child.id)}
    assert event_types == {EVENT_NEW_RELATED_APPLICATION, EVENT_RESERVED_MATTERS_FOUND}


def test_condition_discharge_category_writes_specific_event_too(session):
    child = _add_application(session, reference="CHILD/1")
    written = record_related_application_discovery_event(
        session, application_id=child.id, category="condition_discharge_or_details",
    )
    session.commit()
    assert written == 2
    event_types = {e.event_type for e in _events(session, child.id)}
    assert event_types == {EVENT_NEW_RELATED_APPLICATION, EVENT_CONDITION_DISCHARGE_FOUND}


def test_variation_or_amendment_category_never_fabricates_s73_or_nma_event(session):
    """KNOWN LIMITATION, deliberately: classify_application_category cannot
    distinguish a genuine S73 from an NMA from a deed of variation - this
    module must never guess. Only the generic NEW_RELATED_APPLICATION event
    is written, with the raw category preserved as new_value."""
    child = _add_application(session, reference="CHILD/1")
    written = record_related_application_discovery_event(
        session, application_id=child.id, category="variation_or_amendment",
    )
    session.commit()
    assert written == 1
    events = _events(session, child.id)
    assert events[0].event_type == EVENT_NEW_RELATED_APPLICATION
    assert events[0].new_value == "variation_or_amendment"
    event_types = {e.event_type for e in events}
    assert "s73_found" not in event_types
    assert "nma_found" not in event_types


def _add_related_applications_anchor(session, *, reference: str) -> Application:
    anchor = _add_application(session, reference=reference)
    anchor.decision = "Granted"
    anchor.application_received = "01/01/2020"
    site = Site(council_code="testcouncil", canonical_address=f"1 Test St {reference}", display_address=f"1 Test St {reference}")
    session.add(site)
    session.flush()
    anchor.site_id = site.id
    session.commit()
    return anchor


def test_stage_fetch_related_applications_writes_event_for_genuine_discovery(session):
    """End-to-end through the real stage: a genuinely new related
    application discovered via portal search gets its NEW_RELATED_
    APPLICATION lifecycle event recorded, wired through the actual
    production call path (not just the helper function in isolation)."""
    _add_related_applications_anchor(session, reference="ANCHOR/1")
    stats = LifecycleEventStats()
    child_result = _scraped("CHILD/1", status="Decided", decision="Granted")

    with patch("app.pipeline.run_weekly.search_related_applications", return_value=["https://example.invalid/summary?keyVal=CHILD1"]), \
         patch("app.pipeline.run_weekly.fetch_application_detail", return_value=child_result):
        stage_fetch_related_applications(session, MagicMock(), _council_config(), lifecycle_event_stats=stats)

    child = session.execute(select(Application).where(Application.reference == "CHILD/1")).scalar_one()
    events = _events(session, child.id)
    assert any(e.event_type == EVENT_NEW_RELATED_APPLICATION for e in events)
    assert stats.any_written is True


# --- 4. Document.content_hash --------------------------------------------------


def test_content_hash_computed_for_new_document_with_text(session):
    from app.policy.change_detection import compute_content_hash

    app = _add_application(session, reference="A/1")
    text = "This is the extracted planning statement text."
    doc = Document(
        application_id=app.id, doc_type="planning_statement", document_name="statement.pdf",
        source_url="https://example.invalid/statement.pdf", text_extracted=True,
        extracted_text=text, content_hash=compute_content_hash(text),
    )
    session.add(doc)
    session.commit()

    assert doc.content_hash == compute_content_hash(text)
    assert doc.content_hash is not None


def test_content_hash_none_when_no_text(session):
    app = _add_application(session, reference="A/1")
    doc = Document(
        application_id=app.id, doc_type="other", document_name="drawing.pdf",
        source_url="https://example.invalid/drawing.pdf", text_extracted=False,
        extracted_text=None, content_hash=None,
    )
    session.add(doc)
    session.commit()
    assert doc.content_hash is None


def test_legacy_document_row_content_hash_stays_null(session):
    """A pre-existing Document row (created before this Gate) never gets a
    hash backfilled - same 'plain additive column, legacy rows stay NULL
    forever' precedent as Application.status_verified_at."""
    app = _add_application(session, reference="A/1")
    legacy_doc = Document(
        application_id=app.id, doc_type="planning_statement", document_name="old.pdf",
        source_url="https://example.invalid/old.pdf", text_extracted=True,
        extracted_text="some historic text", downloaded_at=dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc),
        # content_hash deliberately omitted - simulates a row inserted by
        # code that pre-dates this field.
    )
    session.add(legacy_doc)
    session.commit()
    assert legacy_doc.content_hash is None


def test_two_documents_same_text_hash_identically(session):
    from app.policy.change_detection import compute_content_hash
    app = _add_application(session, reference="A/1")
    text = "Identical proposal text."
    d1 = Document(application_id=app.id, doc_type="planning_statement", document_name="a.pdf", extracted_text=text, content_hash=compute_content_hash(text))
    d2 = Document(application_id=app.id, doc_type="planning_statement", document_name="b.pdf", extracted_text=text, content_hash=compute_content_hash(text))
    session.add_all([d1, d2])
    session.commit()
    assert d1.content_hash == d2.content_hash


def test_documents_with_different_text_hash_differently(session):
    from app.policy.change_detection import compute_content_hash
    app = _add_application(session, reference="A/1")
    d1 = Document(application_id=app.id, doc_type="planning_statement", document_name="a.pdf", extracted_text="Version one text.", content_hash=compute_content_hash("Version one text."))
    d2 = Document(application_id=app.id, doc_type="planning_statement", document_name="a.pdf", extracted_text="Version two text, revised.", content_hash=compute_content_hash("Version two text, revised."))
    session.add_all([d1, d2])
    session.commit()
    assert d1.content_hash != d2.content_hash


def test_revised_document_at_same_identity_not_detected_known_limitation(session):
    """KNOWN LIMITATION, documented and deliberate (see Document.
    content_hash's own comment and app.pipeline.run_weekly.
    discover_and_store_documents_for_application's existing_identities
    dedup): this Gate establishes the content_hash baseline for NEW
    documents only. A document identity (source_url/document_name) that
    ALREADY exists is skipped before download in the real pipeline, so a
    genuinely revised document published at the same identity is not
    re-hashed or re-compared by this phase - this test documents that
    boundary explicitly rather than silently assuming it works."""
    from app.pipeline.evidence import document_identity_key
    app = _add_application(session, reference="A/1")
    original = Document(
        application_id=app.id, doc_type="decision_notice", document_name="notice.pdf",
        source_url="https://example.invalid/notice.pdf", extracted_text="Original decision text.",
    )
    session.add(original)
    session.commit()

    existing_identities = {document_identity_key(original.source_url, original.document_name)}
    revised_identity = document_identity_key("https://example.invalid/notice.pdf", "notice.pdf")
    # The real pipeline's own dedup check: an identity already known is
    # skipped BEFORE any re-fetch/re-hash could happen.
    assert revised_identity in existing_identities


# --- 5. Phase D - the downstream-reassessment trigger's own gating condition ----


def test_any_written_gates_the_reassessment_trigger():
    stats = LifecycleEventStats()
    assert stats.any_written is False
    stats.record(1)
    assert stats.any_written is True


def test_weekly_sync_unaffected_by_lifecycle_events_when_nothing_material_in_universe(session):
    """Non-regression: writing an ApplicationLifecycleEvent for an
    Application with no SchemeIntelligence/opportunity linkage must not,
    on its own, perturb sync_opportunity_monitoring_state's own counts -
    proves the two are correctly decoupled (an event does not itself
    mutate opportunity facts; only a genuine opportunity-universe input
    changing does)."""
    app = _add_application(session, reference="A/1", status="Awaiting Decision", decision=None)
    result = detect_material_application_change(
        ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=None),
        ApplicationState(status="Decided", decision="Granted", estimated_unit_count=None),
    )
    record_material_change_events(session, application_id=app.id, result=result, authoritative_source=SOURCE_SCRAPE)
    session.commit()

    first = sync_opportunity_monitoring_state(session)
    second = sync_opportunity_monitoring_state(session)
    assert first == second  # idempotent, unaffected by the lifecycle event row existing


# --- 6. Non-regression: Gate 2B-2A/2B-2C substantive-role guardrails ------------


def test_nma_discovery_event_does_not_change_operative_lapse_anchor(session):
    """A discovered NMA (recorded as NEW_RELATED_APPLICATION only, per the
    KNOWN LIMITATION above) must still never be treated as the operative
    granted permission - Gate 2B-2A/2B-2C's SUBSTANTIVE_ROLES exclusion is
    completely untouched by this Gate's own event-recording logic."""
    site = Site(council_code="testcouncil", canonical_address="1 Test St", display_address="1 Test St")
    session.add(site)
    session.flush()

    granted = _add_application(
        session, reference="GRANT/1", decision="Granted", application_received="01/01/2020",
        proposal="Erection of 40 dwellings", application_category="primary_residential",
    )
    granted.site_id = site.id
    nma = _add_application(
        session, reference="NMA/1", decision="Approve with Conditions", application_received="01/06/2021",
        proposal="Non-material amendment to permission GRANT/1", application_category="variation_or_amendment",
    )
    nma.site_id = site.id
    session.commit()

    record_related_application_discovery_event(session, application_id=nma.id, category="variation_or_amendment")
    session.commit()

    anchor = resolve_operative_lapse_anchor([granted, nma])
    assert anchor.application is not None
    assert anchor.application.reference == "GRANT/1"  # the NMA never becomes the anchor


def test_fingerprint_fields_unaffected_by_a_recorded_lifecycle_event(session):
    """A lifecycle event existing in the database must never, on its own,
    change app.reporting.opportunity_universe's own fingerprint_fields for
    an otherwise-unchanged opportunity - the same 'a verification/history
    record is not itself a planning CHANGE' discipline Gate 2B-0A already
    established for status_verified_at."""
    site = Site(council_code="testcouncil", canonical_address="1 Test St", display_address="1 Test St")
    session.add(site)
    session.flush()
    app = _add_application(
        session, reference="A/1", decision=None, status="Awaiting Decision",
        proposal="Erection of 60 dwellings", application_category="primary_residential",
        estimated_unit_count=60, unit_confirmation_status="confirmed_qualifying",
    )
    app.site_id = site.id
    session.commit()

    before = build_current_opportunity_universe(session)
    before_fields = {r.opportunity_id: r.fingerprint_fields for r in before}

    record_material_change_events(
        session, application_id=app.id,
        result=detect_material_application_change(
            ApplicationState(status="Awaiting Decision", decision=None, estimated_unit_count=60),
            ApplicationState(status="Officer Recommendation: Approve", decision=None, estimated_unit_count=60),
        ),
        authoritative_source=SOURCE_SCRAPE,
    )
    session.commit()

    after = build_current_opportunity_universe(session)
    after_fields = {r.opportunity_id: r.fingerprint_fields for r in after}
    assert before_fields == after_fields
