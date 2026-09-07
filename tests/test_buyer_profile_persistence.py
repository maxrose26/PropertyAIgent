"""Gate 1 (Acquisition Monitoring Substrate) - tests for app.policy.
buyer_profile_store: Workspace bootstrap, persistent BuyerProfile seeding,
the matching-relevant fingerprint, and the onboarding baseline.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from app.db.models import Application, BuyerProfile as BuyerProfileRecord, LocalPlan, LocalPlanSite, SchemeIntelligence, Site, Workspace
from app.policy.buyer_matching import INSUFFICIENT_EVIDENCE, NOT_SUITABLE, STRONG_FIT, assess_buyer_fit, build_planning_delivery_matching_facts
from app.policy.buyer_profiles import BUYER_PROFILE_ORDER, BUYER_PROFILES, NATIONAL_HOUSEBUILDER, NESTEN_HOMES
from app.policy.buyer_profile_store import (
    bootstrap_acquisition_monitoring,
    compute_buyer_profile_fingerprint,
    get_buyer_profile_dataclass,
    is_buyer_profile_baseline_stale,
    list_active_buyer_options,
    record_to_dataclass,
    resolve_default_workspace,
    run_buyer_onboarding_baseline,
    seed_default_buyer_profiles,
)
from app.reporting.opportunity_change import sync_opportunity_monitoring_state


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


# --- BuyerProfile seeding ----------------------------------------------------

def test_seed_default_buyer_profiles_creates_exactly_four(session):
    workspace = resolve_default_workspace(session)
    records = seed_default_buyer_profiles(session, workspace)
    assert len(records) == 4
    assert {r.profile_key for r in records} == set(BUYER_PROFILE_ORDER)
    assert all(r.workspace_id == workspace.id for r in records)


def test_seeding_is_idempotent_and_never_duplicates(session):
    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)
    seed_default_buyer_profiles(session, workspace)
    all_records = session.execute(select(BuyerProfileRecord).where(BuyerProfileRecord.workspace_id == workspace.id)).scalars().all()
    assert len(all_records) == 4


def test_seeding_never_overwrites_an_already_edited_value(session):
    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)
    nesten = session.execute(select(BuyerProfileRecord).where(BuyerProfileRecord.profile_key == "nesten_homes")).scalars().first()
    nesten.target_unit_max = 150  # simulate a user edit
    session.commit()

    seed_default_buyer_profiles(session, workspace)  # rerun - must not clobber the edit

    reloaded = session.execute(select(BuyerProfileRecord).where(BuyerProfileRecord.profile_key == "nesten_homes")).scalars().first()
    assert reloaded.target_unit_max == 150


def test_seeded_fields_match_the_code_template_exactly(session):
    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)
    record = session.execute(select(BuyerProfileRecord).where(BuyerProfileRecord.profile_key == "nesten_homes")).scalars().first()

    assert record.display_name == NESTEN_HOMES.display_name
    assert record.target_unit_min == NESTEN_HOMES.target_unit_min
    assert record.target_unit_max == NESTEN_HOMES.target_unit_max
    assert record.scale_metric == NESTEN_HOMES.scale_metric
    assert set(record.accepted_planning_states.split(",")) == set(NESTEN_HOMES.accepted_planning_states)
    assert record.specialist_development_is_exclusion == NESTEN_HOMES.specialist_development_is_exclusion
    assert record.wholly_affordable_is_exclusion == NESTEN_HOMES.wholly_affordable_is_exclusion
    assert record.below_minimum_scale_is_exclusion == NESTEN_HOMES.below_minimum_scale_is_exclusion
    assert record.source_template_key == "nesten_homes"


# --- Record <-> dataclass round-trip / deterministic matching preserved ----

def test_record_to_dataclass_round_trip_preserves_every_matching_field():
    from app.policy.buyer_profile_store import _template_to_record_fields

    fields = _template_to_record_fields(NATIONAL_HOUSEBUILDER, workspace_id=1)
    record = BuyerProfileRecord(**fields)
    rebuilt = record_to_dataclass(record)

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
    """The core regression guarantee for all four profiles: assess_buyer_
    fit's own output must not change one bit merely because the profile
    now comes from a persisted row instead of the in-memory template -
    Focus School's own real figures, exactly as used in test_buyer_
    matching.py's own acceptance case."""
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

    for profile_key in BUYER_PROFILE_ORDER:
        template = BUYER_PROFILES[profile_key]
        record = session.execute(select(BuyerProfileRecord).where(BuyerProfileRecord.profile_key == profile_key)).scalars().first()
        persisted = record_to_dataclass(record)

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


def test_get_buyer_profile_dataclass_prefers_the_persisted_row_once_seeded(session):
    workspace = resolve_default_workspace(session)
    seed_default_buyer_profiles(session, workspace)
    record = session.execute(select(BuyerProfileRecord).where(BuyerProfileRecord.profile_key == "nesten_homes")).scalars().first()
    record.target_unit_max = 999
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


# --- Buyer profile fingerprint ----------------------------------------------

def test_fingerprint_changes_when_a_matching_field_changes():
    from dataclasses import replace
    fp_before = compute_buyer_profile_fingerprint(NESTEN_HOMES)
    changed = replace(NESTEN_HOMES, target_unit_max=150)
    fp_after = compute_buyer_profile_fingerprint(changed)
    assert fp_before != fp_after


