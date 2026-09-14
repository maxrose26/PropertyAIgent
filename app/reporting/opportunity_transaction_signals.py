"""Agent Evaluation Foundation - Buyer-Independent Transaction/Disposition
Signal V1 (narrow pre-Agent foundation; Product Owner review of the Agent
Evaluation Policy V1 architecture report and its refinement).

THE THREE-LAYER MODEL this module implements the SECOND layer of:

    TRUSTED FACT
        (app.pipeline.lapse_tracking.compute_lapse_status/classify_build_status,
         app.reporting.scheme_reconciliation.resolve_operative_lapse_anchor,
         app.reporting.opportunity_change's own monitoring reason codes -
         ALL UNCHANGED by this module)
    -->
    BUYER-INDEPENDENT TRANSACTION/DEVELOPMENT SIGNAL   <- THIS MODULE
    -->
    (future, NOT built here) buyer-specific interpretation

Every signal below is a DETERMINISTIC, BUYER-INDEPENDENT, PROVENANCE-BACKED
reading of already-trusted facts. No signal here is itself a recommendation,
a score, or a claim about a market participant's intentions. In particular,
no signal may ever be read as, or renamed to imply:

    AVAILABLE / LIKELY_TO_SELL / WILLING_TO_SELL / SELLER_INTENT /
    TRANSACTION_PROPENSITY_SCORE

GOVERNING SEMANTIC CORRECTIONS (Product Owner review of the V1 architecture
report - both preserved structurally, not just by convention):

1. ABSENCE OF COMMENCEMENT EVIDENCE IS NEVER CONFIRMED INACTIVITY. The
   platform-wide "Unknown Must Remain Unknown" rule (see app.pipeline.
   lapse_tracking.classify_build_status's own docstring: its vocabulary has
   NO positive "not started" state at all) is preserved here without
   exception. NO_IDENTIFIED_DEVELOPMENT_PROGRESS never means "confirmed not
   started" or "dormant" or "land banked" - it means only "within the
   trusted development-progress evidence currently available, PropertyAIgent
   has not identified positive evidence of commencement or delivery," and it
   is PRESENT only when there is a resolved basis to have looked (a
   substantive granted permission whose lapse clock has genuinely started -
   compute_lapse_status's own "safe"/"approaching"/"lapsed" states, which
   are BY DEFINITION "granted, and build_status is not one of underway/
   partially_complete/complete") - never manufactured from a bare absence
   of evidence with no such basis (compute_lapse_status's own
   "not_granted"/"not_determined"/"unknown" states), which instead
   correctly reads UNKNOWN.

2. EVIDENCE CHANGING IS NOT THE SAME CLAIM AS OWNERSHIP CHANGING.
   OWNERSHIP_OR_CONTROL_EVIDENCE_CHANGED means only "the trusted evidence
   used to understand ownership/control has changed since the last
   monitoring pass" - it may reflect newly discovered evidence, amended
   evidence, conflicting evidence, or a genuine control change, and this
   module deliberately does not and cannot distinguish those from each
   other. Interpreting WHICH of those occurred is explicitly future
   Acquisition Agent work, not this module's.

3. EXPLICIT_DISPOSAL_EVIDENCE IS NOT IMPLEMENTED. PropertyAIgent has no
   evidence source today for marketing/instructed-agent/disposal-notice/
   tender/auction evidence. Adding an always-UNKNOWN field for it would
   imply a coverage this platform does not have. It is documented as a
   FUTURE / P1 signal in this module's own docstring only, and is
   deliberately NOT a field on TransactionSignals - see the "FUTURE SIGNALS
   (not implemented)" section at the bottom of this file.

RAW FACTS ARE NEVER HIDDEN (Product Owner review, Section 6): every signal's
own underlying raw fact (lapse status, implementation deadline, build
status, the anchor decision date) is retained verbatim on TransactionSignals
alongside its interpreted signal - this bundle is a read layer over those
facts, never a replacement for them.

UNDEVELOPED_LATER_PHASE remains explicitly OUT OF V1 (Product Owner review,
Section 5): the per-phase development-state facts this would need already
exist, but no code anywhere currently compares sibling phases to establish
"an earlier phase is underway while a later phase is not" without risking
treating an UNKNOWN sibling build_status as "undeveloped" - exactly the
kind of manufactured-from-absence signal Correction 1 forbids. This is
future, separately-scoped work.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select

from app.db.models import Application, OpportunityMonitoringState, Site
from app.pipeline.lapse_tracking import compute_lapse_status
from app.policy.buyer_matching import PLANNING_DELIVERY, STRATEGIC_LAND
from app.reporting.opportunity_change import MATERIALLY_CHANGED, REASON_OWNERSHIP_EVIDENCE_CHANGED
from app.reporting.opportunity_universe import RECENT_PERMISSION_WINDOW_MONTHS, add_calendar_months
from app.reporting.scheme_reconciliation import FACT_RESOLVED, resolve_operative_lapse_anchor

TRANSACTION_SIGNAL_POLICY_VERSION = 1

# --- SignalValue: PRESENT / ABSENT / UNKNOWN / NOT_APPLICABLE ---------------

PRESENT = "PRESENT"
ABSENT = "ABSENT"
UNKNOWN = "UNKNOWN"
NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class SignalValue:
    """One transaction/disposition signal's own state - mirrors app.
    reporting.opportunity_intelligence_packet.FactValue's own KNOWN/UNKNOWN/
    NOT_APPLICABLE discipline, extended to PRESENT/ABSENT (a signal, unlike
    a bare fact, has an inherent positive/negative reading once it IS
    known). `.detail` is a short, human-readable derivation note for
    provenance/audit - it must never itself assert anything the signal's
    own name/state doesn't already mean (e.g. never "likely being sold")."""

    state: str
    detail: str | None = None

    @classmethod
    def present(cls, detail: str | None = None) -> "SignalValue":
        return cls(PRESENT, detail)

    @classmethod
    def absent(cls, detail: str | None = None) -> "SignalValue":
        return cls(ABSENT, detail)

    @classmethod
    def unknown(cls, detail: str | None = None) -> "SignalValue":
        return cls(UNKNOWN, detail)

    @classmethod
    def not_applicable(cls, detail: str | None = None) -> "SignalValue":
        return cls(NOT_APPLICABLE, detail)

    @property
    def is_present(self) -> bool:
        return self.state == PRESENT


