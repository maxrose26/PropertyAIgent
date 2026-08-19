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
    find_allocation_evidence_for_document,
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


# ---------------------------------------------------------------------------
# Stage 2D evidence-semantics amendment: positive evidence for a DIFFERENT
# Site must never, by itself, be treated as contradicting a fuzzy
# candidate - a many-to-many world means "documents confirm Site B" says
# nothing about whether Site A (the fuzzy guess) is also related or
# unrelated. Only genuine NEGATIVE language naming the fuzzy candidate's
# own Site is a real contradiction. This regresses the exact pattern found
# in all 4 real production DOCUMENT_CONTRADICTS_FUZZY cases audited during
# the amendment (JPA 32, JPA 1.1, JPA 29, JPA 30) - every one had zero
# contradictory_hits and was simply strong evidence for a different Site.
# ---------------------------------------------------------------------------


def test_alternative_positive_site_evidence_does_not_contradict_fuzzy_candidate(session):
    _make_council(session, "testcouncil")
    fuzzy_site = _make_site(session, "testcouncil", "north of mosley common fuzzy guess")
    document_site = _make_site(session, "testcouncil", "mosley common south of the guided busway worsley")
    allocation = _make_allocation(session, "testcouncil", "North of Mosley Common", "JPA 32")
    app = _make_application(session, "testcouncil", "APP/1", site_id=document_site.id)
    _make_document(session, app.id, "planning_statement",
                    "This site is allocated for residential development under policy JPA 32.")
    session.commit()

    stage2a = _stage2a_high_confidence(allocation.id, fuzzy_site.id, score=100.0)
    result = evaluate_allocation_document_evidence(session, allocation, stage2a)

    assert result.recommended_outcome == DOCUMENT_CONFIRMED_SITE
    assert result.recommended_outcome != DOCUMENT_CONTRADICTS_FUZZY
    assert result.contradiction_flag is False
    assert result.evidenced_site_ids == {document_site.id}


def test_explicit_outside_allocation_language_still_contradicts_named_fuzzy_site(session):
    # Same scenario as above, EXCEPT the document explicitly negates the
    # fuzzy candidate's own Site by name - this is the one case that must
    # still classify as a genuine contradiction.
    _make_council(session, "testcouncil")
    fuzzy_site = _make_site(session, "testcouncil", "old grove house vine street")
    allocation = _make_allocation(session, "testcouncil", "John Street", "HOM 2.1")
    app = _make_application(session, "testcouncil", "APP/1", site_id=fuzzy_site.id)
    _make_document(session, app.id, "decision_notice",
                    "This site is outside allocation HOM 2.1 and is not affected by the Local Plan designation.")
    session.commit()

    stage2a = _stage2a_high_confidence(allocation.id, fuzzy_site.id)
    result = evaluate_allocation_document_evidence(session, allocation, stage2a)

    assert result.recommended_outcome == DOCUMENT_CONTRADICTS_FUZZY
    assert result.contradiction_flag is True


def test_adjacent_to_allocation_language_does_not_establish_membership(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "some neighbouring site")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "officer_report",
                    "The application site is adjacent to allocation HOM 2.30 and is not itself allocated.")
    session.commit()

    positive, contradictory = find_document_evidence_for_allocation(session, allocation)

    # "adjacent to" is never read as membership - it must never appear in
    # positive_hits (which would wrongly suggest this Site is IN the
    # allocation); it is correctly recorded only as a contradictory hit.
    assert not any(h.site_id == site.id for h in positive)
    assert any(h.site_id == site.id and h.category == CONTRADICTORY_REFERENCE for h in contradictory)


