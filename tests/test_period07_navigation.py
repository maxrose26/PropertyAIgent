"""Synthetic representative layouts, not a reconstruction of the lost live DOM."""
import hashlib,json
import pytest
from verification.discovery.pagination_calibration import run_counted_window,COUNTED_MODE
from verification.discovery.four_council_proof import manifest_scope
from verification.discovery.source_profiles import profile,bind_audit
from tests.test_tameside_pagination_calibration import C,FORM,SEARCH,ECHO,body,Response,offline
from tests.test_tameside_b_connection import ROW,contract,outer
from app.ingestion.ledger import DEFAULT_LIMITS,Denied

def run(bodies):
 calls=[]
 def dispatch(*args,**kwargs):calls.append(args);return Response(bodies[len(calls)-1])
 with manifest_scope(ROW,profile(ROW,'SCREENING_METADATA',idox_pagination=COUNTED_MODE)):
  source=run_counted_window(dispatch,C)
 return bind_audit(profile(ROW,'SCREENING_METADATA',idox_pagination=COUNTED_MODE),source),calls

def test_actual_counted_navigation_and_capture_validator_22_records():
 pages=[body(n,count=5 if n<5 else 2,nxt=n<5,previous=n>1,total=22) for n in range(1,6)]
 source,calls=run([FORM,SEARCH,*pages,ECHO])
 receipt=contract().project(source,outer(),DEFAULT_LIMITS,source_bytes_limit=524288)
 assert len(calls)==8 and len(receipt['records'])==22 and len(receipt['segments'])==5
 assert receipt['segments'][-1]['terminal']=='EXPLICIT_LAST_EQUALS_TOTAL'
 assert source['pagination_evidence']['criteria_verified'] and 'navigation_refusal' not in source

def test_actual_terminal_page_and_capture_validator():
 source,calls=run([FORM,SEARCH,body(count=3,total=3),ECHO])
 assert len(contract().project(source,outer(),DEFAULT_LIMITS,source_bytes_limit=524288)['records'])==3 and len(calls)==4

@pytest.mark.parametrize('kind,detail',[
 ('later','NUMBERED_LINK_SKIPS_ADJACENT_PAGE'),('unknown','UNCLASSIFIED_FORWARD_PAGE_LINK'),
 ('numbered_only','NUMBERED_WITHOUT_EXPLICIT_NEXT'),('select','POST_SELECT_NOT_SINGLE')])
def test_refusal_diagnostic_does_not_relax_navigation(kind,detail):
 page=body(nxt=kind not in ('numbered_only','select'),total=22)
 link='<a href="pagedSearchResults.do?action=page&amp;searchCriteria.page=3">3</a>'
 if kind=='unknown':link=link.replace('>3<','>PRIVATE_SENTINEL<')
 if kind=='numbered_only':link=link.replace('page=3','page=2').replace('>3<','>2<')
 if kind=='select':link='<form method="POST" action="pagedSearchResults.do"><input type="hidden" name="_csrf" value="PRIVATE_SECRET"><select name="searchCriteria.page"><option value="2">2</option></select><button>Next</button></form>'
 page=page.replace(b'</html>',link.encode()+b'</html>')
 source,calls=run([FORM,SEARCH,page]);d=source['navigation_refusal']
 assert source['failure']=='CALIBRATION_NAVIGATION_AMBIGUOUS' and len(calls)==3
 assert d==dict(version='PAGINATION_REFUSAL_V1',check=detail,stage='PAGE_PARSE',ordinal=1,body_sha256=hashlib.sha256(page).hexdigest())
 assert 'PRIVATE' not in json.dumps(d)
 with pytest.raises(Denied,match='IDOX_PAGINATION_PROFILE_BINDING'):contract().project(source,outer(),DEFAULT_LIMITS,source_bytes_limit=524288)
