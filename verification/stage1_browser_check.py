"""Synthetic native OIDC and real Chromium checks. No production inputs.

Provider uses ephemeral RSA keys; no signature/user monkeypatch. The external
fixture page imports actual app guards and delivery helpers. Full router is
also exercised against disposable data. Network allowlists are test-only.
"""
import argparse,json,os,sys,time,threading,tempfile,subprocess,shutil,urllib.parse,urllib.request,secrets,re
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from joserfc.jwk import RSAKey
from joserfc import jwt
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--chromium',required=True);parser.add_argument('--routes-only',action='store_true');args=parser.parse_args()
OUT=Path(args.output).resolve();OUT.mkdir(parents=True,exist_ok=True)
if any(k in os.environ for k in ('DATABASE_URL','OPENAI_API_KEY','ANTHROPIC_API_KEY','SUPABASE_URL')):raise RuntimeError('Reject inherited credentials')
if any(p for p in ROOT.glob('.env*') if p.name!='.env.example'):raise RuntimeError('Reject environment files')
TMP=Path(tempfile.mkdtemp(prefix='stage1-browser-'));ISS='http://127.0.0.1:18761';WEB='http://127.0.0.1:18762'
key=RSAKey.generate_key(2048);key.ensure_kid();codes={};subject='reader-a';lifetime=600;claim_changes={};events=[];outcomes=[]
def record(name):outcomes.append({'gate':name,'result':'PASS'});print('PASS',name,flush=True)
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def reply(self,data):
  raw=json.dumps(data).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 def do_GET(self):
  u=urllib.parse.urlsplit(self.path);q=urllib.parse.parse_qs(u.query)
  if u.path=='/.well-known/openid-configuration':self.reply(dict(issuer=ISS,authorization_endpoint=ISS+'/authorize',token_endpoint=ISS+'/token',jwks_uri=ISS+'/jwks',response_types_supported=['code'],subject_types_supported=['public'],id_token_signing_alg_values_supported=['RS256'],token_endpoint_auth_methods_supported=['client_secret_basic']))
  elif u.path=='/jwks':self.reply({'keys':[key.as_dict(private=False)]})
  elif u.path=='/authorize':
   code=secrets.token_urlsafe(20);codes[code]=(q,subject,lifetime,dict(claim_changes));self.send_response(302);self.send_header('Location',q['redirect_uri'][0]+'?'+urllib.parse.urlencode({'code':code,'state':('wrong-state' if claim_changes.get('_bad_state') else q['state'][0])}));self.end_headers()
  else:self.send_error(404)
 def do_POST(self):
  q=urllib.parse.parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode());req,who,life,changes=codes.pop(q['code'][0]);now=int(time.time())
  claims=dict(iss=ISS,sub=who,aud='local-client',iat=now,exp=now+life,nonce=req['nonce'][0],email=who+'@example.invalid',email_verified=True);claims.update(changes)
  signing_key=RSAKey.generate_key(2048) if claims.pop('_bad_signature',False) else key
  self.reply(dict(access_token='synthetic',token_type='Bearer',expires_in=life,id_token=jwt.encode({'alg':'RS256','kid':key.kid},claims,signing_key)))
