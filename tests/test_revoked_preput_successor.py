"""Fresh fixed successor after acknowledged DB closure/token revocation.
Synthetic keys, ciphertext and receipts; actual entry functions; mocked providers.
"""
import contextlib,copy,io as stringio,json,os,signal,subprocess,time
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
import pytest
from verification.ingestion_storage import publication_mint as m,finite_release_binding as flow,intake_owner_client as client,intake_owner as op,intake_owner_operations as extra,intake_owner_io as io
from tests.test_publication_mint import fx,synthetic_key,PASSWORD,TOKEN
from tests.test_intake_owner_operations import inputs,mocked_sql
from tests.test_intake_owner_io import API
DOC=Path('docs/design/b-preput-revoked-successor-20261103')
OLD='SYNTHETIC_PREDECESSOR_VAULT_ONLY_24PLUS'
NEW='SYNTHETIC_FRESH_SUCCESSOR_VAULT_ONLY_24PLUS'

@pytest.fixture
def successor(fx,tmp_path,monkeypatch):
 f=fx;f.a['client_id']='Iv23liHaM7meqJPpdD8x';f.h=m.digest(m.canonical(f.a));oldroot=tmp_path/'old-release';oldroot.mkdir(mode=0o700)
 def put(p,v):
  p=Path(p);p.parent.mkdir(mode=0o700,parents=True,exist_ok=True);p.write_bytes(m.canonical(v));p.chmod(0o600);return p
 authority=put(f.root/'corrected-authority.json',f.a)
 for name,v in dict(CORRECTED_AUTHORITY=authority,CORRECTED_RAW_SHA=m.digest(authority.read_bytes()),CORRECTED_A_SHA=f.h,PREPUT_OLD_RELEASE=oldroot).items():monkeypatch.setattr(m,name,v)
 names=['REVOKED_PREPUT_MODE','SEAL_MARKER','SEAL_OUTPUT','PUBLICATION_VAULT','SUCCESSOR_MARKER','SUCCESSOR_JOURNAL','SUCCESSOR_OUTPUT','SUCCESSOR_ATTEMPT','SUCCESSOR_CLOSURE','SUCCESSOR_CLOSURE_SHA','PREDECESSOR_RECEIPT']
 for name in names:monkeypatch.setattr(m,name,getattr(m,name))
 b,p=inputs(tmp_path);T=f.now;D=T+2100;b.update(period='b-20261103-tm-reserve01',valid_until=D,publication_valid_until=f.expiry,timing_policy=dict(version='SEPARATE_EXPIRY_V2_RESERVE',bound_at=T,execution_day='2026-11-03'),runtime_deadline=D-185,publication_vault_path=str(f.root/m.PREPUT_OLD_PUBLICATION),publication_mint_journal_path=str(f.root/m.PREPUT_OLD_JOURNAL))
 receipt=m.receipt(f.value,T,T,f.h);rh=m.digest(m.canonical(receipt));b['publication_mint']=dict(authority_sha256=f.h,receipt_sha256=rh,expires_at=f.expiry);p['expires_at']=D-185;b['period_policy_sha256']=m.digest(m.canonical(p))
 put(oldroot/'owner-binding.json',b);put(oldroot/'period-policy.json',p);put(oldroot/'FROZEN.json',dict(binding_sha256=m.digest(m.canonical(b)),policy_sha256=b['period_policy_sha256']))
 def vault(name,value):v=io.Vault(f.root/name,OLD,create=True);v.save(value);return v
 vault(m.PREPUT_OLD_JOURNAL,dict(version='ONE_B_MINT_V1',state='SEALED_ACKNOWLEDGED',post_started=True,authority=f.a,authority_sha256=f.h,binding=b,receipt=receipt,receipt_sha256=rh))
 pub=io.Vault(f.root/m.PREPUT_OLD_PUBLICATION,OLD,create=True);extra.token_arm(b,TOKEN,pub.save)
 rev=extra.token_revoke(b,pub.load(),pub.save,runner=lambda cmd,**kw:subprocess.CompletedProcess(cmd,0,b'HTTP/2 204 OK\n',b''))
 vault(m.PREPUT_OLD_ACCESS,dict(version='FINITE_INTAKE_ACCESS_STATE_V1',binding=b,state='DATABASE_CLOSURE_ACKNOWLEDGED',passwords={}))
 vault('b-20261103-tm-reserve01-period.vault',dict(binding=b,policy=p,state='COMMIT_ACKNOWLEDGED'))
 put(f.root/'mint-evidence-reserve-v2-20261103-01/result.json',dict(status='MINT_RECEIPT_VALIDATED_NOT_ARMED',mint_outcome='MINTED',authority_sha256=f.h,receipt_sha256=rh,expiry=f.expiry,retry=False,owner_process=dict(client_closed=True,exit_code=0,reason=None)))
 put(f.root/'mint-reserve-v2-20261103-01-consumed.json',dict(attempt='ONE_B_PUBLICATION_MINT_RESERVE_V2_20261103_01',retry=False))
 put(f.root/'seal-evidence-01/result.json',dict(status='PRIVATE_PUBLICATION_TOKEN_ARMED',receipt_sha256=rh,owner_process=dict(client_closed=True,exit_code=0,reason=None)))
 put(f.root/'seal-01-consumed.json',dict(binding_sha256=m.digest(m.canonical(b)),receipt_sha256=rh))
 closed=dict(outcome='COMMIT_ACKNOWLEDGED',runtime_access='DISABLED',sessions='ABSENT',temporary_owner='REMOVED',authorities=[],intake_run_state=None,open_run_requires_reconciliation=False,stop_preserved=op.ACCEPTED_STOP)
 for phase,result,code in [('close',closed,0),('publication-revoke',rev,0),('handoff',dict(status='STOP_PHASE_REQUIRES_REVIEW_NO_RETRY',failure_reason='EXACT_RENDER_PROFILE_FIELDS_AND_LIMITS'),2)]:
  put(oldroot/(phase+'-evidence/output.txt'),result);put(oldroot/(phase+'-evidence/status.json'),dict(client_closed=True,exit_code=code,reason=None,binding_sha256=m.digest(m.canonical(b))))
 closure=put(oldroot/'ABORTED-B-CLOSURE-REVIEW.json',dict(status='B_NOT_SUBMITTED_CONTAINMENT_ACKNOWLEDGED',receipt=rh,environment_write=dict(put_intent_reached=False,put_reached=False),submission=dict(local_intent_exists=False,job_submitted_by_reviewed_route=False)))
 public={name:m.digest((oldroot/name).read_bytes()) for name in m.PREPUT_PUBLIC_PROOFS};private={name:m.digest((f.root/name).read_bytes()) for name in m.PREPUT_PRIVATE_PROOFS}
 monkeypatch.setattr(m,'PREPUT_PUBLIC_PROOFS',public);monkeypatch.setattr(m,'PREPUT_PRIVATE_PROOFS',private)
 f.preserved={oldroot/name:(oldroot/name).read_bytes() for name in public};f.preserved.update({f.root/name:(f.root/name).read_bytes() for name in private})
 select=m.select_revoked_preput_successor
 def mapped():select();m.SUCCESSOR_CLOSURE_SHA=m.digest(closure.read_bytes());m.PREDECESSOR_RECEIPT=rh
 monkeypatch.setattr(m,'select_revoked_preput_successor',mapped);mapped()
 root=tmp_path/'successor-owner/release';root.mkdir(mode=0o700,parents=True);s=json.loads((DOC/'STATIC-RELEASE.json').read_bytes());s.update(mint_journal_path=str(f.root/m.SUCCESSOR_JOURNAL),mint_result_path=str(f.root/m.SUCCESSOR_OUTPUT/'result.json'),access_vault=str(f.root/'successor-access.vault'),seal_evidence_path=str(f.root/m.SEAL_OUTPUT),seal_consumed_path=str(f.root/m.SEAL_MARKER));s['binding_fields'].update(period_vault_path=str(f.root/'successor-period.vault'),publication_vault_path=str(f.root/m.PUBLICATION_VAULT));s['mint_authority'].update(predecessor_receipt_sha256=rh,predecessor_closure_sha256=m.SUCCESSOR_CLOSURE_SHA)
 api=API();api.env={'PLAYWRIGHT_BROWSERS_PATH':'0','PYTHONUNBUFFERED':'1','DATABASE_URL':'SYNTHETIC_BASELINE_ADMIN','PLANNING_STATUS_VERIFICATION_ENABLED':'SYNTHETIC_BASELINE'};api.session=SimpleNamespace(close=lambda:None);s['binding_fields']['render_config_sha256']=io.service_guard(api.service)
 put(root/'STATIC-RELEASE.json',s);(root/'B-COMMAND.txt').write_bytes((DOC/'B-COMMAND.txt').read_bytes())
 for n,v in dict(TIMING_ROOT=root,TIMING_STATIC_SHA=m.digest((root/'STATIC-RELEASE.json').read_bytes()),PRIVATE=f.root,AUTHORITY=f.h,AUTHORITY_PATH=str(authority),AUTHORITY_RAW=m.CORRECTED_RAW_SHA).items():monkeypatch.setattr(flow,n,v)
 monkeypatch.setattr(m.time,'time',lambda:f.now);flow.use_timing_release();f.release=root;f.oldroot=oldroot;f.oldbinding=b;f.api=api;f.put=put;f.static=s;f.calls.clear();f.closed.clear();return f

