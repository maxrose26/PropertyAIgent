"""Pure data assembly for the Intelligence Dashboard (Sprint 4.2). Kept
separate from Streamlit so this exact assembly is testable independently of
rendering - the same pattern already established by
app.policy.council_dashboard, app.policy.site_view and
app.visuals.site_view (CLAUDE.md's "keep business logic out of the UI").

Every function here queries real, already-existing tables only - nothing is
invented or estimated. Where the brief's own worked examples (Sprint 4.2,
Parts 2-6) don't map onto a concept this platform actually tracks (e.g.
"matched overnight" implies a nightly batch cadence that doesn't exist -
site linking happens inline during scraping, not as a separate nightly
job), the closest honest, real signal is used instead and labelled for what
it actually is, never renamed to match the brief's example wording if that
would overstate what the data shows.

Every query here is a single, indexed, LIMIT-bounded SELECT - no N+1
patterns, consistent with Sprint 3A's "avoid one query per row" discipline
(see app.ui.common.load_applications_for_sites) and this sprint's own
Part 10 ("avoid excessive database queries, batch wherever practical").
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    Application,
    Council,
    LocalPlan,
    LocalPlanSite,
    MonitoredReport,
    MonitoredSource,
    PolicyChangeEvent,
    Site,
    VisualEvidence,
)
from app.pipeline.lapse_tracking import (
    BUILD_STATUS_LABELS,
    DECISION_STATUS_LABELS,
    GRANTED_KEYWORDS,
    LAPSE_WARNING_DAYS,
    classify_decision_status,
    compute_lapse_status,
    parse_portal_date,
)
from app.pipeline.phase_tracking import build_phase_breakdown
from app.visuals import IMAGE_TYPE_LABELS

# LocalPlan.status values (app.policy.status.PLAN_STATUSES) that represent a
# plan genuinely still moving toward adoption - everything except the
# terminal/unknown states. Reused wherever "emerging" needs a real
# definition rather than a guess.
_EMERGING_PLAN_STATUSES = (
    "preparation", "early_consultation", "issues_and_options", "draft_consultation",
    "preferred_options", "proposed_submission", "submitted", "examination",
    "main_modifications", "inspector_report",
)


def build_kpi_row(session: Session) -> list[dict]:
    """Each item: {"label", "value", "help", "live"}. Every figure here is a
    plain count against a real table - none needs a "Coming soon"
    placeholder, since the underlying data genuinely exists today."""
    monitored_councils = session.execute(
        select(func.count()).select_from(Council).where(Council.monitoring_enabled.is_(True))
    ).scalar() or 0
    local_plans = session.execute(select(func.count()).select_from(LocalPlan)).scalar() or 0
    allocation_sites = session.execute(select(func.count()).select_from(LocalPlanSite)).scalar() or 0
    applications = session.execute(select(func.count()).select_from(Application)).scalar() or 0
    visual_evidence = session.execute(
        select(func.count()).select_from(VisualEvidence).where(VisualEvidence.status == "current")
    ).scalar() or 0
    ai_local_plan_summaries = session.execute(
        select(func.count()).select_from(LocalPlan).where(LocalPlan.ai_summary_text.is_not(None))
    ).scalar() or 0
    ai_site_summaries = session.execute(
        select(func.count()).select_from(Site).where(Site.status_summary.is_not(None))
    ).scalar() or 0

    review_queue = build_review_queue_counts(session)

    return [
        {"label": "Councils", "value": monitored_councils, "live": True,
         "help": "Councils with Policy Intelligence monitoring enabled."},
        {"label": "Local Plans", "value": local_plans, "live": True,
         "help": "Every Local Plan ingested, across every council."},
        {"label": "Allocations", "value": allocation_sites, "live": True,
         "help": "Sites allocated for housing in a Local Plan, whether or not an application exists yet."},
        {"label": "Applications", "value": applications, "live": True,
         "help": "Every scraped planning application tracked by the platform."},
        {"label": "Visual Evidence", "value": visual_evidence, "live": True,
         "help": "Current (non-superseded) extracted site plans and allocation maps."},
        {"label": "AI Summaries", "value": ai_local_plan_summaries + ai_site_summaries, "live": True,
         "help": f"{ai_local_plan_summaries} Local Plan summaries + {ai_site_summaries} Site summaries generated."},
        {"label": "Reviews", "value": review_queue["total"], "live": True,
         "help": "Suggested site links, policy changes and visual evidence awaiting a human decision."},
    ]


def build_review_queue_counts(session: Session) -> dict:
    """The platform's full cross-cutting review backlog - reuses the exact
    same filter conditions already established on the Explore page
    (suggested site links) and Council Dashboard (PolicyChangeEvent) rather
    than redefining them, so this total can never silently drift out of
    sync with what those pages already count."""
    suggested_links = session.execute(
        select(func.count(Application.id)).where(
            Application.site_link_method == "suggested_fuzzy", Application.site_id.is_(None)
        )
    ).scalar() or 0
    policy_changes = session.execute(
        select(func.count(PolicyChangeEvent.id)).where(PolicyChangeEvent.review_status == "needs_review")
    ).scalar() or 0
    visual_evidence = session.execute(
        select(func.count(VisualEvidence.id)).where(
            VisualEvidence.status == "current", VisualEvidence.review_status == "needs_review"
        )
    ).scalar() or 0
    return {
        "suggested_links": suggested_links,
        "policy_changes": policy_changes,
        "visual_evidence": visual_evidence,
        "total": suggested_links + policy_changes + visual_evidence,
    }


def build_planning_intelligence(session: Session, limit: int = 5) -> dict:
    """Part 3 - real signals only. "Applications matched overnight" (the
    brief's own example) has no honest equivalent here: site linking runs
    inline during scraping (app.pipeline.site_linking), not as a separate
    nightly batch with its own timestamp - "Recently linked to a site"
    below is the real, non-invented signal closest to that intent."""
    recent_applications = session.execute(
        select(Application).order_by(Application.first_seen_at.desc()).limit(limit)
    ).scalars().all()

    recently_linked = session.execute(
        select(Application)
        .where(Application.site_id.is_not(None), Application.site_link_method.is_not(None))
        .order_by(Application.last_seen_at.desc())
        .limit(limit)
    ).scalars().all()

    recently_updated_schemes = session.execute(
        select(Site).where(Site.excluded.is_not(True)).order_by(Site.updated_at.desc()).limit(limit)
    ).scalars().all()

    review_counts = build_review_queue_counts(session)

    return {
        "recent_applications": [
            {"reference": a.reference, "address": a.address, "council_code": a.council_code, "when": a.first_seen_at}
            for a in recent_applications
        ],
        "recently_linked": [
            {"reference": a.reference, "address": a.address, "method": a.site_link_method, "when": a.last_seen_at}
            for a in recently_linked
        ],
        "recently_updated_schemes": [
            {"address": s.display_address, "council_code": s.council_code, "when": s.updated_at}
            for s in recently_updated_schemes
        ],
        "needs_review_count": review_counts["suggested_links"],
    }


def build_policy_intelligence(session: Session, limit: int = 5) -> dict:
    """Part 4 - real signals only."""
    recent_plan_updates = session.execute(
        select(LocalPlan).order_by(LocalPlan.updated_at.desc()).limit(limit)
    ).scalars().all()

    recent_documents = session.execute(
        select(MonitoredReport).order_by(MonitoredReport.discovered_at.desc()).limit(limit)
    ).scalars().all()

    last_monitoring_check = session.execute(
        select(func.max(MonitoredSource.last_checked))
    ).scalar()

    recent_visual_evidence = session.execute(
        select(VisualEvidence).where(VisualEvidence.status == "current")
        .order_by(VisualEvidence.created_at.desc()).limit(limit)
    ).scalars().all()

    plans_awaiting_review = session.execute(
        select(PolicyChangeEvent.local_plan_id, func.count(PolicyChangeEvent.id))
        .where(PolicyChangeEvent.review_status == "needs_review", PolicyChangeEvent.local_plan_id.is_not(None))
        .group_by(PolicyChangeEvent.local_plan_id)
    ).all()
    plan_ids = [row[0] for row in plans_awaiting_review]
    plans_by_id = {}
    if plan_ids:
        plans_by_id = {
            p.id: p for p in session.execute(select(LocalPlan).where(LocalPlan.id.in_(plan_ids))).scalars().all()
        }

    recent_ai_summaries = session.execute(
        select(LocalPlan).where(LocalPlan.ai_summary_generated_at.is_not(None))
        .order_by(LocalPlan.ai_summary_generated_at.desc()).limit(limit)
    ).scalars().all()

    return {
        "recent_plan_updates": [
            {"plan_name": p.plan_name, "council_code": p.council_code, "status": p.status, "when": p.updated_at}
            for p in recent_plan_updates
        ],
        "recent_documents": [
            {"title": r.title or r.url, "council_code": r.council_code, "when": r.discovered_at}
            for r in recent_documents
        ],
        "last_monitoring_check": last_monitoring_check,
        "recent_visual_evidence": [
            {
                "label": IMAGE_TYPE_LABELS.get(v.image_type, v.image_type),
                "source": v.source_document_title, "when": v.created_at,
            }
            for v in recent_visual_evidence
        ],
        "plans_awaiting_review": [
            {"plan_name": plans_by_id[pid].plan_name, "council_code": plans_by_id[pid].council_code, "pending": count}
            for pid, count in plans_awaiting_review if pid in plans_by_id
        ],
        "recent_ai_summaries": [
            {"plan_name": p.plan_name, "council_code": p.council_code, "when": p.ai_summary_generated_at}
            for p in recent_ai_summaries
        ],
    }


def build_opportunities(session: Session, limit: int = 5) -> dict:
    """Part 5 - "initially deterministic," per the brief. Every category
    below is a plain filter/sort against real, already-populated fields -
    no scoring model, no invented weighting."""
    low_supply = session.execute(
        select(LocalPlan).where(LocalPlan.five_year_supply_years.is_not(None))
        .order_by(LocalPlan.five_year_supply_years.asc()).limit(limit)
    ).scalars().all()

    emerging_plans = session.execute(
        select(LocalPlan).where(LocalPlan.status.in_(_EMERGING_PLAN_STATUSES))
        .order_by(LocalPlan.updated_at.desc()).limit(limit)
    ).scalars().all()

    large_unmatched_allocations = session.execute(
        select(LocalPlanSite).where(
            LocalPlanSite.matched_site_id.is_(None), LocalPlanSite.minimum_dwellings.is_not(None)
        ).order_by(LocalPlanSite.minimum_dwellings.desc()).limit(limit)
    ).scalars().all()

    recent_policy_activity = session.execute(
        select(MonitoredSource.council_code, func.max(MonitoredSource.last_changed).label("last_changed"))
        .where(MonitoredSource.last_changed.is_not(None))
        .group_by(MonitoredSource.council_code)
        .order_by(func.max(MonitoredSource.last_changed).desc())
        .limit(limit)
    ).all()

    recently_adopted = session.execute(
        select(LocalPlan).where(LocalPlan.status == "adopted")
        .order_by(LocalPlan.updated_at.desc()).limit(limit)
    ).scalars().all()

    return {
        "low_supply_authorities": [
            {"council_code": p.council_code, "plan_name": p.plan_name, "years": p.five_year_supply_years}
            for p in low_supply
        ],
        "emerging_plans": [
            {"council_code": p.council_code, "plan_name": p.plan_name, "status": p.status} for p in emerging_plans
        ],
        "large_unmatched_allocations": [
            {
                "council_code": a.council_code, "site_name": a.site_name,
                "policy_reference": a.policy_reference, "minimum_dwellings": a.minimum_dwellings,
            }
            for a in large_unmatched_allocations
        ],
        "recent_policy_activity": [
            {"council_code": row[0], "when": row[1]} for row in recent_policy_activity
        ],
        "recently_adopted_plans": [
            {"council_code": p.council_code, "plan_name": p.plan_name, "when": p.updated_at} for p in recently_adopted
        ],
    }


def build_recent_activity(session: Session, limit: int = 20) -> list[dict]:
    """Part 6 - one merged, real timeline. Each contributing stream is its
    own small LIMIT-bounded query (never a full-table scan), combined and
    re-sorted in Python rather than one large UNION - simpler to read and
    cheap at this scale (each stream is independently bounded)."""
    per_stream_limit = limit

    events: list[dict] = []

    for v in session.execute(
        select(VisualEvidence).where(VisualEvidence.status == "current")
        .order_by(VisualEvidence.created_at.desc()).limit(per_stream_limit)
    ).scalars().all():
        events.append({
            "when": v.created_at, "icon": "🖼️", "category": "Visual Evidence",
            "text": f"{IMAGE_TYPE_LABELS.get(v.image_type, v.image_type)} extracted"
                    + (f" — {v.source_document_title}" if v.source_document_title else ""),
        })

    for r in session.execute(
        select(MonitoredReport).order_by(MonitoredReport.discovered_at.desc()).limit(per_stream_limit)
    ).scalars().all():
        events.append({
            "when": r.discovered_at, "icon": "📄", "category": "Policy Intelligence",
            "text": f"Policy document discovered — {r.title or r.url} ({r.council_code})",
        })

    for p in session.execute(
        select(LocalPlan).order_by(LocalPlan.updated_at.desc()).limit(per_stream_limit)
    ).scalars().all():
        events.append({
            "when": p.updated_at, "icon": "📋", "category": "Policy Intelligence",
            "text": f"Local Plan updated — {p.plan_name} ({p.council_code})",
        })

    for s in session.execute(
        select(MonitoredSource).where(MonitoredSource.last_changed.is_not(None))
        .order_by(MonitoredSource.last_changed.desc()).limit(per_stream_limit)
    ).scalars().all():
        events.append({
            "when": s.last_changed, "icon": "🔎", "category": "Monitoring",
            "text": f"Source content changed — {s.title or s.url} ({s.council_code})",
        })

    for a in session.execute(
        select(LocalPlanSite).where(LocalPlanSite.matched_site_id.is_not(None))
        .order_by(LocalPlanSite.updated_at.desc()).limit(per_stream_limit)
    ).scalars().all():
        events.append({
            "when": a.updated_at, "icon": "🔗", "category": "Planning Intelligence",
            "text": f"Allocation matched to a Site — {a.policy_reference or a.site_name} ({a.council_code})",
        })

    for e in session.execute(
        select(PolicyChangeEvent).where(
            PolicyChangeEvent.review_status.in_(("confirmed", "rejected")), PolicyChangeEvent.reviewed_at.is_not(None)
        ).order_by(PolicyChangeEvent.reviewed_at.desc()).limit(per_stream_limit)
    ).scalars().all():
        events.append({
            "when": e.reviewed_at, "icon": "✅", "category": "Review",
            "text": f"Review completed — {e.event_type} ({e.review_status})",
        })

    # SQLite doesn't preserve tzinfo across a round-trip the same way every
    # column was originally written (some rows here came from a model
    # default's utcnow(), others from an explicit value at insert time) -
    # normalising to naive-for-comparison-only here avoids a
    # "can't compare offset-naive and offset-aware datetimes" TypeError
    # without altering what's actually displayed ("when" keeps its
    # original value).
    events.sort(key=lambda e: e["when"].replace(tzinfo=None) if e["when"].tzinfo else e["when"], reverse=True)
    return events[:limit]


def _naive(value: dt.datetime) -> dt.datetime:
    """Normalise to naive-for-comparison-only, mirroring build_recent_
    activity's own inline handling - not every timestamp column round-trips
    through SQLite with the same tzinfo state, and mixing them in one sort
    otherwise raises "can't compare offset-naive and offset-aware
    datetimes"."""
    return value.replace(tzinfo=None) if value.tzinfo else value


# --- Live Intelligence Leaderboard (Sprint 4.2 amendment) -------------------
#
# Deliberately separate, small query functions rather than reshaping
# build_planning_intelligence/build_policy_intelligence/build_opportunities'
# own results - the amendment's own instruction is explicit ("do not change
# the underlying dashboard queries or business logic"), and the leaderboard
# needs a stable id and a resolved link target per row that those existing
# dict shapes don't carry. Every query below mirrors the exact same filter
# conditions as its counterpart elsewhere on this page (same tables, same
# WHERE clauses, same definition of "recent"/"needs review") - nothing here
# changes what counts as reviewable/opportunity/etc.; it only adds the
# plumbing (id, tie-break, link target) this component specifically needs.
# Ranking is always recency (a real timestamp column) then id (guaranteed
# unique, stable across reruns) - never a score, never invented.

LEADERBOARD_TAB_ORDER = ("New Apps", "Scheme Updates", "Policy", "Evidence & AI", "Attention")


def build_leaderboard_new_applications(session: Session, limit: int = 8) -> list[dict]:
    rows = session.execute(
        select(Application).order_by(Application.first_seen_at.desc(), Application.id.desc()).limit(limit)
    ).scalars().all()
    out = []
    for a in rows:
        page, params = ("pages/1_Scheme_Detail.py", {"site_id": str(a.site_id)}) if a.site_id else (None, None)
        out.append({
            "id": f"application-{a.id}", "title": a.reference,
            "subtitle": (a.address or "No address")[:70], "when": a.first_seen_at,
            "badge": None, "page": page, "params": params,
        })
    return out


def build_leaderboard_updated_schemes(session: Session, limit: int = 8) -> list[dict]:
    rows = session.execute(
        select(Site).where(Site.excluded.is_not(True))
        .order_by(Site.updated_at.desc(), Site.id.desc()).limit(limit)
    ).scalars().all()
    return [
        {
            "id": f"site-{s.id}", "title": s.display_address[:70], "subtitle": s.council_code,
            "when": s.updated_at, "badge": None,
            "page": "pages/1_Scheme_Detail.py", "params": {"site_id": str(s.id)},
        }
        for s in rows
    ]


def build_leaderboard_policy_updates(session: Session, limit: int = 8) -> list[dict]:
    plans = session.execute(
        select(LocalPlan).order_by(LocalPlan.updated_at.desc(), LocalPlan.id.desc()).limit(limit)
    ).scalars().all()
    reports = session.execute(
        select(MonitoredReport).order_by(MonitoredReport.discovered_at.desc(), MonitoredReport.id.desc()).limit(limit)
    ).scalars().all()

    rows = [
        {
            "id": f"plan-{p.id}", "title": p.plan_name, "subtitle": f"{p.council_code} · plan updated",
            "when": p.updated_at, "badge": p.status.replace("_", " ") if p.status else None,
            "page": "pages/4_Council_Dashboard.py", "params": {},
        }
        for p in plans
    ] + [
        {
            "id": f"report-{r.id}", "title": (r.title or r.url)[:70], "subtitle": f"{r.council_code} · document discovered",
            "when": r.discovered_at, "badge": None,
            "page": "pages/4_Council_Dashboard.py", "params": {},
        }
        for r in reports
    ]
    rows.sort(key=lambda row: (_naive(row["when"]), row["id"]), reverse=True)
    return rows[:limit]


def build_leaderboard_evidence_and_ai(session: Session, limit: int = 8) -> list[dict]:
    visuals = session.execute(
        select(VisualEvidence).where(VisualEvidence.status == "current")
        .order_by(VisualEvidence.created_at.desc(), VisualEvidence.id.desc()).limit(limit)
    ).scalars().all()
    summaries = session.execute(
        select(LocalPlan).where(LocalPlan.ai_summary_generated_at.is_not(None))
        .order_by(LocalPlan.ai_summary_generated_at.desc(), LocalPlan.id.desc()).limit(limit)
    ).scalars().all()

    rows = []
    for v in visuals:
        if v.site_id:
            page, params = "pages/1_Scheme_Detail.py", {"site_id": str(v.site_id)}
        elif v.allocation_id or v.local_plan_id:
            page, params = "pages/3_Local_Plan_Sites.py", {}
        else:
            page, params = None, None
        rows.append({
            "id": f"visual-{v.id}", "title": IMAGE_TYPE_LABELS.get(v.image_type, v.image_type),
            "subtitle": (v.source_document_title or "Visual evidence extracted")[:70], "when": v.created_at,
            "badge": "AI", "page": page, "params": params,
        })
    for p in summaries:
        rows.append({
            "id": f"ai-summary-{p.id}", "title": f"{p.plan_name} summary refreshed", "subtitle": p.council_code,
            "when": p.ai_summary_generated_at, "badge": "AI",
            "page": "pages/4_Council_Dashboard.py", "params": {},
        })
    rows.sort(key=lambda row: (_naive(row["when"]), row["id"]), reverse=True)
    return rows[:limit]


def build_leaderboard_needs_attention(session: Session, limit: int = 8) -> list[dict]:
    """Reuses the exact same three filter conditions as
    build_review_queue_counts (never redefined here), just fetching rows
    instead of a bare count."""
    suggested = session.execute(
        select(Application).where(
            Application.site_link_method == "suggested_fuzzy", Application.site_id.is_(None)
        ).order_by(Application.last_seen_at.desc(), Application.id.desc()).limit(limit)
    ).scalars().all()
    visuals = session.execute(
        select(VisualEvidence).where(
            VisualEvidence.status == "current", VisualEvidence.review_status == "needs_review"
        ).order_by(VisualEvidence.created_at.desc(), VisualEvidence.id.desc()).limit(limit)
    ).scalars().all()
    changes = session.execute(
        select(PolicyChangeEvent).where(PolicyChangeEvent.review_status == "needs_review")
        .order_by(PolicyChangeEvent.detected_at.desc(), PolicyChangeEvent.id.desc()).limit(limit)
    ).scalars().all()

    rows = []
    for a in suggested:
        rows.append({
            "id": f"suggested-{a.id}", "title": a.reference, "subtitle": (a.address or "Suggested site match")[:60],
            "when": a.last_seen_at, "badge": "Needs review",
            "page": "pages/2_Review_Site_Links.py", "params": {},
        })
    for v in visuals:
        if v.site_id:
            page, params = "pages/1_Scheme_Detail.py", {"site_id": str(v.site_id)}
        elif v.allocation_id or v.local_plan_id:
            page, params = "pages/3_Local_Plan_Sites.py", {}
        else:
            page, params = None, None
        rows.append({
            "id": f"visual-review-{v.id}", "title": IMAGE_TYPE_LABELS.get(v.image_type, v.image_type),
            "subtitle": (v.source_document_title or "Awaiting review")[:60], "when": v.created_at,
            "badge": "Needs review", "page": page, "params": params,
        })
    for e in changes:
        rows.append({
            "id": f"change-{e.id}", "title": e.event_type.replace("_", " ").title(),
            "subtitle": (e.detail or "Policy change awaiting review")[:60],
            "when": e.detected_at, "badge": "Needs review",
            "page": "pages/4_Council_Dashboard.py", "params": {},
        })

    rows.sort(key=lambda row: (_naive(row["when"]), row["id"]), reverse=True)
    return rows[:limit]


def build_leaderboard(session: Session, limit_per_tab: int = 8) -> dict[str, list[dict]]:
    """Every populated tab, keyed by its display name, ready for
    app.ui.shell.live_leaderboard. A tab with no rows is simply absent from
    this dict - the rendering layer hides it rather than this function
    inventing placeholder rows to fill an empty tab."""
    candidates = {
        "New Apps": build_leaderboard_new_applications(session, limit_per_tab),
        "Scheme Updates": build_leaderboard_updated_schemes(session, limit_per_tab),
        "Policy": build_leaderboard_policy_updates(session, limit_per_tab),
        "Evidence & AI": build_leaderboard_evidence_and_ai(session, limit_per_tab),
        "Attention": build_leaderboard_needs_attention(session, limit_per_tab),
    }
    return {name: candidates[name] for name in LEADERBOARD_TAB_ORDER if candidates[name]}


# --- Opportunity cards (hierarchy amendment) --------------------------------
#
# Deterministic-only, per Part 3's own instruction. Each card's "badge" is
# the real category it came from (never an invented urgency score) - this
# platform's own design principle is "never guess/invent a ranking," so
# priority here is expressed as which real, already-deterministic signal
# surfaced the card, not a synthesised high/medium/low weighting.

_OPPORTUNITY_CATEGORY_ORDER = (
    "low_supply", "large_unmatched", "emerging_plan", "recent_policy_activity", "recently_adopted",
)
_OPPORTUNITY_BADGES = {
    "low_supply": "Low housing supply",
    "large_unmatched": "Large allocation",
    "emerging_plan": "Emerging plan",
    "recent_policy_activity": "Policy activity",
    "recently_adopted": "Recently adopted",
}


def build_opportunity_cards(session: Session, limit_per_category: int = 2) -> list[dict]:
    """Reuses the exact same filter/order definitions as build_opportunities
    (never redefined here) but returns presentation-ready cards - a title,
    a real reason, a real metric, a category badge and a destination -
    rather than that function's plainer per-category dict shape. Order is
    always _OPPORTUNITY_CATEGORY_ORDER then the category's own existing
    sort - never a cross-category score."""
    low_supply = session.execute(
        select(LocalPlan).where(LocalPlan.five_year_supply_years.is_not(None))
        .order_by(LocalPlan.five_year_supply_years.asc(), LocalPlan.id.desc()).limit(limit_per_category)
    ).scalars().all()
    emerging_plans = session.execute(
        select(LocalPlan).where(LocalPlan.status.in_(_EMERGING_PLAN_STATUSES))
        .order_by(LocalPlan.updated_at.desc(), LocalPlan.id.desc()).limit(limit_per_category)
    ).scalars().all()
    large_unmatched = session.execute(
        select(LocalPlanSite).where(
            LocalPlanSite.matched_site_id.is_(None), LocalPlanSite.minimum_dwellings.is_not(None)
        ).order_by(LocalPlanSite.minimum_dwellings.desc(), LocalPlanSite.id.desc()).limit(limit_per_category)
    ).scalars().all()
    recent_policy_activity = session.execute(
        select(MonitoredSource.council_code, func.max(MonitoredSource.last_changed).label("last_changed"))
        .where(MonitoredSource.last_changed.is_not(None))
        .group_by(MonitoredSource.council_code)
        .order_by(func.max(MonitoredSource.last_changed).desc())
        .limit(limit_per_category)
    ).all()
    recently_adopted = session.execute(
        select(LocalPlan).where(LocalPlan.status == "adopted")
        .order_by(LocalPlan.updated_at.desc(), LocalPlan.id.desc()).limit(limit_per_category)
    ).scalars().all()

    cards: dict[str, list[dict]] = {"low_supply": [], "large_unmatched": [], "emerging_plan": [],
                                     "recent_policy_activity": [], "recently_adopted": []}

    for p in low_supply:
        cards["low_supply"].append({
            "id": f"opp-low-supply-{p.id}", "title": p.plan_name, "subtitle": p.council_code,
            "reason": "Below five-year housing land supply", "metric": f"{p.five_year_supply_years:.1f} years supply",
            "category": "low_supply", "when": p.updated_at, "page": "pages/4_Council_Dashboard.py", "params": {},
        })
    for a in large_unmatched:
        cards["large_unmatched"].append({
            "id": f"opp-large-unmatched-{a.id}", "title": a.policy_reference or a.site_name, "subtitle": a.council_code,
            "reason": "Large allocation with no application yet", "metric": f"{a.minimum_dwellings} dwellings",
            "category": "large_unmatched", "when": a.updated_at, "page": "pages/3_Local_Plan_Sites.py", "params": {},
        })
    for p in emerging_plans:
        cards["emerging_plan"].append({
            "id": f"opp-emerging-{p.id}", "title": p.plan_name, "subtitle": p.council_code,
            "reason": "Progressing toward adoption", "metric": (p.status or "unknown").replace("_", " "),
            "category": "emerging_plan", "when": p.updated_at, "page": "pages/4_Council_Dashboard.py", "params": {},
        })
    for council_code, last_changed in recent_policy_activity:
        cards["recent_policy_activity"].append({
            "id": f"opp-policy-activity-{council_code}", "title": f"{council_code} sources updated", "subtitle": council_code,
            "reason": "Monitored source content changed recently", "metric": relative_time_placeholder(last_changed),
            "category": "recent_policy_activity", "when": last_changed,
            "page": "pages/4_Council_Dashboard.py", "params": {},
        })
    for p in recently_adopted:
        cards["recently_adopted"].append({
            "id": f"opp-adopted-{p.id}", "title": p.plan_name, "subtitle": p.council_code,
            "reason": "Local Plan adopted", "metric": "Adopted",
            "category": "recently_adopted", "when": p.updated_at, "page": "pages/4_Council_Dashboard.py", "params": {},
        })

    ordered: list[dict] = []
    for category in _OPPORTUNITY_CATEGORY_ORDER:
        for card in cards[category]:
            card["badge"] = _OPPORTUNITY_BADGES[category]
            ordered.append(card)
    return ordered


def relative_time_placeholder(value: dt.datetime) -> str:
    """Opportunity cards need a metric string, not a raw datetime - this
    just isoformats the date part (no relative-time wording computed here,
    since "relative to now" is a presentation concern app.ui.shell.
    relative_time already owns; kept as a plain, honest date string at the
    data layer)."""
    return value.strftime("%d %b %Y")


# --- Recent Activity aggregation (hierarchy amendment) ----------------------
#
# build_recent_activity above is untouched (same queries, same pre-formatted
# text, still covered by its own tests) - this is a parallel, STRUCTURED
# version of the same six streams (same tables, same filters, same limits)
# whose fields (action type, source, council, id, link) are kept separate
# rather than pre-joined into one string, specifically so they can be
# grouped for display. "Do not alter, delete or merge the underlying
# database records" - nothing here writes anything; grouping happens only
# to the in-memory list this function returns.

_ACTIVITY_ACTION_LABELS = {
    "visual_evidence_extracted": ("🖼️", "visual-evidence page", "extracted from"),
    "document_discovered": ("📄", "policy document", "discovered for"),
    "plan_updated": ("📋", "Local Plan update", "for"),
    "source_changed": ("🔎", "monitored source change", "for"),
    "allocation_matched": ("🔗", "allocation match", "in"),
    "review_completed": ("✅", "review", "completed for"),
}


def build_activity_events(session: Session, limit: int = 40) -> list[dict]:
    """The same six streams as build_recent_activity, kept structured
    (action/source_key/source_label/council_code/link) instead of
    pre-formatted text, so group_activity_events can group them
    meaningfully. Never mutates or merges any database row - read-only,
    same as every other function in this module."""
    per_stream_limit = limit
    events: list[dict] = []

    for v in session.execute(
        select(VisualEvidence).where(VisualEvidence.status == "current")
        .order_by(VisualEvidence.created_at.desc(), VisualEvidence.id.desc()).limit(per_stream_limit)
    ).scalars().all():
        if v.site_id:
            page, params = "pages/1_Scheme_Detail.py", {"site_id": str(v.site_id)}
        elif v.allocation_id or v.local_plan_id:
            page, params = "pages/3_Local_Plan_Sites.py", {}
        else:
            page, params = None, None
        events.append({
            "id": f"visual-{v.id}", "action": "visual_evidence_extracted",
            "source_key": v.source_document_title or "unknown-document",
            "source_label": v.source_document_title or "an unnamed document",
            "when": v.created_at, "page": page, "params": params,
        })

    for r in session.execute(
        select(MonitoredReport).order_by(MonitoredReport.discovered_at.desc(), MonitoredReport.id.desc()).limit(per_stream_limit)
    ).scalars().all():
        events.append({
            "id": f"report-{r.id}", "action": "document_discovered",
            "source_key": r.council_code, "source_label": r.council_code,
            "when": r.discovered_at, "page": "pages/4_Council_Dashboard.py", "params": {},
        })

    for p in session.execute(
        select(LocalPlan).order_by(LocalPlan.updated_at.desc(), LocalPlan.id.desc()).limit(per_stream_limit)
    ).scalars().all():
        events.append({
            "id": f"plan-{p.id}", "action": "plan_updated",
            "source_key": p.plan_name, "source_label": p.plan_name,
            "when": p.updated_at, "page": "pages/4_Council_Dashboard.py", "params": {},
        })

    for s in session.execute(
        select(MonitoredSource).where(MonitoredSource.last_changed.is_not(None))
        .order_by(MonitoredSource.last_changed.desc(), MonitoredSource.id.desc()).limit(per_stream_limit)
    ).scalars().all():
        events.append({
            "id": f"source-{s.id}", "action": "source_changed",
            "source_key": s.council_code, "source_label": s.council_code,
            "when": s.last_changed, "page": "pages/4_Council_Dashboard.py", "params": {},
        })

    for a in session.execute(
        select(LocalPlanSite).where(LocalPlanSite.matched_site_id.is_not(None))
        .order_by(LocalPlanSite.updated_at.desc(), LocalPlanSite.id.desc()).limit(per_stream_limit)
    ).scalars().all():
        events.append({
            "id": f"allocation-{a.id}", "action": "allocation_matched",
            "source_key": a.council_code, "source_label": a.council_code,
            "when": a.updated_at, "page": "pages/3_Local_Plan_Sites.py", "params": {},
        })

    for e in session.execute(
        select(PolicyChangeEvent).where(
            PolicyChangeEvent.review_status.in_(("confirmed", "rejected")), PolicyChangeEvent.reviewed_at.is_not(None)
        ).order_by(PolicyChangeEvent.reviewed_at.desc(), PolicyChangeEvent.id.desc()).limit(per_stream_limit)
    ).scalars().all():
        events.append({
            "id": f"change-{e.id}", "action": "review_completed",
            "source_key": e.event_type, "source_label": e.event_type.replace("_", " "),
            "when": e.reviewed_at, "page": "pages/4_Council_Dashboard.py", "params": {},
        })

    events.sort(key=lambda ev: (_naive(ev["when"]), ev["id"]), reverse=True)
    return events[:limit]


def group_activity_events(events: list[dict], limit_groups: int = 10) -> list[dict]:
    """Pure, in-memory grouping only - Part 5's own "presentation
    aggregation only" instruction. Groups by (action, source_key), which is
    why unrelated activity is never grouped together: a Local Plan update
    and a policy-document discovery for the same council have different
    "action" values, so they can never merge into one row, even though
    both mention the same council."""
    groups: dict[tuple[str, str], dict] = {}
    order: list[tuple[str, str]] = []
    for ev in events:
        group_key = (ev["action"], ev["source_key"])
        if group_key not in groups:
            groups[group_key] = {
                "action": ev["action"], "source_label": ev["source_label"],
                "count": 0, "latest_when": ev["when"], "page": ev["page"], "params": ev["params"],
                "id": f"group-{ev['action']}-{ev['source_key']}",
            }
            order.append(group_key)
        groups[group_key]["count"] += 1
        if _naive(ev["when"]) > _naive(groups[group_key]["latest_when"]):
            groups[group_key]["latest_when"] = ev["when"]
            groups[group_key]["page"] = ev["page"]
            groups[group_key]["params"] = ev["params"]

    rows = []
    for group_key in order:
        g = groups[group_key]
        icon, noun, preposition = _ACTIVITY_ACTION_LABELS[g["action"]]
        noun_plural = noun if g["count"] == 1 else noun + "s"
        if g["action"] == "plan_updated" and g["count"] == 1:
            label = f"{g['source_label']} updated"
        elif g["action"] == "plan_updated":
            label = f"{g['source_label']} updated {g['count']} times"
        else:
            label = f"{g['count']} {noun_plural} {preposition} {g['source_label']}"
        rows.append({
            "id": g["id"], "icon": icon, "label": label, "count": g["count"],
            "latest_when": g["latest_when"], "page": g["page"], "params": g["params"],
        })

    rows.sort(key=lambda r: (_naive(r["latest_when"]), r["id"]), reverse=True)
    return rows[:limit_groups]


def build_grouped_activity(session: Session, limit_events: int = 40, limit_groups: int = 10) -> list[dict]:
    """Convenience wrapper - fetch then group, in one call."""
    return group_activity_events(build_activity_events(session, limit_events), limit_groups)


# --- Recent AI Summaries carousel (hierarchy amendment) ---------------------
#
# Reads already-persisted AI summaries only (LocalPlan.ai_summary_text,
# Site.status_summary) - no AI client is imported or called anywhere in
# this module, and nothing here writes to the database. Ordering is always
# generation timestamp then id - never invented relevance.

def build_ai_summary_carousel_items(session: Session, limit: int = 8) -> list[dict]:
    plans = session.execute(
        select(LocalPlan).where(LocalPlan.ai_summary_generated_at.is_not(None))
        .order_by(LocalPlan.ai_summary_generated_at.desc(), LocalPlan.id.desc()).limit(limit)
    ).scalars().all()
    sites = session.execute(
        select(Site).where(Site.status_summary.is_not(None), Site.status_summary_updated_at.is_not(None))
        .order_by(Site.status_summary_updated_at.desc(), Site.id.desc()).limit(limit)
    ).scalars().all()

    def _excerpt(text: str, length: int = 180) -> str:
        text = (text or "").strip()
        return text if len(text) <= length else text[:length].rsplit(" ", 1)[0] + "…"

    items = [
        {
            "id": f"carousel-plan-{p.id}", "type": "Local Plan Summary", "name": p.plan_name,
            "council_code": p.council_code, "excerpt": _excerpt(p.ai_summary_text),
            "generated_at": p.ai_summary_generated_at, "model": p.ai_summary_model,
            "page": "pages/4_Council_Dashboard.py", "params": {},
        }
        for p in plans
    ] + [
        {
            "id": f"carousel-site-{s.id}", "type": "Site Summary", "name": s.display_address,
            "council_code": s.council_code, "excerpt": _excerpt(s.status_summary),
            "generated_at": s.status_summary_updated_at, "model": None,
            "page": "pages/1_Scheme_Detail.py", "params": {"site_id": str(s.id)},
        }
        for s in sites
    ]
    items.sort(key=lambda it: (_naive(it["generated_at"]), it["id"]), reverse=True)
    return items[:limit]


# --- Planning Intelligence scheme stack (Dashboard refinement) -------------
#
# Replaces the leaderboard's plain rows with richer, per-scheme cards for
# the stacked-card presentation. Every field is read from Application,
# SchemeIntelligence (via the existing .scheme_intelligence relationship,
# always eager-loaded via selectinload below - never a per-row lazy query)
# and Site - the exact same tables the rest of this module already reads,
# batched with the same one-query-per-stream discipline as everything
# above. "Do not show None/zero for missing facts" is enforced entirely at
# render time (app.ui.shell) - this module always returns every key so the
# rendering layer has a single, predictable shape to check.

SCHEME_STACK_TAB_ORDER = ("New Applications", "Scheme Updates", "Decision Changes", "Build Progress", "Needs Attention")


def _scheme_card(app: Application, *, why: str, when, page: str | None = None, params: dict | None = None) -> dict:
    si = app.scheme_intelligence
    site = app.site
    resolved_page, resolved_params = (page, params if params is not None else {}) if page else (
        ("pages/1_Scheme_Detail.py", {"site_id": str(app.site_id)}) if app.site_id else (None, None)
    )
    decision_status = classify_decision_status(app.decision, app.status)
    build_status_raw = site.build_status if site else None
    return {
        "id": f"scheme-{app.id}",
        "reference": app.reference,
        "council_code": app.council_code,
        "address": app.address,
        "total_units": si.total_units_final if si else None,
        "affordable_units": si.affordable_units_final if si else None,
        "affordable_percentage": si.affordable_percentage_final if si else None,
        "planning_status": app.status,
        "decision_status": DECISION_STATUS_LABELS.get(decision_status) if decision_status != "not_yet_decided" else None,
        "build_status": BUILD_STATUS_LABELS.get(build_status_raw) if build_status_raw else None,
        "developer": si.developer if si else None,
        "why": why,
        "when": when,
        "page": resolved_page, "params": resolved_params,
    }


def _load_primary_application_by_site(session: Session, site_ids: list[int]) -> dict[int, Application]:
    """One batched query - the most recently-updated Application per site,
    for a caller (e.g. build_scheme_stack's Build Progress tab) that has a
    list of Sites but needs an Application to build a scheme card from.
    Never one query per site."""
    if not site_ids:
        return {}
    apps = session.execute(
        select(Application).options(selectinload(Application.scheme_intelligence), selectinload(Application.site))
        .where(Application.site_id.in_(site_ids))
        .order_by(Application.site_id, Application.last_seen_at.desc(), Application.id.desc())
    ).scalars().all()
    by_site: dict[int, Application] = {}
    for a in apps:
        by_site.setdefault(a.site_id, a)
    return by_site


def build_scheme_stack(session: Session, limit_per_tab: int = 8) -> dict[str, list[dict]]:
    """Every populated tab, keyed by its display name - a tab with no rows
    is simply absent (same convention as build_leaderboard), never an
    invented empty placeholder tab."""
    tabs: dict[str, list[dict]] = {}
    load_opts = (selectinload(Application.scheme_intelligence), selectinload(Application.site))

    new_apps = session.execute(
        select(Application).options(*load_opts)
        .order_by(Application.first_seen_at.desc(), Application.id.desc()).limit(limit_per_tab)
    ).scalars().all()
    if new_apps:
        tabs["New Applications"] = [_scheme_card(a, why="New application scraped", when=a.first_seen_at) for a in new_apps]

    updated = session.execute(
        select(Application).options(*load_opts)
        .where(Application.site_id.is_not(None))
        .order_by(Application.last_seen_at.desc(), Application.id.desc()).limit(limit_per_tab)
    ).scalars().all()
    if updated:
        tabs["Scheme Updates"] = [_scheme_card(a, why="Application details refreshed", when=a.last_seen_at) for a in updated]

    # decision_issued_date is free text (portal-native formats), not a real
    # date column - fetched a little wider then re-sorted by the same
    # parse_portal_date already used throughout app.pipeline.lapse_tracking,
    # rather than trusting an unreliable string ORDER BY.
    decided_candidates = session.execute(
        select(Application).options(*load_opts)
        .where(Application.decision.is_not(None), Application.decision_issued_date.is_not(None))
        .order_by(Application.last_seen_at.desc(), Application.id.desc()).limit(limit_per_tab * 3)
    ).scalars().all()
    decided = sorted(decided_candidates, key=lambda a: parse_portal_date(a.decision_issued_date), reverse=True)[:limit_per_tab]
    if decided:
        tabs["Decision Changes"] = [_scheme_card(a, why=f"Decision issued: {a.decision}", when=a.last_seen_at) for a in decided]

    build_sites = session.execute(
        select(Site).where(Site.build_status.is_not(None), Site.excluded.is_not(True))
        .order_by(Site.build_status_checked_at.desc(), Site.id.desc()).limit(limit_per_tab)
    ).scalars().all()
    if build_sites:
        apps_by_site = _load_primary_application_by_site(session, [s.id for s in build_sites])
        rows = [
            _scheme_card(
                apps_by_site[s.id],
                why=f"Build status: {BUILD_STATUS_LABELS.get(s.build_status, s.build_status)}",
                when=s.build_status_checked_at,
            )
            for s in build_sites if s.id in apps_by_site
        ]
        if rows:
            tabs["Build Progress"] = rows

    # Needs Attention - the scheme-scoped slice of the platform's review
    # backlog (suggested site links only have a real "scheme" shape;
    # PolicyChangeEvent items belong to a council/plan, not a scheme, so
    # they're deliberately left out of this specific stack).
    suggested = session.execute(
        select(Application).options(*load_opts)
        .where(Application.site_link_method == "suggested_fuzzy", Application.site_id.is_(None))
        .order_by(Application.last_seen_at.desc(), Application.id.desc()).limit(limit_per_tab)
    ).scalars().all()
    if suggested:
        tabs["Needs Attention"] = [
            _scheme_card(
                a, why="Suggested site match awaiting review", when=a.last_seen_at,
                page="pages/2_Review_Site_Links.py", params={},
            )
            for a in suggested
        ]

    return {name: tabs[name] for name in SCHEME_STACK_TAB_ORDER if tabs.get(name)}


# --- Opportunity categories (Dashboard refinement) --------------------------
#
# Each category builder below reuses an already-established filter/order
# definition where one exists (low_supply, allocations_without_application,
# emerging_policy, recent_policy_activity, recently_adopted all mirror
# build_opportunities/build_opportunity_cards' own conditions exactly -
# never redefined) - only approaching_lapse and undeveloped_phase are
# genuinely new, and both are built entirely from existing, already-tested
# deterministic modules (app.pipeline.lapse_tracking.compute_lapse_status,
# app.pipeline.phase_tracking.build_phase_breakdown) rather than new
# ranking/scoring logic of their own.

_OPPORTUNITY_SECTION_ORDER = (
    "approaching_lapse", "low_supply", "undeveloped_phase", "allocations_without_application",
    "emerging_policy", "recent_policy_activity", "recently_adopted",
)
_OPPORTUNITY_SECTION_META = {
    "approaching_lapse": {
        "heading": "Approaching lapse date",
        "explanation": f"Full permissions with no build activity detected, within {LAPSE_WARNING_DAYS} days of their statutory commencement deadline.",
    },
    "low_supply": {
        "heading": "Low housing supply",
        "explanation": "Councils with a verified five-year housing land supply position below five years.",
    },
    "undeveloped_phase": {
        "heading": "Undeveloped phase / remaining delivery",
        "explanation": "Multi-phase schemes with a named phase that has full permission but no commencement filing since.",
    },
    "allocations_without_application": {
        "heading": "Allocations without planning applications",
        "explanation": "Confirmed Local Plan allocations with no linked planning application yet.",
    },
    "emerging_policy": {
        "heading": "Emerging policy opportunity",
        "explanation": "Local Plans still progressing toward adoption - not yet settled.",
    },
    "recent_policy_activity": {
        "heading": "Recent policy activity",
        "explanation": "Councils whose monitored policy sources have changed recently.",
    },
    "recently_adopted": {
        "heading": "Recently adopted plans",
        "explanation": "Local Plans that have reached adopted status.",
    },
}


def _approaching_lapse_cards(session: Session, limit: int) -> list[dict]:
    granted_filter = or_(*(Application.decision.ilike(f"%{kw}%") for kw in GRANTED_KEYWORDS))
    granted_site_ids = list(session.execute(
        select(Application.site_id).where(
            Application.site_id.is_not(None), Application.decision_issued_date.is_not(None), granted_filter,
        ).distinct()
    ).scalars())
    if not granted_site_ids:
        return []
    sites = session.execute(
        select(Site).where(Site.id.in_(granted_site_ids), Site.excluded.is_not(True))
    ).scalars().all()
    apps = session.execute(
        select(Application).where(Application.site_id.in_([s.id for s in sites]))
    ).scalars().all() if sites else []
    apps_by_site: dict[int, list[Application]] = {}
    for a in apps:
        apps_by_site.setdefault(a.site_id, []).append(a)

    today = dt.date.today()
    scored: list[tuple[int, dict]] = []
    for site in sites:
        result = compute_lapse_status(apps_by_site.get(site.id, []), site)
        if result["status"] != "approaching" or result["deadline"] is None:
            continue
        days_left = (result["deadline"] - today).days
        grant_date = parse_portal_date(result["granted_app"].decision_issued_date) if result["granted_app"] else None
        scored.append((days_left, {
            "id": f"opp-lapse-{site.id}", "title": site.display_address, "subtitle": site.council_code,
            "reason": f"Commencement deadline {result['deadline'].strftime('%d %b %Y')} - no build activity detected since the grant",
            "metric": f"{days_left} day{'s' if days_left != 1 else ''} left",
            "when": dt.datetime.combine(grant_date, dt.time.min) if grant_date else None,
            "page": "pages/1_Scheme_Detail.py", "params": {"site_id": str(site.id)},
        }))
    scored.sort(key=lambda pair: pair[0])
    return [card for _, card in scored[:limit]]


def _low_supply_cards(session: Session, limit: int) -> list[dict]:
    rows = session.execute(
        select(LocalPlan).where(LocalPlan.five_year_supply_years.is_not(None), LocalPlan.five_year_supply_years < 5)
        .order_by(LocalPlan.five_year_supply_years.asc(), LocalPlan.id.desc()).limit(limit)
    ).scalars().all()
    return [{
        "id": f"opp-low-supply-{p.id}", "title": p.plan_name, "subtitle": p.council_code,
        "reason": "Verified housing land supply below the five-year threshold",
        "metric": f"{p.five_year_supply_years:.2f} years supply",
        "when": p.updated_at, "page": "pages/4_Council_Dashboard.py", "params": {},
    } for p in rows]


def _undeveloped_phase_cards(session: Session, limit: int) -> list[dict]:
    """Bounded to Sites with 2+ linked applications - build_phase_breakdown
    needs multiple filings to detect a phase at all, and returns [] for a
    single-application site by its own definition. One batched query for
    every Application/Site involved; phase detection itself
    (app.pipeline.phase_tracking) is pure Python over already-fetched rows,
    never a further query per site."""
    apps = session.execute(
        select(Application).where(Application.site_id.is_not(None))
        .join(Site, Application.site_id == Site.id).where(Site.excluded.is_not(True))
        .options(selectinload(Application.scheme_intelligence))
    ).scalars().all()
    by_site: dict[int, list[Application]] = {}
    for a in apps:
        by_site.setdefault(a.site_id, []).append(a)

    candidate_site_ids = [sid for sid, group in by_site.items() if len(group) >= 2]
    if not candidate_site_ids:
        return []
    sites = {s.id: s for s in session.execute(select(Site).where(Site.id.in_(candidate_site_ids))).scalars()}

    cards: list[dict] = []
    for site_id in candidate_site_ids:
        site = sites.get(site_id)
        if site is None:
            continue
        breakdown = build_phase_breakdown(by_site[site_id])
        undeveloped = [row for row in breakdown if row["status"] == "approved_not_started"]
        if not undeveloped:
            continue
        phase = undeveloped[0]
        grant_date = (
            parse_portal_date(phase["latest_grant"].decision_issued_date) if phase.get("latest_grant") else None
        )
        cards.append({
            "id": f"opp-phase-{site.id}-{phase['code']}", "title": f"{site.display_address} — {phase['label']}",
            "subtitle": site.council_code,
            "reason": f"{phase['label']} has full permission but no commencement filing detected since the grant",
            "metric": f"{len(undeveloped)} phase(s) not yet started" if len(undeveloped) > 1 else "Not yet started",
            "when": dt.datetime.combine(grant_date, dt.time.min) if grant_date else site.updated_at,
            "page": "pages/1_Scheme_Detail.py", "params": {"site_id": str(site.id)},
        })
    cards.sort(key=lambda c: _naive(c["when"]), reverse=True)
    return cards[:limit]


def _allocations_without_application_cards(session: Session, limit: int) -> list[dict]:
    rows = session.execute(
        select(LocalPlanSite).where(
            LocalPlanSite.matched_site_id.is_(None), LocalPlanSite.minimum_dwellings.is_not(None)
        ).order_by(LocalPlanSite.minimum_dwellings.desc(), LocalPlanSite.id.desc()).limit(limit)
    ).scalars().all()
    return [{
        "id": f"opp-unmatched-{a.id}", "title": a.policy_reference or a.site_name, "subtitle": a.council_code,
        "reason": "Confirmed allocation with no linked planning application yet",
        "metric": f"{a.minimum_dwellings} dwellings",
        # Website V2 - deep-links straight to this allocation's own detail
        # view (app/ui/pages/3_Local_Plan_Sites.py already supports
        # ?allocation_id=<id>, used elsewhere on that same page) rather than
        # the bare allocation-list page a user then had to search from
        # scratch - cuts the Dashboard -> opportunity journey from three-
        # plus clicks to one.
        "when": a.updated_at, "page": "pages/3_Local_Plan_Sites.py", "params": {"allocation_id": str(a.id)},
    } for a in rows]


def _emerging_policy_cards(session: Session, limit: int) -> list[dict]:
    rows = session.execute(
        select(LocalPlan).where(LocalPlan.status.in_(_EMERGING_PLAN_STATUSES))
        .order_by(LocalPlan.updated_at.desc(), LocalPlan.id.desc()).limit(limit)
    ).scalars().all()
    return [{
        "id": f"opp-emerging-{p.id}", "title": p.plan_name, "subtitle": p.council_code,
        "reason": "Progressing toward adoption - not yet settled",
        "metric": (p.status or "unknown").replace("_", " "),
        "when": p.updated_at, "page": "pages/4_Council_Dashboard.py", "params": {},
    } for p in rows]


def _recent_policy_activity_cards(session: Session, limit: int) -> list[dict]:
    rows = session.execute(
        select(MonitoredSource.council_code, func.max(MonitoredSource.last_changed).label("last_changed"))
        .where(MonitoredSource.last_changed.is_not(None))
        .group_by(MonitoredSource.council_code)
        .order_by(func.max(MonitoredSource.last_changed).desc())
        .limit(limit)
    ).all()
    return [{
        "id": f"opp-policy-activity-{council_code}", "title": f"{council_code} monitored sources updated", "subtitle": council_code,
        "reason": "Monitored source content changed recently", "metric": relative_time_placeholder(last_changed),
        "when": last_changed, "page": "pages/4_Council_Dashboard.py", "params": {},
    } for council_code, last_changed in rows]


def _recently_adopted_cards(session: Session, limit: int) -> list[dict]:
    rows = session.execute(
        select(LocalPlan).where(LocalPlan.status == "adopted")
        .order_by(LocalPlan.updated_at.desc(), LocalPlan.id.desc()).limit(limit)
    ).scalars().all()
    return [{
        "id": f"opp-adopted-{p.id}", "title": p.plan_name, "subtitle": p.council_code,
        "reason": "Local Plan reached adopted status", "metric": "Adopted",
        "when": p.updated_at, "page": "pages/4_Council_Dashboard.py", "params": {},
    } for p in rows]


_OPPORTUNITY_CATEGORY_BUILDERS = {
    "approaching_lapse": _approaching_lapse_cards,
    "low_supply": _low_supply_cards,
    "undeveloped_phase": _undeveloped_phase_cards,
    "allocations_without_application": _allocations_without_application_cards,
    "emerging_policy": _emerging_policy_cards,
    "recent_policy_activity": _recent_policy_activity_cards,
    "recently_adopted": _recently_adopted_cards,
}


def build_opportunity_categories(session: Session, limit_per_category: int = 4) -> list[dict]:
    """One entry per category in _OPPORTUNITY_SECTION_ORDER - every category
    here is genuinely calculable from existing evidence (see each builder's
    own docstring/comment), so none needs an "unavailable" state today; the
    shape still carries "available"/"unavailable_reason" so a future
    category that genuinely can't be computed yet has somewhere honest to
    say so, per this task's own "do not fabricate it" instruction."""
    categories = []
    for key in _OPPORTUNITY_SECTION_ORDER:
        cards = _OPPORTUNITY_CATEGORY_BUILDERS[key](session, limit_per_category)
        meta = _OPPORTUNITY_SECTION_META[key]
        categories.append({
            "key": key, "heading": meta["heading"], "explanation": meta["explanation"],
            "count": len(cards), "cards": cards, "available": True, "unavailable_reason": None,
        })
    return categories


# --- AI Summary rail relevance (Dashboard refinement, Part 9) ---------------
#
# Extends build_ai_summary_carousel_items (untouched, still covered by its
# own tests) rather than duplicating its query - relevance is computed
# entirely from fields already present on the same LocalPlan/Site rows a
# small, additional batched fetch loads (two more queries total, not one
# per carousel item), never a fresh per-item lookup.

def _plan_relevance(plan: LocalPlan) -> str:
    if plan.five_year_supply_years is not None and plan.five_year_supply_years < 5:
        return f"{plan.five_year_supply_years:.2f} years of verified housing land supply - below the five-year threshold"
    if plan.content_last_updated and plan.ai_summary_generated_at and _naive(plan.content_last_updated) > _naive(plan.ai_summary_generated_at):
        return "The underlying evidence has changed since this summary was generated"
    if plan.status in _EMERGING_PLAN_STATUSES and plan.next_milestone:
        return f"Emerging plan - next milestone: {plan.next_milestone}"
    if plan.status == "adopted":
        return "This Local Plan has reached adopted status"
    return "Generated recently from verified evidence"


def _site_relevance(site: Site) -> str:
    if site.status_summary_updated_at and site.updated_at and _naive(site.updated_at) >= _naive(site.status_summary_updated_at):
        return "This Site has a recent planning update"
    if site.build_status in ("complete", "partially_complete"):
        return f"Build status: {BUILD_STATUS_LABELS.get(site.build_status, site.build_status)}"
    return "Generated recently from verified evidence"


def build_ai_summary_rail(session: Session, limit: int = 8) -> list[dict]:
    """build_ai_summary_carousel_items's own items, each carrying a
    deterministic "relevance" explanation - never a new AI call, never
    altering the original ai_summary_text, never a new database write."""
    items = build_ai_summary_carousel_items(session, limit)
    if not items:
        return []

    plan_ids = [int(it["id"].rsplit("-", 1)[-1]) for it in items if it["id"].startswith("carousel-plan-")]
    site_ids = [int(it["id"].rsplit("-", 1)[-1]) for it in items if it["id"].startswith("carousel-site-")]
    plans_by_id = {p.id: p for p in session.execute(select(LocalPlan).where(LocalPlan.id.in_(plan_ids))).scalars()} if plan_ids else {}
    sites_by_id = {s.id: s for s in session.execute(select(Site).where(Site.id.in_(site_ids))).scalars()} if site_ids else {}

    enriched = []
    for it in items:
        if it["id"].startswith("carousel-plan-"):
            plan = plans_by_id.get(int(it["id"].rsplit("-", 1)[-1]))
            relevance = _plan_relevance(plan) if plan else "Generated recently from verified evidence"
        else:
            site = sites_by_id.get(int(it["id"].rsplit("-", 1)[-1]))
            relevance = _site_relevance(site) if site else "Generated recently from verified evidence"
        enriched.append({**it, "relevance": relevance})
    return enriched


def build_dashboard(session: Session) -> dict:
    """Everything the Dashboard page needs, assembled in one call so the
    page itself stays a pure rendering layer (CLAUDE.md's "keep business
    logic out of the UI")."""
    return {
        "kpis": build_kpi_row(session),
        "planning": build_planning_intelligence(session),
        "policy": build_policy_intelligence(session),
        "opportunities": build_opportunities(session),
        "opportunity_cards": build_opportunity_cards(session),
        "activity": build_recent_activity(session),
        "activity_grouped": build_grouped_activity(session),
        "leaderboard": build_leaderboard(session),
        "ai_summary_carousel": build_ai_summary_carousel_items(session),
        "scheme_stack": build_scheme_stack(session),
        "opportunity_categories": build_opportunity_categories(session),
        "ai_summary_rail": build_ai_summary_rail(session),
        "generated_at": dt.datetime.now(dt.timezone.utc),
    }
