"""Allocation Development Coverage + Opportunity Intelligence tests
(Stage 3A). Every test runs against the shared in-memory SQLite `session`
fixture (tests/conftest.py) - never the real production database.
"""
from __future__ import annotations

import inspect

from app.db.models import (
    AllocationSiteRelationship, Application, Council, Document, LocalPlanSite, SchemeIntelligence, Site,
)
from app.reporting import allocation_development_coverage as coverage_module
from app.reporting.allocation_development_coverage import (
    CAPACITY_UNKNOWN,
    CONFIRMED_PHASED,
    DISPUTED_RELATIONSHIP_NOTE,
    FULLY_ACCOUNTED_FOR,
    INSUFFICIENT_EVIDENCE,
    INVESTIGATE,
    LOWER_PRIORITY,
    MONITOR,
    NO_IDENTIFIED_ACTIVITY,
    NO_PHASING_EVIDENCE,
    OWNERSHIP_CAVEAT,
    PARTIAL_COVERAGE,
    PHASING_REVIEW_REQUIRED,
    POTENTIAL_PHASED,
    REVIEW_REQUIRED,
    SUBSTANTIALLY_COVERED,
    build_allocation_development_coverage,
    build_opportunity_signal,
    classify_phasing,
    compute_development_coverage,
    search_phasing_evidence,
    summarise_site_activity,
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


def _make_allocation(session, council_code: str, site_name: str, *, policy_reference: str = "REF1",
                      minimum_dwellings: int | None = None) -> LocalPlanSite:
    allocation = LocalPlanSite(
        council_code=council_code, policy_reference=policy_reference, site_name=site_name,
        minimum_dwellings=minimum_dwellings, plan_name="Test Local Plan", plan_status="adopted",
    )
    session.add(allocation)
    session.flush()
    return allocation


def _make_application(session, council_code: str, reference: str, site_id: int | None = None,
                       *, estimated_unit_count: int | None = None, received: str | None = "01/01/2025") -> Application:
    app = Application(
        council_code=council_code, reference=reference, site_id=site_id,
        estimated_unit_count=estimated_unit_count, application_received=received,
    )
    session.add(app)
    session.flush()
    return app


def _make_scheme_intelligence(session, application_id: int, *, total_units_final: int | None,
                               core_intelligence_complete: bool = True) -> SchemeIntelligence:
    si = SchemeIntelligence(
        application_id=application_id, total_units_final=total_units_final,
        core_intelligence_complete=core_intelligence_complete,
    )
    session.add(si)
    session.flush()
    return si


def _make_document(session, application_id: int, doc_type: str, text: str) -> Document:
    doc = Document(application_id=application_id, doc_type=doc_type, extracted_text=text, text_extracted=True)
    session.add(doc)
    session.flush()
    return doc


def _make_relationship(session, allocation_id: int, site_id: int, **kwargs) -> AllocationSiteRelationship:
    rel = AllocationSiteRelationship(
        allocation_id=allocation_id, site_id=site_id,
        evidence_basis=kwargs.pop("evidence_basis", "document_confirmed_site"), **kwargs,
    )
    session.add(rel)
    session.flush()
    return rel


# ---------------------------------------------------------------------------
# AllocationSiteRelationship is authoritative
# ---------------------------------------------------------------------------


def test_matched_site_id_alone_is_never_used_as_relationship_source(session):
    _make_council(session, "testcouncil")
    matched_only_site = _make_site(session, "testcouncil", "some site")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=100)
    allocation.matched_site_id = matched_only_site.id  # legacy pointer only, NO AllocationSiteRelationship row
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])

    coverage = result[allocation.id]["coverage"]
    assert coverage.number_of_related_sites == 0
    assert coverage.development_coverage_classification == NO_IDENTIFIED_ACTIVITY


def test_allocation_site_relationship_drives_related_sites(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "some site")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=100)
    _make_relationship(session, allocation.id, site.id)
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    coverage = result[allocation.id]["coverage"]
    assert coverage.number_of_related_sites == 1


# ---------------------------------------------------------------------------
# Multi-Site allocation handling
# ---------------------------------------------------------------------------


