from copy import deepcopy
import pytest
from verification.discovery import r0_recovery_proposal as r
from verification.discovery import finite_acceptance as f
from tests.test_discovery_finite_acceptance import evidence as original_evidence


def evidence(row):
    a = original_evidence(row)
    if row['council'] not in f.ARCUS:
        a['resource'].update(budget_exhaustion=False, elapsed_seconds=1)
        a['applied_evidence'] = 'STRICT_REFINE_FORM_ECHO'
    return a


@pytest.fixture(autouse=True)
def no_credentials(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)


def test_exact_28_previously_unattempted_windows():
    assert len(r.PLAN['rows']) == 28
    assert {x['council'] for x in r.PLAN['rows']} == f.COUNCILS - {'bolton', 'bury'}
    assert all(x['start'] >= '2026-09-17' and x['end'] <= '2026-10-14' for x in r.PLAN['rows'])
    bad = deepcopy(r.PLAN); bad['rows'][0]['council'] = 'bury'
    with pytest.raises(ValueError):
        r.execute(bad, f.digest(bad), reader=lambda _: pytest.fail('source called'))
    with pytest.raises(ValueError):
        r.execute(r.PLAN, '0'*64, reader=lambda _: pytest.fail('source called'))


def test_safe_unknown_continues_but_never_claims_parent_complete():
    calls = []
    def reader(row):
        calls.append(row)
        a = evidence(row)
        if len(calls) == 5:  # First Idox row after four Manchester windows.
            a.update(enumeration_evidence='TOTAL_UNKNOWN', explicit_zero_evidence=None)
        return a
    result = r.execute(r.PLAN, r.PLAN_HASH, reader=reader, clock=lambda: 0)
    assert len(calls) == 28 and not result['not_attempted']
    assert result['results'][4]['safe_local_gap'] is True
    assert result['results'][4]['enumeration_completeness'] == 'UNKNOWN'
    assert result['completeness'] == 'INCOMPLETE' and result['accounting_complete'] is True
    assert not result['persistence'] and not result['completed_through_advanced']


def test_complete_recovery_still_cannot_erase_prior_bury_gap():
    result = r.execute(r.PLAN, r.PLAN_HASH, reader=evidence, clock=lambda: 0)
    assert result['enumeration_completeness'] == 'COMPLETE'
    assert result['completeness'] == 'INCOMPLETE' and result['source_contract_qualified'] is False


@pytest.mark.parametrize('change,reason', [
    ({'cleanup': 'FAILED'}, 'SAFETY_OR_UNCLASSIFIED_FAILURE'),
    ({'safety_failure': True}, 'SAFETY_OR_UNCLASSIFIED_FAILURE'),
    ({'safety_events': ['ORIGIN_DENIED']}, 'SAFETY_OR_UNCLASSIFIED_FAILURE'),
    ({'process_cleanup': 'UNKNOWN'}, 'SAFETY_OR_UNCLASSIFIED_FAILURE'),
    ({'live_owned_survivors': 1}, 'SAFETY_OR_UNCLASSIFIED_FAILURE'),
    ({'supervisor_limit_hit': True}, 'SAFETY_OR_UNCLASSIFIED_FAILURE'),
    ({'requests': None}, 'RESOURCE_ACCOUNTING'),
    ({'decoded_bytes': -1}, 'RESOURCE_ACCOUNTING'),
    ({'requests': 81}, 'RESOURCE_ACCOUNTING'),
    ({'accounting_complete': False}, 'SAFETY_OR_UNCLASSIFIED_FAILURE'),
    ({'failure': 'UNCLASSIFIED_FAILURE'}, 'SAFETY_OR_UNCLASSIFIED_FAILURE'),
    ({'destination': 'https://wrong.invalid/'}, 'SAFETY_OR_UNCLASSIFIED_FAILURE'),
    ({'applied_interval': None}, 'SAFETY_OR_UNCLASSIFIED_FAILURE'),
])
def test_unsafe_or_uncertain_failures_stop_remaining_scope(change, reason):
    calls=[]
    def reader(row):
        calls.append(row); return dict(evidence(row), **change)
    out=r.execute(r.PLAN, r.PLAN_HASH, reader=reader, clock=lambda: 0)
    assert len(calls)==1 and len(out['not_attempted'])==27 and out['stop_reason']==reason
    assert out['completeness']=='INCOMPLETE'
    if reason=='RESOURCE_ACCOUNTING': assert out['accounting_complete'] is False
    if change.get('accounting_complete') is False: assert out['accounting_complete'] is False


