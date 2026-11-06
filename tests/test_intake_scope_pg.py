"""Disposable PG17, actual issuer/activation/worker/supervisor and archive readback.

Only council responses and provider integration are synthetic; no live source.
"""
import copy, hashlib, json, os
from datetime import date
from types import SimpleNamespace
from contextlib import contextmanager
import pytest
from tests.test_period10_successor_pg import ready10, exercise_owner_runtime
from tests.test_period09_settlement_pg import failed09
from tests.test_period09_successor_pg import ready09
from tests.test_period08_settlement_pg import failed08,backlog
from tests.test_period08_successor_pg import settled08
from tests.test_period07_settlement_pg import failed07
from tests.test_attempt06_owner_path_pg import world, Fault
from tests.e2e_connection_support import idox_audit,entry,SCHEME
from verification.ingestion_storage import intake_successor as sc, intake_owner as op, intake_owner_operations as extra, owner_pilot as pilot
from verification.ingestion_storage.daily_intake_runtime import Runtime, execution_binding, main
from verification.ingestion_storage.owner_pilot_continuation import migrate_owner_namespace

@pytest.fixture
def succeeded10(ready10,tmp_path,monkeypatch):
 w=ready10;c=w['boot']
 monkeypatch.delenv('P10_LOOPBACK_CAPTURE',raising=False)
 exercise_owner_runtime(w,tmp_path/'prior',monkeypatch,False,record_count=35)
 ctl=op.control(c);marker=ctl['intake_run'];key=ctl['intake_periods'][sc.PREDECESSOR]['days']['2026-11-02']['manchester']
 receipt=c.execute('SELECT checkpoint::jsonb FROM ingestion_work_items WHERE key=%s',(key,)).fetchone()[0]
 for name,value in dict(RUN=marker['id'],CAPTURE=key,CAPTURE_SHA=sc.sha(receipt),SOURCE_SHA=receipt['source_sha256'],FINAL_SHA=marker['publication']['sha256'],BINDING=execution_binding()).items():monkeypatch.setattr(sc,name,value)
 for name in ('PERIOD','PREDECESSOR','OWNER_PERIOD','OWNER_RUN','WINDOW'):monkeypatch.setattr(pilot,name,getattr(pilot,name))
 sc.configure();release=dict(execution_binding=sc.BINDING,tree=sc.TREE,branch=sc.BRANCH,deployment='dep-'+'a'*20)
 monkeypatch.setenv('PROPERTYAIGENT_INTAKE_SOURCE_RELEASE',json.dumps(release))
 b,p=pilot.fixed_binding(release,w['binding']['render_profile'],w['binding']['hostaddr'],'a'*64)
 b.update(credential_policy='STABLE_RESTRICTED_V1',credential_verifier_sha256=w['binding']['credential_verifier_sha256'])
 w.update(binding=b,policy=p,marker=copy.deepcopy(marker),prior_control=copy.deepcopy(ctl))
 w['preserved']=c.execute('SELECT key,state,phase,fence,checkpoint::text,outcome::text FROM ingestion_work_items WHERE key<>%s ORDER BY key',(op.CONTROL,)).fetchall()
 w['evidence']=c.execute('SELECT period,run_id,name,sha256 FROM ingestion_run_evidence ORDER BY period,run_id,name').fetchall()
 w['members']=c.execute(op.MEMBERS).fetchall()
 return w

def issue(w):
 b=w['binding'];p=w['policy']
 with w['actor']() as c:migrate_owner_namespace(c,scope_binding=b,stable_verifiers=b['credential_verifier_sha256'])
 with w['actor']() as c:extra.issue_period(c,b,p,dict(version='FINITE_INTAKE_PERIOD_V1',state='ARMED_NO_RETRY',binding=b,policy=p),lambda _:None)

