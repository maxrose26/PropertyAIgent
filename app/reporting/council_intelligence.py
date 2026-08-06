"""Customer-facing Council Intelligence data assembly (Sprint 4.3).

Splits the platform's per-council view into two audiences: this module
feeds the customer-facing "Council Intelligence" pages under Policy - a
planning intelligence summary, never an operational monitoring view.
app.policy.council_dashboard (renamed "Council Operations" in the UI, per
this sprint) remains the internal, monitoring-health-and-coverage-internals
view for Administration - untouched by this module.

A pure module, no Streamlit imports, mirroring app.reporting.dashboard's
own discipline (CLAUDE.md's "keep business logic out of the UI"). Every
figure here is read from data that already exists elsewhere
(app.policy.council_dashboard.summarise_council, app.policy.coverage,
app.policy.plan_evidence_view, app.visuals.site_view) - this module adds
NO new intelligence engine, only a customer-oriented reshaping of what's
already computed, batched, and tested. Where a figure genuinely doesn't
exist yet, it stays None and the caller (the UI layer) renders an honest
"not available" - nothing here ever fabricates or estimates a value.

Primary-plan selection: a council can have more than one LocalPlan (its own
plan plus a joint plan like Places for Everyone). This module always
prefers the council's OWN plan (its LocalPlanCouncil role is anything other
than "participating_authority") over a joint plan it merely participates
in, then prefers an adopted plan over an emerging one, then the most
recently checked - so a council's headline card/detail page always leads
with the plan a customer would recognise as "this council's Local Plan",
never an arbitrary row order.
"""
from __future__ import annotations

import datetime as dt
import re

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    Council,
    LocalPlan,
    LocalPlanCouncil,
    LocalPlanSite,
    MonitoredReport,
    PolicyChangeEvent,
    VisualEvidence,
)
from app.policy.coverage import build_coverage_inventory
from app.policy.council_dashboard import build_council_dashboard, summarise_council
from app.policy.joint_plans import plans_for_council
from app.policy.plan_evidence_view import build_plan_evidence_view
from app.visuals.site_view import build_allocation_image_status

# Customer-facing labels for app.policy.status.PLAN_STATUSES - the same
# "never surface a raw internal enum" discipline as app.visuals.
# IMAGE_TYPE_LABELS and app.policy.document_types.POLICY_DOCUMENT_TYPE_LABELS.
PLAN_STAGE_LABELS: dict[str, str] = {
    "preparation": "Preparation",
    "early_consultation": "Early consultation",
    "issues_and_options": "Issues & options (Regulation 18)",
    "draft_consultation": "Draft consultation",
    "preferred_options": "Preferred options",
    "proposed_submission": "Proposed submission (Regulation 19)",
    "submitted": "Submitted",
    "examination": "Examination",
    "main_modifications": "Main modifications",
    "inspector_report": "Inspector's report",
    "adopted": "Adopted",
    "paused": "Paused",
    "withdrawn": "Withdrawn",
    "superseded": "Superseded",
    "unknown": "Not yet stated",
}

# A customer never needs to see "monitoring_health: stale" - only whether
# the evidence behind this council can be trusted as current (docs/
# NAVIGATION_ARCHITECTURE.md's "Last checked replaces monitoring health as
# the only freshness signal a customer needs").
EVIDENCE_FRESHNESS_LABELS: dict[str, str] = {
    "ok": "Up to date",
    "stale": "May be out of date",
    "error": "May be out of date",
    "never_checked": "Not yet checked",
    "no_sources": "Monitoring not yet enabled",
}

