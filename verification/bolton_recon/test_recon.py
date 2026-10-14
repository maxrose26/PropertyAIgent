"""Exact Requests code under mocked send + socket denial. Never council traffic."""
import ast
import copy
import io
import json
import os
from pathlib import Path
import socket
import sys
import time
from urllib.parse import parse_qs
from unittest.mock import patch
import pytest
import requests
import yaml
from verification.bolton_recon.recon import *
from verification.bolton_recon.fixtures import FORM, RESULT, ZERO, TOKEN, Raw, offline_responses
from verification.bolton_recon.runner import supervise, admit

@pytest.fixture(autouse=True)
def external_network_denied(monkeypatch):
    def deny(*a,**kw): raise AssertionError('no network in offline acceptance')
    monkeypatch.setattr(socket.socket,'connect',deny); monkeypatch.setattr(socket.socket,'connect_ex',deny)
    monkeypatch.setattr(socket,'create_connection',deny); monkeypatch.setattr(socket,'getaddrinfo',deny)


def observe(form=FORM,result=RESULT,responses=None):
    with offline_responses(responses or [(200,form,{}),(200,result,{})]) as (seen,closed):
        r=run('a'*40,'offline')
    validate(r)
    return r,seen,closed


def test_historical_fixed_date():
    assert DATE=='2026-02-19' and DATE_VALUE=='19/02/2026'
    assert 'Validated' not in ''.join(DATE_FIELDS)
    evidence=json.loads(Path('docs/design/bolton-discovery-recon/date-evidence.json').read_text())
    assert evidence['received_date']==DATE and evidence['reference']=='00307/26'
    assert evidence['truth']=='RETAINED_HISTORICAL_FIELD_PROJECTION'


def test_two_operations_exact_payload_privacy():
    r,seen,closed=observe()
    assert r['outcome']=='RECOGNISED_RESULTS' and r['requests']==2 and len(closed)==2
    assert [(x.method,x.url) for x in seen]==[('GET',FORM_URL),('POST',BASE+'/advancedSearchResults.do?action=firstPage')]
    payload=parse_qs(seen[1].body)
    assert payload=={DATE_FIELDS[0]:[DATE_VALUE],DATE_FIELDS[1]:[DATE_VALUE],'_csrf':[TOKEN],'action':['Search']}
    audit=encode(r)
    for private in (TOKEN,'PRIVATE PROPOSAL','PRIVATE STATUS','<html','Cookie','Set-Cookie'):
        assert private.encode() not in audit
    assert r['result']['candidates'][0]['reference']=='SYNTH/001'
    assert r['result']['qualification']=='FIRST_RESPONSE_ONLY_COMPLETENESS_UNPROVED'


@pytest.mark.parametrize('insertion',[
    '<input name="searchCriteria.reference" value="123/26">',
    '<input name="searchCriteria.applicantName" value="PRIVATE PERSON">',
    '<input name="searchCriteria.address" value="PRIVATE ADDRESS">',
    '<input name="searchCriteria.postcode" value="PRIVATE POSTCODE">',
    '<input name="searchCriteria.description" value="PRIVATE PROPOSAL">',
    '<input name="date(applicationValidatedStart)" value="19/02/2026">',
    '<input name="date(applicationDecisionStart)" value="19/02/2026">',
    '<input name="mystery" type="hidden" value="PRIVATE STATE">',
    '<input name="_csrf" value="PRIVATE STATE">',
    '<select name="unknown"><option value="ALL">All</option></select>',
    '<input type="checkbox" name="searchCriteria.status" checked value="granted">'])
def test_prohibited_or_unknown_populated_controls(insertion):
    form=FORM.replace(b'</form>',insertion.encode()+b'</form>')
    r,seen,_=observe(form=form)
    assert r['outcome']=='FORM_REJECTED' and len(seen)==1
    assert b'PRIVATE' not in encode(r)


@pytest.mark.parametrize('insertion',[
    '<input name="searchCriteria.address" value="">',
    '<input name="unknownOptional" value="">',
    '<input name="searchCriteria.applicantName" value="PRIVATE" disabled>',
    '<input type="checkbox" name="searchCriteria.status" value="granted">'])
def test_ignored_controls_not_submitted(insertion):
    r,seen,_=observe(form=FORM.replace(b'</form>',insertion.encode()+b'</form>'))
    assert r['outcome']=='RECOGNISED_RESULTS'
    assert set(parse_qs(seen[1].body))==set(DATE_FIELDS)|{'_csrf','action'}


