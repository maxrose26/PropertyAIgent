"""Reserve enforcement and connected failure recovery; no real external effects."""
import copy,hashlib,json,time
from types import SimpleNamespace
import pytest
from tests.test_attempt04_cleanup_capacity import MemoryDB,pilot_with_retained_state
from tests.test_attempt04_release_binding import pilot
from verification.ingestion_storage import owner_pilot as p

def test_exact_crypto_arithmetic_and_supported_maxima():
    db=MemoryDB();journal=p.Journal(db);policy=p.cleanup_reserve_policy()
    for n in (0,15,16,511,16534,24480):
        value='x'*n;assert len(journal._vault(value=value))==p.ciphertext_size(len(p.canonical(value)))
    assert policy['growth_bytes']==6937 and policy['margin_bytes']==1024 and policy['reserved_snapshots']==16
    assert p.ciphertext_size(policy['normal_plaintext_ceiling']+6937+1024)<=32768
    assert p.ciphertext_size(policy['normal_plaintext_ceiling']+1+6937+1024)>32768

def test_near_normal_limit_and_direct_callback_cannot_consume_reserve():
    s={'period':p.PERIOD,'status':'ARTIFACT_READY','intents':{},'cleanup_reserve':dict(p.cleanup_reserve_policy(),cleanup_writes=0)}
    obj=pilot_with_retained_state(s);cap=p.cleanup_reserve_policy()['normal_plaintext_ceiling']
    candidate=copy.deepcopy(s);candidate['padding']='';candidate['padding']='x'*(cap-len(p.canonical(candidate)))
    obj.journal.save(candidate);old=obj.db.rows[-1]
    assert len(p.canonical(candidate))==cap
    candidate['padding']+='x'
    with pytest.raises(p.op.Denied,match='RESERVE_BYTE_BOUND'):obj.journal.save(candidate,connection=obj.db)
    assert obj.db.rows[-1]==old
    obj.state=candidate
    obj.record_first_failure(p.op.Denied('OWNER_CLEANUP_RESERVE_BYTE_BOUND'))
    saved=obj.journal.load();assert saved['first_failure']['reason']=='OWNER_CLEANUP_RESERVE_BYTE_BOUND'
    assert len(obj.db.rows[-1][1])<=32768
    changed=copy.deepcopy(saved);changed['first_failure']['reason']='UNKNOWN_FAILURE'
    with obj.cleanup_writes(),pytest.raises(p.op.Denied,match='FIRST_FAILURE_IMMUTABLE'):obj.journal.save(changed)
    with pytest.raises(p.op.Denied,match='NO_NORMAL_AFTER_CLEANUP'):obj.journal.save(saved)

def test_insufficient_byte_or_row_capacity_precedes_opening_and_release(pilot,monkeypatch):
    obj,s,_,_=pilot
    for mode in ('bytes','rows'):
        state=copy.deepcopy(s)
        if mode=='bytes':state['padding']='x'*18000
        clone=pilot_with_retained_state(state);clone.db.address='192.0.2.1'
        if mode=='rows':clone.db.rows=[(47,clone.db.rows[0][1],clone.db.rows[0][2])];clone.journal.load()
        clone.release_preflight=lambda:(setattr(clone,'state',clone.journal.load()) or {'release_root':'/tmp/not-created'}, {})
        clone.intent=lambda *x:pytest.fail('RELEASE_INTENT')
        monkeypatch.setattr(p.op,'activate',lambda *x,**kw:pytest.fail('ACCESS_OPENED'))
        with pytest.raises(p.op.Denied,match='CLEANUP_'):clone.run(time.time())
        assert len(clone.db.rows)==1

