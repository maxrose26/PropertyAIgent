"""Offline synthetic navigation; never claims the live final-page layout."""
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
import hashlib,json,sys
import pytest
from bs4 import BeautifulSoup
from verification.discovery.pagination_calibration import directions,observe,CalibrationError
from verification.discovery import tameside_qualification as q
from tests.test_tameside_pagination_calibration import C,FORM,SEARCH,ECHO,body,perform,offline

FIXTURE=Path(__file__).parent/'fixtures/tameside_pagination/equivalent_controls.html'
def layout():return FIXTURE.read_bytes()
def soup(b):return BeautifulSoup(b,'html.parser')
def page_with_controls():return body().replace(b'</html>',layout()+b'</html>')

@pytest.mark.parametrize('mode',['observed','reversed','query-reordered','absolute-relative','single-pager'])
def test_equivalent_numbered_and_explicit_controls(mode):
    s=soup(layout())
    if mode=='reversed':
        for p in s.select('p.pager'):p.select_one('a').insert_before(p.select_one('a.next').extract())
    if mode=='query-reordered':
        for a in s.select('a.next'):a['href']='pagedSearchResults.do?searchCriteria.page=2&action=page'
    if mode=='absolute-relative':
        for a in s.select('a.next'):a['href']=C.base+'/pagedSearchResults.do?action=page&searchCriteria.page=2'
    if mode=='single-pager':s.select('p.pager')[1].decompose()
    nav,nxt=directions(s,C,1)
    assert nxt==('GET',C.base+'/pagedSearchResults.do?action=page&searchCriteria.page=2',None)
    assert len(nav['next'])==len(nav['numbered_next'])==(1 if mode=='single-pager' else 2)
    rows,p,nxt=observe(body().replace(b'</html>',str(s).encode()+b'</html>'),C,1)
    assert len(rows)==5 and p['range']==dict(first=1,last=5,total=9) and p['terminal_candidate'] is None

def test_equivalence_adds_no_requests_and_is_not_acceptance(tmp_path):
    r,c,_,_=perform(tmp_path,[FORM,SEARCH,page_with_controls(),body(2,count=4,previous=True,total=9),ECHO])
    assert r['failure'] is None and len(c)==5 and len(r['records'])==9
    assert len(r['calibration']['pages'])==2 and r['calibration']['criteria_verified'] is True
    assert r['completeness']=='UNKNOWN' and r['calibration']['acceptance_enabled'] is False
    assert r['calibration']['pages'][-1]['terminal_candidate']=='EXPLICIT_RANGE_LAST_EQUALS_TOTAL'

@pytest.mark.parametrize('query',[
'action=page&searchCriteria.page=2&searchCriteria.page=2',
'action=page&action=page&searchCriteria.page=2',
'action=page&searchCriteria.page=2&searchCriteria.page=3',
'action=page&searchCriteria.page=2&searchCriteria.page=',
'action=page&searchCriteria.page=2&unused=',
'action=page&searchCriteria.page=2&date(applicationReceivedStart)=25/10/2026',
'action=page&searchCriteria.page=2&orderBy=Date',
'action=page&searchCriteria.page=2&searchCriteria.resultsPerPage=10',
'action=page&searchCriteria.page=3',
'action=page&searchCriteria.page=02',
'action=page&searchCriteria.page=2&broken',
'action=printPreview&searchCriteria.page=2',
'action=page&searchCriteria%2Epage=2',
'action=page&searchCriteria.page=2#fragment',
],ids=['duplicate-page','duplicate-action','conflicting-page','duplicate-blank','blank-extra','changed-date','changed-sort','changed-size','skip','noncanonical-page','malformed','wrong-action','encoded-key','fragment'])
def test_meaningful_queries_never_dropped(query):
    s=soup(layout());s.select('a')[0]['href']='pagedSearchResults.do?'+query
    with pytest.raises(CalibrationError):directions(s,C,1)

@pytest.mark.parametrize('target',[
'https://evil.example/online-applications/pagedSearchResults.do?action=page&searchCriteria.page=2',
'http://publicaccess.tameside.gov.uk/online-applications/pagedSearchResults.do?action=page&searchCriteria.page=2',
'applicationDetails.do?action=page&searchCriteria.page=2',
'/online-applications/printResults.do?action=page&searchCriteria.page=2',
],ids=['origin','tls','details','print'])
def test_unsupported_destination_refuses(target):
    s=soup(layout());s.select('a.next')[0]['href']=target
    with pytest.raises(CalibrationError):directions(s,C,1)

