"""Buyer Mandate V2, Phase A (Buyer/Mandate Domain Separation) - tests for
app.policy.buyer_profile_store: Workspace bootstrap, persistent Buyer +
BuyerMandate seeding, the matching-relevant fingerprint (now scoped to the
mandate, not the buyer's own identity), the onboarding baseline, and the
one-time legacy BuyerProfile -> Buyer/BuyerMandate migration.

Every pre-existing Gate 1 behavioural guarantee this file used to assert
against a single BuyerProfile row is preserved here against the split
Buyer + BuyerMandate pair - see each test's own docstring for what,
specifically, is now proven at the mandate level vs the buyer level.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from app.db.models import Application, Buyer, BuyerMandate, Council, LocalPlan, LocalPlanSite, SchemeIntelligence, Site, Workspace
from app.db.models import BuyerProfile as LegacyBuyerProfile
from app.policy.buyer_matching import INSUFFICIENT_EVIDENCE, NOT_SUITABLE, STRONG_FIT, assess_buyer_fit, build_planning_delivery_matching_facts
from app.policy.buyer_profiles import (
    BUYER_PROFILE_ORDER,
    BUYER_PROFILES,
    GEOGRAPHY_ALL_CURRENT_COVERAGE,
    GEOGRAPHY_COUNCILS,
    GEOGRAPHY_UNSPECIFIED,
    HOUSING_ASSOCIATION,
    NATIONAL_HOUSEBUILDER,
    NESTEN_HOMES,
    STRATEGIC_LAND_BUYER,
    UNRESOLVED_OWNERSHIP_INVESTIGATABLE,
)
from app.policy.buyer_profile_store import (
    DEFAULT_MANDATE_KEY,
    backfill_buyer_mandate_b1_defaults,
    bootstrap_acquisition_monitoring,
    compute_buyer_mandate_fingerprint,
    get_buyer_profile_dataclass,
    is_buyer_mandate_baseline_stale,
    list_active_buyer_options,
    mandate_to_policy,
    migrate_buyer_profiles_to_mandates,
    resolve_default_workspace,
    run_buyer_onboarding_baseline,
    seed_default_buyer_profiles,
    validate_geography_councils,
)
from app.reporting.opportunity_change import sync_opportunity_monitoring_state


def _mandate_for(session, buyer_key: str) -> BuyerMandate:
    return session.execute(
        select(BuyerMandate).join(Buyer, BuyerMandate.buyer_id == Buyer.id).where(Buyer.buyer_key == buyer_key)
    ).scalars().first()


# --- Workspace --------------------------------------------------------------

def test_resolve_default_workspace_creates_exactly_one_row(session):
    workspace = resolve_default_workspace(session)
    assert workspace.id is not None
    assert workspace.status == "active"
    assert session.execute(select(Workspace)).scalars().all() == [workspace]


def test_resolve_default_workspace_is_idempotent(session):
    first = resolve_default_workspace(session)
    second = resolve_default_workspace(session)
    assert first.id == second.id
    assert len(session.execute(select(Workspace)).scalars().all()) == 1


# --- Buyer + BuyerMandate seeding --------------------------------------------

def test_seed_default_buyer_profiles_creates_exactly_four_buyers_and_mandates(session):
    workspace = resolve_default_workspace(session)
    mandates = seed_default_buyer_profiles(session, workspace)
    assert len(mandates) == 4
    assert {m.mandate_key for m in mandates} == {DEFAULT_MANDATE_KEY}
    buyers = session.execute(select(Buyer).where(Buyer.workspace_id == workspace.id)).scalars().all()
    assert {b.buyer_key for b in buyers} == set(BUYER_PROFILE_ORDER)
    assert all(m.buyer.workspace_id == workspace.id for m in mandates)


def test_seeding_is_idempotent_and_never_duplicates(session):
    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)
    seed_default_buyer_profiles(session, workspace)
    buyers = session.execute(select(Buyer).where(Buyer.workspace_id == workspace.id)).scalars().all()
    mandates = session.execute(select(BuyerMandate)).scalars().all()
    assert len(buyers) == 4
    assert len(mandates) == 4


def test_seeding_never_overwrites_an_already_edited_value(session):
    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)
    nesten = _mandate_for(session, "nesten_homes")
    nesten.target_unit_max = 150  # simulate a user edit
    session.commit()

    seed_default_buyer_profiles(session, workspace)  # rerun - must not clobber the edit

    reloaded = _mandate_for(session, "nesten_homes")
    assert reloaded.target_unit_max == 150


def test_seeding_never_overwrites_an_edited_buyer_identity_field(session):
    """Phase A's own new guarantee: editing the BUYER's identity (e.g. a
    display-name correction) must be just as durable across a reseed as
    editing the mandate's own strategy already was."""
    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)
    buyer = session.execute(select(Buyer).where(Buyer.buyer_key == "nesten_homes")).scalars().first()
    buyer.display_name = "Nesten Homes Ltd"
    session.commit()

    seed_default_buyer_profiles(session, workspace)

    reloaded = session.execute(select(Buyer).where(Buyer.buyer_key == "nesten_homes")).scalars().first()
    assert reloaded.display_name == "Nesten Homes Ltd"


def test_seeded_fields_match_the_code_template_exactly(session):
    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)
    buyer = session.execute(select(Buyer).where(Buyer.buyer_key == "nesten_homes")).scalars().first()
    mandate = _mandate_for(session, "nesten_homes")

    assert buyer.display_name == NESTEN_HOMES.display_name
    assert buyer.buyer_type == NESTEN_HOMES.buyer_type
    assert mandate.target_unit_min == NESTEN_HOMES.target_unit_min
    assert mandate.target_unit_max == NESTEN_HOMES.target_unit_max
    assert mandate.scale_metric == NESTEN_HOMES.scale_metric
    assert set(mandate.accepted_planning_states.split(",")) == set(NESTEN_HOMES.accepted_planning_states)
    assert mandate.specialist_development_is_exclusion == NESTEN_HOMES.specialist_development_is_exclusion
    assert mandate.wholly_affordable_is_exclusion == NESTEN_HOMES.wholly_affordable_is_exclusion
    assert mandate.below_minimum_scale_is_exclusion == NESTEN_HOMES.below_minimum_scale_is_exclusion
    assert mandate.source_template_key == "nesten_homes"
    assert mandate.mandate_key == DEFAULT_MANDATE_KEY


# --- Record <-> dataclass round-trip / deterministic matching preserved ----

