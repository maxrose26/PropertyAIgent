"""Decision/commencement-deadline helpers shared between the Streamlit UI
(app/ui/common.py) and non-UI modules like app/pipeline/phase_tracking.py.

Split out from app/ui/common.py so this pure date/status logic can be reused
without pulling in a streamlit dependency.
"""
from __future__ import annotations

import datetime as dt

from app.db.models import Application, Site


_PORTAL_DATE_FORMATS = [
    "%a %d %b %Y",  # Idox: "Tue 21 Apr 2026" - plain string comparison sorts
                    # on the day-of-week prefix, not the actual date, so this
                    # must be parsed properly rather than compared as text.
    "%d/%m/%Y",     # Arcus's "Valid Date" field: "16/8/2024" - no day name,
                    # no zero-padding. Confirmed real bug: every Arcus
                    # council's dates were silently parsing to date.min here
                    # (day-name format never matches D/M/YYYY text), which
                    # fed date.min into every consumer of this function -
                    # lapse/commencement deadlines, phase "latest grant"
                    # selection, related-application anchor selection, "most
                    # recent first" sorting - across all of Rochdale,
                    # Manchester and Salford.
]


def parse_portal_date(value: str | None) -> dt.date:
    if not value:
        return dt.date.min
    stripped = value.strip()
    for fmt in _PORTAL_DATE_FORMATS:
        try:
            return dt.datetime.strptime(stripped, fmt).date()
        except ValueError:
            continue
    return dt.date.min


# Most full planning permissions carry a standard condition requiring
# development to commence within 3 years of the decision date (unless a
# different period is expressly stated - we don't have condition-level
# detail to know when that's varied, so this is a reasonable default, not a
# guarantee). No construction detected as that deadline approaches or
# passes is a genuine acquisition signal: the landowner may need to
# re-apply, sell, or risk losing the consent entirely.
GRANTED_KEYWORDS = ["approve", "grant"]
COMMENCEMENT_YEARS = 3
LAPSE_WARNING_DAYS = 180  # ~6 months out

# UK statutory target for a "major" application (10+ dwellings, or 0.5ha+
# site area) is 13 weeks from validation, versus 8 weeks for a minor one -
# every application in this database is either a qualifying 10+ unit scheme
# itself or directly tied to one, so 13 weeks is used uniformly rather than
# trying to infer major/minor per application. Councils routinely agree
# extensions of time, so this is a statutory default, not a promise - always
# labelled as an estimate, never presented as a scraped fact.
STATUTORY_MAJOR_DECISION_WEEKS = 13


def estimate_statutory_decision_date(application_validated: str | None) -> dt.date | None:
    """Idox portals don't publish a target/expected decision date field the
    way Arcus councils do (see Application.expected_decision_date) - this
    computes the statutory default instead of leaving the question
    unanswered. Returns None when there's no validation date to compute
    from (e.g. not yet validated)."""
    validated = parse_portal_date(application_validated)
    if validated == dt.date.min:
        return None
    return validated + dt.timedelta(weeks=STATUTORY_MAJOR_DECISION_WEEKS)


def get_expected_decision(app: Application) -> dict:
    """Best available "when might a decision come" answer for one still-
    undecided application - real scraped value where the portal publishes
    one (Arcus councils), the computed statutory default otherwise (Idox).
    Returns date=None, source=None once a decision already exists - the
    question is moot."""
    if app.decision:
        return {"date": None, "source": None}

    if app.expected_decision_date:
        date = parse_portal_date(app.expected_decision_date)
        if date != dt.date.min:
            return {"date": date, "source": "scraped"}

    estimated = estimate_statutory_decision_date(app.application_validated or app.application_received)
    if estimated:
        return {"date": estimated, "source": "estimated"}

    return {"date": None, "source": None}

LAPSE_STATUS_LABELS = {
    "lapsed": "⚠️ Permission may have lapsed",
    "approaching": "⏰ Commencement deadline approaching",
    "underway": "🏗️ Build underway",
    "safe": "OK",
    "not_granted": "Not yet granted",
    "unknown": "Unknown",
}

# RGBA fill colours for the map - one per planning-status bucket above.
# Alpha kept below 255 (~86%) so overlapping pins near each other on a dense
# cluster stay distinguishable rather than fully occluding one another.
LAPSE_STATUS_COLORS: dict[str, list[int]] = {
    "not_granted": [70, 130, 180, 220],   # steel blue - still awaiting decision
    "safe": [34, 139, 34, 220],           # forest green - granted, on track
    "approaching": [255, 165, 0, 220],    # orange - deadline approaching
    "lapsed": [220, 20, 60, 220],         # crimson - may have lapsed
    "underway": [138, 43, 226, 220],      # blue violet - build underway
    "unknown": [150, 150, 150, 220],      # grey - no decision data
}


def is_granted_decision(decision: str | None) -> bool:
    decision_lower = (decision or "").lower()
    return any(kw in decision_lower for kw in GRANTED_KEYWORDS)


