"""Synthetic/disposable proof only; no source or protected credential access."""
import json,time
from dataclasses import replace
from unittest.mock import patch
from pathlib import Path
import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.db.models import Application
from verification.discovery import bolton53_admission as a
from verification.discovery import bolton53_admission_supervisor as outer
from tests.test_discovery_admission import engine


def synthetic(row):
    from verification.direct_reference.fixtures import Session as SourceSession,summary
    from verification.discovery.material_qualification import project_idox,idox_worker
    closed=next(q for q in a.source.targets() if q['reference']==row['reference'])
    transport=SourceSession(summary(row['reference'],status='Deposited',omit=('Decision','Decision Issued Date')))
    with patch('verification.direct_reference.refresh.requests_session',lambda:transport),patch('verification.direct_reference.batch_supervisor.resource_limits',lambda:None):
        raw=idox_worker(closed)
    raw.update(process_cleanup='CLOSED',live_owned_survivors=0,peak_owned_rss=100,owned_processes_seen=1,supervisor_seconds=1,supervisor_limit_hit=False)
    return project_idox(closed,raw)


def exercise(engine):
    row=next(a.rows());phases=[]
    out=a.record(engine,row,retrieve=synthetic,journal=phases.append)
    assert out['identity']=='CREATED_PENDING' and out['facts']=='INITIAL_FACTS_VERIFIED'
    assert out['admission_mode']=='COMPLETE_WINDOW' and out['transaction']=='COMMIT_READBACK_CONFIRMED'
    assert out['readback']['status']=='Deposited' and out['readback']['site_id'] is None
    assert out['readback']['field_verification']['decision']['state']=='NOT_PRESENT'
    assert out['readback']['field_verification']['decision']['verified_at'] is None
    assert 'SOURCE_CLOSED' in phases and 'FACTS_COMMIT_READBACK_CONFIRMED' in phases
    with Session(engine) as s:
        app=s.get(Application,out['application_id']);app.status='CHANGED';s.commit()
    again=a.record(engine,row,retrieve=lambda _:pytest.fail('must preserve existing'))
    assert again['identity']=='ALREADY_KNOWN' and again['facts']=='EXISTING_NOT_WRITTEN'
    with Session(engine) as s:assert s.get(Application,out['application_id']).status=='CHANGED'


def test_actual_primary_shared_b2(engine):exercise(engine)


def test_all53_original_complete_window_not_qualification_trigger():
    rows=list(a.rows());assert len(rows)==53
    assert all(a.envelope(r).window.outcome.value=='COMPLETE' for r in rows)
    assert all(a.envelope(r).window.run_id=='38731487848' for r in rows)
    assert all('01842/26'!=r['reference'] for r in rows)


def test_source_failure_keeps_committed_pending_identity(engine):
    row=next(a.rows())
    out=a.record(engine,row,retrieve=lambda _:(_ for _ in ()).throw(RuntimeError('secret')))
    assert out['identity']=='CREATED_PENDING' and out['facts']=='WITHHELD_SOURCE_ACCOUNTING_UNKNOWN' and out['stop']
    with Session(engine) as s:
        app=s.get(Application,out['application_id']);assert app.unit_confirmation_status=='discovery_pending' and app.status is None
    assert 'secret' not in str(out)


def test_lost_commit_and_failed_readback_never_next_record(engine):
    from app.pipeline.discovery_admission import UncertainDiscoveryCommit
    row=next(a.rows())
    with patch.object(a,'admit_identity',side_effect=UncertainDiscoveryCommit('secret')):
        out=a.record(engine,row,retrieve=lambda _:pytest.fail('source'))
    assert out['identity']=='UNKNOWN_COMMIT' and out['transaction']=='UNCERTAIN_STOP_NO_RETRY'
    calls=[]
    with patch.object(a,'rows',lambda:iter([row,row])),patch.object(a,'record',return_value=out):
        result=a.run(engine_factory=lambda:calls.append(1) or engine,checkpoint=lambda _:None,journal=lambda *_:None)
    assert len(calls)==1 and result['stop']


def test_b2_readback_uncertainty_preserves_stop(engine):
    with patch.object(a,'readback',side_effect=RuntimeError('secret')):
        out=a.record(engine,next(a.rows()),retrieve=synthetic)
    assert out['facts']=='UNCERTAIN_COMMIT_OR_READBACK' and out['stop']


