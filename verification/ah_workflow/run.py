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
                  PYTHON_DOTENV_DISABLED='1', PROPERTYAIGENT_AH_SOURCE_CLAIMS='1')
def no_network(event, args):
    if event in ('socket.connect','socket.getaddrinfo'):
        raise RuntimeError('Offline acceptance forbids outbound network')
sys.addaudithook(no_network)

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.db.models import Base, Council, Site, Application, SchemeIntelligence, Document
from app.db.ah_claim_schema import migrate_local
from app.policy.ah_claim_store import import_claim, review_claim, preview, text_hash
from app.enrichment.control_entities import create_control_relationship_if_absent
engine=create_engine(os.environ['DATABASE_URL'])
assert not (OUT/'disposable.sqlite').exists()
Base.metadata.create_all(engine)
# Existing guarded test schema provisioner, only this new disposable file.
migrate_local(engine)
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
            affordable_housing_status='proposed'))
    s.commit(); return a
focus=site(78,'stockport','Focus School'); f=app(focus,'DC/085997',82,72,100,'Granted','2023-08-11')
variation=app(focus,'DC/093884',None,decision='Granted',date='2024-12-06',kind='condition_variation')
south=site(25,'oldham','Southlink'); so=app(south,'FUL/355201/25',147,147,100)
wall=site(32,'oldham','Wall Hill Mill'); wa=app(wall,'OUT/355454/25',26)
hyde=site(107,'stockport','Hyde Stockport'); old=app(hyde,'DC/095922',440,0,0,'Withdrawn','2025-05-22')
hy=app(hyde,'DC/098428',440,date='2026-01-15')
other=site(313,'tameside','Hyde Tameside negative control'); otherapp=app(other,'25/00173/OUT',444,67,15)

SOURCE='https://planning.stockport.gov.uk/PlanningData-live/files/C49A86C04CBC9A23DAE658C0354A907F/pdf/DC_093884-AFFORDABLE_HOUSING_STATEMENT-2378349.pdf'
def document(a,title,date,url,passage):
    d=Document(application_id=a.id,document_name=title,source_url=url,extracted_text=passage)
    s.add(d); s.commit(); return d
fp='Residential development consisting of A) 10 semi-detached houses and B) 72 retirement apartments. The 10 x 4-bed semi-detached houses are proposed to be for open market sale. The retirement apartments are to be 100% affordable (now to be of social rent tenure). Westshield on behalf of Housing 21.'
fd=document(variation,'Affordable Housing Statement — supplied excerpt, local acceptance fixture','2024-10-23',SOURCE,fp)
sp='147 affordable homes: 125 to rent, 11 shared ownership and 11 rent to buy. Reported committee approval; issued decision and obligations not inspected.'
sd=document(so,'Southlink report — local acceptance excerpt','2026-09-24','https://www.placenorthwest.co.uk/vistry-wins-oldham-consent/',sp)
def accept(a,root,d,value,scope,label,date,passage,metric='affordable_count',tenure=None):
    key=f'{a.id}:{metric}:{tenure or "count"}'
    raw=dict(application_id=a.id,site_id=a.site_id,scheme_application_id=root.id,
        scope_kind=scope,scope_key='WHOLE_SCHEME' if scope=='whole_scheme' else 'RETIREMENT',
        scope_label=label,scope_basis='Explicit supplied source scope; offline acceptance only',metric=metric,
        qualifier='exact',value=value,document_id=d.id,document_date=date,passage_text=passage,
        passage_locator='printed page 5 paragraphs 2.1-2.6' if a==variation else 'report body',
        extracted_text_hash=text_hash(d.extracted_text),document_url_snapshot=d.source_url,
        document_title_snapshot=d.document_name,origin_kind='reviewed_import',origin_reference=key,
        created_by='local-acceptance',import_key=key,planning_stage='proposed')
    if tenure: raw['tenure_name']=tenure
    cid=import_claim(engine,raw,apply=True)['id']
    p=preview(engine,[root.id])
    review_claim(engine,dict(claim_id=cid,action='ACCEPT',reason='Local test fixture source/scope checked, not final tenure approval',
        request_key=key,expected_token=p['token'],expected_heads=p['heads'],source_checked=True,scope_checked=True),
        reviewer='local-acceptance',apply=True)
accept(variation,f,fd,72,'component','72 retirement apartments within 82-home scheme','2024-10-23',fp)
accept(variation,f,fd,72,'component','72 retirement apartments within 82-home scheme','2024-10-23',fp,
       'tenure_count','Social rent (applicant proposal; final approved terms uninspected)')
