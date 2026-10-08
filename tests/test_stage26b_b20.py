"""Source-qualified dated facts plus explicitly synthetic failures. No council calls."""
import datetime as dt
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import requests
from sqlalchemy import select, event
from app.db.models import Application, ApplicationLifecycleEvent
from app.pipeline.status_verification import verify_application_status, VerificationOutcome
from app.pipeline.lifecycle_events import LifecycleEventStats
from app.pipeline.material_change import MaterialChangeStats
from app.reporting.planning_freshness import present_planning_freshness
from tests.test_planning_status_verification import _add_application, _council_config, _scraped

OLD=dt.datetime(2026,9,18,5,20,51,tzinfo=dt.timezone.utc)
NOW=dt.datetime(2026,10,8,12,tzinfo=dt.timezone.utc)


def app(session, **kw):
    return _add_application(session, reference=kw.pop('reference','A/1'), status=kw.pop('status','Awaiting decision'),
                            status_verified_at=OLD, **kw)


def execute(session, a, result=None, error=None):
    with patch('app.scrapers.idox_portal.fetch_application_by_reference',return_value=result,side_effect=error):
        return verify_application_status(session,MagicMock(),_council_config(),a)


def snapshot(a):
    return (a.status,a.decision,a.decision_issued_date,a.status_verified_at.replace(tzinfo=dt.timezone.utc) if a.status_verified_at else None,a.evidence_refresh_required)


def test_qualified_fixture_provenance():
    data=json.loads(Path('tests/fixtures/stage26b/b20/freshness-cases.json').read_text())
    assert len(data['cases'])==2
    assert data['cases'][0]['historical_cause']=='UNRESOLVED'
    assert all(len(c['source_snapshot_sha256'])==64 for c in data['cases'])
    assert data['unverified_categories']


@pytest.mark.parametrize('name',['Failsworth','Southlink'])
def test_retained_fact_prospective_verification(session,name):
    c=next(c for c in json.loads(Path('tests/fixtures/stage26b/b20/freshness-cases.json').read_text())['cases'] if c['name']==name)
    a=app(session,reference=c['reference']);result=_scraped(a.reference,status='Decided' if c['expected_decision'] else 'Awaiting decision',decision=c['expected_decision'])
    if c['expected_source_date']:result.fields['Decision Issued Date']=c['expected_source_date']
    commits=[]
    event.listen(session,'after_commit',lambda _:commits.append(1))
    out=execute(session,a,result)
    assert len(commits)==1
    assert a.decision==c['expected_decision']
    assert a.decision_issued_date==c['expected_source_date']
    assert out.outcome==('verified_changed' if name=='Failsworth' else 'verified_unchanged')
    assert a.status_verified_at>OLD
    events=session.scalars(select(ApplicationLifecycleEvent)).all()
    assert len(events)==(1 if name=='Failsworth' else 0)
    assert a.evidence_refresh_required==(name=='Failsworth')


@pytest.mark.parametrize('error',[requests.exceptions.Timeout(),requests.exceptions.HTTPError('429'),requests.exceptions.ConnectionError(),ValueError('synthetic parse error')])
def test_failed_retrieval_preserves_all_accepted_facts(session,error):
    a=app(session,decision='Granted',status='Decided',decision_issued_date='2026-09-01');before=snapshot(a)
    out=execute(session,a,error=error)
    assert out.outcome in {'fetch_failed','portal_unavailable'}
    assert snapshot(a)==before
    assert session.scalars(select(ApplicationLifecycleEvent)).all()==[]


@pytest.mark.parametrize('case',['absent','wrong_reference','malformed','empty','garbage','conflict','committee','terminal_regression'])
def test_inadequate_or_conflicting_source_never_stamps(session,case):
    a=app(session,decision='Refused' if case=='terminal_regression' else None,status='Decided' if case=='terminal_regression' else 'Awaiting decision');before=snapshot(a)
    r=_scraped('A/1',status='Awaiting decision')
    if case=='absent':r=None
    if case=='wrong_reference':r.reference='A/2'
    if case=='malformed':r.fields={'Status':['bad']}
    if case=='empty':r.fields={}
    if case=='garbage':r.fields={'Status':'totally malformed content'}
    if case=='conflict':r.fields={'Status':'Refused','Decision':'Granted'}
    if case=='committee':r.fields={'Status':'Committee resolution','Decision':'Approved subject to S106'}
    out=execute(session,a,r)
    assert out.outcome in {'application_not_found','fetch_failed','conflicting_source'}
    assert snapshot(a)==before
    assert not session.scalars(select(ApplicationLifecycleEvent)).all()


@pytest.mark.parametrize('decision',['Granted','Refused','Withdrawn'])
def test_synthetic_terminal_changes_are_coherent(session,decision):
    a=app(session);r=_scraped('A/1',status='Decided',decision=decision);r.fields['Decision Issued Date']='2026-09-25'
    assert execute(session,a,r).outcome=='verified_changed'
    assert a.decision==decision and a.decision_issued_date=='2026-09-25'
    assert len(session.scalars(select(ApplicationLifecycleEvent)).all())==1


