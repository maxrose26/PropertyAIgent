"""The four-entry restricted-connection matrix: entry logic, accounting, stops, closure and interpretation, against a disposable server that logs every statement.

Synthetic credentials and a disposable loopback server only. The full lifecycle (install, mapping, activation, teardown, administrative accounting) is exercised against the
restricted PG17 fixture by test_discovery_ingestion_operational_wrapper_pg.py (matrix faults); this file isolates the matrix itself."""
import json,os,re,socket,subprocess,sys,time
from types import SimpleNamespace
import psycopg,pytest
from sqlalchemy.engine import make_url
from verification.ingestion_storage import restricted_matrix as rm
from verification.ingestion_storage.restricted_matrix import Matrix,MatrixStop,ENTRIES,STATEMENT,LIMITS,INTERPRETATION
from verification.ingestion_storage.operational_preparation import STARTUP_OPTIONS
from verification.ingestion_storage.tls_trust import owned_resources
from tests.test_ingestion_admin_connection_probe import cluster      # noqa: F401  (disposable logging cluster fixture)
from app.ingestion.ledger import Denied
from verification.ingestion_storage.operational_cleanup import Stop

WORKER='ingestion_worker_login';EFFECT='ingestion_effect_login'


@pytest.fixture
def roles(cluster):
    with psycopg.connect(host='127.0.0.1',port=cluster.port,dbname='postgres',user='postgres',autocommit=True) as c:
        for r in (WORKER,EFFECT):
            c.execute(f'DROP ROLE IF EXISTS {r}');c.execute(f'CREATE ROLE {r} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 1')
    yield
    with psycopg.connect(host='127.0.0.1',port=cluster.port,dbname='postgres',user='postgres',autocommit=True) as c:
        c.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename = ANY(%s)',([WORKER,EFFECT],))


def role_counts(cluster):
    text=cluster.log.read_text()
    return (len(re.findall(r'connection authorized: user=ingestion_(?:worker|effect)_login',text)),len(re.findall(r'disconnection: .*user=ingestion_(?:worker|effect)_login',text)),sum(1 for x in cluster.statements() if x.strip()==STATEMENT))


def sessions(cluster):
    with psycopg.connect(host='127.0.0.1',port=cluster.port,dbname='postgres',user='postgres',autocommit=True) as c:
        return c.execute('SELECT count(*) FROM pg_stat_activity WHERE usename = ANY(%s)',([WORKER,EFFECT],)).fetchone()[0]


class Runner:
    """The minimal surface the matrix uses: check, emit, owner (urls, timeline), ssl, hostaddr."""
    def __init__(self,cluster):
        self.events=[];self.ssl=None;self.hostaddr=None
        self.owner=SimpleNamespace(urls={r:f'postgresql://{r}:synthetic@127.0.0.1:{cluster.port}/postgres' for r in (WORKER,EFFECT)},timeline={r:dict(password_committed=100.0,mapped=101.0,activated=102.0) for r in (WORKER,EFFECT)})
        self.cluster=cluster;self.checks=0
    def check(self):self.checks+=1
    def emit(self,event,payload):self.events.append((event,payload))


def principal(url,ssl):
    u=make_url(url);return u,u.username


def make(cluster,connect=None,clock=None):
    runner=Runner(cluster)
    kw=dict(principal=principal)
    if connect:kw['connect']=connect
    if clock:kw['clock']=clock
    return runner,Matrix(runner,**kw)


# --- the real four-entry run, observed at the server --------------------------------------------------------------------------------------------------------

def test_four_entries_each_one_connection_one_statement_closed_before_the_next(cluster,roles):
    runner,matrix=make(cluster)
    before=role_counts(cluster);statements_before=len(cluster.statements())
    seen=[]
    original=matrix.entry
    def watched(index,role,variant):
        original(index,role,variant);seen.append(sessions(cluster))       # after each entry the server shows NO session for either login
    matrix.entry=watched
    report=matrix.run()
    after=role_counts(cluster)
    assert tuple(a-b for a,b in zip(after,before))==(4,4,4) and seen==[0,0,0,0]       # server-side: 4 connections, 4 disconnections, 4 identity statements for the two logins
    assert [e['outcome'] for e in report['entries']]==['CONNECTED_IDENTITY_VERIFIED']*4
    assert [(e['role'],e['startup_options']) for e in report['entries']]==[(r,v) for r,v in ENTRIES]
    delta=[x.strip() for x in cluster.statements()[statements_before:] if 'pg_stat_activity' not in x]
    assert delta==[STATEMENT]*4                                                    # nothing else reached the server: no BEGIN, ROLLBACK, COMMIT, SET or startup query
    acc=report['accounting'];assert (acc['connection_attempts']['value'],acc['identity_statements']['value'],acc['rollbacks']['value'],acc['commits']['value'])==(4,4,0,0)
    assert all(e['connection_closure']=={'status':'CLOSED','connection_object_closed':True,'new_owned_sockets':0,'failed_native_handle_finished':None} for e in report['entries'])
    # the REVIEWED entries really carried the reviewed server settings; the NONE entries did not
    assert [e['observed_server_timeouts_match_reviewed'] for e in report['entries']]==[False,True,False,True]


