"""Council-free pure refusals and policy derivation; no installed-state claims."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import pytest
from app.ingestion.ledger import Denied,DEFAULT_LIMITS,digest
from tests.test_closed_idox_units import START,END
from tests.e2e_connection_support import idox_contract,idox_audit,entry,SCHEME,outer
from verification.ingestion_storage import oldham_policy as policy,observation_worker_sql as obs,screening_v3_worker_sql as v3
from verification.ingestion_storage.oldham_authority import OldhamOwner,STOP_STATE,stop_identity,derive,registration_value
from verification.ingestion_storage.oldham_allocation import capacity,Allocation
from verification.ingestion_storage.scope_binding import binding_for

def inputs():
 o=OldhamOwner(None,lambda *_:None,lambda:None,expiry=datetime.now(timezone.utc)+timedelta(minutes=30),bindings=dict(revision='a'*40,workflow_sha256='b'*64,manifest_sha256='c'*64))
 b=binding_for('oldham');c=idox_contract('oldham',START,END);source=idox_audit('oldham',[entry('SYNTHETIC/1',SCHEME)],START,END);out=outer();args=dict(revision='a'*40,item_limits=DEFAULT_LIMITS)
 reg=derive(o,b,c,**args)
 evidence=dict(source_sha256=digest(source),outer_sha256=digest(out),qualification_sha256=c.qualification_sha256,registration_sha256=digest(registration_value(reg)))
 return o,b,c,source,out,args,reg,evidence

def test_minimal_policy_inverse_and_historical_predicate_untouched():
 original=v3.original_function(obs.combined());assert policy.undo(policy.replacement())==original
 assert 'ingestion_register_bolton_exception' not in policy.installation_script()
 assert 'CREATE ROLE ' not in policy.installation_script()
 assert policy.replacement().index('OLDHAM_ALLOWANCE_INVALID')<policy.replacement().index("IF ctl->'global_stop'")

@pytest.mark.parametrize('field,value',[('global_stop',None),('manual_stop',None),('last_hard_stop','OTHER'),('hard_stop_generation',4),('hard_stop_generation','3')])
def test_every_stop_change_including_clearing_refuses(field,value):
 c=deepcopy(STOP_STATE);c[field]=value
 with pytest.raises(Denied,match='OLDHAM_UNKNOWN_STOP'):stop_identity(c)

@pytest.mark.parametrize('field',list(STOP_STATE))
def test_missing_stop_fields_refuse(field):
 c=deepcopy(STOP_STATE);c.pop(field)
 with pytest.raises(Denied):stop_identity(c)

@pytest.mark.parametrize('field',('authority','root_key','kind','rows','insert','grant','bindings'))
def test_altered_registration_never_connects(field):
 o,b,c,source,out,args,reg,evidence=inputs();setattr(reg,field,None)
 with pytest.raises(Denied):o.issue(reg,b,c,source=source,outer=out,evidence=evidence,**args)
 assert o.connections==0

@pytest.mark.parametrize('field',('source_sha256','outer_sha256','qualification_sha256','registration_sha256'))
def test_hash_shaped_but_wrong_evidence_refuses(field):
 o,b,c,source,out,args,reg,evidence=inputs();evidence[field]='f'*64
 with pytest.raises(Denied):o.issue(reg,b,c,source=source,outer=out,evidence=evidence,**args)
 assert o.connections==0

@pytest.mark.parametrize('which',('source','outer'))
def test_missing_capture_inputs_refuses(which):
 o,b,c,source,out,args,reg,evidence=inputs();kw=dict(source=source,outer=out);kw[which]=None
 with pytest.raises(Denied):o.issue(reg,b,c,evidence=evidence,**kw,**args)
 assert o.connections==0

def test_capacity_and_cumulative_exhaustion():
 assert capacity(6,2)['connections']==21
 assert capacity(0,0)['connections']==3
 with pytest.raises(Denied,match='CAPACITY'):capacity(60,60)
 a=Allocation();assert a.totals()['commands']==0
 a.failed=True
 with pytest.raises(Denied):a.check()

def test_shared_budget_reserves_bytes_deadline_and_latches_uncertain_close(monkeypatch):
 from types import SimpleNamespace
 from verification.ingestion_storage import oldham_allocation as a
 allocation=a.Allocation();prior_budget=SimpleNamespace(statements=2,attempts=1,returned_bytes=100,previous={},hard_deadline_events=[])
 allocation.budgets=[prior_budget]
 fake=SimpleNamespace(check=lambda:None,close=lambda *_:dict(cleanup='UNCERTAIN',connections_closed=False),statements=0,attempts=0,returned_bytes=0,previous={},hard_deadline_events=[])
 seen={}
 def make(self,**kw):seen.update(kw);return fake
 monkeypatch.setattr(a.ChainCaller,'_budget',make)
 caller=object.__new__(a.FiniteCaller);caller.allocation=allocation
 b=caller._budget()
 assert seen['returned_bytes']==a.CAPS['returned_bytes']-a.RESERVE['returned_bytes']-100
 assert b.hard_stop_at==allocation.started+270
 b.close([])
 with pytest.raises(Denied,match='RECONCILE'):allocation.check()

@pytest.mark.parametrize('records,nominees',[(7,7),(60,60),(61,0),(-1,0),(1,2)])
def test_package_capacity_refuses_before_any_work(records,nominees):
 with pytest.raises(Denied):capacity(records,nominees)

def test_documented_installation_and_rollback_are_mechanically_exact():
 from pathlib import Path
 root=Path('docs/design/oldham-finite-authority-20261027')
 assert (root/'installation.sql').read_text()==policy.installation_script()
 assert (root/'rollback.sql').read_text()==policy.rollback_script()

def test_runtime_does_not_exhaust_separate_admin_cleanup_clock(monkeypatch):
 from verification.ingestion_storage import oldham_authority as a
 clock=[100.];monkeypatch.setattr(a.time,'monotonic',lambda:clock[0])
 o,*_=inputs()
 with o.admin_phase():clock[0]+=5
 assert o.admin_elapsed==5
 clock[0]+=250 # runtime, not administrative work
 o.tearing_down=True;o.check()
 with o.admin_phase():clock[0]+=5;o.check()
 assert o.admin_elapsed==10
 clock[0]=581
 with pytest.raises(Denied,match='OUTER'):o.check()

def test_short_lifetime_refuses_before_capture_effects():
 o,b,c,source,out,args,reg,evidence=inputs();o.expiry=datetime.now(timezone.utc)+timedelta(seconds=10)
 with pytest.raises(Denied,match='INSUFFICIENT_LIFETIME'):o.issue(reg,b,c,source=source,outer=out,evidence=evidence,**args)
 assert o.connections==0

def test_shared_owner_outer_deadline_is_not_restarted(monkeypatch):
 from verification.ingestion_storage import oldham_allocation as a
 clock=[100.];monkeypatch.setattr(a.time,'monotonic',lambda:clock[0])
 package_start=clock[0];clock[0]+=200
 allocation=a.Allocation(package_started=package_start)
 assert allocation.deadline==550 #450s package reserve, earlier than runtime570
 clock[0]=550
 with pytest.raises(Denied,match='OUTER_CLOSURE_RESERVE'):allocation.check()

@pytest.mark.parametrize('version,threshold,related',[('v1',10,False),('v3',11,False),('v3',10,True)])
def test_owner_configuration_selection_cannot_change_frozen_screening(version,threshold,related):
 from app.ingestion.listing_screening import ScreeningRule,RULE_V1,RULE_V3
 o,b,c,*_=inputs();rule=ScreeningRule(RULE_V1,link_related=related) if version=='v1' else ScreeningRule(RULE_V3,unit_threshold=threshold,link_related=related)
 with pytest.raises(Denied,match='OLDHAM_FROZEN_SCREENING'):
  derive(o,b,c,revision='a'*40,item_limits=DEFAULT_LIMITS,root={},rule=rule)
 assert o.connections==0


def test_staged_remaining_time_reserves_entire_set_and_never_restarts(monkeypatch):
 from verification.ingestion_storage import oldham_allocation as a
 clock=[100.];monkeypatch.setattr(a.time,'monotonic',lambda:clock[0]);alloc=a.Allocation()
 assert alloc.require_remaining(dict(nominees=3))
 clock[0]=320 #50 work seconds remain, not enough for3*45
 assert not alloc.require_remaining(dict(nominees=3))
 assert alloc.require_remaining(dict(nominees=1))
 assert alloc.started==100 and alloc.deadline==370
 clock[0]=325
 assert not alloc.require_remaining(dict(nominees=1))


def test_staged_pending_expiry_does_not_recharge_completed_batches():
 from verification.ingestion_storage.limit_reconciliation import pending_grant_problems
 assert not pending_grant_problems(195,phase='ADMISSION',batches=12,nominees=1)
 assert pending_grant_problems(194,phase='ADMISSION',batches=0,nominees=1)
 assert not pending_grant_problems(690,phase='SCREENING',batches=4)
 assert pending_grant_problems(689,phase='SCREENING',batches=4)


def test_staged_expiry_extension_and_combined_downgrade_refuse_before_connection():
 o,b,c,source,out,args,reg,evidence=inputs();o.issuance_mode='STAGED'
 with pytest.raises(Denied,match='ISSUANCE_MODE'):o.issue(reg,b,c,source=source,outer=out,evidence=evidence,**args)
 o.issuance_mode=None;o.original_expiry=o.expiry-timedelta(seconds=1)
 reg=derive(o,b,c,phase='CAPTURE',**args);evidence['registration_sha256']=digest(registration_value(reg))
 with pytest.raises(Denied,match='ORIGINAL_EXPIRY'):o.issue(reg,b,c,source=source,outer=out,evidence=evidence,phase='CAPTURE',**args)
 assert o.connections==0


@pytest.mark.parametrize('count',[11,19])
def test_synthetic_multipage_fixture_and_capture_seal_are_canonical(count):
 from app.ingestion.ledger import digest
 from tests.e2e_connection_support import EXTENSION
 o,b,c,_,out,args,_,_=inputs()
 source=idox_audit('oldham',[entry(f'SYNTHETIC/P{i}',EXTENSION) for i in range(count)],START,END)
 assert source['enumeration_evidence']=='COUNT_RECONCILED' and len(source['records'])==count and len(source['pages'])==2
 projected=c.project(source,out,DEFAULT_LIMITS,source_bytes_limit=512*1024)
 assert len(projected['records'])==count
 assert digest(dict(source=digest(source),outer=digest(out),qualification=c.qualification_sha256,scope=c.scope()))
