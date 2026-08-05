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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

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
        {"label": "AI summaries", "value": ai_local_plan_summaries + ai_site_summaries, "live": True,
         "help": f"{ai_local_plan_summaries} Local Plan summaries + {ai_site_summaries} Site summaries generated."},
        {"label": "Review queue", "value": review_queue["total"], "live": True,
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

LEADERBOARD_TAB_ORDER = ("New Applications", "Updated Schemes", "Policy Updates", "Evidence & AI", "Needs Attention")


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
        "New Applications": build_leaderboard_new_applications(session, limit_per_tab),
        "Updated Schemes": build_leaderboard_updated_schemes(session, limit_per_tab),
        "Policy Updates": build_leaderboard_policy_updates(session, limit_per_tab),
        "Evidence & AI": build_leaderboard_evidence_and_ai(session, limit_per_tab),
        "Needs Attention": build_leaderboard_needs_attention(session, limit_per_tab),
    }
    return {name: candidates[name] for name in LEADERBOARD_TAB_ORDER if candidates[name]}


def build_dashboard(session: Session) -> dict:
    """Everything the Dashboard page needs, assembled in one call so the
    page itself stays a pure rendering layer (CLAUDE.md's "keep business
    logic out of the UI")."""
    return {
        "kpis": build_kpi_row(session),
        "planning": build_planning_intelligence(session),
        "policy": build_policy_intelligence(session),
        "opportunities": build_opportunities(session),
        "activity": build_recent_activity(session),
        "leaderboard": build_leaderboard(session),
        "generated_at": dt.datetime.now(dt.timezone.utc),
    }
