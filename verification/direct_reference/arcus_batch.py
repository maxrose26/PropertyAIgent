"""Arcus profile for the existing bounded batch/B2 transaction machinery."""
import datetime as dt
import hashlib
import json
import math
import re
from urllib.parse import urlsplit,parse_qs
from . import batch
from .arcus_manifest import MANIFEST_SHA256, rows,ORIGINS
from .oldham_production import COUPLED, validate_snapshot as coupled_snapshot, check_consequences, safe_text

CONTEXTS={name:batch.ManifestSpec(name,MANIFEST_SHA256,count,True,'ARCUS')
          for name,count in [('validation',3)]+[('catchup_'+letter,9) for letter in 'abcdef']}

def manifest(spec):
    from .salford15_manifest import CONTEXTS as continuation, manifest as continuation_manifest
    if spec in continuation.values():return continuation_manifest(spec)
    if spec not in CONTEXTS.values():raise ValueError('ARCUS_BATCH_SCOPE')
    all_rows=rows();byid={r['application_id']:r for r in all_rows}
    validation=[byid[i] for i in (688,295,252)]
    remaining=[r for r in all_rows if r['application_id'] not in {688,295,252}]
    groups={'validation':validation,**{'catchup_'+letter:remaining[n*9:(n+1)*9]
                                      for n,letter in enumerate('abcdef')}}
    return [{'identity':r,'policy':'A','selection_stratum':'retained_policy_due'} for r in groups[spec.filename]]

METRICS={'requests','redirects','retries','received_body_bytes','encoded_body_bytes','elapsed_seconds',
         'worker_seconds','peak_owned_rss','owned_processes_seen','live_owned_survivors','navigations','pages',
         'cleanup_state','budget_state','source_sha256'}
def source_record(retrieved,row,limits):
    if set(retrieved)!={'observation','audit','failure'}:raise ValueError('ARCUS_RETRIEVAL_SCHEMA')
    metrics=retrieved['audit']
    if set(metrics)!=METRICS:raise ValueError('ARCUS_METRICS_SCHEMA')
    observation=retrieved['observation']
    source=dict(metrics,family='ARCUS',outcome=retrieved['failure'] or 'LITERAL_VERIFIED',
        verification_scope=None,field_states=None,literal_facts=None,normalized_facts=None)
    if observation is not None:
        if (observation.application_id!=row['application_id'] or observation.reference!=row['reference']
                or observation.source_url!=row['source_url']):raise ValueError('ARCUS_IDENTITY')
        labels={'reference':'Reference','status':'Status','decision':'Decision','decision_date':'Decision Issued Date'}
        source.update(verification_scope=observation.verification_scope,field_states=observation.field_states,
                      literal_facts={k:observation.literal_fields.get(v) for k,v in labels.items()},
                      normalized_facts={k:observation.fields.get(v) for k,v in labels.items()})
    validate_source(source,row)
    if (source['requests']>limits['requests'] or source['received_body_bytes']>limits['bytes']
            or source['elapsed_seconds']>limits['seconds']):raise ValueError('ARCUS_ALLOWANCE')
    return source

