"""Local Plan Sites Filter Refinement tests - Planning applications /
Planning activity filters and the new Allocation capacity bands
(app.reporting.allocation_discovery). Every test runs against the shared
in-memory SQLite `session` fixture (tests/conftest.py) - never the real
production database.
"""
from __future__ import annotations

import inspect

from sqlalchemy import event

from app.db.models import AllocationSiteRelationship, Application, LocalPlan, LocalPlanSite, SchemeIntelligence, Site
from app.reporting import allocation_discovery as discovery_module
from app.reporting.allocation_discovery import (
    CAPACITY_BANDS,
    PLANNING_ACTIVITY_IDENTIFIED,
    PLANNING_ACTIVITY_NONE,
    PLANNING_ACTIVITY_REVIEW_REQUIRED,
    apply_filters,
    build_allocation_discovery,
    capacity_band_range,
    compute_categories,
    has_trusted_linked_application,
    planning_activity_status,
    search_allocations,
)


def _make_local_plan(session, council_code="testcouncil", status="adopted") -> LocalPlan:
    plan = LocalPlan(council_code=council_code, plan_name="Test Local Plan", status=status, raw_status=status)
    session.add(plan)
    session.commit()
    return plan


def _make_allocation(session, local_plan_id, *, council_code="testcouncil", policy_reference="HOM 1.1",
                      site_name="Land off Test Road", minimum_dwellings=None) -> LocalPlanSite:
    allocation = LocalPlanSite(
        council_code=council_code, local_plan_id=local_plan_id, policy_reference=policy_reference,
        site_name=site_name, plan_name="Test Local Plan", plan_status="adopted", minimum_dwellings=minimum_dwellings,
    )
    session.add(allocation)
    session.commit()
    return allocation


def _make_site(session, address="1 Test Street") -> Site:
    site = Site(council_code="testcouncil", canonical_address=address.lower(), display_address=address)
    session.add(site)
    session.commit()
    return site


def _make_app_with_capacity(session, site_id, reference, units) -> Application:
    app = Application(council_code="testcouncil", reference=reference, site_id=site_id)
    session.add(app)
    session.commit()
    session.add(SchemeIntelligence(application_id=app.id, total_units_final=units, core_intelligence_complete=True))
    session.commit()
    return app


def _make_relationship(session, *, allocation_id, site_id, review_status="auto_applied") -> AllocationSiteRelationship:
    rel = AllocationSiteRelationship(
        allocation_id=allocation_id, site_id=site_id, evidence_basis="document_confirmed_site", review_status=review_status,
    )
    session.add(rel)
    session.commit()
    return rel


# ---------------------------------------------------------------------------
# Items 1-3 - linked-application filter
# ---------------------------------------------------------------------------


def test_linked_application_filter_any_applies_no_constraint(session):
    plan = _make_local_plan(session)
    linked_alloc = _make_allocation(session, plan.id, policy_reference="REF-A", site_name="Linked Allocation")
    site = _make_site(session)
    _make_relationship(session, allocation_id=linked_alloc.id, site_id=site.id)
    _make_app_with_capacity(session, site.id, "APP/1", 50)
    unlinked_alloc = _make_allocation(session, plan.id, policy_reference="REF-B", site_name="Unlinked Allocation")

    result = build_allocation_discovery(session)
    filtered = apply_filters(result["cards"], {"application_linkage": None})
    assert len(filtered) == 2


def test_linked_application_filter_linked_only(session):
    plan = _make_local_plan(session)
    linked_alloc = _make_allocation(session, plan.id, policy_reference="REF-A", site_name="Linked Allocation")
    site = _make_site(session)
    _make_relationship(session, allocation_id=linked_alloc.id, site_id=site.id)
    _make_app_with_capacity(session, site.id, "APP/1", 50)
    _make_allocation(session, plan.id, policy_reference="REF-B", site_name="Unlinked Allocation")

    result = build_allocation_discovery(session)
    filtered = apply_filters(result["cards"], {"application_linkage": "linked"})
    assert [c["id"] for c in filtered] == [linked_alloc.id]


