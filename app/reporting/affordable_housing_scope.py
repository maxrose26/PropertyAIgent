"""Scope-aware, decided-state-aware affordable-housing aggregation for
Site Summary generation and Gate 2B-2A operative planning facts.

PropertyAIgent's existing multi-application aggregation (app.ui.common.
aggregate_scheme_fields) merges every SchemeIntelligence field independently,
first-non-null, scanning applications in the same priority order for EVERY
field. That is the right behaviour for fields like `developer` or
`housing_typology`, which describe the scheme as a whole regardless of which
application happened to mention them. Affordable housing is different:

1. A technical/condition-discharge application with NO independent
   affordable-housing evidence of its own typically carries
   affordable_percentage_final=0, affordable_units_final=0,
   affordable_housing_status="unknown" - not because the scheme genuinely
   has 0% affordable housing, but because B3 never found anything to say
   about it for THAT application. Under first-non-null scanning, 0 is not
   None, so this technical application can silently clobber a genuine 20%
   position evidenced elsewhere on the same site the moment it happens to
   sort first (confirmed real production defect - Site 519, see this
   module's own test suite).
2. Affordable housing can legitimately differ by scope - a whole-site 50%
   headline and a Phase 1 100%/Phase 2 0% breakdown are not contradictory,
   they describe different scopes, and must never be merged into one
   flattened figure.
3. Percentage/units/tenure/status/notes describe ONE position and must never
   be assembled from different applications ("Frankenstein" mixing) - they
   are only ever read together, from the same application's SchemeIntelligence
   row (or the same prospective override), for the same scope.
4. (Gate 2B-2A) A withdrawn or refused application's affordable-housing
   position must never silently stand in as the CURRENT operative answer
   merely because it is the only evidence available for that scope
   (confirmed real production defect - Stockport Rugby Club: a withdrawn
   hybrid application's 50%/45-unit proposed position was previously the
   only AH figure surfaced at all). Every scope's position is now resolved
   SEPARATELY within each of three decided-state partitions - CONSENTED
   (granted), ACTIVE (live/pending), HISTORICAL (withdrawn/refused) - and
   only CONSENTED and ACTIVE ever appear as "the current answer"; a
   HISTORICAL position is retained for provenance/traceability but is
   never presented as operative. This reuses app.pipeline.material_
   change's existing decided-state vocabulary (shared, unmodified, with
   app.reporting.scheme_reconciliation) - not a new state model.

This module computes a small, in-memory, non-persisted view of the
affordable-housing position(s) that apply to a Site - reusing app.pipeline.
phase_tracking's existing phase/material-development-parcel grouping (Gate
2B-2A: group_applications_by_operative_scope, NOT the raw phase/plot
regex grouping - an individual dwelling plot must not fragment whole-site
or phase-level affordable-housing intelligence into its own scope; see
that function's own docstring and real production evidence) rather than
inventing a new planning hierarchy. Nothing here is persisted and no
schema change is involved - these are throwaway objects computed fresh on
every call, exactly like app.ui.common.aggregate_scheme_fields's own
`merged` dict.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.db.models import Application
from app.pipeline.lapse_tracking import parse_portal_date
from app.pipeline.material_change import (
    DECIDED_GRANTED,
    DECIDED_RECOMMENDATION_ONLY,
    DECIDED_REFUSED,
    DECIDED_UNDETERMINED,
    DECIDED_WITHDRAWN,
    resolve_decided_state,
)
from app.pipeline.phase_tracking import UNPHASED_LABEL, group_applications_by_operative_scope

# Reuses B3's own affordable_housing_status vocabulary (app.extraction.
# intelligence_refresh.AFFORDABLE_HOUSING_STATUSES) as an implicit evidence-
# authority ranking, rather than inventing a new document-level authority
# system - this mirrors that module's own conceptual order (executed S106/
# Deed of Variation > formal Decision Notice/approved condition > Officer/
# Committee evidence > viability evidence > proposed/policy statements).
# Deliberately a plain constant here, not an import, to avoid a module-load
# dependency between app.reporting and app.extraction for one small ranking
# table - the vocabulary itself remains authored and enforced in exactly one
# place (intelligence_refresh.py's own AFFORDABLE_HOUSING_STATUSES/prompt).
_STATUS_AUTHORITY_RANK: dict[str | None, int] = {
    "legally_secured": 6,
    "agreed": 5,
    "conditioned": 5,
    "committee_position": 4,
    "officer_recommended": 4,
    "subject_to_viability_review": 3,
    "policy_required": 2,
    "proposed": 2,
    "unknown": 0,
    None: 0,
}

SCOPE_WHOLE_SITE = "whole_site"
SCOPE_UNCLEAR = "unclear"
SCOPE_PHASE = "phase"
# A "plot" scope here is ALWAYS a confirmed material development parcel
# (Gate 2B-2A) - group_applications_by_operative_scope has already folded
# every individual-dwelling-plot grouping into whole_site/unclear before
# this module ever groups anything.
SCOPE_PLOT = "plot"

_AH_FIELDS = (
    "affordable_percentage_final", "affordable_units_final", "affordable_tenure_split_final",
    "affordable_housing_status", "affordable_housing_notes",
)


@dataclass(frozen=True)
class AffordablePosition:
    """ONE coherent affordable-housing position for one scope, sourced from
    a single application's SchemeIntelligence (or prospective override) -
    percentage/units/tenure/status/notes are always read together from the
    same source, never assembled across applications."""

    scope_type: str  # SCOPE_WHOLE_SITE | SCOPE_UNCLEAR | SCOPE_PHASE | SCOPE_PLOT
    scope_label: str
    application_id: int
    application_reference: str
    percentage: float | None
    units: int | None
    tenure: str | None
    status: str | None
    notes: str | None
    decided_state: str = DECIDED_UNDETERMINED


@dataclass(frozen=True)
class ScopeConflict:
    """Two or more equally (or ambiguously) authoritative positions for the
    SAME scope, WITHIN THE SAME decided-state partition, that disagree and
    cannot be reconciled from evidence alone - Site Summary must surface
    this as an uncertainty, never silently pick one (Part 15/16 of the
    original PR's own task spec). A consented and an active position for
    the same scope disagreeing is NOT a conflict of this kind - they are
    two different, both-true facts about two different positions (Gate
    2B-2A Section 5/16); only disagreement WITHIN one partition is a
    genuine same-scope conflict."""

    scope_type: str
    scope_label: str
    positions: tuple[AffordablePosition, ...]


@dataclass(frozen=True)
class AffordableHousingSummary:
    """Gate 2B-2A - CONSENTED (whole_site/phases), ACTIVE
    (active_whole_site/active_phases) and HISTORICAL affordable-housing
    positions are always structurally separate. A withdrawn/refused
    application's position can only ever appear in `historical` - never in
    `whole_site`/`phases`/`active_whole_site`/`active_phases`."""

    whole_site: AffordablePosition | None
    phases: tuple[AffordablePosition, ...]
    active_whole_site: AffordablePosition | None
    active_phases: tuple[AffordablePosition, ...]
    historical: tuple[AffordablePosition, ...]
    conflicts: tuple[ScopeConflict, ...]


def _effective_fields(app: Application, prospective_overrides: dict[int, dict] | None) -> dict | None:
    """The same override-aware field read as app.ui.common.aggregate_scheme_
    fields's own `_override` helper, narrowed to the 5 AH fields - keeps this
    module's atomicity guarantee identical to B3's existing Site Summary
    preview mechanism (a not-yet-committed refresh's prospective values are
    visible here exactly as they already are to the flattened `merged`
    dict), without touching refresh_intelligence_for_application itself."""
    override = (prospective_overrides or {}).get(app.id)
    intel = app.scheme_intelligence
    if intel is None and override is None:
        return None
    return {
        field: (override[field] if override is not None and field in override else getattr(intel, field, None))
        for field in _AH_FIELDS
    }


def _has_no_independent_affordable_position(fields: dict) -> bool:
    """True means this application carries no independent affordable-housing
    evidence of its own - a technical/condition-discharge/drainage/highways
    filing with nothing to say about affordable housing, distinct from an
    application that explicitly evidences a genuine 0% position (Part 5/6 of
    this PR's own task spec). A real evidenced position always leaves SOME
    trace beyond a bare zero: either a non-"unknown" status (B3 only sets one
    when it found evidence to classify), or explanatory notes (e.g. "No
    affordable housing is provided within Phase 2"), or a non-zero
    percentage/unit figure."""
    status = fields["affordable_housing_status"]
    has_real_status = status not in (None, "unknown")
    has_notes = bool(fields["affordable_housing_notes"] and fields["affordable_housing_notes"].strip())
    has_percentage = fields["affordable_percentage_final"] not in (None, 0)
    has_units = fields["affordable_units_final"] not in (None, 0)
    return not (has_real_status or has_notes or has_percentage or has_units)


def _authority_rank(status: str | None) -> int:
    return _STATUS_AUTHORITY_RANK.get(status, 0)


def _order_candidates(candidates: list[tuple[Application, dict]]) -> list[tuple[Application, dict]]:
    """Same tie-break precedence as app.ui.common.aggregate_scheme_fields /
    pick_representative_application: prefer a fully-extracted application,
    then the most recently received - used only to pick which SINGLE
    application's coherent record represents a scope when candidates agree
    (or when one is decisively more authoritative)."""

    def sort_key(pair: tuple[Application, dict]):
        app, _fields = pair
        complete = bool(app.scheme_intelligence and app.scheme_intelligence.core_intelligence_complete)
        return (complete, parse_portal_date(app.application_received))

    return sorted(candidates, key=sort_key, reverse=True)


def _position(scope_type: str, scope_label: str, app: Application, fields: dict) -> AffordablePosition:
    return AffordablePosition(
        scope_type=scope_type, scope_label=scope_label,
        application_id=app.id, application_reference=app.reference,
        percentage=fields["affordable_percentage_final"], units=fields["affordable_units_final"],
        tenure=fields["affordable_tenure_split_final"], status=fields["affordable_housing_status"],
        notes=fields["affordable_housing_notes"], decided_state=resolve_decided_state(app.decision, app.status),
    )


def _resolve_group_position(
    scope_type: str, scope_label: str, apps: list[Application], prospective_overrides: dict[int, dict] | None,
) -> tuple[AffordablePosition | None, ScopeConflict | None]:
    """One scope, within ONE decided-state partition (see
    _partition_by_decided_state) -> at most one coherent position, or a
    conflict if genuinely irreconcilable WITHIN that partition.

    Candidates with no independent affordable-housing evidence are excluded
    entirely (Part 5) - they can never suppress a genuine position from a
    sibling application in the same scope/partition. Among remaining
    candidates:
    - if every candidate's percentage agrees (or only one states one), the
      best-ordered candidate's whole coherent record wins - no conflict.
    - otherwise, if exactly one authority tier is highest and its own
      candidates agree with each other, that authoritative record wins
      (Part 10: more authoritative evidence may supersede a lower-authority
      disagreement without being treated as a conflict).
    - otherwise (the top authority tier itself contains disagreeing
      percentages) this is a genuine same-scope conflict (Part 4/15) - no
      position is returned, only the conflict, so nothing is silently
      picked."""
    candidates = []
    for app in apps:
        fields = _effective_fields(app, prospective_overrides)
        if fields is None or _has_no_independent_affordable_position(fields):
            continue
        candidates.append((app, fields))
    if not candidates:
        return None, None

    candidates = _order_candidates(candidates)

    percentages = {f["affordable_percentage_final"] for _, f in candidates if f["affordable_percentage_final"] is not None}
    if len(percentages) <= 1:
        app, fields = candidates[0]
        return _position(scope_type, scope_label, app, fields), None

    ranked = sorted(candidates, key=lambda pair: _authority_rank(pair[1]["affordable_housing_status"]), reverse=True)
    top_rank = _authority_rank(ranked[0][1]["affordable_housing_status"])
    tied_at_top = [pair for pair in ranked if _authority_rank(pair[1]["affordable_housing_status"]) == top_rank]
    tied_percentages = {f["affordable_percentage_final"] for _, f in tied_at_top if f["affordable_percentage_final"] is not None}
    if len(tied_percentages) <= 1:
        app, fields = tied_at_top[0]
        return _position(scope_type, scope_label, app, fields), None

    positions = tuple(_position(scope_type, scope_label, a, f) for a, f in candidates)
    return None, ScopeConflict(scope_type=scope_type, scope_label=scope_label, positions=positions)


def _partition_by_decided_state(apps: list[Application]) -> tuple[list[Application], list[Application], list[Application]]:
    """(consented, active, historical) - Gate 2B-2A. `consented` = granted;
    `active` = live (recommendation_only/undetermined); `historical` =
    withdrawn/refused. Reuses app.pipeline.material_change's existing
    decided-state classifier unchanged - the SAME concept app.reporting.
    scheme_reconciliation already uses for residential-fact eligibility,
    so an application's AH partition and its residential-fact eligibility
    can never silently disagree about whether it is granted/live/dead."""
    consented, active, historical = [], [], []
    for app in apps:
        state = resolve_decided_state(app.decision, app.status)
        if state == DECIDED_GRANTED:
            consented.append(app)
        elif state in (DECIDED_RECOMMENDATION_ONLY, DECIDED_UNDETERMINED):
            active.append(app)
        elif state in (DECIDED_WITHDRAWN, DECIDED_REFUSED):
            historical.append(app)
    return consented, active, historical


def _historical_positions(
    scope_type: str, scope_label: str, apps: list[Application], prospective_overrides: dict[int, dict] | None,
) -> list[AffordablePosition]:
    """Withdrawn/refused applications with genuine independent AH evidence,
    retained for provenance ONLY - never ranked/conflict-resolved against
    each other (they are all already superseded by definition; a consumer
    wanting to know why a scheme's history looked a certain way can read
    every one of them, not just a single "winner")."""
    positions = []
    for app in apps:
        fields = _effective_fields(app, prospective_overrides)
        if fields is None or _has_no_independent_affordable_position(fields):
            continue
        positions.append(_position(scope_type, scope_label, app, fields))
    return positions


def compute_affordable_housing_scope_summary(
    applications: list[Application], *, prospective_overrides: dict[int, dict] | None = None,
) -> AffordableHousingSummary:
    """Reuses app.pipeline.phase_tracking.group_applications_by_operative_
    scope (Gate 2B-2A - individual dwelling plots folded into whole-site,
    never their own AH scope) rather than inventing a second, parallel
    scope hierarchy.

    Scope confidence (Part 8: "do not guess scope"): when a site has at
    least one genuinely NAMED peer scope, an application that names no
    phase/parcel of its own is treated as describing the whole scheme (the
    master/outline application typically doesn't repeat a phase code its
    own reserved-matters children do) - scope_type=SCOPE_WHOLE_SITE. When
    NO application on the site names any peer scope at all, there is no
    positive evidence this position covers the whole scheme rather than
    one as-yet-unnamed part of it, so it is returned with
    scope_type=SCOPE_UNCLEAR instead - the position itself is still
    surfaced (Part 13: a positive figure must never be dropped), just not
    asserted as confidently whole-site.

    Gate 2B-2A: within EACH scope, applications are further partitioned by
    decided state before any position is resolved - a withdrawn/refused
    application's AH evidence can never become the CONSENTED or ACTIVE
    answer for that scope, only a HISTORICAL one (see
    _partition_by_decided_state)."""
    groups = group_applications_by_operative_scope(applications)
    whole_site_apps = groups.get((UNPHASED_LABEL, "phase"), [])
    named_groups = {key: apps for key, apps in groups.items() if key[0] != UNPHASED_LABEL}

    conflicts: list[ScopeConflict] = []
    phases: list[AffordablePosition] = []
    active_phases: list[AffordablePosition] = []
    historical: list[AffordablePosition] = []

    for (code, kind), apps in named_groups.items():
        scope_type = SCOPE_PHASE if kind == "phase" else SCOPE_PLOT
        label = f"{'Phase' if kind == 'phase' else 'Plot'} {code}"
        consented_apps, active_apps, historical_apps = _partition_by_decided_state(apps)

        position, conflict = _resolve_group_position(scope_type, label, consented_apps, prospective_overrides)
        if position is not None:
            phases.append(position)
        if conflict is not None:
            conflicts.append(conflict)

        active_position, active_conflict = _resolve_group_position(scope_type, label, active_apps, prospective_overrides)
        if active_position is not None:
            active_phases.append(active_position)
        if active_conflict is not None:
            conflicts.append(active_conflict)

        historical.extend(_historical_positions(scope_type, label, historical_apps, prospective_overrides))

    phases.sort(key=lambda p: p.scope_label)
    active_phases.sort(key=lambda p: p.scope_label)

    whole_site: AffordablePosition | None = None
    active_whole_site: AffordablePosition | None = None
    if whole_site_apps:
        scope_type = SCOPE_WHOLE_SITE if named_groups else SCOPE_UNCLEAR
        label = "Whole site" if named_groups else "Whole site (scope not confirmed by phase evidence)"
        consented_apps, active_apps, historical_apps = _partition_by_decided_state(whole_site_apps)

        whole_site, whole_site_conflict = _resolve_group_position(scope_type, label, consented_apps, prospective_overrides)
        if whole_site_conflict is not None:
            conflicts.append(whole_site_conflict)

        active_whole_site, active_whole_site_conflict = _resolve_group_position(
            scope_type, label, active_apps, prospective_overrides
        )
        if active_whole_site_conflict is not None:
            conflicts.append(active_whole_site_conflict)

        historical.extend(_historical_positions(scope_type, label, historical_apps, prospective_overrides))

    return AffordableHousingSummary(
        whole_site=whole_site, phases=tuple(phases),
        active_whole_site=active_whole_site, active_phases=tuple(active_phases),
        historical=tuple(historical), conflicts=tuple(conflicts),
    )


def _fmt_pct(value: float | None) -> str:
    return f"{value}%" if value is not None else "percentage not evidenced"


def _fmt_units(value: int | None) -> str:
    return f"{value} affordable homes" if value is not None else "unit count not evidenced"


def format_affordable_housing_lines(summary: AffordableHousingSummary) -> list[str]:
    """Renders the AffordableHousingSummary into the same short, grounded-
    fact line style already used by every other block in build_summary_
    prompt (app.reporting.scheme_summary) - the model restates/synthesises
    these lines, it never rediscovers scope from raw documents itself
    (Part 20 of this PR's own task spec). Gate 2B-2A: consented, active and
    historical positions are labelled distinctly so the model never
    narrates a withdrawn application's figure as the current position."""
    lines: list[str] = []

    def _scope_qualifier(p: AffordablePosition) -> str:
        return (
            "" if p.scope_type == SCOPE_WHOLE_SITE
            else " - exact scheme/phase scope not established by linked evidence; state this figure but flag the scope as unconfirmed/needing manual review, do not assert it covers the whole site with confidence"
        )

    if summary.whole_site is not None:
        p = summary.whole_site
        lines.append(
            f"WHOLE SITE AFFORDABLE HOUSING (CONSENTED){_scope_qualifier(p)}: status {p.status or 'unknown'} - "
            f"{_fmt_pct(p.percentage)} / {_fmt_units(p.units)}, tenure: {p.tenure or 'not evidenced'} "
            f"(source: {p.application_reference})"
        )
        if p.notes:
            lines.append(f"WHOLE SITE AFFORDABLE HOUSING NOTES: {p.notes}")

    if summary.active_whole_site is not None:
        p = summary.active_whole_site
        lines.append(
            f"WHOLE SITE AFFORDABLE HOUSING (ACTIVE PROPOSAL, not yet consented){_scope_qualifier(p)}: "
            f"status {p.status or 'unknown'} - {_fmt_pct(p.percentage)} / {_fmt_units(p.units)}, "
            f"tenure: {p.tenure or 'not evidenced'} (source: {p.application_reference})"
        )
        if p.notes:
            lines.append(f"WHOLE SITE AFFORDABLE HOUSING NOTES: {p.notes}")

    for p in summary.phases:
        lines.append(
            f"{p.scope_label.upper()} AFFORDABLE HOUSING (CONSENTED): status {p.status or 'unknown'} - "
            f"{_fmt_pct(p.percentage)} / {_fmt_units(p.units)}, tenure: {p.tenure or 'not evidenced'} "
            f"(source: {p.application_reference})"
        )
        if p.notes:
            lines.append(f"{p.scope_label.upper()} AFFORDABLE HOUSING NOTES: {p.notes}")

    for p in summary.active_phases:
        lines.append(
            f"{p.scope_label.upper()} AFFORDABLE HOUSING (ACTIVE PROPOSAL, not yet consented): "
            f"status {p.status or 'unknown'} - {_fmt_pct(p.percentage)} / {_fmt_units(p.units)}, "
            f"tenure: {p.tenure or 'not evidenced'} (source: {p.application_reference})"
        )
        if p.notes:
            lines.append(f"{p.scope_label.upper()} AFFORDABLE HOUSING NOTES: {p.notes}")

    for p in summary.historical:
        lines.append(
            f"{p.scope_label.upper()} AFFORDABLE HOUSING - HISTORICAL / {p.decided_state.upper()} "
            f"(NOT the current position, retained for provenance only): {_fmt_pct(p.percentage)} / "
            f"{_fmt_units(p.units)} (source: {p.application_reference}). Do not present this as the current "
            f"affordable-housing position."
        )

    for c in summary.conflicts:
        detail = "; ".join(
            f"{pos.application_reference} states {_fmt_pct(pos.percentage)} (status {pos.status or 'unknown'})"
            for pos in c.positions
        )
        lines.append(
            f"AFFORDABLE HOUSING CONFLICT ({c.scope_label}): linked applications give inconsistent affordable "
            f"housing positions for the same scope with no evidence one supersedes the other - {detail}. State "
            f"plainly that this figure is unresolved and MANUAL REVIEW RECOMMENDED - do not pick one value or "
            f"average them."
        )

    return lines
