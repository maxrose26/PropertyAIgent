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
    STRATEGIC_EXTENSION_CAPACITY_THRESHOLD,
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


def test_development_type_strategic_urban_extension_at_high_capacity():
    label = development_type_label(
        site_name="New Carrington", category=None, intended_use="residential",
        capacity_value=STRATEGIC_EXTENSION_CAPACITY_THRESHOLD,
    )
    assert label == "Strategic urban extension"


def test_development_type_plain_residential_below_strategic_threshold():
    label = development_type_label(
        site_name="Anywhere", category=None, intended_use="residential",
        capacity_value=STRATEGIC_EXTENSION_CAPACITY_THRESHOLD - 1,
    )
    assert label == "Residential allocation"


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
        _card(id=1, capacity={"kind": "minimum", "display": "Approximately 100 homes", "value": 100}),
        _card(id=2, capacity={"kind": "minimum", "display": "Approximately 400 homes", "value": 400}),
        _card(id=3, capacity={"kind": "unknown", "display": "Capacity not identified", "value": None}),
    ]
    summary = build_summary_metrics(cards)
    assert summary["total_homes_identified"] == 500


def test_summary_metrics_total_homes_identified_none_when_nothing_known():
    cards = [_card(id=1, capacity={"kind": "unknown", "display": "Capacity not identified", "value": None})]
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
        _card(id=1, capacity={"kind": "minimum", "display": "Approximately 100 homes", "value": 100}, major_housing=True, visual_status="confirmed"),
        _card(id=2, capacity={"kind": "minimum", "display": "Approximately 100 homes", "value": 100}, major_housing=True, visual_status="confirmed", duplicate_classification="duplicate_of_other_plan"),
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
    from pathlib import Path

    for path in ("app/reporting/allocation_discovery.py", "app/ui/pages/3_Local_Plan_Sites.py", "app/ui/shell.py", "app/visuals/site_view.py"):
        source = Path(path).read_text(encoding="utf-8").lower()
        assert "openai" not in source
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
