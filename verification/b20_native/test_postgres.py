"""Disposable PostgreSQL 17 only; synthetic facts and mocked council retrieval.

Never run via the SQLite acceptance launcher. No production URL fallback.
"""
import datetime as dt
import os
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session

from app.db.models import Base, Council, Application, ApplicationLifecycleEvent
from app.pipeline.status_verification import verify_application_status
from tests.test_planning_status_verification import _council_config, _scraped

OLD = dt.datetime(2026, 9, 18, 5, 20, 51, tzinfo=dt.timezone.utc)
COUPLED = ('status', 'decision', 'decision_issued_date', 'status_verified_at',
           'evidence_refresh_required', 'evidence_refresh_reason',
           'evidence_refresh_trigger', 'evidence_refresh_requested_at')


@pytest.fixture(scope='module')
def engine():
    assert os.environ.get('B20_DISPOSABLE') == 'YES_SYNTHETIC_ONLY'
    assert not os.environ.get('DATABASE_URL')
    port = int(os.environ['B20_POSTGRES_PORT'])
    assert 1024 <= port <= 65535
    # Public throwaway CI-only credential, not a production secret.
    e = create_engine(f'postgresql+psycopg://b20_disposable:b20-disposable-only@127.0.0.1:{port}/b20_disposable',
                      pool_size=5, max_overflow=0,
                      connect_args={'connect_timeout': 5, 'application_name': 'b20_native',
                                    'options': '-c statement_timeout=10000 -c lock_timeout=8000'})
    with e.connect() as c:
        version = c.execute(text('SHOW server_version')).scalar_one()
        isolation = c.execute(text('SHOW transaction_isolation')).scalar_one()
        assert version.startswith('17.')
        assert isolation == 'read committed'
        assert c.execute(text('SELECT current_database()')).scalar_one() == 'b20_disposable'
        print(f'NATIVE_ENV version={version} isolation={isolation} synthetic_only=true')
    Base.metadata.create_all(e)  # Disposable empty database, no migration/production.
    with Session(e) as s:
        s.add(Council(code='testcouncil', name='Synthetic', base_url='https://example.invalid',
                      date_field_mode='received', doc_system='idox'))
        s.commit()
    yield e
    assert e.pool.checkedout() == 0
    with e.connect() as c:
        assert c.execute(text("SELECT count(*) FROM pg_stat_activity WHERE application_name='b20_native' AND pid<>pg_backend_pid() AND state LIKE 'idle in transaction%'")).scalar_one() == 0
    e.dispose()


@pytest.fixture(autouse=True)
def no_external_calls():
    with patch('requests.sessions.Session.request', side_effect=AssertionError('Council/network forbidden')):
        yield


def seed(engine, reference, **fields):
    with Session(engine) as s:
        a = Application(council_code='testcouncil', reference=reference,
                        status='Awaiting decision', status_verified_at=OLD, **fields)
        s.add(a); s.commit()
        return a.id


def result(reference, decision='Refused', date='2026-09-25'):
    r = _scraped(reference, status='Decided' if decision else 'Awaiting decision', decision=decision)
    if date and decision: r.fields['Decision Issued Date'] = date
    return r


def read(engine, identity):
    with Session(engine) as s:
        a = s.get(Application, identity)
        facts = tuple(getattr(a, k) for k in COUPLED)
        events = [(e.event_type, e.field_name, e.old_value, e.new_value) for e in
                  s.scalars(select(ApplicationLifecycleEvent).where(ApplicationLifecycleEvent.application_id == identity).order_by(ApplicationLifecycleEvent.id))]
        return facts, events


def verify(s, identity, r):
    with patch('app.scrapers.idox_portal.fetch_application_by_reference', return_value=r):
        return verify_application_status(s, MagicMock(), _council_config(), s.get(Application, identity))


@pytest.mark.parametrize('name,decision', [('Southlink', None), ('Failsworth', 'Refused')])
def test_success_coherent(engine, name, decision):
    identity = seed(engine, name)
    with Session(engine) as s:
        commits = []
        event.listen(s, 'after_commit', lambda _: commits.append(1))
        out = verify(s, identity, result(name, decision))
        assert len(commits) == 1
        assert not s.in_transaction()
    facts, events = read(engine, identity)
    assert facts[1] == decision and facts[3] > OLD
    assert facts[2] == ('2026-09-25' if decision else None)
    assert facts[4] == bool(decision)
    assert len(events) == int(bool(decision))
    assert out.outcome == ('verified_changed' if decision else 'verified_unchanged')
    if decision: assert events[0][0] == 'decision_refused' and facts[7] is not None


