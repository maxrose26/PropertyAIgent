"""Buyer-relative quantity and contextual fit; no persistence or evaluations."""
from dataclasses import replace
import pytest
from app.policy.ah_assessment import AHAssessment, AHClaim
from app.policy.buyer_matching import assess_buyer_fit, B2MatchingContext
from app.policy.buyer_profiles import HOUSING_ASSOCIATION, GEOGRAPHY_COUNCILS
from tests.test_buyer_matching import _facts


def claim(**kw):
    return AHClaim(**(dict(value=72, qualifier='exact', state='verified',
        application_reference='LOCAL/1', scope_type='component', scope_label='Retirement component',
        source_url='https://example.invalid/statement', passage='72 affordable retirement homes') | kw))


def fixture():
    a=AHAssessment(count=claim())
    return _facts(unit_count=82, affordable_unit_count=72, affordable_assessment=a,
        development_type_raw='mixed_retirement_and_market_housing', is_specialist_development=True,
        affordable_percentage=None, affordable_percentage_trusted=False)


@pytest.mark.parametrize('minimum,maximum,outcome',[(20,None,'meets'),(72,None,'meets'),
    (73,None,'investigate'),(None,60,'does_not_meet'),(None,80,'investigate'),
    (20,80,'investigate'),(None,None,'unfiltered')])
def test_quantity_is_buyer_relative_with_component_scope(minimum,maximum,outcome):
    facts=fixture()
    assert facts.affordable_assessment.search(minimum,maximum)==outcome
    result=assess_buyer_fit(replace(HOUSING_ASSOCIATION,target_unit_min=minimum,
        target_unit_max=maximum,retirement_appetite='ACCEPT'),facts)
    reasons=result.matches+result.unknown+result.investigate
    if outcome=='unfiltered':
        assert result.classification=='STRONG_FIT'
        assert not any('AH count assessment' in r for r in reasons)
    else:
        assert any(f'AH count assessment: {outcome}' in r for r in reasons)


@pytest.mark.parametrize('threshold',[20,80,100])
def test_approximate_band_scales_with_buyer_boundary(threshold):
    for value in (threshold*9//10, threshold, threshold*11//10):
        a=AHAssessment(count=claim(value=value,qualifier='approximate',state='estimated',scope_type='whole_site'))
        assert a.search(minimum=threshold)==a.search(maximum=threshold)=='investigate'
    exact=AHAssessment(count=claim(value=threshold,scope_type='whole_site'))
    assert exact.search(minimum=threshold,maximum=threshold)=='meets'
    bounded=AHAssessment(count=claim(value=None,qualifier='range',lower=threshold,upper=threshold+2,scope_type='whole_site'))
    assert bounded.search(minimum=threshold)=='likely_meets'


def test_full_context_preserves_independent_geography_and_acquisition_checks():
    facts=fixture()
    policy=replace(HOUSING_ASSOCIATION,target_unit_min=20,target_unit_max=None,retirement_appetite='ACCEPT',
        geography_scope=GEOGRAPHY_COUNCILS,geography_councils=frozenset({'stockport'}))
    accepted=assess_buyer_fit(policy,facts,B2MatchingContext(council_code='stockport'))
    assert accepted.classification=='STRONG_FIT'
    assert any('geographic boundary' in r for r in accepted.matches)
    assert any('Source-qualified affordable-housing-package signal' in r for r in accepted.matches)
    assert any('does not establish' in r for r in accepted.matches)
    assert assess_buyer_fit(policy,facts,B2MatchingContext(council_code='oldham')).classification=='NOT_SUITABLE'
    assert assess_buyer_fit(policy,facts,B2MatchingContext()).classification=='INSUFFICIENT_EVIDENCE'
    for appetite,want in [('EXCLUDE','NOT_SUITABLE'),('UNSPECIFIED','INSUFFICIENT_EVIDENCE')]:
        assert assess_buyer_fit(replace(policy,retirement_appetite=appetite),facts,B2MatchingContext(council_code='stockport')).classification==want


def test_no_quantity_requirement_does_not_make_unknown_ah_a_package_match():
    policy=replace(HOUSING_ASSOCIATION,target_unit_min=None,target_unit_max=None,retirement_appetite='ACCEPT')
    facts=replace(fixture(),affordable_unit_count=None,affordable_assessment=AHAssessment())
    result=assess_buyer_fit(policy,facts,B2MatchingContext(council_code='stockport'))
    assert result.classification=='INSUFFICIENT_EVIDENCE'
    assert any('package acquisition strategy' in r for r in result.unknown)
    assert not any('AH count assessment' in r for r in result.matches+result.unknown)
