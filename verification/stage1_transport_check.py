"""Actual local TLS fixture with external-only TCP mapping; no public traffic.

Production destination parsing, hostname verification, redirect and cookie code
run unchanged. Only validated public fixture IP -> disposable loopback socket
mapping and the 300-second deadline clock are instrumented, explicitly below.
"""
import datetime,json,socket,ssl,sys,tempfile,threading,time
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from urllib3.connection import HTTPSConnection
from app.security import outbound
import requests
OUT=Path(sys.argv[1]);OUT.mkdir(parents=True,exist_ok=True)
TMP=Path(tempfile.mkdtemp(prefix='stage1-tls-'));key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Synthetic council fixture')]);now=datetime.datetime.now(datetime.timezone.utc)
cert=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=1)).not_valid_after(now+datetime.timedelta(days=1)).add_extension(x509.SubjectAlternativeName([x509.DNSName('planning.bury.gov.uk'),x509.DNSName('planning.stockport.gov.uk')]),critical=False).add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True).sign(key,hashes.SHA256())
(TMP/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM));(TMP/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
seen=[];sni=[];results=[]
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  seen.append(dict(path=self.path,host=self.headers.get('Host'),cookie=self.headers.get('Cookie'),authorization=self.headers.get('Authorization')))
  if self.path=='/cookie':
   self.send_response(302);self.send_header('Location','/file');self.send_header('Set-Cookie','portal=fixture; Path=/; Secure');self.end_headers();return
  if self.path=='/cross':
   self.send_response(302);self.send_header('Location','https://planning.stockport.gov.uk/file');self.end_headers();return
  if self.path=='/private':
   self.send_response(302);self.send_header('Location','https://127.0.0.1/private');self.end_headers();return
  if self.path.startswith('/hop'):
   self.send_response(302);self.send_header('Location','/hop'+str(int(self.path[4:])+1));self.end_headers();return
  if self.path=='/slow':
   self.send_response(200);self.send_header('Content-Length','100');self.end_headers()
   try:
    for _ in range(100):self.wfile.write(b'x');self.wfile.flush();time.sleep(.03)
   except (BrokenPipeError,ConnectionResetError,ssl.SSLError):pass
   return
  body=b'%PDF-1.4 synthetic verified document';self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(TMP/'cert.pem',TMP/'key.pem');context.set_servername_callback(lambda sock,name,ctx:sni.append(name));server.socket=context.wrap_socket(server.socket,server_side=True);threading.Thread(target=server.serve_forever,daemon=True).start()
port=server.server_address[1];original_connect=socket.create_connection;original_timer=threading.Timer
# Guard every outbound socket even if a test fails to bind its transport.
def audit(event,args):
 if event=='socket.connect' and (not isinstance(args[1],tuple) or args[1][:2]!=('127.0.0.1',port)):raise RuntimeError('Forbidden fixture egress')
sys.addaudithook(audit)
def mapped_connection(self):
 assert self.host=='8.8.8.8' and self.port==443
 return original_connect(('127.0.0.1',port),timeout=2)
def record(name):results.append(dict(gate=name,result='PASS'));print('PASS',name,flush=True)
try:
 with patch.object(outbound,'resolved_addresses',lambda host,port:['8.8.8.8']),patch.object(HTTPSConnection,'_new_conn',mapped_connection):
  url='https://planning.bury.gov.uk'
  response=outbound.get(url+'/file',verify=str(TMP/'cert.pem'));assert response.content.startswith(b'%PDF');assert sni[-1]=='planning.bury.gov.uk' and seen[-1]['host']=='planning.bury.gov.uk';record('actual TLS SNI hostname Host and verified body')
  try:outbound.get(url+'/file')
  except requests.exceptions.SSLError:record('untrusted CA denied')
  else:raise AssertionError('untrusted CA accepted')
  try:outbound.get('https://pad-planning.bury.gov.uk/file',verify=str(TMP/'cert.pem'))
  except requests.exceptions.SSLError:record('wrong hostname denied')
  else:raise AssertionError('wrong hostname accepted')
  source=requests.Session();session=outbound.DocumentSession(source);session.get(url+'/cookie',verify=str(TMP/'cert.pem'));assert seen[-1]['cookie']=='portal=fixture' and source.cookies.get('portal')=='fixture';record('portal Set-Cookie round trip preserved')
  session.get(url+'/cross',verify=str(TMP/'cert.pem'),headers={'Authorization':'secret'});assert seen[-1]['host']=='planning.stockport.gov.uk' and seen[-1]['cookie'] is None and seen[-1]['authorization'] is None;record('cross-origin credentials stripped')
  count=len(seen)
  try:session.get(url+'/private',verify=str(TMP/'cert.pem'))
  except outbound.DestinationDenied:assert len(seen)==count+1;record('private redirect denied before dispatch')
  else:raise AssertionError('private redirect accepted')
  count=len(seen)
  try:session.get(url+'/hop0',verify=str(TMP/'cert.pem'))
  except outbound.DestinationDenied:assert len(seen)==count+6;record('redirect hop ceiling')
  else:raise AssertionError('redirect ceiling absent')
  scheduled=[]
  def accelerated_timer(seconds,callback):scheduled.append(seconds);return original_timer(.15,callback)
  start=time.monotonic()
  with patch.object(outbound.threading,'Timer',accelerated_timer):
   try:session.get(url+'/slow',verify=str(TMP/'cert.pem'),timeout=(2,2))
   except requests.RequestException:pass
   else:raise AssertionError('slow drip survived deadline')
  assert len(scheduled)==1 and 0<scheduled[0]<=300 and time.monotonic()-start<2;record('socket deadline interrupts slow drip (accelerated clock)')
finally:
 server.shutdown();server.server_close()
 (OUT/'result.json').write_text(json.dumps(dict(results=results,requests=seen,sni=sni,instrumentation='External public-IP-to-loopback TCP mapping; 300-second timer accelerated to 0.15 seconds only for slow-drip check. Synthetic CA explicitly supplied. No production calls.'),indent=2))
assert len(results)==8
print('DONE',OUT)
