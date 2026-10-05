"""Phase-level planning activity. Filings and permission do not prove works or availability."""
from __future__ import annotations

import re

from app.db.models import Application
from app.pipeline.lapse_tracking import PROGRESS_SIGNAL_CATEGORIES, find_progress_signal_filing
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
    "approved_commencement_unverified": "Permission recorded — commencement unverified",
    "planning_activity": "Planning activity — physical commencement unverified",
}


def acquisition_scope_key(row: dict) -> str:
    """Keep existing phase IDs; material plots must not collide with phases."""
    return f"plot_{row['code']}" if row["kind"] == "plot" else row["code"]


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
    """Separate scoped permission and administrative activity from physical progress."""
    from app.reporting.scheme_reconciliation import FACT_RESOLVED, resolve_operative_lapse_anchor

    anchor = resolve_operative_lapse_anchor(applications)
    if anchor.state == FACT_RESOLVED:
        grant_date = anchor.decision_date
        progress_filing = find_progress_signal_filing(applications, grant_date, exclude=anchor.application)
        if progress_filing:
            return {"status": "planning_activity", "latest_grant": anchor.application, "progress_filing": progress_filing}

        return {"status": "approved_commencement_unverified", "latest_grant": anchor.application, "progress_filing": None}

    # Administrative-only records establish activity, not a grant or physical works.
    any_progress_filing = next((a for a in applications if a.application_category in PROGRESS_SIGNAL_CATEGORIES), None)
    if any_progress_filing:
        return {"status": "planning_activity", "latest_grant": None, "progress_filing": any_progress_filing}

    return {"status": "not_yet_approved", "latest_grant": None, "progress_filing": None}


def _phase_unit_count(apps: list[Application]) -> dict:
    """Use the same approved/proposed scope contract as every other consumer."""
    from app.reporting.scheme_reconciliation import scoped_count_assessment
    from app.reporting.residential_count import CountAssessment
    eligible = [a for a in apps if len(extract_phase_labels(a.proposal) or extract_phase_labels(a.address)) == 1]
    labels = {tuple(extract_phase_labels(a.proposal) or extract_phase_labels(a.address))[0] for a in eligible}
    if len(labels) != 1:
        assessment = CountAssessment("unclear", "Unresolved phase scope")
    else:
        code, kind = next(iter(labels))
        assessment = scoped_count_assessment(eligible, kind, f"{kind.title()} {code}")
    source_ids = {p.application_id for p in assessment.sources}
    source_app = next((a for a in eligible if a.id in source_ids), None)
    return {"unit_count": assessment.exact_value, "unit_count_source": ("portal_text" if assessment.resolution == "portal_estimate" else "documents") if source_app else None,
            "unit_count_application": source_app, "count_assessment": assessment,
            "count_display": assessment.label(), "count_note": assessment.note()}


def is_material_development_parcel(applications: list[Application], *, threshold: int = 10) -> bool:
    """Gate 2B-2A - the deterministic test for whether a named "plot"
    group represents a material development parcel (a peer acquisition-
    level scope) rather than an individual dwelling plot (which must not
    become one). True only if a role-eligible application scoped to
    exactly this ONE named group independently states its own
    qualifying-scale (>= threshold - the same qualifying bar app.
    scrapers.unit_filter applies platform-wide, default 10) residential
    unit count - reusing _phase_unit_count's own EXCLUDE_CATEGORIES +
    single-label discipline completely unchanged, never a new inference.

    Read-only production investigation (Gate 2B-2A) confirmed the plot
    token's own shape cannot safely distinguish the two cases: genuine
    individual-dwelling-plot citations ("plots 45, 46, 49 and 67" gas-
    validation discharges against Wigan A/12/76665; "plots 212, 213, 215,
    236..." roof-type non-material amendments against Stockport
    DC/060928) and a real development-parcel use of the SAME word
    ("Plots 1, 2 and 3" in Stockport DC/094376's own Hybrid full-
    permission application) both use bare small numbers as their token -
    no regex over the token itself can tell them apart. What DOES
    distinguish them, using only evidence already extracted: a genuine
    development parcel's own single-plot-labelled application typically
    states a real, qualifying-scale unit count for that one parcel; an
    individual dwelling-plot citation (almost always a condition-
    discharge or non-material-amendment filing, i.e. already excluded as
    a unit-count source by _phase_unit_count's own EXCLUDE_CATEGORIES
    filter, and/or naming several plots at once, already excluded by its
    single-label filter) never does. No LLM, no token-shape guessing."""
    result = _phase_unit_count(applications)
    if result["unit_count"] is not None:
        return result["unit_count"] >= threshold
    # Existing portal text can establish parcel scale for GROUPING only; it does
    # not become a verified count in matching. Administrative/multi-label rows
    # cannot promote individual plots into acquisition scopes.
    from app.reporting.scheme_reconciliation import resolve_planning_role, SUBSTANTIVE_ROLES
    counts = {n for a in applications if resolve_planning_role(a) in SUBSTANTIVE_ROLES
              and len(extract_phase_labels(a.proposal) or extract_phase_labels(a.address)) == 1
              for n in extract_unit_counts(a.proposal)}
    return len(counts) == 1 and next(iter(counts)) >= threshold