# Timeline event labels (Part 10) - {plan_name} is filled in per-entry.
# Only PolicyChangeEvent.event_type values that are genuinely meaningful to
# a customer are given a friendly label; anything else falls back to a
# generic "{plan_name} updated" rather than surfacing a raw event_type
# string.
_TIMELINE_EVENT_LABELS: dict[str, tuple[str, str]] = {
    "adoption": ("✅", "{plan_name} adopted"),
    "stage_change": ("➡️", "{plan_name} moved to a new stage"),
    "new_plan_version": ("📋", "A new version of {plan_name} was found"),
    "withdrawal": ("🚫", "{plan_name} withdrawn"),
    "new_allocation": ("🏗️", "A new allocation was added to {plan_name}"),
    "allocation_removed": ("🚫", "An allocation was removed from {plan_name}"),
    "allocation_amended": ("✏️", "An allocation was amended in {plan_name}"),
    "capacity_changed": ("✏️", "An allocation's capacity changed in {plan_name}"),
    "report_discovered": ("📄", "A new monitoring report was discovered for {plan_name}"),
    "report_superseded": ("🗄️", "A monitoring report was superseded for {plan_name}"),
    "plan_evidence_proposed": ("📊", "New evidence was proposed for {plan_name}"),
    "source_content_changed": ("🔄", "{plan_name}'s source content changed"),
}

# Housing-position fields whose absence is worth naming explicitly as an
# evidence gap (Part 11), beyond whatever app.policy.coverage's document-
# level inventory already reports missing - the same evidence_view data
# the Housing Position panel itself renders from, so no extra query.
_HOUSING_GAP_FIELDS: list[tuple[str, str]] = [
    ("five_year_supply_years", "Five-year housing land supply not yet stated"),
    ("homes_delivered_latest_period", "Housing delivery figures not yet stated"),
    ("deliverable_supply_dwellings", "Deliverable housing supply not yet stated"),
    ("annual_housing_requirement", "Housing requirement not yet stated"),
]


def _excerpt(text: str | None, length: int = 220) -> str | None:
    """Same word-boundary truncation convention as app.reporting.dashboard's
    own AI-summary excerpting - kept as a small, independent copy here
    rather than importing a private helper across modules."""
    if not text:
        return None
    if len(text) <= length:
        return text
    truncated = text[:length].rsplit(" ", 1)[0]
    return truncated + "…"


def _plan_roles_by_council(session: Session, council_codes: list[str]) -> dict[str, dict[int, str]]:
    """One batched query for every council being rendered (the Overview
    page) or the one council being rendered (the Detail page) - never a
    per-plan query, per Part 14's "no N+1 queries"."""
    if not council_codes:
        return {}
    rows = session.execute(
        select(LocalPlanCouncil).where(LocalPlanCouncil.council_code.in_(council_codes))
    ).scalars().all()
    result: dict[str, dict[int, str]] = {}
    for link in rows:
        result.setdefault(link.council_code, {})[link.local_plan_id] = link.role
    return result


def _select_primary_plan(plans: list[LocalPlan], council_code: str, roles_by_plan: dict[int, str]) -> LocalPlan | None:
    """See module docstring - own plan over joint plan, adopted over
    emerging, most recently checked as the final tie-breaker.

    "Own" means role == "legacy_owner" specifically - app.policy.
    joint_plans only ever assigns that role to a genuine single-authority
    plan (no config/joint_plans.yaml entry at all), or to a plan not yet
    backfilled with any LocalPlanCouncil row (roles_by_plan.get(...,
    "legacy_owner") default, matching that module's own "no config entry
    means single-authority" convention). "lead_authority" is NOT treated
    as own here even though it sounds like it should be: it's the role
    given to whichever authority administratively coordinates a genuinely
    joint plan (e.g. Places for Everyone) - the plan itself is still a
    multi-authority plan, not that council's own single-authority Local
    Plan, so it must rank the same as "participating_authority" for this
    council-card headline-plan decision. Confirmed real case this guards
    against: a council that happens to be the joint plan's coordinating
    authority must still headline its OWN Local Plan first, not the joint
    plan it merely leads administratively."""
    if not plans:
        return None

    def sort_key(plan: LocalPlan):
        role = roles_by_plan.get(plan.id, "legacy_owner")
        is_own = role == "legacy_owner"
        is_adopted = plan.status == "adopted"
        last = plan.last_checked or plan.updated_at
        last_ts = last.timestamp() if last else 0.0
        return (not is_own, not is_adopted, -last_ts)

    return sorted(plans, key=sort_key)[0]


