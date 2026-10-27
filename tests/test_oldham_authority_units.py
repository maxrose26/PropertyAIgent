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
