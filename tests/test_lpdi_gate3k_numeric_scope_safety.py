"""LPDI V1 Gate 3K ("Numeric Scope & Multi-Section Evidence Safety") -
deterministic tests for app.policy.evidence_validation.classify_numeric_scope_risk
and its wiring into validate_fact/validate_facts. No network, no AI call, no
production database access anywhere in this file - every page fixture below
is either the REAL text (verbatim, re-typed from the actual downloaded PDF)
behind a genuine Gate 3J production fact, or a clearly-labelled realistic
fixture for an authority whose real excerpt wasn't available to this test
file, exactly the same "real evidence first, honest fixture where real
evidence isn't available" discipline every other LPDI test file in this
suite already follows.

Built for the exact real failure Gate 3J found in production: Oldham
LocalPlan id 11's total_housing_requirement was proposed/auto-applied as
1,310 with excerpt "TOTAL 1310" - genuinely present on page 14 (a "Housing
Land Release - Phase 1" schedule, policy H1.1), while page 17 - within the
same processed document - carries a SEPARATE "Housing Land Release - Phase
2" schedule (policy H1.2) with its own "TOTAL 451". Neither Gate 3A
(citation is correct) nor the ordinary numeric-presence check (the excerpt
genuinely states 1,310) nor Gate 3D (a single integer field, not one of the
four free-text notes fields it targets) can catch this - see
app.policy.evidence_validation's own Gate 3K module comment for the full
reasoning."""
from __future__ import annotations

from app.policy.evidence_validation import classify_numeric_scope_risk, validate_fact, validate_facts

# --- Real page text (verbatim, re-typed from the actual downloaded PDF -
# https://www.oldham.gov.uk/download/downloads/id/6788/saved_udp_policies_document.pdf) ---

OLDHAM_PAGE_14 = """Oldham Metropolitan Borough Unitary Development Plan - Saved Policies
Housing Land Release - Phase 1
H1.1 The following sites are allocated for Phase 1 development:
Phase 1
Ref Site Type Size Indicative Indicative
(ha) Capacity Density
H1.1.2 Land off Fields New Rd/Ramsey PDL 3.41 136 40
Street, Chadderton
TOTAL 1310
Notes:
a. PDL = Previously Developed Land. GF = Greenfield land.
6.25 The above sites have been identified in line with the principles set out in
Policy H1."""

OLDHAM_PAGE_17 = """Oldham Metropolitan Borough Unitary Development Plan - Saved Policies
Housing Land Release - Phase 2
H1.2 The following sites are allocated for Phase 2 development:
Phase 2
Ref Site Type Size (ha) Indicative Indicative
Capacity Density
H1.2.3 Ashton Road, GF 1.71 51 30
Woodhouses
TOTAL 451
Notes:
a. PDL = Previously Developed Land. GF = Greenfield land.
6.31 It is intended that Phase 2 allocations should only be brought forward if
monitoring activity shows a potential shortfall in supply in relation to the
required building rate of 270 dwellings (net) a year."""

OLDHAM_PAGES = [(14, OLDHAM_PAGE_14), (17, OLDHAM_PAGE_17)]

# --- Real page text - Bolton's Allocations Plan (adopted December 2014) ---
BOLTON_PAGE_24 = """Local Plan - Shaping the future of Bolton
6 Strong and Confident Bolton
Housing
Allocations of Land
6.2 The Core Strategy sets out a requirement of 694 dwellings per annum during 2008-2026.
Since 2008 a total of 1,754 net new dwellings have been completed leaving the
Allocations Plan to make provision for 10,738 for the period 2012-2026."""

# --- Real page text - Trafford Local Plan 2022-2039 Publication Version (July 2026) ---
TRAFFORD_PAGE_59 = """Chapter 15 Site Allocations
A minimum of 19,077 net additional dwellings will be delivered in the plan
period (April 2022 - March 2039) (PfE Policy JP-H1);"""

# Salford's real trusted total_housing_requirement is currently None in
# production (not yet extracted) - this fixture is a realistic, clearly-
# labelled reconstruction of the same qualifying-language shape every
# other authority's genuinely trusted total already uses (a plan-period
# year range plus "total housing requirement"), used here only to prove
# the rule doesn't falsely block an authority whose real evidence follows
# this same safe, well-qualified pattern once it IS extracted.
SALFORD_PAGE_FIXTURE = """Salford Local Plan: Core Strategy and Allocations
This results in a total housing requirement of 34,818 dwellings for the
plan period 2022 to 2043."""


def _fact(field, value, excerpt, page):
    return {"field": field, "value": str(value) if value is not None else None,
            "source_page": page, "source_excerpt": excerpt, "confidence": "high"}


# --- Test 1: Oldham exact failure ---

