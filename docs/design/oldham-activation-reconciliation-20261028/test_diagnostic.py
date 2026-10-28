"""Focused offline tests. All server, process and memory readbacks below are SYNTHETIC.
No credentials, production connection, native cgroup proof or source contact.
"""
import importlib.util,json,time,hashlib,datetime
from pathlib import Path
import pytest
ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('fixed_reconciliation_test',ROOT/'diagnostic.py')
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d);d.configure()
from verification.ingestion_storage import admin_connection_probe as base
from verification.ingestion_storage.operational_preparation import Progress
from verification.ingestion_storage.operational_outcome import finalise


class Cursor:
    description=True
    def __init__(self,rows,extra=0):self.rows=rows;self.extra=extra;self.pgresult=self
    def fetchall(self):return self.rows
    @property
    def ntuples(self):return 1 if self.extra else 0
    nfields=1
    def get_value(self,r,k):return b'x'*self.extra

class Connection:
    def __init__(self,answers,fault=None,close_failure=False,extra=0):self.answers=answers;self.fault=fault;self.close_failure=close_failure;self.extra=extra;self.closed=False;self.sent=[]
    def execute(self,q,params=None):
        name=next(k for k,v in d.Q.items() if v==q);self.sent.append(name)
        if name==self.fault:raise RuntimeError('SYNTHETIC_PRIVATE_EXCEPTION_MUST_NOT_ESCAPE')
        return Cursor(self.answers.get(name,[]),self.extra)
    def close(self):
        if self.close_failure:raise RuntimeError('SYNTHETIC_CLOSE_FAILURE')
        self.closed=True

class Memory:
    def snapshot(self):return {}
    def close(self):return {'owned_groups_removed':True,'owned_survivors':0,'proof':'SYNTHETIC_NOT_KERNEL'}

@pytest.fixture
def world(tmp_path,monkeypatch):
    monkeypatch.setattr(d,'originals',lambda:[dict(file='final-result.json',exists=True,sha256='0'*64,mode=420)])
    monkeypatch.setattr(base,'early_closure',lambda baseline,proof,progress:dict(process=dict(status='CLOSED',live_child_count=0,new_socket_count=0,memory={'proof':'SYNTHETIC_NOT_KERNEL'})))
    funcs=[(n,h,'ingestion_storage_owner',['search_path=pg_catalog'],True,d.old.OLDHAM_HELPER_ARGUMENTS if n=='ingestion_oldham_allowed' else '',True,n=='ingestion_worker_step','sql' if n=='ingestion_acceptance_control' else 'plpgsql','s') for n,h in d.old.expected_states()['oldham'].items()]
    roles=[(n,False,False,None,1,False,False,False,False,False) for n in d.old.LOGINS[:2]]
    codes=json.loads((ROOT/'gate-mapping.json').read_bytes())['codes']
    predicates=[dict(ordinal=i,login=role,code=code,inputs_present=True,failing=False) for i,code in enumerate(codes) for role in (d.old.LOGINS[:2] if i<7 else ['GLOBAL'])]
    ident=['postgres','postgres',False,True,True,True,False,False,False,False,True,False,True,True,True,True,True,datetime.datetime(2020,1,1,tzinfo=datetime.timezone.utc),dict(control_columns=True,barrier_columns=True,rls_unfiltered=True)]
    answers={'begin':[],'identity':[ident],'roles':roles,'roles_without_password':roles,'memberships':[],'sessions':[],'functions':funcs,'gate_predicates':[(predicates,)],'gate_offenders':[([],)],'control':[({'global_stop':{'reason':'CONSUMED_SALFORD_GLOBAL_STOP','run':'38884069913'},'manual_stop':'IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE','hard_stop_generation':3,'unexpired_grants':1},)],'ledger':[({'authority':'INGESTION_CHAIN_OLDHAM_STAGED_CAPTURE_E9D12874CFB5','stored_grant_expiry':0,'grant_expired_at_snapshot':True,'revoked':False},)],'barriers':[(0,0)],'rollback':[]}
    def make(fault=None,close_failure=False,extra=0):
        c=Connection(answers,fault,close_failure,extra);j=d.BoundedJournal(tmp_path/('state'+str(len(list(tmp_path.iterdir())))));r=d.Reconciliation(j,lambda:c,Progress(),Memory(),baseline={},started=time.monotonic());return r,c,j
    return answers,make

