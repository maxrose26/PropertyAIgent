"""Gate 1C amendment ("Planning Opportunity Triggers & Weekly Re-evaluation")
- cross-cutting tests proving the amendment's most important, explicitly-
flagged property: TIME ITSELF changes eligibility, purely from the
evaluation date advancing, with NO underlying record ever modified (Section
12/13/16). Also covers the two "reasoned through but not yet proven" claims
from this gate's own investigation:

- transaction atomicity of sync_opportunity_monitoring_state (a single
  commit at the very end - proven here by simulating a mid-loop
  interruption and confirming nothing partial persists);
- last_seen_at (onupdate=utcnow) as an implicit "still active vs. exited"
  signal (proven here by empirical observation, not just code inspection -
  see the sibling probe this file's own git history/PR notes reference:
  SQLAlchemy DOES re-issue an UPDATE - and so DOES advance last_seen_at -
  even when a scalar attribute is reassigned its own unchanged value).

Clock control: production code calls `dt.date.today()` directly (never an
injected clock - correctly so, since Section 15 explicitly forbids
threading a weekday/schedule concept into core business logic). To
"simulate sequential weekly evaluation dates" without modifying any
records (the brief's own explicit requirement), this file monkeypatches
the process-wide `datetime.date` class itself with a subclass whose
`today()` returns a controlled, advanceable value - every module in the
process that does `import datetime as dt; dt.date.today()` shares the
same `datetime` module object, so this one patch point moves "today" for
the whole system at once, exactly modelling one external clock advancing
between two scheduled runs. Reverted automatically by pytest's monkeypatch
fixture at the end of each test.
"""
from __future__ import annotations

import datetime as real_datetime
import time

import pytest
from sqlalchemy import select

from app.db.models import Application, OpportunityMonitoringState, Site
from app.reporting.dashboard import _approaching_lapse_cards, _long_pending_application_cards, _recent_permission_cards
import app.reporting.opportunity_change as opportunity_change_module
from app.reporting.opportunity_change import BASELINE_EXISTING, NEW, sync_opportunity_monitoring_state
from app.reporting.opportunity_universe import LONG_PENDING_APPLICATION_WINDOW_MONTHS, RECENT_PERMISSION_WINDOW_MONTHS, add_calendar_months


class _FrozenDate(real_datetime.date):
    _frozen = real_datetime.date.today()

    @classmethod
    def today(cls):
        return cls._frozen


def _freeze_today(monkeypatch, value: real_datetime.date) -> None:
    _FrozenDate._frozen = value
    monkeypatch.setattr(real_datetime, "date", _FrozenDate)


def _add_granted_application(session, site: Site, grant_date: real_datetime.date, *, ref: str) -> None:
    session.add(Application(
        council_code="testcouncil", reference=ref, site_id=site.id,
        decision="Granted", decision_issued_date=grant_date.strftime("%a %d %b %Y"),
        first_seen_at=real_datetime.datetime.now(real_datetime.timezone.utc),
        # Gate 2B-2C: resolve_planning_role needs real substantive proposal
        # wording to trust this as the lapse anchor.
        proposal="Erection of 40 dwellings",
    ))


def _add_pending_application(session, site: Site, submitted_date: real_datetime.date, *, ref: str) -> None:
    session.add(Application(
        council_code="testcouncil", reference=ref, site_id=site.id,
        decision=None, status="Under consideration", application_category="full_planning",
        application_received=submitted_date.strftime("%a %d %b %Y"),
        first_seen_at=real_datetime.datetime.now(real_datetime.timezone.utc),
    ))


# --- Worked example 1 (brief's own example): pending application becomes
# long-pending purely from the evaluation date advancing ------------------

