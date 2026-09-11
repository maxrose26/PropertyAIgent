"""Gate 2B-1/2B-2A - Trusted Operative Planning Facts.

Answers exactly one question, deliberately separate from every other
question this codebase already answers about a scheme:

    "Within an already-consolidated Site, WHICH application / phase /
    proposal version is ELIGIBLE to control each acquisition-relevant
    scheme fact - and where the evidence does not support a definitive
    choice, say so rather than picking one."

Public entry point: build_operative_planning_facts(applications) ->
OperativePlanningFacts. (Gate 2B-2A rename - see "Naming" below.)

This replaces, at the scheme-fact boundary, the generic selection done
today by:
  - app.ui.common.pick_representative_application - "most complete
    extraction, then most recently received" (no awareness of application
    type, role, decided state, or supersession), and
  - app.ui.common.aggregate_scheme_fields - first-non-null value per
    field, scanning in that same order.
Both remain available and unchanged for their other callers (the
opportunity universe / fingerprints, buyer matching, allocation coverage -
Gate 2B-2A deliberately does NOT migrate these, see docs/PRODUCT_ROADMAP.md
Gate 2B-2A "explicitly deferred consumers"); this module is a
deterministic layer consulted where scheme facts are presented to a user
(app.reporting.site_profile, and Gate 2B-2A's Stage A/B consumers).

Deliberately NOT an extraction gate:
  - adds no scraper, no NLP heuristic, no AI pass, no new regex-for-
    meaning. Every input is evidence THIS platform already extracted.
  - reuses, unmodified: app.scrapers.unit_filter.classify_application_
    category / is_administrative_application_type (application typing),
    app.pipeline.material_change.classify_planning_state (planning-state
    vocabulary), app.pipeline.phase_tracking.group_applications_by_
    operative_scope (phase/material-parcel scope - Gate 2B-2A, see
    "Phase vs plot" below), app.reporting.affordable_housing_scope.
    compute_affordable_housing_scope_summary (affordable-housing scope/
    authority reconciliation, now decided-state-aware - Gate 2B-2A
    Section 16).

Deliberately NOT persisted: everything here is computed fresh on every
call, exactly like affordable_housing_scope.py's own throwaway objects and
aggregate_scheme_fields's own `merged` dict. No schema change. No Scheme/
OperativeScheme table - Site remains the sole persisted identity anchor
(Gate 2B-2 architecture investigation, Section E: a Scheme's boundaries
are not independently evidenced by source data, so none is fabricated
here). Request/run-level memoisation of a call to this function is a
legitimate performance optimisation for a caller to add; this module
itself caches nothing.

Naming (Gate 2B-2A Section 4): app.extraction.reconcile.reconcile_scheme
is a DIFFERENT function - intra-application reconciliation (merging one
application's own regex/LLM/portal signals into SchemeIntelligence.
*_final). This module's public entry point is deliberately NOT also named
reconcile_scheme (the Gate 2B-1 name), to remove that collision -
build_operative_planning_facts is the cross-application, fact-level
reconciliation this module has always done.

CONSENTED vs ACTIVE (Gate 2B-2A Sections 5-7): the contract never
collapses "current consented position" and "current active planning
position(s)" into one "current scheme". The consented position is
computed independently and is None-shaped (every field individually
not_determined) when nothing is granted - never manufactured from a
pending or ancillary application. Active positions are a TUPLE - zero,
one, or several - one per distinct scope carrying live substantive
planning activity. "Latest application wins" is never replaced with
"latest ACTIVE application wins" globally; the previous "single most
recent live application" answer only exists as one active position among
possibly several, or as a tie-break WITHIN one already-identified scope.

Phase vs plot (Gate 2B-2A Sections 9-14): a WHOLE_SITE or PHASE scope may
legitimately be a peer acquisition-level operative scope. An individual
DWELLING PLOT normally must not. See app.pipeline.phase_tracking.
group_applications_by_operative_scope / is_material_development_parcel
for the deterministic rule (a named "plot" group is a peer scope only if
a role-eligible, single-plot-labelled application in that group
independently states its own qualifying-scale unit count - never by the
plot token's own shape, which real production data confirms cannot
reliably distinguish an individual dwelling from a development parcel).

Relationship confidence (Gate 2B-2A Section 15, "essential now"): every
resolved fact's provenance (FactPosition) carries the source
Application's own site_link_method/site_link_confidence, translated to a
level (high / review_required / unknown) - no new numeric score is
invented; `suggested_fuzzy` links are marked review_required, never
silently equivalent to an exact-address or parent-reference link.

Freshness (Gate 2B-2A Section 18): every resolved fact's provenance also
carries the source Application's own status_verified_at (Gate 2B-0A) and
an explicit independently_verified flag. last_seen_at is NEVER read here
or treated as freshness - see app.pipeline.status_verification's own
module docstring for why (last_seen_at advances on ANY unrelated ORM
write, never a proof of a genuine portal re-check).

Safeguards enforced here (Product Owner, Gate 2B-1 final approval,
carried into Gate 2B-2A unchanged):
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
from app.pipeline.material_change import DECIDED_GRANTED, DECIDED_RECOMMENDATION_ONLY, DECIDED_REFUSED
from app.pipeline.material_change import DECIDED_UNDETERMINED, DECIDED_WITHDRAWN
from app.pipeline.material_change import resolve_decided_state as _resolve_decided_state_from_fields
from app.pipeline.lapse_tracking import DECISION_STATUS_LABELS, parse_portal_date
from app.pipeline.phase_tracking import UNPHASED_LABEL, group_applications_by_operative_scope
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
# DECIDED_* constants and the resolver now live in app.pipeline.
# material_change (Gate 2B-2A) - shared, unmodified, with app.reporting.
# affordable_housing_scope's own decided-state-aware AH partition, rather
# than duplicated here.

# --- Fact-resolution states -------------------------------------------
FACT_RESOLVED = "resolved"
FACT_NOT_DETERMINED = "not_determined"
FACT_CONFLICT = "conflict"

# --- Scope (reuses affordable_housing_scope's vocabulary) --------------
SCOPE_WHOLE_SITE = "whole_site"
SCOPE_UNCLEAR = "unclear"
SCOPE_PHASE = "phase"
# A "plot" scope here is ALWAYS a confirmed material development parcel
# (Gate 2B-2A) - group_applications_by_operative_scope has already folded
# every individual-dwelling-plot grouping into whole_site/unclear before
# this module ever sees it. Kept as "plot" (not renamed to e.g.
# "development_parcel") to match app.reporting.affordable_housing_scope's
# existing, tested public constant of the same name - see that module's
# own Gate 2B-2A docstring update for the identical reasoning.
SCOPE_PLOT = "plot"

# --- Relationship confidence (Gate 2B-2A Section 15, "essential now") ----
# Reuses Application.site_link_method/site_link_confidence UNCHANGED - no
# new numeric score is invented. `suggested_fuzzy` (a human-reviewable,
# non-deterministic address-similarity match) is marked review_required,
# never silently equivalent to exact_address/parent_reference/created
# (all deterministic, evidence-driven links). An application with no
# site_link_method recorded at all (should not normally occur, but legacy
# rows or test fixtures may lack it) is UNKNOWN, never assumed high.
RELATIONSHIP_HIGH = "high"
RELATIONSHIP_REVIEW_REQUIRED = "review_required"
RELATIONSHIP_UNKNOWN = "unknown"

_HIGH_CONFIDENCE_LINK_METHODS = frozenset({"exact_address", "parent_reference", "created"})


def resolve_relationship_confidence(app: Application) -> tuple[str, str | None, float | None]:
    """(level, method, numeric_confidence). `numeric_confidence` is only
    ever meaningful for suggested_fuzzy (Application.site_link_confidence's
    own documented scope) - carried through unchanged, never fabricated
    for a deterministic link method."""
    method = app.site_link_method
    if method in _HIGH_CONFIDENCE_LINK_METHODS:
        return RELATIONSHIP_HIGH, method, None
    if method == "suggested_fuzzy":
        return RELATIONSHIP_REVIEW_REQUIRED, method, app.site_link_confidence
    return RELATIONSHIP_UNKNOWN, method, None


def _proposal_norm(app: Application) -> str:
    return f"{app.proposal or ''} {app.application_type or ''}".lower()


# EIA screening / scoping recognition (Gate 2B-1 Defect 1 remediation).
# Deterministic only - explicit screening/scoping REQUEST/OPINION wording
# (never the bare word "screening", which also appears in unrelated
# condition-discharge filings such as "Television Reception Screening" /
# "Window Screening"), plus the formal screening/scoping DECISION values a
# substantive application never receives. Every phrase/value below is
# confirmed present in production data. Not a new taxonomy, no inference,
# no numeric parsing - it completes resolve_planning_role's existing EIA
# recognition for phrasing variants (e.g. "Screening Request",
# "EIA Not Required") the portal's own opinion-only classifier misses.
_EIA_SCOPING_WORDING = (
    "scoping opinion", "scoping request", "eia scoping",
    "environmental impact assessment scoping", "request for a scoping opinion",
    "request for scoping opinion", "request for a scoping",
)
_EIA_SCREENING_WORDING = (
    "screening opinion", "screening request", "eia screening",
    "environmental impact assessment screening", "request for a screening opinion",
    "request for screening opinion", "request for a screening",
)
_EIA_SCOPING_DECISIONS = ("scoping opinion issued", "scoping opinion")
_EIA_SCREENING_DECISIONS = (
    "eia not required", "eia required",
    "environmental impact assessment not required", "environmental impact assessment required",
    "screening opinion issued", "environmental statement not required",
    "environmental assessment not required",
)


def _eia_role(app: Application) -> str | None:
    """ROLE_EIA_SCOPING / ROLE_EIA_SCREENING / None. Scoping is checked
    first (its wording is the more specific of the two); an application
    mentioning both is treated as scoping - it makes no difference to the
    non-substantive guardrail, both are barred from substantive facts."""
    text = _proposal_norm(app)
    decision = (app.decision or "").strip().lower()
    if any(w in text for w in _EIA_SCOPING_WORDING) or decision in _EIA_SCOPING_DECISIONS:
        return ROLE_EIA_SCOPING
    if any(w in text for w in _EIA_SCREENING_WORDING) or decision in _EIA_SCREENING_DECISIONS:
        return ROLE_EIA_SCREENING
    return None


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

    # Cross-boundary statutory consultation response (Gate 2B-2B.1 Section
    # 22, Pinfold/Edenfield production defect) - checked before every other
    # branch, same reasoning as the EIA check immediately below: a record
    # of ANOTHER authority's Article 18 (Town and Country Planning
    # (Development Management Procedure) Order) consultation reply must
    # never fall through to `full`/`outline` on its own residential
    # wording (confirmed real case: reference 71149, proposal text "Article
    # 18 consultation from Rossendale Borough Council (2023/0396); Full
    # application for residential development comprising no. 50 units...",
    # decision "Raise No Objection" - a neighbouring authority's own
    # consultee response, not the determining authority's substantive
    # decision on its own application). Reuses the existing
    # ROLE_EXTERNAL_CONSULTATION role (already in NON_SUBSTANTIVE_ROLES,
    # already excluded from consented/active resolution and AH
    # reconciliation) rather than inventing a new one - deliberately a
    # narrow, literal phrase match on the specific statutory mechanism
    # name, not a speculative rewrite of the category classifier.
    if "article 18 consultation" in text:
        return ROLE_EXTERNAL_CONSULTATION

    # EIA screening vs scoping - distinct roles (scoping is a later,
    # more detailed pre-application step, but neither is ever substantive).
    # Checked before every other branch: an EIA screening/scoping request
    # must never fall through to `full`/`outline` on its residential
    # wording (Gate 2B-1 Defect 1 - Pennington's Stables, DC/091435:
    # "... Regulations 2017 Screening Request: Residential development of
    # up to 68 dwellings", decision "EIA Not Required").
    eia = _eia_role(app)
    if eia is not None:
        return eia
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
    """One of the DECIDED_* constants (app.pipeline.material_change) -
    thin Application-shaped wrapper kept here for this module's own
    call sites/tests; the classification itself lives in exactly one
    place (material_change.resolve_decided_state)."""
    return _resolve_decided_state_from_fields(app.decision, app.status)


@dataclass(frozen=True)
class ResolvedApplication:
    """One application, with its resolved planning role, decided state and
    phase scope - the unit every downstream eligibility/ranking rule
    operates on. Computed once per build_operative_planning_facts() call."""

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

    @property
    def relationship(self) -> tuple[str, str | None, float | None]:
        return resolve_relationship_confidence(self.application)


@dataclass(frozen=True)
class FactPosition:
    """One application's stated value for one scheme fact, with the
    provenance needed to explain (or contest) the selection - including,
    since Gate 2B-2A, the three explicitly distinct trust dimensions:
    evidence confidence (the OperativeFact's own `confidence`), evidence
    freshness (`status_verified_at`/`independently_verified` here), and
    relationship confidence (`relationship_level`/`relationship_method`
    here) - never combined into one score (Section 18)."""

    value: object
    application_id: int
    application_reference: str
    planning_role: str
    decided_state: str
    scope_type: str
    scope_label: str
    decision_date: dt.date | None
    # Evidence freshness (Section 18) - status_verified_at is the ONLY
    # signal treated as "independently freshness-verified" (Gate 2B-0A).
    # last_seen_at is never read here and never substituted - a fact whose
    # source has no status_verified_at is honestly marked unverified,
    # never silently presented as "checked".
    status_verified_at: dt.datetime | None
    independently_verified: bool
    # Relationship confidence (Section 15) - reused from Application.
    # site_link_method/site_link_confidence, never a new numeric score.
    relationship_level: str
    relationship_method: str | None


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
class ConsentedPosition:
    """Gate 2B-2A - the CURRENT CONSENTED POSITION, kept structurally
    separate from any active proposal (Sections 5-6). Never manufactured
    from a pending or ancillary application - every field is independently
    an OperativeFact, so a granted permission with no extracted unit
    figure still resolves `reference`/`planning_status` while
    `approved_units` alone reads not_determined; nothing here is
    all-or-nothing. When NOTHING is granted, every field reads
    not_determined with its own reason - there is no separate top-level
    "consented position exists" flag to fall out of sync with the facts
    themselves."""

    reference: OperativeFact
    planning_status: OperativeFact
    approved_units: OperativeFact
    residential_only_units: OperativeFact
    all_use_total_units: OperativeFact
    unit_mix: OperativeFact
    superseded_units: tuple[FactPosition, ...] = ()

    @property
    def exists(self) -> bool:
        return self.reference.state == FACT_RESOLVED


@dataclass(frozen=True)
class ActivePosition:
    """Gate 2B-2A - ONE of possibly SEVERAL current active planning
    positions (Section 7). One ActivePosition per distinct scope carrying
    live (undetermined / recommendation-only) substantive planning
    activity - a Site may legitimately have zero, one, or several of
    these coexisting (an extant permission plus a fresh resubmission; two
    independent live applications on different phases; a competing
    proposal). "Latest application wins" is never applied ACROSS scopes to
    collapse these into one; within one scope, recency is used only as a
    tie-break between multiple filings that already share that scope."""

    scope_type: str
    scope_label: str
    reference: OperativeFact
    planning_status: OperativeFact
    proposed_units: OperativeFact
    residential_only_units: OperativeFact
    all_use_total_units: OperativeFact
    unit_mix: OperativeFact


@dataclass(frozen=True)
class OperativePlanningFacts:
    """Gate 2B-2A public contract - the trusted, computed, non-persisted
    planning-fact read model for one Site (see build_operative_planning_
    facts). CURRENT CONSENTED POSITION and CURRENT ACTIVE PLANNING
    POSITION(S) are always structurally separate (Sections 5-7);
    affordable housing is exposed once, scope-labelled, decided-state-
    aware (Section 16), cross-referenced by scope_label to whichever
    consented/active position shares that scope - never duplicated or
    rebuilt per position."""

    resolved_applications: tuple[ResolvedApplication, ...]
    consented_position: ConsentedPosition
    active_positions: tuple[ActivePosition, ...]
    affordable_housing: AffordableHousingSummary
    scope_note: str


# --- Ranking helpers --------------------------------------------------


def _by_grant_then_recency(rs: ResolvedApplication) -> tuple:
    """Sort key: granted-with-a-date first, then latest decision date,
    then latest received date (RECENCY IS A TIE-BREAK ONLY - never the
    primary signal; that is the defect Gate 2B-1 exists to fix)."""
    d = rs.decision_date or dt.date.min
    return (rs.decided_state == DECIDED_GRANTED, d, rs.received, rs.id)


def _position(rs: ResolvedApplication, value: object) -> FactPosition:
    level, method, numeric = rs.relationship
    app = rs.application
    return FactPosition(
        value=value, application_id=rs.id, application_reference=rs.reference,
        planning_role=rs.role, decided_state=rs.decided_state,
        scope_type=rs.scope_type, scope_label=rs.scope_label,
        decision_date=rs.decision_date,
        status_verified_at=app.status_verified_at,
        independently_verified=app.status_verified_at is not None,
        relationship_level=level, relationship_method=method,
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


# --- Fact resolvers - CONSENTED position -------------------------------


def _resolve_reference_and_status(resolved: list[ResolvedApplication]) -> tuple[OperativeFact, OperativeFact]:
    """Consented reference + planning status together (Gate 2B-2A) - a
    granted substantive application, latest by decision date.

    A permission is never manufactured from a pending or ancillary
    application (Section 6). Three genuinely different "nothing granted"
    shapes are distinguished, never conflated:
      - a live substantive application exists (handled separately as an
        ACTIVE position, never here) -> both reference and status stay
        not_determined for the CONSENTED position specifically;
      - every substantive application that exists is refused/withdrawn -
        there is no consented PERMISSION, but the scheme's terminal
        status IS genuinely determinable from that evidence, so
        `planning_status` (and its source reference) resolve to
        "Refused"/"Withdrawn" - this is not a fabricated permission, it
        is an honestly negative, evidenced outcome;
      - no substantive application exists at all - both stay
        not_determined."""
    substantive = [r for r in resolved if r.is_substantive]
    granted = [r for r in substantive if r.decided_state == DECIDED_GRANTED]
    if granted:
        lead = max(granted, key=_by_grant_then_recency)
        superseded = [g for g in granted if g.id != lead.id]
        reason = f"latest granted substantive application ({lead.role})"
        if superseded:
            reason += f"; supersedes {', '.join(g.reference for g in superseded)}"
        ref_fact = OperativeFact(
            fact="consented_reference", state=FACT_RESOLVED, value=lead.reference,
            source=_position(lead, lead.reference), confidence="high", reason=reason,
        )
        status_fact = OperativeFact(
            fact="consented_planning_status", state=FACT_RESOLVED, value="Permission granted",
            source=_position(lead, "Permission granted"), confidence="high",
            reason=f"granted substantive application {lead.reference} ({lead.role})"
                   + (f", decision {lead.application.decision_issued_date}" if lead.application.decision_issued_date else ""),
        )
        return ref_fact, status_fact

    live = [r for r in substantive if r.decided_state in (DECIDED_RECOMMENDATION_ONLY, DECIDED_UNDETERMINED)]
    if not live and substantive:
        # Every substantive application is refused/withdrawn - a genuine,
        # evidenced terminal outcome, not a fabricated permission.
        lead = max(substantive, key=lambda r: (r.decision_date or dt.date.min, r.received, r.id))
        label = "Refused" if lead.decided_state == DECIDED_REFUSED else "Withdrawn"
        return (
            OperativeFact(
                fact="consented_reference", state=FACT_NOT_DETERMINED,
                reason=f"no permission was ever granted - the last substantive application ({lead.reference}) was {label.lower()}",
            ),
            OperativeFact(
                fact="consented_planning_status", state=FACT_RESOLVED, value=label,
                source=_position(lead, label), confidence="medium",
                reason=f"all substantive applications refused/withdrawn; latest is {lead.reference}",
            ),
        )

    reason = (
        "a substantive application is live but not yet granted - see the active planning position(s)"
        if live else
        "no substantive planning application (outline/full/hybrid/reserved-matters) linked to this site"
    )
    return (
        OperativeFact(fact="consented_reference", state=FACT_NOT_DETERMINED, reason=reason),
        OperativeFact(fact="consented_planning_status", state=FACT_NOT_DETERMINED, reason=reason),
    )


def _resolve_approved_units(resolved: list[ResolvedApplication]) -> tuple[OperativeFact, tuple[FactPosition, ...]]:
    """Approved residential units, where consent exists. Eligible sources:
    granted substantive applications, plus an S73/variation ONLY where it
    demonstrably addresses units (safeguard). Returns (operative fact,
    superseded positions)."""
    eligible = [
        r for r in resolved
        if (r.is_substantive and r.decided_state == DECIDED_GRANTED and _scheme_total_units(r) is not None)
        or _s73_addresses_units(r)
    ]
    if not eligible:
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
        return (r.role == ROLE_S73_VARIATION, r.decision_date or dt.date.min, r.received, r.id)

    ranked = sorted(eligible, key=rank, reverse=True)
    operative = ranked[0]
    op_value = _scheme_total_units(operative)

    same_scope_top = [
        r for r in ranked
        if r.scope_type == operative.scope_type and r.scope_label == operative.scope_label
        and (r.decision_date or dt.date.min) == (operative.decision_date or dt.date.min)
        and (r.role == ROLE_S73_VARIATION) == (operative.role == ROLE_S73_VARIATION)
    ]
    distinct = {_scheme_total_units(r) for r in same_scope_top}
    if len(distinct) > 1:
        positions = tuple(_position(r, _scheme_total_units(r)) for r in same_scope_top)
        return (
            OperativeFact(
                fact="approved_residential_units", state=FACT_CONFLICT, conflicts=positions,
                reason="two equally-authoritative applications state different approved unit counts for the same "
                       "scope and neither supersedes the other - manual verification required",
            ),
            (),
        )

    superseded = tuple(
        _position(r, _scheme_total_units(r))
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
            source=_position(operative, op_value), confidence="high", reason=reason,
        ),
        superseded,
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
    resolved: list[ResolvedApplication], operative: OperativeFact,
) -> OperativeFact:
    """SAFEGUARD - residential-only quantum is NOT a new inference. See
    module docstring."""
    if operative.state != FACT_RESOLVED:
        return OperativeFact(fact="residential_only_units", state=FACT_NOT_DETERMINED, reason="no operative total to assess")
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
    record from the lead application's own SchemeIntelligence (never
    assembled across applications)."""
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
        source=_position(rs, "; ".join(parts)), confidence="medium",
        reason=f"read as one coherent record from operative application {lead.value}",
    )


