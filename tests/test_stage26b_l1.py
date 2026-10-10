"""Offline synthetic portal templates, not current council evidence."""
from types import SimpleNamespace
import json
import pytest
from app.config import get_council, load_councils
from app.scrapers import idox_portal, arcus_portal
from verification.stage26b_l1.contract import assess, CanaryBudget, FAILURES
from verification.stage26b_l1.selection import build
from verification.stage26b_l0.dependencies import priority_key

@pytest.fixture(autouse=True)
def offline(monkeypatch):
 import socket, requests, subprocess
 def deny(*a,**k):raise AssertionError('Offline network/subprocess denied')
 monkeypatch.setattr(socket.socket,'connect',deny)
 monkeypatch.setattr(requests.sessions.Session,'request',deny)
 monkeypatch.setattr(subprocess,'Popen',deny)
 monkeypatch.setattr(idox_portal.time,'sleep',lambda *a:None)
 import openai
 monkeypatch.setattr(openai.OpenAI,'__init__',deny)
 monkeypatch.setattr(openai.AsyncOpenAI,'__init__',deny)

class Page:
 def __init__(self,ref,found=True):self.url='';self.ref=ref;self.found=found
 def goto(self,url,**kw):self.url=url
 def fill(self,*args):pass
 def click(self,*args):self.url='https://planningpa.oldham.gov.uk/online-applications/applicationDetails.do?keyVal=X' if self.found else 'https://planningpa.oldham.gov.uk/online-applications/search.do'
 def wait_for_load_state(self,*a,**kw):pass
 def content(self):return '<html>No results</html>'
class Session:
 def __init__(self,ref,status,decision='',date=''):self.ref=ref;self.status=status;self.decision=decision;self.date=date;self.calls=[]
 def get(self,url,**kw):
  self.calls.append(url)
  fields={'Reference':self.ref,'Status':self.status,'Decision':self.decision,'Decision Issued Date':self.date,'Proposal':'Residential development of 68 homes'}
  return SimpleNamespace(text='<table>'+''.join(f'<tr><th>{k}</th><td>{v}</td></tr>' for k,v in fields.items())+'</table>',status_code=200,raise_for_status=lambda:None)
@pytest.mark.parametrize('decision,date,expected',[('', '', 'VERIFIED_UNCHANGED'),('Refused','Fri 25 Sep 2026','VERIFIED_MATERIAL_CHANGE'),('Granted','Fri 25 Sep 2026','VERIFIED_MATERIAL_CHANGE'),('Withdrawn','','VERIFIED_MATERIAL_CHANGE')])
def test_actual_idox_reference_parser(decision,date,expected):
 ref='FUL/355686/26' if decision else 'FUL/355201/25';c=get_council('oldham');s=Session(ref,'Awaiting decision' if not decision else 'Decided',decision,date)
 result=idox_portal.fetch_application_by_reference(Page(ref),s,c,ref)
 before={'status':'Awaiting decision','decision':None,'decision_issued_date':None,'status_verified_at':'2026-09-18T05:20:51+00:00'};copy=dict(before)
 assert assess(before,result,reference=ref,base_url=c.base_url)['outcome']==expected
 assert before==copy and len(s.calls)==2

def test_actual_not_found():
 assert idox_portal.fetch_application_by_reference(Page('X',False),Session('X','Awaiting decision'),get_council('oldham'),'X') is None

@pytest.mark.parametrize('outcome',sorted(FAILURES))
def test_failure_never_accepts_or_advances(outcome):
 before={'status':'Awaiting decision','status_verified_at':'2026-09-18'};copy=dict(before)
 out=assess(before,None,reference='X',base_url='https://example.invalid',signal=outcome)
 assert not out['advance_verification'] and out['acceptance_candidate'] is None and before==copy

