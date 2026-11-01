"""Synthetic only: no live finalREFINE, network, DB or qualification claims."""
from pathlib import Path
import json,hashlib,sys
import pytest
from bs4 import BeautifulSoup
from verification.discovery.pagination_calibration import observe,CalibrationError
from verification.discovery import tameside_qualification as q
from tests.test_tameside_pagination_calibration import C,FORM,SEARCH,ECHO,body,perform,offline

FIXTURES=Path(__file__).parent/'fixtures/tameside_page_identity'
def page(n):
    soup=BeautifulSoup(body(n,count=5 if n==1 else 4),'html.parser')
    for tag in soup.select('.pagination'):tag.decompose()
    result=str(soup).encode().replace(f'name="searchCriteria.page" type="hidden" value="{n}"'.encode(),b'name="searchCriteria.page" type="hidden" value="1"')
    # BeautifulSoup emits attributes in sorted order; fixture's form always resets1.
    soup=BeautifulSoup(result,'html.parser');soup.select_one('input[name="searchCriteria.page"]')['value']='1'
    return str(soup).encode().replace(b'</html>',(FIXTURES/f'page{n}-pager.html').read_bytes()+b'</html>')

@pytest.mark.parametrize('n',[1,2])
def test_response_identity_separate_from_future_sort_form(n):
    rows,p,nxt=observe(page(n),C,n)
    assert p['sort_form_page']=='1' and p['current_page']==n
    assert set(p['identity_basis'])=={'DISPLAYED_RANGE','CURRENT_PAGE_MARKER'}
    assert p['visible_current_pages']==[n,n]
    assert len(rows)==(5 if n==1 else 4) and p['range']==dict(first=1 if n==1 else 6,last=5 if n==1 else 9,total=9)
    assert (nxt is None)==(n==2)
    if n==2:assert p['terminal_candidate']=='EXPLICIT_RANGE_LAST_EQUALS_TOTAL'

@pytest.mark.parametrize('value',['1','2','8'])
def test_sort_hidden_value_is_not_response_identity(value):
    b=page(2).replace(b'name="searchCriteria.page" type="hidden" value="1"',f'name="searchCriteria.page" type="hidden" value="{value}"'.encode())
    _,p,_=observe(b,C,2);assert p['current_page']==2 and p['sort_form_page']==value

@pytest.mark.parametrize('mode',['range-only','marker-only','neither'])
def test_independent_response_identity_required(mode):
    soup=BeautifulSoup(page(2),'html.parser')
    if mode in ('marker-only','neither'):
        for n in soup.select('.showing'):n.decompose()
    if mode in ('range-only','neither'):
        for n in soup.select('p.pager > strong'):n.decompose()
    if mode=='neither':
        with pytest.raises(CalibrationError,match='CALIBRATION_PAGE_IDENTITY'):observe(str(soup).encode(),C,2)
    else:
        _,p,_=observe(str(soup).encode(),C,2)
        assert p['identity_basis']==(['DISPLAYED_RANGE'] if mode=='range-only' else ['CURRENT_PAGE_MARKER'])

@pytest.mark.parametrize('mode',['wrong-marker','conflicting-markers','overlap','gap','skip','conflicting-ranges','wrong-response'])
def test_wrong_or_conflicting_response_page_refuses(mode):
    b=page(2)
    if mode=='wrong-marker':b=b.replace(b'<strong>2</strong>',b'<strong>1</strong>')
    if mode=='conflicting-markers':b=b.replace(b'<strong>2</strong>',b'<strong>1</strong>',1)
    if mode in ('overlap','gap','skip'):b=b.replace('6–9 of 9'.encode(),{'overlap':'5–8 of 9','gap':'7–10 of 10','skip':'11–14 of 14'}[mode].encode())
    if mode=='conflicting-ranges':b=b.replace('6–9 of 9'.encode(),'6–9 of 10'.encode(),1)
    if mode=='wrong-response':b=page(1)
    with pytest.raises(CalibrationError):observe(b,C,2)