@pytest.mark.parametrize('replacement',[
    b'https://evil.invalid/search.do', b'https://paplanning.bolton.gov.uk.evil.invalid/search.do',
    b'https://u@paplanning.bolton.gov.uk/online-applications/search.do',
    b'https://paplanning.bolton.gov.uk:443/online-applications/search.do',
    b'applicationDetails.do?activeTab=summary&keyVal=K',b'advancedSearchResults.do?action=firstPage&address=x',
    b'http://paplanning.bolton.gov.uk/online-applications/search.do'])
def test_form_action_denial(replacement):
    r,seen,_=observe(form=FORM.replace(b'advancedSearchResults.do?action=firstPage',replacement))
    assert r['outcome']=='FORM_REJECTED' and len(seen)==1


@pytest.mark.parametrize('form',[
    FORM.replace(b'method="post"',b'method="get"'), FORM.replace(b'</form>',b''), FORM.replace(b'</html>',b''),
    FORM.replace(b'value=""',b'value="x"',1), FORM.replace(b'type="submit"',b'type="submit" formaction="evil"'),
    FORM.replace(b'name="_csrf"',b'name="_csrf" name="x"'),
    FORM.replace(b'<form ',b'<form target="other" '),FORM.replace(b'</body>',b'<input form="other" name="x"></body>')])
def test_malformed_forms_no_submission(form):
    r,seen,_=observe(form=form)
    assert not r['outcome'].startswith('RECOGNISED_') and len(seen)==1


def test_structural_zero():
    r,seen,_=observe(result=ZERO)
    assert r['outcome']=='RECOGNISED_ZERO_RESULTS' and r['result']['source_count']==0 and len(seen)==2


@pytest.mark.parametrize('body',[b'<html><body>No results found</body></html>', b'<html><div id="searchresults"></div></html>',
    RESULT.replace(b'</html>',b''), ZERO.replace(b'<p class="noResults">',b'<p>'), FORM])
def test_unrecognised_or_rejected_result(body):
    r,seen,_=observe(result=body)
    assert not r['outcome'].startswith('RECOGNISED_') and len(seen)==2


def test_pagination_observed_never_followed():
    body=RESULT.replace(b'</body>',b'<div class="pagination"><a href="search.do?page=2">Next</a></div></body>')
    r,seen,_=observe(result=body)
    assert r['result']['pagination_present'] and r['result']['qualification']=='PAGINATION_PRESENT_STOPPED'
    assert len(seen)==2


@pytest.mark.parametrize('link',[
    b'https://evil.invalid/applicationDetails.do?keyVal=K',b'applicationDetails.do?activeTab=documents&keyVal=K',
    b'applicationDetails.do?activeTab=furtherInformation&keyVal=K',b'applicationDetails.do?activeTab=relatedCases&keyVal=K',
    b'applicationDetails.do?activeTab=history&keyVal=K',b'download.do?keyVal=K',b'javascript:alert(1)',
    b'applicationDetails.do?keyVal=K&keyVal=Z',b'applicationDetails.do?keyVal=%4b'])
def test_result_link_denial(link):
    r,seen,_=observe(result=RESULT.replace(b'applicationDetails.do?activeTab=summary&amp;keyVal=SYNTH1',link))
    assert r['outcome']=='PARTIAL_RETRIEVAL' and len(seen)==2 and r['result'] is None


def test_key_without_displayed_reference_is_not_invented():
    r,_,_=observe(result=RESULT.replace(b'Ref. No: SYNTH/001',b'Unknown label: SYNTH/001'))
    assert r['result']['candidates'][0]['reference'] is None


@pytest.mark.parametrize('status',[301,302,303,307,308,403,404,429,500])
def test_error_status_accounting_no_retry(status):
    r,seen,closed=observe(responses=[(status,b'error-body',{'Location':'https://evil.invalid/'})])
    assert len(seen)==len(closed)==r['requests']==1 and r['retries']==0 and r['received_bytes']==10
    assert r['redirects']==(1 if status<400 else 0) and r['result'] is None


def test_response_streaming_overflow():
    r,seen,closed=observe(responses=[(200,b'X'*(MAX_BODY+100),{})])
    assert r['outcome']=='BUDGET_EXCEEDED' and r['received_bytes']==MAX_BODY+1 and len(closed)==1


def test_partial_read_bytes_counted(monkeypatch):
    class Broken(Raw):
        def read(self,n=-1,decode_content=False):
            super().read(7,decode_content=False)
            raise OSError('sensitive arbitrary exception')
    import verification.bolton_recon.fixtures as f
    monkeypatch.setattr(f,'Raw',Broken)
    r,_,closed=observe()
    assert r['outcome']=='PARTIAL_RETRIEVAL' and r['received_bytes']==7 and len(closed)==1
    assert b'sensitive arbitrary' not in encode(r)