def _resolve_all_use_total(approved_or_proposed: OperativeFact, basis: str) -> OperativeFact:
    """The wider / all-use total to preserve alongside a residential-only
    figure - simply the operative figure (approved or proposed, per
    caller), labelled as all-use because this module does not attempt to
    net out specialist accommodation (see residential-only)."""
    if approved_or_proposed.state != FACT_RESOLVED:
        return OperativeFact(fact="all_use_total_units", state=FACT_NOT_DETERMINED, reason=f"no operative {basis} total to report")
    return OperativeFact(
        fact="all_use_total_units", state=FACT_RESOLVED, value=approved_or_proposed.value,
        source=approved_or_proposed.source, confidence=approved_or_proposed.confidence,
        reason=f"operative {basis} total (all uses, before any residential-only split)",
    )


def _resolve_consented_position(resolved: list[ResolvedApplication]) -> ConsentedPosition:
    reference, status = _resolve_reference_and_status(resolved)
    approved, superseded = _resolve_approved_units(resolved)
    all_use = _resolve_all_use_total(approved, "approved")
    residential_only = _resolve_residential_only(resolved, approved)
    unit_mix = _resolve_unit_mix(resolved, reference)
    return ConsentedPosition(
        reference=reference, planning_status=status, approved_units=approved,
        residential_only_units=residential_only, all_use_total_units=all_use,
        unit_mix=unit_mix, superseded_units=superseded,
    )


