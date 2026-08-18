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
    apply_historical_scan_state_backfill,
    backfill_historical_scan_state,
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
# 1/2/3 (amendment). Strong evidence auto-creates through Stage 2D logic /
# weak evidence never auto-writes
# ---------------------------------------------------------------------------


def test_strong_evidence_auto_creates_relationship_through_stage_2d_logic(session):
    """Final pre-merge amendment Section 1: strong DOCUMENT_CONFIRMED_SITE-
    class evidence now auto-creates the AllocationSiteRelationship, via
    the SAME shared Stage 2D persistence helper - reusing exact provenance
    semantics (evidence_basis/category/document/application/snippet,
    unknown_scope, idempotent pair, auto_applied review_status)."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    site = _make_site(session, "testcouncil", "some site")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    doc = _make_document(session, app.id, "planning_statement", "This forms part of allocation HOM 2.30.")
    session.commit()

    report = scan_council_for_allocation_evidence(session, "testcouncil")

    rels = session.execute(select(AllocationSiteRelationship)).scalars().all()
    assert len(rels) == 1
    rel = rels[0]
    assert rel.allocation_id == allocation.id
    assert rel.site_id == site.id
    assert rel.evidence_basis == "document_confirmed_site"
    assert rel.relationship_type == "unknown_scope"
    assert rel.review_status == "auto_applied"
    assert rel.evidence_document_id == doc.id
    assert rel.evidence_application_id == app.id
    assert rel.evidence_snippet is not None
    assert rel.confidence is None  # Stage 2C hits carry no numeric score - never invented

    assert len(report.new_strong_candidates) == 1
    assert report.new_strong_candidates[0].relationship_id == rel.id


def test_duplicate_strong_evidence_is_idempotent(session):
    """Two documents in the SAME scan naming the same new (allocation,
    Site) pair must produce exactly one relationship, never two."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    site = _make_site(session, "testcouncil", "some site")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "planning_statement", "This forms part of allocation HOM 2.30.")
    _make_document(session, app.id, "officer_report", "The scheme lies within allocation HOM 2.30.")
    session.commit()

    scan_council_for_allocation_evidence(session, "testcouncil")

    rels = session.execute(select(AllocationSiteRelationship)).scalars().all()
    assert len(rels) == 1


def test_existing_human_confirmed_relationship_not_weakened_by_new_strong_evidence(session):
    """A pre-existing, human-confirmed relationship for this exact pair
    must never be touched (not duplicated, not downgraded, not its
    provenance overwritten) when new strong evidence for the SAME pair is
    found - create_relationship_if_absent is a pure no-op here."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    site = _make_site(session, "testcouncil", "some site")
    existing = _make_relationship(
        session, allocation.id, site.id, review_status="confirmed", confidence=99.0,
        evidence_snippet="original human-confirmed snippet",
    )
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "planning_statement", "This forms part of allocation HOM 2.30.")
    session.commit()

    scan_council_for_allocation_evidence(session, "testcouncil")

    rels = session.execute(select(AllocationSiteRelationship)).scalars().all()
    assert len(rels) == 1
    assert rels[0].id == existing.id
    assert rels[0].review_status == "confirmed"
    assert rels[0].confidence == 99.0
    assert rels[0].evidence_snippet == "original human-confirmed snippet"


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


def test_module_creates_relationships_only_through_the_shared_helper_never_directly():
    """'Do not create a second direct-write path' - confirmed structurally:
    this module never constructs AllocationSiteRelationship() itself; the
    one place that ever happens is app.policy.allocation_site_
    relationships.create_relationship_if_absent, called (not duplicated)
    from here."""
    source = inspect.getsource(scan_module)
    assert "AllocationSiteRelationship(" not in source
    assert "create_relationship_if_absent(" in source


# ---------------------------------------------------------------------------
# Final auto-link evidence threshold amendment: STRONG_CONTEXTUAL_REFERENCE
# alone is review-only in the unattended forward pipeline - only
# EXPLICIT_REFERENCE auto-creates. Historical/batch semantics unchanged.
# ---------------------------------------------------------------------------


def test_strong_contextual_reference_alone_does_not_auto_create_relationship(session):
    """A bare mention of the allocation's reference with no explicit
    membership phrase nearby (STRONG_CONTEXTUAL_REFERENCE) must NEVER
    auto-create a relationship in the unattended forward pipeline, even
    though it is one of Stage 2C's own two 'strong' categories."""
    _make_council(session, "testcouncil")
    _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    site = _make_site(session, "testcouncil", "some site")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(
        session, app.id, "officer_report",
        "The trajectory table records progress against allocation HOM 2.30 as due for "
        "delivery in year three of the plan period, alongside twelve other sites monitored "
        "across the borough this year.",
    )
    session.commit()

    report = scan_council_for_allocation_evidence(session, "testcouncil")

    assert report.new_strong_candidates == []
    assert session.execute(select(AllocationSiteRelationship)).scalars().all() == []


