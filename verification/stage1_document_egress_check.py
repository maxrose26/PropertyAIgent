"""Required negative gate with a valid local TURN positive control.

The loopback-candidate flag is fixture-only: this isolated test machine otherwise
has no usable ICE interface. It does not change application/browser launch code.
A successful connection in the protected context is a real failed gate, not xfail.
The resolver denies other destinations but permits the literal loopback fixture;
without that exclusion Chromium also blocks the TURN positive control itself.
"""
import json,socket,sys,threading,os
from contextlib import contextmanager
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.security.document_browser import document_page,DocumentBrowserFailure
from app.security import document_browser as db,document_process as dp
os.environ['PROPERTYAIGENT_DOCUMENT_CHROMIUM']=sys.argv[2]
dp.EXTRA_BROWSER_ARGS=('--allow-loopback-in-peer-connection',)
reports=[]
original_process=db.protected_browser
@contextmanager
def recorded_process(*args,**kwargs):
    status=None
    try:
        with original_process(*args,**kwargs) as value:
            status=value[1]
            yield value
    finally:
        if status is not None:reports.append(status())
db.protected_browser=recorded_process
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True);results=[]
for protected in (False,True):
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen();listener.settimeout(4)
    port=listener.getsockname()[1];connections=[]
    def receive():
        try:
            conn,_=listener.accept();connections.append('local TURN TCP');conn.close()
        except socket.timeout:pass
    thread=threading.Thread(target=receive);thread.start()
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=sys.argv[2],headless=True,args=['--no-sandbox','--disable-background-networking','--allow-loopback-in-peer-connection','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1'])
        parent=browser.new_context();base=parent.new_page();source=requests.Session()
        def probe(page):
            page.evaluate('''port=>{window.pc=new RTCPeerConnection({iceTransportPolicy:'relay',iceServers:[{urls:'turn:127.0.0.1:'+port+'?transport=tcp',username:'synthetic',credential:'synthetic'}]});pc.createDataChannel('fixture');pc.createOffer().then(o=>pc.setLocalDescription(o));}''',port)
            page.wait_for_timeout(3500)
        if protected:
            failure=None
            try:
                with document_page(base,source,[]) as (page,renderer):probe(page);failure=renderer.failure
            except DocumentBrowserFailure as exc:failure=str(exc)
        else:probe(base);failure=None
        results.append(dict(protected=protected,connections=connections,renderer_failure=failure))
        source.close();browser.close()
    thread.join();listener.close()
(out/'result.json').write_text(json.dumps(dict(results=results,process_reports=reports,fixture='Loopback-only synthetic TURN TCP positive control; explicit fixture ICE loopback flag.'),indent=2))
assert results[0]['connections'],'Positive control unavailable: no containment conclusion possible'
assert not results[1]['connections'],'BLOCKED: protected document context permits TURN TCP outside validated transport'
assert results[1]['renderer_failure'],'Native attempt must fail document job'
assert reports and reports[-1]['notifications']>0,'Kernel denial evidence required'
assert reports[-1]['closed'],'Renderer descendants must be reaped'
print('PASS document network containment')
