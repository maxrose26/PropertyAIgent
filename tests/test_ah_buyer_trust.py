"""AH evidence trust regressions; synthetic SQLite only, no model calls."""
from dataclasses import replace
import pytest
from app.db.models import Application
from app.policy.buyer_matching import (
    build_planning_delivery_matching_facts_from_operative,
    build_planning_delivery_matching_facts, assess_buyer_fit,
    STRONG_FIT, INSUFFICIENT_EVIDENCE, NOT_SUITABLE,
)
from app.policy.buyer_profiles import NESTEN_HOMES, HOUSING_ASSOCIATION
from app.reporting.scheme_reconciliation import build_operative_planning_facts
from tests.test_agent_ready_fact_foundation import _make_planning_delivery_site


def make(session, units, pct, total=82, classification=None):
    site = _make_planning_delivery_site(session, unit_count=total)
    app = session.query(Application).filter_by(site_id=site.id).one()
    si = app.scheme_intelligence
    si.affordable_units_final = units
    si.affordable_percentage_final = pct
    si.affordable_data_status = classification
    si.affordable_housing_status = 'conditioned'
    si.affordable_housing_notes = 'Recorded residential affordable provision.'
    si.development_type = 'houses'
    si.affordable_missing = False
    session.flush()
    facts = build_planning_delivery_matching_facts_from_operative(build_operative_planning_facts([app]), [app])
    return app, facts


@pytest.mark.parametrize('units,pct', [(0,0), (41,50), (82,100)])
def test_sound_values_preserved(session, units, pct):
    app, facts = make(session, units, pct)
    assert facts.affordable_percentage == pct
    assert facts.affordable_percentage_trusted
    assert facts.affordable_unit_count == units
    assert facts.affordable_review_reason is None
    result = assess_buyer_fit(NESTEN_HOMES, facts)
    assert result.classification == (NOT_SUITABLE if pct == 100 else STRONG_FIT)


@pytest.mark.parametrize('units,pct,classification', [
    (72,100,'all_units_affordable'), (41,100,None),
    (41,50,'all_units_affordable'), (81,100,None), (90,110,None),
])
def test_contradictions_do_not_support_definitive_ah_claim(session, units, pct, classification):
    app, facts = make(session, units, pct, classification=classification)
    assert facts.affordable_percentage is None
    assert not facts.affordable_percentage_trusted
    assert facts.affordable_unit_count == units
    assert facts.affordable_reported_percentage == pct
    assert facts.affordable_source_reference == app.reference
    assert app.scheme_intelligence.affordable_percentage_final == pct
    for buyer in (NESTEN_HOMES, HOUSING_ASSOCIATION):
        result = assess_buyer_fit(buyer, facts)
        assert result.classification == INSUFFICIENT_EVIDENCE
        assert result.investigate
        assert not any('wholly' in message for message in result.matches + result.does_not_match)
    legacy = build_planning_delivery_matching_facts(app.scheme_intelligence)
    assert legacy.affordable_percentage is None
    assert legacy.affordable_reported_percentage == pct


def test_unknown_stays_unknown(session):
    app, facts = make(session, None, None)
    assert facts.affordable_percentage is None
    assert facts.affordable_unit_count is None
    assert assess_buyer_fit(NESTEN_HOMES, facts).classification == INSUFFICIENT_EVIDENCE


def test_denominator_source_mismatch_requires_review(session):
    app, _ = make(session, 41, 50)
    operative = build_operative_planning_facts([app])
    quantum = operative.consented_position.approved_units
    mismatched = replace(quantum, source=replace(quantum.source, application_id=app.id + 999))
    operative = replace(operative, consented_position=replace(operative.consented_position, approved_units=mismatched))
    facts = build_planning_delivery_matching_facts_from_operative(operative, [app])
    assert facts.affordable_unit_count == 41
    assert facts.affordable_percentage is None
    assert facts.affordable_review_reason


def test_unrelated_specialist_exclusion_is_preserved(session):
    _, facts = make(session, 72, 100, classification='all_units_affordable')
    facts = replace(facts, is_specialist_development=True, development_type_raw='retirement')
    result = assess_buyer_fit(NESTEN_HOMES, facts)
    assert result.classification == NOT_SUITABLE
    assert result.investigate
    assert not any('wholly' in message for message in result.does_not_match)


def test_untrusted_percentage_never_drives_wholly_affordable_rule(session):
    _, facts = make(session, 82, 100)
    facts = replace(facts, affordable_percentage_trusted=False)
    result = assess_buyer_fit(NESTEN_HOMES, facts)
    assert result.classification == INSUFFICIENT_EVIDENCE
    assert not any('wholly' in message for message in result.does_not_match)
