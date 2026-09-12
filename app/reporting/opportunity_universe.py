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
dashboard._recent_permission_cards, alongside its siblings
(_approaching_lapse_cards/_undeveloped_phase_cards/_long_pending_
application_cards) - this module's own wrapper functions are thin, never
a second implementation. A recent_permission card means ONLY "a
qualifying residential permission was granted within the window, and no
delivery/commencement evidence has been identified" - never that the site
is for sale, that the applicant owns it, or any claim about promoter/
housebuilder/ownership status (Applicant Intelligence is Gate 2A, out of
scope here).

GATE 1C AMENDMENT (Product Owner review, revised planning opportunity
lifecycle) adds a FIFTH detection route, long_pending_application, and
changes RECENT_PERMISSION_WINDOW_MONTHS from an original 12 down to 3 -
see each constant's own comment below for the evidence behind both
numbers. The revised lifecycle these two routes together represent:

    application submitted -> normal determination period
        -> still pending >= 6 calendar months -> LONG_PENDING_APPLICATION
        -> (decision granted) -> first 3 calendar months after grant
            -> RECENT_PERMISSION
        -> ages beyond 3 months -> no automatic signal
        -> (later reaches the existing lapse threshold) -> APPROACHING_LAPSE

CALENDAR-MONTH SEMANTICS (Gate 1C amendment, Section 5): both new windows
are evaluated in calendar months (add_calendar_months below), never an
approximated fixed day-count (e.g. "3*30 days") - a boundary date is
computed once (submitted_date/grant_date + N calendar months) and compared
directly against the current evaluation date, so a 31-day month is treated
identically to a 28-day one, exactly as a human reading "6 months" would
expect. Mirrors app.pipeline.lapse_tracking's own existing "add N years,
clamp on a Feb-29 overflow" pattern (COMMENCEMENT_YEARS) applied to months
instead of years - not a new interpretation of "N months from now", the
first one this codebase has needed.

TIME-DRIVEN ELIGIBILITY (Gate 1C amendment, Section 14/16): eligibility
for both new routes is recalculated from stable dates (submitted_date/
grant_date, never re-derived) against THE CURRENT EVALUATION DATE every
time build_current_opportunity_universe runs - never a fixed day-count
"days_pending"/"days_since_grant" value baked into the fingerprint (which
would change every single day and falsely register as a material change,
exactly the mistake this module's own fingerprints have always avoided
for lapse "days left"). This is deliberately NOT a cadence assumption -
core opportunity logic contains no reference to "Monday" or any schedule;
it produces the objectively correct universe whenever invoked, whether
that is daily, weekly, or on any other operator-chosen cadence (see
scripts.sync_opportunity_monitoring's own docstring for the recommended
weekly production cadence - a purely operational decision, never encoded
here).
"""
from __future__ import annotations

import calendar
import datetime as dt
import hashlib
import json
from dataclasses import dataclass, replace

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import Application, ControlRelationship, LocalPlan, LocalPlanSite, Site
from app.pipeline.lapse_tracking import compute_lapse_status
from app.pipeline.phase_tracking import UNPHASED_LABEL
from app.policy.buyer_matching import (
    MatchingFacts,
    build_planning_delivery_matching_facts,
    build_strategic_land_matching_facts,
    resolve_operative_planning_state,
)
from app.reporting.allocation_development_coverage import build_allocation_development_coverage
from app.reporting.allocation_discovery import PLAN_STATUS_META
from app.reporting.opportunity_feed import PLANNING_DELIVERY, STRATEGIC_LAND
from app.reporting.scheme_reconciliation import build_operative_planning_facts
from app.ui.common import pick_representative_application

# A pure batching parameter - bounds the size of each individual keyset-
# pagination page/query, never the total number of allocations returned
# (see _strategic_land_universe below, and this module's own "COMPLETENESS"
# docstring section). Safe to override in a test to exercise the pagination
# loop itself without needing thousands of real rows.
DEFAULT_STRATEGIC_LAND_PAGE_SIZE = 500


def add_calendar_months(d: dt.date, months: int) -> dt.date:
    """`d` plus exactly `months` CALENDAR months - e.g. 31 Jan + 1 month =
    28/29 Feb (clamped to the target month's own last day, never rolling
    over into March), 30 Jun + 3 months = 30 Sep. The one calendar-month
    arithmetic helper in this codebase (Gate 1C amendment, Section 5) -
    every RECENT_PERMISSION/LONG_PENDING_APPLICATION boundary goes through
    this, never a `days=N*30`-style approximation."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


