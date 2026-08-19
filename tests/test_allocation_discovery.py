"""Tests for Sprint 4.5 ("Allocation Discovery") - app.reporting.
allocation_discovery's pure view-model logic (capacity formatting, search,
filters, sorting, categories, why-it-matters/investigate-next) plus the
batched query builders it depends on (app.visuals.site_view's
build_allocation_visual_summaries/build_plan_wide_policies_map). Follows the
same "unit-test the pure helpers a page delegates to, not the page script
itself" convention already established by tests/test_allocation_selector.py
and tests/test_site_profile.py.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import event

from app.db.models import Application, LocalPlan, LocalPlanCouncil, LocalPlanSite, Site, VisualEvidence
from app.reporting.allocation_discovery import (
    CATEGORY_DEFINITIONS,
    MAJOR_HOUSING_CAPACITY_THRESHOLD,
    apply_filters,
    build_allocation_card,
    build_allocation_discovery,
    build_summary_metrics,
    compute_categories,
    format_capacity,
    is_major_housing_allocation,
    linked_application_text,
    matched_status_text,
    search_allocations,
    sort_cards,
)
from app.visuals.site_view import build_allocation_visual_summaries, build_plan_wide_policies_map

_BANNED_PHRASES = (
    "likely to receive", "strong chance", "likely to be approved", "guaranteed", "strong investment",
    "recommend acquisition", "recommend buying", "will be approved", "certain to",
)


def _make_local_plan(session, council_code="testcouncil", status="adopted", plan_name="Test Local Plan", **kwargs) -> LocalPlan:
    plan = LocalPlan(council_code=council_code, plan_name=plan_name, status=status, raw_status=status, **kwargs)
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


def _make_site(session, **kwargs) -> Site:
    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street", **kwargs)
    session.add(site)
    session.commit()
    return site


def _make_app(session, site_id, reference="APP/1", **kwargs) -> Application:
    app = Application(council_code="testcouncil", reference=reference, site_id=site_id, **kwargs)
    session.add(app)
    session.commit()
    return app


def _make_visual(session, *, allocation_id=None, local_plan_id=None, review_status="confirmed",
                  image_type="allocation_map", is_primary=False, status="current") -> VisualEvidence:
    ve = VisualEvidence(
        allocation_id=allocation_id, local_plan_id=local_plan_id, source_page=1, image_type=image_type,
        review_status=review_status, status=status, is_primary=is_primary, image_path="/data/fake/path.png",
    )
    session.add(ve)
    session.commit()
    return ve


def _card(**overrides) -> dict:
    """A minimal, hand-built card dict for testing the pure functions that
    operate on already-assembled cards (search/filter/sort/categories) -
    every field build_allocation_card would set, given a plausible default,
    so a test only has to override what it cares about."""
    base = {
        "id": 1, "site_name": "Test Site", "policy_reference": "REF-1", "council_code": "testcouncil",
        "council_name": "Test Council", "local_plan_id": 1, "plan_name": "Test Local Plan",
        "plan_status": "adopted", "plan_status_label": "Adopted", "plan_status_bucket": "adopted",
        "plan_status_chip_kind": "plan_adopted", "is_multi_authority": False, "cross_boundary_councils": [],
        "intended_use": "residential", "intended_use_label": "Residential",
        "capacity": {"kind": "minimum", "display": "Approximately 150 homes", "value": 150},
        "kpi_capacity_contribution": {"value": 150, "is_estimate": False},
        "major_housing": True, "category": None, "allocation_status": None, "raw_allocation_status": None,
        "progression_signal": None, "review_status": "auto_applied", "review_status_label": "Auto-applied match",
        "review_status_badge_kind": "pending", "duplicate_classification": None, "matched": False,
        "matched_site_id": None, "matched_site_address": None, "match_confidence": None,
        "linked_application_count": 0, "matched_summary": "Not matched to a Site · No linked Application",
        "matched_summary_help": "help", "lapse_status": None, "build_status": None, "build_status_label": None,
        "delivery_note": None, "visual_status": "none", "visual_primary": None, "visual_others": [],
        "visual_fallback": None, "council_five_year_supply": None, "source_document_url": None,
        "source_page": None, "plan_page_url": None, "last_checked": None,
        "updated_at": dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc), "latitude": None, "longitude": None,
    }
    base.update(overrides)
    base["why_it_matters_reasons"] = ["Test reason."]
    base["why_it_matters"] = "Test reason."
    base["investigate_next"] = "Test next step."
    return base


# --- Capacity formatting (Part 14) ------------------------------------------


def test_format_capacity_minimum_only():
    allocation = LocalPlanSite(council_code="c", site_name="A", plan_name="P", plan_status="adopted", minimum_dwellings=300)
    result = format_capacity(allocation)
    assert result == {"kind": "minimum", "display": "Approximately 300 homes", "value": 300}


def test_format_capacity_range_when_min_and_max_differ():
    allocation = LocalPlanSite(
        council_code="c", site_name="A", plan_name="P", plan_status="adopted", minimum_dwellings=100, maximum_capacity=200,
    )
    result = format_capacity(allocation)
    assert result == {"kind": "range", "display": "100–200 homes", "value": 200}


def test_format_capacity_indicative_only():
    allocation = LocalPlanSite(council_code="c", site_name="A", plan_name="P", plan_status="adopted", indicative_capacity=50)
    result = format_capacity(allocation)
    assert result["kind"] == "indicative"
    assert result["display"] == "Approximately 50 homes"
    assert result["value"] == 50


def test_format_capacity_maximum_only():
    allocation = LocalPlanSite(council_code="c", site_name="A", plan_name="P", plan_status="adopted", maximum_capacity=400)
    result = format_capacity(allocation)
    assert result["kind"] == "maximum"
    assert result["value"] == 400


def test_format_capacity_unknown_when_nothing_stated():
    allocation = LocalPlanSite(council_code="c", site_name="A", plan_name="P", plan_status="adopted")
    result = format_capacity(allocation)
    assert result == {"kind": "unknown", "display": "Capacity not identified", "value": None}


def test_format_capacity_never_fabricates_a_range_when_min_equals_max():
    allocation = LocalPlanSite(
        council_code="c", site_name="A", plan_name="P", plan_status="adopted", minimum_dwellings=100, maximum_capacity=100,
    )
    result = format_capacity(allocation)
    assert result["kind"] == "minimum"


# --- Major Housing Allocation (Part 6) ---------------------------------------


def test_major_housing_allocation_true_at_threshold():
    assert is_major_housing_allocation("residential", MAJOR_HOUSING_CAPACITY_THRESHOLD) is True


def test_major_housing_allocation_false_below_threshold():
    assert is_major_housing_allocation("residential", MAJOR_HOUSING_CAPACITY_THRESHOLD - 1) is False


def test_major_housing_allocation_false_for_employment_use():
    assert is_major_housing_allocation("employment", 5000) is False


def test_major_housing_allocation_true_for_mixed_use():
    assert is_major_housing_allocation("mixed use", MAJOR_HOUSING_CAPACITY_THRESHOLD) is True


def test_major_housing_allocation_false_when_capacity_unknown():
    assert is_major_housing_allocation("residential", None) is False


# --- Matched / unmatched wording (Part 13) -----------------------------------


def test_matched_status_text_never_implies_no_development():
    text = matched_status_text(False)
    assert "no development" not in text.lower()
    assert "undeveloped" not in text.lower()
    assert text == "Not matched to a Site"


def test_linked_application_text_never_claims_no_application_exists_in_reality():
    text = linked_application_text(0)
    assert "exists" not in text.lower()
    assert text == "No linked Application"


def test_linked_application_text_pluralises_correctly():
    assert linked_application_text(1) == "1 linked Application"
    assert linked_application_text(3) == "3 linked Applications"


# --- Search (Part 4) ---------------------------------------------------------


def test_search_matches_site_name_case_insensitively():
    cards = [_card(id=1, site_name="Northern Gateway"), _card(id=2, site_name="Southern Fields")]
    result = search_allocations(cards, "northern")
    assert [c["id"] for c in result] == [1]


def test_search_matches_policy_reference():
    cards = [_card(id=1, policy_reference="JPA1.1"), _card(id=2, policy_reference="HOM 2.3")]
    assert [c["id"] for c in search_allocations(cards, "jpa1.1")] == [1]


def test_search_matches_matched_site_address():
    cards = [_card(id=1, matched_site_address="Land off Chester Road"), _card(id=2, matched_site_address=None)]
    assert [c["id"] for c in search_allocations(cards, "chester")] == [1]


def test_search_empty_query_returns_everything():
    cards = [_card(id=1), _card(id=2)]
    assert search_allocations(cards, "") == cards


def test_search_is_deterministic_no_fuzzy_ranking():
    cards = [_card(id=1, site_name="Alpha"), _card(id=2, site_name="Beta")]
    assert search_allocations(cards, "gamma") == []


# --- Filters (Part 5) --------------------------------------------------------


def test_filter_by_matched():
    cards = [_card(id=1, matched=True), _card(id=2, matched=False)]
    assert [c["id"] for c in apply_filters(cards, {"matched": "matched"})] == [1]
    assert [c["id"] for c in apply_filters(cards, {"matched": "unmatched"})] == [2]


def test_filter_by_application_linkage():
    cards = [_card(id=1, linked_application_count=2), _card(id=2, linked_application_count=0)]
    assert [c["id"] for c in apply_filters(cards, {"application_linkage": "linked"})] == [1]
    assert [c["id"] for c in apply_filters(cards, {"application_linkage": "not_linked"})] == [2]


def test_filter_by_visual_evidence_confirmed_suggested_and_none():
    cards = [
        _card(id=1, visual_status="confirmed"),
        _card(id=2, visual_status="needs_review"),
        _card(id=3, visual_status="none", visual_fallback=None),
        _card(id=4, visual_status="none", visual_fallback={"id": 9}),
    ]
    assert [c["id"] for c in apply_filters(cards, {"visual_evidence": "confirmed"})] == [1]
    assert [c["id"] for c in apply_filters(cards, {"visual_evidence": "suggested"})] == [2, 4]
    assert [c["id"] for c in apply_filters(cards, {"visual_evidence": "none"})] == [3]


def test_filter_by_plan_status_bucket():
    cards = [_card(id=1, plan_status_bucket="adopted"), _card(id=2, plan_status_bucket="emerging")]
    assert [c["id"] for c in apply_filters(cards, {"plan_status_buckets": ["adopted"]})] == [1]


def test_filter_by_intended_use():
    cards = [_card(id=1, intended_use="residential"), _card(id=2, intended_use="employment")]
    assert [c["id"] for c in apply_filters(cards, {"intended_uses": ["employment"]})] == [2]


def test_filter_by_capacity_range():
    cards = [_card(id=1, capacity={"kind": "minimum", "display": "50", "value": 50}),
             _card(id=2, capacity={"kind": "minimum", "display": "500", "value": 500})]
    result = apply_filters(cards, {"capacity_min": 100, "capacity_max": 1000})
    assert [c["id"] for c in result] == [2]


def test_filter_by_council():
    cards = [_card(id=1, council_code="bury"), _card(id=2, council_code="stockport")]
    assert [c["id"] for c in apply_filters(cards, {"councils": ["bury"]})] == [1]


def test_filter_by_review_state():
    cards = [_card(id=1, review_status="needs_confirmation"), _card(id=2, review_status="auto_applied")]
    result = apply_filters(cards, {"review_states": ["needs_confirmation"]})
    assert [c["id"] for c in result] == [1]


def test_filter_joint_plan_only():
    cards = [_card(id=1, is_multi_authority=True), _card(id=2, is_multi_authority=False)]
    assert [c["id"] for c in apply_filters(cards, {"joint_plan_only": True})] == [1]


def test_filter_cross_boundary_only_requires_other_councils_present():
    cards = [
        _card(id=1, is_multi_authority=True, cross_boundary_councils=["stockport"]),
        _card(id=2, is_multi_authority=True, cross_boundary_councils=[]),
    ]
    assert [c["id"] for c in apply_filters(cards, {"cross_boundary_only": True})] == [1]


def test_filters_with_no_constraints_return_everything():
    cards = [_card(id=1), _card(id=2)]
    assert apply_filters(cards, {}) == cards


def test_filters_compose_with_and_semantics():
    cards = [
        _card(id=1, council_code="bury", matched=True),
        _card(id=2, council_code="bury", matched=False),
        _card(id=3, council_code="stockport", matched=True),
    ]
    result = apply_filters(cards, {"councils": ["bury"], "matched": "matched"})
    assert [c["id"] for c in result] == [1]


# --- Sorting (Part 16) -------------------------------------------------------


def test_sort_capacity_desc():
    cards = [
        _card(id=1, capacity={"kind": "minimum", "display": "50", "value": 50}),
        _card(id=2, capacity={"kind": "minimum", "display": "500", "value": 500}),
        _card(id=3, capacity={"kind": "unknown", "display": "?", "value": None}),
    ]
    result = sort_cards(cards, "capacity_desc")
    assert [c["id"] for c in result] == [2, 1, 3]


def test_sort_council():
    cards = [_card(id=1, council_name="Stockport"), _card(id=2, council_name="Bury")]
    assert [c["id"] for c in sort_cards(cards, "council")] == [2, 1]


def test_sort_unmatched_first():
    cards = [_card(id=1, matched=True), _card(id=2, matched=False)]
    assert [c["id"] for c in sort_cards(cards, "unmatched_first")] == [2, 1]


def test_sort_plan_stage_uses_real_progression_order():
    cards = [_card(id=1, plan_status="adopted"), _card(id=2, plan_status="preparation")]
    result = sort_cards(cards, "plan_stage")
    assert [c["id"] for c in result] == [2, 1]


def test_sort_visual_evidence_confirmed_first():
    cards = [
        _card(id=1, visual_status="none", visual_fallback=None),
        _card(id=2, visual_status="confirmed"),
        _card(id=3, visual_status="needs_review"),
    ]
    result = sort_cards(cards, "visual_evidence")
    assert [c["id"] for c in result] == [2, 3, 1]


def test_sort_default_puts_adopted_before_emerging_before_other_when_updated_equal():
    same_time = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    cards = [
        _card(id=1, plan_status_bucket="other", updated_at=same_time),
        _card(id=2, plan_status_bucket="adopted", updated_at=same_time),
        _card(id=3, plan_status_bucket="emerging", updated_at=same_time),
    ]
    result = sort_cards(cards, "default")
    assert [c["id"] for c in result] == [2, 3, 1]


def test_sort_default_prioritises_recent_update_first():
    cards = [
        _card(id=1, plan_status_bucket="adopted", updated_at=dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)),
        _card(id=2, plan_status_bucket="other", updated_at=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)),
    ]
    result = sort_cards(cards, "default")
    assert [c["id"] for c in result] == [2, 1]


def test_sort_is_deterministic_id_is_final_tiebreak():
    cards = [_card(id=2, council_name="Same"), _card(id=1, council_name="Same")]
    result = sort_cards(cards, "council")
    assert [c["id"] for c in result] == [1, 2]
    # calling again produces the identical order - no hidden randomness.
    assert [c["id"] for c in sort_cards(cards, "council")] == [1, 2]


# --- Discovery categories (Part 6) -------------------------------------------


def test_compute_categories_hides_categories_with_no_matches():
    cards = [_card(id=1, plan_status_bucket="adopted", major_housing=False, linked_application_count=1,
                    visual_status="none", visual_fallback=None, review_status="confirmed", matched=True,
                    lapse_status="underway")]
    categories = compute_categories(cards)
    keys = {c["key"] for c in categories}
    assert "all" in keys
    assert "adopted" in keys
    # nothing here is emerging, major, unreviewed, mapped, unmatched-app-free, or not-commenced
    assert "emerging" not in keys
    assert "major_housing" not in keys
    assert "needs_review" not in keys
    assert "with_maps" not in keys
    assert "no_linked_application" not in keys
    assert "not_commenced" not in keys


def test_compute_categories_needs_review_includes_unconfirmed_visual_evidence():
    cards = [_card(id=1, review_status="auto_applied", visual_status="needs_review")]
    categories = {c["key"]: c for c in compute_categories(cards)}
    assert "needs_review" in categories
    assert categories["needs_review"]["count"] == 1


def test_compute_categories_not_commenced_requires_matched_and_granted_not_started():
    matched_not_started = _card(id=1, matched=True, lapse_status="safe")
    unmatched = _card(id=2, matched=False, lapse_status=None)
    categories = {c["key"]: c for c in compute_categories([matched_not_started, unmatched])}
    assert categories["not_commenced"]["count"] == 1
    assert categories["not_commenced"]["cards"][0]["id"] == 1


def test_category_definitions_all_referenced_by_key():
    keys = {key for key, _, _ in CATEGORY_DEFINITIONS}
    assert keys == {"all", "adopted", "emerging", "with_maps", "no_linked_application", "not_commenced", "major_housing", "needs_review"}


# --- Why it matters / Investigate next (Parts 9 & 10) ------------------------


def test_why_it_matters_and_investigate_next_never_use_banned_language():
    scenarios = [
        _card(id=1, plan_status_bucket="adopted", major_housing=True, capacity={"kind": "minimum", "display": "500 homes", "value": 500}),
        _card(id=2, plan_status_bucket="emerging", linked_application_count=0),
        _card(id=3, matched=True, lapse_status="approaching"),
        _card(id=4, visual_status="confirmed"),
        _card(id=5, visual_status="needs_review"),
        _card(id=6, council_five_year_supply=1.5),
    ]
    for card in scenarios:
        from app.reporting.allocation_discovery import _investigate_next, _why_it_matters_reasons

        reasons = _why_it_matters_reasons(card)
        next_step = _investigate_next(card)
        combined = " ".join(reasons + [next_step]).lower()
        for phrase in _BANNED_PHRASES:
            assert phrase not in combined, f"banned phrase '{phrase}' found for card {card['id']}"


def test_why_it_matters_varies_by_signal_not_identical_across_cards():
    from app.reporting.allocation_discovery import _why_it_matters_reasons

    adopted_major = _card(id=1, plan_status_bucket="adopted", major_housing=True,
                           capacity={"kind": "minimum", "display": "500 homes", "value": 500})
    emerging_no_app = _card(id=2, plan_status_bucket="emerging", linked_application_count=0)
    assert _why_it_matters_reasons(adopted_major)[0] != _why_it_matters_reasons(emerging_no_app)[0]


def test_investigate_next_grounded_in_visual_status():
    from app.reporting.allocation_discovery import _investigate_next

    assert "confirmed allocation map" in _investigate_next(_card(id=1, visual_status="confirmed")).lower()
    assert "suggested imagery" in _investigate_next(_card(id=2, visual_status="needs_review")).lower()


def test_why_it_matters_honest_fallback_when_no_signals():
    from app.reporting.allocation_discovery import _why_it_matters_reasons

    plain = _card(
        id=1, plan_status_bucket="other", major_housing=False, linked_application_count=1, matched=True,
        lapse_status="underway", council_five_year_supply=None, visual_status="none", visual_fallback=None,
        is_multi_authority=False,
    )
    reasons = _why_it_matters_reasons(plain)
    assert reasons == ["No additional planning signals identified from evidence currently held by the platform."]


# --- Summary metrics + duplicate/contextual handling (Part 14) --------------


def test_summary_metrics_counts_only_real_data():
    cards = [
        _card(id=1, plan_status_bucket="adopted", matched=True, linked_application_count=1, visual_status="confirmed"),
        _card(id=2, plan_status_bucket="emerging", matched=False, linked_application_count=0, visual_status="none", visual_fallback=None),
    ]
    summary = build_summary_metrics(cards)
    assert summary["total_allocations"] == 2
    assert summary["adopted_allocations"] == 1
    assert summary["emerging_allocations"] == 1
    assert summary["matched_to_sites"] == 1
    assert summary["no_linked_application"] == 1
    assert summary["with_visual_evidence"] == 1


def test_summary_metrics_excludes_approved_duplicate_classification_from_totals():
    cards = [
        _card(id=1, duplicate_classification=None),
        _card(id=2, duplicate_classification="duplicate_of_other_plan"),
        _card(id=3, duplicate_classification="contextual_reference"),
    ]
    summary = build_summary_metrics(cards)
    assert summary["total_allocations"] == 1


def test_summary_metrics_never_deduplicates_an_unapproved_classification():
    cards = [_card(id=1, duplicate_classification="uncertain_needs_review"), _card(id=2, duplicate_classification=None)]
    summary = build_summary_metrics(cards)
    assert summary["total_allocations"] == 2


# --- Batched visual evidence selection (Part 11) -----------------------------


def test_visual_summary_prefers_confirmed_primary_over_suggested(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    _make_visual(session, allocation_id=allocation.id, review_status="needs_review", is_primary=False)
    _make_visual(session, allocation_id=allocation.id, review_status="confirmed", is_primary=True)

    result = build_allocation_visual_summaries(session, [allocation.id])
    assert result[allocation.id]["status"] == "confirmed"
    assert result[allocation.id]["primary"].review_status == "confirmed"


def test_visual_summary_status_none_when_no_evidence(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    result = build_allocation_visual_summaries(session, [allocation.id])
    assert result[allocation.id] == {"status": "none", "primary": None, "others": []}


def test_visual_summary_ignores_rejected_evidence(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    _make_visual(session, allocation_id=allocation.id, review_status="rejected")
    result = build_allocation_visual_summaries(session, [allocation.id])
    assert result[allocation.id]["status"] == "none"


def test_visual_summary_query_count_bounded_regardless_of_allocation_count(session):
    plan = _make_local_plan(session)
    allocations = [_make_allocation(session, plan.id, policy_reference=f"REF-{i}") for i in range(10)]
    for a in allocations[:5]:
        _make_visual(session, allocation_id=a.id, review_status="confirmed", is_primary=True)

    engine = session.get_bind()
    statements = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        if statement.strip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", _count)
    try:
        build_allocation_visual_summaries(session, [a.id for a in allocations])
    finally:
        event.remove(engine, "before_cursor_execute", _count)
    assert len(statements) == 1


def test_plan_wide_policies_map_fallback_scoped_to_policies_map_extract_only(session):
    plan = _make_local_plan(session)
    _make_visual(session, local_plan_id=plan.id, image_type="policies_map_extract", review_status="needs_review")
    _make_visual(session, local_plan_id=plan.id, image_type="unknown", review_status="needs_review")

    result = build_plan_wide_policies_map(session, [plan.id])
    assert plan.id in result
    assert result[plan.id].image_type == "policies_map_extract"


def test_plan_wide_policies_map_absent_when_no_policies_map_extract_exists(session):
    plan = _make_local_plan(session)
    _make_visual(session, local_plan_id=plan.id, image_type="unknown", review_status="needs_review")
    result = build_plan_wide_policies_map(session, [plan.id])
    assert plan.id not in result


def test_stockport_style_fallback_is_never_presented_as_allocation_specific(session):
    """The card built for an allocation with no allocation-specific image
    but a plan-wide Policies Map available must carry the fallback
    separately from "primary" (visual_primary stays None), so the caller
    can label it distinctly rather than claiming a confirmed
    allocation-specific boundary image exists (Part 11)."""
    plan = _make_local_plan(session, council_code="stockport")
    allocation = _make_allocation(session, plan.id, council_code="stockport")
    policies_map = _make_visual(session, local_plan_id=plan.id, image_type="policies_map_extract", review_status="needs_review")

    visual_summaries = build_allocation_visual_summaries(session, [allocation.id])
    fallback = build_plan_wide_policies_map(session, [plan.id]).get(plan.id)

    card = build_allocation_card(
        allocation, plan=plan, council_name="Stockport", council_codes_on_plan=["stockport"],
        matched_site=None, linked_applications=[], visual_summary=visual_summaries[allocation.id],
        visual_fallback=fallback, council_five_year_supply=None,
    )
    assert card["visual_primary"] is None
    assert card["visual_fallback"] is not None
    assert card["visual_fallback"]["id"] == policies_map.id


# --- No local filesystem paths in display text (Part 7 / Part 21) -----------


def test_card_display_fields_never_contain_a_raw_filesystem_path(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    _make_visual(session, allocation_id=allocation.id, review_status="confirmed", is_primary=True)
    visual_summaries = build_allocation_visual_summaries(session, [allocation.id])

    card = build_allocation_card(
        allocation, plan=plan, council_name="Test Council", council_codes_on_plan=["testcouncil"],
        matched_site=None, linked_applications=[], visual_summary=visual_summaries[allocation.id],
        visual_fallback=None, council_five_year_supply=None,
    )
    text_fields = [card["why_it_matters"], card["investigate_next"], card["matched_summary"], card["site_name"]]
    for field in text_fields:
        assert "/data/fake/path.png" not in (field or "")


# --- build_allocation_discovery: batched, bounded, joint-plan aware ---------


def test_build_allocation_discovery_makes_no_database_writes(session):
    plan = _make_local_plan(session)
    _make_allocation(session, plan.id)
    assert not session.new
    assert not session.dirty
    build_allocation_discovery(session)
    assert not session.new
    assert not session.dirty


def test_build_allocation_discovery_query_count_bounded_as_allocation_count_grows(session):
    plan = _make_local_plan(session)
    for i in range(20):
        _make_allocation(session, plan.id, policy_reference=f"REF-{i}", site_name=f"Site {i}")

    engine = session.get_bind()
    statements = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        if statement.strip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", _count)
    try:
        build_allocation_discovery(session)
    finally:
        event.remove(engine, "before_cursor_execute", _count)
    # A small, fixed budget regardless of allocation count - never one
    # query per allocation (see this module's own docstring for the exact
    # accounting: LocalPlanSite + 2 selectinload batches, matched Sites,
    # 2 batched Application queries, visual evidence, plan-wide fallback).
    assert len(statements) <= 8


def test_build_allocation_discovery_joint_plan_counts_are_council_specific(session):
    joint_plan = _make_local_plan(session, council_code="bury", plan_name="Places for Everyone")
    session.add(LocalPlanCouncil(local_plan_id=joint_plan.id, council_code="bury", role="participating_authority"))
    session.add(LocalPlanCouncil(local_plan_id=joint_plan.id, council_code="stockport", role="participating_authority"))
    session.commit()
    _make_allocation(session, joint_plan.id, council_code="bury", policy_reference="JPA1", site_name="Bury allocation")
    _make_allocation(session, joint_plan.id, council_code="stockport", policy_reference="JPA2", site_name="Stockport allocation")

    view = build_allocation_discovery(session, council_codes=["bury"])
    assert len(view["cards"]) == 1
    assert view["cards"][0]["council_code"] == "bury"
    assert view["cards"][0]["is_multi_authority"] is True


def test_build_allocation_discovery_matched_allocation_carries_site_and_application_facts(session):
    plan = _make_local_plan(session)
    site = _make_site(session)
    # load_applications_for_sites reuses the same "visible qualifying
    # scheme" rule as the rest of the platform (app.ui.common.
    # _filter_visible_applications) - a proposal must actually qualify
    # (state a unit count at/above the council's threshold) to be counted,
    # the same as everywhere else this helper is used.
    _make_app(
        session, site.id, decision="Granted", status="Decided", decision_issued_date="2020-01-01",
        proposal="Erection of 25 dwellings",
    )
    allocation = _make_allocation(session, plan.id, minimum_dwellings=10)
    allocation.matched_site_id = site.id
    session.commit()

    view = build_allocation_discovery(session)
    card = next(c for c in view["cards"] if c["id"] == allocation.id)
    assert card["matched"] is True
    assert card["linked_application_count"] == 1
    assert card["matched_site_address"] == "1 Test Street"


def test_build_allocation_discovery_unmatched_allocation_has_zero_linked_applications(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    view = build_allocation_discovery(session)
    card = next(c for c in view["cards"] if c["id"] == allocation.id)
    assert card["matched"] is False
    assert card["linked_application_count"] == 0


# --- Page-level regression: capacity slider must not filter anything at its
# default (full-range) position (a real bug caught during live verification -
# the slider's own value=(cap_min, cap_max) default made apply_filters'
# capacity_min/max always "on", silently excluding every allocation with an
# unstated capacity from every single page load). ---------------------------


def test_capacity_filter_inactive_at_default_full_range_position():
    from app.reporting.allocation_discovery import apply_filters

    cards = [
        _card(id=1, capacity={"kind": "minimum", "display": "50", "value": 50}),
        _card(id=2, capacity={"kind": "unknown", "display": "Capacity not identified", "value": None}),
    ]
    # Simulating the slider left untouched at its full observed range
    # (50-50 here, a degenerate single-value span) - both cards, including
    # the one with no stated capacity, must still be returned.
    result = apply_filters(cards, {"capacity_min": None, "capacity_max": None})
    assert len(result) == 2


def test_local_plan_sites_page_only_applies_capacity_filter_once_narrowed():
    """Local Plan Sites Filter Refinement - capacity bands replaced the old
    linear slider, but the same invariant must hold: the default ("Any")
    selection applies no capacity constraint at all (unknown-capacity
    allocations included), only a deliberately narrowed band excludes
    them. The page wires capacity_min/capacity_max straight from
    capacity_band_range - verified here at the function level (the
    "Any" band's own (None, None)) plus a source-level check that the
    page actually calls it rather than hand-rolling a parallel mechanism."""
    from pathlib import Path

    from app.reporting.allocation_discovery import capacity_band_range

    assert capacity_band_range("Any") == (None, None)

    source = Path("app/ui/pages/3_Local_Plan_Sites.py").read_text(encoding="utf-8")
    assert "capacity_band_range(capacity_band_label)" in source


# --- Stage 3A wiring: build_allocation_discovery must surface development
# coverage/phasing/opportunity via AllocationSiteRelationship, additive to
# the existing matched_site_id-derived card fields. ---------------------------


def test_card_has_no_identified_activity_when_no_relationship(session):
    """A card whose allocation has zero AllocationSiteRelationship rows
    still gets real Stage 3A intelligence via the full pipeline (never
    silently None here - that default only applies to a caller of
    build_allocation_card directly, without development_coverage at
    all): confidently NO_IDENTIFIED_ACTIVITY, never treated as unknown."""
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, minimum_dwellings=100)
    session.commit()

    result = build_allocation_discovery(session)
    card = next(c for c in result["cards"] if c["id"] == allocation.id)

    assert card["development_coverage"] is not None
    assert card["development_coverage"].development_coverage_classification == "NO_IDENTIFIED_ACTIVITY"
    assert card["development_coverage"].number_of_related_sites == 0


def test_build_allocation_card_directly_defaults_development_coverage_to_none():
    """The narrower default: a caller building a card WITHOUT going
    through build_allocation_discovery at all (e.g. a future standalone
    caller) gets None, not a fabricated coverage result."""
    allocation = LocalPlanSite(
        council_code="testcouncil", policy_reference="REF-1", site_name="Land off Test Road",
        plan_name="Test Local Plan", plan_status="adopted", minimum_dwellings=100,
    )
    card = build_allocation_card(
        allocation, plan=None, council_name="Test Council", council_codes_on_plan=["testcouncil"],
        matched_site=None, linked_applications=[], visual_summary={"status": "none", "primary": None, "others": []},
        visual_fallback=None, council_five_year_supply=None,
    )
    assert card["development_coverage"] is None
    assert card["phasing"] is None
    assert card["opportunity"] is None


def test_card_surfaces_development_coverage_via_allocation_site_relationship(session):
    from app.db.models import AllocationSiteRelationship, SchemeIntelligence

    plan = _make_local_plan(session, status="adopted")
    allocation = _make_allocation(session, plan.id, policy_reference="JPA 32", site_name="North of Mosley Common", minimum_dwellings=1100)
    site = Site(council_code="testcouncil", canonical_address="mosley common south of the guided busway worsley",
                display_address="Mosley Common")
    session.add(site)
    session.commit()
    session.add(AllocationSiteRelationship(allocation_id=allocation.id, site_id=site.id, evidence_basis="document_confirmed_site"))
    app = _make_app(session, site.id, reference="A/25/099409/RMMAJ")
    session.add(SchemeIntelligence(application_id=app.id, total_units_final=244, core_intelligence_complete=True))
    session.commit()

    result = build_allocation_discovery(session)
    card = next(c for c in result["cards"] if c["id"] == allocation.id)

    assert card["development_coverage"] is not None
    assert card["development_coverage"].allocation_capacity == 1100
    assert card["development_coverage"].identified_application_capacity == 244
    assert card["development_coverage"].indicative_residual_capacity == 856
    assert card["opportunity"]["signal"] == "INVESTIGATE"
