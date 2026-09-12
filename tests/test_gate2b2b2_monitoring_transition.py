"""Gate 2B-2B.2 pre-merge remediation ("Pre-Merge Monitoring Transition") -
tests for app.reporting.opportunity_monitoring_transition, the narrow,
dry-run-first mechanism for correcting OpportunityMonitoringState identity/
fingerprint state after Gate 2B-2B.2's own scope/unit-count corrections,
WITHOUT the ordinary sync_opportunity_monitoring_state ever misreporting
those software corrections as NEW or MATERIALLY_CHANGED planning evidence.

Uses the same in-memory-SQLite `session` fixture as the rest of this
suite (tests/conftest.py). No OpenAI call anywhere.
"""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import select

from app.db.models import Application, OpportunityMonitoringState, Site, SchemeIntelligence
from app.reporting.opportunity_change import MATERIALLY_CHANGED, NEW, UNCHANGED, sync_opportunity_monitoring_state
from app.reporting.opportunity_monitoring_transition import (
    MonitoringTransitionManifest,
    apply_monitoring_transition,
)
from app.reporting.opportunity_universe import (
    build_current_opportunity_universe,
    compute_opportunity_fingerprint,
    planning_delivery_phase_opportunity_id,
)


def _site(session, **kw) -> Site:
    kw.setdefault("display_address", "Land at Test Site")
    kw.setdefault("canonical_address", "land at test site")
    s = Site(council_code="testcouncil", **kw)
    session.add(s)
    session.commit()
    return s


def _app(session, site_id, reference, **kw) -> Application:
    kw.setdefault("application_received", "Mon 01 Jan 2024")
    a = Application(council_code="testcouncil", reference=reference, site_id=site_id, **kw)
    session.add(a)
    session.commit()
    return a


def _intel(session, app, **kw) -> SchemeIntelligence:
    si = SchemeIntelligence(application_id=app.id, **kw)
    session.add(si)
    session.commit()
    return si


def _seed_tracked_row(session, opportunity_id, *, fingerprint="stale" + "0" * 58, first_seen_at=None, **kw) -> OpportunityMonitoringState:
    row = OpportunityMonitoringState(
        opportunity_id=opportunity_id, opportunity_type="planning_delivery", fingerprint=fingerprint,
        fingerprint_fields=json.dumps({"opportunity_type": "planning_delivery"}),
        first_seen_at=first_seen_at or dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc),
        **kw,
    )
    session.add(row)
    session.commit()
    return row


def _row(session, opportunity_id) -> OpportunityMonitoringState | None:
    return session.execute(
        select(OpportunityMonitoringState).where(OpportunityMonitoringState.opportunity_id == opportunity_id)
    ).scalar_one_or_none()


# --- Fixture builders mirroring the two real Gate 2B-2B.2 shapes -----------


def _make_replacement_shape(session) -> tuple[Site, str]:
    """Lacy Street shape: false Plot 25 already retired by the core fix,
    leaving a live-but-never-tracked "Whole site / unphased" replacement
    identity."""
    site = _site(session, display_address="Replacement shape")
    main = _app(session, site.id, "FUL/1", proposal="Erection of 53 dwellings",
                decision="Approve with Conditions", decision_issued_date="Mon 01 Apr 2024",
                application_received="Mon 01 Jan 2024")
    _intel(session, main, total_units_final=53, core_intelligence_complete=True)
    _app(session, site.id, "NMA/1", application_category="variation_or_amendment",
         proposal="Non-material amendment for the omission of Plot 25, end unit of Block 8",
         decision="Approve with Conditions", decision_issued_date="Mon 01 Feb 2024",
         application_received="Mon 01 Jan 2024")
    opportunity_id = planning_delivery_phase_opportunity_id(site.id, "Whole site / unphased")
    return site, opportunity_id


