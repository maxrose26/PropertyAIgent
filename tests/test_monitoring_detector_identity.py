"""Stage 2.5B G1A: canonical monitoring DETECTOR identity (domain + kind) - not a string prefix of the id.

Detector identity is the class of opportunity-producing logic; a site, allocation, phase code or future scope
must never change it. These tests need no production data: they use a real session over an in-memory database
and a stubbed universe.
"""
from __future__ import annotations

import inspect

import pytest
from sqlalchemy import select

import app.reporting.opportunity_change as oc
from app.db.models import OpportunityMonitoringState
from app.policy.buyer_matching import PLANNING_DELIVERY, STRATEGIC_LAND
from app.reporting import acquisition_subjects as subjects
from app.reporting.opportunity_change import (
    BASELINE_EXISTING, NEW, UNCHANGED, UnparseableOpportunityId, opportunity_detector_identity,
    plan_opportunity_changes, sync_opportunity_monitoring_state, tracked_detector_identities,
)
from app.reporting.opportunity_universe import (
    OpportunityRecord, planning_delivery_long_pending_application_opportunity_id, planning_delivery_phase_opportunity_id,
    planning_delivery_recent_permission_opportunity_id, planning_delivery_site_opportunity_id, strategic_land_opportunity_id,
)

UNPHASED = "Whole site / unphased"


def _record(opportunity_id, opportunity_type=PLANNING_DELIVERY, **fields):
    return OpportunityRecord(opportunity_id=opportunity_id, opportunity_type=opportunity_type, matching_facts=None,
                             fingerprint_fields={"unit_count": 100, **fields})


def _stub_universe(monkeypatch, *records):
    monkeypatch.setattr(oc, "build_current_opportunity_universe", lambda session, **kw: list(records))


def _seed(session, opportunity_id):
    session.add(OpportunityMonitoringState(opportunity_id=opportunity_id, opportunity_type=PLANNING_DELIVERY,
                                           fingerprint="seed" + "0" * 60, fingerprint_fields="{}"))
    session.commit()


def _classification(session, opportunity_id):
    return session.execute(select(OpportunityMonitoringState).where(
        OpportunityMonitoringState.opportunity_id == opportunity_id)).scalars().one().last_change_classification


# --- canonical detector identity for every id shape --------------------------------------------------------------------

@pytest.mark.parametrize("opportunity_id,expected", [
    (planning_delivery_site_opportunity_id(61), "planning_delivery:site"),
    (planning_delivery_long_pending_application_opportunity_id(61), "planning_delivery:long_pending_application"),
    (planning_delivery_recent_permission_opportunity_id(61), "planning_delivery:recent_permission"),
    (planning_delivery_phase_opportunity_id(281, "1"), "planning_delivery:phase"),
    (planning_delivery_phase_opportunity_id(149, UNPHASED), "planning_delivery:phase"),
    (strategic_land_opportunity_id(57), "strategic_land:allocation"),
    ("planning_delivery:component:281:abc", "planning_delivery:component"),
    ("planning_delivery:affordable_package:281:abc", "planning_delivery:affordable_package"),
])
def test_canonical_detector_identity_is_domain_plus_kind(opportunity_id, expected):
    assert opportunity_detector_identity(opportunity_id) == expected


def test_three_segment_shapes_are_identical_to_the_legacy_prefix_only_phase_changes():
    for opportunity_id in (planning_delivery_site_opportunity_id(5), planning_delivery_recent_permission_opportunity_id(5),
                           planning_delivery_long_pending_application_opportunity_id(5), strategic_land_opportunity_id(5)):
        assert opportunity_detector_identity(opportunity_id) == opportunity_id.rsplit(":", 1)[0]
    phase = planning_delivery_phase_opportunity_id(281, "1")
    assert phase.rsplit(":", 1)[0] == "planning_delivery:phase:281"          # the old, per-site identity
    assert opportunity_detector_identity(phase) == "planning_delivery:phase"  # the corrected one


@pytest.mark.parametrize("site_id", [1, 61, 281, 99999])
@pytest.mark.parametrize("code", ["1", "3B", UNPHASED, "A:1", "A:1:2", "Plot 7 - north", "x/y"])
def test_detector_identity_never_depends_on_site_or_scope(site_id, code):
    assert opportunity_detector_identity(f"planning_delivery:phase:{site_id}:{code}") == "planning_delivery:phase"
    assert opportunity_detector_identity(f"planning_delivery:component:{site_id}:{code}") == "planning_delivery:component"


