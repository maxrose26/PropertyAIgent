"""Synthetic only. No network or live portal claims."""
from datetime import date
import hashlib,json,os
from pathlib import Path
import pytest
from verification.discovery.idox_window import WindowConfig
from verification.discovery.pagination_calibration import observe,run_calibration,checkpoint,CalibrationError
from verification.discovery.four_council_proof import PrivateResponseBodies
from verification.bolton_recon.fixtures import FORM
from tests.test_discovery_idox_window import page as oldpage,Response,SORT
C=WindowConfig('tameside','RECEIVED',date(2026,10,24),date(2026,10,30),0,60)
ECHO=FORM.replace(b'name="date(applicationReceivedStart)" value=""',b'name="date(applicationReceivedStart)" value="24/10/2026"').replace(b'name="date(applicationReceivedEnd)" value=""',b'name="date(applicationReceivedEnd)" value="30/10/2026"')

def body(n=1, *, count=5, nxt=False, previous=False, total=None):
    refs=tuple(f'{(n-1)*5+i+1:03}/26' for i in range(count))
    b=oldpage(refs=refs,pager=False).replace(b'Mon 28 Sep 2026',b'Tue 27 Oct 2026')
    for i in reversed(range(count)):b=b.replace(f'keyVal=K{i}'.encode(),f'keyVal=P{n}K{i}'.encode())
    b=b.replace(b'value="10" selected>10',b'value="5" selected>5')
    b=b.replace(b'name="action" value="order"',b'name="action" value="page"').replace(b'name="searchCriteria.page" value="1"',f'name="searchCriteria.page" value="{n}"'.encode())
    nav=f'<div class="pagination"><span class="current">{n}</span>'
    if total is not None:nav+=f'<p class="pager">Showing {(n-1)*5+1}-{(n-1)*5+count} of {total}</p>'
    if nxt:nav+=f'<a rel="next" href="pagedSearchResults.do?action=page&amp;searchCriteria.page={n+1}">Next</a>'
    if previous:nav+=f'<a rel="prev" href="pagedSearchResults.do?action=page&amp;searchCriteria.page={n-1}">Previous</a>'
    return b.replace(b'</html>',(nav+'</div></html>').encode())

SEARCH=body().replace(b'<option value="5" selected>5</option>',b'<option value="5">5</option><option value="10" selected>10</option>')

@pytest.fixture(autouse=True)
def offline(monkeypatch):
    import socket,requests
    def no(*a,**k):raise AssertionError('OFFLINE_NETWORK_FORBIDDEN')
    monkeypatch.setattr(socket,'getaddrinfo',no);monkeypatch.setattr(socket.socket,'connect',no)
    monkeypatch.setattr(requests.sessions.Session,'request',no)
    for k in list(os.environ):
        if 'DATABASE' in k or k.endswith(('_KEY','_TOKEN','_PASSWORD')):monkeypatch.delenv(k)

def perform(tmp_path,bodies,alter=None):
    root=tmp_path/'run';root.mkdir(mode=0o700)
    (root/'raw-bodies').mkdir(mode=0o700);store=PrivateResponseBodies(root/'raw-bodies');calls=[];responses=[]
    if alter:alter(store)
    def dispatch(method,url,**kw):
        calls.append((method,url,kw));v=bodies[len(calls)-1]
        if isinstance(v,Exception):raise v
        r=Response(v);responses.append(r);return r
    from verification.discovery.four_council_proof import manifest_scope
    with manifest_scope(dict(council='tameside',semantics='RECEIVED',start='2026-10-24',end='2026-10-30')):
        out=run_calibration(dispatch,C,response_evidence=store.record)
    retained=store.finish()
    assert all(r.closed for r in responses)
    assert out['cleanup']=='BOUNDARY_CLOSED'
    assert out['completeness']!='COMPLETE'
    assert out['calibration']['acceptance_enabled'] is False
    return out,calls,retained,root