def _make_rebaseline_shape(session) -> tuple[Site, str, int]:
    """Beal Lane shape: a genuine, still-live Phase 1 whose unit_count the
    core fix corrects from an old whole-site-derived figure to its own
    documented 140-unit quantum."""
    site = _site(session, display_address="Rebaseline shape")
    outline = _app(session, site.id, "OUT/1", proposal="Outline permission for the wider masterplan",
                    decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2020")
    _intel(session, outline, total_units_final=26, core_intelligence_complete=True)
    rm_phase1 = _app(session, site.id, "RES/1", application_category="reserved_matters",
                      proposal="Reserved matters application for Phase 1 of a residential scheme",
                      decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024",
                      application_received="Mon 15 Dec 2023")
    _intel(session, rm_phase1, total_units_final=140)
    opportunity_id = planning_delivery_phase_opportunity_id(site.id, "1")
    return site, opportunity_id, 140


# --- 1. Replacement IDs can be baseline-created without NEW ---------------


def test_replacement_id_baselines_without_new_on_next_ordinary_sync(session):
    site, opportunity_id = _make_replacement_shape(session)

    # Establish this detector kind's own baseline first (mirrors real
    # production state, where planning_delivery:phase:* rows already
    # exist) so an untracked id would ordinarily read NEW, not
    # BASELINE_EXISTING, if left untouched - the scenario this transition
    # exists to correct.
    _seed_tracked_row(session, "planning_delivery:phase:424242:Whole site / unphased")

    manifest = MonitoringTransitionManifest(replacement_ids=frozenset({opportunity_id}))
    report = apply_monitoring_transition(session, manifest, dry_run=False)
    assert report.ok
    assert opportunity_id in report.replacement_baselined

    counts = sync_opportunity_monitoring_state(session)
    row = _row(session, opportunity_id)
    assert row.last_change_classification == UNCHANGED
    assert counts["new"] == 0


# --- 2. Corrected surviving IDs can be rebaselined without ------------------
#        MATERIALLY_CHANGED --------------------------------------------------


def test_rebaseline_id_updates_fingerprint_without_materially_changed_on_next_sync(session):
    site, opportunity_id, corrected_unit_count = _make_rebaseline_shape(session)
    _seed_tracked_row(session, opportunity_id)  # stale fingerprint, simulating the pre-fix baseline

    manifest = MonitoringTransitionManifest(rebaseline_ids=frozenset({opportunity_id}))
    report = apply_monitoring_transition(session, manifest, dry_run=False)
    assert report.ok
    assert opportunity_id in report.rebaseline_applied

    counts = sync_opportunity_monitoring_state(session)
    row = _row(session, opportunity_id)
    assert row.last_change_classification == UNCHANGED
    assert counts["materially_changed"] == 0


# --- 3. first_seen_at on surviving IDs is preserved -------------------------


def test_rebaseline_preserves_first_seen_at_and_last_change_fields(session):
    site, opportunity_id, _ = _make_rebaseline_shape(session)
    original_first_seen = dt.datetime(2022, 6, 1, tzinfo=dt.timezone.utc)
    row = _seed_tracked_row(
        session, opportunity_id, first_seen_at=original_first_seen,
        last_change_at=dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc),
        last_change_classification=MATERIALLY_CHANGED, last_change_reasons="unit_count_changed",
    )

    original_fingerprint = row.fingerprint
    manifest = MonitoringTransitionManifest(rebaseline_ids=frozenset({opportunity_id}))
    report = apply_monitoring_transition(session, manifest, dry_run=False)
    assert report.ok

    refreshed = _row(session, opportunity_id)
    assert refreshed.first_seen_at.replace(tzinfo=None) == original_first_seen.replace(tzinfo=None)
    assert refreshed.last_change_at.replace(tzinfo=None) == dt.datetime(2023, 1, 1)
    assert refreshed.last_change_classification == MATERIALLY_CHANGED
    assert refreshed.last_change_reasons == "unit_count_changed"
    # Only the snapshot itself moved.
    assert refreshed.fingerprint != original_fingerprint


# --- 4. Retired IDs are not deleted -----------------------------------------


def test_retired_id_row_is_not_deleted_or_mutated(session):
    retired_id = "planning_delivery:phase:9999:25"  # a site that no longer exists at all - definitely absent
    original_fingerprint = "f" * 64
    _seed_tracked_row(session, retired_id, fingerprint=original_fingerprint)

    manifest = MonitoringTransitionManifest(retired_ids=frozenset({retired_id}))
    report = apply_monitoring_transition(session, manifest, dry_run=False)
    assert report.ok
    assert retired_id in report.retired_confirmed_absent

    row = _row(session, retired_id)
    assert row is not None
    assert row.fingerprint == original_fingerprint


