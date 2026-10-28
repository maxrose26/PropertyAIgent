"""Coordinator projection of the existing qualified Idox window/parser contract.

No new transport, detail fan-out or source admission. Qualification is bound to
one council/date semantics by a reviewed controller, never inferred from Idox.
"""
from dataclasses import dataclass
from datetime import datetime,timezone
import re
from .ledger import Denied,bounded,digest
from .coordinator import validate_outer
from . import owner_acceptance
from app.pipeline.discovery_contract import WindowEvidence,Completeness,Literal
from app.scrapers.discovery_idox import source_url


def validate_listing_record(c,row,keys,refs):
    """The strict validation of ONE listing row (identity, fields, date inside the requested interval). Shared, unchanged, by the complete-window projection and the partial observation."""
    url,key=source_url(c.council,row['source_url'])
    if row['identity_state']!='PRESENT_VALUE' or not isinstance(row['reference'],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/._ -]{0,99}',row['reference']) or key!=row['source_key'] or key in keys or row['reference'] in refs:raise Denied('IDOX_ROW_IDENTITY')
    keys.add(key);refs.add(row['reference']);fields={}
    for name in ('proposal','address','received_date','validated_date','application_type'):
        f=row['fields'].get(name,dict(state='UNKNOWN',value=None,locator='NOT_CAPTURED'))
        literal=Literal(f['state'],f.get('value'),f['locator'])
        fields[name]=dict(state=literal.state,value=literal.value,locator=literal.locator,truncated=False)
    d=fields['received_date' if c.semantics=='RECEIVED' else 'validated_date']
    if d['state']!='PRESENT_VALUE' or not c.start<=datetime.strptime(d['value'],'%a %d %b %Y').date()<=c.end:raise Denied('IDOX_ROW_DATE')
    return url,key,fields


# Partial listing observations (specification 033). The kind is deliberately NOT a weaker receipt: it has no field from which a completeness claim could be read.
OBSERVATION_KIND='LISTING_OBSERVATION_V1'
OBSERVATION_WINDOW_CLAIM='NONE'      # the ONLY window-level statement an observation makes
OBSERVATION_DISPLAY_LABEL='Observed applications \u2014 window completeness not established'
OBSERVATION_COUNCILS=frozenset({'bolton'})      # evidenced behaviour only (two Bolton observations); no other council is enabled
OBSERVATION_PAGE_SIZES=frozenset({5,10,20,50,100})      # the page sizes the parser accepts


