"""LPDI V1 Gate 2A ("Multi-Plan Attribution & Same-Plan Evidence Validation
Hardening") - locks the small, reusable app-code hardening this gate adds on
top of Gate 2's unmodified pipeline:

1. app.policy.plan_identity - config-driven (config/plan_aliases.yaml) plan
   identity/alias resolution, generic across every council (never a
   per-authority hardcoded rule).
2. app.policy.plan_attribution.attribute_report - report-level attribution
   using existing signals (plans_for_council, MonitoredSource.local_plan_id,
   report/source title alias matching) instead of Gate 2's
   resolve_plan()-only "any multi-plan council is excluded" limitation.
3. app.policy.evidence_validation.detect_sibling_plan_reference - fact-level
   validation hardening: a fact whose excerpt (or its own sentence within
   the full source text) explicitly names a different, known sibling plan
   is rejected via the SAME existing rejection mechanism, never silently
   auto-applied.

No schema change. No new database table. Every test here uses the SAME
_FakeClient/session mocking convention as Gate 2's own test file - no
network, no real OpenAI call, no real PDF."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.db.models import LocalPlan, MonitoredReport, MonitoredSource
from app.extraction.plan_evidence import CATEGORIES
from app.policy.evidence_validation import detect_sibling_plan_reference, validate_facts
from app.policy.extract_plan_evidence import run_extraction
from app.policy.plan_attribution import AUTHORITY_WIDE_CAPABLE_SOURCE_TYPES, attribute_report
from app.policy.plan_identity import aliases_for_plan, sibling_alias_groups

# --- Shared fakes (same convention as test_lpdi_gate2_controlled_evidence_extraction.py) --


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


def _make_source(session, council_code, *, source_type, local_plan_id=None, title="Test source", url="https://example.gov.uk/source") -> MonitoredSource:
    source = MonitoredSource(council_code=council_code, source_type=source_type, local_plan_id=local_plan_id, title=title, url=url)
    session.add(source)
    session.commit()
    return source


@pytest.fixture(autouse=True)
def _stub_pdf_pages():
    with patch("app.policy.extract_plan_evidence.extract_pdf_pages", return_value=[(1, "stub source text")]):
        yield


def _make_report(session, council_code, *, source_type, monitored_source_id=None, local_plan_id=None,
                  classification_status="auto", title="Test report", url="https://example.gov.uk/report.pdf") -> MonitoredReport:
    report = MonitoredReport(
        council_code=council_code, source_type=source_type, classification_status=classification_status,
        title=title, url=url, status="current", monitored_source_id=monitored_source_id, local_plan_id=local_plan_id,
    )
    session.add(report)
    session.commit()
    return report


# --- A. Single-plan authority still resolves normally --------------------------


def test_single_plan_authority_resolves_via_attribute_report(session):
    plan = _make_plan(session, council_code="oneplan", plan_name="One Plan")
    report = _make_report(session, "oneplan", source_type="local_plan", title="Anything at all")

    result = attribute_report(session, report)

    assert result.status == "PLAN_MATCH"
    assert result.plan.id == plan.id
    assert "single-plan" in result.reason


# --- B/E. Multi-plan authority NOT resolved from authority alone; genuine ambiguity
# remains review-required --------------------------------------------------------


def test_multi_plan_authority_with_no_signal_is_ambiguous_not_guessed(session):
    _make_plan(session, council_code="twoplans", plan_name="Plan One")
    _make_plan(session, council_code="twoplans", plan_name="Plan Two")
    report = _make_report(session, "twoplans", source_type="local_plan", title="Generic Local Plan document")

    result = attribute_report(session, report)

    assert result.status == "AMBIGUOUS"
    assert result.plan is None


# --- C. Explicit trusted source config resolves correctly (Tier 1) --------------


def test_trusted_source_plan_name_resolves_correctly(session):
    plan_a = _make_plan(session, council_code="twoplans", plan_name="Plan One")
    _make_plan(session, council_code="twoplans", plan_name="Plan Two")
    source = _make_source(session, "twoplans", source_type="monitoring_page", local_plan_id=plan_a.id)
    report = _make_report(session, "twoplans", source_type="local_plan", monitored_source_id=source.id,
                           local_plan_id=source.local_plan_id, title="Generic document, no plan name in title")

    result = attribute_report(session, report)

    assert result.status == "PLAN_MATCH"
    assert result.plan.id == plan_a.id
    assert "trusted source configuration" in result.reason


# --- D. Explicit report/document plan identity resolves correctly (Tier 2) ------


def test_report_title_alias_resolves_correctly(session):
    plan_a = _make_plan(session, council_code="bury", plan_name="Bury Local Plan", plan_version="Publication June 2026")
    _make_plan(session, council_code="bury", plan_name="Places for Everyone Joint Development Plan (Bury allocations)", plan_version="2022-2039")
    report = _make_report(session, "bury", source_type="local_plan", title="Publication Local Plan representation guidance note")

    result = attribute_report(session, report)

    assert result.status == "PLAN_MATCH"
    assert result.plan.id == plan_a.id


# --- I. Bury Local Plan report resolves to Bury Local Plan when explicitly evidenced --


def test_bury_local_plan_titled_report_resolves_to_bury_local_plan_not_pfe(session):
    bury_lp = _make_plan(session, council_code="bury", plan_name="Bury Local Plan", plan_version="Publication June 2026")
    _make_plan(session, council_code="bury", plan_name="Places for Everyone Joint Development Plan (Bury allocations)", plan_version="2022-2039")
    report = _make_report(session, "bury", source_type="local_plan", title="Publication Local Plan Policies Map")

    result = attribute_report(session, report)

    assert result.status == "PLAN_MATCH"
    assert result.plan.id == bury_lp.id
    assert result.plan.plan_name == "Bury Local Plan"


# --- J. PfE report resolves to PfE when explicitly evidenced --------------------


def test_places_for_everyone_titled_report_resolves_to_pfe_not_bury_local_plan(session):
    _make_plan(session, council_code="bury", plan_name="Bury Local Plan", plan_version="Publication June 2026")
    pfe = _make_plan(session, council_code="bury", plan_name="Places for Everyone Joint Development Plan (Bury allocations)", plan_version="2022-2039")
    report = _make_report(session, "bury", source_type="local_plan", title="Places for Everyone Joint Development Plan - Housing Trajectory Update")

    result = attribute_report(session, report)

    assert result.status == "PLAN_MATCH"
    assert result.plan.id == pfe.id


def test_report_title_naming_more_than_one_candidate_is_ambiguous(session):
    _make_plan(session, council_code="bury", plan_name="Bury Local Plan", plan_version="Publication June 2026")
    _make_plan(session, council_code="bury", plan_name="Places for Everyone Joint Development Plan (Bury allocations)", plan_version="2022-2039")
    report = _make_report(session, "bury", source_type="local_plan", title="Bury Local Plan and Places for Everyone - joint housing statement")

    result = attribute_report(session, report)

    assert result.status == "AMBIGUOUS"
    assert "more than one candidate plan" in result.reason


# --- K. Authority-wide evidence is not falsely forced onto either plan ----------


def test_authority_wide_source_type_with_no_plan_signal_is_authority_wide_not_forced(session):
    _make_plan(session, council_code="twoplans", plan_name="Plan One")
    _make_plan(session, council_code="twoplans", plan_name="Plan Two")
    report = _make_report(session, "twoplans", source_type="authority_monitoring_report", title="Annual Monitoring Report 2025/26")

    result = attribute_report(session, report)

    assert result.status == "AUTHORITY_WIDE"
    assert result.plan is None
    assert "authority_monitoring_report" in AUTHORITY_WIDE_CAPABLE_SOURCE_TYPES


def test_authority_wide_source_type_still_yields_to_an_explicit_plan_signal(session):
    """An AMR-typed report is only AUTHORITY_WIDE as a last resort - an
    explicit title/source signal still wins, since AUTHORITY_WIDE means
    "no signal ties this to one plan", not "this source_type is always
    authority-wide"."""
    plan_a = _make_plan(session, council_code="twoplans", plan_name="Plan One")
    _make_plan(session, council_code="twoplans", plan_name="Plan Two")
    report = _make_report(session, "twoplans", source_type="authority_monitoring_report", title="Plan One Annual Monitoring Report 2025/26")

    result = attribute_report(session, report)

    assert result.status == "PLAN_MATCH"
    assert result.plan.id == plan_a.id


