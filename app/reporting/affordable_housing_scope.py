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

import re
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
    # Gate 2B-2B.1 (Brixham Road AH semantic hardening) - total_units_final
    # is already a fully-reconciled, existing field (app.extraction.
    # reconcile), read here ONLY to detect when the stored `affordable_
    # percentage_final` and the affordable/total unit-derived percentage
    # materially disagree - see _units_implied_percentage_reconciliation
    # below. Not a new persisted field; no schema change.
    "total_units_final",
)

# Gate 2B-2B.1 - the tolerance (percentage points) below which a stored
# affordable_percentage_final and the affordable/total unit-derived
# percentage are treated as the same figure (ordinary rounding in the
# source document), grounded in the real stored data: of 582 real
# applications with both an affordable and a total unit count, 558
# (~96%) agree with the stored percentage to within 2.0pp, and the
# remaining ~4% are genuine discrepancies worth surfacing rather than
# silently combining (confirmed live: Brixham Road's 54/145 units-implied
# ~37.2% figure differs from its own stored 40.0% by ~2.76pp).
_PERCENTAGE_RECONCILIATION_TOLERANCE = 2.0

# Gate 2B-2B.1 pre-merge remediation (Product Owner correction) - the
# GENERIC arithmetic check above (affordable_units_final / total_units_
# final) establishes ONLY that a percentage was implied by the unit count;
# it must never be labelled "on-site" or any other basis, since arithmetic
# alone cannot establish what the affordable_units_final figure physically
# represents. A SEPARATE, narrow, deterministic reading of explicit
# wording already present in the existing affordable_tenure_split_final
# free-text field (never a new persisted column, never an LLM, never
# fuzzy matching) is used ONLY when the source text itself states a
# specific basis - confirmed real case: Brixham Road's stored
# affordable_tenure_split_final is literally "37% on-site, 3% financial
# contribution". These two patterns are deliberately narrow (exactly the
# two bases evidenced in a real record) - not a general on-site/off-site/
# policy-equivalent parser speculatively built ahead of evidence.
_EXPLICIT_ONSITE_PCT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*on-?\s*site", re.IGNORECASE)
_EXPLICIT_FINANCIAL_CONTRIBUTION_PCT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*financial contribution", re.IGNORECASE)


def _explicit_evidence_percentages(tenure_text: str | None) -> tuple[float | None, float | None]:
    """(explicit_onsite_percentage, explicit_financial_contribution_
    percentage) - both None unless the source text itself literally states
    that basis (e.g. "37% on-site, 3% financial contribution"). Never
    inferred from the generic unit-derived percentage or from the stored
    affordable_percentage_final - only from this application's own
    recorded wording."""
    if not tenure_text:
        return None, None
    onsite_match = _EXPLICIT_ONSITE_PCT_PATTERN.search(tenure_text)
    contribution_match = _EXPLICIT_FINANCIAL_CONTRIBUTION_PCT_PATTERN.search(tenure_text)
    onsite = float(onsite_match.group(1)) if onsite_match else None
    contribution = float(contribution_match.group(1)) if contribution_match else None
    return onsite, contribution


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
    # Gate 2B-2B.1 (Brixham Road; renamed from `onsite_percentage` in the
    # Product Owner's pre-merge remediation - arithmetic alone never
    # establishes a physical basis) - PURELY the ratio affordable_units_
    # final / total_units_final, computed from two already-trusted fields.
    # None whenever either figure is unavailable, never guessed. Carries
    # NO claim about what physical provision the affordable unit count
    # represents (on-site, off-site, or anything else) - it is a units-to-
    # total ratio, nothing more.
    units_implied_percentage: float | None = None
    # False exactly when units_implied_percentage and `percentage` above
    # (the STORED percentage) disagree by more than
    # _PERCENTAGE_RECONCILIATION_TOLERANCE - a signal to show BOTH figures
    # distinctly and flag them as not reconciling. Never asserts WHY they
    # differ (an on-site/policy split, a genuine data error, or something
    # else) - see explicit_onsite_percentage/explicit_financial_
    # contribution_percentage below for the ONLY basis-specific claims this
    # module makes, and only when the source text itself states them.
    percentage_reconciles: bool = True
    # Gate 2B-2B.1 pre-merge remediation - set ONLY when this application's
    # own affordable_tenure_split_final text explicitly states an on-site/
    # financial-contribution percentage (see _explicit_evidence_
    # percentages) - never inferred, never defaulted from the generic
    # units_implied_percentage above.
    explicit_onsite_percentage: float | None = None
    explicit_financial_contribution_percentage: float | None = None


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


