"""Specification 019: synthetic database/portal and real POSIX process tests.

No production connection, portal navigation, or paid evaluation is permitted.
"""
import datetime as dt
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select, create_engine, text, inspect
from sqlalchemy.exc import IntegrityError

from app.db.models import Application, ParentLookupWork, ScrapeRun, Base
from app.pipeline.lookup_outcome import LookupResult, Outcome, strict_lookup, reference_key
from app.pipeline.parent_lookup import run_parent_stage, populate, due_query, reserve, finish
from app.pipeline.discovery_owner import DiscoveryOwner, terminal_evidence, reconcile_owners, process_identity, SERVICE_ID
from app.pipeline.acquisition_health import AcquisitionHealth

ROOT = Path(__file__).resolve().parents[1]
NOW = dt.datetime(2026, 9, 28, tzinfo=dt.timezone.utc)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    import requests
    def blocked(*a, **k): raise AssertionError('network is forbidden in P0-A tests')
    monkeypatch.setattr(requests.Session, 'request', blocked)
    for name in ('RENDER', 'RENDER_SERVICE_ID', 'RENDER_INSTANCE_ID', 'PROPERTYAIGENT_OWNER', 'PROPERTYAIGENT_RUN_ID'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr('app.diagnostics.memory.cgroup_memory', lambda: None)


def council():
    from app.config import CouncilConfig
    return CouncilConfig('testcouncil', 'Test', 'https://example.invalid', 'received', 'idox', None, 10, None, None, request_delay_seconds=0)


def child(session, reference='CHILD/1', parent='OUT/100'):
    a = Application(council_code='testcouncil', reference=reference,
        proposal=f'Reserved matters pursuant to outline planning permission {parent}')
    session.add(a); session.commit()
    return a


def found(ref):
    from app.scrapers.idox_portal import ScrapedApplication
    return LookupResult(Outcome.FOUND, ScrapedApplication(ref, {'Proposal': '50 dwellings'},
        'https://example.invalid/summary', 'https://example.invalid/further', ref, 50,
        'full_application', 'Confirmed', True))


def run(session, lookup, **kwargs):
    return run_parent_stage(session, None, council(), lookup=lookup, sleep=lambda _: None, now=lambda: NOW, **kwargs)


def test_dedup_and_idempotent_sharing(session, capsys):
    a, b = child(session), child(session, 'CHILD/2', 'out/100')
    calls = []
    run(session, lambda r: (calls.append(r), found(r))[1])
    assert len(calls) == 1
    assert a.estimated_unit_count == b.estimated_unit_count == 50
    assert a.unit_confirmation_status == b.unit_confirmation_status == 'confirmed_qualifying'
    run(session, lambda r: pytest.fail('resolved reference requested again'))
    c = child(session, 'CHILD/3')
    run(session, lambda r: pytest.fail('new citation must reuse durable success'))
    assert c.estimated_unit_count == 50
    assert session.query(ParentLookupWork).count() == 1
    assert 'duplicate_requests_suppressed' in capsys.readouterr().out


@pytest.mark.parametrize('outcome', [Outcome.NOT_FOUND, Outcome.AMBIGUOUS_IDENTITY])
def test_negative_cooldown_not_permanent(session, outcome):
    child(session)
    run(session, lambda _: LookupResult(outcome))
    w = session.scalar(select(ParentLookupWork))
    assert w.total_attempts == 1
    assert (w.next_eligible_at.replace(tzinfo=dt.timezone.utc)-NOW).days == 7
    run(session, lambda _: pytest.fail('cooldown bypassed'))
    w.next_eligible_at = NOW-dt.timedelta(seconds=1); session.commit()
    run(session, found)
    assert w.last_outcome == 'found'


def test_changed_citation_justifies_bounded_early_retry(session):
    a = child(session)
    run(session, lambda _: LookupResult(Outcome.NOT_FOUND))
    a.proposal += ' amended evidence'; session.commit()
    run(session, found)
    assert session.scalar(select(ParentLookupWork)).total_attempts == 2


def test_retry_behind_first_attempts_and_max_two(session):
    child(session); child(session, 'CHILD/2', 'OUT/200')
    calls = []
    run(session, lambda r: (calls.append(r), LookupResult(Outcome.TRANSIENT_FAILURE))[1])
    assert calls == ['OUT/100', 'OUT/200', 'OUT/100', 'OUT/200']
    assert all(w.total_attempts == 2 for w in session.scalars(select(ParentLookupWork)))
    run(session, lambda _: pytest.fail('persistent transient cooldown bypassed'))


def test_retry_after_beyond_budget_is_deferred(session):
    child(session)
    calls = []
    run(session, lambda r: (calls.append(r), LookupResult(Outcome.TRANSIENT_FAILURE, retry_after_seconds=100000))[1])
    assert len(calls) == 1
    w = session.scalar(select(ParentLookupWork))
    assert (w.next_eligible_at.replace(tzinfo=dt.timezone.utc)-NOW).total_seconds() == 100000


def test_items_continue_older_work_before_retries(session, monkeypatch):
    for n in range(5): child(session, f'CHILD/{n}', f'OUT/{n}')
    monkeypatch.setenv('PROPERTYAIGENT_DISCOVERY_PARENT_ITEMS', '2')
    seen = []
    for _ in range(3):
        run(session, lambda r: (seen.append(r), found(r))[1])
    assert seen == [f'OUT/{n}' for n in range(5)]


def test_reservation_crash_rotates_preserving_attempts(session, monkeypatch):
    monkeypatch.setattr("app.pipeline.discovery_owner.SCHEDULED_INSTANCE_PATTERN", "old|new")
    child(session); child(session, 'CHILD/2', 'OUT/200')
    from app.pipeline.site_linking import extract_parent_reference
    populate(session, 'testcouncil', extract_parent_reference)
    works = list(session.scalars(due_query('testcouncil', NOW+dt.timedelta(days=10))))
    old = {'version':1, 'invocation':'old', 'service':SERVICE_ID, 'instance':'old', 'scheduler_contract':'render-scheduled-v1'}
    record = ScrapeRun(council_code='testcouncil', status='running', progress=json.dumps({'owner':old}))
    session.add(record); session.commit()
    reserve(session, works[0], record.id, NOW+dt.timedelta(days=10))
    reconcile_owners(session, SimpleNamespace(identity={**old, 'invocation':'new','instance':'new'}))
    assert record.status == 'failed'
    assert works[0].total_attempts == 1
    ordered = list(session.scalars(due_query('testcouncil', NOW+dt.timedelta(days=20))))
    assert ordered[0].id == works[1].id
    assert json.loads(record.progress)['recovery']['finished_at_is_reconciliation'] is True


def test_conditional_owner_transition_and_unique_key(session):
    child(session)
    from app.pipeline.site_linking import extract_parent_reference
    populate(session, 'testcouncil', extract_parent_reference)
    w = session.scalar(select(ParentLookupWork))
    reserve(session, w, None, NOW)
    with pytest.raises(RuntimeError, match='conflict'): reserve(session, w, None, NOW)
    session.add(ParentLookupWork(council_code='testcouncil', reference_key=w.reference_key, raw_reference=w.raw_reference))
    with pytest.raises(IntegrityError): session.commit()
    session.rollback()


@pytest.mark.parametrize('actual', ['OUT-100', '100', 'OUT/100/FUL', None])
def test_strict_identity_never_fuzzy(actual):
    assert strict_lookup(lambda: SimpleNamespace(reference=actual), 'OUT/100').outcome == Outcome.AMBIGUOUS_IDENTITY


def test_case_whitespace_only():
    assert strict_lookup(lambda: SimpleNamespace(reference=' out/100 '), 'OUT/100').outcome == Outcome.FOUND
    assert reference_key('OUT-100') != reference_key('OUT/100')


def test_cooperative_deadline_escapes_broad_exception_retry():
    from app.pipeline.lookup_outcome import bounded_sleep
    def retry_loop():
        while True:
            try: bounded_sleep(.1)
            except Exception: continue
    start=time.monotonic()
    assert strict_lookup(retry_loop, 'OUT/100', seconds=.05).reason == 'logical_deadline'
    assert time.monotonic()-start < 1
    assert signal.getitimer(signal.ITIMER_REAL)[0] == 0


def test_retry_after_survives_logical_deadline():
    from app.pipeline.lookup_outcome import remember_retry_after, bounded_sleep
    def wait():
        remember_retry_after(100)
        bounded_sleep(2)
    result = strict_lookup(wait, 'OUT/100', seconds=.03)
    assert result.outcome == Outcome.TRANSIENT_FAILURE
    assert result.retry_after_seconds > 99


def test_soft_memory_defers_without_false_process_failure(session, monkeypatch):
    child(session)
    monkeypatch.setattr('app.diagnostics.memory.cgroup_memory', lambda: (75,100))
    health=AcquisitionHealth()
    run(session, lambda _: pytest.fail('memory stop ignored'), health=health)
    assert health.classify() == 'partial'
    assert health.parents_deferred == 1


def test_legacy_running_does_not_block_or_relabel(session):
    row=ScrapeRun(council_code='testcouncil', status='running')
    session.add(row); session.commit()
    reconcile_owners(session, SimpleNamespace(identity={'invocation':'new'}))
    assert row.status == 'running' and row.finished_at is None


def test_foreign_owner_cannot_be_reclaimed_by_age():
    old=dict(version=1, invocation='old', service='foreign', instance='old', boot='old')
    with pytest.raises(RuntimeError): terminal_evidence(old, dict(invocation='new', service=SERVICE_ID, instance='new', boot='new'))


def test_process_access_error_is_not_absence(monkeypatch):
    import psutil
    monkeypatch.setattr(psutil, 'Process', lambda _: (_ for _ in ()).throw(psutil.AccessDenied()))
    with pytest.raises(psutil.AccessDenied): process_identity(123)


def test_actual_inherited_lock_and_cleanup(tmp_path):
    from scripts.run_daily_councils import _run_council_subprocess
    path=str(tmp_path/'owner.lock')
    with DiscoveryOwner(path) as owner:
        lines=[]
        script="from app.pipeline.discovery_owner import verify_child; print(verify_child()['invocation'], flush=True)"
        assert _run_council_subprocess([sys.executable,'-c',script], cwd=ROOT, timeout_seconds=5,
            on_line=lines.append, owner=owner, run_id=1) == 0
        assert owner.identity['invocation'] in lines
        with pytest.raises(RuntimeError):
            with DiscoveryOwner(path): pass
    with DiscoveryOwner(path): pass


def test_actual_supervisor_death_surviving_child_holds_lock(tmp_path, record_property):
    path=str(tmp_path/'owner.lock'); ready=tmp_path/'child.pid'
    script='''import subprocess,sys,time
from app.pipeline.discovery_owner import DiscoveryOwner
with DiscoveryOwner(sys.argv[1]) as owner:
 p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)'],pass_fds=(owner.fd,),start_new_session=True)
 open(sys.argv[2],'w').write(str(p.pid))
 time.sleep(20)
'''
    supervisor=subprocess.Popen([sys.executable,'-c',script,path,str(ready)],cwd=ROOT)
    pid=None
    try:
        end=time.monotonic()+5
        while not ready.exists() and time.monotonic()<end: time.sleep(.02)
        assert ready.exists()
        pid=int(ready.read_text())
        supervisor.kill(); supervisor.wait(timeout=3)
        # The retained lock itself is the cross-process liveness evidence.
        with pytest.raises(RuntimeError, match='still active'):
            with DiscoveryOwner(path): pass
        termination_started = time.monotonic()
        os.killpg(pid,signal.SIGKILL)
        end=time.monotonic()+3
        while True:
            try:
                with DiscoveryOwner(path): pass
                record_property('confirmed_termination_to_successor_seconds', time.monotonic()-termination_started)
                break
            except RuntimeError:
                if time.monotonic() >= end: raise
                time.sleep(.02)
    finally:
        if supervisor.poll() is None: supervisor.kill(); supervisor.wait()
        if pid:
            try: os.killpg(pid,signal.SIGKILL)
            except ProcessLookupError: pass


def test_actual_callback_failure_cleans_child_and_descendant(tmp_path):
    from scripts.run_daily_councils import _run_council_subprocess
    pidfile=tmp_path/'pid'
    script="import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)']); open(sys.argv[1],'w').write(str(p.pid)); print('ready',flush=True);time.sleep(20)"
    def callback(line):
        if line == 'ready': raise ValueError('synthetic DB failure')
    with pytest.raises(ValueError):
        _run_council_subprocess([sys.executable,'-u','-c',script,str(pidfile)],cwd=ROOT,timeout_seconds=5,on_line=callback)
    pid=int(pidfile.read_text())
    end=time.monotonic()+3
    while process_identity(pid) is not None and time.monotonic()<end: time.sleep(.02)
    assert process_identity(pid) is None


def test_actual_hard_memory_containment(monkeypatch):
    from scripts.run_daily_councils import _run_council_subprocess, MemoryContainment
    monkeypatch.setattr('app.diagnostics.memory.cgroup_memory',lambda:(81,100))
    start=time.monotonic()
    with pytest.raises(MemoryContainment):
        _run_council_subprocess([sys.executable,'-c','import time;time.sleep(20)'],cwd=ROOT,timeout_seconds=10)
    assert time.monotonic()-start < 6


def test_migration_additive_idempotent_legacy_compatible(tmp_path):
    from app.db.session import migrate_schema, verify_schema
    engine=create_engine('sqlite:///'+str(tmp_path/'migration.db'))
    Base.metadata.create_all(engine)
    with engine.begin() as c:
        c.execute(text('DROP TABLE parent_lookup_work'))
        c.execute(text('ALTER TABLE scrape_runs DROP COLUMN progress'))
    before={t:{c['name'] for c in inspect(engine).get_columns(t)} for t in inspect(engine).get_table_names()}
    missing=verify_schema(engine)
    assert missing == (['parent_lookup_work'], [('scrape_runs','progress')])
    assert migrate_schema(engine) == missing
    assert migrate_schema(engine) == ([],[])
    after={t:{c['name'] for c in inspect(engine).get_columns(t)} for t in before}
    for t in before: assert after[t] == before[t] | ({'progress'} if t=='scrape_runs' else set())
    assert inspect(engine).get_unique_constraints('parent_lookup_work')
    assert inspect(engine).get_indexes('parent_lookup_work')
    engine.dispose()

class FakePage:
    def __init__(self, context): self.context, self.closed = context, False
    def close(self): self.closed = True
    def content(self):
        if self.closed: raise RuntimeError('Target page has been closed')
        return 'synthetic offline document listing'

class FakeContext:
    def new_page(self): return FakePage(self)

@pytest.mark.parametrize('shared', [False, True])
def test_document_discovery_to_evidence_refresh_page_path(session, monkeypatch, tmp_path, shared):
    """Reproduce old closed-page path and prove the shared owner fixes it independently."""
    from app.pipeline.run_weekly import stage_documents, stage_evidence_refresh
    from app.pipeline.page_owner import PageOwner
    a=child(session)
    a.summary_url='https://example.invalid/1'
    a.evidence_refresh_required=True
    a.evidence_refresh_reason='decision_granted'
    a.evidence_refresh_trigger='material_change'
    session.commit()
    monkeypatch.setattr('app.pipeline.run_weekly.document_dir',lambda *a:tmp_path)
    seen=[]
    def discover(page,*args,**kwargs):
        seen.append(page.content())
        return []
    monkeypatch.setattr('app.pipeline.run_weekly.discover_documents',discover)
    original=FakeContext().new_page()
    page=PageOwner(original) if shared else original
    health=AcquisitionHealth()
    stage_documents(session,page,council(),health=health)
    assert original.closed
    stage_evidence_refresh(session,page,council(),health=health)
    if shared:
        assert len(seen) == 2
        assert health.evidence_refresh_failed == 0
        assert not page.page.closed
    else:
        assert len(seen) == 1
        assert health.evidence_refresh_failed == 1


def test_page_creation_and_close_failure_are_distinct():
    from app.pipeline.page_owner import PageOwner
    context=FakeContext(); original=context.new_page(); owner=PageOwner(original)
    context.new_page=lambda: (_ for _ in ()).throw(RuntimeError('create failed'))
    with pytest.raises(RuntimeError): owner.recycle()
    assert owner.page is original and not original.closed
    replacement=FakePage(context); context.new_page=lambda: replacement
    original.close=lambda: (_ for _ in ()).throw(RuntimeError('close failed'))
    with pytest.raises(RuntimeError): owner.recycle()
    assert owner.page is replacement and not replacement.closed


def test_idox_empty_ambiguous_and_partial_results(monkeypatch):
    from app.scrapers import idox_portal as portal
    page=MagicMock(); page.url='https://example.invalid/results'
    for html, outcome in [('<div id="noResults">No results</div>',Outcome.NOT_FOUND),
        ('<html>Unavailable</html>',Outcome.TRANSIENT_FAILURE),
        ('<a href="applicationDetails.do?keyVal=A">A</a><a href="applicationDetails.do?keyVal=B">B</a>',Outcome.AMBIGUOUS_IDENTITY),
        ('<div id="noResults"></div><a rel="next" href="?page=2">Next</a>',Outcome.TRANSIENT_FAILURE)]:
        page.content.return_value=html
        assert portal.lookup_parent(page,MagicMock(),council(),'OUT/100').outcome == outcome


def test_arcus_empty_and_unreadable_results(monkeypatch):
    from app.scrapers import arcus_portal as portal
    page=MagicMock(); page.eval_on_selector_all.return_value=[]
    monkeypatch.setattr(portal,'_parse_result_page',lambda *a:[])
    page.inner_text.return_value='No results found'
    assert portal.lookup_parent(page,council(),'OUT/100').outcome == Outcome.NOT_FOUND
    page.inner_text.return_value='Request failed'
    assert portal.lookup_parent(page,council(),'OUT/100').outcome == Outcome.TRANSIENT_FAILURE


def test_production_missing_identity_and_activation_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setenv('RENDER','true')
    with pytest.raises(RuntimeError,match='activation'):
        with DiscoveryOwner(str(tmp_path/'lock')): pass
    monkeypatch.setenv('RENDER_SERVICE_TYPE','cron')
    monkeypatch.setenv('RENDER_SERVICE_ID',SERVICE_ID)
    monkeypatch.setenv('RENDER_INSTANCE_ID','test')
    with pytest.raises(RuntimeError,match='activation'):
        with DiscoveryOwner(str(tmp_path/'lock')): pass


def test_fair_council_rotation_after_early_stop(session, monkeypatch):
    import scripts.run_daily_councils as daily
    from app.db.models import Council
    session.add(Council(code='third',name='Third',base_url='https://example.invalid',doc_system='idox',date_field_mode='received'))
    session.commit()
    monkeypatch.setattr(daily,'init_db',lambda:None)
    monkeypatch.setattr(daily,'get_session',lambda:session)
    monkeypatch.setattr(session,'close',lambda:None)
    monkeypatch.setattr(sys,'argv',['daily','--council','testcouncil','--council','othercouncil','--council','third'])
    called=[]
    def fake(sess, code,**kwargs):
        called.append(code)
        row=ScrapeRun(council_code=code,status='success',progress='{"process_failure":false}',finished_at=NOW)
        sess.add(row);sess.commit()
        return row
    monkeypatch.setattr(daily,'run_one_council',fake)
    for _ in range(3):
        readings=iter([None,(70,100)])
        monkeypatch.setattr('app.diagnostics.memory.cgroup_memory',lambda:next(readings,(70,100)))
        assert daily.main() == 1
    assert called == ['othercouncil','testcouncil','third']


def test_disabled_does_not_initialize_database(monkeypatch):
    import scripts.run_daily_councils as daily
    monkeypatch.setattr(sys,'argv',['daily'])
    monkeypatch.setenv('PROPERTYAIGENT_DISCOVERY_DISABLED','1')
    monkeypatch.setattr(daily,'init_db',lambda:pytest.fail('disabled must not bootstrap'))
    assert daily.main() == 1


def test_result_rejected_for_wrong_reservation_owner(session):
    w=ParentLookupWork(council_code='testcouncil',reference_key='out/1',raw_reference='OUT/1')
    session.add(w);session.commit()
    reserve(session,w,None,NOW)
    with pytest.raises(RuntimeError,match='result owner conflict'):
        finish(session,w,999,LookupResult(Outcome.NOT_FOUND),NOW)
    assert w.last_outcome == 'in_flight'


def test_postgres_migration_and_unique_key_when_disposable_server_available(monkeypatch):
    """Explicit local-only opt-in; never accepts an application DATABASE_URL."""
    monkeypatch.setattr("app.pipeline.discovery_owner.SCHEDULED_INSTANCE_PATTERN", "pg-old|pg-new")
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session
    from app.db.session import migrate_schema, verify_schema
    url=os.getenv('P0A_TEST_POSTGRES_URL')
    if not url: pytest.skip('disposable local PostgreSQL unavailable; mandatory release gate')
    parsed=make_url(url)
    assert parsed.host in ('127.0.0.1','localhost','::1')
    assert parsed.database.startswith('p0a_test_')
    assert not parsed.query  # no libpq host/service override
    engine=create_engine(url)
    # The named database must be disposable AND empty; never drop existing data.
    assert inspect(engine).get_table_names() == []
    try:
        from sqlalchemy.exc import DBAPIError
        with engine.connect() as connection:
            connection.execute(text('SET LOCAL statement_timeout = 100'))
            started = time.monotonic()
            with pytest.raises(DBAPIError):
                connection.execute(text('SELECT pg_sleep(5)'))
            assert time.monotonic() - started < 2
            connection.rollback()
            assert connection.scalar(text('SELECT 1')) == 1
            connection.rollback()
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(text('DROP TABLE parent_lookup_work'))
            connection.execute(text('ALTER TABLE scrape_runs DROP COLUMN progress'))
        assert migrate_schema(engine) == (['parent_lookup_work'],[('scrape_runs','progress')])
        assert migrate_schema(engine) == ([],[])
        assert verify_schema(engine) == ([],[])
        with pytest.raises(RuntimeError, match='rollback probe'):
            with engine.begin() as connection:
                connection.execute(text('CREATE TABLE p0a_transaction_probe (id INTEGER)'))
                raise RuntimeError('rollback probe')
        assert 'p0a_transaction_probe' not in inspect(engine).get_table_names()
        from app.db.models import Council
        with Session(engine) as db:
            db.add(Council(code='synthetic',name='Synthetic',base_url='https://example.invalid',doc_system='idox',date_field_mode='received'))
            db.commit()
            db.add(ParentLookupWork(council_code='synthetic',reference_key='out/1',raw_reference='OUT/1'))
            db.commit()
            db.add(ParentLookupWork(council_code='synthetic',reference_key='out/1',raw_reference='OUT/1'))
            with pytest.raises(IntegrityError): db.commit()
            db.rollback()
        # Real PostgreSQL sessions: conditional owner writes and rollback of
        # uncommitted result evidence, followed by positive successor recovery.
        from types import SimpleNamespace
        with Session(engine, expire_on_commit=False) as db:
            old = dict(version=1, invocation='pg-old', service=SERVICE_ID, instance='pg-old', scheduler_contract='render-scheduled-v1')
            row = ScrapeRun(council_code='synthetic', status='running', progress=json.dumps({'owner':old}))
            other = ScrapeRun(council_code='synthetic', status='running')
            db.add_all([row, other]); db.commit()
            w = db.scalar(select(ParentLookupWork))
            reserve(db, w, row.id, NOW)
            with pytest.raises(RuntimeError, match='result owner conflict'):
                finish(db, w, other.id, LookupResult(Outcome.NOT_FOUND), NOW)
            db.refresh(w)
            assert w.last_outcome == 'in_flight' and w.owner_scrape_run_id == row.id
            # A failed transaction cannot retain a partially written parent.
            db.add(Application(council_code='synthetic', reference='ROLLBACK/1'))
            db.flush()
            db.add(ParentLookupWork(council_code='missing-council',reference_key='bad/1',raw_reference='BAD/1'))
            with pytest.raises(IntegrityError): db.flush()
            db.rollback()
            assert db.scalar(select(Application).where(Application.reference=='ROLLBACK/1')) is None
            db.refresh(w)
            assert w.last_outcome == 'in_flight'  # earlier reservation survived
            reconcile_owners(db, SimpleNamespace(identity={**old, 'invocation':'pg-new','instance':'pg-new'}))
            db.refresh(w)
            assert w.last_outcome is None and w.total_attempts == 1
            assert w.last_started_at == NOW
            with pytest.raises(RuntimeError, match='result owner conflict'):
                finish(db, w, row.id, LookupResult(Outcome.NOT_FOUND), NOW)
            assert row.status == 'failed'
            reserve(db, w, other.id, NOW+dt.timedelta(days=1))
            finish(db, w, other.id, LookupResult(Outcome.NOT_FOUND), NOW+dt.timedelta(days=1))
            assert w.last_outcome == 'not_found' and w.total_attempts == 2
            # Duplicate/stale completion must not overwrite committed outcome.
            with pytest.raises(RuntimeError, match='result owner conflict'):
                finish(db, w, row.id, LookupResult(Outcome.AMBIGUOUS_IDENTITY), NOW)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_fixed_cohort_bounded_reproduction(session, monkeypatch, capsys):
    """Synthetic 48 references / 192 citations, progressing over three invocations."""
    from sqlalchemy import event
    import tracemalloc
    for n in range(192):
        session.add(Application(council_code='testcouncil',reference=f'CHILD/{n}',
            proposal=f'Reserved matters pursuant to outline planning permission OUT/{n%48}'))
    session.commit()
    queries=[]
    def count(conn,cursor,statement,parameters,context,executemany): queries.append(statement)
    event.listen(session.bind,'before_cursor_execute',count)
    seen=[]
    tracemalloc.start(); start=time.monotonic()
    try:
        monkeypatch.setenv('PROPERTYAIGENT_DISCOVERY_PARENT_ITEMS','20')
        for _ in range(3): run(session,lambda r:(seen.append(r),found(r))[1])
        elapsed=time.monotonic()-start
        _,peak=tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        event.remove(session.bind,'before_cursor_execute',count)
    assert len(seen)==len(set(seen))==48
    assert all(a.estimated_unit_count==50 for a in session.scalars(select(Application).where(Application.reference.like('CHILD/%'))))
    reports=[json.loads(line.split(' ',1)[1])['parents'] for line in capsys.readouterr().out.splitlines() if line.startswith('[discovery-progress] ')]
    assert [r['distinct_attempted'] for r in reports]==[20,20,8]
    assert [r['deferred'] for r in reports]==[28,8,0]
    assert sum(r['duplicate_requests_suppressed'] for r in reports)==144
    assert all('documents.extracted_text' not in q for q in queries)
    assert elapsed < 30 and peak < 64*1024*1024
    print(json.dumps({'fixture_references':48,'fixture_citations':192,'invocation_attempts':[20,20,8],
        'duplicate_requests_suppressed':144,'sql_statements':len(queries),
        'python_peak_bytes':peak,'duration_seconds':round(elapsed,3),
        'work_state_json_bytes':sum(len(json.dumps({c.name:getattr(w,c.name) for c in ParentLookupWork.__table__.columns},default=str).encode()) for w in session.scalars(select(ParentLookupWork))),
        'memory_scope':'tracemalloc Python allocations only; not cgroup or browser memory',
        'transfer_scope':'serialized synthetic work state; not measured database wire egress'}))


def test_parent_stage_envelope_supervised_even_if_worker_is_silent(monkeypatch):
    from scripts.run_daily_councils import _run_council_subprocess
    # Accelerate only the synthetic parent's start budget. Production validates
    # positive configured values; the 60s logical allowance remains unchanged.
    monkeypatch.setattr('app.pipeline.parent_lookup.positive_limit',lambda *a: -59.9)
    script="import time;print('[mem] stage=stage_fetch_missing_parents.before',flush=True);time.sleep(20)"
    start=time.monotonic()
    with pytest.raises(RuntimeError,match='parent stage stop envelope'):
        _run_council_subprocess([sys.executable,'-u','-c',script],cwd=ROOT,timeout_seconds=10)
    assert time.monotonic()-start < 6


def test_missing_final_health_is_not_successful_freshness(session):
    from app.reporting.scraper_health import build_scraper_health_summary
    session.add(ScrapeRun(council_code='testcouncil',status='partial',finished_at=NOW,
        progress='{"version":1,"process_failure":true}'))
    session.commit()
    row=next(r for r in build_scraper_health_summary(session) if r['council_code']=='testcouncil')
    assert row['last_successful_at'] is None
    assert row['last_attempt_status']=='partial'


def test_parent_http_date_retry_after_preserved_without_changing_primary():
    from app.pipeline.lookup_outcome import retry_wait, remember_retry_after, bounded_sleep
    from email.utils import format_datetime
    date=format_datetime(dt.datetime.now(dt.timezone.utc)+dt.timedelta(seconds=100))
    assert retry_wait(date,5)==5  # primary path unchanged
    def wait():
        delay=retry_wait(date,5)
        assert delay > 98
        remember_retry_after(delay)
        bounded_sleep(1)
    result=strict_lookup(wait,'OUT/100',seconds=.03)
    assert result.retry_after_seconds > 98


def test_crash_after_found_commit_resumes_sharing_without_request(session, monkeypatch):
    import app.pipeline.parent_lookup as parents
    a=child(session)
    original=parents.fan_out
    monkeypatch.setattr(parents,'fan_out',lambda *a: (_ for _ in ()).throw(RuntimeError('synthetic interruption')))
    with pytest.raises(RuntimeError): run(session,found)
    assert session.scalar(select(ParentLookupWork)).last_outcome=='found'
    assert a.estimated_unit_count is None
    monkeypatch.setattr(parents,'fan_out',original)
    run(session,lambda _:pytest.fail('committed success must not repeat request'))
    assert a.estimated_unit_count==50


def test_same_instance_recovery_requires_positive_process_absence(monkeypatch):
    old=dict(version=1,invocation='old',service=SERVICE_ID,instance='same',boot='boot',pid=123,pid_start=1,child_pid=456,child_start=2)
    new={**old,'invocation':'new'}
    monkeypatch.setattr('app.pipeline.discovery_owner.process_identity',lambda pid:1 if pid==123 else 2)
    with pytest.raises(RuntimeError): terminal_evidence(old,new)
    monkeypatch.setattr('app.pipeline.discovery_owner.process_identity',lambda pid:None)
    assert terminal_evidence(old,new)=='same_host_processes_exited'


@pytest.mark.parametrize('activated,disabled,mode,expected', [
    ('0','0',None,'bounded'),('1','0','bounded','bounded'),
    ('1','1','bounded','disabled'),('1','0','disabled','disabled'),
    ('0','1',None,'disabled'),
])
def test_switch_precedence(monkeypatch, activated, disabled, mode, expected):
    from app.pipeline.discovery_config import discovery_switches, require_discovery_enabled
    monkeypatch.setenv('PROPERTYAIGENT_DISCOVERY_ACTIVATED',activated)
    monkeypatch.setenv('PROPERTYAIGENT_DISCOVERY_DISABLED',disabled)
    if mode is None: monkeypatch.delenv('PROPERTYAIGENT_DISCOVERY_MODE',raising=False)
    else: monkeypatch.setenv('PROPERTYAIGENT_DISCOVERY_MODE',mode)
    assert discovery_switches()['mode']==expected
    if expected=='disabled':
        with pytest.raises(RuntimeError,match='disabled'): require_discovery_enabled()


@pytest.mark.parametrize('name,value',[('ACTIVATED','true'),('DISABLED','false'),('DISABLED',''),('MODE','off'),('MODE','BOUNDED')])
def test_invalid_switches_fail_before_database(monkeypatch,name,value):
    import scripts.run_daily_councils as daily
    monkeypatch.setattr(sys,'argv',['daily'])
    monkeypatch.setenv('PROPERTYAIGENT_DISCOVERY_'+name,value)
    monkeypatch.setattr(daily,'init_db',lambda:pytest.fail('invalid switch bootstrapped DB'))
    with pytest.raises(ValueError,match='invalid discovery'): daily.main()


def test_bounded_mode_alone_never_activates_production(monkeypatch):
    from app.pipeline.discovery_config import require_discovery_enabled
    monkeypatch.setenv('RENDER','true')
    monkeypatch.setenv('PROPERTYAIGENT_DISCOVERY_MODE','bounded')
    monkeypatch.delenv('PROPERTYAIGENT_DISCOVERY_ACTIVATED',raising=False)
    with pytest.raises(RuntimeError,match='activation blocked'): require_discovery_enabled()


@pytest.mark.parametrize('phase', ['bootstrap', 'reconciliation', 'on_start', 'on_line', 'final_status'])
def test_independent_watchdog_bounds_blocked_persistence(tmp_path, phase, record_property):
    """Real process/lock evidence. No DB driver mock is used as timeout proof."""
    lock = tmp_path/'child.lock'
    ready = tmp_path/'ready'
    child_script = '''import fcntl,sys,time
f=open(sys.argv[1],'w');fcntl.flock(f,fcntl.LOCK_EX)
open(sys.argv[2],'w').write('ready')
print('READY',flush=True)
time.sleep(30)
'''
    supervisor = '''import sys,time,subprocess,os
from types import SimpleNamespace
from app.pipeline.discovery_watchdog import DiscoveryWatchdog
from scripts.run_daily_councils import _run_council_subprocess
phase=sys.argv[1]
with DiscoveryWatchdog(time.monotonic()+2) as watchdog:
 if phase in ('bootstrap','reconciliation'):time.sleep(30)
 fd=os.open(sys.argv[2],os.O_CREAT|os.O_RDWR,0o600)
 owner=SimpleNamespace(watchdog=watchdog,fd=fd,child_environment=lambda run:dict(os.environ))
 def persist_start(pid):
  if phase=='on_start':
   while not os.path.exists(sys.argv[3]):time.sleep(.01)
   time.sleep(30)
 def persist_line(line):
  if phase=='on_line' and line=='READY':time.sleep(30)
 script=sys.argv[4]
 if phase=='final_status':script=script.replace('time.sleep(30)','time.sleep(.05)')
 _run_council_subprocess([sys.executable,'-u','-c',script,sys.argv[2],sys.argv[3]],cwd='.',timeout_seconds=20,on_start=persist_start,on_line=persist_line,owner=owner,run_id=1)
 time.sleep(30)
'''
    started = time.monotonic()
    result = subprocess.run([sys.executable, '-c', supervisor, phase, str(lock), str(ready), child_script],
                            cwd=ROOT, capture_output=True, text=True, timeout=6)
    assert result.returncode == -signal.SIGKILL
    elapsed = time.monotonic()-started
    record_property('termination_seconds', elapsed)
    record_property('configured_deadline_seconds', 2)
    record_property('emergency_cleanup_allowance_seconds', 0)
    record_property('scheduling_margin_seconds', 3)
    assert elapsed < 2 + 0 + 3  # interpreter startup and shared-runner scheduling
    assert 'final database status unverified' in result.stderr
    if phase not in ('bootstrap', 'reconciliation'):
        assert ready.exists()
        import fcntl
        with lock.open('r') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_bounded_page_limits_each_operation_and_preserves_other_calls():
    from app.pipeline.lookup_outcome import BoundedPage, request_deadline, bounded_sleep
    seen=[]
    class Page:
        def goto(self, url, **kw): seen.append(kw['timeout'])
    with request_deadline(.2):
        BoundedPage(Page()).goto('synthetic', timeout=45000)
        bounded_sleep(.02)
        BoundedPage(Page()).goto('synthetic', timeout=45000)
    assert 0 < seen[1] < seen[0] <= 200


def test_discovery_database_bounds_are_opt_in(monkeypatch):
    import app.db.session as db
    captured={}
    monkeypatch.setattr(db, '_engine', None)
    monkeypatch.setattr(db, '_discovery_bounds', False)
    monkeypatch.setattr(db, 'load_dotenv', lambda:None)
    monkeypatch.setenv('DATABASE_URL', 'postgresql://localhost/p0a_test_unit')
    monkeypatch.setattr(db, 'create_engine', lambda url, **kw: captured.update(kw) or object())
    attached=[]
    monkeypatch.setattr(db, 'install_discovery_transaction_bounds', attached.append)
    db.configure_discovery_database_bounds()
    engine=db.get_engine()
    assert captured['connect_args']['connect_timeout']==10
    assert 'options' not in captured['connect_args']
    assert captured['pool_timeout']==10
    assert attached == [engine]
    assert 'prepare_threshold' not in captured['connect_args']


def test_unregistered_gate_exits_on_supervisor_pipe_loss(tmp_path, record_property):
    """Actual creation/registration gap: no application work or retained lock."""
    import fcntl
    lock = tmp_path/'gate.lock'
    marker = tmp_path/'must-not-start'
    fd = os.open(lock, os.O_CREAT|os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
    read_fd, write_fd = os.pipe()
    command = [sys.executable,'-m','app.pipeline.discovery_watchdog','gate',str(read_fd),
               str(time.monotonic()+3),sys.executable,'-c',
               'import pathlib,sys;pathlib.Path(sys.argv[1]).touch()',str(marker)]
    child = subprocess.Popen(command,cwd=ROOT,pass_fds=(read_fd,fd),start_new_session=True)
    started=time.monotonic()
    os.close(read_fd);os.close(write_fd);os.close(fd)
    try:
        assert child.wait(timeout=3)==1
        assert not marker.exists()
        with lock.open('r') as handle:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        record_property('unregistered_gate_cleanup_seconds',time.monotonic()-started)
    finally:
        if child.poll() is None: child.kill();child.wait(timeout=3)


def test_expired_group_cannot_extend_budget(tmp_path, record_property):
    marker=tmp_path/'late-work'
    script='''import os,sys,time,signal,json,subprocess
from app.pipeline.discovery_watchdog import DiscoveryWatchdog
with DiscoveryWatchdog(time.monotonic()+3) as watchdog:
 child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)'],start_new_session=True)
 watchdog.register(child.pid,time.monotonic()+.2)
 os.kill(watchdog.process.pid,signal.SIGSTOP)
 time.sleep(.3)
 os.write(watchdog.process.stdin.fileno(),(json.dumps({'group':child.pid,'deadline':time.monotonic()+10})+'\\n').encode())
 os.kill(watchdog.process.pid,signal.SIGCONT)
 time.sleep(.5)
 open(sys.argv[1],'w').write('bad')
'''
    started=time.monotonic()
    result=subprocess.run([sys.executable,'-c',script,str(marker)],cwd=ROOT,capture_output=True,timeout=5)
    assert result.returncode==-signal.SIGKILL
    assert not marker.exists()
    record_property('expired_group_termination_seconds',time.monotonic()-started)


def test_parent_envelope_is_130_seconds_and_capped():
    from app.pipeline.discovery_watchdog import parent_deadlines
    assert parent_deadlines(100,60,1000,2000)==(220,230)
    assert parent_deadlines(100,60,1000,225)==(220,225)
    assert parent_deadlines(100,60,150,2000)==(150,160)


def test_real_escalation_when_child_ignores_sigterm(tmp_path, monkeypatch, record_property):
    from scripts.run_daily_councils import _run_council_subprocess
    import fcntl
    monkeypatch.setattr('app.pipeline.parent_lookup.positive_limit',lambda *a: -59.9)
    path=tmp_path/'escalation.lock'
    script='''import sys,time,signal,fcntl
f=open(sys.argv[1],'w');fcntl.flock(f,fcntl.LOCK_EX)
signal.signal(signal.SIGTERM,lambda *a:print('TERM_IGNORED',flush=True))
print('[mem] stage=stage_fetch_missing_parents.before',flush=True)
time.sleep(30)
'''
    lines=[];started=time.monotonic()
    with pytest.raises(RuntimeError,match='parent stage stop envelope'):
        _run_council_subprocess([sys.executable,'-u','-c',script,str(path)],cwd=ROOT,
                               timeout_seconds=20,on_line=lines.append)
    elapsed=time.monotonic()-started
    # SIGTERM wait is five seconds; process does not voluntarily finish for 30.
    assert 5 <= elapsed < .1 + 10 + 1
    with path.open('r') as handle:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    record_property('sigterm_to_forced_cleanup_total_seconds',elapsed)


def test_full_stderr_pipe_cannot_hold_watchdog_alive(record_property):
    script='''import os,time
from app.pipeline.discovery_watchdog import DiscoveryWatchdog
with DiscoveryWatchdog(time.monotonic()+.5):
 os.set_blocking(2,False)
 try:
  while True:os.write(2,b'x'*4096)
 except BlockingIOError:pass
 os.set_blocking(2,True)
 time.sleep(20)
'''
    started=time.monotonic()
    p=subprocess.Popen([sys.executable,'-c',script],cwd=ROOT,stderr=subprocess.PIPE)
    try:
        assert p.wait(timeout=3)==-signal.SIGKILL
        # Wait for pipe EOF too: watchdog must exit without a logger drain.
        os.set_blocking(p.stderr.fileno(),False)
        end=started+3
        while True:
            try:
                if not os.read(p.stderr.fileno(),65536):break
            except BlockingIOError:
                assert time.monotonic()<end
                time.sleep(.01)
        record_property('blocked_logging_termination_seconds',time.monotonic()-started)
    finally:
        if p.poll() is None:p.kill();p.wait(timeout=3)
        p.stderr.close()