class Transport:
 def __init__(self,f,error=False):self.f=f;self.error=error
 def call(self,method):
  f=self.f;f.calls.append(method)
  if method=='GET':return 200,m.canonical(f.install)
  marker=json.loads((f.root/m.SUCCESSOR_MARKER).read_bytes());assert marker['attempt']=='ONE_B_MINT_AFTER_REVOKED_PREPUT_20261103_V1'
  assert io.Vault(f.root/m.SUCCESSOR_JOURNAL,NEW).load()['state']=='POST_INTENT_NO_RETRY'
  if self.error:raise TimeoutError('SYNTHETIC_SECRET_SENTINEL')
  return 201,m.canonical(f.value)
 def close(self):self.f.closed.append(True)
def run(f,error=False,new=NEW,prior=OLD):return m.mint(f.a,f.h,PASSWORD,new,predecessor_vault_password=prior,clock=lambda:f.now,transport_factory=lambda *_:Transport(f,error),successor=True)
def preserved(f):assert all(p.read_bytes()==v for p,v in f.preserved.items())

def test_revoked_before_expiry_allows_one_new_post_and_no_replay(successor):
 f=successor;assert f.now<f.expiry;assert run(f)['status']=='MINT_RECEIPT_VALIDATED_NOT_ARMED';assert run(f)['mint_outcome']=='PRIOR_ATTEMPT_RECONCILE';assert f.calls==['GET','POST'];preserved(f)
 with pytest.raises(Exception):io.Vault(f.root/m.SUCCESSOR_JOURNAL,OLD).load()
 assert io.Vault(f.root/m.SUCCESSOR_JOURNAL,NEW).load()['state']=='RECEIPT_VALIDATED_NOT_ARMED'

