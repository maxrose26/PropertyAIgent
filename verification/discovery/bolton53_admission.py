"""Unregistered primary-discovery admission proposal. No live CLI authority.

The only executable entry is a private owned child. Production registration and
execution are deliberately absent. Facts remain in shared B2; uncertain effects
stop all subsequent records. Source children never inherit database credentials.
"""
from dataclasses import replace
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import time
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.db.models import Application
from app.config import get_council
from app.pipeline.discovery_contract import DiscoveryEnvelope, WindowEvidence, Completeness
from app.pipeline.discovery_admission import admit_identity, UncertainDiscoveryCommit
from . import r0_bolton53_qualification as source
from .r0_registered_scopes import AuditStore

ROOT=Path(__file__).resolve().parents[2]
PACK=ROOT/'docs/design/stage4-r0-execution/bolton53-admission-exact16'
COHORT_SHA='98b682d893cc8a695c032a6a2aed059bcfd56b805ae06117e5f50480b3045bce'
PRIMARY_SHA='2fc2bb69cdba4b0f466d17b510457a4070bff363372586f4af647692cd1bf67d'
# Hard owned-process elapsed deadlines, NOT sums claimed from SQL timeouts.
# 55 source + 50 identity (including acquisition/commit/readback) + 60 B2
# and committed readback + 15 rollback/disposal/checkpoint = 180 seconds.
LIMITS=dict(calls=53,requests=106,bytes=106_000_000,source_seconds=2915,
    record_seconds=180,seconds=9660,output_bytes=8_000_000,
    record_output_bytes=65536,rss_bytes=1536*1024*1024,
    setup_seconds=280,job_seconds=10140,cleanup_seconds=15)
PHASES={'RECORD_STARTED','IDENTITY_TRANSACTION_STARTED','IDENTITY_COMMIT_READBACK_CONFIRMED',
    'SOURCE_STARTED','SOURCE_CLOSED','B2_TRANSACTION_STARTED','FACTS_COMMIT_READBACK_CONFIRMED',
    'ENGINE_DISPOSED','RECORD_CLOSED'}


def rows():
    raw=(PACK/'proposed-admission53-cohort.json').read_bytes()
    primary=(PACK/'primary53-evidence.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=COHORT_SHA or hashlib.sha256(primary).hexdigest()!=PRIMARY_SHA:
        raise ValueError('FROZEN_PROVENANCE_REJECTED')
    cohort=json.loads(raw)['rows'];evidence=json.loads(primary)['rows'];qualified=source.targets()
    if len(evidence)!=53 or len(cohort)!=53:raise ValueError('EXACT53_REQUIRED')
    for c,e,q in zip(cohort,evidence,qualified):
        if any(c[k]!=q[k] or e[k]!=c[k] for k in ('council','reference','source_url','source_identifier')):
            raise ValueError('FROZEN_IDENTITY_REJECTED')
        if c['reference']=='01842/26' or c['council']!='bolton':raise ValueError('COHORT_REJECTED')
        yield dict(e,case=q['case'])


def envelope(row):
    w=row['window'];s=row['window_evidence'];r=s['resource'];pages=s['pages']
    # Original enumeration proof, never the later exact-record qualification.
    window=WindowEvidence('bolton',str(row['window_run']),date.fromisoformat(w['start']),date.fromisoformat(w['end']),
        *(date.fromisoformat(x) for x in s['applied_interval']),w['semantics'],
        'IDOX_STRICT_REFINE_SORT_ENUMERATION',s['applied_evidence_sha256'],pages[-1]['terminal'],
        len(pages),pages[-1]['total'],r['requests_attempted'],r['received_bytes'],r['elapsed_seconds'],capped=s['capped'],failure=s['failure'])
    if window.outcome!=Completeness.COMPLETE or s['enumeration_evidence']!='COUNT_RECONCILED':
        raise ValueError('ORIGINAL_WINDOW_NOT_QUALIFIED')
    rec=row['source_record']
    if rec['identity_state']!='PRESENT_VALUE' or rec['source_key']!=row['source_identifier'] or rec['reference']!=row['reference']:
        raise ValueError('ORIGINAL_RECORD_IDENTITY')
    return DiscoveryEnvelope('bolton',row['reference'],row['source_url'],row['source_identifier'],
        datetime.fromisoformat(row['discovered_at']),window,(rec['reference'],),hashlib.sha256(json.dumps(rec,sort_keys=True).encode()).hexdigest(),())


def fresh(row):
    """Existing supervisor launches its source child with a credential-free env.

    Do not call source.read here: that wrapper intentionally rejects a DB parent.
    Only the existing isolated child receives source work. Projection has no DB.
    """
    import contextlib,tempfile
    from verification.direct_reference.instrumented_probe import supervised
    from .material_qualification import project_idox
    with tempfile.TemporaryDirectory(prefix='bolton53-fresh-') as directory:
        path=Path(directory)/'source.json'
        with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink):supervised(row['case'],path)
        if not path.is_file() or path.stat().st_size>=65536:raise ValueError('INVALID_SOURCE_AUDIT')
        value=json.loads(path.read_bytes())
    closed=next(q for q in source.targets() if q['reference']==row['reference'])
    return project_idox(closed,value)


