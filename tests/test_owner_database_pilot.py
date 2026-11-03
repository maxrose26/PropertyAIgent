"""Synthetic owner bridge checks; no live provider or production connection."""
import copy,json,time,hashlib
from contextlib import contextmanager
from datetime import datetime,timezone
import pytest
from verification.ingestion_storage import owner_pilot as p,intake_owner as op
from verification.ingestion_storage.intake_owner_io import handoff,restore_handoff,service_guard
from verification.ingestion_storage.intake_owner_operations import validate_policy
from tests.test_intake_owner_io import API

@pytest.fixture
def bound(monkeypatch,tmp_path):
    e={'revision':'1'*40,'workflow_sha256':'2'*64,'manifest_sha256':'3'*64}
    release={'execution_binding':e,'deployment':'dep-'+'a'*20}
    monkeypatch.setenv('PROPERTYAIGENT_INTAKE_SOURCE_RELEASE',json.dumps(release))
    profile=p.source_profile({'execution_binding':e,'browser_canary':'LAUNCHED_AND_CLOSED','browser_path':'/fixture/browser','browser_sha256':'a'*64},e['revision'])
    api=API();api.env={'DATABASE_URL':'SECRET_ADMIN','PLAYWRIGHT_BROWSERS_PATH':'0','PYTHONUNBUFFERED':'1','PLANNING_STATUS_VERIFICATION_ENABLED':'SECRET_SETTING'}
    b,policy=p.fixed_binding(release,profile,'192.0.2.1',service_guard(api.service))
    b.update(release_root=str(tmp_path),submission_intent_path=str(tmp_path/'intent'))
    return b,policy,api

def obs(b,operation):
    return dict(version='FINITE_OPERATION_OBSERVATION_V1',operation=operation,binding_sha256=hashlib.sha256(p.canonical(b)).hexdigest(),
        service_id=p.SERVICE,observed_at=time.time(),env_groups=[],secret_files=[],inherited_credential_names=[],reviewed=True,
        no_current_work=True,other_activity_stopped=True,deployment_id=b['retained_deployment'],revision=b['execution_binding']['revision'],suspended=True)

def test_fixed_deadline_and_policy_no_provider_token(bound):
    b,policy,api=bound
    assert b['valid_until']==b['timing_policy']['bound_at']+2100 and policy['expires_at']==b['valid_until']-185
    assert validate_policy(b,policy)==policy and 'publication_valid_until' not in b
    bad=copy.deepcopy(b);bad['valid_until']+=1
    with pytest.raises(op.Denied):op.validate_binding(bad)
    with pytest.raises(op.Denied):op.validate_binding(b,opening=True,now=b['valid_until']-1500)
    with pytest.raises(op.Denied):p.fixed_binding({'execution_binding':b['execution_binding'],'deployment':b['retained_deployment']},b['render_profile'],'192.0.2.1',b['render_config_sha256'],datetime(2026,11,3,23,30,tzinfo=timezone.utc).timestamp())

def test_actual_database_handoff_zero_selector_and_exact_restoration(bound):
    b,policy,api=bound;original=copy.deepcopy(api.env);states=[]
    state={'binding':b,'state':'ACTIVATION_ACKNOWLEDGED','passwords':{r:'SYNTHETIC_RESTRICTED_PASSWORD_'+'x'*40 for r in op.ROLES}}
    handoff(api,state,lambda x:states.append(copy.deepcopy(x)),None,observation=obs(b,'HANDOFF'))
    assert api.env['PLAYWRIGHT_BROWSERS_PATH']=='0' and 'GH_TOKEN' not in api.env and 'DATABASE_URL' not in api.env
    assert states[0]['render']['state']=='PUT_INTENT_NO_RETRY'
    state['state']='DATABASE_CLOSURE_ACKNOWLEDGED';api.calls=0
    r=restore_handoff(api,state,lambda _:None,None)
    assert r['status']=='RESTORATION_VERIFIED' and api.env==original

