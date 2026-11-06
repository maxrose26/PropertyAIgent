"""Synthetic HTTP boundary for the real nested Idox worker. Never a live route."""
def child(count):
 import requests,socket,json
 from datetime import date
 from pathlib import Path
 from tests.e2e_connection_support import _Response,_idox_form,_idox_page,entry,SCHEME
 from verification.ingestion_storage.intake_scope_policy import BOLTON
 from verification.discovery import finite_acceptance
 start,end=date.fromisoformat(BOLTON.start),date.fromisoformat(BOLTON.end)
 entries=[entry(f'B/{i}/26',SCHEME) for i in range(count)]
 pages=[_idox_page('bolton',entries[i:i+10],start,end,first=i+1,total=count) for i in range(0,count,10)]
 bodies=iter([_idox_form('RECEIVED'),pages[0],pages[0],*pages[1:],_idox_form('RECEIVED','03/11/2026','05/11/2026')]);calls=[]
 def forbidden(*a,**kw):raise AssertionError('NETWORK_FORBIDDEN')
 socket.create_connection=forbidden;socket.socket.connect=forbidden
 def request(session,method,url,**kwargs):
  assert session.trust_env is False and session.get_adapter(url).max_retries.total==0
  assert url.startswith('https://paplanning.bolton.gov.uk/online-applications/') and len(calls)<10
  calls.append(method);return _Response(next(bodies))
 requests.Session.request=request
 finite_acceptance.main()

def worker(plan,output,count):
 import sys
 from types import SimpleNamespace
 from verification.discovery import finite_acceptance
 original=finite_acceptance.supervise
 def nested(argv,**kw):
  assert argv[1:3]==['-m','verification.discovery.finite_acceptance']
  command=[argv[0],'-c',f'from tests.bolton_worker_transport import child;child({count})',*argv[3:]]
  return original(command,**kw)
 finite_acceptance.supervise=nested
 from verification.ingestion_storage.daily_intake_runtime import source_worker
 source_worker(SimpleNamespace(plan=plan,output=output))
