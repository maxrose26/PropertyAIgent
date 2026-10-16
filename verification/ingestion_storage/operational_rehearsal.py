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
from verification.ingestion_storage.operational_controller import DatabaseBudget,ControllerLedger,AcceptanceBinding,execute,capture,resume_capture
from app.config import get_council


def main():
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if os.environ.get('INGESTION_ACCEPTANCE_DISPOSABLE')!='PG17_ONLY' or a.output.exists():raise ValueError('DISPOSABLE_PRIVATE_ONLY')
 plan=json.loads(a.plan.read_bytes());urls=json.loads(os.environ.pop('INGESTION_ACCEPTANCE_FIXTURE_URLS'))
 expected=['ingestion_worker_login','ingestion_effect_login','ingestion_application_login']
 if plan.get('mode')=='recover_batch':expected.append('ingestion_recovery_login')
 if len(urls)!=len(expected):raise ValueError('EXACT_FIXTURE_PRINCIPALS')
 for raw,role in zip(urls,expected):
  u=make_url(raw)
  if (u.host,u.port,u.database,u.username)!=('127.0.0.1',5432,'ingestion_provisioning_test',role):raise ValueError('LOOPBACK_ONLY')
 binding=AcceptanceBinding(**plan['binding']);audit=plan['listing'];target=plan['target']
 cfg=WindowConfig(audit['council'],audit['date_semantics'],*[date.fromisoformat(x) for x in audit['requested_interval']],0)
 contract=IdoxListingContract('controller-idox',cfg,'a'*64)
 w=plan['envelope']['window']
 for k in ('requested_start','requested_end','applied_start','applied_end'):w[k]=date.fromisoformat(w[k]) if w[k] else None
 e=dict(plan['envelope']);e['window']=WindowEvidence(**w);e['discovered_at']=datetime.fromisoformat(e['discovered_at']);e['displayed_references']=tuple(e['displayed_references']);e['fields']=()
 envelope=DiscoveryEnvelope(**e)
 if binding.retained_capture_sha256 and not plan.get('prior_database_accounting'):raise ValueError('PRIOR_ACCOUNTING_REQUIRED')
 slot_key=plan.get('batch_key') if plan.get('mode') in ('process_batch','recover_batch') else binding.discovery_key if plan.get('mode')=='capture_once' else None
 budget=DatabaseBudget(previous=plan.get('prior_database_accounting'),slot_key=slot_key,**plan.get('database_ceilings',{}));engines=[];result={'outcome':'UNCONFIRMED_NO_RETRY'}
 try:
  engines=[budget.engine(u) for u in urls]
  costs={'enqueue':[],'screening_body':[]}
  class RehearsalLedger(ControllerLedger):
   emitted=0
   def enqueue(self,*args,**kwargs):
    before=budget.statements
    key=super().enqueue(*args,**kwargs);costs['enqueue'].append(budget.statements-before);self.emitted+=1
    if plan.get('interrupt_after_children')==self.emitted:raise SystemExit('FIXTURE_INTERRUPTION_AFTER_COMMITTED_CHILD')
    return key
  l=RehearsalLedger(engines[0],budget=budget,owner='one',authority=plan.get('authority','INGESTION_TEST_sql'),bindings=plan['bindings'],broker_engine=engines[1],application_engine=engines[2])
  class RehearsalCoordinator(Coordinator):
   def screening(self,*args,**kwargs):
    before=budget.statements
    result=super().screening(*args,**kwargs);costs['screening_body'].append(budget.statements-before)
    return result
  co=RehearsalCoordinator(l,{contract.name:contract,'operational-fixture':accepted_idox_new_identity('operational-fixture',target)})
  if not l.authority.startswith('INGESTION_TEST_'):raise ValueError('FIXTURE_AUTHORITY_ONLY')
  counts={'listing':0,'detail':0}
  # Faults exist only in this fixed-loopback disposable command. No production
  # controller or source path consumes these private fixture selectors.
  if plan.get('writer_case')=='race':
   import app.pipeline.discovery_admission as admission
   real_admit=admission.admit_identity
   def competing_admission(engine,envelope):
    winner=real_admit(engine,envelope)
    assert winner['outcome']=='CREATED_PENDING'
    admission.admit_identity=real_admit
    return real_admit(engine,envelope)
   admission.admit_identity=competing_admission
  if plan.get('writer_case')=='uncertain':
   from sqlalchemy.orm import Session
   real_commit=Session.commit;lost=[False]
   def lost_acknowledgement(session):
    real_commit(session)
    if session.bind is engines[2] and not lost[0]:lost[0]=True;raise RuntimeError('DISPOSABLE_COMMIT_ACK_LOST')
   Session.commit=lost_acknowledgement
  def listing(_):counts['listing']+=1;return audit,plan['outer']
  def detail(_):counts['detail']+=1;return plan['detail'],plan['outer']
  from app.ingestion.batching import capture_once,process_batch
  def archive(raw):
   import hashlib
   dest=a.output.parent/'retained-capture.json'
   with dest.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
   assert dest.read_bytes()==raw
   return dict(commit='a'*40,path='docs/design/disposable-capture.json',sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),readback_verified=True)
  def interrupt(i):
   if plan.get('interrupt_batch_after')==i:raise SystemExit('FIXTURE_INTERRUPTION_AFTER_ATOMIC_ROW')
  if plan.get('mode')=='recover_batch':
   from sqlalchemy import text
   from app.ingestion.ledger import digest
   if not budget.previous or digest(budget.previous)!=binding.prior_accounting_sha256 or budget.previous.get('slot_key')!=slot_key:raise ValueError('SEALED_RECOVERY_ACCOUNTING_REQUIRED')
   with engines[3].begin() as recovery:recovered=recovery.execute(text('SELECT public.ingestion_recover_abandoned(:key,:fence,true)'),dict(key=slot_key,fence=plan['recovery_fence'])).scalar_one()
   result=dict(outcome='CLAIM_RECOVERED',recovered=recovered)
  elif plan.get('mode')=='capture_once':
   receipt=capture_once(co,binding.discovery_key,listing,archive,budget.check,prior_accounting_sha256=binding.prior_accounting_sha256)
   result=dict(outcome='CAPTURE_COMPLETE' if receipt['kind']=='LISTING_RECEIPT_V1' else 'CAPTURED_PROCESSING_BLOCKED',receipt=receipt)
  elif plan.get('mode')=='process_batch':result=process_batch(co,plan['batch_key'],check=budget.check,after_row=interrupt,prior_accounting_sha256=binding.prior_accounting_sha256)
  elif plan.get('mode')=='resume_capture':result=resume_capture(co,binding.discovery_key,checkpoint_sha256=binding.retained_capture_sha256,prior_accounting_sha256=binding.prior_accounting_sha256,screening_keys=plan['screening_keys'],check=budget.check)
  elif plan.get('mode')=='capture':result=capture(co,binding.discovery_key,listing_reader=listing,check=budget.check)
  else:result=execute(co,binding,listing_reader=listing,detail_reader=detail,envelope=envelope,council=get_council(target['council']),check=budget.check)
  result['synthetic_reader_callbacks']=counts
 except BaseException as exc:
  result['error_class']=type(exc).__name__
  if plan.get('writer_case')=='uncertain' and type(exc).__name__=='UncertainPersistence':
   try:l.claim(plan['blocked_next_key'])
   except Exception as denied:
    if 'GLOBAL_STOP' not in str(denied):raise
    result['subsequent_claim_denied']=True
   else:raise AssertionError('UNCERTAIN_WRITE_DID_NOT_STOP_NEXT_CLAIM')
  raise
 finally:
  if 'counts' in locals():result['synthetic_reader_callbacks']=counts
  if 'costs' in locals():result['operation_command_costs']=costs
  account=budget.close(engines);result['database_accounting']=account
  raw=json.dumps(result,sort_keys=True,allow_nan=False).encode()
  if len(raw)>512*1024:raise ValueError('WORKER_AUDIT_BOUND')
  with a.output.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 return 0 if result['outcome'] in {'SUPPORTED_FACTS_VERIFIED','DISCOVERY_SCREENING_ONLY','CAPTURE_COMPLETE','CAPTURED_PROCESSING_BLOCKED','BATCH_SCREENED','BATCH_ALREADY_COMPLETE','CLAIM_RECOVERED'} and account['cleanup']=='CLOSED' else 1

if __name__=='__main__':raise SystemExit(main())
