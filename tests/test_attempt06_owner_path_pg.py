"""PG17 owner sequence, production guards, synthetic evidence/source transports only."""
import copy,hashlib,json,time
from pathlib import Path
from types import SimpleNamespace
from contextlib import contextmanager
from datetime import date,datetime,timezone
import pytest,psycopg
from psycopg import sql
from tests.e2e_pg_world import disposable_world
from tests.e2e_connection_support import idox_audit,arcus_audit,entry,SCHEME
from verification.ingestion_storage import intake_owner as op,intake_owner_operations as extra,attempt06_recovery as a06
from verification.ingestion_storage import database_evidence as de,intake_policy,owner_pilot
from verification.ingestion_storage.daily_intake_runtime import Runtime,execution_binding
from verification.ingestion_storage.oldham_reuse import expected_historical
from verification.ingestion_storage.operational_owner import Owner

@pytest.fixture
def world(monkeypatch):
 for w in disposable_world():
  boot=w['boot']
  # Production-shaped non-superuser owner. All synthetic grants are setup only.
  boot.execute("CREATE ROLE postgres LOGIN NOSUPERUSER BYPASSRLS CREATEROLE CREATEDB INHERIT PASSWORD 'disposable_actor_password'")
  try:
   boot.execute('GRANT pg_read_all_stats TO postgres')
   boot.execute('GRANT SELECT (rolname,rolpassword) ON pg_authid TO postgres')
   boot.execute('GRANT USAGE ON SCHEMA public TO postgres')
   boot.execute('GRANT SELECT ON ingestion_work_items,ingestion_work_attempts TO postgres')
   with w['connect']('provisioning_migrator') as c:c.execute(intake_policy.installation_script())
   # Install current evidence definitions with original ownership and ACLs.
   boot.execute('GRANT CREATE ON SCHEMA public TO ingestion_storage_owner')
   boot.execute('SET ROLE ingestion_storage_owner');boot.execute(de.definition_sql());boot.execute('RESET ROLE')
   boot.execute('REVOKE CREATE ON SCHEMA public FROM ingestion_storage_owner')
   for name in ['ingestion_storage_owner','ingestion_recovery_operator','ingestion_barrier_releaser',*op.ROLES,*op.ROLES.values()]:
    boot.execute(sql.SQL('GRANT {} TO postgres WITH ADMIN TRUE,INHERIT FALSE,SET FALSE').format(sql.Identifier(name)))
   for role,cap in op.ROLES.items():
    boot.execute(sql.SQL('ALTER ROLE {} NOLOGIN NOINHERIT CONNECTION LIMIT 1').format(sql.Identifier(role)))
    for (grantor,) in boot.execute('SELECT grantor::regrole::text FROM pg_auth_members WHERE roleid=%s::regrole AND member=%s::regrole',(cap,role)).fetchall():
     boot.execute(sql.SQL('REVOKE {} FROM {} GRANTED BY {} CASCADE').format(sql.Identifier(cap),sql.Identifier(role),sql.Identifier(grantor)))
   # Also keep application and recovery login dormant.
   boot.execute('ALTER ROLE ingestion_application_login NOLOGIN;ALTER ROLE ingestion_recovery_login NOLOGIN')
   ctl=copy.deepcopy(w['control']);ctl.update(a06.STOP6)
   class Q:
    def q(self,c,s,p=None):return c.execute(s,p).fetchall()
   grant,allowance=expected_historical(Q(),boot);grant['expires_at']=0;allowance['revoked']=True
   ctl['grants'][op.OLDHAM]=grant;ctl['oldham_allowances']={op.OLDHAM:allowance}
   boot.execute('INSERT INTO ingestion_work_items SELECT * FROM jsonb_populate_record(NULL::ingestion_work_items,%s::jsonb)',(json.dumps(allowance['package']['registration']['rows'][0]),))
   for key in op.RECOVERED:
    patch=dict(key=key,state='SAFETY_BLOCKED',phase='RECOVERED',fence=2,owner=None,lease_until=None)
    boot.execute("INSERT INTO ingestion_work_items SELECT (jsonb_populate_record(NULL::ingestion_work_items,to_jsonb(w)||%s::jsonb)).* FROM ingestion_work_items w WHERE key=%s",(json.dumps(patch),op.CONTROL))
    boot.execute("INSERT INTO ingestion_work_attempts(work_key,fence,owner,started_at,finished_at,authority,phase) VALUES(%s,1,'synthetic',0,1,'synthetic','RECOVERED')",(key,))
   marker=dict(id=a06.RUN,period=a06.PERIOD,state='OPEN',day='2026-11-02',publication_path=de.path(a06.PERIOD,a06.RUN,'final/result-before-publication.json'))
   ctl['intake_run']=marker
   ctl['intake_periods']={a06.PERIOD:dict(execution_binding=a06.BINDING,days={'2026-11-02':{'tameside':a06.KEY}})}
   ctl['grants'][a06.AUTHORITY]=dict(intake_run=a06.RUN,intake_period=a06.PERIOD,capture_key=a06.KEY,execution_binding=a06.BINDING,expires_at=0)
   boot.execute('UPDATE ingestion_work_items SET outcome=%s::json WHERE key=%s',(json.dumps(ctl),op.CONTROL))
   patch=dict(key=a06.KEY,authority=a06.AUTHORITY,revision=a06.PERIOD+'-2026-11-02-tameside',state='CLAIMED',phase='SOURCE_INTENT',fence=1,attempt_count=1,checkpoint=None,lease_until=time.time()-20,owner='synthetic')
   boot.execute("INSERT INTO ingestion_work_items SELECT (jsonb_populate_record(NULL::ingestion_work_items,to_jsonb(w)||%s::jsonb)).* FROM ingestion_work_items w WHERE key=%s",(json.dumps(patch),op.CONTROL))
   boot.execute("INSERT INTO ingestion_work_attempts(work_key,fence,owner,started_at,authority,phase) VALUES(%s,1,'synthetic',0,%s,'SOURCE_INTENT')",(a06.KEY,a06.AUTHORITY))
   # Only expected hashes are substituted for private production bodies, never a validator.
   evidence={}
   for name in a06.EVIDENCE:
    body=de.canonical([] if 'events' in name else {'status':'STOP_RECONCILE_NO_RETRY','reason':'SOURCE_STOP_OR_ACCESS_CHANGED','synthetic':True})
    h=hashlib.sha256(body).hexdigest();evidence[name]=h
    boot.execute('INSERT INTO ingestion_run_evidence(period,run_id,name,body,sha256) VALUES(%s,%s,%s,%s,%s)',(a06.PERIOD,a06.RUN,name,body,h))
   monkeypatch.setattr(a06,'EVIDENCE',evidence)
   release=dict(execution_binding=execution_binding(),deployment='dep-'+'a'*20)
   monkeypatch.setenv('PROPERTYAIGENT_INTAKE_SOURCE_RELEASE',json.dumps(release))
   profile=owner_pilot.source_profile(dict(execution_binding=release['execution_binding'],browser_canary='LAUNCHED_AND_CLOSED',browser_path='/fixture/browser',browser_sha256='a'*64),release['execution_binding']['revision'])
   b,p=owner_pilot.fixed_binding(release,profile,'192.0.2.1','a'*64)
   b.update(period=a06.SUCCESSOR,accepted_stop=a06.ACCEPTED,attempt06_receipt_sha256=a06.sha(a06.receipt(marker)),credential_policy='STABLE_RESTRICTED_V1')
   b['credential_verifier_sha256']=dict(boot.execute("SELECT rolname,encode(sha256(convert_to(rolpassword,'UTF8')),'hex') FROM pg_authid WHERE rolname=ANY(%s)",(list(op.ROLES),)).fetchall())
   p['expected_stop']=a06.ACCEPTED;b['period_policy_sha256']=hashlib.sha256(de.canonical(p)).hexdigest()
   w.update(binding=b,policy=p,members=boot.execute(op.MEMBERS).fetchall())
   w['actor']=lambda:psycopg.connect(host='127.0.0.1',port=5432,dbname='ingestion_provisioning_test',user='postgres',password='disposable_actor_password',autocommit=True,prepare_threshold=None)
   yield w
  finally:
   boot.execute('DROP OWNED BY postgres CASCADE;DROP ROLE postgres')

