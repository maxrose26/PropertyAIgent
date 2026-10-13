import copy
import datetime as dt
from unittest.mock import patch
import pytest
from sqlalchemy.orm import Session
from app.db.models import Application
from verification.direct_reference import batch as b,batch_transaction as t,batch_production as p
from verification.direct_reference.fixtures import Session as Source,summary
from tests.test_stage4_batch import seed,LIMITS,SHA


def run(engine,**kw):
    row=b.manifest()[0]['identity']
    return t.run_transaction(engine,row,lambda:Source(summary(row['reference'],status='Awaiting decision',omit=('Decision','Decision Issued Date'))),LIMITS,**kw)

def test_exact_pending_status_stamp_only(session):
    e=session.get_bind();seed(e);a=run(e,allow_status_only=True)
    assert a['b2_outcome']=='VERIFIED_STATUS_ONLY' and a['transaction']=='COMMITTED' and a['cleanup']=='CLOSED'
    assert a['source']['semantic_qualification']=='UNKNOWN_UNMAPPED' # coupled decision state remains unknown
    assert a['source']['field_states']['decision']==a['source']['field_states']['decision_date']=='NOT_PRESENT'
    assert a['before']['facts']['status_verified_at'] is None and a['after']['facts']['status_verified_at'] is not None
    assert {k:v for k,v in a['before']['facts'].items() if k!='status_verified_at'}=={k:v for k,v in a['after']['facts'].items() if k!='status_verified_at'}
    assert a['before']['events']==a['after']['events']==[]
    b.validate_record(a,b.manifest()[0]['identity'])
    # Legacy registered contexts cannot silently accept the new scope.
    calls=[]
    def execute(*args):calls.append(1);return a
    audit=b.run(SHA,'123',execute,clock=lambda:300 if calls else 0)
    with pytest.raises(ValueError,match='STATUS_ONLY_NOT_ADMITTED'):p.validate(audit,SHA,'123')


def test_default_retains_complete_contract(session):
    e=session.get_bind();seed(e);a=run(e)
    assert a['transaction']=='NOT_COMMITTED' and a['b2_outcome']=='PARTIAL_RETRIEVAL' and a['before']==a['after']

@pytest.mark.parametrize('field,value',[('status','Registered'),('status','Decided'),('decision','Granted'),('decision',''),('decision_issued_date','2026-09-25'),('decision_issued_date','')])
def test_prior_guard_no_absence_inference(session,field,value):
    e=session.get_bind();seed(e)
    with Session(e) as s:
        app=s.get(Application,b.manifest()[0]['identity']['application_id']);setattr(app,field,value);s.commit()
    a=run(e,allow_status_only=True)
    if value=='':
        # Existing closed snapshot refuses empty-string facts: never manufacture
        # a safe readback or successful status stamp from an unauditable prior.
        assert a['transaction']=='UNKNOWN' and a['disposition']=='UNCERTAIN'
    else:assert a['transaction']=='NOT_COMMITTED' and a['b2_outcome']=='PARTIAL_RETRIEVAL' and a['before']==a['after']
    assert a['statements']['writes']==0

@pytest.mark.parametrize('status',['Registered','Deposited','Unknown','Awaiting Decision','Pending','Decided'])
def test_no_new_status_mapping(session,status):
    e=session.get_bind();seed(e);row=b.manifest()[0]['identity']
    a=t.run_transaction(e,row,lambda:Source(summary(row['reference'],status=status,omit=('Decision','Decision Issued Date'))),LIMITS,allow_status_only=True)
    assert a['transaction']=='NOT_COMMITTED' and a['before']==a['after']


def test_source_blank_not_omitted_status_only(session):
    e=session.get_bind();seed(e);row=b.manifest()[0]['identity']
    a=t.run_transaction(e,row,lambda:Source(summary(row['reference'],status='Awaiting decision',decision='',date='')),LIMITS,allow_status_only=True)
    assert a['b2_outcome']!='VERIFIED_STATUS_ONLY'


def test_stale_status_only_response_never_certifies_concurrent_facts(session):
    e=session.get_bind();seed(e);row=b.manifest()[0]['identity']
    def factory():
        with Session(e) as other:
            app=other.get(Application,row['application_id']);app.decision='Granted';app.status='Decided';app.decision_issued_date='2026-09-25';other.commit()
        return Source(summary(row['reference'],status='Awaiting decision',omit=('Decision','Decision Issued Date')))
    a=t.run_transaction(e,row,factory,LIMITS,allow_status_only=True)
    assert a['b2_outcome']=='STALE_RESPONSE' and a['transaction']=='UNKNOWN' and a['disposition']=='UNCERTAIN'


def test_rollback_and_lost_ack_status_only(session,monkeypatch):
    e=session.get_bind();seed(e);original=Session.commit
    def rollback(s):raise RuntimeError('synthetic failure')
    monkeypatch.setattr(Session,'commit',rollback)
    a=run(e,allow_status_only=True);assert a['transaction']=='NOT_COMMITTED' and a['after']==a['before'] and a['disposition']=='SAFETY_STOP'
    def lost(s):original(s);raise RuntimeError('synthetic lost ack')
    monkeypatch.setattr(Session,'commit',lost)
    a=run(e,allow_status_only=True);assert a['transaction']=='COMMITTED' and a['expected']==a['after'] and a['b2_outcome']=='PERSISTENCE_FAILED'


def test_later_complete_decision_uses_existing_material_consequences(session):
    e=session.get_bind();seed(e);first=run(e,allow_status_only=True);row=b.manifest()[0]['identity']
    a=t.run_transaction(e,row,lambda:Source(summary(row['reference'],status='Decided',decision='Refuse Permission',date='Fri 25 Sep 2026')),LIMITS,allow_status_only=True)
    assert a['transaction']=='COMMITTED' and a['b2_outcome']=='VERIFIED_MATERIAL_CHANGE'
    assert a['after']['facts']['evidence_refresh_required'] and a['after']['events'][0]['event_type']=='decision_refused'
    assert dt.datetime.fromisoformat(a['after']['facts']['status_verified_at'])>dt.datetime.fromisoformat(first['after']['facts']['status_verified_at'])


def test_consumer_status_scope_date_unavailable():
    from app.reporting.planning_freshness import present_planning_freshness,planning_freshness_report_columns
    from types import SimpleNamespace
    now=dt.datetime(2026,10,13,tzinfo=dt.timezone.utc)
    app=SimpleNamespace(status='Awaiting decision',decision=None,decision_issued_date=None,status_verified_at=now,reference='TEST',summary_url='https://example.invalid/a')
    f=present_planning_freshness(app,now=now)
    assert f.planning_state=='not_yet_decided' and f.source_fact_date is None
    assert 'decision and decision date remain unverified' in f.qualification
    columns=planning_freshness_report_columns([('Planning','TEST',f)])
    assert columns['Planning Decision Date']=='TEST: Not available' and 'status only' in columns['Planning Qualification']
