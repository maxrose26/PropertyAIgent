"""Bounded batching fixtures and offline capture controls; no live transport."""
import json,re,hashlib
from datetime import date
from bs4 import BeautifulSoup
import pytest
from app.ingestion.ledger import DEFAULT_LIMITS,digest,Denied
from app.ingestion.idox_adapter import IdoxListingContract
from app.ingestion.batching import archive_capture,batch_plans
from verification.discovery.idox_window import WindowConfig,run
from tests.test_discovery_idox_window import FORM,Response,page
from tests.test_discovery_ingestion_ledger import outer


def sixty_rows():
 cfg=WindowConfig('bolton','RECEIVED',date(2026,10,16),date(2026,10,16),0);pages=[]
 proposals=('Erection of 20 residential dwellings','Discharge of conditions pursuant to 02000/26','Replacement guttering to existing dwelling')
 for n in range(6):
  refs=tuple(f'{2000+n*10+i:05d}/26' for i in range(10))
  body=page(first=n*10+1,last=n*10+10,total=60,refs=refs,next_page=n+2 if n<5 else None)
  body=re.sub(rb'keyVal=K(\d+)',lambda m:b'keyVal=K'+str(n*10+int(m[1])).encode(),body).replace(b'Mon 28 Sep 2026',b'Fri 16 Oct 2026')
  soup=BeautifulSoup(body,'html.parser')
  for i,a in enumerate(soup.select('a.summaryLink')):a.string=proposals[(n*10+i)%3]
  pages.append(str(soup).encode())
 echo=FORM.replace(b'name="date(applicationReceivedStart)" value=""',b'name="date(applicationReceivedStart)" value="16/10/2026"').replace(b'name="date(applicationReceivedEnd)" value=""',b'name="date(applicationReceivedEnd)" value="16/10/2026"')
 bodies=iter([FORM,pages[0],*pages,echo]);calls=[]
 def dispatch(*a,**kw):calls.append(1);return Response(next(bodies))
 audit=run(dispatch,cfg);assert len(calls)==9
 return cfg,audit


def test_complete_source_has_exact_twelve_nonoverlapping_batches():
 from app.ingestion.listing_screening import screen_row
 cfg,a=sixty_rows();r=IdoxListingContract('controller-idox',cfg,'a'*64).project(a,outer(),DEFAULT_LIMITS);r.pop('window');r['durable_archive']={'sha256':digest(a)}
 plans=batch_plans('b'*64,r)
 assert len(plans)==12 and [p['checkpoint']['plan']['first'] for p in plans]==list(range(0,60,5))
 assert len({p['key'] for p in plans})==12 and all(p['max_attempts']==2 for p in plans)
 assert plans[-1]['dependencies']==sorted(['b'*64,plans[-2]['key']])
 results=[screen_row(x) for x in r['records']]
 assert {x['disposition'] for x in results}=={'SUPPORTED_PROCESSING_PRIORITY','RELATED_APPLICATION_FOLLOW_THROUGH','INSUFFICIENT_EVIDENCE'}
 assert sum(bool(x['citations']['occurrences']) for x in results)==20


def test_archive_requires_exact_bytes_and_positive_readback():
 source={'original':'up to 200 dwellings'}
 def archive(raw):return dict(commit='a'*40,path='docs/design/fixture.json',sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),readback_verified=True)
 assert archive_capture(source,archive)['sha256']==digest(source)
 with pytest.raises(Denied):archive_capture(source,lambda raw:dict(archive(raw),sha256='b'*64))
 with pytest.raises(Denied):archive_capture(source,lambda raw:dict(archive(raw),readback_verified=False))


def test_recovery_rejects_reset_accounting_before_claim():
 from types import SimpleNamespace
 from app.ingestion.batching import _process_batch
 plan=dict(capture_key='a'*64,capture_sha256='b'*64,first=0,last=5)
 row=dict(contract='listing-batch-v1',task='LISTING_METADATA',checkpoint={'plan':plan},revision=digest(plan),state='DEFERRED',attempt_count=1)
 prior=dict(slot_key='c'*64,capture_checkpoint_sha256='b'*64,driver_statements=0)
 ledger=SimpleNamespace(get=lambda _:row,budget=SimpleNamespace(slot_key='c'*64,previous=prior))
 with pytest.raises(Denied,match='SEALED_RECOVERY_ACCOUNTING_REQUIRED'):_process_batch(SimpleNamespace(ledger=ledger),'c'*64,prior_accounting_sha256=digest(dict(prior,driver_statements=50)))


