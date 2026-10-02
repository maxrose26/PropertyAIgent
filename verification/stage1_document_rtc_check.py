"""Two synthetic Chromium peers; positive data delivery versus document denial."""
import json,os,sys,socket,struct,threading
from contextlib import contextmanager
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.security import document_browser as db,document_process as dp
OUT=Path(sys.argv[1]);OUT.mkdir(parents=True,exist_ok=True);CHROME=sys.argv[2]
os.environ['PROPERTYAIGENT_DOCUMENT_CHROMIUM']=CHROME
dp.EXTRA_BROWSER_ARGS=('--allow-loopback-in-peer-connection','--disable-features=WebRtcHideLocalIpsWithMdns')
stun=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);stun.bind(('127.0.0.1',0));stun.settimeout(.1);stun_stop=threading.Event();stun_packets=[]
def serve_stun():
 while not stun_stop.is_set():
  try:data,address=stun.recvfrom(65536)
  except socket.timeout:continue
  if len(data)<20 or data[:2]!=b'\x00\x01' or data[4:8]!=b'\x21\x12\xa4\x42':continue
  stun_packets.append('binding')
  mapped=b'\x00\x01'+struct.pack('!H',address[1]^0x2112)+bytes(a^b for a,b in zip(socket.inet_aton(address[0]),b'\x21\x12\xa4\x42'))
  attribute=struct.pack('!HH',0x20,len(mapped))+mapped
  stun.sendto(struct.pack('!HHI',0x101,len(attribute),0x2112a442)+data[8:20]+attribute,address)
stun_thread=threading.Thread(target=serve_stun);stun_thread.start()
records=[];reports=[];original=db.protected_browser
@contextmanager
def recorded(*args,**kwargs):
 status=None
 try:
  with original(*args,**kwargs) as value:status=value[1];yield value
 finally:
  if status is not None:reports.append(status())
db.protected_browser=recorded
setup='''()=>{window.pc=new RTCPeerConnection({iceServers:[]});window.received=[];window.candidates=[];pc.onicecandidate=e=>{if(e.candidate)candidates.push(e.candidate.toJSON())};pc.ondatachannel=e=>{e.channel.onmessage=m=>received.push(m.data)};window.gather=()=>new Promise((resolve,reject)=>{if(pc.iceGatheringState==='complete')return resolve();pc.onicegatheringstatechange=()=>{if(pc.iceGatheringState==='complete')resolve()};setTimeout(()=>reject(Error('ICE gathering fixture timeout')),5000)})}'''
setup=setup.replace('iceServers:[]','iceServers:[{urls:"stun:127.0.0.1:'+str(stun.getsockname()[1])+'"}]')
offer='''async()=>{window.channel=pc.createDataChannel('synthetic');channel.onopen=()=>channel.send('synthetic-contained-message');await pc.setLocalDescription(await pc.createOffer());return pc.localDescription.toJSON()}'''
answer='''async offer=>{await pc.setRemoteDescription(offer);await pc.setLocalDescription(await pc.createAnswer());return pc.localDescription.toJSON()}'''
try:
 for protected in (False,True):
  failure=None;received=[]
  with sync_playwright() as pw:
   browser=pw.chromium.launch(executable_path=CHROME,args=['--no-sandbox','--disable-background-networking','--allow-loopback-in-peer-connection','--disable-features=WebRtcHideLocalIpsWithMdns','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE ::1'])
   context=browser.new_context(permissions=['local-network-access']);context.route('https://rtc.invalid/fixture',lambda route:route.fulfill(body='<p>RTC fixture</p>',content_type='text/html'));base=context.new_page();receiver=context.new_page();base.goto('https://rtc.invalid/fixture');receiver.goto('https://rtc.invalid/fixture');receiver.evaluate(setup)
   def exchange(sender):
    sender.context.grant_permissions(['local-network-access'])
    sender.evaluate(setup);description=sender.evaluate(offer);reply=receiver.evaluate(answer,description);sender.evaluate('answer=>pc.setRemoteDescription(answer)',reply)
    for _ in range(50):
     for candidate in sender.evaluate('candidates.splice(0)'):receiver.evaluate('c=>pc.addIceCandidate(c)',candidate)
     for candidate in receiver.evaluate('candidates.splice(0)'):sender.evaluate('c=>pc.addIceCandidate(c)',candidate)
     if receiver.evaluate('received.length'):break
     receiver.wait_for_timeout(100)
    if receiver.evaluate('received.length')!=1:
     for peer in (sender,receiver):print(peer.evaluate("({gathering:pc.iceGatheringState,connection:pc.connectionState,candidates:pc.localDescription.sdp.split('\\r\\n').filter(l=>l.startsWith('a=candidate'))})"),flush=True)
    assert receiver.evaluate('received.length')==1,'Direct synthetic RTC delivery failed'
   with requests.Session() as source:
    if protected:
     try:
      directory=OUT/'renderer';directory.mkdir()
      with recorded(pw.chromium,directory) as (protected_browser,status):
       protected_context=protected_browser.new_context(permissions=['local-network-access'],service_workers='block')
       protected_context.route('https://rtc.invalid/fixture',lambda route:route.fulfill(body='<p>RTC fixture</p>',content_type='text/html'))
       page=protected_context.new_page();page.goto('https://rtc.invalid/fixture');exchange(page)
     except dp.ContainmentError as exc:failure=str(exc)
    else:exchange(base)
    received=receiver.evaluate('received')
   browser.close()
  records.append(dict(protected=protected,received=received,failure=failure));print(records[-1],flush=True)
 assert records[0]['received']==['synthetic-contained-message']
 assert not records[1]['received'] and records[1]['failure']
 assert reports[-1]['notifications']>0 and reports[-1]['closed']
finally:
 stun_stop.set();stun_thread.join();stun.close()
 (OUT/'result.json').write_text(json.dumps(dict(records=records,process_reports=reports,synthetic_stun_bindings=len(stun_packets)),indent=2))
print('DONE direct RTC')