def validate_source(s,row):
    if set(s)!=METRICS|{'family','outcome','verification_scope','field_states','literal_facts','normalized_facts'}:raise ValueError('ARCUS_SOURCE_SCHEMA')
    if s['family']!='ARCUS':raise ValueError('SOURCE_FAMILY')
    for key in METRICS-{'cleanup_state','budget_state','source_sha256'}:
        if type(s[key]) not in (int,float) or not math.isfinite(s[key]) or s[key]<0:raise ValueError('UNKNOWN_ACCOUNTING')
    if s['requests']>80 or s['received_body_bytes']>20*1024*1024 or s['elapsed_seconds']>45 or s['peak_owned_rss']>1024**3:raise ValueError('RESOURCE_BOUND')
    if s['pages']>1 or s['navigations']>2 or s['retries']!=0:raise ValueError('NAVIGATION_BOUND')
    if s['cleanup_state']!='CLOSED' or s['live_owned_survivors']!=0:raise ValueError('CLEANUP_FAILURE')
    if s['budget_state'] not in {'WITHIN_LIMITS','EXHAUSTED'}:raise ValueError('BUDGET_STATE')
    if s['outcome'] not in batch.LOCAL|batch.SAFETY|{'LITERAL_VERIFIED'}:raise ValueError('SOURCE_OUTCOME')
    if s['source_sha256'] is not None and not re.fullmatch('[0-9a-f]{64}',s['source_sha256']):raise ValueError('SOURCE_HASH')
    if s['outcome']=='LITERAL_VERIFIED':
        if s['source_sha256'] is None or s['verification_scope'] not in {'COUPLED','FIELD_LEVEL_DATE_ONLY'}:raise ValueError('SOURCE_PROVENANCE')
        for key in ('field_states','literal_facts','normalized_facts'):
            if not isinstance(s[key],dict) or set(s[key])!={'reference','status','decision','decision_date'}:raise ValueError('FIELD_SCHEMA')
        for key,state in s['field_states'].items():
            if state not in {'PRESENT_VALUE','PRESENT_BLANK','NOT_PRESENT','CONFLICTING','UNPARSEABLE','UNKNOWN'}:raise ValueError('FIELD_STATE')
            safe_text(s['literal_facts'][key]);safe_text(s['normalized_facts'][key])
        if s['literal_facts']['reference']!=row['reference'] or s['field_states']['reference']!='PRESENT_VALUE':raise ValueError('REFERENCE')

def validate_snapshot(s):
    if set(s)!={'facts','events'} or set(s['facts'])!=set(COUPLED)|{'last_seen_at','planning_field_verification'}:raise ValueError('ARCUS_SNAPSHOT')
    coupled_snapshot(dict(facts={k:s['facts'][k] for k in COUPLED},events=s['events']))
    if s['facts']['last_seen_at'] is not None:dt.datetime.fromisoformat(s['facts']['last_seen_at'])
    raw=s['facts']['planning_field_verification']
    if raw is None:return
    if not isinstance(raw,str) or len(raw)>8192:raise ValueError('FIELD_METADATA_BOUND')
    metadata=json.loads(raw)
    if set(metadata)!={'status','decision','decision_date'}:raise ValueError('FIELD_METADATA')
    for item in metadata.values():
        if set(item)!={'state','literal','normalized','source_url','body_sha256','verified_at','scope'}:raise ValueError('FIELD_METADATA_KEYS')
        safe_text(item['literal']);safe_text(item['normalized'])
        if item['state'] not in {'PRESENT_VALUE','PRESENT_BLANK','NOT_PRESENT','CONFLICTING','UNPARSEABLE','UNKNOWN'}:raise ValueError('FIELD_STATE')
        u=urlsplit(item['source_url'])
        if u.scheme!='https' or u.netloc not in ORIGINS.values() or not re.fullmatch('/pr/s/detail/[A-Za-z0-9]{18}',u.path) or parse_qs(u.query)!={'c__r':['Arcus_BE_Public_Register']} or u.fragment:raise ValueError('FIELD_SOURCE')
        if item['scope']!='FIELD_LEVEL_DATE_ONLY' or not re.fullmatch('[0-9a-f]{64}',item['body_sha256']):raise ValueError('FIELD_PROVENANCE')
        if item['verified_at'] is not None and dt.datetime.fromisoformat(item['verified_at']).tzinfo is None:raise ValueError('FIELD_TIME')

