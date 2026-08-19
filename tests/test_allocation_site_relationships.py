"""GM Allocation <-> Site many-to-many relationship foundation tests
(Stage 2D). Every test runs against the shared in-memory SQLite `session`
fixture (tests/conftest.py) - never the real production database.
"""
from __future__ import annotations

import inspect

from sqlalchemy import select

from app.db.models import AllocationSiteRelationship, Application, Council, Document, LocalPlanSite, Site
from app.policy import allocation_site_relationships as relationships_module
from app.policy.allocation_document_evidence import (
    AMBIGUOUS as EVIDENCE_AMBIGUOUS,
    DOCUMENT_CONFIRMED_APPLICATION_ONLY,
    DOCUMENT_CONFIRMED_SITE,
    DOCUMENT_CONTRADICTS_FUZZY,
    EXPLICIT_REFERENCE,
    FUZZY_SUPPORTED_BY_DOCUMENT,
    MULTIPLE_DOCUMENT_SUPPORTED_SITES,
    NO_DOCUMENT_EVIDENCE,
    AllocationEvidenceResult,
    DocumentEvidenceHit,
)
from app.policy.allocation_site_dry_run_matching import HIGH_CONFIDENCE_CANDIDATE
from app.policy.allocation_site_relationships import (
    EVIDENCE_BASIS_LEGACY_BACKFILL,
    fetch_accepted_relationships,
    plan_document_evidence_relationships,
    plan_legacy_backfill,
    run_controlled_relationship_write,
    run_relationship_dry_run,
)


def _make_council(session, code: str) -> None:
    if session.get(Council, code) is None:
        session.add(Council(code=code, name=code.title(), base_url="https://example.invalid",
                             date_field_mode="received", doc_system="idox"))


def _make_site(session, council_code: str, address: str) -> Site:
    site = Site(council_code=council_code, canonical_address=address, display_address=address)
    session.add(site)
    session.flush()
    return site


