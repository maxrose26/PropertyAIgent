"""Site Profile view-model assembly (Sprint 4.4, "Flagship Site Profile").

A pure module, no Streamlit imports, mirroring app.reporting.council_intelligence's
own discipline (CLAUDE.md's "keep business logic out of the UI"). This module
adds NO new intelligence engine - every figure here is read from data already
computed by app.ui.common (aggregate_scheme_fields, pick_representative_application),
app.pipeline.lapse_tracking, app.pipeline.phase_tracking, app.policy.site_view and
app.visuals.site_view, reshaped for the flagship, tabbed Site Profile experience.
Where a figure genuinely doesn't exist yet, it stays None/omitted and the caller
(the UI layer) renders an honest "not yet verified" - nothing here ever fabricates
or estimates a value, and nothing here ever implies planning permission is more
or less likely than the evidence actually supports.

aggregate_scheme_fields/pick_representative_application/compute_lapse_status/
build_phase_breakdown are deliberately NOT called from within this module (even
though they're pure functions) - they're computed once by the caller (the Site
Profile page) and passed in here as already-computed dicts, the same pattern
app.ui.site_headline.build_site_headline already established, so this module
never has to import app.ui.common (which imports Streamlit and the OpenAI
client) just to reach two pure helper functions.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Application, LocalPlan, LocalPlanSite, PolicyChangeEvent, Site, VisualEvidence
from app.pipeline.lapse_tracking import (
    BUILD_STATUS_LABELS,
    DECISION_STATUS_LABELS,
    LAPSE_STATUS_LABELS,
    PROGRESS_SIGNAL_CATEGORIES,
    parse_portal_date,
)
from app.policy.site_view import build_site_policy_intelligence
from app.reporting.residential_mix import build_residential_mix, format_affordable_tile
from app.reporting.scheme_reconciliation import FACT_RESOLVED, build_operative_planning_facts
from app.visuals import IMAGE_TYPE_LABELS
from app.visuals.site_view import build_site_visual_evidence

# A council-agnostic, platform-defined threshold for what this Site Profile
# calls a "major" scheme in its Opportunity Position wording - deliberately
# well above the platform's own 10-unit qualifying threshold (see
# app.scrapers.unit_filter), since "qualifies at all" and "genuinely major
# scale" are different signals. Not a statutory or council-specific figure -
# just this platform's own, clearly-labelled bar for the phrase "major".
MAJOR_UNIT_THRESHOLD = 100

FIVE_YEAR_SUPPLY_WARNING_THRESHOLD = 5.0

# Friendly Timeline labels for allocation-scoped PolicyChangeEvent rows -
# a small, local copy of the same event_type vocabulary
# app.reporting.council_intelligence's own _TIMELINE_EVENT_LABELS uses,
# kept independent rather than imported since council_intelligence's
# version is keyed to "{plan_name}" phrasing appropriate for a council-wide
# timeline, not a single Site's.
_POLICY_EVENT_LABELS: dict[str, str] = {
    "new_allocation": "This site's allocation was added to the Local Plan",
    "allocation_removed": "This site's allocation was removed from the Local Plan",
    "allocation_amended": "This site's allocation was amended",
    "capacity_changed": "This allocation's capacity changed",
    "adoption": "The Local Plan reached adopted status",
    "stage_change": "The Local Plan moved to a new stage",
}


def _fmt_units(n: int | None) -> str | None:
    return f"{n:,}" if n is not None else None


# --- Header -------------------------------------------------------------


def build_site_header(
    *, site: Site, merged: dict, lapse: dict, decision_status: str | None,
    policy_rows: list[dict], last_ai_summary_at: dt.datetime | None,
    latest_visual_evidence_at: dt.datetime | None,
) -> dict:
    """Executive header badges/facts (Part 2) - every value is either a
    real fact or None, never a placeholder string like "None"/0 for
    something genuinely unknown, so the page can cleanly omit rather than
    show a misleading default."""
    build_status = lapse.get("build_status")
    allocation_badge = None
    if policy_rows:
        row = policy_rows[0]
        allocation_badge = f"{row['allocation_reference'] or row['allocation_name']}" + (
            f" ({row['plan_status'] or 'status unknown'})" if row["plan_status"] else ""
        )

    last_updated_candidates = [t for t in (last_ai_summary_at, latest_visual_evidence_at) if t is not None]

    return {
        "address": site.display_address,
        "council_code": site.council_code,
        "primary_reference": None,  # filled in by the caller once rep_app is known
        "planning_status_label": None,  # filled in by the caller (rep_app.status is raw portal text)
        "decision_status_label": DECISION_STATUS_LABELS.get(decision_status) if decision_status else None,
        "build_status_label": BUILD_STATUS_LABELS.get(build_status) if build_status not in (None, "unknown") else None,
        "lapse_status_label": LAPSE_STATUS_LABELS.get(lapse["status"]) if lapse["status"] not in (None, "unknown") else None,
        "allocation_badge": allocation_badge,
        "latest_evidence_update": max(last_updated_candidates) if last_updated_candidates else None,
    }


# --- Headline metrics -----------------------------------------------------


def build_headline_metrics(
    merged: dict, lapse: dict, decision_status: str | None, affordable_headline: dict,
    *, operative_total: int | None = None, operative_total_is_estimated: bool = False,
    operative_total_basis: str | None = None, operative_total_not_determined: bool = False,
) -> list[dict]:
    """Four consistent headline tiles (Part 3) - the same set, same order,
    on every Site Profile, never swapped per site depending on which
    evidence happens to be available. "Evidence" is deliberately not one
    of these four - evidence freshness/review state is secondary
    information.

    affordable_headline is app.reporting.residential_mix.
    compute_affordable_headline's own output for the site's current
    preferred scheme version (Residential Mix Intelligence, Sprint 4.4
    Amendment Part 4/5) - sourced from that ONE application's
    scheme_intelligence row, never the cross-application `merged` dict
    used for the other three tiles, since affordable units and the total
    they're a percentage of must never come from two different scheme
    versions (Part 5's "never mix affordable units from one scheme
    version with total homes from another")."""
    # Gate 2B-1: prefer the fact-level operative total (approved where
    # consent exists, else proposed) over aggregate_scheme_fields's
    # first-non-null `total_units_final`, which can be sourced from a
    # non-substantive or superseded application.
    #   - operative_total set                -> use it.
    #   - operative_total_not_determined     -> reconciliation RAN and
    #     deliberately found no operative residential quantum (Gate 2B-1
    #     Defect 2 - e.g. Stockport Rugby Club, only substantive
    #     application withdrawn + specialist accommodation present). Show
    #     the unresolved state; do NOT fall back to legacy `merged` facts.
    #   - neither                            -> reconciliation could not
    #     run at all; the legacy `merged` fallback stands.
    if operative_total is not None:
        total_display = _fmt_units(operative_total)
        if total_display and operative_total_is_estimated:
            total_display += " (est.)"
        if total_display and operative_total_basis:
            total_display += f" ({operative_total_basis})"
    elif operative_total_not_determined:
        total_display = None
    else:
        total = merged.get("total_units_final")
        total_display = _fmt_units(total)
        if total_display and merged.get("total_units_is_estimated"):
            total_display += " (est.)"

    affordable_value, affordable_caption = format_affordable_tile(affordable_headline)

    build_status = lapse.get("build_status")
    build_display = BUILD_STATUS_LABELS.get(build_status) if build_status not in (None, "unknown") else "Not yet verified"

    decision_display = DECISION_STATUS_LABELS.get(decision_status) if decision_status else "Not yet verified"

    return [
        {"label": "Total homes", "value": total_display or "Not yet verified", "caption": None},
        {"label": "Affordable homes", "value": affordable_value, "caption": affordable_caption},
        {"label": "Decision status", "value": decision_display, "caption": None},
        {"label": "Build status", "value": build_display, "caption": None},
    ]


# --- Opportunity Position ---------------------------------------------------


def _council_five_year_supply(session: Session, council_code: str, policy_rows: list[dict]) -> dict | None:
    """One small, bounded extra query (documented in Part 15's query-count
    accounting) - every LocalPlan for this Site's council, filtered in
    Python to whichever have a verified five_year_supply_years figure.
    Prefers the plan this Site's own allocation(s) actually belong to,
    where one is matched; otherwise the plan with the lowest (most
    pressing) verified figure - never averaged, never inferred from an
    unrelated plan."""
    plans = session.execute(select(LocalPlan).where(LocalPlan.council_code == council_code)).scalars().all()
    with_supply = [p for p in plans if p.five_year_supply_years is not None]
    if not with_supply:
        return None
    matched_names = {row["plan_name"] for row in policy_rows}
    preferred = [p for p in with_supply if p.plan_name in matched_names]
    plan = preferred[0] if preferred else min(with_supply, key=lambda p: p.five_year_supply_years)
    return {"plan_name": plan.plan_name, "years": plan.five_year_supply_years}


def build_opportunity_position(
    *, merged: dict, lapse: dict, phase_breakdown: list[dict], policy_rows: list[dict],
    council_supply: dict | None, has_missing_evidence: bool,
) -> dict:
    """A concise, deterministic "Opportunity Position" (Part 4) - never a
    planning-permission prediction. Every reason below is derived from a
    structured fact already held elsewhere on this page; wording is
    deliberately hedged ("may represent", "may increase pressure") and
    never claims permission is likely or unlikely, per the brief's
    explicit "do not use: Planning permission likely / Strong chance of
    approval / invented investment recommendations."."""
    reasons: list[str] = []

    total = merged.get("total_units_final")
    if total is not None and total >= MAJOR_UNIT_THRESHOLD:
        reasons.append(f"Major scheme recorded — {total:,} homes.")

    approved_not_started_units = None
    if phase_breakdown:
        approved_not_started = [p for p in phase_breakdown if p["status"] == "approved_not_started"]
        if approved_not_started:
            known_units = [p["unit_count"] for p in approved_not_started if p.get("unit_count")]
            approved_not_started_units = sum(known_units) if known_units else None
            unit_bit = f" ({approved_not_started_units:,} units)" if approved_not_started_units else ""
            reasons.append(
                f"{len(approved_not_started)} phase(s) have full planning permission but no confirmed "
                f"commencement filing since{unit_bit} — an undeveloped phase."
            )
    elif lapse["status"] in ("safe", "approaching") and lapse.get("build_status") in (None, "unknown", "no_completions_yet"):
        reasons.append("Major permitted scheme recorded as not yet commenced.")

    if lapse["status"] == "approaching" and lapse.get("deadline"):
        deadline = lapse["deadline"]
        reasons.append(f"Commencement deadline approaching ({deadline.strftime('%d %b %Y')}) with no build activity detected.")
    elif lapse["status"] == "lapsed":
        reasons.append("The statutory commencement deadline has passed with no build activity detected — permission may have lapsed.")

    if policy_rows:
        row = policy_rows[0]
        plan_status = (row["plan_status"] or "").lower()
        if plan_status == "adopted":
            reasons.append("Local Plan allocation recorded for this site.")
        else:
            reasons.append("Emerging Local Plan allocation recorded for this site — not yet adopted.")

    if council_supply is not None and council_supply["years"] < FIVE_YEAR_SUPPLY_WARNING_THRESHOLD:
        reasons.append(
            f"The council has a verified housing land supply below five years "
            f"({council_supply['years']:g} years, {council_supply['plan_name']})."
        )

    if has_missing_evidence:
        reasons.append("Some evidence for this site is missing or has not yet been verified.")

    if not reasons:
        headline = "No standout structured signals identified from currently held evidence."
        why_it_matters = "Nothing in the evidence currently held for this site stands out against the platform's own opportunity signals."
        investigate_next = "Review the Planning Position and Policy Position tabs for the full evidence base."
    else:
        headline = reasons[0]
        # "Why it matters"/"Investigate next" are grounded in whichever
        # signal is most decision-relevant, in the same priority order the
        # reasons themselves were checked above.
        if any("undeveloped phase" in r or "not yet commenced" in r for r in reasons):
            why_it_matters = "A phase or the whole scheme has full permission with no confirmed start of works, which may represent an acquisition opportunity."
            investigate_next = "Confirm current site control and developer intentions before approaching."
        elif any("deadline" in r or "lapsed" in r for r in reasons):
            why_it_matters = "The statutory commencement deadline is a real legal event that may affect whether this permission remains valid."
            investigate_next = "Check the granted application's own conditions and any recent site activity before relying on this permission."
        elif council_supply is not None and council_supply["years"] < FIVE_YEAR_SUPPLY_WARNING_THRESHOLD:
            why_it_matters = "The council's housing land supply position may increase pressure to bring forward deliverable sites."
            investigate_next = "Review the Policy Position tab for the underlying housing supply evidence."
        elif any("allocation" in r for r in reasons):
            why_it_matters = "Local Plan allocation status indicates the council's own planning intent for this site."
            investigate_next = "Review the Policy Position tab for the allocation's own capacity and progression evidence."
        else:
            why_it_matters = "Recent evidence indicates a change worth reviewing before drawing conclusions."
            investigate_next = "Review the Planning Position tab for the full application history."

    return {"headline": headline, "reasons": reasons, "why_it_matters": why_it_matters, "investigate_next": investigate_next}


# --- Policy Position tab ----------------------------------------------------


def build_policy_position(policy_rows: list[dict], council_supply: dict | None) -> dict:
    """Reshapes app.policy.site_view.build_site_policy_intelligence's own
    rows for the Policy Position tab (Part 8), plus an honest explanation
    when no allocation is linked - the platform's own allocation-to-Site
    matching (app.extraction.local_plan.match_to_existing_sites) only ever
    runs FROM the allocation side, at ingestion time, so a Site with no
    matched allocation genuinely cannot be distinguished here between "not
    allocated in any Local Plan" and "allocated somewhere, but this
    platform's matching hasn't linked it yet" - the honest answer names
    both possibilities rather than picking one, per the brief's explicit
    "explain the distinction... where the evidence does not support a
    definitive conclusion."."""
    if not policy_rows:
        return {
            "allocations": [],
            "no_allocation_message": (
                "No Local Plan allocation has been matched to this site. This does not necessarily mean the "
                "site is not allocated — the platform's allocation matching runs from each Local Plan "
                "allocation outward, so a genuinely allocated site could simply not have been matched yet. "
                "See Local Plan Sites for the full allocation list."
            ),
            "council_supply": council_supply,
        }
    return {"allocations": policy_rows, "no_allocation_message": None, "council_supply": council_supply}


# --- Visual Evidence tab ----------------------------------------------------


def build_visual_evidence_gallery(session: Session, site_id: int) -> dict:
    """Extends app.visuals.site_view.build_site_visual_evidence's primary/
    others split into the four-way bucketing Part 9 asks for: confirmed
    primary, other confirmed, suggested/needs review, and (implicitly) no
    evidence at all. Confirmed evidence always outranks suggested evidence
    in the returned ordering, never the reverse."""
    evidence = build_site_visual_evidence(session, site_id)
    primary = evidence["primary"]
    others = evidence["others"]

    other_confirmed = [img for img in others if img.review_status == "confirmed"]
    needs_review = [img for img in others if img.review_status != "confirmed"]

    def _card(img: VisualEvidence) -> dict:
        return {
            "id": img.id,
            "image_path": img.thumbnail_path or img.image_path,
            "label": IMAGE_TYPE_LABELS.get(img.image_type, img.image_type),
            "source_title": img.source_document_title,
            "source_page": img.source_page,
            "source_url": img.source_document_url,
            "confidence": img.extraction_confidence,
            "review_status": img.review_status,
            "is_primary": img is primary,
        }

    return {
        "has_any": primary is not None or bool(others),
        "primary": _card(primary) if primary else None,
        "other_confirmed": [_card(img) for img in other_confirmed],
        "needs_review": [_card(img) for img in needs_review],
    }


# --- Timeline tab ------------------------------------------------------------


def build_site_timeline(
    session: Session, site: Site, apps: list[Application], lapse: dict, policy_rows: list[dict],
    ai_summary_generated_at: dt.datetime | None, latest_visual_evidence_at: dt.datetime | None,
    visual_evidence_count: int,
) -> list[dict]:
    """One coherent chronological timeline (Part 10) built entirely from
    already-computed facts - never fabricates a date for an undated
    record (a record with no parseable date is simply omitted, not given
    a guessed placeholder), and aggregates repeated technical events
    (progress-signal filings, visual-evidence extraction) into one entry
    rather than one row per underlying record. Every entry's "when" is
    normalised to a datetime (portal/plan dates are date-only) so the
    shared shell.timeline() component - built around datetime - can
    render this list unchanged."""
    def _as_datetime(value: dt.date | dt.datetime) -> dt.datetime:
        """Normalises to a timezone-AWARE (UTC) datetime - portal/plan
        dates are date-only, but detected_at/ai_summary_generated_at/
        visual-evidence timestamps are all stored tz-aware
        (DateTime(timezone=True)), and Python raises comparing a naive
        and an aware datetime directly - every entry below must be one or
        the other consistently before the final chronological sort."""
        if isinstance(value, dt.datetime):
            return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
        return dt.datetime.combine(value, dt.time.min, tzinfo=dt.timezone.utc)

    entries: list[dict] = []

    for app in apps:
        received = parse_portal_date(app.application_received)
        if received != dt.date.min:
            entries.append({
                "icon": "📥", "label": f"{app.reference} submitted", "when": _as_datetime(received),
                "detail": (app.proposal or "")[:150] or None,
            })
        validated = parse_portal_date(app.application_validated)
        if validated != dt.date.min and app.application_validated != app.application_received:
            entries.append({"icon": "📋", "label": f"{app.reference} validated", "when": _as_datetime(validated), "detail": None})
        if app.decision and app.decision_issued_date:
            decided = parse_portal_date(app.decision_issued_date)
            if decided != dt.date.min:
                entries.append({
                    "icon": "✅" if "approve" in app.decision.lower() or "grant" in app.decision.lower() else "🚫",
                    "label": f"{app.reference} decided: {app.decision}", "when": _as_datetime(decided), "detail": None,
                })

    if lapse.get("deadline"):
        entries.append({
            "icon": "⏰", "label": "Commencement deadline", "when": _as_datetime(lapse["deadline"]),
            "detail": f"3 years from {lapse['granted_app'].reference}'s decision" if lapse.get("granted_app") else None,
        })

    # Aggregated, not one row per filing - Part 10's "aggregate repeated
    # technical events where they add no user value".
    progress_filings = sorted(
        (a for a in site.applications if a.application_category in PROGRESS_SIGNAL_CATEGORIES and a.application_received),
        key=lambda a: parse_portal_date(a.application_received),
    )
    if progress_filings:
        latest = progress_filings[-1]
        latest_date = parse_portal_date(latest.application_received)
        if latest_date != dt.date.min:
            n = len(progress_filings)
            entries.append({
                "icon": "🏗️",
                "label": f"{n} commencement/progress filing{'s' if n != 1 else ''} recorded, latest {latest.reference}",
                "when": _as_datetime(latest_date), "detail": None,
            })

    if policy_rows:
        allocation_ids = [row["allocation_id"] for row in policy_rows]
        events = session.execute(
            select(PolicyChangeEvent).where(PolicyChangeEvent.allocation_id.in_(allocation_ids))
        ).scalars().all()
        for event in events:
            if event.detected_at is None:
                continue
            label = _POLICY_EVENT_LABELS.get(event.event_type, "Policy update recorded for this site's allocation")
            entries.append({"icon": "📋", "label": label, "when": _as_datetime(event.detected_at), "detail": None})

    if visual_evidence_count and latest_visual_evidence_at:
        entries.append({
            "icon": "🖼️",
            "label": f"{visual_evidence_count} visual evidence page(s) extracted",
            "when": _as_datetime(latest_visual_evidence_at), "detail": None,
        })

    if ai_summary_generated_at:
        entries.append({"icon": "🤖", "label": "AI status summary generated", "when": _as_datetime(ai_summary_generated_at), "detail": None})

    entries.sort(key=lambda e: e["when"], reverse=True)
    return entries


# --- AI Summary tab ----------------------------------------------------------


def build_ai_summary_view(site: Site) -> dict:
    """Reuses the existing stored Site AI status summary (Part 11) -
    site.status_summary is a single unstructured paragraph (see
    app.reporting.scheme_summary's prompt: "plain text, no markdown
    headers"), with no separately-stored Key Changes/Evidence Gaps/
    Suggested Investigation subsections the way LocalPlan's own AI summary
    has - so this view honestly presents the whole stored text as one
    "Current position" block rather than fabricating a split the stored
    output doesn't actually support. Model/prompt version are NOT shown -
    Site.status_summary has no stored per-row model/prompt_version column
    (unlike LocalPlan.ai_summary_model/ai_summary_prompt_version), so
    showing one here would assert something not actually recorded against
    this specific summary."""
    if not site.status_summary:
        return {"has_summary": False, "text": None, "generated_at": None}
    return {"has_summary": True, "text": site.status_summary, "generated_at": site.status_summary_updated_at}


# --- Evidence gaps -----------------------------------------------------------


def build_evidence_gaps(merged: dict, lapse: dict, policy_rows: list[dict], visual_evidence: dict, ai_summary: dict) -> list[str]:
    """A short, honest list of what's missing (Part 12/14) - never a
    reason to hide a tab, just a clearly labelled gap."""
    gaps: list[str] = []
    if merged.get("total_units_final") is None:
        gaps.append("No verified total unit count yet.")
    elif merged.get("total_units_is_estimated"):
        gaps.append("Total unit count is a portal-listing estimate, not yet AI-verified against the full application.")
    if merged.get("data_quality_status") not in ("verified",) and merged.get("data_quality_status"):
        gaps.append(f"Data quality: {merged['data_quality_status']}.")
    if merged.get("affordable_status_note"):
        gaps.append(f"Affordable housing figures need manual review: {merged['affordable_status_note']}")
    if lapse.get("build_status") in (None, "unknown"):
        gaps.append("Build status has not been verified (no EPC data available).")
    if not policy_rows:
        gaps.append("No Local Plan allocation has been matched to this site.")
    if not visual_evidence.get("has_any"):
        gaps.append("No confirmed or suggested visual evidence has been extracted yet.")
    elif visual_evidence.get("needs_review"):
        gaps.append(f"{len(visual_evidence['needs_review'])} visual evidence item(s) await review.")
    if not ai_summary.get("has_summary"):
        gaps.append("No AI status summary has been generated yet.")
    return gaps


def has_significant_missing_evidence(merged: dict, lapse: dict, policy_rows: list[dict]) -> bool:
    """A coarse boolean used by build_opportunity_position - True when a
    headline-level fact (unit count, build status) is missing/unverified,
    distinct from the fuller evidence_gaps list above (which also flags
    lower-stakes gaps like "no visual evidence yet")."""
    return (
        merged.get("total_units_final") is None
        or bool(merged.get("total_units_is_estimated"))
        or lapse.get("build_status") in (None, "unknown")
    )


# --- Top-level assembly ------------------------------------------------------


def build_site_profile(
    session: Session, site: Site, apps: list[Application], *,
    merged: dict, rep_app: Application | None, lapse: dict, phase_breakdown: list[dict],
    decision_status: str | None,
) -> dict:
    """The Site Profile view model (Sprint 4.4, Part 15) - a small, bounded
    set of batched queries: build_site_policy_intelligence and
    build_site_visual_evidence each already run one query per Site (not
    per application/image, see their own docstrings), this function adds
    exactly two more of its own (the council's LocalPlans for the
    five-year-supply check, and the allocation-scoped PolicyChangeEvent
    rows for the timeline) - never one query per card, image or timeline
    row. merged/rep_app/lapse/phase_breakdown are computed ONCE by the
    caller (the Site Profile page, reusing app.ui.common's existing
    helpers) and passed in here, so every tab below reads from the same
    already-computed dicts rather than recomputing them."""
    policy_rows = build_site_policy_intelligence(
        session.execute(select(LocalPlanSite).where(LocalPlanSite.matched_site_id == site.id)).scalars().all()
    )
    visual_evidence = build_visual_evidence_gallery(session, site.id)
    visual_evidence_count = (
        (1 if visual_evidence["primary"] else 0)
        + len(visual_evidence["other_confirmed"]) + len(visual_evidence["needs_review"])
    )
    latest_visual_evidence_at = None
    all_images = session.execute(
        select(VisualEvidence.created_at).where(
            VisualEvidence.site_id == site.id, VisualEvidence.status == "current", VisualEvidence.review_status != "rejected",
        )
    ).scalars().all()
    if all_images:
        latest_visual_evidence_at = max(all_images)

    ai_summary = build_ai_summary_view(site)
    council_supply = _council_five_year_supply(session, site.council_code, policy_rows)
    has_missing = has_significant_missing_evidence(merged, lapse, policy_rows)

    # Gate 2B-1 - deterministic fact-level reconciliation over this Site's
    # applications. Replaces "primary_reference / planning_status_label =
    # whatever pick_representative_application picked" (which had no
    # awareness of application role, decided state or supersession) at the
    # header and headline-metric boundary. Computed here (this module is
    # pure, no Streamlit) rather than passed in, since no existing caller
    # produces it.
    #
    # site.applications (the raw relationship), NOT the display-filtered
    # `apps` - load_site_applications drops condition-discharge and
    # S73/variation filings as "not a qualifying scheme", but those are
    # exactly the records the non-substantive guardrail and the
    # S73-fact-specific safeguard need to see (same reasoning as
    # compute_lapse_status / build_phase_breakdown, which also read the raw
    # relationship - see app.ui.common.render_scheme_detail's own note).
    all_apps = list(site.applications)
    facts = build_operative_planning_facts(all_apps)
    consented = facts.consented_position
    active_positions = facts.active_positions
    _reconciliation_ran = bool(facts.resolved_applications)

    # Gate 2B-2A Section 20 (Stage A) - the "Decision status" headline tile
    # and the Planning Position tab's own decision-status line both read
    # this SAME `decision_status` value; overriding it here, once, with the
    # reconciled answer is what stops this page from saying "Permission
    # granted" in one place and "Awaiting decision" in another for the
    # SAME site (the Former Burnage Cricket Club regression - the caller's
    # unreconciled decision_status parameter previously came from
    # pick_representative_application's pick, e.g. a newer condition-
    # discharge filing with no decision of its own, while other reconciled
    # facts elsewhere on the page already reflected the granted permission).
    # The caller-supplied `decision_status` is used only as the final
    # fallback, when reconciliation could not run at all.
    decision_status = _reconciled_decision_status(consented, active_positions, _reconciliation_ran, decision_status)

    # The application whose coherent scheme_intelligence record represents
    # the scheme for residential-mix / affordable-headline purposes - the
    # CONSENTED position if one exists, else the first ACTIVE position (an
    # arbitrary but stable choice among possibly several - see
    # header["planning_status_label"] below for how multiple active
    # positions are represented honestly rather than silently reduced to
    # one). Falls back to rep_app only when reconciliation identified
    # neither a consented nor any active operative application.
    operative_app = None
    if consented.reference.state == FACT_RESOLVED and consented.reference.source is not None:
        operative_app = next((a for a in all_apps if a.id == consented.reference.source.application_id), None)
    elif active_positions and active_positions[0].reference.state == FACT_RESOLVED:
        src = active_positions[0].reference.source
        operative_app = next((a for a in all_apps if a.id == src.application_id), None) if src else None
    mix_rep_app = operative_app or rep_app

    header = build_site_header(
        site=site, merged=merged, lapse=lapse, decision_status=decision_status,
        policy_rows=policy_rows, last_ai_summary_at=ai_summary["generated_at"],
        latest_visual_evidence_at=latest_visual_evidence_at,
    )
    # primary_reference is a navigational identifier, not a substantive
    # scheme fact - keep the rep_app fallback so a site whose only record
    # is (e.g.) an EIA screening request still has a reference to open.
    if consented.reference.state == FACT_RESOLVED:
        header["primary_reference"] = consented.reference.value
    elif active_positions and active_positions[0].reference.state == FACT_RESOLVED:
        header["primary_reference"] = active_positions[0].reference.value
    else:
        header["primary_reference"] = rep_app.reference if rep_app else None
    # planning_status_label IS a substantive scheme fact - CONSENTED vs
    # ACTIVE are never collapsed (Gate 2B-2A Sections 5-7). A single clear
    # active position is shown as-is; several simultaneous active
    # positions are represented honestly as a count rather than one of
    # them being silently picked as "the" status. When reconciliation ran
    # and deliberately found neither a consented nor an active position
    # (e.g. the only application is an EIA screening request, or every
    # substantive application is withdrawn/refused), the label is None -
    # a screening request's own "Decided" must never read as the scheme's
    # planning status. The legacy rep_app fallback stands only if
    # reconciliation could not run at all.
    if consented.planning_status.state == FACT_RESOLVED:
        header["planning_status_label"] = str(consented.planning_status.value)
    elif len(active_positions) == 1 and active_positions[0].planning_status.state == FACT_RESOLVED:
        header["planning_status_label"] = str(active_positions[0].planning_status.value)
    elif len(active_positions) > 1:
        header["planning_status_label"] = f"{len(active_positions)} active planning proposals"
    elif _reconciliation_ran:
        header["planning_status_label"] = None
    else:
        header["planning_status_label"] = rep_app.status if rep_app else None
    header["operative_permission_reference"] = consented.reference.value if consented.reference.state == FACT_RESOLVED else None

    opportunity_position = build_opportunity_position(
        merged=merged, lapse=lapse, phase_breakdown=phase_breakdown, policy_rows=policy_rows,
        council_supply=council_supply, has_missing_evidence=has_missing,
    )
    policy_position = build_policy_position(policy_rows, council_supply)
    timeline = build_site_timeline(
        session, site, apps, lapse, policy_rows, ai_summary["generated_at"],
        latest_visual_evidence_at, visual_evidence_count,
    )
    evidence_gaps = build_evidence_gaps(merged, lapse, policy_rows, visual_evidence, ai_summary)
    residential_mix = build_residential_mix(site, apps, rep_app=mix_rep_app)

    # Operative total for the "Total homes" headline tile: the CONSENTED
    # approved figure where a consent exists; otherwise, ONLY when there is
    # exactly one active position (several active positions must never be
    # silently reduced to a single headline number - Section 7), that
    # position's proposed figure. Reconciliation returns not_determined
    # (never a guess) when neither exists - the headline must reflect that,
    # never fall back to aggregate_scheme_fields (Gate 2B-1 Defect 2).
    operative_total = None
    operative_total_basis = None
    operative_total_is_estimated = False
    if consented.approved_units.state == FACT_RESOLVED:
        operative_total, operative_total_basis = consented.approved_units.value, "approved"
    elif len(active_positions) == 1 and active_positions[0].proposed_units.state == FACT_RESOLVED:
        operative_total = active_positions[0].proposed_units.value
        operative_total_basis = "proposed"
        operative_total_is_estimated = active_positions[0].proposed_units.confidence == "low"
    operative_total_not_determined = bool(_reconciliation_ran and operative_total is None)
    headline_metrics = build_headline_metrics(
        merged, lapse, decision_status, residential_mix["affordable_headline"],
        operative_total=operative_total, operative_total_is_estimated=operative_total_is_estimated,
        operative_total_basis=operative_total_basis,
        operative_total_not_determined=operative_total_not_determined,
    )

    return {
        "header": header,
        "headline_metrics": headline_metrics,
        "opportunity_position": opportunity_position,
        "policy_position": policy_position,
        "visual_evidence": visual_evidence,
        "timeline": timeline,
        "ai_summary": ai_summary,
        "evidence_gaps": evidence_gaps,
        "policy_rows": policy_rows,
        "residential_mix": residential_mix,
        "scheme_reconciliation": _reconciliation_view(facts),
    }


def _reconciled_decision_status(consented, active_positions, reconciliation_ran: bool, fallback: str | None) -> str | None:
    """Gate 2B-2A Section 20 - one of app.pipeline.lapse_tracking.
    DECISION_STATUS_LABELS's own 4 keys (granted/refused/withdrawn/
    not_yet_decided), derived from the SAME reconciliation every other
    fact on the page already uses, instead of the caller's own unreconciled
    pick_representative_application-based value. `fallback` (the legacy
    caller-supplied value) is used ONLY when reconciliation could not run
    at all - never when it ran and found nothing (that case returns None,
    which every consumer of this value already renders as "Not yet
    verified"/omitted, exactly like every other not_determined fact)."""
    if consented.planning_status.state == FACT_RESOLVED:
        value = consented.planning_status.value
        if value == "Permission granted":
            return "granted"
        if value == "Refused":
            return "refused"
        if value == "Withdrawn":
            return "withdrawn"
    if len(active_positions) >= 1:
        return "not_yet_decided"
    if reconciliation_ran:
        return None
    return fallback


def _fact_view(f) -> dict:
    return {
        "state": f.state, "value": f.value, "confidence": f.confidence, "reason": f.reason,
        "source_reference": f.source.application_reference if f.source else None,
        "source_role": f.source.planning_role if f.source else None,
        # Gate 2B-2A - relationship confidence and evidence freshness, kept
        # explicitly distinct from `confidence` (evidence confidence) above
        # (Section 18) - never combined into one score.
        "relationship_level": f.source.relationship_level if f.source else None,
        "status_verified_at": f.source.status_verified_at.isoformat() if f.source and f.source.status_verified_at else None,
        "independently_verified": f.source.independently_verified if f.source else None,
        "conflicts": [
            {"reference": p.application_reference, "value": p.value, "role": p.planning_role,
             "scope": p.scope_label}
            for p in f.conflicts
        ],
    }


def _reconciliation_view(facts) -> dict:
    """Compact, presentation-ready summary of the Gate 2B-2A trusted
    operative planning facts - CONSENTED position, ACTIVE position(s)
    (zero, one or several, never collapsed), affordable housing
    (consented / active / historical), and any unresolved same-scope
    conflicts. A read-only trail the UI can surface; a fuller,
    persisted/versioned operative-facts layer remains an open Gate 2B-2
    architecture question (see docs/PRODUCT_ROADMAP.md)."""
    consented = facts.consented_position
    ah = facts.affordable_housing
    return {
        "consented_position": {
            "reference": _fact_view(consented.reference),
            "planning_status": _fact_view(consented.planning_status),
            "approved_units": _fact_view(consented.approved_units),
            "residential_only_units": _fact_view(consented.residential_only_units),
            "all_use_total_units": _fact_view(consented.all_use_total_units),
            "unit_mix": _fact_view(consented.unit_mix),
            "superseded_units": [
                {"reference": p.application_reference, "value": p.value, "role": p.planning_role}
                for p in consented.superseded_units
            ],
        },
        "active_positions": [
            {
                "scope_type": p.scope_type, "scope_label": p.scope_label,
                "reference": _fact_view(p.reference), "planning_status": _fact_view(p.planning_status),
                "proposed_units": _fact_view(p.proposed_units),
                "residential_only_units": _fact_view(p.residential_only_units),
                "all_use_total_units": _fact_view(p.all_use_total_units), "unit_mix": _fact_view(p.unit_mix),
            }
            for p in facts.active_positions
        ],
        "affordable_housing": {
            "whole_site": _ah_position(ah.whole_site),
            "phases": [_ah_position(p) for p in ah.phases],
            "active_whole_site": _ah_position(ah.active_whole_site),
            "active_phases": [_ah_position(p) for p in ah.active_phases],
            "historical": [_ah_position(p) for p in ah.historical],
            "conflicts": [
                {"scope": c.scope_label,
                 "positions": [_ah_position(p) for p in c.positions]}
                for c in ah.conflicts
            ],
        },
        "roles": [
            {"reference": ra.reference, "role": ra.role, "decided_state": ra.decided_state,
             "scope": ra.scope_label}
            for ra in facts.resolved_applications
        ],
        "scope_note": facts.scope_note,
    }


def _ah_position(p) -> dict | None:
    if p is None:
        return None
    return {
        "reference": p.application_reference, "scope": p.scope_label, "scope_type": p.scope_type,
        "percentage": p.percentage, "units": p.units, "tenure": p.tenure, "status": p.status,
        "notes": p.notes, "decided_state": p.decided_state,
    }