def test_valid_returned_next_no_total_never_accepts(tmp_path):
    r,c,ret,root=perform(tmp_path,[FORM,SEARCH,body(nxt=True),body(2,count=4,previous=True),ECHO])
    assert r['failure'] is None and len(c)==5 and len(r['records'])==9
    assert r['calibration']['criteria_verified'] is True
    assert r['calibration']['pages'][1]['terminal_candidate']=='NO_NEXT_CONTROL'
    assert r['enumeration_evidence']=='CALIBRATION_OBSERVATION_ONLY'
    progress=json.loads((root/'calibration-progress.json').read_bytes())
    assert progress==r['calibration'] and 'fixture' not in json.dumps(progress)
    assert c[2][2]['data'].count(b'resultsPerPage=5')==1
    assert c[3][0]=='GET' and 'searchCriteria.page=2' in c[3][1]
    assert len((root/'calibration-progress.json').read_bytes())<=8192

def test_returned_post_next_copies_actual_fresh_controls(tmp_path):
    b=body(nxt=True)
    start=b.index(b'<a rel="next"');end=b.index(b'</a>',start)+4
    control=b'<form method="POST" action="pagedSearchResults.do"><input type="hidden" name="_csrf" value="PRIVATE_SENTINEL"><input type="hidden" name="action" value="page"><button name="searchCriteria.page" value="2">Next</button></form>'
    b=b[:start]+control+b[end:]
    r,c,_,_=perform(tmp_path,[FORM,SEARCH,b,body(2,count=1,previous=True),ECHO])
    assert r['failure'] is None and c[3][0]=='POST' and b'PRIVATE_SENTINEL' in c[3][2]['data']
    assert 'PRIVATE_SENTINEL' not in json.dumps(r)

@pytest.mark.parametrize('change,code',[
    (lambda b:b.replace(b'rel="next"',b'onclick="SECRET()" rel="next"'),'CALIBRATION_NAVIGATION_UNSUPPORTED'),
    (lambda b:b.replace(b'</html>',b'<a class="next" href="pagedSearchResults.do?action=page&amp;searchCriteria.page=3">Next</a></html>'),'CALIBRATION_NAVIGATION_UNSUPPORTED'),
    (lambda b:b.replace(b'</html>',b'<button disabled>Next</button></html>'),'CALIBRATION_NAVIGATION_CONFLICT'),
    (lambda b:b.replace(b'value="5" selected>5',b'value="10" selected>10'),'CALIBRATION_SORT_CHANGED'),
    (lambda b:b.replace(b'value="Descending" selected',b'value="Ascending" selected'),'CALIBRATION_SORT_CHANGED'),
    (lambda b:b.replace(b'name="searchCriteria.page" value="1"',b'name="searchCriteria.page" value="9"'),'CALIBRATION_PAGE_IDENTITY'),
    (lambda b:b.replace(b'</html>',b'<div class="error">SECRET</div></html>'),'CALIBRATION_ERROR_RESPONSE'),
    (lambda b:b.replace(b'</html>',b'<div class="error">Session has expired SECRET</div></html>'),'CALIBRATION_SESSION_EXPIRED'),
    (lambda b:b.replace(b'</html>',b'<p class="pager">Showing 1-5 of 5</p></html>'),'CALIBRATION_CONTRADICTORY_COUNTS'),
    (lambda b:b.replace(b'Next</a>',b'2</a>').replace(b'rel="next"',b''),'CALIBRATION_NAVIGATION_AMBIGUOUS'),
    (lambda b:b.replace(b'</html>',b'<button>Load more</button></html>'),'CALIBRATION_NAVIGATION_UNSUPPORTED'),
])
def test_observation_refusals(change,code):
    with pytest.raises(CalibrationError,match=code):observe(change(body(nxt=True)),C,1)

@pytest.mark.parametrize('control,expected',[(b'<button disabled>Next</button>','NEXT_DISABLED'),(b'', 'NO_NEXT_CONTROL')])
def test_terminal_candidate_alone_not_completeness(control,expected):
    rows,p,nxt=observe(body(count=2).replace(b'</html>',control+b'</html>'),C,1)
    assert p['terminal_candidate']==expected and nxt is None and p['range'] is None

