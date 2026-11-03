import json,time
from types import SimpleNamespace
import pytest
from app import owner_intake_control as c
from app.security import access

def owner(monkeypatch,*,subject='owner',machine=False):
    monkeypatch.setattr(access,'require_operator',lambda *_:SimpleNamespace(issuer='issuer',subject=subject,machine=machine))
    monkeypatch.setattr(access,'load_policy',lambda:{'issuer':'issuer','owner_subject':'owner'})

@pytest.mark.parametrize('subject,machine',[('other',False),('owner',True)])
def test_owner_boundary_before_any_process(monkeypatch,subject,machine):
    owner(monkeypatch,subject=subject,machine=machine)
    monkeypatch.setattr(c.subprocess,'Popen',lambda *_a,**_k:pytest.fail('UNAUTHORISED_CHILD'))
    with pytest.raises(access.AccessDenied):c.start('recover')

def test_supported_launch_has_no_secret_arguments_and_excludes_unrelated_credentials(monkeypatch):
    owner(monkeypatch);monkeypatch.setattr(c,'_process',None)
    monkeypatch.setenv('DATABASE_URL','SYNTHETIC_DATABASE_SENTINEL');monkeypatch.setenv('PROPERTYAIGENT_INTAKE_RENDER_API_KEY','SYNTHETIC_RENDER_SENTINEL');monkeypatch.setenv('OPENAI_API_KEY','SYNTHETIC_AI_SENTINEL')
    calls=[]
    def popen(command,**kw):calls.append((command,kw));return SimpleNamespace(poll=lambda:None)
    monkeypatch.setattr(c.subprocess,'Popen',popen)
    seen=time.time();result=c.start('run',owner_checked=True,checked_at=seen)
    command,kw=calls[0]
    assert command[-2:]==['--owner-checked-at',str(seen)] and all('SENTINEL' not in x for x in command)
    assert kw['env']['DATABASE_URL']=='SYNTHETIC_DATABASE_SENTINEL' and 'OPENAI_API_KEY' not in kw['env']
    assert kw['stdin']==c.subprocess.DEVNULL and kw['stderr']==c.subprocess.DEVNULL and kw['start_new_session'] is True
    assert 'SENTINEL' not in json.dumps(result)
    with pytest.raises(ValueError,match='ALREADY_RUNNING'):c.start('run',owner_checked=True,checked_at=seen)
    assert len(calls)==1

def test_stale_observation_and_unconfigured_boot_cannot_launch(monkeypatch):
    owner(monkeypatch);monkeypatch.delenv('PROPERTYAIGENT_INTAKE_PREPARE_ONCE',raising=False)
    monkeypatch.setattr(c.subprocess,'Popen',lambda *_a,**_k:pytest.fail('UNAUTHORISED_CHILD'))
    with pytest.raises(ValueError,match='EXPIRED'):c.start('run',owner_checked=True,checked_at=time.time()-301)
    with pytest.raises(ValueError,match='PREPARATION_ONLY'):c.start('run',server_prepare=True,owner_checked=True,checked_at=time.time())

def test_recovery_stops_only_this_owned_process_before_independent_close(monkeypatch):
    owner(monkeypatch);events=[]
    active=SimpleNamespace(pid=123456,poll=lambda:None,wait=lambda **kw:events.append('wait'))
    monkeypatch.setattr(c,'_process',active);monkeypatch.setattr(c.os,'killpg',lambda pid,sig:events.append((pid,sig)))
    monkeypatch.setattr(c.subprocess,'Popen',lambda cmd,**kw:events.append(cmd) or SimpleNamespace(poll=lambda:None))
    c.start('recover')
    assert events[0]==(123456,c.signal.SIGTERM) and events[1]=='wait' and events[2][-2:]==['--action','recover']