def test_new_carrington_production_evidence_pattern_is_alternative_not_contradiction(session):
    # Regresses the real JPA 30 New Carrington production case audited
    # during the Stage 2D amendment: Stage 2A AMBIGUOUS across 3 fuzzy
    # candidates within the wider strategic allocation; document evidence
    # (an officer_report, EXPLICIT_REFERENCE) confirms a further, separate
    # parcel. Zero contradictory hits. A large multi-parcel strategic
    # allocation must never be collapsed to one "winner" Site, and
    # confirming one parcel must never exclude the fuzzy candidates as
    # "contradicted".
    _make_council(session, "testcouncil")
    fuzzy_a = _make_site(session, "testcouncil", "new carrington strategic site sale west carrington lane")
    fuzzy_b = _make_site(session, "testcouncil", "power station manchester road carrington")
    document_site = _make_site(session, "testcouncil", "warburton lane warburton")
    allocation = _make_allocation(session, "testcouncil", "New Carrington", "JPA 30")
    app = _make_application(session, "testcouncil", "APP/1", site_id=document_site.id)
    _make_document(session, app.id, "officer_report",
                    "The site is allocated for development under the strategic Places for Everyone (PfE) plan - "
                    "New Carrington allocation (JPA 30).")
    session.commit()

    stage2a = AllocationMatchResult(
        allocation_id=allocation.id, council="testcouncil", policy_reference="JPA 30",
        allocation_name="New Carrington", allocation_capacity=5000, current_review_status="needs_confirmation",
        classification="AMBIGUOUS", reason="multiple plausible candidates",
        candidates=[
            SiteCandidate(site_id=fuzzy_a.id, site_name="a", score=100.0, total_units=None, application_count=1),
            SiteCandidate(site_id=fuzzy_b.id, site_name="b", score=83.3, total_units=None, application_count=1),
        ],
    )
    result = evaluate_allocation_document_evidence(session, allocation, stage2a)

    assert result.recommended_outcome == DOCUMENT_CONFIRMED_SITE
    assert result.recommended_outcome != DOCUMENT_CONTRADICTS_FUZZY
    assert result.evidenced_site_ids == {document_site.id}


def test_forward_reference_finds_evidence_for_matching_allocation(session):
    """Stage 3A Section 9: the FORWARD direction - given one already-
    extracted document, check it against a council's allocations, rather
    than the other way round."""
    _make_council(session, "testcouncil")
    allocation_a = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    allocation_b = _make_allocation(session, "testcouncil", "Other Allocation", "HOM 2.31")
    app = _make_application(session, "testcouncil", "APP/1")
    doc = _make_document(session, app.id, "officer_report", "This forms part of allocation HOM 2.30.")
    session.commit()

    results = find_allocation_evidence_for_document(doc, app, [allocation_a, allocation_b])

    assert allocation_a.id in results
    assert allocation_b.id not in results
    positive, contradictory = results[allocation_a.id]
    assert contradictory == []
    assert any(h.category == EXPLICIT_REFERENCE for h in positive)


def test_forward_reference_scopes_to_matching_council_only(session):
    _make_council(session, "testcouncil")
    _make_council(session, "othercouncil")
    other_council_allocation = _make_allocation(session, "othercouncil", "Sanderling Road", "HOM 2.30")
    app = _make_application(session, "testcouncil", "APP/1")
    doc = _make_document(session, app.id, "officer_report", "This forms part of allocation HOM 2.30.")
    session.commit()

    results = find_allocation_evidence_for_document(doc, app, [other_council_allocation])

    assert results == {}


