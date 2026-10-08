"""Bounded offline walkthrough of real Streamlit pages and emitted CSV bytes.

Run with env -i and the dedicated test interpreter; never a production runner.
Creates its own SQLite file. No existing database or repository .env is used.
"""
import os
import sys
from pathlib import Path
import tempfile
import json
import csv
import io
import datetime as dt
import hashlib
import importlib.metadata
import platform
import subprocess
from dataclasses import asdict, replace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
if any(k in os.environ for k in ('DATABASE_URL','OPENAI_API_KEY','ANTHROPIC_API_KEY','SUPABASE_URL')):
    raise RuntimeError('Reject inherited database/model inputs; run under env -i')
if any(p for p in ROOT.glob('.env*') if p.name != '.env.example'):
    raise RuntimeError('Reject repository environment files')
OUT = Path(tempfile.mkdtemp(prefix='ah-buyer-walkthrough-'))
os.environ.update(DATABASE_URL='sqlite:///' + str(OUT/'disposable.sqlite'),
                  PYTHON_DOTENV_DISABLED='1')
def no_network(event, args):
    if event in ('socket.connect','socket.getaddrinfo'):
        raise RuntimeError('Offline acceptance forbids outbound network')
sys.addaudithook(no_network)

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.db.models import Base, Council, Site, Application, SchemeIntelligence, Document
from app.enrichment.control_entities import create_control_relationship_if_absent
engine=create_engine(os.environ['DATABASE_URL'])
assert not (OUT/'disposable.sqlite').exists()
Base.metadata.create_all(engine)
# Existing guarded test schema provisioner, only this new disposable file.

s=Session(engine, expire_on_commit=False)
for council in ('stockport','oldham','tameside'):
    s.add(Council(code=council,name=council,base_url='https://example.invalid',date_field_mode='received',doc_system='idox'))
s.commit()
def site(sid,council,address):
    row=Site(id=sid,council_code=council,canonical_address=address,display_address=address)
    s.add(row); s.flush(); return row
def app(site,ref,total,ah=None,pct=None,decision=None,date='2026-01-01',kind='full'):
    a=Application(council_code=site.council_code,reference=ref,site_id=site.id,
        status='Decided' if decision else 'Awaiting decision',decision=decision,
        decision_issued_date=date if decision else None,application_received=date,
        application_category=kind,application_type='Full Application' if kind=='full' else 'Variation of Condition',
        proposal=f'Residential development of {total or 82} homes')
    s.add(a); s.flush()
    if total is not None:
        s.add(SchemeIntelligence(application_id=a.id,total_units_final=total,affordable_units_final=ah,
            affordable_percentage_final=pct,core_intelligence_complete=True,unit_reconciliation_status='OK',
            affordable_classification_confidence='high', affordable_data_status='all_units_affordable' if pct==100 else None,
            development_type='mixed_retirement_and_market_housing' if site.id==78 else 'houses',
            affordable_housing_status='legally_secured' if site.id==78 else 'proposed'))
    s.commit(); return a
focus=site(78,'stockport','Focus School'); f=app(focus,'DC/085997',82,72,100,'Granted','2023-08-11')
focus.status_summary='72 affordable retirement apartments legally secured; whole scheme 100% affordable.'
focus.status_summary_updated_at=dt.datetime(2026,9,2)
s.commit()
variation=app(focus,'DC/093884',None,decision='Granted',date='2024-12-06',kind='condition_variation')
south=site(25,'oldham','Southlink'); so=app(south,'FUL/355201/25',147,147,100)
wall=site(32,'oldham','Wall Hill Mill'); wa=app(wall,'OUT/355454/25',26)
hyde=site(107,'stockport','Hyde Stockport'); old=app(hyde,'DC/095922',440,0,0,'Objection (Consult with Neighbour Auth)','2025-05-22')
old.status='Unknown'; old.application_type=None
old.scheme_intelligence.affordable_housing_status='unknown'
hy=app(hyde,'DC/098428',None,decision='Objection (Consult with Neighbour Auth)',date='2026-02-24')
hy.status='Unknown'; hy.application_type=None
s.commit()
other=site(313,'tameside','Hyde Tameside negative control'); otherapp=app(other,'25/00173/OUT',444,67,15)

