"""Disposable real Chromium, actual collector probe, synthetic DOM; no council HTTP."""
import asyncio,json,os,time,threading,tempfile,subprocess,sys,resource,ssl,http.server,hashlib
from dataclasses import replace
from pathlib import Path
import pytest

@pytest.mark.skipif(os.environ.get('MANCHESTER_REAL_BROWSER')!='1',reason='isolated hosted browser only')
def test_normal_collector_file_growth(monkeypatch,record_property):
 if 'MEASURE_FILE_LIMIT' not in os.environ:
  reports=[]
  for limit in (524288,1048576,2097152,4194304,8388608,16777216,20971520):
   result=subprocess.run([sys.executable,'-m','pytest',__file__,'-q','-s','--tb=short'],env=dict(os.environ,MEASURE_FILE_LIMIT=str(limit)),capture_output=True,text=True,timeout=45)
   lines=[x.split('MANCHESTER_FILE_MEASUREMENT ',1)[1] for x in result.stdout.splitlines() if 'MANCHESTER_FILE_MEASUREMENT ' in x]
   assert result.returncode==0 and len(lines)==1,(result.returncode,result.stdout[-4000:])
   report=json.loads(lines[0]);reports.append(report)
  actual=subprocess.run([sys.executable,'-m','pytest',__file__,'-q','-s','--tb=short'],env=dict(os.environ,MEASURE_FILE_LIMIT='2097152',MEASURE_ACTUAL_WORKER='1'),capture_output=True,text=True,timeout=45)
  lines=[x.split('MANCHESTER_FILE_MEASUREMENT ',1)[1] for x in actual.stdout.splitlines() if 'MANCHESTER_FILE_MEASUREMENT ' in x]
  assert actual.returncode==0 and len(lines)==1,actual.stdout[-4000:]
  actual_report=json.loads(lines[0]);assert actual_report['enumeration']=='COUNT_RECONCILED' and actual_report['records']==60
  reports.append(actual_report)
  print('MANCHESTER_FILE_LIMIT_COMPARISON '+json.dumps(reports,sort_keys=True))
  record_property('file_measurements',json.dumps(reports,sort_keys=True))
  assert any(r['enumeration']=='COUNT_RECONCILED' for r in reports)
  return
 limit=int(os.environ['MEASURE_FILE_LIMIT']);resource.setrlimit(resource.RLIMIT_FSIZE,(limit,limit))
 from playwright.async_api import async_playwright as real_playwright
 from verification.direct_reference import instrumented_probe as p
 from verification.discovery.arcus_ui_config import dated_config,MANCHESTER
 # A loopback TLS server exercises Chromium's real network service. Only the
 # fixture DNS resolution differs; collector parsing, CDP guards and cleanup are real.
 root=Path(tempfile.mkdtemp(prefix='mfiles-'))
 key=root/'key.pem';cert=root/'cert.pem'
 subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=localhost'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 class Handler(http.server.BaseHTTPRequestHandler):
  def do_GET(self):
   calls.append(self.path)
   self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(html.encode())
  def log_message(self,*args):pass
 server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
 tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(cert,key);server.socket=tls.wrap_socket(server.socket,server_side=True)
 server_thread=threading.Thread(target=server.serve_forever,daemon=True);server_thread.start()
 from urllib.parse import urlsplit,urlunsplit
 original=dated_config(MANCHESTER,'2026-10-27','2026-11-02');url=urlsplit(original.destination)
 config=replace(original,capture_metadata=True,assessment_metadata=True)
 monkeypatch.setitem(p.UI_CASES,'discovery_manchester_ui_window',config)
 html='<button>Show the search criteria</button>'
 for label,value in {'Valid date from':'27/10/2026','Valid date to':'02/11/2026',**{k:'' for k in config.blank_inputs}}.items():
  html+=f'<label>{label}<input value="{value}"></label>'
 for label in config.blank_combos:html+=f'<div role="combobox" aria-label="{label}">Select an option</div>'
 html+='<div role="combobox" aria-label="Category">Planning Applications</div><p class="pr-pagination__results"></p><section id="rows"></section><a class="pr-pagination__link" href="#" onclick="event.preventDefault();page++;render()">Next</a>'
 html+='''<script>let page=0;function render(){let first=page*10+1,last=first+9;document.querySelector('p').textContent=`Showing ${first} to ${last} of 60 results`;let out='';for(let n=first;n<=last;n++){out+=`<div role="list" class="slds-box"><a href="/pr/s/detail/${String(n).padStart(18,'0')}?c__r=Arcus_BE_Public_Register">M/${n}</a><div role="listitem">Reference<br>M/${n}</div><div role="listitem">Valid Date<br>28/10/2026</div><div role="listitem">Proposal<br>Erection of 12 dwellings</div><div role="listitem">Site Address<br>Fixture site ${n}</div><div role="listitem">Application type<br>Full</div></div>`}document.querySelector('#rows').innerHTML=out;if(page===5)document.querySelector('a.pr-pagination__link').remove()}render()</script>'''
 monkeypatch.setenv('TMPDIR',str(root));monkeypatch.setenv('HOME',str(root));peak={};done=threading.Event();calls=[];seen={};peak_rss=[0]
 def scan():
  while not done.is_set():
   for f in root.rglob('*'):
    try:
     if f.is_file():peak[f.name]=max(peak.get(f.name,0),f.stat().st_size)
    except OSError:pass
   import psutil
   children=psutil.Process().children(recursive=True);rss=0
   for process in children:
    try:
     seen[process.pid]=process.create_time();rss+=process.memory_info().rss
     for fd in Path('/proc',str(process.pid),'fd').iterdir():
      try:
       name=os.readlink(fd);size=fd.stat().st_size
       # Exclude immutable browser resources opened read-only.
       flags=int(next(x.split()[1] for x in Path('/proc',str(process.pid),'fdinfo',fd.name).read_text().splitlines() if x.startswith('flags:')),8)
       if flags & os.O_ACCMODE == os.O_RDONLY:continue
       if size and ('memfd:' in name or '/tmp/' in name or '/dev/shm/' in name):
        key='memfd' if 'memfd:' in name else 'deleted_file' if '(deleted)' in name else Path(name).name
        peak[key]=max(peak.get(key,0),size)
      except OSError:pass
    except (OSError,psutil.Error):pass
   peak_rss[0]=max(peak_rss[0],rss)
   done.wait(.002)
 t=threading.Thread(target=scan,daemon=True);t.start()
 class Wrapped:
  async def __aenter__(self):
   self.manager=real_playwright();self.pw=await self.manager.__aenter__()
   outer=self
   class Chromium:
    async def launch(self,**kw):
     kw['args']=[f'--host-resolver-rules=MAP {url.hostname} 127.0.0.1:{server.server_port}, MAP * ~NOTFOUND','--no-proxy-server']
     browser=await outer.pw.chromium.launch(**kw);original=browser.new_context
     async def context(**opts):
      opts['ignore_https_errors']=True
      return await original(**opts)
     browser.new_context=context;return browser
   from types import SimpleNamespace
   return SimpleNamespace(chromium=Chromium())
  async def __aexit__(self,*a):return await self.manager.__aexit__(*a)
 monkeypatch.setattr('playwright.async_api.async_playwright',Wrapped)
 try:
  def read_probe():return asyncio.run(p.probe('discovery_manchester_ui_window',('2026-10-27','2026-11-02'),execution_budget='BROWSER_SOURCE_V2',deadline_origin=time.monotonic()))
  if os.environ.get('MEASURE_ACTUAL_WORKER')=='1':
   # Exact production worker file selection; only provider execution is redirected
   # to the same real loopback Chromium probe measured above.
   for name in list(os.environ):
    if 'DATABASE' in name or name.endswith(('_KEY','_TOKEN','_PASSWORD')):monkeypatch.delenv(name)
   monkeypatch.setenv('INGESTION_SOURCE_PRIVATE','ONCE')
   from verification.ingestion_storage.daily_intake_runtime import source_worker
   row=dict(council='manchester',semantics='VALIDATED',start='2026-10-27',end='2026-11-02')
   def reader(actual_row,**opts):
    assert actual_row==row and opts['no_transport_retry'] is True and opts['execution_budget']=='BROWSER_SOURCE_V2'
    assert resource.getrlimit(resource.RLIMIT_FSIZE)==(2097152,2097152)
    return read_probe()
   monkeypatch.setattr('verification.discovery.finite_acceptance.read',reader)
   plan=root/'plan';out=root/'source.json';plan.write_text(json.dumps(dict(row=row,fixture=None,file_profile='MANCHESTER_PERIOD09_V1')))
   from types import SimpleNamespace
   source_worker(SimpleNamespace(plan=plan,output=out));a=json.loads(out.read_text())
   assert out.stat().st_size<=524288
  else:a=read_probe()
 finally:done.set();t.join();server.shutdown();server.server_close();server_thread.join()
 import psutil
 survivors=[]
 for pid,born in seen.items():
  try:
   child=psutil.Process(pid)
   if child.create_time()==born and child.status()!=psutil.STATUS_ZOMBIE:survivors.append(pid)
  except psutil.NoSuchProcess:pass
 from verification.direct_reference.prepared_font_cache import headless_shell_executable
 browser_sha=hashlib.sha256(Path(headless_shell_executable(os.environ['PLAYWRIGHT_BROWSERS_PATH'])).read_bytes()).hexdigest()
 report=dict(browser_sha256=browser_sha,peak_owned_rss=peak_rss[0],live_owned_survivors=len(survivors),actual_worker=os.environ.get('MEASURE_ACTUAL_WORKER')=='1',file_limit=limit,max_file_bytes=max(peak.values(),default=0),files=sorted(peak.items(),key=lambda x:x[1],reverse=True)[:12],failure=a['failure'],enumeration=a.get('enumeration_evidence'),cleanup=a['cleanup'],requests=a['requests'],records=len(a.get('listing_records',[])),physical_requests=len(calls))
 print('MANCHESTER_FILE_MEASUREMENT '+json.dumps(report,sort_keys=True));record_property('file_measurement',json.dumps(report,sort_keys=True))
 assert a['cleanup']=='CONTEXT_BROWSER_CLOSED' and not survivors
 assert peak_rss[0]<=1024*1024*1024
 assert a.get('enumeration_evidence')=='COUNT_RECONCILED' or a.get('safety_failure') is True,a
 assert len(calls)<=1
 if a.get('enumeration_evidence')=='COUNT_RECONCILED':assert len(a['listing_records'])==60