def _make_allocation(session, council_code: str, site_name: str, *, policy_reference: str | None = "REF1",
                      matched_site_id: int | None = None, match_confidence: float | None = None,
                      review_status: str = "auto_applied") -> LocalPlanSite:
    allocation = LocalPlanSite(
        council_code=council_code, policy_reference=policy_reference, site_name=site_name,
        minimum_dwellings=100, plan_name="Test Local Plan", plan_status="adopted",
        matched_site_id=matched_site_id, match_confidence=match_confidence, review_status=review_status,
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


def _evidence_result(allocation_id, council, policy_reference, allocation_name, *, classification, positive_hits=None):
    return AllocationEvidenceResult(
        allocation_id=allocation_id, council=council, policy_reference=policy_reference,
        allocation_name=allocation_name, stage2a_classification=classification,
        stage2a_candidate_site_ids=[], positive_hits=positive_hits or [],
    )


def _hit(document_id, application_id, site_id, category, doc_type="planning_statement", weight=3):
    return DocumentEvidenceHit(
        document_id=document_id, document_type=doc_type, application_id=application_id,
        application_reference=f"APP/{application_id}", site_id=site_id, matched_reference="REF1",
        snippet="evidence snippet", category=category, weight=weight,
    )


# ---------------------------------------------------------------------------
# 1/2/3. Cardinality
# ---------------------------------------------------------------------------


def test_one_allocation_one_site(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "some site")
    allocation = _make_allocation(session, "testcouncil", "Allocation A")
    session.add(AllocationSiteRelationship(
        allocation_id=allocation.id, site_id=site.id, evidence_basis="document_confirmed_site",
    ))
    session.commit()

    rels = session.execute(select(AllocationSiteRelationship)).scalars().all()
    assert len(rels) == 1
    assert rels[0].allocation_id == allocation.id
    assert rels[0].site_id == site.id


def test_one_allocation_multiple_sites(session):
    _make_council(session, "testcouncil")
    site_a = _make_site(session, "testcouncil", "site a")
    site_b = _make_site(session, "testcouncil", "site b")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", policy_reference="H3")
    session.add(AllocationSiteRelationship(allocation_id=allocation.id, site_id=site_a.id, evidence_basis="multiple_document_supported_sites"))
    session.add(AllocationSiteRelationship(allocation_id=allocation.id, site_id=site_b.id, evidence_basis="multiple_document_supported_sites"))
    session.commit()

    rels = session.execute(select(AllocationSiteRelationship).where(AllocationSiteRelationship.allocation_id == allocation.id)).scalars().all()
    assert len(rels) == 2
    assert {r.site_id for r in rels} == {site_a.id, site_b.id}


def test_one_site_multiple_allocation_records(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "shared site")
    allocation_1 = _make_allocation(session, "testcouncil", "Allocation A", policy_reference="REF1")
    allocation_2 = _make_allocation(session, "testcouncil", "Allocation B", policy_reference="REF2")
    session.add(AllocationSiteRelationship(allocation_id=allocation_1.id, site_id=site.id, evidence_basis="document_confirmed_site"))
    session.add(AllocationSiteRelationship(allocation_id=allocation_2.id, site_id=site.id, evidence_basis="document_confirmed_site"))
    session.commit()

    rels = session.execute(select(AllocationSiteRelationship).where(AllocationSiteRelationship.site_id == site.id)).scalars().all()
    assert len(rels) == 2
    assert {r.allocation_id for r in rels} == {allocation_1.id, allocation_2.id}


# ---------------------------------------------------------------------------
# 4. Duplicate pair prevented
# ---------------------------------------------------------------------------


def test_duplicate_pair_prevented_by_unique_constraint(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "some site")
    allocation = _make_allocation(session, "testcouncil", "Allocation A")
    session.add(AllocationSiteRelationship(allocation_id=allocation.id, site_id=site.id, evidence_basis="document_confirmed_site"))
    session.commit()

    session.add(AllocationSiteRelationship(allocation_id=allocation.id, site_id=site.id, evidence_basis="document_confirmed_site"))
    import pytest
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


# ---------------------------------------------------------------------------
# 5/6/7. matched_site_id backfill + retention + no whole-coverage claim
# ---------------------------------------------------------------------------


def test_existing_matched_site_id_planned_for_backfill(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "some site")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", matched_site_id=site.id, match_confidence=87.5)
    session.commit()

    planned = plan_legacy_backfill(session)

    assert len(planned) == 1
    assert planned[0].allocation_id == allocation.id
    assert planned[0].site_id == site.id
    assert planned[0].confidence == 87.5
    assert planned[0].evidence_basis == EVIDENCE_BASIS_LEGACY_BACKFILL


def test_controlled_write_backfills_existing_match_idempotently(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "some site")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", matched_site_id=site.id, match_confidence=87.5)
    session.commit()

    first = run_controlled_relationship_write(session)
    assert first["created_legacy_backfill"] == 1

    second = run_controlled_relationship_write(session)
    assert second["created_legacy_backfill"] == 0
    assert second["already_present_skipped"] == 1

    rels = session.execute(select(AllocationSiteRelationship)).scalars().all()
    assert len(rels) == 1  # no duplicate


def test_matched_site_id_is_retained_not_removed(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "some site")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", matched_site_id=site.id, match_confidence=87.5)
    session.commit()

    run_controlled_relationship_write(session)

    session.refresh(allocation)
    assert allocation.matched_site_id == site.id  # untouched, still present
    assert allocation.match_confidence == 87.5


def test_matched_site_id_does_not_imply_whole_allocation_coverage():
    # Structural/documentation guard: relationship_type defaults to
    # "unknown_scope", never "whole_site", for every row this module's
    # writer creates - the model itself never asserts whole coverage.
    source = inspect.getsource(relationships_module)
    assert '"whole_site"' not in source
    assert "= 'whole_site'" not in source


# ---------------------------------------------------------------------------
# 8/9/10. Document-evidence eligibility
# ---------------------------------------------------------------------------


def test_document_confirmed_site_is_eligible(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "some site")
    allocation = _make_allocation(session, "testcouncil", "Allocation A")
    result = _evidence_result(
        allocation.id, "testcouncil", "REF1", "Allocation A", classification="NO_CANDIDATE",
        positive_hits=[_hit(1, 1, site.id, EXPLICIT_REFERENCE)],
    )
    result.recommended_outcome = DOCUMENT_CONFIRMED_SITE

    planned, excluded = plan_document_evidence_relationships([result])

    assert len(planned) == 1
    assert planned[0].site_id == site.id
    assert planned[0].evidence_basis == "document_confirmed_site"
    assert all(len(v) == 0 for v in excluded.values())


def test_fuzzy_supported_by_document_is_eligible(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "some site")
    allocation = _make_allocation(session, "testcouncil", "Allocation A")
    result = _evidence_result(
        allocation.id, "testcouncil", "REF1", "Allocation A", classification=HIGH_CONFIDENCE_CANDIDATE,
        positive_hits=[_hit(1, 1, site.id, "STRONG_CONTEXTUAL_REFERENCE")],
    )
    result.recommended_outcome = FUZZY_SUPPORTED_BY_DOCUMENT

    planned, _ = plan_document_evidence_relationships([result])

    assert len(planned) == 1
    assert planned[0].evidence_basis == "fuzzy_supported_by_document"


def test_multiple_document_supported_sites_persists_all_strong_relationships(session):
    _make_council(session, "testcouncil")
    site_a = _make_site(session, "testcouncil", "site a")
    site_b = _make_site(session, "testcouncil", "site b")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", policy_reference="H3")
    result = _evidence_result(
        allocation.id, "testcouncil", "H3", "North Leigh Park", classification=EVIDENCE_AMBIGUOUS,
        positive_hits=[
            _hit(1, 1, site_a.id, EXPLICIT_REFERENCE),
            _hit(2, 2, site_b.id, "STRONG_CONTEXTUAL_REFERENCE"),
        ],
    )
    result.recommended_outcome = MULTIPLE_DOCUMENT_SUPPORTED_SITES

    planned, _ = plan_document_evidence_relationships([result])

    assert len(planned) == 2
    assert {p.site_id for p in planned} == {site_a.id, site_b.id}
    assert all(p.evidence_basis == "multiple_document_supported_sites" for p in planned)


# ---------------------------------------------------------------------------
# 11/12/13/14. Exclusions
# ---------------------------------------------------------------------------


def test_fuzzy_only_candidate_excluded(session):
    allocation_id = 1
    result = _evidence_result(
        allocation_id, "stockport", "HOM 2.1", "John Street, Hazel Grove", classification=HIGH_CONFIDENCE_CANDIDATE,
        positive_hits=[],
    )
    result.recommended_outcome = NO_DOCUMENT_EVIDENCE

    planned, excluded = plan_document_evidence_relationships([result])

    assert planned == []
    assert allocation_id in excluded["fuzzy_only"]


def test_weak_or_contextual_only_evidence_excluded(session):
    allocation_id = 2
    result = _evidence_result(
        allocation_id, "testcouncil", "REF1", "Allocation A", classification="NO_CANDIDATE",
        positive_hits=[_hit(1, 1, 99, "WEAK_REFERENCE")],
    )
    result.recommended_outcome = "DOCUMENT_REVIEW_REQUIRED"

    planned, excluded = plan_document_evidence_relationships([result])

    assert planned == []
    assert allocation_id in excluded["review_required"]


def test_contradicted_fuzzy_candidate_excluded(session):
    allocation_id = 3
    result = _evidence_result(
        allocation_id, "wigan", "JPA 32", "North of Mosley Common", classification=HIGH_CONFIDENCE_CANDIDATE,
    )
    result.recommended_outcome = DOCUMENT_CONTRADICTS_FUZZY

    planned, excluded = plan_document_evidence_relationships([result])

    assert planned == []
    assert allocation_id in excluded["contradicted"]


def test_application_only_evidence_excluded_from_site_relationships(session):
    allocation_id = 4
    result = _evidence_result(
        allocation_id, "stockport", "HOM 2.26", "Dairyground Farm", classification="NO_CANDIDATE",
        positive_hits=[_hit(1, 1, None, EXPLICIT_REFERENCE)],  # site_id None - Application has no Site
    )
    result.recommended_outcome = DOCUMENT_CONFIRMED_APPLICATION_ONLY

    planned, excluded = plan_document_evidence_relationships([result])

    assert planned == []  # no fake Site relationship created
    assert len(excluded["application_only"]) == 1
    assert excluded["application_only"][0]["allocation_id"] == allocation_id
    assert excluded["application_only"][0]["application_reference"] == "APP/1"


# ---------------------------------------------------------------------------
# 15. Provenance retained
# ---------------------------------------------------------------------------


def test_provenance_retained_on_document_sourced_relationship(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "some site")
    app = _make_application(session, "testcouncil", "APP/1")
    doc = _make_document(session, app.id, "planning_statement", "the application forms part of allocation ref1")
    allocation = _make_allocation(session, "testcouncil", "Allocation A")
    result = _evidence_result(
        allocation.id, "testcouncil", "REF1", "Allocation A", classification="NO_CANDIDATE",
        positive_hits=[_hit(doc.id, app.id, site.id, EXPLICIT_REFERENCE)],
    )
    result.recommended_outcome = DOCUMENT_CONFIRMED_SITE

    planned, _ = plan_document_evidence_relationships([result])

    assert planned[0].evidence_document_id == doc.id
    assert planned[0].evidence_application_id == app.id
    assert planned[0].evidence_category == EXPLICIT_REFERENCE
    assert planned[0].evidence_snippet == "evidence snippet"


def test_provenance_persisted_end_to_end_via_controlled_write(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "heald green west industrial estate testcouncil")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "officer_report", "the scheme forms part of allocation HOM 2.30 in this plan")
    allocation = _make_allocation(session, "testcouncil", "Heald Green West", policy_reference="HOM 2.30")
    session.commit()

    result = run_controlled_relationship_write(session)
    assert result["created_document_relationships"] == 1

    rel = session.execute(select(AllocationSiteRelationship)).scalar_one()
    assert rel.evidence_document_id is not None
    assert rel.evidence_application_id == app.id
    assert rel.evidence_category == EXPLICIT_REFERENCE
    assert rel.evidence_snippet is not None
    assert rel.relationship_type == "unknown_scope"