@pytest.mark.parametrize('boundary',['checkpoint','cleanup','deadline'])
def test_boundary_failure_prevents_next_record(engine,boundary):
    rows=list(a.rows())[:2];calls=[]
    def factory():calls.append(1);return engine
    def checkpoint(_):
        if boundary=='checkpoint':raise ValueError('checkpoint failed')
    class Clock:
        n=0
        def __call__(self):self.n+=1;return 0 if self.n<4 else 181
    with patch.object(a,'rows',lambda:iter(rows)),patch.object(a,'record',return_value={'transaction':'COMMIT_READBACK_CONFIRMED'}):
        if boundary=='cleanup':
            with patch.object(engine,'dispose',side_effect=RuntimeError('cleanup')):result=a.run(engine_factory=factory,checkpoint=checkpoint,journal=lambda *_:None)
        else:result=a.run(engine_factory=factory,checkpoint=checkpoint,journal=lambda *_:None,clock=Clock() if boundary=='deadline' else lambda:0)
    assert len(calls)==1 and result['stop']


def test_phase_deadline_and_hash_checkpoint(tmp_path):
    j=outer.Journal(tmp_path);j(0,'RECORD_STARTED');j(0,'SOURCE_STARTED')
    assert outer.phase_bound(tmp_path,time.monotonic()) is None
    assert outer.phase_bound(tmp_path,time.monotonic()+56)=='PHASE_DEADLINE'
    assert outer.phase_bound(tmp_path,time.monotonic()+181)=='RECORD_DEADLINE'
    assert a.LIMITS['seconds']==53*180+120 and a.LIMITS['source_seconds']==53*55


def test_supervisor_kills_real_hanging_owned_child(tmp_path):
    import subprocess,sys
    captured={}
    def launch(command,**kwargs):
        captured.update(command=command,env=kwargs['env'])
        return subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)'],**kwargs)
    import os
    if int(Path('/proc/self/stat').read_text().split()[0])!=os.getpid():
        with pytest.raises(ValueError,match='PROCESS_NAMESPACE_MISMATCH'):
            outer.supervise(tmp_path/'audit',credential='DISPOSABLE_NOT_A_URL',runner=launch,deadline=.1)
        assert not captured
        return  # hosted exact-head CI exercises the real owned-process timeout
    out=outer.supervise(tmp_path/'audit',credential='DISPOSABLE_NOT_A_URL',runner=launch,deadline=.1)
    assert out['stop_reason']=='AGGREGATE_DEADLINE' and out['cleanup']=='CLOSED' and out['live_owned_survivors']==0
    assert out['transaction']=='UNKNOWN_COMMIT_OR_READBACK_NO_RETRY' and out['retry'] is False
    assert 'DISPOSABLE_NOT_A_URL' not in json.dumps(out)
    assert captured['command'][2]=='verification.discovery.bolton53_admission_supervisor'
    assert set(captured['env'])=={'PATH','HOME','TMPDIR','LANG','PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE','GITHUB_ACTIONS','RUNNER_ENVIRONMENT','BOLTON_ADMISSION_PRIVATE_CHILD','BOLTON_ADMISSION_DATABASE_URL'}


@pytest.mark.parametrize('failure',['AMBIGUOUS_SOURCE_RESULT','INVALID_ARTIFACT','SCOPE_ESCAPE','PARSER_FAILURE','PARTIAL_RETRIEVAL'])
def test_hard_fresh_source_failure_stops_next_identity(engine,failure):
    calls=[];row=next(a.rows())
    def reader(r):
        calls.append(r);resource=synthetic(r);return dict(resource,failure=failure,observation=None)
    with patch.object(a,'rows',lambda:iter([row,row])):
        result=a.run(engine_factory=lambda:engine,reader=reader,checkpoint=lambda _:None,journal=lambda *_:None)
    assert len(calls)==1 and len(result['results'])==1 and result['stop']
    assert result['results'][0]['identity']=='CREATED_PENDING'


def test_supervisor_rechecks_deadline_after_child_exits_between_polls(tmp_path):
    from unittest.mock import MagicMock
    from tests.test_discovery_r0_registered_scopes import proc_namespace
    import psutil
    def runner(command,**kw):
        root=tmp_path/'audit';(root/'worker-result.json').write_text('{"results":[],"stop":null}')
        child=MagicMock(pid=999999,returncode=0);child.poll.return_value=0;child.wait.return_value=0;return child
    with proc_namespace(),patch.object(outer.time,'monotonic',side_effect=[0,181,181,181]),patch.object(psutil,'Process',return_value=MagicMock()),patch.object(psutil,'wait_procs',return_value=([],[])):
        out=outer.supervise(tmp_path/'audit',credential='DISPOSABLE',runner=runner,deadline=180)
    assert out['stop_reason']=='AGGREGATE_DEADLINE' and 'result' not in out
