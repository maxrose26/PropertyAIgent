"""Forward Allocation-Reference Evidence Scan tests (Stage 3B). Every test
runs against the shared in-memory SQLite `session` fixture (tests/
conftest.py) - never the real production database.
"""
from __future__ import annotations

import datetime as dt
import inspect

from sqlalchemy import select

from app.db.models import AllocationSiteRelationship, Application, Council, Document, LocalPlanSite, Site
from app.policy import allocation_evidence_scan as scan_module
from app.policy.allocation_evidence_scan import (
    ALLOCATION_EVIDENCE_SCAN_RUN_LIMIT,
    scan_council_for_allocation_evidence,
    select_unscanned_documents,
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


def _make_allocation(session, council_code: str, site_name: str, policy_reference: str) -> LocalPlanSite:
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


def _make_document(session, application_id: int, doc_type: str, text: str, *, scanned=False) -> Document:
    doc = Document(
        application_id=application_id, doc_type=doc_type, extracted_text=text, text_extracted=True,
        allocation_evidence_scanned_at=None if not scanned else dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
    )
    session.add(doc)
    session.flush()
    return doc


def _make_relationship(session, allocation_id: int, site_id: int, **kwargs) -> AllocationSiteRelationship:
    rel = AllocationSiteRelationship(
        allocation_id=allocation_id, site_id=site_id, evidence_basis=kwargs.pop("evidence_basis", "document_confirmed_site"),
        **kwargs,
    )
    session.add(rel)
    session.flush()
    return rel


# ---------------------------------------------------------------------------
# 1/2/18. Scan-state / idempotent document selection
# ---------------------------------------------------------------------------


def test_newly_extracted_document_is_scanned(session):
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    _make_document(session, app.id, "planning_statement", "some text")
    session.commit()

    docs = select_unscanned_documents(session, "testcouncil")
    assert len(docs) == 1


def test_already_scanned_document_is_not_reselected(session):
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    _make_document(session, app.id, "planning_statement", "some text", scanned=True)
    session.commit()

    docs = select_unscanned_documents(session, "testcouncil")
    assert docs == []


def test_repeated_run_scans_nothing_the_second_time(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    app = _make_application(session, "testcouncil", "APP/1")
    _make_document(session, app.id, "planning_statement", "This forms part of allocation HOM 2.30.")
    session.commit()

    first = scan_council_for_allocation_evidence(session, "testcouncil")
    assert first.documents_scanned == 1

    second = scan_council_for_allocation_evidence(session, "testcouncil")
    assert second.documents_scanned == 0
    assert select_unscanned_documents(session, "testcouncil") == []


def test_no_historical_full_corpus_rescan_on_normal_run(session):
    """Bounded per-run limit exists and documents already flagged
    allocation_evidence_scanned_at are structurally excluded from the
    query - a normal run never re-touches the full historical corpus."""
    assert ALLOCATION_EVIDENCE_SCAN_RUN_LIMIT > 0
    source = inspect.getsource(select_unscanned_documents)
    assert "allocation_evidence_scanned_at.is_(None)" in source
    assert "limit" in source.lower()


# ---------------------------------------------------------------------------
# 3/4. Exact allocation reference / explicit relationship language
# ---------------------------------------------------------------------------


def test_exact_allocation_reference_found(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    site = _make_site(session, "testcouncil", "some site")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "planning_statement", "This forms part of allocation HOM 2.30.")
    session.commit()

    report = scan_council_for_allocation_evidence(session, "testcouncil")

    assert report.documents_scanned == 1
    assert len(report.new_strong_candidates) == 1
    hit = report.new_strong_candidates[0]
    assert hit.allocation_id == allocation.id
    assert hit.site_id == site.id
    assert hit.application_reference == "APP/1"
    assert "HOM 2.30" in hit.snippet or "hom 2.30" in hit.snippet.lower()


def test_explicit_relationship_language_found(session):
    _make_council(session, "testcouncil")
    _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    site = _make_site(session, "testcouncil", "some site")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "officer_report", "The site lies within allocation HOM 2.30 as identified in the Local Plan.")
    session.commit()

    report = scan_council_for_allocation_evidence(session, "testcouncil")
    assert len(report.new_strong_candidates) == 1
    assert report.new_strong_candidates[0].category == "EXPLICIT_REFERENCE"


# ---------------------------------------------------------------------------
# 5. Short-reference false positive prevented
# ---------------------------------------------------------------------------


def test_short_reference_false_positive_prevented(session):
    """A bare short reference like 'H3' with no 'policy'/'allocation'
    prefix must never match - reuses Stage 2C's own GENERIC_REFERENCE_
    MAX_LENGTH safeguard unmodified."""
    _make_council(session, "testcouncil")
    _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    site = _make_site(session, "testcouncil", "some site")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "planning_statement", "The scheme is located near H3 junction of the motorway.")
    session.commit()

    report = scan_council_for_allocation_evidence(session, "testcouncil")
    assert report.new_strong_candidates == []
    assert report.weak_evidence == []