def test_mandate_to_policy_round_trip_preserves_every_matching_field(session):
    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)
    mandate = _mandate_for(session, "national_housebuilder")
    rebuilt = mandate_to_policy(mandate)

    assert rebuilt.key == NATIONAL_HOUSEBUILDER.key
    assert rebuilt.target_unit_min == NATIONAL_HOUSEBUILDER.target_unit_min
    assert rebuilt.target_unit_max == NATIONAL_HOUSEBUILDER.target_unit_max
    assert rebuilt.scale_metric == NATIONAL_HOUSEBUILDER.scale_metric
    assert rebuilt.accepted_planning_states == NATIONAL_HOUSEBUILDER.accepted_planning_states
    assert rebuilt.treats_no_activity_as_positive == NATIONAL_HOUSEBUILDER.treats_no_activity_as_positive
    assert rebuilt.large_allocation_is_self_qualifying == NATIONAL_HOUSEBUILDER.large_allocation_is_self_qualifying
    assert rebuilt.specialist_development_is_exclusion == NATIONAL_HOUSEBUILDER.specialist_development_is_exclusion
    assert rebuilt.wholly_affordable_is_exclusion == NATIONAL_HOUSEBUILDER.wholly_affordable_is_exclusion
    assert rebuilt.below_minimum_scale_is_exclusion == NATIONAL_HOUSEBUILDER.below_minimum_scale_is_exclusion


def test_deterministic_matching_is_identical_before_and_after_persistence(session):
    """The core regression guarantee for all four profiles, preserved
    exactly across the Buyer/BuyerMandate split: assess_buyer_fit's own
    output must not change one bit merely because the policy now comes
    from a persisted Buyer+BuyerMandate pair instead of the in-memory
    template - Focus School's own real figures, exactly as used in
    test_buyer_matching.py's own acceptance case."""
    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)

    site = Site(council_code="stockport", canonical_address="focus school persisted", display_address="Focus School Persisted")
    session.add(site)
    session.flush()
    app = Application(council_code="stockport", reference="DC/085997-PERSIST", site_id=site.id, status="Decided", decision="Granted")
    session.add(app)
    session.flush()
    si = SchemeIntelligence(
        application_id=app.id, total_units_final=82, affordable_units_final=72, affordable_percentage_final=100.0,
        affordable_missing=False, development_type="mixed_retirement_and_market_housing",
        applicant_company="Anwyl Partnerships", core_intelligence_complete=True,
    )
    session.add(si)
    session.commit()
    facts = build_planning_delivery_matching_facts(si)

    for buyer_key in BUYER_PROFILE_ORDER:
        template = BUYER_PROFILES[buyer_key]
        mandate = _mandate_for(session, buyer_key)
        persisted = mandate_to_policy(mandate)

        template_result = assess_buyer_fit(template, facts)
        persisted_result = assess_buyer_fit(persisted, facts)
        assert template_result.classification == persisted_result.classification
        assert template_result.is_investigative_exception == persisted_result.is_investigative_exception
        assert template_result.matches == persisted_result.matches
        assert template_result.does_not_match == persisted_result.does_not_match
        assert template_result.unknown == persisted_result.unknown


def test_get_buyer_profile_dataclass_falls_back_to_template_before_bootstrap(session):
    """No workspace/seed has run at all yet - every existing caller (and
    every pre-existing test) must keep working unchanged."""
    profile = get_buyer_profile_dataclass(session, "nesten_homes")
    assert profile is not None
    assert profile.target_unit_min == NESTEN_HOMES.target_unit_min


def test_get_buyer_profile_dataclass_prefers_the_persisted_mandate_once_seeded(session):
    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)
    mandate = _mandate_for(session, "nesten_homes")
    mandate.target_unit_max = 999
    session.commit()

    profile = get_buyer_profile_dataclass(session, "nesten_homes")
    assert profile.target_unit_max == 999  # the edited, persisted value - not the code template's 100


def test_list_active_buyer_options_falls_back_before_bootstrap(session):
    options = list_active_buyer_options(session)
    assert [key for key, _ in options] == list(BUYER_PROFILE_ORDER)


def test_list_active_buyer_options_reads_persisted_rows_after_bootstrap(session):
    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)
    options = list_active_buyer_options(session)
    assert [key for key, _ in options] == list(BUYER_PROFILE_ORDER)


def test_list_active_buyer_options_sorts_by_canonical_order_not_row_creation_order(session):
    """Regression test for a real bug this Phase A migration produced and
    caught during its own production verification: the one-time legacy-
    BuyerProfile backfill reads the legacy table with no ORDER BY, so the
    NEW Buyer rows' own auto-incrementing ids do not necessarily land in
    BUYER_PROFILE_ORDER's own sequence. list_active_buyer_options must sort
    by each buyer_key's own canonical position, never by Buyer.id, so the
    selector's visible order survives however the rows were actually
    created. Built here by creating the four Buyers in the REVERSE of
    BUYER_PROFILE_ORDER on purpose, proving the fix does not merely happen
    to work when creation order already matches."""
    workspace = resolve_default_workspace(session)
    for key in reversed(BUYER_PROFILE_ORDER):
        template = BUYER_PROFILES[key]
        buyer = Buyer(workspace_id=workspace.id, buyer_key=key, display_name=template.display_name, buyer_type=template.buyer_type)
        session.add(buyer)
        session.flush()
        session.add(BuyerMandate(
            buyer_id=buyer.id, mandate_key=DEFAULT_MANDATE_KEY, display_name=template.display_name,
            primary_requirement=template.primary_requirement, target_unit_min=template.target_unit_min,
            target_unit_max=template.target_unit_max, scale_metric=template.scale_metric,
            accepted_planning_states=",".join(sorted(template.accepted_planning_states)),
            treats_no_activity_as_positive=template.treats_no_activity_as_positive,
            large_allocation_is_self_qualifying=template.large_allocation_is_self_qualifying,
            specialist_development_is_exclusion=template.specialist_development_is_exclusion,
            wholly_affordable_is_exclusion=template.wholly_affordable_is_exclusion,
            below_minimum_scale_is_exclusion=template.below_minimum_scale_is_exclusion,
        ))
    session.commit()

    options = list_active_buyer_options(session)
    assert [key for key, _ in options] == list(BUYER_PROFILE_ORDER)  # canonical order, NOT reversed creation order


# --- Buyer Mandate fingerprint -----------------------------------------------

def test_fingerprint_changes_when_a_matching_field_changes():
    from dataclasses import replace
    fp_before = compute_buyer_mandate_fingerprint(NESTEN_HOMES)
    changed = replace(NESTEN_HOMES, target_unit_max=150)
    fp_after = compute_buyer_mandate_fingerprint(changed)
    assert fp_before != fp_after


