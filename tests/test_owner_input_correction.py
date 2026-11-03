"""Synthetic credentials and mocked capture only; no owner key/provider access."""
import json,os
import pytest
from verification.ingestion_storage import publication_mint as m,intake_owner_client as c
from verification.ingestion_storage.intake_owner_io import Vault
from tests.test_publication_mint import fx,synthetic_key,Fake,PASSWORD,VAULT,TOKEN,run,binding
from tests.test_intake_owner_operations import inputs
REFUSAL=b'{"mint_outcome":"NOT_INFERRED_RECONCILE","reason":"SECRET","retry":false,"status":"STOP_MINT_SEAL_REQUIRES_REVIEW_NO_RETRY"}'

def original(f):
 p=f.root/'mint-evidence-01';p.mkdir(mode=0o700);p=p/'result.json';p.write_bytes(REFUSAL);p.chmod(0o600)
 assert m.digest(REFUSAL)==m.LOCAL_REFUSAL_SHA256
 return p

def terminal(monkeypatch,answers):
 monkeypatch.setattr(m.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(m.sys.stderr,'isatty',lambda:True)
 it=iter(answers);monkeypatch.setattr(c,'hidden',lambda _:next(it))

def args(f,replace=True):
 p=f.root/'authority.json';p.write_bytes(m.canonical(f.a));p.chmod(0o600)
 return ['--phase','mint','--authority',str(p),'--authority-sha256',m.digest(p.read_bytes())]+(['--replace-local-refusal'] if replace else [])

def pipe_read(v,k):
 r,w=os.pipe();os.write(w,m.canonical(dict(vault_password=v,key_password=k)));os.close(w);return r

@pytest.mark.parametrize('bad',['','short','x'*1025,'x\nSECRET','x\0SECRET','\u2603'*400])
def test_local_correction_before_any_reservation(fx,monkeypatch,capsys,bad):
 terminal(monkeypatch,[bad,VAULT,VAULT]);assert c.private_input('hidden:',minimum=24,confirm=True)==VAULT
 assert not list(fx.root.glob('*consumed*')) and not list(fx.root.glob('*evidence*')) and not fx.calls
 out=capsys.readouterr().err;assert VAULT not in out and 'SECRET' not in out and len(out)<512

def test_confirmation_reprompts(fx,monkeypatch,capsys):
 terminal(monkeypatch,[VAULT,'WRONG_PRIVATE_SENTINEL',VAULT,VAULT])
 assert c.private_input('hidden:',minimum=24,confirm=True)==VAULT
 out=capsys.readouterr().err;assert 'LOCAL_CONFIRMATION_MISMATCH' in out and 'SENTINEL' not in out

@pytest.mark.parametrize('error',[EOFError('SECRET_SENTINEL'),KeyboardInterrupt(),RuntimeError('SECRET_SENTINEL')])
def test_cancel_unknown_does_not_retry_or_consume(fx,monkeypatch,error):
 def stop(_):raise error
 monkeypatch.setattr(c,'hidden',stop)
 with pytest.raises(type(error)):c.private_input('hidden:')
 assert not fx.calls and not list(fx.root.glob('*consumed*'))

def test_common_vault_authenticated_without_confirmation(fx,monkeypatch,capsys):
 f=fx;Vault(f.root/'mint-01.vault',VAULT,create=True).save({'synthetic':True})
 terminal(monkeypatch,['WRONG_SYNTHETIC_PASSPHRASE_24_PLUS',VAULT])
 assert c.vault_input(f.root/'new.vault',create=True,mint_bound=True)==VAULT
 assert not (f.root/'new.vault').exists() and not f.calls
 assert 'LOCAL_VAULT_UNLOCK_REFUSED' in capsys.readouterr().err

@pytest.mark.parametrize('name',['mint-01-consumed.json','mint-01.vault','mint-01.vault.next','seal-01-consumed.json','publication-01.vault','publication-01.vault.revoke-consumed'])
def test_original_intent_or_vault_prevents_replacement(fx,name):
 f=fx;original(f);(f.root/name).write_text('synthetic')
 with pytest.raises(m.Refusal,match='EXISTING_ATTEMPT'):m.replacement_preconditions()
 assert not f.calls

@pytest.mark.parametrize('change',['hash','extra','symlink'])
def test_exact_original_required(fx,change):
 f=fx;p=original(f)
 if change=='hash':p.write_bytes(REFUSAL+b'\n')
 elif change=='extra':(p.parent/'extra').write_text('not allowed')
 else:p.rename(p.parent/'saved');p.symlink_to(p.parent/'saved')
 with pytest.raises(m.Refusal):m.replacement_preconditions()
 assert not f.calls

def test_actual_parent_child_local_corrections_and_one_post(fx,monkeypatch,capsys):
 f=fx;p=original(f);before=p.read_bytes();terminal(monkeypatch,['short',VAULT,'mismatch',VAULT,VAULT,'wrongkey',PASSWORD])
 monkeypatch.setattr('builtins.input',lambda _:'EXECUTE_ONE_B_PUBLICATION_TOKEN_MINT');calls=[];actual=m.mint
 def capture(command,environment,**kw):
  assert command[-1]=='--replace-local-refusal' and kw['seconds']==60 and kw['ceiling']==4096
  assert environment.keys()=={'HOME','PATH','LANG','PYTHONDONTWRITEBYTECODE','OPENBLAS_NUM_THREADS'}
  assert not (f.root/'mint-01-consumed.json').exists() and (f.root/m.REPLACEMENT_OUTPUT).is_dir()
  secret=json.loads(os.read(kw['pass_fds'][0],4096));assert secret==dict(vault_password=VAULT,key_password=PASSWORD)
  child=command[command.index('--child'):];child[child.index('--secrets-fd')+1]=str(pipe_read(VAULT,PASSWORD));calls.append(True)
  monkeypatch.setattr(m,'mint',lambda a,h,k,v:actual(a,h,k,v,transport_factory=lambda a,j:Fake(f),clock=lambda:f.now))
  capsys.readouterr();assert m.main(child)==0;raw=capsys.readouterr().out.encode()
  return raw,dict(exit_code=0,reason=None,client_closed=True,output_bytes=len(raw))
 monkeypatch.setattr(c,'capture',capture);a=args(f);assert m.main(a)==0
 assert calls==[True] and f.calls==['GET','POST'] and p.read_bytes()==before
 result=json.loads((f.root/m.REPLACEMENT_OUTPUT/'result.json').read_bytes())
 assert result['status']=='MINT_RECEIPT_VALIDATED_NOT_ARMED' and result['owner_process']['client_closed']
 assert m.main(a)==2 and calls==[True] and f.calls==['GET','POST']
 out=capsys.readouterr().err;assert not any(s in out for s in (VAULT,PASSWORD,TOKEN,'wrongkey'))

def test_key_failure_cancel_before_reservation(fx,monkeypatch,capsys):
 f=fx;original(f);terminal(monkeypatch,[VAULT,VAULT,'wrongkey'])
 monkeypatch.setattr('builtins.input',lambda _:'EXECUTE_ONE_B_PUBLICATION_TOKEN_MINT')
 assert m.main(args(f))==2 and not f.calls
 assert not (f.root/m.REPLACEMENT_OUTPUT).exists() and not (f.root/'mint-01-consumed.json').exists()
 assert 'LOCAL_KEY_UNLOCK_REFUSED' in capsys.readouterr().err

def test_original_entry_stays_used(fx,monkeypatch):
 f=fx;original(f);terminal(monkeypatch,[])
 monkeypatch.setattr('builtins.input',lambda _:'EXECUTE_ONE_B_PUBLICATION_TOKEN_MINT')
 assert m.main(args(f,False))==2 and not f.calls

def test_child_rechecks_before_mint(fx,monkeypatch,capsys):
 f=fx;original(f);a=args(f);(f.root/'mint-01-consumed.json').write_text('prior uncertain');r=pipe_read(VAULT,PASSWORD)
 try:assert m.main(a+['--child','--secrets-fd',str(r)])==2
 finally:os.close(r)
 assert not f.calls and json.loads(capsys.readouterr().out)['reason']=='EXISTING_ATTEMPT'

def test_owner_phase_local_checks_before_output_and_capture(fx,tmp_path,monkeypatch,capsys):
 b,_=inputs(tmp_path);vp=tmp_path/'access.vault';Vault(vp,VAULT,create=True).save({'synthetic':True})
 bp=tmp_path/'b.json';bp.write_bytes(m.canonical(b));out=tmp_path/'phase-evidence'
 answers=iter(['EXECUTE_EXACT_CLOSE_ONCE',str(out)]);monkeypatch.setattr('builtins.input',lambda _:next(answers))
 terminal(monkeypatch,['WRONG_SYNTHETIC_VAULT_PASSPHRASE',VAULT,'',PASSWORD]);seen=[]
 def capture(command,environment,**kw):
  assert out.is_dir();secret=json.loads(os.read(kw['pass_fds'][0],4096))
  assert secret=={'vault_key':VAULT,'owner_password':PASSWORD};seen.append(True)
  return b'{"status":"synthetic"}',dict(exit_code=0,reason=None,client_closed=True,output_bytes=22)
 monkeypatch.setattr(c,'capture',capture)
 assert c.main(['--phase','close','--binding',str(bp),'--binding-sha256',m.digest(bp.read_bytes()),'--vault',str(vp)])==0
 assert seen==[True] and not fx.calls
 out=capsys.readouterr().err;assert VAULT not in out and PASSWORD not in out and 'LOCAL_VAULT_UNLOCK_REFUSED' in out

def test_seal_local_unlock_no_second_confirmation(fx,tmp_path,monkeypatch,capsys):
 f=fx;run(f);b=binding(f,tmp_path);bp=tmp_path/'b.json';bp.write_bytes(m.canonical(b))
 terminal(monkeypatch,['WRONG_SYNTHETIC_VAULT_PASSPHRASE',VAULT])
 monkeypatch.setattr('builtins.input',lambda _:'SEAL_EXACT_B_PUBLICATION_TOKEN_ONCE')
 def capture(command,environment,**kw):
  assert json.loads(os.read(kw['pass_fds'][0],4096))==dict(vault_password=VAULT,key_password=None)
  result=m.seal(f.a,f.h,b,VAULT,clock=lambda:f.expiry-1800)
  return m.canonical(result),dict(exit_code=0,reason=None,client_closed=True,output_bytes=120)
 monkeypatch.setattr(c,'capture',capture);a=args(f,False);a[1]='seal';a+=['--binding',str(bp),'--binding-sha256',m.digest(bp.read_bytes())]
 assert m.main(a)==0 and f.calls==['GET','POST']
 assert 'LOCAL_VAULT_UNLOCK_REFUSED' in capsys.readouterr().err

@pytest.mark.parametrize('phase',['period','activate','qualify','handoff','close','publication-revoke','handoff-restore','readback'])
def test_remaining_owner_phase_dispatch_inputs_and_limits(fx,tmp_path,monkeypatch,capsys,phase):
 from verification.ingestion_storage import intake_owner as op
 f=fx;assert run(f)['status']=='MINT_RECEIPT_VALIDATED_NOT_ARMED';b=binding(f,tmp_path)
 monkeypatch.setattr(op.time,'time',lambda:f.expiry-1800)
 # Policy uses exactly the final binding, not a relaxed fixture policy.
 _,policy=inputs(tmp_path);policy.update(expires_at=b['valid_until'],render_profile=b['render_profile'])
 b['period_policy_sha256']=m.digest(m.canonical(policy))
 bp=tmp_path/'binding.json';bp.write_bytes(m.canonical(b));ep=tmp_path/'expected.json'
 ep.write_bytes(m.canonical(policy if phase=='period' else {'job_id':None}))
 new=phase in ('period','activate');vp=tmp_path/'phase.vault'
 if phase=='period':vp=tmp_path/'period.vault';b['period_vault_path']=str(vp);bp.write_bytes(m.canonical(b))
 if phase=='publication-revoke':vp=f.root/'publication-01.vault'
 if phase!='readback' and not new:Vault(vp,VAULT,create=True).save({'synthetic':True})
 out=tmp_path/'evidence';answers=iter(['EXECUTE_EXACT_'+phase.upper().replace('-','_')+'_ONCE',str(out)])
 monkeypatch.setattr('builtins.input',lambda _:next(answers))
 secrets=[]
 if phase!='readback':secrets.append(VAULT)
 if phase in ('period','activate','close','readback'):secrets.append(PASSWORD)
 if phase.startswith('handoff'):secrets.append('SYNTHETIC_RENDER_KEY')
 terminal(monkeypatch,secrets);seen=[]
 def capture(command,env,**kw):
  raw=os.read(kw['pass_fds'][0],4096);d=json.loads(raw);seen.append(d)
  assert len(raw)<=4000 and kw['ceiling']==30720
  assert 'GH_TOKEN' not in env and 'DATABASE_URL' not in env and 'SYNTHETIC' not in repr(command)
  assert command[command.index('--phase')+1]==phase
  return b'{"status":"SYNTHETIC_PHASE_ACK"}',dict(exit_code=0,reason=None,client_closed=True,output_bytes=32)
 monkeypatch.setattr(c,'capture',capture)
 a=['--phase',phase,'--binding',str(bp),'--binding-sha256',m.digest(bp.read_bytes())]
 if phase!='readback':a+=['--vault',str(vp)]
 if phase in ('period','handoff-restore','readback'):a+=['--expected',str(ep),'--expected-sha256',m.digest(ep.read_bytes())]
 assert c.main(a)==0 and len(seen)==1
 assert len(seen[0])==len(secrets)
 output=capsys.readouterr().err
 assert not any(x in output for x in (PASSWORD,VAULT,'SYNTHETIC_RENDER_KEY'))


def test_local_key_fingerprint_drift_is_terminal_not_password_retry(fx,monkeypatch):
 f=fx;f.a['key_fingerprint']='A'*43+'='
 with pytest.raises(m.Refusal,match='KEY_FINGERPRINT'):m.key_unlock(f.a,PASSWORD)
 assert not f.calls


def test_encoded_secret_frame_bounds_and_long_opaque_token(monkeypatch):
 from verification.ingestion_storage.intake_owner_operations import installation_token_allowed
 values=iter(['ghs_'+'x'*1500]);monkeypatch.setattr(c,'hidden',lambda _:next(values))
 assert len(c.private_input('token:',maximum=2048,validator=installation_token_allowed,unlock_code='TOKEN'))==1504
 values=iter(['x'*1024]);monkeypatch.setattr(c,'hidden',lambda _:next(values))
 assert len(c.private_input('password:'))==1024
 assert len(json.dumps(dict(vault_key='x'*1024,owner_password='x'*1024,render_token='x'*1024)).encode())<4000


def test_actual_getpass_format_handler_reprompts_without_echo(fx,monkeypatch,capsys):
 entries=iter(['', 'x\nSECRET_SENTINEL', VAULT])
 monkeypatch.setattr(c.getpass,'getpass',lambda _:next(entries))
 assert c.private_input('hidden:',minimum=24)==VAULT
 out=capsys.readouterr().err
 assert out.count('LOCAL_INPUT_FORMAT')==2 and 'SENTINEL' not in out and VAULT not in out
 assert not list(fx.root.glob('*consumed*'))


def test_malformed_token_feedback_is_distinct_and_private(monkeypatch,capsys):
 from verification.ingestion_storage.intake_owner_operations import installation_token_allowed
 entries=iter(['ghp_PRIVATE_SENTINEL','ghs_'+'x'*100]);monkeypatch.setattr(c,'hidden',lambda _:next(entries))
 assert c.private_input('hidden:',maximum=2048,validator=installation_token_allowed,unlock_code='TOKEN').startswith('ghs_')
 out=capsys.readouterr().err
 assert 'LOCAL_INSTALLATION_TOKEN_FORMAT_REFUSED' in out and 'SENTINEL' not in out and 'LOCAL_VAULT_UNLOCK' not in out

@pytest.mark.parametrize('fault',[None,'lost_ack','profile_drift','profile_limit'])
def test_single_handoff_from_restored_map_with_exact_profile_and_restoration(fault):
 import copy
 from app.ingestion.ledger import Denied
 from tests.test_intake_owner_io import API,prepared
 from verification.ingestion_storage.intake_owner_io import handoff,restore_handoff,reconcile_handoff
 api=API();s=prepared(api)
 api.env.pop('INGESTION_RENDER_PROFILE');api.env.pop('OPENAI_API_KEY');api.env.pop('OTHER_SECRET')
 api.env['PLANNING_STATUS_VERIFICATION_ENABLED']='SYNTHETIC_ORIGINAL_SETTING'
 original=copy.deepcopy(api.env);saved=[]
 if fault=='profile_drift':api.env['INGESTION_RENDER_PROFILE']='{}'
 if fault=='profile_limit':s['binding']['render_profile']['aggregate_bytes']=None
 if fault in ('profile_drift','profile_limit'):
  with pytest.raises(Denied):handoff(api,s,lambda x:saved.append(copy.deepcopy(x)),TOKEN)
  assert api.puts==0 and not saved;return
 api.fail_put=fault=='lost_ack'
 if fault=='lost_ack':
  with pytest.raises(RuntimeError):handoff(api,s,lambda x:saved.append(copy.deepcopy(x)),TOKEN)
  with pytest.raises(Denied):handoff(api,s,lambda _:None,TOKEN)
  assert api.puts==1 and reconcile_handoff(api,s,lambda _:None)['observed']=='EXPECTED'
  api.fail_put=False
 else:assert handoff(api,s,lambda x:saved.append(copy.deepcopy(x)),TOKEN)['status']=='RENDER_HANDOFF_ACKNOWLEDGED'
 assert json.loads(api.env['INGESTION_RENDER_PROFILE'])==s['binding']['render_profile']
 assert 'DATABASE_URL' not in api.env and 'PLANNING_STATUS_VERIFICATION_ENABLED' not in api.env
 assert saved[0]['render']['state']=='PUT_INTENT_NO_RETRY' and saved[0]['render']['original']==original
 s['state']='DATABASE_CLOSURE_ACKNOWLEDGED';api.calls=0
 assert restore_handoff(api,s,lambda _:None,None)['status']=='RESTORATION_VERIFIED'
 assert api.env==original and 'INGESTION_RENDER_PROFILE' not in api.env and api.puts==2