def test_forward_reference_finds_no_evidence_for_unrelated_document(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    app = _make_application(session, "testcouncil", "APP/1")
    doc = _make_document(session, app.id, "officer_report", "A completely unrelated scheme with no allocation reference.")
    session.commit()

    results = find_allocation_evidence_for_document(doc, app, [allocation])
    assert results == {}


def test_forward_reference_handles_document_with_no_extracted_text(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    app = _make_application(session, "testcouncil", "APP/1")
    doc = Document(application_id=app.id, doc_type="officer_report", extracted_text=None, text_extracted=False)
    session.add(doc)
    session.commit()

    results = find_allocation_evidence_for_document(doc, app, [allocation])
    assert results == {}


def test_forward_reference_reuses_same_evidence_categories_as_reverse_direction(session):
    """Same document/allocation pair evaluated in both directions must
    produce the SAME evidence category - confirms genuine reuse of the
    same underlying regex/proximity primitives, not a second matcher
    with independent (and possibly diverging) behaviour."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    app = _make_application(session, "testcouncil", "APP/1")
    doc = _make_document(session, app.id, "officer_report", "This forms part of allocation HOM 2.30.")
    session.commit()

    reverse_positive, _ = find_document_evidence_for_allocation(session, allocation)
    forward_results = find_allocation_evidence_for_document(doc, app, [allocation])
    forward_positive, _ = forward_results[allocation.id]

    assert len(reverse_positive) == len(forward_positive) == 1
    assert reverse_positive[0].category == forward_positive[0].category == EXPLICIT_REFERENCE


def test_forward_reference_never_writes_to_database():
    source = inspect.getsource(find_allocation_evidence_for_document)
    assert "session.add(" not in source
    assert "session.flush()" not in source
    assert "session.commit()" not in source
    # Takes no Session parameter at all - it does no I/O of its own.
    sig = inspect.signature(find_allocation_evidence_for_document)
    assert "session" not in sig.parameters


def test_south_of_hyde_production_evidence_pattern_is_alternative_not_contradiction(session):
    # Regresses the real JPA 29 South of Hyde production case: Stage 2A
    # REVIEW_CANDIDATE (near-miss only, no decided candidate); document
    # evidence (a planning_statement, STRONG_CONTEXTUAL_REFERENCE) confirms
    # a Site the fuzzy layer never even surfaced as a near miss. Zero
    # contradictory hits - must not be excluded as "contradicted".
    _make_council(session, "testcouncil")
    near_miss_site = _make_site(session, "testcouncil", "brook fold lane rear of 296 mottram road hyde")
    document_site = _make_site(session, "testcouncil", "hyde east and west of stockport road hyde")
    allocation = _make_allocation(session, "testcouncil", "South of Hyde", "JPA 29")
    app = _make_application(session, "testcouncil", "APP/1", site_id=document_site.id)
    _make_document(session, app.id, "planning_statement",
                    "The site is covered by policy JPA 29 - South of Hyde on the policies map.")
    session.commit()

    stage2a = AllocationMatchResult(
        allocation_id=allocation.id, council="testcouncil", policy_reference="JPA 29",
        allocation_name="South of Hyde", allocation_capacity=800, current_review_status="needs_confirmation",
        classification=REVIEW_CANDIDATE, reason="near miss only",
        near_miss_candidates=[SiteCandidate(site_id=near_miss_site.id, site_name="near miss", score=70.0, total_units=None, application_count=1)],
    )
    result = evaluate_allocation_document_evidence(session, allocation, stage2a)

    assert result.recommended_outcome == DOCUMENT_CONFIRMED_SITE
    assert result.recommended_outcome != DOCUMENT_CONTRADICTS_FUZZY
    assert result.evidenced_site_ids == {document_site.id}


# ---------------------------------------------------------------------------
# Stage 2E.2 Final Matcher Amendment - multi-reference sentence attribution
# (Section 17 items 1-8)
# ---------------------------------------------------------------------------


def test_forms_part_of_one_allocation_and_adjoins_another_attributes_correctly(session):
    """Item 1 / the real production case (FUL/355603/26, Land South Of
    Bullcote Lane): "forms part of JPA12 and adjoins JPA10" must not let
    JPA12's positive phrase bleed onto JPA10 - JPA10 must instead pick up
    its own, closer "adjoins" language as a contradiction."""
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "Land South Of Bullcote Lane")
    jpa12 = _make_allocation(session, "testcouncil", "Broadbent Moss", "JPA 12")
    jpa10 = _make_allocation(session, "testcouncil", "Beal Valley", "JPA 10")
    app = _make_application(session, "testcouncil", "FUL/355603/26", site_id=site.id)
    _make_document(session, app.id, "other",
                    "Whilst the present application envisages 248 dwellings, the site forms part of Places "
                    "for Everyone allocation policy JPA 12 Broadbent Moss and adjoins allocation Policy "
                    "JPA 10 Beal Valley within which a total of 1930 dwellings are proposed.")
    session.commit()

    jpa12_positive, jpa12_contra = find_document_evidence_for_allocation(session, jpa12)
    jpa10_positive, jpa10_contra = find_document_evidence_for_allocation(session, jpa10)

    assert any(h.site_id == site.id and h.category == EXPLICIT_REFERENCE for h in jpa12_positive)
    assert jpa12_contra == []

    assert not any(h.site_id == site.id for h in jpa10_positive)
    assert any(h.site_id == site.id and h.category == CONTRADICTORY_REFERENCE for h in jpa10_contra)


def test_within_one_allocation_adjacent_to_another_attributes_correctly(session):
    """Item 2 - a different phrasing pair ("within .../adjacent to
    ...") must split the same way."""
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "Boundary Parcel")
    jpa30 = _make_allocation(session, "testcouncil", "New Carrington", "JPA 30")
    jpa29 = _make_allocation(session, "testcouncil", "South of Hyde", "JPA 29")
    app = _make_application(session, "testcouncil", "APP/2", site_id=site.id)
    _make_document(session, app.id, "other",
                    "The site lies within policy JPA 30, adjacent to the allocation JPA 29 to the south.")
    session.commit()

    jpa30_positive, jpa30_contra = find_document_evidence_for_allocation(session, jpa30)
    jpa29_positive, jpa29_contra = find_document_evidence_for_allocation(session, jpa29)

    assert any(h.site_id == site.id and h.category == EXPLICIT_REFERENCE for h in jpa30_positive)
    assert not any(h.site_id == site.id for h in jpa29_positive)
    assert any(h.site_id == site.id and h.category == CONTRADICTORY_REFERENCE for h in jpa29_contra)


def test_forms_part_of_two_allocations_both_positive(session):
    """Item 3 - a single phrase governing a genuine compound object
    ("forms part of X and Y") must still credit BOTH references - nearest-
    phrase attribution must not require the phrase to be repeated."""
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "Shared Parcel")
    jpa10 = _make_allocation(session, "testcouncil", "Beal Valley", "JPA 10")
    jpa12 = _make_allocation(session, "testcouncil", "Broadbent Moss", "JPA 12")
    app = _make_application(session, "testcouncil", "APP/3", site_id=site.id)
    _make_document(session, app.id, "other",
                    "The site forms part of allocations JPA 10 and JPA 12 within the joint masterplan area.")
    session.commit()

    jpa10_positive, _ = find_document_evidence_for_allocation(session, jpa10)
    jpa12_positive, _ = find_document_evidence_for_allocation(session, jpa12)

    assert any(h.site_id == site.id and h.category == EXPLICIT_REFERENCE for h in jpa10_positive)
    assert any(h.site_id == site.id and h.category == EXPLICIT_REFERENCE for h in jpa12_positive)


def test_straddles_two_allocations_genuine_multi_allocation_evidence(session):
    """Item 4 - "straddles" is explicit enough to support two DIFFERENT
    allocation references at once, unlike a bare shared conjunction."""
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "Boundary Site")
    jpa10 = _make_allocation(session, "testcouncil", "Beal Valley", "JPA 10")
    jpa12 = _make_allocation(session, "testcouncil", "Broadbent Moss", "JPA 12")
    app = _make_application(session, "testcouncil", "APP/4", site_id=site.id)
    _make_document(session, app.id, "other",
                    "The development straddles allocation JPA 10 and allocation JPA 12.")
    session.commit()

    jpa10_positive, _ = find_document_evidence_for_allocation(session, jpa10)
    jpa12_positive, _ = find_document_evidence_for_allocation(session, jpa12)

    assert any(h.site_id == site.id and h.category == EXPLICIT_REFERENCE for h in jpa10_positive)
    assert any(h.site_id == site.id and h.category == EXPLICIT_REFERENCE for h in jpa12_positive)


