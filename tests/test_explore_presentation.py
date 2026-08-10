"""Tests for the Sprint 4.5b Product Owner amendment's Explore discovery-
table simplification (Parts 16-21) - app.ui.housing_type's new
format_affordable_display/HOUSING_TYPE_BADGE_KIND, and source-level checks
on app/ui/pages/0_Explore.py's presentation (the page itself is a Streamlit
script that bootstraps a DB connection at import time, so - matching this
codebase's established convention, e.g. tests/test_council_intelligence.py's
test_wide_canvas_applied_only_to_council_intelligence_overview - it is
verified by reading its source text, not by importing/executing it).
"""
from __future__ import annotations

from pathlib import Path

from app.ui.housing_type import (
    HOUSING_TYPE_BADGE_KIND,
    HOUSING_TYPE_LABELS,
    classify_housing_type,
    format_affordable_display,
)
from app.ui.shell import _BADGE_KIND_STYLE

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPLORE_SOURCE = (REPO_ROOT / "app" / "ui" / "pages" / "0_Explore.py").read_text(encoding="utf-8")

REMOVED_DEFAULT_COLUMNS = [
    "Tenure Split", "Units Estimated", "Housing Type Note", "Landowner", "Planning Agent",
    "Housing Association", "Registered Provider", "Data Quality", "Needs Review",
]

# "Needs Review" was never a named column in build_report_rows even before
# this sprint (it's a `rows`-only field - the main loop computes it as
# `not merged["core_intelligence_complete"]` for the on-screen table/map,
# but build_report_rows, the CSV/PDF export's shared row builder, never
# included it). Removing it from the default table is therefore not fully
# covered by "remains available via CSV export" - the underlying stored
# fact (SchemeIntelligence.core_intelligence_complete) is untouched and the
# sidebar's existing "Hide schemes needing manual review" filter still acts
# on it, but it isn't a CSV column - a genuine, honestly-reported gap, not
# a regression this sprint introduced (see this sprint's final report).
COLUMNS_REMOVED_AND_STILL_IN_CSV_EXPORT = [c for c in REMOVED_DEFAULT_COLUMNS if c != "Needs Review"]


# --- format_affordable_display -----------------------------------------


def test_format_affordable_display_both_values():
    assert format_affordable_display(45, 30) == "45 (30%)"


def test_format_affordable_display_units_only():
    assert format_affordable_display(45, None) == "45"


def test_format_affordable_display_percentage_only():
    assert format_affordable_display(None, 30) == "30%"


def test_format_affordable_display_neither_is_honest_not_stated():
    """Never a fabricated "0" - absence of evidence reads "Not stated",
    never a blank/None (a fresh pandas column mixing str and None hit a
    real Arrow-rendering bug - a None cell rendered as the literal text
    "None" - confirmed live and fixed by always returning a string)."""
    assert format_affordable_display(None, None) == "Not stated"


def test_format_affordable_display_zero_units_is_not_treated_as_missing():
    assert format_affordable_display(0, 0) == "0 (0%)"


# --- Development Type badge mapping (Part 21) ---------------------------


def test_housing_type_badge_kind_covers_every_classify_housing_type_bucket():
    """Every bucket classify_housing_type can return must have a badge
    kind - no silent KeyError on a real Site's real data."""
    for bucket in ("houses", "apartments", "mixed", "other", "unknown"):
        assert bucket in HOUSING_TYPE_BADGE_KIND
        assert bucket in HOUSING_TYPE_LABELS


def test_every_dev_type_badge_kind_is_styled_and_carries_visible_text():
    """Part 21: "visible text must always accompany colour" - every kind
    HOUSING_TYPE_BADGE_KIND can point at must exist in shell's style table
    with a non-empty label, never colour alone."""
    for kind in HOUSING_TYPE_BADGE_KIND.values():
        assert kind in _BADGE_KIND_STYLE
        assert _BADGE_KIND_STYLE[kind]["label"]


def test_unknown_development_type_has_an_honest_fallback():
    bucket = classify_housing_type(development_type=None, housing_typology=None)
    assert bucket == "unknown"
    assert HOUSING_TYPE_LABELS[bucket] == "Unknown"
    assert HOUSING_TYPE_BADGE_KIND[bucket] == "dev_type_unknown"


def test_development_type_badge_colours_distinguishable_from_plan_status_colours():
    """Part 21: "Planning-status colours and Development-Type colours...
    must remain distinguishable" - checked the only way that's actually
    meaningful: the dev_type_* kinds must not silently share their exact
    (color, icon) pair with any plan_* kind (which would make the two
    concepts visually identical wherever both appear)."""
    plan_pairs = {
        (style["color"], style["icon"]) for kind, style in _BADGE_KIND_STYLE.items() if kind.startswith("plan_")
    }
    for kind in HOUSING_TYPE_BADGE_KIND.values():
        pair = (_BADGE_KIND_STYLE[kind]["color"], _BADGE_KIND_STYLE[kind]["icon"])
        assert pair not in plan_pairs


def test_development_type_presentation_requires_no_ai():
    """Part 21/28 - deterministic mapping only, no AI classification on
    page load."""
    import app.ui.housing_type as housing_type_module
    source = Path(housing_type_module.__file__).read_text(encoding="utf-8")
    assert "openai" not in source.lower()
    assert "OPENAI_API_KEY" not in source


