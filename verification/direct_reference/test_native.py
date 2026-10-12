"""Direct retrieval-to-B2 rehearsal against disposable PostgreSQL17 only."""
from sqlalchemy import select, text
from sqlalchemy.orm import Session as DBSession
from verification.b20_native.test_postgres import engine, no_external_calls
from app.db.models import Application, ApplicationLifecycleEvent, Council
from tests.test_stage4_direct_reference import ROW, config, observe
from verification.direct_reference.fixtures import summary
from verification.direct_reference.refresh import refresh


def test_direct_native_atomic_retry_metadata_and_failure(engine,monkeypatch):
    with DBSession(engine,expire_on_commit=False) as s:
        s.add(Council(code='oldham',name='Synthetic',base_url=config().base_url,
            date_field_mode='received',doc_system='idox'))
        s.add(Application(id=42,council_code='oldham',reference=ROW['reference'],
            status='Awaiting decision',estimated_unit_count=68,unit_confirmation_status='review'))
        s.commit()
        a=s.get(Application,42)
        def concurrent():
            with DBSession(engine) as other:
                other.execute(text('UPDATE applications SET estimated_unit_count=99 WHERE id=42'))
                other.commit()
            return observe()
        out=refresh(s,a,config(),retrieve_evidence=concurrent)
        assert out['outcome']=='VERIFIED_UNCHANGED'
        assert a.estimated_unit_count==99 and a.unit_confirmation_status=='review'
        assert not a.evidence_refresh_required
        stamp=a.status_verified_at
        assert not s.scalars(select(ApplicationLifecycleEvent).where(ApplicationLifecycleEvent.application_id==42)).all()
        commit=s.commit
        def fail():raise RuntimeError('before commit')
        monkeypatch.setattr(s,'commit',fail)
        body=summary(ROW['reference'],'Decided','Refused','2026-09-25')
        assert refresh(s,a,config(),retrieve_evidence=lambda:observe(body))['outcome']=='PERSISTENCE_FAILED'
        s.refresh(a);assert a.status_verified_at==stamp and a.decision is None
        def lost():commit();raise RuntimeError('acknowledgement lost')
        monkeypatch.setattr(s,'commit',lost)
        assert refresh(s,a,config(),retrieve_evidence=lambda:observe(body))['outcome']=='PERSISTENCE_FAILED'
        monkeypatch.setattr(s,'commit',commit)
        assert refresh(s,a,config(),retrieve_evidence=lambda:observe(body))['outcome']=='VERIFIED_UNCHANGED'
        assert len(s.scalars(select(ApplicationLifecycleEvent).where(ApplicationLifecycleEvent.application_id==42)).all())==1
