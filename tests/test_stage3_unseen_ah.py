"""Six real-source holdouts frozen at beb26dd before software comparison.

Manual source-faithful inputs, not a claim about model extraction or live data.
Frozen source expectations live in docs/acceptance/stage3-unseen.
"""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.db.models import Application, Council, SchemeIntelligence, Site
from app.policy.ah_assessment import AHAssessment, AHClaim, TenureClaim
from app.policy.buyer_matching import (
    B2MatchingContext, PLANNING_DELIVERY,
    build_planning_delivery_matching_facts_from_operative,
)
from app.reporting.ah_kpi import affordable_count_kpi
from app.reporting.affordable_housing_scope import format_affordable_housing_lines
from app.reporting.dashboard import _scheme_card
from app.reporting.opportunity_feed import _attach_planning_delivery_matching_facts
from app.reporting.opportunity_intelligence_packet import build_opportunity_intelligence_packet, UNKNOWN
from app.reporting.residential_mix import build_residential_mix, build_affordable_tenure
from app.reporting.scheme_reconciliation import build_operative_planning_facts, resolve_operative_filter_facts

FROZEN = Path(__file__).resolve().parents[1] / 'docs/acceptance/stage3-unseen/FROZEN_EXPECTATIONS.json'
CASES = json.loads(FROZEN.read_text())['cases']
# Transcribed from official summaries/reports, no stored product AH answer read.
INPUTS = {
    71: ('Outline application for up to 80 dwellings; all matters reserved except access', 'Decided', 'Refused', None, None, 50.0,
         'Historical proposal: up to 40 AH; 75% social/affordable rent and 25% intermediate; 30/10 only at maximum scheme size',
         'Historical March2026 proposal only. Refused13April2026. Future S106 never proven executed.'),
    621: ('Hybrid application: full residential development of 309 dwellings and outline primary school', 'Under consideration', None, 309, 47, 15.2,
          'CONFLICTING: social rent 12; shared ownership 25 versus 35; bedroom breakdown inconsistent',
          'Committee resolution subject to S106; execution unknown. On-site AH. Proposed total47; shared ownership CONFLICTING25vs35. Residential denominator309; older312 superseded.'),
    24: ('Outline application for 2 semi-detached dwellings', 'Awaiting decision', None, 2, None, None, None, None),
    49: ('Reserved matters appearance and landscaping for a detached house following 22/00846/OUT', 'Decided', 'Approve', 1, None, None, None, None),
    208: ('Outline application for residential development of 3 dwellinghouses. All matters reserved', 'Decided', 'Refused', 3, None, None, None, None),
    16: ('Outline application for a six storey building comprising 40 flats', 'Unknown', 'Withdrawn by Applicant', 40, None, None, None, None),
}


def make_case(session, case):
    council = case['council_code']
    session.add(Council(code=council, name=council, base_url=case['summary_url'], date_field_mode='received', doc_system='idox'))
    site = Site(council_code=council, canonical_address=case['address'].lower(), display_address=case['address'])
    session.add(site); session.flush()
    proposal, status, decision, total, count, pct, tenure, notes = INPUTS[case['id']]
    app = Application(site_id=site.id, council_code=council, reference=case['reference'], address=case['address'],
        proposal=proposal, status=status, decision=decision, application_received='Wed 01 Jan 2025', summary_url=case['summary_url'])
    session.add(app); session.flush()
    app.scheme_intelligence = SchemeIntelligence(application_id=app.id, core_intelligence_complete=True,
        total_units_final=total, affordable_units_final=count, affordable_percentage_final=pct,
        affordable_tenure_split_final=tenure, affordable_housing_notes=notes,
        affordable_status_note=notes, affordable_classification_evidence=notes,
        affordable_housing_status='officer_recommended' if case['id'] in (71,621) else None)
    session.commit()
    return site, app


