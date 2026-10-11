"""Registration/supervision only. All transport is mocked; no council truth."""
import copy
import json
from pathlib import Path
import time
import pytest
import yaml
from verification.stage26b_l1 import bolton_runner as r
from verification.stage26b_l1 import bolton_literal as b
from verification.stage26b_l1.bolton_rehearsal import dispatch

SHA = 'a'*40

@pytest.fixture
def pinned(monkeypatch):
    monkeypatch.setattr(r.subprocess,'check_output',lambda args,**kw: SHA+'\n' if args[1]=='rev-parse' else '')
    for name in ('GITHUB_ACTIONS','RUNNER_ENVIRONMENT','GITHUB_EVENT_NAME','BOLTON_WORKFLOW_SHA'):
        monkeypatch.delenv(name,raising=False)

def live_context(monkeypatch):
    for name,value in dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',
            GITHUB_EVENT_NAME='workflow_dispatch',BOLTON_WORKFLOW_SHA=SHA).items():
        monkeypatch.setenv(name,value)

def test_manual_workflow_contract():
    path=Path('.github/workflows/bolton-literal-canary.yml')
    text=path.read_text(); doc=yaml.load(text,Loader=yaml.BaseLoader)
    assert set(doc['on'])=={'workflow_dispatch'}
    assert set(doc['on']['workflow_dispatch']['inputs'])=={'reviewed_sha','mode','authority'}
    assert doc['permissions']=={'contents':'read'}
    job=doc['jobs']['canary']
    assert job['runs-on']=='ubuntu-24.04' and job['timeout-minutes']=='2'
    assert 'environment' not in job
    checkout=next(s for s in job['steps'] if s.get('uses','').startswith('actions/checkout'))
    assert checkout['with']['persist-credentials']=='false'
    assert checkout['with']['ref']=='${{ inputs.reviewed_sha }}'
    assert 'github.workflow_sha' in text and 'env -i' in text
    for forbidden in ('secrets.','DATABASE_URL','OPENAI','SUPABASE','RENDER','schedule:',
            'pull_request:','push:','self-hosted'):
        assert forbidden not in text
    assert 'AUTHORISE_BOLTON_TWO_SUMMARIES_ONLY' in text

def test_registration_ci_never_live():
    text=Path('.github/workflows/bolton-literal-offline.yml').read_text()
    assert '--mode offline --authority OFFLINE_ONLY' in text
    assert '--mode live' not in text and 'test_bolton_registration.py' in text

@pytest.mark.parametrize('bad', ['authority','host','event','workflow'])
def test_live_admission_rejects_wrong_context(pinned,monkeypatch,bad):
    live_context(monkeypatch);authority=r.AUTHORITY
    if bad=='authority':authority='AUTHORISE_FAILSWORTH_SOUTHLINK_ONLY'
    if bad=='host':monkeypatch.setenv('RUNNER_ENVIRONMENT','self-hosted')
    if bad=='event':monkeypatch.setenv('GITHUB_EVENT_NAME','push')
    if bad=='workflow':monkeypatch.setenv('BOLTON_WORKFLOW_SHA','b'*40)
    with pytest.raises(ValueError):r.admit(SHA,'live',authority)

def test_live_requires_exact_clean_sha(pinned,monkeypatch):
    live_context(monkeypatch)
    r.admit(SHA,'live',r.AUTHORITY)
    with pytest.raises(ValueError):r.admit('b'*40,'live',r.AUTHORITY)
    monkeypatch.setattr(r.subprocess,'check_output',lambda args,**kw: SHA if args[1]=='rev-parse' else ' M file')
    with pytest.raises(ValueError):r.admit(SHA,'live',r.AUTHORITY)

def test_offline_refuses_live_acknowledgement(pinned):
    with pytest.raises(ValueError):r.admit(SHA,'offline',r.AUTHORITY)

def mock_supervisor(monkeypatch,artifact,status=0,expired=False,check=None):
    def supervise(command,*,env,deadline):
        if check:check(command,env,deadline)
        if artifact is not None:
            Path(command[command.index('--output')+1]).write_text(json.dumps(artifact))
        return status,expired
    monkeypatch.setattr(r,'supervise',supervise)

