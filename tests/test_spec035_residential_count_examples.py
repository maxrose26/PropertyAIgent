"""Specification 035 (residential count and categorisation): the executable acceptance examples.
Offline, three jobs: (1) the examples obey the specification's own rules, so the specification cannot contradict itself; (2) the evidence model (separate proposed and approved bases, scope, provenance, revision
relationships, headline, search, size admission), written as the pure reference in tests/spec035_reference.py, reproduces every hand-written expectation; (3) the recorded BASELINE of the current implementation
(legacy qualify + screening rule v1) equals its live behaviour and the documented gap lists equal the live gaps, so the mapping cannot rot. Nothing here changes behaviour.
When the implementation proposal is built and approved, the gap sets below are shrunk deliberately in the same change; that edit is the evidence the gap closed."""
import copy
import json
import random
from pathlib import Path

import pytest

from app.scrapers.unit_filter import qualify
from app.ingestion import listing_screening as ls
from tests import spec035_reference as ref

ROOT=Path(__file__).resolve().parents[1]
DOC=json.loads((ROOT/'specifications/035-residential-count-examples.json').read_text(encoding='utf-8'))
EXAMPLES=DOC['examples']
THRESHOLD=DOC['admission_threshold']
ADMISSIONS={'ADMIT_SCHEME','ADMIT_FOR_ASSESSMENT','ROUTE_COUNT_UNCONFIRMED','RETAIN_BELOW_THRESHOLD','RETAIN_NOT_RESIDENTIAL_SUPPLY','RETAIN_RELATED_TO_PARENT','RETAIN_WATCHLIST','RETAIN_UNUSABLE_PROPOSAL'}
ROLES={'NEW_SCHEME','PHASE_OF_PARENT','AMENDMENT_OF_PARENT','DISCHARGE_OF_PARENT','PRE_APPLICATION_SIGNAL'}
SIZE_OUTCOMES={'ADMIT_SCHEME','ADMIT_FOR_ASSESSMENT','RETAIN_BELOW_THRESHOLD'}
NE='NOT_ESTABLISHED';NONE='NONE'

# The documented gaps of the CURRENT implementation against the specification (specification section 9). Shrink these deliberately when the implementation lands.
LEGACY_FALSE_NEGATIVES={'E06','E07','E08','E10'}      # supported total >= threshold, legacy does not admit (it takes one component, not the total)
LEGACY_FALSE_POSITIVES={'E17','E21','E22','E34','E35','E36'}      # legacy admits although no supported total >= threshold exists
LEGACY_COUNT_GAPS={'E06','E07','E08','E10','E14','E17','E21','E22','E23','E24','E25','E26','E27','E28','E29','E33','E34','E35','E36'}
EVIDENCE_MODEL_EXAMPLES={'E37','E38','E38b','E38c','E38d','E38e','E38f','E38g','E38h','E38i','E38j','E38k','E38l','E38m'}      # the legacy single scalar cannot represent basis, scope, source, revision or conflict


def number(value):
    return value if isinstance(value,int) and not isinstance(value,bool) else None


def records_of(e):
    """Explicit evidence records, or for a plain example the single supported proposed record its proposal text gives."""
    if 'records' in e:return e['records']
    p=e['expected']['proposed_total']
    if number(p) is None and not (isinstance(p,str) and p.startswith('UP_TO:')):return []
    return [dict(id='t1',basis='PROPOSED',scope='whole',value=p,source_kind='LISTING_PROPOSAL_TEXT',document_date=None,revision=None,qualifier='outline' if e['expected']['category']=='outline_application' else None,relations={})]


def project(state):
    keys=('state','quantity','maximum','competing','historical','unsupported_as_approved')
    out={k:state[k] for k in keys if k in state and state[k] not in ([],None)}
    if state['state'] in ('CONFLICT_UNRESOLVED','ALTERNATIVE_PERMISSIONS'):out['competing']=[list(x) for x in state['competing']]
    else:out.pop('competing',None)
    if state['state']=='PER_SCOPE':out['scopes']={n:project(v) for n,v in state['scopes'].items()}
    return out


def test_the_document_header_is_the_specified_version_and_threshold():
    assert DOC['spec_version']=='residential-count-v2' and THRESHOLD==10 and len(EXAMPLES)==len({e['id'] for e in EXAMPLES})>=50


