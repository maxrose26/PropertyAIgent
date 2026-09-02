"""LPDI V1 Gate 3D ("Structured Evidence Semantic Safety") - locks the
narrow, deterministic safety layer that closes the specific trust gap Gate
3C found in real production: a free-text fact (`requirement_notes`) whose
excerpt is genuinely on the correct, citation-verified page, and whose
individual numbers are genuinely present in the source, can still encode a
WRONG structured relationship between periods and values (a table-column
misattribution) that nothing in the existing validation architecture
checks - `_validate_fact_fields`'s free-text branch only confirms value/
excerpt are non-empty (PRESENCE), never that a label/period is correctly
paired with its value (SEMANTIC RELATIONSHIP).

This is deliberately NOT a table-understanding project - see
app.policy.evidence_validation.classify_structured_text_risk's own
docstring. The rule targets exactly one narrow, well-evidenced shape:
free-text "notes" fields whose value states MULTIPLE period/label -> value
relationships that cannot be verified against a single, contiguous source
excerpt - and routes those to needs_review rather than guessing or
rejecting outright, preserving "a citation problem/semantic-ambiguity
problem is not necessarily a value problem" (the same principle Gate 3A
already established for citation verification)."""
from __future__ import annotations

from app.policy.evidence_validation import (
    classify_structured_text_risk,
    validate_fact,
    validate_facts,
)

# --- Step 2: reproduce the failure class BEFORE any fix (generic, not Trafford-named) --


def _period_value_fact(field="requirement_notes"):
    """The underlying failure CLASS this gate exists to close - a
    free-text fact whose VALUE states three period -> annual-figure
    relationships, drawn from a table whose linearised text made the
    period/value pairing ambiguous. Modelled on, but not literally naming,
    the real Gate 3C Trafford case (specifications/018 and the Gate 3C
    final report): a genuinely-shifted table-column reading where every
    individual number is real and present in the source, but paired with
    the wrong period."""
    return {
        "field": field,
        "value": "Annual delivery varies by period: 1,122 (2022-2025), 817 (2025-2030), 1,122 (2030-2039).",
        "source_page": 59,
        "source_excerpt": "stepped phasing for the delivery of new homes will be implemented as set out in Table 5-2",
        "confidence": "high",
    }


def test_step2_reproduction_the_failure_class_is_real_and_unguarded_by_presence_validation():
    """This is the reproduction test Gate 3D's own Step 2 requires: proves
    the underlying failure class is real BEFORE any semantic-safety code
    exists, by exercising only the presence-validation rules that predate
    this gate (excerpt is non-empty, value is non-empty) - never a
    semantic-relationship check. If this assertion ever fails, it means
    presence validation alone started rejecting the fact for some other
    reason - re-check the fixture, not this gate's own new mechanism."""
    fact = _period_value_fact()
    # The two REAL, pre-existing presence checks a free-text field must
    # pass - both trivially satisfied here, exactly as they were for the
    # real Trafford proposal:
    assert isinstance(fact["value"], str) and fact["value"].strip()
    assert fact["source_excerpt"] and fact["source_excerpt"].strip()
    # Multiple genuine numbers really are present in the excerpt/value -
    # nothing here is fabricated text-wise, only the period/value PAIRING
    # is wrong, which is exactly what presence-only validation cannot see.
    assert "1,122" in fact["value"] and "817" in fact["value"]


# --- Step 4: risk-surface classification -----------------------------------------


def test_structured_text_risk_classifies_the_reproduction_case_as_structured():
    assert classify_structured_text_risk("requirement_notes", _period_value_fact()["value"]) == "STRUCTURED_TEXT"


def test_structured_text_risk_classifies_simple_prose_as_simple():
    assert classify_structured_text_risk("requirement_notes", "The requirement is based on the standard method.") == "SIMPLE_TEXT"


def test_structured_text_risk_only_applies_to_the_identified_risk_surface_fields():
    """plan_name/requirement_basis/calculation_method etc. are single-
    purpose label fields, not open-ended "anything else" catch-alls - the
    real risk surface (see this module's own docstring / Gate 3D's
    specification) is the four "any other short, materially useful
    nuance..." catch-all fields (status_notes, requirement_notes,
    delivery_notes, supply_position_notes) that app.extraction.
    plan_evidence's own field descriptions define identically across all
    four categories - exactly where an unrelated multi-value table
    fragment would land. A field outside that surface is never classified
    STRUCTURED_TEXT, even given the same risky-looking value, so it is
    never held up by this new check."""
    risky_value = _period_value_fact()["value"]
    for field in ("status_notes", "requirement_notes", "delivery_notes", "supply_position_notes"):
        assert classify_structured_text_risk(field, risky_value) == "STRUCTURED_TEXT"
    for field in ("plan_name", "plan_version", "requirement_basis", "calculation_method", "next_milestone"):
        assert classify_structured_text_risk(field, risky_value) == "SIMPLE_TEXT"


