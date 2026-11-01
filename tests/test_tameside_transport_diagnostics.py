"""Offline exceptions only. No council, DNS, socket, DB or Render operation."""
import errno
import json
import socket
import ssl
from datetime import date
import pytest
import requests
import urllib3.exceptions as u3
from verification.discovery import source_diagnostics as sd
from verification.discovery.idox_window import WindowBoundary,WindowConfig,run,live
from verification.discovery.four_council_proof import manifest_scope,validate_proof
from verification.stage26b_l1.request_boundary import BoundaryFailure

CONFIG=WindowConfig('tameside','RECEIVED',date(2026,10,24),date(2026,10,30),max_transport_retries=0,max_rows=60)
ROW=dict(council='tameside',semantics='RECEIVED',start='2026-10-24',end='2026-10-30')
SECRET='SENSITIVE_password_cookie_header_body_https://user:pass@example.invalid/?token=HIDDEN'

@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def forbidden(*_,**__):raise AssertionError('OFFLINE_TEST_NETWORK_FORBIDDEN')
    monkeypatch.setattr(socket,'getaddrinfo',forbidden)
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(requests.Session,'request',forbidden)

def wrapped(exc):return requests.ConnectionError(u3.MaxRetryError(None,SECRET,exc))

CASES=[
 (wrapped(socket.gaierror(socket.EAI_AGAIN,SECRET)),'DNS_FAILURE','EAI_AGAIN','REQUESTS_CONNECTION_ERROR'),
 (wrapped(socket.gaierror(socket.EAI_NONAME,SECRET)),'DNS_FAILURE','EAI_NONAME','REQUESTS_CONNECTION_ERROR'),
 (wrapped(ConnectionRefusedError(errno.ECONNREFUSED,SECRET)),'TCP_CONNECTION_REFUSED','ECONNREFUSED','REQUESTS_CONNECTION_ERROR'),
 (wrapped(OSError(errno.ENETUNREACH,SECRET)),'TCP_NETWORK_UNREACHABLE','ENETUNREACH','REQUESTS_CONNECTION_ERROR'),
 (wrapped(OSError(errno.EHOSTUNREACH,SECRET)),'TCP_HOST_UNREACHABLE','EHOSTUNREACH','REQUESTS_CONNECTION_ERROR'),
 (wrapped(PermissionError(errno.EACCES,SECRET)),'TRANSPORT_PERMISSION_DENIED','EACCES','REQUESTS_CONNECTION_ERROR'),
 (wrapped(ConnectionResetError(errno.ECONNRESET,SECRET)),'CONNECTION_RESET','ECONNRESET','REQUESTS_CONNECTION_ERROR'),
 (requests.exceptions.SSLError(u3.SSLError(ssl.SSLCertVerificationError(1,SECRET))),'TLS_CERTIFICATE_VERIFICATION_FAILED','UNKNOWN','REQUESTS_SSL_ERROR'),
 (requests.exceptions.SSLError(SECRET),'TLS_FAILURE','UNKNOWN','REQUESTS_SSL_ERROR'),
 (requests.exceptions.ProxyError(u3.ProxyError(SECRET,ConnectionRefusedError(errno.ECONNREFUSED,SECRET))),'PROXY_FAILURE','ECONNREFUSED','REQUESTS_PROXY_ERROR'),
 (requests.ConnectTimeout(SECRET),'CONNECT_TIMEOUT','UNKNOWN','REQUESTS_CONNECT_TIMEOUT'),
 (requests.ReadTimeout(SECRET),'READ_TIMEOUT','UNKNOWN','REQUESTS_READ_TIMEOUT'),
 (requests.Timeout(SECRET),'TIMEOUT_UNKNOWN_STAGE','UNKNOWN','REQUESTS_TIMEOUT'),
 (requests.ConnectionError(SECRET),'UNKNOWN','UNKNOWN','REQUESTS_CONNECTION_ERROR'),
 (RuntimeError(SECRET),'UNKNOWN','UNKNOWN','UNKNOWN'),
 (wrapped(u3.NameResolutionError('example.invalid',None,socket.gaierror(socket.EAI_AGAIN,SECRET))),'DNS_FAILURE','EAI_AGAIN','REQUESTS_CONNECTION_ERROR'),
 (requests.ConnectionError(u3.ProxyError(SECRET,socket.gaierror(socket.EAI_NONAME,SECRET))),'PROXY_FAILURE','EAI_NONAME','REQUESTS_CONNECTION_ERROR'),
]

