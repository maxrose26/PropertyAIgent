"""Actual encrypted diagnostic path; synthetic database/provider effects."""
import copy,hashlib,time
from contextlib import contextmanager
import pytest
from verification.ingestion_storage import owner_pilot as p,owner_qualification as q
from tests.test_attempt04_release_binding import pilot
from tests.test_attempt04_cleanup_capacity import MemoryDB

@pytest.mark.parametrize('matches',[False,True])
def test_actual_diagnostic_sequence_has_one_job_no_period_and_independent_close(pilot,monkeypatch,tmp_path,matches):
    base,state,_,original=pilot;b,_=base.release_preflight();service,*_=base.preflight()
    monkeypatch.setattr(p,'PERIOD',q.IDENTITY);monkeypatch.setattr(p,'PREDECESSOR',q.CONTEXT)
    s=copy.deepcopy(state);s['period']=q.IDENTITY;s['stable_credentials']['passwords']={r:'s'*64 for r in p.op.ROLES}
    b.update(release_root=str(tmp_path/'diagnostic'),submission_intent_path=str(tmp_path/'diagnostic/intent'))
    obj=object.__new__(q.Qualification);obj.db=MemoryDB();obj.journal=p.Journal(obj.db,q.IDENTITY)
    raw=obj.journal._vault(value=s);obj.db.rows=[(18,raw,hashlib.sha256(raw).hexdigest())];obj.state=obj.journal.load()
    obj.preflight=lambda:None;obj.binding=lambda:copy.deepcopy(b);obj.sleep=lambda _:None
    flags={'login':False,'memberships':0};actual=copy.deepcopy(original);jobs=[];puts=[]
    monkeypatch.setattr(p,'issue_period',lambda *a,**k:pytest.fail('COLLECTION_PERIOD_ISSUED'))
    monkeypatch.setattr(p.op,'prepare_activation',lambda c,b,**kw:dict(version='FINITE_INTAKE_ACCESS_STATE_V1',binding=copy.deepcopy(b),state='ARMED_BEFORE_ACTIVATION',prior_settings={},original_memberships=[],passwords=kw['stable_credentials']))
    def activate(c,b,save,prepared,deadline_observations):
        from verification.ingestion_storage.deadline_evidence import deadline_evidence
        deadline_observations.update({r:deadline_evidence(b['valid_until'],b['valid_until'],None) for r in p.op.ROLES})
        flags.update(login=True,memberships=2);prepared['state']='ACTIVATION_ACKNOWLEDGED';save(prepared);return {'outcome':'COMMIT_ACKNOWLEDGED'}
    def close(c,access,save):
        flags['login']=False;access['state']='ACCESS_DISABLED_ACKNOWLEDGED';save(access)
        flags['memberships']=0;access['membership_closure']='ACKNOWLEDGED';save(access)
        access.update(state='DATABASE_CLOSURE_ACKNOWLEDGED',passwords={});save(access)
        return dict(outcome='COMMIT_ACKNOWLEDGED',runtime_access='DISABLED',temporary_owner='REMOVED',sessions='ABSENT')
    monkeypatch.setattr(p.op,'activate',activate);monkeypatch.setattr(p.op,'close',close)
    def observation(operation,seen):
        value=dict(version='FINITE_OPERATION_OBSERVATION_V1',operation=operation,binding_sha256=hashlib.sha256(p.canonical(obj.state['binding'])).hexdigest(),service_id=p.SERVICE,observed_at=time.time(),env_groups=[],secret_files=[],inherited_credential_names=[],reviewed=True,no_current_work=True,other_activity_stopped=True,deployment_id=b['retained_deployment'],revision=b['execution_binding']['revision'],suspended=True)
        obj.state.setdefault('observations',{})[operation]={'provider_observation':value,'owner_boundary_confirmed_at':seen};obj.save();return value
    obj.observation=observation
    job=dict(id='job-'+'a'*20,serviceId=p.SERVICE,status='succeeded' if matches else 'failed',createdAt='2026-11-04T15:00:00Z',finishedAt='2026-11-04T15:00:01Z')
    class API:
        def __init__(self):self.calls=0
        def close(self):pass
        def call(self,method,suffix='',body=None):
            nonlocal actual
            self.calls+=1;assert self.calls<=8
            if method=='POST':
                assert suffix=='/jobs' and '--qualification-only' in body['startCommand'];assert not jobs
                assert obj.journal.load()['intents']['ONE_JOB']['state']=='INTENT_NO_RETRY'
                jobs.append(True);return dict(job,startCommand=body['startCommand'])
            if method=='PUT':
                puts.append(True);actual={v['key']:v['value'] for v in body};return []
            assert method=='GET'
            if suffix=='':return service
            if suffix=='/env-vars?limit=100':return [{'envVar':{'key':k,'value':v}} for k,v in actual.items()]
            if suffix=='/jobs/'+job['id']:return job
            if suffix.startswith('qualification:'):
                import json
                receipt=dict(period=q.CONTEXT,execution_binding=b['execution_binding'],deadline=b['valid_until'],source_requests=0,status='VERIFIED_BOTH_RESTRICTED_ROLES' if matches else 'REFUSED',first_qualification_failure=None if matches else {'comparison':{'first_mismatch':'evidence_write_execute'}})
                return dict(hasMore=False,logs=[{'message':'DATABASE_PILOT_RUNTIME_QUALIFICATION '+json.dumps(receipt)}])
            pytest.fail(suffix)
    obj.render_factory=API
    obj.inspect=lambda:dict(stable_verifier_binding='MATCH',runtime_membership_count=flags['memberships'],pipeline_session_count=0,temporary_owner_absent=True,runtime_roles=[{'login':flags['login']}],attempt_authorities={'all_expiry_zero':True},current_readback=dict(suspended=True,configuration_equal=True,environment_equal=actual==original))
    result=obj.run(time.time());saved=obj.journal.load()
    assert jobs==[True] and len(puts)==2 and actual==original and not flags['login'] and flags['memberships']==0
    assert len(saved['owner_deadline_observations'])==2
    print('DIAGNOSTIC_CAPACITY',max(len(r[1]) for r in obj.db.rows),obj.journal.ordinal,saved['cleanup_reserve']['cleanup_writes'])
    assert result['status']=='CLOSED' and result['closure_verification']['status']=='VERIFIED'
    assert result['collection_period_issued'] is False and saved['runtime_qualification']['source_requests']==0
    assert saved['cleanup_reserve']['cleanup_writes']<=16 and all(len(r[1])<=32768 for r in obj.db.rows)
    if not matches:assert saved['runtime_qualification']['first_qualification_failure']['comparison']['first_mismatch']=='evidence_write_execute'
    with pytest.raises(p.op.Denied,match='PRIOR_INTENT'):obj.run(time.time())
    assert jobs==[True]


