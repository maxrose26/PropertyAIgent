"""Identity-only admission preparation. No production CLI or source admission.

Call only after independently reviewed source/window qualification. Planning
facts remain exclusively in B2. This helper never promotes a candidate, links a
site, downloads documents, or invokes intelligence. Durable run audit is the
caller's responsibility; an uncertain commit MUST stop that run.
"""
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.db.models import Application
from app.pipeline.discovery_contract import Completeness, DiscoveryEnvelope

PENDING = 'discovery_pending'


class UncertainDiscoveryCommit(RuntimeError):
    """Do not retry; reconcile identity and transaction separately."""


def admit_identity(engine, envelope: DiscoveryEnvelope) -> dict:
    if envelope.window.outcome != Completeness.COMPLETE:
        raise ValueError('incomplete discovery window cannot admit production identities')
    dialect = engine.dialect.name
    if dialect == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == 'sqlite':
        # Local deterministic tests only; operational acceptance requires PG.
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise ValueError('unqualified database dialect')
    columns = (Application.id, Application.council_code, Application.reference,
               Application.unit_confirmation_status, Application.site_id)
    query = select(*columns).where(
        Application.council_code == envelope.council,
        Application.reference == envelope.reference).limit(2)
    with Session(engine, expire_on_commit=False) as session:
        try:
            if dialect == 'postgresql':
                session.execute(text("SET LOCAL statement_timeout = '10s'"))
                session.execute(text("SET LOCAL lock_timeout = '3s'"))
            before = session.execute(query).mappings().all()
            if len(before) > 1:
                raise ValueError('identity uniqueness violated')
            statement = insert(Application).values(
                council_code=envelope.council, reference=envelope.reference,
                unit_confirmation_status=PENDING,
                first_seen_at=envelope.discovered_at,
                last_seen_at=envelope.discovered_at,
            ).on_conflict_do_nothing(index_elements=['council_code', 'reference']).returning(Application.id)
            inserted = session.execute(statement).scalar_one_or_none()
            inside = session.execute(query).mappings().all()
            if len(inside) != 1:
                raise ValueError('identity readback failed')
            if inserted is not None and (inside[0]['unit_confirmation_status'] != PENDING or inside[0]['site_id'] is not None):
                raise ValueError('new identity isolation failed')
        except Exception:
            session.rollback()
            raise
        try:
            session.commit()
        except Exception as exc:
            raise UncertainDiscoveryCommit('commit acknowledgement uncertain; no retry') from exc
    try:
        with Session(engine) as readback:
            if dialect == 'postgresql':
                readback.execute(text("SET LOCAL statement_timeout = '10s'"))
            after = readback.execute(query).mappings().all()
            if len(after) != 1 or dict(after[0]) != dict(inside[0]):
                raise ValueError('committed identity changed or missing')
    except Exception as exc:
        raise UncertainDiscoveryCommit('post-commit readback unresolved; no retry') from exc
    return {'outcome': 'CREATED_PENDING' if inserted is not None else 'ALREADY_KNOWN',
            'application_id': after[0]['id'], 'council': envelope.council,
            'reference': envelope.reference, 'before': [dict(r) for r in before],
            'after': dict(after[0]), 'transaction': 'COMMIT_READBACK_CONFIRMED',
            'provenance_sha256': envelope.body_sha256, 'run_id': envelope.window.run_id,
            'planning_facts_written': False, 'site_relationship': 'UNKNOWN'}
