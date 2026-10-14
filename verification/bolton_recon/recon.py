"""One fixed received-date experiment, two HTTP operations, no linked retrieval.

No application/database/model imports. Recognition rules are conservative proposed
rules; offline fixtures do not certify compatibility with current Bolton markup.
"""
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import math
import re
import time
from urllib.parse import urljoin, urlsplit, parse_qsl, urlencode
import requests
from urllib3.exceptions import ReadTimeoutError
from bs4 import BeautifulSoup

VERSION = 'bolton-discovery-recon-v1'
WORKFLOW = '.github/workflows/bolton-discovery-recon.yml'
REPOSITORY = 'maxrose26/PropertyAIgent'
AUTHORITY = 'AUTHORISE_BOLTON_RECEIVED_2026_02_19_ONLY'
BASE = 'https://paplanning.bolton.gov.uk/online-applications'
FORM_URL = BASE + '/search.do?action=advanced&searchType=Application'
POST_URLS = frozenset({BASE + '/advancedSearchResults.do?action=firstPage', BASE + '/search.do'})
DATE = '2026-02-19'
DATE_FIELDS = ('date(applicationReceivedStart)', 'date(applicationReceivedEnd)')
DATE_VALUE = '19/02/2026'
FIXED_TYPE_FIELDS = frozenset({'caseAddressType', 'searchType'})
CANCEL_CONTROL = 'org.apache.struts.taglib.html.CANCEL'
STATE_FIELDS = frozenset({'_csrf', 'csrfToken', 'org.apache.struts.taglib.html.TOKEN'})
MAX_BODY, MAX_TOTAL, MAX_AUDIT, MAX_ROWS = 500_000, 1_000_000, 32_768, 20
OUTCOMES = frozenset({'RECOGNISED_RESULTS','RECOGNISED_ZERO_RESULTS','FORM_REJECTED','SOURCE_UNAVAILABLE',
                     'LAYOUT_UNRECOGNISED','PARTIAL_RETRIEVAL','TIMEOUT','BUDGET_EXCEEDED'})
REASONS = frozenset({'FORM_SELECTION','FORM_METHOD','FORM_ACTION','FORM_STRUCTURE','CONTROL_LIMIT','DUPLICATE_CONTROL',
    'DATE_CONTROL','STATE_CONTROL','POPULATED_CRITERION','UNKNOWN_CONTROL','SUBMIT_CONTROL','REQUEST_DENIED',
    'REDIRECT_DENIED','BODY_LIMIT','MEDIA_TYPE','ENCODING','ATTACHMENT','HTTP_STATUS','TRANSPORT_FAILURE',
    'TIMEOUT','DOCUMENT_STRUCTURE','RESULT_STRUCTURE','RESULT_LIMIT','IDENTITY_CONFLICT','LINK_DENIED',
    'ARTIFACT_LIMIT','WORKER_INTERRUPTED','OUTPUT_INVALID'})
CLASSES = frozenset({'REQUIRED_SERVER_STATE','APPROVED_DATE_INPUT','APPROVED_FIXED_SUBMIT_CONTROL',
                    'IGNORABLE_CONTROL','APPROVED_FIXED_SOURCE_TYPE','PROHIBITED_SEARCH_EXPANSION','UNKNOWN'})
SAFE_NAMES = STATE_FIELDS | FIXED_TYPE_FIELDS | {CANCEL_CONTROL} | set(DATE_FIELDS) | {'action','searchCriteria.reference','searchCriteria.applicantName',
    'searchCriteria.applicant','searchCriteria.address','searchCriteria.postcode','searchCriteria.description',
    'searchCriteria.proposal','searchCriteria.status','searchCriteria.decision',
    'date(applicationValidatedStart)','date(applicationValidatedEnd)',
    'date(applicationDecisionStart)','date(applicationDecisionEnd)'}


class Failure(Exception):
    def __init__(self, outcome, reason):
        self.outcome, self.reason = outcome, reason
        super().__init__(reason)


