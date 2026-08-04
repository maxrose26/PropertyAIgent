"""Monitoring cadence for Policy Intelligence sources and reports
(housing-supply monitoring amendment, "Add monitored housing supply and
delivery reports", Part 3).

Recommended defaults from the amendment brief:
    active Local Plan progress/timetable pages             -> weekly
    housing land supply index pages                          -> monthly
    AMR/housing delivery index pages                          -> monthly
    stable adopted-plan documents                             -> quarterly
    sources within an expected publication/adoption window   -> weekly
        (overrides the type-based default, since a source is most likely
        to actually change during its own expected publication window)

Nothing here fetches anything or writes to the database -
compute_next_check_due is a pure function; app.policy.monitor and
app.policy.report_discovery are the only callers allowed to persist its
result onto MonitoredSource.next_check_due / MonitoredReport.next_check_due.
"""
from __future__ import annotations

import datetime as dt

WEEKLY_DAYS = 7
MONTHLY_DAYS = 30
QUARTERLY_DAYS = 90
DEFAULT_DAYS = MONTHLY_DAYS  # a safe default for any source_type not named below

# source_type -> cadence in days. Covers both MonitoredSource (index/
# discovery pages) and MonitoredReport (individual documents) type
# vocabularies - the same function serves both, since "how often is this
# worth re-checking" is the same question either way.
_CADENCE_BY_SOURCE_TYPE: dict[str, int] = {
    # --- Active Local Plan progress/timetable pages - weekly ---
    "timetable": WEEKLY_DAYS,
    "landing_page": WEEKLY_DAYS,
    "webpage": WEEKLY_DAYS,
    "local_development_scheme": WEEKLY_DAYS,
    "consultation_portal": WEEKLY_DAYS,
    "examination_library": WEEKLY_DAYS,
    "emerging_plan": WEEKLY_DAYS,
    # --- Housing land supply / AMR index pages - monthly ---
    "housing_land_supply_page": MONTHLY_DAYS,
    "amr_page": MONTHLY_DAYS,
    "monitoring_page": MONTHLY_DAYS,
    "policy_document_library": MONTHLY_DAYS,
    "evidence_library": MONTHLY_DAYS,
    "authority_monitoring_report": MONTHLY_DAYS,
    "housing_land_supply_statement": MONTHLY_DAYS,
    "five_year_supply_statement": MONTHLY_DAYS,  # legacy synonym, see app.policy.document_selection
    "housing_delivery_report": MONTHLY_DAYS,
    "housing_trajectory": MONTHLY_DAYS,
    "housing_delivery_test_action_plan": MONTHLY_DAYS,
    "housing_delivery_statement": MONTHLY_DAYS,
    # --- Stable adopted-plan / permanent-record documents - quarterly ---
    "adopted_plan": QUARTERLY_DAYS,
    "policies_map": QUARTERLY_DAYS,
    "local_plan": QUARTERLY_DAYS,
    "adoption_statement": QUARTERLY_DAYS,
    "inspector_report": QUARTERLY_DAYS,
    "inspectors_report": QUARTERLY_DAYS,
    "main_modifications": QUARTERLY_DAYS,
}


def _in_expected_publication_window(expected_publication_window: str | None, today: dt.date) -> bool:
    """A permissive, best-effort match - expected_publication_window is
    free text (a month name, "Q4", etc.) since councils state this with
    wildly inconsistent precision (Part 3). A false negative here just
    means the type-based default cadence applies instead, never a hard
    failure."""
    if not expected_publication_window:
        return False
    window = expected_publication_window.strip().lower()
    month_name = today.strftime("%B").lower()
    month_abbr = today.strftime("%b").lower()
    if month_name in window or month_abbr in window:
        return True
    quarter = (today.month - 1) // 3 + 1
    return f"q{quarter}" in window.replace(" ", "")


def compute_cadence_days(source_type: str, expected_publication_window: str | None = None, today: dt.date | None = None) -> int:
    """The number of days until the next check should be due, from now."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    if _in_expected_publication_window(expected_publication_window, today):
        return WEEKLY_DAYS
    return _CADENCE_BY_SOURCE_TYPE.get(source_type, DEFAULT_DAYS)


def compute_next_check_due(source_type: str, expected_publication_window: str | None = None, now: dt.datetime | None = None) -> dt.datetime:
    now = now or dt.datetime.now(dt.timezone.utc)
    days = compute_cadence_days(source_type, expected_publication_window, today=now.date())
    return now + dt.timedelta(days=days)


def is_due(next_check_due: dt.datetime | None, now: dt.datetime | None = None) -> bool:
    """None means never checked - always due. SQLite round-trips a stored
    tz-aware datetime as naive on read back (the same fact app.policy.
    monitor's own _naive_utcnow works around) - comparing naive-to-naive
    UTC wall-clock time throughout is correct here, not a workaround for a
    bug."""
    if next_check_due is None:
        return True
    now = now or dt.datetime.now(dt.timezone.utc)
    naive_due = next_check_due.replace(tzinfo=None) if next_check_due.tzinfo else next_check_due
    naive_now = now.replace(tzinfo=None) if now.tzinfo else now
    return naive_due <= naive_now