def test_strong_contextual_reference_retained_and_reported_for_review(session):
    """The same hit is not silently dropped - it is reported into
    report.weak_evidence, carrying its TRUE category (never downgraded to
    WEAK_REFERENCE/NAME_AND_POLICY_CONTEXT) and its resolved Site, for
    later human review or the deliberate batch/historical process."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    site = _make_site(session, "testcouncil", "some site")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    doc = _make_document(
        session, app.id, "officer_report",
        "The trajectory table records progress against allocation HOM 2.30 as due for "
        "delivery in year three of the plan period, alongside twelve other sites monitored "
        "across the borough this year.",
    )
    session.commit()

    report = scan_council_for_allocation_evidence(session, "testcouncil")

    assert len(report.weak_evidence) == 1
    hit = report.weak_evidence[0]
    assert hit.category == "STRONG_CONTEXTUAL_REFERENCE"
    assert hit.allocation_id == allocation.id
    assert hit.site_id == site.id
    assert hit.document_id == doc.id
    assert hit.application_id == app.id
    assert hit.snippet


def test_explicit_reference_beats_contextual_for_same_site_same_document(session):
    """If a document carries BOTH an EXPLICIT_REFERENCE hit and a
    STRONG_CONTEXTUAL_REFERENCE hit for the same allocation/Site pair, the
    explicit hit wins and the relationship IS auto-created - the
    contextual mention alone never suppresses a genuine explicit one."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    site = _make_site(session, "testcouncil", "some site")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(
        session, app.id, "planning_statement",
        "The trajectory table records progress against allocation HOM 2.30 in the annual "
        "monitoring report. This application forms part of allocation HOM 2.30 and delivers "
        "the housing identified for the site.",
    )
    session.commit()

    report = scan_council_for_allocation_evidence(session, "testcouncil")

    rels = session.execute(select(AllocationSiteRelationship)).scalars().all()
    assert len(rels) == 1
    assert rels[0].allocation_id == allocation.id
    assert rels[0].site_id == site.id
    assert len(report.new_strong_candidates) == 1
    assert report.new_strong_candidates[0].category == "EXPLICIT_REFERENCE"


def test_repeated_strong_contextual_evidence_never_accumulates_into_auto_create(session):
    """Two separate documents in the SAME scan, each only carrying
    STRONG_CONTEXTUAL_REFERENCE evidence for the same new (allocation,
    Site) pair, must still create ZERO relationships - repetition alone
    never upgrades contextual evidence into an accepted relationship."""
    _make_council(session, "testcouncil")
    _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    site = _make_site(session, "testcouncil", "some site")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(
        session, app.id, "officer_report",
        "The trajectory table records progress against allocation HOM 2.30 as due for "
        "delivery in year three of the plan period.",
    )
    _make_document(
        session, app.id, "design_access",
        "The annual monitoring report references allocation HOM 2.30 in its summary table "
        "of sites under review this year.",
    )
    session.commit()

    report = scan_council_for_allocation_evidence(session, "testcouncil")

    assert session.execute(select(AllocationSiteRelationship)).scalars().all() == []
    assert report.new_strong_candidates == []
    assert len(report.weak_evidence) == 2
    assert all(h.category == "STRONG_CONTEXTUAL_REFERENCE" for h in report.weak_evidence)


