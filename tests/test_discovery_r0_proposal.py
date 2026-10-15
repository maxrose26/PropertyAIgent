from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import os, pytest
from datetime import datetime,timezone
from verification.discovery import r0_proposal as r
from tests.test_discovery_finite_acceptance import evidence


def context():
    sha='a'*40
    return dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_REPOSITORY='maxrose26/PropertyAIgent',
        GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF='refs/heads/master',GITHUB_SHA=sha,GITHUB_WORKFLOW_SHA=sha,
        GITHUB_WORKFLOW_REF=f'maxrose26/PropertyAIgent/{r.WORKFLOW}@refs/heads/master',
        GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',R0_AUTHORITY=r.AUTHORITY)


def test_r0_scope_overlap_and_explicit_older_partitions():
    p=r.proposal();assert p['start']=='2026-09-29' and p['cut_exclusive']=='2026-10-16'
    assert p['rounds'][0]['start']=='2026-09-18' and p['rounds'][-1]['end']=='2026-10-15'
    assert len(p['rounds'][0]['rows'])==36
    with patch.object(r,'CUT','2026-11-06'):
        p=r.proposal();assert len(p['rounds'])==2
        assert p['rounds'][0]['start']=='2026-09-29' and p['rounds'][-1]['end']=='2026-11-05'
        assert p['rounds'][0]['end']=='2026-10-26' and p['rounds'][1]['start']=='2026-10-27'

@pytest.mark.parametrize('key,value', [('GITHUB_RUN_NUMBER','2'),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_REF','refs/heads/other'),
    ('GITHUB_WORKFLOW_SHA','b'*40),('R0_AUTHORITY','old'),('GITHUB_WORKFLOW_REF','other'),('DATABASE_URL','synthetic')])
def test_admission_closed_before_any_execution(key,value):
    env=context();r.admit(env,'a'*40,r.PLAN_HASH,now=datetime(2026,10,16,tzinfo=timezone.utc));env[key]=value
    with pytest.raises(ValueError):r.admit(env,'a'*40,r.PLAN_HASH,now=datetime(2026,10,16,tzinfo=timezone.utc))


def test_manifest_revision_mismatch():
    for sha,h in [('a'*40,'0'*64),('notsha',r.PLAN_HASH)]:
        with pytest.raises(ValueError):r.admit(context(),sha,h)


def test_new_window_qualification_needs_independent_seal():
    row=r.PLAN['rounds'][0]['rows'][0];source=dict(evidence(row),primary_observation={'started_at':'2026-10-16T00:00:00+00:00','ended_at':'2026-10-16T00:01:00+00:00'})
    assert r.qualify(row,source,{})=='UNKNOWN'
    independent=dict(council=row['council'],interval=[row['start'],row['end']],semantics=row['semantics'],complete=True,
        sealed_before_primary_reveal=True,criteria_verified=True,terminal_verified=True,evidence_sha256='b'*64,
        references=[],segments=1,explicit_zero=True,assessor='independent-operator',assessor_session='blind-session',primary_session='primary-session',
        observed_started_at='2026-10-16T00:00:00+00:00',observed_ended_at='2026-10-16T00:02:00+00:00',
        sealed_at='2026-10-16T00:03:00+00:00',primary_revealed_at='2026-10-16T00:04:00+00:00')
    assert r.qualify(row,source,independent)=='COMPLETE'
    for k,v in [('sealed_before_primary_reveal',False),('criteria_verified',False),('semantics','PUBLICATION'),('explicit_zero',False),('sealed_at','2026-10-16T00:05:00+00:00'),('assessor_session','primary-session'),('primary_revealed_at',None)]:
        assert r.qualify(row,source,dict(independent,**{k:v}))=='UNKNOWN'
    assert r.qualify(row,source,dict(independent,references=['MISSING/26']))=='UNKNOWN'
    assert r.qualify(row,dict(source,capped=True),independent)=='UNKNOWN'


