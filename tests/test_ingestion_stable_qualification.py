"""The finite qualification of the stable restricted credentials: attempt policy, spacing, stop reasons, closure gating, single use, admission, and the per-attempt classification."""
import json,os,signal
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
import pytest
from verification.ingestion_storage import stable_qualification as sq
from verification.ingestion_storage import restricted_route as rr
from verification.ingestion_storage.operational_controller import Denied

WORKER,EFFECT=sq.ROLES
URLS={WORKER:rr.url('POOLER',WORKER,'synthetic-worker'),EFFECT:rr.url('POOLER',EFFECT,'synthetic-effect')}


class Clock:
    def __init__(self):self.now=1000.0;self.sleeps=[]
    def __call__(self):return self.now
    def sleep(self,s):self.sleeps.append(s);self.now+=s


def record(role,n,outcome,reason=None,closure=True):
    return dict(role=role,ordinal=n,spacing_waited_seconds=0.0,outcome=outcome,reason_code=reason,client_closure_verified=closure,connection_attempts=1,driver_statements=0,elapsed_seconds=0.1,credential='UNCHANGED_SINCE_FIRST_ATTEMPT',probe=None)


def scripted(script,stop_file=None):
    """A Qualification whose attempts follow a script; waits advance a fake clock."""
    clock=Clock();events=[];steps=list(script)
    q=sq.Qualification(URLS,emit=lambda e,p:events.append((e,p)),ssl={},hostaddr='192.0.2.1',clock=clock,sleep=clock.sleep,stop_file=stop_file)
    log=[]
    def attempt(role,ordinal,waited):
        step=steps.pop(0);log.append((role,ordinal,waited));clock.now+=1
        r=record(role,ordinal,*step);r['spacing_waited_seconds']=waited;q.attempts.append(r);return r
    q.attempt=attempt;q.log=log;q.clock_obj=clock;q.events=events
    return q


OK=('CONNECTED',None);AUTH=('FAILED','AUTHENTICATION_REJECTED')


def test_both_qualify_on_the_first_attempt_without_any_wait():
    q=scripted([OK,OK]);r=q.run()
    assert r['status']=='STABLE_CREDENTIALS_QUALIFIED' and r['attempts_total']==2 and q.clock_obj.sleeps==[] and r['use_blocked'] is False and r['stop_reason'] is None and r['retained_access'] is None
    assert [a[:2] for a in q.log]==[(WORKER,1),(EFFECT,1)]


def test_the_exact_authentication_failure_continues_with_the_fixed_spacing_20_then_60():
    q=scripted([AUTH,AUTH,OK,OK]);r=q.run()
    assert r['status']=='STABLE_CREDENTIALS_QUALIFIED' and r['attempts_total']==4 and sum(q.clock_obj.sleeps)==80 and all(s<=1.0 for s in q.clock_obj.sleeps)
    assert [a[2] for a in q.log]==[0.0,20.0,60.0,0.0] and [a[:2] for a in q.log]==[(WORKER,1),(WORKER,2),(WORKER,3),(EFFECT,1)]


def test_three_rejections_stop_the_worker_sequence_and_the_effect_login_is_never_attempted():
    q=scripted([AUTH,AUTH,AUTH]);r=q.run()
    assert r['status']=='QUALIFICATION_STOPPED' and r['stop_reason']=='AUTH_REJECTED_EXHAUSTED' and r['attempts_total']==3 and r['roles'][EFFECT]['attempts']==[] and r['use_blocked'] is True
    assert r['retained_access']=='BOTH_LOGINS_REMAIN_ENABLED_UNTIL_THE_OWNER_RUNS_THE_PRIVILEGED_REVOCATION'


def test_effect_failures_after_a_worker_success_are_limited_to_three_and_six_overall_is_never_exceeded():
    q=scripted([OK,AUTH,AUTH,AUTH]);r=q.run()
    assert r['stop_reason']=='AUTH_REJECTED_EXHAUSTED' and r['attempts_total']==4 and r['roles'][WORKER]['qualified'] is True and r['roles'][EFFECT]['qualified'] is False
    q=scripted([AUTH,AUTH,OK,AUTH,AUTH,AUTH]);r=q.run()
    assert r['attempts_total']==6 and r['stop_reason']=='AUTH_REJECTED_EXHAUSTED' and r['limits']['total']==6 and r['limits']['per_role']==3