# ---------------------------------------------------------------------------
# 16/17/18. Dry-run zero-writes, confirmation required, idempotency
# ---------------------------------------------------------------------------


def test_dry_run_makes_zero_mutations(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "heald green west industrial estate testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Heald Green West", policy_reference="HOM 2.30",
                                   matched_site_id=site.id, match_confidence=100.0)
    session.commit()

    run_relationship_dry_run(session)

    assert session.execute(select(AllocationSiteRelationship)).scalars().all() == []


def test_dry_run_functions_never_call_session_add_flush_commit():
    for fn in (plan_legacy_backfill, plan_document_evidence_relationships, run_relationship_dry_run, fetch_accepted_relationships):
        source = inspect.getsource(fn)
        assert "session.add(" not in source
        assert "session.flush()" not in source
        assert "session.commit()" not in source


def test_cli_requires_explicit_confirm_phrase_before_writing():
    import scripts.dry_run_gm_allocation_site_relationships as cli

    assert cli.CONFIRM_PHRASE == "YES-CREATE-GM-ALLOCATION-SITE-RELATIONSHIPS"

    import sys
    import pytest
    old_argv = sys.argv
    try:
        sys.argv = ["prog", "--execute", "--confirm", "wrong-phrase"]
        with pytest.raises(SystemExit) as exc_info:
            cli.main()
        assert exc_info.value.code == 2
    finally:
        sys.argv = old_argv