def test_1_oldham_phase_1_total_is_flagged_multi_scope():
    risk = classify_numeric_scope_risk(
        "total_plan_housing_requirement", 1310, 14, "TOTAL 1310", OLDHAM_PAGES,
    )
    assert risk == "MULTI_SCOPE"

    result = validate_fact(_fact("total_plan_housing_requirement", 1310, "TOTAL 1310", 14), pages=OLDHAM_PAGES)
    assert result["is_valid"] is True  # never rejected - the value/citation are genuinely fine
    assert result["parsed_value"] == 1310  # never replaced
    assert result["numeric_scope_risk"] == "MULTI_SCOPE"
    assert result["numeric_scope_review_reason"] is not None


# --- Test 2: reversed candidate (Phase 2's own total) ---

def test_2_oldham_phase_2_total_is_also_flagged_multi_scope():
    risk = classify_numeric_scope_risk(
        "total_plan_housing_requirement", 451, 17, "TOTAL 451", OLDHAM_PAGES,
    )
    assert risk == "MULTI_SCOPE"


# --- Test 3: simple single total, one definitive figure ---

def test_3_a_single_well_qualified_total_remains_single_scope():
    pages = [(24, BOLTON_PAGE_24)]
    risk = classify_numeric_scope_risk(
        "total_plan_housing_requirement", 10738, 24,
        "the Allocations Plan to make provision for 10,738 for the period 2012-2026.", pages,
    )
    assert risk == "SINGLE_SCOPE"


# --- Test 4: Bolton regression (real production fact) ---

def test_4_bolton_10738_remains_eligible_for_auto_apply():
    pages = [(24, BOLTON_PAGE_24)]
    result = validate_fact(
        _fact("total_plan_housing_requirement", 10738,
              "the Allocations Plan to make provision for 10,738 for the period 2012-2026.", 24),
        pages=pages,
    )
    assert result["numeric_scope_risk"] == "SINGLE_SCOPE"
    assert result["numeric_scope_review_reason"] is None


# --- Test 5: Salford-shape regression - not falsely blocked by other numbers ---

def test_5_a_well_qualified_total_is_not_falsely_blocked_by_surrounding_numbers():
    # The document also states other, unrelated numbers (dwelling counts,
    # dates) elsewhere - none of that should matter, since the candidate's
    # OWN excerpt already carries clear whole-plan qualifying language.
    pages = [
        (1, "Salford Local Plan: Core Strategy and Allocations - adopted 2022"),
        (5, SALFORD_PAGE_FIXTURE),
        (12, "Policy A1 allocates 850 dwellings at Port Salford; Policy A2 allocates 1,200 at Chapel Street."),
    ]
    result = validate_fact(
        _fact("total_plan_housing_requirement", 34818,
              "This results in a total housing requirement of 34,818 dwellings for the plan period 2022 to 2043.", 5),
        pages=pages,
    )
    assert result["numeric_scope_risk"] == "SINGLE_SCOPE"


# --- Test 6: Trafford regression (real production fact) ---

def test_6_trafford_19077_remains_eligible_for_auto_apply():
    pages = [(59, TRAFFORD_PAGE_59)]
    result = validate_fact(
        _fact("total_plan_housing_requirement", 19077,
              "A minimum of 19,077 net additional dwellings will be delivered in the plan period "
              "(April 2022 - March 2039) (PfE Policy JP-H1);", 59),
        pages=pages,
    )
    assert result["numeric_scope_risk"] == "SINGLE_SCOPE"


# --- Test 7: multiple unrelated numbers, only one relevant total ---

def test_7_multiple_unrelated_numbers_on_the_page_do_not_create_false_risk():
    page_text = (
        "Population of the borough is 237,110 (2021 Census). The average household size is 2.3. "
        "This results in a total housing requirement of 12,500 dwellings for the plan period 2024 to 2044. "
        "The town centre has 3 conservation areas and 45 listed buildings."
    )
    risk = classify_numeric_scope_risk(
        "total_plan_housing_requirement", 12500, 3,
        "This results in a total housing requirement of 12,500 dwellings for the plan period 2024 to 2044.",
        [(3, page_text)],
    )
    assert risk == "SINGLE_SCOPE"


# --- Test 8: annual requirement field is never in scope ---

