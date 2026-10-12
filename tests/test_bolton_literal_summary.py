"""Synthetic source/transport fixtures. No claim of current council truth."""
from dataclasses import replace
import json
import subprocess
import sys
import time
import pytest
import requests
from verification.stage26b_l1 import bolton_literal as b
from verification.stage26b_l1.bolton_rehearsal import fixture_html, FixtureResponse, dispatch
from verification.stage26b_l1.actions_runner import supervise
from app.pipeline.material_change import _classify_planning_state

SHA = '1'*40
C, CONTROL = b.CASES

def fields(case=C, **kwargs): return b.parse_summary(fixture_html(case, **kwargs), case)

def test_literal_unchanged_is_not_verified_pending():
    r = b.interpret(C, fields())
    assert r['outcome'] == 'SOURCE_FACT_VERIFIED_UNCHANGED'
    assert r['source_status_raw'] == 'Deposited'
    assert r['semantic_state'] == 'UNKNOWN_UNMAPPED'
    assert r['semantic_materiality'] == 'NO_SOURCE_FACT_CHANGE'

@pytest.mark.parametrize('status,decision,state', [('Decided','Approve','granted'),
    ('Decided','Refused','refused'), ('Withdrawn','','withdrawn')])
def test_unknown_start_never_manufactures_materiality(status, decision, state):
    r = b.interpret(C, fields(status=status, decision=decision, date='2026-10-11'))
    assert r['semantic_state'] == state
    assert r['source_fact_change'] == 'CHANGED'
    assert r['outcome'] == 'SOURCE_FACT_VERIFIED_CHANGED'
    assert r['semantic_materiality'] == 'UNKNOWN_REQUIRES_REVIEW'

def test_unknown_to_unknown_verified_fact_only():
    r = b.interpret(C, fields(status='Council processing label'))
    assert r['semantic_state'] == 'UNKNOWN_UNMAPPED'
    assert r['semantic_materiality'] == 'UNKNOWN_REQUIRES_REVIEW'

def test_global_fallback_is_preserved_but_not_used():
    assert _classify_planning_state(None, 'Deposited') == 'not_yet_decided'
    assert b.semantic_state(fields()) == 'UNKNOWN_UNMAPPED'
    assert b.semantic_state(fields(status='Unrecognised')) == 'UNKNOWN_UNMAPPED'

@pytest.mark.parametrize('status',['Committee review','Resolution recorded','Council processing label'])
def test_unmapped_labels_cannot_reach_global_fallback(status):
    assert b.semantic_state(fields(status=status))=='UNKNOWN_UNMAPPED'

def test_closed_other_table_does_not_certify_unclosed_summary():
    html=fixture_html(C).replace('</table>','')
    html=html.replace('<body>','<body><table><tr><td>Other</td></tr></table>')
    with pytest.raises(b.BoundaryFailure):b.parse_summary(html,C)

def test_ambiguity_latches_run_and_no_second_dispatch():
    calls=[]
    def conflict(*a,**k):
        calls.append(a)
        return FixtureResponse(fixture_html(C).replace('Deposited','').encode())
    audit=b.run(sha=SHA,dispatch=conflict)
    assert len(calls)==1 and audit['results'][1]['attempted'] is False
    assert audit['results'][1]['requests']==0 and audit['execution_status']=='FAIL'

@pytest.mark.parametrize('defect',['missing','scope','semantic','private','count','complete'])
def test_closed_artifact_validation(defect):
    a=b.run(sha=SHA,dispatch=dispatch)
    if defect=='missing':a['results']=[]
    if defect=='scope':a['results'][0]['reference']='OTHER'
    if defect=='semantic':a['results'][0]['semantic_state']='not_yet_decided'
    if defect=='private':a['results'][0]['proposal']='SECRET'
    if defect=='count':a['requests']=0
    if defect=='complete':a['execution_status']='FAIL'
    with pytest.raises(ValueError):b.validate(a)

