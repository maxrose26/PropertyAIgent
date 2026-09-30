"""Real Chromium integration gate. Missing binary is a SKIP, never a pass.

Only local synthetic documents are served. Browser context routes reject
external origins; Chromium uses a local rejecting proxy and background network
features are disabled. These tests do not connect to the cloud browser.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import psutil
import pytest
from playwright.sync_api import sync_playwright
from app.pipeline.discovery_owner import DiscoveryOwner
from app.pipeline.lookup_outcome import strict_lookup, Outcome
from app.pipeline.page_owner import PageOwner

ROOT = Path(__file__).resolve().parents[1]
ARGS = ['--disable-background-networking', '--disable-component-update', '--disable-sync', '--no-first-run']

@pytest.fixture()
def local_pages():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith('http'):
                self.send_error(403); return  # rejecting HTTP proxy
            if self.path == '/slow': time.sleep(2)
            body=b'<html><body>synthetic planning document register</body></html>'
            self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers()
            try: self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError): pass
        def do_CONNECT(self): self.send_error(403)
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try: yield f'http://127.0.0.1:{server.server_port}'
    finally: server.shutdown();server.server_close();thread.join(timeout=3)

@pytest.fixture()
def browser_runtime():
    with sync_playwright() as p:
        if not Path(p.chromium.executable_path).is_file():
            pytest.skip('real Chromium binary unavailable; Gate A remains open')
        yield p

@pytest.fixture()
def browser_context(browser_runtime,local_pages):
    browser=browser_runtime.chromium.launch(headless=True,args=ARGS,
        proxy={'server':local_pages,'bypass':'127.0.0.1,localhost'})
    context=browser.new_context()
    def route(request):
        if request.request.url.startswith(local_pages+'/'): request.continue_()
        else: request.abort()
    context.route('**/*',route)
    try: yield context
    finally: context.close();browser.close()


def test_real_navigation_deadline_cleanup_then_subsequent_work(browser_context,local_pages,record_property):
    from app.pipeline.lookup_outcome import BoundedPage
    page=browser_context.new_page();start=time.monotonic()
    result=strict_lookup(lambda:BoundedPage(page).goto(local_pages+'/slow',timeout=5000),'OUT/1',seconds=.2)
    assert result.outcome==Outcome.TRANSIENT_FAILURE and result.reason=='logical_deadline'
    assert time.monotonic()-start < 1.5
    record_property('cooperative_cancellation_seconds', time.monotonic()-start)
    owner=PageOwner(page)
    owner.recycle()  # application cleanup, asserted before fixture teardown
    assert page.is_closed()
    next_page=owner.page
    def lookup():
        next_page.goto(local_pages+'/ready',timeout=3000)
        return SimpleNamespace(reference='OUT/1')
    assert strict_lookup(lookup,'OUT/1',seconds=2).outcome==Outcome.FOUND
    assert 'synthetic' in next_page.content()
    # The context-level egress rule must reject an external page too.
    with pytest.raises(Exception): next_page.goto('https://example.invalid/blocked',timeout=500)
    next_page.close()


def test_real_document_recycling_then_evidence_refresh(session,monkeypatch,browser_context,local_pages):
    from test_p0a_bounded_discovery import child,council
    from app.pipeline.run_weekly import stage_documents,stage_evidence_refresh
    from app.pipeline.acquisition_health import AcquisitionHealth
    a=child(session);a.summary_url=local_pages+'/documents'
    a.evidence_refresh_required=True;a.evidence_refresh_reason='decision_granted';a.evidence_refresh_trigger='material_change'
    session.commit();seen=[]
    def discover(page,*args,**kwargs):
        page.goto(local_pages+'/documents',timeout=3000)
        seen.append(page.page if isinstance(page,PageOwner) else page)
        return []  # synthetic empty register, no PDF or external portal
    monkeypatch.setattr('app.pipeline.run_weekly.discover_documents',discover)
    original=browser_context.new_page();owner=PageOwner(original);health=AcquisitionHealth()
    stage_documents(session,owner,council(),health=health)
    assert original.is_closed()
    stage_evidence_refresh(session,owner,council(),health=health)
    assert len(seen)==2 and seen[0] is not seen[1]
    assert health.evidence_refresh_failed==0
    owner.page.close()


WORKER = r'''
import json,os,sys,time,psutil
from playwright.sync_api import sync_playwright
from app.pipeline.discovery_owner import verify_child
verify_child()
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,args=['--disable-background-networking','--disable-component-update','--disable-sync'],proxy={'server':'http://127.0.0.1:9'})
 c=b.new_context();c.route('**/*',lambda r:r.abort())
 page=c.new_page();page.set_content('<html>synthetic browser descendant</html>')
 children=[{'pid':x.pid,'start':x.create_time()} for x in psutil.Process().children(recursive=True)]
 open(sys.argv[1],'w').write(json.dumps({'pid':os.getpid(),'children':children}))
 print('BROWSER_READY',flush=True)
 time.sleep(30)
'''


def assert_descendants_gone(records):
    end=time.monotonic()+5
    remaining=records
    while time.monotonic()<end:
        remaining=[]
        for record in records:
            try:
                p=psutil.Process(record['pid'])
                if p.create_time()==record['start']: remaining.append(record)
            except psutil.NoSuchProcess: pass
        if not remaining:return
        time.sleep(.05)
    pytest.fail(f'browser descendants still present, including zombies: {remaining}')


def test_real_browser_descendant_cleanup_on_supervised_failure(browser_runtime,tmp_path):
    from scripts.run_daily_councils import _run_council_subprocess
    ready=tmp_path/'browser.json';lock=str(tmp_path/'owner.lock')
    def stop(line):
        if line=='BROWSER_READY':raise RuntimeError('synthetic supervisor callback failure')
    with DiscoveryOwner(lock) as owner:
        with pytest.raises(RuntimeError,match='synthetic supervisor'):
            _run_council_subprocess([sys.executable,'-u','-c',WORKER,str(ready)],cwd=ROOT,
                timeout_seconds=15,on_line=stop,owner=owner,run_id=1)
    records=json.loads(ready.read_text())['children']
    assert records
    assert_descendants_gone(records)
    with DiscoveryOwner(lock):pass


def test_real_supervisor_death_with_browser_child(browser_runtime,tmp_path):
    ready=tmp_path/'browser.json';lock=str(tmp_path/'owner.lock')
    supervisor_code="""