@pytest.mark.parametrize('code',json.loads((ROOT/'gate-mapping.json').read_bytes())['codes'])
def test_all_fixed_codes_and_multiple_failures_retained(world,code):
    answers,make=world
    for row in answers['gate_predicates'][0][0]:row['failing']=row['code']==code
    r,c,j=make();result=r.execute()
    assert result['status']=='OLDHAM_READONLY_INSPECTION_COMPLETE'
    assert len(result['inspection']['gate_predicates'])==17
    assert any(x['failing'] and x['code']==code for x in result['inspection']['gate_predicates'])
    assert c.sent==d.PRIMARY and len(c.sent)==12 and c.closed and r.rollbacks==1
    assert result['closure_scope'].endswith('NOT_PRIOR_RUN_ACCESS')
    assert result['authority_invalidation'].startswith('NOT_PERFORMED')

@pytest.mark.parametrize('control,barrier,unfiltered',[(False,False,True),(True,True,False),(True,False,True)])
def test_inaccessible_authority_and_barriers_are_unknown(world,control,barrier,unfiltered):
    answers,make=world;answers['identity'][0][18]=dict(control_columns=control,barrier_columns=barrier,rls_unfiltered=unfiltered)
    r,c,j=make();res=r.execute()['inspection']
    assert ('ledger' in c.sent)==(control and unfiltered)
    assert ('barriers' in c.sent)==(barrier and unfiltered)
    if not(control and unfiltered):assert res['stored_authority']['status'].startswith('UNKNOWN')
    if not(barrier and unfiltered):assert res['uncertainty_barriers']['status'].startswith('UNKNOWN')
    assert len(res['gate_predicates'])==17

def test_expired_is_not_revoked(world):
    _,make=world;r,c,j=make();v=r.execute()['inspection']['stored_authority'];assert v['grant_expired_at_snapshot'] is True and v['revoked'] is False

@pytest.mark.parametrize('fault',['identity','roles','memberships','functions','gate_predicates','gate_offenders','ledger','barriers'])
def test_failure_rolls_back_closes_and_redacts(world,fault):
    _,make=world;r,c,j=make(fault);v=r.execute()
    assert v['status']=='STOP_RECONCILE_NO_RETRY' and c.closed and 'rollback' in c.sent
    assert 'SYNTHETIC_PRIVATE_EXCEPTION' not in json.dumps(v)
    assert r.statements<=12 and v['cleanup']=='CLOSED' # diagnostic closure only; never prior activation closure

def test_connection_close_uncertainty_remains_uncertain(world):
    _,make=world;r,c,j=make(close_failure=True);v=r.execute();assert v['cleanup']=='UNCERTAIN' and r.closed==0

def test_process_uncertainty_remains_uncertain(world,monkeypatch):
    monkeypatch.setattr(base,'early_closure',lambda *a:dict(process=dict(status='UNCERTAIN')))
    _,make=world;r,c,j=make();assert r.execute()['cleanup']=='UNCERTAIN'

def test_statement_bound_refuses_before_extra_execute(world):
    _,make=world;r,c,j=make();r.statements=12
    with pytest.raises(d.ProbeDenied,match='STATEMENT_BOUND'):r.send(c,'roles',d.Q['roles'])
    assert not c.sent

def test_unlisted_sql_refuses_without_execution(world):
    _,make=world;r,c,j=make()
    with pytest.raises(d.ProbeDenied,match='STATEMENT_UNEXPECTED'):r.send(c,'bad','SELECT 1')
    assert not c.sent

