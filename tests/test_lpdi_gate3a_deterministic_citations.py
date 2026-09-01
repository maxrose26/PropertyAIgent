"""LPDI V1 Gate 3A ("Deterministic Evidence Citation Verification") - locks
the small, application-side, deterministic citation-verification layer this
gate adds on top of Gate 2/2A's unmodified extraction pipeline:

app.policy.evidence_validation.verify_citation - given a fact's model-
supplied source_page/source_excerpt and the ACTUAL page-bounded document
text (the same [(page_number, text), ...] app.extraction.plan_evidence.
extract_pdf_pages already produces), deterministically:

  - VERIFIES the citation when the excerpt (conservatively normalised) is
    genuinely present on the cited page - source_page is kept unchanged.
  - CORRECTS the citation when the excerpt isn't on the cited page but is
    uniquely findable on exactly one other page - source_page is
    deterministically corrected, and the correction is surfaced (never
    silently pretending the model got it right).
  - Flags the citation AMBIGUOUS when the excerpt is credibly findable on
    more than one page - never guesses a page.
  - Flags the citation UNVERIFIED when the excerpt can't be found anywhere,
    or is too short/generic to trust for page reassignment at all.

Gate 2B's own real finding motivates every one of these tests: 3 of 43
sampled auto-applied facts (~7%) carried a demonstrably wrong page
citation, though every sampled VALUE was correct - the LLM identifies
evidence, the application must verify where it came from. No LLM call is
ever made by anything in this file or in verify_citation itself.

No schema change. No new review/outcome architecture - ambiguous/
unverified citations are surfaced through the SAME existing needs_review
PolicyChangeEvent pathway every other needs_review fact already uses."""
from __future__ import annotations

import json
from unittest.mock import patch

from app.db.models import LocalPlan
from app.extraction.plan_evidence import CATEGORIES
from app.policy.evidence_validation import (
    CitationVerification,
    _is_significant_excerpt,
    _normalise_for_citation,
    verify_citation,
)
from app.policy.extract_plan_evidence import run_extraction

# --- Shared fakes (same convention as Gate 2/2A's own test files) ---------------


class _FakeUsage:
    input_tokens = 1000
    output_tokens = 200


class _FakeResponse:
    def __init__(self, output_text):
        self.output_text = output_text
        self.usage = _FakeUsage()


class _FakeClient:
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


def _fact(field, value, page=5, confidence="high", excerpt=None):
    return {
        "field": field, "value": value, "source_page": page,
        "source_excerpt": excerpt or f"a supporting figure of {value} is stated in the text", "confidence": confidence,
    }


def _all_null_facts(category):
    return [_null_fact(f) for f in CATEGORIES[category]]


def _make_plan(session, council_code="testcouncil", plan_name="Test Local Plan", plan_version=None) -> LocalPlan:
    plan = LocalPlan(council_code=council_code, plan_name=plan_name, plan_version=plan_version, status="unknown", raw_status="unknown")
    session.add(plan)
    session.commit()
    return plan


# --- 1-7: verify_citation's own normalisation/matching behaviour, unit-level ----


def test_1_exact_excerpt_on_supplied_page_is_verified():
    pages = [(1, "irrelevant filler"), (5, "the annual housing requirement is 1,658 dwellings per year.")]
    result = verify_citation(
        "annual_housing_requirement", 5, "the annual housing requirement is 1,658 dwellings per year.", pages,
    )
    assert result.status == "verified"
    assert result.verified_page == 5


def test_2_normalised_whitespace_difference_is_verified():
    pages = [(5, "the   annual  housing\n\nrequirement is 1,658 dwellings per year.")]
    result = verify_citation("annual_housing_requirement", 5, "the annual housing requirement is 1,658 dwellings per year.", pages)
    assert result.status == "verified"


def test_3_line_wrap_difference_is_verified():
    # pdfplumber-style extraction: a wrapped line becomes a newline inside
    # the page's own text, splitting what was one sentence on the page.
    page_text = "the annual housing\nrequirement is 1,658\ndwellings per year."
    result = verify_citation("annual_housing_requirement", 5, "the annual housing requirement is 1,658 dwellings per year.", [(5, page_text)])
    assert result.status == "verified"


def test_4_quote_character_difference_is_verified():
    page_text = "the Council’s “adopted” requirement is 1,658 dwellings per year."
    excerpt = "the Council's \"adopted\" requirement is 1,658 dwellings per year."
    result = verify_citation("status_notes", 5, excerpt, [(5, page_text)])
    assert result.status == "verified"


