"""Offline direct-source mechanism proofs, not council compatibility forecasts."""
import datetime as dt
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest
import requests
from sqlalchemy import select
from app.config import CouncilConfig
from app.db.models import Application, ApplicationLifecycleEvent
from verification.direct_reference.refresh import (
    load_manifest, admitted_row, validate_destination, retrieve, refresh, Budget,
    BoundaryFailure, IDOX,
)
from verification.direct_reference.fixtures import Session, summary
from tests.test_planning_status_verification import _add_application

OLD=dt.datetime(2026,9,18,tzinfo=dt.timezone.utc)
ROW=next(r for r in load_manifest() if r['application_id']==42)

def config(row=ROW):
    return CouncilConfig(code=row['council'],name=row['council'],
        base_url='https://'+IDOX[row['council']][0]+IDOX[row['council']][1].rsplit('/',1)[0],
        date_field_mode='received',doc_system='idox',anite_base_url=None,
        unit_threshold=10,region=None,country=None)

def observe(body=None, **kwargs):
    transport=Session(body if body is not None else summary(ROW['reference']),**kwargs)
    try:return retrieve(42,session_factory=lambda:transport,budget=Budget())
    finally:
        assert transport.closed
        assert all(r.closed for r in transport.responses)

def add(session, **kwargs):
    a=_add_application(session,id=42,council_code=ROW['council'],reference=ROW['reference'],
        status=kwargs.pop('status','Awaiting decision'),status_verified_at=OLD,
        estimated_unit_count=68,unit_confirmation_status='review',application_category='primary_residential',
        further_info_url='https://retained.invalid/details',keyval='RETAINED',
        opportunity_classification='retained',scrape_batch_id='retained-batch',**kwargs)
    return a

def snapshot(a):
    return (a.status,a.decision,a.decision_issued_date,a.status_verified_at.replace(tzinfo=dt.timezone.utc) if a.status_verified_at else None,a.evidence_refresh_required)

def call(session,a,body=None):
    return refresh(session,a,config(),retrieve_evidence=lambda:observe(body))

def test_manifest_reconciles_and_minimises():
    rows=load_manifest()
    assert Counter(r['admission'] for r in rows)=={
        'ADMITTED_DIRECT_ROUTE':116,'MANUAL_FALLBACK_CANDIDATE':4,'UNSUPPORTED_ROUTE':82}
    assert Counter(r['council'] for r in rows)==dict(bolton=13,bury=5,manchester=37,oldham=20,
        rochdale=18,salford=31,stockport=34,tameside=7,trafford=19,wigan=18)
    allowed={'application_id','site_id','council','reference','source_url','source_identifier','platform_family',
        'stored_status','stored_decision','stored_decision_date','status_verified_at','verification_qualification',
        'cohort','reasons','consumers','dependency_roles','admission','admission_reason','historical_manual_summary_available'}
    assert all(set(r)==allowed and r['cohort'] in {1,2,4} for r in rows)
    assert len({(r['council'],r['reference']) for r in rows})==202

@pytest.mark.parametrize('row',load_manifest(),ids=lambda r:str(r['application_id']))
def test_each_admission(row):
    if row['platform_family']=='IDOX':
        validate_destination(row)
        s=Session(summary(row['reference']))
        o=retrieve(row['application_id'],session_factory=lambda:s,budget=Budget())
        assert o.reference==row['reference'] and o.b2_eligible
        assert len(s.calls)==1 and s.closed and s.responses[0].closed
        assert s.calls[0][1]['allow_redirects'] is False and s.trust_env is False
    else:
        with pytest.raises(BoundaryFailure,match='not admitted'):
            retrieve(row['application_id'],session_factory=lambda:pytest.fail('Arcus dispatched'),budget=Budget())

@pytest.mark.parametrize('suffix',['&activeTab=documents','&keyVal=OTHER','&search=anything','#x'])
def test_no_search_document_or_url_expansion(suffix):
    with pytest.raises(BoundaryFailure):validate_destination(dict(ROW,source_url=ROW['source_url']+suffix))