def test_returned_values_bound(world):
    _,make=world;r,c,j=make(extra=32769)
    with pytest.raises(d.ProbeDenied,match='RESPONSE_BOUND'):r.send(c,'roles',d.Q['roles'])
    assert r.returned_bytes==32769

@pytest.mark.parametrize('elapsed',[30.001,45.001])
def test_time_bound_refuses_new_statement(world,monkeypatch,elapsed):
    _,make=world;r,c,j=make();r.database_seconds=elapsed
    with pytest.raises(d.ProbeDenied,match='ACTIVE_WINDOW_EXHAUSTED'):r.send(c,'roles',d.Q['roles'])
    assert not c.sent

def test_active_clock_and_cancellation(world):
    _,make=world;r,c,j=make();r.started-=46
    with pytest.raises(d.ProbeDenied,match='ACTIVE_WINDOW_EXHAUSTED'):r.send(c,'roles',d.Q['roles'])
    r.started=time.monotonic();r.stop_file.touch()
    with pytest.raises(d.ProbeDenied,match='OWNER_STOP'):r.send(c,'roles',d.Q['roles'])
    assert not c.sent

def test_persisted_bounds_and_no_overwrite_on_refusal(tmp_path):
    j=d.BoundedJournal(tmp_path/'journal');j.save('final-result.json',{'original':'SYNTHETIC'})
    raw=(j.root/'final-result.json').read_bytes()
    with pytest.raises(d.ProbeDenied,match='RESPONSE_BOUND'):j.save('final-result.json',{'too_large':'x'*32769})
    assert (j.root/'final-result.json').read_bytes()==raw
    with pytest.raises(d.ProbeDenied,match='RESPONSE_BOUND'):j.emit('oversize',{'x':'y'*32769})

def test_exact_terminal_bound(monkeypatch):
    def session(*a,output=None,**kw):return output('x'*a[0],flush=True)
    monkeypatch.setattr(d,'BASE_SESSION',session);got=[]
    d.bounded_session(32767,output=lambda s,**kw:got.append(s));assert len(got[0])==32767
    with pytest.raises(d.ProbeDenied,match='RESPONSE_BOUND'):d.bounded_session(32768,output=lambda s,**kw:got.append(s))
    assert len(got)==1

def test_historical_mode_and_hash_unchanged(tmp_path,monkeypatch):
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    root=tmp_path/'.local/state/propertyaigent/oldham-owner-capture-screening-once-20261028';root.mkdir(parents=True)
    f=root/'final-result.json';f.write_bytes(b'SYNTHETIC_HISTORICAL_BYTES');f.chmod(0o644)
    first=d.originals();assert first[0]['mode']==0o644 and first[0]['mode_is_private'] is False
    assert f.read_bytes()==b'SYNTHETIC_HISTORICAL_BYTES' and d.originals()==first and f.stat().st_mode&0o777==0o644

def test_inactive_registration_refuses():
    b=(ROOT/'registration.INACTIVE.json').read_bytes()
    with pytest.raises(ValueError,match='EXACT_ATTENDED_READONLY_APPROVAL_REQUIRED'):d.validate(b,d.sha(b))

def test_fresh_namespace_does_not_reuse_original(tmp_path):
    j=d.BoundedJournal(tmp_path/d.STATE)
    with pytest.raises(FileExistsError):d.BoundedJournal(tmp_path/d.STATE)
    assert d.STATE!='oldham-owner-capture-screening-once-20261028'


def test_exact_persisted_file_and_combined_bounds(tmp_path):
    j=d.BoundedJournal(tmp_path/'exact')
    value={'x':'x'*(32768-len(d.canonical({'x':''})))}
    assert len(d.canonical(value))==32768
    j.save('progress.json',value);j.save('final-result.json',value)
    assert sum(p.stat().st_size for p in j.root.iterdir())==65536
    before=(j.root/'final-result.json').read_bytes()
    with pytest.raises(d.ProbeDenied,match='RESPONSE_BOUND'):j.save('final-result.json',{'x':'y'})
    assert (j.root/'final-result.json').read_bytes()==before


