"""One fixed source-only observation. Never enumerates, refines, or admits data."""
from datetime import date
import hashlib,json,re,time
from urllib.parse import urlsplit,parse_qsl,urlencode,urljoin
import requests
from bs4 import BeautifulSoup,Comment
from .idox_window import WindowConfig,WindowBoundary
from .idox_sort import sort_payload
from .pagination_calibration import directions,observe,CalibrationError
from verification.stage26b_l1.request_boundary import Budget,BoundaryFailure

MODE='TAMESIDE_FIRST_SORT_DIAGNOSTIC_V1'
ROW=dict(council='tameside',semantics='RECEIVED',start='2026-10-27',end='2026-11-02')
CONFIG=WindowConfig('tameside','RECEIVED',date(2026,10,27),date(2026,11,2),0,60)
FIELDS={'action','searchCriteria.page','orderBy','orderByDirection','searchCriteria.resultsPerPage'}
LABELS={'next','next page','next >','next »','>','»','previous','prev','previous page','<','«','load more','more results','more applications'}

def safe_value(v):
 return v if v in {'page','Reference','Descending','Ascending'} or re.fullmatch(r'[0-9]{1,3}',v or '') else 'REDACTED'

def safe_url(v):
 u=urlsplit(urljoin(CONFIG.base+'/',v));base=urlsplit(CONFIG.base)
 if u.scheme!='https' or u.netloc!=base.netloc or u.path!=base.path+'/pagedSearchResults.do' or u.fragment or '%' in v:return 'https://redacted.invalid/unsupported'
 pairs=parse_qsl(u.query,keep_blank_values=True)
 return u.path+('?' + urlencode([(k if k in FIELDS else 'redacted',safe_value(x) if k in FIELDS else 'REDACTED') for k,x in pairs]) if u.query else '')

def sanitise(body):
 """Only structural markup and closed vocabulary survive; never raw HTML."""
 soup=BeautifulSoup(body.decode('utf-8','strict'),'html.parser')
 for n in soup.select('script,style,iframe,svg,object,template'):n.decompose()
 for n in soup.find_all(string=True):
  value=' '.join(str(n).split())
  if isinstance(n,Comment):n.extract();continue
  allowed=value.casefold() in LABELS or bool(re.fullmatch(r'[0-9]{1,3}|Showing\s+\d{1,3}\s*(?:-|–|to)\s*\d{1,3}\s+of\s+\d{1,3}',value,re.I))
  n.replace_with(value if allowed else '')
 for n in soup.find_all(True):
  attrs={}
  for k,v in n.attrs.items():
   if k in ('href','action','formaction'):attrs[k]=safe_url(v)
   elif k=='name':attrs[k]=v if v in FIELDS|{'_csrf'} else 'redacted'
   elif k=='value':
    field=n.get('name') if n.name!='option' else (n.find_parent('select').get('name') if n.find_parent('select') else None)
    attrs[k]=safe_value(v) if field in FIELDS else 'REDACTED'
   elif k in ('disabled','hidden','selected'):attrs[k]=''
   elif k in ('aria-disabled','aria-hidden') and v=='true':attrs[k]=v
   elif k=='style' and re.search(r'display\s*:\s*none',v,re.I):attrs[k]='display:none'
   elif k in ('onclick','formmethod','formenctype'):attrs[k]='REDACTED'
   elif k=='method':attrs[k]=v.upper() if v.upper() in ('POST','GET') else 'REDACTED'
   elif k=='type':attrs[k]=v if v in ('submit','button','hidden') else 'text'
   elif k=='role' and v=='button':attrs[k]=v
   elif k=='aria-label':attrs[k]=v if v.casefold() in LABELS else ''
   elif k in ('class','rel'):attrs[k]=[x for x in v if x in {'next','prev','previous','disabled','current','pager','pagination','paging'}]
  n.attrs=attrs
 raw=str(soup).encode();assert len(raw)<=100000
 return raw

def decision(body):
 try:
  _,nxt=directions(BeautifulSoup(body,'html.parser'),CONFIG,1)
  if nxt and nxt[2]:
   nxt=(nxt[0],nxt[1],urlencode([(k,'REDACTED' if k=='_csrf' else v) for k,v in parse_qsl(nxt[2].decode())]))
  return dict(code='PASS',detail=None,next=nxt)
 except CalibrationError as e:return dict(code=e.code,detail=e.detail,next=None)

class DiagnosticBoundary(WindowBoundary):
 def __init__(self,dispatch):
  super().__init__(dispatch,CONFIG,calibration_navigation=True)
  self.budget=Budget(requests=3,per_reference=3,total_bytes=3000000,response_bytes=500000,seconds=45)
 def request(self,*args,**kwargs):
  # Do not even charge a rejected fourth attempt as a physical request.
  if self.requests>=3:self.budget.reject('PARTIAL_RETRIEVAL','request ceiling',True)
  return super().request(*args,**kwargs)

def run(dispatch):
 b=DiagnosticBoundary(dispatch);out=dict(version=MODE,row=ROW,status='INCOMPLETE',coverage='NOT_ESTABLISHED',failure=None,stage='FORM',sanitised_html=None)
 try:
  form=b.retrieve('GET',CONFIG.form_url)
  target,fields=CONFIG.payload(form)
  for stage in ('SEARCH','SORT'):
   out['stage']=stage;b.phase=stage;b.admitted_post=target;b.admitted_body=urlencode(fields).encode()
   body=b.retrieve('POST',target,b.admitted_body);fields.clear();b.admitted_body=None
   if stage=='SEARCH':target,fields=sort_payload(body,CONFIG.base,calibration_five=True)
  out['stage']='PAGE_PARSE';original=decision(body);clean=sanitise(body)
  if decision(clean)!=original:raise ValueError('SANITISATION_DECISION_CHANGED')
  out.update(status='OBSERVED_FIRST_SORT_ONLY',original_body_sha256=hashlib.sha256(body).hexdigest(),sanitised_sha256=hashlib.sha256(clean).hexdigest(),sanitised_html=clean.decode(),navigation=original)
  try:observe(body,CONFIG,1);out['page_parse']='PASS'
  except CalibrationError as e:out['page_parse']=e.code
  # Unconditional stop. No PAGE or REFINE operation exists in this mode.
 except BaseException as e:
  out['failure']=e.code if isinstance(e,CalibrationError) else 'REQUEST_BOUNDARY_REFUSED' if isinstance(e,BoundaryFailure) else 'DIAGNOSTIC_REFUSED'
 finally:
  b.admitted_body=None;b.close();out.update(physical_requests=b.requests,retries=b.retries,bytes=b.received_bytes,cleanup='BOUNDARY_CLOSED')
 return out

def live():
 with requests.Session() as session:
  session.trust_env=False;session.mount('https://',requests.adapters.HTTPAdapter(max_retries=0));last=[None]
  def dispatch(method,url,**kwargs):
   if last[0] is not None:time.sleep(max(0,0.4-(time.monotonic()-last[0])))
   last[0]=time.monotonic();kwargs.pop('deadline',None)
   kwargs['timeout']=(3,min(8,kwargs['timeout']))
   return session.request(method,url,**kwargs)
  result=run(dispatch)
 result['cleanup']='SESSION_BOUNDARY_CLOSED'
 return result
