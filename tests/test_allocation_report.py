"""Tests for Site Selection & Reporting V1 Gate 2 - app.reporting.
allocation_report's deterministic report-context builder and CSV export.

Integration-style against the real in-memory SQLite session fixture (the
same convention tests/test_allocation_discovery.py already uses for
build_allocation_discovery, since build_allocation_report_context is
fundamentally a multi-table query composition, not a pure function over an
already-built dict). council_code uses the fixture's "testcouncil"/
"othercouncil" rows throughout - council_name is sourced from
app.config.load_councils() (a real config file, not the test DB), so tests
never assert on its exact resolved value, only that a name (real or the
raw-code fallback) is present - mirroring how test_allocation_discovery.py's
own integration tests avoid asserting on council_name for the same reason.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import event

from app.db.models import (
    AllocationIntelligenceSummary,
    AllocationSiteRelationship,
    Application,
    ControlRelationship,
    LocalPlan,
    LocalPlanSite,
    SchemeIntelligence,
    Site,
)
from app.reporting.allocation_report import (
    CSV_COLUMNS,
    build_allocation_report_context,
    to_csv_bytes,
    to_csv_rows,
)

# --- Fixtures -----------------------------------------------------------------


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


# --- A/Q. exact shortlisted population only / multiple allocations ----------

def test_context_contains_exactly_the_requested_allocations(session):
    plan = _make_local_plan(session)
    a1 = _make_allocation(session, plan.id, policy_reference="A1", site_name="Alloc One")
    a2 = _make_allocation(session, plan.id, policy_reference="A2", site_name="Alloc Two")
    _make_allocation(session, plan.id, policy_reference="A3", site_name="Alloc Three (not shortlisted)")

    context = build_allocation_report_context(session, [a1.id, a2.id])

    assert {e.allocation_id for e in context.entries} == {a1.id, a2.id}
    assert context.aggregates.allocation_count == 2


# --- B. allocation identity ---------------------------------------------------

def test_allocation_identity_fields(session):
    plan = _make_local_plan(session, plan_name="Bury Local Plan")
    allocation = _make_allocation(
        session, plan.id, policy_reference="JPA1.1", site_name="Northern Gateway", intended_use="residential",
    )
    [entry] = build_allocation_report_context(session, [allocation.id]).entries

    assert entry.allocation_id == allocation.id
    assert entry.allocation_name == "Northern Gateway"
    assert entry.allocation_reference == "JPA1.1"
    assert entry.local_plan_name == "Bury Local Plan"
    assert entry.plan_status_label  # resolved via PLAN_STATUS_META, non-empty
    assert entry.intended_use_label == "Residential"
    assert entry.council_name  # either the real config name or the raw code fallback


# --- C. capacity / T. range/unknown capacity semantics -----------------------

def test_capacity_exact_value(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=150)
    [entry] = build_allocation_report_context(session, [allocation.id]).entries
    assert entry.capacity_value == 150
    assert entry.capacity_kind == "minimum"


def test_capacity_range_reuses_platforms_existing_upper_bound_convention(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=8400, maximum_capacity=15000)
    [entry] = build_allocation_report_context(session, [allocation.id]).entries
    assert entry.capacity_kind == "range"
    assert entry.capacity_value == 15000  # format_capacity's own established range->upper-bound rule, not invented here
    assert entry.capacity_display == "8,400–15,000 homes"


def test_capacity_unknown_when_nothing_stated(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    [entry] = build_allocation_report_context(session, [allocation.id]).entries
    assert entry.capacity_kind == "unknown"
    assert entry.capacity_value is None


# --- D. development coverage / E. residual capacity --------------------------

def test_development_coverage_and_residual_capacity_with_identified_activity(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=1000)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id)
    app = _make_app(session, site.id, reference="APP/1")
    session.add(SchemeIntelligence(application_id=app.id, total_units_final=300, core_intelligence_complete=True))
    session.commit()

    [entry] = build_allocation_report_context(session, [allocation.id]).entries

    assert entry.identified_application_capacity == 300
    assert entry.indicative_residual_capacity == 700
    assert entry.development_coverage_percentage == pytest.approx(0.3)
    assert entry.development_coverage_classification == "PARTIAL_COVERAGE"
    assert entry.capacity_accounting_status == "ok"


# --- F. no-linked-Application case -------------------------------------------

def test_no_linked_application_is_a_valid_neutral_state_not_an_error(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=200)
    [entry] = build_allocation_report_context(session, [allocation.id]).entries

    assert entry.linked_application_count == 0
    assert entry.linked_applications == []
    assert entry.capacity_accounting_status == "no_activity"
    assert entry.indicative_residual_capacity == 200  # the whole allocation, not an error/None


# --- G. linked Application details -------------------------------------------

def test_linked_application_details(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id)
    app = _make_app(
        session, site.id, reference="APP/1", proposal="Erection of 50 dwellings", status="Pending",
        decision="Not Available", decision_issued_date="2026-01-15", application_category="full_planning",
        applicant_name_raw="Acme Homes Ltd", summary_url="https://portal.example/APP-1",
    )
    session.add(SchemeIntelligence(application_id=app.id, total_units_final=50, core_intelligence_complete=True))
    session.commit()

    [entry] = build_allocation_report_context(session, [allocation.id]).entries
    [linked] = entry.linked_applications

    assert linked.reference == "APP/1"
    assert linked.proposal == "Erection of 50 dwellings"
    assert linked.status == "Pending"
    # "Not Available" is a known non-informative portal placeholder - cleaned to None, never shown as a real decision.
    assert linked.decision is None
    assert linked.decision_date == "2026-01-15"
    assert linked.unit_count == 50
    assert linked.unit_count_is_estimate is False
    assert linked.application_category == "full_planning"
    assert linked.applicant == "Acme Homes Ltd"
    assert linked.portal_url == "https://portal.example/APP-1"
    assert linked.is_representative is True
    assert linked.site_relationship_review_status == "auto_applied"


# --- H. multi-Application evidence -------------------------------------------

def test_multi_application_applicant_evidence_aggregates_across_every_trusted_application(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id)
    _make_app(session, site.id, reference="APP/1", applicant_name_raw="Acme Homes Ltd")
    _make_app(session, site.id, reference="APP/2", applicant_name_raw="Acme Homes Ltd")
    _make_app(session, site.id, reference="APP/3", applicant_name_raw="Beta Developments")

    [entry] = build_allocation_report_context(session, [allocation.id]).entries
    by_name = {e.entity_name: e for e in entry.applicant_evidence}

    assert set(by_name) == {"Acme Homes Ltd", "Beta Developments"}
    assert sorted(by_name["Acme Homes Ltd"].application_references) == ["APP/1", "APP/2"]
    assert by_name["Beta Developments"].application_references == ["APP/3"]
    # Never regressed to representative-only: APP/2 is not the representative application, yet still counted.
    assert entry.linked_application_count == 3


# --- I. Applicant-only role / J. independently evidenced Developer role -----

def test_applicant_only_role_is_never_promoted_to_developer(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id)
    _make_app(session, site.id, reference="APP/1", applicant_name_raw="Applicant Only Ltd")

    [entry] = build_allocation_report_context(session, [allocation.id]).entries

    assert entry.applicant_evidence[0].entity_name == "Applicant Only Ltd"
    assert entry.ownership_evidence == []  # no ControlRelationship evidence exists - no Developer/Owner claim invented


def test_independently_evidenced_developer_role(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id)
    _make_control(session, site_id=site.id, entity_name_raw="Real Developer Ltd", role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")

    [entry] = build_allocation_report_context(session, [allocation.id]).entries

    assert len(entry.ownership_evidence) == 1
    assert entry.ownership_evidence[0].entity_name_raw == "Real Developer Ltd"
    assert entry.ownership_evidence[0].role == "DEVELOPER"
    assert entry.ownership_evidence[0].role_label == "S106 Developer"


# --- K. ownership declaration semantics --------------------------------------

def test_certificate_a_declaration_labelled_planning_ownership_declaration_never_current_owner(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id)
    _make_control(
        session, site_id=site.id, entity_name_raw="Landowner Estates Ltd", role="OWNER",
        evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION", evidence_basis="certificate_a_declaration",
    )

    [entry] = build_allocation_report_context(session, [allocation.id]).entries

    assert entry.ownership_evidence[0].role_label == "Planning ownership declaration"
    assert "current owner" not in entry.ownership_evidence[0].role_label.lower()


# --- L. needs_confirmation behaviour / M. rejected evidence excluded --------

def test_needs_confirmation_control_relationship_is_retained_and_flagged(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id)
    _make_control(
        session, site_id=site.id, entity_name_raw="Disputed Party Ltd", role="OWNER",
        evidence_category="S106_DEFINED_OWNER", review_status="needs_confirmation",
    )

    [entry] = build_allocation_report_context(session, [allocation.id]).entries

    assert len(entry.ownership_evidence) == 1
    assert entry.ownership_evidence[0].needs_review is True


def test_rejected_control_relationship_is_excluded_entirely(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id)
    _make_control(
        session, site_id=site.id, entity_name_raw="Rejected Party Ltd", role="OWNER",
        evidence_category="S106_DEFINED_OWNER", review_status="rejected",
    )

    [entry] = build_allocation_report_context(session, [allocation.id]).entries
    assert entry.ownership_evidence == []


def test_needs_confirmation_relationship_forces_review_required_coverage_not_a_confident_number(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=1000)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id, review_status="needs_confirmation")
    app = _make_app(session, site.id, reference="APP/1")
    session.add(SchemeIntelligence(application_id=app.id, total_units_final=300, core_intelligence_complete=True))
    session.commit()

    [entry] = build_allocation_report_context(session, [allocation.id]).entries

    assert entry.capacity_accounting_status == "review_required"
    assert entry.development_coverage_classification == "REVIEW_REQUIRED"
    assert entry.indicative_residual_capacity is None  # never a manufactured number from disputed evidence
    assert entry.disputed_site_count == 1


def test_rejected_allocation_site_relationship_excluded_from_coverage_entirely(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=1000)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id, review_status="rejected")

    [entry] = build_allocation_report_context(session, [allocation.id]).entries

    assert entry.linked_application_count == 0
    assert entry.capacity_accounting_status == "no_activity"  # the rejected Site is not related at all


# --- N. missing allocation ----------------------------------------------------

def test_missing_allocation_is_excluded_with_a_reason_others_still_build(session):
    plan = _make_local_plan(session)
    real = _make_allocation(session, plan.id)

    context = build_allocation_report_context(session, [real.id, 999999])

    assert [e.allocation_id for e in context.entries] == [real.id]
    assert len(context.excluded) == 1
    assert context.excluded[0].allocation_id == 999999
    assert context.excluded[0].reason


# --- O. missing AI summary / P. errored AI summary ---------------------------

def test_missing_ai_summary_is_a_safe_available_false_state(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    [entry] = build_allocation_report_context(session, [allocation.id]).entries

    assert entry.ai_intelligence.available is False
    assert entry.ai_intelligence.headline is None


def test_errored_ai_summary_is_safe_and_never_exposes_the_raw_error(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    _make_summary(session, allocation.id, headline=None, overview=None, status="error", generation_error="raw stack trace / prompt leak")

    [entry] = build_allocation_report_context(session, [allocation.id]).entries

    assert entry.ai_intelligence.available is False
    # The dataclass has no field at all that could carry generation_error - structurally impossible to leak it.
    assert not hasattr(entry.ai_intelligence, "generation_error")


def test_available_ai_summary_is_reshaped_correctly(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    _make_summary(
        session, allocation.id, headline="Strong opportunity.", overview="Detailed overview.",
        key_points=json.dumps(["Point A", "Point B"]), key_uncertainties=json.dumps(["Uncertainty A"]),
        investigation_priorities=json.dumps(["Priority A"]),
    )

    [entry] = build_allocation_report_context(session, [allocation.id]).entries

    assert entry.ai_intelligence.available is True
    assert entry.ai_intelligence.headline == "Strong opportunity."
    assert entry.ai_intelligence.key_points == ["Point A", "Point B"]
    assert entry.ai_intelligence.key_uncertainties == ["Uncertainty A"]
    assert entry.ai_intelligence.investigation_priorities == ["Priority A"]


# --- R. duplicate IDs ----------------------------------------------------------

def test_duplicate_shortlist_ids_do_not_duplicate_the_entry(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)

    context = build_allocation_report_context(session, [allocation.id, allocation.id, allocation.id])

    assert len(context.entries) == 1
    assert context.aggregates.allocation_count == 1


# --- S. empty shortlist --------------------------------------------------------

def test_empty_shortlist_returns_a_valid_empty_context(session):
    context = build_allocation_report_context(session, [])

    assert context.entries == []
    assert context.excluded == []
    assert context.aggregates.allocation_count == 0


def test_only_invalid_ids_returns_valid_context_with_everything_excluded(session):
    context = build_allocation_report_context(session, [123456, 654321])

    assert context.entries == []
    assert len(context.excluded) == 2


# --- Aggregates: known_total + unknown_count, never a manufactured total ----

def test_aggregates_separate_exact_totals_from_unknown_counts(session):
    plan = _make_local_plan(session)
    known = _make_allocation(session, plan.id, policy_reference="K1", minimum_dwellings=100)
    unknown = _make_allocation(session, plan.id, policy_reference="K2")  # no capacity stated at all

    context = build_allocation_report_context(session, [known.id, unknown.id])

    assert context.aggregates.exact_capacity_total == 100
    assert context.aggregates.exact_capacity_count == 1
    assert context.aggregates.unknown_capacity_count == 1


def test_aggregates_plan_status_and_activity_counts(session):
    adopted_plan = _make_local_plan(session, status="adopted")
    emerging_plan = _make_local_plan(session, plan_name="Emerging Plan", status="draft_consultation")
    adopted_alloc = _make_allocation(session, adopted_plan.id, policy_reference="AD1")
    emerging_alloc = _make_allocation(session, emerging_plan.id, policy_reference="EM1")
    site = _make_site(session)
    _make_relationship(session, adopted_alloc.id, site.id)
    _make_app(session, site.id, reference="APP/1")

    context = build_allocation_report_context(session, [adopted_alloc.id, emerging_alloc.id])

    assert context.aggregates.adopted_count == 1
    assert context.aggregates.emerging_count == 1
    assert context.aggregates.allocations_with_linked_activity == 1
    assert context.aggregates.allocations_with_no_identified_activity == 1


# --- Pre-merge semantic hardening: capacity range aggregation (Section 10) --
# A ranged allocation's capacity_value is format_capacity's own existing
# upper-bound convention (e.g. 15000 for "8,400-15,000") - these tests prove
# it can never be silently summed into a total presented as exact.

def test_exact_capacity_contributes_to_the_exact_aggregate(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=300)
    context = build_allocation_report_context(session, [allocation.id])

    assert context.aggregates.exact_capacity_total == 300
    assert context.aggregates.exact_capacity_count == 1
    assert context.aggregates.ranged_capacity_count == 0


def test_ranged_capacity_is_not_aggregated_as_an_exact_upper_bound(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=8400, maximum_capacity=15000)
    context = build_allocation_report_context(session, [allocation.id])

    # The upper bound (15000) must NOT appear in exact_capacity_total - the
    # range contributes zero to it, and is counted separately instead.
    assert context.aggregates.exact_capacity_total == 0
    assert context.aggregates.exact_capacity_count == 0
    assert context.aggregates.ranged_capacity_count == 1
    # The individual entry itself still carries the real range, untouched.
    [entry] = context.entries
    assert entry.capacity_kind == "range"
    assert entry.capacity_value == 15000
    assert entry.capacity_display == "8,400–15,000 homes"


def test_multiple_exact_allocations_aggregate_correctly(session):
    plan = _make_local_plan(session)
    a1 = _make_allocation(session, plan.id, policy_reference="E1", minimum_dwellings=100)
    a2 = _make_allocation(session, plan.id, policy_reference="E2", minimum_dwellings=250)
    a3 = _make_allocation(session, plan.id, policy_reference="E3", indicative_capacity=50)

    context = build_allocation_report_context(session, [a1.id, a2.id, a3.id])

    assert context.aggregates.exact_capacity_total == 400
    assert context.aggregates.exact_capacity_count == 3


def test_mixed_exact_ranged_and_unknown_population_remains_evidence_faithful(session):
    plan = _make_local_plan(session)
    exact = _make_allocation(session, plan.id, policy_reference="M1", minimum_dwellings=100)
    ranged = _make_allocation(session, plan.id, policy_reference="M2", minimum_dwellings=8400, maximum_capacity=15000)
    unknown = _make_allocation(session, plan.id, policy_reference="M3")

    context = build_allocation_report_context(session, [exact.id, ranged.id, unknown.id])

    # Only the genuinely exact allocation's 100 contributes - the range's
    # 15000 upper bound and the unknown allocation are both excluded from
    # the exact total, each accounted for in its own separate count.
    assert context.aggregates.exact_capacity_total == 100
    assert context.aggregates.exact_capacity_count == 1
    assert context.aggregates.ranged_capacity_count == 1
    assert context.aggregates.unknown_capacity_count == 1
    assert context.aggregates.allocation_count == 3


def test_unknown_capacity_is_not_silently_treated_as_zero(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)  # no capacity stated at all
    context = build_allocation_report_context(session, [allocation.id])

    assert context.aggregates.exact_capacity_total == 0  # correctly empty, not a fabricated allocation total
    assert context.aggregates.unknown_capacity_count == 1  # the allocation is accounted for, not silently dropped


def test_review_required_residual_capacity_excluded_from_the_residual_aggregate(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=1000)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id, review_status="needs_confirmation")
    app = _make_app(session, site.id, reference="APP/1")
    session.add(SchemeIntelligence(application_id=app.id, total_units_final=300, core_intelligence_complete=True))
    session.commit()

    context = build_allocation_report_context(session, [allocation.id])

    # The entry's own residual is None (review_required, never a
    # manufactured number - see test_needs_confirmation_relationship_
    # forces_review_required_coverage_not_a_confident_number above); the
    # AGGREGATE must reflect that too, not silently sum a None as zero.
    assert context.aggregates.indicative_residual_capacity_known_total == 0
    assert context.aggregates.indicative_residual_capacity_unknown_count == 1


def test_ranged_csv_output_preserves_the_range_not_a_bare_upper_bound(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=8400, maximum_capacity=15000)
    context = build_allocation_report_context(session, [allocation.id])
    [row] = to_csv_rows(context)

    assert row["Allocation Capacity"] == "8,400–15,000 homes"
    assert row["Allocation Capacity"] != "15000"
    assert row["Allocation Capacity"] != "15,000"


def test_aggregates_dataclass_has_no_field_that_could_blend_ranges_into_an_exact_total(session):
    """Structural safety (Section 9/10H) - the ambiguous field this
    amendment removed (a single "capacity_known_total" blending exact
    figures and range upper bounds) must not exist at all, so a future
    PDF/AI consumer cannot accidentally reach for it and reproduce the
    exact bug this amendment fixes."""
    import dataclasses

    from app.reporting.allocation_report import AllocationReportAggregates

    field_names = {f.name for f in dataclasses.fields(AllocationReportAggregates)}
    assert "capacity_known_total" not in field_names
    assert "capacity_unknown_count" not in field_names
    assert {"exact_capacity_total", "exact_capacity_count", "ranged_capacity_count", "unknown_capacity_count"} <= field_names


# --- Pre-merge semantic hardening: review-pending party evidence (Section 11)

def test_trusted_applicant_appears_correctly(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id)
    _make_app(session, site.id, reference="APP/1", applicant_name_raw="Trusted Applicant Ltd")

    [entry] = build_allocation_report_context(session, [allocation.id]).entries
    assert entry.applicant_evidence[0].entity_name == "Trusted Applicant Ltd"


def test_trusted_developer_appears_correctly_via_the_trust_partition_property(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id)
    _make_control(session, site_id=site.id, entity_name_raw="Trusted Developer Ltd", role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")

    [entry] = build_allocation_report_context(session, [allocation.id]).entries
    assert [e.entity_name_raw for e in entry.trusted_ownership_evidence] == ["Trusted Developer Ltd"]
    assert entry.review_pending_ownership_evidence == []


def test_needs_review_developer_is_not_presented_as_a_settled_known_developer(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id)
    _make_control(
        session, site_id=site.id, entity_name_raw="Uncertain Developer Ltd", role="DEVELOPER",
        evidence_category="S106_DEFINED_DEVELOPER", review_status="needs_confirmation",
    )

    context = build_allocation_report_context(session, [allocation.id])
    [entry] = context.entries

    # Structurally partitioned: a needs_review Developer is never in
    # trusted_ownership_evidence, only in review_pending_ownership_evidence.
    assert entry.trusted_ownership_evidence == []
    assert [e.entity_name_raw for e in entry.review_pending_ownership_evidence] == ["Uncertain Developer Ltd"]

    # And the CSV's "Known Developer(s)" column - the one a spreadsheet
    # user reads as confident fact - must not contain it at all.
    [row] = to_csv_rows(context)
    assert row["Known Developer(s)"] == ""
    assert "Uncertain Developer Ltd" not in row["Known Developer(s)"]


def test_needs_review_ownership_evidence_retains_uncertainty_marker_in_general_evidence_column(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id)
    _make_control(
        session, site_id=site.id, entity_name_raw="Uncertain Owner Ltd", role="OWNER",
        evidence_category="S106_DEFINED_OWNER", review_status="needs_confirmation",
    )

    context = build_allocation_report_context(session, [allocation.id])
    [row] = to_csv_rows(context)

    # Still visible (never simply hidden) in the general evidence column,
    # but explicitly qualified - never presented identically to trusted evidence.
    assert "Uncertain Owner Ltd" in row["Ownership / Control Evidence"]
    assert "needs confirmation" in row["Ownership / Control Evidence"]


def test_rejected_relationship_remains_excluded_from_both_trust_partitions(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id)
    _make_control(
        session, site_id=site.id, entity_name_raw="Rejected Ltd", role="DEVELOPER",
        evidence_category="S106_DEFINED_DEVELOPER", review_status="rejected",
    )

    [entry] = build_allocation_report_context(session, [allocation.id]).entries
    assert entry.trusted_ownership_evidence == []
    assert entry.review_pending_ownership_evidence == []


def test_csv_does_not_silently_flatten_trusted_and_review_pending_developer_evidence(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id)
    _make_control(session, site_id=site.id, entity_name_raw="Confirmed Developer Ltd", role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")
    _make_control(
        session, site_id=site.id, entity_name_raw="Unconfirmed Developer Ltd", role="DEVELOPER",
        evidence_category="S106_DEFINED_DEVELOPER", review_status="needs_confirmation",
    )

    context = build_allocation_report_context(session, [allocation.id])
    [row] = to_csv_rows(context)

    assert "Confirmed Developer Ltd" in row["Known Developer(s)"]
    assert "Unconfirmed Developer Ltd" not in row["Known Developer(s)"]
    assert "Unconfirmed Developer Ltd" in row["Ownership / Control Evidence"]
    assert "needs confirmation" in row["Ownership / Control Evidence"]


def test_applicant_remains_distinct_from_developer_after_trust_partitioning(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id)
    _make_app(session, site.id, reference="APP/1", applicant_name_raw="Applicant Co")
    _make_control(session, site_id=site.id, entity_name_raw="Developer Co", role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")

    context = build_allocation_report_context(session, [allocation.id])
    [row] = to_csv_rows(context)

    assert "Applicant Co" in row["Known Applicant(s)"]
    assert "Applicant Co" not in row["Known Developer(s)"]
    assert "Developer Co" in row["Known Developer(s)"]
    assert "Developer Co" not in row["Known Applicant(s)"]


# --- CSV tests (Section 26) ---------------------------------------------------

def test_csv_rows_shortlisted_only_and_correct_column_set(session):
    plan = _make_local_plan(session)
    a1 = _make_allocation(session, plan.id, policy_reference="A1")
    _make_allocation(session, plan.id, policy_reference="A2")  # not shortlisted

    context = build_allocation_report_context(session, [a1.id])
    rows = to_csv_rows(context)

    assert len(rows) == 1
    assert list(rows[0].keys()) == CSV_COLUMNS


def test_csv_applicant_not_promoted_to_developer_and_multi_party_serialization(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    site = _make_site(session)
    _make_relationship(session, allocation.id, site.id)
    _make_app(session, site.id, reference="APP/1", applicant_name_raw="Entity A")
    _make_app(session, site.id, reference="APP/2", applicant_name_raw="Entity B")
    _make_control(session, site_id=site.id, entity_name_raw="Entity C", role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")

    context = build_allocation_report_context(session, [allocation.id])
    [row] = to_csv_rows(context)

    assert "Entity A [Applicant]" in row["Known Applicant(s)"]
    assert "Entity B [Applicant]" in row["Known Applicant(s)"]
    assert "Entity C" not in row["Known Applicant(s)"]  # Developer evidence never appears in the Applicant column
    assert "Entity C" in row["Known Developer(s)"]
    assert "Entity A" not in row["Known Developer(s)"]  # Applicant never promoted into the Developer column


def test_csv_no_linked_application_row_exports_normally(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    context = build_allocation_report_context(session, [allocation.id])
    [row] = to_csv_rows(context)

    assert row["Planning Activity"] == "No identified activity"
    assert row["Linked Application Count"] == 0


def test_csv_missing_ai_summary_does_not_block_export(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    context = build_allocation_report_context(session, [allocation.id])
    [row] = to_csv_rows(context)

    assert row["AI Summary Available"] == "No"
    assert row["AI Intelligence Headline"] == ""


def test_csv_output_order_is_deterministic(session):
    plan = _make_local_plan(session)
    a3 = _make_allocation(session, plan.id, policy_reference="A3")
    a1 = _make_allocation(session, plan.id, policy_reference="A1")
    a2 = _make_allocation(session, plan.id, policy_reference="A2")

    # Deterministic means "same, well-defined order every time" (here:
    # allocation_id order, matching AllocationReportContext.entries' own
    # documented sort) - not "alphabetical by reference", which the
    # shortlist's own add order (a3, a1, a2) deliberately does not follow.
    expected_order = [r["Allocation Reference"] for r in to_csv_rows(build_allocation_report_context(session, [a3.id, a1.id, a2.id]))]
    repeated_order = [r["Allocation Reference"] for r in to_csv_rows(build_allocation_report_context(session, [a2.id, a3.id, a1.id]))]

    assert expected_order == repeated_order == ["A3", "A1", "A2"]  # id order: a3, a1, a2 were created in that sequence


def test_csv_unicode_and_special_characters_handled_safely(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, site_name="Château-sur-Mère, Zone \"A\", 50% affordable")
    context = build_allocation_report_context(session, [allocation.id])
    csv_bytes = to_csv_bytes(context)

    decoded = csv_bytes.decode("utf-8-sig")
    assert "Château-sur-Mère" in decoded


def test_csv_bytes_produces_valid_csv_with_header(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    context = build_allocation_report_context(session, [allocation.id])
    csv_bytes = to_csv_bytes(context)

    decoded = csv_bytes.decode("utf-8-sig")
    lines = decoded.strip().splitlines()
    assert lines[0] == ",".join(CSV_COLUMNS)
    assert len(lines) == 2  # header + one data row


def test_csv_makes_zero_openai_calls(session, monkeypatch):
    def _fail(*args, **kwargs):
        raise AssertionError("OpenAI must never be called for CSV export")

    monkeypatch.setattr("openai.OpenAI", _fail, raising=False)

    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    _make_summary(session, allocation.id, headline="Existing persisted headline.")

    context = build_allocation_report_context(session, [allocation.id])
    to_csv_bytes(context)  # must not raise / must not attempt any OpenAI call


# --- Batching (Section 27) ----------------------------------------------------

def _build_shortlist_of(session, n: int, *, with_evidence: bool = True, prefix: str = "") -> list[int]:
    plan = _make_local_plan(session, plan_name=f"Batch Plan {prefix}")
    ids = []
    for i in range(n):
        allocation = _make_allocation(session, plan.id, policy_reference=f"{prefix}REF-{i}", minimum_dwellings=100)
        ids.append(allocation.id)
        if with_evidence:
            site = _make_site(session, address=f"{prefix}{i} Batch Street")
            _make_relationship(session, allocation.id, site.id)
            app = _make_app(session, site.id, reference=f"{prefix}APP-{i}", applicant_name_raw=f"Applicant {i}")
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


def test_query_count_does_not_scale_linearly_with_shortlist_size(session):
    """Bounded/non-linear growth assertion (Section 27) rather than a
    brittle absolute count - proves party/AI-summary reads are batched, not
    one-query-per-allocation, across representative shortlist sizes."""
    ids_5 = _build_shortlist_of(session, 5, prefix="A-")
    count_5 = _count_select_queries(session, lambda: build_allocation_report_context(session, ids_5))

    ids_25 = _build_shortlist_of(session, 25, prefix="B-")
    count_25 = _count_select_queries(session, lambda: build_allocation_report_context(session, ids_25))

    # If any path were one-query-per-allocation, 25 allocations would issue
    # roughly 5x the queries of 5 allocations for that path alone; the
    # actual query count here is dominated by a small, FIXED set of batched
    # queries (LocalPlanSite, coverage's own 3-4, AI summaries, ownership),
    # so growth from 5->25 allocations (5x the population) must be far
    # less than 5x the query count.
    assert count_25 < count_5 * 2, (
        f"query count grew from {count_5} (5 allocations) to {count_25} (25 allocations) - "
        "this looks like an N+1 pattern, not batched reads"
    )


def test_query_count_for_50_allocations_remains_bounded(session):
    ids_50 = _build_shortlist_of(session, 50)
    count_50 = _count_select_queries(session, lambda: build_allocation_report_context(session, ids_50))
    # A fixed handful of batched queries regardless of population - a
    # generous ceiling, not a brittle exact count (repository setup/eager-
    # load shape can add a query or two without indicating a real N+1).
    assert count_50 < 15, f"expected a small, fixed query count for 50 allocations, got {count_50}"
