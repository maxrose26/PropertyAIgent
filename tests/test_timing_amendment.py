"""Synthetic/mocked timing amendment only; no provider or PostgreSQL connection."""
import copy,json,hashlib,subprocess,os
from pathlib import Path
from datetime import datetime,timezone
import pytest
from verification.ingestion_storage import intake_owner as op,intake_owner_operations as extra,intake_owner_io as io,intake_owner_client as client,publication_mint as mint,finite_release_binding as flow
from verification.ingestion_storage.operational_publication import canonical
from tests.test_intake_owner_io import API
from tests.test_intake_owner_operations import mocked_sql,issue,KEY,TOKEN

@pytest.fixture
def v2(tmp_path,monkeypatch):
 root=tmp_path/'release';private=tmp_path/'private';root.mkdir(mode=0o700);private.mkdir(mode=0o700)
 monkeypatch.setattr(client.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(client.sys.stderr,'isatty',lambda:True)
 s=json.loads(Path('/home/maxrose26/stage4-owner/b-successor-release-20261103/STATIC-RELEASE.json').read_bytes());s['version']='FINITE_TIMING_V2_STATIC'
 s['binding_fields'].update(period_vault_path=str(private/'period.vault'),publication_vault_path=str(private/'publication-01.vault'))
 s['access_vault']=str(private/'access.vault');s['mint_journal_path']=str(private/mint.SUCCESSOR_JOURNAL)
 clock=[1793706638.0];monkeypatch.setattr(flow.time,'time',lambda:clock[0]);monkeypatch.setattr(flow,'ROOT',root);monkeypatch.setattr(flow,'PRIVATE',private);monkeypatch.setattr(mint,'ROOT',private);monkeypatch.setattr(flow,'static',lambda:s)
 api=API();api.env.pop('INGESTION_RENDER_PROFILE');api.env['PLAYWRIGHT_BROWSERS_PATH']=s['binding_fields']['render_profile']['browser_path'];s['binding_fields']['render_config_sha256']=io.service_guard(api.service)
 E=clock[0]+3600;r=dict(status='MINT_RECEIPT_VALIDATED_NOT_ARMED',mint_outcome='MINTED',retry=False,authority_sha256=flow.AUTHORITY,receipt_sha256='b'*64,expiry=E,expires_at=datetime.fromtimestamp(E,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),owner_process=dict(client_closed=True,exit_code=0,reason=None))
 def put(path,value):path=Path(path);path.parent.mkdir(mode=0o700,parents=True,exist_ok=True);path.write_bytes(canonical(value));path.chmod(0o600);return path
 result=put(private/'result.json',r);monkeypatch.setattr(flow,'MINT_RESULT',result)
 b,p=flow.build_v2(s,r,clock[0]);bh=hashlib.sha256(canonical(b)).hexdigest();ph=hashlib.sha256(canonical(p)).hexdigest();mh=hashlib.sha256(result.read_bytes()).hexdigest()
 proof=dict(binding_path=str(root/'owner-binding.json'),binding_sha256=bh,policy_path=str(root/'period-policy.json'),policy_sha256=ph,mint_result_sha256=mh,receipt_sha256=r['receipt_sha256'],expiry=E,access_deadline=b['valid_until'],bound_at=clock[0])
 for name,value in [('owner-binding.json',b),('period-policy.json',p),('FROZEN.json',proof),('ACTUAL-MINT-REVIEW.json',dict(mint_result_sha256=mh,receipt_sha256=r['receipt_sha256'],expiry=E))]:put(root/name,value)
 return dict(root=root,private=private,s=s,clock=clock,r=r,b=b,p=p,put=put,api=api,bh=bh)

def observation(f,operation='HANDOFF'):
 b=f['b'];return dict(version='FINITE_OPERATION_OBSERVATION_V1',operation=operation,binding_sha256=hashlib.sha256(canonical(b)).hexdigest(),service_id=io.SERVICE,observed_at=f['clock'][0],env_groups=[],secret_files=[],inherited_credential_names=[],reviewed=True,no_current_work=True,other_activity_stopped=True,deployment_id=b['retained_deployment'],revision=b['execution_binding']['revision'],suspended=True)
def state(f):return dict(state='ACTIVATION_ACKNOWLEDGED',binding=f['b'],passwords={r:'SYNTHETIC_PASSWORD_'+'x'*48 for r in op.ROLES})

def test_fresh_hour_token_binds_immediately_without_ageing_and_never_slides(v2):
 f=v2;b=f['b'];assert b['valid_until']==f['clock'][0]+2100 and b['publication_valid_until']==f['clock'][0]+3600 and f['p']['expires_at']==b['runtime_deadline']==b['valid_until']-185
 f['clock'][0]+=500;got,_,_=flow.frozen_binding();assert got==b and got['timing_policy']['bound_at']==b['timing_policy']['bound_at']
 assert 'inherited_boundary' not in b

@pytest.mark.parametrize('remaining,ok',[(2100,True),(2099,False)])
def test_token_full_35_minute_boundary(v2,remaining,ok):
 f=v2;r=copy.deepcopy(f['r']);r['expiry']=f['clock'][0]+remaining;r['expires_at']=datetime.fromtimestamp(r['expiry'],timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
 if ok:assert flow.build_v2(f['s'],r,f['clock'][0])[0]['valid_until']==r['expiry']
 else:
  with pytest.raises(flow.PreparationError,match='FULL_35_MINUTE_MARGIN_REQUIRED'):flow.build_v2(f['s'],r,f['clock'][0])

@pytest.mark.parametrize('seconds_before_midnight,ok',[(2100,True),(2099,False)])
def test_day_full_35_minute_boundary(v2,seconds_before_midnight,ok):
 f=v2;t=datetime(2026,11,4,tzinfo=timezone.utc).timestamp()-seconds_before_midnight;r=copy.deepcopy(f['r']);r['expiry']=t+3600;r['expires_at']=datetime.fromtimestamp(r['expiry'],timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
 if ok:flow.build_v2(f['s'],r,t)
 else:
  with pytest.raises(flow.PreparationError,match='FULL_35_MINUTE_MARGIN_REQUIRED'):flow.build_v2(f['s'],r,t)

@pytest.mark.parametrize('elapsed,ok',[(599.999,True),(600,False),(601,False),(-1,False)])
def test_strict_ten_minute_setup_and_more_than_25_at_submission(v2,elapsed,ok):
 f=v2
 if ok:op.validate_binding(f['b'],opening=True,now=f['clock'][0]+elapsed)
 else:
  with pytest.raises(op.Denied):op.validate_binding(f['b'],opening=True,now=f['clock'][0]+elapsed)

@pytest.mark.parametrize('change',['D_slide','E_change','receipt_change','fixed_proof'])
def test_deadline_receipt_and_frozen_proof_cannot_be_rebound(v2,change):
 f=v2;b=copy.deepcopy(f['b'])
 if change=='D_slide':b['valid_until']+=1
 elif change=='E_change':b['publication_valid_until']-=1
 elif change=='receipt_change':b['publication_mint']['receipt_sha256']='c'*64
 else:
  p=f['root']/'FROZEN.json';x=json.loads(p.read_bytes());x['bound_at']+=1;f['put'](p,x)
 if change!='fixed_proof':f['put'](f['root']/'owner-binding.json',b)
 with pytest.raises((flow.PreparationError,op.Denied)):flow.frozen_binding()


def test_operation_observations_are_immutable_local_and_do_not_change_D(v2,monkeypatch):
 f=v2;before=(f['root']/'owner-binding.json').read_bytes();monkeypatch.setattr('builtins.input',lambda _:'CONFIRM_FRESH_HANDOFF_OBSERVATION_NOW')
 assert flow.record_observation('HANDOFF')['deadline']==f['b']['valid_until']
 with pytest.raises(flow.PreparationError,match='OBSERVATION_ALREADY_RECORDED'):flow.record_observation('HANDOFF')
 assert (f['root']/'owner-binding.json').read_bytes()==before

@pytest.mark.parametrize('change',['stale','future','wrong_operation','wrong_binding','groups','wrong_artifact'])
def test_stale_wrong_operation_and_drift_refuse_before_provider(v2,change):
 f=v2;x=observation(f)
 if change=='stale':x['observed_at']-=301
 elif change=='future':x['observed_at']+=1
 elif change=='wrong_operation':x['operation']='SUBMISSION'
 elif change=='wrong_binding':x['binding_sha256']='0'*64
 elif change=='groups':x['env_groups']=['unexpected']
 else:x['deployment_id']='different'
 with pytest.raises(op.Denied):io.handoff(f['api'],state(f),lambda _:None,TOKEN,observation=x)
 assert f['api'].calls==0 and f['api'].puts==0


def test_handoff_observation_expiring_during_reads_refuses_before_intent(v2):
 f=v2;api=f['api'];call=api.call;x=observation(f);saved=[]
 def read(*a,**kw):
  v=call(*a,**kw)
  if api.calls==2:f['clock'][0]+=301
  return v
 api.call=read
 with pytest.raises(op.Denied):io.handoff(api,state(f),saved.append,TOKEN,observation=x)
 assert api.puts==0 and not saved


def test_uncertain_handoff_is_not_repeated_and_get_only_reconciliation(v2):
 f=v2;api=f['api'];api.fail_put=True;s=state(f);x=observation(f)
 with pytest.raises(RuntimeError):io.handoff(api,s,lambda _:None,TOKEN,observation=x)
 with pytest.raises(op.Denied):io.handoff(api,s,lambda _:None,TOKEN,observation=x)
 assert io.reconcile_handoff(api,s,lambda _:None)['observed']=='EXPECTED' and api.puts==1


def test_separate_fresh_submission_checks_and_one_intent(v2):
 f=v2;s=state(f);io.handoff(f['api'],s,lambda _:None,TOKEN,observation=observation(f));f['clock'][0]+=60
 with pytest.raises(op.Denied):io.submission_check(f['api'],s,lambda _:None,observation(f,'HANDOFF'))
 x=observation(f,'SUBMISSION');r=io.submission_check(f['api'],s,lambda _:None,x)
 assert r['latest_submission_exclusive']==f['b']['valid_until']-1500 and f['api'].puts==1
 before=f['api'].calls
 with pytest.raises(op.Denied):io.submission_check(f['api'],s,lambda _:None,x)
 assert f['api'].calls==before and (f['root']/'submission.intent.json').exists()


def test_submission_drift_has_no_intent_and_no_second_handoff(v2):
 f=v2;s=state(f);io.handoff(f['api'],s,lambda _:None,TOKEN,observation=observation(f));f['api'].env['UNEXPECTED']='synthetic'
 with pytest.raises(op.Denied):io.submission_check(f['api'],s,lambda _:None,observation(f,'SUBMISSION'))
 assert not (f['root']/'submission.intent.json').exists() and f['api'].puts==1


def test_independent_restore_and_exact_token_revoke_after_E_and_stale_obs(v2):
 f=v2;s=state(f);original=copy.deepcopy(f['api'].env);io.handoff(f['api'],s,lambda _:None,TOKEN,observation=observation(f))
 s['state']='DATABASE_CLOSURE_ACKNOWLEDGED';f['clock'][0]=f['r']['expiry']+1
 result=io.restore_handoff(f['api'],s,lambda _:None,'job-'+'a'*20)
 assert result['status']=='RESTORATION_VERIFIED' and result['submission_ack_timing']=='UNKNOWN' and f['api'].env==original
 box=[];extra.token_arm(f['b'],TOKEN,lambda x:box.append(copy.deepcopy(x)));calls=[]
 def runner(*a,**kw):calls.append(kw['env']['GH_TOKEN'] if 'env' in kw else None);return subprocess.CompletedProcess(a,0,b'HTTP/2.0 204 OK\n',b'')
 stale=copy.deepcopy(box[-1]);extra.token_revoke(f['b'],box[-1],lambda _:None,runner=runner)
 assert len(calls)==1
 with pytest.raises(op.Denied):extra.token_revoke(f['b'],box[-1],lambda _:None,runner=runner)
 with pytest.raises(FileExistsError):extra.token_revoke(f['b'],stale,lambda _:None,runner=runner)


def test_period_issuer_uses_P_below_D_and_preserves_memberships(v2,mocked_sql):
 f=v2;c=mocked_sql;prior=list(c.members);_,_,call=issue(c,f['b'],f['p']);r=call()
 assert r['outcome']=='COMMIT_ACKNOWLEDGED' and c.members==prior and c.ctl['intake_periods'][f['b']['period']]['expires_at']==f['b']['runtime_deadline']==f['b']['valid_until']-185<f['r']['expiry']


def test_issuer_server_clock_ten_minute_boundary_rolls_back(v2,mocked_sql):
 f=v2;c=mocked_sql;f['clock'][0]+=600;before=copy.deepcopy((c.ctl,c.members))
 _,_,call=issue(c,f['b'],f['p'])
 with pytest.raises(op.Denied):call()
 assert c.commits==0 and (c.ctl,c.members)==before


def test_memory_reuse_only_allowed_credentials_and_clear_on_interruption(monkeypatch):
 entered=[];sentinel='SYNTHETIC_SECRET_NO_LOGGING'
 def inputter(prompt,**kw):entered.append(prompt);return sentinel
 monkeypatch.setattr(client,'private_input',inputter)
 cache=None
 with pytest.raises(KeyboardInterrupt):
  with client.AttendedCredentials() as memory:
   cache=memory
   for _ in range(3):
    assert client.private_input('PropertyAIgent — Supabase postgres password (hidden): ')==sentinel
    assert client.private_input('PropertyAIgent — Render API key (hidden): ')==sentinel
   client.private_input('PropertyAIgent — GitHub signing-key passphrase (hidden): ')
   client.private_input('PropertyAIgent — GitHub signing-key passphrase (hidden): ')
   assert set(memory.values)=={'postgres','render'};raise KeyboardInterrupt
 assert len(entered)==4 and cache.values=={} and client.private_input is inputter


def test_cache_expiry_reprompts_and_closure_not_opening_bound(v2,monkeypatch):
 f=v2;asked=[];monkeypatch.setattr(client,'private_input',lambda prompt,**kw:asked.append(prompt) or 'synthetic')
 with client.AttendedCredentials(KEY) as memory:
  memory.expires_at=f['r']['expiry'];f['clock'][0]=memory.expires_at+1
  client.private_input('PropertyAIgent — Render API key (hidden): ')
  assert memory.values=={} and len(asked)==1
 op.validate_binding(f['b'],opening=False)
 with pytest.raises(op.Denied):op.validate_binding(f['b'],opening=True)

@pytest.mark.parametrize('created,expected',[(0,'WITHIN_APPROVED_DEADLINE'),(599,'WITHIN_APPROVED_DEADLINE'),(600,'OUTSIDE_APPROVED_DEADLINE'),(-1,'OUTSIDE_APPROVED_DEADLINE')])
def test_actual_provider_submission_ack_deadline_informs_acceptance(v2,created,expected):
 f=v2;j=dict(createdAt=datetime.fromtimestamp(f['b']['timing_policy']['bound_at']+created,timezone.utc).isoformat())
 assert io.submission_ack_timing(f['b'],j)==expected

def test_actual_seal_preserves_E_and_D_and_exact_token_identity(v2):
 f=v2;a=json.loads(Path('/home/maxrose26/stage4-owner/b-github-get-readonly-20261103/authority-client-id-corrected.json').read_bytes());h=hashlib.sha256(canonical(a)).hexdigest()
 r=mint.receipt(dict(token=TOKEN,permissions=mint.PERMISSIONS,repository_selection='selected',repositories=[dict(id=mint.REPOSITORY_ID,full_name=mint.REPOSITORY)],expires_at=f['r']['expires_at']),f['clock'][0],f['clock'][0],h)
 rh=hashlib.sha256(canonical(r)).hexdigest();b=copy.deepcopy(f['b']);b['publication_mint']['receipt_sha256']=rh
 io.Vault(f['private']/mint.SUCCESSOR_JOURNAL,KEY,create=True).save(dict(version='ONE_B_MINT_V1',authority=a,authority_sha256=h,state='RECEIPT_VALIDATED_NOT_ARMED',receipt=r,receipt_sha256=rh,token_candidate=TOKEN))
 result=mint.seal(a,h,b,KEY,clock=lambda:f['clock'][0],successor=True)
 assert result['status']=='PRIVATE_PUBLICATION_TOKEN_ARMED'
 saved=io.Vault(Path(b['publication_vault_path']),KEY).load();assert saved['binding']==b and extra.token_load(b,saved)==TOKEN and b['valid_until']<r['expiry']


def test_memory_expiry_timer_clears_cache_without_disabling_closure(v2,monkeypatch):
 handlers=[];timers=[]
 monkeypatch.setattr(client.signal,'getitimer',lambda *_:(0.0,0.0));monkeypatch.setattr(client.signal,'getsignal',lambda *_:'prior')
 monkeypatch.setattr(client.signal,'signal',lambda sig,fn:handlers.append(fn));monkeypatch.setattr(client.signal,'setitimer',lambda *args:timers.append(args))
 with client.AttendedCredentials(KEY) as memory:
  memory.arm_expiry(v2['r']['expiry']);assert memory.values
  handlers[0]();assert memory.values=={}
 assert handlers[-1]=='prior' and timers[-1][1]==0


def test_known_unknown_diagnostics_do_not_expose_secrets():
 sentinel='PRIVATE_SENTINEL_'*400
 for exc in [op.Denied('OPERATION_OBSERVATION_STALE'),RuntimeError(sentinel)]:
  out=client.failure_output('submission-check',exc);assert len(out.encode())<=client.DIAGNOSTIC_BYTES and sentinel not in out
 assert 'OPERATION_OBSERVATION_STALE' in client.failure_output('handoff',op.Denied('OPERATION_OBSERVATION_STALE'))
 assert 'UNKNOWN_FAILURE' in client.failure_output('handoff',RuntimeError(sentinel))

def test_attended_actual_parents_order_pipes_and_memory_reuse(v2,monkeypatch,capsys):
 monkeypatch.setattr(client.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(client.sys.stderr,'isatty',lambda:True)
 from tests.test_phase_order_preparation import sealed
 from types import SimpleNamespace
 f=v2;sealed(f);io.Vault(f['private']/'mint-01.vault',KEY,create=True).save(dict(fixture=True))
 target=io.Vault(Path(f['b']['publication_vault_path']),KEY,create=True);extra.token_arm(f['b'],TOKEN,target.save)
 f['api'].session=SimpleNamespace(close=lambda:None);monkeypatch.setattr(io,'Render',lambda token:f['api'])
 actions=iter(['next']*7+['exit']);entered=[];calls=[]
 def answer(prompt):
  if prompt.startswith('Attended action'):return next(actions)
  if prompt.startswith('CONFIRM_FRESH_'):return prompt.split(':')[0]
  if 'EXECUTE_EXACT_' in prompt:return prompt.split('(')[1].split(')')[0]
  raise AssertionError('unexpected nonsensitive prompt')
 monkeypatch.setattr('builtins.input',answer)
 def hidden(prompt):entered.append(prompt);return 'SYNTHETIC_OWNER_PASSWORD' if 'Supabase' in prompt else 'SYNTHETIC_RENDER_KEY'
 monkeypatch.setattr(client,'hidden',hidden)
 def capture(cmd,env,**kw):
  phase=cmd[cmd.index('--phase')+1];calls.append(phase);secret=json.loads(os.read(kw['pass_fds'][0],4096));assert 'GH_TOKEN' not in env and set(env)=={'PATH','HOME','LANG','PYTHONDONTWRITEBYTECODE','OPENBLAS_NUM_THREADS'}
  if phase=='period':
   io.Vault(Path(f['b']['period_vault_path']),KEY,create=True).save(dict(binding=f['b']))
   value=dict(outcome='COMMIT_ACKNOWLEDGED',period=f['b']['period'],policy_sha256=f['b']['period_policy_sha256'],temporary_issuer='REMOVED',original_memberships='PRESERVED',readback='EXACT_ON_SAME_CONNECTION',connections=1)
  elif phase=='activate':
   io.Vault(Path(f['s']['access_vault']),KEY,create=True).save(state(f));value=dict(outcome='COMMIT_ACKNOWLEDGED',runtime_roles=sorted(op.ROLES),credentials='ENCRYPTED_LOCAL_ONLY',valid_until=f['b']['valid_until'])
  elif phase=='qualify':value=dict(status='TWO_SINGLE_ATTEMPT_RESTRICTED_AUTHENTICATIONS_CLOSED',roles=[dict(role=n,attempts=1,closed=True) for n in sorted(op.ROLES)])
  else:
   obs=flow.private_json(Path(cmd[cmd.index('--expected')+1]),'OPERATION_OBSERVATION_REQUIRED')
   value=client.worker(phase,f['b'],secret,f['s']['access_vault'],obs)
  raw=canonical(value);return raw,dict(exit_code=0,reason=None,client_closed=True,output_bytes=len(raw))
 monkeypatch.setattr(client,'capture',capture)
 assert client.attended_session(vault_password=KEY)==2
 assert calls==['period','activate','qualify','handoff','submission-check'] and len(entered)==2
 assert (f['root']/'handoff-observation.json').exists() and (f['root']/'submission-observation.json').exists()
 out=capsys.readouterr();assert all(x not in out.out+out.err for x in [KEY,'SYNTHETIC_OWNER_PASSWORD','SYNTHETIC_RENDER_KEY'])
 assert f['api'].puts==1


def test_uncertain_phase_stops_session_progress_and_clears_memory(v2,monkeypatch,capsys):
 monkeypatch.setattr(client.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(client.sys.stderr,'isatty',lambda:True)
 from tests.test_phase_order_preparation import sealed
 f=v2;sealed(f);io.Vault(f['private']/'mint-01.vault',KEY,create=True).save(dict(fixture=True));actions=iter(['next','next','exit']);calls=[];boxes=[]
 base=client.AttendedCredentials
 class Observed(base):
  def __enter__(self):boxes.append(self);return super().__enter__()
 monkeypatch.setattr(client,'AttendedCredentials',Observed)
 monkeypatch.setattr('builtins.input',lambda p:next(actions) if p.startswith('Attended action') else 'EXECUTE_EXACT_PERIOD_ONCE')
 monkeypatch.setattr(client,'hidden',lambda p:'SYNTHETIC_OWNER_PASSWORD')
 def capture(cmd,env,**kw):
  os.read(kw['pass_fds'][0],4096);calls.append(cmd);return b'{}',dict(exit_code=2,reason='DEADLINE',client_closed=True,output_bytes=2)
 monkeypatch.setattr(client,'capture',capture)
 assert client.attended_session(vault_password=KEY)==2 and len(calls)==1 and boxes[0].values=={}
 assert 'OPENING_STOPPED' in capsys.readouterr().out


def test_interrupted_session_clears_cache_and_keeps_independent_closure_binding(v2,monkeypatch):
 f=v2;boxes=[];base=client.AttendedCredentials
 class Observed(base):
  def __enter__(self):boxes.append(self);return super().__enter__()
 monkeypatch.setattr(client,'AttendedCredentials',Observed)
 def interrupt(_):raise KeyboardInterrupt
 monkeypatch.setattr('builtins.input',interrupt)
 with pytest.raises(KeyboardInterrupt):client.attended_session(vault_password=KEY)
 assert boxes[0].values=={};f['clock'][0]=f['r']['expiry']+1;op.validate_binding(f['b'],opening=False)


def test_stale_observation_refuses_in_parent_before_hidden_input_or_child(v2,monkeypatch,capsys):
 f=v2;x=observation(f);x['observed_at']-=301;path=f['put'](f['root']/'obs.json',x)
 monkeypatch.setattr(client.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(client.sys.stderr,'isatty',lambda:True)
 monkeypatch.setattr('builtins.input',lambda _:'EXECUTE_EXACT_HANDOFF_ONCE')
 monkeypatch.setattr(client,'hidden',lambda _:pytest.fail('no credentials'))
 assert client.main(['--phase','handoff','--binding',str(f['root']/'owner-binding.json'),'--binding-sha256',f['bh'],'--vault',f['s']['access_vault'],'--expected',str(path),'--expected-sha256',hashlib.sha256(path.read_bytes()).hexdigest(),'--evidence',str(f['root']/'handoff-evidence')])==2
 assert 'OPERATION_OBSERVATION_STALE' in capsys.readouterr().out and not (f['root']/'handoff-evidence').exists()

def test_actual_owner_launcher_entry_checks_full_args_and_uses_mocked_phase(v2,monkeypatch,capsys):
 from tests.test_phase_order_preparation import sealed
 import shlex
 f=v2;sealed(f);io.Vault(f['private']/'mint-01.vault',KEY,create=True).save(dict(fixture=True));monkeypatch.setattr(flow,'use_timing_release',lambda:None)
 monkeypatch.setattr(client.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(client.sys.stderr,'isatty',lambda:True)
 monkeypatch.setattr('builtins.input',lambda _:'EXECUTE_EXACT_PERIOD_ONCE');monkeypatch.setattr(client,'hidden',lambda p:KEY if 'Vault' in p else 'SYNTHETIC_OWNER')
 calls=[]
 def capture(cmd,env,**kw):
  secret=json.loads(os.read(kw['pass_fds'][0],4096));assert secret['vault_key']==KEY;calls.append(cmd)
  value=dict(outcome='COMMIT_ACKNOWLEDGED',period=f['b']['period'],policy_sha256=f['b']['period_policy_sha256'],temporary_issuer='REMOVED',original_memberships='PRESERVED',readback='EXACT_ON_SAME_CONNECTION',connections=1)
  raw=canonical(value);return raw,dict(exit_code=0,reason=None,client_closed=True,output_bytes=len(raw))
 monkeypatch.setattr(client,'capture',capture)
 _,cmd=flow.next_command();args=shlex.split(cmd)[2:]
 assert client.main(['--launch',*args,'--phase','activate'])==2 and not calls
 assert client.main(['--launch',*args])==0 and len(calls)==1
 assert KEY not in capsys.readouterr().out


def test_actual_seal_launcher_entry_uses_fixed_D_and_mocked_child(v2,monkeypatch,capsys):
 import shlex
 f=v2;monkeypatch.setattr(flow,'use_timing_release',lambda:None)
 monkeypatch.setattr(mint.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(mint.sys.stderr,'isatty',lambda:True)
 monkeypatch.setattr('builtins.input',lambda _:'SEAL_EXACT_B_PUBLICATION_TOKEN_ONCE');monkeypatch.setattr(client,'vault_input',lambda _:KEY)
 calls=[]
 def capture(cmd,env,**kw):
  secret=json.loads(os.read(kw['pass_fds'][0],4096));assert secret['vault_password']==KEY and secret['key_password'] is None;calls.append(cmd)
  raw=canonical(dict(status='PRIVATE_PUBLICATION_TOKEN_ARMED',mint_outcome='MINTED',receipt_sha256=f['r']['receipt_sha256'],provider_calls=0,retry=False))
  return raw,dict(exit_code=0,reason=None,client_closed=True,output_bytes=len(raw))
 monkeypatch.setattr(client,'capture',capture)
 _,cmd=flow.next_command();args=shlex.split(cmd)[2:]
 assert mint.main(['--launch',*args])==0 and len(calls)==1
 assert '--timing-v2' in calls[0] and KEY not in capsys.readouterr().out


def test_actual_owner_session_launcher_entry_unbound_before_credentials(monkeypatch,capsys):
 def unbound():raise flow.PreparationError('TIMING_RELEASE_UNBOUND')
 monkeypatch.setattr(flow,'use_timing_release',unbound);monkeypatch.setattr(client,'hidden',lambda _:pytest.fail('no secret input'))
 assert client.main(['--launch','--session'])==2 and 'TIMING_RELEASE_UNBOUND' in capsys.readouterr().out

def test_repeated_bind_never_slides_deadline_or_requests_new_credentials(v2,monkeypatch,capsys):
 f=v2;monkeypatch.setattr(client.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(client.sys.stderr,'isatty',lambda:True)
 actions=iter(['bind','exit']);monkeypatch.setattr('builtins.input',lambda _:next(actions));monkeypatch.setattr(client,'hidden',lambda _:pytest.fail('no reentry'))
 before=(f['root']/'owner-binding.json').read_bytes();f['clock'][0]+=100
 assert client.attended_session(vault_password=KEY)==2
 assert before==(f['root']/'owner-binding.json').read_bytes() and 'NO_REBIND' in capsys.readouterr().out


def test_v2_freeze_mode_cannot_reintroduce_token_ageing(v2,capsys):
 assert flow.main(['freeze'])==2 and 'USE_BIND_FOR_SEPARATE_EXPIRY' in capsys.readouterr().out


def test_v2_bind_records_D_once_after_confirmation_not_before_input(v2,monkeypatch,capsys):
 f=v2
 for n in ('owner-binding.json','period-policy.json','FROZEN.json'):(f['root']/n).unlink()
 monkeypatch.setattr(flow.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(flow.sys.stderr,'isatty',lambda:True)
 def confirm(_):f['clock'][0]+=120;return 'BIND_EXACT_35_MINUTE_RELEASE'
 monkeypatch.setattr('builtins.input',confirm)
 assert flow.main(['bind'])==0
 b=json.loads((f['root']/'owner-binding.json').read_bytes());assert b['valid_until']==f['clock'][0]+2100 and b['publication_valid_until']==f['r']['expiry']
 assert flow.main(['bind'])==2


def test_submission_lost_local_ack_cannot_create_second_intent(v2):
 f=v2;s=state(f);io.handoff(f['api'],s,lambda _:None,TOKEN,observation=observation(f))
 def lost(_):raise RuntimeError('SYNTHETIC_LOST_LOCAL_ACK')
 with pytest.raises(RuntimeError):io.submission_check(f['api'],s,lost,observation(f,'SUBMISSION'))
 original=(f['root']/'submission.intent.json').read_bytes()
 with pytest.raises(op.Denied):io.submission_check(f['api'],s,lambda _:None,observation(f,'SUBMISSION'))
 assert (f['root']/'submission.intent.json').read_bytes()==original and f['api'].puts==1

# Existing synthetic-key/transport fixtures only; this never mints a real token.
from tests.test_publication_mint import fx,synthetic_key
from tests.test_corrected_issuer_mint import corrected
from tests.test_expired_unused_successor import successor

@pytest.mark.parametrize('session_failure',[False,True])
def test_mint_continuation_drops_signer_references_and_reuses_only_vault(successor,monkeypatch,capsys,session_failure):
 import inspect
 from tests.test_publication_mint import PASSWORD,VAULT
 from tests.test_expired_unused_successor import run
 f=successor;monkeypatch.setattr(mint.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(mint.sys.stderr,'isatty',lambda:True)
 monkeypatch.setattr('builtins.input',lambda _:'EXECUTE_ONE_SUCCESSOR_AFTER_EXPIRED_UNUSED_MINT')
 entered=iter([VAULT,PASSWORD]);monkeypatch.setattr(client,'hidden',lambda _:next(entered));seen=[]
 def capture(cmd,env,**kw):
  secret=json.loads(os.read(kw['pass_fds'][0],4096));assert secret==dict(vault_password=VAULT,key_password=PASSWORD)
  raw=canonical(run(f));return raw,dict(exit_code=0,reason=None,client_closed=True,output_bytes=len(raw))
 monkeypatch.setattr(client,'capture',capture)
 def session(**kw):
  frame=inspect.currentframe().f_back
  assert frame.f_locals['key_password'] is None and frame.f_locals['secrets_raw'] is None and kw==dict(vault_password=VAULT)
  seen.append(True)
  if session_failure:raise RuntimeError('SYNTHETIC_PRIVATE_EXCEPTION_SENTINEL')
  return 0
 monkeypatch.setattr(client,'attended_session',session)
 assert mint.main(['--phase','mint','--successor-expired-unused','--continue-owner-session','--authority',str(mint.CORRECTED_AUTHORITY),'--authority-sha256',mint.CORRECTED_RAW_SHA])==(2 if session_failure else 0)
 assert seen==[True] and f.calls==['GET','POST']
 out=capsys.readouterr();assert all(v not in out.out+out.err for v in [PASSWORD,VAULT,'SYNTHETIC_PRIVATE_EXCEPTION_SENTINEL'])

def test_attended_alarm_not_inherited_by_actual_bounded_child(v2):
 import sys
 f=v2
 with client.AttendedCredentials(KEY) as memory:
  memory.arm_expiry(f['r']['expiry'])
  readfd,writefd=os.pipe();os.write(writefd,b'SYNTHETIC_PIPE_ONLY');os.close(writefd)
  try:
   command=[sys.executable,'-B','-c','import os,signal,sys;assert os.read(int(sys.argv[1]),64)==b"SYNTHETIC_PIPE_ONLY";print("CHILD_ALARM",signal.getitimer(signal.ITIMER_REAL))',str(readfd)]
   data,status=client.capture(command,{'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},seconds=3,ceiling=128,pass_fds=(readfd,))
  finally:os.close(readfd)
  assert status['client_closed'] and status['exit_code']==0 and b'(0.0, 0.0)' in data and KEY.encode() not in data
 assert memory.values=={}


def test_independent_worker_closure_after_session_death_and_expiry(v2,monkeypatch):
 import psycopg
 from verification.ingestion_storage import tls_trust
 f=v2;io.Vault(Path(f['s']['access_vault']),KEY,create=True).save(dict(version='FINITE_INTAKE_ACCESS_STATE_V1',binding=f['b'],state='ACTIVATION_ACKNOWLEDGED'))
 f['clock'][0]=f['r']['expiry']+1;calls=[]
 class Connection:
  def __enter__(self):return self
  def __exit__(self,*_):pass
 def connect(**kw):calls.append(kw);return Connection()
 monkeypatch.setattr(psycopg,'connect',connect);monkeypatch.setattr(tls_trust,'verified_trust',lambda:(Path('/offline/ca.pem'),'offline-hash'))
 def close(c,s,save):
  assert s['binding']['valid_until']<f['clock'][0];op.validate_binding(s['binding'],opening=False)
  return dict(outcome='COMMIT_ACKNOWLEDGED',runtime_access='DISABLED')
 monkeypatch.setattr(op,'close',close)
 result=client.worker('close',f['b'],dict(vault_key=KEY,owner_password='FRESH_SYNTHETIC_OWNER'),f['s']['access_vault'],{})
 assert result['runtime_access']=='DISABLED' and len(calls)==1 and calls[0]['sslmode']=='verify-full' and calls[0]['password']=='FRESH_SYNTHETIC_OWNER'

def test_unbound_actual_launcher_entries_refuse_precisely_without_credentials(monkeypatch,capsys):
 monkeypatch.setattr(client,'hidden',lambda _:pytest.fail('no hidden inputs'))
 monkeypatch.setattr(mint,'sign',lambda *a:pytest.fail('no key'))
 assert client.main(['--launch','--phase','period'])==2
 assert 'TIMING_RELEASE_UNBOUND' in capsys.readouterr().out
 assert mint.main(['--launch','--phase','seal','--authority','NOT_OPENED','--authority-sha256','0'*64])==2
 out=capsys.readouterr().out;assert 'TIMING_RELEASE_UNBOUND' in out and 'UNKNOWN' not in out

def test_qualification_rechecks_setup_boundary_in_child_before_any_connection(v2,monkeypatch):
 import psycopg
 f=v2;f['clock'][0]+=600
 monkeypatch.setattr(psycopg,'connect',lambda **kw:pytest.fail('no connection'))
 with pytest.raises(op.Denied,match='SETUP_TEN_MINUTE_BOUND'):
  client.worker('qualify',f['b'],dict(vault_key=KEY),f['s']['access_vault'],{})
 assert not Path(f['s']['access_vault']).exists()
