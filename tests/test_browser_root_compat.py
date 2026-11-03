"""Owner-only compatibility: real retained guards/code; synthetic browser and APIs.
No actual browser, source, credential, database or provider operation.
"""
import copy,hashlib,json,time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import pytest
from app.ingestion.ledger import Denied
from verification.ingestion_storage import intake_owner as owner,intake_owner_io as io,render_intake as render,daily_intake_runtime as runtime
from tests.test_intake_owner_io import API
from tests.test_intake_owner_operations import inputs
from tests.test_render_intake import profile as synthetic_profile
from verification.ingestion_storage.operational_publication import canonical

@pytest.fixture(autouse=True)
def no_live(monkeypatch):
 import requests,psycopg
 monkeypatch.setattr(requests.sessions.Session,'request',lambda *a,**k:pytest.fail('NO_LIVE_HTTP'))
 monkeypatch.setattr(psycopg,'connect',lambda **k:pytest.fail('NO_LIVE_DATABASE'))

@pytest.fixture
def prepared(tmp_path):
 p=synthetic_profile(tmp_path);p.update(revision=owner.APPLICATION_BINDING['revision'],source_rss_bytes=1073741824,controller_rss_bytes=268435456,reserve_bytes=536870912,source_seconds=75)
 b,_=inputs(tmp_path);T=time.time();b.update(valid_until=T+2100,publication_valid_until=T+3600,timing_policy=dict(version='SEPARATE_EXPIRY_V2_RESERVE',bound_at=T,execution_day=time.strftime('%Y-%m-%d',time.localtime(T))),runtime_deadline=T+2100-185,render_profile=p,retained_deployment='dep-SYNTHETIC',release_root=str(tmp_path),submission_intent_path=str(tmp_path/'submission.intent.json'),publication_mint=dict(authority_sha256='a'*64,receipt_sha256='b'*64,expires_at=T+3600))
 api=API()
 # Model the baseline literally. Never copy the profile directory into this map.
 api.env={'PLAYWRIGHT_BROWSERS_PATH':'0','PYTHONUNBUFFERED':'1','DATABASE_URL':'SYNTHETIC_ADMIN_NEVER_EXPORT','PLANNING_STATUS_VERIFICATION_ENABLED':'SYNTHETIC_BASELINE'}
 b['render_config_sha256']=io.service_guard(api.service)
 obs=dict(version='FINITE_OPERATION_OBSERVATION_V1',operation='HANDOFF',binding_sha256=hashlib.sha256(canonical(b)).hexdigest(),service_id=io.SERVICE,observed_at=T,env_groups=[],secret_files=[],inherited_credential_names=[],reviewed=True,no_current_work=True,other_activity_stopped=True,deployment_id=b['retained_deployment'],revision=b['execution_binding']['revision'],suspended=True)
 state=dict(state='ACTIVATION_ACKNOWLEDGED',binding=b,passwords={r:'SYNTHETIC_PASSWORD_'+'x'*48 for r in owner.ROLES})
 return dict(api=api,b=b,p=p,obs=obs,state=state,root=tmp_path)

def test_actual_handoff_zero_baseline_encrypted_original_and_exact_restore(prepared,monkeypatch):
 f=prepared;api=f['api'];original=copy.deepcopy(api.env);key='SYNTHETIC_LOCAL_VAULT_ONLY_ABOVE24';vault=io.Vault(f['root']/'state.vault',key,create=True);vault.save(f['state'])
 result=io.handoff(api,f['state'],vault.save,'ghs_'+'SYNTHETIC_ONLY_'*5,observation=f['obs'])
 assert result['status']=='RENDER_HANDOFF_ACKNOWLEDGED' and api.puts==1 and api.env['PLAYWRIGHT_BROWSERS_PATH']=='0'
 assert json.loads(api.env['INGESTION_RENDER_PROFILE'])==f['p'] and 'DATABASE_URL' not in api.env
 child=retained_child_environment(f,monkeypatch,api.env['PLAYWRIGHT_BROWSERS_PATH']);assert child['environment']['PLAYWRIGHT_BROWSERS_PATH']==f['p']['browser_path'] and child['environment']['PLAYWRIGHT_BROWSERS_PATH']!='0'
 saved=vault.load();assert saved['render']['original']==original and saved['render']['original']['PLAYWRIGHT_BROWSERS_PATH']=='0'
 assert original['DATABASE_URL'].encode() not in (f['root']/'state.vault').read_bytes()
 saved['state']='DATABASE_CLOSURE_ACKNOWLEDGED';vault.save(saved) # synthetic DB boundary only
 result=io.restore_handoff(api,saved,vault.save,None)
 assert result['status']=='RESTORATION_VERIFIED' and result['submission_ack_timing']=='NO_JOB_VERIFIED' and api.env==original and api.puts==2

