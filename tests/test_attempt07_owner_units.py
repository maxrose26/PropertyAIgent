import copy,json,time
import pytest
from verification.ingestion_storage import attempt06_recovery as a06,intake_owner as op,owner_pilot as p
from tests.test_attempt05_startup import test_actual_runtime_guard_preflight_never_qualifies as startup,test_qualification_only_never_reaches_daily_on_either_outcome as qualification

@pytest.mark.parametrize('kind',['clean','dirty','git_failure'])
def test_successor_keeps_startup_guard(monkeypatch,tmp_path,capsys,kind):
 monkeypatch.setattr(p,'PERIOD',a06.SUCCESSOR);startup(monkeypatch,tmp_path,capsys,kind)

@pytest.mark.parametrize('status',['VERIFIED_BOTH_RESTRICTED_ROLES','REFUSED'])
def test_successor_keeps_qualification_boundary(monkeypatch,capsys,status):
 monkeypatch.setattr(p,'PERIOD',a06.SUCCESSOR);qualification(monkeypatch,capsys,status)

def test_successor_binding_is_exact_and_receipt_required(monkeypatch):
 e=dict(revision='1'*40,workflow_sha256='2'*64,manifest_sha256='3'*64)
 release=dict(execution_binding=e,deployment='dep-'+'a'*20,attempt06_receipt_sha256='a'*64)
 monkeypatch.setenv('PROPERTYAIGENT_INTAKE_SOURCE_RELEASE',json.dumps(release));monkeypatch.setattr(p,'PERIOD',a06.SUCCESSOR)
 profile=p.source_profile(dict(execution_binding=e,browser_canary='LAUNCHED_AND_CLOSED',browser_path='/fixture/browser',browser_sha256='a'*64),e['revision'])
 b,policy=p.fixed_binding(release,profile,'192.0.2.1','a'*64)
 assert b['period']==a06.SUCCESSOR and b['accepted_stop']==a06.ACCEPTED and policy['expected_stop']==a06.ACCEPTED
 for field,value in [('period','b-dbpilot-20261027-1102-08'),('attempt06_receipt_sha256',None),('accepted_stop',op.ACCEPTED_STOP)]:
  changed=copy.deepcopy(b);changed[field]=value
  with pytest.raises((op.Denied,TypeError)):op.validate_binding(changed)

def test_production_evidence_hashes_are_pinned():
 assert a06.EVIDENCE=={'final/result-before-publication.json':'3386dfb045fe64cd149faea835a0b377b7d25e3733eb53e31fd6687644de1e11','final/events-before-publication.json':'8a23b2641ce84002f7c726aa9de6681570b7d12ce8f874fc639910cf03ee0294'}

def test_cli_stops_on_unknown_ack_without_followup(monkeypatch,capsys):
 from scripts import owner_attempt06 as cli
 from contextlib import contextmanager
 calls=[]
 class DB:
  @contextmanager
  def connection(self):calls.append('connection');yield object()
 monkeypatch.setenv('PROPERTYAIGENT_OWNER_PILOT_AUTHORITY',a06.SUCCESSOR)
 monkeypatch.setattr(a06,'configure_successor',lambda:None)
 monkeypatch.setattr(p,'Database',DB);monkeypatch.setattr(a06,'binding_from_saved_state',lambda _: {})
 def lost(*_):calls.append('recovery');raise RuntimeError('SENSITIVE_EXCEPTION')
 monkeypatch.setattr(a06,'recover',lost);monkeypatch.setattr(a06,'readback',lambda *a:pytest.fail('must stop on uncertain mutation'))
 assert cli.main(['--action','settle'])==2
 assert calls==['connection','recovery'] and 'SENSITIVE' not in capsys.readouterr().out
