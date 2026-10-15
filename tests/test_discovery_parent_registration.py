"""Registered fixed-two controls; no live transport or dispatch."""
import hashlib,os,time
from pathlib import Path
from unittest.mock import patch
import pytest,yaml
from verification.discovery import r0_parent_metadata as p
from tests.test_discovery_r0_registered_scopes import context


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for k in list(os.environ):
        if 'DATABASE' in k or k.startswith(('SUPABASE_','OPENAI_','ANTHROPIC_')):monkeypatch.delenv(k,raising=False)


def test_byte_equivalent_parent_fixed_limits_no_credentials():
    raw=Path(p.WORKFLOW).read_bytes();assert raw==p.TEMPLATE.read_bytes()
    assert hashlib.sha256(raw).hexdigest()=='386def0b214f8511d096ebe9905cb4c8e048ff741d23b36fe2088b2500192117'
    assert hashlib.sha256(p.MANIFEST.read_bytes()).hexdigest()==p.MANIFEST_SHA=='9997f55e9af0e646ccf376137f79534fbc73e75e0c0984dffc222ee811f711fa'
    w=yaml.load(raw,Loader=yaml.BaseLoader);job=w['jobs']['source']
    assert set(w['on'])=={'workflow_dispatch'} and set(w['on']['workflow_dispatch']['inputs'])=={'reviewed_sha','manifest_sha','authority'}
    assert w['permissions']=={'contents':'read'} and w['concurrency']['cancel-in-progress']=='false'
    assert 'environment' not in job and 'env' not in job and 'env' not in w
    assert 'secrets.' not in raw.decode() and 'DATABASE_URL' not in raw.decode()
    assert job['timeout-minutes']=='6' and p.PROFILE['setup_seconds']==120
    assert p.PROFILE['execution_seconds']==160 and p.PROFILE['source_seconds']==90
    assert (p.PROFILE['requests'],p.PROFILE['bytes'],p.PROFILE['output_bytes'])==(12,6000000,131072)
    assert 360-120-170-10>=60
    assert p.metadata.REFERENCES==('00284/26','20683/25')
    assert 'verification.discovery.r0_parent_metadata' in raw.decode()


def test_actual_registered_environment_content_and_history_controls():
    w=yaml.load(Path(p.WORKFLOW).read_text(),Loader=yaml.BaseLoader)
    env=dict(context('bolton53'),GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+p.WORKFLOW+'@refs/heads/master')
    values={'${{ inputs.reviewed_sha }}':'a'*40,'${{ inputs.manifest_sha }}':p.MANIFEST_SHA,
        '${{ inputs.authority }}':p.AUTHORITY,'${{ github.workflow_sha }}':'a'*40,
        '${{ env.SOURCE_JOB_STARTED_EPOCH }}':str(int(time.time()))}
    for step in w['jobs']['source']['steps'][1:]:
        if 'env' not in step:continue
        e=dict(env,**{k:values[v] for k,v in step['env'].items()})
        p.admit('a'*40,p.MANIFEST_SHA,p.AUTHORITY,e)
        for k,v in [('GITHUB_WORKFLOW_SHA',None),('GITHUB_WORKFLOW_SHA','b'*40),('GITHUB_SHA','b'*40),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_RUN_NUMBER','2'),('GITHUB_WORKFLOW_REF','consumed workflow'),('GITHUB_REF','refs/heads/other')]:
            with pytest.raises(ValueError):p.admit('a'*40,p.MANIFEST_SHA,p.AUTHORITY,dict(e,**{k:v}))
        for digest,authority in [('0'*64,p.AUTHORITY),(p.MANIFEST_SHA,'OLD_AUTHORITY')]:
            with pytest.raises(ValueError):p.admit('a'*40,digest,authority,e)
        with pytest.raises(ValueError):p.admit('a'*40,p.MANIFEST_SHA,p.AUTHORITY,dict(e,DATABASE_URL='forbidden'))
        original=Path.read_bytes
        def mutated(path):return original(path)+b'changed' if path.resolve()==Path(p.WORKFLOW).resolve() else original(path)
        with patch.object(Path,'read_bytes',mutated):
            with pytest.raises(ValueError,match='WORKFLOW_CONTENT'):p.admit('a'*40,p.MANIFEST_SHA,p.AUTHORITY,e)


@pytest.mark.parametrize('name',['stage4-discovery-offline.yml','stage4-batch-offline.yml'])
def test_parent_registration_triggers_and_suites(name):
    raw=Path('.github/workflows',name).read_text();w=yaml.load(raw,Loader=yaml.BaseLoader)
    assert p.WORKFLOW in w['on']['pull_request']['paths']
    assert 'tests/test_discovery_parent_registration.py' in raw and 'tests/test_discovery_parent_controls.py' in raw