def test_registered_equivalence_credential_free_and_ci_included():
    root=Path(__file__).resolve().parents[1]
    assert (root/r.WORKFLOW).read_bytes()==(root/'docs/design/stage4-r0-execution/workflow-proposal.yml').read_bytes()
    assert_registered_workflow((root/r.WORKFLOW).read_text())
    template=(root/'docs/design/stage4-r0-execution/workflow-proposal.yml').read_text()
    for forbidden in ('secrets.','environment:','schedule:','DATABASE_URL:','workflow_run:'):assert forbidden not in template
    assert '1930s' in template and 'timeout-minutes: 38' in template and 'persist-credentials: false' in template
    ci=(root/'.github/workflows/stage4-discovery-offline.yml').read_text()
    assert "'docs/design/stage4-r0-execution/**'" in ci
    assert 'tests/test_discovery_r0_proposal.py' in ci and 'tests/test_discovery_finite_acceptance.py' in ci
    assert r.WORKFLOW in ci
    batch=(root/'.github/workflows/stage4-batch-offline.yml').read_text()
    assert r.WORKFLOW in batch and 'tests/test_discovery_r0_proposal.py' in batch


def test_hard_supervisor_offline_child_cleanup(tmp_path,monkeypatch):
    # Actual disposable subprocess, no source reader/engine/network path invoked.
    import subprocess,sys
    if int(Path('/proc/self/stat').read_text().split()[0])!=os.getpid():
        with pytest.raises(ValueError,match='PROCESS_NAMESPACE_MISMATCH'):
            r.supervise_round(r.PLAN['rounds'][0],tmp_path/'audit.json',runner=lambda *a,**k:pytest.fail('no spawn'))
        return
    original=subprocess.Popen
    def spawn(command,**kwargs):
        assert set(kwargs['env'])=={'PATH','HOME','TMPDIR','PYTHONDONTWRITEBYTECODE','GITHUB_ACTIONS','RUNNER_ENVIRONMENT','PLAYWRIGHT_BROWSERS_PATH'}
        return original([sys.executable,'-c','pass'],**kwargs)
    result=r.supervise_round(r.PLAN['rounds'][0],tmp_path/'audit.json',runner=spawn)
    assert result['outer_supervisor']['cleanup']=='CLOSED'
    assert result['outer_supervisor']['live_owned_survivors']==0
    assert result['accounting_complete'] is False and result['completeness']=='UNKNOWN'


def test_cut_guard_before_sources():
    with pytest.raises(ValueError,match='CUT_NOT_REACHED'):
        r.admit(context(),'a'*40,r.PLAN_HASH,now=datetime(2026,10,15,tzinfo=timezone.utc))


def test_supervisor_deadline_preserves_unknown_and_terminates(monkeypatch,tmp_path):
    import psutil
    class Process:
        pid=123
        alive=True
        def __init__(self,*a):pass
        def children(self,recursive):return []
        def create_time(self):return 42
        def memory_info(self):return type('M',(),{'rss':1})()
        def status(self):return 'running' if self.alive else psutil.STATUS_ZOMBIE
        def kill(self):Process.alive=False
    class Child:
        pid=123
        returncode=None
        def poll(self):return None
        def wait(self,timeout):self.returncode=-9;return -9
    monkeypatch.setattr(psutil,'Process',Process)
    monkeypatch.setattr(psutil,'wait_procs',lambda *a,**k:([],[]))
    monkeypatch.setattr(r.os,'getpid',lambda:int(Path('/proc/self/stat').read_text().split()[0]))
    killed=[];monkeypatch.setattr(r.os,'killpg',lambda *a:killed.append(a))
    times=iter([0,1901,1902]);monkeypatch.setattr(r.time,'monotonic',lambda:next(times))
    result=r.supervise_round(r.PLAN['rounds'][0],tmp_path/'audit.json',runner=lambda *a,**k:Child())
    assert killed and result['outer_supervisor']['expired']
    assert result['completeness']=='UNKNOWN' and result['accounting_complete'] is False
    assert result['outer_supervisor']['cleanup']=='CLOSED'