@pytest.mark.parametrize('second,expected',[
    (body(nxt=True),'CALIBRATION_REPEATED_PAGE'),
    (body(2,previous=True).replace(b'keyVal=P2K0',b'keyVal=P1K0'),'CALIBRATION_DUPLICATE_IDENTITY'),
    (body(2,previous=True).replace(b'006/26',b'001/26'),'CALIBRATION_DUPLICATE_IDENTITY'),
    (body(2,previous=True,total=11),'CALIBRATION_CONTRADICTORY_COUNTS'),
],ids=['repeat','duplicate-key','duplicate-reference','count-conflict'])
def test_repeated_duplicate_conflicting_pages(tmp_path,second,expected):
    r,c,_,_=perform(tmp_path,[FORM,SEARCH,body(nxt=True),second])
    assert r['failure']==expected and len(c)==4
    assert len(r['calibration']['pages'])==1

def test_wrong_date_echo_stops_without_acceptance(tmp_path):
    r,c,_,_=perform(tmp_path,[FORM,SEARCH,body(),ECHO.replace(b'30/10/2026',b'31/10/2026')])
    assert r['failure']=='CALIBRATION_SEARCH_BINDING' and len(c)==4

def test_page_cap_stops_before_next_or_refine(tmp_path):
    r,c,_,_=perform(tmp_path,[FORM,SEARCH]+[body(n,nxt=True,previous=n>1) for n in range(1,7)])
    assert r['failure']=='CALIBRATION_PAGE_CAP' and len(c)==8
    assert len(r['calibration']['pages'])==6

def test_unknown_exception_is_fixed_safe_no_retry(tmp_path):
    r,c,_,_=perform(tmp_path,[RuntimeError('SECRET https://private/?token=PRIVATE_SENTINEL')])
    assert len(c)==1 and r['failure']=='CALIBRATION_UNKNOWN'
    assert 'SECRET' not in json.dumps(r) and 'PRIVATE_SENTINEL' not in json.dumps(r)

@pytest.mark.parametrize('reason,expected',[('run deadline','CALIBRATION_DEADLINE'),('request ceiling','CALIBRATION_REQUEST_CAP'),('response byte ceiling','CALIBRATION_BYTE_CAP')])
def test_budget_failures(tmp_path,reason,expected):
    from verification.stage26b_l1.request_boundary import BoundaryFailure
    import inspect
    # BoundaryFailure's fixed constructor preserves its existing resource reason.
    e=BoundaryFailure('PARTIAL_RETRIEVAL',reason)
    r,c,_,_=perform(tmp_path,[e])
    assert r['failure']==expected and len(c)==1

def test_retention_failure_refuses_immediately(tmp_path):
    def fail(store):store.failed='SYNTHETIC_WRITE_FAILURE'
    r,c,_,_=perform(tmp_path,[FORM],fail)
    assert r['failure']=='CALIBRATION_RETENTION_INCOMPLETE' and len(c)==1

@pytest.mark.parametrize('kind',['symlink','permissions','overflow','write'])
def test_private_checkpoint_refuses(tmp_path,kind,monkeypatch):
    root=tmp_path/'owner';root.mkdir(mode=0o700);p=root/'calibration-progress.json'
    if kind=='symlink':p.symlink_to(tmp_path/'target')
    if kind=='permissions':root.chmod(0o755)
    if kind=='write':monkeypatch.setattr(os,'replace',lambda *a:(_ for _ in ()).throw(OSError('SECRET')))
    with pytest.raises(CalibrationError) as e:checkpoint(p,{'x':'X'*9000} if kind=='overflow' else {'ok':True})
    assert 'SECRET' not in str(e.value)

