"""Sprint 3B ("AI Local Plan Evidence Extraction", Part 11) - tests for
app.policy.document_selection: targeted document-to-category routing
(Part 4) and deterministic conflict precedence (Part 8). No network, no
database - MonitoredSource-shaped stand-ins are plain objects."""
from __future__ import annotations

from types import SimpleNamespace

from app.policy.document_selection import (
    DOCUMENT_TYPE_TO_CATEGORIES,
    resolve_fact_conflict,
    resolve_report_conflict,
    select_sources_for_category,
)


def _source(source_type, published_date=None, name="src"):
    return SimpleNamespace(source_type=source_type, published_date=published_date, name=name)


def _report(source_type, status="current", base_date=None, reporting_period=None, publication_date=None, name="report"):
    return SimpleNamespace(
        source_type=source_type, status=status, base_date=base_date,
        reporting_period=reporting_period, publication_date=publication_date, name=name,
    )


# --- targeted document selection (Part 4) ---

def test_annual_monitoring_report_is_eligible_for_housing_delivery_and_five_year_supply():
    # Housing-supply monitoring amendment ("Add monitored housing supply
    # and delivery reports", Part 4): an AMR covers annual delivery and,
    # where a council bundles it in, the five-year supply position too.
    assert DOCUMENT_TYPE_TO_CATEGORIES["annual_monitoring_report"] == frozenset({"housing_delivery", "five_year_supply"})


def test_five_year_supply_statement_is_only_eligible_for_five_year_supply():
    assert DOCUMENT_TYPE_TO_CATEGORIES["five_year_supply_statement"] == frozenset({"five_year_supply"})


def test_generic_pdf_source_type_is_eligible_for_nothing_automatically():
    # Part 4: "not every document should be sent to every prompt" - an
    # unclassified source type must not be auto-selected for ANY category,
    # forcing an explicit --category override rather than a silent guess.
    assert DOCUMENT_TYPE_TO_CATEGORIES["pdf"] == frozenset()


def test_select_sources_for_category_filters_correctly():
    sources = [
        _source("adopted_plan", name="plan"),
        _source("annual_monitoring_report", name="amr"),
        _source("five_year_supply_statement", name="supply"),
        _source("landing_page", name="landing"),
    ]
    selected = select_sources_for_category(sources, "housing_delivery")
    assert [s.name for s in selected] == ["amr"]

    selected_identity = select_sources_for_category(sources, "plan_identity")
    assert [s.name for s in selected_identity] == ["plan"]


# --- conflict resolution precedence (Part 8) ---

def test_single_source_with_a_value_is_chosen_unambiguously():
    candidates = [{"source": _source("adopted_plan"), "fact": {"value": "936"}}]
    chosen, is_conflict = resolve_fact_conflict(candidates)
    assert is_conflict is False
    assert chosen["fact"]["value"] == "936"


def test_no_candidate_has_a_value_returns_no_conflict_nothing_to_propose():
    candidates = [
        {"source": _source("adopted_plan"), "fact": {"value": None}},
        {"source": _source("annual_monitoring_report"), "fact": {"value": None}},
    ]
    chosen, is_conflict = resolve_fact_conflict(candidates)
    assert chosen is None
    assert is_conflict is False


def test_agreeing_sources_are_not_a_conflict():
    candidates = [
        {"source": _source("adopted_plan"), "fact": {"value": "936"}},
        {"source": _source("evidence_library"), "fact": {"value": "936"}},
    ]
    chosen, is_conflict = resolve_fact_conflict(candidates)
    assert is_conflict is False
    assert chosen["fact"]["value"] == "936"


def test_adoption_statement_outranks_publication_plan_for_current_status():
    # Part 8's own named example: an adoption statement should outrank an
    # earlier publication-stage plan document for the plan's current status.
    candidates = [
        {"source": _source("emerging_plan", published_date="2023-01-01"), "fact": {"value": "Publication"}},
        {"source": _source("adoption_statement", published_date="2024-06-01"), "fact": {"value": "Adopted"}},
    ]
    chosen, is_conflict = resolve_fact_conflict(candidates)
    assert is_conflict is False
    assert chosen["fact"]["value"] == "Adopted"


