"""Offline wiring tests. No source calls, database connections or credentials."""
from pathlib import Path
import json
import os
from unittest.mock import patch
import pytest
import yaml
from verification.discovery import r0_recovery_proposal as r
from verification.discovery import r0_identity_comparison as c
from tests.test_discovery_r0_recovery_proposal import evidence

ROOT=Path(__file__).resolve().parents[1]
DOC=ROOT/'docs/design/stage4-r0-execution/executable-proposals'


@pytest.fixture(autouse=True)
def credential_free(monkeypatch):
    monkeypatch.delenv('DATABASE_URL',raising=False)


def context(workflow):
    return dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',
        GITHUB_REPOSITORY='maxrose26/PropertyAIgent',GITHUB_EVENT_NAME='workflow_dispatch',
        GITHUB_REF='refs/heads/master',GITHUB_SHA='a'*40,GITHUB_WORKFLOW_SHA='a'*40,
        GITHUB_WORKFLOW_REF=f'maxrose26/PropertyAIgent/{workflow}@refs/heads/master',
        GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1')


def test_actual_recovery_workflow_mapping_and_authority_binding():
    assert r.PLAN_HASH=='5e4170c781314ba76583682e39ef0072ec932926617f3be169316873485ee9ae'
    workflow=yaml.load((DOC/'recovery-workflow.yml').read_text(),Loader=yaml.BaseLoader)
    assert set(workflow['on'])=={'workflow_dispatch'}
    job=workflow['jobs']['observation'];assert 'environment' not in job
    assert not (ROOT/r.WORKFLOW).exists()
    replacements={'${{ inputs.reviewed_sha }}':'a'*40,'${{ inputs.manifest_sha }}':r.PLAN_HASH,
                  '${{ inputs.authority }}':r.AUTHORITY,'${{ github.workflow_sha }}':'a'*40}
    for step in job['steps']:
        if 'env' not in step:continue
        env=dict(context(r.WORKFLOW),**{k:replacements[v] for k,v in step['env'].items()})
        r.admit(env,'a'*40,r.PLAN_HASH)
        for key,value in [('GITHUB_WORKFLOW_SHA',None),('GITHUB_WORKFLOW_SHA','b'*40),
                          ('GITHUB_RUN_NUMBER','2'),('GITHUB_RUN_ATTEMPT','2'),
                          ('RECOVERY_AUTHORITY',r.original.AUTHORITY),
                          ('GITHUB_WORKFLOW_REF',f'maxrose26/PropertyAIgent/{r.original.WORKFLOW}@refs/heads/master')]:
            bad=dict(env)
            if value is None:bad.pop(key)
            else:bad[key]=value
            with pytest.raises(ValueError):r.admit(bad,'a'*40,r.PLAN_HASH)
    text=(DOC/'recovery-workflow.yml').read_text()
    assert 'secrets.' not in text and '1930s' in text and 'timeout-minutes: 38' in text
    assert 'verification.discovery.r0_recovery_proposal' in text


def test_hard_supervisor_launches_new_entrypoint_and_exact_plan(tmp_path,monkeypatch):
    import psutil
    monkeypatch.setattr(r.original.os,'getpid',lambda:int(Path('/proc/self/stat').read_text().split()[0]))
    def absent(_):raise psutil.NoSuchProcess(123)
    monkeypatch.setattr(psutil,'Process',absent)
    commands=[]
    def runner(command,**kwargs):
        commands.append(command)
        assert command[2]=='verification.discovery.r0_recovery_proposal'
        assert json.loads(Path(command[4]).read_text())==r.PLAN
        assert set(kwargs['env'])=={'PATH','HOME','TMPDIR','PYTHONDONTWRITEBYTECODE','GITHUB_ACTIONS','RUNNER_ENVIRONMENT','PLAYWRIGHT_BROWSERS_PATH'}
        assert kwargs['start_new_session'] is True
        Path(command[6]).write_text(json.dumps(dict(completeness='INCOMPLETE',manifest_sha256=r.PLAN_HASH)))
        class Child:
            pid=123;returncode=0
            def poll(self):return 0
            def wait(self,timeout):return 0
        return Child()
    out=r.supervise(r.PLAN,tmp_path/'audit.json',runner=runner)
    assert len(commands)==1 and out['manifest_sha256']==r.PLAN_HASH
    assert out['outer_supervisor']['cleanup']=='CLOSED' and not out['outer_supervisor']['restarted']
    with pytest.raises(ValueError):r.original.supervise_round(r.PLAN,tmp_path/'other',worker_module='arbitrary.worker')