def test_fingerprint_unchanged_by_display_only_metadata():
    from dataclasses import replace
    fp_before = compute_buyer_mandate_fingerprint(NESTEN_HOMES)
    changed = replace(NESTEN_HOMES, display_name="Nesten Homes (renamed)", notes="completely different notes text")
    fp_after = compute_buyer_mandate_fingerprint(changed)
    assert fp_before == fp_after


# --- Architecture test (Phase A brief, Section 33): fingerprint is now
# genuinely mandate-scoped, not buyer-identity-scoped -------------------------

def test_buyer_identity_change_leaves_mandate_fingerprint_unchanged(session):
    """Proves Section 33's own required property structurally, not just by
    convention: changing a Buyer's own display_name/buyer_type (its
    identity) must never move its BuyerMandate's own matching_fingerprint,
    because the fingerprint function reads only fields declared on
    BuyerMandate/consumed by assess_buyer_fit - a Buyer's identity fields
    are never even passed into it except via BuyerMandatePolicy.key/
    display_name/buyer_type, all three of which compute_buyer_mandate_
    fingerprint's own field list (see its source) deliberately excludes."""
    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)
    mandate = _mandate_for(session, "nesten_homes")
    run_buyer_onboarding_baseline(session, mandate)
    fingerprint_before = mandate.matching_fingerprint

    buyer = session.execute(select(Buyer).where(Buyer.buyer_key == "nesten_homes")).scalars().first()
    buyer.display_name = "Nesten Homes Ltd"
    buyer.buyer_type = "Renamed regional housebuilder"
    session.commit()

    assert is_buyer_mandate_baseline_stale(mandate) is False
    assert compute_buyer_mandate_fingerprint(mandate_to_policy(mandate)) == fingerprint_before


def test_mandate_strategy_change_changes_the_fingerprint(session):
    """The other half of Section 33: a genuine strategy change on the
    mandate itself must make the baseline stale, exactly as a legacy
    BuyerProfile edit always did."""
    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)
    mandate = _mandate_for(session, "nesten_homes")
    run_buyer_onboarding_baseline(session, mandate)
    assert is_buyer_mandate_baseline_stale(mandate) is False

    mandate.target_unit_max = 40  # a genuine mandate change
    session.commit()
    assert is_buyer_mandate_baseline_stale(mandate) is True


def test_matching_policy_version_bump_makes_baseline_stale_without_mandate_change(session, monkeypatch):
    """Agent-Ready Fact Foundation, BUYER_MATCHING_POLICY_VERSION 3 -> 4:
    proves the version constant does exactly what its own module comment
    claims - invalidates every mandate's baseline the moment it changes,
    with ZERO mandate strategy field touched. Simulates "persisted under
    v3" by monkeypatching the constant (as seen by both the fingerprint
    function and the store module's own import of it) down to 3, onboarding
    normally, then restoring the real, current value (4) and asserting the
    now-stale baseline is detected purely from the version change."""
    import app.policy.buyer_matching as buyer_matching_module
    import app.policy.buyer_profile_store as buyer_profile_store_module

    real_version = buyer_matching_module.BUYER_MATCHING_POLICY_VERSION
    assert real_version == 4, "this test assumes the current production version is 4"

    monkeypatch.setattr(buyer_matching_module, "BUYER_MATCHING_POLICY_VERSION", 3)
    monkeypatch.setattr(buyer_profile_store_module, "BUYER_MATCHING_POLICY_VERSION", 3)

    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)
    mandate = _mandate_for(session, "nesten_homes")
    run_buyer_onboarding_baseline(session, mandate)
    fingerprint_under_v3 = mandate.matching_fingerprint
    assert is_buyer_mandate_baseline_stale(mandate) is False

    monkeypatch.setattr(buyer_matching_module, "BUYER_MATCHING_POLICY_VERSION", real_version)
    monkeypatch.setattr(buyer_profile_store_module, "BUYER_MATCHING_POLICY_VERSION", real_version)

    assert is_buyer_mandate_baseline_stale(mandate) is True
    assert compute_buyer_mandate_fingerprint(mandate_to_policy(mandate)) != fingerprint_under_v3
    # No mandate strategy field was touched anywhere in this test.


# --- Onboarding baseline -----------------------------------------------------

def _make_plan(session) -> LocalPlan:
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Local Plan", status="proposed_submission", raw_status="proposed_submission")
    session.add(plan)
    session.commit()
    return plan


def _make_allocation(session, plan_id, **kwargs) -> LocalPlanSite:
    allocation = LocalPlanSite(
        council_code="testcouncil", local_plan_id=plan_id, policy_reference=kwargs.pop("policy_reference", "AN1"),
        site_name=kwargs.pop("site_name", "Test Allocation"), plan_name="Test Local Plan", plan_status="proposed_submission",
        matched_site_id=None, **kwargs,
    )
    session.add(allocation)
    session.commit()
    return allocation


def test_onboarding_reviews_the_current_universe_and_produces_counts(session):
    plan = _make_plan(session)
    for i in range(3):
        _make_allocation(session, plan.id, site_name=f"Allocation {i}", policy_reference=f"REF-{i}", minimum_dwellings=60 + i * 10)

    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)
    mandate = _mandate_for(session, "nesten_homes")

    result = run_buyer_onboarding_baseline(session, mandate)
    assert result.opportunities_reviewed >= 3
    assert result.strong_fit + result.not_suitable + result.insufficient_evidence == result.opportunities_reviewed
    assert mandate.onboarding_completed_at is not None
    assert mandate.matching_fingerprint == compute_buyer_mandate_fingerprint(mandate_to_policy(mandate))
    assert mandate.onboarding_summary == result.summary_line
    assert "reviewed=" in result.summary_line and "strong_fit=" in result.summary_line


def test_onboarding_baseline_is_not_stale_immediately_after_running(session):
    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)
    mandate = _mandate_for(session, "nesten_homes")
    assert is_buyer_mandate_baseline_stale(mandate) is True  # never onboarded yet
    run_buyer_onboarding_baseline(session, mandate)
    assert is_buyer_mandate_baseline_stale(mandate) is False