def test_stale_isolation_refuses_before_journal_or_provider():
    obj=object.__new__(q.Qualification)
    with pytest.raises(p.op.Denied,match='INHERITED'):obj.run(time.time()-301)


def test_uncertain_submission_reconciles_get_only_without_another_post(monkeypatch):
    monkeypatch.setattr(p,'PERIOD',q.IDENTITY);monkeypatch.setattr(p,'PREDECESSOR',q.CONTEXT)
    obj=object.__new__(q.Qualification);obj.db=MemoryDB();obj.journal=p.Journal(obj.db,q.IDENTITY)
    state={'period':q.IDENTITY,'status':'CONTAINMENT_REQUIRES_REVIEW','intents':{'ONE_JOB':{'at':1793800000.0,'state':'INTENT_NO_RETRY'}},'job_command':'fixed --qualification-only','cleanup_reserve':dict(p.cleanup_reserve_policy(),cleanup_writes=0)}
    raw=obj.journal._vault(value=state);obj.db.rows=[(25,raw,hashlib.sha256(raw).hexdigest())]
    calls=[]
    class API:
        def close(self):pass
        def call(self,method,suffix):
            calls.append((method,suffix));assert method=='GET'
            return [{'id':'job-'+'a'*20,'serviceId':p.SERVICE,'status':'failed','createdAt':'2026-11-04T16:00:00Z','finishedAt':'2026-11-04T16:00:01Z','startCommand':'fixed --qualification-only'}]
    obj.render_factory=API;obj.reconcile_submission();obj.reconcile_submission()
    assert calls==[('GET','/jobs?limit=100')]
    assert obj.journal.load()['job_terminal']['status']=='failed'


def test_protected_dispatch_rejects_stale_time_before_child(monkeypatch):
    from app import owner_intake_control as control
    monkeypatch.setenv('PROPERTYAIGENT_INTAKE_PREPARE_ONCE','QUALIFICATION-RUN:'+q.IDENTITY)
    monkeypatch.setenv('PROPERTYAIGENT_QUALIFICATION_CHECKED_AT',str(time.time()-301))
    monkeypatch.setattr(control.subprocess,'Popen',lambda *a,**kw:pytest.fail('CHILD_STARTED'))
    with pytest.raises(ValueError,match='EXPIRED'):control.start('qualification-run',server_prepare=True)

def test_deadline_capacity_refuses_before_access_and_preserves_journal(pilot,monkeypatch):
    base,state,_,_=pilot;b,_=base.release_preflight()
    monkeypatch.setattr(p,'PERIOD',q.IDENTITY);monkeypatch.setattr(p,'PREDECESSOR',q.PREDECESSOR)
    obj=object.__new__(q.Qualification);obj.db=MemoryDB();obj.journal=p.Journal(obj.db,q.IDENTITY)
    s=copy.deepcopy(state);s['period']=q.IDENTITY;s['stable_credentials']['passwords']={r:'s'*64 for r in p.op.ROLES}
    raw=obj.journal._vault(value=s);obj.db.rows=[(47,raw,hashlib.sha256(raw).hexdigest())];obj.state=obj.journal.load()
    before=copy.deepcopy(obj.db.rows)
    with pytest.raises(p.op.Denied,match='OWNER_CLEANUP_ROW_BOUND'):obj.verify_deadline_capacity(b)
    assert obj.db.rows==before
