"""Buyer Mandate V2, Phase B2 (Deterministic Buyer Fit Integration) - the
ONE DB-touching orchestration layer that builds a
app.policy.buyer_matching.B2MatchingContext for a given opportunity, and
(Agent-Ready Fact Foundation, P0-2) the ONE authoritative production entry
point for evaluating Buyer Fit at all.

Deliberately kept OUT of app.policy.buyer_matching itself (which must stay
pure/DB-free/network-free/LLM-free - Phase B2 brief, Section 8) and OUT of
app.reporting.opportunity_universe (which Section 54 explicitly forbids
modifying - the shared candidate universe's own detector routes,
fingerprints, ordering and ranking are completely untouched by this
module; it only ever READS an opportunity's already-established identity
to fetch ADDITIONAL trusted facts, never changes which opportunities exist
or how they're found).

Called ONCE per opportunity, never once per (opportunity, buyer) pair -
the resulting B2MatchingContext is reused across every buyer mandate
assessed against that same opportunity, since council/development-state/
Gate 2C control facts are all buyer-independent. This is the "narrow
orchestration-level optimisation" the Phase B2 brief's own Section 64
anticipated ("if acquisition facts are recomputed four times for the same
opportunity when they could safely be computed once and reused") - built
this way from the start rather than added as an afterthought.

Gate 2C's own build_acquisition_position_facts is a genuinely live,
per-application-family computation (see app.reporting.acquisition_
position's own module docstring for its documented cost) - this module is
the ONLY place in the Buyer Mandate V2 domain that calls it.

AGENT-READY FACT FOUNDATION (P0-2, post B2 production closure): the Fact
Coverage Assessment found that every production caller of
app.policy.buyer_matching.assess_buyer_fit (the live opportunity feed, the
Local Plan Sites page, and the onboarding baseline) called it WITHOUT a
B2MatchingContext - B2 was fully implemented, tested and deployed, yet had
zero live behavioural effect. `evaluate_buyer_fit` below is the fix: THE
one supported production entry point for evaluating Buyer Fit at all,
which every product consumer must go through instead of calling
assess_buyer_fit directly (pure, DB-free unit tests may still call
assess_buyer_fit directly - they are testing the deterministic matching
logic itself, not a product code path). `context` has no default here
(unlike assess_buyer_fit's own optional parameter, which stays optional
purely for backward-compatible unit testing) - a caller reaching this
function is a real production consumer and must supply one, either
pre-built (the "build once, reuse across buyers" contract) or via enough
raw identity to let this function build one itself."""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import Application, LocalPlanSite, Site
from app.pipeline.lapse_tracking import compute_lapse_status
from app.pipeline.phase_tracking import UNPHASED_LABEL
from app.policy.buyer_matching import (
    PLANNING_DELIVERY,
    STRATEGIC_LAND,
    B2MatchingContext,
    BuyerFitAssessment,
    BuyerMandatePolicy,
    MatchingFacts,
    assess_buyer_fit,
    build_control_appetite_facts,
)
from app.reporting.acquisition_position import build_acquisition_position_facts


def build_b2_context_for_strategic_land(session, allocation_id: int) -> B2MatchingContext:
    """The STRATEGIC_LAND half of build_b2_context, extracted as its own
    primitive (Agent-Ready Fact Foundation) so a caller that already has a
    raw allocation id - never having constructed an opportunity_universe-
    style opportunity_id string at all - can build a context directly.
    app.reporting.opportunity_feed's own strategic-land cards are exactly
    such a caller: their own card identity is "opp-feed-alloc-{id}", not
    this domain's "strategic_land:allocation:{id}" convention. Read-only;
    identical logic to build_b2_context's own former inline body."""
    allocation = session.get(LocalPlanSite, allocation_id)
    council_code = allocation.council_code if allocation is not None else None
    # A Local Plan allocation with no matched Site has no application
    # family at all - Gate 2C's own build_acquisition_position_facts
    # already handles an empty application list honestly (every fact
    # stays absent/insufficient, never guessed), so this is simply
    # passed through rather than special-cased here.
    acquisition_facts = build_acquisition_position_facts(session, [])
    return B2MatchingContext(
        council_code=council_code,
        development_state=None,  # no site/applications - genuinely not applicable, not "unknown-but-checked"
        control_facts=build_control_appetite_facts(acquisition_facts),
    )


