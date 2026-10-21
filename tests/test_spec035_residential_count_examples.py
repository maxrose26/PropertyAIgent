"""Specification 035 (residential count and categorisation): the executable acceptance examples.
Two jobs, both offline: (1) the examples are internally consistent with the specification's rules, so the specification cannot contradict itself; (2) the recorded BASELINE of the current implementation
(legacy qualify + screening rule v1) equals its live behaviour, and the documented gap lists equal the live gaps, so the mapping cannot rot. Nothing here changes behaviour.
When the implementation proposal is built and approved, the expected-conformance sets below are shrunk deliberately in the same change; that edit is the evidence the gap closed."""
import json
from pathlib import Path

import pytest

from app.scrapers.unit_filter import qualify
from app.ingestion import listing_screening as ls

ROOT=Path(__file__).resolve().parents[1]
DOC=json.loads((ROOT/'specifications/035-residential-count-examples.json').read_text(encoding='utf-8'))
EXAMPLES=DOC['examples']
THRESHOLD=DOC['admission_threshold']
ADMISSIONS={'ADMIT_SCHEME','ADMIT_FOR_ASSESSMENT','ROUTE_COUNT_UNCONFIRMED','RETAIN_BELOW_THRESHOLD','RETAIN_NOT_RESIDENTIAL_SUPPLY','RETAIN_RELATED_TO_PARENT','RETAIN_WATCHLIST','RETAIN_UNUSABLE_PROPOSAL'}
ROLES={'NEW_SCHEME','PHASE_OF_PARENT','AMENDMENT_OF_PARENT','DISCHARGE_OF_PARENT','PRE_APPLICATION_SIGNAL'}
NE='NOT_ESTABLISHED';NONE='NONE'

# The documented gaps of the CURRENT implementation against the specification (specification section 8). Shrink these deliberately when the implementation lands.
LEGACY_FALSE_NEGATIVES={'E06','E07','E08','E10'}      # supported proposed total >= threshold, legacy does not admit (it takes one component, not the total)
LEGACY_FALSE_POSITIVES={'E17','E21','E22','E34','E35','E36'}      # legacy admits although no supported proposed total >= threshold exists
LEGACY_COUNT_GAPS={'E06','E07','E08','E10','E14','E17','E21','E22','E23','E24','E25','E26','E27','E28','E29','E33','E34','E35','E36','E37','E38'}


def number(value):
    return value if isinstance(value,int) and not isinstance(value,bool) else None


def test_the_document_header_is_the_specified_version_and_threshold():
    assert DOC['spec_version']=='residential-count-v1' and THRESHOLD==10 and len(EXAMPLES)==len({e['id'] for e in EXAMPLES})>=30


@pytest.mark.parametrize('e',EXAMPLES,ids=[e['id'] for e in EXAMPLES])
def test_each_example_obeys_the_specified_rules(e):
    x=e['expected'];p=x['proposed_total'];a=x['admission']
    assert a in ADMISSIONS and x['scheme_role'] in ROLES and x['reason']
    # R-ADMIT: admission is by the supported proposed gross total only, against the platform threshold
    if a=='ADMIT_SCHEME':assert number(p) is not None and p>=THRESHOLD
    if a=='RETAIN_BELOW_THRESHOLD':assert number(p) is not None and 0<p<THRESHOLD
    if a=='ADMIT_FOR_ASSESSMENT':assert x['reason'] in ('QUALIFIED_MAXIMUM_AT_OR_ABOVE_THRESHOLD','COUNT_CONFLICT') and (x['reason']=='COUNT_CONFLICT' or (isinstance(p,str) and p.startswith('UP_TO:') and int(p.split(':')[1])>=THRESHOLD))
    if a in ('ROUTE_COUNT_UNCONFIRMED','RETAIN_UNUSABLE_PROPOSAL','RETAIN_WATCHLIST'):assert p==NE
    # R-RELATED: an amendment, discharge or pre-application signal never carries its own proposed total and never admits as a scheme; parent figures are context only
    if x['scheme_role'] in ('AMENDMENT_OF_PARENT','DISCHARGE_OF_PARENT','PRE_APPLICATION_SIGNAL'):
        assert p==NE and a in ('RETAIN_RELATED_TO_PARENT','RETAIN_WATCHLIST')
    if x['parent_context'] is not None:assert x['parent_context']['relation'] and p!=x['parent_context']['context_count'] or number(p) is None or x['scheme_role']!='NEW_SCHEME'
    # R-NET: net is established exactly when proposed and demolished are both established (NONE counts as 0), and then equals proposed - demolished; nothing is inferred otherwise
    pn=0 if p==NONE else number(p);dn=0 if x['demolished']==NONE else number(x['demolished'])
    if pn is not None and dn is not None:assert x['net']==pn-dn
    else:assert x['net']==NE


def live(e):
    t=e['proposal'];q=qualify(t)
    row=dict(reference='T/1',fields={'proposal':dict(state=e['proposal_state'],value=t,locator='x',truncated=False),'address':dict(state='PRESENT_VALUE',value='1 Test Street',locator='x',truncated=False),
                                     'application_type':dict(state='UNKNOWN',value=None,locator='x',truncated=False)})
    return dict(qualify_unit_count=q.unit_count,qualify_category=q.category,qualify_classification=q.classification,legacy_admits=bool(q.qualifies),screen_v1_disposition=ls.screen_row(row)['disposition'])


def test_the_recorded_baseline_equals_the_live_behaviour_of_the_current_implementation():
    drift={e['id'] for e in EXAMPLES if live(e)!=e['baseline_current']}
    assert drift==set()      # refresh the JSON baseline (and review the gap lists) if this ever moves; v1 itself must not


def test_the_documented_gap_lists_equal_the_live_gaps():
    def wants_admission(e):return e['expected']['admission'] in ('ADMIT_SCHEME','ADMIT_FOR_ASSESSMENT')
    def not_scheme(e):return e['expected']['admission'] not in ('ADMIT_SCHEME','ADMIT_FOR_ASSESSMENT','ROUTE_COUNT_UNCONFIRMED')
    fn={e['id'] for e in EXAMPLES if wants_admission(e) and not live(e)['legacy_admits']}
    fp={e['id'] for e in EXAMPLES if not_scheme(e) and live(e)['legacy_admits']}
    def want(e):
        p=e['expected']['proposed_total'];return p if isinstance(p,int) else (int(p.split(':')[1]) if isinstance(p,str) and p.startswith('UP_TO:') else None)
    cg={e['id'] for e in EXAMPLES if (live(e)['qualify_unit_count']!=want(e) if want(e) is not None else live(e)['qualify_unit_count'] is not None)}
    assert (fn,fp,cg)==(LEGACY_FALSE_NEGATIVES,LEGACY_FALSE_POSITIVES,LEGACY_COUNT_GAPS)


def test_historical_screening_results_are_untouched_by_this_specification():
    assert ls.screen_row({'reference':'T/1','fields':{'proposal':{'state':'PRESENT_VALUE','value':'ERECTION OF 12 DWELLINGS','locator':'x','truncated':False},'address':{'state':'UNKNOWN','value':None,'locator':'x','truncated':False},
                                                     'application_type':{'state':'UNKNOWN','value':None,'locator':'x','truncated':False}}})['rule_version']=='manchester-listing-screen-assessment-v1'