@pytest.mark.parametrize('mode',['normal','before','lost'])
def test_success_archive_atomic_and_readback(succeeded10,mode):
 w=succeeded10;c=w['boot'];b=w['binding'];p=w['policy']
 with w['actor']() as actor:migrate_owner_namespace(actor,scope_binding=b,stable_verifiers=b['credential_verifier_sha256'])
 before=op.ledger_sha(c)
 with w['actor']() as actor:
  if mode=='normal':extra.issue_period(actor,b,p,dict(version='FINITE_INTAKE_PERIOD_V1',state='ARMED_NO_RETRY',binding=b,policy=p),lambda _:None)
  else:
   with pytest.raises(Exception):extra.issue_period(Fault(actor,mode),b,p,dict(version='FINITE_INTAKE_PERIOD_V1',state='ARMED_NO_RETRY',binding=b,policy=p),lambda _:None)
 with w['actor']() as fresh:result=sc.inspect(fresh,b)
 ctl=op.control(c)
 if mode=='before':assert op.ledger_sha(c)==before and result['status']=='UNUSED_SUCCESSOR_VERIFIED'
 else:
  assert result['status']=='REGISTERED_READBACK_NO_RETRY'
  assert ctl['intake_periods'][sc.PREDECESSOR]['verified_run']==w['marker']==ctl['intake_run']
  with w['actor']() as actor:
   with pytest.raises(op.Denied):extra.issue_period(actor,b,p,dict(version='FINITE_INTAKE_PERIOD_V1',state='ARMED_NO_RETRY',binding=b,policy=p),lambda _:None)
 assert c.execute(op.MEMBERS).fetchall()==w['members']
 assert c.execute('SELECT period,run_id,name,sha256 FROM ingestion_run_evidence ORDER BY period,run_id,name').fetchall()==w['evidence']

