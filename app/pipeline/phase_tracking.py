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
from app.pipeline.lapse_tracking import find_progress_signal_filing, is_granted_decision, parse_portal_date

PHASE_TOKEN = r"(?:part\s+)?[A-Za-z]{0,4}\d+[A-Za-z]?"
PHASE_LIST_RE = re.compile(
    rf"\b(?:phase|plot)s?\s+((?:{PHASE_TOKEN}\s*(?:,|and|&)?\s*)+)", re.I,
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


def extract_phase_labels(text: str | None) -> list[str]:
    """All phase/plot codes explicitly named in the text, in first-seen
    order - a single application can cover several ("Phase EV1, EV2 and
    part EV3...")."""
    labels: list[str] = []
    for match in PHASE_LIST_RE.finditer(text or ""):
        chunk = match.group(1)
        for token in re.split(r"[,&]|\band\b", chunk, flags=re.I):
            token = re.sub(r"\bpart\b", "", token, flags=re.I).strip()
            if token and token.upper() not in labels:
                labels.append(token.upper())
    return labels


def group_applications_by_phase(applications: list[Application]) -> dict[str, list[Application]]:
    """An application naming multiple phases is attached to each of them
    (it's genuinely relevant to all) - proposal text is checked first since
    it's the more reliable source, falling back to the address only when the
    proposal itself doesn't name a phase."""
    groups: dict[str, list[Application]] = {}
    for app in applications:
        labels = extract_phase_labels(app.proposal) or extract_phase_labels(app.address)
        if not labels:
            groups.setdefault(UNPHASED_LABEL, []).append(app)
            continue
        for label in labels:
            groups.setdefault(label, []).append(app)
    return groups


def compute_phase_progress(applications: list[Application]) -> dict:
    """One phase's applications -> a progress verdict. Mirrors
    lapse_tracking.compute_lapse_status's shape but scoped to a single phase
    rather than the whole site, and without a lapse clock (the whole-site
    commencement deadline already covers that; a phase adds "has this
    specific part actually started" instead)."""
    granted = [a for a in applications if is_granted_decision(a.decision) and a.decision_issued_date]
    if not granted:
        return {"status": "not_yet_approved", "latest_grant": None, "progress_filing": None}

    latest_grant = max(granted, key=lambda a: parse_portal_date(a.decision_issued_date))
    grant_date = parse_portal_date(latest_grant.decision_issued_date)

    progress_filing = find_progress_signal_filing(applications, grant_date, exclude=latest_grant)
    if progress_filing:
        return {"status": "underway", "latest_grant": latest_grant, "progress_filing": progress_filing}

    return {"status": "approved_not_started", "latest_grant": latest_grant, "progress_filing": None}


def build_phase_breakdown(applications: list[Application]) -> list[dict]:
    """One row per detected phase, sorted with the unphased bucket last.
    Returns [] when the site has no more than one group - a single bucket
    (whether phased or not) isn't a "breakdown" worth showing."""
    groups = group_applications_by_phase(applications)
    if len(groups) <= 1:
        return []

    breakdown = []
    for label, apps in groups.items():
        progress = compute_phase_progress(apps)
        breakdown.append({"label": label, "applications": apps, **progress})

    breakdown.sort(key=lambda row: (row["label"] == UNPHASED_LABEL, row["label"]))
    return breakdown