# --- The signal bundle -------------------------------------------------------

@dataclass(frozen=True)
class TransactionSignals:
    """One opportunity's buyer-independent transaction/disposition signal
    bundle, plus the raw facts every signal here is derived from (Product
    Owner review, Section 6 - raw facts are never hidden behind the
    signal). Composed fresh, on demand, from already-trusted sources; never
    persisted by this module, never buyer-specific."""

    # --- Interpreted signals (PRESENT/ABSENT/UNKNOWN/NOT_APPLICABLE) ---
    recent_permission: SignalValue
    approaching_implementation_deadline: SignalValue
    development_underway: SignalValue
    partially_complete: SignalValue
    no_identified_development_progress: SignalValue
    ownership_or_control_evidence_changed: SignalValue

    # --- Raw facts, retained verbatim alongside the signals above ---
    raw_lapse_status: str | None  # one of compute_lapse_status's own status vocabulary, or None (STRATEGIC_LAND)
    raw_implementation_deadline: dt.date | None
    raw_build_status: str | None  # classify_build_status's own vocabulary, or None (STRATEGIC_LAND)
    raw_decision_date: dt.date | None  # the substantive operative permission's own decision date, if resolved
    raw_last_change_reasons: tuple[str, ...]  # this opportunity's own latest OpportunityMonitoringState reasons, if any


