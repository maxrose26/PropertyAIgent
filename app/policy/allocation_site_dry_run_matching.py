"""GM Allocation <-> Site dry-run candidate matching harness (Stage 2A),
extended with a controlled production write mode (Stage 2B).

Dry-run (everything before the "Stage 2B" section below) remains read-only
reporting only and the default. It never writes anything - no
session.add/flush/commit anywhere in that part, and it never assigns to
matched_site_id, match_confidence, review_status, latitude, longitude, or
any other attribute of a LocalPlanSite/Site/Application ORM object. It exists
to answer "what WOULD the existing allocation matcher decide, at Greater
Manchester baseline scale, if it were run" - not to decide anything itself.

Stage 2B adds run_controlled_write() - the ONLY function in this module
that ever mutates the database, and only when a caller (the CLI script,
behind its own --execute/--confirm gate) invokes it explicitly. A persisted
matched_site_id means "this Site is evidenced as relating to this
allocation" - NEVER "this Site accounts for the whole allocation" or any
capacity/coverage/availability conclusion; see run_controlled_write()'s own
docstring for the exact write semantics per classification tier.

The actual matching DECISION is entirely delegated to the existing, already-
tested app.extraction.local_plan.match_to_existing_site() - this module never
reimplements its scoring or its compass-direction veto. It is called
repeatedly (excluding each prior winner) purely to discover whether MORE
THAN ONE candidate Site independently clears its own threshold - a black-box
technique, not a second matching algorithm.

Geocoding is deliberately never called here (app.extraction.local_plan.
geocode_local_plan_site hits an external Nominatim service) - this harness
only ever reasons about allocations/Sites using whatever coordinates they
already have, never fetching new ones.

Reporting categories (HIGH_CONFIDENCE_CANDIDATE / REVIEW_CANDIDATE /
NO_CANDIDATE / AMBIGUOUS) are built entirely from thresholds that ALREADY
exist elsewhere in this codebase - app.extraction.local_plan.
MATCH_SCORE_THRESHOLD (80.0, the real auto-match bar) and app.pipeline.
site_linking.FUZZY_SCORE_THRESHOLD (70.0, that module's own sibling "worth a
human look, not worth auto-applying" bar for Application<->Site matching) -
no new confidence threshold is invented anywhere in this module.

IMPORTANT MULTI-SITE SAFEGUARD (Stage 2A Section 4): finding one plausible
candidate Site is never treated as proof that the Site represents the WHOLE
allocation - LocalPlanSite.matched_site_id is a single scalar FK (see its own
model-level V1-limitation comment), and this module produces no allocation
capacity/accounting conclusion of any kind. It reports a candidate
RELATIONSHIP only.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import LocalPlanSite, Site
# _contradicting_direction is deliberately imported despite its leading
# underscore: Stage 2B's near-miss reporting is about to become a source of
# WRITTEN (unconfirmed) suggestions, so it must respect the same direction
# veto the real matcher applies - reusing the existing helper is the only
# way to do that without a second, divergent implementation of the veto.
from app.extraction.local_plan import MATCH_SCORE_THRESHOLD, _contradicting_direction, match_to_existing_site
from app.pipeline.site_linking import FUZZY_SCORE_THRESHOLD, normalise_address
from app.ui.common import aggregate_scheme_fields, load_site_applications

# Reporting-only classification labels (Stage 2A Section 2) - never
# persisted anywhere, never written to LocalPlanSite.review_status.
HIGH_CONFIDENCE_CANDIDATE = "HIGH_CONFIDENCE_CANDIDATE"
REVIEW_CANDIDATE = "REVIEW_CANDIDATE"
NO_CANDIDATE = "NO_CANDIDATE"
AMBIGUOUS = "AMBIGUOUS"

# Bounded so a pathological name (matching almost every candidate) can't
# blow up runtime - three independent winners is already well past what
# Section 4 needs to prove "more than one plausible Site exists".
MAX_WINNERS_TO_DISCOVER = 3
NEAR_MISS_CANDIDATES_TO_SHOW = 2

MATCHING_BASIS = (
    "app.extraction.local_plan.match_to_existing_site(): council-scoped "
    "candidates, normalise_address() vs Site.canonical_address, rapidfuzz "
    "token_set_ratio, compass-direction veto, auto-match threshold "
    f"{MATCH_SCORE_THRESHOLD:.0f}"
)


@dataclass
class SiteCandidate:
    site_id: int
    site_name: str
    score: float
    total_units: int | None
    application_count: int


@dataclass
class AllocationMatchResult:
    allocation_id: int
    council: str
    policy_reference: str | None
    allocation_name: str
    allocation_capacity: int | None
    current_review_status: str
    classification: str
    reason: str
    candidates: list[SiteCandidate] = field(default_factory=list)
    near_miss_candidates: list[SiteCandidate] = field(default_factory=list)


def _site_candidate(session: Session, site: Site, score: float) -> SiteCandidate:
    """Informational-only view of one candidate Site, including its own
    already-recorded total unit figure (never summed, never compared
    against the allocation's capacity - see module docstring's multi-site
    safeguard). Reuses app.ui.common's existing pure "first non-null value"
    aggregation rather than a new one."""
    apps = load_site_applications(session, site.id)
    merged = aggregate_scheme_fields(apps) if apps else {}
    return SiteCandidate(
        site_id=site.id, site_name=site.canonical_address, score=score,
        total_units=merged.get("total_units_final"), application_count=len(apps),
    )


def _iterative_matches(site_name: str, candidates: list[Site]) -> list[tuple[Site, float]]:
    """Repeatedly calls the EXISTING match_to_existing_site() (never
    reimplemented), excluding each prior winner, to discover whether more
    than one candidate independently clears its own real threshold. Purely
    a black-box technique for Section 4's ambiguity safeguard - the
    decision of what counts as a match is 100% delegated to the real
    function on every call."""
    winners: list[tuple[Site, float]] = []
    remaining = list(candidates)
    for _ in range(MAX_WINNERS_TO_DISCOVER):
        site, score = match_to_existing_site(site_name, remaining)
        if site is None:
            break
        winners.append((site, score))
        remaining = [s for s in remaining if s.id != site.id]
    return winners


def _near_miss_candidates(site_name: str, candidates: list[Site]) -> list[tuple[Site, float]]:
    """Sub-threshold candidates, computed from the exact same primitives
    match_to_existing_site itself uses (normalise_address, rapidfuzz
    token_set_ratio, compass-direction veto) - never a second matching
    decision. As of Stage 2B the top near-miss returned here can become a
    WRITTEN (unconfirmed) REVIEW_CANDIDATE suggestion, so it must honour
    every safeguard the real matcher applies, including the direction veto
    - a directionally-contradicting candidate is never suggested, even as
    an unconfirmed one."""
    normalised = normalise_address(site_name)
    scored = sorted(
        (
            (s, fuzz.token_set_ratio(normalised, s.canonical_address))
            for s in candidates
            if not _contradicting_direction(normalised, s.canonical_address)
        ),
        key=lambda pair: pair[1], reverse=True,
    )
    return scored[:NEAR_MISS_CANDIDATES_TO_SHOW]


def evaluate_allocation(
    session: Session, allocation: LocalPlanSite, candidates: list[Site],
) -> AllocationMatchResult:
    """Classifies ONE currently-unmatched allocation against its council's
    existing Sites, using only the existing matcher (see module docstring).
    Never mutates `allocation` or any Site - read-only throughout."""
    base_kwargs = dict(
        allocation_id=allocation.id, council=allocation.council_code,
        policy_reference=allocation.policy_reference, allocation_name=allocation.site_name,
        allocation_capacity=allocation.minimum_dwellings, current_review_status=allocation.review_status,
    )

    if not candidates:
        return AllocationMatchResult(
            **base_kwargs, classification=NO_CANDIDATE,
            reason="no Sites recorded for this council - nothing to compare against",
        )

    winners = _iterative_matches(allocation.site_name, candidates)

    if len(winners) >= 2:
        winner_candidates = [_site_candidate(session, s, score) for s, score in winners]
        return AllocationMatchResult(
            **base_kwargs, classification=AMBIGUOUS, candidates=winner_candidates,
            reason=(
                f"{len(winners)} candidate Sites independently clear the existing matcher's own "
                f"{MATCH_SCORE_THRESHOLD:.0f} threshold - MULTIPLE_PLAUSIBLE_SITES, not a single winner"
            ),
        )

    if len(winners) == 1:
        site, score = winners[0]
        return AllocationMatchResult(
            **base_kwargs, classification=HIGH_CONFIDENCE_CANDIDATE,
            candidates=[_site_candidate(session, site, score)],
            reason=f"single candidate clears the existing matcher's {MATCH_SCORE_THRESHOLD:.0f} threshold",
        )

    near = _near_miss_candidates(allocation.site_name, candidates)
    if near and near[0][1] >= FUZZY_SCORE_THRESHOLD:
        near_candidates = [_site_candidate(session, s, score) for s, score in near]
        return AllocationMatchResult(
            **base_kwargs, classification=REVIEW_CANDIDATE, near_miss_candidates=near_candidates,
            reason=(
                f"best raw similarity {near[0][1]:.1f} clears site_linking's own review threshold "
                f"({FUZZY_SCORE_THRESHOLD:.0f}) but not local_plan's auto-match threshold "
                f"({MATCH_SCORE_THRESHOLD:.0f})"
            ),
        )

    return AllocationMatchResult(
        **base_kwargs, classification=NO_CANDIDATE,
        near_miss_candidates=[_site_candidate(session, s, score) for s, score in near] if near else [],
        reason="no candidate reaches even the review threshold",
    )


def run_dry_run_matching(session: Session, *, council_codes: list[str] | None = None) -> dict:
    """Orchestrates the whole dry run. READ ONLY - issues only SELECT
    statements, never session.add/flush/commit. Returns a plain dict
    (never persisted) matching the Stage 2A Section 5 baseline report
    shape."""
    total_allocations = session.execute(select(func.count()).select_from(LocalPlanSite)).scalar_one()
    already_matched = session.execute(
        select(func.count()).select_from(LocalPlanSite).where(LocalPlanSite.matched_site_id.is_not(None))
    ).scalar_one()

    unmatched_query = select(LocalPlanSite).where(LocalPlanSite.matched_site_id.is_(None))
    if council_codes:
        unmatched_query = unmatched_query.where(LocalPlanSite.council_code.in_(council_codes))
    unmatched = list(session.execute(unmatched_query).scalars().all())

    site_candidates_by_council: dict[str, list[Site]] = {}
    for council in {a.council_code for a in unmatched}:
        site_candidates_by_council[council] = list(
            session.execute(select(Site).where(Site.council_code == council)).scalars().all()
        )

    results = [
        evaluate_allocation(session, allocation, site_candidates_by_council.get(allocation.council_code, []))
        for allocation in unmatched
    ]

    return {
        "total_allocations": total_allocations,
        "already_matched": already_matched,
        "unmatched_evaluated": len(unmatched),
        "matching_basis": MATCHING_BASIS,
        "results": results,
    }


def summarize_results(dry_run: dict) -> dict:
    """Aggregate counts/distributions over run_dry_run_matching()'s output -
    Stage 2A Section 5's baseline report numbers."""
    results: list[AllocationMatchResult] = dry_run["results"]

    by_classification = {HIGH_CONFIDENCE_CANDIDATE: 0, REVIEW_CANDIDATE: 0, NO_CANDIDATE: 0, AMBIGUOUS: 0}
    by_council: dict[str, dict[str, int]] = {}
    score_buckets = {"90-100": 0, "80-89": 0, "70-79": 0, "below_70": 0}

    for result in results:
        by_classification[result.classification] += 1
        council_counts = by_council.setdefault(
            result.council, {HIGH_CONFIDENCE_CANDIDATE: 0, REVIEW_CANDIDATE: 0, NO_CANDIDATE: 0, AMBIGUOUS: 0}
        )
        council_counts[result.classification] += 1

        all_scores = [c.score for c in result.candidates] + [c.score for c in result.near_miss_candidates]
        for score in all_scores:
            if score >= 90:
                score_buckets["90-100"] += 1
            elif score >= 80:
                score_buckets["80-89"] += 1
            elif score >= 70:
                score_buckets["70-79"] += 1
            else:
                score_buckets["below_70"] += 1

    return {
        "total_allocations": dry_run["total_allocations"],
        "already_matched": dry_run["already_matched"],
        "unmatched_evaluated": dry_run["unmatched_evaluated"],
        "high_confidence_candidates": by_classification[HIGH_CONFIDENCE_CANDIDATE],
        "review_candidates": by_classification[REVIEW_CANDIDATE],
        "ambiguous_candidates": by_classification[AMBIGUOUS],
        "no_candidate": by_classification[NO_CANDIDATE],
        "by_council": by_council,
        "score_distribution": score_buckets,
    }