provider=ThreadingHTTPServer(('127.0.0.1',18761),Handler);threading.Thread(target=provider.serve_forever,daemon=True).start()
policy=dict(version=1,enabled=True,environment='local',issuer=ISS,client_id='local-client',web_processes=1,web_replicas=1,owner_subject='operator',principals=[dict(issuer=ISS,subject=s,role=r,enabled=True,workspace_id=1,buyer_ids=b) for s,r,b in [('operator','operator',[1]),('reader-a','reader',[1]),('reader-b','reader',[2])]])
policy_path=TMP/'policy.json'
def save_policy():policy_path.write_text(json.dumps(policy))
save_policy()
# Disposable schema and explicit grants target deterministic fixture IDs.
from sqlalchemy import create_engine
from app.db.models import Base
from verification.stage1_test_context import seed_fixture
engine=create_engine('sqlite:///'+str(TMP/'disposable.sqlite'));Base.metadata.create_all(engine);seed_fixture(engine)
from sqlalchemy.orm import Session
from app.db.models import Council,Site,Application,SchemeIntelligence,LocalPlan,LocalPlanSite
with Session(engine) as session:
 session.add(Council(code='stockport',name='Stockport',base_url='https://planning.stockport.gov.uk',doc_system='idox',date_field_mode='received'))
 for i in (1,2):
  session.add(Site(id=i,council_code='stockport',canonical_address='synthetic '+str(i),display_address='Synthetic site '+str(i)))
  session.add(Application(id=i,site_id=i,council_code='stockport',reference='SYN/'+str(i),proposal='Residential housing',status='Decided',decision='Granted',application_category='full',application_type='Full Application',application_received='2026-01-01',decision_issued_date='2026-01-01'))
  session.add(SchemeIntelligence(application_id=i,total_units_final=20*i,affordable_units_final=10*i,affordable_percentage_final=50,core_intelligence_complete=True,unit_reconciliation_status='OK',affordable_classification_confidence='high',affordable_housing_status='legally_secured',development_type='houses',developer='=1+1'))
 session.add(LocalPlan(id=1,council_code='stockport',plan_name='Synthetic plan',status='adopted'))
 session.add(LocalPlanSite(id=1,council_code='stockport',local_plan_id=1,site_name='Land off Test Road',policy_reference='TEST1',minimum_dwellings=20,plan_name='Synthetic plan',plan_status='adopted',allocation_status='adopted'))
 session.commit()
