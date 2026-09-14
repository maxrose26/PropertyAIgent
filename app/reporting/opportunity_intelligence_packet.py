"""Agent-Ready Opportunity Fact Coverage Assessment - Recommendation B,
Narrow Agent-Ready Fact Foundation. OpportunityIntelligencePacket.

A pure, read-only, NON-PERSISTED composition of already-computed, already-
trusted facts about ONE opportunity, for a future Acquisition Agent to
consume. This module establishes no new fact of its own: every field is
read straight from an existing trusted source -
app.policy.buyer_matching.MatchingFacts, app.policy.buyer_matching.
B2MatchingContext, app.db.models.LocalPlanSite/LocalPlan/SchemeIntelligence,
and (by reference, never duplicated) app.reporting.acquisition_position's
own Gate 2C AcquisitionPositionFacts. No LLM call. No numeric score. No
availability/willingness-to-sell/transaction-propensity inference anywhere
in this module - see app.reporting.acquisition_position's own governing
semantic, unchanged and un-weakened here.

DELIBERATELY BROADER THAN DETERMINISTIC BUYER FIT. A fact can be genuinely
useful to a future Acquisition Agent's commercial reasoning (e.g.
`recommendation_direction`, `affordable_housing_status`, `progression_
signal`) without ever becoming a new deterministic Buyer Fit rule - see
"packet vs MatchingFacts" in the target architecture:

    OPPORTUNITY INTELLIGENCE PACKET
        (this module - commercially useful trusted facts)
            |
            +--> DETERMINISTIC BUYER FIT (app.policy.buyer_matching) uses
            |    only the narrow subset appropriate for hard compatibility
            |
            +--> future ACQUISITION AGENT uses the richer packet for
                 commercial reasoning

Nothing in this module feeds back into assess_buyer_fit, and nothing here
changes MatchingFacts' own shape or fingerprint-affecting fields.

UNKNOWN vs NOT_APPLICABLE (Fact Coverage Assessment, Section 18): a bare
`None` conflates "evidence has not established this" with "this platform's
own domain semantics establish the fact can never exist for this
opportunity type" (e.g. scheme-specific affordable content for a Local
Plan allocation - see app.policy.buyer_matching's own B2 narrow semantic
cleanup, which fixed exactly this conflation inside Buyer Fit itself).
FactValue below makes the distinction explicit wherever it is material,
without redesigning every existing domain field around it.

STRATEGIC CONTEXT (Section 16): where a PLANNING_DELIVERY opportunity's
own Site has already been matched to a strategic Local Plan allocation
(LocalPlanSite.matched_site_id), that relationship is exposed as
`linked_strategic_allocation_id`/`linked_strategic_allocation_name` - a
plain fact lookup over an EXISTING relationship, never a new matching
attempt, never fuzzy, never backfilled. Absent is normal; present is a
useful additional fact. The opportunity's own `opportunity_type` is never
changed by this - a planning_delivery phase inside a strategic allocation
never becomes a strategic_land opportunity merely because of that context
(Fact Coverage Assessment, Section 17)."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from app.db.models import Application, LocalPlan, LocalPlanSite, Site
from app.policy.buyer_matching import PLANNING_DELIVERY, STRATEGIC_LAND, B2MatchingContext, MatchingFacts, OTHER_OR_UNKNOWN
from app.policy.buyer_matching_b2_context import build_b2_context
from app.reporting.acquisition_position import build_acquisition_position_facts
from app.reporting.opportunity_transaction_signals import TransactionSignals, build_transaction_signals

# --- FactValue: KNOWN / UNKNOWN / NOT_APPLICABLE -----------------------------

KNOWN = "KNOWN"
UNKNOWN = "UNKNOWN"
NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class FactValue:
    """One fact with an explicit KNOWN/UNKNOWN/NOT_APPLICABLE state -
    never collapses "evidence has not established this" and "this can
    never exist for this opportunity type" into the same bare `None`.
    `.value` is only ever meaningful when `.state == KNOWN` - a NOT_
    APPLICABLE fact's `.value` is always None, never a fabricated 0/False
    standing in for "does not apply" (Fact Coverage Assessment, Section
    18: "NOT_APPLICABLE != zero")."""

    state: str
    value: object | None = None

    @classmethod
    def known(cls, value) -> "FactValue":
        return cls(KNOWN, value)

    @classmethod
    def unknown(cls) -> "FactValue":
        return cls(UNKNOWN, None)

    @classmethod
    def not_applicable(cls) -> "FactValue":
        return cls(NOT_APPLICABLE, None)

    @property
    def is_known(self) -> bool:
        return self.state == KNOWN


# --- Actors / control summary (Gate 2C referenced, never duplicated) --------

@dataclass(frozen=True)
class PacketActorsControl:
    """A thin summary OVER app.reporting.acquisition_position's own
    AcquisitionPositionFacts for this opportunity - never a second,
    independently-derived ownership/control computation. Governing
    semantic, unchanged (see that module's own docstring): every fact
    here means only "PropertyAIgent holds evidence of this stated/
    apparent relationship, in this cited evidence" - never current
    registered ownership, current development control, exclusivity,
    whole-allocation control, land availability, or seller intention.
    Certificate A ownership evidence is never equivalent to registered
    title ownership."""

    developer_indications: tuple[str, ...]
    ownership_coverage: str | None  # one of app.reporting.acquisition_position's COVERAGE_* constants, or None if not computed
    conflicts: tuple[str, ...]
    has_ownership_evidence: bool


# --- The packet itself --------------------------------------------------

@dataclass(frozen=True)
class OpportunityIntelligencePacket:
    """One opportunity's agent-ready fact composition. See this module's
    own docstring for the governing architecture and semantics. Every
    field below traces to an existing, already-trusted source - nothing
    here is computed for the first time by this module beyond plain
    lookups and the FactValue KNOWN/UNKNOWN/NOT_APPLICABLE classification
    itself."""

    # --- Identity ---
    opportunity_id: str
    opportunity_type: str  # STRATEGIC_LAND | PLANNING_DELIVERY
    kind: str  # "allocation" | "site" | "phase" | "recent_permission" | "long_pending_application"
    council_code: str | None
    site_id: int | None
    allocation_id: int | None

    # --- Opportunity scope (Section 11.B) ---
    phase_code: str | None
    development_state_scope_verified: bool

    # --- Scale (Section 11.C) ---
    total_units: FactValue
    affordable_units: FactValue
    affordable_percentage: FactValue

    # --- Planning / strategic position (Section 11.D) ---
    operative_planning_state: FactValue  # PLANNING_DELIVERY only
    recommendation_direction: FactValue  # PLANNING_DELIVERY only - SchemeIntelligence.recommendation_direction
    local_plan_status: FactValue  # STRATEGIC_LAND only - the authoritative LocalPlan.status
    allocation_status: FactValue  # STRATEGIC_LAND only - LocalPlanSite.allocation_status
    progression_signal: FactValue  # STRATEGIC_LAND only - app.policy.progression.classify_progression's own output
    has_identified_planning_activity: FactValue  # STRATEGIC_LAND only

    # --- Development position (Section 11.E) ---
    development_state: FactValue  # reused verbatim from B2MatchingContext - Unknown Must Remain Unknown

    # --- Affordable / S106-adjacent position (Section 11.F / 14) ---
    affordable_housing_status: FactValue  # PLANNING_DELIVERY only - SchemeIntelligence.affordable_housing_status; NEVER claimed equivalent to an executed S106

    # --- Actors / control (Section 11.G) ---
    actors_control: PacketActorsControl

    # --- Strategic context (Section 11.H / 16) ---
    linked_strategic_allocation_id: int | None
    linked_strategic_allocation_name: str | None

    # --- Transaction/disposition signals (Agent Evaluation Foundation) ---
    # Buyer-independent, deterministic, never a seller-intent/availability
    # claim - see app.reporting.opportunity_transaction_signals' own module
    # docstring for the full governing semantics and the two Product Owner
    # corrections it encodes (absence of commencement evidence is never
    # confirmed inactivity; evidence changing is not the same claim as
    # ownership changing).
    transaction_signals: TransactionSignals


def _scheme_intelligence_field(applications, field_name: str) -> str | None:
    """Returns the first non-null value of `field_name` across every
    Application linked to this opportunity's Site that has a
    SchemeIntelligence row - mirrors app.ui.common's own established
    "merge across every application linked to the site" precedent (a
    detail may only have been extracted from a sibling application's own
    documents). Never averages, never picks a "most recent" - the first
    genuinely non-null value found, since these are id/status/text
    fields, not something a preference order would meaningfully rank."""
    for application in applications:
        si = application.scheme_intelligence
        if si is not None:
            value = getattr(si, field_name, None)
            if value:
                return value
    return None


def build_opportunity_intelligence_packet(
    session, opportunity, *, context: B2MatchingContext | None = None,
) -> OpportunityIntelligencePacket:
    """Composes the packet for ONE opportunity from already-existing
    trusted sources. `opportunity` is an app.reporting.opportunity_
    universe.OpportunityRecord (or any object exposing the same
    opportunity_id/opportunity_type/matching_facts shape). `context`, if
    already built by the caller, is reused rather than rebuilt - the same
    "build once, reuse" contract build_b2_context/evaluate_buyer_fit
    already document, since a packet is itself buyer-independent and
    naturally built once per opportunity regardless of how many buyers
    are later evaluated against it.

    Read-only throughout - never creates, updates or deletes anything."""
    facts: MatchingFacts = opportunity.matching_facts
    if context is None:
        context = build_b2_context(session, opportunity.opportunity_id, opportunity.opportunity_type)

    parts = opportunity.opportunity_id.split(":")
    kind = parts[1]
    entity_id = int(parts[2])
    phase_code = parts[3] if len(parts) > 3 else None

    development_state = (
        FactValue.unknown() if context.development_state in (None, "unknown") else FactValue.known(context.development_state)
    )

    if opportunity.opportunity_type == STRATEGIC_LAND:
        allocation_id = entity_id
        site_id = None
        allocation = session.get(LocalPlanSite, allocation_id)
        local_plan = session.get(LocalPlan, allocation.local_plan_id) if allocation is not None and allocation.local_plan_id else None

        local_plan_status = FactValue.known(local_plan.status) if local_plan is not None and local_plan.status else FactValue.unknown()
        allocation_status = (
            FactValue.known(allocation.allocation_status)
            if allocation is not None and allocation.allocation_status
            else FactValue.unknown()
        )
        progression_signal = (
            FactValue.known(allocation.progression_signal)
            if allocation is not None and allocation.progression_signal
            else FactValue.unknown()
        )
        has_identified_planning_activity = (
            FactValue.unknown()
            if facts.has_identified_planning_activity is None
            else FactValue.known(facts.has_identified_planning_activity)
        )

        # An application-centric operative planning state / officer
        # recommendation / affordable-housing-status genuinely does not
        # exist for a Local Plan allocation with no scheme yet - NOT
        # APPLICABLE, never UNKNOWN (Section 18's own governing example).
        operative_planning_state = FactValue.not_applicable()
        recommendation_direction = FactValue.not_applicable()
        affordable_housing_status = FactValue.not_applicable()

        # Scheme-specific affordable content is structurally unavailable
        # for a Local Plan allocation (see MatchingFacts' own field
        # docstring: "Always None for STRATEGIC_LAND") - NOT_APPLICABLE,
        # never UNKNOWN and never assumed 0%.
        affordable_units = FactValue.not_applicable()
        affordable_percentage = FactValue.not_applicable()

        acquisition_facts = build_acquisition_position_facts(session, [])
        actors_control = PacketActorsControl(
            developer_indications=tuple(d.developer_name for d in acquisition_facts.developer_indications),
            ownership_coverage=acquisition_facts.ownership_coverage,
            conflicts=tuple(acquisition_facts.conflicts),
            has_ownership_evidence=bool(acquisition_facts.ownership_evidence),
        )

        # A strategic_land opportunity IS the allocation itself - "linked
        # TO a strategic allocation" is a PLANNING_DELIVERY-side concept
        # (Section 16), not applicable to the allocation's own record.
        linked_strategic_allocation_id = None
        linked_strategic_allocation_name = None

        transaction_signals = build_transaction_signals(session, opportunity, scope_verified=context.development_state_scope_verified)

    else:
        site_id = entity_id
        allocation_id = None
        site = session.get(Site, site_id)
        applications = session.execute(select(Application).where(Application.site_id == site_id)).scalars().all()

        operative_planning_state = (
            FactValue.unknown() if facts.planning_state == OTHER_OR_UNKNOWN else FactValue.known(facts.planning_state)
        )
        recommendation_direction_raw = _scheme_intelligence_field(applications, "recommendation_direction")
        recommendation_direction = FactValue.known(recommendation_direction_raw) if recommendation_direction_raw else FactValue.unknown()
        affordable_housing_status_raw = _scheme_intelligence_field(applications, "affordable_housing_status")
        affordable_housing_status = (
            FactValue.known(affordable_housing_status_raw) if affordable_housing_status_raw else FactValue.unknown()
        )

        # Strategic-land-only facts are NOT_APPLICABLE for a
        # planning_delivery opportunity (Section 17 - never collapsed
        # into the same "strategic land" reading merely because a linked
        # allocation may exist - see linked_strategic_allocation_* below
        # instead, which is the correct, separate way to expose that).
        local_plan_status = FactValue.not_applicable()
        allocation_status = FactValue.not_applicable()
        progression_signal = FactValue.not_applicable()
        has_identified_planning_activity = FactValue.not_applicable()

        affordable_units = FactValue.unknown() if facts.affordable_unit_count is None else FactValue.known(facts.affordable_unit_count)
        affordable_percentage = (
            FactValue.unknown() if not facts.affordable_percentage_trusted else FactValue.known(facts.affordable_percentage)
        )

        acquisition_facts = build_acquisition_position_facts(session, applications)
        actors_control = PacketActorsControl(
            developer_indications=tuple(d.developer_name for d in acquisition_facts.developer_indications),
            ownership_coverage=acquisition_facts.ownership_coverage,
            conflicts=tuple(acquisition_facts.conflicts),
            has_ownership_evidence=bool(acquisition_facts.ownership_evidence),
        )

        # Strategic context (Section 16): does an EXISTING, already-
        # established LocalPlanSite -> Site match point at this same
        # Site? Never a new matching attempt, never fuzzy - a plain
        # lookup over the trusted matched_site_id relationship that
        # already exists for a different reason entirely (Pilot
        # Readiness PR-2's own allocation<->site review workflow).
        linked_allocation = (
            session.execute(select(LocalPlanSite).where(LocalPlanSite.matched_site_id == site_id)).scalars().first()
            if site is not None
            else None
        )
        linked_strategic_allocation_id = linked_allocation.id if linked_allocation is not None else None
        linked_strategic_allocation_name = linked_allocation.site_name if linked_allocation is not None else None

        transaction_signals = build_transaction_signals(
            session, opportunity, applications=applications, site=site,
            scope_verified=context.development_state_scope_verified,
        )

    total_units = FactValue.unknown() if facts.unit_count is None else FactValue.known(facts.unit_count)

    return OpportunityIntelligencePacket(
        opportunity_id=opportunity.opportunity_id,
        opportunity_type=opportunity.opportunity_type,
        kind=kind,
        council_code=context.council_code,
        site_id=site_id,
        allocation_id=allocation_id,
        phase_code=phase_code,
        development_state_scope_verified=context.development_state_scope_verified,
        total_units=total_units,
        affordable_units=affordable_units,
        affordable_percentage=affordable_percentage,
        operative_planning_state=operative_planning_state,
        recommendation_direction=recommendation_direction,
        local_plan_status=local_plan_status,
        allocation_status=allocation_status,
        progression_signal=progression_signal,
        has_identified_planning_activity=has_identified_planning_activity,
        development_state=development_state,
        affordable_housing_status=affordable_housing_status,
        actors_control=actors_control,
        linked_strategic_allocation_id=linked_strategic_allocation_id,
        linked_strategic_allocation_name=linked_strategic_allocation_name,
        transaction_signals=transaction_signals,
    )