def test_5_dash_character_difference_is_verified():
    page_text = "the plan period runs from 2022–2043 across the borough evidence base."  # en dash
    excerpt = "the plan period runs from 2022-2043 across the borough evidence base."  # ascii hyphen
    result = verify_citation("requirement_notes", 5, excerpt, [(5, page_text)])
    assert result.status == "verified"


def test_6_thousands_separator_variation_is_verified_where_safe():
    page_text = "the total housing requirement is 34818 net additional dwellings for the borough."
    excerpt = "the total housing requirement is 34,818 net additional dwellings for the borough."
    result = verify_citation("total_plan_housing_requirement", 5, excerpt, [(5, page_text)])
    assert result.status == "verified"


def test_7_surrounding_parenthesis_variation_is_verified_where_safe():
    page_text = "Adoption November 2027 is the next milestone in the plan's own published timetable text."
    excerpt = "Adoption (November 2027) is the next milestone in the plan's own published timetable text."
    result = verify_citation("expected_adoption_date", 5, excerpt, [(5, page_text)])
    assert result.status == "verified"


def test_normalisation_does_not_collapse_genuinely_different_text():
    """The conservative-normalisation boundary: normalisation must never
    make two DIFFERENT clauses equivalent just because they share a
    number - only the exact digit-comma formatting is unified, nothing
    about surrounding words is dropped."""
    assert _normalise_for_citation("1,658 dwellings") == "1658 dwellings"
    assert _normalise_for_citation("1,658 dwellings") != _normalise_for_citation("1,658 households")


# --- 8-9: unique-page correction, physical page semantics -----------------------


def test_8_excerpt_absent_from_cited_page_but_unique_elsewhere_is_corrected():
    pages = [
        (18, "an entirely unrelated page about consultation timetables."),
        (21, "the overall housing requirement of at least 34,818 net additional dwellings for the borough."),
    ]
    result = verify_citation(
        "total_plan_housing_requirement", 18,
        "the overall housing requirement of at least 34,818 net additional dwellings for the borough.", pages,
    )
    assert result.status == "corrected"
    assert result.verified_page == 21
    assert result.note is not None and "18" in result.note and "21" in result.note


def test_9_corrected_page_is_the_physical_pdf_page_number_not_a_printed_footer_number():
    """Gate 2B's own real finding: Bury's Local Plan PDF physical page 28
    displays a printed footer reading "27" (a one-page offset between the
    two numbering schemes). source_page must remain the PHYSICAL PDF page
    index throughout - never translated to a footer number that might
    happen to be printed inside the page's own text - because that's what
    the UI's "#page=N" deep-link (into the real PDF file) requires."""
    pages = [
        (27, "an unrelated page. Printed footer reads: 26"),
        (28, "This results in a total housing requirement of 9,486 dwellings from 2022-2043. Printed footer reads: 27"),
    ]
    result = verify_citation(
        "total_housing_requirement", 27,
        "This results in a total housing requirement of 9,486 dwellings from 2022-2043.", pages,
    )
    assert result.status == "corrected"
    assert result.verified_page == 28  # the PHYSICAL page - never "27", the footer number printed on that very page


# --- 10-12: ambiguity, no-match, and the significance floor ---------------------


def test_10_excerpt_on_multiple_pages_is_ambiguous_never_arbitrarily_corrected():
    pages = [
        (1, "the plan was prepared in accordance with the new Levelling-up and Regeneration Act 2023 system requirements."),
        (5, "the plan was prepared in accordance with the new Levelling-up and Regeneration Act 2023 system requirements."),
        (9, "a completely different page with no relation to the excerpt at all."),
    ]
    result = verify_citation(
        "planning_system", 9,
        "the plan was prepared in accordance with the new Levelling-up and Regeneration Act 2023 system requirements.", pages,
    )
    assert result.status == "ambiguous"
    assert result.verified_page is None
    assert "ambiguous" in result.note.lower()


def test_11_excerpt_occurs_nowhere_is_unverified():
    pages = [(1, "nothing here supports the claimed figure at all.")]
    result = verify_citation("annual_housing_requirement", 1, "a figure of 452 dwellings per year is stated on this page.", pages)
    assert result.status == "unverified"
    assert result.verified_page is None
    assert "could not be verified" in result.note


