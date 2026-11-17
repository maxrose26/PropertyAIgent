"""Offline pinned provider adapter: no network, fixture secrets only."""
import ast,copy,json,os,time
from pathlib import Path
from types import SimpleNamespace
import pytest
from verification.ingestion_storage.tameside_owner_access import provider_io
from verification.ingestion_storage.operational_owner import ROLES


def setup(tmp_path):
 root=os.environ.get('S4_BOLTON_PINNED_CHECKOUT')
 if not root:pytest.skip('pinned #213 checkout required')
 checks=[]
 def validate(b,**kw):
  assert b['period']=='S4_FINITE_677f555670666bcf21f45860'
  checks.append(kw)
 io=provider_io(root,SimpleNamespace(validate_binding=validate))
 scope=dict(copy=copy,json=json,time=time,ROLES=ROLES,SERVICE='crn-d9sv93vavr4c73f98rb0',service_guard=io.service_guard)
 source=(Path(root)/'tests/test_intake_owner_io.py').read_text()
 for n in ast.parse(source).body:
  if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in ('API','prepared'):
   exec(compile(ast.get_source_segment(source,n),'pinned-fixtures','exec'),scope)
 api=scope['API']();state=scope['prepared'](api);b=state['binding']
 # The pinned #213 browser fixture must not silently enter HTTP-only Tameside.
 b.pop('render_profile',None)
 api.env.pop('PLAYWRIGHT_BROWSERS_PATH',None)
 api.env.pop('INGESTION_RENDER_PROFILE',None)
 b.update(period='S4_FINITE_677f555670666bcf21f45860',evidence_backend='POSTGRES_PILOT_V1',
          timing_policy=dict(version='SEPARATE_EXPIRY_V2_RESERVE',bound_at=time.time()),
          release_root=str(tmp_path),submission_intent_path=str(tmp_path/'intent'),retained_deployment='dep-fixture')
 def observation(op):
  import hashlib
  from verification.ingestion_storage.operational_publication import canonical
  return dict(version='FINITE_OPERATION_OBSERVATION_V1',operation=op,binding_sha256=hashlib.sha256(canonical(b)).hexdigest(),service_id=scope['SERVICE'],observed_at=time.time(),env_groups=[],secret_files=[],inherited_credential_names=[],reviewed=True,no_current_work=True,other_activity_stopped=True,deployment_id='dep-fixture',revision=b['execution_binding']['revision'],suspended=True)
 return io,api,state,observation,checks


def test_handoff_submission_and_independent_restore(tmp_path):
 io,api,state,obs,checks=setup(tmp_path);original=copy.deepcopy(api.env);saved=[]
 save=lambda x:saved.append(copy.deepcopy(x))
 io.handoff(api,state,save,None,observation=obs('HANDOFF'))
 assert 'DATABASE_URL' not in api.env and 'OTHER_SECRET' not in api.env
 assert 'PLAYWRIGHT_BROWSERS_PATH' not in api.env and 'INGESTION_RENDER_PROFILE' not in api.env
 assert set(k for k in api.env if 'DATABASE' in k)=={'INGESTION_WORKER_DATABASE_URL','INGESTION_EFFECT_DATABASE_URL'}
 io.submission_check(api,state,save,obs('SUBMISSION'))
 with pytest.raises(Exception,match='SUBMISSION_PRIOR_INTENT_NO_RETRY'):io.submission_check(api,state,save,obs('SUBMISSION'))
 assert (tmp_path/'intent').exists() and len(checks)>=4
 state['state']='DATABASE_CLOSURE_ACKNOWLEDGED'
 io.restore_handoff(api,state,save,None)
 assert api.env==original


def test_lost_handoff_ack_reconciles_without_repeat(tmp_path):
 io,api,state,obs,_=setup(tmp_path);api.fail_put=True
 with pytest.raises(RuntimeError):io.handoff(api,state,lambda _:None,None,observation=obs('HANDOFF'))
 assert io.reconcile_handoff(api,state,lambda _:None)['observed']=='EXPECTED'
 with pytest.raises(Exception,match='HANDOFF_SINGLE_USE'):io.handoff(api,state,lambda _:None,None,observation=obs('HANDOFF'))
 assert api.puts==1

def test_stale_browser_profile_fails_before_any_provider_write(tmp_path):
 io,api,state,obs,_=setup(tmp_path)
 state['binding']['render_profile']={'revision':'old'}
 with pytest.raises(Exception,match='TAMESIDE_HTTP_PROFILE_NOT_PERMITTED'):
  io.handoff(api,state,lambda _:None,None,observation=obs('HANDOFF'))
 assert api.puts==0 and 'render' not in state


def test_old_browser_env_is_not_inherited_and_is_restored(tmp_path):
 io,api,state,obs,_=setup(tmp_path)
 api.env['PLAYWRIGHT_BROWSERS_PATH']='0'
 api.env['INGESTION_RENDER_PROFILE']='untrusted-stale-profile'
 original=copy.deepcopy(api.env)
 io.handoff(api,state,lambda _:None,None,observation=obs('HANDOFF'))
 assert 'PLAYWRIGHT_BROWSERS_PATH' not in api.env
 assert 'INGESTION_RENDER_PROFILE' not in api.env
 state['state']='DATABASE_CLOSURE_ACKNOWLEDGED'
 io.restore_handoff(api,state,lambda _:None,None)
 assert api.env==original
