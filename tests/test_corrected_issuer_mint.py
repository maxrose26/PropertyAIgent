"""Fixed issuer replacement; synthetic encrypted predecessor and mocked POST only."""
import copy,json,time
from datetime import datetime,timezone
from pathlib import Path
import pytest
from tests.test_publication_mint import fx,synthetic_key,PASSWORD,VAULT,TOKEN
from tests.test_intake_owner_operations import inputs
from verification.ingestion_storage import publication_mint as m,intake_owner_client as client
from verification.ingestion_storage.intake_owner_io import Vault

@pytest.fixture
def corrected(fx,monkeypatch):
 f=fx;original=copy.deepcopy(f.a);original['client_id']='Iv23IiHaM7meqJPpdD8x';f.a['client_id']='Iv23liHaM7meqJPpdD8x';f.h=m.digest(m.canonical(f.a));f.original=original
 def put(path,value):
  path.parent.mkdir(mode=0o700,parents=True,exist_ok=True);path.write_bytes(m.canonical(value));path.chmod(0o600);return path
 put(f.root/'authority.json',original)
 ca=put(f.root/'authority-corrected.json',f.a);monkeypatch.setattr(m,'CORRECTED_AUTHORITY',ca);monkeypatch.setattr(m,'CORRECTED_RAW_SHA',m.digest(ca.read_bytes()));monkeypatch.setattr(m,'CORRECTED_A_SHA',f.h)
 put(f.root/'mint-01-consumed.json',dict(attempt=m.ATTEMPT,authority_sha256=m.digest(m.canonical(original)),retry=False))
 old=Vault(f.root/'mint-01.vault',VAULT,create=True);old.save(dict(version='ONE_B_MINT_V1',authority=original,authority_sha256=m.digest(m.canonical(original)),state='REFUSED_POST_NOT_SENT',post_started=False))
 put(f.root/'mint-evidence-01/result.json',m.failure('SECRET','NOT_INFERRED_RECONCILE'))
 put(f.root/'mint-evidence-local-correction-01/result.json',dict(m.failure('HTTP','DEFINITELY_NOT_SENT'),owner_process=dict(client_closed=True,exit_code=2,output_bytes=120,reason=None)))
 proof=put(f.root/'proof/corrected-get.json',dict(authority_sha256=m.CORRECTED_RAW_SHA,http_status=200,binding_check='MATCH',requests_started=1,responses_completed=1,post_requests=0,provider_mutations=0,retry=False,transport_closed=True,body_complete=True,owner_process=dict(client_closed=True,exit_code=0,reason=None)))
 prior=put(f.root/'proof/old-get.json',{'http_status':404})
 monkeypatch.setattr(m,'CORRECTED_DIAGNOSTIC',proof)
 names=['authority.json','mint-01-consumed.json','mint-01.vault','mint-evidence-01/result.json','mint-evidence-local-correction-01/result.json']
 monkeypatch.setattr(m,'CORRECTED_PROOFS',{n:m.digest((f.root/n).read_bytes()) for n in names})
 monkeypatch.setattr(m,'CORRECTED_EXTERNAL_PROOFS',{p:m.digest(p.read_bytes()) for p in (proof,prior)})
 f.preserved={f.root/n:(f.root/n).read_bytes() for n in names};f.preserved.update({p:p.read_bytes() for p in (proof,prior,ca)})
 return f

class Transport:
 def __init__(self,f,*,get_status=200,error=None):self.f=f;self.get_status=get_status;self.error=error
 def call(self,method):
  f=self.f;f.calls.append(method)
  if method=='GET':return self.get_status,m.canonical(f.install)
  assert (f.root/m.CORRECTED_MARKER).exists()
  assert Vault(f.root/m.CORRECTED_JOURNAL,VAULT).load()['state']=='POST_INTENT_NO_RETRY'
  if self.error:raise self.error
  return 201,m.canonical(f.value)
 def close(self):self.f.closed.append(True)

def run(f,**kw):return m.mint(f.a,f.h,PASSWORD,VAULT,transport_factory=lambda a,j:Transport(f,**kw),clock=lambda:f.now,corrected_replacement=True)
def preserved(f):assert all(p.read_bytes()==b for p,b in f.preserved.items())


def test_corrected_success_exact_one_post_and_originals_unchanged(corrected):
 f=corrected;r=run(f)
 assert r['status']=='MINT_RECEIPT_VALIDATED_NOT_ARMED' and f.calls==['GET','POST'] and f.closed==[True]
 assert r['authority_sha256']==f.h and 'token' not in r
 s=Vault(f.root/m.CORRECTED_JOURNAL,VAULT).load();assert s['token_candidate']==TOKEN and s['state']=='RECEIPT_VALIDATED_NOT_ARMED'
 assert TOKEN.encode() not in (f.root/m.CORRECTED_JOURNAL).read_bytes();preserved(f)
 assert run(f)['mint_outcome']=='PRIOR_ATTEMPT_RECONCILE' and f.calls==['GET','POST']
 # Original entry cannot use the preserved old marker as a second authority.
 assert m.mint(f.a,f.h,PASSWORD,VAULT)['reason']=='EXISTING_ATTEMPT';preserved(f)

