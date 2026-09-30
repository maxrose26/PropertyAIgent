"""Specification 020 integration tests. Disposable SQLite fixture only."""
from dataclasses import replace
from types import SimpleNamespace
import pytest

from app.db.models import Application
from app.policy.ah_assessment import AHAssessment
from app.policy.buyer_matching import (
    assess_buyer_fit, build_planning_delivery_matching_facts,
    build_planning_delivery_matching_facts_from_operative,
    INSUFFICIENT_EVIDENCE, NOT_SUITABLE, B2MatchingContext,
)
from app.policy.buyer_profiles import HOUSING_ASSOCIATION, NESTEN_HOMES
from app.reporting.scheme_reconciliation import build_operative_planning_facts, resolve_operative_filter_facts
from app.reporting.opportunity_intelligence_packet import build_opportunity_intelligence_packet, UNKNOWN
from app.reporting.site_profile import _ah_position
from app.reporting.opportunity_feed import _attach_planning_delivery_matching_facts
from tests.test_agent_ready_fact_foundation import _make_planning_delivery_site
from verification.test_ah_assessment import claim


def record(session):
    site = _make_planning_delivery_site(session, unit_count=82)
    application = session.query(Application).filter_by(site_id=site.id).one()
    si = application.scheme_intelligence
    si.affordable_units_final = 72
    si.affordable_percentage_final = 100
    si.affordable_data_status = 'all_units_affordable'
    si.affordable_housing_status = 'proposed'
    si.affordable_classification_evidence = 'Synthetic: approximately 72 retirement apartments and 10 market houses.'
    session.flush()
    operative = build_operative_planning_facts([application])
    return site, application, operative


def test_same_record_legacy_provenance_across_consumers(session):
    site, app, operative = record(session)
    filters = resolve_operative_filter_facts(operative)
    facts = build_planning_delivery_matching_facts_from_operative(operative, [app])
    position = operative.affordable_housing.whole_site or operative.affordable_housing.active_whole_site
    assert position is not None
    detail = _ah_position(position)
    packet = build_opportunity_intelligence_packet(session,
        SimpleNamespace(opportunity_id=f'planning_delivery:site:{site.id}', opportunity_type='planning_delivery',
            kind='site', entity_id=site.id, phase_code=None, matching_facts=facts), context=B2MatchingContext())
    cards = [{'params': {'site_id': str(site.id)}}]
    _attach_planning_delivery_matching_facts(session, cards)
    expected = filters.affordable_assessment.payload()
    assert detail['assessment'] == expected
    assert facts.affordable_assessment.payload() == expected
    assert packet.affordable_assessment.payload() == expected
    assert cards[0]['matching_facts'].affordable_assessment.payload() == expected
    assert packet.affordable_units.state == UNKNOWN
    # Exactly the projection used by Explore and its selected-record CSV.
    assert filters.affordable_assessment.columns()['AH Reported Count'] == 72
    assert filters.affordable_assessment.columns()['AH Qualified'] is False
    assert filters.affordable_assessment.search(minimum=50) == 'unknown'
    assert app.scheme_intelligence.affordable_percentage_final == 100


def test_both_builders_do_not_qualify_raw_counts(session):
    _, app, operative = record(session)
    single=build_planning_delivery_matching_facts(app.scheme_intelligence)
    multi=build_planning_delivery_matching_facts_from_operative(operative,[app])
    assert single.affordable_assessment.search(minimum=50) == 'unknown'
    assert multi.affordable_assessment.search(minimum=50) == 'unknown'
    for assessment in (single.affordable_assessment, multi.affordable_assessment):
        assert assessment.count.value == 72
        assert assessment.count.application_reference == app.reference
        assert assessment.count.stage == 'proposed'
        assert not assessment.count.qualified
    assert single.affordable_assessment.count.scope_type == 'unclear'


