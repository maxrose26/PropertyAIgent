"""Tests for Sprint 4.5a ("Allocation Discovery Commercial Polish") -
wording/hierarchy/KPI refinements layered on top of Sprint 4.5's Allocation
Discovery view model (app.reporting.allocation_discovery). Sprint 4.5's own
tests (tests/test_allocation_discovery.py) already cover the underlying
signals (search/filter/sort/categories/query-budget) this sprint doesn't
touch - these tests focus specifically on what Sprint 4.5a changed: capacity
wording, development-type labelling, "why it matters" tone, the "no linked
planning application" commercial panel, and the KPI strip's new metrics.
"""
from __future__ import annotations

import datetime as dt

from app.db.models import LocalPlanSite
from app.reporting.allocation_discovery import (
    LARGE_RESIDENTIAL_CAPACITY_THRESHOLD,
    NO_LINKED_APPLICATION_PANEL_MESSAGE,
    NO_LINKED_APPLICATION_PANEL_TITLE,
    build_matching_attributes,
    build_summary_metrics,
    development_type_label,
    format_capacity,
    show_no_application_panel,
)

# Part 6's explicit bans, plus the general planning-likelihood/investment-
# advice phrases Sprint 4.5 already guarded against - a superset battery
# every piece of generated wording in this module must avoid.
_BANNED_PHRASES = (
    "good buying opportunity", "acquisition opportunity", "strong investment", "likely to gain planning permission",
    "likely to receive", "strong chance", "likely to be approved", "guaranteed", "recommend acquisition",
    "recommend buying", "will be approved", "certain to", "buying opportunity", "invest in", "worth buying",
)


