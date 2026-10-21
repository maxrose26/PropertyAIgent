"""Read-only projections over stored screening items (specification 035 / PR #171 slice 1). Nothing here writes, supersedes, schedules or executes anything.

`assessment_history` lists every stored assessment of one source record, side by side, with no recency or "current" implied. `investigation_requirements` lists the questions a v3 result leaves open.
A requirement is a RECORDED QUESTION: `executable` is always false and `executor` is always 'NONE' because no executor exists for ledger-held identities; recording one performs no investigation."""
from .listing_screening import RULE_V1,RULE_V3,routing_of

NOTE='recorded requirement; no executor exists for ledger-held identities'

# reason code (count_assessment reason of a ROUTE_COUNT_UNCONFIRMED result) -> requirement kinds. Unlisted reasons still produce a requirement (REVIEW_REQUIRED): an uncertain case is never dropped.
REQUIREMENT_KINDS={
    'RESERVED_MATTERS_WITHOUT_STATED_COUNT':('PARENT_REFERENCE_RESOLUTION','COUNT_FROM_PHASE_DOCUMENTS'),
    'RESIDENTIAL_WITHOUT_STATED_COUNT':('COUNT_CONFIRMATION',),
    'MIXED_USE_WITHOUT_STATED_RESIDENTIAL_COUNT':('COUNT_CONFIRMATION',),
    'AMBIGUOUS_PER_GROUP_COUNT':('COUNT_CLARIFICATION',),
    'COUNT_WORDING_NOT_PARSED':('COUNT_CLARIFICATION',),
    'MULTIPLE_PROPOSED_DWELLING_COUNTS':('COUNT_CLARIFICATION',),
    'STUDENT_ACCOMMODATION_IN_MIXED_SCHEME':('COUNT_CLARIFICATION',),
    'POSSIBLE_BREAKDOWN_OF_A_TOTAL':('COUNT_CLARIFICATION',),
    'REPEATED_COUNT':('COUNT_CLARIFICATION',)}


def _view(item):
    """(item_key, contract, rule_version, config_sha256, record_sha256, result) of one stored SCREENING item, or None when it holds no screening result."""
    result=item.get('checkpoint')
    if item.get('task')!='SCREENING' or not isinstance(result,dict) or 'rule_version' not in result:return None
    record_sha=result.get('record_sha256') or (item.get('revision') if result['rule_version']==RULE_V1 else None)
    return dict(item_key=item['key'],contract=item['contract'],rule_version=result['rule_version'],config_sha256=result.get('config_sha256'),record_sha256=record_sha,result=result,subject=item['subject'])


def assessment_history(items,subject,record_sha256):
    """Every stored assessment of the same source record under the same subject, in a STABLE order (rule version, configuration digest, item key). The order says nothing about recency and no entry is marked
    current, latest, preferred or superseding: a later assessment never replaces an earlier one, and the factual evidence of an earlier item is untouched by a newer screening version."""
    out=[]
    for item in items:
        v=_view(item)
        if v is None or v['subject']!=subject or v['record_sha256']!=record_sha256:continue
        try:authority,outcome=routing_of(v['result'])
        except ValueError:authority=outcome=None
        out.append(dict(item_key=v['item_key'],contract=v['contract'],rule_version=v['rule_version'],config_sha256=v['config_sha256'],record_sha256=v['record_sha256'],routing_authority=authority,routing_outcome=outcome,
                        relation='OTHER_ASSESSMENT_OF_SAME_RECORD'))
    return sorted(out,key=lambda e:(e['rule_version'],e['config_sha256'] or '',e['item_key']))


def investigation_requirements(items):
    """One entry per (v3 screening item, requirement kind) for every result that is not final: ROUTE_COUNT_UNCONFIRMED (the reason code decides the kinds) and ADMIT_FOR_ASSESSMENT (a qualified maximum that still
    needs targeted document extraction). A parent's figure is shown only as CONTEXT_ONLY and is never copied into any total."""
    out=[]
    for item in items:
        v=_view(item)
        if v is None or v['rule_version']!=RULE_V3:continue
        try:authority,outcome=routing_of(v['result'])
        except ValueError:continue
        ca=v['result']['count_assessment']
        if outcome=='ROUTE_COUNT_UNCONFIRMED':kinds=REQUIREMENT_KINDS.get(ca.get('reason'),('REVIEW_REQUIRED',))
        elif outcome=='ADMIT_FOR_ASSESSMENT':kinds=('TARGETED_DOCUMENT_EXTRACTION',)
        else:continue
        for kind in kinds:
            out.append(dict(subject=v['subject'],assessment_item=v['item_key'],record_sha256=v['record_sha256'],requirement_kind=kind,reason=ca.get('reason'),routing_outcome=outcome,
                            parent_context=dict(relation='CONTEXT_ONLY',value=ca.get('parent_context')) if ca.get('parent_context') else None,executable=False,executor='NONE',note=NOTE))
    return sorted(out,key=lambda e:(e['assessment_item'],e['requirement_kind']))


def screening_items(ledger):
    """Read every SCREENING item of a (disposable) ledger as plain dicts. Read-only."""
    from sqlalchemy import select
    from .schema import WorkItem as W
    with ledger.engine.connect() as c:
        return [dict(r) for r in c.execute(select(W).where(W.c.task=='SCREENING')).mappings()]