def test_historical_batch_eligibility_for_strong_contextual_reference_not_weakened():
    """This amendment concerns ONLY unattended forward automatic
    persistence (app.policy.allocation_evidence_scan). The deliberate
    batch/historical mechanism in app.policy.allocation_site_relationships
    (plan_document_evidence_relationships) must still treat
    STRONG_CONTEXTUAL_REFERENCE as strong evidence eligible to combine
    with fuzzy/multi-document/human-review context - confirmed
    structurally unchanged."""
    from app.policy import allocation_site_relationships as batch_module

    source = inspect.getsource(batch_module.plan_document_evidence_relationships)
    assert '"EXPLICIT_REFERENCE", "STRONG_CONTEXTUAL_REFERENCE"' in source


def test_auto_create_categories_is_explicit_reference_only():
    """Structural guard on the amendment itself - the forward pipeline's
    own auto-create eligibility set must be exactly {EXPLICIT_REFERENCE},
    never silently widened back to include STRONG_CONTEXTUAL_REFERENCE."""
    assert scan_module._AUTO_CREATE_CATEGORIES == ("EXPLICIT_REFERENCE",)


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
    # Stage 2E.1 - a generic/short reference (H3) alone, even with a positive
    # relationship phrase, no longer establishes membership; the fixture must
    # also carry the allocation's own distinctive name for this to remain
    # genuine EXPLICIT_REFERENCE evidence under the corrected matcher.
    _make_document(session, app_a.id, "planning_statement", "This forms part of allocation H3, North Leigh Park, western parcel.")
    _make_document(session, app_b.id, "planning_statement", "This forms part of allocation H3, North Leigh Park, eastern parcel.")
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


# ---------------------------------------------------------------------------
# Final pre-merge amendment Section 7: historical scan-state cutover
# ---------------------------------------------------------------------------


def test_historical_cutover_dry_run_finds_pre_cutoff_documents(session):
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    old_doc = Document(
        application_id=app.id, doc_type="planning_statement", extracted_text="old text",
        text_extracted=True, downloaded_at=dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc),
    )
    session.add(old_doc)
    session.commit()

    cutoff = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
    plan = backfill_historical_scan_state(session, cutoff=cutoff)

    assert plan["count"] == 1
    assert old_doc.id in plan["eligible_document_ids"]
    # Dry run - zero mutations.
    session.refresh(old_doc)
    assert old_doc.allocation_evidence_scanned_at is None


def test_historical_cutover_excludes_documents_downloaded_after_cutoff(session):
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    cutoff = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
    new_doc = Document(
        application_id=app.id, doc_type="planning_statement", extracted_text="new text",
        text_extracted=True, downloaded_at=dt.datetime(2026, 6, 15, tzinfo=dt.timezone.utc),
    )
    session.add(new_doc)
    session.commit()

    plan = backfill_historical_scan_state(session, cutoff=cutoff)
    assert plan["count"] == 0


def test_historical_cutover_includes_documents_with_no_downloaded_at(session):
    """A legacy row with no download timestamp cannot be proven to
    postdate the cutover - treated as pre-cutover (the safe direction)."""
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    legacy_doc = Document(
        application_id=app.id, doc_type="planning_statement", extracted_text="legacy text",
        text_extracted=True, downloaded_at=None,
    )
    session.add(legacy_doc)
    session.commit()

    plan = backfill_historical_scan_state(session)
    assert legacy_doc.id in plan["eligible_document_ids"]


def test_historical_cutover_apply_marks_documents_scanned(session):
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    doc = Document(
        application_id=app.id, doc_type="planning_statement", extracted_text="old text",
        text_extracted=True, downloaded_at=dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc),
    )
    session.add(doc)
    session.commit()

    cutoff = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
    result = apply_historical_scan_state_backfill(session, cutoff=cutoff)

    assert result["marked_count"] == 1
    session.refresh(doc)
    # SQLite doesn't round-trip tzinfo on DateTime columns - compare the
    # naive value, which is what matters here (the real Postgres column
    # is timezone-aware; this is purely a test-fixture storage quirk).
    assert doc.allocation_evidence_scanned_at.replace(tzinfo=None) == cutoff.replace(tzinfo=None)


