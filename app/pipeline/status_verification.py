"""Gate 2B-0 ("Planning Freshness Remediation") - Planning Status
Verification.

Answers exactly one question, deliberately separate from every other
question this codebase already answers about a planning application:

    "When did PropertyAIgent last directly re-fetch THIS Application's own
    authoritative portal record, by exact reference, and confirm whether
    its status/decision/dates have changed?"

This is NOT the same responsibility as:
  - app.pipeline.run_weekly.stage_fetch_related_applications - which
    searches for OTHER applications citing a known one. See that module's
    own docstring; it is intentionally untouched in its fetch/parse
    mechanics by this module (only its ANCHOR ELIGIBILITY is extended, in
    run_weekly.py itself, per the Gate 2B-0 spec's Section 20-24 - never
    conflated with status verification's own eligibility here).
  - app.pipeline.evidence_refresh.refresh_material_evidence - which
    refreshes DOCUMENTS, and is explicitly, by its own docstring, AI-free
    and never mutates Application.status/decision from document content.

Root cause this module exists to fix (Gate 2B-A investigation, read-only,
production-confirmed): the only paths that can ever update an existing
Application's own status/decision fields are (1) the monthly received/
validated-date search, which never revisits a past month, and (2) the
missing-parent lookup, which only fires once for a reference not yet
known. An Application that never receives a granted decision therefore has
NO existing mechanism that ever re-checks it - confirmed: 173 pending
applications >6 months old, 100% with zero refresh activity of any kind.

Deliberately reuses, unmodified:
  - app.scrapers.idox_portal.fetch_application_by_reference /
    app.scrapers.arcus_portal.fetch_application_by_reference - the exact
    targeted single-reference lookup already proven by
    stage_fetch_missing_parents, just called for an ALREADY-known
    reference instead of an unknown one. No second scraper.
  - app.pipeline.run_weekly._upsert_scraped_application - already generic
    over "any freshly-fetched ScrapedApplication for a known reference",
    already runs app.pipeline.material_change.detect_material_
    application_change and sets evidence_refresh_required on a genuine
    change. No parallel change-detection logic.

Trust-dimension discipline (Gate 2B-0 Section 3): this module implements
EVIDENCE FRESHNESS only (Application.status_verified_at). It does not
touch evidence CONFIDENCE (SchemeIntelligence's own confidence fields) or
RELATIONSHIP CONFIDENCE (no application-family/lineage inference of any
kind lives here) - those remain separate concepts, never combined into
one score.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import CouncilConfig
from app.db.models import Application, Document, SchemeIntelligence
from app.pipeline.material_change import ApplicationState, MaterialChangeStats, detect_material_application_change
from app.pipeline.portal_circuit_breaker import CouncilPortalCircuitBreaker, is_portal_host_failure

# --- Outcome vocabulary (Section 8/16 of the approved spec) -----------------
# Mirrors app.pipeline.evidence_refresh's own OUTCOME_* naming convention
# deliberately - this module is a sibling of that one, not a new pattern.

OUTCOME_VERIFIED_UNCHANGED = "verified_unchanged"
OUTCOME_VERIFIED_CHANGED = "verified_changed"
OUTCOME_APPLICATION_NOT_FOUND = "application_not_found"
OUTCOME_PORTAL_UNAVAILABLE = "portal_unavailable"
# FETCH_FAILED covers both a non-host-level fetch error (HTTP error,
# unexpected redirect, timeout) and a parse failure - the underlying
# fetch_application_by_reference_{idox,arcus} functions do not currently
# distinguish "the page loaded but its fields couldn't be parsed" from
# "the request itself failed" as two different exception types (confirmed
# by inspection - the same precedent already exists in app.pipeline.
# evidence_refresh's own docstring: "every other reason a targeted check
# could not be completed reliably... is ACQUISITION_INCOMPLETE instead").
# A dedicated PARSE_FAILED value is not introduced without a corresponding
# distinguishable exception from the scrapers themselves - inventing one
# here would be exactly the kind of scope expansion the approved spec
# says to stop and report rather than build silently. See the
# implementation report's own "Failure Semantics" section.
OUTCOME_FETCH_FAILED = "fetch_failed"

# Outcomes that count as a genuinely COMPLETED direct verification -
# status_verified_at advances for these two, and only these two (Section 8
# amendment: "APPLICATION_NOT_FOUND does NOT constitute status
# verification").
COMPLETED_OUTCOMES = frozenset({OUTCOME_VERIFIED_UNCHANGED, OUTCOME_VERIFIED_CHANGED})

# --- Tiers and cadence (Section 11/12 of the approved spec, verbatim) -------

TIER_CONTRADICTION_SIGNAL = 1
TIER_LONG_PENDING_OPPORTUNITY = 2
TIER_OTHER_OPPORTUNITY_PENDING = 3
TIER_OTHER_PENDING = 4
# Tier 5 (already-decided applications) is deliberately absent - out of
# scope for Gate 2B-0 V1 status verification (Section 11).

TIER_CADENCE_DAYS: dict[int, int] = {
    TIER_CONTRADICTION_SIGNAL: 7,
    TIER_LONG_PENDING_OPPORTUNITY: 14,
    TIER_OTHER_OPPORTUNITY_PENDING: 30,
    TIER_OTHER_PENDING: 60,
}

# Section 13: "MAXIMUM new direct status-verification attempts: 10
# applications per council per daily run." Named constant, not a bare
# magic number inside the selection query - the approved spec's own
# explicit instruction.
MAX_STATUS_VERIFICATIONS_PER_COUNCIL_PER_RUN = 10

_LONG_PENDING_APPLICATION_KIND = "long_pending_application"


def _is_pending(application: Application) -> bool:
    """A plain, deliberately narrow "no decision recorded yet" check - not
    app.pipeline.lapse_tracking.is_granted_decision's negation (that would
    also treat a refused/withdrawn application as "pending", which it is
    not - Tier 5, already-decided, correctly excludes refused/withdrawn
    applications too, not just granted ones)."""
    return not application.decision


def classify_verification_tier(
    application: Application, *, has_decision_notice: bool, recommendation_direction: str | None,
    opportunity_kinds_for_site: frozenset[str],
) -> int | None:
    """Returns the Application's verification tier, or None if it is not
    eligible for status verification at all (already decided - Tier 5,
    permanently out of scope for V1, per Section 11).

    Deliberately takes already-computed facts (has_decision_notice,
    recommendation_direction, opportunity_kinds_for_site) rather than
    querying them itself - keeps this function pure/unit-testable without
    a database, and lets the caller batch those lookups once per council
    run rather than once per candidate (see select_verification_candidates
    below)."""
    if not _is_pending(application):
        return None  # Tier 5 - already decided, out of scope for V1

    # Tier 1 - Section 11/19: an internal signal that the real-world
    # status has likely already moved, even though this is only ever used
    # to PRIORITISE re-verification, never to infer the outcome itself
    # (Section 19: "DO NOT automatically convert the document into
    # Application.decision"; "must not become 'approved'").
    if has_decision_notice or recommendation_direction == "approval":
        return TIER_CONTRADICTION_SIGNAL

    if _LONG_PENDING_APPLICATION_KIND in opportunity_kinds_for_site:
        return TIER_LONG_PENDING_OPPORTUNITY

    if opportunity_kinds_for_site:
        return TIER_OTHER_OPPORTUNITY_PENDING

    return TIER_OTHER_PENDING


@dataclass
class VerificationCandidate:
    application: Application
    tier: int


def _tier_sort_key(candidate: VerificationCandidate) -> tuple:
    """NULL status_verified_at first, then oldest-verified first, then a
    stable tie-break on id (Section 12: "Within each tier: NULL first,
    then oldest status_verified_at first"). Naive-UTC throughout, same
    convention as the cutoff comparison above - a bare `dt.datetime.min`
    sentinel for NULL sorts before every real (naive) timestamp without
    ever being compared against an aware one."""
    verified_at = candidate.application.status_verified_at
    verified_at_naive = verified_at.replace(tzinfo=None) if verified_at is not None else dt.datetime.min
    return (verified_at is not None, verified_at_naive, candidate.application.id)


def select_verification_candidates(
    session: Session, council_code: str, *, now: dt.datetime | None = None,
    limit: int = MAX_STATUS_VERIFICATIONS_PER_COUNCIL_PER_RUN,
    opportunity_kinds_by_site: dict[int, frozenset[str]] | None = None,
) -> list[VerificationCandidate]:
    """Deterministic, bounded candidate selection for one council's run.

    `opportunity_kinds_by_site`: {site_id: frozenset of planning-delivery
    opportunity kinds ("long_pending_application", "recent_permission",
    "site", "phase") the current Opportunity Universe assigns that site} -
    optional dependency injection so tests never need a real Opportunity
    Universe build; when None, computed once here via
    app.reporting.opportunity_universe (a pure-DB, no-AI, no-network read,
    the same mechanism the existing weekly opportunity sync already
    relies on - see that module's own docstring for why this is safe to
    call from a pipeline stage).

    Fairness algorithm (Section 14, "the implementation should remain
    simple" - reserve exactly ONE slot, not one per tier, for the single
    oldest eligible candidate across every lower tier (2/3/4) combined,
    then fill every remaining slot by strict tier priority
    (1 -> 2 -> 3 -> 4). This guarantees a Tier 3/4 backlog is never
    permanently starved behind a large Tier 1/2 population, without a
    queue table, a numeric score, or per-tier reserved quotas that would
    need their own justification."""
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)

    if opportunity_kinds_by_site is None:
        opportunity_kinds_by_site = build_opportunity_kinds_by_site(session)

    applications = session.execute(
        select(Application).where(Application.council_code == council_code)
    ).scalars().all()
    if not applications:
        return []

    app_ids = [a.id for a in applications]
    decision_notice_app_ids = frozenset(session.execute(
        select(Document.application_id).where(
            Document.application_id.in_(app_ids), Document.doc_type == "decision_notice",
        ).distinct()
    ).scalars())
    recommendation_by_app_id = dict(session.execute(
        select(SchemeIntelligence.application_id, SchemeIntelligence.recommendation_direction).where(
            SchemeIntelligence.application_id.in_(app_ids),
        )
    ).all())

    # Naive-UTC comparison throughout (both sides stripped of tzinfo) -
    # the same established convention app.pipeline.run_weekly.
    # stage_fetch_related_applications/stage_check_build_status already
    # use for comparing a stored DateTime(timezone=True) value against a
    # freshly-computed cutoff, avoiding an aware-vs-naive TypeError
    # regardless of what the DB driver hands back.
    now_naive = now.replace(tzinfo=None)

    by_tier: dict[int, list[VerificationCandidate]] = {t: [] for t in TIER_CADENCE_DAYS}
    for application in applications:
        tier = classify_verification_tier(
            application,
            has_decision_notice=application.id in decision_notice_app_ids,
            recommendation_direction=recommendation_by_app_id.get(application.id),
            opportunity_kinds_for_site=opportunity_kinds_by_site.get(application.site_id, frozenset()),
        )
        if tier is None:
            continue
        cutoff = now_naive - dt.timedelta(days=TIER_CADENCE_DAYS[tier])
        verified_at = application.status_verified_at
        if verified_at is not None and verified_at.replace(tzinfo=None) > cutoff:
            continue  # verified recently enough for this tier's cadence - not eligible this run
        by_tier[tier].append(VerificationCandidate(application=application, tier=tier))

    for tier in by_tier:
        by_tier[tier].sort(key=_tier_sort_key)

    selected: list[VerificationCandidate] = []
    selected_ids: set[int] = set()

    # Starvation protection: one reserved slot for the single oldest
    # eligible candidate across every lower tier (2, 3, 4) combined.
    lower_tier_pool = [c for t in (TIER_LONG_PENDING_OPPORTUNITY, TIER_OTHER_OPPORTUNITY_PENDING, TIER_OTHER_PENDING) for c in by_tier[t]]
    if lower_tier_pool and limit > 0:
        reserved = min(lower_tier_pool, key=_tier_sort_key)
        selected.append(reserved)
        selected_ids.add(reserved.application.id)

    for tier in (TIER_CONTRADICTION_SIGNAL, TIER_LONG_PENDING_OPPORTUNITY, TIER_OTHER_OPPORTUNITY_PENDING, TIER_OTHER_PENDING):
        for candidate in by_tier[tier]:
            if len(selected) >= limit:
                break
            if candidate.application.id in selected_ids:
                continue
            selected.append(candidate)
            selected_ids.add(candidate.application.id)
        if len(selected) >= limit:
            break

    return selected[:limit]


def build_opportunity_kinds_by_site(session: Session) -> dict[int, frozenset[str]]:
    """One Opportunity Universe build, reused for every candidate in this
    council's run - never rebuilt per-application. Pure-DB, no AI, no
    network (see app.reporting.opportunity_universe's own docstring) -
    the same mechanism app.pipeline.run_weekly's own opportunity-adjacent
    stages and the weekly sync already call. Returns only the finer
    planning-delivery kind per site (e.g. "long_pending_application",
    "recent_permission", "site", "phase") - never strategic_land, which
    this module has no reason to touch (an ungranted, application-less
    allocation is never a status-verification candidate at all)."""
    from app.reporting.opportunity_feed import STRATEGIC_LAND
    from app.reporting.opportunity_universe import build_current_opportunity_universe

    universe = build_current_opportunity_universe(session)
    kinds_by_site: dict[int, set[str]] = {}
    for record in universe:
        if record.opportunity_type == STRATEGIC_LAND:
            continue
        parts = record.opportunity_id.split(":")
        if len(parts) < 3 or not parts[2].isdigit():
            continue
        site_id = int(parts[2])
        kinds_by_site.setdefault(site_id, set()).add(parts[1])
    return {site_id: frozenset(kinds) for site_id, kinds in kinds_by_site.items()}


@dataclass
class VerificationOutcome:
    outcome: str
    application_reference: str
    material_change_reasons: tuple[str, ...] = ()


@dataclass
class VerificationRunStats:
    """Per-run observability (Section 32) - printed once per council,
    mirroring app.pipeline.evidence_refresh's own single end-of-run
    summary-line convention, never logged per application."""
    eligible: int = 0
    selected: int = 0
    outcome_counts: dict[str, int] = field(default_factory=dict)
    tier_counts: dict[int, int] = field(default_factory=dict)
    material_changes: int = 0

    def record(self, tier: int, outcome: VerificationOutcome) -> None:
        self.selected += 1
        self.outcome_counts[outcome.outcome] = self.outcome_counts.get(outcome.outcome, 0) + 1
        self.tier_counts[tier] = self.tier_counts.get(tier, 0) + 1
        if outcome.material_change_reasons:
            self.material_changes += 1

    def summary_line(self, council_code: str) -> str:
        outcome_part = " ".join(f"{k}={v}" for k, v in sorted(self.outcome_counts.items()))
        tier_part = " ".join(f"tier{k}={v}" for k, v in sorted(self.tier_counts.items()))
        return (
            f"[status-verification] council={council_code} summary eligible={self.eligible} "
            f"selected={self.selected} material_changes={self.material_changes} {outcome_part} {tier_part}"
        )


def verify_application_status(
    session: Session, page, council: CouncilConfig, application: Application, *,
    material_change_stats: MaterialChangeStats | None = None,
    breaker: CouncilPortalCircuitBreaker | None = None,
) -> VerificationOutcome:
    """Directly re-fetches ONE already-known Application by its exact
    reference (never a date-range search) and, only on a successfully
    parsed result, passes it through the existing, UNMODIFIED
    _upsert_scraped_application (imported locally to avoid a circular
    import with app.pipeline.run_weekly, which itself will import this
    module) - reusing its already-proven update-in-place and material-
    change-detection behaviour verbatim. No new scraper, no parallel
    change-detection logic, no reconciliation of any kind."""
    from app.pipeline.run_weekly import _upsert_scraped_application  # local import: avoids a circular import

    old_state = ApplicationState(
        status=application.status, decision=application.decision, estimated_unit_count=application.estimated_unit_count,
    )

    try:
        if council.doc_system == "arcus":
            from app.scrapers.arcus_portal import fetch_application_by_reference as fetch_by_reference_arcus
            result = fetch_by_reference_arcus(page, council, application.reference)
        else:
            from app.scrapers.idox_portal import HEADERS
            from app.scrapers.idox_portal import fetch_application_by_reference as fetch_by_reference_idox
            requests_session = requests.Session()
            requests_session.headers.update(HEADERS)
            result = fetch_by_reference_idox(page, requests_session, council, application.reference)
    except Exception as e:
        if is_portal_host_failure(e):
            if breaker is not None:
                breaker.record_failure(e, stage="status-verification")
            return VerificationOutcome(outcome=OUTCOME_PORTAL_UNAVAILABLE, application_reference=application.reference)
        if breaker is not None:
            breaker.record_failure(e, stage="status-verification")
        return VerificationOutcome(outcome=OUTCOME_FETCH_FAILED, application_reference=application.reference)

    if breaker is not None:
        breaker.record_success()

    # Same "not found" contract app.pipeline.run_weekly.
    # stage_fetch_missing_parents already relies on for this exact return
    # shape - a genuinely completed lookup that found nothing is not a
    # fetch failure (Section 9: "It should be observable/logged and remain
    # eligible for appropriate retry" - never a status/decision mutation,
    # never a fabricated withdrawn/excluded state).
    if not result or not result.reference:
        return VerificationOutcome(outcome=OUTCOME_APPLICATION_NOT_FOUND, application_reference=application.reference)

    updated = _upsert_scraped_application(
        session, council, result, batch_id=None, material_change_stats=material_change_stats,
    )
    session.commit()

    new_state = ApplicationState(
        status=updated.status, decision=updated.decision, estimated_unit_count=updated.estimated_unit_count,
    )
    change_result = detect_material_application_change(old_state, new_state)

    # Section 8: status_verified_at advances ONLY here - a completed
    # direct retrieval and parse, whether or not anything changed.
    updated.status_verified_at = dt.datetime.now(dt.timezone.utc)
    session.commit()

    return VerificationOutcome(
        outcome=OUTCOME_VERIFIED_CHANGED if change_result.changed else OUTCOME_VERIFIED_UNCHANGED,
        application_reference=updated.reference, material_change_reasons=change_result.reasons,
    )


def run_status_verification(
    session: Session, page, council: CouncilConfig, *,
    breaker: CouncilPortalCircuitBreaker | None = None,
    limit: int = MAX_STATUS_VERIFICATIONS_PER_COUNCIL_PER_RUN,
    opportunity_kinds_by_site: dict[int, frozenset[str]] | None = None,
) -> VerificationRunStats:
    """The one stage entry point (mirrors app.pipeline.run_weekly.
    stage_evidence_refresh's own shape) - called as a NEW, independent
    stage from run_weekly.main(), never folded into stage_scrape or
    stage_fetch_related_applications.

    `opportunity_kinds_by_site`: optional pre-built snapshot (see
    build_opportunity_kinds_by_site below) - run_weekly.main() builds this
    once per council run and passes the SAME snapshot to both this
    function and stage_fetch_related_applications, so the Opportunity
    Universe is never rebuilt twice in one invocation. Computed here when
    omitted (e.g. when this function is called/tested on its own)."""
    stats = VerificationRunStats()
    if opportunity_kinds_by_site is None:
        opportunity_kinds_by_site = build_opportunity_kinds_by_site(session)
    candidates = select_verification_candidates(
        session, council.code, limit=limit, opportunity_kinds_by_site=opportunity_kinds_by_site,
    )
    stats.eligible = len(candidates)

    material_change_stats = MaterialChangeStats()
    for candidate in candidates:
        if breaker is not None and breaker.is_open:
            print(f"  [circuit] council={council.code} skipping_remaining_network_work stage=status-verification")
            break
        outcome = verify_application_status(
            session, page, council, candidate.application,
            material_change_stats=material_change_stats, breaker=breaker,
        )
        stats.record(candidate.tier, outcome)
        print(
            f"  [status-verification] {candidate.application.reference} tier={candidate.tier} "
            f"outcome={outcome.outcome}"
            + (f" reasons={','.join(outcome.material_change_reasons)}" if outcome.material_change_reasons else "")
        )

    print(stats.summary_line(council.code))
    return stats
