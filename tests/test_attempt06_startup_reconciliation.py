import copy,json
from contextlib import contextmanager
import pytest
from verification.ingestion_storage import owner_pilot as m
from verification.ingestion_storage import owner_startup_reconciliation as r

def setup(monkeypatch):
 receipt={'authentication_attempts':0,'cwd':'/opt/render/project/src','execution_binding':{'manifest_sha256':'6e223d11ad74799688a9c18d3b245d3d2908abc4f806dc5507eb5c5ccab2c77a','revision':r.REVISION,'workflow_sha256':'5b87c6cbef2944fa05468314fc6daefc19b785644b04e04d1ff382b0596cadea'},'git':{'exit_status':0,'tracked_changes':False},'period':r.PERIOD,'source_requests':0,'status':'CLEAN_CHECKOUT_VERIFIED_BEFORE_QUALIFICATION','tree':r.TREE,'version':'RENDER_STARTUP_GUARD_V1'}
 monkeypatch.setenv('PROPERTYAIGENT_INTAKE_SOURCE_RELEASE',json.dumps({'tree':r.TREE,'execution_binding':receipt['execution_binding']}))
 job=dict(id=r.JOB,serviceId=m.SERVICE,status='succeeded',finishedAt='2026-11-04T21:51:28Z',createdAt='2026-11-04T21:50:40Z',startCommand='fixed startup')
 state=dict(period=r.PERIOD,deployment=r.DEPLOY,status='PREPARATION_REFUSED',failure=dict(exception_class='ReadTimeout',phase='STARTUP_PREFLIGHT_JOB',reason='UNKNOWN_FAILURE',sqlstate=None,status='RECONCILIATION_REQUIRED'),startup_job=job,startup_job_terminal=job,startup_command=job['startCommand'],intents={k:dict(state='ACKNOWLEDGED',at=1793828940) for k in ('BUILD_ENVIRONMENT','BUILD_CONFIGURATION','ONE_RESUME_BUILD','RESUSPEND','RESTORE_BUILD_CONFIGURATION','RESTORE_BUILD_ENVIRONMENT','STARTUP_PREFLIGHT_JOB')})
 class Journal:
  previous=r.JOURNAL_SHA;ordinal=21;writes=0;lose=None;corrupt=False
  def __init__(self):self.value=copy.deepcopy(state)
  def load(self):return copy.deepcopy(self.value)
  def save(self,s):
   self.value=copy.deepcopy(s);self.writes+=1;self.ordinal+=1
   if self.corrupt:self.value['startup_preflight']['sha256']='bad'
   if self.lose==self.writes:raise TimeoutError('synthetic lost acknowledgement')
 p=object.__new__(m.Pilot);p.journal=Journal();p.state=None
 calls=[];inventory=[{'job':job}]
 class API:
  def call(self,method,path):
   calls.append((method,path));assert method=='GET'
   return inventory if path=='/jobs?limit=100' else job
 @contextmanager
 def api():yield API()
 p.api=api
 observed=dict(current_readback=dict(configuration_equal=True,environment_equal=True,suspended=True,latest_deployment=r.DEPLOY,latest_revision=r.REVISION,jobs_since_preparation=1),period_present=False,attempt_authorities={'count':0},temporary_owner_absent=True,pipeline_session_count=0,runtime_membership_count=0,stable_verifier_binding='MATCH',runtime_roles=[dict(login=False,password_null=False)]*2)
 def inspect():p.state=p.journal.load();return copy.deepcopy(observed)
 p.inspect=inspect
 return p,dict(version='ATTEMPT06_STARTUP_RECEIPT_V1',receipt=receipt),job,inventory,observed,calls

def test_dispatch_success_idempotence(monkeypatch):
 p,cfg,job,inventory,observed,calls=setup(monkeypatch)
 assert p.reconcile_artifact(cfg)['status']=='ARTIFACT_READY'
 assert p.journal.writes==2 and p.journal.value['failure']==p.journal.value['preparation_failure']
 assert p.reconcile_artifact(cfg)['status']=='ARTIFACT_READY' and p.journal.writes==2
 assert all(method=='GET' for method,_ in calls)

@pytest.mark.parametrize('lost',[1,2])
def test_interrupted_write(monkeypatch,lost):
 p,cfg,*_=setup(monkeypatch);p.journal.lose=lost
 with pytest.raises(TimeoutError):p.reconcile_artifact(cfg)
 p.journal.lose=None
 assert p.reconcile_artifact(cfg)['status']=='ARTIFACT_READY' and p.journal.writes==2

@pytest.mark.parametrize('bad',['receipt','history','environment','access','snapshot','job','conflict'])
def test_refusals(monkeypatch,bad):
 p,cfg,job,inventory,observed,calls=setup(monkeypatch)
 if bad=='receipt':cfg['receipt']['source_requests']=1
 elif bad=='history':inventory.append({'job':dict(job,id='job-'+'a'*20)})
 elif bad=='environment':observed['current_readback']['environment_equal']=False
 elif bad=='access':observed['runtime_roles'][0]['login']=True
 elif bad=='snapshot':p.journal.previous='a'*64
 elif bad=='job':job['status']='failed'
 else:p.journal.value['startup_reconciliation']={'wrong':True}
 with pytest.raises(m.op.Denied):p.reconcile_artifact(cfg)
 assert p.journal.writes==0

def test_corrupt_readback_never_ready(monkeypatch):
 p,cfg,*_=setup(monkeypatch);p.journal.corrupt=True
 with pytest.raises(m.op.Denied,match='DURABLE_READBACK'):p.reconcile_artifact(cfg)
 assert p.journal.value['status']=='PREPARATION_REFUSED' and p.journal.writes==1
