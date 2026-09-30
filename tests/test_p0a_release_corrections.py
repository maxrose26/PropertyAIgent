"""New candidate acceptance. Real PostgreSQL cases must execute, not skip, for release."""
import os
import time
import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from app.db.models import Base
from app.db.session import install_discovery_transaction_bounds
from app.pipeline import discovery_owner as ownership
from scripts import migrate_p0a as migration


@pytest.fixture
def pg():
    url = os.getenv('P0A_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('disposable PostgreSQL unavailable: new candidate gate NOT complete')
    parsed = make_url(url)
    assert parsed.host in ('127.0.0.1', 'localhost', '::1')
    assert parsed.database.startswith('p0a_test_') and not parsed.query
    engine = create_engine(url)
    assert inspect(engine).get_table_names() == [], 'Refuse nonempty database'
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def settings(connection):
    return tuple(connection.execute(text("SELECT current_setting('statement_timeout'), current_setting('lock_timeout'), current_setting('idle_in_transaction_session_timeout')")).one())


def test_pg_transaction_bounds_rollback_replacement_and_orm(pg):
    install_discovery_transaction_bounds(pg)
    for _ in range(2):
        with pg.connect() as c:
            assert settings(c) == ('15s','5s','30s')
            c.rollback()
            assert c.scalar(text('SELECT 1')) == 1
            assert settings(c) == ('15s','5s','30s')
            c.commit()
            assert settings(c) == ('15s','5s','30s')
        pg.dispose()  # next checkout MUST establish a replacement connection
    with Session(pg) as db:
        assert settings(db) == ('15s','5s','30s')
        db.rollback()
        assert settings(db) == ('15s','5s','30s')


def test_pg_real_timeout_retry_and_subsequent_work(pg, record_property):
    install_discovery_transaction_bounds(pg)
    with pg.connect() as c:
        assert settings(c) == ('15s','5s','30s')
        server_start = c.scalar(text('SELECT clock_timestamp()'))
        wall_start = time.time()
        raw_start = time.clock_gettime(time.CLOCK_MONOTONIC_RAW)
        start = time.monotonic()
        with pytest.raises(DBAPIError) as failure:
            c.execute(text('SELECT pg_sleep(25)'))
        elapsed = time.monotonic()-start
        raw_elapsed = time.clock_gettime(time.CLOCK_MONOTONIC_RAW)-raw_start
        wall_elapsed = time.time()-wall_start
        record_property('statement_timeout_elapsed_seconds', elapsed)
        record_property('statement_timeout_raw_elapsed_seconds', raw_elapsed)
        record_property('statement_timeout_wall_elapsed_seconds', wall_elapsed)
        sqlstate = getattr(failure.value.orig, 'sqlstate', None)
        record_property('statement_timeout_sqlstate', sqlstate)
        record_property('statement_timeout_server_message', str(failure.value.orig))
        # Always exercise recovery before assessing the timing measurement.
        # WSL evidence measured an unexpectedly early cancellation; retain the
        # original bound and collect independent clocks, rather than waive it.
        c.rollback()
        assert c.scalar(text('SELECT 1')) == 1
        assert settings(c) == ('15s','5s','30s')
        server_end = c.scalar(text('SELECT clock_timestamp()'))
        record_property('server_elapsed_including_recovery_seconds',
                        (server_end-server_start).total_seconds())
        record_property('rollback_and_subsequent_work_verified', True)
        assert sqlstate == '57014'
        assert 14 <= elapsed < 19  # unchanged: 15s bound + 4s scheduling allowance


def test_pg_bound_verification_failure_invalidates_connection(pg):
    install_discovery_transaction_bounds(pg)
    def changed_setting(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith('SELECT current_setting'):
            cursor.execute("SET LOCAL statement_timeout='2min'")
    event.listen(pg, 'before_cursor_execute', changed_setting)
    try:
        with pg.connect() as c:
            with pytest.raises(RuntimeError, match='not effective'):
                c.execute(text('SELECT 1'))
            assert c.invalidated
            c.rollback()
    finally:
        event.remove(pg, 'before_cursor_execute', changed_setting)
    with pg.connect() as c:
        assert settings(c) == ('15s','5s','30s')


def legacy_schema(pg):
    Base.metadata.create_all(pg)
    with pg.begin() as c:
        c.execute(text('DROP TABLE parent_lookup_work'))
        c.execute(text('ALTER TABLE scrape_runs DROP COLUMN progress'))


def test_pg_exact_migration_first_repeat_and_no_data_updates(pg):
    legacy_schema(pg)
    statements=[]
    def capture(conn,cursor,statement,parameters,context,executemany): statements.append(statement)
    event.listen(pg,'before_cursor_execute',capture)
    assert set(migration.migrate_p0a(pg)) == {'parent_lookup_work','scrape_runs.progress'}
    assert 'parent_lookup_work' not in inspect(pg).get_table_names()
    assert set(migration.migrate_p0a(pg,apply=True)) == {'parent_lookup_work','scrape_runs.progress'}
    assert migration.migrate_p0a(pg,apply=True) == []
    assert not any(s.lstrip().upper().startswith(('UPDATE ', 'INSERT ', 'DELETE ')) for s in statements)


def test_pg_exact_migration_rolls_back_both_additions(pg, monkeypatch):
    legacy_schema(pg)
    original=migration.verify_definitions
    def fail_after_ddl(connection, *, allow_missing):
        if not allow_missing: raise RuntimeError('injected post-DDL verification failure')
        return original(connection,allow_missing=allow_missing)
    monkeypatch.setattr(migration,'verify_definitions',fail_after_ddl)
    with pytest.raises(RuntimeError,match='injected'):
        migration.migrate_p0a(pg,apply=True)
    assert 'parent_lookup_work' not in inspect(pg).get_table_names()
    assert 'progress' not in {c['name'] for c in inspect(pg).get_columns('scrape_runs')}


def test_pg_exact_migration_rejects_unexpected_drift(pg):
    legacy_schema(pg)
    with pg.begin() as c: c.execute(text('ALTER TABLE councils ADD COLUMN unreviewed TEXT'))
    with pytest.raises(RuntimeError,match='unexpected columns'):
        migration.migrate_p0a(pg,apply=True)
    assert 'parent_lookup_work' not in inspect(pg).get_table_names()


def test_pg_exact_migration_rejects_wrong_existing_definition(pg):
    Base.metadata.create_all(pg)
    with pg.begin() as c: c.execute(text('DROP INDEX ix_parent_lookup_due'))
    with pytest.raises(RuntimeError,match='index drift'):
        migration.migrate_p0a(pg,apply=True)


@pytest.fixture
def scheduled(monkeypatch):
    # Synthetic reviewed identity contract for offline tests ONLY. Production's
    # pattern remains None until actual scheduled-runtime evidence is reviewed.
    monkeypatch.setattr(ownership,'SCHEDULED_INSTANCE_PATTERN',r'run-[a-z]+')
    monkeypatch.setenv('RENDER_SERVICE_TYPE','cron')
    monkeypatch.setenv('RENDER_SERVICE_ID',ownership.SERVICE_ID)
    monkeypatch.setenv('RENDER_INSTANCE_ID','run-first')
    monkeypatch.setenv('PROPERTYAIGENT_DISCOVERY_ACTIVATED','1')
    monkeypatch.setenv('PROPERTYAIGENT_DISCOVERY_DISABLED','0')
    monkeypatch.setenv('PROPERTYAIGENT_DISCOVERY_MODE','bounded')


@pytest.mark.parametrize('instance', ['shl-'+ownership.SERVICE_ID, 'worker-first', '', 'unknown'])
def test_shell_and_unverified_runtime_rejected(scheduled, monkeypatch, tmp_path, instance):
    monkeypatch.setenv('RENDER_INSTANCE_ID',instance)
    with pytest.raises(RuntimeError,match='identity'):
        with ownership.DiscoveryOwner(str(tmp_path/'lock')): pass
    assert not (tmp_path/'lock').exists()


def test_production_contract_remains_unverified(scheduled, monkeypatch, tmp_path):
    monkeypatch.setattr(ownership,'SCHEDULED_INSTANCE_PATTERN',None)
    with pytest.raises(RuntimeError,match='unverified'):
        with ownership.DiscoveryOwner(str(tmp_path/'lock')): pass


def test_offline_verified_scheduled_admission(scheduled, tmp_path):
    with ownership.DiscoveryOwner(str(tmp_path/'lock')) as owner:
        assert owner.identity['scheduler_contract'] == ownership.SCHEDULER_CONTRACT
        assert owner.identity['pid_start'] > 0


def test_only_verified_scheduler_successor_can_recover(scheduled):
    old=dict(version=1,invocation='a',service=ownership.SERVICE_ID,instance='run-first',scheduler_contract=ownership.SCHEDULER_CONTRACT)
    new={**old,'invocation':'b','instance':'run-second'}
    assert ownership.terminal_evidence(old,new) == 'same_service_successor_admitted'
    for invalid in ({**old,'instance':'shl-'+ownership.SERVICE_ID}, {**old,'scheduler_contract':None}):
        with pytest.raises(RuntimeError,match='unresolved'):
            ownership.terminal_evidence(invalid,new)
