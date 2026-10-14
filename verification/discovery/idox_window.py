"""Fixed Bolton listing qualification, no database or detail/document requests.

Reuse strict form handling, bounded request accounting and disposable supervision.
This is not an operational source registry or acceptance denominator.
"""
from dataclasses import asdict
from datetime import date
import hashlib
import json
import time
from urllib.parse import urlencode
import requests
from app.scrapers.discovery_idox import parse_page, ListingError
from .idox_sort import sort_payload, require_reference_sort
from verification.bolton_recon.recon import form_payload, FORM_URL, POST_URLS, Failure
from verification.stage26b_l1.request_boundary import Boundary, Budget, Policy, BoundaryFailure

START=date(2026,9,28)
END=date(2026,10,4)
COUNCIL='bolton'
MAX_PAGES=6


class WindowBoundary(Boundary):
    def __init__(self, dispatch):
        super().__init__(Policy(COUNCIL,'received:2026-09-28:2026-10-04','idox',
            'https://paplanning.bolton.gov.uk/online-applications',FORM_URL),
            Budget(requests=10,per_reference=10,total_bytes=3_000_000,response_bytes=500_000,seconds=45),dispatch)
        self.admitted_post=None
        self.admitted_body=None
        self.next_url=None
        self.phase='FORM'

    def validate(self,method,url,body=None):
        self.budget.check()
        if self.closed: self.budget.reject('PARTIAL_RETRIEVAL','closed')
        allowed=((self.phase=='FORM' and method=='GET' and url==FORM_URL and body is None)
            or (self.phase in {'SEARCH','SORT'} and method=='POST' and url==self.admitted_post and body==self.admitted_body and body is not None)
            or (self.phase=='PAGE' and method=='GET' and url==self.next_url and self.next_url is not None and body is None)
            or (self.phase=='REFINE' and method=='GET' and url==self.policy.base_url+'/refineSearch.do?action=refine' and body is None))
        if not allowed: self.budget.reject('PARTIAL_RETRIEVAL','window request not admitted')

    def retrieve(self,method,url,body=None):
        status,headers,data=self.request(method,url,body=body,headers={'Content-Type':'application/x-www-form-urlencoded'} if body else {})
        if status!=200 or headers.get('Content-Type','').split(';')[0].lower() not in {'text/html','application/xhtml+xml'}:
            self.budget.reject('PARTIAL_RETRIEVAL','response shape')
        return data


def run(dispatch):
    b=WindowBoundary(dispatch)
    out={'council':COUNCIL,'requested_interval':[START.isoformat(),END.isoformat()],
        'date_semantics':'RECEIVED','applied_interval':None,'completeness':'UNKNOWN',
        'source_qualification':'CANDIDATE_CONTRACT','persistence':False,'pages':[],
        'records':[],'failure':None,'cleanup':'UNKNOWN','capped':False}
    try:
        form=b.retrieve('GET',FORM_URL)
        fa={'controls':[]}
        target,payload=form_payload(form,fa,date_values=(START.strftime('%d/%m/%Y'),END.strftime('%d/%m/%Y')))
        b.admitted_post=target; b.admitted_body=urlencode(payload).encode(); b.phase='SEARCH'
        payload.clear()
        html=b.retrieve('POST',target,b.admitted_body)
        b.admitted_body=None
        target,payload=sort_payload(html,b.policy.base_url)
        b.admitted_post=target; b.admitted_body=urlencode(payload).encode(); b.phase='SORT'
        payload.clear()
        html=b.retrieve('POST',target,b.admitted_body)
        b.admitted_body=None
        out['sort']='REFERENCE_DESCENDING'
        keys=set(); refs={}; total=None; seen=0
        for ordinal in range(1,MAX_PAGES+1):
            require_reference_sort(html)
            p=parse_page(html,COUNCIL,ordinal,START,END)
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
            html=b.retrieve('GET',p.next_url)
        out['unique_references']=len(refs)
        if not out['capped']:
            b.phase='REFINE'
            echoed=b.retrieve('GET',b.policy.base_url+'/refineSearch.do?action=refine')
            _,echo_payload=form_payload(echoed,{'controls':[]},date_values=(START.strftime('%d/%m/%Y'),END.strftime('%d/%m/%Y')),allow_date_echo=True)
            echo_payload.clear()
            out['applied_interval']=out['requested_interval']
            out['applied_evidence']='STRICT_REFINE_FORM_ECHO'
            out['applied_evidence_sha256']=hashlib.sha256(echoed).hexdigest()
    except (ListingError,BoundaryFailure,Failure) as e:
        out['failure']=type(e).__name__+':'+str(e)[:100]
        out['completeness']='INCOMPLETE' if out['pages'] else 'FAILED'
    except Exception:
        out['failure']='UNCLASSIFIED_FAILURE';out['completeness']='FAILED'
    finally:
        b.admitted_body=None; b.close()
        out['resource']=b.audit(out['completeness']);out['cleanup']='BOUNDARY_CLOSED'
    return out


def live():
    with requests.Session() as s:
        s.trust_env=False
        s.mount('https://',requests.adapters.HTTPAdapter(max_retries=0))
        def dispatch(method,url,**kwargs):
            kwargs.pop('deadline',None)
            kwargs['timeout']=(3,8)
            return s.request(method,url,**kwargs)
        result=run(dispatch)
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
