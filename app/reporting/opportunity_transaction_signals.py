"""Agent Evaluation Foundation - Buyer-Independent Transaction/Disposition
Signal V1 (narrow pre-Agent foundation; Product Owner review of the Agent
Evaluation Policy V1 architecture report, its refinement, and the pre-
release development-progress semantic audit).

THE THREE-LAYER MODEL this module implements the SECOND layer of:

    AUTHORITATIVE PLANNING FACT
        (app.pipeline.lapse_tracking.compute_lapse_status/
         classify_build_status/find_progress_signal_filing,
         app.reporting.scheme_reconciliation.resolve_operative_lapse_anchor,
         app.reporting.opportunity_change's own monitoring reason codes -
         ALL UNCHANGED by this module)
    -->
    BUYER-INDEPENDENT IMPLEMENTATION/TRANSACTION SIGNAL   <- THIS MODULE
    -->
    (future, NOT built here) buyer-specific interpretation

Every signal below is a DETERMINISTIC, BUYER-INDEPENDENT, PROVENANCE-BACKED
reading of already-trusted facts. No signal here is itself a recommendation,
a score, or a claim about a market participant's intentions. In particular,
no signal may ever be read as, or renamed to imply:

    AVAILABLE / LIKELY_TO_SELL / WILLING_TO_SELL / SELLER_INTENT /
    TRANSACTION_PROPENSITY_SCORE

===========================================================================
PRE-RELEASE DEVELOPMENT-PROGRESS SEMANTIC AUDIT - governing corrections
===========================================================================

The audit found THREE defects in this module's first version and the
Product Owner approved a narrow fix for all three, without building any new
evidence subsystem. Every fix below reuses data the platform already
computes.

DEFECT 1 - EPC independence. The first version's `development_underway`/
`partially_complete` treated app.pipeline.lapse_tracking.classify_build_
status's own EPC-derived `"partially_complete"`/`"complete"` states as
sufficient, on their own, to assert a positive implementation signal. The
Product Owner does not currently trust EPC data as a PRIMARY development-
progress source (Section 2 of the audit). FIX: the new
`implementation_activity_evidence_identified` signal is derived ONLY from
an authoritative, subsequent, genuinely-related PLANNING application (the
same app.pipeline.lapse_tracking.find_progress_signal_filing/
PROGRESS_SIGNAL_CATEGORIES mechanism already used elsewhere in this
codebase for exactly this purpose - condition-discharge or variation/
amendment filings received after the operative grant), NEVER from EPC
alone. EPC/build-status data remains fully available as `raw_build_status`
- explicitly SECONDARY/CORROBORATING context, never authoritative for this
signal. `partially_complete` is REMOVED as a primary V1 signal (it was, by
construction, 100% EPC-derived with no possible planning corroboration -
"fewer trustworthy signals are preferable to richer but misleading
intelligence", Product Owner's own words).

DEFECT 2 - coverage-blind negative signal. The first version's
`no_identified_development_progress` read PRESENT purely from a resolved
lapse clock (compute_lapse_status's "safe"/"approaching"/"lapsed"), which
establishes PLANNING/IMPLEMENTATION DEADLINE KNOWLEDGE, never DEVELOPMENT-
PROGRESS SEARCH COVERAGE. FIX: the renamed `no_qualifying_progress_
evidence_identified` additionally requires `Application.related_search_
checked_at` to be populated on the resolved operative anchor - the SAME
already-existing, already-continuous (app.pipeline.run_weekly.stage_fetch_
related_applications, 30-day cooldown) coverage field this codebase already
maintains for exactly this purpose. Never inferred from permission age,
lapse deadline, absent EPC, or a mere absence of a positive finding.

DEFECT 3 - scope overstatement. The first version computed every signal
from the WHOLE SITE's application list regardless of whether the
opportunity itself was a whole site or one named phase/recent_permission/
long_pending_application - exactly the risk app.policy.buyer_matching_
b2_context.B2MatchingContext.development_state_scope_verified already
exists to flag for the sibling `development_state` fact, but which this
module's first version never consulted. FIX: `build_transaction_signals`
now takes `scope_verified` (the same already-computed context.development_
state_scope_verified value, threaded through by the caller - zero new
computation) and NEVER presents a confident opportunity-scoped PRESENT
result when scope is unverified; the wider-site finding, when one exists,
is preserved rather than discarded, via the separate `wider_site_
implementation_activity_context` field (Product Owner's own "do not throw
away the fact that the wider site has relevant activity").

IMPLEMENTATION PREPARATION IS NOT PHYSICAL COMMENCEMENT (Product Owner
Section 12 of the semantic-fix approval): a condition-discharge or
variation/amendment filing is authoritative evidence of POST-PERMISSION
PLANNING ACTIVITY POTENTIALLY RELEVANT TO IMPLEMENTATION - it is
deliberately NOT described, here or in any detail text this module
produces, as proof that construction has commenced, that development is
underway, or that physical works have started. `implementation_activity_
evidence_identified`'s own name and every one of its detail strings are
written to preserve this distinction; a richer PREPARATION vs COMMENCEMENT
vs DEVELOPMENT_UNDERWAY vs DELIVERY_PROGRESS taxonomy is explicitly
deferred to the future Planning Development Progress Detection capability
(P1, immediately after Agent Evaluation Policy V1) - not attempted here.

EVIDENCE CHANGING IS NOT THE SAME CLAIM AS OWNERSHIP CHANGING (unchanged
from the first version - see below).

EXPLICIT_DISPOSAL_EVIDENCE IS NOT IMPLEMENTED (unchanged from the first
version - see the "FUTURE SIGNALS" section at the bottom of this file).

UNDEVELOPED_LATER_PHASE remains explicitly OUT OF V1 (unchanged from the
first version).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select

from app.db.models import Application, OpportunityMonitoringState, Site
from app.pipeline.lapse_tracking import compute_lapse_status, find_progress_signal_filing
from app.policy.buyer_matching import PLANNING_DELIVERY, STRATEGIC_LAND
from app.reporting.opportunity_change import MATERIALLY_CHANGED, REASON_OWNERSHIP_EVIDENCE_CHANGED
from app.reporting.opportunity_universe import RECENT_PERMISSION_WINDOW_MONTHS, add_calendar_months
from app.reporting.scheme_reconciliation import FACT_RESOLVED, resolve_operative_lapse_anchor

TRANSACTION_SIGNAL_POLICY_VERSION = 2

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
    own name/state doesn't already mean (e.g. never "construction has
    commenced", never "likely being sold")."""

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
    bundle, plus the raw facts every signal here is derived from (raw
    facts are never hidden behind the signal - Product Owner review,
    Section 6 of the original architecture report). Composed fresh, on
    demand, from already-trusted sources; never persisted by this module,
    never buyer-specific.

    FINAL V1 SIGNAL SET (post semantic-fix approval): recent_permission,
    approaching_implementation_deadline, implementation_activity_evidence_
    identified, no_qualifying_progress_evidence_identified, ownership_or_
    control_evidence_changed. `partially_complete` was REMOVED as a primary
    signal (Defect 1) - its own raw value remains visible via raw_build_
    status."""

    # --- Interpreted signals (PRESENT/ABSENT/UNKNOWN/NOT_APPLICABLE) ---
    recent_permission: SignalValue
    approaching_implementation_deadline: SignalValue
    # Opportunity-scoped: UNKNOWN whenever scope_verified is False, even if
    # wider-site evidence exists (Defect 3 fix) - see wider_site_
    # implementation_activity_context below for the preserved wider-site
    # finding.
    implementation_activity_evidence_identified: SignalValue
    # NOT opportunity-scope-gated on its own - always reflects whatever the
    # whole application family's own planning record shows, explicitly
    # labelled as wider-site-in-scope, never presented as an opportunity-
    # level fact. Present for every PLANNING_DELIVERY opportunity
    # regardless of scope_verified, so a caller never loses the underlying
    # finding merely because it could not be safely attributed to the
    # narrower opportunity scope.
    wider_site_implementation_activity_context: SignalValue
    no_qualifying_progress_evidence_identified: SignalValue
    ownership_or_control_evidence_changed: SignalValue

    # --- Raw facts, retained verbatim alongside the signals above ---
    raw_lapse_status: str | None  # one of compute_lapse_status's own status vocabulary, or None (STRATEGIC_LAND)
    raw_implementation_deadline: dt.date | None
    # Combined portal+EPC build-status string, UNCHANGED from app.pipeline.
    # lapse_tracking.classify_build_status - SECONDARY/CORROBORATING
    # context only (Defect 1 fix): never used by this module to establish
    # implementation_activity_evidence_identified on its own.
    raw_build_status: str | None
    raw_decision_date: dt.date | None  # the substantive operative permission's own decision date, if resolved
    raw_last_change_reasons: tuple[str, ...]  # this opportunity's own latest OpportunityMonitoringState reasons, if any
    # Application.related_search_checked_at on the resolved operative
    # anchor - the coverage/freshness timestamp behind no_qualifying_
    # progress_evidence_identified (Defect 2 fix). None means "related-
    # application discovery has never run for this anchor" - never
    # converted into a hard staleness threshold here (Product Owner
    # Section 7 of the semantic-fix approval: freshness INTERPRETATION is
    # future Agent/Lifecycle-Watch work, not this module's).
    coverage_checked_at: dt.datetime | None
    # Whether the signals above are safe to read as opportunity-scoped
    # facts - the same app.policy.buyer_matching_b2_context.
    # B2MatchingContext.development_state_scope_verified value, threaded
    # through verbatim (Defect 3 fix).
    scope_verified: bool


def _not_applicable_bundle(scope_verified: bool) -> TransactionSignals:
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
        recent_permission=na, approaching_implementation_deadline=na,
        implementation_activity_evidence_identified=na, wider_site_implementation_activity_context=na,
        no_qualifying_progress_evidence_identified=na,
        ownership_or_control_evidence_changed=SignalValue.unknown(),  # overwritten by the caller
        raw_lapse_status=None, raw_implementation_deadline=None, raw_build_status=None,
        raw_decision_date=None, raw_last_change_reasons=(), coverage_checked_at=None,
        scope_verified=scope_verified,
    )


def _resolve_ownership_or_control_evidence_changed(session, opportunity_id: str) -> tuple[SignalValue, tuple[str, ...]]:
    """This reads ONLY whether the TRUSTED EVIDENCE used to understand
    ownership/control has changed since the last monitoring pass - reusing
    app.reporting.opportunity_change's own already-computed, already-named
    REASON_OWNERSHIP_EVIDENCE_CHANGED reason code verbatim (fired for BOTH
    planning_delivery's own ownership_evidence_count field and strategic_
    land's own matched_to_site field - see that module's own _REASON_BY_
    FIELD mapping). It never claims WHICH of newly-discovered/amended/
    conflicting evidence or a genuine control change occurred - that
    interpretation is explicitly future Acquisition Agent work.

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


