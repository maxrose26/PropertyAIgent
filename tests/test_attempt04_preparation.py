"""Affected owner continuation and actual guard path; synthetic I/O only."""
import copy,json,sys,subprocess
from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from verification.ingestion_storage import owner_pilot as p,owner_pilot_continuation as step
from tests.test_owner_pilot_continuation import closed

def test_prepare_reuses_stable_credentials_and_orders_build_before_startup(monkeypatch):
    from verification.ingestion_storage import stable_runtime_credentials as stable
    old=closed();old['stable_configuration']={'outcome':'COMMIT_ACKNOWLEDGED'};before=copy.deepcopy(old);events=[]
    @contextmanager
    def connection():yield object()
    pilot=object.__new__(p.Pilot);pilot.db=SimpleNamespace(connection=connection);pilot.journal=SimpleNamespace(load=lambda:None)
    monkeypatch.setattr(p,'Journal',lambda db,period:SimpleNamespace(load=lambda:old))
    monkeypatch.setattr(step,'migrate_owner_namespace',lambda c,**kw:events.append(('migration',kw)))
    monkeypatch.setattr(stable,'prepare',lambda *x:pytest.fail('NEW_SECRET_NOT_ALLOWED'))
    monkeypatch.setattr(stable,'configure',lambda *x:pytest.fail('PASSWORD_WRITE_NOT_ALLOWED'))
    pilot.save=lambda:None;pilot.build=lambda:events.append('build');pilot.startup_preflight=lambda:events.append('startup')
    pilot.prepare_continuation()
    assert events==[('migration',{'stable_verifiers':old['stable_credentials']['verifier_sha256']}),'build','startup']
    assert old==before and pilot.state['stable_credentials']==old['stable_credentials']
    assert pilot.state['stable_credentials'] is not old['stable_credentials']
    assert pilot.state['status']=='ARTIFACT_READY' and p.PERIOD=='b-dbpilot-20261027-1102-04'

@pytest.mark.parametrize('kind',['clean','dirty','git_failure'])
def test_actual_runtime_guard_preflight_never_qualifies(monkeypatch,tmp_path,capsys,kind):
    from scripts import owner_pilot_job as job
    from verification.ingestion_storage import daily_intake_runtime as native,runtime_authentication as auth
    from scripts import run_daily_councils as daily
    Real=native.Runtime
    monkeypatch.setattr(native,'execution_binding',lambda:{'revision':'1'*40})
    monkeypatch.setattr(auth,'qualify',lambda *x:pytest.fail('AUTHENTICATION_REACHED'))
    monkeypatch.setattr(daily,'main',lambda **x:pytest.fail('COLLECTION_REACHED'))
    monkeypatch.setattr(native.DatabaseBudget,'engine',lambda *x,**kw:pytest.fail('DATABASE_REACHED'))
    def constructor(args):args.output=str(tmp_path/'source');return Real(args)
    monkeypatch.setattr(native,'Runtime',constructor)
    def git(command,*args,**kw):
        if command==['git','status','--porcelain','--untracked-files=no']:
            if kind=='git_failure':raise subprocess.CalledProcessError(128,command)
            return ' M safe.sh\n' if kind=='dirty' else ''
        return '2'*40+'\n'
    monkeypatch.setattr(subprocess,'check_output',git)
    monkeypatch.setattr(job.os,'environ',{'PATH':'/usr/bin','RENDER_GIT_COMMIT':'1'*40,'DATABASE_URL':'SENSITIVE_SENTINEL'})
    monkeypatch.setattr(sys,'argv',['job','--period',p.PERIOD,'--hostaddr','127.0.0.1','--startup-check-only'])
    assert job.main()==(0 if kind=='clean' else 2)
    raw=capsys.readouterr().out;assert 'SENSITIVE_SENTINEL' not in raw
    r=json.loads(raw.split('DATABASE_PILOT_STARTUP_GUARD ')[1])
    assert r['authentication_attempts']==r['source_requests']==0
    assert r['status']==('CLEAN_CHECKOUT_VERIFIED_BEFORE_QUALIFICATION' if kind=='clean' else 'REFUSED')
    assert r.get('reason')==({'dirty':'CLEAN_REVIEWED_CHECKOUT_REQUIRED','git_failure':'GIT_STATUS_UNVERIFIED'}.get(kind))

