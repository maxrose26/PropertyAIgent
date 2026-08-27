"""Tests for Site Selection & Reporting V1 Gate 4 - app.reporting.
cross_site_intelligence's report-level AI synthesis + dedicated grounding
validator.

Pure-Python fixtures + a scripted fake OpenAI client double, never a real
network/API call (Section 32/33 - "NO real web calls in automated tests")."""
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
from app.reporting.allocation_web_research import AllocationWebResearchContext, WebEvidenceItem
from app.reporting.cross_site_intelligence import (
    CROSS_SITE_SCHEMA,
    generate_cross_site_intelligence,
    validate_cross_site_output,
)

# --- Fixtures (mirrors tests/test_allocation_web_research.py's own helpers) --


def _make_entry(allocation_id: int, *, allocation_name="Land off Test Road", council_name="Testcouncil",
                 capacity_kind="minimum", capacity_value: int | None = 100, capacity_display="Approximately 100 homes",
                 trusted_developer: str | None = None, applicant: str | None = None,
                 linked_application_count: int = 0, identified_application_capacity: int | None = 0) -> AllocationReportEntry:
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
        capacity_value=capacity_value, capacity_kind=capacity_kind, capacity_display=capacity_display,
        identified_application_capacity=identified_application_capacity, indicative_residual_capacity=capacity_value,
        development_coverage_percentage=0.0, development_coverage_classification="NO_IDENTIFIED_ACTIVITY",
        capacity_accounting_status="no_activity",
        linked_application_count=linked_application_count, linked_applications=[],
        applicant_evidence=applicant_evidence, ownership_evidence=ownership_evidence,
        ai_intelligence=AllocationIntelligenceSnapshot(available=False),
    )


def _make_context(entries: list[AllocationReportEntry]) -> AllocationReportContext:
    exact_entries = [e for e in entries if e.capacity_kind in ("minimum", "maximum", "indicative")]
    ranged_entries = [e for e in entries if e.capacity_kind == "range"]
    unknown_entries = [e for e in entries if e.capacity_kind == "unknown"]
    agg = AllocationReportAggregates(
        allocation_count=len(entries),
        exact_capacity_total=sum(e.capacity_value or 0 for e in exact_entries), exact_capacity_count=len(exact_entries),
        ranged_capacity_count=len(ranged_entries), unknown_capacity_count=len(unknown_entries),
        identified_application_capacity_known_total=sum(e.identified_application_capacity or 0 for e in entries if e.identified_application_capacity is not None),
        identified_application_capacity_unknown_count=sum(1 for e in entries if e.identified_application_capacity is None),
        indicative_residual_capacity_known_total=sum(e.indicative_residual_capacity or 0 for e in entries if e.indicative_residual_capacity),
        indicative_residual_capacity_unknown_count=sum(1 for e in entries if e.indicative_residual_capacity is None),
        adopted_count=len(entries), emerging_count=0, other_plan_status_count=0,
        allocations_with_linked_activity=sum(1 for e in entries if e.linked_application_count),
        allocations_with_no_identified_activity=sum(1 for e in entries if not e.linked_application_count),
    )
    return AllocationReportContext(entries=entries, excluded=[], aggregates=agg, generated_at=dt.datetime.now(dt.timezone.utc))


def _make_web_context(items_by_allocation: dict[int | None, list[WebEvidenceItem]] | None = None) -> AllocationWebResearchContext:
    items_by_allocation = items_by_allocation or {}
    result = AllocationWebResearchContext(research_timestamp=dt.datetime.now(dt.timezone.utc))
    n = 0
    for allocation_id, items in items_by_allocation.items():
        renumbered = []
        for item in items:
            n += 1
            renumbered.append(WebEvidenceItem(
                evidence_id=f"W{n}", allocation_id=allocation_id, allocation_name=item.allocation_name,
                title=item.title, publisher=item.publisher, url=item.url, published_date=item.published_date,
                retrieved_at=item.retrieved_at, evidence_type=item.evidence_type, summary=item.summary,
                source_tier=item.source_tier, confidence=item.confidence, query=item.query,
                relevance_reason=item.relevance_reason,
            ))
        if allocation_id is None:
            result.shortlist_level_evidence.extend(renumbered)
        else:
            result.evidence_by_allocation[allocation_id] = renumbered
    return result


