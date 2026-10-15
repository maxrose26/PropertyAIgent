"""Unregistered proposal only; no source, engine or persistence execution."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import yaml
from verification.discovery import material_admission as shared
import verification.discovery as package

ROOT=Path('verification/discovery/proposals')
WF='.github/workflows/stage4-route-qualified-material-admission-once.yml'
AUTH='AUTHORISE_ROUTE_QUALIFIED_THREE_MATERIAL_ADMISSIONS_ONCE'

def test_proposal_is_unregistered_and_preserves_execution_controls():
    assert not Path(WF).exists()
    assert not Path('verification/discovery/material_admission_route_qualified.py').exists()
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

def test_proposed_binding_calls_only_shared_main():
    calls=[];fake=SimpleNamespace(main=lambda:calls.append('shared.main'))
    ns={'__name__':'proposal_not_installed'}
    with patch.object(package,'material_admission',fake):
        exec(compile((ROOT/'material_admission_route_qualified.py.txt').read_text(),'proposal','exec'),ns)
        ns['main']()
    assert calls==['shared.main'] and fake.WORKFLOW==WF and fake.AUTHORITY==AUTH

def test_proposed_single_use_binding_rejects_old_or_repeat_context():
    sha='a'*40
    env=dict(COMMITTEE_WORKFLOW_SHA=sha,GITHUB_REF='refs/heads/master',GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REPOSITORY='maxrose26/PropertyAIgent',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+WF+'@refs/heads/master')
    old=shared.WORKFLOW
    with patch.object(shared,'WORKFLOW',WF),patch.object(shared,'AUTHORITY',AUTH):
        assert shared.admitted(sha,AUTH,shared.MANIFEST_SHA,env)
        for key,value in [('GITHUB_RUN_NUMBER','2'),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_WORKFLOW_REF','maxrose26/PropertyAIgent/'+old+'@refs/heads/master')]:
            assert not shared.admitted(sha,AUTH,shared.MANIFEST_SHA,dict(env,**{key:value}))
        assert not shared.admitted(sha,AUTH,'0'*64,env)