@pytest.mark.parametrize('path',['authority.json','mint-01-consumed.json','mint-01.vault','mint-evidence-local-correction-01/result.json'])
def test_historical_drift_refuses_before_new_intent(corrected,path):
 f=corrected;(f.root/path).write_bytes(b'DRIFT')
 r=run(f);assert r['reason']=='CORRECTED_REPLACEMENT' and not f.calls and not (f.root/m.CORRECTED_MARKER).exists()

@pytest.mark.parametrize('field,value',[('http_status',404),('binding_check','MISMATCH'),('post_requests',1),('responses_completed',0),('transport_closed',False)])
def test_successful_proof_semantics_required(corrected,field,value):
 f=corrected;p=m.CORRECTED_DIAGNOSTIC;v=m.parse(p.read_bytes());v[field]=value;p.write_bytes(m.canonical(v));m.CORRECTED_EXTERNAL_PROOFS[p]=m.digest(p.read_bytes())
 assert run(f)['reason']=='CORRECTED_REPLACEMENT' and not f.calls and not (f.root/m.CORRECTED_MARKER).exists()

@pytest.mark.parametrize('state,post,extra',[('POST_INTENT_NO_RETRY',False,{}),('REFUSED_POST_NOT_SENT',True,{}),('REFUSED_POST_NOT_SENT',False,{'token_candidate':TOKEN}),('RECEIPT_VALIDATED_NOT_ARMED',True,{})])
def test_encrypted_predecessor_cannot_hide_post_or_token(corrected,state,post,extra):
 f=corrected;v=Vault(f.root/'mint-01.vault',VAULT);s=v.load();s.update(state=state,post_started=post,**extra);v.save(s);m.CORRECTED_PROOFS['mint-01.vault']=m.digest((f.root/'mint-01.vault').read_bytes())
 assert run(f)['reason']=='CORRECTED_REPLACEMENT' and not f.calls and not (f.root/m.CORRECTED_MARKER).exists()

@pytest.mark.parametrize('name',['mint-corrected-client-id-01-consumed.json','mint-corrected-client-id-01.vault','mint-corrected-client-id-01.vault.next','seal-01-consumed.json','publication-01.vault'])
def test_new_intent_or_target_blocks_duplicates(corrected,name):
 f=corrected;(f.root/name).write_text('prior')
 assert run(f)['reason']=='EXISTING_ATTEMPT' and not f.calls


def test_uncertain_post_is_consumed_never_retried(corrected):
 f=corrected;r=run(f,error=TimeoutError('PRIVATE_SENTINEL'))
 assert r['mint_outcome']=='UNCERTAIN' and r['reason']=='TRANSPORT_TIMEOUT' and f.calls==['GET','POST']
 assert Vault(f.root/m.CORRECTED_JOURNAL,VAULT).load()['state']=='MINT_OUTCOME_UNCERTAIN'
 assert run(f)['mint_outcome']=='PRIOR_ATTEMPT_RECONCILE' and f.calls==['GET','POST'];preserved(f)
 assert 'PRIVATE' not in json.dumps(r)


def test_another_get_refusal_still_consumes_new_entry(corrected):
 f=corrected;assert run(f,get_status=401)['mint_outcome']=='DEFINITELY_NOT_SENT'
 assert run(f)['mint_outcome']=='PRIOR_ATTEMPT_RECONCILE' and f.calls==['GET'];preserved(f)

@pytest.mark.parametrize('when,reason',[('2026-11-02T12:00:00+00:00','EXECUTION_DAY'),('2026-11-04T00:00:00+00:00','EXECUTION_DAY'),('2026-11-03T23:08:55+00:00','MINT_DAY_MARGIN')])
def test_fixed_date_and_margin_no_silent_roll(corrected,when,reason):
 f=corrected
 with pytest.raises(m.Refusal,match=reason):m.corrected_replacement_preconditions(f.a,f.h,now=datetime.fromisoformat(when).timestamp())
 assert not f.calls