def _evidence(allocation_name=None, title="Some Article", summary="Something happened.", published_date="2026-01-01") -> WebEvidenceItem:
    return WebEvidenceItem(
        evidence_id="Wx", allocation_id=None, allocation_name=allocation_name, title=title, publisher="Test Press",
        url="https://example.com/x", published_date=published_date, retrieved_at=dt.datetime.now(dt.timezone.utc),
        evidence_type="news_coverage", summary=summary, source_tier="strong_secondary", confidence="high",
        query="test", relevance_reason="relevant",
    )


def _good_output(**overrides) -> dict:
    base = {
        "executive_summary": "The shortlist spans 1 adopted allocation with no identified planning activity.",
        "priority_opportunities": ["Land off Test Road warrants further investigation given its residual capacity."],
        "cross_site_observations": ["Land off Test Road has no identified planning activity."],
        "recent_external_developments": [],
        "key_uncertainties": ["No public developer activity has been identified for Land off Test Road."],
        "investigation_priorities": ["Confirm site control for Land off Test Road."],
    }
    base.update(overrides)
    return base


class FakeResponse:
    def __init__(self, output_text: str):
        self.output_text = output_text


class FakeResponses:
    def __init__(self, output_text: str | Exception):
        self.output_text = output_text
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.output_text, Exception):
            raise self.output_text
        return FakeResponse(self.output_text)


class FakeClient:
    def __init__(self, output_text: str | Exception):
        self.responses = FakeResponses(output_text)


# --- Synthesis-call architecture (Section 33 A/B) -----------------------------


def test_exactly_one_synthesis_call_per_report():
    entries = [_make_entry(1)]
    context = _make_context(entries)
    web_context = _make_web_context()
    client = FakeClient(json.dumps(_good_output()))

    generate_cross_site_intelligence(client, context, web_context)

    assert len(client.responses.calls) == 1


def test_no_per_allocation_generation_calls_regardless_of_shortlist_size():
    entries = [_make_entry(i) for i in range(1, 8)]  # 7 allocations
    context = _make_context(entries)
    web_context = _make_web_context()
    client = FakeClient(json.dumps(_good_output()))

    generate_cross_site_intelligence(client, context, web_context)

    assert len(client.responses.calls) == 1  # flat, never one call per allocation


# --- Grounding context correctness (Section 33 C/D) ---------------------------


def test_prompt_includes_deterministic_context_facts():
    from app.reporting.cross_site_intelligence import build_cross_site_prompt

    entries = [_make_entry(1, allocation_name="Land off Elm Road", trusted_developer="Acme Developments Ltd")]
    context = _make_context(entries)
    web_context = _make_web_context({None: [_evidence(title="Acme scheme update")]})

    prompt = build_cross_site_prompt(context, web_context)

    assert "Land off Elm Road" in prompt
    assert "Acme Developments Ltd" in prompt
    assert "[W1]" in prompt


# --- Citation validation (Section 33 E) ----------------------------------------


def test_valid_citation_is_accepted():
    entries = [_make_entry(1)]
    context = _make_context(entries)
    web_context = _make_web_context({None: [_evidence()]})
    output = _good_output(recent_external_developments=["A recent update was reported [W1]."])

    is_valid, problems = validate_cross_site_output(context, web_context, output)

    assert is_valid, problems


def test_invented_citation_id_is_rejected():
    entries = [_make_entry(1)]
    context = _make_context(entries)
    web_context = _make_web_context()  # no evidence at all - W7 cannot exist
    output = _good_output(recent_external_developments=["A recent update was reported [W7]."])

    is_valid, problems = validate_cross_site_output(context, web_context, output)

    assert not is_valid
    assert any("W7" in p for p in problems)


# --- Wrong-allocation attribution (Section 33 F) -------------------------------


