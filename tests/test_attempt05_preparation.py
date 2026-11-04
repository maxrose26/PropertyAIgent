import copy,json
from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from verification.ingestion_storage import owner_pilot as p,owner_pilot_continuation as step
from tests.test_owner_pilot_continuation import closed,SNAPSHOT

def test_successor_copies_only_stable_credentials_and_small_predecessor_reference(monkeypatch,capsys):
    old=closed();old['stable_configuration']={'outcome':'COMMIT_ACKNOWLEDGED'};old['large_closed_state']='x'*20000
    before=copy.deepcopy(old);events=[]
    @contextmanager
    def connection():yield object()
    pilot=object.__new__(p.Pilot);pilot.db=SimpleNamespace(connection=connection)
    pilot.journal=SimpleNamespace(load=lambda:None,ordinal=1,ciphertext_bytes=1600,previous='b'*64)
    monkeypatch.setattr(p,'Journal',lambda *a:SimpleNamespace(load=lambda:old,ordinal=SNAPSHOT['ordinal'],ciphertext_bytes=SNAPSHOT['bytes'],previous=SNAPSHOT['sha256']))
    monkeypatch.setattr(step,'migrate_owner_namespace',lambda *a,**kw:events.append('namespace'))
    pilot.save=lambda:None;pilot.build=lambda:events.append('build');pilot.startup_preflight=lambda:events.append('startup')
    pilot.verify_release_binding=lambda:events.append('readonly_binding') or {'status':'READ_ONLY'}
    pilot.prepare_continuation()
    assert events==['namespace','build','startup','readonly_binding'] and old==before
    assert 'large_closed_state' not in pilot.state and pilot.state['stable_credentials']==old['stable_credentials']
    assert pilot.state['predecessor']['snapshot']==SNAPSHOT and p.PERIOD=='b-dbpilot-20261027-1102-05'
    assert 'INITIAL_JOURNAL' in capsys.readouterr().out

@pytest.mark.parametrize('period',['b-dbpilot-20261027-1102-01','b-dbpilot-20261027-1102-02','b-dbpilot-20261027-1102-03','b-dbpilot-20261027-1102-04','b-dbpilot-20261027-1102-05'])
def test_closed_attempts_refuse_before_preflight_or_effect(period):
    obj=object.__new__(p.Pilot);obj.journal=SimpleNamespace(load=lambda:{'period':period,'status':'CLOSED','intents':{'RELEASE':{}}})
    obj.preflight=lambda:pytest.fail('CONSUMED_PREFLIGHT')
    with pytest.raises(p.op.Denied,match='PRIOR_ATTEMPT'):obj.release_preflight()

def test_period_checkpoint_keeps_exact_root_references():
    import hashlib
    value={'version':'FINITE_INTAKE_PERIOD_V1','state':'COMMIT_ACKNOWLEDGED','binding':{'fixed_window':p.WINDOW,'profile':'x'*1000},'policy':{'max_runs':1,'scope':'y'*1000}}
    result=p.period_checkpoint(value)
    assert result['binding_ref']=='binding' and result['policy_ref']=='policy'
    assert result['binding_sha256']==hashlib.sha256(p.canonical(value['binding'])).hexdigest()
    assert result['policy_sha256']==hashlib.sha256(p.canonical(value['policy'])).hexdigest()
    assert result['state']==value['state'] and 'binding' not in result and len(p.canonical(result))<400

def test_capacity_only_preparation_resume_never_rebuilds_or_reuses_release(monkeypatch):
    old=closed();existing={'period':p.PERIOD,'status':'PREPARATION_REFUSED','failure':{'reason':'OWNER_CLEANUP_RESERVE_BYTE_BOUND'},'intents':{},'private_failure_detail':{'frames':[]}}
    obj=object.__new__(p.Pilot);events=[]
    @contextmanager
    def connection():yield object()
    obj.db=SimpleNamespace(connection=connection)
    obj.journal=SimpleNamespace(load=lambda:copy.deepcopy(existing),ordinal=23,previous='b'*64)
    monkeypatch.setattr(p,'Journal',lambda *a:SimpleNamespace(load=lambda:old,ordinal=46,ciphertext_bytes=29084,previous=SNAPSHOT['sha256']))
    monkeypatch.setattr(step,'migrate_owner_namespace',lambda *a,**kw:None)
    obj.inspect=lambda:{'current_readback':dict(suspended=True,configuration_equal=True,environment_equal=True),'period_present':False,'runtime_membership_count':0,'pipeline_session_count':0,'temporary_owner_absent':True,'stable_verifier_binding':'MATCH','runtime_roles':[{'login':False}]}
    obj.construct_release_binding=lambda r:({},{});obj.preview_release_capacity=lambda *a:events.append('capacity')
    obj.verify_release_binding=lambda:events.append('shared_validator') or {'status':'VERIFIED'}
    obj.save=lambda:events.append('metadata_save')
    obj.build=lambda:pytest.fail('REBUILD');obj.startup_preflight=lambda:pytest.fail('NEW_STARTUP_JOB')
    existing['deployment']='dep-'+'a'*20
    monkeypatch.setenv('PROPERTYAIGENT_INTAKE_SOURCE_RELEASE','{}')
    obj.prepare_continuation()
    assert events==['capacity','metadata_save','shared_validator'] and existing['status']=='PREPARATION_REFUSED'
    assert obj.state['status']=='ARTIFACT_READY' and obj.state['preparation_failure']==existing['failure'] and 'RELEASE' not in obj.state['intents']

def test_access_binding_reference_roundtrips_exactly_and_refuses_tamper():
    binding={'version':'FINITE_INTAKE_OWNER_V1','fixed_window':p.WINDOW,'padding':'x'*2000}
    value={'period':p.PERIOD,'cleanup_reserve':{'version':'CLEANUP_RESERVE_V1'},'binding':binding,'access':{'binding':copy.deepcopy(binding),'passwords':{'synthetic':'s'*64}}}
    stored=p.serialized_state(value)
    assert len(p.canonical(stored))<len(p.canonical(value))-1800
    assert p.hydrated_state(copy.deepcopy(stored))==value
    stored['journal_metadata']['sha256']='0'*64
    with pytest.raises(p.op.Denied,match='OWNER_CODE_BINDING'):p.hydrated_state(stored)
    legacy={'binding':binding,'access':{'binding':binding}}
    assert p.serialized_state(legacy)==legacy and p.hydrated_state(copy.deepcopy(legacy))==legacy