def test_linked_application_filter_not_linked_only(session):
    plan = _make_local_plan(session)
    linked_alloc = _make_allocation(session, plan.id, policy_reference="REF-A", site_name="Linked Allocation")
    site = _make_site(session)
    _make_relationship(session, allocation_id=linked_alloc.id, site_id=site.id)
    _make_app_with_capacity(session, site.id, "APP/1", 50)
    unlinked_alloc = _make_allocation(session, plan.id, policy_reference="REF-B", site_name="Unlinked Allocation")

    result = build_allocation_discovery(session)
    filtered = apply_filters(result["cards"], {"application_linkage": "not_linked"})
    assert [c["id"] for c in filtered] == [unlinked_alloc.id]


# ---------------------------------------------------------------------------
# Item 4 - rejected AllocationSiteRelationship does not count as linked
# ---------------------------------------------------------------------------


def test_rejected_relationship_does_not_count_as_linked(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, policy_reference="REF-A", site_name="Rejected Relationship Allocation")
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="rejected")
    _make_app_with_capacity(session, site.id, "APP/1", 50)
    session.commit()

    result = build_allocation_discovery(session)
    card = next(c for c in result["cards"] if c["id"] == allocation.id)
    assert has_trusted_linked_application(card) is False


def test_gallery_badge_field_matches_recomputed_value_not_a_stale_snapshot(session):
    """Regression for a genuine ordering bug caught during this task's own
    live verification: build_allocation_card used to compute card[
    "show_linked_application_tag"]/card["matching_attributes"] BEFORE
    card["development_coverage"] was set on the same dict, so
    has_trusted_linked_application(card) silently fell back to the legacy
    matched_site_id path at that call site even though development_
    coverage was correctly AllocationSiteRelationship-based moments
    later - a rejected relationship's Site still showed the "Planning
    application linked" gallery badge live on the real page. Both fields
    must equal what recomputing has_trusted_linked_application against
    the FINAL card produces, not a value frozen from an earlier,
    incomplete state of the same dict."""
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, policy_reference="REF-A", site_name="Badge Ordering Allocation")
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="rejected")
    _make_app_with_capacity(session, site.id, "APP/1", 50)
    # The exact real-world trigger: a stale legacy convenience pointer
    # still set even though the relationship itself is rejected.
    allocation.matched_site_id = site.id
    session.commit()

    result = build_allocation_discovery(session)
    card = next(c for c in result["cards"] if c["id"] == allocation.id)

    expected = has_trusted_linked_application(card)
    assert expected is False
    assert card["show_linked_application_tag"] == expected
    assert card["matching_attributes"]["has_linked_application"] == expected


def test_legacy_matched_site_with_no_relationship_row_still_trusted(session):
    """The other half of the ordering-bug fix: a matched_site_id set
    entirely outside Stage 2D (the pre-Stage-2D app.policy.
    site_match_review.confirm_site_match flow, which never writes an
    AllocationSiteRelationship row at all) must remain trusted - an empty
    development_coverage is genuinely ambiguous on its own (no
    relationship row ever existed vs the one relationship that existed
    was rejected), and only matched_site_relationship_rejected being
    True should ever override the legacy signal to "not linked"."""
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, policy_reference="REF-LEGACY", site_name="Legacy Confirmed Allocation")
    site = _make_site(session, "Legacy Matched Site")
    allocation.matched_site_id = site.id
    allocation.review_status = "confirmed"
    _make_app_with_capacity(session, site.id, "APP/LEGACY", 50)
    session.commit()
    # Deliberately NO AllocationSiteRelationship row created at all.

    result = build_allocation_discovery(session)
    card = next(c for c in result["cards"] if c["id"] == allocation.id)

    assert card["matched_site_relationship_rejected"] is False
    assert card["development_coverage"].number_of_related_sites == 0
    assert has_trusted_linked_application(card) is True
    assert card["show_linked_application_tag"] is True


# ---------------------------------------------------------------------------
# Items 5/6/7 - JPA10 / JPA12 / North of Mosley Common regressions
# ---------------------------------------------------------------------------


def test_jpa10_regression_rejected_relationship_shows_no_linked_application(session):
    """Mirrors the real production case: an allocation (JPA10 Beal Valley)
    whose AllocationSiteRelationship to a Site (Bullcote Lane) has been
    rejected must never show as linked, even though that Site has a real
    Application and even though a stale matched_site_id snapshot might
    still point at it."""
    plan = _make_local_plan(session)
    jpa10 = _make_allocation(session, plan.id, policy_reference="JPA 10", site_name="Beal Valley", minimum_dwellings=1930)
    site = _make_site(session, "Land South Of Bullcote Lane")
    _make_relationship(session, allocation_id=jpa10.id, site_id=site.id, review_status="rejected")
    _make_app_with_capacity(session, site.id, "FUL/355603/26", 248)
    # Stale legacy convenience pointer, exactly as found in real production -
    # must NOT make has_trusted_linked_application say "linked".
    jpa10.matched_site_id = site.id
    session.commit()

    result = build_allocation_discovery(session)
    card = next(c for c in result["cards"] if c["id"] == jpa10.id)
    assert has_trusted_linked_application(card) is False
    assert card["development_coverage"].number_of_related_sites == 0


