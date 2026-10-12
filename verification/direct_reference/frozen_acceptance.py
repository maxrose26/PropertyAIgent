"""Frozen LIVE_SOURCE_OBSERVATION translation for DISPOSABLE rehearsal only.

No network, writer or production caller. Exact retrieval instants/body hashes
were not retained in the live audit and must not be invented.
"""
import copy
import hashlib
import json
import os
from pathlib import Path

LIVE_SHA256='8f717b99ef386ee793095bc9e8f3ea64377cf762535e3fba2ffdb18eba9b9cd4'
RUN_ID='38310507094'
SOURCE_SHA='a0feeb7c1cd39c979e2a9018b82d764d1edcd76b'
PROVENANCE=dict(qualification='LIVE_SOURCE_OBSERVATION',run_id=RUN_ID,source_sha=SOURCE_SHA,
 artifact_id=11774039334,audit_sha256=LIVE_SHA256,
 retrieval_window_utc=['2026-10-12T21:25:24Z','2026-10-12T21:25:34Z'],
 exact_retrieval_timestamp=None,source_body_sha256=None,
 persistence_context='DISPOSABLE_REPLAY_NOT_CURRENT_VERIFICATION')


def load_live():
    data=Path(__file__).with_name('live-observations-38310507094.json').read_bytes()
    if hashlib.sha256(data).hexdigest()!=LIVE_SHA256:raise ValueError('Live fixture digest')
    a=json.loads(data)
    from .registration import aggregate
    if (a['repository_sha']!=SOURCE_SHA or a['run_id']!=RUN_ID or a['mode']!='live'
        or aggregate(SOURCE_SHA,'live',a['results'],RUN_ID)!=a):raise ValueError('Live provenance')
    return a


def frozen_observation(application_id):
    if os.environ.get('B20_DISPOSABLE')!='YES_SYNTHETIC_ONLY' or os.environ.get('DATABASE_URL'):
        raise ValueError('Frozen live observations are not production refresh evidence')
    from .refresh import Observation
    row=next(r for r in load_live()['results'] if r['application_id']==application_id)
    missing=any(row['field_states'][k]=='NOT_PRESENT' for k in ('decision','decision_date'))
    return Observation(application_id,row['reference'],row['source_url'],
      copy.deepcopy(row['normalized_facts']),copy.deepcopy(row['field_states']),
      row['semantic_qualification'],None,copy.deepcopy(row['literal_facts']),
      b2_eligible=not missing and row['semantic_qualification']!='UNKNOWN_UNMAPPED')


# Minimum future audit schema. Values are obtained from B2/readback, not a new writer.
AUDIT_KEYS={'application_id','reference','source_provenance','retrieval_started_at',
 'retrieval_completed_at','outcome','before','qualified_incoming','after',
 'verification_watermark_before','verification_watermark_after','material_change',
 'field_states','semantic_qualification','transaction_result','lifecycle_before','lifecycle_after','refresh_signal_before',
 'refresh_signal_after','error_qualification'}
FACT_KEYS={'status','decision','decision_date'}


def validate_persistence_audit(a):
    if set(a)!=AUDIT_KEYS:raise ValueError('Closed persistence audit')
    if type(a['application_id']) is not int or a['application_id'] not in (42,78,202):raise ValueError('Identity')
    live=next(r for r in load_live()['results'] if r['application_id']==a['application_id'])
    if a['reference']!=live['reference']:raise ValueError('Reference')
    expected={k:live['normalized_facts'][f] for k,f in [('status','Status'),('decision','Decision'),('decision_date','Decision Issued Date')]}
    if a['qualified_incoming']!=expected:raise ValueError('Incoming frozen facts')
    if a['field_states']!=live['field_states'] or a['semantic_qualification']!=live['semantic_qualification']:raise ValueError('Evidence qualification')
    for k in ('before','qualified_incoming','after'):
        if set(a[k])!=FACT_KEYS:raise ValueError('Only coupled planning facts')
    # Closed nested schemas prevent arbitrary source bodies/error strings.
    if set(a['source_provenance'])!=set(PROVENANCE) or a['source_provenance']!=PROVENANCE:raise ValueError('Frozen source provenance')
    if a['error_qualification'] not in (None,'WITHHELD_PARTIAL','REJECTED','STALE_RESPONSE','ROLLED_BACK','COMMIT_ACK_UNKNOWN'):raise ValueError('Bounded error')
    if len(json.dumps(a,default=str).encode())>16384:raise ValueError('Audit ceiling')
    import datetime as dt
    import re
    for k in ('retrieval_started_at','retrieval_completed_at','verification_watermark_before','verification_watermark_after'):
        v=a[k]
        if v is not None:
            if not isinstance(v,str) or len(v)>40:raise ValueError('Timestamp')
            dt.datetime.fromisoformat(v)
    for group in ('before','qualified_incoming','after'):
        for k,v in a[group].items():
            if v is not None and (not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9 ()/.,:;-]{1,256}',v)):raise ValueError('Bounded fact')
    if a['outcome'] not in {'VERIFIED_MATERIAL_CHANGE','VERIFIED_NON_MATERIAL_CHANGE','VERIFIED_UNCHANGED','PARTIAL_RETRIEVAL','STALE_RESPONSE','PERSISTENCE_FAILED','PARSER_FAILURE','AMBIGUOUS_SOURCE_RESULT'}:raise ValueError('Outcome')
    if a['transaction_result'] not in {'COMMITTED','REJECTED_NO_WRITE','ROLLED_BACK','COMMIT_ACK_UNKNOWN'}:raise ValueError('Transaction')
    if a['material_change'] not in (True,False,'UNKNOWN'):raise ValueError('Materiality')
    for k in ('lifecycle_before','lifecycle_after'):
        if not isinstance(a[k],list) or len(a[k])>10:raise ValueError('Lifecycle bound')
        for e in a[k]:
            if set(e)!={'event_type','field_name','old_value','new_value','authoritative_source'}:raise ValueError('Lifecycle schema')
            if e['event_type'] not in {'decision_refused','decision_granted','decision_withdrawn','status_changed'} or e['field_name'] not in {'status','decision','decision_issued_date'} or e['authoritative_source']!='status_verification':raise ValueError('Lifecycle scope')
            if any(v is not None and (not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9 ()/.,:;-]{1,256}',v)) for v in e.values()):raise ValueError('Lifecycle fact')
    for k in ('refresh_signal_before','refresh_signal_after'):
        v=a[k]
        if set(v)!={'required','reason','trigger','requested_at'} or type(v['required']) is not bool:raise ValueError('Signal schema')
        if v['reason'] not in (None,'decision_refused') or v['trigger'] not in (None,'material_change'):raise ValueError('Signal scope')
        if v['requested_at'] is not None:dt.datetime.fromisoformat(v['requested_at'])
