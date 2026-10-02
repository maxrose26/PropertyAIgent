"""Real Chromium + synthetic council/CDN TLS. External TCP mapping only; no public calls."""
import os
from contextlib import contextmanager
import datetime,json,socket,ssl,sys,tempfile,threading,time,hashlib,resource
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from urllib3.connection import HTTPSConnection
from playwright.sync_api import sync_playwright
from app.security import outbound,document_browser as db
from app.scrapers.documents import get_anite_documents,get_arcus_documents
import requests
import faulthandler
faulthandler.dump_traceback_later(30,repeat=True)
OUT=Path(sys.argv[1]);OUT.mkdir(parents=True,exist_ok=True)
CHROME=sys.argv[2];os.environ['PROPERTYAIGENT_DOCUMENT_CHROMIUM']=CHROME;TMP=tempfile.TemporaryDirectory(prefix='stage1-document-tls-');tmp=Path(TMP.name)
key=rsa.generate_private_key(public_exponent=65537,key_size=2048);name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Synthetic document fixtures')]);now=datetime.datetime.now(datetime.timezone.utc)
HOST='planning.bury.gov.uk';ARC='salfordcitycouncil.my.site.com';CDN='live-iag-static-assets.s3.eu-west-1.amazonaws.com';BASE='https://'+HOST
cert=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=1)).not_valid_after(now+datetime.timedelta(days=1)).add_extension(x509.SubjectAlternativeName([x509.DNSName(h) for h in (HOST,ARC,CDN)]),critical=False).add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True).sign(key,hashes.SHA256())
(tmp/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM));(tmp/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
seen=[];outcomes=[];process_reports=[]
original_process=db.protected_browser
@contextmanager
def recorded_process(*args,**kwargs):
 status=None
 try:
  with original_process(*args,**kwargs) as value:
   status=value[1];yield value
 finally:
  if status is not None:process_reports.append(status())
db.protected_browser=recorded_process
def row(name,url):
 return '<tr>'+''.join('<td class="dataTableColumnPadding">'+s+'</td>' for s in ('Planning Statement','','','',name,'.pdf'))+f'<td><a class="viewDocument" href="{url}">Download</a></td></tr>'
def table(page=1):
 return '<table id="searchResult"><tbody>'+row('Planning statement '+str(page),'/binary'+str(page))+'</tbody></table>'+ ('<a id="searchResult_next" href="/listing2">Next</a>' if page==1 else '<a id="searchResult_next" class="disabled">Next</a>')
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):
  seen.append(dict(path=self.path,host=self.headers.get('Host'),cookie=self.headers.get('Cookie')))
  status=200;headers={'Content-Type':'text/html'}
  if 'activeTab=externalDocuments' in self.path:body=b'<a href="/listing">View associated documents</a>'
  elif self.path=='/listing':body=table().encode();headers['Set-Cookie']='portal=updated; Secure; Path=/'
  elif self.path=='/listing2':body=table(2).encode()
  elif self.path.startswith('/binary'):body=b'%PDF-1.4 verified '+self.path.encode();headers.update({'Content-Type':'application/pdf','Content-Disposition':'attachment; filename="file.pdf"'})
  elif self.path=='/redirect':status=302;headers['Location']='/base/page';body=b''
  elif self.path=='/base/page':body=b'<img src="asset"><a href="child">relative</a>'
  elif self.path=='/base/asset':body=b'GIF89a';headers['Content-Type']='image/gif'
  elif self.path=='/private':status=302;headers['Location']='https://127.0.0.1/denied';body=b''
  elif self.path.startswith('/hop'):status=302;headers['Location']='/hop'+str(int(self.path[4:])+1);body=b''
  elif self.path=='/ws':body=b'<script>new WebSocket("wss://planning.bury.gov.uk/socket")</script>'
  elif self.path=='/popup':body=b'<script>window.open("https://planning.bury.gov.uk/popped")</script>'
  elif self.path=='/cookie-delete':body=b'<body>deleted</body>';headers['Set-Cookie']='parent=; Max-Age=0; Secure; HttpOnly; SameSite=Strict; Path=/'
  elif self.path=='/cookie-flags':body=b'<body>flags</body>';headers['Set-Cookie']='parent=updated; Secure; HttpOnly; SameSite=Strict; Path=/'
  elif self.path=='/same-frame':body=b'<iframe src="/fixture"></iframe>'
  elif self.path=='/worker':body=b'<script>try{new Worker("/worker.js")}catch(e){};navigator.serviceWorker.register("/sw.js").catch(()=>{})</script>'
  elif self.path=='/frame':body=b'<iframe src="https://127.0.0.1/private-frame"></iframe>'
  elif self.path=='/cdn':body=('<body><script src="https://'+CDN+'/pdf/Local+Plan+evidence/a.js"></script>').encode()
  elif self.path=='/pdf/Local+Plan+evidence/a.js':body=b'document.body.dataset.cdn="ok"';headers['Content-Type']='application/javascript'
  elif self.path=='/arcus':body=b'<button>Files</button><pre>01/10/2026\tPlanning Statement\tDownload</pre><a href="/sfc/servlet.shepherd/file.pdf">Download</a>'
  elif self.path=='/large' or self.path=='/oversize':
   size=200*1024*1024+(1 if self.path=='/oversize' else 0)
   self.send_response(200);self.send_header('Content-Type','application/pdf');self.send_header('Content-Disposition','attachment');self.send_header('Content-Length',str(size));self.end_headers()
   try:
    chunk=b'x'*65536
    while size:self.wfile.write(chunk[:min(size,len(chunk))]);size-=min(size,len(chunk))
   except (BrokenPipeError,ConnectionResetError,ssl.SSLError):pass
   return
  elif self.path=='/slow':
   self.send_response(200);self.send_header('Content-Length','100');self.end_headers()
   try:
    for i in range(100):self.wfile.write(b'x');self.wfile.flush();time.sleep(.05)
   except (BrokenPipeError,ConnectionResetError,ssl.SSLError):pass
   return
  else:body=b'<p>fixture</p>'
  self.send_response(status)
  for k,v in headers.items():self.send_header(k,v)
  self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(tmp/'cert.pem',tmp/'key.pem');server.socket=tls.wrap_socket(server.socket,server_side=True);threading.Thread(target=server.serve_forever,daemon=True).start()