def test_jpa12_regression_genuine_relationship_still_shows_linked(session):
    """The SAME Site's genuine relationship to a DIFFERENT allocation
    (JPA12 Broadbent Moss) must be entirely unaffected by JPA10's
    rejection."""
    plan = _make_local_plan(session)
    jpa10 = _make_allocation(session, plan.id, policy_reference="JPA 10", site_name="Beal Valley", minimum_dwellings=1930)
    jpa12 = _make_allocation(session, plan.id, policy_reference="JPA 12", site_name="Broadbent Moss", minimum_dwellings=1250)
    site = _make_site(session, "Land South Of Bullcote Lane")
    _make_relationship(session, allocation_id=jpa10.id, site_id=site.id, review_status="rejected")
    _make_relationship(session, allocation_id=jpa12.id, site_id=site.id, review_status="auto_applied")
    _make_app_with_capacity(session, site.id, "FUL/355603/26", 248)
    session.commit()

    result = build_allocation_discovery(session)
    jpa12_card = next(c for c in result["cards"] if c["id"] == jpa12.id)
    assert has_trusted_linked_application(jpa12_card) is True
    assert jpa12_card["development_coverage"].number_of_related_sites == 1
    assert jpa12_card["development_coverage"].identified_application_capacity == 248


def test_north_of_mosley_common_regression_unaffected(session):
    """An allocation entirely uninvolved in the JPA10/JPA12 cleanup keeps
    recognising its own genuine linked Application(s)."""
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, policy_reference="JPA 32", site_name="North of Mosley Common", minimum_dwellings=1100)
    site = _make_site(session, "Land North Of Mosley Common")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="auto_applied")
    _make_app_with_capacity(session, site.id, "A/25/099409/RMMAJ", 244)
    session.commit()

    result = build_allocation_discovery(session)
    card = next(c for c in result["cards"] if c["id"] == allocation.id)
    assert has_trusted_linked_application(card) is True
    assert card["development_coverage"].identified_application_capacity == 244


# ---------------------------------------------------------------------------
# Item 8 - "No Linked Application" tab must use the SAME definition as the filter
# ---------------------------------------------------------------------------


def test_no_linked_application_tab_matches_filter_definition(session):
    plan = _make_local_plan(session)
    linked_alloc = _make_allocation(session, plan.id, policy_reference="REF-A", site_name="Linked Allocation")
    site = _make_site(session)
    _make_relationship(session, allocation_id=linked_alloc.id, site_id=site.id)
    _make_app_with_capacity(session, site.id, "APP/1", 50)
    unlinked_alloc = _make_allocation(session, plan.id, policy_reference="REF-B", site_name="Unlinked Allocation")
    rejected_alloc = _make_allocation(session, plan.id, policy_reference="REF-C", site_name="Rejected Allocation")
    rejected_site = _make_site(session, "Rejected Site")
    _make_relationship(session, allocation_id=rejected_alloc.id, site_id=rejected_site.id, review_status="rejected")
    _make_app_with_capacity(session, rejected_site.id, "APP/2", 30)

    cards = build_allocation_discovery(session)["cards"]
    filter_result = {c["id"] for c in apply_filters(cards, {"application_linkage": "not_linked"})}
    tab_categories = compute_categories(cards)
    tab_result = {c["id"] for cat in tab_categories if cat["key"] == "no_linked_application" for c in cat["cards"]}

    assert filter_result == tab_result == {unlinked_alloc.id, rejected_alloc.id}


# ---------------------------------------------------------------------------
# Items 9-16 - each capacity band
# ---------------------------------------------------------------------------


def _card_for_capacity(session, plan, dwellings, *, ref):
    allocation = _make_allocation(session, plan.id, policy_reference=ref, site_name=f"Site {ref}", minimum_dwellings=dwellings)
    return allocation


