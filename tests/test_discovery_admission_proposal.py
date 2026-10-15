"""Registered binding controls; no source, engine or persistence execution."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import yaml
from verification.discovery import material_admission as shared
import verification.discovery as package

ROOT=Path('verification/discovery/proposals')
WF='.github/workflows/stage4-route-qualified-material-admission-once.yml'
AUTH='AUTHORISE_ROUTE_QUALIFIED_THREE_MATERIAL_ADMISSIONS_ONCE'

def test_registered_binding_preserves_execution_controls():
    assert Path(WF).read_bytes()==(ROOT/'stage4-route-qualified-material-admission-once.yml.txt').read_bytes()
    assert Path('verification/discovery/material_admission_route_qualified.py').read_bytes()==(ROOT/'material_admission_route_qualified.py.txt').read_bytes()
    w=yaml.load((ROOT/'stage4-route-qualified-material-admission-once.yml.txt').read_text(),Loader=yaml.BaseLoader)
    old=yaml.load(Path(shared.WORKFLOW).read_text(),Loader=yaml.BaseLoader)
    assert set(w['on'])=={'workflow_dispatch'} and set(w['jobs'])=={'admission'}
    assert w['permissions']==old['permissions'] and w['concurrency']==old['concurrency']
    j=w['jobs']['admission'];o=old['jobs']['admission']
    assert all(j[k]==o[k] for k in ('environment','runs-on','timeout-minutes'))
    assert len(j['steps'])==len(o['steps'])==5
    assert str(w).count('secrets.DATABASE_URL')==1
    assert AUTH in str(w) and shared.AUTHORITY not in str(w)
    assert shared.MANIFEST_SHA in str(w)
    assert '"$PIN" == "$GITHUB_SHA"' in j['steps'][0]['run']

def test_actual_binding_calls_only_shared_main():
    from verification.discovery import material_admission_route_qualified as binding
    calls=[];fake=SimpleNamespace(main=lambda:calls.append('shared.main'))
    with patch.object(binding,'shared',fake):
        binding.main()
    assert calls==['shared.main'] and fake.WORKFLOW==WF and fake.AUTHORITY==AUTH

def test_proposed_single_use_binding_rejects_old_or_repeat_context():
    sha='a'*40
    env=dict(COMMITTEE_WORKFLOW_SHA=sha,GITHUB_REF='refs/heads/master',GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REPOSITORY='maxrose26/PropertyAIgent',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+WF+'@refs/heads/master')
    old=shared.WORKFLOW
    from verification.discovery import material_admission_route_qualified as binding
    with patch.object(shared,'WORKFLOW',shared.WORKFLOW),patch.object(shared,'AUTHORITY',shared.AUTHORITY),patch.object(shared,'main') as main:
        binding.main()
        main.assert_called_once_with()
        assert shared.admitted(sha,AUTH,shared.MANIFEST_SHA,env)
        for key,value in [('GITHUB_RUN_NUMBER','2'),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_WORKFLOW_REF','maxrose26/PropertyAIgent/'+old+'@refs/heads/master')]:
            assert not shared.admitted(sha,AUTH,shared.MANIFEST_SHA,dict(env,**{key:value}))
        assert not shared.admitted(sha,AUTH,'0'*64,env)

        assert not shared.admitted('b'*40,AUTH,shared.MANIFEST_SHA,env)
        assert not shared.admitted(sha,'AUTHORISE_THREE_QUALIFIED_MATERIAL_COHORT_ADMISSIONS_ONCE',shared.MANIFEST_SHA,env)


def test_environment_exceptions_reject_mutated_registration():
    import importlib
    import pytest
    original=Path.read_bytes
    def changed(path):
        data=original(path)
        return data+b'\n# unreviewed\n' if str(path)==WF else data
    for module,name in [('tests.test_stage4_batch_registration','test_workflow_scope'),('tests.test_oldham_production_registration','test_environment_is_exclusive_to_live_job')]:
        with patch.object(Path,'read_bytes',changed),pytest.raises(AssertionError):
            getattr(importlib.import_module(module),name)()