def test_bounded_launcher_cleanup_and_no_secret_inheritance(pinned,monkeypatch,tmp_path):
    artifact=b.run(sha=SHA,dispatch=dispatch);temporary=[]
    monkeypatch.setenv('DATABASE_URL','PROHIBITED_TEST_VALUE')
    monkeypatch.setenv('OPENAI_API_KEY','PROHIBITED_TEST_VALUE')
    def check(command,env,deadline):
        assert deadline==45 and '--worker' in command
        assert not set(env)&{'DATABASE_URL','OPENAI_API_KEY','GITHUB_TOKEN','HTTPS_PROXY'}
        temporary.append(Path(env['HOME']))
    mock_supervisor(monkeypatch,artifact,check=check)
    output=tmp_path/'audit.json'
    assert r.execute(SHA,'offline','OFFLINE_ONLY',output)==0
    assert output.stat().st_size<=16_384
    assert not temporary[0].exists()
    actual=json.loads(output.read_bytes());b.validate(actual)
    assert actual['results'][0]['semantic_state']=='UNKNOWN_UNMAPPED'

@pytest.mark.parametrize('failure',['timeout','missing','oversize','malformed','wrong_qualification','wrong_exit'])
def test_supervisor_failure_never_exports_complete(pinned,monkeypatch,tmp_path,failure):
    artifact=copy.deepcopy(b.run(sha=SHA,dispatch=dispatch))
    status,expired=0,False
    if failure=='timeout':expired=True;status=124
    if failure=='missing':artifact=None
    if failure=='oversize':artifact['extra']='x'*16_384
    if failure=='malformed':artifact['results']=[]
    if failure=='wrong_qualification':artifact['results'][0]['source_qualification']='exact_public_council_summary'
    if failure=='wrong_exit':status=1
    mock_supervisor(monkeypatch,artifact,status,expired)
    output=tmp_path/'audit.json'
    with pytest.raises(ValueError):r.execute(SHA,'offline','OFFLINE_ONLY',output)
    assert not output.exists()

def test_valid_failure_audit_is_retained_without_success(pinned,monkeypatch,tmp_path):
    from verification.stage26b_l1.bolton_rehearsal import FixtureResponse
    def failed(*a,**k):
        response=FixtureResponse(b'error');response.status_code=403;return response
    artifact=b.run(sha=SHA,dispatch=failed)
    mock_supervisor(monkeypatch,artifact,1)
    output=tmp_path/'audit.json'
    assert r.execute(SHA,'offline','OFFLINE_ONLY',output)==1
    assert json.loads(output.read_bytes())['execution_status']=='FAIL'

def test_setup_budget_abort_before_worker(pinned,monkeypatch,tmp_path):
    live_context(monkeypatch)
    monkeypatch.setattr(r,'supervise',lambda *a,**k:pytest.fail('worker must not start'))
    with pytest.raises(ValueError):r.execute(SHA,'live',r.AUTHORITY,tmp_path/'audit.json',time.time()-106)
    with pytest.raises(ValueError):r.execute(SHA,'live',r.AUTHORITY,tmp_path/'audit.json')

def test_remaining_job_budget_never_extends_worker(pinned,monkeypatch,tmp_path):
    artifact=b.run(sha=SHA,dispatch=dispatch)
    def check(command,env,deadline):assert 0<deadline<25
    mock_supervisor(monkeypatch,artifact,check=check)
    r.execute(SHA,'offline','OFFLINE_ONLY',tmp_path/'audit.json',time.time()-90)

def test_existing_output_not_overwritten(pinned,tmp_path):
    output=tmp_path/'audit.json';output.write_text('preserve')
    with pytest.raises(ValueError):r.execute(SHA,'offline','OFFLINE_ONLY',output)
    assert output.read_text()=='preserve'

def test_offline_worker_cannot_use_real_http(monkeypatch,tmp_path):
    monkeypatch.setattr(b,'http_dispatch',lambda *a,**k:pytest.fail('no real transport'))
    assert r.worker(SHA,'offline',tmp_path/'audit.json')==0
    result=json.loads((tmp_path/'audit.json').read_bytes())
    assert result['requests']==2 and result['persistence'] is False
    assert all(row['source_qualification']=='MOCKED_EXPECTATION' for row in result['results'])