def test_controlled_write_full_run_is_idempotent(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "heald green west industrial estate testcouncil")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "officer_report", "the scheme forms part of allocation HOM 2.30 in this plan")
    _make_allocation(session, "testcouncil", "Heald Green West", policy_reference="HOM 2.30")
    session.commit()

    first = run_controlled_relationship_write(session)
    assert first["created_document_relationships"] == 1

    second = run_controlled_relationship_write(session)
    assert second["created_document_relationships"] == 0
    assert second["already_present_skipped"] == 1

    rels = session.execute(select(AllocationSiteRelationship)).scalars().all()
    assert len(rels) == 1


# ---------------------------------------------------------------------------
# matched_site_id convenience pointer behaviour
# ---------------------------------------------------------------------------


def test_convenience_pointer_set_for_single_new_relationship(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "heald green west industrial estate testcouncil")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "officer_report", "the scheme forms part of allocation HOM 2.30 in this plan")
    allocation = _make_allocation(session, "testcouncil", "Heald Green West", policy_reference="HOM 2.30")
    session.commit()

    result = run_controlled_relationship_write(session)

    assert allocation.id in result["matched_site_id_convenience_pointer_set"]
    session.refresh(allocation)
    assert allocation.matched_site_id == site.id


def test_convenience_pointer_never_set_for_multi_site_relationship(session):
    _make_council(session, "testcouncil")
    site_a = _make_site(session, "testcouncil", "jacksons lane hazel grove stockport")
    site_b = _make_site(session, "testcouncil", "land bounded by jacksons lane hazel grove stockport")
    app_a = _make_application(session, "testcouncil", "APP/A", site_id=site_a.id)
    app_b = _make_application(session, "testcouncil", "APP/B", site_id=site_b.id)
    # Stage 2E.1 - a generic/short reference (H3) alone, even with a positive
    # relationship phrase, no longer establishes membership; the fixture must
    # also carry the allocation's own distinctive name for this to remain
    # genuine EXPLICIT_REFERENCE evidence under the corrected matcher.
    _make_document(session, app_a.id, "officer_report", "this forms part of North Leigh Park allocation H3, western parcel")
    _make_document(session, app_b.id, "officer_report", "this forms part of North Leigh Park allocation H3, eastern parcel")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", policy_reference="H3")
    session.commit()

    result = run_controlled_relationship_write(session)

    assert result["created_document_relationships"] == 2
    assert allocation.id not in result["matched_site_id_convenience_pointer_set"]
    session.refresh(allocation)
    assert allocation.matched_site_id is None  # never picks a winner