def _housing_requirement(plan: LocalPlan | None) -> tuple[int | None, str | None]:
    """(value, basis) - the plan's total figure where stated, falling back
    to its annual figure, since a council card has room for one headline
    housing-requirement number, not both (the Housing Position detail panel
    shows both independently via build_plan_evidence_view)."""
    if plan is None:
        return None, None
    if plan.total_housing_requirement is not None:
        return plan.total_housing_requirement, "total"
    if plan.annual_housing_requirement is not None:
        return plan.annual_housing_requirement, "annual"
    return None, None


def _format_housing_requirement(value: int | None, basis: str | None) -> str | None:
    """Compact, non-truncated headline text for a plan's housing
    requirement figure (Sprint 4.3 refinement, Part 3 - "no headline value
    may appear as truncated text"). "annual" is shown as a rate
    ("452 homes/year") so it's never mistaken for the total plan-period
    figure ("9,486 homes")."""
    if value is None:
        return None
    if basis == "annual":
        return f"{value:,} homes/year"
    return f"{value:,} homes"


_FIVE_YEAR_SUPPLY_WARNING_THRESHOLD = 5.0


def _five_year_supply_state(years: float | None) -> str:
    """"warning" | "ok" | "unverified" - drives the overview card's
    low-supply alert treatment (refinement Part 4). Never inferred:
    "unverified" whenever this council has no trusted five-year-supply
    figure extracted yet, even when other housing figures exist - e.g.
    Bury today, where no relevant report has been discovered."""
    if years is None:
        return "unverified"
    return "warning" if years < _FIVE_YEAR_SUPPLY_WARNING_THRESHOLD else "ok"


def _format_five_year_supply(years: float | None) -> str:
    """"1.77 years" for a real figure, or an explicit "Not yet verified" -
    never a bare em dash for this specific headline figure (refinement
    Part 4), and never an estimated/inferred number."""
    if years is None:
        return "Not yet verified"
    return f"{years:g} years"


def _parse_year_from_date_string(value: str | None) -> int | None:
    """Extracts a plain 4-digit year token from a free-text date field
    (LocalPlan.adoption_date is a string like "21 March 2024", not a real
    date column) - deterministic parsing of evidence already on file,
    never an estimate. Returns None whenever the text has no recognisable
    year, rather than guessing one."""
    if not value:
        return None
    match = re.search(r"\b(19|20)\d{2}\b", value)
    return int(match.group(0)) if match else None


def _plan_age_years(adoption_year: int | None) -> int | None:
    """Whole years since adoption, computed from today's date - exact
    arithmetic on a real stored year, never an estimate (refinement Part
    3: "calculated automatically from the adoption date")."""
    if adoption_year is None:
        return None
    current_year = dt.date.today().year
    age = current_year - adoption_year
    return age if age >= 0 else None


# Planning Readiness chip (Commercial Planning Readiness refinement, Part
# 2) - a finer-grained, colour-coded label than the card's own restrained
# background category below; independent of whether the plan is this
# council's own, since a customer still needs to know what stage the
# DISPLAYED plan is actually at. Every LocalPlan.status maps to exactly one
# entry; "unknown" (and anything not explicitly listed) gets an honest
# neutral chip rather than a guessed category.
_READINESS_CHIP_STYLE: dict[str, tuple[str, str]] = {
    "withdrawn": ("🔴", "Withdrawn"),
    "paused": ("🔴", "Paused"),
    "superseded": ("🔴", "Superseded"),
    "examination": ("🔵", "Examination"),
    "submitted": ("🔵", "Submitted"),
    "main_modifications": ("🟠", "Main Modifications"),
    "inspector_report": ("🟠", "Inspector's Report"),
    "issues_and_options": ("🟡", "Regulation 18"),
    "early_consultation": ("🟡", "Regulation 18"),
    "preferred_options": ("🟡", "Regulation 18"),
    "draft_consultation": ("🟡", "Regulation 18"),
    "preparation": ("🟡", "Regulation 18"),
    "proposed_submission": ("🟣", "Regulation 19"),
}


