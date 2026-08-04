"""Phase-level build-progress breakdown for large multi-phase sites.

Large strategic sites are rarely delivered as a single planning application -
they progress through outline consent, then a series of phase- or plot-
specific reserved matters / discharge-of-conditions filings, many of which
explicitly name their phase in the proposal text (confirmed real examples:
"Reserved Matters application for Phase EV1, EV2 and part EV3 site
infrastructure and enabling works", "landscaping works adjoining
infrastructure phase H4"). Grouping a site's applications by phase and
tracking each phase's own filing history separately - rather than one
whole-site status - surfaces exactly the kind of buying opportunity being
looked for: a phase with full planning permission but no commencement/
discharge-of-conditions filing since is a plot the main developer hasn't
started, and could plausibly be bought off to de-risk the wider scheme.

Relies on run_weekly.stage_scrape also capturing condition_discharge_or_
details filings for already-known references (see
lapse_tracking.PROGRESS_SIGNAL_CATEGORIES) - without those, there's no
portal-native "has this phase actually started" signal beyond the original
grant itself.
"""
from __future__ import annotations

import re

from app.db.models import Application
from app.pipeline.lapse_tracking import (
    PROGRESS_SIGNAL_CATEGORIES,
    find_progress_signal_filing,
    is_granted_decision,
    parse_portal_date,
)
from app.scrapers.unit_filter import EXCLUDE_CATEGORIES, extract_unit_counts

PHASE_TOKEN = r"(?:part\s+)?[A-Za-z]{0,4}\d+[A-Za-z]?"
# "phase"/"plot" captured as its own group rather than folded into one
# alternation - confirmed real case (Wigan North Leigh): "plots 45, 46, 49
# and 67" and "phase 1A" were both being collapsed into bare numeric labels
# ("45", "46", "1A"...) with no record of which word introduced them, so the
# UI displayed individual house PLOTS as if they were 15 separate site
# PHASES. A plot is one dwelling (or a handful) within a phase, not a
# development stage in its own right - conflating the two both overstates
# how fragmented the site's phasing is and, per-group, makes a plot's
# genuine 1-unit scale look like an unexplained gap in a "phase"'s figures.
PHASE_LIST_RE = re.compile(
    rf"\b(phase|plot)s?\s+((?:{PHASE_TOKEN}\s*(?:,|and|&)?\s*)+)", re.I,
)

# The bucket for applications where no phase/plot was named at all - kept
# distinct from the real phases so a site with e.g. one unphased outline
# application plus three named phases doesn't get treated as if the outline
# were its own separate "phase".
UNPHASED_LABEL = "Whole site / unphased"

PHASE_STATUS_LABELS = {
    "not_yet_approved": "⏳ Awaiting decision",
    "approved_not_started": "🟢 Approved, not yet started",
    "underway": "🏗️ Underway",
}


def extract_phase_labels(text: str | None) -> list[tuple[str, str]]:
    """All phase/plot codes explicitly named in the text, in first-seen
    order, as (code, kind) pairs where kind is "phase" or "plot" - a single
    application can cover several ("Phase EV1, EV2 and part EV3...")."""
    labels: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in PHASE_LIST_RE.finditer(text or ""):
        kind = match.group(1).lower()
        chunk = match.group(2)
        for token in re.split(r"[,&]|\band\b", chunk, flags=re.I):
            token = re.sub(r"\bpart\b", "", token, flags=re.I).strip().upper()
            if token and token not in seen:
                seen.add(token)
                labels.append((token, kind))
    return labels


def group_applications_by_phase(applications: list[Application]) -> dict[tuple[str, str], list[Application]]:
    """An application naming multiple phases/plots is attached to each of
    them (it's genuinely relevant to all) - proposal text is checked first
    since it's the more reliable source, falling back to the address only
    when the proposal itself doesn't name one. Keyed by (code, kind) rather
    than just code, since the same number can plausibly appear as both a
    phase and a plot on different applications and those shouldn't merge."""
    groups: dict[tuple[str, str], list[Application]] = {}
    for app in applications:
        labels = extract_phase_labels(app.proposal) or extract_phase_labels(app.address)
        if not labels:
            groups.setdefault((UNPHASED_LABEL, "phase"), []).append(app)
            continue
        for code, kind in labels:
            groups.setdefault((code, kind), []).append(app)
    return groups


def compute_phase_progress(applications: list[Application]) -> dict:
    """One phase's applications -> a progress verdict. Mirrors
    lapse_tracking.compute_lapse_status's shape but scoped to a single phase
    rather than the whole site, and without a lapse clock (the whole-site
    commencement deadline already covers that; a phase adds "has this
    specific part actually started" instead)."""
    granted = [a for a in applications if is_granted_decision(a.decision) and a.decision_issued_date]
    if granted:
        latest_grant = max(granted, key=lambda a: parse_portal_date(a.decision_issued_date))
        grant_date = parse_portal_date(latest_grant.decision_issued_date)

        progress_filing = find_progress_signal_filing(applications, grant_date, exclude=latest_grant)
        if progress_filing:
            return {"status": "underway", "latest_grant": latest_grant, "progress_filing": progress_filing}

        return {"status": "approved_not_started", "latest_grant": latest_grant, "progress_filing": None}

    # No grant WITHIN this phase/plot's own applications - but if it has a
    # real progress-signal filing (discharge of conditions, amendment)
    # anyway, that's still unambiguous evidence of active, approved work: a
    # discharge-of-conditions application cannot exist without an underlying
    # permission to discharge FROM. Confirmed a real case (Wigan North Leigh
    # "Plot 41"): three condition-discharge applications, all decided
    # "Agreed", with no grant of their own attached to this specific plot -
    # the grant lives on the whole-site outline these filings cite by
    # reference, not co-located in this group. Without this fallback, plot-
    # level administrative groups like this were wrongly reported as "not
    # yet approved" - reading as still-undecided planning applications, when
    # they're actually clear evidence of work already happening on the
    # ground.
    any_progress_filing = next((a for a in applications if a.application_category in PROGRESS_SIGNAL_CATEGORIES), None)
    if any_progress_filing:
        return {"status": "underway", "latest_grant": None, "progress_filing": any_progress_filing}

    return {"status": "not_yet_approved", "latest_grant": None, "progress_filing": None}


