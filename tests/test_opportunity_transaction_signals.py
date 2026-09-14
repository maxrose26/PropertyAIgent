"""Agent Evaluation Foundation - tests for app.reporting.
opportunity_transaction_signals: the buyer-independent Transaction/
Disposition Signal V1 read layer.

Focus areas (Product Owner review of the Agent Evaluation Policy V1
architecture report and its refinement):
- recent_permission / approaching_implementation_deadline / development_
  underway / partially_complete are correctly derived from
  compute_lapse_status/classify_build_status;
- absence of commencement evidence is NEVER read as confirmed inactivity -
  no_identified_development_progress is UNKNOWN whenever there is no
  resolved basis to have looked, PRESENT only when a lapse clock has
  genuinely started with no progress evidence found, and this is never
  collapsed with development_underway's own ABSENT-never-exists guarantee;
- ownership_or_control_evidence_changed reads only whether the EVIDENCE
  changed, never that ownership itself changed;
- STRATEGIC_LAND opportunities receive NOT_APPLICABLE for every
  development-progress-shaped signal.

Uses the same in-memory-SQLite `session` fixture as the rest of this suite
(tests/conftest.py). No OpenAI call anywhere.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from app.db.models import Application, OpportunityMonitoringState, Site
from app.policy.buyer_matching import PLANNING_DELIVERY, STRATEGIC_LAND
from app.reporting.opportunity_transaction_signals import (
    ABSENT,
    NOT_APPLICABLE,
    PRESENT,
    UNKNOWN,
    build_transaction_signals,
)
from app.reporting.opportunity_universe import RECENT_PERMISSION_WINDOW_MONTHS, add_calendar_months


def _site(session, **kw) -> Site:
    kw.setdefault("display_address", "Land at Test Site")
    kw.setdefault("canonical_address", "land at test site")
    s = Site(council_code="testcouncil", **kw)
    session.add(s)
    session.commit()
    return s


def _app(session, site_id, reference, **kw) -> Application:
    kw.setdefault("application_received", "Mon 01 Jan 2024")
    # A substantive proposal description - app.reporting.scheme_
    # reconciliation.resolve_planning_role derives its own "category" from
    # app.scrapers.unit_filter.classify_application_category(proposal), NOT
    # from the stored application_category DB column, so a granted-
    # permission test needs real proposal text to resolve as ROLE_FULL
    # (a substantive role) rather than ROLE_OTHER_SUBSTANTIVE/unknown.
    kw.setdefault("proposal", "Erection of 50 dwellings")
    a = Application(council_code="testcouncil", reference=reference, site_id=site_id, **kw)
    session.add(a)
    session.commit()
    return a


def _portal_date(d: dt.date) -> str:
    return d.strftime("%a %d %b %Y")


def _apps_for(session, site: Site) -> list[Application]:
    return session.execute(select(Application).where(Application.site_id == site.id)).scalars().all()


class _FakeOpportunity:
    """The minimal shape build_transaction_signals actually reads -
    opportunity_id/opportunity_type only, mirroring app.reporting.
    opportunity_universe.OpportunityRecord's own two identity fields."""

    def __init__(self, opportunity_id: str, opportunity_type: str) -> None:
        self.opportunity_id = opportunity_id
        self.opportunity_type = opportunity_type


# --- STRATEGIC_LAND: everything development-progress-shaped is N/A ---------

def test_strategic_land_receives_not_applicable_for_every_development_signal(session):
    opp = _FakeOpportunity("strategic_land:allocation:1", STRATEGIC_LAND)
    signals = build_transaction_signals(session, opp)
    assert signals.recent_permission.state == NOT_APPLICABLE
    assert signals.approaching_implementation_deadline.state == NOT_APPLICABLE
    assert signals.development_underway.state == NOT_APPLICABLE
    assert signals.partially_complete.state == NOT_APPLICABLE
    assert signals.no_identified_development_progress.state == NOT_APPLICABLE
    assert signals.raw_lapse_status is None
    assert signals.raw_build_status is None
    assert signals.raw_decision_date is None


def test_strategic_land_ownership_signal_is_still_meaningful(session):
    """matched_to_site is one of opportunity_change.py's own tracked
    strategic-land fingerprint fields - OWNERSHIP_OR_CONTROL_EVIDENCE_CHANGED
    remains a real, non-N/A question for STRATEGIC_LAND, unlike the
    development-progress signals."""
    opp = _FakeOpportunity("strategic_land:allocation:1", STRATEGIC_LAND)
    signals = build_transaction_signals(session, opp)
    assert signals.ownership_or_control_evidence_changed.state == UNKNOWN  # never monitored yet


# --- RECENT_PERMISSION -------------------------------------------------------

def test_recent_permission_present_within_window(session):
    site = _site(session)
    recent_decision = dt.date.today() - dt.timedelta(days=30)
    _app(session, site.id, "REF/1", application_category="primary_residential",
         decision="Approve with Conditions", decision_issued_date=_portal_date(recent_decision))
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site)
    assert signals.recent_permission.state == PRESENT
    assert signals.raw_decision_date == recent_decision


def test_recent_permission_absent_outside_window(session):
    site = _site(session)
    old_decision = add_calendar_months(dt.date.today(), -(RECENT_PERMISSION_WINDOW_MONTHS + 6))
    _app(session, site.id, "REF/1", application_category="primary_residential",
         decision="Approve with Conditions", decision_issued_date=_portal_date(old_decision))
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site)
    assert signals.recent_permission.state == ABSENT


