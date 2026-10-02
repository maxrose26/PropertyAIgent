"""Deterministic UI ownership tests; no GC, disposal or test-side session close."""
import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import sessionmaker
from app.db.models import Base, Council, Site, Application
from app.ui import common


@pytest.fixture
def owned(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path / 'lifecycle.sqlite'))
    Base.metadata.create_all(engine)
    sessions = []  # Strong references prevent GC from concealing missing cleanup.
    counts = {'out': 0, 'in': 0}
    event.listen(engine, 'checkout', lambda *a: counts.__setitem__('out', counts['out'] + 1))
    event.listen(engine, 'checkin', lambda *a: counts.__setitem__('in', counts['in'] + 1))
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    def acquire():
        session = factory()
        sessions.append(session)
        return session
    monkeypatch.setattr(common, 'get_session', acquire)
    return engine, sessions, counts


def released(owned):
    engine, sessions, counts = owned
    assert engine.pool.checkedout() == 0
    assert counts['out'] == counts['in']
    assert all(not s.in_transaction() for s in sessions)


def test_normal_and_independent_scopes(owned):
    engine, sessions, _ = owned
    for _ in range(20):
        with common.get_db() as (session, settings):
            session.execute(text('select 1'))
            assert engine.pool.checkedout() == 1
        released(owned)
    assert len({id(s) for s in sessions}) == 20


def test_settings_failure(owned, monkeypatch):
    def fail(session):
        session.execute(text('select 1'))
        raise ValueError('settings failure')
    monkeypatch.setattr(common, 'get_settings', fail)
    with pytest.raises(ValueError, match='settings failure'):
        with common.get_db():
            pytest.fail('must not enter body')
    released(owned)


def test_acquisition_failure(monkeypatch):
    def fail():
        raise ValueError('acquisition failure')
    monkeypatch.setattr(common, 'get_session', fail)
    with pytest.raises(ValueError, match='acquisition failure'):
        with common.get_db():
            pytest.fail('must not enter body')


@pytest.mark.parametrize('kind', ['page', 'stop', 'rerun'])
def test_exception_release(owned, kind):
    from streamlit.runtime.scriptrunner import StopException, RerunException
    from streamlit.runtime.scriptrunner_utils.script_requests import RerunData
    error = {'page': ValueError('page failure'), 'stop': StopException(),
             'rerun': RerunException(RerunData())}[kind]
    with pytest.raises(type(error)) as caught:
        with common.get_db() as (session, settings):
            session.execute(text('select 1'))
            raise error
    assert caught.value is error
    released(owned)


def test_explicit_commit_and_uncommitted_cleanup(owned):
    with common.get_db() as (session, settings):
        session.add(Council(code='committed', name='Committed', base_url='https://example.invalid', date_field_mode='received', doc_system='idox'))
        session.commit()
        session.add(Council(code='pending', name='Pending', base_url='https://example.invalid', date_field_mode='received', doc_system='idox'))
        session.flush()  # Prove a real pending database write is rolled back.
    released(owned)
    with owned[0].connect() as connection:
        assert connection.execute(select(Council.code)).scalars().all() == ['committed']
    released(owned)


def test_lazy_orm_access_inside_scope(owned):
    with common.get_db() as (session, settings):
        session.add(Council(code='fixture', name='Fixture', base_url='https://example.invalid', date_field_mode='received', doc_system='idox'))
        session.add(Site(id=1, council_code='fixture', canonical_address='Fixture', display_address='Fixture'))
        session.add(Application(council_code='fixture', reference='fixture', site_id=1))
        session.commit()
    released(owned)
    with common.get_db() as (session, settings):
        site = session.get(Site, 1)
        assert [a.reference for a in site.applications] == ['fixture']
    released(owned)
