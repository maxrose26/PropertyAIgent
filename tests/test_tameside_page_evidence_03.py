"""Synthetic HTML only; no source, DNS, DB, Render or public raw-body export."""
import hashlib,io,json,os,socket,sys,stat
from pathlib import Path
from datetime import date
import pytest,requests
from verification.discovery import four_council_proof as proof
from verification.discovery import tameside_qualification as q
from verification.discovery import finite_acceptance as finite
from verification.discovery.source_profiles import profile
from tests.test_discovery_idox_window import page,Response
from verification.bolton_recon.fixtures import FORM

TOKEN=b'PRIVATE_SYNTHETIC_SESSION_TOKEN'

@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    for k in list(os.environ):
        if 'DATABASE' in k or k.endswith(('_KEY','_TOKEN','_PASSWORD')):monkeypatch.delenv(k)
    def forbidden(*a,**kw):raise AssertionError('OFFLINE_NETWORK_FORBIDDEN')
    monkeypatch.setattr(socket,'getaddrinfo',forbidden);monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(requests.Session,'request',forbidden)
    import sqlite3,psycopg
    from sqlalchemy.engine import Engine
    monkeypatch.setattr(sqlite3,'connect',forbidden);monkeypatch.setattr(psycopg,'connect',forbidden);monkeypatch.setattr(Engine,'connect',forbidden)

def directory(tmp_path):
    p=tmp_path/'raw-bodies';p.mkdir(mode=0o700);return p

def index(root):return json.loads((root/'index.json').read_bytes())

def test_exact_private_bytes_sequence_hashes_and_modes(tmp_path,capsys):
    root=directory(tmp_path);store=proof.PrivateResponseBodies(root)
    bodies=[b'<html>'+TOKEN+b'</html>',b'\xff\x00original-response-bytes']
    for i,b in enumerate(bodies,1):store.record(['SEARCH','REFINE'][i-1],i,b)
    store.finish();v=proof.validate_private_responses(root)
    for e,b in zip(v['entries'],bodies):
        assert (root/e['name']).read_bytes()==b
        assert e['observed_bytes']==e['retained_bytes']==len(b)
        assert e['observed_sha256']==e['retained_sha256']==hashlib.sha256(b).hexdigest()
        assert e['complete'] is True and e['status']=='COMPLETE'
        assert (root/e['name']).stat().st_mode&0o777==0o600
    assert root.stat().st_mode&0o777==0o700
    assert TOKEN.decode() not in json.dumps(v) and not capsys.readouterr().out

@pytest.mark.parametrize('mode',['aggregate','single','truncated'])
def test_overflow_and_partial_never_claim_complete_original(tmp_path,mode):
    root=directory(tmp_path);store=proof.PrivateResponseBodies(root)
    if mode=='aggregate':
        for i in range(1,6):store.record('PAGE',i,b'x'*500000)
        expected='AGGREGATE_LIMIT'
    elif mode=='single':store.record('SEARCH',1,b'x'*500001);expected='BODY_LIMIT'
    else:store.record('SORT',1,b'partial-prefix',complete=False);expected='PARTIAL'
    store.finish();v=index(root)
    assert v['state']=='INCOMPLETE' and v['entries'][-1]['status']==expected
    assert v['entries'][-1]['complete'] is False
    assert sum(f.stat().st_size for f in root.glob('*.body'))<=2000000
    with pytest.raises(proof.ProofError):proof.validate_private_responses(root)