_PLAN_AGE_DISPLAY_THRESHOLD = 5


def _planning_readiness_chip(plan: LocalPlan | None) -> dict | None:
    """The overview card's Planning Readiness chip - None when there's no
    plan to describe at all (the existing "No Local Plan yet" badge covers
    that case). For an adopted plan, the label includes the adoption year;
    the plan's age in whole years is added as a sublabel ONLY once the plan
    is genuinely old (Sprint 4.3a, Part 4 - "avoid clutter such as
    'Adopted 2024 (1 year old)'"), never for a recently-adopted plan where
    the age adds no useful signal. Both year and age are parsed/derived
    from LocalPlan.adoption_date, never invented; falls back to a bare
    "Adopted" when that field has no recognisable year."""
    if plan is None:
        return None
    if plan.status == "adopted":
        year = _parse_year_from_date_string(plan.adoption_date)
        if year is None:
            return {"emoji": "🟢", "label": "Adopted", "sublabel": None}
        age = _plan_age_years(year)
        sublabel = (
            f"{age} years old" if age is not None and age > _PLAN_AGE_DISPLAY_THRESHOLD else None
        )
        return {"emoji": "🟢", "label": f"Adopted {year}", "sublabel": sublabel}
    emoji, label = _READINESS_CHIP_STYLE.get(plan.status, ("⚪", "Not yet stated"))
    return {"emoji": emoji, "label": label, "sublabel": None}


# Restrained, status-based card colour categories (Sprint 4.3a, Part 3) -
# five buckets, driven ONLY by the plan's own status: Adopted / Emerging /
# Regulation 18 / Examination / Withdrawn. The previous refinement's
# "Joint-plan only" colour OVERRIDE has been removed per this sprint's
# explicit instruction - "Status colour should always reflect the plan
# status" - joint-plan participation is now communicated separately via
# the Joint Plan badge (see build_council_overview), never by recolouring
# the card away from what its displayed plan's status actually is. A
# council with no Local Plan onboarded at all still gets its own distinct
# "no-plan" neutral treatment (there's genuinely no status to reflect).
_STATUS_COLOR_CATEGORIES: dict[str, str] = {
    "adopted": "adopted",
    "withdrawn": "withdrawn",
    "paused": "withdrawn",
    "superseded": "withdrawn",
    "examination": "examination",
    "submitted": "examination",
    "issues_and_options": "regulation-18",
    "early_consultation": "regulation-18",
    "preferred_options": "regulation-18",
    "draft_consultation": "regulation-18",
    "preparation": "regulation-18",
}


def _status_color_category(plan: LocalPlan | None) -> str:
    if plan is None:
        return "no-plan"
    return _STATUS_COLOR_CATEGORIES.get(plan.status, "emerging")


def _planning_outlook(plan: LocalPlan | None) -> dict:
    """A deterministic Planning Outlook classification (Sprint 4.3a, Part
    1 - renamed from "Planning Health" and reworded so nothing here reads
    as "this site is more likely to get planning permission"; it describes
    the council's planning CONTEXT only). Built ONLY from plan.status and
    the same five_year_supply_years already shown on the card, never AI-
    generated. "delivery shortfall" is deliberately NOT wired into this
    classification: computing it would mean calling app.policy.
    plan_evidence_view.build_plan_evidence_view for every card in the
    overview list, which this module's own performance discipline (Part
    14, "no N+1 queries") reuses only on the per-council Detail page, not
    the overview - a documented trade-off, not an oversight."""
    if plan is None or plan.five_year_supply_years is None:
        return {"emoji": "⚪", "label": "Planning position still being assessed"}
    years = plan.five_year_supply_years
    if years < _FIVE_YEAR_SUPPLY_WARNING_THRESHOLD:
        return {"emoji": "🟠", "label": "Housing delivery pressure"}
    if plan.status == "adopted":
        return {"emoji": "🟢", "label": "Stable planning environment"}
    return {"emoji": "🟣", "label": "Major policy transition underway"}


