"""Synthetic keys/tokens and mocked requests only. Never touch owner credentials."""
import base64,copy,hashlib,json,os,subprocess,time
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
import pytest
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding,rsa
from verification.ingestion_storage import publication_mint as m,intake_owner as op,intake_owner_client as client,intake_owner_operations as extra
from verification.ingestion_storage.intake_owner_io import Vault
from tests.test_intake_owner_operations import inputs

PASSWORD='SYNTHETIC_KEY_PASSWORD_ONLY';VAULT='SYNTHETIC_VAULT_PASSPHRASE_24_PLUS';TOKEN='ghs_SYNTHETIC_NOT_A_REAL_TOKEN_'+('x'*490)

@pytest.fixture(scope='module')
def synthetic_key():
 return rsa.generate_private_key(public_exponent=65537,key_size=2048)

@pytest.fixture
def fx(tmp_path,monkeypatch,synthetic_key):
 root=tmp_path/'private';root.mkdir(mode=0o700);monkeypatch.setattr(m,'ROOT',root)
 public=synthetic_key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
 a=dict(version='FIXED_B_PUBLICATION_APP_V1',attempt=m.ATTEMPT,app_id=123456,client_id='Iv1.SYNTHETIC',installation_id=654321,app_slug=m.SLUG,repository=m.REPOSITORY,repository_id=m.REPOSITORY_ID,permissions=m.PERMISSIONS,key_fingerprint=base64.b64encode(hashlib.sha256(public).digest()).decode(),application=op.APPLICATION_BINDING)
 pem=synthetic_key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.BestAvailableEncryption(PASSWORD.encode()));(root/'signing-key.pem').write_bytes(pem);(root/'signing-key.pem').chmod(0o600)
 now=int(time.time());expiry=now+3600
 value=dict(token=TOKEN,permissions=copy.deepcopy(m.PERMISSIONS),repository_selection='selected',repositories=[dict(id=m.REPOSITORY_ID,full_name=m.REPOSITORY)],expires_at=datetime.fromtimestamp(expiry,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
 install=dict(id=a['installation_id'],app_id=a['app_id'],app_slug=m.SLUG,account=dict(login='maxrose26',type='User'),repository_selection='selected',suspended_at=None,permissions=m.PERMISSIONS)
 return SimpleNamespace(root=root,a=a,h=m.digest(m.canonical(a)),now=now,expiry=expiry,value=value,install=install,key=synthetic_key,calls=[],closed=[])

class Fake:
 def __init__(self,f,*,error=None,install=None,value=None,status=201,prepost=None,close_error=False):self.f=f;self.error=error;self.install=f.install if install is None else install;self.value=f.value if value is None else value;self.status=status;self.prepost=prepost;self.close_error=close_error
 def call(self,method):
  self.f.calls.append(method)
  if method=='GET':return 200,m.canonical(self.install)
  # Authentic state transition must be persisted before the mutation boundary.
  assert (self.f.root/'mint-01-consumed.json').exists()
  assert Vault(self.f.root/'mint-01.vault',VAULT).load()['state']=='POST_INTENT_NO_RETRY'
  if self.prepost:self.prepost()
  if self.error:raise self.error
  return self.status,self.value if type(self.value) is bytes else m.canonical(self.value)
 def close(self):
  self.f.closed.append(True)
  if self.close_error:raise RuntimeError('SENSITIVE_CLOSE_SENTINEL')

def run(f,**kw):
 factory=lambda a,jwt:Fake(f,**kw)
 return m.mint(f.a,f.h,PASSWORD,VAULT,transport_factory=factory,clock=lambda:f.now)

def state(f):return Vault(f.root/'mint-01.vault',VAULT).load()
def binding(f,tmp_path):
 b,_=inputs(tmp_path);s=state(f);b.update(publication_valid_until=f.expiry,valid_until=f.expiry,publication_vault_path=str(f.root/'publication-01.vault'),publication_scope=dict(repository=m.REPOSITORY,**m.PERMISSIONS),publication_mint=dict(authority_sha256=f.h,receipt_sha256=s['receipt_sha256'],expires_at=f.expiry));return b

def test_success_signature_receipt_private_storage(fx):
 f=fx;seen=[]
 def factory(a,jwt):seen.append(jwt);return Fake(f)
 result=m.mint(f.a,f.h,PASSWORD,VAULT,transport_factory=factory,clock=lambda:f.now)
 assert result['status']=='MINT_RECEIPT_VALIDATED_NOT_ARMED' and f.calls==['GET','POST'] and f.closed==[True]
 head,claims,sig=seen[0].split('.');dec=lambda s:base64.urlsafe_b64decode(s+'='*(-len(s)%4))
 assert json.loads(dec(head))==dict(alg='RS256',typ='JWT')
 assert json.loads(dec(claims))==dict(iat=f.now-60,exp=f.now+300,iss=f.a['client_id'])
 f.key.public_key().verify(dec(sig),(head+'.'+claims).encode(),padding.PKCS1v15(),hashes.SHA256())
 s=state(f);assert s['token_candidate']==TOKEN and s['receipt']['expiry']==f.expiry
 assert TOKEN not in json.dumps(result) and seen[0] not in json.dumps(result)
 for name in ('mint-01.vault','mint-01-consumed.json'):
  raw=(f.root/name).read_bytes();assert TOKEN.encode() not in raw and seen[0].encode() not in raw and b'PRIVATE KEY' not in raw and (f.root/name).stat().st_mode&0o777==0o600

@pytest.mark.parametrize('field,value',[('app_id',True),('installation_id',0),('repository','other/repo'),('repository_id',1),('app_slug','different'),('permissions',{'contents':'write','metadata':'read','actions':'write'}),('attempt','SECOND_ATTEMPT'),('application',dict(revision='other'))])
def test_wrong_authority_refuses_without_key_or_request(fx,field,value):
 f=fx;f.a[field]=value;f.h=m.digest(m.canonical(f.a));r=run(f)
 assert r['reason']=='AUTHORITY' and r['mint_outcome']=='DEFINITELY_NOT_SENT' and not f.calls and not (f.root/'mint-01-consumed.json').exists()

@pytest.mark.parametrize('field,value',[('id',9),('app_id',9),('app_slug','other'),('permissions',{'contents':'read','metadata':'read'}),('repository_selection','all'),('suspended_at','2026-01-01T00:00:00Z'),('account',{'login':'other','type':'User'})])
def test_wrong_installation_is_definitely_unsent(fx,field,value):
 f=fx;x=copy.deepcopy(f.install);x[field]=value;r=run(f,install=x)
 assert r['reason']=='INSTALLATION' and r['mint_outcome']=='DEFINITELY_NOT_SENT' and f.calls==['GET'] and state(f)['post_started'] is False

@pytest.mark.parametrize('field,value',[('permissions',{'contents':'write','metadata':'read','issues':'write'}),('repository_selection','all'),('repositories',[]),('repositories',[dict(id=8,full_name=m.REPOSITORY)]),('repositories',[dict(id=m.REPOSITORY_ID,full_name='wrong/name')]),('repositories',[dict(id=m.REPOSITORY_ID,full_name=m.REPOSITORY)]*2)])
def test_wrong_minted_scope_preserves_token_but_cannot_arm(fx,tmp_path,field,value):
 f=fx;v=copy.deepcopy(f.value);v[field]=value;r=run(f,value=v)
 assert r['reason']=='SCOPE' and r['mint_outcome']=='MINTED_REQUIRES_CLOSURE'
 assert state(f)['token_candidate']==TOKEN and 'receipt' not in state(f)
 assert m.seal(f.a,f.h,{},VAULT)['reason']=='RECEIPT' and not (f.root/'publication-01.vault').exists()

@pytest.mark.parametrize('raw',[b'{bad',b'null',b'[]',b'{"token":"x","token":"y"}',b'{"token":NaN}',b'x'*32769])
def test_malformed_acknowledged_response_never_success(fx,raw):
 f=fx;r=run(f,value=raw);assert r['status'].startswith('STOP_') and f.calls==['GET','POST'] and r['mint_outcome']=='MINTED_REQUIRES_CLOSURE'

@pytest.mark.parametrize('token',[None,123,'ghp_'+'x'*80,'ghs_'+'x'*2045,'ghs_'+('x'*30)+'\n'])
def test_malformed_token_refuses(fx,token):
 f=fx;v=dict(f.value,token=token);r=run(f,value=v);assert r['reason']=='TOKEN' and r['mint_outcome']=='MINTED_REQUIRES_CLOSURE'

@pytest.mark.parametrize('change',[None,'tomorrow','2026-02-30T10:00:00Z','2026-11-01T00:00:00+00:00',0,1145,3661])
def test_expiry_missing_invalid_short_or_implausible_refuses(fx,change):
 f=fx;expires=datetime.fromtimestamp(f.now+change,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') if type(change) is int else change
 r=run(f,value=dict(f.value,expires_at=expires));assert r['reason']=='EXPIRY' and state(f)['token_candidate']==TOKEN

@pytest.mark.parametrize('exc',[TimeoutError('SENSITIVE_TIMEOUT_SENTINEL'),RuntimeError('SENSITIVE_UNKNOWN_SENTINEL')])
def test_post_exception_is_uncertain_never_retries(fx,exc):
 f=fx;r=run(f,error=exc);assert r['mint_outcome']=='UNCERTAIN' and r['reason']==('TRANSPORT_TIMEOUT' if isinstance(exc,TimeoutError) else 'UNKNOWN') and f.calls==['GET','POST'] and state(f)['state']=='MINT_OUTCOME_UNCERTAIN'
 again=run(f);assert again['status'].startswith('STOP_') and f.calls==['GET','POST']
 assert 'SENSITIVE' not in json.dumps(r)

def test_get_timeout_is_definitely_unsent(fx):
 f=fx
 class Bad(Fake):
  def call(self,method):f.calls.append(method);raise TimeoutError('PRIVATE_SENTINEL')
 r=m.mint(f.a,f.h,PASSWORD,VAULT,transport_factory=lambda a,j:Bad(f),clock=lambda:f.now)
 assert r['mint_outcome']=='DEFINITELY_NOT_SENT' and f.calls==['GET'] and state(f)['state']=='REFUSED_POST_NOT_SENT'

@pytest.mark.parametrize('point',['intent','candidate','validated'])
def test_journal_failure_before_or_after_post_is_safe(fx,monkeypatch,point):
 f=fx;original=Vault.save
 def save(self,v):
  if (point=='intent' and v.get('state')=='POST_INTENT_NO_RETRY') or (point=='candidate' and v.get('state')=='MINTED_UNVALIDATED_REQUIRES_CLOSURE') or (point=='validated' and v.get('state')=='RECEIPT_VALIDATED_NOT_ARMED'):raise OSError('SECRET_STORAGE_SENTINEL')
  return original(self,v)
 monkeypatch.setattr(Vault,'save',save);r=run(f)
 assert r['status'].startswith('STOP_') and 'SECRET' not in json.dumps(r)
 assert r['mint_outcome']==('DEFINITELY_NOT_SENT' if point=='intent' else 'MINTED_REQUIRES_CLOSURE')
 assert f.calls==(['GET'] if point=='intent' else ['GET','POST'])

def test_aged_seal_and_existing_independent_revocation(fx,tmp_path):
 f=fx;assert run(f)['status']=='MINT_RECEIPT_VALIDATED_NOT_ARMED';b=binding(f,tmp_path)
 # Fresh token is deliberately too early; no seal intent consumed by waiting.
 r=m.seal(f.a,f.h,b,VAULT,clock=lambda:f.now);assert r['reason']=='WINDOW' and not (f.root/'seal-01-consumed.json').exists()
 now=f.expiry-1800;r=m.seal(f.a,f.h,b,VAULT,clock=lambda:now)
 assert r['status']=='PRIVATE_PUBLICATION_TOKEN_ARMED' and r['provider_calls']==0 and state(f)['state']=='SEALED_ACKNOWLEDGED' and 'token_candidate' not in state(f)
 target=Vault(f.root/'publication-01.vault',VAULT);s=target.load();assert extra.token_load(b,s)==TOKEN
 calls=[]
 def runner(cmd,**kw):
  calls.append(cmd);assert TOKEN not in repr(cmd);return subprocess.CompletedProcess(cmd,0,b'HTTP/2.0 204 No Content\n',b'')
 assert extra.token_revoke(b,s,target.save,runner=runner)['status']=='PUBLICATION_TOKEN_REVOCATION_ACKNOWLEDGED'
 assert target.load()['token']=='' and len(calls)==1
 with pytest.raises(op.Denied):extra.token_revoke(b,target.load(),target.save,runner=runner)
 assert m.seal(f.a,f.h,b,VAULT,clock=lambda:now)['status'].startswith('STOP_') and len(calls)==1 and f.calls==['GET','POST']

@pytest.mark.parametrize('seconds',[0,960,1145,1445,2101,3600])
def test_seal_rejects_insufficient_or_too_early_window(fx,tmp_path,seconds):
 f=fx;run(f);b=binding(f,tmp_path);r=m.seal(f.a,f.h,b,VAULT,clock=lambda:f.expiry-seconds)
 assert r['reason']=='WINDOW' and not (f.root/'publication-01.vault').exists()

@pytest.mark.parametrize('field,value',[('publication_valid_until',1),('valid_until',1),('publication_scope',{'repository':m.REPOSITORY,'contents':'read','metadata':'read'}),('publication_vault_path','/tmp/unreviewed'),('publication_mint',{})])
def test_seal_wrong_binding_refuses_before_creating_target(fx,tmp_path,field,value):
 f=fx;run(f);b=binding(f,tmp_path);b[field]=value;r=m.seal(f.a,f.h,b,VAULT,clock=lambda:f.expiry-1800)
 assert r['reason']=='BINDING' and not (f.root/'seal-01-consumed.json').exists()

@pytest.mark.parametrize('point',['intent','arm','final_ack'])
def test_sealing_failure_is_consumed_no_automatic_rearm(fx,tmp_path,monkeypatch,point):
 f=fx;run(f);b=binding(f,tmp_path);orig=Vault.save
 def save(self,v):
  if (point=='intent' and v.get('state')=='SEAL_INTENT_NO_RETRY') or (point=='arm' and v.get('version')=='FINITE_PUBLICATION_TOKEN_V1') or (point=='final_ack' and v.get('state')=='SEALED_ACKNOWLEDGED'):raise OSError('SENSITIVE_SEAL_SENTINEL')
  return orig(self,v)
 monkeypatch.setattr(Vault,'save',save);r=m.seal(f.a,f.h,b,VAULT,clock=lambda:f.expiry-1800)
 assert r['mint_outcome']=='SEAL_UNCERTAIN_RECONCILE' and (f.root/'seal-01-consumed.json').exists() and f.calls==['GET','POST']
 assert m.seal(f.a,f.h,b,VAULT,clock=lambda:f.expiry-1800)['status'].startswith('STOP_')
 if point=='final_ack':assert extra.token_load(b,Vault(f.root/'publication-01.vault',VAULT).load())==TOKEN

def test_activation_refuses_before_connection_and_server_clock_guard(fx,tmp_path,monkeypatch):
 f=fx;run(f);b=binding(f,tmp_path);monkeypatch.setattr(op.time,'time',lambda:f.expiry-1100)
 with pytest.raises(op.Denied,match='MINT_B_AND_CLOSURE_WINDOW'):client.worker('activate',b,{},str(tmp_path/'not-created'),{})
 assert not (tmp_path/'not-created').exists()
 monkeypatch.setattr(op.time,'time',lambda:f.expiry-1800)
 with pytest.raises(op.Denied,match='MINT_B_AND_CLOSURE_WINDOW'):op.validate_binding(b,opening=True,now=f.expiry-1145)
 op.validate_binding(b,opening=True,now=f.expiry-1800)
 # Historical bindings keep the original960..2100 limit, unchanged.
 b.pop('publication_mint');op.validate_binding(b,opening=True,now=f.expiry-1100)

def test_path_and_key_fingerprint_refusals(fx):
 f=fx;(f.root/'signing-key.pem').chmod(0o644);assert run(f)['reason']=='PRIVATE_FILE' and not f.calls

@pytest.mark.parametrize('kind',['symlink','hardlink','wrong_fingerprint'])
def test_unsafe_key_or_identity_refuses_before_get(fx,kind):
 f=fx;p=f.root/'signing-key.pem'
 if kind=='symlink':p.rename(f.root/'saved');p.symlink_to(f.root/'saved')
 elif kind=='hardlink':os.link(p,f.root/'copy')
 else:f.a['key_fingerprint']='A'*43+'=';f.h=m.digest(m.canonical(f.a))
 assert run(f)['status'].startswith('STOP_') and not f.calls

def test_real_requests_configuration_is_credential_isolated(fx,monkeypatch):
 import requests
 f=fx;seen=[];session=SimpleNamespace(trust_env=True,mount=lambda *a:None,close=lambda:None)
 class Response:
  status_code=200
  def __enter__(self):return self
  def __exit__(self,*a):pass
  def iter_content(self,n):yield b'{}'
 def request(method,url,**kw):seen.append((method,url,kw));return Response()
 session.request=request;monkeypatch.setattr(requests,'Session',lambda:session)
 monkeypatch.setenv('GH_TOKEN','SYNTHETIC_INHERITED_TOKEN');monkeypatch.setenv('HTTPS_PROXY','http://SYNTHETIC_PROXY')
 t=m.Transport(f.a,'SYNTHETIC_APP_JWT');t.call('GET');t.call('POST')
 assert session.trust_env is False
 assert [x[0] for x in seen]==['GET','POST'] and seen[1][2]['json']==m.BODY
 assert seen[1][1]==m.API+'/app/installations/654321/access_tokens'
 for method,url,kw in seen:assert kw['verify'] is True and kw['allow_redirects'] is False and kw['stream'] is True and kw['timeout']==(5,5) and kw['headers']['Authorization']=='Bearer SYNTHETIC_APP_JWT'
 with pytest.raises(m.Refusal):t.call('POST')
 t.close();assert t.jwt is None

def test_transport_overflow_does_not_return_body(fx,monkeypatch):
 import requests
 f=fx
 class Response:
  status_code=201
  def __enter__(self):return self
  def __exit__(self,*a):pass
  def iter_content(self,n):yield b'SENSITIVE_BODY'*3000
 session=SimpleNamespace(trust_env=True,mount=lambda *a:None,close=lambda:None,request=lambda *a,**kw:Response());monkeypatch.setattr(requests,'Session',lambda:session)
 t=m.Transport(f.a,'SYNTHETIC_JWT')
 with pytest.raises(m.Refusal,match='RESPONSE_BOUND'):t.call('GET')

@pytest.mark.parametrize('operation',['mint','seal'])
def test_terminal_failure_output_bounded_and_suppresses_arbitrary_errors(fx,monkeypatch,capsys,operation):
 f=fx;authority=f.root/'authority.json';authority.write_bytes(m.canonical(f.a));authority.chmod(0o600)
 monkeypatch.setattr(m.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(m.sys.stderr,'isatty',lambda:True)
 monkeypatch.setattr('builtins.input',lambda _: 'EXECUTE_ONE_B_PUBLICATION_TOKEN_MINT' if operation=='mint' else 'SEAL_EXACT_B_PUBLICATION_TOKEN_ONCE')
 monkeypatch.setattr(m,'hidden',lambda prompt:PASSWORD if 'PEM' in prompt else VAULT)
 monkeypatch.setattr(client,'capture',lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('SECRET_TERMINAL_SENTINEL'*10000)))
 args=['--phase',operation,'--authority',str(authority),'--authority-sha256',m.digest(authority.read_bytes())]
 if operation=='seal':args+=['--binding','/nonexistent/SENSITIVE_BINDING_SENTINEL','--binding-sha256','0'*64]
 assert m.main(args)==2;out=capsys.readouterr().out
 assert len(out.encode())<2048 and 'SENTINEL' not in out and TOKEN not in out and PASSWORD not in out and VAULT not in out

@pytest.mark.parametrize('minted',[False,True])
def test_cleanup_failure_is_refusal_not_success(fx,minted):
 f=fx;x=copy.deepcopy(f.install)
 if not minted:x['app_id']=9
 r=run(f,install=x,close_error=True)
 assert r['reason']=='CLEANUP' and r['mint_outcome']==('MINTED_REQUIRES_CLOSURE' if minted else 'DEFINITELY_NOT_SENT')
 assert state(f)['state']=='TRANSPORT_CLEANUP_REQUIRES_CLOSURE' and 'SENSITIVE' not in json.dumps(r)

def test_repeat_invocation_does_not_reclassify_prior_outcome(fx):
 f=fx;run(f);r=run(f)
 assert r['reason']=='EXISTING_ATTEMPT' and r['mint_outcome']=='PRIOR_ATTEMPT_RECONCILE' and f.calls==['GET','POST']

@pytest.mark.parametrize('code',['MINT_RECEIPT_BINDING','MINT_B_AND_CLOSURE_WINDOW'])
def test_new_timing_diagnostics_are_allowlisted(code):
 r=json.loads(client.failure_output('activate',op.Denied(code)))
 assert r['failure_reason']==code and len(json.dumps(r))<1024

@pytest.mark.parametrize('after_post',[False,True])
def test_clock_drift_refuses_without_false_time_claim(fx,after_post):
 f=fx;values=iter([f.now,f.now if after_post else f.now+10,f.now,f.now+10])
 r=m.mint(f.a,f.h,PASSWORD,VAULT,transport_factory=lambda a,j:Fake(f),clock=lambda:next(values))
 assert r['reason']=='CLOCK' and r['mint_outcome']==('MINTED_REQUIRES_CLOSURE' if after_post else 'DEFINITELY_NOT_SENT')

@pytest.mark.parametrize('status',[200,302,401,403,429,500])
def test_non201_post_response_is_consumed_uncertainty(fx,status):
 f=fx;r=run(f,status=status)
 assert r['reason']=='HTTP' and r['mint_outcome']=='UNCERTAIN' and state(f)['state']=='MINT_OUTCOME_UNCERTAIN'

def test_envelope_expiration_fixed_and_timer_restored():
 import signal
 with pytest.raises(m.Refusal,match='DEADLINE'):
  with m.envelope():signal.getsignal(signal.SIGALRM)()
 assert signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0)

def test_activation_server_clock_refuses_before_owner_entry(fx,tmp_path,monkeypatch):
 f=fx;run(f);b=binding(f,tmp_path);monkeypatch.setattr(op.time,'time',lambda:f.expiry-1800)
 for n in ('begin','admin_capabilities','inventory'):monkeypatch.setattr(op,n,lambda *a,**kw:None)
 monkeypatch.setattr(op,'dormant',lambda *_:[]);monkeypatch.setattr(op,'control',lambda *_:{})
 entered=[];monkeypatch.setattr(op,'enter_owner',lambda *_:entered.append(True))
 class C:
  def execute(self,sql,params=None):
   if 'clock_timestamp' in sql:return SimpleNamespace(fetchone=lambda:(f.expiry-1100,))
   assert sql=='ROLLBACK'
 with pytest.raises(op.Denied,match='MINT_B_AND_CLOSURE_WINDOW'):op.activate(C(),b,lambda _:None,password_factory=lambda:'SYNTHETIC'*8)
 assert entered==[]

def test_private_authority_hash_and_duplicate_json_refuse(fx):
 f=fx;p=f.root/'authority.json';p.write_bytes(m.canonical(f.a));p.chmod(0o600)
 with pytest.raises(m.Refusal,match='FILE_HASH'):m.load_file(p,'0'*64)
 with pytest.raises(m.Refusal,match='JSON'):m.parse(b'{"app_id":1,"app_id":2}')

def test_terminal_success_writes_bounded_nonsecret_evidence(fx,monkeypatch,capsys):
 f=fx;p=f.root/'authority.json';p.write_bytes(m.canonical(f.a));p.chmod(0o600)
 monkeypatch.setattr(m.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(m.sys.stderr,'isatty',lambda:True)
 monkeypatch.setattr('builtins.input',lambda _:'EXECUTE_ONE_B_PUBLICATION_TOKEN_MINT')
 monkeypatch.setattr(m,'hidden',lambda prompt:PASSWORD if 'PEM' in prompt else VAULT)
 def capture(*args,**kw):
  r=m.mint(f.a,f.h,PASSWORD,VAULT,transport_factory=lambda a,j:Fake(f),clock=lambda:f.now)
  return m.canonical(r),dict(exit_code=0,reason=None,client_closed=True,output_bytes=len(m.canonical(r)))
 monkeypatch.setattr(client,'capture',capture)
 assert m.main(['--phase','mint','--authority',str(p),'--authority-sha256',m.digest(p.read_bytes())])==0
 out=capsys.readouterr().out;raw=(f.root/'mint-evidence-01/result.json').read_text()
 assert json.loads(raw)['status']=='MINT_RECEIPT_VALIDATED_NOT_ARMED' and len(raw)+len(out)<65536
 for secret in (TOKEN,PASSWORD,VAULT,'PRIVATE KEY'):assert secret not in raw+out

@pytest.mark.parametrize('reason',[None,[],{'SENSITIVE':'VALUE'},'SENSITIVE_REASON'*10000])
def test_diagnostic_unknown_values_cannot_expand_or_leak(reason):
 r=m.failure(reason,'NOT_INFERRED');assert r['reason']=='UNKNOWN' and len(m.canonical(r))<2048 and b'SENSITIVE' not in m.canonical(r)

@pytest.mark.parametrize('meta',[None,{},dict(authority_sha256='x',receipt_sha256='b'*64,expires_at=1),dict(authority_sha256='a'*64,receipt_sha256='b'*64,expires_at=True)])
def test_malformed_mint_metadata_does_not_enable_owner_access(tmp_path,meta):
 b,_=inputs(tmp_path);b['publication_mint']=meta
 with pytest.raises(op.Denied,match='MINT_RECEIPT_BINDING'):op.validate_binding(b,opening=True)

@pytest.mark.parametrize('why',['DEADLINE','OUTPUT_OVERFLOW',None])
def test_parent_lost_or_uncertain_child_is_refusal_without_raw_output(fx,monkeypatch,capsys,why):
 f=fx;p=f.root/'authority.json';p.write_bytes(m.canonical(f.a));p.chmod(0o600)
 monkeypatch.setattr(m.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(m.sys.stderr,'isatty',lambda:True)
 monkeypatch.setattr('builtins.input',lambda _:'EXECUTE_ONE_B_PUBLICATION_TOKEN_MINT')
 monkeypatch.setattr(m,'hidden',lambda prompt:PASSWORD if 'PEM' in prompt else VAULT)
 def capture(command,environment,**kw):
  assert set(environment)=={'HOME','PATH','LANG','PYTHONDONTWRITEBYTECODE','OPENBLAS_NUM_THREADS'}
  assert TOKEN not in repr(command) and PASSWORD not in repr(command) and VAULT not in repr(environment)
  assert kw['seconds']==60 and kw['ceiling']==4096 and len(kw['pass_fds'])==1
  return b'SENSITIVE_CHILD_SENTINEL',dict(exit_code=None,reason=why,client_closed=False,output_bytes=24)
 monkeypatch.setattr(client,'capture',capture)
 assert m.main(['--phase','mint','--authority',str(p),'--authority-sha256',m.digest(p.read_bytes())])==2
 out=capsys.readouterr().out;assert 'SENSITIVE' not in out and json.loads(out)['mint_outcome']=='NOT_INFERRED_RECONCILE'

@pytest.mark.parametrize('raw',[b'{"status":"SENSITIVE_SENTINEL"}',b'{"token":"ghs_PRIVATE"}',b'x'*2049])
def test_parent_cannot_export_unrecognised_child_values(raw):
 with pytest.raises(m.Refusal):m.public_result(raw)

def test_real_owner_capture_secret_pipe_with_mocked_child_provider(fx,tmp_path,monkeypatch,capsys):
 f=fx;p=f.root/'authority.json';p.write_bytes(m.canonical(f.a));p.chmod(0o600)
 # Child has the real helper/crypto/vault, but only a synthetic provider fixture.
 script=tmp_path/'synthetic_child.py'
 script.write_text('''import sys,os,json,pathlib\nsys.path.insert(0,''' +repr(str(Path.cwd()))+''')\nfrom verification.ingestion_storage import publication_mint as m\nassert not any(k in os.environ for k in ('GH_TOKEN','GITHUB_TOKEN','HTTPS_PROXY'))\nm.ROOT=pathlib.Path('''+repr(str(f.root))+''')\nclass Fake:\n def __init__(self,a,jwt):pass\n def call(self,method):\n  return (200,m.canonical('''+repr(f.install)+''')) if method=='GET' else (201,m.canonical('''+repr(f.value)+'''))\n def close(self):pass\noriginal=m.mint\nm.mint=lambda *a:original(*a,transport_factory=Fake)\nraise SystemExit(m.main())\n''')
 original=client.capture
 def capture(command,environment,**kw):
  assert command[:4]==[m.sys.executable,'-B','-m','verification.ingestion_storage.publication_mint']
  return original([m.sys.executable,'-B',str(script),*command[4:]],environment,**kw)
 monkeypatch.setattr(client,'capture',capture);monkeypatch.setenv('GH_TOKEN','SYNTHETIC_INHERITED_DO_NOT_PASS')
 monkeypatch.setattr(m.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(m.sys.stderr,'isatty',lambda:True)
 monkeypatch.setattr('builtins.input',lambda _:'EXECUTE_ONE_B_PUBLICATION_TOKEN_MINT')
 monkeypatch.setattr(m,'hidden',lambda prompt:PASSWORD if 'PEM' in prompt else VAULT)
 assert m.main(['--phase','mint','--authority',str(p),'--authority-sha256',m.digest(p.read_bytes())])==0
 out=capsys.readouterr().out;assert json.loads(out)['owner_process']['client_closed'] is True and state(f)['token_candidate']==TOKEN
 for secret in (TOKEN,PASSWORD,VAULT,'SYNTHETIC_INHERITED'):assert secret not in out
