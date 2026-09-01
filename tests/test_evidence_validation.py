"""Sprint 3B ("AI Local Plan Evidence Extraction", Part 11) - deterministic
validation tests for app.policy.evidence_validation. No network, no AI
call anywhere in this file - every fact is a hand-built dict, exactly the
shape app.extraction.plan_evidence returns."""
from __future__ import annotations

from app.policy.evidence_validation import validate_fact, validate_facts


def _fact(field, value, excerpt="the plan states a figure here", page=5, confidence="high"):
    return {"field": field, "value": value, "source_page": page, "source_excerpt": excerpt, "confidence": confidence}


# --- missing values -> null, never rejected ---

def test_null_value_is_valid_and_stays_null():
    result = validate_fact(_fact("annual_housing_requirement", None, excerpt=None, page=None, confidence=None))
    # LPDI V1 Gate 3A ("Deterministic Evidence Citation Verification") adds
    # citation_status/verified_source_page/citation_note to every result -
    # "not_checked"/original page/None here, since no pages= was given
    # (fully backward compatible - a null-value fact has no citation to
    # verify regardless).
    assert result == {
        "field": "annual_housing_requirement", "parsed_value": None,
        "is_valid": True, "rejection_reason": None, "raw_fact": result["raw_fact"],
        "citation_status": "not_checked", "verified_source_page": None, "citation_note": None,
    }


def test_free_text_field_passes_through_untouched():
    result = validate_fact(_fact("requirement_basis", "standard method uplifted for affordability"))
    assert result["is_valid"] is True
    assert result["parsed_value"] == "standard method uplifted for affordability"


# --- regression: no hallucinated evidence (Part 11's explicit fabrication test) ---

def test_regression_numeric_value_with_no_excerpt_is_rejected_not_invented():
    # A structurally sound-looking fact (a real field, a real-looking
    # number) but with no supporting excerpt at all must never become a
    # trusted proposal - this is precisely the fabrication failure mode
    # Part 11 requires a regression test for.
    result = validate_fact(_fact("annual_housing_requirement", "936", excerpt=None, page=None, confidence="high"))
    assert result["is_valid"] is False
    assert result["parsed_value"] is None
    assert "excerpt" in result["rejection_reason"]


def test_regression_excerpt_with_an_unrelated_number_does_not_support_the_claimed_value():
    # Real pilot finding (Stockport Local Plan, live document):
    # housing_need_annual=1035 was proposed with an excerpt about a house-
    # price-to-income ratio ("...is 8.6691...") - a real number, just not
    # the claimed one. The excerpt containing SOME digit is not enough;
    # it must contain THIS value.
    result = validate_fact(_fact(
        "housing_need_annual", "1035",
        excerpt="the most recently published ratio of median house prices to median incomes is 8.6691",
    ))
    assert result["is_valid"] is False
    assert "does not appear to state" in result["rejection_reason"]


def test_regression_implausible_annual_figure_that_is_really_a_plan_period_total_is_rejected():
    # Real pilot finding: annual_housing_requirement=25371 was proposed
    # from an excerpt reading "...the housing target of 25,371 as set out
    # in section 10..." - the number IS genuinely in the excerpt, but
    # 25,371 dwellings in a single year for one borough is not remotely
    # plausible; it is almost certainly the plan-PERIOD total, mislabelled.
    result = validate_fact(_fact(
        "annual_housing_requirement", "25371",
        excerpt="the housing target of 25,371 as set out in section 10 of Strategic Policy 1",
    ))
    assert result["is_valid"] is False
    assert "annual figure" in result["rejection_reason"]


def test_a_genuinely_plausible_annual_figure_is_accepted():
    result = validate_fact(_fact("annual_housing_requirement", "1370", excerpt="an annual requirement of 1,370 dwellings"))
    assert result["is_valid"] is True
    assert result["parsed_value"] == 1370


def test_regression_numeric_value_with_excerpt_containing_no_digits_is_rejected():
    # The excerpt exists but doesn't actually support a NUMBER - a strong
    # sign of a paraphrase/hallucination rather than a real transcription.
    result = validate_fact(_fact("annual_housing_requirement", "936", excerpt="the plan discusses housing supply generally"))
    assert result["is_valid"] is False
    assert "digit" in result["rejection_reason"]


def test_regression_blank_excerpt_string_is_treated_as_missing():
    result = validate_fact(_fact("plan_name", "Stockport Local Plan", excerpt="   "))
    assert result["is_valid"] is False


# --- numeric range / non-negative checks ---

def test_negative_dwelling_count_is_rejected():
    result = validate_fact(_fact("annual_housing_requirement", "-40", excerpt="a requirement of -40 dwellings"))
    assert result["is_valid"] is False
    assert "negative" in result["rejection_reason"]


def test_non_numeric_value_for_an_integer_field_is_rejected():
    result = validate_fact(_fact("annual_housing_requirement", "approximately nine hundred", excerpt="approximately nine hundred dwellings per year"))
    assert result["is_valid"] is False


def test_thousands_separator_is_parsed_correctly():
    result = validate_fact(_fact("total_plan_housing_requirement", "17,800", excerpt="a total of 17,800 dwellings"))
    assert result["is_valid"] is True
    assert result["parsed_value"] == 17800


def test_signed_field_accepts_a_negative_value():
    result = validate_fact(_fact("delivery_surplus_or_shortfall", "-120", excerpt="a shortfall of -120 dwellings against the requirement"))
    assert result["is_valid"] is True
    assert result["parsed_value"] == -120