@pytest.mark.parametrize('change',['relative','malformed_hash','missing_field','wrong_limit','different_preexisting_profile'])
def test_owner_profile_guards_still_refuse_before_put(prepared,change):
 f=prepared
 if change=='relative':f['p']['browser_path']='relative'
 elif change=='malformed_hash':f['p']['browser_sha256']='BAD'
 elif change=='missing_field':f['p'].pop('browser_sha256')
 elif change=='wrong_limit':f['p']['source_seconds']=76
 else:f['api'].env['INGESTION_RENDER_PROFILE']='{}'
 f['obs']['binding_sha256']=hashlib.sha256(canonical(f['b'])).hexdigest()
 with pytest.raises(Denied):io.handoff(f['api'],f['state'],lambda _:None,'ghs_'+'SYNTHETIC_ONLY_'*5,observation=f['obs'])
 assert f['api'].puts==0 and 'render' not in f['state']

def test_legacy_literal_equality_remains(prepared):
 f=prepared;f['b']['timing_policy']['version']='SEPARATE_EXPIRY_V1';f['obs']['binding_sha256']=hashlib.sha256(canonical(f['b'])).hexdigest()
 with pytest.raises(Denied,match='EXACT_RENDER_PROFILE_FIELDS_AND_LIMITS'):io.handoff(f['api'],f['state'],lambda _:None,'ghs_'+'SYNTHETIC_ONLY_'*5,observation=f['obs'])
 assert f['api'].puts==0

@pytest.mark.parametrize('change',['executable_instead_of_directory','wrong_digest','missing_directory'])
def test_retained_runtime_directory_and_executable_hash_stay_strict(prepared,change):
 p=copy.deepcopy(prepared['p']);assert render.validate_profile(p)==p
 if change=='executable_instead_of_directory':p['browser_path']=str(next(Path(p['browser_path']).rglob('chrome-headless-shell')))
 elif change=='wrong_digest':p['browser_sha256']='0'*64
 else:p['browser_path']=str(prepared['root']/'not-a-browser-directory')
 with pytest.raises(Denied,match='RENDER_BROWSER_(PATH|HASH)'):render.validate_profile(p)

class StopAtSupervisor(Exception):pass

def retained_child_environment(f,monkeypatch,baseline):
 # SHA-check the imported implementation against the exact frozen application.
 frozen=Path('/home/maxrose26/stage4-owner/tameside-b-application-db05f5d/verification/ingestion_storage/daily_intake_runtime.py')
 assert hashlib.sha256(frozen.read_bytes()).hexdigest()=='2c5bd037763eadb431ca9ce98ca8a336648238f6c941c86696991ed9fd5796e4'
 assert Path(runtime.__file__).read_bytes()==frozen.read_bytes()
 monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH',baseline)
 @contextmanager
 def connection(**kw):yield object(),SimpleNamespace(check=lambda:None)
 self=SimpleNamespace(test=False,args=SimpleNamespace(disposable_sources=None),root=f['root'],connection=connection,policy_read=lambda _:None,run=SimpleNamespace(check=lambda:None),memory=None,policy={'render_profile':f['p']})
 seen={}
 def supervise(*args,**kw):seen.update(kw);raise StopAtSupervisor()
 monkeypatch.setattr(runtime,'supervise',supervise)
 with pytest.raises(StopAtSupervisor):runtime.Runtime.collect(self,{'council':'manchester','start':'2026-10-27','end':'2026-11-02','semantics':'VALIDATED'})
 return seen