def _phase_unit_count(apps: list[Application]) -> dict:
    """Best available "how many units does this phase deliver" figure -
    grounded-numbers, not guessed. Prefers a real AI-extracted total from a
    phase application's own downloaded documents (scheme_intelligence,
    populated once classify_application_category correctly recognises a
    phase-defining Reserved Matters submission as such rather than as a
    minor condition-discharge filing - see unit_filter.py); falls back to
    the same portal-text regex used at scrape time when no document
    extraction has run yet, which is often already exact for a Reserved
    Matters application that states its own dwelling count directly (e.g.
    "...for the erection of 257 dwellings").

    Only trusts EXCLUDE_CATEGORIES-exempt applications as a unit-count
    source - confirmed a real case (Wigan North Leigh "Phase 1A"): its own
    condition-discharge filings (materials/drainage/gas validation, no
    housing count of their own) already had scheme_intelligence rows from an
    earlier, unrelated qualifying run, with the AI extraction latching onto
    an incidental "1" somewhere in a thin administrative document -
    plausible-looking but meaningless as a unit count. A condition-discharge
    or amendment filing was never going to state its phase's real unit
    count in the first place, so it's excluded as a source entirely rather
    than trusted just because scheme_intelligence happens to exist.

    Also only trusts an application that names this ONE phase alone, not one
    spanning several at once - confirmed two real cases: a Tameside
    "Reserved Matters application for Phase EV1, EV2 and part EV3 site
    infrastructure and enabling works" whose extracted total (2350) is the
    whole outline's dwelling count, not any one of the three phases' own
    share, and a Stockport hybrid application covering Phases 5-8 together
    where phases 5-7 are pure office space (Phase 8 only "office OR
    residential") - a shared multi-phase filing's own total, genuine or not,
    doesn't tell you what ANY single one of those phases delivers, so it's
    excluded as a source for all of them rather than misattributed to each."""
    substantive = [
        a for a in apps
        if a.application_category not in EXCLUDE_CATEGORIES
        and len(extract_phase_labels(a.proposal) or extract_phase_labels(a.address)) == 1
    ]

    for app in substantive:
        si = getattr(app, "scheme_intelligence", None)
        if si and si.total_units_final:
            return {"unit_count": si.total_units_final, "unit_count_source": "documents", "unit_count_application": app}

    for app in substantive:
        counts = extract_unit_counts(app.proposal)
        if counts:
            return {"unit_count": max(counts), "unit_count_source": "portal_text", "unit_count_application": app}

    return {"unit_count": None, "unit_count_source": None, "unit_count_application": None}


def build_phase_breakdown(applications: list[Application]) -> list[dict]:
    """One row per detected phase/plot, sorted with the unphased bucket
    last. Returns [] when the site has no more than one group - a single
    bucket (whether phased or not) isn't a "breakdown" worth showing.

    Unit counts are only computed for genuine phases, not individual plots -
    a plot is a single dwelling (or a handful) within a phase, not its own
    deliverable unit count worth surfacing separately."""
    groups = group_applications_by_phase(applications)
    if len(groups) <= 1:
        return []

    breakdown = []
    for (code, kind), apps in groups.items():
        progress = compute_phase_progress(apps)
        label = code if code == UNPHASED_LABEL else f"{'Phase' if kind == 'phase' else 'Plot'} {code}"
        row = {"label": label, "code": code, "kind": kind, "applications": apps, **progress}
        if kind == "phase" and code != UNPHASED_LABEL:
            row.update(_phase_unit_count(apps))
        breakdown.append(row)

    breakdown.sort(key=lambda row: (row["code"] == UNPHASED_LABEL, row["kind"] != "phase", row["code"]))
    return breakdown


def summarize_phase_units(breakdown: list[dict]) -> dict:
    """Roll named phases (not plots, not the unphased bucket - see
    build_phase_breakdown's own unit-count scoping) up into three buckets by
    build status: units already underway, units approved but not yet
    started (the clean acquisition signal - full permission, no legal
    urgency on the developer to build it, per the lapse-status reasoning in
    ui.common), and units still awaiting a decision at all.

    A phase's units only ever go into the sum for its ACTUAL bucket - a
    phase with unknown units still counts toward that bucket's phase count
    (so "2 phases underway" stays honest even when neither states its own
    unit total), it just can't contribute to the units total. Never
    backfills a missing count from the site's whole-scheme total or any
    other phase - that would silently misattribute units across phases
    exactly the way the two bugs fixed in _phase_unit_count did."""
    phases = [p for p in breakdown if p["kind"] == "phase" and p["code"] != UNPHASED_LABEL]

    def _bucket(status: str) -> dict:
        rows = [p for p in phases if p["status"] == status]
        known = [p["unit_count"] for p in rows if p.get("unit_count")]
        return {
            "phase_count": len(rows),
            "units": sum(known) if known else None,
            "phases_with_known_units": len(known),
            "phases": rows,
        }

    return {
        "phase_count": len(phases),
        "underway": _bucket("underway"),
        "approved_not_started": _bucket("approved_not_started"),
        "not_yet_approved": _bucket("not_yet_approved"),
    }
