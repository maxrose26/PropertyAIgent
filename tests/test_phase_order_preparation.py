"""Credential-free local readiness/ordering tests; no provider or DB connection."""
import copy,hashlib,json,os,shlex
from pathlib import Path
import pytest
from verification.ingestion_storage import publication_mint as mint,finite_release_binding as flow,intake_owner_client as client
from verification.ingestion_storage.operational_publication import canonical

@pytest.fixture
def prepared(tmp_path,monkeypatch):
 root=tmp_path/'release';private=tmp_path/'private';root.mkdir(mode=0o700);private.mkdir(mode=0o700)
 source=flow.ROOT;s=json.loads((source/'STATIC-RELEASE.json').read_bytes());now=1793706638.0
 s['binding_fields']['period_vault_path']=str(private/'period.vault');s['binding_fields']['publication_vault_path']=str(private/'publication.vault');s['access_vault']=str(private/'access.vault')
 monkeypatch.setattr(flow,'ROOT',root);monkeypatch.setattr(flow,'PRIVATE',private);monkeypatch.setattr(mint,'ROOT',private)
 monkeypatch.setattr(flow,'static',lambda:s);monkeypatch.setattr(flow.time,'time',lambda:now)
 def put(p,v):p.parent.mkdir(mode=0o700,parents=True,exist_ok=True);p.write_bytes(canonical(v));p.chmod(0o600);return p
 result=dict(status='MINT_RECEIPT_VALIDATED_NOT_ARMED',mint_outcome='MINTED',retry=False,authority_sha256=flow.AUTHORITY,receipt_sha256='b'*64,expiry=now+2100,expires_at='2026-11-03T12:25:38Z',owner_process=dict(client_closed=True,exit_code=0,reason=None))
 path=put(private/'result.json',result);monkeypatch.setattr(flow,'MINT_RESULT',path)
 b,p=flow.build(s,result,now,now=now);bh=hashlib.sha256(canonical(b)).hexdigest();ph=hashlib.sha256(canonical(p)).hexdigest();mh=hashlib.sha256(path.read_bytes()).hexdigest()
 frozen=dict(binding_path=str(root/'owner-binding.json'),binding_sha256=bh,policy_path=str(root/'period-policy.json'),policy_sha256=ph,mint_result_sha256=mh,receipt_sha256=result['receipt_sha256'],expiry=result['expiry'],isolation_observed_at=now,handoff_latest=now+300)
 for n,v in [('owner-binding.json',b),('period-policy.json',p),('FROZEN.json',frozen),('ACTUAL-MINT-REVIEW.json',dict(mint_result_sha256=mh,receipt_sha256=result['receipt_sha256'],expiry=result['expiry']))]:put(root/n,v)
 return dict(root=root,private=private,now=now,b=b,bh=bh,put=put)

def sealed(f):
 f['put'](f['private']/'seal-evidence-01/result.json',dict(status='PRIVATE_PUBLICATION_TOKEN_ARMED',receipt_sha256='b'*64,owner_process=dict(client_closed=True,exit_code=0,reason=None)))
 f['put'](f['private']/'seal-01-consumed.json',dict(binding_sha256=hashlib.sha256(canonical(f['b'])).hexdigest(),receipt_sha256='b'*64))