def test_option_variants_differ_only_in_startup_options(cluster,roles):
    calls=[]
    real=psycopg.connect
    runner,matrix=make(cluster,connect=lambda **k:(calls.append(k),real(**k))[1])
    matrix.run()
    assert len(calls)==4 and 'options' not in calls[0] and 'options' not in calls[2] and calls[1]['options']==STARTUP_OPTIONS==calls[3]['options']
    strip=lambda k:{x:v for x,v in k.items() if x!='options'}
    assert strip(calls[0])==strip(calls[1]) and strip(calls[2])==strip(calls[3])
    assert all(k['prepare_threshold'] is None and k['autocommit'] is True and k['connect_timeout']==3 for k in calls)


def test_connection_limit_one_makes_a_held_session_a_classified_capacity_failure_not_a_stop(cluster,roles):
    held=psycopg.connect(host='127.0.0.1',port=cluster.port,dbname='postgres',user=WORKER,autocommit=True)
    try:
        runner,matrix=make(cluster)
        report=matrix.run()
    finally:held.close()
    # With the worker login's single slot occupied, both worker entries fail with a classified capacity reason; the effect login (its own slot) is unaffected.
    assert [e['outcome'] for e in report['entries']]==['FAILED_CLASSIFIED','FAILED_CLASSIFIED','CONNECTED_IDENTITY_VERIFIED','CONNECTED_IDENTITY_VERIFIED']
    assert [e.get('failure',{}).get('reason_code') for e in report['entries'][:2]]==['CONNECTION_CAPACITY']*2 and report['entries'][0]['failure']['sqlstate'] is None   # connect-time server errors carry no SQLSTATE in this driver
    assert sessions(cluster)==0


def test_sequential_entries_for_the_same_login_succeed_only_because_each_is_closed_first(cluster,roles):
    runner,matrix=make(cluster);report=matrix.run()
    assert [e['outcome'] for e in report['entries'][:2]]==['CONNECTED_IDENTITY_VERIFIED']*2          # worker NONE then worker REVIEWED on a CONNECTION LIMIT 1 login


def test_a_connection_left_open_would_poison_the_next_entry_so_it_is_a_global_stop(cluster,roles):
    real=psycopg.connect
    kept=[]
    class Leaky:
        """Looks like a connection but its close() does not close: closure must be UNCERTAIN and stop everything."""
        def __init__(self,k):self.inner=real(**k);kept.append(self.inner)
        def execute(self,s):return self.inner.execute(s)
        closed=False
        def close(self):pass
    runner,matrix=make(cluster,connect=lambda **k:Leaky(k))
    with pytest.raises(MatrixStop) as stopped:matrix.run()
    kept[0].close()
    assert stopped.value.code=='CLOSURE_UNCERTAIN' and matrix.entries[0]['connection_closure']['status']=='UNCERTAIN'
    report=matrix.finalise();assert [e['outcome'] for e in report['entries'][1:]]==['SKIPPED_GLOBAL_STOP']*3 and report['global_stop']=='CLOSURE_UNCERTAIN'


# --- injected failures: per-entry outcomes, continuation rules, skipped entries, cumulative accounting ----------------------------------------------------------------

def _connect_with(cluster,plan):
    """plan: ordinal -> exception to raise instead of connecting."""
    real=psycopg.connect;count=[0]
    def connect(**k):
        count[0]+=1
        if count[0] in plan:raise plan[count[0]]
        return real(**k)
    return connect