def test_positive_phrase_does_not_bleed_across_a_more_distant_reference(session):
    """Item 5 - a positive phrase attached to a reference right next to it
    must not reach a SECOND reference further away in the same window just
    because both fall inside PROXIMITY_WINDOW_CHARS."""
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "Far Parcel")
    near_alloc = _make_allocation(session, "testcouncil", "Near Site", "JPA 40")
    far_alloc = _make_allocation(session, "testcouncil", "Far Site", "JPA 41")
    app = _make_application(session, "testcouncil", "APP/5", site_id=site.id)
    _make_document(session, app.id, "other",
                    "The proposal forms part of allocation JPA 40, a strategic site with significant "
                    "highway and drainage infrastructure requirements still under review, and lies "
                    "opposite the allocation JPA 41 on the other side of the valley.")
    session.commit()

    near_positive, _ = find_document_evidence_for_allocation(session, near_alloc)
    far_positive, far_contra = find_document_evidence_for_allocation(session, far_alloc)

    assert any(h.site_id == site.id and h.category == EXPLICIT_REFERENCE for h in near_positive)
    assert not any(h.site_id == site.id and h.category == EXPLICIT_REFERENCE for h in far_positive)
    assert any(h.site_id == site.id and h.category == CONTRADICTORY_REFERENCE for h in far_contra)