def receipt(f,phase,**changes):
 b=f['b'];v=dict(period=dict(outcome='COMMIT_ACKNOWLEDGED',period=b['period'],policy_sha256=b['period_policy_sha256'],temporary_issuer='REMOVED',original_memberships='PRESERVED',readback='EXACT_ON_SAME_CONNECTION',connections=1),activate=dict(outcome='COMMIT_ACKNOWLEDGED',runtime_roles=sorted(flow.owner.ROLES),credentials='ENCRYPTED_LOCAL_ONLY',valid_until=b['valid_until']),qualify=dict(status='TWO_SINGLE_ATTEMPT_RESTRICTED_AUTHENTICATIONS_CLOSED',roles=[dict(role=n,attempts=1,closed=True) for n in sorted(flow.owner.ROLES)]),handoff=dict(status='RENDER_HANDOFF_ACKNOWLEDGED',service_id='crn-d9sv93vavr4c73f98rb0'))[phase];v.update(changes)
 d=f['root']/(phase+'-evidence');f['put'](d/'output.txt',v);f['put'](d/'status.json',dict(phase=phase,binding_sha256=f['bh'],client_closed=True,exit_code=0,reason=None,remote_closure='NORMAL_PHASE_EXIT_SEE_RESULT'))

def test_missing_binding_refuses_before_input_child_or_consumption(prepared,monkeypatch,capsys):
 f=prepared;(f['root']/'owner-binding.json').unlink();monkeypatch.setattr(mint,'load_file',lambda *a:{})
 monkeypatch.setattr(mint,'validate_authority',lambda a:None)
 def forbidden(*a,**kw):raise AssertionError('SENSITIVE_SENTINEL_MUST_NOT_APPEAR')
 monkeypatch.setattr('builtins.input',forbidden);monkeypatch.setattr(client,'capture',forbidden);monkeypatch.setattr(client,'hidden',forbidden)
 assert mint.main(['--phase','seal','--successor-expired-unused','--authority','unused','--authority-sha256','unused'])==2
 out=capsys.readouterr().out;assert 'BINDING_MISSING_RUN_FREEZE' in out and 'SENSITIVE_SENTINEL' not in out
 assert not (f['private']/'seal-01-consumed.json').exists() and not (f['private']/'seal-evidence-01').exists()
 assert flow.main(['ready'])==2 and 'command' not in capsys.readouterr().out

@pytest.mark.parametrize('name',['FROZEN.json','period-policy.json'])
def test_incomplete_freeze_never_presents_seal(prepared,name,capsys):
 (prepared['root']/name).unlink();assert flow.main(['ready'])==2;assert 'command' not in capsys.readouterr().out

def test_tampered_binding_and_forged_frozen_proof_refuse(prepared):
 f=prepared;p=f['root']/'owner-binding.json';b=json.loads(p.read_bytes());b['period']='different';f['put'](p,b)
 with pytest.raises(flow.PreparationError,match='FROZEN_BINDING_MISMATCH'):flow.next_command(now=f['now'])

@pytest.mark.parametrize('delta',[-1,301])
def test_observations_not_backdated_or_extended(prepared,delta):
 with pytest.raises(flow.PreparationError,match='FROZEN_OBSERVATION_EXPIRED'):flow.next_command(now=prepared['now']+delta)

def test_successful_order_only_after_each_matching_acknowledged_result(prepared):
 f=prepared
 phase,cmd=flow.next_command(now=f['now']);assert phase=='seal' and '--binding' not in shlex.split(cmd)
 sealed(f)
 for phase in ['period','activate','qualify','handoff']:
  actual,cmd=flow.next_command(now=f['now']);assert actual==phase
  args=shlex.split(cmd);assert args[args.index('--binding-sha256')+1]==f['bh'];assert '--evidence' in args
  with pytest.raises(flow.PreparationError,match='PHASE_ORDER_REFUSED'):flow.next_command(now=f['now'],expect='seal')
  receipt(f,phase)
 with pytest.raises(flow.PreparationError,match='NEXT_SUBMISSION_REVIEW_REQUIRED'):flow.next_command(now=f['now'])

