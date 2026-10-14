"""Fixed committee-trigger admission using shared transactions, transport and B2.

No scheduling, models, site linking, document traversal or arbitrary identities.
Production dispatch requires exact reviewed master, environment approval and CI.
"""
import contextlib
from dataclasses import replace
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.db.models import Application
from app.config import get_council
from app.pipeline.discovery_contract import DiscoveryEnvelope, ExactTriggerEvidence, WindowEvidence
from app.pipeline.discovery_admission import admit_identity

MANIFEST_SHA = '8c8d6fb5de8997cf64bcfa95dd2d3c6c292d51dc1533f834e892728d372e25ad'
AUTHORITY = 'AUTHORISE_THREE_COMMITTEE_IDENTITIES_AND_B2_ONCE'
WORKFLOW = '.github/workflows/stage4-committee-admission-once.yml'


def targets():
    raw = Path(__file__).with_name('committee_targets.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA:
        raise ValueError('manifest digest')
    rows = json.loads(raw)['targets']
    if [(r['council'], r['reference']) for r in rows] != [
            ('salford', 'PA/2025/1506'), ('manchester', '145583/FO/2026'), ('manchester', '143413/FO/2025')]:
        raise ValueError('fixed cohort')
    return rows


def case_definitions():
    return {r['case']: (None, r['reference'], r['source_url']) for r in targets()}


def envelope(row, run_id):
    now = datetime.now(timezone.utc)
    # Context interval only: exact-trigger admission NEVER claims enumeration.
    window = WindowEvidence(row['council'], run_id, date(2026, 7, 14), date(2026, 10, 13),
        None, None, 'PUBLICATION', None, None, None, 0, 0, 0, None, 0, accounting_complete=False)
    return DiscoveryEnvelope(row['council'], row['reference'], row['source_url'],
        row['source_identifier'], now, window, (row['reference'],), row['portal_evidence_fingerprint'], ())


def retrieve(row, application_id, runner=None):
    from verification.direct_reference.arcus_adapter import _from_observed_row
    from verification.direct_reference.arcus_transport import _qualify_row
    if runner is None:
        from verification.direct_reference.instrumented_probe import supervised
        runner = supervised
    with tempfile.TemporaryDirectory(prefix='committee-exact-') as directory:
        path = Path(directory) / 'source.json'
        with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink):
            runner(row['case'], path)
        if not path.is_file() or path.stat().st_size >= 65536:
            raise ValueError('bounded source audit absent')
        source = json.loads(path.read_bytes())
    worker_row = dict(row, application_id=None)
    projection_row = dict(row, application_id=application_id)
    def project(observed):
        state = observed.get('record_field_states', {}).get('status', {}).get('value')
        return _from_observed_row(projection_row, observed,
            initial_status=state in {'Under Consideration', 'Under Consultation'})
    result = _qualify_row(None, source, worker_row, row['case'], project)
    return result


def checked_engine(raw):
    u = make_url(raw)
    if (u.drivername != 'postgresql+psycopg' or u.host != 'aws-0-eu-west-2.pooler.supabase.com'
            or u.port != 5432 or u.database != 'postgres' or u.username != 'postgres.zcikcfgpblzuzpanpdqd'
            or u.query):
        raise ValueError('existing production route only')
    return create_engine(u, connect_args={'connect_timeout': 5, 'sslmode': 'require',
        'options': '-c statement_timeout=10000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=40000'},
        pool_size=1, max_overflow=0, pool_timeout=3)


def admission_environment(sha, authority):
    import re
    env = os.environ
    return (bool(re.fullmatch('[0-9a-f]{40}', sha)) and authority == AUTHORITY
        and sha == env.get('COMMITTEE_WORKFLOW_SHA') and env.get('GITHUB_REF') == 'refs/heads/master'
        and env.get('GITHUB_RUN_NUMBER') == '1' and env.get('GITHUB_RUN_ATTEMPT') == '1'
        and env.get('GITHUB_WORKFLOW_REF') == 'maxrose26/PropertyAIgent/' + WORKFLOW + '@refs/heads/master'
        and env.get('GITHUB_ACTIONS') == 'true' and env.get('RUNNER_ENVIRONMENT') == 'github-hosted')


def validate_sources(source_retrieve=retrieve,results=None):
    """Credential-free prerequisite; no identity creation or factual persistence."""
    results=[] if results is None else results
    for row in targets():
        resource=source_retrieve(row, None)
        observation=resource.get('observation')
        audit=dict(council=row['council'],reference=row['reference'],source=resource['audit'],
                   failure=resource.get('failure'),qualified=False)
        results.append(audit)
        from .rejection_audit import observation_audit
        audit['observation_evidence']=observation_audit(row,resource)
        if (resource.get('failure') or observation is None
                or resource['audit'].get('cleanup_state') != 'CLOSED'
                or resource['audit'].get('budget_state') != 'WITHIN_LIMITS'
                or not observation.literal_verified or not observation.b2_eligible):
            raise RuntimeError('transport-only qualification failed; no production admission')
        audit.update(qualified=True,verification_scope=observation.verification_scope,
                     field_states=observation.field_states,
                     supported_literal_facts=observation.literal_fields)
    return results


