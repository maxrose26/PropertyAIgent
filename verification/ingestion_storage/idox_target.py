"""Closed, sealed detail configurations for three dormant Idox caller bindings."""
from app.ingestion.ledger import Denied,digest
from verification.stage26b_l1.request_boundary import BoundaryFailure
from app.scrapers.discovery_idox import source_url

COUNCILS=frozenset({'bury','oldham','stockport'})
KEYS={'admission','platform_family','application_id','application_role','site_relationship',
      'case','council','reference','source_identifier','source_url','verification_scope','record_sha256','target_sha256'}


def derive(council,record):
    if council not in COUNCILS:raise Denied('CLOSED_IDOX_COUNCIL')
    try:
        url,key=source_url(council,record['source_url'])
        if url!=record['source_url'] or key!=record['source_record_id']:raise ValueError
        reference=record['reference']
        if not isinstance(reference,str) or not reference or reference!=reference.strip():raise ValueError
        from verification.direct_reference.refresh import validate_destination
        sha=digest(record)
        value=dict(admission='ADMITTED_DIRECT_ROUTE',platform_family='IDOX',application_id=None,
            application_role='UNKNOWN',site_relationship='UNKNOWN',case=f'chain_idox_{council}_{sha}',
            council=council,reference=reference,source_identifier=key,source_url=url,
            verification_scope='COUPLED',record_sha256=sha)
        validate_destination(value)
    except (ValueError,KeyError,TypeError,BoundaryFailure):raise Denied('CLOSED_IDOX_RECORD') from None
    return validate(dict(value,target_sha256=digest(value)))


def validate(target):
    """Private source child cannot trust even its parent's serialised configuration."""
    try:
        if not isinstance(target,dict) or set(target)!=KEYS:raise ValueError
        c=target['council'];sha=target['record_sha256']
        import re
        if c not in COUNCILS or not isinstance(sha,str) or not re.fullmatch('[a-f0-9]{64}',sha):raise ValueError
        if (target['case']!=f'chain_idox_{c}_{sha}' or target['verification_scope']!='COUPLED'
            or target['application_id'] is not None or target['application_role']!='UNKNOWN' or target['site_relationship']!='UNKNOWN'
            or target['target_sha256']!=digest({k:v for k,v in target.items() if k!='target_sha256'})):raise ValueError
        from verification.direct_reference.refresh import validate_destination
        validate_destination(target)
        url,key=source_url(c,target['source_url'])
        if url!=target['source_url'] or key!=target['source_identifier']:raise ValueError
        ref=target['reference']
        if not isinstance(ref,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/._ -]{0,99}',ref) or ref!=ref.strip():raise ValueError
    except (ValueError,KeyError,TypeError,BoundaryFailure):raise Denied('CLOSED_IDOX_TARGET') from None
    return target
