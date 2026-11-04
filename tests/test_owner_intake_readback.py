import copy,json
from contextlib import contextmanager
from types import SimpleNamespace
from verification.ingestion_storage import owner_pilot as p
from verification.ingestion_storage.intake_owner_io import service_guard

def test_preparation_readback_is_get_and_read_only_without_journal_mutation():
    service={'id':p.SERVICE,'type':'cron_job','suspended':'suspended','autoDeploy':'no','branch':'master','serviceDetails':{'schedule':'0 5 * * *','envSpecificDetails':{'startCommand':'/bin/true','buildCommand':'original'}}}
    original={'DATABASE_URL':'SENSITIVE_SENTINEL','PLAYWRIGHT_BROWSERS_PATH':'0'}
    state={'period':p.PERIOD,'status':'PREPARATION_REFUSED','intents':{'RESTORE_BUILD_ENVIRONMENT':{'state':'ACKNOWLEDGED'}},'original_guard':service_guard(service),'original_environment':original,'failure':{'reason':'UNKNOWN_FAILURE','phase':'RESUSPEND'}}
    class DB:
        @contextmanager
        def connection(self):yield self
        def execute(self,q,params=None):
            assert q.startswith(('BEGIN READ ONLY','SELECT ','ROLLBACK'));self.q=q;return self
        def fetchone(self):return ({'intake_periods':{}},) if 'outcome::jsonb' in self.q else (0,) if 'count(*)' in self.q else (True,)
        def fetchall(self):return [('ingestion_worker_login',False,True),('ingestion_effect_login',False,True)]
    calls=[]
    class API:
        def call(self,method,suffix='',body=None):
            assert method=='GET' and body is None;calls.append(suffix)
            if suffix=='':return service
            if suffix=='/env-vars?limit=100':return [{'envVar':{'key':k,'value':v}} for k,v in original.items()]
            return []
        def close(self):pass
    pilot=object.__new__(p.Pilot);pilot.db=DB();pilot.render_factory=API
    pilot.journal=SimpleNamespace(ordinal=0,load=lambda:copy.deepcopy(state),save=lambda *_a,**_k:(_ for _ in ()).throw(AssertionError('READBACK_MUTATION')))
    result=pilot.inspect()
    assert result['status']=='READ_ONLY_EVIDENCE_SAVED' and result['workflow_status']=='PREPARATION_REFUSED'
    assert result['current_readback']['environment_equal'] and result['current_readback']['configuration_equal'] and result['temporary_owner_absent']
    assert result['period_present'] is False and len(calls)==4 and 'SENSITIVE_SENTINEL' not in json.dumps(result)

def test_unknown_class_and_message_are_not_exported():
    exception=type('SENSITIVE_SENTINEL',(RuntimeError,),{})('SENSITIVE_SENTINEL')
    result=p.safe_result(exception)
    assert result['exception_class']=='UNKNOWN_CLASS' and result['reason']=='UNKNOWN_FAILURE' and 'SENSITIVE_SENTINEL' not in json.dumps(result)