@pytest.mark.parametrize('value',['private@example.com','<html>secret</html>','x'*257])
def test_artifact_rejects_literal_privacy_leak(value):
    a=b.run(sha=SHA,dispatch=dispatch)
    a['results'][0]['source_status_raw']=value
    with pytest.raises(ValueError):b.validate(a)

def test_absence_requires_explicit_blank_rows():
    f = fields(); assert f['Decision'] is None and f['Decision Issued Date'] is None
    html = fixture_html(C).replace('<tr><th>Decision</th><td></td></tr>', '')
    parsed=b.parse_summary(html,C)
    assert parsed.evidence['decision']=='NOT_PRESENT'
    result=b.interpret(C,parsed)
    assert result['source_retrieval']=='COMPLETE_FOR_STATUS_ONLY'
    assert result['semantic_materiality']=='UNKNOWN_REQUIRES_REVIEW'

def test_control_unchanged():
    r = b.interpret(CONTROL, fields(CONTROL))
    assert r['outcome']=='VERIFIED_UNCHANGED' and r['semantic_state']=='granted'
    assert r['source_decision_date']=='2026-09-11'

@pytest.mark.parametrize('changes,outcome', [({'decision':'Refused','date':'2026-10-11'},'VERIFIED_MATERIAL_CHANGE'),
    ({'date':'2026-09-12'},'VERIFIED_MATERIAL_CHANGE')])
def test_control_change_uses_existing_contract(changes,outcome):
    assert b.interpret(CONTROL,fields(CONTROL,**changes))['outcome']==outcome

@pytest.mark.parametrize('changes',[{'decision':''},{'date':''}])
def test_control_missing_prior_fact_fails(changes):
    with pytest.raises(b.BoundaryFailure):b.interpret(CONTROL,fields(CONTROL,**changes))

@pytest.mark.parametrize('label,value',[('Reference','OTHER'),('Status','Refused'),('Decision','Refused'),('Decision Issued Date','2026-10-11')])
def test_conflicting_duplicate_rejected(label,value):
    html=fixture_html(C).replace('</table>',f'<tr><th>{label}</th><td>{value}</td></tr></table>')
    with pytest.raises(b.BoundaryFailure):b.parse_summary(html,C)

def test_identical_duplicates_reconcile_existing_parser():
    html=fixture_html(C).replace('</table>','<tr><th>Status</th><td>Deposited</td></tr></table>')
    assert b.parse_summary(html,C)['Status']=='Deposited'

@pytest.mark.parametrize('html',[fixture_html(C).replace(C.reference,'OTHER'),
    fixture_html(C).replace(C.reference,''),fixture_html(C).replace('Deposited',''),
    '<html>broken',fixture_html(C).replace('simpleDetailsTable','other')])
def test_missing_wrong_or_malformed_summary(html):
    with pytest.raises(b.BoundaryFailure):b.parse_summary(html,C)

@pytest.mark.parametrize('code,outcome',[(403,'SOURCE_UNAVAILABLE'),(404,'SOURCE_UNAVAILABLE'),
    (429,'RATE_LIMITED'),(503,'SOURCE_UNAVAILABLE')])
def test_http_failures_never_verify_or_claim_not_found(code,outcome):
    responses=[]
    def fail(*a,**k):
        r=FixtureResponse(b'error');r.status_code=code;responses.append(r);return r
    audit=b.run(sha=SHA,dispatch=fail)
    assert audit['execution_status']=='FAIL'
    assert audit['results'][0]['outcome']==outcome
    assert all(r.closed for r in responses)
    assert all(not r['source_fact_verified'] for r in audit['results'])

def test_transient_retry_counted():
    calls=[]
    def transient(method,url,**kwargs):
        calls.append(url)
        if len(calls)==1:raise requests.Timeout()
        return dispatch(method,url,**kwargs)
    audit=b.run(sha=SHA,dispatch=transient)
    assert audit['execution_status']=='COMPLETE' and audit['requests']==3
    assert audit['results'][0]['retries']==1

