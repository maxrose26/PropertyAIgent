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


def test_fixed_committee_shared_admission_and_b2_on_postgres(pg):
    from tests.test_discovery_committee_exact import seed, synthetic_source
    from verification.discovery.committee_exact import run
    seed(pg)
    first=run(pg,'disposable-pg',synthetic_source)
    second=run(pg,'disposable-pg',lambda *_: pytest.fail('known identity must not refetch'))
    assert all(r['transaction']=='COMMIT_READBACK_CONFIRMED' for r in first)
    assert all(r['admission']['outcome']=='ALREADY_KNOWN' for r in second)
    assert [r['verification_scope'] for r in first]==['INITIAL_STATUS_ONLY','INITIAL_STATUS_ONLY','COUPLED']
    with Session(pg) as session:
        assert session.scalar(select(func.count()).select_from(Application))==3


def test_qualified_material_three_shared_caller_on_postgres(pg):
    from tests.test_discovery_material_admission import seed_material,source
    from verification.discovery.material_admission import execute
    seed_material(pg)
    first=execute(pg,'material-pg',retrieve_evidence=source)
    assert [r['verification_scope'] for r in first]==['COUPLED','INITIAL_STATUS_ONLY','COUPLED']
    assert first[2]['readback']['decision_issued_date']=='2026-07-28'
    again=execute(pg,'overlap',retrieve_evidence=lambda *_:pytest.fail('duplicate source'))
    assert all(r['outcome']=='ALREADY_EXISTS_AT_EXECUTION' for r in again)
    with Session(pg) as session:
        assert session.scalar(select(func.count()).select_from(Application))==3
        assert all(a.site_id is None for a in session.scalars(select(Application)))


def test_fixed80_identity_comparison_real_read_only_transaction(pg):
    """Existing disposable-only fixture, production route never supplied."""
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from verification.discovery.r0_identity_comparison import identities, query
    identity = identities()[0]
    assert identity['council_code'] == 'bolton'
    with Session(pg) as session:
        session.add(Application(**identity)); session.commit()
        before = session.scalar(select(func.count()).select_from(Application))
    with pg.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        result = query(connection)
        assert result['transaction'] == 'READ_ONLY_ROLLED_BACK'
        assert sum(x['outcome']=='ONE_MATCH' for x in result['comparison']) == 1
        assert sum(x['outcome']=='ABSENT' for x in result['comparison']) == 79
        connection.exec_driver_sql('BEGIN READ ONLY')
        try:
            with pytest.raises(DBAPIError):
                connection.execute(text("INSERT INTO public.applications (council_code,reference) VALUES ('bolton','DISPOSABLE_RO_WRITE_DENIED')"))
        finally:
            connection.exec_driver_sql('ROLLBACK')
    with Session(pg) as session:
        assert session.scalar(select(func.count()).select_from(Application)) == before