class Fault:
 def __init__(self,c,mode):self.c=c;self.mode=mode;self.commits=0
 def __getattr__(self,n):return getattr(self.c,n)
 def execute(self,s,p=None):
  if s=='COMMIT':
   self.commits+=1
   if self.mode=='before':raise RuntimeError('SYNTHETIC_PRECOMMIT')
  r=self.c.execute(s,p)
  if s=='COMMIT' and self.mode=='lost':raise RuntimeError('SYNTHETIC_LOST_ACK')
  return r

def act(w,method,mode='normal'):
 with w['actor']() as c:
  wrapped=Fault(c,mode)
  if mode=='normal':method(wrapped,w['binding'])
  else:
   with pytest.raises(RuntimeError):method(wrapped,w['binding'])
  assert wrapped.commits==1

def read(w,phase):
 with w['actor']() as c:return a06.readback(c,w['binding'],phase)

@pytest.mark.parametrize('phase',['recovery','disposition'])
@pytest.mark.parametrize('mode',['before','lost'])
def test_atomic_failure_and_lost_ack(world,phase,mode):
 w=world;b=w['boot']
 if phase=='disposition':act(w,a06.recover);read(w,'recovery')
 before=op.ledger_sha(b);members=b.execute(op.MEMBERS).fetchall()
 act(w,a06.recover if phase=='recovery' else a06.dispose,mode)
 assert b.execute(op.MEMBERS).fetchall()==members
 if mode=='before':assert op.ledger_sha(b)==before
 else:assert read(w,phase)['status']=='COMMITTED_STATE_VERIFIED_READ_ONLY'