# ---------------------------------------------------------------------------
# Stage 2B - controlled production write mode.
#
# Dry-run (everything above) remains the default and makes zero mutations.
# This section is the ONLY part of this module that ever writes anything,
# and it is never called implicitly - a caller (the CLI script) must invoke
# run_controlled_write() explicitly, behind its own --execute/--confirm gate.
#
# Semantics (Stage 2B Section 2 - "nothing stronger"): a persisted
# matched_site_id means "this Site is evidenced as relating to this
# allocation" - never "this Site accounts for the whole allocation" and
# never any capacity/coverage/availability conclusion. This module computes
# and writes no such conclusion anywhere.
# ---------------------------------------------------------------------------

REJECTED_REVIEW_STATUS = "rejected"
NEEDS_CONFIRMATION_REVIEW_STATUS = "needs_confirmation"


def run_controlled_write(session: Session, *, council_codes: list[str] | None = None) -> dict:
    """PRODUCTION WRITE MODE. Only called with explicit CLI confirmation.

    HIGH_CONFIDENCE_CANDIDATE: writes matched_site_id + match_confidence
    only. review_status is left completely untouched - this mirrors
    exactly how app.extraction.local_plan's own existing ingest_local_plan.py
    pipeline already auto-applies a match at this same >=80 threshold,
    without any review step. No new status vocabulary is introduced.

    REVIEW_CANDIDATE: writes matched_site_id + match_confidence as an
    UNCONFIRMED SUGGESTION, with review_status set to the existing
    "needs_confirmation" value - the model's own documented meaning for
    exactly this state ("...e.g. after a low-confidence Site match", see
    LocalPlanSite.review_status's own comment). This makes the allocation
    actionable via the EXISTING app.policy.site_match_review.
    confirm_site_match()/reject_site_match() - never calls them itself.

    AMBIGUOUS and NO_CANDIDATE allocations are never written.

    Idempotent and fails closed on drift: recomputes the dry run fresh
    immediately before writing, and re-checks each allocation's live state
    right before touching it - matched_site_id already set (by anything,
    including a previous run of this same function) or review_status
    already "rejected" means SKIP, never overwrite. A rejected match must
    stay rejected forever; an already-matched allocation is never revisited.
    """
    dry_run = run_dry_run_matching(session, council_codes=council_codes)

    written_high_confidence: list[int] = []
    written_review_candidate: list[int] = []
    skipped_drift: list[int] = []

    for result in dry_run["results"]:
        if result.classification not in (HIGH_CONFIDENCE_CANDIDATE, REVIEW_CANDIDATE):
            continue

        allocation = session.get(LocalPlanSite, result.allocation_id)
        if (
            allocation is None
            or allocation.matched_site_id is not None
            or allocation.review_status == REJECTED_REVIEW_STATUS
        ):
            skipped_drift.append(result.allocation_id)
            continue

        if result.classification == HIGH_CONFIDENCE_CANDIDATE:
            winner = result.candidates[0]
            allocation.matched_site_id = winner.site_id
            allocation.match_confidence = winner.score
            written_high_confidence.append(result.allocation_id)
        else:
            winner = result.near_miss_candidates[0]
            allocation.matched_site_id = winner.site_id
            allocation.match_confidence = winner.score
            allocation.review_status = NEEDS_CONFIRMATION_REVIEW_STATUS
            written_review_candidate.append(result.allocation_id)

    session.commit()

    return {
        "written_high_confidence": written_high_confidence,
        "written_review_candidate": written_review_candidate,
        "skipped_drift": skipped_drift,
        "ambiguous_not_written": [r.allocation_id for r in dry_run["results"] if r.classification == AMBIGUOUS],
        "no_candidate_untouched": [r.allocation_id for r in dry_run["results"] if r.classification == NO_CANDIDATE],
    }