def test_mandate_change_makes_the_baseline_stale_without_touching_opportunities(session):
    """Gate 1 brief, Section 19/20 (unchanged by Phase A): editing a
    buyer's own mandate must mark ITS OWN baseline stale, and must NEVER
    cause any global opportunity to be (re)classified NEW - a mandate
    change is a different trigger from a new opportunity, and this module
    has no mechanism that could even touch OpportunityMonitoringState."""
    plan = _make_plan(session)
    _make_allocation(session, plan.id, site_name="Untouched Allocation", minimum_dwellings=80)
    sync_opportunity_monitoring_state(session)
    from app.db.models import OpportunityMonitoringState
    states_before = {s.opportunity_id: s.last_change_classification for s in session.execute(select(OpportunityMonitoringState)).scalars()}

    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)
    mandate = _mandate_for(session, "nesten_homes")
    run_buyer_onboarding_baseline(session, mandate)
    assert is_buyer_mandate_baseline_stale(mandate) is False

    mandate.target_unit_max = 40  # a genuine mandate change
    session.commit()
    assert is_buyer_mandate_baseline_stale(mandate) is True

    # Global opportunity state is completely untouched by the mandate edit.
    states_after = {s.opportunity_id: s.last_change_classification for s in session.execute(select(OpportunityMonitoringState)).scalars()}
    assert states_before == states_after


def test_new_buyer_does_not_report_existing_opportunities_as_new(session):
    """Required acceptance scenario E (unchanged by Phase A): existing
    opportunities must be HISTORICAL baseline for a newly onboarded
    mandate, never later reported as newly discovered merely because
    monitoring has just started."""
    from app.db.models import OpportunityMonitoringState
    from app.reporting.opportunity_change import BASELINE_EXISTING, NEW

    plan = _make_plan(session)
    for i in range(3):
        _make_allocation(session, plan.id, site_name=f"Pre-existing {i}", policy_reference=f"PRE-{i}", minimum_dwellings=70)
    sync_opportunity_monitoring_state(session)  # first-ever sync - these become BASELINE_EXISTING, not NEW

    states = session.execute(select(OpportunityMonitoringState)).scalars().all()
    assert len(states) >= 3
    assert all(s.last_change_classification == BASELINE_EXISTING for s in states)
    assert not any(s.last_change_classification == NEW for s in states)

    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)
    mandate = _mandate_for(session, "nesten_homes")
    run_buyer_onboarding_baseline(session, mandate)

    new_for_buyer = session.execute(
        select(OpportunityMonitoringState).where(OpportunityMonitoringState.first_seen_at > mandate.onboarding_completed_at)
    ).scalars().all()
    assert new_for_buyer == []  # nothing pre-existing is "new for this buyer"


def test_bootstrap_is_idempotent_end_to_end(session):
    """Scenario A (existing database + first deployment): one call sets
    everything up - including establishing the GLOBAL opportunity baseline
    BEFORE buyer onboarding, per the canonical sequence - and a second
    call changes nothing further."""
    from app.db.models import OpportunityMonitoringState
    from app.reporting.opportunity_change import BASELINE_EXISTING

    plan = _make_plan(session)
    for i in range(3):
        _make_allocation(session, plan.id, site_name=f"Already In The Database {i}", policy_reference=f"EXIST-{i}", minimum_dwellings=80)

    first = bootstrap_acquisition_monitoring(session)
    assert len(first["profiles_onboarded_this_run"]) == 4
    assert first["global_opportunity_baseline"]["baseline_existing"] >= 3
    assert first["global_opportunity_baseline"]["new"] == 0

    states = session.execute(select(OpportunityMonitoringState)).scalars().all()
    assert states and all(s.last_change_classification == BASELINE_EXISTING for s in states)

    second = bootstrap_acquisition_monitoring(session)
    assert second["profiles_onboarded_this_run"] == []  # every baseline already current - no re-scan
    assert second["global_opportunity_baseline"]["baseline_existing"] == 0  # table was no longer empty
    assert second["global_opportunity_baseline"]["new"] == 0
    assert second["global_opportunity_baseline"]["materially_changed"] == 0
    assert second["profiles_total"] == 4
    assert len(session.execute(select(Workspace)).scalars().all()) == 1
    assert len(session.execute(select(Buyer)).scalars().all()) == 4
    assert len(session.execute(select(BuyerMandate)).scalars().all()) == 4


def test_a_fifth_buyer_added_later_also_treats_existing_opportunities_as_baseline(session):
    """Scenario E via the real deployment entry point: after first
    deployment has already run (existing opportunities baselined, four
    buyers onboarded), a fifth Buyer + BuyerMandate seeded afterward must
    still review the SAME pre-existing opportunities as historical
    onboarding context, never as newly discovered."""
    plan = _make_plan(session)
    _make_allocation(session, plan.id, site_name="Pre-existing For Fifth Buyer", minimum_dwellings=90)
    bootstrap_acquisition_monitoring(session)  # first deployment - baselines everything, onboards the four pilots

    workspace = resolve_default_workspace(session)
    fifth_buyer = Buyer(workspace_id=workspace.id, buyer_key="fifth_pilot_buyer", display_name="Fifth Pilot Buyer", buyer_type=NESTEN_HOMES.buyer_type)
    session.add(fifth_buyer)
    session.flush()
    fifth_mandate = BuyerMandate(
        buyer_id=fifth_buyer.id, mandate_key=DEFAULT_MANDATE_KEY, display_name="Fifth Pilot Buyer",
        primary_requirement=NESTEN_HOMES.primary_requirement, target_unit_min=NESTEN_HOMES.target_unit_min,
        target_unit_max=NESTEN_HOMES.target_unit_max, scale_metric=NESTEN_HOMES.scale_metric,
        accepted_planning_states=",".join(sorted(NESTEN_HOMES.accepted_planning_states)),
        treats_no_activity_as_positive=NESTEN_HOMES.treats_no_activity_as_positive,
        large_allocation_is_self_qualifying=NESTEN_HOMES.large_allocation_is_self_qualifying,
        specialist_development_is_exclusion=NESTEN_HOMES.specialist_development_is_exclusion,
        wholly_affordable_is_exclusion=NESTEN_HOMES.wholly_affordable_is_exclusion,
        below_minimum_scale_is_exclusion=NESTEN_HOMES.below_minimum_scale_is_exclusion,
    )
    session.add(fifth_mandate)
    session.commit()
    assert is_buyer_mandate_baseline_stale(fifth_mandate) is True

    result = bootstrap_acquisition_monitoring(session)
    assert "fifth_pilot_buyer" in result["profiles_onboarded_this_run"]
    assert result["global_opportunity_baseline"]["new"] == 0  # the pre-existing opportunity is still not "new"
    assert fifth_mandate.onboarding_completed_at is not None
    assert fifth_mandate.onboarding_summary is not None and "reviewed=" in fifth_mandate.onboarding_summary


