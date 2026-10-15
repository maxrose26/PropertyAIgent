"""Fixed Bolton listing qualification, no database or detail/document requests.

Reuse strict form handling, bounded request accounting and disposable supervision.
This is not an operational source registry or acceptance denominator.
"""
from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
import re
import time
from urllib.parse import urlencode
import requests
from app.scrapers.discovery_idox import parse_page, ListingError, IDOX, explicit_zero
from app.pipeline.discovery_contract import SOURCE_ROOTS
from .idox_sort import sort_payload, require_reference_sort
from verification.bolton_recon.recon import form_payload, FORM_URL, POST_URLS, Failure
from verification.stage26b_l1.request_boundary import Boundary, Budget, Policy, BoundaryFailure

START=date(2026,9,28)
END=date(2026,10,4)
COUNCIL='bolton'
MAX_PAGES=6


@dataclass(frozen=True)
class WindowConfig:
    council: str = COUNCIL
    semantics: str = 'RECEIVED'
    start: date = START
    end: date = END

    def __post_init__(self):
        if self.council not in IDOX or self.semantics not in {'RECEIVED','VALIDATED'} or not self.start<=self.end or (self.end-self.start).days>27:
            raise ValueError('unadmitted council/date window')

    @property
    def base(self):
        host,prefix=SOURCE_ROOTS[self.council]
        return 'https://'+host+prefix.rstrip('/')

    @property
    def form_url(self):return self.base+'/search.do?action=advanced&searchType=Application'

    def payload(self,body,*,echo=False):
        stem='Received' if self.semantics=='RECEIVED' else 'Validated'
        return form_payload(body,{'controls':[]},form_url=self.form_url,
            post_urls=frozenset({self.base+'/advancedSearchResults.do?action=firstPage',self.base+'/search.do'}),
            date_fields=(f'date(application{stem}Start)',f'date(application{stem}End)'),
            date_values=(self.start.strftime('%d/%m/%Y'),self.end.strftime('%d/%m/%Y')),allow_date_echo=echo)


class WindowBoundary(Boundary):
    def __init__(self, dispatch, config=WindowConfig()):
        self.config=config
        super().__init__(Policy(config.council,config.semantics+':'+config.start.isoformat()+':'+config.end.isoformat(),'idox',
            config.base,config.form_url),
            Budget(requests=10,per_reference=10,total_bytes=3_000_000,response_bytes=500_000,seconds=45),dispatch)
        self.admitted_post=None
        self.admitted_body=None
        self.next_url=None
        self.phase='FORM'
        self.response_provenance=[]

    def validate(self,method,url,body=None):
        self.budget.check()
        if self.closed: self.budget.reject('PARTIAL_RETRIEVAL','closed')
        allowed=((self.phase=='FORM' and method=='GET' and url==self.config.form_url and body is None)
            or (self.phase in {'SEARCH','SORT'} and method=='POST' and url==self.admitted_post and body==self.admitted_body and body is not None)
            or (self.phase=='PAGE' and method=='GET' and url==self.next_url and self.next_url is not None and body is None)
            or (self.phase=='REFINE' and method=='GET' and url==self.policy.base_url+'/refineSearch.do?action=refine' and body is None))
        if not allowed: self.budget.reject('PARTIAL_RETRIEVAL','window request not admitted')

    def retrieve(self,method,url,body=None):
        status,headers,data=self.request(method,url,body=body,headers={'Content-Type':'application/x-www-form-urlencoded'} if body else {})
        if status!=200 or headers.get('Content-Type','').split(';')[0].lower() not in {'text/html','application/xhtml+xml'}:
            self.budget.reject('PARTIAL_RETRIEVAL','response shape')
        original=data
        encoding='UTF-8'
        if self.config.council=='wigan':
            declared=re.search(r'charset\s*=\s*["\']?([A-Za-z0-9_-]+)',headers.get('Content-Type',''),re.I)
            if declared is None or declared.group(1).lower() not in {'iso-8859-1','utf-8'}:
                self.budget.reject('PARTIAL_RETRIEVAL','unqualified source encoding')
            encoding=declared.group(1).upper()
            if encoding=='ISO-8859-1':data=data.decode('iso-8859-1',errors='strict').encode('utf-8')
            if len(data)>500_000:self.budget.reject('PARTIAL_RETRIEVAL','parser body bound')
        self.response_provenance.append({'source_encoding':encoding,'body_sha256':hashlib.sha256(original).hexdigest(),
            'parser_body_sha256':hashlib.sha256(data).hexdigest()})
        return data


