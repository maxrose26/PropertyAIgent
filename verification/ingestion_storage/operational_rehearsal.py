"""PRIVATE fixed-loopback controller worker, no production execution path.

No source client: synthetic retained responses supplied in its non-secret plan.
Existing protected production authorities cannot enter this disposable command.
"""
import argparse,json,os
from pathlib import Path
from dataclasses import fields
from datetime import date,datetime
from sqlalchemy.engine import make_url
from app.ingestion.coordinator import Coordinator
from app.ingestion.idox_adapter import IdoxListingContract
from app.pipeline.discovery_contract import DiscoveryEnvelope,WindowEvidence
from verification.discovery.idox_window import WindowConfig
from verification.ingestion_storage.new_identity_contract import accepted_idox_new_identity
from verification.ingestion_storage.operational_controller import DatabaseBudget,ControllerLedger,AcceptanceBinding,execute,capture
from app.config import get_council


def main():
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if os.environ.get('INGESTION_ACCEPTANCE_DISPOSABLE')!='PG17_ONLY' or a.output.exists():raise ValueError('DISPOSABLE_PRIVATE_ONLY')
 urls=json.loads(os.environ.pop('INGESTION_ACCEPTANCE_FIXTURE_URLS'))
 expected=['ingestion_worker_login','ingestion_effect_login','ingestion_application_login']
 if len(urls)!=3:raise ValueError('EXACT_FIXTURE_PRINCIPALS')
 for raw,role in zip(urls,expected):
  u=make_url(raw)
  if (u.host,u.port,u.database,u.username)!=('127.0.0.1',5432,'ingestion_provisioning_test',role):raise ValueError('LOOPBACK_ONLY')
 plan=json.loads(a.plan.read_bytes());binding=AcceptanceBinding(**plan['binding']);audit=plan['listing'];target=plan['target']
 cfg=WindowConfig(audit['council'],audit['date_semantics'],*[date.fromisoformat(x) for x in audit['requested_interval']],0)
 contract=IdoxListingContract('controller-idox',cfg,'a'*64)
 w=plan['envelope']['window']
 for k in ('requested_start','requested_end','applied_start','applied_end'):w[k]=date.fromisoformat(w[k]) if w[k] else None
 e=dict(plan['envelope']);e['window']=WindowEvidence(**w);e['discovered_at']=datetime.fromisoformat(e['discovered_at']);e['displayed_references']=tuple(e['displayed_references']);e['fields']=()
 envelope=DiscoveryEnvelope(**e)
 if binding.retained_capture_sha256 and not plan.get('prior_database_accounting'):raise ValueError('PRIOR_ACCOUNTING_REQUIRED')
 budget=DatabaseBudget(previous=plan.get('prior_database_accounting'));engines=[];result={'outcome':'UNCONFIRMED_NO_RETRY'}
 try:
  engines=[budget.engine(u) for u in urls]
  l=ControllerLedger(engines[0],budget=budget,owner='one',authority=plan.get('authority','INGESTION_TEST_sql'),bindings=plan['bindings'],broker_engine=engines[1],application_engine=engines[2])
  co=Coordinator(l,{contract.name:contract,'operational-fixture':accepted_idox_new_identity('operational-fixture',target)})
  if not l.authority.startswith('INGESTION_TEST_'):raise ValueError('FIXTURE_AUTHORITY_ONLY')
  counts={'listing':0,'detail':0}
  def listing(_):counts['listing']+=1;return audit,plan['outer']
  def detail(_):counts['detail']+=1;return plan['detail'],plan['outer']
  if plan.get('mode')=='capture':result=capture(co,binding.discovery_key,listing_reader=listing,check=budget.check)
  else:result=execute(co,binding,listing_reader=listing,detail_reader=detail,envelope=envelope,council=get_council(target['council']),check=budget.check)
  result['synthetic_reader_callbacks']=counts
 except BaseException as exc:
  result['error_class']=type(exc).__name__
  raise
 finally:
  account=budget.close(engines);result['database_accounting']=account
  raw=json.dumps(result,sort_keys=True,allow_nan=False).encode()
  if len(raw)>512*1024:raise ValueError('WORKER_AUDIT_BOUND')
  with a.output.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 return 0 if result['outcome'] in {'SUPPORTED_FACTS_VERIFIED','DISCOVERY_SCREENING_ONLY'} and account['cleanup']=='CLOSED' else 1

if __name__=='__main__':raise SystemExit(main())