def validate_record(a,row):
    if set(a)!=set(batch.blank(row)):raise ValueError('RECORD_SCHEMA')
    if any(a[k]!=row[k] for k in ('application_id','reference','council','source_url')):raise ValueError('RECORD_IDENTITY')
    if a['disposition']=='NOT_ATTEMPTED':
        if a!=batch.blank(row):raise ValueError('FALSE_NOT_ATTEMPTED')
        return
    if a['disposition'] not in {'COMPLETED','SAFELY_REJECTED','UNCERTAIN','SAFETY_STOP'}:raise ValueError('DISPOSITION')
    if a['transaction'] not in {'COMMITTED','NOT_COMMITTED','UNKNOWN'}:raise ValueError('TRANSACTION')
    if a['error'] not in {None,'SOURCE_REJECTED','DB_REJECTED','READBACK_MISMATCH','COMMIT_ACK_UNKNOWN','INTERRUPTED','AUDIT_REJECTED','CLEANUP_FAILED','SCOPE_REJECTED'}:raise ValueError('ERROR')
    if a['cleanup'] not in {'CLOSED','FAILED','UNKNOWN'}:raise ValueError('CLEANUP')
    if a['b2_outcome'] not in batch.COMPLETE|batch.LOCAL|batch.SAFETY|{'FIELD_LEVEL_VERIFIED','PERSISTENCE_FAILED','UNKNOWN'}:raise ValueError('B2_OUTCOME')
    if a['source_provenance'] not in {None,'SYNTHETIC_REHEARSAL','FRESH_OFFICIAL_SUMMARY'}:raise ValueError('SOURCE_PROVENANCE')
    for k in ('before','expected','after'):
        if a[k] is not None:validate_snapshot(a[k])
    if a['source'] is not None:
        validate_source(a['source'],row)
        start,end=[dt.datetime.fromisoformat(a[k]) for k in ('retrieval_started_at','retrieval_completed_at')]
        if start.tzinfo is None or end.tzinfo is None or end<start:raise ValueError('SOURCE_TIMING')
    if a['statements'] is not None:
        if set(a['statements'])!={'reads','writes','other','commits','rollbacks','connections','peak_connections'} or any(type(v)is not int or v<0 for v in a['statements'].values()) or a['statements']['peak_connections']>1:raise ValueError('DB_ACCOUNTING')
    if a['transaction']=='COMMITTED':
        if a['before'] is None or a['expected'] is None or a['after']!=a['expected'] or a['source'] is None or a['source']['outcome']!='LITERAL_VERIFIED':raise ValueError('UNPROVED_COMMIT')
        b=a['before']['facts'];after=a['after']['facts'];s=a['source']
        if s['verification_scope']=='FIELD_LEVEL_DATE_ONLY':
            if a['b2_outcome'] not in {'FIELD_LEVEL_VERIFIED','PERSISTENCE_FAILED'}:raise ValueError('FIELD_SCOPE_OUTCOME')
            if any(after[k]!=b[k] for k in ('status','decision','status_verified_at','last_seen_at')):raise ValueError('FIELD_SCOPE_MUTATION')
            metadata=json.loads(after['planning_field_verification'])
            item=metadata['decision_date']
            if item['normalized']!=s['normalized_facts']['decision_date'] or item['literal']!=s['literal_facts']['decision_date'] or item['source_url']!=row['source_url'] or item['body_sha256']!=s['source_sha256']:raise ValueError('FIELD_READBACK')
            if dt.datetime.fromisoformat(item['verified_at'])<end:raise ValueError('FIELD_STAMP')
        elif after['status_verified_at'] is None:raise ValueError('STATUS_STAMP')
        check_consequences(a['before'],a['after'])
    if a['disposition']=='COMPLETED' and (a['transaction']!='COMMITTED' or a['error'] is not None or a['cleanup']!='CLOSED'):raise ValueError('FALSE_COMPLETION')
    if a['disposition']=='SAFELY_REJECTED' and (a['transaction']!='NOT_COMMITTED' or a['before'] is None or a['after']!=a['before'] or a['expected'] is not None or a['b2_outcome'] not in batch.LOCAL or a['cleanup']!='CLOSED'):raise ValueError('FALSE_SAFE_REJECTION')
    if a['transaction']=='UNKNOWN' and a['disposition'] not in {'UNCERTAIN','SAFETY_STOP'}:raise ValueError('FALSE_CERTAINTY')
    batch.encode(a,batch.MAX_RECORD)
