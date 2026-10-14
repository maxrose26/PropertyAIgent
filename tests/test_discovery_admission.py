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


def test_exact_trigger_reuses_transaction_without_enumeration_claim(engine):
    from app.pipeline.discovery_contract import ExactTriggerEvidence, completed_through
    e = envelope()
    e = replace(e, window=replace(e.window, source_contract=None, applied_evidence=None))
    trigger = ExactTriggerEvidence('bolton', 'TEST/26',
        'https://bolton.moderngov.co.uk/documents/s1/report.pdf', ('TEST/26',), 'b'*64)
    first = admit_identity(engine, e, trigger=trigger)
    second = admit_identity(engine, e, trigger=trigger)
    assert first['outcome'] == 'CREATED_PENDING'
    assert second['outcome'] == 'ALREADY_KNOWN'
    assert first['application_id'] == second['application_id']
    assert first['trigger']['enumeration_complete'] is False
    assert first['trigger']['coverage_watermark_advanced'] is False
    prior = date(2026, 9, 30)
    assert completed_through(prior, [e.window], council='bolton', date_semantics='RECEIVED') == prior
    with Session(engine) as s:
        row = s.scalar(select(Application))
        assert row.site_id is None and row.status is None and row.proposal is None


def test_exact_trigger_mismatch_and_untrusted_shape_fail_before_write(engine):
    from app.pipeline.discovery_contract import ExactTriggerEvidence
    t = ExactTriggerEvidence('bolton', 'OTHER/26',
        'https://bolton.moderngov.co.uk/documents/s1/report.pdf', ('OTHER/26',), 'b'*64)
    with pytest.raises(ValueError): admit_identity(engine, envelope(), trigger=t)
    with pytest.raises(ValueError): admit_identity(engine, envelope(), trigger=SimpleNamespace())
    with pytest.raises(ValueError): replace(t, displayed_references=('OTHER/26', 'TEST/26'))
    with pytest.raises(ValueError): replace(t, source_url='https://example.com/report.pdf')
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(Application)) == 0


def test_exact_trigger_uncertain_commit_is_not_retried(engine):
    from app.pipeline.discovery_contract import ExactTriggerEvidence
    t = ExactTriggerEvidence('bolton', 'TEST/26',
        'https://bolton.moderngov.co.uk/documents/s1/report.pdf', ('TEST/26',), 'b'*64)
    with patch.object(Session, 'commit', side_effect=RuntimeError('lost acknowledgement')) as commit:
        with pytest.raises(UncertainDiscoveryCommit): admit_identity(engine, envelope(), trigger=t)
        assert commit.call_count == 1


@pytest.mark.parametrize('council,status,host', [('manchester','Under Consideration','arcusbe.manchester.gov.uk'),('salford','Under Consultation','salfordcitycouncil.my.site.com')])
def test_initial_status_only_b2_never_promotes_or_verifies_missing_fields(engine,council,status,host):
    import json
    from app.pipeline.status_verification import verify_application_status,current_verified_planning_field
    with Session(engine) as s:
        s.add(Council(code=council,name=council,base_url='https://'+host+'/pr',date_field_mode='validated',doc_system='arcus'))
        app=Application(council_code=council,reference='R',unit_confirmation_status=PENDING)
        s.add(app);s.commit()
        result=SimpleNamespace(reference='R',summary_url='https://'+host+'/pr/s/detail/a1DSl000007GOGYMA4?c__r=Arcus_BE_Public_Register',body_sha256='a'*64,
            verification_scope='INITIAL_STATUS_ONLY',fields={'Reference':'R','Status':status},
            field_evidence={'reference':{'state':'PRESENT_VALUE','value':'R'},'status':{'state':'PRESENT_VALUE','value':status},
                'decision':{'state':'NOT_PRESENT','value':None},'decision_date':{'state':'PRESENT_BLANK','value':''}})
        cfg=SimpleNamespace(code=council,base_url='https://'+host+'/pr',doc_system='arcus')
        outcome=verify_application_status(s,None,cfg,app,evidence_loader=lambda prior:result)
        assert outcome.outcome=='field_level_verified' and not outcome.material_change_reasons
        s.refresh(app)
        assert app.status==status and app.decision is None and app.decision_issued_date is None and app.status_verified_at is None
        assert app.unit_confirmation_status==PENDING and app.site_id is None and not app.evidence_refresh_required
        assert current_verified_planning_field(app,'status')
        assert current_verified_planning_field(app,'decision_date') is None
        assert json.loads(app.planning_field_verification)['decision']['verified_at'] is None
        assert verify_application_status(s,None,cfg,app,evidence_loader=lambda prior:result).outcome=='fetch_failed'
        app.status='Changed'
        assert current_verified_planning_field(app,'status') is None