def test_defaults_preserved_and_contract_refuses_observation(tmp_path):
    from verification.discovery.idox_sort import sort_payload
    from app.scrapers.discovery_idox import parse_page
    from app.ingestion.idox_adapter import IdoxListingContract
    from app.ingestion.ledger import DEFAULT_LIMITS
    assert sort_payload(SEARCH,C.base)[1]['searchCriteria.resultsPerPage']=='10'
    assert parse_page(body(count=2),C.council,1,C.start,C.end).terminal is None
    r,c,_,_=perform(tmp_path,[FORM,SEARCH,body(),ECHO])
    with pytest.raises(Exception):IdoxListingContract('tameside-screening-metadata-v1',C,'a'*64).project(r,{},DEFAULT_LIMITS,source_bytes_limit=524288)

@pytest.mark.parametrize('which',['first','second','third','output','authority'])
def test_new_authority_refuses_bad_binding_before_consumption(tmp_path,monkeypatch,which):
    from verification.discovery import tameside_qualification as q
    import sys
    for prefix,data in [('','one'),('SECOND_','two'),('THIRD_','three')]:
        p=tmp_path/data;p.write_text(data);monkeypatch.setattr(q,prefix+'CONSUMPTION',p)
        monkeypatch.setattr(q,'PREDECESSOR_SHA256' if not prefix else prefix+'CONSUMPTION_SHA256',hashlib.sha256(data.encode()).hexdigest())
    monkeypatch.setattr(q,'CALIBRATION_OUTPUT',tmp_path/'out');monkeypatch.setattr(q,'CALIBRATION_CONSUMPTION',tmp_path/'consumed')
    if which in ('first','second','third'):getattr(q,{'first':'CONSUMPTION','second':'SECOND_CONSUMPTION','third':'THIRD_CONSUMPTION'}[which]).write_text('changed')
    monkeypatch.setattr(q,'qualify',lambda *a,**k:pytest.fail('NO_SOURCE'))
    monkeypatch.setattr(sys,'argv',['q','--output',str(tmp_path/'wrong' if which=='output' else q.CALIBRATION_OUTPUT),'--authority','BAD' if which=='authority' else q.CALIBRATION_AUTHORITY])
    with pytest.raises(SystemExit):q.main()
    assert not q.CALIBRATION_CONSUMPTION.exists()

def test_new_consumption_durable_before_source_and_repeat_refuses(tmp_path,monkeypatch,capsys):
    from verification.discovery import tameside_qualification as q
    import sys
    for prefix,data in [('','one'),('SECOND_','two'),('THIRD_','three')]:
        p=tmp_path/data;p.write_text(data);monkeypatch.setattr(q,prefix+'CONSUMPTION',p)
        monkeypatch.setattr(q,'PREDECESSOR_SHA256' if not prefix else prefix+'CONSUMPTION_SHA256',hashlib.sha256(data.encode()).hexdigest())
    monkeypatch.setattr(q,'CALIBRATION_OUTPUT',tmp_path/'out');monkeypatch.setattr(q,'CALIBRATION_CONSUMPTION',tmp_path/'consumed')
    calls=[]
    def refuse(*a,**kw):
        calls.append(kw);assert json.loads(q.CALIBRATION_CONSUMPTION.read_bytes())['state']=='CONSUMED_BEFORE_SOURCE'
        raise RuntimeError('PRIVATE_SENTINEL')
    monkeypatch.setattr(q,'qualify',refuse)
    monkeypatch.setattr(sys,'argv',['q','--output',str(q.CALIBRATION_OUTPUT),'--authority',q.CALIBRATION_AUTHORITY])
    assert q.main()==2 and len(calls)==1 and calls[0]['pagination_calibration'] is True
    with pytest.raises(SystemExit,match='CONSUMED'):q.main()
    assert len(calls)==1 and 'PRIVATE_SENTINEL' not in capsys.readouterr().out
    assert q.CONSUMPTION.read_text()=='one' and q.SECOND_CONSUMPTION.read_text()=='two' and q.THIRD_CONSUMPTION.read_text()=='three'