port=server.server_address[1];connect=socket.create_connection
# A fixture bug cannot send Python traffic outside this one local TLS server.
def audit(event,args):
 if event=='socket.connect' and (not isinstance(args[1],tuple) or args[1][:2]!=('127.0.0.1',port)):raise RuntimeError('Forbidden fixture egress')
sys.addaudithook(audit)
def mapped(self):
 assert self.host=='8.8.8.8' and self.port==443
 return connect(('127.0.0.1',port),timeout=2)
def record(gate,**extra):outcomes.append(dict(gate=gate,result='PASS',**extra));print('PASS',gate,flush=True)
try:
 with patch.object(outbound,'resolved_addresses',lambda h,p:['8.8.8.8']),patch.object(HTTPSConnection,'_new_conn',mapped),patch.object(outbound.certifi,'where',lambda:str(tmp/'cert.pem')),sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=CHROME,headless=True,args=['--no-sandbox','--disable-background-networking','--host-resolver-rules=MAP * ~NOTFOUND'])
  parent=browser.new_context();page=parent.new_page();source=requests.Session();source.trust_env=False
  source.cookies.set('portal','original',domain=HOST,path='/',secure=True)
  source.cookies.set('other','secret',domain='unrelated.invalid',path='/',secure=True)
  parent.add_cookies([dict(name='parent',value='only',domain=HOST,path='/',secure=True,httpOnly=True,sameSite='Strict')])
  baseline_fds=len(os.listdir('/proc/self/fd'))
  def stable():
   assert browser.contexts==[parent] and parent.pages==[page] and not page.is_closed()
   assert len(os.listdir('/proc/self/fd'))==baseline_fds,'Document process/custodian descriptor leak'
  docs=get_anite_documents(page,source,BASE+'/summary?activeTab=summary',OUT/'anite');assert len(docs)==2
  assert all(d.local_path.read_bytes().startswith(b'%PDF-1.4 verified') for d in docs)
  assert source.cookies.get('portal',domain=HOST,path='/')=='updated';assert source.cookies.get('other')=='secret';stable()
  record('Anite two pages verified disk bytes identity cookies and parent preservation')
  docs=get_arcus_documents(page,'https://'+ARC+'/arcus',source);assert len(docs)==1 and docs[0].document_name=='Planning Statement' and '/servlet.shepherd/' in docs[0].source_url;stable();record('Arcus Files identity')
  with db.document_page(page,source,[BASE+'/redirect']) as (p,g):
   p.goto(BASE+'/redirect',wait_until='networkidle');g.check();assert p.url==BASE+'/base/page';assert p.locator('a').evaluate('e=>e.href')==BASE+'/base/child'
  assert any(x['path']=='/base/asset' for x in seen);stable();record('redirect final origin relative URL and subresource')
  with db.document_page(page,source,[BASE+'/cdn']) as (p,g):
   p.goto(BASE+'/cdn',wait_until='networkidle');assert p.locator('body').get_attribute('data-cdn')=='ok'
  assert all(not x['cookie'] for x in seen if x['host']==CDN);stable();record('legitimate allowlisted CDN no parent credentials')
  for path in ('private','hop0','ws','popup','frame'):
   try:
    with db.document_page(page,source,[BASE+'/'+path]) as (p,g):
     try:p.goto(BASE+'/'+path,wait_until='networkidle',timeout=5000);p.wait_for_timeout(100)
     finally:g.check()
   except db.DocumentBrowserFailure:pass
   else:raise AssertionError('Hostile path accepted: '+path)
   stable();record('denied '+path+' and context cleanup')
  assert not any(x['path'] in ('/popped','/socket','/private-frame') for x in seen)
  try:
   with db.document_page(page,source,[BASE+'/worker']) as (p,g):
    p.goto(BASE+'/worker',wait_until='networkidle');assert not p.context.service_workers
  except db.DocumentBrowserFailure:pass
  else:raise AssertionError('Unsupported worker attempt reported document success')
  assert not any(x['path'] in ('/worker.js','/sw.js') for x in seen);stable();record('service and dedicated workers blocked before dispatch')
  with db.document_page(page,source,[BASE]) as (p,g):
   p.goto(BASE+'/cookie-flags');assert 'parent=' not in p.evaluate('document.cookie')
   c=next(c for c in p.context.cookies() if c['name']=='parent');assert c['httpOnly'] and c['sameSite']=='Strict'
  c=next(c for c in parent.cookies() if c['name']=='parent');assert c['value']=='updated' and c['httpOnly'] and c['sameSite']=='Strict'
  with db.document_page(page,source,[BASE]) as (p,g):p.goto(BASE+'/cookie-delete')
  assert not any(c['name']=='parent' for c in parent.cookies());stable();record('cookie flags updates and deletion do not resurrect credentials')
  with db.document_page(page,source,[BASE]) as (p,g):
   p.goto(BASE+'/same-frame',wait_until='networkidle');assert p.frames[1].locator('p').inner_text()=='fixture'
  stable();record('same-origin frame traverses validated transport')
  with db.document_page(page,source,[BASE]) as (p,g):
   p.set_content('<a id="a" href="'+BASE+'/binaryA">A</a><a id="b" href="'+BASE+'/binaryB">B</a><a id="c" href="'+BASE+'/binaryC">C</a>')
   with p.expect_download() as a:p.locator('#a').click()
   with p.expect_download() as b:p.locator('#b').click()
   g.save_download(a.value,OUT/'queued-A.pdf')
   with p.expect_download() as c:p.locator('#c').click()
   g.save_download(b.value,OUT/'queued-B.pdf');g.save_download(c.value,OUT/'queued-C.pdf')
   assert (OUT/'queued-B.pdf').read_bytes().endswith(b'/binaryB') and (OUT/'queued-C.pdf').read_bytes().endswith(b'/binaryC')
  stable();record('queued download consume/interleave preserves exact identity')
  original=OUT/'existing.pdf';original.write_bytes(b'original-file')
  try:
   with db.document_page(page,source,[BASE]) as (p,g):
    p.set_content('<a href="'+BASE+'/binaryNew">new</a>')
    with p.expect_download() as download:p.locator('a').click()
    g.save_download(download.value,original);raise RuntimeError('after download')
  except db.DocumentBrowserFailure as exc:assert isinstance(exc.__cause__,RuntimeError)
  assert original.read_bytes()==b'original-file';stable();record('failed discovery restores preexisting file and removes partials')
  saved_process=db.protected_browser
  @contextmanager
  def late_failure(*args,**kwargs):
   with saved_process(*args,**kwargs) as value:yield value
   raise db.DocumentBrowserFailure('Synthetic late supervisor failure')
  before_cookie=source.cookies.get('portal',domain=HOST,path='/')
  try:
   with patch.object(db,'protected_browser',late_failure):
    with db.document_page(page,source,[BASE]) as (p,g):
     p.set_content('<a href="'+BASE+'/binaryLate">late</a>')
     with p.expect_download() as download:p.locator('a').click()
     g.save_download(download.value,original)
     g.source.cookies.set('portal','uncommitted',domain=HOST,path='/',secure=True)
  except db.DocumentBrowserFailure:pass
  else:raise AssertionError('Late supervisor failure suppressed')
  assert original.read_bytes()==b'original-file'
  assert source.cookies.get('portal',domain=HOST,path='/')==before_cookie
  stable();record('late supervisor failure restores file and withholds cookies')
  replace=Path.replace
  def interrupted_replace(path,target):
   value=replace(path,target)
   if path.name.startswith('.document-'):raise KeyboardInterrupt('after atomic replacement')
   return value
  try:
   with db.document_page(page,source,[BASE]) as (p,g):
    p.set_content('<a href="'+BASE+'/binaryInterrupt">interrupt</a>')
    with p.expect_download() as download:p.locator('a').click()
    with patch.object(Path,'replace',interrupted_replace):g.save_download(download.value,original)
  except KeyboardInterrupt:pass
  else:raise AssertionError('Post-replace cancellation suppressed')
  assert original.read_bytes()==b'original-file'
  assert not list(OUT.glob('.document-*'));stable();record('post-replacement cancellation restores original and removes partials')
  for error in (RuntimeError,KeyboardInterrupt):
   try:
    with db.document_page(page,source,[BASE]) as (p,g):raise error('synthetic interruption')
   except BaseException as exc:
    if error is KeyboardInterrupt:assert isinstance(exc,KeyboardInterrupt)
    else:assert isinstance(exc,db.DocumentBrowserFailure) and isinstance(exc.__cause__,error)
   stable()
  record('exception and cancellation cleanup')
  with db.document_page(page,source,[BASE]) as (p,g):
   p.set_content('<a href="'+BASE+'/large">download</a>');g.operation(15)
   before=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
   with p.expect_download():p.locator('a').click()
   assert len(g.artifacts)==1 and next(iter(g.artifacts.values())).stat().st_size==200*1024*1024
   assert g.max_chunk_bytes<=65536 and g.max_render_bytes==0
   growth=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss-before
   assert growth<100*1024,'large document materialized in Python memory'
   directory=g.directory
  assert not directory.exists();stable();record('200 MiB streaming bounded memory temporary cleanup',rss_growth_kib=growth,max_chunk_bytes=65536)
  try:
   with db.document_page(page,source,[BASE]) as (p,g):
    p.set_content('<a href="'+BASE+'/oversize">download</a>');g.operation(15);directory=g.directory
    try:p.locator('a').click();p.wait_for_timeout(50)
    finally:g.check()
  except db.DocumentBrowserFailure:pass
  else:raise AssertionError('oversize accepted')
  assert not directory.exists();stable();record('oversize streaming rejected partial file removed')
  try:
   with db.document_page(page,source,[BASE]) as (p,g):
    g.operation(.15);directory=g.directory
    try:p.goto(BASE+'/slow')
    finally:g.check()
  except db.DocumentBrowserFailure:pass
  else:raise AssertionError('slow timeout accepted')
  assert not directory.exists();stable();record('existing operation deadline interrupts slow stream')
  for i in range(21):
   with db.document_page(page,source,[BASE]) as (p,g):
    assert browser.contexts==[parent] and p.context.browser is not browser
    assert len(p.context.browser.contexts)==1
   stable()
   if i==19:
    replacement=parent.new_page();page.close();page=replacement;stable()
  record('21 context lifetimes and original page recycle leave no resources')
  try:
   with db.document_page(page,source,[BASE]) as (p,g):
    directory=g.directory;browser.close();raise RuntimeError('browser lost')
  except db.DocumentBrowserFailure:pass
  assert not directory.exists() and not browser.is_connected();record('browser failure releases temporary artifacts')
finally:
 server.shutdown();server.server_close();TMP.cleanup()
 (OUT/'result.json').write_text(json.dumps(dict(outcomes=outcomes,requests=seen,process_reports=process_reports,instrumentation='Synthetic TLS CA; validated public IP mapped only to loopback TCP. Separate syscall-filtered renderer process, measured status snapshots; original assertions preserved, context-count assertion adapted to process boundary; unsupported worker attempt now also must fail job.'),indent=2))
print('DONE',OUT)