def candidate(**kw):return SimpleNamespace(reference='X',summary_url='https://example.invalid/a',fields={'Reference':'X','Status':'Awaiting decision','Decision':'',**kw})
@pytest.mark.parametrize('fields,outcome',[({'Status':'garbage'},'PARSER_FAILURE'),({'Status':'Committee resolution','Decision':'Granted'},'AMBIGUOUS_SOURCE_RESULT'),({'Status':'Decided','Decision':'Refused','Decision Issued Date':'garbage'},'PARSER_FAILURE'),({'Status':''},'PARTIAL_RETRIEVAL')])
def test_bad_evidence(fields,outcome):
 assert assess({'status':'Awaiting decision'},candidate(**fields),reference='X',base_url='https://example.invalid')['outcome']==outcome

def test_timestamp_only_and_nonmaterial():
 a={'status':'Awaiting decision','decision':'','decision_issued_date':None,'status_verified_at':'2026-09-10'}
 assert assess(a,candidate(),reference='X',base_url='https://example.invalid')['outcome']=='VERIFIED_UNCHANGED'
 assert assess(a,candidate(Status='Awaiting determination'),reference='X',base_url='https://example.invalid')['outcome']=='VERIFIED_NON_MATERIAL_CHANGE'

@pytest.mark.parametrize('kwargs',[{'response_bytes':10000001,'elapsed':1},{'response_bytes':1,'elapsed':181},{'response_bytes':-1,'elapsed':0}])
def test_budget_aborts(kwargs):
 b=CanaryBudget(['X'])
 with pytest.raises(ValueError):b.charge('X',**kwargs)
 with pytest.raises(ValueError):b.charge('X',response_bytes=0,elapsed=0)

def test_allowlist_request_ceiling():
 b=CanaryBudget(['X'],requests=1);b.charge('X',response_bytes=1,elapsed=1)
 with pytest.raises(ValueError):b.charge('X',response_bytes=1,elapsed=2)
 with pytest.raises(ValueError):CanaryBudget(['A','B','C'])

def test_council_route_existing():
 configs=load_councils();assert len(configs)==10
 for c in configs.values():assert callable((arcus_portal if c.doc_system=='arcus' else idox_portal).fetch_application_by_reference)

def test_real_arcus_detail_parser_without_network(monkeypatch):
 class ArcusPage:
  def __init__(self):self.url=''
  def goto(self,u,**kw):self.url=u
  def wait_for_timeout(self,*a):pass
  def inner_text(self,*a):
   if '/detail/' in self.url:return 'Status\tDecided\nDecision\tRefused\nDecision date\tFri 25 Sep 2026\nApplication type\tDischarge of Conditions'
   return 'Reference\nX\nApplication type\nDischarge of Conditions\nSite address\nFixture\nDescription\nCondition\nStatus\nDecided\nDecision\nRefused\n'
  def eval_on_selector_all(self,*a):return [{'text':'X','href':'https://account.rochdale.gov.uk/pr/s/detail/X'}]
 c=get_council('rochdale');result=arcus_portal.fetch_application_by_reference(ArcusPage(),c,'X')
 assert result.reference=='X' and result.fields['Decision']=='Refused'
 assert assess({'status':'Awaiting decision'},result,reference='X',base_url=c.base_url)['outcome']=='VERIFIED_MATERIAL_CHANGE'

def test_priority_missing_then_oldest():
 base={'cohort':2,'council':'oldham','reference':'X','application_id':1}
 rows=[dict(base,status_verified_at='2026-09-18'),dict(base,status_verified_at=None),dict(base,status_verified_at='2026-09-10')]
 assert [x['status_verified_at'] for x in sorted(rows,key=priority_key)]==[None,'2026-09-10','2026-09-18']

