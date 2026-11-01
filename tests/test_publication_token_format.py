"""Synthetic tokens only; no real credentials, mint, authenticated API or Render."""
import copy,hashlib,json,os,subprocess,sys
from types import SimpleNamespace
from pathlib import Path
import pytest
from verification.ingestion_storage import intake_owner_operations as extra,intake_owner_client as client,intake_owner_io as io
from verification.ingestion_storage.intake_owner import Denied
from tests.test_intake_owner_operations import inputs,KEY
from tests.test_intake_owner_io import API,prepared

def token(n=520):
    # Deliberately opaque; not a valid JWT, signature or GitHub credential.
    return ('ghs_SYNTHETIC_opaque.-'+('xyz._-"\\$'*(n+1)))[:n]

@pytest.mark.parametrize('n',[24,40,255,256,520,777,2048])
def test_variable_documented_and_legacy_formats(n):
    assert extra.installation_token_allowed(token(n))
@pytest.mark.parametrize('value',[None,42,'ghs_'+'x'*19,'ghs_'+'x'*2045,'github_pat_'+'x'*100,'ghp_'+'x'*80,'ey.synthetic.admin.jwt','ghs_'+('a'*30)+'\n','ghs_'+('a'*30)+' ','ghs_'+('a'*30)+'\t','ghs_'+('a'*30)+'\x00','ghs_'+('a'*30)+'\x7f','ghs_'+('a'*30)+'é'],ids=['none','integer','short','oversize','fine-pat','classic-pat','app-jwt','newline','space','tab','nul','del','unicode'])
def test_malformed_oversize_and_wrong_type_refuse(value):
    assert not extra.installation_token_allowed(value)

@pytest.mark.parametrize('n',[40,520,2048])
def test_vault_handoff_and_duplicate_revoke_preserve_full_token(monkeypatch,tmp_path,n):
    b,_=inputs(tmp_path);t=token(n);secret=dict(vault_key=KEY,publication_token=t)
    result=client.worker('publication-arm',b,secret,b['publication_vault_path'],{})
    assert t not in json.dumps(result) and t.encode() not in Path(b['publication_vault_path']).read_bytes()
    stored=io.Vault(b['publication_vault_path'],KEY).load();assert extra.token_load(b,stored)==t
    assert stored['token_sha256']==hashlib.sha256(t.encode()).hexdigest()
    api=API();state=prepared(api);b.update(render_config_sha256=io.service_guard(api.service),inherited_boundary=state['binding']['inherited_boundary'])
    # Full immutable binding is established before arm in the actual flow.
    # Direct I/O unit uses that independently prepared state, not edits to a vault.
    state['binding']=b;api.env['INGESTION_RENDER_PROFILE']=json.dumps(b['render_profile'])
    out=io.handoff(api,state,lambda _:None,t)
    assert api.env['GH_TOKEN']==t and t not in json.dumps(out)
    calls=[]
    def runner(command,**kw):
        calls.append(command);assert t not in repr(command)
        return subprocess.CompletedProcess(command,0,b'HTTP/2.0 204 No Content\n',b'')
    saved=[];original=copy.deepcopy(stored)
    extra.token_revoke(stored['binding'],stored,lambda x:saved.append(copy.deepcopy(x)),runner=runner)
    assert saved[-1]['token']=='' and len(calls)==1
    with pytest.raises(Denied):extra.token_revoke(stored['binding'],saved[-1],lambda _:None,runner=runner)
    with pytest.raises(FileExistsError):extra.token_revoke(original['binding'],original,lambda _:None,runner=runner)
    assert len(calls)==1

def test_worker_uses_exact_new_format_token_from_armed_vault(monkeypatch,tmp_path):
    b,_=inputs(tmp_path);api=API();state=prepared(api);b.update(render_config_sha256=io.service_guard(api.service),inherited_boundary=state['binding']['inherited_boundary'])
    api.env['INGESTION_RENDER_PROFILE']=json.dumps(b['render_profile']);state['binding']=b
    t=token();client.worker('publication-arm',b,dict(vault_key=KEY,publication_token=t),b['publication_vault_path'],{})
    access=tmp_path/'access.vault';io.Vault(access,KEY,create=True).save(state)
    closed=[];api.session=SimpleNamespace(close=lambda:closed.append(True))
    monkeypatch.setattr(io,'Render',lambda _:api)
    r=client.worker('handoff',b,dict(vault_key=KEY,render_token='SYNTHETIC_ONLY'),str(access),{})
    assert api.env['GH_TOKEN']==t and t not in json.dumps(r) and closed==[True]
    assert t.encode() not in access.read_bytes()