import subprocess,sys,time
from app.pipeline.discovery_owner import DiscoveryOwner
with DiscoveryOwner(sys.argv[1]) as owner:
 p=subprocess.Popen([sys.executable,'-u','-c',sys.argv[3],sys.argv[2]],env=owner.child_environment(1),pass_fds=(owner.fd,),start_new_session=True)
 p.wait()
"""
    supervisor=subprocess.Popen([sys.executable,'-c',supervisor_code,lock,str(ready),WORKER],cwd=ROOT)
    child=None
    try:
        end=time.monotonic()+15
        while not ready.exists() and time.monotonic()<end:time.sleep(.05)
        assert ready.exists()
        child=json.loads(ready.read_text())
        supervisor.kill();supervisor.wait(timeout=3)
        with pytest.raises(RuntimeError,match='still active'):
            with DiscoveryOwner(lock):pass
        os.killpg(child['pid'],signal.SIGKILL)
        assert_descendants_gone(child['children'])
        with DiscoveryOwner(lock):pass
    finally:
        if supervisor.poll() is None:supervisor.kill();supervisor.wait(timeout=3)
        if child:
            try:os.killpg(child['pid'],signal.SIGKILL)
            except ProcessLookupError:pass


def test_real_browser_cleanup_when_persistence_blocks(browser_runtime,tmp_path,record_property):
    """Independent watchdog, real browser descendants and inherited owner lock."""
    ready=tmp_path/'browser.json';lock=str(tmp_path/'owner.lock')
    code='''import sys,time
from app.pipeline.discovery_owner import DiscoveryOwner
from app.pipeline.discovery_watchdog import DiscoveryWatchdog
from scripts.run_daily_councils import _run_council_subprocess
with DiscoveryWatchdog(time.monotonic()+8) as watchdog, DiscoveryOwner(sys.argv[1]) as owner:
 owner.watchdog=watchdog
 def persist(line):
  if line=='BROWSER_READY':time.sleep(60)
 _run_council_subprocess([sys.executable,'-u','-c',sys.argv[3],sys.argv[2]],cwd='.',timeout_seconds=20,on_line=persist,owner=owner,run_id=1)
'''
    started=time.monotonic()
    result=subprocess.run([sys.executable,'-c',code,lock,str(ready),WORKER],cwd=ROOT,
                          capture_output=True,text=True,timeout=15)
    assert result.returncode==-signal.SIGKILL
    record_property('supervisor_termination_seconds',time.monotonic()-started)
    assert 'final database status unverified' in result.stderr
    child=json.loads(ready.read_text())
    assert child['children']
    assert_descendants_gone(child['children'])
    with DiscoveryOwner(lock):pass
    elapsed=time.monotonic()-started
    record_property('termination_and_descendant_cleanup_seconds',elapsed)
    record_property('deadline_plus_margin_seconds',8+4)
    assert elapsed < 8 + 0 + 4  # hard invocation limit, no grace; startup/reaping margin