def test_exception_is_bounded_and_uncertain_accounting_stops():
    def reader(_): raise RuntimeError('private payload must not escape')
    result=r.execute(r.PLAN,r.PLAN_HASH,reader=reader,clock=lambda:0)
    assert result['stop_reason']=='SOURCE_EXCEPTION' and not result['accounting_complete']
    assert 'private payload' not in str(result)


def test_caps_not_resource_or_identity_relaxation():
    row=next(x for x in r.PLAN['rows'] if x['council']=='oldham')
    a=evidence(row);a.update(capped=True,enumeration_evidence='PAGE_CAP',completeness='INCOMPLETE')
    assert r.safety(row,a) and r.local_gap(row,a)
    a['records']=[{'reference':None,'source_key':'X','identity_state':'UNKNOWN'}]
    assert not r.local_gap(row,a)
    a['records']=[];a['failure']='BoundaryFailure:origin'
    assert not r.safety(row,a)


def test_complete_idox_identity_failure_stops_not_just_unknown_gaps():
    calls=[]
    def reader(row):
        calls.append(row);a=evidence(row)
        if row['council']=='oldham':
            a['records']=[dict(reference='TEST/26',source_key='X',identity_state='UNKNOWN')]
            a['pages']=[dict(first=1,last=1,total=1,terminal=True)]
        return a
    result=r.execute(r.PLAN,r.PLAN_HASH,reader=reader,clock=lambda:0)
    assert len(calls)==5 and result['stop_reason']=='SAFETY_OR_UNCLASSIFIED_FAILURE'
    assert result['results'][-1]['enumeration_completeness']=='FAILED'


@pytest.mark.parametrize('change',[{'applied_evidence_sha256':None},{'applied_evidence_sha256':''},
                                  {'applied_evidence':'UNKNOWN'},{'applied_evidence_sha256':'invalid'}])
def test_unknown_gap_cannot_drop_criteria_provenance(change):
    row=next(x for x in r.PLAN['rows'] if x['council']=='oldham')
    a=evidence(row);a.update(enumeration_evidence='TOTAL_UNKNOWN',**change)
    assert not r.local_gap(row,a)


def test_arcus_local_gap_requires_safe_identity_and_cleanup():
    row=r.PLAN['rows'][0];assert row['council']=='manchester'
    a=evidence(row);a.update(enumeration_evidence='TOTAL_UNKNOWN')
    assert r.safety(row,a) and r.local_gap(row,a)
    calls=[]
    def reader(current):
        calls.append(current)
        return a if len(calls)==1 else evidence(current)
    result=r.execute(r.PLAN,r.PLAN_HASH,reader=reader,clock=lambda:0)
    assert len(calls)==28 and result['results'][0]['safe_local_gap']
    assert result['results'][0]['enumeration_completeness']=='UNKNOWN'
    assert result['completeness']=='INCOMPLETE'
    a['listing_records'][0]['reference']=None
    assert not r.safety(row,a) and not r.local_gap(row,a)


def test_outer_deadline_reservation_and_credentials(monkeypatch):
    times=iter([0,1900])
    out=r.execute(r.PLAN,r.PLAN_HASH,reader=lambda _:pytest.fail('no call'),clock=lambda:next(times))
    assert out['stop_reason']=='ROUND_BUDGET' and len(out['not_attempted'])==28
    monkeypatch.setenv('COMMITTEE_DATABASE_URL','synthetic')
    with pytest.raises(ValueError):r.execute(r.PLAN,r.PLAN_HASH,reader=lambda _:pytest.fail('no call'))
