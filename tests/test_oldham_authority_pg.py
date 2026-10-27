"""Actual owner issuance and restricted caller; fixtures never represent live authority."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json,time
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
 w['boot'].execute('GRANT pg_read_all_stats TO provisioning_migrator')
 yield w
 with pytest.raises(StopIteration):next(gen)

class GitHub:
 def __init__(self):self.present={'DATABASE_URL'};self.calls=[]
 def names(self):self.calls.append('NAMES');return sorted(self.present)
 def put_secret(self,name,value):assert isinstance(value,str) and value;self.calls.append(('PUT',name));self.present.add(name)
 def call(self,method,path):assert method=='DELETE';name=path.rsplit('/',1)[-1];self.calls.append(('DELETE',name));self.present.discard(name)

def owner(w,chain):
 o=OldhamOwner(lambda:w['connect']('provisioning_migrator'),lambda *_:None,lambda:None,identity='provisioning_migrator',expiry=datetime.now(timezone.utc)+timedelta(minutes=30),bindings=dict(OWNER_BINDINGS))
 o.require_control_sha256=digest(chain._control());return o

def evidence(chain,reg):return dict(source_sha256=digest(chain.source),outer_sha256=digest(chain.outer),qualification_sha256=chain.contract.qualification_sha256,registration_sha256=digest(registration_value(reg)))

def issue(o,ch,*,root=None,nominees=()):
 args=dict(revision=ch.revision,item_limits=ch.item_limits)
 extra={} if root is None else dict(root=root,receipt=ch.capture_receipt,nominees=tuple(nominees),rule=ch.rule,detail_targets=None,allow_test_evidence=True)
 reg=derive(o,ch.binding,ch.contract,**args,**extra)
 o.require_control_sha256=digest(ch._control())
 o.issue(reg,ch.binding,ch.contract,source=ch.source,outer=ch.outer,evidence=evidence(ch,reg),**args,**extra)
 ch.bindings.update(reg.bindings)
 return reg

def setup(w,tmp,entries=None):
 ch=Chain(w,tmp,'idox','a'*40,entries,council='oldham').owner_reset()
 ctl=ch._control();ctl.update(deepcopy(STOP_STATE));ch._write_control(ctl)
 for r in RESTRICTED:w['boot'].execute(sql.SQL('ALTER ROLE {} NOLOGIN PASSWORD NULL').format(sql.Identifier(r)))
 ch.supervised_source();o=owner(w,ch);reg=issue(o,ch)
 ch.root=reg.rows[0];ch.capture_registration=reg
 allocation=Allocation()
 # Same production caller with its one cumulative accounted budget, not a mocked effect.
 old=ch.caller
 ch.caller=FiniteCaller(old.sb,old.contract,old.rule,old.urls,revision=old.revision,bindings=old.bindings,capture_authority=old.capture_authority,chain_authority=old.chain_authority,allow_test_evidence=True,allocation=allocation)
 gh=GitHub();life=Lifecycle(o,gh)
 def url_factory(role,password):
  from sqlalchemy.engine import make_url
  return make_url(w['urls'][role]).set(password=password).render_as_string(hide_password=False)
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
 print('OLDHAM_ACTUAL_OWNER_CHAIN',json.dumps(dict(admin=o.accounting(),runtime=ch.caller.allocation.totals(),identities=2,factual_deliveries=2,credential_teardown=life.state),default=str))

@pytest.mark.parametrize('change',[('global_stop',None),('manual_stop','OTHER'),('hard_stop_generation',4),('last_hard_stop','OTHER')])
def test_sql_stop_changes_invalidate_even_when_global_stop_cleared(world,tmp_path,change):
 ch,o,life,gh=setup(world,tmp_path);ctl=ch._control();ctl[change[0]]=change[1];ch._write_control(ctl)
 with pytest.raises(Exception):ch.capture()
 assert world['boot'].execute('SELECT count(*) FROM applications').fetchone()[0]==0
 life.teardown()

@pytest.mark.parametrize('fault',('revoked','expired','grant_binding','package','missing','source_cap'))
def test_sql_allowance_tampering_refuses(world,tmp_path,fault):
 ch,o,life,gh=setup(world,tmp_path);ctl=ch._control();a=ch.auth_capture;e=ctl['oldham_allowances'][a]
 if fault=='revoked':e['revoked']=True
 elif fault=='expired':e['expires_at']=0
 elif fault=='grant_binding':e['grant_binding']['capture_key']='f'*64
 elif fault=='package':e['package']['scope']['start']='2026-11-10'
 elif fault=='missing':del ctl['oldham_allowances'][a]
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