SOURCE='https://planning.stockport.gov.uk/PlanningData-live/files/C49A86C04CBC9A23DAE658C0354A907F/pdf/DC_093884-AFFORDABLE_HOUSING_STATEMENT-2378349.pdf'
def document(a,title,date,url,passage):
    d=Document(application_id=a.id,document_name=title,source_url=url,extracted_text=passage)
    s.add(d); s.commit(); return d
fp='Residential development consisting of A) 10 semi-detached houses and B) 72 retirement apartments. The 10 x 4-bed semi-detached houses are proposed to be for open market sale. The retirement apartments are to be 100% affordable (now to be of social rent tenure). Westshield on behalf of Housing 21.'
fd=document(variation,'Affordable Housing Statement — supplied excerpt, local acceptance fixture','2024-10-23',SOURCE,fp)
sp='147 affordable homes: 125 to rent, 11 shared ownership and 11 rent to buy. Reported committee approval; issued decision and obligations not inspected.'
sd=document(so,'Southlink report — local acceptance excerpt','2026-09-24','https://www.placenorthwest.co.uk/vistry-wins-oldham-consent/',sp)
for name,role,category,snippet in [
    ('Westshield','DEVELOPER','DOCUMENT_DELIVERY_PARTY','Statement 23 October 2024: Westshield would develop on behalf of Housing 21; not current ownership or availability.'),
    ('Housing 21','OTHER','DOCUMENT_PROPOSED_OPERATOR','Statement 23 October 2024: Housing 21 is the proposed retirement-housing operator; not a current buyer mandate or stock availability.')]:
    create_control_relationship_if_absent(s,entity_name_raw=name,role=role,evidence_basis='document_statement',
        evidence_category=category,extraction_method='manual',application_id=variation.id,site_id=78,
        evidence_document_id=fd.id,evidence_snippet=snippet,evidence_date=dt.datetime(2024,10,23),review_status='confirmed')
s.commit()

from streamlit.testing.v1 import AppTest
from streamlit.runtime.memory_media_file_storage import MemoryMediaFileStorage
stores=[]
def storage(*a,**kw):
    obj=MemoryMediaFileStorage(*a,**kw); stores.append(obj); return obj
def run(at):
    with patch('streamlit.testing.v1.app_test.MemoryMediaFileStorage',side_effect=storage):
        at.run(timeout=30)
    if at.exception:
        raise RuntimeError(str([(e.message,e.stack_trace) for e in at.exception]))
    return at
def values(at):
    return {'page_links': [str(e.proto) for e in at.get('page_link')], **{typ:[str(e.value) for e in at.get(typ)] for typ in ('markdown','caption','info','warning','metric','json')}}
def table(at):
    return next(d.value for d in at.dataframe if str(d.key).startswith('sites_table_'))
def export_selected(at,name,key='download_selected_report'):
    d=next(d for d in at.download_button if d.key==key)
    fileid=d.proto.url.rsplit('/',1)[-1].split('.')[0]
    data=stores[-1].get_file(fileid).content
    (OUT/name).write_bytes(data)
    rows = list(csv.DictReader(io.StringIO(data.decode())))
    internal = {'AH Explicit Tenure Claims', 'AH Conflicting Claims', 'AH Source Claims', 'AH Claim Relationships'}
    assert rows and not internal.intersection(rows[0]), 'Machine claim JSON must not reach buyer CSV'
    assert {'AH Assessment', 'AH Source', 'AH Application', 'AH Reported Count'} <= set(rows[0])
    return rows
