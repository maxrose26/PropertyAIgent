"""Byte-equivalent exact9 registration, actual environment controls, no dispatch."""
import hashlib,os,time
from pathlib import Path
from unittest.mock import patch
import pytest,yaml
from verification.discovery import r0_exact9 as x
from tests.test_discovery_r0_registered_scopes import context


def test_registered_exact9_identity_scope_and_ceilings():
    raw=Path(x.WORKFLOW).read_bytes();assert raw==x.TEMPLATE.read_bytes()
    assert hashlib.sha256(raw).hexdigest()=='57489b54cf402e7aa11dc0428806e063b337247cf278d6bef30c950347e6e825'
    assert hashlib.sha256(x.MANIFEST.read_bytes()).hexdigest()==x.MANIFEST_SHA
    w=yaml.load(raw,Loader=yaml.BaseLoader);job=w['jobs']['source']
    assert set(w['on'])=={'workflow_dispatch'} and set(w['on']['workflow_dispatch']['inputs'])=={'reviewed_sha','manifest_sha','authority'}
    assert w['permissions']=={'contents':'read'} and w['concurrency']['cancel-in-progress']=='false'
    assert 'environment' not in job and 'env' not in job and 'env' not in w
    assert 'secrets.' not in raw.decode() and 'DATABASE_URL' not in raw.decode()
    assert job['timeout-minutes']=='16'
    assert (x.PROFILE['calls'],x.PROFILE['requests'],x.PROFILE['bytes'],x.PROFILE['seconds'])==(9,90,27000000,495)
    assert 960-260-525-10>=120
    from verification.discovery.r0_parent_metadata import WORKFLOW,TEMPLATE
    assert Path(WORKFLOW).read_bytes()==TEMPLATE.read_bytes()


def test_actual_registered_mapping_and_content_rejection(monkeypatch):
    for k in list(os.environ):
        if 'DATABASE' in k or k.startswith(('SUPABASE_','OPENAI_','ANTHROPIC_')):monkeypatch.delenv(k,raising=False)
    w=yaml.load(Path(x.WORKFLOW).read_text(),Loader=yaml.BaseLoader)
    env=dict(context('bolton53'),GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+x.WORKFLOW+'@refs/heads/master')
    values={'${{ inputs.reviewed_sha }}':'a'*40,'${{ inputs.manifest_sha }}':x.MANIFEST_SHA,'${{ inputs.authority }}':x.AUTHORITY,'${{ github.workflow_sha }}':'a'*40,'${{ env.SOURCE_JOB_STARTED_EPOCH }}':str(int(time.time()))}
    for step in w['jobs']['source']['steps'][1:]:
        if 'env' not in step:continue
        e=dict(env,**{k:values[v] for k,v in step['env'].items()})
        x.admit('a'*40,x.MANIFEST_SHA,x.AUTHORITY,e)
        for k,v in [('GITHUB_WORKFLOW_SHA',None),('GITHUB_WORKFLOW_SHA','b'*40),('GITHUB_RUN_NUMBER','2'),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_SHA','b'*40)]:
            with pytest.raises(ValueError):x.admit('a'*40,x.MANIFEST_SHA,x.AUTHORITY,dict(e,**{k:v}))
        real=Path.read_bytes
        def mutated(p):return real(p)+b'changed' if p.resolve()==Path(x.WORKFLOW).resolve() else real(p)
        with patch.object(Path,'read_bytes',mutated):
            with pytest.raises(ValueError,match='WORKFLOW_CONTENT'):x.admit('a'*40,x.MANIFEST_SHA,x.AUTHORITY,e)


@pytest.mark.parametrize('name',['stage4-discovery-offline.yml','stage4-batch-offline.yml'])
def test_registration_ci_paths_and_affected_suites(name):
    text=Path('.github/workflows',name).read_text();w=yaml.load(text,Loader=yaml.BaseLoader)
    assert x.WORKFLOW in w['on']['pull_request']['paths']
    assert 'tests/test_discovery_exact9_registration.py' in text