def test_uncertain_post_never_repeated(successor):
 f=successor;assert run(f,True)['mint_outcome']=='UNCERTAIN';assert run(f)['mint_outcome']=='PRIOR_ATTEMPT_RECONCILE';assert f.calls==['GET','POST'];preserved(f)

@pytest.mark.parametrize('kind',['handoff','close','revocation','mint_cipher','publication_cipher','access_cipher','submission'])
def test_predecessor_drift_or_open_work_refuses_without_new_intent(successor,kind):
 f=successor
 paths={'handoff':f.oldroot/'handoff-evidence/output.txt','close':f.oldroot/'close-evidence/output.txt','revocation':f.oldroot/'publication-revoke-evidence/output.txt','mint_cipher':f.root/m.PREPUT_OLD_JOURNAL,'publication_cipher':f.root/m.PREPUT_OLD_PUBLICATION,'access_cipher':f.root/m.PREPUT_OLD_ACCESS,'submission':f.oldroot/'submission.intent.json'}
 paths[kind].write_bytes(b'SYNTHETIC_DRIFT');assert run(f)['status'].startswith('STOP_') and not f.calls and not (f.root/m.SUCCESSOR_MARKER).exists()

@pytest.mark.parametrize('kind',['seal','publication','mint','access','period','freeze'])
def test_fresh_exclusive_slots_are_not_replaceable_authority(successor,kind):
 f=successor;paths={'seal':f.root/m.SEAL_MARKER,'publication':f.root/m.PUBLICATION_VAULT,'mint':f.root/m.SUCCESSOR_MARKER,'access':Path(f.static['access_vault']),'period':Path(f.static['binding_fields']['period_vault_path']),'freeze':f.release/'FROZEN.json'};paths[kind].write_bytes(b'SYNTHETIC_PRIOR_CONSUMPTION');assert run(f)['status'].startswith('STOP_') and not f.calls

