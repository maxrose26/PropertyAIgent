"""Buyer Mandate V2, Phase B2 (Deterministic Buyer Fit Integration) - the
ONE DB-touching orchestration layer that builds a
app.policy.buyer_matching.B2MatchingContext for a given opportunity.

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
the ONLY place in the Buyer Mandate V2 domain that calls it, and it is
never called from a page-load/live-feed path today (see this module's own
callers - only the B2 comparison script, as of this phase)."""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import Application, LocalPlanSite, Site
from app.pipeline.lapse_tracking import compute_lapse_status
from app.pipeline.phase_tracking import UNPHASED_LABEL
from app.policy.buyer_matching import PLANNING_DELIVERY, STRATEGIC_LAND, B2MatchingContext, build_control_appetite_facts
from app.reporting.acquisition_position import build_acquisition_position_facts


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
        allocation = session.get(LocalPlanSite, entity_id)
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

    # PLANNING_DELIVERY (site / phase / recent_permission / long_pending_application)
    site_id = entity_id
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

    acquisition_facts = build_acquisition_position_facts(session, applications)
    control_facts = build_control_appetite_facts(acquisition_facts)

    return B2MatchingContext(
        council_code=council_code,
        development_state=development_state,
        control_facts=control_facts,
        development_state_scope_verified=development_state_scope_verified,
    )