accept(so,so,sd,147,'whole_scheme','Southlink proposed scheme','2026-09-24',sp)
for tenure,value in [('Rent (reported)',125),('Shared ownership',11),('Rent to buy',11)]:
    accept(so,so,sd,value,'whole_scheme','Southlink proposed scheme','2026-09-24',sp,'tenure_count',tenure)
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
    return {typ:[str(e.value) for e in at.get(typ)] for typ in ('markdown','caption','info','warning','metric')}
def table(at):
    return next(d.value for d in at.dataframe if d.key=='sites_table')
def export_selected(at,name):
    d=next(d for d in at.download_button if d.key=='download_selected_report')
    fileid=d.proto.url.rsplit('/',1)[-1].split('.')[0]
    data=stores[-1].get_file(fileid).content
    (OUT/name).write_bytes(data)
    return list(csv.DictReader(io.StringIO(data.decode())))
explore=run(AppTest.from_file(str(ROOT/'app/ui/streamlit_app.py')))
explore.switch_page('pages/0_Explore.py')
run(explore)
(OUT/'explore-initial.json').write_text(json.dumps(values(explore),indent=2))
print('OUT',OUT,flush=True)
for e in explore.checkbox:
    if e.label=='Apply affordable minimum':e.check()
for e in explore.number_input:
    if e.label=='Min affordable units':e.set_value(50)
run(explore)
assert set(table(explore)['Address'])=={'Focus School','Southlink'}
(OUT/'explore-filtered-table.json').write_text(table(explore).to_json(orient='records',indent=2))
(OUT/'explore-filtered.json').write_text(json.dumps(values(explore),indent=2))
explore.session_state['sites_table']={'selection':{'rows':[0,1]}}
run(explore)
exported=export_selected(explore,'selected-50plus.csv')
assert {r['Address'] for r in exported}=={'Focus School','Southlink'}
for e in explore.checkbox:
    if e.label=='Apply affordable minimum':e.uncheck()
explore.session_state['sites_table']={'selection':{'rows':[]}}
run(explore)
selected=[i for i,r in table(explore).reset_index(drop=True).iterrows() if r['Address']!='Hyde Tameside negative control']
explore.session_state['sites_table']={'selection':{'rows':selected}}
run(explore)
exported=export_selected(explore,'selected-records.csv')
assert len(exported)==4
byname={r['Address']:r for r in exported}
assert byname['Focus School']['AH Application']=='DC/093884'
assert byname['Focus School']['AH Qualified']=='True'
assert byname['Focus School']['Affordable %']==''
assert float(byname['Focus School']['Affordable Units'])==72
assert byname['Southlink']['AH Qualified']=='True'
assert float(byname['Southlink']['Affordable Units'])==147
for name,ref in [('Wall Hill Mill','OUT/355454/25'),('Hyde Stockport','DC/098428')]:
    assert byname[name]['AH Qualified']=='False'
    assert byname[name]['AH Application']==ref
    assert byname[name]['Affordable Units']==''
    assert byname[name]['AH Reported Count']==''
print('CSV four selected records emitted and parsed',flush=True)
legacy_rows=[i for i,r in table(explore).reset_index(drop=True).iterrows() if r['Address']=='Hyde Tameside negative control']
assert len(legacy_rows)==1  # Visible without a numeric AH constraint.
explore.session_state['sites_table']={'selection':{'rows':legacy_rows}}
run(explore)
legacy_csv=export_selected(explore,'selected-legacy.csv')[0]
assert float(legacy_csv['AH Reported Count'])==67
assert legacy_csv['Affordable Units']=='' and legacy_csv['AH Qualified']=='False'
assert 'reported; source and scope unverified' in legacy_csv['AH Assessment']


