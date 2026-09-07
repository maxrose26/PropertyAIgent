"""Gate 1 (Acquisition Monitoring Substrate) - the persistence layer for
Buyer Profiles: default Workspace bootstrap, seeding the four existing
pilot templates, converting between app.db.models.BuyerProfile (the
persistent, Workspace-owned row) and app.policy.buyer_profiles.BuyerProfile
(the dataclass app.policy.buyer_matching.assess_buyer_fit actually
consumes), the buyer-profile matching fingerprint, and the onboarding
baseline scan.

Deliberately kept OUT of app.policy.buyer_profiles.py (a pure, DB-free
config module - UNCHANGED by this gate) and app.policy.buyer_matching.py
(pure matching, DB-free - also UNCHANGED). This is the only new module
that talks to the database on the Buyer Profile side; assess_buyer_fit
itself never sees a database row, only ever the same dataclass it always
has.

Read-path resilience (important): every function here that reads Buyer
Profiles falls back to the in-memory app.policy.buyer_profiles.
BUYER_PROFILES/BUYER_PROFILE_ORDER templates whenever no persisted
Workspace/row exists yet - this is what keeps every pre-existing test and
the live UI working completely unchanged before an operator has run
scripts.bootstrap_acquisition_monitoring (see that script's own docstring
for why seeding is an explicit step, never a page-load side effect).
Once bootstrap has run, the persisted row (which may since have been
edited) takes over transparently.
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import select

from app.db.models import BuyerProfile as BuyerProfileRecord
from app.db.models import Workspace, utcnow
from app.policy.buyer_matching import INSUFFICIENT_EVIDENCE, NOT_SUITABLE, STRONG_FIT, assess_buyer_fit
from app.policy.buyer_profiles import BUYER_PROFILE_ORDER, BUYER_PROFILES, BuyerProfile
from app.reporting.opportunity_change import sync_opportunity_monitoring_state
from app.reporting.opportunity_universe import DEFAULT_STRATEGIC_LAND_PAGE_SIZE, build_current_opportunity_universe

DEFAULT_WORKSPACE_NAME = "Property AIgent Pilot"


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


# --- Buyer Profile fingerprint -------------------------------------------

def compute_buyer_profile_fingerprint(profile: BuyerProfile) -> str:
    """sha256 over ONLY the fields app.policy.buyer_matching.assess_buyer_
    fit actually reads (Gate 1 brief: "fingerprint ONLY fields that affect
    buyer matching/monitoring... do NOT include display-only metadata").
    display_name/buyer_type/primary_requirement/notes/key are deliberately
    excluded - assess_buyer_fit never reads any of them, confirmed by
    inspection of that function."""
    fingerprint_source = {
        "target_unit_min": profile.target_unit_min,
        "target_unit_max": profile.target_unit_max,
        "scale_metric": profile.scale_metric,
        "accepted_planning_states": sorted(profile.accepted_planning_states),
        "treats_no_activity_as_positive": profile.treats_no_activity_as_positive,
        "large_allocation_is_self_qualifying": profile.large_allocation_is_self_qualifying,
        "specialist_development_is_exclusion": profile.specialist_development_is_exclusion,
        "wholly_affordable_is_exclusion": profile.wholly_affordable_is_exclusion,
        "below_minimum_scale_is_exclusion": profile.below_minimum_scale_is_exclusion,
    }
    canonical = json.dumps(fingerprint_source, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --- Record <-> dataclass conversion -------------------------------------

def record_to_dataclass(record: BuyerProfileRecord) -> BuyerProfile:
    """Builds the exact dataclass app.policy.buyer_matching.assess_buyer_
    fit expects from a persisted row - the ONLY place a BuyerProfileRecord
    is converted for matching use; assess_buyer_fit itself is never handed
    a record directly, so it required zero changes for this gate."""
    return BuyerProfile(
        key=record.profile_key,
        display_name=record.display_name,
        buyer_type=record.buyer_type,
        primary_requirement=record.primary_requirement,
        target_unit_min=record.target_unit_min,
        target_unit_max=record.target_unit_max,
        scale_metric=record.scale_metric,
        accepted_planning_states=frozenset(s for s in record.accepted_planning_states.split(",") if s),
        treats_no_activity_as_positive=record.treats_no_activity_as_positive,
        large_allocation_is_self_qualifying=record.large_allocation_is_self_qualifying,
        specialist_development_is_exclusion=record.specialist_development_is_exclusion,
        wholly_affordable_is_exclusion=record.wholly_affordable_is_exclusion,
        below_minimum_scale_is_exclusion=record.below_minimum_scale_is_exclusion,
        notes=record.notes or "",
    )


def _template_to_record_fields(template: BuyerProfile, workspace_id: int) -> dict:
    return dict(
        workspace_id=workspace_id,
        profile_key=template.key,
        display_name=template.display_name,
        buyer_type=template.buyer_type,
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
    )


# --- Seeding --------------------------------------------------------------

def seed_default_buyer_profiles(session, workspace: Workspace) -> list[BuyerProfileRecord]:
    """Idempotent: creates a persistent row for every template in
    app.policy.buyer_profiles.BUYER_PROFILE_ORDER this workspace doesn't
    already have (matched by profile_key, never by display_name, which
    may change), and NEVER overwrites an already-existing row's fields
    (Gate 1 brief: "rerunning bootstrap does not overwrite user-edited
    persistent values") even if the code template's own values have since
    changed. Returns every record for this workspace's seeded
    profile_keys, whether newly created this call or already present."""
    existing = {
        r.profile_key: r
        for r in session.execute(select(BuyerProfileRecord).where(BuyerProfileRecord.workspace_id == workspace.id)).scalars()
    }
    records = []
    created_any = False
    for key in BUYER_PROFILE_ORDER:
        if key in existing:
            records.append(existing[key])
            continue
        template = BUYER_PROFILES[key]
        record = BuyerProfileRecord(**_template_to_record_fields(template, workspace.id))
        session.add(record)
        records.append(record)
        created_any = True
    if created_any:
        session.commit()
    return records


# --- Read path (used by the UI and by buyer-matching callers) ------------

def list_active_buyer_options(session) -> list[tuple[str, str]]:
    """(profile_key, display_name) pairs for the buyer selector, in a
    stable order - from persisted, Workspace-owned BuyerProfile rows once
    scripts.bootstrap_acquisition_monitoring has run, falling back to the
    in-memory pilot templates (in their own existing BUYER_PROFILE_ORDER)
    otherwise, so the selector never regresses to showing only "Generic"
    before an operator has bootstrapped a fresh/test database."""
    workspace = _find_default_workspace(session)
    if workspace is not None:
        records = session.execute(
            select(BuyerProfileRecord)
            .where(BuyerProfileRecord.workspace_id == workspace.id, BuyerProfileRecord.status == "active")
            .order_by(BuyerProfileRecord.id.asc())
        ).scalars().all()
        if records:
            return [(r.profile_key, r.display_name) for r in records]
    return [(key, BUYER_PROFILES[key].display_name) for key in BUYER_PROFILE_ORDER]


def get_buyer_profile_dataclass(session, profile_key: str) -> BuyerProfile | None:
    """The dataclass app.policy.buyer_matching.assess_buyer_fit expects,
    for one profile_key - reads the persisted, possibly-edited row when
    one exists for the default workspace, otherwise falls back to the
    in-memory template of the same key (None if neither exists). This is
    the one function every buyer-matching read path (app.reporting.
    opportunity_feed, the Opportunity Profile page) should call instead of
    reading app.policy.buyer_profiles.BUYER_PROFILES directly."""
    workspace = _find_default_workspace(session)
    if workspace is not None:
        record = session.execute(
            select(BuyerProfileRecord).where(
                BuyerProfileRecord.workspace_id == workspace.id,
                BuyerProfileRecord.profile_key == profile_key,
                BuyerProfileRecord.status == "active",
            )
        ).scalars().first()
        if record is not None:
            return record_to_dataclass(record)
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


def run_buyer_onboarding_baseline(session, record: BuyerProfileRecord, *, page_size: int = DEFAULT_STRATEGIC_LAND_PAGE_SIZE) -> OnboardingBaselineResult:
    """Gate 1 brief, Sections 17-18: when a BuyerProfile is newly onboarded
    (or its mandate has genuinely changed - see is_buyer_profile_baseline_
    stale), review the CURRENT opportunity universe against it once,
    deterministically (the existing, unmodified assess_buyer_fit; no AI;
    no score), then record that this is the buyer's baseline - every
    opportunity considered here is HISTORICAL for this buyer from this
    point on, never later reported as newly discovered merely because
    monitoring has just started (Section 20's "NEW BUYER vs NEW
    OPPORTUNITY" distinction: Gate 2's own future "what's new for this
    buyer" query is opportunities with first_seen_at/last_change_at AFTER
    this profile's own onboarding_completed_at, never a per-(buyer,
    opportunity) row - that table is explicitly Gate 2's own
    BuyerOpportunityAssessment, not built here).

    Sets record.matching_fingerprint/onboarding_completed_at/
    onboarding_summary and commits; creates no BuyerOpportunityAssessment
    row (Gate 2's own responsibility, explicitly out of scope here)."""
    profile = record_to_dataclass(record)
    universe = build_current_opportunity_universe(session, page_size=page_size)

    strong_fit = not_suitable = insufficient_evidence = investigative_exceptions = 0
    for opportunity in universe:
        assessment = assess_buyer_fit(profile, opportunity.matching_facts)
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

    record.matching_fingerprint = compute_buyer_profile_fingerprint(profile)
    record.onboarding_completed_at = utcnow()
    record.onboarding_summary = summary_line
    session.commit()

    return OnboardingBaselineResult(
        opportunities_reviewed=len(universe), strong_fit=strong_fit, not_suitable=not_suitable,
        insufficient_evidence=insufficient_evidence, investigative_exceptions=investigative_exceptions,
        summary_line=summary_line,
    )


def is_buyer_profile_baseline_stale(record: BuyerProfileRecord) -> bool:
    """True when this buyer has never been onboarded at all, OR its own
    matching-relevant fields have changed since the last successful
    baseline (BUYER_PROFILE_CHANGED - Gate 1 brief Section 19) - a fresh
    fingerprint comparison every time, never a separate boolean flag that
    could drift from the truth (mirrors app.reporting.allocation_
    intelligence_summary.should_regenerate_allocation_summary's own
    "prefer a fingerprint over ad-hoc mark-stale writes" principle). Never
    reads or affects any global opportunity data - a buyer's own mandate
    changing must never, on its own, mark any opportunity as newly
    discovered (Section 20's own "a profile change is a different trigger
    from a new opportunity" instruction)."""
    if record.onboarding_completed_at is None or record.matching_fingerprint is None:
        return True
    current_fingerprint = compute_buyer_profile_fingerprint(record_to_dataclass(record))
    return current_fingerprint != record.matching_fingerprint


def bootstrap_acquisition_monitoring(session, *, page_size: int = DEFAULT_STRATEGIC_LAND_PAGE_SIZE) -> dict:
    """The single Gate 1 entry point (scripts.bootstrap_acquisition_
    monitoring's own only call) - the ONE canonical, safe sequence (Gate 1
    amendment, Product Owner review):

        existing DB
        -> global opportunity monitoring baseline established
        -> current buyer onboarding baseline established
        -> (ongoing, separately scheduled) monitoring starts

    1. Establishes the GLOBAL opportunity monitoring baseline first
       (app.reporting.opportunity_change.sync_opportunity_monitoring_state)
       - on a fresh/never-before-monitored database this persists every
       current opportunity as BASELINE_EXISTING, never NEW (see that
       function's own docstring); on an already-monitored database this is
       ordinary, idempotent ongoing sync.
    2. Resolves the default workspace and seeds the four pilot profiles
       into it (idempotent - never overwrites an already-persisted, edited
       row).
    3. Runs/re-runs the onboarding baseline for every active profile whose
       baseline is currently stale (never onboarded yet, or genuinely
       changed since) - safe to call repeatedly, since checking staleness
       for an already-current buyer is a cheap in-memory fingerprint
       comparison with no opportunity-universe scan at all.

    Doing step 1 before step 3 is a deliberate belt-and-braces ordering,
    not the ONLY thing preventing a false NEW - sync_opportunity_
    monitoring_state's own self-detection (an empty monitoring table means
    "never established before", regardless of call order) is what actually
    guarantees correctness even if these steps were ever invoked out of
    order or from separate processes."""
    global_baseline = sync_opportunity_monitoring_state(session, page_size=page_size)

    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)

    records = session.execute(
        select(BuyerProfileRecord).where(BuyerProfileRecord.workspace_id == workspace.id, BuyerProfileRecord.status == "active")
    ).scalars().all()

    onboarding_results: dict[str, OnboardingBaselineResult] = {}
    for record in records:
        if is_buyer_profile_baseline_stale(record):
            onboarding_results[record.profile_key] = run_buyer_onboarding_baseline(session, record, page_size=page_size)

    return {
        "workspace_id": workspace.id,
        "global_opportunity_baseline": global_baseline,
        "profiles_total": len(records),
        "profiles_onboarded_this_run": list(onboarding_results.keys()),
        "results": onboarding_results,
    }