# --- Fact resolvers - ACTIVE position(s) --------------------------------


def _build_active_position(group: list[ResolvedApplication], scope_type: str, scope_label: str) -> ActivePosition:
    """ONE active position for one scope, from the live substantive
    application(s) sharing that scope. Recency is used only as a
    tie-break WITHIN this already-identified scope - never across scopes
    (see ActivePosition's own docstring)."""
    with_fig = [r for r in group if _scheme_total_units(r) is not None or _portal_estimated_units(r) is not None]
    pool = with_fig or group
    lead = max(pool, key=lambda r: (r.received, r.id))

    ref_fact = OperativeFact(
        fact="active_reference", state=FACT_RESOLVED, value=lead.reference,
        source=_position(lead, lead.reference), confidence="high",
        reason=f"live substantive application in scope {scope_label}",
    )
    status_label = "Awaiting decision (officer recommendation made)" if lead.decided_state == DECIDED_RECOMMENDATION_ONLY else "Awaiting decision"
    status_fact = OperativeFact(
        fact="active_planning_status", state=FACT_RESOLVED, value=status_label,
        source=_position(lead, status_label), confidence="medium",
        reason=f"substantive application {lead.reference} pending in scope {scope_label}"
               + (" - recommendation is never treated as permission" if lead.decided_state == DECIDED_RECOMMENDATION_ONLY else ""),
    )

    if lead not in with_fig:
        proposed = OperativeFact(
            fact="proposed_residential_units", state=FACT_NOT_DETERMINED,
            reason=f"a substantive application is live in scope {scope_label} but no residential unit figure has "
                   f"been extracted or estimated for it yet",
        )
    else:
        extracted = _scheme_total_units(lead)
        value = extracted if extracted is not None else _portal_estimated_units(lead)
        proposed = OperativeFact(
            fact="proposed_residential_units", state=FACT_RESOLVED, value=value,
            source=_position(lead, value), confidence="high" if extracted is not None else "low",
            reason=(f"most recent live substantive application in scope {scope_label}: {lead.reference}"
                    + ("" if extracted is not None else " (portal-listing estimate only - not document-verified)")),
        )

    all_use = _resolve_all_use_total(proposed, "proposed")
    residential_only = _resolve_residential_only([lead], proposed)
    unit_mix = _resolve_unit_mix([lead], ref_fact)

    return ActivePosition(
        scope_type=scope_type, scope_label=scope_label, reference=ref_fact, planning_status=status_fact,
        proposed_units=proposed, residential_only_units=residential_only, all_use_total_units=all_use,
        unit_mix=unit_mix,
    )


