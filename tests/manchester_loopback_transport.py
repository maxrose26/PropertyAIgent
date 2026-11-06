"""Test-only Chromium transport substitution. All hosts except loopback are denied."""
def install(host,port):
 from playwright.async_api import async_playwright as real
 import playwright.async_api
 from types import SimpleNamespace
 class Wrapped:
  async def __aenter__(self):
   self.manager=real();self.pw=await self.manager.__aenter__();outer=self
   class Chromium:
    async def launch(self,**kw):
     kw['args']=[f'--host-resolver-rules=MAP {host} 127.0.0.1:{port}, MAP * ~NOTFOUND','--no-proxy-server']
     browser=await outer.pw.chromium.launch(**kw);original=browser.new_context
     async def context(**opts):
      opts['ignore_https_errors']=True
      return await original(**opts)
     browser.new_context=context;return browser
   return SimpleNamespace(chromium=Chromium())
  async def __aexit__(self,*a):return await self.manager.__aexit__(*a)
 playwright.async_api.async_playwright=Wrapped

def run(host,port,receipt):
 import json
 from pathlib import Path
 install(host,port)
 from verification.direct_reference.instrumented_probe import main
 try:return main()
 except Exception as error:
  allowed={'WORKER_AUDIT_BOUND','PROOF_OUTPUT_BOUND','PROOF_OBSERVATION_OUTPUT_BOUND','PROFILE_AUDIT_BINDING','PROOF_MISSING','EXISTING_OUTPUT'}
  Path(receipt).write_text(json.dumps(dict(exception_class=type(error).__name__,code=str(error) if str(error) in allowed else 'UNCLASSIFIED')))
  raise