@dataclass(frozen=True)
class IdoxListingContract:
    name: str
    config: object
    qualification_sha256: str
    partial_observation: bool = False      # default OFF: a source without an explicit total keeps stopping exactly as before
    owner_acceptance: str | None = None      # default OFF: a KEY STRING naming a closed in-code registry entry (specification 037); never an object, file or hash

    def __post_init__(self):
        if not re.fullmatch('[a-f0-9]{64}',self.qualification_sha256) or self.config.max_transport_retries!=0:
            raise Denied('EXACT_IDOX_QUALIFICATION_AND_ZERO_RETRY_REQUIRED')
        if self.owner_acceptance is not None:
            d=owner_acceptance.require(self.owner_acceptance).data;c=self.config
            if (c.council,c.semantics,c.start.isoformat(),c.end.isoformat())!=(d['council'],d['semantics'],d['start'],d['end']):raise Denied('OWNER_ACCEPTANCE_SCOPE')

    def scope(self):
        """The exact discovery scope this contract captures (the ledger task subject)."""
        c=self.config
        return {'kind':'DISCOVERY_SCOPE','council':c.council,'start':c.start.isoformat(),'end':c.end.isoformat(),'semantics':c.semantics}

    def admission_window(self,receipt,council_code):
        """The window proof shared admission re-derives from the exact retained receipt (logic moved unchanged from the controller). A receipt that carries an owner-acceptance basis is re-validated against THIS contract's own
        registry entry; a receipt without one is derived exactly as before, from its source terminal."""
        c=self.config;r=receipt['resources'];extra={}
        basis=receipt.get('completeness_basis')
        if basis is not None or 'owner_acceptance' in receipt:
            if self.owner_acceptance is None or basis!=owner_acceptance.BASIS:raise Denied('OWNER_ACCEPTANCE_RECEIPT_BINDING')
            acc=owner_acceptance.require(self.owner_acceptance);s=acc.data['source']
            if (receipt.get('owner_acceptance')!=acc.binding() or receipt['source_sha256']!=s['audit_sha256'] or len(receipt['records'])!=s['record_count']
                or receipt['segments']!=s['pages']):raise Denied('OWNER_ACCEPTANCE_RECEIPT_BINDING')
            extra=dict(completeness_basis=owner_acceptance.BASIS,owner_acceptance_sha256=acc.sha256)
        return WindowEvidence(council_code,'manual-ingestion-controller',c.start,c.end,c.start,c.end,c.semantics,
            receipt['contract'],receipt['source_sha256'],receipt['segments'][-1]['terminal'],len(receipt['segments']),len(receipt['records']),
            r['requests_attempted'],r['received_bytes'],r['elapsed_seconds'],**extra)

    def record_body_sha256(self,record):
        return record['provenance']['body_sha256']

    def _row(self,row,keys,refs):
        return validate_listing_record(self.config,row,keys,refs)

    def project(self, source, outer, limits,*,source_bytes_limit=128*1024):
        from .collection_mode import require_screening_mode
        require_screening_mode(source,self.config.council)
        if type(source_bytes_limit) is not int or not 0<source_bytes_limit<=512*1024:raise Denied("SOURCE_AUDIT_BOUND")
        validate_outer(outer,limits);bounded(source,source_bytes_limit)
        c=self.config;interval=[c.start.isoformat(),c.end.isoformat()]
        # Owner acceptance (specification 037) is consulted ONLY for a TOTAL_UNKNOWN source and ONLY by a contract constructed with a registry key; it must be the exact bound audit. A source with a count signal uses the normal rule.
        accepted=owner_acceptance.require(self.owner_acceptance).verify_source(source,c) if (self.owner_acceptance is not None and source.get('enumeration_evidence')=='TOTAL_UNKNOWN') else None
        if (source.get('council')!=c.council or source.get('date_semantics')!=c.semantics
            or source.get('requested_interval')!=interval or source.get('applied_interval')!=interval
            or source.get('failure') is not None or source.get('capped') is not False
            or (source.get('enumeration_evidence')!='COUNT_RECONCILED' and accepted is None) or source.get('cleanup') not in {'BOUNDARY_CLOSED','SESSION_BOUNDARY_CLOSED'}):
            raise Denied('IDOX_WINDOW_BINDING_OR_COMPLETENESS')
        pages=source['pages'];records=source['records'];r=source['resource']
        if not 1<=len(pages)<=limits['pages'] or len(records)>limits['rows'] or r.get('budget_exhaustion') is not False:
            raise Denied('IDOX_RESOURCE_BOUND')
        if any(type(r.get(k)) is not int or r[k]<0 for k in ('requests_attempted','received_bytes','retries')) or r['retries']!=0:
            raise Denied('IDOX_ACCOUNTING')
        if r['requests_attempted']>min(10,limits['requests']) or r['received_bytes']>min(3000000,limits['bytes']):raise Denied('IDOX_RESOURCE_BOUND')
        if type(r.get('elapsed_seconds')) not in (int,float) or not 0<=r['elapsed_seconds']<=min(45,limits['worker_seconds']):raise Denied('IDOX_CLOCK')
        zero=not records and source.get('explicit_zero_evidence')=='NO_RESULTS_FOUND_AND_RETAINED_DATE_CRITERIA'
        if not re.fullmatch('[a-f0-9]{64}',source.get('applied_evidence_sha256','')):raise Denied('IDOX_CRITERIA_HASH')
        provenance=source.get('response_provenance',[])
        if r.get('redirects')!=0 or len(provenance)!=r['requests_attempted']:
            raise Denied('IDOX_RESPONSE_ACCOUNTING')
        if (not provenance or provenance[-1].get('parser_body_sha256')!=source['applied_evidence_sha256']
            or any(p['body_sha256'] not in [x.get('parser_body_sha256') for x in provenance] for p in pages)):
            raise Denied('IDOX_RESPONSE_PROVENANCE')
        if not zero:
            binding=source.get('criteria_result_binding',{})
            if (binding.get('method')!='SAME_SESSION_POST_ENUMERATION_REFINE_NO_RESUBMIT'
                or binding.get('segment_sha256')!=[p['body_sha256'] for p in pages]
                or binding.get('criteria_sha256')!=source['applied_evidence_sha256'] or binding.get('result_set_reenumerated') is not False or binding.get('request_ordinal')!=r['requests_attempted']):raise Denied('IDOX_CRITERIA_BINDING')
        seen=0
        for i,p in enumerate(pages,1):
            if p['ordinal']!=i or not re.fullmatch('[a-f0-9]{64}',p['body_sha256']):raise Denied('IDOX_SEGMENT')
            if zero:
                if len(pages)!=1 or p['total']!=0 or p['rows']!=0 or p['terminal']!='EXPLICIT_ZERO_RESULTS':raise Denied('IDOX_ZERO')
            elif accepted is None and (p['first']!=seen+1 or p['last']-p['first']+1!=p['rows'] or p['total']!=len(records)):raise Denied('IDOX_COUNTS')
            seen+=p['rows']
        if seen!=len(records) or source['unique_references']!=len(records) or (not zero and accepted is None and pages[-1]['terminal']!='EXPLICIT_LAST_EQUALS_TOTAL'):raise Denied('IDOX_TERMINAL')
        projected=[];keys=set();refs=set()
        for row in records:
            url,key,fields=self._row(row,keys,refs)
            segment=pages[0] if accepted is not None else next(p for p in pages if p['first']<=len(projected)+1<=p['last'])
            projected.append(dict(reference=row['reference'],source_record_id=key,source_url=url,fields=fields,
                provenance=dict(parser='app.scrapers.discovery_idox.parse_page',body_sha256=segment['body_sha256'],row_ordinal=len(projected)+1),
                field_capture_scope=['reference',*fields]))
        window=WindowEvidence(c.council,'coordinator-retained',c.start,c.end,c.start,c.end,c.semantics,
            self.name,source['applied_evidence_sha256'],pages[-1]['terminal'],len(pages),len(projected),r['requests_attempted'],r['received_bytes'],r['elapsed_seconds'],explicit_zero=zero,
            **(dict(completeness_basis=owner_acceptance.BASIS,owner_acceptance_sha256=accepted.sha256) if accepted is not None else {}))
        if window.outcome!=Completeness.COMPLETE:raise Denied('IDOX_QUALIFIED_WINDOW_REQUIRED')
        receipt=dict(kind='LISTING_RECEIPT_V1',contract=self.name,council=c.council,interval=interval,records=projected,
            segments=pages,source_sha256=digest(source),qualification_sha256=self.qualification_sha256,
            applied_interval=interval,cleanup='CLOSED',accounting_complete=True,outer_supervisor=outer,
            resources=dict(metric='EXISTING_IDOX_RECEIVED_BODY_BYTES',**r),window=window.receipt_dict())
        if accepted is not None:receipt.update(completeness_basis=owner_acceptance.BASIS,owner_acceptance=accepted.binding())      # separate evidence: the segments above keep the source's own pagination facts (terminal is null)
        if c.semantics!='RECEIVED':receipt['date_semantics']=c.semantics      # historical receipts carry no date basis and their digests are pinned, so only a non-default basis (Stockport VALIDATED) is named here; retained_capture always names it
        return receipt

    def observe(self,source,outer,limits,*,observed_at,source_bytes_limit=128*1024):
        """The partial observation: verified records from ONE results page whose total is unknown, with NO window claim. Only for an explicitly enabled council, only when EVERY condition holds; anything else stops exactly as
        `project` does. Admission does not infer completeness from the short page: it records that a bounded set of valid records was observed."""
        from .collection_mode import require_screening_mode
        require_screening_mode(source,self.config.council)
        c=self.config
        if not self.partial_observation or c.council not in OBSERVATION_COUNCILS or c.semantics!='RECEIVED':raise Denied('PARTIAL_OBSERVATION_NOT_ENABLED')
        if type(source_bytes_limit) is not int or not 0<source_bytes_limit<=512*1024:raise Denied("SOURCE_AUDIT_BOUND")
        try:
            stamp=datetime.fromisoformat(observed_at)
            if stamp.tzinfo is None or stamp.utcoffset()!=timezone.utc.utcoffset(None):raise ValueError
        except (TypeError,ValueError):raise Denied('OBSERVATION_TIMESTAMP_UTC_REQUIRED') from None
        validate_outer(outer,limits);bounded(source,source_bytes_limit)
        interval=[c.start.isoformat(),c.end.isoformat()]
        if (source.get('council')!=c.council or source.get('date_semantics')!=c.semantics
            or source.get('requested_interval')!=interval or source.get('applied_interval')!=interval
            or source.get('failure') is not None or source.get('capped') is not False
            or source.get('cleanup') not in {'BOUNDARY_CLOSED','SESSION_BOUNDARY_CLOSED'}):
            raise Denied('IDOX_WINDOW_BINDING_OR_COMPLETENESS')
        if source.get('enumeration_evidence')!='TOTAL_UNKNOWN' or source.get('explicit_zero_evidence') is not None or source.get('applied_evidence')!='STRICT_REFINE_FORM_ECHO':raise Denied('IDOX_OBSERVATION_REQUIRES_UNKNOWN_TOTAL')
        pages=source['pages'];records=source['records'];r=source['resource']
        if len(pages)!=1 or len(records)>limits['rows'] or r.get('budget_exhaustion') is not False:raise Denied('IDOX_OBSERVATION_SINGLE_PAGE_ONLY')
        if any(type(r.get(k)) is not int or r[k]<0 for k in ('requests_attempted','received_bytes','retries')) or r['retries']!=0:raise Denied('IDOX_ACCOUNTING')
        if r['requests_attempted']>min(10,limits['requests']) or r['received_bytes']>min(3000000,limits['bytes']):raise Denied('IDOX_RESOURCE_BOUND')
        if type(r.get('elapsed_seconds')) not in (int,float) or not 0<=r['elapsed_seconds']<=min(45,limits['worker_seconds']):raise Denied('IDOX_CLOCK')
        if not re.fullmatch('[a-f0-9]{64}',source.get('applied_evidence_sha256','')):raise Denied('IDOX_CRITERIA_HASH')
        provenance=source.get('response_provenance',[])
        if r.get('redirects')!=0 or len(provenance)!=r['requests_attempted']:raise Denied('IDOX_RESPONSE_ACCOUNTING')
        if (not provenance or provenance[-1].get('parser_body_sha256')!=source['applied_evidence_sha256']
            or any(p['body_sha256'] not in [x.get('parser_body_sha256') for x in provenance] for p in pages)):raise Denied('IDOX_RESPONSE_PROVENANCE')
        binding=source.get('criteria_result_binding',{})
        if (binding.get('method')!='SAME_SESSION_POST_ENUMERATION_REFINE_NO_RESUBMIT' or binding.get('segment_sha256')!=[p['body_sha256'] for p in pages]
            or binding.get('criteria_sha256')!=source['applied_evidence_sha256'] or binding.get('result_set_reenumerated') is not False or binding.get('request_ordinal')!=r['requests_attempted']):raise Denied('IDOX_CRITERIA_BINDING')
        page=pages[0]
        if (page.get('ordinal')!=1 or not re.fullmatch('[a-f0-9]{64}',page.get('body_sha256','')) or page.get('first') is not None or page.get('last') is not None
            or page.get('total') is not None or page.get('terminal') is not None):raise Denied('IDOX_OBSERVATION_PAGE_SHAPE')
        size=page.get('page_size')
        if (type(size) is not int or size not in OBSERVATION_PAGE_SIZES or type(page.get('rows')) is not int or not 0<page['rows']<size      # non-empty and STRICTLY below the selected page size
            or page['rows']!=len(records) or source.get('unique_references')!=len(records)):raise Denied('IDOX_OBSERVATION_ROWS_BELOW_PAGE_SIZE')
        projected=[];keys=set();refs=set()
        for row in records:
            url,key,fields=self._row(row,keys,refs)
            projected.append(dict(reference=row['reference'],source_record_id=key,source_url=url,fields=fields,
                provenance=dict(parser='app.scrapers.discovery_idox.parse_page',body_sha256=page['body_sha256'],row_ordinal=len(projected)+1),
                field_capture_scope=['reference',*fields]))
        return dict(kind=OBSERVATION_KIND,contract=self.name,council=c.council,requested_interval=interval,
                    applied_interval_evidence=dict(method=binding['method'],evidence=source['applied_evidence'],sha256=source['applied_evidence_sha256']),
                    records=projected,page=dict(body_sha256=page['body_sha256'],rows=page['rows'],page_size=size),observed_at=observed_at,
                    window_claim=OBSERVATION_WINDOW_CLAIM,display_label=OBSERVATION_DISPLAY_LABEL,
                    source_sha256=digest(source),qualification_sha256=self.qualification_sha256,cleanup='CLOSED',accounting_complete=True,outer_supervisor=outer,
                    resources=dict(metric='EXISTING_IDOX_RECEIVED_BODY_BYTES',**r))