def _why_it_matters(plan: LocalPlan | None, primary_plan_is_own: bool) -> str:
    """A short, deterministic (never AI-generated) 1-2 sentence explanation
    beneath Planning Outlook (Sprint 4.3a, Part 2) - built from the same
    evidence already used for the outlook classification plus whether the
    displayed plan is this council's own, so the wording never overstates
    certainty or implies planning permission is more or less likely."""
    if plan is None:
        return "No Local Plan has been identified for this council yet."
    if plan.five_year_supply_years is None:
        return "The council's housing land supply has not yet been verified."
    if plan.five_year_supply_years < _FIVE_YEAR_SUPPLY_WARNING_THRESHOLD:
        return "Housing delivery remains an important planning priority."
    if not primary_plan_is_own:
        if plan.status == "adopted":
            return f"Strategic development is currently guided through the adopted {plan.plan_name}."
        return f"Strategic development is currently guided through {plan.plan_name}."
    if plan.status != "adopted":
        return "The council is progressing a new Local Plan which may influence future planning policy."
    return "This council has an adopted Local Plan providing a settled policy framework for development."


def _format_next_milestone(plan: LocalPlan | None) -> dict:
    """The overview card's fourth STANDARDISED headline metric (Sprint
    4.3a, Part 5 - "every council card should display the same four
    headline metrics... never replace a metric with a different one").
    Always the plan's next milestone, never swapped out for a delivery
    figure regardless of what evidence happens to be available - an
    honest "Not yet verified" (the same fallback text used across every
    standardised metric on this card, per Part 5) when there's no
    milestone on file, never a fabricated placeholder."""
    if plan is not None and plan.next_milestone:
        value = plan.next_milestone_date or plan.next_milestone
        caption = plan.next_milestone if plan.next_milestone_date else None
        return {"value": value, "caption": caption}
    return {"value": "Not yet verified", "caption": None}


def _has_missing_evidence(plan: LocalPlan | None) -> bool:
    """Overview-card "missing-evidence indicator" (Part 4) - a cheap,
    card-level proxy (no coverage-engine query per card in a list of every
    council) rather than the full build_coverage_inventory/evidence-gap
    computation the detail page does. True whenever the plan is missing
    either its five-year supply position or any housing requirement figure
    - the two headline numbers a customer would expect to see filled in."""
    if plan is None:
        return True
    has_requirement = plan.total_housing_requirement is not None or plan.annual_housing_requirement is not None
    return plan.five_year_supply_years is None or not has_requirement


def _build_overview_card(row: dict, plan: LocalPlan | None, primary_plan_is_own: bool) -> dict:
    requirement_value, requirement_basis = _housing_requirement(plan)
    last_updated_candidates = [t for t in (row["last_checked"], plan.last_checked if plan else None) if t is not None]
    return {
        "council_code": row["council_code"],
        "council_name": row["council_name"],
        "plan_id": plan.id if plan else None,
        "plan_name": plan.plan_name if plan else None,
        "primary_plan_is_own": primary_plan_is_own,
        "adopted_or_emerging": ("Adopted" if plan.status == "adopted" else "Emerging") if plan else None,
        "current_stage": (PLAN_STAGE_LABELS.get(plan.status, "Not yet stated") if plan else "No Local Plan yet"),
        "planning_readiness_chip": _planning_readiness_chip(plan),
        "planning_outlook": _planning_outlook(plan),
        "why_it_matters": _why_it_matters(plan, primary_plan_is_own),
        "next_milestone": plan.next_milestone if plan else None,
        "next_milestone_date": plan.next_milestone_date if plan else None,
        "expected_adoption_date": plan.expected_adoption_date if plan else None,
        "five_year_supply_years": plan.five_year_supply_years if plan else None,
        "five_year_supply_state": _five_year_supply_state(plan.five_year_supply_years if plan else None),
        "five_year_supply_display": _format_five_year_supply(plan.five_year_supply_years if plan else None),
        "five_year_supply_base_date": plan.five_year_supply_base_date if plan else None,
        "housing_requirement": requirement_value,
        "housing_requirement_basis": requirement_basis,
        "housing_requirement_display": _format_housing_requirement(requirement_value, requirement_basis),
        "homes_delivered_latest_period": plan.homes_delivered_latest_period if plan else None,
        "latest_reporting_period": plan.latest_reporting_period if plan else None,
        "next_milestone_metric": _format_next_milestone(plan),
        "allocation_count": row["total_allocations_imported"],
        "status_color": _status_color_category(plan),
        "last_updated": max(last_updated_candidates) if last_updated_candidates else None,
        "ai_summary_excerpt": _excerpt(plan.ai_summary_text, length=180) if plan else None,
        "ai_summary_generated_at": plan.ai_summary_generated_at if plan else None,
        "evidence_freshness": EVIDENCE_FRESHNESS_LABELS.get(row["monitoring_health"], "Not yet checked"),
        "has_missing_evidence": _has_missing_evidence(plan),
        "page": "pages/6_Council_Intelligence_Detail.py",
        "params": {"council": row["council_code"]},
    }


