"""GM Allocation <-> Planning Activity document-evidence matching tests
(Stage 2C). Every test runs against the shared in-memory SQLite `session`
fixture (tests/conftest.py) - never the real production database.
"""
from __future__ import annotations

import inspect

from sqlalchemy import select

from app.db.models import Application, Council, Document, LocalPlanSite, Site
from app.policy import allocation_document_evidence as evidence_module
from app.policy.allocation_document_evidence import (
    CONTRADICTORY_REFERENCE,
    DOCUMENT_CONFIRMED_APPLICATION_ONLY,
    DOCUMENT_CONFIRMED_SITE,
    DOCUMENT_CONTRADICTS_FUZZY,
    EXPLICIT_REFERENCE,
    FUZZY_SUPPORTED_BY_DOCUMENT,
    MULTIPLE_DOCUMENT_SUPPORTED_SITES,
    NAME_AND_POLICY_CONTEXT,
    NO_DOCUMENT_EVIDENCE,
    STRONG_CONTEXTUAL_REFERENCE,
    WEAK_REFERENCE,
    derive_recommended_outcome,
    evaluate_allocation_document_evidence,
    find_document_evidence_for_allocation,
    is_generic_reference,
)
from app.policy.allocation_site_dry_run_matching import (
    HIGH_CONFIDENCE_CANDIDATE,
    REVIEW_CANDIDATE,
    AllocationMatchResult,
    SiteCandidate,
)


def _make_council(session, code: str) -> None:
    if session.get(Council, code) is None:
        session.add(Council(code=code, name=code.title(), base_url="https://example.invalid",
                             date_field_mode="received", doc_system="idox"))


def _make_allocation(session, council_code: str, site_name: str, policy_reference: str | None) -> LocalPlanSite:
    allocation = LocalPlanSite(
        council_code=council_code, policy_reference=policy_reference, site_name=site_name,
        minimum_dwellings=100, plan_name="Test Local Plan", plan_status="adopted",
    )
    session.add(allocation)
    session.flush()
    return allocation


def _make_application(session, council_code: str, reference: str, site_id: int | None = None) -> Application:
    app = Application(council_code=council_code, reference=reference, site_id=site_id)
    session.add(app)
    session.flush()
    return app


def _make_document(session, application_id: int, doc_type: str, text: str) -> Document:
    doc = Document(application_id=application_id, doc_type=doc_type, extracted_text=text, text_extracted=True)
    session.add(doc)
    session.flush()
    return doc


def _make_site(session, council_code: str, address: str) -> Site:
    site = Site(council_code=council_code, canonical_address=address, display_address=address)
    session.add(site)
    session.flush()
    return site


# ---------------------------------------------------------------------------
# 1/2/3. Exact reference match, explicit relationship language
# ---------------------------------------------------------------------------


