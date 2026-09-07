"""Gate 1 (Acquisition Monitoring Substrate) - the formalised, reusable
CURRENT opportunity universe: stable logical identity + a deterministic
fingerprint fact set for every candidate the platform's EXISTING
opportunity-detection functions already produce.

Deliberately NOT a new intelligence engine and NOT a persisted Opportunity
table (per the approved Workspace & Ownership Architecture Investigation -
"Opportunities should remain read models, not persisted rows"). Every fact
here is read straight from the same trusted functions app.reporting.
opportunity_feed/dashboard already call for the Dashboard's own live feed:

    app.reporting.allocation_development_coverage.build_allocation_
    development_coverage (strategic land)
    app.reporting.dashboard._approaching_lapse_cards / _undeveloped_
    phase_cards (planning/delivery) - the same private-name cross-module
    reuse app.reporting.opportunity_feed.build_opportunity_feed itself
    already relies on, not a new pattern introduced here
    app.policy.buyer_matching.build_strategic_land_matching_facts /
    build_planning_delivery_matching_facts (buyer-matching facts, reused
    verbatim - never re-derived a second time)

This module adds exactly two things on top: a STABLE LOGICAL IDENTITY
string per opportunity (formalising the same convention app.reporting.
opportunity_feed's own card "id" field already uses informally), and a
DETERMINISTIC FINGERPRINT fact set (see compute_opportunity_fingerprint)
built mostly from MatchingFacts' own fields - by definition the
decision-relevant facts the buyer-matching engine itself cares about -
plus a small number of fields MatchingFacts doesn't carry (Green Belt
status, site area, ownership-evidence count, the STABLE lapse/build facts
- deliberately never the live "N days left" countdown, which would change
every single day and falsely register as a material change; see
_planning_delivery_universe's own comment).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import Application, ControlRelationship, LocalPlan, LocalPlanSite, Site
from app.pipeline.lapse_tracking import compute_lapse_status
from app.policy.buyer_matching import (
    MatchingFacts,
    build_planning_delivery_matching_facts,
    build_strategic_land_matching_facts,
)
from app.reporting.allocation_development_coverage import build_allocation_development_coverage
from app.reporting.allocation_discovery import PLAN_STATUS_META
from app.reporting.opportunity_feed import PLANNING_DELIVERY, STRATEGIC_LAND
from app.ui.common import pick_representative_application

# A real, adjustable overfetch bound (mirrors app.reporting.opportunity_
# feed._strategic_land_cards' own `limit(max(limit*3,12))` convention) -
# NOT a full unbounded table scan, but generous enough to cover the
# entire current opportunity universe (255 as of this gate - see the
# Gate 1 implementation report) many times over. Raise this, or make it a
# real paging loop, only once repository evidence shows the universe has
# genuinely grown past it - never pre-optimised speculatively.
DEFAULT_UNIVERSE_POOL_LIMIT = 2000


def strategic_land_opportunity_id(allocation_id: int) -> str:
    return f"strategic_land:allocation:{allocation_id}"


def planning_delivery_site_opportunity_id(site_id: int) -> str:
    return f"planning_delivery:site:{site_id}"


def planning_delivery_phase_opportunity_id(site_id: int, phase_code: str) -> str:
    return f"planning_delivery:phase:{site_id}:{phase_code}"


@dataclass(frozen=True)
class OpportunityRecord:
    """One current opportunity candidate - identity, the same MatchingFacts
    app.policy.buyer_matching.assess_buyer_fit already consumes (reused
    verbatim, never recomputed a second way), and the raw fingerprint fact
    dict compute_opportunity_fingerprint hashes. Never persisted itself -
    rebuilt fresh on every call to build_current_opportunity_universe."""

    opportunity_id: str
    opportunity_type: str  # STRATEGIC_LAND | PLANNING_DELIVERY
    matching_facts: MatchingFacts
    fingerprint_fields: dict


def compute_opportunity_fingerprint(fingerprint_fields: dict) -> str:
    """sha256 over the fingerprint_fields dict only - mirrors app.
    reporting.allocation_intelligence_summary.compute_context_fingerprint's
    own convention exactly (sorted keys, default=str so a date/None/etc.
    always serialises the same way). Callers own deciding what belongs in
    fingerprint_fields; this function never inspects or filters it -
    see _strategic_land_universe/_planning_delivery_universe below for
    the actual field selection and, just as importantly, what is
    deliberately excluded as noise."""
    canonical = json.dumps(fingerprint_fields, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _strategic_land_universe(session, pool_limit: int) -> list[OpportunityRecord]:
    candidates = session.execute(
        select(LocalPlanSite).where(LocalPlanSite.matched_site_id.is_(None), LocalPlanSite.minimum_dwellings.is_not(None))
        .order_by(LocalPlanSite.id.asc()).limit(pool_limit)
    ).scalars().all()
    if not candidates:
        return []

    coverage_by_id = build_allocation_development_coverage(session, candidates)
    plan_ids = {a.local_plan_id for a in candidates if a.local_plan_id}
    plans_by_id = (
        {p.id: p for p in session.execute(select(LocalPlan).where(LocalPlan.id.in_(plan_ids))).scalars()}
        if plan_ids else {}
    )

    records: list[OpportunityRecord] = []
    for a in candidates:
        result = coverage_by_id.get(a.id)
        if result is None:
            continue
        plan = plans_by_id.get(a.local_plan_id)
        plan_meta = PLAN_STATUS_META.get(plan.status if plan else None, PLAN_STATUS_META[None])
        facts = build_strategic_land_matching_facts(a, result["coverage"], result["phasing"])

        fingerprint_fields = {
            "opportunity_type": STRATEGIC_LAND,
            "unit_count": facts.unit_count,
            "development_type_raw": facts.development_type_raw,
            "is_specialist_development": facts.is_specialist_development,
            "planning_state": facts.planning_state,
            "has_identified_planning_activity": facts.has_identified_planning_activity,
            "has_phasing_evidence": facts.has_phasing_evidence,
            "matched_to_site": facts.matched_to_site,
            "plan_status_bucket": plan_meta["bucket"],
            # Real, decision-relevant facts a future re-extraction could
            # genuinely change (Gate 4A capacity/Green Belt evidence) -
            # deliberately EXCLUDES a.updated_at/source_document_url/
            # source_page, which describe when/where the fact was read
            # from, never what the fact itself is (same reasoning
            # compute_context_fingerprint's own docstring already applies
            # to last_checked/source_document_url there).
            "site_area_hectares": a.site_area_hectares,
            "green_belt_status": a.green_belt_status,
        }
        records.append(OpportunityRecord(
            opportunity_id=strategic_land_opportunity_id(a.id),
            opportunity_type=STRATEGIC_LAND,
            matching_facts=facts,
            fingerprint_fields=fingerprint_fields,
        ))
    return records


def _planning_delivery_universe(session, pool_limit: int) -> list[OpportunityRecord]:
    # Local import: avoids a circular import, exactly the same reason
    # app.reporting.opportunity_feed.build_opportunity_feed's own local
    # import of these two functions already exists - not a new pattern.
    from app.reporting.dashboard import _approaching_lapse_cards, _undeveloped_phase_cards

    lapse_cards = _approaching_lapse_cards(session, pool_limit)
    undeveloped_cards = _undeveloped_phase_cards(session, pool_limit)
    tagged = [(c, "site") for c in lapse_cards] + [(c, "phase") for c in undeveloped_cards]
    if not tagged:
        return []

    site_ids = {int(c["params"]["site_id"]) for c, _ in tagged}
    apps = session.execute(
        select(Application).where(Application.site_id.in_(site_ids))
        .options(selectinload(Application.scheme_intelligence))
    ).scalars().all()
    apps_by_site: dict[int, list[Application]] = {}
    for app in apps:
        apps_by_site.setdefault(app.site_id, []).append(app)
    sites_by_id = {s.id: s for s in session.execute(select(Site).where(Site.id.in_(site_ids))).scalars()}

    # One batched ownership-evidence count per site - the same query shape
    # already proven in the Persistent Buyer Acquisition Agents
    # investigation's own read-only export script, formalised here as real
    # application code. A raw count, never a claim about WHO owns
    # anything - ControlRelationship's own semantic invariant (never
    # current ownership/exclusivity) is preserved; this only measures
    # "has the evidence picture for this site changed at all".
    control_rows = session.execute(
        select(ControlRelationship).where(ControlRelationship.site_id.in_(site_ids))
    ).scalars().all()
    ownership_count_by_site: dict[int, int] = {}
    for cr in control_rows:
        if cr.site_id is not None:
            ownership_count_by_site[cr.site_id] = ownership_count_by_site.get(cr.site_id, 0) + 1

    records: list[OpportunityRecord] = []
    for card, kind in tagged:
        site_id = int(card["params"]["site_id"])
        site = sites_by_id.get(site_id)
        if site is None:
            continue
        site_apps = apps_by_site.get(site_id, [])
        rep = pick_representative_application(site_apps)
        si = rep.scheme_intelligence if rep else None
        facts = build_planning_delivery_matching_facts(si)

        # compute_lapse_status is pure Python over already-fetched
        # Application rows (no further query) - recomputed here rather
        # than re-parsed out of _approaching_lapse_cards/_undeveloped_
        # phase_cards' own already-formatted card text, so the fingerprint
        # gets the STABLE underlying facts (deadline date, lapse/build
        # status) rather than that formatted "N days left" countdown
        # string, which changes every single day purely with the passage
        # of time and would otherwise register as a false material change
        # on every routine check.
        lapse_result = compute_lapse_status(site_apps, site)

        fingerprint_fields = {
            "opportunity_type": PLANNING_DELIVERY,
            "unit_count": facts.unit_count,
            "affordable_unit_count": facts.affordable_unit_count,
            "development_type_raw": facts.development_type_raw,
            "is_specialist_development": facts.is_specialist_development,
            "decision": rep.decision if rep else None,
            "status": rep.status if rep else None,
            "lapse_status": lapse_result.get("status"),
            "deadline": lapse_result.get("deadline"),
            "build_status": lapse_result.get("build_status"),
            "ownership_evidence_count": ownership_count_by_site.get(site_id, 0),
        }

        if kind == "site":
            opportunity_id = planning_delivery_site_opportunity_id(site_id)
        else:
            # card["id"] is "opp-phase-{site_id}-{phase_code}" - reuse the
            # existing construction's own trailing segment rather than
            # re-deriving a phase code a second, possibly-inconsistent way.
            phase_code = card["id"].rsplit("-", 1)[-1]
            opportunity_id = planning_delivery_phase_opportunity_id(site_id, phase_code)
            fingerprint_fields["phase_code"] = phase_code

        records.append(OpportunityRecord(
            opportunity_id=opportunity_id,
            opportunity_type=PLANNING_DELIVERY,
            matching_facts=facts,
            fingerprint_fields=fingerprint_fields,
        ))
    return records


def build_current_opportunity_universe(session, *, pool_limit: int = DEFAULT_UNIVERSE_POOL_LIMIT) -> list[OpportunityRecord]:
    """The Gate 1 canonical opportunity read model - every current
    candidate the platform's existing detection functions already produce,
    each carrying a stable logical identity and a deterministic fingerprint
    fact set. Never persisted itself; app.reporting.opportunity_change and
    app.policy.buyer_profile_store's onboarding baseline are this
    function's only two callers this gate."""
    return _strategic_land_universe(session, pool_limit) + _planning_delivery_universe(session, pool_limit)