# --- 5. Unrelated monitoring rows are untouched -----------------------------


def test_unrelated_monitoring_row_is_completely_untouched(session):
    site, opportunity_id, _ = _make_rebaseline_shape(session)
    _seed_tracked_row(session, opportunity_id)

    unrelated_id = "planning_delivery:site:99999"
    unrelated_fingerprint = "u" * 64
    unrelated_fields = json.dumps({"opportunity_type": "planning_delivery", "unit_count": 5})
    unrelated_first_seen = dt.datetime(2021, 3, 3, tzinfo=dt.timezone.utc)
    _seed_tracked_row(
        session, unrelated_id, fingerprint=unrelated_fingerprint, first_seen_at=unrelated_first_seen,
    )
    session.execute(
        OpportunityMonitoringState.__table__.update()
        .where(OpportunityMonitoringState.opportunity_id == unrelated_id)
        .values(fingerprint_fields=unrelated_fields)
    )
    session.commit()

    manifest = MonitoringTransitionManifest(rebaseline_ids=frozenset({opportunity_id}))
    report = apply_monitoring_transition(session, manifest, dry_run=False)
    assert report.ok

    unrelated_row = _row(session, unrelated_id)
    assert unrelated_row.fingerprint == unrelated_fingerprint
    assert unrelated_row.fingerprint_fields == unrelated_fields
    assert unrelated_row.first_seen_at.replace(tzinfo=None) == unrelated_first_seen.replace(tzinfo=None)


# --- 6. Dry-run performs zero writes ----------------------------------------


def test_dry_run_performs_zero_writes(session):
    replacement_site, replacement_id = _make_replacement_shape(session)
    rebaseline_site, rebaseline_id, _ = _make_rebaseline_shape(session)
    stale_fingerprint = "stale" + "0" * 58
    _seed_tracked_row(session, rebaseline_id, fingerprint=stale_fingerprint)

    manifest = MonitoringTransitionManifest(
        replacement_ids=frozenset({replacement_id}), rebaseline_ids=frozenset({rebaseline_id}),
    )
    report = apply_monitoring_transition(session, manifest, dry_run=True)

    assert report.ok
    assert report.writes  # the report DOES describe what would happen
    assert replacement_id in report.replacement_baselined
    assert rebaseline_id in report.rebaseline_applied

    assert _row(session, replacement_id) is None  # no row was created
    rebaseline_row = _row(session, rebaseline_id)
    assert rebaseline_row.fingerprint == stale_fingerprint  # untouched


# --- 7. Unexpected manifest drift fails closed ------------------------------


def test_manifest_drift_fails_closed_and_applies_no_writes_at_all(session):
    # A valid rebaseline candidate...
    valid_site, valid_rebaseline_id, _ = _make_rebaseline_shape(session)
    stale_fingerprint = "stale" + "0" * 58
    _seed_tracked_row(session, valid_rebaseline_id, fingerprint=stale_fingerprint)

    # ...bundled in the SAME manifest as a replacement id that the
    # manifest author believed was untracked, but which (data drift) is
    # actually already tracked - this must refuse the WHOLE transition,
    # not just the bad half.
    drifted_replacement_site, drifted_replacement_id = _make_replacement_shape(session)
    _seed_tracked_row(session, drifted_replacement_id, fingerprint="already-tracked" + "0" * 49)

    manifest = MonitoringTransitionManifest(
        rebaseline_ids=frozenset({valid_rebaseline_id}), replacement_ids=frozenset({drifted_replacement_id}),
    )
    report = apply_monitoring_transition(session, manifest, dry_run=False)

    assert not report.ok
    assert drifted_replacement_id in report.replacement_already_tracked
    assert not report.writes

    # The valid rebaseline candidate must ALSO remain untouched.
    row = _row(session, valid_rebaseline_id)
    assert row.fingerprint == stale_fingerprint


