"""Affected release boundary; real validators, synthetic journal/provider I/O."""
import copy,hashlib,json,sys,time
from types import SimpleNamespace
import pytest
from verification.ingestion_storage import owner_pilot as p,intake_owner as op
from verification.ingestion_storage.intake_owner_io import service_guard

@pytest.fixture
def pilot(monkeypatch):
    e=dict(revision='938f3f18d8b75c6467290461139b03bf9b95a338',workflow_sha256='5b87c6cbef2944fa05468314fc6daefc19b785644b04e04d1ff382b0596cadea',manifest_sha256='26a07287b6d7ebf89eedb04b29e36c56e2d8a67acb7282b1821ed5273509de99')
    release=dict(execution_binding=e,tree='3ebc682a285bb0ee82afd4aecc607b464c444474')
    monkeypatch.setenv('PROPERTYAIGENT_INTAKE_SOURCE_RELEASE',json.dumps(release))
    monkeypatch.setattr(p.time,'time',lambda:1793793600.0)  # 4 November noon; no fake live observation.
    artifact=dict(execution_binding=e,browser_canary='LAUNCHED_AND_CLOSED',browser_path='/fixture/browser',browser_sha256='a'*64)
    receipt=dict(period=p.PERIOD,execution_binding=e,tree=release['tree'],status='CLEAN_CHECKOUT_VERIFIED_BEFORE_QUALIFICATION')
    service=dict(id=p.SERVICE,type='cron_job',suspended='suspended',autoDeploy='no',branch='master',serviceDetails=dict(schedule='0 5 * * *',envSpecificDetails=dict(startCommand='/bin/true',buildCommand='original')))
    env={'PLAYWRIGHT_BROWSERS_PATH':'0','DATABASE_URL':'SYNTHETIC_SECRET_SENTINEL'}
    state=dict(period=p.PERIOD,status='ARTIFACT_READY',intents={},original_guard=service_guard(service),original_environment=env,
        deployment='dep-dblhmq3m8hqs739auu5g',artifact=artifact,profile=p.source_profile(artifact,e['revision']),
        startup_preflight={'receipt':receipt,'sha256':hashlib.sha256(p.canonical(receipt)).hexdigest()},
        stable_credentials={'verifier_sha256':{r:'b'*64 for r in op.ROLES}})
    class Journal:
        previous='c'*64;ordinal=31
        def load(self):return copy.deepcopy(state)
        def save(self,*a,**k):pytest.fail('JOURNAL_WRITE')
    pilot=object.__new__(p.Pilot);pilot.journal=Journal();pilot.db=SimpleNamespace(address='192.0.2.1')
    deploys=[dict(id=state['deployment'],createdAt='2026-11-04T11:47:52Z',commit={'id':e['revision']})]
    pilot.preflight=lambda:(service,service_guard(service),[],deploys,env)
    pilot.preview_release_capacity=lambda *a:{'synthetic_io_fixture':True}
    pilot.intent=lambda *a:pytest.fail('INTENT_REACHED')
    return pilot,state,deploys,env

def test_exact_binding_passes_actual_run_validators_and_readonly_check(pilot):
    obj,state,_,_=pilot;before=copy.deepcopy(state)
    b,policy=obj.release_preflight()
    assert op.validate_binding(b,opening=True)==b and p.validate_policy(b,policy)==policy
    result=obj.verify_release_binding()
    assert result['status']=='RELEASE_BINDING_VERIFIED_READ_ONLY' and result['period']==p.PERIOD
    assert result['execution_binding']['revision']=='938f3f18d8b75c6467290461139b03bf9b95a338'
    assert result['max_runs']==1 and result['journal_unchanged'] and result['provider_mutations']==0
    assert not any(result[k] for k in ('release_intent_present','access_opened','job_created','deadline_frozen'))
    assert state==before and 'SYNTHETIC_SECRET_SENTINEL' not in json.dumps(result)

def test_run_consumes_same_validated_boundary_before_intent(pilot):
    obj,state,_,_=pilot;seen=[]
    class AtIntent(Exception):pass
    def intent(name):seen.append(name);raise AtIntent()
    obj.intent=intent
    obj.arm_cleanup_reserve=lambda:seen.append('RESERVE')
    with pytest.raises(AtIntent):obj.run(time.time())
    assert seen==['RESERVE','RELEASE'] and state['status']=='ARTIFACT_READY' and state['intents']=={}