def require(ok, outcome, reason):
    if not ok: raise Failure(outcome, reason)


def safe_url(raw, allowed):
    require(isinstance(raw,str) and len(raw)<=512 and not re.search(r'[\s\\%]',raw), 'FORM_REJECTED','FORM_ACTION')
    url = urljoin(FORM_URL, raw)
    require(url in allowed, 'FORM_REJECTED','FORM_ACTION')
    return url


class Shape(HTMLParser):
    def __init__(self):
        super().__init__(); self.forms=0; self.depth=0; self.invalid=False
    def handle_starttag(self,tag,attrs):
        names=[k for k,v in attrs]
        if len(names)!=len(set(names)): self.invalid=True
        if tag=='form':
            if self.depth: self.invalid=True
            self.depth+=1; self.forms+=1
    def handle_endtag(self,tag):
        if tag=='form':
            if self.depth!=1: self.invalid=True
            self.depth=max(0,self.depth-1)


def soup_for(body):
    try: text=body.decode('utf-8',errors='strict')
    except UnicodeError: raise Failure('LAYOUT_UNRECOGNISED','DOCUMENT_STRUCTURE') from None
    require(bool(re.search(r'</html\s*>\s*$',text,re.I)), 'PARTIAL_RETRIEVAL','DOCUMENT_STRUCTURE')
    shape=Shape(); shape.feed(text)
    require(not shape.invalid and shape.depth==0, 'FORM_REJECTED','FORM_STRUCTURE')
    return BeautifulSoup(text,'html.parser')


def form_payload(body, audit):
    soup=soup_for(body)
    forms=[f for f in soup.find_all('form') if all(f.find('input',attrs={'name':n}) for n in DATE_FIELDS)]
    require(len(forms)==1 and len(soup.find_all('form'))<=10,'FORM_REJECTED','FORM_SELECTION')
    form=forms[0]
    require(form.get('method','get').lower()=='post' and form.get('enctype','application/x-www-form-urlencoded').lower()=='application/x-www-form-urlencoded',
            'FORM_REJECTED','FORM_METHOD')
    target=safe_url(form.get('action',''),POST_URLS)
    require(not form.has_attr('target') and not soup.find('base'), 'FORM_REJECTED','FORM_STRUCTURE')
    # External form-associated controls / per-control action overrides are not understood.
    require(not soup.select('[form]') and not form.select('[formaction],[formmethod],[formenctype]'), 'FORM_REJECTED','FORM_STRUCTURE')
    controls=form.find_all(['input','select','textarea','button'])
    require(len(controls)<=80,'FORM_REJECTED','CONTROL_LIMIT')
    data={}; seen=set(); submits=0
    audit.update(selected=True,action_path=urlsplit(target).path,method='POST')
    for ordinal,el in enumerate(controls):
        name=el.get('name','')
        kind=el.name if el.name in ('select','textarea') else el.get('type','submit' if el.name=='button' else 'text').lower()
        disabled=el.has_attr('disabled') or any(p.name=='fieldset' and p.has_attr('disabled') for p in el.parents)
        if kind=='select':
            options=el.find_all('option'); require(len(options)<=500,'FORM_REJECTED','CONTROL_LIMIT')
            selected=[o for o in options if o.has_attr('selected')]
            selected=selected or (options[:1] if not el.has_attr('multiple') else [])
            values=[o.get('value',o.get_text()) for o in selected]
            value=''.join(values)
        else: value=el.get_text() if kind=='textarea' else el.get('value','')
        row={'ordinal':ordinal,'field':name if name in SAFE_NAMES else None,'classification':'UNKNOWN',
             'populated':bool(value),'disabled':disabled}
        audit['controls'].append(row)
        if disabled or kind in ('button','reset') or (kind in ('checkbox','radio') and not el.has_attr('checked')):
            row['classification']='IGNORABLE_CONTROL'; continue
        if name:
            require(name not in seen,'FORM_REJECTED','DUPLICATE_CONTROL'); seen.add(name)
        if name in DATE_FIELDS:
            require(kind=='text' and not value and not el.has_attr('readonly'),'FORM_REJECTED','DATE_CONTROL')
            data[name]=DATE_VALUE; row['classification']='APPROVED_DATE_INPUT'
        elif name in STATE_FIELDS:
            row['classification']='REQUIRED_SERVER_STATE'
            require(kind=='hidden' and bool(re.fullmatch(r'[A-Za-z0-9_+/=.-]{1,256}',value)), 'FORM_REJECTED','STATE_CONTROL')
            data[name]=value
        elif name in FIXED_TYPE_FIELDS:
            require(kind=='hidden' and value=='Application', 'FORM_REJECTED','UNKNOWN_CONTROL')
            data[name]='Application'; row['classification']='APPROVED_FIXED_SOURCE_TYPE'
        elif name==CANCEL_CONTROL:
            require(kind=='submit', 'FORM_REJECTED','SUBMIT_CONTROL')
            row['classification']='IGNORABLE_CONTROL'  # not the clicked submitter
        elif kind=='submit':
            require(value=='Search' and name in ('','action'),'FORM_REJECTED','SUBMIT_CONTROL')
            submits+=1; row['classification']='APPROVED_FIXED_SUBMIT_CONTROL'
            if name: data[name]='Search'
        elif not name and kind!='hidden':
            row['classification']='IGNORABLE_CONTROL'
        elif not value:
            row['classification']='IGNORABLE_CONTROL'
        elif name.startswith(('searchCriteria.','date(')):
            row['classification']='PROHIBITED_SEARCH_EXPANSION'
            raise Failure('FORM_REJECTED','POPULATED_CRITERION')
        else:
            raise Failure('FORM_REJECTED','UNKNOWN_CONTROL')
    require(submits==1 and all(data.get(n)==DATE_VALUE for n in DATE_FIELDS),'FORM_REJECTED','DATE_CONTROL')
    # Tokens are local to this returned form/action and never included in the audit.
    return target,data


