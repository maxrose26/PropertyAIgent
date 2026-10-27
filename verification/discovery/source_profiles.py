"""Closed collection profiles, not source qualification or operational authority."""
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import urlsplit
from app.pipeline.discovery_contract import SOURCE_ROOTS
from . import finite_acceptance as finite
from .arcus_ui_config import UI_CASES, dated_config, assessment_dated_config

VERSION = 'COUNCIL_COLLECTION_PROFILE_V1'
MODES = frozenset({'IDENTITY_ONLY', 'SCREENING_METADATA'})
_active = ContextVar('collection_profile', default=None)


def profile(row, mode):
    from .campaign_manifest import require_row
    require_row(row, profiled=True)
    if mode not in MODES:raise ValueError('COLLECTION_MODE')
    council=row['council'];arc=council in finite.ARCUS
    case='discovery_'+council+'_ui_window' if arc else 'IDOX_WINDOW'
    destination=(dated_config(UI_CASES[case],row['start'],row['end']).destination if arc else
        'https://'+SOURCE_ROOTS[council][0]+SOURCE_ROOTS[council][1].rstrip('/')+'/search.do?action=advanced&searchType=Application')
    value=dict(version=VERSION,council=council,semantics=row['semantics'],interval=[row['start'],row['end']],
        family='ARCUS_UI' if arc else 'IDOX',case=case,destination=destination,host=urlsplit(destination).hostname,
        collection_mode=mode,execution_budget='BROWSER_SOURCE_V2' if arc else None,
        validator='ARCUS_UI_AUDIT_V1' if arc else 'IDOX_COUNT_RECONCILED_V1',proof='FOUR_COUNCIL_STRUCTURAL_PROOF_V1')
    return dict(value,sha256=finite.digest(value))


def validate(value, row=None):
    if not isinstance(value,dict):raise ValueError('COLLECTION_PROFILE')
    if row is None:
        row=dict(council=value.get('council'),semantics=value.get('semantics'),
            start=value.get('interval',[None,None])[0],end=value.get('interval',[None,None])[1])
    if value!=profile(row,value.get('collection_mode')):raise ValueError('COLLECTION_PROFILE_BINDING')
    return value


def config(value):
    validate(value)
    if value['family']!='ARCUS_UI':raise ValueError('ARCUS_PROFILE_REQUIRED')
    factory=assessment_dated_config if value['collection_mode']=='SCREENING_METADATA' else dated_config
    return factory(UI_CASES[value['case']],*value['interval'])


def current():
    value=_active.get()
    return dict(value) if value is not None else None


@contextmanager
def selected(value):
    validate(value);token=_active.set(dict(value))
    try:yield
    finally:_active.reset(token)


def bind_audit(value, audit):
    """Validate routing/mode before tagging the returned source audit."""
    validate(value)
    if audit.get('requested_interval')!=value['interval'] or audit.get('date_semantics')!=value['semantics']:
        raise ValueError('PROFILE_AUDIT_SCOPE')
    if value['family']=='ARCUS_UI':
        if audit.get('case')!=value['case'] or audit.get('destination')!=value['destination']:raise ValueError('PROFILE_AUDIT_ROUTE')
        if audit.get('execution_budget')!=value['execution_budget']:raise ValueError('PROFILE_AUDIT_BUDGET')
        from app.ingestion.coordinator import canonical_rows
        rows=canonical_rows(audit.get('listing_records',[]))
        from .arcus_ui_window import qualify_segment
        c=config(value)
        for row in rows:
            fields=[dict(label='Reference',value=row['reference'])]
            if c.row_date:fields.append(dict(label='Valid Date',value=row['validated_date']['literal']))
            card=dict(fields=fields,links=[dict(text=row['reference'],href=row['source_url'])])
            if value['collection_mode']=='SCREENING_METADATA':card['assessment_capture']=row['assessment_capture']
            elif 'assessment_capture' in row:raise ValueError('PROFILE_AUDIT_MODE')
            if qualify_segment('Showing 1 to 1 of 1 results',[card],1,config=c)[3][0]!=row:raise ValueError('PROFILE_METADATA_SHAPE')
    else:
        if audit.get('execution_budget') is not None:raise ValueError('PROFILE_AUDIT_BUDGET')
        if audit.get('council')!=value['council']:raise ValueError('PROFILE_AUDIT_ROUTE')
        from datetime import date
        from app.ingestion.idox_adapter import validate_listing_record
        from .idox_window import WindowConfig
        c=WindowConfig(value['council'],value['semantics'],*map(date.fromisoformat,value['interval']),max_transport_retries=0)
        keys,refs=set(),set()
        for row in audit.get('records',[]):validate_listing_record(c,row,keys,refs)
    if 'collection_profile' in audit and audit['collection_profile']!=value:raise ValueError('PROFILE_AUDIT_SUBSTITUTION')
    return dict(audit,collection_profile=value)


def validate_audit(value,audit):
    if audit.get('collection_profile')!=value:raise ValueError('PROFILE_AUDIT_BINDING')
    bind_audit(value,audit)
    return audit
