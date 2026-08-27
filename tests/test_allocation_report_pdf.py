"""Tests for Site Selection & Reporting V1 Gate 3 - app.reporting.
allocation_report_pdf's deterministic PDF renderer.

Same integration-style-fixture convention as tests/test_allocation_report.py
(this module deliberately duplicates the small set of fixture helpers it
needs rather than cross-importing another test module - no precedent for
that in this test suite, and each test file already stays self-contained).

Text-content assertions read the rendered PDF back with pdfplumber (already
an existing project dependency - app/extraction/*.py - never a new PDF
library added purely for testing).
"""
from __future__ import annotations

import ast
import io
from inspect import getsource as inspect_getsource

import pdfplumber
import pytest
from sqlalchemy import event

from app.db.models import (
    AllocationIntelligenceSummary,
    AllocationSiteRelationship,
    Application,
    ControlRelationship,
    LocalPlan,
    LocalPlanSite,
    Site,
)
from app.reporting.allocation_report import build_allocation_report_context
from app.reporting.allocation_report_pdf import (
    AI_INTELLIGENCE_UNAVAILABLE_TEXT,
    NO_LINKED_APPLICATION_TEXT,
    allocation_report_pdf_filename,
    render_allocation_report_pdf,
)

# --- Fixtures (mirrors tests/test_allocation_report.py's own helpers) --------


def _make_local_plan(session, council_code="testcouncil", status="adopted", plan_name="Test Local Plan") -> LocalPlan:
    plan = LocalPlan(council_code=council_code, plan_name=plan_name, status=status, raw_status=status)
    session.add(plan)
    session.commit()
    return plan


def _make_allocation(session, local_plan_id, *, council_code="testcouncil", policy_reference="HOM 1.1",
                      site_name="Land off Test Road", **kwargs) -> LocalPlanSite:
    allocation = LocalPlanSite(
        council_code=council_code, local_plan_id=local_plan_id, policy_reference=policy_reference, site_name=site_name,
        plan_name="Test Local Plan", plan_status="adopted", **kwargs,
    )
    session.add(allocation)
    session.commit()
    return allocation


def _make_site(session, *, address="1 Test Street", council_code="testcouncil") -> Site:
    site = Site(council_code=council_code, canonical_address=address.lower(), display_address=address)
    session.add(site)
    session.commit()
    return site


def _make_relationship(session, allocation_id, site_id, *, review_status="auto_applied") -> AllocationSiteRelationship:
    rel = AllocationSiteRelationship(
        allocation_id=allocation_id, site_id=site_id, relationship_type="matched_site",
        evidence_basis="document_confirmed_site", review_status=review_status,
    )
    session.add(rel)
    session.commit()
    return rel


def _make_app(session, site_id, reference="APP/1", *, council_code="testcouncil", **kwargs) -> Application:
    app = Application(council_code=council_code, reference=reference, site_id=site_id, **kwargs)
    session.add(app)
    session.commit()
    return app


def _make_control(session, *, site_id, entity_name_raw, role, evidence_category, evidence_basis="s106_defined_role",
                   review_status="auto_applied", application_id=None) -> ControlRelationship:
    row = ControlRelationship(
        site_id=site_id, application_id=application_id, entity_name_raw=entity_name_raw, role=role,
        evidence_category=evidence_category, evidence_basis=evidence_basis, extraction_method="ai_extraction",
        review_status=review_status,
    )
    session.add(row)
    session.commit()
    return row


def _make_summary(session, allocation_id, *, headline="Test headline.", overview="Test overview.", status="ok", **kwargs) -> AllocationIntelligenceSummary:
    row = AllocationIntelligenceSummary(
        allocation_id=allocation_id, headline=headline, overview=overview, status=status, **kwargs,
    )
    session.add(row)
    session.commit()
    return row


