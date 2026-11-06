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

@pytest.mark.parametrize('incomplete',[False,True])
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
 if incomplete:audit['enumeration_evidence']='TOTAL_UNKNOWN'
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
 result_code=main(argv,prepared_runtime=runtime)
 result=json.loads((runtime.root/'final-result.json').read_text())
 assert result_code==(1 if incomplete else 0),{k:result.get(k) for k in ('status','reason','cleanup','usage')}
 assert calls==[sc.SCOPE.row()]
 assert result['usage']['requests']==audit['resource']['requests_attempted']<=10
 assert result['usage']['all_connections_closed'] is True
 ctl=op.control(c);assert ctl['intake_periods'][sc.PREDECESSOR]['verified_run']==w['marker']
 assert op.stop_snapshot(ctl)==(sc.ACCEPTED if not incomplete else op.stop_snapshot(ctl))
 if not incomplete:
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