def test_capture_recovery_requires_exact_prior_seal_and_slot():
 from types import SimpleNamespace
 from app.ingestion.batching import capture_once
 checkpoint={'kind':'LISTING_RECEIPT_V1'};key='a'*64
 prior=dict(slot_key=key,capture_checkpoint_sha256=digest(checkpoint),driver_statements=0)
 ledger=SimpleNamespace(get=lambda _:{'checkpoint':checkpoint,'state':'DEFERRED'},budget=SimpleNamespace(slot_key=key,previous=prior))
 with pytest.raises(Denied,match='SEALED_RECOVERY_ACCOUNTING_REQUIRED'):capture_once(SimpleNamespace(ledger=ledger),key,None,None,prior_accounting_sha256=digest(dict(prior,driver_statements=50)))
 ledger.budget.slot_key='b'*64
 with pytest.raises(Denied,match='SEALED_RECOVERY_ACCOUNTING_REQUIRED'):capture_once(SimpleNamespace(ledger=ledger),key,None,None,prior_accounting_sha256=digest(prior))


def test_allocation_is_hash_bound_and_cumulative_not_per_delivery():
 from verification.ingestion_storage.operational_controller import batch_allocation
 key='a'*64;other='b'*64
 receipt=dict(database=dict(slot_key=key,cleanup='CLOSED',connections_closed=True,driver_statements=1000,connection_attempts=30,returned_data_value_bytes=100),supervised_seconds=20,cleanup='CLOSED')
 receipts={key:receipt}
 a=batch_allocation([key,other],receipts,sealed_sha256=digest(receipts),slot_key=other)
 assert a['remaining']['driver_statements']==40 and a['remaining']['connection_attempts']==10
 with pytest.raises(Denied,match='SEALED_ALLOCATION_REQUIRED'):batch_allocation([key,other],receipts,sealed_sha256='c'*64,slot_key=other)
 receipt['database']['driver_statements']=1041
 with pytest.raises(Denied,match='AGGREGATE_ALLOCATION_EXHAUSTED'):batch_allocation([key,other],receipts,sealed_sha256=digest(receipts),slot_key=other)


def test_oversized_inline_receipt_preserves_complete_archive_and_blocks_no_refetch():
 from types import SimpleNamespace
 from app.ingestion.coordinator import Coordinator
 from app.ingestion.batching import capture_once
 cfg,a=sixty_rows()
 for r in a['records']:r['fields']['proposal']['value']='Full literal retained '+('x'*3000)
 row=dict(subject={'kind':'DISCOVERY_SCOPE','council':'bolton','start':'2026-10-16','end':'2026-10-16','semantics':'RECEIVED'},contract='controller-idox',checkpoint=None,limits=DEFAULT_LIMITS,state='CLAIMED')
 saved=[];calls=[]
 def store(raw):saved.append(raw);return dict(commit='a'*40,path='docs/design/fixture.json',sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),readback_verified=True)
 def checkpoint(claim,payload):row['checkpoint']=payload
 def finish(claim,outcome,**kwargs):row.update(state=kwargs.get('state','COMPLETE'),outcome=outcome)
 ledger=SimpleNamespace(get=lambda _:row,intent=lambda *a:None,checkpoint=checkpoint,finish=finish,stop=lambda *a,**kw:None)
 co=Coordinator(ledger,{'controller-idox':IdoxListingContract('controller-idox',cfg,'a'*64)})
 co.idox_source(SimpleNamespace(key='b'*64),lambda _: (calls.append(1) or a,outer()),materialize=False,archive=store)
 assert len(saved)==1 and len(json.loads(saved[0])['records'])==60 and len(calls)==1
 assert row['checkpoint']['kind']=='CAPTURE_BLOCKED_V1' and row['state']=='UNSUPPORTED_CONTRACT'
 with pytest.raises(Denied,match='CAPTURE_BLOCKED_NO_REFETCH'):capture_once(co,'b'*64,None,None)
