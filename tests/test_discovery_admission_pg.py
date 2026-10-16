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


def test_bolton_initial_literal_real_shared_path_on_postgres(pg):
    from tests.test_discovery_initial_application_contract import assert_bolton_path
    assert_bolton_path(pg)


def test_bolton53_primary_discovery_initial_b2_disposable(pg):
    from tests.test_discovery_bolton53_admission import exercise
    exercise(pg)


def test_bolton53_primary_race_and_lost_commit(pg):
    from verification.discovery import bolton53_admission as a
    row=next(a.rows());barrier=Barrier(2,timeout=3)
    def one():
        barrier.wait();return admit_identity(pg,a.envelope(row))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=[f.result(timeout=15) for f in [pool.submit(one),pool.submit(one)]]
    assert sorted(x['outcome'] for x in results)==['ALREADY_KNOWN','CREATED_PENDING']
    row=list(a.rows())[1];original=Session.commit
    def lost(session):original(session);raise RuntimeError('synthetic lost commit')
    with patch.object(Session,'commit',lost):
        result=a.record(pg,row,retrieve=lambda _:pytest.fail('source after uncertainty'))
    assert result['identity']=='UNKNOWN_COMMIT' and result['transaction']=='UNCERTAIN_STOP_NO_RETRY'
    with Session(pg) as s:
        records=s.scalars(select(Application).where(Application.reference==row['reference'])).all()
        assert len(records)==1 and records[0].status is None


def test_bolton53_source_failure_after_identity_and_readback_uncertainty(pg):
    from verification.discovery import bolton53_admission as a
    from tests.test_discovery_bolton53_admission import synthetic
    row=next(a.rows())
    result=a.record(pg,row,retrieve=lambda _:(_ for _ in ()).throw(RuntimeError('synthetic source failure')))
    assert result['identity']=='CREATED_PENDING' and result['stop']
    with Session(pg) as s:assert s.get(Application,result['application_id']).status is None
    row=list(a.rows())[1]
    with patch.object(a,'readback',side_effect=RuntimeError('synthetic readback failure')):
        result=a.record(pg,row,retrieve=synthetic)
    assert result['facts']=='UNCERTAIN_COMMIT_OR_READBACK' and result['stop']
    with Session(pg) as s:assert s.get(Application,result['application_id']).status=='Deposited'


def test_bolton53_rollback_before_identity_commit(pg):
    from verification.discovery import bolton53_admission as a
    original=Session.execute
    def reject(session,statement,*args,**kwargs):
        if getattr(statement,'is_insert',False):raise RuntimeError('synthetic insertion rejection')
        return original(session,statement,*args,**kwargs)
    with patch.object(Session,'execute',reject):
        result=a.record(pg,next(a.rows()),retrieve=lambda _:pytest.fail('source'))
    assert result['identity']=='FAILED_OR_UNCERTAIN'
    with Session(pg) as s:assert s.scalar(select(func.count()).select_from(Application))==0


def test_selective5_actual_fixed_subset_on_disposable_postgres(pg):
    from verification.discovery import selective5 as chosen
    from tests.test_discovery_bolton53_admission import synthetic
    first=chosen.run(engine_factory=lambda:pg,reader=synthetic,checkpoint=lambda _:None,journal=lambda *_:None)
    assert first['stop'] is None and len(first['results'])==5
    assert [r['reference'] for r in first['results']]==['01768/26','01769/26','01827/26','DC/100094','DC/100393']
    assert all(r['facts']=='INITIAL_FACTS_VERIFIED' for r in first['results'][:3])
    assert all(r['transaction']=='NOT_STARTED' and r['identity']=='WITHHELD' for r in first['results'][3:])
    again=chosen.run(engine_factory=lambda:pg,reader=lambda _:pytest.fail('existing must not refetch'),checkpoint=lambda _:None,journal=lambda *_:None)
    assert all(r['identity']=='ALREADY_KNOWN' and r['facts']=='EXISTING_NOT_WRITTEN' for r in again['results'][:3])
    with Session(pg) as session:assert session.scalar(select(func.count()).select_from(Application))==3


def test_completion944_exact_readonly_query_and_rollback(pg):
    from verification.discovery.completion_comparison import identities
    from verification.discovery.r0_identity_comparison import query
    first=next(r for r in identities() if r['council_code']=='bolton')
    with Session(pg) as session:
        session.add(Application(council_code='bolton',reference=first['reference']))
        session.commit()
    with pg.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        audit={};result=query(connection,audit,exact_rows=identities(),output_bound=1000000)
        assert result['requested_identities']==944 and audit['read_only_confirmed'] is True
        assert result['production_writes']==0 and audit['transaction']=='READ_ONLY_ROLLED_BACK'
        assert sum(x['matching_rows_up_to_two'] for x in result['comparison'])==1
    with Session(pg) as session:assert session.scalar(select(func.count()).select_from(Application))==1


def test_narrow_oldham_actual_shared_coupled_readback(pg):
    from tests.test_discovery_narrow_continuation import exercise
    exercise(pg)


def test_narrow_oldham_concurrent_exact_identity(pg):
    from tests.test_discovery_narrow_continuation import seed
    from verification.discovery.narrow_oldham_record import envelope as original,rows
    seed(pg);barrier=Barrier(2,timeout=3);row=next(rows())
    def one():barrier.wait();return admit_identity(pg,original(row))
    with ThreadPoolExecutor(max_workers=2) as workers:
        results=[f.result(timeout=15) for f in [workers.submit(one),workers.submit(one)]]
    assert sorted(r['outcome'] for r in results)==['ALREADY_KNOWN','CREATED_PENDING']
    assert len({r['application_id'] for r in results})==1


def test_narrow_oldham_uncertain_readback_stops_following_record(pg):
    from tests.test_discovery_narrow_continuation import seed,synthetic
    from verification.discovery import narrow_oldham as o,narrow_oldham_record as record
    seed(pg);calls=[]
    def factory():calls.append(1);return pg
    with patch.object(record,'readback',side_effect=RuntimeError('simulated readback loss')):
        out=o.run(engine_factory=factory,reader=synthetic,checkpoint=lambda _:None,journal=lambda *_:None)
    assert len(calls)==1 and out['stop']
    assert out['results'][0]['facts']=='UNCERTAIN_COMMIT_OR_READBACK'
    with Session(pg) as session:
        apps=session.scalars(select(Application).where(Application.council_code=='oldham')).all()
        assert len(apps)==1 and apps[0].status is not None  # actual commit despite failed readback


def test_narrow_delta3_verified_read_only_query(pg):
    from verification.discovery.narrow_comparison import identities
    from verification.discovery.r0_identity_comparison import query
    rows=identities()
    with pg.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        result=query(connection,exact_rows=rows)
    assert result['transaction']=='READ_ONLY_ROLLED_BACK' and len(result['comparison'])==3
    assert all(r['outcome']=='ABSENT' for r in result['comparison'])