def test_multi_site_allocation_aggregates_across_distinct_sites(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", policy_reference="H3", minimum_dwellings=500)
    site_a = _make_site(session, "testcouncil", "site a")
    site_b = _make_site(session, "testcouncil", "site b")
    site_c = _make_site(session, "testcouncil", "site c - no activity")
    for site in (site_a, site_b, site_c):
        _make_relationship(session, allocation.id, site.id)

    app_a = _make_application(session, "testcouncil", "APP/A", site_id=site_a.id)
    _make_scheme_intelligence(session, app_a.id, total_units_final=100)
    app_b = _make_application(session, "testcouncil", "APP/B", site_id=site_b.id)
    _make_scheme_intelligence(session, app_b.id, total_units_final=150)
    # site_c: no application at all
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    coverage = result[allocation.id]["coverage"]

    assert coverage.number_of_related_sites == 3
    assert coverage.number_of_sites_with_planning_activity == 2
    assert coverage.number_of_sites_without_identified_planning_activity == 1
    assert coverage.identified_application_capacity == 250
    assert coverage.indicative_residual_capacity == 250
    assert coverage.development_coverage_classification == PARTIAL_COVERAGE


def test_one_site_never_assumed_to_be_whole_allocation(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "H4", policy_reference="H4", minimum_dwellings=1000)
    site_a = _make_site(session, "testcouncil", "site a")
    site_b = _make_site(session, "testcouncil", "site b")
    _make_relationship(session, allocation.id, site_a.id)
    _make_relationship(session, allocation.id, site_b.id)
    app_a = _make_application(session, "testcouncil", "APP/A", site_id=site_a.id)
    _make_scheme_intelligence(session, app_a.id, total_units_final=200)
    # site_b has no application - must not be assumed to cover the rest
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    coverage = result[allocation.id]["coverage"]

    assert coverage.number_of_related_sites == 2
    assert coverage.identified_application_capacity == 200
    assert coverage.indicative_residual_capacity == 800


# ---------------------------------------------------------------------------
# Linked application discovery
# ---------------------------------------------------------------------------


def test_linked_application_discovery_counts_across_all_related_sites(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=300)
    site_a = _make_site(session, "testcouncil", "site a")
    site_b = _make_site(session, "testcouncil", "site b")
    _make_relationship(session, allocation.id, site_a.id)
    _make_relationship(session, allocation.id, site_b.id)
    _make_application(session, "testcouncil", "APP/1", site_id=site_a.id, estimated_unit_count=50)
    _make_application(session, "testcouncil", "APP/2", site_id=site_a.id, estimated_unit_count=60, received="02/01/2025")
    _make_application(session, "testcouncil", "APP/3", site_id=site_b.id, estimated_unit_count=70)
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    coverage = result[allocation.id]["coverage"]

    assert coverage.number_of_linked_applications == 3


# ---------------------------------------------------------------------------
# No application = NO_IDENTIFIED_ACTIVITY, never "available"
# ---------------------------------------------------------------------------


def test_no_application_produces_no_identified_activity_not_available(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=400)
    site = _make_site(session, "testcouncil", "some site")
    _make_relationship(session, allocation.id, site.id)
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    coverage = result[allocation.id]["coverage"]

    assert coverage.development_coverage_classification == NO_IDENTIFIED_ACTIVITY
    assert coverage.identified_application_capacity == 0
    assert coverage.indicative_residual_capacity == 400


def test_wording_never_uses_available_language(session):
    """Checks actual GENERATED strings (coverage notes + opportunity
    reasons) across representative scenarios - not the module's own
    source code, which legitimately quotes these forbidden phrases while
    explaining why they must never appear in output."""
    banned = ("available land", "available units", "available capacity", "undeveloped land", "uncontrolled land", "land for sale")

    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=1000)
    site = _make_site(session, "testcouncil", "some site")
    _make_relationship(session, allocation.id, site.id)
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_scheme_intelligence(session, app.id, total_units_final=300)
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    coverage = result[allocation.id]["coverage"]
    opportunity = build_opportunity_signal(plan_status_bucket="adopted", coverage=coverage, phasing=result[allocation.id]["phasing"])

    generated_text = " ".join(opportunity["reasons"]) + " " + (coverage.note or "")
    lowered = generated_text.lower()
    for phrase in banned:
        assert phrase not in lowered