# --- five-year supply years: explicit numeric range + never inferred ---

def test_five_year_supply_years_within_range_is_accepted():
    result = validate_fact(_fact("five_year_supply_years", "4.8", excerpt="the Council can demonstrate 4.8 years of supply"))
    assert result["is_valid"] is True
    assert result["parsed_value"] == 4.8


def test_five_year_supply_years_outside_plausible_range_is_rejected():
    result = validate_fact(_fact("five_year_supply_years", "450", excerpt="a supply figure of 450 years is stated"))
    assert result["is_valid"] is False


def test_five_year_supply_years_with_no_excerpt_is_never_inferred():
    # Part 3/Part 6: five_year_supply_years must never be filled without
    # explicit source wording - the universal "value needs an excerpt"
    # rule is what enforces this, not a field-specific special case.
    result = validate_fact(_fact("five_year_supply_years", "4.8", excerpt=None, page=None, confidence="high"))
    assert result["is_valid"] is False


# --- percentage 0-100 ---

def test_buffer_percentage_in_range_is_accepted():
    result = validate_fact(_fact("buffer_percentage", "20", excerpt="a 20% buffer is applied"))
    assert result["is_valid"] is True
    assert result["parsed_value"] == 20.0


def test_buffer_percentage_out_of_range_is_rejected():
    result = validate_fact(_fact("buffer_percentage", "150", excerpt="a 150% buffer is applied"))
    assert result["is_valid"] is False


# --- date validity ---

def test_plausible_date_with_year_is_accepted():
    result = validate_fact(_fact("adoption_date", "14 March 2027", excerpt="the plan was adopted on 14 March 2027"))
    assert result["is_valid"] is True
    assert result["parsed_value"] == "14 March 2027"


def test_date_with_implausible_year_is_rejected():
    result = validate_fact(_fact("adoption_date", "14 March 1350", excerpt="adopted 14 March 1350"))
    assert result["is_valid"] is False


def test_date_with_no_year_at_all_is_rejected():
    result = validate_fact(_fact("expected_adoption_date", "next spring", excerpt="expected next spring"))
    assert result["is_valid"] is False


def test_plan_period_year_out_of_plausible_range_is_rejected():
    result = validate_fact(_fact("plan_period_start", "1750", excerpt="the plan period begins in 1750"))
    assert result["is_valid"] is False


# --- adopted status requires explicit evidence (Part 6's named example) ---

def test_adopted_status_with_supporting_excerpt_is_accepted():
    result = validate_fact(_fact("raw_plan_status", "Adopted", excerpt="this plan was formally adopted by the Council"))
    assert result["is_valid"] is True


def test_adopted_status_with_no_excerpt_is_rejected():
    result = validate_fact(_fact("raw_plan_status", "Adopted", excerpt=None, page=None, confidence="high"))
    assert result["is_valid"] is False


def test_non_adopted_status_with_excerpt_is_unaffected_by_the_adopted_safeguard():
    result = validate_fact(_fact("raw_plan_status", "Publication", excerpt="this is the Publication version of the plan"))
    assert result["is_valid"] is True
    assert result["parsed_value"] == "Publication"


# --- cross-field: plan_period_end must not precede plan_period_start ---

def test_plan_period_end_before_start_is_rejected_by_batch_validation():
    facts = [
        _fact("plan_period_start", "2042", excerpt="the plan period runs from 2042 to 2020"),
        _fact("plan_period_end", "2020", excerpt="the plan period runs from 2042 to 2020"),
    ]
    results = validate_facts(facts)
    by_field = {r["field"]: r for r in results}
    assert by_field["plan_period_start"]["is_valid"] is True
    assert by_field["plan_period_end"]["is_valid"] is False
    assert "precedes" in by_field["plan_period_end"]["rejection_reason"]


def test_plan_period_end_after_start_is_valid():
    facts = [
        _fact("plan_period_start", "2024", excerpt="the plan period runs from 2024 to 2042"),
        _fact("plan_period_end", "2042", excerpt="the plan period runs from 2024 to 2042"),
    ]
    results = validate_facts(facts)
    assert all(r["is_valid"] for r in results)


def test_missing_one_side_of_plan_period_does_not_crash_the_cross_check():
    facts = [_fact("plan_period_start", "2024", excerpt="the plan period begins in 2024")]
    results = validate_facts(facts)
    assert results[0]["is_valid"] is True


def test_regression_equal_start_and_end_year_is_rejected():
    # Real pilot finding (Stockport Local Plan, live document): the source
    # text only stated "...to 2042" - an end year - with no explicit start
    # year on the page, and the model echoed the same figure into both
    # fields using the identical excerpt. A Local Plan period is never a
    # single year, so this must always be rejected, not silently accepted.
    facts = [
        _fact("plan_period_start", "2042", excerpt="Stockport Local Plan to 2042"),
        _fact("plan_period_end", "2042", excerpt="Stockport Local Plan to 2042"),
    ]
    results = validate_facts(facts)
    by_field = {r["field"]: r for r in results}
    assert by_field["plan_period_start"]["is_valid"] is False
    assert "never a single year" in by_field["plan_period_start"]["rejection_reason"]
    assert by_field["plan_period_end"]["is_valid"] is True  # the end year IS genuinely supported by "to 2042"
