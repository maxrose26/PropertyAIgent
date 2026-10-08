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

from dataclasses import dataclass, field

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


@dataclass(frozen=True)
class FamilyInputs:
    """The buyer-independent subject inputs of one read window: loaded ONCE, then evaluated for any number of buyers (the one-read principle)."""
    strategic: list
    lapse_raw: list
    undeveloped_raw: list
    recent_permission_raw: list
    long_pending_raw: list
    delivery: list
    residuals: dict = field(default_factory=dict)   # V8-B: {site_id: ResidualQualification} (R1/R2/R3), buyer-independent


def load_buyer_family_inputs(session, *, strategic_page_size: int = STRATEGIC_PAGE_SIZE, residual_evidence_provider=None) -> FamilyInputs:
    """The complete, unbounded, buyer-independent subject population (strategic cards + planning-delivery cards with their matching facts)."""
    from app.security.access import require_admitted
    require_admitted()
    strategic = _complete_strategic_cards(session, page_size=strategic_page_size)
    lapse_raw, undeveloped_raw, recent_permission_raw, long_pending_raw, delivery = _planning_delivery_cards(session, None)
    operative_by_site = _attach_planning_delivery_matching_facts(session, delivery)
    from app.reporting.residual_feed import build_site_residuals
    residuals = build_site_residuals(operative_by_site or {}, residual_evidence_provider)   # production evidence = containment only => R2/R3; R1 is dormant by evidence
    return FamilyInputs(strategic, lapse_raw, undeveloped_raw, recent_permission_raw, long_pending_raw, delivery, residuals)


def build_buyer_opportunity_families(session, buyer_key: str, limit: int = 6, *, memoise_context: bool = True,
                                     strategic_page_size: int = STRATEGIC_PAGE_SIZE, residual_evidence_provider=None) -> dict:
    """The complete buyer-family result: ``{"families": [OpportunityFamily...], "excluded_family_keys": (...), "counts": {...}, "buyer_key": ...}``.

    ``families`` are the top ``limit`` NON-excluded families, ordered by fit bucket then family key; each family's members carry their own
    feed card in ``FamilySubject.source`` (with ``buyer_fit``). Nothing is summed across subjects."""
    from app.security.access import require_admitted
    require_admitted()
    from app.policy.buyer_profile_store import get_buyer_profile_dataclass
    if get_buyer_profile_dataclass(session, buyer_key) is None:      # resolve the buyer BEFORE the full read: an unknown buyer fails cheaply, as it always did
        raise UnknownBuyerProfile(f"buyer {buyer_key!r} does not resolve to an active profile")
    inputs = load_buyer_family_inputs(session, strategic_page_size=strategic_page_size, residual_evidence_provider=residual_evidence_provider)
    return evaluate_buyer_families(session, buyer_key, inputs, limit, memoise_context=memoise_context)


def load_site_subject_inputs(session, site_id: int) -> FamilyInputs:
    """Reuse canonical delivery detectors bounded to one admitted site's records.

    Detail navigation never loads strategic allocations or the full opportunity
    universe. Default dashboard/family loading remains unchanged.
    """
    from app.security.access import require_admitted
    require_admitted()
    lapse, phases, recent, pending, delivery = _planning_delivery_cards(session, None, site_id=site_id)
    operative = _attach_planning_delivery_matching_facts(session, delivery)
    from app.reporting.residual_feed import build_site_residuals
    return FamilyInputs([], lapse, phases, recent, pending, delivery, build_site_residuals(operative or {}, None))