def test_12_very_short_generic_excerpt_cannot_trigger_unsafe_reassignment():
    """A bare, generic word/phrase for a FREE-TEXT field ("new") proved
    capable, in Gate 2B's own real sample, of trivially "matching" over
    550 of a 561-page document's pages (running headers/boilerplate) -
    genuinely meaningless as evidence of anything. Even when it happens to
    occur on exactly one page, it must never be treated as a safe,
    unique, deterministic correction."""
    pages = [(1, "irrelevant filler"), (11, "the plan adopts a new approach to something else entirely")]
    result = verify_citation("planning_system", 1, "new", pages)
    assert result.status == "unverified"
    assert "too short" in result.note


def test_12b_numeric_field_is_exempt_from_the_word_count_floor():
    """Unlike a free-text field, a short excerpt for a NUMERIC/DATE field
    already has an independent, existing value-presence guarantee
    (_excerpt_supports_number, enforced before citation verification ever
    runs) - "Total 3,847" is short but is genuinely anchored to a real
    number, not boilerplate, so it is NOT held to the same word-count
    floor as free text."""
    pages = [(5, "Total 3,847")]
    result = verify_citation("deliverable_supply_dwellings", 5, "Total 3,847", pages)
    assert result.status == "verified"


def test_significance_floor_boundary_cases_are_deterministic():
    assert _is_significant_excerpt("annual_housing_requirement", "3847") is True  # numeric field, always exempt
    assert _is_significant_excerpt("planning_system", "new") is False  # 1 word, well under floor
    assert _is_significant_excerpt("planning_system", "a new approach") is False  # 3 words, still under the 4-word floor
    assert _is_significant_excerpt("planning_system", "the plan adopts a new approach") is True  # 6 words, over both floors


# --- 13-14: existing fact-value validation and sibling-plan rejection are untouched -


def test_13_excerpt_value_mismatch_remains_rejected_by_existing_fact_validation(session):
    """A numeric claim whose excerpt doesn't support the claimed VALUE at
    all is still rejected by the existing, unmodified _excerpt_supports_
    number check, before citation verification (a different concern -
    WHERE the evidence is, not WHETHER it says what's claimed) ever runs."""
    plan = _make_plan(session)
    facts = [
        {"field": "annual_housing_requirement", "value": "936", "source_page": 5,
         "source_excerpt": "the ratio of median house prices to median incomes is 8.6691.", "confidence": "high"},
        *[_null_fact(f) for f in CATEGORIES["housing_requirement"] if f != "annual_housing_requirement"],
    ]
    with patch("app.policy.extract_plan_evidence.extract_pdf_pages", return_value=[(5, "the ratio of median house prices to median incomes is 8.6691.")]):
        stats = run_extraction(session, _FakeClient({"housing_requirement": facts, "plan_identity": _all_null_facts("plan_identity")}), plan, "stub.pdf", 1, 1, "local_plan")
    assert stats["facts_rejected"] == 1
    assert stats["auto_applied"] == 0
    assert plan.annual_housing_requirement is None


def test_14_sibling_plan_contamination_remains_rejected_with_gate3a_active(session):
    """Gate 2A's own sibling-plan protection must remain fully intact once
    Gate 3A's citation layer runs alongside it - the sibling check runs
    FIRST and short-circuits before citation verification is ever reached
    for a contaminated fact."""
    plan = _make_plan(session, council_code="salford", plan_name="Salford Local Plan: Core Strategy and Allocations")
    excerpt = (
        "the Salford Local Plan: Development Management Policies and Designations (SLP:DMP), "
        "which was adopted on 18 January 2023"
    )
    facts = [
        _fact("adoption_date", "18 January 2023", page=15, excerpt=excerpt, confidence="high"),
        *[_null_fact(f) for f in CATEGORIES["plan_identity"] if f != "adoption_date"],
    ]
    with patch("app.policy.extract_plan_evidence.extract_pdf_pages", return_value=[(15, excerpt)]):
        stats = run_extraction(session, _FakeClient({
            "housing_requirement": _all_null_facts("housing_requirement"), "plan_identity": facts,
        }), plan, "stub.pdf", 1, 30, "local_plan")
    assert stats["auto_applied"] == 0
    assert stats["facts_rejected"] == 1
    assert plan.adoption_date is None


# --- 15: table/diagram-shaped citation failure fails SAFE, never a factual rejection -