@pytest.mark.parametrize('point', ['before_flush', 'after_flush', 'commit', 'interrupt'])
def test_atomic_failure(engine, monkeypatch, point):
    identity = seed(engine, f'failure-{point}'); before = read(engine, identity)
    with Session(engine) as s:
        if point in {'before_flush', 'after_flush'}:
            def fail(*_): raise RuntimeError('Synthetic flush interruption')
            event.listen(s, point, fail)
        else:
            def fail():
                if point == 'interrupt': raise KeyboardInterrupt()
                raise RuntimeError('Synthetic commit failure')
            monkeypatch.setattr(s, 'commit', fail)
        if point == 'interrupt':
            with pytest.raises(KeyboardInterrupt): verify(s, identity, result(f'failure-{point}'))
        else: assert verify(s, identity, result(f'failure-{point}')).outcome == 'persistence_failed'
        assert not s.in_transaction()
    assert read(engine, identity) == before
    assert engine.pool.checkedout() == 0


def test_lost_ack_and_duplicate_retry(engine, monkeypatch):
    identity = seed(engine, 'lost-ack')
    with Session(engine) as s:
        original = s.commit
        def lost(): original(); raise RuntimeError('Synthetic lost commit acknowledgement')
        monkeypatch.setattr(s, 'commit', lost)
        assert verify(s, identity, result('lost-ack')).outcome == 'persistence_failed'
        assert not s.in_transaction()
    accepted = read(engine, identity)
    assert accepted[0][1] == 'Refused' and len(accepted[1]) == 1
    with Session(engine) as s:
        assert verify(s, identity, result('lost-ack')).outcome == 'verified_unchanged'
    assert read(engine, identity)[1] == accepted[1]


@pytest.mark.parametrize('block_writer', [False, True])
def test_real_concurrent_connections(engine, block_writer):
    ref = f'concurrent-{block_writer}'; identity = seed(engine, ref)
    barrier = threading.Barrier(2); reserved = threading.Event(); release = threading.Event()
    finished = threading.Event(); older_fetch = threading.Event()
    outcomes = {}; failures = []; pids = {}; local = threading.local()
    def fetch(*_):
        barrier.wait(timeout=8)  # both accepted-state snapshots precede either response
        if local.kind == 'older':
            older_fetch.set()
            assert (reserved if block_writer else finished).wait(8)
        return result(ref, 'Granted' if local.kind == 'older' else 'Refused',
                      '2026-09-01' if local.kind == 'older' else '2026-09-25')
    def after_sql(conn, cursor, statement, *args):
        if block_writer and local.kind == 'newer' and statement.startswith('UPDATE applications SET status_verified_at'):
            reserved.set(); assert release.wait(8)
    def worker(kind):
        local.kind = kind
        try:
            with Session(engine) as s:
                pids[kind] = s.connection().connection.driver_connection.info.backend_pid
                if kind == 'newer': event.listen(s.connection(), 'after_cursor_execute', after_sql)
                outcomes[kind] = verify_application_status(s, MagicMock(), _council_config(), s.get(Application, identity)).outcome
                assert not s.in_transaction()
            if kind == 'newer': finished.set()
        except BaseException as exc: failures.append(exc); release.set(); finished.set(); reserved.set()
    with patch('app.scrapers.idox_portal.fetch_application_by_reference', side_effect=fetch):
        threads = [threading.Thread(target=worker, args=(k,)) for k in ('newer', 'older')]
        for t in threads: t.start()
        try:
            if block_writer:
                assert reserved.wait(8) and older_fetch.wait(8)
                deadline = time.monotonic() + 5
                waiting = False
                while time.monotonic() < deadline:
                    with engine.connect() as c:
                        waiting = c.execute(text("SELECT wait_event_type='Lock' FROM pg_stat_activity WHERE pid=:pid"), {'pid': pids['older']}).scalar_one()
                    if waiting: break
                    time.sleep(.02)
                assert waiting, 'Second actual PostgreSQL UPDATE did not wait on the first writer'
        finally:
            release.set()
            for t in threads: t.join(timeout=12)
    assert not any(t.is_alive() for t in threads)
    assert failures == []
    assert len(set(pids.values())) == 2
    assert outcomes == {'newer': 'verified_changed', 'older': 'stale_response'}
    facts, events = read(engine, identity)
    assert facts[1:3] == ('Refused', '2026-09-25') and len(events) == 1
    assert engine.pool.checkedout() == 0


