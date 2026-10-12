"""Actual PG transactions; frozen source facts, disposable application rows only."""
import copy
import datetime as dt
from unittest.mock import patch

from sqlalchemy import delete,select,text
from sqlalchemy.orm import Session
from app.config import CouncilConfig
from app.db.models import Application,ApplicationLifecycleEvent,Council
from verification.direct_reference.frozen_acceptance import frozen_observation,load_live,PROVENANCE
from verification.direct_reference.refresh import refresh

OLD=dt.datetime(2026,9,18,tzinfo=dt.timezone.utc)
SCENARIOS=('oldham','bolton','stockport','atomic_rollback','stale_response','lost_ack',
 'wrong_reference','conflicting','partial','parser_failure','b2_rejection','database_exception')
COLUMNS=('status','decision','decision_issued_date','status_verified_at','evidence_refresh_required',
 'evidence_refresh_reason','evidence_refresh_trigger','evidence_refresh_requested_at',
 'estimated_unit_count','unit_confirmation_status')


def config(i):
    from .refresh import admitted_row
    r=admitted_row(i)
    return CouncilConfig(code=r['council'],name=r['council'],base_url=r['source_url'].split('/applicationDetails.do')[0],
      date_field_mode='received',doc_system='idox',anite_base_url=None,unit_threshold=10,region='GM',country='England')


def seed(engine):
    with Session(engine) as s:
        s.execute(delete(ApplicationLifecycleEvent).where(ApplicationLifecycleEvent.application_id.in_([42,78,202])))
        s.execute(delete(Application).where(Application.id.in_([42,78,202])))
        for i,status,decision,date in [(42,'Awaiting decision',None,None),(202,'Deposited',None,None),(78,'Decided','Granted','Wed 27 Dec 2023')]:
            cfg=config(i)
            if not s.get(Council,cfg.code):s.add(Council(code=cfg.code,name=cfg.name,base_url=cfg.base_url,date_field_mode='received',doc_system='idox'))
            s.add(Application(id=i,council_code=cfg.code,reference=frozen_observation(i).reference,
              status=status,decision=decision,decision_issued_date=date,status_verified_at=OLD,
              estimated_unit_count=68,unit_confirmation_status='review'))
        s.commit()


def read(engine,i):
    with Session(engine) as s:
        a=s.get(Application,i)
        return dict(facts={k:getattr(a,k) for k in COLUMNS},events=[(e.event_type,e.field_name,e.old_value,e.new_value,e.authoritative_source)
          for e in s.scalars(select(ApplicationLifecycleEvent).where(ApplicationLifecycleEvent.application_id==i).order_by(ApplicationLifecycleEvent.id))])


def apply(s,i,loader=None):
    return refresh(s,s.get(Application,i),config(i),retrieve_evidence=loader or (lambda:frozen_observation(i)))


def run_scenario(engine,monkeypatch,scenario):
    seed(engine)
    i=202 if scenario=='bolton' else 78 if scenario=='stockport' else 42
    before=read(engine,i)
    with Session(engine,expire_on_commit=False) as s:
        if scenario=='oldham':
            out=apply(s,i);assert out['accepted'] and out['outcome']=='VERIFIED_MATERIAL_CHANGE'
            after=read(engine,i);f=after['facts']
            assert (f['status'],f['decision'],f['decision_issued_date'])==('Decided','Refuse Permission','2026-09-25')
            assert f['status_verified_at']>OLD and f['evidence_refresh_required']
            assert f['evidence_refresh_reason']=='decision_refused' and f['evidence_refresh_trigger']=='material_change'
            assert f['evidence_refresh_requested_at'] is not None
            assert len(after['events'])==1 and after['events'][0][0]=='decision_refused'
            assert f['estimated_unit_count']==68 and f['unit_confirmation_status']=='review'
        elif scenario=='bolton':
            out=apply(s,i)
            assert not out['accepted'] and out['outcome']=='PARTIAL_RETRIEVAL'
            assert out['observation'].literal_verified and out['observation'].semantic_state=='UNKNOWN_UNMAPPED'
            assert read(engine,i)==before
        elif scenario=='stockport':
            out=apply(s,i);assert out['accepted'] and out['outcome']=='VERIFIED_NON_MATERIAL_CHANGE'
            first=read(engine,i)
            assert not first['events'] and not first['facts']['evidence_refresh_required']
            assert first['facts']['decision_issued_date']=='2023-12-27' and first['facts']['status_verified_at']>OLD
            out=apply(s,i);assert out['outcome']=='VERIFIED_UNCHANGED'
            second=read(engine,i)
            assert second['events']==first['events'] and second['facts']['status_verified_at']>first['facts']['status_verified_at']
            assert not second['facts']['evidence_refresh_required']
        elif scenario in ('atomic_rollback','database_exception'):
            def broken():
                s.flush()
                # Independent reader sees none of the reservation/facts/event before commit.
                assert read(engine,i)==before
                if scenario=='database_exception':s.execute(text('SELECT 1/0'))
                raise RuntimeError('disposable failure before commit')
            monkeypatch.setattr(s,'commit',broken)
            out=apply(s,i);assert out['outcome']=='PERSISTENCE_FAILED'
            assert read(engine,i)==before
        elif scenario=='stale_response':
            accepted=[]
            def newer():
                with Session(engine) as other:assert apply(other,i)['accepted']
                accepted.append(read(engine,i));return frozen_observation(i)
            out=apply(s,i,newer)
            assert out['outcome']=='STALE_RESPONSE' and not out['accepted']
            assert read(engine,i)==accepted[0] and len(accepted[0]['events'])==1
        elif scenario=='lost_ack':
            commit=s.commit
            def lost():commit();raise RuntimeError('lost acknowledgement')
            monkeypatch.setattr(s,'commit',lost)
            assert apply(s,i)['outcome']=='PERSISTENCE_FAILED'
            committed=read(engine,i);assert len(committed['events'])==1
            monkeypatch.setattr(s,'commit',commit)
            assert apply(s,i)['outcome']=='VERIFIED_UNCHANGED'
            retried=read(engine,i);assert retried['events']==committed['events']
            assert retried['facts']['status_verified_at']>committed['facts']['status_verified_at']
            for key in COLUMNS:
                if key!='status_verified_at':assert retried['facts'][key]==committed['facts'][key]
        elif scenario=='b2_rejection':
            # Negative control: accepted later terminal date may not be replaced by older evidence.
            a=s.get(Application,i);a.status='Decided';a.decision='Granted';a.decision_issued_date='2026-10-01';s.commit()
            before=read(engine,i);out=apply(s,i)
            assert not out['accepted'] and out['b2_outcome']=='conflicting_source'
            assert read(engine,i)==before
        else:
            def invalid():
                from verification.stage26b_l1.request_boundary import BoundaryFailure
                if scenario=='parser_failure':raise BoundaryFailure('PARSER_FAILURE','Frozen negative control')
                o=frozen_observation(i)
                if scenario=='wrong_reference':o.reference='WRONG'
                if scenario=='conflicting':o.field_states['decision']='CONFLICTING'
                if scenario=='partial':o.field_states['decision_date']='NOT_PRESENT';o.b2_eligible=False
                return o
            out=apply(s,i,invalid);assert not out['accepted']
            assert read(engine,i)==before
    print('FROZEN_LIVE_B2_PASS',scenario,'provenance=LIVE_SOURCE_OBSERVATION','database=DISPOSABLE_ONLY')