def test_exact_reference_with_positive_language_is_explicit_reference(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    app = _make_application(session, "testcouncil", "APP/1")
    _make_document(session, app.id, "planning_statement",
                    "The application site forms part of allocation HOM 2.30 in the adopted Local Plan.")
    session.commit()

    positive, contradictory = find_document_evidence_for_allocation(session, allocation)

    assert contradictory == []
    assert any(h.category == EXPLICIT_REFERENCE for h in positive)


def test_within_allocation_language_is_explicit_reference(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    app = _make_application(session, "testcouncil", "APP/1")
    _make_document(session, app.id, "officer_report",
                    "The proposal lies within allocation HOM 2.30 as identified in the Local Plan.")
    session.commit()

    positive, _ = find_document_evidence_for_allocation(session, allocation)

    assert any(h.category == EXPLICIT_REFERENCE for h in positive)


def test_reference_without_relationship_language_is_strong_contextual(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    app = _make_application(session, "testcouncil", "APP/1")
    _make_document(session, app.id, "decision_notice",
                    "Reference is made to HOM 2.30 elsewhere in the officer's assessment of this scheme.")
    session.commit()

    positive, _ = find_document_evidence_for_allocation(session, allocation)

    assert any(h.category == STRONG_CONTEXTUAL_REFERENCE for h in positive)
    assert not any(h.category == EXPLICIT_REFERENCE for h in positive)


# ---------------------------------------------------------------------------
# 4/5. Short-token false-positive prevention
# ---------------------------------------------------------------------------


def test_short_reference_bare_mention_is_not_matched(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    app = _make_application(session, "testcouncil", "APP/1")
    # "H3" appears bare here - inside an unrelated word/context, no "policy"
    # or "allocation" immediately before it.
    _make_document(session, app.id, "planning_statement",
                    "The site is accessed via the H3 junction improvement scheme, unrelated to any allocation.")
    session.commit()

    positive, contradictory = find_document_evidence_for_allocation(session, allocation)

    assert positive == []
    assert contradictory == []


def test_short_reference_with_policy_prefix_is_matched(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    app = _make_application(session, "testcouncil", "APP/1")
    _make_document(session, app.id, "officer_report",
                    "The application forms part of allocation H3 (North Leigh Park) in the Local Plan.")
    session.commit()

    positive, _ = find_document_evidence_for_allocation(session, allocation)

    assert any(h.category == EXPLICIT_REFERENCE for h in positive)


def test_is_generic_reference_classification():
    assert is_generic_reference("H3") is True
    assert is_generic_reference("AN1") is True
    assert is_generic_reference("AN6") is True
    assert is_generic_reference("HOM 2.30") is False
    assert is_generic_reference("HLA0029") is False
    assert is_generic_reference("JPA 30") is False


# ---------------------------------------------------------------------------
# 6/7. Adjacency/negative language is never positive
# ---------------------------------------------------------------------------


def test_adjacent_to_allocation_is_contradictory_not_positive(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    app = _make_application(session, "testcouncil", "APP/1")
    _make_document(session, app.id, "planning_statement",
                    "The application site is adjacent to allocation HOM 2.30 but does not form part of it.")
    session.commit()

    positive, contradictory = find_document_evidence_for_allocation(session, allocation)

    assert any(h.category == CONTRADICTORY_REFERENCE for h in contradictory)
    assert positive == []


def test_outside_allocation_is_contradictory(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    app = _make_application(session, "testcouncil", "APP/1")
    _make_document(session, app.id, "decision_notice",
                    "The application site falls outside allocation HOM 2.30 as shown on the policies map.")
    session.commit()

    positive, contradictory = find_document_evidence_for_allocation(session, allocation)

    assert any(h.category == CONTRADICTORY_REFERENCE for h in contradictory)
    assert positive == []


# ---------------------------------------------------------------------------
# 8/9. Multiple Applications / multiple Sites preserved
# ---------------------------------------------------------------------------


def test_same_allocation_linked_via_multiple_applications(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    app1 = _make_application(session, "testcouncil", "APP/1")
    app2 = _make_application(session, "testcouncil", "APP/2")
    _make_document(session, app1.id, "planning_statement", "This forms part of allocation HOM 2.30, phase 1.")
    _make_document(session, app2.id, "planning_statement", "This forms part of allocation HOM 2.30, phase 2.")
    session.commit()

    positive, _ = find_document_evidence_for_allocation(session, allocation)

    application_ids = {h.application_id for h in positive}
    assert application_ids == {app1.id, app2.id}


def test_multiple_site_support_preserved_not_forced_to_one(session):
    _make_council(session, "testcouncil")
    site_a = _make_site(session, "testcouncil", "site a address")
    site_b = _make_site(session, "testcouncil", "site b address")
    allocation = _make_allocation(session, "testcouncil", "New Carrington", "JPA 30")
    app1 = _make_application(session, "testcouncil", "APP/1", site_id=site_a.id)
    app2 = _make_application(session, "testcouncil", "APP/2", site_id=site_b.id)
    _make_document(session, app1.id, "officer_report", "The scheme forms part of allocation JPA 30, western parcel.")
    _make_document(session, app2.id, "officer_report", "The scheme forms part of allocation JPA 30, eastern parcel.")
    session.commit()

    result = evaluate_allocation_document_evidence(session, allocation, stage2a=None)

    assert result.multi_site_flag is True
    assert result.evidenced_site_ids == {site_a.id, site_b.id}
    assert result.recommended_outcome == MULTIPLE_DOCUMENT_SUPPORTED_SITES


# ---------------------------------------------------------------------------
# 10. Application-only evidence retained
# ---------------------------------------------------------------------------


def test_application_only_evidence_retained_when_no_site_linked(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    app = _make_application(session, "testcouncil", "APP/1", site_id=None)
    _make_document(session, app.id, "planning_statement", "This forms part of allocation HOM 2.30.")
    session.commit()

    result = evaluate_allocation_document_evidence(session, allocation, stage2a=None)

    assert result.recommended_outcome == DOCUMENT_CONFIRMED_APPLICATION_ONLY
    assert result.positive_hits[0].application_id == app.id
    assert result.positive_hits[0].site_id is None


# ---------------------------------------------------------------------------
# 11/12/13. Combination with Stage 2A fuzzy results
# ---------------------------------------------------------------------------


def _stage2a_high_confidence(allocation_id, site_id, score=87.8):
    return AllocationMatchResult(
        allocation_id=allocation_id, council="testcouncil", policy_reference="HOM 2.30",
        allocation_name="Sanderling Road", allocation_capacity=100, current_review_status="auto_applied",
        classification=HIGH_CONFIDENCE_CANDIDATE, reason="single candidate",
        candidates=[SiteCandidate(site_id=site_id, site_name="site", score=score, total_units=None, application_count=1)],
    )


def test_fuzzy_high_confidence_supported_by_document_evidence(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "sanderling road site")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "officer_report", "This forms part of allocation HOM 2.30.")
    session.commit()

    stage2a = _stage2a_high_confidence(allocation.id, site.id)
    result = evaluate_allocation_document_evidence(session, allocation, stage2a)

    assert result.recommended_outcome == FUZZY_SUPPORTED_BY_DOCUMENT


def test_fuzzy_high_confidence_unsupported_no_document_evidence(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "old grove house vine street")
    allocation = _make_allocation(session, "testcouncil", "John Street, Hazel Grove", "HOM 2.1")
    session.commit()  # no documents at all

    stage2a = _stage2a_high_confidence(allocation.id, site.id)
    result = evaluate_allocation_document_evidence(session, allocation, stage2a)

    assert result.recommended_outcome == NO_DOCUMENT_EVIDENCE


def test_fuzzy_candidate_contradicted_by_document_evidence(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "old grove house vine street")
    allocation = _make_allocation(session, "testcouncil", "John Street", "HOM 2.1")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "decision_notice",
                    "This site is outside allocation HOM 2.1 and is not affected by the Local Plan designation.")
    session.commit()

    stage2a = _stage2a_high_confidence(allocation.id, site.id)
    result = evaluate_allocation_document_evidence(session, allocation, stage2a)

    assert result.recommended_outcome == DOCUMENT_CONTRADICTS_FUZZY
    assert result.contradiction_flag is True


def test_no_candidate_near_miss_never_treated_as_contradicted_fuzzy(session):
    # Regression test: app.policy.allocation_site_dry_run_matching's
    # NO_CANDIDATE results still carry near_miss_candidates purely for
    # score-distribution reporting (a below-threshold near miss Stage 2A
    # itself judged too weak to surface) - confirmed a real production
    # case where this made a genuinely NEW document-evidenced finding get
    # mislabelled as "contradicts fuzzy" when there was never a real
    # fuzzy candidate at all.
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "some weak near miss site")
    allocation = _make_allocation(session, "testcouncil", "Northern Gateway", "JPA1.1")
    app = _make_application(session, "testcouncil", "APP/1")
    _make_document(session, app.id, "planning_statement",
                    "The application site is part of the Northern Gateway allocation (JPA1.1).")
    session.commit()

    stage2a = AllocationMatchResult(
        allocation_id=allocation.id, council="testcouncil", policy_reference="JPA1.1",
        allocation_name="Northern Gateway", allocation_capacity=100, current_review_status="auto_applied",
        classification="NO_CANDIDATE", reason="no candidate reaches even the review threshold",
        near_miss_candidates=[SiteCandidate(site_id=site.id, site_name="site", score=40.0, total_units=None, application_count=0)],
    )
    result = evaluate_allocation_document_evidence(session, allocation, stage2a)

    assert result.recommended_outcome != DOCUMENT_CONTRADICTS_FUZZY
    assert result.recommended_outcome == DOCUMENT_CONFIRMED_APPLICATION_ONLY


def test_review_candidate_near_miss_supported_by_document_evidence(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "some review candidate site")
    allocation = _make_allocation(session, "testcouncil", "Land off Midland Road", "HOM 2.7")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "planning_statement", "This forms part of allocation HOM 2.7.")
    session.commit()

    stage2a = AllocationMatchResult(
        allocation_id=allocation.id, council="testcouncil", policy_reference="HOM 2.7",
        allocation_name="Land off Midland Road", allocation_capacity=220, current_review_status="needs_confirmation",
        classification=REVIEW_CANDIDATE, reason="near miss",
        near_miss_candidates=[SiteCandidate(site_id=site.id, site_name="site", score=76.5, total_units=None, application_count=1)],
    )
    result = evaluate_allocation_document_evidence(session, allocation, stage2a)

    assert result.recommended_outcome == FUZZY_SUPPORTED_BY_DOCUMENT


# ---------------------------------------------------------------------------
# 14/15. No production writes, no matched_site_id mutation
# ---------------------------------------------------------------------------


def test_no_mutations_anywhere(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "sanderling road site")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "officer_report", "This forms part of allocation HOM 2.30.")
    session.commit()

    before_matched = allocation.matched_site_id
    before_app_site = app.site_id

    evaluate_allocation_document_evidence(session, allocation, None)

    session.refresh(allocation)
    session.refresh(app)
    assert allocation.matched_site_id == before_matched
    assert app.site_id == before_app_site


def test_evidence_functions_never_call_session_add_flush_commit():
    for fn in (
        find_document_evidence_for_allocation, evaluate_allocation_document_evidence,
        derive_recommended_outcome,
    ):
        source = inspect.getsource(fn)
        assert "session.add(" not in source
        assert "session.flush()" not in source
        assert "session.commit()" not in source


# ---------------------------------------------------------------------------
# 16. No OpenAI
# ---------------------------------------------------------------------------


def test_no_openai_dependency():
    source = inspect.getsource(evidence_module)
    # The module docstring explains IN PROSE that OpenAI is never called -
    # that mention is fine. What must never appear is an actual import/call.
    assert "import openai" not in source.lower()
    assert "OpenAI(" not in source
    assert "from openai" not in source.lower()


# ---------------------------------------------------------------------------
# 17. No schema change
# ---------------------------------------------------------------------------


def test_no_schema_change_local_plan_site_columns_unchanged():
    expected_columns = {
        "id", "council_code", "local_plan_id", "policy_reference", "site_name", "intended_use",
        "minimum_dwellings", "indicative_capacity", "maximum_capacity", "category", "allocation_status",
        "raw_allocation_status", "plan_name", "plan_status", "source_document_url", "source_page",
        "geometry_placeholder", "matched_site_id", "match_confidence", "confirmed_by", "confirmed_at",
        "match_review_note", "review_status", "duplicate_classification", "duplicate_classification_note",
        "progression_signal", "progression_reasons", "progression_computed_at", "latitude", "longitude",
        "extracted_at", "updated_at",
    }
    assert {c.name for c in LocalPlanSite.__table__.columns} == expected_columns
    # Confirms this module never introduced a new Document/Application column.
    assert "extracted_text" in {c.name for c in Document.__table__.columns}


# ---------------------------------------------------------------------------
# Additional: NAME_AND_POLICY_CONTEXT / WEAK_REFERENCE tiers
# ---------------------------------------------------------------------------


def test_distinctive_name_with_local_plan_context_is_name_and_policy_context(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Grey Mare Lane", policy_reference=None)
    app = _make_application(session, "testcouncil", "APP/1")
    _make_document(session, app.id, "design_access",
                    "The Grey Mare Lane site is identified in the Local Plan allocation schedule.")
    session.commit()

    positive, _ = find_document_evidence_for_allocation(session, allocation)

    assert any(h.category == NAME_AND_POLICY_CONTEXT for h in positive)


def test_distinctive_name_alone_with_no_context_is_weak_reference(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Grey Mare Lane", policy_reference=None)
    app = _make_application(session, "testcouncil", "APP/1")
    _make_document(session, app.id, "application_form", "The proposal is located at Grey Mare Lane, Manchester.")
    session.commit()

    positive, _ = find_document_evidence_for_allocation(session, allocation)

    assert any(h.category == WEAK_REFERENCE for h in positive)