def test_capacity_bands_are_the_exact_approved_set():
    labels = [label for label, _, _ in CAPACITY_BANDS]
    assert labels == [
        "Any", "Under 25 homes", "25–49 homes", "50–99 homes", "100–199 homes",
        "200–499 homes", "500–999 homes", "1,000–1,999 homes", "2,000+ homes",
    ]


def test_band_under_25(session):
    plan = _make_local_plan(session)
    inside = _card_for_capacity(session, plan, 10, ref="IN")
    outside = _card_for_capacity(session, plan, 30, ref="OUT")
    session.commit()
    cmin, cmax = capacity_band_range("Under 25 homes")
    filtered = apply_filters(build_allocation_discovery(session)["cards"], {"capacity_min": cmin, "capacity_max": cmax})
    assert [c["id"] for c in filtered] == [inside.id]


def test_band_25_49(session):
    plan = _make_local_plan(session)
    inside = _card_for_capacity(session, plan, 40, ref="IN")
    _card_for_capacity(session, plan, 10, ref="LOW")
    _card_for_capacity(session, plan, 60, ref="HIGH")
    session.commit()
    cmin, cmax = capacity_band_range("25–49 homes")
    filtered = apply_filters(build_allocation_discovery(session)["cards"], {"capacity_min": cmin, "capacity_max": cmax})
    assert [c["id"] for c in filtered] == [inside.id]


def test_band_50_99(session):
    plan = _make_local_plan(session)
    inside = _card_for_capacity(session, plan, 75, ref="IN")
    session.commit()
    cmin, cmax = capacity_band_range("50–99 homes")
    filtered = apply_filters(build_allocation_discovery(session)["cards"], {"capacity_min": cmin, "capacity_max": cmax})
    assert [c["id"] for c in filtered] == [inside.id]


def test_band_100_199(session):
    plan = _make_local_plan(session)
    inside = _card_for_capacity(session, plan, 150, ref="IN")
    session.commit()
    cmin, cmax = capacity_band_range("100–199 homes")
    filtered = apply_filters(build_allocation_discovery(session)["cards"], {"capacity_min": cmin, "capacity_max": cmax})
    assert [c["id"] for c in filtered] == [inside.id]


def test_band_200_499(session):
    plan = _make_local_plan(session)
    inside = _card_for_capacity(session, plan, 300, ref="IN")
    session.commit()
    cmin, cmax = capacity_band_range("200–499 homes")
    filtered = apply_filters(build_allocation_discovery(session)["cards"], {"capacity_min": cmin, "capacity_max": cmax})
    assert [c["id"] for c in filtered] == [inside.id]


def test_band_500_999(session):
    plan = _make_local_plan(session)
    inside = _card_for_capacity(session, plan, 750, ref="IN")
    session.commit()
    cmin, cmax = capacity_band_range("500–999 homes")
    filtered = apply_filters(build_allocation_discovery(session)["cards"], {"capacity_min": cmin, "capacity_max": cmax})
    assert [c["id"] for c in filtered] == [inside.id]


def test_band_1000_1999(session):
    plan = _make_local_plan(session)
    inside = _card_for_capacity(session, plan, 1500, ref="IN")
    session.commit()
    cmin, cmax = capacity_band_range("1,000–1,999 homes")
    filtered = apply_filters(build_allocation_discovery(session)["cards"], {"capacity_min": cmin, "capacity_max": cmax})
    assert [c["id"] for c in filtered] == [inside.id]


def test_band_2000_plus(session):
    plan = _make_local_plan(session)
    inside = _card_for_capacity(session, plan, 5000, ref="IN")
    session.commit()
    cmin, cmax = capacity_band_range("2,000+ homes")
    filtered = apply_filters(build_allocation_discovery(session)["cards"], {"capacity_min": cmin, "capacity_max": cmax})
    assert [c["id"] for c in filtered] == [inside.id]


# ---------------------------------------------------------------------------
# Items 17-22 - exact boundary values
# ---------------------------------------------------------------------------


def test_boundary_49_50(session):
    plan = _make_local_plan(session)
    forty_nine = _card_for_capacity(session, plan, 49, ref="49")
    fifty = _card_for_capacity(session, plan, 50, ref="50")
    session.commit()
    cards = build_allocation_discovery(session)["cards"]
    low_min, low_max = capacity_band_range("25–49 homes")
    high_min, high_max = capacity_band_range("50–99 homes")
    assert [c["id"] for c in apply_filters(cards, {"capacity_min": low_min, "capacity_max": low_max})] == [forty_nine.id]
    assert [c["id"] for c in apply_filters(cards, {"capacity_min": high_min, "capacity_max": high_max})] == [fifty.id]