@pytest.mark.parametrize('mode',['valid','date-start','date-end','missing-echo','blank-dates','filter','sort','size','repeat','duplicate','changed-total'])
def test_full_flow_through_page_two_and_refine(tmp_path,mode):
    first=page(1);second=page(2);echo=ECHO
    if mode=='date-start':echo=echo.replace(b'24/10/2026',b'25/10/2026')
    if mode=='date-end':echo=echo.replace(b'30/10/2026',b'31/10/2026')
    if mode=='missing-echo':echo=b'<html><body>No form</body></html>'
    if mode=='blank-dates':echo=FORM
    if mode=='filter':echo=echo.replace(b'name="searchCriteria.reference" value=""',b'name="searchCriteria.reference" value="UNREQUESTED"')
    if mode=='sort':second=second.replace(b'value="Descending"',b'value="Ascending"')
    if mode=='size':
        soup=BeautifulSoup(second,'html.parser')
        for option in soup.select('select#resultsPerPage option[selected],select[name="searchCriteria.resultsPerPage"] option[selected]'):option['value']='10'
        option=soup.new_tag('option',value='5');option.string='5'
        soup.select_one('select[name="searchCriteria.resultsPerPage"]').append(option)
        second=str(soup).encode()
    if mode=='repeat':second=first
    if mode=='duplicate':second=second.replace(b'keyVal=P2K0',b'keyVal=P1K0')
    if mode=='changed-total':second=second.replace('6–9 of 9'.encode(),'6–9 of 10'.encode())
    r,c,_,root=perform(tmp_path,[FORM,SEARCH,first,second,echo])
    if mode=='valid':
        assert r['failure'] is None and len(c)==5 and len(r['records'])==9
        assert r['calibration']['criteria_verified'] is True and r['applied_interval']==['2026-10-24','2026-10-30']
        assert r['criteria_result_binding']['request_ordinal']==5 and r['calibration']['pages'][1]['current_page']==2
        assert r['completeness']=='UNKNOWN' and r['calibration']['acceptance_enabled'] is False
    else:
        assert r['failure'] is not None and r['calibration']['criteria_verified'] is False and r['applied_interval'] is None
        if mode in ('date-start','date-end','missing-echo','blank-dates','filter'):assert r['failure']=='CALIBRATION_SEARCH_BINDING' and len(c)==5
        else:assert len(c)==4
    assert not (root/'assessment.json').exists()


def bind_five(tmp_path,monkeypatch):
    entries=[('CONSUMPTION','PREDECESSOR_SHA256'),('SECOND_CONSUMPTION','SECOND_CONSUMPTION_SHA256'),('THIRD_CONSUMPTION','THIRD_CONSUMPTION_SHA256'),('CALIBRATION_CONSUMPTION','CALIBRATION_CONSUMPTION_SHA256'),('SECOND_CALIBRATION_CONSUMPTION','SECOND_CALIBRATION_CONSUMPTION_SHA256')]
    for name,h in entries:
        f=tmp_path/name;f.write_bytes(name.encode());monkeypatch.setattr(q,name,f);monkeypatch.setattr(q,h,hashlib.sha256(name.encode()).hexdigest())
    monkeypatch.setattr(q,'THIRD_CALIBRATION_OUTPUT',tmp_path/'out');monkeypatch.setattr(q,'THIRD_CALIBRATION_CONSUMPTION',tmp_path/'consume')
    monkeypatch.setattr(sys,'argv',['q','--output',str(q.THIRD_CALIBRATION_OUTPUT),'--authority',q.THIRD_CALIBRATION_AUTHORITY])
    return entries

@pytest.mark.parametrize('name',['CONSUMPTION','SECOND_CONSUMPTION','THIRD_CONSUMPTION','CALIBRATION_CONSUMPTION','SECOND_CALIBRATION_CONSUMPTION','output','authority'])
def test_new_authority_requires_all_five_originals(tmp_path,monkeypatch,name):
    bind_five(tmp_path,monkeypatch)
    if name in ('output','authority'):
        monkeypatch.setattr(sys,'argv',['q','--output',str(tmp_path/'wrong' if name=='output' else q.THIRD_CALIBRATION_OUTPUT),'--authority','WRONG' if name=='authority' else q.THIRD_CALIBRATION_AUTHORITY])
    else:getattr(q,name).write_bytes(b'changed')
    monkeypatch.setattr(q,'qualify',lambda *a,**k:pytest.fail('NO_SOURCE'))
    with pytest.raises(SystemExit):q.main()
    assert not q.THIRD_CALIBRATION_CONSUMPTION.exists()

