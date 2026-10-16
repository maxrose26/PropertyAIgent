"""Selective qualified new identity -> existing admission/B2 -> committed readback.

No source client or new factual semantics. Caller supplies retained fresh source
from the existing qualified projector. No pending identity for unsupported facts.
"""
from dataclasses import dataclass,replace
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.models import Application
from .ledger import Denied,UncertainPersistence


@dataclass(frozen=True)
class NewIdentityContract:
    name: str
    row: dict
    projector: object
    handoff: object
    coupled_gate: object
    verification_scope: str='COUPLED'

    def __post_init__(self):
        if not all(callable(x) for x in (self.projector,self.handoff,self.coupled_gate)):raise Denied('QUALIFIED_FACTUAL_COMPONENTS_REQUIRED')
        if self.verification_scope not in {'COUPLED','INITIAL_STATUS_ONLY'} or self.row.get('application_id') is not None:
            raise Denied('NEW_IDENTITY_ACCEPTED_CONTRACT')


def execute(coordinator,claim,*,envelope,council,source):
    from app.pipeline.discovery_admission import admit_identity,PROTECTED_FIELDS
    from app.pipeline.discovery_contract import Completeness
    ledger=coordinator.ledger;row=ledger.get(claim.key);contract=coordinator.contracts.get(row['contract'])
    if not isinstance(contract,NewIdentityContract) or row['task']!='FACTUAL_REFRESH' or len(row['dependencies'])!=1:raise Denied('NEW_IDENTITY_TASK')
    target=contract.row
    if (row['subject']!={'kind':'APPLICATION','council':envelope.council,'reference':envelope.reference}
        or (target['council'],target['reference'],target['source_url'])!=(envelope.council,envelope.reference,envelope.source_url)
        or council.code!=envelope.council or envelope.window.outcome!=Completeness.COMPLETE):raise Denied('NEW_IDENTITY_BINDING')
    parent=ledger.get(row['dependencies'][0]);screen=parent['checkpoint']
    if parent['state']!='COMPLETE' or parent['task']!='SCREENING' or parent['subject']!=row['subject'] or not screen or screen.get('disposition') not in {'SUPPORTED_PROCESSING_PRIORITY','RELATED_APPLICATION_FOLLOW_THROUGH'}:
        raise Denied('SELECTIVE_SCREENING_REQUIRED')
    def lookup():
        with Session(ledger.engine) as s:
            a=s.scalar(select(Application).where(Application.council_code==envelope.council,Application.reference==envelope.reference))
            if a is None:return None
            return dict(application_id=a.id,protected={k:(getattr(a,k).isoformat() if hasattr(getattr(a,k),'isoformat') else getattr(a,k)) for k in PROTECTED_FIELDS})
    prior=row['checkpoint']
    if prior and prior.get('outcome')=='SUPPORTED_FACTS_VERIFIED':
        if lookup()!=prior['readback']:ledger.stop('COMMITTED_READBACK_CHANGED');raise Denied('RECONCILIATION_REQUIRED')
        ledger.finish(claim,prior);return prior
    known=lookup()
    if known:
        result=dict(outcome='ALREADY_KNOWN',identity='EXISTING_IDENTITY_PRESERVED',facts='EXISTING_NOT_WRITTEN',application_id=known['application_id'])
        ledger.checkpoint(claim,result);ledger.finish(claim,result);return result
    # SAME projector as the accepted Idox qualification, including identity,
    # field states, owned-process bounds, cleanup and exact factual scope.
    packet=contract.projector(target,source);obs=packet['observation']
    if packet['failure'] or obs is None or not obs.b2_eligible or obs.verification_scope!=contract.verification_scope or (obs.verification_scope=='COUPLED' and not contract.coupled_gate(obs,target)):
        result=dict(outcome='FACTS_WITHHELD',identity='NOT_CREATED',reason=packet['failure'] or 'UNSUPPORTED_FACTUAL_SCOPE')
        ledger.checkpoint(claim,result);ledger.finish(claim,result,state='UNSUPPORTED_CONTRACT',reason='SUPPORTED_FACTS_REQUIRED');return result
    if obs.application_id is not None:raise Denied('NEW_IDENTITY_OBSERVATION')
    if screen.get('source_url')!=envelope.source_url or screen.get('source_record_id')!=envelope.source_record_id:raise Denied('SCREENING_SOURCE_BINDING')
    def writer(_):
        admitted=admit_identity(ledger.engine,envelope)
        # Admission uniqueness may lose a race; preserve the winner unchanged.
        if admitted['outcome']=='ALREADY_KNOWN':return dict(outcome='ALREADY_KNOWN',identity='EXISTING_IDENTITY_PRESERVED',facts='EXISTING_NOT_WRITTEN',application_id=admitted['application_id'],cleanup='CLOSED',accounting_complete=True)
        app_id=admitted['application_id'];bound_obs=replace(obs,application_id=app_id)
        with Session(ledger.engine) as s:
            a=s.get(Application,app_id)
            handoff=contract.handoff(s,a,council,dict(target,application_id=app_id),retrieve_evidence=lambda:bound_obs)
        if not handoff['accepted']:raise RuntimeError('ADMISSION_COMMITTED_B2_NOT_ACCEPTED_RECONCILE')
        after=lookup()
        if after is None or after['application_id']!=app_id:raise RuntimeError('COMMITTED_READBACK_MISSING')
        metadata=__import__('json').loads(after['protected']['planning_field_verification'] or '{}')
        expected={'status':'Status','decision':'Decision','decision_date':'Decision Issued Date'}
        names={'status':'status','decision':'decision','decision_date':'decision_issued_date'}
        for field,label in expected.items():
            if contract.verification_scope=='INITIAL_STATUS_ONLY' and field!='status':continue
            if (after['protected'][names[field]]!=bound_obs.fields[label]
                or (contract.verification_scope=='INITIAL_STATUS_ONLY' and (metadata.get(field,{}).get('body_sha256')!=bound_obs.body_sha256 or not metadata.get(field,{}).get('verified_at')))
                or (contract.verification_scope=='COUPLED' and not after['protected']['status_verified_at'])):raise RuntimeError('COMMITTED_FACT_READBACK_UNRESOLVED')
        return dict(outcome='SUPPORTED_FACTS_VERIFIED',identity='COMMITTED_PENDING_IDENTITY',application_id=app_id,
            verification_scope=contract.verification_scope,readback=after,unit_facts='NOT_WRITTEN',cleanup='CLOSED',accounting_complete=True)
    ledger.intent(claim,'writes',cost=2) # identity transaction + B2 transaction
    result=ledger.fenced_effect(claim,writer)
    ledger.finish(claim,result);return result
