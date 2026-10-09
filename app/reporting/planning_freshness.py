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
    raw = f"{application.status or ''} {application.decision or ''}".lower()
    if not raw.strip():
        state = "unknown_unverified"
    elif "committee" in raw or "resolution" in raw:
        state = "committee_resolution_unissued"
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
    if state == "committee_resolution_unissued":
        # Legacy conditional approvals must never masquerade as an issued grant.
        # Qualify the stored contradiction; do not rewrite the accepted fields.
        fact_date = None
        if _classify_planning_state(application.decision, application.status) in {"granted", "refused"}:
            freshness = "conflicting"
            qualification = "Committee resolution is not an issued decision; conflicting decision evidence requires review"
    from urllib.parse import urlsplit
    url = application.summary_url
    try:
        parsed_url = urlsplit(url or "")
        safe_url = url if parsed_url.scheme in {"http", "https"} and parsed_url.hostname and not parsed_url.username and not parsed_url.password else None
    except ValueError:
        safe_url = None
    return PlanningFreshness(state, fact_date, safe_url, verified, freshness, qualification, visibility)


# Presentation-only source binding. No reconciliation, matcher or hash changes.
def present_planning_fact_freshness(fact, applications, *, now):
    """Bind to the fact's existing ID AND reference; never choose a replacement.

    Missing/conflicting attribution preserves the reconciled fact but cannot
    claim that a related application verified it. Callers pass already-batched
    applications; this function performs no database access.
    """
    source = fact.source
    matches = [a for a in applications if source is not None
               and a.id == source.application_id
               and a.reference == source.application_reference]
    if fact.determined and len(matches) == 1:
        return present_planning_freshness(matches[0], now=now)
    conflicting = fact.state == "conflict"
    return PlanningFreshness(
        str(fact.value) if fact.determined else "unknown_unverified", None, None, None,
        "conflicting" if conflicting else "verification_unavailable",
        "Planning source conflict requires review" if conflicting else "Current verification unavailable: planning source attribution unresolved",
        "unavailable")


def present_operative_planning_freshness(facts, applications, *, now):
    """Distinct consented/active positions, using each STATUS fact's source.

    The reference/count source can legitimately differ. Never transfer its
    date to the planning-status source, nor combine dates across positions.
    """
    positions = []
    if facts.consented_position.exists:
        positions.append(("Permission", facts.consented_position.planning_status))
    positions.extend((p.scope_label or "Active proposal", p.planning_status) for p in facts.active_positions)
    if not positions:
        positions.append(("Planning position", facts.consented_position.planning_status))
    return tuple((label, fact.source.application_reference if fact.source else None,
                  present_planning_fact_freshness(fact, applications, now=now)) for label, fact in positions)


def planning_freshness_report_columns(positions):
    """Same position-qualified fields for detail/history/CSV; no new age policy."""
    def values(getter):
        return " | ".join(f"{reference or label}: {getter(f)}" for label, reference, f in positions)
    return {
        "Planning Status As Of": values(lambda f: f.planning_state.replace("_", " ")),
        "Planning Source References": " | ".join(reference or "Unresolved" for _, reference, _ in positions),
        "Planning Decision Date": values(lambda f: f.source_fact_date or "Not available"),
        "Planning Verified As Of": values(lambda f: _utc(f.last_successful_verification).isoformat() if f.last_successful_verification else "Not available"),
        "Planning Qualification": values(lambda f: f.qualification),
        "Planning Source URL": " | ".join(f.source_url or "" for _, _, f in positions),
    }