# ---------------------------------------------------------------------------
# Safe dwelling aggregation / duplicate-supersession protection
# ---------------------------------------------------------------------------


def test_multiple_applications_on_same_site_never_summed(session):
    """Outline + reserved matters, amendment, replacement scheme - all on
    ONE site - must contribute ONE representative figure, never a sum."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=500)
    site = _make_site(session, "testcouncil", "some site")
    _make_relationship(session, allocation.id, site.id)
    app_outline = _make_application(session, "testcouncil", "APP/OUTLINE", site_id=site.id, received="01/01/2025")
    _make_scheme_intelligence(session, app_outline.id, total_units_final=200, core_intelligence_complete=False)
    app_reserved_matters = _make_application(session, "testcouncil", "APP/RM", site_id=site.id, received="01/06/2025")
    _make_scheme_intelligence(session, app_reserved_matters.id, total_units_final=200, core_intelligence_complete=True)
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    coverage = result[allocation.id]["coverage"]

    # Not 400 (200+200) - exactly one representative application's figure.
    assert coverage.identified_application_capacity == 200
    assert coverage.number_of_linked_applications == 2


def test_representative_application_prefers_complete_extraction(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "some site")
    app_incomplete = _make_application(session, "testcouncil", "APP/1", site_id=site.id, received="01/06/2025")
    _make_scheme_intelligence(session, app_incomplete.id, total_units_final=999, core_intelligence_complete=False)
    app_complete = _make_application(session, "testcouncil", "APP/2", site_id=site.id, received="01/01/2025")
    _make_scheme_intelligence(session, app_complete.id, total_units_final=150, core_intelligence_complete=True)
    session.commit()

    summary = summarise_site_activity(site, [app_incomplete, app_complete])
    assert summary.capacity == 150
    assert summary.representative_application.id == app_complete.id


# ---------------------------------------------------------------------------
# Review-required when capacity cannot safely aggregate
# ---------------------------------------------------------------------------


def test_active_site_with_unknown_capacity_forces_review_required(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=500)
    site = _make_site(session, "testcouncil", "some site")
    _make_relationship(session, allocation.id, site.id)
    # An application exists but has no scheme_intelligence and no estimated_unit_count.
    _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    coverage = result[allocation.id]["coverage"]

    assert coverage.capacity_accounting_status == "review_required"
    assert coverage.development_coverage_classification == REVIEW_REQUIRED
    assert coverage.identified_application_capacity is None
    assert coverage.indicative_residual_capacity is None


def test_multi_site_review_required_uses_multi_parcel_wording(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=500)
    site_a = _make_site(session, "testcouncil", "site a")
    site_b = _make_site(session, "testcouncil", "site b")
    _make_relationship(session, allocation.id, site_a.id)
    _make_relationship(session, allocation.id, site_b.id)
    _make_application(session, "testcouncil", "APP/1", site_id=site_a.id)  # no unit count
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    coverage = result[allocation.id]["coverage"]

    assert coverage.development_coverage_classification == REVIEW_REQUIRED
    assert "Multiple development parcels" in coverage.note


# ---------------------------------------------------------------------------
# Stage 3B amendment (Section 5/6): disputed/rejected relationship semantics
# ---------------------------------------------------------------------------


def test_disputed_relationship_with_known_capacity_forces_review_required(session):
    """Section 5: a Site with a REAL known capacity number, but whose
    accepted relationship has since been flagged needs_confirmation by
    contradicting evidence, must never silently produce a confident
    coverage percentage/residual - the underlying accounting relationship
    is disputed."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=1000)
    site = _make_site(session, "testcouncil", "some site")
    _make_relationship(session, allocation.id, site.id, review_status="needs_confirmation")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_scheme_intelligence(session, app.id, total_units_final=300)
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    coverage = result[allocation.id]["coverage"]

    assert coverage.development_coverage_classification == REVIEW_REQUIRED
    assert coverage.capacity_accounting_status == "review_required"
    assert coverage.note == DISPUTED_RELATIONSHIP_NOTE
    assert coverage.identified_application_capacity is None
    assert coverage.indicative_residual_capacity is None
    # The relationship itself is still retained/counted as related - never
    # auto-deleted or hidden, only the derived conclusion is withheld.
    assert coverage.number_of_related_sites == 1