def _resolve_active_positions(resolved: list[ResolvedApplication]) -> tuple[ActivePosition, ...]:
    """Gate 2B-2A Section 7 - zero, one, or several simultaneous active
    substantive planning proposals, one per distinct scope. Never reduced
    to a single "most recent" answer across scopes."""
    live = [r for r in resolved if r.is_substantive and r.decided_state in (DECIDED_UNDETERMINED, DECIDED_RECOMMENDATION_ONLY)]
    if not live:
        return ()
    by_scope: dict[tuple[str, str], list[ResolvedApplication]] = {}
    for r in live:
        by_scope.setdefault((r.scope_type, r.scope_label), []).append(r)
    return tuple(
        _build_active_position(group, stype, slabel)
        for (stype, slabel), group in sorted(by_scope.items(), key=lambda kv: kv[0][1])
    )


# --- Public entry point ------------------------------------------------


def build_operative_planning_facts(applications: list[Application]) -> OperativePlanningFacts:
    """Deterministic, computed, non-persisted reconciliation of one
    consolidated Site's applications into the trusted operative planning
    facts contract (Gate 2B-2A). Formerly `reconcile_scheme` (Gate 2B-1) -
    see module docstring, "Naming".

    `applications` is a Site's linked applications - callers should pass
    the RAW `site.applications` relationship, not a display-filtered
    subset (a display filter can drop condition-discharge/S73 records
    this function specifically needs to see for the non-substantive
    guardrail and the S73 fact-specific safeguard - see
    app.reporting.site_profile's own note on this). Callers must have the
    .scheme_intelligence relationship available, exactly as aggregate_
    scheme_fields / affordable_housing_scope already require."""
    resolved = resolve_applications(list(applications))

    consented = _resolve_consented_position(resolved)
    active_positions = _resolve_active_positions(resolved)

    # Affordable housing: reuse the existing scope/authority reconciliation,
    # now decided-state-aware (Gate 2B-2A Section 16), over only the
    # applications a substantive/S73 role permits to speak to it - a
    # non-substantive filing's affordable_*_final = 0 must never enter the
    # pool (the Site 519 / Burnage defect). S73 is included:
    # affordable_housing_scope's own _has_no_independent_affordable_
    # position guard drops it if it carries no AH evidence.
    ah_eligible = [r.application for r in resolved if r.is_substantive or r.role == ROLE_S73_VARIATION]
    affordable = compute_affordable_housing_scope_summary(ah_eligible)

    scope_note = _scope_note(resolved)

    return OperativePlanningFacts(
        resolved_applications=tuple(resolved),
        consented_position=consented,
        active_positions=active_positions,
        affordable_housing=affordable,
        scope_note=scope_note,
    )


