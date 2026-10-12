"""Synthetic/retained design fixtures, not source truth or operational admission."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import pytest

from verification.da0.contracts import (
    VERSION, Capability, FieldState, FieldEvidence, RawEnvelope, Snapshot,
    validate_registry, validate_url, eligible, admit_fixture_url, status_claim_complete,
    compare_fact, snapshot_diff, event_id, failure_projection, invoke_offline_operation,
)

FIXTURES = Path(__file__).parent / 'registry_fixtures.json'


def records():
    return json.loads(FIXTURES.read_text())['records']


def field(value='Deposited', state=FieldState.VALUE):
    return FieldEvidence(state, value, 'approved:status')


def envelope(ref='00307/26'):
    return RawEnvelope(VERSION, 'bolton-register', 'bolton', ref, ref, '202',
                       'https://paplanning.bolton.gov.uk/online-applications', '2026-10-12T00:00:00Z',
                       {'reference': field(ref), 'source_status_raw': field()},
                       dict.fromkeys(['adapter','parser','config','source_schema','code'], 'offline-v1'),
                       dict.fromkeys(['record_created_at','record_updated_at','dataset_updated_at'],
                                     field(None, FieldState.MISSING)), True, 1, 100, 0.1, 'WITHIN_BOUND')


def snap(rows=(('bolton:00307/26', 'Deposited'),), **kwargs):
    projected = tuple((k, {'source_status_raw': {'state':'PRESENT_VALUE','value':v}}) for k,v in rows)
    return Snapshot('bolton-register', 'bolton:fixture', 'v1', 'p1', 'c1', projected,
                    True, True, len(projected), consistency='SOURCE_GUARANTEED', **kwargs)


def test_inventory_non_operational_and_complete():
    rs=records(); assert len(rs)==40==len({r['source_id'] for r in rs})
    assert len({r['council'] for r in rs if r['council']!='all_ten'})==10
    for r in rs:
        validate_registry(r)
        assert r['execution_authority'] is None
        assert r['operational_state'] in {'PROPOSED','DEFERRED','UNSUPPORTED'}
        for cap in Capability:
            assert not eligible(r,r['council'],r['fact_domain'],cap.value)
            assert invoke_offline_operation(r,cap.value)['execution_performed'] is False


@pytest.mark.parametrize('mutation', ['extra','capability','gates','active','authority','false_support'])
def test_registry_rejects_unsafe_declarations(mutation):
    r=copy.deepcopy(records()[0]); cap=r['capabilities'][Capability.STATUS.value]
    if mutation=='extra': r['new_unknown_field']=1
    if mutation=='capability': del r['capabilities'][Capability.STATUS.value]
    if mutation=='gates': del cap['gates']['RIGHTS']
    if mutation=='active': r['operational_state']='ACTIVE'
    if mutation=='authority': r['execution_authority']='historical-unrelated-action'
    if mutation=='false_support': cap['declaration']='SUPPORTED'
    with pytest.raises(ValueError): validate_registry(r)


def test_capability_council_domain_are_independent():
    r=copy.deepcopy(records()[0]); c=r['capabilities'][Capability.NEW.value]
    c['declaration']='SUPPORTED'; c['gates']=dict.fromkeys(c['gates'],'PASS'); c['evidence_ids']=['SYNTHETIC_ONLY']
    assert eligible(r,r['council'],r['fact_domain'],Capability.NEW.value)
    assert not eligible(r,r['council'],r['fact_domain'],Capability.STATUS.value)
    assert not eligible(r,'another-council',r['fact_domain'],Capability.NEW.value)
    assert not eligible(r,r['council'],'another-domain',Capability.NEW.value)
    assert invoke_offline_operation(r,Capability.NEW.value)['outcome']=='UNSUPPORTED'


@pytest.mark.parametrize('url',['http://example.com','https://localhost/','https://127.0.0.1/',
                              'https://169.254.169.254/','https://[::1]/','https://user:password@example.com/',
                              'https://example.com:8080/','https://example.com/#secret'])
def test_ssrf_url_configuration_denial(url):
    with pytest.raises(ValueError): validate_url(url)


def test_exact_url_route_denial():
    r=records()[0]; u=r['admission']['exact_urls'][0]
    admit_fixture_url(r,u)
    for bad in [u+'?activeTab=documents',u+'/related',u.replace('https://','https://other.')]:
        with pytest.raises(ValueError): admit_fixture_url(r,bad)


@pytest.mark.parametrize('state',list(FieldState))
def test_field_states_distinct(state):
    f=field('Deposited' if state==FieldState.VALUE else None,state)
    assert f.state==state
    if state!=FieldState.VALUE:
        with pytest.raises(ValueError): field('invented accepted value',state)


def test_literal_status_does_not_invent_semantics_or_absence():
    e=envelope(); assert status_claim_complete(e,'00307/26')
    assert e.fields['source_status_raw'].value=='Deposited'
    assert 'semantic_state' not in e.__dict__
    assert 'source_decision_raw' not in e.fields
    blank=field(None,FieldState.BLANK); missing=field(None,FieldState.MISSING)
    assert blank!=missing
    assert compare_fact(('bolton','202','decision'),blank,('bolton','202','decision'),missing)=='REVIEW_REQUIRED'


@pytest.mark.parametrize('failure',['identity','status_missing','reference_missing','conflict','partial','budget','derived'])
def test_status_fail_closed(failure):
    e=envelope(); f=dict(e.fields)
    if failure=='identity': e=replace(e,application_reference_raw='wrong',application_reference_canonical='wrong')
    if failure=='status_missing': f.pop('source_status_raw')
    if failure=='reference_missing': f.pop('reference')
    if failure=='conflict': f['source_status_raw']=field(None,FieldState.CONFLICT)
    if failure=='partial': e=replace(e,complete_for_claim=False)
    if failure=='budget': e=replace(e,budget_outcome='OVERFLOW')
    if failure=='derived': f['source_status_raw']=FieldEvidence(FieldState.VALUE,'pending','status','DERIVED_QUALIFIED')
    assert not status_claim_complete(replace(e,fields=f),'00307/26')


@pytest.mark.parametrize('bad',['proposal_raw','applicant','semantic_state'])
def test_status_projection_privacy(bad):
    e=envelope()
    with pytest.raises(ValueError): replace(e,fields={**e.fields,bad:field('not permitted')})


def test_parent_child_not_same_claim():
    assert compare_fact(('bolton','parent','status'),field('Granted'),('bolton','child','status'),field('Granted'))=='IDENTITY_MISMATCH'


def test_conflict_not_latest_retrieval_or_tier_wins():
    assert compare_fact(('bolton','202','status'),field('Deposited'),('bolton','202','status'),field('Refused'))=='SOURCE_CONFLICT_DETECTED'


@pytest.mark.parametrize('alteration',['partial','terminal','overflow','count','duplicates','schema','parser','config','scope','consistency'])
def test_snapshot_rejection(alteration):
    a=snap(); b=a
    if alteration=='partial': b=replace(a,complete=False)
    if alteration=='terminal': b=replace(a,terminal=False)
    if alteration=='overflow': b=replace(a,overflow=True)
    if alteration=='count': b=replace(a,expected_count=100)
    if alteration=='duplicates': b=replace(a,records=a.records+a.records,expected_count=2)
    if alteration in {'schema','parser','config','scope'}: b=replace(a,**{alteration:'changed'})
    if alteration=='consistency': b=replace(a,consistency='UNPROVED')
    with pytest.raises(ValueError): snapshot_diff(a,b)


def test_snapshot_determinism_and_removal_candidate_only():
    a=snap((('a','Deposited'),('b','Decided'))); reordered=snap((('b','Decided'),('a','Deposited')))
    assert a.factual_hash()==reordered.factual_hash()
    assert snapshot_diff(a,reordered)=={'new':[],'changed':[],'removed_candidates_only':[]}
    assert snapshot_diff(a,snap((('a','Deposited'),)))['removed_candidates_only']==['b']


def test_retrieval_timestamps_cannot_enter_factual_hash():
    s=snap(); r=dict(s.records[0][1]); r['retrieved_at']={'state':'PRESENT_VALUE','value':'now'}
    with pytest.raises(ValueError): replace(s,records=(('a',r),)).factual_hash()


def test_event_replay_and_repeated_transitions():
    first=event_id('s','a','cp0','A','B','STATUS_CHANGED')
    assert first==event_id('s','a','cp0','A','B','STATUS_CHANGED')
    back=event_id('s','a',first,'B','A','STATUS_CHANGED')
    later=event_id('s','a',back,'A','B','STATUS_CHANGED')
    assert len({first,back,later})==3


def test_event_requires_accepted_predecessor():
    with pytest.raises(ValueError): event_id('s','a','','A','B','STATUS_CHANGED')


@pytest.mark.parametrize('failure',['TIMEOUT','RATE_LIMITED','PARSER_FAILURE','PARTIAL_RETRIEVAL','UNSUPPORTED'])
def test_failure_preserves_accepted_evidence(failure):
    r=failure_projection('Refused','2026-09-17',failure)
    assert r['accepted_fact']=='Refused' and r['successful_verification_at']=='2026-09-17'
    assert r['failed_attempt']==failure and r['acceptance_authorised'] is False