def _pdf_text(pdf_bytes: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def _build_shortlist_of(session, n: int, *, prefix: str = "") -> list[int]:
    plan = _make_local_plan(session, plan_name=f"Batch Plan {prefix}")
    ids = []
    for i in range(n):
        allocation = _make_allocation(session, plan.id, policy_reference=f"{prefix}REF-{i}", minimum_dwellings=100)
        ids.append(allocation.id)
        site = _make_site(session, address=f"{prefix}{i} Batch Street")
        _make_relationship(session, allocation.id, site.id)
        _make_app(session, site.id, reference=f"{prefix}APP-{i}", applicant_name_raw=f"Applicant {i}")
        _make_control(session, site_id=site.id, entity_name_raw=f"Developer {i}", role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")
        _make_summary(session, allocation.id, headline=f"Headline {i}")
    return ids


def _count_select_queries(session, fn) -> int:
    statements = []

    def _listener(conn, cursor, statement, parameters, context, executemany):
        if statement.strip().upper().startswith("SELECT"):
            statements.append(statement)

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", _listener)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _listener)
    return len(statements)


# --- PDF validity ---------------------------------------------------------------


def test_output_is_valid_pdf_bytes(session):
    plan = _make_local_plan(session)
    _make_allocation(session, plan.id, site_name="Land off Valid Road", minimum_dwellings=150)
    context = build_allocation_report_context(session, [row.id for row in session.query(LocalPlanSite).all()])

    pdf_bytes = render_allocation_report_pdf(context)

    assert pdf_bytes.startswith(b"%PDF-")
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        assert len(pdf.pages) >= 1


def test_report_title_and_allocation_name_present(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, site_name="Land off Reservoir Lane", minimum_dwellings=200)
    context = build_allocation_report_context(session, [allocation.id])

    text = _pdf_text(render_allocation_report_pdf(context))

    assert "Allocation Opportunity Report" in text
    assert "PropertyAIgent" in text
    assert "Land off Reservoir Lane" in text


def test_summary_table_text_present(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, site_name="Land off Table Street", minimum_dwellings=75)
    context = build_allocation_report_context(session, [allocation.id])

    text = _pdf_text(render_allocation_report_pdf(context))

    assert "Shortlist Summary" in text
    assert "Land off Table Street" in text


def test_multi_allocation_generation_succeeds(session):
    ids = _build_shortlist_of(session, 8)
    context = build_allocation_report_context(session, ids)

    pdf_bytes = render_allocation_report_pdf(context)

    assert pdf_bytes.startswith(b"%PDF-")
    text = _pdf_text(pdf_bytes)
    assert "Batch Plan" in text or "REF-0" in text or "Applicant 0" in text


def test_long_text_does_not_crash(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, site_name="Land with a very long name " * 10, minimum_dwellings=100)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id)
    _make_app(
        session, site.id, reference="APP/LONG",
        proposal="Erection of dwellings. " * 60,
    )
    context = build_allocation_report_context(session, [allocation.id])

    pdf_bytes = render_allocation_report_pdf(context)

    assert pdf_bytes.startswith(b"%PDF-")


def test_empty_optional_fields_do_not_crash(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)  # no capacity, no site relationship, no summary
    context = build_allocation_report_context(session, [allocation.id])

    pdf_bytes = render_allocation_report_pdf(context)

    assert pdf_bytes.startswith(b"%PDF-")


def test_ampersand_in_entity_name_does_not_break_rendering(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=100)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id)
    _make_control(session, site_id=site.id, entity_name_raw="Smith & Sons <Holdings> Ltd", role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")
    context = build_allocation_report_context(session, [allocation.id])

    text = _pdf_text(render_allocation_report_pdf(context))

    assert "Smith & Sons" in text


# --- Capacity semantics -----------------------------------------------------


def test_exact_capacity_rendered_and_not_summed_with_ranges(session):
    plan = _make_local_plan(session)
    exact = _make_allocation(session, plan.id, policy_reference="E1", minimum_dwellings=100)
    ranged = _make_allocation(session, plan.id, policy_reference="E2", minimum_dwellings=8400, maximum_capacity=15000)
    context = build_allocation_report_context(session, [exact.id, ranged.id])

    text = _pdf_text(render_allocation_report_pdf(context))

    assert "Exact stated capacity across 1 allocation: 100 homes." in text
    assert "1 allocation has a ranged capacity" in text
    # The exact-capacity sentence itself must never silently include the
    # ranged allocation's upper bound (the Section 6 BAD-example failure
    # mode) - it must read exactly "100 homes", never "15,100 homes".
    assert "Exact stated capacity across 1 allocation: 15,100 homes." not in text
    assert "15,000" in text or "8,400" in text  # the range's own display string, unblended


def test_unknown_capacity_rendered_separately(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)  # no dwellings figures at all -> unknown
    context = build_allocation_report_context(session, [allocation.id])

    text = _pdf_text(render_allocation_report_pdf(context))

    assert "1 allocation has unknown capacity." in text


def test_review_required_residual_not_shown_as_zero(session):
    from app.db.models import SchemeIntelligence

    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=1000)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id, review_status="needs_confirmation")
    app = _make_app(session, site.id, reference="APP/1")
    session.add(SchemeIntelligence(application_id=app.id, total_units_final=300, core_intelligence_complete=True))
    session.commit()
    context = build_allocation_report_context(session, [allocation.id])
    entry = context.entries[0]
    assert entry.indicative_residual_capacity is None  # precondition matches Gate 2's own hardening test

    text = _pdf_text(render_allocation_report_pdf(context))

    assert "Not determined" in text