explore=run(AppTest.from_file(str(ROOT/'app/ui/streamlit_app.py')))
dashboard_text=json.dumps(values(explore))
(OUT/'dashboard.json').write_text(dashboard_text)
assert 'DC/085997' in dashboard_text
assert 'Reported AH count: 72' in dashboard_text
assert 'legally_secured' not in dashboard_text
assert 'Historical AI output' in dashboard_text and 'unverified' in dashboard_text
assert any(e.label=='Read historical narrative (unverified)' and not e.proto.expanded for e in explore.expander)
explore.switch_page('pages/0_Explore.py')
run(explore)
(OUT/'explore-initial.json').write_text(json.dumps(values(explore),indent=2))
print('OUT',OUT,flush=True)
# This release reads the existing schema only. Source text is preserved, but
# cannot magically become a reviewed count-level claim in this release.
assert set(table(explore)['Address']) == {'Focus School','Southlink','Wall Hill Mill','Hyde Stockport','Hyde Tameside negative control'}
initial_table=table(explore)
all_rows=export_selected(explore,'all-filtered.csv','download_all_filtered_report')
assert len(all_rows)==5
(OUT/'explore-table.json').write_text(initial_table.to_json(orient='records', default_handler=str))
focus_row=initial_table[initial_table['Address']=='Focus School'].iloc[0]
assert 'operative terms unverified' in str(focus_row.to_dict())
assert 'legally_secured' not in str(focus_row.to_dict())
# Exact previously missed branch: one selected row opens common.render_scheme_detail.
focus_index=next(i for i,r in table(explore).reset_index(drop=True).iterrows() if r['Address']=='Focus School')
explore.session_state[next(d.key for d in explore.dataframe if str(d.key).startswith('sites_table_'))]={'selection':{'rows':[focus_index]}}
run(explore)
inline=json.dumps(values(explore)); (OUT/'explore-single-focus.json').write_text(inline)
# Spec 023 withholds this unversioned inline narrative until reviewed.
# Preserve the AH safeguard by proving the unsupported claim is not rendered.
assert 'Stored narrative requires review against the commercial evidence contract before reuse' in inline
assert '72 affordable retirement apartments legally secured; whole scheme 100% affordable.' not in inline
assert not any(e.label=='Read historical narrative (unverified)' for e in explore.expander)
assert 'reported; source and scope unverified' in inline
assert 'operative terms unverified' in inline
assert 'AH source link: not available' in inline
assert '**Affordable %:**' not in inline
assert '**Total / Affordable / Private units:**' not in inline
assert 'built from evidence already verified' not in inline
assert not explore.get('json')
single=export_selected(explore,'single-focus.csv')
assert len(single)==1 and single[0]['AH Application']=='DC/085997'
assert float(single[0]['AH Reported Count'])==72 and single[0]['Affordable Units']==''
hyde_index=next(i for i,r in table(explore).reset_index(drop=True).iterrows() if r['Address']=='Hyde Stockport')
explore.session_state[next(d.key for d in explore.dataframe if str(d.key).startswith('sites_table_'))]={'selection':{'rows':[hyde_index]}}
run(explore)
hyde_inline=json.dumps(values(explore)); (OUT/'explore-single-hyde.json').write_text(hyde_inline)
hyde_csv=export_selected(explore,'single-hyde.csv')
assert hyde_csv[0]['AH Application']=='DC/098428'
assert hyde_csv[0]['AH Reported Count']=='' and hyde_csv[0]['Affordable Units']==''
assert '0 affordable homes' not in hyde_csv[0]['AH Assessment']
assert 'DC/095922' in hyde_csv[0]['Other application AH reports (not current)']
assert '0 affordable homes' in hyde_csv[0]['Other application AH reports (not current)']
assert 'Other application AH evidence' in [e.label.split(' —')[0] for e in explore.expander]
selected=[i for i,r in table(explore).reset_index(drop=True).iterrows() if r['Address']!='Hyde Tameside negative control']
explore.session_state[next(d.key for d in explore.dataframe if str(d.key).startswith('sites_table_'))]={'selection':{'rows':selected}}
run(explore)
rows=export_selected(explore,'selected-records.csv')
assert len(rows)==4
byname={r['Address']:r for r in rows}
for r in rows:
    assert r['Affordable Units']=='' and r['Affordable %']=='' and r['AH Qualified']=='False'
