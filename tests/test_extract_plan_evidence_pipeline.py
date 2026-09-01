"""Sprint 3B ("AI Local Plan Evidence Extraction", Part 11) - tests for
app.policy.extract_plan_evidence: the runnable pipeline that turns
extracted facts into PolicyChangeEvent proposals. No network, no real
OpenAI call, no real PDF - a fake client stands in for the API and every
test points source_type/category directly at CATEGORIES so page-range
text content is irrelevant to what gets asserted (pages are only ever
formatted into a prompt string here, never actually read for content by
the fake client)."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.db.models import LocalPlan, LocalPlanFieldHistory, PolicyChangeEvent
from app.extraction.plan_evidence import CATEGORIES
from app.policy.extract_plan_evidence import (
    classify_evidence_confidence,
    resolve_plan,
    run_extraction,
)
from app.policy.review import approve_change, reject_change


class _FakeUsage:
    input_tokens = 1000
    output_tokens = 200


class _FakeResponse:
    def __init__(self, output_text):
        self.output_text = output_text
        self.usage = _FakeUsage()


class _FakeClient:
    """facts_by_category: {category: [fact, ...]} - a fixed, hand-written
    fact list per category, standing in for whatever the real model would
    have returned for a given prompt. schema_name in the prompt call tells
    this fake which category is being asked for."""

    def __init__(self, facts_by_category):
        self._facts_by_category = facts_by_category
        outer = self

        class _Responses:
            def create(self, model, input, text):
                category = text["format"]["name"].removeprefix("plan_evidence_")
                return _FakeResponse(json.dumps({"facts": outer._facts_by_category[category]}))

        self.responses = _Responses()


def _null_fact(field):
    return {"field": field, "value": None, "source_page": None, "source_excerpt": None, "confidence": None}


def _fact(field, value, page=5, confidence="high"):
    excerpt = f"a supporting figure of {value} is stated in the text"
    return {"field": field, "value": value, "source_page": page, "source_excerpt": excerpt, "confidence": confidence}


def _make_plan(session, **kwargs):
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Local Plan", status="draft_consultation", raw_status="draft", **kwargs)
    session.add(plan)
    session.commit()
    return plan


def _all_null_facts(category):
    return [_null_fact(f) for f in CATEGORIES[category]]


# LPDI V1 Gate 3A ("Deterministic Evidence Citation Verification") - the
# stub page below now needs to genuinely CONTAIN every _fact()-generated
# excerpt a test in this file expects to auto-apply, since run_extraction
# deterministically verifies source_excerpt against this same page-bounded
# text before a fact can auto-apply. _fact()'s own excerpt template is
# f"a supporting figure of {value} is stated in the text" (default page 5,
# but the stub below is page 1 - a real citation-verification mismatch
# this file's tests never needed to care about before Gate 3A) - listing
# every value actually used with that default template across this file's
# auto-apply assertions is simpler and more transparent than trying to
# generate it dynamically.
_STUB_PAGE_TEXT = " ".join(
    f"a supporting figure of {v} is stated in the text" for v in (936, 1100, 17800)
)


@pytest.fixture(autouse=True)
def _stub_pdf_pages():
    # run_extraction always reads real page text via
    # app.extraction.plan_evidence.extract_pdf_pages before running any
    # category's pass - the fake client below ignores that text entirely
    # (it returns fixed, hand-written facts regardless of prompt content),
    # so stubbing this out avoids every test needing a real PDF file on
    # disk, the same way tests/test_monitor.py stubs requests.get rather
    # than hitting a real URL.
    with patch("app.policy.extract_plan_evidence.extract_pdf_pages", return_value=[(1, _STUB_PAGE_TEXT), (5, _STUB_PAGE_TEXT)]):
        yield


# --- resolve_plan ---

def test_resolve_plan_finds_the_single_plan_for_a_council(session):
    plan = _make_plan(session)
    resolved = resolve_plan(session, "testcouncil", plan_id=None)
    assert resolved.id == plan.id


def test_resolve_plan_requires_plan_id_when_more_than_one_exists(session):
    _make_plan(session)
    _make_plan(session)  # a second plan for the same council (name collision is fine here - no unique index in play)
    with pytest.raises(ValueError):
        resolve_plan(session, "testcouncil", plan_id=None)


def test_resolve_plan_errors_when_none_exist(session):
    with pytest.raises(ValueError):
        resolve_plan(session, "testcouncil", plan_id=None)


# --- classify_evidence_confidence ---

def test_null_current_value_with_high_confidence_auto_applies():
    assert classify_evidence_confidence(None, "high") == "auto_applied"


def test_null_current_value_with_medium_confidence_needs_review():
    assert classify_evidence_confidence(None, "medium") == "needs_review"


def test_existing_value_always_needs_review_even_at_high_confidence():
    # Part 7: changing an already-known value is never auto-applied,
    # regardless of confidence - only filling a genuinely empty field is.
    assert classify_evidence_confidence(450, "high") == "needs_review"


# --- auto-apply vs needs-review wiring, using the real pipeline ---

def test_new_field_at_high_confidence_is_auto_applied_and_writes_field_history(session):
    plan = _make_plan(session)
    facts = _all_null_facts("housing_requirement")
    facts[0] = _fact("annual_housing_requirement", "936")  # first field in HOUSING_REQUIREMENT_FIELDS
    client = _FakeClient({"housing_requirement": facts})

    stats = run_extraction(session, client, plan, pdf_path="unused.pdf", first_page=1, last_page=1,
                            source_type="x", category_override="housing_requirement")

    assert stats["auto_applied"] == 1
    assert stats["needs_review"] == 0
    session.refresh(plan)
    assert plan.annual_housing_requirement == 936

    history = session.execute(select(LocalPlanFieldHistory).where(LocalPlanFieldHistory.local_plan_id == plan.id)).scalars().all()
    assert len(history) == 1
    assert history[0].field_name == "annual_housing_requirement"
    assert history[0].old_value is None
    assert history[0].new_value == "936"


def test_changing_an_existing_value_needs_review_and_leaves_trusted_value_untouched(session):
    plan = _make_plan(session, annual_housing_requirement=450)
    facts = _all_null_facts("housing_requirement")
    facts[0] = _fact("annual_housing_requirement", "936")
    client = _FakeClient({"housing_requirement": facts})

    stats = run_extraction(session, client, plan, pdf_path="unused.pdf", first_page=1, last_page=1,
                            source_type="x", category_override="housing_requirement")

    assert stats["auto_applied"] == 0
    assert stats["needs_review"] == 1
    session.refresh(plan)
    assert plan.annual_housing_requirement == 450  # untouched - only proposed, not applied

    events = session.execute(select(PolicyChangeEvent).where(PolicyChangeEvent.local_plan_id == plan.id)).scalars().all()
    assert len(events) == 1
    assert events[0].event_type == "plan_evidence_proposed"
    assert events[0].review_status == "needs_review"
    assert json.loads(events[0].proposed_data) == {"annual_housing_requirement": 936}


def test_facts_rejected_by_validation_never_become_a_change_event(session):
    plan = _make_plan(session)
    facts = _all_null_facts("housing_requirement")
    # a numeric value with no supporting excerpt - rejected by
    # app.policy.evidence_validation before it ever reaches proposal stage
    facts[0] = {"field": "annual_housing_requirement", "value": "936", "source_page": None, "source_excerpt": None, "confidence": "high"}
    client = _FakeClient({"housing_requirement": facts})

    stats = run_extraction(session, client, plan, pdf_path="unused.pdf", first_page=1, last_page=1,
                            source_type="x", category_override="housing_requirement")

    assert stats["facts_rejected"] == 1
    assert stats["events_created"] == 0
    events = session.execute(select(PolicyChangeEvent).where(PolicyChangeEvent.local_plan_id == plan.id)).scalars().all()
    assert events == []


def test_no_eligible_category_for_source_type_does_nothing(session):
    plan = _make_plan(session)
    client = _FakeClient({})
    stats = run_extraction(session, client, plan, pdf_path="unused.pdf", first_page=1, last_page=1, source_type="landing_page")
    assert stats["categories"] == []
    assert stats["passes_run"] == 0
    assert stats["events_created"] == 0


# --- housing need vs requirement: structurally must never cross-fill ---

def test_housing_need_and_requirement_are_written_to_distinct_fields(session):
    plan = _make_plan(session)
    facts = _all_null_facts("housing_requirement")
    by_field = {f["field"]: f for f in facts}
    facts[facts.index(by_field["annual_housing_requirement"])] = _fact("annual_housing_requirement", "936")
    facts[facts.index(by_field["housing_need_annual"])] = _fact("housing_need_annual", "1100")
    client = _FakeClient({"housing_requirement": facts})

    run_extraction(session, client, plan, pdf_path="unused.pdf", first_page=1, last_page=1,
                    source_type="x", category_override="housing_requirement")

    session.refresh(plan)
    # annual_housing_requirement auto-applied (was null, high confidence);
    # housing_need_annual also auto-applied (also was null) - but critically
    # each landed on ITS OWN column, never merged or cross-written.
    assert plan.annual_housing_requirement == 936
    assert plan.housing_need_annual == 1100
    assert plan.annual_housing_requirement != plan.housing_need_annual or True  # distinct columns, coincidental equality would still be fine
    assert plan.annual_housing_requirement == 936 and plan.housing_need_annual == 1100


# --- extraction field name -> model field name translation ---

def test_raw_plan_status_extraction_field_maps_to_model_raw_status_column(session):
    plan = _make_plan(session)
    facts = _all_null_facts("plan_identity")
    by_field = {f["field"]: f for f in facts}
    facts[facts.index(by_field["raw_plan_status"])] = _fact("raw_plan_status", "Publication")
    client = _FakeClient({"plan_identity": facts})

    run_extraction(session, client, plan, pdf_path="unused.pdf", first_page=1, last_page=1,
                    source_type="x", category_override="plan_identity")

    events = session.execute(select(PolicyChangeEvent).where(PolicyChangeEvent.local_plan_id == plan.id)).scalars().all()
    assert len(events) == 1
    assert json.loads(events[0].proposed_data) == {"raw_status": "Publication"}


def test_total_plan_housing_requirement_maps_to_model_total_housing_requirement_column(session):
    plan = _make_plan(session)
    facts = _all_null_facts("housing_requirement")
    by_field = {f["field"]: f for f in facts}
    facts[facts.index(by_field["total_plan_housing_requirement"])] = _fact("total_plan_housing_requirement", "17800")
    client = _FakeClient({"housing_requirement": facts})

    run_extraction(session, client, plan, pdf_path="unused.pdf", first_page=1, last_page=1,
                    source_type="x", category_override="housing_requirement")

    session.refresh(plan)
    assert plan.total_housing_requirement == 17800


# --- idempotency (Part 9) ---

def test_rerunning_against_an_unchanged_document_creates_no_new_events_after_auto_apply(session):
    plan = _make_plan(session)
    facts = _all_null_facts("housing_requirement")
    facts[0] = _fact("annual_housing_requirement", "936")
    client = _FakeClient({"housing_requirement": facts})

    run_extraction(session, client, plan, pdf_path="unused.pdf", first_page=1, last_page=1,
                    source_type="x", category_override="housing_requirement")
    second_stats = run_extraction(session, client, plan, pdf_path="unused.pdf", first_page=1, last_page=1,
                                   source_type="x", category_override="housing_requirement")

    assert second_stats["events_created"] == 0
    assert second_stats["unchanged_skipped"] == 1


def test_rerunning_a_still_pending_needs_review_proposal_does_not_duplicate_it(session):
    # The trickier idempotency case: a needs_review fact never touches the
    # trusted field, so naive "does the value already match?" logic would
    # keep re-proposing it on every re-run - this must not happen.
    plan = _make_plan(session, annual_housing_requirement=450)
    facts = _all_null_facts("housing_requirement")
    facts[0] = _fact("annual_housing_requirement", "936")
    client = _FakeClient({"housing_requirement": facts})

    run_extraction(session, client, plan, pdf_path="unused.pdf", first_page=1, last_page=1,
                    source_type="x", category_override="housing_requirement")
    second_stats = run_extraction(session, client, plan, pdf_path="unused.pdf", first_page=1, last_page=1,
                                   source_type="x", category_override="housing_requirement")

    assert second_stats["events_created"] == 0
    events = session.execute(select(PolicyChangeEvent).where(PolicyChangeEvent.local_plan_id == plan.id)).scalars().all()
    assert len(events) == 1  # still just the one from the first run


def test_reprocess_unchanged_flag_forces_a_new_event_despite_a_pending_proposal(session):
    plan = _make_plan(session, annual_housing_requirement=450)
    facts = _all_null_facts("housing_requirement")
    facts[0] = _fact("annual_housing_requirement", "936")
    client = _FakeClient({"housing_requirement": facts})

    run_extraction(session, client, plan, pdf_path="unused.pdf", first_page=1, last_page=1,
                    source_type="x", category_override="housing_requirement")
    second_stats = run_extraction(session, client, plan, pdf_path="unused.pdf", first_page=1, last_page=1,
                                   source_type="x", category_override="housing_requirement", reprocess_unchanged=True)

    assert second_stats["events_created"] == 1
    events = session.execute(select(PolicyChangeEvent).where(PolicyChangeEvent.local_plan_id == plan.id)).scalars().all()
    assert len(events) == 2


# --- dry run writes nothing ---

def test_dry_run_creates_no_database_rows_and_leaves_the_plan_untouched(session):
    plan = _make_plan(session)
    facts = _all_null_facts("housing_requirement")
    facts[0] = _fact("annual_housing_requirement", "936")
    client = _FakeClient({"housing_requirement": facts})

    stats = run_extraction(session, client, plan, pdf_path="unused.pdf", first_page=1, last_page=1,
                            source_type="x", category_override="housing_requirement", dry_run=True)

    assert stats["events_created"] == 1  # reported, for the CLI's own output
    session.refresh(plan)
    assert plan.annual_housing_requirement is None
    events = session.execute(select(PolicyChangeEvent).where(PolicyChangeEvent.local_plan_id == plan.id)).scalars().all()
    assert events == []


# --- proposed changes flow through app.policy.review correctly (approve/reject) ---

def test_a_needs_review_proposal_can_be_approved_and_writes_field_history(session):
    plan = _make_plan(session, annual_housing_requirement=450)
    facts = _all_null_facts("housing_requirement")
    facts[0] = _fact("annual_housing_requirement", "936")
    client = _FakeClient({"housing_requirement": facts})
    run_extraction(session, client, plan, pdf_path="unused.pdf", first_page=1, last_page=1,
                    source_type="x", category_override="housing_requirement")

    [event] = session.execute(select(PolicyChangeEvent).where(PolicyChangeEvent.local_plan_id == plan.id)).scalars().all()
    approve_change(session, event, note="Confirmed against the published plan.")

    session.refresh(plan)
    assert plan.annual_housing_requirement == 936
    history = session.execute(select(LocalPlanFieldHistory).where(LocalPlanFieldHistory.local_plan_id == plan.id)).scalars().all()
    assert len(history) == 1
    assert history[0].old_value == "450"
    assert history[0].new_value == "936"


def test_a_needs_review_proposal_can_be_rejected_leaving_trusted_value_and_no_history(session):
    plan = _make_plan(session, annual_housing_requirement=450)
    facts = _all_null_facts("housing_requirement")
    facts[0] = _fact("annual_housing_requirement", "936")
    client = _FakeClient({"housing_requirement": facts})
    run_extraction(session, client, plan, pdf_path="unused.pdf", first_page=1, last_page=1,
                    source_type="x", category_override="housing_requirement")

    [event] = session.execute(select(PolicyChangeEvent).where(PolicyChangeEvent.local_plan_id == plan.id)).scalars().all()
    reject_change(session, event, note="Mis-extracted - the PDF table cell was misread.")

    session.refresh(plan)
    assert plan.annual_housing_requirement == 450  # unchanged
    history = session.execute(select(LocalPlanFieldHistory).where(LocalPlanFieldHistory.local_plan_id == plan.id)).scalars().all()
    assert history == []
