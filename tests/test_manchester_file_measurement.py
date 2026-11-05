"""Disposable real Chromium, actual collector probe, synthetic DOM; no council HTTP."""
import asyncio,json,os,time,threading,tempfile
from pathlib import Path
import pytest

@pytest.mark.skipif(os.environ.get('MANCHESTER_REAL_BROWSER')!='1',reason='isolated hosted browser only')
def test_normal_collector_file_growth(monkeypatch,record_property):
 from playwright.async_api import async_playwright as real_playwright
 from verification.direct_reference import instrumented_probe as p
 from verification.discovery.arcus_ui_config import dated_config,MANCHESTER
 config=dated_config(MANCHESTER,'2026-10-27','2026-11-02')
 html='<button>Show the search criteria</button>'
 for label,value in {'Valid date from':'27/10/2026','Valid date to':'02/11/2026',**{k:'' for k in config.blank_inputs}}.items():
  html+=f'<label>{label}<input value="{value}"></label>'
 for label in config.blank_combos:html+=f'<div role="combobox" aria-label="{label}">Select an option</div>'
 html+='<div role="combobox" aria-label="Category">Planning Applications</div><p>No results found</p>'
 root=Path(tempfile.mkdtemp(prefix='mfiles-'));monkeypatch.setenv('TMPDIR',str(root));peak={};done=threading.Event();calls=[]
 def scan():
  while not done.is_set():
   for f in root.rglob('*'):
    try:
     if f.is_file():peak[f.name]=max(peak.get(f.name,0),f.stat().st_size)
    except OSError:pass
   done.wait(.005)
 t=threading.Thread(target=scan,daemon=True);t.start()
 class Wrapped:
  async def __aenter__(self):
   self.manager=real_playwright();self.pw=await self.manager.__aenter__()
   outer=self
   class Chromium:
    async def launch(self,**kw):
     kw['args']=['--host-resolver-rules=MAP * ~NOTFOUND']
     browser=await outer.pw.chromium.launch(**kw);original=browser.new_context
     async def context(**opts):
      c=await original(**opts)
      async def route(r):
       calls.append(r.request.url==config.destination)
       if r.request.url==config.destination:await r.fulfill(status=200,content_type='text/html',body=html)
       else:await r.abort()
      await c.route('**/*',route);return c
     browser.new_context=context;return browser
   from types import SimpleNamespace
   return SimpleNamespace(chromium=Chromium())
  async def __aexit__(self,*a):return await self.manager.__aexit__(*a)
 monkeypatch.setattr('playwright.async_api.async_playwright',Wrapped)
 try:a=asyncio.run(p.probe('discovery_manchester_ui_window',('2026-10-27','2026-11-02'),execution_budget='BROWSER_SOURCE_V2',deadline_origin=time.monotonic()))
 finally:done.set();t.join()
 report=dict(max_file_bytes=max(peak.values(),default=0),files=sorted(peak.items(),key=lambda x:x[1],reverse=True)[:12],failure=a['failure'],enumeration=a.get('enumeration_evidence'),cleanup=a['cleanup'],requests=a['requests'])
 print('MANCHESTER_FILE_MEASUREMENT '+json.dumps(report,sort_keys=True));record_property('file_measurement',json.dumps(report,sort_keys=True))
 assert a['cleanup']=='CONTEXT_BROWSER_CLOSED'
 assert a.get('enumeration_evidence')=='COUNT_RECONCILED',a
 assert calls==[True]
