"""Offline source-qualified case wrappers, not a historical extraction replay."""
import json
from pathlib import Path
from dataclasses import asdict
import pytest
from app.db.models import Application, SchemeIntelligence
from app.reporting.residential_count_eligibility import residential_count_eligibility, eligible_residential_scalar
from app.reporting.scheme_reconciliation import build_operative_planning_facts, count_assessment_for_facts

CASES = json.loads((Path(__file__).parent / 'fixtures/stage26b/retained-cases.json').read_text())


def case_app(case, *, pending=False):
    a = Application(id=case['application_id'], site_id=case['site_id'], council_code='test',
        reference=case['reference'], proposal=case['proposal_from_current_source'],
        decision=None if pending else 'Granted', status='Awaiting decision' if pending else 'Decided',
        decision_issued_date=None if pending else '2026-01-01', application_received='2025-01-01',
        estimated_unit_count=case['stored_total'])
    a.scheme_intelligence = SchemeIntelligence(total_units_final=case['stored_total'],
        development_type=case['stored_development_type'], housing_typology=case['stored_housing_typology'],
        **{k:v for k,v in case['stored_ah'].items() if hasattr(SchemeIntelligence,k)})
    return a

@pytest.mark.parametrize('case', CASES, ids=lambda c:c['reference'])
@pytest.mark.parametrize('pending', [True, False])
def test_source_qualified_acceptance(case,pending):
    a=case_app(case,pending=pending); before={k:getattr(a.scheme_intelligence,k) for k in case['stored_ah']}
    result=count_assessment_for_facts(build_operative_planning_facts([a]))
    if case['site_id'] in (248,16,62,336,371,508):
        assert result.exact_value is None
        assert result.precision=='UNKNOWN'
        assert eligible_residential_scalar(a,case['stored_total']) is None
    else:
        assert result.exact_value==case['stored_total']
    assert before=={k:getattr(a.scheme_intelligence,k) for k in case['stored_ah']}
    assert a.scheme_intelligence.total_units_final==case['stored_total']

@pytest.mark.parametrize('proposal,total',[
 ('Erection of 120 dwellings and a pedestrian bridge',120),
 ('Construction of 120 residential homes and commercial building with office space',120),
 ('Erection of 67 retirement apartments',67),
 ('',120),
 ('Erection of 100 dwellings including 30 affordable homes',100),
 ('Erection of 49 retirement apartments together with 18 retirement bungalows',67),
 ('Section 73 variation of previous permission for 100 homes to allow 120 homes',120),
])
def test_positive_controls(proposal,total):
    assert residential_count_eligibility(Application(proposal=proposal),total).eligible

@pytest.mark.parametrize('proposal,total',[
 ('Demolition of existing porches to 56 dwellings and erection of replacement porches',56),
 ('Reserved matters approval for pedestrian crossings/bridges',372),
 ('Outline for proposed commercial building Use Class B2/B8',47),
 ('Reserved matters for Acoustics Building',79),
 ('Erection of 43 dwellings and erection of 60 retirement-living apartments',60),
 ('Reserved matters for erection of 76 residential dwellings',116),
])
def test_negative_controls(proposal,total):
    assert not residential_count_eligibility(Application(proposal=proposal),total).eligible


def test_b0_truth_and_sample_boundaries():
    index=json.loads((Path(__file__).parent/'fixtures/stage26b/case-index.json').read_text())
    assert len(index['cases'])==25
    assert sum(c['scale_scope_comparison']=='DISCREPANCY' for c in index['cases'])==6
    assert sum(c['scale_scope_comparison']=='UNRESOLVED' for c in index['cases'])==5
    assert all(c['historical_extraction_origin']=='UNRESOLVED' and c['source_url'].startswith('https://') and c['observed_at'] for c in CASES)

@pytest.mark.parametrize('proposal,total',[
 ('Residential development comprising 100 dwellings and pedestrian bridges',100),
 ('Erection of 100 two-storey dwellings and replacement porches to existing houses',100),
 ('Construction of 60 apartments and demolition of 43 houses',60),
])
def test_review_held_out_creation_controls(proposal,total):
    assert residential_count_eligibility(Application(proposal=proposal),total).eligible

@pytest.mark.parametrize('pending',[False,True])
def test_ancillary_record_does_not_poison_independently_supported_same_scope(pending):
    a=case_app(CASES[0],pending=pending);a.proposal='Erection of 100 dwellings';a.scheme_intelligence.total_units_final=100
    other=case_app(CASES[2],pending=pending);other.site_id=a.site_id;other.scheme_intelligence=None;other.estimated_unit_count=None
    result=count_assessment_for_facts(build_operative_planning_facts([a,other]))
    assert result.exact_value==100


@pytest.mark.parametrize('proposal,total',[
 ('Variation of permission for erection of 100 dwellings to allow erection of 120 dwellings',120),
 ('Construction of 100 homes including erection of 30 affordable homes',100),
])
def test_non_additive_creation_clauses_are_not_components(proposal,total):
    assert residential_count_eligibility(Application(proposal=proposal),total).eligible


@pytest.mark.parametrize('estimate',[76,None])
@pytest.mark.parametrize('pending',[False,True])
def test_conflicted_source_cannot_reenter_through_portal_fallback(estimate,pending):
    a=case_app(CASES[0],pending=pending);a.estimated_unit_count=estimate
    count=count_assessment_for_facts(build_operative_planning_facts([a]))
    assert count.precision=='UNKNOWN' and count.value is None


def test_parent_creation_context_cannot_qualify_bridge():
    a=Application(proposal='Reserved matters for pedestrian bridges pursuant to outline permission for erection of 372 dwellings')
    assert not residential_count_eligibility(a,372).eligible


def test_retirement_component_remains_eligible_as_its_own_subject():
    a=case_app(CASES[1]);a.proposal='Reserved matters Phase 3 erection of 60 retirement apartments pursuant to outline permission for 103 homes'
    from app.reporting.scheme_reconciliation import scoped_count_assessment
    count=scoped_count_assessment([a],'phase','Phase 3')
    assert count.exact_value==60


@pytest.mark.parametrize('proposal,total',[
 ('Conversion of commercial building to 50 dwellings',50),
 ('Change of use of commercial building to 50 apartments',50),
 ('Development of land for 100 dwellings and pedestrian bridges',100),
])
def test_conversion_and_land_development_are_not_nonresidential(proposal,total):
    assert residential_count_eligibility(Application(proposal=proposal),total).eligible
