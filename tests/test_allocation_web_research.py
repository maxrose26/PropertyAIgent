"""Tests for Site Selection & Reporting V1 Gate 4 - app.reporting.
allocation_web_research's bounded web research layer.

Pure-Python fixtures (AllocationReportContext is a plain dataclass tree -
no database session needed to construct one directly) + a scripted fake
OpenAI client double, never a real network/API call (Section 32 - "NO real
web calls in automated tests")."""
from __future__ import annotations

import datetime as dt
import json

from app.reporting.allocation_report import (
    AllocationIntelligenceSnapshot,
    AllocationReportAggregates,
    AllocationReportContext,
    AllocationReportEntry,
    ApplicantEvidenceEntry,
    OwnershipEvidenceEntry,
)
from app.reporting.allocation_web_research import (
    MAX_SEARCHES_PER_ALLOCATION,
    MAX_SOURCES_RETAINED_PER_ALLOCATION,
    TIER_CONTEXTUAL,
    TIER_OFFICIAL_PRIMARY,
    TIER_STRONG_SECONDARY,
    _build_allocation_search_angles,
    _classify_source_tier,
    build_allocation_web_research_context,
)

# --- Fixtures -----------------------------------------------------------------


def _make_entry(allocation_id: int, *, allocation_name="Land off Test Road", council_name="Testcouncil",
                 trusted_developer: str | None = None, applicant: str | None = None) -> AllocationReportEntry:
    ownership_evidence = []
    if trusted_developer:
        ownership_evidence.append(OwnershipEvidenceEntry(
            site_label="1 Test Street", entity_name_raw=trusted_developer, role="DEVELOPER",
            role_label="Developer", needs_review=False, application_references=[],
        ))
    applicant_evidence = []
    if applicant:
        applicant_evidence.append(ApplicantEvidenceEntry(site_label="1 Test Street", entity_name=applicant, application_references=["APP/1"]))

    return AllocationReportEntry(
        allocation_id=allocation_id, allocation_name=allocation_name, allocation_reference=f"REF-{allocation_id}",
        council_code="testcouncil", council_name=council_name, local_plan_name="Test Local Plan",
        plan_status="adopted", plan_status_label="Adopted", plan_status_bucket="adopted",
        intended_use="residential", intended_use_label="Residential",
        capacity_value=100, capacity_kind="minimum", capacity_display="Approximately 100 homes",
        identified_application_capacity=0, indicative_residual_capacity=100,
        development_coverage_percentage=0.0, development_coverage_classification="NO_IDENTIFIED_ACTIVITY",
        capacity_accounting_status="no_activity",
        linked_application_count=0, linked_applications=[],
        applicant_evidence=applicant_evidence, ownership_evidence=ownership_evidence,
        ai_intelligence=AllocationIntelligenceSnapshot(available=False),
    )


def _make_context(entries: list[AllocationReportEntry]) -> AllocationReportContext:
    agg = AllocationReportAggregates(
        allocation_count=len(entries), exact_capacity_total=sum(e.capacity_value or 0 for e in entries),
        exact_capacity_count=len(entries), ranged_capacity_count=0, unknown_capacity_count=0,
        identified_application_capacity_known_total=0, identified_application_capacity_unknown_count=0,
        indicative_residual_capacity_known_total=sum(e.indicative_residual_capacity or 0 for e in entries),
        indicative_residual_capacity_unknown_count=0, adopted_count=len(entries), emerging_count=0,
        other_plan_status_count=0, allocations_with_linked_activity=0, allocations_with_no_identified_activity=len(entries),
    )
    return AllocationReportContext(entries=entries, excluded=[], aggregates=agg, generated_at=dt.datetime.now(dt.timezone.utc))


class FakeResponse:
    def __init__(self, output_text: str | None):
        self.output_text = output_text


class FakeResponses:
    def __init__(self, script: list):
        self.script = list(script)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.script:
            raise AssertionError("FakeResponses.create called more times than scripted")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)


class FakeClient:
    """Scripted double for openai.OpenAI - .with_options(...) returns self
    (mirrors the real SDK's own chained-options shape closely enough for
    this module's usage: `client.with_options(timeout=...).responses.create(...)`)."""

    def __init__(self, script: list):
        self.responses = FakeResponses(script)

    def with_options(self, **kwargs):
        return self


def _extraction_json(items: list[dict]) -> str:
    return json.dumps({"items": items})


_GOOD_ITEM = {
    "title": "Council approves outline plans", "publisher": "Place North West", "url": "https://www.placenorthwest.co.uk/story-1",
    "published_date": "2026-01-15", "evidence_type": "news_coverage", "summary": "Outline consent discussed.",
    "confidence": "high", "relevance_reason": "Directly names the allocation.",
}