@pytest.mark.parametrize('reason,stop',[('TLS_HOSTNAME_MISMATCH','TLS_FAILURE'),('TLS_CHAIN_REJECTED','TLS_FAILURE'),('TLS_CA_UNAVAILABLE','TLS_FAILURE'),('CIRCUIT_BREAKER_INDICATED','CIRCUIT_BREAKER_INDICATED'),
    ('UNEXPECTED_PROFILE','UNEXPECTED_PROFILE'),('UNKNOWN','UNRECOGNISED_FAILURE'),('CONNECTION_TIMEOUT','UNRECOGNISED_FAILURE'),('ROUTING_IDENTITY_REJECTED','UNRECOGNISED_FAILURE'),
    ('CONNECTION_CAPACITY','UNRECOGNISED_FAILURE'),('PERMISSION_DENIED','UNRECOGNISED_FAILURE'),('CONNECTION_REFUSED','UNRECOGNISED_FAILURE'),('AUTHORIZATION_REJECTED','UNRECOGNISED_FAILURE')])
def test_any_other_failure_class_stops_at_once_without_a_second_attempt(reason,stop):
    q=scripted([('FAILED',reason)]);r=q.run()
    assert r['stop_reason']==stop and r['attempts_total']==1 and q.clock_obj.sleeps==[]


def test_uncertain_closure_stops_even_after_the_exact_authentication_failure():
    q=scripted([('FAILED','AUTHENTICATION_REJECTED',False)]);r=q.run()
    assert r['stop_reason']=='UNCERTAIN_CLOSURE' and r['attempts_total']==1 and q.clock_obj.sleeps==[]


def test_a_stop_file_during_a_spacing_wait_ends_the_sequence(tmp_path):
    stop=tmp_path/'STOP';q=scripted([AUTH,OK,OK],stop_file=stop)
    original=q.sleep
    def sleeper(s):
        original(s)
        if len(q.clock_obj.sleeps)==3:stop.write_text('x')
    q.sleep=sleeper;r=q.run()
    assert r['stop_reason']=='MANUAL_STOP' and r['attempts_total']==1 and len(q.clock_obj.sleeps)==3


def test_the_overall_deadline_ends_the_sequence():
    q=scripted([AUTH,AUTH,AUTH,AUTH])
    q.clock_obj.now=q.started+sq.OVERALL_SECONDS-30
    r=q.run()
    assert r['stop_reason']=='OVERALL_DEADLINE' and r['attempts_total']<=2
    assert sq.OVERALL_SECONDS>=2*sum(sq.SPACING_SECONDS)+6*10          # the documented schedule fits inside the hard stop with room for the bounded attempts


def test_a_qualification_object_is_single_use_and_cannot_be_extended():
    q=scripted([OK,OK]);q.run()
    with pytest.raises(RuntimeError,match='QUALIFICATION_SINGLE_USE'):q.run()


def test_the_credentials_must_be_exactly_the_two_restricted_ones_and_unchanged_between_attempts():
    with pytest.raises(ValueError):sq.Qualification({WORKER:URLS[WORKER]},emit=lambda *_:None,ssl={},hostaddr='192.0.2.1')
    q=sq.Qualification(URLS,emit=lambda *_:None,ssl={},hostaddr='192.0.2.1')
    q.urls[WORKER]=URLS[WORKER]+'x'
    with pytest.raises(sq.Stop):q.attempt(WORKER,1,0.0)
    q.urls[WORKER]=URLS[EFFECT]                      # the other login's credential presented as the worker's
    q.first_urls[WORKER]=URLS[EFFECT]
    with pytest.raises(sq.Stop,match='ROUTE_OR_CREDENTIAL_REJECTED_BEFORE_CONNECT'):q.attempt(WORKER,1,0.0)


def test_the_result_claims_nothing_the_restricted_runtime_cannot_know_and_no_authority():
    q=scripted([OK,OK]);r=q.run()
    assert r['grants_issued']==0 and r['exceptions_registered']==0 and r['source_requests']==0 and r['application_writes']==0 and r['administrative_credential_present'] is False
    assert set(r['owner_verifications_required'])=={'NO_OTHER_SESSIONS_OF_THE_TWO_LOGINS','PASSWORD_STATE_AND_EXACT_VALID_UNTIL_ON_THE_SERVER','NO_UNEXPIRED_GRANT_FOR_THE_EFFECT_VIEW','SERVER_SIDE_CLOSURE_OF_THE_QUALIFICATION_SESSIONS'}
    assert 'synthetic-worker' not in json.dumps(r)+json.dumps(q.events) and 'postgresql://' not in json.dumps(r)+json.dumps(q.events)


