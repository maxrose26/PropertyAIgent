import io
from unittest.mock import patch
from verification.discovery.idox_window import run, WindowBoundary
from verification.bolton_recon.fixtures import FORM
from tests.test_discovery_idox_listing import page


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
    result,calls=perform([FORM,page(),echo])
    assert result['enumeration_evidence']=='COUNT_RECONCILED'
    assert result['completeness']=='UNKNOWN' and result['persistence'] is False
    assert result['unique_references']==2
    assert len(calls)==3 and b'28%2F09%2F2026' in calls[1][2]


def test_page_failure_retains_partial_without_completion():
    first=page(first=1,last=10,total=12,refs=tuple(f'{i}/26' for i in range(10)),next_page=2)
    r,c=perform([FORM,first,b'<html>truncated'])
    assert len(r['pages'])==1 and r['completeness']=='INCOMPLETE'
    assert len(c)==3


def test_duplicate_reference_across_pages_fails_closed():
    first=page(first=1,last=10,total=12,refs=tuple(f'{i}/26' for i in range(10)),next_page=2)
    second=page(first=11,last=12,total=12,refs=('1/26','11/26')).replace(b'keyVal=K0',b'keyVal=L0').replace(b'keyVal=K1',b'keyVal=L1')
    r,c=perform([FORM,first,second])
    assert r['completeness']=='INCOMPLETE' and 'ambiguous reference' in r['failure']


def test_boundary_rejects_detail_and_arbitrary_window():
    import pytest
    from verification.stage26b_l1.request_boundary import BoundaryFailure
    b=WindowBoundary(lambda *a,**k: (_ for _ in ()).throw(AssertionError('no dispatch')))
    with pytest.raises(BoundaryFailure): b.retrieve('GET',b.policy.base_url+'/applicationDetails.do?keyVal=X')
    assert b.requests==0