def admit_payload(data):
    require(type(data) is dict and set(DATE_FIELDS)<=set(data) and set(data)<=set(DATE_FIELDS)|STATE_FIELDS|FIXED_TYPE_FIELDS|{'action'},
            'FORM_REJECTED','REQUEST_DENIED')
    require(all(data[n]==DATE_VALUE for n in DATE_FIELDS),'FORM_REJECTED','REQUEST_DENIED')
    for k,v in data.items():
        if k in FIXED_TYPE_FIELDS: require(v=='Application','FORM_REJECTED','UNKNOWN_CONTROL')
        if k in STATE_FIELDS: require(isinstance(v,str) and bool(re.fullmatch(r'[A-Za-z0-9_+/=.-]{1,256}',v)), 'FORM_REJECTED','STATE_CONTROL')
        if k=='action': require(v=='Search','FORM_REJECTED','SUBMIT_CONTROL')


class Transport:
    """One session, no proxies/netrc/auth, redirects, retries, assets or link fetches."""
    def __init__(self):
        self.session=requests.Session(); self.session.trust_env=False
        self.session.mount('https://',requests.adapters.HTTPAdapter(max_retries=0))
        self.session.headers.update({'Accept-Encoding':'identity'})
        self.requests=0; self.redirects=0; self.bytes=0; self.statuses=[]; self.started=time.monotonic(); self.closed=False
        self.approved_form=None
    def request(self,method,url,data=None):
        require(not self.closed and ((self.requests==0 and method=='GET' and url==FORM_URL and data is None)
                or (self.requests==1 and method=='POST' and url==self.approved_form and url in POST_URLS)),
                'PARTIAL_RETRIEVAL','REQUEST_DENIED')
        if method=='POST': admit_payload(data)
        require(time.monotonic()-self.started<30,'TIMEOUT','TIMEOUT')
        self.requests+=1
        response=None; body=bytearray(); before=self.bytes; wire=0
        try:
            response=self.session.request(method,url,data=data,stream=True,allow_redirects=False,timeout=(3,8))
            self.statuses.append(response.status_code)
            if 300<=response.status_code<400: self.redirects+=1
            require('attachment' not in response.headers.get('Content-Disposition','').lower(),'PARTIAL_RETRIEVAL','ATTACHMENT')
            require(response.headers.get('Content-Encoding','identity').lower() in ('','identity'),'PARTIAL_RETRIEVAL','ENCODING')
            while True:
                require(time.monotonic()-self.started<30,'TIMEOUT','TIMEOUT')
                chunk=response.raw.read(min(8192,MAX_BODY-len(body)+1,MAX_TOTAL-self.bytes+1),decode_content=False)
                wire=response.raw.tell(); self.bytes=before+max(len(body)+len(chunk),wire)
                require(self.bytes-before<=MAX_BODY and self.bytes<=MAX_TOTAL,'BUDGET_EXCEEDED','BODY_LIMIT')
                if not chunk: break
                body.extend(chunk)
            require(self.redirects==0,'PARTIAL_RETRIEVAL','REDIRECT_DENIED')
            require(response.status_code==200,'SOURCE_UNAVAILABLE','HTTP_STATUS')
            require(response.headers.get('Content-Type','').split(';')[0].strip().lower() in ('text/html','application/xhtml+xml'),
                    'LAYOUT_UNRECOGNISED','MEDIA_TYPE')
            return bytes(body)
        except (requests.exceptions.Timeout, ReadTimeoutError):
            raise Failure('TIMEOUT','TIMEOUT') from None
        except Failure: raise
        except Exception:
            raise Failure('PARTIAL_RETRIEVAL','TRANSPORT_FAILURE') from None
        finally:
            if response is not None:
                try: self.bytes=max(self.bytes,before+response.raw.tell())
                finally: response.close()
            body.clear()
    def close(self):
        self.session.close(); self.closed=True


