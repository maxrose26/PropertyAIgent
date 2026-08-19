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
from app.policy.allocation_site_relationships import EVIDENCE_BASIS_LEGACY_BACKFILL
from app.policy.relationship_cleanup_plan import revalidate_before_write
from app.reporting.allocation_development_coverage import build_allocation_development_coverage

CONFIRM_PHRASE = "YES-CLEANUP-ALLOCATION-SITE-RELATIONSHIPS"

# Stage 2E.1 Amendment's original seven approved semantic reject targets,
# reproduced verbatim - unchanged by the Stage 2E.2 Final Matcher
# Amendment (Section 2: "preserve the seven proven reject targets").
# Every write is still independently revalidated live before it happens -
# see revalidate_before_write below - never re-derived from the matcher
# at import time.
#
# (51, 27) - JPA 10 Beal Valley / "Land South Of Bullcote Lane" - added by
# the Stage 2E.2 Final Matcher Amendment ("Multi-Reference Sentence
# Attribution Fix + Corpus Safety Scan"), Sections 9/11/12. Moved here
# FROM TO_NEEDS_CONFIRMATION (below) once the multi-reference attribution
# fix + the resulting relationship_cleanup_plan.py contradiction-awareness
# fix together proved this relationship's only supporting evidence was a
# misattributed "adjoins allocation Policy JPA 10" sentence that actually
# describes the site as ADJACENT to, not part of, JPA 10 (it genuinely
# forms part of the neighbouring JPA 12 Broadbent Moss allocation
# instead, which is correctly unaffected and remains KEEP). Confirmed via
# live production revalidate_before_write(expected_action="reject") ->
# still_matches_plan=True before this pair was added here.
TO_REJECT: tuple[tuple[int, int], ...] = (
    (210, 171), (210, 174), (211, 171), (211, 174), (212, 171), (213, 171), (146, 260),
    (51, 27),
)

TO_NEEDS_CONFIRMATION: tuple[tuple[int, int], ...] = (
    (15, 115), (13, 102), (14, 112), (18, 85), (32, 74), (3, 40),
    (16, 123), (19, 85), (155, 236), (76, 216), (80, 248),
)

WOULD_APPLY = "WOULD_APPLY"
APPLIED = "APPLIED"
ALREADY_APPLIED = "ALREADY_APPLIED"
BLOCKED_HUMAN_CONFIRMATION = "BLOCKED_HUMAN_CONFIRMATION"
# Stage 2E.2 Final Amendment (Section 5) - review_status == "confirmed" on a
# relationship row is, by itself, never proof of a genuine relationship-level
# human decision (see _verify_human_confirmation_provenance's own docstring
# for the full inheritance-chain reasoning). A "confirmed" row whose
# provenance cannot be traced back to a genuine app.policy.site_match_review.
# confirm_site_match decision is protected EXACTLY as strongly as one that
# verifies cleanly - never overwritten either way - but reported honestly
# under this distinct outcome rather than being mislabelled
# BLOCKED_HUMAN_CONFIRMATION when the evidence for that label doesn't exist.
BLOCKED_LEGACY_CONFIRMED_UNVERIFIED = "BLOCKED_LEGACY_CONFIRMED_UNVERIFIED"
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


