from dataclasses import replace
from datetime import date
from copy import deepcopy
import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.ingestion.ledger import Ledger,Denied,UncertainPersistence,DEFAULT_LIMITS
from app.ingestion.schema import install,WorkItem as W
from app.ingestion.coordinator import Coordinator
from app.ingestion.idox_adapter import IdoxListingContract
from app.ingestion.new_identity import NewIdentityContract
from tests.test_discovery_admission import engine,envelope
from tests.test_discovery_idox_window import perform,page,FORM
from verification.discovery.idox_window import WindowConfig
from tests.test_discovery_ingestion_ledger import outer
from tests.test_discovery_initial_application_contract import projected
from verification.direct_reference.fixtures import summary
from app.db.models import Application
from app.config import get_council


def audit(config=None):
 config=config or WindowConfig(max_transport_retries=0)
 echo=FORM.replace(b'name="date(applicationReceivedStart)" value=""',b'name="date(applicationReceivedStart)" value="28/09/2026"').replace(b'name="date(applicationReceivedEnd)" value=""',b'name="date(applicationReceivedEnd)" value="04/10/2026"')
 echo=echo.replace(b'28/09/2026',config.start.strftime('%d/%m/%Y').encode()).replace(b'04/10/2026',config.end.strftime('%d/%m/%Y').encode())
 body=page().replace(b'Mon 28 Sep 2026',config.start.strftime('%a %d %b %Y').encode())
 from tests.test_discovery_idox_window import Response
 from verification.discovery.idox_window import run
 bodies=iter([FORM,body,body,echo])
 return run(lambda *a,**k:Response(next(bodies)),config)


def test_idox_contract_projection_screening_and_current_historical_same_path(engine):
 install(engine);l=Ledger(engine)
 for start,end in [(date(2026,9,28),date(2026,10,4)),(date(2026,10,12),date(2026,10,18))]:
  config=WindowConfig('bolton','RECEIVED',start,end,0);a=audit(config)
  contract=IdoxListingContract('bolton-idox-qualified-v1',config,'a'*64)
  # Different configured windows, exactly the same parser projection/coordinator.
  key=l.enqueue(dict(kind='DISCOVERY_SCOPE',council='bolton',start=start.isoformat(),end=end.isoformat(),semantics='RECEIVED'),'DISCOVERY',contract=contract.name)
  authority='INGESTION_TEST_'+start.isoformat();l.grant(authority,[key],contracts=[contract.name],expires_at=l.clock()+600)
  co=Coordinator(l,{contract.name:contract});children=co.idox_listing(l.claim(key,'worker',authority),a,outer())
  assert len(children)==2 and l.get(key)['state']=='COMPLETE'
  retained=l.get(key)['checkpoint'];assert retained['records'][0]['fields']['application_type']['state']=='UNKNOWN'
  assert retained['records'][0]['provenance']['body_sha256']==a['pages'][0]['body_sha256']
  assert retained['resources']['metric']=='EXISTING_IDOX_RECEIVED_BODY_BYTES'
  # Historical and current repeated identity does not duplicate a screening task
  # when metadata revision changes only by source-observation provenance.
  for child in children:assert l.get(child)['task']=='SCREENING'


@pytest.mark.parametrize('field',['capped','cleanup','identity','criteria','retries'])
def test_idox_adapter_fail_closed(engine,field):
 c=IdoxListingContract('fixture',WindowConfig(max_transport_retries=0),'a'*64);a=audit()
 if field=='capped':a['capped']=True
 elif field=='cleanup':a['cleanup']='UNKNOWN'
 elif field=='identity':a['records'][0]['reference']=None
 elif field=='criteria':a['criteria_result_binding']['criteria_sha256']='b'*64
 else:a['resource']['retries']=1
 with pytest.raises(Denied):c.project(a,outer(),DEFAULT_LIMITS)


def setup_new(engine,*,supported=True):
 install(engine);l=Ledger(engine);target,raw,packet=projected(summary('01780/26',status='Decided',decision='Approve',date='Mon 28 Sep 2026') if supported else summary('01780/26',status='Awaiting decision',omit=('Decision','Decision Issued Date')))
 e=replace(envelope(),reference=target['reference'],displayed_references=(target['reference'],),source_url=target['source_url'],source_record_id=target['source_identifier'])
 parent=l.enqueue(dict(kind='APPLICATION',council='bolton',reference=e.reference),'SCREENING',contract='fixture-screen')
 l.grant('INGESTION_TEST_screen',[parent],contracts=['fixture-screen'],expires_at=l.clock()+600)
 claim=l.claim(parent,'screen','INGESTION_TEST_screen')
 l.checkpoint(claim,dict(disposition='SUPPORTED_PROCESSING_PRIORITY',source_url=e.source_url,source_record_id=e.source_record_id));l.finish(claim,{'outcome':'SCREENED'})
 contract=NewIdentityContract('bolton-existing-coupled-new',target)
 key=l.enqueue(dict(kind='APPLICATION',council='bolton',reference=e.reference),'FACTUAL_REFRESH',contract=contract.name,dependencies=[parent])
 l.grant('INGESTION_TEST_new',[key],contracts=[contract.name],expires_at=l.clock()+600,writes=2)
 return l,Coordinator(l,{contract.name:contract}),key,e,raw