@pytest.mark.parametrize('exc,reason,code,cls',CASES)
def test_recognised_and_unknown_failures_retain_only_safe_detail(exc,reason,code,cls):
    calls=[]
    def dispatch(*_,**__):calls.append(1);raise exc
    with manifest_scope(ROW):
        out=run(dispatch,CONFIG,retain_proof=True)
        validate_proof(out['retained_proof'])
    t=out['failure_diagnostic']['transport'];detail=t['failure']
    assert sd.validate_transport(t)==t
    assert detail==dict(version=1,stage='REQUEST_DISPATCH',reason=reason,exception_class=cls,error_code=code,chain_truncated=False)
    assert out['failure_diagnostic']['stage']=='FORM_REQUEST' and t['http_status'] is None
    assert out['resource']['requests_attempted']==len(calls)==1 and out['resource']['retries']==0
    assert out['resource']['received_bytes']==0 and out['resource']['retry_policy']=='NO_INTERNAL_RETRY'
    assert out['completeness']=='FAILED' and not out['records'] and not out['pages']
    assert out['cleanup']=='BOUNDARY_CLOSED' and out['persistence'] is False
    expected='TIMEOUT' if isinstance(exc,requests.Timeout) else 'SOURCE_UNAVAILABLE' if isinstance(exc,requests.ConnectionError) else 'PARTIAL_RETRIEVAL'
    assert t['rejection_outcome']==expected
    assert t['rejection_reason']==('unqualified transport failure' if expected=='PARTIAL_RETRIEVAL' else 'transport failed')
    assert SECRET not in json.dumps(out) and 'token=HIDDEN' not in json.dumps(out)
    assert out['retained_proof']['events'][0]['transport']==t
    assert len(json.dumps(detail).encode())<=sd.FAILURE_BYTES==512

class Response:
    status_code=200
    headers={'Content-Type':'text/html'}
    closed=False
    def iter_content(self,_):raise requests.ReadTimeout(SECRET);yield b''
    def close(self):self.closed=True

def test_response_read_failure_closes_response_and_preserves_accounting():
    response=Response();out=run(lambda *a,**kw:response,CONFIG)
    detail=out['failure_diagnostic']['transport']['failure']
    assert detail['stage']=='RESPONSE_READ' and detail['reason']=='READ_TIMEOUT'
    assert response.closed and out['resource']['requests_attempted']==1 and out['resource']['retries']==0
    assert out['failure_diagnostic']['transport']['http_status']==200
    assert SECRET not in json.dumps(out)

def test_current_live_session_configuration_is_preserved_without_live_transport(monkeypatch):
    seen={}
    class Session:
        def __enter__(self):return self
        def __exit__(self,*_):seen['closed']=True
        def mount(self,scheme,adapter):seen['scheme']=scheme;seen['retry_total']=adapter.max_retries.total
        def request(self,*args,**kw):
            seen['trust_env']=self.trust_env;seen['kwargs']=kw
            raise requests.ConnectionError(SECRET)
    monkeypatch.setattr(requests,'Session',Session)
    out=live(CONFIG)
    assert seen['closed'] and seen['trust_env'] is False and seen['scheme']=='https://' and seen['retry_total']==0
    assert seen['kwargs']['timeout']==(3,8) and seen['kwargs']['allow_redirects'] is False
    assert 'verify' not in seen['kwargs'] and 'proxies' not in seen['kwargs']
    assert out['cleanup']=='SESSION_BOUNDARY_CLOSED' and out['failure_diagnostic']['transport']['failure']['reason']=='UNKNOWN'