def build_b2_context_for_planning_delivery(
    session, site_id: int, *, development_state_scope_verified: bool = False,
) -> B2MatchingContext:
    """The PLANNING_DELIVERY half of build_b2_context, extracted as its
    own primitive (Agent-Ready Fact Foundation) for the same reason as
    build_b2_context_for_strategic_land above - a caller with a raw
    site_id (e.g. the live opportunity feed's own delivery cards, keyed
    by card["params"]["site_id"]) never needs to construct a fake
    opportunity_universe-style id string just to reach this logic.
    `development_state_scope_verified` defaults to the same safe False
    every B2MatchingContext field defaults to - a caller unable to
    positively establish scope (e.g. the live feed's own detector
    taxonomy, which does not map 1:1 onto app.reporting.opportunity_
    universe's site/phase/recent_permission/long_pending_application
    kinds) simply leaves it unset, which can never cause an incorrect
    hard rejection (see assess_buyer_fit's own STRATEGIC_LAND_CONTROL
    scope-safety rule). Read-only; identical logic to build_b2_context's
    own former inline body."""
    site = session.get(Site, site_id)
    applications = session.execute(select(Application).where(Application.site_id == site_id)).scalars().all()

    council_code = site.council_code if site is not None else (applications[0].council_code if applications else None)

    development_state = "unknown"
    if site is not None and applications:
        # Reused verbatim - the SAME function app.reporting.
        # opportunity_universe already calls for its own fingerprint's
        # build_status field (never a second, independently-derived
        # build-status computation).
        lapse_result = compute_lapse_status(applications, site)
        development_state = lapse_result.get("build_status") or "unknown"

    acquisition_facts = build_acquisition_position_facts(session, applications)
    control_facts = build_control_appetite_facts(acquisition_facts)

    return B2MatchingContext(
        council_code=council_code,
        development_state=development_state,
        control_facts=control_facts,
        development_state_scope_verified=development_state_scope_verified,
    )


def build_b2_context(session, opportunity_id: str, opportunity_type: str) -> B2MatchingContext:
    """Parses an app.reporting.opportunity_universe opportunity_id
    (e.g. "planning_delivery:site:504", "strategic_land:allocation:1") to
    recover the underlying Site/LocalPlanSite id - the same id-encoding
    convention that module's own strategic_land_opportunity_id/
    planning_delivery_*_opportunity_id helpers already establish; this
    function never invents a new one. Every PLANNING_DELIVERY variant
    (site/phase/recent_permission/long_pending_application) encodes the
    site_id as the segment immediately after the kind, regardless of any
    further suffix (e.g. a phase_code) - so parsing only ever needs that
    one segment.

    A thin wrapper over build_b2_context_for_strategic_land/
    build_b2_context_for_planning_delivery above - kept for every existing
    caller that already has (or can cheaply construct) an
    opportunity_universe-style id string (the onboarding baseline, the
    Local Plan Sites page, every read-only diagnostic script). A caller
    with only a raw allocation_id/site_id (the live opportunity feed)
    should call the two primitives directly instead of constructing a
    fake id string merely to satisfy this function's own parsing.

    Read-only throughout - never creates, updates or deletes anything.

    Phase B2 narrow remediation (Issue B): also determines
    development_state_scope_verified - whether `development_state` below
    is known to cover the SAME opportunity scope as this specific
    opportunity, using the platform's OWN existing scope vocabulary
    (app.pipeline.phase_tracking.UNPHASED_LABEL, already used by
    app.reporting.opportunity_universe itself to distinguish a genuine
    whole-site/"Whole site / unphased" card from a named Phase/Plot
    card - no new scope taxonomy is introduced here). A "site" kind
    opportunity IS the whole site, so scope is trivially verified; a
    "phase" kind opportunity is verified only when its own phase_code
    equals UNPHASED_LABEL (i.e. it is itself the whole-site/unphased
    scope, just recorded under the "phase" kind bucket - see
    build_current_opportunity_universe's own kind=="phase" branch). A
    named phase/plot, a "recent_permission", or a "long_pending_
    application" opportunity is a NARROWER scope than "the whole site",
    so a site-wide or differently-scoped underway/build-status fact is
    never assumed to describe that narrower opportunity's own scope -
    scope stays unverified (False) for those, which is the safe default
    B2MatchingContext.development_state_scope_verified itself already
    documents."""
    parts = opportunity_id.split(":")
    kind = parts[1]
    entity_id = int(parts[2])

    if opportunity_type == STRATEGIC_LAND:
        return build_b2_context_for_strategic_land(session, entity_id)

    # PLANNING_DELIVERY (site / phase / recent_permission / long_pending_application)
    site_id = entity_id
    if kind == "site":
        development_state_scope_verified = True
    elif kind == "phase":
        # parts[3] is the phase_code segment of planning_delivery_phase_
        # opportunity_id(site_id, phase_code) - only equal to UNPHASED_
        # LABEL for a genuine whole-site/unphased card.
        phase_code = parts[3] if len(parts) > 3 else None
        development_state_scope_verified = phase_code == UNPHASED_LABEL
    else:  # "recent_permission" / "long_pending_application"
        development_state_scope_verified = False

    return build_b2_context_for_planning_delivery(session, site_id, development_state_scope_verified=development_state_scope_verified)