from app.policy.buyer_matching import build_planning_delivery_matching_facts_from_operative, assess_buyer_fit, B2MatchingContext
from app.policy.buyer_profiles import HOUSING_ASSOCIATION,NESTEN_HOMES
from app.policy.buyer_matching_b2_context import build_b2_context_for_planning_delivery, evaluate_buyer_fit
from app.reporting.scheme_reconciliation import build_operative_planning_facts,resolve_operative_filter_facts
from app.reporting.opportunity_intelligence_packet import build_opportunity_intelligence_packet
from app.reporting.opportunity_feed import _attach_planning_delivery_matching_facts
from types import SimpleNamespace
matrix=[]
for sid in (78,25,32,107,313):
    apps=s.scalars(select(Application).where(Application.site_id==sid)).all()
    facts=build_planning_delivery_matching_facts_from_operative(build_operative_planning_facts(apps),apps)
    assessment=facts.affordable_assessment
    context=build_b2_context_for_planning_delivery(s,sid)
    packet=build_opportunity_intelligence_packet(s,SimpleNamespace(opportunity_id=f'planning_delivery:site:{sid}',
        opportunity_type='planning_delivery',kind='site',entity_id=sid,phase_code=None,matching_facts=facts),context=context)
    cards=[{'params':{'site_id':str(sid)}}]
    _attach_planning_delivery_matching_facts(s,cards)
    assert packet.affordable_assessment.payload()==assessment.payload()
    assert cards[0]['matching_facts'].affordable_assessment.payload()==assessment.payload()
    outcome=evaluate_buyer_fit(s,replace(HOUSING_ASSOCIATION,target_unit_max=None),facts,context=context)
    expected='meets' if sid in (78,25) else 'unknown'
    assert assessment.search(minimum=50)==expected
    retirement_outcomes={}
    if sid==78:
        for appetite in ('ACCEPT','EXCLUDE','UNSPECIFIED'):
            fit=evaluate_buyer_fit(s,replace(HOUSING_ASSOCIATION,target_unit_max=None,retirement_appetite=appetite),facts,context=context)
            retirement_outcomes[appetite]=asdict(fit)
        assert retirement_outcomes['ACCEPT']['classification']=='STRONG_FIT'
        assert retirement_outcomes['EXCLUDE']['classification']=='NOT_SUITABLE'
        assert retirement_outcomes['UNSPECIFIED']['classification']=='INSUFFICIENT_EVIDENCE'
        assert any('explicitly accepts retirement' in x for x in retirement_outcomes['ACCEPT']['matches'])
        assert not any('appetite for specialist/retirement' in x for x in retirement_outcomes['ACCEPT']['unknown'])
        excluded=assess_buyer_fit(NESTEN_HOMES,facts)
        assert excluded.classification=='NOT_SUITABLE'
        assert any('specialist' in reason for reason in excluded.does_not_match)
    if sid in (32,107,313):assert assessment.search(maximum=50)=='unknown'
    if sid==313:
        assert assessment.count.value==67 and not assessment.count.qualified
        assert outcome.classification=='INSUFFICIENT_EVIDENCE'
        assert packet.affordable_units.value is None
    matrix.append(dict(site=sid,assessment=assessment.payload(),minimum50=expected,
                       buyer=asdict(outcome),packet=asdict(packet),retirement_outcomes=retirement_outcomes,
                       matching_context=asdict(context),local_mandate=asdict(replace(HOUSING_ASSOCIATION,target_unit_max=None)),
                       independent_exclusion=asdict(excluded) if sid==78 else None))
(OUT/'matching-packets.json').write_text(json.dumps(matrix,indent=2,default=str))
for sid in (78,25,32,107,313):
    detail=explore
    detail.switch_page('pages/1_Scheme_Detail.py')
    detail.query_params['site_id']=str(sid)
    run(detail)
    (OUT/f'detail-{sid}.json').write_text(json.dumps(values(detail),indent=2))
    rendered=json.dumps(values(detail))
    if sid==78:
        assert 'all_units_affordable' not in rendered and 'confidence: high' not in rendered
        assert 'Developer / delivery party stated in document' in rendered
        assert 'Housing association / proposed operator stated in document' in rendered
        assert 'Social rent (applicant proposal; final approved terms uninspected)' in rendered
    if sid==313:
        assert '67' in rendered and 'reported; source and scope unverified' in rendered
    if sid==25:
        assert 'Rent (reported): 125' in rendered and 'Shared ownership: 11' in rendered and 'Rent to buy: 11' in rendered
    if sid in (32,107):assert 'Affordable tenure not identified; affordable housing provision remains unresolved.' in rendered
    print('DETAIL',sid,'OK',flush=True)
print('DONE',OUT,flush=True)
(OUT/'runtime.json').write_text(json.dumps({
    'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
    'working_tree':subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),
    'python':platform.python_version(),
    'dependencies':{name:importlib.metadata.version(name) for name in ('pytest','SQLAlchemy','pandas','streamlit')},
    'mode':'Offline disposable SQLite; real Streamlit AppTest rendering and download media bytes; no HTTP delivery test',
    'code_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in (
        'app/reporting/residential_mix.py','app/reporting/ownership_control.py','verification/ah_workflow/run.py',
        'app/policy/buyer_profiles.py','app/policy/buyer_matching.py','app/policy/ah_assessment.py','app/ui/site_profile_view.py','app/ui/pages/0_Explore.py')}
},indent=2))
(OUT/'checksums.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest()
    for p in OUT.iterdir() if p.is_file() and p.suffix in ('.csv','.json')},indent=2))