@pytest.mark.parametrize('mode',['numbered-alone','explicit-conflict','numbered-disagree','numeric-label-target-conflict','disabled-conflict','post-vs-get','form-override'])
def test_no_new_numbered_only_or_conflicting_authority(mode):
    s=soup(layout())
    if mode=='numbered-alone':
        for n in s.select('a.next'):n.decompose()
    elif mode=='explicit-conflict':s.select('a.next')[1]['href']='pagedSearchResults.do?action=page&searchCriteria.page=3'
    elif mode=='numbered-disagree':s.select('a')[0]['href']='pagedSearchResults.do?action=page&searchCriteria.page=3'
    elif mode=='numeric-label-target-conflict':s.select('a')[0].string='3';s.select('a')[0]['href']='pagedSearchResults.do?action=page&searchCriteria.page=4'
    elif mode=='disabled-conflict':s.select('a.next')[1]['aria-disabled']='true'
    elif mode=='post-vs-get':
        for a in s.select('a.next'):a.decompose()
        s.append(soup(b'<form method="POST" action="pagedSearchResults.do"><input type="hidden" name="_csrf" value="SYNTHETIC"><input type="hidden" name="action" value="page"><button name="searchCriteria.page" value="2">Next</button></form>'))
    else:s.select('a.next')[0]['onclick']='privateSentinel()'
    with pytest.raises(CalibrationError):directions(s,C,1)

@pytest.mark.parametrize('mode',['top-bottom-range','next-with-final-range','repeat','changed-echo','duplicate-key'])
def test_existing_refusals_survive_equivalent_controls(tmp_path,mode):
    first=page_with_controls();second=body(2,count=4,previous=True,total=9);echo=ECHO
    if mode=='top-bottom-range':first=first.replace('Showing 1–5 of 9'.encode(),'Showing 1–5 of 10'.encode(),1)
    if mode=='next-with-final-range':first=first.replace('Showing 1–5 of 9'.encode(),'Showing 1–5 of 5'.encode())
    if mode=='repeat':second=first
    if mode=='changed-echo':echo=ECHO.replace(b'30/10/2026',b'31/10/2026')
    if mode=='duplicate-key':second=second.replace(b'keyVal=P2K0',b'keyVal=P1K0')
    r,c,_,_=perform(tmp_path,[FORM,SEARCH,first,second,echo])
    assert r['failure']=={'top-bottom-range':'CALIBRATION_CONTRADICTORY_COUNTS','next-with-final-range':'CALIBRATION_CONTRADICTORY_COUNTS','repeat':'CALIBRATION_REPEATED_PAGE','changed-echo':'CALIBRATION_SEARCH_BINDING','duplicate-key':'CALIBRATION_DUPLICATE_IDENTITY'}[mode]
    assert len(c)==(3 if mode in ('top-bottom-range','next-with-final-range') else 5 if mode=='changed-echo' else 4)

