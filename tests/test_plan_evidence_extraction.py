"""Sprint 3B ("AI Local Plan Evidence Extraction", Part 11) - tests for
app.extraction.plan_evidence: the four extraction schemas, page-marker
prompt formatting, and the extraction call's own "one fact per field,
every time" contract. No real OpenAI call anywhere - a fake client stands
in, matching the pattern already used for external I/O across this test
suite (see tests/test_monitor.py)."""
from __future__ import annotations

import json

from app.extraction.plan_evidence import (
    CATEGORIES,
    format_pages_for_prompt,
    _build_schema,
    build_evidence_prompt,
    extract_plan_evidence,
)


# --- page-marker provenance (Part 5) ---

def test_format_pages_for_prompt_embeds_explicit_page_markers():
    text = format_pages_for_prompt([(110, "Site HOM 2.30 allocated for 40 dwellings"), (111, "Site HOM 2.31 allocated for 25 dwellings")])
    assert "[PAGE 110]" in text
    assert "[PAGE 111]" in text
    assert text.index("[PAGE 110]") < text.index("Site HOM 2.30")
    assert text.index("[PAGE 111]") < text.index("Site HOM 2.31")


def test_build_evidence_prompt_includes_page_markers_and_field_list():
    prompt = build_evidence_prompt("plan_identity", format_pages_for_prompt([(1, "Stockport Local Plan to 2042")]))
    assert "[PAGE 1]" in prompt
    assert "plan_name" in prompt
    assert "never invent" in prompt.lower()


# --- schema shape (strict, one fact per field, every time) ---

def test_every_category_schema_covers_every_declared_field():
    for category, fields in CATEGORIES.items():
        schema = _build_schema(category)
        enum = schema["schema"]["properties"]["facts"]["items"]["properties"]["field"]["enum"]
        assert set(enum) == set(fields.keys())


def test_schema_marks_value_as_nullable_string_never_forcing_a_guess():
    schema = _build_schema("plan_identity")
    value_prop = schema["schema"]["properties"]["facts"]["items"]["properties"]["value"]
    assert set(value_prop["type"]) == {"string", "null"}


def test_schema_confidence_field_has_no_enum_constraint():
    # Deliberate: nullable-string-without-enum is the pattern already
    # proven safe elsewhere in this codebase's structured outputs
    # (app.extraction.local_plan's policy_reference); an enum+null
    # combination was avoided as untested territory for this provider.
    schema = _build_schema("housing_requirement")
    confidence_prop = schema["schema"]["properties"]["facts"]["items"]["properties"]["confidence"]
    assert "enum" not in confidence_prop
    assert set(confidence_prop["type"]) == {"string", "null"}


def test_schema_is_strict_with_no_additional_properties():
    for category in CATEGORIES:
        schema = _build_schema(category)
        assert schema["schema"]["additionalProperties"] is False
        assert schema["schema"]["properties"]["facts"]["items"]["additionalProperties"] is False


class _FakeUsage:
    input_tokens = 500
    output_tokens = 100


class _FakeResponse:
    def __init__(self, output_text):
        self.output_text = output_text
        self.usage = _FakeUsage()


class _FakeClient:
    def __init__(self, facts):
        self._facts = facts
        self.calls = []

        class _Responses:
            def create(_self, model, input, text):
                self.calls.append({"model": model, "input": input, "schema_name": text["format"]["name"]})
                return _FakeResponse(json.dumps({"facts": self._facts}))

        self.responses = _Responses()


def _null_facts_for(category):
    return [{"field": f, "value": None, "source_page": None, "source_excerpt": None, "confidence": None} for f in CATEGORIES[category]]


def test_extract_plan_evidence_returns_one_fact_per_field_even_when_all_null():
    client = _FakeClient(_null_facts_for("five_year_supply"))
    facts = extract_plan_evidence(client, "five_year_supply", "some source text")
    assert {f["field"] for f in facts} == set(CATEGORIES["five_year_supply"].keys())
    assert all(f["value"] is None for f in facts)


def test_extract_plan_evidence_rejects_an_unknown_category():
    import pytest

    with pytest.raises(ValueError):
        extract_plan_evidence(_FakeClient([]), "not_a_real_category", "text")


def test_extract_plan_evidence_reports_usage_when_a_sink_is_given():
    client = _FakeClient(_null_facts_for("plan_identity"))
    usage_sink = []
    extract_plan_evidence(client, "plan_identity", "text", usage_sink=usage_sink)
    assert len(usage_sink) == 1
    assert usage_sink[0].input_tokens == 500
    assert usage_sink[0].output_tokens == 100