def test_same_or_missing_predecessor_state_key_refuses_before_intent(successor):
 f=successor
 for new,prior in [(OLD,OLD),(None,OLD),(NEW,None)]:assert run(f,new=new,prior=prior)['reason']=='FRESH_STATE_KEY_REQUIRED'
 assert not f.calls and not (f.root/m.SUCCESSOR_MARKER).exists()


def test_actual_connected_fixed_launcher_entries_through_restore(successor,mocked_sql,monkeypatch,capsys):
 f=successor;phases=[];entries=[];original_env=copy.deepcopy(f.api.env);revokes=[];old_used=[False]
 monkeypatch.setattr(client.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(client.sys.stderr,'isatty',lambda:True);monkeypatch.setattr(io,'Render',lambda _:f.api)
 import requests,psycopg
 monkeypatch.setattr(requests.sessions.Session,'request',lambda *a,**k:pytest.fail('NO_LIVE_HTTP'));monkeypatch.setattr(psycopg,'connect',lambda **k:pytest.fail('NO_LIVE_DB'))
 actual_mint=m.mint;actual_seal=m.seal
 monkeypatch.setattr(m,'mint',lambda a,h,k,v,**kw:actual_mint(a,h,k,v,clock=lambda:f.now,transport_factory=lambda *_:Transport(f),**kw))
 monkeypatch.setattr(m,'seal',lambda a,h,b,v,**kw:actual_seal(a,h,b,v,clock=lambda:f.now,**kw))
 actual_worker=client.worker
 def worker(phase,b,secret,vault,expected):
  phases.append(phase);assert secret['vault_key']==NEW
  if phase=='period':
   v=io.Vault(Path(vault),NEW,create=True);s=dict(version='FINITE_INTAKE_PERIOD_V1',state='ARMED_NO_RETRY',binding=b,policy=expected);v.save(s);return extra.issue_period(mocked_sql,b,expected,s,v.save)
  if phase=='activate':
   io.Vault(Path(vault),NEW,create=True).save(dict(version='FINITE_INTAKE_ACCESS_STATE_V1',state='ACTIVATION_ACKNOWLEDGED',binding=b,passwords={n:'SYNTHETIC_RUNTIME_'+n+'x'*48 for n in op.ROLES}));return dict(outcome='COMMIT_ACKNOWLEDGED',runtime_roles=sorted(op.ROLES),credentials='ENCRYPTED_LOCAL_ONLY',valid_until=b['valid_until'])
  if phase=='qualify':return dict(status='TWO_SINGLE_ATTEMPT_RESTRICTED_AUTHENTICATIONS_CLOSED',roles=[dict(role=n,attempts=1,closed=True) for n in sorted(op.ROLES)])
  if phase=='close':
   v=io.Vault(Path(vault),NEW);s=v.load();s.update(state='DATABASE_CLOSURE_ACKNOWLEDGED',passwords={});v.save(s);return dict(outcome='COMMIT_ACKNOWLEDGED',runtime_access='DISABLED',sessions='ABSENT')
  return actual_worker(phase,b,secret,vault,expected)
 monkeypatch.setattr(client,'worker',worker)
 actual_revoke=extra.token_revoke
 def runner(cmd,**kw):revokes.append(cmd);return subprocess.CompletedProcess(cmd,0,b'HTTP/2 204 OK\n',b'')
 monkeypatch.setattr(extra,'token_revoke',lambda b,s,save:actual_revoke(b,s,save,runner=runner))
 def capture(cmd,env,**kw):
  assert all(x not in repr(cmd) for x in [OLD,NEW,PASSWORD,TOKEN]);args=list(cmd[4:]);args[args.index('--secrets-fd')+1]=str(os.dup(int(args[args.index('--secrets-fd')+1])));timer=signal.getitimer(signal.ITIMER_REAL);signal.setitimer(signal.ITIMER_REAL,0);buf=stringio.StringIO()
  try:
   with contextlib.redirect_stdout(buf):code=(m.main if cmd[3].endswith('publication_mint') else client.main)(args)
  finally:signal.setitimer(signal.ITIMER_REAL,*timer)
  raw=buf.getvalue().encode();return raw,dict(exit_code=code,reason=None,client_closed=True,output_bytes=len(raw))
 monkeypatch.setattr(client,'capture',capture)
 def hidden(prompt):
  entries.append(prompt)
  if 'signing-key' in prompt:return PASSWORD
  if prompt.startswith('NEW ') or prompt.startswith('Confirm'):return NEW
  if prompt.startswith('B-state'):
   if not old_used[0]:old_used[0]=True;return OLD
   return NEW
  return 'SYNTHETIC_DB_OWNER' if 'Supabase' in prompt else 'SYNTHETIC_RENDER_KEY'
 monkeypatch.setattr(client,'hidden',hidden)
 actions=iter(['preview','bind']+['next']*8+['close','publication-revoke','handoff-restore','exit']);terminal=f.put(f.release/'mock-terminal.json',dict(job_id='job-'+'a'*20));th=m.digest(terminal.read_bytes())
 def answer(prompt):
  if prompt.startswith('Attended action'):return next(actions)
  if 'Approved phrase' in prompt or 'EXECUTE_EXACT_' in prompt:return prompt.split('(')[1].split(')')[0]
  if 'BIND_EXACT_' in prompt:return 'BIND_EXACT_35_MINUTE_RELEASE'
  if prompt.startswith('CONFIRM_FRESH_'):return prompt.split(':')[0]
  if 'expected' in prompt.lower() and 'SHA' not in prompt:return str(terminal)
  if 'SHA-256' in prompt:return th
  raise AssertionError('UNEXPECTED_NONSECRET_PROMPT')
 monkeypatch.setattr('builtins.input',answer)
 args=json.loads((DOC/'LAUNCHER-ENTRIES.json').read_bytes())['RUN-MINT-INACTIVE.sh']['arguments'];args[args.index('--authority')+1]=str(m.CORRECTED_AUTHORITY);args[args.index('--authority-sha256')+1]=m.CORRECTED_RAW_SHA
 assert m.main(args)==0
 assert f.calls==['GET','POST'] and f.closed==[True] and phases==['period','activate','qualify','handoff','submission-check','close','publication-revoke','handoff-restore']
 b=json.loads((f.release/'owner-binding.json').read_bytes());assert b['valid_until']==f.now+2100 and b['runtime_deadline']==b['valid_until']-185 and b['publication_valid_until']==f.expiry
 assert json.loads((f.release/'period-policy.json').read_bytes())['expires_at']==b['runtime_deadline'] and (f.release/'submission.intent.json').exists()
 assert f.api.env==original_env and f.api.env['PLAYWRIGHT_BROWSERS_PATH']=='0' and f.api.puts==2 and len(revokes)==1
 assert (f.root/m.SEAL_MARKER).exists() and (f.root/m.SEAL_OUTPUT/'result.json').exists() and io.Vault(f.root/m.PUBLICATION_VAULT,NEW).load()['state']=='REVOKED_ACKNOWLEDGED'
 preserved(f);out=capsys.readouterr();assert all(x not in out.out+out.err for x in [OLD,NEW,PASSWORD,TOKEN,'SYNTHETIC_DB_OWNER','SYNTHETIC_RENDER_KEY'])
 assert sum('signing-key' in x for x in entries)==1 and sum(x.startswith('NEW ') for x in entries)==1


def test_parent_existing_evidence_slot_refuses_before_hidden_input(successor,monkeypatch,capsys):
 f=successor;path=f.root/m.SUCCESSOR_OUTPUT;path.mkdir(mode=0o700);f.put(path/'original.json',dict(preserved=True));before=(path/'original.json').read_bytes()
 monkeypatch.setattr(client.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(client.sys.stderr,'isatty',lambda:True);monkeypatch.setattr('builtins.input',lambda _:'EXECUTE_ONE_REVOKED_PREPUT_SUCCESSOR_MINT');monkeypatch.setattr(client,'hidden',lambda _:pytest.fail('NO_HIDDEN_INPUT'))
 args=json.loads((DOC/'LAUNCHER-ENTRIES.json').read_bytes())['RUN-MINT-INACTIVE.sh']['arguments'];args[args.index('--authority')+1]=str(m.CORRECTED_AUTHORITY);args[args.index('--authority-sha256')+1]=m.CORRECTED_RAW_SHA
 assert m.main(args)==2 and not f.calls and not (f.root/m.SUCCESSOR_MARKER).exists() and (path/'original.json').read_bytes()==before
 assert 'EXISTING_ATTEMPT' in capsys.readouterr().out

@pytest.mark.parametrize('kind',['revocation_uncertain','access_not_closed','render_intent_present'])
def test_authenticated_predecessor_state_must_agree_with_receipts(successor,kind):
 f=successor;name=m.PREPUT_OLD_PUBLICATION if kind=='revocation_uncertain' else m.PREPUT_OLD_ACCESS;v=io.Vault(f.root/name,OLD);state=v.load()
 if kind=='revocation_uncertain':state['state']='REVOKE_INTENT_NO_RETRY'
 elif kind=='access_not_closed':state['state']='ACTIVATION_ACKNOWLEDGED'
 else:state['render']={'state':'PUT_INTENT_NO_RETRY'}
 v.save(state);m.PREPUT_PRIVATE_PROOFS[name]=m.digest((f.root/name).read_bytes())
 assert run(f)['reason']=='CLOSED_PREDECESSOR' and not f.calls and not (f.root/m.SUCCESSOR_MARKER).exists()


def test_wrong_approval_status_text_does_not_consume_slot(successor,monkeypatch,capsys):
 f=successor;monkeypatch.setattr(client.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(client.sys.stderr,'isatty',lambda:True);monkeypatch.setattr('builtins.input',lambda _:'MINT_RECEIPT_VALIDATED_NOT_ARMED');monkeypatch.setattr(client,'hidden',lambda _:pytest.fail('NO_HIDDEN_INPUT'))
 args=json.loads((DOC/'LAUNCHER-ENTRIES.json').read_bytes())['RUN-MINT-INACTIVE.sh']['arguments'];args[args.index('--authority')+1]=str(m.CORRECTED_AUTHORITY);args[args.index('--authority-sha256')+1]=m.CORRECTED_RAW_SHA
 assert m.main(args)==2 and not f.calls and not (f.root/m.SUCCESSOR_OUTPUT).exists() and not (f.root/m.SUCCESSOR_MARKER).exists()
 assert 'APPROVAL' in capsys.readouterr().out


def test_fresh_state_key_authenticates_against_exact_current_journal(successor,monkeypatch):
 f=successor;assert run(f)['status']=='MINT_RECEIPT_VALIDATED_NOT_ARMED';seen=[]
 def unlock(path,value):seen.append(Path(path));return io.Vault(Path(path),value).load()['state']=='RECEIPT_VALIDATED_NOT_ARMED'
 monkeypatch.setattr(client,'vault_unlock',unlock);monkeypatch.setattr(client,'hidden',lambda _:NEW)
 assert client.vault_input(f.root/'future-period.vault',create=True,mint_bound=True,authentication_path=f.root/m.SUCCESSOR_JOURNAL)==NEW
 assert seen==[f.root/m.SUCCESSOR_JOURNAL] and not (f.root/'future-period.vault').exists()


@pytest.mark.parametrize('which',['predecessor_submission','new_access_next'])
def test_dangling_symlink_is_uncertain_prior_state_not_unused(successor,which):
 f=successor;p=f.oldroot/'submission.intent.json' if which=='predecessor_submission' else Path(f.static['access_vault']+'.next');p.symlink_to(f.root/'NO_TARGET_SYNTHETIC')
 assert run(f)['status'].startswith('STOP_') and not f.calls and not (f.root/m.SUCCESSOR_MARKER).exists()