# --- Architecture test (Phase A brief, Section 31): one Buyer, two mandates --

def test_one_buyer_can_own_two_mandates(session):
    """Structural proof the schema allows what the legacy BuyerProfile
    row (profile_key unique per workspace) never could: a single Buyer
    owning more than one BuyerMandate, each independently identified and
    independently matchable, without duplicating the buyer's own identity
    fields. Phase B fields (geography, acquisition type, ...) are
    deliberately NOT introduced here - both mandates use only fields that
    already exist today, differing only in unit range, exactly as the
    Phase A brief's own example (GM_CONSENTED_50_100 vs CHESHIRE_
    STRATEGIC_100_250) describes conceptually."""
    workspace = resolve_default_workspace(session)
    buyer = Buyer(workspace_id=workspace.id, buyer_key="nesten_homes_test", display_name="Nesten Homes", buyer_type=NESTEN_HOMES.buyer_type)
    session.add(buyer)
    session.flush()

    mandate_a = BuyerMandate(
        buyer_id=buyer.id, mandate_key="gm_consented_50_100", display_name="GM Consented 50-100",
        primary_requirement=NESTEN_HOMES.primary_requirement, target_unit_min=50, target_unit_max=100,
        scale_metric=NESTEN_HOMES.scale_metric, accepted_planning_states=",".join(sorted(NESTEN_HOMES.accepted_planning_states)),
        treats_no_activity_as_positive=False, large_allocation_is_self_qualifying=False,
        specialist_development_is_exclusion=True, wholly_affordable_is_exclusion=True, below_minimum_scale_is_exclusion=False,
    )
    mandate_b = BuyerMandate(
        buyer_id=buyer.id, mandate_key="cheshire_strategic_100_250", display_name="Cheshire Strategic 100-250",
        primary_requirement="Large residential strategic-land opportunities", target_unit_min=100, target_unit_max=250,
        scale_metric=NESTEN_HOMES.scale_metric, accepted_planning_states=",".join(sorted(["adopted_allocation", "emerging_allocation"])),
        treats_no_activity_as_positive=True, large_allocation_is_self_qualifying=True,
        specialist_development_is_exclusion=True, wholly_affordable_is_exclusion=True, below_minimum_scale_is_exclusion=False,
    )
    session.add_all([mandate_a, mandate_b])
    session.commit()  # must not raise - both share buyer_id, mandate_key differs

    reloaded = session.execute(select(BuyerMandate).where(BuyerMandate.buyer_id == buyer.id)).scalars().all()
    assert {m.mandate_key for m in reloaded} == {"gm_consented_50_100", "cheshire_strategic_100_250"}
    assert all(m.buyer_id == buyer.id for m in reloaded)

    # Independently matchable - policy A's own range excludes a 150-unit
    # scheme that policy B's own range happily includes.
    policy_a, policy_b = mandate_to_policy(mandate_a), mandate_to_policy(mandate_b)
    assert policy_a.target_unit_max == 100
    assert policy_b.target_unit_max == 250


def test_duplicate_mandate_key_within_the_same_buyer_is_rejected(session):
    """The uniqueness constraint's own other half: mandate_key must still
    be unique WITHIN one buyer - this is not an unconstrained free-for-all,
    only no longer constrained at the workspace level."""
    from sqlalchemy.exc import IntegrityError

    workspace = resolve_default_workspace(session)
    buyer = Buyer(workspace_id=workspace.id, buyer_key="dup_test_buyer", display_name="Dup Test Buyer", buyer_type="Test")
    session.add(buyer)
    session.flush()
    session.add(BuyerMandate(
        buyer_id=buyer.id, mandate_key=DEFAULT_MANDATE_KEY, display_name="A", primary_requirement="x",
        target_unit_min=1, target_unit_max=2, scale_metric="total_units", accepted_planning_states="",
        treats_no_activity_as_positive=False, large_allocation_is_self_qualifying=False,
        specialist_development_is_exclusion=True, wholly_affordable_is_exclusion=True, below_minimum_scale_is_exclusion=False,
    ))
    session.commit()

    session.add(BuyerMandate(
        buyer_id=buyer.id, mandate_key=DEFAULT_MANDATE_KEY, display_name="B", primary_requirement="y",
        target_unit_min=3, target_unit_max=4, scale_metric="total_units", accepted_planning_states="",
        treats_no_activity_as_positive=False, large_allocation_is_self_qualifying=False,
        specialist_development_is_exclusion=True, wholly_affordable_is_exclusion=True, below_minimum_scale_is_exclusion=False,
    ))
    try:
        session.commit()
        assert False, "expected an IntegrityError for a duplicate (buyer_id, mandate_key)"
    except IntegrityError:
        session.rollback()


# --- Architecture test (Phase A brief, Section 32): workspace isolation -----

def test_equivalent_buyer_and_mandate_keys_coexist_across_workspaces(session):
    """Workspace A and Workspace B may each have their own "nesten_homes"
    Buyer with its own "default" BuyerMandate, entirely independently -
    Buyer.buyer_key is unique per WORKSPACE, and BuyerMandate.mandate_key
    is unique per BUYER, so two different buyer rows (even sharing the
    identical key string, in different workspaces) never collide."""
    ws_a = Workspace(name="Workspace A", status="active")
    ws_b = Workspace(name="Workspace B", status="active")
    session.add_all([ws_a, ws_b])
    session.flush()

    buyer_a = Buyer(workspace_id=ws_a.id, buyer_key="nesten_homes", display_name="Nesten Homes (A)", buyer_type=NESTEN_HOMES.buyer_type)
    buyer_b = Buyer(workspace_id=ws_b.id, buyer_key="nesten_homes", display_name="Nesten Homes (B)", buyer_type=NESTEN_HOMES.buyer_type)
    session.add_all([buyer_a, buyer_b])
    session.flush()

    mandate_a = BuyerMandate(
        buyer_id=buyer_a.id, mandate_key=DEFAULT_MANDATE_KEY, display_name="Nesten Homes (A)", primary_requirement="x",
        target_unit_min=50, target_unit_max=100, scale_metric="total_units", accepted_planning_states="",
        treats_no_activity_as_positive=False, large_allocation_is_self_qualifying=False,
        specialist_development_is_exclusion=True, wholly_affordable_is_exclusion=True, below_minimum_scale_is_exclusion=False,
    )
    mandate_b = BuyerMandate(
        buyer_id=buyer_b.id, mandate_key=DEFAULT_MANDATE_KEY, display_name="Nesten Homes (B)", primary_requirement="y",
        target_unit_min=200, target_unit_max=500, scale_metric="total_units", accepted_planning_states="",
        treats_no_activity_as_positive=False, large_allocation_is_self_qualifying=False,
        specialist_development_is_exclusion=True, wholly_affordable_is_exclusion=True, below_minimum_scale_is_exclusion=False,
    )
    session.add_all([mandate_a, mandate_b])
    session.commit()  # must not raise

    assert session.execute(select(Buyer).where(Buyer.workspace_id == ws_a.id)).scalars().all() == [buyer_a]
    assert session.execute(select(Buyer).where(Buyer.workspace_id == ws_b.id)).scalars().all() == [buyer_b]
    assert mandate_to_policy(mandate_a).target_unit_max == 100
    assert mandate_to_policy(mandate_b).target_unit_max == 500