# ---------------------------------------------------------------------------
# 6. Negative/adjacency evidence handled safely
# ---------------------------------------------------------------------------


def test_negative_adjacency_evidence_never_creates_positive_candidate(session):
    _make_council(session, "testcouncil")
    _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    site = _make_site(session, "testcouncil", "some site")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "officer_report", "This site is outside allocation HOM 2.30 and unaffected by it.")
    session.commit()

    report = scan_council_for_allocation_evidence(session, "testcouncil")
    assert report.new_strong_candidates == []
    assert report.contradictions_flagged == []  # no existing relationship to contradict


def test_negative_adjacency_flags_existing_relationship_for_review(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    site = _make_site(session, "testcouncil", "some site")
    rel = _make_relationship(session, allocation.id, site.id, review_status="auto_applied")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "officer_report", "This site is outside allocation HOM 2.30 and unaffected by it.")
    session.commit()

    report = scan_council_for_allocation_evidence(session, "testcouncil")

    assert len(report.contradictions_flagged) == 1
    flag = report.contradictions_flagged[0]
    assert flag.relationship_id == rel.id
    assert flag.previous_review_status == "auto_applied"

    session.refresh(rel)
    assert rel.review_status == "needs_confirmation"


# ---------------------------------------------------------------------------
# 7/8. Strong evidence reported (never auto-written) / weak never auto-writes
# ---------------------------------------------------------------------------


def test_strong_evidence_never_creates_a_relationship_row(session):
    _make_council(session, "testcouncil")
    _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    site = _make_site(session, "testcouncil", "some site")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "planning_statement", "This forms part of allocation HOM 2.30.")
    session.commit()

    scan_council_for_allocation_evidence(session, "testcouncil")

    assert session.execute(select(AllocationSiteRelationship)).scalars().all() == []


def test_weak_contextual_evidence_never_auto_writes_and_is_reported(session):
    _make_council(session, "testcouncil")
    _make_allocation(session, "testcouncil", "Grey Mare Lane", None)
    site = _make_site(session, "testcouncil", "some site")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "application_form", "The proposal is located at Grey Mare Lane, Manchester.")
    session.commit()

    report = scan_council_for_allocation_evidence(session, "testcouncil")

    assert report.new_strong_candidates == []
    assert len(report.weak_evidence) == 1
    assert session.execute(select(AllocationSiteRelationship)).scalars().all() == []


def test_module_makes_no_relationship_creation_writes():
    source = inspect.getsource(scan_module)
    assert "AllocationSiteRelationship(" not in source


# ---------------------------------------------------------------------------
# 9. Multi-Site evidence preserved
# ---------------------------------------------------------------------------