@pytest.mark.parametrize('drift',['id','stop','generation','fence','lease','attempt','evidence','successor','grant','manchester'])
def test_changed_state_refuses_without_effect(world,drift):
 w=world;c=w['boot'];ctl=op.control(c)
 if drift=='id':ctl['intake_run']['id']='f'*32
 elif drift=='stop':ctl['global_stop']={'reason':'UNRELATED'}
 elif drift=='generation':ctl['hard_stop_generation']=7
 elif drift=='successor':ctl['intake_periods'][a06.SUCCESSOR]={}
 elif drift=='grant':ctl['grants'][a06.AUTHORITY]['execution_binding']={}
 elif drift=='fence':c.execute('UPDATE ingestion_work_items SET fence=2 WHERE key=%s',(a06.KEY,))
 elif drift=='lease':c.execute('UPDATE ingestion_work_items SET lease_until=%s WHERE key=%s',(time.time()+100,a06.KEY))
 elif drift=='attempt':c.execute('UPDATE ingestion_work_attempts SET finished_at=1 WHERE work_key=%s',(a06.KEY,))
 elif drift=='evidence':c.execute('DELETE FROM ingestion_run_evidence WHERE name=%s',(next(iter(a06.EVIDENCE)),))
 else:c.execute('UPDATE ingestion_work_items SET revision=%s WHERE key=%s',(a06.PERIOD+'-2026-11-02-manchester',op.RECOVERED[0]))
 c.execute('UPDATE ingestion_work_items SET outcome=%s::json WHERE key=%s',(json.dumps(ctl),op.CONTROL))
 before=op.ledger_sha(c);members=c.execute(op.MEMBERS).fetchall()
 with w['actor']() as actor:
  with pytest.raises(Exception):a06.recover(actor,w['binding'])
 assert op.ledger_sha(c)==before and c.execute(op.MEMBERS).fetchall()==members

@pytest.mark.parametrize('drift',['global','manual','generation','receipt'])
def test_disposition_refuses_unrelated_stops_and_receipt(world,drift):
 w=world;act(w,a06.recover);c=w['boot'];ctl=op.control(c)
 if drift=='receipt':ctl['intake_periods'][a06.PERIOD]['failed_runs'][a06.RUN]['actual_requests']=0
 else:ctl[{'global':'global_stop','manual':'manual_stop','generation':'hard_stop_generation'}[drift]]='UNRELATED'
 c.execute('UPDATE ingestion_work_items SET outcome=%s::json WHERE key=%s',(json.dumps(ctl),op.CONTROL));before=op.ledger_sha(c)
 with w['actor']() as actor:
  with pytest.raises(op.Denied):a06.dispose(actor,w['binding'])
 assert op.ledger_sha(c)==before and c.execute(op.MEMBERS).fetchall()==w['members']

