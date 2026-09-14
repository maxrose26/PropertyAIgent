"""Agent Evaluation Foundation - Acquisition-Type Interpretation Policy V1
(narrow pre-Agent foundation; Product Owner review of the Agent Evaluation
Policy V1 architecture report and its refinement).

Pure, versioned CONFIG - bounded commercial principles for how a future
Acquisition Agent should read each app.reporting.opportunity_transaction_
signals signal THROUGH one of app.policy.buyer_profiles' four existing
acquisition types (LAND_SITE_ACQUISITION / STRATEGIC_LAND_CONTROL /
AFFORDABLE_HOUSING_PACKAGE / DEVELOPMENT_HOMES_ACQUISITION). No BuyerMandate
field is read, added, or changed here - see app.policy.mandate_
interpretation's own docstring for why acquisition_types is deliberately
NOT classified as a mandate dimension: it is the SELECTOR that chooses
which set of principles below applies, not a constraint/preference itself.

DELIBERATELY NOT A POLARITY LOOKUP TABLE (Product Owner correction,
Sections 4/9). A rigid "signal -> positive/negative" table was proposed and
explicitly rejected: e.g. RECENT_PERMISSION must never mean "low
transaction propensity for a land buyer" as a fixed rule - it means only
"recent consent has been established," and a future agent may read that as
a potential value-realisation point, preparation for self-delivery, or
neutral, DEPENDING on other evidence (ownership, development-progress
signals). Every principle below is therefore expressed as circumstances,
not a verdict - `strengthens_when`/`weakens_when`/`neutral_when` describe
conditions under which a reading applies, never a standalone answer.

This module contains no decision logic, no scoring, and is never itself
called by anything today - it is read-only reference config for the NOT-
YET-BUILT Agent Evaluation Policy to consult. Nothing in PropertyAIgent
currently imports or evaluates this module as part of any live code path.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.policy.buyer_profiles import (
    AFFORDABLE_HOUSING_PACKAGE,
    DEVELOPMENT_HOMES_ACQUISITION,
    LAND_SITE_ACQUISITION,
    STRATEGIC_LAND_CONTROL,
)

ACQUISITION_TYPE_INTERPRETATION_POLICY_VERSION = 1


@dataclass(frozen=True)
class SignalCommercialPrinciple:
    """One transaction/disposition signal's bounded commercial reading for
    ONE acquisition type - descriptive config for a future agent to reason
    within, never itself a positive/negative/neutral VERDICT. `signal`
    names the app.reporting.opportunity_transaction_signals field this
    principle applies to (e.g. "recent_permission")."""

    signal: str
    why_it_matters: str
    strengthens_when: str
    weakens_when: str
    neutral_when: str
    distinguishing_evidence: str


# --- LAND_SITE_ACQUISITION ---------------------------------------------------
# The buyer wants the site/parcel itself, for its own future scheme.

_LAND_SITE_ACQUISITION_PRINCIPLES = (
    SignalCommercialPrinciple(
        signal="recent_permission",
        why_it_matters="A fresh grant can mean the current holder is about to commit capital to delivery (closing a land-acquisition window), or has just crystallised value it may now consider realising via disposal (opening one) - the fact alone does not distinguish these.",
        strengthens_when="Paired with no development-progress evidence and no clear developer-led delivery indication yet - the window may still be genuinely open.",
        weakens_when="Paired with development_underway PRESENT for the same scope, or a clear developer-led delivery indication with no ownership/control uncertainty.",
        neutral_when="Isolated, with no other transaction/disposition signal yet available.",
        distinguishing_evidence="development_underway; ownership_or_control_evidence_changed; the identity/type of any developer indication.",
    ),
    SignalCommercialPrinciple(
        signal="no_identified_development_progress",
        why_it_matters="This is the closest buyer-independent proxy PropertyAIgent has for 'the current holder may not be actively progressing delivery of this scope' - it is not evidence of unwillingness to build or to sell.",
        strengthens_when="Paired with any ownership/control uncertainty - worth an investigative approach.",
        weakens_when="Explained by known phasing evidence indicating delivery is planned for a later, scheduled stage rather than stalled.",
        neutral_when="On its own, without any scale/fit read for this buyer's own target.",
        distinguishing_evidence="has_phasing_evidence; approaching_implementation_deadline; ownership_or_control_evidence_changed.",
    ),
    SignalCommercialPrinciple(
        signal="development_underway",
        why_it_matters="Usually signals the current holder intends to deliver, not dispose of, THIS scope.",
        strengthens_when="A distinct, evidenced later phase or adjacent parcel within the same site remains untouched by this progress (see app.reporting.opportunity_intelligence_packet's own linked-context fields) - the land-acquisition interest may lie there instead.",
        weakens_when="The progress evidence covers the same scope the buyer is actually assessing.",
        neutral_when="The opportunity's own scope relative to the progress evidence is not yet verified (development_state_scope_verified is False).",
        distinguishing_evidence="development_state_scope_verified; phase_code; linked_strategic_allocation_id.",
    ),
    SignalCommercialPrinciple(
        signal="approaching_implementation_deadline",
        why_it_matters="A statutory deadline approaching without progress can mean a holder may welcome a land-acquisition conversation before the permission lapses, or may be about to commence to preserve it - both remain live possibilities.",
        strengthens_when="Paired with no_identified_development_progress PRESENT and no clear developer-led delivery signal.",
        weakens_when="Paired with development_underway PRESENT (commencement to preserve the permission may already be happening).",
        neutral_when="Isolated.",
        distinguishing_evidence="development_underway; ownership_or_control_evidence_changed.",
    ),
    SignalCommercialPrinciple(
        signal="ownership_or_control_evidence_changed",
        why_it_matters="A change in the trusted ownership/control evidence can reopen a conversation, but the signal itself never says what changed.",
        strengthens_when="The newly-evidenced controller is of a type this buyer's own mandate is willing to investigate (see app.policy.mandate_interpretation's own control_appetite reading).",
        weakens_when="The change is later found (via further evidence) to reflect the same delivery-focused holder as before.",
        neutral_when="On its own, before the nature of the change is established.",
        distinguishing_evidence="The specific new ownership/control evidence itself, once investigated.",
    ),
)

# --- STRATEGIC_LAND_CONTROL ---------------------------------------------------
# The buyer wants long-term promotion/control of the allocation, at
# whatever lifecycle stage.

_STRATEGIC_LAND_CONTROL_PRINCIPLES = (
    SignalCommercialPrinciple(
        signal="development_underway",
        why_it_matters="Can mean the wider strategic allocation has genuinely moved past a control-stage opportunity into delivery - or can describe only a narrower phase that does not represent the whole allocation.",
        strengthens_when="Never strengthens this acquisition type on its own.",
        weakens_when="The evidence is confirmed to apply at the SAME scope as the strategic opportunity being assessed (development_state_scope_verified is True) - this is exactly why app.policy.buyer_matching's own STRATEGIC_LAND_CONTROL hard-rejection rule requires verified scope before treating this as disqualifying.",
        neutral_when="development_state_scope_verified is False - a confirmed-underway phase, recent permission, or long-pending application does not itself prove the wider allocation has been overtaken.",
        distinguishing_evidence="development_state_scope_verified; whether the opportunity itself is STRATEGIC_LAND or a linked PLANNING_DELIVERY phase.",
    ),
    SignalCommercialPrinciple(
        signal="ownership_or_control_evidence_changed",
        why_it_matters="A change in the evidenced promoter/controller of an allocation is directly relevant to a control-stage strategy.",
        strengthens_when="Paired with an early or progressing Local Plan stage (more room to shape the promotion).",
        weakens_when="Never weakens this acquisition type on its own - it is always worth investigating for a control-stage buyer.",
        neutral_when="Never fully neutral - always worth noting for this acquisition type.",
        distinguishing_evidence="The allocation's own progression_signal.",
    ),
)

# --- AFFORDABLE_HOUSING_PACKAGE ------------------------------------------------
# The buyer wants the affordable-unit content of a scheme, not its total
# scale.

_AFFORDABLE_HOUSING_PACKAGE_PRINCIPLES = (
    SignalCommercialPrinciple(
        signal="development_underway",
        why_it_matters="Can mean the affordable units are on a concrete, fundable delivery track, or that they have already been allocated to another party (e.g. a registered provider already in place).",
        strengthens_when="Paired with no other registered-provider/housing-association developer indication already evidenced for this scheme.",
        weakens_when="A developer indication already evidences a different housing association or registered provider already engaged.",
        neutral_when="No developer/RP indication is available either way.",
        distinguishing_evidence="developer_indications on the packet's own actors_control field.",
    ),
    SignalCommercialPrinciple(
        signal="recent_permission",
        why_it_matters="Establishes the scheme's affordable content is now fixed by a real decision, not merely proposed.",
        strengthens_when="Paired with a confirmed, non-zero affordable-unit count within this buyer's own target.",
        weakens_when="Paired with a confirmed zero-affordable outcome (already a hard exclusion under Buyer Fit, independent of this signal).",
        neutral_when="The affordable-unit count itself remains unconfirmed.",
        distinguishing_evidence="affordable_housing_status; affordable_unit_count/affordable_percentage on the packet.",
    ),
)

# --- DEVELOPMENT_HOMES_ACQUISITION --------------------------------------------
# The buyer wants completed or near-complete homes, or a forward-funding
# position.

_DEVELOPMENT_HOMES_ACQUISITION_PRINCIPLES = (
    SignalCommercialPrinciple(
        signal="development_underway",
        why_it_matters="Direct, positive evidence of an imminent deliverable pipeline - the read most favourable to this acquisition type of any signal in the taxonomy.",
        strengthens_when="Present, for the same scope the buyer is assessing.",
        weakens_when="Never weakens this acquisition type - development progress is inherently positive here.",
        neutral_when="UNKNOWN (no progress evidence identified) rather than confirmed absent - this is genuinely neutral, not negative (see no_identified_development_progress's own principle below for why it is NOT automatically read negatively even here).",
        distinguishing_evidence="partially_complete (further strengthens - closer to deliverable stock); development_state_scope_verified.",
    ),
    SignalCommercialPrinciple(
        signal="partially_complete",
        why_it_matters="The strongest available positive evidence of near-term deliverable stock for a forward-purchase/completed-homes strategy.",
        strengthens_when="Present.",
        weakens_when="Never weakens this acquisition type.",
        neutral_when="UNKNOWN - most schemes lack EPC-sourced completion evidence; absence of this signal is not itself informative.",
        distinguishing_evidence="Total unit count relative to this buyer's own target.",
    ),
    SignalCommercialPrinciple(
        signal="no_identified_development_progress",
        why_it_matters="May indicate a stalled pipeline - a genuine, if evidentially soft, negative for this acquisition type specifically, in contrast to LAND_SITE_ACQUISITION where the same signal opens a land-acquisition window.",
        strengthens_when="Never strengthens this acquisition type.",
        weakens_when="Paired with a recent_permission that is no longer within the recency window (i.e. this reads more meaningfully once enough time has passed to plausibly expect progress, never merely because the signal is PRESENT for a very fresh grant).",
        neutral_when="Paired with a still-recent grant (recent_permission PRESENT) - too early to read this as a stalled pipeline.",
        distinguishing_evidence="recent_permission; approaching_implementation_deadline.",
    ),
    SignalCommercialPrinciple(
        signal="recent_permission",
        why_it_matters="A future pipeline entry point, not yet an actionable one for this acquisition type.",
        strengthens_when="Never strengthens this acquisition type on its own (no delivery evidence yet).",
        weakens_when="Never weakens this acquisition type on its own.",
        neutral_when="Always neutral in isolation - this acquisition type cares about delivery progress, which recent_permission alone does not yet establish.",
        distinguishing_evidence="development_underway; partially_complete.",
    ),
)

ACQUISITION_TYPE_PRINCIPLES: dict[str, tuple[SignalCommercialPrinciple, ...]] = {
    LAND_SITE_ACQUISITION: _LAND_SITE_ACQUISITION_PRINCIPLES,
    STRATEGIC_LAND_CONTROL: _STRATEGIC_LAND_CONTROL_PRINCIPLES,
    AFFORDABLE_HOUSING_PACKAGE: _AFFORDABLE_HOUSING_PACKAGE_PRINCIPLES,
    DEVELOPMENT_HOMES_ACQUISITION: _DEVELOPMENT_HOMES_ACQUISITION_PRINCIPLES,
}


def get_principles(acquisition_type: str) -> tuple[SignalCommercialPrinciple, ...]:
    """The one read accessor a future Agent Evaluation Policy should use -
    returns an empty tuple for an acquisition type this policy has not
    (yet) documented principles for, never raises, so a caller can always
    fall back to asking no acquisition-type-specific question rather than
    crashing."""
    return ACQUISITION_TYPE_PRINCIPLES.get(acquisition_type, ())


def get_principle_for_signal(acquisition_type: str, signal: str) -> SignalCommercialPrinciple | None:
    """Convenience lookup for one specific signal within one acquisition
    type's own principles - returns None (never raises) when this policy
    has not documented that combination."""
    for principle in get_principles(acquisition_type):
        if principle.signal == signal:
            return principle
    return None