@pytest.mark.parametrize('baseline',['0','/different/service/root'])
def test_actual_retained_collect_always_supplies_approved_child_directory(prepared,monkeypatch,baseline):
 f=prepared;seen=retained_child_environment(f,monkeypatch,baseline)
 assert seen['environment']=={'INGESTION_SOURCE_PRIVATE':'ONCE','PLAYWRIGHT_BROWSERS_PATH':f['p']['browser_path'],'INGESTION_RENDER_PROFILE':json.dumps(f['p'])}
 assert seen['render_profile']==f['p'] and seen['source'] is True and seen['seconds']==75 and seen['execution_budget']=='BROWSER_SOURCE_V2'
 monkeypatch.setattr(render,'memory_group',lambda:f['root']);monkeypatch.setattr(render,'memory_sample',lambda _:dict(**{'memory.max':2147483648}))
 with monkeypatch.context() as m:
  for name in list(render.os.environ):m.delenv(name)
  for name,value in seen['environment'].items():m.setenv(name,value)
  assert render.source_context(f['p']) is True
  m.setenv('PLAYWRIGHT_BROWSERS_PATH',baseline)
  with pytest.raises(Denied,match='RENDER_SOURCE_ENVIRONMENT'):render.source_context(f['p'])


def test_uncertain_handoff_remains_one_put(prepared):
 f=prepared;f['api'].fail_put=True
 with pytest.raises(RuntimeError):io.handoff(f['api'],f['state'],lambda _:None,'ghs_'+'SYNTHETIC_ONLY_'*5,observation=f['obs'])
 assert f['api'].puts==1 and f['state']['render']['state']=='PUT_INTENT_NO_RETRY'
 with pytest.raises(Denied,match='HANDOFF_SINGLE_USE'):io.handoff(f['api'],f['state'],lambda _:None,'ghs_'+'SYNTHETIC_ONLY_'*5,observation=f['obs'])
 assert f['api'].puts==1


def test_live_manchester_requires_approved_profile_before_source():
 with pytest.raises(Denied,match='ARCUS_INTAKE_EXECUTION_CONTEXT_UNSUPPORTED'):runtime.require_source_context({'manchester':{}},disposable=False,profile=None,binding=owner.APPLICATION_BINDING)


def test_retained_supervisor_passes_exact_child_env_to_popen(prepared,monkeypatch):
 from verification.ingestion_storage import operational_supervisor as supervisor
 f=prepared;seen=retained_child_environment(f,monkeypatch,'0');captured={}
 monkeypatch.setenv('GH_TOKEN','SYNTHETIC_OWNER_SECRET_NEVER_IN_CHILD')
 monkeypatch.setattr(render,'OwnedSubreaper',lambda:SimpleNamespace(close=lambda:None))
 def intercepted(command,**kw):captured.update(kw);raise RuntimeError('SYNTHETIC_STOP_BEFORE_PROCESS_CREATION')
 monkeypatch.setattr(supervisor.subprocess,'Popen',intercepted)
 result=supervisor.supervise(['SYNTHETIC_NOT_EXECUTED'],environment=seen['environment'],root=f['root']/'owned-supervisor',seconds=75,source=True,execution_budget='BROWSER_SOURCE_V2',render_profile=f['p'])
 assert captured['env']['PLAYWRIGHT_BROWSERS_PATH']==f['p']['browser_path'] and 'GH_TOKEN' not in captured['env'] and not any('DATABASE' in k for k in captured['env'])
 assert result['cleanup']=='UNCERTAIN' and result['retry'] is False # intentionally no child/closure proof fabricated


def test_runtime_guard_source_bytes_equal_frozen_artifact():
 from verification.ingestion_storage import operational_supervisor as supervisor
 root=Path('/home/maxrose26/stage4-owner/tameside-b-application-db05f5d/verification/ingestion_storage')
 for module in [runtime,render,supervisor]:assert Path(module.__file__).read_bytes()==(root/Path(module.__file__).name).read_bytes()