def test_five_year_supply_statement_outranks_older_amr_for_supply_position():
    candidates = [
        {"source": _source("annual_monitoring_report", published_date="2022-01-01"), "fact": {"value": "5.1"}},
        {"source": _source("five_year_supply_statement", published_date="2024-01-01"), "fact": {"value": "3.2"}},
    ]
    chosen, is_conflict = resolve_fact_conflict(candidates)
    assert is_conflict is False
    assert chosen["fact"]["value"] == "3.2"


def test_tied_precedence_with_different_values_is_a_genuine_conflict():
    # Part 8: "if sources conflict and no safe precedence rule exists,
    # queue for review" - two sources of the SAME type disagreeing must
    # never be silently resolved by picking one.
    candidates = [
        {"source": _source("annual_monitoring_report", published_date="2023-01-01"), "fact": {"value": "40"}},
        {"source": _source("annual_monitoring_report", published_date="2023-01-01"), "fact": {"value": "55"}},
    ]
    chosen, is_conflict = resolve_fact_conflict(candidates)
    assert chosen is None
    assert is_conflict is True


# --- report-level conflict resolution (housing-supply monitoring
# amendment, "Add monitored housing supply and delivery reports", Part 5) ---

def test_newer_amr_by_reporting_period_outranks_an_older_amr_for_annual_delivery():
    # Part 5: "a newer AMR normally outranks an older AMR for annual
    # delivery" - decided by reporting_period/base_date, NOT publication
    # date (an older report re-published later must not win just because
    # its download date is more recent).
    candidates = [
        {"report": _report("authority_monitoring_report", reporting_period="2021/22", publication_date="2024-01-01"), "fact": {"value": "400"}},
        {"report": _report("authority_monitoring_report", reporting_period="2023/24", publication_date="2022-01-01"), "fact": {"value": "452"}},
    ]
    chosen, is_conflict = resolve_report_conflict(candidates)
    assert is_conflict is False
    assert chosen["fact"]["value"] == "452"


def test_housing_land_supply_statement_outranks_amr_for_five_year_supply():
    candidates = [
        {"report": _report("authority_monitoring_report", reporting_period="2023/24"), "fact": {"value": "5.1"}},
        {"report": _report("housing_land_supply_statement", reporting_period="2023/24"), "fact": {"value": "3.2"}},
    ]
    chosen, is_conflict = resolve_report_conflict(candidates)
    assert is_conflict is False
    assert chosen["fact"]["value"] == "3.2"


def test_superseded_reports_are_never_chosen_even_if_otherwise_highest_precedence():
    candidates = [
        {"report": _report("housing_land_supply_statement", status="superseded", reporting_period="2024/25"), "fact": {"value": "2.9"}},
        {"report": _report("authority_monitoring_report", status="current", reporting_period="2023/24"), "fact": {"value": "5.1"}},
    ]
    chosen, is_conflict = resolve_report_conflict(candidates)
    assert is_conflict is False
    assert chosen["fact"]["value"] == "5.1"


def test_two_current_reports_of_the_same_type_and_period_with_different_values_is_a_conflict():
    candidates = [
        {"report": _report("authority_monitoring_report", reporting_period="2023/24"), "fact": {"value": "400"}},
        {"report": _report("authority_monitoring_report", reporting_period="2023/24"), "fact": {"value": "450"}},
    ]
    chosen, is_conflict = resolve_report_conflict(candidates)
    assert chosen is None
    assert is_conflict is True


def test_no_current_report_has_a_value_returns_nothing_to_propose():
    candidates = [{"report": _report("authority_monitoring_report"), "fact": {"value": None}}]
    chosen, is_conflict = resolve_report_conflict(candidates)
    assert chosen is None
    assert is_conflict is False