# Gate 2B-2B.1 (Section 23, Pinfold/Edenfield production defect) - a note
# that itself says "we found nothing" must never count as affirmative
# evidence of a genuine zero-AH position. Confirmed live: Pinfold/
# Edenfield's cross-boundary consultation-response record has
# affordable_percentage_final=0.0/affordable_units_final=0/status="unknown"
# (none of which alone establish independent evidence) PLUS the note "No
# affordable housing provision mentioned in the decision notice..." - a
# statement of absent information, not a statement of a confirmed zero -
# which the old has_notes check (any non-empty text) incorrectly treated
# as genuine evidence. Deliberately narrow and literal (no fuzzy/LLM
# matching, Section 22/23's own "do not add an LLM" instruction) - matches
# only the small set of explicit absence-of-information phrasings named in
# the Gate 2B-2B.1 brief; a note that says something substantive (e.g.
# Brixham's "...remains unclear as legal agreements are pending", which
# co-occurs with a real evidenced percentage/unit count independent of
# this check entirely) is unaffected, since has_percentage/has_units below
# never depend on notes content at all.
_ABSENCE_OF_INFORMATION_NOTE_PHRASES = (
    "no affordable housing provision mentioned",
    "not mentioned in the decision notice",
    "no mention of affordable housing",
    "no information",
    "not identified",
)


def _has_no_independent_affordable_position(fields: dict) -> bool:
    """True means this application carries no independent affordable-housing
    evidence of its own - a technical/condition-discharge/drainage/highways
    filing with nothing to say about affordable housing, distinct from an
    application that explicitly evidences a genuine 0% position (Part 5/6 of
    this PR's own task spec). A real evidenced position always leaves SOME
    trace beyond a bare zero: either a non-"unknown" status (B3 only sets one
    when it found evidence to classify), or explanatory notes (e.g. "No
    affordable housing is provided within Phase 2"), or a non-zero
    percentage/unit figure. Gate 2B-2B.1 (Section 23): notes that themselves
    state an ABSENCE of information (see _ABSENCE_OF_INFORMATION_NOTE_
    PHRASES) never count as that "some trace" on their own."""
    status = fields["affordable_housing_status"]
    has_real_status = status not in (None, "unknown")
    notes_text = (fields["affordable_housing_notes"] or "").strip()
    notes_lower = notes_text.lower()
    has_notes = bool(notes_text) and not any(phrase in notes_lower for phrase in _ABSENCE_OF_INFORMATION_NOTE_PHRASES)
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


def _units_implied_percentage_reconciliation(fields: dict) -> tuple[float | None, bool]:
    """Gate 2B-2B.1 (Brixham Road; renamed per Product Owner pre-merge
    remediation) - purely arithmetic, from two already-trusted fields
    (affordable_units_final / total_units_final), never a new persisted
    field and never a guess at WHY the two figures might differ - the
    result is a units-to-total RATIO, never labelled with any physical
    basis (on-site, off-site, or otherwise). Returns
    (units_implied_percentage, percentage_reconciles).
    units_implied_percentage is None whenever either input is unavailable.
    percentage_reconciles is True whenever there is nothing to compare
    (either figure missing) OR the two agree within
    _PERCENTAGE_RECONCILIATION_TOLERANCE - calibrated against the real
    stored data (96% of applications with both figures agree to within
    2.0pp; see that constant's own docstring)."""
    units = fields["affordable_units_final"]
    total = fields["total_units_final"]
    stored_pct = fields["affordable_percentage_final"]
    if units is None or not total:
        return None, True
    units_implied_percentage = round(units / total * 100, 1)
    if stored_pct is None:
        return units_implied_percentage, True
    return units_implied_percentage, abs(units_implied_percentage - stored_pct) <= _PERCENTAGE_RECONCILIATION_TOLERANCE