def test_frozen_expectations_have_not_changed():
    assert hashlib.sha256(FROZEN.read_bytes()).hexdigest() == '48fbab1c8bce266de83f932ac4c2b485da837d003c7ed2eba6fcb317372945dc'


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['reference'])
def test_holdout_existing_consumers(session, case):
    site, app = make_case(session, case)
    facts = build_operative_planning_facts([app])
    selected = resolve_operative_filter_facts(facts, application_reference=app.reference)
    assessment = selected.affordable_assessment
    # Existing importer is absent: manual legacy source transcription is reported,
    # never magically trusted. This is SAFE_UNKNOWN for numeric buyer gates.
    assert not assessment.count.qualified
    assert assessment.search(minimum=1) == 'unknown'
    assert assessment.search(maximum=0) == 'unknown'
    assert affordable_count_kpi(assessment) == 'N/A'
    columns = assessment.columns()  # same AH columns used by Explore and CSV
    assert columns['AH Qualified'] is False
    assert 'operative terms unverified' in columns['AH Stage']
    current = case['id'] not in (71,208,16)
    mix = build_residential_mix(site, [app], rep_app=app if current else None)
    assert not mix['affordable_assessment'].count.qualified
    assert mix['affordable_assessment'].search(maximum=0) == 'unknown'
    buyer = build_planning_delivery_matching_facts_from_operative(facts, [app], application_reference=app.reference)
    assert buyer.affordable_unit_count is None
    assert buyer.affordable_percentage is None
    cards = [{'params': {'site_id': str(site.id)}, 'application_reference': app.reference}]
    _attach_planning_delivery_matching_facts(session, cards)
    assert cards[0]['matching_facts'].affordable_unit_count is None
    packet = build_opportunity_intelligence_packet(session,
        SimpleNamespace(opportunity_id=f'planning_delivery:site:{site.id}', opportunity_type=PLANNING_DELIVERY, matching_facts=buyer),
        context=B2MatchingContext(council_code=case['council_code']))
    assert packet.affordable_units.state == UNKNOWN
    assert packet.affordable_percentage.state == UNKNOWN
    dashboard = _scheme_card(app, why='Holdout', when=None, operative_facts=facts)
    explanations = '\n'.join(format_affordable_housing_lines(facts.affordable_housing))
    if case['id'] == 621:
        assert assessment.count.value == 47
        assert assessment.reported_percentage == 15.2
        assert 'CONFLICTING' in columns['AH Reported Tenure']
        assert '25 versus 35' in columns['AH Reported Tenure']
        assert 'CONFLICTING' in explanations
        assert dashboard['affordable_units'] == 47  # rendered explicitly as reported/unverified
    else:
        assert assessment.count.value is None
        assert dashboard['affordable_units'] is None
    if case['id'] == 71:
        assert 'HISTORICAL / REFUSED' in explanations
        assert not facts.affordable_housing.active_whole_site
    print(json.dumps({'case':case['reference'], 'explore_export':columns,
        'profile':mix['structured_summary'], 'buyer_count':buyer.affordable_unit_count,
        'feed_count':cards[0]['matching_facts'].affordable_unit_count,
        'packet_count_state':packet.affordable_units.state,
        'dashboard_reported_count':dashboard['affordable_units'], 'explanation':explanations}, default=str))


def test_bolton_source_bound_is_not_a_point_or_legal_proof():
    claim = AHClaim(upper=40, qualifier='up_to', state='verified', application_reference='21082/25',
        scope_type='whole_site', scope_label='Historical refused outline proposal', stage='historical_proposed_refused',
        source_url='https://bolton.moderngov.co.uk/documents/s13300/Land%20north%20of%20Arthur%20Lane.pdf',
        document_date='2026-03-26', passage='up to 40 affordable houses')
    a = AHAssessment(count=claim, reported_percentage=50)
    assert claim.qualified and claim.value is None
    assert affordable_count_kpi(a) == 'Up to 40'
    assert a.search(minimum=41) == 'does_not_meet'
    assert 'operative terms unverified' in a.stage_label()
    assert a.columns()['AH Upper Bound'] == 40
    assert a.columns()['AH Reported Count'] is None


def test_rochdale_source_tenure_conflict_is_not_silently_corrected():
    source='https://rochdale.moderngov.co.uk/documents/s119316/Application%202400581HYBR%20-%20Land%20to%20the%20West%20of%20Hollingworth%20Road.pdf'
    base=dict(application_reference='24/00581/HYBR',scope_type='component',scope_label='Residential component of hybrid proposal',
              source_url=source,document_date='2025-11-27',stage='proposed_subject_to_s106')
    a=AHAssessment(count=AHClaim(value=47,qualifier='exact',state='verified',passage='47 affordable housing units',**base),
        reported_percentage=15.2,reported_tenure='CONFLICTING: shared ownership25vs35',
        tenures=(TenureClaim('Social rent',AHClaim(value=12,qualifier='exact',state='verified',passage='12 social rent homes',**base)),
                 TenureClaim('Shared ownership CONFLICTING25vs35',AHClaim(state='conflicting',review_reason='Paragraph7.29 says35;2.6/7.248 say25; no correction authorised',**base))))
    assert a.count.qualified
    assert affordable_count_kpi(a) == 'N/A'  # component cannot become whole-site KPI
    assert a.search(maximum=47) == 'investigate'
    rendered=build_affordable_tenure(None,{'state':'verified'},a)
    assert any('CONFLICTING25vs35' in s and 'conflicting' in s for s in rendered['categories'])
    assert not a.tenures[1].claim.qualified
    assert 'operative terms unverified' in a.stage_label()
    assert 'conflicting' in a.columns()['AH Explicit Tenure Claims']
