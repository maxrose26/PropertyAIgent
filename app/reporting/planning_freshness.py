"""Request-local status/freshness presentation; no query, matcher or persistence.

A failed attempt can be shown only when an exact-reference outcome and attempt
instant are available to the current caller. After runtime loss it is unavailable,
not inferred from council run health or document checks.
"""
from dataclasses import dataclass
import datetime as dt
from app.pipeline.material_change import _classify_planning_state
from app.pipeline.status_verification import COMPLETED_OUTCOMES, OUTCOME_CONFLICTING


@dataclass(frozen=True)
class PlanningFreshness:
    planning_state: str
    source_fact_date: str | None
    source_url: str | None
    last_successful_verification: dt.datetime | None
    freshness: str
    qualification: str
    attempt_visibility: str


def _utc(value):
    return value.replace(tzinfo=dt.timezone.utc) if value.tzinfo is None else value.astimezone(dt.timezone.utc)


def present_planning_freshness(application, *, now, cadence_days=None,
                               current_outcome=None, attempted_at=None):
    """Cadence is supplied by the existing status/operational policy, never guessed.

    Future/faulty clocks remain qualified. Same-scope source timestamps only;
    neither parent timestamps nor stored AI prose is consumed.
    """
    verified = application.status_verified_at
    state = _classify_planning_state(application.decision, application.status)
    freshness = "verification_unavailable"
    qualification = "Successful status verification unavailable"
    visibility = "unavailable"
    if verified:
        if _utc(verified) > _utc(now):
            freshness, qualification = "verification_unavailable", "Verification timestamp requires review"
        elif cadence_days is None:
            freshness, qualification = "verified_as_of", "Verified as of the recorded date; current status may require refresh"
        elif cadence_days <= 0:
            raise ValueError("Cadence must be positive")
        elif _utc(now) - _utc(verified) > dt.timedelta(days=cadence_days):
            freshness, qualification = "requires_refresh", "Current status requires refresh"
        else:
            freshness, qualification = "verified_within_policy", "Verified within the supplied check policy; status is as-of verification"
    if current_outcome is not None:
        if current_outcome.application_reference != application.reference:
            raise ValueError("Verification outcome belongs to another application")
        if attempted_at is not None and _utc(attempted_at) <= _utc(now):
            visibility = "request_local_only"
            if (verified is None or _utc(attempted_at) > _utc(verified)) and current_outcome.outcome not in COMPLETED_OUTCOMES:
                freshness = "conflicting" if current_outcome.outcome == OUTCOME_CONFLICTING else "currently_unverifiable"
                qualification = "Source conflict requires review" if freshness == "conflicting" else "Latest available check did not verify current status; accepted fact retained"
    from app.pipeline.lapse_tracking import parse_portal_date
    raw_date = application.decision_issued_date
    parsed_date = parse_portal_date(raw_date)
    fact_date = parsed_date.isoformat() if parsed_date != dt.date.min else None
    from urllib.parse import urlsplit
    url = application.summary_url
    safe_url = url if url and urlsplit(url).scheme in {"http", "https"} and urlsplit(url).hostname and not urlsplit(url).username and not urlsplit(url).password else None
    return PlanningFreshness(state, fact_date, safe_url, verified, freshness, qualification, visibility)
