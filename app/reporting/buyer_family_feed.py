"""Stage 2.5B G3b Slice 1 (spec 025): the complete buyer-FAMILY feed data model. Additive, not user-facing.

What it answers: "what is the best currently-evidenced acquisition subject within each planning family, for this buyer?" - without being
distorted by the legacy bounded candidate pool (``max(8 x limit, 40)``), which can omit family members and phase-only families, pick the
wrong representative, change family fit or terminal exclusion and change the top-N.

Pipeline (Option A - complete/unbounded, approved for the pilot scale):

    COMPLETE subject population  ->  buyer fit for EVERY subject  ->  G3a grouping/representative/order  ->  limit (families)

* planning-delivery: the four existing detectors with ``limit=None`` (they already read their whole population; the exclusion sets used by the
  canonical precedence are therefore complete too), through the SAME card reshaping/matching-facts steps as the legacy feed;
* strategic: a keyset-paged read of the same candidate population (matched_site_id IS NULL, minimum_dwellings NOT NULL), then the feed's own
  signal eligibility + card shaping across ALL pages (the capacity-ordered SQL LIMIT is gone; eligibility is not);
* buyer fit: the existing v6 matcher via ``evaluate_buyer_fit`` - no new semantics, no model/paid calls;
* grouping/representative/related roles/family order: ``app.reporting.opportunity_families.group_into_families`` (fit bucket, then family key);
* integrity violations raise (typed ``FamilyInputError`` subclasses, ``UnknownBuyerProfile``) - there is NO silent fallback to the legacy cards.

Not here (by decision): any G2 relationship/label/tie-break, units summation, dashboard/UI, schema, fingerprints, monitoring, policy version.
Request-scoped B2-context memoisation only (buyer + site_id / buyer + allocation_id); MatchingFacts are never shared across subjects.
"""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import LocalPlanSite
from app.reporting.opportunity_families import group_into_families, subject_from_feed_card
from app.reporting.opportunity_feed import (
    PLANNING_DELIVERY,
    STRATEGIC_LAND,
    _attach_planning_delivery_matching_facts,
    _planning_delivery_cards,
    _strategic_cards_for_candidates,
)

STRATEGIC_PAGE_SIZE = 500  # each page's cost only; the loop continues to the true end of the candidate set


class MissingFamilySubjectMatchingFacts(ValueError):
    """An otherwise eligible subject has no matching facts, so it cannot be evaluated. Omitting it could change the representative, the
    family fit, the related subjects, terminal exclusion and the top-N, so family mode FAILS CLOSED (no skip, no partial family, no legacy
    fallback). Carries only non-sensitive identity: the feed-card id and subject type."""

    def __init__(self, subject_id: str, subject_type: str):
        self.subject_id, self.subject_type = subject_id, subject_type
        super().__init__(f"eligible {subject_type} subject {subject_id!r} has no matching facts; family result would be partial")


class UnknownBuyerProfile(ValueError):
    """The buyer key does not resolve to an active profile. Family mode never degrades to an empty/legacy result."""


def _complete_strategic_cards(session, *, page_size: int = STRATEGIC_PAGE_SIZE) -> list[dict]:
    """Every eligible strategic card: keyset pagination by id (never a LIMIT that could drop an allocation), the unchanged feed eligibility."""
    cards: list[dict] = []
    last_id = 0
    while True:
        page = session.execute(
            select(LocalPlanSite)
            .where(LocalPlanSite.matched_site_id.is_(None), LocalPlanSite.minimum_dwellings.is_not(None), LocalPlanSite.id > last_id)
            .order_by(LocalPlanSite.id.asc())
            .limit(page_size)
        ).scalars().all()
        if not page:
            break
        cards.extend(_strategic_cards_for_candidates(session, page, None))
        last_id = page[-1].id
        if len(page) < page_size:
            break
    return cards