def test_pending_application_becomes_long_pending_purely_from_time_passing(session, monkeypatch):
    t0 = real_datetime.date.today()
    _freeze_today(monkeypatch, t0)

    submitted = t0 - real_datetime.timedelta(days=150)  # ~5 months - not yet 6
    site = Site(council_code="testcouncil", canonical_address="time-transition-pending", display_address="Time Transition Pending Site")
    session.add(site)
    session.flush()
    _add_pending_application(session, site, submitted, ref="REF-TT-PENDING")
    session.commit()

    week1_cards = _long_pending_application_cards(session, None)
    assert not any(c["params"]["site_id"] == str(site.id) for c in week1_cards), (
        "not yet eligible at week 1 - only ~5 months pending"
    )

    # Advance the evaluation date to the exact 6-calendar-month boundary -
    # NO record touched at all (same submitted application, same status).
    t1 = add_calendar_months(submitted, LONG_PENDING_APPLICATION_WINDOW_MONTHS)
    _freeze_today(monkeypatch, t1)

    week2_cards = _long_pending_application_cards(session, None)
    assert any(c["params"]["site_id"] == str(site.id) for c in week2_cards), (
        "eligibility must flip to included purely because the evaluation date advanced"
    )


# --- Worked example 2 (brief's own example): a permission's lapse
# countdown crosses 180 days purely from the evaluation date advancing ----

def test_lapse_countdown_crosses_180_days_purely_from_time_passing(session, monkeypatch):
    t0 = real_datetime.date.today()
    _freeze_today(monkeypatch, t0)

    # Deadline (grant + 3 calendar years, compute_lapse_status's own
    # construction) chosen to land 190 days after t0 - "safe" (>180) at t0.
    target_deadline = t0 + real_datetime.timedelta(days=190)
    grant_date = target_deadline.replace(year=target_deadline.year - 3)
    site = Site(council_code="testcouncil", canonical_address="time-transition-lapse", display_address="Time Transition Lapse Site")
    session.add(site)
    session.flush()
    _add_granted_application(session, site, grant_date, ref="REF-TT-LAPSE")
    session.commit()

    week1_cards = _approaching_lapse_cards(session, None)
    assert not any(c["params"]["site_id"] == str(site.id) for c in week1_cards), (
        "190 days to deadline is still 'safe', not yet 'approaching'"
    )

    # Advance the evaluation date by 15 days (e.g. two scheduled weekly
    # runs) - the SAME grant_date, the SAME Application row, untouched.
    t1 = t0 + real_datetime.timedelta(days=15)
    _freeze_today(monkeypatch, t1)

    week2_cards = _approaching_lapse_cards(session, None)
    assert any(c["params"]["site_id"] == str(site.id) for c in week2_cards), (
        "175 days to deadline must now read as 'approaching' purely from time passing"
    )


# --- Worked example 3: recent_permission exits the universe purely from
# time passing (the brief's own "ages beyond 3 months -> no signal") ------

def test_recent_permission_ages_out_purely_from_time_passing(session, monkeypatch):
    t0 = real_datetime.date.today()
    _freeze_today(monkeypatch, t0)

    grant_date = t0 - real_datetime.timedelta(days=30)  # ~1 month old
    site = Site(council_code="testcouncil", canonical_address="time-transition-recent", display_address="Time Transition Recent Site")
    session.add(site)
    session.flush()
    _add_granted_application(session, site, grant_date, ref="REF-TT-RECENT")
    session.commit()

    week1_cards = _recent_permission_cards(session, None)
    assert any(c["params"]["site_id"] == str(site.id) for c in week1_cards)

    # Advance to just past the exclusive 3-month boundary - same grant,
    # same Application row, untouched.
    t1 = add_calendar_months(grant_date, RECENT_PERMISSION_WINDOW_MONTHS) + real_datetime.timedelta(days=1)
    _freeze_today(monkeypatch, t1)

    week2_cards = _recent_permission_cards(session, None)
    assert not any(c["params"]["site_id"] == str(site.id) for c in week2_cards), (
        "must age out purely from time passing - no record was modified"
    )


# --- Threshold-crossing entry = NEW, never confused with detector-
# expansion BASELINE_EXISTING (Section 16's own explicit (A) vs (B)) ------