_COUNCIL_ITEM = {
    "title": "Planning committee agenda", "publisher": "Testcouncil Council", "url": "https://www.testcouncil.gov.uk/agenda-1",
    "published_date": None, "evidence_type": "council_publication", "summary": "Committee to consider the site.",
    "confidence": "medium", "relevance_reason": "Official council source.",
}


# --- Query construction (Section 6) -------------------------------------------


def test_query_construction_is_deterministic_from_trusted_fields():
    entry = _make_entry(1, allocation_name="Land off Elm Road", trusted_developer="Acme Developments Ltd")
    angles = _build_allocation_search_angles(entry, current_year=2026)

    assert any("Land off Elm Road" in a for a in angles)
    assert any("Acme Developments Ltd" in a for a in angles)
    assert len(angles) <= MAX_SEARCHES_PER_ALLOCATION


def test_query_construction_omits_developer_angle_when_no_trusted_party():
    entry = _make_entry(1, allocation_name="Land off Elm Road")
    angles = _build_allocation_search_angles(entry, current_year=2026)

    assert not any("Acme" in a for a in angles)
    assert len(angles) <= MAX_SEARCHES_PER_ALLOCATION


# --- Source tier classification (Section 7) -----------------------------------


def test_source_tier_classification():
    assert _classify_source_tier("https://www.testcouncil.gov.uk/page", frozenset()) == TIER_OFFICIAL_PRIMARY
    assert _classify_source_tier("https://www.planningportal.co.uk/x", frozenset()) == TIER_OFFICIAL_PRIMARY
    assert _classify_source_tier("https://www.placenorthwest.co.uk/story", frozenset()) == TIER_STRONG_SECONDARY
    assert _classify_source_tier("https://some-random-blog.example/post", frozenset()) == TIER_CONTEXTUAL
    assert _classify_source_tier("https://sub.trafford.gov.uk/news", frozenset({"trafford.gov.uk"})) == TIER_OFFICIAL_PRIMARY
    assert _classify_source_tier("not a url", frozenset()) == TIER_CONTEXTUAL


# --- Bounded search count / OpenAI calls (Section 5/28) -----------------------


def test_bounded_search_count_for_normal_shortlist():
    entries = [_make_entry(i) for i in range(1, 6)]  # 5 allocations - normal V1 size
    context = _make_context(entries)
    # Per allocation: 1 search call (findings=None -> no extraction call).
    # Shortlist-level: 1 search call (findings=None -> no extraction call).
    script = [None] * (len(entries) + 1)
    client = FakeClient(script)

    result = build_allocation_web_research_context(client, context)

    assert result.searches_attempted == len(entries) + 1  # one per allocation + one shortlist-level batch
    assert len(client.responses.calls) == len(entries) + 1  # exactly one OpenAI call per attempted search - no extraction call fired with empty findings


def test_full_call_count_with_findings_for_every_allocation():
    entries = [_make_entry(i) for i in range(1, 4)]  # 3 allocations
    context = _make_context(entries)
    # Per allocation: search (findings) + extraction = 2 calls. Shortlist-level: search (findings) + extraction = 2 calls.
    script = []
    for _ in entries:
        script.append("Found something relevant.")
        script.append(_extraction_json([_GOOD_ITEM]))
    script.append("Found shortlist-level context.")
    script.append(_extraction_json([_COUNCIL_ITEM]))
    client = FakeClient(script)

    result = build_allocation_web_research_context(client, context)

    assert len(client.responses.calls) == len(entries) * 2 + 2
    assert result.searches_attempted == len(entries) + 1
    assert result.searches_succeeded == len(entries) + 1


# --- Evidence association / retention / dedup ---------------------------------


def test_evidence_correctly_associated_with_allocation():
    entries = [_make_entry(1), _make_entry(2)]
    context = _make_context(entries)
    script = [
        "findings for 1", _extraction_json([_GOOD_ITEM]),
        None,  # allocation 2: no findings
        None,  # shortlist-level: no findings
    ]
    client = FakeClient(script)

    result = build_allocation_web_research_context(client, context)

    assert 1 in result.evidence_by_allocation
    assert 2 not in result.evidence_by_allocation
    assert result.evidence_by_allocation[1][0].allocation_id == 1
    assert result.evidence_by_allocation[1][0].allocation_name == entries[0].allocation_name


