"""Corrective addendum (specification 032 section 9): final publication inside the enforced memory scope and a bounded reserve, then final closure; safe bounded source transport diagnostics.
Offline, no network, no database."""
import io
import json
import subprocess
import time
from pathlib import Path

import pytest

from app.ingestion.ledger import Denied
from verification.discovery import source_diagnostics as sd
from verification.discovery.idox_window import run
from verification.bolton_recon.fixtures import FORM
from verification.ingestion_storage import operational_owner as oo
from verification.ingestion_storage import stable_pipeline as sp
from verification.ingestion_storage.connection_diagnostics import fixed_stop_reason
from verification.ingestion_storage.operational_journal import Journal
from verification.ingestion_storage.operational_publication import GitHub
from verification.discovery.source_diagnostics import response_shape


# --------------------------------------------------------------------------- the publication reserve (requests and seconds)
def github(**kw):
    def runner(command,**_):
        return subprocess.CompletedProcess(command,0,stdout=b'{}',stderr=b'')
    return GitHub(lambda *a,**k:None,lambda:None,runner=runner,**kw)


def test_reserve_caps_requests_and_never_widens_the_overall_bound():
    g=github(bound=10)
    with g.reserve_scope(3,60):
        for _ in range(3):g.call('GET','x')
        with pytest.raises(ValueError,match='GITHUB_PUBLICATION_RESERVE_EXHAUSTED'):g.call('GET','x')
        with pytest.raises(ValueError,match='GITHUB_PUBLICATION_RESERVE_EXHAUSTED'):g.probe('x')
    assert g.reserve is None and g.requests==3
    for _ in range(7):g.call('GET','x')      # outside the scope only the overall bound applies
    with pytest.raises(ValueError,match='GITHUB_REQUEST_BOUND'):g.call('GET','x')
    h=github(bound=4);h.requests=3
    with h.reserve_scope(14,60):      # the reserve is clipped to what remains of the overall bound
        h.call('GET','x')
        with pytest.raises(ValueError):h.call('GET','x')


def test_reserve_expires_by_wall_time_and_cannot_nest():
    g=github(bound=50)
    with g.reserve_scope(10,0.0):
        with pytest.raises(ValueError,match='GITHUB_PUBLICATION_RESERVE_EXHAUSTED'):g.call('GET','x')
    with g.reserve_scope(10,60):
        with pytest.raises(ValueError):
            with g.reserve_scope(1,60):pass
    assert g.reserve is None


# --------------------------------------------------------------------------- publication inside the scope, then the closure; the closed-envelope guard is untouched
class StubMemory:
    """Same contract as OperationalMemory for the controller: snapshot() while enforcing, close() once."""
    source=None
    def __init__(self):self.closed=False;self.snapshots=0
    def snapshot(self):
        assert not self.closed;self.snapshots+=1
    def close(self):
        self.closed=True;return dict(owned_groups_removed=True,owned_survivors=0,memory=dict(aggregate=dict(events=dict(oom_kill=0))))


def runner_with_memory(tmp_path,gh_runner=None):
    urls={r:'postgresql://%s:x@h/db'%r for r in oo.ROLES};Path(tmp_path).mkdir(parents=True,exist_ok=True)
    memory=StubMemory()
    r=sp.HostedRunner(urls,Journal(tmp_path/'j'),None,None,{},'192.0.2.1',memory,evidence_head='1'*40,manifest_sha256='c'*64,revision='a'*40)
    r.github=GitHub(r.emit,lambda:r.check(),runner=gh_runner or (lambda command,**_:subprocess.CompletedProcess(command,0,stdout=b'{}',stderr=b'')),bound=140)
    return r,memory


def fresh_result(r):
    return r.hosted_failure(RuntimeError('boom'),None)