# --- Scope resolution ---------------------------------------------------


def _resolve_scopes(applications: list[Application]) -> dict[int, tuple[str, str]]:
    """{application_id: (scope_type, scope_label)}. Gate 2B-2A: uses
    app.pipeline.phase_tracking.group_applications_by_operative_scope,
    NOT the raw group_applications_by_phase - a named "plot" group only
    becomes its own peer scope here if it is a confirmed material
    development parcel (see that function's own docstring for the
    deterministic rule and the real production evidence behind it).
    Everything else about this resolution is unchanged from Gate 2B-1:
    an application naming several peer scopes at once is WHOLE_SITE (it
    spans them); an application naming none, on a site with no peer
    scopes at all, is UNCLEAR (no positive evidence of whole-site vs one
    unnamed part)."""
    groups = group_applications_by_operative_scope(applications)
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


def _scope_note(resolved: list[ResolvedApplication]) -> str:
    named = sorted({r.scope_label for r in resolved if r.scope_type in (SCOPE_PHASE, SCOPE_PLOT)})
    if not named:
        return "single-scope scheme (no distinct phases/material development parcels evidenced)"
    return "multi-scope scheme; distinct scopes: " + ", ".join(named)


# --- Gate 2B-2A pre-merge remediation - Explore discovery-surface facts --