@pytest.mark.parametrize('url',['https://evil.invalid/x','http://planningpa.oldham.gov.uk/x',
    'https://planningpa.oldham.gov.uk@evil.invalid/x','https://planningpa.oldham.gov.uk/online-applications/search.do'])
def test_exact_origin_only(url):
    with pytest.raises(BoundaryFailure):validate_destination(dict(ROW,source_url=url))

@pytest.mark.parametrize('ref',['OTHER','ful/355686/26',''])
def test_identity_independent_and_exact(ref):
    with pytest.raises(BoundaryFailure):observe(summary(ref))

def test_duplicate_conflicting_field_and_partial_document():
    for body in [summary(ROW['reference'])[:-7],summary(ROW['reference']).replace(b'</table>',
        b'<tr><th>Status</th><td>Decided</td></tr></table>')]:
        with pytest.raises(BoundaryFailure):observe(body)

@pytest.mark.parametrize('omitted',[('Decision',),('Decision Issued Date',),('Decision','Decision Issued Date')])
def test_optional_omission_literal_success_no_b2(session,omitted):
    a=add(session);before=snapshot(a);result=call(session,a,summary(ROW['reference'],omit=omitted))
    assert result['observation'].literal_verified and not result['accepted']
    assert 'NOT_PRESENT' in result['observation'].field_states.values()
    assert snapshot(a)==before

def test_deposited_is_literal_only_unknown(session):
    a=add(session);before=snapshot(a);result=call(session,a,summary(ROW['reference'],status='Deposited'))
    assert result['observation'].semantic_state=='UNKNOWN_UNMAPPED'
    assert result['observation'].literal_fields['Status']=='Deposited'
    assert not result['accepted'] and snapshot(a)==before

def test_literal_date_separate_from_normalised():
    o=observe(summary(ROW['reference'],'Decided','Refused','Fri 25 Sep 2026'))
    assert o.fields['Decision Issued Date']=='2026-09-25'
    assert o.literal_fields['Decision Issued Date']=='Fri 25 Sep 2026'

@pytest.mark.parametrize('date',['nonsense','2026-99-12'])
def test_unparseable_date(date):
    with pytest.raises(BoundaryFailure):observe(summary(ROW['reference'],'Decided','Refused',date))

@pytest.mark.parametrize('status,outcome',[(429,'RATE_LIMITED'),(404,'SOURCE_UNAVAILABLE'),
    (403,'SOURCE_UNAVAILABLE'),(503,'SOURCE_UNAVAILABLE'),(302,'PARTIAL_RETRIEVAL')])
def test_http_outcomes(status,outcome):
    s=Session(b'',status=status);b=Budget()
    with pytest.raises(BoundaryFailure) as e:retrieve(42,session_factory=lambda:s,budget=b)
    assert e.value.outcome==outcome and s.closed and all(r.closed for r in s.responses)
    assert b.requests==(2 if status==503 else 1)

@pytest.mark.parametrize('error,outcome',[(requests.Timeout(),'TIMEOUT'),(requests.ConnectionError(),'SOURCE_UNAVAILABLE')])
def test_retry_bound(error,outcome):
    s=Session(error);b=Budget()
    with pytest.raises(BoundaryFailure) as e:retrieve(42,session_factory=lambda:s,budget=b)
    assert e.value.outcome==outcome and b.requests==2 and s.closed

@pytest.mark.parametrize('headers',[{'Content-Type':'application/pdf'},{'Content-Encoding':'gzip'},
    {'Content-Disposition':'attachment'},{'Content-Length':'1000001'},{'Content-Length':'999'}])
def test_non_summary_or_truncated(headers):
    with pytest.raises(BoundaryFailure):observe(headers=headers)