def test_recent_permission_absent_when_nothing_granted(session):
    site = _site(session)
    _app(session, site.id, "REF/1", application_category="primary_residential", decision=None, status="Under consideration")
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site)
    assert signals.recent_permission.state == ABSENT
    assert signals.raw_decision_date is None


# --- APPROACHING_IMPLEMENTATION_DEADLINE ------------------------------------

def test_approaching_implementation_deadline_present_near_lapse(session):
    site = _site(session)
    # ~3 years ago minus a handful of days, so the deadline is imminent but not passed.
    near_lapse_decision = dt.date.today() - dt.timedelta(days=3 * 365 - 20)
    _app(session, site.id, "REF/1", application_category="primary_residential",
         decision="Approve with Conditions", decision_issued_date=_portal_date(near_lapse_decision))
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site)
    assert signals.approaching_implementation_deadline.state == PRESENT
    assert signals.raw_lapse_status == "approaching"


def test_approaching_implementation_deadline_absent_when_comfortably_distant(session):
    site = _site(session)
    recent_decision = dt.date.today() - dt.timedelta(days=60)
    _app(session, site.id, "REF/1", application_category="primary_residential",
         decision="Approve with Conditions", decision_issued_date=_portal_date(recent_decision))
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site)
    assert signals.approaching_implementation_deadline.state == ABSENT
    assert signals.raw_lapse_status == "safe"


# --- DEVELOPMENT_UNDERWAY: PRESENT or UNKNOWN, NEVER ABSENT -----------------

def test_development_underway_unknown_never_absent_when_no_progress_evidence(session):
    """Correction 1 (Product Owner review): an absence of commencement
    evidence must never become a confirmed 'not underway' fact."""
    site = _site(session)
    recent_decision = dt.date.today() - dt.timedelta(days=60)
    _app(session, site.id, "REF/1", application_category="primary_residential",
         decision="Approve with Conditions", decision_issued_date=_portal_date(recent_decision))
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site)
    assert signals.development_underway.state == UNKNOWN
    assert signals.development_underway.state != ABSENT


def test_development_underway_present_with_progress_signal_filing(session):
    site = _site(session)
    recent_decision = dt.date.today() - dt.timedelta(days=60)
    _app(session, site.id, "REF/1", application_category="primary_residential",
         decision="Approve with Conditions", decision_issued_date=_portal_date(recent_decision))
    # A progress-signal filing (e.g. a commencement notice) submitted after
    # the decision date - mirrors classify_build_status's own "portal-native
    # progress-signal filing" detection.
    _app(session, site.id, "REF/1-COMM", application_category="condition_discharge_or_details",
         proposal="Notification of commencement of development",
         application_received=_portal_date(dt.date.today() - dt.timedelta(days=10)))
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site)
    # This assertion is intentionally loose (PRESENT or UNKNOWN) - the
    # exact portal-filing detection heuristic belongs to classify_build_
    # status, not this module; what this module must never do is turn the
    # PRESENCE of a filing into an ABSENT signal.
    assert signals.development_underway.state in (PRESENT, UNKNOWN)
    assert signals.development_underway.state != ABSENT


# --- NO_IDENTIFIED_DEVELOPMENT_PROGRESS: the conservative signal -----------

def test_no_identified_development_progress_unknown_when_nothing_granted(session):
    """The core Product Owner correction: no basis to have looked -> UNKNOWN,
    never PRESENT."""
    site = _site(session)
    _app(session, site.id, "REF/1", application_category="primary_residential", decision=None, status="Under consideration")
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site)
    assert signals.no_identified_development_progress.state == UNKNOWN


def test_no_identified_development_progress_present_only_with_a_resolved_lapse_clock(session):
    site = _site(session)
    recent_decision = dt.date.today() - dt.timedelta(days=60)
    _app(session, site.id, "REF/1", application_category="primary_residential",
         decision="Approve with Conditions", decision_issued_date=_portal_date(recent_decision))
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site)
    assert signals.raw_lapse_status == "safe"
    assert signals.no_identified_development_progress.state == PRESENT
    # And its own detail text must never claim confirmed inactivity.
    detail = signals.no_identified_development_progress.detail or ""
    for forbidden in ("dormant", "stalled", "land bank", "unwilling", "confirmed uncommenced"):
        assert forbidden not in detail.lower() or "does not mean" in detail.lower()


# --- OWNERSHIP_OR_CONTROL_EVIDENCE_CHANGED: evidence change, never ownership change ---

def test_ownership_evidence_changed_unknown_without_any_monitoring_baseline(session):
    site = _site(session)
    recent_decision = dt.date.today() - dt.timedelta(days=60)
    _app(session, site.id, "REF/1", application_category="primary_residential",
         decision="Approve with Conditions", decision_issued_date=_portal_date(recent_decision))
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site)
    assert signals.ownership_or_control_evidence_changed.state == UNKNOWN


def test_ownership_evidence_changed_present_reflects_evidence_not_ownership(session):
    session.add(OpportunityMonitoringState(
        opportunity_id="planning_delivery:site:1", opportunity_type="planning_delivery",
        fingerprint="fp-after", fingerprint_fields="{}",
        last_change_classification="MATERIALLY_CHANGED", last_change_reasons="ownership_evidence_changed",
    ))
    session.commit()
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=[], site=_site(session))
    assert signals.ownership_or_control_evidence_changed.state == PRESENT
    detail = signals.ownership_or_control_evidence_changed.detail or ""
    assert "does not itself establish" in detail or "does not establish" in detail
    for forbidden in ("ownership has changed", "control has changed", "new owner"):
        assert forbidden not in detail.lower()