def build_buyer_opportunity_families(session, buyer_key: str, limit: int = 6, *, memoise_context: bool = True,
                                     strategic_page_size: int = STRATEGIC_PAGE_SIZE) -> dict:
    """The complete buyer-family result: ``{"families": [OpportunityFamily...], "excluded_family_keys": (...), "counts": {...}, "buyer_key": ...}``.

    ``families`` are the top ``limit`` NON-excluded families, ordered by fit bucket then family key; each family's members carry their own
    feed card in ``FamilySubject.source`` (with ``buyer_fit``). Nothing is summed across subjects."""
    from app.security.access import require_admitted
    require_admitted()
    from app.policy.buyer_matching_b2_context import (
        build_b2_context_for_planning_delivery,
        build_b2_context_for_strategic_land,
        evaluate_buyer_fit,
    )
    from app.policy.buyer_profile_store import get_buyer_profile_dataclass

    profile = get_buyer_profile_dataclass(session, buyer_key)
    if profile is None:
        raise UnknownBuyerProfile(f"buyer {buyer_key!r} does not resolve to an active profile")

    strategic = _complete_strategic_cards(session, page_size=strategic_page_size)
    lapse_raw, undeveloped_raw, recent_permission_raw, long_pending_raw, delivery = _planning_delivery_cards(session, None)
    _attach_planning_delivery_matching_facts(session, delivery)

    contexts: dict[tuple, object] = {}  # request-scoped; dies with this call

    def _context(kind: str, anchor_id: int):
        key = (buyer_key, kind, anchor_id)
        if memoise_context and key in contexts:
            return contexts[key]
        if kind == STRATEGIC_LAND:
            context = build_b2_context_for_strategic_land(session, anchor_id)
        else:
            context = build_b2_context_for_planning_delivery(session, anchor_id)   # the SITE-level context; the subject-scope guard is applied per subject below
        if memoise_context:
            contexts[key] = context
        return context

    evaluated: list[dict] = []
    for card in (*strategic, *delivery):
        facts = card.get("matching_facts")
        if facts is None:
            raise MissingFamilySubjectMatchingFacts(str(card.get("id")), str(card.get("opportunity_type")))   # never skipped
        if card["opportunity_type"] == STRATEGIC_LAND:
            context = _context(STRATEGIC_LAND, int(card["params"]["allocation_id"]))
        else:
            from dataclasses import replace
            from app.reporting.acquisition_phasing import subject_scope_for_feed_card
            phase_scope_key, application_anchored = subject_scope_for_feed_card(card)
            context = replace(_context(PLANNING_DELIVERY, int(card["params"]["site_id"])),
                              subject_phase_scope_key=phase_scope_key, subject_application_anchored=application_anchored)
            card["acquisition_phasing"] = context.acquisition_phasing   # the single shared fact the Slice 2 presentation label consumes
            from app.policy.buyer_matching import phasing_is_acquisition_relevant
            card["acquisition_phasing_relevant"] = phasing_is_acquisition_relevant(profile, facts, context)   # evidence vs relevance: whether the label is shown
        card["buyer_fit"] = evaluate_buyer_fit(session, profile, facts, context=context)
        evaluated.append(card)

    subjects = [subject_from_feed_card(card) for card in evaluated]   # malformed identity raises
    families = group_into_families(subjects)                          # integrity violations raise; no fallback
    excluded = [f for f in families if f.is_terminally_excluded]
    candidates = [f for f in families if not f.is_terminally_excluded]
    shown = candidates[:limit]                                         # the limit applies to FAMILIES, after everything else

    counts = {
        "families_considered": len(families),
        "families_shown": len(shown),
        "families_excluded_not_suitable": len(excluded),
        "subjects_considered": len(subjects),
        "strategic_land": len(strategic),
        "approaching_lapse": len(lapse_raw),
        "undeveloped_phase": len(undeveloped_raw),
        "recent_permission": len(recent_permission_raw),
        "long_pending_application": len(long_pending_raw),
    }
    return {"families": shown, "excluded_family_keys": tuple(f.family_key for f in excluded), "counts": counts, "buyer_key": buyer_key}
