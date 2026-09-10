"""Gate 2B-1 - Scheme / Application / Phase Reconciliation (V1).

Answers exactly one question, deliberately separate from every other
question this codebase already answers about a scheme:

    "Within an already-consolidated Site, WHICH application / phase /
    proposal version is ELIGIBLE to control each acquisition-relevant
    scheme fact - and where the evidence does not support a definitive
    choice, say so rather than picking one."

This replaces, at the scheme-fact boundary, the generic selection done
today by:
  - app.ui.common.pick_representative_application - "most complete
    extraction, then most recently received" (no awareness of application
    type, role, decided state, or supersession), and
  - app.ui.common.aggregate_scheme_fields - first-non-null value per
    field, scanning in that same order.
Both remain available and unchanged for their other callers (the
opportunity universe / fingerprints, review pages, allocation coverage);
this module is a NEW, deterministic layer consulted where scheme facts are
presented to a user (see app.reporting.site_profile).

Deliberately NOT an extraction gate:
  - adds no scraper, no NLP heuristic, no AI pass, no new regex-for-
    meaning. Every input is evidence THIS platform already extracted.
  - reuses, unmodified: app.scrapers.unit_filter.classify_application_
    category / is_administrative_application_type (application typing),
    app.pipeline.material_change.classify_planning_state (planning-state
    vocabulary), app.pipeline.phase_tracking.group_applications_by_phase
    (phase/plot scope), app.reporting.affordable_housing_scope.compute_
    affordable_housing_scope_summary (affordable-housing scope/authority
    reconciliation - a working prototype of exactly this pattern, kept as
    the single source of AH reconciliation rather than re-implemented).

Deliberately NOT persisted: everything here is computed fresh on every
call, exactly like affordable_housing_scope.py's own throwaway objects and
aggregate_scheme_fields's own `merged` dict. No schema change. Persistence
and versioning of the reconciled fact layer are Gate 2B-2, not this gate.

Two Product-Owner safeguards enforced here (see docs/PRODUCT_ROADMAP.md,
Gate 2B-1):
  - RESIDENTIAL-ONLY QUANTUM IS NOT A NEW INFERENCE. A residential-only
    operative figure is resolved ONLY where existing evidence already
    supports a deterministic distinction between general residential
    dwellings and specialist accommodation (care beds, extra-care,
    supported living). Where it does not, the wider/all-use figure is
    preserved separately and the residential-only value is explicitly
    `not_determined` - never a derived split.
  - SECTION 73 / VARIATION AUTHORITY IS FACT-SPECIFIC. A later S73 /
    variation does NOT supersede all underlying-permission facts by
    recency. It controls a specific fact ONLY where existing extracted
    evidence (its own SchemeIntelligence figures) shows it addresses that
    fact. Unclear -> the underlying permission continues to control.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from app.db.models import Application
from app.pipeline.material_change import (
    STATE_GRANTED,
    STATE_RECOMMENDATION_MADE,
    STATE_RECOMMENDED_FOR_APPROVAL,
    STATE_RECOMMENDED_FOR_REFUSAL,
    STATE_REFUSED,
    STATE_WITHDRAWN,
    classify_planning_state,
)
from app.pipeline.lapse_tracking import parse_portal_date
from app.pipeline.phase_tracking import UNPHASED_LABEL, group_applications_by_phase
from app.reporting.affordable_housing_scope import (
    AffordableHousingSummary,
    compute_affordable_housing_scope_summary,
)
from app.scrapers.unit_filter import classify_application_category, is_administrative_application_type

# --- Planning roles --------------------------------------------------------
# How an application participates in the planning lifecycle and whether it
# may control particular scheme facts. DELIBERATELY DISTINCT from
# app.scrapers.unit_filter's `application_category` (qualification /
# filtering / business classification) - the two taxonomies are not
# merged. `planning_role` is derived FROM `application_category` (plus the
# portal's own Application Type field and a few proposal-text hints the
# category classifier already relies on), never the other way round.

ROLE_OUTLINE = "outline"
ROLE_HYBRID = "hybrid"
ROLE_FULL = "full"
ROLE_RESERVED_MATTERS = "reserved_matters"
ROLE_S73_VARIATION = "s73_variation"
ROLE_NMC_AMENDMENT = "nmc_amendment"
ROLE_CONDITION_DISCHARGE = "condition_discharge"
ROLE_EIA_SCREENING = "eia_screening"
ROLE_EIA_SCOPING = "eia_scoping"
ROLE_PRIOR_APPROVAL = "prior_approval"
ROLE_CERTIFICATE = "certificate_of_lawfulness"
ROLE_LISTED_BUILDING_OR_ANCILLARY = "listed_building_or_ancillary"
ROLE_EXTERNAL_CONSULTATION = "external_consultation"
ROLE_OTHER_SUBSTANTIVE = "other_substantive"
ROLE_UNKNOWN = "unknown"

# Roles that MAY establish substantive planning permission / operative
# residential quantum. Everything else is barred from substantive facts
# (the hard non-substantive guardrail). ROLE_S73_VARIATION is deliberately
# in NEITHER set - it is "conditionally substantive": eligible for a fact
# only where existing evidence shows it varies that fact (see
# _s73_addresses_units / the AH scope guard).
SUBSTANTIVE_ROLES = frozenset({
    ROLE_OUTLINE, ROLE_HYBRID, ROLE_FULL, ROLE_RESERVED_MATTERS, ROLE_OTHER_SUBSTANTIVE,
})
NON_SUBSTANTIVE_ROLES = frozenset({
    ROLE_NMC_AMENDMENT, ROLE_CONDITION_DISCHARGE, ROLE_EIA_SCREENING, ROLE_EIA_SCOPING,
    ROLE_PRIOR_APPROVAL, ROLE_CERTIFICATE, ROLE_LISTED_BUILDING_OR_ANCILLARY,
    ROLE_EXTERNAL_CONSULTATION, ROLE_UNKNOWN,
})

# --- Decided-state overlay ----------------------------------------------
# Derived from app.pipeline.material_change.classify_planning_state (the
# one canonical planning-state classifier - see that module), collapsed to
# the 5 buckets 2B-1 ranking needs.
DECIDED_GRANTED = "granted"
DECIDED_REFUSED = "refused"
DECIDED_WITHDRAWN = "withdrawn"
DECIDED_RECOMMENDATION_ONLY = "recommendation_only"
DECIDED_UNDETERMINED = "undetermined"

_DECIDED_BY_STATE = {
    STATE_GRANTED: DECIDED_GRANTED,
    STATE_REFUSED: DECIDED_REFUSED,
    STATE_WITHDRAWN: DECIDED_WITHDRAWN,
    STATE_RECOMMENDATION_MADE: DECIDED_RECOMMENDATION_ONLY,
    STATE_RECOMMENDED_FOR_APPROVAL: DECIDED_RECOMMENDATION_ONLY,
    STATE_RECOMMENDED_FOR_REFUSAL: DECIDED_RECOMMENDATION_ONLY,
}

# --- Fact-resolution states -------------------------------------------
FACT_RESOLVED = "resolved"
FACT_NOT_DETERMINED = "not_determined"
FACT_CONFLICT = "conflict"

# --- Scope (reuses affordable_housing_scope's vocabulary) --------------
SCOPE_WHOLE_SITE = "whole_site"
SCOPE_UNCLEAR = "unclear"
SCOPE_PHASE = "phase"
SCOPE_PLOT = "plot"


def _proposal_norm(app: Application) -> str:
    return f"{app.proposal or ''} {app.application_type or ''}".lower()


def resolve_planning_role(app: Application) -> str:
    """Deterministic planning role for one application, from evidence this
    platform already holds: the portal's own Application Type field
    (most authoritative when present), app.scrapers.unit_filter's existing
    category classifier, and the same proposal-text keywords that
    classifier already keys off. No new NLP.

    `application_category` is NOT consulted as a stored value (it may be
    stale on legacy rows - the same reasoning app.ui.common.load_
    applications_for_sites uses when it re-classifies live); the classifier
    is re-run on the current proposal text instead.
    """
    text = _proposal_norm(app)
    app_type = (app.application_type or "").lower()

    # EIA screening vs scoping - distinct roles (scoping is a later,
    # more detailed pre-application step, but neither is ever substantive).
    category = classify_application_category(app.proposal)
    if category == "screening_or_scoping_opinion" or "screening opinion" in app_type or "scoping opinion" in app_type:
        if "scoping" in text:
            return ROLE_EIA_SCOPING
        return ROLE_EIA_SCREENING

    if category == "external_consultation" or "adjoining authority consultation" in app_type:
        return ROLE_EXTERNAL_CONSULTATION

    if category == "condition_discharge_or_details" or any(
        k in app_type for k in ("discharge of condition", "approval of details")
    ):
        return ROLE_CONDITION_DISCHARGE

    if category == "variation_or_amendment" or any(
        k in app_type for k in ("non-material amendment", "non material amendment", "section 73", "s73",
                                "variation of condition", "removal of condition", "minor material amendment")
    ):
        if any(k in text for k in ("non-material amendment", "non material amendment", "nmc", "nma ",
                                   "working amendment")) or "non-material" in app_type:
            return ROLE_NMC_AMENDMENT
        # "deed of variation" modifies an S106's legal terms - not a
        # development application at all; treat as ancillary, never as a
        # scheme-fact source.
        if "deed of variation" in text:
            return ROLE_LISTED_BUILDING_OR_ANCILLARY
        return ROLE_S73_VARIATION

    if "certificate of lawful" in text or "lawful development certificate" in text or "certificate of lawful" in app_type:
        return ROLE_CERTIFICATE
    if "prior approval" in text or "prior approval" in app_type:
        return ROLE_PRIOR_APPROVAL
    if "listed building" in text or "listed building" in app_type or "advertisement consent" in text:
        return ROLE_LISTED_BUILDING_OR_ANCILLARY

    if category == "reserved_matters" or "reserved matters" in app_type:
        return ROLE_RESERVED_MATTERS

    if any(k in text for k in ("hybrid", "part outline part full", "part full part outline",
                               "outline and full", "full and outline")):
        return ROLE_HYBRID
    if category == "outline_application" or "outline" in app_type or any(
        k in text for k in ("outline application", "outline planning", "outline permission")
    ):
        return ROLE_OUTLINE

    if category in ("primary_residential", "affordable_or_specialist_housing", "mixed_use",
                    "build_to_rent"):
        return ROLE_FULL
    if is_administrative_application_type(app.application_type):
        return ROLE_LISTED_BUILDING_OR_ANCILLARY
    if category == "non_target_admin_or_minor":
        return ROLE_LISTED_BUILDING_OR_ANCILLARY
    if category == "unknown":
        return ROLE_UNKNOWN
    return ROLE_OTHER_SUBSTANTIVE


def resolve_decided_state(app: Application) -> str:
    return _DECIDED_BY_STATE.get(classify_planning_state(app.decision, app.status), DECIDED_UNDETERMINED)


@dataclass(frozen=True)
class ResolvedApplication:
    """One application, with its resolved planning role, decided state and
    phase scope - the unit every downstream eligibility/ranking rule
    operates on. Computed once per reconcile_scheme() call."""

    application: Application
    role: str
    decided_state: str
    scope_type: str
    scope_label: str

    @property
    def id(self) -> int:
        return self.application.id

    @property
    def reference(self) -> str:
        return self.application.reference

    @property
    def received(self) -> dt.date:
        return parse_portal_date(self.application.application_received)

    @property
    def decision_date(self) -> dt.date | None:
        return parse_portal_date(self.application.decision_issued_date) if self.application.decision_issued_date else None

    @property
    def is_substantive(self) -> bool:
        return self.role in SUBSTANTIVE_ROLES

    @property
    def scheme(self):
        return self.application.scheme_intelligence


@dataclass(frozen=True)
class FactPosition:
    """One application's stated value for one scheme fact, with the
    provenance needed to explain (or contest) the selection."""

    value: object
    application_id: int
    application_reference: str
    planning_role: str
    decided_state: str
    scope_type: str
    scope_label: str


@dataclass(frozen=True)
class OperativeFact:
    """The reconciled operative position for one scheme fact.

    state == FACT_RESOLVED  -> `value`/`source` populated.
    state == FACT_NOT_DETERMINED -> no eligible/rankable source; `value` is
        None; `reason` explains why (never a silent guess).
    state == FACT_CONFLICT  -> `conflicts` holds >=2 same-scope positions
        that could not be ranked; `value`/`source` stay None (nothing is
        silently picked).
    """

    fact: str
    state: str
    value: object | None = None
    source: FactPosition | None = None
    confidence: str = "none"  # high | medium | low | none
    reason: str = ""
    conflicts: tuple[FactPosition, ...] = ()

    @property
    def determined(self) -> bool:
        return self.state == FACT_RESOLVED


@dataclass(frozen=True)
class ResidentialQuantum:
    """Residential unit count, with approved / proposed / superseded held
    separately - never collapsed into one number (Product Owner
    requirement). `residential_only` is subject to the "no new inference"
    safeguard; `all_use_total` is the wider figure preserved alongside it."""

    approved: OperativeFact
    proposed: OperativeFact
    residential_only: OperativeFact
    all_use_total: OperativeFact
    superseded: tuple[FactPosition, ...] = ()


@dataclass(frozen=True)
class SchemeReconciliation:
    resolved_applications: tuple[ResolvedApplication, ...]
    lead_application: OperativeFact          # value = reference string
    operative_planning_status: OperativeFact
    operative_permission: OperativeFact      # value = granted permission reference, or not_determined
    residential: ResidentialQuantum
    unit_mix: OperativeFact                  # value = narrative typology / specialist string
    affordable_housing: AffordableHousingSummary
    scope_note: str


# --- Scope resolution ---------------------------------------------------


def _resolve_scopes(applications: list[Application]) -> dict[int, tuple[str, str]]:
    """{application_id: (scope_type, scope_label)} using the SAME regex
    phase/plot grouping app.pipeline.phase_tracking already powers the Site
    Summary phase breakdown with. An application naming several phases is
    treated as whole-site for reconciliation purposes (it spans them);
    only an application naming exactly one phase/plot is scoped to it."""
    groups = group_applications_by_phase(applications)
    named = {k: v for k, v in groups.items() if k[0] != UNPHASED_LABEL}
    per_app_named: dict[int, list[tuple[str, str]]] = {}
    for (code, kind), apps in named.items():
        for a in apps:
            per_app_named.setdefault(a.id, []).append((code, kind))

    out: dict[int, tuple[str, str]] = {}
    for a in applications:
        labels = per_app_named.get(a.id, [])
        if len(labels) == 1:
            code, kind = labels[0]
            stype = SCOPE_PHASE if kind == "phase" else SCOPE_PLOT
            out[a.id] = (stype, f"{'Phase' if kind == 'phase' else 'Plot'} {code}")
        elif named:
            out[a.id] = (SCOPE_WHOLE_SITE, "Whole site")
        else:
            # No application on the site names any phase at all - no
            # positive evidence of whole-site vs one unnamed part.
            out[a.id] = (SCOPE_UNCLEAR, "Whole site (scope not confirmed by phase evidence)")
    return out


def resolve_applications(applications: list[Application]) -> list[ResolvedApplication]:
    scopes = _resolve_scopes(applications)
    resolved = []
    for a in applications:
        stype, slabel = scopes.get(a.id, (SCOPE_UNCLEAR, "Whole site (scope not confirmed by phase evidence)"))
        resolved.append(ResolvedApplication(
            application=a, role=resolve_planning_role(a), decided_state=resolve_decided_state(a),
            scope_type=stype, scope_label=slabel,
        ))
    return resolved


# --- Ranking helpers --------------------------------------------------


def _by_grant_then_recency(rs: ResolvedApplication) -> tuple:
    """Sort key: granted-with-a-date first, then latest decision date,
    then latest received date (RECENCY IS A TIE-BREAK ONLY - never the
    primary signal; that is the defect 2B-1 exists to fix)."""
    d = rs.decision_date or dt.date.min
    return (rs.decided_state == DECIDED_GRANTED, d, rs.received, rs.id)


def _position(fact: str, rs: ResolvedApplication, value: object) -> FactPosition:
    return FactPosition(
        value=value, application_id=rs.id, application_reference=rs.reference,
        planning_role=rs.role, decided_state=rs.decided_state,
        scope_type=rs.scope_type, scope_label=rs.scope_label,
    )


def _scheme_total_units(rs: ResolvedApplication) -> int | None:
    si = rs.scheme
    if si is not None and si.total_units_final is not None:
        return int(si.total_units_final)
    return None


def _portal_estimated_units(rs: ResolvedApplication) -> int | None:
    v = rs.application.estimated_unit_count
    return int(v) if v is not None else None


def _s73_addresses_units(rs: ResolvedApplication) -> bool:
    """Safeguard: an S73/variation controls approved units ONLY where
    existing extracted evidence shows it addresses units - i.e. its OWN
    SchemeIntelligence carries a total unit figure (the platform extracted
    one from that application's own documents). No unit figure of its own
    -> it does not supersede the underlying permission's count."""
    return rs.role == ROLE_S73_VARIATION and _scheme_total_units(rs) is not None


# --- Fact resolvers -------------------------------------------------


def _resolve_lead_application(resolved: list[ResolvedApplication]) -> OperativeFact:
    """The single application whose reference/status best represents the
    scheme for headline display - replaces pick_representative_application
    at that boundary. A granted substantive permission if one exists (the
    latest); else the most senior substantive pending application; else
    (nothing substantive at all) explicit not_determined."""
    substantive = [r for r in resolved if r.is_substantive]
    if not substantive:
        return OperativeFact(
            fact="lead_application", state=FACT_NOT_DETERMINED,
            reason="no substantive planning application (outline/full/hybrid/reserved-matters) linked to this site",
        )
    granted = [r for r in substantive if r.decided_state == DECIDED_GRANTED]
    if granted:
        lead = max(granted, key=_by_grant_then_recency)
        return OperativeFact(
            fact="lead_application", state=FACT_RESOLVED, value=lead.reference,
            source=_position("lead_application", lead, lead.reference), confidence="high",
            reason=f"latest granted substantive application ({lead.role})",
        )
    # No grant - the most senior (earliest received) still-live substantive
    # application anchors the scheme; a refused/withdrawn one only if
    # nothing is live.
    live = [r for r in substantive if r.decided_state in (DECIDED_UNDETERMINED, DECIDED_RECOMMENDATION_ONLY)]
    pool = live or substantive
    lead = min(pool, key=lambda r: (r.received, r.id))
    return OperativeFact(
        fact="lead_application", state=FACT_RESOLVED, value=lead.reference,
        source=_position("lead_application", lead, lead.reference), confidence="medium",
        reason=("most senior live substantive application (no grant yet)" if live
                else "most senior substantive application (all refused/withdrawn)"),
    )


def _resolve_planning_status(resolved: list[ResolvedApplication]) -> OperativeFact:
    substantive = [r for r in resolved if r.is_substantive]
    if not substantive:
        return OperativeFact(
            fact="operative_planning_status", state=FACT_NOT_DETERMINED,
            reason="no substantive application; non-substantive filings (screening/discharge/etc.) "
                   "cannot establish an operative planning status",
        )
    granted = [r for r in substantive if r.decided_state == DECIDED_GRANTED]
    if granted:
        lead = max(granted, key=_by_grant_then_recency)
        return OperativeFact(
            fact="operative_planning_status", state=FACT_RESOLVED, value="Permission granted",
            source=_position("operative_planning_status", lead, "Permission granted"), confidence="high",
            reason=f"granted substantive application {lead.reference} ({lead.role})"
                   + (f", decision {lead.application.decision_issued_date}" if lead.application.decision_issued_date else ""),
        )
    recommendation = [r for r in substantive if r.decided_state == DECIDED_RECOMMENDATION_ONLY]
    if recommendation:
        lead = max(recommendation, key=lambda r: (r.received, r.id))
        return OperativeFact(
            fact="operative_planning_status", state=FACT_RESOLVED,
            value="Awaiting decision (officer recommendation made)",
            source=_position("operative_planning_status", lead, lead.application.status), confidence="medium",
            reason=f"substantive application {lead.reference} has an officer recommendation but no formal decision "
                   f"- recommendation is never treated as permission",
        )
    live = [r for r in substantive if r.decided_state == DECIDED_UNDETERMINED]
    if live:
        lead = min(live, key=lambda r: (r.received, r.id))
        return OperativeFact(
            fact="operative_planning_status", state=FACT_RESOLVED, value="Awaiting decision",
            source=_position("operative_planning_status", lead, lead.application.status), confidence="medium",
            reason=f"substantive application {lead.reference} pending",
        )
    # All substantive applications refused/withdrawn.
    lead = max(substantive, key=lambda r: (r.decision_date or dt.date.min, r.received, r.id))
    label = "Refused" if lead.decided_state == DECIDED_REFUSED else "Withdrawn"
    return OperativeFact(
        fact="operative_planning_status", state=FACT_RESOLVED, value=label,
        source=_position("operative_planning_status", lead, label), confidence="medium",
        reason=f"all substantive applications refused/withdrawn; latest is {lead.reference}",
    )


def _resolve_operative_permission(resolved: list[ResolvedApplication]) -> OperativeFact:
    granted = [r for r in resolved if r.is_substantive and r.decided_state == DECIDED_GRANTED]
    if not granted:
        return OperativeFact(
            fact="operative_permission", state=FACT_NOT_DETERMINED,
            reason="no granted substantive application - there is no operative planning permission yet",
        )
    lead = max(granted, key=_by_grant_then_recency)
    superseded = [g for g in granted if g.id != lead.id]
    reason = f"latest granted substantive application ({lead.role})"
    if superseded:
        reason += f"; supersedes {', '.join(g.reference for g in superseded)}"
    return OperativeFact(
        fact="operative_permission", state=FACT_RESOLVED, value=lead.reference,
        source=_position("operative_permission", lead, lead.reference), confidence="high", reason=reason,
    )


def _resolve_approved_units(resolved: list[ResolvedApplication]) -> tuple[OperativeFact, tuple[FactPosition, ...]]:
    """Approved residential units, where consent exists. Eligible sources:
    granted substantive applications, plus an S73/variation ONLY where it
    demonstrably addresses units (safeguard). Reserved matters is eligible
    at its own phase scope. Returns (operative fact, superseded positions)."""
    eligible = [
        r for r in resolved
        if (r.is_substantive and r.decided_state == DECIDED_GRANTED and _scheme_total_units(r) is not None)
        or _s73_addresses_units(r)
    ]
    if not eligible:
        # A granted permission with no extracted unit figure at all -> we
        # know it's approved but not for how many homes.
        any_grant = any(r.is_substantive and r.decided_state == DECIDED_GRANTED for r in resolved)
        return (
            OperativeFact(
                fact="approved_residential_units", state=FACT_NOT_DETERMINED,
                reason=("a substantive permission is granted but no residential unit figure has been extracted from it"
                        if any_grant else "no granted substantive application - no approved unit count exists yet"),
            ),
            (),
        )

    def rank(r: ResolvedApplication) -> tuple:
        # S73 that varies units outranks the base grant it varies; else
        # latest decision date; recency tie-break only.
        return (r.role == ROLE_S73_VARIATION, r.decision_date or dt.date.min, r.received, r.id)

    ranked = sorted(eligible, key=rank, reverse=True)
    operative = ranked[0]
    op_value = _scheme_total_units(operative)

    # Same-scope conflict: two eligible sources at the same scope, same
    # top rank tier, different figures, neither superseding the other.
    same_scope_top = [
        r for r in ranked
        if r.scope_type == operative.scope_type and r.scope_label == operative.scope_label
        and (r.decision_date or dt.date.min) == (operative.decision_date or dt.date.min)
        and (r.role == ROLE_S73_VARIATION) == (operative.role == ROLE_S73_VARIATION)
    ]
    distinct = {_scheme_total_units(r) for r in same_scope_top}
    if len(distinct) > 1:
        positions = tuple(_position("approved_residential_units", r, _scheme_total_units(r)) for r in same_scope_top)
        return (
            OperativeFact(
                fact="approved_residential_units", state=FACT_CONFLICT, conflicts=positions,
                reason="two equally-authoritative applications state different approved unit counts for the same "
                       "scope and neither supersedes the other - manual verification required",
            ),
            (),
        )

    superseded = tuple(
        _position("approved_residential_units", r, _scheme_total_units(r))
        for r in ranked[1:]
        if _scheme_total_units(r) is not None and _scheme_total_units(r) != op_value
    )
    reason = f"granted {operative.role} {operative.reference}"
    if operative.role == ROLE_S73_VARIATION:
        reason = f"S73/variation {operative.reference} carries its own extracted unit figure - it varies the approved count"
    if superseded:
        reason += f"; earlier/other figures ({', '.join(str(p.value) for p in superseded)}) retained as superseded"
    return (
        OperativeFact(
            fact="approved_residential_units", state=FACT_RESOLVED, value=op_value,
            source=_position("approved_residential_units", operative, op_value),
            confidence="high", reason=reason,
        ),
        superseded,
    )


def _resolve_proposed_units(resolved: list[ResolvedApplication]) -> OperativeFact:
    """Current proposed residential units - the live (undetermined /
    recommendation) substantive application's own figure. Where a
    permission is already granted, the approved figure is the acquisition
    fact; this is only meaningful while something is still in play."""
    live = [
        r for r in resolved
        if r.is_substantive and r.decided_state in (DECIDED_UNDETERMINED, DECIDED_RECOMMENDATION_ONLY)
    ]
    with_fig = [r for r in live if _scheme_total_units(r) is not None or _portal_estimated_units(r) is not None]
    if not with_fig:
        if live:
            return OperativeFact(
                fact="proposed_residential_units", state=FACT_NOT_DETERMINED,
                reason="a substantive application is live but no residential unit figure has been extracted or "
                       "estimated for it yet",
            )
        return OperativeFact(
            fact="proposed_residential_units", state=FACT_NOT_DETERMINED,
            reason="no live substantive application - nothing is currently proposed",
        )
    lead = max(with_fig, key=lambda r: (r.received, r.id))
    extracted = _scheme_total_units(lead)
    value = extracted if extracted is not None else _portal_estimated_units(lead)
    return OperativeFact(
        fact="proposed_residential_units", state=FACT_RESOLVED, value=value,
        source=_position("proposed_residential_units", lead, value),
        confidence="high" if extracted is not None else "low",
        reason=(f"most recent live substantive application {lead.reference}"
                + ("" if extracted is not None else " (portal-listing estimate only - not document-verified)")),
    )


def _resolve_all_use_total(resolved: list[ResolvedApplication], approved: OperativeFact, proposed: OperativeFact) -> OperativeFact:
    """The wider / all-use total to preserve alongside a residential-only
    figure. Simply the operative substantive figure (approved if consent
    exists, else proposed) - labelled as all-use because 2B-1 does not
    attempt to net out specialist accommodation (see residential-only)."""
    if approved.state == FACT_RESOLVED:
        return OperativeFact(
            fact="all_use_total_units", state=FACT_RESOLVED, value=approved.value,
            source=approved.source, confidence=approved.confidence,
            reason="operative approved total (all uses, before any residential-only split)",
        )
    if proposed.state == FACT_RESOLVED:
        return OperativeFact(
            fact="all_use_total_units", state=FACT_RESOLVED, value=proposed.value,
            source=proposed.source, confidence=proposed.confidence,
            reason="operative proposed total (all uses, before any residential-only split)",
        )
    return OperativeFact(
        fact="all_use_total_units", state=FACT_NOT_DETERMINED,
        reason="no operative approved or proposed total to report",
    )


def _has_specialist_component(resolved: list[ResolvedApplication], operative_source_id: int | None) -> bool:
    """Positive evidence, from EXISTING extraction only, that the operative
    scheme mixes general residential with specialist accommodation - i.e.
    the operative application's own SchemeIntelligence names a
    specialist_housing_type, or its proposal text (already stored) names a
    care/extra-care/supported-living/nursing component alongside dwellings.
    No new parsing - a plain membership check against text the platform
    already holds."""
    specialist_terms = ("care home", "extra care", "extra-care", "nursing home", "supported living",
                        "assisted living", "retirement living", "close care", "care beds", "care apartments",
                        "residential institution", "c2 use", "use class c2")
    for r in resolved:
        if operative_source_id is not None and r.id != operative_source_id:
            continue
        si = r.scheme
        if si is not None and si.specialist_housing_type:
            return True
        if any(t in (r.application.proposal or "").lower() for t in specialist_terms):
            return True
    return False


def _resolve_residential_only(
    resolved: list[ResolvedApplication], approved: OperativeFact, proposed: OperativeFact
) -> OperativeFact:
    """SAFEGUARD - residential-only quantum is NOT a new inference.

    Resolve a residential-only figure ONLY where existing evidence already
    supports a deterministic distinction:
      - the operative source has NO specialist component evidence at all
        -> its total IS the residential-only figure; OR
      - the operative source's SchemeIntelligence carries an explicit
        private_units_final AND affordable_units_final whose sum is the
        general-residential total, with a specialist type recorded
        separately -> not attempted in V1 (the platform does not currently
        extract a clean specialist unit count to subtract), so this path
        returns not_determined.
    Otherwise: not_determined, and the wider all-use figure is preserved
    by _resolve_all_use_total. NEVER a derived/parsed split.
    """
    operative = approved if approved.state == FACT_RESOLVED else proposed
    if operative.state != FACT_RESOLVED:
        return OperativeFact(
            fact="residential_only_units", state=FACT_NOT_DETERMINED,
            reason="no operative total to assess",
        )
    source_id = operative.source.application_id if operative.source else None
    if _has_specialist_component(resolved, source_id):
        return OperativeFact(
            fact="residential_only_units", state=FACT_NOT_DETERMINED,
            reason="the operative scheme includes specialist accommodation (care / extra-care / supported living) "
                   "and the existing evidence does not deterministically separate general residential dwellings "
                   "from it - the wider all-use figure is preserved instead; no residential-only value is inferred",
        )
    return OperativeFact(
        fact="residential_only_units", state=FACT_RESOLVED, value=operative.value,
        source=operative.source, confidence=operative.confidence,
        reason="no specialist-accommodation component evidenced for the operative scheme - the operative total is "
               "entirely general residential",
    )


def _resolve_unit_mix(resolved: list[ResolvedApplication], lead: OperativeFact) -> OperativeFact:
    """House/apartment/specialist/other-use mix - read as one coherent
    record from the lead operative application's own SchemeIntelligence
    (never assembled across applications). Reserved-matters detail for a
    phase would refine this, but V1 reports the whole-site operative
    application's typology; a phase-level mix is a 2B-2 concern."""
    if lead.state != FACT_RESOLVED or lead.source is None:
        return OperativeFact(fact="unit_mix", state=FACT_NOT_DETERMINED, reason="no operative application")
    rs = next((r for r in resolved if r.id == lead.source.application_id), None)
    si = rs.scheme if rs else None
    if si is None:
        return OperativeFact(
            fact="unit_mix", state=FACT_NOT_DETERMINED,
            reason=f"operative application {lead.value} has no extracted scheme intelligence",
        )
    parts = []
    if si.housing_typology:
        parts.append(si.housing_typology)
    if si.specialist_housing_type:
        parts.append(f"specialist: {si.specialist_housing_type}")
    if si.development_type:
        parts.append(si.development_type)
    if not parts:
        return OperativeFact(
            fact="unit_mix", state=FACT_NOT_DETERMINED,
            reason=f"no housing typology / specialist type extracted for operative application {lead.value}",
        )
    return OperativeFact(
        fact="unit_mix", state=FACT_RESOLVED, value="; ".join(parts),
        source=_position("unit_mix", rs, "; ".join(parts)), confidence="medium",
        reason=f"read as one coherent record from operative application {lead.value}",
    )


# --- Public entry point ------------------------------------------------


def reconcile_scheme(applications: list[Application]) -> SchemeReconciliation:
    """Deterministic, computed, non-persisted reconciliation of one
    consolidated Site's applications into fact-level operative positions.

    `applications` is a Site's linked applications (the caller's existing
    list - e.g. site.applications). Callers must have the .scheme_
    intelligence relationship available, exactly as aggregate_scheme_
    fields / affordable_housing_scope already require."""
    resolved = resolve_applications(list(applications))

    lead = _resolve_lead_application(resolved)
    status = _resolve_planning_status(resolved)
    permission = _resolve_operative_permission(resolved)
    approved, superseded = _resolve_approved_units(resolved)
    proposed = _resolve_proposed_units(resolved)
    all_use = _resolve_all_use_total(resolved, approved, proposed)
    residential_only = _resolve_residential_only(resolved, approved, proposed)
    unit_mix = _resolve_unit_mix(resolved, lead)

    # Affordable housing: reuse the existing scope/authority reconciliation
    # UNCHANGED, but only over applications a substantive/S73 role permits
    # to speak to it - a non-substantive filing's affordable_*_final = 0
    # must never enter the pool (the Site 519 / Burnage defect). S73 is
    # included: affordable_housing_scope's own _has_no_independent_
    # affordable_position guard drops it if it carries no AH evidence.
    ah_eligible = [
        r.application for r in resolved
        if r.is_substantive or r.role == ROLE_S73_VARIATION
    ]
    affordable = compute_affordable_housing_scope_summary(ah_eligible)

    scope_note = _scope_note(resolved)

    return SchemeReconciliation(
        resolved_applications=tuple(resolved),
        lead_application=lead,
        operative_planning_status=status,
        operative_permission=permission,
        residential=ResidentialQuantum(
            approved=approved, proposed=proposed, residential_only=residential_only,
            all_use_total=all_use, superseded=superseded,
        ),
        unit_mix=unit_mix,
        affordable_housing=affordable,
        scope_note=scope_note,
    )


def _scope_note(resolved: list[ResolvedApplication]) -> str:
    named = sorted({r.scope_label for r in resolved if r.scope_type in (SCOPE_PHASE, SCOPE_PLOT)})
    if not named:
        return "single-scope scheme (no distinct phases/plots evidenced)"
    return "multi-scope scheme; distinct scopes: " + ", ".join(named)