# --- Planning activity -------------------------------------------------------


def test_no_linked_application_shows_neutral_text(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=100)
    context = build_allocation_report_context(session, [allocation.id])

    text = _pdf_text(render_allocation_report_pdf(context))

    assert NO_LINKED_APPLICATION_TEXT in text


def test_linked_application_reference_present_but_not_headline(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=100)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id)
    _make_app(session, site.id, reference="24/01234/FUL", proposal="Erection of 50 dwellings")
    context = build_allocation_report_context(session, [allocation.id])

    text = _pdf_text(render_allocation_report_pdf(context))

    assert "24/01234/FUL" in text
    assert "Erection of 50 dwellings" in text
    # The reference line is a secondary "Ref: ..." detail line, never the section heading itself.
    assert "Ref: 24/01234/FUL" in text


# --- Party evidence -----------------------------------------------------------


def test_applicant_stays_applicant(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=100)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id)
    _make_app(session, site.id, reference="APP/1", applicant_name_raw="Acme Applicant Ltd")
    context = build_allocation_report_context(session, [allocation.id])

    text = _pdf_text(render_allocation_report_pdf(context))

    assert "Applicant:" in text
    assert "Acme Applicant Ltd" in text
    # Never promoted onto a "Developer:" line.
    assert "Developer: Acme Applicant Ltd" not in text


def test_trusted_developer_appears_as_developer(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=100)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id)
    _make_control(session, site_id=site.id, entity_name_raw="Trusted Developer Ltd", role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")
    context = build_allocation_report_context(session, [allocation.id])

    text = _pdf_text(render_allocation_report_pdf(context))

    assert "Developer:" in text
    assert "Trusted Developer Ltd" in text


def test_needs_confirmation_developer_excluded_from_trusted_line(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=100)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id)
    _make_control(
        session, site_id=site.id, entity_name_raw="Pending Developer Ltd", role="DEVELOPER",
        evidence_category="S106_DEFINED_DEVELOPER", review_status="needs_confirmation",
    )
    context = build_allocation_report_context(session, [allocation.id])

    text = _pdf_text(render_allocation_report_pdf(context))

    assert "Developer (evidence pending confirmation): Pending Developer Ltd" in text
    assert "Developer: Pending Developer Ltd" not in text


def test_rejected_evidence_absent(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=100)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id)
    _make_control(
        session, site_id=site.id, entity_name_raw="Rejected Party Ltd", role="DEVELOPER",
        evidence_category="S106_DEFINED_DEVELOPER", review_status="rejected",
    )
    context = build_allocation_report_context(session, [allocation.id])

    text = _pdf_text(render_allocation_report_pdf(context))

    assert "Rejected Party Ltd" not in text


# --- AI Allocation Intelligence -----------------------------------------------


def test_available_summary_rendered(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=100)
    _make_summary(
        session, allocation.id, headline="Strong opportunity signal.", overview="Detailed overview text.",
        key_points='["Point one", "Point two"]',
    )
    context = build_allocation_report_context(session, [allocation.id])

    text = _pdf_text(render_allocation_report_pdf(context))

    assert "Strong opportunity signal." in text
    assert "Detailed overview text." in text
    assert "Point one" in text


def test_missing_summary_shows_neutral_unavailable_text(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=100)
    context = build_allocation_report_context(session, [allocation.id])

    text = _pdf_text(render_allocation_report_pdf(context))

    assert AI_INTELLIGENCE_UNAVAILABLE_TEXT in text


def test_errored_summary_shows_neutral_unavailable_text_and_no_raw_error(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=100)
    _make_summary(session, allocation.id, status="error", headline=None, overview=None, generation_error="Traceback: OpenAI timeout at line 42")
    context = build_allocation_report_context(session, [allocation.id])

    text = _pdf_text(render_allocation_report_pdf(context))

    assert AI_INTELLIGENCE_UNAVAILABLE_TEXT in text
    assert "Traceback" in text or "OpenAI timeout" not in text  # never leak the raw error string
    assert "OpenAI timeout" not in text


def test_zero_openai_calls(session):
    """Static isolation proof: the renderer module imports no OpenAI client
    at all (unlike app.reporting.pdf_report, which does for its own,
    unrelated narrative step) - there is nothing in this module capable of
    making a network call, so exercising it can never reach OpenAI."""
    import app.reporting.allocation_report_pdf as module

    # No "import openai" (or equivalent) anywhere in the module's actual
    # code - the docstring itself discusses the design decision in prose
    # and legitimately mentions "OpenAI", so this checks import statements
    # specifically rather than scanning the whole source text for the word.
    tree = ast.parse(inspect_getsource(module))
    imported_names = {
        alias.name.split(".")[0]
        for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "openai" not in imported_names

    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=100)
    _make_summary(session, allocation.id)
    context = build_allocation_report_context(session, [allocation.id])

    render_allocation_report_pdf(context)  # must not raise


