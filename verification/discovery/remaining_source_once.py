"""Fixed remaining qualification calls. No production, documents or broad input."""
import hashlib,json,os,re,subprocess,sys,tempfile
from pathlib import Path
from bs4 import BeautifulSoup
from .idox_window import WindowConfig,WindowBoundary,live
from verification.stage26b_l1.actions_runner import supervise


def wigan_shape():
    import requests
    config=WindowConfig('wigan');header={}
    with requests.Session() as session:
        session.trust_env=False
        session.mount('https://',requests.adapters.HTTPAdapter(max_retries=0))
        def dispatch(method,url,**kw):
            kw.pop('deadline',None);kw['timeout']=(3,8)
            response=session.request(method,url,**kw)
            header['media_type']=response.headers.get('Content-Type','')[:100]
            return response
        b=WindowBoundary(dispatch,config)
        # A transient failure cannot dispatch a second request: the shared
        # boundary charges its request budget before every dispatch.
        b.budget.requests=1
        b.budget.per_reference=1
        result={'council':'wigan','purpose':'FORM_SHAPE_DIAGNOSIS','persistence':False,'failure':None}
        try:
            body=b.retrieve('GET',config.form_url)
            result['body_sha256']=hashlib.sha256(body).hexdigest()
            try:text=body.decode('utf-8',errors='strict');result['utf8']=True
            except UnicodeError:text=body.decode('utf-8',errors='replace');result['utf8']=False
            close=list(re.finditer(r'</html\s*>',text,re.I))
            tail=text[close[-1].end():] if close else ''
            result.update(html_closing_count=len(close),trailing_nonwhitespace=bool(tail.strip()),
                trailing_element_names=re.findall(r'</?([A-Za-z][A-Za-z0-9]*)\b',tail)[:20],
                trailing_comment_count=len(re.findall(r'<!--',tail)),**header)
            soup=BeautifulSoup(text,'html.parser')
            result['forms']=len(soup.find_all('form'))
            result['received_date_forms']=sum(all(f.find('input',attrs={'name':n}) for n in ('date(applicationReceivedStart)','date(applicationReceivedEnd)')) for f in soup.find_all('form'))
        except Exception as e:result['failure']=type(e).__name__
        finally:b.close();result['resource']=b.audit('UNKNOWN');result['cleanup']='BOUNDARY_CLOSED'
    result['cleanup']='SESSION_BOUNDARY_CLOSED'
    return result


def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--case',choices=('bury','wigan-shape'),required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--worker',action='store_true');a=p.parse_args()
    if any(k in os.environ for k in ('DATABASE_URL','OPENAI_API_KEY','ANTHROPIC_API_KEY')):raise ValueError('credential-free')
    sha=os.environ.get('DISCOVERY_CANDIDATE_SHA','');run_id=os.environ.get('DISCOVERY_RUN_ID','')
    if not re.fullmatch('[0-9a-f]{40}',sha) or not re.fullmatch('[0-9]{1,20}',run_id):raise ValueError('identity')
    if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=sha:raise ValueError('candidate')
    if a.output.exists():raise ValueError('existing output')
    if a.worker:
        d=live(WindowConfig('bury')) if a.case=='bury' else wigan_shape()
        d.update(code_sha=sha,run_id=run_id,attempt=1)
        raw=json.dumps(d,sort_keys=True).encode()
        if len(raw)>512000:raise ValueError('output bound')
        a.output.write_bytes(raw);return 0
    with tempfile.TemporaryDirectory(prefix='discovery-remaining-') as td:
        child=Path(td)/'audit.json';env={'HOME':td,'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','DISCOVERY_CANDIDATE_SHA':sha,'DISCOVERY_RUN_ID':run_id}
        code,expired=supervise([sys.executable,'-m','verification.discovery.remaining_source_once','--case',a.case,'--worker','--output',str(child)],env=env,deadline=50)
        if expired or code!=0 or not child.exists() or child.stat().st_size>512000:raise ValueError('worker failed')
        d=json.loads(child.read_bytes());d['supervisor']={'worker_exit':code,'expired':expired,'returned':True,'worker_restarted':False}
        a.output.write_text(json.dumps(d,sort_keys=True))
        accepted=d.get('failure') is None
        if a.case=='bury':
            accepted=accepted and d.get('enumeration_evidence')=='COUNT_RECONCILED' and not d.get('capped') and d.get('applied_interval')==d.get('requested_interval')
        return 0 if accepted else 1

if __name__=='__main__':raise SystemExit(main())
