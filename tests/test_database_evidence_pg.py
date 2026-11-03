"""Actual fixed hosted PG17 transactions; synthetic authorities/transports only."""
import copy,json,time,hashlib,subprocess,sys,os
from datetime import date,datetime,timezone
from pathlib import Path
import pytest
from tests.test_daily_intake_runtime import world,reset,policy,authorise,env_and_sources
from verification.ingestion_storage.database_evidence import definition_sql,canonical
from verification.ingestion_storage import screening_v3_worker_sql as v3
from tests.e2e_connection_support import arcus_audit,entry,SCHEME

@pytest.fixture(scope='module')
def evidence_world(world):
 assert 170000<=world['server_version']<180000
 world['boot'].execute('CREATE ROLE postgres NOLOGIN NOSUPERUSER')
 with world['connect']('provisioning_migrator') as c:c.execute(v3.CEREMONY_OPEN+definition_sql()+v3.CEREMONY_CLOSE)
 yield world
 world['boot'].execute('REVOKE EXECUTE ON FUNCTION ingestion_intake_evidence_read(text,text,text) FROM postgres')
 world['boot'].execute('REVOKE EXECUTE ON FUNCTION ingestion_intake_owner_state(text,text,text,bytea) FROM postgres')
 world['boot'].execute('DROP ROLE postgres')

def seed(w):
 reset(w);w['boot'].execute('DELETE FROM ingestion_run_evidence')
 ctl=copy.deepcopy(w['control']);run='a'*32;period='db-pilot-test'
 ctl['intake_run']=dict(id=run,period=period,state='OPEN',day='2026-11-02')
 ctl['intake_periods']={period:dict(evidence_backend='POSTGRES_PILOT_V1',max_runs=1,expires_at=time.time()+1800,execution_binding={'fixture':True})}
 ctl['grants']={'FIXTURE_ONLY':dict(intake_period=period,intake_run=run,capture_key='b'*64,execution_binding={'fixture':True},expires_at=time.time()+1800)}
 w['boot'].execute('UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat(\'0\',64)',(json.dumps(ctl),))
 row=dict(key='b'*64,subject=dict(kind='DISCOVERY_SCOPE',council='tameside',start='2026-10-27',end='2026-11-02',semantics='RECEIVED'),task='DISCOVERY',contract='fixture',revision='fixture',dependencies=[],priority=0,eligible_at=0,state='LEASED',next_action='WAIT',limits={},attempt_count=1,max_attempts=1,fence=1,phase='SOURCE_INTENT')
 w['boot'].execute('INSERT INTO ingestion_work_items SELECT * FROM jsonb_populate_record(NULL::ingestion_work_items,%s::jsonb)',(json.dumps(row),))
 return period,run,ctl

def source(size=None):
 v=dict(council='tameside',requested_interval=['2026-10-27','2026-11-02'],date_semantics='RECEIVED',padding='')
 if size:v['padding']='x'*(size-len(canonical(v)))
 return canonical(v)
def put(c,p,r,n,b):return c.execute('SELECT ingestion_intake_evidence_write(%s,%s,%s,%s)',(p,r,n,b)).fetchone()[0]
def get(c,p,r,n):return bytes(c.execute('SELECT ingestion_intake_evidence_read(%s,%s,%s)',(p,r,n)).fetchone()[0])

def test_pg17_append_identical_conflict_and_direct_mutation_denied(evidence_world):
 w=evidence_world;p,r,ctl=seed(w);raw=source()
 with w['connect']('ingestion_worker_login') as c:
  a=put(c,p,r,'capture-1/source.json',raw);assert get(c,p,r,'capture-1/source.json')==raw and a['sha256']==hashlib.sha256(raw).hexdigest()
  assert put(c,p,r,'capture-1/source.json',raw)==a
  with pytest.raises(Exception,match='EVIDENCE_CONFLICT'):put(c,p,r,'capture-1/source.json',source(1000))
  for sql in ['DELETE FROM ingestion_run_evidence','UPDATE ingestion_run_evidence SET body=body','INSERT INTO ingestion_run_evidence VALUES (NULL)']:
   with pytest.raises(Exception):c.execute(sql)
 assert w['boot'].execute('SELECT count(*) FROM ingestion_run_evidence').fetchone()==(1,)

