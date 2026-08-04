"""Housing-supply monitoring amendment ("Add monitored housing supply and
delivery reports", Part 7) - tests for app.policy.report_cadence: source
due-date calculation, weekly/monthly/quarterly cadences, and the expected-
publication-window override. Pure functions, no database, no network."""
from __future__ import annotations

import datetime as dt

from app.policy.report_cadence import compute_cadence_days, compute_next_check_due, is_due


def test_active_local_plan_pages_are_weekly():
    assert compute_cadence_days("timetable") == 7
    assert compute_cadence_days("landing_page") == 7
    assert compute_cadence_days("local_development_scheme") == 7


def test_housing_supply_and_amr_index_pages_are_monthly():
    assert compute_cadence_days("housing_land_supply_page") == 30
    assert compute_cadence_days("amr_page") == 30
    assert compute_cadence_days("authority_monitoring_report") == 30
    assert compute_cadence_days("housing_land_supply_statement") == 30


def test_stable_adopted_plan_documents_are_quarterly():
    assert compute_cadence_days("adopted_plan") == 90
    assert compute_cadence_days("adoption_statement") == 90


def test_unknown_source_type_falls_back_to_a_safe_monthly_default():
    assert compute_cadence_days("some_unregistered_type") == 30


def test_expected_publication_window_overrides_to_weekly_when_current():
    october_5th = dt.date(2026, 10, 5)
    assert compute_cadence_days("adopted_plan", expected_publication_window="October", today=october_5th) == 7


def test_expected_publication_window_does_not_override_when_not_current():
    may_5th = dt.date(2026, 5, 5)
    assert compute_cadence_days("adopted_plan", expected_publication_window="October", today=may_5th) == 90


def test_expected_publication_window_matches_a_quarter_label():
    q4_date = dt.date(2026, 11, 1)  # November -> Q4
    assert compute_cadence_days("adopted_plan", expected_publication_window="Q4", today=q4_date) == 7


def test_compute_next_check_due_adds_the_right_number_of_days():
    now = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    due = compute_next_check_due("amr_page", now=now)
    assert due == now + dt.timedelta(days=30)


def test_is_due_when_never_checked():
    assert is_due(None) is True


def test_is_due_in_the_past():
    now = dt.datetime.now(dt.timezone.utc)
    assert is_due(now - dt.timedelta(days=1), now=now) is True


def test_is_due_in_the_future():
    now = dt.datetime.now(dt.timezone.utc)
    assert is_due(now + dt.timedelta(days=1), now=now) is False


def test_is_due_handles_naive_datetimes_without_crashing():
    # SQLite round-trips a stored tz-aware datetime as naive - is_due must
    # not raise a "can't compare naive and aware" TypeError either way.
    now_naive = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    assert is_due(now_naive - dt.timedelta(days=1)) is True
    assert is_due(now_naive + dt.timedelta(days=1)) is False