def run(dispatch, config=WindowConfig()):
    b=WindowBoundary(dispatch,config)
    out={'council':config.council,'requested_interval':[config.start.isoformat(),config.end.isoformat()],
        'date_semantics':config.semantics,'applied_interval':None,'completeness':'UNKNOWN',
        'source_qualification':'CANDIDATE_CONTRACT','persistence':False,'pages':[],
        'records':[],'failure':None,'cleanup':'UNKNOWN','capped':False}
    diagnostic_stage='FORM_REQUEST';diagnostic_body=b''
    try:
        form=b.retrieve('GET',config.form_url)
        diagnostic_stage='FORM_PARSE';diagnostic_body=form
        target,payload=config.payload(form)
        b.admitted_post=target; b.admitted_body=urlencode(payload).encode(); b.phase='SEARCH'
        payload.clear()
        diagnostic_stage='SEARCH_REQUEST';diagnostic_body=b''
        html=b.retrieve('POST',target,b.admitted_body)
        b.admitted_body=None
        diagnostic_stage='ZERO_CHECK';diagnostic_body=html
        if explicit_zero(html,config.council):
            _,echo_payload=config.payload(html,echo=True)
            echo_payload.clear()
            out.update(enumeration_evidence='COUNT_RECONCILED',unique_references=0,
                applied_interval=out['requested_interval'],applied_evidence='STRICT_ZERO_RESULT_FORM_ECHO',
                applied_evidence_sha256=hashlib.sha256(html).hexdigest(),
                explicit_zero_evidence='NO_RESULTS_FOUND_AND_RETAINED_DATE_CRITERIA')
            out['pages']=[{'ordinal':1,'first':0,'last':0,'total':0,'rows':0,'body_sha256':hashlib.sha256(html).hexdigest(),'terminal':'EXPLICIT_ZERO_RESULTS'}]
            return out
        diagnostic_stage='SORT_FORM_PARSE'
        target,payload=sort_payload(html,b.policy.base_url)
        b.admitted_post=target; b.admitted_body=urlencode(payload).encode(); b.phase='SORT'
        payload.clear()
        diagnostic_stage='SORT_REQUEST';diagnostic_body=b''
        html=b.retrieve('POST',target,b.admitted_body)
        b.admitted_body=None
        out['sort']='REFERENCE_DESCENDING'
        keys=set(); refs={}; total=None; seen=0
        for ordinal in range(1,MAX_PAGES+1):
            diagnostic_stage='SORT_VERIFY';diagnostic_body=html
            require_reference_sort(html)
            diagnostic_stage='PAGE_PARSE'
            p=parse_page(html,config.council,ordinal,config.start,config.end,config.semantics)
            if p.total is not None:
                if total is not None and total!=p.total: raise ListingError('changing source count')
                total=p.total
            for r in p.rows:
                if r.source_key in keys: raise ListingError('repeated source key across pages')
                keys.add(r.source_key)
                if r.reference is not None:
                    if r.reference in refs: raise ListingError('ambiguous reference across pages')
                    refs[r.reference]=r.source_key
                out['records'].append(asdict(r))
            seen+=len(p.rows)
            out['pages'].append({'ordinal':ordinal,'first':p.first,'last':p.last,'total':p.total,
                'rows':len(p.rows),'body_sha256':p.fingerprint,'terminal':p.terminal})
            if p.next_url is None:
                # Contract candidate only: transport result never self-admits a source.
                out['enumeration_evidence']='COUNT_RECONCILED' if p.terminal and total==seen else 'TOTAL_UNKNOWN'
                break
            if ordinal==MAX_PAGES:
                out['capped']=True; out['completeness']='INCOMPLETE';break
            b.phase='PAGE';b.next_url=p.next_url
            diagnostic_stage='PAGE_REQUEST';diagnostic_body=b''
            html=b.retrieve('GET',p.next_url)
        out['unique_references']=len(refs)
        # Read the current session's refine view after the LAST retained segment,
        # including caps/missing totals. No search is resubmitted and no results
        # are replaced. Submitted payload alone is never applied-date evidence.
        b.phase='REFINE'
        diagnostic_stage='REFINE_REQUEST';diagnostic_body=b''
        echoed=b.retrieve('GET',b.policy.base_url+'/refineSearch.do?action=refine')
        diagnostic_stage='CRITERIA_ECHO';diagnostic_body=echoed
        _,echo_payload=config.payload(echoed,echo=True)
        echo_payload.clear()
        out['applied_interval']=out['requested_interval']
        out['applied_evidence']='STRICT_REFINE_FORM_ECHO'
        out['applied_evidence_sha256']=hashlib.sha256(echoed).hexdigest()
        out['criteria_result_binding']={
            'method':'SAME_SESSION_POST_ENUMERATION_REFINE_NO_RESUBMIT',
            'segment_sha256':[p['body_sha256'] for p in out['pages']],
            'criteria_sha256':out['applied_evidence_sha256'],
            'request_ordinal':b.requests,
            'result_set_reenumerated':False,
            'publication_semantics':'UNKNOWN'}
        if out['capped']:out['enumeration_evidence']='PAGE_CAP'
    except (ListingError,BoundaryFailure,Failure) as e:
        from .source_diagnostics import shape
        # Only these fixed known messages retain their legacy spelling. Other
        # exceptions never export arbitrary str(e), URLs, tokens or source text.
        known={'sort selector':('sort selector','SORT_SELECTOR_COUNT'),
               'ambiguous reference across pages':('ambiguous reference across pages','DUPLICATE_REFERENCE')}
        label,code=known.get(str(e),('SOURCE_CONTRACT_REJECTED','SOURCE_CONTRACT_REJECTED'))
        out['failure']=type(e).__name__+':'+label
        out['failure_diagnostic']=shape(diagnostic_body,diagnostic_stage,code)
        out['completeness']='INCOMPLETE' if out['pages'] else 'FAILED'
    except Exception:
        from .source_diagnostics import shape
        out['failure_diagnostic']=shape(diagnostic_body,diagnostic_stage,'UNCLASSIFIED_FAILURE')
        out['failure']='UNCLASSIFIED_FAILURE';out['completeness']='FAILED'
    finally:
        b.admitted_body=None; b.close()
        out['resource']=b.audit(out['completeness']);out['cleanup']='BOUNDARY_CLOSED'
        out['response_provenance']=b.response_provenance
    return out