def test_boundary_99_100(session):
    plan = _make_local_plan(session)
    ninety_nine = _card_for_capacity(session, plan, 99, ref="99")
    one_hundred = _card_for_capacity(session, plan, 100, ref="100")
    session.commit()
    cards = build_allocation_discovery(session)["cards"]
    low_min, low_max = capacity_band_range("50–99 homes")
    high_min, high_max = capacity_band_range("100–199 homes")
    assert [c["id"] for c in apply_filters(cards, {"capacity_min": low_min, "capacity_max": low_max})] == [ninety_nine.id]
    assert [c["id"] for c in apply_filters(cards, {"capacity_min": high_min, "capacity_max": high_max})] == [one_hundred.id]


def test_boundary_199_200(session):
    plan = _make_local_plan(session)
    a = _card_for_capacity(session, plan, 199, ref="199")
    b = _card_for_capacity(session, plan, 200, ref="200")
    session.commit()
    cards = build_allocation_discovery(session)["cards"]
    low_min, low_max = capacity_band_range("100–199 homes")
    high_min, high_max = capacity_band_range("200–499 homes")
    assert [c["id"] for c in apply_filters(cards, {"capacity_min": low_min, "capacity_max": low_max})] == [a.id]
    assert [c["id"] for c in apply_filters(cards, {"capacity_min": high_min, "capacity_max": high_max})] == [b.id]


def test_boundary_499_500(session):
    plan = _make_local_plan(session)
    a = _card_for_capacity(session, plan, 499, ref="499")
    b = _card_for_capacity(session, plan, 500, ref="500")
    session.commit()
    cards = build_allocation_discovery(session)["cards"]
    low_min, low_max = capacity_band_range("200–499 homes")
    high_min, high_max = capacity_band_range("500–999 homes")
    assert [c["id"] for c in apply_filters(cards, {"capacity_min": low_min, "capacity_max": low_max})] == [a.id]
    assert [c["id"] for c in apply_filters(cards, {"capacity_min": high_min, "capacity_max": high_max})] == [b.id]


def test_boundary_999_1000(session):
    plan = _make_local_plan(session)
    a = _card_for_capacity(session, plan, 999, ref="999")
    b = _card_for_capacity(session, plan, 1000, ref="1000")
    session.commit()
    cards = build_allocation_discovery(session)["cards"]
    low_min, low_max = capacity_band_range("500–999 homes")
    high_min, high_max = capacity_band_range("1,000–1,999 homes")
    assert [c["id"] for c in apply_filters(cards, {"capacity_min": low_min, "capacity_max": low_max})] == [a.id]
    assert [c["id"] for c in apply_filters(cards, {"capacity_min": high_min, "capacity_max": high_max})] == [b.id]


def test_boundary_1999_2000(session):
    plan = _make_local_plan(session)
    a = _card_for_capacity(session, plan, 1999, ref="1999")
    b = _card_for_capacity(session, plan, 2000, ref="2000")
    session.commit()
    cards = build_allocation_discovery(session)["cards"]
    low_min, low_max = capacity_band_range("1,000–1,999 homes")
    high_min, high_max = capacity_band_range("2,000+ homes")
    assert [c["id"] for c in apply_filters(cards, {"capacity_min": low_min, "capacity_max": low_max})] == [a.id]
    assert [c["id"] for c in apply_filters(cards, {"capacity_min": high_min, "capacity_max": high_max})] == [b.id]


# ---------------------------------------------------------------------------
# Items 23/24 - unknown capacity behaviour
# ---------------------------------------------------------------------------


def test_unknown_capacity_included_under_any(session):
    plan = _make_local_plan(session)
    unknown = _card_for_capacity(session, plan, None, ref="UNKNOWN")
    known = _card_for_capacity(session, plan, 100, ref="KNOWN")
    session.commit()
    cmin, cmax = capacity_band_range("Any")
    filtered = apply_filters(build_allocation_discovery(session)["cards"], {"capacity_min": cmin, "capacity_max": cmax})
    assert {c["id"] for c in filtered} == {unknown.id, known.id}


