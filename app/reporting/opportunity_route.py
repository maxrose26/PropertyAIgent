"""Stage 2.5B final slice: the OPPORTUNITY ROUTE - "what kind of acquisition opportunity is this?" - derived PURELY from facts the architecture already holds.

THREE DIMENSIONS stay separate and are never collapsed into one score:
  A. OPPORTUNITY ROUTE (this module)          - the kind of acquisition opportunity.
  B. BUYER FIT (assess_buyer_fit)             - STRONG_FIT / POSSIBLE_FIT / INSUFFICIENT_EVIDENCE / NOT_SUITABLE + the investigative flag.
  C. EVIDENCE / READINESS                      - how strong the underlying evidence is (this slice only states the basis honestly; no new score).

OPPORTUNITY ROUTE IS NOT A RANK. A strategic allocation is not automatically weaker or stronger than a consented site. The route never affects buyer fit, ordering, family or subject
identity, fingerprints, monitoring or phasing evidence: it is a deterministic, presentation-derived label (no schema, no persistence, no model).

Routes (and the existing deterministic evidence each reads):
  STRATEGIC_ALLOCATION       a strategic-land card (a Local Plan allocation).
  PHASE_OR_PLOT              a planning-delivery subject scoped to a NAMED phase or a material plot (phase_code other than the unphased bucket); subtype PHASE or PLOT (a plot code is
                             prefixed ``plot_`` by the existing scope resolution). A plot is a valid subject but is NOT phasing evidence; the two are kept distinct here.
  OUTLINE_CONSENTED_SITE     a planning-delivery wider subject whose operative CONSENTED position (scheme_reconciliation.build_operative_planning_facts) is an OUTLINE permission.
  CONSENTED_SITE             the same, where the consented position is full / hybrid / reserved matters / other substantive. Wording is deliberately "consented site" with a commencement
                             caveat: the architecture holds no positive "development not started" fact (absence of commencement evidence is an evidence gap, never confirmed non-commencement).
  UNCLASSIFIED_PLANNING_ROUTE  fail-closed neutral value: a planning subject with no resolved consented position (e.g. a pending application) or no role evidence.
Production-route 5 (promotable land) is Stage 2.5C and is NOT represented here.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from app.pipeline.phase_tracking import UNPHASED_LABEL

STRATEGIC_ALLOCATION = "STRATEGIC_ALLOCATION"
PHASE_OR_PLOT = "PHASE_OR_PLOT"
OUTLINE_CONSENTED_SITE = "OUTLINE_CONSENTED_SITE"
CONSENTED_SITE = "CONSENTED_SITE"
UNCLASSIFIED_PLANNING_ROUTE = "UNCLASSIFIED_PLANNING_ROUTE"
RESIDUAL_OPPORTUNITY = "RESIDUAL_OPPORTUNITY"      # V8-B: an R1 derived residual subject ONLY (R2 is investigation context, never a route)
ROUTES = (CONSENTED_SITE, OUTLINE_CONSENTED_SITE, PHASE_OR_PLOT, RESIDUAL_OPPORTUNITY, STRATEGIC_ALLOCATION)
ALL_ROUTE_KEYS = (*ROUTES, UNCLASSIFIED_PLANNING_ROUTE)
SUBTYPE_PHASE, SUBTYPE_PLOT = "PHASE", "PLOT"

ROUTE_LABELS = {
    CONSENTED_SITE: "Consented site",
    OUTLINE_CONSENTED_SITE: "Outline-consented site",
    PHASE_OR_PLOT: "Phase / plot opportunity",
    RESIDUAL_OPPORTUNITY: "Residual opportunity (derived)",
    STRATEGIC_ALLOCATION: "Strategic allocation",
    UNCLASSIFIED_PLANNING_ROUTE: "Planning opportunity (consent not established)",
}
ROUTE_CAVEATS = {
    CONSENTED_SITE: "Planning permission is granted; whether development has started is not verified.",
    OUTLINE_CONSENTED_SITE: "Outline permission only: further approvals are required; whether development has started is not verified.",
    PHASE_OR_PLOT: "A specific phase or plot within a wider development; a plot alone does not establish formal phasing, and ownership and sale position are not established.",
    STRATEGIC_ALLOCATION: "Plan-stated capacity, unverified; planning permission, deliverability, ownership and sale position are not established.",
    UNCLASSIFIED_PLANNING_ROUTE: "A consented position has not been established for this opportunity.",
    RESIDUAL_OPPORTUNITY: "Derived (apparent) residual planning capacity; availability, ownership, parcel geometry and independent deliverability are unverified.",
}
_FULL_CONSENT_ROLES = frozenset({"full", "hybrid", "reserved_matters", "other_substantive"})
_OUTLINE_ROLE = "outline"


@dataclass(frozen=True)
class OpportunityRoute:
    route: str
    subtype: str | None
    label: str
    caveat: str


def derive_opportunity_route(card: dict) -> OpportunityRoute:
    """Pure and deterministic. ``card`` is an opportunity-feed card; ``consent_role`` (the planning role of the operative CONSENTED application) is attached to planning-delivery cards by the
    feed's existing batched fact pass. Anything not positively established falls to the neutral UNCLASSIFIED_PLANNING_ROUTE."""
    if card.get("opportunity_type") == "strategic_land":
        return _make(STRATEGIC_ALLOCATION)
    if card.get("residual_subject_id"):
        return _make(RESIDUAL_OPPORTUNITY)
    phase_code = card.get("phase_code")
    if phase_code and phase_code != UNPHASED_LABEL:
        return _make(PHASE_OR_PLOT, SUBTYPE_PLOT if str(phase_code).startswith("plot_") else SUBTYPE_PHASE)
    role = card.get("consent_role")
    if role == _OUTLINE_ROLE:
        return _make(OUTLINE_CONSENTED_SITE)
    if role in _FULL_CONSENT_ROLES:
        return _make(CONSENTED_SITE)
    return _make(UNCLASSIFIED_PLANNING_ROUTE)


def _make(route: str, subtype: str | None = None) -> OpportunityRoute:
    label = ROUTE_LABELS[route] + (f" ({subtype.lower()})" if subtype else "")
    return OpportunityRoute(route=route, subtype=subtype, label=label, caveat=ROUTE_CAVEATS[route])


def route_counts(routes) -> dict:
    """Counts by route over any iterable of route values (every key always present, so a count of zero is stated rather than omitted). Never summed into a score."""
    counted = Counter(routes)
    return {key: counted.get(key, 0) for key in ALL_ROUTE_KEYS}
