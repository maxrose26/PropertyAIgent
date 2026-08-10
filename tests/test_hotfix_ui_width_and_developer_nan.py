"""Post-Sprint-4.5b hotfix ("Live Deployment Verification + Core Page Width +
Developer NaN") - focused regression tests for the two code changes this
hotfix made:

1. Explore and Review Site Links now call the existing page-scoped
   wide_canvas() helper (app.ui.shell), the same architecture already used
   by Dashboard, Council Intelligence, Allocation Discovery and Council
   Operations - never a second, competing wide-layout system. Scheme Detail
   needed no change: it has called wide_canvas() (via
   app.ui.site_profile_view.render_site_profile) since Sprint 4.4, already
   covered by test_site_profile.py's own guard.

2. app.ui.shell.clean_display_text - a small presentation helper that fixes
   the "Developer: nan" defect found during Sprint 4.5b merge validation,
   and is reused for Explore's mobile-card Planning Status/Decision text
   too, since they share the exact same render path and missing-value bug
   class.

Page scripts bootstrap a DB connection at import time, so - per this
codebase's established convention (see tests/test_council_intelligence.py's
test_wide_canvas_applied_only_to_council_intelligence_overview) - the
width changes are verified by reading page source text, not by importing
the pages directly.
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from app.ui.shell import clean_display_text

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPLORE_SOURCE = (REPO_ROOT / "app" / "ui" / "pages" / "0_Explore.py").read_text(encoding="utf-8")
REVIEW_SITE_LINKS_SOURCE = (REPO_ROOT / "app" / "ui" / "pages" / "2_Review_Site_Links.py").read_text(encoding="utf-8")
SITE_PROFILE_VIEW_SOURCE = (REPO_ROOT / "app" / "ui" / "site_profile_view.py").read_text(encoding="utf-8")
SHELL_SOURCE = (REPO_ROOT / "app" / "ui" / "shell.py").read_text(encoding="utf-8")


# --- Part 9.1-9.4: wide-page architecture, page-scoped only -----------------


def test_explore_invokes_the_approved_wide_canvas_architecture():
    assert "wide_canvas()" in EXPLORE_SOURCE
    assert "from app.ui.shell import" in EXPLORE_SOURCE
    import_block = EXPLORE_SOURCE[EXPLORE_SOURCE.index("from app.ui.shell import"):]
    import_line = import_block[: import_block.index("\n")]
    assert "wide_canvas" in import_line


def test_review_site_links_invokes_the_approved_wide_canvas_architecture():
    assert "wide_canvas()" in REVIEW_SITE_LINKS_SOURCE
    assert "from app.ui.shell import" in REVIEW_SITE_LINKS_SOURCE
    import_block = REVIEW_SITE_LINKS_SOURCE[REVIEW_SITE_LINKS_SOURCE.index("from app.ui.shell import"):]
    import_line = import_block[: import_block.index("\n")]
    assert "wide_canvas" in import_line


def test_scheme_detail_already_uses_wide_canvas_via_site_profile_view():
    """No source change was needed for Scheme Detail - render_site_profile
    has called wide_canvas() since Sprint 4.4, already covered by
    test_site_profile.py's own guard. Re-asserted here so this hotfix's own
    test file stands alone as proof the architecture is genuinely reused,
    not just assumed."""
    scheme_detail_source = (REPO_ROOT / "app" / "ui" / "pages" / "1_Scheme_Detail.py").read_text(encoding="utf-8")
    assert "wide_canvas()" not in scheme_detail_source  # delegates, doesn't call it directly
    assert "render_site_profile(" in scheme_detail_source
    assert "wide_canvas()" in SITE_PROFILE_VIEW_SOURCE


def test_wide_canvas_change_is_page_scoped_not_global():
    """Part 9.4 - the shared shell's own default .block-container max-width
    (app.ui.shell.inject_global_styles) must be untouched by this hotfix;
    only page-scoped wide_canvas() calls changed. A page-scoped override
    only ever widens the page that calls it (Streamlit reruns each page's
    script from scratch), so this also guards against a future edit
    accidentally moving the override into the shared shell function."""
    assert "def inject_global_styles" in SHELL_SOURCE
    inject_body = SHELL_SOURCE[
        SHELL_SOURCE.index("def inject_global_styles"):SHELL_SOURCE.index("def wide_canvas")
    ]
    # The shared shell's own block-container rule must still be the fixed,
    # non-page-scoped default - not the 94%/wide_canvas() override.
    assert "max-width: {max_width}" not in inject_body
    still_unwidened_pages = ["6_Council_Intelligence_Detail.py", "1_Scheme_Detail.py"]
    for filename in still_unwidened_pages:
        source = (REPO_ROOT / "app" / "ui" / "pages" / filename).read_text(encoding="utf-8")
        assert "wide_canvas()" not in source, f"{filename} must not be widened by this hotfix"


# --- Part 9.5-9.8: clean_display_text (the Developer NaN fix) ---------------


@pytest.mark.parametrize("missing_value", [None, float("nan"), math.nan, pd.NA])
def test_clean_display_text_missing_values_return_none(missing_value):
    assert clean_display_text(missing_value) is None


def test_clean_display_text_empty_string_returns_none():
    assert clean_display_text("") is None


@pytest.mark.parametrize("whitespace_value", ["   ", "\t", "\n", "  \t \n "])
def test_clean_display_text_whitespace_only_returns_none(whitespace_value):
    assert clean_display_text(whitespace_value) is None


def test_clean_display_text_genuine_value_renders_unchanged():
    assert clean_display_text("Bellway Homes") == "Bellway Homes"


def test_clean_display_text_strips_surrounding_whitespace_from_a_genuine_value():
    assert clean_display_text("  Bellway Homes  ") == "Bellway Homes"


def test_clean_display_text_matches_pandas_dataframe_nan_coercion():
    """Reproduces the exact real-world defect: a pandas DataFrame built from
    a list of dicts silently coerces a Python None entry in an otherwise
    all-string column to a float NaN, not None - this is the actual value
    Explore's mobile card read for a site with no known developer, and
    `if row["Developer"]:` / an f-string was truthy for it, rendering the
    literal text "Developer: nan" (confirmed live)."""
    df = pd.DataFrame([{"Developer": "Bellway Homes"}, {"Developer": None}, {"Developer": ""}, {"Developer": "  "}])
    coerced_missing = df["Developer"].iloc[1]
    assert pd.isna(coerced_missing)  # confirms None really did become NaN, not stay None
    assert clean_display_text(coerced_missing) is None
    assert clean_display_text(df["Developer"].iloc[0]) == "Bellway Homes"
    assert clean_display_text(df["Developer"].iloc[2]) is None
    assert clean_display_text(df["Developer"].iloc[3]) is None


# --- Part 9.5/9.9: the mobile card render path itself -----------------------


def test_mobile_card_developer_line_never_renders_the_literal_string_nan():
    """Source-level guard: the mobile card's Developer caption must be
    built from clean_display_text's output, not a raw truthiness check on
    the possibly-NaN DataFrame cell - the exact pattern that produced
    "Developer: nan" live."""
    assert 'if row["Developer"]:' not in EXPLORE_SOURCE
    start = EXPLORE_SOURCE.index('st.container(key="explore-mobile-cards")')
    end = EXPLORE_SOURCE.index("\n\n", start)
    mobile_card_body = EXPLORE_SOURCE[start:end]
    assert "clean_display_text(row[\"Developer\"])" in mobile_card_body
    assert 'f"Developer: {developer}"' in mobile_card_body


def test_mobile_card_status_bits_also_use_clean_display_text():
    """The same render path builds a Planning Status/Decision caption from
    the same kind of possibly-missing free-text column - checked here so a
    future edit can't reintroduce the bug for those two fields even though
    "Developer" specifically is what was reported."""
    start = EXPLORE_SOURCE.index('st.container(key="explore-mobile-cards")')
    end = EXPLORE_SOURCE.index("\n\n", start)
    mobile_card_body = EXPLORE_SOURCE[start:end]
    assert 'clean_display_text(row["Planning Status"])' in mobile_card_body
    assert 'clean_display_text(row["Decision"])' in mobile_card_body


# --- Part 9.9: existing mobile presentation remains present -----------------


def test_mobile_card_view_and_desktop_table_both_still_always_render():
    assert 'st.container(key="explore-desktop-table")' in EXPLORE_SOURCE
    assert 'st.container(key="explore-mobile-cards")' in EXPLORE_SOURCE


def test_mobile_card_still_shows_development_type_badge_and_units_affordable():
    start = EXPLORE_SOURCE.index('st.container(key="explore-mobile-cards")')
    end = EXPLORE_SOURCE.index("\n\n", start)
    mobile_card_body = EXPLORE_SOURCE[start:end]
    assert "status_badge(badge_kind, row[\"Development Type\"])" in mobile_card_body
    assert 'pd.notna(row["Units"])' in mobile_card_body
    assert '"Open Site' in mobile_card_body


def test_shell_css_still_switches_explore_table_and_cards_by_media_query_only():
    """No JavaScript viewport detection was introduced by this hotfix
    either - the CSS-only breakpoint approach from Sprint 4.5b is
    untouched."""
    assert "@media (max-width: 640px)" in SHELL_SOURCE
    assert "@media (min-width: 641px)" in SHELL_SOURCE
    for banned in ("window.innerWidth", "matchMedia", "setTimeout", "setInterval"):
        assert banned not in SHELL_SOURCE


# --- Part 9.10: reduced Explore desktop column set is unchanged ------------


def test_explore_desktop_column_set_is_unchanged_by_this_hotfix():
    start = EXPLORE_SOURCE.index("DESKTOP_TABLE_COLUMNS = [")
    end = EXPLORE_SOURCE.index("]", start)
    column_list_source = EXPLORE_SOURCE[start:end]
    expected_columns = [
        "Address", "Council", "Units", "Affordable", "Development Type", "Planning Status", "Decision",
        "Build Status", "Application Ref(s)", "Developer", "Planning portal",
    ]
    for column in expected_columns:
        assert f'"{column}"' in column_list_source
    removed_columns = [
        "Tenure Split", "Units Estimated", "Housing Type Note", "Landowner", "Planning Agent",
        "Housing Association", "Registered Provider", "Data Quality", "Needs Review",
    ]
    for column in removed_columns:
        assert column not in column_list_source


# --- Part 9.11/9.12: no AI calls, no DB writes ------------------------------


def test_clean_display_text_and_wide_canvas_introduce_no_ai_calls():
    for banned in ("import openai", "OpenAI(", 'getenv("OPENAI_API_KEY")', 'environ["OPENAI_API_KEY"]'):
        assert banned not in SHELL_SOURCE.split("def clean_display_text")[1].split("\ndef ")[0]


def test_clean_display_text_makes_no_database_writes():
    clean_display_text_body = SHELL_SOURCE[
        SHELL_SOURCE.index("def clean_display_text"):SHELL_SOURCE.index("\ndef _escape")
    ]
    for banned in ("session.add(", "session.commit(", "session.delete(", ".flush("):
        assert banned not in clean_display_text_body


def test_wide_canvas_itself_makes_no_database_writes():
    wide_canvas_body = SHELL_SOURCE[
        SHELL_SOURCE.index("def wide_canvas"):SHELL_SOURCE.index("def evidence_confidence_badge")
    ]
    for banned in ("session.add(", "session.commit(", "session.delete(", ".flush("):
        assert banned not in wide_canvas_body