@pytest.mark.parametrize('e',EXAMPLES,ids=[e['id'] for e in EXAMPLES])
def test_each_example_obeys_the_specified_rules(e):
    x=e['expected'];p=x['proposed_total'];a=x['admission']
    assert a in ADMISSIONS and x['scheme_role'] in ROLES and x['reason'] and isinstance(x['non_residential_units'],dict)
    # R-ADMIT: size eligibility comes from the supported proposed or approved count against the platform threshold, nothing else; conflicts and qualified quantities route to assessment
    if a in SIZE_OUTCOMES:assert ref.size_outcome(records_of(e),THRESHOLD,e.get('scope_relations',()))==a
    if a=='ADMIT_FOR_ASSESSMENT':assert x['reason'] in ('QUALIFIED_MAXIMUM_AT_OR_ABOVE_THRESHOLD','COUNT_CONFLICT')
    if a in ('ROUTE_COUNT_UNCONFIRMED','RETAIN_UNUSABLE_PROPOSAL','RETAIN_WATCHLIST'):assert p==NE and not records_of(e)
    # R-RELATED: an amendment, discharge or pre-application signal never carries its own proposed total and never admits as a scheme; parent figures are context only
    if x['scheme_role'] in ('AMENDMENT_OF_PARENT','DISCHARGE_OF_PARENT','PRE_APPLICATION_SIGNAL'):
        assert p==NE and a in ('RETAIN_RELATED_TO_PARENT','RETAIN_WATCHLIST')
    # R-NET: net is established exactly when proposed and demolished are both established (NONE counts as 0), and then equals proposed - demolished; nothing is inferred otherwise
    pn=0 if p==NONE else number(p);dn=0 if x['demolished']==NONE else number(x['demolished'])
    if pn is not None and dn is not None:assert x['net']==pn-dn
    else:assert x['net']==NE
    # R-MIXED: commercial units are recorded separately and are never residential dwellings
    for kind,count in x['non_residential_units'].items():assert number(count) is not None and count>0
    # R-STATUS: planning status and construction progress are separate facts and never enter a count
    if 'planning' in e:assert set(e['planning'])<={'planning_status','construction_progress'}


@pytest.mark.parametrize('e',[e for e in EXAMPLES if 'records' in e],ids=[e['id'] for e in EXAMPLES if 'records' in e])
def test_the_evidence_model_reproduces_every_hand_written_expectation(e):
    recs=e['records'];rel=e['scope_relations'];x=e['expected']
    for basis,name in ((ref.PROPOSED,'proposed'),(ref.APPROVED,'approved')):
        assert project(ref.resolve_basis(recs,basis,rel))==x['bases'][name],(e['id'],name)
    assert ref.headline(recs,rel)==x['headline']
    for s in x['search']:
        got=ref.search_match(recs,s['basis'],s['threshold'],rel)
        assert got==dict(match=s['match'],matched_by=s['matched_by']),(e['id'],s)
    assert {s['basis'] for s in x['search'] if s['threshold']==THRESHOLD}=={'APPROVED','PROPOSED','EITHER'}      # every example states all three bases at the default threshold


def test_approval_needs_permission_evidence_and_a_form_or_proposal_alone_never_establishes_it():
    for kind in ('APPLICATION_FORM_STRUCTURED','LISTING_PROPOSAL_TEXT','DETAIL_PROPOSAL_TEXT','PLANNING_STATEMENT','OFFICER_REPORT'):
        s=ref.resolve_basis([dict(id='a',basis='APPROVED',value=49,source_kind=kind,relations={})],ref.APPROVED)
        assert s['state']==ref.NOT_ESTABLISHED and s['unsupported_as_approved']==['a']
    for kind in ('DECISION_NOTICE','APPROVED_PLANS_SCHEDULE'):
        assert ref.resolve_basis([dict(id='a',basis='APPROVED',value=49,source_kind=kind,relations={})],ref.APPROVED)['state']==ref.RESOLVED