def result_link(href):
    require(isinstance(href,str) and len(href)<=512 and not re.search(r'[\s\\%]',href),'PARTIAL_RETRIEVAL','LINK_DENIED')
    u=urlsplit(urljoin(FORM_URL,href))
    try: pairs=parse_qsl(u.query,keep_blank_values=True,strict_parsing=True)
    except ValueError: raise Failure('PARTIAL_RETRIEVAL','LINK_DENIED') from None
    q=dict(pairs)
    require(u.scheme=='https' and u.netloc=='paplanning.bolton.gov.uk' and not u.fragment
            and u.path=='/online-applications/applicationDetails.do' and len(q)==len(pairs)
            and set(q) in ({'keyVal'},{'keyVal','activeTab'}) and q.get('activeTab','summary')=='summary'
            and bool(re.fullmatch(r'[A-Za-z0-9]{1,40}',q.get('keyVal',''))),'PARTIAL_RETRIEVAL','LINK_DENIED')
    return q['keyVal'],u.path+'?'+urlencode({'activeTab':'summary','keyVal':q['keyVal']})


def parse_results(body):
    soup=soup_for(body)
    # Structural hypotheses only: a mismatch is a qualified reconnaissance result.
    if any(soup.find('input',attrs={'name':n}) for n in DATE_FIELDS):
        raise Failure('FORM_REJECTED','RESULT_STRUCTURE')
    containers=soup.select('#searchresults')
    require(len(containers)==1,'LAYOUT_UNRECOGNISED','RESULT_STRUCTURE')
    container=containers[0]
    rows=container.select('li.searchresult')
    zeros=container.select('.noResults')
    pagination=bool(soup.select('a[rel="next"], a.next, .pagination a')) or any(a.get_text(' ',strip=True)=='Next' for a in soup.find_all('a'))
    if zeros:
        require(len(zeros)==1 and not rows and not container.find('a') and not pagination
                and zeros[0].get_text(' ',strip=True) in ('No results found.','No results found'),
                'LAYOUT_UNRECOGNISED','RESULT_STRUCTURE')
        return 'RECOGNISED_ZERO_RESULTS',{'source_count':0,'pagination_present':False,'page_ordinal':1,'candidates':[],
                                         'qualification':'STRUCTURAL_ZERO_FIRST_RESPONSE_ONLY'}
    require(0<len(rows)<=MAX_ROWS,'BUDGET_EXCEEDED' if len(rows)>MAX_ROWS else 'LAYOUT_UNRECOGNISED',
            'RESULT_LIMIT' if len(rows)>MAX_ROWS else 'RESULT_STRUCTURE')
    candidates={}; refs={}
    for row in rows:
        links=row.find_all('a',href=True)
        require(bool(links),'LAYOUT_UNRECOGNISED','RESULT_STRUCTURE')
        keys={result_link(a['href']) for a in links}
        require(len(keys)==1,'PARTIAL_RETRIEVAL','IDENTITY_CONFLICT')
        key,path=next(iter(keys))
        meta=row.select('.metaInfo')
        ref_values=[]
        for node in meta:
            text=node.get_text(' ',strip=True)
            ref_values+=re.findall(r'(?:^|\|)\s*Ref\. No:\s*([A-Za-z0-9/_.-]{1,80})(?=\s*(?:\||$))',text)
        require(len(set(ref_values))<=1,'PARTIAL_RETRIEVAL','IDENTITY_CONFLICT')
        ref=ref_values[0] if ref_values else None
        if ref: require(bool(re.search(r'\d',ref)),'LAYOUT_UNRECOGNISED','RESULT_STRUCTURE')
        candidate={'reference':ref,'source_key':key,'source_path':path}
        require(key not in candidates,'PARTIAL_RETRIEVAL','IDENTITY_CONFLICT')
        require(ref is None or ref not in refs or refs[ref]==key,'PARTIAL_RETRIEVAL','IDENTITY_CONFLICT')
        candidates[key]=candidate
        if ref: refs[ref]=key
    shown=None
    summaries=soup.select('.searchinfo')
    if len(summaries)==1:
        match=re.fullmatch(r'Showing\s+1\s+to\s+(\d+)\s+of\s+(\d+)\s+(?:results|applications)',summaries[0].get_text(' ',strip=True),re.I)
        if match:
            last,shown=map(int,match.groups())
            require(last==len(rows) and last<=shown<=100000,'PARTIAL_RETRIEVAL','RESULT_STRUCTURE')
            pagination=pagination or shown>last
    return 'RECOGNISED_RESULTS',{'source_count':shown,'pagination_present':pagination,'page_ordinal':1,
        'candidates':sorted(candidates.values(),key=lambda c:(c['reference'] or '',c['source_key'])),
        'qualification':'PAGINATION_PRESENT_STOPPED' if pagination else 'FIRST_RESPONSE_ONLY_COMPLETENESS_UNPROVED'}