def test_older_terminal_evidence(engine):
    identity = seed(engine, 'terminal-old')
    with Session(engine) as s: assert verify(s, identity, result('terminal-old')).outcome == 'verified_changed'
    before = read(engine, identity)
    with Session(engine) as s:
        assert verify(s, identity, result('terminal-old', 'Granted', '2026-09-01')).outcome == 'conflicting_source'
        assert not s.in_transaction()
    assert read(engine, identity) == before


def test_date_only_correction_retry(engine):
    identity = seed(engine, 'date-only')
    with Session(engine) as s: assert verify(s, identity, result('date-only', 'Granted', '2026-09-01')).outcome == 'verified_changed'
    with Session(engine) as s:
        out = verify(s, identity, result('date-only', 'Granted', '2026-09-02'))
        assert out.outcome == 'verified_changed' and 'decision_date_corrected' in out.material_change_reasons
    accepted = read(engine, identity)
    assert accepted[0][2] == '2026-09-02' and len(accepted[1]) == 2
    assert accepted[1][-1][1] == 'decision_issued_date'
    with Session(engine) as s: assert verify(s, identity, result('date-only', 'Granted', '2026-09-02')).outcome == 'verified_unchanged'
    assert read(engine, identity)[1] == accepted[1]


@pytest.mark.parametrize('case', ['wrong_reference', 'unavailable'])
def test_retrieval_failure_cleanup(engine, case):
    identity = seed(engine, f'retrieval-{case}'); before = read(engine, identity)
    with Session(engine) as s:
        r = result('OTHER') if case == 'wrong_reference' else None
        assert verify(s, identity, r).outcome in {'fetch_failed', 'application_not_found'}
        assert not s.in_transaction()
    assert read(engine, identity) == before and engine.pool.checkedout() == 0


def test_server_commit_rejection(engine):
    identity = seed(engine, 'server-reject'); before = read(engine, identity)
    # Harness-only deferred FK: a real PostgreSQL COMMIT rejection, not a
    # changed application schema or mocked database exception.
    with engine.begin() as c:
        c.execute(text('CREATE TABLE b20_commit_parent (id integer PRIMARY KEY)'))
        c.execute(text('CREATE TABLE b20_commit_child (parent_id integer REFERENCES b20_commit_parent(id) DEFERRABLE INITIALLY DEFERRED)'))
    with Session(engine) as s:
        def fail(session):
            session.flush()  # actual facts, watermark and events sent to PostgreSQL
            session.execute(text('INSERT INTO b20_commit_child(parent_id) VALUES (999)'))
        event.listen(s, 'before_commit', fail)
        assert verify(s, identity, result('server-reject')).outcome == 'persistence_failed'
        assert not s.in_transaction()
    assert read(engine, identity) == before


def test_native_query_cancellation_cleanup(engine):
    identity = seed(engine, 'cancel'); before = read(engine, identity)
    pid = []; outcomes = []; failures = []; fetching = threading.Event()
    def fetch(*_): fetching.set(); return result('cancel')
    def worker():
        try:
            with Session(engine) as s:
                pid.append(s.connection().connection.driver_connection.info.backend_pid)
                outcomes.append(verify_application_status(s, MagicMock(), _council_config(), s.get(Application, identity)).outcome)
                assert not s.in_transaction()
        except BaseException as exc: failures.append(exc)
    with engine.connect() as blocker:
        tx = blocker.begin()
        blocker.execute(text('SELECT id FROM applications WHERE id=:id FOR UPDATE'), {'id': identity})
        with patch('app.scrapers.idox_portal.fetch_application_by_reference', side_effect=fetch):
            thread = threading.Thread(target=worker); thread.start()
            try:
                assert fetching.wait(5)
                deadline = time.monotonic() + 5
                waiting = False
                while time.monotonic() < deadline:
                    with engine.connect() as c:
                        waiting = c.execute(text("SELECT wait_event_type='Lock' FROM pg_stat_activity WHERE pid=:pid"), {'pid': pid[0]}).scalar_one()
                        if waiting: assert c.execute(text('SELECT pg_cancel_backend(:pid)'), {'pid': pid[0]}).scalar_one()
                    if waiting: break
                    time.sleep(.02)
                assert waiting
                thread.join(timeout=8)
            finally: tx.rollback(); thread.join(timeout=12)
    assert not thread.is_alive() and failures == [] and outcomes == ['persistence_failed']
    assert read(engine, identity) == before and engine.pool.checkedout() == 0