def test_new_authority_consumes_before_source_once_and_preserves_five(tmp_path,monkeypatch,capsys):
    entries=bind_five(tmp_path,monkeypatch);calls=[]
    def stop(*a,**k):
        calls.append(k);assert json.loads(q.THIRD_CALIBRATION_CONSUMPTION.read_bytes())['state']=='CONSUMED_BEFORE_SOURCE'
        raise RuntimeError('PRIVATE_SENTINEL')
    monkeypatch.setattr(q,'qualify',stop)
    assert q.main()==2 and len(calls)==1 and calls[0]['authority']==q.THIRD_CALIBRATION_AUTHORITY
    with pytest.raises(SystemExit,match='CONSUMED'):q.main()
    assert len(calls)==1 and 'PRIVATE_SENTINEL' not in capsys.readouterr().out
    for name,h in entries:assert getattr(q,name).read_bytes()==name.encode()


def test_third_authority_supervised_qualifier_end_to_end(tmp_path,monkeypatch):
    from tests.test_tameside_page_evidence_03 import install_synthetic_session
    from verification.discovery.four_council_proof import PrivateResponseBodies,manifest_scope,write_audit,validate_private_responses
    from verification.discovery.idox_window import live
    seen=install_synthetic_session(monkeypatch,[FORM,SEARCH,page(1),page(2),ECHO])
    def supervisor(command,**kwargs):
        assert kwargs['seconds']==45 and kwargs['source'] is True and kwargs['environment']=={'INGESTION_SOURCE_PRIVATE':'ONCE'}
        plan=json.loads(Path(command[command.index('--plan')+1]).read_bytes());assert plan['row']==q.ROW
        store=PrivateResponseBodies(plan['private_response_bodies'])
        with manifest_scope(q.ROW):result=live(C,retain_proof=True,response_evidence=store.record,pagination_calibration=True)
        store.finish()
        with manifest_scope(q.ROW):write_audit(Path(command[command.index('--output')+1]),result)
        return dict(cleanup='CLOSED',exit_code=0,limit_hit=None,expired=False,accounting_complete=True,live_owned_survivors=0,peak_owned_rss=1024,elapsed_seconds=.1)
    root=tmp_path/'out';summary=q.qualify(root,supervisor=supervisor,authority=q.THIRD_CALIBRATION_AUTHORITY,private_pages=True,pagination_calibration=True)
    assert summary['status']=='CALIBRATION_OBSERVATIONS_REQUIRE_REVIEW' and summary['observed_records']==9 and summary['observed_pages']==2
    assert summary['completeness']=='UNKNOWN' and summary['acceptance_enabled'] is False and not (root/'assessment.json').exists()
    source=json.loads((root/'source.json').read_bytes())
    with manifest_scope(q.ROW):assert validate_private_responses(root/'raw-bodies',source)['state']=='FINISHED'
    assert len(seen['calls'])==5 and seen['closed'] and seen['retry_total']==0 and seen['trust_env'] is False
    assert all(c['timeout']==(3,8) and c['allow_redirects'] is False and 'verify' not in c for c in seen['calls'])

def test_guarded_launcher_bindings():
    text=(Path(__file__).resolve().parents[1]/'docs/design/tameside-page-identity-20261101/RUN-CALIBRATION-INACTIVE.sh').read_text()
    for v in [str(q.THIRD_CALIBRATION_OUTPUT),str(q.THIRD_CALIBRATION_CONSUMPTION),q.THIRD_CALIBRATION_AUTHORITY,'EXECUTE_ONE_TAMESIDE_PAGINATION_CALIBRATION_03','--signal=INT --kill-after=2s 58s','CHECK-PACKAGE.py','/usr/bin/env -i']:
        assert v in text

@pytest.mark.parametrize('name',['AUTHORITY','SECOND_AUTHORITY','THIRD_AUTHORITY','CALIBRATION_AUTHORITY','SECOND_CALIBRATION_AUTHORITY'])
def test_all_five_old_authorities_remain_consumed(tmp_path,monkeypatch,name):
    bind_five(tmp_path,monkeypatch)
    outputs={'AUTHORITY':str(tmp_path/'unused'),'SECOND_AUTHORITY':str(q.SECOND_OUTPUT),'THIRD_AUTHORITY':str(q.THIRD_OUTPUT),'CALIBRATION_AUTHORITY':str(q.CALIBRATION_OUTPUT),'SECOND_CALIBRATION_AUTHORITY':str(q.SECOND_CALIBRATION_OUTPUT)}
    monkeypatch.setattr(sys,'argv',['q','--output',outputs[name],'--authority',getattr(q,name)])
    monkeypatch.setattr(q,'qualify',lambda *a,**k:pytest.fail('NO_SOURCE'))
    with pytest.raises(SystemExit,match='CONSUMED'):q.main()
    assert not q.THIRD_CALIBRATION_CONSUMPTION.exists()
