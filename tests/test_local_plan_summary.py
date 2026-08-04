"""Sprint 3B.1 ("AI Local Plan Summary") - tests for
app.reporting.local_plan_summary: the deterministic payload builder,
evidence fingerprint/regeneration gating, and the AI generation +
output-validation pipeline. No real OpenAI call anywhere - a fake client
stands in, matching the pattern already used throughout this test suite
(tests/test_monitor.py, tests/test_extract_plan_evidence_pipeline.py)."""
from __future__ import annotations

import datetime as dt
import json

from app.db.models import LocalPlan, LocalPlanSite, PolicyChangeEvent
from app.reporting.local_plan_summary import (
    build_summary_payload,
    build_summary_prompt,
    compute_evidence_fingerprint,
    generate_local_plan_summary,
    is_summary_stale,
    should_regenerate,
    validate_summary_output,
)


def _make_plan(session, status="draft_consultation", raw_status="draft", **kwargs):
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Local Plan", status=status, raw_status=raw_status, **kwargs)
    session.add(plan)
    session.commit()
    return plan


def _confirmed_event(session, plan, field, value, **kwargs):
    event = PolicyChangeEvent(
        local_plan_id=plan.id, event_type="plan_evidence_proposed",
        old_value=None, new_value=str(value), proposed_data=json.dumps({field: value}),
        source_document_title=kwargs.get("title", "Test Local Plan PDF"),
        source_page=kwargs.get("page", 10), source_excerpt=kwargs.get("excerpt", "a supporting excerpt"),
        extraction_method="ai_structured_extraction", extraction_model="gpt-4o-mini",
        extraction_prompt_version="plan-evidence-v1",
        extracted_at=kwargs.get("extracted_at", dt.datetime.now(dt.timezone.utc)),
        auto_applied=kwargs.get("auto_applied", True),
        review_status=kwargs.get("review_status", "auto_applied"),
    )
    session.add(event)
    session.commit()
    return event


def _pending_event(session, plan, field, value, **kwargs):
    event = PolicyChangeEvent(
        local_plan_id=plan.id, event_type="plan_evidence_proposed",
        old_value=None, new_value=str(value), proposed_data=json.dumps({field: value}),
        source_document_title=kwargs.get("title", "Test Local Plan PDF"),
        source_page=kwargs.get("page", 10), source_excerpt=kwargs.get("excerpt", "a supporting excerpt"),
        auto_applied=False, review_status="needs_review",
    )
    session.add(event)
    session.commit()
    return event


class _FakeUsage:
    input_tokens = 100
    output_tokens = 50


class _FakeResponse:
    def __init__(self, output_text: str):
        self.output_text = output_text
        self.usage = _FakeUsage()


def _fake_client(structured_output: dict):
    class _Responses:
        def create(self, model, input, text):
            return _FakeResponse(json.dumps(structured_output))

    client = type("FakeClient", (), {})()
    client.responses = _Responses()
    return client


_GOOD_OUTPUT = {
    "summary_text": "This is a plausible-length test summary describing the plan's emerging status, its housing requirement position, and its lack of five-year supply evidence at this time.",
    "key_risks": ["No five-year supply evidence is currently available."],
    "key_opportunities": ["The plan has allocations already progressing."],
    "evidence_gaps": ["Five-year supply position is unavailable."],
}


# --- payload uses trusted facts only ---

def test_payload_marks_a_confirmed_fact_as_confirmed_trust(session):
    plan = _make_plan(session, annual_housing_requirement=450)
    _confirmed_event(session, plan, "annual_housing_requirement", 450, review_status="confirmed")

    payload = build_summary_payload(session, plan)
    assert payload["facts"]["annual_housing_requirement"]["trust"] == "confirmed"
    assert payload["facts"]["annual_housing_requirement"]["value"] == 450


def test_payload_marks_an_auto_applied_fact_distinctly_from_confirmed(session):
    plan = _make_plan(session, annual_housing_requirement=450)
    _confirmed_event(session, plan, "annual_housing_requirement", 450, review_status="auto_applied")

    payload = build_summary_payload(session, plan)
    assert payload["facts"]["annual_housing_requirement"]["trust"] == "auto_applied"


def test_payload_never_treats_a_pending_value_as_the_trusted_value(session):
    plan = _make_plan(session)  # annual_housing_requirement left null
    _pending_event(session, plan, "annual_housing_requirement", 936)

    payload = build_summary_payload(session, plan)
    entry = payload["facts"]["annual_housing_requirement"]
    assert entry["value"] is None  # trusted field genuinely still empty
    assert entry["trust"] == "pending"
    assert entry["proposed_value"] == 936


# --- proposed changes remain clearly labelled ---