@pytest.mark.parametrize('period',['b-dbpilot-20261027-1102-01','b-dbpilot-20261027-1102-02','b-dbpilot-20261027-1102-03','b-dbpilot-20261027-1102-04'])
def test_consumed_or_historical_journals_never_reopen(pilot,period):
    obj,state,_,_=pilot;state.update(period=period,status='CLOSED',intents={'RELEASE':{'state':'ACKNOWLEDGED'}})
    with pytest.raises(op.Denied,match='OWNER_PRIOR_ATTEMPT_RECONCILE'):obj.verify_release_binding()

def test_release_intent_even_with_ready_status_refuses(pilot):
    obj,state,_,_=pilot;state['intents']['RELEASE']={'state':'INTENT_NO_RETRY'}
    with pytest.raises(op.Denied,match='OWNER_PRIOR_ATTEMPT_RECONCILE'):obj.release_preflight()

@pytest.mark.parametrize('drift',['deployment','revision','profile','startup','environment'])
def test_artifact_and_state_drift_refuse_before_intent(pilot,drift):
    obj,state,deploys,env=pilot
    if drift=='deployment':deploys[0]['id']='dep-'+'z'*20
    elif drift=='revision':deploys[0]['commit']['id']='f'*40
    elif drift=='profile':state['profile']['aggregate_bytes']=2147483647
    elif drift=='startup':state['startup_preflight']['receipt']['tree']='f'*40
    else:state['original_environment']=dict(env,PLAYWRIGHT_BROWSERS_PATH='different')
    with pytest.raises(op.Denied):obj.verify_release_binding()

def test_scope_and_policy_still_refuse_wrong_window_attempt_and_limits(pilot):
    obj,_,_,_=pilot;b,policy=obj.release_preflight()
    for change in ({'period':'b-dbpilot-20261027-1102-06'},{'fixed_window':{'start':'2026-10-28','end':'2026-11-03'}}):
        bad=dict(b,**change)
        with pytest.raises(op.Denied,match='OWNER_DATABASE_PILOT_SCOPE'):op.validate_binding(bad)
    bad=copy.deepcopy(policy);bad['max_runs']=2
    with pytest.raises(op.Denied):p.validate_policy(b,bad)

def test_changed_journal_during_check_refuses(pilot):
    obj,_,_,_=pilot;load=obj.journal.load;calls=[]
    def changed():
        calls.append(True)
        if len(calls)>1:obj.journal.previous='d'*64
        return load()
    obj.journal.load=changed
    with pytest.raises(op.Denied,match='OWNER_PRIOR_ATTEMPT_RECONCILE'):obj.verify_release_binding()

def test_deployed_command_routes_only_to_readonly_check(monkeypatch,capsys):
    from scripts import owner_managed_pilot as cli
    monkeypatch.setenv('PROPERTYAIGENT_OWNER_PILOT_AUTHORITY',p.PERIOD)
    monkeypatch.setattr(sys,'argv',['pilot','--action','verify-binding'])
    monkeypatch.setattr(cli,'Pilot',lambda:SimpleNamespace(verify_release_binding=lambda:{'status':'RELEASE_BINDING_VERIFIED_READ_ONLY'}))
    assert cli.main()==0 and 'RELEASE_BINDING_VERIFIED_READ_ONLY' in capsys.readouterr().out

def test_actual_parent_launcher_binding_check_is_fixed_and_bounded(monkeypatch):
    from app import owner_intake_control as control
    monkeypatch.setattr(control,'_process',None);calls=[]
    monkeypatch.setenv('PROPERTYAIGENT_INTAKE_PREPARE_ONCE','VERIFY_BINDING:'+p.PERIOD)
    monkeypatch.setattr(control.subprocess,'Popen',lambda cmd,**kw:calls.append((cmd,kw)) or SimpleNamespace(poll=lambda:None))
    control.startup_prepare()
    command,kw=calls[0]
    assert command[3]=='60s' and command[-2:]==['--action','verify-binding']
    assert '--owner-checked-at' not in command and kw['env']['PROPERTYAIGENT_OWNER_PILOT_AUTHORITY']==p.PERIOD
    assert kw['stdin']==control.subprocess.DEVNULL and kw['stderr']==control.subprocess.DEVNULL