def test_auto_applied_and_confirmed_relationships_are_unaffected_by_disputed_check(session):
    """Only needs_confirmation triggers the disputed-relationship
    override - auto_applied and confirmed relationships compute coverage
    normally."""
    _make_council(session, "testcouncil")
    allocation_auto = _make_allocation(session, "testcouncil", "Auto", policy_reference="A1", minimum_dwellings=1000)
    site_auto = _make_site(session, "testcouncil", "site auto")
    _make_relationship(session, allocation_auto.id, site_auto.id, review_status="auto_applied")
    app_auto = _make_application(session, "testcouncil", "APP/AUTO", site_id=site_auto.id)
    _make_scheme_intelligence(session, app_auto.id, total_units_final=300)

    allocation_confirmed = _make_allocation(session, "testcouncil", "Confirmed", policy_reference="A2", minimum_dwellings=1000)
    site_confirmed = _make_site(session, "testcouncil", "site confirmed")
    _make_relationship(session, allocation_confirmed.id, site_confirmed.id, review_status="confirmed")
    app_confirmed = _make_application(session, "testcouncil", "APP/CONFIRMED", site_id=site_confirmed.id)
    _make_scheme_intelligence(session, app_confirmed.id, total_units_final=300)
    session.commit()

    result = build_allocation_development_coverage(session, [allocation_auto, allocation_confirmed])

    assert result[allocation_auto.id]["coverage"].development_coverage_classification == PARTIAL_COVERAGE
    assert result[allocation_confirmed.id]["coverage"].development_coverage_classification == PARTIAL_COVERAGE


def test_rejected_relationship_excluded_from_coverage_entirely(session):
    """Section 6: 'rejected' must not contribute to accepted relationship
    development accounting at all - excluded from related-Site counts,
    not just from the capacity sum."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=1000)
    site = _make_site(session, "testcouncil", "some site")
    _make_relationship(session, allocation.id, site.id, review_status="rejected")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_scheme_intelligence(session, app.id, total_units_final=300)
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    coverage = result[allocation.id]["coverage"]

    assert coverage.number_of_related_sites == 0
    assert coverage.development_coverage_classification == NO_IDENTIFIED_ACTIVITY
    assert coverage.identified_application_capacity == 0


def test_rejected_relationship_alongside_accepted_one_only_counts_the_accepted(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=1000)
    site_rejected = _make_site(session, "testcouncil", "rejected site")
    site_accepted = _make_site(session, "testcouncil", "accepted site")
    _make_relationship(session, allocation.id, site_rejected.id, review_status="rejected")
    _make_relationship(session, allocation.id, site_accepted.id, review_status="auto_applied")
    app_rejected = _make_application(session, "testcouncil", "APP/REJECTED", site_id=site_rejected.id)
    _make_scheme_intelligence(session, app_rejected.id, total_units_final=999)
    app_accepted = _make_application(session, "testcouncil", "APP/ACCEPTED", site_id=site_accepted.id)
    _make_scheme_intelligence(session, app_accepted.id, total_units_final=100)
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    coverage = result[allocation.id]["coverage"]

    assert coverage.number_of_related_sites == 1
    assert coverage.identified_application_capacity == 100  # never the rejected Site's 999


def test_local_plan_site_review_status_does_not_affect_relationship_acceptance(session):
    """Section 6: never conflate LocalPlanSite.review_status with
    AllocationSiteRelationship.review_status - an allocation whose OWN
    review_status is 'needs_confirmation' (an unrelated Local Plan
    content-review concept) must compute coverage exactly as if that
    field were absent."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=1000)
    allocation.review_status = "needs_confirmation"  # LocalPlanSite's OWN field - unrelated
    site = _make_site(session, "testcouncil", "some site")
    _make_relationship(session, allocation.id, site.id, review_status="auto_applied")  # relationship itself is fine
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_scheme_intelligence(session, app.id, total_units_final=300)
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    coverage = result[allocation.id]["coverage"]

    assert coverage.development_coverage_classification == PARTIAL_COVERAGE  # not REVIEW_REQUIRED
    assert coverage.identified_application_capacity == 300