def test_duplicate_buyer_key_within_the_same_workspace_is_rejected(session):
    from sqlalchemy.exc import IntegrityError

    workspace = resolve_default_workspace(session)
    session.add(Buyer(workspace_id=workspace.id, buyer_key="dup_buyer", display_name="A", buyer_type="Test"))
    session.commit()
    session.add(Buyer(workspace_id=workspace.id, buyer_key="dup_buyer", display_name="B", buyer_type="Test"))
    try:
        session.commit()
        assert False, "expected an IntegrityError for a duplicate (workspace_id, buyer_key)"
    except IntegrityError:
        session.rollback()


# --- Legacy BuyerProfile -> Buyer/BuyerMandate migration ---------------------

def _make_legacy_profile(session, workspace_id: int, key: str, **overrides) -> LegacyBuyerProfile:
    template = BUYER_PROFILES[key]
    fields = dict(
        workspace_id=workspace_id, profile_key=key, display_name=template.display_name, buyer_type=template.buyer_type,
        primary_requirement=template.primary_requirement, target_unit_min=template.target_unit_min,
        target_unit_max=template.target_unit_max, scale_metric=template.scale_metric,
        accepted_planning_states=",".join(sorted(template.accepted_planning_states)),
        treats_no_activity_as_positive=template.treats_no_activity_as_positive,
        large_allocation_is_self_qualifying=template.large_allocation_is_self_qualifying,
        specialist_development_is_exclusion=template.specialist_development_is_exclusion,
        wholly_affordable_is_exclusion=template.wholly_affordable_is_exclusion,
        below_minimum_scale_is_exclusion=template.below_minimum_scale_is_exclusion,
        notes=template.notes, source_template_key=key,
    )
    fields.update(overrides)
    record = LegacyBuyerProfile(**fields)
    session.add(record)
    session.commit()
    return record


def test_migration_dry_run_makes_zero_database_changes(session):
    workspace = resolve_default_workspace(session)
    _make_legacy_profile(session, workspace.id, "nesten_homes")

    report = migrate_buyer_profiles_to_mandates(session, dry_run=True)

    assert report["dry_run"] is True
    assert report["legacy_rows_found"] == 1
    assert report["buyers_created"] == 1
    assert report["mandates_created"] == 1
    assert session.execute(select(Buyer)).scalars().all() == []
    assert session.execute(select(BuyerMandate)).scalars().all() == []


def test_migration_execute_creates_a_buyer_and_mandate_per_legacy_row(session):
    workspace = resolve_default_workspace(session)
    for key in BUYER_PROFILE_ORDER:
        _make_legacy_profile(session, workspace.id, key)

    report = migrate_buyer_profiles_to_mandates(session, dry_run=False)

    assert report["dry_run"] is False
    assert report["legacy_rows_found"] == 4
    assert report["buyers_created"] == 4
    assert report["mandates_created"] == 4
    assert report["fingerprint_mismatches"] == []
    assert len(session.execute(select(Buyer)).scalars().all()) == 4
    assert len(session.execute(select(BuyerMandate)).scalars().all()) == 4
    # Legacy rows are completely untouched.
    assert len(session.execute(select(LegacyBuyerProfile)).scalars().all()) == 4


def test_migration_is_idempotent(session):
    workspace = resolve_default_workspace(session)
    _make_legacy_profile(session, workspace.id, "nesten_homes")

    first = migrate_buyer_profiles_to_mandates(session, dry_run=False)
    second = migrate_buyer_profiles_to_mandates(session, dry_run=False)

    assert first["buyers_created"] == 1 and first["mandates_created"] == 1
    assert second["buyers_created"] == 0 and second["mandates_created"] == 0
    assert second["buyers_already_present"] == 1 and second["mandates_already_present"] == 1
    assert len(session.execute(select(Buyer)).scalars().all()) == 1
    assert len(session.execute(select(BuyerMandate)).scalars().all()) == 1


def test_migration_does_not_hardcode_exactly_four_rows(session):
    """Phase A brief, Section 13: 'Do NOT hard-code the migration to
    exactly four rows if production data could contain more.' Proven with
    five legacy rows (the four templates plus one extra, hand-built like a
    genuinely-onboarded fifth buyer would be)."""
    workspace = resolve_default_workspace(session)
    for key in BUYER_PROFILE_ORDER:
        _make_legacy_profile(session, workspace.id, key)
    _make_legacy_profile(session, workspace.id, "nesten_homes", profile_key="fifth_pilot_buyer", display_name="Fifth Pilot Buyer")

    report = migrate_buyer_profiles_to_mandates(session, dry_run=False)

    assert report["legacy_rows_found"] == 5
    assert report["buyers_created"] == 5
    assert report["mandates_created"] == 5


def test_migration_preserves_onboarding_state_and_recomputes_a_matching_fingerprint(session):
    workspace = resolve_default_workspace(session)
    onboarded_at = dt.datetime(2026, 9, 7, 19, 11, 42, tzinfo=dt.timezone.utc)
    legacy = _make_legacy_profile(
        session, workspace.id, "housing_association",
        onboarding_completed_at=onboarded_at, onboarding_summary="reviewed=255 strong_fit=1 not_suitable=16 insufficient_evidence=238 investigative_exceptions=0",
    )
    # A fingerprint computed the way Phase A itself would have computed it
    # (frozen to the pre-Phase-B1 field set) - a REAL legacy row's own
    # matching_fingerprint predates B1's wider fingerprint schema, so this
    # must be built from _phase_a_only_fingerprint, never today's full
    # compute_buyer_mandate_fingerprint.
    from app.policy.buyer_profiles import HOUSING_ASSOCIATION
    from app.policy.buyer_profile_store import _phase_a_only_fingerprint
    legacy.matching_fingerprint = _phase_a_only_fingerprint(HOUSING_ASSOCIATION)
    session.commit()

    report = migrate_buyer_profiles_to_mandates(session, dry_run=False)
    assert report["fingerprint_mismatches"] == []

    mandate = _mandate_for(session, "housing_association")
    assert mandate.onboarding_completed_at.replace(tzinfo=None) == onboarded_at.replace(tzinfo=None)
    assert mandate.onboarding_summary == legacy.onboarding_summary
    # The migrated mandate's own PERSISTED fingerprint is always the
    # CURRENT, full (post-Phase-B1) value - not literally equal to the
    # legacy row's pre-B1 value, but internally consistent with the
    # mandate's own (now B1-populated) fields.
    assert mandate.matching_fingerprint == compute_buyer_mandate_fingerprint(mandate_to_policy(mandate))


