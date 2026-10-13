"""Reviewed manifest batch core. No production CLI, activation or scheduler.

Transport and engine are explicit capabilities. Future registration must wrap
each record in a supervised worker; this module never creates a database engine.
"""
import copy
import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

MANIFEST_SHA256='33882abdafca290400e43a18359d1654fa8a9b80f985ea1aabe54c10003fc1c1'
MAX_RECORD=16384
MAX_BATCH=384*1024
LOCAL={'SOURCE_UNAVAILABLE','TIMEOUT','RATE_LIMITED','PARSER_FAILURE','PARTIAL_RETRIEVAL','STALE_RESPONSE'}
COMPLETE={'VERIFIED_UNCHANGED','VERIFIED_MATERIAL_CHANGE','VERIFIED_NON_MATERIAL_CHANGE','VERIFIED_STATUS_ONLY'}
SAFETY={'AMBIGUOUS_SOURCE_RESULT','SCOPE_ESCAPE','REDIRECT_VIOLATION','PRIVACY_FAILURE',
        'ACCOUNTING_FAILURE','CLEANUP_FAILURE','INVALID_ARTIFACT','UNSUPPORTED_ROUTE'}

def encode(value,limit=MAX_BATCH):
    b=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if len(b)>limit:raise ValueError('AUDIT_BOUND')
    return b

@dataclass(frozen=True)
class ManifestSpec:
    filename: str
    digest: str
    count: int
    catchup: bool = False

REPRESENTATIVE=ManifestSpec('batch-manifest.json',MANIFEST_SHA256,20)

def manifest(spec=None):
    spec=REPRESENTATIVE if spec is None else spec
    if Path(spec.filename).name!=spec.filename or not re.fullmatch('[0-9a-f]{64}',spec.digest):raise ValueError('MANIFEST_SPEC')
    from .refresh import admitted_row
    raw=Path(__file__).with_name(spec.filename).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=spec.digest:raise ValueError('MANIFEST_DIGEST')
    m=json.loads(raw)
    if set(m)!={'schema','selection_seed','census_at','description','rows'} or m['schema']!=1:raise ValueError('MANIFEST_SCHEMA')
    rows=m['rows']
    if not 1<=len(rows)<=20 or len(rows)!=spec.count or len({r['identity']['application_id'] for r in rows})!=len(rows):raise ValueError('MANIFEST_SIZE')
    for r in rows:
        keys={'identity','policy','selection_stratum'}|({'prior_facts','selection_reason'} if spec.catchup else set())
        if set(r)!=keys or r['policy'] not in 'ABCDEF':raise ValueError('MANIFEST_ROW')
        if r['identity']!=admitted_row(r['identity']['application_id']):raise ValueError('MANIFEST_ADMISSION')
    return rows

def blank(row):
    return dict(application_id=row['application_id'],reference=row['reference'],council=row['council'],
        source_url=row['source_url'],source=None,before=None,expected=None,after=None,
        source_provenance=None,retrieval_started_at=None,retrieval_completed_at=None,
        b2_outcome='NOT_ATTEMPTED',transaction='NOT_ATTEMPTED',error=None,cleanup='NOT_STARTED',
        disposition='NOT_ATTEMPTED',statements=None)