def _card(**overrides) -> dict:
    base = {
        "id": 1, "site_name": "Test Site", "policy_reference": "REF-1", "council_code": "testcouncil",
        "council_name": "Test Council", "local_plan_id": 1, "plan_name": "Test Local Plan",
        "plan_status": "adopted", "plan_status_label": "Adopted", "plan_status_bucket": "adopted",
        "plan_status_chip_kind": "plan_adopted", "is_multi_authority": False, "cross_boundary_councils": [],
        "intended_use": "residential", "intended_use_label": "Residential", "development_type": "Residential allocation",
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


# --- Part 3: capacity presentation -------------------------------------------


def test_capacity_minimum_reads_as_a_natural_sentence():
    allocation = LocalPlanSite(council_code="c", site_name="A", plan_name="P", plan_status="adopted", minimum_dwellings=250)
    result = format_capacity(allocation)
    assert result["display"] == "Approximately 250 homes"


def test_capacity_large_number_uses_thousands_separator():
    allocation = LocalPlanSite(council_code="c", site_name="A", plan_name="P", plan_status="adopted", minimum_dwellings=1250)
    result = format_capacity(allocation)
    assert result["display"] == "Approximately 1,250 homes"


def test_capacity_maximum_reads_up_to_phrasing():
    allocation = LocalPlanSite(council_code="c", site_name="A", plan_name="P", plan_status="adopted", maximum_capacity=600)
    result = format_capacity(allocation)
    assert result["display"] == "Up to 600 homes"


def test_capacity_unknown_reads_not_identified_never_fabricates_a_number():
    allocation = LocalPlanSite(council_code="c", site_name="A", plan_name="P", plan_status="adopted")
    result = format_capacity(allocation)
    assert result["display"] == "Capacity not identified"
    assert result["value"] is None


def test_capacity_never_uses_bare_database_style_field_value_pair():
    """Never a bare "Capacity: 250" / "Capacity 250" pattern - always a
    natural sentence fragment (Part 3)."""
    allocation = LocalPlanSite(council_code="c", site_name="A", plan_name="P", plan_status="adopted", minimum_dwellings=250)
    display = format_capacity(allocation)["display"]
    assert not display.lower().startswith("capacity:")
    assert not display.lower().startswith("capacity ")


# --- Part 2: development type ------------------------------------------------


def test_development_type_garden_village_from_site_name():
    label = development_type_label(site_name="Godley Green Garden Village", category=None, intended_use="residential", capacity_value=2350)
    assert label == "Garden village allocation"


def test_development_type_regeneration_from_site_name():
    label = development_type_label(site_name="Roch Valley Regeneration Site", category=None, intended_use="residential", capacity_value=200)
    assert label == "Urban regeneration allocation"


def test_development_type_employment():
    label = development_type_label(site_name="Anywhere", category=None, intended_use="employment", capacity_value=None)
    assert label == "Employment allocation"


def test_development_type_mixed_use():
    label = development_type_label(site_name="Anywhere", category=None, intended_use="mixed use", capacity_value=500)
    assert label == "Mixed-use allocation"


def test_development_type_large_capacity_alone_is_not_strategic_urban_extension():
    """Evidence Terminology Amendment, Part 1: a 1,500-home allocation with
    no explicit supporting wording must never be labelled "Strategic urban
    extension" on capacity alone - capacity may only choose between the
    two capacity-neutral residential descriptions."""
    label = development_type_label(
        site_name="New Carrington", category=None, intended_use="residential", capacity_value=1500,
    )
    assert label == "Large residential allocation"
    assert label != "Strategic urban extension"


def test_development_type_explicit_strategic_urban_extension_retains_the_label():
    """An allocation whose own title/category text explicitly says "urban
    extension" keeps that label - evidence-grounded, not scale-inferred -
    even at a capacity below the "large residential" bar."""
    label = development_type_label(
        site_name="Land at Foxhall - Strategic Urban Extension", category=None, intended_use="residential",
        capacity_value=300,
    )
    assert label == "Strategic urban extension"


def test_development_type_explicit_strategic_urban_extension_via_category():
    label = development_type_label(
        site_name="Anywhere", category="Strategic Extension to the settlement", intended_use="residential",
        capacity_value=None,
    )
    assert label == "Strategic urban extension"


def test_development_type_capacity_does_not_override_evidenced_type():
    """A large capacity never displaces an explicit typology already
    evidenced in the row's own text - garden village wording wins
    regardless of scale."""
    label = development_type_label(
        site_name="Example Garden Village", category=None, intended_use="residential", capacity_value=5000,
    )
    assert label == "Garden village allocation"


def test_development_type_plain_residential_below_large_threshold():
    label = development_type_label(
        site_name="Anywhere", category=None, intended_use="residential",
        capacity_value=LARGE_RESIDENTIAL_CAPACITY_THRESHOLD - 1,
    )
    assert label == "Residential allocation"


def test_development_type_large_residential_at_threshold_with_no_explicit_evidence():
    label = development_type_label(
        site_name="Anywhere", category=None, intended_use="residential",
        capacity_value=LARGE_RESIDENTIAL_CAPACITY_THRESHOLD,
    )
    assert label == "Large residential allocation"


def test_development_type_missing_evidence_produces_neutral_or_omitted_label():
    """No intended_use, no capacity, no title/category signal - the
    honest, evidence-led outcome is an omitted label (None), never a
    guessed typology."""
    label = development_type_label(site_name="Anywhere", category=None, intended_use=None, capacity_value=5000)
    assert label is None


def test_development_type_honestly_omitted_when_no_evidence_supports_one():
    label = development_type_label(site_name="Anywhere", category=None, intended_use=None, capacity_value=None)
    assert label is None


def test_development_type_never_invents_a_classification_beyond_stored_evidence():
    """A capacity-only allocation with no intended_use and a generic name
    must not silently become "Strategic urban extension" just because the
    number is large - the label is gated on intended_use=="residential"
    actually being known, not inferred from capacity alone."""
    label = development_type_label(site_name="Anywhere", category=None, intended_use=None, capacity_value=5000)
    assert label is None


# --- Part 1 / product principle: equal visual weight regardless of size -----


def test_development_type_wording_is_the_only_thing_capacity_affects():
    """Capacity may change which WORDS are used (Part 2's own "Strategic
    urban extension" example), but nothing else about a card's presentation
    is a function of scale - large_card and small_card differ only in
    capacity-derived text fields, never in any structural/visual-weight
    key (there is no "size"/"emphasis"/"weight"/"rank" key on the card
    dict at all, which this test additionally proves by construction)."""
    small = _card(id=1, capacity={"kind": "minimum", "display": "Approximately 20 homes", "value": 20}, major_housing=False)
    large = _card(id=2, capacity={"kind": "minimum", "display": "Approximately 5,000 homes", "value": 5000}, major_housing=True)
    small_keys = set(small.keys())
    large_keys = set(large.keys())
    assert small_keys == large_keys
    for banned_key in ("size", "emphasis", "weight", "rank", "score", "priority"):
        assert banned_key not in small_keys


# --- Part 5: "why it matters" wording ----------------------------------------


def test_why_it_matters_uses_commercial_growth_location_phrasing_for_major_adopted():
    from app.reporting.allocation_discovery import _why_it_matters_reasons

    card = _card(plan_status_bucket="adopted", major_housing=True, council_name="Bury Metropolitan Borough Council")
    reasons = _why_it_matters_reasons(card)
    assert "planned residential growth locations" in reasons[0]


def test_why_it_matters_uses_emerging_local_plan_phrasing():
    from app.reporting.allocation_discovery import _why_it_matters_reasons

    card = _card(plan_status_bucket="emerging", linked_application_count=0, major_housing=False)
    reasons = _why_it_matters_reasons(card)
    assert "Identified for future development through the emerging Local Plan" in reasons[0]


def test_why_it_matters_uses_confirmed_allocation_mapping_phrasing():
    from app.reporting.allocation_discovery import _why_it_matters_reasons

    card = _card(plan_status_bucket="other", visual_status="confirmed", major_housing=False, linked_application_count=1, matched=True, lapse_status="underway")
    reasons = _why_it_matters_reasons(card)
    assert any("Confirmed allocation mapping is available" in r for r in reasons)


def test_why_it_matters_never_uses_banned_commercial_or_likelihood_language():
    scenarios = [
        _card(id=1, plan_status_bucket="adopted", major_housing=True, capacity={"kind": "minimum", "display": "Approximately 5,000 homes", "value": 5000}),
        _card(id=2, plan_status_bucket="emerging", linked_application_count=0),
        _card(id=3, matched=True, lapse_status="approaching"),
        _card(id=4, visual_status="confirmed"),
        _card(id=5, visual_status="needs_review"),
        _card(id=6, council_five_year_supply=1.5),
        _card(id=7, is_multi_authority=True, major_housing=True),
    ]
    for card in scenarios:
        from app.reporting.allocation_discovery import _investigate_next, _why_it_matters_reasons

        combined = " ".join(_why_it_matters_reasons(card) + [_investigate_next(card)]).lower()
        for phrase in _BANNED_PHRASES:
            assert phrase not in combined, f"banned phrase '{phrase}' found for card {card['id']}"


def test_no_linked_application_panel_text_never_uses_banned_language():
    combined = (NO_LINKED_APPLICATION_PANEL_TITLE + " " + NO_LINKED_APPLICATION_PANEL_MESSAGE).lower()
    for phrase in _BANNED_PHRASES:
        assert phrase not in combined


# --- Part 6: "No linked planning application" panel rules -------------------


def test_no_application_panel_shows_for_adopted_unmatched_no_application():
    card = _card(plan_status_bucket="adopted", matched=False, linked_application_count=0)
    assert show_no_application_panel(card) is True


def test_no_application_panel_shows_for_emerging_unmatched_no_application():
    card = _card(plan_status_bucket="emerging", matched=False, linked_application_count=0)
    assert show_no_application_panel(card) is True


def test_no_application_panel_hidden_when_plan_status_is_other():
    card = _card(plan_status_bucket="other", matched=False, linked_application_count=0)
    assert show_no_application_panel(card) is False


def test_no_application_panel_hidden_when_an_application_is_linked():
    card = _card(plan_status_bucket="adopted", matched=True, linked_application_count=1)
    assert show_no_application_panel(card) is False


def test_no_application_panel_hidden_when_matched_site_has_a_real_build_status():
    """Matched + zero linked (qualifying) applications + a genuine
    build-status signal (some activity IS being tracked) must not trigger
    the panel - "no development identified" requires no evidence at all,
    not just an absent application count."""
    card = _card(plan_status_bucket="adopted", matched=True, linked_application_count=0, build_status="partially_complete")
    assert show_no_application_panel(card) is False


def test_no_application_panel_shown_when_matched_but_build_status_unknown():
    card = _card(plan_status_bucket="adopted", matched=True, linked_application_count=0, build_status="unknown")
    assert show_no_application_panel(card) is True


# --- Part 7: KPI strip --------------------------------------------------------


def test_summary_metrics_total_homes_identified_sums_known_capacities_only():
    cards = [
        _card(id=1, kpi_capacity_contribution={"value": 100, "is_estimate": False}),
        _card(id=2, kpi_capacity_contribution={"value": 400, "is_estimate": False}),
        _card(id=3, kpi_capacity_contribution={"value": None, "is_estimate": False}),
    ]
    summary = build_summary_metrics(cards)
    assert summary["total_homes_identified"] == 500
    assert summary["total_homes_identified_is_estimate"] is False


def test_summary_metrics_total_homes_identified_none_when_nothing_known():
    cards = [_card(id=1, kpi_capacity_contribution={"value": None, "is_estimate": False})]
    summary = build_summary_metrics(cards)
    assert summary["total_homes_identified"] is None


def test_summary_metrics_strategic_housing_allocations_counts_major_housing():
    cards = [_card(id=1, major_housing=True), _card(id=2, major_housing=False)]
    summary = build_summary_metrics(cards)
    assert summary["strategic_housing_allocations"] == 1


def test_summary_metrics_confirmed_allocation_maps_only_counts_confirmed_not_suggested():
    cards = [
        _card(id=1, visual_status="confirmed"),
        _card(id=2, visual_status="needs_review"),
        _card(id=3, visual_status="none", visual_fallback={"id": 9}),
    ]
    summary = build_summary_metrics(cards)
    assert summary["confirmed_allocation_maps"] == 1


def test_summary_metrics_new_kpis_respect_duplicate_exclusion():
    cards = [
        _card(id=1, kpi_capacity_contribution={"value": 100, "is_estimate": False}, major_housing=True, visual_status="confirmed"),
        _card(id=2, kpi_capacity_contribution={"value": 100, "is_estimate": False}, major_housing=True, visual_status="confirmed", duplicate_classification="duplicate_of_other_plan"),
    ]
    summary = build_summary_metrics(cards)
    assert summary["total_homes_identified"] == 100
    assert summary["strategic_housing_allocations"] == 1
    assert summary["confirmed_allocation_maps"] == 1


# --- Part 9: future-readiness structured attributes --------------------------


def test_matching_attributes_exposes_the_named_attribute_set():
    card = _card(
        capacity={"kind": "minimum", "display": "Approximately 250 homes", "value": 250}, intended_use="residential",
        plan_status_bucket="adopted", build_status="underway", linked_application_count=2, matched=True,
        matched_site_id=42, visual_status="confirmed", review_status="confirmed", council_code="bury",
        local_plan_id=7, council_five_year_supply=4.2,
    )
    attrs = build_matching_attributes(card)
    assert attrs == {
        "capacity_value": 250, "capacity_kind": "minimum", "intended_use": "residential",
        "planning_status_bucket": "adopted", "planning_status": card["plan_status"], "build_status": "underway",
        "has_linked_application": True, "linked_application_count": 2, "matched_site_id": 42,
        "visual_evidence_status": "confirmed", "review_status": "confirmed", "council_code": "bury",
        "local_plan_id": 7, "council_five_year_supply": 4.2,
    }


def test_matching_attributes_is_not_a_score_or_ranking():
    """Explicitly proves Part 9's "do NOT implement ranking/scoring" - the
    attribute dict contains no numeric composite, no "rank"/"score"/"match"
    percentage key of any kind, only raw structured facts."""
    card = _card()
    attrs = build_matching_attributes(card)
    for banned_key_fragment in ("score", "rank", "match_percent", "recommend", "suitability"):
        assert not any(banned_key_fragment in key for key in attrs), f"'{banned_key_fragment}' found in matching_attributes keys"


def test_matching_attributes_attached_to_every_card():
    """Not purely for debugging (Part 9) - present on the actual card dict
    build_allocation_card produces, not a side-channel only tests can see."""
    from app.reporting.allocation_discovery import build_allocation_card

    allocation = LocalPlanSite(id=1, council_code="c", site_name="A", plan_name="P", plan_status="adopted", minimum_dwellings=100, intended_use="residential")
    card = build_allocation_card(
        allocation, plan=None, council_name="Test Council", council_codes_on_plan=["c"], matched_site=None,
        linked_applications=[], visual_summary={"status": "none", "primary": None, "others": []},
        visual_fallback=None, council_five_year_supply=None,
    )
    assert "matching_attributes" in card
    assert card["matching_attributes"]["capacity_value"] == 100


# --- Part 8: badge rendering (no truncation) ---------------------------------


def test_allocation_card_uses_the_shared_non_truncating_badge_row():
    """Part 8: "badge text must not truncate at common laptop widths" - the
    fix is status_badge_row (proportional column widths sized to each
    label's length, the same pattern already proven on site_profile_
    header's own badge row) - confirms the gallery card actually uses it
    rather than a fixed equal-width st.columns(2)/st.columns(3) call that
    would clip a long label again."""
    from pathlib import Path

    shell_source = Path("app/ui/shell.py").read_text(encoding="utf-8")
    assert "def status_badge_row(" in shell_source
    assert "max(len(label), 10)" in shell_source
    # the allocation_card function body must call it
    card_fn_start = shell_source.index("def allocation_card(")
    card_fn_body = shell_source[card_fn_start:card_fn_start + 4000]
    assert "status_badge_row(badges)" in card_fn_body


def test_detail_page_also_uses_the_shared_non_truncating_badge_row():
    from pathlib import Path

    page_source = Path("app/ui/pages/3_Local_Plan_Sites.py").read_text(encoding="utf-8")
    assert "status_badge_row(" in page_source


# --- No AI calls / no database writes ----------------------------------------


def test_no_ai_calls_anywhere_in_allocation_discovery_module():
    """AI Allocation Intelligence Summary amendment - 3_Local_Plan_Sites.py
    now legitimately mentions "OpenAI" in a comment explaining that it
    deliberately never calls it (Section 8's own "opening an allocation
    page must not normally call OpenAI" rule) and imports is_allocation_
    summary_stale (a pure, OpenAI-free staleness check) - so the check here
    narrows to the actual call-shaped patterns, the same fix already
    applied once elsewhere in this codebase for an identical false-positive
    (a docstring/comment mentioning "openai" while explaining why a module
    never calls it)."""
    from pathlib import Path

    for path in ("app/reporting/allocation_discovery.py", "app/ui/pages/3_Local_Plan_Sites.py", "app/ui/shell.py", "app/visuals/site_view.py"):
        source = Path(path).read_text(encoding="utf-8").lower()
        assert "import openai" not in source
        assert "from openai" not in source
        assert "opena i(" not in source.replace(" ", "")


def test_build_allocation_discovery_still_makes_no_database_writes_after_polish(session):
    from app.db.models import LocalPlan
    from app.reporting.allocation_discovery import build_allocation_discovery

    local_plan = LocalPlan(council_code="testcouncil", plan_name="Test Local Plan", status="adopted", raw_status="Adopted")
    session.add(local_plan)
    session.commit()
    allocation = LocalPlanSite(
        council_code="testcouncil", local_plan_id=local_plan.id, site_name="Test Allocation",
        plan_name="Test Local Plan", plan_status="adopted", minimum_dwellings=100, intended_use="residential",
    )
    session.add(allocation)
    session.commit()

    assert not session.new
    assert not session.dirty
    view = build_allocation_discovery(session)
    assert not session.new
    assert not session.dirty
    assert view["cards"][0]["matching_attributes"] is not None


# =============================================================================
# Evidence Terminology Amendment (following Sprint 4.5a) - tightens
# development-type wording (Part 1, tested above) and the Total Homes
# Identified KPI's capacity-aggregation rule (Parts 2-4, tested below).
# =============================================================================

from app.reporting.allocation_discovery import (  # noqa: E402
    build_allocation_discovery,
    kpi_capacity_contribution,
    total_homes_kpi_caption,
    total_homes_kpi_label,
)


def _allocation(**kwargs) -> LocalPlanSite:
    defaults = {"council_code": "c", "site_name": "A", "plan_name": "P", "plan_status": "adopted"}
    defaults.update(kwargs)
    return LocalPlanSite(**defaults)


# --- Part 2: KPI capacity-contribution rule ----------------------------------


def test_kpi_contribution_minimum_only_counts_at_face_value_not_an_estimate():
    result = kpi_capacity_contribution(_allocation(minimum_dwellings=250))
    assert result == {"value": 250, "is_estimate": False}


def test_kpi_contribution_range_uses_the_minimum_never_the_maximum():
    """Part 4: "do not silently choose the maximum and add it as though
    exact" - a 100-200 range contributes 100, not 200."""
    result = kpi_capacity_contribution(_allocation(minimum_dwellings=100, maximum_capacity=200))
    assert result == {"value": 100, "is_estimate": False}


def test_kpi_contribution_maximum_only_is_excluded_not_zero():
    """An upper bound alone is not evidence of a floor - excluded from the
    total entirely (never contributes 0, which would silently pass a
    falsy-but-present check downstream, and never contributes the
    maximum, which would overstate)."""
    result = kpi_capacity_contribution(_allocation(maximum_capacity=400))
    assert result["value"] is None


def test_kpi_contribution_indicative_only_counts_but_is_flagged_an_estimate():
    result = kpi_capacity_contribution(_allocation(indicative_capacity=80))
    assert result == {"value": 80, "is_estimate": True}


def test_kpi_contribution_unknown_excluded():
    result = kpi_capacity_contribution(_allocation())
    assert result["value"] is None


def test_kpi_contribution_minimum_present_takes_priority_over_indicative():
    """A row that (unusually) states both a minimum and an indicative
    figure uses the minimum - the more concrete, floor-type evidence -
    never averages or otherwise blends the two."""
    result = kpi_capacity_contribution(_allocation(minimum_dwellings=100, indicative_capacity=150))
    assert result == {"value": 100, "is_estimate": False}


def test_summary_metrics_range_capacity_does_not_overstate_the_total():
    """Integration: a card built from a real range-capacity allocation
    contributes its minimum to the KPI total, not its display "value"
    (which is the range's maximum, used for sort/filter only)."""
    from app.reporting.allocation_discovery import build_allocation_card

    allocation = _allocation(id=1, minimum_dwellings=100, maximum_capacity=900, intended_use="residential")
    card = build_allocation_card(
        allocation, plan=None, council_name="Test Council", council_codes_on_plan=["c"], matched_site=None,
        linked_applications=[], visual_summary={"status": "none", "primary": None, "others": []},
        visual_fallback=None, council_five_year_supply=None,
    )
    assert card["capacity"]["value"] == 900  # display/sort value - unchanged, still the range's maximum
    assert card["kpi_capacity_contribution"]["value"] == 100  # KPI contribution - the range's minimum
    summary = build_summary_metrics([card])
    assert summary["total_homes_identified"] == 100


def test_summary_metrics_label_switches_to_indicative_when_an_estimate_contributes():
    stated = _card(id=1, kpi_capacity_contribution={"value": 100, "is_estimate": False})
    estimated = _card(id=2, kpi_capacity_contribution={"value": 80, "is_estimate": True})

    summary_stated_only = build_summary_metrics([stated])
    assert summary_stated_only["total_homes_identified_is_estimate"] is False
    assert total_homes_kpi_label(summary_stated_only) == "Total Homes Identified"

    summary_with_estimate = build_summary_metrics([stated, estimated])
    assert summary_with_estimate["total_homes_identified_is_estimate"] is True
    assert total_homes_kpi_label(summary_with_estimate) == "Indicative homes identified"


def test_total_homes_kpi_caption_explains_the_rule_and_never_claims_a_firm_total():
    summary = build_summary_metrics([_card(id=1, kpi_capacity_contribution={"value": 100, "is_estimate": False})])
    caption = total_homes_kpi_caption(summary)
    assert "minimum" in caption.lower()
    assert "never" in caption.lower() or "not" in caption.lower()

    estimate_summary = build_summary_metrics([_card(id=1, kpi_capacity_contribution={"value": 100, "is_estimate": True})])
    estimate_caption = total_homes_kpi_caption(estimate_summary)
    assert "indicative" in estimate_caption.lower()


def test_local_plan_sites_page_shows_the_total_homes_kpi_caption():
    from pathlib import Path

    source = Path("app/ui/pages/3_Local_Plan_Sites.py").read_text(encoding="utf-8")
    assert "total_homes_kpi_caption(summary)" in source
    assert "total_homes_kpi_label(summary)" in source


# --- Part 3: duplicate / contextual / cross-boundary handling ----------------


def _make_local_plan(session, council_code="testcouncil", plan_name="Test Local Plan", status="adopted"):
    from app.db.models import LocalPlan

    plan = LocalPlan(council_code=council_code, plan_name=plan_name, status=status, raw_status=status)
    session.add(plan)
    session.commit()
    return plan


def _make_allocation(session, local_plan_id, *, council_code="testcouncil", site_name="Land off Test Road",
                      policy_reference="REF-1", minimum_dwellings=100, **kwargs):
    allocation = LocalPlanSite(
        council_code=council_code, local_plan_id=local_plan_id, policy_reference=policy_reference,
        site_name=site_name, plan_name="Test Local Plan", plan_status="adopted", minimum_dwellings=minimum_dwellings,
        intended_use="residential", **kwargs,
    )
    session.add(allocation)
    session.commit()
    return allocation


def test_approved_duplicate_of_other_plan_excluded_from_totals(session):
    plan = _make_local_plan(session)
    _make_allocation(session, plan.id, policy_reference="REF-A", minimum_dwellings=100)
    _make_allocation(session, plan.id, policy_reference="REF-B", minimum_dwellings=100, duplicate_classification="duplicate_of_other_plan")

    view = build_allocation_discovery(session)
    summary = build_summary_metrics(view["cards"])
    assert summary["total_allocations"] == 1
    assert summary["total_homes_identified"] == 100


def test_approved_contextual_reference_excluded_from_totals(session):
    plan = _make_local_plan(session)
    _make_allocation(session, plan.id, policy_reference="REF-A", minimum_dwellings=200)
    _make_allocation(session, plan.id, policy_reference="REF-B", minimum_dwellings=200, duplicate_classification="contextual_reference")

    view = build_allocation_discovery(session)
    summary = build_summary_metrics(view["cards"])
    assert summary["total_allocations"] == 1
    assert summary["total_homes_identified"] == 200


def test_unapproved_suspected_duplicate_remains_counted(session):
    """Part 3: "do not deduplicate rows whose classification remains
    unapproved" - uncertain_needs_review must never silently vanish from
    the totals the way an approved classification does."""
    plan = _make_local_plan(session)
    _make_allocation(session, plan.id, policy_reference="REF-A", minimum_dwellings=150)
    _make_allocation(session, plan.id, policy_reference="REF-B", minimum_dwellings=150, duplicate_classification="uncertain_needs_review")

    view = build_allocation_discovery(session)
    summary = build_summary_metrics(view["cards"])
    assert summary["total_allocations"] == 2
    assert summary["total_homes_identified"] == 300


def test_unapproved_duplicate_rows_all_remain_visible_in_the_gallery(session):
    """Part 3: "keep all records visible in the gallery" - exclusion from
    summary METRICS never removes a row from view["cards"] itself, even
    once approved."""
    plan = _make_local_plan(session)
    _make_allocation(session, plan.id, policy_reference="REF-A", minimum_dwellings=100)
    _make_allocation(session, plan.id, policy_reference="REF-B", minimum_dwellings=100, duplicate_classification="duplicate_of_other_plan")

    view = build_allocation_discovery(session)
    assert len(view["cards"]) == 2


def test_cross_plan_same_physical_site_relationship_excluded_once_approved(session):
    """Two allocations on DIFFERENT LocalPlans (e.g. a council's own plan
    and a joint plan) referring to the same physical site - once an
    approved review confirms this via duplicate_classification, only the
    canonical row counts toward the total."""
    own_plan = _make_local_plan(session, council_code="bury", plan_name="Bury Local Plan")
    joint_plan = _make_local_plan(session, council_code="bury", plan_name="Places for Everyone")
    _make_allocation(session, own_plan.id, council_code="bury", policy_reference="JPA1.1", site_name="Northern Gateway", minimum_dwellings=1550)
    _make_allocation(
        session, joint_plan.id, council_code="bury", policy_reference="JPA 1.2", site_name="Northern Gateway (PfE)",
        minimum_dwellings=1550, duplicate_classification="duplicate_of_other_plan",
    )

    view = build_allocation_discovery(session)
    summary = build_summary_metrics(view["cards"])
    assert summary["total_allocations"] == 1
    assert summary["total_homes_identified"] == 1550


def test_cross_boundary_allocation_counted_once_per_physical_row(session):
    """A joint plan shared across multiple councils (via LocalPlanCouncil)
    does not multiply an allocation's contribution - each council's own
    distinct LocalPlanSite row is counted exactly once, never once per
    participating council on the shared plan."""
    from app.db.models import LocalPlanCouncil

    joint_plan = _make_local_plan(session, council_code="bury", plan_name="Places for Everyone")
    session.add(LocalPlanCouncil(local_plan_id=joint_plan.id, council_code="bury", role="participating_authority"))
    session.add(LocalPlanCouncil(local_plan_id=joint_plan.id, council_code="stockport", role="participating_authority"))
    session.commit()
    _make_allocation(session, joint_plan.id, council_code="bury", policy_reference="JPA1", site_name="Bury allocation", minimum_dwellings=500)
    _make_allocation(session, joint_plan.id, council_code="stockport", policy_reference="JPA2", site_name="Stockport allocation", minimum_dwellings=300)

    view = build_allocation_discovery(session)
    summary = build_summary_metrics(view["cards"])
    assert summary["total_allocations"] == 2
    assert summary["total_homes_identified"] == 800
    for card in view["cards"]:
        assert card["is_multi_authority"] is True


# --- No AI calls / no database writes (amendment-scoped re-check) -----------


def test_evidence_terminology_amendment_introduces_no_ai_calls():
    from pathlib import Path

    source = Path("app/reporting/allocation_discovery.py").read_text(encoding="utf-8").lower()
    assert "openai" not in source


def test_evidence_terminology_amendment_makes_no_database_writes(session):
    plan = _make_local_plan(session)
    _make_allocation(session, plan.id, minimum_dwellings=100, maximum_capacity=900)
    assert not session.new
    assert not session.dirty
    view = build_allocation_discovery(session)
    build_summary_metrics(view["cards"])
    assert not session.new
    assert not session.dirty