assert float(byname['Focus School']['AH Reported Count'])==72
assert float(byname['Southlink']['AH Reported Count'])==147
assert byname['Focus School']['AH Application']=='DC/085997'
assert byname['Focus School']['AH Stage']=='Reported AH status: legally secured; operative terms unverified'
assert 'legally_secured' not in byname['Focus School']['AH Assessment']
for name in ('Wall Hill Mill','Hyde Stockport'):
    assert byname[name]['AH Reported Count']==''
assert byname['Hyde Stockport']['AH Application']=='DC/098428'
assert float(byname['Wall Hill Mill']['Total Units'])==26
assert '67' not in byname['Hyde Stockport']['AH Assessment']
# Shrinking to a different nonempty set must clear a still-in-range old offset.
before_first=table(explore).iloc[0]['Address']
old_key=next(d.key for d in explore.dataframe if str(d.key).startswith('sites_table_'))
explore.session_state[old_key]={'selection':{'rows':[0]}}
run(explore)
for e in explore.multiselect:
    if e.label=='Council':e.set_value(['stockport'])
run(explore)
assert len(table(explore))==2
assert table(explore).iloc[0]['Address']!=before_first  # same offset, different site
assert not any(d.key=='download_selected_report' for d in explore.download_button)
new_key=next(d.key for d in explore.dataframe if str(d.key).startswith('sites_table_'))
assert new_key!=old_key
assert 'Other application AH evidence — not applied to this record' not in [e.label for e in explore.expander]
explore.session_state[new_key]={'selection':{'rows':[0,1]}}
run(explore)
reselected=export_selected(explore,'reselected-after-filter.csv')
assert {r['Address'] for r in reselected}=={'Focus School','Hyde Stockport'}
for e in explore.multiselect:
    if e.label=='Council':e.set_value(['stockport','oldham','tameside'])
run(explore)
assert not any(d.key=='download_selected_report' for d in explore.download_button)
# Re-select before the minimum produces zero rows: no stale .iloc access/export.
key=next(d.key for d in explore.dataframe if str(d.key).startswith('sites_table_'))
explore.session_state[key]={'selection':{'rows':[0,4]}}
run(explore)
for e in explore.checkbox:
    if e.label=='Apply affordable minimum':e.check()
for e in explore.number_input:
    if e.label=='Min affordable units':e.set_value(50)
run(explore)
assert not any(str(d.key).startswith('sites_table_') and len(d.value) for d in explore.dataframe)
assert not any(d.key=='download_selected_report' for d in explore.download_button)
for e in explore.multiselect:
    if e.label=='AH evidence results':e.set_value(['unknown'])
run(explore)
assert len(table(explore))==5
assert all('unknown' in r for r in table(explore)['Affordable'])
# Single selection before maximum-zero; this offset was valid in the old results.
hyde_index=next(i for i,r in table(explore).reset_index(drop=True).iterrows() if r['Address']=='Hyde Stockport')
key=next(d.key for d in explore.dataframe if str(d.key).startswith('sites_table_'))
explore.session_state[key]={'selection':{'rows':[hyde_index]}}
run(explore)
assert any(d.key=='download_selected_report' for d in explore.download_button)
for e in explore.checkbox:
    if e.label=='Apply affordable minimum':e.uncheck()
    if e.label=='Apply affordable maximum':e.check()
for e in explore.number_input:
    if e.label=='Max affordable units':e.set_value(0)