def group_applications_by_operative_scope(
    applications: list[Application], *, material_parcel_unit_threshold: int = 10,
) -> dict[tuple[str, str], list[Application]]:
    """Gate 2B-2A - the SAME grouping as group_applications_by_phase,
    except a named "plot" group is kept as its own peer acquisition-level
    scope ONLY if is_material_development_parcel confirms it - otherwise
    its applications are folded into the unphased/whole-site bucket,
    exactly as if no plot had been named at all.

    This is a PRESENTATION/RESOLUTION rule for acquisition-level operative
    scope only (app.reporting.scheme_reconciliation, app.reporting.
    affordable_housing_scope) - it never deletes an application from the
    result and does NOT change group_applications_by_phase or
    build_phase_breakdown themselves, whose existing "Phase Breakdown" UI
    legitimately continues to show individual-plot filing activity as
    detailed planning evidence (Gate 2B-2A Section 13: "individual dwelling
    plots may remain relevant as underlying application evidence,
    provenance, detailed planning activity... this is a resolution/
    presentation rule, not destructive data cleansing").

    Root cause this fixes: read-only production investigation confirmed
    "plot" labels are overwhelmingly individual dwelling-plot citations in
    condition-discharge/non-material-amendment filings - each would
    otherwise become its own "peer" acquisition scope/affordable-housing
    position for a single house, fragmenting whole-site/phase intelligence
    into meaningless slivers (confirmed real defect: app.reporting.
    affordable_housing_scope previously gave a 1-unit "Plot 5" its own AH
    scope entry - see that module's own Gate 2B-2A regression test)."""
    groups = group_applications_by_phase(applications)
    resolved: dict[tuple[str, str], list[Application]] = {}
    unphased_key = (UNPHASED_LABEL, "phase")
    for key, apps in groups.items():
        code, kind = key
        if (
            kind == "plot" and code != UNPHASED_LABEL
            and not is_material_development_parcel(apps, threshold=material_parcel_unit_threshold)
        ):
            target = resolved.setdefault(unphased_key, [])
        else:
            target = resolved.setdefault(key, [])
        for a in apps:
            if a not in target:
                target.append(a)
    return resolved


def build_phase_breakdown(applications: list[Application]) -> list[dict]:
    """One row per detected phase/plot, sorted with the unphased bucket
    last. Returns [] when the site has no more than one group - a single
    bucket (whether phased or not) isn't a "breakdown" worth showing.

    Unit counts are only computed for genuine phases, not individual plots -
    a plot is a single dwelling (or a handful) within a phase, not its own
    deliverable unit count worth surfacing separately."""
    groups = group_applications_by_phase(applications)
    if len(groups) <= 1 and all(code == UNPHASED_LABEL for code, _ in groups):
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