def test_selective_new_shared_admission_b2_and_no_duplicate_effect(engine):
 l,co,k,e,raw=setup_new(engine)
 result=co.new_identity(l.claim(k,'worker','INGESTION_TEST_new'),envelope=e,council=get_council('bolton'),source=raw)
 assert result['outcome']=='SUPPORTED_FACTS_VERIFIED' and result['unit_facts']=='NOT_WRITTEN'
 with Session(engine) as s:
  assert s.scalar(select(func.count()).select_from(Application))==1
  a=s.scalar(select(Application));assert a.estimated_unit_count is None and a.site_id is None and a.status_verified_at is not None
 with pytest.raises(Denied):l.claim(k,'duplicate','INGESTION_TEST_new')


def test_unsupported_source_never_creates_pending_application(engine):
 l,co,k,e,raw=setup_new(engine,supported=False)
 result=co.new_identity(l.claim(k,'worker','INGESTION_TEST_new'),envelope=e,council=get_council('bolton'),source=raw)
 assert result['identity']=='NOT_CREATED' and l.get(k)['state']=='UNSUPPORTED_CONTRACT'
 with Session(engine) as s:assert s.scalar(select(func.count()).select_from(Application))==0


def test_existing_identity_is_preserved_without_source_projection(engine):
 l,co,k,e,raw=setup_new(engine)
 with Session(engine) as s:s.add(Application(council_code='bolton',reference=e.reference,status='PRESERVED'));s.commit()
 result=co.new_identity(l.claim(k,'worker','INGESTION_TEST_new'),envelope=e,council=get_council('bolton'),source={})
 assert result['outcome']=='ALREADY_KNOWN'
 with Session(engine) as s:assert s.scalar(select(Application)).status=='PRESERVED'


def test_new_identity_commit_uncertainty_stops_following_work(engine,monkeypatch):
 l,co,k,e,raw=setup_new(engine);claim=l.claim(k,'worker','INGESTION_TEST_new');original=Session.commit
 def lost(s):original(s);raise RuntimeError('lost commit acknowledgement')
 monkeypatch.setattr(Session,'commit',lost)
 with pytest.raises(UncertainPersistence):co.new_identity(claim,envelope=e,council=get_council('bolton'),source=raw)
 assert l.get(k)['phase']=='WRITE_INTENT'
 with Session(engine) as s:assert s.scalar(select(func.count()).select_from(Application))==1


def test_idox_source_intent_supervised_receipt_and_no_replay(engine):
 install(engine);l=Ledger(engine);config=WindowConfig(max_transport_retries=0);contract=IdoxListingContract('idox-source-fixture',config,'a'*64)
 key=l.enqueue(dict(kind='DISCOVERY_SCOPE',council='bolton',start=config.start.isoformat(),end=config.end.isoformat(),semantics='RECEIVED'),'DISCOVERY',contract=contract.name)
 l.grant('INGESTION_TEST_source',[key],contracts=[contract.name],source_calls=1,expires_at=l.clock()+600)
 co=Coordinator(l,{contract.name:contract});claim=l.claim(key,'worker','INGESTION_TEST_source');calls=[]
 def reader(row):calls.append(row['key']);return audit(config),outer()
 assert len(co.idox_source(claim,reader))==2 and calls==[key]
 with pytest.raises(Denied):co.idox_source(claim,reader)
 assert calls==[key]


def test_new_identity_recovery_uses_committed_receipt_without_admission_or_source_replay(engine,monkeypatch):
 l,co,k,e,raw=setup_new(engine);clock=[l.clock()];l.clock=lambda:clock[0];claim=l.claim(k,'worker','INGESTION_TEST_new');finish=l.finish
 def crash(*a,**kw):raise RuntimeError('after durable fact checkpoint')
 monkeypatch.setattr(l,'finish',crash)
 with pytest.raises(RuntimeError,match='durable'):co.new_identity(claim,envelope=e,council=get_council('bolton'),source=raw)
 receipt=l.get(k)['checkpoint'];assert receipt['outcome']=='SUPPORTED_FACTS_VERIFIED'
 clock[0]+=121;l.recover(claim,cleanup_closed=True);new=l.claim(k,'replacement','INGESTION_TEST_new');monkeypatch.setattr(l,'finish',finish)
 def no_commit(*a):pytest.fail('recovery must not repeat admission/B2')
 monkeypatch.setattr(Session,'commit',no_commit)
 result=co.new_identity(new,envelope=e,council=get_council('bolton'),source={})
 assert result==receipt and l.get(k)['state']=='COMPLETE'


def test_claimed_eligibility_cannot_bypass_existing_b2_gate_before_admission(engine,monkeypatch):
 l,co,k,e,raw=setup_new(engine)
 from verification.discovery import material_qualification
 original=material_qualification.project_idox
 def tampered(*args):
  packet=original(*args);packet['observation'].field_states['decision']='NOT_PRESENT'
  packet['observation'].b2_eligible=True
  return packet
 monkeypatch.setattr(material_qualification,'project_idox',tampered)
 result=co.new_identity(l.claim(k,'worker','INGESTION_TEST_new'),envelope=e,council=get_council('bolton'),source=raw)
 assert result['identity']=='NOT_CREATED'
 with Session(engine) as s:assert s.scalar(select(func.count()).select_from(Application))==0
