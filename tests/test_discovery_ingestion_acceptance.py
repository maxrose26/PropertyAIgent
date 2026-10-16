"""Single-window controller and unit acceptance, synthetic/disposable only."""
from copy import deepcopy
from dataclasses import replace
import json
import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.db.models import Application
from app.ingestion.ledger import Ledger,Denied,DEFAULT_LIMITS,digest
from app.ingestion.schema import install,WorkItem as W
from app.ingestion.coordinator import Coordinator
from app.ingestion.idox_adapter import IdoxListingContract
from verification.ingestion_storage.operational_controller import AcceptanceBinding,execute,DatabaseBudget
from verification.ingestion_storage.new_identity_contract import accepted_idox_new_identity
from verification.discovery.idox_window import WindowConfig,run
from tests.test_discovery_idox_window import FORM,Response
from tests.test_discovery_idox_window import page
from tests.test_discovery_ingestion_ledger import outer
from tests.test_discovery_admission import engine,envelope
from tests.test_discovery_initial_application_contract import projected
from verification.direct_reference.fixtures import summary
from app.config import get_council


def listing_audit(target,refs=None):
 cfg=WindowConfig(max_transport_retries=0)
 echo=FORM.replace(b'name="date(applicationReceivedStart)" value=""',b'name="date(applicationReceivedStart)" value="28/09/2026"').replace(b'name="date(applicationReceivedEnd)" value=""',b'name="date(applicationReceivedEnd)" value="04/10/2026"')
 refs=refs or (target['reference'],)
 body=page(first=1,last=len(refs),total=len(refs),refs=refs).replace(b'keyVal=K0',('keyVal='+target['source_identifier']).encode()).replace(b'Outline residential development, scale unknown',b'Erection of 20 residential dwellings')
 bodies=iter([FORM,body,body,echo]);return run(lambda *a,**k:Response(next(bodies)),cfg)


class BoundLedger(Ledger):
 def claim(self,key,owner='controller',authority='INGESTION_TEST_controller',lease_seconds=165):return super().claim(key,owner,authority,lease_seconds)


def prepared(engine):
 install(engine);l=BoundLedger(engine);target,raw,_=projected(summary('01780/26',status='Decided',decision='Approve',date='Mon 28 Sep 2026'))
 cfg=WindowConfig(max_transport_retries=0);contract=IdoxListingContract('controller-idox',cfg,'a'*64);a=listing_audit(target);r=contract.project(a,outer(),DEFAULT_LIMITS)['records'][0]
 root=l.enqueue({'kind':'DISCOVERY_SCOPE','council':'bolton','start':cfg.start.isoformat(),'end':cfg.end.isoformat(),'semantics':'RECEIVED'},'DISCOVERY',contract=contract.name)
 child=l.enqueue({'kind':'APPLICATION','council':'bolton','reference':r['reference']},'SCREENING',contract='listing-screen-v1',revision=digest(r),dependencies=[root])
 fact=l.enqueue({'kind':'APPLICATION','council':'bolton','reference':r['reference']},'FACTUAL_REFRESH',contract='controller-fact',dependencies=[child])
 l.grant('INGESTION_TEST_controller',[root,child,fact],contracts=[contract.name,'listing-screen-v1','controller-fact'],expires_at=l.clock()+600,source_calls=2,writes=2,detail_source_keys=[fact])
 co=Coordinator(l,{contract.name:contract,'controller-fact':accepted_idox_new_identity('controller-fact',target)})
 env=replace(envelope(),reference=r['reference'],displayed_references=(r['reference'],),source_url=r['source_url'],source_record_id=r['source_record_id'])
 binding=AcceptanceBinding(root,child,fact,r['reference'],r['source_url'],r['source_record_id'],digest(r))
 return l,co,binding,a,raw,env


def test_one_window_supported_candidate_with_authority_before_detail(engine):
 l,co,b,a,raw,e=prepared(engine);seen=[]
 def detail(row):
  assert l.get(b.factual_key)['phase']=='SOURCE_INTENT'
  seen.append(1);return raw,outer()
 result=execute(co,b,listing_reader=lambda _: (a,outer()),detail_reader=detail,envelope=e,council=get_council('bolton'))
 assert result['outcome']=='SUPPORTED_FACTS_VERIFIED' and len(seen)==1
 with Session(engine) as s:assert s.scalar(select(func.count()).select_from(Application))==1
 with pytest.raises(Denied):execute(co,b,listing_reader=lambda _:pytest.fail('replay'),detail_reader=detail,envelope=e,council=get_council('bolton'))


@pytest.mark.parametrize('mode',['known','changed','absent','stop','missing_detail_authority'])
def test_no_replacement_or_unauthorised_detail(engine,mode,tmp_path):
 l,co,b,a,raw,e=prepared(engine);calls=[]
 if mode=='known':
  with Session(engine) as s:s.add(Application(council_code='bolton',reference=e.reference,status='PRESERVED'));s.commit()
 if mode=='changed':b=replace(b,listing_revision='0'*64)
 if mode=='absent':
  b=replace(b,reference='99999/26');e=replace(e,reference='99999/26',displayed_references=('99999/26',))
 if mode=='missing_detail_authority':
  with l.tx() as (c,control):
   control['outcome']['grants']['INGESTION_TEST_controller']['detail_source_keys']=[];l._control(c,control)
 check=lambda:None
 if mode=='stop':
  p=tmp_path/'STOP';p.touch();check=DatabaseBudget(stop_file=p).check
 if mode in {'stop','missing_detail_authority'}:
  with pytest.raises(Denied):execute(co,b,listing_reader=lambda _: (a,outer()),detail_reader=lambda _:calls.append(1),envelope=e,council=get_council('bolton'),check=check)
 else:
  result=execute(co,b,listing_reader=lambda _: (a,outer()),detail_reader=lambda _:calls.append(1),envelope=e,council=get_council('bolton'))
  assert result['admission']=='NOT_ATTEMPTED' and result['b2']=='NOT_ATTEMPTED'
 assert calls==[]


