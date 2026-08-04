"""Sprint 3B ("AI Local Plan Evidence Extraction", Part 11/Part 10) - tests
for app.policy.plan_evidence_view: the pure data-assembly behind the
Council Dashboard's plan evidence sections. Confirms complete, partial,
and missing evidence are all distinguishable, trusted values carry their
source, pending proposals are surfaced separately, and nothing is ever
rendered as a bare zero for a genuinely missing value."""
from __future__ import annotations

import datetime as dt
import json

from app.db.models import LocalPlan, PolicyChangeEvent
from app.policy.plan_evidence_view import build_plan_evidence_view, get_field_evidence, get_pending_proposals


def _make_plan(session, **kwargs):
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Local Plan", status="draft_consultation", raw_status="draft", **kwargs)
    session.add(plan)
    session.commit()
    return plan


def _confirmed_event(session, plan, field, value, **kwargs):
    event = PolicyChangeEvent(
        local_plan_id=plan.id, event_type="plan_evidence_proposed",
        old_value=None, new_value=str(value), proposed_data=json.dumps({field: value}),
        source_document_title=kwargs.get("title", "Test Local Plan"),
        source_document_url=kwargs.get("url", "https://example.invalid/plan.pdf"),
        source_page=kwargs.get("page", 5), source_excerpt=kwargs.get("excerpt", "a supporting excerpt"),
        extraction_method="ai_structured_extraction", extraction_model="gpt-4o-mini",
        extraction_prompt_version="plan-evidence-v1", extracted_at=kwargs.get("extracted_at", dt.datetime.now(dt.timezone.utc)),
        auto_applied=True, review_status="confirmed",
    )
    session.add(event)
    session.commit()
    return event


def _pending_event(session, plan, field, value, **kwargs):
    event = PolicyChangeEvent(
        local_plan_id=plan.id, event_type="plan_evidence_proposed",
        old_value=None, new_value=str(value), proposed_data=json.dumps({field: value}),
        source_document_title=kwargs.get("title", "Test Local Plan"),
        source_page=kwargs.get("page", 5), source_excerpt=kwargs.get("excerpt", "a supporting excerpt"),
        auto_applied=False, review_status="needs_review",
    )
    session.add(event)
    session.commit()
    return event


# --- get_field_evidence ---

def test_get_field_evidence_finds_the_confirmed_event_that_set_a_field(session):
    plan = _make_plan(session, annual_housing_requirement=936)
    _confirmed_event(session, plan, "annual_housing_requirement", 936, page=112)

    evidence = get_field_evidence(session, plan.id, "annual_housing_requirement")
    assert evidence is not None
    assert evidence.source_page == 112


def test_get_field_evidence_ignores_needs_review_events(session):
    plan = _make_plan(session)
    _pending_event(session, plan, "annual_housing_requirement", 936)

    evidence = get_field_evidence(session, plan.id, "annual_housing_requirement")
    assert evidence is None


def test_get_field_evidence_returns_none_for_a_field_never_set_by_an_event(session):
    plan = _make_plan(session, annual_housing_requirement=936)  # set directly, no event behind it
    evidence = get_field_evidence(session, plan.id, "annual_housing_requirement")
    assert evidence is None


# --- get_pending_proposals ---

def test_get_pending_proposals_maps_field_to_its_pending_event(session):
    plan = _make_plan(session)
    _pending_event(session, plan, "total_housing_requirement", 17800)

    pending = get_pending_proposals(session, plan.id)
    assert "total_housing_requirement" in pending
    assert json.loads(pending["total_housing_requirement"].proposed_data)["total_housing_requirement"] == 17800


def test_get_pending_proposals_excludes_confirmed_events(session):
    plan = _make_plan(session, annual_housing_requirement=936)
    _confirmed_event(session, plan, "annual_housing_requirement", 936)

    pending = get_pending_proposals(session, plan.id)
    assert pending == {}


# --- build_plan_evidence_view: complete / partial / missing evidence ---

def test_a_field_with_a_confirmed_trusted_value_shows_its_source(session):
    plan = _make_plan(session, annual_housing_requirement=936)
    _confirmed_event(session, plan, "annual_housing_requirement", 936, page=112, title="Stockport Local Plan")

    view = build_plan_evidence_view(session, plan)
    entry = next(e for e in view["requirement"] if e["field"] == "annual_housing_requirement")
    assert entry["has_value"] is True
    assert entry["value"] == 936
    assert entry["source_document_title"] == "Stockport Local Plan"
    assert entry["source_page"] == 112
    assert entry["pending_value"] is None


def test_a_field_with_no_value_and_no_proposal_is_reported_as_missing_never_zero(session):
    plan = _make_plan(session)
    view = build_plan_evidence_view(session, plan)
    entry = next(e for e in view["requirement"] if e["field"] == "annual_housing_requirement")
    assert entry["has_value"] is False
    assert entry["value"] is None  # never coerced to 0
    assert entry["pending_value"] is None


def test_a_field_with_no_trusted_value_but_a_pending_proposal_shows_both_states(session):
    plan = _make_plan(session)
    _pending_event(session, plan, "total_housing_requirement", 17800)

    view = build_plan_evidence_view(session, plan)
    entry = next(e for e in view["requirement"] if e["field"] == "total_housing_requirement")
    assert entry["has_value"] is False  # trusted state genuinely still empty
    assert entry["pending_value"] == 17800  # but a change is proposed and awaiting review


def test_a_trusted_value_with_a_further_pending_change_shows_both(session):
    # "partial" evidence in Part 10's sense - a real current value, AND a
    # proposed change to it still awaiting a decision.
    plan = _make_plan(session, annual_housing_requirement=450)
    _confirmed_event(session, plan, "annual_housing_requirement", 450)
    _pending_event(session, plan, "annual_housing_requirement", 936)

    view = build_plan_evidence_view(session, plan)
    entry = next(e for e in view["requirement"] if e["field"] == "annual_housing_requirement")
    assert entry["has_value"] is True
    assert entry["value"] == 450
    assert entry["pending_value"] == 936


def test_stale_evidence_is_flagged_when_extracted_long_ago(session):
    plan = _make_plan(session, five_year_supply_years=3.2)
    old_date = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=800)
    _confirmed_event(session, plan, "five_year_supply_years", 3.2, extracted_at=old_date)

    view = build_plan_evidence_view(session, plan)
    entry = next(e for e in view["five_year_supply"] if e["field"] == "five_year_supply_years")
    assert entry["is_stale"] is True


def test_fresh_evidence_is_not_flagged_stale(session):
    plan = _make_plan(session, five_year_supply_years=3.2)
    _confirmed_event(session, plan, "five_year_supply_years", 3.2)

    view = build_plan_evidence_view(session, plan)
    entry = next(e for e in view["five_year_supply"] if e["field"] == "five_year_supply_years")
    assert entry["is_stale"] is False


def test_delivery_section_is_entirely_empty_when_nothing_was_ever_extracted(session):
    plan = _make_plan(session)
    view = build_plan_evidence_view(session, plan)
    assert all(not e["has_value"] and e["pending_value"] is None for e in view["delivery"])