for e in explore.multiselect:
    if e.label=='AH evidence results':e.set_value(['meets','likely_meets'])
run(explore)
assert not any(str(d.key).startswith('sites_table_') and len(d.value) for d in explore.dataframe)
assert not any(d.key=='download_selected_report' for d in explore.download_button)
for sid in (78,25,32,107):
    detail=AppTest.from_file(str(ROOT/'app/ui/streamlit_app.py'))
    run(detail);detail.switch_page('pages/1_Scheme_Detail.py');detail.query_params['site_id']=str(sid);run(detail)
    rendered=json.dumps(values(detail));(OUT/f'detail-{sid}.json').write_text(rendered)
    assert 'confidence: high' not in rendered and 'all_units_affordable' not in rendered
    assert 'Not applicable - no affordable homes' not in rendered
    if sid in (32,78,107):
        ah_tiles=[block for block in detail.get('flex_container') if any(c.value=='Affordable homes' for c in block.get('caption')) and len(block.get('markdown'))==1]
        assert ah_tiles and all('>N/A</div>' in block.get('markdown')[0].value for block in ah_tiles)
    if sid==32:
        # CountAssessment supplies discovery scale; planning state stays separate.
        assert any('>26 homes</div>' in x for x in values(detail)['markdown'])
        assert any('Awaiting decision' in x for x in values(detail)['markdown'])
        assert not any('Permission granted' in x for x in values(detail)['markdown'])
    if sid==107:
        # New portal-only 82-home proposal must not steal the attribution of
        # the old extracted 440 count, nor inherit that application's 0 AH.
        assert any('>440 homes</div>' in x for x in values(detail)['markdown'])
        assert not any('>82 homes</div>' in x for x in values(detail)['markdown'])
        assert 'stockport \u00b7 DC/098428' in '\n'.join(values(detail)['caption'])
        assert 'Current preferred version: **DC/098428**' in '\n'.join(values(detail)['caption'])
        assert 'Source application: DC/095922' in '\n'.join(values(detail)['caption'])
        assert 'Residential extraction source for totals, housing type and density: DC/095922' in '\n'.join(values(detail)['caption'])
        assert 'Source application: DC/098428' not in '\n'.join(values(detail)['caption'])
        assert '0 affordable homes' not in next(x for x in values(detail)['markdown'] if 'unknown affordable homes' in x)
    if sid==78:
        assert any('>N/A</div>' in x for x in values(detail)['markdown'])
        assert not any('font-size:1.35rem' in x and 'reported;' in x for x in values(detail)['markdown'])
        assert 'reported; source and scope unverified' in rendered
        assert 'Reported AH status: legally secured; operative terms unverified' in rendered
        assert 'legally_secured' not in rendered
        assert not detail.get('json'), 'No internal assessment JSON on the buyer page'
        assert 'Final approved conditions and tenure terms require checking' in rendered
        assert 'Westshield' in rendered and 'Housing 21' in rendered
        assert 'No applicant/developer organisation identified' not in rendered
        assert 'No applicant/developer/landowner names extracted' not in rendered
        assert 'Document-backed roles are shown separately when recorded.' in rendered
        assert 'Developer / delivery party stated in document' in rendered
        assert 'Housing association / proposed operator stated in document' in rendered
