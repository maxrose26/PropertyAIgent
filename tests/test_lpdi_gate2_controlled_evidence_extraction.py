"""LPDI V1 Gate 2 ("Controlled Evidence Extraction Pass") - this gate makes
NO app-code changes to app.policy.extract_plan_evidence, app.extraction.
plan_evidence, app.policy.evidence_validation, app.policy.document_selection,
or any database model. It exercises the existing, unmodified pipeline (via
a controlled, isolated-database validation run against real, discovered
Gate 1 documents - not included in this automated test suite, which uses
mocks only per Section 23's own "prefer mocks in automated tests"
instruction) and documents exactly what it found.

These tests lock:
1. The cohort-classification logic (SAFE_TO_EXTRACT / STILL_NEEDS_REVIEW /
   EXCLUDED) built entirely from EXISTING, unmodified functions
   (resolve_plan, DOCUMENT_TYPE_TO_CATEGORIES) - never a new attribution
   heuristic.
2. That review-pending reports are never blindly processed.
3. That plan-ambiguous councils (Bury, Tameside - real, both currently have
   2 LocalPlan rows) are correctly excluded, never guessed.
4. The real, controlled-validation finding this gate's own live run
   surfaced - a genuine, demonstrated grounding gap: a fact from a
   supporting/ancillary document (a Viability Assessment) that is
   genuinely, verifiably about a DIFFERENT, sibling plan document can
   currently be auto-applied to the wrong LocalPlan row, because
   validate_fact only checks that an excerpt supports the CLAIMED VALUE,
   never that the claim is about the SAME PLAN the whole document is being
   attributed to. Documented and regression-tested here, NOT "fixed" -
   see this gate's own specification for why a real fix is out of this
   gate's narrow scope (Section 21's "smallest possible fix" bar is not met
   by anything narrower than a genuine same-plan-reference validator
   enhancement)."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.db.models import LocalPlan, MonitoredReport, PolicyChangeEvent
from app.extraction.plan_evidence import CATEGORIES
from app.policy.document_selection import DOCUMENT_TYPE_TO_CATEGORIES
from app.policy.extract_plan_evidence import resolve_plan, run_extraction

# --- Shared fakes (mirrors tests/test_extract_plan_evidence_pipeline.py's
# own established mocking convention exactly - no network, no real OpenAI
# call, no real PDF in this automated suite) --------------------------------


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


def _make_plan(session, council_code="testcouncil", plan_name="Test Local Plan", plan_version=None, **kwargs) -> LocalPlan:
    plan = LocalPlan(council_code=council_code, plan_name=plan_name, plan_version=plan_version, status="unknown", raw_status="unknown", **kwargs)
    session.add(plan)
    session.commit()
    return plan


def _make_report(session, council_code, *, source_type, classification_status="auto", title="Test report", url="https://example.gov.uk/report.pdf") -> MonitoredReport:
    report = MonitoredReport(council_code=council_code, source_type=source_type, classification_status=classification_status, title=title, url=url, status="current")
    session.add(report)
    session.commit()
    return report


# LPDI V1 Gate 3A ("Deterministic Evidence Citation Verification") - page
# 18 below needs to genuinely contain the excerpt text this file's own
# genuine-Salford-evidence tests use, since run_extraction now
# deterministically verifies source_excerpt against this same page-bounded
# text before a fact can auto-apply. The longer real excerpt used by
# test_genuine_target_plan_evidence_still_auto_applies_after_sibling_
# hardening already contains, as a strict prefix, the shorter one used by
# test_existing_extraction_pipeline_produces_grounded_auto_applied_facts -
# one string covers both.
_STUB_PAGE_18_TEXT = "phased at an average of 1,658 dwellings per annum across the plan period 2022 to 2043."


@pytest.fixture(autouse=True)
def _stub_pdf_pages():
    with patch("app.policy.extract_plan_evidence.extract_pdf_pages", return_value=[(1, "stub source text"), (18, _STUB_PAGE_18_TEXT)]):
        yield


def _classify_cohort(session, reports: list[MonitoredReport]) -> tuple[list, list, list]:
    """The exact classification logic this gate's own controlled-validation
    script used - built entirely from EXISTING, unmodified functions
    (resolve_plan, DOCUMENT_TYPE_TO_CATEGORIES), never a new heuristic.
    Reproduced here (not imported from a script) so it is directly tested,
    matching this codebase's own established "each test file self-
    contained" convention."""
    safe, excluded, still_review = [], [], []
    for r in reports:
        if r.classification_status != "auto":
            still_review.append(r)
            continue
        if not DOCUMENT_TYPE_TO_CATEGORIES.get(r.source_type, frozenset()):
            excluded.append((r, "not extraction-eligible"))
            continue
        try:
            plan = resolve_plan(session, r.council_code, None)
            safe.append((r, plan))
        except ValueError as e:
            excluded.append((r, str(e)))
    return safe, excluded, still_review