def test_actual_owner_sequence_and_bounded_successor(world,tmp_path,monkeypatch,record_property):
 w=world;c=w['boot'];b=w['binding'];p=w['policy']
 act(w,a06.recover);assert read(w,'recovery')['stop']==a06.STOP7
 saved=copy.deepcopy(op.control(c)['intake_periods'][a06.PERIOD])
 act(w,a06.dispose);assert read(w,'disposition')['stop']==a06.ACCEPTED
 state=dict(version='FINITE_INTAKE_PERIOD_V1',state='ARMED_NO_RETRY',binding=b,policy=p)
 with w['actor']() as actor:extra.issue_period(actor,b,p,state,lambda _:None)
 assert c.execute(op.MEMBERS).fetchall()==w['members']
 passwords={r:__import__('sqlalchemy').engine.make_url(w['urls'][r]).password for r in op.ROLES}
 states=[]
 with w['actor']() as actor:
  prepared=op.prepare_activation(actor,b,stable_credentials=passwords)
  op.activate(actor,b,lambda v:states.append(copy.deepcopy(v)),prepared=prepared)
 # Only transport/resource adapters are synthetic. Owner/SQL guards are unchanged.
 for role,var in [('ingestion_worker_login','INGESTION_WORKER_DATABASE_URL'),('ingestion_effect_login','INGESTION_EFFECT_DATABASE_URL')]:monkeypatch.setenv(var,w['urls'][role])
 monkeypatch.delenv('DATABASE_URL',raising=False)
 args=SimpleNamespace(period=a06.SUCCESSOR,output=str(tmp_path/'run'),hostaddr=b['hostaddr'],disposable_sources=None,disposable_archive=None)
 runtime=Runtime(args);runtime.route_name=b['route']  # same SQL connection, fixture loopback transport
 monkeypatch.setattr('verification.ingestion_storage.daily_intake_runtime.require_source_context',lambda *a,**kw:None)
 def source(row):
  runtime.run.begin_source();start,end=date.fromisoformat(row['start']),date.fromisoformat(row['end'])
  records=[entry('SYNTHETIC/26',SCHEME)]
  audit=idox_audit('tameside',records,start,end) if row['council']=='tameside' else arcus_audit('manchester',records,start,end,budget='BROWSER_SOURCE_V2')
  runtime.run.source(dict(requests=1,source_bytes=len(de.canonical(audit)),source_seconds=0.1,supervised_seconds=0.1))
  return audit,dict(cleanup='CLOSED',exit_code=0,limit_hit=None,live_owned_survivors=0,elapsed_seconds=.1,observed_at=datetime.now(timezone.utc).isoformat())
 runtime.collect=source
 result=runtime.execute()
 assert result['status']=='RETAINED_AND_SCREENED',json.dumps(result,sort_keys=True)
 assert result['authority_closure']=='INVALIDATED' and result['cleanup']=='CLOSED'
 ctl=op.control(c);assert ctl['intake_run']['state']=='VERIFIED' and ctl['intake_run']['id']!=a06.RUN
 assert ctl['intake_periods'][a06.PERIOD]['failed_runs']==saved['failed_runs'] and op.stop_snapshot(ctl)==a06.ACCEPTED
 assert len(ctl['intake_periods'][a06.SUCCESSOR]['days']['2026-11-02'])==2
 assert c.execute("SELECT count(*) FROM ingestion_run_evidence WHERE period=%s AND sha256=encode(sha256(body),'hex')",(a06.SUCCESSOR,)).fetchone()==(4,)
 with w['actor']() as actor:closed=op.close(actor,states[-1],lambda _:None)
 assert closed['runtime_access']=='DISABLED' and closed['sessions']=='ABSENT'
 assert c.execute(op.MEMBERS).fetchall()==w['members']
 record_property('postgres_version',w['server_version']);record_property('actor_superuser',False)
 record_property('sequence','recover/readback/dispose/readback/issue/activate/runtime/close')


def test_successor_namespace_preserves_encrypted_history(world,monkeypatch):
 from verification.ingestion_storage.owner_pilot_continuation import migrate_owner_namespace
 w=world;boot=w['boot'];act(w,a06.recover);read(w,'recovery');act(w,a06.dispose);read(w,'disposition')
 # Synthetic installed Attempt06 namespace, using its exact original SQL body.
 boot.execute('GRANT CREATE ON SCHEMA public TO ingestion_storage_owner');boot.execute('SET ROLE ingestion_storage_owner')
 boot.execute(de.ATTEMPT06_OWNER_SQL.split('REVOKE ALL ON FUNCTION',1)[0].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1))
 boot.execute('RESET ROLE');boot.execute('REVOKE CREATE ON SCHEMA public FROM ingestion_storage_owner')
 boot.execute('GRANT CREATE ON SCHEMA public TO postgres WITH GRANT OPTION')
 old=a06.PERIOD+'_owner';rid=hashlib.sha256(old.encode()).hexdigest()[:32]
 with w['actor']() as c:prior=c.execute('SELECT * FROM ingestion_intake_owner_state(%s,%s,%s,%s)',(old,rid,'',b'synthetic-encrypted-history')).fetchone()
 release=json.loads(__import__('os').environ['PROPERTYAIGENT_INTAKE_SOURCE_RELEASE']);release['attempt06_receipt_sha256']=w['binding']['attempt06_receipt_sha256'];monkeypatch.setenv('PROPERTYAIGENT_INTAKE_SOURCE_RELEASE',json.dumps(release))
 members=boot.execute(op.MEMBERS).fetchall();ledger=op.ledger_sha(boot)
 with w['actor']() as c:result=migrate_owner_namespace(c,attempt07=True,stable_verifiers=w['binding']['credential_verifier_sha256'])
 assert result['permissions_restored'] and op.ledger_sha(boot)==ledger and boot.execute(op.MEMBERS).fetchall()==members
 with w['actor']() as c:
  assert c.execute('SELECT * FROM ingestion_intake_owner_state(%s,%s,%s,NULL::bytea)',(old,rid,'')).fetchone()==prior
  new=a06.SUCCESSOR+'_owner';newid=hashlib.sha256(new.encode()).hexdigest()[:32]
  assert c.execute('SELECT * FROM ingestion_intake_owner_state(%s,%s,%s,%s)',(new,newid,'',b'synthetic-successor')).fetchone()[0]==0
