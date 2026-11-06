"""Scope admission and both unchanged clocks, using actual validators."""
import copy,json
from dataclasses import FrozenInstanceError
import pytest
from tests.test_owner_database_pilot import bound
from verification.ingestion_storage import intake_successor as sc,owner_pilot as pilot,intake_owner as op
from verification.ingestion_storage.intake_scope_policy import BOLTON
from verification.ingestion_storage.intake_owner_operations import validate_policy


def test_policy_is_immutable_and_does_not_admit_detail():
 with pytest.raises(FrozenInstanceError):BOLTON.start='2026-11-02'
 from verification.ingestion_storage.scope_binding import binding_for,intake_binding_for,check_detail_target
 with pytest.raises(op.Denied,match='SCOPE_HISTORICAL_ONLY'):binding_for('bolton')
 with pytest.raises(op.Denied,match='INTAKE_NO_DETAIL'):check_detail_target(intake_binding_for('bolton'),{}, {})

@pytest.mark.parametrize('elapsed,allowed',[(0,True),(599.999,True),(600,False),(1140,False),(2100,False)])
def test_actual_scope_owner_clock(bound,monkeypatch,elapsed,allowed):
 old,_,_=bound;release=dict(execution_binding=old['execution_binding'],tree='1'*40,branch=sc.BRANCH,deployment=old['retained_deployment'])
 monkeypatch.setattr(sc,'BINDING',old['execution_binding']);monkeypatch.setattr(sc,'TREE',release['tree'])
 for name in ('PERIOD','PREDECESSOR','OWNER_PERIOD','OWNER_RUN','WINDOW'):monkeypatch.setattr(pilot,name,getattr(pilot,name))
 sc.configure();t=old['timing_policy']['bound_at']
 b,p=pilot.fixed_binding(release,old['render_profile'],old['hostaddr'],old['render_config_sha256'],now=t)
 assert b['valid_until']==t+2100 and p['expires_at']==t+1915 and b['valid_until']-p['expires_at']==185
 assert b['scope_policy_sha256']==BOLTON.fingerprint() and p['councils']==BOLTON.councils()
 if allowed:assert validate_policy(b,p,now=t+elapsed)==p
 else:
  with pytest.raises(op.Denied):validate_policy(b,p,now=t+elapsed)


def test_finish_guard_unchanged_and_release_pin_not_in_sql():
 a=sc.prior.registration_sql();b=sc.registration_sql()
 start="  IF p->>'operation'='intake_finish' THEN";end="  IF ctl ? 'intake_run'"
 assert a[a.index(start):a.index(end)]==b[b.index(start):b.index(end)]
 # The worker's inventory must stay identical when the owner pins the sealed
 # scraper commit: exact release is checked by the existing owner issuer.
 before=b
 original=sc.BINDING
 try:
  sc.BINDING=dict(revision='a'*40,workflow_sha256='b'*64,manifest_sha256='c'*64)
  assert sc.registration_sql()==before
 finally:sc.BINDING=original
