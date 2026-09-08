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

COMPLETENESS (Gate 1 amendment, Product Owner review): the canonical
monitoring/onboarding universe this module builds must never silently
truncate, unlike a bounded UI feed - a new Buyer Profile must be
evaluated against the COMPLETE current opportunity universe, and
PropertyAIgent is expected to scale well past today's few hundred
candidates. build_current_opportunity_universe therefore takes no
correctness-affecting size limit at all:
  - Strategic land is fetched via genuine keyset pagination
    (_strategic_land_universe below) - `page_size` only bounds the cost
    of each individual database round-trip, never the total number of
    allocations returned; the loop continues until every matching
    allocation has been fetched, however many there are.
  - Planning/delivery reuses app.reporting.dashboard._approaching_lapse_
    cards/_undeveloped_phase_cards UNCHANGED, passing `limit=None` -
    both functions already fetch their ENTIRE underlying candidate
    population in an unbounded query and only ever slice their own
    already-complete, already-sorted output list at the very end
    (confirmed by inspection: neither query has a SQL-level LIMIT
    anywhere); Python's own slicing semantics make `some_list[:None]`
    return the complete list unchanged, so this reuses those two
    functions exactly as they already exist - no modification, no
    redesign - while genuinely disabling only the final truncation this
    module never wants.

GATE 1C ("Recent Permission Opportunity Candidate Detection") adds a
fourth detection route, recent_permission, filling the structural gap
Gate 1B measured: a site with exactly one granted application (or several,
but none yet forming a detected "phase") has NO route into the
opportunity universe at all for up to ~2.5 years, regardless of scale or
commercial relevance. The detector itself lives in app.reporting.
dashboard._recent_permission_cards, alongside its two siblings
(_approaching_lapse_cards/_undeveloped_phase_cards) - this module's own
_recent_permission_candidate_sites is a thin wrapper, never a second
implementation. RECENT_PERMISSION_WINDOW_MONTHS below is the evidence-
based window (12 months - see this gate's own implementation report for
the full marginal-value analysis across 6/12/18/24-month windows that
justified it) shared by both this module and that function, so the two
can never drift apart. A recent_permission card means ONLY "a qualifying
residential permission was granted within the window, and no delivery/
commencement evidence has been identified" - never that the site is for
sale, that the applicant owns it, or any claim about promoter/
housebuilder/ownership status (Gate 1C brief, Section 12/13 - Applicant
Intelligence is explicitly out of scope here).
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

# A pure batching parameter - bounds the size of each individual keyset-
# pagination page/query, never the total number of allocations returned
# (see _strategic_land_universe below, and this module's own "COMPLETENESS"
# docstring section). Safe to override in a test to exercise the pagination
# loop itself without needing thousands of real rows.
DEFAULT_STRATEGIC_LAND_PAGE_SIZE = 500

# Gate 1C - the evidence-based recency boundary for the recent_permission
# detector. A read-only comparison across 6/12/18/24-month windows against
# production data (see this gate's own implementation report) found the
# marginal STRONG_FIT signal (summed across all four pilot Buyer Profiles)
# rises sharply from 6 to 12 months (+5 STRONG_FIT for +44 candidates),
# rises only marginally from 12 to 18 months (+2 for +23), and adds ZERO
# further STRONG_FIT from 18 to 24 months (+0 for +21) - i.e. by 18-24
# months this detector is adding candidate volume with no further
# commercial signal, while 6 months would discard genuine, real STRONG_FIT
# results that 12 months captures. 12 months is therefore the narrowest
# boundary that does not sacrifice measured commercial signal - not an
# arbitrary anniversary of Gate 1B's own analytical cohort.
RECENT_PERMISSION_WINDOW_MONTHS = 12
_AVG_DAYS_PER_MONTH = 30.44

# Gate 1C, Section 7: a scheme already demonstrably being delivered must
# never become a recent_permission candidate merely because its decision
# is recent - reuses app.pipeline.lapse_tracking.compute_lapse_status's
# own build_status classification verbatim (never a second, competing
# build-status algorithm). "unknown" is deliberately NOT excluded here -
# see _recent_permission_candidate_sites' own docstring for why absence of
# commencement evidence must never be conflated with verified non-
# commencement.
_EXCLUDED_BUILD_STATUSES_FOR_RECENT_PERMISSION = ("underway", "partially_complete", "complete")


def strategic_land_opportunity_id(allocation_id: int) -> str:
    return f"strategic_land:allocation:{allocation_id}"


def planning_delivery_site_opportunity_id(site_id: int) -> str:
    return f"planning_delivery:site:{site_id}"


def planning_delivery_phase_opportunity_id(site_id: int, phase_code: str) -> str:
    return f"planning_delivery:phase:{site_id}:{phase_code}"


def planning_delivery_recent_permission_opportunity_id(site_id: int) -> str:
    return f"planning_delivery:recent_permission:{site_id}"


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


def _strategic_land_records_for_page(session, candidates: list[LocalPlanSite]) -> list[OpportunityRecord]:
    """The per-page processing step - identical logic to what a single,
    unpaginated pass used to do, just scoped to one page's worth of
    allocations at a time so each individual query stays bounded (Gate 1
    amendment, "batch/page opportunity candidates; keep individual
    queries/processing bounded")."""
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