def test_prompt_labels_a_pending_value_as_awaiting_review_not_settled(session):
    plan = _make_plan(session, annual_housing_requirement=450)
    _confirmed_event(session, plan, "annual_housing_requirement", 450)
    _pending_event(session, plan, "annual_housing_requirement", 936)

    payload = build_summary_payload(session, plan)
    prompt = build_summary_prompt(payload)
    assert "PROPOSED (awaiting review, NOT yet trusted): 936" in prompt
    assert "450" in prompt  # the trusted value is still what's stated as current


def test_prompt_labels_conflicting_pending_values_explicitly(session):
    plan = _make_plan(session)
    _pending_event(session, plan, "annual_housing_requirement", 936, title="Source A")
    event_b = PolicyChangeEvent(
        local_plan_id=plan.id, event_type="plan_evidence_proposed", old_value=None, new_value="1000",
        proposed_data=json.dumps({"annual_housing_requirement": 1000}),
        source_document_title="Source B", source_page=5, source_excerpt="a different figure",
        auto_applied=False, review_status="needs_review",
    )
    session.add(event_b)
    session.commit()

    payload = build_summary_payload(session, plan)
    entry = payload["facts"]["annual_housing_requirement"]
    assert entry["has_conflict"] is True
    assert set(entry["conflicting_values"]) == {936, 1000}
    prompt = build_summary_prompt(payload)
    assert "CONFLICTING PROPOSED VALUES" in prompt


# --- missing evidence is represented honestly ---

def test_missing_fact_is_marked_missing_not_zero(session):
    plan = _make_plan(session)  # nothing set at all
    payload = build_summary_payload(session, plan)
    entry = payload["facts"]["five_year_supply_years"]
    assert entry["value"] is None
    assert entry["trust"] == "missing"

    prompt = build_summary_prompt(payload)
    assert "UNAVAILABLE" in prompt


# --- stale evidence warning ---

def test_stale_fact_is_flagged_and_the_prompt_mentions_it(session):
    plan = _make_plan(session, five_year_supply_years=3.2)
    old_date = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=800)
    _confirmed_event(session, plan, "five_year_supply_years", 3.2, extracted_at=old_date)

    payload = build_summary_payload(session, plan)
    assert payload["facts"]["five_year_supply_years"]["is_stale"] is True
    assert "five_year_supply_years" in payload["stale_fields"]
    prompt = build_summary_prompt(payload)
    assert "STALE" in prompt


def test_is_summary_stale_true_when_evidence_moved_since_generation(session):
    plan = _make_plan(session, annual_housing_requirement=450)
    payload = build_summary_payload(session, plan)
    plan.ai_summary_text = "An old summary."
    plan.ai_summary_evidence_fingerprint = compute_evidence_fingerprint(payload)
    session.commit()
    assert is_summary_stale(session, plan) is False

    # Now the trusted value changes.
    plan.annual_housing_requirement = 500
    session.commit()
    assert is_summary_stale(session, plan) is True


def test_is_summary_stale_false_when_no_summary_exists_yet(session):
    plan = _make_plan(session)
    assert is_summary_stale(session, plan) is False


# --- need and requirement remain distinct ---

def test_housing_need_and_requirement_are_separate_payload_facts(session):
    plan = _make_plan(session, annual_housing_requirement=450, housing_need_annual=600)
    payload = build_summary_payload(session, plan)
    assert payload["facts"]["annual_housing_requirement"]["value"] == 450
    assert payload["facts"]["housing_need_annual"]["value"] == 600
    # Distinct dict entries, never merged into one field.
    assert "annual_housing_requirement" != "housing_need_annual"


def test_prompt_explains_need_and_requirement_are_different_concepts(session):
    plan = _make_plan(session, annual_housing_requirement=450, housing_need_annual=600)
    payload = build_summary_payload(session, plan)
    prompt = build_summary_prompt(payload)
    assert "different concepts" in prompt or "distinct figures" in prompt


# --- adopted/emerging status wording ---

def test_adopted_plan_is_labelled_adopted(session):
    plan = _make_plan(session, status="adopted", raw_status="Adopted")
    payload = build_summary_payload(session, plan)
    assert payload["adopted_or_emerging"] == "adopted"
    prompt = build_summary_prompt(payload)
    assert "STATUS: ADOPTED" in prompt


def test_any_non_adopted_status_is_labelled_emerging(session):
    for status in ("draft_consultation", "examination", "submitted", "unknown"):
        plan = _make_plan(session, status=status, raw_status=status)
        payload = build_summary_payload(session, plan)
        assert payload["adopted_or_emerging"] == "emerging", status


# --- evidence fingerprint changes when trusted facts change ---

