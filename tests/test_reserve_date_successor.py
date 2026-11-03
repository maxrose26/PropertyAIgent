"""Fixed extension; synthetic keys and mocked parent/child/provider/DB only."""
import contextlib,copy,io as stringio,json,os,subprocess,signal
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
import pytest
from verification.ingestion_storage import publication_mint as m,finite_release_binding as flow,intake_owner_client as client,intake_owner as op,intake_owner_operations as extra,intake_owner_io as io
from tests.test_publication_mint import fx,synthetic_key,PASSWORD,VAULT,TOKEN
from tests.test_corrected_issuer_mint import corrected
from tests.test_expired_unused_successor import successor,run as old_run
from tests.test_intake_owner_operations import mocked_sql
from tests.test_intake_owner_io import API
DOC=Path('docs/design/b-reserve-date-successor-20261103')

@pytest.fixture
def reserve(successor,monkeypatch,tmp_path):
 f=successor;old=old_run(f);assert old['status']=='MINT_RECEIPT_VALIDATED_NOT_ARMED'
 prior=m.SUCCESSOR_JOURNAL;names=[prior,m.SUCCESSOR_MARKER,m.SUCCESSOR_OUTPUT+'/result.json']
 def put(p,v):
  p=Path(p);p.parent.mkdir(parents=True,exist_ok=True,mode=0o700);p.write_bytes(m.canonical(v));p.chmod(0o600);return p
 put(f.root/names[-1],dict(old,owner_process=dict(client_closed=True,exit_code=0,reason=None)))
 expiry=f.expiry;f.now=expiry+1;f.expiry=f.now+3600;f.value['expires_at']=datetime.fromtimestamp(f.expiry,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
 closure=put(f.root/'closure-new.json',dict(status='EXPIRED_UNUSED',recorded_expiry_epoch=expiry,observed_epoch=f.now,token_specific_revocation='NOT_PERFORMED',installation_removal='NOT_PERFORMED',later_phases_evidenced=False))
 proofs={**m.SUCCESSOR_PREDECESSOR_PROOFS,**{n:m.digest((f.root/n).read_bytes()) for n in names}}
 for n in names:f.preserved[f.root/n]=(f.root/n).read_bytes()
 f.preserved[closure]=closure.read_bytes()
 for n in ['SUCCESSOR_MARKER','SUCCESSOR_JOURNAL','SUCCESSOR_OUTPUT','SUCCESSOR_CLOSURE','SUCCESSOR_CLOSURE_SHA','PREDECESSOR_EXPIRY','PREDECESSOR_RECEIPT','SUCCESSOR_PREDECESSOR_PROOFS','SUCCESSOR_UNUSED_RELEASE','SUCCESSOR_PREDECESSOR_JOURNAL','SUCCESSOR_ATTEMPT']:monkeypatch.setattr(m,n,getattr(m,n))
 select=m.select_reserve_successor;unused=f.root/'previous-release';unused.mkdir()
 def mapped():
  select();m.SUCCESSOR_CLOSURE=closure;m.SUCCESSOR_CLOSURE_SHA=m.digest(closure.read_bytes());m.PREDECESSOR_EXPIRY=expiry;m.PREDECESSOR_RECEIPT=old['receipt_sha256'];m.SUCCESSOR_PREDECESSOR_PROOFS=dict(proofs);m.SUCCESSOR_UNUSED_RELEASE=unused;m.SUCCESSOR_PREDECESSOR_JOURNAL=prior
 monkeypatch.setattr(m,'select_reserve_successor',mapped);mapped()
 root=tmp_path/'new-owner/release';root.mkdir(parents=True,mode=0o700)
 s=json.loads((DOC/'STATIC-RELEASE.json').read_bytes());s['mint_authority'].update(predecessor_closure_sha256=m.SUCCESSOR_CLOSURE_SHA,predecessor_receipt_sha256=m.PREDECESSOR_RECEIPT);s.update(mint_journal_path=str(f.root/m.SUCCESSOR_JOURNAL),mint_result_path=str(f.root/m.SUCCESSOR_OUTPUT/'result.json'),access_vault=str(f.root/'access.vault'));s['binding_fields'].update(period_vault_path=str(f.root/'period.vault'),publication_vault_path=str(f.root/'publication-01.vault'))
 api=API();api.env.pop('INGESTION_RENDER_PROFILE');api.env['PLAYWRIGHT_BROWSERS_PATH']=s['binding_fields']['render_profile']['browser_path'];s['binding_fields']['render_config_sha256']=io.service_guard(api.service);api.session=SimpleNamespace(close=lambda:None)
 put(root/'STATIC-RELEASE.json',s);(root/'B-COMMAND.txt').write_bytes((DOC/'B-COMMAND.txt').read_bytes())
 for n,v in dict(TIMING_ROOT=root,TIMING_STATIC_SHA=m.digest((root/'STATIC-RELEASE.json').read_bytes()),PRIVATE=f.root,AUTHORITY=f.h,AUTHORITY_PATH=str(m.CORRECTED_AUTHORITY),AUTHORITY_RAW=m.CORRECTED_RAW_SHA).items():monkeypatch.setattr(flow,n,v)
 flow.use_timing_release();f.release=root;f.static=s;f.api=api;f.put=put;f.calls.clear();f.closed.clear();return f
class Transport:
 def __init__(self,f,error=False):self.f=f;self.error=error
 def call(self,method):
  f=self.f;f.calls.append(method)
  if method=='GET':return 200,m.canonical(f.install)
  assert json.loads((f.root/m.SUCCESSOR_MARKER).read_bytes())['attempt']=='ONE_B_PUBLICATION_MINT_RESERVE_V2_20261103_01'
  assert io.Vault(f.root/m.SUCCESSOR_JOURNAL,VAULT).load()['state']=='POST_INTENT_NO_RETRY'
  if self.error:raise TimeoutError('SYNTHETIC_SECRET_MUST_NOT_ESCAPE')
  return 201,m.canonical(f.value)
 def close(self):self.f.closed.append(True)
def run(f,error=False):return m.mint(f.a,f.h,PASSWORD,VAULT,clock=lambda:f.now,transport_factory=lambda *_:Transport(f,error),successor=True)
def preserved(f):assert all(p.read_bytes()==b for p,b in f.preserved.items())

def test_fixed_authority_one_post_and_predecessors_preserved(reserve):
 f=reserve;assert run(f)['status']=='MINT_RECEIPT_VALIDATED_NOT_ARMED';assert run(f)['mint_outcome']=='PRIOR_ATTEMPT_RECONCILE';assert f.calls==['GET','POST'];preserved(f)
 record=json.loads((f.root/m.SUCCESSOR_MARKER).read_bytes());assert record['predecessor_receipt_sha256']==m.PREDECESSOR_RECEIPT and record['predecessor_closure_sha256']==m.SUCCESSOR_CLOSURE_SHA
 assert TOKEN.encode() not in (f.root/m.SUCCESSOR_JOURNAL).read_bytes()
def test_uncertain_post_no_replay(reserve):
 f=reserve;assert run(f,True)['mint_outcome']=='UNCERTAIN';assert run(f)['mint_outcome']=='PRIOR_ATTEMPT_RECONCILE';assert f.calls==['GET','POST'];preserved(f)
@pytest.mark.parametrize('kind',['marker','journal','closure','later_phase'])
def test_predecessor_drift_refuses_before_post(reserve,kind):
 f=reserve
 if kind=='later_phase':(m.SUCCESSOR_UNUSED_RELEASE/'submission.intent.json').write_text('SYNTHETIC')
 elif kind=='closure':m.SUCCESSOR_CLOSURE_SHA='0'*64
 else:(f.root/('mint-expired-unused-successor-01-consumed.json' if kind=='marker' else 'mint-expired-unused-successor-01.vault')).write_bytes(b'SYNTHETIC_DRIFT')
 assert run(f)['status'].startswith('STOP_') and not f.calls and not (f.root/m.SUCCESSOR_MARKER).exists()
def test_old_entries_cannot_replay(reserve):
 f=reserve;assert m.mint(f.a,f.h,PASSWORD,VAULT)['reason']=='EXISTING_ATTEMPT';assert m.mint(f.a,f.h,PASSWORD,VAULT,corrected_replacement=True)['reason']=='EXISTING_ATTEMPT';assert not f.calls;preserved(f)
def test_date_template_and_explicit_authority():
 s=json.loads((DOC/'STATIC-RELEASE.json').read_bytes());assert s['execution_day']=='2026-11-03' and s['window']==dict(start='2026-10-27',end='2026-11-02',inclusive=True,tameside='RECEIVED',manchester='VALIDATED')
 assert s['mint_authority']['attempt']=='ONE_B_PUBLICATION_MINT_RESERVE_V2_20261103_01' and s['mint_authority']['max_mint_posts']==1 and s['policy_fields']['max_runs']==1
 assert s['B_command_sha256']==m.digest((DOC/'B-COMMAND.txt').read_bytes()) and s['binding_fields']['render_profile']['aggregate_bytes']==2147483648
@pytest.mark.parametrize('delta',[-86400,86400])
def test_wrong_day_no_intent(reserve,delta):
 f=reserve
 with pytest.raises(m.Refusal):m.successor_preconditions(f.a,f.h,now=f.now+delta)
 assert not f.calls and not (f.root/m.SUCCESSOR_MARKER).exists()

def test_connected_actual_entries_through_independent_closure(reserve,mocked_sql,monkeypatch,capsys):
 f=reserve;phases=[];hidden=[];original_env=copy.deepcopy(f.api.env);revocations=[]
 monkeypatch.setattr(client.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(client.sys.stderr,'isatty',lambda:True);monkeypatch.setattr(io,'Render',lambda _:f.api)
 import requests,psycopg
 monkeypatch.setattr(requests.sessions.Session,'request',lambda *a,**k:pytest.fail('LIVE_HTTP_FORBIDDEN'));monkeypatch.setattr(psycopg,'connect',lambda **k:pytest.fail('LIVE_DATABASE_FORBIDDEN'))
 actual_mint=m.mint;monkeypatch.setattr(m,'mint',lambda a,h,k,v,**kw:actual_mint(a,h,k,v,transport_factory=lambda *_:Transport(f),clock=lambda:f.now,**kw))
 actual_seal=m.seal;monkeypatch.setattr(m,'seal',lambda a,h,b,v,**kw:actual_seal(a,h,b,v,clock=lambda:f.now,**kw))
 actual_worker=client.worker
 def worker(phase,b,secrets,vault,expected):
  phases.append(phase)
  if phase=='period':
   v=io.Vault(Path(vault),VAULT,create=True);state=dict(version='FINITE_INTAKE_PERIOD_V1',state='ARMED_NO_RETRY',binding=b,policy=expected);v.save(state);return extra.issue_period(mocked_sql,b,expected,state,v.save)
  if phase=='activate':
   io.Vault(Path(vault),VAULT,create=True).save(dict(state='ACTIVATION_ACKNOWLEDGED',binding=b,passwords={n:'SYNTHETIC_RUNTIME_PASSWORD_'+n for n in op.ROLES}));return dict(outcome='COMMIT_ACKNOWLEDGED',runtime_roles=sorted(op.ROLES),credentials='ENCRYPTED_LOCAL_ONLY',valid_until=b['valid_until'])
  if phase=='qualify':return dict(status='TWO_SINGLE_ATTEMPT_RESTRICTED_AUTHENTICATIONS_CLOSED',roles=[dict(role=n,attempts=1,closed=True) for n in sorted(op.ROLES)])
  if phase=='close':
   v=io.Vault(Path(vault),VAULT);s=v.load();s['state']='DATABASE_CLOSURE_ACKNOWLEDGED';v.save(s);return dict(outcome='COMMIT_ACKNOWLEDGED',runtime_access='DISABLED',sessions='ABSENT')
  return actual_worker(phase,b,secrets,vault,expected)
 monkeypatch.setattr(client,'worker',worker)
 real_revoke=extra.token_revoke
 def runner(cmd,**kw):revocations.append(cmd);return subprocess.CompletedProcess(cmd,0,b'HTTP/2 204 No Content\n',b'')
 monkeypatch.setattr(extra,'token_revoke',lambda b,s,save:real_revoke(b,s,save,runner=runner))
 def capture(cmd,env,**kw):
  assert set(env)=={'HOME','PATH','LANG','PYTHONDONTWRITEBYTECODE','OPENBLAS_NUM_THREADS'}
  assert all(x not in repr(cmd) for x in [PASSWORD,VAULT,TOKEN]);buf=stringio.StringIO()
  child=list(cmd[4:]);child[child.index('--secrets-fd')+1]=str(os.dup(int(child[child.index('--secrets-fd')+1])))
  timer=signal.getitimer(signal.ITIMER_REAL);signal.setitimer(signal.ITIMER_REAL,0)
  try:
   with contextlib.redirect_stdout(buf):code=(m.main if cmd[3].endswith('publication_mint') else client.main)(child)
  finally:signal.setitimer(signal.ITIMER_REAL,*timer)
  raw=buf.getvalue().encode();return raw,dict(exit_code=code,reason=None,client_closed=True,output_bytes=len(raw))
 monkeypatch.setattr(client,'capture',capture)
 def secret(prompt):hidden.append(prompt);return PASSWORD if 'signing-key' in prompt else VAULT if 'Vault' in prompt else 'SYNTHETIC_DB_PASSWORD' if 'Supabase' in prompt else 'SYNTHETIC_RENDER_KEY'
 monkeypatch.setattr(client,'hidden',secret)
 actions=iter(['preview','bind']+['next']*8+['close','publication-revoke','handoff-restore','exit'])
 terminal=f.put(f.release/'synthetic-terminal.json',dict(job_id='job-'+'a'*20));terminalhash=m.digest(terminal.read_bytes())
 def answer(prompt):
  if prompt.startswith('Attended action'):return next(actions)
  if 'Approved phrase' in prompt:return prompt.split('(')[1].split(')')[0]
  if prompt.startswith('CONFIRM_FRESH_'):return prompt.split(':')[0]
  if 'BIND_EXACT_' in prompt:return 'BIND_EXACT_35_MINUTE_RELEASE'
  if 'EXECUTE_EXACT_' in prompt:return prompt.split('(')[1].split(')')[0]
  if 'expected' in prompt.lower() and 'SHA' not in prompt:return str(terminal)
  if 'SHA-256' in prompt:return terminalhash
  raise AssertionError('UNEXPECTED_PROMPT:'+prompt)
 monkeypatch.setattr('builtins.input',answer)
 args=json.loads((DOC/'LAUNCHER-ENTRIES.json').read_bytes())['RUN-MINT-INACTIVE.sh']['arguments']
 args[args.index('--authority')+1]=str(m.CORRECTED_AUTHORITY);args[args.index('--authority-sha256')+1]=m.CORRECTED_RAW_SHA
 assert m.main(args)==0
 assert f.calls==['GET','POST'] and f.closed==[True]
 assert phases==['period','activate','qualify','handoff','submission-check','close','publication-revoke','handoff-restore']
 b=json.loads((f.release/'owner-binding.json').read_bytes());assert b['valid_until']==f.now+2100 and b['runtime_deadline']==b['valid_until']-185 and b['publication_valid_until']==f.expiry
 assert json.loads((f.release/'period-policy.json').read_bytes())['expires_at']==b['runtime_deadline']
 assert (f.release/'submission.intent.json').exists() and f.api.puts==2 and f.api.env==original_env and len(revocations)==1
 assert io.Vault(Path(b['publication_vault_path']),VAULT).load()['token']=='';preserved(f)
 out=capsys.readouterr();assert all(x not in out.out+out.err for x in [PASSWORD,VAULT,TOKEN,'SYNTHETIC_DB_PASSWORD','SYNTHETIC_RENDER_KEY'])
 assert sum('signing-key' in x for x in hidden)==1
 assert actual_mint(f.a,f.h,PASSWORD,VAULT,clock=lambda:f.now,transport_factory=lambda *_:Transport(f),successor=True)['mint_outcome']=='PRIOR_ATTEMPT_RECONCILE' and f.calls==['GET','POST']

@pytest.mark.parametrize('which',['freeze','period_vault','access_vault','observation'])
def test_existing_new_release_state_is_not_new_mint_authority(reserve,which):
 f=reserve;path=f.release/'FROZEN.json' if which=='freeze' else Path(f.static['binding_fields']['period_vault_path']) if which=='period_vault' else Path(f.static['access_vault']) if which=='access_vault' else f.release/'handoff-observation.json'
 path.write_text('SYNTHETIC_PRIOR_STATE');assert run(f)['reason']=='EXISTING_ATTEMPT' and not f.calls and not (f.root/m.SUCCESSOR_MARKER).exists()

def test_static_hash_drift_refuses_before_credentials_or_intent(reserve):
 f=reserve;(f.release/'STATIC-RELEASE.json').write_text('{}');assert run(f)['status'].startswith('STOP_') and not f.calls and not (f.root/m.SUCCESSOR_MARKER).exists()
