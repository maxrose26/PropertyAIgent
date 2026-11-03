from datetime import datetime,timezone
from types import SimpleNamespace
import pytest
from verification.ingestion_storage import owner_pilot as p
from app import owner_intake_control as control
from app.security import access

def stamp(value):return datetime.fromisoformat(value).timestamp()

def test_midnight_guard_and_fixed_historical_collection_dates():
    latest=stamp('2026-11-03T23:25:00+00:00')
    assert p.start_availability(latest)['available'] is True
    late=p.start_availability(latest+0.001)
    assert late['available'] is False and late['next_available_at']==stamp('2026-11-04T00:00:00+00:00')
    ready=p.start_availability(stamp('2026-11-04T09:00:00+00:00'))
    assert ready['available'] is True and ready['window']=={'start':'2026-10-27','end':'2026-11-02'}
    assert ready['access_seconds']==2100

def test_unavailable_start_refuses_before_child_or_credentials(monkeypatch):
    now=stamp('2026-11-03T23:25:20+00:00')
    monkeypatch.setattr(control.time,'time',lambda:now)
    monkeypatch.setattr(access,'require_operator',lambda *_:SimpleNamespace(issuer='issuer',subject='owner',machine=False))
    monkeypatch.setattr(access,'load_policy',lambda:{'issuer':'issuer','owner_subject':'owner'})
    monkeypatch.setattr(control.subprocess,'Popen',lambda *_a,**_k:pytest.fail('CHILD_STARTED'))
    result=control.start('run',owner_checked=True,checked_at=now)
    assert result['status']=='NOT_STARTED_TIME_WINDOW' and result['child_started'] is False
    assert result['provider_calls']==0 and result['authority_consumed'] is False

def test_guard_is_display_only_never_backdates_or_changes_binding(monkeypatch):
    now=stamp('2026-11-04T09:00:00+00:00')
    release={'deployment':'dep-'+'a'*20,'execution_binding':{'revision':'a'*40,'workflow_sha256':'b'*64,'manifest_sha256':'c'*64}}
    import json
    monkeypatch.setenv('PROPERTYAIGENT_INTAKE_SOURCE_RELEASE',json.dumps(release))
    b,policy=p.fixed_binding(release,{},'192.0.2.1','a'*64,now=now)
    assert b['valid_until']==now+2100 and policy['expires_at']==b['valid_until']-185
    assert b['timing_policy']['execution_day']=='2026-11-04' and b['fixed_window']=={'start':'2026-10-27','end':'2026-11-02'}

def test_existing_readback_entrypoint_reports_inspection_success_without_mutation(monkeypatch,capsys):
    import sys
    from scripts import owner_managed_pilot as command
    class Pilot:
        def inspect(self):return {'status':'READ_ONLY_EVIDENCE_SAVED','provider_mutations':0,'release_intent_present':False}
    monkeypatch.setattr(command,'Pilot',Pilot)
    monkeypatch.setattr(sys,'argv',['owner','--action','status'])
    assert command.main()==0
    assert 'READ_ONLY_EVIDENCE_SAVED' in capsys.readouterr().out