def test_fingerprint_changes_when_a_trusted_fact_changes(session):
    plan = _make_plan(session, annual_housing_requirement=450)
    fp1 = compute_evidence_fingerprint(build_summary_payload(session, plan))
    plan.annual_housing_requirement = 500
    session.commit()
    fp2 = compute_evidence_fingerprint(build_summary_payload(session, plan))
    assert fp1 != fp2


def test_fingerprint_unaffected_by_last_checked_alone(session):
    plan = _make_plan(session, annual_housing_requirement=450)
    fp1 = compute_evidence_fingerprint(build_summary_payload(session, plan))
    plan.last_checked = dt.datetime.now(dt.timezone.utc)
    session.commit()
    fp2 = compute_evidence_fingerprint(build_summary_payload(session, plan))
    assert fp1 == fp2  # a routine check with no real evidence change must not force regeneration


# --- unchanged evidence does not regenerate / refresh forces regeneration ---

def test_should_regenerate_false_when_fingerprint_and_prompt_version_unchanged(session):
    plan = _make_plan(session, annual_housing_requirement=450)
    fp = compute_evidence_fingerprint(build_summary_payload(session, plan))
    plan.ai_summary_text = "Existing summary."
    plan.ai_summary_evidence_fingerprint = fp
    plan.ai_summary_prompt_version = "local-plan-summary-v1"
    session.commit()
    assert should_regenerate(plan, fp) is False


def test_should_regenerate_true_when_no_summary_exists():
    plan = LocalPlan(council_code="x", plan_name="x", status="unknown")
    assert should_regenerate(plan, "any-fingerprint") is True


def test_should_regenerate_true_when_force_even_if_unchanged(session):
    plan = _make_plan(session, annual_housing_requirement=450)
    fp = compute_evidence_fingerprint(build_summary_payload(session, plan))
    plan.ai_summary_text = "Existing summary."
    plan.ai_summary_evidence_fingerprint = fp
    plan.ai_summary_prompt_version = "local-plan-summary-v1"
    session.commit()
    assert should_regenerate(plan, fp, force=True) is True


def test_generate_summary_does_not_call_ai_when_nothing_changed(session):
    plan = _make_plan(session, annual_housing_requirement=450)
    client = _fake_client(_GOOD_OUTPUT)

    first = generate_local_plan_summary(session, client, plan)
    assert first["regenerated"] is True

    second = generate_local_plan_summary(session, client, plan)
    assert second["regenerated"] is False
    assert second["summary_text"] == first["summary_text"]


def test_generate_summary_force_regenerates_even_when_unchanged(session):
    plan = _make_plan(session, annual_housing_requirement=450)
    client = _fake_client(_GOOD_OUTPUT)

    generate_local_plan_summary(session, client, plan)
    forced = generate_local_plan_summary(session, client, plan, force=True)
    assert forced["regenerated"] is True


# --- AI output cannot introduce unsupported figures ---

def test_validate_summary_output_rejects_a_hallucinated_number(session):
    plan = _make_plan(session, annual_housing_requirement=450)
    payload = build_summary_payload(session, plan)
    bad_output = {
        "summary_text": "The annual housing requirement is 99999 dwellings.",
        "key_risks": [], "key_opportunities": [], "evidence_gaps": [],
    }
    is_valid, unsupported = validate_summary_output(payload, bad_output)
    assert is_valid is False
    assert "99999" in unsupported


def test_validate_summary_output_accepts_numbers_actually_in_the_payload(session):
    plan = _make_plan(session, annual_housing_requirement=450, buffer_percentage=20.0)
    payload = build_summary_payload(session, plan)
    good_output = {
        "summary_text": "The annual housing requirement is 450 dwellings, with a 20% buffer applied elsewhere.",
        "key_risks": [], "key_opportunities": [], "evidence_gaps": [],
    }
    is_valid, unsupported = validate_summary_output(payload, good_output)
    assert is_valid is True
    assert unsupported == []


def test_regression_a_year_at_the_end_of_a_sentence_is_not_falsely_rejected(session):
    # Real pilot finding (live Stockport/Bury data): "...adoption expected
    # in 2027." was captured as "2027." (trailing full stop included) by
    # an earlier version of the number regex, which then never matched
    # the allowed set's plain "2027" - a false-positive rejection of a
    # genuinely well-supported figure, not a real hallucination.
    plan = _make_plan(session, expected_adoption_date="November 2027")
    _confirmed_event(session, plan, "expected_adoption_date", "November 2027")
    payload = build_summary_payload(session, plan)
    output = {
        "summary_text": "The plan's adoption is expected in 2027. No other figures are stated here.",
        "key_risks": [], "key_opportunities": [], "evidence_gaps": [],
    }
    is_valid, unsupported = validate_summary_output(payload, output)
    assert is_valid is True, unsupported


