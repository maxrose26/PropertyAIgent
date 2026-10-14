"""Disposable PostgreSQL acceptance only. Never accepts a production URL."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.db.models import Base, Council, Application
from app.pipeline.discovery_admission import admit_identity, UncertainDiscoveryCommit
from tests.test_discovery_admission import envelope


@pytest.fixture
def pg():
    raw = os.environ.get('DISCOVERY_TEST_POSTGRES_URL')
    if not raw:
        pytest.skip('requires disposable PostgreSQL CI service')
    url = make_url(raw)
    if (url.host != '127.0.0.1' or url.port != 5432 or
        url.database != 'stage4_discovery_test' or url.username != 'discovery_test'):
        raise ValueError('only fixed disposable test database admitted')
    engine = create_engine(url, connect_args={'connect_timeout': 3,
        'options': '-c statement_timeout=10000 -c lock_timeout=3000'}, pool_size=2, max_overflow=0, pool_timeout=3)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Council(code='bolton', name='Bolton', base_url='https://paplanning.bolton.gov.uk',
                      date_field_mode='received', doc_system='idox'))
        s.commit()
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_concurrent_overlap_creates_one_pending_identity(pg):
    barrier = Barrier(2, timeout=3)
    def one():
        barrier.wait()
        return admit_identity(pg, envelope())
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(one) for _ in range(2)]
        results = [f.result(timeout=15) for f in futures]
    assert sorted(r['outcome'] for r in results) == ['ALREADY_KNOWN', 'CREATED_PENDING']
    assert len({r['application_id'] for r in results}) == 1
    with Session(pg) as s:
        assert s.scalar(select(func.count()).select_from(Application)) == 1


def test_lost_acknowledgement_after_real_commit_stops(pg):
    original = Session.commit
    def lost(session):
        original(session)
        raise RuntimeError('simulated acknowledgement loss after actual commit')
    with patch.object(Session, 'commit', lost):
        with pytest.raises(UncertainDiscoveryCommit):
            admit_identity(pg, envelope())
    # Read-only reconciliation proves why blind retry was forbidden.
    with Session(pg) as s:
        assert s.scalar(select(func.count()).select_from(Application)) == 1
        assert s.scalar(select(Application)).unit_confirmation_status == 'discovery_pending'