def test_unknown_capacity_excluded_under_numerical_band(session):
    plan = _make_local_plan(session)
    unknown = _card_for_capacity(session, plan, None, ref="UNKNOWN")
    known = _card_for_capacity(session, plan, 100, ref="KNOWN")
    session.commit()
    cmin, cmax = capacity_band_range("100–199 homes")
    filtered = apply_filters(build_allocation_discovery(session)["cards"], {"capacity_min": cmin, "capacity_max": cmax})
    assert [c["id"] for c in filtered] == [known.id]


# ---------------------------------------------------------------------------
# Items 25-28 - filter combinations
# ---------------------------------------------------------------------------


def test_capacity_and_council_combination(session):
    plan_a = _make_local_plan(session, council_code="councila")
    plan_b = _make_local_plan(session, council_code="councilb")
    match = _make_allocation(session, plan_a.id, council_code="councila", policy_reference="A1", site_name="Match", minimum_dwellings=150)
    _make_allocation(session, plan_a.id, council_code="councila", policy_reference="A2", site_name="Wrong capacity", minimum_dwellings=5000)
    _make_allocation(session, plan_b.id, council_code="councilb", policy_reference="B1", site_name="Wrong council", minimum_dwellings=150)
    session.commit()

    cards = build_allocation_discovery(session)["cards"]
    cmin, cmax = capacity_band_range("100–199 homes")
    filtered = apply_filters(cards, {"councils": ["councila"], "capacity_min": cmin, "capacity_max": cmax})
    assert [c["id"] for c in filtered] == [match.id]


def test_capacity_and_plan_status_combination(session):
    adopted_plan = _make_local_plan(session, status="adopted")
    emerging_plan = _make_local_plan(session, status="emerging draft")
    match = _make_allocation(session, adopted_plan.id, policy_reference="A1", site_name="Match", minimum_dwellings=150)
    _make_allocation(session, adopted_plan.id, policy_reference="A2", site_name="Wrong capacity", minimum_dwellings=5000)
    _make_allocation(session, emerging_plan.id, policy_reference="B1", site_name="Wrong status", minimum_dwellings=150)
    session.commit()

    cards = build_allocation_discovery(session)["cards"]
    cmin, cmax = capacity_band_range("100–199 homes")
    filtered = apply_filters(cards, {"plan_status_buckets": ["adopted"], "capacity_min": cmin, "capacity_max": cmax})
    assert [c["id"] for c in filtered] == [match.id]


def test_capacity_and_linked_application_combination(session):
    plan = _make_local_plan(session)
    match = _make_allocation(session, plan.id, policy_reference="A1", site_name="Match", minimum_dwellings=150)
    site = _make_site(session)
    _make_relationship(session, allocation_id=match.id, site_id=site.id)
    _make_app_with_capacity(session, site.id, "APP/1", 50)
    _make_allocation(session, plan.id, policy_reference="A2", site_name="Right capacity, no link", minimum_dwellings=150)
    session.commit()

    cards = build_allocation_discovery(session)["cards"]
    cmin, cmax = capacity_band_range("100–199 homes")
    filtered = apply_filters(cards, {"application_linkage": "linked", "capacity_min": cmin, "capacity_max": cmax})
    assert [c["id"] for c in filtered] == [match.id]


def test_search_text_and_filters_compose(session):
    plan = _make_local_plan(session)
    match = _make_allocation(session, plan.id, policy_reference="A1", site_name="Northfield Gardens", minimum_dwellings=150)
    _make_allocation(session, plan.id, policy_reference="A2", site_name="Northfield Gardens Extension", minimum_dwellings=5000)
    _make_allocation(session, plan.id, policy_reference="B1", site_name="Southfield Meadow", minimum_dwellings=150)
    session.commit()

    cards = build_allocation_discovery(session)["cards"]
    searched = search_allocations(cards, "northfield")
    cmin, cmax = capacity_band_range("100–199 homes")
    filtered = apply_filters(searched, {"capacity_min": cmin, "capacity_max": cmax})
    assert [c["id"] for c in filtered] == [match.id]


# ---------------------------------------------------------------------------
# Planning activity filter (Section 4) - additional coverage beyond the
# 30-item minimum, since this is the second half of the required distinction.
# ---------------------------------------------------------------------------


def test_planning_activity_no_activity(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, policy_reference="A1", site_name="No Activity")
    session.commit()
    result = build_allocation_discovery(session)
    card = next(c for c in result["cards"] if c["id"] == allocation.id)
    assert planning_activity_status(card) == PLANNING_ACTIVITY_NONE