def test_body_overflow_accounting_and_cleanup():
    s=Session(b'x'*1_000_001);b=Budget()
    with pytest.raises(BoundaryFailure):retrieve(42,session_factory=lambda:s,budget=b)
    assert b.bytes==1_000_001 and s.closed and s.responses[0].closed

def test_run_byte_request_deadline_and_row_bounds():
    for b in [Budget(byte_limit=10),Budget(request_limit=1,requests=1),Budget(seconds=.001,started=0),Budget(rows=20)]:
        s=Session(summary(ROW['reference']))
        with pytest.raises(BoundaryFailure):retrieve(42,session_factory=lambda:s,budget=b)
        assert b.requests<=b.request_limit

def test_parser_structure_bound():
    with pytest.raises(BoundaryFailure):observe(b'<html>'+b'<tr>'*257+b'</html>')

def test_unchanged_handoff_and_nonstatus_preservation(session):
    a=add(session);before=(a.estimated_unit_count,a.unit_confirmation_status,a.further_info_url,
        a.keyval,a.application_category,a.opportunity_classification,a.scrape_batch_id)
    out=call(session,a)
    assert out['accepted'] and out['outcome']=='VERIFIED_UNCHANGED'
    assert a.status_verified_at.replace(tzinfo=dt.timezone.utc)>OLD
    assert before==(a.estimated_unit_count,a.unit_confirmation_status,a.further_info_url,
        a.keyval,a.application_category,a.opportunity_classification,a.scrape_batch_id)


def test_material_change_single_writer_and_idempotent_retry(session):
    a=add(session);body=summary(ROW['reference'],'Decided','Refused','Fri 25 Sep 2026')
    assert call(session,a,body)['outcome']=='VERIFIED_MATERIAL_CHANGE'
    assert a.decision=='Refused' and a.evidence_refresh_required
    assert call(session,a,body)['outcome']=='VERIFIED_UNCHANGED'
    assert len(session.scalars(select(ApplicationLifecycleEvent)).all())==1

@pytest.mark.parametrize('point',['commit','upsert','interrupt'])
def test_b2_failure_preservation(session,monkeypatch,point):
    a=add(session);before=snapshot(a)
    if point=='upsert':
        import app.pipeline.run_weekly as w
        orig=w._upsert_scraped_application
        def bad(*args,**kw):orig(*args,**kw);raise RuntimeError('synthetic')
        monkeypatch.setattr(w,'_upsert_scraped_application',bad)
    else:
        def bad():raise KeyboardInterrupt() if point=='interrupt' else RuntimeError('synthetic')
        monkeypatch.setattr(session,'commit',bad)
    body=summary(ROW['reference'],'Decided','Refused','Fri 25 Sep 2026')
    if point=='interrupt':
        with pytest.raises(KeyboardInterrupt):call(session,a,body)
    else:assert call(session,a,body)['outcome']=='PERSISTENCE_FAILED'
    assert snapshot(a)==before and not session.scalars(select(ApplicationLifecycleEvent)).all()

def test_blank_does_not_certify_retained_nonblank(session):
    a=add(session,status='Decided',decision='Granted',decision_issued_date='2026-09-01');before=snapshot(a)
    out=call(session,a,summary(ROW['reference'],'Decided'))
    assert not out['accepted'] and snapshot(a)==before

def test_stale_response_rejected_and_concurrent_metadata_preserved(session):
    from sqlalchemy.orm import Session as DBSession
    a=add(session)
    def load():
        with DBSession(session.get_bind(),expire_on_commit=False) as other:
            b=other.get(Application,a.id)
            b.estimated_unit_count=69;other.commit()
            assert call(other,b,summary(ROW['reference'],'Decided','Refused','2026-09-25'))['accepted']
        return observe(summary(ROW['reference'],'Decided','Granted','2026-09-26'))
    out=refresh(session,a,config(),retrieve_evidence=load)
    assert out['outcome']=='STALE_RESPONSE'
    session.refresh(a);assert a.decision=='Refused' and a.estimated_unit_count==69


