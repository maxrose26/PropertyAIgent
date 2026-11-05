import io,json
from types import SimpleNamespace
import pytest,requests
from verification.discovery import tameside_diagnostic as d
from verification.ingestion_storage.daily_intake_runtime import source_worker
from tests.test_tameside_pagination_calibration import FORM,SEARCH,body
from verification.stage26b_l1.request_boundary import BoundaryFailure

def worker(tmp_path,monkeypatch,responses):
 calls=[]
 def send(adapter,request,**kw):
  calls.append((request,kw));value=responses[len(calls)-1]
  assert adapter.max_retries.total==0
  if isinstance(value,Exception):raise value
  raw,status,headers=value if isinstance(value,tuple) else (value,200,{})
  r=requests.Response();r.status_code=status;r.headers={'Content-Type':'text/html',**headers};r.raw=io.BytesIO(raw);r.url=request.url;r.request=request
  return r
 monkeypatch.setattr(requests.adapters.HTTPAdapter,'send',send)
 monkeypatch.setattr(d.time,'sleep',lambda x:None)
 for key in list(__import__('os').environ):
  if 'DATABASE' in key or key.endswith(('_KEY','_TOKEN','_PASSWORD')):monkeypatch.delenv(key)
 monkeypatch.setenv('INGESTION_SOURCE_PRIVATE','ONCE')
 plan=tmp_path/'plan.json';out=tmp_path/'out.json';plan.write_text(json.dumps(dict(row=d.ROW,fixture=None,diagnostic_mode=d.MODE)))
 source_worker(SimpleNamespace(plan=str(plan),output=str(out)))
 return json.loads(out.read_text()),calls

def test_real_worker_session_sort_stops_and_sanitises(tmp_path,monkeypatch):
 page=body(nxt=True,total=22).replace(b'</html>',b'<a href="pagedSearchResults.do?action=page&amp;searchCriteria.page=3">3</a><input name="session" value="NEVER_RETAIN"><script>COOKIE_SECRET</script></html>')
 result,calls=worker(tmp_path,monkeypatch,[FORM,SEARCH,page])
 assert len(calls)==result['physical_requests']==3 and result['retries']==0
 assert result['cleanup']=='SESSION_BOUNDARY_CLOSED' and result['navigation']['detail']=='NUMBERED_LINK_SKIPS_ADJACENT_PAGE'
 assert 'NEVER_RETAIN' not in json.dumps(result) and 'COOKIE_SECRET' not in json.dumps(result)
 assert d.decision(result['sanitised_html'].encode())==d.decision(page)
 assert all(c[0].method==m for c,m in zip(calls,['GET','POST','POST']))
 assert '27%2F10%2F2026' in calls[1][0].body.decode() and '02%2F11%2F2026' in calls[1][0].body.decode()
 assert 'resultsPerPage=5' in calls[2][0].body.decode()

@pytest.mark.parametrize('page',[body(nxt=True,total=22),body(count=3,total=3)])
def test_valid_pages_also_stop_before_next_or_refine(tmp_path,monkeypatch,page):
 result,calls=worker(tmp_path,monkeypatch,[FORM,SEARCH,page]);assert len(calls)==3 and result['page_parse']=='PASS'

@pytest.mark.parametrize('response',[(b'',302,{'Location':'https://publicaccess.tameside.gov.uk/online-applications/search.do?action=advanced&searchType=Application'}),requests.Timeout('SECRET'),requests.ConnectionError('SECRET')])
def test_redirect_and_transport_failure_never_retry(tmp_path,monkeypatch,response):
 result,calls=worker(tmp_path,monkeypatch,[response]);assert len(calls)==result['physical_requests']==1 and result['retries']==0
 assert result['sanitised_html'] is None and 'SECRET' not in json.dumps(result)

def test_fourth_dispatch_impossible():
 calls=[]
 from tests.test_discovery_idox_window import Response
 b=d.DiagnosticBoundary(lambda *a,**kw:(calls.append(a) or Response(FORM)))
 for _ in range(3):b.retrieve('GET',d.CONFIG.form_url)
 with pytest.raises(BoundaryFailure):b.retrieve('GET',d.CONFIG.form_url)
 assert len(calls)==b.requests==3

@pytest.mark.parametrize('fragment',[
 '<form method="POST" action="pagedSearchResults.do"><input type="hidden" name="_csrf" value="SECRET"><input type="hidden" name="action" value="page"><button name="searchCriteria.page" value="2">Next</button></form>',
 '<a href="pagedSearchResults.do?action=page&searchCriteria.page=2&session=SECRET">Next</a>',
 '<a class="next" onclick="SECRET()" href="pagedSearchResults.do?action=page&searchCriteria.page=2">Next</a>'])
def test_token_redaction_preserves_decision(fragment):
 raw=fragment.encode();clean=d.sanitise(raw);assert b'SECRET' not in clean and d.decision(raw)==d.decision(clean)
