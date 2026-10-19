"""The credential-free budget receipt of EVERY qualification attempt and the cumulative accounting, exported through the REAL qualification entrypoint (main): measured values stay measured, unknown or
unavailable ones stay explicit, a preparation failure or a cancellation never becomes a measured zero or a verified closure, and the client closure is never presented as a server-session verification."""
import json,os,signal
from contextlib import contextmanager
from types import SimpleNamespace
import psycopg,pytest
from verification.ingestion_storage import stable_qualification as sq
from verification.ingestion_storage import restricted_route as rr

WORKER,EFFECT=sq.ROLES
SECRETS={WORKER:'secret-worker-pw',EFFECT:'secret-effect-pw'}


@pytest.fixture
def entry(tmp_path,monkeypatch):
    env=dict(QUALIFICATION_REVIEWED_SHA='a'*40,GITHUB_SHA='a'*40,GITHUB_WORKFLOW_SHA='a'*40,GITHUB_REF='refs/heads/master',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',GITHUB_ACTIONS='true',
             RUNNER_ENVIRONMENT='github-hosted',QUALIFICATION_AUTHORITY=sq.AUTHORITY,INGESTION_WORKER_DATABASE_URL=rr.url('POOLER',WORKER,SECRETS[WORKER]),INGESTION_EFFECT_DATABASE_URL=rr.url('POOLER',EFFECT,SECRETS[EFFECT]))
    for key in list(os.environ):
        if key.startswith('PG') or key in sq.FORBIDDEN_ENV:monkeypatch.delenv(key,raising=False)
    for key,value in env.items():monkeypatch.setenv(key,value)
    monkeypatch.setattr(sq,'resolve_addresses',lambda progress:'192.0.2.1')
    monkeypatch.setattr(sq,'SPACING_SECONDS',(0,0))
    saved={s:signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGINT)}
    out=tmp_path/'out'
    def run():
        with pytest.raises(SystemExit) as caught:sq.main(['--output',str(out)])
        return caught.value.code,json.loads((out/'final-result.json').read_text()),out
    yield run
    for s,h in saved.items():signal.signal(s,h)
    sq._Cancellation.requested=False;sq._Cancellation.interruptible=False


def refuse(message):
    def connect(cls,*a,**kw):raise psycopg.OperationalError(message)
    return classmethod(connect)


def test_every_attempt_exports_its_complete_credential_free_receipt_through_the_real_entrypoint(entry,monkeypatch):
    monkeypatch.setattr(psycopg.Connection,'connect',refuse('connection failed: password authentication failed for user "x"'))
    code,result,out=entry()
    assert code==1 and result['status']=='QUALIFICATION_STOPPED' and result['stop_reason']=='AUTH_REJECTED_EXHAUSTED' and result['attempts_total']==3 and result['roles'][EFFECT]['attempts']==[]
    for a in result['roles'][WORKER]['attempts']:
        r=a['receipt']
        assert a['receipt_basis']=='MEASURED' and a['client_closure_verified'] is True and a['reason_code']=='AUTHENTICATION_REJECTED' and a['outcome']=='FAILED'
        assert r['connection_attempts']==1 and r['driver_statements']==0 and r['returned_data_value_bytes']==0 and r['cleanup']=='CLOSED' and r['connections_closed'] is True and r['connections_opened']==0
        assert r['cancel_attempts']==0 and r['cancel_failures']==0 and r['hard_deadline_events']==[] and r['socket_closure']=='NO_NEW_OWNED_SOCKETS' and r['failed_native_connections_closed'] is True
        assert r['connection_diagnostics'][0]['reason_code']=='AUTHENTICATION_REJECTED' and r['connection_diagnostics'][0]['message_exported'] is False and r['connection_active_seconds']>=0
    acc=result['accounting']
    assert acc['attempts_started']==dict(value=3,basis='MEASURED') and acc['attempts_with_receipt']==dict(value=3,basis='MEASURED')
    for name,value in (('connection_attempts',3),('driver_commands',0),('returned_database_value_bytes',0),('cancel_attempts',0),('cancel_failures',0),('connections_opened',0)):
        assert acc['metrics'][name]==dict(value=value,basis='MEASURED'),name
    assert acc['metrics']['connection_active_seconds']['basis']=='MEASURED' and acc['metrics']['connection_active_seconds']['value']>=0 and acc['metrics']['hard_deadline_events']['value']==0
    assert acc['client_closure']['status']=='VERIFIED_FOR_EVERY_ATTEMPT' and acc['client_closure']['basis']=='THE_CLIENT_SIDE_BUDGET_RECEIPT_ONLY' and acc['server_session_verification'].startswith('NOT_PERFORMED_BY_THE_RESTRICTED_RUNTIME')
    # durable, independent records: one event per attempt carrying the receipt, and a progress snapshot with the cumulative accounting
    events=[json.loads(l) for l in (out/'events.jsonl').read_text().splitlines()]
    assert [e['payload']['receipt']['connection_attempts'] for e in events if e['event']=='qualification_attempt']==[1,1,1]
    progress=json.loads((out/'progress.json').read_text());assert progress['attempts_started']['value']==3 and progress['metrics']['connection_attempts']['value']==3
    # nothing secret anywhere
    blob=''.join(p.read_text() for p in out.iterdir() if p.is_file())
    assert not any(pw in blob for pw in SECRETS.values()) and 'postgresql://' not in blob and 'password authentication failed' not in blob
    assert result['use_blocked'] is True and 'NOT_A_DURABLE_DATABASE_BARRIER' in result['use_blocked_semantics'] and result['grant_may_be_issued_from_this_milestone'] is False and result['grants_issued']==0