@pytest.mark.parametrize('point',['upsert','flush','commit','interrupt'])
def test_atomicity_failure_injection_rolls_back_facts_watermark_events_and_stats(session,monkeypatch,point):
    import app.pipeline.run_weekly as weekly
    a=app(session);before=snapshot(a);events=LifecycleEventStats();stats=MaterialChangeStats()
    if point=='upsert':
        original=weekly._upsert_scraped_application
        def fail(*args,**kwargs):
            original(*args,**kwargs)
            raise RuntimeError('after fact/event assignment')
        monkeypatch.setattr(weekly,'_upsert_scraped_application',fail)
    elif point=='flush':
        def fail(*args):raise RuntimeError('flush failed')
        event.listen(session,'before_flush',fail)
    else:
        def fail():raise KeyboardInterrupt() if point=='interrupt' else RuntimeError('commit failed')
        monkeypatch.setattr(session,'commit',fail)
    with patch('app.scrapers.idox_portal.fetch_application_by_reference',return_value=_scraped('A/1',status='Decided',decision='Refused')):
        if point=='interrupt':
            with pytest.raises(KeyboardInterrupt):verify_application_status(session,MagicMock(),_council_config(),a,material_change_stats=stats,lifecycle_event_stats=events)
        else:
            assert verify_application_status(session,MagicMock(),_council_config(),a,material_change_stats=stats,lifecycle_event_stats=events).outcome=='persistence_failed'
    assert snapshot(a)==before
    assert session.scalars(select(ApplicationLifecycleEvent)).all()==[]
    assert events.written==0 and stats.compared==0


def test_old_response_rejected_after_newer_success(session):
    a=app(session)
    def old_response(*_):
        with patch('app.scrapers.idox_portal.fetch_application_by_reference',return_value=_scraped('A/1',status='Decided',decision='Refused')):
            assert verify_application_status(session,MagicMock(),_council_config(),a).outcome=='verified_changed'
        return _scraped('A/1',status='Decided',decision='Granted')
    with patch('app.scrapers.idox_portal.fetch_application_by_reference',side_effect=old_response):
        assert verify_application_status(session,MagicMock(),_council_config(),a).outcome=='stale_response'
    assert a.decision=='Refused'
    assert len(session.scalars(select(ApplicationLifecycleEvent)).all())==1


def test_changed_decision_does_not_borrow_old_date(session):
    a=app(session,status='Decided',decision='Granted',decision_issued_date='2025-01-01')
    execute(session,a,_scraped('A/1',status='Decided',decision='Refused'))
    assert a.decision_issued_date is None


def test_presentation_distinguishes_dates_scope_failures_and_policy(session):
    a=app(session,decision_issued_date='2026-09-25');v=present_planning_freshness(a,now=NOW,cadence_days=14)
    assert v.source_fact_date=='2026-09-25' and v.freshness=='requires_refresh'
    fail=VerificationOutcome('fetch_failed','A/1')
    v=present_planning_freshness(a,now=NOW,current_outcome=fail,attempted_at=NOW)
    assert v.freshness=='currently_unverifiable' and v.attempt_visibility=='request_local_only'
    v=present_planning_freshness(a,now=NOW,current_outcome=fail,attempted_at=OLD-dt.timedelta(days=1))
    assert v.freshness=='verified_as_of'
    with pytest.raises(ValueError):present_planning_freshness(a,now=NOW,current_outcome=VerificationOutcome('fetch_failed','OTHER'))
    a.decision_issued_date='bad';a.summary_url='javascript:bad'
    v=present_planning_freshness(a,now=NOW)
    assert v.source_fact_date is None and v.source_url is None


def test_commit_acknowledgement_loss_retry_does_not_duplicate_events(session,monkeypatch):
    a=app(session);original=session.commit
    def lost():original();raise RuntimeError('acknowledgement lost')
    monkeypatch.setattr(session,'commit',lost)
    assert execute(session,a,_scraped('A/1',status='Decided',decision='Refused')).outcome=='persistence_failed'
    monkeypatch.setattr(session,'commit',original)
    assert execute(session,a,_scraped('A/1',status='Decided',decision='Refused')).outcome=='verified_unchanged'
    assert len(session.scalars(select(ApplicationLifecycleEvent)).all())==1


@pytest.mark.parametrize('status,decision',[('Decided','banana'),('Awaiting decision','Granted'),('Withdrawn','Granted'),('Appeal pending',None)])
def test_unsupported_or_conflicting_status_combinations_do_not_stamp(session,status,decision):
    a=app(session);before=snapshot(a)
    assert execute(session,a,_scraped('A/1',status=status,decision=decision)).outcome in {'fetch_failed','conflicting_source'}
    assert snapshot(a)==before


def test_status_only_withdrawal_cannot_retain_previous_grant_date(session):
    a=app(session,status='Decided',decision='Granted',decision_issued_date='2025-01-01')
    assert execute(session,a,_scraped('A/1',status='Withdrawn')).outcome=='verified_changed'
    assert a.decision=='Withdrawn' and a.decision_issued_date is None


def test_date_only_correction_has_one_atomic_lifecycle_signal(session):
    a=app(session,status='Decided',decision='Granted',decision_issued_date='2026-09-01')
    r=_scraped('A/1',status='Decided',decision='Granted');r.fields['Decision Issued Date']='2026-09-02'
    out=execute(session,a,r)
    assert out.outcome=='verified_changed' and 'decision_date_corrected' in out.material_change_reasons
    events=session.scalars(select(ApplicationLifecycleEvent)).all()
    assert len(events)==1 and events[0].field_name=='decision_issued_date'
    assert a.evidence_refresh_required
    assert execute(session,a,r).outcome=='verified_unchanged'
    assert len(session.scalars(select(ApplicationLifecycleEvent)).all())==1
