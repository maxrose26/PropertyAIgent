"""Real PG17 restricted SQL capabilities and shared coordinator; fixed loopback only."""
import json,os,secrets,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import psycopg,pytest
from psycopg import sql
from sqlalchemy import create_engine,select,text
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


def test_restricted_sql_claims_fencing_checkpoints_completion_and_shared_new_identity(record_property):
 raw=os.environ.get('INGESTION_PROVISIONING_TEST_URL')
 if not raw:pytest.skip('fixed disposable PG17 service required')
 info=psycopg.conninfo.conninfo_to_dict(raw)
 assert (info.get('host'),info.get('port'),info.get('dbname'),info.get('user'))==('127.0.0.1','5432','ingestion_provisioning_test','provisioning_bootstrap')
 extra=['ingestion_effect_broker','ingestion_recovery_operator','operational_broker_login','operational_recovery_login','operational_untrusted']
 passwords={r:secrets.token_urlsafe(48) for r in ['provisioning_migrator','ingestion_worker_login','ingestion_storage_login',*extra[-3:]]}
 def connect(role):return psycopg.connect(**{**info,'user':role,'password':passwords[role]},autocommit=True,prepare_threshold=None,connect_timeout=3)
 def engine(role):
  from sqlalchemy.engine import URL
  return create_engine(URL.create('postgresql+psycopg',username=role,password=passwords.get(role,info['password']),host='127.0.0.1',port=5432,database=info['dbname']),poolclass=NullPool,connect_args={'connect_timeout':3,'prepare_threshold':None})
 engines=[]
 with psycopg.connect(raw,autocommit=True,connect_timeout=3) as boot:
  try:
   boot.execute(sql.SQL('CREATE ROLE provisioning_migrator LOGIN NOSUPERUSER NOCREATEDB CREATEROLE NOINHERIT NOBYPASSRLS PASSWORD {}').format(sql.Literal(passwords['provisioning_migrator'])))
   boot.execute('GRANT USAGE,CREATE ON SCHEMA public TO provisioning_migrator WITH GRANT OPTION')
   boot.execute('GRANT CONNECT ON DATABASE ingestion_provisioning_test TO provisioning_migrator WITH GRANT OPTION')
   with connect('provisioning_migrator') as m:
    m.execute((PACKAGE/'install.sql').read_text())
    m.execute(Path('docs/design/ingestion-operational-20261016/worker.sql').read_text())
    assert m.execute("SELECT pg_has_role(current_user,'ingestion_storage_owner','SET'),has_schema_privilege('ingestion_storage_owner','public','CREATE')").fetchone()==(False,False)
   # Fixture-only credential activation. Production helper remains BLOCKED.
   for role in ['ingestion_worker_login','ingestion_storage_login',*extra[-3:]]:
    if role not in ROLES:boot.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD {}').format(sql.Identifier(role),sql.Literal(passwords[role])))
    else:boot.execute(sql.SQL('ALTER ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role),sql.Literal(passwords[role])))
   boot.execute('GRANT ingestion_effect_broker TO operational_broker_login WITH ADMIN FALSE, INHERIT TRUE, SET FALSE')
   boot.execute('GRANT ingestion_recovery_operator TO operational_recovery_login WITH ADMIN FALSE, INHERIT TRUE, SET FALSE')
   worker=engine('ingestion_worker_login');broker=engine('operational_broker_login');app=engine('provisioning_bootstrap');engines.extend([worker,broker,app])
   Base.metadata.create_all(app)
   with Session(app) as s:s.add(Council(code='bolton',name='Bolton',base_url='https://paplanning.bolton.gov.uk',date_field_mode='received',doc_system='idox'));s.commit()
   # Bootstrap constructs fixtures/allowances only; no worker release API exists.
   def seed(reference,task='SCREENING',state='QUEUED',checkpoint=None):
    key=__import__('hashlib').sha256((reference+task).encode()).hexdigest()
    row=dict(key=key,subject={'kind':'APPLICATION','council':'bolton','reference':reference},task=task,contract='operational-fixture',revision='v1',dependencies=[],priority=50,eligible_at=0,state=state,reason='FIXTURE' if state!='QUEUED' else None,next_action='FIXTURE',limits=DEFAULT_LIMITS,authority=None,attempt_count=0,max_attempts=3,fence=0,owner=None,lease_until=None,phase='IDLE',checkpoint=checkpoint,outcome=None)
    with app.begin() as c:c.execute(W.insert().values(**row))
    return key
   k=seed('ONE');blocked=seed('BLOCKED',state='SAFETY_BLOCKED');other=seed('OTHER')
   bindings={}
   def bind(keys,*,writes=0,source_calls=0):
    nonlocal bindings
    with app.begin() as c:
     for key in keys:
      row=c.execute(select(W).where(W.c.key==key)).mappings().one();bindings[key]={x:row[x] for x in ('task','contract','revision','subject')}
     control=c.execute(select(W.c.outcome).where(W.c.key=='0'*64)).scalar_one()
     control['grants']['INGESTION_TEST_sql']={'keys':keys,'contracts':sorted({bindings[x]['contract'] for x in keys}),'expires_at':time.time()+600,'source_calls':source_calls,'writes':writes,'login':'ingestion_worker_login','effect_login':'operational_broker_login','workers':['one','two'],'bindings':{key:bindings[key] for key in keys},'completion_outcomes':{'DISCOVERY':['ENUMERATED_METADATA_RETAINED'],'SCREENING':['SCREENED','ALREADY_KNOWN','INSUFFICIENT_EVIDENCE','SUPPORTED_PROCESSING_PRIORITY','RELATED_APPLICATION_FOLLOW_THROUGH','DEEPER_PROCESSING_EXCLUDED_FOR_THIS_SLICE'],'FACTUAL_REFRESH':['SUPPORTED_FACTS_VERIFIED','ALREADY_KNOWN']}}
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
   with connect('operational_recovery_login') as recovery:result=recovery.execute('SELECT public.ingestion_recover_abandoned(%s,%s,true)',(k,old.fence)).fetchone()[0]
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
   # Abandoned write intent is recovered as uncertain, globally stops next work.
   uncertain=seed('UNCERTAIN','FACTUAL_REFRESH');bind([uncertain,other],writes=1)
   x=SQLLedger(worker,owner='one',authority='INGESTION_TEST_sql',bindings=bindings);cl=x.claim(uncertain);x.intent(cl,'writes')
   boot.execute('UPDATE public.ingestion_work_items SET lease_until=0 WHERE key=%s',(uncertain,))
   with connect('operational_recovery_login') as recovery:r=recovery.execute('SELECT public.ingestion_recover_abandoned(%s,%s,true)',(uncertain,cl.fence)).fetchone()[0]
   assert r['state']=='PERSISTENCE_UNCERTAIN'
   with pytest.raises(Exception):x.claim(other)
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
