"""Synthetic transport tests. No council truth or live network is exercised."""
from types import SimpleNamespace
import pytest
import requests
from verification.stage26b_l1.request_boundary import Boundary, Budget, Policy, BoundaryFailure
from app.config import get_council

C = get_council('oldham')
REF = 'FUL/355686/26'

def policy(): return Policy('oldham', REF, 'idox', C.base_url, C.search_url)

class Response:
    def __init__(self, data=b'fixture', status=200, headers=None):
        self.data, self.status_code, self.headers = data, status, headers or {}
        self.closed=False
    def iter_content(self, size):
        for i in range(0,len(self.data),size): yield self.data[i:i+size]
    def close(self): self.closed=True

def boundary(dispatch=None, **limits):
    return Boundary(policy(), Budget(**limits), dispatch or (lambda *a, **k:Response()))

def test_bounds_cannot_expand():
    for k,v in [('requests',21),('per_reference',11),('total_bytes',10000001),('response_bytes',2000001),('seconds',166)]:
        with pytest.raises(ValueError): Budget(**{k:v})

@pytest.mark.parametrize('url',[C.base_url+'/applicationDetails.do?activeTab=documents&keyVal=X',
    C.base_url+'/applicationDetails.do?activeTab=relatedCases&keyVal=X',
    C.base_url+'/download.pdf','https://evil.example/search.do','http://planningpa.oldham.gov.uk/online-applications/search.do',
    C.base_url+'/../search.do',C.base_url+'/%73earch.do',C.base_url+'/history.js'])
def test_route_denial_before_dispatch(url):
    b=boundary(lambda *a,**k:pytest.fail('dispatch denied'))
    with pytest.raises(BoundaryFailure): b.request('GET',url)
    assert b.requests==0

def test_exact_form():
    b=boundary()
    b.request('POST',C.base_url+'/search.do',body=b'searchCriteria.reference=FUL%2F355686%2F26')
    with pytest.raises(BoundaryFailure): b.request('POST',C.base_url+'/search.do',body=b'searchCriteria.reference=OTHER')

@pytest.mark.parametrize('matches,complete,outcome',[([],False,'PARTIAL_RETRIEVAL'),([],True,'REFERENCE_NOT_FOUND'),(['A','B'],True,'AMBIGUOUS_SOURCE_RESULT')])
def test_unique_failure(matches,complete,outcome):
    with pytest.raises(BoundaryFailure) as exc: boundary().unique(matches,complete=complete)
    assert exc.value.outcome==outcome

def test_single_key_multiple_tab_links_not_ambiguous():
    b=boundary();assert b.unique(['A','A'])=='A'
    b.request('GET',C.base_url+'/applicationDetails.do?activeTab=summary&keyVal=A')
    with pytest.raises(BoundaryFailure):b.request('GET',C.base_url+'/applicationDetails.do?activeTab=summary&keyVal=B')

def test_retry_charged_and_closed():
    responses=[Response(b'transient',503),Response()]
    seen=[]
    def dispatch(*a,**k): r=responses[len(seen)];seen.append(r);return r
    b=boundary(dispatch);b.request('GET',C.search_url)
    assert b.requests==2 and b.retries==1 and b.received_bytes==16
    assert all(r.closed for r in seen)

@pytest.mark.parametrize('exception,outcome',[(requests.Timeout(),'TIMEOUT'),(requests.ConnectionError(),'SOURCE_UNAVAILABLE')])
def test_one_retry_and_circuit(exception,outcome):
    def dispatch(*a,**k):raise exception
    b=boundary(dispatch)
    with pytest.raises(BoundaryFailure) as exc:b.request('GET',C.search_url)
    assert exc.value.outcome==outcome and b.requests==2 and b.retries==1
    other=Boundary(Policy('oldham','FUL/355201/25','idox',C.base_url,C.search_url),b.budget,dispatch)
    with pytest.raises(BoundaryFailure):other.request('GET',C.search_url)
    assert other.requests==0

