"""Real Chromium viewport/accessibility smoke of existing shared renderers.

Network is restricted to the disposable loopback Streamlit server. No production
or council traffic; no model calls, credentials or persistent application writes.
"""
import os,sys,json,subprocess,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
for key in ('DATABASE_URL','OPENAI_API_KEY','ANTHROPIC_API_KEY','SUPABASE_URL','PROPERTYAIGENT_ACCESS_POLICY'):
    if key in os.environ:raise RuntimeError('Reject inherited sensitive runtime inputs')
env=dict(os.environ,B21_BROWSER_REHEARSAL='1',PYTHON_DOTENV_DISABLED='1')
log=(out/'server.log').open('w')
proc=subprocess.Popen([sys.executable,'-m','streamlit','run',str(ROOT/'verification/b21/browser_app.py'),
    '--server.address=127.0.0.1','--server.port=18721','--server.headless=true','--browser.gatherUsageStats=false'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
try:
    for _ in range(100):
        if proc.poll() is not None:raise RuntimeError('Disposable renderer exited')
        try:
            with urllib.request.urlopen('http://127.0.0.1:18721/_stcore/health',timeout=1) as response:
                if response.status==200:break
        except OSError:time.sleep(.1)
    else:raise RuntimeError('Disposable renderer health timeout')
    results=[]
    with sync_playwright() as p:
        browser=p.chromium.launch()
        for name,width,height in [('desktop',1440,1000),('mobile',390,844)]:
            context=browser.new_context(viewport={'width':width,'height':height})
            context.route('**/*',lambda route:route.continue_() if route.request.url.startswith('http://127.0.0.1:18721/') else route.abort())
            page=context.new_page();page.goto('http://127.0.0.1:18721',wait_until='networkidle')
            page.get_by_text('B2.1 synthetic presentation rehearsal',exact=True).wait_for()
            page.get_by_text('Related acquisition subjects (2)',exact=True).click()
            page.get_by_text('Source conflict requires review.',exact=False).wait_for()
            body=page.locator('body').inner_text()
            for expected in ('Planning: Refused','Decision issued: 2026-09-25','Verified as of: 08 Oct 2026','Successful status verification unavailable','Source conflict requires review','Profile planning history'):
                assert expected in body,(name,expected,body)
            assert page.locator('[data-testid="stException"]').count()==0
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'),f'{name}: page overflow'
            # Verify the live captions themselves wrap and are not horizontally clipped.
            long=page.get_by_text('Source conflict requires review.',exact=False)
            box=long.bounding_box();assert box and box['x']>=0 and box['x']+box['width']<=width+1
            assert box['height']>20
            # Streamlit expander uses the native disclosure (summary), not a button.
            disclosure=page.locator('summary').filter(has_text='Related acquisition subjects')
            assert disclosure.count()==1
            assert 'Related acquisition subjects' in disclosure.inner_text()
            assert disclosure.evaluate("el => el.parentElement.tagName === 'DETAILS' && el.parentElement.open")
            page.screenshot(path=str(out/f'{name}.png'),full_page=True)
            results.append({'viewport':name,'width':width,'height':height,'overflow':False,'status_fact_date_verification_qualification':True,'long_qualification_wrap':True,'expander_accessible_name':True})
            context.close()
        browser.close()
    (out/'browser.json').write_text(json.dumps({'candidate':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'results':results,'scope':'Shared real Streamlit renderers with synthetic fixtures; full application journeys separately tested by AppTest. Not production authentication or complete WCAG certification.'},indent=2))
finally:
    proc.terminate()
    try:proc.wait(timeout=10)
    except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
    log.close()
