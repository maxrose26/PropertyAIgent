"""Tests for the Gate 4 extension to app.reporting.allocation_report_pdf -
optional executive_intelligence/web_evidence composition on top of the
Gate 3 deterministic renderer (Section 34).

Pure-Python fixtures (no database session needed - AllocationReportContext,
CrossSiteIntelligence, and AllocationWebResearchContext are all plain
dataclass trees), matching tests/test_cross_site_intelligence.py's and
tests/test_allocation_web_research.py's own convention."""
from __future__ import annotations

import datetime as dt
import io

import pdfplumber

from app.reporting.allocation_report import (
    AllocationIntelligenceSnapshot,
    AllocationReportAggregates,
    AllocationReportContext,
    AllocationReportEntry,
)
from app.reporting.allocation_report_pdf import (
    NO_WEB_EVIDENCE_TEXT,
    WEB_EVIDENCE_NOTE,
    allocation_report_pdf_filename,
    render_allocation_report_pdf,
)
from app.reporting.allocation_web_research import AllocationWebResearchContext, WebEvidenceItem
from app.reporting.cross_site_intelligence import CrossSiteIntelligence


def _make_entry(allocation_id=1, allocation_name="Land off Test Road") -> AllocationReportEntry:
    return AllocationReportEntry(
        allocation_id=allocation_id, allocation_name=allocation_name, allocation_reference="REF-1",
        council_code="testcouncil", council_name="Testcouncil", local_plan_name="Test Local Plan",
        plan_status="adopted", plan_status_label="Adopted", plan_status_bucket="adopted",
        intended_use="residential", intended_use_label="Residential",
        capacity_value=100, capacity_kind="minimum", capacity_display="Approximately 100 homes",
        identified_application_capacity=0, indicative_residual_capacity=100,
        development_coverage_percentage=0.0, development_coverage_classification="NO_IDENTIFIED_ACTIVITY",
        capacity_accounting_status="no_activity", linked_application_count=0, linked_applications=[],
        applicant_evidence=[], ownership_evidence=[], ai_intelligence=AllocationIntelligenceSnapshot(available=False),
    )


def _make_context(entries: list[AllocationReportEntry] | None = None) -> AllocationReportContext:
    entries = entries if entries is not None else [_make_entry()]
    agg = AllocationReportAggregates(
        allocation_count=len(entries), exact_capacity_total=sum(e.capacity_value or 0 for e in entries),
        exact_capacity_count=len(entries), ranged_capacity_count=0, unknown_capacity_count=0,
        identified_application_capacity_known_total=0, identified_application_capacity_unknown_count=0,
        indicative_residual_capacity_known_total=sum(e.indicative_residual_capacity or 0 for e in entries),
        indicative_residual_capacity_unknown_count=0, adopted_count=len(entries), emerging_count=0,
        other_plan_status_count=0, allocations_with_linked_activity=0, allocations_with_no_identified_activity=len(entries),
    )
    return AllocationReportContext(entries=entries, excluded=[], aggregates=agg, generated_at=dt.datetime.now(dt.timezone.utc))


def _make_intelligence(**overrides) -> CrossSiteIntelligence:
    base = dict(
        executive_summary="This shortlist has 1 allocation with no identified activity [W1].",
        priority_opportunities=["Land off Test Road warrants further investigation."],
        cross_site_observations=["No cross-site pattern identified yet."],
        recent_external_developments=["Recent coverage was found [W1]."],
        key_uncertainties=["Developer intent is unclear."],
        investigation_priorities=["Confirm site control."],
        generated_at=dt.datetime.now(dt.timezone.utc), model="gpt-4o-mini", prompt_version="cross-site-intelligence-v1",
    )
    base.update(overrides)
    return CrossSiteIntelligence(**base)


def _make_web_evidence() -> AllocationWebResearchContext:
    return AllocationWebResearchContext(
        shortlist_level_evidence=[WebEvidenceItem(
            evidence_id="W1", allocation_id=None, allocation_name=None, title="Council update on housing sites",
            publisher="Testcouncil Council", url="https://www.testcouncil.gov.uk/news/1", published_date="2026-02-01",
            retrieved_at=dt.datetime.now(dt.timezone.utc), evidence_type="council_publication",
            summary="The council published an update.", source_tier="official_primary", confidence="high",
            query="test", relevance_reason="relevant",
        )],
        research_timestamp=dt.datetime.now(dt.timezone.utc),
    )