def test_missing_replacement_id_fails_closed(session):
    manifest = MonitoringTransitionManifest(replacement_ids=frozenset({"planning_delivery:phase:8888:1"}))
    report = apply_monitoring_transition(session, manifest, dry_run=False)
    assert not report.ok
    assert "planning_delivery:phase:8888:1" in report.replacement_missing_from_universe
    assert not report.writes


def test_rebaseline_id_not_currently_tracked_fails_closed(session):
    site, opportunity_id, _ = _make_rebaseline_shape(session)
    # No _seed_tracked_row call - this id has never been tracked, so there
    # is nothing to rebaseline (it belongs on the replacement path).
    manifest = MonitoringTransitionManifest(rebaseline_ids=frozenset({opportunity_id}))
    report = apply_monitoring_transition(session, manifest, dry_run=False)
    assert not report.ok
    assert opportunity_id in report.rebaseline_not_currently_tracked
    assert not report.writes


def test_id_in_multiple_categories_fails_closed(session):
    site, opportunity_id, _ = _make_rebaseline_shape(session)
    _seed_tracked_row(session, opportunity_id)
    manifest = MonitoringTransitionManifest(
        rebaseline_ids=frozenset({opportunity_id}), retired_ids=frozenset({opportunity_id}),
    )
    report = apply_monitoring_transition(session, manifest, dry_run=False)
    assert not report.ok
    assert opportunity_id in report.ids_in_multiple_categories
    assert not report.writes


# --- 8/9/10. Normal sync semantics remain completely unaffected ------------


def test_normal_new_behaviour_is_unaffected_by_the_transition_module(session):
    site, opportunity_id = _make_replacement_shape(session)
    # _opportunity_kind_prefix strips only the FINAL ":"-separated segment
    # (the phase code), so for a "planning_delivery:phase:{site_id}:{code}"
    # id, baseline-run detection is scoped PER SITE, not per detector
    # family - seed a DIFFERENT phase code on the SAME site to correctly
    # establish that this site's own "phase" kind already has a tracked
    # baseline, so the opportunity actually under test is genuinely NEW,
    # not this run's first-ever baseline.
    _seed_tracked_row(session, planning_delivery_phase_opportunity_id(site.id, "OTHER"))

    # No transition applied at all - a genuinely new, untracked opportunity
    # must still be classified NEW by ordinary sync.
    counts = sync_opportunity_monitoring_state(session)
    row = _row(session, opportunity_id)
    assert row.last_change_classification == NEW
    assert counts["new"] >= 1


def test_normal_materially_changed_behaviour_is_unaffected_by_the_transition_module(session):
    site, opportunity_id, _ = _make_rebaseline_shape(session)
    sync_opportunity_monitoring_state(session)  # establish tracking normally
    row = _row(session, opportunity_id)
    assert row.last_change_classification in (NEW, "BASELINE_EXISTING")
    original_fingerprint = row.fingerprint

    # A genuine change: a later, real condition-discharge filing on the
    # SAME site is unambiguous post-grant progress evidence, flipping the
    # whole site's own lapse_status/build_status (compute_lapse_status,
    # untouched by this gate's fix) - unrelated to this transition module
    # entirely.
    _app(session, site.id, "CND/2", application_category="condition_discharge_or_details",
         proposal="Full discharge of conditions", decision="Full discharge of conditions",
         decision_issued_date="Mon 01 Feb 2024", application_received="Mon 01 Feb 2024")

    counts = sync_opportunity_monitoring_state(session)
    refreshed = _row(session, opportunity_id)
    assert refreshed.fingerprint != original_fingerprint
    assert refreshed.last_change_classification == MATERIALLY_CHANGED
    assert counts["materially_changed"] >= 1


def test_normal_unchanged_behaviour_is_unaffected_by_the_transition_module(session):
    site, opportunity_id, _ = _make_rebaseline_shape(session)
    sync_opportunity_monitoring_state(session)
    row_after_first_sync = _row(session, opportunity_id)
    fingerprint_after_first_sync = row_after_first_sync.fingerprint

    counts = sync_opportunity_monitoring_state(session)  # nothing changed in between
    refreshed = _row(session, opportunity_id)
    assert refreshed.fingerprint == fingerprint_after_first_sync
    assert refreshed.last_change_classification == UNCHANGED
    assert counts["unchanged"] >= 1