GOOD=dict(QUALIFICATION_REVIEWED_SHA='a'*40,GITHUB_SHA='a'*40,GITHUB_WORKFLOW_SHA='a'*40,GITHUB_REF='refs/heads/master',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',GITHUB_ACTIONS='true',
          RUNNER_ENVIRONMENT='github-hosted',QUALIFICATION_AUTHORITY=sq.AUTHORITY,INGESTION_WORKER_DATABASE_URL='x',INGESTION_EFFECT_DATABASE_URL='y')


def test_admission_is_single_use_exact_and_refuses_any_administrative_credential():
    assert sq.admitted(GOOD)
    for key,bad in (('QUALIFICATION_REVIEWED_SHA','b'*40),('GITHUB_SHA','b'*40),('GITHUB_WORKFLOW_SHA','b'*40),('GITHUB_REF','refs/heads/other'),('GITHUB_RUN_NUMBER','2'),('GITHUB_RUN_ATTEMPT','2'),
                    ('GITHUB_ACTIONS','false'),('RUNNER_ENVIRONMENT','self-hosted'),('QUALIFICATION_AUTHORITY','NOT_AUTHORISED')):
        assert not sq.admitted({**GOOD,key:bad})
    for extra in ('DATABASE_URL','INGESTION_STORAGE_DATABASE_URL','GH_TOKEN','GITHUB_TOKEN','PGPASSWORD','PGHOST'):
        assert not sq.admitted({**GOOD,extra:'x'})


# --- the per-attempt classification, with a fake budget (no database) -----------------------------------------------------------------------------------------
class FakeConnection:
    def __init__(self,rows):self.rows=list(rows)
    def execute(self,statement,params=None):
        return SimpleNamespace(fetchone=lambda:self.rows.pop(0))


def fake_budget(*,connect=None,rows=(),diagnostics=(),receipt=None):
    class Budget:
        def __init__(self,**kw):self.connection_diagnostics=list(diagnostics)
        def engine(self,url,**kw):
            conn=FakeConnection(rows)
            @contextmanager
            def connect_ctx():
                if connect is not None:raise connect
                yield conn
            return SimpleNamespace(connect=connect_ctx)
        def close(self,_):return receipt or dict(cleanup='CLOSED',connections_closed=True,connection_attempts=1,driver_statements=3)
    return Budget


def probe_row(role=WORKER,days=90,**over):
    now=datetime.now(timezone.utc)
    row=dict(valid=now+timedelta(days=days),limit=1,login=True,members=[sq.CAPABILITY[role]],cap=True,forbidden=False,dml=False,select=role==WORKER,now=now);row.update(over)
    return (row['valid'],row['limit'],row['login'],row['members'],row['cap'],row['forbidden'],row['dml'],row['select'],row['now'])


def run_attempt(role,**kw):
    q=sq.Qualification(URLS,emit=lambda *_:None,ssl={},hostaddr='192.0.2.1',budget_factory=fake_budget(**kw))
    return q.attempt(role,1,0.0)


def test_a_clean_worker_attempt_reports_the_self_visible_profile_and_the_informational_control_row():
    r=run_attempt(WORKER,rows=[probe_row(),(True,'STORAGE_TEST_STOP',1,0)])
    assert r['outcome']=='CONNECTED' and r['probe']['control_row']==dict(global_stop_set=True,manual_stop='STORAGE_TEST_STOP',hard_stop_generation=1,unexpired_grants=0) and r['probe']['valid_days_remaining']>=89 and r['client_closure_verified']


def test_the_effect_attempt_makes_no_control_row_read():
    r=run_attempt(EFFECT,rows=[probe_row(EFFECT)])
    assert r['outcome']=='CONNECTED' and r['probe']['control_row'] is None


@pytest.mark.parametrize('over',[dict(days=3),dict(limit=2),dict(login=False),dict(members=['ingestion_worker','ingestion_storage_operator']),dict(cap=False),dict(forbidden=True),dict(dml=True),dict(select=False)])
def test_any_profile_deviation_is_an_unexpected_profile(over):
    r=run_attempt(WORKER,rows=[probe_row(**over),(True,None,0,0)])
    assert r['outcome']=='FAILED' and r['reason_code']=='UNEXPECTED_PROFILE'


