import json,re,time
from pathlib import Path
from datetime import date
from sqlalchemy import create_engine,select,func
from app.ingestion.schema import install,WorkItem as W
from app.ingestion.ledger import Ledger,DEFAULT_LIMITS,digest
from app.ingestion.coordinator import Coordinator
from app.ingestion.idox_adapter import IdoxListingContract
from verification.discovery.idox_window import WindowConfig,run
from tests.test_discovery_idox_window import FORM,Response,page
from tests.test_discovery_ingestion_ledger import outer
cfg=WindowConfig('bolton','RECEIVED',date(2026,10,16),date(2026,10,16),0)
frames=[]
for n in range(6):
 refs=tuple(f'{2000+n*10+i:05d}/26' for i in range(10))
 body=page(first=n*10+1,last=n*10+10,total=60,refs=refs,next_page=n+2 if n<5 else None)
 body=re.sub(rb'keyVal=K(\d+)',lambda m:b'keyVal=K'+str(n*10+int(m[1])).encode(),body)
 body=body.replace(b'Mon 28 Sep 2026',b'Fri 16 Oct 2026').replace(b'Outline residential development, scale unknown',b'Erection of 20 residential dwellings')
 frames.append(body)
echo=FORM.replace(b'name="date(applicationReceivedStart)" value=""',b'name="date(applicationReceivedStart)" value="16/10/2026"').replace(b'name="date(applicationReceivedEnd)" value=""',b'name="date(applicationReceivedEnd)" value="16/10/2026"')
bodies=iter([FORM,frames[0],*frames,echo]);calls=[]
def dispatch(*a,**kw):calls.append(a[0]);return Response(next(bodies))
audit=run(dispatch,cfg);contract=IdoxListingContract('practical-bolton-fixture',cfg,'a'*64)
receipt=contract.project(audit,outer(),DEFAULT_LIMITS);receipt.pop('window')
assert len(receipt['records'])==60 and len(receipt['segments'])==6
p=Path('/workspace/scratch/bfed03f1aa09/metadata-evidence/docs/design/ingestion-practical-acceptance-result-20261016')
e=create_engine('sqlite:///:memory:');install(e);l=Ledger(e);root=l.enqueue({'kind':'DISCOVERY_SCOPE','council':'bolton','start':'2026-10-16','end':'2026-10-16','semantics':'RECEIVED'},'DISCOVERY',contract=contract.name)
l.grant('INGESTION_TEST_practical',[root],source_calls=1,writes=0,expires_at=time.time()+600,contracts=[contract.name])
co=Coordinator(l,{contract.name:contract});callbacks=[]
children=co.idox_source(l.claim(root,'fixture','INGESTION_TEST_practical'),lambda _:(callbacks.append(1) or audit,outer()))
assert len(children)==60 and len(callbacks)==1
sealed=digest(l.get(root)['checkpoint']);batches=[]
for batchno in range(12):
 keys=children[batchno*5:(batchno+1)*5];auth=f'INGESTION_TEST_queue_{batchno}'
 fresh=Ledger(e);fresh.grant(auth,keys,source_calls=0,writes=0,expires_at=time.time()+600,contracts=['listing-screen-v1']);worker=Coordinator(fresh,{})
 for key in keys:worker.screening(fresh.claim(key,'fixture',auth))
 assert digest(fresh.get(root)['checkpoint'])==sealed
 batches.append({'ordinal':batchno+1,'screened':len(keys),'completed_total':sum(fresh.get(k)['state']=='COMPLETE' for k in children),'source_callbacks_total':len(callbacks)})
with e.connect() as c:total=c.scalar(select(func.count()).select_from(W))
report={'kind':'OFFLINE_SYNTHETIC_NOT_PRODUCTION','runtime_candidate':'5f36a886e685fb4e705ee7c58fbbb81bbd41736f','source_requests_via_fake_dispatch':len(calls),'source_actual_network_calls':0,'qualified_records':60,'pages':6,'canonical_receipt_bytes':len(json.dumps(receipt,sort_keys=True,separators=(',',':')).encode()),'receipt_ceiling':128*1024,'receipt_sha256':sealed,'source_received_body_bytes':audit['resource']['received_bytes'],'coordinator_materialised_children':len(children),'screening_batches':batches,'source_callbacks_total':len(callbacks),'work_items_including_control_and_root':total,'limitations':['SQLite functional probe; not PostgreSQL command/RSS/deadline proof','Materialisation still unbatched in current code; cannot dispatch at120 commands','Queued screening batches use exact new disposable allowances; membership is not source/write authority','Short synthetic descriptions; not worst-case128KiB payload certification']}
(p/'sixty-row-probe.json').write_text(json.dumps(report,indent=2)+'\n');(p/'synthetic-capture.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='screening_batches'}));e.dispose()