def _strategic_land_universe(session, page_size: int) -> list[OpportunityRecord]:
    """Genuine keyset pagination - `page_size` bounds only the cost of
    each individual round-trip; this loop continues fetching pages,
    ordered by LocalPlanSite.id, until a page comes back with fewer than
    `page_size` rows (i.e. the true end of the candidate set), however
    many pages that takes. Unlike a single `LIMIT N` query, this can never
    silently drop an allocation beyond some fixed count - see this
    module's own "COMPLETENESS" docstring section."""
    records: list[OpportunityRecord] = []
    last_id = 0
    while True:
        page = session.execute(
            select(LocalPlanSite)
            .where(
                LocalPlanSite.matched_site_id.is_(None),
                LocalPlanSite.minimum_dwellings.is_not(None),
                LocalPlanSite.id > last_id,
            )
            .order_by(LocalPlanSite.id.asc())
            .limit(page_size)
        ).scalars().all()
        if not page:
            break
        records.extend(_strategic_land_records_for_page(session, page))
        last_id = page[-1].id
        if len(page) < page_size:
            break
    return records


def _recent_permission_candidate_sites(session, *, exclude_site_ids: set[int]) -> list[dict]:
    """Thin wrapper around app.reporting.dashboard._recent_permission_
    cards - the single canonical implementation of the Gate 1C detector,
    living alongside its two siblings (_approaching_lapse_cards/
    _undeveloped_phase_cards) for the same reason this module already
    reuses those two rather than re-deriving "granted"/"build status" a
    second time. `limit=None` for the same completeness reason this
    module's own docstring already explains for the other two detectors."""
    from app.reporting.dashboard import _recent_permission_cards

    return _recent_permission_cards(session, None, exclude_site_ids=frozenset(exclude_site_ids))


def _planning_delivery_universe(session) -> list[OpportunityRecord]:
    # Local import: avoids a circular import, exactly the same reason
    # app.reporting.opportunity_feed.build_opportunity_feed's own local
    # import of these two functions already exists - not a new pattern.
    from app.reporting.dashboard import _approaching_lapse_cards, _undeveloped_phase_cards

    # limit=None: both functions already fetch their ENTIRE underlying
    # candidate population in one unbounded query each and only slice
    # their own already-complete, already-sorted list at the very end
    # (`scored[:limit]` / `cards[:limit]` - confirmed by inspection, no
    # SQL-level LIMIT exists in either function). Python's own slicing
    # treats `some_list[:None]` as "the whole list" - this reuses both
    # functions completely unmodified while genuinely disabling only the
    # truncation this canonical module never wants (see this module's own
    # "COMPLETENESS" docstring section).
    lapse_cards = _approaching_lapse_cards(session, None)
    undeveloped_cards = _undeveloped_phase_cards(session, None)
    tagged = [(c, "site") for c in lapse_cards] + [(c, "phase") for c in undeveloped_cards]

    # Gate 1C - recent_permission never duplicates a site the two
    # detectors above already cover (see _recent_permission_candidate_
    # sites' own docstring for the precedence rule).
    already_covered_site_ids = {int(c["params"]["site_id"]) for c, _ in tagged}
    recent_permission_cards = _recent_permission_candidate_sites(session, exclude_site_ids=already_covered_site_ids)
    tagged += [(c, "recent_permission") for c in recent_permission_cards]

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
        elif kind == "phase":
            # card["id"] is "opp-phase-{site_id}-{phase_code}" - reuse the
            # existing construction's own trailing segment rather than
            # re-deriving a phase code a second, possibly-inconsistent way.
            phase_code = card["id"].rsplit("-", 1)[-1]
            opportunity_id = planning_delivery_phase_opportunity_id(site_id, phase_code)
            fingerprint_fields["phase_code"] = phase_code
        else:  # "recent_permission" (Gate 1C)
            opportunity_id = planning_delivery_recent_permission_opportunity_id(site_id)
            # The grant date itself is a STABLE fact (never a live
            # countdown, unlike a formatted "N days left" string) -
            # included so a genuinely different, later grant on the same
            # site (e.g. a fresh full permission superseding an earlier
            # one) registers as a material change, never merely the
            # passage of time. card["when"] is the same grant-date-derived
            # datetime _recent_permission_cards already built - reused,
            # not re-parsed a second way.
            fingerprint_fields["decision_date"] = card.get("when")

        records.append(OpportunityRecord(
            opportunity_id=opportunity_id,
            opportunity_type=PLANNING_DELIVERY,
            matching_facts=facts,
            fingerprint_fields=fingerprint_fields,
        ))
    return records


def build_current_opportunity_universe(session, *, page_size: int = DEFAULT_STRATEGIC_LAND_PAGE_SIZE) -> list[OpportunityRecord]:
    """The Gate 1 canonical opportunity read model - every current
    candidate the platform's existing detection functions already produce,
    each carrying a stable logical identity and a deterministic fingerprint
    fact set. ALWAYS complete - see this module's own "COMPLETENESS"
    docstring section; `page_size` only tunes the strategic-land
    pagination's own batch size and never truncates the result. Never
    persisted itself; app.reporting.opportunity_change and app.policy.
    buyer_profile_store's onboarding baseline are this function's only two
    callers this gate."""
    return _strategic_land_universe(session, page_size) + _planning_delivery_universe(session)