def test_launcher_guards_and_unchanged_envelope():
    from verification.discovery import tameside_qualification as q
    s=(Path(__file__).resolve().parents[1]/'docs/design/tameside-pagination-calibration-20261101/RUN-CALIBRATION-INACTIVE.sh').read_text()
    for expected in (str(q.CALIBRATION_OUTPUT),str(q.CALIBRATION_CONSUMPTION),q.CALIBRATION_AUTHORITY,'EXECUTE_ONE_TAMESIDE_PAGINATION_CALIBRATION','--signal=INT --kill-after=2s 58s','-t 0 && -t 2','/usr/bin/env -i','CHECK-PACKAGE.py'):
        assert expected in s
    assert s.index('CHECK-PACKAGE.py')<s.index('read -r')<s.index('--authority')

def test_nested_reader_passes_mode_and_private_path_and_closes_session(tmp_path,monkeypatch):
    from verification.discovery import finite_acceptance as finite,tameside_qualification as q
    from verification.discovery.source_profiles import profile
    from tests.test_tameside_page_evidence_03 import install_synthetic_session
    import sys
    (tmp_path/'raw-bodies').mkdir(mode=0o700)
    seen=install_synthetic_session(monkeypatch,[FORM,SEARCH,body(nxt=True),body(2,count=4,previous=True),ECHO]);commands=[]
    def supervise(command,*,env,deadline):
        assert deadline==50 and set(env)=={'PATH','HOME','TMPDIR','PYTHONDONTWRITEBYTECODE'}
        assert '--tameside-pagination-calibration' in command and '--no-transport-retry' in command
        commands.append(command);monkeypatch.setattr(sys,'argv',['finite',*command[3:]])
        finite.main();return 0,False
    monkeypatch.setattr(finite,'supervise',supervise)
    p=profile(q.ROW,'SCREENING_METADATA')
    result=finite.read(q.ROW,no_transport_retry=True,retain_proof=True,fixed_four_rows=True,campaign_scope=q.ROW,collection_profile=p,private_response_bodies=tmp_path/'raw-bodies',pagination_calibration=True)
    assert len(seen['calls'])==5 and len(commands)==1
    assert result['failure'] is None and 'screening' not in result
    assert not Path(commands[0][-1]).exists()
    from verification.discovery.four_council_proof import validate_private_responses
    assert validate_private_responses(tmp_path/'raw-bodies',result)['state']=='FINISHED'

@pytest.mark.parametrize('closure',[{'cleanup':'UNKNOWN','exit_code':0,'limit_hit':None},{'cleanup':'CLOSED','exit_code':1,'limit_hit':None},{'cleanup':'CLOSED','exit_code':0,'limit_hit':'wall'}])
def test_supervisor_uncertainty_cannot_produce_assessment(tmp_path,closure):
    from verification.discovery import tameside_qualification as q
    with pytest.raises(q.Denied):q.qualify(tmp_path/'out',supervisor=lambda *a,**k:closure,authority=q.CALIBRATION_AUTHORITY,private_pages=True,pagination_calibration=True)
    assert not (tmp_path/'out/assessment.json').exists() and not (tmp_path/'out/calibration-summary.json').exists()
    assert json.loads((tmp_path/'out/qualification-outcome.json').read_bytes())['stage']=='SOURCE_SAFETY'

