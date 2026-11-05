"""Actual source-worker and diagnostic request gate, with no council transport."""
import json, socket
from types import SimpleNamespace
import pytest
from playwright.async_api import Error, TimeoutError
from verification.discovery import manchester_navigation_diagnostic as d
from verification.ingestion_storage.daily_intake_runtime import source_worker

@pytest.mark.parametrize('scenario', ['ok','redirect','subresources','repeat','dns','timeout','cleanup','response_before_cdp'])
def test_worker_transport_gate(tmp_path,monkeypatch,scenario):
 handlers={};calls=[];closed=[];options=[]
 class Client:
  def on(self,k,f):handlers[k]=f
  async def send(self,k,args=None):calls.append((k,args))
 class Page:
  async def goto(self,url,**kw):
   assert url==d.DESTINATION and kw==dict(wait_until='commit',timeout=25000)
   event=dict(requestId='TOKEN_PRIVATE',resourceType='Document',request=dict(url=url,method='GET'))
   await handlers['Fetch.requestPaused'](event)
   if scenario in ('dns','timeout'):
    raise (Error('net::ERR_NAME_NOT_RESOLVED SECRET_COOKIE') if scenario=='dns' else TimeoutError('SECRET_COOKIE'))
   if scenario in ('redirect','subresources','repeat'):
    event.update(requestId='SECRET_SECOND')
    if scenario=='redirect':event.update(redirectedRequestId='TOKEN_PRIVATE')
    if scenario=='subresources':event.update(resourceType='Script')
    await handlers['Fetch.requestPaused'](event)
   if scenario=='response_before_cdp':return SimpleNamespace(status=200)
   handlers['Network.responseReceived'](dict(type='Document',response=dict(status=302 if scenario=='redirect' else 200)))
 class Context:
  async def route_web_socket(self,*a):pass
  async def new_page(self):return Page()
  async def new_cdp_session(self,p):return Client()
  async def close(self):
   closed.append('context')
   if scenario=='cleanup':raise Error('SECRET_COOKIE')
 class Browser:
  async def new_context(self,**kw):options.append(kw);return Context()
  async def close(self):closed.append('browser')
 class PW:
  async def __aenter__(self):return SimpleNamespace(chromium=self)
  async def __aexit__(self,*a):pass
  async def launch(self,**kw):return Browser()
 monkeypatch.setattr('playwright.async_api.async_playwright',PW)
 monkeypatch.setattr(socket.socket,'connect',lambda *a:pytest.fail('LIVE_NETWORK_FORBIDDEN'))
 monkeypatch.setattr('resource.setrlimit',lambda *a:None)
 for k in list(__import__('os').environ):
  if 'DATABASE' in k or k.endswith(('_KEY','_TOKEN','_PASSWORD')):monkeypatch.delenv(k)
 monkeypatch.setenv('INGESTION_SOURCE_PRIVATE','ONCE')
 plan=tmp_path/'plan.json';out=tmp_path/'out.json'
 plan.write_text(json.dumps(dict(row=d.ROW,fixture=None,diagnostic_mode=d.MODE)))
 source_worker(SimpleNamespace(plan=str(plan),output=str(out)))
 result=json.loads(out.read_text())
 assert result['physical_requests']==1 and result['retries']==0
 assert sum(k=='Fetch.continueRequest' for k,a in calls)==1
 assert closed==['context','browser'] and options==[dict(service_workers='block',accept_downloads=False)]
 assert result['coverage']=='NOT_ESTABLISHED'
 assert not any(x in json.dumps(result) for x in ['SECRET','TOKEN','https://'])
 if scenario in ('redirect','subresources','repeat'):
  assert result['blocked_requests']==1 and sum(k=='Fetch.failRequest' for k,a in calls)==1
 if scenario=='response_before_cdp':assert result['responses']==1 and result['http_status']==200
 if scenario=='dns':assert result['network_error']=='ERR_NAME_NOT_RESOLVED' and result['responses']==0
 if scenario=='timeout':assert result['exception_class']=='TimeoutError' and result['responses']==0
 assert result['cleanup']==('UNVERIFIED' if scenario=='cleanup' else 'CONTEXT_BROWSER_CLOSED')

@pytest.mark.parametrize('change',[{'council':'tameside'},{'start':'2026-10-26'},{'semantics':'RECEIVED'}])
def test_fixed_scope_refuses(tmp_path,monkeypatch,change):
 for k in list(__import__('os').environ):
  if 'DATABASE' in k or k.endswith(('_KEY','_TOKEN','_PASSWORD')):monkeypatch.delenv(k)
 monkeypatch.setenv('INGESTION_SOURCE_PRIVATE','ONCE');monkeypatch.setattr('resource.setrlimit',lambda *a:None)
 monkeypatch.setattr(d,'live',lambda:pytest.fail('TRANSPORT_REACHED'))
 p=tmp_path/'plan';p.write_text(json.dumps(dict(row={**d.ROW,**change},fixture=None,diagnostic_mode=d.MODE)))
 with pytest.raises(Exception,match='DIAGNOSTIC_SCOPE'):source_worker(SimpleNamespace(plan=p,output=tmp_path/'out'))