def run(engine, run_id, source_retrieve=retrieve, results=None):
    from verification.direct_reference.refresh import _refresh_row
    result = [] if results is None else results
    for row in targets():
        audit = dict(council=row['council'], reference=row['reference'], admission=None,
                     planning_observation='NOT_ATTEMPTED', source=None,
                     transaction='IDENTITY_ADMISSION_STARTED_UNCONFIRMED')
        result.append(audit)
        trigger = ExactTriggerEvidence(row['council'], row['reference'], row['trigger_url'],
                                       (row['reference'],), row['trigger_sha256'])
        admitted = admit_identity(engine, envelope(row, run_id), trigger=trigger)
        audit['admission'] = admitted
        audit['transaction'] = 'IDENTITY_COMMIT_READBACK_CONFIRMED'
        # A later race may have created an existing application. Do not reset it.
        if admitted['outcome'] == 'CREATED_PENDING':
            resource = None
            with Session(engine) as session:
                app = session.scalar(select(Application).where(Application.id == admitted['application_id']).limit(1))
                def fresh():
                    nonlocal resource
                    resource = source_retrieve(row, app.id)
                    audit['source'] = resource['audit']
                    if resource.get('failure') or resource.get('observation') is None:
                        from verification.direct_reference.refresh import fail
                        fail(resource.get('failure') or 'PARTIAL_RETRIEVAL', 'Fresh exact source withheld')
                    return resource['observation']
                audit['transaction'] = 'B2_EXECUTION_UNCONFIRMED'
                handoff = _refresh_row(session, app, get_council(row['council']),
                    dict(row, application_id=app.id), retrieve_evidence=fresh)
                audit['planning_observation'] = handoff['outcome']
                observation = handoff['observation']
                if observation:
                    audit['field_states'] = observation.field_states
                    audit['verification_scope'] = observation.verification_scope
                    audit['supported_literal_facts'] = observation.literal_fields
                audit['source'] = resource['audit'] if resource else None
                if handoff['outcome'] == 'PERSISTENCE_FAILED':
                    raise RuntimeError('B2 persistence uncertain; no retry')
            with Session(engine) as session:
                if engine.dialect.name == 'postgresql':
                    session.execute(text("SET LOCAL statement_timeout = '10s'"))
                current = session.execute(select(Application.id, Application.reference, Application.council_code,
                    Application.status, Application.decision, Application.decision_issued_date,
                    Application.status_verified_at, Application.planning_field_verification,
                    Application.unit_confirmation_status, Application.site_id, Application.evidence_refresh_required)
                    .where(Application.id == admitted['application_id']).limit(2)).mappings().all()
                if (len(current) != 1 or current[0]['reference'] != row['reference']
                        or current[0]['council_code'] != row['council']
                        or current[0]['unit_confirmation_status'] != 'discovery_pending'
                        or current[0]['site_id'] is not None):
                    raise RuntimeError('post-B2 readback unresolved; no retry')
                after = current[0]
                if handoff['accepted']:
                    if observation.verification_scope == 'INITIAL_STATUS_ONLY':
                        meta = json.loads(after['planning_field_verification'] or '{}')
                        if (after['status'] != observation.fields['Status']
                                or any(after[k] is not None for k in ('decision','decision_issued_date','status_verified_at'))
                                or meta.get('status',{}).get('body_sha256') != observation.body_sha256
                                or not meta.get('status',{}).get('verified_at')
                                or any(meta.get(k,{}).get('verified_at') is not None for k in ('decision','decision_date'))):
                            raise RuntimeError('initial field readback unresolved; no retry')
                    elif observation.verification_scope == 'COUPLED':
                        if (after['status'] != observation.fields['Status']
                                or after['decision'] != observation.fields['Decision']
                                or after['decision_issued_date'] != observation.fields['Decision Issued Date']
                                or after['status_verified_at'] is None):
                            raise RuntimeError('coupled readback unresolved; no retry')
                elif any(after[k] is not None for k in ('status','decision','decision_issued_date','status_verified_at','planning_field_verification')):
                    raise RuntimeError('failed verification preservation unresolved; no retry')
                audit['readback'] = {k: v.isoformat() if hasattr(v, 'isoformat') else v for k,v in current[0].items()}
                audit['transaction'] = 'COMMIT_READBACK_CONFIRMED'
                audit['observation_kind'] = 'INITIAL_RETAINED_OBSERVATION_NOT_PROVEN_SOURCE_CHANGE'
            if (resource is None or resource['audit'].get('cleanup_state') != 'CLOSED'
                    or resource['audit'].get('budget_state') != 'WITHIN_LIMITS'
                    or resource.get('failure') in {'CLEANUP_FAILURE','SCOPE_ESCAPE','ACCOUNTING_FAILURE','INVALID_ARTIFACT'}):
                raise RuntimeError('source supervision unresolved; no subsequent admission')
    return result


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--sha', required=True); parser.add_argument('--authority',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--transport-only',action='store_true')
    args=parser.parse_args()
    if not admission_environment(args.sha,args.authority):
        raise ValueError('execution not admitted')
    engine=None if args.transport_only else checked_engine(os.environ['COMMITTEE_DATABASE_URL'])
    output={'sha':args.sha,'manifest_sha':MANIFEST_SHA,'run_id':os.environ['GITHUB_RUN_ID'],
            'model_calls':0,'completed_through_advanced':False,'results':[], 'execution':'UNKNOWN'}
    try:
        if args.transport_only:
            validate_sources(results=output['results'])
            output['production_writes']=0
        else:
            run(engine,output['run_id'],results=output['results'])
        output['execution']='COMPLETED'
    except BaseException:
        output['execution']='STOP_UNCERTAIN_OR_FAILED_NO_RETRY'
        raise
    finally:
        if engine is not None: engine.dispose()
        raw=json.dumps(output,sort_keys=True,default=str)
        if len(raw.encode())>65536:
            raise ValueError('audit bound')
        Path(args.output).write_text(raw+'\n')

if __name__=='__main__':
    main()