def _pdf_text(pdf_bytes: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


# --- Deterministic fallback (Section 34) ---------------------------------------


def test_deterministic_pdf_remains_available_without_ai():
    context = _make_context()

    pdf_bytes = render_allocation_report_pdf(context)  # no executive_intelligence/web_evidence at all

    assert pdf_bytes.startswith(b"%PDF-")
    text = _pdf_text(pdf_bytes)
    assert "Executive Intelligence" not in text
    assert "External Web Sources" not in text


def test_filename_unaffected_when_ai_enhanced_not_requested():
    context = _make_context()
    assert allocation_report_pdf_filename(context) == allocation_report_pdf_filename(context, ai_enhanced=False)
    # "property-aigent" itself legitimately contains "ai" (the product's own
    # name) - check for the specific ai-enhanced suffix, not the bare substring.
    assert "-ai-intelligence-" not in allocation_report_pdf_filename(context)


def test_ai_enhanced_filename_is_distinguished():
    context = _make_context()
    assert allocation_report_pdf_filename(context, ai_enhanced=True) != allocation_report_pdf_filename(context)


# --- Executive Intelligence section (Section 25) --------------------------------


def test_executive_intelligence_section_renders_when_provided():
    context = _make_context()
    intelligence = _make_intelligence()
    web_evidence = _make_web_evidence()

    pdf_bytes = render_allocation_report_pdf(context, executive_intelligence=intelligence, web_evidence=web_evidence)
    text = _pdf_text(pdf_bytes)

    assert "Executive Intelligence" in text
    assert "Priority Opportunities" in text
    assert "Recent External Developments" in text
    assert "Key Cross-Site Observations" in text
    assert "Key Uncertainties" in text
    assert "Investigation Priorities" in text
    assert intelligence.executive_summary.replace("[W1]", "[W1]") in text or "This shortlist has 1 allocation" in text
    # Concise evidence note (Section 27) is present.
    assert "verified against primary sources" in text


def test_executive_intelligence_appears_before_deterministic_sections():
    context = _make_context()
    intelligence = _make_intelligence()
    web_evidence = _make_web_evidence()

    text = _pdf_text(render_allocation_report_pdf(context, executive_intelligence=intelligence, web_evidence=web_evidence))

    assert text.index("Executive Intelligence") < text.index("1. Shortlist Overview")


def test_citation_markers_appear_in_executive_intelligence():
    context = _make_context()
    intelligence = _make_intelligence()
    web_evidence = _make_web_evidence()

    text = _pdf_text(render_allocation_report_pdf(context, executive_intelligence=intelligence, web_evidence=web_evidence))

    assert "[W1]" in text


# --- External Web Sources section (Section 26) ----------------------------------


def test_external_web_sources_section_renders_when_provided():
    context = _make_context()
    intelligence = _make_intelligence()
    web_evidence = _make_web_evidence()

    text = _pdf_text(render_allocation_report_pdf(context, executive_intelligence=intelligence, web_evidence=web_evidence))

    assert "External Web Sources" in text
    assert "EXTERNAL WEB RESEARCH" in text
    assert "Testcouncil Council" in text
    assert "Council update on housing sites" in text
    assert "testcouncil.gov.uk" in text


def test_external_web_sources_appears_after_deterministic_sections():
    context = _make_context()
    intelligence = _make_intelligence()
    web_evidence = _make_web_evidence()

    text = _pdf_text(render_allocation_report_pdf(context, executive_intelligence=intelligence, web_evidence=web_evidence))

    # The Executive Intelligence section's own closing note (by design)
    # forward-references "the External Web Sources section" by name, so a
    # bare text.index("External Web Sources") would match that mention
    # instead of the real section heading - search for the section's own
    # unique sub-heading text instead, which appears only once, in the real
    # section.
    assert text.index("3. Allocation Details") < text.index("EXTERNAL WEB RESEARCH -")


def test_no_web_evidence_neutral_text_when_research_found_nothing():
    context = _make_context()
    intelligence = _make_intelligence(recent_external_developments=[])
    empty_web_evidence = AllocationWebResearchContext(research_timestamp=dt.datetime.now(dt.timezone.utc))

    text = _pdf_text(render_allocation_report_pdf(context, executive_intelligence=intelligence, web_evidence=empty_web_evidence))

    assert NO_WEB_EVIDENCE_TEXT in text


def test_web_evidence_none_falls_back_to_neutral_text_when_intelligence_present():
    """Section 11 - AI generation can succeed even when web research itself
    found nothing (web_evidence=None is a valid caller state, e.g. research
    was skipped/failed entirely) - the External Web Sources section must
    still render its own honest "nothing found" state, never crash on a
    None."""
    context = _make_context()
    intelligence = _make_intelligence(recent_external_developments=[])

    pdf_bytes = render_allocation_report_pdf(context, executive_intelligence=intelligence, web_evidence=None)

    assert pdf_bytes.startswith(b"%PDF-")
    text = _pdf_text(pdf_bytes)
    assert NO_WEB_EVIDENCE_TEXT in text


# --- Robustness -------------------------------------------------------------------


def test_ampersand_in_web_source_does_not_break_rendering():
    context = _make_context()
    intelligence = _make_intelligence()
    web_evidence = AllocationWebResearchContext(
        shortlist_level_evidence=[WebEvidenceItem(
            evidence_id="W1", allocation_id=None, allocation_name=None, title="Smith & Sons announce plans",
            publisher="Local & Regional Press", url="https://example.com/a?x=1&y=2", published_date="2026-01-01",
            retrieved_at=dt.datetime.now(dt.timezone.utc), evidence_type="news_coverage", summary="summary",
            source_tier="strong_secondary", confidence="medium", query="test", relevance_reason="relevant",
        )],
        research_timestamp=dt.datetime.now(dt.timezone.utc),
    )

    pdf_bytes = render_allocation_report_pdf(context, executive_intelligence=intelligence, web_evidence=web_evidence)

    assert pdf_bytes.startswith(b"%PDF-")
    text = _pdf_text(pdf_bytes)
    assert "Smith & Sons" in text