def _verify_human_confirmation_provenance(
    session: Session, allocation_id: int, rel: AllocationSiteRelationship,
) -> tuple[bool, str]:
    """Stage 2E.2 Final Amendment (Section 3/5) - traces WHY a relationship's
    review_status is "confirmed" rather than trusting the bare string.

    No code path in this codebase ever writes review_status="confirmed"
    directly onto an AllocationSiteRelationship row. The only way it can
    appear is app.policy.allocation_site_relationships.plan_legacy_backfill
    copying LocalPlanSite.review_status verbatim at relationship-creation
    time (legacy_matched_site_id_backfill rows only - every document-
    evidenced row starts "auto_applied" and the multi-allocation collision
    guard only ever downgrades to "needs_confirmation", never up to
    "confirmed"). And the ONLY writer of LocalPlanSite.review_status=
    "confirmed" is app.policy.site_match_review.confirm_site_match, which
    ALWAYS sets confirmed_by/confirmed_at/match_review_note atomically in
    that same call - there is no way for a LocalPlanSite to reach
    review_status="confirmed" with those three fields empty.

    So a "confirmed" relationship is only genuinely traceable to a real
    human decision when: (a) it originated from that legacy backfill path,
    (b) the allocation's matched_site_id still points at this exact site -
    the pointer this relationship was copied from has not since drifted
    away underneath it, and (c) the allocation actually carries
    confirmed_by/confirmed_at. All three checked live, every call - never
    cached, never assumed from the row's own evidence_basis alone.

    Returns (verified, detail). verified=False does NOT reduce write
    protection one bit - see BLOCKED_LEGACY_CONFIRMED_UNVERIFIED, which is
    exactly as protected from being overwritten as BLOCKED_HUMAN_
    CONFIRMATION. The only difference this makes is which outcome label
    (and which explanation) the dry-run report shows - this function never
    invents provenance that doesn't exist, it only reports honestly
    whether provenance that DOES exist can be traced for this row."""
    if rel.evidence_basis != EVIDENCE_BASIS_LEGACY_BACKFILL:
        return False, (
            f"review_status='confirmed' but evidence_basis={rel.evidence_basis!r} is not a legacy "
            "matched_site_id backfill row - no known provenance path establishes this as human-reviewed."
        )
    allocation = session.get(LocalPlanSite, allocation_id)
    if allocation is None:
        return False, "Allocation no longer exists - cannot verify confirmation provenance."
    if allocation.matched_site_id != rel.site_id:
        return False, (
            f"Allocation.matched_site_id={allocation.matched_site_id} no longer matches this relationship's "
            f"site_id={rel.site_id} - the provenance link between the allocation's confirmed match and this "
            "relationship row has drifted."
        )
    if not allocation.confirmed_by or not allocation.confirmed_at:
        return False, "Allocation has review_status='confirmed' but no confirmed_by/confirmed_at provenance recorded."
    return True, (
        f"Human-confirmed via allocation matched_site_id review: confirmed_by={allocation.confirmed_by!r} "
        f"at {allocation.confirmed_at} - {allocation.match_review_note or '(no note)'}"
    )


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

    rel = _get_relationship(session, allocation_id, site_id)
    current_status = revalidation.current_review_status

    if current_status == "confirmed":
        verified, detail = _verify_human_confirmation_provenance(session, allocation_id, rel)
        outcome_name = BLOCKED_HUMAN_CONFIRMATION if verified else BLOCKED_LEGACY_CONFIRMED_UNVERIFIED
        return TargetOutcome(allocation_id, site_id, action, outcome_name, rel.id, current_status, detail)

    if current_status == "rejected" or current_status == target_status:
        return TargetOutcome(
            allocation_id, site_id, action, ALREADY_APPLIED, rel.id, current_status,
            "Already at or beyond the planned target status - idempotent, no write needed.",
        )

    if not revalidation.still_matches_plan:
        return TargetOutcome(
            allocation_id, site_id, action, BLOCK_DRIFT, rel.id, current_status, revalidation.reason,
        )

    if not execute:
        return TargetOutcome(
            allocation_id, site_id, action, WOULD_APPLY, rel.id, current_status,
            f"Revalidated eligible - would set review_status={target_status!r}.",
        )

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


def simulate_proposed_coverage(
    session: Session, allocation_ids: list[int], report: CleanupRunReport,
) -> dict[int, dict]:
    """READ ONLY, despite mutating ORM objects internally - previews what
    app.reporting.allocation_development_coverage.
    build_allocation_development_coverage would report for these
    allocations AFTER the approved cleanup runs.

    Stage 2E.2 Final Amendment (Section 8) - CORE INVARIANT: "the dry-run
    proposed state must equal the state execute mode would actually
    create." This function used to independently re-decide, for every
    approved target, whether it "should" be treated as applied - which
    silently drifted from run_cleanup_relationships' own real
    classification (a BLOCK_DRIFT or BLOCKED_HUMAN_CONFIRMATION target
    was being simulated as applied here even though it would NOT actually
    be written in execute mode). Fixed by removing that independent
    decision entirely: `report` is the ACTUAL CleanupRunReport this same
    dry run already produced (via run_cleanup_relationships), and this
    function applies review_status IN MEMORY ONLY for the exact same
    outcomes - WOULD_APPLY/APPLIED - that proposed_status_distribution
    treats as effective, and no others. There is now exactly one place
    that decides "would this target's status actually change" -
    _classify_and_maybe_write, via `report` - so the coverage preview and
    the status-distribution preview can never diverge again.

    Ends with an unconditional session.rollback(), so nothing computed
    here is ever flushed past this function's own return, whether or not
    the caller is itself in a dry run."""
    for outcome in report.reject_outcomes + report.needs_confirmation_outcomes:
        if outcome.outcome not in (WOULD_APPLY, APPLIED):
            continue
        rel = _get_relationship(session, outcome.allocation_id, outcome.site_id)
        if rel is not None:
            rel.review_status = _ACTION_TO_STATUS[outcome.action]

    allocations = [a for a in (session.get(LocalPlanSite, aid) for aid in allocation_ids) if a is not None]
    proposed = build_allocation_development_coverage(session, allocations)

    session.rollback()
    return proposed