# ---------------------------------------------------------------------------
# Residual / percentage / negative-residual clamp
# ---------------------------------------------------------------------------


def test_residual_and_percentage_calculation(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=1000)
    site = _make_site(session, "testcouncil", "some site")
    _make_relationship(session, allocation.id, site.id)
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_scheme_intelligence(session, app.id, total_units_final=300)
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    coverage = result[allocation.id]["coverage"]

    assert coverage.identified_application_capacity == 300
    assert coverage.indicative_residual_capacity == 700
    assert coverage.development_coverage_percentage == 0.3


def test_negative_residual_becomes_review_required_not_zeroed(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=100)
    site = _make_site(session, "testcouncil", "some site")
    _make_relationship(session, allocation.id, site.id)
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_scheme_intelligence(session, app.id, total_units_final=150)  # exceeds allocation capacity
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    coverage = result[allocation.id]["coverage"]

    assert coverage.development_coverage_classification == REVIEW_REQUIRED
    assert coverage.capacity_accounting_status == "review_required"
    assert coverage.indicative_residual_capacity is None  # never a negative number, never silently zeroed


def test_fully_accounted_for_and_substantially_covered_thresholds(session):
    _make_council(session, "testcouncil")
    allocation_full = _make_allocation(session, "testcouncil", "Full", policy_reference="F1", minimum_dwellings=100)
    site_full = _make_site(session, "testcouncil", "full site")
    _make_relationship(session, allocation_full.id, site_full.id)
    app_full = _make_application(session, "testcouncil", "APP/FULL", site_id=site_full.id)
    _make_scheme_intelligence(session, app_full.id, total_units_final=95)

    allocation_sub = _make_allocation(session, "testcouncil", "Sub", policy_reference="S1", minimum_dwellings=100)
    site_sub = _make_site(session, "testcouncil", "sub site")
    _make_relationship(session, allocation_sub.id, site_sub.id)
    app_sub = _make_application(session, "testcouncil", "APP/SUB", site_id=site_sub.id)
    _make_scheme_intelligence(session, app_sub.id, total_units_final=75)
    session.commit()

    result = build_allocation_development_coverage(session, [allocation_full, allocation_sub])
    assert result[allocation_full.id]["coverage"].development_coverage_classification == FULLY_ACCOUNTED_FOR
    assert result[allocation_sub.id]["coverage"].development_coverage_classification == SUBSTANTIALLY_COVERED


def test_capacity_unknown_when_allocation_capacity_not_stated(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=None)
    site = _make_site(session, "testcouncil", "some site")
    _make_relationship(session, allocation.id, site.id)
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_scheme_intelligence(session, app.id, total_units_final=50)
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    coverage = result[allocation.id]["coverage"]
    assert coverage.development_coverage_classification == CAPACITY_UNKNOWN
    assert coverage.identified_application_capacity == 50
    assert coverage.indicative_residual_capacity is None


# ---------------------------------------------------------------------------
# Confirmed phasing requires documentary evidence
# ---------------------------------------------------------------------------


def test_partial_capacity_alone_cannot_produce_confirmed_phased(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=1000)
    site = _make_site(session, "testcouncil", "some site")
    _make_relationship(session, allocation.id, site.id)
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_scheme_intelligence(session, app.id, total_units_final=100)
    _make_document(session, app.id, "planning_statement", "A perfectly ordinary scheme with no phasing language at all.")
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    phasing = result[allocation.id]["phasing"]
    assert phasing["classification"] != CONFIRMED_PHASED