def build_council_overview(session: Session) -> list[dict]:
    """One card per council with real Policy Intelligence activity - reuses
    app.policy.council_dashboard.build_council_dashboard's own council
    selection (a council with nothing onboarded yet correctly has no card,
    same as it has no row on Council Operations) rather than re-deriving
    which councils qualify. Sorted by council name for a stable, scannable
    order across reruns."""
    rows = build_council_dashboard(session)
    if not rows:
        return []

    council_codes = [r["council_code"] for r in rows]
    roles_by_council = _plan_roles_by_council(session, council_codes)

    all_plan_ids = [p["plan_id"] for r in rows for p in r["local_plans"]]
    plans_by_id: dict[int, LocalPlan] = {}
    if all_plan_ids:
        plans_by_id = {
            p.id: p for p in session.execute(select(LocalPlan).where(LocalPlan.id.in_(all_plan_ids))).scalars()
        }

    cards = []
    for row in rows:
        plan_objs = [plans_by_id[p["plan_id"]] for p in row["local_plans"] if p["plan_id"] in plans_by_id]
        roles = roles_by_council.get(row["council_code"], {})
        primary = _select_primary_plan(plan_objs, row["council_code"], roles)
        primary_plan_is_own = primary is not None and roles.get(primary.id, "legacy_owner") == "legacy_owner"
        cards.append(_build_overview_card(row, primary, primary_plan_is_own))

    cards.sort(key=lambda c: c["council_name"].lower())
    return cards


def _attach_latest_documents(session: Session, council_code: str, coverage: list[dict]) -> list[dict]:
    """Enriches app.policy.coverage's own inventory rows with the most
    recent CURRENT MonitoredReport for that document type (title, url,
    when) - Part 7's "status, current, last updated, open document",
    without touching or duplicating the coverage engine itself. One
    batched query for every document type this council has, grouped in
    Python - never one query per document type."""
    reports = session.execute(
        select(MonitoredReport).where(MonitoredReport.council_code == council_code, MonitoredReport.status == "current")
    ).scalars().all()
    by_type: dict[str, list[MonitoredReport]] = {}
    for report in reports:
        if report.policy_document_type is None:
            continue
        by_type.setdefault(report.policy_document_type, []).append(report)

    enriched = []
    for row in coverage:
        candidates = by_type.get(row["policy_document_type"], [])
        latest = max(candidates, key=lambda r: r.publication_date or "", default=None) if candidates else None
        enriched.append({
            **row,
            "latest_document_title": latest.title if latest else None,
            "latest_document_url": latest.url if latest else None,
            "latest_document_updated": latest.publication_date if latest else None,
        })
    return enriched