# Gate 1C amendment - the Product Owner's revised RECENT_PERMISSION window.
# The original Gate 1C implementation (12 months) is superseded: the
# approved commercial model is now a short, immediate post-grant
# acquisition window (Section 4) - a permission stops being a
# RECENT_PERMISSION candidate once it ages beyond 3 CALENDAR months,
# specifically to represent "before the scheme progresses into delivery or
# other commercial arrangements crystallise", not the broader "hasn't yet
# been picked up by a later signal" gap-filling role the original 12-month
# figure was evidence-optimised for. Qualifies while
# `today < add_calendar_months(grant_date, 3)` - i.e. the boundary date
# itself (exactly 3 calendar months after grant) is the first date this NO
# LONGER qualifies, matching the brief's own "ages BEYOND 3 months -> no
# automatic signal" wording (see tests/test_recent_permission_
# opportunities.py's own test_exact_calendar_month_boundary_is_
# deterministic_and_exclusive for the exact tested boundary).
RECENT_PERMISSION_WINDOW_MONTHS = 3

# Gate 1C amendment, Section 8 - the Product Owner's approved V1 threshold
# for the new LONG_PENDING_APPLICATION route: a qualifying residential
# application still awaiting determination at least 6 calendar months
# after it was submitted. Qualifies while
# `today >= add_calendar_months(submitted_date, 6)` - i.e. the boundary
# date itself (exactly 6 calendar months after submission) is the FIRST
# date this candidate becomes eligible, matching the brief's own "AT/AFTER
# six months -> LONG_PENDING_APPLICATION" wording (inclusive at the
# boundary - deliberately the opposite inequality direction from
# RECENT_PERMISSION's own exclusive-at-boundary rule above, each matching
# its own literal wording in the brief).
LONG_PENDING_APPLICATION_WINDOW_MONTHS = 6

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