def test_a_missing_validity_is_an_unexpected_profile():
    row=list(probe_row());row[0]=None
    assert run_attempt(WORKER,rows=[tuple(row),(True,None,0,0)])['reason_code']=='UNEXPECTED_PROFILE'


def test_an_effect_login_that_can_read_the_ledger_is_an_unexpected_profile():
    assert run_attempt(EFFECT,rows=[probe_row(EFFECT,select=True)])['reason_code']=='UNEXPECTED_PROFILE'


def test_a_driver_connect_failure_uses_the_recorded_allow_listed_reason():
    r=run_attempt(WORKER,connect=RuntimeError('private text must never escape'),diagnostics=[dict(phase='DRIVER_CONNECT',reason_code='AUTHENTICATION_REJECTED')])
    assert r['outcome']=='FAILED' and r['reason_code']=='AUTHENTICATION_REJECTED' and 'private text' not in json.dumps(r)
    r=run_attempt(WORKER,connect=RuntimeError('x'),diagnostics=[dict(phase='DRIVER_CONNECT',reason_code='TLS_HOSTNAME_MISMATCH')])
    assert r['reason_code']=='TLS_HOSTNAME_MISMATCH'


def test_the_runtime_gate_denial_is_an_unexpected_profile_and_unclassified_errors_stay_unknown():
    assert run_attempt(WORKER,connect=Denied('SERVER_TIMEOUT_OR_RESTRICTED_IDENTITY_PROFILE'))['reason_code']=='UNEXPECTED_PROFILE'
    assert run_attempt(WORKER,connect=RuntimeError('anything else'))['reason_code'] in {'UNKNOWN','OTHER'}


def test_closure_is_taken_from_the_budget_receipt():
    r=run_attempt(WORKER,connect=RuntimeError('x'),diagnostics=[dict(phase='DRIVER_CONNECT',reason_code='AUTHENTICATION_REJECTED')],receipt=dict(cleanup='UNCERTAIN',connections_closed=False,connection_attempts=1,driver_statements=0))
    assert r['client_closure_verified'] is False


def test_uncertain_closure_stops_even_a_successful_attempt():
    q=scripted([('CONNECTED',None,False)]);r=q.run()
    assert r['stop_reason']=='UNCERTAIN_CLOSURE' and r['attempts_total']==1 and r['status']=='QUALIFICATION_STOPPED' and r['roles'][WORKER]['qualified'] is False and r['roles'][EFFECT]['attempts']==[]


def test_a_circuit_breaker_message_is_a_distinct_fixed_class_and_a_conflicting_message_stays_unknown():
    import psycopg
    from verification.ingestion_storage.connection_diagnostics import classify_native
    assert classify_native(psycopg.OperationalError('Circuit breaker open: too many authentication errors'),None)==('CIRCUIT_BREAKER_INDICATED','LOCAL_ALLOWLIST')
    assert classify_native(psycopg.OperationalError('password authentication failed for user "x" (circuit breaker open)'),None)[0]=='CIRCUIT_BREAKER_INDICATED'      # the protection indication wins: never continue
    assert classify_native(psycopg.OperationalError('Circuit breaker open: too many authentication errors'),'28P01')==('CIRCUIT_BREAKER_INDICATED','LOCAL_ALLOWLIST')      # even with an authentication SQLSTATE
    assert classify_native(psycopg.OperationalError('Circuit breaker open'),'08006')[0]=='CIRCUIT_BREAKER_INDICATED'
    assert classify_native(psycopg.OperationalError('password authentication failed for user "x"'),None)==('AUTHENTICATION_REJECTED','LOCAL_ALLOWLIST')


def test_no_attempt_starts_unless_it_can_finish_inside_the_overall_window():
    q=scripted([AUTH,AUTH,AUTH,AUTH])
    q.clock_obj.now=q.started+sq.OVERALL_SECONDS-(sq.ATTEMPT_SECONDS+10)+1
    r=q.run()
    assert r['stop_reason']=='OVERALL_DEADLINE' and r['attempts_total']==0 and sq.ATTEMPT_SECONDS+10<sq.OVERALL_SECONDS and sq.OVERALL_SECONDS+15<=345      # the workflow kills the process at 345 s