@pytest.mark.parametrize('failure',[False,True],ids=['observations','refusal'])
def test_full_owner_calibration_keeps_bodies_proof_and_never_assessment(tmp_path,monkeypatch,failure,capsys):
    from verification.discovery import tameside_qualification as q,finite_acceptance as finite
    from tests.test_tameside_page_evidence_03 import install_synthetic_session
    from verification.discovery.four_council_proof import manifest_scope,validate_private_responses,write_audit
    bodies=[FORM,SEARCH,body(nxt=True),body(2,count=4,previous=True),ECHO]
    if failure:bodies[2]=bodies[2].replace(b'</html>',b'<div class="error">Session expired PRIVATE_SENTINEL</div></html>')
    seen=install_synthetic_session(monkeypatch,bodies)
    def supervisor(command,**kw):
        assert kw['seconds']==45 and kw['source'] is True and kw['environment']=={'INGESTION_SOURCE_PRIVATE':'ONCE'}
        plan=json.loads(Path(command[command.index('--plan')+1]).read_bytes())
        assert plan['pagination_calibration']=='TAMESIDE_FIVE_PER_PAGE_V1'
        store=PrivateResponseBodies(plan['private_response_bodies'])
        from verification.discovery.idox_window import live
        with manifest_scope(q.ROW):result=live(C,retain_proof=True,response_evidence=store.record,pagination_calibration=True)
        store.finish()
        with manifest_scope(q.ROW):write_audit(Path(command[command.index('--output')+1]),result)
        return dict(cleanup='CLOSED',exit_code=0,limit_hit=None,expired=False,accounting_complete=True,live_owned_survivors=0,peak_owned_rss=1024,elapsed_seconds=.1)
    root=tmp_path/'out'
    if failure:
        with pytest.raises(q.Denied,match='CALIBRATION_SESSION_EXPIRED'):q.qualify(root,supervisor=supervisor,authority=q.CALIBRATION_AUTHORITY,private_pages=True,pagination_calibration=True)
    else:
        result=q.qualify(root,supervisor=supervisor,authority=q.CALIBRATION_AUTHORITY,private_pages=True,pagination_calibration=True)
        assert result['status']=='CALIBRATION_OBSERVATIONS_REQUIRE_REVIEW'
    source=json.loads((root/'source.json').read_bytes())
    assert not (root/'assessment.json').exists()
    summary=json.loads((root/'calibration-summary.json').read_bytes())
    assert summary['acceptance_enabled'] is False and summary['completeness']=='UNKNOWN' and summary['retry'] is False
    assert summary['status']==('CALIBRATION_STOP_REQUIRES_REVIEW' if failure else 'CALIBRATION_OBSERVATIONS_REQUIRE_REVIEW')
    outcome=json.loads((root/'qualification-outcome.json').read_bytes())
    assert outcome['stage']=='CALIBRATION' and outcome['status']==('REFUSED' if failure else 'OBSERVATIONS_RECORDED')
    with manifest_scope(q.ROW):index=validate_private_responses(root/'raw-bodies',source)
    assert len(index['entries'])==len(seen['calls'])==(3 if failure else 5)
    assert seen['closed'] and all(r.closed for r in seen['responses']) and seen['trust_env'] is False and seen['retry_total']==0
    assert all(c['timeout']==(3,8) and c['allow_redirects'] is False and 'verify' not in c for c in seen['calls'])
    assert not capsys.readouterr().out and 'PRIVATE_SENTINEL' not in json.dumps(source)
    for e,b in zip(index['entries'],bodies):
        assert (root/'raw-bodies'/e['name']).read_bytes()==b
        assert e['observed_sha256']==hashlib.sha256(b).hexdigest()


def test_page_post_does_not_expand_default_boundary():
    from verification.discovery.idox_window import WindowBoundary
    from verification.stage26b_l1.request_boundary import BoundaryFailure
    b=WindowBoundary(lambda *a,**k:pytest.fail('NO_DISPATCH'),C)
    b.phase='PAGE';b.admitted_post=C.base+'/pagedSearchResults.do';b.admitted_body=b'action=page'
    with pytest.raises(BoundaryFailure):b.retrieve('POST',b.admitted_post,b.admitted_body)
    assert b.requests==0

@pytest.mark.parametrize('mode',['ignored-size','changed-sort','missing-page','conflicting-current'])
def test_selected_state_must_be_consistent(mode):
    b=body()
    if mode=='ignored-size':b=b.replace(b'value="5" selected>5</option>',b'value="10" selected>10</option><option value="5">5</option>')
    if mode=='changed-sort':b=b.replace(b'value="Descending" selected',b'value="Ascending" selected').replace(b'</select><select name="searchCriteria.resultsPerPage">',b'<option value="Descending">Descending</option></select><select name="searchCriteria.resultsPerPage">')
    if mode=='missing-page':b=b.replace(b'<input type="hidden" name="searchCriteria.page" value="1">',b'')
    if mode=='conflicting-current':b=b.replace(b'<span class="current">1</span>',b'<span class="current">2</span>')
    with pytest.raises((CalibrationError,ValueError)):observe(b,C,1)


