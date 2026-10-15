"""Registered exact16 and inert admission-proposal mappings/delegation."""
import hashlib,json,os,time
from pathlib import Path
from unittest.mock import patch
import pytest,yaml
from verification.discovery import r0_exact16 as x
from verification.discovery import bolton53_admission_binding as a
from verification.discovery import r0_proposal as outer
from verification.discovery import r0_registered_scopes as shared
from tests.test_discovery_r0_registered_scopes import context
from tests.test_discovery_r0_recovery_proposal import evidence


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for k in list(os.environ):
        if 'DATABASE' in k or k.startswith(('SUPABASE_','OPENAI_','ANTHROPIC_')):monkeypatch.delenv(k,raising=False)


def mapping(module):
    workflow=yaml.load(module.TEMPLATE.read_text(),Loader=yaml.BaseLoader)
    sha='a'*40
    env=dict(context('bolton53'),GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+module.WORKFLOW+'@refs/heads/master')
    replacements={'${{ inputs.reviewed_sha }}':sha,'${{ inputs.manifest_sha }}':x.MANIFEST_SHA if module is x else a.shared.COHORT_SHA,
        '${{ inputs.authority }}':module.AUTHORITY,'${{ github.workflow_sha }}':sha,'${{ env.SOURCE_JOB_STARTED_EPOCH }}':str(int(time.time()))}
    return workflow,env,replacements


@pytest.mark.parametrize('module',[x,a])
def test_actual_proposed_mapping_and_mutated_context(module,monkeypatch):
    monkeypatch.delenv('DATABASE_URL',raising=False)
    workflow,env,replacements=mapping(module);steps=workflow['jobs']['source']['steps']
    if module is x:
        assert Path(module.WORKFLOW).read_bytes()==module.TEMPLATE.read_bytes()
    else:assert not Path(module.WORKFLOW).exists()
    for step in [s for s in steps[1:] if 'env' in s]:
        mapped={k:replacements[v] for k,v in step['env'].items() if v in replacements}
        valid=dict(env,**mapped);manifest=mapped['MANIFEST_SHA']
        module.admit('a'*40,manifest,module.AUTHORITY,valid,workflow_bytes=module.TEMPLATE.read_bytes())
        for key,value in [('GITHUB_WORKFLOW_SHA','b'*40),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_RUN_NUMBER','2'),('GITHUB_SHA','b'*40),('GITHUB_WORKFLOW_REF','old')]:
            with pytest.raises(ValueError):module.admit('a'*40,manifest,module.AUTHORITY,dict(valid,**{key:value}),workflow_bytes=module.TEMPLATE.read_bytes())
        with pytest.raises(ValueError):module.admit('a'*40,manifest,module.AUTHORITY,valid,workflow_bytes=module.TEMPLATE.read_bytes()+b'changed')
    assert workflow['permissions']=={'contents':'read'}
    if module is x:
        assert 'environment' not in workflow['jobs']['source'] and 'secrets.' not in module.TEMPLATE.read_text()
        assert 'timeout --signal=TERM --kill-after=10s 1030s' in module.TEMPLATE.read_text()
    else:
        assert workflow['jobs']['source']['environment']=='stage4-production-canary'
        assert module.TEMPLATE.read_text().count('${{ secrets.DATABASE_URL }}')==1
        assert 'timeout --signal=TERM --kill-after=10s 9690s' in module.TEMPLATE.read_text()


def test_exact16_worker_uses_exact_manifest_and_existing_durable_store(tmp_path,monkeypatch):
    monkeypatch.delenv('DATABASE_URL',raising=False)
    calls=[]
    def read(row):calls.append(row);return evidence(row)
    with patch.object(x.finite,'read',read):x.execute_worker(x.plan(),tmp_path/'result.json',tmp_path)
    result=json.loads((tmp_path/'result.json').read_bytes())
    assert calls==json.loads(x.MANIFEST.read_bytes())['rows'] and len(calls)==16
    assert len(result['checkpoint_sha256'])==16 and result['completeness']=='INCOMPLETE'


def test_exact16_supervisor_selects_new_module_not_consumed_worker(tmp_path):
    # Existing outer supervisor's injected fake process prevents any source work.
    import inspect
    code=inspect.getsource(x.main)
    assert "worker_module='verification.discovery.r0_exact16'" in code
    code=inspect.getsource(outer.supervise_round)
    assert "from .r0_exact16 import validate_plan" in code
    assert 'worker_module' in code and "'--audit-dir'" in code
    assert x.PROFILE['seconds']==1000 and x.PROFILE['requests']==440


def test_actual_exact16_parent_supervisor_worker_delegation(tmp_path,monkeypatch):
    import sys,psutil
    from unittest.mock import MagicMock
    from tests.test_discovery_r0_registered_scopes import proc_namespace
    workflow,env,replacements=mapping(x);steps=workflow['jobs']['source']['steps']
    step=next(s for s in steps if s.get('name','').startswith('One owned-process'))
    env.update({k:replacements[v] for k,v in step['env'].items()})
    for k,v in env.items():monkeypatch.setenv(k,v)
    directory=tmp_path/'audit';calls=[];launches=[]
    def reader(row):
        assert len(list((directory/'checkpoints').glob('*.json')))==len(calls)
        calls.append(row);return evidence(row)
    def runner(command,**kw):
        launches.append(command)
        assert command[1:3]==['-m','verification.discovery.r0_exact16']
        assert not any('DATABASE' in k or 'AUTHORITY' in k for k in kw['env'])
        plan=json.loads(Path(command[command.index('--worker')+1]).read_bytes());assert plan==x.plan()
        x.execute_worker(plan,Path(command[command.index('--output')+1]),directory)
        child=MagicMock(pid=999999,returncode=0);child.poll.return_value=0;child.wait.return_value=0;return child
    real=outer.supervise_round;original_admit=x.admit
    monkeypatch.setattr(sys,'argv',['exact16','--reviewed-sha','a'*40,'--manifest-sha',x.MANIFEST_SHA,'--authority',x.AUTHORITY,'--output',str(directory)])
    with proc_namespace(),patch.object(x,'admit',side_effect=lambda sha,m,a,e:original_admit(sha,m,a,e,workflow_bytes=x.TEMPLATE.read_bytes())),patch.object(shared,'checkout'),patch.object(x.finite,'read',reader),patch.object(outer,'supervise_round',side_effect=lambda p,o,**kw:real(p,o,runner=runner,**kw)),patch.object(psutil,'Process',return_value=MagicMock()),patch.object(psutil,'wait_procs',return_value=([],[])):
        assert x.main()==0
    assert len(calls)==16 and len(launches)==1


@pytest.mark.parametrize('value',[{}, {'result':{'stop':None}}, {'stop_reason':None,'cleanup':'UNKNOWN'},
    {'stop_reason':None,'transaction':'UNKNOWN_COMMIT_OR_READBACK_NO_RETRY'}])
def test_admission_binding_never_promotes_missing_or_uncertain_output(value):
    assert not a.successful(value)
