"""PR B2: Targeted Evidence Refresh.

B1 (app.pipeline.material_change) detects a material planning-state or
unit-count change on an EXISTING Application and persists a request:
`evidence_refresh_required = True`, with a deterministic reason code in
`evidence_refresh_reason`. B1 never checks the portal itself - it only ever
raises the request.

This module is what actually CONSUMES that request: for one Application, it
works out which document categories the request's reason code(s) plausibly
route to (ROUTING below), re-lists the relevant portal document register
for a narrow, already-linked application family, acquires whatever relevant
evidence is genuinely new, and produces one truthful RefreshOutcome -
distinct from "AI is stale", which remains entirely B3's job. This module
never calls OpenAI, never touches SchemeIntelligence, and never mutates
Application.decision/status from document content - see refresh_material_
evidence's own docstring for the exact boundary.

One generic entry point (refresh_material_evidence) rather than one
implementation per trigger type - B1 (material-change) is the first caller;
future callers (manual "Find latest S106", periodic staleness, system
recovery) are expected to call the exact same function with a different
trigger/reason, not a parallel implementation (PR B2 spec, Part 3). Only the
B1 caller (app.pipeline.run_weekly.stage_evidence_refresh) is wired up in
this PR - the others are explicitly out of scope.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import CouncilConfig
from app.db.models import Application
from app.pipeline.material_change import (
    REASON_DECISION_GRANTED,
    REASON_DECISION_OUTCOME_UNKNOWN,
    REASON_DECISION_REFUSED,
    REASON_DECISION_WITHDRAWN,
    REASON_RECOMMENDATION_MADE,
    REASON_RECOMMENDED_FOR_APPROVAL,
    REASON_RECOMMENDED_FOR_REFUSAL,
    REASON_UNIT_COUNT_CHANGED,
)
from app.pipeline.portal_circuit_breaker import CouncilPortalCircuitBreaker
from app.pipeline.site_linking import extract_parent_reference

# --- Outcome taxonomy (PR B2 spec, Part 11) -----------------------------------
# Deliberately the smallest operational set that distinguishes "the flag can
# safely be cleared" from "it cannot" (see the flag-clearing rule in
# refresh_material_evidence's own docstring) - not DOWNLOAD_FAILED/
# EXTRACTION_FAILED as separate values, since nothing in this PR needs to
# tell those apart from ACQUISITION_INCOMPLETE to make that decision
# correctly; per-document diagnostics already exist in the [documents] log
# lines discover_and_store_documents_for_application itself prints.
OUTCOME_NEW_MATERIAL_EVIDENCE = "new_material_evidence"
OUTCOME_CHECKED_NO_NEW_EVIDENCE = "checked_no_new_evidence"
OUTCOME_PORTAL_UNAVAILABLE = "portal_unavailable"
OUTCOME_ACQUISITION_INCOMPLETE = "acquisition_incomplete"

# Priority when a family has more than one Application (Part 7) and their
# per-application results differ - the most conservative result always wins
# for the OVERALL outcome, matching Part 12's "never lose a refresh
# requirement just because a refresh attempt failed": a family where 3 of 4
# applications checked cleanly but the 4th hit a portal failure must still
# report PORTAL_UNAVAILABLE overall, not silently clear the request based on
# the majority result.
_OUTCOME_PRIORITY = (
    OUTCOME_PORTAL_UNAVAILABLE,
    OUTCOME_ACQUISITION_INCOMPLETE,
    OUTCOME_NEW_MATERIAL_EVIDENCE,
    OUTCOME_CHECKED_NO_NEW_EVIDENCE,
)

# Outcomes that clear evidence_refresh_required (Part 12) - a genuinely
# completed check, whether or not it found anything new. The other two
# outcomes leave the request exactly as B1 raised it, so the very next
# Daily Discovery run's own bounded selection retries it.
CLEARING_OUTCOMES = frozenset({OUTCOME_NEW_MATERIAL_EVIDENCE, OUTCOME_CHECKED_NO_NEW_EVIDENCE})


# --- B1 reason -> target evidence category routing (PR B2 spec, Part 4) ------
# One canonical map, not scattered category lists - every caller (today just
# stage_evidence_refresh) goes through target_doc_types_for_reasons() below.
#
# Committee/officer evidence taxonomy audit (Part 5): inspected app.
# extraction.pdf_text.DOCUMENT_TYPE_PATTERNS - "officer_report" already
# matches r"officer{SEP}report", r"delegated{SEP}report" AND
# r"committee{SEP}report" (i.e. a document literally named "Committee
# Report" or "Delegated Report" already classifies as officer_report
# today), so it is reused as-is for every recommendation/committee-evidence
# target below rather than inventing a new category. KNOWN LIMITATION
# (recorded, not fixed in this PR): a document named only "Committee
# Minutes" or "Committee Agenda" - no "report" - does not match any pattern
# and falls into "other", so is silently excluded from a targeted refresh
# the same way it already is from PR A's own document acquisition. Closing
# that gap is B4/B5 taxonomy work, not required for B2's own targeted-
# refresh correctness (an officer/committee REPORT, when one exists, is
# still found).
ROUTING: dict[str, frozenset[str]] = {
    # Directionless recommendation - seek the officer/committee evidence
    # that will let a human (or later B3) read the actual recommended
    # direction; B2 itself never guesses it from the bare status text (PR
    # B2 spec, Part 25).
    REASON_RECOMMENDATION_MADE: frozenset({"officer_report"}),
    REASON_RECOMMENDED_FOR_APPROVAL: frozenset({"officer_report"}),
    REASON_RECOMMENDED_FOR_REFUSAL: frozenset({"officer_report"}),
    # Status says "decided"/"decision made" but no formal outcome text
    # exists yet - seek the evidence capable of actually resolving it.
    REASON_DECISION_OUTCOME_UNKNOWN: frozenset({"decision_notice", "officer_report"}),
    # Broadest target (Part 4): a formal grant is exactly when S106/legal
    # evidence commonly appears, sometimes with a delay (Part 6/22) - do
    # NOT redesign S106/DoV/Supplemental classification in this PR, just
    # include the existing canonical "s106" category in the target set.
    REASON_DECISION_GRANTED: frozenset({"decision_notice", "officer_report", "s106"}),
    # Focused, commercial rationale (Part 6/23): a future B3 should extract
    # refusal reasons, not regenerate every scheme field.
    REASON_DECISION_REFUSED: frozenset({"decision_notice", "officer_report"}),
    # Focused (Part 23): withdrawal evidence only - never invent a reason
    # if none is found.
    REASON_DECISION_WITHDRAWN: frozenset({"decision_notice", "officer_report"}),
    # Conservative (Part 4): documents likely to explain a revised scheme,
    # not the full useful-document set.
    REASON_UNIT_COUNT_CHANGED: frozenset({"planning_statement", "design_access"}),
}

# Fallback for any reason code not named above (e.g. a future material_change
# reason this routing map hasn't been extended for yet) - the same
# conservative "decision-resolution" pair used for decision_outcome_unknown,
# rather than either the full useful-document set (too broad - defeats the
# whole point of a *targeted* refresh) or an empty set (would silently do
# nothing for an unrecognised reason).
_DEFAULT_TARGET_DOC_TYPES = frozenset({"decision_notice", "officer_report"})


def target_doc_types_for_reasons(reasons: list[str] | tuple[str, ...]) -> frozenset[str]:
    """B1 persists evidence_refresh_reason as a comma-joined string (one or
    more deterministic reason codes from ONE material-change detection
    pass - see MaterialChangeResult.reasons). This is the one canonical
    place that turns that into a target document-category set: the
    deterministic UNION of each individual reason's own routing (Part 4,
    "Multiple reasons... union target evidence categories deterministically.
    Do not duplicate work.") - e.g. "decision_granted,unit_count_changed"
    targets decision_notice+officer_report+s106+planning_statement+
    design_access in one pass, not two separate refresh attempts."""
    target: set[str] = set()
    for reason in reasons:
        target |= ROUTING.get(reason, _DEFAULT_TARGET_DOC_TYPES)
    return frozenset(target)


def reasons_from_stored_field(evidence_refresh_reason: str | None) -> tuple[str, ...]:
    """Splits Application.evidence_refresh_reason (comma-joined, B1's own
    persisted format - see that field's model comment) back into individual
    reason codes for target_doc_types_for_reasons(). Empty/None -> ()."""
    if not evidence_refresh_reason:
        return ()
    return tuple(part for part in evidence_refresh_reason.split(",") if part)


# --- Application-family scoping (PR B2 spec, Part 7) --------------------------


def resolve_application_family(session: Session, application: Application) -> list[Application]:
    """The narrowest bounded set of Applications a targeted refresh should
    check for ONE trigger, using ONLY already-persisted relationships - NOT
    "every Application on the trigger's Site" (Part 7 explicitly forbids
    that; a real production site was found with 30 Applications sharing one
    site_id, spanning years of unrelated phases/filings - see this PR's own
    read-only production analysis).

    Reuses app.pipeline.site_linking.extract_parent_reference (the exact
    same proposal-text parent-citation parser site-linking itself already
    uses) purely as a LOOKUP against Applications already in the database -
    this discovers no new portal data and calls no network code, it only
    narrows which already-persisted rows are "clearly part of the same
    planning family" (Part 7's own phrase) for the trigger:

    1. the triggering Application itself;
    2. its own parent, if the trigger cites one in its proposal text and
       that parent is already a persisted Application row for the same
       council;
    3. any other persisted Application on the trigger's own site whose
       proposal text explicitly cites the TRIGGER as ITS parent (a
       reserved-matters/variation filing against this exact permission).

    Deterministic order (id ascending) and de-duplicated by id."""
    family: dict[int, Application] = {application.id: application}

    parent_ref = extract_parent_reference(application.proposal or "")
    if parent_ref:
        parent = session.execute(
            select(Application).where(
                Application.council_code == application.council_code,
                Application.reference == parent_ref,
            )
        ).scalar_one_or_none()
        if parent is not None:
            family[parent.id] = parent

    if application.site_id is not None:
        site_siblings = session.execute(
            select(Application).where(
                Application.site_id == application.site_id,
                Application.id != application.id,
            )
        ).scalars().all()
        for sibling in site_siblings:
            sibling_parent_ref = extract_parent_reference(sibling.proposal or "")
            if sibling_parent_ref and sibling_parent_ref == application.reference:
                family[sibling.id] = sibling

    return [family[i] for i in sorted(family)]


# --- Per-run bounds and prioritisation (PR B2 spec, Parts 15/16) -------------

# Conservative default (Part 15: "Do not allow an unexpectedly large refresh
# backlog to hammer councils in one run... The initial number should be
# conservative"). Chosen to match the existing order-of-magnitude scale
# already accepted elsewhere in this pipeline for a per-run bounded backlog
# (app.extraction.run_extraction's own daily extraction limit is the closest
# comparable precedent) - deliberately small because, unlike routine
# document discovery (which only ever processes genuinely NEW applications),
# a busy day of material changes - or the very first run after B1's own
# rollout, when the whole existing backlog could in principle be flagged at
# once - could otherwise queue a much larger one-off spike than a council's
# portal has ever been asked to serve in one Daily Discovery run.
EVIDENCE_REFRESH_RUN_LIMIT = 20


def select_refresh_candidates(session: Session, council_code: str, limit: int = EVIDENCE_REFRESH_RUN_LIMIT) -> list[Application]:
    """Only Applications this SAME council has itself flagged
    (evidence_refresh_required = True) - never a scan of every Application,
    never re-checking granted/legacy-documented schemes that were never
    flagged (Part 15). Most-recent-material-change-first (Part 16:
    evidence_refresh_requested_at DESC), stable id tie-break - deterministic,
    no priority-scoring model."""
    return session.execute(
        select(Application)
        .where(Application.council_code == council_code, Application.evidence_refresh_required.is_(True))
        .order_by(Application.evidence_refresh_requested_at.desc().nullslast(), Application.id.asc())
        .limit(limit)
    ).scalars().all()


# --- Outcome result + the generic refresh entry point -------------------------


@dataclass
class RefreshOutcome:
    outcome: str
    new_document_count: int = 0
    checked_categories: frozenset[str] = field(default_factory=frozenset)
    family_size: int = 1


def _refresh_one_application(
    session: Session, page, requests_session: requests.Session, council: CouncilConfig,
    target: Application, target_doc_types: frozenset[str],
    breaker: CouncilPortalCircuitBreaker | None,
) -> tuple[str, int]:
    """Runs the targeted, filtered rediscovery for ONE Application in the
    family and returns (outcome, new_document_count) - one of the four
    OUTCOME_* values, minus family aggregation (see refresh_material_
    evidence for how per-application results combine).

    PR B2 pre-merge amendment ("Explicit Acquisition Completion Contract")
    - reads discover_and_store_documents_for_application's own explicit
    DocumentAcquisitionResult directly (listing_succeeded/acquisition_
    complete/new_document_count) rather than reverse-engineering completion
    from whether Application.documents_last_checked_at moved. That timestamp
    proxy - the original implementation - is deliberately gone: it was an
    indirect signal for foundational refresh infrastructure, and the
    acquisition function itself already knows the true answer (see that
    function's own docstring for exactly what changed and why). new_
    document_count also comes directly from that same result - it is
    already scoped to target_doc_types (the function only ever persists a
    Document whose classified type is in whatever useful_types it was
    given), so no separate before/after identity-set diff is needed here
    any more either.

    Imported lazily from app.pipeline.run_weekly to avoid a circular import
    (run_weekly itself imports this module's ROUTING/target_doc_types_for_
    reasons for its own stage_evidence_refresh)."""
    from app.pipeline.run_weekly import discover_and_store_documents_for_application

    if breaker is not None and breaker.is_open:
        return OUTCOME_PORTAL_UNAVAILABLE, 0

    if not target.summary_url:
        # Nothing to check for this specific family member - not a portal
        # failure, just no known register to query. Treated as a clean,
        # trivially-complete check contributing zero new documents, so it
        # never blocks the rest of the family's real result.
        return OUTCOME_CHECKED_NO_NEW_EVIDENCE, 0

    acquisition_result = discover_and_store_documents_for_application(
        session, page, requests_session, council, target,
        health=None, breaker=breaker, target_doc_types=target_doc_types,
    )

    if not acquisition_result.listing_succeeded:
        # discover_and_store_documents_for_application's own except block
        # already covers every failure mode (host-down, parsing error, ...)
        # under one broad catch and returns listing_succeeded=False - from
        # here, "the listing could not be reliably obtained" is exactly
        # PORTAL_UNAVAILABLE (Part 10: "portal unavailable -> UNKNOWN/
        # failed check, not 'no change'"), the smallest taxonomy that keeps
        # the request retryable.
        return OUTCOME_PORTAL_UNAVAILABLE, 0

    if not acquisition_result.acquisition_complete:
        # A document that DID succeed before a later one failed this same
        # pass is still counted in new_document_count (Part 5 of the
        # amendment: "DO NOT lose it") - only the OUTCOME here is
        # conservative, not the persisted evidence itself.
        return OUTCOME_ACQUISITION_INCOMPLETE, acquisition_result.new_document_count

    new_count = acquisition_result.new_document_count
    return (OUTCOME_NEW_MATERIAL_EVIDENCE if new_count > 0 else OUTCOME_CHECKED_NO_NEW_EVIDENCE), new_count


def refresh_material_evidence(
    session: Session, page, requests_session: requests.Session, council: CouncilConfig,
    application: Application, *, trigger: str, reason: str | None,
    target_categories: frozenset[str] | None = None,
    breaker: CouncilPortalCircuitBreaker | None = None,
) -> RefreshOutcome:
    """The ONE generic targeted-evidence-refresh entry point (PR B2 spec,
    Part 3) - B1 (material_change trigger) is the first caller
    (app.pipeline.run_weekly.stage_evidence_refresh); future callers
    (manual "Find latest S106", periodic staleness, system recovery) are
    expected to call this exact same function with their own trigger/reason,
    not a parallel implementation. Only the B1 caller is wired up in this PR.

    target_categories (PR B2 pre-merge amendment B, "Trigger-Agnostic S106
    Refresh") - an explicit override for which document categories to
    target, bypassing reason -> ROUTING entirely when given. B1's own
    caller never passes this (None, the default), so decision_granted
    continues to automatically include s106 exactly as before - this
    amendment does NOT broaden B1's own routing. It exists so a FUTURE
    caller (manual "Find latest S106", S106-outstanding monitoring) can
    request `{"s106"}` directly regardless of the Application's current
    decision/status - nothing in this function, resolve_application_
    family(), or discover_and_store_documents_for_application ever
    inspects Application.decision/status to decide whether a requested
    category is permitted; classification is purely by the LISTED
    document's own type (see app.extraction.pdf_text.
    standardise_document_type), never by the target Application's
    planning state. Confirmed by test_awaiting_decision_application_
    with_explicit_s106_target_is_not_gated_by_status and its Granted
    counterpart. No caller for this parameter is wired up in this PR.

    `application` must be the ONE Application whose own evidence_refresh_
    required/reason/trigger/requested_at fields this call is answering for
    (see the flag-clearing rule below) - it is also always included in its
    own resolve_application_family() result, so passing it as both the
    trigger and (implicitly) a family member is correct, not redundant.

    AI-FREE (PR B2 spec, STRICT NON-GOALS): this function never calls
    OpenAI, never invalidates/regenerates SchemeIntelligence or Site
    summaries, and never mutates Application.decision/status from document
    content - a resolved decision_outcome_unknown or recommendation_made
    still leaves those fields exactly as the portal itself last reported
    them (Parts 24/25); only a later, explicitly-scoped PR may change that.

    Flag-clearing rule (Part 12) - applied ONLY to `application` itself,
    never to other family members (each Application's own evidence_refresh_
    required reflects its OWN B1 history, untouched by another family
    member's refresh):
      - NEW_MATERIAL_EVIDENCE or CHECKED_NO_NEW_EVIDENCE (a genuinely
        completed check, whichever way it came out): evidence_refresh_
        required -> False. evidence_refresh_reason/trigger/requested_at are
        deliberately left as B1 wrote them (an audit trail of what
        triggered the request, not a queue-position marker - see those
        fields' own model comments).
      - PORTAL_UNAVAILABLE or ACQUISITION_INCOMPLETE: evidence_refresh_
        required stays True, completely unchanged, retryable by the next
        Daily Discovery run's own bounded selection.
      Either way, evidence_refresh_last_outcome/evidence_refresh_last_
      checked_at are always stamped - a truthful record that a check was
      attempted, independent of whether it was allowed to clear the flag.

    B3 handoff (Part 13): Application.material_evidence_changed_at is
    stamped to now() ONLY on NEW_MATERIAL_EVIDENCE - never fabricated, never
    cleared here (a later B3 owns clearing/updating it once it has actually
    acted on it)."""
    family = resolve_application_family(session, application)
    if target_categories is not None:
        target_doc_types = frozenset(target_categories)
    else:
        reasons = reasons_from_stored_field(reason)
        target_doc_types = target_doc_types_for_reasons(reasons)

    per_application_outcomes: list[str] = []
    total_new_documents = 0
    for member in family:
        member_outcome, member_new_count = _refresh_one_application(
            session, page, requests_session, council, member, target_doc_types, breaker,
        )
        per_application_outcomes.append(member_outcome)
        total_new_documents += member_new_count
        if breaker is not None and breaker.is_open:
            # Circuit just opened partway through this family - stop
            # attempting the remaining members' network calls too (same
            # "stop further network calls where practical" principle
            # stage_documents/discover_and_store_documents_for_application
            # already apply within one application's own document list).
            for _remaining in family[len(per_application_outcomes):]:
                per_application_outcomes.append(OUTCOME_PORTAL_UNAVAILABLE)
            break

    overall_outcome = next(o for o in _OUTCOME_PRIORITY if o in per_application_outcomes)

    now = dt.datetime.now(dt.timezone.utc)
    application.evidence_refresh_last_outcome = overall_outcome
    application.evidence_refresh_last_checked_at = now
    if overall_outcome in CLEARING_OUTCOMES:
        application.evidence_refresh_required = False
    if overall_outcome == OUTCOME_NEW_MATERIAL_EVIDENCE:
        application.material_evidence_changed_at = now

    print(
        f"[evidence-refresh] council={council.code} application={application.reference} "
        f"trigger={trigger} reason={reason or 'none'} "
        f"target_categories={','.join(sorted(target_doc_types))} "
        f"family_size={len(family)} outcome={overall_outcome} new_docs={total_new_documents}"
    )

    session.commit()
    return RefreshOutcome(
        outcome=overall_outcome, new_document_count=total_new_documents,
        checked_categories=target_doc_types, family_size=len(family),
    )