@pytest.mark.parametrize('plan,outcomes,reasons',[
    ({1:psycopg.errors.InvalidPassword('password authentication failed for user "x"')},['FAILED_CLASSIFIED','CONNECTED_IDENTITY_VERIFIED','CONNECTED_IDENTITY_VERIFIED','CONNECTED_IDENTITY_VERIFIED'],['AUTHENTICATION_REJECTED',None,None,None]),
    ({2:psycopg.OperationalError('connection timeout expired'),4:psycopg.OperationalError('FATAL:  Tenant or user not found')},['CONNECTED_IDENTITY_VERIFIED','FAILED_CLASSIFIED','CONNECTED_IDENTITY_VERIFIED','FAILED_CLASSIFIED'],[None,'CONNECTION_TIMEOUT',None,'ROUTING_IDENTITY_REJECTED']),
    ({1:psycopg.errors.InvalidPassword('password authentication failed for user "x"'),2:psycopg.errors.InvalidPassword('password authentication failed for user "x"'),
      3:psycopg.errors.InvalidPassword('password authentication failed for user "x"'),4:psycopg.errors.InvalidPassword('password authentication failed for user "x"')},['FAILED_CLASSIFIED']*4,['AUTHENTICATION_REJECTED']*4),
])
def test_classified_failures_are_recorded_per_entry_and_the_matrix_continues(cluster,roles,plan,outcomes,reasons):
    runner,matrix=make(cluster,connect=_connect_with(cluster,plan))
    report=matrix.run()
    assert [e['outcome'] for e in report['entries']]==outcomes
    assert [e.get('failure',{}).get('reason_code') for e in report['entries']]==reasons
    assert all(e.get('failure',{}).get('underlying_cause','UNDETERMINED')=='UNDETERMINED' for e in report['entries'])
    acc=report['accounting'];connected=outcomes.count('CONNECTED_IDENTITY_VERIFIED')
    assert (acc['connection_attempts']['value'],acc['identity_statements']['value'],acc['entries_connected']['value'],acc['entries_failed_classified']['value'])==(4,connected,connected,4-connected)
    assert report['global_stop'] is None and all(e['connection_closure']['status']=='CLOSED' for e in report['entries']) and sessions(cluster)==0


@pytest.mark.parametrize('failing,error,code,skipped',[
    (2,RuntimeError('private text'),'UNCLASSIFIED_FAILURE',2),
    (1,psycopg.OperationalError('arbitrary unknown text'),'UNCLASSIFIED_FAILURE',3),
    (3,psycopg.OperationalError('server certificate for "x" does not match host name "y"'),'SECURITY_CLASS_FAILURE',1),
    (1,psycopg.OperationalError('SSL error: certificate verify failed'),'SECURITY_CLASS_FAILURE',3),
    (4,psycopg.errors.QueryCanceled('canceling statement due to statement timeout'),'NON_CONTINUABLE_FAILURE',0),
])
def test_global_stops_skip_the_remaining_entries_and_say_so(cluster,roles,failing,error,code,skipped):
    runner,matrix=make(cluster,connect=_connect_with(cluster,{failing:error}))
    with pytest.raises(MatrixStop) as stopped:matrix.run()
    assert stopped.value.code==code
    report=matrix.finalise()
    assert [e['outcome'] for e in report['entries']].count('SKIPPED_GLOBAL_STOP')==skipped and report['global_stop']==code
    assert report['accounting']['connection_attempts']['value']==failing and report['accounting']['entries_not_attempted']['value']==skipped
    assert all(e['connection_closure']['status']=='CLOSED' for e in report['entries'] if e['outcome'] not in ('SKIPPED_GLOBAL_STOP',)) and sessions(cluster)==0
    assert 'private text' not in json.dumps(report) and 'arbitrary unknown text' not in json.dumps(report)


def test_unexpected_identity_stops_everything(cluster,roles,monkeypatch):
    runner,matrix=make(cluster)
    monkeypatch.setattr(rm,'EXPECTED_FLAGS',(True,True,False,False,False,False))
    with pytest.raises(MatrixStop) as stopped:matrix.run()
    e=matrix.entries[0]
    assert stopped.value.code=='UNEXPECTED_IDENTITY' and e['outcome']=='IDENTITY_UNEXPECTED' and e['connection_closure']['status']=='CLOSED'
    assert e['identity_check']==dict(current_user_matches_login=True,session_user_matches_login=True,restricted_flags_match=False,verified=False)       # which part of identity failed is recorded
    assert e['timeout_check']['requested_startup_options']=='NONE'


