"""Tests for app.ui.site_headline (Sprint 3A, "Map Navigation and Site
UX", Part 8). Pure functions - no Streamlit, no database - so every case
here runs without a live browser or a real Site."""
from __future__ import annotations

from app.ui.site_headline import HEADLINE_FIELDS, build_site_headline, clean_tooltip_text, format_site_tooltip

COMPLETE_MERGED = {
    "total_units_final": 150, "total_units_is_estimated": False,
    "affordable_units_final": 30, "affordable_percentage_final": 20.0,
    "developer": "Bloor Homes (North West) Ltd",
}
COMPLETE_LAPSE = {"build_status": "underway"}


def test_headline_fields_are_a_stable_known_set():
    headline = build_site_headline(
        site_id=1, address="1 Test Street", council_label="Test Council",
        merged=COMPLETE_MERGED, lapse=COMPLETE_LAPSE, decision_status="granted",
    )
    assert set(headline.keys()) == set(HEADLINE_FIELDS)


def test_headline_with_complete_data():
    headline = build_site_headline(
        site_id=42, address="1 Sanderling Road, Stockport", council_label="Stockport Metropolitan Borough Council",
        merged=COMPLETE_MERGED, lapse=COMPLETE_LAPSE, decision_status="granted",
        local_plan_status="Allocated (HOM 2.1, progressing)",
    )
    assert headline["site_id"] == 42
    assert headline["address"] == "1 Sanderling Road, Stockport"
    assert headline["council"] == "Stockport Metropolitan Borough Council"
    assert headline["total_units"] == 150
    assert headline["affordable_units"] == 30
    assert headline["affordable_percentage"] == 20.0
    assert headline["decision_status_label"] == "Granted"
    assert headline["developer"] == "Bloor Homes (North West) Ltd"
    assert headline["build_status_label"] is not None
    assert headline["local_plan_status"] == "Allocated (HOM 2.1, progressing)"

    tooltip = format_site_tooltip(headline)
    for expected in ("1 Sanderling Road, Stockport", "Stockport Metropolitan Borough Council",
                      "150 units", "Affordable: 30 (20%)", "Bloor Homes", "Granted", "Allocated (HOM 2.1"):
        assert expected in tooltip


def test_headline_with_missing_optional_fields():
    headline = build_site_headline(
        site_id=7, address="2 Empty Road", council_label="Test Council",
        merged={"total_units_final": None, "affordable_units_final": None, "affordable_percentage_final": None,
                "developer": None, "applicant_company": None, "total_units_is_estimated": False},
        lapse={"build_status": None}, decision_status=None, local_plan_status=None,
    )
    assert headline["total_units"] is None
    assert headline["affordable_units"] is None
    assert headline["decision_status_label"] is None
    assert headline["developer"] is None
    assert headline["build_status_label"] is None
    assert headline["local_plan_status"] is None

    tooltip = format_site_tooltip(headline)
    # Part 2: "do not show empty labels... omit rather than showing None"
    assert "None" not in tooltip
    assert "Click to open scheme details" in tooltip
    # Only the address, council, and final CTA lines should be present -
    # every field derived from merged/lapse/decision_status was None.
    assert tooltip.count("\n") == 2


def test_build_status_unknown_is_omitted_not_shown_as_unknown():
    headline = build_site_headline(
        site_id=1, address=None, council_label=None, merged={}, lapse={"build_status": "unknown"}, decision_status=None,
    )
    assert headline["build_status_label"] is None


def test_build_status_no_completions_yet_is_kept_as_real_information():
    headline = build_site_headline(
        site_id=1, address=None, council_label=None, merged={}, lapse={"build_status": "no_completions_yet"}, decision_status=None,
    )
    assert headline["build_status_label"] is not None
    assert "no_completions_yet" not in headline["build_status_label"]  # the human label, not the raw key


def test_developer_falls_back_to_applicant_company():
    headline = build_site_headline(
        site_id=1, address=None, council_label=None,
        merged={"developer": None, "applicant_company": "Acme Developments Ltd"},
        lapse={}, decision_status=None,
    )
    assert headline["developer"] == "Acme Developments Ltd"


def test_duplicate_site_names_still_resolve_through_the_unique_site_id():
    # Two different Sites that happen to share a display address - the
    # headline is keyed by site_id, not by name, so they never collide.
    shared_address = "Land off Station Road"
    headline_a = build_site_headline(
        site_id=101, address=shared_address, council_label="Test Council", merged={}, lapse={}, decision_status=None,
    )
    headline_b = build_site_headline(
        site_id=202, address=shared_address, council_label="Test Council", merged={}, lapse={}, decision_status=None,
    )
    assert headline_a["site_id"] != headline_b["site_id"]
    assert headline_a["address"] == headline_b["address"]  # same display text is fine...
    assert headline_a["site_id"] == 101 and headline_b["site_id"] == 202  # ...but never confused for navigation


def test_tooltip_strips_template_braces_and_control_characters():
    # Part 7/8: safe escaping of tooltip content - a company name or
    # address containing characters that could be misread as pydeck's own
    # {ColumnName} template tokens, or that would break a single-line
    # tooltip layout.
    headline = build_site_headline(
        site_id=1, address="1 Test Street", council_label="Test Council",
        merged={"developer": "Rogue {Injected} Homes\tLtd\r\nSecond Line"},
        lapse={}, decision_status=None,
    )
    tooltip = format_site_tooltip(headline)
    assert "{" not in tooltip.split("Developer: ")[1].split("\n")[0]
    assert "}" not in tooltip.split("Developer: ")[1].split("\n")[0]
    assert "\t" not in tooltip
    developer_line = next(line for line in tooltip.split("\n") if line.startswith("Developer:"))
    assert "\r" not in developer_line


def test_clean_tooltip_text_truncates_long_values():
    long_name = "A" * 200
    cleaned = clean_tooltip_text(long_name, max_length=50)
    assert len(cleaned) <= 50
    assert cleaned.endswith("…")  # ellipsis


def test_long_address_does_not_break_the_tooltip():
    headline = build_site_headline(
        site_id=1, address="Land at " + ("Very Long Place Name " * 20), council_label="Test Council",
        merged={}, lapse={}, decision_status=None,
    )
    tooltip = format_site_tooltip(headline)
    first_line = tooltip.split("\n")[0]
    assert len(first_line) <= 70
