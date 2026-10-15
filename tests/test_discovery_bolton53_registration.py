"""SYNTHETIC offline/disposable controls; no live source or production proof."""
import json
from pathlib import Path
from unittest.mock import patch,MagicMock
import pytest
import yaml
from verification.discovery import r0_bolton53_qualification as b
from verification.discovery import r0_registered_scopes as s
from verification.discovery import r0_fixed80_qualification as q
from verification.direct_reference.fixtures import Session,summary


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    import os
    for key in list(os.environ):
        if 'DATABASE' in key or key.startswith(('SUPABASE_','OPENAI_','ANTHROPIC_')):monkeypatch.delenv(key,raising=False)


def test_frozen53_origin_exclusions_and_exact_capacity():
    rows=b.targets();old=q.targets()
    assert [r['reference'] for r in rows]==[r['reference'] for i,r in enumerate(old[:54]) if i!=42]
    assert len(set(b.case_definitions()))==53 and not set(b.case_definitions())&set(q.case_definitions())
    assert b.LIMITS['seconds']==53*55 and b.LIMITS['requests']==53*2
    assert b.LIMITS['bytes']==53*2_000_000
    assert 2*53*65536+s.AUDIT_RESERVE<=b.LIMITS['output_bytes']
    profile=s.PROFILES['bolton53'];w=yaml.load(Path(profile['workflow']).read_text(),Loader=yaml.BaseLoader)
    assert int(w['jobs']['source']['timeout-minutes'])*60==3360
    assert profile['setup_seconds']==280 and profile['seconds']==2915
    step=next(x for x in w['jobs']['source']['steps'] if 'timeout --signal' in x.get('run',''))
    assert '--kill-after=10s 2945s' in step['run']
    assert 3360-280-2945-10>=120 # reserve survives even the shell fallback
    with patch('verification.discovery.material_qualification.idox_worker') as worker:
        for index in [-1,53,True]:
            with pytest.raises(ValueError):b.worker(index)
        worker.assert_not_called()
    with pytest.raises(ValueError):b.read(0,dict(rows[0],reference='OTHER'))


def test_actual_owned_supervisor_to_bolton_worker_parser_projector(tmp_path,monkeypatch):
    from verification.direct_reference import instrumented_probe as probe
    import psutil,os
    row=b.targets()[0];calls=[]
    monkeypatch.setenv('GITHUB_ACTIONS','true');monkeypatch.setenv('RUNNER_ENVIRONMENT','github-hosted')
    def popen(argv,**kw):
        calls.append(argv)
        assert argv[1:6]==['-m','verification.discovery.r0_bolton53_qualification','--worker','--case',row['case']]
        assert set(kw['env'])=={'PATH','HOME','TMPDIR','LANG','PYTHONNOUSERSITE','PYTHONDONTWRITEBYTECODE','PLAYWRIGHT_BROWSERS_PATH'}
        body=summary(row['reference'],status='Deposited',omit=('Decision','Decision Issued Date'))
        transport=Session(body)
        with patch('verification.direct_reference.refresh.requests_session',lambda:transport),patch('verification.direct_reference.batch_supervisor.resource_limits',lambda:None):
            result=b.worker(0)
        assert transport.closed
        Path(argv[argv.index('--output')+1]).write_text(json.dumps(result))
        child=MagicMock(pid=999999,returncode=0);child.poll.return_value=0;child.wait.return_value=0;return child
    original_read=Path.read_text
    def namespace(path,*a,**kw):return str(os.getpid())+' synthetic' if str(path)=='/proc/self/stat' else original_read(path,*a,**kw)
    with patch.object(Path,'read_text',namespace),patch.object(probe.subprocess,'Popen',popen),patch.object(psutil,'Process',return_value=MagicMock()),patch.object(psutil,'wait_procs',return_value=([],[])):
        raw=b.read(0,row)
    projected=q.project(row,raw);obs=projected['observation']
    assert len(calls)==1 and projected['failure'] is None
    assert obs.b2_eligible and obs.verification_scope=='INITIAL_STATUS_ONLY'
    assert obs.fields['Status']=='Deposited' and obs.semantic_state=='UNKNOWN_UNMAPPED'
    assert obs.field_states['decision']==obs.field_states['decision_date']=='NOT_PRESENT'
    assert projected['audit']['cleanup_state']=='CLOSED'


@pytest.mark.parametrize('change',[
 {'failure':'PARSER_FAILURE'}, {'reference':'WRONG'}, {'requests':3},
 {'process_cleanup':'UNKNOWN'}, {'live_owned_survivors':1}, {'destination':'https://wrong.invalid/'},
])
def test_bolton53_unsafe_result_stops_before_second_record(change):
    from tests.test_discovery_fixed80_qualification import source
    calls=[]
    def reader(i,row):calls.append(i);return dict(source(row,False),**change)
    out=b.qualify(reader=reader,checkpoint=lambda _:None)
    assert calls==[0] and out['attempted']==1 and len(out['not_attempted'])==52 and out['stop_reason']
    assert out['manifest_sha256']==b.MANIFEST_SHA and not out['admission_authorised']


def test_bolton53_checkpoint_failure_prevents_next_call():
    from tests.test_discovery_fixed80_qualification import source
    calls=[]
    def reader(i,row):calls.append(i);return source(row,False)
    def fail(_):raise OSError('SYNTHETIC')
    out=b.qualify(reader=reader,checkpoint=fail)
    assert calls==[0] and out['stop_reason']=='CHECKPOINT_FAILURE_NO_NEXT_CALL'