# The SAME 4-key vocabulary app.pipeline.lapse_tracking.DECISION_STATUS_LABELS
# already defines for the natural-language search's structured "statuses"
# filter (app.search.query_parser) - reused, not duplicated, so a NL query
# for "granted"/"refused"/"withdrawn"/"awaiting decision" keeps matching the
# exact same machine values it always has. NOT_DETERMINED is the one
# genuinely new value: reconciliation ran and found no substantive
# consented or active position at all (e.g. an EIA-screening-only site) -
# distinct from "not_yet_decided", which now specifically means "a live
# substantive proposal exists and is pending", never "we don't know".
NOT_DETERMINED_DECISION_STATUS = "not_determined"
OPERATIVE_DECISION_STATUS_LABELS: dict[str, str] = {
    **DECISION_STATUS_LABELS,
    NOT_DETERMINED_DECISION_STATUS: "Not yet verified",
}


def resolve_canonical_decision_status(
    consented: ConsentedPosition, active_positions: tuple[ActivePosition, ...],
    reconciliation_ran: bool, fallback: str | None = None,
) -> str | None:
    """ONE of DECISION_STATUS_LABELS's own 4 keys (granted/refused/
    withdrawn/not_yet_decided), derived from the SAME reconciliation every
    other trusted fact already uses - never a second, independently-derived
    status taxonomy. Shared verbatim by app.reporting.site_profile's
    Decision Status tile and app.ui.pages.0_Explore's table/filter column,
    so the two surfaces can no longer disagree about a Site's status by
    construction (they call the same function with the same facts) - Gate
    2B-2A pre-merge remediation requirement 1/2.

    `fallback` (a caller-supplied legacy value) is used ONLY when
    reconciliation could not run at all (e.g. zero linked applications) -
    never when it ran and found nothing determinable, which returns None
    (every consumer already renders that as "Not yet verified"/omitted,
    same as any other not_determined fact; see
    OPERATIVE_DECISION_STATUS_LABELS/NOT_DETERMINED_DECISION_STATUS above
    for callers that want a concrete string key instead of None)."""
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


