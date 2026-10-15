from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import os, pytest
from verification.discovery import r0_proposal as r
from tests.test_discovery_finite_acceptance import evidence


def context():
    sha='a'*40
    return dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_REPOSITORY='maxrose26/PropertyAIgent',
        GITHUB_REF='refs/heads/master',GITHUB_SHA=sha,GITHUB_WORKFLOW_SHA=sha,
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
    env=context();r.admit(env,'a'*40,r.PLAN_HASH);env[key]=value
    with pytest.raises(ValueError):r.admit(env,'a'*40,r.PLAN_HASH)


def test_manifest_revision_mismatch():
    for sha,h in [('a'*40,'0'*64),('notsha',r.PLAN_HASH)]:
        with pytest.raises(ValueError):r.admit(context(),sha,h)


def test_new_window_qualification_needs_independent_seal():
    row=r.PLAN['rounds'][0]['rows'][0];source=evidence(row)
    assert r.qualify(row,source,{})=='UNKNOWN'
    independent=dict(council=row['council'],interval=[row['start'],row['end']],semantics=row['semantics'],complete=True,
        sealed_before_primary_reveal=True,criteria_verified=True,terminal_verified=True,evidence_sha256='b'*64,
        references=[],segments=1,explicit_zero=True)
    assert r.qualify(row,source,independent)=='COMPLETE'
    for k,v in [('sealed_before_primary_reveal',False),('criteria_verified',False),('semantics','PUBLICATION'),('explicit_zero',False)]:
        assert r.qualify(row,source,dict(independent,**{k:v}))=='UNKNOWN'
    assert r.qualify(row,source,dict(independent,references=['MISSING/26']))=='INCOMPLETE'
    assert r.qualify(row,dict(source,capped=True),independent)=='UNKNOWN'


def test_proposal_unregistered_credential_free_and_ci_included():
    root=Path(__file__).resolve().parents[1]
    assert not (root/r.WORKFLOW).exists()
    template=(root/'docs/design/stage4-r0-execution/workflow-proposal.yml').read_text()
    for forbidden in ('secrets.','environment:','schedule:','DATABASE_URL:','workflow_run:'):assert forbidden not in template
    assert '1930s' in template and 'timeout-minutes: 38' in template and 'persist-credentials: false' in template
    ci=(root/'.github/workflows/stage4-discovery-offline.yml').read_text()
    assert "'docs/design/stage4-r0-execution/**'" in ci
    assert 'tests/test_discovery_r0_proposal.py' in ci and 'tests/test_discovery_finite_acceptance.py' in ci


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
