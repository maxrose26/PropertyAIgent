"""PROPERTY AIGENT — Historical B3 Intelligence Rebuild Runner.

A one-off, operator-invoked, resumable pathway that regenerates EXISTING
production SchemeIntelligence rows using the current approved B3 refresh
standard (app.extraction.intelligence_refresh). This is NOT a planning-
change event and must never fake B1/B2 trigger state (Application.
evidence_refresh_required/reason/trigger, material_evidence_changed_at) on
a historical row merely to make it eligible - see refresh_intelligence_for_
application's own docstring for why Application.intelligence_evidence_
processed_at means something specific and different (the latest material_
evidence_changed_at incorporated into live intelligence) that this module
must never fabricate.

Reuses refresh_intelligence_for_application(...) UNCHANGED - no parallel
historical AI extraction engine exists. Every B3 safety property (evidence
selection, event/depth logic, the legal-security guards, refusal-reason
highlighting, prospective Site Summary generation, atomic replacement, the
OUTCOME_* taxonomy) is inherited automatically from that one call. This
module differs from normal scheduled B3 processing ONLY in:
  - candidate selection (existing SchemeIntelligence rows not yet rebuilt
    at the current REBUILD_VERSION, instead of the material_evidence_
    changed_at-vs-watermark eligibility query app.pipeline.run_weekly.
    INTELLIGENCE_REFRESH_ELIGIBLE uses);
  - a separate completion marker (SchemeIntelligence.intelligence_rebuild_
    version/intelligence_rebuilt_at) tracking "has this row been rebuilt
    under the current B3 standard", never conflated with the B1/B2/B3
    freshness watermark;
  - bounded batch/resume/dry-run control for a large one-off backfill.

Historical rows overwhelmingly predate B1/B2 (Application.evidence_refresh_
reason is NULL for essentially all of them, confirmed at design time), so
refresh_depth_for_reasons(()) already defaults to DEPTH_BROAD via existing,
untouched logic - no new depth-routing system was needed or built here.

QA checks (detect_tenure_narrative_mismatch, is_complex_site) are a
DETERMINISTIC, bounded, non-blocking layer on top of the reused B3
outcome - never a hard failure, never a second AI judgement call, and
never mutate anything the QA check itself flags. They exist because a live
production sample (Trafford 114786/FUL/24) showed the structured
affordable_tenure_split_final field can occasionally remain stale even
when the refreshed narrative is correct, and a separate sample (Stockport
DC/060928, site 74) showed complex 30-application Sites can produce
confusing aggregate Site Summaries - both known, out-of-scope-for-this-
module limitations that the QA layer surfaces for operator review rather
than silently hiding or attempting to fix.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from openai import OpenAI
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Application, SchemeIntelligence, Site
from app.extraction.intelligence_refresh import (
    refresh_depth_for_reasons,
    refresh_intelligence_for_application,
    select_refresh_evidence_documents,
)
from app.extraction.run_extraction import (
    OUTCOME_AI_ERROR,
    OUTCOME_ERROR,
    OUTCOME_INVALID_OUTPUT,
    OUTCOME_NO_USABLE_TEXT,
    OUTCOME_SUCCESS,
)
from app.pipeline.evidence_refresh import resolve_application_family

# Named, deterministic version identity - not a timestamp (Part 9 of the
# task: "do not hard-code a random timestamp as the version identity"). A
# future B3 standard upgrade bumps this string, making every row eligible
# for rebuild again regardless of B1/B2 activity.
REBUILD_VERSION = "b3_v1"

# Bounded batch size (Part 11) - a deliberately conservative default that
# still lets an operator inspect a meaningful dry-run/live batch without
# the risk of an accidental full-corpus run. MAX_BATCH_LIMIT_WITHOUT_
# OVERRIDE makes going beyond that a deliberate, explicit choice (Part 30).
DEFAULT_BATCH_LIMIT = 25
MAX_BATCH_LIMIT_WITHOUT_OVERRIDE = 50

# Smallest safe rule (Part 21) - not a scoring model. Confirmed via the
# live Stockport sample: site 74 has 30 linked applications and produced a
# genuinely confusing blended Site Summary; ordinary sites in the
# production corpus have far fewer (the vast majority under 5).
COMPLEX_SITE_APPLICATION_THRESHOLD = 15

# QA warning labels (Part 22) - reporting-only, never a RefreshOutcome
# value, never persisted, never gate rebuild-completion marking.
QA_TENURE_NARRATIVE_MISMATCH = "STRUCTURED_TENURE_NARRATIVE_MISMATCH"
QA_SITE_SUMMARY_COMPLEX_SITE = "SITE_SUMMARY_COMPLEX_SITE_REVIEW"

# Reporting-only label (Part 22/23) - "SUCCESS_WITH_WARNING" is never a
# value refresh_intelligence_for_application/RefreshOutcome itself
# produces; it is this module's own derived label for
# outcome == OUTCOME_SUCCESS with one or more non-blocking QA warnings.
OUTCOME_SUCCESS_WITH_WARNING = "success_with_warning"

# Deliberately narrow, bounded keyword list (same style as intelligence_
# refresh.py's own _MIXED_SECURITY_SIGNAL_PATTERNS) - not an NLP model.
_TENURE_KEYWORDS = (
    "social rent", "affordable rent", "shared ownership", "rent to buy",
    "intermediate", "discounted market rent", "shared equity", "affordable home ownership",
)


def detect_tenure_narrative_mismatch(tenure_split: str | None, notes: str | None) -> bool:
    """Deterministic, bounded comparison (Part 20) - flags when affordable_
    housing_notes mentions a tenure category that affordable_tenure_split_
    final does not, which is exactly the shape of the live-validation
    defect found on Trafford 114786/FUL/24 (notes correctly said "16 for
    social rent and 57 for shared ownership"; the structured field stayed
    at the stale "Shared Ownership, Rent to Buy", never mentioning social
    rent at all). Deliberately one-directional (notes-has-more-than-field,
    not the reverse) - a field naming a category the notes don't repeat is
    not itself suspicious (notes are a short narrative, not required to
    restate every structured value). Returns False (no warning) whenever
    either input is missing - nothing to compare."""
    if not tenure_split or not notes:
        return False
    tenure_lower = tenure_split.lower()
    notes_lower = notes.lower()
    tenure_terms = {kw for kw in _TENURE_KEYWORDS if kw in tenure_lower}
    notes_terms = {kw for kw in _TENURE_KEYWORDS if kw in notes_lower}
    return bool(notes_terms - tenure_terms)


def is_complex_site(site: Site | None, *, threshold: int = COMPLEX_SITE_APPLICATION_THRESHOLD) -> bool:
    """Smallest safe complex-site signal (Part 21) - a simple application
    count threshold, not an attempt to detect the underlying cause (e.g.
    the Stockport site-linking peculiarity found live, where an unrelated
    special-school scheme and a residential development share one Site
    row). Reports the risk; does not diagnose or fix it."""
    if site is None:
        return False
    return len(site.applications) >= threshold


# --- Candidate selection ------------------------------------------------------


def _not_yet_rebuilt_clause(rebuild_version: str):
    return (
        SchemeIntelligence.intelligence_rebuild_version.is_(None)
        | (SchemeIntelligence.intelligence_rebuild_version != rebuild_version)
    )


def select_historical_rebuild_candidates(
    session: Session, *,
    rebuild_version: str = REBUILD_VERSION,
    council: str | None = None,
    application_id: int | None = None,
    site_id: int | None = None,
    limit: int = DEFAULT_BATCH_LIMIT,
) -> list[Application]:
    """The historical candidate universe (Part 6): every Application with
    an EXISTING SchemeIntelligence row (the rebuild's whole purpose is to
    regenerate already-extracted intelligence to the new standard, not to
    perform first-ever extraction - that remains stage_extraction's job,
    untouched) whose SchemeIntelligence has not already been rebuilt at
    `rebuild_version`. Evidence sufficiency is NOT pre-filtered here - a
    row with no usable evidence is still a valid candidate that will
    correctly resolve to OUTCOME_NO_USABLE_TEXT (old intelligence
    preserved, no OpenAI call - Part 7) inside refresh_intelligence_for_
    application itself; excluding it here would just duplicate that
    function's own, already-correct check.

    Deterministic ordering (Part 12): Application.last_seen_at DESC (most
    recently confirmed-still-live schemes first - the ones most likely to
    still be commercially relevant), then Application.id ASC as a stable
    tie-break. Not a commercial scoring model."""
    stmt = (
        select(Application)
        .join(SchemeIntelligence, SchemeIntelligence.application_id == Application.id)
        .where(_not_yet_rebuilt_clause(rebuild_version))
    )
    if council:
        stmt = stmt.where(Application.council_code == council)
    if application_id:
        stmt = stmt.where(Application.id == application_id)
    if site_id:
        stmt = stmt.where(Application.site_id == site_id)
    stmt = stmt.order_by(Application.last_seen_at.desc(), Application.id.asc()).limit(limit)
    return list(session.execute(stmt).scalars().all())


def count_remaining_backlog(
    session: Session, *, rebuild_version: str = REBUILD_VERSION, council: str | None = None,
) -> int:
    stmt = (
        select(func.count(func.distinct(Application.id)))
        .select_from(Application)
        .join(SchemeIntelligence, SchemeIntelligence.application_id == Application.id)
        .where(_not_yet_rebuilt_clause(rebuild_version))
    )
    if council:
        stmt = stmt.where(Application.council_code == council)
    return session.execute(stmt).scalar() or 0


@dataclass
class CandidateEvidenceSnapshot:
    """Dry-run reporting only (Part 14) - never used to gate whether a
    candidate is selected (see select_historical_rebuild_candidates's own
    docstring for why)."""
    application_id: int
    reference: str
    council_code: str
    site_id: int | None
    depth: str
    usable_document_count: int
    has_usable_evidence: bool
    expected_llm_calls: int
    prior_rebuild_version: str | None


def build_candidate_evidence_snapshot(session: Session, application: Application) -> CandidateEvidenceSnapshot:
    """Read-only preview of what a live refresh would do for this
    candidate - reuses the exact same family-resolution/depth/evidence-
    selection functions refresh_intelligence_for_application itself calls
    (Part 4: reuse, don't duplicate), just without calling the LLM."""
    family = resolve_application_family(session, application)
    reasons = tuple(part for part in (application.evidence_refresh_reason or "").split(",") if part)
    depth = refresh_depth_for_reasons(reasons)
    documents = select_refresh_evidence_documents(family, depth)
    # 1 refresh call always; +1 Site Summary call only when a Site is
    # linked (matches refresh_intelligence_for_application's own `if site
    # is not None` branch).
    expected_calls = 2 if application.site_id else 1
    return CandidateEvidenceSnapshot(
        application_id=application.id, reference=application.reference, council_code=application.council_code,
        site_id=application.site_id, depth=depth, usable_document_count=len(documents),
        has_usable_evidence=len(documents) > 0, expected_llm_calls=expected_calls,
        prior_rebuild_version=(application.scheme_intelligence.intelligence_rebuild_version if application.scheme_intelligence else None),
    )


# --- Live batch orchestration --------------------------------------------------


@dataclass
class RebuildCandidateResult:
    application_id: int
    reference: str
    council_code: str
    outcome: str  # one of run_extraction's own OUTCOME_* values, reused unchanged
    qa_warnings: list[str] = field(default_factory=list)
    rebuilt: bool = False

    @property
    def display_outcome(self) -> str:
        if self.outcome == OUTCOME_SUCCESS and self.qa_warnings:
            return OUTCOME_SUCCESS_WITH_WARNING
        return self.outcome


@dataclass
class HistoricalRebuildRunSummary:
    dry_run: bool
    rebuild_version: str
    candidates_inspected: int = 0
    selected: int = 0
    attempted: int = 0
    success: int = 0
    success_with_warning: int = 0
    no_usable_text: int = 0
    ai_error: int = 0
    invalid_output: int = 0
    error: int = 0
    skipped_already_rebuilt: int = 0
    tenure_mismatch_warnings: int = 0
    complex_site_warnings: int = 0
    estimated_llm_calls: int = 0
    council_distribution: dict[str, int] = field(default_factory=dict)
    dry_run_snapshots: list[CandidateEvidenceSnapshot] = field(default_factory=list)
    results: list[RebuildCandidateResult] = field(default_factory=list)
    remaining_estimated_backlog: int = 0


def _process_one_candidate(
    session: Session, client: OpenAI, application: Application, *, rebuild_version: str,
) -> RebuildCandidateResult:
    """One candidate, one refresh_intelligence_for_application call - the
    ENTIRE B3 atomic-replacement/evidence-selection/guard/prompt stack
    applies exactly as it does for normal scheduled B3 processing (Part 4).
    On success, the rebuild-completion marker is written as a small,
    separate follow-up commit (Part 23) - refresh_intelligence_for_
    application's own atomic commit already guarantees the structured
    intelligence AND Site Summary succeeded before this point; this
    function never has to (and never does) touch either of those fields
    itself. A crash in the narrow window between the two commits would
    leave a genuinely-refreshed row not yet marked rebuilt - the only
    consequence is that row remains a candidate on the NEXT run (one extra
    possible LLM call on retry, never corrupted or lost data); see this
    module's own docstring / the implementation report for why extending
    refresh_intelligence_for_application itself to close that window was
    deliberately avoided (Part 4: do not reopen approved B3 architecture)."""
    outcome_obj = refresh_intelligence_for_application(session, client, application)
    result = RebuildCandidateResult(
        application_id=application.id, reference=application.reference, council_code=application.council_code,
        outcome=outcome_obj.outcome,
    )
    if outcome_obj.outcome != OUTCOME_SUCCESS:
        # NO_USABLE_TEXT / AI_ERROR / INVALID_OUTPUT / ERROR - old
        # intelligence already guaranteed untouched by refresh_
        # intelligence_for_application's own atomicity. Never marked
        # rebuilt (Part 23); remains eligible on the next run (Part 24).
        return result

    intel = application.scheme_intelligence
    if detect_tenure_narrative_mismatch(intel.affordable_tenure_split_final, intel.affordable_housing_notes):
        result.qa_warnings.append(QA_TENURE_NARRATIVE_MISMATCH)
    if is_complex_site(application.site):
        result.qa_warnings.append(QA_SITE_SUMMARY_COMPLEX_SITE)

    # QA warnings are non-blocking (Part 23's own explicit recommendation)
    # - the refresh output is still safe and still counts as successfully
    # rebuilt; they are surfaced for operator review, never silently
    # dropped and never a reason to withhold the completion marker.
    intel.intelligence_rebuild_version = rebuild_version
    intel.intelligence_rebuilt_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    result.rebuilt = True
    return result


def _tally(summary: HistoricalRebuildRunSummary, result: RebuildCandidateResult) -> None:
    if result.outcome == OUTCOME_SUCCESS:
        if result.qa_warnings:
            summary.success_with_warning += 1
        else:
            summary.success += 1
    elif result.outcome == OUTCOME_NO_USABLE_TEXT:
        summary.no_usable_text += 1
    elif result.outcome == OUTCOME_AI_ERROR:
        summary.ai_error += 1
    elif result.outcome == OUTCOME_INVALID_OUTPUT:
        summary.invalid_output += 1
    elif result.outcome == OUTCOME_ERROR:
        summary.error += 1

    if QA_TENURE_NARRATIVE_MISMATCH in result.qa_warnings:
        summary.tenure_mismatch_warnings += 1
    if QA_SITE_SUMMARY_COMPLEX_SITE in result.qa_warnings:
        summary.complex_site_warnings += 1


def run_historical_rebuild(
    session: Session, client: OpenAI | None, *,
    dry_run: bool = True,
    limit: int = DEFAULT_BATCH_LIMIT,
    allow_large_batch: bool = False,
    council: str | None = None,
    application_id: int | None = None,
    site_id: int | None = None,
    rebuild_version: str = REBUILD_VERSION,
) -> HistoricalRebuildRunSummary:
    """The one entry point both the CLI and tests call. dry_run=True (the
    default) performs the full candidate-selection + evidence-preview pass
    with ZERO database writes and ZERO OpenAI calls (Part 14) - this is
    mandatory before any first production batch. dry_run=False requires a
    real `client` and processes candidates SEQUENTIALLY (Part 15: "prefer
    sequential processing for the first production implementation... do
    not introduce concurrency unless clearly safe and necessary" - it
    wasn't judged necessary here), with per-candidate failure isolation -
    one candidate's AI_ERROR/INVALID_OUTPUT/ERROR never rolls back or
    blocks any other candidate in the same batch (Part 33)."""
    if limit > MAX_BATCH_LIMIT_WITHOUT_OVERRIDE and not allow_large_batch:
        raise ValueError(
            f"--limit {limit} exceeds the safe default of {MAX_BATCH_LIMIT_WITHOUT_OVERRIDE}; "
            "pass allow_large_batch=True (--allow-large-batch on the CLI) to proceed deliberately."
        )
    if not dry_run and client is None:
        raise ValueError("client is required for a live (non-dry-run) batch")

    candidates = select_historical_rebuild_candidates(
        session, rebuild_version=rebuild_version, council=council,
        application_id=application_id, site_id=site_id, limit=limit,
    )

    summary = HistoricalRebuildRunSummary(
        dry_run=dry_run, rebuild_version=rebuild_version,
        candidates_inspected=len(candidates), selected=len(candidates),
    )

    for application in candidates:
        summary.council_distribution[application.council_code] = (
            summary.council_distribution.get(application.council_code, 0) + 1
        )

        if dry_run:
            snapshot = build_candidate_evidence_snapshot(session, application)
            summary.dry_run_snapshots.append(snapshot)
            summary.estimated_llm_calls += snapshot.expected_llm_calls
            continue

        summary.attempted += 1
        result = _process_one_candidate(session, client, application, rebuild_version=rebuild_version)
        summary.results.append(result)
        _tally(summary, result)

    summary.remaining_estimated_backlog = count_remaining_backlog(session, rebuild_version=rebuild_version, council=council)
    return summary