def test_independent_qualified_count_survives_percentage_conflict(session):
    _, app, operative = record(session)
    facts=build_planning_delivery_matching_facts_from_operative(operative,[app])
    a=AHAssessment(count=claim(),reported_percentage=100,percentage_review_reason='Conflicting denominator')
    result=assess_buyer_fit(HOUSING_ASSOCIATION,replace(facts,affordable_assessment=a))
    assert result.classification == INSUFFICIENT_EVIDENCE
    assert result.is_investigative_exception
    assert any('likely_meets' in message for message in result.unknown)
    assert not result.does_not_match
    assert facts.affordable_review_reason


def test_retirement_exclusion_still_wins(session):
    _, app, operative = record(session)
    facts=build_planning_delivery_matching_facts_from_operative(operative,[app])
    facts=replace(facts,affordable_assessment=AHAssessment(count=claim()),
                  is_specialist_development=True,development_type_raw='retirement')
    result = assess_buyer_fit(NESTEN_HOMES,facts)
    assert result.classification == NOT_SUITABLE
    assert any('specialist development' in reason for reason in result.does_not_match)


def test_exact_retirement_component_count_does_not_qualify_whole_scheme_classification(session):
    # Offline acceptance projection, not an import of real production claims.
    _, app, operative = record(session)
    facts = build_planning_delivery_matching_facts_from_operative(operative, [app])
    evidence = claim(value=72, qualifier='exact', state='verified',
        scope_type='component', scope_label='Retirement apartments',
        application_reference=app.reference, stage='proposed',
        passage='72 affordable retirement apartments within an 82-home scheme.')
    facts = replace(facts, affordable_assessment=AHAssessment(count=evidence),
                    is_specialist_development=True, development_type_raw='retirement')
    # A component proves a minimum, not a whole-scheme maximum. The fixed
    # HA pilot has a 300-home maximum; this task is specifically 50+.
    result = assess_buyer_fit(replace(HOUSING_ASSOCIATION, target_unit_max=None), facts)
    reasons = result.matches + result.unknown + result.does_not_match + result.investigate
    assert any('AH count assessment: meets' in reason for reason in reasons)
    assert not any('Trusted evidence shows this is a wholly' in reason for reason in reasons)
    assert not result.does_not_match
    assert assess_buyer_fit(NESTEN_HOMES, facts).classification == NOT_SUITABLE
    assert facts.affordable_assessment.count.stage == 'proposed'
    assert not facts.affordable_percentage_trusted
    bounded = assess_buyer_fit(HOUSING_ASSOCIATION, facts)
    assert any('AH count assessment: investigate' in reason for reason in bounded.unknown)


@pytest.mark.parametrize('value', [0, 20, 48, 90, 120])
def test_legacy_counts_remain_investigative_not_qualified(value):
    from tests.test_buyer_matching import _facts
    from tests.ah_claim_fixtures import verified_count
    facts = _facts(affordable_unit_count=value)
    result = assess_buyer_fit(HOUSING_ASSOCIATION, facts, context=B2MatchingContext())
    assert result.classification == INSUFFICIENT_EVIDENCE
    assert result.is_investigative_exception
    assert not result.does_not_match
    assert not any('Source-qualified' in reason for reason in result.matches)
    assert any(str(value) in reason and 'unknown' in reason for reason in result.unknown)
    qualified = assess_buyer_fit(HOUSING_ASSOCIATION,
        replace(facts, affordable_assessment=verified_count(value)), context=B2MatchingContext())
    assert qualified.classification == (NOT_SUITABLE if value < 50 else 'STRONG_FIT')


def test_matching_keeps_inclusive_band_in_both_directions():
    from tests.test_buyer_matching import _facts
    for value, minimum, maximum in ((44, 'does_not_meet', 'likely_meets'),
            (45, 'investigate', 'investigate'), (50, 'investigate', 'investigate'),
            (55, 'investigate', 'investigate'), (56, 'likely_meets', 'does_not_meet')):
        facts = _facts(affordable_assessment=AHAssessment(count=claim(value=value)))
        for profile, expected in ((HOUSING_ASSOCIATION, minimum),
                (replace(HOUSING_ASSOCIATION, target_unit_min=0, target_unit_max=50), maximum)):
            result = assess_buyer_fit(profile, facts)
            reasons = result.matches + result.unknown + result.does_not_match + result.investigate
            assert any(f'AH count assessment: {expected}' in reason for reason in reasons)
            if expected == 'investigate':
                assert result.classification == INSUFFICIENT_EVIDENCE
                assert result.is_investigative_exception