def test_the_result_is_published_while_the_scope_enforces_then_the_scope_is_closed(tmp_path):
    r,memory=runner_with_memory(tmp_path);seen=[]
    def publish(result):
        seen.append(dict(memory_closed=memory.closed,cleanup=result['cleanup'],stage=result['closure_stage'],reserve=r.github.reserve is not None))
        r.github.call('GET','x');r.github.call('GET','y')
    r.publish_completed=publish
    result=fresh_result(r)
    assert not memory.closed and result['cleanup']=='PENDING_MEMORY_SCOPE_CLOSURE'      # nothing removed the scope before publication
    sealed=r.finalise(result)
    assert seen==[dict(memory_closed=False,cleanup='PENDING_MEMORY_SCOPE_CLOSURE',stage='PUBLISHED_BEFORE_MEMORY_SCOPE_CLOSURE',reserve=True)]
    assert memory.closed and sealed['closure_stage']=='FINAL_AFTER_PUBLICATION' and sealed['publication']=='PUBLISHED' and sealed['publication_reason'] is None
    assert sealed['cleanup']=='CLOSED' and sealed['published_cleanup']=='PENDING_MEMORY_SCOPE_CLOSURE'
    assert sealed['status']=='STOP_RECONCILE_NO_RETRY'      # a failed capture stays a stop; closure does not turn it into success
    assert json.loads((tmp_path/'j'/'final-result.json').read_bytes())['closure_stage']=='FINAL_AFTER_PUBLICATION'      # the sealed local record carries the complete closure


def test_no_github_call_is_admitted_after_the_memory_scope_is_closed(tmp_path):
    r,memory=runner_with_memory(tmp_path)
    r.publish_completed=lambda result:r.github.call('GET','x')
    r.finalise(fresh_result(r))
    assert memory.closed
    with pytest.raises(Denied) as caught:r.github.call('GET','x')      # the guard that denied the first run is exactly as before
    assert caught.value.args[0]=='RESOURCE_ENVELOPE_CLOSED_NO_MORE_OPERATIONS'
    with pytest.raises(Denied):r.github.probe('x')


def test_a_publication_failure_carries_a_fixed_reason_and_does_not_stop_the_closure(tmp_path):
    r,memory=runner_with_memory(tmp_path)
    def publish(result):raise sp.Uncertain('EVIDENCE_HEAD_MOVED_RECONCILE')
    r.publish_completed=publish
    sealed=r.finalise(fresh_result(r))
    assert sealed['publication']=='UNCERTAIN_Uncertain' and sealed['publication_reason']=='EVIDENCE_HEAD_MOVED_RECONCILE' and memory.closed and sealed['cleanup']=='CLOSED'
    r2,memory2=runner_with_memory(tmp_path/'b')
    r2.publish_completed=lambda result:[r2.github.call('GET','x') for _ in range(15)]
    sealed2=r2.finalise(fresh_result(r2))
    assert sealed2['publication_reason']=='GITHUB_PUBLICATION_RESERVE_EXHAUSTED' and memory2.closed      # a runaway publication is stopped by the reserve, then the scope is closed
    r3,_=runner_with_memory(tmp_path/'c')
    r3.publish_completed=lambda result:(_ for _ in ()).throw(RuntimeError('free text with a secret-looking token'))
    sealed3=r3.finalise(fresh_result(r3))
    assert sealed3['publication']=='UNCERTAIN_RuntimeError' and sealed3['publication_reason'] is None and 'secret' not in json.dumps(sealed3)      # never arbitrary exception text


def test_a_failed_closure_is_never_reported_as_closed(tmp_path):
    r,memory=runner_with_memory(tmp_path)
    class Bad(StubMemory):
        def close(self):raise OSError('no')
    r.memory=Bad()
    r.publish_completed=lambda result:None
    sealed=r.finalise(fresh_result(r))
    assert sealed['cleanup']!='CLOSED' and sealed['status']=='STOP_RECONCILE_NO_RETRY'


