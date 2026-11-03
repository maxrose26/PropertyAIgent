import copy,hashlib,json
from contextlib import contextmanager
import pytest
from verification.ingestion_storage import owner_pilot as p

def setup(monkeypatch):
 e={'revision':'1'*40,'workflow_sha256':'2'*64,'manifest_sha256':'3'*64};monkeypatch.setenv('PROPERTYAIGENT_INTAKE_SOURCE_RELEASE',json.dumps({'execution_binding':e}))
 failure={'phase':'RESUSPEND','reason':'UNKNOWN_FAILURE','sqlstate':None,'status':'RECONCILIATION_REQUIRED'}
 receipt={'kind':'DATABASE_PILOT_BUILD_NOT_EXECUTION','execution_binding':e,'browser_canary':'LAUNCHED_AND_CLOSED','browser_path':'/fixture/browser','browser_executable':'/fixture/browser/shell/chrome-headless-shell','browser_sha256':'a'*64}
 cfg={'version':'AUTHORITATIVE_RENDER_RECEIPT_V1','deployment':'dep-'+'a'*20,'receipt_sha256':hashlib.sha256(p.canonical(receipt)).hexdigest(),'receipt':receipt,'preparation_failure_sha256':hashlib.sha256(p.canonical(failure)).hexdigest()}
 names=('BUILD_ENVIRONMENT','BUILD_CONFIGURATION','ONE_RESUME_BUILD','RESUSPEND','RESTORE_BUILD_CONFIGURATION','RESTORE_BUILD_ENVIRONMENT')
 state={'period':p.PERIOD,'status':'PREPARATION_REFUSED','deployment':cfg['deployment'],'failure':failure,'intents':{x:{'state':'ACKNOWLEDGED'} for x in names}}
 class Journal:
  def __init__(self):self.value=copy.deepcopy(state);self.writes=0;self.reads=0
  def load(self):self.reads+=1;return copy.deepcopy(self.value)
  def save(self,value):self.value=copy.deepcopy(value);self.writes+=1
 class DB:
  @contextmanager
  def connection(self):yield self
  def execute(self,statement):assert statement in ('BEGIN READ ONLY','ROLLBACK')
 pilot=object.__new__(p.Pilot);pilot.journal=Journal();pilot.db=DB()
 observed={'workflow_status':'PREPARATION_REFUSED','current_readback':{'suspended':True,'configuration_equal':True,'environment_equal':True,'latest_deployment':cfg['deployment'],'latest_revision':e['revision'],'jobs_since_preparation':0},'period_present':False,'temporary_owner_absent':True,'runtime_roles':[{'login':False,'password_null':True}]*2}
 monkeypatch.setattr(p.Pilot,'inspect',lambda _:copy.deepcopy(observed))
 for name in ('dormant','inventory','no_hazards'):monkeypatch.setattr(p.op,name,lambda *_:None)
 monkeypatch.setattr(p.op,'control',lambda *_:{})
 monkeypatch.setattr(p,'verify_inventory',lambda *_:None)
 return pilot,cfg,observed,state

def test_existing_receipt_journal_idempotency_conflict_and_durable_readback(monkeypatch):
 pilot,cfg,observed,original=setup(monkeypatch)
 result=pilot.reconcile_artifact(cfg)
 assert result['status']=='ARTIFACT_READY' and pilot.journal.writes==1 and pilot.journal.reads==2
 assert pilot.journal.value['failure']==original['failure'] and pilot.journal.value['intents']==original['intents']
 assert pilot.journal.value['artifact']==cfg['receipt']
 assert pilot.reconcile_artifact(cfg)['status']=='ARTIFACT_READY' and pilot.journal.writes==1
 wrong=copy.deepcopy(cfg);wrong['deployment']='dep-'+'b'*20
 with pytest.raises(p.op.Denied,match='CONFLICT'):pilot.reconcile_artifact(wrong)
 assert pilot.journal.writes==1

@pytest.mark.parametrize('bad',['hash','drift','active_role'])
def test_bad_binding_or_current_state_refuses_before_write(monkeypatch,bad):
 pilot,cfg,observed,original=setup(monkeypatch)
 if bad=='hash':cfg['receipt_sha256']='0'*64
 elif bad=='drift':observed['current_readback']['environment_equal']=False
 else:observed['runtime_roles'][0]['login']=True
 with pytest.raises(p.op.Denied):pilot.reconcile_artifact(cfg)
 assert pilot.journal.writes==0

def test_private_diagnostic_omits_messages_locals_and_secret_values():
 try:raise TypeError('SENSITIVE_SENTINEL bearer=password')
 except TypeError as exc:diagnostic=p.private_failure(exc,'RECONCILE')
 assert diagnostic['exception_class']=='TypeError' and diagnostic['messages']=='OMITTED' and 'SENSITIVE_SENTINEL' not in json.dumps(diagnostic)