def test_wrong_operation_stale_observation_and_uncertain_put_do_not_repeat(bound):
    b,policy,api=bound;state={'binding':b,'state':'ACTIVATION_ACKNOWLEDGED','passwords':{r:'x'*48 for r in op.ROLES}}
    for wrong in ('SUBMISSION','STALE'):
        o=obs(b,'HANDOFF' if wrong=='STALE' else wrong)
        if wrong=='STALE':o['observed_at']-=301
        with pytest.raises(op.Denied):handoff(api,state,lambda _:None,None,observation=o)
    assert api.puts==0
    api.fail_put=True
    with pytest.raises(RuntimeError):handoff(api,state,lambda _:None,None,observation=obs(b,'HANDOFF'))
    with pytest.raises(op.Denied):handoff(api,state,lambda _:None,None,observation=obs(b,'HANDOFF'))
    assert api.puts==1

class MemoryDB:
    key='a'*64
    def __init__(self):
        from types import SimpleNamespace
        from psycopg.pq import TransactionStatus
        self.rows=[];self.lost=False;self.pgconn=SimpleNamespace(transaction_status=TransactionStatus.IDLE)
    @contextmanager
    def connection(self):yield self
    def execute(self,sql,params):
        period,run,previous=params[:3];body=params[3] if len(params)==4 else None
        assert (period,run)==(p.OWNER_PERIOD,p.OWNER_RUN)
        if body is None:self.row=self.rows[-1] if self.rows else None
        else:
            assert previous==(self.rows[-1][2] if self.rows else '')
            self.row=(len(self.rows),body,hashlib.sha256(body).hexdigest());self.rows.append(self.row)
            if self.lost:raise RuntimeError('SENSITIVE_SENTINEL')
        return self
    def fetchone(self):return self.row

def test_existing_vault_format_is_durable_and_recoverable_after_session_loss():
    db=MemoryDB();j=p.Journal(db);assert j.load() is None
    j.save({'period':p.PERIOD,'password':'SENSITIVE_SENTINEL','intents':{'ACTIVATE':'INTENT'}})
    assert b'SENSITIVE_SENTINEL' not in db.rows[0][1]
    other=p.Journal(db);assert other.load()['password']=='SENSITIVE_SENTINEL'
    db.lost=True
    with pytest.raises(RuntimeError):other.save({'period':p.PERIOD,'password':'SENSITIVE_SENTINEL','state':'COMMITTED'})
    assert p.Journal(db).load()['state']=='COMMITTED' and len(db.rows)==2
    assert 'SENSITIVE_SENTINEL' not in json.dumps(p.safe_result(RuntimeError('SENSITIVE_SENTINEL')))

def test_consumed_journal_cannot_start_a_second_run(monkeypatch):
    pilot=object.__new__(p.Pilot);pilot.journal=p.Journal(MemoryDB());pilot.journal.save({'period':p.PERIOD,'status':'RELEASE_BOUND','intents':{'RELEASE':{}}})
    with pytest.raises(op.Denied,match='PRIOR_ATTEMPT'):pilot.run(time.time())

def test_missing_or_stale_owner_boundary_refuses_before_database_or_consumption():
    pilot=object.__new__(p.Pilot)
    for observed in (None,time.time()-301,time.time()+60):
        with pytest.raises(op.Denied,match='INHERITED_BOUNDARY'):pilot.run(observed)

@pytest.mark.parametrize('value',[[],[{'deploy':{'id':'dep-a','createdAt':'2026-11-03T10:00:00Z','finishedAt':'2026-11-03T10:01:00Z','status':'live'}}]])
def test_complete_inventory(value):assert p.complete_inventory(value,'deploy')==[x['deploy'] for x in value]

@pytest.mark.parametrize('bad',[([{}]),([{'job':{'id':'j','createdAt':'2026-11-03T10:00:00Z','status':'running'}}]),([{}]*100)])
def test_partial_active_or_malformed_inventory_refuses(bad):
    with pytest.raises((op.Denied,KeyError)):p.complete_inventory(bad,'job')