def readback(engine,row,app_id,observation=None,accepted=False):
    with Session(engine) as s:
        if engine.dialect.name=='postgresql':
            s.execute(text('SET TRANSACTION READ ONLY'));s.execute(text("SET LOCAL statement_timeout='10s'"))
        app=s.scalar(select(Application).where(Application.id==app_id,Application.council_code==row['council'],Application.reference==row['reference']))
        if app is None:raise UncertainDiscoveryCommit('READBACK_MISSING_NO_RETRY')
        if app.site_id is not None or app.unit_confirmation_status!='discovery_pending':raise UncertainDiscoveryCommit('READBACK_CHANGED_NO_RETRY')
        metadata=json.loads(app.planning_field_verification or '{}')
        if accepted:
            if observation.verification_scope!='INITIAL_STATUS_ONLY':raise UncertainDiscoveryCommit('UNEXPECTED_SCOPE_NO_RETRY')
            if (app.status!=observation.fields['Status'] or app.status_verified_at is not None
                or app.decision is not None or app.decision_issued_date is not None
                or metadata.get('status',{}).get('body_sha256')!=observation.body_sha256
                or not metadata.get('status',{}).get('verified_at')
                or any(metadata.get(k,{}).get('verified_at') is not None for k in ('decision','decision_date'))):
                raise UncertainDiscoveryCommit('FACTUAL_READBACK_UNRESOLVED_NO_RETRY')
        return dict(id=app.id,council_code=app.council_code,reference=app.reference,
            status=app.status,decision=app.decision,decision_date=app.decision_issued_date,
            field_verification=metadata,site_id=app.site_id,application_role='UNKNOWN',site_relationship='UNKNOWN')