# --- Missing / excluded candidates --------------------------------------------


def test_excluded_candidate_reported_and_others_still_render(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, site_name="Land off Present Road", minimum_dwellings=100)
    missing_id = allocation.id + 999999
    context = build_allocation_report_context(session, [allocation.id, missing_id])

    assert len(context.excluded) == 1

    text = _pdf_text(render_allocation_report_pdf(context))

    assert "Excluded Shortlist Items" in text
    assert str(missing_id) in text
    assert "Land off Present Road" in text  # the remaining, valid allocation still renders in full


def test_no_excluded_section_when_nothing_excluded(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=100)
    context = build_allocation_report_context(session, [allocation.id])

    text = _pdf_text(render_allocation_report_pdf(context))

    assert "Excluded Shortlist Items" not in text


# --- Determinism / renderer isolation -----------------------------------------


def test_repeated_generation_from_same_context_is_equivalent(session):
    plan = _make_local_plan(session)
    ids = _build_shortlist_of(session, 3)
    context = build_allocation_report_context(session, ids)

    text_1 = _pdf_text(render_allocation_report_pdf(context))
    text_2 = _pdf_text(render_allocation_report_pdf(context))

    assert text_1 == text_2


def test_allocation_sections_render_in_deterministic_id_order(session):
    plan = _make_local_plan(session)
    a1 = _make_allocation(session, plan.id, policy_reference="Z1", site_name="Zeta Allocation", minimum_dwellings=100)
    a2 = _make_allocation(session, plan.id, policy_reference="A1", site_name="Alpha Allocation", minimum_dwellings=100)
    context = build_allocation_report_context(session, [a2.id, a1.id])  # requested out of id order

    text = _pdf_text(render_allocation_report_pdf(context))

    # context.entries is id-sorted (Gate 2 guarantee) - Zeta (lower id, created first) must precede Alpha in the text.
    assert text.index("Zeta Allocation") < text.index("Alpha Allocation")


def test_renderer_performs_zero_database_queries(session):
    plan = _make_local_plan(session)
    ids = _build_shortlist_of(session, 5)
    context = build_allocation_report_context(session, ids)

    query_count = _count_select_queries(session, lambda: render_allocation_report_pdf(context))

    assert query_count == 0


def test_renderer_needs_no_session_or_orm_object():
    """Signature-level proof: render_allocation_report_pdf takes exactly one
    REQUIRED argument (context) - no Session, no engine, no ORM object, no
    OpenAI client can be required. Gate 4 (specifications/016-...) added two
    OPTIONAL, keyword-only, default-None parameters (executive_intelligence/
    web_evidence, both already-built plain dataclasses, never a Session/
    client/engine) - every Gate 3 call site (`render_allocation_report_pdf(
    context)`) is therefore still exactly as isolated as this test always
    asserted; only the "exactly one parameter, full stop" shape of the
    original assertion needed updating for the new, deliberate optional
    extension."""
    import inspect

    sig = inspect.signature(render_allocation_report_pdf)
    params = list(sig.parameters.values())
    required = [p for p in params if p.default is inspect.Parameter.empty]
    optional = [p for p in params if p.default is not inspect.Parameter.empty]

    assert [p.name for p in required] == ["context"]
    for p in optional:
        assert p.default is None
        assert p.kind is inspect.Parameter.KEYWORD_ONLY
        assert not any(kw in p.name.lower() for kw in ("session", "client", "engine", "openai", "db"))


def test_full_query_count_context_plus_pdf_remains_flat_across_shortlist_sizes(session):
    counts = {}
    for n in (5, 10, 25, 50):
        ids = _build_shortlist_of(session, n, prefix=f"Q{n}-")

        def _build_and_render():
            ctx = build_allocation_report_context(session, ids)
            render_allocation_report_pdf(ctx)

        counts[n] = _count_select_queries(session, _build_and_render)

    # Flat regardless of shortlist size (Gate 2's own 9-query baseline,
    # preserved unchanged since the renderer adds zero queries of its own).
    assert len(set(counts.values())) == 1, f"query count did not stay flat across sizes: {counts}"
    assert counts[5] == 9, f"expected the Gate 2 baseline of 9 queries, got {counts}"


# --- Filename helper -----------------------------------------------------------


def test_filename_helper_is_deterministic_and_safe(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=100)
    context = build_allocation_report_context(session, [allocation.id])

    filename = allocation_report_pdf_filename(context)

    assert filename.startswith("property-aigent-allocation-report-")
    assert filename.endswith(".pdf")
    assert " " not in filename
