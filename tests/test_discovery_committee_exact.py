"""Fixed exact-trigger caller acceptance; no source access or production URL."""
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from tests.test_discovery_admission import engine
from app.db.models import Council, Application
from verification.discovery.committee_exact import targets, envelope, run, admission_environment, checked_engine


def synthetic_source(row, application_id):
    final = row['reference']=='143413/FO/2025'
    status='Final' if final else 'Under Consultation' if row['council']=='salford' else 'Under Consideration'
    fields={'Reference':row['reference'],'Status':status,'Decision':'Approve' if final else None,
            'Decision Issued Date':'2026-09-28' if final else None}
    states={k:'PRESENT_VALUE' if final or k in ('reference','status') else 'NOT_PRESENT'
            for k in ('reference','status','decision','decision_date')}
    obs=SimpleNamespace(application_id=application_id,reference=row['reference'],source_url=row['source_url'],
        fields=fields,field_states=states,body_sha256='a'*64,literal_fields=fields,
        literal_verified=True,b2_eligible=True,verification_scope='COUPLED' if final else 'INITIAL_STATUS_ONLY',
        field_evidence={k:{'state':states[k],'value':fields[label]} for k,label in
            {'reference':'Reference','status':'Status','decision':'Decision','decision_date':'Decision Issued Date'}.items()})
    return {'observation':obs,'audit':{'cleanup_state':'CLOSED','budget_state':'WITHIN_LIMITS'},'failure':None}


def seed(engine):
    with Session(engine) as s:
        for code,host in [('manchester','arcusbe.manchester.gov.uk'),('salford','salfordcitycouncil.my.site.com')]:
            s.add(Council(code=code,name=code,base_url='https://'+host+'/pr',date_field_mode='validated',doc_system='arcus'))
        s.commit()


def test_exact_cohort_and_no_enumeration_claim():
    rows=targets()
    assert len(rows)==3 and all('trafford' not in r['council'] and 'stockport' not in r['council'] for r in rows)
    assert all(envelope(r,'offline').window.outcome.value=='INCOMPLETE' for r in rows)
    assert not admission_environment('a'*40,'AUTHORISE_THREE_COMMITTEE_IDENTITIES_AND_B2_ONCE')
    with pytest.raises(ValueError): checked_engine('postgresql+psycopg://x:y@127.0.0.1/other')


def test_transport_prerequisite_has_no_production_credentials():
    import yaml
    from pathlib import Path
    from verification.discovery.committee_exact import WORKFLOW
    workflow=yaml.load(Path(WORKFLOW).read_text(),Loader=yaml.BaseLoader)
    assert set(workflow['on'])=={'workflow_dispatch'}
    transport=workflow['jobs']['transport'];admission=workflow['jobs']['admission']
    assert 'secrets.' not in str(transport) and 'environment' not in transport
    assert '--transport-only' in str(transport)
    assert admission['needs']=='transport'
    assert admission['environment']=='stage4-production-canary'
    assert str(admission).count('secrets.')==1
    assert all(j['timeout-minutes']=='8' for j in workflow['jobs'].values())


def test_transport_failure_preserves_progress_and_never_uses_database():
    from verification.discovery.committee_exact import validate_sources
    progress=[]
    def bad(row,application_id):
        assert application_id is None
        return {'observation':None,'failure':'PARSER_FAILURE',
                'audit':{'cleanup_state':'CLOSED','budget_state':'WITHIN_LIMITS'}}
    with pytest.raises(RuntimeError,match='transport-only qualification failed'):
        validate_sources(bad,progress)
    assert len(progress)==1 and not progress[0]['qualified']


def test_shared_caller_identity_and_b2_idempotency(engine):
    seed(engine)
    first=run(engine,'offline',source_retrieve=synthetic_source)
    second=run(engine,'offline',source_retrieve=lambda *_:pytest.fail('already known source call'))
    assert len(first)==len(second)==3
    assert all(r['transaction']=='COMMIT_READBACK_CONFIRMED' for r in first)
    assert all(r['admission']['outcome']=='ALREADY_KNOWN' for r in second)
    assert [r['verification_scope'] for r in first]==['INITIAL_STATUS_ONLY','INITIAL_STATUS_ONLY','COUPLED']
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(Application))==3
        assert all(a.site_id is None and a.unit_confirmation_status=='discovery_pending' for a in s.scalars(select(Application)))


def test_partial_progress_survives_uncertain_identity_commit(engine):
    from app.pipeline.discovery_admission import admit_identity
    seed(engine)
    from app.pipeline.discovery_admission import UncertainDiscoveryCommit
    calls=[];progress=[]
    def controlled(*args,**kwargs):
        calls.append(1)
        if len(calls)==2:raise UncertainDiscoveryCommit('synthetic acknowledgement loss')
        return admit_identity(*args,**kwargs)
    with patch('verification.discovery.committee_exact.admit_identity',side_effect=controlled):
        with pytest.raises(UncertainDiscoveryCommit):run(engine,'offline',synthetic_source,progress)
    assert len(calls)==2 and len(progress)==2
    assert progress[0]['transaction']=='COMMIT_READBACK_CONFIRMED'
    assert progress[1]['transaction']=='IDENTITY_ADMISSION_STARTED_UNCONFIRMED'


@pytest.mark.parametrize('failure,cleanup,budget',[
    ('CLEANUP_FAILURE','FAILED','WITHIN_LIMITS'),
    ('ACCOUNTING_FAILURE','CLOSED','EXHAUSTED'),
    ('SCOPE_ESCAPE','CLOSED','WITHIN_LIMITS'),
])
def test_failed_cleanup_stops_before_next_identity(engine,failure,cleanup,budget):
    seed(engine)
    progress=[]
    def unclosed(row, application_id):
        return {'observation':None,'audit':{'cleanup_state':cleanup,'budget_state':budget},
                'failure':failure}
    with pytest.raises(RuntimeError,match='source supervision unresolved'):
        run(engine,'offline',unclosed,progress)
    assert len(progress)==1 and progress[0]['transaction']=='COMMIT_READBACK_CONFIRMED'
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Application))==1
        app=session.scalar(select(Application))
        assert app.status is None and app.status_verified_at is None