def test_nothing_resolves_a_conflict_by_date_upload_order_record_order_or_size():
    base=[dict(id='a1',basis='APPROVED',value=49,source_kind='DECISION_NOTICE',document_date='2024-02-01',relations={}),dict(id='a2',basis='APPROVED',value=52,source_kind='DECISION_NOTICE',document_date='2026-02-01',relations={})]
    want=ref.resolve_basis(base,ref.APPROVED)
    assert want['state']==ref.CONFLICT
    for _ in range(20):      # any order, any dates, either figure larger: still unresolved
        shuffled=copy.deepcopy(base);random.shuffle(shuffled)
        for r in shuffled:r['document_date']=random.choice(['2020-01-01','2030-01-01',None]);r['value']=random.choice([49,52]) if r['id']=='a1' else 52
        s=ref.resolve_basis(shuffled,ref.APPROVED)
        assert s['state']==(ref.CONFLICT if len({r['value'] for r in shuffled})>1 else ref.RESOLVED)
    superseded=copy.deepcopy(base);superseded[1]['relations']={'supersedes':'a1'}
    assert ref.resolve_basis(superseded,ref.APPROVED)['quantity']==52      # only an explicit relationship resolves it
    unsupported_supersede=copy.deepcopy(base);unsupported_supersede[1]['source_kind']='APPLICATION_FORM_STRUCTURED';unsupported_supersede[1]['relations']={'supersedes':'a1'}
    assert ref.resolve_basis(unsupported_supersede,ref.APPROVED)['quantity']==49      # an unsupported record cannot supersede a permission


def test_a_conflict_in_one_scope_never_arises_from_a_different_scope_and_the_planning_status_is_never_read():
    recs=[dict(id='p1',basis='PROPOSED',scope='Phase 1',value=49,source_kind='LISTING_PROPOSAL_TEXT',relations={}),dict(id='p2',basis='PROPOSED',scope='Phase 2',value=9,source_kind='LISTING_PROPOSAL_TEXT',relations={})]
    assert ref.resolve_basis(recs,ref.PROPOSED)['state']==ref.PER_SCOPE
    assert ref.search_match(recs,ref.PROPOSED)['match']==ref.CONFIRMED      # each phase is judged on its own scope
    with_status=copy.deepcopy(recs);[r.update(planning_status='REFUSED',construction_progress='STARTED') for r in with_status]
    assert ref.headline(with_status)==ref.headline(recs)


def test_search_separates_possible_from_confirmed_shows_the_causing_basis_and_defaults_to_either():
    assert ref.EITHER=='EITHER'
    by_id={e['id']:e for e in EXAMPLES}
    got=ref.search_match(by_id['E38e']['records'],ref.EITHER,50)
    assert got=={'match':'CONFIRMED','matched_by':['PROPOSED']}      # approved 49 misses 50, proposed revision 52 matches: the result names the basis
    assert ref.search_match(by_id['E38h']['records'],ref.EITHER)['match']=='POSSIBLE' and ref.search_match(by_id['E38g']['records'],ref.EITHER)['match']=='POSSIBLE'
    assert ref.search_match(by_id['E38']['records'],ref.EITHER)['match']=='CONFIRMED'      # both competing figures >= 10: size is established though the quantity is under review


def test_results_are_deduplicated_by_scheme_identity_keeping_the_best_class_and_every_contributing_application():
    rows=[dict(scheme_id='S1',application='APP/2',match='POSSIBLE',matched_by=['PROPOSED']),dict(scheme_id='S1',application='APP/1',match='CONFIRMED',matched_by=['APPROVED']),
          dict(scheme_id='S1',application='APP/3',match='CONFIRMED',matched_by=['PROPOSED']),dict(scheme_id='S2',application='APP/9',match='POSSIBLE',matched_by=['APPROVED'])]
    assert ref.dedupe_by_scheme(rows)==[dict(scheme_id='S1',match='CONFIRMED',matched_by=['APPROVED','PROPOSED'],applications=['APP/1','APP/2','APP/3']),dict(scheme_id='S2',match='POSSIBLE',matched_by=['APPROVED'],applications=['APP/9'])]