def _build_visual_evidence_summary(session: Session, plan_ids: list[int], allocation_ids: list[int]) -> dict:
    """Number of images / confirmed / needs review / latest extracted /
    recent allocation maps (Part 9) - a council-wide aggregate, genuinely
    new (app.visuals.site_view's existing helpers are scoped to a single
    Site or Allocation), but built from the same VisualEvidence rows and
    the same current/non-rejected filter those helpers already apply."""
    if not plan_ids and not allocation_ids:
        return {"total": 0, "confirmed": 0, "needs_review": 0, "latest_extracted": None, "recent_allocation_maps": []}

    conditions = []
    if plan_ids:
        conditions.append(VisualEvidence.local_plan_id.in_(plan_ids))
    if allocation_ids:
        conditions.append(VisualEvidence.allocation_id.in_(allocation_ids))

    rows = session.execute(
        select(VisualEvidence).where(
            or_(*conditions), VisualEvidence.status == "current", VisualEvidence.review_status != "rejected",
        )
    ).scalars().all()

    confirmed = [r for r in rows if r.review_status == "confirmed"]
    needs_review = [r for r in rows if r.review_status == "needs_review"]
    latest_extracted = max((r.created_at for r in rows), default=None)

    allocation_maps = sorted(
        (r for r in rows if r.allocation_id is not None),
        key=lambda r: r.created_at, reverse=True,
    )[:5]
    recent_allocation_maps = [{
        "id": r.id,
        "label": r.detected_allocation_title or r.source_document_title or "Allocation image",
        "reference": r.detected_allocation_reference,
        "review_status": r.review_status,
        "when": r.created_at,
    } for r in allocation_maps]

    return {
        "total": len(rows), "confirmed": len(confirmed), "needs_review": len(needs_review),
        "latest_extracted": latest_extracted, "recent_allocation_maps": recent_allocation_maps,
    }


def _build_council_timeline(session: Session, plan_ids: list[int], limit: int = 15) -> list[dict]:
    """A chronological council activity timeline (Part 10) - built entirely
    from PolicyChangeEvent (the platform's own change-detection log) plus
    each plan's own AI-summary-generation timestamp, never a new tracked
    signal. Presentation-only: nothing here writes or reclassifies
    anything."""
    if not plan_ids:
        return []

    plans = {p.id: p for p in session.execute(select(LocalPlan).where(LocalPlan.id.in_(plan_ids))).scalars()}
    events = session.execute(
        select(PolicyChangeEvent).where(PolicyChangeEvent.local_plan_id.in_(plan_ids))
        .order_by(PolicyChangeEvent.detected_at.desc()).limit(limit * 2)
    ).scalars().all()

    entries: list[dict] = []
    for event in events:
        plan = plans.get(event.local_plan_id)
        plan_name = plan.plan_name if plan else "Local Plan"
        icon, template = _TIMELINE_EVENT_LABELS.get(event.event_type, ("🕗", "{plan_name} updated"))
        entries.append({"icon": icon, "label": template.format(plan_name=plan_name), "when": event.detected_at})
        if event.review_status in ("confirmed", "rejected") and event.reviewed_at:
            verb = "confirmed" if event.review_status == "confirmed" else "rejected"
            entries.append({
                "icon": "✅" if verb == "confirmed" else "🚫",
                "label": f"A proposed change to {plan_name} was {verb} after review",
                "when": event.reviewed_at,
            })

    for plan in plans.values():
        if plan.ai_summary_generated_at:
            entries.append({
                "icon": "🤖", "label": f"{plan.plan_name} AI summary refreshed", "when": plan.ai_summary_generated_at,
            })

    entries.sort(key=lambda e: e["when"] or dt.datetime.min, reverse=True)
    return entries[:limit]