def test_time_threshold_crossing_after_kind_already_baselined_is_new_not_baseline(session, monkeypatch):
    """(A) a historical population on first deployment of a detector kind
    is BASELINE_EXISTING (proven by the week-1 sync below, establishing
    the long_pending_application kind for the first time via one already-
    old candidate). (B) a DIFFERENT candidate later crossing the same time
    threshold, with the kind already tracked, must be NEW - proven by the
    week-2 sync, where the second application's eligibility flips purely
    because the evaluation date advanced, not because any record changed."""
    t0 = real_datetime.date.today()
    _freeze_today(monkeypatch, t0)

    # Site A: already long-pending at week 1 - establishes the
    # long_pending_application kind's baseline.
    already_old_submitted = t0 - real_datetime.timedelta(days=250)  # >8 months
    site_a = Site(council_code="testcouncil", canonical_address="baseline-a", display_address="Baseline Established Site")
    session.add(site_a)
    session.flush()
    _add_pending_application(session, site_a, already_old_submitted, ref="REF-BASE-A")

    # Site B: pending, but NOT yet 6 months at week 1 - will cross the
    # threshold at week 2 with no modification.
    almost_old_submitted = t0 - real_datetime.timedelta(days=150)  # ~5 months
    site_b = Site(council_code="testcouncil", canonical_address="crosses-later-b", display_address="Crosses Threshold Later Site")
    session.add(site_b)
    session.flush()
    _add_pending_application(session, site_b, almost_old_submitted, ref="REF-CROSS-B")
    session.commit()

    week1 = sync_opportunity_monitoring_state(session)
    assert week1["baseline_existing"] >= 1
    assert week1["new"] == 0
    state_a = session.execute(
        select(OpportunityMonitoringState).where(
            OpportunityMonitoringState.opportunity_id.like("planning_delivery:long_pending_application:%")
        )
    ).scalars().all()
    assert len(state_a) == 1  # only site A qualifies at week 1
    assert state_a[0].last_change_classification == BASELINE_EXISTING

    # Advance to the exact moment site B's application crosses 6 months -
    # site B's own Application row is never touched.
    t1 = add_calendar_months(almost_old_submitted, LONG_PENDING_APPLICATION_WINDOW_MONTHS)
    _freeze_today(monkeypatch, t1)

    week2 = sync_opportunity_monitoring_state(session)
    assert week2["new"] == 1  # site B, entering for the first time, kind already tracked
    assert week2["baseline_existing"] == 0

    all_states = session.execute(
        select(OpportunityMonitoringState).where(
            OpportunityMonitoringState.opportunity_id.like("planning_delivery:long_pending_application:%")
        )
    ).scalars().all()
    by_site_id = {int(s.opportunity_id.rsplit(":", 1)[1]): s for s in all_states}
    assert by_site_id[site_a.id].last_change_classification != NEW  # unchanged, still tracked from week 1
    assert by_site_id[site_b.id].last_change_classification == NEW


def test_repeated_unchanged_weekly_run_produces_no_false_new(session, monkeypatch):
    t0 = real_datetime.date.today()
    _freeze_today(monkeypatch, t0)
    submitted = t0 - real_datetime.timedelta(days=250)
    site = Site(council_code="testcouncil", canonical_address="repeated-run", display_address="Repeated Run Site")
    session.add(site)
    session.flush()
    _add_pending_application(session, site, submitted, ref="REF-REPEAT")
    session.commit()

    sync_opportunity_monitoring_state(session)  # baseline
    # Three further "weekly" runs at unchanged dates - no false NEW ever.
    for _ in range(3):
        result = sync_opportunity_monitoring_state(session)
        assert result["new"] == 0


# --- Baseline-interruption resilience (Section 19) ------------------------

