"""Native-process layer tests, independent of the higher-level HTTP interceptor.

A fixed 24-byte synthetic page is supplied via the private CDP pipe. Both controls
have identical context options. No application guard is edited or disabled: this
exercises protected_browser directly to prove its filter survives native protocol
paths even without document_page's additional offline/HTTP interception defenses.
Application-level HTTP/WebSocket/worker behavior is tested separately by mechanisms.
"""
import json,os,socket,sys,threading
from contextlib import contextmanager
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.security import document_process as dp
OUT=Path(sys.argv[1]);OUT.mkdir(parents=True,exist_ok=True);CHROME=sys.argv[2]
os.environ['PROPERTYAIGENT_DOCUMENT_CHROMIUM']=CHROME
records=[]
@contextmanager
def plain(browser_type,directory):
 browser=browser_type.launch(executable_path=CHROME,args=['--no-sandbox','--disable-background-networking','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE ::1'])
 try:yield browser,None
 finally:browser.close()
try:
 for family,host in ((socket.AF_INET,'127.0.0.1'),(socket.AF_INET6,'::1')):
  for protocol in ('webtransport','websocket','http'):
   for protected in (False,True):
    packets=[];failure=None;status=None;report=None
    listener=socket.socket(family,socket.SOCK_DGRAM if protocol=='webtransport' else socket.SOCK_STREAM)
    listener.bind((host,0));port=listener.getsockname()[1];listener.settimeout(4)
    if protocol!='webtransport':listener.listen()
    def receive():
     try:
      if protocol=='webtransport':data,_=listener.recvfrom(65536);packets.append(len(data))
      else:peer,_=listener.accept();packets.append('TCP');peer.close()
     except socket.timeout:pass
    receiver=threading.Thread(target=receive);receiver.start()
    base='https://'+('['+host+']' if family==socket.AF_INET6 else host)+':'+str(port)
    directory=OUT/f'{family}-{protocol}-{protected}';directory.mkdir()
    try:
     with sync_playwright() as pw:
      try:
       with (dp.protected_browser if protected else plain)(pw.chromium,directory) as (browser,status):
        context=browser.new_context(service_workers='block')
        context.route(base+'/fixture',lambda route:route.fulfill(body='<p>synthetic fixture</p>',content_type='text/html'))
        page=context.new_page();page.goto(base+'/fixture')
        if protocol=='webtransport':
         assert page.evaluate('typeof WebTransport')=='function'
         page.evaluate('url=>{window.transport=new WebTransport(url);transport.ready.catch(()=>{});transport.closed.catch(()=>{})}',base+'/transport')
        elif protocol=='websocket':page.evaluate('url=>{window.ws=new WebSocket(url)}',base.replace('https:','wss:')+'/socket')
        else:page.evaluate('url=>{fetch(url).catch(()=>{})}',base+'/network')
        page.wait_for_timeout(3000)
        context.close()
      except dp.ContainmentError as exc:failure=str(exc)
      finally:
       if status is not None:report=status()
    finally:receiver.join();listener.close()
    records.append(dict(protocol=protocol,family=family,protected=protected,packets=packets,failure=failure,process_report=report));print(records[-1],flush=True)
   assert records[-2]['packets'],'Unrestricted native positive control failed'
   assert not records[-1]['packets'],'Native renderer traffic escaped'
   assert records[-1]['failure'],'Unsupported native transport reported success'
   assert report['notifications']>0 and report['closed']
finally:(OUT/'result.json').write_text(json.dumps(dict(records=records),indent=2))
print('DONE native extra')