# --- validate_fact end-to-end: the shipped mechanism ------------------------------


def test_1_trafford_style_shifted_table_relationship_is_not_trusted():
    result = validate_fact(_period_value_fact())
    assert result["is_valid"] is True  # not a hard rejection - see module docstring
    assert result["parsed_value"] == _period_value_fact()["value"]  # the proposal itself is preserved, not discarded
    assert result["structured_text_risk"] == "STRUCTURED_TEXT"
    assert result["force_review_reason"] is not None
    assert "structured" in result["force_review_reason"].lower()


def test_2_all_numbers_present_but_associations_wrong_still_flagged():
    """Explicitly proves presence of every individual number does NOT
    exempt the fact - this is the exact Gate 3C finding: correct document,
    correct page, real numbers, wrong relationship."""
    fact = _period_value_fact()
    assert all(n in fact["value"] for n in ("1,122", "817"))
    result = validate_fact(fact)
    assert result["structured_text_risk"] == "STRUCTURED_TEXT"


def test_3_structured_period_value_mapping_forces_review():
    fact = {
        "field": "requirement_notes", "value": "817 homes per year from 2022-2025, 1,122 from 2025-2030 and 1,224 from 2030-2039.",
        "source_page": 12, "source_excerpt": "stepped delivery rates are set out in the table below", "confidence": "high",
    }
    assert classify_structured_text_risk(fact["field"], fact["value"]) == "STRUCTURED_TEXT"
    result = validate_fact(fact)
    assert result["structured_text_risk"] == "STRUCTURED_TEXT"


def test_4_structured_label_value_mapping_forces_review():
    fact = {
        "field": "status_notes",
        "value": "Delivery split by locality: Core Growth Area: 1,500, Inner Area: 900, Northern Area: 600.",
        "source_page": 40, "source_excerpt": "the spatial distribution of housing is set out by locality in the table below",
        "confidence": "high",
    }
    assert classify_structured_text_risk(fact["field"], fact["value"]) == "STRUCTURED_TEXT"
    result = validate_fact(fact)
    assert result["structured_text_risk"] == "STRUCTURED_TEXT"


def test_5_simple_single_numeric_fact_remains_valid():
    # total_plan_housing_requirement (a whole-plan-period total, e.g. the
    # real 19,077 net additional dwellings figure) - not
    # annual_housing_requirement, whose own separate plausibility ceiling
    # (a single-authority ANNUAL figure) 19,077 would correctly, and
    # pre-existingly, fail regardless of anything Gate 3D changes.
    fact = {"field": "total_plan_housing_requirement", "value": "19077", "source_page": 59,
            "source_excerpt": "A minimum of 19,077 net additional dwellings will be delivered", "confidence": "high"}
    result = validate_fact(fact)
    assert result["is_valid"] is True
    assert result["parsed_value"] == 19077
    assert result["structured_text_risk"] in (None, "SIMPLE_TEXT", "not_applicable")
    assert result["force_review_reason"] is None


def test_6_simple_date_remains_valid():
    fact = {"field": "publication_date", "value": "July 2026", "source_page": 1,
            "source_excerpt": "Publication Version (July 2026)", "confidence": "high"}
    result = validate_fact(fact)
    assert result["is_valid"] is True
    assert result["parsed_value"] == "July 2026"
    assert result["force_review_reason"] is None


def test_7_simple_plan_period_remains_valid():
    start = validate_fact({"field": "plan_period_start", "value": "2022", "source_page": 11,
                            "source_excerpt": "the period 2022 - 2039 (the plan period)", "confidence": "high"})
    end = validate_fact({"field": "plan_period_end", "value": "2039", "source_page": 11,
                          "source_excerpt": "the period 2022 - 2039 (the plan period)", "confidence": "high"})
    assert start["is_valid"] is True and start["parsed_value"] == 2022
    assert end["is_valid"] is True and end["parsed_value"] == 2039
    assert start["force_review_reason"] is None and end["force_review_reason"] is None


def test_8_simple_requirement_basis_remains_valid():
    fact = {"field": "requirement_basis", "value": "PfE Policy JP-H1", "source_page": 59,
            "source_excerpt": "A minimum of 19,077 net additional dwellings will be delivered in the plan period (PfE Policy JP-H1)",
            "confidence": "high"}
    result = validate_fact(fact)
    assert result["is_valid"] is True
    assert result["force_review_reason"] is None


def test_9_ordinary_prose_containing_a_number_is_not_over_blocked():
    """A real, existing fixture value (see tests/test_evidence_validation.py's
    own test_regression_...) - genuine prose with incidental numeric
    content must not be swept up by a raw "does it contain 2 numbers"
    count."""
    fact = {
        "field": "requirement_notes",
        "value": "Stockport remains one of the most desirable places to live in Greater Manchester but has long-term issues of affordability and supply.",
        "source_page": 108, "source_excerpt": "Stockport remains one of the most desirable places to live", "confidence": "high",
    }
    assert classify_structured_text_risk(fact["field"], fact["value"]) == "SIMPLE_TEXT"
    result = validate_fact(fact)
    assert result["force_review_reason"] is None


