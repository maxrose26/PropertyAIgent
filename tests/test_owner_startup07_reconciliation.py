import copy,json
from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from verification.ingestion_storage import owner_startup07_reconciliation as r, owner_pilot as p


def fixture(monkeypatch):
    monkeypatch.setenv('PROPERTYAIGENT_INTAKE_SOURCE_RELEASE',json.dumps({'tree':r.TREE,'execution_binding':r.RECEIPT['execution_binding']}))
    job={'id':r.JOB,'status':'succeeded','finishedAt':'2026-11-05T12:04:00Z','createdAt':'2026-11-05T12:03:00Z','serviceId':p.SERVICE,'startCommand':'fixed-startup'}
    failure={'exception_class':'ReadTimeout','phase':'STARTUP_PREFLIGHT_JOB','reason':'UNKNOWN_FAILURE','sqlstate':None,'status':'RECONCILIATION_REQUIRED'}
    s={'period':r.PERIOD,'deployment':r.DEPLOY,'status':'PREPARATION_REFUSED','failure':failure,'startup_job':job,'startup_job_terminal':job,'startup_command':'fixed-startup',
       'intents':{k:{'state':'ACKNOWLEDGED','at':0} for k in ('BUILD_ENVIRONMENT','BUILD_CONFIGURATION','ONE_RESUME_BUILD','RESUSPEND','RESTORE_BUILD_CONFIGURATION','RESTORE_BUILD_ENVIRONMENT','STARTUP_PREFLIGHT_JOB')}}
    observed={'current_readback':{'configuration_equal':True,'environment_equal':True,'suspended':True,'latest_deployment':r.DEPLOY,'latest_revision':r.REVISION,'jobs_since_preparation':1},
        'period_present':False,'attempt_authorities':{'count':0},'temporary_owner_absent':True,'pipeline_session_count':0,'runtime_membership_count':0,'stable_verifier_binding':'MATCH',
        'runtime_roles':[{'login':False,'password_null':False}]*2}
    class Journal:
        previous=r.JOURNAL_SHA;ordinal=21
        def load(self):return copy.deepcopy(s)
    class API:
        def call(self,method,path):
            assert method=='GET'
            return [job] if path=='/jobs?limit=100' else job
    class Pilot:
        journal=Journal();writes=0
        @contextmanager
        def api(self):yield API()
        def inspect(self):return observed
        def save(self):
            s.clear();s.update(copy.deepcopy(self.state));self.writes+=1
            self.journal.ordinal+=1;self.journal.previous='a'*64
        def summary(self):return copy.deepcopy(self.state)
    return Pilot(),s,observed


def test_reconcile_and_lost_ack_readback(monkeypatch):
    pilot,s,_=fixture(monkeypatch);cfg={'version':'ATTEMPT07_STARTUP_RECEIPT_V1','receipt':r.RECEIPT}
    result=r.reconcile(pilot,cfg)
    assert result['status']=='ARTIFACT_READY' and result['preparation_failure']==result['failure']
    assert pilot.writes==2 and result['startup_preflight']['receipt']['source_requests']==0
    r.reconcile(pilot,cfg)  # lost acknowledgement: identical receipt is read-only
    assert pilot.writes==2


@pytest.mark.parametrize('drift',['receipt','journal','job','period','permission','environment'])
def test_changed_state_refused_without_write(monkeypatch,drift):
    pilot,s,observed=fixture(monkeypatch)
    receipt=copy.deepcopy(r.RECEIPT)
    if drift=='receipt':receipt['authentication_attempts']=1
    if drift=='journal':pilot.journal.previous='b'*64
    if drift=='job':s['startup_job_terminal']['status']='failed'
    if drift=='period':observed['period_present']=True
    if drift=='permission':observed['temporary_owner_absent']=False
    if drift=='environment':observed['current_readback']['environment_equal']=False
    with pytest.raises(p.op.Denied):r.reconcile(pilot,{'version':'ATTEMPT07_STARTUP_RECEIPT_V1','receipt':receipt})
    assert pilot.writes==0