def test_safe_classifier_does_not_inspect_unknown_exception_or_environment(monkeypatch):
    monkeypatch.setenv('SYNTHETIC_SECRET',SECRET)
    class Hostile(Exception):
        def __str__(self):raise AssertionError('no stringify')
        @property
        def args(self):raise AssertionError('no unknown args')
        @property
        def reason(self):raise AssertionError('no unknown reason')
    detail=sd.transport_failure(Hostile(SECRET),SECRET)
    assert detail['stage']==detail['reason']==detail['exception_class']==detail['error_code']=='UNKNOWN'
    assert SECRET not in json.dumps(detail)

def test_graph_bound_cycles_and_oversize_text_are_safe():
    err=requests.ConnectionError(SECRET*10000)
    assert sd.transport_failure(err)['reason']=='UNKNOWN'
    err.__cause__=err
    assert sd.transport_failure(err)['chain_truncated'] is False
    for _ in range(20):err=requests.ConnectionError(err)
    detail=sd.transport_failure(err,'REQUEST_DISPATCH')
    assert detail['chain_truncated'] is True and detail['reason']=='UNKNOWN'
    assert len(json.dumps(detail).encode())<=512 and SECRET not in json.dumps(detail)

@pytest.mark.parametrize('patch',[{'reason':SECRET},{'stage':'DNS_LOOKUP'},{'exception_class':'ArbitraryClass'},
 {'error_code':999},{'version':True},{'chain_truncated':0},{'url':SECRET}])
def test_validator_refuses_unsafe_detail(patch):
    value=sd.transport_failure(RuntimeError(SECRET));value.update(patch)
    with pytest.raises(ValueError,match='DIAGNOSTIC_SCHEMA'):sd.validate_transport_failure(value)

def test_legacy_diagnostics_unchanged_and_stale_detail_cleared():
    legacy=dict(http_status=None,media_type=None,redirect=None,rejection_outcome='SOURCE_UNAVAILABLE',rejection_reason='transport failed')
    assert sd.validate_transport(legacy)==legacy and 'failure' not in sd.transport_facts(None,None)
    def dispatch(*_,**__):raise requests.ConnectTimeout(SECRET)
    boundary=WindowBoundary(dispatch,CONFIG)
    with pytest.raises(BoundaryFailure):boundary.retrieve('GET',CONFIG.form_url)
    assert boundary.transport_failure['reason']=='CONNECT_TIMEOUT'
    with pytest.raises(BoundaryFailure):boundary.retrieve('GET','https://elsewhere.invalid/')
    assert boundary.transport_failure is None and boundary.last_response is None

def test_diagnostic_internal_failure_cannot_replace_original_refusal(monkeypatch):
    def broken(*_):raise RuntimeError(SECRET)
    monkeypatch.setattr(sd,'_transport_failure',broken)
    def dispatch(*_,**__):raise requests.ConnectionError(SECRET)
    out=run(dispatch,CONFIG)
    t=out['failure_diagnostic']['transport']
    assert t['rejection_outcome']=='SOURCE_UNAVAILABLE' and t['rejection_reason']=='transport failed'
    assert t['failure']['stage']=='REQUEST_DISPATCH' and t['failure']['reason']=='UNKNOWN'
    assert SECRET not in json.dumps(out) and out['resource']['retries']==0
    assert len(json.dumps(t['failure']).encode())<=512

def test_upstream_http_status_is_not_mislabelled_as_a_network_layer():
    class Upstream(Response):
        status_code=503
        def iter_content(self,_):yield b''
    response=Upstream();out=run(lambda *a,**kw:response,CONFIG)
    t=out['failure_diagnostic']['transport']
    assert t['http_status']==503 and t['failure']['stage']=='RESPONSE_STATUS'
    assert t['failure']['reason']=='UNKNOWN' and response.closed
    assert out['resource']['requests_attempted']==1 and out['resource']['retries']==0