def test_a_phase_code_containing_a_colon_does_not_change_detector_identity():
    assert (opportunity_detector_identity("planning_delivery:phase:13:A:1")
            == opportunity_detector_identity("planning_delivery:phase:13:A")
            == "planning_delivery:phase")


@pytest.mark.parametrize("bad", [
    "", "planning_delivery", "planning_delivery:site", "planning_delivery:site:", "planning_delivery:site:abc",
    "planning_delivery:site:61:extra", "planning_delivery:phase:281", "planning_delivery:phase:281:",
    "planning_delivery:unknown:61", "strategic_land:site:61", "strategic_land:allocation:5:extra", "other:site:1",
])
def test_unparseable_ids_raise(bad):
    with pytest.raises(UnparseableOpportunityId):
        opportunity_detector_identity(bad)


def test_non_strings_raise():
    for bad in (None, 61):
        with pytest.raises(UnparseableOpportunityId):
            opportunity_detector_identity(bad)


# --- pure seam ------------------------------------------------------------------------------------------------------------

def test_plan_is_pure_and_needs_no_session():
    universe = [_record(planning_delivery_phase_opportunity_id(1, "1")), _record(planning_delivery_phase_opportunity_id(2, "1"))]
    plan = plan_opportunity_changes(universe, {}, set())
    assert [result.classification for _, _, result in plan] == [BASELINE_EXISTING, BASELINE_EXISTING]
    plan = plan_opportunity_changes(universe, {}, {"planning_delivery:phase"})
    assert [result.classification for _, _, result in plan] == [NEW, NEW]


def test_sync_uses_the_shared_helpers_not_string_truncation():
    source = inspect.getsource(sync_opportunity_monitoring_state)
    assert "tracked_detector_identities(" in source and "plan_opportunity_changes(" in source
    assert "rsplit" not in source and "_opportunity_kind_prefix" not in source


# --- phase semantics (cases A, B, C) ----------------------------------------------------------------------------------------

def test_case_a_first_detector_run_baselines_every_pre_existing_phase(session, monkeypatch):
    phases = [planning_delivery_phase_opportunity_id(s, c) for s, c in ((1, "1"), (1, "2"), (7, "A"), (9, UNPHASED))]
    _stub_universe(monkeypatch, *[_record(p) for p in phases])
    counts = sync_opportunity_monitoring_state(session)
    assert counts["baseline_existing"] == 4 and counts["new"] == 0
    assert all(_classification(session, p) == BASELINE_EXISTING for p in phases)


def test_case_b_a_new_untracked_phase_is_new_once_the_detector_is_active(session, monkeypatch):
    existing = planning_delivery_phase_opportunity_id(1, "1")
    _stub_universe(monkeypatch, _record(existing))
    sync_opportunity_monitoring_state(session)  # activates the phase detector
    later = planning_delivery_phase_opportunity_id(1, "2")  # a second, later phase at the same site
    _stub_universe(monkeypatch, _record(existing), _record(later))
    counts = sync_opportunity_monitoring_state(session)
    assert counts["new"] == 1 and _classification(session, later) == NEW
    assert _classification(session, existing) == UNCHANGED


def test_case_c_first_ever_phase_at_a_new_site_is_new_when_phases_are_monitored_elsewhere(session, monkeypatch):
    elsewhere = planning_delivery_phase_opportunity_id(1, "1")
    _stub_universe(monkeypatch, _record(elsewhere))
    sync_opportunity_monitoring_state(session)
    first_at_new_site = planning_delivery_phase_opportunity_id(2, "1")
    _stub_universe(monkeypatch, _record(elsewhere), _record(first_at_new_site))
    sync_opportunity_monitoring_state(session)
    # Before G1A this was silently BASELINE_EXISTING (the detector was tracked per SITE).
    assert _classification(session, first_at_new_site) == NEW


def test_other_detectors_are_unaffected_by_an_active_phase_detector(session, monkeypatch):
    _stub_universe(monkeypatch, _record(planning_delivery_phase_opportunity_id(1, "1")))
    sync_opportunity_monitoring_state(session)
    site = planning_delivery_site_opportunity_id(3)
    _stub_universe(monkeypatch, _record(planning_delivery_phase_opportunity_id(1, "1")), _record(site))
    sync_opportunity_monitoring_state(session)
    assert _classification(session, site) == BASELINE_EXISTING  # the site detector's own first run


# --- pre-created rows ---------------------------------------------------------------------------------------------------------