def planning_delivery_long_pending_application_opportunity_id(site_id: int) -> str:
    return f"planning_delivery:long_pending_application:{site_id}"


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
    living alongside its siblings (_approaching_lapse_cards/
    _undeveloped_phase_cards/_long_pending_application_cards) for the same
    reason this module already reuses those rather than re-deriving
    "granted"/"build status" a second time. `limit=None` for the same
    completeness reason this module's own docstring already explains for
    the other detectors."""
    from app.reporting.dashboard import _recent_permission_cards

    return _recent_permission_cards(session, None, exclude_site_ids=frozenset(exclude_site_ids))


def _long_pending_application_candidate_sites(session, *, exclude_site_ids: set[int]) -> list[dict]:
    """Thin wrapper around app.reporting.dashboard._long_pending_
    application_cards - the single canonical implementation of the Gate 1C
    amendment's new detector, living alongside its siblings for the same
    reason the other planning/delivery detectors do. `limit=None` for the
    same completeness reason this module's own docstring explains for
    every other detector."""
    from app.reporting.dashboard import _long_pending_application_cards

    return _long_pending_application_cards(session, None, exclude_site_ids=frozenset(exclude_site_ids))


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

    # Precedence chain (Gate 1C amendment, Section 13): each later detector
    # is the EARLIER lifecycle stage / broader-window fallback and never
    # duplicates a site any more-specific, higher-precedence detector
    # already covers - approaching_lapse/undeveloped_permission (most
    # specific, established signals) > recent_permission (a fresh grant,
    # narrower now at 3 months) > long_pending_application (the earliest,
    # pre-grant stage, and the lowest precedence of all four planning/
    # delivery routes). A normal site lifecycle therefore shows AT MOST one
    # planning/delivery card at a time as it moves through: long_pending ->
    # (granted) -> recent_permission -> (ages out) -> nothing ->
    # (approaches its deadline) -> approaching_lapse.
    already_covered_site_ids = {int(c["params"]["site_id"]) for c, _ in tagged}
    recent_permission_cards = _recent_permission_candidate_sites(session, exclude_site_ids=already_covered_site_ids)
    tagged += [(c, "recent_permission") for c in recent_permission_cards]

    already_covered_site_ids = already_covered_site_ids | {int(c["params"]["site_id"]) for c in recent_permission_cards}
    long_pending_cards = _long_pending_application_candidate_sites(session, exclude_site_ids=already_covered_site_ids)
    tagged += [(c, "long_pending_application") for c in long_pending_cards]

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
        # Gate 2B-2B.1 pre-merge remediation - unit_count/affordable_unit_
        # count/development_type_raw/is_specialist_development below still
        # come from `si` (this Site's single representative application's
        # own SchemeIntelligence) exactly as before - those four fields
        # feed fingerprint_fields just below, and this gate is forbidden
        # from changing opportunity fingerprints. planning_state is NOT
        # one of those fingerprinted fields (confirmed: absent from
        # fingerprint_fields immediately below), so it is resolved here
        # from the trusted, role-aware, decided-state-aware
        # OperativePlanningFacts over this Site's FULL application list
        # (site_apps, already batched above) - the same resolution
        # build_planning_delivery_matching_facts_from_operative uses for
        # the live Buyer Fit path - rather than the previous hardcoded
        # PERMISSION_GRANTED, which this exact object also fed to app.
        # policy.buyer_profile_store.run_buyer_onboarding_baseline via
        # OpportunityRecord.matching_facts.
        operative_facts = build_operative_planning_facts(site_apps)
        planning_state = resolve_operative_planning_state(operative_facts)
        facts = build_planning_delivery_matching_facts(si, planning_state=planning_state)

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
            # Gate 2B-2B.2 - a named phase or material development parcel
            # (phase_code != UNPHASED_LABEL) must carry ITS OWN
            # deterministically supported unit_count, never the whole
            # site's rep-derived total set above. card["phase_unit_count"]
            # is that scope's own app.pipeline.phase_tracking._phase_
            # unit_count result, already computed once by
            # build_acquisition_scope_breakdown inside _undeveloped_phase_
            # cards - reused here verbatim rather than re-grouping this
            # site's applications a second time. None (genuinely not
            # determined) is a valid, expected outcome and is never
            # backfilled from the whole-site figure. A "Whole site /
            # unphased" card has only one scope on the site, so it keeps
            # the existing rep-derived unit_count unchanged - there is no
            # separate "whole site" figure to prefer it over.
            if phase_code != UNPHASED_LABEL:
                phase_unit_count = card.get("phase_unit_count")
                facts = replace(facts, unit_count=phase_unit_count)
                fingerprint_fields["unit_count"] = phase_unit_count
        elif kind == "recent_permission":
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
        else:  # "long_pending_application" (Gate 1C amendment)
            opportunity_id = planning_delivery_long_pending_application_opportunity_id(site_id)
            # The submission date of the specific application that
            # triggered eligibility (card["when"], from _long_pending_
            # application_cards' own selection - see that function's own
            # docstring for why this is deliberately NOT the same
            # application `rep`/`facts` above uses) - a STABLE fact, never
            # a live "days pending" counter. A genuinely different
            # application later becoming the long-pending trigger for this
            # site (e.g. the current one is withdrawn/decided and an older
            # co-pending one takes over) registers as a material change.
            fingerprint_fields["submitted_date"] = card.get("when")

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