def test_interrupted_sync_persists_nothing_partial(session, monkeypatch):
    """Proves sync_opportunity_monitoring_state's atomicity by construction
    (a single session.commit() at the very end, after the entire per-record
    loop) rather than merely asserting it from code inspection: force an
    exception partway through a multi-candidate sync and confirm the table
    is left completely untouched, exactly as before the call - no schema
    change, no partial-row cleanup logic needed."""
    for i in range(3):
        submitted = real_datetime.date.today() - real_datetime.timedelta(days=250)
        site = Site(council_code="testcouncil", canonical_address=f"interrupt-{i}", display_address=f"Interrupt Site {i}")
        session.add(site)
        session.flush()
        _add_pending_application(session, site, submitted, ref=f"REF-INTERRUPT-{i}")
    session.commit()

    call_count = {"n": 0}
    original = opportunity_change_module.classify_opportunity_change

    def _flaky_classifier(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated interruption partway through the sync")
        return original(*args, **kwargs)

    monkeypatch.setattr(opportunity_change_module, "classify_opportunity_change", _flaky_classifier)

    with pytest.raises(RuntimeError):
        sync_opportunity_monitoring_state(session)

    session.rollback()
    rows = session.execute(select(OpportunityMonitoringState)).scalars().all()
    assert rows == [], "an interrupted sync must never leave partial rows behind - single end-of-function commit makes this atomic by construction"

    # And a subsequent, uninterrupted sync behaves exactly as a normal
    # first-ever baseline run - the interrupted attempt left no trace to
    # confuse later classification.
    result = sync_opportunity_monitoring_state(session)
    assert result["baseline_existing"] == 3
    assert result["new"] == 0


# --- Candidate exit: last_seen_at distinguishes active vs. historical ----

def test_last_seen_at_distinguishes_currently_active_from_exited_candidates(session):
    """Empirically proven (not merely reasoned from code inspection - see
    this module's own docstring): SQLAlchemy re-issues an UPDATE, and so
    onupdate=utcnow DOES advance last_seen_at, even when a scalar attribute
    is reassigned its own already-equal value - which is exactly what
    happens to every UNCHANGED candidate on every sync. This already gives
    'currently active' vs. 'historical, no longer present' a real signal
    with NO schema change: a candidate that exits the universe simply stops
    being touched, so its last_seen_at goes stale relative to the most
    recent sync, while an active candidate's last_seen_at keeps advancing."""
    today = real_datetime.date.today()
    stays_active = Site(council_code="testcouncil", canonical_address="exit-stays-active", display_address="Stays Active Site")
    exits_universe = Site(council_code="testcouncil", canonical_address="exit-leaves", display_address="Exits Universe Site")
    session.add_all([stays_active, exits_universe])
    session.flush()
    _add_pending_application(session, stays_active, today - real_datetime.timedelta(days=250), ref="REF-STAYS")
    exiting_app_ref = "REF-EXITS"
    _add_pending_application(session, exits_universe, today - real_datetime.timedelta(days=250), ref=exiting_app_ref)
    session.commit()

    sync_opportunity_monitoring_state(session)
    states = {
        s.opportunity_id: s for s in session.execute(select(OpportunityMonitoringState)).scalars()
        if s.opportunity_id.startswith("planning_delivery:long_pending_application:")
    }
    active_id = f"planning_delivery:long_pending_application:{stays_active.id}"
    exiting_id = f"planning_delivery:long_pending_application:{exits_universe.id}"
    t1_active = states[active_id].last_seen_at
    t1_exiting = states[exiting_id].last_seen_at

    # The exiting site's application is now granted - it leaves the
    # long_pending_application universe entirely (a genuinely different,
    # real state change - not a fingerprint edit while still present).
    exiting_app = session.execute(select(Application).where(Application.reference == exiting_app_ref)).scalars().first()
    exiting_app.decision = "Granted"
    exiting_app.status = "Decided"
    session.commit()

    time.sleep(0.02)  # ensure real wall-clock advances between syncs
    sync_opportunity_monitoring_state(session)
    session.refresh(states[active_id])
    session.refresh(states[exiting_id])

    assert states[active_id].last_seen_at > t1_active, "still-present candidate must be touched (last_seen_at advances) on every sync"
    assert states[exiting_id].last_seen_at == t1_exiting, "a candidate that exits the universe must stop being touched - its last_seen_at goes stale, never advanced or deleted"