def live(config=WindowConfig()):
    with requests.Session() as s:
        s.trust_env=False
        s.mount('https://',requests.adapters.HTTPAdapter(max_retries=0))
        previous=[None]
        def dispatch(method,url,**kwargs):
            delay=2.5 if config.council=='stockport' else 0.4
            if previous[0] is not None:time.sleep(max(0,delay-(time.monotonic()-previous[0])))
            previous[0]=time.monotonic()
            kwargs.pop('deadline',None)
            kwargs['timeout']=(3,8)
            return s.request(method,url,**kwargs)
        result=run(dispatch,config)
    result['cleanup']='SESSION_BOUNDARY_CLOSED'
    return result


def main():
    import argparse, os, re, subprocess, sys, tempfile
    from pathlib import Path
    from verification.stage26b_l1.actions_runner import supervise
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--worker',action='store_true')
    a=p.parse_args()
    if any(k in os.environ for k in ('DATABASE_URL','OPENAI_API_KEY','ANTHROPIC_API_KEY')):
        raise ValueError('credential-free only')
    if a.output.exists(): raise ValueError('existing output')
    sha=os.environ.get('DISCOVERY_CANDIDATE_SHA','')
    run_id=os.environ.get('DISCOVERY_RUN_ID','')
    if not re.fullmatch('[0-9a-f]{40}',sha) or not re.fullmatch('[0-9]{1,20}',run_id): raise ValueError('run identity')
    if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=sha: raise ValueError('candidate mismatch')
    if a.worker:
        result=live()
        result.update(code_sha=sha,run_id=run_id,attempt=1,validation_revision=3,
            execution_workflow='.github/workflows/stage4-discovery-bolton-window-once.yml')
        raw=json.dumps(result,sort_keys=True).encode()
        if len(raw)>512000: raise ValueError('audit output bound')
        a.output.write_bytes(raw)
        return 0
    with tempfile.TemporaryDirectory(prefix='discovery-idox-') as td:
        child=Path(td)/'audit.json'
        env={'HOME':td,'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1',
             'DISCOVERY_CANDIDATE_SHA':sha,'DISCOVERY_RUN_ID':run_id}
        code,expired=supervise([sys.executable,'-m','verification.discovery.idox_window','--worker','--output',str(child)],env=env,deadline=50)
        if expired or code!=0 or not child.exists() or child.stat().st_size>512000:
            raise ValueError('worker failure/no complete audit')
        result=json.loads(child.read_bytes())
        result['supervisor']={'worker_exit':code,'expired':expired,'returned':True,'worker_restarted':False,'transport_retry_limit':1}
        a.output.write_text(json.dumps(result,sort_keys=True))
        return 0 if result['failure'] is None and result.get('enumeration_evidence')=='COUNT_RECONCILED' and result.get('applied_interval')==result['requested_interval'] else 1


if __name__=='__main__':
    raise SystemExit(main())
