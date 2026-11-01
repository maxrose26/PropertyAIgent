"""Only changed attempt/launcher guards. Temporary paths and mocked source only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import socket
from datetime import date

import pytest
import requests
from verification.discovery import tameside_qualification as q
from verification.discovery.idox_window import run,WindowConfig
from verification.discovery.four_council_proof import manifest_scope
from tests.test_tameside_qualification_package import supervisor as successful_supervisor

REPO=Path(__file__).resolve().parents[1]
TOOLS=REPO/'docs/design/tameside-owner-attempt-02-20261101'
REAL_SECOND_OUTPUT=q.SECOND_OUTPUT
REAL_SECOND_CONSUMPTION=q.SECOND_CONSUMPTION


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*_a,**_kw):raise AssertionError('OFFLINE_TEST_NETWORK_FORBIDDEN')
    monkeypatch.setattr(socket,'getaddrinfo',forbidden)
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(requests.Session,'request',forbidden)


@pytest.fixture
def attempt(tmp_path,monkeypatch):
    for key in list(os.environ):
        if 'DATABASE' in key or key.endswith(('_KEY','_TOKEN','_PASSWORD')):monkeypatch.delenv(key)
    first=tmp_path/'first-consumed.json';first.write_text('{"state":"CONSUMED_BEFORE_SOURCE","original":true}')
    monkeypatch.setattr(q,'CONSUMPTION',first)
    monkeypatch.setattr(q,'PREDECESSOR_SHA256',hashlib.sha256(first.read_bytes()).hexdigest())
    monkeypatch.setattr(q,'SECOND_OUTPUT',tmp_path/'evidence-02')
    monkeypatch.setattr(q,'SECOND_CONSUMPTION',tmp_path/'consumed-02.json')
    def invoke(authority=q.SECOND_AUTHORITY,output=None):
        monkeypatch.setattr(sys,'argv',['qualification','--authority',authority,'--output',str(q.SECOND_OUTPUT if output is None else output)])
        return q.main()
    return invoke,first,first.read_bytes()


@pytest.mark.parametrize('authority',['wrong',q.AUTHORITY])
def test_wrong_or_original_consumed_authority_never_reaches_source(attempt,monkeypatch,authority):
    invoke,first,raw=attempt
    monkeypatch.setattr(q,'qualify',lambda *_a,**_kw:pytest.fail('source forbidden'))
    with pytest.raises(SystemExit):invoke(authority)
    assert first.read_bytes()==raw and not q.SECOND_CONSUMPTION.exists()


def test_output_change_is_not_authority_and_original_hash_cannot_drift(attempt,monkeypatch,tmp_path):
    invoke,first,raw=attempt
    monkeypatch.setattr(q,'qualify',lambda *_a,**_kw:pytest.fail('source forbidden'))
    with pytest.raises(SystemExit,match='EXACT_SECOND_ATTEMPT_OUTPUT_REQUIRED'):invoke(output=tmp_path/'replacement')
    first.write_bytes(raw+b' ')
    with pytest.raises(SystemExit,match='ORIGINAL_CONSUMPTION_BINDING_REQUIRED'):invoke()
    assert not q.SECOND_CONSUMPTION.exists()


def test_new_record_and_directory_fsynced_before_source_repeated_invocation_refuses(attempt,monkeypatch):
    invoke,first,raw=attempt;calls=[];synced=[]
    fsync=os.fsync
    def sync(fd):synced.append(fd);return fsync(fd)
    monkeypatch.setattr(os,'fsync',sync)
    def source(output,*,authority):
        record=json.loads(q.SECOND_CONSUMPTION.read_bytes())
        assert record==dict(authority=q.SECOND_AUTHORITY,row=q.ROW,state='CONSUMED_BEFORE_SOURCE',output=str(q.SECOND_OUTPUT))
        assert len(synced)==2 and q.SECOND_CONSUMPTION.stat().st_mode&0o777==0o600
        assert first.read_bytes()==raw and authority==q.SECOND_AUTHORITY
        calls.append(output)
        return dict(status='SYNTHETIC_ONLY',record_count=0,pages=0,source_sha256='1'*64)
    monkeypatch.setattr(q,'qualify',source)
    assert invoke()==0
    with pytest.raises(SystemExit,match='CONSUMED'):invoke()
    assert len(calls)==1 and first.read_bytes()==raw


@pytest.mark.parametrize('blocked',['record','dangling-symlink'])
def test_existing_or_uncertain_new_consumption_refuses(attempt,monkeypatch,blocked):
    invoke,first,raw=attempt
    if blocked=='record':q.SECOND_CONSUMPTION.write_text('UNCERTAIN')
    else:q.SECOND_CONSUMPTION.symlink_to('absent-target')
    monkeypatch.setattr(q,'qualify',lambda *_a,**_kw:pytest.fail('source forbidden'))
    with pytest.raises(SystemExit,match='CONSUMED'):invoke()
    assert first.read_bytes()==raw


def test_durability_failure_preserves_record_without_source_or_retry(attempt,monkeypatch):
    invoke,first,raw=attempt
    def fail(_):raise OSError('SYNTHETIC_FSYNC_FAILURE')
    monkeypatch.setattr(os,'fsync',fail)
    monkeypatch.setattr(q,'qualify',lambda *_a,**_kw:pytest.fail('source forbidden'))
    with pytest.raises(SystemExit,match='CONSUMED'):invoke()
    assert q.SECOND_CONSUMPTION.is_file() and first.read_bytes()==raw


def test_second_authority_propagates_into_existing_success_projection(attempt,monkeypatch):
    invoke,first,raw=attempt;original=q.qualify
    monkeypatch.setattr(q,'qualify',lambda root,*,authority:original(root,supervisor=successful_supervisor,authority=authority))
    assert invoke()==0
    assert (q.SECOND_OUTPUT/'CONSUMED').read_text()==q.SECOND_AUTHORITY+'\n'
    assessment=json.loads((q.SECOND_OUTPUT/'assessment.json').read_bytes())
    assert assessment['authority']==q.SECOND_AUTHORITY and assessment['row']==q.ROW
    assert assessment['record_count']==1 and assessment['database_connections']==0 and assessment['replay'] is False
    assert assessment['limits']==dict(requests=10,received_bytes=3000000,source_seconds=45,supervised_reservation_seconds=60,rows=60,pages=6,source_export_bytes=524288)
    assert first.read_bytes()==raw


@pytest.mark.parametrize('error,reason',[(requests.ConnectTimeout('SYNTHETIC_SECRET'),'CONNECT_TIMEOUT'),(requests.ConnectionError('SYNTHETIC_SECRET'),'UNKNOWN')])
def test_diagnostic_failure_survives_new_attempt_into_source_and_proof(attempt,monkeypatch,error,reason):
    invoke,first,raw=attempt;original=q.qualify;calls=[]
    def supervisor(command,**kw):
        assert kw['environment']=={'INGESTION_SOURCE_PRIVATE':'ONCE'} and kw['source'] is True and kw['seconds']==45
        assert json.loads(Path(command[command.index('--plan')+1]).read_bytes())==dict(row=q.ROW,fixture=None)
        def dispatch(*_,**__):calls.append(1);raise error
        config=WindowConfig('tameside','RECEIVED',date(2026,10,24),date(2026,10,30),0,60)
        with manifest_scope(q.ROW):source=run(dispatch,config,retain_proof=True)
        Path(command[command.index('--output')+1]).write_text(json.dumps(source))
        return dict(cleanup='CLOSED',accounting_complete=True,exit_code=0,limit_hit=None,elapsed_seconds=.1,live_owned_survivors=0,peak_owned_rss=1024,expired=False)
    monkeypatch.setattr(q,'qualify',lambda root,*,authority:original(root,supervisor=supervisor,authority=authority))
    assert invoke()==2 and len(calls)==1 and q.SECOND_CONSUMPTION.exists()
    source=json.loads((q.SECOND_OUTPUT/'source.json').read_bytes())
    detail=source['failure_diagnostic']['transport']['failure']
    assert detail['reason']==reason and source['retained_proof']['events'][0]['transport']['failure']==detail
    assert source['resource']['retries']==0 and source['resource']['requests_attempted']==1
    assert 'SYNTHETIC_SECRET' not in json.dumps(source) and not (q.SECOND_OUTPUT/'assessment.json').exists()
    assert first.read_bytes()==raw


@pytest.mark.parametrize('mode',['uncertain-cleanup','empty-source'])
def test_unsafe_cleanup_or_empty_result_still_refuses_and_keeps_consumption(attempt,monkeypatch,mode):
    invoke,first,raw=attempt;original=q.qualify
    def supervisor(*args,**kw):
        result=successful_supervisor(*args,**kw)
        if mode=='uncertain-cleanup':result['cleanup']='UNCERTAIN'
        else:
            command=args[0];f=Path(command[command.index('--output')+1]);s=json.loads(f.read_bytes());s['records']=[];s['pages']=[];f.write_text(json.dumps(s))
        return result
    monkeypatch.setattr(q,'qualify',lambda root,*,authority:original(root,supervisor=supervisor,authority=authority))
    assert invoke()==2 and q.SECOND_CONSUMPTION.exists() and not (q.SECOND_OUTPUT/'assessment.json').exists()
    assert first.read_bytes()==raw


@pytest.fixture
def package(tmp_path):
    repo=tmp_path/'repo';repo.mkdir();(repo/'source.py').write_text('SYNTHETIC_SOURCE_NEVER_EXECUTED=True\n')
    for args in (['init','-q'],['add','source.py'],['-c','user.name=Offline Fixture','-c','user.email=fixture@example.invalid','commit','-qm','synthetic only']):
        subprocess.run(['git','-C',str(repo),*args],check=True,stdout=subprocess.DEVNULL)
    out=tmp_path/'package';out.mkdir()
    for n in ('CHECK-PACKAGE.py','RUN-QUALIFICATION-INACTIVE.sh'):(out/n).write_bytes((TOOLS/n).read_bytes())
    interpreter=Path('/home/maxrose26/stage4-owner/storage-controller-venv/bin/python')
    if not interpreter.is_file():interpreter=Path(sys.executable)
    versions=json.loads(subprocess.check_output([str(interpreter),'-c','import importlib.metadata,json; print(json.dumps({n:importlib.metadata.version(n) for n in ["requests","urllib3"]}))'],text=True))
    original=tmp_path/'original.json';original.write_text('CONSUMED_ORIGINAL')
    h=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
    b=dict(checkout_path=str(repo),owner_commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),owner_tree=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD^{tree}'],text=True).strip(),runtime_files={'source.py':h(repo/'source.py')},preparation_files={},interpreter=str(interpreter),interpreter_sha256=h(interpreter),original_evidence={str(original):h(original)},dependency_versions=versions)
    binding=out/'BINDINGS.json';binding.write_text(json.dumps(b))
    wrapper=out/'RUN-QUALIFICATION-INACTIVE.sh'
    wrapper.write_text(wrapper.read_text().replace('/home/maxrose26/stage4-owner/tameside-owner-attempt-02-20261101',str(repo)).replace('/home/maxrose26/stage4-owner/storage-controller-venv/bin/python',str(interpreter)))
    def manifest():
        (out/'SHA256SUMS').write_text(''.join(f'{h(f)}  {f.name}\n' for f in sorted(out.iterdir()) if f.is_file() and f.name!='SHA256SUMS'))
    manifest()
    return out,repo,b,manifest,original


def test_bound_launcher_local_check_without_source(package):
    out,repo,b,manifest,original=package
    result=subprocess.run(['/bin/bash',str(out/'RUN-QUALIFICATION-INACTIVE.sh'),'--check'],capture_output=True,text=True)
    assert result.returncode==0 and 'LOCAL_PACKAGE_CHECKS_PASS' in result.stdout


@pytest.mark.parametrize('mismatch,code',[('commit','CHECKOUT_COMMIT'),('source-hash','CHECKOUT_FILE_HASH'),('package-hash','PACKAGE_HASH'),('original','ORIGINAL_EVIDENCE_CHANGED'),('interpreter','INTERPRETER_HASH')])
def test_wrong_bindings_refuse_in_wrapper_before_source_or_terminal_prompt(package,mismatch,code):
    out,repo,b,manifest,original=package
    if mismatch=='commit':b['owner_commit']='0'*40
    elif mismatch=='source-hash':b['runtime_files']['source.py']='0'*64
    elif mismatch=='interpreter':b['interpreter_sha256']='0'*64
    elif mismatch=='original':original.write_text('CHANGED')
    else:(out/'RUN-QUALIFICATION-INACTIVE.sh').write_text((out/'RUN-QUALIFICATION-INACTIVE.sh').read_text()+'\n# changed bytes\n')
    if mismatch!='package-hash':
        (out/'BINDINGS.json').write_text(json.dumps(b));manifest()
    result=subprocess.run(['/bin/bash',str(out/'RUN-QUALIFICATION-INACTIVE.sh')],stdin=subprocess.DEVNULL,capture_output=True,text=True)
    assert result.returncode!=0 and code in result.stderr
    assert 'Approval phrase' not in result.stdout and 'REFUSED: exact reviewed' not in result.stdout


def test_launcher_exact_authority_paths_and_existing_envelope_are_fixed():
    text=(TOOLS/'RUN-QUALIFICATION-INACTIVE.sh').read_text()
    assert str(REAL_SECOND_OUTPUT) in text and str(REAL_SECOND_CONSUMPTION) in text
    assert q.SECOND_AUTHORITY in text and 'EXECUTE_ONE_TAMESIDE_LISTING_QUALIFICATION_ATTEMPT_02' in text
    assert '/usr/bin/env -i' in text and '--signal=INT --kill-after=2s 58s' in text
    assert 'verification.discovery.tameside_qualification' in text and '--check' in text