# --- Explore page source checks (Parts 17-20) ----------------------------


def test_removed_fields_are_absent_from_default_desktop_table_columns():
    """Part 17 - the explicit removal list must not appear in
    DESKTOP_TABLE_COLUMNS (the actual on-screen default table)."""
    start = EXPLORE_SOURCE.index("DESKTOP_TABLE_COLUMNS = [")
    end = EXPLORE_SOURCE.index("]", start)
    column_list_source = EXPLORE_SOURCE[start:end]
    for removed in REMOVED_DEFAULT_COLUMNS:
        assert removed not in column_list_source, f"{removed} must not be in the default Explore table"


def test_removed_fields_remain_in_the_csv_export_row_builder():
    """Part 17/19 - "must remain stored and available elsewhere" -
    build_report_rows (both CSV export buttons' shared source) must still
    carry every field removed from the on-screen table."""
    start = EXPLORE_SOURCE.index("def build_report_rows(")
    end = EXPLORE_SOURCE.index("\ndef ", start + 1)
    body = EXPLORE_SOURCE[start:end]
    for removed in COLUMNS_REMOVED_AND_STILL_IN_CSV_EXPORT:
        assert removed in body, f"{removed} must remain available via CSV export"


def test_planning_link_uses_concise_display_text():
    """Part 19 - never the raw URL as visible link text."""
    assert 'display_text="Planning portal ↗"' in EXPLORE_SOURCE


def test_planning_link_column_config_does_not_fabricate_a_url():
    """Part 19 - LinkColumn only ever renders whatever real value is
    already in the "Planning portal" column (renamed from the existing
    "Portal URL"/rep_app.summary_url, per the rename mapping) - the
    destination itself is untouched, only the display text changes."""
    assert '"Portal URL": "Planning portal"' in EXPLORE_SOURCE


def test_mobile_card_view_and_desktop_table_both_always_render():
    """Part 20 - CSS-only switching (both containers render; visibility is
    a CSS media-query concern, not a Python conditional) - never a
    Python-level "if is_mobile:" branch that would only render one."""
    assert 'st.container(key="explore-desktop-table")' in EXPLORE_SOURCE
    assert 'st.container(key="explore-mobile-cards")' in EXPLORE_SOURCE


def test_mobile_card_view_uses_no_javascript_viewport_detection():
    """Part 20 - "Do not introduce brittle JavaScript viewport detection,
    timers or custom responsive hacks." Checked at the page-source level;
    the actual CSS-only switch lives in app.ui.shell.inject_global_styles
    (checked separately below)."""
    for banned in ("window.innerWidth", "matchMedia", "setTimeout", "setInterval", "streamlit.components.v1"):
        assert banned not in EXPLORE_SOURCE


def test_shell_css_switches_explore_table_and_cards_by_media_query_only():
    shell_source = (REPO_ROOT / "app" / "ui" / "shell.py").read_text(encoding="utf-8")
    assert "@media (max-width: 640px)" in shell_source
    assert "@media (min-width: 641px)" in shell_source
    assert "st-key-explore-desktop-table" in shell_source
    assert "st-key-explore-mobile-cards" in shell_source
    # No JS-based responsive technique anywhere in shell.py either.
    for banned in ("window.innerWidth", "matchMedia", "setTimeout", "setInterval"):
        assert banned not in shell_source


def test_mobile_card_shows_only_the_reduced_field_set():
    """Part 20 - "Do not expose every desktop field on mobile." - the
    mobile card block must not render the fields explicitly removed from
    the desktop table either (Landowner, Planning Agent, etc. never
    reappear on mobile just because the desktop table dropped them)."""
    start = EXPLORE_SOURCE.index('st.container(key="explore-mobile-cards")')
    end = EXPLORE_SOURCE.index("\n\n", start)
    body = EXPLORE_SOURCE[start:end]
    for removed in REMOVED_DEFAULT_COLUMNS:
        assert removed not in body


def test_explore_search_scope_labels_use_development_sites_terminology():
    """Part 2 - customer-facing rename, checked directly on the actual
    scope selector and grouped-results source."""
    assert '["All", "Development Sites", "Allocations"]' in EXPLORE_SOURCE
    assert '"Development Sites": "planning_sites"' in EXPLORE_SOURCE
    shell_source = (REPO_ROOT / "app" / "ui" / "shell.py").read_text(encoding="utf-8")
    assert "Development Sites (" in shell_source
    assert "No Development Sites or Allocations matched" in shell_source


def test_explore_entity_search_import_and_filters_still_present():
    """Sanity check that the Sprint 4.5b Entity Search wiring (Parts 4-13)
    survived this continuation's edits intact."""
    assert "from app.reporting.entity_search import search_entities" in EXPLORE_SOURCE
    assert "search_entities(" in EXPLORE_SOURCE


def test_no_db_writes_in_explore_presentation_helpers():
    """Part 28 - the new formatting/presentation code never writes to the
    database."""
    housing_type_source = (REPO_ROOT / "app" / "ui" / "housing_type.py").read_text(encoding="utf-8")
    for banned in ("session.add(", "session.commit(", "session.delete(", ".flush("):
        assert banned not in housing_type_source