def record(engine,row,*,retrieve=fresh,journal=lambda _:None):
    """Actual primary envelope -> shared identity -> shared B2; no trigger path."""
    from verification.direct_reference.refresh import _refresh_row
    audit=dict(council=row['council'],reference=row['reference'],identity='NOT_ATTEMPTED',
        facts='NOT_ATTEMPTED',transaction='NOT_STARTED',site_relationship='UNKNOWN',application_role='UNKNOWN')
    journal('IDENTITY_TRANSACTION_STARTED')
    try:admitted=admit_identity(engine,envelope(row))
    except UncertainDiscoveryCommit:
        audit.update(identity='UNKNOWN_COMMIT',transaction='UNCERTAIN_STOP_NO_RETRY');return audit
    except Exception:
        audit.update(identity='FAILED_OR_UNCERTAIN',transaction='UNCERTAIN_STOP_NO_RETRY',stop=True);return audit
    audit.update(identity=admitted['outcome'],application_id=admitted['application_id'],admission_mode=admitted['admission_mode'],
        transaction='IDENTITY_COMMIT_READBACK_CONFIRMED')
    journal('IDENTITY_COMMIT_READBACK_CONFIRMED')
    if admitted['outcome']=='ALREADY_KNOWN':
        audit['identity']='ALREADY_KNOWN';audit['facts']='EXISTING_NOT_WRITTEN';return audit
    journal('SOURCE_STARTED')
    try:resource=retrieve(row)
    except Exception:
        audit.update(facts='WITHHELD_SOURCE_ACCOUNTING_UNKNOWN',stop=True);return audit
    a=resource.get('audit',{});obs=resource.get('observation')
    audit['source']=a
    from .rejection_audit import observation_audit
    audit['fresh_evidence']=observation_audit(row,resource)
    if (a.get('cleanup_state')!='CLOSED' or a.get('budget_state')!='WITHIN_LIMITS'
        or type(a.get('requests')) is not int or not 0<=a['requests']<=2
        or type(a.get('received_body_bytes')) is not int or not 0<=a['received_body_bytes']<=2_000_000):
        audit.update(facts='WITHHELD_RESOURCE_OR_CLEANUP',stop=True);return audit
    journal('SOURCE_CLOSED')
    if resource.get('failure') or obs is None or not obs.b2_eligible or obs.verification_scope!='INITIAL_STATUS_ONLY':
        audit['facts']='WITHHELD_FRESH_EVIDENCE'
        from .r0_fixed80_qualification import LOCAL
        if resource.get('failure') and resource['failure'] not in LOCAL:audit['stop']=True
        try:audit['readback']=readback(engine,row,admitted['application_id'])
        except Exception:audit.update(transaction='UNCERTAIN_STOP_NO_RETRY',stop=True)
        return audit
    if obs.application_id is not None or obs.reference!=row['reference'] or obs.source_url!=row['source_url']:
        audit.update(facts='WITHHELD_IDENTITY',stop=True);return audit
    obs=replace(obs,application_id=admitted['application_id'])
    journal('B2_TRANSACTION_STARTED')
    try:
        with Session(engine) as s:
            if engine.dialect.name=='postgresql':
                s.execute(text("SET LOCAL statement_timeout='10s'"));s.execute(text("SET LOCAL lock_timeout='3s'"))
            app=s.get(Application,admitted['application_id'])
            handoff=_refresh_row(s,app,get_council('bolton'),dict(row,application_id=app.id),retrieve_evidence=lambda:obs)
            if handoff['outcome']=='PERSISTENCE_FAILED':raise UncertainDiscoveryCommit('B2_COMMIT_UNCERTAIN')
        audit['readback']=readback(engine,row,admitted['application_id'],obs,handoff['accepted'])
        audit.update(facts='INITIAL_FACTS_VERIFIED' if handoff['accepted'] else 'WITHHELD_BY_B2',
            verification_scope=obs.verification_scope,field_states=obs.field_states,
            transaction='COMMIT_READBACK_CONFIRMED',observation_kind='INITIAL_POPULATION_NOT_PROVEN_SOURCE_CHANGE')
        journal('FACTS_COMMIT_READBACK_CONFIRMED')
    except Exception:
        audit.update(facts='UNCERTAIN_COMMIT_OR_READBACK',transaction='UNCERTAIN_STOP_NO_RETRY',stop=True)
    return audit


def run(*,engine_factory,reader=fresh,checkpoint,journal,clock=time.monotonic):
    """Disposable/injected parent; a live registration is deliberately absent."""
    start=clock();result=[];requests=size=0
    for i,row in enumerate(rows()):
        if clock()-start+LIMITS['record_seconds']>LIMITS['seconds']:break
        record_start=clock();journal(i,'RECORD_STARTED');engine=None
        try:
            engine=engine_factory()
            audit=record(engine,row,retrieve=reader,journal=lambda phase:journal(i,phase))
        except Exception:
            audit=dict(council=row['council'],reference=row['reference'],identity='UNKNOWN',facts='UNKNOWN',transaction='UNCERTAIN_STOP_NO_RETRY',stop=True)
        finally:
            if engine is not None:
                try:engine.dispose();journal(i,'ENGINE_DISPOSED')
                except Exception:audit=dict(council=row['council'],reference=row['reference'],transaction='CLEANUP_UNCERTAIN',stop=True)
        result.append(audit)
        # No subsequent record before bounded durable checkpoint and closure.
        try:
            checkpoint(audit);journal(i,'RECORD_CLOSED')
        except Exception:return dict(results=result,stop='CHECKPOINT_UNCERTAIN_NO_NEXT_RECORD')
        a=audit.get('source',{});requests+=a.get('requests',0);size+=a.get('received_body_bytes',0)
        if (audit.get('stop') or 'UNCERTAIN' in audit.get('transaction','')
            or clock()-record_start>LIMITS['record_seconds'] or requests>106 or size>106_000_000):
            return dict(results=result,stop='UNCERTAIN_OR_BOUND_NO_NEXT_RECORD')
    return dict(results=result,stop=None if len(result)==53 else 'AGGREGATE_DEADLINE',requests=requests,received_bytes=size)