engine.dispose()
(TMP/'fixture.py').write_text('''import streamlit as st
from app.ui.access import page_scope
from app.security.access import require_operator,AccessDenied
from app.ui.protected_download import download_button
from app.ui import safe_table
import pandas as pd
with page_scope() as actor:
 st.success("ADMITTED "+actor.subject)
 st.write("Buyers "+str(sorted(actor.buyer_ids)))
 safe_table.data_editor(pd.DataFrame({"External":["=1+1"],"Hidden":["@SUM(1,1)"]}),column_config={"Hidden":None},key="fixture-editor")
 download_button("Request protected CSV",("buyer_id\\n"+str(next(iter(actor.buyer_ids)))+"\\n").encode(),file_name="private.csv",mime="text/csv",key="csv")
 if st.button("Operator command"):
  try:
   require_operator("test.write")
   st.success("Operator authorised")
  except AccessDenied: st.error("Command denied")
''')
from PIL import Image
Image.new('RGB',(4,4),'red').save(TMP/'evidence.png')
fixture=(TMP/'fixture.py').read_text().replace('from app.ui.protected_download import download_button','from app.ui.protected_download import download_button,image\nfrom app.db import session as database\nfrom pathlib import Path\ndatabase.DATA_DIR=Path('+repr(str(TMP))+')').replace(' st.success("ADMITTED "+actor.subject)',' image('+repr(str(TMP/'evidence.png'))+')\n st.success("ADMITTED "+actor.subject)')
(TMP/'fixture.py').write_text(fixture)
secrets_config={'auth':{'redirect_uri':WEB+'/oauth2callback','cookie_secret':secrets.token_hex(32),'oidc':{'client_id':'local-client','client_secret':'synthetic-only','server_metadata_url':ISS+'/.well-known/openid-configuration'}}}
(TMP/'server.py').write_text('import streamlit as st\nfrom starlette.middleware import Middleware\nfrom app.security.middleware import AccessMiddleware\napp=st.App('+repr(str(TMP/'fixture.py'))+',middleware=[Middleware(AccessMiddleware)],secrets='+repr(secrets_config)+')\n')
# Block Python-side outbound connections except the two allocated fixture ports.
(TMP/'launch.py').write_text('''import sys,runpy
import socket
def guard(event,args):
 if event=='socket.connect' and isinstance(args[1],tuple):
  host,port=args[1][:2]
  if host not in ('127.0.0.1','::1') or port not in (18761,18762):raise RuntimeError('Forbidden fixture egress')
 if event=='socket.getaddrinfo' and args[0] not in ('127.0.0.1','localhost','::1'):raise RuntimeError('Forbidden fixture DNS')
sys.addaudithook(guard)
from pathlib import Path
from app.db import session as database
# Isolated provider fixture replaces only the SDK constructor, never guards,
# identities, generation services, schemas or grounding validation.
import openai,json
from types import SimpleNamespace
class SyntheticProvider:
 def __init__(self,*args,**kwargs):self.responses=self
 def create(self,**kwargs):
  name=kwargs.get('text',{}).get('format',{}).get('name')
  with open('provider-calls.jsonl','a') as log:log.write(json.dumps({'schema':name})+'\\n')
  if name=='report_narrative':data=dict(executive_summary='Synthetic local report.',buying_opportunities_and_risks='Verify primary evidence.')
  elif name=='web_research_evidence':data={'items':[]}
  elif name=='cross_site_intelligence':data=dict(executive_summary='The shortlist spans an adopted allocation.',priority_opportunities=['Land off Test Road warrants further investigation.'],cross_site_observations=['Land off Test Road has no identified planning activity.'],recent_external_developments=[],key_uncertainties=['Site control remains unverified.'],investigation_priorities=['Confirm site control for Land off Test Road.'])
  else:return SimpleNamespace(output_text='No additional public evidence found.',output=[])
  return SimpleNamespace(output_text=json.dumps(data),output=[])
openai.OpenAI=SyntheticProvider
original_engine=database.get_engine
counter=Path('database-acquisitions.txt');counter.write_text('0')
def guarded_engine():
 counter.write_text(str(int(counter.read_text())+1))
 return original_engine()
database.get_engine=guarded_engine
sys.argv=['streamlit','run',sys.argv[1],'--server.address=127.0.0.1','--server.port=18762','--server.headless=true','--browser.gatherUsageStats=false']
runpy.run_module('streamlit',run_name='__main__')
''')
env={'PATH':'/usr/bin:/bin','HOME':str(TMP),'PYTHONPATH':str(ROOT),'PROPERTYAIGENT_ACCESS_POLICY':str(policy_path),'DATABASE_URL':'sqlite:///'+str(TMP/'disposable.sqlite'),'PYTHON_DOTENV_DISABLED':'1','PYTHONDONTWRITEBYTECODE':'1','OPENAI_API_KEY':'synthetic-fixture-not-a-real-key'}
proc=None;logs=[]
def start():
 global proc
 log=(OUT/f'server-{len(logs)}.log').open('w');logs.append(log)
 proc=subprocess.Popen([sys.executable,str(TMP/'launch.py'),str(TMP/'server.py')],cwd=TMP,env=env,stdout=log,stderr=subprocess.STDOUT)
 for _ in range(150):
  if proc.poll() is not None:raise RuntimeError('Server stopped; inspect redacted log')
  try:urllib.request.urlopen(WEB+'/_stcore/health',timeout=.2);return
  except Exception:time.sleep(.1)
 raise RuntimeError('Local server startup timeout')
def stop():
 if proc and proc.poll() is None:proc.terminate();proc.wait(timeout=10)
# Observe actual protocol completion without injecting widget/session state.
# Allocation-detail labels intentionally lag one interaction (accepted Gate 1A).
script_events={}
def observe_page(page):
 from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
 from streamlit.proto.BackMsg_pb2 import BackMsg
 state=script_events[page]=dict(requests=0,completed=0,running=False,pending=False)
 page.on('pageerror',lambda error:events.append({'browser_error':str(error)}))
 def observe_socket(socket):
  def sent(payload):
   msg=BackMsg();msg.ParseFromString(payload)
   if msg.WhichOneof('type')=='rerun_script':state['requests']+=1;state['pending']=True
  def received(payload):
   msg=ForwardMsg();msg.ParseFromString(payload);kind=msg.WhichOneof('type')
   if kind=='session_status_changed':state['running']=msg.session_status_changed.script_is_running
   if kind=='script_finished' and msg.script_finished==ForwardMsg.FINISHED_SUCCESSFULLY:state['completed']+=1;state['pending']=False
  socket.on('framesent',sent);socket.on('framereceived',received)
 page.on('websocket',observe_socket)
def wait_script(page,predicate):
 deadline=time.monotonic()+30
 while time.monotonic()<deadline:
  if predicate(script_events[page]):return
  page.wait_for_timeout(50)
 raise AssertionError('Streamlit script completion not observed: '+repr(script_events[page]))
