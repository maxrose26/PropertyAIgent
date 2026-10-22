"""Explicitly selected restricted observation stage; no CLI or registration."""
from app.ingestion.ledger import Denied,digest
from app.ingestion.idox_adapter import OBSERVATION_KIND
from app.ingestion.observation_screening import require_enabled

def retain_observation(coordinator, key, reader, archive, *, check=lambda: None, prior_accounting_sha256=None):
    """Restricted capture-stage seam. No enqueue, issuer, window or writer access.

    Recovery uses only a closed, sealed checkpoint after operator claim recovery.
    An unresolved source intent is not permission to call the source again.
    """
    from .operational_controller import ControllerLedger
    if not isinstance(coordinator.ledger,ControllerLedger):raise Denied('ACCOUNTED_SQL_LEDGER_REQUIRED')
    l=coordinator.ledger;check()
    # The old broker accepts arbitrary closed source payloads. Refuse that
    # installed state BEFORE claim/source effects; rollback must really disable
    # this new controller, not merely fail a later batch.
    from sqlalchemy import text
    from . import observation_worker_sql as ow
    import re
    expected=re.search(r'AS \$fn\$(.*?)\$fn\$;',ow.installation_script(),re.S).group(1)
    with l.worker_engine.connect() as connection:
        actual=connection.execute(text("SELECT p.prosrc,r.rolname,p.proconfig,p.prosecdef FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_roles r ON r.oid=p.proowner WHERE p.oid=to_regprocedure('public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)')")).one_or_none()
    if actual is None or tuple(actual)!=(expected,'ingestion_storage_owner',['search_path=pg_catalog'],True):
        raise Denied('OBSERVATION_WORKER_NOT_INSTALLED')
    row=l.get(key)
    require_enabled(coordinator.observation_councils,row['subject']['council'])
    from app.ingestion.listing_screening import RULE_V1
    if coordinator.screening_rule.rule_version!=RULE_V1 and coordinator.screening_rule.link_related:
        raise Denied('BOUNDED_OBSERVATION_HISTORY_SELECTION_REQUIRED')
    saved=row['checkpoint']
    if saved is None:
        if row['attempt_count'] or row['phase'] not in ('IDLE','RECOVERED'):
            raise Denied('OBSERVATION_SOURCE_REPLAY_FORBIDDEN')
        coordinator.idox_source(l.claim(key,lease_seconds=165),reader,materialize=False,archive=archive)
    else:
        if saved.get('kind')!=OBSERVATION_KIND:raise Denied('OBSERVATION_CHECKPOINT_REQUIRED')
        if row['state']!='COMPLETE':
            budget=l.budget
            if (budget.slot_key!=key or not budget.previous or budget.previous.get('slot_key')!=key
                or not prior_accounting_sha256 or digest(budget.previous)!=prior_accounting_sha256
                or budget.previous.get('capture_checkpoint_sha256')!=digest(saved)):
                raise Denied('SEALED_RECOVERY_ACCOUNTING_REQUIRED')
            claim=l.claim(key,lease_seconds=165);l.checkpoint(claim,saved)
            l.finish(claim,dict(outcome='ENUMERATED_METADATA_RETAINED',children=[],source_sha256=saved['source_sha256']))
    check();result=l.get(key)['checkpoint']
    if result.get('kind')!=OBSERVATION_KIND:raise Denied('OBSERVATION_NOT_RETAINED')
    return result