def test_actual_workflow_parent_environment_mapping(monkeypatch):
    import yaml
    root=Path(__file__).resolve().parents[1]
    workflow=yaml.safe_load((root/'docs/design/stage4-r0-execution/workflow-proposal.yml').read_text())
    checks=[step for step in workflow['jobs']['observation']['steps'] if 'env' in step]
    assert len(checks)==2
    expressions={'${{ inputs.reviewed_sha }}':'a'*40, '${{ inputs.manifest_sha }}':r.PLAN_HASH,
        '${{ inputs.authority }}':r.AUTHORITY, '${{ github.workflow_sha }}':'a'*40}
    defaults=context();defaults.pop('GITHUB_WORKFLOW_SHA');defaults.pop('R0_AUTHORITY')
    for step in checks:
        assert step['env']['GITHUB_WORKFLOW_SHA']=='${{ github.workflow_sha }}'
        resolved={k:expressions[v] for k,v in step['env'].items()}
        env=dict(defaults,**resolved)
        with patch.object(r.f,'read',side_effect=AssertionError('no source')) as source:
            r.admit(env,env['REVIEWED_SHA'],env['MANIFEST_SHA'],now=datetime(2026,10,16,tzinfo=timezone.utc))
            for bad in (None,'b'*40):
                broken=dict(env)
                if bad is None:broken.pop('GITHUB_WORKFLOW_SHA')
                else:broken['GITHUB_WORKFLOW_SHA']=bad
                with pytest.raises(ValueError,match='R0_ADMISSION_REJECTED'):
                    r.admit(broken,broken['REVIEWED_SHA'],broken['MANIFEST_SHA'],now=datetime(2026,10,16,tzinfo=timezone.utc))
            source.assert_not_called()


def test_reference_difference_is_unresolved_not_parser_failure():
    out=r.reference_difference(['A/26'],['B/26'])
    assert out==dict(outcome='UNRESOLVED_REFERENCE_DIFFERENCE',primary_only=['A/26'],independent_only=['B/26'],cause='UNKNOWN_SOURCE_CHANGE_OR_ENUMERATION')


def assert_registered_workflow(text):
    import hashlib,yaml
    assert hashlib.sha256(text.encode()).hexdigest()==WORKFLOW_SHA256
    w=yaml.load(text,Loader=yaml.BaseLoader)
    assert set(w['on'])=={'workflow_dispatch'} and set(w['jobs'])=={'observation'}
    assert set(w['on']['workflow_dispatch']['inputs'])=={'reviewed_sha','manifest_sha','authority'}
    assert w['permissions']=={'contents':'read'}
    job=w['jobs']['observation']
    assert job['runs-on']=='ubuntu-24.04' and job['timeout-minutes']=='38'
    assert 'environment' not in job and 'env' not in job and 'env' not in w
    assert 'secrets.' not in text and 'DATABASE_URL:' not in text
    for step in job['steps']:
        if 'env' in step:assert step['env']['GITHUB_WORKFLOW_SHA']=='${{ github.workflow_sha }}'


@pytest.mark.parametrize('old,new',[('1930s','3930s'),('timeout-minutes: 38','timeout-minutes: 99'),
    ('${{ github.workflow_sha }}','${{ github.sha }}'),('persist-credentials: false','persist-credentials: true')])
def test_registration_mutations_rejected(old,new):
    root=Path(__file__).resolve().parents[1]
    text=(root/r.WORKFLOW).read_text();assert old in text
    with pytest.raises(AssertionError):assert_registered_workflow(text.replace(old,new))

WORKFLOW_SHA256='5766acc2a137d50c4072d3153b6a0c52e7966580a66298c602d4d68484e4d893'