# --- No LocalPlan at all yet -----------------------------------------------------


def test_no_local_plan_at_all_is_ambiguous_not_an_error(session):
    report = _make_report(session, "unregistered", source_type="local_plan", title="Something")
    result = attribute_report(session, report)
    assert result.status == "AMBIGUOUS"
    assert result.plan is None


# --- F/G/H. Fact-level sibling-plan validation (Section 12's asymmetric rule) ----


def test_case_a_missing_plan_reference_does_not_reject_otherwise_grounded_evidence(session):
    """CASE A (Section 12): absence of the target plan's own name near a
    fact does NOT itself indicate a problem."""
    plan = LocalPlan(council_code="salford", plan_name="Salford Local Plan: Core Strategy and Allocations", status="unknown", raw_status="unknown")
    groups = sibling_alias_groups(plan)
    excerpt = "phased at an average of 1,658 dwellings per annum across the plan period."
    assert detect_sibling_plan_reference(excerpt, groups) is None


def test_case_b_target_plan_explicitly_identified_is_a_strong_positive(session):
    """CASE B (Section 12): the target plan's own name appearing is a
    strong positive, never itself a rejection reason."""
    plan = LocalPlan(council_code="salford", plan_name="Salford Local Plan: Core Strategy and Allocations", status="unknown", raw_status="unknown")
    groups = sibling_alias_groups(plan)
    excerpt = "The Salford Local Plan: Core Strategy and Allocations (SLP:CSA) covers the period 2022 to 2043."
    assert detect_sibling_plan_reference(excerpt, groups) is None