def _not_applicable_bundle() -> TransactionSignals:
    """STRATEGIC_LAND has no lapse/build-status/decision-date concept at
    all (an allocation is not a decided, anchored planning permission) -
    every development-progress-shaped signal is NOT_APPLICABLE, never
    UNKNOWN (the same KNOWN/UNKNOWN/NOT_APPLICABLE discipline the packet
    itself already applies to affordable_units/affordable_percentage for
    this exact opportunity type). OWNERSHIP_OR_CONTROL_EVIDENCE_CHANGED
    remains meaningful for STRATEGIC_LAND (matched_to_site is itself one of
    opportunity_change.py's own tracked fingerprint fields) and is
    therefore NOT included in this all-NOT_APPLICABLE shortcut - see
    build_transaction_signals below."""
    na = SignalValue.not_applicable("Not applicable to a strategic land allocation - no decided planning permission exists to anchor a lapse/build-status clock.")
    return TransactionSignals(
        recent_permission=na, approaching_implementation_deadline=na, development_underway=na,
        partially_complete=na, no_identified_development_progress=na,
        ownership_or_control_evidence_changed=SignalValue.unknown(),  # overwritten by the caller
        raw_lapse_status=None, raw_implementation_deadline=None, raw_build_status=None,
        raw_decision_date=None, raw_last_change_reasons=(),
    )


def _resolve_ownership_or_control_evidence_changed(session, opportunity_id: str) -> tuple[SignalValue, tuple[str, ...]]:
    """Correction 2 (Product Owner review): this reads ONLY whether the
    TRUSTED EVIDENCE used to understand ownership/control has changed since
    the last monitoring pass - reusing app.reporting.opportunity_change's
    own already-computed, already-named REASON_OWNERSHIP_EVIDENCE_CHANGED
    reason code verbatim (fired for BOTH planning_delivery's own
    ownership_evidence_count field and strategic_land's own matched_to_site
    field - see that module's own _REASON_BY_FIELD mapping). It never
    claims WHICH of newly-discovered/amended/conflicting evidence or a
    genuine control change occurred - that interpretation is explicitly
    future Acquisition Agent work.

    UNKNOWN when this opportunity has never been monitored before (no
    OpportunityMonitoringState row exists yet) - there is nothing to
    compare against, which is a genuine absence of a baseline, never read
    as ABSENT (which would incorrectly claim "checked, no change found")."""
    state = session.execute(
        select(OpportunityMonitoringState).where(OpportunityMonitoringState.opportunity_id == opportunity_id)
    ).scalars().first()
    if state is None:
        return SignalValue.unknown("This opportunity has not yet been through a monitoring pass - no prior evidence snapshot exists to compare against."), ()

    reasons = tuple(r for r in (state.last_change_reasons or "").split(",") if r)
    if state.last_change_classification == MATERIALLY_CHANGED and REASON_OWNERSHIP_EVIDENCE_CHANGED in reasons:
        return SignalValue.present("The trusted ownership/control evidence for this opportunity changed at its last monitoring pass - this does not itself establish what changed or why."), reasons
    return SignalValue.absent("No ownership/control evidence change was detected at this opportunity's last monitoring pass."), reasons