def test_the_reserve_fits_the_publisher_and_the_hosted_bound():
    assert sp.PUBLICATION_RESERVE_REQUESTS==14 and sp.PUBLICATION_RESERVE_SECONDS==90 and sp.PUBLICATION_RESERVE_REQUESTS<=140
    two_file_publication=6+2*2
    assert two_file_publication+2<=sp.PUBLICATION_RESERVE_REQUESTS      # head read, commit read and the four-step write/readback fit with margin


# --------------------------------------------------------------------------- safe source transport diagnostics
class Resp:
    def __init__(self,status=200,ctype='text/html',headers=None,body=b'x'*183):
        self.status_code=status;self.headers=dict({'Content-Type':ctype} if ctype is not None else {},**(headers or {}));self.b=body;self.closed=False;self.raw=io.BytesIO()
    def iter_content(self,n):yield self.b
    def close(self):self.closed=True


def failed_run(response):
    calls=[]
    def dispatch(method,url,**kw):calls.append(url);return response
    return run(dispatch),calls


def test_a_403_is_reported_with_its_status_media_type_and_fixed_reason():
    cookie='session=SECRET-COOKIE-VALUE'
    result,calls=failed_run(Resp(403,'text/html; charset=utf-8',{'Set-Cookie':cookie,'Server':'secret-server','X-Trace':'token-abc'},b'<html>Access denied for 203.0.113.9</html>'))
    d=result['failure_diagnostic']
    assert len(calls)==1 and result['failure']=='BoundaryFailure:SOURCE_CONTRACT_REJECTED' and d['code']=='SOURCE_CONTRACT_REJECTED' and d['stage']=='FORM_REQUEST'      # the original classification is preserved
    assert d['transport']==dict(http_status=403,media_type='text/html',redirect='NONE',rejection_outcome='SOURCE_UNAVAILABLE',rejection_reason='HTTP failure')
    dumped=json.dumps(result)
    for forbidden in ('SECRET-COOKIE','secret-server','token-abc','203.0.113.9','Access denied'):assert forbidden not in dumped
    assert sd.validate(d)==d


def test_other_failure_shapes_are_distinguished_without_naming_a_cause():
    r,_=failed_run(Resp(200,'application/json'))
    assert r['failure_diagnostic']['transport']==dict(http_status=200,media_type='application/json',redirect='NONE',rejection_outcome='PARTIAL_RETRIEVAL',rejection_reason='response shape')
    r,_=failed_run(Resp(302,'text/html',{'Location':'https://elsewhere.example/login?token=abc'}))
    t=r['failure_diagnostic']['transport']
    assert t['http_status']==302 and t['redirect']=='OTHER_ORIGIN' and 'elsewhere' not in json.dumps(r) and 'token=abc' not in json.dumps(r)
    r,_=failed_run(Resp(302,'text/html',{'Location':'/online-applications/other.do'}))
    assert r['failure_diagnostic']['transport']['redirect'] in ('SAME_ORIGIN','OTHER_ORIGIN') and r['failure_diagnostic']['code']=='SOURCE_CONTRACT_REJECTED'
    r,_=failed_run(Resp(429,'text/html'))
    assert r['failure_diagnostic']['transport']['rejection_outcome']=='RATE_LIMITED' and r['failure_diagnostic']['transport']['http_status']==429
    r,_=failed_run(Resp(200,'application/x-weird'))
    assert r['failure_diagnostic']['transport']['media_type']=='OTHER'
    r,_=failed_run(Resp(200,None))
    assert r['failure_diagnostic']['transport']['media_type'] is None


