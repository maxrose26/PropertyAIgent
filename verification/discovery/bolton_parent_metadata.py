"""Offline-prepared fixed-two metadata caller. No live dispatch/CLI or writer.

Physical dispatch is injected for review/disposable tests; not execution authority.
"""
from types import SimpleNamespace
from urllib.parse import urlsplit,parse_qs
import hashlib,json,re,os
from datetime import datetime,timezone
from bs4 import BeautifulSoup
from app.pipeline.discovery_contract import SOURCE_ROOTS
from app.scrapers.idox_portal import fetch_application_status_by_reference
from verification.stage26b_l1.actions_canary import retrieve
from verification.stage26b_l1.request_boundary import Boundary,Budget,Policy,BoundaryFailure
from .material_qualification import credential_free

REFERENCES=('00284/26','20683/25')
BASE='https://'+SOURCE_ROOTS['bolton'][0]+SOURCE_ROOTS['bolton'][1].rstrip('/')
SEARCH=BASE+'/search.do?action=advanced&searchType=Application'
FIELDS=('Reference','Proposal','Address','Application Type','Status','Decision','Decision Issued Date')
LIMITS=dict(calls=2,requests=12,bytes=6_000_000,source_seconds=90,output_bytes=131072,
    per_record_requests=6,per_record_bytes=3_000_000,per_record_seconds=45,
    owned_rss_bytes=1610612736,outer_seconds=160)


class ParentBoundary(Boundary):
    def __init__(self,reference,dispatch):
        if reference not in REFERENCES:raise ValueError('FIXED_PARENT_REJECTED')
        super().__init__(Policy('bolton',reference,'idox',BASE,SEARCH),
            Budget(requests=6,per_reference=6,total_bytes=3_000_000,response_bytes=500_000,seconds=45),dispatch)
        self.summary=None;self.summary_url=None

    def reject(self,outcome,reason):self.budget.reject(outcome,reason)

    def validate(self,method,url,body=None):
        # Public form state only. Reject every populated alternative criterion,
        # duplicated input, unsupported control, asset/document or arbitrary route.
        if method=='POST' and url in {BASE+'/search.do',BASE+'/advancedSearchResults.do?action=firstPage'}:
            self.budget.check()
            if self.closed or not isinstance(body,bytes) or len(body)>65536:self.reject('PARTIAL_RETRIEVAL','form bound')
            try:fields=parse_qs(body.decode('utf-8'),keep_blank_values=True,strict_parsing=True)
            except Exception:self.reject('PARSER_FAILURE','form encoding')
            if fields.get('searchCriteria.reference')!=[self.policy.reference]:self.reject('PARTIAL_RETRIEVAL','exact reference')
            for k,v in fields.items():
                if len(v)!=1:self.reject('PARSER_FAILURE','duplicate control')
                if k=='searchCriteria.reference':continue
                if k.startswith(('searchCriteria.','date(')) and v==['']:continue
                if k=='action' and v==['Search']:continue
                if k=='searchType' and v==['Application']:continue
                if k in {'_csrf','csrfToken','org.apache.struts.taglib.html.TOKEN'} and re.fullmatch(r'[A-Za-z0-9_+/=.-]{1,256}',v[0]):continue
                self.reject('PARTIAL_RETRIEVAL','unapproved control')
            return
        if method!='GET' or (url not in {SEARCH,BASE+'/advancedSearchResults.do?action=firstPage'} and urlsplit(url).path!=urlsplit(BASE).path+'/applicationDetails.do'):
            self.reject('PARTIAL_RETRIEVAL','route rejected')
        super().validate(method,url,body)

    def retrieve(self,method,url,body=None):
        url,text=retrieve(self,method,url,body)
        if urlsplit(url).path==urlsplit(BASE).path+'/applicationDetails.do':
            self.summary=text;self.summary_url=url
        return url,text


def metadata(reference,dispatch):
    credential_free(os.environ)
    b=ParentBoundary(reference,dispatch);out=dict(council='bolton',reference=reference,
        identity='WITHHELD',fields={},persistence=False,admission_authorised=False)
    try:
        found=fetch_application_status_by_reference(SimpleNamespace(base_url=BASE,search_url=SEARCH),reference,b)
        if found.reference!=reference or b.summary is None:b.reject('AMBIGUOUS_SOURCE_RESULT','displayed identity')
        # Identity independently rechecked, duplicates fail closed; no URL-only identity.
        soup=BeautifulSoup(b.summary,'html.parser');values={k:[] for k in FIELDS}
        for tr in soup.select('#simpleDetailsTable tr'):
            cells=tr.find_all(['th','td'])
            if len(cells)==2 and cells[0].get_text(strip=True) in values:
                values[cells[0].get_text(strip=True)].append(cells[1].get_text(' ',strip=True))
        if values['Reference']!=[reference]:b.reject('AMBIGUOUS_SOURCE_RESULT','reference table')
        out.update(identity='EXACT_DISPLAYED_REFERENCE',source_url=b.summary_url,
            fingerprint=hashlib.sha256(b.summary.encode()).hexdigest())
        for label,v in values.items():
            if any(len(x)>8192 for x in v):b.reject('PARSER_FAILURE','literal bound')
            state='CONFLICTING' if len(v)>1 else 'NOT_PRESENT' if not v else 'PRESENT_VALUE' if v[0] else 'PRESENT_BLANK'
            out['fields'][label]=dict(state=state,value=v[0] if len(v)==1 else None,locator='#simpleDetailsTable:'+label)
        out['failure']=None
    except BoundaryFailure:
        out['failure']='SOURCE_OR_IDENTITY_REJECTED'
    except Exception:
        out['failure']='UNCLASSIFIED_FAILURE'
    finally:
        b.summary=None;b.close();out.update(resource=b.audit('METADATA_ONLY'),cleanup='BOUNDARY_CLOSED',retrieved_at=datetime.now(timezone.utc).isoformat())
    if len(json.dumps(out).encode())>LIMITS['output_bytes']//2:raise ValueError('OUTPUT_BOUND')
    return out
