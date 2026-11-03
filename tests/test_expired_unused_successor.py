"""Synthetic expired predecessor and mocked successor only. No real credentials."""
import copy,json,hashlib,os
from pathlib import Path
from datetime import datetime,timezone
import pytest
from tests.test_publication_mint import fx,synthetic_key,PASSWORD,VAULT,TOKEN
from tests.test_corrected_issuer_mint import corrected,Transport as PriorTransport,run as prior_run
from verification.ingestion_storage import publication_mint as m,finite_release_binding as assembler,intake_owner_client as client
from verification.ingestion_storage.intake_owner_io import Vault

@pytest.fixture
def successor(corrected,monkeypatch):
 f=corrected;old_result=prior_run(f);assert old_result['status']=='MINT_RECEIPT_VALIDATED_NOT_ARMED'
 old_expiry=f.expiry;old_receipt=old_result['receipt_sha256'];out=f.root/m.CORRECTED_OUTPUT;out.mkdir(mode=0o700)
 def put(path,value):
  path.parent.mkdir(mode=0o700,parents=True,exist_ok=True);path.write_bytes(m.canonical(value));path.chmod(0o600);return path
 put(out/'result.json',dict(old_result,owner_process=dict(client_closed=True,exit_code=0,reason=None,output_bytes=312)))
 f.now=old_expiry+1;f.expiry=f.now+3600;f.value['expires_at']=datetime.fromtimestamp(f.expiry,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ');f.calls.clear();f.closed.clear()
 monkeypatch.setattr(m,'PREDECESSOR_EXPIRY',old_expiry);monkeypatch.setattr(m,'PREDECESSOR_RECEIPT',old_receipt)
 names=[m.CORRECTED_JOURNAL,m.CORRECTED_MARKER,m.CORRECTED_OUTPUT+'/result.json'];monkeypatch.setattr(m,'SUCCESSOR_PREDECESSOR_PROOFS',{n:m.digest((f.root/n).read_bytes()) for n in names})
 closure=put(f.root/'proof/closure.json',dict(status='EXPIRED_UNUSED',recorded_expiry_epoch=old_expiry,observed_epoch=f.now,token_specific_revocation='NOT_PERFORMED',installation_removal='NOT_PERFORMED',later_phases_evidenced=False))
 monkeypatch.setattr(m,'SUCCESSOR_CLOSURE',closure);monkeypatch.setattr(m,'SUCCESSOR_CLOSURE_SHA',m.digest(closure.read_bytes()))
 unused=f.root/'unused-release';unused.mkdir(mode=0o700);monkeypatch.setattr(m,'SUCCESSOR_UNUSED_RELEASE',unused)
 monkeypatch.setattr(m.time,'time',lambda:f.now)
 f.preserved.update({f.root/n:(f.root/n).read_bytes() for n in names});f.preserved[closure]=closure.read_bytes();return f

class Transport(PriorTransport):
 def call(self,method):
  f=self.f;f.calls.append(method)
  if method=='GET':return 200,m.canonical(f.install)
  assert (f.root/m.SUCCESSOR_MARKER).exists()
  assert Vault(f.root/m.SUCCESSOR_JOURNAL,VAULT).load()['state']=='POST_INTENT_NO_RETRY'
  if self.error:raise self.error
  return 201,m.canonical(f.value)

def run(f,**kw):return m.mint(f.a,f.h,PASSWORD,VAULT,clock=lambda:f.now,transport_factory=lambda a,j:Transport(f,**kw),successor=True)
def preserved(f):assert all(p.read_bytes()==b for p,b in f.preserved.items())


def test_one_successor_and_no_overlap_or_duplicate(successor):
 f=successor;r=run(f);assert r['status']=='MINT_RECEIPT_VALIDATED_NOT_ARMED' and f.calls==['GET','POST'];preserved(f)
 assert run(f)['mint_outcome']=='PRIOR_ATTEMPT_RECONCILE' and f.calls==['GET','POST']
 assert m.mint(f.a,f.h,PASSWORD,VAULT)['reason']=='EXISTING_ATTEMPT'
 assert m.mint(f.a,f.h,PASSWORD,VAULT,corrected_replacement=True)['reason']=='EXISTING_ATTEMPT'
 assert TOKEN.encode() not in (f.root/m.SUCCESSOR_JOURNAL).read_bytes()

@pytest.mark.parametrize('delta',[-1,0])
def test_no_successor_before_actual_expiry(successor,delta):
 f=successor
 with pytest.raises(m.Refusal,match='PREDECESSOR_NOT_EXPIRED'):m.successor_preconditions(f.a,f.h,VAULT,now=m.PREDECESSOR_EXPIRY+delta)
 assert not f.calls and not (f.root/m.SUCCESSOR_MARKER).exists()

@pytest.mark.parametrize('field,value',[('status','REVOKED'),('later_phases_evidenced',True),('recorded_expiry_epoch',0),('observed_epoch',0)])
def test_closure_must_be_exact_expired_unused(successor,field,value):
 f=successor;p=m.SUCCESSOR_CLOSURE;v=m.parse(p.read_bytes());v[field]=value;p.write_bytes(m.canonical(v));m.SUCCESSOR_CLOSURE_SHA=m.digest(p.read_bytes())
 assert run(f)['reason']=='SUCCESSOR_PRECONDITION' and not f.calls

@pytest.mark.parametrize('name',['seal-01-consumed.json','publication-01.vault','publication-01.vault.revoke-consumed','b-20261103-tm-2e4ec5466a21-access.vault'])
def test_old_later_phase_refuses_successor(successor,name):
 f=successor;(f.root/name).write_text('later phase');assert run(f)['reason']=='EXISTING_ATTEMPT' and not f.calls

@pytest.mark.parametrize('name',['activate-evidence','handoff-evidence','submission.intent.json'])
def test_later_release_evidence_refuses(successor,name):
 f=successor;(m.SUCCESSOR_UNUSED_RELEASE/name).write_text('later');assert run(f)['reason']=='SUCCESSOR_PRECONDITION' and not f.calls


def test_predecessor_encrypted_token_is_never_rewritten(successor,monkeypatch):
 f=successor;save=Vault.save
 def checked(self,v):
  assert self.path.name not in ('mint-01.vault',m.CORRECTED_JOURNAL)
  return save(self,v)
 monkeypatch.setattr(Vault,'save',checked);assert run(f)['status']=='MINT_RECEIPT_VALIDATED_NOT_ARMED';preserved(f)


def test_uncertain_successor_post_cannot_repeat(successor):
 f=successor;r=run(f,error=TimeoutError('SECRET_SENTINEL'));assert r['mint_outcome']=='UNCERTAIN' and f.calls==['GET','POST']
 assert run(f)['mint_outcome']=='PRIOR_ATTEMPT_RECONCILE' and f.calls==['GET','POST'];preserved(f)


def test_successor_seal_uses_new_receipt_only(successor,tmp_path):
 from tests.test_intake_owner_operations import inputs
 f=successor;run(f);s=Vault(f.root/m.SUCCESSOR_JOURNAL,VAULT).load();b,_=inputs(tmp_path)
 b.update(valid_until=f.expiry,publication_valid_until=f.expiry,publication_vault_path=str(f.root/'publication-01.vault'),publication_scope=dict(repository=m.REPOSITORY,**m.PERMISSIONS),publication_mint=dict(authority_sha256=f.h,receipt_sha256=s['receipt_sha256'],expires_at=f.expiry))
 assert m.seal(f.a,f.h,b,VAULT,clock=lambda:f.expiry-1800,successor=True)['status']=='PRIVATE_PUBLICATION_TOKEN_ARMED';preserved(f)


def test_real_child_flag_dispatch(successor,monkeypatch,capsys):
 f=successor;actual=m.mint
 def invoke(a,h,k,p,**kw):
  assert kw=={'successor':True};return actual(a,h,k,p,clock=lambda:f.now,transport_factory=lambda a,j:Transport(f),**kw)
 monkeypatch.setattr(m,'mint',invoke);r,w=os.pipe();os.write(w,m.canonical(dict(vault_password=VAULT,key_password=PASSWORD)));os.close(w)
 a=['--phase','mint','--successor-expired-unused','--authority',str(m.CORRECTED_AUTHORITY),'--authority-sha256',m.CORRECTED_RAW_SHA,'--child','--secrets-fd',str(r)]
 assert m.main(a)==0 and f.calls==['GET','POST'];out=capsys.readouterr().out;assert PASSWORD not in out and VAULT not in out and TOKEN not in out;preserved(f)


def test_static_blueprint_build_and_freeze_without_private_access(successor,tmp_path,monkeypatch,capsys):
 f=successor;r=run(f);r['owner_process']=dict(client_closed=True,exit_code=0,reason=None);s=assembler.static();monkeypatch.setattr(assembler,'AUTHORITY',f.h)
 b,policy=assembler.build(s,r,f.expiry-1800,now=f.expiry-1800)
 assert b['valid_until']==r['expiry'] and b['publication_mint']['receipt_sha256']==r['receipt_sha256'] and policy['max_runs']==1
 work=tmp_path/'local-binding';work.mkdir(mode=0o700)
 for n in ['STATIC-RELEASE.json','B-COMMAND.txt']:(work/n).write_bytes((assembler.ROOT/n).read_bytes())
 public=tmp_path/'public.json';public.write_bytes(m.canonical(r));monkeypatch.setattr(assembler,'MINT_RESULT',public);monkeypatch.setattr(assembler,'ROOT',work)
 monkeypatch.setattr(assembler.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(assembler.sys.stderr,'isatty',lambda:True)
 assert assembler.main(['preview'])==0
 monkeypatch.setattr(assembler.time,'time',lambda:f.expiry-1800)
 def confirm(_):
  assert not (work/'owner-binding.json').exists();return assembler.FRESH_PHRASE
 monkeypatch.setattr('builtins.input',confirm)
 assert assembler.main(['freeze'])==0
 frozen=json.loads((work/'FROZEN.json').read_bytes());assert frozen['isolation_observed_at']==f.expiry-1800 and frozen['handoff_latest']==f.expiry-1500
 assert frozen['binding_sha256']==hashlib.sha256((work/'owner-binding.json').read_bytes()).hexdigest()
 assert assembler.main(['freeze'])==2;preserved(f)

@pytest.mark.parametrize('seconds',[1445,2101])
def test_assembler_rejects_too_early_late_before_observation(successor,tmp_path,monkeypatch,seconds):
 f=successor;r=run(f);r['owner_process']=dict(client_closed=True,exit_code=0,reason=None);monkeypatch.setattr(assembler,'AUTHORITY',f.h);s=assembler.static()
 with pytest.raises(Exception):assembler.build(s,r,f.expiry-seconds,now=f.expiry-seconds)


def test_successor_marker_binds_exact_predecessor(successor):
 f=successor;assert run(f)['status']=='MINT_RECEIPT_VALIDATED_NOT_ARMED'
 record=json.loads((f.root/m.SUCCESSOR_MARKER).read_bytes());assert record['attempt']=='ONE_B_EXPIRED_UNUSED_SUCCESSOR_V1'
 assert record['predecessor_receipt_sha256']==m.PREDECESSOR_RECEIPT and record['predecessor_closure_sha256']==m.SUCCESSOR_CLOSURE_SHA
 assert TOKEN not in json.dumps(record) and VAULT not in json.dumps(record);preserved(f)

@pytest.mark.parametrize('field,value',[('mint_outcome','UNCERTAIN'),('receipt_sha256','BAD'),('authority_sha256','0'*64)])
def test_static_assembler_never_accepts_uncertain_receipt(successor,monkeypatch,field,value):
 f=successor;r=run(f);r['owner_process']=dict(client_closed=True,exit_code=0,reason=None);monkeypatch.setattr(assembler,'AUTHORITY',f.h);r[field]=value
 with pytest.raises(Exception):assembler.build(assembler.static(),r,f.expiry-1800,now=f.expiry-1800)

@pytest.mark.parametrize('field,value',[('version','OTHER'),('post_started',False)])
def test_predecessor_decrypted_schema_is_strict(successor,field,value):
 f=successor;v=Vault(f.root/m.CORRECTED_JOURNAL,VAULT);s=v.load();s[field]=value;v.save(s)
 m.SUCCESSOR_PREDECESSOR_PROOFS[m.CORRECTED_JOURNAL]=m.digest((f.root/m.CORRECTED_JOURNAL).read_bytes())
 assert run(f)['reason']=='SUCCESSOR_PRECONDITION' and not f.calls


def test_binding_assembler_has_no_live_effect_surface():
 import ast
 tree=ast.parse(Path(assembler.__file__).read_text());attrs={n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
 assert not attrs&{'connect','engine','request','post','put','delete','mint','seal','activate','handoff','token_revoke','sign','Vault'}

@pytest.mark.parametrize('stamp,reason',[(datetime(2026,11,4,tzinfo=timezone.utc).timestamp(),'EXECUTION_DAY'),(datetime(2026,11,3,23,9,tzinfo=timezone.utc).timestamp(),'MINT_DAY_MARGIN')])
def test_successor_cannot_roll_date_or_rush_midnight(successor,stamp,reason):
 f=successor
 with pytest.raises(m.Refusal,match=reason):m.successor_preconditions(f.a,f.h,VAULT,now=stamp)
 assert not f.calls and not (f.root/m.SUCCESSOR_MARKER).exists();preserved(f)


def test_successor_parent_secret_pipe_and_exclusive_result(successor,monkeypatch,capsys):
 f=successor;monkeypatch.setattr(m.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(m.sys.stderr,'isatty',lambda:True)
 monkeypatch.setattr('builtins.input',lambda _:'EXECUTE_ONE_SUCCESSOR_AFTER_EXPIRED_UNUSED_MINT')
 values=iter([VAULT,PASSWORD]);monkeypatch.setattr(client,'hidden',lambda _:next(values));seen=[]
 def capture(cmd,env,**kw):
  assert '--successor-expired-unused' in cmd and '--replace-issuer-refusal' not in cmd
  assert kw['seconds']==60 and kw['ceiling']==4096 and len(kw['pass_fds'])==1
  secret=json.loads(os.read(kw['pass_fds'][0],4096));assert secret==dict(vault_password=VAULT,key_password=PASSWORD)
  assert not (f.root/m.SUCCESSOR_MARKER).exists();seen.append(True)
  raw=m.canonical(run(f));return raw,dict(exit_code=0,reason=None,client_closed=True,output_bytes=len(raw))
 monkeypatch.setattr(client,'capture',capture)
 args=['--phase','mint','--successor-expired-unused','--authority',str(m.CORRECTED_AUTHORITY),'--authority-sha256',m.CORRECTED_RAW_SHA]
 assert m.main(args)==0 and seen==[True]
 assert m.main(args)==2 and seen==[True] and f.calls==['GET','POST'];preserved(f)
 out=capsys.readouterr();assert not any(x in out.out+out.err for x in (PASSWORD,VAULT,TOKEN))