def test_only_metadata_concurrent_update_survives(session):
    from sqlalchemy.orm import Session as DBSession
    a=add(session)
    def load():
        with DBSession(session.get_bind(),expire_on_commit=False) as other:
            # Simulate a metadata writer that does not touch B2's guarded fields.
            from sqlalchemy import text
            other.execute(text('UPDATE applications SET estimated_unit_count=99 WHERE id=:id'), {'id':a.id})
            other.commit()
        return observe()
    out=refresh(session,a,config(),retrieve_evidence=load)
    assert out['accepted'] and out['outcome']=='VERIFIED_UNCHANGED', out
    assert not session.scalars(select(ApplicationLifecycleEvent)).all()
    assert not a.evidence_refresh_required
    session.refresh(a);assert a.estimated_unit_count==99 and a.unit_confirmation_status=='review'


def test_lost_ack_never_claims_success_and_retry_idempotent(session,monkeypatch):
    a=add(session);commit=session.commit
    def lost():commit();raise RuntimeError('lost acknowledgement')
    monkeypatch.setattr(session,'commit',lost)
    body=summary(ROW['reference'],'Decided','Refused','2026-09-25')
    assert call(session,a,body)['outcome']=='PERSISTENCE_FAILED'
    monkeypatch.setattr(session,'commit',commit)
    assert call(session,a,body)['outcome']=='VERIFIED_UNCHANGED'
    assert len(session.scalars(select(ApplicationLifecycleEvent)).all())==1


def test_arbitrary_handoff_identity_never_stamps(session):
    a=add(session);before=snapshot(a);o=replace(observe(),reference='WRONG')
    assert not refresh(session,a,config(),retrieve_evidence=lambda:o)['accepted']
    assert snapshot(a)==before


def test_ordinary_supervisor_timeout():
    from verification.stage26b_l1.actions_runner import supervise
    status,expired=supervise([sys.executable,'-c','import time; time.sleep(30)'],env={'PATH':'/usr/bin:/bin'},deadline=.05)
    assert expired and status==124


def test_minimised_retained_official_summary_optional_labels():
    p=Path('verification/direct_reference/retained-summary-24.json')
    retained=json.loads(p.read_text())
    s=Session(retained['html'].encode())
    o=retrieve(24,session_factory=lambda:s,budget=Budget())
    assert o.reference=='OUT/354782/25' and o.literal_verified
    assert o.field_states['decision']==o.field_states['decision_date']=='NOT_PRESENT'
    assert not o.b2_eligible and len(retained['source_sha256'])==64


def test_privacy_unrelated_source_fields_not_retained():
    body=summary(ROW['reference']).replace(b'</table>',b'<tr><th>Applicant</th><td>PERSON PRIVATE</td></tr></table>')
    o=observe(body)
    from dataclasses import asdict
    assert 'PERSON PRIVATE' not in json.dumps(asdict(o))
    assert set(o.literal_fields)=={'Reference','Status','Decision','Decision Issued Date'}


def test_interrupted_retrieval_closes_session_and_response():
    from verification.direct_reference.fixtures import Response
    s=Session(b'')
    class Interrupted(Response):
        def iter_content(self,chunk_size):raise KeyboardInterrupt()
    r=Interrupted(ROW['source_url'],b'')
    s.get=lambda *args,**kwargs:r
    with pytest.raises(KeyboardInterrupt):retrieve(42,session_factory=lambda:s,budget=Budget())
    assert s.closed and r.closed


def test_failure_diagnostics_retain_field_state_only():
    body=summary(ROW['reference']).replace(b'</table>',b'<tr><th>Decision</th><td>Refused</td></tr></table>')
    with pytest.raises(BoundaryFailure) as e:observe(body)
    assert e.value.diagnostics['fields']['decision']['state']=='CONFLICTING'
    with pytest.raises(BoundaryFailure) as e:observe(summary(ROW['reference'],date='invalid'))
    assert e.value.diagnostics['fields']['decision_date']['state']=='UNPARSEABLE'