# --- Buyer Mandate V2, Phase B1: structured mandate domain expansion -------

def _make_pre_b1_mandate(session, workspace, buyer_key: str) -> BuyerMandate:
    """Simulates a mandate exactly as Phase A left it - seeded before
    Phase B1's own columns existed. seed_default_buyer_profiles now always
    populates B1 fields on creation, so this test helper constructs the
    Buyer + BuyerMandate directly, leaving the five B1 columns genuinely
    NULL, to exercise the ADD-COLUMN-then-backfill scenario Phase B1 must
    actually handle."""
    template = BUYER_PROFILES[buyer_key]
    buyer = Buyer(workspace_id=workspace.id, buyer_key=buyer_key, display_name=template.display_name, buyer_type=template.buyer_type)
    session.add(buyer)
    session.flush()
    mandate = BuyerMandate(
        buyer_id=buyer.id, mandate_key=DEFAULT_MANDATE_KEY, display_name=template.display_name,
        primary_requirement=template.primary_requirement, target_unit_min=template.target_unit_min,
        target_unit_max=template.target_unit_max, scale_metric=template.scale_metric,
        accepted_planning_states=",".join(sorted(template.accepted_planning_states)),
        treats_no_activity_as_positive=template.treats_no_activity_as_positive,
        large_allocation_is_self_qualifying=template.large_allocation_is_self_qualifying,
        specialist_development_is_exclusion=template.specialist_development_is_exclusion,
        wholly_affordable_is_exclusion=template.wholly_affordable_is_exclusion,
        below_minimum_scale_is_exclusion=template.below_minimum_scale_is_exclusion,
        notes=template.notes, source_template_key=buyer_key,
        # Deliberately omitted: geography_scope/geography_councils/
        # acquisition_types/development_state_appetite/control_appetite -
        # stay NULL, exactly like a real pre-B1 row after a bare ALTER
        # TABLE ADD COLUMN.
    )
    session.add(mandate)
    session.commit()
    return mandate


def test_seeding_backfills_b1_fields_onto_a_pre_existing_mandate(session):
    workspace = resolve_default_workspace(session)
    pre_b1 = _make_pre_b1_mandate(session, workspace, "nesten_homes")
    assert pre_b1.geography_scope is None  # confirms the fixture really simulates a pre-B1 row

    seed_default_buyer_profiles(session, workspace)

    reloaded = _mandate_for(session, "nesten_homes")
    assert reloaded.geography_scope == GEOGRAPHY_ALL_CURRENT_COVERAGE
    assert reloaded.acquisition_types == "LAND_SITE_ACQUISITION"
    assert reloaded.development_state_appetite == "UNCOMMENCED_PREFERRED"
    assert reloaded.control_appetite == UNRESOLVED_OWNERSHIP_INVESTIGATABLE


def test_reseeding_never_overwrites_an_edited_b1_field(session):
    """Phase B1 brief, Section 32: 'An edited B1 field must survive
    reseeding.' Simulates a user (or a future Phase B3 UI) editing a
    mandate's own geography after the B1 backfill has already run once -
    a second reseed call must leave that edit completely untouched."""
    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)  # first seed - B1 fields populated from the template

    mandate = _mandate_for(session, "nesten_homes")
    mandate.geography_scope = GEOGRAPHY_COUNCILS
    mandate.geography_councils = "trafford,bury"
    session.commit()

    seed_default_buyer_profiles(session, workspace)  # rerun - must not clobber the edit

    reloaded = _mandate_for(session, "nesten_homes")
    assert reloaded.geography_scope == GEOGRAPHY_COUNCILS
    assert reloaded.geography_councils == "trafford,bury"


def test_backfill_is_idempotent_and_never_duplicates(session):
    workspace = resolve_default_workspace(session)
    for key in BUYER_PROFILE_ORDER:
        _make_pre_b1_mandate(session, workspace, key)

    first = backfill_buyer_mandate_b1_defaults(session, dry_run=False)
    second = backfill_buyer_mandate_b1_defaults(session, dry_run=False)

    assert all(info["needs_backfill"] for info in first["mandates"].values())
    assert not any(info["needs_backfill"] for info in second["mandates"].values())
    assert len(session.execute(select(BuyerMandate)).scalars().all()) == 4  # no duplicate rows created


def test_backfill_dry_run_makes_zero_database_changes(session):
    workspace = resolve_default_workspace(session)
    _make_pre_b1_mandate(session, workspace, "nesten_homes")

    report = backfill_buyer_mandate_b1_defaults(session, dry_run=True)

    assert report["dry_run"] is True
    assert report["mandates"]["nesten_homes"]["needs_backfill"] is True
    assert "proposed_fields" in report["mandates"]["nesten_homes"]
    reloaded = _mandate_for(session, "nesten_homes")
    assert reloaded.geography_scope is None  # still untouched


# --- Architecture test (Phase B1 brief, Section 29): fingerprint baseline
# migration must NOT trigger a wasted re-onboarding scan -------------------

