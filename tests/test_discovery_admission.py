from dataclasses import replace
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from app.db.models import Base, Council, Application, Site
from app.pipeline.discovery_contract import DiscoveryEnvelope, WindowEvidence
from app.pipeline.discovery_admission import admit_identity, PENDING, UncertainDiscoveryCommit


def envelope():
    w = WindowEvidence('bolton', 'offline', date(2026, 10, 1), date(2026, 10, 7),
        date(2026, 10, 1), date(2026, 10, 7), 'RECEIVED', 'offline-fixture',
        'date-labels', 'terminal-count', 1, 1, 2, 2000, 1)
    return DiscoveryEnvelope('bolton', 'TEST/26',
        'https://paplanning.bolton.gov.uk/online-applications/applicationDetails.do?keyVal=X',
        'X', datetime(2026, 10, 14, tzinfo=timezone.utc), w, ('TEST/26',), 'a'*64, ())


@pytest.fixture
def engine():
    e = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(e)
    with Session(e) as s:
        s.add(Council(code='bolton', name='Bolton', base_url='https://paplanning.bolton.gov.uk',
                      date_field_mode='received', doc_system='idox'))
        s.commit()
    yield e
    e.dispose()


def test_overlap_is_identity_only_idempotent(engine):
    a = admit_identity(engine, envelope())
    b = admit_identity(engine, envelope())
    assert a['outcome'] == 'CREATED_PENDING' and b['outcome'] == 'ALREADY_KNOWN'
    assert a['application_id'] == b['application_id']
    with Session(engine) as s:
        rows = s.scalars(select(Application)).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.unit_confirmation_status == PENDING
        assert all(getattr(row, k) is None for k in
            ('site_id', 'proposal', 'address', 'status', 'decision', 'decision_issued_date', 'estimated_unit_count'))
        assert s.scalar(select(func.count()).select_from(Site)) == 0


def test_incomplete_and_wrong_origin_never_insert(engine):
    e = envelope()
    with pytest.raises(ValueError): admit_identity(engine, replace(e, window=replace(e.window, capped=True)))
    with pytest.raises(ValueError): replace(e, source_url='https://example.com/application')
    with Session(engine) as s: assert s.scalar(select(func.count()).select_from(Application)) == 0


def test_existing_facts_unchanged(engine):
    with Session(engine) as s:
        s.add(Application(council_code='bolton', reference='TEST/26', status='Granted', unit_confirmation_status='confirmed_qualifying'))
        s.commit()
    assert admit_identity(engine, envelope())['outcome'] == 'ALREADY_KNOWN'
    with Session(engine) as s:
        row = s.scalar(select(Application))
        assert row.status == 'Granted' and row.unit_confirmation_status == 'confirmed_qualifying'


def test_commit_uncertainty_has_no_retry(engine):
    with patch.object(Session, 'commit', side_effect=RuntimeError('lost acknowledgement')) as commit:
        with pytest.raises(UncertainDiscoveryCommit): admit_identity(engine, envelope())
        assert commit.call_count == 1


def test_pending_is_not_promoted_by_legacy_paths(engine):
    from app.pipeline.run_weekly import _upsert_scraped_application, stage_link_sites, UNIT_GATE_PASSED
    from app.pipeline.site_linking import link_application_to_site
    admit_identity(engine, envelope())
    with Session(engine) as s:
        row = _upsert_scraped_application(s, SimpleNamespace(code='bolton'),
            SimpleNamespace(reference='TEST/26'), None, unit_confirmation_status='confirmed_qualifying')
        assert row.unit_confirmation_status == PENDING
        link_application_to_site(s, row)
        assert row.site_id is None
        assert stage_link_sites(s, SimpleNamespace(code='bolton')) == 0
        assert s.scalars(select(Application).where(UNIT_GATE_PASSED)).all() == []


def test_pending_b2_writes_supported_facts_without_promotion(engine):
    from app.config import get_council
    from app.pipeline.status_verification import verify_application_status, OUTCOME_VERIFIED_CHANGED
    admit_identity(engine, envelope())
    result = SimpleNamespace(reference='TEST/26',
        fields={'Reference': 'TEST/26', 'Status': 'Decided', 'Decision': 'Approved',
                'Decision Issued Date': '12/10/2026'},
        summary_url=envelope().source_url, estimated_unit_count=None)
    with Session(engine) as s:
        row = s.scalar(select(Application))
        outcome = verify_application_status(s, None, get_council('bolton'), row,
                                             evidence_loader=lambda prior: result)
        assert outcome.outcome == OUTCOME_VERIFIED_CHANGED
        s.refresh(row)
        assert row.decision == 'Approved' and row.status == 'Decided'
        assert row.status_verified_at is not None
        assert row.unit_confirmation_status == PENDING and row.site_id is None


def test_pending_legacy_b2_fetch_cannot_advance_watermark(engine):
    from app.config import get_council
    from app.pipeline.status_verification import verify_application_status, OUTCOME_FETCH_FAILED
    admit_identity(engine, envelope())
    with Session(engine) as s:
        row = s.scalar(select(Application))
        with patch('app.scrapers.idox_portal.fetch_application_by_reference') as fetch:
            result = verify_application_status(s, None, get_council('bolton'), row)
            assert result.outcome == OUTCOME_FETCH_FAILED
            fetch.assert_not_called()
        s.refresh(row)
        assert row.status_verified_at is None and row.status is None


@pytest.mark.parametrize('column,value', [('status',"'unexpected'"),('estimated_unit_count','99'),('opportunity_classification',"'promoted'")])
def test_identity_readback_rejects_unexpected_factual_side_effect(engine,column,value):
    from sqlalchemy import text
    # A DB-side effect must not be hidden by an identity-only readback.
    with engine.begin() as connection:
        connection.execute(text(f"""CREATE TRIGGER unexpected_fact AFTER INSERT ON applications
          BEGIN UPDATE applications SET {column}={value} WHERE id=NEW.id; END"""))
    with pytest.raises(ValueError,match='isolation'):
        admit_identity(engine,envelope())
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Application))==0