def test_options_not_reflected_is_a_separate_observation_not_an_identity_failure(cluster,roles,monkeypatch):
    runner,matrix=make(cluster)
    monkeypatch.setitem(rm.EXPECTED_TIMEOUTS,'REVIEWED',('1s','1s','1s'))            # the session does not carry the requested values
    report=matrix.run()
    assert [e['outcome'] for e in report['entries']]==['CONNECTED_IDENTITY_VERIFIED','CONNECTED_IDENTITY_VERIFIED_OPTIONS_NOT_REFLECTED','CONNECTED_IDENTITY_VERIFIED','CONNECTED_IDENTITY_VERIFIED_OPTIONS_NOT_REFLECTED']
    assert report['global_stop'] is None and report['accounting']['entries_connected']['value']==4 and report['accounting']['entries_options_not_reflected']['value']==2
    e=report['entries'][1]
    assert e['identity_check']['verified'] is True and e['timeout_check']['reflected_as_requested'] is False and e['timeout_check']['matches_reviewed_values'] is False
    assert report['entries'][0]['timeout_check']['reflected_as_requested'] is None                       # no options were requested for the NONE entry
    assert e['timeout_check']['observed_statement_lock_idle_timeouts']==['10s','3s','20s']             # bounded allow-listed observation retained


def test_observed_settings_are_bounded_and_allow_listed():
    assert [rm.bounded_setting(x) for x in ('0','10s','2min','1500ms','10 s','x'*40,'DROP','',None,'1;2')]==['0','10s','2min','1500ms']+['NON_ALLOWLISTED_VALUE']*6
    runner=None
    assert rm.bounded_setting('999999d')=='999999d' and rm.bounded_setting('9999999')=='NON_ALLOWLISTED_VALUE'


def test_budgets_are_global_stops(cluster,roles,monkeypatch):
    monkeypatch.setitem(rm.LIMITS,'connection_attempts',2)
    runner,matrix=make(cluster)
    with pytest.raises(MatrixStop) as stopped:matrix.run()
    assert stopped.value.code=='CONNECTION_BUDGET_EXHAUSTED' and matrix.attempts==2 and matrix.entries[2]['outcome']=='NOT_REACHED'
    monkeypatch.setitem(rm.LIMITS,'connection_attempts',4);monkeypatch.setitem(rm.LIMITS,'returned_data_value_bytes',20)
    runner,matrix=make(cluster)
    with pytest.raises(MatrixStop) as stopped:matrix.run()
    assert stopped.value.code=='RETURNED_BYTES_EXHAUSTED' and matrix.entries[0]['connection_closure']['status']=='CLOSED' and sessions(cluster)==0
    monkeypatch.setitem(rm.LIMITS,'returned_data_value_bytes',1024)
    tick=iter([0.0]+[999.0]*50)
    runner,matrix=make(cluster,clock=lambda:next(tick))
    with pytest.raises(MatrixStop) as stopped:matrix.run()
    assert stopped.value.code=='MATRIX_TIME_EXHAUSTED'


def test_entry_order_cannot_be_repeated_or_reused(cluster,roles):
    runner,matrix=make(cluster);matrix.run()
    with pytest.raises(MatrixStop) as stopped:matrix.entry(0,*ENTRIES[0])
    assert stopped.value.code=='MATRIX_ORDER_VIOLATION'


def test_a_leaked_socket_makes_closure_uncertain(cluster,roles):
    leaked=[]
    def connect(**k):
        leaked.append(socket.socket());raise psycopg.OperationalError('connection timeout expired')
    runner,matrix=make(cluster,connect=connect)
    with pytest.raises(MatrixStop) as stopped:matrix.run()
    [s.close() for s in leaked]
    assert stopped.value.code=='CLOSURE_UNCERTAIN' and matrix.entries[0]['connection_closure']['new_owned_sockets']==1


# --- intervals, interpretation, secrecy -------------------------------------------------------------------------------------------------------------------------------