@dataclass(frozen=True)
class OperativeFilterFacts:
    """Gate 2B-2A pre-merge remediation - the trusted, machine-readable
    facts Explore's table/filters (and any future list-scale consumer)
    should search/sort/filter on, separate from the human-readable label a
    UI chooses to print (OPERATIVE_DECISION_STATUS_LABELS /
    format_operative_units_display below). Built from the SAME
    OperativePlanningFacts every other Gate 2B-2A surface already uses -
    never a second, independently-derived selection of "which application
    matters"."""

    decision_status: str  # one of OPERATIVE_DECISION_STATUS_LABELS's keys
    has_active_proposal: bool
    active_proposal_count: int
    units: int | None
    units_source: str | None  # "consented" | "active" | None
    units_kind: str | None  # "residential" | "all_use" | None
    units_is_estimated: bool
    units_not_determined: bool
    active_units: int | None
    active_units_kind: str | None  # "residential" | "all_use" | None
    # Gate 2B-2B.1 - the trusted, decided-state-aware affordable-housing
    # figures for this same consented/single-active resolution (never the
    # withdrawn/refused/technical-zero-tainted legacy aggregate_scheme_
    # fields merge that produced the Burnage 0%/Stockport Rugby leakage
    # defects). None/not-determined whenever no genuine consented or
    # single-active AH position was resolved - never a fabricated zero.
    affordable_units: int | None = None
    affordable_percentage: float | None = None
    affordable_source: str | None = None  # "consented" | "active" | None


def _resolve_units_from_units_facts(residential: OperativeFact, all_use: OperativeFact) -> tuple[int | None, str | None, bool]:
    """Prefers the residential-only quantum (Gate 2B-2A pre-merge
    remediation: "min/max unit filtering must use the trusted operative
    RESIDENTIAL quantum, not a raw representative-application total") -
    falls back to the all-use total ONLY when residential-only genuinely
    cannot be determined (case E/F: a mixed/specialist scheme where the
    existing Gate 2B-1 "no new inference" safeguard correctly withholds a
    residential-only figure) - never fabricates a residential split that
    isn't there. Returns (value, kind, is_estimated)."""
    if residential.state == FACT_RESOLVED:
        return residential.value, "residential", residential.confidence == "low"
    if all_use.state == FACT_RESOLVED:
        return all_use.value, "all_use", all_use.confidence == "low"
    return None, None, False