def test_validate_summary_output_excuses_single_digit_boilerplate(session):
    plan = _make_plan(session)
    payload = build_summary_payload(session, plan)
    output = {
        "summary_text": "This plan currently has 0 allocations and no five-year supply evidence.",
        "key_risks": [], "key_opportunities": [], "evidence_gaps": [],
    }
    is_valid, unsupported = validate_summary_output(payload, output)
    assert is_valid is True


def test_generate_summary_rejects_and_does_not_persist_a_hallucinated_output(session):
    plan = _make_plan(session, annual_housing_requirement=450)
    bad_client = _fake_client({
        "summary_text": "The annual housing requirement is 99999 dwellings, a fabricated figure.",
        "key_risks": [], "key_opportunities": [], "evidence_gaps": [],
    })

    result = generate_local_plan_summary(session, bad_client, plan)
    assert result["rejected"] is True
    assert "99999" in result["rejection_reason"]
    session.refresh(plan)
    assert plan.ai_summary_text is None  # never persisted


def test_generate_summary_rejection_preserves_a_previously_good_summary(session):
    plan = _make_plan(session, annual_housing_requirement=450)
    good_client = _fake_client(_GOOD_OUTPUT)
    generate_local_plan_summary(session, good_client, plan)
    original_text = plan.ai_summary_text

    plan.ai_summary_evidence_fingerprint = "force-a-regen-attempt"
    session.commit()
    bad_client = _fake_client({
        "summary_text": "A wildly unsupported 12345678 dwelling figure appears here.",
        "key_risks": [], "key_opportunities": [], "evidence_gaps": [],
    })
    result = generate_local_plan_summary(session, bad_client, plan)
    assert result["rejected"] is True
    session.refresh(plan)
    assert plan.ai_summary_text == original_text  # untouched by the rejected attempt


# --- safe UI rendering ---

def test_generation_result_always_has_list_type_risks_opportunities_gaps(session):
    plan = _make_plan(session, annual_housing_requirement=450)
    client = _fake_client(_GOOD_OUTPUT)
    result = generate_local_plan_summary(session, client, plan)
    assert isinstance(result["key_risks"], list)
    assert isinstance(result["key_opportunities"], list)
    assert isinstance(result["evidence_gaps"], list)
    assert isinstance(result["summary_text"], str)


def test_persisted_result_for_an_ungenerated_plan_has_safe_empty_defaults(session):
    plan = _make_plan(session)  # never generated
    from app.reporting.local_plan_summary import _persisted_summary_result
    result = _persisted_summary_result(plan, regenerated=False, rejected=False, rejection_reason=None)
    assert result["summary_text"] is None
    assert result["key_risks"] == []
    assert result["key_opportunities"] == []
    assert result["evidence_gaps"] == []
    assert result["generated_at"] is None


# --- empty or partial plans ---

def test_payload_for_a_completely_empty_plan_does_not_crash_and_marks_everything_missing(session):
    # raw_status=None: "status" itself is a NOT-NULL column (defaults to
    # "unknown") and can never be genuinely "missing" - every other fact
    # field, including raw_status, can be, and that's what this test
    # actually exercises.
    plan = _make_plan(session, raw_status=None)  # no facts, no allocations, nothing
    payload = build_summary_payload(session, plan)
    assert payload["allocation_count"] == 0
    assert payload["matched_site_count"] == 0
    assert payload["progression_status_counts"] == {}
    non_status_facts = {k: v for k, v in payload["facts"].items() if k != "status"}
    assert all(e["trust"] == "missing" for e in non_status_facts.values())

    prompt = build_summary_prompt(payload)
    assert "no allocations" in prompt.lower()


def test_payload_for_a_partial_plan_mixes_present_and_missing_facts(session):
    plan = _make_plan(session, annual_housing_requirement=450)
    session.add(LocalPlanSite(
        council_code="testcouncil", local_plan_id=plan.id, site_name="Site A", minimum_dwellings=40,
        plan_name=plan.plan_name, plan_status=plan.status, progression_signal="early_stage",
    ))
    session.commit()

    payload = build_summary_payload(session, plan)
    assert payload["facts"]["annual_housing_requirement"]["value"] == 450
    assert payload["facts"]["five_year_supply_years"]["value"] is None
    assert payload["allocation_count"] == 1
    assert payload["progression_status_counts"] == {"early_stage": 1}


def test_generate_summary_works_for_a_plan_with_no_evidence_at_all(session):
    plan = _make_plan(session)
    client = _fake_client({
        "summary_text": "This plan currently has no trusted evidence recorded - its stage, housing requirement, "
                         "delivery position, and five-year supply are all unavailable at this time.",
        "key_risks": [], "key_opportunities": [], "evidence_gaps": ["All facts are currently unavailable."],
    })
    result = generate_local_plan_summary(session, client, plan)
    assert result["regenerated"] is True
    assert result["rejected"] is False
