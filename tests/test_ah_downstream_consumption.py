"""Narrow AH consumer tests; disposable SQLite fixture, no external calls."""
from dataclasses import replace
from types import SimpleNamespace

import pandas as pd
import pytest

from app.db.models import Application, SchemeIntelligence
from app.policy.buyer_matching import (
    PLANNING_DELIVERY, B2MatchingContext,
    build_planning_delivery_matching_facts_from_operative,
)
from app.reporting.affordable_housing_scope import select_affordable_position_for_scope
from app.reporting.opportunity_intelligence_packet import build_opportunity_intelligence_packet, UNKNOWN
from app.reporting.scheme_reconciliation import build_operative_planning_facts
from app.ui.housing_type import explicit_affordable_maximum_mask
from tests.test_agent_ready_fact_foundation import _make_planning_delivery_site


def test_explicit_maximum_never_counts_unknown_as_zero():
    counts = pd.Series([None, 0, 1, 10], dtype='Float64')
    assert explicit_affordable_maximum_mask(counts, 0).tolist() == [False, True, False, False]
    assert explicit_affordable_maximum_mask(counts, 5).tolist() == [False, True, True, False]


def _summary(**kwargs):
    defaults = dict(whole_site=None, active_whole_site=None, phases=(), active_phases=(), conflicts=())
    return SimpleNamespace(**(defaults | kwargs))


def test_scope_selection_cannot_borrow_whole_site_or_guess_parcel_kind():
    whole = SimpleNamespace(scope_label='Whole site')
    phase = SimpleNamespace(scope_label='Phase 2')
    parcel = SimpleNamespace(scope_label='Plot 2')
    assert select_affordable_position_for_scope(_summary(whole_site=whole), phase_code='2') is None
    assert select_affordable_position_for_scope(_summary(whole_site=whole, phases=(phase,)), phase_code='2') is phase
    assert select_affordable_position_for_scope(_summary(phases=(phase, parcel)), phase_code='2') is None


def test_conflict_does_not_fall_back_to_active_or_another_scope():
    active = SimpleNamespace(scope_label='Whole site')
    conflict = SimpleNamespace(scope_type='whole_site', scope_label='Whole site')
    assert select_affordable_position_for_scope(_summary(active_whole_site=active, conflicts=(conflict,)), active_position_count=1) is None
    assert select_affordable_position_for_scope(_summary(active_whole_site=active), active_position_count=2) is None


@pytest.mark.parametrize('units,percentage,status', [(30,30.0,'conditioned'), (0,0.0,'conditioned'), (30,30.0,'unknown'), (30,30.0,'   ')])
def test_packet_uses_one_current_position_not_first_historical_status(session, units, percentage, status):
    site = _make_planning_delivery_site(session, unit_count=100)
    historic = session.query(Application).filter_by(site_id=site.id).one()
    historic.status = historic.decision = 'Withdrawn'
    historic.scheme_intelligence.affordable_units_final = 400
    historic.scheme_intelligence.affordable_percentage_final = 100
    historic.scheme_intelligence.affordable_housing_status = 'legally_secured'
    current = Application(council_code='testcouncil', reference='CURRENT/1', site_id=site.id,
        status='Decided', decision='Granted', application_category='full', application_type='Full Application',
        proposal='Full application for the erection of residential dwellings')
    session.add(current); session.flush()
    session.add(SchemeIntelligence(application_id=current.id, total_units_final=100,
        affordable_units_final=units, affordable_percentage_final=percentage,
        affordable_housing_status=status, core_intelligence_complete=True,
        affordable_housing_notes='The scheme provides the stated affordable homes.'))
    session.commit()
    apps = [historic, current]
    operative = build_operative_planning_facts(apps)
    facts = build_planning_delivery_matching_facts_from_operative(operative, apps)
    # Deliberately stale caller AH facts must not leak into the coherent packet.
    facts = replace(facts, affordable_unit_count=400, affordable_percentage=100)
    opp = SimpleNamespace(opportunity_id=f'planning_delivery:site:{site.id}',
        opportunity_type=PLANNING_DELIVERY, matching_facts=facts)
    context = B2MatchingContext(council_code='testcouncil', development_state='unknown')
    packet = build_opportunity_intelligence_packet(session, opp, context=context)
    # Spec020: a stored number is not source-qualified KNOWN evidence.
    # Keep the original application's reported value in the explicit payload,
    # including zero, rather than losing it or inheriting stale caller values.
    assert packet.affordable_units.state == UNKNOWN
    assert packet.affordable_units.value is None
    assert packet.affordable_assessment.count.value == units
    assert packet.affordable_assessment.count.application_reference == current.reference
    assert packet.affordable_assessment.count.stage == status
    assert not packet.affordable_assessment.count.qualified
    assert packet.affordable_percentage.value == percentage
    assert packet.affordable_housing_status.value == (None if status.strip() in ('', 'unknown') else status)
    if status.strip() in ('', 'unknown'):
        assert packet.affordable_housing_status.state == UNKNOWN
    # A different packet denominator must never inherit the same percentage.
    opp.matching_facts = replace(facts, unit_count=400)
    assert build_opportunity_intelligence_packet(session, opp, context=context).affordable_percentage.state == UNKNOWN


def test_packet_missing_evidence_stays_unknown(session):
    site = _make_planning_delivery_site(session, unit_count=100)
    apps = session.query(Application).filter_by(site_id=site.id).all()
    facts = build_planning_delivery_matching_facts_from_operative(build_operative_planning_facts(apps), apps)
    opp = SimpleNamespace(opportunity_id=f'planning_delivery:site:{site.id}', opportunity_type=PLANNING_DELIVERY, matching_facts=facts)
    packet = build_opportunity_intelligence_packet(session, opp, context=B2MatchingContext(council_code='testcouncil', development_state='unknown'))
    assert packet.affordable_units.state == packet.affordable_percentage.state == packet.affordable_housing_status.state == UNKNOWN