def test_convenience_pointer_never_overwrites_existing_value(session):
    _make_council(session, "testcouncil")
    existing_site = _make_site(session, "testcouncil", "existing matched site")
    other_site = _make_site(session, "testcouncil", "heald green west industrial estate testcouncil")
    app = _make_application(session, "testcouncil", "APP/1", site_id=other_site.id)
    _make_document(session, app.id, "officer_report", "the scheme forms part of allocation HOM 2.30 in this plan")
    allocation = _make_allocation(session, "testcouncil", "Heald Green West", policy_reference="HOM 2.30",
                                   matched_site_id=existing_site.id, match_confidence=100.0)
    session.commit()

    # This allocation already has matched_site_id set, so the document-
    # evidence pipeline never even evaluates it (Stage 2A/2C both scope
    # to unmatched allocations) - matched_site_id must remain untouched.
    run_controlled_relationship_write(session)

    session.refresh(allocation)
    assert allocation.matched_site_id == existing_site.id


# ---------------------------------------------------------------------------
# 19/20. No OpenAI, no unrelated schema change
# ---------------------------------------------------------------------------


def test_no_openai_dependency():
    source = inspect.getsource(relationships_module)
    assert "import openai" not in source.lower()
    assert "OpenAI(" not in source
    assert "from openai" not in source.lower()


def test_no_unrelated_schema_changes():
    # LocalPlanSite/Site must be byte-for-byte unchanged - only a new,
    # additive table (AllocationSiteRelationship) was introduced.
    expected_local_plan_site_columns = {
        "id", "council_code", "local_plan_id", "policy_reference", "site_name", "intended_use",
        "minimum_dwellings", "indicative_capacity", "maximum_capacity", "category", "allocation_status",
        "raw_allocation_status", "plan_name", "plan_status", "source_document_url", "source_page",
        "geometry_placeholder", "matched_site_id", "match_confidence", "confirmed_by", "confirmed_at",
        "match_review_note", "review_status", "duplicate_classification", "duplicate_classification_note",
        "progression_signal", "progression_reasons", "progression_computed_at", "latitude", "longitude",
        "extracted_at", "updated_at",
        # AI Allocation Intelligence Summary (Phase 1 Local Plan Intelligence) -
        # additive columns only, same grounded-numbers-then-narrate pattern as
        # LocalPlan.ai_summary_*. See app.reporting.allocation_intelligence_summary.
        "ai_summary_headline", "ai_summary_overview", "ai_summary_key_points",
        "ai_summary_key_uncertainties", "ai_summary_investigation_priorities",
        "ai_summary_generated_at", "ai_summary_context_fingerprint", "ai_summary_model",
        "ai_summary_prompt_version", "ai_summary_status", "ai_summary_generation_error",
    }
    expected_site_columns = {
        "id", "council_code", "canonical_address", "display_address", "postcode", "latitude", "longitude",
        "build_status", "build_status_checked_at", "epc_dwellings_found", "status_summary",
        "status_summary_updated_at", "excluded", "excluded_reason", "excluded_at", "first_seen_at", "updated_at",
    }
    assert {c.name for c in LocalPlanSite.__table__.columns} == expected_local_plan_site_columns
    assert {c.name for c in Site.__table__.columns} == expected_site_columns


