"""Offline Chromium layout proof for actual shared Spec028 renderers.

Synthetic multipage host exercises real Streamlit links and components. Access
guards and application-page resolution are separately tested by journey tests;
this host is not evidence of production authentication or production data.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = '''
import streamlit as st
from app.policy.buyer_matching import BuyerFitAssessment
from app.reporting.family_presentation import FamilyView, SubjectView
from app.reporting.mandate_explanation import present_mandate_explanation
from app.ui.shell import opportunity_family_card, render_mandate_explanation
st.set_page_config(page_title="Offline Spec028 evidence",layout="wide")
fit=BuyerFitAssessment(classification="POSSIBLE_FIT",is_investigative_exception=False,matches=["Recorded general-needs housing reason.","Recorded planning reason.","Recorded scope-qualified scale reason."],unknown=["Recorded source limitation."])
explanation=present_mandate_explanation(fit,{"application_reference":"SYN/PHASE1","decision_date":"2026-01-01"})
def dashboard():
 st.title("Buyer dashboard")
 st.caption("Synthetic buyer: Nesten Homes")
 best=SubjectView(label="Phase 1",scale="~100 homes",fit_key="POSSIBLE_FIT",fit_label="Possible Mandate Fit",investigative=False,reasons=tuple(fit.matches[:2]),headline_reason=None,signal_key=None,signal_label=None,metrics=(),tags=(),page=profile_page,params={"subject_key":"synthetic-phase-1"},explanation=explanation)
 related=SubjectView(label="Wider permission",scale="500 homes",fit_key="STRONG_FIT",fit_label="Strong Mandate Fit",investigative=False,reasons=("Recorded wider-scope reason.",),headline_reason=None,signal_key=None,signal_label=None,metrics=(),tags=(),page=None,params={},explanation=present_mandate_explanation(BuyerFitAssessment(classification="STRONG_FIT",is_investigative_exception=False,matches=["Recorded wider-scope reason."])))
 opportunity_family_card(FamilyView("synthetic","Synthetic development","Scope-qualified offline fixture",False,best,(related,),None,None,"Related subjects may overlap - do not add unit counts."),key="browser")
def profile():
 st.title("Wider-site evidence profile")
 if st.query_params.get("subject_key")=="synthetic-phase-1":
  st.subheader("Originating acquisition subject: Phase 1 - ~100 homes")
  render_mandate_explanation(explanation)
 else:
  st.info("Subject-specific mandate explanation unavailable")
 st.caption("Wider-site evidence is separate from the originating subject assessment.")
profile_page=st.Page(profile,title="Profile",url_path="profile")
st.navigation([st.Page(dashboard,title="Dashboard",default=True),profile_page]).run()
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--chromium', required=True)
    args = parser.parse_args()
    if any(os.environ.get(k) for k in ('DATABASE_URL', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'SUPABASE_URL')):
        raise RuntimeError('Reject inherited production/model configuration')
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='spec028-browser-') as directory:
        script = Path(directory) / 'fixture.py'
        script.write_text(SCRIPT)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = dict(os.environ, PYTHONPATH=str(ROOT), STREAMLIT_BROWSER_GATHER_USAGE_STATS='false')
        process = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', str(script),
            '--server.address=127.0.0.1', f'--server.port={port}', '--server.headless=true',
            '--browser.gatherUsageStats=false'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        url = f'http://127.0.0.1:{port}'
        try:
            for attempt in range(100):
                try:
                    urllib.request.urlopen(url+'/_stcore/health', timeout=1).close()
                    break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError('Offline host did not start')
            observations = []
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=args.chromium,
                    args=['--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--disable-software-rasterizer'])
                context = browser.new_context()
                context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url) else route.abort())
                page = context.new_page()
                for width in (390,768,1366,1920):
                    for zoom in (1,2):
                        page.set_viewport_size({'width':width,'height':1080})
                        page.goto(url)
                        try:
                            page.get_by_text('Possible Mandate Fit', exact=False).first.wait_for(timeout=15000)
                        except Exception:
                            page.screenshot(path=str(output/'failure.png'), full_page=True)
                            print(page.locator('body').inner_text())
                            raise
                        page.locator('body').evaluate('(element,zoom)=>element.style.zoom=zoom', zoom)
                        page.get_by_text('Related acquisition subjects (1)',exact=True).click()
                        page.get_by_text('All recorded matching reasons',exact=True).click()
                        page.get_by_text('Recorded wider-scope reason.',exact=True).wait_for()
                        page.wait_for_timeout(500)  # Wait for native expander animation before geometry/screenshots.
                        assert page.get_by_text('Possible Mandate Fit — classification explanation not fully available',exact=True).is_visible()
                        overflow = page.evaluate('document.documentElement.scrollWidth > window.innerWidth + 2')
                        assert not overflow, (width,zoom,'horizontal overflow')
                        page.evaluate('document.querySelectorAll("*").forEach(element=>element.scrollTop=0)')
                        page.screenshot(path=str(output/f'dashboard-{width}-{zoom}x-top.png'), full_page=True)
                        page.evaluate('document.querySelectorAll("*").forEach(element=>element.scrollTop=element.scrollHeight)')
                        page.screenshot(path=str(output/f'dashboard-{width}-{zoom}x-bottom.png'), full_page=True)
                        (output/f'accessibility-{width}-{zoom}x.txt').write_text(page.locator('body').aria_snapshot())
                        observations.append({'width':width,'zoom':zoom,'overflow':overflow,'related_expansion':'PASS','reason_expansion':'PASS'})
                page.get_by_role('link',name='View opportunity →').click()
                page.get_by_text('Originating acquisition subject: Phase 1 - ~100 homes',exact=True).wait_for()
                page.screenshot(path=str(output/'profile-valid.png'),full_page=True)
                page.goto(url+'/profile?subject_key=tampered')
                page.get_by_text('Subject-specific mandate explanation unavailable',exact=True).wait_for()
                page.screenshot(path=str(output/'profile-invalid.png'),full_page=True)
                page.goto(url)
                page.get_by_text('Possible Mandate Fit',exact=False).first.wait_for()
                # Native summary/link elements remain keyboard operable and labelled.
                summaries = page.locator('summary').count()
                assert summaries >= 2
                page.locator('summary').first.focus()
                assert page.locator('summary').first.evaluate('(element)=>element===document.activeElement')
                page.screenshot(path=str(output/'keyboard-focus.png'),full_page=True)
                page.keyboard.press('Enter')
                assert page.locator('summary').first.evaluate('(element)=>element.parentElement.open')
                browser.close()
            (output/'browser-observations.json').write_text(json.dumps({'result':'PASS','scope':'actual shared renderers in synthetic multipage host; guarded application journeys separately tested','layout':observations,'native_keyboard_expansion':'PASS','labelled_link_navigation':'PASS','invalid_fixture_context':'PASS'},indent=2))
            print('PASS: 8 viewport/zoom layouts, related/full reason expansion, native keyboard expansion, real Streamlit profile link, invalid synthetic context')
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == '__main__':
    main()
