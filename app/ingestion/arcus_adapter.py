"""Arcus public-UI listing contract: a validated retained audit becomes a LISTING_RECEIPT_V1 (mirror of IdoxListingContract).

Pure and source-free. It reuses the existing ledger Arcus validation (`ListingContract.validate`: the reader's own audit validator, the row re-qualification
and the segment hashes), adds no reader and makes no request. Only audits captured in the screening-grade `assessment_metadata` mode can be projected: an
identity-only audit has no proposal text, so it cannot be screened or admitted and is refused here (it remains detection evidence). The reader reports
`source_registry_qualified: False` because it cannot qualify itself; the qualification identity below is the external act that carries the 14 October
qualification, exactly as for Idox. Nothing here claims window completeness for any other purpose.
"""
from dataclasses import dataclass
from datetime import date
import re
from app.pipeline.discovery_contract import Completeness,WindowEvidence
from .coordinator import ListingContract,canonical_rows,validate_source_resources
from .ledger import Denied,bounded,digest
from .resource_accounting import combined_bytes

ARCUS_COUNCILS=frozenset({'manchester','rochdale','salford'})
ARCUS_TERMINAL='COUNT_RECONCILED_LAST_EQUALS_TOTAL'


@dataclass(frozen=True)
class ArcusListingContract:
    name:str
    config:object      # a dated UIConfig: council, start/end as ISO strings, assessment_metadata
    case:str
    audit_validator:object
    row_qualifier:object
    qualification_sha256:str
    execution_budget:str|None=None
    retain_explicit_zero:bool=False  # opt-in intake; historical empty-window refusal unchanged

    def __post_init__(self):
        if not re.fullmatch('[a-f0-9]{64}',self.qualification_sha256):raise Denied('EXACT_ARCUS_QUALIFICATION_REQUIRED')
        if self.config.council not in ARCUS_COUNCILS:raise Denied('ARCUS_COUNCIL')
        if getattr(self.config,'assessment_metadata',False) is not True:raise Denied('ARCUS_ASSESSMENT_METADATA_REQUIRED')      # identity-only audits cannot be screened or admitted
        if not callable(self.audit_validator) or not callable(self.row_qualifier):raise Denied('QUALIFIED_ADAPTER_REQUIRED')

    def scope(self):
        c=self.config
        return {'kind':'DISCOVERY_SCOPE','council':c.council,'start':c.start,'end':c.end,'semantics':'VALIDATED'}

    def _listing(self):
        return ListingContract(self.name,self.config,self.case,self.audit_validator,self.row_qualifier,self.execution_budget)

    def project(self,source,outer,limits,*,source_bytes_limit=128*1024):
        from .collection_mode import require_screening_mode
        require_screening_mode(source,self.config.council)
        if type(source_bytes_limit) is not int or not 0<source_bytes_limit<=512*1024:raise Denied('SOURCE_AUDIT_BOUND')
        c=self.config
        validate_source_resources(source,outer,limits,audit_bytes_limit=source_bytes_limit)
        try:
            self._listing().validate(source,audit_bytes_limit=source_bytes_limit)
        except Denied:raise
        except (ValueError,KeyError,TypeError) as exc:raise Denied('ARCUS_AUDIT_REJECTED') from exc      # a reader-validator refusal, malformed row or missing metadata: fixed code, no source text
        interval=[c.start,c.end]
        if (source.get('applied_interval')!=interval or source.get('failure') is not None or source.get('enumeration_evidence')!='COUNT_RECONCILED'
            or source.get('completeness')!='UNKNOWN' or source.get('persistence') is not False):raise Denied('ARCUS_WINDOW_BINDING_OR_COMPLETENESS')
        rows=canonical_rows(source['listing_records']);segments=source['listing_segments']
        if not rows and not self.retain_explicit_zero:raise Denied('ARCUS_EMPTY_WINDOW_NOT_CAPTURED')
        if len(rows)>limits['rows'] or not 1<=len(segments)<=limits['pages']:raise Denied('ARCUS_RESOURCE_BOUND')
        records=[]
        for n,row in enumerate(rows,1):
            seg=next((s for s in segments if s['first']<=n<=s['last']),None)
            if seg is None or not re.fullmatch('[a-f0-9]{64}',str(seg.get('evidence_sha256',''))):raise Denied('ARCUS_SEGMENT_PROVENANCE')
            records.append(dict(row,provenance=dict(parser='app.ingestion.arcus_adapter',segment_ordinal=seg['ordinal'],body_sha256=seg['evidence_sha256'],row_ordinal=n)))
        resources=dict(metric='ARCUS_UI_COMBINED_BYTES',requests=source['requests'],decoded_bytes=source['decoded_bytes'],encoded_bytes=source['encoded_bytes'],
            outbound_payload_bytes=source['outbound_payload_bytes'],combined_bytes=combined_bytes(source),supervisor_seconds=source['supervisor_seconds'],
            peak_owned_rss=source['peak_owned_rss'],redirects=source.get('redirects'))
        receipt=dict(kind='LISTING_RECEIPT_V1',contract=self.name,council=c.council,interval=interval,records=records,segments=segments,source_sha256=digest(source),
            qualification_sha256=self.qualification_sha256,applied_interval=interval,cleanup='CLOSED',accounting_complete=True,outer_supervisor=outer,resources=resources,
            date_semantics='VALIDATED')
        if not rows:
            # The existing source validator admits only Manchester's exact
            # visible zero, retained criteria, no rows and no next control.
            if c.council!='manchester' or source.get('explicit_zero_evidence')!='EXACT_VISIBLE_ZERO_AND_RETAINED_CRITERIA_NO_ROWS_OR_NEXT':raise Denied('ARCUS_ZERO_EVIDENCE')
            receipt['explicit_zero']=True
        window=self.admission_window(receipt,c.council)
        if window.outcome!=Completeness.COMPLETE:raise Denied('ARCUS_QUALIFIED_WINDOW_REQUIRED')
        receipt['window']=window.receipt_dict()
        return receipt

    def admission_window(self,receipt,council_code):
        c=self.config;r=receipt['resources'];start,end=date.fromisoformat(c.start),date.fromisoformat(c.end)
        return WindowEvidence(council_code,'coordinator-retained',start,end,start,end,'VALIDATED',receipt['contract'],receipt['source_sha256'],ARCUS_TERMINAL,
            len(receipt['segments']),len(receipt['records']),r['requests'],r['combined_bytes'],r['supervisor_seconds'],explicit_zero=receipt.get('explicit_zero',False))

    def record_body_sha256(self,record):
        return record['provenance']['body_sha256']
