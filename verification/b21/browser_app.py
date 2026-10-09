"""Disposable synthetic renderer only. No production bootstrap/database/model calls."""
import os,sys,datetime as dt
from pathlib import Path
if os.environ.get('B21_BROWSER_REHEARSAL')!='1':raise RuntimeError('Offline browser rehearsal only')
if any(k in os.environ for k in ('DATABASE_URL','OPENAI_API_KEY','ANTHROPIC_API_KEY','SUPABASE_URL','PROPERTYAIGENT_ACCESS_POLICY')):raise RuntimeError('Reject inherited credentials/configuration')
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import streamlit as st
from dataclasses import replace
from app.reporting.planning_freshness import present_planning_freshness
from app.db.models import Application
from app.reporting.family_presentation import FamilyView,SubjectView
from app.ui.shell import opportunity_family_card,render_planning_freshness,inject_global_styles
from app.ui.site_profile_view import _applications_dataframe
st.set_page_config(page_title='B2.1 offline browser rehearsal',layout='wide')
inject_global_styles()
st.title('B2.1 synthetic presentation rehearsal')
st.caption('Disposable rendering fixtures; no production connection, authentication or facts.')
now=dt.datetime(2026,10,9,tzinfo=dt.timezone.utc)
def app(ref,**kw):
    fields=dict(id=1,reference=ref,council_code='synthetic',status='Awaiting decision',decision=None,
        decision_issued_date=None,status_verified_at=None,summary_url=None)
    fields.update(kw);return Application(**fields)
a=app('SYN/REFUSAL',status='Decided',decision='Refused',decision_issued_date='2026-09-25',status_verified_at=dt.datetime(2026,10,8,tzinfo=dt.timezone.utc))
f=present_planning_freshness(a,now=now)
view=SubjectView(label='Residential subject',scale='68 homes',fit_key='POSSIBLE_FIT',fit_label='Possible Mandate Fit',investigative=False,reasons=(),headline_reason=None,signal_key=None,signal_label=None,metrics=(),tags=(),page=None,params={},planning_freshness=(('Subject',a.reference,f),))
legacy=replace(view,label='Related subject — legacy missing verification',planning_freshness=(('Related scope','SYN/LEGACY',present_planning_freshness(app('SYN/LEGACY'),now=now)),))
conflict=replace(view,label='Related subject — conflict',planning_freshness=(('Related scope','SYN/CONFLICT',replace(f,freshness='conflicting',qualification='Source conflict requires review. The accepted planning fact is retained; current verification is unavailable for this exact subject. '+('Long synthetic qualification to test wrapping and readable disclosure. '*8))),))
opportunity_family_card(FamilyView('synthetic','Synthetic development','Exact-source freshness',False,view,(legacy,conflict),None,'Related acquisition subjects within this development.',None),key='b21')
st.subheader('Profile planning history')
render_planning_freshness(view.planning_freshness)
st.dataframe(_applications_dataframe([a,app('SYN/LEGACY')]),hide_index=True)