def test_a_pre_created_row_activates_the_detector_for_every_other_untracked_id(session, monkeypatch):
    """Documented rule: a PARTIAL pre-created row (e.g. a manifest or seed covering only some ids) makes the
    detector active, so the remaining untracked ids of the same detector classify NEW. Deployment manifests for
    a detector must cover ALL of its untracked live ids, or none (carried to G1B)."""
    covered = planning_delivery_phase_opportunity_id(1, "1")
    not_covered = [planning_delivery_phase_opportunity_id(2, "1"), planning_delivery_phase_opportunity_id(3, "A")]
    _seed(session, covered)
    _stub_universe(monkeypatch, _record(covered), *[_record(o) for o in not_covered])
    counts = sync_opportunity_monitoring_state(session)
    assert counts["new"] == 2 and counts["baseline_existing"] == 0
    assert all(_classification(session, o) == NEW for o in not_covered)


def test_with_no_pre_created_row_the_same_ids_all_baseline_together(session, monkeypatch):
    ids = [planning_delivery_phase_opportunity_id(1, "1"), planning_delivery_phase_opportunity_id(2, "1"),
           planning_delivery_phase_opportunity_id(3, "A")]
    _stub_universe(monkeypatch, *[_record(o) for o in ids])
    counts = sync_opportunity_monitoring_state(session)
    assert counts["baseline_existing"] == 3 and counts["new"] == 0


# --- fail-closed current ids, tolerant historical rows ----------------------------------------------------------------------

def test_a_malformed_current_id_fails_loudly_and_writes_nothing(session, monkeypatch):
    good = _record(planning_delivery_site_opportunity_id(1))
    bad = _record("planning_delivery:mystery:5")
    _stub_universe(monkeypatch, good, bad)
    with pytest.raises(UnparseableOpportunityId):
        sync_opportunity_monitoring_state(session)
    assert session.execute(select(OpportunityMonitoringState)).scalars().all() == []  # no state, not even the valid one


def test_an_unparseable_historical_row_uses_the_legacy_fallback_and_never_crashes(session, monkeypatch):
    legacy_oddity = "planning_delivery:site:61:extra"  # cannot parse under the lightweight rule
    _seed(session, legacy_oddity)
    assert tracked_detector_identities([legacy_oddity]) == {"planning_delivery:site:61"}  # the legacy rsplit prefix
    _stub_universe(monkeypatch, _record(planning_delivery_site_opportunity_id(2)))
    counts = sync_opportunity_monitoring_state(session)  # does not raise
    # The fallback prefix is NOT the canonical site detector, so the site detector's first run still baselines.
    assert counts["baseline_existing"] == 1 and counts["new"] == 0


def test_the_legacy_fallback_is_used_only_for_unparseable_rows():
    assert tracked_detector_identities(["planning_delivery:phase:281:1"]) == {"planning_delivery:phase"}
    assert tracked_detector_identities(["planning_delivery:phase:281:1", "garbage"]) == {"planning_delivery:phase", "garbage"}
    assert tracked_detector_identities(["a:b:c"]) == {"a:b"}


# --- future kinds remain non-emittable -------------------------------------------------------------------------------------

def test_future_kinds_remain_non_emittable_and_have_a_canonical_detector_identity():
    assert subjects.EMIT_CAPABLE_NEW_KINDS == frozenset()
    for kind in subjects.NEW_KINDS:
        opportunity_id = subjects.build_new_kind_opportunity_id(kind, 61, "abc")
        assert opportunity_detector_identity(opportunity_id) == f"planning_delivery:{kind}"  # identity exists, emission does not
        with pytest.raises(subjects.NewKindNotEmitCapable):
            subjects.resolve_anchor_key(subjects.parse_opportunity_id(opportunity_id), PLANNING_DELIVERY)


def test_a_future_detector_with_no_rows_baselines_all_pre_existing_subjects_together(session, monkeypatch):
    """Intended future first-release behaviour (the detector is NOT enabled today; this exercises the monitoring
    rule only, with a stubbed universe): no rows for the detector -> everything it exposes baselines together,
    and a later subject is NEW."""
    first = [subjects.build_new_kind_opportunity_id("component", s, "abc") for s in (1, 2)]
    _stub_universe(monkeypatch, *[_record(o) for o in first])
    counts = sync_opportunity_monitoring_state(session)
    assert counts["baseline_existing"] == 2 and counts["new"] == 0
    later = subjects.build_new_kind_opportunity_id("component", 3, "abc")
    _stub_universe(monkeypatch, *[_record(o) for o in first], _record(later))
    sync_opportunity_monitoring_state(session)
    assert _classification(session, later) == NEW