def test_future_seal_reads_only_corrected_receipt_journal(corrected,tmp_path):
 f=corrected;run(f);s=Vault(f.root/m.CORRECTED_JOURNAL,VAULT).load();b,_=inputs(tmp_path)
 b.update(valid_until=f.expiry,publication_valid_until=f.expiry,publication_vault_path=str(f.root/'publication-01.vault'),publication_scope=dict(repository=m.REPOSITORY,**m.PERMISSIONS),publication_mint=dict(authority_sha256=f.h,receipt_sha256=s['receipt_sha256'],expires_at=f.expiry))
 assert m.seal(f.a,f.h,b,VAULT,clock=lambda:f.expiry-1800)['status']=='PRIVATE_PUBLICATION_TOKEN_ARMED'
 assert f.calls==['GET','POST'];preserved(f)


def test_parent_child_flags_secrets_and_refusal_slot_guards(corrected,monkeypatch,capsys):
 f=corrected;monkeypatch.setattr(m.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(m.sys.stderr,'isatty',lambda:True)
 monkeypatch.setattr('builtins.input',lambda _:'EXECUTE_ONE_CORRECTED_ISSUER_B_PUBLICATION_TOKEN_MINT')
 values=iter([VAULT,PASSWORD]);monkeypatch.setattr(client,'hidden',lambda _:next(values));seen=[];actual=m.mint
 def capture(cmd,env,**kw):
  import os
  assert '--replace-issuer-refusal' in cmd and '--replace-local-refusal' not in cmd
  assert kw['seconds']==60 and kw['ceiling']==4096 and len(kw['pass_fds'])==1
  secret=json.loads(os.read(kw['pass_fds'][0],4096));assert secret==dict(vault_password=VAULT,key_password=PASSWORD)
  assert not (f.root/m.CORRECTED_MARKER).exists();seen.append(True)
  raw=m.canonical(actual(f.a,f.h,PASSWORD,VAULT,transport_factory=lambda a,j:Transport(f),clock=lambda:f.now,corrected_replacement=True))
  return raw,dict(exit_code=0,reason=None,client_closed=True,output_bytes=len(raw))
 monkeypatch.setattr(client,'capture',capture)
 args=['--phase','mint','--replace-issuer-refusal','--authority',str(m.CORRECTED_AUTHORITY),'--authority-sha256',m.CORRECTED_RAW_SHA]
 assert m.main(args)==0 and seen==[True]
 assert m.main(args)==2 and seen==[True] and f.calls==['GET','POST'];preserved(f)
 out=capsys.readouterr();assert not any(x in out.out+out.err for x in (PASSWORD,VAULT,TOKEN))


def test_corrected_flag_cannot_approve_seal_or_combine_authorities(corrected,capsys):
 f=corrected
 args=['--phase','mint','--replace-issuer-refusal','--replace-local-refusal','--authority',str(m.CORRECTED_AUTHORITY),'--authority-sha256',m.CORRECTED_RAW_SHA]
 assert m.main(args)==2 and not f.calls


def test_actual_child_dispatch_enforces_corrected_mode(corrected,monkeypatch,capsys):
 import os
 f=corrected;actual=m.mint
 def call(a,h,key,password,**kw):
  assert kw=={'corrected_replacement':True}
  return actual(a,h,key,password,transport_factory=lambda a,j:Transport(f),clock=lambda:f.now,**kw)
 monkeypatch.setattr(m,'mint',call)
 r,w=os.pipe();os.write(w,m.canonical(dict(vault_password=VAULT,key_password=PASSWORD)));os.close(w)
 args=['--child','--secrets-fd',str(r),'--phase','mint','--replace-issuer-refusal','--authority',str(m.CORRECTED_AUTHORITY),'--authority-sha256',m.CORRECTED_RAW_SHA]
 assert m.main(args)==0
 out=capsys.readouterr().out;assert json.loads(out)['status']=='MINT_RECEIPT_VALIDATED_NOT_ARMED'
 assert f.calls==['GET','POST'];preserved(f)


@pytest.mark.parametrize('point',['post_intent','candidate','validated'])
def test_new_journal_write_failure_never_changes_history_or_allows_retry(corrected,monkeypatch,point):
 f=corrected;original=Vault.save
 def save(self,value):
  state=value.get('state')
  if self.path.name==m.CORRECTED_JOURNAL and ((point=='post_intent' and state=='POST_INTENT_NO_RETRY') or (point=='candidate' and state=='MINTED_UNVALIDATED_REQUIRES_CLOSURE') or (point=='validated' and state=='RECEIPT_VALIDATED_NOT_ARMED')):raise OSError('SENSITIVE_STORAGE_SENTINEL')
  return original(self,value)
 monkeypatch.setattr(Vault,'save',save);r=run(f)
 assert r['mint_outcome']==('DEFINITELY_NOT_SENT' if point=='post_intent' else 'MINTED_REQUIRES_CLOSURE')
 calls=list(f.calls);assert run(f)['mint_outcome']=='PRIOR_ATTEMPT_RECONCILE' and f.calls==calls
 assert 'SENSITIVE' not in json.dumps(r);preserved(f)