def validate_record(a,row):
    from .registration import validate_row
    from .oldham_production import validate_snapshot,check_consequences
    if set(a)!=set(blank(row)):raise ValueError('RECORD_SCHEMA')
    if any(a[k]!=blank(row)[k] for k in ('application_id','reference','council','source_url')):raise ValueError('RECORD_IDENTITY')
    if a['disposition'] not in {'NOT_ATTEMPTED','COMPLETED','SAFELY_REJECTED','UNCERTAIN','SAFETY_STOP'}:raise ValueError('DISPOSITION')
    if a['disposition']=='NOT_ATTEMPTED':
        if a!=blank(row):raise ValueError('FALSE_NOT_ATTEMPTED')
        return
    if a['transaction'] not in {'COMMITTED','NOT_COMMITTED','UNKNOWN'}:raise ValueError('TRANSACTION')
    if a['error'] not in {None,'SOURCE_REJECTED','DB_REJECTED','READBACK_MISMATCH','COMMIT_ACK_UNKNOWN','INTERRUPTED','AUDIT_REJECTED','CLEANUP_FAILED','SCOPE_REJECTED'}:raise ValueError('ERROR')
    if a['cleanup'] not in {'CLOSED','FAILED','UNKNOWN'}:raise ValueError('CLEANUP')
    if a['b2_outcome'] not in COMPLETE|LOCAL|SAFETY|{'PERSISTENCE_FAILED','UNKNOWN'}:raise ValueError('B2_OUTCOME')
    if a['source_provenance'] not in {None,'SYNTHETIC_REHEARSAL','FRESH_OFFICIAL_SUMMARY'}:raise ValueError('SOURCE_PROVENANCE')
    import datetime as dt
    times=[]
    for key in ('retrieval_started_at','retrieval_completed_at'):
        if a[key] is not None:
            value=dt.datetime.fromisoformat(a[key])
            if value.tzinfo is None:raise ValueError('NAIVE_SOURCE_TIME')
            times.append(value)
    if len(times)==2 and times[1]<times[0]:raise ValueError('SOURCE_TIME_ORDER')
    if a['source'] is not None and (len(times)!=2 or a['source_provenance'] is None):raise ValueError('SOURCE_TIMING_REQUIRED')
    for k in ('before','expected','after'):
        if a[k] is not None:validate_snapshot(a[k])
    if a['source'] is not None:validate_row(a['source'],row['application_id'],identity=row)
    if a['statements'] is not None:
        if set(a['statements'])!={'reads','writes','other','commits','rollbacks','connections','peak_connections'}:raise ValueError('DB_ACCOUNTING')
        if any(type(v)is not int or v<0 for v in a['statements'].values()):raise ValueError('DB_ACCOUNTING')
        if a['statements']['peak_connections']>1:raise ValueError('DB_CONCURRENCY')
    if a['transaction']=='COMMITTED':
        if a['before'] is None or a['expected'] is None or a['after']!=a['expected'] or a['source'] is None:raise ValueError('UNPROVED_COMMIT')
        if a['source']['outcome']!='LITERAL_VERIFIED' or a['after']['facts']['status_verified_at'] is None:raise ValueError('PROVENANCE')
        if a['b2_outcome']=='VERIFIED_STATUS_ONLY' or a['source']['field_states']['decision']=='NOT_PRESENT':
            from .refresh import Observation,pending_status_evidence
            s=a['source'];o=Observation(row['application_id'],row['reference'],row['source_url'],s['normalized_facts'],s['field_states'],s['semantic_qualification'],None,s['literal_facts'])
            b=a['before']['facts'];after=a['after']['facts']
            if a['b2_outcome'] not in {'VERIFIED_STATUS_ONLY','PERSISTENCE_FAILED'}:raise ValueError('STATUS_ONLY_OUTCOME')
            if not pending_status_evidence(o) or b['status']!='Awaiting decision' or b['decision'] is not None or b['decision_issued_date'] is not None:raise ValueError('FALSE_STATUS_ONLY')
            if any(after[k]!=v for k,v in b.items() if k!='status_verified_at') or a['before']['events']!=a['after']['events']:raise ValueError('STATUS_ONLY_FACT_MUTATION')
        check_consequences(a['before'],a['after'])
    if a['disposition']=='COMPLETED' and (a['transaction']!='COMMITTED' or a['error'] is not None or a['cleanup']!='CLOSED'):raise ValueError('FALSE_COMPLETION')
    if a['disposition']=='SAFELY_REJECTED' and (a['transaction']!='NOT_COMMITTED' or a['before'] is None or a['after']!=a['before'] or a['expected'] is not None or a['b2_outcome'] not in LOCAL or a['cleanup']!='CLOSED'):raise ValueError('FALSE_SAFE_REJECTION')
    if a['transaction']=='UNKNOWN' and a['disposition'] not in {'UNCERTAIN','SAFETY_STOP'}:raise ValueError('FALSE_CERTAINTY')
    encode(a,MAX_RECORD)

def validate(a,*,spec=None):
    rows=manifest(spec)
    digest=MANIFEST_SHA256 if spec is None else spec.digest
    if set(a)!={'schema','manifest_sha256','repository_sha','invocation','parent_audit_sha256','records','carried_ids','assessment','totals'}:raise ValueError('BATCH_SCHEMA')
    if a['schema']!=1 or a['manifest_sha256']!=digest or not re.fullmatch('[0-9a-f]{40}',a['repository_sha']):raise ValueError('BATCH_IDENTITY')
    if not re.fullmatch('[A-Za-z0-9_-]{1,64}',a['invocation']):raise ValueError('INVOCATION')
    if a['parent_audit_sha256'] is not None and not re.fullmatch('[0-9a-f]{64}',a['parent_audit_sha256']):raise ValueError('PARENT_AUDIT')
    if len(a['records'])!=len(rows):raise ValueError('ALL_RECORDS_REQUIRED')
    ids={r['identity']['application_id'] for r in rows}
    if len(set(a['carried_ids']))!=len(a['carried_ids']) or set(a['carried_ids'])-ids:raise ValueError('CARRY_SCOPE')
    for item,r in zip(a['records'],rows):validate_record(item,r['identity'])
    for item in a['records']:
        if item['application_id'] in a['carried_ids'] and item['disposition'] not in {'COMPLETED','SAFELY_REJECTED'}:raise ValueError('UNSAFE_CARRY')
    actual=totals(a['records'],a['carried_ids'])
    if actual!=a['totals']:raise ValueError('TOTALS')
    assessment='STOPPED_REVIEW_REQUIRED' if any(r['disposition'] in {'UNCERTAIN','SAFETY_STOP','NOT_ATTEMPTED'} for r in a['records']) else 'ACCOUNTED'
    if a['assessment']!=assessment:raise ValueError('ASSESSMENT')
    stopped=False
    for item in a['records']:
        if item['application_id'] in a['carried_ids']:continue
        if stopped and item['disposition']!='NOT_ATTEMPTED':raise ValueError('CONTINUED_AFTER_SAFETY_STOP')
        if item['disposition'] in {'UNCERTAIN','SAFETY_STOP'}:stopped=True
    encode(a)