def compute_percentage_reconciliation(scheme) -> dict:
    """Gate 2B-2B.1 final closure micro-fix - the single public entry
    point for ANY consumer that already has one, already-selected
    SchemeIntelligence row (not a full multi-application AffordablePosition
    resolution) and needs to know whether ITS OWN recorded
    affordable_percentage_final reconciles with its own affordable/total
    unit count, without re-deriving the check or re-parsing tenure text a
    second time. Reuses the exact same _units_implied_percentage_
    reconciliation / _explicit_evidence_percentages helpers
    AffordablePosition itself is built from (see _position above) - no
    second implementation, no new regex, no schema change.

    Used by app.reporting.residential_mix's Structured Summary (the
    confirmed Brixham Road production defect: that consumer independently
    read affordable_units_final/affordable_percentage_final straight off a
    SchemeIntelligence row and combined them into "54 homes, representing
    40%" with no awareness that the two figures do not reconcile).

    `scheme` is a SchemeIntelligence row or None (mirrors every other
    function in this module's own scheme-shaped helpers). Returns a dict:
        units_implied_percentage: float | None
        percentage_reconciles: bool (True when there is nothing to
            compare, or the two figures agree within the existing
            tolerance - see _units_implied_percentage_reconciliation)
        explicit_onsite_percentage: float | None
        explicit_financial_contribution_percentage: float | None
    identical in meaning to AffordablePosition's own same-named fields."""
    if scheme is None:
        return {
            "units_implied_percentage": None, "percentage_reconciles": True,
            "explicit_onsite_percentage": None, "explicit_financial_contribution_percentage": None,
        }
    fields = {
        "affordable_units_final": scheme.affordable_units_final,
        "total_units_final": scheme.total_units_final,
        "affordable_percentage_final": scheme.affordable_percentage_final,
    }
    units_implied_percentage, percentage_reconciles = _units_implied_percentage_reconciliation(fields)
    explicit_onsite_percentage, explicit_financial_contribution_percentage = _explicit_evidence_percentages(
        scheme.affordable_tenure_split_final,
    )
    return {
        "units_implied_percentage": units_implied_percentage, "percentage_reconciles": percentage_reconciles,
        "explicit_onsite_percentage": explicit_onsite_percentage,
        "explicit_financial_contribution_percentage": explicit_financial_contribution_percentage,
    }


