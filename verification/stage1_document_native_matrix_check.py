"""Synthetic native packet listeners, no external network or credentials.

Positive controls are mandatory; no unsupported control becomes a passing gate.
IPv6 availability is reported explicitly. Native API failures cannot be success.
"""
import json,os,socket,sys,threading
from contextlib import contextmanager
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.security import document_browser as db,document_process as dp
OUT=Path(sys.argv[1]);OUT.mkdir(parents=True,exist_ok=True)
CHROME=sys.argv[2];os.environ['PROPERTYAIGENT_DOCUMENT_CHROMIUM']=CHROME
dp.EXTRA_BROWSER_ARGS=('--allow-loopback-in-peer-connection',)
records=[];reports=[];original=db.protected_browser
@contextmanager
def recorded(*args,**kwargs):
 status=None
 try:
  with original(*args,**kwargs) as value:status=value[1];yield value
 finally:
  if status is not None:reports.append(status())
db.protected_browser=recorded
script='''url=>{window.pc=new RTCPeerConnection({iceTransportPolicy:url.startsWith('turn:')?'relay':'all',iceServers:[{urls:url,username:'synthetic',credential:'synthetic'}]});pc.createDataChannel('fixture');pc.createOffer().then(o=>pc.setLocalDescription(o));}'''
try:
 for family,host in ((socket.AF_INET,'127.0.0.1'),(socket.AF_INET6,'::1')):
  for scheme,transport in (('turn','tcp'),('turn','udp'),('stun','udp')):
   case=f'{scheme}-{transport}-IPv{4 if family==socket.AF_INET else 6}'
   for protected in (False,True):
    packets=[];failure=None;listener=socket.socket(family,socket.SOCK_STREAM if transport=='tcp' else socket.SOCK_DGRAM)
    listener.bind((host,0));port=listener.getsockname()[1];listener.settimeout(4)
    if transport=='tcp':listener.listen()
    def receive():
     try:
      if transport=='tcp':connection,_=listener.accept();connection.close();packets.append('TCP')
      else:data,_=listener.recvfrom(65536);packets.append(len(data))
     except socket.timeout:pass
    thread=threading.Thread(target=receive);thread.start()
    try:
     with sync_playwright() as pw:
      browser=pw.chromium.launch(executable_path=CHROME,headless=True,args=['--no-sandbox','--disable-background-networking','--allow-loopback-in-peer-connection','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE ::1'])
      context=browser.new_context();base=context.new_page()
      address=f'[{host}]' if family==socket.AF_INET6 else host
      url=f'{scheme}:{address}:{port}'+(f'?transport={transport}' if scheme=='turn' else '')
      with requests.Session() as source:
       if protected:
        try:
         with db.document_page(base,source,[]) as (page,renderer):page.evaluate(script,url);page.wait_for_timeout(3500)
        except db.DocumentBrowserFailure as exc:failure=str(exc)
       else:base.evaluate(script,url);base.wait_for_timeout(3500)
      browser.close()
    finally:thread.join();listener.close()
    records.append(dict(case=case,protected=protected,packets=packets,failure=failure))
    print(case,protected,packets,failure,flush=True)
   assert records[-2]['packets'],f'{case}: unrestricted positive control failed'
   assert not records[-1]['packets'],f'{case}: renderer escaped'
   assert records[-1]['failure'],f'{case}: unsupported native attempt reported success'
   assert reports[-1]['notifications'] and reports[-1]['closed'],f'{case}: denial/cleanup not evidenced'
finally:
 (OUT/'result.json').write_text(json.dumps(dict(records=records,process_reports=reports),indent=2))
print('DONE native matrix')
