"""Acquisition Agent V1, Gate 1 - Persistence Foundation.

Turns the ephemeral app.policy.acquisition_evaluate.evaluate() call into a
persistent one: resolves a durable acquisition-subject identity, computes a
canonical evaluation-input fingerprint, claims exclusive ownership of that
evaluation BEFORE any OpenAI call is made, then persists the outcome as an
append-only history row and an upserted current-state row.

This module NEVER modifies, wraps the commercial logic of, or reinterprets
app.policy.acquisition_evaluate / agent_evaluation_prompt / agent_
evaluation_validator / agent_evaluation_result (Agent Evaluation Policy V1,
CLOSED - PRODUCTION VERIFIED) - it calls evaluate() as a black box and
persists exactly what it returns. See app.db.models' own new-table
docstrings (AcquisitionSubjectAnchor, AgentEvaluationHistory,
CurrentBuyerOpportunityState, AgentEvaluationClaim) for the full schema
rationale this module implements against.

NOT INCLUDED IN GATE 1 (Product Owner brief, explicit deferrals):
  - the Scheduled Acquisition Agent Runner itself (no cron, no weekly loop,
    no full-universe evaluation) - this module only provides the service
    functions a future runner would call, one (buyer_mandate, opportunity)
    combination at a time;
  - Human Decision / Feedback persistence;
  - OpenAI response.usage capture - EvaluationExecutionResult does not
    expose the raw OpenAI response object to its own caller at all (it is
    fully encapsulated inside evaluate()'s own retry loop), so capturing
    token usage would require modifying that closed file - explicitly not
    done here per the brief's own "if it requires changing closed Agent
    Evaluation Policy semantics... report it as a Benchmark prerequisite"
    instruction. See this module's own report for the exact recommendation.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    AcquisitionSubjectAnchor,
    AgentEvaluationClaim,
    AgentEvaluationHistory,
    CurrentBuyerOpportunityState,
    utcnow,
)
from app.policy.acquisition_type_interpretation import ACQUISITION_TYPE_INTERPRETATION_POLICY_VERSION
from app.policy.agent_evaluation_result import FAILED as EXEC_FAILED
from app.policy.agent_evaluation_result import SUCCESS as EXEC_SUCCESS
from app.policy.agent_evaluation_result import EvaluationExecutionResult
from app.policy.buyer_matching import BUYER_MATCHING_POLICY_VERSION, PLANNING_DELIVERY, STRATEGIC_LAND
from app.policy.mandate_interpretation import MANDATE_INTERPRETATION_POLICY_VERSION
from app.policy.terminal_hard_exclusion import TERMINAL_HARD_EXCLUSION_POLICY_VERSION
from app.reporting.opportunity_transaction_signals import TRANSACTION_SIGNAL_POLICY_VERSION

# --- Provenance constants (Gate 1, Section 11/J) ----------------------------
#
# GOVERNING_POLICY_PROMPT_VERSION is deliberately declared HERE, not inside
# app.policy.agent_evaluation_prompt itself - the architecture audit found
# AGENT_EVALUATION_POLICY_VERSION stayed at 1 across three real production
# prompt-text releases (the narrow implementation, the commercial-semantic
# fix, the ownership/role-separation patch), so there is currently no way
# to tell, from persisted provenance alone, which released prompt text
# produced a historical evaluation. This constant tracks EXACTLY that gap
# for evaluations persisted FROM Gate 1 onwards - it starts at 1 because it
# tracks the CURRENT, already-production-verified GOVERNING_POLICY text as
# of Gate 1 (the ownership/role-separation patch, feature SHA a201d85f...),
# not because any earlier revision is being retroactively numbered (there
# is no historical Agent Evaluation dataset to backfill - Gate 1 brief,
# Section 30). Bump this by 1 whenever GOVERNING_POLICY's text changes in a
# future controlled release - a manual, documented operational discipline,
# never inferred automatically (an automatic diff-based version would be a
# fingerprint, not a controlled-release marker - see Section 19's own
# distinction).
GOVERNING_POLICY_PROMPT_VERSION = 1

MODEL_PROVIDER_OPENAI = "openai"

# Namespaces the fingerprint ALGORITHM itself (the shape of the canonical
# payload below), independent of any individual policy-version component
# inside that payload - so a future change to what the fingerprint
# considers material can be told apart from an ordinary policy-version bump
# within the existing shape.
AGENT_EVALUATION_INPUT_FINGERPRINT_VERSION = 1

# --- Acquisition Subject scope keys (Gate 1, Section 3/4) -------------------
WHOLE_SITE = "WHOLE_SITE"
WHOLE_ALLOCATION = "WHOLE_ALLOCATION"

# --- Claim lifecycle (Gate 1, Section 7/8) ----------------------------------
CLAIM_CLAIMED = "claimed"
CLAIM_COMPLETED = "completed"
CLAIM_FAILED = "failed"

# Comfortably longer than any observed Agent Evaluation latency (single
# OpenAI Responses API call, at most one bounded repair retry) and short
# enough that an abandoned claim (a crashed worker) does not block
# re-evaluation of the same fingerprint for an operationally meaningful
# length of time. A future Scheduled Runner gate may make this
# configurable; Gate 1 fixes it as a plain module constant since no
# scheduler exists yet to configure.
CLAIM_EXPIRY_MINUTES = 30


# --- Acquisition Subject identity resolution (Gate 1, Section 3/4) --------

def resolve_acquisition_subject_key(opportunity_id: str, opportunity_type: str) -> tuple[str, int, str]:
    """Pure function: (subject_type, anchor_id, scope_key) from an
    app.reporting.opportunity_universe opportunity_id/opportunity_type
    pair. Implements the Product Owner's own explicit lifecycle rule
    (Gate 1 brief, Section 4): `site`/`recent_permission`/`long_pending_
    application` for the SAME Site.id share one WHOLE_SITE subject (these
    three kinds already represent, by opportunity_universe's own
    documented design, "at most one planning/delivery card at a time" for
    one site moving through its lifecycle); `phase` opportunities are
    scoped by their own phase_code, never merged with WHOLE_SITE or with
    a different phase_code; strategic_land allocations are WHOLE_
    ALLOCATION. Never queries the database - the opportunity_id string
    already carries everything needed (see app.reporting.opportunity_
    universe's own *_opportunity_id() constructors)."""
    parts = opportunity_id.split(":")
    kind = parts[1]
    anchor_id = int(parts[2])

    if opportunity_type == STRATEGIC_LAND:
        return (STRATEGIC_LAND, anchor_id, WHOLE_ALLOCATION)

    if kind == "phase":
        phase_code = parts[3]
        return (PLANNING_DELIVERY, anchor_id, phase_code)

    # "site" | "recent_permission" | "long_pending_application" - see
    # docstring: these three deliberately share one WHOLE_SITE subject.
    return (PLANNING_DELIVERY, anchor_id, WHOLE_SITE)


def get_or_create_subject_anchor(session: Session, *, subject_type: str, anchor_id: int, scope_key: str) -> AcquisitionSubjectAnchor:
    """Idempotent lookup-or-create against the unique (subject_type,
    anchor_id, scope_key) key. A concurrent duplicate insert is caught and
    resolved by re-querying - the row itself, not who created it, is what
    every caller actually needs."""
    existing = session.execute(
        select(AcquisitionSubjectAnchor).where(
            AcquisitionSubjectAnchor.subject_type == subject_type,
            AcquisitionSubjectAnchor.anchor_id == anchor_id,
            AcquisitionSubjectAnchor.scope_key == scope_key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    anchor = AcquisitionSubjectAnchor(subject_type=subject_type, anchor_id=anchor_id, scope_key=scope_key)
    session.add(anchor)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        existing = session.execute(
            select(AcquisitionSubjectAnchor).where(
                AcquisitionSubjectAnchor.subject_type == subject_type,
                AcquisitionSubjectAnchor.anchor_id == anchor_id,
                AcquisitionSubjectAnchor.scope_key == scope_key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        raise
    return anchor


def _opportunity_kind(opportunity_id: str) -> str:
    """The kind segment of an opportunity_id string, verbatim (e.g.
    "site", "phase", "recent_permission", "long_pending_application",
    "allocation") - denormalised onto history/current-state rows for
    cheap filtering without re-parsing the string every read."""
    return opportunity_id.split(":")[1]


# --- Evaluation input fingerprint (Gate 1, Section 16/17/18) ----------------

def _fact_value_pair(fv) -> tuple[str, object | None]:
    """(state, value) - value only when state == KNOWN, never leaking a
    free-text label's exact wording (Section 18's own exclusion) beyond
    the bare fact/value the state actually establishes."""
    return (fv.state, fv.value if fv.state == "KNOWN" else None)


def compute_agent_evaluation_input_fingerprint(
    *, mandate_fingerprint: str, acquisition_type: str, buyer_fit_assessment, packet,
) -> str:
    """AGENT_EVALUATION_INPUT_FINGERPRINT_V1 - a canonical, explicitly-
    named payload, never a hash of the raw OpportunityIntelligencePacket
    and never a reuse of OpportunityMonitoringState.fingerprint (that
    fingerprint's own semantics - "has this opportunity's raw fact set
    changed at all" - are close to but not identical with "would the
    Agent reason differently", and the Gate 1 brief explicitly forbids
    assuming the two match without proof).

    INCLUDED (Section 17 - commercially material): the Buyer Mandate's
    own matching_fingerprint (reused verbatim, never re-derived here -
    Section 20), acquisition_type, the full deterministic Buyer Fit
    assessment (classification/investigative-exception/matches/unknown/
    investigate/non-terminal does_not_match), the packet's own
    commercially material facts (scale, planning/strategic position,
    development state, scope verification, the COMPUTED ownership/
    control posture - never the raw developer-name list itself, which is
    presentation/identity-bearing text, not itself a commercial fact),
    every Transaction Signal's own `.state` (never its free-text
    `.detail`), and only the policy-version components the Product Owner
    has designated as automatically-invalidating market/buyer-fit
    interpretation policies (BUYER_MATCHING_POLICY_VERSION, MANDATE_
    INTERPRETATION_POLICY_VERSION, ACQUISITION_TYPE_INTERPRETATION_
    POLICY_VERSION, TRANSACTION_SIGNAL_POLICY_VERSION, TERMINAL_HARD_
    EXCLUSION_POLICY_VERSION).

    EXCLUDED (Section 18 - controlled-release or presentation-only, never
    part of this hash): AGENT_EVALUATION_POLICY_VERSION, prompt_version,
    model_provider/model_id (Section 19 - these are CONTROLLED RELEASE
    concerns, recorded as separate history columns, never blended into
    the auto-invalidating fingerprint); site/address/council/linked-
    allocation display names; raw coverage timestamps
    (signals.coverage_checked_at); free-text reasoning_summary/next_
    action_detail/signal labels/raw conflict sentences (the COMPUTED
    ownership/control posture already captures the material fact of a
    conflict existing, without being sensitive to how it is worded)."""
    from app.policy.agent_evaluation_prompt import compute_ownership_control_posture

    payload: dict = {
        "fingerprint_version": AGENT_EVALUATION_INPUT_FINGERPRINT_VERSION,
        "buyer_mandate_matching_fingerprint": mandate_fingerprint,
        "acquisition_type": acquisition_type,
        "buyer_fit": {
            "classification": buyer_fit_assessment.classification,
            "is_investigative_exception": buyer_fit_assessment.is_investigative_exception,
            "matches": sorted(buyer_fit_assessment.matches),
            "unknown": sorted(buyer_fit_assessment.unknown),
            "investigate": sorted(buyer_fit_assessment.investigate),
            "does_not_match": sorted(buyer_fit_assessment.does_not_match),
        },
        "opportunity_facts": {
            "total_units": _fact_value_pair(packet.total_units),
            "development_state": _fact_value_pair(packet.development_state),
            "development_state_scope_verified": packet.development_state_scope_verified,
            "ownership_control_posture": compute_ownership_control_posture(packet),
        },
        "policy_versions": {
            "buyer_matching_policy_version": BUYER_MATCHING_POLICY_VERSION,
            "mandate_interpretation_policy_version": MANDATE_INTERPRETATION_POLICY_VERSION,
            "acquisition_type_interpretation_policy_version": ACQUISITION_TYPE_INTERPRETATION_POLICY_VERSION,
            "transaction_signal_policy_version": TRANSACTION_SIGNAL_POLICY_VERSION,
            "terminal_hard_exclusion_policy_version": TERMINAL_HARD_EXCLUSION_POLICY_VERSION,
        },
    }

    if packet.opportunity_type == STRATEGIC_LAND:
        payload["opportunity_facts"]["local_plan_status"] = _fact_value_pair(packet.local_plan_status)
        payload["opportunity_facts"]["allocation_status"] = _fact_value_pair(packet.allocation_status)
        payload["opportunity_facts"]["progression_signal"] = _fact_value_pair(packet.progression_signal)
        payload["opportunity_facts"]["has_identified_planning_activity"] = _fact_value_pair(packet.has_identified_planning_activity)
    else:
        payload["opportunity_facts"]["affordable_units"] = _fact_value_pair(packet.affordable_units)
        payload["opportunity_facts"]["affordable_percentage"] = _fact_value_pair(packet.affordable_percentage)
        payload["opportunity_facts"]["operative_planning_state"] = _fact_value_pair(packet.operative_planning_state)
        payload["opportunity_facts"]["recommendation_direction"] = _fact_value_pair(packet.recommendation_direction)
        payload["opportunity_facts"]["affordable_housing_status"] = _fact_value_pair(packet.affordable_housing_status)

    s = packet.transaction_signals
    payload["transaction_signals"] = {
        "recent_permission_state": s.recent_permission.state,
        "approaching_implementation_deadline_state": s.approaching_implementation_deadline.state,
        "implementation_activity_evidence_identified_state": s.implementation_activity_evidence_identified.state,
        "wider_site_implementation_activity_context_state": s.wider_site_implementation_activity_context.state,
        "no_qualifying_progress_evidence_identified_state": s.no_qualifying_progress_evidence_identified.state,
        "ownership_or_control_evidence_changed_state": s.ownership_or_control_evidence_changed.state,
        "scope_verified": s.scope_verified,
    }

    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _as_aware_utc(value: dt.datetime | None) -> dt.datetime | None:
    """SQLite (this project's test/local-dev engine) does not preserve
    tzinfo across a round-trip even for a DateTime(timezone=True) column -
    a value written as UTC-aware comes back naive. PostgreSQL (production)
    does not have this problem, but the claim-expiry comparison below must
    work correctly under both, since Gate 1's own tests run against
    SQLite. Every datetime this module ever writes is produced by
    app.db.models.utcnow() (always UTC), so a naive readback is safely
    assumed to already be UTC, never re-interpreted as local time."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=dt.timezone.utc)


# --- Pre-LLM claim / concurrency (Gate 1, Section 7/8) ----------------------

@dataclass(frozen=True)
class ClaimOutcome:
    """status is one of:
      "claimed" - the caller now owns this evaluation; proceed to call
        acquisition_evaluate.evaluate().
      "already_in_progress" - another (unexpired) worker owns it; the
        caller must NOT call evaluate().
      "already_completed" - a successful evaluation for this EXACT
        fingerprint already exists; the caller should read
        `existing_history_id` instead of re-evaluating.
      "previously_failed" - the last attempt for this exact fingerprint
        failed and was not force-reclaimed; the caller must NOT call
        evaluate() (retry policy is the future Scheduled Runner's
        responsibility - Gate 1 brief Section 15)."""
    status: str
    claim: AgentEvaluationClaim | None
    existing_history_id: int | None = None


def try_claim_evaluation(
    session: Session, *, buyer_mandate_id: int, subject_anchor_id: int, acquisition_type: str,
    evaluation_input_fingerprint: str, force: bool = False,
) -> ClaimOutcome:
    """The one entry point establishing "only one worker may own this
    evaluation at a time" BEFORE any OpenAI call - see app.db.models.
    AgentEvaluationClaim's own docstring for the full claim-row rationale
    (chosen over pg_advisory_lock specifically because this platform's
    production DATABASE_URL is a Supabase transaction-mode pooler
    connection, under which session-scoped advisory locks are unsafe).

    Each branch below is one short, immediately-committed transaction -
    never held open across the caller's own subsequent OpenAI call."""
    existing = session.execute(
        select(AgentEvaluationClaim).where(
            AgentEvaluationClaim.buyer_mandate_id == buyer_mandate_id,
            AgentEvaluationClaim.subject_anchor_id == subject_anchor_id,
            AgentEvaluationClaim.acquisition_type == acquisition_type,
            AgentEvaluationClaim.evaluation_input_fingerprint == evaluation_input_fingerprint,
        )
    ).scalar_one_or_none()

    if existing is None:
        claim = AgentEvaluationClaim(
            buyer_mandate_id=buyer_mandate_id, subject_anchor_id=subject_anchor_id,
            acquisition_type=acquisition_type, evaluation_input_fingerprint=evaluation_input_fingerprint,
            status=CLAIM_CLAIMED,
        )
        session.add(claim)
        try:
            session.commit()
        except IntegrityError:
            # Lost a genuine race to a concurrent insert of the identical
            # key - never retried blindly; the other worker owns it.
            session.rollback()
            return ClaimOutcome(status="already_in_progress", claim=None)
        return ClaimOutcome(status="claimed", claim=claim)

    if existing.status == CLAIM_COMPLETED:
        return ClaimOutcome(status="already_completed", claim=existing, existing_history_id=existing.history_id)

    if existing.status == CLAIM_FAILED and not force:
        return ClaimOutcome(status="previously_failed", claim=existing, existing_history_id=existing.history_id)

    # status == CLAIM_CLAIMED (in progress), or CLAIM_FAILED with force=True.
    if existing.status == CLAIM_CLAIMED:
        cutoff = utcnow() - timedelta(minutes=CLAIM_EXPIRY_MINUTES)
        claimed_at = _as_aware_utc(existing.claimed_at)
        if claimed_at is not None and claimed_at >= cutoff:
            return ClaimOutcome(status="already_in_progress", claim=existing)
        # Expired - atomically reclaim via a conditional UPDATE, checking
        # rowcount to confirm THIS caller actually won the race rather
        # than assuming session-local state is still true.
        result = session.execute(
            AgentEvaluationClaim.__table__.update()
            .where(
                AgentEvaluationClaim.id == existing.id,
                AgentEvaluationClaim.status == CLAIM_CLAIMED,
                AgentEvaluationClaim.claimed_at < cutoff,
            )
            .values(status=CLAIM_CLAIMED, claimed_at=utcnow(), completed_at=None, history_id=None)
        )
        session.commit()
        if result.rowcount != 1:
            return ClaimOutcome(status="already_in_progress", claim=None)
        session.refresh(existing)
        return ClaimOutcome(status="claimed", claim=existing)

    # CLAIM_FAILED with force=True - reclaim explicitly, same conditional-
    # UPDATE-with-rowcount-check discipline.
    result = session.execute(
        AgentEvaluationClaim.__table__.update()
        .where(AgentEvaluationClaim.id == existing.id, AgentEvaluationClaim.status == CLAIM_FAILED)
        .values(status=CLAIM_CLAIMED, claimed_at=utcnow(), completed_at=None, history_id=None)
    )
    session.commit()
    if result.rowcount != 1:
        return ClaimOutcome(status="already_in_progress", claim=None)
    session.refresh(existing)
    return ClaimOutcome(status="claimed", claim=existing)


# --- Persisting the outcome (Gate 1, Section 9/10/13/14/29) -----------------

def _json_signals(signals) -> str:
    return json.dumps([{"label": s.label, "source_reference": s.source_reference} for s in signals])


def _json_unknowns(unknowns) -> str:
    return json.dumps([
        {
            "fact_or_question": u.fact_or_question, "material": u.material,
            "resolvable": u.resolvable, "blocking": u.blocking, "why_it_matters": u.why_it_matters,
        }
        for u in unknowns
    ])


def record_evaluation_outcome(
    session: Session, *, claim: AgentEvaluationClaim, result: EvaluationExecutionResult,
    buyer_mandate_id: int, subject_anchor_id: int, acquisition_type: str,
    opportunity_id: str, buyer_mandate_fingerprint: str, evaluation_input_fingerprint: str,
    model_id: str,
) -> AgentEvaluationHistory:
    """Inserts the one, never-mutated-again AgentEvaluationHistory row for
    this attempt, updates the claim to its terminal state, and upserts
    CurrentBuyerOpportunityState - all in ONE transaction (Section 29:
    these three writes are DB-only, no network call between them, so
    committing them together is correct and minimises round-trips; the
    OpenAI call itself must already be finished before this function is
    ever invoked - see run_persisted_evaluation below for the exact
    ordering).

    A FAILED result never touches current_history_id/current_evaluation_
    fingerprint on the current-state row - the previous successful
    evaluation (if any) remains operative, exactly per the Product Owner
    brief Section 14. If no successful evaluation has ever existed, the
    current-state row's current_history_id stays NULL - represented
    honestly, never fabricated as VERIFY/MONITOR/NOT_RELEVANT."""
    opportunity_kind = _opportunity_kind(opportunity_id)
    e = result.evaluation

    history = AgentEvaluationHistory(
        buyer_mandate_id=buyer_mandate_id, subject_anchor_id=subject_anchor_id, acquisition_type=acquisition_type,
        opportunity_id=opportunity_id, opportunity_kind=opportunity_kind,
        buyer_mandate_fingerprint=buyer_mandate_fingerprint, evaluation_input_fingerprint=evaluation_input_fingerprint,
        evaluation_policy_version=(e.evaluation_policy_version if e else ""),
        prompt_version=GOVERNING_POLICY_PROMPT_VERSION, model_provider=MODEL_PROVIDER_OPENAI, model_id=model_id,
        execution_status=result.status, failure_reason=result.failure_reason, retry_count=result.retry_count,
        diagnostic_detail=result.diagnostic_detail,
        recommendation=(e.recommendation if e else None),
        confidence=(e.confidence if e else None),
        confidence_basis=(json.dumps(list(e.confidence_basis)) if e else None),
        acquisition_subject_level=(e.acquisition_subject.level if e else None),
        acquisition_subject_reference=(e.acquisition_subject.reference if e else None),
        acquisition_subject_note=(e.acquisition_subject.note if e else None),
        supporting_signals=(_json_signals(e.material_positive_signals) if e else None),
        countervailing_signals=(_json_signals(e.material_negative_signals) if e else None),
        material_unknowns=(_json_unknowns(e.material_unknowns) if e else None),
        reasoning_summary=(e.reasoning_summary if e else None),
        next_action=(e.next_action if e else None),
        next_action_detail=(e.next_action_detail if e else None),
        monitoring_trigger=(e.monitoring_trigger if e else None),
        evidence_references=(json.dumps(list(e.evidence_references)) if e else None),
    )
    session.add(history)
    session.flush()  # obtain history.id

    claim.status = CLAIM_COMPLETED if result.status == EXEC_SUCCESS else CLAIM_FAILED
    claim.completed_at = utcnow()
    claim.history_id = history.id

    current = session.execute(
        select(CurrentBuyerOpportunityState).where(
            CurrentBuyerOpportunityState.buyer_mandate_id == buyer_mandate_id,
            CurrentBuyerOpportunityState.subject_anchor_id == subject_anchor_id,
            CurrentBuyerOpportunityState.acquisition_type == acquisition_type,
        )
    ).scalar_one_or_none()

    if current is None:
        current = CurrentBuyerOpportunityState(
            buyer_mandate_id=buyer_mandate_id, subject_anchor_id=subject_anchor_id, acquisition_type=acquisition_type,
            current_opportunity_id=opportunity_id, current_opportunity_kind=opportunity_kind,
            last_attempt_status="success" if result.status == EXEC_SUCCESS else "failed",
        )
        session.add(current)

    current.current_opportunity_id = opportunity_id
    current.current_opportunity_kind = opportunity_kind
    current.last_evaluated_at = utcnow()
    current.last_attempt_status = "success" if result.status == EXEC_SUCCESS else "failed"
    current.is_current_candidate = True
    if result.status == EXEC_SUCCESS:
        current.current_history_id = history.id
        current.current_evaluation_fingerprint = evaluation_input_fingerprint
    # FAILED: current_history_id / current_evaluation_fingerprint
    # deliberately left untouched - see docstring.

    session.commit()
    return history


@dataclass(frozen=True)
class PersistedEvaluationOutcome:
    """What run_persisted_evaluation actually did - never itself a
    commercial recommendation; read `history`/`current_state` for that."""
    status: str  # "evaluated" | "skipped_in_progress" | "skipped_already_evaluated" | "skipped_previously_failed"
    history: AgentEvaluationHistory | None
    current_state: CurrentBuyerOpportunityState | None


def run_persisted_evaluation(
    session: Session, *, mandate, mandate_key: str, buyer_mandate_id: int, mandate_fingerprint: str,
    acquisition_type: str, opportunity, opportunity_fingerprint: str, packet, buyer_fit_assessment,
    client=None,
) -> PersistedEvaluationOutcome:
    """The one orchestration entry point a future Scheduled Acquisition
    Agent Runner (explicitly NOT built in this gate) would call, one
    (buyer_mandate, opportunity, acquisition_type) combination at a time.

    TRANSACTION BOUNDARIES (Section 29, exact):
      1. resolve_acquisition_subject_key / get_or_create_subject_anchor -
         one short DB transaction (a lookup, or a lookup+insert).
      2. compute_agent_evaluation_input_fingerprint - pure, no DB.
      3. try_claim_evaluation - one short DB transaction, committed before
         step 4. If not "claimed", return immediately - NO OpenAI call.
      4. acquisition_evaluate.evaluate() - the OpenAI network call. NO
         database transaction is held open here at all.
      5. record_evaluation_outcome - one short DB transaction (history
         insert + claim update + current-state upsert together)."""
    from app.policy.acquisition_evaluate import MODEL, evaluate

    subject_type, anchor_id, scope_key = resolve_acquisition_subject_key(opportunity.opportunity_id, opportunity.opportunity_type)
    anchor = get_or_create_subject_anchor(session, subject_type=subject_type, anchor_id=anchor_id, scope_key=scope_key)

    fingerprint = compute_agent_evaluation_input_fingerprint(
        mandate_fingerprint=mandate_fingerprint, acquisition_type=acquisition_type,
        buyer_fit_assessment=buyer_fit_assessment, packet=packet,
    )

    claim_outcome = try_claim_evaluation(
        session, buyer_mandate_id=buyer_mandate_id, subject_anchor_id=anchor.id,
        acquisition_type=acquisition_type, evaluation_input_fingerprint=fingerprint,
    )
    if claim_outcome.status == "already_in_progress":
        return PersistedEvaluationOutcome(status="skipped_in_progress", history=None, current_state=None)
    if claim_outcome.status == "already_completed":
        existing_history = session.get(AgentEvaluationHistory, claim_outcome.existing_history_id) if claim_outcome.existing_history_id else None
        return PersistedEvaluationOutcome(status="skipped_already_evaluated", history=existing_history, current_state=None)
    if claim_outcome.status == "previously_failed":
        return PersistedEvaluationOutcome(status="skipped_previously_failed", history=None, current_state=None)

    result = evaluate(
        session, mandate=mandate, mandate_key=mandate_key, mandate_fingerprint=mandate_fingerprint,
        acquisition_type=acquisition_type, opportunity=opportunity, opportunity_fingerprint=opportunity_fingerprint,
        packet=packet, buyer_fit_assessment=buyer_fit_assessment, client=client,
    )

    history = record_evaluation_outcome(
        session, claim=claim_outcome.claim, result=result,
        buyer_mandate_id=buyer_mandate_id, subject_anchor_id=anchor.id, acquisition_type=acquisition_type,
        opportunity_id=opportunity.opportunity_id, buyer_mandate_fingerprint=mandate_fingerprint,
        evaluation_input_fingerprint=fingerprint, model_id=MODEL,
    )
    current_state = session.execute(
        select(CurrentBuyerOpportunityState).where(
            CurrentBuyerOpportunityState.buyer_mandate_id == buyer_mandate_id,
            CurrentBuyerOpportunityState.subject_anchor_id == anchor.id,
            CurrentBuyerOpportunityState.acquisition_type == acquisition_type,
        )
    ).scalar_one_or_none()
    return PersistedEvaluationOutcome(status="evaluated", history=history, current_state=current_state)