def test_multi_site_evidence_preserved_separately(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    site_a = _make_site(session, "testcouncil", "site a")
    site_b = _make_site(session, "testcouncil", "site b")
    app_a = _make_application(session, "testcouncil", "APP/A", site_id=site_a.id)
    app_b = _make_application(session, "testcouncil", "APP/B", site_id=site_b.id)
    _make_document(session, app_a.id, "planning_statement", "This forms part of allocation H3, western parcel.")
    _make_document(session, app_b.id, "planning_statement", "This forms part of allocation H3, eastern parcel.")
    session.commit()

    report = scan_council_for_allocation_evidence(session, "testcouncil")

    site_ids_found = {c.site_id for c in report.new_strong_candidates}
    assert site_ids_found == {site_a.id, site_b.id}
    assert all(c.allocation_id == allocation.id for c in report.new_strong_candidates)


# ---------------------------------------------------------------------------
# 10. Application-only evidence preserved without fake Site
# ---------------------------------------------------------------------------


def test_application_only_evidence_preserved_without_fake_site(session):
    _make_council(session, "testcouncil")
    _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    app = _make_application(session, "testcouncil", "APP/1", site_id=None)  # no linked Site
    _make_document(session, app.id, "planning_statement", "This forms part of allocation HOM 2.30.")
    session.commit()

    report = scan_council_for_allocation_evidence(session, "testcouncil")

    assert report.new_strong_candidates == []
    assert len(report.application_only_evidence) == 1
    assert report.application_only_evidence[0].application_reference == "APP/1"
    assert session.execute(select(AllocationSiteRelationship)).scalars().all() == []


# ---------------------------------------------------------------------------
# 11/12/13. Existing relationship not duplicated / not overwritten / no auto-delete
# ---------------------------------------------------------------------------


def test_existing_relationship_not_reported_as_new_candidate(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    site = _make_site(session, "testcouncil", "some site")
    _make_relationship(session, allocation.id, site.id)
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "planning_statement", "This forms part of allocation HOM 2.30.")
    session.commit()

    report = scan_council_for_allocation_evidence(session, "testcouncil")
    assert report.new_strong_candidates == []  # already accepted, not "new"


def test_human_confirmed_relationship_provenance_not_overwritten_by_contradiction(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    site = _make_site(session, "testcouncil", "some site")
    rel = _make_relationship(
        session, allocation.id, site.id, review_status="confirmed", evidence_basis="document_confirmed_site",
        confidence=95.0, evidence_snippet="original confirmed snippet",
    )
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "officer_report", "This site is outside allocation HOM 2.30 and unaffected by it.")
    session.commit()

    scan_council_for_allocation_evidence(session, "testcouncil")

    session.refresh(rel)
    assert rel.review_status == "needs_confirmation"  # flagged...
    # ...but every other field of the original confirmed evidence is untouched.
    assert rel.evidence_basis == "document_confirmed_site"
    assert rel.confidence == 95.0
    assert rel.evidence_snippet == "original confirmed snippet"
    assert rel.site_id == site.id
    assert rel.allocation_id == allocation.id


def test_contradiction_never_deletes_the_relationship_row(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    site = _make_site(session, "testcouncil", "some site")
    rel = _make_relationship(session, allocation.id, site.id)
    rel_id = rel.id
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "officer_report", "This site is outside allocation HOM 2.30 and unaffected by it.")
    session.commit()

    scan_council_for_allocation_evidence(session, "testcouncil")

    assert session.get(AllocationSiteRelationship, rel_id) is not None


def test_contradiction_flag_is_idempotent_not_reflagged_every_run(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    site = _make_site(session, "testcouncil", "some site")
    _make_relationship(session, allocation.id, site.id)
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "officer_report", "This site is outside allocation HOM 2.30 and unaffected by it.")
    session.commit()

    first = scan_council_for_allocation_evidence(session, "testcouncil")
    assert len(first.contradictions_flagged) == 1

    # A second document with the same contradiction, on an already-flagged relationship.
    _make_document(session, app.id, "planning_statement", "This site is outside allocation HOM 2.30 and unaffected by it.")
    session.commit()
    second = scan_council_for_allocation_evidence(session, "testcouncil")
    assert second.contradictions_flagged == []  # already needs_confirmation - not re-flagged/re-logged


# ---------------------------------------------------------------------------
# 14. Repeated run idempotent (end-to-end)
# ---------------------------------------------------------------------------


def test_repeated_run_produces_no_duplicate_candidates_or_flags(session):
    _make_council(session, "testcouncil")
    _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    site = _make_site(session, "testcouncil", "some site")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "planning_statement", "This forms part of allocation HOM 2.30.")
    session.commit()

    first = scan_council_for_allocation_evidence(session, "testcouncil")
    second = scan_council_for_allocation_evidence(session, "testcouncil")

    assert len(first.new_strong_candidates) == 1
    assert len(second.new_strong_candidates) == 0  # document already scanned, not reprocessed


# ---------------------------------------------------------------------------
# 15. One-document failure isolated
# ---------------------------------------------------------------------------