def click_after_script(page,button):
 wait_script(page,lambda s:s['completed']>0 and not s['pending'] and not s['running'])
 before=script_events[page].copy();button.click()
 wait_script(page,lambda s:s['requests']>before['requests'] and s['completed']>before['completed'] and not s['pending'] and not s['running'])
 (OUT/'shortlist-script-completion.json').write_text(json.dumps(dict(before=before,after=script_events[page]),indent=2))
def new_context(browser):
 ctx=browser.new_context()
 # Headless OS save dialogs cannot be accepted. Exercise Streamlit's actual
 # browser Blob fallback, as in browsers without File System Access support.
 ctx.add_init_script("window.showSaveFilePicker=async()=>{throw new DOMException('Synthetic unsupported picker','NotSupportedError')};")
 ctx.on('page',observe_page)
 ctx.route('**/*',lambda route:route.continue_() if urllib.parse.urlsplit(route.request.url).hostname=='127.0.0.1' and urllib.parse.urlsplit(route.request.url).port in (18761,18762) else route.abort())
 return ctx
def login(page,who):
 global subject
 subject=who;page.goto(WEB);page.get_by_role('button',name='Sign in',exact=True).wait_for();time.sleep(1.05)
 with page.expect_response(lambda response:'/oauth2callback?' in response.url):
  page.get_by_role('button',name='Sign in',exact=True).click()
def browser_download(page,label,filename,save_name,prefix=None):
 page.get_by_role('button',name=label,exact=True).click()
 selector='a[download="'+filename+'"]'
 if 'selected scheme' in label:selector='[class*="st-key-delivery-"][class*="download_selected_report"] '+selector
 link=page.locator(selector)
 try:link.wait_for()
 except Exception:
  (OUT/'delivery-dom.html').write_text(page.content());page.screenshot(path=str(OUT/'delivery-failure.png'),full_page=True);raise
 assert link.get_attribute('href').startswith('blob:')
 with page.expect_download() as event:link.click()
 path=OUT/save_name;event.value.save_as(path);raw=path.read_bytes()
 if prefix:assert raw.startswith(prefix)
 return raw