def test_verified_source_range_is_still_only_likely_package():
    from tests.test_buyer_matching import _facts
    from app.policy.buyer_profiles import AFFORDABLE_HOUSING_PACKAGE
    evidence = claim(value=None, qualifier='range', state='verified', lower=60, upper=80)
    result = assess_buyer_fit(replace(NESTEN_HOMES,
        acquisition_types=frozenset({AFFORDABLE_HOUSING_PACKAGE})),
        _facts(affordable_assessment=AHAssessment(count=evidence)), context=B2MatchingContext())
    assert result.classification == INSUFFICIENT_EVIDENCE
    assert result.is_investigative_exception


def test_buyer_feed_retains_legacy_investigation(session):
    from app.reporting.opportunity_feed import _buyer_selection
    site, app, _ = record(session)
    cards, counts = _buyer_selection(session, [], [{
        'params': {'site_id': str(site.id)}, 'opportunity_type': 'planning_delivery',
    }], 5, 'housing_association')
    assert len(cards) == 1
    assert counts['excluded_not_suitable'] == 0
    assert cards[0]['buyer_fit'].classification == INSUFFICIENT_EVIDENCE
    assert cards[0]['buyer_fit'].is_investigative_exception
    assert cards[0]['affordable_assessment']['count']['value'] == 72
    assert 'unknown' in cards[0]['affordable_label']
    assert 'unverified' in cards[0]['affordable_label']
    assert app.scheme_intelligence.affordable_units_final == 72


def test_override_assessment_uses_received_fields_without_writing(session):
    from app.reporting.affordable_housing_scope import compute_affordable_housing_scope_summary
    _, app, _ = record(session)
    summary = compute_affordable_housing_scope_summary([app], prospective_overrides={
        app.id: {'affordable_units_final': 48, 'affordable_housing_status': 'conditioned',
                 'affordable_tenure_split_final': 'Reported social rent'},
    })
    position = summary.whole_site or summary.active_whole_site
    assert position.assessment.count.value == position.units == 48
    assert position.assessment.count.stage == position.status == 'conditioned'
    assert position.assessment.reported_tenure == position.tenure == 'Reported social rent'
    assert position.assessment.count.application_reference == app.reference
    assert not position.assessment.count.qualified
    assert app.scheme_intelligence.affordable_units_final == 72


def test_single_application_reconciliation_needs_no_ambient_application():
    from app.reporting.affordable_housing_scope import compute_percentage_reconciliation
    from app.policy.buyer_matching import build_planning_delivery_matching_facts
    scheme = SimpleNamespace(development_type='houses', affordable_percentage_final=30,
        affordable_units_final=30, total_units_final=100, affordable_tenure_split_final=None)
    assert compute_percentage_reconciliation(scheme)['percentage_reconciles']
    assessment = build_planning_delivery_matching_facts(scheme).affordable_assessment
    assert assessment.count.value == 30
    assert assessment.count.application_reference is None
    assert not assessment.count.qualified
    assert build_planning_delivery_matching_facts(None).affordable_assessment.search(50) == 'unknown'


def test_ah_fingerprint_contract_rejects_missing_and_tracks_qualification():
    from tests.test_agent_evaluation_persistence import _fp, _FakeFingerprintPacket, _fake_assessment
    from app.policy.agent_evaluation_persistence import compute_agent_evaluation_input_fingerprint
    a = AHAssessment(count=claim())
    assert _fp(affordable_assessment=a) != _fp(affordable_assessment=replace(a,
        count=replace(a.count, source_url=None, document_id=None)))
    packet = _FakeFingerprintPacket()
    del packet.affordable_assessment
    with pytest.raises(AttributeError, match='affordable_assessment'):
        compute_agent_evaluation_input_fingerprint(mandate_fingerprint='fp-mandate',
            acquisition_type='LAND_SITE_ACQUISITION', buyer_fit_assessment=_fake_assessment(), packet=packet)