def _position(scope_type: str, scope_label: str, app: Application, fields: dict) -> AffordablePosition:
    units_implied_percentage, percentage_reconciles = _units_implied_percentage_reconciliation(fields)
    explicit_onsite_percentage, explicit_financial_contribution_percentage = _explicit_evidence_percentages(
        fields["affordable_tenure_split_final"],
    )
    return AffordablePosition(
        scope_type=scope_type, scope_label=scope_label,
        application_id=app.id, application_reference=app.reference,
        percentage=fields["affordable_percentage_final"], units=fields["affordable_units_final"],
        tenure=fields["affordable_tenure_split_final"], status=fields["affordable_housing_status"],
        notes=fields["affordable_housing_notes"], decided_state=resolve_decided_state(app.decision, app.status),
        units_implied_percentage=units_implied_percentage, percentage_reconciles=percentage_reconciles,
        explicit_onsite_percentage=explicit_onsite_percentage,
        explicit_financial_contribution_percentage=explicit_financial_contribution_percentage,
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

    def _reconciliation_note(label: str, p: AffordablePosition) -> str | None:
        # Gate 2B-2B.1 (Brixham Road, Product Owner pre-merge remediation) -
        # a stored percentage that does not arithmetically reconcile with
        # the affordable/total unit count is never silently combined into
        # one "N affordable homes representing P%" statement - both
        # figures are surfaced, neither is assumed to be the error, and no
        # basis (on-site, off-site, policy-equivalent, or a genuine data
        # issue) is invented for the generic units-implied figure. If (and
        # only if) this application's own tenure text explicitly states an
        # on-site/financial-contribution basis, that explicit evidence is
        # named separately and distinctly, never as an inference from the
        # arithmetic figure.
        if p.percentage_reconciles or p.units_implied_percentage is None or p.percentage is None:
            return None
        explicit_bits = []
        if p.explicit_onsite_percentage is not None:
            explicit_bits.append(f"the source evidence explicitly states {_fmt_pct(p.explicit_onsite_percentage)} on-site")
        if p.explicit_financial_contribution_percentage is not None:
            explicit_bits.append(
                f"the source evidence explicitly states a {_fmt_pct(p.explicit_financial_contribution_percentage)} "
                f"financial contribution"
            )
        explicit_sentence = (
            f" The application's own recorded evidence distinguishes these bases: {'; '.join(explicit_bits)} - "
            f"use these exact figures/labels if you state a basis, never invent one for a scheme without this "
            f"explicit wording."
            if explicit_bits else
            " No source evidence states what physical basis (on-site, off-site, or otherwise) either figure "
            "represents - do not invent one."
        )
        return (
            f"{label} PERCENTAGE DOES NOT RECONCILE: the recorded affordable percentage ({_fmt_pct(p.percentage)}) "
            f"does not match the units-implied percentage from the {_fmt_units(p.units)} alone against the "
            f"scheme's total units (~{_fmt_pct(p.units_implied_percentage)}, a plain ratio, not a claim about "
            f"on-site/off-site provision). Both the {_fmt_units(p.units)} and the {_fmt_pct(p.percentage)} figure "
            f"are evidenced; state them distinctly, never as one combined figure (e.g. never state "
            f"'{_fmt_units(p.units)} representing {_fmt_pct(p.percentage)}' as if they describe the same "
            f"denominator).{explicit_sentence} MANUAL REVIEW RECOMMENDED."
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
        note = _reconciliation_note("WHOLE SITE AFFORDABLE HOUSING (CONSENTED)", p)
        if note:
            lines.append(note)

    if summary.active_whole_site is not None:
        p = summary.active_whole_site
        lines.append(
            f"WHOLE SITE AFFORDABLE HOUSING (ACTIVE PROPOSAL, not yet consented){_scope_qualifier(p)}: "
            f"status {p.status or 'unknown'} - {_fmt_pct(p.percentage)} / {_fmt_units(p.units)}, "
            f"tenure: {p.tenure or 'not evidenced'} (source: {p.application_reference})"
        )
        if p.notes:
            lines.append(f"WHOLE SITE AFFORDABLE HOUSING NOTES: {p.notes}")
        note = _reconciliation_note("WHOLE SITE AFFORDABLE HOUSING (ACTIVE PROPOSAL)", p)
        if note:
            lines.append(note)

    for p in summary.phases:
        lines.append(
            f"{p.scope_label.upper()} AFFORDABLE HOUSING (CONSENTED): status {p.status or 'unknown'} - "
            f"{_fmt_pct(p.percentage)} / {_fmt_units(p.units)}, tenure: {p.tenure or 'not evidenced'} "
            f"(source: {p.application_reference})"
        )
        if p.notes:
            lines.append(f"{p.scope_label.upper()} AFFORDABLE HOUSING NOTES: {p.notes}")
        note = _reconciliation_note(f"{p.scope_label.upper()} AFFORDABLE HOUSING (CONSENTED)", p)
        if note:
            lines.append(note)

    for p in summary.active_phases:
        lines.append(
            f"{p.scope_label.upper()} AFFORDABLE HOUSING (ACTIVE PROPOSAL, not yet consented): "
            f"status {p.status or 'unknown'} - {_fmt_pct(p.percentage)} / {_fmt_units(p.units)}, "
            f"tenure: {p.tenure or 'not evidenced'} (source: {p.application_reference})"
        )
        if p.notes:
            lines.append(f"{p.scope_label.upper()} AFFORDABLE HOUSING NOTES: {p.notes}")
        note = _reconciliation_note(f"{p.scope_label.upper()} AFFORDABLE HOUSING (ACTIVE PROPOSAL)", p)
        if note:
            lines.append(note)

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