def parent_args(tmp_path,b):
    file=tmp_path/'binding.json';file.write_text(json.dumps(b));h=hashlib.sha256(file.read_bytes()).hexdigest()
    return ['--phase','publication-arm','--binding',str(file),'--binding-sha256',h,'--vault',b['publication_vault_path']]

def fake_terminal(monkeypatch,output,hidden_values):
    monkeypatch.setattr(sys.stdin,'isatty',lambda:True);monkeypatch.setattr(sys.stderr,'isatty',lambda:True)
    answers=iter(['EXECUTE_EXACT_PUBLICATION_ARM_ONCE',str(output)])
    monkeypatch.setattr('builtins.input',lambda _:next(answers));secrets=iter(hidden_values);monkeypatch.setattr(client,'hidden',lambda _:next(secrets))

@pytest.mark.parametrize('n',[520,2048])
def test_actual_parent_child_secret_pipe_new_format_no_plaintext(monkeypatch,tmp_path,capsys,n):
    b,_=inputs(tmp_path);args=parent_args(tmp_path,b);t=token(n);out=tmp_path/'evidence'
    fake_terminal(monkeypatch,out,[KEY,KEY,t]);prior=os.umask(0o077)
    try:r=client.main(args)
    finally:os.umask(prior)
    assert r==0 and t not in capsys.readouterr().out
    assert t.encode() not in (out/'output.txt').read_bytes()
    assert io.Vault(b['publication_vault_path'],KEY).load()['token']==t
    assert (out/'status.json').stat().st_size+(out/'output.txt').stat().st_size<65536

@pytest.mark.parametrize('case',['over_policy_limit','encoded_frame_limit'])
def test_parent_refuses_before_child_without_secret_echo(monkeypatch,tmp_path,capsys,case):
    b,_=inputs(tmp_path);args=parent_args(tmp_path,b);t=token(2049) if case=='over_policy_limit' else 'ghs_'+('\\'*2044)
    fake_terminal(monkeypatch,tmp_path/'evidence',[KEY,KEY,t])
    monkeypatch.setattr(client,'capture',lambda *a,**kw:pytest.fail('must refuse before child'))
    prior=os.umask(0o077)
    try:r=client.main(args)
    finally:os.umask(prior)
    printed=capsys.readouterr().out
    assert r==2 and t not in printed
    assert ('INSTALLATION_TOKEN_ONLY' if case=='over_policy_limit' else 'SECRET_PIPE_BOUND') in printed
    assert not Path(b['publication_vault_path']).exists()

def test_handoff_malformed_token_refuses_before_any_api(monkeypatch):
    api=API();state=prepared(api)
    with pytest.raises(Denied):io.handoff(api,state,lambda _:None,'ghs_'+('a'*40)+'\n')
    assert api.calls==0 and api.puts==0

def test_legacy_revoke_load_uses_same_bounded_opaque_policy(monkeypatch,tmp_path):
    b,_=inputs(tmp_path);b.pop('publication_vault_path');t=token();v=tmp_path/'legacy.vault'
    state=dict(binding=b,state='DATABASE_CLOSURE_ACKNOWLEDGED',render=dict(state='RESTORATION_ACKNOWLEDGED',publication_state='ACTIVE',publication_token=t))
    io.Vault(v,KEY,create=True).save(state);calls=[]
    def run(command,**kw):
        calls.append(command);assert kw['env']['GH_TOKEN']==t and t not in repr(command)
        return subprocess.CompletedProcess(command,0,b'HTTP/2.0 204 No Content\n',b'')
    monkeypatch.setattr(subprocess,'run',run)
    r=client.worker('publication-close',b,dict(vault_key=KEY),str(v),{})
    assert len(calls)==1 and r['status']=='PUBLICATION_TOKEN_REVOCATION_ACKNOWLEDGED'


def test_legacy_alphanumeric_format_still_accepted():
    assert extra.installation_token_allowed('ghs_'+('A'*36))