def test_an_unexpected_error_keeps_the_attempts_already_made_in_the_accounting():
    q=scripted([OK,AUTH])
    original=q.attempt
    def attempt(role,ordinal,waited):
        if len(q.attempts)==2:raise RuntimeError('private text must never escape')
        return original(role,ordinal,waited)
    q.attempt=attempt;r=q.run()
    assert r['attempts_total']==2 and r['stop_reason']=='UNRECOGNISED_FAILURE' and 'private text' not in json.dumps(r) and r['roles'][WORKER]['qualified'] is True


def _handler():
    def cancel(signum,frame):raise sq.Cancelled()
    saved={s:signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGINT)}
    for s in saved:signal.signal(s,cancel)
    return saved


def _restore(saved):
    for s,h in saved.items():signal.signal(s,h)


def test_a_cancellation_while_the_budget_is_being_closed_leaves_a_started_unknown_attempt_not_a_lost_one():
    saved=_handler()
    class Budget:
        def __init__(self,**kw):self.connection_diagnostics=[]
        def engine(self,url,**kw):
            @contextmanager
            def connect():
                raise RuntimeError('x')
                yield
            return SimpleNamespace(connect=connect)
        def close(self,_):os.kill(os.getpid(),signal.SIGTERM);return dict(cleanup='CLOSED',connections_closed=True)
    try:
        q=sq.Qualification(URLS,emit=lambda *_:None,ssl={},hostaddr='192.0.2.1',budget_factory=Budget);r=q.run()
    finally:_restore(saved)
    a=r['roles'][WORKER]['attempts'][0]
    assert r['stop_reason']=='CANCELLED' and r['attempts_total']==1 and a['outcome']=='INTERRUPTED' and a['receipt'] is None and a['receipt_basis']=='UNKNOWN' and a['client_closure_verified'] is False
    assert r['accounting']['attempts_started']['value']==1 and all(m['basis']=='LOWER_BOUND_ONLY_SOME_RECEIPT_UNKNOWN' for m in r['accounting']['metrics'].values()) and r['accounting']['client_closure']['status']=='NOT_VERIFIED_FOR_SOME_ATTEMPT'


def test_a_cancellation_before_the_budget_exists_still_counts_the_attempt_as_started_and_unknown():
    saved=_handler()
    def factory(**kw):os.kill(os.getpid(),signal.SIGTERM);raise AssertionError('unreached')
    try:
        q=sq.Qualification(URLS,emit=lambda *_:None,ssl={},hostaddr='192.0.2.1',budget_factory=factory);r=q.run()
    finally:_restore(saved)
    a=r['roles'][WORKER]['attempts'][0]
    assert r['stop_reason']=='CANCELLED' and r['attempts_total']==1 and a['outcome'] in ('INTERRUPTED','STARTED_UNRESOLVED') and a['receipt'] is None and a['client_closure_verified'] is False
    assert r['accounting']['attempts_started']['value']==1 and r['accounting']['metrics']['connection_attempts']['basis']!='MEASURED' and r['use_blocked'] is True


def test_a_receipt_missing_a_numeric_field_is_not_a_measured_zero():
    partial=dict(receipt=dict(connection_attempts=1,driver_statements=None,returned_data_value_bytes=0,connection_active_seconds=0.1,connections_opened=0,connections_closed_count=0,cancel_attempts=0,cancel_failures=0,cancel_seconds=0.0,hard_deadline_events=[]),client_closure_verified=True)
    acc=sq.Qualification.accounting_for([partial])
    assert acc['metrics']['driver_commands']=={'value':0,'basis':'LOWER_BOUND_ONLY_SOME_RECEIPT_UNKNOWN'}
    nokey=dict(receipt={'cleanup':'CLOSED'},client_closure_verified=True)
    assert sq.Qualification.accounting_for([nokey])['metrics']['connection_attempts']['basis']=='LOWER_BOUND_ONLY_SOME_RECEIPT_UNKNOWN'


def test_a_cancelled_preparation_is_reported_as_cancelled_not_as_a_credential_rejection():
    r=sq.preparation_failure_result('Cancelled')
    assert r['stop_reason']=='CANCELLED' and r['accounting']['attempts_started']['value']==0 and all(m['basis']=='NOT_STARTED' for m in r['accounting']['metrics'].values())


def test_a_signal_during_a_shielded_record_is_delivered_only_after_the_record_is_complete():
    saved=_handler();done=[]
    try:
        with pytest.raises(sq.Cancelled):
            with sq.shielded():
                os.kill(os.getpid(),signal.SIGTERM);done.append('record written')      # still running: the signal is pending, not delivered
    finally:_restore(saved)
    assert done==['record written']