def test_actual_transport_limits_and_safe_http_diagnostics():
    class Reply:
        status_code=200
        def __init__(self,raw):self.raw=raw
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def iter_content(self,n):
            for i in range(0,len(self.raw),n):yield self.raw[i:i+n]
    class Session:
        def __init__(self,raw):self.raw=raw;self.calls=0;self.status=200
        def request(self,*a,**kw):
            self.calls+=1;assert kw['allow_redirects'] is False and kw['headers']['Authorization']=='Bearer SYNTHETIC_SENTINEL'
            reply=Reply(self.raw);reply.status_code=self.status;return reply
        def close(self):pass
    s=Session(b'"'+b'x'*524286+b'"');api=p.Render('SYNTHETIC_SENTINEL',session=s)
    assert len(api.call('GET','/deploys?limit=100'))==524286
    s.raw=b'"'+b'x'*32767+b'"'
    with pytest.raises(op.Denied) as failure:api.call('GET','')
    result=p.safe_result(failure.value);assert result['reason']=='OWNER_RENDER_RESPONSE_BYTE_LIMIT' and result['limits']['response_byte_limit']==32768
    assert 'SYNTHETIC_SENTINEL' not in json.dumps(result)
    s=Session(b'[]');api=p.Render('SYNTHETIC_SENTINEL',session=s)
    for _ in range(8):api.call('GET','')
    with pytest.raises(op.Denied) as failure:api.call('GET','')
    assert s.calls==8 and p.safe_result(failure.value)['reason']=='OWNER_RENDER_REQUEST_LIMIT'
    s=Session(b'[]');s.status=401;api=p.Render('SYNTHETIC_SENTINEL',session=s)
    with pytest.raises(op.Denied) as failure:api.call('GET','')
    assert p.safe_result(failure.value)['http_status']==401 and s.calls==1

def test_restoration_uncertainty_never_permits_a_second_put(bound):
    b,policy,api=bound
    state={'binding':b,'state':'ACTIVATION_ACKNOWLEDGED','passwords':{r:'x'*48 for r in op.ROLES}}
    handoff(api,state,lambda _:None,None,observation=obs(b,'HANDOFF'))
    state['state']='DATABASE_CLOSURE_ACKNOWLEDGED';state['render']['reconciliation']='EXPECTED';api.fail_put=True
    with pytest.raises(RuntimeError):restore_handoff(api,state,lambda _:None,None)
    with pytest.raises(op.Denied,match='PRIOR_INTENT'):restore_handoff(api,state,lambda _:None,None)
    assert api.puts==2

