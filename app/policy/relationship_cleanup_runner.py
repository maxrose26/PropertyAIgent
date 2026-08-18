"""Stage 2E.2 ("Controlled Allocation<->Site Relationship Cleanup Runner") -
the approved, semantically-targeted execution of the Stage 2E.1 Amendment's
final classification (KEEP=17, NEEDS_CONFIRMATION=12, REJECT=7, TOTAL=36)
against AllocationSiteRelationship.review_status.

REUSE, NOT REIMPLEMENTATION (Section 2): every eligibility/safety decision
is made by app.policy.relationship_cleanup_plan.revalidate_before_write -
this module adds no independent matcher re-evaluation of its own. It only
adds the thin business-rule layer that interprets a RevalidationResult into
one of the outcome classifications below and, in execute mode, performs the
one-column review_status write.

SEMANTIC TARGETING ONLY (Section 2/3): TO_REJECT/TO_NEEDS_CONFIRMATION are
(allocation_id, site_id) pairs, exactly as approved in the Stage 2E.1
Amendment report. A relationship's own primary-key id is never used to
target a write - it may appear in outcome records purely for audit-log
traceability (Section 2: "IDs may appear in logs only").

OUTCOME VOCABULARY (Sections 5/7/8):
  - WOULD_APPLY / APPLIED: revalidation confirms the target is still
    eligible for the planned action; APPLIED only in execute mode.
  - ALREADY_APPLIED: the relationship already carries the plan's target
    review_status, OR (Section 7, exact instruction) is already
    "rejected" regardless of which action was planned for it - both are
    idempotent no-ops, never treated as errors.
  - BLOCKED_HUMAN_CONFIRMATION: review_status is "confirmed" - a human
    has acted on this relationship since the approved audit; the plan
    must never overwrite that decision (Section 7).
  - BLOCKED_MISSING: the (allocation_id, site_id) pair no longer
    resolves to any relationship row at all.
  - BLOCK_DRIFT: revalidate_before_write found new/changed evidence that
    no longer supports the planned action (Section 7's drift clause).
  - FAILED: an exception was raised while writing this one target;
    isolated via per-target commit/rollback (Section 9) so it can never
    corrupt any other target's outcome.

TRANSACTION SAFETY (Section 9): each target is committed (execute mode)
or rolled back (its own failure) independently - mirrors the established
per-document commit/rollback pattern in
app.enrichment.control_population.run_control_relationship_population.

NO DERIVED WRITES (Section 10): this module writes review_status only.
Downstream coverage (app.reporting.allocation_development_coverage) and
ownership/control Site cards (app.reporting.ownership_control) both
already filter live on AllocationSiteRelationship.review_status, so they
change automatically as soon as a row's status changes - nothing here
computes or persists a derived value. simulate_proposed_coverage below
previews that same derived change WITHOUT writing anything: it mutates
relationship objects in the current session only long enough to call the
existing coverage builder, then unconditionally rolls the session back
before returning, so a dry-run preview can never leave a stray write
behind even if the caller never continues to execute mode.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AllocationSiteRelationship, LocalPlanSite
from app.policy.relationship_cleanup_plan import revalidate_before_write
from app.reporting.allocation_development_coverage import build_allocation_development_coverage

CONFIRM_PHRASE = "YES-CLEANUP-ALLOCATION-SITE-RELATIONSHIPS"

# Stage 2E.1 Amendment's final approved semantic targets - reproduced here
# verbatim from that report, never re-derived from the matcher at import
# time (every write is still independently revalidated live before it
# happens - see revalidate_before_write below).
TO_REJECT: tuple[tuple[int, int], ...] = (
    (210, 171), (210, 174), (211, 171), (211, 174), (212, 171), (213, 171), (146, 260),
)

TO_NEEDS_CONFIRMATION: tuple[tuple[int, int], ...] = (
    (15, 115), (13, 102), (14, 112), (18, 85), (32, 74), (3, 40),
    (16, 123), (19, 85), (155, 236), (51, 27), (76, 216), (80, 248),
)

WOULD_APPLY = "WOULD_APPLY"
APPLIED = "APPLIED"
ALREADY_APPLIED = "ALREADY_APPLIED"
BLOCKED_HUMAN_CONFIRMATION = "BLOCKED_HUMAN_CONFIRMATION"
BLOCKED_MISSING = "BLOCKED_MISSING"
BLOCK_DRIFT = "BLOCK_DRIFT"
FAILED = "FAILED"

_ACTION_TO_STATUS = {"reject": "rejected", "needs_confirmation": "needs_confirmation"}


@dataclass
class TargetOutcome:
    allocation_id: int
    site_id: int
    action: str  # "reject" | "needs_confirmation"
    outcome: str  # one of the classification constants above
    relationship_id: int | None
    previous_review_status: str | None
    detail: str


@dataclass
class CleanupRunReport:
    execute: bool
    reject_outcomes: list[TargetOutcome] = field(default_factory=list)
    needs_confirmation_outcomes: list[TargetOutcome] = field(default_factory=list)

    @property
    def failures(self) -> list[TargetOutcome]:
        return [o for o in (self.reject_outcomes + self.needs_confirmation_outcomes) if o.outcome == FAILED]


def _get_relationship(session: Session, allocation_id: int, site_id: int) -> AllocationSiteRelationship | None:
    return session.execute(
        select(AllocationSiteRelationship).where(
            AllocationSiteRelationship.allocation_id == allocation_id,
            AllocationSiteRelationship.site_id == site_id,
        )
    ).scalar_one_or_none()


def _classify_and_maybe_write(
    session: Session, allocation_id: int, site_id: int, *, action: str, execute: bool,
) -> TargetOutcome:
    """The one place a target's fate is decided. Always calls
    revalidate_before_write immediately beforehand (Section 3: "every
    target must be revalidated immediately before any execute-mode
    write") - dry-run and execute mode share this exact same
    classification path, so a dry-run report is a faithful preview of
    what execute mode would actually do."""
    target_status = _ACTION_TO_STATUS[action]
    revalidation = revalidate_before_write(session, allocation_id, site_id, expected_action=action)

    if not revalidation.relationship_exists:
        return TargetOutcome(
            allocation_id, site_id, action, BLOCKED_MISSING, None, None, revalidation.reason,
        )

    current_status = revalidation.current_review_status
    rel_id = _get_relationship(session, allocation_id, site_id).id

    if current_status == "confirmed":
        return TargetOutcome(
            allocation_id, site_id, action, BLOCKED_HUMAN_CONFIRMATION, rel_id, current_status,
            "Relationship has been human-confirmed since the approved audit - never overwritten by this runner.",
        )

    if current_status == "rejected" or current_status == target_status:
        return TargetOutcome(
            allocation_id, site_id, action, ALREADY_APPLIED, rel_id, current_status,
            "Already at or beyond the planned target status - idempotent, no write needed.",
        )

    if not revalidation.still_matches_plan:
        return TargetOutcome(
            allocation_id, site_id, action, BLOCK_DRIFT, rel_id, current_status, revalidation.reason,
        )

    if not execute:
        return TargetOutcome(
            allocation_id, site_id, action, WOULD_APPLY, rel_id, current_status,
            f"Revalidated eligible - would set review_status={target_status!r}.",
        )

    rel = _get_relationship(session, allocation_id, site_id)
    rel.review_status = target_status
    session.flush()
    return TargetOutcome(
        allocation_id, site_id, action, APPLIED, rel.id, current_status,
        f"Set review_status={target_status!r}.",
    )


def run_cleanup_relationships(session: Session, *, execute: bool = False) -> CleanupRunReport:
    """The one orchestration entry point. execute=False (default) makes
    ZERO database mutations - _classify_and_maybe_write's own execute
    guard is the only place a write is ever issued. execute=True commits
    per target (Section 9) so a failure on one target can never corrupt
    any other target already committed or yet to be processed."""
    report = CleanupRunReport(execute=execute)

    for allocation_id, site_id in TO_REJECT:
        try:
            outcome = _classify_and_maybe_write(session, allocation_id, site_id, action="reject", execute=execute)
            if execute and outcome.outcome == APPLIED:
                session.commit()
            report.reject_outcomes.append(outcome)
        except Exception as e:
            if execute:
                session.rollback()
            report.reject_outcomes.append(
                TargetOutcome(allocation_id, site_id, "reject", FAILED, None, None, repr(e))
            )

    for allocation_id, site_id in TO_NEEDS_CONFIRMATION:
        try:
            outcome = _classify_and_maybe_write(
                session, allocation_id, site_id, action="needs_confirmation", execute=execute,
            )
            if execute and outcome.outcome == APPLIED:
                session.commit()
            report.needs_confirmation_outcomes.append(outcome)
        except Exception as e:
            if execute:
                session.rollback()
            report.needs_confirmation_outcomes.append(
                TargetOutcome(allocation_id, site_id, "needs_confirmation", FAILED, None, None, repr(e))
            )

    return report


def current_status_distribution(session: Session) -> dict[str, int]:
    """READ ONLY - current AllocationSiteRelationship.review_status
    counts, for dry-run before/after reporting."""
    rows = session.execute(
        select(AllocationSiteRelationship.review_status, func.count(AllocationSiteRelationship.id))
        .group_by(AllocationSiteRelationship.review_status)
    ).all()
    return {status: count for status, count in rows}


def proposed_status_distribution(session: Session, report: CleanupRunReport) -> dict[str, int]:
    """Derives the AFTER distribution purely from the current distribution
    plus this run's own outcomes - never re-queries a hypothetical state,
    never writes anything. Every outcome that will genuinely change a row
    (WOULD_APPLY/APPLIED) moves one row from its previous_review_status
    bucket to the target status bucket; every other outcome
    (ALREADY_APPLIED/BLOCKED_*/BLOCK_DRIFT/FAILED) leaves the distribution
    untouched, since none of those write anything."""
    distribution = dict(current_status_distribution(session))
    for outcome in report.reject_outcomes + report.needs_confirmation_outcomes:
        if outcome.outcome not in (WOULD_APPLY, APPLIED):
            continue
        target_status = _ACTION_TO_STATUS[outcome.action]
        if outcome.previous_review_status is not None:
            distribution[outcome.previous_review_status] = distribution.get(outcome.previous_review_status, 0) - 1
        distribution[target_status] = distribution.get(target_status, 0) + 1
    return distribution


def affected_allocation_ids(report: CleanupRunReport | None = None) -> list[int]:
    """The allocation_ids named by the approved target lists - used to
    scope dry-run coverage reporting. Independent of any particular run's
    outcomes (the same allocations are "affected" whether or not this
    run's targets turned out to still be eligible), so `report` is
    accepted but not required."""
    ids = {allocation_id for allocation_id, _ in TO_REJECT} | {allocation_id for allocation_id, _ in TO_NEEDS_CONFIRMATION}
    return sorted(ids)


def simulate_proposed_coverage(session: Session, allocation_ids: list[int]) -> dict[int, dict]:
    """READ ONLY, despite mutating ORM objects internally - previews what
    app.reporting.allocation_development_coverage.
    build_allocation_development_coverage would report for these
    allocations AFTER the approved cleanup runs, by setting review_status
    on the exact approved targets IN THIS SESSION ONLY, calling the
    existing coverage builder unmodified, then unconditionally
    session.rollback()-ing before returning - so nothing computed here is
    ever flushed past this function's own return, whether or not the
    caller is itself in a dry run. A target already "confirmed" or
    "rejected" is left alone here exactly as run_cleanup_relationships
    would leave it alone for real (Section 7 protections apply to the
    preview too, so a dry-run coverage number is never rosier than what
    execute mode would actually produce)."""
    for allocation_id, site_id in TO_REJECT:
        rel = _get_relationship(session, allocation_id, site_id)
        if rel is not None and rel.review_status not in ("confirmed", "rejected"):
            rel.review_status = "rejected"
    for allocation_id, site_id in TO_NEEDS_CONFIRMATION:
        rel = _get_relationship(session, allocation_id, site_id)
        if rel is not None and rel.review_status not in ("confirmed", "rejected", "needs_confirmation"):
            rel.review_status = "needs_confirmation"

    allocations = [a for a in (session.get(LocalPlanSite, aid) for aid in allocation_ids) if a is not None]
    proposed = build_allocation_development_coverage(session, allocations)

    session.rollback()
    return proposed