def test_a_preparation_failure_is_not_started_not_a_measured_zero_and_not_a_verified_closure(entry,monkeypatch):
    def broken(progress):raise RuntimeError('private text must never escape')
    monkeypatch.setattr(sq,'resolve_addresses',broken)
    code,result,out=entry()
    assert code==1 and result['stop_reason']=='ROUTE_OR_CREDENTIAL_REJECTED_BEFORE_CONNECT' and result['attempts_total']==0 and result['detail']=='RuntimeError'
    acc=result['accounting']
    assert acc['attempts_started']['value']==0 and all(m['basis']=='NOT_STARTED' for m in acc['metrics'].values()) and acc['client_closure']['status']=='NOT_APPLICABLE_NO_ATTEMPT_STARTED'
    assert 'MEASURED' not in json.dumps(acc['metrics']) and 'VERIFIED' not in acc['client_closure']['status'] and 'private text' not in json.dumps(result) and result['use_blocked'] is True


def test_a_cancellation_during_an_attempt_keeps_that_attempts_receipt_and_stops_as_cancelled(entry,monkeypatch):
    def connect(cls,*a,**kw):
        os.kill(os.getpid(),signal.SIGTERM)          # the real signal handler installed by main()
        raise psycopg.OperationalError('unreached')
    monkeypatch.setattr(psycopg.Connection,'connect',classmethod(connect))
    code,result,out=entry()
    assert code==1 and result['stop_reason']=='CANCELLED' and result['attempts_total']==1
    a=result['roles'][WORKER]['attempts'][0]
    assert a['outcome']=='INTERRUPTED' and a['reason_code']=='CANCELLED' and a['receipt_basis']=='MEASURED' and a['receipt']['connection_attempts']==1 and a['receipt']['driver_statements']==0
    assert result['roles'][EFFECT]['attempts']==[] and result['accounting']['metrics']['connection_attempts']==dict(value=1,basis='MEASURED') and result['use_blocked'] is True


def test_a_request_arriving_just_after_the_run_returns_still_publishes_the_final_result(entry,monkeypatch):
    original=sq.Qualification.run
    def late(self):
        r=original(self);os.kill(os.getpid(),signal.SIGTERM);return r      # the request lands between run() and the final publication
    monkeypatch.setattr(sq.Qualification,'run',late)
    monkeypatch.setattr(psycopg.Connection,'connect',refuse('password authentication failed for user "x"'))
    code,result,out=entry()
    assert code==1 and (out/'final-result.json').exists() and '"final"' in (out/'events.jsonl').read_text().splitlines()[-1]


class UnreadableReceiptBudget:
    def __init__(self,**kw):self.connection_diagnostics=[]
    def engine(self,url,**kw):
        @contextmanager
        def connect():raise RuntimeError('boom')
        yield_ = SimpleNamespace(connect=connect);return yield_
    def close(self,_):raise RuntimeError('closing failed')


def test_an_unreadable_receipt_is_unknown_never_zero_and_never_verified_closure():
    events=[];q=sq.Qualification({WORKER:rr.url('POOLER',WORKER,'x'),EFFECT:rr.url('POOLER',EFFECT,'y')},emit=lambda e,p:events.append(p),ssl={},hostaddr='192.0.2.1',budget_factory=UnreadableReceiptBudget)
    r=q.run()
    a=r['roles'][WORKER]['attempts'][0]
    assert r['stop_reason']=='UNCERTAIN_CLOSURE' and r['attempts_total']==1 and a['receipt'] is None and a['receipt_basis']=='UNKNOWN' and a['client_closure_verified'] is False
    acc=r['accounting']
    assert acc['attempts_started']['value']==1 and acc['attempts_with_receipt']['value']==0 and all(m['basis']=='LOWER_BOUND_ONLY_SOME_RECEIPT_UNKNOWN' for m in acc['metrics'].values())
    assert acc['client_closure']['status']=='NOT_VERIFIED_FOR_SOME_ATTEMPT'


def test_the_cumulative_accounting_over_mixed_receipts_is_a_labelled_lower_bound():
    good=dict(receipt=dict(connection_attempts=1,driver_statements=3,returned_data_value_bytes=40,connection_active_seconds=0.5,connections_opened=1,connections_closed_count=1,cancel_attempts=0,cancel_failures=0,cancel_seconds=0.0,hard_deadline_events=[]),client_closure_verified=True)
    missing=dict(receipt=None,client_closure_verified=False)
    mixed=sq.Qualification.accounting_for([good,missing])
    assert mixed['metrics']['connection_attempts']=={'value':1,'basis':'LOWER_BOUND_ONLY_SOME_RECEIPT_UNKNOWN'} and mixed['client_closure']['status']=='NOT_VERIFIED_FOR_SOME_ATTEMPT'
    whole=sq.Qualification.accounting_for([good,good])
    assert whole['metrics']['driver_commands']=={'value':6,'basis':'MEASURED'} and whole['metrics']['returned_database_value_bytes']['value']==80 and whole['client_closure']['status']=='VERIFIED_FOR_EVERY_ATTEMPT'
    empty=sq.Qualification.accounting_for([])
    assert all(m=={'value':0,'basis':'NOT_STARTED'} for m in empty['metrics'].values())


def test_the_receipt_whitelist_exports_no_url_password_or_message():
    full={k:1 for k in sq.Qualification.RECEIPT_KEYS};full.update(slot_key='x',capture_checkpoint_sha256='y',password='secret',url='postgresql://u:p@h/db')
    clean=sq.Qualification.sanitise(full)
    assert set(clean)==set(sq.Qualification.RECEIPT_KEYS) and 'password' not in clean and 'url' not in clean and 'slot_key' not in clean