def totals(records,carried):
    source=[r['source'] for r in records if r['source'] is not None and r['application_id'] not in carried]
    out={k:sum(r[k] for r in source) for k in ('requests','redirects','retries','received_body_bytes','elapsed_seconds')}
    if out['requests']>40 or out['received_body_bytes']>20_000_000 or out['elapsed_seconds']>150:raise ValueError('GLOBAL_SOURCE_BOUND')
    # Observed redirects are never followed; retain their truthful count as a
    # safety failure rather than erasing the record to force a zero counter.
    if any(r['source'] is None and r['disposition'] in {'UNCERTAIN','SAFETY_STOP'} and r['application_id'] not in carried for r in records):
        return {k:'UNKNOWN' for k in out}
    return out

def run(repository_sha,invocation,execute_record,*,prior=None,prior_sha256=None,clock=time.monotonic,spec=None):
    """Explicit capability injection; no activation from import or arbitrary IDs.

    Resume carries completed/safely rejected records only. Any uncertainty or
    safety stop requires REVIEW resolution before a new manifest/invocation.
    Local rejections are terminal for this refresh epoch; future refresh requires
    a separately reviewed invocation, never automatic retries.
    """
    rows=manifest(spec);records=[blank(r['identity']) for r in rows];carried=[]
    if prior is not None:
        validate(prior,spec=spec)
        if hashlib.sha256(encode(prior)).hexdigest()!=prior_sha256:raise ValueError('RESUME_DIGEST')
        if prior['repository_sha']!=repository_sha or prior['invocation']==invocation:raise ValueError('RESUME_IDENTITY')
        if any(r['disposition'] in {'UNCERTAIN','SAFETY_STOP'} for r in prior['records']):raise ValueError('RESUME_REQUIRES_REVIEW')
        for n,r in enumerate(prior['records']):
            if r['disposition'] in {'COMPLETED','SAFELY_REJECTED'}:records[n]=copy.deepcopy(r);carried.append(r['application_id'])
    elif prior_sha256 is not None:raise ValueError('RESUME_MISSING')
    started=clock()
    for n,entry in enumerate(rows):
        row=entry['identity']
        if row['application_id'] in carried:continue
        if clock()-started>=300:break
        used=totals(records,carried)
        if used['requests']>=40 or used['received_body_bytes']>=20_000_000 or used['elapsed_seconds']>=150:break
        limits=dict(requests=min(2,40-used['requests']),bytes=min(2_000_000,20_000_000-used['received_body_bytes']),seconds=min(40,150-used['elapsed_seconds']),worker_seconds=min(45,300-(clock()-started)))
        try:
            result=execute_record(copy.deepcopy(row),limits)
            validate_record(result,row)
            candidate=copy.deepcopy(records);candidate[n]=result
            totals(candidate,carried)
            records[n]=result
        except Exception:
            # Never infer absence of a commit from an exception/missing audit.
            records[n]=blank(row);records[n].update(b2_outcome='UNKNOWN',transaction='UNKNOWN',error='AUDIT_REJECTED',cleanup='UNKNOWN',disposition='UNCERTAIN')
            break
        if result['disposition'] in {'UNCERTAIN','SAFETY_STOP'}:break
    out=dict(schema=1,manifest_sha256=MANIFEST_SHA256 if spec is None else spec.digest,repository_sha=repository_sha,invocation=invocation,
        parent_audit_sha256=prior_sha256,records=records,carried_ids=carried,assessment='ACCOUNTED',totals=totals(records,carried))
    if any(r['disposition'] in {'UNCERTAIN','SAFETY_STOP','NOT_ATTEMPTED'} for r in records):out['assessment']='STOPPED_REVIEW_REQUIRED'
    validate(out,spec=spec);return out