def test_actual_byte_exhaustion_retains_partial_and_closes(tmp_path):
    r,c,_,root=perform(tmp_path,[b'x'*500001])
    assert r['failure']=='CALIBRATION_BYTE_CAP' and len(c)==1
    e=json.loads((root/'raw-bodies/index.json').read_bytes())['entries'][0]
    assert e['complete'] is False


def test_recognised_transport_diagnostic_survives_into_proof(tmp_path):
    import requests
    r,c,_,_=perform(tmp_path,[requests.exceptions.ConnectTimeout('PRIVATE_SENTINEL')])
    assert len(c)==1 and r['resource']['retries']==0
    d=r['failure_diagnostic']['transport']
    assert d['failure']['exception_class']=='REQUESTS_CONNECT_TIMEOUT'
    assert r['retained_proof']['events'][-1]['transport']==d
    assert 'PRIVATE_SENTINEL' not in json.dumps(r)

@pytest.mark.parametrize('patch',[{'accounting_complete':False},{'accounting_complete':None},{'live_owned_survivors':1},{'peak_owned_rss':2**31},{'elapsed_seconds':60},{'expired':True},{'live_owned_survivors':True}])
def test_calibration_retains_existing_outer_safety_validation(tmp_path,patch):
    from verification.discovery import tameside_qualification as q
    outer=dict(cleanup='CLOSED',exit_code=0,limit_hit=None,expired=False,accounting_complete=True,live_owned_survivors=0,peak_owned_rss=1024,elapsed_seconds=.1)
    outer.update(patch)
    with pytest.raises(q.Denied,match='OUTER_SAFETY'):q.qualify(tmp_path/'out',supervisor=lambda *a,**k:outer,authority=q.CALIBRATION_AUTHORITY,private_pages=True,pagination_calibration=True)
    outcome=json.loads((tmp_path/'out/qualification-outcome.json').read_bytes())
    assert outcome['stage']=='SOURCE_SAFETY' and outcome['reason']=='OUTER_SAFETY'
    assert not (tmp_path/'out/calibration-summary.json').exists()

@pytest.mark.parametrize('mode',['correct','wrong-mode','wrong-path'])
def test_source_worker_exact_calibration_opt_in(tmp_path,monkeypatch,mode):
    from verification.ingestion_storage import daily_intake_runtime as runtime
    from verification.discovery import finite_acceptance as finite,tameside_qualification as q
    from types import SimpleNamespace
    import resource
    limits=[];calls=[]
    monkeypatch.setattr(resource,'setrlimit',lambda *a:limits.append(a))
    monkeypatch.setenv('INGESTION_SOURCE_PRIVATE','ONCE')
    monkeypatch.setattr(finite,'read',lambda *a,**k:(calls.append(k) or {'fixture':True}))
    plan=tmp_path/'plan.json';out=tmp_path/'source.json'
    plan.write_text(json.dumps(dict(row=q.ROW,fixture=None,private_response_bodies=str(tmp_path/('elsewhere' if mode=='wrong-path' else 'raw-bodies')),pagination_calibration='BAD' if mode=='wrong-mode' else 'TAMESIDE_FIVE_PER_PAGE_V1')))
    if mode=='correct':
        runtime.source_worker(SimpleNamespace(plan=str(plan),output=str(out)))
        assert len(calls)==1 and calls[0]['pagination_calibration'] is True
        assert calls[0]['no_transport_retry'] is True
        assert (resource.RLIMIT_FSIZE,(524288,524288)) in limits
    else:
        with pytest.raises(q.Denied):runtime.source_worker(SimpleNamespace(plan=str(plan),output=str(out)))
        assert not calls and not out.exists()