def evaluate_buyer_fit(
    session,
    profile: BuyerMandatePolicy,
    facts: MatchingFacts,
    *,
    context: B2MatchingContext | None = None,
    opportunity_id: str | None = None,
    opportunity_type: str | None = None,
    allocation_id: int | None = None,
    site_id: int | None = None,
    development_state_scope_verified: bool = False,
) -> BuyerFitAssessment:
    """THE one supported production entry point for evaluating Buyer Fit
    (Agent-Ready Fact Foundation, P0-2 - see this module's own docstring
    for the finding this fixes). Every product consumer (the opportunity
    feed, the Local Plan Sites page, the onboarding baseline) must call
    this, never bare app.policy.buyer_matching.assess_buyer_fit(profile,
    facts) - that call shape silently activates B1-only semantics by
    omitting B2MatchingContext, exactly the defect this function exists
    to make structurally impossible to repeat.

    Resolves a B2MatchingContext for the opportunity, then delegates to
    the existing, completely unmodified assess_buyer_fit - this function
    adds no reasoning, no new classification, no new hard exclusion; it
    is purely the DB-touching boundary assess_buyer_fit itself must never
    cross (Phase B2 brief, Section 8 - assess_buyer_fit stays pure/
    DB-free/LLM-free).

    Exactly one of the following must be supplied to resolve the context:
      - `context` itself, already built - pass this when evaluating
        MANY buyers against the SAME opportunity (e.g. the onboarding
        bootstrap loop, or any future batch/diagnostic use), so Gate 2C's
        own live computation happens exactly once per opportunity, never
        once per (opportunity, buyer) pair - the same contract
        build_b2_context has always documented for itself.
      - `opportunity_id` + `opportunity_type` - for a caller that already
        has (or can cheaply construct) an opportunity_universe-style id.
      - `allocation_id` - for a STRATEGIC_LAND caller with only a raw
        allocation id (e.g. the live opportunity feed's own strategic-
        land cards, keyed by card["params"]["allocation_id"]).
      - `site_id` (optionally with `development_state_scope_verified`) -
        for a PLANNING_DELIVERY caller with only a raw site id (the live
        feed's own delivery cards, keyed by card["params"]["site_id"])."""
    if context is None:
        if opportunity_id is not None:
            context = build_b2_context(session, opportunity_id, opportunity_type)
        elif allocation_id is not None:
            context = build_b2_context_for_strategic_land(session, allocation_id)
        elif site_id is not None:
            context = build_b2_context_for_planning_delivery(session, site_id, development_state_scope_verified=development_state_scope_verified)
        else:
            raise ValueError(
                "evaluate_buyer_fit requires one of: context, opportunity_id+opportunity_type, allocation_id, or site_id"
            )
    return assess_buyer_fit(profile, facts, context=context)
