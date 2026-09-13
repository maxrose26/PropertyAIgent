"""Buyer Mandate V2, Phase A (Buyer/Mandate Domain Separation) - the
persistence layer for Buyer identity and Buyer Mandates: default Workspace
bootstrap, seeding the four existing pilot templates as a Buyer + one
BuyerMandate each, converting between app.db.models.BuyerMandate (the
persistent, Buyer-owned row) and app.policy.buyer_profiles.
BuyerMandatePolicy (the pure dataclass app.policy.buyer_matching.
assess_buyer_fit actually consumes), the buyer-mandate matching
fingerprint, and the onboarding baseline scan.

Deliberately kept OUT of app.policy.buyer_profiles.py (a pure, DB-free
config module - UNCHANGED by this migration) and app.policy.buyer_matching
.py (pure matching, DB-free - also UNCHANGED except for the BuyerProfile ->
BuyerMandatePolicy rename). This is the only module that talks to the
database on the Buyer/BuyerMandate side; assess_buyer_fit itself never
sees a database row, only ever the same dataclass it always has.

PHASE A DOMAIN MIGRATION (this module's own history): every function here
used to operate on app.db.models.BuyerProfile, one indivisible row per
buyer/strategy. That row has been split into two: app.db.models.Buyer
(commercial identity: buyer_key, display_name, buyer_type) and
app.db.models.BuyerMandate (one persistent acquisition strategy belonging
to one Buyer: everything assess_buyer_fit actually reads, plus
primary_requirement/notes/status/provenance/fingerprint/onboarding state -
see BuyerMandate's own docstring for exactly why each field ended up
where it did). The legacy app.db.models.BuyerProfile table/class is
retained, UNCHANGED, read-only, purely for rollback safety - see its own
docstring. Nothing in this module writes to it any more.

migrate_buyer_profiles_to_mandates() is the one-time, idempotent backfill
that copies every legacy BuyerProfile row into an equivalent Buyer +
BuyerMandate pair (mandate_key="default") the first time this runs against
an already-populated database. Every OTHER function below (seeding,
onboarding, fingerprinting, the UI read path) operates on Buyer/
BuyerMandate exclusively and has no awareness of the legacy table at all -
this keeps the migration itself as the only place old and new
representations ever meet.

Read-path resilience (unchanged from Phase 0): every function here that
reads Buyer Mandates falls back to the in-memory app.policy.buyer_profiles
.BUYER_PROFILES/BUYER_PROFILE_ORDER templates whenever no persisted
Workspace/Buyer/BuyerMandate row exists yet - this is what keeps every
pre-existing test and the live UI working completely unchanged before an
operator has run scripts.bootstrap_acquisition_monitoring (see that
script's own docstring for why seeding is an explicit step, never a
page-load side effect). Once bootstrap has run, the persisted row (which
may since have been edited) takes over transparently.
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import select

from app.db.models import Buyer, BuyerMandate, Council, Workspace, utcnow
from app.policy.buyer_matching import INSUFFICIENT_EVIDENCE, NOT_SUITABLE, STRONG_FIT, assess_buyer_fit
from app.policy.buyer_profiles import (
    ACQUISITION_TYPES,
    BUYER_PROFILE_ORDER,
    BUYER_PROFILES,
    CONTROL_APPETITES,
    DEVELOPMENT_STATE_APPETITES,
    DEVELOPMENT_STATE_UNSPECIFIED,
    GEOGRAPHY_COUNCILS,
    GEOGRAPHY_SCOPES,
    GEOGRAPHY_UNSPECIFIED,
    BuyerMandatePolicy,
)
from app.reporting.opportunity_change import sync_opportunity_monitoring_state
from app.reporting.opportunity_universe import DEFAULT_STRATEGIC_LAND_PAGE_SIZE, build_current_opportunity_universe

DEFAULT_WORKSPACE_NAME = "Property AIgent Pilot"

# Every migrated/seeded buyer gets exactly one mandate under this key in
# Phase A - see BuyerMandate's own docstring. A future Phase B UI would
# introduce further mandate_key values (e.g. "gm_consented_50_100") under
# the same buyer; nothing in Phase A creates a second one.
DEFAULT_MANDATE_KEY = "default"


# --- Workspace ----------------------------------------------------------

def _find_default_workspace(session) -> Workspace | None:
    """Read-only - never creates anything. The single query every read-
    path function below uses; resolve_default_workspace (below) is the
    only function allowed to create one."""
    return session.execute(select(Workspace).order_by(Workspace.id.asc())).scalars().first()


def resolve_default_workspace(session) -> Workspace:
    """Idempotent get-or-create for the single default Workspace this
    still-single-user installation needs - mirrors app.db.models.Settings'
    own existing "one hand-maintained default row" precedent, never a
    second, novel singleton pattern. Only ever called from the explicit
    scripts.bootstrap_acquisition_monitoring step, never from an ordinary
    request/page-load path (same "migrations/seeding are not a page-load
    side effect" discipline as scripts.migrate_schema)."""
    workspace = _find_default_workspace(session)
    if workspace is not None:
        return workspace
    workspace = Workspace(name=DEFAULT_WORKSPACE_NAME, status="active")
    session.add(workspace)
    session.commit()
    return workspace


# --- Buyer Mandate fingerprint --------------------------------------------

def compute_buyer_mandate_fingerprint(policy: BuyerMandatePolicy) -> str:
    """sha256 over ONLY the fields app.policy.buyer_matching.assess_buyer_
    fit actually reads (unchanged rule from the original Gate 1 brief:
    "fingerprint ONLY fields that affect buyer matching/monitoring... do
    NOT include display-only metadata"). display_name/buyer_type/
    primary_requirement/notes/key are deliberately excluded - assess_
    buyer_fit never reads any of them, confirmed by inspection of that
    function.

    Phase A significance: every one of the excluded fields now lives
    partly on Buyer (display_name, buyer_type) and partly on BuyerMandate
    (primary_requirement, notes, key) - this fingerprint reads the
    BuyerMandatePolicy dataclass exactly as before, so a Buyer's own
    identity fields changing (which never even reach this dataclass's
    matching-relevant portion) cannot change this value, structurally,
    not merely by convention. See compute_buyer_mandate_fingerprint's own
    test coverage (tests/test_buyer_profile_persistence.py) for a direct
    proof of this.

    Buyer Mandate V2, Phase B1: geography/acquisition_types/development_
    state_appetite/control_appetite are now included, per the Phase B1
    brief's own explicit instruction ("these fields are matching-relevant
    and therefore should be included... even though B1 does not activate
    matching behaviour yet, establish correct fingerprint semantics now").
    Every set-like value is sorted before hashing (geography_councils,
    acquisition_types, control_appetite) so member ORDER can never affect
    the fingerprint - only membership can. Adding these fields changes
    every existing mandate's own fingerprint value once - see
    scripts.backfill_buyer_mandate_b1_defaults for how that one-time change
    is applied without triggering a wasted full opportunity-universe
    re-onboarding scan (B1 does not change assess_buyer_fit's own output at
    all, so re-scanning would recompute identical conclusions)."""
    fingerprint_source = {
        "target_unit_min": policy.target_unit_min,
        "target_unit_max": policy.target_unit_max,
        "scale_metric": policy.scale_metric,
        "accepted_planning_states": sorted(policy.accepted_planning_states),
        "treats_no_activity_as_positive": policy.treats_no_activity_as_positive,
        "large_allocation_is_self_qualifying": policy.large_allocation_is_self_qualifying,
        "specialist_development_is_exclusion": policy.specialist_development_is_exclusion,
        "wholly_affordable_is_exclusion": policy.wholly_affordable_is_exclusion,
        "below_minimum_scale_is_exclusion": policy.below_minimum_scale_is_exclusion,
        "geography_scope": policy.geography_scope,
        "geography_councils": sorted(policy.geography_councils),
        "acquisition_types": sorted(policy.acquisition_types),
        "development_state_appetite": policy.development_state_appetite,
        "control_appetite": sorted(policy.control_appetite),
    }
    canonical = json.dumps(fingerprint_source, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# Phase-A-era alias, kept for one release so any external/ad-hoc caller of
# the pre-split name does not break silently. New code should call
# compute_buyer_mandate_fingerprint directly.
compute_buyer_profile_fingerprint = compute_buyer_mandate_fingerprint


def _phase_a_only_fingerprint(policy: BuyerMandatePolicy) -> str:
    """Frozen replica of compute_buyer_mandate_fingerprint's field set AS
    IT EXISTED BEFORE Buyer Mandate V2 Phase B1 - used ONLY by
    migrate_buyer_profiles_to_mandates' own internal self-consistency
    check (does the field-by-field copy from a legacy BuyerProfile row
    reproduce the same Phase-A fields its own matching_fingerprint was
    computed over), since that legacy fingerprint was necessarily computed
    under the pre-B1 schema and can never be compared against the current,
    wider one. Never used to persist a mandate's own matching_fingerprint
    column - that is always the current, full compute_buyer_mandate_
    fingerprint value."""
    fingerprint_source = {
        "target_unit_min": policy.target_unit_min,
        "target_unit_max": policy.target_unit_max,
        "scale_metric": policy.scale_metric,
        "accepted_planning_states": sorted(policy.accepted_planning_states),
        "treats_no_activity_as_positive": policy.treats_no_activity_as_positive,
        "large_allocation_is_self_qualifying": policy.large_allocation_is_self_qualifying,
        "specialist_development_is_exclusion": policy.specialist_development_is_exclusion,
        "wholly_affordable_is_exclusion": policy.wholly_affordable_is_exclusion,
        "below_minimum_scale_is_exclusion": policy.below_minimum_scale_is_exclusion,
    }
    canonical = json.dumps(fingerprint_source, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --- Record <-> dataclass conversion -------------------------------------

def mandate_to_policy(mandate: BuyerMandate) -> BuyerMandatePolicy:
    """Builds the exact dataclass app.policy.buyer_matching.assess_buyer_
    fit expects from a persisted BuyerMandate row (+ its owning Buyer's
    identity fields) - the ONLY place a BuyerMandate is converted for
    matching use; assess_buyer_fit itself is never handed a record
    directly. `key` is deliberately the owning BUYER's own buyer_key
    (e.g. "nesten_homes"), not the mandate_key ("default") - this is what
    every existing consumer/test already means by a policy's `.key`
    (a stable per-buyer-strategy identity), and Phase A's one-mandate-
    per-buyer migration makes the two values equivalent in every case
    that exists today.

    Buyer Mandate V2, Phase B1: geography_scope/development_state_appetite
    default to their own UNSPECIFIED constant, and geography_councils/
    acquisition_types/control_appetite default to the empty frozenset,
    whenever the persisted column is still NULL (a row the B1 backfill/
    reseed has not reached yet - see BuyerMandate's own class docstring).
    This is a deliberately SAFE read-time fallback, never a claim that
    "unconfigured" means "matches everything" - no code reads these fields
    for matching purposes yet (Phase B2), so the distinction is purely
    about not fabricating a decision no one has made."""
    buyer = mandate.buyer
    return BuyerMandatePolicy(
        key=buyer.buyer_key,
        display_name=buyer.display_name,
        buyer_type=buyer.buyer_type,
        primary_requirement=mandate.primary_requirement,
        target_unit_min=mandate.target_unit_min,
        target_unit_max=mandate.target_unit_max,
        scale_metric=mandate.scale_metric,
        accepted_planning_states=frozenset(s for s in mandate.accepted_planning_states.split(",") if s),
        treats_no_activity_as_positive=mandate.treats_no_activity_as_positive,
        large_allocation_is_self_qualifying=mandate.large_allocation_is_self_qualifying,
        specialist_development_is_exclusion=mandate.specialist_development_is_exclusion,
        wholly_affordable_is_exclusion=mandate.wholly_affordable_is_exclusion,
        below_minimum_scale_is_exclusion=mandate.below_minimum_scale_is_exclusion,
        notes=mandate.notes or "",
        geography_scope=mandate.geography_scope or GEOGRAPHY_UNSPECIFIED,
        geography_councils=frozenset(c for c in (mandate.geography_councils or "").split(",") if c),
        acquisition_types=frozenset(t for t in (mandate.acquisition_types or "").split(",") if t),
        development_state_appetite=mandate.development_state_appetite or DEVELOPMENT_STATE_UNSPECIFIED,
        control_appetite=frozenset(c for c in (mandate.control_appetite or "").split(",") if c),
    )


# Phase-A-era alias for the pre-split name - see compute_buyer_profile_
# fingerprint's own comment above for why this exists.
record_to_dataclass = mandate_to_policy


def _template_to_buyer_fields(template: BuyerMandatePolicy, workspace_id: int) -> dict:
    return dict(
        workspace_id=workspace_id,
        buyer_key=template.key,
        display_name=template.display_name,
        buyer_type=template.buyer_type,
    )


def _template_to_mandate_fields(template: BuyerMandatePolicy, buyer_id: int) -> dict:
    return dict(
        buyer_id=buyer_id,
        mandate_key=DEFAULT_MANDATE_KEY,
        display_name=template.display_name,
        primary_requirement=template.primary_requirement,
        target_unit_min=template.target_unit_min,
        target_unit_max=template.target_unit_max,
        scale_metric=template.scale_metric,
        accepted_planning_states=",".join(sorted(template.accepted_planning_states)),
        treats_no_activity_as_positive=template.treats_no_activity_as_positive,
        large_allocation_is_self_qualifying=template.large_allocation_is_self_qualifying,
        specialist_development_is_exclusion=template.specialist_development_is_exclusion,
        wholly_affordable_is_exclusion=template.wholly_affordable_is_exclusion,
        below_minimum_scale_is_exclusion=template.below_minimum_scale_is_exclusion,
        notes=template.notes,
        source_template_key=template.key,
        geography_scope=template.geography_scope,
        geography_councils=",".join(sorted(template.geography_councils)),
        acquisition_types=",".join(sorted(template.acquisition_types)),
        development_state_appetite=template.development_state_appetite,
        control_appetite=",".join(sorted(template.control_appetite)),
    )


def validate_geography_councils(session, council_codes) -> None:
    """Buyer Mandate V2, Phase B1 - the one DB-aware validation this domain
    needs: app.policy.buyer_profiles.BuyerMandatePolicy.__post_init__
    validates geography_scope/geography_councils structurally (a COUNCILS
    scope must carry at least one code, every other scope must carry none)
    but cannot check whether a given code is a REAL council - that requires
    a database, which the pure policy module must never depend on. Raises
    ValueError naming exactly which code(s) are unrecognised; a caller with
    no session-aware validation point of its own (there is no mandate-
    editing UI yet - Phase B3) has nowhere else this could be checked."""
    if not council_codes:
        return
    known = {c.code for c in session.execute(select(Council)).scalars()}
    invalid = set(council_codes) - known
    if invalid:
        raise ValueError(f"Unknown council code(s): {sorted(invalid)} (known councils: {sorted(known)})")


def _b1_fields_from_template(template: BuyerMandatePolicy) -> dict:
    """Just the Buyer Mandate V2 Phase B1 columns, in persisted (comma-
    joined-string) form - the subset of _template_to_mandate_fields used
    by _apply_b1_defaults_if_missing below to backfill an EXISTING mandate
    row that predates these columns, without touching any of its other,
    already-set fields."""
    return dict(
        geography_scope=template.geography_scope,
        geography_councils=",".join(sorted(template.geography_councils)),
        acquisition_types=",".join(sorted(template.acquisition_types)),
        development_state_appetite=template.development_state_appetite,
        control_appetite=",".join(sorted(template.control_appetite)),
    )


def _apply_b1_defaults_if_missing(mandate: BuyerMandate, template: BuyerMandatePolicy) -> bool:
    """Backfills the Phase B1 structural fields onto an EXISTING mandate
    row whose geography_scope is still NULL (i.e. it predates Phase B1 -
    every Phase-A-only production mandate is in exactly this state before
    this function first runs for it), from its own source template.
    Idempotent and non-destructive: a mandate whose geography_scope is
    already set (by an earlier call to this function, or - once a future
    UI exists - a genuine user edit) is never touched again, mirroring
    seed_default_buyer_profiles' own existing "never overwrite an already-
    persisted value" guarantee for the Phase A fields.

    geography_scope alone is used as the single "has B1 already run for
    this row" signal (rather than checking all five fields independently)
    because _template_to_mandate_fields/this function always set all five
    together, in one call - they can never be partially set for a row this
    module created or backfilled.

    Returns True if anything was changed (the caller uses this to decide
    whether a commit - and a one-time fingerprint refresh, see
    scripts.backfill_buyer_mandate_b1_defaults - is needed)."""
    if mandate.geography_scope is not None:
        return False
    for field_name, value in _b1_fields_from_template(template).items():
        setattr(mandate, field_name, value)
    return True


# --- Seeding --------------------------------------------------------------

def seed_default_buyer_profiles(session, workspace: Workspace) -> list[BuyerMandate]:
    """Idempotent: creates a Buyer + one BuyerMandate (mandate_key=
    DEFAULT_MANDATE_KEY) for every template in app.policy.buyer_profiles.
    BUYER_PROFILE_ORDER this workspace doesn't already have a Buyer for
    (matched by buyer_key, never by display_name, which may change), and
    NEVER overwrites an already-existing Buyer's or BuyerMandate's fields
    (unchanged guarantee from the original Gate 1 brief: "rerunning
    bootstrap does not overwrite user-edited persistent values") even if
    the code template's own values have since changed. Returns the
    (possibly newly-created) default BuyerMandate for every seeded
    buyer_key, whether created this call or already present.

    "DEFAULT BUYER + DEFAULT MANDATE" (Phase A brief, Section 19): each of
    the four templates conceptually seeds both halves together, in one
    transaction, so a Buyer row can never exist without its own default
    mandate (or vice versa) even if this is interrupted mid-way - the
    Buyer is added and flushed (to obtain its id) before its BuyerMandate
    is constructed, and both are committed together.

    Buyer Mandate V2, Phase B1: also backfills the five new structural
    fields (geography/acquisition types/development-state appetite/
    control appetite) onto an already-existing mandate whose
    geography_scope is still NULL (see _apply_b1_defaults_if_missing) -
    the same idempotent, non-destructive, "only fill in what's genuinely
    missing" contract this function already had for Phase A fields,
    extended rather than duplicated in a second function. When this
    backfill fires on a mandate that was already onboarded (matching_
    fingerprint set) under the pre-B1 field set, its fingerprint is
    immediately recomputed and re-persisted under the complete post-B1
    field set - a one-time "fingerprint baseline migration" (Phase B1
    brief, Section 29) that keeps the stored fingerprint accurate for
    future change detection WITHOUT calling run_buyer_onboarding_baseline
    (which would re-scan the entire opportunity universe for zero benefit:
    B1 does not change assess_buyer_fit's own output, so a re-scan would
    only reproduce the exact counts already on record). onboarding_
    completed_at/onboarding_summary are deliberately left untouched by
    this - they still, correctly, describe when the mandate's assess_
    buyer_fit conclusions were last genuinely reviewed, which this
    backfill does not do."""
    existing_buyers = {
        b.buyer_key: b
        for b in session.execute(select(Buyer).where(Buyer.workspace_id == workspace.id)).scalars()
    }
    mandates: list[BuyerMandate] = []
    created_any = False
    for key in BUYER_PROFILE_ORDER:
        template = BUYER_PROFILES[key]
        validate_geography_councils(session, template.geography_councils)
        buyer = existing_buyers.get(key)
        if buyer is None:
            buyer = Buyer(**_template_to_buyer_fields(template, workspace.id))
            session.add(buyer)
            session.flush()  # obtain buyer.id for the mandate FK below
            created_any = True

        existing_mandate = session.execute(
            select(BuyerMandate).where(BuyerMandate.buyer_id == buyer.id, BuyerMandate.mandate_key == DEFAULT_MANDATE_KEY)
        ).scalars().first()
        if existing_mandate is not None:
            was_already_onboarded = existing_mandate.matching_fingerprint is not None
            if _apply_b1_defaults_if_missing(existing_mandate, template):
                if was_already_onboarded:
                    existing_mandate.matching_fingerprint = compute_buyer_mandate_fingerprint(mandate_to_policy(existing_mandate))
                created_any = True
            mandates.append(existing_mandate)
            continue
        mandate = BuyerMandate(**_template_to_mandate_fields(template, buyer.id))
        session.add(mandate)
        mandates.append(mandate)
        created_any = True
    if created_any:
        session.commit()
    return mandates


# --- Read path (used by the UI and by buyer-matching callers) ------------

def list_active_buyer_options(session) -> list[tuple[str, str]]:
    """(buyer_key, display_name) pairs for the buyer selector, in a stable
    order - from persisted, Workspace-owned Buyer rows (each with at least
    one active BuyerMandate) once scripts.bootstrap_acquisition_monitoring
    has run, falling back to the in-memory pilot templates (in their own
    existing BUYER_PROFILE_ORDER) otherwise, so the selector never
    regresses to showing only "Generic" before an operator has bootstrapped
    a fresh/test database.

    Still keyed by BUYER, not by mandate (Phase A brief, Section 23: "do
    not add nested Buyer -> Mandate selectors unless required to preserve
    functionality") - with exactly one mandate per migrated buyer today,
    get_buyer_profile_dataclass below resolves the rest transparently.

    ORDERING: the four known pilot buyer_keys always sort into their own
    canonical BUYER_PROFILE_ORDER position (Nesten Homes, Strategic Land
    Buyer, National Housebuilder, Housing Association - unchanged from
    before Phase A/the migration), regardless of the row order the one-time
    legacy-BuyerProfile backfill happened to create them in (that backfill
    reads the legacy table with no ORDER BY, so its own Buyer.id assignment
    order is not guaranteed to match the brief's own order - confirmed
    directly against production: it does not). Any buyer_key NOT among the
    four known templates (a genuinely new buyer, added after Phase A)
    sorts after all four, by its own Buyer.id - i.e. creation order, the
    only ordering that has any real meaning for a row this function has
    never seen a "canonical position" for."""
    order_index = {key: i for i, key in enumerate(BUYER_PROFILE_ORDER)}

    def _sort_key(buyer: Buyer) -> tuple[int, int]:
        return (order_index.get(buyer.buyer_key, len(order_index)), buyer.id)

    workspace = _find_default_workspace(session)
    if workspace is not None:
        buyers = session.execute(
            select(Buyer)
            .join(BuyerMandate, BuyerMandate.buyer_id == Buyer.id)
            .where(Buyer.workspace_id == workspace.id, Buyer.status == "active", BuyerMandate.status == "active")
            .distinct()
        ).scalars().all()
        if buyers:
            return [(b.buyer_key, b.display_name) for b in sorted(buyers, key=_sort_key)]
    return [(key, BUYER_PROFILES[key].display_name) for key in BUYER_PROFILE_ORDER]


def _resolve_default_mandate_for_buyer(session, buyer: Buyer) -> BuyerMandate | None:
    """The one active BuyerMandate a buyer_key currently resolves to.
    Phase A never has more than one active mandate per buyer, so "first by
    id" is unambiguous today; a future multi-mandate UI (Phase B) would
    need its own mandate-level selector instead of calling this at all -
    this function is deliberately the ONLY place that ambiguity is
    papered over, so it's easy to find and replace later."""
    return session.execute(
        select(BuyerMandate)
        .where(BuyerMandate.buyer_id == buyer.id, BuyerMandate.status == "active")
        .order_by(BuyerMandate.id.asc())
    ).scalars().first()


def get_buyer_profile_dataclass(session, profile_key: str) -> BuyerMandatePolicy | None:
    """The dataclass app.policy.buyer_matching.assess_buyer_fit expects,
    for one buyer_key - reads the persisted Buyer's own (single, Phase A)
    active BuyerMandate when one exists for the default workspace,
    otherwise falls back to the in-memory template of the same key (None
    if neither exists). This is the one function every buyer-matching read
    path (app.reporting.opportunity_feed, the Opportunity Profile page)
    should call instead of reading app.policy.buyer_profiles.BUYER_PROFILES
    directly. Parameter name/shape unchanged from before Phase A
    (`profile_key`, a plain string) - callers across the UI/opportunity
    feed need no changes at all."""
    workspace = _find_default_workspace(session)
    if workspace is not None:
        buyer = session.execute(
            select(Buyer).where(
                Buyer.workspace_id == workspace.id,
                Buyer.buyer_key == profile_key,
                Buyer.status == "active",
            )
        ).scalars().first()
        if buyer is not None:
            mandate = _resolve_default_mandate_for_buyer(session, buyer)
            if mandate is not None:
                return mandate_to_policy(mandate)
    return BUYER_PROFILES.get(profile_key)


# --- Onboarding baseline ---------------------------------------------------

class OnboardingBaselineResult:
    """Plain result holder (Gate 1 brief: "no AI... use existing
    assess_buyer_fit... do not create a numeric score") - counts only,
    never a score or ranking."""

    __slots__ = ("opportunities_reviewed", "strong_fit", "not_suitable", "insufficient_evidence", "investigative_exceptions", "summary_line")

    def __init__(self, opportunities_reviewed: int, strong_fit: int, not_suitable: int, insufficient_evidence: int, investigative_exceptions: int, summary_line: str):
        self.opportunities_reviewed = opportunities_reviewed
        self.strong_fit = strong_fit
        self.not_suitable = not_suitable
        self.insufficient_evidence = insufficient_evidence
        self.investigative_exceptions = investigative_exceptions
        self.summary_line = summary_line


def run_buyer_onboarding_baseline(session, mandate: BuyerMandate, *, page_size: int = DEFAULT_STRATEGIC_LAND_PAGE_SIZE) -> OnboardingBaselineResult:
    """Gate 1 brief, Sections 17-18 (unchanged by Phase A - only the
    persisted object passed in changed from a BuyerProfile row to a
    BuyerMandate row): when a BuyerMandate is newly onboarded (or its own
    strategy has genuinely changed - see is_buyer_mandate_baseline_stale),
    review the CURRENT opportunity universe against it once,
    deterministically (the existing, unmodified assess_buyer_fit; no AI;
    no score), then record that this is the mandate's baseline - every
    opportunity considered here is HISTORICAL for this mandate from this
    point on, never later reported as newly discovered merely because
    monitoring has just started.

    Sets mandate.matching_fingerprint/onboarding_completed_at/
    onboarding_summary and commits; creates no BuyerOpportunityAssessment
    row (a future gate's own responsibility, explicitly out of scope
    here, unchanged from before Phase A)."""
    policy = mandate_to_policy(mandate)
    universe = build_current_opportunity_universe(session, page_size=page_size)

    strong_fit = not_suitable = insufficient_evidence = investigative_exceptions = 0
    for opportunity in universe:
        assessment = assess_buyer_fit(policy, opportunity.matching_facts)
        if assessment.classification == STRONG_FIT:
            strong_fit += 1
        elif assessment.classification == NOT_SUITABLE:
            not_suitable += 1
        elif assessment.classification == INSUFFICIENT_EVIDENCE:
            insufficient_evidence += 1
        if assessment.is_investigative_exception:
            investigative_exceptions += 1

    summary_line = (
        f"reviewed={len(universe)} strong_fit={strong_fit} not_suitable={not_suitable} "
        f"insufficient_evidence={insufficient_evidence} investigative_exceptions={investigative_exceptions}"
    )

    mandate.matching_fingerprint = compute_buyer_mandate_fingerprint(policy)
    mandate.onboarding_completed_at = utcnow()
    mandate.onboarding_summary = summary_line
    session.commit()

    return OnboardingBaselineResult(
        opportunities_reviewed=len(universe), strong_fit=strong_fit, not_suitable=not_suitable,
        insufficient_evidence=insufficient_evidence, investigative_exceptions=investigative_exceptions,
        summary_line=summary_line,
    )


def is_buyer_mandate_baseline_stale(mandate: BuyerMandate) -> bool:
    """True when this mandate has never been onboarded at all, OR its own
    matching-relevant fields have changed since the last successful
    baseline (BUYER_PROFILE_CHANGED, now more precisely a mandate-strategy
    change - Gate 1 brief Section 19) - a fresh fingerprint comparison
    every time, never a separate boolean flag that could drift from the
    truth. Never reads or affects any global opportunity data - a
    mandate's own strategy changing must never, on its own, mark any
    opportunity as newly discovered.

    Phase A significance: because compute_buyer_mandate_fingerprint reads
    only fields declared on BuyerMandate/consumed by assess_buyer_fit, a
    Buyer's own display_name/buyer_type changing (which never touches this
    mandate row's own columns) cannot make this return True - see this
    function's own test coverage for a direct proof."""
    if mandate.onboarding_completed_at is None or mandate.matching_fingerprint is None:
        return True
    current_fingerprint = compute_buyer_mandate_fingerprint(mandate_to_policy(mandate))
    return current_fingerprint != mandate.matching_fingerprint


# Phase-A-era alias for the pre-split name.
is_buyer_profile_baseline_stale = is_buyer_mandate_baseline_stale


def bootstrap_acquisition_monitoring(session, *, page_size: int = DEFAULT_STRATEGIC_LAND_PAGE_SIZE) -> dict:
    """The single Gate 1 entry point (scripts.bootstrap_acquisition_
    monitoring's own only call) - the ONE canonical, safe sequence (Gate 1
    amendment, Product Owner review), now operating on Buyer/BuyerMandate:

        existing DB
        -> global opportunity monitoring baseline established
        -> current buyer onboarding baseline established
        -> (ongoing, separately scheduled) monitoring starts

    1. Establishes the GLOBAL opportunity monitoring baseline first
       (app.reporting.opportunity_change.sync_opportunity_monitoring_state)
       - unchanged, buyer-independent.
    2. Resolves the default workspace and seeds the four pilot Buyers +
       their default BuyerMandates into it (idempotent - never overwrites
       an already-persisted, edited row).
    3. Runs/re-runs the onboarding baseline for every active BuyerMandate
       whose baseline is currently stale (never onboarded yet, or
       genuinely changed since) - safe to call repeatedly, since checking
       staleness for an already-current mandate is a cheap in-memory
       fingerprint comparison with no opportunity-universe scan at all.

    Return-shape unchanged from before Phase A: `results` is still keyed
    by buyer_key (the same string scripts.bootstrap_acquisition_monitoring
    already prints as "profile_key") - Phase A's one-mandate-per-buyer
    migration makes buyer_key and this mandate's own identity equivalent
    in every case that exists today."""
    global_baseline = sync_opportunity_monitoring_state(session, page_size=page_size)

    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)

    buyers = session.execute(
        select(Buyer).where(Buyer.workspace_id == workspace.id, Buyer.status == "active")
    ).scalars().all()

    onboarding_results: dict[str, OnboardingBaselineResult] = {}
    mandate_count = 0
    for buyer in buyers:
        mandates = session.execute(
            select(BuyerMandate).where(BuyerMandate.buyer_id == buyer.id, BuyerMandate.status == "active")
        ).scalars().all()
        mandate_count += len(mandates)
        for mandate in mandates:
            if is_buyer_mandate_baseline_stale(mandate):
                onboarding_results[buyer.buyer_key] = run_buyer_onboarding_baseline(session, mandate, page_size=page_size)

    return {
        "workspace_id": workspace.id,
        "global_opportunity_baseline": global_baseline,
        "profiles_total": mandate_count,
        "profiles_onboarded_this_run": list(onboarding_results.keys()),
        "results": onboarding_results,
    }


# --- Phase B1 one-time backfill: structural fields onto pre-B1 mandates ----

def backfill_buyer_mandate_b1_defaults(session, *, dry_run: bool = True) -> dict:
    """Reporting/execution wrapper for scripts.backfill_buyer_mandate_b1_
    defaults - identifies every known-template BuyerMandate (matched by
    buyer_key against app.policy.buyer_profiles.BUYER_PROFILE_ORDER, the
    same set seed_default_buyer_profiles seeds) whose geography_scope is
    still NULL, reports its current state and the template values it would
    receive, and - only when dry_run=False - actually performs the
    backfill by calling seed_default_buyer_profiles itself (the SAME
    idempotent, non-destructive code path every other reseed already uses,
    now extended with the Phase B1 fields - see that function's own
    docstring for the one-time fingerprint-baseline-migration it performs
    when a mandate was already onboarded). Never touches a mandate whose
    geography_scope is already set - there is nothing this function does
    that seed_default_buyer_profiles' own idempotency guarantee doesn't
    already cover; this exists purely to give the migration script a safe,
    inspectable dry-run report before it commits to anything."""
    workspace = resolve_default_workspace(session)
    before: dict[str, dict] = {}
    for key in BUYER_PROFILE_ORDER:
        buyer = session.execute(
            select(Buyer).where(Buyer.workspace_id == workspace.id, Buyer.buyer_key == key)
        ).scalars().first()
        if buyer is None:
            continue
        mandate = session.execute(
            select(BuyerMandate).where(BuyerMandate.buyer_id == buyer.id, BuyerMandate.mandate_key == DEFAULT_MANDATE_KEY)
        ).scalars().first()
        if mandate is None:
            continue
        before[key] = {
            "needs_backfill": mandate.geography_scope is None,
            "matching_fingerprint_before": mandate.matching_fingerprint,
        }

    if not dry_run:
        seed_default_buyer_profiles(session, workspace)

    report: dict[str, dict] = {}
    for key, info in before.items():
        entry = dict(info)
        if info["needs_backfill"]:
            entry["proposed_fields"] = _b1_fields_from_template(BUYER_PROFILES[key])
        if not dry_run and info["needs_backfill"]:
            mandate = session.execute(
                select(BuyerMandate).join(Buyer, BuyerMandate.buyer_id == Buyer.id).where(Buyer.buyer_key == key)
            ).scalars().first()
            entry["applied_fields"] = _b1_fields_from_template(BUYER_PROFILES[key])
            entry["matching_fingerprint_after"] = mandate.matching_fingerprint
        report[key] = entry

    return {"dry_run": dry_run, "workspace_id": workspace.id, "mandates": report}


# --- Phase A one-time migration: legacy BuyerProfile -> Buyer + BuyerMandate

def migrate_buyer_profiles_to_mandates(session, *, dry_run: bool = True) -> dict:
    """The one-time, idempotent backfill from the legacy app.db.models.
    BuyerProfile table into an equivalent Buyer + BuyerMandate pair per
    row (mandate_key=DEFAULT_MANDATE_KEY). Explicit, operator-invoked
    (scripts.migrate_buyer_profiles_to_mandates.py) - never run
    automatically on page load, mirroring scripts.migrate_schema's own
    "migrations are not a page-load side effect" discipline.

    dry_run=True (the default) computes and returns the full report
    WITHOUT committing anything - every Buyer/BuyerMandate object
    constructed below is flushed only to obtain an id for FK-building
    within this call, then rolled back at the end. Pass dry_run=False to
    actually persist the migration.

    Migrates WHATEVER legitimate BuyerProfile rows exist - never
    hard-coded to exactly four, so a workspace with more (or fewer) rows
    than the four pilot templates still migrates completely and correctly.

    Idempotent and non-destructive:
      - matched by (workspace_id, buyer_key=profile_key) for the Buyer,
        and (buyer_id, mandate_key=DEFAULT_MANDATE_KEY) for the
        BuyerMandate - a row already migrated is skipped entirely, never
        re-created or overwritten, so a second run is a safe no-op.
      - never reads matching_fingerprint/onboarding_completed_at/
        onboarding_summary/status/source_template_key from the legacy row
        and blindly copies them across without re-deriving them: the
        migrated BuyerMandate's own fingerprint is RECOMPUTED from its own
        (freshly-populated) fields via compute_buyer_mandate_fingerprint,
        which should equal the legacy row's own matching_fingerprint bit-
        for-bit (same field set, same JSON/hash convention) whenever the
        legacy row was itself already onboarded - this is checked, not
        assumed: any mismatch is collected into the returned report's own
        "fingerprint_mismatches" list (never silently ignored) for the
        caller to treat as a STOP signal before running with dry_run=False
        against production. onboarding_completed_at/onboarding_summary/
        status/
        source_template_key are copied across verbatim, since they
        describe the SAME underlying onboarding event and code-template
        provenance, not something Phase A itself performed.
      - never deletes, modifies, or writes to the legacy BuyerProfile
        table itself.

    Returns a dict report of what happened - never prints or logs
    directly, so scripts.migrate_buyer_profiles_to_mandates.py owns all
    operator-facing output."""
    from app.db.models import BuyerProfile as LegacyBuyerProfile

    # Ordered by the legacy row's own id - purely for deterministic,
    # reproducible Buyer/BuyerMandate id assignment across repeated dry
    # runs; list_active_buyer_options does NOT rely on this order for
    # display (it sorts by each buyer_key's own canonical position - see
    # that function's own docstring for exactly why an ORDER BY here would
    # not have been sufficient on its own).
    legacy_rows = session.execute(select(LegacyBuyerProfile).order_by(LegacyBuyerProfile.id.asc())).scalars().all()

    migrated_buyers = 0
    migrated_mandates = 0
    already_present_buyers = 0
    already_present_mandates = 0
    skipped_fingerprint_mismatch: list[str] = []

    for legacy in legacy_rows:
        buyer = session.execute(
            select(Buyer).where(Buyer.workspace_id == legacy.workspace_id, Buyer.buyer_key == legacy.profile_key)
        ).scalars().first()
        if buyer is None:
            buyer = Buyer(
                workspace_id=legacy.workspace_id,
                buyer_key=legacy.profile_key,
                display_name=legacy.display_name,
                buyer_type=legacy.buyer_type,
                status=legacy.status,
            )
            session.add(buyer)
            session.flush()
            migrated_buyers += 1
        else:
            already_present_buyers += 1

        existing_mandate = session.execute(
            select(BuyerMandate).where(BuyerMandate.buyer_id == buyer.id, BuyerMandate.mandate_key == DEFAULT_MANDATE_KEY)
        ).scalars().first()
        if existing_mandate is not None:
            already_present_mandates += 1
            continue

        mandate = BuyerMandate(
            buyer_id=buyer.id,
            mandate_key=DEFAULT_MANDATE_KEY,
            display_name=legacy.display_name,
            primary_requirement=legacy.primary_requirement,
            target_unit_min=legacy.target_unit_min,
            target_unit_max=legacy.target_unit_max,
            scale_metric=legacy.scale_metric,
            accepted_planning_states=legacy.accepted_planning_states,
            treats_no_activity_as_positive=legacy.treats_no_activity_as_positive,
            large_allocation_is_self_qualifying=legacy.large_allocation_is_self_qualifying,
            specialist_development_is_exclusion=legacy.specialist_development_is_exclusion,
            wholly_affordable_is_exclusion=legacy.wholly_affordable_is_exclusion,
            below_minimum_scale_is_exclusion=legacy.below_minimum_scale_is_exclusion,
            notes=legacy.notes,
            status=legacy.status,
            source_template_key=legacy.source_template_key,
            onboarding_completed_at=legacy.onboarding_completed_at,
            onboarding_summary=legacy.onboarding_summary,
            # Buyer Mandate V2, Phase B1: a mandate migrated from a known
            # code template is fully B1-populated from birth, exactly like
            # one created by seed_default_buyer_profiles - never left with
            # NULL B1 columns merely because it arrived via this older
            # migration path instead. A legacy row with no matching
            # template (source_template_key not in BUYER_PROFILES) is left
            # unset - mandate_to_policy's own NULL-safe fallback handles it.
            **(_b1_fields_from_template(BUYER_PROFILES[legacy.profile_key]) if legacy.profile_key in BUYER_PROFILES else {}),
        )
        session.add(mandate)
        session.flush()

        # Phase A's own self-consistency check: did the field-by-field copy
        # above correctly reproduce the SAME Phase-A-era fields the legacy
        # row's own matching_fingerprint was computed over? Deliberately
        # compared against a fingerprint FROZEN to that original field set
        # (_phase_a_only_fingerprint), never the current, Phase-B1-widened
        # compute_buyer_mandate_fingerprint - the two now cover genuinely
        # different field sets by design (B1 added new fields no legacy
        # row ever had an opinion on), so comparing the current schema's
        # fingerprint against a pre-B1 value would always "mismatch" for a
        # reason that has nothing to do with a copy error.
        phase_a_check = _phase_a_only_fingerprint(mandate_to_policy(mandate))
        if legacy.matching_fingerprint is not None and phase_a_check != legacy.matching_fingerprint:
            # This should be structurally impossible if the field-by-field
            # copy above is correct. Recorded for the caller (scripts.
            # migrate_buyer_profiles_to_mandates.py) to treat as a STOP
            # signal rather than silently trusted either value.
            skipped_fingerprint_mismatch.append(legacy.profile_key)
        # The mandate's own PERSISTED fingerprint is always the CURRENT,
        # full (post-Phase-B1) value - never the Phase-A-only comparison
        # value above, which exists solely for this one integrity check.
        mandate.matching_fingerprint = compute_buyer_mandate_fingerprint(mandate_to_policy(mandate))

        migrated_mandates += 1

    if dry_run:
        # Roll back every Buyer/BuyerMandate flushed above - dry_run=True
        # (the default) must make ZERO durable database changes, exactly
        # like every other population script's own dry-run convention
        # (see scripts.populate_control_relationships). flush() above was
        # only ever needed to obtain each new Buyer's own id for its
        # BuyerMandate's FK within this same, still-open transaction.
        session.rollback()
    else:
        session.commit()

    return {
        "dry_run": dry_run,
        "legacy_rows_found": len(legacy_rows),
        "buyers_created": migrated_buyers,
        "buyers_already_present": already_present_buyers,
        "mandates_created": migrated_mandates,
        "mandates_already_present": already_present_mandates,
        "fingerprint_mismatches": skipped_fingerprint_mismatch,
    }