def build_transaction_signals(
    session, opportunity, *,
    applications: list[Application] | None = None, site: Site | None = None,
    scope_verified: bool = False,
) -> TransactionSignals:
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

    `scope_verified` MUST be the caller's own already-computed app.policy.
    buyer_matching_b2_context.B2MatchingContext.development_state_scope_
    verified value for this exact opportunity (Defect 3 fix) - it is never
    recomputed here. Defaults to False (the same conservative default
    B2MatchingContext itself uses) so a caller that omits it gets the
    safe, non-overclaiming behaviour.

    Read-only throughout - never creates, updates or deletes anything."""
    ownership_signal, last_change_reasons = _resolve_ownership_or_control_evidence_changed(session, opportunity.opportunity_id)

    if opportunity.opportunity_type == STRATEGIC_LAND:
        bundle = _not_applicable_bundle(scope_verified)
        return TransactionSignals(
            recent_permission=bundle.recent_permission,
            approaching_implementation_deadline=bundle.approaching_implementation_deadline,
            implementation_activity_evidence_identified=bundle.implementation_activity_evidence_identified,
            wider_site_implementation_activity_context=bundle.wider_site_implementation_activity_context,
            no_qualifying_progress_evidence_identified=bundle.no_qualifying_progress_evidence_identified,
            ownership_or_control_evidence_changed=ownership_signal,
            raw_lapse_status=None, raw_implementation_deadline=None, raw_build_status=None,
            raw_decision_date=None, raw_last_change_reasons=last_change_reasons, coverage_checked_at=None,
            scope_verified=scope_verified,
        )

    # PLANNING_DELIVERY from here on.
    if applications is None or site is None:
        raise ValueError("build_transaction_signals requires applications and site for a PLANNING_DELIVERY opportunity")

    lapse_result = compute_lapse_status(applications, site)
    lapse_status = lapse_result["status"]
    deadline = lapse_result["deadline"]
    build_status = lapse_result["build_status"]  # SECONDARY/CORROBORATING only - see module docstring, Defect 1

    anchor = resolve_operative_lapse_anchor(applications)
    decision_date = anchor.decision_date if anchor.state == FACT_RESOLVED else None
    coverage_checked_at = anchor.application.related_search_checked_at if anchor.state == FACT_RESOLVED and anchor.application is not None else None

    # --- RECENT_PERMISSION (UNCHANGED - a planning-clock fact, not a
    # commencement claim; not scope-gated, per explicit Product Owner
    # instruction) -----------------------------------------------------------
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

    # --- APPROACHING_IMPLEMENTATION_DEADLINE (UNCHANGED) --------------------
    if lapse_status == "approaching":
        approaching_implementation_deadline = SignalValue.present(f"The statutory commencement deadline ({deadline.isoformat() if deadline else 'unknown'}) is within the platform's lapse-warning window.")
    elif lapse_status in ("underway", "safe", "lapsed"):
        approaching_implementation_deadline = SignalValue.absent("The deadline is not currently within the platform's lapse-warning window (already underway, comfortably distant, or already passed).")
    else:  # not_granted / not_determined / unknown
        approaching_implementation_deadline = SignalValue.unknown("No resolved implementation deadline exists to assess.")

    # --- IMPLEMENTATION_ACTIVITY_EVIDENCE_IDENTIFIED (Defect 1 + 3 fix) -----
    #
    # Derived ONLY from an authoritative, subsequent, genuinely-related
    # PLANNING application - the same find_progress_signal_filing/
    # PROGRESS_SIGNAL_CATEGORIES mechanism classify_build_status itself
    # uses for its own "underway" branch, called independently here so EPC
    # can never contribute to this signal. A found filing means only that
    # authoritative planning activity POTENTIALLY RELEVANT TO
    # IMPLEMENTATION exists - never that construction has commenced, that
    # development is underway, or that physical works have started (a
    # condition-discharge or variation/amendment filing is exactly the
    # kind of implementation-PREPARATION evidence the Product Owner's own
    # semantic-fix approval distinguishes from commencement - see this
    # module's docstring). PRESENT/UNKNOWN only, deliberately no ABSENT
    # state (Correction 1's "Unknown Must Remain Unknown" discipline
    # extended here: no filing found is not proof none exists or that
    # nothing has happened).
    filing = find_progress_signal_filing(applications, decision_date) if decision_date is not None else None
    if filing is not None:
        wider_site_implementation_activity_context = SignalValue.present(
            f"Post-permission planning activity identified for this site's application family: "
            f"{filing.reference} ({filing.application_category}), received {filing.application_received}. "
            f"This is evidence of planning activity potentially relevant to implementation or delivery - it "
            f"does not itself establish that construction has commenced or that physical works have started."
        )
    elif decision_date is None:
        wider_site_implementation_activity_context = SignalValue.unknown("No resolved operative permission exists to search subsequent planning activity against.")
    else:
        wider_site_implementation_activity_context = SignalValue.unknown(
            "No qualifying post-permission planning activity (condition-discharge or variation/amendment filing) "
            "has been identified for this site's application family."
        )

    if scope_verified:
        implementation_activity_evidence_identified = wider_site_implementation_activity_context
    elif wider_site_implementation_activity_context.is_present:
        # Defect 3: never present a whole-site finding as a confident
        # opportunity-level fact when scope is unverified - the finding
        # itself is preserved above, never discarded.
        implementation_activity_evidence_identified = SignalValue.unknown(
            "Implementation-related planning activity exists on the wider site/application family, but has not "
            "been verified as scoped to this specific opportunity - see wider_site_implementation_activity_context."
        )
    else:
        implementation_activity_evidence_identified = wider_site_implementation_activity_context  # already UNKNOWN either way

    # --- NO_QUALIFYING_PROGRESS_EVIDENCE_IDENTIFIED (Defect 2 + 3 fix) ------
    #
    # PRESENT only when ALL of: (1) a relevant operative permission/lapse
    # anchor is resolved; (2) the relevant related-application search has
    # actually run for that anchor (Application.related_search_checked_at
    # is populated - the same already-existing, already-continuous
    # coverage field app.pipeline.run_weekly.stage_fetch_related_
    # applications maintains); (3) no qualifying implementation-activity
    # evidence was found within that covered search; (4) the opportunity's
    # own scope is verified. Never inferred from permission age, lapse
    # deadline, absent EPC, or a mere absence of a positive finding alone -
    # UNKNOWN is always preferred over PRESENT when any condition is
    # unmet."""
    has_coverage = decision_date is not None and coverage_checked_at is not None
    if has_coverage and not wider_site_implementation_activity_context.is_present and scope_verified:
        no_qualifying_progress_evidence_identified = SignalValue.present(
            "PropertyAIgent has completed the relevant covered planning-evidence search (related-application "
            "discovery) and no qualifying implementation/progress evidence was identified within those covered "
            "sources. This does not mean the site is confirmed uncommenced, inactive, stalled, dormant, or land "
            "banked, and it does not mean the owner is not progressing the site - only that no qualifying evidence "
            "was found within the sources actually searched."
        )
    else:
        reasons = []
        if decision_date is None:
            reasons.append("no resolved operative permission exists")
        if decision_date is not None and coverage_checked_at is None:
            reasons.append("related-application discovery has not yet run for the operative permission")
        if wider_site_implementation_activity_context.is_present:
            reasons.append("qualifying planning activity was in fact identified")
        if not scope_verified:
            reasons.append("this opportunity's own scope has not been verified")
        no_qualifying_progress_evidence_identified = SignalValue.unknown(
            "Insufficient basis to conclude no qualifying progress evidence exists: " + "; ".join(reasons) + "."
        )

    return TransactionSignals(
        recent_permission=recent_permission,
        approaching_implementation_deadline=approaching_implementation_deadline,
        implementation_activity_evidence_identified=implementation_activity_evidence_identified,
        wider_site_implementation_activity_context=wider_site_implementation_activity_context,
        no_qualifying_progress_evidence_identified=no_qualifying_progress_evidence_identified,
        ownership_or_control_evidence_changed=ownership_signal,
        raw_lapse_status=lapse_status,
        raw_implementation_deadline=deadline,
        raw_build_status=build_status,
        raw_decision_date=decision_date,
        raw_last_change_reasons=last_change_reasons,
        coverage_checked_at=coverage_checked_at,
        scope_verified=scope_verified,
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
#
# A richer PLANNING DEVELOPMENT PROGRESS DETECTION capability - continuous
# (not just related-application) document discovery, document-content
# classification for commencement notices/construction management plans/
# discharge-of-conditions submissions, and a full IMPLEMENTATION_PREPARATION
# / COMMENCEMENT / DEVELOPMENT_UNDERWAY / DELIVERY_PROGRESS taxonomy -
# remains future, P1-after-Agent-Evaluation-Policy-V1 work (pre-release
# semantic audit, Section O). Not attempted here.