@pytest.mark.parametrize('wrong',['period','run','source_scope','effect_role'])
def test_pg17_scope_and_principal_isolation(evidence_world,wrong):
 w=evidence_world;p,r,ctl=seed(w)
 with w['connect']('ingestion_effect_login' if wrong=='effect_role' else 'ingestion_worker_login') as c:
  raw=source()
  if wrong=='period':p='other'
  if wrong=='run':r='c'*32
  if wrong=='source_scope':v=json.loads(raw);v['council']='manchester';raw=canonical(v)
  with pytest.raises(Exception):put(c,p,r,'capture-1/source.json',raw)
 assert w['boot'].execute('SELECT count(*) FROM ingestion_run_evidence').fetchone()==(0,)

def test_pg17_source_and_aggregate_bounds(evidence_world):
 w=evidence_world;p,r,ctl=seed(w)
 with w['connect']('ingestion_worker_login') as c:
  put(c,p,r,'capture-1/source.json',source(524288))
  with pytest.raises(Exception,match='EVIDENCE_ARGUMENT_BOUND'):put(c,p,r,'capture-2/source.json',source(524289))
  put(c,p,r,'capture-2/source.json',source(524288))
 ctl['grants']['FIXTURE_ONLY']['expires_at']=0
 w['boot'].execute('UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat(\'0\',64)',(json.dumps(ctl),))
 with w['connect']('ingestion_worker_login') as c:
  raw=canonical({'padding':'x'*(1048576-len(canonical({'padding':''})))})
  put(c,p,r,'final/result-before-publication.json',raw)
  with pytest.raises(Exception,match='EVIDENCE_RUN_EXPORT_BOUND'):put(c,p,r,'final/events-before-publication.json',b'[]')
 assert w['boot'].execute('SELECT sum(octet_length(body)) FROM ingestion_run_evidence').fetchone()==(2097152,)

