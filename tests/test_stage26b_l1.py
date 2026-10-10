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
   if '/detail/' in self.url:return 'Status\tDecided\nDecision\tRefused\nDecision date\t25 September 2026\nApplication type\tDischarge of Conditions'
   return 'Reference\nX\nApplication type\nDischarge of Conditions\nSite address\nFixture\nDescription\nCondition\nStatus\nDecided\nDecision\nRefused\n'
  def eval_on_selector_all(self,*a):return [{'text':'X','href':'https://account.rochdale.gov.uk/pr/s/detail/X'}]
 c=get_council('rochdale');result=arcus_portal.fetch_application_by_reference(ArcusPage(),c,'X')
 assert result.reference=='X' and result.fields['Decision']=='Refused'
 assert assess({'status':'Awaiting decision'},result,reference='X',base_url=c.base_url)['outcome']=='VERIFIED_MATERIAL_CHANGE'

def test_priority_missing_then_oldest():
 base={'cohort':2,'council':'oldham','reference':'X','application_id':1}
 rows=[dict(base,status_verified_at='2026-09-18'),dict(base,status_verified_at=None),dict(base,status_verified_at='2026-09-10')]
 assert [x['status_verified_at'] for x in sorted(rows,key=priority_key)]==[None,'2026-09-10','2026-09-18']