def test_short_write_is_partial_and_write_error_is_explicit(tmp_path,monkeypatch):
    root=directory(tmp_path);store=proof.PrivateResponseBodies(root);real=os.fdopen
    class Short:
        def __init__(self,f):self.f=f
        def __enter__(self):return self
        def __exit__(self,*args):self.f.close()
        def __getattr__(self,n):return getattr(self.f,n)
        def write(self,b):return self.f.write(b[:len(b)//2]) if b.startswith(b'TRUNCATE_BODY') else self.f.write(b)
    monkeypatch.setattr(os,'fdopen',lambda *a,**kw:Short(real(*a,**kw)))
    store.record('SEARCH',1,b'TRUNCATE_BODY_synthetic');store.finish()
    e=index(root)['entries'][0]
    assert e['status']=='PARTIAL' and not e['complete'] and e['retained_bytes']<e['observed_bytes']


def test_write_failure_has_no_secret_diagnostic_or_complete_body(tmp_path,monkeypatch,capsys):
    root=directory(tmp_path);store=proof.PrivateResponseBodies(root);real=os.open
    def fail(path,*args,**kw):
        if str(path).endswith('.body'):raise OSError(TOKEN.decode())
        return real(path,*args,**kw)
    monkeypatch.setattr(os,'open',fail)
    store.record('SEARCH',1,TOKEN);store.finish();v=index(root)
    assert v['entries'][0]['status']=='WRITE_FAILURE' and v['entries'][0]['complete'] is False
    assert TOKEN.decode() not in json.dumps(v) and not capsys.readouterr().out

@pytest.mark.parametrize('mode',['symlink','public-mode','preexisting'])
def test_unsafe_root_refuses_before_capture(tmp_path,mode):
    root=directory(tmp_path)
    if mode=='symlink':other=tmp_path/'other';other.mkdir();root.rmdir();root.symlink_to(other,target_is_directory=True)
    elif mode=='public-mode':root.chmod(0o755)
    else:(root/'old').write_bytes(TOKEN)
    with pytest.raises(proof.ProofError):proof.PrivateResponseBodies(root)


def test_unsafe_body_path_is_not_followed_or_overwritten(tmp_path):
    root=directory(tmp_path);store=proof.PrivateResponseBodies(root)
    other=tmp_path/'private-original';other.write_bytes(TOKEN)
    (root/'01-SEARCH.body').symlink_to(other)
    store.record('SEARCH',1,b'new');store.finish()
    assert other.read_bytes()==TOKEN and index(root)['entries'][0]['status']=='UNSAFE_PATH'


def test_manifest_interruption_stays_unacknowledged(tmp_path,monkeypatch):
    root=directory(tmp_path);store=proof.PrivateResponseBodies(root);real=os.replace
    def fail(*a,**kw):raise OSError(TOKEN.decode())
    monkeypatch.setattr(os,'replace',fail)
    store.record('SEARCH',1,TOKEN);store.finish()
    assert index(root)['state']=='OPEN'
    with pytest.raises(proof.ProofError):proof.validate_private_responses(root)


def synthetic_bodies():
    form=FORM.replace(b'fixture',TOKEN)
    results=page(pager=False).replace(b'Mon 28 Sep 2026',b'Tue 27 Oct 2026')
    echo=form.replace(b'name="date(applicationReceivedStart)" value=""',b'name="date(applicationReceivedStart)" value="24/10/2026"').replace(b'name="date(applicationReceivedEnd)" value=""',b'name="date(applicationReceivedEnd)" value="30/10/2026"')
    return [form,results,results,echo]


def install_synthetic_session(monkeypatch,bodies):
    seen=dict(calls=[],responses=[])
    class Session:
        verify=True
        def __enter__(self):return self
        def __exit__(self,*args):seen['closed']=True
        def mount(self,scheme,adapter):seen['retry_total']=adapter.max_retries.total
        def request(self,*args,**kw):
            seen['calls'].append(kw);seen['trust_env']=self.trust_env
            response=Response(bodies[len(seen['calls'])-1]);seen['responses'].append(response);return response
    monkeypatch.setattr(requests,'Session',Session)
    return seen


def run_private_worker(root,monkeypatch,raw_root=None):
    raw_root=root/'raw-bodies' if raw_root is None else raw_root
    p=profile(q.ROW,'SCREENING_METADATA')
    args=['finite','--idox-worker','tameside','2026-10-24','2026-10-30','--output',str(root/'source.json'),'--no-transport-retry','--retain-four-council-proof','--fixed-four-row-limit','--campaign-scope',json.dumps(q.ROW),'--collection-profile',json.dumps(p),'--private-response-bodies',str(raw_root)]
    monkeypatch.setattr(sys,'argv',args);finite.main()


def test_actual_worker_preserves_original_proof_and_private_results_after_completeness_refusal(tmp_path,monkeypatch,capsys):
    for k in list(os.environ):
        if 'DATABASE' in k or k.endswith(('_KEY','_TOKEN','_PASSWORD')):monkeypatch.delenv(k)
    bodies=synthetic_bodies();seen=install_synthetic_session(monkeypatch,bodies)
    def supervisor(command,**kw):
        assert kw['source'] is True and kw['seconds']==45 and kw['environment']=={'INGESTION_SOURCE_PRIVATE':'ONCE'}
        plan=json.loads(Path(command[command.index('--plan')+1]).read_bytes())
        assert plan['row']==q.ROW and plan['fixture'] is None
        root=Path(command[command.index('--output')+1]).parent
        run_private_worker(root,monkeypatch,Path(plan['private_response_bodies']))
        return dict(cleanup='CLOSED',exit_code=0,limit_hit=None,expired=False,accounting_complete=True,live_owned_survivors=0,peak_owned_rss=1024,elapsed_seconds=.1)
    root=tmp_path/'attempt03'
    with pytest.raises(q.Denied,match='IDOX_WINDOW_BINDING_OR_COMPLETENESS'):
        q.qualify(root,supervisor=supervisor,authority=q.THIRD_AUTHORITY,private_pages=True)
    source=json.loads((root/'source.json').read_bytes());v=proof.validate_private_responses(root/'raw-bodies',source)
    assert len(seen['calls'])==4 and seen['closed'] and all(x.closed for x in seen['responses'])
    assert seen['trust_env'] is False and seen['retry_total']==0
    assert all(c['timeout']==(3,8) and c['allow_redirects'] is False and 'verify' not in c for c in seen['calls'])
    assert [e['operation'] for e in v['entries']]==['FORM','SEARCH','SORT','REFINE']
    for e,b in zip(v['entries'],bodies):assert (root/'raw-bodies'/e['name']).read_bytes()==b
    assert source['enumeration_evidence']=='TOTAL_UNKNOWN' and source['resource']['retries']==0
    assert source['retained_proof']['complete_response_archive'] is False and 'raw_html' not in source
    outcome=json.loads((root/'qualification-outcome.json').read_bytes())
    assert outcome==dict(status='REFUSED',stage='PROJECTION',reason='IDOX_WINDOW_BINDING_OR_COMPLETENESS',retry=False)
    assert not (root/'assessment.json').exists()
    assert TOKEN.decode() not in json.dumps(source) and TOKEN.decode() not in json.dumps(outcome) and not capsys.readouterr().out


@pytest.mark.parametrize('reason,stage',[('IDOX_ROW_DATE','PROJECTION'),('PRIVATE_RESPONSE_RETENTION_INCOMPLETE','PRIVATE_RETENTION'),('QUALIFICATION_SOURCE_EXPORT','SOURCE_EXPORT')])
def test_distinct_allowlisted_outcomes_and_unknown_suppression(tmp_path,reason,stage):
    q.qualification_outcome(tmp_path,stage,q.Denied(reason))
    assert json.loads((tmp_path/'qualification-outcome.json').read_bytes())['reason']==reason
    q.qualification_outcome(tmp_path,'PROJECTION',RuntimeError(TOKEN.decode()))
    raw=(tmp_path/'qualification-outcome.json').read_bytes()
    assert json.loads(raw)['reason']=='UNKNOWN' and TOKEN not in raw and len(raw)<=2048


def test_third_authority_requires_both_consumed_predecessors_and_is_one_use(tmp_path,monkeypatch):
    for key in list(os.environ):
        if 'DATABASE' in key or key.endswith(('_KEY','_TOKEN','_PASSWORD')):monkeypatch.delenv(key)
    first=tmp_path/'first.json';second=tmp_path/'second.json';first.write_bytes(b'FIRST_CONSUMED');second.write_bytes(b'SECOND_CONSUMED')
    for name,value in dict(CONSUMPTION=first,SECOND_CONSUMPTION=second,PREDECESSOR_SHA256=hashlib.sha256(first.read_bytes()).hexdigest(),SECOND_CONSUMPTION_SHA256=hashlib.sha256(second.read_bytes()).hexdigest(),THIRD_OUTPUT=tmp_path/'output03',THIRD_CONSUMPTION=tmp_path/'consumed03.json').items():monkeypatch.setattr(q,name,value)
    calls=[]
    def qualify(root,**kw):
        assert q.THIRD_CONSUMPTION.is_file() and kw==dict(authority=q.THIRD_AUTHORITY,private_pages=True)
        calls.append(1);return dict(status='SYNTHETIC_ONLY',record_count=0,pages=0,source_sha256='1'*64)
    monkeypatch.setattr(q,'qualify',qualify)
    monkeypatch.setattr(sys,'argv',['q','--output',str(q.THIRD_OUTPUT),'--authority',q.THIRD_AUTHORITY])
    assert q.main()==0
    with pytest.raises(SystemExit,match='CONSUMED'):q.main()
    assert len(calls)==1 and first.read_bytes()==b'FIRST_CONSUMED' and second.read_bytes()==b'SECOND_CONSUMED'


def test_unknown_application_type_is_supported_uncertain_screening_input():
    # Synthetic metadata only. This does not screen any live ATTEMPT_02 record.
    from app.ingestion.listing_screening import ScreeningRule,RULE_V3
    fields={n:dict(state='UNKNOWN',value=None,locator='NOT_CAPTURED',truncated=False) for n in ('proposal','address','application_type','received_date','validated_date')}
    fields['proposal']=dict(state='PRESENT_VALUE',value='Erection of 12 dwellings',locator='synthetic listing',truncated=False)
    row=dict(reference='SYNTHETIC/26',source_record_id='SYNTHETIC',source_url='https://example.invalid/',fields=fields)
    result=ScreeningRule(RULE_V3,unit_threshold=10,link_related=False).screen(row)
    assert result['rule_version']==RULE_V3 and row['fields']['application_type']['state']=='UNKNOWN'

def test_stream_truncation_is_retained_as_partial_with_unchanged_timeout_cleanup(tmp_path):
    from verification.discovery.idox_window import WindowBoundary,WindowConfig
    from verification.stage26b_l1.request_boundary import BoundaryFailure
    root=directory(tmp_path);store=proof.PrivateResponseBodies(root)
    class Partial(Response):
        def iter_content(self,n):
            yield TOKEN
            raise requests.ReadTimeout('SYNTHETIC_PRIVATE_EXCEPTION')
    response=Partial(b'')
    c=WindowConfig('tameside','RECEIVED',date(2026,10,24),date(2026,10,30),0,60)
    b=WindowBoundary(lambda *a,**kw:response,c,response_evidence=store.record)
    with pytest.raises(BoundaryFailure):b.retrieve('GET',c.form_url)
    store.finish();e=index(root)['entries'][0]
    assert e['complete'] is False and e['status']=='PARTIAL' and e['retained_bytes']==len(TOKEN)
    assert b.requests==1 and b.retries==0 and response.closed


def test_actual_pagination_and_results_bearing_refine_are_retained_without_extra_requests(tmp_path,monkeypatch):
    root=tmp_path/'run';root.mkdir(mode=0o700);(root/'raw-bodies').mkdir(mode=0o700)
    bodies=synthetic_bodies()
    first=page(first=1,last=10,total=12,refs=tuple(f'{i}/26' for i in range(10)),next_page=2).replace(b'Mon 28 Sep 2026',b'Tue 27 Oct 2026')
    second=page(first=11,last=12,total=12,refs=('10/26','11/26')).replace(b'Mon 28 Sep 2026',b'Tue 27 Oct 2026').replace(b'keyVal=K0',b'keyVal=L0').replace(b'keyVal=K1',b'keyVal=L1')
    responses=[bodies[0],first,first,second,bodies[-1]]
    seen=install_synthetic_session(monkeypatch,responses);run_private_worker(root,monkeypatch)
    v=proof.validate_private_responses(root/'raw-bodies')
    assert [e['operation'] for e in v['entries']]==['FORM','SEARCH','SORT','PAGE','REFINE']
    assert len(seen['calls'])==5 and (root/'raw-bodies'/v['entries'][3]['name']).read_bytes()==second
    # An encountered REFINE body is retained without filtering by its layout.
    from verification.discovery.idox_window import WindowBoundary,WindowConfig
    another=tmp_path/'refine';another.mkdir(mode=0o700);store=proof.PrivateResponseBodies(another)
    response=Response(second);c=WindowConfig('tameside','RECEIVED',date(2026,10,24),date(2026,10,30),0,60)
    boundary=WindowBoundary(lambda *a,**kw:response,c,response_evidence=store.record);boundary.phase='REFINE'
    boundary.retrieve('GET',c.base+'/refineSearch.do?action=refine');store.finish()
    assert (another/'01-REFINE.body').read_bytes()==second and response.closed


def test_private_path_is_forwarded_through_existing_nested_reader_and_temp_export_is_cleaned(tmp_path,monkeypatch):
    raw_root=directory(tmp_path);seen=install_synthetic_session(monkeypatch,synthetic_bodies());commands=[]
    def supervise(command,*,env,deadline):
        assert deadline==50 and set(env)=={'PATH','HOME','TMPDIR','PYTHONDONTWRITEBYTECODE'}
        assert '--no-transport-retry' in command and '--private-response-bodies' in command
        assert command[command.index('--private-response-bodies')+1]==str(raw_root)
        commands.append(command)
        monkeypatch.setattr(sys,'argv',['finite',*command[3:]])
        finite.main();return 0,False
    monkeypatch.setattr(finite,'supervise',supervise)
    p=profile(q.ROW,'SCREENING_METADATA')
    result=finite.read(q.ROW,no_transport_retry=True,retain_proof=True,fixed_four_rows=True,campaign_scope=q.ROW,collection_profile=p,private_response_bodies=raw_root)
    assert len(commands)==1 and len(seen['calls'])==4
    assert not Path(commands[0][commands[0].index('--output')+1]).exists()
    assert proof.validate_private_responses(raw_root,result)['state']=='FINISHED'


def test_source_worker_binds_opt_in_to_exact_private_sibling_without_changing_fsize(monkeypatch,tmp_path):
    import resource
    from verification.ingestion_storage import daily_intake_runtime as runtime
    limits=[];calls=[]
    monkeypatch.setattr(resource,'setrlimit',lambda *a:limits.append(a))
    for k in list(os.environ):
        if 'DATABASE' in k or k.endswith(('_KEY','_TOKEN','_PASSWORD')):monkeypatch.delenv(k)
    monkeypatch.setenv('INGESTION_SOURCE_PRIVATE','ONCE')
    def read(row,**kwargs):calls.append(kwargs);return {'synthetic_only':True}
    monkeypatch.setattr(finite,'read',read)
    plan=tmp_path/'plan.json';out=tmp_path/'source.json'
    from types import SimpleNamespace
    plan.write_text(json.dumps(dict(row=q.ROW,fixture=None,private_response_bodies=str(tmp_path/'raw-bodies'))))
    runtime.source_worker(SimpleNamespace(plan=str(plan),output=str(out)))
    assert calls[0]['private_response_bodies']==str(tmp_path/'raw-bodies')
    assert (resource.RLIMIT_FSIZE,(524288,524288)) in limits
    plan.write_text(json.dumps(dict(row=q.ROW,fixture=None,private_response_bodies=str(tmp_path/'elsewhere'))))
    with pytest.raises(q.Denied,match='PRIVATE_RESPONSE_SCOPE'):runtime.source_worker(SimpleNamespace(plan=str(plan),output=str(tmp_path/'other.json')))
    assert len(calls)==1


def test_manifest_rebind_or_public_body_permission_refuses(tmp_path):
    root=directory(tmp_path);store=proof.PrivateResponseBodies(root);store.record('SEARCH',1,b'original');store.finish()
    body=root/'01-SEARCH.body';body.chmod(0o644)
    with pytest.raises(proof.ProofError,match='UNSAFE_PATH'):proof.validate_private_responses(root)
    body.chmod(0o600)
    v=index(root);v['entries'][0]['name']='../outside'
    (root/'index.json').write_text(json.dumps(v))
    with pytest.raises(proof.ProofError,match='INCOMPLETE'):proof.validate_private_responses(root)

@pytest.mark.parametrize('patch',[{'observed_bytes':True},{'retained_sha256':'bad'},{'operation':'HEADERS'},{'extra':'PRIVATE_TOKEN'}])
def test_private_index_schema_refuses_unsafe_or_boolean_bindings(tmp_path,patch):
    root=directory(tmp_path);store=proof.PrivateResponseBodies(root);store.record('SEARCH',1,b'x');store.finish()
    value=index(root);value['entries'][0].update(patch);(root/'index.json').write_text(json.dumps(value))
    with pytest.raises(proof.ProofError):proof.validate_private_responses(root)


def test_body_retention_keeps_default_source_receipt_and_request_meaning(tmp_path,monkeypatch):
    from verification.discovery.idox_window import live,WindowConfig
    from verification.discovery.four_council_proof import manifest_scope
    c=WindowConfig('tameside','RECEIVED',date(2026,10,24),date(2026,10,30),0,60)
    old_seen=install_synthetic_session(monkeypatch,synthetic_bodies())
    with manifest_scope(q.ROW):old=live(c,retain_proof=True)
    root=directory(tmp_path);store=proof.PrivateResponseBodies(root)
    new_seen=install_synthetic_session(monkeypatch,synthetic_bodies())
    with manifest_scope(q.ROW):new=live(c,retain_proof=True,response_evidence=store.record)
    store.finish()
    for key in ['pages','records','enumeration_evidence','sort','applied_interval','failure','completeness','cleanup','response_provenance']:
        assert old[key]==new[key]
    assert len(old_seen['calls'])==len(new_seen['calls'])==4
    assert old['resource']['requests_attempted']==new['resource']['requests_attempted']==4
    assert old['resource']['retries']==new['resource']['retries']==0
    assert old['retained_proof']['complete_response_archive'] is new['retained_proof']['complete_response_archive'] is False

@pytest.mark.parametrize('mismatch',['first','second','output','authority'])
def test_third_attempt_binding_mismatch_refuses_before_source(tmp_path,monkeypatch,mismatch):
    first=tmp_path/'one';second=tmp_path/'two';first.write_bytes(b'one');second.write_bytes(b'two')
    changes=dict(CONSUMPTION=first,SECOND_CONSUMPTION=second,PREDECESSOR_SHA256=hashlib.sha256(b'one').hexdigest(),SECOND_CONSUMPTION_SHA256=hashlib.sha256(b'two').hexdigest(),THIRD_OUTPUT=tmp_path/'out',THIRD_CONSUMPTION=tmp_path/'consumed')
    for n,v in changes.items():monkeypatch.setattr(q,n,v)
    if mismatch in ('first','second'):(first if mismatch=='first' else second).write_bytes(b'changed')
    monkeypatch.setattr(q,'qualify',lambda *a,**kw:pytest.fail('source forbidden'))
    monkeypatch.setattr(sys,'argv',['q','--output',str(tmp_path/'wrong' if mismatch=='output' else q.THIRD_OUTPUT),'--authority','WRONG' if mismatch=='authority' else q.THIRD_AUTHORITY])
    with pytest.raises(SystemExit):q.main()
    assert not q.THIRD_CONSUMPTION.exists()


def test_third_launcher_binds_fixed_paths_and_preserves_existing_envelope():
    tools=Path(__file__).resolve().parents[1]/'docs/design/tameside-page-evidence-03-20261101'
    text=(tools/'RUN-QUALIFICATION-INACTIVE.sh').read_text()
    assert str(q.THIRD_OUTPUT) in text and str(q.THIRD_CONSUMPTION) in text
    assert q.THIRD_AUTHORITY in text and 'EXECUTE_ONE_TAMESIDE_LISTING_QUALIFICATION_ATTEMPT_03' in text
    assert '/usr/bin/env -i' in text and '--signal=INT --kill-after=2s 58s' in text
    assert 'verification.discovery.tameside_qualification' in text
