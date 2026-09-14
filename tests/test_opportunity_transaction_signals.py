"""Agent Evaluation Foundation - tests for app.reporting.
opportunity_transaction_signals: the buyer-independent Transaction/
Disposition Signal V1 read layer, post pre-release development-progress
semantic-fix approval.

Focus areas:
A. EPC SAFETY - EPC-only build_status ("partially_complete"/"complete")
   must never make implementation_activity_evidence_identified PRESENT;
   raw_build_status remains available as secondary context regardless.
B. POSITIVE PLANNING EVIDENCE - a qualifying post-permission related
   planning application (condition-discharge/variation-amendment) makes
   the signal PRESENT, with detail identifying the actual filing, never
   claiming physical commencement.
C. COVERAGE - no_qualifying_progress_evidence_identified requires
   Application.related_search_checked_at to be populated on the resolved
   anchor; coverage_checked_at is retained/exposed.
D. SCOPE - an unverified named-phase-shaped opportunity (scope_verified=
   False) must never inherit a confident opportunity-level PRESENT from
   wider-site evidence; the wider-site finding is preserved separately.
E. TERMINOLOGY - no signal detail anywhere claims physical commencement,
   confirmed inactivity, or seller willingness.
F. NON-REGRESSION - recent_permission/approaching_implementation_deadline/
   ownership_or_control_evidence_changed remain exactly as before.

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

FORBIDDEN_PHRASES = (
    "construction commenced", "construction has commenced", "development is underway", "development underway",
    "site inactive", "confirmed uncommenced", "owner not progressing", "owner is not progressing",
    "likely to sell", "willing to sell", "available for purchase", "physical works have started",
    "physical works started",
)


_NEGATION_CUES = ("does not", "do not", "never", "not itself", "not that", "not proof", "no evidence")


def _assert_no_forbidden_claims(*details: str | None) -> None:
    """Fails only on an unqualified ASSERTION of a forbidden claim - a
    sentence that explicitly NEGATES it (e.g. "does not itself establish
    that construction has commenced") is exactly the required safety
    language, not a violation. Checked per-sentence so a negation earlier
    in a long detail string can't accidentally excuse an unrelated,
    genuinely unqualified claim later in the same string."""
    for detail in details:
        lowered = (detail or "").lower()
        for sentence in lowered.split("."):
            for phrase in FORBIDDEN_PHRASES:
                if phrase in sentence and not any(cue in sentence for cue in _NEGATION_CUES):
                    raise AssertionError(f"unqualified forbidden phrase {phrase!r} found in sentence {sentence!r} (full detail: {detail!r})")


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


def _grant(session, site, *, decision_date: dt.date, related_search_checked_at=None) -> Application:
    app = _app(session, site.id, "REF/1", application_category="primary_residential",
               decision="Approve with Conditions", decision_issued_date=_portal_date(decision_date))
    if related_search_checked_at is not None:
        app.related_search_checked_at = related_search_checked_at
        session.commit()
    return app


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
    assert signals.implementation_activity_evidence_identified.state == NOT_APPLICABLE
    assert signals.wider_site_implementation_activity_context.state == NOT_APPLICABLE
    assert signals.no_qualifying_progress_evidence_identified.state == NOT_APPLICABLE
    assert signals.raw_lapse_status is None
    assert signals.raw_build_status is None
    assert signals.raw_decision_date is None
    assert signals.coverage_checked_at is None


def test_strategic_land_ownership_signal_is_still_meaningful(session):
    """matched_to_site is one of opportunity_change.py's own tracked
    strategic-land fingerprint fields - OWNERSHIP_OR_CONTROL_EVIDENCE_CHANGED
    remains a real, non-N/A question for STRATEGIC_LAND, unlike the
    development-progress signals."""
    opp = _FakeOpportunity("strategic_land:allocation:1", STRATEGIC_LAND)
    signals = build_transaction_signals(session, opp)
    assert signals.ownership_or_control_evidence_changed.state == UNKNOWN  # never monitored yet


# --- F. NON-REGRESSION: RECENT_PERMISSION -----------------------------------

def test_recent_permission_present_within_window(session):
    site = _site(session)
    recent_decision = dt.date.today() - dt.timedelta(days=30)
    _grant(session, site, decision_date=recent_decision)
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site, scope_verified=True)
    assert signals.recent_permission.state == PRESENT
    assert signals.raw_decision_date == recent_decision


def test_recent_permission_absent_outside_window(session):
    site = _site(session)
    old_decision = add_calendar_months(dt.date.today(), -(RECENT_PERMISSION_WINDOW_MONTHS + 6))
    _grant(session, site, decision_date=old_decision)
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site, scope_verified=True)
    assert signals.recent_permission.state == ABSENT


def test_recent_permission_absent_when_nothing_granted(session):
    site = _site(session)
    _app(session, site.id, "REF/1", decision=None, status="Under consideration")
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site, scope_verified=True)
    assert signals.recent_permission.state == ABSENT
    assert signals.raw_decision_date is None


# --- F. NON-REGRESSION: APPROACHING_IMPLEMENTATION_DEADLINE -----------------

def test_approaching_implementation_deadline_present_near_lapse(session):
    site = _site(session)
    near_lapse_decision = dt.date.today() - dt.timedelta(days=3 * 365 - 20)
    _grant(session, site, decision_date=near_lapse_decision)
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site, scope_verified=True)
    assert signals.approaching_implementation_deadline.state == PRESENT
    assert signals.raw_lapse_status == "approaching"


def test_approaching_implementation_deadline_absent_when_comfortably_distant(session):
    site = _site(session)
    recent_decision = dt.date.today() - dt.timedelta(days=60)
    _grant(session, site, decision_date=recent_decision)
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site, scope_verified=True)
    assert signals.approaching_implementation_deadline.state == ABSENT
    assert signals.raw_lapse_status == "safe"


# --- A. EPC SAFETY -----------------------------------------------------------

def test_epc_only_partially_complete_never_makes_implementation_activity_present(session):
    site = _site(session)
    recent_decision = dt.date.today() - dt.timedelta(days=60)
    _grant(session, site, decision_date=recent_decision, related_search_checked_at=dt.datetime.now(dt.timezone.utc))
    site.build_status = "partially_complete"  # EPC-only outcome, no portal filing at all
    session.commit()
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site, scope_verified=True)
    assert signals.implementation_activity_evidence_identified.state != PRESENT
    assert signals.raw_build_status == "partially_complete"  # still visible as secondary/raw context


def test_epc_only_complete_never_makes_implementation_activity_present(session):
    site = _site(session)
    recent_decision = dt.date.today() - dt.timedelta(days=60)
    _grant(session, site, decision_date=recent_decision, related_search_checked_at=dt.datetime.now(dt.timezone.utc))
    site.build_status = "complete"  # EPC-only outcome, no portal filing at all
    session.commit()
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site, scope_verified=True)
    assert signals.implementation_activity_evidence_identified.state != PRESENT
    assert signals.raw_build_status == "complete"


def test_no_partially_complete_field_exists_on_transaction_signals(session):
    """PARTIALLY_COMPLETE has been removed as a primary V1 signal."""
    opp = _FakeOpportunity("strategic_land:allocation:1", STRATEGIC_LAND)
    signals = build_transaction_signals(session, opp)
    assert not hasattr(signals, "partially_complete")
    assert not hasattr(signals, "development_underway")
    assert not hasattr(signals, "no_identified_development_progress")


# --- B. POSITIVE PLANNING EVIDENCE ------------------------------------------

def test_qualifying_planning_activity_makes_implementation_activity_present(session):
    site = _site(session)
    recent_decision = dt.date.today() - dt.timedelta(days=60)
    _grant(session, site, decision_date=recent_decision)
    # A genuine, authoritative post-permission planning-portal filing.
    _app(session, site.id, "REF/1-DOC", application_category="condition_discharge_or_details",
         proposal="Discharge of pre-commencement conditions 3 and 4",
         application_received=_portal_date(dt.date.today() - dt.timedelta(days=10)))
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site, scope_verified=True)
    assert signals.implementation_activity_evidence_identified.state == PRESENT
    detail = signals.implementation_activity_evidence_identified.detail or ""
    assert "REF/1-DOC" in detail
    assert "condition_discharge_or_details" in detail
    _assert_no_forbidden_claims(detail)


def test_implementation_activity_unknown_never_absent_when_nothing_found(session):
    """Correction: an absence of qualifying planning activity must never
    become a confirmed 'no activity' fact - PRESENT or UNKNOWN only."""
    site = _site(session)
    recent_decision = dt.date.today() - dt.timedelta(days=60)
    _grant(session, site, decision_date=recent_decision)
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site, scope_verified=True)
    assert signals.implementation_activity_evidence_identified.state == UNKNOWN
    assert signals.implementation_activity_evidence_identified.state != ABSENT


# --- C. COVERAGE -------------------------------------------------------------

def test_no_qualifying_progress_evidence_unknown_when_coverage_never_run(session):
    site = _site(session)
    recent_decision = dt.date.today() - dt.timedelta(days=60)
    _grant(session, site, decision_date=recent_decision, related_search_checked_at=None)
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site, scope_verified=True)
    assert signals.no_qualifying_progress_evidence_identified.state == UNKNOWN
    assert signals.coverage_checked_at is None


def test_no_qualifying_progress_evidence_present_with_coverage_and_verified_scope(session):
    site = _site(session)
    recent_decision = dt.date.today() - dt.timedelta(days=60)
    checked_at = dt.datetime.now(dt.timezone.utc)
    _grant(session, site, decision_date=recent_decision, related_search_checked_at=checked_at)
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site, scope_verified=True)
    assert signals.no_qualifying_progress_evidence_identified.state == PRESENT
    assert signals.coverage_checked_at is not None
    detail = signals.no_qualifying_progress_evidence_identified.detail or ""
    _assert_no_forbidden_claims(detail)
    assert "does not mean" in detail.lower()


def test_no_qualifying_progress_evidence_unknown_when_scope_unverified_even_with_coverage(session):
    site = _site(session)
    recent_decision = dt.date.today() - dt.timedelta(days=60)
    _grant(session, site, decision_date=recent_decision, related_search_checked_at=dt.datetime.now(dt.timezone.utc))
    opp = _FakeOpportunity("planning_delivery:phase:1:PhaseTwo", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site, scope_verified=False)
    assert signals.no_qualifying_progress_evidence_identified.state == UNKNOWN


# --- D. SCOPE ----------------------------------------------------------------

def test_verified_scope_exposes_the_signal_normally(session):
    site = _site(session)
    recent_decision = dt.date.today() - dt.timedelta(days=60)
    _grant(session, site, decision_date=recent_decision)
    _app(session, site.id, "REF/1-DOC", application_category="condition_discharge_or_details",
         proposal="Discharge of pre-commencement conditions",
         application_received=_portal_date(dt.date.today() - dt.timedelta(days=10)))
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site, scope_verified=True)
    assert signals.implementation_activity_evidence_identified.state == PRESENT
    assert signals.wider_site_implementation_activity_context.state == PRESENT


def test_unverified_named_phase_does_not_inherit_confident_whole_site_signal(session):
    """The confirmed live production defect: a named phase with
    scope_verified=False must never present wider-site activity as an
    opportunity-level fact."""
    site = _site(session)
    recent_decision = dt.date.today() - dt.timedelta(days=60)
    _grant(session, site, decision_date=recent_decision)
    _app(session, site.id, "REF/1-DOC", application_category="condition_discharge_or_details",
         proposal="Discharge of pre-commencement conditions",
         application_received=_portal_date(dt.date.today() - dt.timedelta(days=10)))
    opp = _FakeOpportunity("planning_delivery:phase:1:PhaseTwo", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site, scope_verified=False)
    # The opportunity-level signal must NOT confidently claim PRESENT...
    assert signals.implementation_activity_evidence_identified.state == UNKNOWN
    # ...but the wider-site finding is preserved, not thrown away.
    assert signals.wider_site_implementation_activity_context.state == PRESENT
    detail = signals.implementation_activity_evidence_identified.detail or ""
    assert "wider" in detail.lower() and "not been verified" in detail.lower()


def test_scope_verified_flag_is_exposed_verbatim(session):
    site = _site(session)
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=[], site=site, scope_verified=True)
    assert signals.scope_verified is True
    signals_unverified = build_transaction_signals(session, opp, applications=[], site=site, scope_verified=False)
    assert signals_unverified.scope_verified is False


# --- E. TERMINOLOGY -----------------------------------------------------------

def test_no_forbidden_terminology_across_a_representative_scenario(session):
    site = _site(session)
    recent_decision = dt.date.today() - dt.timedelta(days=60)
    _grant(session, site, decision_date=recent_decision, related_search_checked_at=dt.datetime.now(dt.timezone.utc))
    _app(session, site.id, "REF/1-DOC", application_category="condition_discharge_or_details",
         proposal="Discharge of pre-commencement conditions",
         application_received=_portal_date(dt.date.today() - dt.timedelta(days=10)))
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site, scope_verified=True)
    _assert_no_forbidden_claims(
        signals.recent_permission.detail, signals.approaching_implementation_deadline.detail,
        signals.implementation_activity_evidence_identified.detail,
        signals.wider_site_implementation_activity_context.detail,
        signals.no_qualifying_progress_evidence_identified.detail,
        signals.ownership_or_control_evidence_changed.detail,
    )


# --- F. NON-REGRESSION: OWNERSHIP_OR_CONTROL_EVIDENCE_CHANGED ---------------

def test_ownership_evidence_changed_unknown_without_any_monitoring_baseline(session):
    site = _site(session)
    recent_decision = dt.date.today() - dt.timedelta(days=60)
    _grant(session, site, decision_date=recent_decision)
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=_apps_for(session, site), site=site, scope_verified=True)
    assert signals.ownership_or_control_evidence_changed.state == UNKNOWN


def test_ownership_evidence_changed_present_reflects_evidence_not_ownership(session):
    session.add(OpportunityMonitoringState(
        opportunity_id="planning_delivery:site:1", opportunity_type="planning_delivery",
        fingerprint="fp-after", fingerprint_fields="{}",
        last_change_classification="MATERIALLY_CHANGED", last_change_reasons="ownership_evidence_changed",
    ))
    session.commit()
    opp = _FakeOpportunity("planning_delivery:site:1", PLANNING_DELIVERY)
    signals = build_transaction_signals(session, opp, applications=[], site=_site(session), scope_verified=True)
    assert signals.ownership_or_control_evidence_changed.state == PRESENT
    detail = signals.ownership_or_control_evidence_changed.detail or ""
    assert "does not itself establish" in detail or "does not establish" in detail
    for forbidden in ("ownership has changed", "control has changed", "new owner"):
        assert forbidden not in detail.lower()