@pytest.mark.parametrize('failure',['lost_ack','wrong_binding','temporary_permission','existing_intent','later_receipt'])
def test_no_repeated_or_skipped_effect_from_partial_evidence(prepared,failure):
 f=prepared;sealed(f)
 if failure=='existing_intent':f['put'](Path(f['b']['period_vault_path']),dict(state='COMMIT_INTENT_NO_RETRY'))
 elif failure=='later_receipt':receipt(f,'activate')
 else:
  receipt(f,'period',**({'temporary_issuer':'PRESENT'} if failure=='temporary_permission' else {}))
  p=f['root']/'period-evidence/status.json';v=json.loads(p.read_bytes())
  if failure=='lost_ack':v['exit_code']=2
  elif failure=='wrong_binding':v['binding_sha256']='a'*64
  f['put'](p,v)
 with pytest.raises(flow.PreparationError):flow.next_command(now=f['now'])

def test_wrong_seal_approval_before_credentials_and_result_slot(prepared,monkeypatch,capsys):
 f=prepared;monkeypatch.setattr(mint,'load_file',lambda *a:{})
 monkeypatch.setattr(mint,'validate_authority',lambda a:None);monkeypatch.setattr(mint,'digest',lambda a:mint.CORRECTED_A_SHA)
 monkeypatch.setattr(mint.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(mint.sys.stderr,'isatty',lambda:True)
 monkeypatch.setattr('builtins.input',lambda _:'PRIVATE_PUBLICATION_TOKEN_ARMED')
 def forbidden(*a,**kw):raise AssertionError('SECRET_SENTINEL')
 monkeypatch.setattr(client,'hidden',forbidden);monkeypatch.setattr(client,'capture',forbidden)
 assert mint.main(['--phase','seal','--successor-expired-unused','--authority','unused','--authority-sha256','unused'])==2
 text=capsys.readouterr().out;assert 'APPROVAL' in text and 'SECRET_SENTINEL' not in text
 assert not (f['private']/'seal-evidence-01').exists()

def test_seal_autobinds_exact_frozen_paths_before_credentials(prepared,monkeypatch,capsys):
 f=prepared;seen=[];monkeypatch.setattr(mint,'load_file',lambda *a:{})
 monkeypatch.setattr(mint,'validate_authority',lambda a:None);monkeypatch.setattr(mint,'digest',lambda a:mint.CORRECTED_A_SHA)
 monkeypatch.setattr(mint.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(mint.sys.stderr,'isatty',lambda:True)
 monkeypatch.setattr('builtins.input',lambda _:'SEAL_EXACT_B_PUBLICATION_TOKEN_ONCE')
 monkeypatch.setattr(client,'vault_input',lambda p:'x'*24)
 def capture(cmd,env,**kw):
  os.read(kw['pass_fds'][0],4096);seen.append(cmd)
  assert cmd[cmd.index('--binding')+1]==str(f['root']/'owner-binding.json')
  assert cmd[cmd.index('--binding-sha256')+1]==f['bh']
  raw=canonical(dict(status='PRIVATE_PUBLICATION_TOKEN_ARMED',mint_outcome='MINTED',receipt_sha256='b'*64,provider_calls=0,retry=False))
  return raw,dict(exit_code=0,reason=None,client_closed=True,output_bytes=len(raw))
 monkeypatch.setattr(client,'capture',capture)
 assert mint.main(['--phase','seal','--successor-expired-unused','--authority','unused','--authority-sha256','unused'])==0
 assert len(seen)==1;assert 'x'*24 not in capsys.readouterr().out

def test_owner_parent_fixed_evidence_and_binding_receipt(prepared,monkeypatch,capsys):
 f=prepared;sealed(f);prompts=[]
 monkeypatch.setattr(client.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(client.sys.stderr,'isatty',lambda:True)
 def prompt(s):prompts.append(s);return 'EXECUTE_EXACT_PERIOD_ONCE'
 monkeypatch.setattr('builtins.input',prompt);monkeypatch.setattr(client,'vault_input',lambda *a,**k:'v'*24);monkeypatch.setattr(client,'private_input',lambda *a,**k:'FAKE_OWNER_SECRET')
 def capture(command,environment,**kw):
  secret=json.loads(os.read(kw['pass_fds'][0],4096));assert secret==dict(vault_key='v'*24,owner_password='FAKE_OWNER_SECRET')
  v=dict(outcome='COMMIT_ACKNOWLEDGED',period=f['b']['period'],policy_sha256=f['b']['period_policy_sha256'],temporary_issuer='REMOVED',original_memberships='PRESERVED',readback='EXACT_ON_SAME_CONNECTION',connections=1)
  raw=canonical(v);return raw,dict(exit_code=0,reason=None,client_closed=True,output_bytes=len(raw))
 monkeypatch.setattr(client,'capture',capture)
 phase,command=flow.next_command(now=f['now']);args=shlex.split(command)[2:]
 assert phase=='period' and client.main(args)==0 and len(prompts)==1
 st=json.loads((f['root']/'period-evidence/status.json').read_bytes());assert st['binding_sha256']==f['bh']
 assert flow.next_command(now=f['now'])[0]=='activate'
 assert 'FAKE_OWNER_SECRET' not in capsys.readouterr().out


def test_existing_failed_evidence_not_replaced(prepared):
 f=prepared;sealed(f);p=f['root']/'period-evidence';p.mkdir(mode=0o700)
 f['put'](p/'status.json',dict(phase='period',binding_sha256=f['bh'],client_closed=True,exit_code=2,reason='UNKNOWN',remote_closure='UNKNOWN_AFTER_FORCED_EXIT'))
 original=(p/'status.json').read_bytes()
 with pytest.raises(flow.PreparationError,match='PRIOR_PHASE_REQUIRES_REVIEW_NO_RETRY'):flow.next_command(now=f['now'])
 assert (p/'status.json').read_bytes()==original and not (p/'output.txt').exists()


def test_supplied_seal_hash_cannot_override_frozen_binding(prepared,monkeypatch,capsys):
 monkeypatch.setattr(mint,'load_file',lambda *a:{})
 monkeypatch.setattr(mint,'validate_authority',lambda a:None)
 monkeypatch.setattr('builtins.input',lambda _:pytest.fail('approval must not be reached'))
 assert mint.main(['--phase','seal','--successor-expired-unused','--authority','unused','--authority-sha256','unused','--binding',str(prepared['root']/'owner-binding.json'),'--binding-sha256','0'*64])==2
 assert 'BINDING_ARGUMENT_MISMATCH' in capsys.readouterr().out


def test_local_ready_has_no_phase_execution_or_secret_surface():
 import ast
 tree=ast.parse(Path(flow.__file__).read_text());names={n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
 assert not names&{'connect','request','post','put','delete','mint','seal','activate','handoff','Vault','Popen','run','execv','execve','system','getpass'}

def test_handoff_readiness_does_not_extend_or_narrow_activation_expiry_guard(prepared):
 f=prepared;r=json.loads(flow.MINT_RESULT.read_bytes());observed=r['expiry']-1500
 b,policy=flow.build(flow.static(),r,observed,now=observed);f['b']=b;f['bh']=hashlib.sha256(canonical(b)).hexdigest()
 f['put'](f['root']/'owner-binding.json',b);proof=json.loads((f['root']/'FROZEN.json').read_bytes());proof.update(binding_sha256=f['bh'],isolation_observed_at=observed,handoff_latest=observed+300);f['put'](f['root']/'FROZEN.json',proof)
 sealed(f);receipt(f,'period')
 with pytest.raises(flow.PreparationError,match='RELEASE_WINDOW_CLOSED'):flow.next_command(now=observed+100)
 receipt(f,'activate');receipt(f,'qualify')
 assert flow.next_command(now=observed+100)[0]=='handoff'

def test_freeze_requires_mint_review_before_any_confirmation(prepared,monkeypatch,capsys):
 f=prepared;(f['root']/'ACTUAL-MINT-REVIEW.json').unlink()
 monkeypatch.setattr(flow.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(flow.sys.stderr,'isatty',lambda:True)
 monkeypatch.setattr('builtins.input',lambda _:pytest.fail('must not prompt'))
 assert flow.main(['freeze'])==2 and 'MINT_REVIEW_REQUIRED' in capsys.readouterr().out

def test_wrong_freeze_confirmation_writes_nothing(prepared,monkeypatch,capsys):
 f=prepared
 for name in ['FROZEN.json','owner-binding.json','period-policy.json']:(f['root']/name).unlink()
 monkeypatch.setattr(flow.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(flow.sys.stderr,'isatty',lambda:True)
 monkeypatch.setattr('builtins.input',lambda _:'PRIVATE_PUBLICATION_TOKEN_ARMED')
 assert flow.main(['freeze'])==2 and 'FRESH_CONFIRMATION_REQUIRED' in capsys.readouterr().out
 assert not any((f['root']/n).exists() for n in ['FROZEN.json','owner-binding.json','period-policy.json'])


def test_local_freeze_then_ready_uses_actual_confirmation_time(prepared,monkeypatch,capsys):
 f=prepared
 for name in ['FROZEN.json','owner-binding.json','period-policy.json']:(f['root']/name).unlink()
 review=json.loads((f['root']/'ACTUAL-MINT-REVIEW.json').read_bytes());review['policy_sha256']=f['b']['period_policy_sha256'];f['put'](f['root']/'ACTUAL-MINT-REVIEW.json',review)
 monkeypatch.setattr(flow.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(flow.sys.stderr,'isatty',lambda:True)
 monkeypatch.setattr('builtins.input',lambda _:flow.FRESH_PHRASE)
 assert flow.main(['freeze'])==0
 assert json.loads((f['root']/'FROZEN.json').read_bytes())['isolation_observed_at']==f['now']
 assert flow.main(['ready'])==0
 value=json.loads(capsys.readouterr().out.splitlines()[-1]);assert value['phase']=='seal' and '--binding' not in value['command']

def test_missing_mint_result_is_specific_precredential_refusal(prepared,capsys):
 flow.MINT_RESULT.unlink();assert flow.main(['ready'])==2
 out=capsys.readouterr().out;assert 'MINT_RESULT_REQUIRED' in out and 'command' not in out

@pytest.mark.parametrize('change',['duplicate_phase','wrong_binding','child'])
def test_actual_launcher_argv_cannot_bypass_phase_or_frozen_hash(prepared,change,capsys):
 f=prepared;sealed(f);phase,command=flow.next_command(now=f['now']);args=shlex.split(command)[2:]
 if change=='duplicate_phase':args+=['--phase','activate']
 elif change=='wrong_binding':args[args.index('--binding-sha256')+1]='0'*64
 else:args+=['--child','--secrets-fd','3']
 assert flow.main(['ready','--expect-phase',phase,'--verify-argv',*args])==2
 assert 'PHASE_ARGUMENTS_REFUSED' in capsys.readouterr().out


def test_actual_launcher_exact_argv_is_verified_before_owner_client(prepared,capsys):
 f=prepared;sealed(f);phase,command=flow.next_command(now=f['now']);args=shlex.split(command)[2:]
 assert flow.main(['ready','--expect-phase',phase,'--verify-argv',*args])==0
 assert 'NEXT_PHASE_VERIFIED' in capsys.readouterr().out

def test_closed_release_is_not_instructed_to_freeze_again(prepared,capsys):
 f=prepared;path=f['put'](f['root']/'EXPIRED-UNUSED-SUCCESSOR-CLOSURE.json',dict(status='EXPIRED_UNUSED'));raw=path.read_bytes()
 assert flow.main(['ready'])==2
 out=capsys.readouterr().out;assert 'RELEASE_CLOSED_EXPLICIT_REBIND_REQUIRED' in out and 'command' not in out
 assert path.read_bytes()==raw