def test_negative_phrase_wins_for_its_own_reference(session):
    """Item 6 - a negative phrase local to a reference always overrides,
    even when there is no competing positive phrase for that reference at
    all."""
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "Beyond Site")
    allocation = _make_allocation(session, "testcouncil", "Chequerbent North", "JPA 5")
    app = _make_application(session, "testcouncil", "APP/6", site_id=site.id)
    _make_document(session, app.id, "other", "This site sits beyond the allocation JPA 5 boundary.")
    session.commit()

    positive, contradictory = find_document_evidence_for_allocation(session, allocation)
    assert not any(h.site_id == site.id for h in positive)
    assert any(h.site_id == site.id and h.category == CONTRADICTORY_REFERENCE for h in contradictory)


def test_generic_reference_safeguard_unchanged_by_attribution_fix(session):
    """Item 7 - Stage 2E.1's generic-reference name-corroboration rule is
    untouched: a bare "policy H3, H4..." list still never establishes
    membership, regardless of the new nearest-phrase logic."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    site = _make_site(session, "testcouncil", "King Street")
    app = _make_application(session, "testcouncil", "APP/7", site_id=site.id)
    _make_document(session, app.id, "design_access",
                    "policy h3 - accessibility to sustainable transport/bus routes. "
                    "policy h4 - affordable housing provision.")
    session.commit()

    positive, _ = find_document_evidence_for_allocation(session, allocation)
    site_hits = [h for h in positive if h.site_id == site.id]
    assert site_hits
    assert all(h.category == WEAK_REFERENCE for h in site_hits)


def test_stage3b_explicit_only_auto_create_unchanged_by_attribution_fix(session):
    """Item 8 - the forward (Stage 3B) direction shares _build_reference_hits
    with the backward direction, so the attribution fix applies identically
    there too, and JPA10/JPA12-style separation holds in that direction."""
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "Land South Of Bullcote Lane")
    jpa12 = _make_allocation(session, "testcouncil", "Broadbent Moss", "JPA 12")
    jpa10 = _make_allocation(session, "testcouncil", "Beal Valley", "JPA 10")
    app = _make_application(session, "testcouncil", "FUL/355603/26", site_id=site.id)
    doc = _make_document(session, app.id, "other",
                          "The site forms part of Places for Everyone allocation policy JPA 12 Broadbent "
                          "Moss and adjoins allocation Policy JPA 10 Beal Valley.")
    session.commit()

    results = find_allocation_evidence_for_document(doc, app, [jpa12, jpa10])

    assert jpa12.id in results
    jpa12_positive, jpa12_contra = results[jpa12.id]
    assert any(h.category == EXPLICIT_REFERENCE for h in jpa12_positive)
    assert jpa12_contra == []

    if jpa10.id in results:
        jpa10_positive, jpa10_contra = results[jpa10.id]
        assert not any(h.category in (EXPLICIT_REFERENCE, STRONG_CONTEXTUAL_REFERENCE) for h in jpa10_positive)
        assert any(h.category == CONTRADICTORY_REFERENCE for h in jpa10_contra)