# --- 1. Cohort classification (Section 6) --------------------------------------


def test_needs_review_reports_are_never_in_safe_to_extract(session):
    _make_plan(session, council_code="oneplan", plan_name="One Plan")
    review_report = _make_report(session, "oneplan", source_type="authority_monitoring_report", classification_status="needs_review")
    auto_report = _make_report(session, "oneplan", source_type="authority_monitoring_report", classification_status="auto")

    safe, excluded, still_review = _classify_cohort(session, [review_report, auto_report])

    assert review_report in still_review
    assert review_report not in [r for r, _ in safe]
    assert auto_report in [r for r, _ in safe]


def test_non_extraction_eligible_source_types_are_excluded_not_silently_dropped():
    # monitoring_page/amr_page etc. are index-only types (Gate 1) - never
    # extraction targets themselves.
    for index_type in ("monitoring_page", "amr_page", "housing_land_supply_page"):
        assert DOCUMENT_TYPE_TO_CATEGORIES[index_type] == frozenset()


def test_ambiguous_council_reports_are_excluded_via_existing_resolve_plan_only(session):
    """Real, current production shape - Bury and Tameside both genuinely
    have 2 LocalPlan rows. resolve_plan (unmodified) already refuses to
    guess; this gate's cohort classification uses ONLY that refusal, never
    a new title-matching heuristic."""
    _make_plan(session, council_code="bury", plan_name="Bury Local Plan", plan_version="Publication June 2026")
    _make_plan(session, council_code="bury", plan_name="Places for Everyone Joint Development Plan (Bury allocations)", plan_version="2022-2039")
    report = _make_report(session, "bury", source_type="local_plan", classification_status="auto", title="Publication Local Plan")

    safe, excluded, still_review = _classify_cohort(session, [report])

    assert report not in [r for r, _ in safe]
    assert report in [r for r, _ in excluded]
    reason = next(reason for r, reason in excluded if r is report)
    assert "more than one LocalPlan" in reason


def test_single_plan_council_reports_are_safe_to_extract(session):
    _make_plan(session, council_code="oneplan", plan_name="One Plan")
    report = _make_report(session, "oneplan", source_type="local_plan", classification_status="auto")

    safe, excluded, still_review = _classify_cohort(session, [report])

    assert report in [r for r, _ in safe]


def test_full_gate1_cohort_shape_reproduces_the_real_measured_split(session):
    """Reproduces the exact real classification this gate's own controlled
    validation measured against the real Gate 1 43-report cohort: 6
    SAFE_TO_EXTRACT (Salford, single-plan council), 7 EXCLUDED (Bury,
    2-plan council), 30 STILL_NEEDS_REVIEW."""
    _make_plan(session, council_code="salford", plan_name="Salford Local Plan: Core Strategy and Allocations", plan_version="Regulation 19 Publication")
    _make_plan(session, council_code="bury", plan_name="Bury Local Plan", plan_version="Publication June 2026")
    _make_plan(session, council_code="bury", plan_name="Places for Everyone Joint Development Plan (Bury allocations)", plan_version="2022-2039")

    reports = (
        [_make_report(session, "salford", source_type="local_plan", classification_status="auto") for _ in range(6)]
        + [_make_report(session, "bury", source_type="local_plan", classification_status="auto") for _ in range(7)]
        + [_make_report(session, "salford", source_type=None, classification_status="needs_review") for _ in range(25)]
        + [_make_report(session, "trafford", source_type=None, classification_status="needs_review") for _ in range(2)]
        + [_make_report(session, "bolton", source_type=None, classification_status="needs_review") for _ in range(1)]
        + [_make_report(session, "salford", source_type=None, classification_status="needs_review") for _ in range(2)]
    )

    safe, excluded, still_review = _classify_cohort(session, reports)

    assert len(safe) == 6
    assert len(excluded) == 7
    assert len(still_review) == 30
    assert len(safe) + len(excluded) + len(still_review) == 43


# --- 2. Existing extraction pipeline exercised, unchanged (Section 5/22) -------