def test_wrong_allocation_evidence_attribution_is_rejected():
    e1 = _make_entry(1, allocation_name="Land off Elm Road")
    e2 = _make_entry(2, allocation_name="Land off Oak Road")
    context = _make_context([e1, e2])
    web_context = _make_web_context({1: [_evidence(allocation_name="Land off Elm Road")]})  # W1 belongs to allocation 1
    output = _good_output(cross_site_observations=["Land off Oak Road has seen recent developer activity [W1]."])  # cited for allocation 2

    is_valid, problems = validate_cross_site_output(context, web_context, output)

    assert not is_valid
    assert any("different allocation" in p for p in problems)


def test_correct_allocation_evidence_attribution_is_accepted():
    e1 = _make_entry(1, allocation_name="Land off Elm Road")
    context = _make_context([e1])
    web_context = _make_web_context({1: [_evidence(allocation_name="Land off Elm Road")]})
    output = _good_output(cross_site_observations=["Land off Elm Road has seen recent developer activity [W1]."])

    is_valid, problems = validate_cross_site_output(context, web_context, output)

    assert is_valid, problems


# --- Party role semantics (Section 33 G/H/I) -----------------------------------


def test_applicant_promoted_to_developer_is_rejected():
    entries = [_make_entry(1, applicant="Acme Applicant Ltd")]
    context = _make_context(entries)
    web_context = _make_web_context()
    output = _good_output(key_uncertainties=["Developer: Acme Applicant Ltd is progressing the scheme."])

    is_valid, problems = validate_cross_site_output(context, web_context, output)

    assert not is_valid
    assert any("Acme Applicant Ltd" in p for p in problems)


def test_trusted_developer_claim_is_accepted():
    entries = [_make_entry(1, trusted_developer="Trusted Developer Ltd")]
    context = _make_context(entries)
    web_context = _make_web_context()
    output = _good_output(cross_site_observations=["Developer: Trusted Developer Ltd is the trusted Developer for this allocation."])

    is_valid, problems = validate_cross_site_output(context, web_context, output)

    assert is_valid, problems


def test_web_public_association_wording_allowed_without_trusted_role_conversion():
    entries = [_make_entry(1)]
    context = _make_context(entries)
    web_context = _make_web_context({None: [_evidence()]})
    # GOOD shape (Section 13) - never "Developer: X", always attributed to the public statement + citation.
    output = _good_output(recent_external_developments=["Acme Homes publicly states it is progressing the site [W1]."])

    is_valid, problems = validate_cross_site_output(context, web_context, output)

    assert is_valid, problems


# --- Capacity semantics (Section 33 J/K) ---------------------------------------


def test_range_capacity_not_blended_into_a_fabricated_total():
    e1 = _make_entry(1, capacity_kind="minimum", capacity_value=100, capacity_display="Approximately 100 homes")
    e2 = _make_entry(2, capacity_kind="range", capacity_value=15000, capacity_display="8,400-15,000 homes")
    context = _make_context([e1, e2])
    web_context = _make_web_context()
    # A genuinely invented figure - not exact_capacity_total (100, since the
    # range entry is correctly excluded from it), not either entry's own
    # capacity_value/capacity_display (100, 8400, 15000), not any aggregate
    # this fixture's own _make_context computes (residual total legitimately
    # is 100+15000=15100 - see indicative_residual_capacity's own, different,
    # genuinely-additive semantics - so 15,100 itself is NOT a safe negative
    # test case here; 15,105 has no legitimate source at all).
    output = _good_output(executive_summary="This shortlist totals 15,105 homes.")

    is_valid, problems = validate_cross_site_output(context, web_context, output)

    assert not is_valid
    assert any("15105" in p for p in problems)


def test_unknown_capacity_not_converted_to_a_fabricated_figure():
    """Section 33K's own principle ("unknown capacity not converted to
    zero") generalises here to "not converted to ANY fabricated figure" -
    a bare "0" specifically has several OTHER legitimate, grounded sources
    in a normal entry (development_coverage_percentage=0.0,
    linked_application_count=0, all genuinely meaningful "no activity"
    facts, not capacity claims) that a purely numeric allow-list cannot
    disambiguate from a fabricated zero CAPACITY claim - a known, accepted
    limitation of numeric-only grounding, same class as validate_summary_
    output's own documented "mitigation, not structural guarantee" cases.
    A clearly non-zero fabricated figure has no such collision and proves
    the same underlying principle robustly."""
    entry = _make_entry(1, capacity_kind="unknown", capacity_value=None, capacity_display="Capacity not identified")
    context = _make_context([entry])
    web_context = _make_web_context()
    output = _good_output(cross_site_observations=["Land off Test Road has 1,234 homes of capacity."])

    is_valid, problems = validate_cross_site_output(context, web_context, output)

    assert not is_valid
    assert any("1234" in p for p in problems)