def test_max_sources_retained_per_allocation_is_enforced():
    entries = [_make_entry(1)]
    context = _make_context(entries)
    many_items = [dict(_GOOD_ITEM, url=f"https://www.placenorthwest.co.uk/story-{i}") for i in range(10)]
    script = ["findings", _extraction_json(many_items), None]  # shortlist-level: no findings
    client = FakeClient(script)

    result = build_allocation_web_research_context(client, context)

    assert len(result.evidence_by_allocation[1]) == MAX_SOURCES_RETAINED_PER_ALLOCATION


def test_deduplicates_identical_url_across_allocations():
    entries = [_make_entry(1), _make_entry(2)]
    context = _make_context(entries)
    same_item = dict(_GOOD_ITEM)
    script = [
        "findings 1", _extraction_json([same_item]),
        "findings 2", _extraction_json([same_item]),  # same URL again
        None,
    ]
    client = FakeClient(script)

    result = build_allocation_web_research_context(client, context)

    urls = [item.url for item in result.all_evidence()]
    assert urls.count(same_item["url"]) == 1


def test_evidence_ids_are_stable_and_sequential():
    entries = [_make_entry(1), _make_entry(2)]
    context = _make_context(entries)
    script = [
        "findings 1", _extraction_json([_GOOD_ITEM]),
        "findings 2", _extraction_json([dict(_GOOD_ITEM, url="https://www.placenorthwest.co.uk/story-2")]),
        "shortlist findings", _extraction_json([_COUNCIL_ITEM]),
    ]
    client = FakeClient(script)

    result = build_allocation_web_research_context(client, context)

    ids = [item.evidence_id for item in result.all_evidence()]
    assert ids == ["W1", "W2", "W3"]
    assert result.evidence_by_id()["W1"].url == _GOOD_ITEM["url"]


def test_items_missing_url_or_title_are_dropped():
    entries = [_make_entry(1)]
    context = _make_context(entries)
    bad_item = dict(_GOOD_ITEM, url="")
    script = ["findings", _extraction_json([bad_item]), None]
    client = FakeClient(script)

    result = build_allocation_web_research_context(client, context)

    assert 1 not in result.evidence_by_allocation


# --- Publication-date handling (Section 10) -----------------------------------


def test_dated_and_undated_evidence_both_retained():
    entries = [_make_entry(1)]
    context = _make_context(entries)
    script = ["findings", _extraction_json([_GOOD_ITEM, dict(_COUNCIL_ITEM, url="https://www.testcouncil.gov.uk/undated")]), None]
    client = FakeClient(script)

    result = build_allocation_web_research_context(client, context)

    dates = {item.published_date for item in result.evidence_by_allocation[1]}
    assert "2026-01-15" in dates
    assert None in dates  # undated retained, never crashes, never fabricated


# --- No-result / failure semantics (Section 11/32) -----------------------------


def test_no_useful_findings_is_a_valid_non_fatal_state():
    entries = [_make_entry(1)]
    context = _make_context(entries)
    script = [None, None]  # allocation search returns no findings, shortlist-level too
    client = FakeClient(script)

    result = build_allocation_web_research_context(client, context)

    assert result.evidence_by_allocation == {}
    assert result.failures == []
    assert result.searches_succeeded == 2  # the call succeeded; it simply found nothing


def test_search_api_failure_is_recorded_and_does_not_stop_other_allocations():
    entries = [_make_entry(1), _make_entry(2)]
    context = _make_context(entries)
    script = [
        RuntimeError("API timeout"),  # allocation 1 search fails
        "findings 2", _extraction_json([_GOOD_ITEM]),  # allocation 2 succeeds
        None,  # shortlist-level: no findings
    ]
    client = FakeClient(script)

    result = build_allocation_web_research_context(client, context)

    assert len(result.failures) == 1
    assert "allocation 1" in result.failures[0]
    assert 2 in result.evidence_by_allocation  # allocation 2 still processed despite allocation 1's failure


def test_extraction_failure_is_recorded_and_does_not_raise():
    entries = [_make_entry(1)]
    context = _make_context(entries)
    script = ["findings", RuntimeError("bad JSON"), None]
    client = FakeClient(script)

    result = build_allocation_web_research_context(client, context)

    assert result.failures
    assert 1 not in result.evidence_by_allocation


def test_web_research_never_raises_even_on_total_failure():
    entries = [_make_entry(i) for i in range(1, 4)]
    context = _make_context(entries)
    script = [RuntimeError("down")] * (len(entries) + 1)
    client = FakeClient(script)

    result = build_allocation_web_research_context(client, context)  # must not raise

    assert result.evidence_by_allocation == {}
    assert result.shortlist_level_evidence == []
    assert len(result.failures) == len(entries) + 1