def test_retry_body_accounting_is_cumulative_not_per_response():
    calls=[]
    def transient(method,url,**kwargs):
        calls.append(url)
        if len(calls)==1:
            response=FixtureResponse(b'x'*600_000);response.status_code=503
            return response
        response=dispatch(method,url,**kwargs)
        if url==C.url:
            response=FixtureResponse((fixture_html(C).replace('</body>',' '*500_000+'</body>')).encode())
        return response
    audit=b.run(sha=SHA,dispatch=transient)
    assert audit['execution_status']=='COMPLETE'
    assert 1_000_000<audit['results'][0]['received_bytes']<2_000_000
    assert audit['results'][0]['retries']==1 and audit['requests']==3
    b.validate(audit)

def test_timeout_no_unbounded_retry():
    def timeout(*a,**k):raise requests.Timeout()
    audit=b.run(sha=SHA,dispatch=timeout)
    assert audit['requests']==2 and audit['results'][0]['outcome']=='TIMEOUT'
    assert audit['results'][1]['requests']==0

@pytest.mark.parametrize('location',[C.url, 'https://evil.example/',b.BASE+'/applicationDetails.do?activeTab=documents&keyVal=X'])
def test_redirect_never_followed(location):
    calls=[]
    def redirected(*a,**k):
        calls.append(a);r=FixtureResponse(b'');r.status_code=302
        r.headers={'Location':location,'Content-Type':'text/html'};return r
    audit=b.run(sha=SHA,dispatch=redirected)
    assert audit['execution_status']=='FAIL'
    assert all(r['source_fact_verified'] is False for r in audit['results'])
    assert audit['results'][0]['redirects']==1
    assert len(calls)<=2

def test_oversize_actual_body_ignores_content_length():
    responses=[]
    def huge(*a,**k):
        r=FixtureResponse(b'x'*1_000_001)
        r.headers={'Content-Type':'text/html','Content-Length':'1'};responses.append(r);return r
    audit=b.run(sha=SHA,dispatch=huge)
    assert audit['execution_status']=='FAIL' and audit['results'][1]['requests']==0
    assert responses[0].closed and audit['received_bytes']>1_000_000

def test_exact_tuples_only():
    for key,value in [('reference','OTHER'),('key','X'),('application_id',999)]:
        with pytest.raises(ValueError):b.admit(replace(C,**{key:value}))

def test_status_only_no_link_following_and_privacy():
    calls=[]
    def response(method,url,**kwargs):
        calls.append((method,url));case=next(c for c in b.CASES if c.url==url)
        html=fixture_html(case).replace('</body>', '<a href="documents">SECRET PROPOSAL</a><a href="relatedCases">PERSON NAME</a></body>')
        return FixtureResponse(html.encode())
    audit=b.run(sha=SHA,dispatch=response);data=b.encode(audit)
    assert calls==[('GET',c.url) for c in b.CASES]
    for secret in (b'SECRET PROPOSAL',b'PERSON NAME',b'<html',b'cookie',b'DATABASE_URL'):
        assert secret not in data
    assert audit['persistence'] is False

def test_artifact_overflow():
    with pytest.raises(ValueError):b.encode({'excess':'x'*16_384})

def test_http_adapter_denies_non_fixed_routes_before_network():
    for method,url in [('POST',C.url),('GET',b.BASE+'/search.do'),('GET','https://evil.example')]:
        with pytest.raises(b.BoundaryFailure):b.http_dispatch(method,url)

def test_independent_deadline_hung_child():
    started=time.monotonic()
    status,expired=supervise([sys.executable,'-c','import time;time.sleep(60)'],
        env={'PATH':'/usr/bin:/bin'},deadline=.1)
    assert status==124 and expired and time.monotonic()-started<7