cards = run(AppTest.from_string("""
from types import SimpleNamespace
from app.ui.shell import _scheme_stack_card, opportunity_feed_card
_scheme_stack_card(dict(reference='FIXTURE', total_units=82, affordable_units=72, affordable_percentage=100), rank=1, key='scope')
opportunity_feed_card(dict(id='fixture', title='Fixture', subtitle='Existing policy', buyer_fit=SimpleNamespace(classification='STRONG_FIT',matches=['72 affordable units meet the minimum'])),key='fit')
"""))
card_text=json.dumps(values(cards));(OUT/'cards.json').write_text(card_text)
assert '100% affordable' not in card_text
assert 'Reported AH percentage: 100% (scope unverified)' in card_text
assert 'Strong Mandate Fit' in card_text
assert 'does not verify AH count source or scope' in card_text
# Shared evidence renderer exercised with qualified/source-bounded and conflicting inputs.
qualified = run(AppTest.from_string("""
import streamlit as st
from dataclasses import replace
from app.policy.ah_assessment import AHAssessment, AHClaim
from app.ui.ah_evidence import render_ah_evidence
base=AHClaim(value=72, qualifier='exact', state='verified', application_reference='Q/1',
 scope_type='whole_site', scope_label='Whole Q/1 scheme', document_id='q1',
 source_url='https://example.invalid/q1.pdf', document_date='2024-10-23', passage='72 affordable homes')
for assessment in (AHAssessment(count=base), AHAssessment(count=replace(base, value=None)),
 AHAssessment(count=replace(base, state='conflicting'), alternatives=(base, replace(base,value=74))),
 AHAssessment(count=replace(base, qualifier='at_least',value=None,lower=70)),
 AHAssessment(count=replace(base, scope_type='component',scope_label='Retirement component'))):
 st.caption(assessment.label())
 render_ah_evidence(assessment)
"""))
qt=json.dumps(values(qualified)); (OUT/'qualified-presentations.json').write_text(qt)
assert 'View reported AH source' in qt and 'https://example.invalid/q1.pdf' in qt
assert 'Retirement component' in qt and '74' in qt
assert not qualified.get('json')
# Actual Streamlit selection replay for a server result reorder, same IDs and
# still-valid offsets. Uses the production helper with production-shaped IDs.
reorder = run(AppTest.from_string("""
import streamlit as st
import pandas as pd
from app.ui.explore_selection import selection_widget_key, selected_site_ids
ids=st.session_state.get('fixture_order',[78,25,32])
key=selection_widget_key(st.session_state,ids)
event=st.dataframe(pd.DataFrame({'site_id':ids}),key=key,on_select='rerun',selection_mode='multi-row')
selected=selected_site_ids(ids,event['selection']['rows'])
if selected:
 st.caption('Selected site IDs: '+','.join(map(str,selected)))
 st.download_button('Selected fixture CSV',pd.DataFrame({'Site ID':selected}).to_csv(index=False).encode(),key='reorder_csv')
"""))
def reorder_key():
    return next(d.key for d in reorder.dataframe if str(d.key).startswith('sites_table_'))
key_a=reorder_key();reorder.session_state[key_a]={'selection':{'rows':[0]}};run(reorder)
assert 'Selected site IDs: 78' in values(reorder)['caption']
reorder.session_state['fixture_order']=[25,78,32];run(reorder)
assert reorder_key()!=key_a and not reorder.download_button
reorder.session_state['fixture_order']=[78,25,32];run(reorder)
assert reorder_key()!=key_a and not reorder.download_button
reorder.session_state[reorder_key()]={'selection':{'rows':[1]}};run(reorder)
assert 'Selected site IDs: 25' in values(reorder)['caption']
d=next(d for d in reorder.download_button if d.key=='reorder_csv')
fileid=d.proto.url.rsplit('/',1)[-1].split('.')[0]
reorder_bytes=stores[-1].get_file(fileid).content
(OUT/'reordered-reselection.csv').write_bytes(reorder_bytes)
assert list(csv.DictReader(io.StringIO(reorder_bytes.decode())))==[{'Site ID':'25'}]
print('PASS: actual Explore/detail rendering, reported counts, min/max unknown exclusion, investigation route, and selected CSV bytes',flush=True)
(OUT/'result.json').write_text(json.dumps({'candidate':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'csv_rows':len(rows),'schema':'unchanged production-baseline ORM; no AH/P0A/revisit additions','limits':'AppTest media bytes, not browser HTTP delivery; legacy inputs not source-qualified production claims'},indent=2))
print('DONE',OUT,flush=True)
