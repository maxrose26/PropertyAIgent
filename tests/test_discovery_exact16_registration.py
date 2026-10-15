"""Exact reviewed registration only; admission workflow remains absent."""
import hashlib,json,os,time
from pathlib import Path
from unittest.mock import patch
import pytest,yaml
from verification.discovery import r0_exact16 as x
from tests.test_discovery_exact16_proposal import mapping


def test_registered_byte_equivalence_and_unchanged_limits():
    raw=Path(x.WORKFLOW).read_bytes()
    assert raw==x.TEMPLATE.read_bytes()
    assert hashlib.sha256(raw).hexdigest()=='f8d0e33c29f3ba396b314026ebb6b86f6e4b010159e404fd59f3bb08146c6391'
    assert hashlib.sha256(x.MANIFEST.read_bytes()).hexdigest()==x.MANIFEST_SHA=='aaabab2f0757ba8c373c7588322618ee6d9bbeff3f21fdd08638b147d8be6283'
    w=yaml.load(raw,Loader=yaml.BaseLoader);job=w['jobs']['source']
    assert set(w['on'])=={'workflow_dispatch'} and set(w['on']['workflow_dispatch']['inputs'])=={'reviewed_sha','manifest_sha','authority'}
    assert w['permissions']=={'contents':'read'} and w['concurrency']['cancel-in-progress']=='false'
    assert 'environment' not in job and 'env' not in w and 'env' not in job
    assert 'secrets.' not in raw.decode() and 'DATABASE_URL' not in raw.decode()
    assert job['timeout-minutes']=='24' and x.PROFILE['setup_seconds']==260
    assert x.PROFILE['calls']==16 and x.PROFILE['requests']==440 and x.PROFILE['bytes']==119886080
    assert x.PROFILE['seconds']==1000 and x.PROFILE['output_bytes']==20_000_000
    steps=job['steps'];install=next(i for i,s in enumerate(steps) if 'playwright install' in s.get('run',''))
    guard=next(i for i,s in enumerate(steps) if s.get('name','').startswith('Exact content'))
    assert install<guard
    assert 'timeout --signal=TERM --kill-after=10s 1030s' in raw.decode()
    assert 1440-260-1030-10>=120
    assert not Path('.github/workflows/stage4-r0-bolton53-admission-once.yml').exists()


def test_actual_registered_env_reaches_binding_and_rejects_mutation():
    w,env,replacements=mapping(x)
    for step in w['jobs']['source']['steps'][1:]:
        if 'env' not in step:continue
        mapped={k:replacements[v] for k,v in step['env'].items()}
        valid=dict(env,**mapped)
        # No injected ideal content: real registered path is read by the validator.
        x.admit('a'*40,x.MANIFEST_SHA,x.AUTHORITY,valid)
        original=Path.read_bytes
        def changed(path):
            raw=original(path)
            return raw+b'changed' if path.resolve()==Path(x.WORKFLOW).resolve() else raw
        with patch.object(Path,'read_bytes',changed):
            with pytest.raises(ValueError,match='WORKFLOW_CONTENT_REJECTED'):x.admit('a'*40,x.MANIFEST_SHA,x.AUTHORITY,valid)
        for key,value in [('GITHUB_WORKFLOW_SHA',None),('GITHUB_WORKFLOW_SHA','b'*40),('GITHUB_RUN_NUMBER','2'),('GITHUB_RUN_ATTEMPT','2')]:
            changed=dict(valid,**{key:value})
            with pytest.raises(ValueError):x.admit('a'*40,x.MANIFEST_SHA,x.AUTHORITY,changed)


@pytest.mark.parametrize('file',['stage4-discovery-offline.yml','stage4-batch-offline.yml'])
def test_registration_ci_trigger_and_suite_coverage(file):
    w=yaml.load(Path('.github/workflows',file).read_text(),Loader=yaml.BaseLoader)
    paths=w['on']['pull_request']['paths'];assert x.WORKFLOW in paths
    assert 'verification/discovery/**' in paths or 'verification/discovery/r0_exact16.py' in paths
    text=Path('.github/workflows',file).read_text()
    assert 'tests/test_discovery_exact16_registration.py' in text and 'tests/test_discovery_exact16_proposal.py' in text