def test_source_supervisor_denies_credentials_before_launch(tmp_path):
 import sys
 from verification.ingestion_storage.operational_supervisor import supervise
 with pytest.raises(ValueError):supervise([sys.executable,'-c','pass'],environment={'DATABASE_URL':'forbidden'},root=tmp_path/'source',source=True)


def test_detail_accounting_failure_stops_before_application_creation(engine):
 l,co,b,a,raw,e=prepared(engine);raw=deepcopy(raw);raw['process_cleanup']='UNCERTAIN'
 with pytest.raises(Denied):execute(co,b,listing_reader=lambda _: (a,outer()),detail_reader=lambda _: (raw,outer()),envelope=e,council=get_council('bolton'))
 with Session(engine) as s:assert s.scalar(select(func.count()).select_from(Application))==0
 with pytest.raises(Denied):l.claim(b.factual_key)


def test_wrong_factual_contract_stops_before_detail_authority_or_call(engine):
 l,co,b,a,raw,e=prepared(engine);calls=[]
 co.contracts['controller-fact']=replace(co.contracts['controller-fact'],row=dict(co.contracts['controller-fact'].row,source_url='https://invalid.example/wrong'))
 with pytest.raises(Denied):execute(co,b,listing_reader=lambda _: (a,outer()),detail_reader=lambda _: calls.append(1),envelope=e,council=get_council('bolton'))
 assert calls==[] and l.get(b.factual_key)['phase']=='CLAIMED'


def test_unsupported_detail_preserves_receipt_and_creates_no_application(engine):
 l,co,b,a,raw,e=prepared(engine)
 _,raw,_=projected(summary('01780/26',status='Awaiting decision',omit=('Decision','Decision Issued Date')))
 result=execute(co,b,listing_reader=lambda _: (a,outer()),detail_reader=lambda _: (raw,outer()),envelope=e,council=get_council('bolton'))
 assert result['outcome']=='FACTS_WITHHELD' and l.get(b.factual_key)['state']=='UNSUPPORTED_CONTRACT'
 assert l.get(b.factual_key)['checkpoint']['kind']=='DETAIL_RECEIPT_V1'
 with Session(engine) as s:assert s.scalar(select(func.count()).select_from(Application))==0


def test_retained_capture_continues_with_exact_nominee_without_second_observation(engine):
 from verification.ingestion_storage.operational_controller import capture
 l,co,b,a,raw,e=prepared(engine)
 first=capture(co,b.discovery_key,listing_reader=lambda _: (a,outer()))
 assert first['outcome']=='DISCOVERY_SCREENING_ONLY' and first['admission']=='NOT_ATTEMPTED'
 frozen=replace(b,retained_capture_sha256=first['checkpoint_sha256'])
 result=execute(co,frozen,listing_reader=lambda _:pytest.fail('completed discovery must never repeat'),detail_reader=lambda _: (raw,outer()),envelope=e,council=get_council('bolton'))
 assert result['outcome']=='SUPPORTED_FACTS_VERIFIED'


def test_aggregate_database_allowance_survives_manual_nomination_pause():
 previous=dict(connection_attempts=3,driver_statements=90,elapsed_seconds=4.5,connections_closed=True,cleanup='CLOSED',statement_kinds={'cursor':90})
 b=DatabaseBudget(previous=previous)
 assert b.attempts==3 and b.statements==90
 for _ in range(22):b.tick('cursor')
 with pytest.raises(Denied):b.tick('cursor')
 for _ in range(8):b.tick('rollback',cleanup=True)
 with pytest.raises(Denied):b.tick('rollback',cleanup=True)
 with pytest.raises(Denied):DatabaseBudget(previous=dict(previous,cleanup='UNCERTAIN'))


def test_retained_sql_continuation_cannot_reset_or_misbind_budget():
 from verification.ingestion_storage.operational_controller import ControllerLedger
 def reject(previous,binding):
  budget=DatabaseBudget(previous=previous)
  engine=budget.engine('postgresql+psycopg://ingestion_worker_login:unused@127.0.0.1:5432/ingestion_provisioning_test')
  ledger=ControllerLedger(engine,budget=budget,owner='one',authority='unused',bindings={})
  with pytest.raises(Denied,match='SEALED_PRIOR_ACCOUNTING_REQUIRED'):execute(Coordinator(ledger,{}),binding,listing_reader=None,detail_reader=None,envelope=None,council=None)
  assert budget.attempts==(previous or {}).get('connection_attempts',0) and budget.opened==[]
  budget.close([engine])
 binding=AcceptanceBinding('a'*64,'b'*64,'c'*64,'X','https://example.invalid','K','d'*64,retained_capture_sha256='e'*64)
 reject(None,binding)
 prior=dict(connection_attempts=2,driver_statements=30,elapsed_seconds=1,connections_closed=True,cleanup='CLOSED',capture_checkpoint_sha256='f'*64)
 reject(prior,replace(binding,prior_accounting_sha256=digest(prior)))
