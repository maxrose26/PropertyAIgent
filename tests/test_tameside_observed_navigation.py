from pathlib import Path
import hashlib
from bs4 import BeautifulSoup
import pytest
from verification.discovery import pagination_calibration as p
from verification.discovery.tameside_diagnostic import CONFIG
from tests.test_period07_navigation import run,contract,outer,DEFAULT_LIMITS
from tests.test_tameside_pagination_calibration import FORM,SEARCH,ECHO,body
ROOT=Path(__file__).parent/'fixtures/tameside_pagination'
def observed():
 raw=(ROOT/'observed-first-sort-20261105.html').read_bytes()
 assert hashlib.sha256(raw).hexdigest()=='06828e49e5e451ea2ca24b469db36d6b21c77d861db3b0191875ec48fcc9a323'
 return BeautifulSoup(raw,'html.parser')

def test_observed_response_reproduces_old_refusal_and_correct_next():
 ns=dict(vars(p));exec((ROOT/'directions-before-fix.py').read_text(),ns)
 with pytest.raises(p.CalibrationError) as e:ns['directions'](observed(),CONFIG,1)
 assert e.value.code=='CALIBRATION_NAVIGATION_AMBIGUOUS' and e.value.detail=='NUMBERED_LINK_SKIPS_ADJACENT_PAGE'
 nav,nxt=p.directions(observed(),CONFIG,1)
 assert nxt==('GET',CONFIG.base+'/pagedSearchResults.do?action=page&searchCriteria.page=2',None)
 assert nav['validated_later_pages']==[3,4,5] and len(nav['next'])==len(nav['numbered_next'])==2

@pytest.mark.parametrize('mode',['no-next','different-next','changed-page','extra-param','outside-pager','onclick','far-page'])
def test_observed_pager_mutations_still_refuse(mode):
 s=observed();links=s.select('p.pager a');later=next(a for a in links if a.get_text(strip=True)=='3')
 if mode=='no-next':
  for a in s.select('a.next'):a.decompose()
 elif mode=='different-next':s.select('a.next')[1]['href']='pagedSearchResults.do?action=page&searchCriteria.page=3'
 elif mode=='changed-page':later['href']='pagedSearchResults.do?action=page&searchCriteria.page=4'
 elif mode=='extra-param':later['href']+='&session=REDACTED'
 elif mode=='outside-pager':s.append(later.extract())
 elif mode=='onclick':later['onclick']='REDACTED'
 else:later.string='7';later['href']='pagedSearchResults.do?action=page&searchCriteria.page=7'
 with pytest.raises(p.CalibrationError):p.directions(s,CONFIG,1)

def test_observed_controls_in_real_navigation_and_capture_path():
 # Real controls with synthetic listing rows; no claim about live pages 2–5.
 s=observed();nav=''.join(str(n) for n in s.select('p.pager'))
 first=body(nxt=False,total=22).replace(b'</html>',nav.encode()+b'</html>')
 pages=[first]+[body(n,count=5 if n<5 else 2,nxt=n<5,previous=True,total=22) for n in range(2,6)]
 source,calls=run([FORM,SEARCH,*pages,ECHO]);receipt=contract().project(source,outer(),DEFAULT_LIMITS,source_bytes_limit=524288)
 assert len(calls)==8 and len(receipt['records'])==22 and calls[3][1].endswith('action=page&searchCriteria.page=2')
 assert receipt['segments'][-1]['terminal']=='EXPLICIT_LAST_EQUALS_TOTAL'

def test_later_page_outside_displayed_total_refuses():
 s=observed();nav=''.join(str(n) for n in s.select('p.pager'))
 first=body(nxt=False,total=9).replace(b'</html>',nav.encode()+b'</html>')
 source,calls=run([FORM,SEARCH,first]);assert len(calls)==3 and source['failure']=='CALIBRATION_CONTRADICTORY_COUNTS'

def test_five_pages_with_two_full_pagers_fit_unchanged_trace_bound():
 pages=[]
 for n in range(1,6):
  links=''.join(f'<a href="pagedSearchResults.do?action=page&amp;searchCriteria.page={page}">{page}</a>' for page in range(1,6) if page!=n)
  if n<5:links+=f'<a class="next" href="pagedSearchResults.do?action=page&amp;searchCriteria.page={n+1}">Next</a>'
  if n>1:links+=f'<a class="previous" href="pagedSearchResults.do?action=page&amp;searchCriteria.page={n-1}">Previous</a>'
  nav=('<p class="pager">'+links+'</p>')*2
  pages.append(body(n,count=5 if n<5 else 2,total=22).replace(b'</html>',nav.encode()+b'</html>'))
 source,calls=run([FORM,SEARCH,*pages,ECHO])
 assert source['failure'] is None and len(calls)==8
 assert len(p.encoded(source['pagination_evidence']))<=p.TRACE_LIMIT==8192
 assert len(contract().project(source,outer(),DEFAULT_LIMITS,source_bytes_limit=524288)['records'])==22
 assert source['pagination_evidence']['pages'][1]['navigation_occurrences']['next']==2
