"""Small source-free batch stages in the existing coordinator/ledger contract."""
from copy import deepcopy
import json,re
from .ledger import Denied,digest,bounded

def archive_capture(source,archive):
    raw=json.dumps(source,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if len(raw)>512*1024:raise Denied('SOURCE_AUDIT_BOUND')
    receipt=bounded(archive(raw),4096)
    if (receipt.get('sha256')!=digest(source) or receipt.get('bytes')!=len(raw)
        or receipt.get('readback_verified') is not True or not re.fullmatch('[a-f0-9]{40}',receipt.get('commit',''))
        or not receipt.get('path','').startswith('docs/design/') or '..' in receipt['path'].split('/')):raise Denied('DURABLE_ARCHIVE_NOT_VERIFIED')
    return receipt


def batch_plans(capture_key,capture,screening=None,*,observation_councils=()):
    observation=capture.get('kind')=='LISTING_OBSERVATION_V1'
    if observation:
        if observation_councils!=('bolton',):raise Denied('ARCHIVED_CAPTURE_REQUIRED')
        from .observation_screening import require_enabled
        require_enabled(observation_councils,capture['council'])
    if capture['kind'] not in ('LISTING_RECEIPT_V1','LISTING_OBSERVATION_V1') or not capture.get('durable_archive'):raise Denied('ARCHIVED_CAPTURE_REQUIRED')
    records=capture['records']
    if len(records)>60:raise Denied('ROW_CEILING')
    plans=[];previous=None
    for first in range(0,len(records),5):
        plan=dict(capture_key=capture_key,capture_sha256=digest(capture),first=first,last=min(first+5,len(records)))
        if observation:plan['source_kind']='LISTING_OBSERVATION_V1'
        if screening is not None:
            from .listing_screening import screening_plan_binding
            plan['screening']=screening_plan_binding(screening)[0]      # explicit v3 selection: part of the plan, so part of the batch identity (new keys; the v1 batches are never touched)
        interval=capture['requested_interval'] if observation else capture['interval']
        identity=dict(subject={'kind':'DISCOVERY_SCOPE','council':capture['council'],'start':interval[0],'end':interval[1],'semantics':'RECEIVED'},task='LISTING_METADATA',contract='listing-batch-v1',revision=digest(plan))
        key=digest(identity);plans.append(dict(identity,key=key,dependencies=sorted([capture_key]+([previous] if previous else [])),checkpoint={'kind':'BATCH_PLAN_V1','plan':plan},max_attempts=2));previous=key
    return plans


def capture_once(coordinator,key,reader,archive,check=lambda:None,*,prior_accounting_sha256=None):
    l=coordinator.ledger;check();row=l.get(key)
    if row['checkpoint'] is not None:
        if row['checkpoint'].get('kind')=='LISTING_OBSERVATION_V1':raise Denied('OBSERVATION_IS_NOT_A_CAPTURE')      # specification 033 P6: a partial observation is never returned as a window capture
        if row['state']=='COMPLETE':return row['checkpoint']
        if row['checkpoint'].get('kind')!='LISTING_RECEIPT_V1':raise Denied('CAPTURE_BLOCKED_NO_REFETCH')
        budget=getattr(l,'budget',None)
        if (not budget or budget.slot_key!=key or not budget.previous or budget.previous.get('slot_key')!=key
            or not prior_accounting_sha256 or digest(budget.previous)!=prior_accounting_sha256
            or budget.previous.get('capture_checkpoint_sha256')!=digest(row['checkpoint'])):raise Denied('SEALED_RECOVERY_ACCOUNTING_REQUIRED')
        claim=l.claim(key,lease_seconds=165);l.checkpoint(claim,row['checkpoint'])
        l.finish(claim,dict(outcome='ENUMERATED_METADATA_RETAINED',children=[],source_sha256=row['checkpoint']['source_sha256']))
    else:coordinator.idox_source(l.claim(key,lease_seconds=165),reader,materialize=False,archive=archive)
    check();return l.get(key)['checkpoint']


def _process_batch(coordinator,key,*,check=lambda:None,after_row=lambda _:None,prior_accounting_sha256=None):
    """At most five rows, no source client; existing typed per-row operations.

    Only the complete immutable parent is cached; task claims/progress stay live.
    A completed batch delivery is read-only. No authority or exception issuance.
    """
    l=coordinator.ledger;check();row=l.get(key)
    if row['contract']!='listing-batch-v1' or row['task']!='LISTING_METADATA':raise Denied('BATCH_CONTRACT')
    plan=row['checkpoint']['plan']
    if digest(plan)!=row['revision'] or not 0<=plan['first']<plan['last']<=60 or plan['last']-plan['first']>5:raise Denied('EXACT_BATCH_PLAN')
    from .listing_screening import RULE_V1,screening_plan_binding
    rule=getattr(coordinator,'screening_rule',None)      # a coordinator that predates the registry (historical stubs) is v1
    if plan.get('screening') is None:
        if rule is not None and rule.rule_version!=RULE_V1:raise Denied('BATCH_RULE_MISMATCH')      # a v1 plan is never screened by a v3 coordinator
    elif rule is None or rule.rule_version==RULE_V1 or screening_plan_binding(rule)[0]!=plan['screening']:raise Denied('BATCH_RULE_MISMATCH')      # a v3 plan only by the exact registered rule
    if row['state']=='COMPLETE':return dict(outcome='BATCH_ALREADY_COMPLETE',checkpoint=row['checkpoint'])
    budget=getattr(l,'budget',None)
    if budget is None or budget.slot_key!=key:raise Denied('LOGICAL_BATCH_BUDGET_REQUIRED')
    if budget.previous and (not prior_accounting_sha256 or digest(budget.previous)!=prior_accounting_sha256):raise Denied('SEALED_RECOVERY_ACCOUNTING_REQUIRED')
    if row['attempt_count']>0 and (not budget.previous or budget.previous.get('slot_key')!=key or budget.previous.get('capture_checkpoint_sha256')!=plan['capture_sha256']):raise Denied('RECOVERY_CANNOT_RESET_BUDGET')
    parent=l.get(plan['capture_key']);capture=parent['checkpoint']
    if parent['state']!='COMPLETE' or digest(capture)!=plan['capture_sha256'] or not capture.get('durable_archive'):raise Denied('IMMUTABLE_CAPTURE_REQUIRED')
    if capture.get('kind')=='LISTING_OBSERVATION_V1':
        from .observation_screening import require_enabled
        require_enabled(getattr(coordinator,'observation_councils',()),capture['council'])
        if plan.get('source_kind')!='LISTING_OBSERVATION_V1':raise Denied('OBSERVATION_PLAN_BINDING')
    elif capture.get('kind')!='LISTING_RECEIPT_V1' or 'source_kind' in plan:raise Denied('CAPTURE_KIND_BINDING')
    if plan['last']>len(capture['records']):raise Denied('BATCH_RANGE')
    budget.capture_checkpoint_sha256=plan['capture_sha256']
    claim=l.claim(key,lease_seconds=165);progress=row['checkpoint'];children=list(progress.get('children',[]))
    start=progress.get('next',plan['first'])
    if start==plan['last']:l.batch_row(claim,plan,capture,capture['records'][plan['last']-1],reseal=True)
    for i in range(start,plan['last']):
        check();child,progress=l.batch_row(claim,plan,capture,capture['records'][i]);children.append(child);after_row(i)
    # Reuse the existing screening method while serving its parent from one
    # verified immutable read. No per-row full-capture DB retrieval.
    original_get=l.get
    def cached_get(k):return deepcopy(parent) if k==plan['capture_key'] else original_get(k)
    l.get=cached_get
    try:
        for child in children:
            check();item=l.get(child)
            if item['state']!='COMPLETE':coordinator.screening(l.claim(child,lease_seconds=165))
    finally:l.get=original_get
    l.finish(claim,dict(outcome='BATCH_SCREENED',children=children))
    check();return dict(outcome='BATCH_SCREENED',children=children,checkpoint=progress)


def process_batch(coordinator,key,**kwargs):
    try:return _process_batch(coordinator,key,**kwargs)
    except Exception:
        try:coordinator.ledger.stop('BATCH_SECURITY_IDENTITY_ACCOUNTING_OR_PERSISTENCE_FAILURE')
        except Exception:pass  # Caller must stop/reconcile; never launch next slot.
        raise