def _residual_subject_cards(evaluated: list, residuals: dict, profile, context_for) -> list:
    """One derived feed card per R1 qualification (never persisted). Parent facts = the site's lifecycle card facts; with none, the residual cannot be assessed and is skipped
    (fail closed: a residual without trusted parent facts is not a subject)."""
    from dataclasses import replace
    from app.policy.residual_fit import assess_residual_fit
    from app.reporting.residual_opportunity import LEVEL_R1
    lifecycle_prefixes = ("opp-lapse-", "opp-recent-permission-", "opp-long-pending-")
    parent_cards = {}
    for card in evaluated:
        if card["opportunity_type"] == PLANNING_DELIVERY and str(card.get("id", "")).startswith(lifecycle_prefixes):
            parent_cards.setdefault(int(card["params"]["site_id"]), card)
    out = []
    for site_id in sorted(residuals):
        q = residuals[site_id]
        parent_card = parent_cards.get(site_id)
        if q.level != LEVEL_R1 or parent_card is None:
            continue
        context = replace(context_for(PLANNING_DELIVERY, site_id), subject_phase_scope_key=None, subject_application_anchored=False)
        fit = assess_residual_fit(profile, parent_card["matching_facts"], q, context)
        digest = q.subject_id.rsplit(":", 1)[1]
        out.append({"id": f"opp-residual-{site_id}-{digest}", "opportunity_type": PLANNING_DELIVERY, "params": {"site_id": str(site_id)}, "title": parent_card.get("title"),
                    "subtitle": parent_card.get("subtitle"), "metrics": [], "tags": [], "page": parent_card.get("page"), "headline_reason": None,
                    "buyer_fit": fit, "count_assessment": q.residual_assessment, "residual": q, "residual_subject_id": q.subject_id,
                    "residual_evidence_fingerprint": q.evidence_fingerprint, "matching_facts": parent_card["matching_facts"]})
    return out


def evaluate_buyer_families(session, buyer_key: str, inputs: FamilyInputs, limit: int = 6, *, memoise_context: bool = True,
                            contexts: dict | None = None, include_excluded: bool = False, profile=None) -> dict:
    """Evaluate already-loaded inputs for one buyer (the body of build_buyer_opportunity_families, unchanged in behaviour).

    ``profile`` (default None = the buyer's stored mandate, resolved exactly as before) lets a read-only analysis tool evaluate an EXPLICIT policy object (used only for labelled counterfactual
    analysis; production behaviour never passes it).
    ``contexts`` may be a caller-owned dict shared across buyers: B2 contexts are buyer-independent (keyed by subject kind + anchor id only). ``include_excluded`` adds the
    terminally excluded families themselves under ``"excluded_families"`` (default off: the result shape is otherwise unchanged)."""
    from app.security.access import require_admitted
    require_admitted()
    from app.policy.buyer_matching_b2_context import (
        build_b2_context_for_planning_delivery,
        build_b2_context_for_strategic_land,
        evaluate_buyer_fit,
    )
    from app.policy.buyer_profile_store import get_buyer_profile_dataclass

    if profile is None:
        profile = get_buyer_profile_dataclass(session, buyer_key)
    if profile is None:
        raise UnknownBuyerProfile(f"buyer {buyer_key!r} does not resolve to an active profile")

    strategic, lapse_raw, undeveloped_raw = inputs.strategic, inputs.lapse_raw, inputs.undeveloped_raw
    recent_permission_raw, long_pending_raw, delivery = inputs.recent_permission_raw, inputs.long_pending_raw, inputs.delivery

    if contexts is None:
        contexts = {}  # request-scoped; dies with this call

    def _context(kind: str, anchor_id: int):
        key = (kind, anchor_id)
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
    for source_card in (*strategic, *delivery):
        card = dict(source_card)   # inputs are shared across buyers: never mutate them
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

    from app.reporting.residual_opportunity import LEVEL_R1, LEVEL_R2, PLANNING_R2_TEXT
    residuals = inputs.residuals or {}
    for card in evaluated:                                              # R2: investigation CONTEXT on the existing cards only - no subject, no id, no count, no fit
        q = residuals.get(int(card["params"]["site_id"])) if card["opportunity_type"] == PLANNING_DELIVERY else None
        if q is not None and q.level == LEVEL_R2:
            card["potential_residual"] = PLANNING_R2_TEXT
    residual_cards = _residual_subject_cards(evaluated, residuals, profile, _context)   # R1 ONLY: a derived FamilySubject per qualified residual
    evaluated.extend(residual_cards)
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
        "derived_subjects_r1": len(residual_cards),
        "investigation_contexts_r2": sum(1 for q in residuals.values() if q.level == LEVEL_R2),
    }
    from app.reporting.opportunity_route import derive_opportunity_route, route_counts
    result = {"families": shown, "excluded_family_keys": tuple(f.family_key for f in excluded), "counts": counts, "buyer_key": buyer_key,
              # additive, presentation-only: the opportunity ROUTE of each shown family's representative (never a rank, never an input to fit or ordering)
              "route_counts": route_counts(derive_opportunity_route(f.representative.source or {}).route for f in shown)}
    if include_excluded:
        result["excluded_families"] = excluded
    return result