def bind_four(tmp_path,monkeypatch):
    for name,data,hashname in [('CONSUMPTION',b'one','PREDECESSOR_SHA256'),('SECOND_CONSUMPTION',b'two','SECOND_CONSUMPTION_SHA256'),('THIRD_CONSUMPTION',b'three','THIRD_CONSUMPTION_SHA256'),('CALIBRATION_CONSUMPTION',b'four','CALIBRATION_CONSUMPTION_SHA256')]:
        f=tmp_path/name;f.write_bytes(data);monkeypatch.setattr(q,name,f);monkeypatch.setattr(q,hashname,hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(q,'SECOND_CALIBRATION_OUTPUT',tmp_path/'new-output');monkeypatch.setattr(q,'SECOND_CALIBRATION_CONSUMPTION',tmp_path/'new-consumption')
    monkeypatch.setattr(sys,'argv',['q','--output',str(q.SECOND_CALIBRATION_OUTPUT),'--authority',q.SECOND_CALIBRATION_AUTHORITY])

@pytest.mark.parametrize('name',['CONSUMPTION','SECOND_CONSUMPTION','THIRD_CONSUMPTION','CALIBRATION_CONSUMPTION','wrong-output','wrong-authority'])
def test_corrected_authority_binds_all_four_predecessors(tmp_path,monkeypatch,name):
    bind_four(tmp_path,monkeypatch)
    if name=='wrong-output':monkeypatch.setattr(sys,'argv',['q','--output',str(tmp_path/'elsewhere'),'--authority',q.SECOND_CALIBRATION_AUTHORITY])
    elif name=='wrong-authority':monkeypatch.setattr(sys,'argv',['q','--output',str(q.SECOND_CALIBRATION_OUTPUT),'--authority','WRONG'])
    else:getattr(q,name).write_bytes(b'changed')
    monkeypatch.setattr(q,'qualify',lambda *a,**k:pytest.fail('NO_SOURCE'))
    with pytest.raises(SystemExit):q.main()
    assert not q.SECOND_CALIBRATION_CONSUMPTION.exists()

def test_corrected_authority_consumes_once_before_source(tmp_path,monkeypatch,capsys):
    bind_four(tmp_path,monkeypatch);before={n:getattr(q,n).read_bytes() for n in ['CONSUMPTION','SECOND_CONSUMPTION','THIRD_CONSUMPTION','CALIBRATION_CONSUMPTION']};calls=[]
    def stop(*a,**k):
        calls.append(k);assert json.loads(q.SECOND_CALIBRATION_CONSUMPTION.read_bytes())['state']=='CONSUMED_BEFORE_SOURCE'
        raise RuntimeError('PRIVATE_SENTINEL')
    monkeypatch.setattr(q,'qualify',stop)
    assert q.main()==2 and len(calls)==1 and calls[0]['authority']==q.SECOND_CALIBRATION_AUTHORITY and calls[0]['pagination_calibration'] is True
    with pytest.raises(SystemExit,match='CONSUMED'):q.main()
    assert len(calls)==1 and 'PRIVATE_SENTINEL' not in capsys.readouterr().out
    for n,raw in before.items():assert getattr(q,n).read_bytes()==raw

def test_new_launcher_and_old_authorities_preserved():
    d=Path(__file__).resolve().parents[1]/'docs/design/tameside-pagination-equivalence-20261101'
    text=(d/'RUN-CALIBRATION-INACTIVE.sh').read_text()
    for value in (str(q.SECOND_CALIBRATION_OUTPUT),str(q.SECOND_CALIBRATION_CONSUMPTION),q.SECOND_CALIBRATION_AUTHORITY,'EXECUTE_ONE_TAMESIDE_PAGINATION_CALIBRATION_02','--signal=INT --kill-after=2s 58s','/usr/bin/env -i','CHECK-PACKAGE.py'):
        assert value in text
    assert q.CALIBRATION_AUTHORITY=='ONE_TAMESIDE_PAGINATION_CALIBRATION_20261024_30_V1'
    assert str(q.CALIBRATION_OUTPUT).endswith('tameside-pagination-calibration-evidence-01')

@pytest.mark.parametrize('which',['AUTHORITY','SECOND_AUTHORITY','THIRD_AUTHORITY','CALIBRATION_AUTHORITY'])
def test_all_old_authorities_still_consumed(tmp_path,monkeypatch,which):
    bind_four(tmp_path,monkeypatch)
    output={'AUTHORITY':str(tmp_path/'unused'),'SECOND_AUTHORITY':str(q.SECOND_OUTPUT),'THIRD_AUTHORITY':str(q.THIRD_OUTPUT),'CALIBRATION_AUTHORITY':str(q.CALIBRATION_OUTPUT)}[which]
    monkeypatch.setattr(sys,'argv',['q','--output',output,'--authority',getattr(q,which)])
    monkeypatch.setattr(q,'qualify',lambda *a,**k:pytest.fail('NO_SOURCE'))
    with pytest.raises(SystemExit,match='CONSUMED'):q.main()
    assert not q.SECOND_CALIBRATION_CONSUMPTION.exists()

def test_corrected_authority_existing_supervised_qualifier(tmp_path,monkeypatch,capsys):
    from tests.test_tameside_page_evidence_03 import install_synthetic_session
    from verification.discovery.four_council_proof import PrivateResponseBodies,manifest_scope,write_audit,validate_private_responses
    from verification.discovery.idox_window import live
    seen=install_synthetic_session(monkeypatch,[FORM,SEARCH,page_with_controls(),body(2,count=4,previous=True,total=9),ECHO])
    def supervisor(command,**kwargs):
        assert kwargs['seconds']==45 and kwargs['source'] is True and kwargs['environment']=={'INGESTION_SOURCE_PRIVATE':'ONCE'}
        plan=json.loads(Path(command[command.index('--plan')+1]).read_bytes())
        assert plan['row']==q.ROW and plan['pagination_calibration']=='TAMESIDE_FIVE_PER_PAGE_V1'
        store=PrivateResponseBodies(plan['private_response_bodies'])
        with manifest_scope(q.ROW):result=live(C,retain_proof=True,response_evidence=store.record,pagination_calibration=True)
        store.finish()
        with manifest_scope(q.ROW):write_audit(Path(command[command.index('--output')+1]),result)
        return dict(cleanup='CLOSED',exit_code=0,limit_hit=None,expired=False,accounting_complete=True,live_owned_survivors=0,peak_owned_rss=1024,elapsed_seconds=.1)
    root=tmp_path/'out';summary=q.qualify(root,supervisor=supervisor,authority=q.SECOND_CALIBRATION_AUTHORITY,private_pages=True,pagination_calibration=True)
    assert summary['status']=='CALIBRATION_OBSERVATIONS_REQUIRE_REVIEW' and summary['observed_records']==9 and summary['observed_pages']==2
    assert (root/'CONSUMED').read_text().strip()==q.SECOND_CALIBRATION_AUTHORITY
    assert not (root/'assessment.json').exists() and summary['acceptance_enabled'] is False and summary['completeness']=='UNKNOWN'
    source=json.loads((root/'source.json').read_bytes())
    with manifest_scope(q.ROW):assert validate_private_responses(root/'raw-bodies',source)['state']=='FINISHED'
    assert len(seen['calls'])==5 and seen['closed'] and all(r.closed for r in seen['responses']) and seen['retry_total']==0 and seen['trust_env'] is False
    assert all(c['timeout']==(3,8) and c['allow_redirects'] is False and 'verify' not in c for c in seen['calls'])
    assert not capsys.readouterr().out