def test_timeout_no_retry():
    r,seen,_=observe(responses=[requests.exceptions.ConnectTimeout('secret')])
    assert r['outcome']=='TIMEOUT' and r['requests']==1 and len(seen)==1 and b'secret' not in encode(r)


@pytest.mark.parametrize('headers',[{'Content-Disposition':'attachment; filename=private.pdf'},{'Content-Encoding':'gzip'},{'Content-Type':'application/json'}])
def test_non_html_download_compression_denial(headers):
    r,seen,closed=observe(responses=[(200,b'private',headers)])
    assert not r['outcome'].startswith('RECOGNISED_') and len(seen)==len(closed)==1


def test_session_security():
    t=Transport()
    try:
        assert not t.session.trust_env and t.session.auth is None
        assert t.session.get_adapter(FORM_URL).max_retries.total==0
        for method,url,data in [('GET',BASE+'/applicationDetails.do?keyVal=K',None),('POST',next(iter(POST_URLS)),{}),('GET','https://evil.invalid/',None)]:
            with pytest.raises(Failure): t.request(method,url,data)
        assert t.requests==0
    finally: t.close()
    assert t.closed


def test_query_expansion_rejected_at_transport():
    t=Transport(); t.requests=1; t.approved_form=next(iter(POST_URLS))
    try:
        with pytest.raises(Failure): t.request('POST',t.approved_form,{DATE_FIELDS[0]:DATE_VALUE,DATE_FIELDS[1]:DATE_VALUE,'reference':'123/26'})
        assert t.requests==1
    finally: t.close()


def test_request_three_denied():
    t=Transport();t.requests=2
    try:
        with pytest.raises(Failure):t.request('GET',FORM_URL)
        assert t.requests==2
    finally:t.close()


@pytest.mark.parametrize('key,value',[('requests',0),('redirects',1),('start_date','2026-02-20'),('retries',1),('failure_reason','private'),('outcome','RECOGNISED_ZERO_RESULTS')])
def test_closed_audit_reconciliation(key,value):
    r,_,_=observe();r[key]=value
    with pytest.raises(Failure):encode(r)


def test_extra_audit_values_rejected():
    r,_,_=observe();r['token']='secret'
    with pytest.raises(Failure):encode(r)
    r,_,_=observe();r['form']['controls'][0]['value']=TOKEN
    with pytest.raises(Failure):encode(r)


def test_independent_deadline_and_unrelated_survival(tmp_path):
    import subprocess
    control=subprocess.Popen([sys.executable,'-c','import time; time.sleep(10)'])
    try:
        start=time.monotonic()
        rc,expired=supervise([sys.executable,'-c','import time; time.sleep(60)'],{'PATH':'/usr/bin:/bin'},0.2)
        assert expired and rc!=0 and time.monotonic()-start<3 and control.poll() is None
    finally:control.terminate();control.wait(timeout=2)


def test_manual_workflow_contract():
    text=Path(WORKFLOW).read_text(); doc=yaml.safe_load(text)
    assert set(doc.get('on',doc.get(True)))=={'workflow_dispatch'}
    assert doc['permissions']=={'contents':'read'}
    job=doc['jobs']['recon'];assert job['runs-on']=='ubuntu-24.04' and job['timeout-minutes']==2
    assert 'environment' not in job and 'secrets.' not in text and 'persist-credentials: false' in text
    inputs=doc.get('on',doc.get(True))['workflow_dispatch']['inputs']
    assert set(inputs)=={'reviewed_sha','mode','authority'}
    assert 'AUTHORISE_BOLTON_RECEIVED_2026_02_19_ONLY' in text and '"$ATTEMPT" == 1' in text
    assert 'env -i' in text


def test_no_application_model_database_browser_imports():
    for path in Path('verification/bolton_recon').glob('*.py'):
        if path.name.startswith('test_'):continue
        for n in ast.walk(ast.parse(path.read_text())):
            modules=[a.name for a in n.names] if isinstance(n,ast.Import) else [n.module or ''] if isinstance(n,ast.ImportFrom) else []
            assert not any(m.startswith(('app','sqlalchemy','openai','playwright','supabase')) for m in modules)


def test_live_admission_rejects_local_runtime(monkeypatch):
    monkeypatch.setattr('subprocess.check_output',lambda cmd,**kw:'a'*40 if cmd[1]=='rev-parse' else '')
    with pytest.raises(ValueError):admit('a'*40,'live',AUTHORITY)


def test_whole_run_bytes_include_both_bodies(monkeypatch):
    import verification.bolton_recon.recon as m
    monkeypatch.setattr(m,'MAX_TOTAL',len(FORM)+len(RESULT)-1)
    r,seen,closed=observe()
    assert r['outcome']=='BUDGET_EXCEEDED' and r['received_bytes']==len(FORM)+len(RESULT) and len(seen)==len(closed)==2


