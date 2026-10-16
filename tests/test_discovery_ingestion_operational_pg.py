"""Real PG17 restricted SQL capabilities and shared coordinator; fixed loopback only."""
import json,os,secrets,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import psycopg,pytest
from psycopg import sql
from sqlalchemy import create_engine,select,text,event
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import Session
from app.ingestion.ledger import Ledger,Denied,UncertainPersistence,DEFAULT_LIMITS
from app.ingestion.schema import WorkItem as W,WorkAttempt as A
from app.ingestion.sql_ledger import SQLLedger
from app.ingestion.coordinator import Coordinator
from verification.ingestion_storage.new_identity_contract import accepted_idox_new_identity
from app.db.models import Base,Council,Application
from app.config import get_council
from tests.test_discovery_ingestion_provisioning_pg import ROLES,PACKAGE
from tests.test_discovery_ingestion_operational import setup_new


def test_restricted_sql_claims_fencing_checkpoints_completion_and_shared_new_identity(record_property,tmp_path):
 raw=os.environ.get('INGESTION_PROVISIONING_TEST_URL')
 if not raw:pytest.skip('fixed disposable PG17 service required')
 info=psycopg.conninfo.conninfo_to_dict(raw)
 assert (info.get('host'),info.get('port'),info.get('dbname'),info.get('user'))==('127.0.0.1','5432','ingestion_provisioning_test','provisioning_bootstrap')
 extra=['ingestion_application_writer','ingestion_effect_broker','ingestion_recovery_operator','ingestion_effect_login','ingestion_recovery_login','operational_untrusted','ingestion_application_login']
 passwords={r:secrets.token_urlsafe(48) for r in ['provisioning_migrator','ingestion_worker_login','ingestion_storage_login','ingestion_effect_login','ingestion_recovery_login','operational_untrusted','ingestion_application_login']}
 fixture_costs={'connection_attempts':1,'cursor_calls':0}
 class FixtureCursor(psycopg.Cursor):
  def execute(self,*args,**kwargs):fixture_costs['cursor_calls']+=1;return super().execute(*args,**kwargs)
 def connect(role):
  fixture_costs['connection_attempts']+=1
  return psycopg.connect(**{**info,'user':role,'password':passwords[role]},autocommit=True,prepare_threshold=None,connect_timeout=3,cursor_factory=FixtureCursor)
 def engine(role):
  from sqlalchemy.engine import URL
  e=create_engine(URL.create('postgresql+psycopg',username=role,password=passwords.get(role,info['password']),host='127.0.0.1',port=5432,database=info['dbname']),poolclass=NullPool,connect_args={'connect_timeout':3,'prepare_threshold':None})
  @event.listens_for(e,'before_cursor_execute')
  def cursor_call(*args):fixture_costs['cursor_calls']+=1
  @event.listens_for(e,'do_connect')
  def physical_attempt(*args):fixture_costs['connection_attempts']+=1
  return e
 engines=[]
 with psycopg.connect(raw,autocommit=True,connect_timeout=3,cursor_factory=FixtureCursor) as boot:
  try:
   boot.execute(sql.SQL('CREATE ROLE provisioning_migrator LOGIN NOSUPERUSER NOCREATEDB CREATEROLE NOINHERIT NOBYPASSRLS PASSWORD {}').format(sql.Literal(passwords['provisioning_migrator'])))
   boot.execute('GRANT USAGE,CREATE ON SCHEMA public TO provisioning_migrator WITH GRANT OPTION')
   boot.execute('GRANT CONNECT ON DATABASE ingestion_provisioning_test TO provisioning_migrator WITH GRANT OPTION')
   with connect('provisioning_migrator') as m:
    m.execute((PACKAGE/'install.sql').read_text())
    m.execute(Path('docs/design/ingestion-operational-20261016/worker.sql').read_text())
    assert m.execute("SELECT pg_has_role(current_user,'ingestion_storage_owner','SET'),has_schema_privilege('ingestion_storage_owner','public','CREATE')").fetchone()==(False,False)
   # Exact package installation with comparable non-superuser grant options.
   app=engine('provisioning_bootstrap');engines.append(app);Base.metadata.create_all(app)
   writer_sql=Path('docs/design/ingestion-operational-acceptance-20261016/application-writer.sql').read_text()
   grants='\n'.join(line for line in writer_sql.splitlines() if not line.startswith('CREATE ROLE '))
   grants=grants.replace(' TO ingestion_application_writer',' TO provisioning_migrator WITH GRANT OPTION')
   boot.execute(grants)
   with connect('provisioning_migrator') as migration:
    migration.execute(writer_sql)
    migration.execute(Path('docs/design/ingestion-operational-acceptance-20261016/runtime-mappings.sql').read_text())
   # Fixture-only secret setup. All five tested logins have NOLOGIN first.
   for role in ['ingestion_worker_login','ingestion_storage_login','ingestion_effect_login','ingestion_recovery_login','operational_untrusted','ingestion_application_login']:
    if role=='operational_untrusted':boot.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD {}').format(sql.Identifier(role),sql.Literal(passwords[role])))
    else:boot.execute(sql.SQL('ALTER ROLE {} PASSWORD {}').format(sql.Identifier(role),sql.Literal(passwords[role])))
   activation=Path('docs/design/ingestion-operational-acceptance-20261016/activate.sql').read_text()
   for permission in ['UPDATE (event_type) ON public.application_lifecycle_events','REFERENCES (reference) ON public.applications','USAGE ON SEQUENCE public.sites_id_seq']:
    boot.execute('GRANT '+permission+' TO PUBLIC')
    with connect('provisioning_migrator') as migration:
     with pytest.raises(psycopg.Error):migration.execute(activation)
    boot.execute('REVOKE '+permission+' FROM PUBLIC')
    assert boot.execute("SELECT count(*) FROM pg_roles WHERE rolname IN ('ingestion_worker_login','ingestion_effect_login','ingestion_application_login') AND rolcanlogin").fetchone()[0]==0
   with connect('provisioning_migrator') as migration:migration.execute(activation)
   # Storage and recovery login activation are fixture tests only, not runtime.
   boot.execute('ALTER ROLE ingestion_storage_login LOGIN');boot.execute('ALTER ROLE ingestion_recovery_login LOGIN')
   worker=engine('ingestion_worker_login');broker=engine('ingestion_effect_login');engines.extend([worker,broker])
   with Session(app) as s:s.add(Council(code='bolton',name='Bolton',base_url='https://paplanning.bolton.gov.uk',date_field_mode='received',doc_system='idox'));s.commit()
   # Bootstrap constructs fixtures/allowances only; no worker release API exists.
   def seed(reference,task='SCREENING',state='QUEUED',checkpoint=None):
    key=__import__('hashlib').sha256((reference+task).encode()).hexdigest()
    row=dict(key=key,subject={'kind':'APPLICATION','council':'bolton','reference':reference},task=task,contract='operational-fixture',revision='v1',dependencies=[],priority=50,eligible_at=0,state=state,reason='FIXTURE' if state!='QUEUED' else None,next_action='FIXTURE',limits=DEFAULT_LIMITS,authority=None,attempt_count=0,max_attempts=3,fence=0,owner=None,lease_until=None,phase='IDLE',checkpoint=checkpoint,outcome=None)
    with app.begin() as c:c.execute(W.insert().values(**row))
    return key
   k=seed('ONE');blocked=seed('BLOCKED',state='SAFETY_BLOCKED');other=seed('OTHER')
   bindings={}
   def bind(keys,*,writes=0,source_calls=0,authority='INGESTION_TEST_sql',prepared=None):
    nonlocal bindings
    with app.begin() as c:
     for key in keys:
      row=c.execute(select(W).where(W.c.key==key)).mappings().one_or_none()
      if row is None:row=(prepared or {})[key]
      bindings[key]={x:row[x] for x in ('task','contract','revision','subject')}
     control=c.execute(select(W.c.outcome).where(W.c.key=='0'*64)).scalar_one()
     control['grants'][authority]={'keys':keys,'contracts':sorted({bindings[x]['contract'] for x in keys}),'expires_at':time.time()+600,'source_calls':source_calls,'writes':writes,'login':'ingestion_worker_login','effect_login':'ingestion_effect_login','workers':['one','two'],'bindings':{key:bindings[key] for key in keys},'detail_source_keys':[key for key in keys if source_calls and bindings[key]['task']=='FACTUAL_REFRESH'],'completion_outcomes':{'DISCOVERY':['ENUMERATED_METADATA_RETAINED'],'SCREENING':['SCREENED','ALREADY_KNOWN','INSUFFICIENT_EVIDENCE','SUPPORTED_PROCESSING_PRIORITY','RELATED_APPLICATION_FOLLOW_THROUGH','DEEPER_PROCESSING_EXCLUDED_FOR_THIS_SLICE'],'FACTUAL_REFRESH':['SUPPORTED_FACTS_VERIFIED','ALREADY_KNOWN']}}
     c.execute(W.update().where(W.c.key=='0'*64).values(outcome=control))
   bind([k,blocked,other]);l=SQLLedger(worker,owner='one',authority='INGESTION_TEST_sql',bindings=bindings,application_engine=app,broker_engine=broker)
   with pytest.raises(Exception):l.claim(k) # original consumed Salford stop
   assert l.get(k)['attempt_count']==0
   with connect('ingestion_worker_login') as c:
    for statement in ["UPDATE public.ingestion_work_items SET outcome='{}'",'SET ROLE ingestion_storage_owner','SET ROLE ingestion_authority_issuer','SET ROLE ingestion_barrier_releaser',"SELECT public.ingestion_recover_abandoned('x',1,true)","INSERT INTO public.applications(council_code,reference) VALUES('bolton','FORBIDDEN')"]:
     with pytest.raises(psycopg.Error) as e:c.execute(statement)
     assert e.value.sqlstate=='42501'
   with connect('ingestion_storage_login') as c:
    with pytest.raises(psycopg.Error) as e:c.execute("SELECT public.ingestion_worker_step('claim',%s,0,'one','INGESTION_TEST_sql',%s,'{}')",(k,json.dumps(bindings[k])))
    assert e.value.sqlstate=='42501'
   # Clear only the DISPOSABLE control fixture, never a production barrier.
   boot.execute("UPDATE public.ingestion_work_items SET outcome=jsonb_set(outcome::jsonb,'{global_stop}','null')::json WHERE key=repeat('0',64)")
   with pytest.raises(Exception):l.claim(blocked)
   boot.execute('ALTER ROLE ingestion_worker_login CONNECTION LIMIT 2') # disposable concurrent-lock stress only
   barrier=Barrier(2)
   def claim(owner):
    x=SQLLedger(worker,owner=owner,authority='INGESTION_TEST_sql',bindings=bindings);barrier.wait()
    try:return x.claim(k)
    except __import__('sqlalchemy').exc.DBAPIError as e:
     assert e.orig.sqlstate=='42501';return None
   with ThreadPoolExecutor(max_workers=2) as pool:claims=list(pool.map(claim,['one','two']))
   boot.execute('ALTER ROLE ingestion_worker_login CONNECTION LIMIT 1')
   old=next(x for x in claims if x);assert sum(x is not None for x in claims)==1
   l.owner=old.owner;l.checkpoint(old,{'kind':'fixture','retained_sha256':'a'*64})
   with connect('ingestion_worker_login') as c:
    with pytest.raises(psycopg.Error):c.execute("SELECT public.ingestion_worker_step('resolve_effect',%s,%s,%s,'INGESTION_TEST_sql',%s,%s)",(k,old.fence,old.owner,json.dumps(bindings[k]),json.dumps({'outcome':'SUPPORTED_FACTS_VERIFIED','cleanup':'CLOSED','accounting_complete':True})))
   boot.execute('UPDATE public.ingestion_work_items SET lease_until=0 WHERE key=%s',(k,))
   with connect('ingestion_recovery_login') as recovery:result=recovery.execute('SELECT public.ingestion_recover_abandoned(%s,%s,true)',(k,old.fence)).fetchone()[0]
   assert result['state']=='DEFERRED' and result['checkpoint']['retained_sha256']=='a'*64
   fresh=l.claim(k)
   with pytest.raises(Exception):l.checkpoint(old,{'old':'stale'})
   l.checkpoint(fresh,{'kind':'fixture','retained_sha256':'a'*64});l.finish(fresh,{'outcome':'SCREENED'})
   assert l.get(k)['state']=='COMPLETE'
   # Real shared admission+B2 orchestration through the SAME SQL ledger/broker.
   from tests.test_discovery_ingestion_operational import setup_new
   # Reuse fixture builder with a disposable Ledger-shaped admission seam.
   from tests.test_discovery_initial_application_contract import projected
   from verification.direct_reference.fixtures import summary
   from tests.test_discovery_admission import envelope
   from dataclasses import replace
   target,raw_source,packet=projected(summary('01780/26',status='Decided',decision='Approve',date='Mon 28 Sep 2026'))
   env=replace(envelope(),reference=target['reference'],displayed_references=(target['reference'],),source_url=target['source_url'],source_record_id=target['source_identifier'])
   parent=seed('01780/26');fact=seed('01780/26','FACTUAL_REFRESH')
   with app.begin() as c:
    c.execute(W.update().where(W.c.key==parent).values(state='COMPLETE',checkpoint={'disposition':'SUPPORTED_PROCESSING_PRIORITY','source_url':env.source_url,'source_record_id':env.source_record_id}))
    c.execute(W.update().where(W.c.key==fact).values(dependencies=[parent]))
   bind([parent,fact,other],writes=2)
   client=SQLLedger(worker,owner='one',authority='INGESTION_TEST_sql',bindings=bindings,application_engine=app,broker_engine=broker)
   co=Coordinator(client,{'operational-fixture':accepted_idox_new_identity('operational-fixture',target)})
   result=co.new_identity(client.claim(fact),envelope=env,council=get_council('bolton'),source=raw_source)
   assert result['outcome']=='SUPPORTED_FACTS_VERIFIED' and client.get(fact)['state']=='COMPLETE'
   with Session(app) as s:
    rows=list(s.scalars(select(Application)));assert len(rows)==1 and rows[0].estimated_unit_count is None
   # Full existing Idox -> durable metadata -> child -> screening on SQL ledger.
   from app.ingestion.idox_adapter import IdoxListingContract
   from verification.discovery.idox_window import WindowConfig
   from tests.test_discovery_ingestion_operational import audit
   from tests.test_discovery_ingestion_ledger import outer
   cfg=WindowConfig(max_transport_retries=0);scope=seed('SCOPE','DISCOVERY')
   with app.begin() as c:c.execute(W.update().where(W.c.key==scope).values(subject={'kind':'DISCOVERY_SCOPE','council':'bolton','start':cfg.start.isoformat(),'end':cfg.end.isoformat(),'semantics':'RECEIVED'},contract='bolton-idox-fixture'))
   bind([scope],source_calls=1);reader=SQLLedger(worker,owner='one',authority='INGESTION_TEST_sql',bindings=bindings,broker_engine=broker)
   discovery=Coordinator(reader,{'bolton-idox-fixture':IdoxListingContract('bolton-idox-fixture',cfg,'a'*64)})
   children=discovery.idox_source(reader.claim(scope),lambda _: (audit(cfg),outer()));assert len(children)==2
   with pytest.raises(Exception):reader.claim(children[0])
   bind([scope,*children])
   screener=SQLLedger(worker,owner='one',authority='INGESTION_TEST_sql',bindings=bindings)
   screening=Coordinator(screener,{})
   for child in children:
    out=screening.screening(screener.claim(child));assert out['residential_dwelling_count'] is None
   assert all(screener.get(k)['state']=='COMPLETE' for k in children)
   # One concrete controller rehearsal. Only disposable bootstrap prepares the
   # exact three task bindings and allowance before the accounted controller.
   from tests.test_discovery_ingestion_acceptance import listing_audit
   from verification.ingestion_storage.operational_controller import DatabaseBudget,ControllerLedger,AcceptanceBinding,execute
   from app.ingestion.ledger import digest
   boot.execute("TRUNCATE public.applications CASCADE")
   source_audit=listing_audit(target);contract=IdoxListingContract('controller-idox',cfg,'a'*64)
   retained=contract.project(source_audit,outer(),DEFAULT_LIMITS);record=retained['records'][0]
   scope=seed('CONTROLLER_SCOPE','DISCOVERY')
   child=digest(dict(subject={'kind':'APPLICATION','council':'bolton','reference':target['reference']},task='SCREENING',contract='listing-screen-v1',revision=digest(record)))
   fact=seed('CONTROLLER_FACT','FACTUAL_REFRESH')
   with app.begin() as c:
    c.execute(W.update().where(W.c.key==scope).values(subject={'kind':'DISCOVERY_SCOPE','council':'bolton','start':cfg.start.isoformat(),'end':cfg.end.isoformat(),'semantics':'RECEIVED'},contract=contract.name))
    prototype=dict(c.execute(select(W).where(W.c.key==scope)).mappings().one());prototype.update(key=child,subject={'kind':'APPLICATION','council':'bolton','reference':target['reference']},task='SCREENING',contract='listing-screen-v1',revision=digest(record),dependencies=[scope],max_attempts=2)
    c.execute(W.insert().values(**prototype))
    c.execute(W.update().where(W.c.key==fact).values(subject=prototype['subject'],dependencies=[child]))
   from sqlalchemy.engine import URL
   from dataclasses import asdict
   import sys
   from verification.ingestion_storage.operational_supervisor import supervise
   urls=[URL.create('postgresql+psycopg',username=r,password=passwords.get(r,info['password']),host='127.0.0.1',port=5432,database=info['dbname']).render_as_string(hide_password=False) for r in ['ingestion_worker_login','ingestion_effect_login','ingestion_application_login']]
   fixed=AcceptanceBinding(scope,child,fact,target['reference'],target['source_url'],target['source_identifier'],digest(record))
   prior=None
   for phase in ['capture','execute']:
    authority='INGESTION_TEST_sql_'+phase
    bind([scope] if phase=='capture' else [scope,child,fact],source_calls=1,writes=0 if phase=='capture' else 2,authority=authority)
    plan=tmp_path/('plan-'+phase+'.json');root=tmp_path/('controller-'+phase);output=root/'worker-result.json'
    value=dict(mode=phase,authority=authority,binding=asdict(fixed),bindings=bindings,listing=source_audit,detail=raw_source,target=target,envelope=asdict(env),outer=outer(),prior_database_accounting=prior)
    plan.write_text(json.dumps(value,default=str))
    supervised=supervise([sys.executable,'-m','verification.ingestion_storage.operational_rehearsal','--plan',str(plan),'--output',str(output)],environment={'INGESTION_ACCEPTANCE_DISPOSABLE':'PG17_ONLY','INGESTION_ACCEPTANCE_FIXTURE_URLS':json.dumps(urls)},root=root)
    result=json.loads(output.read_bytes()) if output.exists() else {};account=result.get('database_accounting',{})
    record_property('controller_accounting_'+phase,json.dumps(account,sort_keys=True));record_property('controller_supervisor_'+phase,json.dumps(supervised,sort_keys=True));record_property('controller_operation_costs_'+phase,json.dumps(result.get('operation_command_costs',{}),sort_keys=True))
    assert supervised['cleanup']=='CLOSED' and supervised['exit_code']==0 and supervised['limit_hit'] is None, (supervised,result)
    assert account['cleanup']=='CLOSED' and account['connection_attempts']<=16 and account['driver_statements']<=120
    if phase=='capture':
     assert result['outcome']=='DISCOVERY_SCREENING_ONLY' and result['synthetic_reader_callbacks']=={'listing':1,'detail':0}
     assert boot.execute('SELECT count(*) FROM public.applications').fetchone()[0]==0
     prior=account;fixed=replace(fixed,retained_capture_sha256=result['checkpoint_sha256'],prior_accounting_sha256=digest(account))
    else:
     assert result['outcome']=='SUPPORTED_FACTS_VERIFIED' and result['synthetic_reader_callbacks']=={'listing':0,'detail':1}
     assert account['driver_statements']>prior['driver_statements'] and account['connection_attempts']>prior['connection_attempts']
   # Complete three-row capture survives an owned-process interruption after
   # the first committed child. Subsequent bounded phases have source_calls=0.
   multi=listing_audit(target,refs=('01780/26','01781/26','01782/26'))
   projected_multi=contract.project(multi,outer(),DEFAULT_LIMITS)
   scope_multi=seed('MULTI_SCOPE','DISCOVERY');keys=[];prepared_multi={}
   with app.begin() as c:
    c.execute(W.update().where(W.c.key==scope_multi).values(subject={'kind':'DISCOVERY_SCOPE','council':'bolton','start':cfg.start.isoformat(),'end':cfg.end.isoformat(),'semantics':'RECEIVED'},contract=contract.name))
   # Only root is queued initially; children are created by actual coordinator.
   for r in projected_multi['records']:
    identity=dict(subject={'kind':'APPLICATION','council':'bolton','reference':r['reference']},task='SCREENING',contract='listing-screen-v1',revision=digest(r))
    keys.append(digest(identity));prepared_multi[keys[-1]]=identity
   fixed_multi=replace(fixed,discovery_key=scope_multi,retained_capture_sha256=None,prior_accounting_sha256=None)
   prior_multi=None;before_apps=boot.execute('SELECT count(*) FROM public.applications').fetchone()[0]
   for phase in ['interrupted_capture','resume','duplicate_delivery']:
    if phase=='interrupted_capture':bind([scope_multi],source_calls=1,authority='INGESTION_TEST_multi_capture')
    else:bind([scope_multi,*keys],source_calls=0,authority='INGESTION_TEST_multi_resume',prepared=prepared_multi)
    reader.bindings=bindings
    plan=tmp_path/('multi-'+phase+'.json');root=tmp_path/('multi-worker-'+phase);output=root/'worker-result.json'
    value=dict(mode='capture' if phase=='interrupted_capture' else 'resume_capture',authority='INGESTION_TEST_multi_capture' if phase=='interrupted_capture' else 'INGESTION_TEST_multi_resume',binding=asdict(fixed_multi),bindings=bindings,listing=multi,detail=raw_source,target=target,envelope=asdict(env),outer=outer(),prior_database_accounting=prior_multi,screening_keys=keys,interrupt_after_children=1 if phase=='interrupted_capture' else None)
    plan.write_text(json.dumps(value,default=str))
    supervised=supervise([sys.executable,'-m','verification.ingestion_storage.operational_rehearsal','--plan',str(plan),'--output',str(output)],environment={'INGESTION_ACCEPTANCE_DISPOSABLE':'PG17_ONLY','INGESTION_ACCEPTANCE_FIXTURE_URLS':json.dumps(urls)},root=root)
    result=json.loads(output.read_bytes());account=result['database_accounting']
    record_property('multi_accounting_'+phase,json.dumps(account,sort_keys=True));record_property('multi_supervisor_'+phase,json.dumps(supervised,sort_keys=True));record_property('multi_operation_costs_'+phase,json.dumps(result.get('operation_command_costs',{}),sort_keys=True))
    assert supervised['cleanup']=='CLOSED' and supervised['live_owned_survivors']==0 and account['cleanup']=='CLOSED'
    assert account['driver_statements']<=120 and account['connection_attempts']<=16
    if phase=='interrupted_capture':
     assert supervised['exit_code']!=0 and result['error_class']=='SystemExit'
     assert result['synthetic_reader_callbacks']=={'listing':1,'detail':0}
     retained_row=reader.get(scope_multi);assert len(retained_row['checkpoint']['records'])==3
     assert account['capture_checkpoint_sha256']==digest(retained_row['checkpoint'])
     # Reconciliation sees the closed owned process and certain checkpoint;
     # only disposable owner expires/reconciles the original claim.
     boot.execute('UPDATE public.ingestion_work_items SET lease_until=0 WHERE key=%s',(scope_multi,))
     recovery_budget=DatabaseBudget(previous=account)
     recovery_url=URL.create('postgresql+psycopg',username='ingestion_recovery_login',password=passwords['ingestion_recovery_login'],host='127.0.0.1',port=5432,database=info['dbname']).render_as_string(hide_password=False)
     recovery_engine=recovery_budget.engine(recovery_url)
     try:
      with recovery_engine.begin() as recovery:recovered=recovery.execute(text('SELECT public.ingestion_recover_abandoned(:key,:fence,true)'),{'key':scope_multi,'fence':retained_row['fence']}).scalar_one()
     finally:account=recovery_budget.close([recovery_engine])
     record_property('multi_accounting_recovery',json.dumps(account,sort_keys=True))
     assert account['cleanup']=='CLOSED' and account['driver_statements']<=120
     assert recovered['state']=='DEFERRED' and recovered['checkpoint']==retained_row['checkpoint']
    else:
     assert supervised['exit_code']==0 and result['outcome']=='DISCOVERY_SCREENING_ONLY'
     assert result['synthetic_reader_callbacks']=={'listing':0,'detail':0} and len(result['screening'])==3
     if phase=='resume':completed_attempts=boot.execute('SELECT count(*) FROM public.ingestion_work_attempts').fetchone()[0]
     else:assert boot.execute('SELECT count(*) FROM public.ingestion_work_attempts').fetchone()[0]==completed_attempts
     assert all(reader.get(k)['state']=='COMPLETE' for k in keys)
    prior_multi=account;fixed_multi=replace(fixed_multi,retained_capture_sha256=account['capture_checkpoint_sha256'],prior_accounting_sha256=digest(account))
   assert boot.execute('SELECT count(*) FROM public.applications').fetchone()[0]==before_apps
   assert boot.execute('SELECT count(*) FROM public.ingestion_work_items WHERE key=ANY(%s)',(keys,)).fetchone()[0]==3
   # Exact completed-day source capture, twelve five-row SQL batches, mixed
   # deterministic outcomes/citations, scoped original-stop exception.
   from tests.test_discovery_ingestion_batching import sixty_rows
   from app.ingestion.batching import batch_plans
   import hashlib,subprocess
   fixture_baseline=dict(fixture_costs);practical_started=time.monotonic()
   application_count_before=boot.execute('SELECT count(*) FROM public.applications').fetchone()[0]
   cfg60,audit60=sixty_rows();root60=seed('PRACTICAL_CAPTURE','DISCOVERY')
   scope60={'kind':'DISCOVERY_SCOPE','council':'bolton','start':'2026-10-16','end':'2026-10-16','semantics':'RECEIVED'}
   with app.begin() as c:
    c.execute(W.update().where(W.c.key==root60).values(subject=scope60,contract='controller-idox'))
    control=c.execute(select(W.c.outcome).where(W.c.key=='0'*64)).scalar_one()
    original_stop={'reason':'CONSUMED_SALFORD_GLOBAL_STOP','run':'38884069913'}
    control.update(global_stop=original_stop,hard_stop_generation=0,bolton_exceptions={})
    c.execute(W.update().where(W.c.key=='0'*64).values(outcome=control))
   # Fixture-only owner capability, real non-superuser login. No production mapping.
   policy_role='ingestion_policy_fixture';extra.append(policy_role);passwords[policy_role]=secrets.token_urlsafe(48)
   boot.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD {}').format(sql.Identifier(policy_role),sql.Literal(passwords[policy_role])))
   boot.execute('GRANT ingestion_barrier_releaser TO ingestion_policy_fixture WITH ADMIN FALSE, INHERIT TRUE, SET FALSE')
   execution_binding=dict(revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),workflow_sha256=hashlib.sha256(Path('.github/workflows/stage4-discovery-offline.yml').read_bytes()).hexdigest(),manifest_sha256=digest({'capture':root60,'scope':scope60}))
   def scoped(keys,authority,*,source_calls=0,prepared=None):
    bind(keys,authority=authority,source_calls=source_calls,prepared=prepared)
    with app.begin() as c:
     control=c.execute(select(W.c.outcome).where(W.c.key=='0'*64)).scalar_one();grant=control['grants'][authority]
     grant.update(capture_key=root60,execution_binding=execution_binding,capture_only=bool(source_calls))
     grant['completion_outcomes']['LISTING_METADATA']=['BATCH_SCREENED']
     c.execute(W.update().where(W.c.key=='0'*64).values(outcome=control))
    payload=dict(authority=authority,transport='REQUESTS_IDOX',stop_checkpoint_sha256='a2345cf136fc92abf13bb55772f5c14a7a299b7f2b9cb0b89fe6037ccdb8a10e',grant_binding={k:v for k,v in grant.items() if k not in ('source_calls','writes')},**execution_binding)
    with connect('ingestion_worker_login') as denied:
     with pytest.raises(psycopg.Error) as err:denied.execute('SELECT public.ingestion_register_bolton_exception(%s::jsonb)',(json.dumps(payload),))
     assert err.value.sqlstate=='42501'
    for member in ['authority','transport','stop_checkpoint_sha256','revision','workflow_sha256','manifest_sha256']:
     with connect(policy_role) as owner:
      with pytest.raises(psycopg.Error,match='EXCEPTION_TYPES'):owner.execute('SELECT public.ingestion_register_bolton_exception(%s::jsonb)',(json.dumps(dict(payload,**{member:None})),))
    with connect(policy_role) as owner:owner.execute('SELECT public.ingestion_register_bolton_exception(%s::jsonb)',(json.dumps(payload),))
    return payload
   scoped([root60],'INGESTION_TEST_capture_once',source_calls=1)
   fixed60=replace(fixed,discovery_key=root60,retained_capture_sha256=None,prior_accounting_sha256=None)
   from verification.ingestion_storage.operational_controller import batch_allocation
   measured=[];source_callback_total=0;supervisions=[];allocation_receipts={};allocated_slots=[root60]
   def run60(label,mode,authority,batch_key=None,prior=None,interrupt=None,recovery_fence=None):
    nonlocal source_callback_total
    path=tmp_path/('practical-'+label+'.json');root=tmp_path/('practical-worker-'+label);output=root/'worker-result.json'
    slot=batch_key or root60
    if prior is not None and slot in allocation_receipts:
     old=allocation_receipts[slot]['database']
     assert all(prior[k]>=old[k] for k in ('driver_statements','connection_attempts','returned_data_value_bytes','elapsed_seconds'))
     allocation_receipts[slot]['database']=prior
    allocation=batch_allocation(allocated_slots,allocation_receipts,sealed_sha256=digest(allocation_receipts),slot_key=slot)
    remaining=allocation['remaining'];ceilings=dict(connections=min(16,remaining['connection_attempts']),statements=min(120,remaining['driver_statements']),returned_bytes=min(4*1024**2,remaining['returned_data_value_bytes']))
    slot_binding=replace(fixed60,prior_accounting_sha256=digest(prior) if prior else None)
    path.write_text(json.dumps(dict(mode=mode,authority=authority,binding=asdict(slot_binding),bindings=bindings,listing=audit60,detail=raw_source,target=target,envelope=asdict(env),outer=outer(),batch_key=batch_key,prior_database_accounting=prior,interrupt_batch_after=interrupt,database_ceilings=ceilings,recovery_fence=recovery_fence),default=str))
    phase_urls=urls+[recovery_url] if mode=='recover_batch' else urls
    supervision=supervise([sys.executable,'-m','verification.ingestion_storage.operational_rehearsal','--plan',str(path),'--output',str(output)],environment={'INGESTION_ACCEPTANCE_DISPOSABLE':'PG17_ONLY','INGESTION_ACCEPTANCE_FIXTURE_URLS':json.dumps(phase_urls)},root=root,seconds=min(165,300-allocation['totals']['supervised_seconds']))
    result=json.loads(output.read_bytes());account=result['database_accounting'];source_callback_total+=result['synthetic_reader_callbacks']['listing']
    assert supervision['cleanup']=='CLOSED' and supervision['live_owned_survivors']==0 and supervision['limit_hit'] is None
    assert account['cleanup']=='CLOSED' and account['driver_statements']<=120 and account['connection_attempts']<=16
    if interrupt is None:assert supervision['exit_code']==0,(label,result,supervision)
    else:assert supervision['exit_code']!=0 and result['error_class']=='SystemExit'
    exported_bytes=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    assert exported_bytes<=2*1024**2
    cumulative=allocation_receipts.get(slot,{}).get('supervised_seconds',0)+supervision['elapsed_seconds']
    allocation_receipts[slot]=dict(database=account,supervised_seconds=cumulative,cleanup=supervision['cleanup'])
    batch_allocation(allocated_slots,allocation_receipts,sealed_sha256=digest(allocation_receipts),slot_key=slot)
    supervisions.append(dict(label=label,exported_bytes=exported_bytes,worker_audit_bytes=output.stat().st_size,**supervision));return result,account
   captured,account60=run60('capture','capture_once','INGESTION_TEST_capture_once');measured.append(dict(slot='capture',**account60))
   capture60=captured['receipt'];assert len(capture60['records'])==60 and capture60['durable_archive']['readback_verified']
   plans60=batch_plans(root60,capture60);assert len(plans60)==12
   allocated_slots.extend(r['key'] for r in plans60)
   prepared60={}
   with app.begin() as c:
    prototype=dict(c.execute(select(W).where(W.c.key==root60)).mappings().one())
    for rowplan in plans60:
     full=dict(prototype,**rowplan);full.update(state='QUEUED',authority=None,owner=None,lease_until=None,attempt_count=0,fence=0,phase='IDLE',outcome=None)
     c.execute(W.insert().values(**full))
   for r in capture60['records']:
    identity=dict(subject={'kind':'APPLICATION','council':'bolton','reference':r['reference']},task='SCREENING',contract='listing-screen-v1',revision=digest(r));prepared60[digest(identity)]=identity
   sentinel=seed('POLICY_SENTINEL')
   queuekeys=[root60,*[r['key'] for r in plans60],*prepared60,sentinel]
   queue_payload=scoped(queuekeys,'INGESTION_TEST_queue60',prepared=prepared60)
   queue_client=SQLLedger(worker,owner='one',authority='INGESTION_TEST_queue60',bindings=bindings,broker_engine=broker)
   # Worker cannot forge protected progress or reuse source permission.
   first_claim=queue_client.claim(plans60[0]['key'])
   with pytest.raises(Exception):queue_client.checkpoint(first_claim,{'kind':'BATCH_PROGRESS_V1'})
   with pytest.raises(Exception):queue_client.intent(first_claim,'source_calls')
   # Reset ONLY disposable negative-test claim; accepted manifest execution
   # begins fresh. No production claim reset interface exists.
   boot.execute('DELETE FROM public.ingestion_work_attempts WHERE work_key=%s',(first_claim.key,))
   boot.execute("UPDATE public.ingestion_work_items SET state='QUEUED',owner=NULL,lease_until=NULL,attempt_count=0,fence=0,phase='IDLE' WHERE key=%s",(first_claim.key,))
   for ordinal,item in enumerate(plans60):
    if ordinal==1:
     interrupted,prior=run60('batch-interrupted','process_batch','INGESTION_TEST_queue60',item['key'],interrupt=item['checkpoint']['plan']['first'])
     current=queue_client.get(item['key']);assert current['checkpoint']['next']==item['checkpoint']['plan']['first']+1
     boot.execute('UPDATE public.ingestion_work_items SET lease_until=0 WHERE key=%s',(item['key'],))
     recovered,prior=run60('batch-recovery','recover_batch','INGESTION_TEST_queue60',item['key'],prior=prior,recovery_fence=current['fence'])
     assert recovered['recovered']['state']=='DEFERRED' and prior['cleanup']=='CLOSED'
     result,account=run60('batch-resumed','process_batch','INGESTION_TEST_queue60',item['key'],prior=prior)
    else:result,account=run60('batch-'+str(ordinal),'process_batch','INGESTION_TEST_queue60',item['key'])
    assert result['outcome']=='BATCH_SCREENED'
    if ordinal==0:
     attempt_total=boot.execute('SELECT count(*) FROM public.ingestion_work_attempts').fetchone()[0]
     dup,account=run60('batch-duplicate','process_batch','INGESTION_TEST_queue60',item['key'],prior=account)
     assert dup['outcome']=='BATCH_ALREADY_COMPLETE' and boot.execute('SELECT count(*) FROM public.ingestion_work_attempts').fetchone()[0]==attempt_total
    measured.append(dict(slot=item['key'],**account))
   screened=[queue_client.get(k) for k in prepared60];assert all(r['state']=='COMPLETE' for r in screened)
   from collections import Counter
   dispositions=Counter(r['checkpoint']['disposition'] for r in screened);citations=[x for r in screened for x in r['checkpoint']['citations']['occurrences']]
   assert dispositions=={'SUPPORTED_PROCESSING_PRIORITY':20,'RELATED_APPLICATION_FOLLOW_THROUGH':20,'INSUFFICIENT_EVIDENCE':20} and len(citations)==20
   assert all(x['literal']=='02000/26' for x in citations)
   assert source_callback_total==1 and digest(queue_client.get(root60)['checkpoint'])==digest(capture60)
   record_property('practical_accounts',json.dumps(measured,sort_keys=True));record_property('practical_supervisions',json.dumps(supervisions,sort_keys=True));record_property('practical_dispositions',json.dumps(dispositions,sort_keys=True));record_property('practical_citations',json.dumps(citations,sort_keys=True))
   aggregate={k:sum(x[k] for x in measured) for k in ['connection_attempts','driver_statements','returned_data_value_bytes','elapsed_seconds']}
   aggregate.update(supervised_seconds=sum(x['elapsed_seconds'] for x in supervisions),peak_owned_rss=max(x['peak_owned_rss'] for x in supervisions),exported_bytes=sum(x['exported_bytes'] for x in supervisions),worker_audit_bytes=sum(x['worker_audit_bytes'] for x in supervisions))
   assert aggregate['driver_statements']<=1040 and aggregate['connection_attempts']<=40 and aggregate['returned_data_value_bytes']<=4*1024**2
   assert aggregate['supervised_seconds']<=300 and aggregate['exported_bytes']<=2*1024**2
   record_property('practical_aggregate',json.dumps(aggregate,sort_keys=True));record_property('practical_capture_sha256',digest(capture60))
   record_property('practical_allocation_receipts',json.dumps(allocation_receipts,sort_keys=True))
   capacity=boot.execute("SELECT (SELECT sum(octet_length(to_jsonb(w)::text)) FROM public.ingestion_work_items w WHERE key=ANY(%s)),(SELECT sum(octet_length(to_jsonb(a)::text)) FROM public.ingestion_work_attempts a WHERE work_key=ANY(%s)),pg_total_relation_size('public.ingestion_work_items')+pg_total_relation_size('public.ingestion_work_attempts'),(SELECT count(*) FROM public.ingestion_work_attempts WHERE work_key=ANY(%s))",(queuekeys,queuekeys,queuekeys)).fetchone()
   record_property('practical_capacity',json.dumps(dict(scope_items=len(queuekeys),scope_item_serialized_bytes=capacity[0],scope_attempt_serialized_bytes=capacity[1],whole_fixture_physical_bytes=capacity[2],scope_attempts=capacity[3],note='74includes_unexecuted_policy_sentinel;physical_includes_preceding_fixture_work'),sort_keys=True))
   # Exact grant mutation/expiry/other council denial, registration cannot extend.
   with connect(policy_role) as owner:
    with pytest.raises(psycopg.Error):owner.execute('SELECT public.ingestion_register_bolton_exception(%s::jsonb)',(json.dumps(queue_payload),))
   def sentinel_claim(expected=None):
    with connect('ingestion_worker_login') as probe:
     probe.autocommit=False
     try:
      if expected:
       with pytest.raises(psycopg.Error,match=expected):probe.execute("SELECT public.ingestion_worker_step('claim',%s,0,'one','INGESTION_TEST_queue60',%s::jsonb,'{\"lease_seconds\":165}')",(sentinel,json.dumps(bindings[sentinel])))
      else:
       result=probe.execute("SELECT public.ingestion_worker_step('claim',%s,0,'one','INGESTION_TEST_queue60',%s::jsonb,'{\"lease_seconds\":165}')",(sentinel,json.dumps(bindings[sentinel]))).fetchone()[0]
       assert result['state']=='CLAIMED'
     finally:probe.rollback()
    assert boot.execute('SELECT attempt_count FROM public.ingestion_work_items WHERE key=%s',(sentinel,)).fetchone()[0]==0
   sentinel_claim()  # Otherwise eligible: rollback preserves the exact baseline.
   pristine=boot.execute("SELECT outcome::jsonb FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
   with app.begin() as c:
    control=c.execute(select(W.c.outcome).where(W.c.key=='0'*64)).scalar_one();assert control['global_stop']==original_stop
    control['grants']['INGESTION_TEST_queue60']['execution_binding']['revision']='f'*40
    c.execute(W.update().where(W.c.key=='0'*64).values(outcome=control))
   sentinel_claim('GLOBAL_STOP')
   assert boot.execute('SELECT count(*) FROM public.applications').fetchone()[0]==application_count_before
   boot.execute("UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(pristine),))
   expired=json.loads(json.dumps(pristine));expired['bolton_exceptions']['INGESTION_TEST_queue60']['expires_at']=0
   boot.execute("UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(expired),))
   sentinel_claim('GLOBAL_STOP')
   record_property('practical_fixture_harness',json.dumps({**{k:fixture_costs[k]-fixture_baseline[k] for k in fixture_costs},'elapsed_seconds':round(time.monotonic()-practical_started,3),'metric':'setup_and_assertion_cursor_calls_excludes_driver_internal_and_controller_calls'},sort_keys=True))
   boot.execute("UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(pristine),))
   boot.execute("UPDATE public.ingestion_work_items SET subject=jsonb_set(subject::jsonb,'{council}','\"salford\"')::json WHERE key=%s",(sentinel,))
   sentinel_claim('GLOBAL_STOP')
   boot.execute("UPDATE public.ingestion_work_items SET subject=%s::json WHERE key=%s",(json.dumps(bindings[sentinel]['subject']),sentinel))
   sentinel_claim()
   with connect('ingestion_worker_login') as stopping:stopping.execute("SELECT public.ingestion_raise_stop('SECURITY_OR_UNCERTAIN_COMMIT')")
   after_stop=boot.execute("SELECT outcome::jsonb FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
   assert after_stop['global_stop']==original_stop and after_stop['hard_stop_generation']==1
   with connect(policy_role) as owner:
    with pytest.raises(psycopg.Error):owner.execute('SELECT public.ingestion_register_bolton_exception(%s::jsonb)',(json.dumps(dict(queue_payload,authority='fresh')),))
   sentinel_claim('GLOBAL_STOP')
   # Return to the original disposable fixture's independent remaining tests.
   with app.begin() as c:
    control=c.execute(select(W.c.outcome).where(W.c.key=='0'*64)).scalar_one();control.update(global_stop=None,bolton_exceptions={},hard_stop_generation=0)
    c.execute(W.update().where(W.c.key=='0'*64).values(outcome=control))
   with connect('ingestion_application_login') as aw:
    for statement in ["UPDATE public.applications SET estimated_unit_count=999","UPDATE public.applications SET site_id=NULL","DELETE FROM public.applications","SELECT * FROM public.ingestion_work_items","SET ROLE ingestion_storage_owner","SELECT public.ingestion_worker_step('claim','x',0,'x','x','{}','{}')"]:
     with pytest.raises(psycopg.Error) as denied:aw.execute(statement)
     assert denied.value.sqlstate=='42501'
   # The restricted worker cannot forge a detail receipt or bypass source intent.
   bypass=seed('BYPASS','FACTUAL_REFRESH');bind([bypass],source_calls=1,writes=2)
   neg=SQLLedger(worker,owner='one',authority='INGESTION_TEST_sql',bindings=bindings,broker_engine=broker)
   nc=neg.claim(bypass)
   with pytest.raises(Exception):neg.intent(nc,'writes',cost=2)
   with pytest.raises(Exception):neg.checkpoint(nc,{'kind':'DETAIL_RECEIPT_V1'})
   for mode in ['unsupported','known_race']:
    boot.execute('TRUNCATE public.applications CASCADE')
    check_fact=seed('DETAIL_'+mode,'FACTUAL_REFRESH')
    boot.execute('UPDATE public.ingestion_work_items SET subject=%s,dependencies=%s WHERE key=%s',(json.dumps({'kind':'APPLICATION','council':'bolton','reference':target['reference']}),json.dumps([child]),check_fact))
    bind([scope,child,check_fact],source_calls=1,writes=2)
    checker=SQLLedger(worker,owner='one',authority='INGESTION_TEST_sql',bindings=bindings,application_engine=app,broker_engine=broker)
    check_co=Coordinator(checker,{'operational-fixture':accepted_idox_new_identity('operational-fixture',target)})
    if mode=='unsupported':
     _,detail,_=projected(summary('01780/26',status='Awaiting decision',omit=('Decision','Decision Issued Date')))
    else:detail=raw_source
    def callback(_):
     if mode=='known_race':
      with Session(app) as fixture:fixture.add(Application(council_code='bolton',reference=target['reference'],status='PRESERVED'));fixture.commit()
     return detail,outer()
    honest=check_co.new_identity_source(checker.claim(check_fact),envelope=env,council=get_council('bolton'),supervised_reader=callback)
    assert honest['outcome']==('FACTS_WITHHELD' if mode=='unsupported' else 'ALREADY_KNOWN')
    assert checker.get(check_fact)['checkpoint']['kind']=='DETAIL_RECEIPT_V1'
    assert checker.get(check_fact)['state']==('UNSUPPORTED_CONTRACT' if mode=='unsupported' else 'COMPLETE')
   # Abandoned write intent is recovered as uncertain, globally stops next work.
   uncertain=seed('UNCERTAIN','FACTUAL_REFRESH');bind([uncertain,other],writes=1)
   x=SQLLedger(worker,owner='one',authority='INGESTION_TEST_sql',bindings=bindings);cl=x.claim(uncertain);x.intent(cl,'writes')
   boot.execute('UPDATE public.ingestion_work_items SET lease_until=0 WHERE key=%s',(uncertain,))
   with connect('ingestion_recovery_login') as recovery:r=recovery.execute('SELECT public.ingestion_recover_abandoned(%s,%s,true)',(uncertain,cl.fence)).fetchone()[0]
   assert r['state']=='PERSISTENCE_UNCERTAIN'
   with pytest.raises(Exception):x.claim(other)
   with connect('provisioning_migrator') as migration:migration.execute(Path('docs/design/ingestion-operational-acceptance-20261016/revoke.sql').read_text())
   assert boot.execute("SELECT count(*) FROM pg_roles WHERE rolname IN ('ingestion_worker_login','ingestion_storage_login','ingestion_effect_login','ingestion_application_login','ingestion_recovery_login') AND rolcanlogin").fetchone()[0]==0
   record_property('real_restricted_sql_claims',True);record_property('shared_admission_b2_readback',True);record_property('production_connections',0)
  finally:
   for e in engines:e.dispose()
   # Bootstrap owns disposable teardown only; production rollback never drops.
   boot.execute('DROP TABLE IF EXISTS public.ingestion_work_attempts CASCADE');boot.execute('DROP TABLE IF EXISTS public.ingestion_work_items CASCADE')
   for e in engines:
    if e.url.username=='provisioning_bootstrap':Base.metadata.drop_all(e);e.dispose()
   for role in [*extra,*ROLES,'provisioning_migrator']:
    if boot.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone():boot.execute(sql.SQL('DROP OWNED BY {} CASCADE').format(sql.Identifier(role)))
   for role in [*extra,*ROLES,'provisioning_migrator']:
    boot.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(role)))