def test_new_table_is_correctly_additive_and_unique_constrained():
    columns = {c.name for c in AllocationSiteRelationship.__table__.columns}
    expected = {
        "id", "allocation_id", "site_id", "relationship_type", "confidence", "evidence_basis",
        "evidence_category", "evidence_document_id", "evidence_application_id", "evidence_snippet",
        "review_status", "created_at",
    }
    assert columns == expected
    constraint_names = {c.name for c in AllocationSiteRelationship.__table__.constraints}
    assert "uq_allocation_site_relationship" in constraint_names


# ---------------------------------------------------------------------------
# Stage 2D evidence-semantics amendment: ALTERNATIVE_POSITIVE_SITE_EVIDENCE
# consequence - a document-confirmed Site DIFFERENT from Stage 2A's fuzzy
# candidate must still be eligible to persist (it arrives here classified
# DOCUMENT_CONFIRMED_SITE post-fix, already one of AUTO_ELIGIBLE_OUTCOMES),
# while the unsupported fuzzy candidate itself must never be invented as a
# relationship just because it was Stage 2A's guess.
# ---------------------------------------------------------------------------


def test_alternative_positive_evidence_persists_only_the_document_supported_site(session):
    _make_council(session, "testcouncil")
    fuzzy_site = _make_site(session, "testcouncil", "fuzzy guess site")
    document_site = _make_site(session, "testcouncil", "document confirmed site")
    allocation = _make_allocation(session, "testcouncil", "North of Mosley Common", policy_reference="JPA 32")
    result = _evidence_result(
        allocation.id, "testcouncil", "JPA 32", "North of Mosley Common", classification=HIGH_CONFIDENCE_CANDIDATE,
        positive_hits=[_hit(1, 1, document_site.id, EXPLICIT_REFERENCE)],
    )
    # Post-amendment: derive_recommended_outcome no longer classifies this
    # as DOCUMENT_CONTRADICTS_FUZZY - it falls through to DOCUMENT_CONFIRMED_SITE.
    result.recommended_outcome = DOCUMENT_CONFIRMED_SITE

    planned, excluded = plan_document_evidence_relationships([result])

    assert len(planned) == 1
    assert planned[0].site_id == document_site.id
    # The fuzzy-only candidate is never fabricated into a relationship -
    # it simply never appears anywhere in the planned set.
    assert not any(p.site_id == fuzzy_site.id for p in planned)
    assert all(len(v) == 0 for v in excluded.values())


def test_relationship_planning_is_deterministic_across_repeated_calls(session):
    _make_council(session, "testcouncil")
    site_a = _make_site(session, "testcouncil", "site a")
    site_b = _make_site(session, "testcouncil", "site b")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", policy_reference="H3")
    result = _evidence_result(
        allocation.id, "testcouncil", "H3", "North Leigh Park", classification=EVIDENCE_AMBIGUOUS,
        positive_hits=[
            _hit(1, 1, site_a.id, EXPLICIT_REFERENCE),
            _hit(2, 2, site_b.id, "STRONG_CONTEXTUAL_REFERENCE"),
        ],
    )
    result.recommended_outcome = MULTIPLE_DOCUMENT_SUPPORTED_SITES

    first_planned, first_excluded = plan_document_evidence_relationships([result])
    second_planned, second_excluded = plan_document_evidence_relationships([result])

    assert [(p.allocation_id, p.site_id, p.evidence_basis) for p in first_planned] == \
        [(p.allocation_id, p.site_id, p.evidence_basis) for p in second_planned]
    assert first_excluded == second_excluded