def test_intervals_since_password_mapping_activation_and_previous_entry_are_recorded(cluster,roles):
    now=[110.0]
    def clock():
        now[0]+=0.5;return now[0]
    runner,matrix=make(cluster,clock=clock)
    runner.owner.timeline[EFFECT]=dict(password_committed=109.0,mapped=109.2,activated=109.4)
    report=matrix.run()
    first=report['entries'][0]['intervals_at_attempt'];assert first['since_password_committed_seconds']>first['since_mapping_acknowledged_seconds']>first['since_activation_committed_seconds']>0 and first['since_previous_entry_closed_seconds'] is None
    assert all(e['intervals_at_attempt']['since_previous_entry_closed_seconds']>0 for e in report['entries'][1:])
    assert report['entries'][2]['intervals_at_attempt']['since_password_committed_seconds']<report['entries'][0]['intervals_at_attempt']['since_password_committed_seconds']   # per-role stamps


def test_the_report_states_what_the_matrix_does_not_establish_and_leaks_nothing(cluster,roles):
    runner,matrix=make(cluster);report=matrix.run()
    text=json.dumps(report)
    assert report['interpretation']['scope']=='CONFIGURATION_SPECIFIC_OBSERVATIONS_AT_ONE_POINT_IN_TIME' and report['interpretation']['execution_authority']=='NONE'
    assert {'CREDENTIAL_CACHING','PROPAGATION_DELAY','PROVIDER_DEFECT','CAUSE_OF_ANY_FAILURE'}<=set(report['interpretation']['not_established'])
    assert 'synthetic' not in text and 'postgresql://' not in text and '127.0.0.1' not in text
    events=json.dumps(runner.events);assert 'synthetic' not in events and 'postgresql://' not in events
    assert LIMITS['administrative_connections']==5 and LIMITS['administrative_commands']==64 and LIMITS['driver_statements']==4 and LIMITS['connection_attempts']==4 and LIMITS['rollbacks']==0 and LIMITS['commits']==0


def test_matrix_module_has_no_grant_authority_queue_source_or_application_capability():
    import ast
    from pathlib import Path
    tree=ast.parse(Path(rm.__file__).read_text());names=set()
    for node in ast.walk(tree):
        if isinstance(node,ast.Name):names.add(node.id)
        elif isinstance(node,ast.Attribute):names.add(node.attr)
        elif isinstance(node,(ast.Import,ast.ImportFrom)):names.update(a.name for a in node.names);names.add(getattr(node,'module','') or '')
    for forbidden in ('register','GitHub','github','put_secret','Coordinator','ledger','source_reader','capture_once','teardown','map_and_activate','install','Application','requests','subprocess'):assert forbidden not in names,forbidden


def test_capacity_after_the_matrix_own_connection_to_the_same_login_is_ambiguous_so_it_stops(cluster,roles):
    real=psycopg.connect;count=[0]
    def connect(**k):
        count[0]+=1
        if count[0]==2:raise psycopg.OperationalError('connection failed: FATAL:  too many connections for role "ingestion_worker_login"')
        return real(**k)
    runner,matrix=make(cluster,connect=connect)
    with pytest.raises(MatrixStop) as stopped:matrix.run()
    assert stopped.value.code=='CAPACITY_AFTER_OWN_CONNECTION' and matrix.entries[0]['outcome']=='CONNECTED_IDENTITY_VERIFIED' and matrix.entries[1]['outcome']=='FAILED_CLASSIFIED'
    assert matrix.entries[1]['failure']['reason_code']=='CONNECTION_CAPACITY' and matrix.finalise()['entries'][2]['outcome']=='SKIPPED_GLOBAL_STOP'


@pytest.mark.parametrize('raised',[Stop('WORK_CLOSURE_RESERVE'),Denied('MANUAL_STOP_OR_CONTROLLER_DEADLINE')])
def test_a_session_deadline_or_denial_during_an_entry_is_a_stop_not_a_connection_failure(cluster,roles,raised):
    runner,matrix=make(cluster,connect=_connect_with(cluster,{1:raised}))
    with pytest.raises(MatrixStop) as stopped:matrix.run()
    assert stopped.value.code=='DEADLINE_OR_BUDGET_DENIAL' and matrix.entries[0]['outcome']=='STOPPED_DURING_ENTRY' and 'failure' not in matrix.entries[0]


def test_an_audit_failure_while_recording_intent_is_a_stop_with_closure_recorded(cluster,roles):
    runner,matrix=make(cluster)
    def failing(event,payload):raise RuntimeError('audit bound')
    runner.emit=failing
    with pytest.raises(RuntimeError):matrix.run()          # an audit failure propagates to the Runner failure path (teardown); the entry still recorded its closure
    assert matrix.entries[0]['connection_closure']['status']=='CLOSED'