def _build_evidence_gaps(coverage: list[dict], evidence_view: dict | None) -> list[str]:
    """Missing evidence (Part 11) - reuses app.policy.coverage's own
    "missing" flag for document-level gaps, plus a small, fixed set of
    high-value housing-position fields drawn from the SAME evidence_view
    the Housing Position panel already renders from (no extra query)."""
    gaps = [row["label"] for row in coverage if row["missing"]]

    if evidence_view:
        by_field = {
            entry["field"]: entry
            for section in ("requirement", "delivery", "five_year_supply")
            for entry in evidence_view[section]
        }
        for field_name, label in _HOUSING_GAP_FIELDS:
            entry = by_field.get(field_name)
            if entry is not None and not entry["has_value"]:
                gaps.append(label)

    return gaps


def build_council_detail(session: Session, council_code: str) -> dict | None:
    """Everything the Council Intelligence detail page renders for one
    council, or None if the council doesn't exist. Every sub-assembly below
    reuses an existing module (see each helper's own docstring) - this
    function's only real job is fetching each council's own rows ONCE and
    handing them to those existing/new assemblers, never re-querying per
    section."""
    council = session.get(Council, council_code)
    if council is None:
        return None

    plans = plans_for_council(session, council_code)
    roles = _plan_roles_by_council(session, [council_code]).get(council_code, {})
    primary = _select_primary_plan(plans, council_code, roles)
    primary_plan_is_own = primary is not None and roles.get(primary.id, "legacy_owner") == "legacy_owner"

    summary = summarise_council(session, council)

    allocations = session.execute(
        select(LocalPlanSite).where(LocalPlanSite.council_code == council_code)
    ).scalars().all()
    allocation_ids = [a.id for a in allocations]
    image_status_by_id = build_allocation_image_status(session, allocation_ids)

    coverage = build_coverage_inventory(session, council_code)
    coverage = _attach_latest_documents(session, council_code, coverage)

    evidence_view = build_plan_evidence_view(session, primary) if primary is not None else None

    plan_ids = [p.id for p in plans]
    # Visual Evidence must only count images genuinely about THIS council -
    # allocation-scoped images always qualify (LocalPlanSite.council_code is
    # already council-specific), but plan-level images (VisualEvidence.
    # local_plan_id, not tied to any one allocation) must be restricted to
    # this council's OWN single-authority plan(s). Confirmed real bug this
    # guards against: without this restriction, every one of Places for
    # Everyone's ~150+ plan-wide extracted images (most of which show a
    # SPECIFIC allocation in a DIFFERENT participating borough, just not
    # confidently matched to an allocation_id) was being counted under
    # every single one of the plan's 9 participating authorities - Trafford
    # (3 allocations of its own) was showing "156 images" as if that many
    # were genuinely about Trafford.
    own_plan_ids = [p.id for p in plans if roles.get(p.id, "legacy_owner") == "legacy_owner"]
    visual_evidence = _build_visual_evidence_summary(session, own_plan_ids, allocation_ids)
    timeline = _build_council_timeline(session, plan_ids)
    evidence_gaps = _build_evidence_gaps(coverage, evidence_view)

    return {
        "council_code": council_code,
        "council_name": council.name,
        "primary_plan": primary,
        "primary_plan_is_own": primary_plan_is_own,
        "plans": plans,
        "plan_summaries": summary["local_plans"],
        "monitoring_health": summary["monitoring_health"],
        "evidence_freshness": EVIDENCE_FRESHNESS_LABELS.get(summary["monitoring_health"], "Not yet checked"),
        "review_items_pending": summary["review_items_pending"],
        "allocations": {
            "total": len(allocations),
            "matched": sum(1 for a in allocations if a.matched_site_id is not None),
            "without_application": sum(1 for a in allocations if a.matched_site_id is None),
            "with_images": sum(1 for a in allocations if image_status_by_id.get(a.id) == "confirmed"),
            "images_needing_review": sum(1 for a in allocations if image_status_by_id.get(a.id) == "needs_review"),
            "needing_review": sum(1 for a in allocations if a.review_status == "needs_confirmation"),
        },
        "coverage": coverage,
        "evidence_gaps": evidence_gaps,
        "evidence_view": evidence_view,
        "visual_evidence": visual_evidence,
        "timeline": timeline,
    }