def synthetic_basis():
 direct=[];apps={};risks=[];subjects=[]
 for i in range(1,235):
  fields=['planning_status','decision','decision_issued_date'] if i<=211 else ['qualified_residential_scale']
  ref=f'SYNTHETIC/{i}';apps[i]=dict(id=i,site_id=i,council_code='oldham',reference=ref,status='Awaiting decision',decision=None,decision_issued_date=None,status_verified_at=None)
  direct.append(dict(application_id=i,reference=ref,site_id=i,council='oldham',dependency_type='DIRECT_FACTUAL_DEPENDENCY',supported_fields=fields,consumers=['dashboard'],subject_key=f'synthetic-{i}'))
  risks.append(dict(application_id=i,cohort=1 if i==42 else 2,reasons=['synthetic_fixture']))
  subjects.append(dict(subject_key=f'synthetic-{i}',site_id=i,status_sources=[ref] if i<=211 else []))
 from verification.stage26b_l1.selection import REVIEW_IDS
 for i in REVIEW_IDS-apps.keys():apps[i]=dict(id=i,site_id=i,council_code='oldham',reference=f'SYNTHETIC/{i}')
 return dict(dependencies=direct,risk_cohorts=risks,subjects=subjects),dict(retrieval_state='COMPLETE',dependency_census_state='QUALIFIED',capture={'captured_at':'2026-10-09T17:46:54+00:00','snapshot':'SYNTHETIC'},data={'applications':list(apps.values()),'allocation_site_relationships':[]})

def test_complete_manifest_and_other_fact_separation():
 r,c=synthetic_basis();m=build(r,c)
 assert m['candidate_count']==234 and len(m['status_manifest'])==211
 assert m['other_fact_dispositions']=={'B_OTHER_FACT_DEFERRED':23}
 assert len(m['allocation_review'])==10 and all(not a['request_eligible'] for a in m['allocation_review'])
 assert len(m['unresolved_attribution'])==23 and all(not a['request_eligible'] for a in m['unresolved_attribution'])
 assert m['status_manifest'][0]['application_id']==42
 assert all(row['manifest_version']==m['version'] for row in m['status_manifest'])
 assert build(r,c)==m

@pytest.mark.parametrize('change',['remove_status','reference','duplicate','incomplete'])
def test_selection_fails_closed(change):
 r,c=synthetic_basis()
 if change=='remove_status':r['dependencies'][0]['supported_fields']=['qualified_residential_scale']
 if change=='reference':c['data']['applications'][0]['reference']='DIFFERENT'
 if change=='duplicate':c['data']['applications'].append(c['data']['applications'][0])
 if change=='incomplete':c['retrieval_state']='PARTIAL'
 with pytest.raises(ValueError):build(r,c)

@pytest.mark.parametrize('before,fields,outcome',[
 ({'status':'Awaiting decision'},{'Status':'garbage','Decision':'garbage'},'PARSER_FAILURE'),
 ({'status':'Decided','decision':'Granted','decision_issued_date':'Fri 25 Sep 2026'},{'Status':'Decided'},'PARTIAL_RETRIEVAL'),
 ({'status':'Decided','decision':'Granted','decision_issued_date':'Fri 25 Sep 2026'},{'Status':'Decided','Decision':'Refused','Decision Issued Date':'Thu 24 Sep 2026'},'AMBIGUOUS_SOURCE_RESULT'),
 ({'status':'Awaiting decision'},{'Status':'Appeal pending'},'PARTIAL_RETRIEVAL')])
def test_partial_unknown_older_evidence_does_not_erase(before,fields,outcome):
 out=assess(before,candidate(**fields),reference='X',base_url='https://example.invalid')
 assert out['outcome']==outcome and not out['advance_verification'] and out['acceptance_candidate'] is None

@pytest.mark.parametrize('status,decision',[('Awaiting decision','Granted'),('Pending','Refused'),('Decided','Not granted'),('Decided','Minded to approve'),('Decided','Granted subject to S106'),('Withdrawn','Granted'),('Refused','Granted'),('Approved','Refused')])
def test_b20_negative_authority_cases(status,decision):
 out=assess({'status':'Awaiting decision'},candidate(Status=status,Decision=decision),reference='X',base_url='https://example.invalid')
 assert out['outcome']=='AMBIGUOUS_SOURCE_RESULT' and not out['advance_verification']
