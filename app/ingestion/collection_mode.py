"""A new profile can restrict capture, never upgrade historical qualification."""
from .ledger import Denied, digest


def require_screening_mode(source, council):
    if 'collection_profile' not in source:return  # historical capture contract unchanged
    p=source['collection_profile']
    if not isinstance(p,dict):raise Denied('COLLECTION_PROFILE')
    value={k:v for k,v in p.items() if k!='sha256'}
    if (p.get('version')!='COUNCIL_COLLECTION_PROFILE_V1' or p.get('council')!=council
        or p.get('collection_mode')!='SCREENING_METADATA' or p.get('sha256')!=digest(value)
        or p.get('interval')!=source.get('requested_interval')
        or p.get('semantics')!=source.get('date_semantics')):raise Denied('SCREENING_COLLECTION_MODE_REQUIRED')