@pytest.mark.parametrize('lost_put_ack',[False,True])
def test_near_limit_failure_after_real_handoff_recovers_and_preserves_first(pilot,monkeypatch,tmp_path,lost_put_ack):
    obj,s,deploys,original=pilot
    original.update(PYTHONUNBUFFERED='1',PLANNING_STATUS_VERIFICATION_ENABLED='SYNTHETIC_SETTING')
    obj.state=obj.journal.load();b,policy=obj.release_preflight()
    b.update(release_root=str(tmp_path/'release'),submission_intent_path=str(tmp_path/'release/intent'))
    state=copy.deepcopy(s);state['retained_audit']='x'*2500
    state['stable_credentials']['passwords']={r:'s'*64 for r in p.op.ROLES}
    clone=pilot_with_retained_state(state);clone.db.address='192.0.2.1'
    raw=clone.db.rows[0][1];clone.db.rows=[(22,raw,hashlib.sha256(raw).hexdigest())];clone.journal.load()
    clone.release_preflight=lambda:(setattr(clone,'state',clone.journal.load()) or copy.deepcopy(b),copy.deepcopy(policy))
    flags={'logins':False,'memberships':0};events=[];puts=[];actual=copy.deepcopy(original)
    def issue(c,b,policy,journal,save):
        journal['state']='COMMIT_ACKNOWLEDGED';save(journal);return {'outcome':'COMMIT_ACKNOWLEDGED'}
    def prepare(c,b,**kw):
        return dict(version='FINITE_INTAKE_ACCESS_STATE_V1',binding=copy.deepcopy(b),state='ARMED_BEFORE_ACTIVATION',prior_settings={},original_memberships=[],passwords={r:'s'*64 for r in p.op.ROLES})
    def activate(c,b,save,prepared):
        assert clone.journal.load()['cleanup_reserve']['cleanup_writes']==0
        events.append('OPEN');flags.update(logins=True,memberships=2)
        prepared['state']='ACTIVATION_ACKNOWLEDGED';save(prepared);return {'outcome':'COMMIT_ACKNOWLEDGED'}
    def close(c,access,save):
        flags['logins']=False;access['state']='ACCESS_DISABLED_ACKNOWLEDGED';save(access)
        flags['memberships']=0;access['membership_closure']='ACKNOWLEDGED';save(access)
        access.update(state='DATABASE_CLOSURE_ACKNOWLEDGED',passwords={});save(access)
        return dict(outcome='COMMIT_ACKNOWLEDGED',runtime_access='DISABLED',authorities=[],authority_expiry=0,sessions='ABSENT',temporary_owner='REMOVED')
    monkeypatch.setattr(p,'issue_period',issue);monkeypatch.setattr(p.op,'prepare_activation',prepare)
    monkeypatch.setattr(p.op,'activate',activate);monkeypatch.setattr(p.op,'close',close)
    service,_,_,_,_=obj.preflight()
    class API:
        calls=0
        def call(self,method,suffix='',body=None):
            nonlocal actual
            self.calls+=1;assert self.calls<=8
            if method=='PUT':
                acknowledged=clone.journal.load();assert acknowledged['access']['render']['state'] in ('PUT_INTENT_NO_RETRY','RESTORE_INTENT_NO_RETRY')
                actual={x['key']:x['value'] for x in body};puts.append(acknowledged['access']['render']['state'])
                if lost_put_ack and len(puts)==2:
                    from requests.exceptions import ReadTimeout
                    raise ReadTimeout('SENSITIVE_SECRET_SENTINEL')
                return []
            assert method=='GET'
            if suffix=='':return service
            if suffix=='/env-vars?limit=100':return [{'envVar':{'key':k,'value':v}} for k,v in actual.items()]
            if suffix=='/jobs?limit=100':return []
            pytest.fail('JOB_OR_EXTRA_REQUEST')
        def close(self):pass
    clone.render_factory=API
    def observe(operation,seen):
        if operation=='SUBMISSION':
            assert clone.journal.load()['intents']['HANDOFF']['state']=='ACKNOWLEDGED'
            events.append('INJECTED_AFTER_HANDOFF')
            raise p.op.Denied('OWNER_CONFIGURATION_DRIFT')
        return dict(version='FINITE_OPERATION_OBSERVATION_V1',operation=operation,binding_sha256=hashlib.sha256(p.canonical(clone.state['binding'])).hexdigest(),service_id=p.SERVICE,observed_at=time.time(),env_groups=[],secret_files=[],inherited_credential_names=[],reviewed=True,no_current_work=True,other_activity_stopped=True,deployment_id=b['retained_deployment'],revision=b['execution_binding']['revision'],suspended=True)
    clone.observation=observe
    def inspect():
        clone.state=clone.journal.load()
        return dict(stable_verifier_binding='MATCH',runtime_membership_count=flags['memberships'],pipeline_session_count=0,temporary_owner_absent=True,runtime_roles=[{'login':flags['logins']}],attempt_authorities={'all_expiry_zero':True},current_readback=dict(suspended=True,configuration_equal=True,environment_equal=actual==original))
    clone.inspect=inspect
    old=clone.db.rows[0]
    result=clone.run(time.time())
    if lost_put_ack:
        assert result['status']=='CONTAINMENT_REQUIRES_REVIEW'
        first=copy.deepcopy(clone.journal.load()['first_failure'])
        clone.record_first_failure(RuntimeError('SENSITIVE_SECRET_SENTINEL'))
        assert clone.journal.load()['first_failure']==first
        result=clone.recover()
    saved=clone.journal.load()
    assert events==['OPEN','INJECTED_AFTER_HANDOFF'] and not flags['logins'] and flags['memberships']==0
    assert result['status']=='CLOSED' and actual==original and len(puts)==2
    assert saved['first_failure']['reason']=='OWNER_CONFIGURATION_DRIFT' and 'ONE_JOB' not in saved['intents']
    assert saved['closure_verification']['status']=='VERIFIED' and clone.db.rows[0]==old
    assert all(len(r[1])<=32768 for r in clone.db.rows) and saved['cleanup_reserve']['cleanup_writes']<=16
    assert 'SENSITIVE_SECRET_SENTINEL' not in json.dumps(saved['first_failure'])
    normal=[len(r[1]) for r in clone.db.rows if p.Journal(clone.db)._vault(raw=r[1]).get('cleanup_reserve',{}).get('cleanup_writes',0)==0]
    print(json.dumps(dict(normal_max_ciphertext=max(normal),final_ciphertext=len(clone.db.rows[-1][1]),cleanup_writes=saved['cleanup_reserve']['cleanup_writes'],lost_ack=lost_put_ack)))