def test_new_worker_entrypoint_uses_recovery_not_historical_execute(tmp_path,monkeypatch):
    plan=tmp_path/'plan.json';plan.write_text(json.dumps(r.PLAN));out=tmp_path/'result.json'
    monkeypatch.setattr('resource.setrlimit',lambda *args: None)
    monkeypatch.setattr('sys.argv',['recovery','--worker',str(plan),'--output',str(out)])
    with patch.object(r.f,'read',side_effect=evidence) as reader, patch.object(r.f,'execute',side_effect=AssertionError('historical worker')):
        r.main()
    assert reader.call_count==28
    assert json.loads(out.read_text())['completeness']=='INCOMPLETE'


def test_comparison_proposal_is_protected_fixed_and_not_registered():
    w=yaml.load((DOC/'comparison-workflow.yml').read_text(),Loader=yaml.BaseLoader)
    assert set(w['on'])=={'workflow_dispatch'}
    assert w['jobs']['comparison']['environment']=='stage4-production-canary'
    assert not (ROOT/c.WORKFLOW).exists()
    text=(DOC/'comparison-workflow.yml').read_text()
    assert text.count('${{ secrets.DATABASE_URL }}')==1 and 'timeout --signal=TERM --kill-after=5s 60s' in text
    assert 'admission' not in text and 'playwright' not in text
    env=context(c.WORKFLOW);c.admit(env,'a'*40,c.MANIFEST_SHA,c.AUTHORITY)
    for key,value in [('GITHUB_RUN_ATTEMPT','2'),('GITHUB_RUN_NUMBER','2'),('GITHUB_WORKFLOW_SHA','b'*40),('GITHUB_WORKFLOW_REF','old')]:
        with pytest.raises(ValueError):c.admit(dict(env,**{key:value}),'a'*40,c.MANIFEST_SHA,c.AUTHORITY)
    with pytest.raises(ValueError):c.admit(env,'a'*40,'0'*64,c.AUTHORITY)
    sql,params=c.statement()
    assert len(params)==160 and 'LIMIT 2' in sql and 'a.council_code = r.council_code AND a.reference = r.reference' in sql
    assert len(c.identities())==80 and all(x['reference'] not in sql for x in c.identities())


def fake_connection(*,readonly='on',failed=False):
    from datetime import datetime,timezone
    class Result:
        def scalar_one(self):return readonly
        def mappings(self):
            if failed:raise RuntimeError('secret failure payload')
            stamp=datetime(2026,10,15,tzinfo=timezone.utc)
            return [dict(snapshot_timestamp=stamp,**row,matches=[] if n>1 else [dict(id=n+j+1,**row) for j in range(n+1)],matching_rows_up_to_two=0 if n>1 else n+1) for n,row in enumerate(c.identities())]
    class Connection:
        statements=[]
        def exec_driver_sql(self,sql):self.statements.append(sql);return Result()
        def execute(self,sql,params):self.statements.append(str(sql));return Result()
    return Connection()


def test_fixed_comparison_absent_unique_duplicate_and_rollback():
    conn=fake_connection();out=c.query(conn)
    assert conn.statements[0]=='BEGIN READ ONLY' and conn.statements[-1]=='ROLLBACK'
    assert "SET LOCAL statement_timeout = '15s'" in conn.statements
    assert "SET LOCAL lock_timeout = '2s'" in conn.statements
    assert len(out['comparison'])==80 and {x['outcome'] for x in out['comparison']}=={'ABSENT','ONE_MATCH','DUPLICATE_DETECTED'}
    assert out['production_writes']==0


@pytest.mark.parametrize('options',[{'readonly':'off'},{'failed':True}])
def test_read_failure_preserves_rollback(options):
    conn=fake_connection(**options)
    with pytest.raises(Exception):c.query(conn)
    assert conn.statements[-1]=='ROLLBACK'


def test_wrong_route_rejected_before_engine_and_no_secret_output():
    with patch('sqlalchemy.create_engine',side_effect=AssertionError('engine must not construct')) as engine:
        out=c.run('postgresql://secret:password@wrong.invalid/postgres')
    engine.assert_not_called()
    assert out['route_validation']['reason_code']=='HOST_MISMATCH'
    assert 'password' not in str(out) and 'wrong.invalid' not in str(out)