def test_b1_backfill_on_an_already_onboarded_mandate_refreshes_fingerprint_without_reonboarding(session):
    """The core Section 29 requirement: adding new matching-relevant
    fields naturally changes an existing mandate's own fingerprint once -
    but B1 does not change assess_buyer_fit's own output at all, so that
    change must be applied as a direct fingerprint refresh (a "baseline
    migration"), never by re-running the full, expensive opportunity-
    universe scan a genuine strategy change would warrant. Proven here by
    constructing a pre-B1 mandate that is ALREADY onboarded (has its own
    real matching_fingerprint/onboarding_completed_at/onboarding_summary,
    exactly like production's four Phase A mandates), then confirming the
    backfill (a) makes it non-stale immediately, (b) changes its
    fingerprint, and (c) leaves onboarding_completed_at/onboarding_summary
    completely untouched, proving no re-scan occurred."""
    workspace = resolve_default_workspace(session)
    mandate = _make_pre_b1_mandate(session, workspace, "nesten_homes")

    from app.policy.buyer_profile_store import _phase_a_only_fingerprint
    template = BUYER_PROFILES["nesten_homes"]
    pre_b1_fingerprint = _phase_a_only_fingerprint(template)
    onboarded_at = dt.datetime(2026, 9, 7, 19, 11, 47, tzinfo=dt.timezone.utc)
    mandate.matching_fingerprint = pre_b1_fingerprint
    mandate.onboarding_completed_at = onboarded_at
    mandate.onboarding_summary = "reviewed=255 strong_fit=2 not_suitable=5 insufficient_evidence=248 investigative_exceptions=85"
    session.commit()

    seed_default_buyer_profiles(session, workspace)  # this is what the backfill script actually calls

    reloaded = _mandate_for(session, "nesten_homes")
    # (a) not stale immediately - no re-onboarding was needed/triggered.
    assert is_buyer_mandate_baseline_stale(reloaded) is False
    # (b) fingerprint changed (now computed under the full, B1-inclusive
    # field set) - and is internally self-consistent.
    assert reloaded.matching_fingerprint != pre_b1_fingerprint
    assert reloaded.matching_fingerprint == compute_buyer_mandate_fingerprint(mandate_to_policy(reloaded))
    # (c) onboarding_completed_at/onboarding_summary are UNTOUCHED - proof
    # no opportunity-universe scan ran (run_buyer_onboarding_baseline would
    # have updated both to a fresh timestamp/summary).
    assert reloaded.onboarding_completed_at.replace(tzinfo=None) == onboarded_at.replace(tzinfo=None)
    assert reloaded.onboarding_summary == "reviewed=255 strong_fit=2 not_suitable=5 insufficient_evidence=248 investigative_exceptions=85"


def test_bootstrap_does_not_reonboard_solely_because_b1_fields_were_added(session):
    """End-to-end proof via the real production entry point
    (bootstrap_acquisition_monitoring): a mandate that was already
    onboarded before B1, once B1's backfill runs (which bootstrap's own
    seed_default_buyer_profiles call now performs automatically), must NOT
    appear in profiles_onboarded_this_run merely because five new columns
    were populated - onboarding is reserved for a GENUINE strategy change
    or first-time onboarding, never a structural-field backfill."""
    workspace = resolve_default_workspace(session)
    mandate = _make_pre_b1_mandate(session, workspace, "nesten_homes")
    from app.policy.buyer_profile_store import _phase_a_only_fingerprint
    mandate.matching_fingerprint = _phase_a_only_fingerprint(BUYER_PROFILES["nesten_homes"])
    mandate.onboarding_completed_at = dt.datetime.now(dt.timezone.utc)
    mandate.onboarding_summary = "reviewed=1 strong_fit=0 not_suitable=0 insufficient_evidence=1 investigative_exceptions=0"
    session.commit()

    result = bootstrap_acquisition_monitoring(session)

    # The other three (genuinely never-onboarded) pilot mandates DO get
    # onboarded, as normal - only nesten_homes (pre-onboarded, B1-backfilled
    # in-place) is correctly excluded.
    assert "nesten_homes" not in result["profiles_onboarded_this_run"]
    assert set(result["profiles_onboarded_this_run"]) == {"strategic_land_buyer", "national_housebuilder", "housing_association"}


# --- Geography council validation (Phase B1 brief, Section 26) ------------

def test_validate_geography_councils_accepts_known_codes(session):
    session.add(Council(code="trafford", name="Trafford Council", base_url="https://example.test", date_field_mode="received", doc_system="idox"))
    session.commit()
    validate_geography_councils(session, frozenset({"trafford"}))  # must not raise


def test_validate_geography_councils_rejects_unknown_codes(session):
    session.add(Council(code="trafford", name="Trafford Council", base_url="https://example.test", date_field_mode="received", doc_system="idox"))
    session.commit()
    try:
        validate_geography_councils(session, frozenset({"trafford", "atlantis"}))
        assert False, "expected a ValueError for an unrecognised council code"
    except ValueError as e:
        assert "atlantis" in str(e)


def test_validate_geography_councils_accepts_empty_set():
    # No session needed at all - an empty set is trivially valid (nothing
    # to check) and must never attempt a query.
    validate_geography_councils(session=None, council_codes=frozenset())


# --- Behavioural-equivalence requirement (Phase B1 brief, Sections 33-34) --

def test_existing_four_mandates_behaviourally_unchanged_by_b1_fields(session):
    """The single most important Phase B1 guarantee: adding five new
    structural columns/fields must not move ANY existing buyer-fit
    conclusion by even one reason string. Compares assess_buyer_fit's
    output for all four pilot mandates, read via the live, post-B1
    get_buyer_profile_dataclass path, against the same Focus-School-shaped
    fixture tests/test_buyer_profile_persistence.py's own Phase A
    equivalence test already used - zero mismatches required."""
    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)

    site = Site(council_code="stockport", canonical_address="focus school b1", display_address="Focus School B1")
    session.add(site)
    session.flush()
    app = Application(council_code="stockport", reference="DC/085997-B1", site_id=site.id, status="Decided", decision="Granted")
    session.add(app)
    session.flush()
    si = SchemeIntelligence(
        application_id=app.id, total_units_final=82, affordable_units_final=72, affordable_percentage_final=100.0,
        affordable_missing=False, development_type="mixed_retirement_and_market_housing",
        applicant_company="Anwyl Partnerships", core_intelligence_complete=True,
    )
    session.add(si)
    session.commit()
    facts = build_planning_delivery_matching_facts(si)

    for buyer_key in BUYER_PROFILE_ORDER:
        template = BUYER_PROFILES[buyer_key]
        persisted = get_buyer_profile_dataclass(session, buyer_key)  # the live, current read path

        template_result = assess_buyer_fit(template, facts)
        persisted_result = assess_buyer_fit(persisted, facts)
        assert template_result.classification == persisted_result.classification
        assert template_result.is_investigative_exception == persisted_result.is_investigative_exception
        assert template_result.matches == persisted_result.matches
        assert template_result.does_not_match == persisted_result.does_not_match
        assert template_result.unknown == persisted_result.unknown
        assert template_result.investigate == persisted_result.investigate
