"""Offline intake bounds and inactive CLI; no source, DB or credential access."""
from datetime import datetime, timezone
import pytest
from app.ingestion.daily_intake import current_windows, inactive_main
from app.ingestion.ledger import Denied


def test_current_intake_does_not_wait_for_historical_recovery():
    rows=current_windows(datetime(2026,10,29,tzinfo=timezone.utc),['bolton','manchester'])
    assert rows==[dict(council='bolton',semantics='RECEIVED',start='2026-10-22',end='2026-10-28'),
                  dict(council='manchester',semantics='VALIDATED',start='2026-10-22',end='2026-10-28')]


def test_local_completed_day_not_utc_day():
    row=current_windows(datetime(2026,7,1,23,30,tzinfo=timezone.utc),['bolton'],overlap_days=1)[0]
    assert row['start']==row['end']=='2026-07-01'


@pytest.mark.parametrize('councils,days',[(['trafford'],7),(['bolton','bolton'],7),([],7),(['bolton'],29),(['bolton'],True),
                                            (['bolton','bury','oldham','tameside'],7)])
def test_unsupported_capacity_and_scopes_refuse(councils,days):
    with pytest.raises(Denied):current_windows(datetime.now(timezone.utc),councils,overlap_days=days)


def test_default_command_cannot_fall_back_to_legacy(capsys):
    assert inactive_main()==2
    import json
    result=json.loads(capsys.readouterr().out)
    assert result['database_connections']==result['source_requests']==result['application_writes']==0
    assert result['reason']=='EXPLICIT_INTAKE_PERIOD_REQUIRED'


def test_capture_bound_worker_is_an_explicit_reversible_extension():
    from verification.ingestion_storage import screening_v3_worker_sql as v3
    historical=v3.derive()
    current=v3.capture_bound_text(historical)
    for old,new in reversed(v3.capture_bound_sites()):
        assert current.count(new)==1
        current=current.replace(new,old)
    assert current==historical


def test_capture_bound_revision_reuses_existing_observation_contract():
    from app.ingestion.observation_screening import observation_revision
    from app.ingestion.ledger import digest
    assessment='a'*64
    first,second=observation_revision(assessment,'b'*64),observation_revision(assessment,'c'*64)
    assert first!=second
    assert first==digest(dict(assessment_revision=assessment,observation_sha256='b'*64))

def test_unaccounted_supervised_source_is_unknown_and_blocks_next_scope():
    # Zero accounted calls never proves zero physical requests after a
    # source worker starts. Only a validated complete audit resolves UNKNOWN.
    from verification.ingestion_storage.intake_budget import IntakeRun
    run=IntakeRun(clock=lambda:0)
    run.before_scope('idox')
    run.begin_source()
    usage=run.totals()
    assert usage['requests'] is None and usage['requests_status']=='UNKNOWN'
    assert usage['requests_accounted']==0
    with pytest.raises(Denied,match='SOURCE_ACCOUNTING_UNKNOWN_NO_CONTINUATION'):
        run.before_scope('idox')
    with pytest.raises(Denied,match='SOURCE_ACCOUNTING'):
        run.source(dict(requests=1))
    assert run.totals()['requests'] is None
    run.source(dict(requests=2,source_bytes=512,source_seconds=1,supervised_seconds=2))
    assert run.totals()['requests']==2 and run.totals()['requests_status']=='COMPLETE'
    run.before_scope('idox')

@pytest.mark.parametrize('poll_changes',[False,True])
def test_source_supervision_keeps_database_deadline_on_main_thread(tmp_path,monkeypatch,poll_changes):
    """No network/SQL. A supervised source must outlive a bounded main-thread poll."""
    import json,time,threading
    from contextlib import contextmanager
    from types import SimpleNamespace
    from verification.ingestion_storage.daily_intake_runtime import Runtime
    from verification.ingestion_storage.operational_controller import DatabaseBudget
    from verification.ingestion_storage.intake_budget import IntakeRun

    runtime=object.__new__(Runtime)
    runtime.root=tmp_path/'output';runtime.root.mkdir()
    sources=tmp_path/'source-fixtures';sources.mkdir()
    runtime.args=SimpleNamespace(period='safe-poll-fixture',disposable_sources=str(sources))
    runtime.test=True;runtime.policy={};runtime.run=IntakeRun()
    runtime.memory=None;runtime.events=[]
    budget=DatabaseBudget();poll_threads=[];supervisor_threads=[]

    def synthetic_supervisor(command,*,check,root,**kw):
        supervisor_threads.append(threading.current_thread())
        root.mkdir()
        deadline=time.monotonic()+2.4
        try:
            while time.monotonic()<deadline:
                check()
                time.sleep(.025)
            (runtime.root/'tameside-source.json').write_text(json.dumps(
                dict(resource=dict(requests_attempted=4,received_bytes=30,elapsed_seconds=2))))
        except Denied:
            pass
        return dict(cleanup='CLOSED',exit_code=0,limit_hit=None,elapsed_seconds=2)

    monkeypatch.setattr('verification.ingestion_storage.daily_intake_runtime.supervise',synthetic_supervisor)
    @contextmanager
    def connection(**kwargs):
        yield None,budget
    runtime.connection=connection

    def read_policy(connection):
        poll_threads.append(threading.current_thread())
        budget.guarded(None,lambda:None)  # signal deadline must run on main thread
        if poll_changes and len(poll_threads)==2:
            raise Denied('INTAKE_SHARED_STOP_CHANGED')
    runtime.policy_read=read_policy
    if poll_changes:
        with pytest.raises(Denied,match='SOURCE_STOP_OR_ACCESS_CHANGED'):
            runtime.collect(dict(council='tameside'))
        usage=runtime.run.totals()
        assert usage['requests'] is None and usage['requests_status']=='UNKNOWN'
        with pytest.raises(Denied,match='UNKNOWN_NO_CONTINUATION'):
            runtime.run.before_scope('arcus')
    else:
        source,outer=runtime.collect(dict(council='tameside'))
        assert outer['cleanup']=='CLOSED' and source['resource']['requests_attempted']==4
        assert runtime.run.totals()['requests']==4
        assert runtime.run.totals()['requests_status']=='COMPLETE'
    assert len(poll_threads)>=2 and all(t is threading.main_thread() for t in poll_threads)
    assert len(supervisor_threads)==1 and supervisor_threads[0] is not threading.main_thread()