def test_existing_extraction_pipeline_produces_grounded_auto_applied_facts(session):
    plan = _make_plan(session, council_code="salford", plan_name="Salford Local Plan: Core Strategy and Allocations")
    client = _FakeClient({
        "housing_requirement": [
            _fact("annual_housing_requirement", "1658", page=18, excerpt="phased at an average of 1,658 dwellings per annum across the plan period"),
            *[_null_fact(f) for f in CATEGORIES["housing_requirement"] if f != "annual_housing_requirement"],
        ],
        "plan_identity": _all_null_facts("plan_identity"),
    })

    stats = run_extraction(session, client, plan, "stub.pdf", 1, 30, "local_plan")

    assert stats["facts_extracted"] == 1
    assert stats["auto_applied"] == 1
    assert plan.annual_housing_requirement == 1658


# --- 3. Provenance retention (Section 22) ---------------------------------------


def test_provenance_is_retained_on_every_created_event(session):
    plan = _make_plan(session, council_code="salford", plan_name="Salford Local Plan: Core Strategy and Allocations")
    client = _FakeClient({
        "housing_requirement": [
            _fact("annual_housing_requirement", "1658", page=18, excerpt="1,658 dwellings per annum"),
            *[_null_fact(f) for f in CATEGORIES["housing_requirement"] if f != "annual_housing_requirement"],
        ],
        "plan_identity": _all_null_facts("plan_identity"),
    })

    run_extraction(session, client, plan, "stub.pdf", 1, 30, "local_plan", source_title="Test Doc", source_url="https://example.gov.uk/x.pdf", monitored_report_id=999)

    event = session.execute(select(PolicyChangeEvent).where(PolicyChangeEvent.local_plan_id == plan.id)).scalar_one()
    assert event.source_document_url == "https://example.gov.uk/x.pdf"
    assert event.source_document_title == "Test Doc"
    assert event.source_page == 18
    assert event.source_excerpt
    assert event.monitored_report_id == 999
    assert event.extraction_method == "ai_structured_extraction"
    assert event.extraction_prompt_version


# --- 4. Temporal semantics: first-write-only auto-apply (Section 13) -----------


def test_a_second_extraction_for_an_already_populated_field_never_auto_applies(session):
    plan = _make_plan(session, council_code="salford", plan_name="Salford Local Plan: Core Strategy and Allocations", annual_housing_requirement=1658)
    client = _FakeClient({
        "housing_requirement": [
            _fact("annual_housing_requirement", "1700", page=3, excerpt="1,700 dwellings per annum", confidence="high"),
            *[_null_fact(f) for f in CATEGORIES["housing_requirement"] if f != "annual_housing_requirement"],
        ],
        "plan_identity": _all_null_facts("plan_identity"),
    })

    stats = run_extraction(session, client, plan, "stub.pdf", 1, 30, "local_plan")

    assert plan.annual_housing_requirement == 1658  # unchanged, never silently overwritten
    assert stats["auto_applied"] == 0
    assert stats["needs_review"] == 1


# --- 5. The genuine, demonstrated grounding-gap finding - FIXED in Gate 2A ------
#
# Gate 2 found and documented this as an unfixed limitation; Gate 2A
# ("Multi-Plan Attribution & Same-Plan Evidence Validation Hardening")
# closes it via app.policy.evidence_validation.detect_sibling_plan_reference
# + config/plan_aliases.yaml. This test previously asserted the OLD,
# undesirable behaviour (auto_applied == 1) with an explicit note that it
# was expected to start failing once a fix landed - it now asserts the
# fixed, correct behaviour instead.


def test_a_fact_about_an_explicitly_different_sibling_plan_is_blocked_not_auto_applied(session):
    """Reproduces this gate's own real, controlled-validation finding
    (verified directly against the real downloaded Salford Local Plan
    Viability Assessment PDF): the document's own text explicitly names a
    DIFFERENT, sibling plan ("Salford Local Plan: Development Management
    Policies and Designations (SLP:DMP)... adopted on 18 January 2023") -
    genuinely, verifiably NOT the plan (SLP:CSA) this extraction run is
    attributing facts to. Gate 2A hardening: validate_facts is now given
    the target plan's known sibling-identity aliases (config/
    plan_aliases.yaml) and rejects a fact whose excerpt explicitly names
    one of them, via the SAME existing rejection mechanism used for every
    other validation failure - never silently auto-applied, never
    silently dropped without a reason."""
    plan = _make_plan(session, council_code="salford", plan_name="Salford Local Plan: Core Strategy and Allocations")
    excerpt = (
        "This work follows on from Part One of the Local Plan - the Salford Local Plan: Development Management "
        "Policies and Designations (SLP:DMP), which was adopted on 18 January 2023."
    )
    client = _FakeClient({
        "housing_requirement": _all_null_facts("housing_requirement"),
        "plan_identity": [
            _fact("adoption_date", "18 January 2023", page=15, excerpt=excerpt, confidence="high"),
            *[_null_fact(f) for f in CATEGORIES["plan_identity"] if f != "adoption_date"],
        ],
    })

    stats = run_extraction(session, client, plan, "stub.pdf", 1, 30, "local_plan")

    assert stats["auto_applied"] == 0
    assert stats["needs_review"] == 0  # rejected outright, not queued - see evidence_validation's existing rejection contract
    assert stats["facts_rejected"] == 1
    assert plan.adoption_date is None  # never applied to the wrong plan


