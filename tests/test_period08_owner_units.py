import copy,json
from contextlib import contextmanager
import pytest
from verification.ingestion_storage import period08_successor as p08,owner_pilot as p,intake_owner as op
from tests.test_attempt05_startup import test_actual_runtime_guard_preflight_never_qualifies as startup,test_qualification_only_never_reaches_daily_on_either_outcome as qualification

@pytest.mark.parametrize('kind',['clean','dirty','git_failure'])
def test_actual_startup_guard_remains_closed(monkeypatch,tmp_path,capsys,kind):
 monkeypatch.setattr(p,'PERIOD',p08.SUCCESSOR);startup(monkeypatch,tmp_path,capsys,kind)

@pytest.mark.parametrize('status',['VERIFIED_BOTH_RESTRICTED_ROLES','REFUSED'])
def test_qualification_boundary(monkeypatch,capsys,status):
 monkeypatch.setattr(p,'PERIOD',p08.SUCCESSOR);qualification(monkeypatch,capsys,status)

@pytest.mark.parametrize('field',['revision','workflow_sha256','manifest_sha256','tree','branch'])
def test_each_release_field_refuses_drift(field):
 r=dict(execution_binding=copy.deepcopy(p08.BINDING),tree=p08.TREE,branch=p08.BRANCH)
 assert p08.release(r)==r
 (r['execution_binding'] if field in p08.BINDING else r)[field]='changed'
 with pytest.raises(op.Denied,match='P08_RELEASE_BINDING'):p08.release(r)

def test_binding_accepts_only_exact08(monkeypatch):
 monkeypatch.setattr(p,'PERIOD',p08.SUCCESSOR)
 r=dict(execution_binding=p08.BINDING,tree=p08.TREE,branch=p08.BRANCH,deployment='dep-'+'a'*20)
 monkeypatch.setenv('PROPERTYAIGENT_INTAKE_SOURCE_RELEASE',json.dumps(r))
 profile=p.source_profile(dict(execution_binding=p08.BINDING,browser_canary='LAUNCHED_AND_CLOSED',browser_path='/fixture/browser',browser_sha256='a'*64),p08.BINDING['revision'])
 b,policy=p.fixed_binding(r,profile,'192.0.2.1','a'*64)
 assert b['accepted_stop']==policy['expected_stop']==p08.ACCEPTED
 for field,value in [('period','b-dbpilot-20261027-1102-09'),('period07_receipt_sha256','0'*64),('accepted_stop',dict(p08.ACCEPTED,hard_stop_generation=10))]:
  changed=copy.deepcopy(b);changed[field]=value
  with pytest.raises(op.Denied):op.validate_binding(changed)

def test_uncertain_cli_does_not_repeat_or_proceed(monkeypatch,capsys):
 from scripts import owner_period08 as cli
 calls=[]
 class DB:
  @contextmanager
  def connection(self):calls.append('connection');yield object()
 monkeypatch.setenv('PROPERTYAIGENT_OWNER_PILOT_AUTHORITY',p08.SUCCESSOR)
 monkeypatch.setattr(p08,'configure',lambda:None);monkeypatch.setattr(p,'Database',DB)
 monkeypatch.setattr(p08,'binding_from_saved_state',lambda _: {})
 def lost(*a):calls.append('dispose');raise RuntimeError('PRIVATE_SENTINEL')
 monkeypatch.setattr(p08,'dispose',lost);monkeypatch.setattr(p08,'inspect',lambda *a:pytest.fail('Must stop after uncertain write'))
 assert cli.main(['--action','dispose'])==2 and calls==['connection','dispose']
 assert 'PRIVATE_SENTINEL' not in capsys.readouterr().out