def test_15_unverifiable_citation_is_routed_to_review_not_rejected_as_incorrect(session):
    """Gate 2B's own real, demonstrated table/diagram finding: a fact's
    VALUE can be genuinely correct while its excerpt is unverifiable via
    linear page text (pdfplumber reorders a flowchart/table's visual
    layout). citation_status "unverified"/"ambiguous" must force
    needs_review, NEVER a hard rejection (is_valid=False, no event at
    all) - a citation problem is not a value problem, and the fact must
    stay visible/reviewable, not silently vanish."""
    plan = _make_plan(session)
    # A fact whose excerpt is perfectly well-formed and DOES support its
    # claimed value (so ordinary fact validation passes cleanly) but which
    # genuinely doesn't appear anywhere in the page-bounded text supplied -
    # exactly what a diagram/table text-extraction reordering produces in
    # real documents.
    facts = [
        _fact("annual_housing_requirement", "452", page=9, excerpt="a requirement of 452 dwellings per year will apply to the period."),
        *[_null_fact(f) for f in CATEGORIES["housing_requirement"] if f != "annual_housing_requirement"],
    ]
    with patch("app.policy.extract_plan_evidence.extract_pdf_pages", return_value=[(9, "Submission\nAdoption* Examination*\n(Regulation 22)\n(November 2027) (April 2027)\n(November 2026)")]):
        stats = run_extraction(session, _FakeClient({"housing_requirement": facts, "plan_identity": _all_null_facts("plan_identity")}), plan, "stub.pdf", 1, 1, "local_plan")

    # Not a hard rejection - the fact is still visible/reviewable.
    assert stats["facts_rejected"] == 0
    assert stats["facts_extracted"] == 1
    assert stats["needs_review"] == 1
    assert stats["auto_applied"] == 0


def test_ambiguous_citation_also_fails_safe_to_review_not_rejection(session):
    plan = _make_plan(session)
    excerpt_text = "a figure of 452 dwellings a year appears on this page in the plan's own housing requirement section."
    facts = [
        {"field": "annual_housing_requirement", "value": "452", "source_page": 3,
         "source_excerpt": excerpt_text, "confidence": "high"},
        *[_null_fact(f) for f in CATEGORIES["housing_requirement"] if f != "annual_housing_requirement"],
    ]
    pages = [
        # The CITED page (3) genuinely does not contain the excerpt - it
        # occurs, identically, on two OTHER pages instead - a real
        # ambiguity, never an arbitrary guess between them.
        (1, excerpt_text),
        (2, excerpt_text),
        (3, "an entirely unrelated page with no connection to this fact at all."),
    ]
    with patch("app.policy.extract_plan_evidence.extract_pdf_pages", return_value=pages):
        stats = run_extraction(session, _FakeClient({"housing_requirement": facts, "plan_identity": _all_null_facts("plan_identity")}), plan, "stub.pdf", 1, 3, "local_plan")

    assert stats["facts_rejected"] == 0
    assert stats["needs_review"] == 1
    assert stats["auto_applied"] == 0


# --- Auditability: a "corrected" citation is surfaced, never silently pretended -


def test_corrected_citation_is_surfaced_in_the_stats_proposal_and_event_detail(session):
    plan = _make_plan(session)
    facts = [
        _fact("total_plan_housing_requirement", "34818", page=18, excerpt="the overall housing requirement of at least 34,818 net additional dwellings."),
        *[_null_fact(f) for f in CATEGORIES["housing_requirement"] if f != "total_plan_housing_requirement"],
    ]
    pages = [
        (18, "an unrelated page about consultation timetables."),
        (21, "the overall housing requirement of at least 34,818 net additional dwellings."),
    ]
    with patch("app.policy.extract_plan_evidence.extract_pdf_pages", return_value=pages):
        stats = run_extraction(session, _FakeClient({"housing_requirement": facts, "plan_identity": _all_null_facts("plan_identity")}), plan, "stub.pdf", 1, 30, "local_plan")

    assert stats["auto_applied"] == 1
    proposal = stats["proposals"][0]
    assert proposal["citation_status"] == "corrected"
    assert proposal["source_page"] == 21  # the corrected, physical page - written to PolicyChangeEvent.source_page

    from app.db.models import PolicyChangeEvent
    event = session.query(PolicyChangeEvent).filter_by(local_plan_id=plan.id).one()
    assert event.source_page == 21
    assert "18" in event.detail and "21" in event.detail  # original model page still visible in the audit trail
    assert plan.total_housing_requirement == 34818  # the VALUE was correct all along - only the citation needed correcting


# --- not_checked backward compatibility (no pages given) ------------------------


def test_pages_none_is_fully_backward_compatible():
    result = verify_citation("annual_housing_requirement", 5, "anything at all", None)
    assert result == CitationVerification("not_checked", 5, None)


def test_no_excerpt_is_not_checked_not_a_crash():
    result = verify_citation("annual_housing_requirement", 5, None, [(5, "some text")])
    assert result.status == "not_checked"