def resolve_operative_filter_facts(facts: OperativePlanningFacts) -> OperativeFilterFacts:
    """The single deterministic rule Explore's Total Units/Decision Status
    columns, min/max unit filters, and status filter all read from - see
    this module's own docstring cases A-F (Gate 2B-2A pre-merge
    remediation report, Section C):

    A/B. A resolvable quantum (consented, else - only when there is
         exactly ONE active substantive proposal - that proposal's own
         quantum) is used for filtering; residential-only preferred, all-
         use total as a flagged fallback (see _resolve_units_from_units_
         facts).
    C.   When a consent AND an active proposal both exist, the CONSENTED
         quantum remains the primary `units` value (it is the established,
         evidenced position) - the active proposal's own figure is never
         discarded, only carried separately as `active_units` /
         `has_active_proposal` / `active_proposal_count`, so a consumer can
         still see and act on it without a single-valued filter column
         being forced to pick a winner.
    D.   Multiple active substantive proposals with no consent -> `units`
         stays None/not_determined (no arbitrary "latest wins" or summed
         figure); `active_proposal_count` still reports how many exist.
    E/F. Residential-only NOT_DETERMINED but an all-use/mixed-use total IS
         resolved -> that all-use total is used, flagged `units_kind=
         "all_use"` rather than silently presented as a residential count.
    """
    consented = facts.consented_position
    active_positions = facts.active_positions
    reconciliation_ran = bool(facts.resolved_applications)

    decision_status = resolve_canonical_decision_status(consented, active_positions, reconciliation_ran)
    if decision_status is None:
        decision_status = NOT_DETERMINED_DECISION_STATUS

    units, units_kind, units_is_estimated = _resolve_units_from_units_facts(
        consented.residential_only_units, consented.all_use_total_units,
    )
    units_source: str | None = "consented" if units is not None else None
    if units is None and len(active_positions) == 1:
        units, units_kind, units_is_estimated = _resolve_units_from_units_facts(
            active_positions[0].residential_only_units, active_positions[0].all_use_total_units,
        )
        units_source = "active" if units is not None else None
    units_not_determined = bool(reconciliation_ran and units is None)

    active_units: int | None = None
    active_units_kind: str | None = None
    if len(active_positions) == 1:
        active_units, active_units_kind, _ = _resolve_units_from_units_facts(
            active_positions[0].residential_only_units, active_positions[0].all_use_total_units,
        )

    # Gate 2B-2B.1 - affordable housing, same consented-then-single-active
    # priority as units above. `facts.affordable_housing.historical`
    # (withdrawn/refused positions) is never read here, so that evidence
    # structurally cannot leak into Explore's current AH columns - this is
    # the fix for the confirmed Stockport Rugby Club (withdrawn AH shown
    # as current) and Burnage (an ancillary technical zero outranking the
    # real 13/19.7% consented position) production defects.
    ah = facts.affordable_housing
    affordable_units: int | None = None
    affordable_percentage: float | None = None
    affordable_source: str | None = None
    if ah.whole_site is not None:
        affordable_units, affordable_percentage, affordable_source = ah.whole_site.units, ah.whole_site.percentage, "consented"
    elif len(active_positions) == 1 and ah.active_whole_site is not None:
        affordable_units, affordable_percentage, affordable_source = ah.active_whole_site.units, ah.active_whole_site.percentage, "active"

    return OperativeFilterFacts(
        decision_status=decision_status,
        has_active_proposal=len(active_positions) >= 1,
        active_proposal_count=len(active_positions),
        affordable_units=affordable_units, affordable_percentage=affordable_percentage, affordable_source=affordable_source,
        units=units, units_source=units_source, units_kind=units_kind, units_is_estimated=units_is_estimated,
        units_not_determined=units_not_determined,
        active_units=active_units, active_units_kind=active_units_kind,
    )


def format_operative_decision_status_label(filter_facts: OperativeFilterFacts) -> str:
    """The human-facing label for OperativeFilterFacts.decision_status -
    kept separate from the canonical machine key it is derived from (Gate
    2B-2A pre-merge remediation: "separate CANONICAL MACHINE-READABLE
    PLANNING STATE from USER-FACING DISPLAY LABEL"). A single active
    proposal shows the same "Awaiting decision" wording the label map
    already gives every not_yet_decided site; several simultaneous active
    proposals say so explicitly, rather than the label silently implying
    there is only one - reused verbatim by every Explore surface (table,
    map tooltip, exported report) that shows a Site's decision status, so
    they can never print different words for the same trusted fact."""
    if filter_facts.decision_status == "not_yet_decided" and filter_facts.active_proposal_count > 1:
        return f"{filter_facts.active_proposal_count} active planning proposals"
    return OPERATIVE_DECISION_STATUS_LABELS[filter_facts.decision_status]


def format_operative_units_basis_label(filter_facts: OperativeFilterFacts) -> str | None:
    """Short provenance string for OperativeFilterFacts.units - "Residential
    - consented", "All-use - active proposal", etc. - so a reviewer can see
    WHY a number is what it is without opening the Site itself. None only
    when `units` is also None (nothing to attribute)."""
    if filter_facts.units is None:
        return None
    bits = []
    if filter_facts.units_kind:
        bits.append("Residential" if filter_facts.units_kind == "residential" else "All-use")
    if filter_facts.units_source:
        bits.append("consented" if filter_facts.units_source == "consented" else "active proposal")
    return " - ".join(bits) if bits else None