def fetch_pending_review_allocations(session: Session, *, council_codes: list[str] | None = None) -> list[LocalPlanSite]:
    """The actionable REVIEW_CANDIDATE queue for a human-review UI - every
    LocalPlanSite currently carrying an unconfirmed Site-match suggestion
    written by run_controlled_write(). Uses the exact same combined filter
    (review_status == "needs_confirmation" AND matched_site_id IS NOT NULL)
    that scripts/apply_pr2_allocation_match_review.py already established
    as this codebase's own convention for "a pending Site-match review",
    which keeps this query from also picking up allocations whose
    review_status is "needs_confirmation" for an unrelated CONTENT reason
    (e.g. an ambiguous plan_status derived by migration) - those never have
    matched_site_id set at all, so this filter naturally excludes them."""
    query = select(LocalPlanSite).where(
        LocalPlanSite.review_status == NEEDS_CONFIRMATION_REVIEW_STATUS,
        LocalPlanSite.matched_site_id.is_not(None),
    )
    if council_codes:
        query = query.where(LocalPlanSite.council_code.in_(council_codes))
    return list(session.execute(query).scalars().all())


def fetch_ambiguous_allocations(session: Session, *, council_codes: list[str] | None = None) -> list[AllocationMatchResult]:
    """Live-computed AMBIGUOUS results for display only - Stage 2B Section 4
    deliberately does not persist candidate alternatives anywhere (no
    many-to-many table yet), so this is the dry-run harness itself acting
    as the "generated review dataset", recomputed on demand rather than
    stored, with zero new permanent data architecture."""
    dry_run = run_dry_run_matching(session, council_codes=council_codes)
    return [r for r in dry_run["results"] if r.classification == AMBIGUOUS]