def test_maximum_cleanup_records_fit_with_explicit_margin():
    policy=p.cleanup_reserve_policy()
    state={'period':p.PERIOD,'intents':{},'access':{},'cleanup_reserve':dict(policy,cleanup_writes=0)}
    state['padding']='';state['padding']='x'*(policy['normal_plaintext_ceiling']-len(p.canonical(state)))
    obj=pilot_with_retained_state(state);obj.state=obj.journal.load()
    for k,n in p.CLEANUP_RECORD_LIMITS.items():
        value={'padding':''};value['padding']='x'*(n-len(p.canonical(value)))
        obj.state[k]=value
    with obj.cleanup_writes():obj.save()
    assert len(obj.db.rows[-1][1])+p.CLEANUP_MARGIN<32768
    for _ in range(15):
        with obj.cleanup_writes():obj.save()
    count=len(obj.db.rows)
    with obj.cleanup_writes(),pytest.raises(p.op.Denied,match='CLEANUP_ROW_BOUND'):obj.save()
    assert len(obj.db.rows)==count

def test_secret_exception_and_unknown_class_are_suppressed(capsys):
    state={'period':p.PERIOD,'status':'RELEASE_BOUND','intents':{},'cleanup_reserve':dict(p.cleanup_reserve_policy(),cleanup_writes=0)}
    obj=pilot_with_retained_state(state)
    exc=type('SECRET_SENTINEL',(Exception,),{})('SECRET_SENTINEL')
    obj.record_first_failure(exc)
    first=obj.journal.load()['first_failure'];output=capsys.readouterr().out
    assert first['reason']=='UNKNOWN_FAILURE' and first['exception_class']=='UNKNOWN_CLASS'
    assert 'SECRET_SENTINEL' not in output and len(output.encode())<600 and len(p.canonical(first))<=512

def test_cleanup_first_failure_is_not_replaced_by_later_cleanup_errors():
    state={'period':p.PERIOD,'status':'RELEASE_BOUND','intents':{},'cleanup_reserve':dict(p.cleanup_reserve_policy(),cleanup_writes=0)}
    obj=pilot_with_retained_state(state)
    obj.record_cleanup_failure(p.op.Denied('STABLE_VERIFIER_BINDING'),'closure_failure')
    first=copy.deepcopy(obj.journal.load()['first_failure'])
    obj.record_cleanup_failure(RuntimeError('SENSITIVE_SECRET_SENTINEL'),'restoration_failure')
    saved=obj.journal.load()
    assert saved['first_failure']==first and saved['restoration_failure']['reason']=='UNKNOWN_FAILURE'
    assert first['phase']=='CLEANUP' and 'SENSITIVE_SECRET_SENTINEL' not in json.dumps(saved)

def test_pre_intent_reservation_reentry_is_read_only_and_closed_attempt_stays_closed():
    state={'period':p.PERIOD,'status':'ARTIFACT_READY','intents':{}}
    obj=pilot_with_retained_state(state);obj.arm_cleanup_reserve();rows=len(obj.db.rows)
    obj.state=obj.journal.load();obj.arm_cleanup_reserve();assert len(obj.db.rows)==rows
    obj.state['status']='CLOSED'
    with pytest.raises(p.op.Denied,match='PRIOR_ATTEMPT'):obj.arm_cleanup_reserve()

def test_oversized_reserved_record_is_rejected_during_normal_activity():
    state={'period':p.PERIOD,'status':'ARTIFACT_READY','intents':{},'cleanup_reserve':dict(p.cleanup_reserve_policy(),cleanup_writes=0)}
    obj=pilot_with_retained_state(state);obj.state['closure_receipt']={'padding':'x'*2048}
    with pytest.raises(p.op.Denied,match='CLEANUP_RECORD_BOUND'):obj.save()
    assert len(obj.db.rows)==1

def test_preopening_validation_uses_real_vault_without_persisting_or_advancing():
    state={'period':p.PERIOD,'status':'ARTIFACT_READY','intents':{},'cleanup_reserve':dict(p.cleanup_reserve_policy(),cleanup_writes=0)}
    obj=pilot_with_retained_state(state);previous=obj.journal.previous;ordinal=obj.journal.ordinal
    assert obj.journal.save(copy.deepcopy(state),validate_only=True)<=22152
    assert len(obj.db.rows)==1 and obj.journal.previous==previous and obj.journal.ordinal==ordinal
    state['padding']='x'*18000
    with pytest.raises(p.op.Denied,match='RESERVE_BYTE_BOUND'):obj.journal.save(state,validate_only=True)
    assert len(obj.db.rows)==1