def envelope(sha,mode):
    return dict(manifest_version=VERSION,repository=REPOSITORY,code_sha=sha,workflow=WORKFLOW,
        execution_time=datetime.now(timezone.utc).isoformat(),mode=mode,council='bolton',date_basis='RECEIVED',
        start_date=DATE,end_date=DATE,outcome='PARTIAL_RETRIEVAL',failure_reason=None,
        requests=0,redirects=0,retries=0,received_bytes=0,http_statuses=[],elapsed_seconds=0,
        accounting_complete=True,cleanup_verified=False,persistence=False,
        form={'selected':False,'action_path':None,'method':None,'controls':[]},result=None,budget_state='WITHIN_LIMITS')


def run(sha,mode):
    require(bool(re.fullmatch(r'[0-9a-f]{40}',sha)) and mode in ('offline','live'),'PARTIAL_RETRIEVAL','REQUEST_DENIED')
    out=envelope(sha,mode); transport=Transport()
    try:
        body=transport.request('GET',FORM_URL)
        target,payload=form_payload(body,out['form'])
        transport.approved_form=target
        try: body=transport.request('POST',target,payload)
        finally: payload.clear()
        out['outcome'],out['result']=parse_results(body)
    except Failure as exc:
        out.update(outcome=exc.outcome,failure_reason=exc.reason,result=None)
    except Exception:
        out.update(outcome='PARTIAL_RETRIEVAL',failure_reason='OUTPUT_INVALID',result=None)
    finally:
        transport.close()
        out.update(requests=transport.requests,redirects=transport.redirects,received_bytes=transport.bytes,
                   http_statuses=transport.statuses,elapsed_seconds=round(time.monotonic()-transport.started,6),cleanup_verified=transport.closed)
    if out['received_bytes']>MAX_TOTAL or out['outcome']=='BUDGET_EXCEEDED': out['budget_state']='EXHAUSTED'
    return out