def test_explicit_phase_one_language_produces_confirmed_phased(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=1000)
    site = _make_site(session, "testcouncil", "some site")
    _make_relationship(session, allocation.id, site.id)
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_scheme_intelligence(session, app.id, total_units_final=100)
    _make_document(session, app.id, "planning_statement", "This application represents Phase 1 of the wider allocation.")
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    phasing = result[allocation.id]["phasing"]
    assert phasing["classification"] == CONFIRMED_PHASED
    assert len(phasing["evidence"]) == 1
    assert phasing["evidence"][0].phrase == "phase 1"
    assert phasing["evidence"][0].application_id == app.id


def test_phase_1_habitat_survey_is_not_phasing_evidence(session):
    """Real production false-positive found during Stage 3A live
    verification (Wigan JPA 32/North of Mosley Common): 'Phase 1 Habitat
    Survey Report' is standard UK ecological-survey report-naming
    convention, unrelated to whether the DEVELOPMENT is phased."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=1000)
    site = _make_site(session, "testcouncil", "some site")
    _make_relationship(session, allocation.id, site.id)
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_scheme_intelligence(session, app.id, total_units_final=100)
    _make_document(session, app.id, "planning_statement",
                    "The habitat descriptions provided in the Phase 1 habitat survey report are still valid.")
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    phasing = result[allocation.id]["phasing"]
    assert phasing["classification"] != CONFIRMED_PHASED
    assert phasing["evidence"] == []


def test_phase_1_and_2_ground_investigation_is_not_phasing_evidence(session):
    """Real production false-positive found during Stage 3A live
    verification (Wigan H6/East of Atherton): 'Phase 1 and 2 Ground
    Investigation Report' is a standard geotechnical/contamination survey
    title, not development-phasing evidence."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=1000)
    site = _make_site(session, "testcouncil", "some site")
    _make_relationship(session, allocation.id, site.id)
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_scheme_intelligence(session, app.id, total_units_final=100)
    _make_document(session, app.id, "officer_report",
                    "Submitted documents include a Phase 1 and 2 Ground Investigation Report and a transport assessment.")
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    phasing = result[allocation.id]["phasing"]
    assert phasing["classification"] != CONFIRMED_PHASED
    assert phasing["evidence"] == []