@pytest.mark.parametrize('mode',['success','wrong_receipt','uncertain_post'])
def test_packaged_preflight_intent_receipt_and_no_second_post(monkeypatch,mode):
    from verification.ingestion_storage.intake_owner_io import service_guard
    binding={'revision':'1'*40};release={'execution_binding':binding,'tree':'2'*40}
    monkeypatch.setenv('PROPERTYAIGENT_INTAKE_SOURCE_RELEASE',json.dumps(release))
    service={'id':p.SERVICE,'type':'cron_job','suspended':'suspended','autoDeploy':'no','branch':'master','serviceDetails':{'schedule':'0 5 * * *','envSpecificDetails':{'buildCommand':'original','startCommand':'/bin/true'}}}
    pilot=object.__new__(p.Pilot);pilot.state={'period':p.PERIOD,'intents':{},'deployment':'dep-'+'a'*20,'original_guard':service_guard(service),'original_environment':{'PLAYWRIGHT_BROWSERS_PATH':'0'},'stable_credentials':{'verifier_sha256':{'r':'a'*64}}}
    pilot.save=lambda:None;pilot.sleep=lambda _:None;posts=[]
    receipt=dict(status='CLEAN_CHECKOUT_VERIFIED_BEFORE_QUALIFICATION',period=p.PERIOD,execution_binding=binding,tree=release['tree'],cwd='/opt/render/project/src',git=dict(exit_status=0,tracked_changes=False),authentication_attempts=0,source_requests=0)
    if mode=='wrong_receipt':receipt['source_requests']=1
    class API:
        def __init__(self):self.calls=0
        def call(self,method,suffix='',body=None):
            self.calls+=1;assert self.calls<=8
            if method=='POST':
                assert pilot.state['intents']['STARTUP_PREFLIGHT_JOB']['state']=='INTENT_NO_RETRY'
                posts.append(True)
                if mode=='uncertain_post':raise RuntimeError('SENSITIVE_SENTINEL')
                return dict(id='job-'+'b'*20,serviceId=p.SERVICE,startCommand=body['startCommand'])
            if suffix=='':return service
            if suffix=='/env-vars?limit=100':return [{'envVar':{'key':'PLAYWRIGHT_BROWSERS_PATH','value':'0'}}]
            if suffix=='/jobs?limit=100':return []
            if suffix=='/deploys?limit=100':return [{'deploy':dict(id=pilot.state['deployment'],commit={'id':'1'*40},status='live',createdAt='2026-11-04T00:00:00Z',finishedAt='2026-11-04T00:01:00Z')}]
            if suffix.startswith('/jobs/'):return dict(id='job-'+'b'*20,status='succeeded',finishedAt='2026-11-04T00:03:00Z')
            assert suffix.startswith('startup:');return {'hasMore':False,'logs':[{'message':'DATABASE_PILOT_STARTUP_GUARD '+json.dumps(receipt)}]}
        def close(self):pass
    pilot.render_factory=API
    @contextmanager
    def connection():yield object()
    pilot.db=SimpleNamespace(connection=connection)
    monkeypatch.setattr(p.op,'dormant',lambda c,**kw:None);monkeypatch.setattr(p.op,'owner_absent',lambda c:None)
    monkeypatch.setattr(p.op,'control',lambda c:{});monkeypatch.setattr(p.op,'no_hazards',lambda *x:None)
    if mode=='success':
        pilot.startup_preflight();assert pilot.state['startup_preflight']['receipt']==receipt
    else:
        with pytest.raises((RuntimeError,p.op.Denied)):pilot.startup_preflight()
        assert 'startup_preflight' not in pilot.state
    with pytest.raises(p.op.Denied,match='PRIOR_INTENT'):pilot.startup_preflight()
    assert len(posts)==1
