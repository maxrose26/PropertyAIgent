"""Coordinator projection of the existing qualified Idox window/parser contract.

No new transport, detail fan-out or source admission. Qualification is bound to
one council/date semantics by a reviewed controller, never inferred from Idox.
"""
from dataclasses import dataclass
from datetime import datetime
import re
from .ledger import Denied,bounded,digest
from .coordinator import validate_outer
from app.pipeline.discovery_contract import WindowEvidence,Completeness,Literal
from app.scrapers.discovery_idox import source_url


@dataclass(frozen=True)
class IdoxListingContract:
    name: str
    config: object
    qualification_sha256: str

    def __post_init__(self):
        if not re.fullmatch('[a-f0-9]{64}',self.qualification_sha256) or self.config.max_transport_retries!=0:
            raise Denied('EXACT_IDOX_QUALIFICATION_AND_ZERO_RETRY_REQUIRED')

    def project(self, source, outer, limits):
        validate_outer(outer,limits);bounded(source)
        c=self.config;interval=[c.start.isoformat(),c.end.isoformat()]
        if (source.get('council')!=c.council or source.get('date_semantics')!=c.semantics
            or source.get('requested_interval')!=interval or source.get('applied_interval')!=interval
            or source.get('failure') is not None or source.get('capped') is not False
            or source.get('enumeration_evidence')!='COUNT_RECONCILED' or source.get('cleanup')!='BOUNDARY_CLOSED'):
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
        if not zero:
            binding=source.get('criteria_result_binding',{})
            if (binding.get('method')!='SAME_SESSION_POST_ENUMERATION_REFINE_NO_RESUBMIT'
                or binding.get('segment_sha256')!=[p['body_sha256'] for p in pages]
                or binding.get('criteria_sha256')!=source['applied_evidence_sha256'] or binding.get('result_set_reenumerated') is not False):raise Denied('IDOX_CRITERIA_BINDING')
        seen=0
        for i,p in enumerate(pages,1):
            if p['ordinal']!=i or not re.fullmatch('[a-f0-9]{64}',p['body_sha256']):raise Denied('IDOX_SEGMENT')
            if zero:
                if len(pages)!=1 or p['total']!=0 or p['rows']!=0 or p['terminal']!='EXPLICIT_ZERO_RESULTS':raise Denied('IDOX_ZERO')
            elif p['first']!=seen+1 or p['last']-p['first']+1!=p['rows'] or p['total']!=len(records):raise Denied('IDOX_COUNTS')
            seen+=p['rows']
        if seen!=len(records) or source['unique_references']!=len(records) or (not zero and pages[-1]['terminal']!='EXPLICIT_LAST_EQUALS_TOTAL'):raise Denied('IDOX_TERMINAL')
        projected=[];keys=set();refs=set()
        for row in records:
            url,key=source_url(c.council,row['source_url'])
            if row['identity_state']!='PRESENT_VALUE' or not isinstance(row['reference'],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/._ -]{0,99}',row['reference']) or key!=row['source_key'] or key in keys or row['reference'] in refs:raise Denied('IDOX_ROW_IDENTITY')
            keys.add(key);refs.add(row['reference']);fields={}
            for name in ('proposal','address','received_date','validated_date','application_type'):
                f=row['fields'].get(name,dict(state='UNKNOWN',value=None,locator='NOT_CAPTURED'))
                literal=Literal(f['state'],f.get('value'),f['locator'])
                fields[name]=dict(state=literal.state,value=literal.value,locator=literal.locator,truncated=False)
            d=fields['received_date' if c.semantics=='RECEIVED' else 'validated_date']
            if d['state']!='PRESENT_VALUE' or not c.start<=datetime.strptime(d['value'],'%a %d %b %Y').date()<=c.end:raise Denied('IDOX_ROW_DATE')
            segment=next(p for p in pages if p['first']<=len(projected)+1<=p['last'])
            projected.append(dict(reference=row['reference'],source_record_id=key,source_url=url,fields=fields,
                provenance=dict(parser='app.scrapers.discovery_idox.parse_page',body_sha256=segment['body_sha256'],row_ordinal=len(projected)+1),
                field_capture_scope=['reference',*fields]))
        window=WindowEvidence(c.council,'coordinator-retained',c.start,c.end,c.start,c.end,c.semantics,
            self.name,source['applied_evidence_sha256'],pages[-1]['terminal'],len(pages),len(projected),r['requests_attempted'],r['received_bytes'],r['elapsed_seconds'],explicit_zero=zero)
        if window.outcome!=Completeness.COMPLETE:raise Denied('IDOX_QUALIFIED_WINDOW_REQUIRED')
        return dict(kind='LISTING_RECEIPT_V1',contract=self.name,council=c.council,interval=interval,records=projected,
            segments=pages,source_sha256=digest(source),qualification_sha256=self.qualification_sha256,
            applied_interval=interval,cleanup='CLOSED',accounting_complete=True,outer_supervisor=outer,
            resources=dict(metric='EXISTING_IDOX_RECEIVED_BODY_BYTES',**r),window=window.__dict__)