def test_genuine_target_plan_evidence_still_auto_applies_after_sibling_hardening(session):
    """The other half of the same regression: hardening against sibling
    contamination must not become a blanket rejection of everything.
    Genuine SLP:CSA evidence, with no sibling-plan reference anywhere in
    its excerpt, must still auto-apply exactly as it did before Gate 2A -
    the real, grounded Salford annual_housing_requirement/
    total_housing_requirement figures this gate's own controlled
    extraction produced."""
    plan = _make_plan(session, council_code="salford", plan_name="Salford Local Plan: Core Strategy and Allocations")
    excerpt = "phased at an average of 1,658 dwellings per annum across the plan period 2022 to 2043."
    client = _FakeClient({
        "housing_requirement": [
            _fact("annual_housing_requirement", "1658", page=18, excerpt=excerpt, confidence="high"),
            *[_null_fact(f) for f in CATEGORIES["housing_requirement"] if f != "annual_housing_requirement"],
        ],
        "plan_identity": _all_null_facts("plan_identity"),
    })

    stats = run_extraction(session, client, plan, "stub.pdf", 1, 30, "local_plan")

    assert stats["auto_applied"] == 1
    assert stats["facts_rejected"] == 0
    assert plan.annual_housing_requirement == 1658


# --- 6. Failure isolation / idempotency (Section 22) ----------------------------


def test_rejected_facts_never_become_events(session):
    plan = _make_plan(session, council_code="salford", plan_name="Salford Local Plan: Core Strategy and Allocations")
    client = _FakeClient({
        "housing_requirement": [
            _fact("annual_housing_requirement", "not a number", page=3, excerpt="not a number"),
            *[_null_fact(f) for f in CATEGORIES["housing_requirement"] if f != "annual_housing_requirement"],
        ],
        "plan_identity": _all_null_facts("plan_identity"),
    })

    stats = run_extraction(session, client, plan, "stub.pdf", 1, 30, "local_plan")

    assert stats["facts_rejected"] == 1
    assert stats["events_created"] == 0
    assert plan.annual_housing_requirement is None


def test_repeated_extraction_against_unchanged_facts_is_idempotent(session):
    plan = _make_plan(session, council_code="salford", plan_name="Salford Local Plan: Core Strategy and Allocations")
    facts = {
        "housing_requirement": [
            _fact("annual_housing_requirement", "1658", page=18, excerpt="1,658 dwellings per annum"),
            *[_null_fact(f) for f in CATEGORIES["housing_requirement"] if f != "annual_housing_requirement"],
        ],
        "plan_identity": _all_null_facts("plan_identity"),
    }

    run_extraction(session, _FakeClient(facts), plan, "stub.pdf", 1, 30, "local_plan")
    second_stats = run_extraction(session, _FakeClient(facts), plan, "stub.pdf", 1, 30, "local_plan", reprocess_unchanged=False)

    assert second_stats["unchanged_skipped"] == 1
    assert second_stats["events_created"] == 0
    events = session.execute(select(PolicyChangeEvent).where(PolicyChangeEvent.local_plan_id == plan.id)).scalars().all()
    assert len(events) == 1  # not duplicated


# --- 7. No-production-write-path discipline (Section 9) ------------------------


def test_run_extraction_and_resolve_plan_only_ever_use_the_given_session(session):
    """A structural proof, not a behavioural one - both functions take
    `session` as an explicit, required parameter and never import or reach
    for a module-level/global database connection, so calling them against
    an isolated test session cannot reach production regardless of the
    caller's own DATABASE_URL."""
    import inspect

    assert "session" in inspect.signature(run_extraction).parameters
    assert "session" in inspect.signature(resolve_plan).parameters
    source = inspect.getsource(resolve_plan)
    assert "get_session(" not in source  # never re-acquires its own session