def test_case_c_explicit_sibling_plan_reference_blocks_even_with_short_excerpt(session):
    """CASE C (Section 12) + the real, live, controlled-validation finding
    this gate exists to fix: a short excerpt alone ("adopted on 18 January
    2023") gives no signal, but the SAME SENTENCE in the full source text
    names the sibling plan explicitly - detect_sibling_plan_reference must
    still catch it via source_text."""
    plan = LocalPlan(council_code="salford", plan_name="Salford Local Plan: Core Strategy and Allocations", status="unknown", raw_status="unknown")
    groups = sibling_alias_groups(plan)
    source_text = (
        "1.1 AspinallVerdi have been commissioned to provide viability analysis. This work follows on from "
        "Part One of the Local Plan - the Salford Local Plan: Development Management Policies and "
        "Designations (SLP:DMP), which was adopted on 18 January 2023. The assessment examines the "
        "cumulative impact of adopted planning policies."
    )
    reason = detect_sibling_plan_reference("adopted on 18 January 2023", groups, source_text)
    assert reason is not None
    assert "Development Management Policies" in reason or "SLP:DMP" in reason


def test_sibling_mention_in_a_different_sentence_does_not_block_genuine_evidence(session):
    """The Bury Local Plan regression finding: a document can legitimately
    mention a sibling plan (Places for Everyone) in a NEARBY but different
    sentence while still correctly stating its OWN plan's genuine figure -
    the sentence-boundary check must not treat this as contamination."""
    plan = LocalPlan(council_code="bury", plan_name="Bury Local Plan", status="unknown", raw_status="unknown")
    groups = sibling_alias_groups(plan)
    source_text = (
        "4.2 The scale of housing growth to be accommodated up to 2039 has been set through the Joint "
        "Places for Everyone Development Plan, as set out in Table 1. Bury housing requirement 452. "
        "4.4 As a result, a requirement of 452 dwellings per year will apply to the period from 2039 to "
        "2043. This results in a total housing requirement of 9,486 dwellings from 2022 to 2043."
    )
    reason = detect_sibling_plan_reference("total housing requirement of 9,486 dwellings", groups, source_text)
    assert reason is None


def test_no_config_entry_for_a_plan_means_no_sibling_groups_and_nothing_is_blocked(session):
    """A plan with zero config/plan_aliases.yaml entry degrades safely -
    aliases_for_plan falls back to just its own plan_name, and
    sibling_alias_groups returns no groups (nothing to conflict with)."""
    plan = LocalPlan(council_code="nowhereville", plan_name="Nowhereville Local Plan", status="unknown", raw_status="unknown")
    assert aliases_for_plan(plan) == ["Nowhereville Local Plan"]
    assert sibling_alias_groups(plan) == []
    assert detect_sibling_plan_reference("anything at all, mentioning any other plan by name", []) is None


# --- End-to-end via run_extraction (real wiring, fake OpenAI client) ------------


def test_run_extraction_blocks_sibling_plan_fact_end_to_end(session):
    plan = _make_plan(session, council_code="salford", plan_name="Salford Local Plan: Core Strategy and Allocations")
    # The excerpt itself names the sibling plan directly here - proving the
    # mechanism is wired all the way through run_extraction (sibling_groups
    # computed from the target plan, threaded into validate_facts, into a
    # real rejection). The narrower "short excerpt, full context only in
    # source_text" case is exercised at the detect_sibling_plan_reference
    # unit level above (test_case_c_...), where the source_text can be
    # controlled precisely.
    excerpt = "the Salford Local Plan: Development Management Policies and Designations (SLP:DMP), which was adopted on 18 January 2023"
    client = _FakeClient({
        "housing_requirement": _all_null_facts("housing_requirement"),
        "plan_identity": [
            _fact("adoption_date", "18 January 2023", page=15, excerpt=excerpt, confidence="high"),
            *[_null_fact(f) for f in CATEGORIES["plan_identity"] if f != "adoption_date"],
        ],
    })

    stats = run_extraction(session, client, plan, "stub.pdf", 1, 30, "local_plan")

    assert stats["auto_applied"] == 0
    assert stats["facts_rejected"] == 1
    assert plan.adoption_date is None


def test_run_extraction_still_auto_applies_genuine_target_plan_evidence(session):
    plan = _make_plan(session, council_code="salford", plan_name="Salford Local Plan: Core Strategy and Allocations")
    client = _FakeClient({
        "housing_requirement": [
            _fact("annual_housing_requirement", "1658", page=18, excerpt="1,658 dwellings per annum across the plan period", confidence="high"),
            *[_null_fact(f) for f in CATEGORIES["housing_requirement"] if f != "annual_housing_requirement"],
        ],
        "plan_identity": _all_null_facts("plan_identity"),
    })

    stats = run_extraction(session, client, plan, "stub.pdf", 1, 30, "local_plan")

    assert stats["auto_applied"] == 1
    assert plan.annual_housing_requirement == 1658