def encode(out):
    validate(out)
    raw=json.dumps(out,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    require(len(raw)<=MAX_AUDIT,'BUDGET_EXCEEDED','ARTIFACT_LIMIT')
    return raw


def validate(out):
    require(type(out) is dict and set(out)==set(envelope('0'*40,'offline')),'PARTIAL_RETRIEVAL','OUTPUT_INVALID')
    for k,v in {'manifest_version':VERSION,'repository':REPOSITORY,'workflow':WORKFLOW,'council':'bolton','date_basis':'RECEIVED',
                'start_date':DATE,'end_date':DATE,'retries':0,'persistence':False}.items():
        require(out[k]==v,'PARTIAL_RETRIEVAL','OUTPUT_INVALID')
    require(bool(re.fullmatch(r'[0-9a-f]{40}',out['code_sha'])) and out['mode'] in ('offline','live')
            and out['outcome'] in OUTCOMES and out['failure_reason'] in REASONS|{None},'PARTIAL_RETRIEVAL','OUTPUT_INVALID')
    require(datetime.fromisoformat(out['execution_time']).utcoffset().total_seconds()==0,'PARTIAL_RETRIEVAL','OUTPUT_INVALID')
    require(type(out['elapsed_seconds']) in (int,float) and math.isfinite(out['elapsed_seconds']) and 0<=out['elapsed_seconds']<=36,
            'PARTIAL_RETRIEVAL','OUTPUT_INVALID')
    if out['accounting_complete'] is False:
        require(out['outcome']=='TIMEOUT' and out['failure_reason']=='WORKER_INTERRUPTED' and out['requests'] is None
                and out['redirects'] is None and out['received_bytes'] is None and out['http_statuses']==[] and out['result'] is None,
                'PARTIAL_RETRIEVAL','OUTPUT_INVALID')
    else:
        require(out['accounting_complete'] is True and type(out['requests']) is int and 0<=out['requests']<=2
                and type(out['redirects']) is int and 0<=out['redirects']<=out['requests']
                and type(out['received_bytes']) is int and 0<=out['received_bytes']<=MAX_TOTAL+8192
                and len(out['http_statuses'])<=out['requests'] and all(type(s) is int and 100<=s<=599 for s in out['http_statuses']),
                'PARTIAL_RETRIEVAL','OUTPUT_INVALID')
    require(out['cleanup_verified'] is True and out['budget_state'] in ('WITHIN_LIMITS','EXHAUSTED','UNKNOWN_INTERRUPTED'),
            'PARTIAL_RETRIEVAL','OUTPUT_INVALID')
    form=out['form']
    require(set(form)=={'selected','action_path','method','controls'} and type(form['selected']) is bool
            and form['action_path'] in (None,'/online-applications/search.do','/online-applications/advancedSearchResults.do')
            and form['method'] in (None,'POST') and len(form['controls'])<=80,'PARTIAL_RETRIEVAL','OUTPUT_INVALID')
    for i,c in enumerate(form['controls']):
        require(set(c)=={'ordinal','field','classification','populated','disabled'} and c['ordinal']==i and c['field'] in SAFE_NAMES|{None}
                and c['classification'] in CLASSES and type(c['populated']) is bool and type(c['disabled']) is bool,
                'PARTIAL_RETRIEVAL','OUTPUT_INVALID')
    good=out['outcome'] in ('RECOGNISED_RESULTS','RECOGNISED_ZERO_RESULTS')
    if not good:
        require(out['result'] is None and out['failure_reason'] is not None,'PARTIAL_RETRIEVAL','OUTPUT_INVALID'); return
    require(out['accounting_complete'] and out['requests']==2 and out['redirects']==0 and out['http_statuses']==[200,200]
            and out['received_bytes']<=MAX_TOTAL and out['failure_reason'] is None and form['selected'] and out['budget_state']=='WITHIN_LIMITS'
            and out['elapsed_seconds']<=30,'PARTIAL_RETRIEVAL','OUTPUT_INVALID')
    require(form['method']=='POST' and form['action_path'] in ('/online-applications/search.do','/online-applications/advancedSearchResults.do'),
            'PARTIAL_RETRIEVAL','OUTPUT_INVALID')
    active=[c for c in form['controls'] if not c['disabled']]
    dates=[c for c in active if c['classification']=='APPROVED_DATE_INPUT']
    submits=[c for c in active if c['classification']=='APPROVED_FIXED_SUBMIT_CONTROL']
    require(len(dates)==2 and {c['field'] for c in dates}==set(DATE_FIELDS) and not any(c['populated'] for c in dates)
            and len(submits)==1 and submits[0]['field'] in (None,'action') and submits[0]['populated']
            and not any(c['classification'] in ('UNKNOWN','PROHIBITED_SEARCH_EXPANSION') for c in active),
            'PARTIAL_RETRIEVAL','OUTPUT_INVALID')
    require(all(c['field'] in STATE_FIELDS and c['populated'] for c in active if c['classification']=='REQUIRED_SERVER_STATE'),
            'PARTIAL_RETRIEVAL','OUTPUT_INVALID')
    r=out['result']
    require(set(r)=={'source_count','pagination_present','page_ordinal','candidates','qualification'} and type(r['pagination_present']) is bool
            and r['page_ordinal']==1 and (r['source_count'] is None or type(r['source_count']) is int and 0<=r['source_count']<=100000)
            and len(r['candidates'])<=MAX_ROWS,'PARTIAL_RETRIEVAL','OUTPUT_INVALID')
    require(r['source_count'] is None or r['source_count']>=len(r['candidates']) and (r['source_count']==len(r['candidates']) or r['pagination_present']),
            'PARTIAL_RETRIEVAL','OUTPUT_INVALID')
    zero=out['outcome']=='RECOGNISED_ZERO_RESULTS'
    require((len(r['candidates'])==0)==zero and (not zero or r['source_count']==0 and not r['pagination_present']),
            'PARTIAL_RETRIEVAL','OUTPUT_INVALID')
    expected='STRUCTURAL_ZERO_FIRST_RESPONSE_ONLY' if zero else 'PAGINATION_PRESENT_STOPPED' if r['pagination_present'] else 'FIRST_RESPONSE_ONLY_COMPLETENESS_UNPROVED'
    require(r['qualification']==expected,'PARTIAL_RETRIEVAL','OUTPUT_INVALID')
    keys=set(); refs=set()
    for c in r['candidates']:
        require(set(c)=={'reference','source_key','source_path'},'PARTIAL_RETRIEVAL','OUTPUT_INVALID')
        key,path=result_link(c['source_path'])
        require(key==c['source_key'] and path==c['source_path'] and key not in keys,'PARTIAL_RETRIEVAL','OUTPUT_INVALID'); keys.add(key)
        ref=c['reference']
        require(ref is None or isinstance(ref,str) and bool(re.fullmatch(r'[A-Za-z0-9/_.-]{1,80}',ref))
                and bool(re.search(r'\d',ref)) and ref not in refs,'PARTIAL_RETRIEVAL','OUTPUT_INVALID')
        if ref: refs.add(ref)