def test_planning_activity_identified(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, policy_reference="A1", site_name="Has Activity", minimum_dwellings=200)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    _make_app_with_capacity(session, site.id, "APP/1", 50)
    session.commit()
    result = build_allocation_discovery(session)
    card = next(c for c in result["cards"] if c["id"] == allocation.id)
    assert planning_activity_status(card) == PLANNING_ACTIVITY_IDENTIFIED


def test_planning_activity_review_required(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, policy_reference="A1", site_name="Disputed Activity", minimum_dwellings=200)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="needs_confirmation")
    _make_app_with_capacity(session, site.id, "APP/1", 50)
    session.commit()
    result = build_allocation_discovery(session)
    card = next(c for c in result["cards"] if c["id"] == allocation.id)
    assert planning_activity_status(card) == PLANNING_ACTIVITY_REVIEW_REQUIRED


def test_planning_activity_filter_wired_into_apply_filters(session):
    plan = _make_local_plan(session)
    no_activity = _make_allocation(session, plan.id, policy_reference="A1", site_name="No Activity")
    has_activity = _make_allocation(session, plan.id, policy_reference="A2", site_name="Has Activity", minimum_dwellings=200)
    site = _make_site(session)
    _make_relationship(session, allocation_id=has_activity.id, site_id=site.id)
    _make_app_with_capacity(session, site.id, "APP/1", 50)
    session.commit()

    cards = build_allocation_discovery(session)["cards"]
    filtered = apply_filters(cards, {"planning_activity": PLANNING_ACTIVITY_NONE})
    assert [c["id"] for c in filtered] == [no_activity.id]


# ---------------------------------------------------------------------------
# Item 29 - no N+1 regression
# ---------------------------------------------------------------------------


def _seed_allocations_with_relationships(session, plan, count: int, *, prefix: str) -> None:
    for i in range(count):
        allocation = _make_allocation(session, plan.id, policy_reference=f"{prefix}-REF-{i}", site_name=f"{prefix} Site {i}", minimum_dwellings=100 + i)
        if i % 3 == 0:
            site = _make_site(session, f"{prefix} Site Address {i}")
            _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
            _make_app_with_capacity(session, site.id, f"{prefix}-APP/{i}", 20)


def _query_count_for_discovery_and_filters(session) -> int:
    engine = session.get_bind()
    statements = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        if statement.strip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", _count)
    try:
        result = build_allocation_discovery(session)
        # Apply every new filter concept - still zero additional queries,
        # since apply_filters/has_trusted_linked_application/
        # planning_activity_status/capacity_band_range are all pure
        # functions over already-loaded card dicts.
        cmin, cmax = capacity_band_range("100–199 homes")
        apply_filters(result["cards"], {
            "application_linkage": "linked", "planning_activity": PLANNING_ACTIVITY_IDENTIFIED,
            "capacity_min": cmin, "capacity_max": cmax,
        })
    finally:
        event.remove(engine, "before_cursor_execute", _count)
    return len(statements)


def test_no_n_plus_1_with_filter_refinement_fields(session):
    """The real invariant (build_allocation_discovery's own fixed query
    budget, including its Stage 3A development-coverage sub-queries, is
    already covered by tests/test_allocation_discovery.py's own bounded-
    query test): the count does NOT grow with allocation count - proven
    here by comparing a small and a larger seeded set, never a specific
    magic number that happens to depend on how many of those allocations
    carry a relationship/Application/Document."""
    plan_a = _make_local_plan(session, council_code="testcouncil")
    _seed_allocations_with_relationships(session, plan_a, 5, prefix="A")
    small_count = _query_count_for_discovery_and_filters(session)

    plan_b = _make_local_plan(session, council_code="othercouncil")
    _seed_allocations_with_relationships(session, plan_b, 40, prefix="B")
    large_count = _query_count_for_discovery_and_filters(session)

    assert large_count == small_count


# ---------------------------------------------------------------------------
# Item 30 - no OpenAI / external API dependency
# ---------------------------------------------------------------------------


def test_no_openai_or_external_api_dependency():
    source = inspect.getsource(discovery_module)
    lowered = source.lower()
    assert "import openai" not in lowered
    assert "from openai" not in lowered
    assert "requests.get(" not in source
    assert "requests.post(" not in source