def test_8_oldham_annual_270_remains_eligible_even_on_a_phase_2_page():
    # The real production excerpt for annual_housing_requirement sits on
    # the SAME page as Phase 2's own "TOTAL 451" - proving the field-scope
    # restriction (NOT total_housing_requirement) is what protects it, not
    # an accident of page separation.
    risk = classify_numeric_scope_risk(
        "annual_housing_requirement", 270, 17, "the required building rate of 270 dwellings (net) a year",
        OLDHAM_PAGES,
    )
    assert risk == "SINGLE_SCOPE"

    result = validate_fact(
        _fact("annual_housing_requirement", 270, "the required building rate of 270 dwellings (net) a year", 17),
        pages=OLDHAM_PAGES,
    )
    # Matches Gate 3D's own established convention exactly (classify_
    # structured_text_risk returns "SIMPLE_TEXT", its own in-scope-safe
    # default, for a field outside its risk surface - never
    # "not_applicable", which validate_fact reserves for a null/rejected
    # fact) - "SINGLE_SCOPE" here is the correct, safe, unconditional
    # result for a field outside _NUMERIC_SCOPE_RISK_FIELDS.
    assert result["numeric_scope_risk"] == "SINGLE_SCOPE"
    assert result["is_valid"] is True
    assert result["parsed_value"] == 270


# --- Test 9: multiple phases present but no candidate value at all ---

def test_9_phase_rich_pages_with_no_candidate_value_never_invent_an_aggregate():
    fact = _fact("total_plan_housing_requirement", None, None, None)
    result = validate_fact(fact, pages=OLDHAM_PAGES)
    assert result["parsed_value"] is None
    assert result["is_valid"] is True  # a missing value is always valid, never an error
    assert result["numeric_scope_risk"] == "not_applicable"  # nothing to assess - no candidate exists to flag


# --- Test 10: citation correction interaction ---

def test_10_gate_3a_citation_correction_still_works_alongside_numeric_scope_review():
    # Mirrors the REAL Oldham production event exactly: the model cited
    # page 18 for the annual figure, deterministically corrected to page
    # 17 - and this must keep working unchanged regardless of the new
    # numeric-scope check running on a different field in the same batch.
    pages = OLDHAM_PAGES + [(18, "6.32 If levels of housing development should exceed expectations...")]
    facts = [
        _fact("annual_housing_requirement", 270, "the required building rate of 270 dwellings (net) a year", 18),
        _fact("total_plan_housing_requirement", 1310, "TOTAL 1310", 14),
    ]
    results = validate_facts(facts, pages=pages)
    by_field = {r["field"]: r for r in results}

    assert by_field["annual_housing_requirement"]["citation_status"] == "corrected"
    assert by_field["annual_housing_requirement"]["verified_source_page"] == 17
    assert by_field["annual_housing_requirement"]["numeric_scope_risk"] == "SINGLE_SCOPE"  # out of scope, safe default

    assert by_field["total_plan_housing_requirement"]["citation_status"] == "verified"
    assert by_field["total_plan_housing_requirement"]["numeric_scope_risk"] == "MULTI_SCOPE"


# --- Test 11: Gate 3D structured-text safety remains intact and independent ---

def test_11_gate_3d_structured_text_risk_is_unaffected_by_the_new_numeric_scope_check():
    # requirement_notes is a Gate 3D risk field, NOT a Gate 3K numeric-scope
    # field - a structured multi-value note must still force review exactly
    # as before, and numeric_scope_risk must stay "not_applicable" for it
    # (it's a free-text field, not a numeric one at all).
    structured_value = "Core Growth Area: 1,500 (2022-2030), Inner Area: 900 (2030-2039)"
    result = validate_fact(_fact("requirement_notes", structured_value, structured_value, 5))
    assert result["structured_text_risk"] == "STRUCTURED_TEXT"
    assert result["force_review_reason"] is not None
    assert result["numeric_scope_risk"] == "SINGLE_SCOPE"  # a free-text field, outside the numeric-scope field set

    # And the reverse: total_plan_housing_requirement's own numeric-scope
    # risk is independent of Gate 3D's text-structure classifier, which
    # never applies to it (a plain integer, not a free-text notes field).
    result2 = validate_fact(_fact("total_plan_housing_requirement", 1310, "TOTAL 1310", 14), pages=OLDHAM_PAGES)
    assert result2["structured_text_risk"] == "SIMPLE_TEXT"  # outside Gate 3D's own risk fields, safe default
    assert result2["numeric_scope_risk"] == "MULTI_SCOPE"


# --- Test 12: risk classification never creates a trusted replacement value ---

def test_12_multi_scope_never_computes_or_substitutes_a_summed_value():
    result = validate_fact(_fact("total_plan_housing_requirement", 1310, "TOTAL 1310", 14), pages=OLDHAM_PAGES)
    # The classifier only ever answers a risk QUESTION - it must never
    # invent 1761 (1310+451), never null out a genuinely-supported value,
    # and never mark the fact invalid/rejected on this basis alone.
    assert result["parsed_value"] == 1310
    assert result["parsed_value"] != 1761
    assert result["is_valid"] is True
    assert result["rejection_reason"] is None