def test_9b_two_unrelated_numbers_without_period_structure_not_over_blocked():
    """Step 7's own explicit warning: do not assume every sentence with
    two numbers is a table. Two genuinely unrelated figures, with no
    period/label pairing structure, must stay SIMPLE_TEXT."""
    value = "This leaves a shortfall against housing need of 15,384, out of a total need of 13,455 households."
    assert classify_structured_text_risk("requirement_notes", value) == "SIMPLE_TEXT"


def test_9c_a_single_period_value_pair_is_not_flagged_as_structured():
    """Exactly one period->value relationship has no ambiguity about which
    number belongs to which period - the product principle explicitly
    allows deterministically-supportable structured evidence to remain
    auto-apply-eligible."""
    value = "817 dwellings per year were delivered in the period 2022-2025."
    assert classify_structured_text_risk("requirement_notes", value) == "SIMPLE_TEXT"


def test_10_citation_verified_plus_semantic_structure_unsafe_forces_review():
    pages = [(59, "stepped phasing for the delivery of new homes will be implemented as set out in Table 5-2")]
    fact = _period_value_fact()
    result = validate_fact(fact, pages=pages)
    assert result["citation_status"] == "verified"  # Gate 3A's own mechanism still runs, unaffected
    assert result["structured_text_risk"] == "STRUCTURED_TEXT"
    assert result["force_review_reason"] is not None


def test_11_citation_corrected_plus_semantic_structure_unsafe_forces_review():
    fact = dict(_period_value_fact())
    fact["source_page"] = 12  # model cited the wrong page
    pages = [(12, "an unrelated page"), (59, fact["source_excerpt"])]
    result = validate_fact(fact, pages=pages)
    assert result["citation_status"] == "corrected"
    assert result["verified_source_page"] == 59
    assert result["structured_text_risk"] == "STRUCTURED_TEXT"
    assert result["force_review_reason"] is not None


def test_12_existing_sibling_plan_rejection_remains_intact():
    sibling_groups = [["Sibling Plan", "SP"]]
    fact = {"field": "adoption_date", "value": "1 January 2020", "source_page": 5,
            "source_excerpt": "the Sibling Plan (SP) was adopted on 1 January 2020", "confidence": "high"}
    result = validate_fact(fact, sibling_groups=sibling_groups)
    assert result["is_valid"] is False
    assert "different Local Plan" in result["rejection_reason"]


def test_13_citation_ambiguity_behaviour_remains_intact():
    text = "a genuinely long and specific sentence that recurs verbatim on more than one page of this document"
    pages = [(1, text), (2, text), (3, "unrelated")]
    fact = {"field": "planning_system", "value": "new", "source_page": 3, "source_excerpt": text, "confidence": "high"}
    result = validate_fact(fact, pages=pages)
    assert result["citation_status"] == "ambiguous"


def test_14_citation_unverified_behaviour_remains_intact():
    pages = [(1, "nothing here supports the claimed figure at all")]
    fact = {"field": "annual_housing_requirement", "value": "452", "source_page": 1,
            "source_excerpt": "a figure of 452 dwellings per year is stated on this page", "confidence": "high"}
    result = validate_fact(fact, pages=pages)
    assert result["citation_status"] == "unverified"


def test_15_existing_trusted_value_change_behaviour_remains_intact():
    """Gate 3D touches validate_fact only - classify_evidence_confidence
    (the "never overwrite an already-trusted value" rule) lives in
    app.policy.extract_plan_evidence and is untouched; this test locks
    that validate_fact itself still returns a normal, usable result for a
    change-worthy fact regardless of the new structured_text_risk key."""
    fact = {"field": "annual_housing_requirement", "value": "936", "source_page": 5,
            "source_excerpt": "a supporting figure of 936 is stated in the text", "confidence": "high"}
    result = validate_fact(fact)
    assert result["is_valid"] is True
    assert result["parsed_value"] == 936
    assert result["force_review_reason"] is None


def test_16_backwards_compatibility_for_callers_without_new_optional_context():
    """Every existing caller (Gate 2/2A/3A's own tests, ingest_local_plan.py,
    etc.) calls validate_fact/validate_facts with no new arguments - Gate
    3D adds no new REQUIRED parameter, and every new result key defaults
    to a safe, non-blocking value when structured-text risk simply isn't
    triggered."""
    result = validate_fact({"field": "plan_name", "value": "Test Plan", "source_page": 1,
                             "source_excerpt": "Test Plan", "confidence": "high"})
    assert "structured_text_risk" in result
    assert "force_review_reason" in result
    assert result["force_review_reason"] is None

    results = validate_facts([{"field": "plan_name", "value": "Test Plan", "source_page": 1,
                                "source_excerpt": "Test Plan", "confidence": "high"}])
    assert results[0]["force_review_reason"] is None