@pytest.mark.parametrize('e',[e for e in EXAMPLES if 'records' not in e and e['expected']['admission'] in SIZE_OUTCOMES],ids=lambda e:e['id'])
def test_a_plain_example_gets_the_labelled_proposed_headline_and_the_default_either_search(e):
    recs=records_of(e);h=ref.headline(recs);p=e['expected']['proposed_total']
    if number(p) is not None:assert h==dict(kind='PROPOSED',label='Proposed: %d'%p)
    else:assert h['label'] in ('Proposed (outline): up to %s'%p.split(':')[1],'Proposed: up to %s'%p.split(':')[1])
    want=ref.CONFIRMED if number(p) is not None and p>=THRESHOLD else ref.POSSIBLE if number(p) is None and int(p.split(':')[1])>=THRESHOLD else ref.NO_MATCH
    assert ref.search_match(recs,ref.EITHER,THRESHOLD)['match']==want and ref.search_match(recs,ref.APPROVED,THRESHOLD)['match']==ref.NO_MATCH


def test_mixed_use_counts_only_dwellings_and_records_commercial_units_separately():
    by_id={e['id']:e for e in EXAMPLES}
    nine=by_id['E41']['expected'];ten=by_id['E42']['expected']
    assert nine['proposed_total']==9 and nine['non_residential_units']=={'retail':1} and nine['admission']=='RETAIN_BELOW_THRESHOLD'      # 9 flats + 1 shop is 9 dwellings, not 10 units
    assert ten['proposed_total']==10 and ten['non_residential_units']=={'retail':2} and ten['admission']=='ADMIT_SCHEME'
    assert by_id['E23']['expected']['non_residential_units']=={'retail':3} and by_id['E23']['expected']['proposed_total']==NONE


def live(e):
    t=e['proposal'];q=qualify(t)
    row=dict(reference='T/1',fields={'proposal':dict(state=e['proposal_state'],value=t,locator='x',truncated=False),'address':dict(state='PRESENT_VALUE',value='1 Test Street',locator='x',truncated=False),
                                     'application_type':dict(state='UNKNOWN',value=None,locator='x',truncated=False)})
    return dict(qualify_unit_count=q.unit_count,qualify_category=q.category,qualify_classification=q.classification,legacy_admits=bool(q.qualifies),screen_v1_disposition=ls.screen_row(row)['disposition'])


def test_the_recorded_baseline_equals_the_live_behaviour_of_the_current_implementation():
    drift={e['id'] for e in EXAMPLES if live(e)!=e['baseline_current']}
    assert drift==set()      # refresh the JSON baseline (and review the gap lists) if this ever moves; v1 itself must not


def test_the_documented_gap_lists_equal_the_live_gaps():
    plain=[e for e in EXAMPLES if 'records' not in e]
    def wants_admission(e):return e['expected']['admission'] in ('ADMIT_SCHEME','ADMIT_FOR_ASSESSMENT')
    def not_scheme(e):return e['expected']['admission'] not in ('ADMIT_SCHEME','ADMIT_FOR_ASSESSMENT','ROUTE_COUNT_UNCONFIRMED')
    fn={e['id'] for e in plain if wants_admission(e) and not live(e)['legacy_admits']}
    fp={e['id'] for e in plain if not_scheme(e) and live(e)['legacy_admits']}
    def want(e):
        p=e['expected']['proposed_total'];return p if isinstance(p,int) else (int(p.split(':')[1]) if isinstance(p,str) and p.startswith('UP_TO:') else None)
    cg={e['id'] for e in plain if (live(e)['qualify_unit_count']!=want(e) if want(e) is not None else live(e)['qualify_unit_count'] is not None)}
    assert (fn,fp,cg)==(LEGACY_FALSE_NEGATIVES,LEGACY_FALSE_POSITIVES,LEGACY_COUNT_GAPS)
    assert {e['id'] for e in EXAMPLES if 'records' in e}==EVIDENCE_MODEL_EXAMPLES      # these cannot be conformant until the single scalar is replaced as the source of truth


def test_historical_screening_results_are_untouched_by_this_specification():
    assert ls.screen_row({'reference':'T/1','fields':{'proposal':{'state':'PRESENT_VALUE','value':'ERECTION OF 12 DWELLINGS','locator':'x','truncated':False},'address':{'state':'UNKNOWN','value':None,'locator':'x','truncated':False},
                                                     'application_type':{'state':'UNKNOWN','value':None,'locator':'x','truncated':False}}})['rule_version']=='manchester-listing-screen-assessment-v1'