def test_rate_limit_no_retry():
    r=Response(status=429);b=boundary(lambda *a,**k:r)
    with pytest.raises(BoundaryFailure) as exc:b.request('GET',C.search_url)
    assert exc.value.outcome=='RATE_LIMITED' and b.requests==1 and b.retries==0 and r.closed

@pytest.mark.parametrize('limits', [{'response_bytes':4},{'total_bytes':4}])
def test_actual_bytes_not_content_length(limits):
    r=Response(b'12345',headers={'Content-Length':'1'});b=boundary(lambda *a,**k:r,**limits)
    with pytest.raises(BoundaryFailure):b.request('GET',C.search_url)
    assert b.received_bytes==5 and b.budget.used_bytes==5 and r.closed

def test_redirect_validation_and_accounting():
    b=boundary();b.request('GET',C.search_url,redirected=True)
    b.request('GET',C.search_url,redirected=True)
    with pytest.raises(BoundaryFailure):b.request('GET',C.search_url,redirected=True)
    assert b.requests==2 and b.redirects==3

def test_cross_host_location_denied():
    r=Response(status=302,headers={'Location':'https://evil.example/'})
    b=boundary(lambda *a,**k:r)
    with pytest.raises(BoundaryFailure):b.request('GET',C.search_url)
    assert b.requests==1 and r.closed

def test_requests_exhaustion_no_later_dispatch():
    b=boundary(per_reference=1);b.request('GET',C.search_url)
    with pytest.raises(BoundaryFailure):b.request('GET',C.search_url)
    assert b.requests==1 and b.budget.failure.budget
    with pytest.raises(BoundaryFailure):b.request('GET',C.search_url)
    assert b.requests==1

def test_parser_transport_exception_conservative():
    def dispatch(*a,**k):raise ValueError('sensitive raw source')
    b=boundary(dispatch)
    with pytest.raises(BoundaryFailure) as exc:b.request('GET',C.search_url)
    assert exc.value.outcome=='PARTIAL_RETRIEVAL' and 'sensitive' not in str(exc.value)

def test_close_is_fail_closed():
    b=boundary();b.close()
    with pytest.raises(BoundaryFailure):b.request('GET',C.search_url)

def test_cooperative_deadline_is_not_independent_proof(monkeypatch):
    b=boundary();monkeypatch.setattr('verification.stage26b_l1.request_boundary.time.monotonic',lambda:b.budget.started+166)
    with pytest.raises(BoundaryFailure) as exc:b.request('GET',C.search_url)
    assert exc.value.outcome=='TIMEOUT' and b.requests==0


@pytest.mark.parametrize('body,url',[(b'searchCriteria.reference=FUL%2F355686%2F26&query=all',C.base_url+'/search.do'),
    (b'searchCriteria.reference=FUL%2F355686%2F26',C.base_url+'/search.do?query=all')])
def test_unapproved_search_fields_denied(body,url):
    b=boundary(lambda *a,**k:pytest.fail('No broad search'))
    with pytest.raises(BoundaryFailure):b.request('POST',url,body=body)

def test_truncated_wire_bytes_reconciled_before_close():
    class Broken(Response):
        raw=SimpleNamespace(tell=lambda:123)
        def iter_content(self,size):
            raise requests.exceptions.ChunkedEncodingError('source body excluded')
            yield b''
    r=Broken();b=boundary(lambda *a,**k:r)
    with pytest.raises(BoundaryFailure) as exc:b.request('GET',C.search_url)
    assert exc.value.outcome=='PARTIAL_RETRIEVAL'
    assert r.closed and b.received_bytes==123 and b.budget.used_bytes==123

def test_attachment_rejected_without_document_retention():
    r=Response(b'body',headers={'Content-Disposition':'attachment; filename="notice.pdf"'})
    b=boundary(lambda *a,**k:r)
    with pytest.raises(BoundaryFailure):b.request('GET',C.search_url)
    assert r.closed