@pytest.mark.skipif(__import__('os').environ.get('MANCHESTER_REAL_BROWSER')!='1',reason='explicit isolated browser runtime required')
@pytest.mark.parametrize('response',['normal','redirect','disconnect'])
def test_real_chromium_local_transport_only(monkeypatch,response):
 import asyncio,threading
 from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
 calls=[]
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def do_GET(self):
   calls.append(self.path)
   if response=='disconnect':self.connection.close();return
   self.send_response(302 if response=='redirect' else 200)
   if response=='redirect':self.send_header('Location','/next')
   self.send_header('Content-Type','text/html');self.end_headers()
   try:self.wfile.write(b'<script src="/script"></script><img src="/image"><iframe src="/frame"></iframe>')
   except (BrokenPipeError,ConnectionResetError):pass
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
 thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 monkeypatch.setattr(d,'DESTINATION',f'http://127.0.0.1:{server.server_port}/initial')
 try:result=asyncio.run(d.observe())
 finally:server.shutdown();server.server_close();thread.join()
 assert calls==['/initial'],(calls,result)
 assert result['physical_requests']==1 and result['cleanup']=='CONTEXT_BROWSER_CLOSED'
 if response=='normal':assert result['responses']==1 and result['http_status']==200

@pytest.mark.parametrize('env,seconds',[
 ({'INGESTION_SOURCE_PRIVATE':'ONCE','PLAYWRIGHT_BROWSERS_PATH':'/wrong'},45),
 ({'INGESTION_SOURCE_PRIVATE':'ONCE','PLAYWRIGHT_BROWSERS_PATH':'/tmp/propertyaigent-manchester-diagnostic-browser','DATABASE_URL':'SECRET'},45),
 ({'INGESTION_SOURCE_PRIVATE':'ONCE','PLAYWRIGHT_BROWSERS_PATH':'/tmp/propertyaigent-manchester-diagnostic-browser'},46)])
def test_supervisor_refuses_changed_envelope_before_launch(tmp_path,monkeypatch,env,seconds):
 from verification.ingestion_storage.operational_supervisor import supervise
 monkeypatch.setattr('subprocess.Popen',lambda *a,**k:pytest.fail('LAUNCH_REACHED'))
 with pytest.raises(ValueError,match='DIAGNOSTIC'):
  supervise(['never'],environment=env,root=tmp_path/'owned',source=True,seconds=seconds,diagnostic_mode=d.MODE)

def test_supervisor_actual_child_environment_and_cleanup(tmp_path):
 import sys,tempfile
 tmp_path=__import__('pathlib').Path(tempfile.mkdtemp(prefix='mnav-test-'))
 from verification.ingestion_storage.operational_supervisor import supervise
 result=supervise([sys.executable,'-c',"import os;assert set(os.environ)<={'PATH','HOME','TMPDIR','LANG','PYTHONNOUSERSITE','PYTHONDONTWRITEBYTECODE','OPENBLAS_NUM_THREADS','INGESTION_SOURCE_PRIVATE','PLAYWRIGHT_BROWSERS_PATH','LC_CTYPE'}"],
  environment={'INGESTION_SOURCE_PRIVATE':'ONCE','PLAYWRIGHT_BROWSERS_PATH':'/tmp/propertyaigent-manchester-diagnostic-browser'},root=tmp_path/'owned',source=True,seconds=45,diagnostic_mode=d.MODE)
 assert result['exit_code']==0 and result['cleanup']=='CLOSED' and result['live_owned_survivors']==0 and result['retry'] is False, result

@pytest.mark.skipif(__import__('os').environ.get('MANCHESTER_REAL_BROWSER')!='1',reason='explicit isolated browser runtime required')
def test_actual_supervised_worker_45_second_envelope(tmp_path):
 import sys,threading,tempfile
 owned_root=__import__('pathlib').Path(tempfile.mkdtemp(prefix='mnav-test-'))/'owned'
 from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
 from verification.ingestion_storage.operational_supervisor import supervise
 calls=[]
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*a):pass
  def do_GET(self):
   calls.append(self.path);self.send_response(200);self.end_headers()
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
 thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 plan=tmp_path/'plan';out=tmp_path/'out'
 plan.write_text(json.dumps(dict(row=d.ROW,fixture=None,diagnostic_mode=d.MODE)))
 code=f"from verification.discovery import manchester_navigation_diagnostic as d;d.DESTINATION='http://127.0.0.1:{server.server_port}/initial';from verification.ingestion_storage.daily_intake_runtime import source_worker;from types import SimpleNamespace;source_worker(SimpleNamespace(plan={str(plan)!r},output={str(out)!r}))"
 try:
  result=supervise([sys.executable,'-B','-c',code],environment={'INGESTION_SOURCE_PRIVATE':'ONCE','PLAYWRIGHT_BROWSERS_PATH':'/tmp/propertyaigent-manchester-diagnostic-browser'},root=owned_root,source=True,seconds=45,diagnostic_mode=d.MODE)
 finally:server.shutdown();server.server_close();thread.join()
 assert result['exit_code']==0 and result['cleanup']=='CLOSED' and result['accounting_complete'] and result['live_owned_survivors']==0,result
 obs=json.loads(out.read_text())
 assert calls==['/initial'] and obs['physical_requests']==1 and obs['responses']==1 and obs['cleanup']=='CONTEXT_BROWSER_CLOSED',obs
 assert result['elapsed_seconds']<45


def test_long_browser_temp_path_refused_before_launch(tmp_path,monkeypatch):
 from verification.ingestion_storage.operational_supervisor import supervise
 monkeypatch.setattr('subprocess.Popen',lambda *a,**k:pytest.fail('LAUNCH_REACHED'))
 with pytest.raises(ValueError,match='DIAGNOSTIC_TEMP_PATH_BOUND'):
  supervise(['never'],environment={'INGESTION_SOURCE_PRIVATE':'ONCE','PLAYWRIGHT_BROWSERS_PATH':'/tmp/propertyaigent-manchester-diagnostic-browser'},root='/tmp/'+'x'*60,source=True,seconds=45,diagnostic_mode=d.MODE)