def build_acquisition_scope_breakdown(applications: list[Application]) -> list[dict]:
    """Acquisition-level counterpart to build_phase_breakdown (Gate 2B-2B.2)
    - identical row shape (label/code/kind/progress/unit_count), but grouped
    by group_applications_by_operative_scope (Gate 2B-2A) rather than raw
    group_applications_by_phase, so an individual dwelling plot that fails
    is_material_development_parcel is folded into the whole-site/unphased
    bucket before a row is ever produced for it - it can never surface as
    its own standalone row here, and therefore never as its own standalone
    acquisition opportunity card downstream (app.reporting.dashboard.
    _undeveloped_phase_cards).

    Reuses group_applications_by_operative_scope/compute_phase_progress/
    _phase_unit_count completely unchanged - no new grouping, no new
    material-parcel test, no duplicated regex/threshold logic. Only a
    named "plot" group that INDEPENDENTLY survives group_applications_by_
    operative_scope's own materiality test (i.e. a genuine material
    development parcel) ever reaches this function's output with
    kind == "plot" - every non-material plot citation is already folded
    into the unphased bucket upstream, so this function's own unit_count
    scoping (any named code, not just kind == "phase") is safe: a survivor
    already proved it has its own qualifying-scale figure.

    build_phase_breakdown itself is NOT changed and is not called by this
    function - the Scheme Detail "Phase Breakdown" evidence view keeps
    showing every named plot's own filing activity in full, unresolved
    detail, exactly as before (Gate 2B-2B.2 Section 5: this is a
    presentation/resolution rule for acquisition-opportunity generation
    only, not a change to planning evidence display).

    The "worth a breakdown at all" gate below deliberately checks the RAW
    group_applications_by_phase count, not the resolved (post-fold) one.
    Read-only Gate 2B-2B.2 production investigation confirmed a real
    regression from gating on the resolved count instead: a site with
    exactly one genuine whole-site scope plus one non-material plot
    citation (e.g. "Land North Of Mosley Common", "Land Off Crabtree
    Lane") has 2 RAW groups (so a genuine, pre-existing "approved, not
    started" whole-site card was already being generated for it), but
    folds down to a single RESOLVED group once the non-material plot is
    absorbed - gating on the resolved count would then silently drop that
    site's own legitimate whole-site opportunity entirely, purely as a
    side effect of correctly suppressing an unrelated false plot, which
    is not this gate's purpose. Gating on the raw count instead preserves
    exactly the same "does this site have any phase/plot activity worth
    resolving at all" bar build_phase_breakdown already applies, while
    still folding/resolving the groups that make it through."""
    raw_groups = group_applications_by_phase(applications)
    if len(raw_groups) <= 1 and all(code == UNPHASED_LABEL for code, _ in raw_groups):
        return []
    groups = group_applications_by_operative_scope(applications)

    breakdown = []
    for (code, kind), apps in groups.items():
        progress = compute_phase_progress(apps)
        label = code if code == UNPHASED_LABEL else f"{'Phase' if kind == 'phase' else 'Plot'} {code}"
        row = {"label": label, "code": code, "kind": kind, "applications": apps, **progress}
        if code != UNPHASED_LABEL:
            row.update(_phase_unit_count(apps))
        breakdown.append(row)

    breakdown.sort(key=lambda row: (row["code"] == UNPHASED_LABEL, row["kind"] != "phase", row["code"]))
    return breakdown


def summarize_phase_units(breakdown: list[dict], *, non_overlap_evidence: tuple = ()) -> dict:
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
        known = [p["unit_count"] for p in rows if p.get("unit_count") is not None]
        # Explicit pair evidence: (left code, right code, provenance). No
        # production adapter invents this from labels/application IDs/dates.
        pairs = {frozenset((left, right)) for left, right, source in non_overlap_evidence if source}
        disjoint = len({r["code"] for r in rows}) == len(rows) and all(frozenset((a["code"], b["code"])) in pairs
                       for i, a in enumerate(rows) for b in rows[i + 1:])
        aggregate = sum(known) if known and disjoint and len(known) == len(rows) else None
        return {
            "phase_count": len(rows),
            "units": aggregate,
            "aggregation_state": "resolved" if aggregate is not None else "overlap_or_count_unverified",
            "phases_with_known_units": len(known),
            "phases": rows,
        }

    return {
        "phase_count": len(phases),
        "planning_activity": _bucket("planning_activity"),
        "approved_commencement_unverified": _bucket("approved_commencement_unverified"),
        "not_yet_approved": _bucket("not_yet_approved"),
    }
