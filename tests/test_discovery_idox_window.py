import io
from unittest.mock import patch
from verification.discovery.idox_window import run, WindowBoundary
from verification.bolton_recon.fixtures import FORM
from tests.test_discovery_idox_listing import page as raw_page
from verification.discovery.idox_sort import sort_payload

SORT = b'''<form method="post" action="/online-applications/pagedSearchResults.do"><input type="hidden" name="_csrf" value="fixture"><input type="hidden" name="action" value="order"><input type="hidden" name="searchCriteria.page" value="1"><select name="orderBy"><option value="Reference" selected>Ref. No.</option></select><select name="orderByDirection"><option value="Descending" selected>Descending</option></select><select name="searchCriteria.resultsPerPage"><option value="10" selected>10</option></select><input type="submit" value="Go"></form>'''

def page(**kw):
    return raw_page(**kw).replace(b'</html>',SORT+b'</html>')


class Response:
    status_code=200
    headers={'Content-Type':'text/html'}
    def __init__(self,b): self.b=b;self.closed=False;self.raw=io.BytesIO()
    def iter_content(self,n): yield self.b
    def close(self): self.closed=True


def perform(bodies):
    responses=[Response(b) for b in bodies];calls=[]
    def dispatch(method,url,**kw):
        calls.append((method,url,kw.get('data')))
        return responses[len(calls)-1]
    result=run(dispatch)
    assert all(r.closed for r in responses[:len(calls)])
    return result,calls


def test_count_reconciled_is_not_source_admission():
    echo=FORM.replace(b'name="date(applicationReceivedStart)" value=""',b'name="date(applicationReceivedStart)" value="28/09/2026"').replace(b'name="date(applicationReceivedEnd)" value=""',b'name="date(applicationReceivedEnd)" value="04/10/2026"')
    result,calls=perform([FORM,page(),page(),echo])
    assert result['enumeration_evidence']=='COUNT_RECONCILED'
    assert result['completeness']=='UNKNOWN' and result['persistence'] is False
    assert result['unique_references']==2
    assert len(calls)==4 and b'28%2F09%2F2026' in calls[1][2]


def test_page_failure_retains_partial_without_completion():
    first=page(first=1,last=10,total=12,refs=tuple(f'{i}/26' for i in range(10)),next_page=2)
    r,c=perform([FORM,first,first,b'<html>truncated'])
    assert len(r['pages'])==1 and r['completeness']=='INCOMPLETE'
    assert len(c)==4


def test_duplicate_reference_across_pages_fails_closed():
    first=page(first=1,last=10,total=12,refs=tuple(f'{i}/26' for i in range(10)),next_page=2)
    second=page(first=11,last=12,total=12,refs=('1/26','11/26')).replace(b'keyVal=K0',b'keyVal=L0').replace(b'keyVal=K1',b'keyVal=L1')
    r,c=perform([FORM,first,first,second])
    assert r['completeness']=='INCOMPLETE' and 'ambiguous reference' in r['failure']


def test_boundary_rejects_detail_and_arbitrary_window():
    import pytest
    from verification.stage26b_l1.request_boundary import BoundaryFailure
    b=WindowBoundary(lambda *a,**k: (_ for _ in ()).throw(AssertionError('no dispatch')))
    with pytest.raises(BoundaryFailure): b.retrieve('GET',b.policy.base_url+'/applicationDetails.do?keyVal=X')
    assert b.requests==0


def test_sort_form_is_bound_and_unknown_controls_fail_closed():
    import pytest
    from app.scrapers.discovery_idox import ListingError
    base='https://paplanning.bolton.gov.uk/online-applications'
    target,payload=sort_payload(page(),base)
    assert target==base+'/pagedSearchResults.do'
    assert payload['orderBy']=='Reference'
    for b in (page().replace(b'/online-applications/pagedSearchResults.do',b'https://evil.example/submit'),
              page().replace(b'</form>',b'<input name="arbitrary" value="x"></form>'),
              page().replace(b'value="Reference"',b'value="Other"')):
        with pytest.raises(ListingError):sort_payload(b,base)


def test_sort_preserves_returned_hidden_state_without_inventing_values():
    body=page().replace(b'name="action" value="order"',b'name="action" value="source-state"').replace(b'name="searchCriteria.page" value="1"',b'name="searchCriteria.page" value="source-page-state"')
    _,payload=sort_payload(body,'https://paplanning.bolton.gov.uk/online-applications')
    assert payload['action']=='source-state' and payload['searchCriteria.page']=='source-page-state'
    assert payload['orderBy']=='Reference' and payload['searchCriteria.resultsPerPage']=='10'


def test_bury_zero_requires_independently_echoed_dates():
    from verification.discovery.idox_window import WindowConfig
    config=WindowConfig('bury')
    echo=FORM.replace(b'name="date(applicationReceivedStart)" value=""',b'name="date(applicationReceivedStart)" value="28/09/2026"').replace(b'name="date(applicationReceivedEnd)" value=""',b'name="date(applicationReceivedEnd)" value="04/10/2026"')
    zero=echo.replace(b'</html>','<h1>Planning – Applications Search</h1><div class="messagebox"><h2>Please check the search criteria:</h2><ul><li>No results found.</li></ul></div></html>'.encode())
    for body,ok in ((zero,True),(zero.replace(b'04/10/2026',b'05/10/2026'),False)):
        calls=[]
        def dispatch(method,url,**kw):
            calls.append((method,url));return Response(FORM if len(calls)==1 else body)
        audit=run(dispatch,config)
        assert (audit['failure'] is None)==ok
        if ok:assert audit['unique_references']==0 and audit['explicit_zero_evidence'] and audit['completeness']=='UNKNOWN'
        assert len(calls)==2


def test_wigan_declared_encoding_is_not_guessed_and_hashes_original():
    from verification.discovery.idox_window import WindowConfig
    body='<html><p>é</p></html>'.encode('iso-8859-1')
    response=Response(body);response.headers={'Content-Type':'text/html;charset=ISO-8859-1'}
    b=WindowBoundary(lambda *a,**k:response,WindowConfig('wigan'))
    assert b.retrieve('GET',b.config.form_url)==body.decode('iso-8859-1').encode('utf-8')
    assert b.response_provenance[0]['source_encoding']=='ISO-8859-1'
    assert b.response_provenance[0]['body_sha256']!=b.response_provenance[0]['parser_body_sha256']
    response=Response(body);response.headers={'Content-Type':'text/html;charset=unqualified'}
    b=WindowBoundary(lambda *a,**k:response,WindowConfig('wigan'))
    from verification.stage26b_l1.request_boundary import BoundaryFailure
    with __import__('pytest').raises(BoundaryFailure):b.retrieve('GET',b.config.form_url)
    assert response.closed