def test_row_overflow_no_partial_metadata():
    from bs4 import BeautifulSoup
    soup=BeautifulSoup(RESULT,'html.parser')
    li=str(soup.select_one('li.searchresult'))
    body=('<html><ul id="searchresults">'+li*21+'</ul></html>').encode()
    r,_,_=observe(result=body)
    assert r['outcome']=='BUDGET_EXCEEDED' and r['result'] is None


def test_unknown_identifier_is_redacted():
    name='dynamicTokenName_0123456789ABCDEF0123456789'
    r,_,_=observe(form=FORM.replace(b'</form>',f'<input name="{name}" type="hidden" value="secret"></form>'.encode()))
    assert r['outcome']=='FORM_REJECTED' and name.encode() not in encode(r) and b'secret' not in encode(r)


def test_empty_date_fields_are_required():
    for change in (lambda f:f.replace(b'name="date(applicationReceivedStart)"',b'name="date(applicationValidatedStart)"'),
                   lambda f:f.replace(b'<html>',b'<html><base href="https://evil.invalid/">')):
        r,seen,_=observe(form=change(FORM))
        assert r['outcome']=='FORM_REJECTED' and len(seen)==1


def test_artifact_overflow_rejected():
    r,_,_=observe()
    r['execution_time']='2026-01-01T00:00:00+00:00'+' '*33000
    with pytest.raises((Failure,ValueError)): encode(r)


def test_independent_normal_and_exception_cleanup():
    for command,expected in [('pass',0),('raise RuntimeError("private")',1)]:
        status,expired=supervise([sys.executable,'-c',command],{'PATH':'/usr/bin:/bin'},2)
        assert status==expected and not expired


def test_session_closed_after_failure(monkeypatch):
    close=requests.Session.close; closed=[]
    def record(self):closed.append(True);return close(self)
    monkeypatch.setattr(requests.Session,'close',record)
    r,_,_=observe(result=b'<html></html>')
    assert closed and r['cleanup_verified'] and r['result'] is None


def test_requirements_exact_existing_lock_subset():
    root=Path('verification/ah_pg/requirements.lock').read_text().splitlines()
    selected=[l for l in Path('verification/bolton_recon/requirements.txt').read_text().splitlines() if l and not l.startswith('#')]
    assert all(l in root for l in selected)


def test_offline_ci_cannot_dispatch_live():
    text=Path('.github/workflows/da0-contract-offline.yml').read_text()
    assert '--mode offline --authority OFFLINE_ONLY' in text and '--mode live' not in text


@pytest.mark.parametrize('field,value',[('method',None),('action_path',None),('controls',[])])
def test_success_requires_complete_form_qualification(field,value):
    r,_,_=observe();r['form'][field]=value
    with pytest.raises(Failure):encode(r)


def test_success_cannot_hide_prohibited_control():
    r,_,_=observe()
    r['form']['controls'][0]['classification']='UNKNOWN'
    with pytest.raises(Failure):encode(r)


@pytest.mark.parametrize('count',[0,2])
def test_success_count_and_pagination_reconcile(count):
    r,_,_=observe();r['result']['source_count']=count
    with pytest.raises(Failure):encode(r)


def test_duplicate_result_rows_fail_instead_of_count_ambiguity():
    row=RESULT[RESULT.index(b'<li '):RESULT.index(b'</li>')+5]
    r,_,_=observe(result=b'<html><ul id="searchresults">'+row+row+b'</ul></html>')
    assert r['outcome']=='PARTIAL_RETRIEVAL' and r['failure_reason']=='IDENTITY_CONFLICT'


def test_observed_application_type_and_cancel_controls():
    # Qualified form shape: run 38534362595, body SHA 74b4be1a...68607591.
    controls = (b'<input type="hidden" name="caseAddressType" value="Application">'
                b'<input type="hidden" name="searchType" value="Application">'
                b'<input type="submit" name="org.apache.struts.taglib.html.CANCEL" value="Cancel">')
    r, seen, _ = observe(form=FORM.replace(b'</form>', controls+b'</form>'))
    assert r['outcome'] == 'RECOGNISED_RESULTS'
    payload = parse_qs(seen[1].body)
    assert payload['caseAddressType'] == ['Application']
    assert payload['searchType'] == ['Application']
    assert CANCEL_CONTROL not in payload
    for wrong in (b'Appeal', b'All', b''):
        r, seen, _ = observe(form=FORM.replace(b'</form>', controls.replace(b'value="Application"', b'value="'+wrong+b'"')+b'</form>'))
        assert r['outcome'] == 'FORM_REJECTED' and len(seen) == 1
