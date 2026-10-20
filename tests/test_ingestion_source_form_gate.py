"""The form gate, through the REAL source boundary: `operational_source.read` -> the real supervisor -> the real credential-free worker process -> the real window runner and request boundary -> the real
`requests` stack, with only the HTTPS adapter redirected to a loopback fixture (tests/source_loopback_entry.py). A refusal, a redirect, a non-form page, a non-HTML page or a transient upstream status must
produce EXACTLY ONE GET: no POST, no listing request, no internal retry. A valid form continues, within the ten-request allowance. Loopback only; no council contact."""
import http.server
import json
import sys
import threading
from pathlib import Path

import pytest

from verification.bolton_recon.fixtures import FORM
from verification.discovery.idox_window import WindowConfig
from verification.ingestion_storage import operational_source as src
from tests.test_discovery_idox_window import page,SORT

CONFIG=dict(council='bolton',semantics='RECEIVED',start='2026-10-16',end='2026-10-16')
FORM_PATH='/online-applications/search.do?action=advanced&searchType=Application'


class Fixture:
    def __init__(self,responses):
        self.responses=list(responses);self.seen=[];fixture=self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*a):pass
            def handle_any(self):
                length=int(self.headers.get('Content-Length') or 0);body=self.rfile.read(length) if length else b''
                fixture.seen.append((self.command,self.path,bool(body),self.headers.get('X-Original-Host')))
                status,headers,payload=fixture.responses[len(fixture.seen)-1] if len(fixture.seen)<=len(fixture.responses) else (500,{'Content-Type':'text/html'},b'<html>unexpected extra request</html>')
                self.send_response(status)
                for k,v in {'Content-Type':'text/html; charset=utf-8',**headers}.items():self.send_header(k,v)
                self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
            do_GET=do_POST=handle_any
        self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    @property
    def port(self):return self.server.server_address[1]
    def close(self):
        self.server.shutdown();self.server.server_close()


def read_through_the_real_boundary(fixture,tmp_path,monkeypatch,kind='listing'):
    real=src.supervise
    def through_loopback(command,**kwargs):      # the SAME supervisor call; only the module the child runs is the test entry (which runs the production worker unchanged)
        command=[sys.executable,'-m','tests.source_loopback_entry','--loopback-port',str(fixture.port),*command[3:]]
        return real(command,**kwargs)
    monkeypatch.setattr(src,'supervise',through_loopback)
    return src.read(kind,CONFIG,root=tmp_path/'source')


def resp(status,body=b'',**headers):
    return (status,headers,body)


REFUSALS={
    'refusal_403':resp(403,b'<html>Access denied</html>'),
    'refusal_404':resp(404,b'<html>not found</html>'),
    'rate_limited_429':resp(429,b'<html>slow down</html>'),
    'transient_503':resp(503,b'<html>unavailable</html>'),
    'redirect_other_origin':resp(302,b'',Location='https://other.example/x'),
    'redirect_same_origin_form':resp(302,b'',Location='https://publicaccess.bolton.gov.uk'+FORM_PATH),
    'redirect_without_location':resp(302,b''),
    'non_form_html':resp(200,b'<html><body>hello</body></html>'),
    'login_page':resp(200,b'<html><body><form action="/login" method="post"><input name="user"></form></body></html>'),
    'not_html':resp(200,b'{"a":1}',**{'Content-Type':'application/json'}),
    'pdf':resp(200,b'%PDF-1.4',**{'Content-Type':'application/pdf'}),
}


@pytest.mark.parametrize('name',sorted(REFUSALS))
def test_a_bad_form_response_produces_exactly_one_get_and_nothing_else(name,tmp_path,monkeypatch):
    fixture=Fixture([REFUSALS[name],resp(200,FORM),resp(200,page())]);
    try:audit,outer=read_through_the_real_boundary(fixture,tmp_path,monkeypatch)
    finally:fixture.close()
    assert [(m,bool(body)) for m,_,body,_ in fixture.seen]==[('GET',False)],fixture.seen      # one GET, no body, no POST, no second request of any kind (so no listing request and no internal retry)
    assert fixture.seen[0][1]==FORM_PATH and fixture.seen[0][3]==WindowConfig('bolton').base.split('/')[2]      # the exact admitted form URL on the council host (rewritten to loopback only by the test adapter)
    assert audit['completeness']=='FAILED' and audit['failure'].endswith('SOURCE_CONTRACT_REJECTED') and audit['records']==[] and audit['pages']==[]
    assert audit['resource']['requests_attempted']==1 and audit['resource']['retries']==0 and audit['resource']['redirects']==0
    assert outer['exit_code']==0 and outer['cleanup']=='CLOSED' and outer['limit_hit'] is None      # a normal, accountable stop: the child closed cleanly
    diagnostic=audit['failure_diagnostic']
    assert diagnostic is not None and json.dumps(audit).count('hello')==0      # bounded diagnostics only; the body is never retained


def test_the_form_probe_worker_makes_the_same_single_get(tmp_path,monkeypatch):
    fixture=Fixture([resp(200,FORM),resp(200,page())])
    try:audit,_=read_through_the_real_boundary(fixture,tmp_path,monkeypatch,kind='form_probe')
    finally:fixture.close()
    assert [(m,bool(body)) for m,_,body,_ in fixture.seen]==[('GET',False)] and audit['observation']['outcome']=='FORM_RECOGNISED'


def test_a_valid_form_continues_to_the_listing_within_the_ten_request_allowance(tmp_path,monkeypatch):
    echo=FORM.replace(b'name="date(applicationReceivedStart)" value=""',b'name="date(applicationReceivedStart)" value="16/10/2026"').replace(b'name="date(applicationReceivedEnd)" value=""',b'name="date(applicationReceivedEnd)" value="16/10/2026"')
    results=lambda **kw:page(**kw).replace(b'28 Sep 2026',b'16 Oct 2026')
    fixture=Fixture([resp(200,FORM),resp(200,results()),resp(200,results()),resp(200,echo)])
    try:audit,outer=read_through_the_real_boundary(fixture,tmp_path,monkeypatch)
    finally:fixture.close()
    methods=[(m,bool(body)) for m,_,body,_ in fixture.seen]
    assert methods[0]==('GET',False) and methods[1]==('POST',True) and len(fixture.seen)<=10      # the form first; only then the search POST
    assert audit['resource']['requests_attempted']==len(fixture.seen) and audit['resource']['retries']==0 and audit['resource']['redirects']==0
    assert outer['exit_code']==0 and outer['cleanup']=='CLOSED'


def test_the_listing_budget_is_ten_requests_and_the_probe_budget_is_one():
    from verification.discovery.idox_window import WindowBoundary
    full=WindowBoundary(lambda *a,**k:None,WindowConfig(max_transport_retries=0));probe=WindowBoundary(lambda *a,**k:None,WindowConfig(max_transport_retries=0),probe=True)
    assert full.budget.requests==10 and full.budget.total_bytes==3_000_000 and full.budget.seconds==45 and full.max_retries==0
    assert probe.budget.requests==1 and probe.budget.total_bytes==262_144 and probe.budget.seconds==15
