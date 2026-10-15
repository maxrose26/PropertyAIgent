"""Synthetic HTTP bodies; real worker/main/transport/parent, no live sources."""
from copy import deepcopy
from datetime import date
import hashlib,json,sys
import pytest
from verification.bolton_recon.fixtures import FORM
from tests.test_discovery_idox_window import page,Response
from verification.discovery import finite_acceptance as finite, r0_recovery_proposal as parent


def bodies(kind='cap',echo='valid'):
    result=[]
    for i in range(6 if kind=='cap' else 1):
        p=page(first=i*10+1,last=i*10+10,total=64 if kind=='cap' else 10,
            refs=tuple(f'{i*10+j:05}/26' for j in range(10)),next_page=i+2 if kind=='cap' else None)
        for j in range(10):p=p.replace(f'keyVal=K{j}&'.encode(),f'keyVal=P{i}K{j}&'.encode())
        if kind=='missing_total':p=page(pager=False)
        result.append(p)
    e=FORM.replace(b'Start)" value=""',b'Start)" value="28/09/2026"').replace(b'End)" value=""',b'End)" value="04/10/2026"')
    if echo=='wrong':e=e.replace(b'04/10/2026',b'05/10/2026')
    if echo=='missing':e=FORM
    return [FORM,result[0],*result,e]


def through_transport(monkeypatch,tmp_path,kind='cap',echo='valid',mutation=None,checkpoint=None):
    monkeypatch.delenv('DATABASE_URL',raising=False)
    rows=[dict(council='bolton',start='2026-09-28',end='2026-10-04',semantics='RECEIVED'),
          dict(council='bolton',start='2026-09-28',end='2026-10-04',semantics='RECEIVED')]
    calls=[];physical=[];queue=[]
    def request(session,method,url,**kw):
        physical.append((method,url));return Response(queue.pop(0))
    monkeypatch.setattr('requests.Session.request',request)
    monkeypatch.setattr('verification.discovery.idox_window.time.sleep',lambda _:None)
    def supervisor(argv,*,env,deadline):
        assert argv[1:3]==['-m','verification.discovery.finite_acceptance']
        assert not any('DATABASE' in k for k in env)
        with monkeypatch.context() as m:
            m.setattr(sys,'argv',[argv[2],*argv[3:]])
            finite.main()  # actual worker -> live/run -> real boundary and parser
        return 0,False
    monkeypatch.setattr(finite,'supervise',supervisor)
    def reader(row):
        calls.append(row);queue.extend(bodies(kind if len(calls)==1 else 'complete',echo if len(calls)==1 else 'valid'))
        a=finite.read(row)  # actual credential-free transport entry
        if len(calls)==1 and mutation:mutation(a)
        return a
    out=parent._execute_fixed(dict(rows=rows),'synthetic',reader=reader,
        limits=dict(requests=20,bytes=6_000_000,seconds=110,output_bytes=1_000_000),checkpoint=checkpoint or (lambda _:None),clock=lambda:0)
    return out,calls,physical


def test_real_capped_worker_transport_parent_continues(monkeypatch,tmp_path):
    out,calls,physical=through_transport(monkeypatch,tmp_path)
    assert len(calls)==2 and out['stop_reason'] is None
    first=out['results'][0];a=first['source']
    assert first['safe_local_gap'] and first['enumeration_completeness']=='INCOMPLETE'
    assert len(a['records'])==60 and a['enumeration_evidence']=='PAGE_CAP'
    assert a['resource']['requests_attempted']==9<=10
    b=a['criteria_result_binding']
    assert b['segment_sha256']==[p['body_sha256'] for p in a['pages']]
    assert b['criteria_sha256']==a['applied_evidence_sha256'] and b['request_ordinal']==9
    assert not b['result_set_reenumerated']
    assert out['completeness']=='INCOMPLETE' and not out['completed_through_advanced']
    assert all('processing_screen' in r for r in a['records'])


@pytest.mark.parametrize('echo',['wrong','missing'])
def test_criteria_rejection_stops_before_next_source(monkeypatch,tmp_path,echo):
    out,calls,_=through_transport(monkeypatch,tmp_path,echo=echo)
    assert len(calls)==1 and out['stop_reason']=='SAFETY_OR_UNCLASSIFIED_FAILURE'
    assert out['results'][0]['source']['applied_interval'] is None


@pytest.mark.parametrize('mutation',[
    lambda a:a.update(safety_failure=True),lambda a:a.update(safety_events=['ORIGIN_DENIED']),
    lambda a:a['records'][0].update(identity_state='CONFLICTING'),
    lambda a:a['resource'].update(received_bytes=None),
    lambda a:a.update(cleanup='UNKNOWN'),lambda a:a.update(applied_interval=['wrong','dates']),
    lambda a:a.update(failure='UNCLASSIFIED_FAILURE'),
])
def test_actual_transport_hard_mutations_stop(monkeypatch,tmp_path,mutation):
    out,calls,_=through_transport(monkeypatch,tmp_path,mutation=mutation)
    assert len(calls)==1 and out['stop_reason']


def test_checkpoint_failure_stops_real_transport(monkeypatch,tmp_path):
    def fail(_):raise OSError('checkpoint unavailable')
    out,calls,_=through_transport(monkeypatch,tmp_path,checkpoint=fail)
    assert len(calls)==1 and out['stop_reason']=='CHECKPOINT_FAILURE_NO_NEXT_CALL'


@pytest.mark.parametrize('kind,state',[('complete','COMPLETE'),('missing_total','UNKNOWN')])
def test_complete_and_missing_total_keep_criteria_checks(monkeypatch,tmp_path,kind,state):
    out,calls,_=through_transport(monkeypatch,tmp_path,kind=kind)
    assert len(calls)==2 and out['results'][0]['enumeration_completeness']==state
    out,calls,_=through_transport(monkeypatch,tmp_path,kind=kind,echo='wrong')
    assert len(calls)==1 and out['stop_reason']


def test_screening_retains_sparse_related_and_generic_counts():
    from app.pipeline.discovery_screening import retain_screening
    a=dict(completeness='INCOMPLETE',records=[
        dict(reference='A',fields={}),
        dict(reference='B',fields=dict(proposal=dict(state='PRESENT_VALUE',value='Variation of condition 2 of planning permission 20683/25 affecting layout of plots 18 to 32',locator='a.summaryLink'))),
        dict(reference='C',fields=dict(proposal=dict(state='PRESENT_VALUE',value='Installation of 1 air handling unit',locator='a.summaryLink')))])
    before=deepcopy(a);retain_screening(a)
    assert a['completeness']==before['completeness'] and len(a['records'])==3
    for old,r in zip(before['records'],a['records']):
        assert r['fields']==old['fields'] and r['reference']==old['reference']
        s=r['processing_screen'];assert s['retained'] and not s['exclusion']
        assert s['residential_dwelling_count'] is None and s['count_metric']=='UNKNOWN'
    assert a['records'][1]['processing_screen']['parent_reference'] is None
    assert a['records'][1]['processing_screen']['related_reference_literals']==['20683/25']