def test_historical_cutover_apply_is_idempotent(session):
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    doc = Document(
        application_id=app.id, doc_type="planning_statement", extracted_text="old text",
        text_extracted=True, downloaded_at=dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc),
    )
    session.add(doc)
    session.commit()

    cutoff = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
    first = apply_historical_scan_state_backfill(session, cutoff=cutoff)
    second = apply_historical_scan_state_backfill(session, cutoff=cutoff)

    assert first["marked_count"] == 1
    assert second["marked_count"] == 0


def test_previously_backfilled_historical_document_not_rescanned_by_normal_run(session):
    """The whole point of the cutover: after backfill, a normal
    scan_council_for_allocation_evidence run does NOT touch the
    already-covered historical corpus."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    site = _make_site(session, "testcouncil", "some site")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    historical_doc = Document(
        application_id=app.id, doc_type="planning_statement",
        extracted_text="This forms part of allocation HOM 2.30.", text_extracted=True,
        downloaded_at=dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc),
    )
    session.add(historical_doc)
    session.commit()

    cutoff = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
    apply_historical_scan_state_backfill(session, cutoff=cutoff)

    report = scan_council_for_allocation_evidence(session, "testcouncil")
    assert report.documents_scanned == 0
    # Confirmed: no relationship was created either - the historical
    # document was never re-evaluated, exactly as intended (it was
    # already covered by Stage 2C's own historical pass).
    assert session.execute(select(AllocationSiteRelationship)).scalars().all() == []


def test_genuinely_new_document_after_cutover_still_scanned_normally(session):
    """A document extracted AFTER the cutover (downloaded_at post-dates
    it) is never touched by the backfill, and remains eligible for the
    normal incremental scan."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    site = _make_site(session, "testcouncil", "some site")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)

    cutoff = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
    historical_doc = Document(
        application_id=app.id, doc_type="planning_statement", extracted_text="old, unrelated text",
        text_extracted=True, downloaded_at=dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc),
    )
    session.add(historical_doc)
    new_doc = Document(
        application_id=app.id, doc_type="officer_report",
        extracted_text="This forms part of allocation HOM 2.30.", text_extracted=True,
        downloaded_at=dt.datetime(2026, 6, 15, tzinfo=dt.timezone.utc),
    )
    session.add(new_doc)
    session.commit()

    apply_historical_scan_state_backfill(session, cutoff=cutoff)

    report = scan_council_for_allocation_evidence(session, "testcouncil")
    assert report.documents_scanned == 1
    rels = session.execute(select(AllocationSiteRelationship)).scalars().all()
    assert len(rels) == 1
    assert rels[0].evidence_document_id == new_doc.id


def test_historical_cutover_no_openai():
    source = inspect.getsource(backfill_historical_scan_state) + inspect.getsource(apply_historical_scan_state_backfill)
    assert "openai" not in source.lower()


# ---------------------------------------------------------------------------
# Section 10/17: a newly auto-created relationship appears in Stage 3A
# coverage immediately, with no separate refresh/regeneration job.
# ---------------------------------------------------------------------------


def test_new_relationship_reflected_in_stage_3a_coverage_with_no_refresh_job(session):
    from app.reporting.allocation_development_coverage import PARTIAL_COVERAGE, build_allocation_development_coverage

    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Sanderling Road", "HOM 2.30")
    allocation.minimum_dwellings = 1000
    site = _make_site(session, "testcouncil", "some site")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "planning_statement", "This forms part of allocation HOM 2.30.")
    session.commit()

    # Before the scan: no relationship, NO_IDENTIFIED_ACTIVITY.
    from app.db.models import SchemeIntelligence
    before = build_allocation_development_coverage(session, [allocation])
    assert before[allocation.id]["coverage"].number_of_related_sites == 0

    session.add(SchemeIntelligence(application_id=app.id, total_units_final=300, core_intelligence_complete=True))
    session.commit()

    scan_council_for_allocation_evidence(session, "testcouncil")

    # No refresh/regeneration call of any kind in between - coverage is
    # simply re-derived on the next read.
    after = build_allocation_development_coverage(session, [allocation])
    coverage = after[allocation.id]["coverage"]
    assert coverage.number_of_related_sites == 1
    assert coverage.identified_application_capacity == 300
    assert coverage.development_coverage_classification == PARTIAL_COVERAGE