def test_genuinely_known_zero_is_accepted():
    entry = _make_entry(1, linked_application_count=0)  # identified_application_capacity=0, genuinely known
    context = _make_context([entry])
    web_context = _make_web_context()
    output = _good_output(cross_site_observations=["Land off Test Road has 0 identified application capacity."])

    is_valid, problems = validate_cross_site_output(context, web_context, output)

    assert is_valid, problems


# --- No-linked-Application neutrality (Section 33 L) ---------------------------


def test_prompt_states_no_linked_application_neutrally():
    from app.reporting.cross_site_intelligence import _render_allocation_line

    entry = _make_entry(1, linked_application_count=0)
    line = _render_allocation_line(entry)

    assert "none identified" in line
    assert "error" not in line.lower() and "warning" not in line.lower()


# --- Forbidden scoring / probability shapes (Section 33 M/N) -------------------


def test_numeric_score_shape_is_rejected():
    entries = [_make_entry(1)]
    context = _make_context(entries)
    web_context = _make_web_context()
    output = _good_output(executive_summary="Land off Test Road scores 82/100 for opportunity.")

    is_valid, problems = validate_cross_site_output(context, web_context, output)

    assert not is_valid
    assert any("forbidden score" in p for p in problems)


def test_probability_of_consent_claim_is_rejected():
    entries = [_make_entry(1)]
    context = _make_context(entries)
    web_context = _make_web_context()
    output = _good_output(executive_summary="This allocation has a 78% probability of consent.")

    is_valid, problems = validate_cross_site_output(context, web_context, output)

    assert not is_valid
    assert any("forbidden score" in p for p in problems)


def test_housing_delivery_score_shape_is_rejected():
    entries = [_make_entry(1)]
    context = _make_context(entries)
    web_context = _make_web_context()
    output = _good_output(executive_summary="This council has a housing delivery score of 65/100.")

    is_valid, problems = validate_cross_site_output(context, web_context, output)

    assert not is_valid
    assert any("forbidden score" in p for p in problems)


# --- Schema shape ---------------------------------------------------------------


def test_schema_has_no_numeric_field():
    def _walk(node):
        if isinstance(node, dict):
            if node.get("type") == "number" or node.get("type") == "integer":
                raise AssertionError(f"schema unexpectedly contains a numeric field: {node}")
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(CROSS_SITE_SCHEMA["schema"])


# --- Generation orchestration / failure behaviour -------------------------------


def test_generation_success_returns_intelligence():
    entries = [_make_entry(1)]
    context = _make_context(entries)
    web_context = _make_web_context()
    client = FakeClient(json.dumps(_good_output()))

    result = generate_cross_site_intelligence(client, context, web_context)

    assert result.status == "ok"
    assert result.intelligence is not None
    assert result.intelligence.executive_summary


def test_generation_api_failure_returns_error_status_never_raises():
    entries = [_make_entry(1)]
    context = _make_context(entries)
    web_context = _make_web_context()
    client = FakeClient(RuntimeError("API down"))

    result = generate_cross_site_intelligence(client, context, web_context)  # must not raise

    assert result.status == "error"
    assert result.intelligence is None


def test_generation_validation_rejection_returns_rejected_status_never_raises():
    entries = [_make_entry(1)]
    context = _make_context(entries)
    web_context = _make_web_context()
    bad_output = _good_output(executive_summary="Scores 99/100 for opportunity.")
    client = FakeClient(json.dumps(bad_output))

    result = generate_cross_site_intelligence(client, context, web_context)

    assert result.status == "rejected"
    assert result.intelligence is None
    assert result.rejection_reason