def test_one_document_failure_does_not_abort_the_batch(session, monkeypatch):
    _make_council(session, "testcouncil")
    _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    site = _make_site(session, "testcouncil", "some site")
    app1 = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    app2 = _make_application(session, "testcouncil", "APP/2", site_id=site.id)
    bad_doc = _make_document(session, app1.id, "planning_statement", "This forms part of allocation HOM 2.30.")
    good_doc = _make_document(session, app2.id, "planning_statement", "This forms part of allocation HOM 2.30.")
    session.commit()

    original = scan_module.find_allocation_evidence_for_document

    def flaky(document, application, allocations):
        if document.id == bad_doc.id:
            raise RuntimeError("simulated processing failure")
        return original(document, application, allocations)

    monkeypatch.setattr(scan_module, "find_allocation_evidence_for_document", flaky)

    report = scan_council_for_allocation_evidence(session, "testcouncil")

    assert report.documents_failed == 1
    assert report.documents_scanned == 1
    # The failing document stays unscanned (eligible for retry); the good one doesn't.
    session.refresh(bad_doc)
    session.refresh(good_doc)
    assert bad_doc.allocation_evidence_scanned_at is None
    assert good_doc.allocation_evidence_scanned_at is not None


# ---------------------------------------------------------------------------
# 16/17. No OpenAI, no external API
# ---------------------------------------------------------------------------


def test_no_openai_or_external_api_dependency():
    """Checks actual imports/calls, not the module's own prose docstring
    (which legitimately discusses OpenAI while explaining it is never
    used)."""
    source = inspect.getsource(scan_module)
    assert "import openai" not in source.lower()
    assert "OpenAI(" not in source
    assert "from openai" not in source.lower()
    assert "requests." not in source
    assert "playwright" not in source.lower()


# ---------------------------------------------------------------------------
# 19. Stage 3A compatibility
# ---------------------------------------------------------------------------


def test_stage_3a_coverage_engine_still_works_after_contradiction_flag(session):
    from app.reporting.allocation_development_coverage import build_allocation_development_coverage

    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    allocation.minimum_dwellings = 500
    site = _make_site(session, "testcouncil", "some site")
    _make_relationship(session, allocation.id, site.id)
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "officer_report", "This site is outside allocation HOM 2.30 and unaffected by it.")
    session.commit()

    scan_council_for_allocation_evidence(session, "testcouncil")

    # A relationship flagged needs_confirmation is still a real, existing
    # AllocationSiteRelationship row - Stage 3A's coverage engine reads
    # every relationship regardless of review_status (it is not a Stage
    # 2A-style pending-candidate queue), so coverage computation must not
    # crash or silently drop it.
    result = build_allocation_development_coverage(session, [allocation])
    assert result[allocation.id]["coverage"].number_of_related_sites == 1


# ---------------------------------------------------------------------------
# 20. No unrelated schema change
# ---------------------------------------------------------------------------


def test_only_the_one_new_document_column_added():
    expected_document_columns = {
        "id", "application_id", "doc_type", "document_name", "source_url", "local_path",
        "text_extracted", "extracted_text", "downloaded_at", "allocation_evidence_scanned_at",
    }
    assert {c.name for c in Document.__table__.columns} == expected_document_columns


# ---------------------------------------------------------------------------
# 13 (run_weekly.py wiring). Thin pipeline-stage wrapper, separately callable/testable
# ---------------------------------------------------------------------------


def test_stage_allocation_evidence_scan_wrapper_delegates_correctly(session):
    from app.config import CouncilConfig
    from app.pipeline.run_weekly import stage_allocation_evidence_scan

    council = CouncilConfig(
        code="testcouncil", name="testcouncil", base_url="https://example.invalid",
        date_field_mode="received", doc_system="idox", anite_base_url=None,
        unit_threshold=10, region=None, country=None,
    )
    _make_council(session, "testcouncil")
    _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    site = _make_site(session, "testcouncil", "some site")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "planning_statement", "This forms part of allocation HOM 2.30.")
    session.commit()

    scanned_count = stage_allocation_evidence_scan(session, council)

    assert scanned_count == 1
    assert select_unscanned_documents(session, "testcouncil") == []


def test_run_weekly_orchestration_is_thin():
    """Section 13: 'do not place complex logic directly in run_weekly.py' -
    the stage function must delegate, not reimplement, the scan."""
    from app.pipeline.run_weekly import stage_allocation_evidence_scan
    source = inspect.getsource(stage_allocation_evidence_scan)
    assert "scan_council_for_allocation_evidence(" in source
    # A handful of print/report lines only - no query/regex logic of its own.
    assert "select(" not in source
    assert "find_allocation_evidence_for_document(" not in source
