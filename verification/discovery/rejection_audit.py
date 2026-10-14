"""Bounded observation diagnostics only; never decides eligibility or writes facts."""
from datetime import datetime, timezone
import re

LABELS = {'reference':'Reference','status':'Status','decision':'Decision','decision_date':'Decision Issued Date'}
STATES = {'PRESENT_VALUE','PRESENT_BLANK','NOT_PRESENT','CONFLICTING','UNPARSEABLE','UNKNOWN'}
SCOPES = {'COUPLED','INITIAL_STATUS_ONLY','FIELD_LEVEL_DATE_ONLY','UNCHANGED_PENDING_STATUS_ONLY'}


def observation_audit(row, resource):
    """Export only qualified planning fields, including a truthfully rejected scope."""
    obs=resource.get('observation')
    audit=dict(requested_reference=row['reference'],retrieved_at=datetime.now(timezone.utc).isoformat(),
        identity_qualification='NOT_QUALIFIED',displayed_reference=None,field_states={},
        supported_literal_facts={},verification_scope='UNKNOWN',b2_eligible=False,
        rejection_reason='NO_QUALIFIED_OBSERVATION',diagnostic_conditions=[])
    if obs is None:
        return audit
    if obs.reference != row['reference'] or obs.source_url != row['source_url']:
        raise ValueError('audit identity mismatch')
    if type(obs.b2_eligible) is not bool or type(obs.literal_verified) is not bool:
        raise ValueError('audit qualification type')
    digest=obs.body_sha256
    if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):
        raise ValueError('audit fingerprint')
    audit.update(identity_qualification='EXACT_DISPLAYED_REFERENCE' if obs.literal_verified else 'NOT_QUALIFIED',
        displayed_reference=obs.fields.get('Reference'),source_url=row['source_url'],body_sha256=digest,
        b2_eligible=obs.b2_eligible,
        verification_scope=obs.verification_scope if obs.verification_scope in SCOPES else 'UNSUPPORTED_SCOPE',
        rejection_reason=None if obs.b2_eligible else 'B2_EVIDENCE_SCOPE_INELIGIBLE')
    if not isinstance(audit['displayed_reference'],str) or audit['displayed_reference'] != row['reference']:
        raise ValueError('audit displayed identity')
    for key,label in LABELS.items():
        state=obs.field_states.get(key,'MISSING_FIELD')
        if state not in STATES | {'MISSING_FIELD'}:
            raise ValueError('audit field state')
        audit['field_states'][key]=state
        if state in {'MISSING_FIELD','NOT_PRESENT','CONFLICTING','UNPARSEABLE','UNKNOWN'}:
            audit['diagnostic_conditions'].append(key.upper()+'_'+state)
        if label in obs.literal_fields:
            value=obs.literal_fields[label]
            if value is None: continue
            if not isinstance(value,str) or len(value)>160:
                raise ValueError('audit literal bound')
            audit['supported_literal_facts'][label]=value
    if audit['verification_scope']=='UNSUPPORTED_SCOPE':
        audit['diagnostic_conditions'].append('UNSUPPORTED_VERIFICATION_SCOPE')
    if getattr(obs,'semantic_state',None)=='UNKNOWN_UNMAPPED':
        audit['diagnostic_conditions'].append('SOURCE_SEMANTIC_STATE_UNKNOWN_UNMAPPED')
    return audit
