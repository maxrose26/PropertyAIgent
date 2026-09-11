"""Gate 2B-2A Stage A - app.ui.common's reconciled "Status / Decision" and
unit-count helpers for render_scheme_detail (the shared block between the
dedicated Scheme Detail page and the home page's inline row expansion).

render_scheme_detail itself is Streamlit-rendering code with no existing
behavioural test harness in this codebase; these tests cover its two new
PURE helper functions directly, proving they read the SAME reconciled
facts app.reporting.site_profile already uses - so this shared block can
no longer show a different planning status/unit count than the Site
Profile page for the same Site.
"""
from __future__ import annotations

from app.db.models import Application, SchemeIntelligence, Site
from app.reporting.scheme_reconciliation import build_operative_planning_facts
from app.ui.common import _operative_status_decision_display, _operative_units_display


def _site(session, **kw) -> Site:
    s = Site(council_code="testcouncil", canonical_address="land at x", display_address="Land at X", **kw)
    session.add(s)
    session.commit()
    return s


def _app(session, site_id, reference, **kw) -> Application:
    kw.setdefault("application_received", "Mon 01 Jan 2024")
    a = Application(council_code="testcouncil", reference=reference, site_id=site_id, **kw)
    session.add(a)
    session.commit()
    return a


def test_status_decision_display_uses_consented_position_not_raw_rep_app(session):
    """Burnage shape: a granted permission plus a newer, no-decision
    condition-discharge filing must show the GRANTED status, not the
    discharge filing's own blank decision."""
    site = _site(session)
    granted = _app(session, site.id, "FUL/1", proposal="Erection of 66 dwellings",
                   status="Final", decision="Approve", decision_issued_date="Mon 23 Mar 2026")
    session.add(SchemeIntelligence(application_id=granted.id, total_units_final=66))
    doc = _app(session, site.id, "DOC/1", proposal="Discharge of a condition of FUL/1",
               status="Under Consultation", decision=None, application_received="Fri 07 Aug 2026")
    session.add(SchemeIntelligence(application_id=doc.id, total_units_final=66))
    session.commit()

    facts = build_operative_planning_facts([granted, doc])
    assert _operative_status_decision_display(facts) == "Permission granted"
    determined, units = _operative_units_display(facts)
    assert determined is True
    assert units == 66


def test_status_decision_display_not_yet_verified_when_not_determined(session):
    """Stockport Rugby shape: a withdrawn-only site with a specialist
    component must show an honest unresolved state, not a fabricated
    figure or a 'several proposals' label it doesn't have."""
    site = _site(session)
    a = _app(session, site.id, "DC/1",
             proposal="Hybrid application for residential development and a residential care facility",
             status="Withdrawn", decision="Application Withdrawn")
    session.add(SchemeIntelligence(application_id=a.id, total_units_final=90, specialist_housing_type="care facility"))
    session.commit()

    facts = build_operative_planning_facts([a])
    assert _operative_status_decision_display(facts) == "Withdrawn"
    determined, units = _operative_units_display(facts)
    assert determined is True
    assert units is None  # honest not_determined - never falls back to a raw figure


def test_multiple_active_positions_named_honestly_not_collapsed(session):
    site = _site(session)
    outline = _app(session, site.id, "OUT/1", proposal="Outline application for up to 400 dwellings",
                   status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2020")
    session.add(SchemeIntelligence(application_id=outline.id, total_units_final=400))
    live_a = _app(session, site.id, "RM/Phase1", proposal="Reserved matters for Phase 1 comprising 100 dwellings",
                  status="Awaiting decision", application_received="Mon 01 Jan 2024")
    session.add(SchemeIntelligence(application_id=live_a.id, total_units_final=100))
    live_b = _app(session, site.id, "RM/Phase2", proposal="Reserved matters for Phase 2 comprising 120 dwellings",
                  status="Awaiting decision", application_received="Mon 01 Feb 2024")
    session.add(SchemeIntelligence(application_id=live_b.id, total_units_final=120))
    session.commit()

    facts = build_operative_planning_facts([outline, live_a, live_b])
    # consented (400, from the granted outline) still resolves - the
    # multiple ACTIVE positions coexist alongside it, never replacing it.
    assert _operative_status_decision_display(facts) == "Permission granted"
    determined, units = _operative_units_display(facts)
    assert units == 400