def test_pg17_missing_evidence_cannot_finalise(evidence_world):
 w=evidence_world;p,r,ctl=seed(w);ctl['grants']['FIXTURE_ONLY']['expires_at']=0
 w['boot'].execute('UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat(\'0\',64)',(json.dumps(ctl),))
 payload=dict(operation='intake_finish',period=p,run_id=r,execution_binding={'fixture':True},status='RETAINED_AND_SCREENED',publication=dict(backend='POSTGRES_PILOT_V1',period=p,run_id=r,name='final/result-before-publication.json',sha256='0'*64,bytes=2,readback_verified=True))
 with w['connect']('ingestion_worker_login') as c:
  with pytest.raises(Exception):c.execute('SELECT ingestion_register_bolton_exception(%s::jsonb)',(json.dumps(payload),))
 assert w['boot'].execute("SELECT outcome::jsonb->'intake_run'->>'state' FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()==('OPEN',)

def test_pg17_actual_daily_command_database_audits_screens_backlog_no_github(evidence_world,tmp_path,monkeypatch,record_property):
 from tests.test_tameside_b_connection import connected_source,COUNTED_CONTRACT,QUAL
 w=evidence_world;reset(w);w['boot'].execute('DELETE FROM ingestion_run_evidence')
 p=policy(w);d=time.time()+2090;p.update(evidence_backend='POSTGRES_PILOT_V1',fixed_window={'start':'2026-10-27','end':'2026-11-02'},max_runs=1,access_deadline=d,expires_at=d-185)
 p['councils']['tameside']=dict(contract=COUNTED_CONTRACT,qualification_sha256=QUAL);name='db-evidence-connected';authorise(w,name,p)
 env,sources=env_and_sources(w,tmp_path)
 row=dict(council='tameside',semantics='RECEIVED',start='2026-10-27',end='2026-11-02');d=tmp_path/'source-fixture';d.mkdir();audit,calls=connected_source(d,monkeypatch,row)
 (sources/'tameside.json').write_text(json.dumps(audit))
 man=arcus_audit('manchester',[entry('DATABASE/1/26',SCHEME)],date(2026,10,27),date(2026,11,2),budget='BROWSER_SOURCE_V2');(sources/'manchester.json').write_text(json.dumps(man))
 out=tmp_path/'result';run=subprocess.run([sys.executable,'-B','-m','scripts.run_daily_councils','--period',name,'--output',str(out),'--disposable-sources',str(sources),'--disposable-archive',str(tmp_path/'unused-local-archive')],env=env,capture_output=True,text=True,timeout=90)
 result=json.loads((out/'final-result.json').read_bytes());record_property('connected_result',json.dumps(result,sort_keys=True));assert run.returncode==0,json.dumps(result,sort_keys=True)
 assert result['status']=='RETAINED_AND_SCREENED' and result['finalisation']=='VERIFIED' and result['github_publication']=='NOT_REQUESTED' and result['usage']['github_actual_calls']==0
 assert result['cleanup']=='CLOSED' and result['authority_closure']=='INVALIDATED' and len(result['backlog']['records'])==10
 rows=w['boot'].execute('SELECT name,body,sha256 FROM ingestion_run_evidence ORDER BY name').fetchall();assert len(rows)==4
 for n,b,h in rows:assert hashlib.sha256(bytes(b)).hexdigest()==h
 assert not (tmp_path/'unused-local-archive').exists()
 assert w['boot'].execute("SELECT outcome::jsonb->'intake_run'->>'state' FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()==('VERIFIED',)
 record_property('server_version',w['server_version']);record_property('records',10);record_property('evidence_rows',4);record_property('source_transport','SYNTHETIC_ONLY')

def test_pg17_queued_start_without_full_reserve_refuses_before_source(evidence_world,tmp_path):
 w=evidence_world;reset(w);w['boot'].execute('DELETE FROM ingestion_run_evidence')
 p=policy(w);d=time.time()+1490;p.update(evidence_backend='POSTGRES_PILOT_V1',fixed_window={'start':'2026-10-27','end':'2026-11-02'},max_runs=1,access_deadline=d,expires_at=d-185)
 name='db-queue-reserve';authorise(w,name,p);env,sources=env_and_sources(w,tmp_path);out=tmp_path/'result'
 run=subprocess.run([sys.executable,'-B','-m','scripts.run_daily_councils','--period',name,'--output',str(out),'--disposable-sources',str(sources),'--disposable-archive',str(tmp_path/'archive')],env=env,capture_output=True,text=True,timeout=30)
 result=json.loads((out/'final-result.json').read_bytes())
 assert run.returncode!=0 and result['status']=='STOP_RECONCILE_NO_RETRY' and result['usage']['requests']==0 and result['scopes']==[]
 assert result['authority_closure']=='NOT_ISSUED' and result['usage']['all_connections_closed']
 assert w['boot'].execute('SELECT count(*) FROM ingestion_run_evidence').fetchone()==(0,)

def test_pg17_projection_refusal_preserves_source_audit_and_truthful_open(evidence_world,tmp_path,monkeypatch):
 from tests.test_tameside_b_connection import connected_source,COUNTED_CONTRACT,QUAL
 w=evidence_world;reset(w);w['boot'].execute('DELETE FROM ingestion_run_evidence')
 p=policy(w);d=time.time()+2090;p.update(evidence_backend='POSTGRES_PILOT_V1',fixed_window={'start':'2026-10-27','end':'2026-11-02'},max_runs=1,access_deadline=d,expires_at=d-185)
 p['councils']['tameside']=dict(contract=COUNTED_CONTRACT,qualification_sha256=QUAL);name='db-evidence-refusal';authorise(w,name,p)
 env,sources=env_and_sources(w,tmp_path);folder=tmp_path/'fixture';folder.mkdir()
 audit,_=connected_source(folder,monkeypatch,dict(council='tameside',semantics='RECEIVED',start='2026-10-27',end='2026-11-02'))
 (sources/'tameside.json').write_text(json.dumps(audit))
 man=arcus_audit('manchester',[entry('REFUSAL/1/26',SCHEME)],date(2026,10,27),date(2026,11,2),budget='BROWSER_SOURCE_V2');man['applied_interval']=['2026-10-26','2026-11-02']
 (sources/'manchester.json').write_text(json.dumps(man));out=tmp_path/'result'
 run=subprocess.run([sys.executable,'-B','-m','scripts.run_daily_councils','--period',name,'--output',str(out),'--disposable-sources',str(sources),'--disposable-archive',str(tmp_path/'unused')],env=env,capture_output=True,text=True,timeout=90)
 result=json.loads((out/'final-result.json').read_bytes())
 assert run.returncode!=0 and result['status']=='STOP_RECONCILE_NO_RETRY' and result['finalisation']=='NOT_ATTEMPTED_STOPPED'
 stored=w['boot'].execute("SELECT body,sha256 FROM ingestion_run_evidence WHERE name='capture-2/source.json'").fetchone()
 assert bytes(stored[0])==canonical(man) and stored[1]==hashlib.sha256(canonical(man)).hexdigest()
 assert w['boot'].execute("SELECT outcome::jsonb->'intake_run'->>'state' FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()==('OPEN',)
 assert result['cleanup']=='CLOSED' and result['authority_closure']=='INVALIDATED' and result['evidence']=='READBACK_VERIFIED'