def test_exact_returned_value_bound(world):
    _,make=world;r,c,j=make(extra=32768);r.send(c,'roles',d.Q['roles']);assert r.returned_bytes==32768


def test_exact_statement_bound(world):
    _,make=world;r,c,j=make()
    for _ in range(12):r.send(c,'roles',d.Q['roles'])
    with pytest.raises(d.ProbeDenied,match='STATEMENT_BOUND'):r.send(c,'roles',d.Q['roles'])
    assert len(c.sent)==12


def test_database_time_exact_boundary(world):
    _,make=world;r,c,j=make();r.database_seconds=30
    with pytest.raises(d.ProbeDenied,match='ACTIVE_WINDOW_EXHAUSTED'):r.send(c,'roles',d.Q['roles'])
    assert not c.sent


def test_missing_predicate_inputs_stay_unknown(world):
    answers,make=world;answers['gate_predicates'][0][0][0].update(inputs_present=False,failing=None)
    r,c,j=make();p=r.execute()['inspection']['gate_predicates'];assert len(p)==17 and p[0]['failing'] is None


def test_changed_control_function_is_not_called(world):
    answers,make=world;rows=answers['functions'];i=next(i for i,r in enumerate(rows) if r[0]=='ingestion_acceptance_control');row=list(rows[i]);row[1]='f'*64;rows[i]=tuple(row)
    r,c,j=make();v=r.execute()['inspection'];assert 'control' not in c.sent and v['control']['status']=='UNKNOWN_FUNCTION_NOT_VERIFIED'
    assert len(v['gate_predicates'])==17


def test_cancellation_before_connection(world):
    _,make=world;r,c,j=make();r.stop_file.touch();v=r.execute();assert r.attempts==0 and not c.sent and v['status']=='STOP_RECONCILE_NO_RETRY'


def test_watchdog_is_30_seconds_and_closed(world,monkeypatch):
    from verification.ingestion_storage import operational_cleanup
    events=[]
    class Watch:
        def __init__(self,end):events.append(('start',end-time.monotonic()))
        def close(self):events.append(('closed',True))
    monkeypatch.setattr(operational_cleanup,'HardDeadline',Watch)
    _,make=world;r,c,j=make();r.execute();assert events[0][0]=='start' and 29.9<events[0][1]<=30 and events[-1]==('closed',True)


def test_existing_watchdog_real_child_timeout_and_release(tmp_path):
    import subprocess,sys,os
    env={'PATH':'/usr/bin:/bin','PYTHONPATH':os.environ['PYTHONPATH'],'PYTHONDONTWRITEBYTECODE':'1','DATABASE_URL':'sqlite:///:memory:'}
    prefix='from verification.ingestion_storage.operational_cleanup import HardDeadline;import time;'
    expired=subprocess.run([sys.executable,'-c',prefix+'w=HardDeadline(time.monotonic()+0.05);time.sleep(2)'],env=env,capture_output=True,timeout=5)
    assert expired.returncode==124
    closed=subprocess.run([sys.executable,'-c',prefix+'w=HardDeadline(time.monotonic()+0.05);w.close();time.sleep(0.1)'],env=env,capture_output=True,timeout=5)
    assert closed.returncode==0

@pytest.mark.parametrize('exists,login',[(False,None),(True,False),(True,True)])
def test_recovery_dormancy_condition_has_its_own_observation(world,exists,login):
    answers,make=world
    if exists:answers['roles'].append(('ingestion_recovery_login',login,False,None,1,False,False,False,False,False))
    r,c,j=make();v=r.execute()['inspection']['recovery_dormancy'];assert v==dict(exists=exists,can_login=login)