# Categories that indicate an application is a follow-on administrative
# filing against an already-granted permission, rather than a new proposal.
# A developer filing one of these is the clearest available portal-native
# evidence that a scheme is actually moving, not just approved on paper -
# these are essentially never filed speculatively. Single-sourced here
# (rather than in app.pipeline.phase_tracking, which uses it too) since
# lapse_tracking is the lower-level module both phase_tracking and this
# whole-site build-status check depend on.
PROGRESS_SIGNAL_CATEGORIES = {"condition_discharge_or_details", "variation_or_amendment"}


def find_progress_signal_filing(
    applications: list[Application], since: dt.date, exclude: Application | None = None,
) -> Application | None:
    """Most recent progress-signal filing received after `since` (typically
    a grant date), or None if there isn't one."""
    candidates = [
        a for a in applications
        if a.application_category in PROGRESS_SIGNAL_CATEGORIES
        and a is not exclude
        and parse_portal_date(a.application_received) > since
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda a: parse_portal_date(a.application_received))


BUILD_STATUS_LABELS = {
    "underway": "🏗️ Underway (filing detected)",
    "complete": "✅ Complete (EPC)",
    "partially_complete": "🏗️ Partially complete (EPC)",
    # Deliberately not "Not started" - an EPC is only lodged near practical
    # completion, so 0 EPCs only proves nothing has finished yet, not that
    # construction hasn't begun (a site mid-build with no logged portal
    # filing looks identical to a genuinely untouched one here).
    "no_completions_yet": "❔ No completions yet (0 EPCs - may still be under construction)",
    "unknown": "Unknown",
}


def classify_build_status(applications: list[Application], site: Site, since: dt.date | None) -> str:
    """Combines two independent "has this actually been built" signals:

    1. Portal-native progress-signal filing (see PROGRESS_SIGNAL_CATEGORIES
       above) - free, always available, no API key needed. Its PRESENCE is
       strong positive evidence of "underway", but its ABSENCE doesn't prove
       nothing has started (not every site generates one of these filings),
       so this can only ever confirm "underway", never "not started".
    2. EPC Open Data (site.build_status, set by
       app.pipeline.run_weekly.stage_check_build_status) - new dwellings get
       an EPC registered near completion, so this is the only signal that
       can distinguish "complete"/"not started" - but needs a free
       EPC_API_KEY (bearer token) in .env, from
       https://get-energy-performance-data.communities.gov.uk, to be
       anything but "unknown".

    Portal evidence of "underway" takes priority when both are present -
    it's the more direct signal and doesn't depend on external API setup.
    """
    if since:
        filing = find_progress_signal_filing(applications, since)
        if filing:
            return "underway"
    return site.build_status or "unknown"


DECISION_STATUS_LABELS = {
    "granted": "Granted",
    "refused": "Refused",
    "withdrawn": "Withdrawn",
    "not_yet_decided": "Awaiting decision",
}


def classify_decision_status(decision: str | None, status: str | None) -> str:
    """Coarse 4-way bucket for the natural-language search's "statuses"
    filter (see app/search/query_parser.py) - confirmed a real case where a
    query for "planning approved" schemes parsed correctly into structured
    filters but the result was never actually applied to the dataframe,
    silently returning everything. Reuses is_granted_decision's own keyword
    check for "granted" so the two stay consistent rather than drifting."""
    if is_granted_decision(decision):
        return "granted"
    decision_lower = (decision or "").lower()
    if "refuse" in decision_lower:
        return "refused"
    status_lower = (status or "").lower()
    if "withdraw" in decision_lower or "withdraw" in status_lower:
        return "withdrawn"
    return "not_yet_decided"


def compute_lapse_status(applications: list[Application], site: Site) -> dict:
    """Uses the most recently granted application on the site - a site can
    have several linked applications (screening opinions, reserved matters,
    variations...), only the granted full/outline one(s) actually start this
    clock."""
    granted_apps = [a for a in applications if is_granted_decision(a.decision) and a.decision_issued_date]
    if not granted_apps:
        return {"status": "not_granted", "deadline": None, "granted_app": None, "build_status": "unknown"}

    latest_granted = max(granted_apps, key=lambda a: parse_portal_date(a.decision_issued_date))
    decision_date = parse_portal_date(latest_granted.decision_issued_date)
    if decision_date == dt.date.min:
        return {"status": "unknown", "deadline": None, "granted_app": latest_granted, "build_status": "unknown"}

    try:
        deadline = decision_date.replace(year=decision_date.year + COMMENCEMENT_YEARS)
    except ValueError:  # 29 Feb decision date, target year isn't a leap year
        deadline = decision_date.replace(year=decision_date.year + COMMENCEMENT_YEARS, day=28)

    build_status = classify_build_status(applications, site, decision_date)
    if build_status in ("underway", "partially_complete", "complete"):
        return {"status": "underway", "deadline": deadline, "granted_app": latest_granted, "build_status": build_status}

    days_left = (deadline - dt.date.today()).days
    if days_left < 0:
        status = "lapsed"
    elif days_left <= LAPSE_WARNING_DAYS:
        status = "approaching"
    else:
        status = "safe"
    return {"status": status, "deadline": deadline, "granted_app": latest_granted, "build_status": build_status}