def build_transaction_signals(session, opportunity, *, applications: list[Application] | None = None, site: Site | None = None) -> TransactionSignals:
    """Composes the buyer-independent transaction/disposition signal bundle
    for ONE opportunity, from already-trusted, already-computed sources
    only. `opportunity` exposes opportunity_id/opportunity_type, matching
    app.reporting.opportunity_universe.OpportunityRecord's own shape (the
    same contract app.reporting.opportunity_intelligence_packet.
    build_opportunity_intelligence_packet already relies on).

    `applications`/`site` let a PLANNING_DELIVERY caller that has already
    fetched them (build_opportunity_intelligence_packet does) pass them
    straight through rather than re-querying - mirrors that function's own
    "build once, reuse" contract. A STRATEGIC_LAND caller never needs
    either.

    Read-only throughout - never creates, updates or deletes anything."""
    ownership_signal, last_change_reasons = _resolve_ownership_or_control_evidence_changed(session, opportunity.opportunity_id)

    if opportunity.opportunity_type == STRATEGIC_LAND:
        bundle = _not_applicable_bundle()
        return TransactionSignals(
            recent_permission=bundle.recent_permission,
            approaching_implementation_deadline=bundle.approaching_implementation_deadline,
            development_underway=bundle.development_underway,
            partially_complete=bundle.partially_complete,
            no_identified_development_progress=bundle.no_identified_development_progress,
            ownership_or_control_evidence_changed=ownership_signal,
            raw_lapse_status=None, raw_implementation_deadline=None, raw_build_status=None,
            raw_decision_date=None, raw_last_change_reasons=last_change_reasons,
        )

    # PLANNING_DELIVERY from here on.
    if applications is None or site is None:
        raise ValueError("build_transaction_signals requires applications and site for a PLANNING_DELIVERY opportunity")

    lapse_result = compute_lapse_status(applications, site)
    lapse_status = lapse_result["status"]
    deadline = lapse_result["deadline"]
    build_status = lapse_result["build_status"]

    anchor = resolve_operative_lapse_anchor(applications)
    decision_date = anchor.decision_date if anchor.state == FACT_RESOLVED else None

    # --- RECENT_PERMISSION -------------------------------------------------
    # Reuses the SAME 3-calendar-month window and calendar-month arithmetic
    # app.reporting.opportunity_universe's own recent_permission detector
    # uses (RECENT_PERMISSION_WINDOW_MONTHS/add_calendar_months) - never a
    # second, independently-tuned recency definition. Requires a genuinely
    # resolved decision date (lapse_status in underway/safe/approaching/
    # lapsed all require one); "not_granted"/"not_determined" are read as
    # ABSENT/UNKNOWN respectively per those states' own documented meaning
    # (see compute_lapse_status's own docstring: "not_granted" is a
    # positive, stable fact - nothing has been granted at all; "not_
    # determined" is a genuine uncertainty about the operative permission).
    if lapse_status == "not_granted":
        recent_permission = SignalValue.absent("No application has been granted for this opportunity at all.")
    elif lapse_status == "not_determined":
        recent_permission = SignalValue.unknown("A grant exists but no substantive-role application could be trusted as the operative permission.")
    elif lapse_status == "unknown" or decision_date is None:
        recent_permission = SignalValue.unknown("The operative permission's own decision date could not be resolved.")
    else:
        recency_boundary = add_calendar_months(decision_date, RECENT_PERMISSION_WINDOW_MONTHS)
        if dt.date.today() <= recency_boundary:
            recent_permission = SignalValue.present(f"The operative permission was decided on {decision_date.isoformat()}, within the platform's {RECENT_PERMISSION_WINDOW_MONTHS}-calendar-month recency window.")
        else:
            recent_permission = SignalValue.absent(f"The operative permission was decided on {decision_date.isoformat()}, outside the platform's {RECENT_PERMISSION_WINDOW_MONTHS}-calendar-month recency window.")

    # --- APPROACHING_IMPLEMENTATION_DEADLINE --------------------------------
    if lapse_status == "approaching":
        approaching_implementation_deadline = SignalValue.present(f"The statutory commencement deadline ({deadline.isoformat() if deadline else 'unknown'}) is within the platform's lapse-warning window.")
    elif lapse_status in ("underway", "safe", "lapsed"):
        approaching_implementation_deadline = SignalValue.absent("The deadline is not currently within the platform's lapse-warning window (already underway, comfortably distant, or already passed).")
    else:  # not_granted / not_determined / unknown
        approaching_implementation_deadline = SignalValue.unknown("No resolved implementation deadline exists to assess.")

    # --- DEVELOPMENT_UNDERWAY ------------------------------------------------
    # Correction 1: this vocabulary has NO confirmed "not started" state
    # (classify_build_status's own docstring) - PRESENT or UNKNOWN only,
    # NEVER ABSENT. A confirmed "complete"/"partially_complete" scheme was
    # necessarily underway at some point, so both also read PRESENT here.
    if build_status in ("underway", "partially_complete", "complete"):
        development_underway = SignalValue.present(f"Development-progress evidence ('{build_status}') has been identified for this opportunity.")
    else:
        development_underway = SignalValue.unknown("No development-progress evidence has been identified - this does not confirm development has not started.")

    # --- PARTIALLY_COMPLETE --------------------------------------------------
    # Only EPC-sourced evidence can distinguish "partially complete" from
    # "complete"; a bare portal "underway" filing does not itself establish
    # a completion fraction, so it reads UNKNOWN here, never ABSENT (which
    # would wrongly claim "checked and ruled out").
    if build_status == "partially_complete":
        partially_complete = SignalValue.present("EPC evidence shows some, but not all, dwellings on this scheme completed.")
    elif build_status == "complete":
        partially_complete = SignalValue.absent("EPC evidence shows this scheme fully completed, not partially.")
    else:  # underway (via portal only) / unknown
        partially_complete = SignalValue.unknown("No EPC-sourced completion evidence is available to establish a completion fraction.")

    # --- NO_IDENTIFIED_DEVELOPMENT_PROGRESS ----------------------------------
    # Product Owner's required conservative replacement for the previously-
    # proposed PROLONGED_POST_PERMISSION_INACTIVITY. PRESENT only when there
    # IS a resolved basis to have looked for progress (a substantive grant
    # whose lapse clock has genuinely started - "safe"/"approaching"/
    # "lapsed" are BY DEFINITION "granted, and build_status is not one of
    # underway/partially_complete/complete", see compute_lapse_status's own
    # source) - never manufactured from a bare absence of any evidence at
    # all (not_granted/not_determined/unknown all read UNKNOWN, since there
    # is no resolved basis to say development progress was even checked
    # against a real permission).
    if lapse_status in ("safe", "approaching", "lapsed"):
        no_identified_development_progress = SignalValue.present(
            "Within the trusted development-progress evidence currently available, PropertyAIgent has not identified "
            "positive evidence of commencement or delivery for this permission. This does not mean the site is "
            "confirmed uncommenced, dormant, land banked, or that its owner is unwilling to build - only that no "
            "positive progress evidence has been identified."
        )
    elif lapse_status == "underway":
        no_identified_development_progress = SignalValue.absent("Development-progress evidence has been identified for this opportunity.")
    else:  # not_granted / not_determined / unknown
        no_identified_development_progress = SignalValue.unknown("There is no resolved operative permission to assess development progress against.")

    return TransactionSignals(
        recent_permission=recent_permission,
        approaching_implementation_deadline=approaching_implementation_deadline,
        development_underway=development_underway,
        partially_complete=partially_complete,
        no_identified_development_progress=no_identified_development_progress,
        ownership_or_control_evidence_changed=ownership_signal,
        raw_lapse_status=lapse_status,
        raw_implementation_deadline=deadline,
        raw_build_status=build_status,
        raw_decision_date=decision_date,
        raw_last_change_reasons=last_change_reasons,
    )


# --- FUTURE SIGNALS (not implemented) ---------------------------------------
#
# UNDEVELOPED_LATER_PHASE - P1. Requires comparing sibling phases' own
# development_state facts (which exist per-phase today) without treating an
# UNKNOWN sibling's own build_status as "undeveloped" - a genuinely separate
# piece of design/implementation work, not a safe extension of this module's
# existing per-opportunity signals.
#
# EXPLICIT_DISPOSAL_EVIDENCE - P1/FUTURE. No evidence source exists today for
# marketing, instructed-agent, disposal-notice, tender, or auction evidence.
# Deliberately NOT a field on TransactionSignals - adding an always-UNKNOWN
# field would imply a coverage this platform does not have. Introduce only
# once a real evidence source is connected.
