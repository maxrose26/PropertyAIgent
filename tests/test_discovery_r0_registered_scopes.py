"""Closed workflow -> real parent -> owned supervisor -> fixed worker wiring.

All process/source interactions are intercepted; network denial stays installed.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import MagicMock,patch
import pytest
import yaml
from verification.discovery import r0_registered_scopes as s
from verification.discovery import r0_proposal as outer
from verification.discovery import r0_fixed80_qualification as q
from verification.discovery import finite_acceptance as finite
from tests.test_discovery_fixed80_qualification import source
from tests.test_discovery_r0_recovery_proposal import evidence
from tests.test_discovery_page_cap_transport import capped_transport

SHA='a'*40

@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for key in list(os.environ):
        if 'DATABASE' in key or key.startswith(('SUPABASE_','OPENAI_','ANTHROPIC_')):
            monkeypatch.delenv(key,raising=False)


def workflow(scope):return yaml.load(Path(s.PROFILES[scope]['workflow']).read_text(),Loader=yaml.BaseLoader)


def context(scope):
    p=s.PROFILES[scope]
    return dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_REPOSITORY='maxrose26/PropertyAIgent',
        GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF='refs/heads/master',GITHUB_SHA=SHA,GITHUB_WORKFLOW_SHA=SHA,
        GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+p['workflow']+'@refs/heads/master',GITHUB_RUN_NUMBER='1',
        GITHUB_RUN_ATTEMPT='1',GITHUB_RUN_ID='999',JOB_STARTED_EPOCH=str(int(time.time())))


def mapped_step(scope,step):
    p=s.PROFILES[scope]
    values={'${{ inputs.reviewed_sha }}':SHA,'${{ inputs.manifest_sha }}':p['manifest_sha'],
      '${{ inputs.authority }}':p['authority'],'${{ github.workflow_sha }}':SHA,
      '${{ env.SOURCE_JOB_STARTED_EPOCH }}':str(int(time.time()))}
    return {k:values[v] for k,v in step.get('env',{}).items()}


@pytest.mark.parametrize('scope',s.PROFILES)
def test_actual_registered_content_controls_and_mapping(scope):
    p=s.PROFILES[scope];raw=Path(p['workflow']).read_bytes();w=workflow(scope)
    assert hashlib.sha256(raw).hexdigest()==s.WORKFLOW_HASHES[scope]
    assert raw==(Path('docs/design/stage4-r0-execution/bounded-registration')/Path(p['workflow']).name).read_bytes()
    assert set(w['on'])=={'workflow_dispatch'} and set(w['on']['workflow_dispatch']['inputs'])=={'reviewed_sha','manifest_sha','authority'}
    assert w['permissions']=={'contents':'read'} and w['concurrency']['cancel-in-progress']=='false'
    assert 'env' not in w and set(w['jobs'])=={'source'}
    job=w['jobs']['source'];assert 'environment' not in job and 'env' not in job
    assert 'secrets.' not in raw.decode() and 'DATABASE_URL' not in raw.decode()
    assert int(job['timeout-minutes'])*60==p['job_seconds']
    steps=job['steps'];assert steps[0]['name']=='Single-use binding before checkout or dependencies'
    checkout=next(x for x in steps if x.get('uses')=='actions/checkout@v4')
    assert checkout['with']=={'ref':'${{ inputs.reviewed_sha }}','persist-credentials':'false'}
    parents=[x for x in steps if 'env' in x]
    for step in parents:
        mapped=mapped_step(scope,step);env=dict(context(scope),**mapped)
        s.admit(scope,mapped['REVIEWED_SHA'],mapped['MANIFEST_SHA'],mapped['SOURCE_AUTHORITY'],env)
    execution=next(x for x in steps if x.get('name','').startswith('One owned-process'))
    assert f'--scope {scope}' in execution['run'] and 'verification.discovery.r0_registered_scopes' in execution['run']
    assert '--authority "$SOURCE_AUTHORITY"' in execution['run']
    gate=next(x for x in steps if x.get('id')=='audit_gate')
    assert gate['if']=='always()' and '--verify-audit' in gate['run']
    upload=next(x for x in steps if x.get('uses')=='actions/upload-artifact@v4')
    assert "steps.audit_gate.outcome == 'success'" in upload['if']


@pytest.mark.parametrize('scope',s.PROFILES)
@pytest.mark.parametrize('key,value',[
 ('GITHUB_WORKFLOW_SHA',None),('GITHUB_WORKFLOW_SHA','b'*40),('GITHUB_SHA','b'*40),
 ('GITHUB_RUN_NUMBER','2'),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_REF','refs/heads/other'),
 ('GITHUB_EVENT_NAME','push'),('JOB_STARTED_EPOCH','0'),
])
def test_context_rejected_before_any_source(scope,key,value):
    env=context(scope);p=s.PROFILES[scope]
    if value is None:env.pop(key)
    else:env[key]=value
    with patch.object(q,'read') as reader,pytest.raises(ValueError):
        s.admit(scope,SHA,p['manifest_sha'],p['authority'],env)
    reader.assert_not_called()


@pytest.mark.parametrize('scope',s.PROFILES)
def test_cross_scope_old_authority_manifest_and_mutated_content_rejected(scope,monkeypatch):
    p=s.PROFILES[scope];env=context(scope);other=s.PROFILES['untouched27' if scope=='fixed80' else 'fixed80']
    for manifest,authority in [(other['manifest_sha'],p['authority']),(p['manifest_sha'],other['authority']),
      (p['manifest_sha'],'AUTHORISE_SEVEN_COUNCIL_R0_UNTOUCHED_WINDOW_RECOVERY_ONCE')]:
        with pytest.raises(ValueError):s.admit(scope,SHA,manifest,authority,env)
    monkeypatch.setitem(s.WORKFLOW_HASHES,scope,'0'*64)
    with pytest.raises(ValueError,match='WORKFLOW_CONTENT'):s.admit(scope,SHA,p['manifest_sha'],p['authority'],env)


@pytest.mark.parametrize('scope',s.PROFILES)
def test_initial_shell_gate_actual_mapping_fails_before_checkout(scope,tmp_path):
    import subprocess
    step=workflow(scope)['jobs']['source']['steps'][0]
    env=dict(context(scope),**mapped_step(scope,step),PATH='/usr/bin:/bin',GITHUB_ENV=str(tmp_path/'env'))
    good=subprocess.run(['bash','-c',step['run']],env=env,capture_output=True)
    assert good.returncode==0 and 'SOURCE_JOB_STARTED_EPOCH=' in (tmp_path/'env').read_text()
    bad=subprocess.run(['bash','-c',step['run']],env=dict(env,GITHUB_RUN_ATTEMPT='2'),capture_output=True)
    assert bad.returncode!=0


def proc_namespace():
    read=Path.read_text
    def fake(path,*a,**kw):
        return str(os.getpid())+' synthetic-stat' if str(path)=='/proc/self/stat' else read(path,*a,**kw)
    return patch.object(Path,'read_text',fake)


@pytest.mark.parametrize('scope,expected', [('fixed80',80),('untouched27',27),('untouched20',20)])
def test_actual_parent_outer_worker_checkpoint_delegation(scope,expected,tmp_path,monkeypatch):
    directory=tmp_path/'audit';p=s.PROFILES[scope];calls=[];launches=[]
    def reader80(i,row):
        assert len(list((directory/'checkpoints').glob('*.json')))==i
        calls.append(row['reference']);return source(row,False)
    def reader27(row):
        assert len(list((directory/'checkpoints').glob('*.json')))==len(calls)
        calls.append(row)
        return capped_transport(row) if len(calls)==1 else evidence(row)
    def runner(argv,**kw):
        launches.append((argv,kw));assert argv[1:3]==['-m','verification.discovery.r0_registered_scopes']
        assert set(kw['env'])=={'PATH','HOME','TMPDIR','PYTHONDONTWRITEBYTECODE','GITHUB_ACTIONS','RUNNER_ENVIRONMENT','PLAYWRIGHT_BROWSERS_PATH'}
        assert 'DATABASE_URL' not in kw['env'] and 'SOURCE_AUTHORITY' not in kw['env']
        value=json.loads(Path(argv[argv.index('--worker')+1]).read_text());assert value==s.plan(scope)
        assert Path(argv[argv.index('--audit-dir')+1])==directory
        s.execute_worker(value,Path(argv[argv.index('--output')+1]),directory)
        c=MagicMock(pid=999999,returncode=0);c.poll.return_value=0;c.wait.return_value=0;return c
    import psutil
    real_supervise=s.supervise
    for k,v in context(scope).items():monkeypatch.setenv(k,v)
    monkeypatch.setattr(sys,'argv',['r0','--scope',scope,'--reviewed-sha',SHA,'--manifest-sha',p['manifest_sha'],
      '--authority',p['authority'],'--output',str(directory)])
    with proc_namespace(),patch.object(s,'checkout') as checkout,patch.object(q,'read',reader80),patch.object(finite,'read',reader27),\
      patch.object(s,'supervise',lambda value,out:real_supervise(value,out,runner=runner)),\
      patch.object(psutil,'Process',return_value=MagicMock()),patch.object(psutil,'wait_procs',return_value=([],[])):
        assert s.main()==0
    checkout.assert_called_once_with(SHA)
    assert len(calls)==expected and len(launches)==1
    assert len(list((directory/'checkpoints').glob('*.json')))==expected
    result=json.loads((directory/'result.json').read_text());metadata=json.loads((directory/'execution.json').read_text())
    assert result['outer_supervisor']['cleanup']=='CLOSED' and not result['outer_supervisor']['expired']
    assert s.verify_export(scope,directory,context(scope))==s.audit_bytes(directory)<=p['output_bytes']
    assert metadata['aggregate_audit_bytes']==s.audit_bytes(directory)
    if scope!='fixed80':
        assert result['results'][0]['safe_local_gap'] and result['results'][0]['enumeration_completeness']=='INCOMPLETE'
        assert len(result['results'][0]['source']['listing_records'])==60
        assert result['completeness']=='INCOMPLETE' and not result['completed_through_advanced']


@pytest.mark.parametrize('scope',s.PROFILES)
def test_checkpoint_failure_stops_next_source_and_preserves_diagnostic(scope,tmp_path):
    calls=[];value=s.plan(scope)
    def read80(i,row):calls.append(i);return source(row,False)
    def read27(row):calls.append(row);return evidence(row)
    with patch.object(q,'read',read80),patch.object(finite,'read',read27),patch.object(s.os,'fsync',side_effect=OSError('fixed-test')):
        s.execute_worker(value,tmp_path/'result.json',tmp_path)
    assert len(calls)==1
    result=json.loads((tmp_path/'result.json').read_text())
    assert result['stop_reason']=='FINAL_AUDIT_FAILURE_NO_RETRY'
    assert len(list((tmp_path/'checkpoints').glob('*.json')))==1


def test_audit_store_reserves_final_copy_and_enforces_aggregate_bytes(tmp_path):
    profile=dict(s.PROFILES['fixed80'],output_bytes=s.AUDIT_RESERVE+100)
    store=s.AuditStore(tmp_path,profile)
    with pytest.raises(ValueError,match='AGGREGATE_AUDIT'):store.record({'value':'x'*100})
    assert not list((tmp_path/'checkpoints').iterdir())


@pytest.mark.parametrize('cause',['DEADLINE','RSS','AUDIT_BYTES'])
def test_outer_hard_limits_kill_owned_group_and_preserve_checkpoints(cause,tmp_path):
    value=s.plan('fixed80');signals=[];profile=s.PROFILES['fixed80']
    fake=MagicMock(pid=999999,returncode=None);fake.poll.return_value=None
    def waited(**kw):fake.returncode=-9;return -9
    fake.wait.side_effect=waited
    process=MagicMock(pid=999999);process.children.return_value=[];process.create_time.return_value=1
    process.memory_info.return_value.rss=s.RSS_LIMIT+1 if cause=='RSS' else 10
    import psutil
    def runner(argv,**kw):return fake
    ticks=iter([0,profile['seconds']+1,profile['seconds']+2,profile['seconds']+3]) if cause=='DEADLINE' else None
    def measured(_):return profile['output_bytes'] if cause=='AUDIT_BYTES' else 0
    # audit_bytes initial guard must see zero, then the mocked live measurement.
    amounts=iter([0,profile['output_bytes'],0,0,0,0])
    audit=lambda _:next(amounts,0) if cause=='AUDIT_BYTES' else 0
    with proc_namespace(),patch.object(psutil,'Process',return_value=process),patch.object(psutil,'wait_procs',return_value=([],[])),\
      patch.object(outer.os,'killpg',side_effect=lambda pid,sig:signals.append(pid)),\
      patch.object(s,'audit_bytes',audit),patch.object(outer.time,'sleep',lambda _:None),\
      patch.object(outer.time,'monotonic',side_effect=(lambda:next(ticks,profile['seconds']+3)) if ticks else lambda:0):
        # Mark tracked process gone after cleanup; no real PID is touched.
        process.status.side_effect=[psutil.STATUS_RUNNING,psutil.STATUS_ZOMBIE]
        result=s.supervise(value,tmp_path/'result.json',runner=runner)
    assert signals==[999999] and result['outer_supervisor']['expired']
    assert result['outer_supervisor']['limit_hit']==cause and result['outer_supervisor']['cleanup']=='CLOSED'
    assert result['accounting_complete'] is False


def test_clean_checkout_and_output_export_fail_closed(tmp_path):
    with patch.object(s.subprocess,'check_output',side_effect=[SHA+'\n',' M file']):
        with pytest.raises(ValueError):s.checkout(SHA)
    (tmp_path/'unexpected.txt').write_text('not exportable')
    with pytest.raises(ValueError):s.verify_export('fixed80',tmp_path,context('fixed80'))

@pytest.mark.parametrize('change',[
 {'failure':'SOURCE_EXCEPTION'}, {'safety_failure':True}, {'destination':'https://wrong.invalid/'},
 {'applied_interval':None}, {'process_cleanup':'UNKNOWN'}, {'requests':None},
])
@pytest.mark.parametrize('scope', ['untouched27','untouched20'])
def test_real_capped_transport_mutated_hard_failures_stop_new27(change,tmp_path,scope):
    calls=[]
    def reader(row):
        calls.append(row);return dict(capped_transport(row),**change)
    with patch.object(finite,'read',reader):s.execute_worker(s.plan(scope),tmp_path/'result.json',tmp_path)
    out=json.loads((tmp_path/'result.json').read_bytes())
    assert len(calls)==1 and len(out['not_attempted'])==s.PROFILES[scope]['calls']-1 and out['stop_reason']
    assert out['completeness']=='INCOMPLETE' and len(list((tmp_path/'checkpoints').glob('*.json')))==1


def test_outer_accounting_exception_kills_and_never_reports_success(tmp_path):
    import psutil
    child=MagicMock(pid=999999,returncode=None);child.poll.return_value=None
    def waited(**kw):child.returncode=-9;return -9
    child.wait.side_effect=waited
    with proc_namespace(),patch.object(psutil,'Process',side_effect=psutil.AccessDenied(999999)),\
      patch.object(psutil,'wait_procs',return_value=([],[])),patch.object(outer.os,'killpg') as kill:
        out=s.supervise(s.plan('fixed80'),tmp_path/'result.json',runner=lambda *a,**k:child)
    kill.assert_called_once()
    assert out['accounting_complete'] is False
    assert out['stop_reason']=='OUTER_ACCOUNTING_OR_CLEANUP_UNCERTAIN'
    assert out['outer_supervisor']['cleanup']=='UNKNOWN'


def test_ci_covers_new_workflows_controller_and_test():
    for path in ['.github/workflows/stage4-discovery-offline.yml','.github/workflows/stage4-batch-offline.yml']:
        w=yaml.load(Path(path).read_text(),Loader=yaml.BaseLoader)
        patterns=w['on']['pull_request']['paths']
        from fnmatch import fnmatch
        for target in [p['workflow'] for p in s.PROFILES.values()]+[
          'verification/discovery/r0_registered_scopes.py','verification/discovery/r0_proposal.py',
          'verification/discovery/r0_recovery_proposal.py','verification/discovery/r0_fixed80_qualification.py',
          'tests/test_discovery_r0_registered_scopes.py']:
            assert any(fnmatch(target,x) for x in patterns),(path,target)
        assert 'tests/test_discovery_r0_registered_scopes.py' in str(w['jobs']['offline']['steps'])