def admitted(page,who):page.get_by_text('ADMITTED '+who,exact=True).wait_for(timeout=20000)
try:
 if args.routes_only:
  (TMP/'server.py').write_text((TMP/'server.py').read_text().replace(repr(str(TMP/'fixture.py')),repr(str(ROOT/'app/ui/streamlit_app.py'))))
 start()
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox','--disable-background-networking'])
  if not args.routes_only:
   ctx=new_context(browser);page=ctx.new_page();page.goto(WEB+'/Scheme_Detail?site_id=78');page.get_by_role('button',name='Sign in',exact=True).wait_for();assert 'ADMITTED' not in page.locator('body').inner_text();record('signed-out deep link denies')
   login(page,'unadmitted');page.get_by_text('Access denied.',exact=True).wait_for();assert 'Request protected CSV' not in page.locator('body').inner_text();record('valid unadmitted identity denied');ctx.close()
   for label,changes in [('forged signature',{'_bad_signature':True}),('wrong issuer',{'iss':'https://wrong.invalid'}),('wrong audience',{'aud':'wrong'}),('wrong nonce',{'nonce':'wrong'}),('expired token',{'exp':1}),('wrong state',{'_bad_state':True})]:
    claim_changes=changes
    invalid_ctx=new_context(browser);invalid_page=invalid_ctx.new_page();login(invalid_page,'reader-a');invalid_page.get_by_role('button',name='Sign in',exact=True).wait_for(timeout=20000);assert 'ADMITTED' not in invalid_page.locator('body').inner_text();record('native '+label+' denied');invalid_ctx.close()
   claim_changes={}
   # Hold the new application WebSocket after the native callback; the
   # initial anonymous WebSocket already exists. No new app lease can load.
   prelease=new_context(browser);landing=prelease.new_page();subject='reader-a'
   landing.goto(WEB);landing.get_by_role('button',name='Sign in',exact=True).wait_for();time.sleep(1.05)
   held_sockets=[]
   prelease.route_web_socket('**/*',lambda route:held_sockets.append(route))
   with landing.expect_response(lambda response:'/oauth2callback?' in response.url):landing.get_by_role('button',name='Sign in',exact=True).click()
   for attempt in range(100):
    if held_sockets:break
    landing.wait_for_timeout(50)
   assert held_sockets,'Native landing must be held before its app WebSocket connects'
   assert 'ADMITTED' not in landing.locator('body').inner_text()
   unleased_cookies=prelease.cookies();assert any(c['name']=='_streamlit_user' for c in unleased_cookies)
   prelease.request.get(WEB+'/auth/logout');prelease.close()
   replay=new_context(browser);replay.add_cookies(unleased_cookies);replay_page=replay.new_page();replay_page.goto(WEB)
   replay_page.get_by_text('Sign in again.',exact=True).wait_for();assert 'ADMITTED' not in replay_page.locator('body').inner_text();replay.close()
   record('native logout before first app lease rejects copied cookie')
   ctx=new_context(browser);page=ctx.new_page();login(page,'reader-a');admitted(page,'reader-a');record('native OIDC reader login')
   assert page.locator('a[download]').count()==0
   editor=page.locator('[data-testid="stDataFrame"]').first;editor.hover()
   editor_export=editor.get_by_role('button',name='Download as CSV',exact=True);editor_export.focus()
   with page.expect_download() as event:editor_export.press('Enter')
   event.value.save_as(OUT/'editor-toolbar.csv');assert b"'=1+1" in (OUT/'editor-toolbar.csv').read_bytes();record('data editor toolbar CSV safety')
   page.get_by_role('button',name='Operator command',exact=True).click();page.get_by_text('Command denied',exact=True).wait_for();record('reader command denied')
   page.get_by_role('button',name='Request protected CSV',exact=True).click();link=page.locator('a[download="private.csv"]');link.wait_for()
   assert link.get_attribute('href').startswith('blob:');old_blob=link.get_attribute('href')
   source_image=page.locator('img[alt="Source evidence"]');source_image.wait_for();assert source_image.get_attribute('src').startswith('blob:');old_image=source_image.get_attribute('src');record('protected image browser payload')
   with page.expect_download() as download:link.click()
   saved=OUT/'reader-a.csv';download.value.save_as(saved);assert saved.read_bytes()==b'buyer_id\n1\n';record('protected CSV browser download bytes')
   assert ctx.request.get(WEB+'/media/anything.csv').status==404;record('native media route denied')
   oldcookies=ctx.cookies();second=ctx.new_page();second.goto(WEB);admitted(second,'reader-a')
   page.goto(WEB+'/auth/logout');page.get_by_role('button',name='Sign in',exact=True).wait_for();second.reload();second.get_by_role('button',name='Sign in',exact=True).wait_for();record('direct native logout and stale tab')
   replay=new_context(browser);replay.add_cookies(oldcookies);replay_page=replay.new_page();replay_page.goto(WEB);replay_page.get_by_text('Sign in again.',exact=True).wait_for();assert replay_page.locator('a[download]').count()==0;record('copied old cookie denied after logout');replay.close();ctx.close()
   ctx=new_context(browser);page=ctx.new_page();login(page,'reader-b');admitted(page,'reader-b');assert 'Buyers [2]' in page.locator('body').inner_text();assert page.locator('a[download]').count()==0;record('fresh buyer B has no A download');assert page.evaluate('(url)=>fetch(url).then(()=>false).catch(()=>true)',old_blob);assert page.evaluate('(url)=>fetch(url).then(()=>false).catch(()=>true)',old_image);record('buyer B cannot fetch A Blob URL');ctx.close()
   ctx=new_context(browser);page=ctx.new_page();login(page,'operator');admitted(page,'operator');page.get_by_role('button',name='Operator command',exact=True).click();page.get_by_text('Operator authorised',exact=True).wait_for();record('operator positive path');ctx.close()
   ctx=new_context(browser);page=ctx.new_page();login(page,'reader-a');admitted(page,'reader-a');policy['principals'][1]['enabled']=False;save_policy();page.reload();page.get_by_text('Access denied.',exact=True).wait_for();record('grant revocation');policy['principals'][1]['enabled']=True;save_policy();ctx.close()
   lifetime=3;ctx=new_context(browser);page=ctx.new_page();login(page,'reader-a');admitted(page,'reader-a');time.sleep(3.2);page.reload();page.get_by_text('Sign in again.',exact=True).wait_for();record('provider expiry');ctx.close();lifetime=600
   ctx=new_context(browser);page=ctx.new_page();login(page,'reader-a');admitted(page,'reader-a');stop();time.sleep(1.05);start();page.reload();page.get_by_text('Sign in again.',exact=True).wait_for();record('restart rejects old issuance');ctx.close()
   stop()
   server_text=(TMP/'server.py').read_text().replace(repr(str(TMP/'fixture.py')),repr(str(ROOT/'app/ui/streamlit_app.py')))
   (TMP/'server.py').write_text(server_text)
   start()
   ctx=new_context(browser);page=ctx.new_page();page.goto(WEB+'/Scheme_Detail?site_id=78');page.get_by_role('button',name='Sign in',exact=True).wait_for();(OUT/'anonymous-router.txt').write_text(page.locator('body').inner_text());assert (TMP/'database-acquisitions.txt').read_text()=='0';assert page.get_by_role('heading',name=re.compile('Dashboard$')).count()==0;record('real router anonymous deep link denied')
   policy_path.unlink();page.reload();page.get_by_text('Application access is unavailable.',exact=True).wait_for();assert (TMP/'database-acquisitions.txt').read_text()=='0';record('missing policy denies before database');save_policy()
   saved_owner=policy['owner_subject'];policy['owner_subject']='missing-owner';save_policy();page.reload();page.get_by_text('Application access is unavailable.',exact=True).wait_for();assert (TMP/'database-acquisitions.txt').read_text()=='0';record('missing owner denies before database');policy['owner_subject']=saved_owner;save_policy()
   login(page,'reader-a');page.get_by_role('heading',name=re.compile('Dashboard$')).wait_for(timeout=20000);assert page.get_by_text('Application access is unavailable.',exact=True).count()==0;record('real router reader dashboard')
   page.screenshot(path=str(OUT/'reader-dashboard.png'),full_page=True)
   page.goto(WEB+'/Council_Dashboard');page.get_by_text('Operator permission required.',exact=True).wait_for(timeout=20000);record('real router operator page denied')
   ctx.close()
  policy['paid_actions']={'report.narrative':True,'shortlist.research':True,'shortlist.intelligence':True};save_policy()
  ctx=new_context(browser);page=ctx.new_page();login(page,'operator');page.get_by_role('heading',name=re.compile('Dashboard$')).wait_for()
  page.goto(WEB+'/Explore');page.get_by_role('button',name='Export as CSV (2 sites)',exact=True).wait_for(timeout=20000)
  raw=browser_download(page,'Export as CSV (2 sites)','scheme_report.csv','explore-all.csv');assert b'Synthetic site 1' in raw and b'Synthetic site 2' in raw;record('populated Explore all CSV real browser bytes')
  table=page.locator('.st-key-explore-desktop-table');table.hover()
  table_export=table.get_by_role('button',name='Download as CSV',exact=True);table_export.focus()
  with page.expect_download() as event:table_export.press('Enter')
  event.value.save_as(OUT/'explore-toolbar.csv');assert b"'=1+1" in (OUT/'explore-toolbar.csv').read_bytes();record('populated dataframe toolbar CSV safety')
  # Select a real table row via the browser canvas, not injected widget state.
  canvas=page.locator('.st-key-explore-desktop-table canvas').first;canvas.scroll_into_view_if_needed();box=canvas.bounding_box();page.mouse.click(box['x']+15,box['y']+52);page.screenshot(path=str(OUT/'selection.png'),full_page=True);(OUT/'selection.txt').write_text(page.locator('body').inner_text())
  page.get_by_role('button',name='Export as CSV (1 selected scheme)',exact=True).wait_for(timeout=20000)
  raw=browser_download(page,'Export as CSV (1 selected scheme)','scheme_report.csv','explore-selected.csv');assert (b'Synthetic site 1' in raw)!=(b'Synthetic site 2' in raw);record('populated Explore selected CSV actual selection')
  page.get_by_role('button',name='Generate PDF summary report (2 sites)',exact=True).click();page.get_by_role('button',name='Download PDF summary report',exact=True).wait_for(timeout=20000)
  browser_download(page,'Download PDF summary report','scheme_summary_report.pdf','explore.pdf',b'%PDF');record('populated Explore PDF with isolated provider')
  # Filter change invalidates the previous generated report and selection.
  page.get_by_role('spinbutton',name='Min total units',exact=True).fill('30');page.get_by_role('spinbutton',name='Min total units',exact=True).press('Enter')
  try:page.get_by_role('button',name='Export as CSV (2 sites)',exact=True).wait_for(state='hidden')
  except Exception:
   (OUT/'filter-failure.txt').write_text(page.locator('body').inner_text());(OUT/'filter-inputs.json').write_text(json.dumps(page.get_by_role('spinbutton').evaluate_all('(els)=>els.map(e=>({label:e.getAttribute("aria-label"),value:e.value}))')));raise
  assert page.get_by_role('button',name='Download PDF summary report',exact=True).count()==0;assert page.get_by_role('button',name='Export as CSV (1 selected scheme)',exact=True).count()==0;record('changed results clear PDF and selection')
  page.goto(WEB+'/Local_Plan_Sites?allocation_id=1');page.get_by_role('button',name='☆ Add to shortlist',exact=True).wait_for();click_after_script(page,page.get_by_role('button',name='☆ Add to shortlist',exact=True))
  page.get_by_role('button',name='← Back to Allocation Discovery',exact=True).click()
  page.get_by_role('link',name=re.compile('1 allocation shortlisted')).first.click();page.get_by_role('heading',name=re.compile('Shortlist$')).wait_for()
  raw=browser_download(page,'Download shortlist CSV (1 allocation)','allocation_shortlist.csv','shortlist.csv');assert b'Land off Test Road' in raw;record('populated shortlist CSV')
  page.get_by_role('button',name='Download shortlist PDF report',exact=True).click();pdf=page.locator('a[download$=".pdf"]').first;pdf.wait_for()
  with page.expect_download() as event:pdf.click()
  event.value.save_as(OUT/'shortlist.pdf');assert (OUT/'shortlist.pdf').read_bytes().startswith(b'%PDF');record('populated deterministic shortlist PDF')
  page.get_by_text('🧠 Generate AI Intelligence Report',exact=True).click();page.get_by_role('button',name='Generate AI Intelligence Report',exact=True).click();page.get_by_role('button',name='Download AI Intelligence PDF report',exact=True).wait_for(timeout=20000)
  page.get_by_role('button',name='Download AI Intelligence PDF report',exact=True).click();pdf=page.locator('a[download*="ai"]').first;pdf.wait_for()
  with page.expect_download() as event:pdf.click()
  event.value.save_as(OUT/'shortlist-ai.pdf');assert (OUT/'shortlist-ai.pdf').read_bytes().startswith(b'%PDF');record('populated AI shortlist PDF with isolated provider')
  page.get_by_role('button',name='Clear shortlist',exact=True).click();page.get_by_text('No allocations shortlisted yet',exact=True).wait_for();assert page.locator('a[download]').count()==0;record('shortlist removal clears all downloads')
  page.screenshot(path=str(OUT/'populated-completion.png'),full_page=True)
  if (TMP/'provider-calls.jsonl').exists():shutil.copyfile(TMP/'provider-calls.jsonl',OUT/'provider-calls.jsonl')
  ctx.close();browser.close()
except BaseException:
 try:
  page.screenshot(path=str(OUT/'failure.png'),full_page=True)
  (OUT/'failure.txt').write_text(page.locator('body').inner_text())
 except Exception:pass
 raise
finally:
 (OUT/'browser-errors.json').write_text(json.dumps(events,indent=2))
 stop();provider.shutdown()
 for log in logs:log.close()
 (OUT/'result.json').write_text(json.dumps({'outcomes':outcomes,'expected_checks':9 if args.routes_only else 37,'limits':'Synthetic local OIDC; fixture page uses production guards/delivery. Not production verification.'},indent=2))
print('DONE',OUT,flush=True)
