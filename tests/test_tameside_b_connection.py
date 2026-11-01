"""Synthetic source-worker/reader/adapter connection; no source or DB contact."""
from pathlib import Path
from datetime import date
from dataclasses import asdict
from types import SimpleNamespace
import copy,json,os,sys,hashlib
import pytest
from verification.discovery import source_profiles as profiles,finite_acceptance as finite
from verification.discovery.four_council_proof import manifest_scope,validate_audit
from verification.discovery.pagination_calibration import COUNTED_MODE,COUNTED_CONTRACT,run_counted_window
from verification.discovery.idox_window import WindowConfig
from verification.ingestion_storage import daily_intake_runtime as runtime
from app.ingestion.idox_adapter import IdoxListingContract
from app.ingestion.ledger import DEFAULT_LIMITS,Denied
from tests.test_tameside_page_identity import page
from tests.test_tameside_pagination_calibration import C,FORM,SEARCH,ECHO,Response,offline
ROW=dict(council='tameside',semantics='RECEIVED',start='2026-10-24',end='2026-10-30')
QUAL=hashlib.sha256((Path(__file__).resolve().parents[1]/'docs/design/tameside-b-connection-20261101/tameside-qualification.json').read_bytes()).hexdigest()

def connected_source(tmp_path,monkeypatch,row=None,failure=None):
    row=row or ROW;calls=[];responses=[];commands=[];limits=[];a,b=date.fromisoformat(row['start']),date.fromisoformat(row['end']);when=(a+(b-a)//2).strftime('%a %d %b %Y').encode()
    bodies=[FORM,SEARCH,page(1),page(2),ECHO]
    bodies=[v.replace(b'Tue 27 Oct 2026',when).replace(b'24/10/2026',a.strftime('%d/%m/%Y').encode()).replace(b'30/10/2026',b.strftime('%d/%m/%Y').encode()) for v in bodies]
    if failure=='criteria':bodies[-1]=FORM
    if failure=='repeated':bodies[3]=bodies[2]
    if failure=='wrong-page':bodies[3]=bodies[3].replace(b'<strong>2</strong>',b'<strong>1</strong>')
    if failure=='total':bodies[3]=bodies[3].replace('6–9 of 9'.encode(),'6–9 of 10'.encode())
    if failure=='duplicate':bodies[3]=bodies[3].replace(b'keyVal=P2K0',b'keyVal=P1K0')
    if failure=='terminal':bodies[3]=bodies[3].replace('6–9 of 9'.encode(),'6–9 of 10'.encode())
    if failure=='navigation':bodies[2]=bodies[2].replace(b'searchCriteria.page=2',b'searchCriteria.page=3')
    class Session:
        verify=True
        def __enter__(self):return self
        def __exit__(self,*args):self.closed=True
        def mount(self,scheme,adapter):assert adapter.max_retries.total==0
        def request(self,method,url,**kw):
            assert self.trust_env is False and self.verify is True and kw['timeout']==(3,8) and kw['allow_redirects'] is False
            calls.append((method,url));response=Response(bodies[len(calls)-1]);response.status_code=503 if failure=='503' else 200;responses.append(response);return response
    def supervise(command,*,env,deadline):
        assert deadline==50 and set(env)=={'PATH','HOME','TMPDIR','PYTHONDONTWRITEBYTECODE'}
        assert '--tameside-pagination-calibration' not in command and '--private-response-bodies' not in command
        assert '--no-transport-retry' in command and '--retain-four-council-proof' in command
        commands.append(command)
        with monkeypatch.context() as m:
            m.setattr(sys,'argv',['finite',*command[3:]]);finite.main()
        return 0,False
    import resource,requests
    with monkeypatch.context() as m:
        for k in list(os.environ):m.delenv(k)
        m.setenv('INGESTION_SOURCE_PRIVATE','ONCE');m.setenv('PATH','/usr/bin:/bin');m.setenv('HOME',str(tmp_path));m.setenv('PYTHONDONTWRITEBYTECODE','1')
        from verification.discovery import idox_window
        m.setattr(idox_window.time,'sleep',lambda _:None)  # mocked transport pacing only; production delay unchanged
        m.setattr(requests,'Session',Session);m.setattr(finite,'supervise',supervise);m.setattr(resource,'setrlimit',lambda *args:limits.append(args))
        plan=tmp_path/'plan.json';out=tmp_path/'source.json';plan.write_text(json.dumps(dict(row=row,fixture=None)))
        runtime.source_worker(SimpleNamespace(plan=str(plan),output=str(out)))
    source=json.loads(out.read_bytes());assert all(v.closed for v in responses)
    assert (resource.RLIMIT_FSIZE,(524288,524288)) in limits and (resource.RLIMIT_CPU,(45,45)) in limits
    assert len(commands)==1 and not Path(commands[0][-1]).exists()
    return source,calls


def outer():return dict(exit_code=0,cleanup='CLOSED',accounting_complete=True,expired=False,limit_hit=None,live_owned_survivors=0,peak_owned_rss=1024,elapsed_seconds=.1)
def contract(row=None):
    r=row or ROW;return IdoxListingContract(COUNTED_CONTRACT,WindowConfig('tameside','RECEIVED',date.fromisoformat(r['start']),date.fromisoformat(r['end']),0,60),QUAL)

def test_actual_source_worker_reader_proof_adapter_nine_records(tmp_path,monkeypatch):
    source,calls=connected_source(tmp_path,monkeypatch);p=profiles.profile(ROW,'SCREENING_METADATA',idox_pagination=COUNTED_MODE)
    assert source['collection_profile']==p and p['idox_pagination']==COUNTED_MODE and p['page_size']==5
    with manifest_scope(ROW,p):validate_audit(source,tuple(ROW[k] for k in ['council','semantics','start','end']))
    assert len(calls)==5 and source['enumeration_evidence']=='COUNT_RECONCILED' and 'calibration' not in source
    receipt=contract().project(source,outer(),DEFAULT_LIMITS,source_bytes_limit=524288)
    assert len(receipt['records'])==9 and len(receipt['segments'])==2 and receipt['segments'][-1]['terminal']=='EXPLICIT_LAST_EQUALS_TOTAL'
    assert receipt['pagination_mode']==COUNTED_MODE and all(r['fields']['application_type']['state']=='UNKNOWN' and r['fields']['application_type']['value'] is None for r in receipt['records'])
    assert all(r['provenance']['parser']=='verification.discovery.pagination_calibration.observe' for r in receipt['records'])
    assert source['completeness']=='UNKNOWN'  # adapter, not transport, proves window

@pytest.mark.parametrize('failure',['criteria','wrong-page','total','duplicate','terminal','navigation','repeated'])
def test_connected_contradictions_refuse(tmp_path,monkeypatch,failure):
    source,calls=connected_source(tmp_path,monkeypatch,failure=failure)
    assert source['failure'] is not None and source['resource']['retries']==0 and source['cleanup']=='SESSION_BOUNDARY_CLOSED'
    with pytest.raises(Denied):contract().project(source,outer(),DEFAULT_LIMITS,source_bytes_limit=524288)
    assert len(calls)<=5

@pytest.mark.parametrize('patch',[{'pagination_mode':None},{'collection_profile':{}},{'pages':[]},{'pagination_evidence':{}},{'applied_interval':None},{'criteria_result_binding':{}}])
def test_adapter_refuses_missing_profile_or_binding(tmp_path,monkeypatch,patch):
    source,_=connected_source(tmp_path,monkeypatch);source.update(patch)
    with pytest.raises((Denied,KeyError)):contract().project(source,outer(),DEFAULT_LIMITS,source_bytes_limit=524288)

def test_legacy_receipt_and_other_profile_compatibility():
    from tests.e2e_connection_support import idox_audit,idox_contract,entry,SCHEME
    audit=idox_audit('tameside',[entry('HIST/26',SCHEME)],C.start,C.end)
    receipt=idox_contract('tameside',C.start,C.end).project(audit,outer(),DEFAULT_LIMITS)
    assert 'pagination_mode' not in receipt and receipt['records'][0]['provenance']['parser']=='app.scrapers.discovery_idox.parse_page'
    for council,sem in [('bolton','RECEIVED'),('manchester','VALIDATED'),('oldham','RECEIVED')]:
        r=dict(ROW,council=council,semantics=sem);assert 'idox_pagination' not in profiles.profile(r,'SCREENING_METADATA')
    assert 'idox_pagination' not in profiles.profile(ROW,'IDENTITY_ONLY')
    assert 'idox_pagination' not in profiles.profile(ROW,'SCREENING_METADATA')

def test_runtime_rejects_unbound_contract_before_source():
    obj=object.__new__(runtime.Runtime);obj.test=False;obj.policy={'councils':{'tameside':dict(contract='old',qualification_sha256=QUAL)}}
    with pytest.raises(Denied,match='TAMESIDE_REVIEWED_CONTRACT_BINDING'):obj.contract(ROW)
    obj.policy['councils']['tameside']=dict(contract=COUNTED_CONTRACT,qualification_sha256=QUAL)
    assert obj.contract(ROW).name==COUNTED_CONTRACT

def test_bound_inventory_includes_actual_shared_sources():
    for name in ['verification/discovery/pagination_calibration.py','verification/discovery/idox_sort.py','verification/discovery/four_council_proof.py','verification/stage26b_l1/request_boundary.py','app/ingestion/listing_screening.py','docs/design/tameside-b-connection-20261101/tameside-qualification.json']:assert name in runtime.BOUND_FILES

@pytest.mark.parametrize('row,mode',[({**ROW,'council':'oldham'},'SCREENING_METADATA'),(ROW,'IDENTITY_ONLY'),({**ROW,'end':'2026-10-29'},'SCREENING_METADATA')])
def test_five_mode_cannot_expand_profile(row,mode):
    with pytest.raises(ValueError,match='IDOX_PAGINATION_PROFILE'):profiles.profile(row,mode,idox_pagination=COUNTED_MODE)


def test_generic_profile_generation_is_byte_compatible_with_base():
    import subprocess
    from verification.discovery.finite_acceptance import manifest
    # Execute only the old pure profile definitions in a separate module namespace.
    base=subprocess.check_output(['git','show','83a0cc23d30ef80bf0e307aaa09742cf15800d3c:verification/discovery/source_profiles.py'],text=True)
    namespace={'__name__':'verification.discovery.historical_profile','__package__':'verification.discovery'};exec(compile(base,'historical_profile','exec'),namespace)
    for row in manifest('2026-10-24','2026-10-30','PROSPECTIVE')['rows']:
        for mode in ('IDENTITY_ONLY','SCREENING_METADATA'):assert profiles.profile(row,mode)==namespace['profile'](row,mode)

@pytest.mark.parametrize('reason,code',[('run deadline','CALIBRATION_DEADLINE'),('request ceiling','CALIBRATION_REQUEST_CAP'),('response byte ceiling','CALIBRATION_BYTE_CAP')])
def test_counted_runtime_budget_refusals(reason,code):
    from verification.stage26b_l1.request_boundary import BoundaryFailure
    p=profiles.profile(ROW,'SCREENING_METADATA',idox_pagination=COUNTED_MODE);calls=[]
    def dispatch(*args,**kwargs):calls.append(1);raise BoundaryFailure('PARTIAL_RETRIEVAL',reason)
    with manifest_scope(ROW,p):source=run_counted_window(dispatch,C)
    assert source['failure']==code and len(calls)==1 and source['resource']['retries']==0 and source['cleanup']=='BOUNDARY_CLOSED'

def test_counted_runtime_body_ceiling_is_not_raised():
    p=profiles.profile(ROW,'SCREENING_METADATA',idox_pagination=COUNTED_MODE);responses=[]
    def dispatch(*args,**kwargs):r=Response(b'x'*500001);responses.append(r);return r
    with manifest_scope(ROW,p):source=run_counted_window(dispatch,C)
    assert source['failure']=='CALIBRATION_BYTE_CAP' and len(responses)==1 and responses[0].closed

@pytest.mark.parametrize('patch',[{'cleanup':'UNCERTAIN'},{'live_owned_survivors':1},{'limit_hit':'DEADLINE'},{'expired':True}])
def test_counted_projection_refuses_unclosed_outer(tmp_path,monkeypatch,patch):
    source,_=connected_source(tmp_path,monkeypatch);o=outer();o.update(patch)
    with pytest.raises(Denied,match='OUTER_SAFETY'):contract().project(source,o,DEFAULT_LIMITS,source_bytes_limit=524288)


def test_new_contract_cannot_accept_legacy_unbound_mode():
    from tests.e2e_connection_support import idox_audit,entry,SCHEME
    source=idox_audit('tameside',[entry('LEGACY/26',SCHEME)],C.start,C.end)
    with pytest.raises(Denied,match='IDOX_PAGINATION_PROFILE_BINDING'):contract().project(source,outer(),DEFAULT_LIMITS)
