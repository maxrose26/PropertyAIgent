"""Actual owner issuance and restricted caller; fixtures never represent live authority."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json,time,os
from pathlib import Path
import pytest
from psycopg import sql
from app.ingestion.ledger import Denied,digest
from tests.e2e_pg_world import disposable_world,RESTRICTED
from tests.e2e_chain_caller import Chain,OWNER_BINDINGS,application,snapshot
from tests.test_closed_idox_pg import admit_fixture
from tests.test_e2e_connection_pg import assert_closed,assert_confined
from verification.ingestion_storage import oldham_policy
from verification.ingestion_storage.oldham_authority import OldhamOwner,STOP_STATE,derive,registration_value
from verification.ingestion_storage.oldham_lifecycle import Lifecycle
from verification.ingestion_storage.oldham_allocation import Allocation,FiniteCaller

COSTS=[]

@pytest.fixture(scope='module')
def world():
 gen=disposable_world();w=next(gen)
 with w['connect']('provisioning_migrator') as c:
  from verification.ingestion_storage.operational_owner import PKG,GENERATION3_SCREENING_V3_POLICY
  c.execute((PKG/'successor-policy.sql').read_text())
  c.execute(GENERATION3_SCREENING_V3_POLICY.read_text())
  c.execute(oldham_policy.installation_script())
 # Explicit disposable installer prerequisites; not runtime privileges or production proof.
 w['boot'].execute('GRANT SELECT (rolname,rolpassword) ON pg_authid TO provisioning_migrator')
 w['boot'].execute('GRANT pg_read_all_stats TO provisioning_migrator WITH INHERIT TRUE, SET FALSE')
 yield w
 with pytest.raises(StopIteration):next(gen)
 if os.environ.get('OLDHAM_AUTHORITY_COST_PATH'):Path(os.environ['OLDHAM_AUTHORITY_COST_PATH']).write_text(json.dumps(dict(cases=COSTS,sources='SYNTHETIC',database='RESTRICTED_PG17',production_authority=False),default=str,sort_keys=True))

class GitHub:
 def __init__(self):self.present={'DATABASE_URL'};self.calls=[]
 def names(self):self.calls.append('NAMES');return sorted(self.present)
 def put_secret(self,name,value):assert isinstance(value,str) and value;self.calls.append(('PUT',name));self.present.add(name)
 def call(self,method,path):assert method=='DELETE';name=path.rsplit('/',1)[-1];self.calls.append(('DELETE',name));self.present.discard(name)

def owner(w,chain):
 o=OldhamOwner(lambda:w['connect']('provisioning_migrator'),lambda *_:None,lambda:None,identity='provisioning_migrator',expiry=datetime.now(timezone.utc)+timedelta(minutes=30),bindings=dict(OWNER_BINDINGS))
 o.require_control_sha256=digest(chain._control());return o

def evidence(chain,reg):return dict(source_sha256=digest(chain.source),outer_sha256=digest(chain.outer),qualification_sha256=chain.contract.qualification_sha256,registration_sha256=digest(registration_value(reg)))

def issue(o,ch,*,root=None,nominees=(),phase=None,screening_rows=None):
 args=dict(revision=ch.revision,item_limits=ch.item_limits,phase=phase,screening_rows=screening_rows)
 extra={} if root is None else dict(root=root,receipt=ch.capture_receipt,nominees=tuple(nominees),rule=ch.rule,detail_targets=None,allow_test_evidence=True)
 reg=derive(o,ch.binding,ch.contract,**args,**extra)
 o.require_control_sha256=digest(ch._control())
 actual=o.issue(reg,ch.binding,ch.contract,source=ch.source,outer=ch.outer,evidence=evidence(ch,reg),**args,**extra)
 if isinstance(actual,dict):return actual
 ch.bindings.update(reg.bindings)
 return reg

def setup(w,tmp,entries=None,configure=None,staged=False):
 ch=Chain(w,tmp,'idox','a'*40,entries,council='oldham').owner_reset()
 ctl=ch._control();ctl.update(deepcopy(STOP_STATE));ch._write_control(ctl)
 for r in RESTRICTED:w['boot'].execute(sql.SQL('ALTER ROLE {} NOLOGIN PASSWORD NULL').format(sql.Identifier(r)))
 ch.supervised_source();o=owner(w,ch);reg=issue(o,ch,phase='CAPTURE' if staged else None)
 ch.root=reg.rows[0];ch.capture_registration=reg
 if staged:ch.auth_capture=reg.authority;ch.caller.capture_authority=reg.authority
 # Same production caller with its one cumulative accounted budget, not a mocked effect.
 old=ch.caller
 ch.caller=o.caller(old.sb,old.contract,old.rule,old.urls,revision=old.revision,bindings=old.bindings,capture_authority=old.capture_authority,chain_authority=old.chain_authority,allow_test_evidence=True)
 gh=GitHub();life=Lifecycle(o,gh)
 def url_factory(role,password):
  from sqlalchemy.engine import make_url
  return make_url(w['urls'][role]).set(password=password).render_as_string(hide_password=False)
 if configure:configure(ch,o,life,gh,url_factory)
 ch.caller.urls=life.activate(url_factory=url_factory)
 return ch,o,life,gh

def stage(ch,o):
 ch.capture();ch.read_capture();ns=ch.nominees()
 root=ch.w['boot'].execute('SELECT row_to_json(w) FROM ingestion_work_items w WHERE key=%s',(ch.root['key'],)).fetchone()[0]
 reg=issue(o,ch,root=root,nominees=ns.nominees);ch.chain_registration=reg;ch.caller.use(reg);ch.screen();return ns

def test_actual_issue_chain_three_login_teardown(world,tmp_path):
 ch,o,life,gh=setup(world,tmp_path);ns=stage(ch,o);before=snapshot(world['boot'])
 assert len(ns.nominees)==2
 for n in ns.nominees:
  result,calls,observed=admit_fixture(ch,n,tmp_path)
  assert result['outcome']=='SUPPORTED_FACTS_VERIFIED' and result['factual']['verification_scope']=='COUPLED' and calls==[1]
 assert_confined(world,'idox',before,admitted=True);assert_closed(world,ch)
 life.teardown();assert life.state=='CLOSED' and o.invalidation=='VERIFIED' and gh.present=={'DATABASE_URL'}
 assert o.opened==o.closed and not o.effect_uncertain
 COSTS.append(dict(admin=o.accounting(),admin_supervised_seconds=o.admin_elapsed,runtime=ch.caller.allocation.totals(),identities=2,factual_deliveries=2,credential_teardown=life.state))

@pytest.mark.parametrize('change',[('global_stop',None),('manual_stop','OTHER'),('hard_stop_generation',4),('last_hard_stop','OTHER')])
def test_sql_stop_changes_invalidate_even_when_global_stop_cleared(world,tmp_path,change):
 ch,o,life,gh=setup(world,tmp_path);ctl=ch._control();ctl[change[0]]=change[1];ch._write_control(ctl)
 with pytest.raises(Exception):ch.capture()
 assert world['boot'].execute('SELECT count(*) FROM applications').fetchone()[0]==0
 life.teardown()

@pytest.mark.parametrize('fault',('revoked','expired','grant_binding','package','missing','source_cap','binding_reseal'))
def test_sql_allowance_tampering_refuses(world,tmp_path,fault):
 ch,o,life,gh=setup(world,tmp_path);ctl=ch._control();a=ch.auth_capture;e=ctl['oldham_allowances'][a]
 if fault=='revoked':e['revoked']=True
 elif fault=='expired':e['expires_at']=0
 elif fault=='grant_binding':e['grant_binding']['capture_key']='f'*64
 elif fault=='package':e['package']['scope']['start']='2026-11-10'
 elif fault=='missing':del ctl['oldham_allowances'][a]
 elif fault=='binding_reseal':
  ctl['grants'][a]['completion_outcomes']['DISCOVERY'].append('UNREVIEWED')
  e['grant_binding']={k:v for k,v in ctl['grants'][a].items() if k not in ('source_calls','writes')}
 else:ctl['grants'][a]['source_calls']=1
 ch._write_control(ctl)
 with pytest.raises(Exception):ch.capture()
 # Missing allowance cannot be silently reconstructed; it is an explicit reconciliation stop.
 if fault=='missing':
  with pytest.raises(Denied):life.teardown()
 else:life.teardown()

@pytest.mark.parametrize('fault',('writes','keys','target','evidence'))
def test_actual_issuance_refuses_forgery_before_mutation(world,tmp_path,fault):
 ch,o,life,gh=setup(world,tmp_path);ch.capture();ch.read_capture();ns=ch.nominees();root=world['boot'].execute('SELECT row_to_json(w) FROM ingestion_work_items w WHERE key=%s',(ch.root['key'],)).fetchone()[0]
 args=dict(revision=ch.revision,item_limits=ch.item_limits,root=root,receipt=ch.capture_receipt,nominees=ns.nominees,rule=ch.rule,detail_targets=None,allow_test_evidence=True)
 reg=derive(o,ch.binding,ch.contract,**args);ev=evidence(ch,reg);before=deepcopy(ch._control())
 if fault=='writes':reg.grant['writes']+=1
 elif fault=='keys':reg.grant['keys'].append('f'*64)
 elif fault=='target':next(iter(reg.factual_contracts.values())).row['source_url']='https://example.org/'
 else:ev['outer_sha256']='f'*64
 with pytest.raises(Denied):o.issue(reg,ch.binding,ch.contract,source=ch.source,outer=ch.outer,evidence=ev,**args)
 assert ch._control()==before
 life.teardown()

@pytest.mark.parametrize('mode',('zero','existing'))
def test_new_authority_zero_and_existing_preserve(world,tmp_path,mode):
 from tests.e2e_connection_support import entry,EXTENSION
 entries=[entry('SYNTHETIC/ZERO',EXTENSION)] if mode=='zero' else None
 ch,o,life,gh=setup(world,tmp_path,entries);ns=stage(ch,o)
 if mode=='zero':assert ns.nominees==()
 else:
  first=ns.nominees[0]
  from sqlalchemy.orm import Session
  from app.db.models import Application
  with Session(world['app']) as session:
   session.add(Application(council_code='oldham',reference=first.reference,unit_confirmation_status='discovery_pending'));session.commit()
  before=application(world['boot'],'oldham',first.reference)
  result,_,_=admit_fixture(ch,first,tmp_path)
  assert result['outcome']=='DISCOVERY_SCREENING_ONLY_ALREADY_KNOWN' and application(world['boot'],'oldham',first.reference)==before
 life.teardown()

@pytest.mark.parametrize('fault',('persistence','write_intent','deferred'))
def test_independent_sql_barriers_still_stop(world,tmp_path,fault):
 ch,o,life,gh=setup(world,tmp_path)
 if fault=='deferred':
  ctl=ch._control();ctl['council_deferred_until']={'oldham':time.time()+600};ch._write_control(ctl)
 elif fault=='persistence':world['boot'].execute("UPDATE ingestion_work_items SET state='PERSISTENCE_UNCERTAIN' WHERE key=%s",(ch.root['key'],))
 else:world['boot'].execute("UPDATE ingestion_work_items SET phase='WRITE_INTENT' WHERE key=%s",(ch.root['key'],))
 with pytest.raises(Exception):ch.capture()
 assert world['boot'].execute('SELECT count(*) FROM applications').fetchone()[0]==0
 life.teardown()


def test_counter_exhaustion_does_not_replay_detail(world,tmp_path):
 ch,o,life,gh=setup(world,tmp_path);ns=stage(ch,o)
 ctl=ch._control();ctl['grants'][ch.auth_chain]['source_calls']=0;ch._write_control(ctl)
 with pytest.raises(Exception):admit_fixture(ch,ns.nominees[0],tmp_path)
 assert world['boot'].execute('SELECT count(*) FROM applications').fetchone()[0]==0
 life.teardown()


def test_lost_issuance_commit_ack_latches_without_replay(world,tmp_path):
 from verification.ingestion_storage.operational_publication import Uncertain
 ch,o,life,gh=setup(world,tmp_path);ch.capture();ch.read_capture();ns=ch.nominees()
 original=o.connector;failed=[]
 class Proxy:
  def __init__(self,c):self.c=c
  def __getattr__(self,n):return getattr(self.c,n)
  def execute(self,q,params=None):
   result=self.c.execute(q,params)
   if q=='COMMIT' and not failed:failed.append(True);raise ConnectionError('SYNTHETIC_ACK_LOSS')
   return result
 o.connector=lambda:Proxy(original())
 with pytest.raises(Uncertain):
  root=world['boot'].execute('SELECT row_to_json(w) FROM ingestion_work_items w WHERE key=%s',(ch.root['key'],)).fetchone()[0]
  issue(o,ch,root=root,nominees=ns.nominees)
 assert o.effect_uncertain and ch.auth_chain in ch._control()['grants']
 with pytest.raises(Denied):issue(o,ch,root=root,nominees=ns.nominees)
 with pytest.raises(Denied):life.teardown()
 assert world['boot'].execute('SELECT count(*) FROM applications').fetchone()[0]==0

@pytest.mark.parametrize('operation',('put','delete'))
def test_secret_uncertainty_stops_subsequent_mutations(world,tmp_path,operation):
 from verification.ingestion_storage.operational_publication import Uncertain
 if operation=='delete':
  ch,o,life,gh=setup(world,tmp_path);original=gh.call
  def lost(method,path):original(method,path);raise Uncertain('SYNTHETIC_SECRET_ACK_LOSS')
  gh.call=lost
  with pytest.raises(Uncertain):life.teardown()
  assert len([c for c in gh.calls if isinstance(c,tuple) and c[0]=='DELETE'])==1
 else:
  held=[]
  def configure(ch,o,life,gh,factory):
   held.extend((ch,o,life,gh));original=gh.put_secret
   def lost(name,value):original(name,value);raise Uncertain('SYNTHETIC_SECRET_ACK_LOSS')
   gh.put_secret=lost
  with pytest.raises(Uncertain):setup(world,tmp_path,configure=configure)
  ch,o,life,gh=held
  assert len([c for c in gh.calls if isinstance(c,tuple) and c[0]=='PUT'])==1
 before=o.commands
 with pytest.raises(Denied):life.teardown()
 assert o.commands==before and life.state=='UNCERTAIN'


def test_surviving_application_session_never_reports_closed(world,tmp_path):
 from sqlalchemy.engine import make_url
 import psycopg
 from verification.ingestion_storage.operational_publication import Uncertain
 ch,o,life,gh=setup(world,tmp_path);u=make_url(life.urls['ingestion_application_login'])
 held=psycopg.connect(host=u.host,port=u.port,dbname=u.database,user=u.username,password=u.password,autocommit=True)
 try:
  with pytest.raises(Uncertain,match='SESSIONS_REMAIN'):life.teardown()
  assert life.state=='UNCERTAIN' and gh.present=={'DATABASE_URL'}
  rows=world['boot'].execute('SELECT r.rolcanlogin,a.rolpassword IS NULL FROM pg_roles r JOIN pg_authid a ON a.rolname=r.rolname WHERE r.rolname=ANY(%s)',(RESTRICTED,)).fetchall()
  assert len(rows)==3 and all(r==(False,True) for r in rows)
 finally:held.close()


def test_postcommit_readback_failure_latches_owner(world,tmp_path):
 ch,o,life,gh=setup(world,tmp_path);ch.capture();ch.read_capture();ns=ch.nominees();q=o.q
 def fail(c,statement,params=None,**kw):
  if o.awaiting_verification and isinstance(statement,str) and statement.startswith('SELECT pg_has_role'):raise ConnectionError('SYNTHETIC_READBACK_FAILURE')
  return q(c,statement,params,**kw)
 o.q=fail
 root=world['boot'].execute('SELECT row_to_json(w) FROM ingestion_work_items w WHERE key=%s',(ch.root['key'],)).fetchone()[0]
 with pytest.raises(ConnectionError):issue(o,ch,root=root,nominees=ns.nominees)
 assert o.effect_uncertain and ch.auth_chain in ch._control()['grants']
 with pytest.raises(Denied):o.revoke()


def test_third_login_activation_commit_uncertainty_stops(world,tmp_path):
 from verification.ingestion_storage.operational_publication import Uncertain
 held=[]
 def configure(ch,o,life,gh,factory):
  held.extend((ch,o,life,gh));original=o.connector;armed=[];lost=[]
  class Proxy:
   def __init__(self,c):self.c=c
   def __getattr__(self,n):return getattr(self.c,n)
   def execute(self,q,params=None):
    result=self.c.execute(q,params)
    if isinstance(q,sql.Composed) and q.as_string(self.c)=='ALTER ROLE "ingestion_application_login" LOGIN':armed.append(True)
    if q=='COMMIT' and armed and not lost:lost.append(True);raise ConnectionError('SYNTHETIC_THIRD_LOGIN_ACK_LOSS')
    return result
  o.connector=lambda:Proxy(original())
 with pytest.raises(Uncertain):setup(world,tmp_path,configure=configure)
 ch,o,life,gh=held
 assert o.effect_uncertain and life.state=='UNCERTAIN'
 before=o.commands
 with pytest.raises(Denied):life.teardown()
 assert o.commands==before


def test_six_record_capacity_through_shared_owner_caller(world,tmp_path):
 from tests.e2e_connection_support import entry,SCHEME
 entries=[entry('SYNTHETIC/CAPACITY/'+str(i),SCHEME) for i in range(6)]
 ch,o,life,gh=setup(world,tmp_path,entries);ns=stage(ch,o);before=snapshot(world['boot'])
 assert len(ns.nominees)==6 and ch.caller.allocation.package_started==o.package_started
 for n in ns.nominees:
  result,calls,_=admit_fixture(ch,n,tmp_path)
  assert result['outcome']=='SUPPORTED_FACTS_VERIFIED' and calls==[1]
 assert_confined(world,'idox',before,admitted=True);assert_closed(world,ch)
 life.teardown()
 COSTS.append(dict(case='six_eligible',admin=o.accounting(),admin_supervised_seconds=o.admin_elapsed,runtime=ch.caller.allocation.totals(),identities=6,factual_deliveries=6,credential_teardown=life.state))

# Staged tests use the SAME real owner issuance, lifecycle and restricted caller.
def staged_screen(ch,o):
 ch.capture();ch.read_capture()
 root=ch.w['boot'].execute('SELECT row_to_json(w) FROM ingestion_work_items w WHERE key=%s',(ch.root['key'],)).fetchone()[0]
 reg=issue(o,ch,root=root,phase='SCREENING');ch.chain_registration=reg;ch.caller.use(reg)
 assert reg.grant['source_calls']==reg.grant['writes']==0 and not reg.facts
 ch.screen();rows=ch.caller.read_screening()
 ch.staged_rows=rows;ch.staged_registrations=[registration_value(ch.capture_registration),registration_value(reg)]
 return root,rows,ch.nominees()


def staged_admission(ch,o,root,rows,ns):
 reg=issue(o,ch,root=root,nominees=ns.nominees,phase='ADMISSION',screening_rows=rows)
 if not isinstance(reg,dict):ch.chain_registration=reg;ch.caller.use(reg)
 ch.staged_registrations.append(reg if isinstance(reg,dict) else registration_value(reg))
 return reg


def staged_cost(ch,o,life,gh,*,records,nominees,result):
 assert_closed(ch.w,ch);life.teardown()
 assert life.state=='CLOSED' and gh.present=={'DATABASE_URL'} and o.invalidation=='VERIFIED'
 assert o.opened==o.closed and not o.effect_uncertain
 value=dict(case='STAGED',records=records,nominees=nominees,result=result,admin=o.accounting(),admin_supervised_seconds=o.admin_elapsed,
            runtime=ch.caller.allocation.totals(),credential_teardown=life.state,source_inputs='SYNTHETIC_REAL_CHILD',github='IN_MEMORY_ACK_STAND_IN')
 packet=dict(source=ch.source,outer=ch.outer,capture=ch.capture_receipt,screening=getattr(ch,'staged_rows',[]),registrations=getattr(ch,'staged_registrations',[]),costs=value)
 raw=json.dumps(packet,default=str,sort_keys=True,separators=(',',':')).encode()
 import hashlib
 value['retained_fixture_packet_bytes']=len(raw);value['retained_fixture_packet_sha256']=hashlib.sha256(raw).hexdigest()
 value['exported_fixture_bytes']=len(json.dumps(value,default=str,sort_keys=True).encode());assert len(raw)<2*1024**2-128*1024;COSTS.append(value)


@pytest.mark.parametrize('count',[11,19])
def test_staged_complete_zero_nominees(world,tmp_path,count):
 from tests.e2e_connection_support import entry,EXTENSION
 ch,o,life,gh=setup(world,tmp_path,[entry(f'SYNTHETIC/Z{i}',EXTENSION) for i in range(count)],staged=True)
 root,rows,ns=staged_screen(ch,o)
 assert not ns.nominees and len(ch.capture_receipt['records'])==count
 assert world['boot'].execute('SELECT count(*) FROM applications').fetchone()[0]==0
 assert not any(r['task']=='FACTUAL_REFRESH' for r in ch.chain_registration.rows)
 assert ch.listing_requests==[]
 staged_cost(ch,o,life,gh,records=count,nominees=0,result='SCREENING_COMPLETE_NO_ADMISSION_REQUIRED')


def test_staged_six_eligible_held_when_full_remaining_time_cannot_fit(world,tmp_path):
 from tests.e2e_connection_support import entry,SCHEME
 ch,o,life,gh=setup(world,tmp_path,[entry(f'SYNTHETIC/S{i}',SCHEME) for i in range(6)],staged=True)
 root,rows,ns=staged_screen(ch,o);clock=ch.caller.allocation.started
 assert len(ns.nominees)==6 and world['boot'].execute('SELECT count(*) FROM applications').fetchone()[0]==0
 with pytest.raises(Denied,match='NOT_REGISTERED'):ch.caller.prepare(ns.nominees[0])
 reg=staged_admission(ch,o,root,rows,ns)
 assert reg['outcome']=='SCREENING_COMPLETED_ADMISSION_HELD_CAPACITY'
 assert ch.caller.allocation.started==clock
 assert world['boot'].execute("SELECT count(*) FROM ingestion_work_items WHERE task='FACTUAL_REFRESH'").fetchone()[0]==0
 staged_cost(ch,o,life,gh,records=6,nominees=6,result='SIX_STAGED_HELD_ACTUAL_REMAINING_TIME')


def test_staged_two_eligible_actual_detail_and_committed_readback(world,tmp_path):
 ch,o,life,gh=setup(world,tmp_path,staged=True);root,rows,ns=staged_screen(ch,o);before=snapshot(world['boot'])
 reg=staged_admission(ch,o,root,rows,ns)
 assert reg.kind=='ADMISSION' and reg.grant['source_calls']==2 and reg.grant['writes']==4
 with pytest.raises(Denied,match='REPLAY'):ch.screen()
 for n in ns.nominees:
  result,calls,_=admit_fixture(ch,n,tmp_path);assert result['outcome']=='SUPPORTED_FACTS_VERIFIED' and calls==[1]
 assert_confined(world,'idox',before,admitted=True)
 staged_cost(ch,o,life,gh,records=6,nominees=2,result='TWO_ADMITTED_COUPLED')


@pytest.mark.parametrize('extra_connections',[0,1])
def test_staged_all_nominees_fit_or_whole_set_held(world,tmp_path,extra_connections):
 from tests.e2e_connection_support import entry,SCHEME
 from types import SimpleNamespace
 ch,o,life,gh=setup(world,tmp_path,[entry('SYNTHETIC/FIT',SCHEME)],staged=True)
 root,rows,ns=staged_screen(ch,o);saved=deepcopy(rows);allocation=ch.caller.allocation
 # Synthetic accounting boundary, not memory pressure or extra DB operations.
 spent=allocation.totals();extra=40-2-4-spent['connections']+extra_connections
 boundary=SimpleNamespace(statements=0,attempts=extra,returned_bytes=0,previous={},hard_deadline_events=[]);allocation.budgets.append(boundary)
 result=staged_admission(ch,o,root,rows,ns)
 if extra_connections:
  assert result['outcome']=='SCREENING_COMPLETED_ADMISSION_HELD_CAPACITY'
  assert not any(a.endswith('_ADMISSION_'+ch.auth_capture.rsplit('_',1)[-1]) for a in o.authorities)
  assert world['boot'].execute("SELECT count(*) FROM ingestion_work_items WHERE task='FACTUAL_REFRESH'").fetchone()[0]==0
  assert world['boot'].execute('SELECT count(*) FROM applications').fetchone()[0]==0
  assert ch.caller.read_screening()==saved
 else:assert result.kind=='ADMISSION'
 # Reconciliation assertions for the synthetic counter are separate from DB receipts.
 allocation.budgets.remove(boundary);staged_cost(ch,o,life,gh,records=1,nominees=1,result='CAPACITY_HOLD' if extra_connections else 'CAPACITY_FITS')


@pytest.mark.parametrize('forgery',['outcome','row_outcome','revision','batch','nominees','target'])
def test_staged_admission_refuses_changed_screening_or_nominees(world,tmp_path,forgery):
 from tests.e2e_connection_support import entry,SCHEME
 ch,o,life,gh=setup(world,tmp_path,[entry('SYNTHETIC/FORGE',SCHEME)],staged=True)
 root,rows,ns=staged_screen(ch,o);rows=deepcopy(rows);nominees=ns.nominees;target=None
 if forgery=='outcome':next(r for r in rows if r['task']=='SCREENING')['checkpoint']['count_assessment']['admission']='EXCLUDE'
 if forgery=='row_outcome':next(r for r in rows if r['task']=='SCREENING')['outcome']['outcome']='RETAIN_BELOW_THRESHOLD'
 if forgery=='revision':next(r for r in rows if r['task']=='SCREENING')['revision']='f'*64
 if forgery=='batch':next(r for r in rows if r['task']=='LISTING_METADATA')['checkpoint']['next']=0
 if forgery=='nominees':nominees=()
 if forgery=='target':target={ns.nominees[0].reference:{'council':'bury'}}
 with pytest.raises((Denied,KeyError,TypeError)):
  args=dict(revision=ch.revision,item_limits=ch.item_limits,root=root,receipt=ch.capture_receipt,nominees=nominees,rule=ch.rule,detail_targets=target,allow_test_evidence=True,phase='ADMISSION',screening_rows=rows)
  reg=derive(o,ch.binding,ch.contract,**args)
  o.require_control_sha256=digest(ch._control());o.issue(reg,ch.binding,ch.contract,source=ch.source,outer=ch.outer,evidence=evidence(ch,reg),**args)
 assert world['boot'].execute('SELECT count(*) FROM applications').fetchone()[0]==0
 staged_cost(ch,o,life,gh,records=1,nominees=1,result='FORGERY_REFUSED')


@pytest.mark.parametrize('mutation',['stop','expiry','revocation','stored_checkpoint'])
def test_staged_between_phase_refusal(world,tmp_path,mutation):
 from tests.e2e_connection_support import entry,SCHEME
 ch,o,life,gh=setup(world,tmp_path,[entry('SYNTHETIC/BETWEEN',SCHEME)],staged=True)
 root,rows,ns=staged_screen(ch,o);ctl=ch._control()
 if mutation=='stop':ctl['hard_stop_generation']+=1;ch._write_control(ctl)
 if mutation=='expiry':o.grant_expiry=datetime.now(timezone.utc)-timedelta(seconds=1)
 if mutation=='revocation':ctl['oldham_allowances'][ch.chain_registration.authority]['revoked']=True;ch._write_control(ctl)
 if mutation=='stored_checkpoint':
  changed=deepcopy(next(r for r in rows if r['task']=='SCREENING')['checkpoint']);changed['config_sha256']='f'*64
  world['boot'].execute('UPDATE ingestion_work_items SET checkpoint=%s::json WHERE key=%s',(json.dumps(changed),next(r for r in rows if r['task']=='SCREENING')['key']))
 with pytest.raises(Denied):staged_admission(ch,o,root,rows,ns)
 assert world['boot'].execute('SELECT count(*) FROM applications').fetchone()[0]==0
 if mutation=='expiry':o.grant_expiry=None
 staged_cost(ch,o,life,gh,records=1,nominees=1,result='BETWEEN_PHASE_REFUSAL')


def test_staged_combined_downgrade_refuses_after_real_capture(world,tmp_path):
 ch,o,life,gh=setup(world,tmp_path,staged=True);ch.capture();ch.read_capture()
 root=world['boot'].execute('SELECT row_to_json(w) FROM ingestion_work_items w WHERE key=%s',(ch.root['key'],)).fetchone()[0]
 with pytest.raises(Denied,match='ISSUANCE_MODE'):issue(o,ch,root=root,nominees=ch.nominees().nominees)
 staged_cost(ch,o,life,gh,records=6,nominees=2,result='COMBINED_DOWNGRADE_REFUSED')


def test_staged_commit_uncertainty_cannot_issue_another_phase(world,tmp_path,monkeypatch):
 ch,o,life,gh=setup(world,tmp_path,staged=True);root,rows,ns=staged_screen(ch,o)
 o.effect_uncertain=True
 with pytest.raises(Denied,match='RECONCILE'):staged_admission(ch,o,root,rows,ns)
 with pytest.raises(Denied,match='RECONCILE'):life.teardown()
 assert world['boot'].execute('SELECT count(*) FROM applications').fetchone()[0]==0
 # Injection removed only by the disposable test owner, not library compensation.
 o.effect_uncertain=False;staged_cost(ch,o,life,gh,records=6,nominees=2,result='INJECTED_UNCERTAINTY_NO_REPLAY')


@pytest.mark.parametrize('phase',['SCREENING','ADMISSION'])
@pytest.mark.parametrize('fault',['commit_ack','readback'])
def test_staged_actual_issuance_uncertainty_blocks_every_followup(world,tmp_path,phase,fault):
 from tests.e2e_connection_support import entry,SCHEME
 from verification.ingestion_storage.operational_publication import Uncertain
 ch,o,life,gh=setup(world,tmp_path,[entry('SYNTHETIC/ACK',SCHEME)],staged=True)
 if phase=='ADMISSION':root,rows,ns=staged_screen(ch,o)
 else:
  ch.capture();ch.read_capture();root=world['boot'].execute('SELECT row_to_json(w) FROM ingestion_work_items w WHERE key=%s',(ch.root['key'],)).fetchone()[0];rows=None;ns=None
 if fault=='commit_ack':
  connector=o.connector;lost=[]
  class Proxy:
   def __init__(self,c):self.c=c
   def __getattr__(self,n):return getattr(self.c,n)
   def execute(self,q,params=None):
    result=self.c.execute(q,params)
    if q=='COMMIT' and not lost:lost.append(True);raise ConnectionError('SYNTHETIC_ACK_LOSS')
    return result
  o.connector=lambda:Proxy(connector())
 else:
  query=o.q
  def fail(c,statement,params=None,**kw):
   if o.awaiting_verification and isinstance(statement,str) and statement.startswith('SELECT pg_has_role'):raise ConnectionError('SYNTHETIC_READBACK_LOSS')
   return query(c,statement,params,**kw)
  o.q=fail
 args=dict(root=root,phase=phase,nominees=() if ns is None else ns.nominees,screening_rows=rows)
 with pytest.raises((Uncertain,ConnectionError)):issue(o,ch,**args)
 assert o.effect_uncertain
 issued=[a for a in ch._control()['grants'] if '_'+phase+'_' in a];assert len(issued)==1
 before=(o.commands,o.connections,len(gh.calls))
 with pytest.raises(Denied,match='RECONCILE'):issue(o,ch,**args)
 with pytest.raises(Denied,match='RECONCILE'):life.teardown()
 assert before==(o.commands,o.connections,len(gh.calls))
 assert world['boot'].execute('SELECT count(*) FROM applications').fetchone()[0]==0
 if phase=='ADMISSION':
  for row in rows:
   actual=world['boot'].execute('SELECT state,checkpoint FROM ingestion_work_items WHERE key=%s',(row['key'],)).fetchone()
   assert actual==('COMPLETE',row['checkpoint'])


def test_staged_issuance_waits_cannot_consume_future_source_reserve(world,tmp_path,monkeypatch):
 from tests.e2e_connection_support import entry,SCHEME
 ch,o,life,gh=setup(world,tmp_path,[entry('SYNTHETIC/TAIL',SCHEME)],staged=True)
 root,rows,ns=staged_screen(ch,o);query=o.q;allocation=ch.caller.allocation;original_deadline=allocation.deadline
 # Advance the shared deadline during issuance, after its pre-effect gate.
 # No sleep or pressure workload; actual DB inserts remain uncommitted.
 injected=[]
 def advance(c,statement,params=None,**kw):
  result=query(c,statement,params,**kw)
  if isinstance(statement,str) and statement.startswith('INSERT INTO public.ingestion_work_items') and not injected:
   injected.append(True);o.issuance_deadline=time.monotonic()-1
  return result
 o.q=advance
 with pytest.raises(Denied,match='ISSUANCE_WORK_RESERVE'):staged_admission(ch,o,root,rows,ns)
 assert injected and allocation.deadline==original_deadline
 assert world['boot'].execute("SELECT count(*) FROM ingestion_work_items WHERE task='FACTUAL_REFRESH'").fetchone()[0]==0
 assert not any('_ADMISSION_' in a for a in ch._control()['grants'])
 staged_cost(ch,o,life,gh,records=1,nominees=1,result='ISSUANCE_TAIL_RESERVE_REFUSED')
