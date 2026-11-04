import copy,hashlib,json
from types import SimpleNamespace
import pytest
from verification.ingestion_storage import owner_pilot as p
from verification.ingestion_storage.intake_owner_io import Vault,VAULT_LIMIT

def state():
    original={'DATABASE_URL':'SECRET_SENTINEL','PLAYWRIGHT_BROWSERS_PATH':'0'}
    return dict(status='RELEASE_BOUND',binding={'render_config_sha256':'a'*64},original_guard='a'*64,
        original_environment=original,access={'state':'DATABASE_CLOSURE_ACKNOWLEDGED','render':{'guard':'a'*64,'original':copy.deepcopy(original),'expected':{'restricted':'SECRET_SENTINEL'},'state':'RESTORE_INTENT_NO_RETRY'}},
        stable_credentials={'passwords':{'worker':'SECRET_SENTINEL'}},
        job={'id':'job-'+'a'*20},job_terminal={'status':'failed'},
        original_service={'buildCommand':'synthetic finished-build metadata'+'x'*17000},
        original_deploy_ids=['dep-'+'a'*20],build_guard='b'*64,build_environment={'harmless':'0'},build_receipt_created_at='2026-11-03T23:11:57Z',
        intents={name:{'state':'ACKNOWLEDGED'} for name in ('RESUSPEND','RESTORE_BUILD_CONFIGURATION','RESTORE_BUILD_ENVIRONMENT','ONE_JOB')})

def test_existing_vault_bound_restored_without_dropping_closure_material(tmp_path):
    pilot=object.__new__(p.Pilot);pilot.state=state();before=copy.deepcopy(pilot.state)
    vault=Vault(tmp_path/'state','s'*64,create=True);vault.save(before);prior_bytes=(tmp_path/'state').read_bytes()
    pilot.state['private_failure_detail']={'synthetic_padding':'y'*8000}
    with pytest.raises(p.op.Denied,match='VAULT_32K_BOUND'):vault.save(pilot.state)
    assert (tmp_path/'state').read_bytes()==prior_bytes
    pilot.journal=SimpleNamespace(previous=hashlib.sha256(prior_bytes).hexdigest(),ordinal=40)
    writes=[]
    def save():vault.save(pilot.state);writes.append(copy.deepcopy(pilot.state))
    pilot.save=save;pilot.reserve_closure_space()
    assert len(writes)==1 and len((tmp_path/'state').read_bytes())<=VAULT_LIMIT==32768
    value=vault.load()
    for name in ('binding','original_guard','original_environment','access','stable_credentials','job','job_terminal','intents'):
        assert value[name]==before[name]
    assert value['access']['render']['state']=='RESTORE_INTENT_NO_RETRY'
    assert value['closed_build_archive']['prior_ciphertext_sha256']==hashlib.sha256(prior_bytes).hexdigest()
    assert value['closed_build_archive']['fields']['original_service']==hashlib.sha256(p.canonical(before['original_service'])).hexdigest()
    assert b'SECRET_SENTINEL' not in (tmp_path/'state').read_bytes()
    pilot.reserve_closure_space();assert len(writes)==1

@pytest.mark.parametrize('drift',['guard','baseline','ack','capacity'])
def test_archive_refuses_drift_or_missing_capacity_before_save(drift):
    pilot=object.__new__(p.Pilot);pilot.state=state();pilot.journal=SimpleNamespace(previous='b'*64,ordinal=40)
    pilot.save=lambda:pytest.fail('UNSAFE_SAVE')
    if drift=='guard':pilot.state['access']['render']['guard']='c'*64
    if drift=='baseline':pilot.state['access']['render']['original']={}
    if drift=='ack':pilot.state['intents']['RESUSPEND']['state']='UNKNOWN'
    if drift=='capacity':pilot.journal.ordinal=60
    with pytest.raises(p.op.Denied):pilot.reserve_closure_space()

def test_completed_recovery_does_not_repeat_any_effect():
    pilot=object.__new__(p.Pilot);pilot.journal=SimpleNamespace(load=lambda:{'status':'CLOSED'})
    pilot.cleanup=lambda:pytest.fail('REPEATED_CLOSURE')
    pilot.summary=lambda:{'status':pilot.state['status']}
    assert pilot.recover()=={'status':'CLOSED'}

@pytest.mark.parametrize('mode',['normal','prior_intent_original','prior_intent_expected','drift','lost_ack'])
def test_actual_cleanup_path_restores_once_or_only_reconciles(mode):
    from requests.exceptions import ReadTimeout
    from verification.ingestion_storage.intake_owner_io import service_guard
    s=state();service={'id':p.SERVICE,'type':'cron_job','suspended':'suspended','autoDeploy':'no','branch':'master','serviceDetails':{'schedule':'0 5 * * *','envSpecificDetails':{'buildCommand':'original','startCommand':'/bin/true'}}}
    guard=service_guard(service);s['original_guard']=guard;s['binding']['render_config_sha256']=guard;s['access']['render']['guard']=guard
    s['job']['serviceId']=p.SERVICE;s['access']['binding']=copy.deepcopy(s['binding'])
    r=s['access']['render'];r['state']='RESTORE_INTENT_NO_RETRY' if mode.startswith('prior_intent') else 'PUT_ACKNOWLEDGED'
    if mode.startswith('prior_intent'):r['reconciliation']='EXPECTED'
    actual=copy.deepcopy(r['original'] if mode=='prior_intent_original' else {'drift':'unrelated'} if mode=='drift' else r['expected'])
    events=[];puts=[];snapshots=[]
    class API:
        def __init__(self):self.calls=0
        def call(self,method,suffix='',body=None):
            nonlocal actual
            self.calls+=1;assert self.calls<=8
            if method=='PUT':
                assert snapshots[-1]['access']['render']['state']=='RESTORE_INTENT_NO_RETRY'
                puts.append(True);events.append('PUT');actual={x['key']:x['value'] for x in body}
                if mode=='lost_ack' and len(puts)==1:raise ReadTimeout('SECRET_SENTINEL')
                return []
            assert method=='GET'
            if suffix=='':return service
            if suffix=='/env-vars?limit=100':return [{'envVar':{'key':k,'value':v}} for k,v in actual.items()]
            assert suffix=='/jobs/'+s['job']['id']
            return dict(id=s['job']['id'],status='failed',finishedAt='2026-11-04T00:02:57Z')
        def close(self):pass
    pilot=object.__new__(p.Pilot);pilot.state=s;pilot.render_factory=API
    pilot.save=lambda:snapshots.append(copy.deepcopy(pilot.state))
    if mode=='prior_intent_expected':
        with pytest.raises(p.op.Denied,match='OWNER_RESTORE_UNCERTAIN_NO_RETRY'):pilot.cleanup()
        assert puts==[];return
    pilot.cleanup()
    if mode=='lost_ack':
        assert s['status']=='CONTAINMENT_REQUIRES_REVIEW' and len(puts)==1
        pilot.cleanup()
        assert s['status']=='CLOSED' and len(puts)==1
    elif mode=='drift':assert s['status']=='CONTAINMENT_REQUIRES_REVIEW' and puts==[]
    else:
        assert s['status']=='CLOSED' and actual==r['original']
        assert len(puts)==(1 if mode=='normal' else 0)
    assert 'SECRET_SENTINEL' not in json.dumps(pilot.summary())