@pytest.mark.parametrize('incomplete',[False,True,'retained-recovery','startup-boundary'])
def test_actual_bolton_entry_capture_screen_backlog_close(succeeded10,tmp_path,monkeypatch,incomplete):
 w=succeeded10;c=w['boot'];b=w['binding'];p=w['policy']
 from scripts import owner_intake_scope
 class DB:
  @contextmanager
  def connection(self):
   with w['actor']() as actor:yield actor
 monkeypatch.setattr(pilot,'Database',DB);monkeypatch.setattr(sc,'binding_from_saved_state',lambda db:b)
 monkeypatch.setenv('PROPERTYAIGENT_OWNER_PILOT_AUTHORITY',sc.SCOPE.period)
 assert owner_intake_scope.main(['--action','inspect'])==0
 issue(w)
 passwords={r:__import__('sqlalchemy').engine.make_url(w['urls'][r]).password for r in op.ROLES};states=[]
 with w['actor']() as actor:
  prepared=op.prepare_activation(actor,b,stable_credentials=passwords);op.activate(actor,b,lambda v:states.append(copy.deepcopy(v)),prepared=prepared)
 for role,var in [('ingestion_worker_login','INGESTION_WORKER_DATABASE_URL'),('ingestion_effect_login','INGESTION_EFFECT_DATABASE_URL')]:monkeypatch.setenv(var,w['urls'][role])
 monkeypatch.delenv('DATABASE_URL',raising=False)
 # The real reader produces the synthetic transport audit; the actual runtime
 # collect -> supervisor -> credential-free worker path is retained below.
 audit=idox_audit('bolton',[entry(f'B/{i}/26',SCHEME) for i in range(24)],date(2026,11,3),date(2026,11,5))
 if os.environ.get('BOLTON_WORKER_AUDIT'):
  audit=json.loads(__import__('pathlib').Path(os.environ['BOLTON_WORKER_AUDIT']).read_text())
  assert len(audit['records'])==24 and audit['resource']['requests_attempted']==6
 if incomplete is True:audit['enumeration_evidence']='TOTAL_UNKNOWN'
 fixture=tmp_path/'bolton-response.json';fixture.write_text(json.dumps(audit))
 import verification.ingestion_storage.daily_intake_runtime as module
 original=module.supervise;calls=[]
 def synthetic_transport(argv,**kwargs):
  plan_path=__import__('pathlib').Path(argv[argv.index('--plan')+1]);plan=json.loads(plan_path.read_text())
  assert plan==dict(row=sc.SCOPE.row(),fixture=None)
  plan['fixture']=str(fixture);plan_path.write_text(json.dumps(plan));calls.append(plan['row'])
  return original(argv,**kwargs)
 monkeypatch.setattr(module,'supervise',synthetic_transport)
 monkeypatch.setattr(module,'require_source_context',lambda *a,**kw:None)
 args=SimpleNamespace(period=sc.SCOPE.period,output=str(tmp_path/'canary'),hostaddr=b['hostaddr'],disposable_sources=None,disposable_archive=None,backlog=False,after=None,page_size=3)
 runtime=Runtime(args);runtime.route_name=b['route']
 argv=['--period',args.period,'--output',args.output,'--hostaddr',args.hostaddr]
 recovery=[]
 if incomplete=='retained-recovery':
  actual_slot=module.intake_slot
  def interrupted_slot(caller,key,collect,archive,prepare,**kw):
   def interrupt(receipt):
    recovery.append(receipt['source_sha256']);raise RuntimeError('SYNTHETIC_AFTER_DURABLE_CAPTURE')
   with pytest.raises(RuntimeError,match='SYNTHETIC_AFTER_DURABLE_CAPTURE'):
    actual_slot(caller,key,collect,archive,interrupt,**kw)
   # Existing retained-capture recovery entry; fresh worker read, no source replay.
   return actual_slot(caller,key,lambda _:pytest.fail('SOURCE_REPLAY'),archive,prepare,**kw)
  monkeypatch.setattr(module,'intake_slot',interrupted_slot)
 if incomplete=='startup-boundary':
  import time as real_time
  monkeypatch.setattr(module,'time',SimpleNamespace(time=lambda:b['valid_until']-1500,monotonic=real_time.monotonic))
 result_code=main(argv,prepared_runtime=runtime)
 result=json.loads((runtime.root/'final-result.json').read_text())
 if incomplete=='startup-boundary':
  assert result_code==1 and result['reason']=='DATABASE_PILOT_STARTUP_RESERVE'
  assert calls==[] and op.control(c)['intake_run']==w['marker']
  with w['actor']() as actor:closed=op.close(actor,states[-1],lambda _:None)
  assert closed['runtime_access']=='DISABLED' and closed['sessions']=='ABSENT'
  return
 assert result_code==(1 if incomplete is True else 0),json.dumps({k:result.get(k) for k in ('status','reason','failure','cleanup','scopes','finalisation_failure')})
 assert calls==[sc.SCOPE.row()]
 assert result['usage']['requests']==audit['resource']['requests_attempted']<=10
 assert result['usage']['all_connections_closed'] is True
 ctl=op.control(c);assert ctl['intake_periods'][sc.PREDECESSOR]['verified_run']==w['marker']
 if incomplete is not True:assert op.stop_snapshot(ctl)==sc.ACCEPTED
 else:assert ctl['global_stop']['reason']=='DAILY_INTAKE_SHARED_FAILURE'
 if incomplete is not True:
  assert ctl['intake_run']['state']=='VERIFIED'
  with w['actor']() as actor:verified=op.finalisation(actor,b,dict(run_id=ctl['intake_run']['id'],publication=ctl['intake_run']['publication']))
  assert verified['captures'][0]['screening_complete']==24
  key=ctl['intake_periods'][sc.SCOPE.period]['days'][sc.SCOPE.end]['bolton']
  receipt=c.execute('SELECT checkpoint::jsonb FROM ingestion_work_items WHERE key=%s',(key,)).fetchone()[0]
  a=receipt['durable_archive'];raw=bytes(c.execute('SELECT body FROM ingestion_run_evidence WHERE period=%s AND run_id=%s AND name=%s',(a['period'],a['run_id'],a['name'])).fetchone()[0])
  assert hashlib.sha256(raw).hexdigest()==a['sha256']==receipt['source_sha256']
  from app.ingestion.daily_intake import backlog_page
  from app.ingestion.sql_ledger import SQLLedger
  from app.ingestion.listing_screening import ScreeningRule,RULE_V3
  page=backlog_page(SQLLedger(w['app'],owner='test',authority='',bindings={}),['bolton'],[sc.SCOPE.contract],ScreeningRule(RULE_V3,unit_threshold=10,link_related=False))
  assert len(page['records'])==24 and all(r['archive']['period']==sc.SCOPE.period for r in page['records'])
  if incomplete=='retained-recovery':assert recovery==[receipt['source_sha256']]
  # Preserve two historical assessment sets. Scope by explicit contract; never
  # choose a version by ordering or silently erase ambiguous history.
  legacy='e'*64;legacy_contract='bolton-received-idox-coordinator-v1'
  patch=dict(key=legacy,contract=legacy_contract)
  c.execute("INSERT INTO ingestion_work_items SELECT (jsonb_populate_record(NULL::ingestion_work_items,to_jsonb(w)||%s::jsonb)).* FROM ingestion_work_items w WHERE key=%s",(json.dumps(patch),key))
  for index in range(2):
   patch=dict(key=str(index+1)*64,dependencies=[legacy])
   c.execute("INSERT INTO ingestion_work_items SELECT (jsonb_populate_record(NULL::ingestion_work_items,to_jsonb(w)||%s::jsonb)).* FROM ingestion_work_items w WHERE dependencies::jsonb=%s::jsonb AND task='SCREENING' ORDER BY key LIMIT 1",(json.dumps(patch),json.dumps([key])))
  ledger=SQLLedger(w['app'],owner='test',authority='',bindings={});rule=ScreeningRule(RULE_V3,unit_threshold=10,link_related=False)
  with pytest.raises(op.Denied,match='BACKLOG_MULTIPLE_ASSESSMENTS'):backlog_page(ledger,['bolton'],[legacy_contract],rule)
  assert len(backlog_page(ledger,['bolton'],[sc.SCOPE.contract],rule)['records'])==24
  assert c.execute("SELECT count(*) FROM ingestion_work_items WHERE dependencies::jsonb=%s::jsonb",(json.dumps([legacy]),)).fetchone()==(2,)

  duplicate=Runtime(SimpleNamespace(**{**vars(args),'output':str(tmp_path/'duplicate')}));duplicate.route_name=b['route'];duplicate.collect=lambda _:pytest.fail('RECOLLECTION')
  before=op.ledger_sha(c);assert duplicate.execute()['reason']=='SCOPE_ALREADY_CONSUMED';assert op.ledger_sha(c)==before
 else:assert ctl['intake_run']['state']!='VERIFIED'
 with w['actor']() as actor:closed=op.close(actor,states[-1],lambda _:None)
 assert closed['runtime_access']=='DISABLED' and closed['sessions']=='ABSENT'
 assert c.execute(op.MEMBERS).fetchall()==w['members']
 # All prior work, including 35 Manchester and 24 Tameside, byte-identical.
 for row in w['preserved']:
  assert c.execute('SELECT key,state,phase,fence,checkpoint::text,outcome::text FROM ingestion_work_items WHERE key=%s',(row[0],)).fetchone()==row
 assert set(w['evidence']).issubset(set(c.execute('SELECT period,run_id,name,sha256 FROM ingestion_run_evidence').fetchall()))

