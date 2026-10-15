"""Cheap retained-evidence screening, never identity exclusion or admission.

Reuses accepted rules; raw generic counts are not residential dwelling facts.
"""
import re
from app.pipeline.discovery_contract import Literal, candidate_materiality
from app.scrapers.unit_filter import qualify

RULE_VERSION = 'stage4-retained-screen-v1'


def screen(record):
    field = record.get('fields', {}).get('proposal', {})
    state = field.get('state', 'UNKNOWN')
    value = field.get('value')
    if state == 'PRESENT_VALUE' and (not isinstance(value,str) or not value.strip()):
        state = 'UNPARSEABLE'
    supported = value if state == 'PRESENT_VALUE' else None
    literal = Literal(state, value if state == 'PRESENT_VALUE' else None, field.get('locator') or 'listing:proposal:UNKNOWN')
    materiality = candidate_materiality(literal)
    q = qualify(value) if state == 'PRESENT_VALUE' and isinstance(value, str) else None
    # Import the existing literal citation extractor only; never execute its
    # linking/backfill functions or relaxed parent-reference matching.
    from app.pipeline.site_linking import extract_parent_reference
    parent = extract_parent_reference(value) if q else None
    citations = sorted(set(re.findall(r'\b[0-9]{4,6}/[0-9]{2}\b', supported or '')))
    # Existing helper can return only the numeric prefix. Keep that diagnostic,
    # never silently turn it into a qualified parent identity.
    short_parent = parent if parent and any(c.startswith(parent + '/') for c in citations) else None
    if short_parent: parent = None
    return dict(rule_version=RULE_VERSION, materiality=materiality,
        reasons=[materiality['reason']], retained=True, exclusion=False,
        existing_qualification=q.classification if q else None,
        raw_generic_count=q.unit_count if q else None,
        count_metric='UNKNOWN', residential_dwelling_count=None,
        parent_reference=parent, unqualified_parent_prefix=short_parent,
        related_reference_literals=citations, relationship='UNKNOWN',
        proposal_evidence=dict(state=state, locator=field.get('locator')),
        source_record_id=record.get('source_key', record.get('source_record_id')),
        source_url=record.get('source_url'))


def retain_screening(audit):
    """Annotate all identities before any expensive exact-record caller.

    Does not alter references, field states, enumeration/coverage or source data.
    """
    for record in audit.get('records', audit.get('listing_records', [])):
        record['processing_screen'] = screen(record)
        record['processing_screen']['provenance'] = dict(
            segment_sha256=[p.get('body_sha256',p.get('evidence_sha256'))
                for p in audit.get('pages',[]) if isinstance(p,dict)]
                if isinstance(audit.get('pages'),list) else
                [p.get('evidence_sha256') for p in audit.get('listing_segments',[])],
            criteria_sha256=audit.get('applied_evidence_sha256'),
            requested_interval=audit.get('requested_interval'))
    return audit