def test_connected_owner_prepare_run_and_independent_closure_mocked(bound,tmp_path,monkeypatch):
    b,policy,old=bound;e=b['execution_binding']
    monkeypatch.setenv('PROPERTYAIGENT_INTAKE_SOURCE_RELEASE',json.dumps({'execution_binding':e,'branch':'prep/b-timing-pg17-current-20261103'}))
    class Provider:
        def __init__(self):
            self.env=copy.deepcopy(old.env);self.original=copy.deepcopy(self.env);self.jobs=[];self.writes=[];self.calls=0
            self.service={'id':p.SERVICE,'ownerId':p.WORKSPACE,'type':'cron_job','suspended':'suspended','autoDeploy':'no','branch':'master',
                'serviceDetails':{'plan':'standard','schedule':'0 5 * * *','envSpecificDetails':{'buildCommand':'original','startCommand':'/bin/true'}}}
            self.deploys=[{'id':'dep-'+'b'*20,'createdAt':'2026-11-02T10:00:00Z','finishedAt':'2026-11-02T10:01:00Z','status':'live','commit':{'id':'9'*40}}]
        def call(self,method,suffix='',body=None):
            self.calls+=1
            if method!='GET':self.writes.append((method,suffix))
            if method=='PUT':self.env={x['key']:x['value'] for x in body};return []
            if method=='PATCH':
                self.service['branch']=body['branch'];self.service['serviceDetails']['envSpecificDetails'].update(body['serviceDetails']['envSpecificDetails']);return self.service
            if method=='POST' and suffix=='/resume':
                self.service['suspended']='not_suspended';self.deploys.insert(0,{'id':'dep-'+'a'*20,'createdAt':'2026-11-03T10:00:00Z','finishedAt':'2026-11-03T10:01:00Z','status':'live','commit':{'id':e['revision']}});return None
            if method=='POST' and suffix=='/suspend':self.service['suspended']='suspended';return None
            if method=='POST' and suffix=='/jobs':
                self.jobs.append({'id':'job-'+'a'*20,'serviceId':p.SERVICE,'startCommand':body['startCommand'],'createdAt':datetime.now(timezone.utc).isoformat(),'finishedAt':datetime.now(timezone.utc).isoformat(),'status':'succeeded'});return copy.deepcopy(self.jobs[-1])
            if suffix=='':return copy.deepcopy(self.service)
            if suffix=='/env-vars?limit=100':return [{'envVar':{'key':k,'value':v}} for k,v in self.env.items()]
            if suffix=='/jobs?limit=100':return [{'job':x} for x in self.jobs]
            if suffix=='/deploys?limit=100':return [{'deploy':x} for x in self.deploys]
            if suffix=='/secret-files?limit=100':return []
            if suffix.startswith('/jobs/'):return copy.deepcopy(self.jobs[-1])
            if suffix.startswith('artifact:'):return {'hasMore':False,'logs':[{'message':'DATABASE_PILOT_BUILD_RECEIPT '+json.dumps({'execution_binding':e,'browser_path':'/fixture/browser','browser_sha256':'a'*64,'browser_canary':'LAUNCHED_AND_CLOSED'})}]}
            raise AssertionError((method,suffix))
        def close(self):pass
    provider=Provider();db=MemoryDB();db.address='192.0.2.1'
    pilot=p.Pilot(db,token='SENSITIVE_SENTINEL',render_factory=lambda:provider,sleep=lambda _:None)
    monkeypatch.setattr(p.Pilot,'migrate',lambda _:None)
    monkeypatch.setattr(p,'verify_inventory',lambda _:None)
    for name in ('identity','inventory','dormant','owner_absent','retained_cleanup','no_hazards'):monkeypatch.setattr(op,name,lambda *a,**kw:None)
    monkeypatch.setattr(op,'control',lambda *_:dict(op.ACCEPTED_STOP,intake_periods={},intake_run={'id':'a'*32,'publication':{'fixture':True}}))
    def period(c,b,policy,journal,save):journal['state']='COMMIT_ACKNOWLEDGED';save(journal);return {'temporary_issuer':'REMOVED'}
    monkeypatch.setattr(p,'issue_period',period)
    prepared=lambda c,b:{'version':'FINITE_INTAKE_ACCESS_STATE_V1','binding':b,'state':'ARMED_BEFORE_ACTIVATION','passwords':{r:'x'*48 for r in op.ROLES}}
    monkeypatch.setattr(op,'prepare_activation',prepared)
    def activate(c,b,save,prepared=None):
        save(dict(prepared,state='ACTIVATION_ACKNOWLEDGED'));return {'outcome':'COMMIT_ACKNOWLEDGED'}
    monkeypatch.setattr(op,'activate',activate);monkeypatch.setattr(p.Pilot,'qualify',lambda _:['SYNTHETIC_AUTHENTICATIONS'])
    monkeypatch.setattr(op,'finalisation',lambda *a:{'status':'INDEPENDENT_DATABASE_VERIFIED_SUCCESS','captures':[{'council':'tameside','record_count':9},{'council':'manchester','record_count':1}]})
    monkeypatch.setattr(p.Pilot,'read_result',lambda _:None)
    def close(c,state,save):state['state']='DATABASE_CLOSURE_ACKNOWLEDGED';state['passwords']={};save(state);return {'runtime_access':'DISABLED'}
    monkeypatch.setattr(op,'close',close)
    # Keep the actual exclusive local submission-file path, isolated from all
    # historical paths. No fake intent or provider effect is written to them.
    monkeypatch.setattr(p,'RELEASE_PARENT',tmp_path)
    failures=[];safe=p.safe_result
    def remember(exc):failures.append((type(exc).__name__,str(exc)));return safe(exc)
    monkeypatch.setattr(p,'safe_result',remember)
    pilot.prepare();assert pilot.state['status']=='ARTIFACT_READY'
    result=pilot.run(time.time())
    assert result['pipeline_status']=='VERIFIED_RETAINED_AND_SCREENED' and result['status']=='CLOSED',failures
    assert all(result['final_service'].values()) and provider.env==provider.original
    assert provider.writes.count(('POST','/resume'))==1 and provider.writes.count(('POST','/jobs'))==1
    assert not any(suffix=='/deploys' for method,suffix in provider.writes)
    assert 'SENSITIVE_SENTINEL' not in json.dumps(result)
    with pytest.raises(op.Denied):pilot.run(time.time())