def test_fingerprint_unchanged_by_display_only_metadata():
    from dataclasses import replace
    fp_before = compute_buyer_profile_fingerprint(NESTEN_HOMES)
    changed = replace(NESTEN_HOMES, display_name="Nesten Homes (renamed)", notes="completely different notes text")
    fp_after = compute_buyer_profile_fingerprint(changed)
    assert fp_before == fp_after


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
    [record] = [r for r in seed_default_buyer_profiles(session, workspace) if r.profile_key == "nesten_homes"]

    result = run_buyer_onboarding_baseline(session, record)
    assert result.opportunities_reviewed >= 3
    assert result.strong_fit + result.not_suitable + result.insufficient_evidence == result.opportunities_reviewed
    assert record.onboarding_completed_at is not None
    assert record.matching_fingerprint == compute_buyer_profile_fingerprint(record_to_dataclass(record))
    assert record.onboarding_summary == result.summary_line
    assert "reviewed=" in result.summary_line and "strong_fit=" in result.summary_line


def test_onboarding_baseline_is_not_stale_immediately_after_running(session):
    workspace = resolve_default_workspace(session)
    [record] = [r for r in seed_default_buyer_profiles(session, workspace) if r.profile_key == "nesten_homes"]
    assert is_buyer_profile_baseline_stale(record) is True  # never onboarded yet
    run_buyer_onboarding_baseline(session, record)
    assert is_buyer_profile_baseline_stale(record) is False


def test_profile_change_makes_the_baseline_stale_without_touching_opportunities(session):
    """Gate 1 brief, Section 19/20: editing a buyer's own mandate must
    mark ITS OWN baseline stale, and must NEVER cause any global
    opportunity to be (re)classified NEW - a profile change is a
    different trigger from a new opportunity, and this module has no
    mechanism that could even touch OpportunityMonitoringState."""
    plan = _make_plan(session)
    _make_allocation(session, plan.id, site_name="Untouched Allocation", minimum_dwellings=80)
    sync_opportunity_monitoring_state(session)
    from app.db.models import OpportunityMonitoringState
    states_before = {s.opportunity_id: s.last_change_classification for s in session.execute(select(OpportunityMonitoringState)).scalars()}

    workspace = resolve_default_workspace(session)
    [record] = [r for r in seed_default_buyer_profiles(session, workspace) if r.profile_key == "nesten_homes"]
    run_buyer_onboarding_baseline(session, record)
    assert is_buyer_profile_baseline_stale(record) is False

    record.target_unit_max = 40  # a genuine mandate change
    session.commit()
    assert is_buyer_profile_baseline_stale(record) is True

    # Global opportunity state is completely untouched by the profile edit.
    states_after = {s.opportunity_id: s.last_change_classification for s in session.execute(select(OpportunityMonitoringState)).scalars()}
    assert states_before == states_after


def test_new_buyer_does_not_report_existing_opportunities_as_new(session):
    """Required acceptance scenario E: existing opportunities must be
    HISTORICAL baseline for a newly onboarded buyer, never later reported
    as newly discovered merely because monitoring has just started.
    Proven two ways: the definitive persisted signal (last_change_
    classification == BASELINE_EXISTING, never NEW) from the very first
    sync, and the timestamp-based query Gate 2's own future "what's new
    for this buyer" step will use as a secondary check."""
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
    [record] = [r for r in seed_default_buyer_profiles(session, workspace) if r.profile_key == "nesten_homes"]
    run_buyer_onboarding_baseline(session, record)

    new_for_buyer = session.execute(
        select(OpportunityMonitoringState).where(OpportunityMonitoringState.first_seen_at > record.onboarding_completed_at)
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
    assert len(session.execute(select(BuyerProfileRecord)).scalars().all()) == 4


def test_a_fifth_buyer_added_later_also_treats_existing_opportunities_as_baseline(session):
    """Scenario E via the real deployment entry point: after first
    deployment has already run (existing opportunities baselined, four
    profiles onboarded), a fifth Buyer Profile seeded afterward must still
    review the SAME pre-existing opportunities as historical onboarding
    context, never as newly discovered - proven by re-running bootstrap
    after adding a fifth profile row directly."""
    plan = _make_plan(session)
    _make_allocation(session, plan.id, site_name="Pre-existing For Fifth Buyer", minimum_dwellings=90)
    bootstrap_acquisition_monitoring(session)  # first deployment - baselines everything, onboards the four pilots

    workspace = resolve_default_workspace(session)
    from app.policy.buyer_profiles import NESTEN_HOMES
    from app.policy.buyer_profile_store import _template_to_record_fields
    fifth = BuyerProfileRecord(**_template_to_record_fields(NESTEN_HOMES, workspace.id))
    fifth.profile_key = "fifth_pilot_buyer"
    fifth.display_name = "Fifth Pilot Buyer"
    session.add(fifth)
    session.commit()
    assert is_buyer_profile_baseline_stale(fifth) is True

    result = bootstrap_acquisition_monitoring(session)
    assert "fifth_pilot_buyer" in result["profiles_onboarded_this_run"]
    assert result["global_opportunity_baseline"]["new"] == 0  # the pre-existing opportunity is still not "new"
    assert fifth.onboarding_completed_at is not None
    assert fifth.onboarding_summary is not None and "reviewed=" in fifth.onboarding_summary
