"""Stage 2.5B G3b Slice 2 (spec 025): buyer-dashboard FAMILY presentation - view models only, no Streamlit, no policy.

Turns the accepted ``build_buyer_opportunity_families`` result into plain, deterministic view models for the buyer dashboard. This module PRESENTS what
the family already contains; it never re-ranks subjects, never changes a buyer-fit classification, never infers a relationship (G2 is not consumed),
never sums or subtracts unit counts and never claims availability. Business logic stays here, out of the UI.

Phasing (product principle: evidenced phasing is acquisition-INVESTIGATION evidence, not availability): only CURRENT Level 1 is presented - the shared derived fact
(app.reporting.acquisition_phasing) says a genuine, granted, non-lapsed named phase exists - labelled "Phased delivery evidenced." Nothing more is
claimed. Level 2 (documented phasing without a child subject) is NOT presented: no accepted structured signal exists (spec 025, G3b Slice 2).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.pipeline.phase_tracking import UNPHASED_LABEL
from app.reporting.opportunity_families import OVERLAP_WARNING, SLOT_PHASE, STRATEGIC_LAND, FamilyInputError, OpportunityFamily

logger = logging.getLogger(__name__)

PHASING_CONTEXT = "Phased delivery evidenced."
PHASING_CONTEXT_CURRENTNESS_UNKNOWN = "Phase evidence identified — current status unverified."
RELATIONSHIP_NOTE = "Related opportunity subjects within this development."
POLICY_CAVEAT = "This existing-policy result does not verify AH count source or scope, final tenure terms or acquisition availability."
FAMILY_ERROR_MESSAGE = ("Acquisition-family results are temporarily unavailable for this buyer. "
                        "The issue has been logged for the operator; no other pages are affected.")

FIT_LABELS = {"STRONG_FIT": "Strong fit", "POSSIBLE_FIT": "Possible fit", "NOT_SUITABLE": "Not suitable"}

_LIFECYCLE_LABELS = (
    ("opp-lapse-", "Permission approaching its assumed review date"),
    ("opp-recent-permission-", "Recently granted permission"),
    ("opp-long-pending-", "Long-pending application"),
)


@dataclass(frozen=True)
class SubjectView:
    label: str
    scale: str | None                      # the subject's OWN count with its honest precision, or None (strategic cards use ``metrics``)
    fit_key: str                           # BuyerFitAssessment.classification (unchanged)
    fit_label: str
    investigative: bool
    reasons: tuple[str, ...]
    headline_reason: str | None
    signal_key: str | None                 # strategic allocations only (the existing signal) and its label
    signal_label: str | None
    metrics: tuple[tuple[str, str], ...]   # strategic allocations only (existing metric tiles)
    tags: tuple[str, ...]
    page: str | None
    params: dict
    route: str | None = None               # opportunity ROUTE (what kind of opportunity) - separate from fit and evidence; never a rank
    route_label: str | None = None
    route_caveat: str | None = None
    scale_basis: str | None = None         # strategic allocations only: the plan-stated, UNVERIFIED capacity wording


@dataclass(frozen=True)
class FamilyView:
    family_id: str                         # a widget key only; never displayed
    title: str
    subtitle: str
    is_strategic: bool
    best: SubjectView
    related: tuple[SubjectView, ...]
    phasing_context: str | None
    relationship_note: str | None
    overlap_warning: str | None
    caveat: str = POLICY_CAVEAT


@dataclass(frozen=True)
class FamilyFeedView:
    families: tuple[FamilyView, ...] = ()
    caption: str = ""
    subject_caption: str = ""
    error: str | None = None
    route_counts: tuple = ()               # ((route_key, count), ...) over the shown families' representatives
    route_caption: str = ""


def fit_label(fit: str, investigative: bool) -> str:
    if fit == "INSUFFICIENT_EVIDENCE":
        return "Investigate" if investigative else "Insufficient evidence"
    return FIT_LABELS.get(fit, fit.replace("_", " ").capitalize())


def _scale(card: dict) -> str | None:
    assessment = card.get("count_assessment")
    return assessment.label() if assessment is not None else None


def _subject_label(subject, card: dict) -> str:
    key = subject.subject_key
    if subject.domain == STRATEGIC_LAND:
        return card.get("title") or "Strategic land allocation"
    for prefix, label in _LIFECYCLE_LABELS:
        if key.startswith(prefix):
            return label
    code = card.get("phase_code")
    if code == UNPHASED_LABEL:
        return "Wider permission"
    assessment = card.get("count_assessment")
    if assessment is not None and assessment.scope_type == "phase" and assessment.scope_label:
        return str(assessment.scope_label)
    return f"Phase {code}" if code else "Phase"


def _subject_view(subject) -> SubjectView:
    from app.reporting.opportunity_route import derive_opportunity_route
    card = subject.source or {}
    route = derive_opportunity_route(card)
    fit = card["buyer_fit"]
    reasons = tuple(fit.matches[:2])
    if fit.classification == "INSUFFICIENT_EVIDENCE" and fit.is_investigative_exception and getattr(fit, "investigate", None):
        reasons = tuple(fit.investigate[:1])
    return SubjectView(
        label=_subject_label(subject, card), scale=None if subject.domain == STRATEGIC_LAND else (_scale(card) or "Unit count unverified"),
        fit_key=fit.classification, fit_label=fit_label(fit.classification, bool(fit.is_investigative_exception)),
        investigative=bool(fit.is_investigative_exception), reasons=reasons, headline_reason=card.get("headline_reason"),
        signal_key=card.get("signal") if subject.domain == STRATEGIC_LAND else None,
        signal_label=card.get("signal_label") if subject.domain == STRATEGIC_LAND else None,
        metrics=tuple(tuple(m) for m in (card.get("metrics") or ())) if subject.domain == STRATEGIC_LAND else (),
        tags=tuple(card.get("tags") or ()), page=card.get("page"), params=dict(card.get("params") or {}),
        route=route.route, route_label=route.label, route_caveat=route.caveat,
        scale_basis=(card.get("strategic_scale") or {}).get("display") if subject.domain == STRATEGIC_LAND else None)


def phasing_context(family: OpportunityFamily) -> str | None:
    """The BUYER-FACING phasing label. Two separate questions: (1) the EVIDENCE fact (shared, unchanged): CURRENT -> "Phased delivery evidenced."; PHASE_EVIDENCE_CURRENTNESS_UNKNOWN ->
    the weaker "Phase evidence identified — current status unverified."; historical-only, none, reserved documented, a missing fact and every strategic family -> no label; and (2) its
    acquisition RELEVANCE to this buyer (app.policy.buyer_matching.phasing_is_acquisition_relevant, carried on the card as ``acquisition_phasing_relevant``): the label shows only when
    some WIDER (non-self-phase) planning-delivery subject is above the buyer's discovery maximum on a total-units mandate. Below-minimum, in-range, affordable-unit-metric and
    self-phase-only families show no label; the underlying fact is untouched (phasing_evidenced still reports it)."""
    if family.family_key[0] == STRATEGIC_LAND:
        return None
    if not any((member.source or {}).get("acquisition_phasing_relevant") is True for member in family.members):
        return None
    from app.reporting.acquisition_phasing import phasing_state_of
    for member in family.members:
        state = phasing_state_of((member.source or {}).get("acquisition_phasing"))
        if state is not None:
            return {"CURRENT_EVIDENCED_PHASE": PHASING_CONTEXT, "PHASE_EVIDENCE_CURRENTNESS_UNKNOWN": PHASING_CONTEXT_CURRENTNESS_UNKNOWN}.get(state)
    return None


def phasing_evidenced(family: OpportunityFamily) -> bool:
    """The Slice 2 label consumes the SHARED derived fact (app.reporting.acquisition_phasing, attached to each planning-delivery card by the family feed): True only for
    CURRENT_EVIDENCED_PHASE (a genuine named phase with a substantive granted anchor that is not assumed-lapsed). Historical-only, none-identified, a missing fact and every strategic
    family are False. The rule lives only in that module - never duplicated here or in the matcher. The state describes the wider development, so it is identical for every member."""
    if family.family_key[0] == STRATEGIC_LAND:
        return False
    from app.reporting.acquisition_phasing import is_current_evidenced_phase
    for member in family.members:
        evidence = (member.source or {}).get("acquisition_phasing")
        if evidence is not None:
            return is_current_evidenced_phase(evidence)
    return False


def present_family(family: OpportunityFamily, site) -> FamilyView:
    best = _subject_view(family.representative)
    related = tuple(_subject_view(r.subject) for r in family.related)
    strategic = family.family_key[0] == STRATEGIC_LAND
    if strategic:
        card = family.representative.source
        title, subtitle = card.get("title") or "Strategic land allocation", card.get("subtitle") or ""
    elif site is not None:
        title, subtitle = site.display_address or f"Site {site.id}", site.council_code or ""
    else:  # no site row: fall back to the representative card's own title
        title, subtitle = (family.representative.source or {}).get("title") or "Development", (family.representative.source or {}).get("subtitle") or ""
    multi = len(family.members) > 1
    return FamilyView(
        family_id=f"{family.family_key[0]}-{family.family_key[1]}", title=title, subtitle=subtitle, is_strategic=strategic, best=best, related=related,
        phasing_context=phasing_context(family),
        relationship_note=RELATIONSHIP_NOTE if multi and not strategic else None,
        overlap_warning=OVERLAP_WARNING if multi else None)


def counts_captions(counts: dict) -> tuple[str, str]:
    shown, considered, excluded = counts["families_shown"], counts["families_considered"], counts["families_excluded_not_suitable"]
    more = considered - excluded - shown
    caption = (f"{shown} of {considered} development families shown · {excluded} excluded as not suitable for this buyer"
               + (f" · {more} more not shown" if more > 0 else "") + f" · {counts['subjects_considered']} acquisition subjects considered.")
    subjects = (f"Subject counts (not opportunities): {counts['strategic_land']} strategic land · {counts['approaching_lapse']} approaching lapse · "
                f"{counts['undeveloped_phase']} permission(s), commencement unverified · {counts['recent_permission']} recent permission · "
                f"{counts['long_pending_application']} long-pending application.")
    return caption, subjects


def route_counts_caption(counts: dict) -> str:
    """"of which: X consented · Y outline-consented · Z phase/plot · W strategic allocations" - counts by opportunity route; descriptive only (a route is not a rank)."""
    if not counts:
        return ""
    from app.reporting.opportunity_route import CONSENTED_SITE, OUTLINE_CONSENTED_SITE, PHASE_OR_PLOT, STRATEGIC_ALLOCATION, UNCLASSIFIED_PLANNING_ROUTE
    parts = [f"{counts.get(CONSENTED_SITE, 0)} consented", f"{counts.get(OUTLINE_CONSENTED_SITE, 0)} outline-consented", f"{counts.get(PHASE_OR_PLOT, 0)} phase/plot",
             f"{counts.get(STRATEGIC_ALLOCATION, 0)} strategic allocation(s)"]
    if counts.get(UNCLASSIFIED_PLANNING_ROUTE, 0):
        parts.append(f"{counts[UNCLASSIFIED_PLANNING_ROUTE]} planning (consent not established)")
    joined = " · ".join(parts)
    return f"Opportunity routes among the families shown: {joined}."


def present_family_result(result: dict, sites_by_id: dict) -> FamilyFeedView:
    views = tuple(present_family(f, sites_by_id.get(f.family_key[1]) if f.family_key[0] != STRATEGIC_LAND else None) for f in result["families"])
    caption, subject_caption = counts_captions(result["counts"])
    counts = result.get("route_counts") or {}
    return FamilyFeedView(families=views, caption=caption, subject_caption=subject_caption, route_counts=tuple(counts.items()), route_caption=route_counts_caption(counts))


def build_buyer_family_dashboard_view(session, buyer_key: str, limit: int = 6) -> FamilyFeedView:
    """Family construction + presentation for the buyer dashboard. A typed family-construction failure becomes an operator-safe error view: it is logged
    server-side, never shown with detail and NEVER replaced by the legacy buyer cards. Stage 1 access refusals and unexpected errors propagate."""
    from sqlalchemy import select

    from app.db.models import Site
    from app.reporting.buyer_family_feed import MissingFamilySubjectMatchingFacts, UnknownBuyerProfile, build_buyer_opportunity_families
    try:
        result = build_buyer_opportunity_families(session, buyer_key, limit)
    except (FamilyInputError, MissingFamilySubjectMatchingFacts, UnknownBuyerProfile):
        logger.exception("buyer family construction failed closed")
        return FamilyFeedView(error=FAMILY_ERROR_MESSAGE)
    site_ids = {f.family_key[1] for f in result["families"] if f.family_key[0] != STRATEGIC_LAND}
    sites = {s.id: s for s in session.execute(select(Site).where(Site.id.in_(site_ids))).scalars()} if site_ids else {}
    return present_family_result(result, sites)