def test_unknown_literals_are_never_exported_and_the_schema_is_strict():
    class Odd(Exception):
        outcome='SECRET_OUTCOME';reason='password=hunter2'
    out=sd.transport_facts(dict(http_status=200,media_type='text/html',redirect='NONE'),Odd())
    assert out['rejection_outcome']=='OTHER' and out['rejection_reason']=='OTHER' and 'hunter2' not in json.dumps(out)
    assert sd.transport_facts(None,None)==dict(http_status=None,media_type=None,redirect=None,rejection_outcome=None,rejection_reason=None)
    base=sd.shape(b'',"FORM_REQUEST","SOURCE_CONTRACT_REJECTED")
    assert 'transport' not in base and sd.validate(base)==base      # version-1 records without transport still validate
    for bad in (dict(http_status=99),dict(http_status='403'),dict(media_type='text/evil'),dict(redirect='https://x'),dict(rejection_reason='free text'),dict(extra=1)):
        value=dict(sd.shape(b'',"FORM_REQUEST","SOURCE_CONTRACT_REJECTED"),transport=dict(http_status=200,media_type='text/html',redirect='NONE',rejection_outcome='OTHER',rejection_reason='OTHER',**{}))
        value['transport'].update(bad)
        with pytest.raises(ValueError):sd.validate(value)


def test_response_shape_never_raises_and_exports_only_allow_listed_facts():
    class Broken:
        @property
        def status_code(self):raise RuntimeError('x')
        headers=None
    assert response_shape(Broken(),'https://h/x','https://h')==dict(http_status=None,media_type=None,redirect=None)
    shape=response_shape(Resp(301,'text/html',{'Location':'https://h/y','Set-Cookie':'a=b'}),'https://h/x','https://h')
    assert shape==dict(http_status=301,media_type='text/html',redirect='SAME_ORIGIN')
    assert response_shape(Resp(301,'text/html'),'https://h/x','https://h')['redirect']=='MISSING_LOCATION'


def test_hosted_failure_text_exports_the_publication_reason_code_only(tmp_path):
    assert fixed_stop_reason(ValueError('GITHUB_PUBLICATION_RESERVE_EXHAUSTED'))=='GITHUB_PUBLICATION_RESERVE_EXHAUSTED'
    assert fixed_stop_reason(ValueError('some other value error text')) is None


# ---------------------------------------------------------------- review fixes
def test_the_owner_accepts_a_published_pending_closure_only_with_its_stage_and_never_for_a_stop():
    from verification.ingestion_storage.operational_runner import hosted_finished
    ok=dict(status='STABLE_PIPELINE_CAPTURE_SCREENING_COMPLETED_RESTRICTED_RUNTIME_ONLY',cleanup='PENDING_MEMORY_SCOPE_CLOSURE',closure_stage='PUBLISHED_BEFORE_MEMORY_SCOPE_CLOSURE')
    assert hosted_finished(ok,[]) is True
    assert hosted_finished(dict(ok,closure_stage=None),[]) is False and hosted_finished(dict(ok,closure_stage='FINAL_AFTER_PUBLICATION'),[]) is False
    assert hosted_finished(dict(ok,status='STOP_RECONCILE_NO_RETRY'),[]) is False and hosted_finished(ok,['batch']) is False
    assert hosted_finished(dict(ok,cleanup='UNCERTAIN'),[]) is False
    assert hosted_finished(dict(status='X',cleanup='CLOSED'),[]) is True and hosted_finished(dict(status='X'),[]) is True      # earlier shapes still accepted


def test_transport_facts_are_those_of_the_failing_request_only():
    from verification.discovery.idox_window import WindowBoundary
    state={'n':0}
    def dispatch(method,url,**kw):
        state['n']+=1
        if state['n']>1:raise RuntimeError('dispatch failed')
        return Resp(200,'text/html')
    b=WindowBoundary(dispatch)
    b.request('GET',b.config.form_url);assert b.last_response['http_status']==200
    with pytest.raises(Exception):b.request('GET',b.config.form_url)      # the dispatch itself raises on the next request
    assert b.last_response is None
    with pytest.raises(Exception):b.retrieve('POST','https://elsewhere.example/x',b'a=b')      # rejected before any dispatch
    assert b.last_response is None