def test_genuine_phase_1_evidence_still_detected_alongside_survey_titles(session):
    """The exclusion must be narrow: a document that ALSO contains a
    genuine development-phasing phrase elsewhere must still be detected,
    even if it separately mentions a Phase 1 survey report."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=1000)
    site = _make_site(session, "testcouncil", "some site")
    _make_relationship(session, allocation.id, site.id)
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_scheme_intelligence(session, app.id, total_units_final=100)
    _make_document(session, app.id, "planning_statement",
                    "A Phase 1 habitat survey report was submitted. Future phases of the wider allocation will "
                    "be brought forward through separate reserved matters applications in due course.")
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    phasing = result[allocation.id]["phasing"]
    assert phasing["classification"] == CONFIRMED_PHASED
    assert any(hit.phrase in ("future phase", "future phases") for hit in phasing["evidence"])


def test_potential_phased_when_partial_and_multi_site_no_explicit_language(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=1000)
    site_a = _make_site(session, "testcouncil", "site a")
    site_b = _make_site(session, "testcouncil", "site b")
    _make_relationship(session, allocation.id, site_a.id)
    _make_relationship(session, allocation.id, site_b.id)
    app_a = _make_application(session, "testcouncil", "APP/A", site_id=site_a.id)
    _make_scheme_intelligence(session, app_a.id, total_units_final=100)
    app_b = _make_application(session, "testcouncil", "APP/B", site_id=site_b.id)
    _make_scheme_intelligence(session, app_b.id, total_units_final=50)
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    phasing = result[allocation.id]["phasing"]
    assert phasing["classification"] == POTENTIAL_PHASED


def test_no_phasing_evidence_for_single_site_no_multi_activity(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=100)
    site = _make_site(session, "testcouncil", "some site")
    _make_relationship(session, allocation.id, site.id)
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_scheme_intelligence(session, app.id, total_units_final=95)
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    phasing = result[allocation.id]["phasing"]
    assert phasing["classification"] == NO_PHASING_EVIDENCE


def test_phasing_review_required_mirrors_capacity_review_required(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=100)
    site = _make_site(session, "testcouncil", "some site")
    _make_relationship(session, allocation.id, site.id)
    _make_application(session, "testcouncil", "APP/1", site_id=site.id)  # no unit count -> review_required
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    assert result[allocation.id]["phasing"]["classification"] == PHASING_REVIEW_REQUIRED


# ---------------------------------------------------------------------------
# Evidence provenance
# ---------------------------------------------------------------------------


def test_phasing_evidence_provenance_retained(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=1000)
    site = _make_site(session, "testcouncil", "some site")
    _make_relationship(session, allocation.id, site.id)
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    doc = _make_document(session, app.id, "planning_statement", "This scheme forms the first phase of a wider strategic allocation.")
    session.commit()

    hits = search_phasing_evidence([(doc, app)])
    assert len(hits) == 1
    assert hits[0].document_id == doc.id
    assert hits[0].application_id == app.id
    assert hits[0].application_reference == "APP/1"
    assert hits[0].phrase == "first phase"
    assert "wider strategic allocation" in hits[0].snippet
    # Never the entire document text - bounded snippet only.
    assert len(hits[0].snippet) < len(doc.extracted_text) + 10


# ---------------------------------------------------------------------------
# North of Mosley Common regression (real production figures)
# ---------------------------------------------------------------------------


def test_north_of_mosley_common_regression(session):
    """Real production figures (Stage 3A audit): allocation JPA 32 / North
    of Mosley Common, minimum_dwellings=1100; document-confirmed Site
    (application A/25/099409/RMMAJ) with SchemeIntelligence.
    total_units_final=244. Expected: ~22% coverage, ~856 residual,
    PARTIAL_COVERAGE, and never described as "available"."""
    _make_council(session, "wigan")
    allocation = _make_allocation(session, "wigan", "North of Mosley Common", policy_reference="JPA 32", minimum_dwellings=1100)
    site = _make_site(session, "wigan", "mosley common south of the guided busway worsley")
    _make_relationship(session, allocation.id, site.id)
    app = _make_application(session, "wigan", "A/25/099409/RMMAJ", site_id=site.id)
    _make_scheme_intelligence(session, app.id, total_units_final=244)
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    coverage = result[allocation.id]["coverage"]

    assert coverage.allocation_capacity == 1100
    assert coverage.identified_application_capacity == 244
    assert coverage.indicative_residual_capacity == 856
    assert round(coverage.development_coverage_percentage * 100) == 22
    assert coverage.development_coverage_classification == PARTIAL_COVERAGE

    opportunity = build_opportunity_signal(
        plan_status_bucket="adopted", coverage=coverage, phasing=result[allocation.id]["phasing"],
    )
    assert opportunity["signal"] == INVESTIGATE
    joined_reasons = " ".join(opportunity["reasons"])
    assert "856" in joined_reasons
    assert "22%" in joined_reasons
    assert OWNERSHIP_CAVEAT in opportunity["reasons"]
    assert "available" not in joined_reasons.lower()


# ---------------------------------------------------------------------------
# Housing mix remains application-specific (reuses residential_mix.py)
# ---------------------------------------------------------------------------


def test_housing_mix_reuses_residential_mix_module_not_duplicated():
    """Section 8: no duplicate housing-mix storage/computation is
    introduced by this module - confirmed it defines no bedroom/tenure/
    storeys field, dataclass, or regex pattern list of its own (the
    module's own docstring legitimately DISCUSSES this gap in prose,
    which is why this checks structure, not a raw substring scan)."""
    dataclass_field_names = set()
    for name in ("SiteActivitySummary", "DevelopmentCoverageResult", "PhasingEvidenceHit"):
        cls = getattr(coverage_module, name)
        dataclass_field_names.update(cls.__dataclass_fields__.keys())
    for field_name in dataclass_field_names:
        assert "bed" not in field_name.lower()
        assert "storey" not in field_name.lower()
        assert "tenure" not in field_name.lower()
    assert not hasattr(coverage_module, "extract_housing_mix")
    assert not hasattr(coverage_module, "AFFORDABLE_SCHEMA")


def test_residential_mix_stays_scoped_to_its_own_application(session):
    from app.reporting.residential_mix import build_residential_mix

    _make_council(session, "wigan")
    site = _make_site(session, "wigan", "mosley common south of the guided busway worsley")
    app = _make_application(session, "wigan", "A/25/099409/RMMAJ", site_id=site.id)
    _make_scheme_intelligence(session, app.id, total_units_final=244)
    session.commit()

    mix = build_residential_mix(site, [app], rep_app=app)
    assert mix["overview_totals"]["total_homes"] == 244
    # Never labelled as the whole allocation's mix - scoped to this one
    # application/current_version only.
    assert mix["current_version"]["application_id"] == app.id


# ---------------------------------------------------------------------------
# Opportunity signal is explainable + ownership caveat
# ---------------------------------------------------------------------------


def test_opportunity_signal_always_includes_ownership_caveat(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=1000)
    session.commit()
    result = build_allocation_development_coverage(session, [allocation])
    opportunity = build_opportunity_signal(
        plan_status_bucket="adopted", coverage=result[allocation.id]["coverage"], phasing=result[allocation.id]["phasing"],
    )
    assert OWNERSHIP_CAVEAT in opportunity["reasons"]


def test_opportunity_signal_insufficient_evidence_when_capacity_review_required(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=100)
    site = _make_site(session, "testcouncil", "some site")
    _make_relationship(session, allocation.id, site.id)
    _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    opportunity = build_opportunity_signal(
        plan_status_bucket="adopted", coverage=result[allocation.id]["coverage"], phasing=result[allocation.id]["phasing"],
    )
    assert opportunity["signal"] == INSUFFICIENT_EVIDENCE


def test_opportunity_signal_lower_priority_when_fully_accounted(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=100)
    site = _make_site(session, "testcouncil", "some site")
    _make_relationship(session, allocation.id, site.id)
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_scheme_intelligence(session, app.id, total_units_final=98)
    session.commit()

    result = build_allocation_development_coverage(session, [allocation])
    opportunity = build_opportunity_signal(
        plan_status_bucket="adopted", coverage=result[allocation.id]["coverage"], phasing=result[allocation.id]["phasing"],
    )
    assert opportunity["signal"] == LOWER_PRIORITY


def test_opportunity_signal_insufficient_evidence_for_non_adopted_non_emerging_plan(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=100)
    session.commit()
    result = build_allocation_development_coverage(session, [allocation])
    opportunity = build_opportunity_signal(
        plan_status_bucket="other", coverage=result[allocation.id]["coverage"], phasing=result[allocation.id]["phasing"],
    )
    assert opportunity["signal"] == INSUFFICIENT_EVIDENCE


# ---------------------------------------------------------------------------
# Batched query discipline / no OpenAI / no production writes
# ---------------------------------------------------------------------------


def test_no_openai_dependency():
    source = inspect.getsource(coverage_module)
    assert "import openai" not in source.lower()
    assert "OpenAI(" not in source
    assert "from openai" not in source.lower()


def test_module_makes_no_writes():
    for fn in (
        summarise_site_activity, compute_development_coverage, search_phasing_evidence,
        classify_phasing, build_opportunity_signal, build_allocation_development_coverage,
    ):
        source = inspect.getsource(fn)
        assert "session.add(" not in source
        assert "session.flush()" not in source
        assert "session.commit()" not in source


def test_empty_allocation_list_returns_empty_dict(session):
    assert build_allocation_development_coverage(session, []) == {}


def test_every_allocation_present_even_with_zero_related_sites(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Allocation A", minimum_dwellings=100)
    session.commit()
    result = build_allocation_development_coverage(session, [allocation])
    assert allocation.id in result
    assert result[allocation.id]["coverage"].development_coverage_classification == NO_IDENTIFIED_ACTIVITY