@pytest.mark.parametrize('change',['council','window','stop','predecessor','used'])
def test_sql_admission_refuses_changed_scope(succeeded10,change):
 w=succeeded10;c=w['boot'];b=w['binding'];policy=copy.deepcopy(w['policy'])
 with w['actor']() as actor:migrate_owner_namespace(actor,scope_binding=b,stable_verifiers=b['credential_verifier_sha256'])
 before=op.ledger_sha(c);members=c.execute(op.MEMBERS).fetchall()
 c.execute('BEGIN')
 try:
  if change=='council':policy['councils']=extra.COUNCILS
  elif change=='window':policy['fixed_window']['start']='2026-11-02'
  else:
   ctl=op.control(c)
   if change=='stop':ctl['manual_stop']='UNRELATED';policy['expected_stop']['manual_stop']='UNRELATED'
   elif change=='predecessor':ctl['intake_run']['id']='f'*32
   elif change=='used':ctl['intake_periods'][sc.SCOPE.period]={}
   c.execute('UPDATE ingestion_work_items SET outcome=%s::json WHERE key=%s',(json.dumps(ctl),op.CONTROL))
  with pytest.raises(__import__('psycopg').errors.RaiseException):c.execute('SELECT ingestion_register_bolton_exception(%s::jsonb)',(json.dumps(dict(operation='intake_period',period=sc.SCOPE.period,policy=policy)),))
 finally:c.execute('ROLLBACK')
 assert op.ledger_sha(c)==before and c.execute(op.MEMBERS).fetchall()==members

@pytest.mark.parametrize('mode',['before','lost'])
def test_namespace_atomicity(succeeded10,mode):
 w=succeeded10;c=w['boot'];b=w['binding'];before=op.ledger_sha(c)
 query="SELECT proname,prosrc,proacl::text,proowner,prosecdef,proconfig FROM pg_proc WHERE oid=ANY(ARRAY['public.ingestion_intake_owner_state(text,text,text,bytea)'::regprocedure,'public.ingestion_register_bolton_exception(jsonb)'::regprocedure,'public.ingestion_intake_evidence_write(text,text,text,bytea)'::regprocedure]) ORDER BY proname"
 definitions=c.execute(query).fetchall();schema=c.execute("SELECT nspacl::text FROM pg_namespace WHERE nspname='public'").fetchone()
 with w['actor']() as actor:
  with pytest.raises(RuntimeError):migrate_owner_namespace(Fault(actor,mode),scope_binding=b,stable_verifiers=b['credential_verifier_sha256'])
 if mode=='before':assert c.execute(query).fetchall()==definitions
 else:
  with w['actor']() as fresh:sc.namespace(fresh,migrated=True)
  assert all(x[2:]==y[2:] for x,y in zip(definitions,c.execute(query).fetchall()))
 assert c.execute(op.MEMBERS).fetchall()==w['members'] and op.ledger_sha(c)==before
 assert c.execute("SELECT nspacl::text FROM pg_namespace WHERE nspname='public'").fetchone()==schema
